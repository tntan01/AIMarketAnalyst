"""Task 41 tests for canonical zone/setup identities and immutable bounds."""

from __future__ import annotations

import pytest

from core.smc_models import SmcSetup, SmcZone, build_setup_id, build_zone_id


def _zone(**overrides):
    payload = {
        "type": "bullish_order_block",
        "symbol": "EUR/USD",
        "timeframe": "H4",
        "family": "ob",
        "direction": "buy",
        "low": 99.0,
        "high": 101.0,
        "origin_index": 12,
        "origin_time": "2026-09-10T08:00:00+00:00",
        "formation_start": "2026-09-10T04:00:00+00:00",
        "formation_end": "2026-09-10T08:00:00+00:00",
        "departure_end": "2026-09-10T12:00:00+00:00",
        "confirmation_event_id": "bos-h4-1",
        "confirmed_at": "2026-09-10T16:00:00+00:00",
        "available_at": "2026-09-10T16:00:00+00:00",
        "lifecycle_status": "confirmed",
        "reason_codes": ["ZONE_CONFIRMED"],
    }
    payload.update(overrides)
    return SmcZone.from_dict(payload)


def test_zone_preserves_original_bounds_when_current_bounds_are_refined():
    zone = _zone(
        low=99.5,
        high=100.5,
        original_bounds={"low": 99.0, "high": 101.0},
        refined_bounds={"low": 99.5, "high": 100.5},
    )

    assert zone.original_bounds == {"low": 99.0, "high": 101.0}
    assert zone.refined_bounds == {"low": 99.5, "high": 100.5}
    assert zone.to_dict()["original_bounds"] == {"low": 99.0, "high": 101.0}
    assert zone.zone_id == build_zone_id(
        symbol="EUR/USD",
        timeframe="H4",
        family="ob",
        direction="buy",
        origin_time="2026-09-10T08:00:00+00:00",
        low=99.0,
        high=101.0,
    )


def test_zone_round_trip_keeps_setup_and_availability_contract():
    zone = _zone()
    restored = SmcZone.from_dict(zone.to_dict())

    assert restored == zone
    assert zone.setup_id == build_setup_id(
        symbol="EUR/USD",
        timeframe="H4",
        direction="buy",
        departure_source="bos-h4-1",
    )
    assert zone.available_at == zone.confirmed_at
    assert zone.to_dict()["setup_id"] == zone.setup_id


def test_setup_round_trip_has_unique_child_zone_ids():
    setup = SmcSetup(
        setup_id="smcs-example",
        symbol="EUR/USD",
        timeframe="H4",
        direction="buy",
        departure_source="bos-h4-1",
        child_zone_ids=("zone-ob", "zone-fvg"),
        status="confirmed",
        available_at="2026-09-10T16:00:00+00:00",
        reason_codes=("ZONE_CONFIRMED",),
    )

    assert SmcSetup.from_dict(setup.to_dict()) == setup
    with pytest.raises(ValueError):
        SmcSetup(
            setup_id="smcs-example",
            symbol="EUR/USD",
            timeframe="H4",
            direction="buy",
            departure_source="bos-h4-1",
            child_zone_ids=("zone-ob", "zone-ob"),
        )


def test_zone_rejects_available_before_confirmation_and_outside_refinement():
    with pytest.raises(ValueError):
        _zone(available_at="2026-09-10T15:59:59+00:00")
    with pytest.raises(ValueError):
        _zone(refined_bounds={"low": 98.0, "high": 100.0})
