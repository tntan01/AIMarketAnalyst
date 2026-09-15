"""Tasks 94/95 — one final result per side, plus the special states.

Task 94: the final result carries the selected candidate's quality, lifecycle,
confirmation and plan reference from ONE setup; alternatives only explain.
Task 95: no-zone is an evaluated ``0``, core-unavailable is ``null``, and a
watch zone without a plan keeps its ids/quality but is never READY.

Contract sources: selection spec §7/§8, readiness spec §5.4/§5.5/§10,
compatibility spec §3.
"""

from __future__ import annotations

import importlib
import json
from fractions import Fraction

import pytest

from core.smc_models import CandidateEvaluation, SmcQualityBreakdown
from core.smc_quality import evaluate_candidate_sets
from core.smc_selection import (
    finalize_canonical_result,
    finalize_side_selection,
    select_canonical_sides,
    select_side_candidate,
)
from core.smc_scoring_result import (
    SELECTION_STATE_DATA_UNAVAILABLE,
    SELECTION_STATE_EVALUATED,
    SELECTION_STATE_NO_ZONE,
    SELECTION_STATE_WATCH_ZONE,
    SmcScoringResult,
    SmcSideSelection,
    validate_smc_selection_result,
    smc_selection_of,
)

_COORD = importlib.import_module("tests.test_smc_selection_coordinator_task93")
_CALLER = importlib.import_module("tests.test_smc_canonical_caller_task91")

_AS_OF = _COORD._AS_OF
_MIN_RR = Fraction(2, 1)


def _selected(side=None, *, technical=None, min_rr=_MIN_RR, as_of=_AS_OF,
              m15_candles=None, core_reason_codes=()):
    technical = technical or _COORD._technical()
    candidate_set = evaluate_candidate_sets(
        _COORD._context(side if side is not None else [_COORD._ob("smcz-first", 101.0, 102.0)]),
        technical,
        as_of=as_of,
        core_reason_codes=core_reason_codes,
        m15_candles=m15_candles,
        m15_as_of=as_of if m15_candles is not None else None,
    )["buy"]
    return select_side_candidate(candidate_set, technical, min_rr=min_rr)


# -- Task 94: one final result per side, all from the same setup ---------------


def test_final_result_carries_quality_zone_confirmation_and_plan_of_one_setup():
    selection = _selected()
    assert selection.selected_candidate_id == "smcz-first"

    side_result = finalize_side_selection(selection)
    payload = smc_selection_of(side_result)
    selected = selection.selected

    assert isinstance(payload, SmcSideSelection)
    assert payload.state == SELECTION_STATE_EVALUATED
    assert payload.selected_candidate_id == selected.candidate_id
    assert payload.selected_zone_id == selected.zone_id
    assert payload.selected_setup_id == selected.setup_id
    assert payload.timeframe == selected.timeframe == "H4"
    assert payload.family == selected.family == "ob"
    assert payload.lifecycle_status == selected.lifecycle_status == "confirmed"
    assert payload.confirmation_state == selected.confirmation_state
    assert payload.confirmation_rank == selected.confirmation_rank
    assert payload.entry_visit_id == selected.visit_id
    assert payload.confirmation_event_id == selected.confirmation_event_id
    # Quality is the SELECTED candidate's, hand-computed in the task93 fixture:
    # formation .62 -> Q .70825, B .8925, L 0, C .75 -> S 10.02775 -> raw 10.
    assert payload.quality_raw == selected.quality_raw == 10
    assert payload.b == pytest.approx(0.8925, abs=1e-9)
    assert payload.q == pytest.approx(0.70825, abs=1e-9)
    assert payload.l == 0.0
    assert payload.c == pytest.approx(0.75, abs=1e-9)
    assert payload.total == pytest.approx(10.02775, abs=1e-9)
    assert side_result.score == 10
    # The plan reference belongs to the same zone.
    assert payload.plan_available is True
    assert payload.plan["direction"] == "buy"
    assert payload.plan["entry_zone_low"] == 101.0
    assert payload.plan["entry_zone_high"] == 102.0


def test_the_final_result_never_carries_the_rejected_candidates_quality():
    """`first` raw 10 is rejected on R:R; the result must report raw 8."""

    candidate_set = evaluate_candidate_sets(
        _COORD._context(
            [
                _COORD._ob("smcz-first", 101.0, 102.0),
                _COORD._ob("smcz-second", 98.0, 99.0, full_formation=False),
            ]
        ),
        _COORD._technical(),
        as_of=_AS_OF,
    )["buy"]
    selection = select_side_candidate(
        candidate_set, _COORD._technical(), min_rr=Fraction(5, 2)
    )

    payload = smc_selection_of(finalize_side_selection(selection))

    assert payload.selected_zone_id == "smcz-second"
    assert payload.quality_raw == 8
    assert payload.quality_raw != candidate_set.candidates[0].quality_raw == 10
    assert [entry.candidate_id for entry in payload.alternatives] == ["smcz-first"]


