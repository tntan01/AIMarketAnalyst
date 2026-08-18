"""Scanner snapshot persistence envelope (Bước 10; target-only).

10C — persistence schema bump.  The legacy controller stamps integer ``persistence_schema_version =
1`` at ``controllers/scanner_controller.py:2529``; Scanner consumer artifacts use
their own envelope identity ``scanner-snapshot-envelope`` (the legacy
``scanner-v4-snapshot-envelope-v1`` alias is still read for old artifacts) with a
``mode``:

* ``compact`` — keeps what a consumer needs to *display and audit*: full
  identity versions, snapshot_id, symbol, captured_at, capture_source, the
  side-owned technical/setup/evidence/execution scores, selected side,
  candidate status, Safety/Macro status + cap + reason codes, gate/block codes
  and the row's reason codes.  It deliberately does NOT embed the whole
  composition (gates with observed values / scenario plans), so a compact
  envelope is *not* replayable.
* ``full`` — embeds the strict ``composition.to_dict()`` payload so the
  envelope round-trips exactly and can be replayed deterministically.

Both modes require the full Scanner version identity.  A legacy payload (missing
``envelope_schema_version`` or carrying a legacy identity), a missing version, or
any legacy scored field in the payload is refused at read time —
``SCANNER_V4_LEGACY_V3_AUDIT_ONLY`` / ``VERSION_MISSING`` / ``VERSION_MISMATCH``,
never auto-labelled.  The reader is a *strict* reader: it never rewrites a
legacy snapshot or upgrades it in place.

This module is not wired to runtime; the legacy controller persistence stays as-is
until the atomic cutover (Bước 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from core.reason_codes import (
    SCANNER_FORBIDDEN_SCORED_FIELD,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)
from core.scanner_composition import (
    COMPOSITION_POLICY_VERSION,
    ScannerCompositionResult,
)
from core.scanner_v4_models import (
    BUY,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_MACRO_POLICY_VERSION,
    SCANNER_OUTPUT_SCHEMA_VERSION,
    SCANNER_SAFETY_POLICY_VERSION,
    SCANNER_SCORING_VERSION,
    SCANNER_SNAPSHOT_VERSION,
    SELL,
    UNKNOWN,
    VALID_SIDES,
    deserialize_canonical_pair_snapshot,
    serialize_canonical_pair_snapshot,
)

SCANNER_SNAPSHOT_ENVELOPE_VERSION = "scanner-snapshot-envelope"
SCANNER_SNAPSHOT_ENVELOPE_LEGACY_VERSION = "scanner-v4-snapshot-envelope-v1"

MODE_COMPACT = "compact"
MODE_FULL = "full"
VALID_ENVELOPE_MODES = frozenset({MODE_COMPACT, MODE_FULL})

# Complete key set of a compact envelope (DoR-10 / 10C).
COMPACT_KEYS = frozenset(
    {
        "envelope_schema_version",
        "mode",
        "composition_version",
        "scoring_version",
        "feature_version",
        "output_schema_version",
        "safety_policy_version",
        "macro_policy_version",
        "snapshot_version",
        "snapshot_id",
        "symbol",
        "captured_at",
        "capture_source",
        "candidate_status",
        "selected_side",
        "score_gap",
        "decision_cap",
        "side_scores",
        "safety_status",
        "safety_reason_codes",
        "macro_status",
        "macro_reason_codes",
        "gate_codes",
        "block_codes",
        "reason_codes",
    }
)

# Full mode adds the strict composition payload.
FULL_KEYS = frozenset({*COMPACT_KEYS, "composition"})

# Legacy scored fields that never belong in a Scanner envelope.
LEGACY_ENVELOPE_FIELDS = frozenset(
    {
        "persistence_schema_version",
        "total",
        "best_score",
        "signal_score",
        "opportunity_score",
        "scanner_action",
        "scanner_group",
        "expected_effective_rr",
        "risk_condition",
        "macro_alignment",
        "buy_score",
        "sell_score",
        "macro_score",
        "macro_bias",
    }
)


class SnapshotEnvelopeError(ValueError):
    """Fail-closed envelope reader error carrying a reason code."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.detail = message
        super().__init__(f"{code} at {path}: {message}")


