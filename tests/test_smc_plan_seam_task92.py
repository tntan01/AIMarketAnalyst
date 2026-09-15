"""Task 92 — pure ``plan_for_candidate`` seam.

The planner must be callable for ONE evaluated candidate without a canonical
result, must use the SAME shared geometry gate as the scorer, must keep the
rejection reason when it refuses, and must never reach for the scorer.

Every expected number is written from the approved contract (selection spec §5,
parameter table P11, core/plans/smc-geometry thresholds) — the production helper
is never used to produce an expectation.
"""

from __future__ import annotations

import importlib
from fractions import Fraction

import pytest

from core.scanner_composition import ScenarioPlan
from core.smc_geometry import GEOMETRY_WIDTH_TOO_WIDE
from core.smc_models import candidate_plan_zone
from core.smc_quality import evaluate_candidate_sets
from core.scanner_scenario_producers import (
    PLAN_CANDIDATE_EVIDENCE_MISSING,
    PLAN_MIN_RR,
    PLAN_POLICY_UNAVAILABLE,
    PLAN_SNAPSHOT_UNAVAILABLE,
    PLAN_TP_MISSING,
    PlanAttempt,
    plan_for_candidate,
    plan_to_dict,
)

_QUALITY = importlib.import_module("tests.test_smc_quality_task88")
_GEOMETRY = importlib.import_module("tests.test_smc_geometry_task89")

_AS_OF = _QUALITY._AS_OF
_PRICE = 99.5
_ATR = 2.0
_MIN_RR = Fraction(2, 1)


def _technical(*, resistance=105.0, support=97.0, atr=_ATR, price=_PRICE):
    technical = dict(_QUALITY._technical(price=price, atr=atr))
    technical["resistance_zones"] = (
        [] if resistance is None else [{"level": resistance, "low": resistance - 0.1,
                                        "high": resistance + 0.1}]
    )
    technical["support_zones"] = (
        [] if support is None else [{"level": support, "low": support - 0.1,
                                     "high": support + 0.1}]
    )
    return technical


def _buy_candidate(zone=None, *, technical=None):
    technical = technical or _technical()
    side = evaluate_candidate_sets(
        _QUALITY._context(zone or _QUALITY._zone()), technical, as_of=_AS_OF
    )["buy"]
    assert side.ordered, "fixture must produce one eligible BUY candidate"
    return side.ordered[0], technical


# -- The seam is pure and candidate-shaped ------------------------------------


def test_plan_is_built_without_a_canonical_result():
    candidate, technical = _buy_candidate()

    attempt = plan_for_candidate(candidate, technical, _MIN_RR)

    assert isinstance(attempt, PlanAttempt)
    assert attempt.plan_available is True
    assert attempt.candidate_id == candidate.candidate_id
    assert attempt.rejection_codes == ()
    plan = attempt.plan
    assert isinstance(plan, ScenarioPlan)
    # Unchanged plan geometry: entry on the protective edge, SL = 1.0 * ATR
    # beyond it, TP at the nearest opposite level past the far edge.
    assert (plan.entry, plan.stop_loss, plan.take_profit) == (99.0, 99.0 - _ATR, 105.0)
    assert (plan.entry_zone_low, plan.entry_zone_high) == (99.0, 100.0)
    assert plan.source == "smc_canonical_zone"


def test_the_seam_carries_the_evidence_the_scorer_gated_on():
    """The candidate owns the exact payload subset the gate validated."""

    candidate, _ = _buy_candidate()

    assert candidate.plan_zone == candidate_plan_zone(_QUALITY._zone())
    assert candidate.plan_zone["low"] == 99.0
    assert candidate.plan_zone["high"] == 100.0
    assert candidate.plan_zone["original_bounds"] == {"low": 99.0, "high": 100.0}
    assert candidate.plan_zone["departure_measurement"]["atr_before_event"] == _ATR
    assert candidate.plan_zone["tick_size"] == 0.1


def test_seam_rejects_a_candidate_that_carries_no_plan_evidence():
    import dataclasses

    candidate, technical = _buy_candidate()
    stripped = dataclasses.replace(candidate, plan_zone=None)

    attempt = plan_for_candidate(stripped, technical, _MIN_RR)

    assert attempt.plan_available is False
    assert attempt.plan is None
    assert attempt.rejection_codes == (PLAN_CANDIDATE_EVIDENCE_MISSING,)


def test_seam_refuses_anything_that_is_not_an_evaluated_candidate():
    with pytest.raises(ValueError):
        plan_for_candidate({"zone_id": "smcz-x"}, _technical(), _MIN_RR)


def test_seam_never_reaches_the_scorer_or_the_quality_evaluator(monkeypatch):
    from core import scanner_scenario_producers as planner

    assert "smc_scorer" not in dir(planner)
    assert "smc_quality" not in dir(planner)

    candidate, technical = _buy_candidate()
    attempt = plan_for_candidate(candidate, technical, _MIN_RR)
    assert attempt.plan_available is True


# -- Rejection reasons are kept ------------------------------------------------


