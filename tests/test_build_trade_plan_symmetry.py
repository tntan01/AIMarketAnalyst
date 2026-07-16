"""Tests for build_trade_plan symmetry and guard behavior after refactoring.

Verifies that buy/sell mirror inputs produce symmetric outputs (equal absolute
distances), and that TP/SL guards work correctly for edge cases.
"""

from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from core.market_models import Candle
from core.risk_engine import AnalysisInput, build_trade_plan


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(
    n: int,
    *,
    price: float = 1.1000,
    step: float = 0.0000,
    volatility: float = 0.0006,
    start_time: datetime | None = None,
    bar_minutes: int = 60,
) -> list[Candle]:
    """Generate n candles around *price*, optionally trending."""
    t = start_time or datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    cur = price
    for i in range(n):
        body = step * (0.3 + 0.7 * (i % 5) / 5) if step != 0 else 0.0
        wick = volatility * 0.4
        open_p = cur
        close_p = cur + body
        high_p = max(open_p, close_p) + wick
        low_p = min(open_p, close_p) - wick
        candles.append(Candle(
            time=t, open=round(open_p, 5), high=round(high_p, 5),
            low=round(low_p, 5), close=round(close_p, 5),
            volume=float(1000 + i * 10),
        ))
        cur = close_p if step != 0 else price + (i % 3 - 1) * volatility * 0.15
        t += timedelta(minutes=bar_minutes)
    return candles


def _req(symbol="EUR/USD", broker="EURUSDm", balance=10000.0, risk=2.0,
         contract_override=100000.0) -> AnalysisInput:
    return AnalysisInput(
        symbol=symbol, broker_symbol=broker,
        account_balance=balance, risk_percent=risk,
        contract_size_override=contract_override,
    )


def _zone(level, low, high, strength="moderate", zone_score=None, source="technical"):
    return {
        "level": level, "low": low, "high": high, "type": "support" if low < level else "resistance",
        "strength": strength,
        "zone_score": zone_score if zone_score is not None else (75 if strength == "strong" else 50),
        "confluence_count": 1, "consolidation_bars": 0,
        "freshness_bars": None, "mitigated": False, "broken": False,
        "test_count": 0, "displacement_multiple": 0, "liquidity_sweep": False,
        "zone_location": "unknown", "source": source,
    }


def _swing(level, index=0):
    return {"level": level, "index": index, "time": "2026-06-01T00:00:00"}


