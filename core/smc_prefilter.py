"""Auditable, fail-open decisions for Scanner SMC fast paths.

This module deliberately has no routing side effects.  It consumes the SAME
frozen snapshot and the SAME canonical evaluation the full route would produce,
so a Tier-1 reject is a statement about the canonical verdict and never about a
second scoring rule.

Task 104 rules:

* the evaluation is REUSED, never rebuilt — the prefilter returns the
  ``SmcEvaluation`` it made so the full route does not score the same snapshot
  twice;
* a side that is merely waiting for its M15 confirmation is NOT rejected: it is
  a valid watch/setup state, and M15 owns readiness only;
* "no usable setup on either side" (an evaluated, concluded empty) is the only
  reason to reject on SMC grounds;
* core data that could not be concluded is a FAIL-CLOSED rejection with
  ``SMC_CORE_DATA_UNAVAILABLE`` — it is never reported as "no setup", because
  the two mean different things and only the second one was evaluated;
* a schema/numeric problem in the snapshot fails open so the caller can run the
  existing full path and report its own error.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Mapping, Sequence

from core.smc_scoring_result import (
    SELECTION_STATE_DATA_UNAVAILABLE,
    SELECTION_STATE_EVALUATED,
    SELECTION_STATE_WATCH_ZONE,
)
from core.smc_snapshot import SmcSnapshotEvaluation, SmcSnapshotInput, evaluate_smc_snapshot

SMC_PREFILTER_VERSION = "smc-prefilter-v2"
SCANNER_FAST_PATH_VERSION = "scanner-fast-path-v1"

STAGE_PRE_SMC = "pre_smc"
STAGE_POST_CONTEXT = "post_context"

NO_RAW_SMC_CANDIDATE = "NO_RAW_SMC_CANDIDATE"
NO_ACTIONABLE_SMC_ZONE = "NO_ACTIONABLE_SMC_ZONE"
SMC_PREFILTER_ERROR_FAIL_OPEN = "SMC_PREFILTER_ERROR_FAIL_OPEN"
SMC_SCORING_ERROR = "SMC_SCORING_ERROR"
# The canonical core-data verdict (data spec §6): the snapshot itself could not
# be concluded, so no setup exists to accept OR reject on its merits.
SMC_CORE_DATA_UNAVAILABLE = "SMC_CORE_DATA_UNAVAILABLE"

# Selection states that still carry a usable selected zone for the side.
_ACTIONABLE_STATES = frozenset({
    SELECTION_STATE_EVALUATED,
    SELECTION_STATE_WATCH_ZONE,
})


def evaluate_post_context_prefilter(
    *,
    snapshot: SmcSnapshotInput | None,
    min_rr: Any | None = None,
    external_status: Mapping[str, str] | None = None,
    external_reason_codes: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Return the canonical Tier-1 decision for one frozen snapshot.

    A reject is allowed only after the canonical chain concluded that neither
    side carries a usable setup, or that the core data was unavailable.  Any
    other problem fails open so the caller can run the full route and report it.
    """

    decision = _base_decision(raw_counts=_raw_counts(snapshot))
    if not _snapshot_is_frozen(snapshot):
        # The snapshot could not even be frozen (no cutoff, no context): the
        # full route owns the explicit data-error report, so fail open here.
        # A core-data verdict *inside* a frozen snapshot is different — see
        # ``SMC_CORE_DATA_UNAVAILABLE`` below.
        return _fail_open(decision)
    if not _is_evaluable_snapshot(snapshot):
        # The snapshot exists but cannot support the canonical measurement (no
        # price/ATR, or a timeframe group that is not a context).  Rejecting
        # here would claim "evaluated, nothing found", which is false — the
        # full route reports the real error instead.
        return _fail_open(decision)

    try:
        evaluation = evaluate_smc_snapshot(
            snapshot,
            min_rr=min_rr,
            external_status=external_status,
            external_reason_codes=external_reason_codes,
        )
    except Exception:
        # A chain exception is fail-closed: block the analysis instead of
        # retrying the full route or falling back to another scorer.
        decision["should_reject"] = True
        decision["reason_code"] = SMC_SCORING_ERROR
        decision["fail_open"] = False
        decision["scorer_error"] = True
        return decision

    decision["precomputed_smc"] = evaluation.result
    decision["precomputed_evaluation"] = evaluation
    decision["selected_zone_ids"] = _selected_zone_ids(evaluation)

    # A reject is only ever about the WHOLE snapshot: as long as one side
    # carries a usable setup, the other side's state (unavailable included) is
    # that side's own business and must not cancel it.
    if _actionable_sides(evaluation):
        return decision

    unavailable = _unavailable_sides(evaluation)
    if unavailable:
        decision["should_reject"] = True
        decision["reason_code"] = SMC_CORE_DATA_UNAVAILABLE
        decision["core_unavailable_sides"] = unavailable
        return decision

    decision["should_reject"] = True
    decision["reason_code"] = NO_ACTIONABLE_SMC_ZONE
    return decision


