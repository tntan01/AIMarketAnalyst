"""Scanner execution readiness (Bước 08; target-only, not live-wired yet).

Execution readiness is a **consumer of the canonical decision**: it derives
``fresh_snapshot`` / ``can_execute`` from the Step 07 canonical decision codes
and never re-interprets raw actions or gates itself.  (the legacy path re-derived readiness
from scanner_action/gates; Bước 08 makes the decision block the single source.)

* ``fresh_snapshot`` — the canonical decision carries no freshness failure
  (``SNAPSHOT_STALE`` / ``SNAPSHOT_FRESHNESS_UNKNOWN`` are absent).
* ``can_execute`` — fresh *and* the canonical base status is not
  ``DATA_UNAVAILABLE``/``BLOCKED`` (a candidate can exist).
* ``prepared`` — set only once the candidate decision exists: prepared = the
  candidate reached ``READY_NOW``.  ``revalidation_required`` stays ``True``:
  a real order still requires execution revalidation at cutover (Bước 12).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import TYPE_CHECKING, Any, Mapping

from core.reason_codes import (
    SNAPSHOT_FRESHNESS_UNKNOWN,
    SNAPSHOT_STALE,
    EXECUTION_FRESH_OK,
    EXECUTION_NOT_READY,
    EXECUTION_REVALIDATION_REQUIRED,
    ORDER_NOT_PREPARED,
    ORDER_PREPARED,
)
from core.scanner_v4_models import BLOCKED, DATA_UNAVAILABLE, READY_NOW
from core.smc_readiness import SMC_STATUS_READY_NOW

# Task 109 reason codes owned here.
SMC_NOT_READY = "SMC_NOT_READY"
SMC_SELECTION_UNAVAILABLE = "SMC_SELECTION_UNAVAILABLE"

if TYPE_CHECKING:  # import guard: no runtime import cycles
    from core.scanner_candidate import ScannerV4CandidateDecision
    from core.scanner_composition import ScannerCompositionResult

FRESHNESS_FAILURE_CODES = frozenset({SNAPSHOT_STALE, SNAPSHOT_FRESHNESS_UNKNOWN})
_ORDER_PREPARED_CODES = frozenset({ORDER_PREPARED, ORDER_NOT_PREPARED})


@dataclass(frozen=True, slots=True)
class ExecutionReadiness:
    """Immutable readiness state derived from the canonical decision.

    ``prepared`` is ``None`` until the candidate decision exists; use
    ``with_candidate`` to attach the candidate outcome (the same evaluator
    collapses into a new frozen instance — never a mutation).
    """

    snapshot_id: str
    captured_at: datetime
    fresh_snapshot: bool
    can_execute: bool
    prepared: bool | None = None
    revalidation_required: bool = True
    reason_codes: tuple[str, ...] = ()

    def with_candidate(
        self, candidate: ScannerV4CandidateDecision | None
    ) -> ExecutionReadiness:
        """Attach the candidate outcome; ``prepared`` follows READY_NOW only.

        Calling twice is idempotent: the prepared-order code is *replaced*
        (never stacked), so a single readiness carries exactly one verdict.
        """
        prepared = (
            bool(self.can_execute)
            and candidate is not None
            and candidate.candidate_status == READY_NOW
        )
        base_codes = [c for c in self.reason_codes if c not in _ORDER_PREPARED_CODES]
        codes = base_codes + [ORDER_PREPARED if prepared else ORDER_NOT_PREPARED]
        return replace(self, prepared=prepared, reason_codes=tuple(codes))

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "captured_at": self.captured_at.isoformat(),
            "fresh_snapshot": self.fresh_snapshot,
            "can_execute": self.can_execute,
            "prepared": self.prepared,
            "revalidation_required": self.revalidation_required,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "execution") -> ExecutionReadiness:
        payload = _require_exact_keys(
            value,
            {
                "snapshot_id",
                "captured_at",
                "fresh_snapshot",
                "can_execute",
                "prepared",
                "revalidation_required",
                "reason_codes",
            },
            path,
        )
        return cls(
            snapshot_id=_require_text(payload["snapshot_id"], f"{path}.snapshot_id"),
            captured_at=_require_datetime(payload["captured_at"], f"{path}.captured_at"),
            fresh_snapshot=bool(payload["fresh_snapshot"]),
            can_execute=bool(payload["can_execute"]),
            prepared=(
                None
                if payload["prepared"] is None
                else bool(payload["prepared"])
            ),
            revalidation_required=bool(payload["revalidation_required"]),
            reason_codes=_parse_reason_codes(payload["reason_codes"], f"{path}.reason_codes"),
        )


def _require_exact_keys(value: object, expected: set[str], path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"EXECUTION_READINESS_INVALID at {path}: expected a mapping")
    actual = frozenset(value)
    if actual != frozenset(expected):
        raise ValueError(
            f"EXECUTION_READINESS_INVALID at {path}: "
            f"expected exactly {sorted(expected)}, got {sorted(actual)}"
        )
    return value


def _require_text(value: object, path: str) -> str:
    if type(value) is not str:
        raise ValueError(f"EXECUTION_READINESS_INVALID at {path}: expected a string")
    return value


def _require_datetime(value: object, path: str) -> datetime:
    if type(value) is datetime:
        return value
    if type(value) is not str:
        raise ValueError(f"EXECUTION_READINESS_INVALID at {path}: expected ISO datetime")
    try:
        return datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(
            f"EXECUTION_READINESS_INVALID at {path}: invalid ISO datetime: {exc}"
        ) from exc


def _parse_reason_codes(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"EXECUTION_READINESS_INVALID at {path}: expected a list of reason codes"
        )
    codes: list[str] = []
    for index, item in enumerate(value):
        if type(item) is not str or not item:
            raise ValueError(f"EXECUTION_READINESS_INVALID at {path}[{index}]: bad code")
        if item not in codes:
            codes.append(item)
    return tuple(codes)


def evaluate_execution_readiness(
    composition: ScannerCompositionResult,
) -> ExecutionReadiness:
    """Evaluate readiness from the canonical decision — never from raw gates.

    Deterministic: depends only on the composition result (decisions already
    stamped the freshness codes), not on the evaluation wall clock.

    Task 109: the SMC readiness verdict of the SELECTED side is applied on top
    of the existing execution conditions.  SMC readiness can only ever LOWER
    the verdict — a high SMC quality never overrides invalidation, a missing
    confirmation or the market/account/risk/safety gates, and no SMC state can
    grant execution on its own.
    """
    reason_codes = composition.decision.reason_codes
    fresh = not bool(FRESHNESS_FAILURE_CODES.intersection(reason_codes))
    base = composition.decision.candidate_status
    can_execute = fresh and base not in (DATA_UNAVAILABLE, BLOCKED)

    smc_status, smc_codes = _selected_smc_readiness(composition)
    smc_ready = smc_status == SMC_STATUS_READY_NOW
    if not smc_ready:
        can_execute = False

    codes: list[str] = []
    if fresh:
        codes.append(EXECUTION_FRESH_OK)
    if not can_execute:
        codes.append(EXECUTION_NOT_READY)
    codes.append(EXECUTION_REVALIDATION_REQUIRED)
    codes.extend(smc_codes)
    # Keep the underlying freshness failure codes so the trace stays complete.
    codes.extend(sorted(c for c in FRESHNESS_FAILURE_CODES if c in reason_codes))

    return ExecutionReadiness(
        snapshot_id=composition.snapshot_id,
        captured_at=composition.captured_at,
        fresh_snapshot=fresh,
        can_execute=can_execute,
        prepared=None,
        reason_codes=tuple(dict.fromkeys(codes)),
    )


def _selected_smc_readiness(
    composition: ScannerCompositionResult,
) -> tuple[str | None, tuple[str, ...]]:
    """SMC readiness of the side the composition actually selected.

    Task 108/109: the verdict is READ from the canonical summary the
    composition copied out of the final selection — it is never re-derived from
    the raw SMC context, and a composition whose selected side carries no
    canonical summary is refused (fail closed) instead of being read as ready.
    """

    side = _selected_side(composition)
    if side is None:
        return None, ()
    canonical = getattr(composition, "canonical", None)
    summary = None
    for side_score in getattr(canonical, "side_scores", ()) or ():
        if getattr(side_score, "side", None) == side:
            summary = side_score.smc_selection
            break
    if not isinstance(summary, Mapping):
        return None, (SMC_SELECTION_UNAVAILABLE,)
    status = summary.get("readiness_status")
    if not isinstance(status, str) or not status:
        return None, (SMC_SELECTION_UNAVAILABLE,)
    if status == SMC_STATUS_READY_NOW:
        return status, ()
    return status, (SMC_NOT_READY, f"SMC_READINESS_{status}")


def _selected_side(composition: ScannerCompositionResult) -> str | None:
    side = getattr(composition.decision, "selected_side", None)
    if side in ("buy", "sell"):
        return side
    scenario = getattr(composition, "scenario", None)
    side = getattr(scenario, "side", None)
    return side if side in ("buy", "sell") else None