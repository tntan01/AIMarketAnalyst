"""R100-01 — final selection must lock identity before any projection.

Finding (Task100 review): the coordinator accepted any ``PlanAttempt`` whose
``plan_available`` was true and attached it to the candidate being tried, so a
final result could report one selected zone while carrying another zone's
scenario; and ``project_smc_quality_raw`` published a plausible SMC raw from a
final result that the validator already rejected.

This file locks both ends:
* the coordinator refuses a foreign attempt and keeps walking the approved
  order, so a later candidate with its OWN plan is still selected;
* the DTO/validator refuse an ``evaluated`` side without selected identity and a
  plan of the same zone/setup, and refuse a B/Q/L/C breakdown that does not
  agree with ``total``/``quality_raw``/``quality_score``;
* the projection applies exactly that invariant instead of emitting a raw.

Contract sources: selection spec §5/§6/§8, compatibility spec §2/§3,
checklist 93/94/95/96.
"""

from __future__ import annotations

import dataclasses
import importlib
from fractions import Fraction

import pytest

from core.scanner_scenario_producers import plan_for_candidate
from core.smc_quality import evaluate_candidate_sets
from core.smc_scoring_result import (
    SmcSideSelection,
    SmcScoringResult,
    SmcSideScoringResult,
    validate_smc_selection_result,
    validate_smc_side_selection,
)
from core.smc_selection import (
    PLAN_ATTEMPT_IDENTITY_MISMATCH,
    finalize_canonical_result,
    finalize_side_selection,
    select_canonical_sides,
    select_side_candidate,
)
from core.technical_signal_scorer import (
    TechnicalScoreDataError,
    project_smc_quality_raw,
    validate_smc_quality_raw_result,
)

_COORD = importlib.import_module("tests.test_smc_selection_coordinator_task93")
_CALLER = importlib.import_module("tests.test_smc_canonical_caller_task91")

_AS_OF = _COORD._AS_OF
_MIN_RR = Fraction(2, 1)


def _two_candidates(*, price=101.5):
    """`smcz-first` raw 10 / R:R 2.0; `smcz-second` raw 8 / R:R 3.5."""

    technical = dict(_COORD._technical(), price=price)
    candidate_set = evaluate_candidate_sets(
        _COORD._context(
            [
                _COORD._ob("smcz-first", 101.0, 102.0),
                _COORD._ob("smcz-second", 98.0, 99.0, full_formation=False),
            ]
        ),
        technical,
        as_of=_AS_OF,
    )["buy"]
    return candidate_set, technical


def _good_result():
    technical = _COORD._technical()
    candidate_sets = evaluate_candidate_sets(
        _COORD._context([_COORD._ob("smcz-good", 99.0, 100.0)]),
        technical,
        as_of=_AS_OF,
    )
    return finalize_canonical_result(
        select_canonical_sides(candidate_sets, technical, min_rr=_MIN_RR)
    )


def _forge(selection: SmcSideSelection, **changes) -> SmcSideSelection:
    """A payload that never passed the constructor — a foreign/deserialized one.

    The DTO now refuses these at construction, so a regression test has to build
    them the way such a payload would really arrive.
    """

    values = {
        item.name: getattr(selection, item.name)
        for item in dataclasses.fields(SmcSideSelection)
    }
    values.update(changes)
    forged = object.__new__(SmcSideSelection)
    for name, value in values.items():
        object.__setattr__(forged, name, value)
    return forged


def _result_with(selection: SmcSideSelection, *, good) -> SmcScoringResult:
    return SmcScoringResult(
        scoring_version=good.scoring_version,
        sides={
            "buy": SmcSideScoringResult(
                score=selection.quality_raw, breakdown={}, selection=selection
            ),
            "sell": good.side("sell"),
        },
    )


# -- 1. Coordinator identity lock ---------------------------------------------


