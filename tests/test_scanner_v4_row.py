"""Scanner V4 row/API consumer tests (Bước 10; target-only; 10A).

Proves the canonical-only V4 row contract:

* the row reads ONLY canonical side-owned scores + composition decision, and
  emits the full output/schema/policy identity, selected side, TechnicalScore,
  SetupScore, Safety/Macro status + cap and reason codes;
* ``blocked_scanner_row_v4`` is a full-schema ``DATA_UNAVAILABLE`` row with
  **null** technical/setup and Safety/Macro ``UNKNOWN`` — never the V3
  «macro 15 / zeroed buy/sell» shape;
* the persisted-row reader is strict: V3 scored fields, missing or mismatched
  row version are refused (no downgrade into a V4 row).

Runtime isolation: this test also asserts the V3 scanner runtime never imports
the V4 row module (no partial V4 activation before cutover).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.reason_codes import (
    SCANNER_V4_FORBIDDEN_SCORED_FIELD,
    SCANNER_V4_SCHEMA_INVALID,
    SCANNER_V4_VERSION_MISMATCH,
    SCANNER_V4_VERSION_MISSING,
)
from core.scanner_v4_composition import COMPOSITION_POLICY_VERSION
from core.scanner_v4_models import (
    BUY,
    DATA_UNAVAILABLE,
    UNKNOWN,
    VALID_CANDIDATE_STATUSES,
)
from core.scanner_v4_row import (
    LEGACY_SCORED_FIELDS,
    ROW_KEYS,
    SCANNER_V4_ROW_VERSION,
    RowContractError,
    ScannerV4Row,
    blocked_scanner_row_v4,
    scanner_v4_row_from_composition,
    scanner_v4_row_from_dict,
)

from tests.test_scanner_v4_composition import _compose, _run, _snapshot

_CAPTURED = datetime(2026, 8, 13, 12, 0, 0, tzinfo=timezone.utc)


class TestRowFromComposition:
    def test_canonical_only_when_default_composition(self):
        row = scanner_v4_row_from_composition(_run())
        assert row.row_version == SCANNER_V4_ROW_VERSION
        assert row.composition_version == COMPOSITION_POLICY_VERSION
        assert row.scoring_version == "scanner-v4"
        assert row.feature_version == "scanner-features-v4"
        assert row.candidate_status in VALID_CANDIDATE_STATUSES
        assert {s.side for s in row.side_scores} == {BUY, "sell"}

    def test_full_version_identity_emitted(self):
        row = scanner_v4_row_from_composition(_run())
        assert {
            "row_version",
            "composition_version",
            "scoring_version",
            "feature_version",
            "output_schema_version",
            "safety_policy_version",
            "macro_policy_version",
            "snapshot_version",
        } <= set(row.to_dict())
        assert row.to_dict()["composition_version"] == COMPOSITION_POLICY_VERSION

    def test_selected_side_scores_come_from_canonical_side_score(self):
        composition = _run()
        row = scanner_v4_row_from_composition(composition)
        selected = row.selected_side
        if selected is not None:
            canonical_score = composition.canonical.side_score(selected)
            assert row.selected_technical_signal_score == canonical_score.technical_signal_score
            assert row.selected_setup_score == canonical_score.setup_score

    def test_side_score_summaries_never_carry_breakdown(self):
        row = scanner_v4_row_from_composition(_run())
        for summary in row.side_scores:
            payload = summary.to_dict()
            assert "technical_breakdown" not in payload
            assert payload["side"] == row.side_scores[0].side or payload["side"] == "sell"

    def test_typed_input_required(self):
        with pytest.raises(TypeError):
            scanner_v4_row_from_composition({"not": "a composition"})


class TestNoLegacyScoredFields:
    def test_row_never_contains_any_v3_scored_field(self):
        row = scanner_v4_row_from_composition(_run())
        payload = row.to_dict()
        assert LEGACY_SCORED_FIELDS.isdisjoint(set(payload))
        assert "risk_condition" not in payload
        assert "macro_alignment" not in payload
        assert "buy_score" not in payload and "sell_score" not in payload

    def test_blocked_row_has_no_fabricated_macro_or_zero_scores(self):
        row = blocked_scanner_row_v4("XAUUSD", ("SOME_BLOCK",), captured_at=_CAPTURED)
        payload = row.to_dict()
        assert "macro_score" not in payload
        assert "buy_score" not in payload and "sell_score" not in payload
        assert "scanner_action" not in payload


class TestBlockedRow:
    def test_full_schema_data_unavailable_blocked_row(self):
        row = blocked_scanner_row_v4(
            "XAUUSD",
            ("SAFETY_MT5_NOT_READY",),
            captured_at=_CAPTURED,
            snapshot_id="v4:XAUUSD:snap",
        )
        assert row.candidate_status == DATA_UNAVAILABLE
        assert row.selected_side is None
        assert row.score_gap is None and row.decision_cap is None
        # technical / setup are explicit None — nothing fabricated
        assert row.selected_technical_signal_score is None
        assert row.selected_setup_score is None
        # Safety/Macro fail closed to UNKNOWN, never to a neutral/pass value
        assert row.safety_status == UNKNOWN
        assert row.macro_status == UNKNOWN
        assert row.side_scores == ()
        assert "SAFETY_MT5_NOT_READY" in row.reason_codes
        assert "SAFETY_MT5_NOT_READY" in row.safety_reason_codes

    def test_blocked_row_version_identity_present(self):
        row = blocked_scanner_row_v4("XAUUSD", ("SOME_BLOCK",), captured_at=_CAPTURED)
        assert row.row_version == SCANNER_V4_ROW_VERSION
        for key in ("scoring_version", "feature_version", "output_schema_version",
                    "safety_policy_version", "macro_policy_version", "snapshot_version"):
            assert row.to_dict()[key]

    def test_blocked_row_requires_symbol(self):
        with pytest.raises(ValueError):
            blocked_scanner_row_v4("", ("SOME_BLOCK",))

    def test_blocked_row_requires_at_least_one_reason(self):
        with pytest.raises(ValueError):
            blocked_scanner_row_v4("XAUUSD", ())


class TestStrictReader:
    def test_round_trip(self):
        row = scanner_v4_row_from_composition(_run())
        restored = scanner_v4_row_from_dict(row.to_dict())
        # identity/status round-trips byte-for-byte
        assert restored.to_dict()["snapshot_id"] == row.snapshot_id
        assert restored.to_dict()["candidate_status"] == row.candidate_status
        assert {s.side for s in restored.side_scores} == {s.side for s in row.side_scores}
        assert restored.row_version == SCANNER_V4_ROW_VERSION

    def test_round_trip_blocked_row(self):
        row = blocked_scanner_row_v4("XAUUSD", ("SOME_BLOCK",), captured_at=_CAPTURED)
        restored = scanner_v4_row_from_dict(row.to_dict())
        assert restored.candidate_status == DATA_UNAVAILABLE
        assert restored.safety_status == UNKNOWN
        assert restored.selected_setup_score is None

    def test_refuses_v3_scored_fields(self):
        payload = scanner_v4_row_from_composition(_run()).to_dict()
        payload["risk_condition"] = "high_risk"
        payload["macro_alignment"] = "aligned"
        with pytest.raises(RowContractError) as exc:
            scanner_v4_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_FORBIDDEN_SCORED_FIELD

    def test_refuses_missing_row_version(self):
        payload = scanner_v4_row_from_composition(_run()).to_dict()
        del payload["row_version"]
        with pytest.raises(RowContractError) as exc:
            scanner_v4_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_VERSION_MISSING

    def test_refuses_mismatched_row_version(self):
        payload = scanner_v4_row_from_composition(_run()).to_dict()
        payload["row_version"] = "scanner-v3-row"
        with pytest.raises(RowContractError) as exc:
            scanner_v4_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_VERSION_MISMATCH

    def test_refuses_non_dict_payload(self):
        with pytest.raises(RowContractError) as exc:
            scanner_v4_row_from_dict(["not", "a", "dict"])
        assert exc.value.code == SCANNER_V4_SCHEMA_INVALID

    def test_refuses_missing_required_fields(self):
        payload = scanner_v4_row_from_composition(_run()).to_dict()
        del payload["side_scores"]
        with pytest.raises(RowContractError) as exc:
            scanner_v4_row_from_dict(payload)
        assert exc.value.code == SCANNER_V4_SCHEMA_INVALID


class TestRuntimeIsolation10A:
    """The V4 row consumer must never leak into the V3 executable runtime."""

    def test_v3_runtime_files_do_not_reference_v4_consumers(self):
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[1]
        v3_runtime = [
            "core/scanner.py",
            "ui/screens/scanner_detail_screen.py",
            "controllers/scanner_controller.py",
            "services/journal_converters.py",
            "services/journal_models.py",
        ]
        for rel in v3_runtime:
            path = project_root / rel
            text = path.read_text(encoding="utf-8")
            assert "scanner_v4_row" not in text, f"{rel} must not import the V4 row"
            assert "scanner_v4_presentation" not in text, f"{rel} must not import V4 presentation"
            assert "scanner_v4_snapshot" not in text, f"{rel} must not import the V4 snapshot"