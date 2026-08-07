"""Test Bước 5 — nối dây SHADOW (Prompt 2).

Xác nhận: NewsService đánh giá sự kiện trong preload (lỗi thì bỏ qua, không
phá preload), data_quality_flags trả field mới lọc đúng currency, pipeline đưa
assessment vào result["macro"]["event_assessments"] nhưng KHÔNG đổi
macro_confidence (chưa derate). Mock toàn bộ, không network.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

from core.analysis_pipeline import AnalysisPipeline
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from services.event_impact_assessor import EventImpactAssessment, make_event_key
from services.news_service import NewsService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

T0 = datetime(2026, 8, 7, 9, 0, 0, tzinfo=UTC)


class _BrokenAssessor:
    """Stub assessor luôn ném exception — để test fail-closed của preload."""

    def assess_upcoming_events(self, *args, **kwargs):
        raise RuntimeError("AI down")


class _FrozenDatetime(datetime):
    """datetime đóng băng tại T0 — deterministic cho test phụ thuộc thời gian."""

    @classmethod
    def now(cls, tz=None):
        return cls(2026, 8, 7, 9, 0, 0, tzinfo=UTC)


def _fake_snapshot() -> Any:
    return type(
        "FakeSnapshot",
        (),
        {
            "calendar_payload": {
                "source": "test",
                "events": [
                    {
                        "currency": "USD",
                        "event": "FOMC Meeting",
                        "impact": "high",
                        "time_utc": "2026-08-08T12:00:00Z",
                        "hours_until": 20.0,
                        "forecast": "5.25%",
                        "previous": "5.00%",
                        "actual": "",
                    }
                ],
                "warning": "",
            },
            "global_headlines": ({"title": "Fed hikes rate sharply"},),
            "fetched_at_utc": T0,
            "expires_at_utc": T0 + timedelta(minutes=5),
        },
    )()


def _assessment_payload(
    currency: str,
    hours_until: float,
    *,
    magnitude: str = "high",
    priced_in: str = "not_priced_in",
    risk: float = 48.0,
) -> dict[str, Any]:
    """Tạo dict payload assessment (đúng schema EventImpactAssessment)."""
    assessment = EventImpactAssessment(
        event_key=f"ev-{currency}-{hours_until}",
        currency=currency,
        event_name="FOMC Meeting",
        time_utc=f"2026-08-08T{int(hours_until):02d}:00:00Z",
        hours_until=hours_until,
        magnitude=magnitude,
        priced_in=priced_in,
        expected_direction="currency_up",
        risk_window_hours=risk,
        ai_confidence=0.8,
        evidence=["forecast lệch lớn"],
        source="ai",
    )
    return asdict(assessment)


def _seed_last_assessments(
    svc: NewsService,
    rows: list[tuple[str, float]],
    *,
    at: datetime | None = None,
) -> None:
    """Gieo trực tiếp kết quả preload (self._last_event_assessments) — không gọi AI.

    Mặc định at = bây giờ để lọt qua freshness gate _preload_cache_ttl.
    """
    svc._last_event_assessments = [
        EventImpactAssessment(**_assessment_payload(currency, hours_until))
        for currency, hours_until in rows
    ]
    svc._last_event_assessments_at = at if at is not None else datetime.now(UTC)


def _snapshot_with_event(time_utc: str, hours_until: float) -> Any:
    """Snapshot với 1 event USD high-impact có time_utc/hours_until theo ý muốn."""
    return type(
        "FakeSnapshot",
        (),
        {
            "calendar_payload": {
                "source": "test",
                "events": [
                    {
                        "currency": "USD",
                        "event": "FOMC Meeting",
                        "impact": "high",
                        "time_utc": time_utc,
                        "hours_until": hours_until,
                        "forecast": "5.25%",
                        "previous": "5.00%",
                        "actual": "",
                    }
                ],
                "warning": "",
            },
            "global_headlines": ({"title": "Fed hikes rate sharply"},),
            "fetched_at_utc": T0,
            "expires_at_utc": T0 + timedelta(minutes=5),
        },
    )()


# ---------------------------------------------------------------------------
# Nến tổng hợp tối thiểu (đủ D1=120, H4=120, H1=60 cho pipeline chạy đủ route)
# ---------------------------------------------------------------------------

def _candles(n: int, *, bar_minutes: int, start: datetime, step: float = 0.0002) -> list[Candle]:
    result: list[Candle] = []
    price = 1.0800
    t = start
    for i in range(n):
        result.append(
            Candle(
                time=t,
                open=round(price, 5),
                high=round(price + 0.0008, 5),
                low=round(price - 0.0008, 5),
                close=round(price + step, 5),
                volume=float(1000 + i),
            )
        )
        price += step
        t += timedelta(minutes=bar_minutes)
    return result


def _candles_by_timeframe() -> dict[str, list[Candle]]:
    end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    return {
        "D1": _candles(120, bar_minutes=1440, start=end - timedelta(days=120)),
        "H4": _candles(120, bar_minutes=240, start=end - timedelta(days=20)),
        "H1": _candles(60, bar_minutes=60, start=end - timedelta(days=3)),
        "M15": _candles(60, bar_minutes=15, start=end - timedelta(hours=15)),
    }


def _default_input(symbol: str = "EUR/USD") -> AnalysisInput:
    return AnalysisInput(
        symbol=symbol,
        broker_symbol="EURUSDm",
        account_balance=10_000.0,
        risk_percent=2.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )


# ---------------------------------------------------------------------------
# 1. preload — assessor/AI lỗi không phá preload
# ---------------------------------------------------------------------------

def test_preload_assessor_loi_khong_pha_preload():
    """preload với assessor ném exception → preload hoàn tất bình thường."""
    svc = NewsService()
    svc._event_assessor = _BrokenAssessor()
    with patch.object(svc, "_get_global_macro_snapshot", return_value=_fake_snapshot()), patch.object(
        svc, "latest_macro_context", return_value={}
    ):
        svc.preload_macro_contexts(["EUR/USD", "GBP/USD"])
    # Không exception; preload đánh dấu xong.
    assert svc._preload_cache_time is not None
    # Fail-closed (Lỗi 2): không có kết quả khả dụng, không bom cache cũ.
    assert svc._last_event_assessments == []


def test_preload_ai_event_assessment_ghi_journal_moi_ai():
    """Assessment source='ai' được ghi journal (data/event_assessment_journal.jsonl)."""
    svc = NewsService()
    events = [
        {
            "currency": "USD",
            "event": "FOMC Meeting",
            "impact": "high",
            "time_utc": "2026-08-08T12:00:00Z",
            "hours_until": 20.0,
            "forecast": "5.25%",
            "previous": "5.00%",
            "actual": "",
        }
    ]
    # Gọi trực tiếp helper với assessor giả thành công (source='ai').
    captured: list[dict[str, Any]] = []

    class _GoodAssessor:
        def assess_upcoming_events(self, events_, ai_service, stance_lookup, headlines_by_currency, **kwargs):
            assessment = EventImpactAssessment(
                event_key=make_event_key(events_[0]),
                currency="USD",
                event_name="FOMC Meeting",
                time_utc="2026-08-08T12:00:00Z",
                hours_until=27.0,
                magnitude="high",
                priced_in="not_priced_in",
                expected_direction="currency_up",
                risk_window_hours=12.0,
                ai_confidence=0.8,
                evidence=["forecast lệch"],
                source="ai",
            )
            # Contract mới: (assessments, fresh_ai_keys) — key này vừa được
            # gọi AI thật nên phải nằm trong tập fresh để được ghi journal.
            return [assessment], {assessment.event_key}

    with patch.object(
        svc,
        "_journal_event_assessment",
        side_effect=lambda a: captured.append(
            {
                "event_key": a.event_key,
                "source": a.source,
                "currency": a.currency,
                "priced_in": a.priced_in,
            }
        ),
    ):
        svc._event_assessor = _GoodAssessor()
        svc._preload_event_impact_assessments(
            _fake_snapshot(),
            ai_service=None,
            performance_tracker=None,
            now=T0,  # deterministic: event 2026-08-08T12:00Z còn 27h tính từ T0
        )
    assert captured, "assessment source='ai' phải được ghi journal"
    assert captured[0]["source"] == "ai"


def test_preload_loc_event_da_qua_dua_tren_time_utc():
    """Bổ sung review: event có field hours_until trong cửa sổ (10.0) nhưng
    time_utc ĐÃ QUA → bị loại: không vào _last_event_assessments, không ghi journal."""
    svc = NewsService()
    snapshot = _snapshot_with_event(time_utc="2026-08-07T07:00:00Z", hours_until=10.0)
    journal_calls: list[Any] = []
    with patch("services.news_service.datetime", _FrozenDatetime):
        with patch.object(svc, "_journal_event_assessment", side_effect=lambda a: journal_calls.append(a)):
            svc._preload_event_impact_assessments(snapshot, ai_service=None, performance_tracker=None, now=T0)
        # T0 = 2026-08-07T09:00Z, time_utc = 07:00Z → hours_until = -2.0 → loại.
        assert svc._last_event_assessments == []
        assert journal_calls == []
        with patch.object(svc, "latest_macro_context", return_value={"events": [], "source": "test", "warning": ""}):
            flags = svc.data_quality_flags("EUR/USD")
        assert flags["upcoming_event_assessments"] == []


def test_preload_tinh_lai_hours_until_tu_time_utc():
    """Bổ sung review: event time_utc tương lai hợp lệ nhưng field hours_until
    sai (99.0) → assessment có hours_until tính lại đúng từ time_utc."""
    svc = NewsService()
    snapshot = _snapshot_with_event(time_utc="2026-08-07T15:00:00Z", hours_until=99.0)
    with patch("services.news_service.datetime", _FrozenDatetime):
        svc._preload_event_impact_assessments(snapshot, ai_service=None, performance_tracker=None, now=T0)
        # T0 = 09:00Z, time_utc = 15:00Z → hours_until = 6.0 (không còn 99.0).
        assert svc._last_event_assessments is not None
        assert len(svc._last_event_assessments) == 1
        assert abs(svc._last_event_assessments[0].hours_until - 6.0) < 1e-6
        with patch.object(svc, "latest_macro_context", return_value={"events": [], "source": "test", "warning": ""}):
            flags = svc.data_quality_flags("EUR/USD")
        upcoming = flags["upcoming_event_assessments"]
        assert len(upcoming) == 1
        assert abs(float(upcoming[0]["hours_until"]) - 6.0) < 1e-6


def test_preload_khong_derate_ma_cho_event_da_qua_cache_24h():
    """Bổ sung review — tái hiện đúng kịch bản PO: calendar cache fetch cách đây
    20h, lúc fetch event có hours_until=6.0 (time_utc = fetch+6h). Tới now (T0)
    sự kiện ĐÃ QUA 14h, nhưng field hours_until stale vẫn nói 6.0 (trong cửa sổ
    4-48). Nếu không tính lại từ time_utc → tạo assessment gây derate ma khi bật
    Prompt 4. Fix phải LOẠI event này."""
    svc = NewsService()
    # time_utc = T0 - 14h = 2026-08-06T19:00Z (đã qua); field hours_until stale = 6.0.
    snapshot = _snapshot_with_event(time_utc="2026-08-06T19:00:00Z", hours_until=6.0)
    journal_calls: list[Any] = []
    with patch("services.news_service.datetime", _FrozenDatetime):
        with patch.object(svc, "_journal_event_assessment", side_effect=lambda a: journal_calls.append(a)):
            svc._preload_event_impact_assessments(snapshot, ai_service=None, performance_tracker=None, now=T0)
        # hours_until tính lại = (06T19:00Z - 07T09:00Z)/3600 = -14.0 → loại.
        assert svc._last_event_assessments == []
        assert journal_calls == []
        with patch.object(svc, "latest_macro_context", return_value={"events": [], "source": "test", "warning": ""}):
            flags = svc.data_quality_flags("EUR/USD")
        assert flags["upcoming_event_assessments"] == []


def test_preload_step5_dau_ngay_van_co_boi_canh_stance():
    """Lỗi 4: hook Bước 5 phải chạy SAU vòng lặp per-symbol (nơi _macro_tier3
    gọi _ai_currency_stance đổ đầy _stance_cache). Nhờ vậy ngay chu kỳ preload
    đầu tiên trong ngày (cache stance còn trống), stance_lookup đã trả dữ liệu —
    không phải None (input quan trọng nhất cho priced_in)."""
    svc = NewsService()
    snapshot = _snapshot_with_event(time_utc="2026-08-08T12:00:00Z", hours_until=20.0)

    # Đúng cache key mà _make_stance_lookup sẽ đọc (currency + fingerprint AI).
    fp = NewsService._ai_fingerprint(None)
    stance_key = json.dumps(
        {"currency": "USD", "ai": fp},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )

    # Giả lập _macro_tier3: mỗi lần latest_macro_context chạy trong vòng lặp
    # per-symbol thì đổ đầy _stance_cache cho USD (mô phỏng _ai_currency_stance).
    def fake_latest_macro_context(symbol, **kwargs):
        svc._stance_cache[stance_key] = (
            {"stance": "hawkish", "strength": 7, "confidence": 0.8, "source": "ai"},
            T0,
        )
        return {}

    captured: dict[str, object] = {}

    class _CapturingAssessor:
        def assess_upcoming_events(self, events_, ai_service, stance_lookup, headlines_by_currency, **kwargs):
            captured["USD"] = stance_lookup("USD")
            return [], set()

    svc._event_assessor = _CapturingAssessor()
    with patch("services.news_service.datetime", _FrozenDatetime), patch.object(
        svc, "_get_global_macro_snapshot", return_value=snapshot
    ), patch.object(svc, "latest_macro_context", side_effect=fake_latest_macro_context):
        svc.preload_macro_contexts(["EUR/USD"], ai_service=None)

    # Nếu hook chạy TRƯỚC vòng lặp → _stance_cache trống → stance_lookup trả None.
    # Fix (hook chạy SAU vòng lặp) → cache đã đầy → stance_lookup trả dict stance.
    assert captured.get("USD") is not None, "stance_lookup phải có dữ liệu ngay chu kỳ preload đầu"
    assert captured["USD"]["stance"] == "hawkish"


# ---------------------------------------------------------------------------
# 2. data_quality_flags — field mới lọc đúng currency, field cũ giữ nguyên
# ---------------------------------------------------------------------------

def test_data_quality_flags_them_field_moi_loc_dung_currency():
    """data_quality_flags trả field mới chỉ chứa assessment thuộc cặp."""
    svc = NewsService()
    _seed_last_assessments(svc, [("USD", 6.0), ("EUR", 20.0), ("JPY", 10.0)])
    with patch.object(svc, "latest_macro_context", return_value={"events": [], "source": "test", "warning": ""}):
        flags = svc.data_quality_flags("EUR/USD")
    upcoming = flags["upcoming_event_assessments"]
    assert isinstance(upcoming, list)
    # JPY không thuộc EUR/USD → bị loại; USD trước EUR theo hours_until.
    assert [item["currency"] for item in upcoming] == ["USD", "EUR"]
    # Field cũ giữ nguyên, không đổi.
    assert "next_high_impact_event" in flags
    assert flags["news_in_3h"] is False
    assert flags["high_impact_event_within_30m"] is False
    assert flags["resume_after"] is None


def test_data_quality_flags_khong_co_cache_tra_rong():
    """Không có cache → field mới là list rỗng, không crash."""
    svc = NewsService()
    with patch.object(svc, "latest_macro_context", return_value={"events": [], "source": "test", "warning": ""}):
        flags = svc.data_quality_flags("EUR/USD")
    assert flags["upcoming_event_assessments"] == []


# ---------------------------------------------------------------------------
# 3. pipeline — payload có assessment, macro_confidence KHÔNG đổi (shadow)
# ---------------------------------------------------------------------------

def test_pipeline_event_assessments_co_payload_confidence_khong_doi():
    """Pipeline có assessments → event_assessments có payload; macro_confidence không đổi."""
    payload = _assessment_payload("USD", 20.0)
    candles = _candles_by_timeframe()

    with_assess = AnalysisPipeline().execute(
        _default_input(),
        candles,
        data_quality={"upcoming_event_assessments": [payload]},
        macro_confidence=0.8,
    )
    without_assess = AnalysisPipeline().execute(
        _default_input(),
        candles,
        data_quality={},
        macro_confidence=0.8,
    )

    event_assessments = with_assess["macro"]["event_assessments"]
    assert isinstance(event_assessments, list)
    assert len(event_assessments) == 1
    assert event_assessments[0]["currency"] == "USD"
    assert event_assessments[0]["hours_until"] == 20.0
    # SHADOW: macro_confidence và final_score KHÔNG đổi khi có assessments.
    assert with_assess["macro"]["macro_confidence"] == without_assess["macro"]["macro_confidence"]
    assert with_assess["final_score"] == without_assess["final_score"]


def test_pipeline_khong_co_field_event_assessments_rong():
    """data_quality không có field (fixture cũ) → không crash, payload rỗng."""
    result = AnalysisPipeline().execute(
        _default_input(),
        _candles_by_timeframe(),
        data_quality={"spread_status": "normal"},
        macro_confidence=0.8,
    )
    assert result["macro"]["event_assessments"] == []


def test_pipeline_event_ahead_assessment_duoc_gan_va_reason_code_none():
    """Bước 5 shadow: biến instance được gắn payload, reason code vẫn None (chưa bật)."""
    payload = _assessment_payload("USD", 20.0)
    pipeline = AnalysisPipeline()
    pipeline.execute(
        _default_input(),
        _candles_by_timeframe(),
        data_quality={"upcoming_event_assessments": [payload]},
        macro_confidence=0.8,
    )
    assert pipeline._macro_event_ahead_assessment is not None
    assert pipeline._macro_event_ahead_assessment["currency"] == "USD"
    assert pipeline._macro_event_ahead_reason_code is None