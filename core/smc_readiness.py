"""SMC readiness mapping (task 90).

Maps the SMC-local state of one side to the consumer status of the approved
readiness contract (docs/plans/smc-readiness-spec.md §1–§6): which zone/visit/
M15/conflict state the side is in, whether an entry may even be considered, and
which reasons explain a waiting/blocked verdict.

Scope boundary of this lot: SMC readiness is *not* entry permission.  The plan
step belongs to the coordinator (tasks 92–99) and the external gates
(safety/macro/account/portfolio/journal) to tasks 101–116, so this module:

* never claims ``READY_NOW`` without an available plan (``plan_available=True``
  must be supplied by the caller; ``None`` means the planner has not run yet);
* always reports ``can_execute=False`` and ``revalidation_required=True`` —
  execution revalidation is mandatory before any dispatch.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from core.smc_models import (
    SMC_QUALITY_STATE_DATA_UNAVAILABLE,
    SmcCandidateSet,
)

# Consumer statuses (readiness spec §1).
SMC_STATUS_READY_NOW = "READY_NOW"
SMC_STATUS_WAITING_CONFIRMATION = "WAITING_CONFIRMATION"
SMC_STATUS_WATCH_ZONE = "WATCH_ZONE"
SMC_STATUS_OUT_OF_STRATEGY = "OUT_OF_STRATEGY"
SMC_STATUS_BLOCKED = "BLOCKED"
SMC_STATUS_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
VALID_SMC_READINESS_STATUSES = frozenset({
    SMC_STATUS_READY_NOW,
    SMC_STATUS_WAITING_CONFIRMATION,
    SMC_STATUS_WATCH_ZONE,
    SMC_STATUS_OUT_OF_STRATEGY,
    SMC_STATUS_BLOCKED,
    SMC_STATUS_DATA_UNAVAILABLE,
})

# Detailed SMC states (readiness spec §3, §8).
SMC_STATE_DATA_UNAVAILABLE = "DATA_UNAVAILABLE"
SMC_STATE_NO_ZONE = "NO_ZONE"
SMC_STATE_ZONE_CANDIDATE = "ZONE_CANDIDATE"
SMC_STATE_ACTIVE_WAITING_VISIT = "ACTIVE_WAITING_VISIT"
SMC_STATE_VISIT_OPEN = "VISIT_OPEN"
SMC_STATE_WAITING_M15 = "WAITING_M15"
SMC_STATE_COUNTERTREND_UNCONFIRMED = "COUNTERTREND_UNCONFIRMED"
SMC_STATE_ZONE_INVALIDATED = "ZONE_INVALIDATED"
SMC_STATE_ZONE_EXPIRED = "ZONE_EXPIRED"
SMC_STATE_LOCAL_READY_PLAN_PENDING = "LOCAL_READY_PLAN_PENDING"
SMC_STATE_READY_FOR_REVALIDATION = "READY_FOR_REVALIDATION"
SMC_STATE_EXTERNAL_CAUTION = "LOCAL_READY_EXTERNAL_CAUTION"
SMC_STATE_EXTERNAL_BLOCKED = "EXTERNAL_BLOCKED"

# Reasoning codes (readiness spec §2 and task 78 contract).
SMC_READY_FOR_REVALIDATION = "SMC_READY_FOR_REVALIDATION"
SMC_CORE_DATA_UNAVAILABLE = "SMC_CORE_DATA_UNAVAILABLE"
SMC_NO_VALID_SETUP = "SMC_NO_VALID_SETUP"
SMC_ZONE_PENDING_CONFIRMATION = "SMC_ZONE_PENDING_CONFIRMATION"
SMC_ZONE_NOT_AVAILABLE_YET = "SMC_ZONE_NOT_AVAILABLE_YET"
SMC_ZONE_INVALID_OR_EXPIRED = "SMC_ZONE_INVALID_OR_EXPIRED"
SMC_WAITING_FOR_ZONE_VISIT = "SMC_WAITING_FOR_ZONE_VISIT"
SMC_WAITING_REACTION = "SMC_WAITING_REACTION"
SMC_TRIGGER_EXPIRED = "TRIGGER_EXPIRED"
SMC_COUNTERTREND_UNCONFIRMED = "SMC_COUNTERTREND_UNCONFIRMED"
SMC_PLAN_UNAVAILABLE = "SMC_PLAN_UNAVAILABLE"
SMC_M15_DATA_UNAVAILABLE = "M15_DATA_UNAVAILABLE"
SMC_M15_INSUFFICIENT_DATA = "M15_INSUFFICIENT_DATA"
SMC_M15_NO_CONFIRMATION = "M15_NO_CONFIRMATION"
SMC_M15_CONFIRMED_PARENT_OPEN = "SMC_M15_CONFIRMED_PARENT_OPEN"
SMC_HARD_INVALID = "SMC_ZONE_HARD_INVALID"


@dataclass(frozen=True, slots=True)
class SmcReadiness:
    """SMC-local readiness verdict for one side."""

    status: str
    smc_state: str
    can_consider_entry: bool
    can_execute: bool
    reason_codes: tuple[str, ...] = ()
    m15_status: str | None = None
    plan_available: bool | None = None
    quality_raw: int | None = None
    selected_zone_id: str | None = None
    selected_setup_id: str | None = None
    entry_blockers: tuple[str, ...] = ()
    revalidation_required: bool = True

    def __post_init__(self) -> None:
        status = str(self.status or "").strip().upper()
        if status not in VALID_SMC_READINESS_STATUSES:
            raise ValueError(f"Invalid SMC readiness status: {self.status}")
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "reason_codes", tuple(_texts(self.reason_codes)))
        object.__setattr__(self, "entry_blockers", tuple(_texts(self.entry_blockers)))
        # Readiness never grants execution by itself (readiness spec §1).
        if self.can_execute:
            raise ValueError("SMC readiness cannot grant execution by itself")
        if self.can_consider_entry and self.status != SMC_STATUS_READY_NOW:
            raise ValueError("can_consider_entry requires READY_NOW")

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "smc_state": self.smc_state,
            "can_consider_entry": self.can_consider_entry,
            "can_execute": self.can_execute,
            "revalidation_required": self.revalidation_required,
            "m15_status": self.m15_status,
            "plan_available": self.plan_available,
            "quality_raw": self.quality_raw,
            "selected_zone_id": self.selected_zone_id,
            "selected_setup_id": self.selected_setup_id,
            "reason_codes": list(self.reason_codes),
            "entry_blockers": list(self.entry_blockers),
        }


def evaluate_smc_readiness(
    candidate_set: SmcCandidateSet,
    *,
    candidate: Any | None = None,
    plan_available: bool | None = None,
    external_status: str | None = None,
    external_reason_codes: Sequence[str] = (),
) -> SmcReadiness:
    """Map one side's SMC state to the consumer status (readiness spec §6).

    ``plan_available`` is the caller's planner verdict: ``True`` only when the
    coordinator produced a plan for this side.  ``None`` means the planner has
    not been consulted at this stage, which is the case before tasks 92–99; the
    verdict then stays at ``WATCH_ZONE`` and never claims entry permission.
    ``external_status`` carries the outer gates ("BLOCKED"/"CAUTION"/"PASS");
    when it is not supplied the external layer is simply not evaluated yet.

    ``candidate`` is the candidate the coordinator actually selected.  It
    defaults to the best ordered candidate; when the planner skipped the first
    candidates, the verdict must describe the SAME candidate the plan belongs
    to, otherwise the zone ids and the plan reference would come from two
    different setups (selection spec §8).
    """

    if not isinstance(candidate_set, SmcCandidateSet):
        raise ValueError("SMC readiness requires a candidate set")
    quality = candidate_set.quality
    common = {
        "m15_status": None,
        "plan_available": plan_available,
        "quality_raw": quality.quality_raw,
    }

    # 1. Snapshot/core data unavailable (precedence §6.1).
    if candidate_set.state == SMC_QUALITY_STATE_DATA_UNAVAILABLE:
        return smc_data_unavailable_readiness(
            quality.reason_codes or (SMC_CORE_DATA_UNAVAILABLE,),
            **common,
        )

    # 2. External BLOCK wins over any SMC-local readiness (precedence §6.2).
    external = str(external_status or "").strip().upper()
    if external == "BLOCKED":
        return _verdict(
            SMC_STATUS_BLOCKED,
            SMC_STATE_EXTERNAL_BLOCKED,
            tuple(external_reason_codes) or ("SMC_EXTERNAL_GATE_BLOCKED",),
            **common,
        )

    # ``ordered`` already excludes hard-rejected candidates (R80-91-01); the
    # full history stays in ``candidate_set.candidates`` for the trace.
    eligible = candidate_set.ordered
    if not eligible:
        # 3. No usable candidate: invalid/expired history vs evaluated-empty.
        has_history = bool(candidate_set.candidates)
        if has_history:
            return _verdict(
                SMC_STATUS_OUT_OF_STRATEGY,
                SMC_STATE_ZONE_INVALIDATED,
                (SMC_ZONE_INVALID_OR_EXPIRED,),
                **common,
            )
        return _verdict(
            SMC_STATUS_WATCH_ZONE,
            SMC_STATE_NO_ZONE,
            (SMC_NO_VALID_SETUP,),
            **common,
        )

    best = eligible[0] if candidate is None else candidate
    common = {
        "m15_status": best.m15_status,
        "plan_available": plan_available,
        "quality_raw": best.quality_raw,
        "selected_zone_id": best.zone_id or None,
        "selected_setup_id": best.setup_id,
    }
    reasons = list(best.reason_codes)

    # 4a. The best candidate itself is terminal.
    if best.confirmation_state in {"invalid", "expired"}:
        return _verdict(
            SMC_STATUS_OUT_OF_STRATEGY,
            SMC_STATE_ZONE_EXPIRED
            if best.confirmation_state == "expired"
            else SMC_STATE_ZONE_INVALIDATED,
            (SMC_ZONE_INVALID_OR_EXPIRED,),
            **common,
        )

    # 4b. Zone is not confirmed/available yet.
    if best.confirmation_state == "candidate":
        blockers = [SMC_ZONE_PENDING_CONFIRMATION]
        if best.available_at is None:
            blockers.append(SMC_ZONE_NOT_AVAILABLE_YET)
        return _verdict(
            SMC_STATUS_WATCH_ZONE,
            SMC_STATE_ZONE_CANDIDATE,
            blockers,
            **common,
        )

    # 5. Countertrend without a confirmed reversal (precedence §6.4).  The
    # quality evaluator emits the bare code, the consumer contract prefixes it.
    if any(
        code == SMC_COUNTERTREND_UNCONFIRMED or code == "COUNTERTREND_UNCONFIRMED"
        for code in reasons
    ):
        return _verdict(
            SMC_STATUS_WATCH_ZONE,
            SMC_STATE_COUNTERTREND_UNCONFIRMED,
            (SMC_COUNTERTREND_UNCONFIRMED,),
            **common,
        )

    # 6. Zone active but the first visit has not happened yet (§6.6).
    if best.visit_id is None:
        return _verdict(
            SMC_STATUS_WATCH_ZONE,
            SMC_STATE_ACTIVE_WAITING_VISIT,
            (SMC_WAITING_FOR_ZONE_VISIT,),
            **common,
        )

    # 7. Visit/M15 waiting states (precedence §6.5).
    m15_status = best.m15_status or "not_required"
    if m15_status == "missing":
        return _verdict(
            SMC_STATUS_WAITING_CONFIRMATION,
            SMC_STATE_WAITING_M15,
            _waiting_reasons(best, (SMC_M15_DATA_UNAVAILABLE,)),
            **common,
        )
    if m15_status != "confirmed":
        return _verdict(
            SMC_STATUS_WAITING_CONFIRMATION,
            SMC_STATE_VISIT_OPEN,
            _waiting_reasons(best, (SMC_M15_NO_CONFIRMATION,)),
            **common,
        )

    # 8. All SMC-local conditions pass: the plan decides between ready and watch.
    if plan_available is not True:
        return _verdict(
            SMC_STATUS_WATCH_ZONE,
            SMC_STATE_LOCAL_READY_PLAN_PENDING,
            (SMC_PLAN_UNAVAILABLE,),
            **common,
        )

    if external == "CAUTION":
        return _verdict(
            SMC_STATUS_WATCH_ZONE,
            SMC_STATE_EXTERNAL_CAUTION,
            tuple(external_reason_codes) or ("SMC_EXTERNAL_GATE_CAUTION",),
            **common,
        )

    return _verdict(
        SMC_STATUS_READY_NOW,
        SMC_STATE_READY_FOR_REVALIDATION,
        (SMC_READY_FOR_REVALIDATION,),
        can_consider_entry=True,
        **common,
    )


def smc_data_unavailable_readiness(
    reason_codes: Sequence[str] = (),
    **kwargs: Any,
) -> SmcReadiness:
    """The canonical ``DATA_UNAVAILABLE`` verdict (readiness spec §5.5/§6.1).

    Exposed so a caller that detects an unusable shared snapshot *outside* the
    candidate set (for example the coordinator's plan seam reporting no usable
    execution context) reports exactly the same verdict the ladder produces,
    instead of inventing a second mapping.
    """

    return _verdict(
        SMC_STATUS_DATA_UNAVAILABLE,
        SMC_STATE_DATA_UNAVAILABLE,
        tuple(reason_codes) or (SMC_CORE_DATA_UNAVAILABLE,),
        **kwargs,
    )


def _waiting_reasons(
    candidate: Any,
    default: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = list(default)
    for code in candidate.reason_codes:
        if code == SMC_TRIGGER_EXPIRED and SMC_TRIGGER_EXPIRED not in reasons:
            reasons.append(SMC_TRIGGER_EXPIRED)
    if candidate.m15_status == "expired" and SMC_TRIGGER_EXPIRED not in reasons:
        reasons.append(SMC_TRIGGER_EXPIRED)
    return tuple(dict.fromkeys(reasons))


def _verdict(
    status: str,
    smc_state: str,
    reason_codes: Sequence[str],
    *,
    can_consider_entry: bool = False,
    **kwargs: Any,
) -> SmcReadiness:
    reasons = tuple(dict.fromkeys(str(code) for code in reason_codes if str(code)))
    return SmcReadiness(
        status=status,
        smc_state=smc_state,
        can_consider_entry=can_consider_entry,
        can_execute=False,
        reason_codes=reasons,
        entry_blockers=reasons if status != SMC_STATUS_READY_NOW else (),
        **kwargs,
    )


def _texts(values: Sequence[object]) -> list[str]:
    return [str(value).strip() for value in values if str(value).strip()]
