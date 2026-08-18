"""Scanner journal data models (Bước 10; target-only; additive).

10D — an *additive* Scanner journal schema.  Unlike the legacy ``JournalEntry``
(``services/journal_models.py``) which reads ``scenario_scores.buy.total`` and
``buy_score`` / ``sell_score`` / ``scanner_action``, the Scanner journal row records:

* the canonical side-owned scores — ``technical_signal_score``, ``setup_score``,
  ``evidence_score``, ``execution_quality_score`` per side — from the
  ``CanonicalPairSnapshot``;
* Safety/Macro status + reason codes + policy versions;
* the full version identity (composition / scoring / feature / output_schema /
  snapshot / safety / macro / threshold);
* ``selected_side``, ``candidate_status``, ``decision_cap``,
  ``gate_codes``/``block_codes``, ``reason_codes``, ``snapshot_id``.

Migration is additive: the legacy journal table/converters are untouched; the Scanner
converter writes a separate, versioned row.  Evidence aggregation is
**partitioned by scorer/policy version** (see ``evidence_partition``) so legacy and
Scanner evidence are never mixed; when no reuse decision exists the partition
fails closed and mixing is refused.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from core.reason_codes import SCANNER_JOURNAL_PARTITION_MIXED
from core.scanner_composition import COMPOSITION_POLICY_VERSION

SCANNER_JOURNAL_SCHEMA_VERSION = "scanner-journal"
SCANNER_JOURNAL_SCHEMA_LEGACY_VERSION = "scanner-v4-journal-v1"

# Fields the Scanner journal stores and indexes (DoR-10 / 10D).
JOURNAL_VERSION_FIELDS = (
    "journal_schema_version",
    "composition_version",
    "scoring_version",
    "feature_version",
    "output_schema_version",
    "safety_policy_version",
    "macro_policy_version",
    "snapshot_version",
    "threshold_policy_version",
)

# Timestamp keys usable for journal index/query.
JOURNAL_TIMESTAMP_KEYS = ("captured_at", "timestamp_utc")

# Legacy-era scored fields that must never appear in a Scanner journal row.
FORBIDDEN_V3_JOURNAL_FIELDS = frozenset(
    {
        "scenario_scores",
        "buy_score",
        "sell_score",
        "scanner_action",
        "scanner_group",
        "total",
        "best_score",
        "signal_score",
        "opportunity_score",
        "expected_effective_rr",
        "risk_condition",
        "macro_alignment",
        "macro_score",
        "macro_bias",
    }
)


class JournalError(ValueError):
    """Fail-closed Scanner journal converter error carrying a reason code."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.detail = message
        super().__init__(f"{code} at {path}: {message}")


@dataclass(frozen=True, slots=True)
class JournalSideScore:
    """Canonical side-owned score block of a Scanner journal row."""

    side: str
    technical_signal_score: int | None
    setup_score: int | None
    evidence_score: int | None
    evidence_source: str
    execution_quality_score: int | None
    execution_quality_source: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "technical_signal_score": self.technical_signal_score,
            "setup_score": self.setup_score,
            "evidence_score": self.evidence_score,
            "evidence_source": self.evidence_source,
            "execution_quality_score": self.execution_quality_score,
            "execution_quality_source": self.execution_quality_source,
        }


@dataclass(frozen=True, slots=True)
class ScannerJournalRow:
    """One additive Scanner journal row (canonical side-owned; partitioned)."""

    journal_schema_version: str
    composition_version: str
    scoring_version: str
    feature_version: str
    output_schema_version: str
    safety_policy_version: str
    macro_policy_version: str
    snapshot_version: str
    threshold_policy_version: str

    snapshot_id: str
    symbol: str
    captured_at: datetime
    timestamp_utc: datetime

    selected_side: str | None
    candidate_status: str
    score_gap: int | None
    decision_cap: str | None
    side_scores: tuple[JournalSideScore, ...]

    safety_status: str
    safety_reason_codes: tuple[str, ...]
    macro_status: str
    macro_reason_codes: tuple[str, ...]
    gate_codes: tuple[str, ...]
    block_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def evidence_partition(self) -> str:
        """Partition key: Scanner evidence is keyed by scorer + policy identity.

        Aggregating evidence across partitions is refused until an explicit
        reuse decision exists (DoR-10 / 10D).
        """
        return evidence_partition_key(
            scoring_version=self.scoring_version,
            feature_version=self.feature_version,
            safety_policy_version=self.safety_policy_version,
            macro_policy_version=self.macro_policy_version,
            threshold_policy_version=self.threshold_policy_version,
            composition_version=self.composition_version,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "journal_schema_version": self.journal_schema_version,
            "composition_version": self.composition_version,
            "scoring_version": self.scoring_version,
            "feature_version": self.feature_version,
            "output_schema_version": self.output_schema_version,
            "safety_policy_version": self.safety_policy_version,
            "macro_policy_version": self.macro_policy_version,
            "snapshot_version": self.snapshot_version,
            "threshold_policy_version": self.threshold_policy_version,
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "timestamp_utc": self.timestamp_utc.isoformat(),
            "selected_side": self.selected_side,
            "candidate_status": self.candidate_status,
            "score_gap": self.score_gap,
            "decision_cap": self.decision_cap,
            "side_scores": [s.to_dict() for s in self.side_scores],
            "safety_status": self.safety_status,
            "safety_reason_codes": list(self.safety_reason_codes),
            "macro_status": self.macro_status,
            "macro_reason_codes": list(self.macro_reason_codes),
            "gate_codes": list(self.gate_codes),
            "block_codes": list(self.block_codes),
            "reason_codes": list(self.reason_codes),
        }


def evidence_partition_key(
    *,
    scoring_version: str,
    feature_version: str,
    safety_policy_version: str,
    macro_policy_version: str,
    threshold_policy_version: str,
    composition_version: str,
) -> str:
    """Deterministic evidence partition key for Scanner (never mixes with legacy).

    A legacy journal row has none of these identities, so any aggregation that
    groups by this key automatically excludes legacy semantics.
    """
    return "|".join(
        (
            "v4",
            composition_version,
            scoring_version,
            feature_version,
            safety_policy_version,
            macro_policy_version,
            threshold_policy_version,
        )
    )


def assert_same_partition(rows: list[ScannerJournalRow]) -> str:
    """Return the single partition key of *rows*, refusing mixed partitions.

    Fail-closed: when rows carry different Scanner scorer/policy identities — or
    when a "row" is actually legacy-shaped — aggregation is refused instead of
    silently aligning semantics.
    """
    if not rows:
        return ""
    partitions = {row.evidence_partition() for row in rows}
    if len(partitions) != 1:
        raise JournalError(
            SCANNER_JOURNAL_PARTITION_MIXED,
            "rows",
            f"evidence rows span {sorted(partitions)} partitions — refusing to mix",
        )
    return partitions.pop()