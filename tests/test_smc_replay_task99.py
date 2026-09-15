"""Task 99 — snapshot replay on the shared evaluator and planner seam.

A replay must reach the SAME evaluator and the SAME plan seam with the SAME
input set the live route supplies (context, technical, cutoff, M15 window and
the caller's core-data verdict), and its ``status`` must be DERIVED from the
resulting readiness verdict — a declared label in the snapshot is inert.

The legacy ``score_smc`` replay is deliberately untouched by this task.
"""

from __future__ import annotations

import importlib
from fractions import Fraction

import pytest

from core.smc_quality import evaluate_candidate_sets
from core.smc_validation import (
    REPLAY_SNAPSHOT_MALFORMED,
    SMC_SNAPSHOT_REPLAY_VERSION,
    replay_canonical_snapshot,
    replay_samples_match,
)
from core.smc_versions import SMC_SELECTION_VERSION

_COORD = importlib.import_module("tests.test_smc_selection_coordinator_task93")
_CALLER = importlib.import_module("tests.test_smc_canonical_caller_task91")

_AS_OF = _CALLER._AS_OF
_MIN_RR = Fraction(2, 1)


def _snapshot(**overrides):
    snapshot = {
        "sample_id": "snap-1",
        "symbol": "EUR/USD",
        "smc": _COORD._context([_COORD._ob("smcz-replay", 99.0, 100.0)]),
        "technical": _COORD._technical(),
        "as_of": _AS_OF,
        "m15_as_of": _AS_OF,
        "m15_candles": _CALLER._m15_confirming_zone(),
        "core_reason_codes": (),
        "metadata": {"capture_source": "fixture"},
    }
    snapshot.update(overrides)
    return snapshot


# -- The shared seam is really the one being used ------------------------------


def test_replay_runs_the_shared_evaluator_and_the_shared_planner_once(monkeypatch):
    from core import smc_selection, smc_snapshot

    evaluator_calls: list[dict] = []
    planner_calls: list[str] = []
    # Task 114: replay delegates to the ONE canonical seam, so the evaluator
    # is reached through ``core.smc_snapshot`` for every route.
    real_evaluator = smc_snapshot.evaluate_candidate_sets
    real_planner = smc_selection.plan_for_candidate

    def spy_evaluator(smc, technical=None, **kwargs):
        evaluator_calls.append({"smc": smc, "technical": technical, **kwargs})
        return real_evaluator(smc, technical, **kwargs)

    def spy_planner(candidate, technical, min_rr=None, snapshot_metadata=None):
        planner_calls.append(candidate.candidate_id)
        return real_planner(
            candidate, technical, min_rr=min_rr, snapshot_metadata=snapshot_metadata
        )

    monkeypatch.setattr(smc_snapshot, "evaluate_candidate_sets", spy_evaluator)
    monkeypatch.setattr(smc_selection, "plan_for_candidate", spy_planner)

    replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)

    assert len(evaluator_calls) == 1
    assert planner_calls == ["smcz-replay"]


def test_replay_feeds_the_evaluator_the_same_inputs_the_live_caller_does(
    monkeypatch,
):
    """No thinner input set: same context/technical/cutoff/M15/core reasons."""

    from core import smc_scorer, smc_snapshot

    live_calls: list[dict] = []
    replay_calls: list[dict] = []
    real = smc_snapshot.evaluate_candidate_sets

    def recorder(target):
        def spy(smc, technical=None, **kwargs):
            target.append({"smc": smc, "technical": technical, **kwargs})
            return real(smc, technical, **kwargs)

        return spy

    snapshot = _snapshot(core_reason_codes=("SMC_H4_COVERAGE_GAP",))

    monkeypatch.setattr(smc_scorer, "evaluate_candidate_sets", recorder(live_calls))
    smc_scorer.evaluate_canonical_diagnostics(
        snapshot["smc"],
        snapshot["technical"],
        as_of=snapshot["m15_as_of"],
        core_reason_codes=snapshot["core_reason_codes"],
        m15_candles=snapshot["m15_candles"],
        m15_as_of=snapshot["m15_as_of"],
    )
    monkeypatch.undo()

    monkeypatch.setattr(smc_snapshot, "evaluate_candidate_sets", recorder(replay_calls))
    replay_canonical_snapshot(snapshot, min_rr=_MIN_RR)

    assert len(live_calls) == len(replay_calls) == 1
    live, replay = live_calls[0], replay_calls[0]
    assert live["smc"] == replay["smc"]
    assert live["technical"] == replay["technical"]
    assert live["as_of"] == replay["as_of"] == _AS_OF
    assert live["m15_as_of"] == replay["m15_as_of"] == _AS_OF
    assert live["core_reason_codes"] == replay["core_reason_codes"]
    assert live["m15_candles"] == replay["m15_candles"]


