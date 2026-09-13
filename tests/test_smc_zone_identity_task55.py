"""Task 55 tests for stable zone identity and setup deduplication."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    detect_fvg_candidates,
    detect_order_block_candidates,
    group_smc_zones_into_setups,
)


def _candles(rows, *, start=None):
    start = start or datetime(2026, 9, 9, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(hours=index),
            open=open_, high=high, low=low, close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def test_adding_later_candles_does_not_change_existing_ob_or_fvg_identity():
    ob_candles = _candles([
        (100, 101, 99, 100),
        (101, 102, 99, 100),
        (100, 104, 100, 103),
    ])
    ob_initial = detect_order_block_candidates(
        ob_candles, symbol="EUR/USD", timeframe="H1",
    )
    ob_extended = detect_order_block_candidates(
        ob_candles + _candles(
            [(103, 105, 102, 104)],
            start=ob_candles[-1].time + timedelta(hours=1),
        )[0:1],
        symbol="EUR/USD", timeframe="H1",
    )
    initial_ob = next(item for item in ob_initial if item["direction"] == "buy")
    extended_ob = next(item for item in ob_extended if item["zone_id"] == initial_ob["zone_id"])
    assert extended_ob["zone_id"] == initial_ob["zone_id"]
    assert extended_ob["original_bounds"] == initial_ob["original_bounds"]
    assert extended_ob["formation_start"] == initial_ob["formation_start"]
    assert extended_ob["formation_end"] == initial_ob["formation_end"]

    fvg_candles = _candles([
        (100, 100, 99, 99.5),
        (100, 103, 99.5, 102.5),
        (102, 104, 101, 103),
    ])
    fvg_initial = detect_fvg_candidates(
        fvg_candles, symbol="EUR/USD", timeframe="H1",
        tick_size=0.1, atr_before_event=5.0,
    )[0]
    fvg_extended = detect_fvg_candidates(
        fvg_candles + _candles(
            [(103, 104, 102, 103.5)],
            start=fvg_candles[-1].time + timedelta(hours=1),
        )[0:1],
        symbol="EUR/USD", timeframe="H1",
        tick_size=0.1, atr_before_event=5.0,
    )
    same_fvg = next(item for item in fvg_extended if item["zone_id"] == fvg_initial["zone_id"])
    assert same_fvg["original_bounds"] == fvg_initial["original_bounds"]
    assert same_fvg["formation_start"] == fvg_initial["formation_start"]
    assert same_fvg["formation_end"] == fvg_initial["formation_end"]


def test_candidate_permutation_does_not_change_setup_count_or_identity():
    zones = [
        {"zone_id": "ob-1", "family": "ob", "direction": "buy", "departure_end": "event-1", "snapshot_id": "s1", "low": 99, "high": 101},
        {"zone_id": "fvg-1", "family": "fvg", "direction": "buy", "departure_end": "event-1", "snapshot_id": "s1", "low": 100, "high": 101},
        {"zone_id": "sd-1", "family": "supply_demand", "direction": "buy", "departure_end": "event-1", "snapshot_id": "s1", "low": 98, "high": 100},
    ]
    forward = group_smc_zones_into_setups(zones, symbol="EUR/USD", timeframe="H4")
    reverse = group_smc_zones_into_setups(list(reversed(zones)), symbol="EUR/USD", timeframe="H4")

    assert list(forward) == list(reverse)
    assert {zone["zone_id"] for zone in next(iter(forward.values()))} == {
        "ob-1", "fvg-1", "sd-1"
    }


def test_duplicate_family_children_keep_distinct_zone_ids_but_one_setup():
    zones = [
        {"zone_id": "ob-1", "family": "ob", "direction": "buy", "departure_end": "event-1", "snapshot_id": "s1", "low": 99, "high": 101, "original_bounds": {"low": 99, "high": 101}},
        {"zone_id": "ob-2", "family": "ob", "direction": "buy", "departure_end": "event-1", "snapshot_id": "s1", "low": 99.5, "high": 100.5, "original_bounds": {"low": 99.5, "high": 100.5}},
    ]
    grouped = group_smc_zones_into_setups(zones, symbol="EUR/USD", timeframe="H4")
    assert len(grouped) == 1
    children = next(iter(grouped.values()))
    assert {zone["zone_id"] for zone in children} == {"ob-1", "ob-2"}
    assert {tuple(zone["original_bounds"].values()) for zone in children} == {
        (99, 101),
        (99.5, 100.5),
    }
