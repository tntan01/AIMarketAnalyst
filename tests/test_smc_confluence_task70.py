"""Task 70 contracts for parent/child and canonical D1 reaction evidence."""

from __future__ import annotations

import pytest

from core.smc_confluence import (
    build_d1_reaction_evidence,
    build_parent_child_relation,
)


def _zone(zone_id: str, *, side: str = "buy", low: float = 100, high: float = 110) -> dict[str, object]:
    return {"zone_id": zone_id, "direction": side, "low": low, "high": high}


def _reacted_lifecycle(**overrides: object) -> dict[str, object]:
    result: dict[str, object] = {
        "visits": [
            {
                "visit_id": "d1-zone:visit-1",
                "visit_state": "completed_reacted",
                "reacted_at": "2026-09-11T10:00:00+00:00",
                "reaction_event_id": "reaction-1",
            }
        ],
        "age_bars": 5,
        "lifecycle_stale": False,
        "lifecycle_expired": False,
    }
    result.update(overrides)
    return result


def test_parent_child_containment_has_full_relation_score():
    result = build_parent_child_relation(
        _zone("parent", low=99, high=111),
        _zone("child", low=100, high=110),
        tick_size=0.1,
        atr_parent=2.0,
    )

    assert result["valid"] is True
    assert result["relation"] == "contained"
    assert result["score"] == 1.0


def test_parent_child_sell_direction_mirrors_buy():
    result = build_parent_child_relation(
        _zone("parent", side="sell", low=99, high=111),
        _zone("child", side="sell", low=100, high=110),
        tick_size=0.1,
        atr_parent=2.0,
    )

    assert result["valid"] is True
    assert result["direction"] == "sell"


def test_parent_child_fifty_percent_overlap_is_accepted_as_alternative():
    result = build_parent_child_relation(
        _zone("parent"),
        _zone("child", low=105, high=115),
        expansion_tolerance=0.1,
    )

    assert result["valid"] is True
    assert result["relation"] == "overlap"
    assert result["score"] == 0.75
    assert result["overlap_ratio"] == pytest.approx(0.5)


def test_parent_child_wrong_direction_is_rejected():
    result = build_parent_child_relation(
        _zone("parent", side="buy"),
        _zone("child", side="sell"),
        tick_size=0.1,
        atr_parent=2.0,
    )

    assert result["valid"] is False
    assert "PARENT_CHILD_DIRECTION_MISMATCH" in result["reason_codes"]


def test_parent_child_proximity_only_is_not_a_relation():
    result = build_parent_child_relation(
        _zone("parent", low=100, high=110),
        _zone("child", low=120, high=130),
        tick_size=0.1,
        atr_parent=2.0,
    )

    assert result["valid"] is False
    assert result["score"] == 0.0


def test_parent_child_missing_expansion_metadata_is_unknown():
    result = build_parent_child_relation(
        _zone("parent"),
        _zone("child", low=100, high=110),
    )

    assert result["relation"] == "unknown"
    assert "PARENT_CHILD_EXPANSION_UNAVAILABLE" in result["reason_codes"]


def test_d1_reaction_requires_canonical_completed_reacted_visit():
    result = build_d1_reaction_evidence(
        _zone("d1-zone"),
        _reacted_lifecycle(),
        as_of="2026-09-11T11:00:00+00:00",
    )

    assert result["valid"] is True
    assert result["score"] == 1.0
    assert result["source_visit_id"] == "d1-zone:visit-1"
    assert result["source_event_id"] == "reaction-1"


@pytest.mark.parametrize(
    "visit_state, lifecycle_overrides, expected_reason",
    [
        ("open", {}, "D1_REACTION_NOT_COMPLETED_REACTED"),
        ("completed_unreacted", {}, "D1_REACTION_NOT_COMPLETED_REACTED"),
        ("completed_reacted", {"lifecycle_stale": True}, "D1_REACTION_STALE"),
    ],
)
def test_d1_reaction_rejects_open_unreacted_or_stale(
    visit_state: str,
    lifecycle_overrides: dict[str, object],
    expected_reason: str,
):
    lifecycle = _reacted_lifecycle(**lifecycle_overrides)
    lifecycle["visits"] = [{
        "visit_id": "d1-zone:visit-1",
        "visit_state": visit_state,
        "reacted_at": (
            "2026-09-11T10:00:00+00:00"
            if visit_state == "completed_reacted" else None
        ),
    }]

    result = build_d1_reaction_evidence(_zone("d1-zone"), lifecycle)

    assert result["valid"] is False
    assert expected_reason in result["reason_codes"]


def test_d1_proximity_or_legacy_boolean_does_not_create_reaction():
    result = build_d1_reaction_evidence(
        {"zone_id": "d1-zone", "d1_reaction": True, "proximity": True},
        {"visits": [], "d1_reaction": True},
    )

    assert result["valid"] is False
    assert result["score"] == 0.0


def test_d1_reaction_after_cutoff_is_rejected():
    result = build_d1_reaction_evidence(
        _zone("d1-zone"),
        _reacted_lifecycle(),
        as_of="2026-09-11T09:59:59+00:00",
    )

    assert result["valid"] is False
    assert result["reason_codes"] == ["D1_REACTION_AFTER_CUTOFF"]
