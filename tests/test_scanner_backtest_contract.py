"""Scanner backtest parity contract (Bước 09, target-only).

Mục 9A: backtest MUST call the same ``compose_scanner`` (and the same
canonical side scores / gates / candidate) as the live adapter — there is NO
backtest-specific scorer, gate, fallback, or decision.  These tests prove the
structural parity that Bước 07 built (one snapshot builder per source, one
composition API) is a *verifiable contract*: two compositions from the same
immutable input differ ONLY in ``capture_source``; any other leaf difference is
a ``SCANNER_V4_BACKTEST_PARITY_VIOLATION``.

For the candidate layer the tests prove router output of a backtest-sourced
composition equals the live output byte-for-byte.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.reason_codes import (
    SCANNER_BACKTEST_PARITY_VIOLATION,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISSING,
)
from core.scanner_backtest_contract import (
    SCANNER_BACKTEST_CONTRACT_VERSION,
    SCANNER_CANDIDATE_LEDGER_VERSION,
    SCANNER_CANDIDATE_REPLAY_VERSION,
    SCANNER_FROZEN_STRATEGY_VERSION,
    INCOMPATIBLE_ARTIFACT_KIND,
    V3_AUDIT_ONLY_ARTIFACT_KIND,
    REPLAYABLE_ARTIFACT_KIND,
    ArtifactClassification,
    ScannerArtifactError,
    classify_backtest_artifact,
    require_replayable,
    verify_candidate_parity,
    verify_composition_parity,
)
from core.scanner_composition import (
    COMPOSITION_POLICY_VERSION,
    ScannerCompositionResult,
)
from core.scanner_v4_strategy_router import (
    ROUTE_ROUTED,
    route_scanner,
)
from core.scanner_threshold_policy import make_default_threshold_policy
from tests.test_scanner_composition import (
    _compose,
    _run,
    _snapshot,
    _side_snapshot,
    BUY,
)


def _pair() -> tuple[ScannerCompositionResult, ScannerCompositionResult]:
    return _compose(_snapshot(source="live")), _compose(_snapshot(source="backtest"))


def _candidate_pair():
    live, backtest = _pair()
    thresholds = make_default_threshold_policy()
    out_live = route_scanner(live.to_dict(), thresholds=thresholds, entry_confirmation="confirmed")
    out_bt = route_scanner(backtest.to_dict(), thresholds=thresholds, entry_confirmation="confirmed")
    assert out_live.route_status == ROUTE_ROUTED
    assert out_bt.route_status == ROUTE_ROUTED
    return out_live.candidate, out_bt.candidate


class TestCompositionParity:
    def test_identical_input_parity_passes(self):
        report = verify_composition_parity(*_pair())
        assert report.passed is True
        assert report.contract_version == SCANNER_BACKTEST_CONTRACT_VERSION
        assert report.reason_codes == ()
        assert not report.diffs

    def test_only_capture_source_may_differ(self):
        report = verify_composition_parity(*_pair())
        # The composition_to_dict has capture_source both top-level and in
        # canonical.provenance — both must be whitelisted and must not surface
        # as diffs.
        assert not any("capture_source" in d.path for d in report.diffs)

    def test_same_input_yields_same_snapshot_id(self):
        live, backtest = _pair()
        assert live.snapshot_id == backtest.snapshot_id
        assert live.to_dict()["canonical"]["snapshot_id"] == backtest.to_dict()["canonical"]["snapshot_id"]

    def test_same_technical_and_setup_scores(self):
        live, backtest = _pair()
        for side in ("buy", "sell"):
            live_side = next(
                s for s in live.canonical.side_scores if s.side == side
            )
            bt_side = next(
                s for s in backtest.canonical.side_scores if s.side == side
            )
            assert (
                live_side.technical_signal_score
                == bt_side.technical_signal_score
            )
            assert live_side.setup_score == bt_side.setup_score

    def test_same_selected_side_and_gates(self):
        live, backtest = _pair()
        assert live.decision.selected_side == backtest.decision.selected_side
        assert live.safety.status == backtest.safety.status
        assert live.macro_gate.status == backtest.macro_gate.status
        assert [g.name for g in live.composition_gates] == [
            g.name for g in backtest.composition_gates
        ]

    def test_split_snapshot_single_api_is_the_only_path(self):
        # The structural contract: `compose_scanner` is one shared API and
        # the two snapshot builders differ ONLY by capture_source.  The
        # canonical input fingerprint excludes capture_source (proven by the
        # existing composition tests).  Assert the two results share object
        # identity for the snapshot schema (same class) and the composition
        # policy version.
        live, backtest = _pair()
        assert type(live.canonical) is type(backtest.canonical)
        assert live.to_dict()["composition_version"] == COMPOSITION_POLICY_VERSION
        assert backtest.to_dict()["composition_version"] == COMPOSITION_POLICY_VERSION

    def test_payload_type_parity_covers_canonical_block(self):
        live, backtest = _pair()
        assert "scanner_action" not in live.to_dict()
        assert "final_score" not in live.canonical.to_dict()
        assert "opportunity_score" not in live.to_dict()
        # An envelope has no legacy decision block; the router would refuse it.

    def test_a_real_score_difference_flags_violation(self):
        live = _compose(_snapshot(source="live"))
        corrupted = _compose(
            _snapshot(
                source="backtest",
                buy_side=_side_snapshot(BUY, trend=21, momentum=14, location=18),
            )
        )
        report = verify_composition_parity(live, corrupted)
        assert report.passed is False
        assert report.reason_codes == (SCANNER_BACKTEST_PARITY_VIOLATION,)
        assert any("technical" in d.path for d in report.diffs)

    def test_missing_backtest_leaf_flags_violation(self):
        # Backtest input missing a gate input the live path had (simulated by a
        # macro raw value difference) → the leaf differs → parity flags it.
        live = _compose(_snapshot(source="live"))
        corrupted = _compose(_snapshot(source="backtest", macro_raw_buy=30))
        report = verify_composition_parity(live, corrupted)
        assert report.passed is False
        assert report.reason_codes == (SCANNER_BACKTEST_PARITY_VIOLATION,)


class TestCandidateParity:
    def test_candidate_parity_passes_for_same_input(self):
        c_live, c_bt = _candidate_pair()
        report = verify_candidate_parity(c_live, c_bt)
        assert report.passed
        assert report.contract_version == SCANNER_BACKTEST_CONTRACT_VERSION

    def test_router_output_is_byte_identical_for_live_vs_backtest(self):
        c_live, c_bt = _candidate_pair()
        assert c_live.to_dict() == c_bt.to_dict()

    def test_candidate_status_identical(self):
        c_live, c_bt = _candidate_pair()
        assert c_live.candidate_status == c_bt.candidate_status

    def test_router_never_executes_on_backtest(self):
        # A routed candidate from a backtest composition still does not carry a
        # real order flag — the order payload is the same read-only envelope.
        c_live, c_bt = _candidate_pair()
        for c in (c_live, c_bt):
            assert c.order_payload is not None
            assert c.order_payload.sends_real_order is False

    def test_router_v3_canonical_refused_before_any_execution(self):
        payload = _run().to_dict()
        payload["canonical"] = {
            "symbol": "XAUUSD",
            "side": "buy",
            "direction": "buy",
            "exchange": "BINANCE",
            "snapshot_version": "scanner-pair-snapshot-v3",
            "composition_version": COMPOSITION_POLICY_VERSION,
            "captured_at": "2026-08-13T12:00:00+00:00",
            "capture_source": "backtest",
        }
        out = route_scanner(
            payload,
            thresholds=make_default_threshold_policy(),
            entry_confirmation="confirmed",
        )
        assert out.candidate is None
        assert out.executed is False
        assert any(
            "VERSION" in code or "LEGACY" in code for code in out.reason_codes
        )


class TestNoBacktestSpecificPath:
    def test_backtest_snapshot_has_no_scorer_semantics(self):
        # The backtest snapshot builder is a provenance wrapper; the actual
        # snapshot model carries no legacy score fields.
        bt = _snapshot(source="backtest").to_canonical_input_dict()
        live = _snapshot(source="live").to_canonical_input_dict()
        assert bt == live

    def test_composition_accepts_both_sources(self):
        _, backtest = _pair()
        assert backtest.capture_source == "backtest"
        assert backtest.to_dict()["capture_source"] == "backtest"


# ---------------------------------------------------------------------------
# 9C artifact classification (read-only legacy, replayable current)
# ---------------------------------------------------------------------------


class TestArtifactClassification:
    def test_full_composition_envelope_is_replayable(self):
        verdict = classify_backtest_artifact(_compose(_snapshot()).to_dict())
        assert verdict.kind == REPLAYABLE_ARTIFACT_KIND
        assert verdict.reason_codes == ()

    def test_single_version_field_is_not_replayable(self):
        # §12.1 / §7.3: a single version field is NOT a complete artifact.
        verdict = classify_backtest_artifact(
            {"candidate_ledger_version": SCANNER_CANDIDATE_LEDGER_VERSION}
        )
        assert verdict.kind == INCOMPATIBLE_ARTIFACT_KIND
        assert SCANNER_VERSION_MISSING in verdict.reason_codes

    def test_single_contract_field_is_not_replayable(self):
        verdict = classify_backtest_artifact(
            {"backtest_contract_version": SCANNER_BACKTEST_CONTRACT_VERSION}
        )
        assert verdict.kind == INCOMPATIBLE_ARTIFACT_KIND
        assert SCANNER_VERSION_MISSING in verdict.reason_codes

    def test_v3_contract_is_audit_only(self):
        verdict = classify_backtest_artifact(
            {"backtest_contract_version": "phase0-backtest-safety-v1"}
        )
        assert verdict.kind == V3_AUDIT_ONLY_ARTIFACT_KIND
        assert SCANNER_LEGACY_V3_AUDIT_ONLY in verdict.reason_codes

    def test_v3_ledger_is_audit_only(self):
        verdict = classify_backtest_artifact(
            {"candidate_ledger_version": "backtest-candidate-ledger-v1"}
        )
        assert verdict.kind == V3_AUDIT_ONLY_ARTIFACT_KIND

    def test_v3_replay_and_frozen_are_audit_only(self):
        for version in ("candidate-replay-v1", "frozen-strategy-config-v1"):
            verdict = classify_backtest_artifact(
                {"replay_version": version}
                if version == "candidate-replay-v1"
                else {"frozen_strategy_version": version}
            )
            assert verdict.kind == V3_AUDIT_ONLY_ARTIFACT_KIND, version

    def test_missing_version_incompatible(self):
        verdict = classify_backtest_artifact({})
        assert verdict.kind == INCOMPATIBLE_ARTIFACT_KIND
        assert SCANNER_VERSION_MISSING in verdict.reason_codes

    def test_non_dict_incompatible(self):
        verdict = classify_backtest_artifact(None)
        assert verdict.kind == INCOMPATIBLE_ARTIFACT_KIND
        assert SCANNER_SCHEMA_INVALID in verdict.reason_codes

    def test_require_replayable_returns_unchanged(self):
        value = _compose(_snapshot()).to_dict()
        assert require_replayable(value) == value

    def test_require_replayable_refuses_v3(self):
        with pytest.raises(ScannerArtifactError):
            require_replayable(
                {"candidate_ledger_version": "backtest-candidate-ledger-v1"}
            )

    def test_versions_are_distinct_from_v3(self):
        assert SCANNER_BACKTEST_CONTRACT_VERSION != "phase0-backtest-safety-v1"
        assert SCANNER_CANDIDATE_LEDGER_VERSION != "backtest-candidate-ledger-v1"
        assert SCANNER_CANDIDATE_REPLAY_VERSION != "candidate-replay-v1"
        assert SCANNER_FROZEN_STRATEGY_VERSION != "frozen-strategy-config-v1"

    def test_artifact_classification_to_dict_shape(self):
        verdict = classify_backtest_artifact({})
        payload = verdict.to_dict()
        assert set(payload) == {"kind", "version_field", "version", "reason_codes"}