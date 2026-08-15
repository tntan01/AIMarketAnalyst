"""Scanner V4 row/API consumer contract (Bước 10; target-only).

10A replaces the V3 row adapter reads in ``core/scanner.py`` with a strict V4
reader that consumes ONLY the canonical Step 07/08 output — the
``ScannerV4CompositionResult`` / ``CanonicalPairSnapshot`` — and emits the full
output/schema/policy identity plus TechnicalScore, SetupScore, selected side,
Safety/Macro status + cap and reason codes.  There is **no legacy fallback**:

* it never reads ``risk_condition`` / ``macro_alignment`` / ``scenario_scores`` /
  ``scanner_action`` / ``best_score`` / ``opportunity_score`` / ``total``;
* ``blocked_scanner_row_v4`` emits the full-schema row with
  ``candidate_status = DATA_UNAVAILABLE`` and **null** technical/setup and
  Safety/Macro status ``UNKNOWN`` — it does NOT fabricate a «macro 15» or a
  neutral score (contrast ``core/scanner.py:355-402`` which hardcodes
  ``macro_score = 15`` and zeroed scores for its V3 row);
* a V3 artifact or a missing/mismatched version is refused at read time, never
  coerced into a V4 row.

This module is not wired to runtime.  The V3 executable scanner is untouched
until the atomic cutover (Bước 12).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from core.reason_codes import (
    SCANNER_V4_FORBIDDEN_SCORED_FIELD,
    SCANNER_V4_SCHEMA_INVALID,
    SCANNER_V4_VERSION_MISMATCH,
    SCANNER_V4_VERSION_MISSING,
)
from core.scanner_v4_composition import (
    COMPOSITION_POLICY_VERSION,
    CompositionInputError,
    ScannerV4CompositionResult,
)
from core.scanner_v4_models import (
    DATA_UNAVAILABLE,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_V4_MACRO_POLICY_VERSION,
    SCANNER_V4_OUTPUT_SCHEMA_VERSION,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SCANNER_V4_SNAPSHOT_VERSION,
    UNKNOWN,
    VALID_SIDES,
    CanonicalPairSnapshot,
    SideScore,
)

# Row identity stamped by this consumer (not the snapshot schema; see DoR-10).
SCANNER_V4_ROW_VERSION = "scanner-v4-row-v1"

# Version keys this row emits, in canonical order.  These are exactly the
# identity fields a row reader must expose for audit (DoR-10 / 10A).
ROW_VERSION_FIELDS = (
    "row_version",
    "composition_version",
    "scoring_version",
    "feature_version",
    "output_schema_version",
    "safety_policy_version",
    "macro_policy_version",
    "snapshot_version",
)

# V3-era scored/legacy fields a V4 row must never carry.
LEGACY_SCORED_FIELDS = frozenset(
    {
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

# Every key a V4 row emits.  The row is *full-schema* — no V3 six-component
# keys, no macro-as-scored-component, no legacy rank/action fields.
ROW_KEYS = frozenset(
    {
        *ROW_VERSION_FIELDS,
        "snapshot_id",
        "symbol",
        "captured_at",
        "capture_source",
        "candidate_status",
        "selected_side",
        "score_gap",
        "decision_cap",
        "side_scores",
        "selected_technical_signal_score",
        "selected_setup_score",
        "safety_status",
        "safety_reason_codes",
        "macro_status",
        "macro_reason_codes",
        "gate_codes",
        "reason_codes",
        "block_codes",
    }
)


class RowContractError(ValueError):
    """Fail-closed error for the V4 row reader (carries a reason code)."""

    def __init__(self, code: str, path: str, message: str) -> None:
        self.code = code
        self.path = path
        self.detail = message
        super().__init__(f"{code} at {path}: {message}")


@dataclass(frozen=True, slots=True)
class SideScoreSummary:
    """Side-owned summary copied from the canonical SideScore (no breakdown)."""

    side: str
    technical_signal_score: int | None
    setup_score: int | None
    evidence_score: int | None
    evidence_source: str
    execution_quality_score: int | None
    execution_quality_source: str
    reason_codes: tuple[str, ...] = ()

    @classmethod
    def from_side_score(cls, score: SideScore) -> SideScoreSummary:
        if type(score) is not SideScore:
            raise TypeError("expected a Scanner V4 SideScore")
        return cls(
            side=score.side,
            technical_signal_score=score.technical_signal_score,
            setup_score=score.setup_score,
            evidence_score=score.evidence_score,
            evidence_source=score.evidence_source,
            execution_quality_score=score.execution_quality_score,
            execution_quality_source=score.execution_quality_source,
            reason_codes=score.reason_codes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": self.side,
            "technical_signal_score": self.technical_signal_score,
            "setup_score": self.setup_score,
            "evidence_score": self.evidence_score,
            "evidence_source": self.evidence_source,
            "execution_quality_score": self.execution_quality_score,
            "execution_quality_source": self.execution_quality_source,
            "reason_codes": list(self.reason_codes),
        }

    @classmethod
    def from_dict(cls, value: object, *, path: str = "side_score_summary") -> SideScoreSummary:
        if type(value) is not dict:
            raise RowContractError(SCANNER_V4_SCHEMA_INVALID, path, "expected an object")
        expected = {
            "side",
            "technical_signal_score",
            "setup_score",
            "evidence_score",
            "evidence_source",
            "execution_quality_score",
            "execution_quality_source",
            "reason_codes",
        }
        unknown = sorted(set(value) - expected)
        missing = sorted(expected - set(value))
        if unknown or missing:
            raise RowContractError(
                SCANNER_V4_SCHEMA_INVALID,
                path,
                f"unknown={unknown} missing={missing}",
            )
        side = _require_text(value["side"], f"{path}.side")
        if side not in VALID_SIDES:
            raise RowContractError(SCANNER_V4_SCHEMA_INVALID, f"{path}.side", "invalid side")
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
            reason_codes=_parse_codes(value["reason_codes"], f"{path}.reason_codes"),
        )


@dataclass(frozen=True, slots=True)
class ScannerV4Row:
    """Canonical-only V4 scanner row (10A; strict, no legacy fallback)."""

    row_version: str
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
    side_scores: tuple[SideScoreSummary, ...]
    selected_technical_signal_score: int | None
    selected_setup_score: int | None
    safety_status: str
    safety_reason_codes: tuple[str, ...]
    macro_status: str
    macro_reason_codes: tuple[str, ...]
    gate_codes: tuple[str, ...]
    reason_codes: tuple[str, ...]
    block_codes: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "row_version": self.row_version,
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
            "selected_technical_signal_score": self.selected_technical_signal_score,
            "selected_setup_score": self.selected_setup_score,
            "safety_status": self.safety_status,
            "safety_reason_codes": list(self.safety_reason_codes),
            "macro_status": self.macro_status,
            "macro_reason_codes": list(self.macro_reason_codes),
            "gate_codes": list(self.gate_codes),
            "reason_codes": list(self.reason_codes),
            "block_codes": list(self.block_codes),
        }


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def scanner_v4_row_from_composition(
    composition: ScannerV4CompositionResult,
) -> ScannerV4Row:
    """Build the canonical-only V4 scanner row for one composition result.

    Reads exclusively the Step 07 ``canonical`` artifact (which already owned
    side scores, gates and identity) plus the composition decision.  Nothing is
    re-scored and no V3 scored/legacy field is ever read.
    """
    if type(composition) is not ScannerV4CompositionResult:
        raise TypeError("expected a ScannerV4CompositionResult")
    canonical: CanonicalPairSnapshot = composition.canonical
    if composition.snapshot_id != canonical.snapshot_id:
        raise CompositionInputError(
            "row.snapshot_id",
            "composition.snapshot_id differs from canonical.snapshot_id",
        )
    side_scores = tuple(
        SideScoreSummary.from_side_score(score) for score in canonical.side_scores
    )
    if set(s.side for s in side_scores) != set(VALID_SIDES) or len(side_scores) != 2:
        raise CompositionInputError(
            "row.canonical.side_scores",
            "canonical snapshot must carry exactly buy and sell side scores",
        )

    # Selected-side scores come from the canonical side score of the selected
    # side only.  When there is no selected side the scores are explicit None —
    # never zero-aggregated from V3-style side totals.
    selected = composition.decision.selected_side
    selected_scores = [s for s in side_scores if s.side == selected]
    if selected is not None and not selected_scores:
        raise CompositionInputError(
            "row.selected_side",
            f"canonical has no side score for the selected side {selected!r}",
        )
    selected_technical = selected_scores[0].technical_signal_score if selected_scores else None
    selected_setup = selected_scores[0].setup_score if selected_scores else None

    return ScannerV4Row(
        row_version=SCANNER_V4_ROW_VERSION,
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
        selected_side=selected,
        score_gap=composition.decision.score_gap,
        decision_cap=composition.decision.decision_cap,
        side_scores=side_scores,
        selected_technical_signal_score=selected_technical,
        selected_setup_score=selected_setup,
        safety_status=canonical.market_safety.status,
        safety_reason_codes=canonical.market_safety.reason_codes,
        macro_status=canonical.macro_gate.status,
        macro_reason_codes=canonical.macro_gate.reason_codes,
        gate_codes=composition.decision.gate_codes,
        reason_codes=composition.decision.reason_codes,
        block_codes=composition.decision.block_codes,
    )


def blocked_scanner_row_v4(
    symbol: str,
    reason_codes: list[str] | tuple[str, ...],
    *,
    captured_at: datetime | None = None,
    snapshot_id: str | None = None,
) -> ScannerV4Row:
    """Full-schema ``DATA_UNAVAILABLE`` V4 row (10A; no fabricated values).

    Deliberately NOT the V3 ``blocked_scanner_row`` shape
    (``core/scanner.py:355-402``) which hardcodes ``macro_score = 15`` and
    zeroed ``buy_score``/``sell_score``.  A V4 blocked row keeps the full
    identity shape but reports technical/setup as ``None`` and Safety/Macro as
    ``UNKNOWN`` with the given reason codes — no macro 15, no neutral score
    fabrications, no legacy fallback.
    """
    if type(symbol) is not str or not symbol:
        raise ValueError("symbol must be a non-empty string")
    codes = _as_codes(reason_codes)
    if not codes:
        raise ValueError("a blocked row requires at least one reason code")
    if captured_at is None:
        captured_at = datetime.now(timezone.utc)
    if snapshot_id is None:
        # Deterministic non-empty id for a blocked (data-unavailable) row.
        snapshot_id = (
            f"v4:blocked:{symbol}:{captured_at.astimezone(timezone.utc).isoformat()}"
        )
    identity = _blocked_identity()
    return ScannerV4Row(
        row_version=SCANNER_V4_ROW_VERSION,
        composition_version=COMPOSITION_POLICY_VERSION,
        scoring_version=identity["scoring_version"],
        feature_version=identity["feature_version"],
        output_schema_version=identity["output_schema_version"],
        safety_policy_version=identity["safety_policy_version"],
        macro_policy_version=identity["macro_policy_version"],
        snapshot_version=identity["snapshot_version"],
        snapshot_id=snapshot_id,
        symbol=symbol,
        captured_at=captured_at,
        capture_source="live",
        candidate_status=DATA_UNAVAILABLE,
        selected_side=None,
        score_gap=None,
        decision_cap=None,
        side_scores=(),
        selected_technical_signal_score=None,
        selected_setup_score=None,
        safety_status=UNKNOWN,
        safety_reason_codes=codes,
        macro_status=UNKNOWN,
        macro_reason_codes=codes,
        gate_codes=codes,
        reason_codes=codes,
        block_codes=(),
    )


def _as_codes(codes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(codes, (list, tuple)):
        raise TypeError("reason codes must be a list or tuple")
    result: list[str] = []
    for code in codes:
        if type(code) is not str or not code:
            raise ValueError("reason codes must be non-empty strings")
        if code not in result:
            result.append(code)
    return tuple(result)


def _blocked_identity() -> dict[str, str]:
    """Version identity for a blocked row (same locked V4 constants)."""
    from core.scanner_v4_models import (
        SCANNER_V4_FEATURE_VERSION,
        SCANNER_V4_MACRO_POLICY_VERSION,
        SCANNER_V4_OUTPUT_SCHEMA_VERSION,
        SCANNER_V4_SAFETY_POLICY_VERSION,
        SCANNER_V4_SCORING_VERSION,
        SCANNER_V4_SNAPSHOT_VERSION,
    )

    return {
        "scoring_version": SCANNER_V4_SCORING_VERSION,
        "feature_version": SCANNER_V4_FEATURE_VERSION,
        "output_schema_version": SCANNER_V4_OUTPUT_SCHEMA_VERSION,
        "safety_policy_version": SCANNER_V4_SAFETY_POLICY_VERSION,
        "macro_policy_version": SCANNER_V4_MACRO_POLICY_VERSION,
        "snapshot_version": SCANNER_V4_SNAPSHOT_VERSION,
    }


# ---------------------------------------------------------------------------
# Strict reader for an already-persisted V4 row (target-only; V3/missing
# identity is refused, never downgraded into a V4 row).
# ---------------------------------------------------------------------------


def scanner_v4_row_from_dict(value: object, *, path: str = "scanner_v4_row") -> ScannerV4Row:
    """Strict deserializer of a persisted V4 row.

    Refuses rows that are not stamped ``scanner-v4-row-v1`` with the locked V4
    versions.  A V3 row (e.g. one from the executable ``core/scanner.py`` whose
    ``row_version`` is missing) is refused — never reloaded as a V4 row.
    """
    if type(value) is not dict:
        raise RowContractError(
            SCANNER_V4_SCHEMA_INVALID, path, "external payload must use a JSON object"
        )
    unknown_fields = sorted(LEGACY_SCORED_FIELDS.intersection(value))
    if unknown_fields:
        raise RowContractError(
            SCANNER_V4_FORBIDDEN_SCORED_FIELD,
            path,
            f"forbidden V3 scored fields in V4 row: {unknown_fields}",
        )
    if "row_version" not in value:
        raise RowContractError(
            SCANNER_V4_VERSION_MISSING, f"{path}.row_version", "missing row_version"
        )
    if value.get("row_version") != SCANNER_V4_ROW_VERSION:
        raise RowContractError(
            SCANNER_V4_VERSION_MISMATCH,
            f"{path}.row_version",
            f"unsupported row version {value.get('row_version')!r}",
        )
    missing = sorted(ROW_KEYS - set(value))
    if missing:
        raise RowContractError(
            SCANNER_V4_SCHEMA_INVALID, path, f"missing required fields: {missing}"
        )
    return ScannerV4Row(
        row_version=SCANNER_V4_ROW_VERSION,
        composition_version=_require_exact_version(
            value["composition_version"],
            COMPOSITION_POLICY_VERSION,
            f"{path}.composition_version",
        ),
        scoring_version=_require_exact_version(
            value["scoring_version"], SCANNER_V4_SCORING_VERSION, f"{path}.scoring_version"
        ),
        feature_version=_require_exact_version(
            value["feature_version"], SCANNER_V4_FEATURE_VERSION, f"{path}.feature_version"
        ),
        output_schema_version=_require_exact_version(
            value["output_schema_version"],
            SCANNER_V4_OUTPUT_SCHEMA_VERSION,
            f"{path}.output_schema_version",
        ),
        safety_policy_version=_require_exact_version(
            value["safety_policy_version"],
            SCANNER_V4_SAFETY_POLICY_VERSION,
            f"{path}.safety_policy_version",
        ),
        macro_policy_version=_require_exact_version(
            value["macro_policy_version"],
            SCANNER_V4_MACRO_POLICY_VERSION,
            f"{path}.macro_policy_version",
        ),
        snapshot_version=_require_exact_version(
            value["snapshot_version"],
            SCANNER_V4_SNAPSHOT_VERSION,
            f"{path}.snapshot_version",
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
            SideScoreSummary.from_dict(item, path=f"{path}.side_scores[{index}]")
            for index, item in enumerate(_require_list(value["side_scores"], f"{path}.side_scores"))
        ),
        selected_technical_signal_score=_optional_int(
            value["selected_technical_signal_score"],
            f"{path}.selected_technical_signal_score",
        ),
        selected_setup_score=_optional_int(
            value["selected_setup_score"], f"{path}.selected_setup_score"
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
        reason_codes=_parse_codes(value["reason_codes"], f"{path}.reason_codes"),
        block_codes=_parse_codes(value["block_codes"], f"{path}.block_codes"),
    )


def _require_list(value: object, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise RowContractError(SCANNER_V4_SCHEMA_INVALID, path, "expected an array")
    return value


def _require_text(value: object, path: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise RowContractError(SCANNER_V4_SCHEMA_INVALID, path, "expected a string")
    if not allow_empty and not value:
        raise RowContractError(SCANNER_V4_SCHEMA_INVALID, path, "expected a non-empty string")
    return value


def _require_exact_version(value: object, expected: str, path: str) -> str:
    """Require the EXACT locked V4 identity string (reject V3/mixed/unknown)."""
    if type(value) is not str or value != expected:
        raise RowContractError(
            SCANNER_V4_VERSION_MISMATCH, path, f"expected {expected!r}, got {value!r}"
        )
    return value


def _optional_int(value: object, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise RowContractError(SCANNER_V4_SCHEMA_INVALID, path, "expected int or null")
    return value


def _parse_datetime(value: object, path: str) -> datetime:
    text = _require_text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise RowContractError(
            SCANNER_V4_SCHEMA_INVALID, path, f"invalid ISO datetime: {exc}"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RowContractError(SCANNER_V4_SCHEMA_INVALID, path, "must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_codes(value: object, path: str) -> tuple[str, ...]:
    result: list[str] = []
    for index, item in enumerate(_require_list(value, path)):
        if type(item) is not str or not item:
            raise RowContractError(
                SCANNER_V4_SCHEMA_INVALID, f"{path}[{index}]", "expected a code"
            )
        result.append(item)
    return tuple(result)