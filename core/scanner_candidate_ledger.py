"""Scanner candidate ledger (Bước 09; target-only).

Mục 9C: thay trade/candidate ledger cũ (``scenario_scores``/``signal_score` on
the legacy side) bằng **side-owned** ``technical_signal_score`` / ``setup_score``.
The ledger records the canonical Bước 07/08 output without re-scoring anything:
it is a strict *reader* that stamps every score with its side, the technical
breakdown, gate/macro/safety statuses, reason codes and the full scorer /
feature / output / snapshot / policy / threshold identity.

One Scanner ledger row is built from a ``ScannerCompositionResult`` (the canonical
artifact, which carries ``side_scores`` per side) plus the refined candidate
decision.  The row is a plain dataclass/``to_dict`` artifact; it does NOT read
legacy ``final_score``/``signal_score``/``opportunity_score`` fields.  A row carries
``candidate_ledger_version`` so the Scanner replay contract can distinguish it from a
legacy ledger row (non-replayable, audit-only).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from fractions import Fraction

from core.reason_codes import (
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)
from core.scanner_backtest_contract import SCANNER_CANDIDATE_LEDGER_VERSION
from core.scanner_candidate import ScannerV4CandidateDecision
from core.scanner_composition import (
    COMPOSITION_POLICY_VERSION,
    COMPOSITION_POLICY_LEGACY_VERSION,
    ScannerCompositionResult,
)
from core.scanner_v4_models import (
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_MACRO_POLICY_VERSION,
    SCANNER_OUTPUT_SCHEMA_VERSION,
    SCANNER_SAFETY_POLICY_VERSION,
    SCANNER_SCORING_VERSION,
    SCANNER_SNAPSHOT_VERSION,
    SideScore,
)
from core.scanner_threshold_policy import SCANNER_THRESHOLD_POLICY_VERSION


@dataclass(frozen=True, slots=True)
class LedgerSideScore:
    """Side-owned ledger record of one canonical SideScore (never legacy fields)."""

    side: str
    technical_signal_score: int | None
    setup_score: int | None
    evidence_score: int | None
    execution_quality_score: int | None
    reason_codes: tuple[str, ...] = ()

    @classmethod
    def from_side_score(cls, side_score: SideScore) -> LedgerSideScore:
        if type(side_score) is not SideScore:
            raise TypeError("expected a Scanner V4 SideScore")
        return cls(
            side=side_score.side,
            technical_signal_score=side_score.technical_signal_score,
            setup_score=side_score.setup_score,
            evidence_score=side_score.evidence_score,
            execution_quality_score=side_score.execution_quality_score,
            reason_codes=side_score.reason_codes,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "side": self.side,
            "technical_signal_score": self.technical_signal_score,
            "setup_score": self.setup_score,
            "evidence_score": self.evidence_score,
            "execution_quality_score": self.execution_quality_score,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class ScannerLedgerRow:
    """One Scanner candidate ledger row (side-owned, fully attributed, replayable)."""

    candidate_id: str
    symbol: str
    captured_at: datetime
    snapshot_id: str
    candidate_ledger_version: str

    composition_version: str
    scoring_version: str
    feature_version: str
    output_schema_version: str
    snapshot_version: str
    safety_policy_version: str
    macro_policy_version: str
    threshold_policy_version: str

    selected_side: str | None
    candidate_status: str
    side_scores: tuple[LedgerSideScore, ...]
    selected_technical_signal_score: int | None
    selected_setup_score: int | None
    score_gap: int | None
    risk_reward_ratio: Fraction | None
    proximity: float | None
    decision_cap: str | None
    gate_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "snapshot_id": self.snapshot_id,
            "candidate_ledger_version": self.candidate_ledger_version,
            "composition_version": self.composition_version,
            "scoring_version": self.scoring_version,
            "feature_version": self.feature_version,
            "output_schema_version": self.output_schema_version,
            "snapshot_version": self.snapshot_version,
            "safety_policy_version": self.safety_policy_version,
            "macro_policy_version": self.macro_policy_version,
            "threshold_policy_version": self.threshold_policy_version,
            "selected_side": self.selected_side,
            "candidate_status": self.candidate_status,
            "side_scores": [s.to_dict() for s in self.side_scores],
            "selected_technical_signal_score": self.selected_technical_signal_score,
            "selected_setup_score": self.selected_setup_score,
            "score_gap": self.score_gap,
            "risk_reward_ratio": (
                None
                if self.risk_reward_ratio is None
                else str(self.risk_reward_ratio)
            ),
            "proximity": self.proximity,
            "decision_cap": self.decision_cap,
            "gate_codes": list(self.gate_codes),
            "reason_codes": list(self.reason_codes),
        }


def build_scanner_ledger_row(
    composition: ScannerCompositionResult,
    candidate: ScannerV4CandidateDecision,
) -> ScannerLedgerRow:
    """Build one Scanner ledger row from the canonical artifact + candidate decision.

    The row never re-scores and never reads legacy fields; it copies the side-owned
    canonical scores.  Identity is stamped from the candidate (which already
    owns all version identities) and cross-checked against the composition so a row
    cannot be assembled from mismatched artifacts.
    """
    if not isinstance(composition, ScannerCompositionResult):
        raise TypeError("expected a ScannerCompositionResult")
    if not isinstance(candidate, ScannerV4CandidateDecision):
        raise TypeError("expected a ScannerV4CandidateDecision")
    if composition.snapshot_id != candidate.snapshot_id:
        raise ValueError(
            "candidate.snapshot_id differs from composition.snapshot_id — "
            "cannot build a ledger row from mismatched artifacts"
        )
    if candidate.composition_version not in (COMPOSITION_POLICY_VERSION, COMPOSITION_POLICY_LEGACY_VERSION):
        raise ValueError("candidate composition version mismatch")

    side_scores = tuple(
        LedgerSideScore.from_side_score(side_score)
        for side_score in composition.canonical.side_scores
    )

    return ScannerLedgerRow(
        candidate_id=f"v4:{candidate.snapshot_id}",
        symbol=candidate.symbol,
        captured_at=candidate.captured_at,
        snapshot_id=candidate.snapshot_id,
        candidate_ledger_version=SCANNER_CANDIDATE_LEDGER_VERSION,
        composition_version=COMPOSITION_POLICY_VERSION,
        scoring_version=candidate.scoring_version,
        feature_version=candidate.feature_version,
        output_schema_version=candidate.output_schema_version,
        snapshot_version=candidate.snapshot_version,
        safety_policy_version=candidate.safety_policy_version,
        macro_policy_version=candidate.macro_policy_version,
        threshold_policy_version=candidate.threshold_policy_version,
        selected_side=candidate.selected_side,
        candidate_status=candidate.candidate_status,
        side_scores=side_scores,
        selected_technical_signal_score=candidate.technical_signal_score,
        selected_setup_score=candidate.setup_score,
        score_gap=candidate.score_gap,
        risk_reward_ratio=candidate.risk_reward_ratio,
        proximity=candidate.proximity,
        decision_cap=candidate.decision_cap,
        gate_codes=candidate.gate_codes,
        reason_codes=candidate.reason_codes,
    )


class LedgerContractError(ValueError):
    """Fail-closed error for the Scanner candidate-ledger reader."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        self.code = code
        self.path = path
        self.detail = detail
        super().__init__(f"{code} at {path}: {detail}")


