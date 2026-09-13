"""Task 65 lifecycle acceptance matrix across the completed lifecycle tasks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle, validate_smc_candles
from core.smc_lifecycle import analyze_zone_lifecycle, update_fvg_fill
from core.smc_models import ZoneVisit


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(rows, *, step_hours=1):
    values = [
        Candle(
            time=START + timedelta(hours=step_hours * index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    timeframe = "H4" if step_hours == 4 else "H1"
    issues = validate_smc_candles(values, timeframe)
    assert not issues, f"task65 fixture must contain valid OHLC: {issues}"
    return values


def _lifecycle(candles, **kwargs):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side="buy",
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task65",
        timeframe="H1",
        tf_minutes=60,
        **kwargs,
    )


def test_departure_is_excluded_and_first_overlap_is_an_open_visit():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (105, 111, 105, 108),  # departure overlap
        (112, 114, 111, 113),
        (109, 111, 108, 109),  # first eligible overlap
    ]))

    assert result.first_retest_index == 3
    assert result.bars_spent_inside == 1
    assert result.visits[0].visit_state == "open"


def test_long_dwell_counts_each_closed_overlap_candle_once():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        *[(105, 111, 105, 108)] * 6,
    ]))

    assert result.bars_spent_inside == 6
    assert result.visits[0].bars_spent_inside == 6
    assert result.dwell_bars == 6
    assert result.visits[0].max_penetration_ratio == pytest.approx(0.5)


def test_boundary_jitter_inside_tolerance_does_not_create_extra_visit():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 108),
        (111, 112, 110.05, 110.2),  # inside high + 0.1 tolerance
        (112, 114, 110.2, 112),      # outside tolerance, closes visit
        (105, 111, 105, 108),
    ]), tick_size=0.1, atr_current=2.0)

    assert result.independent_retest_count == 2
    assert [visit.start_index for visit in result.visits] == [2, 5]
    assert result.visits[0].bars_spent_inside == 2


def test_fvg_partial_and_full_fill_remain_separate_from_zone_identity():
    partial = update_fvg_fill(
        {
            "zone_id": "smcz-task65-partial",
            "type": "bullish_fvg",
            "family": "fvg",
            "direction": "buy",
            "low": 100,
            "high": 110,
            "original_bounds": {"low": 100, "high": 110},
            "origin_index": 2,
        },
        _candles([
            (100, 101, 99, 100),
            (100, 103, 99.5, 102),
            (102, 112, 102, 110),
            (110, 111, 105, 108),
        ]),
        tick_size=0.1,
        timeframe="H1",
    )
    full = update_fvg_fill(
        {**partial, "zone_id": "smcz-task65-full"},
        _candles([
            (100, 101, 99, 100),
            (100, 103, 99.5, 102),
            (102, 112, 102, 110),
            (110, 111, 99, 100),
        ]),
        tick_size=0.1,
        timeframe="H1",
    )

    assert partial["fill_status"] == "partially_filled"
    assert partial["fill_ratio"] == pytest.approx(0.5)
    assert full["fill_status"] == "filled"
    assert full["fill_ratio"] == 1.0
    assert full["original_bounds"] == {"low": 100, "high": 110}
    assert full["zone_id"] == "smcz-task65-full"


def test_invalidation_uses_close_buffer_and_preserves_penetration_visit():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 108),
        (99, 100, 98, 99.89),
    ]), tick_size=0.1, atr_current=2.0)

    assert result.lifecycle_broken is True
    assert result.invalidation_buffer == pytest.approx(0.1)
    assert result.visits[0].visit_state == "closed_by_invalidation"
    assert result.visits[0].bars_spent_inside == 2


def test_age_expiry_is_terminal_but_keeps_prior_visit_history():
    rows = [(112, 114, 111, 113)] * 32
    rows[2] = (105, 111, 105, 108)
    candles = _candles(rows, step_hours=4)
    result = analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side="buy",
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task65-age",
        timeframe="H4",
        tf_minutes=240,
    )

    assert result.lifecycle_expired is True
    assert result.expiry_index == 31
    assert result.visits[0].start_index == 2
    assert result.age_score == 0.0


def test_visit_and_lifecycle_round_trip_are_deterministic():
    candles = _candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (105, 111, 105, 108),
    ])
    first = _lifecycle(candles)
    second = _lifecycle(list(candles))
    visit = first.visits[0]

    assert first.to_dict() == second.to_dict()
    assert ZoneVisit.from_dict(visit.to_dict()) == visit
    assert visit.visit_id == "smcz-task65:visit-1"
