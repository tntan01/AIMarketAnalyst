"""Đường AI nhận định xu hướng (plan lô L3.5) — controller §9.1 + dialog d.1621-1649.

Controller được kiểm với repository THẬT trên DB tạm (viết path: compose →
``add_verdicts`` → đọc lại qua ``verdicts_for``) + FakeAI đếm lời gọi `analyze`
(khuôn test_news_controller: fake có kiểu, không mock sâu, không mạng).  Dialog
kiểm offscreen với controller giả **có kiểu** (trả ``AiScopePreview`` /
``TrendAnalysisResult`` thật của ``controllers.news_controller``) — khuôn
test_news_screen_actions.  ``%APPDATA%`` không bao giờ bị chạm.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PyQt6.QtWidgets import QApplication, QLabel, QPushButton

from config.constants import SUPPORTED_SYMBOLS
from controllers.news_controller import (
    AiScopePreview,
    BatchScopeResult,
    BatchTrendResult,
    NewsController,
    PARSE_FAIL_TEXT,
    STRUCTURE_FAIL_TEXT,
    TrendAnalysisResult,
    UserNoteResult,
)
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    RateSource,
    TrendVerdict,
    VerdictConfidence,
    VerdictDirection,
    VerdictHorizon,
    VerdictScopeType,
)
from core.news_policy import load_news_policy
from core.rate_trend import RatePath, RateTrend
from core.trend_prompt_builder import MarketContext, build_trend_prompt
from core.yield_context import YieldContext, YieldDeltaSet
from services.news_repository import CurrencyRateTrend
from ui.screens import news_screen as news
from ui.screens.news_screen import NewsScreen

PROJECT_ROOT = Path(__file__).resolve().parents[1]
NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"

WIDE_FROM = "2000-01-01T00:00:00Z"
NOW = datetime(2026, 9, 23, 10, 0, tzinfo=UTC)  # cố định (các test không phụ thuộc đồng hồ)
NOW_ISO = NOW.isoformat(timespec="seconds").replace("+00:00", "Z")


def _repo(tmp_path: Path):
    from services.news_repository import NewsRepository

    return NewsRepository(db_path=tmp_path / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR)


def _past(days: int = 0, hours: int = 1) -> datetime:
    return NOW - timedelta(days=days, hours=hours)


class _FakeConfig:
    """Cấu hình AI giả — đúng bề mặt `settings.ai.active_provider()` (khuôn scanner)."""

    def __init__(self, provider: str = "deepseek", model: str = "deepseek-v4-flash", api_key: str = "key-1") -> None:
        self.provider = provider
        self.model = model
        self.api_key = api_key
        self.base_url = ""


class FakeAI:
    """Fake có kiểu của ``AIService``: ghi từng prompt, trả response đã dựng
    (scripted), đếm số lần gọi ``analyze``."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self.responses: list[str] = list(responses or [])
        self.calls: list[str] = []
        self.raise_error: Exception | None = None

    def analyze(self, prompt: str, max_tokens: int = 1800) -> str:
        self.calls.append(prompt)
        if self.raise_error is not None:
            raise self.raise_error
        if not self.responses:
            raise AssertionError("FakeAI hết response đã dựng")
        return self.responses.pop(0)


_USE_DEFAULT_CONFIG = object()


def _ai_controller(tmp_path: Path, ai: FakeAI, *, config: object = _USE_DEFAULT_CONFIG):
    if config is _USE_DEFAULT_CONFIG:
        config = _FakeConfig()
    return NewsController(
        repo=_repo(tmp_path),
        policy=load_news_policy(),
        rss_producer=object(),
        ai_service=ai,
        ai_config_provider=lambda: config,
    )


def _seed_items(controller: NewsController, count: int) -> None:
    """Gieo ``count`` tin nhập tay trong cửa sổ 7 ngày (đủ để vượt ai_min_items=3)."""
    for index in range(count):
        result: UserNoteResult = controller.add_user_note(
            kind="user_note",
            published_utc=_past(hours=1 + index),
            content=f"Tin nhập tay thứ {index}",
            currencies=["USD", "EUR"],
        )
        assert result.ok


def _verdict_json(ids: list[int], *, direction: str = "bullish", confidence: str = "high") -> str:
    """Một câu trả lời hợp lệ của model cho 3 chân trời (evidence trong prompt)."""
    return json.dumps(
        {
            "short": {
                "direction": direction,
                "confidence": confidence,
                "rationale": "Lập luận tiếng Việt.",
                "evidence_item_ids": ids,
            },
            "mid": {
                "direction": "neutral",
                "confidence": "medium",
                "rationale": "Lập luận tiếng Việt.",
                "evidence_item_ids": ids,
            },
            "long": {
                "direction": "insufficient_data",
                "confidence": "none",
                "rationale": "Lập luận tiếng Việt.",
                "evidence_item_ids": [],
            },
        },
        ensure_ascii=False,
    )


def _item_ids(controller: NewsController) -> list[int]:
    return [
        item.id
        for item in controller.items_in_range(WIDE_FROM, NOW_ISO)
        if item.id is not None
    ]


def _stored_verdicts(controller: NewsController) -> list[TrendVerdict]:
    return controller.verdicts_for("pair", "EUR/USD", 10)


# ---------------------------------------------------------------------------
# 1. Đường controller — §9.1 (repository thật + FakeAI đếm gọi)
# ---------------------------------------------------------------------------


