"""Scanner persistence envelope tests (Bước 10; target-only; 10C).

Proves the compact/full snapshot envelope:

* compact keeps the full identity (versions, snapshot_id, selected side,
  Technical/Setup side scores, candidate status, Safety/Macro status + cap and
  reason codes) and round-trips strictly;
* full additionally embeds the strict composition and round-trips with the
  composition re-validated and the snapshot_id cross-checked;
* a legacy artifact (or any missing/mismatched version) is refused — never
  re-labelled as a live envelope; a legacy payload is audit-only, non-replayable.

Runtime isolation: ``controllers/scanner_controller.py`` keeps its legacy
``persistence_schema_version = 1`` shape and is untouched by the envelope.
"""

from __future__ import annotations

import pytest

from core.reason_codes import (
    SCANNER_FORBIDDEN_SCORED_FIELD,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)
from core.scanner_snapshot import (
    COMPACT_KEYS,
    FULL_KEYS,
    MODE_COMPACT,
    MODE_FULL,
    SCANNER_SNAPSHOT_ENVELOPE_VERSION,
    EnvelopeSideScore,
    SnapshotEnvelopeError,
    build_snapshot_envelope,
    snapshot_envelope_from_dict,
)

from tests.test_scanner_composition import _run

V3_PAYLOAD = {
    "envelope_schema_version": "scanner-v3",
    "persistence_schema_version": 1,
    "scoring_version": "scanner-v3",
    "feature_version": "scanner-features-v3",
    "snapshot_id": "legacy",
    "symbol": "XAUUSD",
    "captured_at": "2026-08-13T12:00:00+00:00",
    "side_scores": {},
    "scanner_action": "TRADE_BLOCKED",
}


class TestCompactEnvelope:
    def test_compact_round_trip_identity_preserved(self):
        env = build_snapshot_envelope(_run(), mode=MODE_COMPACT)
        assert env.mode == MODE_COMPACT
        payload = env.to_dict()
        restored = snapshot_envelope_from_dict(payload)
        assert restored.to_dict() == payload  # byte-for-byte
        assert restored.envelope_schema_version == SCANNER_SNAPSHOT_ENVELOPE_VERSION
        assert restored.snapshot_id == env.snapshot_id
        assert restored.candidate_status == env.candidate_status
        assert restored.selected_side == env.selected_side
        # compact is display/audit-only: never replayable
        assert restored.replayable is False

    def test_compact_carries_side_scores_but_no_composition(self):
        env = build_snapshot_envelope(_run(), mode=MODE_COMPACT)
        assert set(env.to_dict()) == COMPACT_KEYS
        assert "composition" not in env.to_dict()
        assert len(env.side_scores) == 2
        for side in env.side_scores:
            assert side.side in {"buy", "sell"}
            assert side.setup_score is not None

    def test_full_embedding_is_strict_round_trip(self):
        composition = _run()
        full = build_snapshot_envelope(composition, mode=MODE_FULL)
        payload = full.to_dict()
        assert set(payload) == FULL_KEYS
        assert "composition" in payload
        restored = snapshot_envelope_from_dict(payload)
        assert restored.replayable is True
        assert restored.composition == payload["composition"]
        assert restored.snapshot_id == composition.snapshot_id

    def test_invalid_mode_refused(self):
        with pytest.raises(ValueError):
            build_snapshot_envelope(_run(), mode="ultra")

    def test_full_to_dict_without_composition_raises(self):
        env = build_snapshot_envelope(_run(), mode=MODE_FULL)
        # hand-strip the embedded composition: the reader must re-validate and refuse
        payload = env.to_dict()
        del payload["composition"]
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_SCHEMA_INVALID


class TestStrictReaderContract:
    def test_refuses_v3_scored_fields(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_FULL).to_dict()
        payload["risk_condition"] = "high_risk"
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_FORBIDDEN_SCORED_FIELD

    def test_refuses_v3_persistence_version_field(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_COMPACT).to_dict()
        payload["persistence_schema_version"] = 1
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_FORBIDDEN_SCORED_FIELD

    def test_refuses_missing_schema_version(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_COMPACT).to_dict()
        del payload["envelope_schema_version"]
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_VERSION_MISSING

    def test_refuses_mismatched_schema_version(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_COMPACT).to_dict()
        payload["envelope_schema_version"] = "scanner-v4-snapshot-envelope-v999"
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_VERSION_MISMATCH

    def test_refuses_unknown_mode(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_COMPACT).to_dict()
        payload["mode"] = "ultra"
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_VERSION_MISMATCH

    def test_refuses_v3_artifact_audit_only(self):
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(V3_PAYLOAD)
        assert exc.value.code == SCANNER_LEGACY_V3_AUDIT_ONLY

    def test_full_snapshot_id_must_match_embedded_composition(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_FULL).to_dict()
        payload["snapshot_id"] = "v4:forged:snapshot"
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_VERSION_MISMATCH

    def test_full_requires_dict_composition(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_FULL).to_dict()
        payload["composition"] = []
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_SCHEMA_INVALID

    def test_refuses_key_set_mismatch(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_COMPACT).to_dict()
        payload["unexpected"] = True
        with pytest.raises(SnapshotEnvelopeError) as exc:
            snapshot_envelope_from_dict(payload)
        assert exc.value.code == SCANNER_SCHEMA_INVALID


class TestSideScoreStrictRead:
    def test_side_score_refuses_unknown_keys(self):
        env = build_snapshot_envelope(_run(), mode=MODE_COMPACT)
        item = env.to_dict()["side_scores"][0]
        item = dict(item)
        item["total"] = 99
        with pytest.raises(SnapshotEnvelopeError):
            EnvelopeSideScore.from_dict(item, path="test.side[0]")


class TestV3RuntimeUntouched:
    def test_v3_controller_schema_still_unchanged(self):
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[1]
        controller = (project_root / "controllers" / "scanner_controller.py").read_text(
            encoding="utf-8"
        )
        # The legacy controller legitimately houses a `scanner_snapshots` directory and
        # bare `scanner_snapshot` folder names; assert on the envelope
        # exports / import path so those legacy filesystem names are not flagged.
        assert "ScannerSnapshotEnvelope" not in controller
        assert "core.scanner_snapshot" not in controller
        assert "persistence_schema_version" in controller  # legacy shape still present