def test_alternatives_explain_without_becoming_a_second_selected_result():
    candidate_set = evaluate_candidate_sets(
        _COORD._context(
            [
                _COORD._ob("smcz-first", 101.0, 102.0),
                _COORD._ob("smcz-second", 98.0, 99.0, full_formation=False),
            ]
        ),
        _COORD._technical(),
        as_of=_AS_OF,
    )["buy"]
    selection = select_side_candidate(
        candidate_set, _COORD._technical(), min_rr=Fraction(5, 2)
    )

    payload = smc_selection_of(finalize_side_selection(selection))

    assert all(entry.plan_available is False for entry in payload.alternatives)
    assert all(
        entry.zone_id != payload.selected_zone_id for entry in payload.alternatives
    )
    assert payload.plan_available is True


def test_one_result_per_side_and_a_round_trip_that_keeps_it():
    technical = _COORD._technical()
    candidate_sets = evaluate_candidate_sets(
        _COORD._context([_COORD._ob("smcz-first", 101.0, 102.0)]),
        technical,
        as_of=_AS_OF,
    )
    result = finalize_canonical_result(
        select_canonical_sides(candidate_sets, technical, min_rr=_MIN_RR)
    )

    assert set(result.sides) == {"buy", "sell"}
    assert result.side("buy").selection.selected_zone_id == "smcz-first"
    assert result.side("sell").selection.quality_raw == 0

    restored = SmcScoringResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert restored.side("buy").selection == result.side("buy").selection
    assert restored.side("sell").selection == result.side("sell").selection
    assert validate_smc_selection_result(restored)


def test_the_result_module_never_imports_the_planner_or_the_coordinator():
    from core import smc_scoring_result

    assert "scanner_scenario_producers" not in dir(smc_scoring_result)
    assert "smc_selection" not in dir(smc_scoring_result)
    assert "smc_scorer" not in dir(smc_scoring_result)


# -- Task 95: no-zone, core unavailable and watch-no-plan ----------------------


def test_no_zone_is_zero_and_never_certifies_a_selection():
    technical = _COORD._technical()
    candidate_set = evaluate_candidate_sets(
        _COORD._context([]), technical, as_of=_AS_OF
    )["buy"]
    selection = select_side_candidate(candidate_set, technical, min_rr=_MIN_RR)

    payload = smc_selection_of(finalize_side_selection(selection))

    assert payload.state == SELECTION_STATE_NO_ZONE
    assert payload.quality_raw == 0
    # raw 0 and score 0 are the evaluated empty result, not a missing value.
    assert payload.quality_score == 0.0
    assert payload.selected_zone_id is None
    assert payload.selected_setup_id is None
    assert payload.selected_candidate_id is None
    assert payload.plan is None
    assert payload.plan_available is False
    assert payload.readiness["status"] == "WATCH_ZONE"
    assert "SMC_NO_VALID_SETUP" in payload.readiness["reason_codes"]


def test_core_unavailable_is_null_and_never_zero():
    technical = _COORD._technical()
    candidate_set = evaluate_candidate_sets(
        _COORD._context([_COORD._ob("smcz-first", 101.0, 102.0)]),
        technical,
        as_of=_AS_OF,
        core_reason_codes=("SMC_H4_COVERAGE_GAP",),
    )["buy"]
    selection = select_side_candidate(candidate_set, technical, min_rr=_MIN_RR)

    payload = smc_selection_of(finalize_side_selection(selection))

    assert payload.state == SELECTION_STATE_DATA_UNAVAILABLE
    assert payload.quality_raw is None
    assert payload.quality_score is None
    assert payload.selected_zone_id is None
    assert payload.plan_available is False
    assert payload.readiness["status"] == "DATA_UNAVAILABLE"
    # null must not be confused with the evaluated zero above.
    assert payload.quality_raw != 0


def test_watch_zone_without_a_plan_keeps_ids_and_quality_but_is_not_ready():
    """Readiness spec §10 row 2: confirmed zone, no plan -> WATCH_ZONE."""

    technical = _COORD._technical(resistance=())
    selection = _selected(
        [_COORD._ob("smcz-watch", 99.0, 100.0)],
        technical=technical,
        as_of=_CALLER._AS_OF,
        m15_candles=_CALLER._m15_confirming_zone(),
    )

    payload = smc_selection_of(finalize_side_selection(selection))

    assert selection.selected.m15_status == "confirmed"
    assert payload.state == SELECTION_STATE_WATCH_ZONE
    assert payload.selected_zone_id == "smcz-watch"
    assert payload.quality_raw == 10
    assert payload.lifecycle_status == "confirmed"
    assert payload.plan is None
    assert payload.plan_available is False
    assert payload.plan_rejection_codes == ("PLAN_TP_MISSING",)
    assert payload.readiness["status"] == "WATCH_ZONE"
    assert payload.readiness["smc_state"] == "LOCAL_READY_PLAN_PENDING"
    assert payload.readiness["can_consider_entry"] is False
    assert payload.readiness["plan_available"] is False
    assert "SMC_PLAN_UNAVAILABLE" in payload.readiness["reason_codes"]