class TestInsufficientData:
    def test_below_min_items_never_calls_the_ai(self, tmp_path):
        ai = FakeAI([_verdict_json([])])
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 2)  # 2 tin < ai_min_items=3

        preview = controller.ai_scope_preview("pair", "EUR/USD", NOW)
        assert (preview.event_count, preview.item_count, preview.min_items) == (0, 2, 3)
        assert preview.insufficient is True

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert result.insufficient is True
        assert ai.calls == []  # KHÔNG phát lời gọi AI (plan test d.331)
        assert _stored_verdicts(controller) == []


class TestHappyPath:
    def test_composes_and_stores_three_verdict_rows(self, tmp_path):
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai, config=_FakeConfig("deepseek", "deepseek-v4-flash"))
        _seed_items(controller, 3)
        ids = _item_ids(controller)
        assert len(ids) == 3
        ai.responses.append(_verdict_json(ids))

        preview = controller.ai_scope_preview("pair", "EUR/USD", NOW)
        assert preview.insufficient is False

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is True
        assert result.inserted == 3
        assert len(ai.calls) == 1
        stored = _stored_verdicts(controller)
        assert len(stored) == 3
        # Mới nhất trước — cùng created_at ⇒ id desc: long → mid → short.
        assert [v.horizon for v in stored] == [
            VerdictHorizon.LONG,
            VerdictHorizon.MID,
            VerdictHorizon.SHORT,
        ]
        # Đối chiếu provenance với hàm thuần — snapshot + prompt_hash khớp chính xác.
        from core.trend_prompt_builder import HorizonWindowSet

        policy = load_news_policy()
        outcome = build_trend_prompt(
            scope_type="pair",
            scope_value="EUR/USD",
            rows=controller._ai_rows("pair", "EUR/USD", NOW),
            context=MarketContext(),
            now=NOW,
            window_days=policy.ai_window_days,
            horizon_windows=HorizonWindowSet.from_policy(policy.ai_horizon_windows),
            long_max_rows=policy.ai_long_window_max_rows,
            horizons=policy.ai_horizons,
            min_items=policy.ai_min_items,
        )
        assert outcome.prompt is not None
        horizons_seen = set()
        for verdict in stored:
            assert verdict.input_snapshot == outcome.prompt.snapshot
            assert verdict.prompt_hash == outcome.prompt.prompt_hash
            assert verdict.provider == "deepseek"
            assert verdict.model == "deepseek-v4-flash"
            assert verdict.rationale == "Lập luận tiếng Việt."
            horizons_seen.add(verdict.horizon)
        assert horizons_seen == {VerdictHorizon.SHORT, VerdictHorizon.MID, VerdictHorizon.LONG}
        short = next(v for v in stored if v.horizon is VerdictHorizon.SHORT)
        assert short.direction is VerdictDirection.BULLISH
        assert short.confidence is VerdictConfidence.HIGH
        assert short.evidence_item_ids == ids  # dẫn chứng của model giữ nguyên
        long_ = next(v for v in stored if v.horizon is VerdictHorizon.LONG)
        assert long_.direction is VerdictDirection.INSUFFICIENT_DATA
        assert long_.evidence_item_ids == []


class TestParseFailures:
    def test_retryable_failure_retries_once_then_stores(self, tmp_path):
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ids = _item_ids(controller)
        ai.responses.extend(["không phải JSON gì cả", _verdict_json(ids)])

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is True
        assert len(ai.calls) == 2  # retry ĐÚNG MỘT lần (parser retryable)
        assert len(_stored_verdicts(controller)) == 3

    def test_exhausted_retry_stores_nothing_with_friendly_message(self, tmp_path):
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ai.responses.extend(["rác", "rác nữa"])

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert len(ai.calls) == 2
        assert result.error_message == PARSE_FAIL_TEXT
        assert _stored_verdicts(controller) == []  # không lưu verdict rác

    def test_schema_violation_gets_the_repair_retry_too(self, tmp_path):
        """Câu trả lời parse được nhưng vi phạm hợp đồng (thừa horizon).

        Lô D (QĐ 30/09/2026): lần retry duy nhất phủ MỌI từ chối — đo thật cho
        thấy chạy lại cùng prompt là model trả về đúng; cứu được phạm vi thay vì
        mất trắng."""
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ids = _item_ids(controller)
        bad = json.loads(_verdict_json(ids))
        bad["extra_horizon"] = {"direction": "bullish", "confidence": "high", "rationale": "x", "evidence_item_ids": []}
        ai.responses.extend([json.dumps(bad), _verdict_json(ids)])

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is True
        assert len(ai.calls) == 2
        assert "Your previous answer was rejected" in ai.calls[1]
        assert len(_stored_verdicts(controller)) == 3

    def test_two_schema_violations_still_store_nothing(self, tmp_path):
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ids = _item_ids(controller)
        bad = json.loads(_verdict_json(ids))
        bad["extra_horizon"] = {"direction": "bullish", "confidence": "high", "rationale": "x", "evidence_item_ids": []}
        ai.responses.extend([json.dumps(bad), json.dumps(bad)])

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert result.error_message == STRUCTURE_FAIL_TEXT
        assert result.error_type == "UnexpectedHorizon"
        assert len(ai.calls) == 2  # vẫn đúng một lần retry
        assert _stored_verdicts(controller) == []

    def test_fabricated_evidence_ids_refuse_the_whole_answer(self, tmp_path):
        """Doctrine §9.1 bước 3: dẫn chứng ngoài prompt = bịa — từ chối toàn bộ.

        Lô D: lần retry duy nhất chạy cho cả ca này (model có thể sửa sang id
        thật), nhưng hai lần bịa thì không verdict nào được lưu."""
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ai.responses.extend(
            [_verdict_json([9_999_999]), _verdict_json([9_999_999])]  # id không có trong prompt
        )

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert result.error_type == "InvalidEvidenceIds"
        assert len(ai.calls) == 2  # một lần retry, rồi dừng
        assert _stored_verdicts(controller) == []


