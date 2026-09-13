"""Task 52 tests for zone availability and lifetime history gates."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle, candle_close_at
from core.smc_context import apply_zone_availability


def _candles(count=70):
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(hours=index),
            open=100.0,
            high=101.0,
            low=99.0,
            close=100.5,
            volume=100,
        )
        for index in range(count)
    ]


def _zone(candles, *, status="confirmed", available_index=65, origin_index=60):
    available = candle_close_at(candles[available_index].time, "H1").isoformat()
    return {
        "zone_id": "zone-1",
        "family": "ob",
        "direction": "buy",
        "low": 99.0,
        "high": 101.0,
        "origin_time": candles[origin_index].time.isoformat(),
        "lifecycle_status": status,
        "confirmed_at": available,
        "available_at": available,
        "reason_codes": [],
    }


def test_confirmed_zone_becomes_usable_only_with_complete_lifetime_history():
    candles = _candles()
    result = apply_zone_availability(
        [_zone(candles)],
        candles,
        timeframe="H1",
        symbol="EUR/USD",
        as_of=candle_close_at(candles[-1].time, "H1"),
    )[0]

    assert result["availability_status"] == "usable"
    assert result["usable"] is True
    assert result["lifecycle_status"] == "usable"
    assert result["history_coverage"]["freshness_eligible"] is True


def test_candidate_or_future_available_zone_stays_waiting():
    candles = _candles()
    as_of = candle_close_at(candles[64].time, "H1")
    candidate = apply_zone_availability(
        [_zone(candles, status="candidate")],
        candles,
        timeframe="H1",
        symbol="EUR/USD",
        as_of=as_of,
    )[0]
    future = apply_zone_availability(
        [_zone(candles, available_index=69)],
        candles,
        timeframe="H1",
        symbol="EUR/USD",
        as_of=as_of,
    )[0]

    assert candidate["usable"] is False
    assert candidate["availability_status"] == "waiting_confirmation"
    assert future["usable"] is False
    assert future["availability_status"] == "waiting_availability"
    assert "ZONE_NOT_AVAILABLE_YET" in future["reason_codes"]


def test_uncovered_origin_or_short_history_is_data_unavailable():
    candles = _candles(20)
    zone = _zone(candles, origin_index=0, available_index=5)
    result = apply_zone_availability(
        [zone],
        candles,
        timeframe="H1",
        symbol="EUR/USD",
        as_of=candle_close_at(candles[-1].time, "H1"),
    )[0]
    missing_origin = {**zone, "origin_time": "2026-08-01T00:00:00+00:00"}
    missing_result = apply_zone_availability(
        [missing_origin],
        candles,
        timeframe="H1",
        symbol="EUR/USD",
        as_of=candle_close_at(candles[-1].time, "H1"),
    )[0]

    assert result["usable"] is False
    assert result["availability_status"] == "data_unavailable"
    assert "SMC_INSUFFICIENT_HISTORY" in result["reason_codes"]
    assert missing_result["usable"] is False
    assert "SMC_COVERAGE_GAP" in missing_result["reason_codes"]
