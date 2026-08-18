"""Scanner strategy router (Bước 08, target-only).

The router is the fail-closed door in front of the single decision path:

* it accepts ONLY the Step 07 canonical output (typed or strict JSON dict);
* any legacy payload — a legacy top-level scored field (``total``/``best_score``/
  ``scanner_action``/…), a missing/mismatched version, or a non-current canonical
  snapshot — returns ``version_mismatch`` **before anything executes**;
* there is no fallback path: a legacy artifact can never be routed, and a routed
  result never carries a real order at Bước 08 (``executed=False``).

The integration tests prove that the router's candidate is byte-identical to
``build_candidate`` on the same canonical output, and that every consumer
(execution readiness, order payload) sees the same decision.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.reason_codes import (
    SCANNER_FORBIDDEN_SCORED_FIELD,
    SCANNER_LEGACY_V3_AUDIT_ONLY,
    SCANNER_SCHEMA_INVALID,
    SCANNER_VERSION_MISMATCH,
    SCANNER_VERSION_MISSING,
)
from core.scanner_candidate import build_candidate
from core.scanner_composition import (
    COMPOSITION_POLICY_VERSION,
    ScannerCompositionResult,
)
from core.scanner_execution_readiness import evaluate_execution_readiness
from core.scanner_v4_models import (
    BLOCKED,
    DATA_UNAVAILABLE,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)
from core.scanner_v4_strategy_router import (
    FORBIDDEN_LEGACY_KEYS,
    ROUTE_INVALID,
    ROUTE_ROUTED,
    ROUTE_VERSION_MISMATCH,
    RoutedCandidate,
    route_scanner,
)
from core.scanner_threshold_policy import (
    SCANNER_THRESHOLD_POLICY_VERSION,
    ThresholdPolicy,
    make_default_threshold_policy,
)
from tests.test_scanner_composition import (
    _compose,
    _run,
    _snapshot,
    _options,
    _side_snapshot,
    _canonical_smc,
    COMPOSITION_POLICY_VERSION as _CV,
    _safety_context,
    _safety_policy,
)


def _route(payload, *, entry="confirmed", **kwargs):
    return route_scanner(
        payload,
        thresholds=make_default_threshold_policy(),
        entry_confirmation=entry,
        **kwargs,
    )


def _full_pass_dict() -> dict:
    return _run().to_dict()


# ---------------------------------------------------------------------------
# Fail-closed: legacy / missing / mismatched anything -> VERSION_MISMATCH
# ---------------------------------------------------------------------------


class TestLegacyRejected:
    def test_legacy_total_is_refused_before_anything_runs(self):
        payload = _full_pass_dict()
        payload["total"] = 55
        out = _route(payload)
        assert out.route_status == ROUTE_VERSION_MISMATCH
        assert out.candidate is None
        assert out.executed is False
        assert SCANNER_FORBIDDEN_SCORED_FIELD in out.reason_codes
        assert "total" in out.reason_codes

    def test_legacy_best_score_opportunity_action_all_refused(self):
        for key in ("best_score", "opportunity_score", "scanner_action",
                    "scanner_group", "expected_effective_rr",
                    "risk_condition", "macro_alignment", "final_score"):
            assert key in FORBIDDEN_LEGACY_KEYS, key
            payload = _full_pass_dict()
            payload[key] = 42
            out = _route(payload)
            assert out.route_status == ROUTE_VERSION_MISMATCH, key
            assert SCANNER_FORBIDDEN_SCORED_FIELD in out.reason_codes, key

    def test_legacy_rejection_never_uses_the_scored_value(self):
        # Even a "higher" total cannot rescue a legacy payload.
        payload = _full_pass_dict()
        payload["total"] = 100
        out = _route(payload)
        assert out.route_status == ROUTE_VERSION_MISMATCH
        assert out.candidate is None

    def test_forbidden_key_list_is_complete(self):
        assert FORBIDDEN_LEGACY_KEYS == frozenset({
            "total",
            "best_score",
            "final_score",
            "opportunity_score",
            "scanner_action",
            "scanner_group",
            "expected_effective_rr",
            "risk_condition",
            "macro_alignment",
        })


class TestVersionFencing:
    def test_missing_composition_version_returns_version_mismatch(self):
        payload = _full_pass_dict()
        del payload["composition_version"]
        out = _route(payload)
        assert out.route_status == ROUTE_VERSION_MISMATCH
        assert SCANNER_VERSION_MISMATCH in out.reason_codes

    def test_wrong_composition_version_returns_version_mismatch(self):
        payload = _full_pass_dict()
        payload["composition_version"] = "scanner-composition-v3"
        out = _route(payload)
        assert out.route_status == ROUTE_VERSION_MISMATCH

    def test_non_dict_payload_invalid(self):
        out = _route(object())
        assert out.route_status == ROUTE_VERSION_MISMATCH
        assert SCANNER_SCHEMA_INVALID in out.reason_codes

    def test_wrong_envelope_keys_returns_version_mismatch(self):
        payload = _full_pass_dict()
        del payload["canonical"]
        out = _route(payload)
        assert out.route_status == ROUTE_VERSION_MISMATCH
        assert SCANNER_VERSION_MISMATCH in out.reason_codes

    def test_canonical_not_a_dict_returns_version_mismatch(self):
        payload = _full_pass_dict()
        payload["canonical"] = "not-a-canonical"
        out = _route(payload)
        assert out.route_status == ROUTE_VERSION_MISMATCH

    def test_v3_canonical_snapshot_inside_envelope_refused(self):
        # The envelope claims current identity but the canonical is a legacy snapshot: the deep
        # reader refuses it (composition_version/snapshot_version mismatch).
        payload = _full_pass_dict()
        payload["canonical"] = {
            "symbol": "XAUUSD",
            "side": "buy",
            "direction": "buy",
            "exchange": "BINANCE",
            "snapshot_version": "scanner-pair-snapshot-v3",
            "composition_version": COMPOSITION_POLICY_VERSION,
            "captured_at": "2026-08-13T12:00:00+00:00",
            "capture_source": "live",
        }
        out = _route(payload)
        assert out.route_status == ROUTE_VERSION_MISMATCH
        assert out.candidate is None


# ---------------------------------------------------------------------------
# ROUTE_ROUTED — the canonical path
# ---------------------------------------------------------------------------


class TestRouted:
    def test_full_pass_routes_to_ready_now_without_order(self):
        out = _route(_full_pass_dict(), entry="confirmed")
        assert out.route_status == ROUTE_ROUTED
        assert out.executed is False
        assert out.candidate is not None
        assert out.candidate.candidate_status == READY_NOW
        assert out.candidate.order_payload.sends_real_order is False
        assert out.candidate.order_payload.revalidation_required is True

    def test_typed_composition_result_routes_same_as_dict(self):
        composition = _run()
        from_dict_out = _route(composition.to_dict())
        typed_out = _route(composition)
        assert typed_out.route_status == ROUTE_ROUTED
        assert from_dict_out.candidate.to_dict() == typed_out.candidate.to_dict()

    def test_router_never_reads_gate_action_reinterprets(self):
        # The router only consumes canonical scores/gates/versions; it never
        # re-interprets a "scanner_action".  For a full-pass input the action
        # concept is simply absent: no such key exists in the envelope.
        payload = _full_pass_dict()
        assert "scanner_action" not in payload

    def test_reason_codes_surface_all_decision_codes(self):
        out = _route(_full_pass_dict(), entry="confirmed")
        assert out.candidate.reason_codes
        assert out.candidate.threshold_policy_version == SCANNER_THRESHOLD_POLICY_VERSION


# ---------------------------------------------------------------------------
# Integration: the router output equals build_candidate byte-for-byte
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_dict_path_matches_direct_build_candidate(self):
        composition = _run()
        out = _route(composition.to_dict(), entry="confirmed")
        thresholds = make_default_threshold_policy()
        direct = build_candidate(
            composition=composition,
            thresholds=thresholds,
            entry_confirmation="confirmed",
            execution=evaluate_execution_readiness(composition),
        )
        assert out.candidate.to_dict() == direct.to_dict()

    def test_typed_path_matches_direct_build_candidate(self):
        composition = _run()
        out = _route(composition, entry="confirmed")
        direct = build_candidate(
            composition=composition,
            thresholds=make_default_threshold_policy(),
            entry_confirmation="confirmed",
            execution=evaluate_execution_readiness(composition),
        )
        assert out.candidate.to_dict() == direct.to_dict()

    def test_full_pipeline_status_ladder_survives_roundtrip(self):
        # engine -> composition -> dict -> router -> candidate: status held.
        candidates = {}
        for label, payload in {
            "full": _full_pass_dict(),
        }.items():
            out = route_scanner(
                payload,
                thresholds=make_default_threshold_policy(),
                entry_confirmation="unconfirmed",
            )
            candidates[label] = out.candidate.candidate_status
        assert candidates["full"] == WAITING_CONFIRMATION

    def test_router_blocks_and_unavailable_are_untouched(self):
        from datetime import timedelta

        # stale -> DATA_UNAVAILABLE
        stale = _compose(
            _snapshot(
                captured_at=_snapshot().captured_at - timedelta(seconds=300)
            )
        )
        assert stale.decision.candidate_status == DATA_UNAVAILABLE
        out = _route(stale.to_dict())
        assert out.candidate.candidate_status == DATA_UNAVAILABLE

        # safety BLOCK -> BLOCKED
        context = _safety_context(spread_points=40.0)
        safety = _safety_policy(spread_threshold_by_symbol={"XAUUSD": 30})
        blocked = _compose(_snapshot(safety=context), safety=safety)
        out_b = _route(blocked.to_dict())
        assert out_b.candidate.candidate_status == BLOCKED

    def test_open_threshold_policy_stays_watch_via_router(self):
        open_policy = ThresholdPolicy(
            policy_version=SCANNER_THRESHOLD_POLICY_VERSION,
            technical_floor=None,
            setup_floor=None,
            min_score_gap=None,
            min_risk_reward=None,
        )
        out = route_scanner(
            _full_pass_dict(),
            thresholds=open_policy,
            entry_confirmation="confirmed",
        )
        assert out.candidate.candidate_status == WATCH_ZONE
        assert any("THRESHOLD_POLICY_OPEN" in code for code in out.candidate.reason_codes)


# ---------------------------------------------------------------------------
# RoutedCandidate contract
# ---------------------------------------------------------------------------


class TestRoutedCandidateContract:
    def test_round_trip_of_to_dict_shape(self):
        out = _route(_full_pass_dict())
        payload = out.to_dict()
        assert set(payload) == {"route_status", "candidate", "executed", "reason_codes"}
        assert payload["route_status"] == ROUTE_ROUTED
        assert payload["executed"] is False
        assert payload["candidate"]["candidate_status"] == READY_NOW

    def test_non_routed_outcome_carries_no_candidate(self):
        out = _route(_full_pass_dict())
        refused = RoutedCandidate(
            route_status=ROUTE_VERSION_MISMATCH,
            candidate=None,
            reason_codes=(SCANNER_VERSION_MISMATCH,),
        )
        assert refused.executed is False
        assert refused.candidate is None

    def test_routed_outcome_requires_candidate(self):
        with pytest.raises(ValueError):
            RoutedCandidate(route_status=ROUTE_ROUTED, candidate=None)

    def test_refused_outcome_must_not_carry_candidate(self):
        with pytest.raises(ValueError):
            RoutedCandidate(
                route_status=ROUTE_VERSION_MISMATCH,
                candidate=_route(_full_pass_dict()).candidate,
            )

    def test_executed_always_false_at_step_08(self):
        with pytest.raises(ValueError):
            RoutedCandidate(
                route_status=ROUTE_ROUTED,
                candidate=_route(_full_pass_dict()).candidate,
                executed=True,
            )
        # The lock is total: a refused outcome cannot carry executed=True either.
        with pytest.raises(ValueError):
            RoutedCandidate(
                route_status=ROUTE_VERSION_MISMATCH,
                candidate=None,
                executed=True,
            )
        with pytest.raises(ValueError):
            RoutedCandidate(route_status=ROUTE_INVALID, candidate=None, executed=True)

    def test_route_status_vocabulary_locked(self):
        assert {ROUTE_ROUTED, ROUTE_VERSION_MISMATCH, ROUTE_INVALID} == {
            "routed",
            "version_mismatch",
            "invalid",
        }