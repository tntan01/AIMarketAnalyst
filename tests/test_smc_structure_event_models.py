from dataclasses import replace

import pytest

from core.smc_models import SmcStructureEvent


def bos(**changes) -> SmcStructureEvent:
    values = {
        "event_id": "BOS-H4-1",
        "event_type": "BOS",
        "direction": "bullish",
        "source_level": 110.0,
        "occurred_at": "2026-01-05T12:00:00Z",
        "broken_level_id": "H1",
        "source_swing_id": "L1",
        "confirmed_at": "2026-01-05T12:00:00Z",
        "expires_at": "2026-02-01T00:00:00Z",
        "invalidated_at": None,
        "snapshot_id": "snapshot-1",
        "reason_codes": ("BOS_CONFIRMED",),
    }
    values.update(changes)
    return SmcStructureEvent(**values)


def test_bos_has_source_level_direction_and_causal_timestamps():
    event = bos()

    assert event.level == 110.0
    assert event.direction == "bullish"
    assert event.occurred_at == "2026-01-05T12:00:00+00:00"
    assert event.confirmed_at == event.occurred_at
    assert event.invalidated_at is None
    assert event.status == "confirmed"


def test_choch_candidate_has_no_confirmation_until_follow_through():
    candidate = SmcStructureEvent(
        event_id="CHOCH-C-1",
        event_type="CHOCH_CANDIDATE",
        direction="bearish",
        source_level=100.0,
        occurred_at="2026-01-09T00:00:00Z",
        broken_level_id="L1",
        protected_swing_id="L1",
        confirmed_at=None,
        expires_at="2026-01-12T00:00:00Z",
        snapshot_id="snapshot-2",
    )

    assert candidate.status == "candidate"
    assert candidate.confirmed_at is None


def test_confirmed_choch_requires_confirmation_and_can_be_invalidated():
    event = SmcStructureEvent(
        event_id="CHOCH-C-1",
        event_type="CHOCH_CONFIRMED",
        direction="bearish",
        source_level=97.0,
        occurred_at="2026-01-09T00:00:00Z",
        broken_level_id="L3",
        source_swing_id="H3",
        protected_swing_id="L1",
        confirmed_at="2026-01-13T12:00:00Z",
        invalidated_at="2026-01-15T00:00:00Z",
        snapshot_id="snapshot-3",
        reason_codes=("CHOCH_CONFIRMED",),
    )

    assert event.status == "invalidated"
    assert event.invalidated_at == "2026-01-15T00:00:00+00:00"


def test_structure_event_round_trips_with_references_and_reason_codes():
    original = bos()

    restored = SmcStructureEvent.from_dict(original.to_dict())

    assert restored == original
    assert restored.to_dict()["level"] == 110.0
    assert restored.to_dict()["status"] == "confirmed"


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"direction": "sideways"}, "Invalid SMC structure direction"),
        ({"event_type": "UNKNOWN"}, "Invalid SMC structure event type"),
        ({"source_level": float("nan")}, "source_level must be finite"),
        ({"occurred_at": "2026-01-05T12:00:00"}, "timezone-aware UTC"),
        ({"snapshot_id": ""}, "snapshot_id is required"),
    ],
)
def test_structure_event_rejects_invalid_core_fields(changes, message):
    with pytest.raises(ValueError, match=message):
        bos(**changes)


def test_structure_event_rejects_missing_source_reference():
    with pytest.raises(ValueError, match="source_swing_id or protected_swing_id"):
        bos(source_swing_id=None)


@pytest.mark.parametrize(
    "changes, message",
    [
        (
            {"confirmed_at": "2026-01-05T11:59:00Z"},
            "confirmed_at cannot precede occurred_at",
        ),
        (
            {"expires_at": "2026-01-05T11:59:00Z"},
            "expires_at cannot precede occurred_at",
        ),
        (
            {"invalidated_at": "2026-01-05T11:59:00Z"},
            "invalidated_at cannot precede occurred_at",
        ),
    ],
)
def test_structure_event_enforces_timestamp_order(changes, message):
    with pytest.raises(ValueError, match=message):
        bos(**changes)


def test_candidate_and_confirmed_event_semantics_are_fail_closed():
    with pytest.raises(ValueError, match="CHOCH_CANDIDATE cannot have confirmed_at"):
        SmcStructureEvent(
            event_id="candidate",
            event_type="CHOCH_CANDIDATE",
            direction="bullish",
            source_level=100,
            occurred_at="2026-01-01T00:00:00Z",
            broken_level_id="H1",
            protected_swing_id="H1",
            confirmed_at="2026-01-01T01:00:00Z",
            snapshot_id="snapshot",
        )

    with pytest.raises(ValueError, match="CHOCH_CONFIRMED requires confirmed_at"):
        SmcStructureEvent(
            event_id="confirmed",
            event_type="CHOCH_CONFIRMED",
            direction="bullish",
            source_level=100,
            occurred_at="2026-01-01T00:00:00Z",
            broken_level_id="H1",
            source_swing_id="L1",
            confirmed_at=None,
            snapshot_id="snapshot",
        )