def _snapshot_is_frozen(snapshot: Any) -> bool:
    """Whether the snapshot seam produced a usable frozen input at all."""

    return (
        isinstance(snapshot, SmcSnapshotInput)
        and snapshot.as_of is not None
        and isinstance(snapshot.smc, Mapping)
        and isinstance(snapshot.technical, Mapping)
    )


def _is_evaluable_snapshot(snapshot: SmcSnapshotInput) -> bool:
    """Whether the canonical chain can actually conclude for this snapshot.

    The Tier-1 reject is only trustworthy when the evaluator had what it needs:
    a positive price and execution ATR (the geometry/distance reference) and a
    context carrying the three core timeframes.  Anything less fails open so the
    full route reports its own explicit error instead of a fabricated
    "no setup".
    """

    technical = snapshot.technical if isinstance(snapshot.technical, Mapping) else {}
    if not _positive_finite(technical.get("price")):
        return False
    if not _positive_finite(technical.get("atr_h4") or technical.get("atr_d1")):
        return False
    context = snapshot.smc if isinstance(snapshot.smc, Mapping) else {}
    return all(
        isinstance(context.get(timeframe), Mapping) for timeframe in _TIMEFRAMES
    )


def _positive_finite(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return False
    return isfinite(number) and number > 0


def _base_decision(
    *,
    raw_counts: dict[str, dict[str, int]],
) -> dict[str, Any]:
    return {
        "should_reject": False,
        "stage": STAGE_POST_CONTEXT,
        "reason_code": "",
        "prefilter_version": SMC_PREFILTER_VERSION,
        "fast_path_version": SCANNER_FAST_PATH_VERSION,
        "raw_counts": raw_counts,
        "selected_zone_ids": {"buy": None, "sell": None},
        "fail_open": False,
        # The full route reuses this payload instead of invoking the canonical
        # chain a second time for symbols that remain on the full route.
        "precomputed_smc": None,
        "precomputed_evaluation": None,
    }


def _fail_open(decision: dict[str, Any]) -> dict[str, Any]:
    decision["fail_open"] = True
    decision["reason_code"] = SMC_PREFILTER_ERROR_FAIL_OPEN
    return decision


def _unavailable_sides(evaluation: SmcSnapshotEvaluation) -> list[str]:
    """Sides the canonical chain could not conclude (core data unavailable)."""

    return [
        side
        for side in ("buy", "sell")
        if _state(evaluation, side) == SELECTION_STATE_DATA_UNAVAILABLE
    ]


def _actionable_sides(evaluation: SmcSnapshotEvaluation) -> list[str]:
    """Sides that still carry a usable selected zone (plan or watch)."""

    return [
        side
        for side in ("buy", "sell")
        if _state(evaluation, side) in _ACTIONABLE_STATES
        and _zone_id(evaluation, side) is not None
    ]


def _state(evaluation: SmcSnapshotEvaluation, side: str) -> str:
    selection = evaluation.selection(side)
    return selection.state if selection is not None else ""


def _zone_id(evaluation: SmcSnapshotEvaluation, side: str) -> str | None:
    selection = evaluation.selection(side)
    return selection.selected_zone_id if selection is not None else None


def _raw_counts(snapshot: Any) -> dict[str, dict[str, int]]:
    """Candidate counts per timeframe/family, read from the frozen context."""

    context = snapshot.smc if isinstance(snapshot, SmcSnapshotInput) else None
    source = context if isinstance(context, Mapping) else {}
    counts: dict[str, dict[str, int]] = {}
    for timeframe in ("H4", "H1"):
        timeframe_data = source.get(timeframe)
        timeframe_data = timeframe_data if isinstance(timeframe_data, dict) else {}
        counts[timeframe] = {
            family: len(timeframe_data.get(key, []))
            if isinstance(timeframe_data.get(key, []), list)
            else 0
            for family, key in _RAW_FAMILIES.items()
        }
    return counts


_TIMEFRAMES = ("H4", "H1")
_RAW_FAMILIES = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}


def _selected_zone_ids(evaluation: SmcSnapshotEvaluation) -> dict[str, str | None]:
    return {side: _zone_id(evaluation, side) for side in ("buy", "sell")}


__all__ = [
    "NO_ACTIONABLE_SMC_ZONE",
    "NO_RAW_SMC_CANDIDATE",
    "SCANNER_FAST_PATH_VERSION",
    "SMC_CORE_DATA_UNAVAILABLE",
    "SMC_PREFILTER_ERROR_FAIL_OPEN",
    "SMC_PREFILTER_VERSION",
    "SMC_SCORING_ERROR",
    "STAGE_POST_CONTEXT",
    "STAGE_PRE_SMC",
    "evaluate_post_context_prefilter",
]