def test_a_side_without_m15_and_without_a_plan_waits_instead_of_watching():
    """The M15 wait outranks the plan wait in the readiness precedence (§6)."""

    technical = _COORD._technical(resistance=())
    selection = _selected([_COORD._ob("smcz-watch", 99.0, 100.0)], technical=technical)

    payload = smc_selection_of(finalize_side_selection(selection))

    assert payload.state == SELECTION_STATE_WATCH_ZONE
    assert payload.plan_available is False
    assert payload.readiness["status"] == "WAITING_CONFIRMATION"
    assert payload.readiness["can_consider_entry"] is False
    assert "M15_DATA_UNAVAILABLE" in payload.readiness["reason_codes"]


def test_a_planned_side_with_a_confirmed_trigger_reaches_ready_for_revalidation():
    """The plan is what separates READY from watch; nothing else was relaxed."""

    technical = _COORD._technical()
    selection = _selected(
        [_COORD._ob("smcz-ready", 99.0, 100.0)],
        technical=technical,
        as_of=_CALLER._AS_OF,
        m15_candles=_CALLER._m15_confirming_zone(),
    )

    payload = smc_selection_of(finalize_side_selection(selection))

    assert payload.plan_available is True
    assert payload.readiness["status"] == "READY_NOW"
    assert payload.readiness["can_consider_entry"] is True
    # ... and execution is still never granted by SMC readiness alone.
    assert payload.readiness["can_execute"] is False
    assert payload.readiness["revalidation_required"] is True


def test_an_expired_trigger_keeps_a_valid_plan_but_never_becomes_ready():
    """Compatibility spec §3: expiry cancels the entry right, not the plan."""

    as_of = "2026-02-06T12:00:00+00:00"
    selection = _selected(
        as_of=as_of,
        m15_candles=_CALLER._m15_confirming_zone(),
    )

    payload = smc_selection_of(finalize_side_selection(selection))

    assert selection.selected.m15_status == "expired"
    assert selection.selected.confirmation_state == "watch"
    assert payload.quality_raw == 10
    assert payload.plan_available is True
    assert payload.plan is not None
    assert payload.readiness["status"] == "WAITING_CONFIRMATION"
    assert payload.readiness["can_consider_entry"] is False
    assert "TRIGGER_EXPIRED" in payload.readiness["reason_codes"]


def test_an_expired_trigger_never_changes_the_quality_of_the_candidate():
    """R16-03 / readiness spec §9: M15 is readiness, not quality."""

    without_m15 = _selected()
    expired = _selected(
        as_of="2026-02-06T12:00:00+00:00",
        m15_candles=_CALLER._m15_confirming_zone(),
    )
    confirmed = _selected(
        as_of="2026-02-06T05:00:00+00:00",
        m15_candles=_CALLER._m15_confirming_zone(),
    )

    baseline = smc_selection_of(finalize_side_selection(without_m15))
    for other in (expired, confirmed):
        payload = smc_selection_of(finalize_side_selection(other))
        assert (payload.quality_raw, payload.b, payload.q, payload.l, payload.c) == (
            baseline.quality_raw,
            baseline.b,
            baseline.q,
            baseline.l,
            baseline.c,
        )


# -- The final contract refuses a malformed payload ----------------------------


def test_validator_accepts_only_results_whose_selection_agrees_with_its_state():
    technical = _COORD._technical()
    candidate_sets = evaluate_candidate_sets(
        _COORD._context([_COORD._ob("smcz-first", 101.0, 102.0)]), technical, as_of=_AS_OF
    )
    good = finalize_canonical_result(
        select_canonical_sides(candidate_sets, technical, min_rr=_MIN_RR)
    )
    assert validate_smc_selection_result(good)

    assert not validate_smc_selection_result(good.to_dict())
    assert not validate_smc_selection_result(
        SmcScoringResult(scoring_version="smc-v2", sides={})
    )
    assert not validate_smc_selection_result(
        SmcScoringResult(scoring_version="smc-v2", sides={"buy": good.side("buy")})
    )


def test_a_no_zone_payload_can_never_certify_a_selected_zone():
    with pytest.raises(ValueError):
        SmcSideSelection(
            side="buy",
            state=SELECTION_STATE_NO_ZONE,
            quality_raw=0,
            selected_zone_id="smcz-x",
        )


def test_a_data_unavailable_payload_cannot_claim_an_evaluated_zero():
    with pytest.raises(ValueError):
        SmcSideSelection(side="buy", state=SELECTION_STATE_DATA_UNAVAILABLE, quality_raw=0)


def test_an_available_plan_requires_a_plan_object():
    with pytest.raises(ValueError):
        SmcSideSelection(
            side="buy",
            state=SELECTION_STATE_EVALUATED,
            quality_raw=7,
            selected_zone_id="smcz-x",
            plan_available=True,
        )


def test_selected_candidate_must_be_a_typed_evaluation():
    selection = _selected()
    assert isinstance(selection.selected, CandidateEvaluation)
    assert isinstance(selection.quality, SmcQualityBreakdown)
