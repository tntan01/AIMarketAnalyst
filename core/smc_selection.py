"""SMC selection coordinator and final result finalizer (tasks 93–95).

One owner of the final per-side decision (selection spec §1/§6):

```text
candidate set (already evaluated + ordered by the scorer)
  -> try each ordered candidate with the pure plan seam
       - keep the rejection reasons of every attempt
       - the first candidate with a plan is the selected one
  -> finalize the canonical side result of the SAME candidate
```

Discipline kept here:

* the coordinator never calls the scorer again, never changes quality and never
  reorders candidates by R:R/risk;
* a candidate rejected by geometry never hides a later valid candidate;
* a blocking market/account/safety gate stops the loop instead of being dodged
  by trying the next zone;
* an unusable shared snapshot (no price/execution ATR) ends as
  ``data_unavailable`` rather than being papered over by another attempt;
* the result/DTO modules never import this module back — selection depends on
  the planner and the result contract, never the other way round.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Any, Callable, Mapping, Sequence

from core.scanner_scenario_producers import (
    PLAN_SNAPSHOT_UNAVAILABLE,
    PlanAttempt,
    plan_for_candidate,
    plan_to_dict,
)
from core.scanner_composition import ScenarioPlan
from core.smc_models import (
    SMC_QUALITY_STATE_DATA_UNAVAILABLE,
    CandidateEvaluation,
    SmcCandidateSet,
)
from core.smc_readiness import (
    evaluate_smc_readiness,
    smc_data_unavailable_readiness,
)
from core.smc_scoring_result import (
    SELECTION_REASON_CORE_UNAVAILABLE,
    SELECTION_REASON_EXTERNAL_BLOCKED,
    SELECTION_REASON_NEXT_CANDIDATE,
    SELECTION_REASON_NO_VALID_SETUP,
    SELECTION_REASON_QUALITY_RANK,
    SELECTION_REASON_WATCH_NO_PLAN,
    SELECTION_REASON_ZONE_INVALID,
    SELECTION_STATE_BLOCKED,
    SELECTION_STATE_DATA_UNAVAILABLE,
    SELECTION_STATE_EVALUATED,
    SELECTION_STATE_NO_ZONE,
    SELECTION_STATE_OUT_OF_STRATEGY,
    SELECTION_STATE_WATCH_ZONE,
    SmcCandidateTraceEntry,
    SmcScoringResult,
    SmcSideScoringResult,
    SmcSideSelection,
)
from core.smc_versions import SMC_SCORER_VERSION

VALID_SIDES = ("buy", "sell")

# The external gate verdicts the coordinator understands (readiness spec §6.2).
EXTERNAL_STATUS_BLOCKED = "BLOCKED"

# R100-01: a plan may only be accepted for the candidate it was built for.
# A `PlanAttempt` that names another candidate/zone/setup is a foreign plan and
# is refused instead of being attached to the candidate being tried.
PLAN_ATTEMPT_IDENTITY_MISMATCH = "PLAN_ATTEMPT_IDENTITY_MISMATCH"

PlanFor = Callable[..., PlanAttempt]


@dataclass(frozen=True, slots=True)
class SideSelection:
    """Coordinator verdict for one side, before it becomes a result payload."""

    side: str
    state: str
    selected: CandidateEvaluation | None = None
    # Side-level quality of the evaluated candidate set: the `no_zone` zero and
    # the `data_unavailable` null come from here because neither state owns a
    # selected candidate to read a quality from (task 95).
    quality: Any | None = None
    plan: ScenarioPlan | None = None
    plan_available: bool = False
    plan_rejection_codes: tuple[str, ...] = ()
    # R100-01: identity of the candidate the accepted plan was built for.  A
    # plan is only ever carried together with the candidate it belongs to, so a
    # later reader cannot pair a selected zone with another zone's scenario.
    plan_candidate_id: str | None = None
    plan_zone_id: str | None = None
    plan_setup_id: str | None = None
    trace: tuple[SmcCandidateTraceEntry, ...] = ()
    alternatives: tuple[SmcCandidateTraceEntry, ...] = ()
    selection_reason_codes: tuple[str, ...] = ()
    readiness: Any | None = None

    @property
    def selected_candidate_id(self) -> str | None:
        return self.selected.candidate_id if self.selected is not None else None

    @property
    def selected_zone_id(self) -> str | None:
        if self.selected is None:
            return None
        return self.selected.zone_id or None

    @property
    def selected_setup_id(self) -> str | None:
        return self.selected.setup_id if self.selected is not None else None

    @property
    def selected_quality_raw(self) -> int | None:
        """Raw of the selected setup, else the evaluated side-level raw."""

        if self.selected is not None:
            return self.selected.quality_raw
        return getattr(self.quality, "quality_raw", None)


def select_side_candidate(
    candidate_set: SmcCandidateSet,
    technical: Mapping[str, Any] | None,
    *,
    min_rr: Any | None = None,
    plan_for: PlanFor | None = None,
    snapshot_metadata: Mapping[str, Any] | None = None,
    external_status: str | None = None,
    external_reason_codes: Sequence[str] = (),
) -> SideSelection:
    """Try the ordered candidates of one side and keep every rejection reason.

    ``plan_for`` defaults to the pure :func:`plan_for_candidate` seam and is
    injectable so a caller (replay/diagnostics) can supply the same planner
    with a different snapshot without a second selection rule existing.
    """

    if not isinstance(candidate_set, SmcCandidateSet):
        raise ValueError("SMC selection requires an SmcCandidateSet")
    planner: PlanFor = plan_for if plan_for is not None else plan_for_candidate
    external = str(external_status or "").strip().upper()

    # 1. Core/snapshot data unavailable: no candidate may be attempted, and the
    #    side is never turned into an evaluated zero (readiness spec §5.5).
    if candidate_set.state == SMC_QUALITY_STATE_DATA_UNAVAILABLE:
        return _finish(
            SideSelection(
                side=candidate_set.side,
                state=SELECTION_STATE_DATA_UNAVAILABLE,
                selection_reason_codes=(SELECTION_REASON_CORE_UNAVAILABLE,),
            ),
            candidate_set,
            plan_available=False,
            external_status=external_status,
            external_reason_codes=external_reason_codes,
        )

    # 2. A blocking outer gate stops the whole thesis: trying another zone would
    #    only be a way around the gate (selection spec §6).
    if external == EXTERNAL_STATUS_BLOCKED:
        return _finish(
            SideSelection(
                side=candidate_set.side,
                state=SELECTION_STATE_BLOCKED,
                selection_reason_codes=(SELECTION_REASON_EXTERNAL_BLOCKED,),
            ),
            candidate_set,
            plan_available=False,
            external_status=external_status,
            external_reason_codes=external_reason_codes,
        )

    ordered = candidate_set.ordered
    if not ordered:
        evaluated = bool(candidate_set.candidates)
        return _finish(
            SideSelection(
                side=candidate_set.side,
                state=(
                    SELECTION_STATE_OUT_OF_STRATEGY
                    if evaluated
                    else SELECTION_STATE_NO_ZONE
                ),
                selection_reason_codes=(
                    SELECTION_REASON_ZONE_INVALID
                    if evaluated
                    else SELECTION_REASON_NO_VALID_SETUP,
                ),
            ),
            candidate_set,
            plan_available=False,
            external_status=external_status,
            external_reason_codes=external_reason_codes,
        )

    trace: list[SmcCandidateTraceEntry] = []
    for index, candidate in enumerate(ordered):
        attempt = planner(
            candidate,
            technical,
            min_rr=min_rr,
            snapshot_metadata=snapshot_metadata,
        )
        if not _attempt_matches(candidate, attempt):
            # R100-01: the seam returned a plan for a DIFFERENT candidate/zone/
            # setup.  A foreign plan is refused — never attached to the candidate
            # being tried — and the ordered search continues, so a later
            # candidate with its own plan can still be selected.
            trace.append(
                _trace_entry(
                    candidate,
                    attempt,
                    plan_available=False,
                    rejection_codes=(
                        PLAN_ATTEMPT_IDENTITY_MISMATCH,
                        *attempt.rejection_codes,
                    ),
                )
            )
            continue
        trace.append(_trace_entry(candidate, attempt))
        if attempt.plan_available:
            return _finish(
                SideSelection(
                    side=candidate_set.side,
                    state=SELECTION_STATE_EVALUATED,
                    selected=candidate,
                    plan=attempt.plan,
                    plan_available=True,
                    plan_candidate_id=candidate.candidate_id,
                    plan_zone_id=candidate.zone_id or None,
                    plan_setup_id=candidate.setup_id,
                    trace=tuple(trace),
                    alternatives=_alternatives(ordered, index),
                    selection_reason_codes=(
                        SELECTION_REASON_QUALITY_RANK
                        if index == 0
                        else SELECTION_REASON_NEXT_CANDIDATE,
                    ),
                ),
                candidate_set,
                plan_available=True,
                external_status=external_status,
                external_reason_codes=external_reason_codes,
            )
        if PLAN_SNAPSHOT_UNAVAILABLE in attempt.rejection_codes:
            # Shared execution context is unusable: stop instead of hiding a bad
            # snapshot behind another candidate (selection spec §6).
            return _finish(
                SideSelection(
                    side=candidate_set.side,
                    state=SELECTION_STATE_DATA_UNAVAILABLE,
                    trace=tuple(trace),
                    selection_reason_codes=(SELECTION_REASON_CORE_UNAVAILABLE,),
                ),
                candidate_set,
                plan_available=False,
                external_status=external_status,
                external_reason_codes=external_reason_codes,
            )

    # No plan for any candidate, but a confirmed/usable watch zone still exists:
    # it keeps its quality and lifecycle with ``plan_available=false`` and can
    # never be READY (readiness spec §10, task 95).
    best = ordered[0]
    best_attempt_rejections = trace[0].rejection_codes
    return _finish(
        SideSelection(
            side=candidate_set.side,
            state=SELECTION_STATE_WATCH_ZONE,
            selected=best,
            plan_available=False,
            plan_rejection_codes=best_attempt_rejections,
            trace=tuple(trace),
            alternatives=_alternatives(ordered, 0),
            selection_reason_codes=(SELECTION_REASON_WATCH_NO_PLAN,),
        ),
        candidate_set,
        plan_available=False,
        external_status=external_status,
        external_reason_codes=external_reason_codes,
    )


def select_canonical_sides(
    candidate_sets: Mapping[str, SmcCandidateSet],
    technical: Mapping[str, Any] | None,
    *,
    min_rr: Any | None = None,
    plan_for: PlanFor | None = None,
    snapshot_metadata: Mapping[str, Any] | None = None,
    external_status: Mapping[str, str] | None = None,
    external_reason_codes: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, SideSelection]:
    """Run the coordinator for both sides of one snapshot."""

    statuses = external_status if isinstance(external_status, Mapping) else {}
    reasons = external_reason_codes if isinstance(external_reason_codes, Mapping) else {}
    return {
        side: select_side_candidate(
            candidate_sets[side],
            technical,
            min_rr=min_rr,
            plan_for=plan_for,
            snapshot_metadata=snapshot_metadata,
            external_status=statuses.get(side),
            external_reason_codes=reasons.get(side) or (),
        )
        for side in VALID_SIDES
        if isinstance(candidate_sets.get(side), SmcCandidateSet)
    }


def finalize_side_selection(selection: SideSelection) -> SmcSideScoringResult:
    """Write the selected fields of ONE side into the result contract.

    This is the only place that fills a side result's selection payload; it
    only converts typed data and never selects again.
    """

    if not isinstance(selection, SideSelection):
        raise ValueError("finalize_side_selection requires a SideSelection")
    candidate = selection.selected
    quality = candidate.quality if candidate is not None else selection.quality
    zone_low, zone_high = _selected_zone_band(candidate)
    payload = SmcSideSelection(
        side=selection.side,
        state=selection.state,
        selected_candidate_id=selection.selected_candidate_id,
        selected_zone_id=selection.selected_zone_id,
        selected_setup_id=selection.selected_setup_id,
        timeframe=candidate.timeframe if candidate is not None else None,
        family=candidate.family if candidate is not None else None,
        lifecycle_status=candidate.lifecycle_status if candidate is not None else None,
        confirmation_state=(
            candidate.confirmation_state if candidate is not None else None
        ),
        confirmation_rank=(
            candidate.confirmation_rank if candidate is not None else None
        ),
        entry_visit_id=candidate.visit_id if candidate is not None else None,
        confirmation_event_id=(
            candidate.confirmation_event_id if candidate is not None else None
        ),
        # Task117: the typed record travels unchanged, so the stored result keeps
        # the visit anchor, trigger identity/time, expiry, invalidation and reason
        # codes of the SAME candidate the plan belongs to.
        confirmation=(
            candidate.confirmation.to_dict()
            if candidate is not None and candidate.confirmation is not None
            else None
        ),
        quality_raw=quality.quality_raw if quality is not None else None,
        quality_score=quality.quality_score if quality is not None else None,
        b=quality.b if quality is not None else None,
        q=quality.q if quality is not None else None,
        l=quality.l if quality is not None else None,
        c=quality.c if quality is not None else None,
        total=(
            quality.total
            if quality is not None and quality.b is not None
            else None
        ),
        plan=plan_to_dict(
            selection.plan,
            zone_id=selection.plan_zone_id,
            setup_id=selection.plan_setup_id,
        ),
        plan_available=selection.plan_available,
        plan_zone_id=selection.plan_zone_id,
        plan_setup_id=selection.plan_setup_id,
        plan_rejection_codes=selection.plan_rejection_codes,
        zone_low=zone_low,
        zone_high=zone_high,
        readiness=(
            selection.readiness.to_dict()
            if selection.readiness is not None
            else None
        ),
        selection_reason_codes=selection.selection_reason_codes,
        candidate_trace=selection.trace,
        alternatives=selection.alternatives,
        # Lô A: the protected swing of the SELECTED candidate travels with the
        # selection it belongs to.  It is copied verbatim from the candidate the
        # coordinator actually chose — never looked up again here, and never
        # borrowed from another candidate or another timeframe — so the record
        # the consumer publishes describes the same setup as the selected zone.
        protected_swing=(
            candidate.protected_swing if candidate is not None else None
        ),
    )
    return SmcSideScoringResult(
        score=payload.quality_raw,
        breakdown={},
        selected_zone_id=payload.selected_zone_id,
        selected_zone_type=payload.family,
        selected_zone_timeframe=payload.timeframe,
        reason_codes=_side_reason_codes(payload),
        smc_reason=_side_smc_reason(payload),
        selection=payload,
    )


def finalize_canonical_result(
    selections: Mapping[str, SideSelection],
) -> SmcScoringResult:
    """Final canonical result carrying one selected setup per side (task 94)."""

    sides: dict[str, SmcSideScoringResult] = {}
    for side in VALID_SIDES:
        selection = selections.get(side)
        if isinstance(selection, SideSelection):
            sides[side] = finalize_side_selection(selection)
    return SmcScoringResult(
        scoring_version=SMC_SCORER_VERSION,
        sides=sides,
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _finish(
    selection: SideSelection,
    candidate_set: SmcCandidateSet,
    *,
    plan_available: bool,
    external_status: str | None,
    external_reason_codes: Sequence[str],
) -> SideSelection:
    """Attach the readiness verdict of the SAME selected candidate.

    When the loop ended because the shared snapshot itself proved unusable, the
    verdict is the canonical ``DATA_UNAVAILABLE`` one — the candidate set still
    looks evaluated, so the ladder alone would report a watch state and hide
    the real reason.
    """

    if selection.state == SELECTION_STATE_DATA_UNAVAILABLE:
        readiness = smc_data_unavailable_readiness(
            selection.selection_reason_codes,
            quality_raw=candidate_set.quality.quality_raw,
            plan_available=plan_available,
        )
    else:
        readiness = evaluate_smc_readiness(
            candidate_set,
            candidate=selection.selected,
            plan_available=plan_available,
            external_status=external_status,
            external_reason_codes=external_reason_codes,
        )
    return replace(selection, quality=candidate_set.quality, readiness=readiness)


def _selected_zone_band(
    candidate: CandidateEvaluation | None,
) -> tuple[float | None, float | None]:
    """Entry band of the selected candidate, taken from its own plan evidence.

    These are the exact numbers the accepted plan was anchored on, so the result
    can prove the plan and the selected zone are the same setup.
    """

    if candidate is None:
        return None, None
    zone = candidate.plan_zone
    if not isinstance(zone, dict):
        return None, None
    return _finite(zone.get("low")), _finite(zone.get("high"))


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _attempt_matches(
    candidate: CandidateEvaluation,
    attempt: PlanAttempt,
) -> bool:
    """Whether *attempt* really describes the candidate being tried (R100-01).

    The candidate/zone identity must always match.  When the attempt claims a
    plan, the setup lineage must match too, so an accepted plan is provably
    about the same setup as the selected candidate.  Nothing about the ordering,
    geometry, R:R/risk/SL/TP or the external gates is touched here.
    """

    if attempt.candidate_id != candidate.candidate_id:
        return False
    if attempt.zone_id != (candidate.zone_id or None):
        return False
    if attempt.plan_available and attempt.setup_id != candidate.setup_id:
        return False
    return True


def _trace_entry(
    candidate: CandidateEvaluation,
    attempt: PlanAttempt,
    *,
    plan_available: bool | None = None,
    rejection_codes: Sequence[str] | None = None,
) -> SmcCandidateTraceEntry:
    return SmcCandidateTraceEntry(
        candidate_id=candidate.candidate_id,
        side=candidate.side,
        timeframe=candidate.timeframe,
        family=candidate.family,
        zone_id=candidate.zone_id or None,
        setup_id=candidate.setup_id,
        confirmation_state=candidate.confirmation_state,
        confirmation_rank=candidate.confirmation_rank,
        quality_raw=candidate.quality_raw,
        quality_score=candidate.quality_score,
        distance_atr=candidate.distance_atr,
        plan_available=(
            attempt.plan_available if plan_available is None else plan_available
        ),
        rejection_codes=(
            attempt.rejection_codes if rejection_codes is None else rejection_codes
        ),
        reason_codes=candidate.reason_codes,
    )


def _alternatives(
    ordered: Sequence[CandidateEvaluation],
    selected_index: int,
) -> tuple[SmcCandidateTraceEntry, ...]:
    """Remaining ordered candidates, explanation only — never a second plan."""

    return tuple(
        SmcCandidateTraceEntry(
            candidate_id=candidate.candidate_id,
            side=candidate.side,
            timeframe=candidate.timeframe,
            family=candidate.family,
            zone_id=candidate.zone_id or None,
            setup_id=candidate.setup_id,
            confirmation_state=candidate.confirmation_state,
            confirmation_rank=candidate.confirmation_rank,
            quality_raw=candidate.quality_raw,
            quality_score=candidate.quality_score,
            distance_atr=candidate.distance_atr,
            plan_available=False,
            reason_codes=candidate.reason_codes,
        )
        for index, candidate in enumerate(ordered)
        if index != selected_index
    )


def _side_reason_codes(payload: SmcSideSelection) -> tuple[str, ...]:
    codes: list[str] = list(payload.selection_reason_codes)
    codes.extend(payload.plan_rejection_codes)
    if payload.readiness is not None:
        codes.extend(payload.readiness.get("reason_codes") or ())
    return tuple(dict.fromkeys(str(code) for code in codes if str(code)))


def _side_smc_reason(payload: SmcSideSelection) -> str:
    codes = _side_reason_codes(payload)
    return codes[0] if codes else ""


__all__ = [
    "EXTERNAL_STATUS_BLOCKED",
    "PLAN_ATTEMPT_IDENTITY_MISMATCH",
    "SideSelection",
    "finalize_canonical_result",
    "finalize_side_selection",
    "select_canonical_sides",
    "select_side_candidate",
]
