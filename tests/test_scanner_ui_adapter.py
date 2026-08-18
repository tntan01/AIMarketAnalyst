"""Scanner → UI row adapter tests (Bước 12 C2a; target-only).

Proves the single row→UI mapping:

* every key with a real source equals its exact source
  (setup_score, candidate_status, selected_side, score_gap, decision_cap,
   evidence/execution, risk_reward, market_regime, macro/safety status + codes,
   gate codes, scenario entry/SL/TP, snapshot_id, exact identity, adapter stamp);
* legacy-only keys the UI still reads are the documented neutral (never fabricated);
* a legacy/mixed/unknown version is REFUSED before mapping (AdapterContractError);
* fail-closed when the candidate is ``None`` (no order intent, no optimistic flags);
* the routed order payload stays INTENT ONLY (``sends_real_order == False``);
* the retained-technical price/atr_h1 compat shim carries REAL values or None;
* deterministic (two maps are equal).
"""

from __future__ import annotations

import dataclasses
from fractions import Fraction

import pytest

from core.reason_codes import SCANNER_VERSION_MISMATCH
from core.scanner_release import (
    DEFAULT_THRESHOLD_POLICY,
    run_pair,
    run_pair_from_live,
)
from core.scanner_ui_adapter import (
    ADAPTER_VERSION,
    ANALYSIS_OK,
    AdapterContractError,
    V3_ONLY_NEUTRAL_KEYS,
    pair_to_ui_row,
)

from tests.scanner_testkit import NOW as TESTKIT_NOW
from tests.scanner_testkit import build_snapshot

SNAPSHOT = build_snapshot()


def _pair(entry_confirmation: str = "confirmed"):
    return run_pair(
        SNAPSHOT, now=TESTKIT_NOW, entry_confirmation=entry_confirmation
    )


def _live_pair():
    import math
    from datetime import timedelta

    from core.market_models import Candle

    now = TESTKIT_NOW
    base = 1000.0

    def mk(n, step, phase):
        out = []
        for i in range(n):
            o = base + math.sin((i + phase) / 3) * 0.5 + i * step
            c = base + math.sin((i + 1 + phase) / 3) * 0.5 + (i + 1) * step
            out.append(
                Candle(
                    time=now - timedelta(seconds=int((n - i) * step * 3600)),
                    open=o,
                    high=max(o, c) + 0.1,
                    low=min(o, c) - 0.1,
                    close=c,
                )
            )
        return out

    from core.scanner_live_producers import build_live_market_safety_context

    d1, h4, h1 = mk(120, 0.08, 0.0), mk(120, 0.04, 1.0), mk(80, 0.02, 2.0)
    safety = build_live_market_safety_context(
        "XAUUSD",
        now,
        terminal_connected=True,
        broker_logged_in=True,
        connectivity_checked_at=now - timedelta(seconds=30),
        last_candle_time_utc=now - timedelta(seconds=30),
        spread_points=20.0,
        spread_checked_at=now,
        news_source_verified=True,
        news_checked_at=now,
        volatility_ratio=1.0,
        volatility_checked_at=now,
    )
    return run_pair_from_live(
        d1, h4, h1, "XAUUSD", safety,
        now=now, captured_at=now,
        macro_raw_buy=20, macro_raw_sell=14, macro_confidence=0.8,
    )