class TestProviderErrors:
    def test_provider_error_is_friendly_and_nothing_is_stored(self, tmp_path):
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ai.raise_error = RuntimeError("Không kết nối được AI API: boom")

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert result.error_message == "Không kết nối được AI API: boom"  # friendly, không retry
        assert len(ai.calls) == 1
        assert _stored_verdicts(controller) == []

    def test_missing_ai_configuration_is_fail_closed_with_zero_calls(self, tmp_path):
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai, config=None)
        _seed_items(controller, 3)

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert result.error_message == "Chưa cấu hình AI Provider hoặc API key trong Settings."
        assert ai.calls == []  # 0 call
        assert _stored_verdicts(controller) == []

    def test_currency_scope_reads_only_that_currency(self, tmp_path):
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)  # USD/EUR — không phải JPY

        preview = controller.ai_scope_preview("currency", "JPY", NOW)

        assert (preview.event_count, preview.item_count) == (0, 0)
        assert preview.insufficient is True


# ---------------------------------------------------------------------------
# 2. Dialog — offscreen, controller giả có kiểu (khuôn test_news_screen_actions)
# ---------------------------------------------------------------------------

_APP = QApplication.instance() or QApplication(sys.argv)


def _app() -> QApplication:
    return _APP


def _derived_scopes() -> tuple[str, ...]:
    """11 tài sản rút từ SUPPORTED_SYMBOLS (khuôn controller.AI_ASSET_SCOPES)."""
    scopes: list[str] = []
    for symbol in SUPPORTED_SYMBOLS:
        for code in symbol.split("/"):
            code = code.strip()
            if code and code not in scopes:
                scopes.append(code)
    return tuple(scopes)


def _batch_result(ok: int = 11, insufficient: int = 0, error: int = 0) -> BatchTrendResult:
    results = tuple(
        BatchScopeResult(scope=scope, result=TrendAnalysisResult(ok=True))
        for scope in _derived_scopes()
    )
    return BatchTrendResult(results=results, ok=ok, insufficient=insufficient, error=error)


def _batch_result_with_reasons(reasons: dict[str, str]) -> BatchTrendResult:
    """Batch CÓ phạm vi lỗi thật kèm lý do — để kiểm dòng "Lý do lỗi"."""
    results = []
    for scope in _derived_scopes():
        reason = reasons.get(scope)
        result = (
            TrendAnalysisResult(ok=True)
            if reason is None
            else TrendAnalysisResult(ok=False, error_message=reason)
        )
        results.append(BatchScopeResult(scope=scope, result=result))
    return BatchTrendResult(
        results=tuple(results),
        ok=len(results) - len(reasons),
        insufficient=0,
        error=len(reasons),
    )


def _rate_context(currency: str = "USD", rate: float = 5.5) -> CurrencyRateTrend:
    return CurrencyRateTrend(
        currency=currency,
        latest=RateObservation(
            currency=currency,
            rate=rate,
            observed_at="2026-09-18",
            source=RateSource.FRED,
            fetched_at="2026-09-19T00:00:00Z",
            id=1,
        ),
        previous=None,
        trend=RateTrend.HOLD,
    )


def _yield_context() -> YieldContext:
    return YieldContext(
        yield_2y=3.72,
        observed_at_2y="2026-09-18",
        yield_10y=3.91,
        observed_at_10y="2026-09-18",
        be10y=2.36,
        observed_at_be10y="2026-09-18",
        delta_2y=-0.08,
        delta_10y=0.02,
        spread_2y10y=0.19,
        real_yield_10y=1.55,
    )


class FakeAiController:
    """Controller giả của dialog: trả preview/result/history THẬT, ghi lời gọi."""

    def __init__(
        self,
        preview: AiScopePreview,
        result: TrendAnalysisResult | None = None,
        history: list[TrendVerdict] | None = None,
        events: list[CalendarEvent] | None = None,
        items: list[NewsItem] | None = None,
        verdicts_by_scope: dict[str, list[TrendVerdict]] | None = None,
        batch_result: BatchTrendResult | None = None,
    ) -> None:
        self.preview = preview
        self.result = result if result is not None else TrendAnalysisResult(ok=True)
        self.history = list(history or [])
        self.events = list(events or [])
        self.items = list(items or [])
        self.verdicts_by_scope = dict(verdicts_by_scope or {})
        self.batch_result = batch_result
        self.preview_calls: list[tuple[str, str]] = []
        self.history_calls: list[tuple[str, str, int]] = []
        self.analyze_calls: list[tuple[str, str]] = []
        self.batch_calls: list[object] = []
        self.gate: threading.Event | None = None
        self.analyze_error: Exception | None = None
        self.AI_ASSET_SCOPES = _derived_scopes()

    def ai_scope_preview(self, scope_type, scope_value):
        self.preview_calls.append((scope_type, scope_value))
        return self.preview

    def analyze_trend(self, scope_type, scope_value):
        self.analyze_calls.append((scope_type, scope_value))
        if self.gate is not None:
            self.gate.wait(timeout=5)
        if self.analyze_error is not None:
            raise self.analyze_error
        return self.result

    def analyze_all_trends(self, now=None, on_scope_done=None):
        self.batch_calls.append(on_scope_done)
        result = self.batch_result if self.batch_result is not None else _batch_result()
        if on_scope_done is not None:
            for entry in result.results:
                on_scope_done(entry.scope, entry.result)
        return result

    def verdicts_for(self, scope_type, scope_value, limit):
        self.history_calls.append((scope_type, scope_value, limit))
        if scope_value in self.verdicts_by_scope:
            return list(self.verdicts_by_scope[scope_value])[:limit]
        return list(self.history)

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        return list(self.events)

    def items_in_range(self, from_utc, to_utc=None, kinds=None, currencies=None, exclude_flagged=True):
        return list(self.items)