def test_a_plan_of_another_candidate_is_never_attached_to_the_one_tried():
    """The reviewer's repro: candidate A receives candidate B's valid plan."""

    candidate_set, technical = _two_candidates()
    first, second = candidate_set.ordered
    plan_of_second = plan_for_candidate(second, technical, _MIN_RR)
    assert plan_of_second.plan_available is True

    def foreign(candidate, technical_, min_rr=None, snapshot_metadata=None):
        if candidate.candidate_id == first.candidate_id:
            return plan_of_second
        return plan_for_candidate(
            candidate, technical_, min_rr=min_rr, snapshot_metadata=snapshot_metadata
        )

    selection = select_side_candidate(
        candidate_set, technical, min_rr=_MIN_RR, plan_for=foreign
    )

    # A is not selected with B's plan...
    assert selection.selected_candidate_id == second.candidate_id
    assert selection.plan.entry_zone_low == second.plan_zone["low"]
    assert selection.plan.entry_zone_low != first.plan_zone["low"]
    # ... the mismatch is explicit in the trace ...
    rejected = selection.trace[0]
    assert rejected.candidate_id == first.candidate_id
    assert rejected.plan_available is False
    assert rejected.rejection_codes == (PLAN_ATTEMPT_IDENTITY_MISMATCH,)
    # ... and B was still tried and selected with its own plan.
    assert selection.trace[1].candidate_id == second.candidate_id
    assert selection.trace[1].plan_available is True


def test_the_finalized_result_carries_one_setup_only():
    candidate_set, technical = _two_candidates()
    first, second = candidate_set.ordered
    plan_of_second = plan_for_candidate(second, technical, _MIN_RR)

    def foreign(candidate, technical_, min_rr=None, snapshot_metadata=None):
        if candidate.candidate_id == first.candidate_id:
            return plan_of_second
        return plan_for_candidate(
            candidate, technical_, min_rr=min_rr, snapshot_metadata=snapshot_metadata
        )

    payload = finalize_side_selection(
        select_side_candidate(candidate_set, technical, min_rr=_MIN_RR, plan_for=foreign)
    ).selection

    assert payload.selected_zone_id == "smcz-second"
    assert payload.selected_setup_id == "smcs-smcz-second"
    assert payload.plan_zone_id == payload.selected_zone_id
    assert payload.plan_setup_id == payload.selected_setup_id
    assert (payload.zone_low, payload.zone_high) == (98.0, 99.0)
    assert (
        payload.plan["entry_zone_low"],
        payload.plan["entry_zone_high"],
    ) == (payload.zone_low, payload.zone_high)
    assert payload.quality_raw == 8
    assert validate_smc_side_selection(payload)


def test_every_foreign_identity_variant_is_refused():
    candidate_set, technical = _two_candidates()
    first, second = candidate_set.ordered
    plan_of_second = plan_for_candidate(second, technical, _MIN_RR)

    def variant(**changes):
        base = plan_of_second

        def planner(candidate, technical_, min_rr=None, snapshot_metadata=None):
            if candidate.candidate_id == first.candidate_id:
                return dataclasses.replace(base, **changes)
            return plan_for_candidate(
                candidate,
                technical_,
                min_rr=min_rr,
                snapshot_metadata=snapshot_metadata,
            )

        return planner

    for changes in (
        {"candidate_id": "smcz-someone-else"},
        {"zone_id": "smcz-someone-else"},
        {"setup_id": "smcs-someone-else"},
    ):
        selection = select_side_candidate(
            candidate_set, technical, min_rr=_MIN_RR, plan_for=variant(**changes)
        )
        assert selection.trace[0].rejection_codes == (
            PLAN_ATTEMPT_IDENTITY_MISMATCH,
        ), changes
        assert selection.selected_candidate_id == second.candidate_id
        assert selection.plan_zone_id == "smcz-second"


def test_a_foreign_attempt_cannot_stop_the_ordered_search():
    """A foreign rejection is not a signal about this candidate."""

    candidate_set, technical = _two_candidates()
    first, second = candidate_set.ordered
    attempted: list[str] = []

    def foreign_snapshot_claim(candidate, technical_, min_rr=None, snapshot_metadata=None):
        attempted.append(candidate.candidate_id)
        if candidate.candidate_id == first.candidate_id:
            from core.scanner_scenario_producers import PLAN_SNAPSHOT_UNAVAILABLE

            return dataclasses.replace(
                plan_for_candidate(second, technical_, _MIN_RR),
                candidate_id="smcz-elsewhere",
                rejection_codes=(PLAN_SNAPSHOT_UNAVAILABLE,),
                plan=None,
                plan_available=False,
            )
        return plan_for_candidate(
            candidate, technical_, min_rr=min_rr, snapshot_metadata=snapshot_metadata
        )

    selection = select_side_candidate(
        candidate_set,
        technical,
        min_rr=_MIN_RR,
        plan_for=foreign_snapshot_claim,
    )

    assert attempted == ["smcz-first", "smcz-second"]
    assert selection.selected_candidate_id == "smcz-second"
    assert selection.state == "evaluated"


