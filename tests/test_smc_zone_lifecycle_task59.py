"""Task 59 contracts for lifecycle visit exit tolerance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle, candle_close_at, validate_smc_candles
from core.smc_lifecycle import analyze_zone_lifecycle


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(rows):
    values = [
        Candle(
            time=START + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    issues = validate_smc_candles(values, "H1")
    assert not issues, f"task59 fixture must contain valid OHLC: {issues}"
    return values


def _lifecycle(candles, *, side="buy", **kwargs):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side=side,
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task59",
        timeframe="H1",
        tf_minutes=60,
        **kwargs,
    )


def test_inside_tolerance_does_not_close_visit():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 110),
        (111, 111.05, 110.01, 110.5),  # 0.01 outside raw edge, inside tolerance
    ]), tick_size=0.1, atr_current=2.0)

    assert result.independent_retest_count == 1
    assert result.visits[0].visit_state == "open"
    assert result.visits[0].exited_at is None


def test_outside_beyond_tolerance_closes_visit_and_reentry_starts_next_visit():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 110),
        (112, 114, 110.2, 110.2),  # outside above high + 0.1, no reaction displacement
        (105, 111, 105, 110),
    ]), tick_size=0.1, atr_current=2.0)

    assert result.independent_retest_count == 2
    assert result.visits[0].visit_state == "completed_unreacted"
    assert result.visits[0].end_index == 2
    assert result.visits[1].visit_state == "open"
    assert result.visits[1].start_index == 4


def test_tolerance_is_symmetric_for_sell():
    result = _lifecycle(_candles([
        (88, 89, 86, 87),
        (88, 89, 86, 87),
        (101, 105, 99, 100),
        (98.95, 99.99, 98, 99),  # 0.01 below raw low, inside tolerance
    ]), side="sell", tick_size=0.1, atr_current=2.0)

    assert result.independent_retest_count == 1
    assert result.visits[0].visit_state == "open"


def test_exit_timestamp_is_close_of_last_inside_boundary():
    candles = _candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 110),
        (112, 114, 111.2, 112),
    ])
    result = _lifecycle(candles, zone_tolerance=0.1)

    assert result.visits[0].exited_at == candle_close_at(
        candles[3].time, "H1"
    ).isoformat()


def test_invalid_tolerance_metadata_is_rejected():
    candles = _candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 110),
    ])
    with pytest.raises(ValueError):
        _lifecycle(candles, tick_size=0, atr_current=2.0)
    with pytest.raises(ValueError):
        _lifecycle(candles, zone_tolerance=-0.1)