@dataclass(frozen=True, slots=True)
class EnvelopeSideScore:
    """Side-owned score carried in the envelope (never legacy scored fields)."""

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

    @classmethod
    def from_dict(cls, value: object, *, path: str = "envelope_side_score") -> EnvelopeSideScore:
        if type(value) is not dict:
            raise SnapshotEnvelopeError(
                SCANNER_SCHEMA_INVALID, path, "expected an object"
            )
        expected = {
            "side",
            "technical_signal_score",
            "setup_score",
            "evidence_score",
            "evidence_source",
            "execution_quality_score",
            "execution_quality_source",
        }
        if set(value) != expected:
            raise SnapshotEnvelopeError(
                SCANNER_SCHEMA_INVALID,
                path,
                f"unexpected side-score keys: {sorted(set(value) - expected)}",
            )
        side = _require_text(value["side"], f"{path}.side")
        if side not in VALID_SIDES:
            raise SnapshotEnvelopeError(
                SCANNER_SCHEMA_INVALID, f"{path}.side", "invalid side"
            )
        return cls(
            side=side,
            technical_signal_score=_optional_int(
                value["technical_signal_score"], f"{path}.technical_signal_score"
            ),
            setup_score=_optional_int(value["setup_score"], f"{path}.setup_score"),
            evidence_score=_optional_int(
                value["evidence_score"], f"{path}.evidence_score"
            ),
            evidence_source=_require_text(
                value["evidence_source"], f"{path}.evidence_source", allow_empty=True
            ),
            execution_quality_score=_optional_int(
                value["execution_quality_score"], f"{path}.execution_quality_score"
            ),
            execution_quality_source=_require_text(
                value["execution_quality_source"],
                f"{path}.execution_quality_source",
                allow_empty=True,
            ),
        )


@dataclass(frozen=True, slots=True)
class ScannerSnapshotEnvelope:
    """Scanner persistence envelope (compact or full; strict; target-only)."""

    envelope_schema_version: str
    mode: str
    composition_version: str
    scoring_version: str
    feature_version: str
    output_schema_version: str
    safety_policy_version: str
    macro_policy_version: str
    snapshot_version: str
    snapshot_id: str
    symbol: str
    captured_at: datetime
    capture_source: str
    candidate_status: str
    selected_side: str | None
    score_gap: int | None
    decision_cap: str | None
    side_scores: tuple[EnvelopeSideScore, ...]
    safety_status: str
    safety_reason_codes: tuple[str, ...]
    macro_status: str
    macro_reason_codes: tuple[str, ...]
    gate_codes: tuple[str, ...]
    block_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    composition: dict[str, Any] | None = None  # only for mode=full

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "envelope_schema_version": self.envelope_schema_version,
            "mode": self.mode,
            "composition_version": self.composition_version,
            "scoring_version": self.scoring_version,
            "feature_version": self.feature_version,
            "output_schema_version": self.output_schema_version,
            "safety_policy_version": self.safety_policy_version,
            "macro_policy_version": self.macro_policy_version,
            "snapshot_version": self.snapshot_version,
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "captured_at": self.captured_at.isoformat(),
            "capture_source": self.capture_source,
            "candidate_status": self.candidate_status,
            "selected_side": self.selected_side,
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
        if self.mode == MODE_FULL:
            if self.composition is None:
                raise SnapshotEnvelopeError(
                    SCANNER_SCHEMA_INVALID,
                    "snapshot.full.composition",
                    "a full envelope requires the embedded composition",
                )
            payload["composition"] = self.composition
        return payload

    @property
    def replayable(self) -> bool:
        """A full envelope embeds the strict composition and can be replayed."""
        return self.mode == MODE_FULL and self.composition is not None


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def build_snapshot_envelope(
    composition: ScannerCompositionResult,
    *,
    mode: str = MODE_COMPACT,
) -> ScannerSnapshotEnvelope:
    """Build a compact/full Scanner snapshot envelope from a canonical composition.

    The envelope never re-scores and never reads legacy fields; every score is the
    canonical side-owned value, and Safety/Macro statuses come from the gates.
    ``mode=full`` additionally embeds the strict ``composition.to_dict()`` so
    the envelope round-trips exactly.
    """
    if type(composition) is not ScannerCompositionResult:
        raise TypeError("expected a ScannerCompositionResult")
    if mode not in VALID_ENVELOPE_MODES:
        raise ValueError(f"invalid envelope mode {mode!r}")
    canonical = composition.canonical

    def _side(side: str) -> EnvelopeSideScore:
        score = canonical.side_score(side)
        return EnvelopeSideScore(
            side=side,
            technical_signal_score=score.technical_signal_score,
            setup_score=score.setup_score,
            evidence_score=score.evidence_score,
            evidence_source=score.evidence_source,
            execution_quality_score=score.execution_quality_score,
            execution_quality_source=score.execution_quality_source,
        )

    return ScannerSnapshotEnvelope(
        envelope_schema_version=SCANNER_SNAPSHOT_ENVELOPE_VERSION,
        mode=mode,
        composition_version=COMPOSITION_POLICY_VERSION,
        scoring_version=canonical.scoring_version,
        feature_version=canonical.feature_version,
        output_schema_version=canonical.output_schema_version,
        safety_policy_version=canonical.safety_policy_version,
        macro_policy_version=canonical.macro_policy_version,
        snapshot_version=canonical.snapshot_version,
        snapshot_id=canonical.snapshot_id,
        symbol=canonical.symbol,
        captured_at=canonical.captured_at,
        capture_source=composition.capture_source,
        candidate_status=composition.decision.candidate_status,
        selected_side=composition.decision.selected_side,
        score_gap=composition.decision.score_gap,
        decision_cap=composition.decision.decision_cap,
        side_scores=(_side(BUY), _side(SELL)),
        safety_status=canonical.market_safety.status,
        safety_reason_codes=canonical.market_safety.reason_codes,
        macro_status=canonical.macro_gate.status,
        macro_reason_codes=canonical.macro_gate.reason_codes,
        gate_codes=composition.decision.gate_codes,
        block_codes=composition.decision.block_codes,
        reason_codes=composition.decision.reason_codes,
        composition=(composition.to_dict() if mode == MODE_FULL else None),
    )


