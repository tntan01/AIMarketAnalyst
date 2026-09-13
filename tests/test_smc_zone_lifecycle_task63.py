"""Task 63 contracts for buffered lifecycle invalidation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle, validate_smc_candles
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
    assert not issues, f"task63 fixture must contain valid OHLC: {issues}"
    return values


def _lifecycle(candles, *, side="buy", **kwargs):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side=side,
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task63",
        timeframe="H1",
        tf_minutes=60,
        tick_size=0.1,
        atr_current=2.0,
        **kwargs,
    )


def _buy_rows(close):
    return [
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 108),
        (99, 100, 98, close),
    ]


def test_break_buffer_uses_max_tick_and_atr_fraction():
    result = _lifecycle(_candles(_buy_rows(99.89)))

    assert result.invalidation_buffer == 0.1
    assert result.lifecycle_broken is True
    assert result.invalidation_index == 3
    assert result.visits[0].visit_state == "closed_by_invalidation"


def test_close_at_buffer_boundary_does_not_invalidate():
    result = _lifecycle(_candles(_buy_rows(99.9)))

    assert result.invalidation_buffer == 0.1
    assert result.lifecycle_broken is False
    assert result.invalidation_index is None
    assert result.visits[0].visit_state == "open"


def test_sell_invalidation_is_symmetric_and_uses_close_not_wick():
    exact = _lifecycle(
        _candles([
            (88, 89, 86, 87),
            (88, 89, 86, 87),
            (101, 105, 99, 102),
            (110, 111, 109, 110.1),
        ]),
        side="sell",
    )
    wick_only = _lifecycle(
        _candles([
            (88, 89, 86, 87),
            (88, 89, 86, 87),
            (101, 105, 99, 102),
            (105, 111, 104.5, 109.5),
        ]),
        side="sell",
    )
    beyond = _lifecycle(
        _candles([
            (88, 89, 86, 87),
            (88, 89, 86, 87),
            (101, 105, 99, 102),
            (110.2, 111, 109, 110.11),
        ]),
        side="sell",
    )

    assert exact.lifecycle_broken is False
    assert wick_only.lifecycle_broken is False
    assert beyond.lifecycle_broken is True
    assert beyond.invalidation_index == 3


def test_explicit_break_buffer_is_used_without_widening_overlap_tolerance():
    result = analyze_zone_lifecycle(
        candles=_candles(_buy_rows(99.95)),
        low=100,
        high=110,
        side="buy",
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task63-explicit",
        timeframe="H1",
        break_buffer=0.1,
    )

    assert result.lifecycle_broken is False
    assert result.invalidation_buffer == 0.1


def test_invalidation_before_reaction_uses_buffered_boundary():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 108),
        (112, 113, 110.2, 110.2),
        (99, 100, 98, 99.89),
        (112, 113, 110.5, 110.5),
    ]))

    assert result.lifecycle_broken is True
    assert result.visits[0].reacted_at is None
