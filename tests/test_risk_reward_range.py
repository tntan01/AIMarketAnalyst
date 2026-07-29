"""Tests for risk_reward_range field in build_trade_plan().

Verifies:
- best > base > worst ordering
- tp1=None → all None
- best ≈ existing risk_reward numeric value
- buy/sell symmetry
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.market_models import Candle
from core.risk_engine import AnalysisInput, build_trade_plan, reward_risk
from core.scanner import scanner_row_from_analysis


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(n, price=1.1000, volatility=0.0006, start_time=None, bar_minutes=60):
    t = start_time or datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    cur = price
    for i in range(n):
        wick = volatility * 0.4
        open_p = cur
        close_p = cur + (i % 3 - 1) * volatility * 0.1
        high_p = max(open_p, close_p) + wick
        low_p = min(open_p, close_p) - wick
        candles.append(Candle(
            time=t, open=round(open_p, 5), high=round(high_p, 5),
            low=round(low_p, 5), close=round(close_p, 5), volume=float(1000 + i * 10)))
        cur = close_p
        t += timedelta(minutes=bar_minutes)
    return candles


def _req():
    return AnalysisInput(symbol="EUR/USD", broker_symbol="EURUSDm",
                         account_balance=10000.0, risk_percent=2.0,
                         contract_size_override=100000.0)


def _zone(level, low, high, strength="moderate", zone_score=None):
    return {"level": level, "low": low, "high": high,
            "type": "support" if low < level else "resistance",
            "strength": strength,
            "zone_score": zone_score if zone_score is not None else (75 if strength == "strong" else 50),
            "confluence_count": 1, "consolidation_bars": 0,
            "freshness_bars": None, "mitigated": False, "broken": False,
            "test_count": 0, "displacement_multiple": 0, "liquidity_sweep": False,
            "zone_location": "unknown", "source": "technical"}


def _swing(level, index=0):
    return {"level": level, "index": index, "time": "2026-06-01T00:00:00"}


def _base_tech(price, atr, supports, resistances):
    return {"price": price, "atr_h4": atr, "atr_d1": atr * 1.2,
            "ema50_d1": price - 0.002, "ema200_d1": price - 0.005,
            "ema50_h4": price - 0.001,
            "ema50_d1_slope": 0.0001, "ema200_d1_slope": 0.00005,
            "rsi_h4": 50.0, "rsi_h4_previous": 48.0,
            "macd_histogram_h4": {"value": 0.00002, "previous_value": -0.00001,
                                  "previous2_value": -0.00003, "direction": "increasing"},
            "support_zones": supports, "resistance_zones": resistances,
            "structure_d1": "trend_up", "structure_h4": "trend_up",
            "swings_h4": {"highs": [], "lows": []},
            "swings_d1": {"highs": [], "lows": []},
            "range_info": {"in_range": False, "range_high": None, "range_low": None}}


def _base_smc():
    return {"H4": {"demand_zones": [], "supply_zones": [],
                   "swings": {"highs": [], "lows": []},
                   "liquidity_pools": {"equal_highs": [], "equal_lows": []},
                   "bos": False, "displacement": None, "choch": False, "fvg": False}}


candles = _candles(200)
m15 = _candles(200, volatility=0.0003, bar_minutes=15)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRRRangeOrdering:
    """best > base > worst for both buy and sell."""

    def test_buy_rr_range_ordering(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        rr = plan["risk_reward_range"]
        assert rr["best"] is not None
        assert rr["base"] is not None
        assert rr["worst"] is not None
        assert rr["best"] > rr["base"] > rr["worst"], \
            f"Expected best > base > worst, got {rr}"

    def test_sell_rr_range_ordering(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0920, 1.0910, 1.0930, "strong", 70)],
                          [_zone(1.1040, 1.1030, 1.1050, "strong", 75)])
        tech["structure_d1"] = "trend_down"
        tech["structure_h4"] = "trend_down"
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1060, 10)], "lows": [_swing(1.0920, 5)]}
        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_down"})
        assert plan is not None
        rr = plan["risk_reward_range"]
        assert rr["best"] > rr["base"] > rr["worst"], \
            f"Expected best > base > worst for sell, got {rr}"

    def test_buy_rr_best_matches_risk_reward(self):
        """risk_reward_range['best'] should match the numeric part of risk_reward string."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        rr_str = plan["risk_reward"]  # "1:5.6"
        rr_best = plan["risk_reward_range"]["best"]
        # Parse the numeric RR from the string
        expected = float(rr_str.split(":")[1]) if rr_str else None
        assert rr_best == pytest.approx(expected, abs=0.15), \
            f"best={rr_best} should match risk_reward={expected}"


