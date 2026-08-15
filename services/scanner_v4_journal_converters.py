"""Scanner V4 journal converter (Bước 10; target-only; additive).

10D — converter from a canonical composition + candidate into the additive V4
journal row.  The converter reads ONLY the canonical side-owned scores
(``CanonicalPairSnapshot.side_scores``), the composition decision and the V4
identity — it never reads ``scenario_scores.*.total``, ``buy_score``,
``sell_score``, ``scanner_action`` or any other V3 semantics (contrast
``services/journal_converters.py:58-61`` and ``:289-290``).

Migration is additive: the V3 journal table, converters and rows are untouched
(never rewritten or re-labelled).  Evidence rows carry an explicit partition
(see ``scanner_v4_journal_models.evidence_partition``); aggregation refuses to
mix partitions until a reuse decision exists.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.reason_codes import (
    SCANNER_V4_FORBIDDEN_SCORED_FIELD,
    SCANNER_V4_LEGACY_V3_AUDIT_ONLY,
    SCANNER_V4_SCHEMA_INVALID,
    SCANNER_V4_VERSION_MISMATCH,
    SCANNER_V4_VERSION_MISSING,
)
from core.scanner_v4_composition import (
    COMPOSITION_POLICY_VERSION,
    ScannerV4CompositionResult,
)
from core.scanner_v4_threshold_policy import (
    SCANNER_V4_THRESHOLD_POLICY_VERSION,
    ThresholdPolicy,
)
from core.scanner_v4_models import (
    BUY,
    SCANNER_V4_FEATURE_VERSION,
    SCANNER_V4_MACRO_POLICY_VERSION,
    SCANNER_V4_OUTPUT_SCHEMA_VERSION,
    SCANNER_V4_SAFETY_POLICY_VERSION,
    SCANNER_V4_SCORING_VERSION,
    SCANNER_V4_SNAPSHOT_VERSION,
    SELL,
    VALID_SIDES,
)

from services.scanner_v4_journal_models import (
    FORBIDDEN_V3_JOURNAL_FIELDS,
    SCANNER_V4_JOURNAL_SCHEMA_VERSION,
    JournalV4Error,
    JournalV4SideScore,
    ScannerV4JournalRow,
)

JOURNAL_MODE_SNAPSHOT = "snapshot"


def journal_row_from_v4_composition(
    composition: ScannerV4CompositionResult,
    *,
    thresholds: ThresholdPolicy | None = None,
    candidate_side: str | None = None,
    candidate_status: str | None = None,
    now: datetime | None = None,
) -> ScannerV4JournalRow:
    """Build an additive V4 journal row from the canonical composition.

    The row reads only canonical side-owned scores and V4 identity.  When a
    candidate decision exists it is used for ``selected_side`` /
    ``candidate_status`` (defaulting to the composition decision otherwise).
    ``thresholds`` provides the threshold policy identity for the partition
    key when provided (defaults to the test-policy identity otherwise — the
    row is still *written* V4, but partition key always includes the threshold
    policy version).
    """
    if type(composition) is not ScannerV4CompositionResult:
        raise TypeError("expected a ScannerV4CompositionResult")
    canonical = composition.canonical
    token = composition

    def _side_score(side: str) -> JournalV4SideScore:
        score = canonical.side_score(side)
        return JournalV4SideScore(
            side=side,
            technical_signal_score=score.technical_signal_score,
            setup_score=score.setup_score,
            evidence_score=score.evidence_score,
            evidence_source=score.evidence_source,
            execution_quality_score=score.execution_quality_score,
            execution_quality_source=score.execution_quality_source,
        )

    selected_side = (
        candidate_side if candidate_side is not None else composition.decision.selected_side
    )
    if selected_side is not None and selected_side not in VALID_SIDES:
        raise JournalV4Error(
            SCANNER_V4_SCHEMA_INVALID, "selected_side", "invalid side"
        )
    candidate_status = (
        candidate_status
        if candidate_status is not None
        else composition.decision.candidate_status
    )
    threshold_version = (
        thresholds.policy_version
        if thresholds is not None
        else "scanner-threshold-policy-v4"
    )
    if now is None:
        now = datetime.now(timezone.utc)

    return ScannerV4JournalRow(
        journal_schema_version=SCANNER_V4_JOURNAL_SCHEMA_VERSION,
        composition_version=token.to_dict()["composition_version"],
        scoring_version=canonical.scoring_version,
        feature_version=canonical.feature_version,
        output_schema_version=canonical.output_schema_version,
        safety_policy_version=canonical.safety_policy_version,
        macro_policy_version=canonical.macro_policy_version,
        snapshot_version=canonical.snapshot_version,
        threshold_policy_version=threshold_version,
        snapshot_id=canonical.snapshot_id,
        symbol=canonical.symbol,
        captured_at=canonical.captured_at,
        timestamp_utc=now,
        selected_side=selected_side,
        candidate_status=candidate_status,
        score_gap=composition.decision.score_gap,
        decision_cap=composition.decision.decision_cap,
        side_scores=(_side_score(BUY), _side_score(SELL)),
        safety_status=canonical.market_safety.status,
        safety_reason_codes=canonical.market_safety.reason_codes,
        macro_status=canonical.macro_gate.status,
        macro_reason_codes=canonical.macro_gate.reason_codes,
        gate_codes=composition.decision.gate_codes,
        block_codes=composition.decision.block_codes,
        reason_codes=composition.decision.reason_codes,
    )


# ---------------------------------------------------------------------------
# Strict reader for persisted V4 journal rows
# ---------------------------------------------------------------------------


JOURNAL_V4_KEYS = frozenset(
    {
        "journal_schema_version",
        "composition_version",
        "scoring_version",
        "feature_version",
        "output_schema_version",
        "safety_policy_version",
        "macro_policy_version",
        "snapshot_version",
        "threshold_policy_version",
        "snapshot_id",
        "symbol",
        "captured_at",
        "timestamp_utc",
        "selected_side",
        "candidate_status",
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


def journal_row_from_dict(value: object, *, path: str = "journal_row_v4") -> ScannerV4JournalRow:
    """Strict reader for a persisted V4 journal row.

    Refuses V3-shaped rows (any ``FORBIDDEN_V3_JOURNAL_FIELDS`` present), a
    missing/mismatched ``journal_schema_version``, or unexpected shape.  Never
    rewrites or re-labels a V3 row as V4.
    """
    if type(value) is not dict:
        raise JournalV4Error(
            SCANNER_V4_SCHEMA_INVALID, path, "external payload must be a JSON object"
        )
    forbidden = sorted(FORBIDDEN_V3_JOURNAL_FIELDS.intersection(value))
    if forbidden:
        raise JournalV4Error(
            SCANNER_V4_FORBIDDEN_SCORED_FIELD,
            path,
            f"forbidden V3 journal fields in V4 row: {forbidden}",
        )
    schema = value.get("journal_schema_version")
    if schema is None:
        raise JournalV4Error(
            SCANNER_V4_VERSION_MISSING,
            f"{path}.journal_schema_version",
            "missing journal_schema_version",
        )
    if schema != SCANNER_V4_JOURNAL_SCHEMA_VERSION:
        if schema in ("scanner-v3", "phase-*") or str(schema).startswith("v1"):
            raise JournalV4Error(
                SCANNER_V4_LEGACY_V3_AUDIT_ONLY,
                f"{path}.journal_schema_version",
                "V3 journal rows are audit-only and non-replayable",
            )
        raise JournalV4Error(
            SCANNER_V4_VERSION_MISMATCH,
            f"{path}.journal_schema_version",
            f"unsupported journal schema {schema!r}",
        )
    if set(value) != JOURNAL_V4_KEYS:
        raise JournalV4Error(
            SCANNER_V4_SCHEMA_INVALID,
            path,
            f"journal row key set mismatch: unknown="
            f"{sorted(set(value) - JOURNAL_V4_KEYS)}",
        )
    if not isinstance(value["side_scores"], list):
        raise JournalV4Error(SCANNER_V4_SCHEMA_INVALID, f"{path}.side_scores", "expected array")

    def _read_side(item: object, index: int) -> JournalV4SideScore:
        if type(item) is not dict:
            raise JournalV4Error(
                SCANNER_V4_SCHEMA_INVALID, f"{path}.side_scores[{index}]", "expected object"
            )
        side = item.get("side")
        if side not in VALID_SIDES:
            raise JournalV4Error(
                SCANNER_V4_SCHEMA_INVALID, f"{path}.side_scores[{index}].side", "invalid side"
            )
        return JournalV4SideScore(
            side=side,
            technical_signal_score=_optional_int(
                item.get("technical_signal_score"),
                f"{path}.side_scores[{index}].technical_signal_score",
            ),
            setup_score=_optional_int(
                item.get("setup_score"), f"{path}.side_scores[{index}].setup_score"
            ),
            evidence_score=_optional_int(
                item.get("evidence_score"), f"{path}.side_scores[{index}].evidence_score"
            ),
            evidence_source=_require_text(
                item.get("evidence_source", ""),
                f"{path}.side_scores[{index}].evidence_source",
                allow_empty=True,
            ),
            execution_quality_score=_optional_int(
                item.get("execution_quality_score"),
                f"{path}.side_scores[{index}].execution_quality_score",
            ),
            execution_quality_source=_require_text(
                item.get("execution_quality_source", ""),
                f"{path}.side_scores[{index}].execution_quality_source",
                allow_empty=True,
            ),
        )

    return ScannerV4JournalRow(
        journal_schema_version=SCANNER_V4_JOURNAL_SCHEMA_VERSION,
        composition_version=_require_exact_version(
            value["composition_version"], COMPOSITION_POLICY_VERSION, f"{path}.composition_version"
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
            value["snapshot_version"], SCANNER_V4_SNAPSHOT_VERSION, f"{path}.snapshot_version"
        ),
        threshold_policy_version=_require_exact_version(
            value["threshold_policy_version"],
            SCANNER_V4_THRESHOLD_POLICY_VERSION,
            f"{path}.threshold_policy_version",
        ),
        snapshot_id=_require_text(value["snapshot_id"], f"{path}.snapshot_id"),
        symbol=_require_text(value["symbol"], f"{path}.symbol"),
        captured_at=_parse_datetime(value["captured_at"], f"{path}.captured_at"),
        timestamp_utc=_parse_datetime(value["timestamp_utc"], f"{path}.timestamp_utc"),
        selected_side=(
            None
            if value["selected_side"] is None
            else _require_text(value["selected_side"], f"{path}.selected_side")
        ),
        candidate_status=_require_text(
            value["candidate_status"], f"{path}.candidate_status"
        ),
        score_gap=_optional_int(value["score_gap"], f"{path}.score_gap"),
        decision_cap=(
            None
            if value["decision_cap"] is None
            else _require_text(value["decision_cap"], f"{path}.decision_cap")
        ),
        side_scores=tuple(_read_side(item, index) for index, item in enumerate(value["side_scores"])),
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
    )


def _require_text(value: object, path: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise JournalV4Error(SCANNER_V4_SCHEMA_INVALID, path, "expected a string")
    if not allow_empty and not value:
        raise JournalV4Error(SCANNER_V4_SCHEMA_INVALID, path, "expected a non-empty string")
    return value


def _require_exact_version(value: object, expected: str, path: str) -> str:
    """Require the EXACT locked V4 identity string (reject V3/mixed/unknown)."""
    if type(value) is not str or value != expected:
        raise JournalV4Error(
            SCANNER_V4_VERSION_MISMATCH, path, f"expected {expected!r}, got {value!r}"
        )
    return value


def _optional_int(value: object, path: str) -> int | None:
    if value is None:
        return None
    if type(value) is not int:
        raise JournalV4Error(SCANNER_V4_SCHEMA_INVALID, path, "expected int or null")
    return value


def _parse_datetime(value: object, path: str) -> datetime:
    text = _require_text(value, path)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (ValueError, OverflowError) as exc:
        raise JournalV4Error(
            SCANNER_V4_SCHEMA_INVALID, path, f"invalid ISO datetime: {exc}"
        )
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JournalV4Error(SCANNER_V4_SCHEMA_INVALID, path, "must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _parse_codes(value: object, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise JournalV4Error(SCANNER_V4_SCHEMA_INVALID, path, "expected an array")
    return tuple(
        _require_text(item, f"{path}[{index}]")
        for index, item in enumerate(value)
    )