def test_the_honest_seam_is_unaffected_by_the_identity_lock():
    candidate_set, technical = _two_candidates()

    selection = select_side_candidate(
        candidate_set, technical, min_rr=Fraction(5, 2)
    )

    assert selection.selected_candidate_id == "smcz-second"
    assert [entry.candidate_id for entry in selection.trace] == [
        "smcz-first",
        "smcz-second",
    ]
    assert selection.trace[0].rejection_codes == ("PLAN_MIN_RR",)
    assert selection.trace[1].rejection_codes == ()


# -- 2. DTO / validator invariant ---------------------------------------------


def test_evaluated_without_selected_identity_or_plan_is_refused_at_construction():
    with pytest.raises(ValueError):
        SmcSideSelection(side="buy", state="evaluated", quality_raw=10)


def test_forged_evaluated_payload_is_refused_by_the_validator():
    good = _good_result()
    selection = good.side("buy").selection

    forged = [
        _forge(selection, selected_zone_id=None, selected_candidate_id=None),
        _forge(selection, plan=None, plan_available=False),
        _forge(selection, selected_candidate_id=None),
        _forge(selection, plan_zone_id="smcz-other"),
        _forge(selection, plan_setup_id="smcs-other"),
        _forge(selection, plan={**selection.plan, "zone_id": "smcz-other"}),
        _forge(selection, plan={**selection.plan, "setup_id": "smcs-other"}),
        _forge(selection, plan={**selection.plan, "direction": "sell"}),
        _forge(
            selection,
            plan={**selection.plan, "entry_zone_low": 500.0, "entry_zone_high": 501.0},
        ),
        _forge(selection, zone_low=None, zone_high=None),
    ]
    for payload in forged:
        assert validate_smc_side_selection(payload) is False
        assert validate_smc_selection_result(_result_with(payload, good=good)) is False


def test_inconsistent_bqlc_total_raw_or_score_is_refused_by_the_validator():
    good = _good_result()
    selection = good.side("buy").selection
    assert selection.b is not None and selection.q is not None

    forged = [
        _forge(selection, quality_raw=selection.quality_raw + 1),
        _forge(selection, total=float(selection.total) + 0.5),
        _forge(selection, quality_score=float(selection.quality_score) + 1.0),
        _forge(selection, q=None),
        _forge(selection, b=1.5),
        _forge(selection, c=-0.25),
        _forge(selection, total=None),
        _forge(selection, quality_score=None),
    ]
    for payload in forged:
        assert validate_smc_side_selection(payload) is False
        assert validate_smc_selection_result(_result_with(payload, good=good)) is False


def test_the_valid_side_still_passes_every_check():
    good = _good_result()
    selection = good.side("buy").selection

    assert validate_smc_side_selection(selection) is True
    assert validate_smc_selection_result(good) is True
    assert validate_smc_quality_raw_result(good) is True


def test_a_forged_payload_cannot_be_smuggled_through_a_round_trip():
    good = _good_result()
    forged = _forge(good.side("buy").selection, quality_raw=99)

    with pytest.raises(ValueError):
        SmcSideSelection.from_dict(forged.to_dict())
    with pytest.raises(ValueError):
        SmcScoringResult.from_dict(
            _result_with(forged, good=good).to_dict()
        )


# -- 3. Projection applies the whole invariant --------------------------------


def test_projection_refuses_an_evaluated_result_without_identity_or_plan():
    good = _good_result()
    selection = good.side("buy").selection

    for payload in (
        _forge(selection, selected_zone_id=None, selected_candidate_id=None),
        _forge(selection, plan=None, plan_available=False),
        _forge(selection, plan_zone_id="smcz-other"),
    ):
        result = _result_with(payload, good=good)
        with pytest.raises(TechnicalScoreDataError):
            project_smc_quality_raw(result, "buy")
        assert validate_smc_quality_raw_result(result) is False


def test_projection_refuses_a_foreign_plan_of_the_same_candidate():
    """Same ids, different band: the plan is not the one that was accepted."""

    good = _good_result()
    selection = good.side("buy").selection
    payload = _forge(
        selection,
        plan={**selection.plan, "entry_zone_low": 500.0, "entry_zone_high": 501.0},
    )

    with pytest.raises(TechnicalScoreDataError):
        project_smc_quality_raw(_result_with(payload, good=good), "buy")


def test_projection_refuses_inconsistent_arithmetic():
    good = _good_result()
    selection = good.side("buy").selection

    for payload in (
        _forge(selection, quality_raw=selection.quality_raw + 1),
        _forge(selection, total=float(selection.total) + 0.5),
        _forge(selection, quality_score=float(selection.quality_score) + 1.0),
        _forge(selection, q=1.5),
    ):
        with pytest.raises(TechnicalScoreDataError):
            project_smc_quality_raw(_result_with(payload, good=good), "buy")