# ---------------------------------------------------------------------------
# Strict reader
# ---------------------------------------------------------------------------


def snapshot_envelope_from_dict(
    value: object, *, path: str = "snapshot_envelope"
) -> ScannerSnapshotEnvelope:
    """Strict reader for a persisted Scanner envelope.

    Refuses unknown/missing versions, legacy identity, and any legacy scored field
    — a legacy snapshot is *audit-only*, non-replayable, and never auto-labelled.
    """
    if type(value) is not dict:
        raise SnapshotEnvelopeError(
            SCANNER_SCHEMA_INVALID, path, "external payload must be a JSON object"
        )
    schema_version = value.get("envelope_schema_version")
    # A genuine legacy artifact is audit-only — identified before any legacy-field
    # check so it is never mislabelled as a «Scanner payload with forbidden fields».
    if _is_v3_artifact(value):
        raise SnapshotEnvelopeError(
            SCANNER_LEGACY_V3_AUDIT_ONLY,
            f"{path}.envelope_schema_version",
            "V3 persistence payload is audit-only and non-replayable",
        )
    legacy = sorted(LEGACY_ENVELOPE_FIELDS.intersection(value))
    if legacy:
        raise SnapshotEnvelopeError(
            SCANNER_FORBIDDEN_SCORED_FIELD,
            path,
            f"forbidden V3/legacy fields in V4 envelope: {legacy}",
        )
    if schema_version is None:
        raise SnapshotEnvelopeError(
            SCANNER_VERSION_MISSING,
            f"{path}.envelope_schema_version",
            "missing envelope_schema_version",
        )
    if schema_version not in (SCANNER_SNAPSHOT_ENVELOPE_VERSION, SCANNER_SNAPSHOT_ENVELOPE_LEGACY_VERSION):
        if _is_v3_identity(value):
            raise SnapshotEnvelopeError(
                SCANNER_LEGACY_V3_AUDIT_ONLY,
                f"{path}.envelope_schema_version",
                "V3 persistence payload is audit-only and non-replayable",
            )
        raise SnapshotEnvelopeError(
            SCANNER_VERSION_MISMATCH,
            f"{path}.envelope_schema_version",
            f"unsupported envelope version {schema_version!r}",
        )
    if "mode" not in value:
        raise SnapshotEnvelopeError(
            SCANNER_VERSION_MISSING, f"{path}.mode", "missing mode"
        )
    mode = value["mode"]
    if mode not in VALID_ENVELOPE_MODES:
        raise SnapshotEnvelopeError(
            SCANNER_VERSION_MISMATCH, f"{path}.mode", f"invalid mode {mode!r}"
        )
    expected_keys = FULL_KEYS if mode == MODE_FULL else COMPACT_KEYS
    if set(value) != expected_keys:
        raise SnapshotEnvelopeError(
            SCANNER_SCHEMA_INVALID,
            path,
            f"envelope key set mismatch for mode {mode!r}: "
            f"unknown={sorted(set(value) - expected_keys)} "
            f"missing={sorted(expected_keys - set(value))}",
        )
    composition_payload = value.get("composition")
    if mode == MODE_FULL:
        if not isinstance(composition_payload, dict):
            raise SnapshotEnvelopeError(
                SCANNER_SCHEMA_INVALID,
                f"{path}.composition",
                "full envelope requires the embedded composition dict",
            )
        # Re-validate strictly through the canonical composition reader.
        try:
            ScannerCompositionResult.from_dict(composition_payload)
        except SnapshotEnvelopeError:
            raise
        except ValueError as exc:
            code = getattr(exc, "code", None) or SCANNER_SCHEMA_INVALID
            raise SnapshotEnvelopeError(
                code, f"{path}.composition", f"embedded composition invalid: {exc}"
            )
        # Cross-check identity: snapshot_id must match the composition.
        comp_snapshot_id = composition_payload.get("snapshot_id")
        if comp_snapshot_id != value.get("snapshot_id"):
            raise SnapshotEnvelopeError(
                SCANNER_VERSION_MISMATCH,
                f"{path}.snapshot_id",
                "envelope snapshot_id differs from embedded composition",
            )
    else:
        composition_payload = None

    return ScannerSnapshotEnvelope(
        envelope_schema_version=schema_version,
        mode=mode,
        composition_version=_require_exact_version(
            value["composition_version"], COMPOSITION_POLICY_VERSION, f"{path}.composition_version"
        ),
        scoring_version=_require_exact_version(
            value["scoring_version"], SCANNER_SCORING_VERSION, f"{path}.scoring_version"
        ),
        feature_version=_require_exact_version(
            value["feature_version"], SCANNER_V4_FEATURE_VERSION, f"{path}.feature_version"
        ),
        output_schema_version=_require_exact_version(
            value["output_schema_version"],
            SCANNER_OUTPUT_SCHEMA_VERSION,
            f"{path}.output_schema_version",
        ),
        safety_policy_version=_require_exact_version(
            value["safety_policy_version"],
            SCANNER_SAFETY_POLICY_VERSION,
            f"{path}.safety_policy_version",
        ),
        macro_policy_version=_require_exact_version(
            value["macro_policy_version"],
            SCANNER_MACRO_POLICY_VERSION,
            f"{path}.macro_policy_version",
        ),
        snapshot_version=_require_exact_version(
            value["snapshot_version"], SCANNER_SNAPSHOT_VERSION, f"{path}.snapshot_version"
        ),
        snapshot_id=_require_text(value["snapshot_id"], f"{path}.snapshot_id"),
        symbol=_require_text(value["symbol"], f"{path}.symbol"),
        captured_at=_parse_datetime(value["captured_at"], f"{path}.captured_at"),
        capture_source=_require_text(value["capture_source"], f"{path}.capture_source"),
        candidate_status=_require_text(
            value["candidate_status"], f"{path}.candidate_status"
        ),
        selected_side=(
            None
            if value["selected_side"] is None
            else _require_text(value["selected_side"], f"{path}.selected_side")
        ),
        score_gap=_optional_int(value["score_gap"], f"{path}.score_gap"),
        decision_cap=(
            None
            if value["decision_cap"] is None
            else _require_text(value["decision_cap"], f"{path}.decision_cap")
        ),
        side_scores=tuple(
            EnvelopeSideScore.from_dict(item, path=f"{path}.side_scores[{index}]")
            for index, item in enumerate(_require_list(value["side_scores"], f"{path}.side_scores"))
        ),
        safety_status=_require_text(value["safety_status"], f"{path}.safety_status"),
        safety_reason_codes=_parse_codes(
            value["safety_reason_codes"], f"{path}.safety_reason_codes"
        ),
        macro_status=_require_text(value["macro_status"], f"{path}.macro_status"),
        macro_reason_codes=_parse_codes(
            value["macro_reason_codes"], f"{path}.macro_reason_codes"
        ),
        gate_codes=_parse_codes(value["gate_codes"], f"{path}.gate_codes"),
        block_codes=_parse_codes(value["block_codes"], f"{path}.block_codes"),
        reason_codes=_parse_codes(value["reason_codes"], f"{path}.reason_codes"),
        composition=composition_payload,
    )


