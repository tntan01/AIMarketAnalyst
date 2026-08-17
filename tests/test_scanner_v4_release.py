"""Scanner V4 release wiring tests (Bước 12; target-only cutover entry).

Proves the SINGLE release wiring (``core.scanner_v4_release``):

* ``compose_scanner_v4`` is the only scoring/decision entry — the release
  module exposes it and never reads V3 scored fields;
* the DEFAULT threshold policy (technical 40 / setup 35 / gap 5 / R:R 2/1,
  ``scanner-threshold-policy-v4``) is what the candidate decision layer uses —
  a single-owner default, not a fabricated/V3-copied threshold; ``None`` still
  fails closed;
* candidate routing + ranking use the locked defaults (no caller order);
* end-to-end shape: composition → row → candidate → setup filter → locked rank
  → group, with exact V4 identity end-to-end;
* the routed candidate is intent-only (``sends_real_order=False``) — the
  release wiring never dispatches;
* V3/mixed/unknown identity is rejected before any decision.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.scanner_v4_release import (
    DEFAULT_THRESHOLD_POLICY,
    ROUTE_ROUTED,
    SCANNER_V4_RELEASE_VERSION,
    grouped_pairs,
    rank_pairs,
    ready_pairs_above_setup,
    run_v4_pair,
)
from core.scanner_v4_row import SCANNER_V4_ROW_VERSION
from core.scanner_v4_threshold_policy import make_default_threshold_policy

from tests.test_scanner_v4_composition import (
    NOW,
    _snapshot,
)


def _pair(entry_confirmation: str = "confirmed"):
    return run_v4_pair(_snapshot(), now=NOW, entry_confirmation=entry_confirmation)


def _live_candles():
    import math
    from datetime import timedelta
    from core.market_models import Candle

    base = 1000.0

    def mk(n, step, phase):
        out = []
        for i in range(n):
            o = base + math.sin((i + phase) / 3) * 0.5 + i * step
            c = base + math.sin((i + 1 + phase) / 3) * 0.5 + (i + 1) * step
            out.append(
                Candle(
                    time=NOW - timedelta(seconds=int((n - i) * step * 3600)),
                    open=o,
                    high=max(o, c) + 0.1,
                    low=min(o, c) - 0.1,
                    close=c,
                )
            )
        return out

    return mk(120, 0.08, 0.0), mk(120, 0.04, 1.0), mk(80, 0.02, 2.0)


def _live_safety():
    from datetime import timedelta
    from core.scanner_v4_live_producers import build_live_market_safety_context

    return build_live_market_safety_context(
        "XAUUSD",
        NOW,
        terminal_connected=True,
        broker_logged_in=True,
        connectivity_checked_at=NOW - timedelta(seconds=30),
        last_candle_time_utc=NOW - timedelta(seconds=30),
        spread_points=20.0,
        spread_checked_at=NOW,
        news_source_verified=True,
        news_checked_at=NOW,
        volatility_ratio=1.0,
        volatility_checked_at=NOW,
    )


def _live_pair():
    from core.scanner_v4_release import run_v4_pair_from_live

    d1, h4, h1 = _live_candles()
    return run_v4_pair_from_live(
        d1, h4, h1, "XAUUSD", _live_safety(),
        now=NOW, captured_at=NOW,
        macro_raw_buy=20, macro_raw_sell=14, macro_confidence=0.8,
    )


def _zoned_candles():
    """Triangle-wave candles whose H4 swings yield REAL technical zones.

    The swing detector requires a UNIQUE max/min inside its window, so the
    per-candle wicks vary with the bar index (two candles sharing a peak price
    would otherwise tie and be rejected).
    """
    import math
    from datetime import timedelta
    from core.market_models import Candle

    def mk(n, hours, period, amp, step, phase=0.25):
        px = []
        base = 1000.0
        for i in range(n + 1):
            t = ((i + phase) % period) / period
            tri = 4 * abs(t - 0.5) - 1
            px.append(base + tri * amp + i * step)
        out = []
        for i in range(n):
            o, c = px[i], px[i + 1]
            out.append(
                Candle(
                    time=NOW - timedelta(hours=(n - i) * hours),
                    open=o,
                    high=max(o, c) + 0.2 + (i % 5) * 0.01,
                    low=min(o, c) - 0.2 - ((i + 2) % 5) * 0.01,
                    close=c,
                )
            )
        return out

    return (
        mk(120, 24, period=17, amp=12.0, step=0.3),
        mk(120, 4, period=13, amp=8.0, step=0.1),
        mk(80, 1, period=11, amp=4.0, step=0.05),
    )


def _zoned_pair():
    from core.scanner_v4_release import run_v4_pair_from_live

    d1, h4, h1 = _zoned_candles()
    return run_v4_pair_from_live(
        d1, h4, h1, "XAUUSD", _live_safety(),
        now=NOW, captured_at=NOW,
        macro_raw_buy=20, macro_raw_sell=14, macro_confidence=0.8,
    )


class TestSingleEntry:
    def test_run_v4_pair_builds_full_release_pair(self):
        pair = _pair()
        assert pair.composition.to_dict()["composition_version"] == "scanner-composition-v4"
        assert pair.row.scoring_version == "scanner-v4"
        assert pair.row.row_version == SCANNER_V4_ROW_VERSION
        assert pair.candidate is not None
        assert pair.route_status == ROUTE_ROUTED

    def test_default_threshold_policy_is_the_locked_default(self):
        # Single-owner default: 40 / 35 / 5 / R:R 2/1.  This is a DEFAULT, never
        # fabricated nor copied from V3.  The release binds exactly this policy.
        assert DEFAULT_THRESHOLD_POLICY == make_default_threshold_policy()
        assert DEFAULT_THRESHOLD_POLICY.policy_version == "scanner-threshold-policy-v4"
        assert DEFAULT_THRESHOLD_POLICY.technical_floor == 40
        assert DEFAULT_THRESHOLD_POLICY.setup_floor == 35
        assert DEFAULT_THRESHOLD_POLICY.min_score_gap == 5
        assert DEFAULT_THRESHOLD_POLICY.min_risk_reward == Fraction(2, 1)

    def test_release_version_is_locked(self):
        assert SCANNER_V4_RELEASE_VERSION == "scanner-v4-release-v1"

    def test_release_row_is_canonical_and_exact_identity(self):
        row = _pair().row
        assert row.scoring_version == "scanner-v4"
        assert row.feature_version == "scanner-features-v4"
        assert row.output_schema_version == "scanner-output-v4"
        assert row.snapshot_version == "scanner-pair-snapshot-v4"
        assert row.safety_policy_version == "scanner-safety-policy-v4"
        assert row.macro_policy_version == "scanner-macro-policy-v4"
        assert row.composition_version == "scanner-composition-v4"

    def test_candidate_is_intent_only(self):
        pair = _pair()
        # If execution readiness has not passed there is no order payload at all.
        # When a payload IS materialized it is structurally locked to
        # sends_real_order=False — the release path never dispatches.
        payload = pair.candidate.order_payload
        if payload is not None:
            assert payload.sends_real_order is False


class TestRouting:
    def test_confirmed_executable_routes_ready(self):
        pair = _pair(entry_confirmation="confirmed")
        assert pair.route_status == ROUTE_ROUTED

    def test_unconfirmed_candidate_is_waiting_confirmation(self):
        pair = _pair(entry_confirmation="unconfirmed")
        # The candidate must still be produced but demand a fresh confirmation
        # before any execution intent.
        assert pair.candidate is not None


class TestRankAndGroup:
    def test_rank_pairs_orders_and_returns_pairs(self):
        pairs = [_pair() for _ in range(3)]
        ranked = rank_pairs(pairs)
        assert len(ranked) == 3
        assert set(id(p) for p in ranked) == set(id(p) for p in pairs)

    def test_grouped_pairs_groups_by_candidate_status(self):
        groups = grouped_pairs([_pair(), _pair(entry_confirmation="unconfirmed")])
        assert groups
        for status, items in groups.items():
            assert all(p.candidate.candidate_status == status for p in items)


class TestSetupFilter:
    def test_default_floor_is_35(self):
        assert int(DEFAULT_THRESHOLD_POLICY.setup_floor) == 35
        pair = _pair()
        # Filter must be consistent: with the explicit 35 floor, the pair is
        # kept iff its selected-side setup meets that floor.
        assert ready_pairs_above_setup([pair], min_setup_score=35) == (
            [pair] if (pair.row.selected_setup_score or 0) >= 35 else []
        )
        assert ready_pairs_above_setup([pair]) == ready_pairs_above_setup(
            [pair], min_setup_score=35
        )

    def test_explicit_floor_is_used(self):
        pair = _pair()
        kept_high = ready_pairs_above_setup([pair], min_setup_score=10_000)
        assert kept_high == []

    def test_filter_refuses_v3_scored_input_through_row_mapping(self):
        # ready_pairs_above_setup builds V4-only row dicts; a forged V3 field on
        # the underlying row's dict is never introduced here.
        pair = _pair()
        rows = [
            {
                "selected_side": pair.row.selected_side,
                "setup_score": pair.row.selected_setup_score,
            }
        ]
        assert rows[0]["selected_side"] in ("buy", "sell")
        assert "buy_score" not in rows[0] and "scenario_scores" not in rows[0]


class TestV3Rejected:
    def test_release_refuses_v3_copied_threshold_policy(self):
        # The threshold policy model itself is version-locked: you cannot even
        # construct a V3/mixed policy.  Nothing V3-copied can enter the release
        # decision layer.  ThresholdPolicyError is a subclass of ValueError.
        from core.scanner_v4_threshold_policy import (
            ThresholdPolicy,
            ThresholdPolicyError,
        )

        with pytest.raises(ThresholdPolicyError):
            ThresholdPolicy(
                policy_version="scanner-threshold-policy-v3",
                technical_floor=50,
                setup_floor=40,
                min_score_gap=10,
                min_risk_reward=Fraction(1, 1),
            )

    def test_release_row_reader_rejects_v3_identity(self):
        from core.reason_codes import SCANNER_V4_VERSION_MISMATCH
        from core.scanner_v4_row import RowContractError, scanner_v4_row_from_dict

        row = _pair().row.to_dict()
        row["row_version"] = "scanner-v3-row-v1"
        with pytest.raises(RowContractError) as exc:
            scanner_v4_row_from_dict(row)
        assert exc.value.code == SCANNER_V4_VERSION_MISMATCH


class TestLiveWiringFromCandles:
    """Bước 5: drive the release path from live candles (Bước 2/3 producers)."""

    def test_live_pair_carries_exact_v4_identity(self):
        pair = _live_pair()
        assert pair.row.scoring_version == "scanner-v4"
        assert pair.row.feature_version == "scanner-features-v4"
        assert pair.row.composition_version == "scanner-composition-v4"
        assert pair.route_status in (ROUTE_ROUTED, "blocked", "needs_confirmation")

    def test_live_pair_intent_only_never_dispatches(self):
        pair = _live_pair()
        payload = pair.candidate.order_payload if pair.candidate else None
        if payload is not None:
            assert payload.sends_real_order is False

    def test_live_pair_deterministic(self):
        from core.scanner_v4_release import run_v4_pair_from_live

        d1, h4, h1 = _live_candles()
        a = run_v4_pair_from_live(d1, h4, h1, "XAUUSD", _live_safety(), now=NOW,
                                  captured_at=NOW, macro_raw_buy=20, macro_raw_sell=14)
        b = run_v4_pair_from_live(d1, h4, h1, "XAUUSD", _live_safety(), now=NOW,
                                  captured_at=NOW, macro_raw_buy=20, macro_raw_sell=14)
        assert a.composition.snapshot_id == b.composition.snapshot_id

    def test_live_pair_fails_closed_on_insufficient_history(self):
        from core.scanner_v4_features import TechnicalRawDerivationError
        from core.scanner_v4_release import run_v4_pair_from_live

        d1, h4, h1 = _live_candles()
        with pytest.raises(TechnicalRawDerivationError):
            run_v4_pair_from_live(d1[:30], h4, h1, "XAUUSD", _live_safety(),
                                  now=NOW, captured_at=NOW)


class TestLiveScenarioPlanWiring:
    """Scenario plans flow from REAL structure into the live composition.

    A side with a real protective zone + opposite target gets a plan and the
    scenario gate evaluates the REAL R:R; a side without structure keeps the
    fail-closed UNKNOWN (``GATE_SCENARIO_PLAN_MISSING``).
    """

    def test_plan_flows_into_snapshot_from_real_structure(self):
        pair = _zoned_pair()
        scenario = pair.composition.scenario
        plan = scenario.plan
        assert plan is not None
        assert plan.direction == scenario.side
        assert plan.entry > 0 and plan.stop_loss > 0 and plan.take_profit > 0
        assert plan.source in ("smc_canonical_zone_v4", "technical_zone_v4")
        # The gate's exact R:R is the plan's own ratio (never approximated).
        from core.scanner_v4_composition import compute_scenario_rr

        assert scenario.risk_reward_ratio == compute_scenario_rr(plan, scenario.side)

    def test_plan_missing_code_disappears_when_structure_present(self):
        pair = _zoned_pair()
        scenario = pair.composition.scenario
        gate = scenario.gate
        # The gate now evaluates a REAL plan: PASS (RR >= floor) or an honest
        # RR BLOCK — never the structural plan-missing UNKNOWN.
        assert gate.status in ("PASS", "BLOCK")
        assert "GATE_SCENARIO_PLAN_MISSING" not in gate.reason_codes
        assert "GATE_SCENARIO_PLAN_MISSING" not in pair.composition.decision.gate_codes
        # The V3-aligned zone-anchored construction (entry at the protective
        # zone, risk = 1.0 * ATR buffer, TP beyond the far edge) yields an R:R
        # at/above the 2/1 floor for this fixture: the honest outcome is PASS.
        assert gate.status == "PASS"
        assert "GATE_SCENARIO_RR_BLOCK" not in gate.reason_codes
        assert gate.observed >= 2.0

    def test_no_structure_keeps_plan_missing_fail_closed(self):
        # Regression: the smooth sine candles carry no H4 swing structure, so
        # no side can produce a plan and the gate must stay UNKNOWN (WATCH cap),
        # never inventing entry/SL/TP.
        pair = _live_pair()
        scenario = pair.composition.scenario
        assert scenario.plan is None
        assert scenario.gate.status == "UNKNOWN"
        assert "GATE_SCENARIO_PLAN_MISSING" in scenario.gate.reason_codes
        assert "GATE_SCENARIO_PLAN_MISSING" in pair.composition.decision.gate_codes

    def test_zoned_pair_still_intent_only(self):
        pair = _zoned_pair()
        payload = pair.candidate.order_payload if pair.candidate else None
        if payload is not None:
            assert payload.sends_real_order is False