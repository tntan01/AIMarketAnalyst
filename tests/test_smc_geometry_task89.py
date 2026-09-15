"""Task 89 / R80-91-02 — one shared geometry gate for scorer and planner.

The planner must consume ``core.smc_geometry.pre_plan_geometry_gate`` for real:
the same candidate has to be rejected (or accepted) by both sides of the seam,
including when the zone carries ``original_bounds`` that differ from the
protective bounds the plan is anchored to.
"""

from __future__ import annotations

from fractions import Fraction
from math import isclose

from core.scanner_composition import ScenarioPlan
from core.scanner_scenario_producers import produce_scenario_plans_from_zones
from core.smc_geometry import (
    GEOMETRY_WIDTH_TOO_WIDE,
    HARD_DISTANCE_ATR,
    MAX_ZONE_WIDTH_ATR,
    pre_plan_geometry_gate,
)
from core.smc_quality import evaluate_candidate_sets

_AS_OF = "2026-02-10T00:00:00+00:00"
_PRICE = 99.5
_ATR = 2.0


def _zone(*, original_bounds, current=(99.0, 100.0)):
    return {
        "zone_id": "smcz-geom-1",
        "setup_id": "smcs-geom-1",
        "family": "ob",
        "direction": "buy",
        "type": "bullish_order_block",
        "lifecycle_status": "confirmed",
        "available_at": "2026-02-05T00:00:00+00:00",
        "original_bounds": {"low": original_bounds[0], "high": original_bounds[1]},
        "low": current[0],
        "high": current[1],
        # The planner's protective-zone contract requires the zone level.
        "level": (current[0] + current[1]) / 2,
        "tick_size": 0.1,
        "age_bars": 5,
        "age_score": 0.9,
        "confirmation_event_id": "smc-bos-geom-1",
        "departure_measurement": {
            "direction": "buy",
            "body_atr": 0.6,
            "body_range": 0.8,
            "directional_close_location": 0.86,
            "atr_before_event": _ATR,
            "status": "ok",
        },
        "visits": [
            {
                "visit_id": "smcz-geom-1:visit-1",
                "visit_state": "completed_reacted",
                "max_penetration_ratio": 0.25,
                "bars_spent_inside": 1,
            }
        ],
        "linked_sweep_id": None,
        "liquidity_sweep_linked": False,
    }


def _context(zone):
    return {
        "symbol": "EUR/USD",
        "D1": {
            "structure": "HH/HL",
            "bos": True,
            "displacement": "bullish",
            "demand_zones": [zone],
            "supply_zones": [],
            "order_blocks": [],
            "fvg": [],
            "zone_link_sweeps": {},
        },
        "H4": {
            "structure": "HH/HL",
            "bos": True,
            "displacement": "bullish",
            "demand_zones": [zone],
            "supply_zones": [],
            "order_blocks": [],
            "fvg": [],
            "zone_link_sweeps": {},
        },
        "H1": {
            "structure": "HH/HL",
            "bos": True,
            "displacement": "bullish",
            "demand_zones": [],
            "supply_zones": [],
            "order_blocks": [],
            "fvg": [],
            "zone_link_sweeps": {},
        },
        "confluence": {
            "timeframe_evidence": {
                "D1": {"direction": "buy"},
                "H4": {"direction": "buy"},
                "H1": {"direction": "buy"},
            }
        },
    }


def _technical():
    return {
        "price": _PRICE,
        "atr_h4": _ATR,
        "atr_d1": _ATR,
        "support_zones": [{"level": 98.0, "low": 97.9, "high": 98.1}],
        "resistance_zones": [{"level": 105.0, "low": 104.9, "high": 105.1}],
    }


def test_scorer_and_planner_use_the_same_original_bounds_gate():
    """A 10-point wide original zone is rejected on both sides of the seam.

    original_bounds 90–100 with ATR 2 is 5.00 ATR wide (cap 1.00); the current
    bounds 99–100 would look valid on their own, which is exactly the gap
    R80-91-02 closes.
    """

    wide = _zone(original_bounds=(90.0, 100.0), current=(99.0, 100.0))
    side = evaluate_candidate_sets(
        _context(wide), _technical(), as_of=_AS_OF
    )["buy"]

    assert side.state == "no_zone"
    assert side.quality_raw == 0
    assert wide["original_bounds"] != {"low": wide["low"], "high": wide["high"]}
    candidate = side.candidates[0]
    assert candidate.mandatory_passed is False
    assert GEOMETRY_WIDTH_TOO_WIDE in candidate.rejection_codes
    assert candidate.geometry["width_atr"] == 5.0
    assert candidate.geometry["plan_eligible"] is False

    plans = produce_scenario_plans_from_zones(
        _technical(), {"buy": wide, "sell": None}, min_rr=Fraction(2, 1)
    )
    assert plans["buy"] is None

    # The gate itself is what both sides consult (same helper, same verdict).
    gate = pre_plan_geometry_gate(
        side="buy",
        original_low=90.0,
        original_high=100.0,
        formation_atr=_ATR,
        execution_atr=_ATR,
        price=_PRICE,
        tick_size=0.1,
    )
    assert gate.plan_eligible is False
    assert gate.width_score == 0.0