def _ledger_text(value: object, path: str) -> str:
    if type(value) is not str or not value:
        raise LedgerContractError(SCANNER_SCHEMA_INVALID, path, "expected a non-empty string")
    return value


def _ledger_exact_version(value: object, expected: str, path: str) -> str:
    """Require the EXACT locked Scanner identity string (reject legacy/mixed/unknown)."""
    if type(value) is not str or value != expected:
        raise LedgerContractError(
            SCANNER_VERSION_MISMATCH, path, f"expected {expected!r}, got {value!r}"
        )
    return value


def _ledger_side_scores(value: object, path: str) -> tuple[LedgerSideScore, ...]:
    if type(value) is not list:
        raise LedgerContractError(SCANNER_SCHEMA_INVALID, path, "expected an array")
    scores: list[LedgerSideScore] = []
    for index, item in enumerate(value):
        scores.append(_ledger_side_score(item, f"{path}[{index}]"))
    return tuple(scores)


def _ledger_side_score(value: object, path: str) -> LedgerSideScore:
    if type(value) is not dict:
        raise LedgerContractError(SCANNER_SCHEMA_INVALID, path, "expected an object")
    side = _ledger_text(value.get("side"), f"{path}.side")
    return LedgerSideScore(
        side=side,
        technical_signal_score=(
            None if value.get("technical_signal_score") is None
            else value["technical_signal_score"]
        ),
        setup_score=(None if value.get("setup_score") is None else value["setup_score"]),
        evidence_score=(None if value.get("evidence_score") is None else value["evidence_score"]),
        execution_quality_score=(
            None if value.get("execution_quality_score") is None else value["execution_quality_score"]
        ),
        reason_codes=tuple(
            _ledger_text(item, f"{path}.reason_codes")
            for item in (value.get("reason_codes") or ())
        ),
    )


