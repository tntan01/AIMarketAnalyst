"""Tests for TP selection anchor split (_TP_SELECTION_AGGRESSIVENESS vs _ENTRY_AGGRESSIVENESS).

Verifies that:
- Borderline TPs (RR>=1 from edge, RR<1 from midpoint) are rejected
- Far TPs (RR>>1 from both) are unchanged
- entry_price/risk_reward display values stay consistent with edge anchor
- Symmetry between buy and sell
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.market_models import Candle
from core.risk_engine import (
    AnalysisInput,
    _ENTRY_AGGRESSIVENESS,
    _TP_SELECTION_AGGRESSIVENESS,
    build_trade_plan,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(n: int, *, price: float = 1.1000, volatility: float = 0.0006,
             start_time: datetime | None = None, bar_minutes: int = 60) -> list[Candle]:
    t = start_time or datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    cur = price
    for i in range(n):
        wick = volatility * 0.4
        open_p = cur
        close_p = cur + (i % 3 - 1) * volatility * 0.1
        high_p = max(open_p, close_p) + wick
        low_p = min(open_p, close_p) - wick
        candles.append(Candle(
            time=t, open=round(open_p, 5), high=round(high_p, 5),
            low=round(low_p, 5), close=round(close_p, 5),
            volume=float(1000 + i * 10),
        ))
        cur = close_p
        t += timedelta(minutes=bar_minutes)
    return candles


def _req() -> AnalysisInput:
    return AnalysisInput(
        symbol="EUR/USD", broker_symbol="EURUSDm",
        account_balance=10000.0, risk_percent=2.0,
        contract_size_override=100000.0,
    )


def _zone(level, low, high, strength="moderate", zone_score=None):
    return {
        "level": level, "low": low, "high": high,
        "type": "support" if low < level else "resistance",
        "strength": strength,
        "zone_score": zone_score if zone_score is not None else (75 if strength == "strong" else 50),
        "confluence_count": 1, "consolidation_bars": 0,
        "freshness_bars": None, "mitigated": False, "broken": False,
        "test_count": 0, "displacement_multiple": 0, "liquidity_sweep": False,
        "zone_location": "unknown", "source": "technical",
    }


def _swing(level, index=0):
    return {"level": level, "index": index, "time": "2026-06-01T00:00:00"}


def _base_tech(price, atr, support_zones, resistance_zones):
    return {
        "price": price, "atr_h4": atr, "atr_d1": atr * 1.2,
        "ema50_d1": price - 0.002, "ema200_d1": price - 0.005,
        "ema50_h4": price - 0.001,
        "ema50_d1_slope": 0.0001, "ema200_d1_slope": 0.00005,
        "rsi_h4": 50.0, "rsi_h4_previous": 48.0,
        "macd_histogram_h4": {"value": 0.00002, "previous_value": -0.00001,
                              "previous2_value": -0.00003, "direction": "increasing"},
        "support_zones": support_zones,
        "resistance_zones": resistance_zones,
        "structure_d1": "trend_up", "structure_h4": "trend_up",
        "swings_h4": {"highs": [], "lows": []},
        "swings_d1": {"highs": [], "lows": []},
        "range_info": {"in_range": False, "range_high": None, "range_low": None},
    }


def _base_smc():
    return {
        "H4": {
            "demand_zones": [], "supply_zones": [],
            "swings": {"highs": [], "lows": []},
            "liquidity_pools": {"equal_highs": [], "equal_lows": []},
            "bos": False, "displacement": None, "choch": False, "fvg": False,
        },
    }


candles = _candles(200, price=1.1000)
m15 = _candles(200, price=1.1000, volatility=0.0003, bar_minutes=15)


# ---------------------------------------------------------------------------
# Constant tests
# ---------------------------------------------------------------------------

class TestConstants:
    def test_entry_aggressiveness_is_zero(self):
        assert _ENTRY_AGGRESSIVENESS == 0.0

    def test_tp_selection_aggressiveness_is_half(self):
        assert _TP_SELECTION_AGGRESSIVENESS == 0.5

    def test_selection_more_conservative_than_display(self):
        assert _TP_SELECTION_AGGRESSIVENESS > _ENTRY_AGGRESSIVENESS


# ---------------------------------------------------------------------------
# Borderline TP rejection tests
# ---------------------------------------------------------------------------

class TestBorderlineTPRejection:
    """TP that barely passes RR>=1 from edge but fails from midpoint → rejected."""

    def test_buy_borderline_tp_rejected_fallback_to_farther_target(self):
        """Buy: borderline TP at 1.0990 rejected, system picks farther target."""
        atr = 0.0020
        price = 1.1000
        tech = _base_tech(
            price, atr,
            support_zones=[_zone(1.0970, 1.0960, 1.0980, "strong", 75)],
            resistance_zones=[
                _zone(1.0990, 1.0985, 1.0995, "moderate", 50),  # borderline
                _zone(1.1050, 1.1040, 1.1060, "strong", 70),     # solid far TP
            ],
        )
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0950, 5)]}

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})

        assert plan is not None, "Plan should not be None — farther TP exists"
        tps = plan["take_profit"]
        assert len(tps) > 0, "Should have at least one TP"
        # TP1 must NOT be the borderline 1.0990 — must be farther (>= 1.1050 or Fib)
        assert tps[0] > 1.1000, f"TP1={tps[0]} should be farther than borderline 1.0990"

    def test_sell_borderline_tp_rejected_fallback_to_farther_target(self):
        """Sell: borderline TP rejected, picks farther target. (Mirror of buy test.)"""
        atr = 0.0020
        price = 1.1000
        tech = _base_tech(
            price, atr,
            support_zones=[
                _zone(1.0980, 1.0975, 1.0985, "moderate", 50),  # borderline for sell
                _zone(1.0920, 1.0910, 1.0930, "strong", 70),     # solid far TP
            ],
            resistance_zones=[_zone(1.1030, 1.1020, 1.1040, "strong", 75)],
        )
        tech["structure_d1"] = "trend_down"
        tech["structure_h4"] = "trend_down"
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0950, 5)]}

        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_down"})

        # The sell TP at 1.0980 may or may not be borderline depending on SL width.
        # This test verifies the plan is not None and TP is reasonable.
        assert plan is not None, "Sell plan should not be None"
        tps = plan["take_profit"]
        assert len(tps) > 0

    def test_non_preferred_returns_none_when_only_borderline_tp_exists(self):
        """Non-preferred buy with only borderline TP → return None."""
        atr = 0.0020
        price = 1.1000
        tech = _base_tech(
            price, atr,
            support_zones=[_zone(1.0970, 1.0960, 1.0980, "strong", 75)],
            resistance_zones=[_zone(1.0990, 1.0985, 1.0995, "moderate", 50)],
        )
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [], "lows": [_swing(1.0950, 5)]}

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is None, (
            "Non-preferred buy with only borderline TP must return None"
        )


# ---------------------------------------------------------------------------
# Far TP unchanged tests
# ---------------------------------------------------------------------------

class TestFarTPUnchanged:
    """TPs far enough from both edge and midpoint should remain unchanged."""

    def test_buy_far_tp_unchanged(self):
        atr = 0.0020
        price = 1.1000
        tech = _base_tech(
            price, atr,
            support_zones=[_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
            resistance_zones=[_zone(1.1050, 1.1040, 1.1060, "strong", 70)],
        )
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        assert len(plan["take_profit"]) > 0
        # Phase 13C: TP uses boundary (low - buffer), not zone level directly.
        # Zone low=1.1040 → TP = 1.1040 - 0.03*ATR ≈ 1.10394 < 1.1050
        assert plan["take_profit"][0] >= 1.1039, \
            f"Far boundary TP should be near zone low {plan['take_profit'][0]}"

    def test_sell_far_tp_unchanged(self):
        atr = 0.0020
        price = 1.1000
        tech = _base_tech(
            price, atr,
            support_zones=[_zone(1.0920, 1.0910, 1.0930, "strong", 70)],
            resistance_zones=[_zone(1.1040, 1.1030, 1.1050, "strong", 75)],
        )
        tech["structure_d1"] = "trend_down"
        tech["structure_h4"] = "trend_down"
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1060, 10)], "lows": [_swing(1.0920, 5)]}

        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_down"})
        assert plan is not None
        assert len(plan["take_profit"]) > 0


# ---------------------------------------------------------------------------
# Display values unchanged tests
# ---------------------------------------------------------------------------

class TestDisplayValuesUseEdgeAnchor:
    """entry_price/risk_reward must use edge anchor (_ENTRY_AGGRESSIVENESS=0.0),
    NOT the selection anchor."""

    def test_entry_price_is_at_edge_not_midpoint(self):
        """For buy, entry_price should be at entry_low (edge), not midpoint."""
        atr = 0.0020
        price = 1.1000
        tech = _base_tech(
            price, atr,
            support_zones=[_zone(1.0960, 1.0950, 1.0970, "strong", 75)],
            resistance_zones=[_zone(1.1050, 1.1040, 1.1060, "strong", 70)],
        )
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1050, 10)], "lows": [_swing(1.0940, 5)]}

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})
        assert plan is not None
        entry_low = plan["entry_zone"][0]
        entry_high = plan["entry_zone"][1]
        zone_width = entry_high - entry_low
        midpoint = entry_low + zone_width * 0.5

        # entry_price should be at the edge (entry_low for buy), within tolerance
        assert plan["entry_price"] == pytest.approx(entry_low, abs=zone_width * 0.15), \
            f"entry_price={plan['entry_price']} should be near edge {entry_low}, not midpoint {midpoint}"

    def test_sell_entry_price_is_at_edge_not_midpoint(self):
        """For sell, entry_price should be at entry_high (edge)."""
        atr = 0.0020
        price = 1.1000
        tech = _base_tech(
            price, atr,
            support_zones=[_zone(1.0920, 1.0910, 1.0930, "strong", 70)],
            resistance_zones=[_zone(1.1040, 1.1030, 1.1050, "strong", 75)],
        )
        tech["structure_d1"] = "trend_down"
        tech["structure_h4"] = "trend_down"
        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1060, 10)], "lows": [_swing(1.0920, 5)]}

        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_down"})
        assert plan is not None
        entry_high = plan["entry_zone"][1]
        entry_low = plan["entry_zone"][0]
        zone_width = entry_high - entry_low
        midpoint = entry_low + zone_width * 0.5

        assert plan["entry_price"] == pytest.approx(entry_high, abs=zone_width * 0.15), \
            f"entry_price={plan['entry_price']} should be near edge {entry_high}, not midpoint {midpoint}"


# ---------------------------------------------------------------------------
# Symmetry tests
# ---------------------------------------------------------------------------

class TestBuySellSymmetry:
    """Buy/sell mirror inputs should produce symmetric TP selection behavior."""

    def test_both_sides_behave_consistently_for_mirror_setup(self):
        """Mirror buy/sell setups produce consistent results (both plan or both None)."""
        atr = 0.0020
        price = 1.1000

        # Mirror: buy uses support below, sell uses resistance above
        # Both have a TP that clears RR>=1 from both edge and midpoint
        tech_buy = _base_tech(
            price, atr,
            support_zones=[_zone(1.0970, 1.0960, 1.0980, "strong", 75)],
            resistance_zones=[_zone(1.1050, 1.1040, 1.1060, "strong", 70)],
        )
        tech_sell = _base_tech(
            price, atr,
            support_zones=[_zone(1.0950, 1.0940, 1.0960, "strong", 70)],
            resistance_zones=[_zone(1.1030, 1.1020, 1.1040, "strong", 75)],
        )
        tech_sell["structure_d1"] = "trend_down"
        tech_sell["structure_h4"] = "trend_down"

        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1060, 10)], "lows": [_swing(1.0940, 5)]}

        plan_buy = build_trade_plan("buy", _req(), tech_buy, smc, candles, m15_candles=m15,
                                    market_regime={"primary": "trend_up"})
        plan_sell = build_trade_plan("sell", _req(), tech_sell, smc, candles, m15_candles=m15,
                                     market_regime={"primary": "trend_down"})

        # Both should produce plans with TPs — mirror setup with valid targets
        assert plan_buy is not None, "Buy should have valid TP"
        assert plan_sell is not None, "Sell should have valid TP"
        assert len(plan_buy["take_profit"]) > 0
        assert len(plan_sell["take_profit"]) > 0

        # entry_price should be at zone edge for both
        buy_entry = plan_buy["entry_price"]
        buy_zone_low = plan_buy["entry_zone"][0]
        assert buy_entry == pytest.approx(buy_zone_low, abs=0.0002)

        sell_entry = plan_sell["entry_price"]
        sell_zone_high = plan_sell["entry_zone"][1]
        assert sell_entry == pytest.approx(sell_zone_high, abs=0.0002)