_V3_VERSION_MARKERS = frozenset(
    {
        "scanner-v3",
        "scanner-features-v3",
        "smc-v2",
        "phase7-observability-v1",
        "phase8-scoring-provenance-v1",
    }
)


def _is_v3_artifact(value: Mapping[str, Any]) -> bool:
    """Genuine legacy artifact detection (version/schema markers only).

    Used *before* the legacy-field check so a real legacy payload (whose legacy
    scored fields are its native shape) is classified audit-only instead of being
    mislabelled as a Scanner payload carrying forbidden fields.
    """
    if value.get("envelope_schema_version") in _V3_VERSION_MARKERS:
        return True
    for key in ("scoring_version", "feature_version", "scorer_version"):
        if value.get(key) in _V3_VERSION_MARKERS:
            return True
    return False


def _is_v3_identity(value: Mapping[str, Any]) -> bool:
    """Cheap legacy heuristic: any legacy version marker / scored field present."""
    known_v3_values = {
        "scanner-v3",
        "scanner-features-v3",
        "smc-v2",
        "phase7-observability-v1",
        "phase8-scoring-provenance-v1",
    }
    for key in ("scoring_version", "feature_version", "scorer_version"):
        if value.get(key) in known_v3_values:
            return True
    for key in LEGACY_ENVELOPE_FIELDS:
        if key in value:
            return True
    return False


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise SnapshotEnvelopeError(SCANNER_SCHEMA_INVALID, path, "expected an array")
    return value