def scanner_ledger_row_from_dict(value: object, *, path: str = "scanner_ledger_row") -> ScannerLedgerRow:
    """Strict reader for a persisted Scanner candidate-ledger row.

    Refuses any row that is not the exact locked Scanner identity (candidate ledger +
    composition + scorer/feature/output/snapshot/policy/threshold versions).  A
    legacy ledger row, a missing/mismatched version, or an unknown identity is
    refused — never reloaded as a Scanner row (Bước 12 §12.1 / §7.3).
    """
    if type(value) is not dict:
        raise LedgerContractError(SCANNER_SCHEMA_INVALID, path, "expected a JSON object")

    _ledger_exact_version(
        value.get("candidate_ledger_version"),
        SCANNER_CANDIDATE_LEDGER_VERSION,
        f"{path}.candidate_ledger_version",
    )
    _ledger_exact_version(
        value.get("composition_version"),
        COMPOSITION_POLICY_VERSION,
        f"{path}.composition_version",
    )
    _ledger_exact_version(
        value.get("scoring_version"), SCANNER_SCORING_VERSION, f"{path}.scoring_version"
    )
    _ledger_exact_version(
        value.get("feature_version"), SCANNER_V4_FEATURE_VERSION, f"{path}.feature_version"
    )
    _ledger_exact_version(
        value.get("output_schema_version"),
        SCANNER_OUTPUT_SCHEMA_VERSION,
        f"{path}.output_schema_version",
    )
    _ledger_exact_version(
        value.get("snapshot_version"), SCANNER_SNAPSHOT_VERSION, f"{path}.snapshot_version"
    )
    _ledger_exact_version(
        value.get("safety_policy_version"),
        SCANNER_SAFETY_POLICY_VERSION,
        f"{path}.safety_policy_version",
    )
    _ledger_exact_version(
        value.get("macro_policy_version"),
        SCANNER_MACRO_POLICY_VERSION,
        f"{path}.macro_policy_version",
    )
    _ledger_exact_version(
        value.get("threshold_policy_version"),
        SCANNER_THRESHOLD_POLICY_VERSION,
        f"{path}.threshold_policy_version",
    )

    ratio = value.get("risk_reward_ratio")
    parsed_ratio = None if ratio is None else Fraction(str(ratio))
    captured_at = datetime.fromisoformat(_ledger_text(value.get("captured_at"), f"{path}.captured_at"))

    return ScannerLedgerRow(
        candidate_id=_ledger_text(value.get("candidate_id"), f"{path}.candidate_id"),
        symbol=_ledger_text(value.get("symbol"), f"{path}.symbol"),
        captured_at=captured_at,
        snapshot_id=_ledger_text(value.get("snapshot_id"), f"{path}.snapshot_id"),
        candidate_ledger_version=SCANNER_CANDIDATE_LEDGER_VERSION,
        composition_version=COMPOSITION_POLICY_VERSION,
        scoring_version=SCANNER_SCORING_VERSION,
        feature_version=SCANNER_V4_FEATURE_VERSION,
        output_schema_version=SCANNER_OUTPUT_SCHEMA_VERSION,
        snapshot_version=SCANNER_SNAPSHOT_VERSION,
        safety_policy_version=SCANNER_SAFETY_POLICY_VERSION,
        macro_policy_version=SCANNER_MACRO_POLICY_VERSION,
        threshold_policy_version=SCANNER_THRESHOLD_POLICY_VERSION,
        selected_side=(
            None
            if value.get("selected_side") is None
            else _ledger_text(value.get("selected_side"), f"{path}.selected_side")
        ),
        candidate_status=_ledger_text(
            value.get("candidate_status"), f"{path}.candidate_status"
        ),
        side_scores=_ledger_side_scores(value.get("side_scores"), f"{path}.side_scores"),
        selected_technical_signal_score=(
            None if value.get("selected_technical_signal_score") is None
            else value["selected_technical_signal_score"]
        ),
        selected_setup_score=(
            None if value.get("selected_setup_score") is None else value["selected_setup_score"]
        ),
        score_gap=(None if value.get("score_gap") is None else value["score_gap"]),
        risk_reward_ratio=parsed_ratio,
        proximity=(None if value.get("proximity") is None else value["proximity"]),
        decision_cap=(
            None
            if value.get("decision_cap") is None
            else _ledger_text(value.get("decision_cap"), f"{path}.decision_cap")
        ),
        gate_codes=tuple(
            _ledger_text(item, f"{path}.gate_codes") for item in (value.get("gate_codes") or ())
        ),
        reason_codes=tuple(
            _ledger_text(item, f"{path}.reason_codes") for item in (value.get("reason_codes") or ())
        ),
    )