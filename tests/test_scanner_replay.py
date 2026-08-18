"""Scanner strict replay tests (Bước 10; target-only; 10C).

Proves deterministic, strict replay:

* a ``full`` envelope is the only replayable artifact; replay routes the
  embedded composition through the single decision path and compares the
  replayed candidate byte-for-byte against the stored envelope fields;
* a ``compact`` envelope, a legacy snapshot and a missing/mismatched-version
  payload are **non-replayable** — refused, never routed through the decision path,
  never rewritten;
* replay is deterministic: the same envelope + same threshold policy produce
  the same outcome every run, and an actor change (entry confirmation) is
  *detected* as a mismatch (the stored fields stay authoritative).
"""

from __future__ import annotations

import pytest

from core.reason_codes import (
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)
from core.scanner_replay import (
    SCANNER_REPLAY_VERSION,
    SnapshotReplayOutcome,
    classify_snapshot_envelope,
    replay_snapshot_envelope,
)
from core.scanner_snapshot import MODE_COMPACT, MODE_FULL, build_snapshot_envelope
from core.scanner_threshold_policy import make_default_threshold_policy

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


class TestClassify:
    def test_full_envelope_is_replayable(self):
        env = build_snapshot_envelope(_run(), mode=MODE_FULL)
        assert classify_snapshot_envelope(env.to_dict()) == "replayable"

    def test_compact_envelope_is_audit_only(self):
        env = build_snapshot_envelope(_run(), mode=MODE_COMPACT)
        assert classify_snapshot_envelope(env.to_dict()) == "audit_only"

    def test_v3_payload_is_audit_only(self):
        assert classify_snapshot_envelope(V3_PAYLOAD) == "audit_only"

    def test_garbage_is_invalid(self):
        assert classify_snapshot_envelope({"random": "data"}) == "invalid"

    def test_non_mapping_is_invalid(self):
        assert classify_snapshot_envelope(["x"]) == "invalid"


class TestReplayDeterministic:
    def test_full_envelope_replays_to_same_candidate(self):
        env = build_snapshot_envelope(_run(), mode=MODE_FULL)
        thresholds = make_default_threshold_policy()
        outcome = replay_snapshot_envelope(env.to_dict(), thresholds=thresholds)
        assert outcome.replayable is True
        assert outcome.match is True
        assert outcome.comparisons == ()
        assert outcome.candidate_status == env.candidate_status
        assert outcome.selected_side == env.selected_side
        assert outcome.reason_codes is not None

    def test_replay_is_byte_deterministic(self):
        env = build_snapshot_envelope(_run(), mode=MODE_FULL)
        thresholds = make_default_threshold_policy()
        first = replay_snapshot_envelope(env.to_dict(), thresholds=thresholds)
        second = replay_snapshot_envelope(env.to_dict(), thresholds=thresholds)
        assert first.to_dict() == second.to_dict()

    def test_actor_change_is_detected_not_silenced(self):
        # The stored envelope was produced by the unconfirmed composition; an
        # actor replaying with confirmation routes a different status and the
        # mismatch is surfaced, never silently rewritten.
        env = build_snapshot_envelope(_run(), mode=MODE_FULL)
        outcome = replay_snapshot_envelope(
            env.to_dict(),
            thresholds=make_default_threshold_policy(),
            entry_confirmation="confirmed",
        )
        assert outcome.replayable is True
        assert outcome.match is False
        assert any("candidate_status" in text for text in outcome.comparisons)

    def test_selected_setup_score_compared(self):
        env = build_snapshot_envelope(_run(), mode=MODE_FULL)
        outcome = replay_snapshot_envelope(
            env.to_dict(), thresholds=make_default_threshold_policy()
        )
        if outcome.match and outcome.selected_side is not None:
            assert outcome.selected_setup_score is not None


class TestNonReplayable:
    def test_compact_envelope_is_refused(self):
        env = build_snapshot_envelope(_run(), mode=MODE_COMPACT)
        outcome = replay_snapshot_envelope(env.to_dict(), thresholds=make_default_threshold_policy())
        assert outcome.replayable is False
        assert outcome.match is None  # no replay comparison was possible
        assert outcome.route_status == "not_replayable"

    def test_v3_artifact_is_non_replayable(self):
        outcome = replay_snapshot_envelope(V3_PAYLOAD, thresholds=make_default_threshold_policy())
        assert outcome.replayable is False
        assert outcome.match is False
        assert SCANNER_LEGACY_V3_AUDIT_ONLY in outcome.reason_codes

    def test_missing_version_is_non_replayable(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_FULL).to_dict()
        del payload["envelope_schema_version"]
        outcome = replay_snapshot_envelope(payload, thresholds=make_default_threshold_policy())
        assert outcome.replayable is False
        assert outcome.match is False
        assert outcome.reason_codes == (SCANNER_VERSION_MISSING,) or (
            SCANNER_VERSION_MISSING in outcome.reason_codes
        )

    def test_mismatched_version_is_non_replayable(self):
        payload = build_snapshot_envelope(_run(), mode=MODE_FULL).to_dict()
        payload["envelope_schema_version"] = "scanner-v4-snapshot-envelope-v999"
        outcome = replay_snapshot_envelope(payload, thresholds=make_default_threshold_policy())
        assert outcome.replayable is False
        assert outcome.reason_codes and SCANNER_VERSION_MISMATCH in outcome.reason_codes

    def test_non_dict_payload_is_non_replayable(self):
        outcome = replay_snapshot_envelope(["nope"], thresholds=make_default_threshold_policy())
        assert outcome.replayable is False
        assert outcome.match is False

    def test_outcome_shape_is_stable(self):
        env = build_snapshot_envelope(_run(), mode=MODE_FULL)
        doc = replay_snapshot_envelope(env.to_dict(), thresholds=make_default_threshold_policy())
        payload = doc.to_dict()
        for key in (
            "replayable",
            "route_status",
            "match",
            "candidate_status",
            "selected_side",
            "selected_setup_score",
            "reason_codes",
            "comparisons",
        ):
            assert key in payload


class TestReplayVersionIdentity:
    def test_replay_version_constant_exists(self):
        assert SCANNER_REPLAY_VERSION == "scanner-replay"
        assert isinstance(SCANNER_REPLAY_VERSION, str) and SCANNER_REPLAY_VERSION