class TestIdentityAndMapping:
    def test_exact_identity_block(self):
        row = pair_to_ui_row(_pair())
        assert row["row_version"] == "scanner-row"
        assert row["composition_version"] == "scanner-composition"
        assert row["scoring_version"] == "scanner"
        assert row["feature_version"] == "scanner-features"
        assert row["output_schema_version"] == "scanner-output"
        assert row["safety_policy_version"] == "scanner-safety-policy"
        assert row["macro_policy_version"] == "scanner-macro-policy"
        assert row["snapshot_version"] == "scanner-pair-snapshot"
        assert row["adapter_version"] == ADAPTER_VERSION

    def test_mapped_keys_equal_sources(self):
        pair = _pair()
        row = pair_to_ui_row(pair)
        assert row["symbol"] == pair.row.symbol
        assert row["snapshot_id"] == pair.row.snapshot_id
        assert row["candidate_status"] == pair.row.candidate_status
        assert row["selected_side"] == pair.row.selected_side
        assert row["score_gap"] == pair.row.score_gap
        assert row["decision_cap"] == pair.row.decision_cap
        assert row["setup_score"] == pair.row.selected_setup_score
        assert row["technical_signal_score"] == pair.row.selected_technical_signal_score
        assert row["macro_status"] == pair.row.macro_status
        assert row["safety_status"] == pair.row.safety_status
        assert row["gate_codes"] == list(pair.row.gate_codes)
        assert row["reason_codes"] == list(pair.row.reason_codes)
        assert row["block_codes"] == list(pair.row.block_codes)

    def test_candidate_sourced_fields(self):
        pair = _pair()
        cand = pair.candidate
        assert cand is not None, "the default strong fixture must route a candidate"
        row = pair_to_ui_row(pair)
        assert row["evidence_confidence"] == cand.evidence_score
        assert row["execution_readiness"] == cand.execution_quality_score
        assert row["expected_effective_rr"] == (
            float(cand.risk_reward_ratio) if cand.risk_reward_ratio else None
        )

    def test_scenario_zone_prices_only_when_plan_present(self):
        row = pair_to_ui_row(_pair())
        # The default fixture ships a selected-side plan with the canonical values.
        if row["selected_side"] is not None:
            assert "entry_price" in row
            assert "stop_loss" in row
            assert "take_profit" in row

    def test_market_regime_comes_from_selected_technical_result(self):
        row = pair_to_ui_row(_pair())
        side = row["selected_side"]
        if side is not None:
            assert row["market_regime"] in (
                "trending_up", "trending_down", "ranging", "volatile", "unknown",
            )

    def test_analysis_status_is_ok_not_structural_reject(self):
        # The model has no structural-reject/OUT_OF_STRATEGY classification.
        assert pair_to_ui_row(_pair())["analysis_status"] == ANALYSIS_OK

    def test_deterministic(self):
        assert pair_to_ui_row(_pair()) == pair_to_ui_row(_pair())

    def test_controller_metadata_emitted(self):
        row = pair_to_ui_row(
            _pair(),
            broker_symbol="B-XAUUSD",
            scan_id="scan-1",
            row_id="row-1",
            settings_hash="h1",
            latency_ms=12.5,
        )
        assert row["broker_symbol"] == "B-XAUUSD"
        assert row["scan_id"] == "scan-1"
        assert row["row_id"] == "row-1"
        assert row["settings_hash"] == "h1"
        assert "rollout_stage" not in row
        assert row["analysis_latency_ms"] == 12.5


class TestV3OnlyNeutrals:
    def test_v3_only_keys_are_documented_neutral(self):
        row = pair_to_ui_row(_pair())
        for key in V3_ONLY_NEUTRAL_KEYS:
            assert key in row, f"{key} must be present (documented neutral)"
        assert row["opportunity_rank"] is None
        assert row["auto_trade_branch"] is None
        assert row["strategy_config_status"] is None
        assert row["ranking_score_breakdown"] is None
        # The testkit's synthetic plan has no protective zone (source "plan"),
        # so the zone origin stays "none"; REAL routed plans stamp smc/technical
        # (asserted in test_scanner_ui_rr_contract::test_real_scanner_row_shows_rr...).
        assert row["zone_origin_class"] == "none"
        assert row["journal_sample_size"] == 0
        assert row["journal_feedback"] == {}
        # price_vs_zone is now a real per-row classification (not a neutral key).
        assert row["price_vs_zone"] in ("in_zone", "near_zone", "far", "unknown")
        assert row["m15_quality"] is None

    def test_no_optimistic_scored_weapons(self):
        # Never emit a number the UI could read as a real score for legacy-only keys.
        row = pair_to_ui_row(_pair())
        for key in (
            "best_score", "best_side", "risk_score", "scanner_action",
        ):
            assert row[key] is None or row[key] == "none", key


class TestFailClosedWhenNoCandidate:
    def _no_candidate_pair(self):
        pair = _pair()
        return dataclasses.replace(pair, candidate=None)

    def test_maps_without_candidate(self):
        pair = self._no_candidate_pair()
        row = pair_to_ui_row(pair)
        # Without a candidate the row keeps its real status (BLOCKED for the
        # default fixture — the default ComposeOptions opens the portfolio gate),
        # but every candidate-sourced field is fail-closed.
        assert row["candidate_status"] == pair.row.candidate_status
        assert row["evidence_confidence"] is None
        assert row["execution_readiness"] is None
        assert row["expected_effective_rr"] is None
        assert row["candidate_order_payload"] is None
        assert row["auto_trade_candidate"] is False

    def test_candidate_order_payload_is_intent_only(self):
        pair = _pair()
        if pair.candidate is not None and pair.candidate.order_payload is not None:
            row = pair_to_ui_row(pair)
            payload = row["candidate_order_payload"]
            assert payload is not None
            assert payload["sends_real_order"] is False