EVENT = CalendarEvent(
    day_key="2026-09-20",
    event_time_utc="2026-09-20T14:30:00Z",
    currency="USD",
    title="FOMC Meeting",
    impact=EventImpact.HIGH,
    status=EventStatus.RELEASED,
    source=EventSource.FF_HTML,
    dedupe_key="ev-1",
    fetched_at="2026-09-20T15:00:00Z",
    actual="5.50%",
    id=7,
)
EVIDENCE_ITEM = NewsItem(
    kind=NewsItemKind.HEADLINE,
    source=NewsItemSource.GOOGLE_NEWS_RSS,
    title="Fed signals patience",
    published_utc="2026-09-21T08:00:00Z",
    currencies=["USD"],
    dedupe_key="item-1",
    fetched_at="2026-09-21T09:00:00Z",
    id=11,
)
HIDDEN_ITEM = NewsItem(
    kind=NewsItemKind.HEADLINE,
    source=NewsItemSource.GOOGLE_NEWS_RSS,
    title="Hidden row",
    published_utc="2026-09-22T08:00:00Z",
    currencies=["EUR"],
    dedupe_key="item-2",
    fetched_at="2026-09-22T09:00:00Z",
    id=12,
)

_DIALOGS: list[news.AiTrendDialog] = []
_SCREENS: list[NewsScreen] = []


@pytest.fixture(scope="module", autouse=True)
def _teardown():
    yield
    for dialog in _DIALOGS:
        dialog._shutdown_ai()
    for screen in _SCREENS:
        screen.shutdown()
    _app().processEvents()