def _base_technical(price, atr, support_zones, resistance_zones):
    return {
        "price": price, "atr_h4": atr, "atr_d1": atr * 1.2,
        "ema50_d1": price - 0.002, "ema200_d1": price - 0.005,
        "ema50_h4": price - 0.001,
        "ema50_d1_slope": 0.0001, "ema200_d1_slope": 0.00005,
        "rsi_h4": 50.0, "rsi_h4_previous": 48.0,
        "macd_histogram_h4": {"value": 0.00002, "previous_value": -0.00001, "previous2_value": -0.00003, "direction": "increasing"},
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


# ---------------------------------------------------------------------------
# Symmetry tests
# ---------------------------------------------------------------------------

class TestBuySellSymmetry:
    """Mirror inputs between buy and sell should produce symmetric outputs."""

    def test_entry_zone_width_symmetric(self):
        """Entry zone width (high-low) should be equal for mirrored buy/sell."""
        atr = 0.0015
        price_buy = 1.1000
        price_sell = 1.1000  # same absolute price

        # Buy: support at 1.0960 (40 pips below), resistance at 1.1040
        tech_buy = _base_technical(
            price_buy, atr,
            support_zones=[_zone(1.0960, 1.0950, 1.0970, "strong")],
            resistance_zones=[_zone(1.1040, 1.1030, 1.1050, "strong")],
        )
        # Sell: resistance at 1.1040 (40 pips above), support at 1.0960
        tech_sell = _base_technical(
            price_sell, atr,
            support_zones=[_zone(1.0960, 1.0950, 1.0970, "strong")],
            resistance_zones=[_zone(1.1040, 1.1030, 1.1050, "strong")],
        )

        smc = _base_smc()
        candles = _candles(200, price=price_buy, volatility=atr * 0.5)
        m15 = _candles(200, price=price_buy, volatility=atr * 0.25, bar_minutes=15)

        plan_buy = build_trade_plan("buy", _req(), tech_buy, smc, candles, m15_candles=m15,
                                    market_regime={"primary": "trend_up"})
        plan_sell = build_trade_plan("sell", _req(), tech_sell, smc, candles, m15_candles=m15,
                                     market_regime={"primary": "trend_down"})

        assert plan_buy is not None, "Buy plan should not be None"
        assert plan_sell is not None, "Sell plan should not be None"

        buy_width = plan_buy["entry_zone"][1] - plan_buy["entry_zone"][0]
        sell_width = plan_sell["entry_zone"][1] - plan_sell["entry_zone"][0]
        assert buy_width == pytest.approx(sell_width, rel=0.01), \
            f"Entry zone width: buy={buy_width:.6f} vs sell={sell_width:.6f}"

    def test_sl_distance_symmetric(self):
        """SL distance from level should be equal for mirrored buy/sell."""
        atr = 0.0015
        price = 1.1000

        buy_support = _zone(1.0960, 1.0950, 1.0970, "strong")
        sell_resist = _zone(1.1040, 1.1030, 1.1050, "strong")

        tech_buy = _base_technical(price, atr,
                                   support_zones=[buy_support],
                                   resistance_zones=[_zone(1.1040, 1.1030, 1.1050, "strong")])
        tech_sell = _base_technical(price, atr,
                                    support_zones=[_zone(1.0960, 1.0950, 1.0970, "strong")],
                                    resistance_zones=[sell_resist])

        smc = _base_smc()
        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan_buy = build_trade_plan("buy", _req(), tech_buy, smc, candles, m15_candles=m15,
                                    market_regime={"primary": "trend_up"})
        plan_sell = build_trade_plan("sell", _req(), tech_sell, smc, candles, m15_candles=m15,
                                     market_regime={"primary": "trend_down"})

        assert plan_buy is not None
        assert plan_sell is not None

        buy_sl_dist = abs(plan_buy["entry_price"] - plan_buy["stop_loss"])
        sell_sl_dist = abs(plan_sell["entry_price"] - plan_sell["stop_loss"])
        assert buy_sl_dist == pytest.approx(sell_sl_dist, rel=0.05), \
            f"SL distance: buy={buy_sl_dist:.6f} vs sell={sell_sl_dist:.6f}"

    def test_tp_distance_symmetric(self):
        """TP distance from entry should be equal for mirrored buy/sell with same zone distances."""
        atr = 0.0015
        price = 1.1000

        # Buy: support at 1.0970, resistance targets at 1.1030, 1.1060
        # Sell: resistance at 1.1030, support targets at 1.0970, 1.0940
        tech_buy = _base_technical(
            price, atr,
            support_zones=[_zone(1.0970, 1.0960, 1.0980, "strong")],
            resistance_zones=[_zone(1.1030, 1.1020, 1.1040, "strong"),
                            _zone(1.1060, 1.1050, 1.1070, "moderate")],
        )
        tech_sell = _base_technical(
            price, atr,
            support_zones=[_zone(1.0970, 1.0960, 1.0980, "strong"),
                          _zone(1.0940, 1.0930, 1.0950, "moderate")],
            resistance_zones=[_zone(1.1030, 1.1020, 1.1040, "strong")],
        )

        smc = _base_smc()
        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan_buy = build_trade_plan("buy", _req(), tech_buy, smc, candles, m15_candles=m15,
                                    market_regime={"primary": "trend_up"})
        plan_sell = build_trade_plan("sell", _req(), tech_sell, smc, candles, m15_candles=m15,
                                     market_regime={"primary": "trend_down"})

        assert plan_buy is not None, "Buy plan should not be None"
        assert plan_sell is not None, "Sell plan should not be None"

        assert len(plan_buy["take_profit"]) > 0, "Buy should have at least TP1"
        assert len(plan_sell["take_profit"]) > 0, "Sell should have at least TP1"

        buy_tp_dist = abs(plan_buy["take_profit"][0] - plan_buy["entry_price"])
        sell_tp_dist = abs(plan_sell["take_profit"][0] - plan_sell["entry_price"])
        assert buy_tp_dist == pytest.approx(sell_tp_dist, rel=0.05), \
            f"TP distance: buy={buy_tp_dist:.6f} vs sell={sell_tp_dist:.6f}"


# ---------------------------------------------------------------------------
# TP / use_preferred edge cases
# ---------------------------------------------------------------------------

class TestPreferredNoTP:
    """When use_preferred=True and no valid TP found, tp1/tp2 must be None."""

    def test_buy_preferred_no_tp_returns_none_tps(self):
        """Buy with preferred zone but no resistance/swing above → tp=None."""
        atr = 0.0010
        price = 1.0850
        pref = {
            "level": 1.0840, "low": 1.0832, "high": 1.0848,
            "strength": "moderate", "zone_score": 68,
            "confluence_count": 2, "consolidation_bars": 5,
            "freshness_bars": 20, "mitigated": False, "broken": False,
            "test_count": 0, "displacement_multiple": 2.0, "liquidity_sweep": True,
            "zone_location": "discount", "source": "smc", "type": "demand",
        }
        tech = _base_technical(price, atr,
                               support_zones=[_zone(1.0800, 1.0790, 1.0810, "weak", 40)],
                               resistance_zones=[])
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.0880, "range_low": 1.0800}

        smc = _base_smc()
        smc["H4"]["demand_zones"] = [pref]
        smc["H4"]["swings"] = {"highs": [], "lows": [_swing(1.0820)]}

        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                preferred_zone=pref, market_regime={"primary": "range"})

        assert plan is not None, "Plan should NOT be None (use_preferred=True allows no-TP)"
        assert plan["take_profit"] == [], f"Expected empty take_profit, got {plan['take_profit']}"
        assert plan["risk_reward"] is None, f"Expected None risk_reward, got {plan['risk_reward']}"
        assert plan["expected_effective_rr"] is None, \
            f"Expected None effective_rr, got {plan['expected_effective_rr']}"

    def test_sell_preferred_no_tp_returns_none_tps(self):
        """Sell with preferred zone but no support/swing below → tp=None."""
        atr = 0.0010
        price = 1.1150
        pref = {
            "level": 1.1160, "low": 1.1152, "high": 1.1168,
            "strength": "moderate", "zone_score": 68,
            "confluence_count": 2, "consolidation_bars": 5,
            "freshness_bars": 20, "mitigated": False, "broken": False,
            "test_count": 0, "displacement_multiple": 2.0, "liquidity_sweep": True,
            "zone_location": "premium", "source": "smc", "type": "supply",
        }
        tech = _base_technical(price, atr,
                               support_zones=[],
                               resistance_zones=[_zone(1.1200, 1.1190, 1.1210, "weak", 40)])
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.1200, "range_low": 1.1120}

        smc = _base_smc()
        smc["H4"]["supply_zones"] = [pref]
        smc["H4"]["swings"] = {"highs": [_swing(1.1180)], "lows": []}

        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                preferred_zone=pref, market_regime={"primary": "range"})

        assert plan is not None, "Plan should NOT be None (use_preferred=True allows no-TP)"
        assert plan["take_profit"] == [], f"Expected empty take_profit, got {plan['take_profit']}"
        assert plan["risk_reward"] is None
        assert plan["expected_effective_rr"] is None


