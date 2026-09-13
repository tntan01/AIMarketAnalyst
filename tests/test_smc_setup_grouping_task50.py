"""Task 50 tests for setup identity and child-zone grouping."""

from core.smc_context import (
    assign_setup_ids_to_zones,
    group_smc_zones_into_setups,
)


def _zone(zone_id, family, direction="buy", departure="2026-09-11T03:00:00+00:00", **extra):
    value = {
        "zone_id": zone_id,
        "family": family,
        "direction": direction,
        "low": 99.0,
        "high": 101.0,
        "departure_end": departure,
        "snapshot_id": "snapshot-1",
    }
    value.update(extra)
    return value


def test_same_departure_and_direction_share_setup_without_merging_children():
    zones = [
        _zone("ob-1", "ob"),
        _zone("fvg-1", "fvg", low=100.0, high=101.0),
        _zone("sd-1", "supply_demand", low=98.0, high=100.5),
    ]
    assigned = assign_setup_ids_to_zones(
        zones,
        symbol="EUR/USD",
        timeframe="H4",
    )
    setup_ids = {zone["setup_id"] for zone in assigned}

    assert len(setup_ids) == 1
    assert [zone["zone_id"] for zone in assigned] == ["ob-1", "fvg-1", "sd-1"]
    assert assigned[0]["low"] == 99.0
    assert assigned[1]["low"] == 100.0
    assert assigned[2]["high"] == 100.5

    grouped = group_smc_zones_into_setups(
        zones,
        symbol="EUR/USD",
        timeframe="H4",
    )
    assert list(grouped) == list(setup_ids)
    assert {zone["zone_id"] for zone in next(iter(grouped.values()))} == {
        "ob-1", "fvg-1", "sd-1"
    }


def test_overlap_or_opposite_direction_does_not_group():
    zones = [
        _zone("ob-a", "ob", departure="event-a"),
        _zone("fvg-b", "fvg", departure="event-b", low=99.5, high=100.5),
        _zone("sd-sell", "supply_demand", direction="sell", departure="event-a"),
    ]
    assigned = assign_setup_ids_to_zones(zones, symbol="EUR/USD", timeframe="H4")

    assert len({zone["setup_id"] for zone in assigned}) == 3


def test_missing_source_is_not_assigned_and_input_is_not_mutated():
    source = _zone("zone-1", "ob")
    source.pop("departure_end")
    source.pop("snapshot_id")
    assigned = assign_setup_ids_to_zones([source], symbol="EUR/USD", timeframe="H4")

    assert assigned[0]["setup_id"] is None
    assert "SETUP_SOURCE_MISSING" in assigned[0]["reason_codes"]
    assert "setup_id" not in source