def test_replay_never_touches_the_legacy_scorer(monkeypatch):
    from core import smc_validation

    def must_not_run(*args, **kwargs):  # pragma: no cover - failure path
        raise AssertionError("replay must not use the legacy score_smc route")

    monkeypatch.setattr(smc_validation, "score_smc", must_not_run)

    sample = replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)

    assert sample["status"] == "READY_NOW"


# -- Status is derived ---------------------------------------------------------


def test_the_status_is_derived_from_the_result_not_declared():
    sample = replay_canonical_snapshot(
        _snapshot(status="READY_NOW", declared_side="sell"), min_rr=_MIN_RR
    )

    assert sample["declared_status"] == "READY_NOW"
    assert sample["status_source"] == "derived"
    assert sample["replay_contract_version"] == SMC_SNAPSHOT_REPLAY_VERSION
    assert sample["selection_version"] == SMC_SELECTION_VERSION
    # Derived from the readiness verdict of the side that was actually reported.
    assert sample["status"] == sample["sides"][sample["side"]]["readiness_status"]


def test_a_declared_label_cannot_change_the_replay_sample():
    honest = replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)
    declared = replay_canonical_snapshot(
        _snapshot(status="READY_NOW"), min_rr=_MIN_RR
    )

    assert replay_samples_match(honest, declared)
    assert declared["status"] == honest["status"]


def test_replay_reports_the_derived_side_and_its_quality():
    sample = replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)

    assert sample["side"] == "buy"
    assert sample["quality_raw"] == 10
    assert sample["selected_zone_id"] == "smcz-replay"
    assert sample["selected_setup_id"] == "smcs-smcz-replay"
    assert sample["plan_available"] is True
    assert sample["smc_state"] == "READY_FOR_REVALIDATION"
    assert sample["sides"]["sell"]["quality_raw"] == 0


def test_replay_keeps_null_and_zero_apart():
    technical = _COORD._technical()
    empty = _snapshot(
        smc=_COORD._context([]), technical=technical, m15_candles=None
    )
    unavailable = _snapshot(
        technical=technical,
        m15_candles=None,
        core_reason_codes=("SMC_H4_COVERAGE_GAP",),
    )

    zero = replay_canonical_snapshot(empty, min_rr=_MIN_RR)
    missing = replay_canonical_snapshot(unavailable, min_rr=_MIN_RR)

    assert zero["sides"]["buy"]["quality_raw"] == 0
    assert zero["sides"]["buy"]["state"] == "no_zone"
    assert missing["sides"]["buy"]["quality_raw"] is None
    assert missing["sides"]["buy"]["state"] == "data_unavailable"


# -- Parity and determinism ----------------------------------------------------


def test_live_diagnostics_and_replay_agree_on_the_evaluated_facts():
    """Same snapshot -> same candidates, raw and order on both routes."""

    from core.smc_scorer import evaluate_canonical_diagnostics

    snapshot = _snapshot()
    live = evaluate_canonical_diagnostics(
        snapshot["smc"],
        snapshot["technical"],
        as_of=snapshot["as_of"],
        core_reason_codes=snapshot["core_reason_codes"],
        m15_candles=snapshot["m15_candles"],
        m15_as_of=snapshot["m15_as_of"],
    )
    replay = replay_canonical_snapshot(snapshot, min_rr=_MIN_RR)

    for side in ("buy", "sell"):
        assert replay["sides"][side]["quality_raw"] == live["sides"][side]["quality_raw"]
        assert (
            replay["sides"][side]["quality_state"] == live["sides"][side]["state"]
        )

    buy = live["sides"]["buy"]
    assert buy["ordered_candidate_ids"] == ["smcz-replay"]
    assert replay["sides"]["buy"]["selected_zone_id"] == "smcz-replay"
    # The replay is the only route with a planner, so only it can be READY.
    assert buy["readiness"]["plan_available"] is None
    assert buy["readiness"]["status"] != "READY_NOW"