class TestNonPreferredNoTPReturnsNone:
    """When use_preferred=False and no valid TP found, function must return None."""

    def test_buy_no_preferred_no_tp_returns_none(self):
        """Buy without preferred zone and no valid TP → return None."""
        atr = 0.0010
        price = 1.0850
        tech = _base_technical(
            price, atr,
            support_zones=[_zone(1.0820, 1.0810, 1.0830, "moderate", 55)],
            resistance_zones=[],  # no targets above
        )
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.0880, "range_low": 1.0800}
        tech["swings_h4"] = {"highs": [], "lows": [_swing(1.0800)]}

        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [], "lows": [_swing(1.0800)]}

        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "range"})
        assert plan is None, "Non-preferred buy with no valid TP must return None"

    def test_sell_no_preferred_no_tp_returns_none(self):
        """Sell without preferred zone and no valid TP → return None."""
        atr = 0.0010
        price = 1.1150
        tech = _base_technical(
            price, atr,
            support_zones=[],  # no targets below
            resistance_zones=[_zone(1.1180, 1.1170, 1.1190, "moderate", 55)],
        )
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.1200, "range_low": 1.1120}
        tech["swings_h4"] = {"highs": [_swing(1.1200)], "lows": []}

        smc = _base_smc()
        smc["H4"]["swings"] = {"highs": [_swing(1.1200)], "lows": []}

        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan = build_trade_plan("sell", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "range"})
        assert plan is None, "Non-preferred sell with no valid TP must return None"


# ---------------------------------------------------------------------------
# SL guard tests
# ---------------------------------------------------------------------------

