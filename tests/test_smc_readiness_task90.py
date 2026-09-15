"""Task 90 — SMC readiness mapping (docs/plans/smc-readiness-spec.md §1–§8).

The verdict is SMC-local: it never grants execution, never claims READY without
an available plan and keeps DATA_UNAVAILABLE apart from no-zone.
"""

from __future__ import annotations

import pytest

from core.smc_models import (
    CandidateEvaluation,
    SmcCandidateSet,
    SmcQualityBreakdown,
)
from core.smc_readiness import (
    SMC_M15_DATA_UNAVAILABLE,
    SMC_M15_NO_CONFIRMATION,
    SMC_NO_VALID_SETUP,
    SMC_PLAN_UNAVAILABLE,
    SMC_READY_FOR_REVALIDATION,
    SMC_STATUS_BLOCKED,
    SMC_STATUS_DATA_UNAVAILABLE,
    SMC_STATUS_OUT_OF_STRATEGY,
    SMC_STATUS_READY_NOW,
    SMC_STATUS_WAITING_CONFIRMATION,
    SMC_STATUS_WATCH_ZONE,
    SMC_TRIGGER_EXPIRED,
    SMC_WAITING_FOR_ZONE_VISIT,
    SMC_ZONE_INVALID_OR_EXPIRED,
    SmcReadiness,
    evaluate_smc_readiness,
)

_QUALITY = SmcQualityBreakdown(b=0.8, q=0.7, l=0.5, c=0.6)


def _candidate(**overrides):
    payload = {
        "candidate_id": "smcz-ready",
        "zone_id": "smcz-ready",
        "setup_id": "smcs-ready",
        "side": "buy",
        "timeframe": "H4",
        "family": "ob",
        "confirmation_state": "confirmed",
        "quality": _QUALITY,
        "visit_id": "smcz-ready:visit-1",
        "available_at": "2026-02-05T00:00:00+00:00",
        "m15_status": "confirmed",
        "mandatory_passed": True,
        "confirmation_rank": 0,
    }
    payload.update(overrides)
    return CandidateEvaluation(**payload)


def _candidate_set(candidate=None, **overrides):
    payload = {
        "side": "buy",
        "state": "evaluated",
        "quality": _QUALITY,
        "candidates": (candidate if candidate is not None else _candidate(),),
    }
    payload.update(overrides)
    return SmcCandidateSet(**payload)


def test_ready_requires_an_available_plan():
    candidate_set = _candidate_set()

    without_plan = evaluate_smc_readiness(candidate_set)
    assert without_plan.status == SMC_STATUS_WATCH_ZONE
    assert without_plan.can_consider_entry is False
    assert without_plan.reason_codes == (SMC_PLAN_UNAVAILABLE,)

    failed_plan = evaluate_smc_readiness(candidate_set, plan_available=False)
    assert failed_plan.status == SMC_STATUS_WATCH_ZONE
    assert failed_plan.reason_codes == (SMC_PLAN_UNAVAILABLE,)

    ready = evaluate_smc_readiness(candidate_set, plan_available=True)
    assert ready.status == SMC_STATUS_READY_NOW
    assert ready.can_consider_entry is True
    assert ready.can_execute is False
    assert ready.revalidation_required is True
    assert ready.reason_codes == (SMC_READY_FOR_REVALIDATION,)
    assert ready.selected_zone_id == "smcz-ready"
    assert ready.selected_setup_id == "smcs-ready"
    assert ready.quality_raw == _QUALITY.quality_raw


def test_execution_is_never_granted_by_smc_readiness():
    with pytest.raises(ValueError):
        SmcReadiness(
            status=SMC_STATUS_READY_NOW,
            smc_state="READY_FOR_REVALIDATION",
            can_consider_entry=True,
            can_execute=True,
        )
    with pytest.raises(ValueError):
        SmcReadiness(
            status=SMC_STATUS_WATCH_ZONE,
            smc_state="NO_ZONE",
            can_consider_entry=True,
            can_execute=False,
        )


def test_core_unavailable_is_not_the_same_as_no_zone():
    unavailable = SmcCandidateSet(
        side="buy",
        state="data_unavailable",
        quality=SmcQualityBreakdown.data_unavailable("SMC_H4_COVERAGE_GAP"),
    )
    verdict = evaluate_smc_readiness(unavailable, plan_available=True)
    assert verdict.status == SMC_STATUS_DATA_UNAVAILABLE
    assert verdict.quality_raw is None
    assert verdict.can_consider_entry is False
    assert "SMC_H4_COVERAGE_GAP" in verdict.reason_codes

    no_zone = SmcCandidateSet(
        side="buy",
        state="no_zone",
        quality=SmcQualityBreakdown.no_zone(SMC_NO_VALID_SETUP),
    )
    empty = evaluate_smc_readiness(no_zone)
    assert empty.status == SMC_STATUS_WATCH_ZONE
    assert empty.quality_raw == 0
    assert empty.reason_codes == (SMC_NO_VALID_SETUP,)
    assert empty.can_consider_entry is False


