"""Task 53 tests for lifecycle-first history retention and output limits."""

from core.smc_context import (
    limit_zones_for_output,
    retain_zone_history_candidates,
)


def _zone(zone_id, index, status="confirmed", usable=True):
    return {
        "zone_id": zone_id,
        "origin_index": index,
        "origin_time": f"2026-09-11T{index:02d}:00:00+00:00",
        "lifecycle_status": status,
        "usable": usable,
        "family": "fvg",
        "low": float(index),
        "high": float(index) + 1.0,
    }


def test_all_candidates_are_retained_before_lifecycle():
    zones = [_zone(f"zone-{index}", index) for index in range(10)]
    retained = retain_zone_history_candidates(zones)
    assert len(retained) == 10
    assert [zone["zone_id"] for zone in retained] == [
        f"zone-{index}" for index in range(10)
    ]
    assert retained is not zones
    assert retained[0] is not zones[0]


def test_output_limit_is_separate_and_invalid_new_zone_does_not_displace_valid_old_zone():
    zones = [
        _zone("old-valid", 1, status="confirmed", usable=True),
        _zone("new-invalid", 99, status="invalid", usable=False),
        _zone("new-valid", 98, status="usable", usable=True),
    ]
    output = limit_zones_for_output(zones, family="fvg", limit=2)

    assert [zone["zone_id"] for zone in output] == ["new-valid", "old-valid"]
    assert len(zones) == 3


def test_default_limits_are_family_specific_and_sort_is_deterministic():
    zones = [_zone(f"zone-{index}", index) for index in range(8)]
    fvg_output = limit_zones_for_output(list(reversed(zones)), family="fvg")
    ob_output = limit_zones_for_output(list(reversed(zones)), family="ob")
    sd_output = limit_zones_for_output(
        list(reversed(zones)), family="supply_demand"
    )

    assert len(fvg_output) == 6
    assert len(ob_output) == 6
    assert len(sd_output) == 5
    assert fvg_output[0]["zone_id"] == "zone-7"
