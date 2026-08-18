"""Scanner session review brief (Bước 10; target-only).

10E — deterministic session-review tracer that consumes **canonical** candidate
statuses only.  The brief is derived from ``ScannerObservabilityDocument``
documents (one per composition) and never re-scores, never reads legacy fields and
never produces a legacy/current disagreement metric (legacy and current remain separate canvases
until cutover).

The prompt is deterministic: no wall-clock timestamps, no counter randomness —
the same session (same set of observability documents, in the same order)
always produces the same brief.  ``reveal_session`` builds the human/LLM brief;
``session_summary`` returns the compact structural digest used for tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.scanner_v4_observability import (
    SCANNER_OBSERVABILITY_LEGACY_VERSION,
    SCANNER_V4_OBSERVABILITY_VERSION,
    ScannerObservabilityDocument,
    build_observability_document,
)
from core.scanner_v4_models import (
    BLOCK,
    CAUTION,
    PASS,
    UNKNOWN,
    VALID_CANDIDATE_STATUSES,
)

SCANNER_SESSION_REVIEW_VERSION = "scanner-session-review"
SCANNER_SESSION_REVIEW_LEGACY_VERSION = "scanner-session-review-v4"


def _require_observability_document(value: object) -> ScannerObservabilityDocument:
    if type(value) is not ScannerObservabilityDocument:
        raise TypeError(
            "expected ScannerObservabilityDocument; got "
            f"{type(value).__name__}"
        )
    if value.observability_version not in (SCANNER_V4_OBSERVABILITY_VERSION, SCANNER_OBSERVABILITY_LEGACY_VERSION):
        raise ValueError(
            f"observability version mismatch: {value.observability_version!r}"
        )
    return value


def _require_known_symbol(rows: list[ScannerObservabilityDocument]) -> None:
    symbols = {row.symbol for row in rows}
    if len(symbols) != 1:
        raise ValueError(f"session review refused mixed symbols: {sorted(symbols)}")


def reveal_session(
    rows: list[ScannerObservabilityDocument],
) -> str:
    """Deterministic AI-brief prompt over canonical observability documents.

    Consumers (the AI brief) read only canonical statuses / reasons / versions —
    never scores.  Mixed symbols are refused (a session is one pair).
    """
    docs = [_require_observability_document(row) for row in rows]
    if len(docs) == 0:
        raise ValueError("session review requires at least one observability document")
    _require_known_symbol(docs)
    summary = session_summary(docs)
    lines = [
        "# Scanner V4 — Session Review Brief",
        f"observability_version: {SCANNER_V4_OBSERVABILITY_VERSION}",
        f"composition_version: {summary.composition_versions[0]}",
        f"symbol: {summary.symbol}",
        f"candidate_count: {summary.candidate_count}",
        "statuses by candidate:",
    ]
    for status, count in summary.candidates_by_status.items():
        lines.append(f"  - {status}: {count}")
    lines.append("gate statuses (PASS/CAUTION/BLOCK/UNKNOWN):")
    for status in (PASS, CAUTION, BLOCK, UNKNOWN):
        lines.append(f"  - {status}: {summary.gate_status.get(status, 0)}")
    lines.append("unknown reasons with their gate sources:")
    for reason in summary.unknown_reasons:
        lines.append(f"  - {reason}")
    lines.append("sources observed:")
    lines.extend(f"  - {source}" for source in summary.capture_sources)
    lines.extend(
        (
            "version identities:",
            f"  - scoring: {summary.scoring_versions[0]}",
            f"  - feature: {summary.feature_versions[0]}",
            f"  - safety_policy: {summary.safety_policy_versions[0]}",
            f"  - macro_policy: {summary.macro_policy_versions[0]}",
            f"  - output_schema: {summary.output_schema_versions[0]}",
        )
    )
    lines.append(f"decision caps: {summary.decision_caps}")
    lines.append(f"evidence fallbacks: {summary.evidence_fallbacks}")
    lines.append(f"execution fallbacks: {summary.execution_fallbacks}")
    lines.append(f"blocked high-score candidates: {summary.blocked_high_score_candidates}")
    lines.append("Canonical-only: this brief never re-scores and never mixes V3/V4.")
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class SessionReviewSummary:
    symbol: str
    candidate_count: int
    candidates_by_status: dict[str, int]
    gate_status: dict[str, int]
    unknown_reasons: tuple[str, ...]
    capture_sources: tuple[str, ...]
    scoring_versions: tuple[str, ...]
    feature_versions: tuple[str, ...]
    safety_policy_versions: tuple[str, ...]
    macro_policy_versions: tuple[str, ...]
    output_schema_versions: tuple[str, ...]
    composition_versions: tuple[str, ...]
    decision_caps: tuple[str, ...]
    evidence_fallbacks: int
    execution_fallbacks: int
    blocked_high_score_candidates: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "candidate_count": self.candidate_count,
            "candidates_by_status": dict(self.candidates_by_status),
            "gate_status": dict(self.gate_status),
            "unknown_reasons": list(self.unknown_reasons),
            "capture_sources": list(self.capture_sources),
            "scoring_versions": list(self.scoring_versions),
            "feature_versions": list(self.feature_versions),
            "safety_policy_versions": list(self.safety_policy_versions),
            "macro_policy_versions": list(self.macro_policy_versions),
            "output_schema_versions": list(self.output_schema_versions),
            "composition_versions": list(self.composition_versions),
            "decision_caps": list(self.decision_caps),
            "evidence_fallbacks": self.evidence_fallbacks,
            "execution_fallbacks": self.execution_fallbacks,
            "blocked_high_score_candidates": self.blocked_high_score_candidates,
        }


def session_summary(
    docs: list[ScannerObservabilityDocument],
) -> SessionReviewSummary:
    """Compact structural digest of a session — test-friendly, deterministic.

    Aggregates only canonical statuses / version identities / reason codes;
    reading it never re-scores and never reads legacy fields.  ``comparisons`` /
    ``candidate`` can be passed from a live session without altering determinism.
    """
    rows = [_require_observability_document(doc) for doc in docs]
    if not rows:
        raise ValueError("session review requires at least one observability document")

    symbol = rows[0].symbol
    versions: dict[str, set[str]] = {
        key: set() for key in (
            "scoring_versions",
            "feature_versions",
            "safety_policy_versions",
            "macro_policy_versions",
            "output_schema_versions",
            "composition_versions",
        )
    }
    statuses: dict[str, int] = dict.fromkeys(VALID_CANDIDATE_STATUSES, 0)
    gate_status: dict[str, int] = {}
    unknown: set[str] = set()
    caps: set[str] = set()
    sources: set[str] = set()
    evidence_fallbacks = 0
    execution_fallbacks = 0
    blocked_high_score = 0

    for doc in rows:
        if doc.symbol != symbol:
            raise ValueError(f"session review refused mixed symbols: {symbol} vs {doc.symbol}")
        statuses[doc.candidate_status] = statuses.get(doc.candidate_status, 0) + 1
        versions["scoring_versions"].add(doc.versions["scoring_version"])
        versions["feature_versions"].add(doc.versions["feature_version"])
        versions["safety_policy_versions"].add(doc.versions["safety_policy_version"])
        versions["macro_policy_versions"].add(doc.versions["macro_policy_version"])
        versions["output_schema_versions"].add(doc.versions["output_schema_version"])
        versions["composition_versions"].add(doc.composition_version)
        for entry in doc.gate_trace:
            status = entry.get("status")
            if status in (PASS, CAUTION, BLOCK, UNKNOWN):
                gate_status[status] = gate_status.get(status, 0) + 1
        unknown.update(doc.unknown_reasons)
        sources.add(doc.capture_source)
        if doc.decision_cap is not None:
            caps.add(doc.decision_cap)
        for trace in doc.technical:
            if trace.fallback_evidence:
                evidence_fallbacks += 1
            if trace.fallback_execution:
                execution_fallbacks += 1
        blocked_high_score += doc.counters.blocked_high_score_count

    return SessionReviewSummary(
        symbol=symbol,
        candidate_count=len(rows),
        candidates_by_status=dict(statuses),
        gate_status=gate_status,
        unknown_reasons=tuple(sorted(unknown)),
        capture_sources=tuple(sorted(sources)),
        scoring_versions=tuple(sorted(versions["scoring_versions"])),
        feature_versions=tuple(sorted(versions["feature_versions"])),
        safety_policy_versions=tuple(sorted(versions["safety_policy_versions"])),
        macro_policy_versions=tuple(sorted(versions["macro_policy_versions"])),
        output_schema_versions=tuple(sorted(versions["output_schema_versions"])),
        composition_versions=tuple(sorted(versions["composition_versions"])),
        decision_caps=tuple(sorted(caps)),
        evidence_fallbacks=evidence_fallbacks,
        execution_fallbacks=execution_fallbacks,
        blocked_high_score_candidates=blocked_high_score,
    )


def brief_from_compositions(
    compositions: list[Any],
) -> str:
    """Convenience entry-point: build the brief from raw compositions.

    Each composition is turned into an observability document through the
    canonical path (``build_observability_document``) — nothing is re-scored.
    """
    if not compositions:
        raise ValueError("session review requires at least one composition")
    docs = [build_observability_document(comp) for comp in compositions]
    return reveal_session(docs)