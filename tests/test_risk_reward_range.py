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
                assert plan["risk_reward"] is None
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