def test_planner_gate_ignores_current_bounds_when_original_bounds_exist():
    """A narrow current band must not smuggle a wide original zone into a plan."""

    wide = _zone(original_bounds=(90.0, 100.0), current=(99.0, 100.0))
    narrow = _zone(original_bounds=(99.0, 100.0), current=(99.0, 100.0))

    assert (
        produce_scenario_plans_from_zones(
            _technical(), {"buy": wide, "sell": None}, min_rr=Fraction(2, 1)
        )["buy"]
        is None
    )
    plan = produce_scenario_plans_from_zones(
        _technical(), {"buy": narrow, "sell": None}, min_rr=Fraction(2, 1)
    )["buy"]
    assert isinstance(plan, ScenarioPlan)


def test_valid_original_bounds_keep_the_existing_plan_geometry():
    """Control: entry/SL/TP and the plan shape are unchanged by the shared gate."""

    zone = _zone(original_bounds=(99.0, 100.0), current=(99.0, 100.0))
    plans = produce_scenario_plans_from_zones(
        _technical(), {"buy": zone, "sell": None}, min_rr=Fraction(2, 1)
    )

    plan = plans["buy"]
    assert isinstance(plan, ScenarioPlan)
    assert plan.direction == "buy"
    # Entry anchors at the protective zone's own edge; SL buffers by 1.0 * ATR;
    # TP is the nearest opposite level beyond the far edge (unchanged contract).
    assert plan.entry == 99.0
    assert plan.stop_loss == 99.0 - _ATR
    assert plan.take_profit == 105.0
    assert plan.entry_zone_low == 99.0 and plan.entry_zone_high == 100.0

    # The same candidate is eligible on the scorer side of the seam.
    side = evaluate_candidate_sets(
        _context(zone), _technical(), as_of=_AS_OF
    )["buy"]
    assert side.state == "evaluated"
    assert side.ordered[0].geometry["plan_eligible"] is True


def test_far_original_zone_is_rejected_by_both_sides():
    """Hard distance is measured on the same bounds by scorer and planner."""

    far = _zone(original_bounds=(99.0, 100.0), current=(99.0, 100.0))
    technical = _technical()
    technical["price"] = 100.0 + HARD_DISTANCE_ATR * _ATR + 0.5

    side = evaluate_candidate_sets(_context(far), technical, as_of=_AS_OF)["buy"]
    assert side.candidates[0].geometry["plan_eligible"] is False
    assert (
        produce_scenario_plans_from_zones(
            technical, {"buy": far, "sell": None}, min_rr=Fraction(2, 1)
        )["buy"]
        is None
    )


def test_gate_thresholds_are_the_approved_ones():
    assert MAX_ZONE_WIDTH_ATR == 1.0
    assert HARD_DISTANCE_ATR == 3.0


# -- R80-91-02 (còn lại): formation ATR vs execution ATR ---------------------


def _atr_zone(*, formation_atr, original_bounds=(99.0, 102.0), current=(99.0, 100.0)):
    """Canonical BUY zone whose formation ATR is independent of the execution ATR."""

    zone = _zone(original_bounds=original_bounds, current=current)
    zone["departure_measurement"] = {
        "direction": "buy",
        "body_atr": 0.6,
        "body_range": 0.8,
        "directional_close_location": 0.86,
        "atr_before_event": formation_atr,
        "status": "ok",
    }
    # The formation ATR is the zone's own (source timeframe) reference; the
    # execution ATR lives only on the frozen technical snapshot.
    zone.pop("formation_atr", None)
    return zone


def test_formation_atr_owns_width_and_execution_atr_owns_distance():
    """R80-91-02: a wide zone under its own formation ATR is rejected by both.

    original width 3.00 with formation ATR 1.00 is 3.00 ATR (cap 1.00), while the
    execution ATR 5.00 would have made the same zone look 0.60 ATR wide — the
    exact confusion P11 forbids.
    """

    zone = _atr_zone(formation_atr=1.0)
    technical = _technical()
    technical["atr_h4"] = 5.0
    technical["atr_d1"] = 5.0
    technical["resistance_zones"] = [{"level": 120.0, "low": 119.9, "high": 120.1}]

    side = evaluate_candidate_sets(_context(zone), technical, as_of=_AS_OF)["buy"]
    candidate = side.candidates[0]
    assert candidate.geometry["width_atr"] == 3.0
    assert GEOMETRY_WIDTH_TOO_WIDE in candidate.rejection_codes
    assert candidate.geometry["plan_eligible"] is False
    assert side.state == "no_zone"

    plans = produce_scenario_plans_from_zones(
        technical, {"buy": zone, "sell": None}, min_rr=Fraction(2, 1)
    )
    assert plans["buy"] is None


