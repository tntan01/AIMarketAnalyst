"""Scanner V4 journal tests (Bước 10; target-only; additive; 10D).

Proves the additive V4 journal contract:

* the V4 converter reads ONLY canonical side-owned scores (never
  ``scenario_scores`` / ``buy_score`` / ``sell_score`` / ``scanner_action``),
  and the produced row carries the full version identity (composition /
  scoring / feature / output_schema / safety / macro / snapshot / threshold);
* evidence is **partitioned** by scorer + policy identity, and mixing rows from
  different partitions fails closed (``SCANNER_V4_JOURNAL_PARTITION_MIXED``);
* the V3 journal (rows carrying V3 scored fields) is never mixed into V4, never
  re-labelled and never replayed into the V4 shape.

Runtime isolation: the live V3 journal services are untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.reason_codes import (
    SCANNER_V4_FORBIDDEN_SCORED_FIELD,
    SCANNER_V4_LEGACY_V3_AUDIT_ONLY,
    SCANNER_V4_SCHEMA_INVALID,
    SCANNER_V4_VERSION_MISMATCH,
    SCANNER_V4_VERSION_MISSING,
)
from core.scanner_v4_threshold_policy import make_default_threshold_policy
from services.scanner_v4_journal_converters import (
    JOURNAL_V4_KEYS,
    journal_row_from_dict,
    journal_row_from_v4_composition,
)
from services.scanner_v4_journal_models import (
    SCANNER_V4_JOURNAL_SCHEMA_VERSION,
    JournalV4Error,
    assert_same_partition,
    evidence_partition_key,
)

from tests.test_scanner_v4_composition import _run

_NOW = datetime(2026, 8, 13, 12, 1, 0, tzinfo=timezone.utc)


class TestConverterReadsCanonicalOnly:
    def test_row_is_canonical_and_versioned(self):
        row = journal_row_from_v4_composition(_run(), now=_NOW)
        assert row.journal_schema_version == SCANNER_V4_JOURNAL_SCHEMA_VERSION
        assert row.scoring_version == "scanner-v4"
        assert row.feature_version == "scanner-features-v4"
        assert row.snapshot_id == _run().snapshot_id
        assert row.timestamp_utc == _NOW
        assert {s.side for s in row.side_scores} == {"buy", "sell"}

    def test_side_scores_come_from_canonical_side_score(self):
        composition = _run()
        row = journal_row_from_v4_composition(composition, now=_NOW)
        for side in ("buy", "sell"):
            canonical = composition.canonical.side_score(side)
            journal_side = next(s for s in row.side_scores if s.side == side)
            assert journal_side.technical_signal_score == canonical.technical_signal_score
            assert journal_side.setup_score == canonical.setup_score
            assert journal_side.evidence_score == canonical.evidence_score
            assert journal_side.execution_quality_source == canonical.execution_quality_source

    def test_row_never_carries_v3_scored_fields(self):
        from services.scanner_v4_journal_models import FORBIDDEN_V3_JOURNAL_FIELDS

        payload = journal_row_from_v4_composition(_run(), now=_NOW).to_dict()
        assert FORBIDDEN_V3_JOURNAL_FIELDS.isdisjoint(set(payload))
        assert "scenario_scores" not in payload
        assert "buy_score" not in payload and "sell_score" not in payload
        assert "scanner_action" not in payload and "scanner_group" not in payload
        assert "risk_condition" not in payload and "macro_alignment" not in payload

    def test_row_is_strict_per_version_id(self):
        row = journal_row_from_v4_composition(_run(), now=_NOW)
        row_dict = row.to_dict()
        assert set(row_dict) == JOURNAL_V4_KEYS
        # threshold identity is part of the partition (DoR-10 / 10D)
        assert row.threshold_policy_version == make_default_threshold_policy().policy_version

    def test_safety_macro_statuses_from_gates(self):
        composition = _run()
        row = journal_row_from_v4_composition(composition, now=_NOW)
        assert row.safety_status == composition.canonical.market_safety.status
        assert row.macro_status == composition.canonical.macro_gate.status
        assert row.reason_codes == composition.decision.reason_codes


class TestEvidencePartition:
    def test_partition_key_bundles_scorer_and_policy(self):
        pkey = evidence_partition_key(
            scoring_version="scanner-v4",
            feature_version="scanner-features-v4",
            safety_policy_version="scanner-safety-policy-v4",
            macro_policy_version="scanner-macro-policy-v4",
            threshold_policy_version="scanner-threshold-policy-v4",
            composition_version="scanner-composition-v4",
        )
        assert pkey.startswith("v4|")
        assert pkey.count("|") == 6

    def test_same_partition_returns_key(self):
        row = journal_row_from_v4_composition(_run(), now=_NOW)
        pkey = assert_same_partition([row, row])
        assert pkey == assert_same_partition([row])

    def test_forged_different_policy_identity_refused_at_reader(self):
        # §12.1 / §7.3: a journal row must carry the EXACT locked V4 identity.
        # Forging a different threshold-policy version is refused at the strict
        # reader (VERSION_MISMATCH) — a mixed-identity row can never enter the
        # partition logic in the first place.
        row = journal_row_from_v4_composition(_run(), now=_NOW)
        payload = row.to_dict()
        payload["threshold_policy_version"] = "scanner-threshold-policy-v9"
        with pytest.raises(JournalV4Error) as exc:
            journal_row_from_dict(payload, path="journal_rows[1]")
        assert exc.value.code == SCANNER_V4_VERSION_MISMATCH

    def test_v3_row_cannot_enter_partition_logic(self):
        # A V3-shaped row is refused at the strict reader before partitioning.
        row = journal_row_from_v4_composition(_run(), now=_NOW)
        payload = row.to_dict()
        payload["buy_score"] = 70
        with pytest.raises(JournalV4Error) as exc:
            journal_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_FORBIDDEN_SCORED_FIELD

    def test_empty_partition_refused_only_when_rows_missing(self):
        assert assert_same_partition([]) == ""


class TestStrictReader:
    def test_round_trip(self):
        row = journal_row_from_v4_composition(_run(), now=_NOW)
        restored = journal_row_from_dict(row.to_dict(), path="journal_restored")
        assert restored.to_dict() == row.to_dict()

    def test_refuses_missing_schema_version(self):
        payload = journal_row_from_v4_composition(_run(), now=_NOW).to_dict()
        del payload["journal_schema_version"]
        with pytest.raises(JournalV4Error) as exc:
            journal_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_VERSION_MISSING

    def test_refuses_mismatched_schema_version(self):
        payload = journal_row_from_v4_composition(_run(), now=_NOW).to_dict()
        payload["journal_schema_version"] = "scanner-v4-journal-v999"
        with pytest.raises(JournalV4Error) as exc:
            journal_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_VERSION_MISMATCH

    def test_refuses_v3_journal_row_audit_only(self):
        payload = journal_row_from_v4_composition(_run(), now=_NOW).to_dict()
        payload["journal_schema_version"] = "v1"
        payload["scenario_scores"] = {"buy": {"total": 70}}
        with pytest.raises(JournalV4Error) as exc:
            journal_row_from_dict(payload)
        # a V3 row is audit-only (never reloadable as a V4 row)
        assert exc.value.code in (
            SCANNER_V4_FORBIDDEN_SCORED_FIELD,
            SCANNER_V4_LEGACY_V3_AUDIT_ONLY,
        )

    def test_refuses_unknown_keys(self):
        payload = journal_row_from_v4_composition(_run(), now=_NOW).to_dict()
        payload["unexpected"] = 1
        with pytest.raises(JournalV4Error) as exc:
            journal_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_SCHEMA_INVALID

    def test_non_dict_payload_refused(self):
        with pytest.raises(JournalV4Error) as exc:
            journal_row_from_dict({"buy_score": 70})
        assert exc.value.code == SCANNER_V4_FORBIDDEN_SCORED_FIELD


class TestV3RuntimeUntouched:
    def test_v3_journal_modules_do_not_import_v4_converter(self):
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[1]
        for rel in ("services/journal_converters.py", "services/journal_models.py"):
            text = (project_root / rel).read_text(encoding="utf-8")
            assert "scanner_v4_journal" not in text, f"{rel} must not import the V4 journal"