def _wait_until(predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        _app().processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _preview(
    *,
    events: int = 0,
    items: int = 3,
    min_items: int = 3,
    context: MarketContext | None = None,
    short_days: int = 7,
    mid_days: int = 42,
    long_days: int = 180,
    long_max_rows: int = 50,
    short_rows: int = 0,
    mid_rows: int = 0,
    long_rows: int = 0,
) -> AiScopePreview:
    context = context if context is not None else MarketContext()
    return AiScopePreview(
        scope_type="currency",
        scope_value="USD",
        window_days=7,
        event_count=events,
        item_count=items,
        min_items=min_items,
        rate_available=bool(context.rates),
        yields_available=context.yields is not None,
        context=context,
        short_days=short_days,
        mid_days=mid_days,
        long_days=long_days,
        long_max_rows=long_max_rows,
        short_rows=short_rows,
        mid_rows=mid_rows,
        long_rows=long_rows,
    )


def _verdict(
    horizon: VerdictHorizon,
    *,
    direction: VerdictDirection = VerdictDirection.BULLISH,
    confidence: VerdictConfidence = VerdictConfidence.HIGH,
    created_at: str = "2026-09-23T09:00:00Z",
    ids: tuple[int, ...] = (11,),
) -> TrendVerdict:
    return TrendVerdict(
        created_at=created_at,
        scope_type=VerdictScopeType.PAIR,
        scope_value="EUR/USD",
        horizon=horizon,
        direction=direction,
        confidence=confidence,
        rationale="Lập luận tiếng Việt.",
        evidence_item_ids=list(ids),
        input_snapshot={"window_days": 7, "event_count": 0, "item_count": 3},
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt_hash="hash-abc",
    )


def _result(*verdicts: TrendVerdict, inserted: int = 3) -> TrendAnalysisResult:
    return TrendAnalysisResult(ok=True, verdicts=tuple(verdicts), inserted=inserted)


def _dialog(controller: FakeAiController, on_evidence=None) -> news.AiTrendDialog:
    dialog = news.AiTrendDialog(controller, on_evidence)
    dialog.show()
    _app().processEvents()
    _DIALOGS.append(dialog)
    return dialog


def _screen(controller: FakeAiController) -> NewsScreen:
    screen = NewsScreen(None, app=SimpleNamespace(news_controller=controller))
    screen.resize(752, 500)
    screen.show()
    _app().processEvents()
    _wait_until(lambda: bool(controller.preview is not None))
    _SCREENS.append(screen)
    return screen


def _header_text(dialog: news.AiTrendDialog, horizon: str) -> str:
    """Chuỗi hiển thị của header thẻ: nhãn chân trời + hướng (kéo dấu)."""
    card = dialog._cards[horizon]
    return card["header"].text() + " " + card["direction"].text()


def _select_detail(dialog: news.AiTrendDialog, scope: str = "USD") -> None:
    dialog._detail_combo.setCurrentIndex(dialog._detail_combo.findData(scope))


class TestAiDialogSmoke:
    def test_default_tab_is_overview_and_open_calls_no_ai(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)

        assert dialog.windowTitle() == news.AI_TEXT
        advisory = dialog.findChild(QLabel, "NewsAiAdvisory")
        assert advisory is not None
        assert advisory.text() == news.AI_ADVISORY_TEXT  # nguyên văn d.1638, thường trực
        assert dialog._tabs.count() == 3
        assert [dialog._tabs.tabText(i) for i in range(3)] == [
            news.AI_TAB_OVERVIEW_TEXT,
            news.AI_TAB_DETAIL_TEXT,
            news.AI_TAB_PAIR_TEXT,
        ]
        assert dialog._tabs.currentIndex() == 0  # mặc định "Tổng quan"
        # Mở dialog chỉ ĐỌC — không gọi AI (kể cả batch).
        assert controller.analyze_calls == []
        assert controller.batch_calls == []

    def test_dialog_is_fixed_800x600(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)

        assert (dialog.width(), dialog.height()) == (800, 600)
        assert dialog.minimumSize() == dialog.maximumSize()

    def test_overview_grid_lists_eleven_assets(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)

        assert dialog._overview_table.model() is dialog._overview_model
        assert dialog._overview_model.rowCount() == 11
        scopes = [dialog._overview_model.scope_at(i) for i in range(11)]
        assert scopes == list(controller.AI_ASSET_SCOPES)
        assert news.AI_OVERVIEW_COLUMNS == (
            "Tài sản", "Ngắn hạn", "Trung hạn", "Dài hạn", "Verdict lúc",
        )

    def test_detail_combo_and_count_come_from_the_controller(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)

        items = [
            dialog._detail_combo.itemData(i)
            for i in range(dialog._detail_combo.count())
        ]
        assert items == list(controller.AI_ASSET_SCOPES)
        assert controller.preview_calls[0] == ("currency", controller.AI_ASSET_SCOPES[0])
        assert dialog._count_label.text() == news.AI_COUNT_TEXT.format(window_days=7, count=3)

    def test_detail_context_line_renders_typed_values(self):
        context = MarketContext(
            rates=(_rate_context("USD", 5.5),), yields=_yield_context()
        )
        controller = FakeAiController(_preview(context=context))
        dialog = _dialog(controller)

        text = dialog._context_label.text()
        assert "Lãi suất 5.50% (hold)" in text
        assert "US 2Y 3.72% (-0.08; 3m —; 6m —)" in text
        assert "US 10Y 3.91% (+0.02; 3m —; 6m —)" in text
        assert "Spread 2Y10Y +0.19" in text
        assert "Real yield 1.55%" in text

    def test_detail_context_line_dash_when_missing(self):
        controller = FakeAiController(_preview())  # context rỗng
        dialog = _dialog(controller)

        assert dialog._context_label.text() == f"{news.AI_CONTEXT_PREFIX} —"

    def test_insufficient_preview_shows_message_and_never_calls_ai(self):
        controller = FakeAiController(_preview(items=2), result=TrendAnalysisResult(ok=False, insufficient=True))
        dialog = _dialog(controller)

        assert dialog._status_label.text() == news.AI_INSUFFICIENT_TEXT  # d.1642 hiện sẵn
        dialog._analyze_button.click()
        _app().processEvents()

        assert controller.analyze_calls == []  # KHÔNG gọi AI (B4)
        assert dialog._status_label.text() == news.AI_INSUFFICIENT_TEXT


class TestAiOverview:
    @staticmethod
    def _row(dialog, scope: str = "USD") -> int:
        scopes = [
            dialog._overview_model.scope_at(i)
            for i in range(dialog._overview_model.rowCount())
        ]
        return scopes.index(scope)

    def test_latest_verdict_per_horizon_is_shown(self):
        from PyQt6.QtCore import Qt

        news._configure_display_timezone("Asia/Ho_Chi_Minh")
        verdicts = {
            "USD": [
                _verdict(VerdictHorizon.SHORT, created_at="2026-09-23T09:00:00Z"),
                _verdict(
                    VerdictHorizon.MID,
                    direction=VerdictDirection.BEARISH,
                    confidence=VerdictConfidence.LOW,
                ),
                _verdict(
                    VerdictHorizon.LONG,
                    direction=VerdictDirection.NEUTRAL,
                    confidence=VerdictConfidence.MEDIUM,
                ),
            ]
        }
        controller = FakeAiController(_preview(), verdicts_by_scope=verdicts)
        dialog = _dialog(controller)
        model = dialog._overview_model
        row = self._row(dialog)

        assert "▲" in model.data(model.index(row, 1), Qt.ItemDataRole.DisplayRole)
        assert "▼" in model.data(model.index(row, 2), Qt.ItemDataRole.DisplayRole)
        assert model.data(model.index(row, 4), Qt.ItemDataRole.DisplayRole) == "23/09/2026 16:00"

    def test_never_judged_scope_shows_chua_co(self):
        from PyQt6.QtCore import Qt

        controller = FakeAiController(_preview())  # không có verdict nào
        dialog = _dialog(controller)
        model = dialog._overview_model
        row = self._row(dialog)

        assert model.data(model.index(row, 1), Qt.ItemDataRole.DisplayRole) == news.NO_VALUE
        assert (
            model.data(model.index(row, 4), Qt.ItemDataRole.DisplayRole)
            == news.AI_NO_VERDICT_TEXT
        )

    def test_row_click_switches_to_the_detail_scope(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)
        row = self._row(dialog)

        dialog._on_overview_clicked(dialog._overview_model.index(row, 0))

        assert dialog._tabs.currentWidget() is dialog._detail_tab
        assert dialog._detail_combo.currentData() == "USD"

    def test_batch_button_runs_the_batch_and_reloads_the_grid(self):
        controller = FakeAiController(
            _preview(), batch_result=_batch_result(ok=9, insufficient=1, error=1)
        )
        dialog = _dialog(controller)
        reads_before = len(controller.history_calls)

        dialog._batch_button.click()
        assert _wait_until(lambda: len(controller.batch_calls) == 1)
        assert _wait_until(lambda: dialog._batch_button.isEnabled())

        assert dialog._batch_status.text() == news.AI_BATCH_SUMMARY_TEXT.format(
            ok=9, insufficient=1, error=1
        )
        assert len(controller.history_calls) > reads_before  # lưới nạp lại

    def test_batch_summary_shows_the_reason_of_failed_scopes(self):
        # Owner yêu cầu 30/09/2026: tổng kết batch phải nói VÌ SAO lỗi, không chỉ
        # đếm — nhiều phạm vi cùng một lý do thì gom thành một nhóm.
        reason = "AI hết giới hạn token trước khi tạo được nội dung."
        controller = FakeAiController(
            _preview(),
            batch_result=_batch_result_with_reasons({"EUR": reason, "USD": reason}),
        )
        dialog = _dialog(controller)

        dialog._batch_button.click()
        assert _wait_until(lambda: len(controller.batch_calls) == 1)
        assert _wait_until(lambda: dialog._batch_button.isEnabled())

        text = dialog._batch_status.text()
        assert text.startswith(
            news.AI_BATCH_SUMMARY_TEXT.format(ok=9, insufficient=0, error=2)
        )
        assert news.AI_BATCH_REASON_TEXT.format(detail=reason) in text
        assert "EUR" in text and "USD" in text  # nhóm lý do kèm phạm vi

    def test_batch_summary_has_no_reason_line_when_nothing_failed(self):
        controller = FakeAiController(_preview(), batch_result=_batch_result())
        dialog = _dialog(controller)

        dialog._batch_button.click()
        assert _wait_until(lambda: len(controller.batch_calls) == 1)
        assert _wait_until(lambda: dialog._batch_button.isEnabled())

        assert dialog._batch_status.text() == news.AI_BATCH_SUMMARY_TEXT.format(
            ok=11, insufficient=0, error=0
        )

    def test_batch_summary_shows_the_structure_reason_for_a_schema_failure(self):
        # Lô C (ca "Nhận định AI — độ bền kết quả"): câu chữ theo LOẠI lỗi — lỗi
        # cấu trúc verdict hiện đúng câu của nó, không lẫn với "JSON hỏng".
        reason = STRUCTURE_FAIL_TEXT
        controller = FakeAiController(
            _preview(), batch_result=_batch_result_with_reasons({"XAU": reason})
        )
        dialog = _dialog(controller)

        dialog._batch_button.click()
        assert _wait_until(lambda: len(controller.batch_calls) == 1)
        assert _wait_until(lambda: dialog._batch_button.isEnabled())

        text = dialog._batch_status.text()
        assert reason in text
        assert "XAU" in text
        assert reason != PARSE_FAIL_TEXT  # hai loại lỗi khác nhau, hai câu khác nhau


class TestAiDialogAnalysis:
    def test_runs_in_background_disables_button_and_renders_verdicts(self):
        verdicts = (
            _verdict(VerdictHorizon.SHORT),
            _verdict(VerdictHorizon.MID, direction=VerdictDirection.NEUTRAL, confidence=VerdictConfidence.MEDIUM),
            _verdict(
                VerdictHorizon.LONG,
                direction=VerdictDirection.INSUFFICIENT_DATA,
                confidence=VerdictConfidence.NONE,
            ),
        )
        controller = FakeAiController(_preview(), result=_result(*verdicts))
        controller.gate = threading.Event()
        dialog = _dialog(controller)
        _select_detail(dialog, "USD")

        dialog._analyze_button.click()
        assert _wait_until(lambda: not dialog._analyze_button.isEnabled())
        assert dialog._status_label.text() == news.AI_PROGRESS_TEXT  # progress + disable (d.1615)

        controller.gate.set()
        assert _wait_until(lambda: dialog._analyze_button.isEnabled())
        assert _wait_until(lambda: "▲" in _header_text(dialog, "short"))
        assert ("Ngắn hạn" in _header_text(dialog, "short") and "Tăng" in _header_text(dialog, "short"))
        assert ("Trung hạn" in _header_text(dialog, "mid") and "—" in _header_text(dialog, "mid") and "Trung lập" in _header_text(dialog, "mid"))
        assert ("Dài hạn" in _header_text(dialog, "long") and "Không đủ dữ liệu" in _header_text(dialog, "long"))
        # Màu semantic của hướng (d.1633) — tô qua QPalette, đúng vai trò success/danger.
        from PyQt6.QtGui import QPalette
        from ui.theme_manager import semantic_qcolor

        short_color = dialog._cards["short"]["direction"].palette().color(QPalette.ColorRole.WindowText)
        assert short_color.name() == semantic_qcolor("success").name()
        mid_color = dialog._cards["mid"]["direction"].palette().color(QPalette.ColorRole.WindowText)
        assert mid_color.name() == semantic_qcolor("text_muted").name()
        assert dialog._cards["short"]["conf"].text() == "Cao"
        assert dialog._cards["mid"]["conf"].text() == "Trung bình"
        assert dialog._cards["long"]["conf"].text() == "Không có"
        assert dialog._cards["short"]["rationale"].text() == "Lập luận tiếng Việt."
        assert controller.analyze_calls == [("currency", "USD")]

    def test_failed_result_shows_friendly_message_without_cards(self):
        controller = FakeAiController(
            _preview(),
            result=TrendAnalysisResult(ok=False, error_message="AI không trả về JSON hợp lệ."),
        )
        dialog = _dialog(controller)
        _select_detail(dialog, "USD")

        dialog._analyze_button.click()
        assert _wait_until(lambda: dialog._analyze_button.isEnabled())
        assert dialog._status_label.text() == "AI không trả về JSON hợp lệ."
        assert dialog._cards["short"]["frame"].isHidden() is True
        assert controller.analyze_calls == [("currency", "USD")]

    def test_worker_exception_shows_the_message(self):
        controller = FakeAiController(_preview())
        controller.analyze_error = RuntimeError("Không kết nối được AI API: boom")
        dialog = _dialog(controller)

        dialog._analyze_button.click()
        assert _wait_until(lambda: dialog._analyze_button.isEnabled())
        assert dialog._status_label.text() == "Không kết nối được AI API: boom"


class TestAiDialogHistory:
    def test_history_lists_verdicts_with_registered_labels(self):
        # Múi giờ hiển thị cố định (Asia/Ho_Chi_Minh) — hiển thị theo múi giờ
        # người dùng (Owner 25/09/2026), không phụ thuộc settings máy chạy test.
        news._configure_display_timezone("Asia/Ho_Chi_Minh")
        history = [
            _verdict(VerdictHorizon.LONG, created_at="2026-09-23T09:00:00Z", direction=VerdictDirection.NEUTRAL),
            _verdict(VerdictHorizon.SHORT, created_at="2026-09-22T09:00:00Z"),
        ]
        controller = FakeAiController(_preview(), history=history)
        dialog = _dialog(controller)
        _select_detail(dialog, "USD")

        assert ("currency", "USD", news.AI_HISTORY_LIMIT) in controller.history_calls
        texts = [label.text() for label in dialog._history_layout.parent().findChildren(QLabel)]
        assert any("23/09/2026 16:00" in t and "Dài hạn" in t and "Trung lập" in t for t in texts)
        assert any("22/09/2026 16:00" in t and "Ngắn hạn" in t and "Tăng" in t for t in texts)

    def test_history_refreshes_after_a_successful_analysis(self):
        controller = FakeAiController(_preview(), result=_result(_verdict(VerdictHorizon.SHORT), inserted=1))
        dialog = _dialog(controller)
        reads_before = len(controller.history_calls)

        dialog._analyze_button.click()
        assert _wait_until(lambda: len(controller.history_calls) > reads_before)


class TestAiDialogEvidence:
    @pytest.mark.parametrize("evidence_id", [11, 12])
    def test_evidence_click_closes_dialog_and_selects_the_row(self, tmp_path, evidence_id):
        controller = FakeAiController(
            _preview(),
            result=_result(_verdict(VerdictHorizon.SHORT, ids=(evidence_id,)), inserted=1),
            items=[EVIDENCE_ITEM, HIDDEN_ITEM],
        )
        screen = _screen(controller)
        dialog = _dialog(controller, on_evidence=screen._jump_to_evidence)
        _wait_until(lambda: screen.table_model.rowCount() == 2)

        dialog._analyze_button.click()
        assert _wait_until(lambda: "▲" in _header_text(dialog, "short"))
        evidence_button = next(
            button
            for button in dialog._cards["short"]["frame"].findChildren(QPushButton)
            if button.text() == str(evidence_id)
        )
        evidence_button.click()
        _app().processEvents()

        assert dialog.result() == 1  # đóng dialog (d.1646)
        selected = screen.table.selectionModel().selectedRows()
        assert len(selected) == 1
        row = screen.table_model.rows[selected[0].row()]
        assert row.item is not None and row.item.id == evidence_id  # nhảy đúng dòng dẫn chứng


class TestAiPair:
    def test_pair_tab_is_read_only_on_open(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)

        assert dialog._pair_combo.count() == len(SUPPORTED_SYMBOLS)
        assert [
            dialog._pair_combo.itemData(i) for i in range(dialog._pair_combo.count())
        ] == list(SUPPORTED_SYMBOLS)
        assert controller.analyze_calls == []
        assert controller.batch_calls == []

    def test_pair_bias_rendered_from_component_verdicts(self):
        verdicts = {
            "EUR": [
                _verdict(VerdictHorizon.SHORT, direction=VerdictDirection.BULLISH, confidence=VerdictConfidence.HIGH)
            ],
            "USD": [
                _verdict(VerdictHorizon.SHORT, direction=VerdictDirection.BEARISH, confidence=VerdictConfidence.LOW)
            ],
        }
        controller = FakeAiController(_preview(), verdicts_by_scope=verdicts)
        dialog = _dialog(controller)
        row = dialog._pair_rows["short"]

        assert row["base"].text() == "EUR: ▲ Tăng (Cao)"
        assert row["quote"].text() == "USD: ▼ Giảm (Thấp)"
        assert row["bias"].text() == f"{news.AI_PAIR_BIAS_PREFIX} Nghiêng tăng"
        assert controller.analyze_calls == []  # không gọi AI

    def test_missing_leg_bias_is_unclear(self):
        controller = FakeAiController(
            _preview(),
            verdicts_by_scope={"EUR": [_verdict(VerdictHorizon.SHORT)]},
        )
        dialog = _dialog(controller)

        assert (
            dialog._pair_rows["short"]["bias"].text()
            == f"{news.AI_PAIR_BIAS_PREFIX} Không rõ"
        )

    def test_pair_note_is_always_shown(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)

        labels = [label.text() for label in dialog._pair_tab.findChildren(QLabel)]
        assert news.AI_PAIR_NOTE_TEXT in labels

    def test_deep_dive_calls_analyze_trend_pair(self):
        controller = FakeAiController(_preview(), result=_result(_verdict(VerdictHorizon.SHORT)))
        dialog = _dialog(controller)

        dialog._pair_deep_button.click()
        assert _wait_until(lambda: dialog._pair_deep_button.isEnabled())

        assert ("pair", "EUR/USD") in controller.analyze_calls
        # isHidden() reflects the card's own setVisible (the pair tab itself is
        # not the current tab, so isVisible() would be False regardless).
        assert _wait_until(lambda: not dialog._pair_cards["short"]["frame"].isHidden())


# ---------------------------------------------------------------------------
# 3. Ranh giới mạng của dialog — màn không gọi thẳng producer/network
# ---------------------------------------------------------------------------


def test_ai_dialog_issue_no_direct_services_import_in_screen_source():
    source = Path(news.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "import urllib", "import socket", "from services."):
        assert forbidden not in source, forbidden


# ---------------------------------------------------------------------------
# 4. Panel độ phủ theo chân trời + dòng ngữ cảnh mở rộng (đợt 6 — C4)
# ---------------------------------------------------------------------------


def _yield_context_with_deltas() -> YieldContext:
    """YieldContext đủ delta 3m/6m (đợt 6) cho dòng ngữ cảnh mở rộng."""
    return YieldContext(
        yield_2y=3.72,
        observed_at_2y="2026-09-18",
        yield_10y=3.91,
        observed_at_10y="2026-09-18",
        be10y=2.36,
        observed_at_be10y="2026-09-18",
        delta_2y=-0.08,
        delta_10y=0.02,
        spread_2y10y=0.19,
        real_yield_10y=1.55,
        delta_3m=YieldDeltaSet(delta_2y=-0.15, delta_10y=0.10),
        delta_6m=YieldDeltaSet(delta_2y=-0.30),  # 10Y 6m thiếu → "—"
    )


class TestAiDialogHorizonCoverage:
    """Panel độ phủ + dòng ngữ cảnh mở rộng (đợt 6) — UI chỉ định dạng dữ liệu
    preview (không gọi AI, không hard-code ngày/tối đa)."""

    def test_coverage_panel_renders_preview_counts_days_and_cap(self):
        controller = FakeAiController(_preview(short_rows=4, mid_rows=4, long_rows=5))
        dialog = _dialog(controller)

        assert dialog._coverage_label.text() == (
            "Độ phủ theo chân trời: Ngắn 7 ngày: 4 dòng · Trung 42 ngày: 4 dòng"
            " · Dài 180 ngày: 5 dòng (tối đa 50)"
        )

    def test_coverage_panel_follows_the_preview_counts(self):
        controller = FakeAiController(_preview(short_rows=1, mid_rows=2, long_rows=3))
        dialog = _dialog(controller)
        first = dialog._coverage_label.text()
        assert "Ngắn 7 ngày: 1 dòng" in first
        assert "Trung 42 ngày: 2 dòng" in first
        assert "Dài 180 ngày: 3 dòng" in first

        controller.preview = _preview(short_rows=9, mid_rows=8, long_rows=7)
        dialog._on_detail_scope_changed()

        changed = dialog._coverage_label.text()
        assert changed != first
        assert "Ngắn 7 ngày: 9 dòng" in changed
        assert "Trung 42 ngày: 8 dòng" in changed
        assert "Dài 180 ngày: 7 dòng" in changed

    def test_opening_the_detail_tab_never_calls_the_ai(self):
        controller = FakeAiController(_preview(short_rows=1, mid_rows=1, long_rows=1))
        dialog = _dialog(controller)

        assert controller.preview_calls  # preview đã đọc (chỉ đọc)
        assert controller.analyze_calls == []
        assert controller.batch_calls == []

    def test_context_line_renders_rate_path_and_3m_6m_deltas(self):
        context = MarketContext(
            rates=(_rate_context("USD", 5.5),),
            yields=_yield_context_with_deltas(),
            rate_path=RatePath(rate_now=4.35, rate_then=4.10, change=0.25),
        )
        controller = FakeAiController(_preview(context=context))
        dialog = _dialog(controller)

        text = dialog._context_label.text()
        assert "US 2Y 3.72% (-0.08; 3m -0.15; 6m -0.30)" in text
        assert "US 10Y 3.91% (+0.02; 3m +0.10; 6m —)" in text
        assert "Rate path 6 tháng: +0.25 (từ 4.10 → 4.35)" in text

    def test_context_line_dash_when_rate_path_components_missing(self):
        context = MarketContext(
            rate_path=RatePath(rate_now=None, rate_then=None, change=None)
        )
        controller = FakeAiController(_preview(context=context))
        dialog = _dialog(controller)

        assert "Rate path 6 tháng: — (từ — → —)" in dialog._context_label.text()

    def test_context_line_dash_when_delta_6m_missing(self):
        context = MarketContext(
            yields=YieldContext(
                yield_2y=3.72,
                observed_at_2y="2026-09-18",
                yield_10y=3.91,
                observed_at_10y="2026-09-18",
                be10y=None,
                observed_at_be10y=None,
                delta_2y=-0.08,
                delta_10y=0.02,
                spread_2y10y=0.19,
                real_yield_10y=None,
                delta_3m=YieldDeltaSet(delta_2y=-0.15),
                delta_6m=YieldDeltaSet(),  # mọi mốc 6m thiếu
            )
        )
        controller = FakeAiController(_preview(context=context))
        dialog = _dialog(controller)

        text = dialog._context_label.text()
        assert "US 2Y 3.72% (-0.08; 3m -0.15; 6m —)" in text
        assert "Spread 2Y10Y +0.19" in text  # giữ khuôn đợt 5 (không gắn delta)