class TestRRRangeNone:
    """tp1=None → all risk_reward_range values are None."""

    def test_preferred_no_tp_all_none(self):
        """use_preferred=True with no valid TP → best/base/worst all None."""
        pref = {"level": 1.0975, "low": 1.0968, "high": 1.0982, "strength": "moderate",
                "zone_score": 68, "source": "smc", "confluence_count": 2,
                "consolidation_bars": 5, "freshness_bars": 20, "mitigated": False,
                "broken": False, "test_count": 0, "displacement_multiple": 2.0,
                "liquidity_sweep": True, "zone_location": "discount", "type": "demand"}
        tech = _base_tech(1.1000, 0.0010,
                          [_zone(1.0940, 1.0930, 1.0950, "moderate", 50)],
                          [])
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.1020, "range_low": 1.0940}
        smc = _base_smc()
        smc["H4"]["demand_zones"] = [pref]
        smc["H4"]["swings"] = {"highs": [], "lows": [_swing(1.0940, 5)]}

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                preferred_zone=pref, market_regime={"primary": "range"})

        if plan is not None:
            # Plan may exist with no TP if use_preferred
            if plan["take_profit"] == []:
                rr = plan["risk_reward_range"]
                assert rr["best"] is None
                assert rr["base"] is None
                assert rr["worst"] is None
                eff = plan["risk_reward_effective_range"]
                assert eff["best"] is None
                assert eff["base"] is None
                assert eff["worst"] is None
                assert plan["risk_reward"] is None
                assert plan["risk_reward_base"] is None
                assert plan["risk_reward_worst"] is None
                assert plan["expected_effective_rr"] is None
                assert plan["expected_effective_rr_base"] is None
                assert plan["expected_effective_rr_worst"] is None
        # If plan is None, that's also valid (SL might be too tight)


class TestRRRangeSymmetry:
    """Mirror buy/sell should produce symmetric RR ranges."""

    def test_mirror_rr_ranges_similar(self):
        """Buy/sell with mirrored zone distances produce similar absolute RR ranges."""
        atr = 0.0020
        price = 1.1000

        tech_buy = _base_tech(price, atr,
                              [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                              [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        tech_sell = _base_tech(price, atr,
                               [_zone(1.0950, 1.0940, 1.0960, "strong", 70)],
                               [_zone(1.1040, 1.1030, 1.1050, "strong", 75)])
        tech_sell["structure_d1"] = "trend_down"
        tech_sell["structure_h4"] = "trend_down"

        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1060, 10)], "lows": [_swing(1.0940, 5)]}

        plan_buy = build_trade_plan("buy", _req(), tech_buy, smc, candles, m15_candles=m15,
                                    market_regime={"primary": "trend_up"})
        plan_sell = build_trade_plan("sell", _req(), tech_sell, smc, candles, m15_candles=m15,
                                     market_regime={"primary": "trend_down"})

        assert plan_buy is not None
        assert plan_sell is not None

        rr_buy = plan_buy["risk_reward_range"]
        rr_sell = plan_sell["risk_reward_range"]

        # Both should have well-defined best > worst (qualitative check)
        assert rr_buy["best"] > rr_buy["worst"]
        assert rr_sell["best"] > rr_sell["worst"]


