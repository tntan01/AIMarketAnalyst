"""Task 49 tests for causal supply/demand departure confirmation."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    confirm_supply_demand_candidate,
    detect_supply_demand_candidates,
)


def _candles(rows):
    start = datetime(2026, 9, 11, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def _buy_candidate():
    candles = _candles([
        (100, 100.4, 99.8, 100.1),
        (100.1, 100.5, 99.9, 100.2),
        (100.2, 100.3, 99.9, 100.0),
        (100.0, 102.0, 100.0, 101.8),
    ])
    candidate = detect_supply_demand_candidates(
        candles,
        symbol="EUR/USD",
        timeframe="H1",
        average_range_before_departure={3: 0.6},
    )[0]
    return candidate, candles


def test_departure_close_body_and_efficiency_confirm_demand():
    candidate, candles = _buy_candidate()
    result = confirm_supply_demand_candidate(
        candidate,
        candles,
        timeframe="H1",
        atr_before_event=2.0,
    )

    assert result["lifecycle_status"] == "confirmed"
    assert result["candidate"] is False
    assert result["entry_eligible"] is False
    assert result["confirmation_source"] == "departure"
    assert result["confirmation_event_id"] is None
    assert result["confirmed_at"] == "2026-09-11T04:00:00+00:00"
    assert result["available_at"] == result["confirmed_at"]
    assert result["departure_efficiency"] > 1.5
    assert "ZONE_CONFIRMED" in result["reason_codes"]


def test_close_inside_base_or_wick_only_stays_unconfirmed():
    candidate, candles = _buy_candidate()
    inside = list(candles)
    inside[3] = Candle(
        time=inside[3].time,
        open=100.0,
        high=102.0,
        low=99.8,
        close=100.2,
        volume=100,
    )
    result = confirm_supply_demand_candidate(
        candidate,
        inside,
        timeframe="H1",
        atr_before_event=2.0,
    )
    assert result["lifecycle_status"] == "candidate"
    assert "SD_CLOSE_NOT_OUTSIDE_BASE" in result["reason_codes"]

    wick = list(candles)
    wick[3] = Candle(
        time=wick[3].time,
        open=100.0,
        high=102.0,
        low=100.0,
        close=100.1,
        volume=100,
    )
    result = confirm_supply_demand_candidate(
        candidate,
        wick,
        timeframe="H1",
        atr_before_event=2.0,
    )
    assert result["lifecycle_status"] == "candidate"
    assert "SD_DEPARTURE_WICK_ONLY" in result["reason_codes"]


def test_missing_atr_does_not_get_replaced_and_base_measurement_stays_stable():
    candidate, candles = _buy_candidate()
    result = confirm_supply_demand_candidate(
        candidate,
        candles + _candles([(102, 103, 101, 102)])[0:1],
        timeframe="H1",
        atr_before_event=None,
    )
    assert result["lifecycle_status"] == "candidate"
    assert "SD_DEPARTURE_ATR_UNAVAILABLE" in result["reason_codes"]
    assert result["base_measurement"] == candidate["base_measurement"]
