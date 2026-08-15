"""Scanner V4 observability (Bước 10; target-only).

10E — telemetry for the V4 consumer layer that traces the *canonical* pipeline
without ever re-scoring:

* **per-side technical raw/scaled components** + the evidence / execution
  fallback source (``FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK`` /
  ``FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK``) and any ``FINAL_SCORE_DATA_*``
  status;
* **per-safety-sub-gate status** (connectivity/data/spread/news/volatility) and
  the macro gate status with its ``decision_cap``;
* every **UNKNOWN reason** seen (gates that fail closed), plus the
  ``decision_cap`` and full version identity;
* **counters**: candidate distribution by status, gate-status counters
  (PASS/CAUTION/BLOCK/UNKNOWN across all gate cards), neutral-fallback counter
  and blocked-high-score counter (a candidate that is BLOCKED/DATA_UNAVAILABLE
  while its selected technical score is at/above the given floor).

There is intentionally **no V3/V4 disagreement metric**: V3 and V4 telemetry
are separate canvases until cutover.

The module also carries a deterministic session-review tracer that consumes
canonical candidate statuses (see ``core/scanner_v4_session_review.py``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from core.reason_codes import (
    FINAL_SCORE_DATA_UNAVAILABLE,
    FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,
    FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK,
    TECHNICAL_DATA_UNAVAILABLE,
)
from core.scanner_v4_composition import (
    COMPOSITION_POLICY_VERSION,
    ScannerV4CompositionResult,
)
from core.scanner_v4_models import (
    BLOCK,
    BLOCKED,
    BUY,
    CAUTION,
    DATA_UNAVAILABLE,
    PASS,
    SELL,
    UNKNOWN,
    VALID_CANDIDATE_STATUSES,
    VALID_GATE_STATUSES,
)

SCANNER_V4_OBSERVABILITY_VERSION = "scanner-observability-v4"

# Order of gate cards used for the status counters (canonical + macro).
_GATE_CARD_NAMES = (
    "market_safety.connectivity",
    "market_safety.data",
    "market_safety.spread",
    "market_safety.news",
    "market_safety.volatility",
    "macro",
    "scenario",
    "account",
    "portfolio",
    "journal",
)


@dataclass(frozen=True, slots=True)
class TechnicalTrace:
    side: str
    components: tuple[dict[str, Any], ...]  # name/raw/raw_max/weight/contribution/scaled
    fallback_evidence: bool
    fallback_execution: bool
    technical_unavailable: bool
    final_score_data_error: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "components": list(self.components),
            "fallback_evidence": self.fallback_evidence,
            "fallback_execution": self.fallback_execution,
            "technical_unavailable": self.technical_unavailable,
            "final_score_data_error": self.final_score_data_error,
        }


@dataclass(frozen=True, slots=True)
class ObserverCounters:
    candidates_by_status: dict[str, int]
    gate_status: dict[str, int]
    neutral_fallback_count: int
    blocked_high_score_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidates_by_status": dict(self.candidates_by_status),
            "gate_status": dict(self.gate_status),
            "neutral_fallback_count": self.neutral_fallback_count,
            "blocked_high_score_count": self.blocked_high_score_count,
        }


@dataclass(frozen=True, slots=True)
class ScannerV4ObservabilityDocument:
    observability_version: str
    composition_version: str
    snapshot_id: str
    symbol: str
    captured_at: str
    capture_source: str
    candidate_status: str
    selected_side: str | None
    decision_cap: str | None
    versions: Mapping[str, Any]
    technical: tuple[TechnicalTrace, ...]
    gate_trace: tuple[dict[str, Any], ...]
    unknown_reasons: tuple[str, ...]
    counters: ObserverCounters

    def to_dict(self) -> dict[str, Any]:
        return {
            "observability_version": self.observability_version,
            "composition_version": self.composition_version,
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "captured_at": self.captured_at,
            "capture_source": self.capture_source,
            "candidate_status": self.candidate_status,
            "selected_side": self.selected_side,
            "decision_cap": self.decision_cap,
            "versions": dict(self.versions),
            "technical": [t.to_dict() for t in self.technical],
            "gate_trace": list(self.gate_trace),
            "unknown_reasons": list(self.unknown_reasons),
            "counters": self.counters.to_dict(),
        }


def build_v4_observability_document(
    composition: ScannerV4CompositionResult,
    *,
    samples: list[ScannerV4CompositionResult] | None = None,
    blocked_high_score_floor: int = 40,
) -> ScannerV4ObservabilityDocument:
    """Build the target-only V4 observability document for one composition.

    Inputs are the canonical composition (and optional extra composition samples
    for the status distribution); nothing is re-scored.
    """
    if type(composition) is not ScannerV4CompositionResult:
        raise TypeError("expected a ScannerV4CompositionResult")
    canonical = composition.canonical

    technical_traces: list[TechnicalTrace] = []
    for side in (BUY, SELL):
        score = canonical.side_score(side)
        reason_codes = score.reason_codes
        components: list[dict[str, Any]] = []
        bd = score.technical_breakdown
        for name, comp in (
            ("trend", bd.trend),
            ("momentum", bd.momentum),
            ("location", bd.location),
            ("smc", bd.smc),
        ):
            components.append(
                {
                    "name": name,
                    "raw": comp.raw,
                    "raw_max": comp.raw_max,
                    "weight": comp.weight,
                    "contribution": comp.contribution,
                }
            )
        # Fallback/error source lives on the canonical side score (which carries
        # the FinalScore fallback warnings); the composition never re-scores.
        evidence_fallback = bool(
            FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK in reason_codes
        )
        execution_fallback = bool(
            FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK in reason_codes
        )
        final_error = bool(FINAL_SCORE_DATA_UNAVAILABLE in reason_codes)
        technical_unavailable = bool(
            score.technical_signal_score is None
            or TECHNICAL_DATA_UNAVAILABLE in reason_codes
        )
        technical_traces.append(
            TechnicalTrace(
                side=side,
                components=tuple(components),
                fallback_evidence=evidence_fallback,
                fallback_execution=execution_fallback,
                technical_unavailable=technical_unavailable,
                final_score_data_error=final_error,
            )
        )

    gate_trace: list[dict[str, Any]] = []
    for check in canonical.market_safety.checks:
        gate_trace.append(
            {
                "name": f"market_safety.{check.name}",
                "status": check.status,
                "reason_codes": list(check.reason_codes),
            }
        )
    gate_trace.append(
        {
            "name": "macro",
            "status": canonical.macro_gate.status,
            "decision_cap": canonical.macro_gate.decision_cap,
            "reason_codes": list(canonical.macro_gate.reason_codes),
        }
    )
    for gate in composition.composition_gates:
        gate_trace.append(
            {
                "name": gate.name,
                "status": gate.status,
                "reason_codes": list(gate.reason_codes),
            }
        )

    unknown_reasons = _collect_unknown_reason_codes(composition)

    counters = _build_counters(
        composition=composition,
        samples=samples or (),
        blocked_high_score_floor=blocked_high_score_floor,
    )

    return ScannerV4ObservabilityDocument(
        observability_version=SCANNER_V4_OBSERVABILITY_VERSION,
        composition_version=COMPOSITION_POLICY_VERSION,
        snapshot_id=canonical.snapshot_id,
        symbol=canonical.symbol,
        captured_at=canonical.captured_at.isoformat(),
        capture_source=composition.capture_source,
        candidate_status=composition.decision.candidate_status,
        selected_side=composition.decision.selected_side,
        decision_cap=composition.decision.decision_cap,
        versions={
            "scoring_version": canonical.scoring_version,
            "feature_version": canonical.feature_version,
            "output_schema_version": canonical.output_schema_version,
            "safety_policy_version": canonical.safety_policy_version,
            "macro_policy_version": canonical.macro_policy_version,
            "snapshot_version": canonical.snapshot_version,
            "composition_version": COMPOSITION_POLICY_VERSION,
        },
        technical=tuple(technical_traces),
        gate_trace=tuple(gate_trace),
        unknown_reasons=tuple(unknown_reasons),
        counters=counters,
    )


def _collect_unknown_reason_codes(composition: ScannerV4CompositionResult) -> list[str]:
    """Every reason code attached to an UNKNOWN gate (fail-closed evidence)."""
    reasons: list[str] = []
    seen: set[str] = set()

    def _add(codes: Any) -> None:
        if codes is None:
            return
        for code in codes:
            if code and code not in seen:
                seen.add(code)
                reasons.append(code)

    canonical = composition.canonical
    for check in canonical.market_safety.checks:
        if check.status == UNKNOWN:
            _add(check.reason_codes)
    if canonical.macro_gate.status == UNKNOWN:
        _add(canonical.macro_gate.reason_codes)
    for gate in composition.composition_gates:
        if gate.status == UNKNOWN:
            _add(gate.reason_codes)
    if composition.decision.decision_cap is not None:
        _add([composition.decision.decision_cap])
    return reasons


def _build_counters(
    *,
    composition: ScannerV4CompositionResult,
    samples: tuple[ScannerV4CompositionResult, ...],
    blocked_high_score_floor: int,
) -> ObserverCounters:
    status_counters: dict[str, int] = {}
    gate_status: dict[str, int] = dict.fromkeys(VALID_GATE_STATUSES, 0)

    all_compositions: list[ScannerV4CompositionResult] = [composition]
    for item in samples:
        if type(item) is ScannerV4CompositionResult:
            all_compositions.append(item)

    for comp in all_compositions:
        status = comp.decision.candidate_status
        status_counters[status] = status_counters.get(status, 0) + 1
        canonical = comp.canonical
        for check in canonical.market_safety.checks:
            gate_status[check.status] += 1
        gate_status[canonical.macro_gate.status] += 1
        for gate in comp.composition_gates:
            gate_status[gate.status] += 1

    # candidate distribution should list every valid status (zero counts kept).
    ordered_statuses = {status: status_counters.get(status, 0) for status in VALID_CANDIDATE_STATUSES}
    candidates_by_status = {
        status: ordered_statuses[status] for status in VALID_CANDIDATE_STATUSES
    }

    neutral_fallback_count = 0
    blocked_high_score_count = 0
    for comp in all_compositions:
        for side in (BUY, SELL):
            sc = comp.canonical.side_score(side)
            if any(
                code in sc.reason_codes
                for code in (
                    FINAL_SCORE_EVIDENCE_NEUTRAL_FALLBACK,
                    FINAL_SCORE_EXECUTION_NEUTRAL_FALLBACK,
                )
            ):
                neutral_fallback_count += 1
        selected = comp.decision.selected_side
        status = comp.decision.candidate_status
        if status in (BLOCKED, DATA_UNAVAILABLE) and selected is not None:
            selected_score: int | None = None
            for score in comp.canonical.side_scores:
                if score.side == selected:
                    selected_score = score.setup_score or score.technical_signal_score
                    break
            if selected_score is not None and selected_score >= blocked_high_score_floor:
                blocked_high_score_count += 1

    return ObserverCounters(
        candidates_by_status=candidates_by_status,
        gate_status=gate_status,
        neutral_fallback_count=neutral_fallback_count,
        blocked_high_score_count=blocked_high_score_count,
    )


# ---------------------------------------------------------------------------
# Static checks used by tests (10E: telemetry shape)
# ---------------------------------------------------------------------------


def has_required_trace_keys(document: Mapping[str, Any]) -> bool:
    """True when the document carries the full telemetry acceptance surface."""
    required = {
        "observability_version",
        "composition_version",
        "snapshot_id",
        "symbol",
        "captured_at",
        "capture_source",
        "candidate_status",
        "selected_side",
        "decision_cap",
        "versions",
        "technical",
        "gate_trace",
        "unknown_reasons",
        "counters",
    }
    return required.issubset(set(document))


def has_no_v3_disagreement_metric(document: Mapping[str, Any]) -> bool:
    """Contract: no V3/V4 disagreement metric is ever produced."""
    for key in document:
        if "disagreement" in str(key).lower() or "v3_vs_v4" in str(key).lower():
            return False
    return True