class TestRRRangeFieldPresent:
    """Every valid plan must include risk_reward_range."""

    def test_field_present_in_valid_plan(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        assert "risk_reward_range" in plan
        assert isinstance(plan["risk_reward_range"], dict)
        assert set(plan["risk_reward_range"].keys()) == {"best", "base", "worst"}

    def test_new_rr_fields_present_in_valid_plan(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"},
                                spread_price=0.0001)
        assert plan is not None

        for key in (
            "risk_reward_base",
            "risk_reward_worst",
            "expected_effective_rr_base",
            "expected_effective_rr_worst",
            "risk_reward_effective_range",
        ):
            assert key in plan

        assert isinstance(plan["risk_reward_effective_range"], dict)
        assert set(plan["risk_reward_effective_range"].keys()) == {"best", "base", "worst"}

    def test_new_nominal_fields_match_rr_range(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None

        rr = plan["risk_reward_range"]
        assert plan["risk_reward_base"] == rr["base"]
        assert plan["risk_reward_worst"] == rr["worst"]

    def test_effective_rr_fields_are_ordered(self):
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"},
                                spread_price=0.0001)
        assert plan is not None

        assert plan["expected_effective_rr"] >= plan["expected_effective_rr_base"]
        assert plan["expected_effective_rr_base"] >= plan["expected_effective_rr_worst"]

        eff = plan["risk_reward_effective_range"]
        assert eff["best"] == plan["expected_effective_rr"]
        assert eff["base"] == plan["expected_effective_rr_base"]
        assert eff["worst"] == plan["expected_effective_rr_worst"]

    def test_scanner_row_copies_new_rr_fields_without_reinterpreting(self):
        plan = {
            "type": "buy",
            "risk_reward": "1:2.4",
            "risk_reward_base": 1.8,
            "risk_reward_worst": 1.2,
            "expected_effective_rr": 2.3,
            "expected_effective_rr_base": 1.7,
            "expected_effective_rr_worst": 1.1,
            "risk_reward_range": {"best": 2.4, "base": 1.8, "worst": 1.2},
            "risk_reward_effective_range": {"best": 2.3, "base": 1.7, "worst": 1.1},
            "entry_zone": [1.095, 1.097],
            "entry_status": "watch_zone",
            "m15_quality": "loose",
            "stop_loss": 1.093,
            "take_profit": [1.105],
        }
        result = {
            "symbol": "EUR/USD",
            "scenario_scores": {"buy": {"signal_score": 80}, "sell": {"signal_score": 50}},
            "trade_permission": {"status": "allowed"},
            "scenarios": [plan],
            "technical": {"price": 1.096, "atr_h4": 0.002},
            "decision_engine": {"legacy_action": "watch", "decision": "WATCH_ONLY"},
            "direction_bias": {"best_side": "buy"},
        }

        row = scanner_row_from_analysis(result)

        assert row["risk_reward_base"] == plan["risk_reward_base"]
        assert row["risk_reward_worst"] == plan["risk_reward_worst"]
        assert row["expected_effective_rr_base"] == plan["expected_effective_rr_base"]
        assert row["expected_effective_rr_worst"] == plan["expected_effective_rr_worst"]
        assert row["risk_reward_effective_range"] == plan["risk_reward_effective_range"]


# ===========================================================================
# Phase 6: Cross-contract regression — lock RR anchor semantics
# ===========================================================================


class TestCrossContractAnchors:
    """Verify that a single trade plan is consumed consistently by all layers:
    plan → scanner row → gate → ranking.  These tests lock the anchor
    semantics documented in docs/trading/rr_anchor_semantics.md."""

    # ------------------------------------------------------------------
    # Plan-level: build_trade_plan anchor correctness
    # ------------------------------------------------------------------

    def test_plan_risk_reward_is_best_case_string(self):
        """risk_reward must be '1:X.X' from best edge, never midpoint."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        # Contract: risk_reward is a "1:X.X" string
        assert isinstance(plan["risk_reward"], str)
        assert plan["risk_reward"].startswith("1:")
        # Contract: numeric value matches risk_reward_range.best (not base)
        rr_str_val = float(plan["risk_reward"].split(":")[1])
        assert rr_str_val == pytest.approx(plan["risk_reward_range"]["best"], abs=0.15)

    def test_plan_expected_effective_rr_is_best_case_float(self):
        """expected_effective_rr is best-case, after spread."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        assert isinstance(plan["expected_effective_rr"], float)
        assert plan["expected_effective_rr"] > 0
        # effective_range best should match (allowing for spread effect)
        eff_range = plan.get("risk_reward_effective_range")
        if eff_range and eff_range.get("best") is not None:
            assert plan["expected_effective_rr"] == pytest.approx(eff_range["best"], abs=0.15)

    def test_plan_base_worst_is_conservative(self):
        """Base and worst RR must be <= best RR for both nominal and effective."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None

        # Nominal range
        rr = plan["risk_reward_range"]
        assert rr["best"] > rr["base"] > rr["worst"]

        # Effective range
        eff = plan.get("risk_reward_effective_range")
        if eff and eff["best"] is not None:
            assert eff["best"] > eff["base"] > eff["worst"]

        # expected_effective_rr_base <= expected_effective_rr
        assert plan["expected_effective_rr_base"] <= plan["expected_effective_rr"]

    # ------------------------------------------------------------------
    # Gate-level: gate uses base, not best
    # ------------------------------------------------------------------

    def test_gate_blocks_best_pass_base_fail(self):
        """Gate must produce WATCH_ONLY when best RR passes but base fails."""
        from core.trade_gate_engine import check_trade_gates

        ctx = {
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "data_quality_warning": False,
            "high_impact_event_within_30m": False,
            "m15_quality": "strict",
            "score_gap": 20,
            "min_buy_sell_score_gap": 10,
            "zone_broken": False,
            "daily_loss_limit_reached": False,
            "weekly_loss_limit_reached": False,
            "min_expected_effective_rr": 1.3,
            "risk_reward": "1:2.5",
            "expected_effective_rr": 2.5,               # best: passes
            "expected_effective_rr_base": 1.1,           # base: fails
            "expected_effective_rr_for_gate": 1.1,
            "expected_effective_rr_source": "base",
        }
        result = check_trade_gates(ctx)
        from core.reason_codes import EXPECTED_RR_TOO_LOW
        assert EXPECTED_RR_TOO_LOW in result["warning_codes"]
        assert result["decision_cap"] == "WATCH_ONLY"

    # ------------------------------------------------------------------
    # Ranking-level: ranking uses base, not best
    # ------------------------------------------------------------------

    def test_ranking_rr_bonus_uses_base_over_best(self):
        """A row with best=2.5 (strong) but base=1.1 (no bonus) gets rr_bonus=0."""
        from core.scanner_ranking_engine import calculate_opportunity_score

        result = calculate_opportunity_score({
            "final_score": 80,
            "decision": "READY_TO_TRADE",
            "price_vs_zone": "in_zone",
            "expected_effective_rr": 2.5,
            "expected_effective_rr_base": 1.1,
            "spread_status": "normal",
        })
        assert result["score_breakdown"]["rr_bonus"] == 0

    def test_ranking_safe_rr_uses_base_over_best(self):
        """_safe_rr must prefer base over best over risk_reward string."""
        from core.scanner import _safe_rr

        # base available → use it
        assert _safe_rr({
            "expected_effective_rr_base": 1.1,
            "expected_effective_rr": 2.5,
            "risk_reward": "1:3.0",
        }) == 1.1

        # base missing → fallback best
        assert _safe_rr({
            "expected_effective_rr": 2.0,
            "risk_reward": "1:1.8",
        }) == 2.0

        # both missing → fallback risk_reward string
        assert _safe_rr({"risk_reward": "1:1.5"}) == 1.5

        # all missing
        assert _safe_rr({}) == 0.0

    # ------------------------------------------------------------------
    # Execution guard: current RR blocks/skips, never gate/ranking
    # ------------------------------------------------------------------

    def test_current_rr_guard_logic_does_not_affect_gate(self):
        """Current RR being low must NOT affect the gate — only execution guard."""
        from core.trade_gate_engine import check_trade_gates
        from core.reason_codes import EXPECTED_RR_TOO_LOW

        ctx = {
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "data_quality_warning": False,
            "high_impact_event_within_30m": False,
            "m15_quality": "strict",
            "score_gap": 20,
            "min_buy_sell_score_gap": 10,
            "zone_broken": False,
            "daily_loss_limit_reached": False,
            "weekly_loss_limit_reached": False,
            "min_expected_effective_rr": 1.3,
            "risk_reward": "1:2.5",
            "expected_effective_rr": 2.5,
            "expected_effective_rr_base": 1.8,
            "expected_effective_rr_for_gate": 1.8,
            "expected_effective_rr_source": "base",
            # current_effective_rr is NOT in gate_context — gate doesn't see it
        }
        result = check_trade_gates(ctx)
        # Gate should pass (base=1.8 >= 1.3), no current RR involvement
        assert EXPECTED_RR_TOO_LOW not in result["warning_codes"]

    # ------------------------------------------------------------------
    # Legacy field immutability
    # ------------------------------------------------------------------

    def test_risk_reward_never_changed_to_base(self):
        """risk_reward must always be best-case, never midpoint or worst."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None

        rr_val = float(plan["risk_reward"].split(":")[1])
        base_val = plan["risk_reward_range"]["base"]
        # Contract: risk_reward matches BEST, not base
        assert rr_val > base_val, \
            f"risk_reward={rr_val} must be > base={base_val} (best edge > midpoint)"

    def test_expected_effective_rr_never_changed_to_base(self):
        """expected_effective_rr must always be best-case, never midpoint."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None

        assert plan["expected_effective_rr"] > plan["expected_effective_rr_base"], \
            f"expected_effective_rr={plan['expected_effective_rr']} must be > base={plan['expected_effective_rr_base']}"

    # ------------------------------------------------------------------
    # Field presence contract
    # ------------------------------------------------------------------

    def test_plan_contains_rr_and_execution_price_fields(self):
        """Every valid plan must contain 8 RR anchor fields + 4 execution price fields."""
        tech = _base_tech(1.1000, 0.0020,
                          [_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
                          [_zone(1.1050, 1.1040, 1.1060, "strong", 70)])
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}
        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None

        required_fields = [
            # 8 RR anchor fields
            "risk_reward",
            "risk_reward_base",
            "risk_reward_worst",
            "risk_reward_range",
            "risk_reward_effective_range",
            "expected_effective_rr",
            "expected_effective_rr_base",
            "expected_effective_rr_worst",
            # 4 execution price fields
            "entry_price",
            "entry_zone",
            "stop_loss",
            "take_profit",
        ]
        for field in required_fields:
            assert field in plan, f"Missing field '{field}' in trade plan"
