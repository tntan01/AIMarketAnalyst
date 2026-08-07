"""Test Bước 5 — nối dây SHADOW (Prompt 2).

Xác nhận: NewsService đánh giá sự kiện trong preload (lỗi thì bỏ qua, không
phá preload), data_quality_flags trả field mới lọc đúng currency, pipeline đưa
assessment vào result["macro"]["event_assessments"] nhưng KHÔNG đổi
macro_confidence (chưa derate). Mock toàn bộ, không network.
"""

from __future__ import annotations

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


def _seed_assessor_cache(svc: NewsService, rows: list[tuple[str, float]]) -> None:
    """Gieo trực tiếp assessment vào cache của assessor (không gọi AI)."""
    cache = svc._event_assessor.cache
    for currency, hours_until in rows:
        payload = _assessment_payload(currency, hours_until)
        event = {"currency": currency, "event": "FOMC Meeting", "impact": "high"}
        cache.put(
            make_event_key(event),
            "test-fp",
            EventImpactAssessment(**payload),
            T0,
        )


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


def test_preload_ai_event_assessment_ghi_journal_moi_ai():
    """Assessment source='ai' được ghi journal (data/event_assessment_journal.jsonl)."""
    svc = NewsService()
    svc._event_assessor = _BrokenAssessor()  # thay bằng stub ghi journal thật qua preload
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
            return [
                EventImpactAssessment(
                    event_key=make_event_key(events_[0]),
                    currency="USD",
                    event_name="FOMC Meeting",
                    time_utc="2026-08-08T12:00:00Z",
                    hours_until=20.0,
                    magnitude="high",
                    priced_in="not_priced_in",
                    expected_direction="currency_up",
                    risk_window_hours=12.0,
                    ai_confidence=0.8,
                    evidence=["forecast lệch"],
                    source="ai",
                )
            ]

    with patch.object(svc, "_get_global_macro_snapshot", return_value=_fake_snapshot()), patch.object(
        svc, "latest_macro_context", return_value={}
    ), patch.object(
        svc, "_journal_event_assessment", side_effect=lambda a: captured.append(
            {
                "event_key": a.event_key,
                "source": a.source,
                "currency": a.currency,
                "priced_in": a.priced_in,
            }
        )
    ):
        svc._event_assessor = _GoodAssessor()
        svc.preload_macro_contexts(["EUR/USD"])
    assert captured, "assessment source='ai' phải được ghi journal"
    assert captured[0]["source"] == "ai"


# ---------------------------------------------------------------------------
# 2. data_quality_flags — field mới lọc đúng currency, field cũ giữ nguyên
# ---------------------------------------------------------------------------

def test_data_quality_flags_them_field_moi_loc_dung_currency():
    """data_quality_flags trả field mới chỉ chứa assessment thuộc cặp."""
    svc = NewsService()
    _seed_assessor_cache(svc, [("USD", 6.0), ("EUR", 20.0), ("JPY", 10.0)])
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