"""Task 58 contracts for starting SMC visits at the first eligible overlap."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle, candle_close_at
from core.smc_context import enrich_zones
from core.smc_lifecycle import analyze_zone_lifecycle


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


def _analyze(candles, **kwargs):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side="buy",
        origin_index=0,
        departure_end_index=1,
        zone_id="smcz-task58",
        timeframe="H1",
        tf_minutes=60,
        **kwargs,
    )


def test_departure_overlap_is_excluded_and_first_later_overlap_opens_visit():
    result = _analyze(_candles([
        (112, 114, 111, 113),
        (108, 112, 105, 111),  # departure overlaps
        (112, 114, 111, 113),  # outside
        (109, 111, 109, 110),  # first eligible overlap
    ]))

    assert result.first_retest_index == 3
    assert result.first_retest_time == candle_close_at(
        START + timedelta(hours=3), "H1"
    ).isoformat()
    assert result.visits[0].start_index == 3
    assert result.visits[0].visit_state == "open"


def test_available_at_blocks_overlap_until_zone_is_usable():
    candles = _candles([
        (112, 114, 111, 113),
        (108, 112, 105, 111),  # departure
        (109, 111, 109, 110),  # overlap before available_at
        (112, 114, 111, 113),  # outside before available_at
        (109, 111, 109, 110),  # first usable overlap
    ])
    available_at = candle_close_at(candles[4].time, "H1")
    result = _analyze(candles, available_at=available_at)

    assert result.first_retest_index == 4
    assert result.visits[0].entered_at == available_at.isoformat()


@pytest.mark.parametrize(
    "row",
    [
        (110, 111, 109, 110.5),  # low touches distal edge
        (100, 101, 99, 100.5),   # high touches proximal edge
    ],
)
def test_overlap_at_either_zone_boundary_opens_visit(row):
    result = _analyze(_candles([
        (112, 114, 111, 113),
        (112, 114, 111, 113),
        row,
    ]))

    assert result.first_retest_index == 2
    assert result.independent_retest_count == 1


def test_enrich_zones_passes_available_at_to_canonical_lifecycle():
    candles = _candles([
        (112, 114, 111, 113),
        (108, 112, 105, 111),
        (109, 111, 109, 110),  # blocked before availability
        (112, 114, 111, 113),
        (109, 111, 109, 110),  # accepted after availability
    ])
    zone = {
        "type": "demand_zone",
        "low": 100,
        "high": 110,
        "index": 0,
        "origin_index": 0,
        "time": candles[0].time.isoformat(),
        "origin_time": candles[0].time.isoformat(),
        "departure_end_index": 1,
        "available_at": candle_close_at(candles[4].time, "H1").isoformat(),
    }
    result = enrich_zones(
        [zone], candles, "demand", {}, {"status": "unknown"},
        tf_minutes=60, symbol="EUR/USD", timeframe="H1",
    )[0]

    assert result["first_retest_index"] == 4
    assert result["visits"][0]["start_index"] == 4


def test_available_at_must_be_timezone_aware():
    with pytest.raises(ValueError):
        _analyze(_candles([
            (112, 114, 111, 113),
            (112, 114, 111, 113),
            (109, 111, 109, 110),
        ]), available_at="2026-09-11T03:00:00")
