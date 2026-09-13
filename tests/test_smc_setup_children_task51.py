"""Task 51 tests for setup child zones and per-child evidence."""

import pytest

from core.smc_models import SmcSetup, SmcSetupChild


def _zones():
    return [
        {
            "zone_id": "ob-1",
            "family": "ob",
            "direction": "buy",
            "original_bounds": {"low": 99.0, "high": 101.0},
            "evidence": {"body_atr": 1.2, "source": "departure-1"},
            "reason_codes": ["ZONE_CANDIDATE"],
        },
        {
            "zone_id": "fvg-1",
            "family": "fvg",
            "direction": "buy",
            "original_bounds": {"low": 100.0, "high": 100.5},
            "evidence": {"gap_width": 0.5, "source": "departure-1"},
            "reason_codes": ["ZONE_CONFIRMED"],
        },
    ]


def test_setup_from_zones_keeps_each_child_bounds_and_evidence():
    setup = SmcSetup.from_zones(
        _zones(),
        setup_id="smcs-1",
        symbol="EUR/USD",
        timeframe="H4",
        direction="buy",
        departure_source="departure-1",
    )

    assert setup.child_zone_ids == ("ob-1", "fvg-1")
    assert setup.children[0].original_bounds == {"low": 99.0, "high": 101.0}
    assert setup.children[1].original_bounds == {"low": 100.0, "high": 100.5}
    assert setup.children[0].evidence["body_atr"] == 1.2
    assert setup.children[1].evidence["gap_width"] == 0.5
    assert SmcSetup.from_dict(setup.to_dict()) == setup


def test_child_bounds_are_not_unioned_and_child_ids_must_match():
    child = SmcSetupChild(
        zone_id="zone-1",
        family="ob",
        direction="buy",
        original_low=99.0,
        original_high=101.0,
        evidence={"body_atr": 1.0},
    )
    setup = SmcSetup(
        setup_id="smcs-1",
        symbol="EUR/USD",
        timeframe="H4",
        direction="buy",
        departure_source="departure-1",
        children=(child,),
    )
    assert setup.child_zone_ids == ("zone-1",)
    assert setup.children[0].original_bounds == {"low": 99.0, "high": 101.0}

    with pytest.raises(ValueError):
        SmcSetup(
            setup_id="smcs-1",
            symbol="EUR/USD",
            timeframe="H4",
            direction="buy",
            departure_source="departure-1",
            child_zone_ids=("different-zone",),
            children=(child,),
        )