# -- 4. Valid cases keep their behaviour --------------------------------------


def test_the_valid_states_still_project():
    good = _good_result()
    assert project_smc_quality_raw(good, "buy").raw == 10

    technical = _COORD._technical()
    no_zone = finalize_canonical_result(
        select_canonical_sides(
            evaluate_candidate_sets(_COORD._context([]), technical, as_of=_AS_OF),
            technical,
            min_rr=_MIN_RR,
        )
    )
    zero = project_smc_quality_raw(no_zone, "buy")
    assert (zero.state, zero.raw, zero.plan_available) == ("no_zone", 0, False)
    assert validate_smc_quality_raw_result(no_zone) is True

    unavailable = finalize_canonical_result(
        select_canonical_sides(
            evaluate_candidate_sets(
                _COORD._context([_COORD._ob("smcz-good", 99.0, 100.0)]),
                technical,
                as_of=_AS_OF,
                core_reason_codes=("SMC_H4_COVERAGE_GAP",),
            ),
            technical,
            min_rr=_MIN_RR,
        )
    )
    missing = project_smc_quality_raw(unavailable, "buy")
    assert (missing.state, missing.raw) == ("data_unavailable", None)
    assert validate_smc_quality_raw_result(unavailable) is True


def test_watch_zone_without_a_plan_still_validates_and_is_not_ready():
    technical = _COORD._technical(resistance=())
    result = finalize_canonical_result(
        select_canonical_sides(
            evaluate_candidate_sets(
                _COORD._context([_COORD._ob("smcz-watch", 99.0, 100.0)]),
                technical,
                as_of=_AS_OF,
            ),
            technical,
            min_rr=_MIN_RR,
        )
    )
    selection = result.side("buy").selection

    assert selection.state == "watch_zone"
    assert selection.plan_available is False
    assert selection.plan is None
    assert validate_smc_side_selection(selection) is True
    assert validate_smc_selection_result(result) is True
    projection = project_smc_quality_raw(result, "buy")
    assert projection.raw == 10
    assert projection.readiness_status != "READY_NOW"


def test_m15_swap_still_never_changes_the_quality_of_a_candidate():
    technical = _COORD._technical()
    window = _CALLER._m15_confirming_zone()

    def finalize(m15):
        return finalize_canonical_result(
            select_canonical_sides(
                evaluate_candidate_sets(
                    _COORD._context([_COORD._ob("smcz-m15", 99.0, 100.0)]),
                    technical,
                    as_of=_CALLER._AS_OF if m15 is not None else _AS_OF,
                    m15_candles=m15,
                    m15_as_of=_CALLER._AS_OF if m15 is not None else None,
                ),
                technical,
                min_rr=_MIN_RR,
            )
        ).side("buy").selection

    baseline = finalize(None)
    confirmed = finalize(window)
    moved = finalize(_window_that_stops_confirming(window))

    assert confirmed.quality_raw == moved.quality_raw == baseline.quality_raw == 10
    assert (confirmed.b, confirmed.q, confirmed.l, confirmed.c) == (
        baseline.b,
        baseline.q,
        baseline.l,
        baseline.c,
    )
    # The M15 state moved without touching any quality number.
    assert confirmed.readiness["m15_status"] == "confirmed"
    assert moved.readiness["m15_status"] == "waiting"
    for selection in (confirmed, moved):
        assert validate_smc_side_selection(selection) is True


def _window_that_stops_confirming(window):
    extra = [
        _CALLER._candle(len(window) + index, 106.0, 106.3, 105.9, 106.2)
        for index in range(20)
    ]
    return list(window) + extra


def test_the_replay_still_derives_its_status_and_validates():
    from core.smc_validation import replay_canonical_snapshot

    technical = _COORD._technical()
    sample = replay_canonical_snapshot(
        {
            "sample_id": "r100-01",
            "symbol": "EUR/USD",
            "smc": _COORD._context([_COORD._ob("smcz-replay", 99.0, 100.0)]),
            "technical": technical,
            "as_of": _CALLER._AS_OF,
            "m15_as_of": _CALLER._AS_OF,
            "m15_candles": _CALLER._m15_confirming_zone(),
            "status": "READY_NOW",
        },
        min_rr=_MIN_RR,
    )

    assert sample["status_source"] == "derived"
    assert sample["status"] == "READY_NOW"
    assert sample["selected_zone_id"] == "smcz-replay"