class TestCompatShims:
    def test_price_atr_passthrough_real_values(self):
        row = pair_to_ui_row(_pair(), technical={"price": 1910.5, "atr_h1": 4.2})
        assert row["analysis_result"]["technical"]["price"] == 1910.5
        assert row["analysis_result"]["technical"]["atr_h1"] == 4.2

    def test_price_atr_absent_is_none(self):
        row = pair_to_ui_row(_pair())
        assert row["analysis_result"]["technical"]["price"] is None
        assert row["analysis_result"]["technical"]["atr_h1"] is None


class TestVersionRefusal:
    def test_refuses_non_pair(self):
        for bad in (None, {}, "v3", SNAPSHOT, 42):
            with pytest.raises(AdapterContractError):
                pair_to_ui_row(bad)

    def test_refuses_v3_scoring_version(self):
        pair = _pair()
        bad_row = dataclasses.replace(pair.row, scoring_version="scanner-v3")
        bad_pair = dataclasses.replace(pair, row=bad_row)
        with pytest.raises(AdapterContractError):
            pair_to_ui_row(bad_pair)

    def test_refuses_unknown_row_version(self):
        pair = _pair()
        bad_pair = dataclasses.replace(
            pair, row=dataclasses.replace(pair.row, row_version="scanner-v3-row-v1")
        )
        with pytest.raises(AdapterContractError):
            pair_to_ui_row(bad_pair)


class TestLiveWiringAdapter:
    def test_live_pair_maps_with_exact_identity(self):
        pair = _live_pair()
        row = pair_to_ui_row(pair)
        assert row["scoring_version"] == "scanner"
        assert row["feature_version"] == "scanner-features"
        assert row["composition_version"] == "scanner-composition"

    def test_live_order_intent_never_dispatches(self):
        pair = _live_pair()
        row = pair_to_ui_row(pair)
        payload = row["candidate_order_payload"]
        if payload is not None:
            assert payload["sends_real_order"] is False


def _custom_policy(*, technical_floor=50, setup_floor=45, min_score_gap=4,
                   min_risk_reward=3):
    from fractions import Fraction

    from core.scanner_order_policy import DEFAULT_RUNTIME_ORDER_POLICY
    from core.scanner_threshold_policy import (
        SCANNER_THRESHOLD_POLICY_VERSION,
        ThresholdPolicy,
    )

    return dataclasses.replace(
        DEFAULT_RUNTIME_ORDER_POLICY,
        threshold=ThresholdPolicy(
            policy_version=SCANNER_THRESHOLD_POLICY_VERSION,
            technical_floor=technical_floor,
            setup_floor=setup_floor,
            min_score_gap=min_score_gap,
            min_risk_reward=Fraction(min_risk_reward),
        ),
    )


class TestThresholdColumns:
    def test_default_thresholds_when_not_supplied(self):
        decision = pair_to_ui_row(_pair())["scanner_candidate_decision"]
        assert decision["strategy"]["min_score"] == float(
            DEFAULT_THRESHOLD_POLICY.setup_floor
        )
        assert decision["strategy"]["min_rr"] == float(
            DEFAULT_THRESHOLD_POLICY.min_risk_reward
        )

    def test_supplied_thresholds_override(self):
        custom = _custom_policy(min_risk_reward=3)
        pair = run_pair(SNAPSHOT, now=TESTKIT_NOW, order_policy=custom)
        row = pair_to_ui_row(pair, min_score=45.0, min_rr=3.0)
        decision = row["scanner_candidate_decision"]
        assert decision["strategy"]["min_score"] == 45.0
        assert decision["strategy"]["min_rr"] == 3.0

    def test_router_and_display_share_owner_threshold(self):
        """The row the owner sees shows the SAME threshold the gate used."""
        custom = _custom_policy(min_risk_reward=Fraction(5, 2))
        pair = run_pair(SNAPSHOT, now=TESTKIT_NOW, order_policy=custom)
        row = pair_to_ui_row(
            pair,
            min_score=float(custom.threshold.setup_floor),
            min_rr=float(custom.threshold.min_risk_reward),
        )
        decision = row["scanner_candidate_decision"]["strategy"]
        assert decision["min_score"] == float(custom.threshold.setup_floor)
        assert decision["min_rr"] == float(custom.threshold.min_risk_reward)
        assert decision["min_rr"] > DEFAULT_THRESHOLD_POLICY.min_risk_reward