def test_same_bounds_pass_when_the_formation_atr_is_the_wide_one():
    """Mirror: formation ATR 5 makes width 0.60 ATR and both sides accept it."""

    zone = _atr_zone(formation_atr=5.0)
    technical = _technical()
    technical["atr_h4"] = 2.0
    technical["atr_d1"] = 2.0
    technical["resistance_zones"] = [{"level": 120.0, "low": 119.9, "high": 120.1}]

    side = evaluate_candidate_sets(_context(zone), technical, as_of=_AS_OF)["buy"]
    candidate = side.candidates[0]
    assert isclose(candidate.geometry["width_atr"], 0.6, abs_tol=1e-12)
    assert candidate.geometry["plan_eligible"] is True
    assert candidate.mandatory_passed is True
    assert side.state == "evaluated"

    plans = produce_scenario_plans_from_zones(
        technical, {"buy": zone, "sell": None}, min_rr=Fraction(2, 1)
    )
    plan = plans["buy"]
    assert isinstance(plan, ScenarioPlan)
    # Entry/SL/TP keep the existing contract: SL buffers by the execution ATR
    # (2.0), TP is the nearest opposite level beyond the far edge.
    assert plan.entry == 99.0
    assert plan.stop_loss == 99.0 - 2.0
    assert plan.take_profit == 120.0
    assert plan.source == "smc_canonical_zone"


def test_hard_distance_still_uses_the_execution_atr():
    """The distance term keeps the frozen execution ATR, not the formation ATR."""

    zone = _atr_zone(formation_atr=5.0)
    technical = _technical()
    technical["atr_h4"] = 2.0
    technical["atr_d1"] = 2.0
    # Distance is measured from the ORIGINAL far edge (102): 6.5 / 2 = 3.25.
    technical["price"] = 102.0 + 3.0 * 2.0 + 0.5
    technical["resistance_zones"] = [{"level": 120.0, "low": 119.9, "high": 120.1}]

    side = evaluate_candidate_sets(_context(zone), technical, as_of=_AS_OF)["buy"]
    candidate = side.candidates[0]
    assert isclose(candidate.geometry["distance_atr"], 3.25, abs_tol=1e-9)
    assert candidate.geometry["plan_eligible"] is False

    assert (
        produce_scenario_plans_from_zones(
            technical, {"buy": zone, "sell": None}, min_rr=Fraction(2, 1)
        )["buy"]
        is None
    )


def test_canonical_provenance_without_usable_formation_atr_fails_closed():
    """Canonical evidence present but its ATR unusable -> no plan, no substitute.

    The boundary is the provenance block, not the zone label: a payload that
    carries canonical formation evidence (here ``departure_measurement`` with a
    null ATR) must fail the geometry gate closed, while a payload that carries no
    canonical evidence at all keeps the producer's existing reference (the live
    Scanner selected-zone projection today) — see the R80-91-02 note in the log.
    """

    unusable = _zone(original_bounds=(99.0, 100.0), current=(99.0, 100.0))
    unusable["departure_measurement"] = {
        "direction": "buy",
        "atr_before_event": None,
        "status": "unavailable",
    }
    unusable["formation_atr"] = None
    technical = _technical()
    technical["resistance_zones"] = [{"level": 105.0, "low": 104.9, "high": 105.1}]

    assert (
        produce_scenario_plans_from_zones(
            technical, {"buy": unusable, "sell": None}, min_rr=Fraction(2, 1)
        )["buy"]
        is None
    )

    # A payload with no canonical evidence block keeps the documented existing
    # reference so the live Scanner projection is unchanged.
    legacy = {
        "zone_id": "smcz-legacy",
        "direction": "buy",
        "low": 99.0,
        "high": 100.0,
        "level": 99.5,
    }
    technical["resistance_zones"] = [{"level": 105.0, "low": 104.9, "high": 105.1}]
    unchanged = produce_scenario_plans_from_zones(
        technical, {"buy": legacy, "sell": None}, min_rr=Fraction(2, 1)
    )["buy"]
    assert isinstance(unchanged, ScenarioPlan)
    assert unchanged.source == "smc_canonical_zone"

    # The technical fallback path is untouched as well.
    fallback = produce_scenario_plans_from_zones(
        technical, {"buy": None, "sell": None}, min_rr=Fraction(2, 1)
    )["buy"]
    assert isinstance(fallback, ScenarioPlan)
    assert fallback.source == "technical_zone"