# -- 5. R100-01 (re-review): strict scalar typing in the invariant owner ------
#
# Python treats ``True`` as ``1``: ``True == 1`` and ``float(True) == 1.0``.  A
# boolean that lands on the canonical value would therefore slip through an
# equality-only check.  These are the exact coincidences the re-review used:
#
#   S = 4 * 0.25   = 1.00   -> ``True == 1``    matches quality_raw and total
#   S = 4 * 0.0375 = 0.15   -> ``100*S/15 == 1`` matches quality_score
#
# The numeric payloads below are the positive controls; only the type gate may
# separate them from the boolean variants.

_S_ONE = {
    "b": 0.25,
    "q": 0.0,
    "l": 0.0,
    "c": 0.0,
    "total": 1.0,
    "quality_raw": 1,
    "quality_score": 100 * 1.0 / 15,
}
_S_SCORE_ONE = {
    "b": 0.0375,
    "q": 0.0,
    "l": 0.0,
    "c": 0.0,
    "total": 0.15,
    "quality_raw": 0,
    "quality_score": 1.0,
}


def _constructor_kwargs(selection: SmcSideSelection) -> dict:
    return {
        item.name: getattr(selection, item.name)
        for item in dataclasses.fields(SmcSideSelection)
    }


def _quality_payload(good, **overrides) -> SmcSideSelection:
    return _forge(good.side("buy").selection, **overrides)


def _assert_refused_by_every_layer(payload, *, good) -> None:
    """Direct DTO, side validator, result validator and projection agree."""

    with pytest.raises(ValueError):
        SmcSideSelection(**_constructor_kwargs(payload))
    assert validate_smc_side_selection(payload) is False
    result = _result_with(payload, good=good)
    assert validate_smc_selection_result(result) is False
    assert validate_smc_quality_raw_result(result) is False
    with pytest.raises(TechnicalScoreDataError):
        project_smc_quality_raw(result, "buy")


def test_the_numerically_coincident_payloads_are_the_valid_controls():
    good = _good_result()

    for values in (_S_ONE, _S_SCORE_ONE):
        payload = _quality_payload(good, **values)
        result = _result_with(payload, good=good)

        assert validate_smc_side_selection(payload) is True, values
        assert validate_smc_selection_result(result) is True, values
        projection = project_smc_quality_raw(result, "buy")
        assert projection.raw == values["quality_raw"]
        assert projection.total == values["total"]


def test_a_boolean_quality_raw_is_never_the_canonical_raw():
    good = _good_result()
    payload = _quality_payload(good, **{**_S_ONE, "quality_raw": True})

    # Python cannot tell them apart numerically, which is the whole leak...
    assert payload.quality_raw is True and payload.quality_raw == 1
    # ... so the type gate is what refuses it.
    _assert_refused_by_every_layer(payload, good=good)


def test_a_boolean_total_is_never_the_canonical_total():
    good = _good_result()
    payload = _quality_payload(good, **{**_S_ONE, "total": True})

    assert payload.total is True and payload.total == 1.0
    _assert_refused_by_every_layer(payload, good=good)


def test_a_boolean_quality_score_is_never_the_canonical_score():
    good = _good_result()
    payload = _quality_payload(good, **{**_S_SCORE_ONE, "quality_score": True})

    assert payload.quality_score is True and payload.quality_score == 1.0
    _assert_refused_by_every_layer(payload, good=good)


def test_boolean_scalars_are_refused_even_when_they_do_not_coincide():
    """The rule is the type, not the accidental agreement of the value."""

    good = _good_result()
    assert good.side("buy").selection.quality_raw == 10

    for changes in (
        {"quality_raw": True},
        {"total": True},
        {"quality_score": True},
    ):
        _assert_refused_by_every_layer(
            _quality_payload(good, **changes), good=good
        )


def test_the_strict_scalar_rule_also_guards_the_zone_band_and_the_plan_band():
    good = _good_result()
    selection = good.side("buy").selection

    # Same numeric band, written as a boolean.
    numeric = _quality_payload(good)
    assert validate_smc_side_selection(numeric) is True

    for changes in (
        {"zone_low": True},
        {"zone_high": True},
        {"plan": {**selection.plan, "entry_zone_low": True}},
        {"plan": {**selection.plan, "entry_zone_high": True}},
    ):
        _assert_refused_by_every_layer(_quality_payload(good, **changes), good=good)
