"""Task 57 contracts for typed SMC zone visits."""

from __future__ import annotations

import pytest

from core.smc_models import SmcZone, ZoneVisit


ZONE_ID = "smcz-task57-zone"
ENTERED = "2026-09-11T10:00:00+00:00"
EXITED = "2026-09-11T11:00:00+00:00"
REACTED = "2026-09-11T12:00:00+00:00"


def test_visit_id_is_stable_and_source_zone_is_explicit():
    assert ZoneVisit.build_id(ZONE_ID, 1) == f"{ZONE_ID}:visit-1"
    visit = ZoneVisit(
        visit_id=ZoneVisit.build_id(ZONE_ID, 1),
        zone_id=ZONE_ID,
        entered_at=ENTERED,
        exited_at=None,
        start_index=5,
        end_index=None,
    )
    assert visit.zone_id == ZONE_ID
    assert visit.visit_state == "open"
    assert visit.state == "open"


@pytest.mark.parametrize(
    ("visit_state", "exited_at", "reacted_at"),
    [
        ("completed_unreacted", EXITED, None),
        ("completed_reacted", EXITED, REACTED),
        ("closed_by_invalidation", EXITED, None),
    ],
)
def test_visit_states_require_their_causal_timestamps(visit_state, exited_at, reacted_at):
    visit = ZoneVisit(
        visit_id=ZoneVisit.build_id(ZONE_ID, 2),
        zone_id=ZONE_ID,
        entered_at=ENTERED,
        exited_at=exited_at,
        reacted_at=reacted_at,
        start_index=5,
        end_index=6,
        max_penetration_ratio=0.5,
        visit_state=visit_state,
    )
    assert visit.visit_state == visit_state
    assert ZoneVisit.from_dict(visit.to_dict()) == visit


def test_visit_evidence_survives_zone_round_trip():
    visit = ZoneVisit(
        visit_id=ZoneVisit.build_id(ZONE_ID, 1),
        zone_id=ZONE_ID,
        entered_at=ENTERED,
        exited_at=EXITED,
        reacted_at=REACTED,
        start_index=5,
        end_index=7,
        max_penetration_ratio=0.75,
        visit_state="completed_reacted",
    )
    zone = SmcZone.from_dict({
        "zone_id": ZONE_ID,
        "symbol": "EUR/USD",
        "timeframe": "H1",
        "family": "ob",
        "direction": "buy",
        "zone_type": "bullish_order_block",
        "low": 100,
        "high": 101,
        "origin_index": 3,
        "origin_time": "2026-09-11T08:00:00+00:00",
        "visits": [visit.to_dict()],
    })
    restored = SmcZone.from_dict(zone.to_dict())
    assert restored.visits == (visit,)
    assert restored.to_dict()["visits"][0]["zone_id"] == ZONE_ID
    assert restored.to_dict()["visits"][0]["reacted_at"] == REACTED


@pytest.mark.parametrize(
    "kwargs",
    [
        {"visit_state": "open", "exited_at": EXITED},
        {"visit_state": "completed_reacted", "exited_at": EXITED},
        {"visit_state": "completed_unreacted", "exited_at": EXITED, "reacted_at": REACTED},
        {"visit_state": "open", "reacted_at": REACTED},
        {"visit_state": "completed_unreacted", "exited_at": EXITED, "max_penetration_ratio": 1.1},
    ],
)
def test_visit_rejects_inconsistent_state_or_measurement(kwargs):
    with pytest.raises(ValueError):
        values = {
            "visit_id": ZoneVisit.build_id(ZONE_ID, 1),
            "zone_id": ZONE_ID,
            "entered_at": ENTERED,
            "exited_at": None,
            "start_index": 5,
            "end_index": 6,
        }
        values.update(kwargs)
        ZoneVisit(**values)


def test_legacy_visit_id_infers_source_zone_for_compatibility():
    visit = ZoneVisit.from_dict({
        "visit_id": f"{ZONE_ID}:visit-4",
        "entered_at": ENTERED,
        "exited_at": None,
        "start_index": 8,
        "end_index": None,
    })
    assert visit.zone_id == ZONE_ID
    assert visit.visit_state == "open"