def test_wide_original_bounds_are_rejected_with_the_shared_geometry_reason():
    """Cover 90–100 / formation ATR 2 = 5.00 ATR wide against a 1.00 cap."""

    wide = _QUALITY._zone(original_bounds={"low": 90.0, "high": 100.0})
    side = evaluate_candidate_sets(
        _QUALITY._context(wide), _technical(), as_of=_AS_OF
    )["buy"]
    rejected = side.candidates[0]
    assert rejected.mandatory_passed is False
    assert GEOMETRY_WIDTH_TOO_WIDE in rejected.rejection_codes

    attempt = plan_for_candidate(rejected, _technical(), _MIN_RR)

    assert attempt.plan_available is False
    assert GEOMETRY_WIDTH_TOO_WIDE in attempt.rejection_codes


def test_formation_atr_owns_the_width_the_planner_reads():
    """The planner uses the zone's own ATR, never the execution ATR (P11)."""

    zone = _GEOMETRY._atr_zone(formation_atr=1.0)
    technical = _technical(atr=5.0)
    side = evaluate_candidate_sets(
        _GEOMETRY._context(zone), technical, as_of=_AS_OF
    )["buy"]

    attempt = plan_for_candidate(side.candidates[0], technical, _MIN_RR)

    # 3.00 wide / formation ATR 1.00 = 3.00 ATR > 1.00 cap; the execution ATR
    # 5.00 would have made it look 0.60 ATR wide.
    assert attempt.plan_available is False
    assert GEOMETRY_WIDTH_TOO_WIDE in attempt.rejection_codes


def test_missing_opposite_level_is_reported_not_invented():
    candidate, technical = _buy_candidate(technical=_technical(resistance=None))

    attempt = plan_for_candidate(candidate, technical, _MIN_RR)

    assert attempt.plan_available is False
    assert attempt.rejection_codes == (PLAN_TP_MISSING,)


def test_absent_policy_reports_the_missing_threshold_instead_of_guessing():
    candidate, technical = _buy_candidate()

    attempt = plan_for_candidate(candidate, technical, None)

    assert attempt.plan_available is False
    assert attempt.rejection_codes == (PLAN_POLICY_UNAVAILABLE,)


def test_rr_below_the_policy_floor_is_reported_as_min_rr():
    candidate, technical = _buy_candidate()
    # entry 99, SL 97, TP 105 -> R:R = 6/2 = 3; a 4.0 floor must reject it.
    attempt = plan_for_candidate(candidate, technical, Fraction(4, 1))

    assert attempt.plan_available is False
    assert attempt.rejection_codes == (PLAN_MIN_RR,)


def test_unusable_execution_snapshot_is_its_own_reason():
    candidate, technical = _buy_candidate()
    broken = dict(technical)
    broken["atr_h4"] = None
    broken["atr_d1"] = None

    attempt = plan_for_candidate(candidate, broken, _MIN_RR)

    assert attempt.plan_available is False
    assert attempt.rejection_codes == (PLAN_SNAPSHOT_UNAVAILABLE,)


def test_a_rejected_attempt_has_no_plan_object():
    candidate, technical = _buy_candidate()

    attempt = plan_for_candidate(candidate, technical, None)

    assert attempt.plan is None
    assert attempt.to_dict()["plan"] is None
    with pytest.raises(ValueError):
        PlanAttempt(candidate_id="x", zone_id="y", plan=None, plan_available=True)


# -- The legacy producer keeps the same rule ----------------------------------


def test_the_legacy_producer_and_the_seam_share_one_plan_rule():
    """Same zone, same policy: the live producer and the seam agree exactly."""

    from core.scanner_scenario_producers import produce_scenario_plans_from_zones

    zone = _GEOMETRY._zone(original_bounds=(99.0, 100.0), current=(99.0, 100.0))
    technical = _GEOMETRY._technical()
    side = evaluate_candidate_sets(
        _GEOMETRY._context(zone), technical, as_of=_AS_OF
    )["buy"]
    legacy = produce_scenario_plans_from_zones(
        technical, {"buy": zone, "sell": None}, min_rr=_MIN_RR
    )["buy"]
    attempt = plan_for_candidate(side.ordered[0], technical, _MIN_RR)

    assert legacy is not None
    assert plan_to_dict(legacy) == plan_to_dict(attempt.plan)


def test_sell_candidate_is_the_price_mirror():
    zone = dict(_QUALITY._zone())
    zone.update(
        {
            "zone_id": "smcz-sell-1",
            "setup_id": "smcs-sell-1",
            "direction": "sell",
            "type": "bearish_order_block",
            "original_bounds": {"low": 100.0, "high": 101.0},
            "low": 100.0,
            "high": 101.0,
            "departure_measurement": {
                "direction": "sell",
                "body_atr": 0.6,
                "body_range": 0.8,
                "directional_close_location": 0.86,
                "atr_before_event": _ATR,
                "status": "ok",
            },
        }
    )
    technical = _technical()
    side = evaluate_candidate_sets(
        _QUALITY._context(zone, side="sell", structure="LH/LL", displacement="bearish"),
        technical,
        as_of=_AS_OF,
    )["sell"]

    attempt = plan_for_candidate(side.ordered[0], technical, _MIN_RR)

    plan = attempt.plan
    assert isinstance(plan, ScenarioPlan)
    assert plan.direction == "sell"
    assert plan.entry == 101.0
    assert plan.stop_loss == 101.0 + _ATR
    assert plan.take_profit == 97.0