def test_invalid_or_expired_history_is_out_of_strategy():
    invalid = _candidate(
        confirmation_state="invalid",
        quality=None,
        mandatory_passed=False,
        rejection_codes=(SMC_ZONE_INVALID_OR_EXPIRED,),
        confirmation_rank=3,
    )
    verdict = evaluate_smc_readiness(_candidate_set(invalid))
    assert verdict.status == SMC_STATUS_OUT_OF_STRATEGY
    assert SMC_ZONE_INVALID_OR_EXPIRED in verdict.reason_codes
    assert verdict.can_consider_entry is False


def test_waiting_states_follow_the_visit_and_m15_contract():
    no_visit = _candidate(visit_id=None)
    waiting_visit = evaluate_smc_readiness(_candidate_set(no_visit))
    assert waiting_visit.status == SMC_STATUS_WATCH_ZONE
    assert SMC_WAITING_FOR_ZONE_VISIT in waiting_visit.reason_codes

    missing_m15 = _candidate(m15_status="missing")
    waiting_m15 = evaluate_smc_readiness(
        _candidate_set(missing_m15), plan_available=True
    )
    assert waiting_m15.status == SMC_STATUS_WAITING_CONFIRMATION
    assert SMC_M15_DATA_UNAVAILABLE in waiting_m15.reason_codes
    # A plan never turns a missing M15 confirmation into entry permission.
    assert waiting_m15.can_consider_entry is False

    waiting_trigger = _candidate(m15_status="waiting")
    verdict = evaluate_smc_readiness(_candidate_set(waiting_trigger), plan_available=True)
    assert verdict.status == SMC_STATUS_WAITING_CONFIRMATION
    assert SMC_M15_NO_CONFIRMATION in verdict.reason_codes

    expired = _candidate(
        m15_status="expired",
        reason_codes=(SMC_TRIGGER_EXPIRED,),
    )
    expired_verdict = evaluate_smc_readiness(_candidate_set(expired), plan_available=True)
    assert expired_verdict.status == SMC_STATUS_WAITING_CONFIRMATION
    assert SMC_TRIGGER_EXPIRED in expired_verdict.reason_codes


def test_countertrend_and_pending_candidates_stay_watch_only():
    countertrend = _candidate(reason_codes=("COUNTERTREND_UNCONFIRMED",))
    verdict = evaluate_smc_readiness(_candidate_set(countertrend), plan_available=True)
    assert verdict.status == SMC_STATUS_WATCH_ZONE
    assert verdict.can_consider_entry is False

    pending = _candidate(
        confirmation_state="candidate",
        confirmation_rank=3,
        available_at=None,
        visit_id=None,
    )
    pending_verdict = evaluate_smc_readiness(
        _candidate_set(pending), plan_available=True
    )
    assert pending_verdict.status == SMC_STATUS_WATCH_ZONE
    assert "SMC_ZONE_PENDING_CONFIRMATION" in pending_verdict.reason_codes


def test_external_gates_can_only_lower_the_verdict():
    candidate_set = _candidate_set()

    blocked = evaluate_smc_readiness(
        candidate_set,
        plan_available=True,
        external_status="BLOCKED",
        external_reason_codes=("MACRO_BLOCKED",),
    )
    assert blocked.status == SMC_STATUS_BLOCKED
    assert "MACRO_BLOCKED" in blocked.reason_codes
    assert blocked.can_consider_entry is False

    caution = evaluate_smc_readiness(
        candidate_set,
        plan_available=True,
        external_status="CAUTION",
        external_reason_codes=("MACRO_CAUTION",),
    )
    assert caution.status == SMC_STATUS_WATCH_ZONE
    assert caution.can_consider_entry is False

    passed = evaluate_smc_readiness(
        candidate_set, plan_available=True, external_status="PASS"
    )
    assert passed.status == SMC_STATUS_READY_NOW


def test_verdict_is_serializable_and_keeps_the_side_quality():
    verdict = evaluate_smc_readiness(_candidate_set(), plan_available=True)
    payload = verdict.to_dict()
    assert payload["status"] == SMC_STATUS_READY_NOW
    assert payload["quality_raw"] == _QUALITY.quality_raw
    assert payload["revalidation_required"] is True
    assert payload["m15_status"] == "confirmed"
