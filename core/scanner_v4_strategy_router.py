"""Scanner strategy router (Bước 08; target-only, not live-wired yet).

The router is the fail-closed gateway in front of the decision path:

* it reads ONLY the Step 07 canonical output — side scores, gates and the
  locked versions (``composition_version`` + the canonical snapshot's own
  version fields);
* a legacy payload, a missing/mismatched version, or any forbidden legacy field
  (``total``, ``best_score``, top-level legacy score, ``scanner_action``, etc.)
  returns ``version_mismatch`` **before anything executes** — there is no
  fallback that lets a legacy artifact enter the path;
* a routed result never executes a real order at Bước 08 (``executed=False``).

``route_scanner`` accepts either the typed ``ScannerCompositionResult`` or
its strict JSON dict.  Every dict is deep-validated via the exact-key readers
and ``deserialize_canonical_pair_snapshot`` (which itself refuses legacy artifacts).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.reason_codes import (
    SCANNER_FORBIDDEN_SCORED_FIELD,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)
from core.scanner_candidate import (
    ScannerV4CandidateDecision,
)
from core.scanner_composition import (
    COMPOSITION_POLICY_VERSION,
    COMPOSITION_POLICY_LEGACY_VERSION,
    ScannerCompositionResult,
)
from core.scanner_execution_readiness import (
    ExecutionReadiness,
    evaluate_execution_readiness,
)
from core.scanner_threshold_policy import ThresholdPolicy

# Top-level legacy fields that must never co-exist with a route.  The
# decision reads only canonical side_scores/gates/versions; these keys are
# legacy-era 「opportunity/total/best」 aggregations with their own owners.
FORBIDDEN_LEGACY_KEYS = frozenset(
    {
        "total",
        "best_score",
        "final_score",
        "opportunity_score",
        "scanner_action",
        "scanner_group",
        "expected_effective_rr",
        "risk_condition",
        "macro_alignment",
    }
)

_COMPOSITION_ENVELOPE_KEYS = frozenset(
    {
        "composition_version",
        "snapshot_id",
        "symbol",
        "captured_at",
        "capture_source",
        "technical",
        "technical_errors",
        "safety",
        "macro_assessment",
        "macro_gate",
        "scenario",
        "final_scores",
        "composition_gates",
        "decision",
        "canonical",
    }
)

ROUTE_ROUTED = "routed"
ROUTE_VERSION_MISMATCH = "version_mismatch"
ROUTE_INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class RoutedCandidate:
    """Fail-closed routing outcome; a real order is NEVER executed at Bước 08."""

    route_status: str
    candidate: ScannerV4CandidateDecision | None
    executed: bool = False
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.route_status not in (ROUTE_ROUTED, ROUTE_VERSION_MISMATCH, ROUTE_INVALID):
            raise ValueError(f"invalid route_status {self.route_status!r}")
        if self.executed is not False:
            raise ValueError(
                "Step 08 never executes a real order; executed must be False"
            )
        if self.route_status == ROUTE_ROUTED and self.candidate is None:
            raise ValueError("a routed outcome requires a candidate decision")
        if self.route_status != ROUTE_ROUTED and self.candidate is not None:
            raise ValueError("a refused outcome must not carry a candidate")

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_status": self.route_status,
            "candidate": (
                None if self.candidate is None else self.candidate.to_dict()
            ),
            "executed": self.executed,
            "reason_codes": list(self.reason_codes),
        }


def _mismatch(code: str) -> RoutedCandidate:
    return RoutedCandidate(
        route_status=ROUTE_VERSION_MISMATCH,
        candidate=None,
        reason_codes=(code,),
    )


def route_scanner(
    payload: object,
    *,
    thresholds: ThresholdPolicy,
    entry_confirmation: str,
    proximity: float | None = None,
) -> RoutedCandidate:
    """Route a composition artifact into the single decision path.

    Fail-closed: any shape/version/legacy doubt yields ``version_mismatch``
    before the decision layer runs.  Execution readiness is ALWAYS evaluated
    fresh from the canonical decision (Bước 12 §12.1) — there is no caller-
    supplied ``execution`` override, so revalidation cannot be bypassed here.
    """
    if not isinstance(payload, (ScannerCompositionResult, Mapping)):
        return _mismatch(SCANNER_SCHEMA_INVALID)

    if isinstance(payload, ScannerCompositionResult):
        composition = payload
    else:
        payload_mapping = _require_mapping(payload)
        legacy = sorted(FORBIDDEN_LEGACY_KEYS.intersection(payload_mapping))
        if legacy:
            return RoutedCandidate(
                route_status=ROUTE_VERSION_MISMATCH,
                candidate=None,
                reason_codes=(SCANNER_FORBIDDEN_SCORED_FIELD, *legacy),
            )
        if frozenset(payload_mapping) != _COMPOSITION_ENVELOPE_KEYS:
            return _mismatch(SCANNER_VERSION_MISMATCH)
        if payload_mapping.get("composition_version") not in (COMPOSITION_POLICY_VERSION, COMPOSITION_POLICY_LEGACY_VERSION):
            return _mismatch(SCANNER_VERSION_MISMATCH)
        if type(payload_mapping.get("canonical")) is not dict:
            return _mismatch(SCANNER_VERSION_MISMATCH)
        try:
            composition = ScannerCompositionResult.from_dict(payload)
        except ValueError as exc:
            code = getattr(exc, "code", None) or SCANNER_VERSION_MISMATCH
            if code in {
                SCANNER_VERSION_MISMATCH,
                SCANNER_VERSION_MISSING,
                SCANNER_LEGACY_V3_AUDIT_ONLY,
                SCANNER_FORBIDDEN_SCORED_FIELD,
            }:
                return _mismatch(code)
            return _mismatch(SCANNER_SCHEMA_INVALID)

    readiness = evaluate_execution_readiness(composition)
    candidate = build_candidate_with(
        composition=composition,
        thresholds=thresholds,
        entry_confirmation=entry_confirmation,
        execution=readiness,
        proximity=proximity,
    )
    return RoutedCandidate(
        route_status=ROUTE_ROUTED,
        candidate=candidate,
        reason_codes=candidate.reason_codes,
    )


def _require_mapping(value: object) -> Mapping[str, Any]:
    from core.scanner_composition import CompositionInputError  # local import

    if type(value) is not dict:
        raise CompositionInputError("router.payload", "expected a mapping")
    return value


# import at module bottom to avoid a circular import at module load
from core.scanner_candidate import build_candidate as build_candidate_with  # noqa: E402