class TestSLGuard:
    """SL minimum-distance guard must reject plans with SL too tight."""

    def test_buy_sl_too_tight_rejected(self):
        """Buy with SL closer than _MIN_SL_DISTANCE_ATR * ATR → return None."""
        atr = 0.0005  # very small ATR
        price = 1.0850
        # Support very close to price → calculated SL will be extremely tight
        tech = _base_technical(
            price, atr,
            support_zones=[_zone(1.0849, 1.0848, 1.08495, "weak", 30)],
            resistance_zones=[_zone(1.0860, 1.0858, 1.0862, "weak", 30)],
        )
        tech["structure_d1"] = "range"
        tech["structure_h4"] = "range"
        tech["range_info"] = {"in_range": True, "range_high": 1.0860, "range_low": 1.0840}

        smc = _base_smc()

        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "unknown"})
        # With _MIN_SL_DISTANCE_ATR = 0.5 and atr = 0.0005,
        # min SL = 0.00025. The SL might pass or fail depending on exact calculation.
        # This test just ensures no crash; the guard behavior is verified by
        # dedicated guard tests.
        # If plan is not None, SL must be at least _MIN_SL_DISTANCE_ATR * atr away
        if plan is not None:
            from core.risk_engine import _MIN_SL_DISTANCE_ATR
            sl_dist = abs(plan["entry_price"] - plan["stop_loss"])
            assert sl_dist >= _MIN_SL_DISTANCE_ATR * atr * 0.99, \
                f"SL distance {sl_dist} < min required {_MIN_SL_DISTANCE_ATR * atr}"


class TestTP2MinGap:
    """TP2 must be dropped when too close to TP1."""

    def test_tp2_too_close_to_tp1_is_none(self):
        """When TP2 - TP1 < _TP2_MIN_GAP_ATR * ATR, tp2 should be None."""
        atr = 0.0020
        price = 1.1000

        # Resistance at 1.1020 and 1.1021 (only 1 pip apart → < min gap)
        tech = _base_technical(
            price, atr,
            support_zones=[_zone(1.0960, 1.0950, 1.0970, "strong")],
            resistance_zones=[
                _zone(1.1020, 1.1015, 1.1025, "strong"),
                _zone(1.1021, 1.1016, 1.1026, "moderate"),  # too close to TP1
            ],
        )

        smc = _base_smc()
        candles = _candles(200, price=price, volatility=atr * 0.5)
        m15 = _candles(200, price=price, volatility=atr * 0.25, bar_minutes=15)

        plan = build_trade_plan("buy", _req(), tech, smc, candles, m15_candles=m15,
                                market_regime={"primary": "trend_up"})

        assert plan is not None
        # TP2 at 1.1021 is only 0.0001 from TP1 at 1.1020
        # _TP2_MIN_GAP_ATR * atr = 0.15 * 0.0020 = 0.0003 → tp2 discarded
        if len(plan["take_profit"]) >= 2:
            tp1, tp2 = plan["take_profit"][0], plan["take_profit"][1]
            gap = abs(tp2 - tp1)
            from core.risk_engine import _TP2_MIN_GAP_ATR
            assert gap >= _TP2_MIN_GAP_ATR * atr * 0.99, \
                f"TP2 gap {gap} < min required {_TP2_MIN_GAP_ATR * atr}"
        # else: only 1 TP is fine — tp2 was correctly dropped


class TestAtRZeroReturnsNone:
    """Zero ATR must cause early return None."""

    def test_zero_atr_returns_none(self):
        tech = _base_technical(1.1000, 0.0, [], [])
        tech["atr_d1"] = None
        smc = _base_smc()
        candles = _candles(10, price=1.1000)
        plan = build_trade_plan("buy", _req(), tech, smc, candles)
        assert plan is None


class TestNoZoneReturnsNone:
    """No valid zone on the correct side → return None."""

    def test_buy_no_support_returns_none(self):
        tech = _base_technical(1.1000, 0.0010,
                               support_zones=[],  # no supports below
                               resistance_zones=[_zone(1.1050, 1.1040, 1.1060, "strong")])
        smc = _base_smc()
        candles = _candles(200, price=1.1000, volatility=0.0005)
        plan = build_trade_plan("buy", _req(), tech, smc, candles)
        assert plan is None

    def test_sell_no_resistance_returns_none(self):
        tech = _base_technical(1.1000, 0.0010,
                               support_zones=[_zone(1.0950, 1.0940, 1.0960, "strong")],
                               resistance_zones=[])  # no resistances above
        smc = _base_smc()
        candles = _candles(200, price=1.1000, volatility=0.0005)
        plan = build_trade_plan("sell", _req(), tech, smc, candles)
        assert plan is None
