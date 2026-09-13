"""Task 62 contracts for directional FVG partial/full fill."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle, validate_smc_candles
from core.smc_context import enrich_zones
from core.smc_lifecycle import update_fvg_fill
from core.smc_models import SmcZone


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
    assert not issues, f"task62 fixture must contain valid OHLC: {issues}"
    return values


def _zone(*, direction="buy"):
    return {
        "zone_id": "smcz-task62",
        "type": "bullish_fvg" if direction == "buy" else "bearish_fvg",
        "zone_type": "bullish_fvg" if direction == "buy" else "bearish_fvg",
        "family": "fvg",
        "direction": direction,
        "low": 100.0,
        "high": 110.0,
        "original_bounds": {"low": 100.0, "high": 110.0},
        "origin_index": 2,
        "formation_end_index": 2,
    }


def test_bullish_partial_fill_uses_lowest_post_formation_low():
    candles = _candles([
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (102, 112, 102, 110),
        (110, 111, 105, 108),
        (108, 109, 107, 108),
    ])

    result = update_fvg_fill(_zone(), candles, tick_size=0.1, timeframe="H1")

    assert result["original_bounds"] == {"low": 100.0, "high": 110.0}
    assert result["remaining_bounds"] == {"low": 100.0, "high": 105.0}
    assert result["fill_status"] == "partially_filled"
    assert result["fill_ratio"] == pytest.approx(0.5)
    assert result["zone_id"] == "smcz-task62"


def test_bearish_partial_fill_is_symmetric():
    candles = _candles([
        (100, 105, 99, 100),
        (100, 103, 98, 99),
        (98, 99, 90, 92),
        (102, 105, 101, 103),
        (103, 104, 102, 103),
    ])

    result = update_fvg_fill(_zone(direction="sell"), candles, tick_size=0.1, timeframe="H1")

    assert result["remaining_bounds"] == {"low": 105.0, "high": 110.0}
    assert result["fill_status"] == "partially_filled"
    assert result["fill_ratio"] == pytest.approx(0.5)


@pytest.mark.parametrize(
    "direction, rows, expected_remaining",
    [
        (
            "buy",
            [
                (100, 101, 99, 100),
                (100, 102, 99, 101),
                (102, 112, 102, 110),
                (110, 111, 99, 100),
            ],
            {"low": 100.0, "high": 100.0},
        ),
        (
            "sell",
            [
                (100, 105, 99, 100),
                (100, 103, 98, 99),
                (98, 99, 90, 92),
                (109, 111, 108, 110),
            ],
            {"low": 110.0, "high": 110.0},
        ),
    ],
)
def test_full_fill_sets_filled_without_changing_identity(
    direction,
    rows,
    expected_remaining,
):
    zone = _zone(direction=direction)
    result = update_fvg_fill(
        zone,
        _candles(rows),
        tick_size=0.1,
        timeframe="H1",
    )

    assert result["fill_status"] == "filled"
    assert result["fill_ratio"] == 1.0
    assert result["remaining_bounds"] == expected_remaining
    assert result["zone_id"] == zone["zone_id"]
    assert result["original_bounds"] == zone["original_bounds"]
    assert result["low"] == zone["low"]
    assert result["high"] == zone["high"]


def test_remaining_width_within_full_fill_tolerance_is_filled():
    result = update_fvg_fill(
        _zone(),
        _candles([
            (100, 101, 99, 100),
            (100, 102, 99, 101),
            (102, 112, 102, 110),
            (110, 111, 100.4, 101),
        ]),
        tick_size=0.1,
        timeframe="H1",
    )

    assert result["remaining_bounds"] == {"low": 100.0, "high": 100.4}
    assert result["full_fill_tolerance"] == pytest.approx(0.5)
    assert result["fill_status"] == "filled"
    assert result["fill_ratio"] == 1.0


def test_enrich_zones_integrates_fvg_fill_without_replacing_zone_bounds():
    candles = _candles([
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (102, 112, 102, 110),
        (110, 111, 105, 108),
    ])
    zone = _zone()
    result = enrich_zones(
        [zone], candles, "fvg", {}, {"status": "unknown"},
        tf_minutes=60, timeframe="H1", tick_size=0.1,
    )[0]

    assert result["fill_status"] == "partially_filled"
    assert result["fill_ratio"] == pytest.approx(0.5)
    assert result["original_bounds"] == {"low": 100.0, "high": 110.0}
    assert result["low"] == 100.0
    assert result["high"] == 110.0


def test_typed_fvg_round_trip_accepts_zero_width_full_fill():
    zone = SmcZone.from_dict({
        **_zone(),
        "remaining_bounds": {"low": 100.0, "high": 100.0},
        "fill_status": "filled",
        "fill_ratio": 1.0,
    })

    restored = SmcZone.from_dict(zone.to_dict())
    assert zone.fill_status == "filled"
    assert zone.fill_ratio == 1.0
    assert zone.remaining_bounds == {"low": 100.0, "high": 100.0}
    assert restored == zone