def _require_text(value: object, path: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise SnapshotEnvelopeError(SCANNER_SCHEMA_INVALID, path, "expected a string")
    if not allow_empty and not value:
        raise SnapshotEnvelopeError(SCANNER_SCHEMA_INVALID, path, "expected a non-empty string")
    return value


def _require_exact_version(value: object, expected: str, path: str) -> str:
    """Require the EXACT locked Scanner identity string (reject legacy/mixed/unknown)."""
    if type(value) is not str or value != expected:
        raise SnapshotEnvelopeError(
            SCANNER_VERSION_MISMATCH, path, f"expected {expected!r}, got {value!r}"
        )
    return value


def _optional_int(value: object, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise SnapshotEnvelopeError(SCANNER_SCHEMA_INVALID, path, "expected int or null")
    return value


def _parse_datetime(value: object, path: str) -> datetime:
    text = _require_text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise SnapshotEnvelopeError(
            SCANNER_SCHEMA_INVALID, path, f"invalid ISO datetime: {exc}"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SnapshotEnvelopeError(SCANNER_SCHEMA_INVALID, path, "must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_codes(value: object, path: str) -> tuple[str, ...]:
    result: list[str] = []
    for index, item in enumerate(_require_list(value, path)):
        if type(item) is not str or not item:
            raise SnapshotEnvelopeError(
                SCANNER_SCHEMA_INVALID, f"{path}[{index}]", "expected a code"
            )
        result.append(item)
    return tuple(result)