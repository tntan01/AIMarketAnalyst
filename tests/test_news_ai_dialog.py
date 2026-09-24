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
    NewsController,
    PARSE_FAIL_TEXT,
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
    TrendVerdict,
    VerdictConfidence,
    VerdictDirection,
    VerdictHorizon,
    VerdictScopeType,
)
from core.news_policy import load_news_policy
from core.trend_prompt_builder import build_trend_prompt
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

    def analyze(self, prompt: str) -> str:
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
        policy = load_news_policy()
        outcome = build_trend_prompt(
            scope_type="pair",
            scope_value="EUR/USD",
            events=controller.events_in_range(WIDE_FROM, NOW_ISO),
            items=controller.items_in_range(WIDE_FROM, NOW_ISO),
            now=NOW,
            window_days=policy.ai_window_days,
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

    def test_non_retryable_answer_is_refused_after_one_call(self, tmp_path):
        """Câu trả lời parse được nhưng vi phạm hợp đồng (thừa horizon) — không retry."""
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ids = _item_ids(controller)
        bad = json.loads(_verdict_json(ids))
        bad["extra_horizon"] = {"direction": "bullish", "confidence": "high", "rationale": "x", "evidence_item_ids": []}
        ai.responses.append(json.dumps(bad))

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert len(ai.calls) == 1  # không retry (không retryable)
        assert _stored_verdicts(controller) == []

    def test_fabricated_evidence_ids_refuse_the_whole_answer(self, tmp_path):
        """Doctrine §9.1 bước 3: dẫn chứng ngoài prompt = bịa — từ chối toàn bộ."""
        ai = FakeAI()
        controller = _ai_controller(tmp_path, ai)
        _seed_items(controller, 3)
        ai.responses.append(_verdict_json([9_999_999]))  # id không có trong prompt

        result = controller.analyze_trend("pair", "EUR/USD", NOW)

        assert result.ok is False
        assert len(ai.calls) == 1
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


class FakeAiController:
    """Controller giả của dialog: trả preview/result/history THẬT, ghi lời gọi."""

    def __init__(
        self,
        preview: AiScopePreview,
        result: TrendAnalysisResult | None = None,
        history: list[TrendVerdict] | None = None,
        events: list[CalendarEvent] | None = None,
        items: list[NewsItem] | None = None,
    ) -> None:
        self.preview = preview
        self.result = result if result is not None else TrendAnalysisResult(ok=True)
        self.history = list(history or [])
        self.events = list(events or [])
        self.items = list(items or [])
        self.preview_calls: list[tuple[str, str]] = []
        self.history_calls: list[tuple[str, str, int]] = []
        self.analyze_calls: list[tuple[str, str]] = []
        self.gate: threading.Event | None = None
        self.analyze_error: Exception | None = None

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

    def verdicts_for(self, scope_type, scope_value, limit):
        self.history_calls.append((scope_type, scope_value, limit))
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


def _preview(*, events: int = 0, items: int = 3, min_items: int = 3) -> AiScopePreview:
    return AiScopePreview(
        scope_type="pair",
        scope_value="EUR/USD",
        window_days=7,
        event_count=events,
        item_count=items,
        min_items=min_items,
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


class TestAiDialogSmoke:
    def test_dialog_shows_registered_labels_and_scope_sources(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)

        assert dialog.windowTitle() == news.AI_TEXT
        advisory = dialog.findChild(QLabel, "NewsAiAdvisory")
        assert advisory is not None
        assert advisory.text() == news.AI_ADVISORY_TEXT  # nguyên văn d.1638, thường trực
        # Phạm vi: SUPPORTED_SYMBOLS (tiêu thụ — không bịa) rồi các đồng tiền rút từ cặp.
        items = [dialog._scope_combo.itemData(i) for i in range(dialog._scope_combo.count())]
        pairs = [data for data in items if data[0] == "pair"]
        assert [data[1] for data in pairs] == list(SUPPORTED_SYMBOLS)
        currencies = [data[1] for data in items if data[0] == "currency"]
        assert "JPY" in currencies and "EUR" in currencies and "XAU" in currencies
        assert controller.preview_calls[0] == ("pair", "EUR/USD")
        # Dòng đếm (§9.1 bước 2) — chuỗi mockup d.1629.
        assert dialog._count_label.text() == news.AI_COUNT_TEXT.format(window_days=7, count=3)

    def test_scope_switch_reads_the_new_scope_preview(self):
        controller = FakeAiController(_preview())
        dialog = _dialog(controller)
        currency_index = next(
            i for i in range(dialog._scope_combo.count())
            if dialog._scope_combo.itemData(i)[0] == "currency"
        )

        dialog._scope_combo.setCurrentIndex(currency_index)
        _app().processEvents()

        assert controller.preview_calls[-1] == ("currency", dialog._scope_combo.itemData(currency_index)[1])

    def test_insufficient_preview_shows_message_and_never_calls_ai(self):
        controller = FakeAiController(_preview(items=2), result=TrendAnalysisResult(ok=False, insufficient=True))
        dialog = _dialog(controller)

        assert dialog._status_label.text() == news.AI_INSUFFICIENT_TEXT  # d.1642 hiện sẵn
        dialog._analyze_button.click()
        _app().processEvents()

        assert controller.analyze_calls == []  # KHÔNG gọi AI (B4)
        assert dialog._status_label.text() == news.AI_INSUFFICIENT_TEXT


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
        assert controller.analyze_calls == [("pair", "EUR/USD")]

    def test_failed_result_shows_friendly_message_without_cards(self):
        controller = FakeAiController(
            _preview(),
            result=TrendAnalysisResult(ok=False, error_message="AI không trả về JSON hợp lệ."),
        )
        dialog = _dialog(controller)

        dialog._analyze_button.click()
        assert _wait_until(lambda: dialog._analyze_button.isEnabled())
        assert dialog._status_label.text() == "AI không trả về JSON hợp lệ."
        assert dialog._cards["short"]["frame"].isVisible() is False
        assert controller.analyze_calls == [("pair", "EUR/USD")]

    def test_worker_exception_shows_the_message(self):
        controller = FakeAiController(_preview())
        controller.analyze_error = RuntimeError("Không kết nối được AI API: boom")
        dialog = _dialog(controller)

        dialog._analyze_button.click()
        assert _wait_until(lambda: dialog._analyze_button.isEnabled())
        assert dialog._status_label.text() == "Không kết nối được AI API: boom"


class TestAiDialogHistory:
    def test_history_lists_verdicts_with_registered_labels(self):
        history = [
            _verdict(VerdictHorizon.LONG, created_at="2026-09-23T09:00:00Z", direction=VerdictDirection.NEUTRAL),
            _verdict(VerdictHorizon.SHORT, created_at="2026-09-22T09:00:00Z"),
        ]
        controller = FakeAiController(_preview(), history=history)
        dialog = _dialog(controller)

        assert controller.history_calls == [("pair", "EUR/USD", news.AI_HISTORY_LIMIT)]
        texts = [label.text() for label in dialog._history_layout.parent().findChildren(QLabel)]
        assert any("23/09/2026 09:00" in t and "Dài hạn" in t and "Trung lập" in t for t in texts)
        assert any("22/09/2026 09:00" in t and "Ngắn hạn" in t and "Tăng" in t for t in texts)

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


# ---------------------------------------------------------------------------
# 3. Ranh giới mạng của dialog — màn không gọi thẳng producer/network
# ---------------------------------------------------------------------------


def test_ai_dialog_issue_no_direct_services_import_in_screen_source():
    source = Path(news.__file__).read_text(encoding="utf-8")
    for forbidden in ("import requests", "import urllib", "import socket", "from services."):
        assert forbidden not in source, forbidden