def test_replay_is_deterministic_for_the_same_snapshot():
    first = replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)
    second = replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)

    assert replay_samples_match(first, second)
    assert first["sides"] == second["sides"]


def test_replay_without_a_plan_policy_cannot_become_ready():
    sample = replay_canonical_snapshot(_snapshot(), min_rr=None)

    assert sample["plan_available"] is False
    assert sample["status"] != "READY_NOW"
    assert sample["sides"]["buy"]["plan_rejection_codes"] == [
        "PLAN_POLICY_UNAVAILABLE"
    ]


def test_replay_of_an_invalidated_zone_never_reports_it_as_selected():
    broken = _COORD._ob("smcz-replay", 99.0, 100.0)
    broken["lifecycle_status"] = "invalid"
    broken["broken"] = True

    sample = replay_canonical_snapshot(
        _snapshot(smc=_COORD._context([broken]), m15_candles=None), min_rr=_MIN_RR
    )

    assert sample["sides"]["buy"]["state"] == "out_of_strategy"
    assert sample["sides"]["buy"]["selected_zone_id"] is None
    assert sample["sides"]["buy"]["plan_available"] is False
    assert sample["status"] != "READY_NOW"


def test_replay_rejects_a_malformed_snapshot_instead_of_guessing():
    """Garbage in must not read as "evaluated, nothing found" (compat §3)."""

    for payload in (None, {}, {"smc": "not-a-dict"}, {"technical": 3}):
        sample = replay_canonical_snapshot(payload, min_rr=_MIN_RR)
        assert sample["sides"]["buy"]["quality_raw"] is None
        assert sample["sides"]["buy"]["state"] == "data_unavailable"
        assert sample["status"] == "DATA_UNAVAILABLE"
        assert sample["side"] == "neutral"
        assert REPLAY_SNAPSHOT_MALFORMED in (
            sample["sides"]["buy"]["quality_reason_codes"]
        )


def test_a_caller_supplied_core_verdict_outranks_the_shape_check():
    """An explicit core verdict is the caller's word and is kept verbatim."""

    sample = replay_canonical_snapshot(
        _snapshot(core_reason_codes=("SMC_D1_MISSING",)), min_rr=_MIN_RR
    )

    assert sample["status"] == "DATA_UNAVAILABLE"
    assert sample["sides"]["buy"]["reason_codes"] == ["SMC_CORE_DATA_UNAVAILABLE"]
    assert "SMC_D1_MISSING" in sample["sides"]["buy"]["quality_reason_codes"]
    assert REPLAY_SNAPSHOT_MALFORMED not in (
        sample["sides"]["buy"]["quality_reason_codes"]
    )


def test_replay_reports_the_cutoff_it_was_given():
    sample = replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)

    assert sample["as_of"] == _AS_OF
    assert sample["symbol"] == "EUR/USD"
    assert sample["sample_id"] == "snap-1"


def test_replay_samples_match_detects_a_different_decision():
    left = replay_canonical_snapshot(_snapshot(), min_rr=_MIN_RR)
    right = replay_canonical_snapshot(_snapshot(), min_rr=None)

    assert not replay_samples_match(left, right)


def test_the_evaluator_still_accepts_the_snapshot_inputs_directly():
    """Guard against the replay helper drifting from the evaluator contract."""

    snapshot = _snapshot()
    direct = evaluate_candidate_sets(
        snapshot["smc"],
        snapshot["technical"],
        as_of=snapshot["as_of"],
        core_reason_codes=snapshot["core_reason_codes"],
        m15_candles=snapshot["m15_candles"],
        m15_as_of=snapshot["m15_as_of"],
    )["buy"]
    replay = replay_canonical_snapshot(snapshot, min_rr=_MIN_RR)

    assert direct.quality.quality_raw == replay["sides"]["buy"]["quality_raw"] == 10


def test_replay_requires_a_valid_min_rr_type_to_reach_the_planner():
    """A garbage policy is a caller error, not a silently accepted verdict."""

    with pytest.raises(TypeError):
        replay_canonical_snapshot(_snapshot(), min_rr="two")
