"""Task 61 contracts for penetration and continuous visit dwell."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.smc_lifecycle import analyze_zone_lifecycle
from core.smc_models import ZoneVisit


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(rows):
    return [
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


def _lifecycle(candles, *, side="buy", **kwargs):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side=side,
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task61",
        timeframe="H1",
        tf_minutes=60,
        **kwargs,
    )


def test_visit_stores_continuous_dwell_and_total_is_separate():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (109, 112, 108, 109),
        (107, 109, 104, 106),
        (105, 108, 101, 104),
        (112, 114, 111, 113),
    ]))

    assert result.bars_spent_inside == 3
    assert result.dwell_bars == 3
    assert result.current_dwell_bars == 3
    assert result.visits[0].bars_spent_inside == 3
    assert result.visits[0].dwell_bars == 3
    assert result.visits[0].max_penetration_ratio == pytest.approx(0.9)


def test_reentry_resets_current_dwell_but_keeps_total_overlap_count():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (109, 112, 106, 108),
        (107, 109, 104, 106),
        (112, 114, 111, 113),
        (108, 111, 103, 106),
        (112, 114, 111, 113),
    ]))

    assert result.bars_spent_inside == 3
    assert [visit.bars_spent_inside for visit in result.visits] == [2, 1]
    assert result.dwell_bars == 1
    assert result.current_dwell_bars == 1


def test_open_visit_dwell_counts_closed_overlapping_candles_only():
    result = _lifecycle(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (109, 112, 108, 109),
        (107, 109, 104, 106),
    ]))

    assert result.visits[0].visit_state == "open"
    assert result.visits[0].bars_spent_inside == 2
    assert result.dwell_bars == 2
    assert result.bars_spent_inside == 2


def test_scan_frequency_does_not_change_dwell_result():
    candles = _candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        (109, 112, 108, 109),
        (107, 109, 104, 106),
        (112, 114, 111, 113),
    ])

    first = _lifecycle(candles)
    second = _lifecycle(list(candles))

    assert first.to_dict() == second.to_dict()
    assert first.visits[0].bars_spent_inside == 2


@pytest.mark.parametrize("value", [-1, True, 1.5, "bad"])
def test_visit_dwell_count_is_non_negative_integer(value):
    with pytest.raises(ValueError):
        ZoneVisit(
            visit_id="smcz-task61:visit-1",
            zone_id="smcz-task61",
            entered_at="2026-09-11T01:00:00+00:00",
            exited_at="2026-09-11T02:00:00+00:00",
            start_index=1,
            end_index=1,
            bars_spent_inside=value,
        )
