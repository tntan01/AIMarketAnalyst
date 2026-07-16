"""Baseline snapshot for build_trade_plan() — run BEFORE refactoring.

Captures the output of build_trade_plan() for 8 diverse fixtures so the
refactored version can be compared field-by-field for 100% equivalence.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

sys.path.insert(0, ".")

from core.market_models import Candle
from core.risk_engine import AnalysisInput, build_trade_plan, round_price


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_candles(
    n: int,
    *,
    start_price: float = 1.0800,
    step: float = 0.0005,
    volatility: float = 0.0010,
    start_time: datetime | None = None,
    bar_minutes: int = 60,
) -> list[Candle]:
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    price = start_price
    for i in range(n):
        body = step * (0.3 + 0.7 * (i % 5) / 5)
        wick = volatility * 0.4
        open_p = price
        close_p = price + body
        high_p = close_p + wick * (0.3 + 0.7 * (i % 3) / 3)
        low_p = open_p - wick * (0.2 + 0.8 * (i % 4) / 4)
        candles.append(
            Candle(
                time=t,
                open=round(open_p, 5),
                high=round(high_p, 5),
                low=round(low_p, 5),
                close=round(close_p, 5),
                volume=float(1000 + i * 10),
            )
        )
        price = close_p
        t += timedelta(minutes=bar_minutes)
    return candles


def _make_candles_flat(
    n: int,
    *,
    price: float = 1.0800,
    volatility: float = 0.0005,
    start_time: datetime | None = None,
    bar_minutes: int = 60,
) -> list[Candle]:
    """Flat/range candles oscillating around a fixed price."""
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(n):
        wick = volatility * (0.5 + 0.5 * (i % 7) / 7)
        open_p = price + (i % 3 - 1) * volatility * 0.2
        close_p = price - (i % 3 - 1) * volatility * 0.2
        high_p = max(open_p, close_p) + wick
        low_p = min(open_p, close_p) - wick
        candles.append(
            Candle(
                time=t,
                open=round(open_p, 5),
                high=round(high_p, 5),
                low=round(low_p, 5),
                close=round(close_p, 5),
                volume=float(1000 + i * 10),
            )
        )
        t += timedelta(minutes=bar_minutes)
    return candles


def _make_request(symbol="EUR/USD", broker="EURUSDm", balance=10000.0, risk=2.0,
                  contract_override=100000.0) -> AnalysisInput:
    return AnalysisInput(
        symbol=symbol,
        broker_symbol=broker,
        account_balance=balance,
        risk_percent=risk,
        contract_size_override=contract_override,
    )


def _make_zone(level, low, high, strength="moderate", source="technical",
               zone_score=None, confluence_count=1, consolidation_bars=0,
               freshness_bars=None, mitigated=False, broken=False,
               test_count=0, displacement_multiple=0, liquidity_sweep=False,
               zone_location="unknown", type_="support"):
    return {
        "level": level,
        "low": low,
        "high": high,
        "type": type_,
        "strength": strength,
        "confluence_count": confluence_count,
        "consolidation_bars": consolidation_bars,
        "zone_score": zone_score if zone_score is not None else (75 if strength == "strong" else 50),
        "freshness_bars": freshness_bars,
        "mitigated": mitigated,
        "broken": broken,
        "test_count": test_count,
        "displacement_multiple": displacement_multiple,
        "liquidity_sweep": liquidity_sweep,
        "zone_location": zone_location,
        "source": source,
    }


def _make_smc_zone(level, low, high, strength="moderate", zone_score=65,
                   confluence_count=2, consolidation_bars=5, freshness_bars=20,
                   mitigated=False, broken=False, test_count=0,
                   displacement_multiple=2.5, liquidity_sweep=True,
                   zone_location="premium"):
    return {
        "level": level,
        "low": low,
        "high": high,
        "type": "demand" if low < level else "supply",
        "strength": strength,
        "confluence_count": confluence_count,
        "consolidation_bars": consolidation_bars,
        "zone_score": zone_score,
        "freshness_bars": freshness_bars,
        "mitigated": mitigated,
        "broken": broken,
        "test_count": test_count,
        "displacement_multiple": displacement_multiple,
        "liquidity_sweep": liquidity_sweep,
        "zone_location": zone_location,
        "source": "smc",
    }


def _make_swing(level, index=0, time_str="2026-06-01T00:00:00"):
    return {"level": level, "index": index, "time": time_str}


def _snap_plan(plan: dict[str, Any] | None) -> Any:
    """Round all float values for deterministic comparison."""
    if plan is None:
        return None
    out = {}
    for k, v in plan.items():
        if isinstance(v, float):
            out[k] = round(v, 5)
        elif isinstance(v, list) and all(isinstance(x, float) for x in v):
            out[k] = [round(x, 5) for x in v]
        elif isinstance(v, dict):
            out[k] = _snap_plan(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Shared candle data (enough for evaluate_entry not to crash)
# ---------------------------------------------------------------------------

BASE_TIME = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

# Trending up candles for buy-friendly contexts
h1_up = _make_candles(200, start_price=1.0800, step=0.00008, volatility=0.0003,
                      start_time=BASE_TIME - timedelta(hours=200), bar_minutes=60)
m15_up = _make_candles(200, start_price=h1_up[-1].close - 0.0010, step=0.00002,
                       volatility=0.00015,
                       start_time=h1_up[-1].time - timedelta(minutes=200 * 15),
                       bar_minutes=15)

# Trending down candles for sell-friendly contexts
h1_down = _make_candles(200, start_price=1.1200, step=-0.00008, volatility=0.0003,
                        start_time=BASE_TIME - timedelta(hours=200), bar_minutes=60)
m15_down = _make_candles(200, start_price=h1_down[-1].close + 0.0010, step=-0.00002,
                         volatility=0.00015,
                         start_time=h1_down[-1].time - timedelta(minutes=200 * 15),
                         bar_minutes=15)

# Flat/range candles
h1_flat = _make_candles_flat(200, price=1.1000, volatility=0.0008,
                             start_time=BASE_TIME - timedelta(hours=200), bar_minutes=60)
m15_flat = _make_candles_flat(200, price=1.1000, volatility=0.0004,
                              start_time=h1_flat[-1].time - timedelta(minutes=200 * 15),
                              bar_minutes=15)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

fixtures = []

# --- Fixture 1: buy + preferred SMC zone hợp lệ ---
price1 = 1.0850
atr1 = 0.0012
pref1 = _make_smc_zone(level=1.0820, low=1.0810, high=1.0830, strength="strong",
                       zone_score=82, zone_location="discount")

tech1 = {
    "price": price1,
    "atr_h4": atr1,
    "atr_d1": 0.0015,
    "ema50_d1": 1.0780,
    "ema200_d1": 1.0700,
    "ema50_h4": 1.0820,
    "ema50_d1_slope": 0.0002,
    "ema200_d1_slope": 0.0001,
    "rsi_h4": 45.0,
    "rsi_h4_previous": 42.0,
    "macd_histogram_h4": {"value": 0.00005, "previous_value": -0.00002, "previous2_value": -0.00005, "direction": "increasing"},
    "support_zones": [
        _make_zone(1.0800, 1.0790, 1.0810, strength="moderate", zone_score=55),
        _make_zone(1.0750, 1.0740, 1.0760, strength="weak", zone_score=40),
    ],
    "resistance_zones": [
        _make_zone(1.0900, 1.0890, 1.0910, strength="strong", zone_score=70),
        _make_zone(1.0950, 1.0940, 1.0960, strength="moderate", zone_score=55),
    ],
    "structure_d1": "trend_up",
    "structure_h4": "trend_up",
    "swings_h4": {"highs": [_make_swing(1.0900), _make_swing(1.0950)],
                  "lows": [_make_swing(1.0800), _make_swing(1.0750)]},
    "swings_d1": {"highs": [_make_swing(1.1000)], "lows": [_make_swing(1.0700)]},
    "range_info": {"in_range": False, "range_high": None, "range_low": None},
}

smc1 = {
    "H4": {
        "demand_zones": [
            {"low": 1.0810, "high": 1.0830, "level": 1.0820, "strength": "strong",
             "zone_score": 82, "confluence_count": 3, "consolidation_bars": 8,
             "freshness_bars": 15, "mitigated": False, "broken": False,
             "test_count": 0, "displacement_multiple": 3.0, "liquidity_sweep": True,
             "zone_location": "discount", "source": "smc", "type": "demand"},
        ],
        "supply_zones": [
            {"low": 1.0890, "high": 1.0910, "level": 1.0900, "strength": "moderate",
             "zone_score": 60, "confluence_count": 2, "consolidation_bars": 5,
             "freshness_bars": 30, "mitigated": False, "broken": False,
             "test_count": 1, "displacement_multiple": 2.0, "liquidity_sweep": False,
             "zone_location": "premium", "source": "smc", "type": "supply"},
        ],
        "swings": {
            "highs": [_make_swing(1.0900, 10), _make_swing(1.0950, 20)],
            "lows": [_make_swing(1.0800, 5), _make_swing(1.0750, 15)],
        },
        "liquidity_pools": {
            "equal_highs": [1.0905],
            "equal_lows": [1.0795],
        },
        "bos": True,
        "displacement": "bullish",
        "choch": False,
        "fvg": True,
    },
}

regime_trend_up = {"primary": "trend_up"}

fixtures.append({
    "name": "buy_preferred_smc_valid",
    "side": "buy",
    "request": _make_request(),
    "technical": tech1,
    "smc": smc1,
    "h1_candles": h1_up,
    "m15_candles": m15_up,
    "preferred_zone": pref1,
    "market_regime": regime_trend_up,
    "spread_price": 0.00012,
})


# --- Fixture 2: sell + preferred SMC zone hợp lệ ---
price2 = 1.1150
atr2 = 0.0012
pref2 = _make_smc_zone(level=1.1180, low=1.1170, high=1.1190, strength="strong",
                       zone_score=82, zone_location="premium")

tech2 = {
    "price": price2,
    "atr_h4": atr2,
    "atr_d1": 0.0015,
    "ema50_d1": 1.1200,
    "ema200_d1": 1.1250,
    "ema50_h4": 1.1170,
    "ema50_d1_slope": -0.0002,
    "ema200_d1_slope": -0.0001,
    "rsi_h4": 58.0,
    "rsi_h4_previous": 62.0,
    "macd_histogram_h4": {"value": -0.00005, "previous_value": 0.00002, "previous2_value": 0.00005, "direction": "decreasing"},
    "support_zones": [
        _make_zone(1.1100, 1.1090, 1.1110, strength="moderate", zone_score=55),
        _make_zone(1.1050, 1.1040, 1.1060, strength="weak", zone_score=40),
    ],
    "resistance_zones": [
        _make_zone(1.1200, 1.1190, 1.1210, strength="strong", zone_score=70),
        _make_zone(1.1250, 1.1240, 1.1260, strength="moderate", zone_score=55),
    ],
    "structure_d1": "trend_down",
    "structure_h4": "trend_down",
    "swings_h4": {"highs": [_make_swing(1.1200), _make_swing(1.1250)],
                  "lows": [_make_swing(1.1100), _make_swing(1.1050)]},
    "swings_d1": {"highs": [_make_swing(1.1300)], "lows": [_make_swing(1.1000)]},
    "range_info": {"in_range": False, "range_high": None, "range_low": None},
}

smc2 = {
    "H4": {
        "demand_zones": [
            {"low": 1.1090, "high": 1.1110, "level": 1.1100, "strength": "moderate",
             "zone_score": 60, "confluence_count": 2, "consolidation_bars": 5,
             "freshness_bars": 30, "mitigated": False, "broken": False,
             "test_count": 1, "displacement_multiple": 2.0, "liquidity_sweep": False,
             "zone_location": "discount", "source": "smc", "type": "demand"},
        ],
        "supply_zones": [
            {"low": 1.1170, "high": 1.1190, "level": 1.1180, "strength": "strong",
             "zone_score": 82, "confluence_count": 3, "consolidation_bars": 8,
             "freshness_bars": 15, "mitigated": False, "broken": False,
             "test_count": 0, "displacement_multiple": 3.0, "liquidity_sweep": True,
             "zone_location": "premium", "source": "smc", "type": "supply"},
        ],
        "swings": {
            "highs": [_make_swing(1.1200, 10), _make_swing(1.1250, 20)],
            "lows": [_make_swing(1.1100, 5), _make_swing(1.1050, 15)],
        },
        "liquidity_pools": {
            "equal_highs": [1.1210],
            "equal_lows": [1.1090],
        },
        "bos": True,
        "displacement": "bearish",
        "choch": False,
        "fvg": True,
    },
}

regime_trend_down = {"primary": "trend_down"}

fixtures.append({
    "name": "sell_preferred_smc_valid",
    "side": "sell",
    "request": _make_request(),
    "technical": tech2,
    "smc": smc2,
    "h1_candles": h1_down,
    "m15_candles": m15_down,
    "preferred_zone": pref2,
    "market_regime": regime_trend_down,
    "spread_price": 0.00012,
})


# --- Fixture 3: buy + NO preferred zone, dùng S/R zone kỹ thuật ---
tech3 = {
    "price": 1.0850,
    "atr_h4": 0.0012,
    "atr_d1": 0.0015,
    "ema50_d1": 1.0780,
    "ema200_d1": 1.0700,
    "ema50_h4": 1.0830,
    "ema50_d1_slope": 0.0002,
    "ema200_d1_slope": 0.0001,
    "rsi_h4": 45.0,
    "rsi_h4_previous": 42.0,
    "macd_histogram_h4": {"value": 0.00005, "previous_value": -0.00002, "previous2_value": -0.00005, "direction": "increasing"},
    "support_zones": [
        _make_zone(1.0820, 1.0810, 1.0830, strength="strong", zone_score=70),
        _make_zone(1.0780, 1.0770, 1.0790, strength="moderate", zone_score=55),
    ],
    "resistance_zones": [
        _make_zone(1.0900, 1.0890, 1.0910, strength="strong", zone_score=75),
        _make_zone(1.0950, 1.0940, 1.0960, strength="moderate", zone_score=55),
    ],
    "structure_d1": "trend_up",
    "structure_h4": "trend_up",
    "swings_h4": {"highs": [_make_swing(1.0900), _make_swing(1.0950)],
                  "lows": [_make_swing(1.0810), _make_swing(1.0760)]},
    "swings_d1": {"highs": [_make_swing(1.1000)], "lows": [_make_swing(1.0650)]},
    "range_info": {"in_range": False, "range_high": None, "range_low": None},
}

smc3 = {
    "H4": {
        "demand_zones": [],
        "supply_zones": [],
        "swings": {
            "highs": [_make_swing(1.0900, 10), _make_swing(1.0950, 20)],
            "lows": [_make_swing(1.0810, 5), _make_swing(1.0760, 15)],
        },
        "liquidity_pools": {"equal_highs": [1.0905], "equal_lows": [1.0795]},
        "bos": True,
        "displacement": "bullish",
        "choch": False,
        "fvg": False,
    },
}

fixtures.append({
    "name": "buy_no_preferred_sr_zone",
    "side": "buy",
    "request": _make_request(),
    "technical": tech3,
    "smc": smc3,
    "h1_candles": h1_up,
    "m15_candles": m15_up,
    "preferred_zone": None,
    "market_regime": regime_trend_up,
    "spread_price": 0.00012,
})


# --- Fixture 4: sell + NO preferred zone, dùng S/R zone kỹ thuật ---
tech4 = {
    "price": 1.1150,
    "atr_h4": 0.0012,
    "atr_d1": 0.0015,
    "ema50_d1": 1.1200,
    "ema200_d1": 1.1250,
    "ema50_h4": 1.1170,
    "ema50_d1_slope": -0.0002,
    "ema200_d1_slope": -0.0001,
    "rsi_h4": 58.0,
    "rsi_h4_previous": 62.0,
    "macd_histogram_h4": {"value": -0.00005, "previous_value": 0.00002, "previous2_value": 0.00005, "direction": "decreasing"},
    "support_zones": [
        _make_zone(1.1100, 1.1090, 1.1110, strength="moderate", zone_score=55),
        _make_zone(1.1050, 1.1040, 1.1060, strength="weak", zone_score=40),
    ],
    "resistance_zones": [
        _make_zone(1.1180, 1.1170, 1.1190, strength="strong", zone_score=75),
        _make_zone(1.1220, 1.1210, 1.1230, strength="moderate", zone_score=55),
    ],
    "structure_d1": "trend_down",
    "structure_h4": "trend_down",
    "swings_h4": {"highs": [_make_swing(1.1190), _make_swing(1.1240)],
                  "lows": [_make_swing(1.1100), _make_swing(1.1050)]},
    "swings_d1": {"highs": [_make_swing(1.1300)], "lows": [_make_swing(1.0950)]},
    "range_info": {"in_range": False, "range_high": None, "range_low": None},
}

smc4 = {
    "H4": {
        "demand_zones": [],
        "supply_zones": [],
        "swings": {
            "highs": [_make_swing(1.1190, 10), _make_swing(1.1240, 20)],
            "lows": [_make_swing(1.1100, 5), _make_swing(1.1050, 15)],
        },
        "liquidity_pools": {"equal_highs": [1.1210], "equal_lows": [1.1090]},
        "bos": True,
        "displacement": "bearish",
        "choch": False,
        "fvg": False,
    },
}

fixtures.append({
    "name": "sell_no_preferred_sr_zone",
    "side": "sell",
    "request": _make_request(),
    "technical": tech4,
    "smc": smc4,
    "h1_candles": h1_down,
    "m15_candles": m15_down,
    "preferred_zone": None,
    "market_regime": regime_trend_down,
    "spread_price": 0.00012,
})


# --- Fixture 5: buy + use_preferred, no valid TP found (tp1/tp2 = None) ---
# Preferred zone is very close to price with no resistance above, range regime skips Fib,
# no equal highs, no swing highs = no TP possible
price5 = 1.0850
atr5 = 0.0010
pref5 = _make_smc_zone(level=1.0840, low=1.0832, high=1.0848, strength="moderate",
                       zone_score=68, zone_location="discount")

tech5 = {
    "price": price5,
    "atr_h4": atr5,
    "atr_d1": 0.0012,
    "ema50_d1": 1.0880,
    "ema200_d1": 1.0920,
    "ema50_h4": 1.0850,
    "ema50_d1_slope": -0.0001,
    "ema200_d1_slope": -0.00005,
    "rsi_h4": 48.0,
    "rsi_h4_previous": 50.0,
    "macd_histogram_h4": {"value": 0.00001, "previous_value": -0.00001, "previous2_value": -0.00003, "direction": "increasing"},
    "support_zones": [
        _make_zone(1.0800, 1.0790, 1.0810, strength="weak", zone_score=40),
    ],
    "resistance_zones": [],  # No resistance → no TP from S/R
    "structure_d1": "range",
    "structure_h4": "range",
    "swings_h4": {"highs": [], "lows": [_make_swing(1.0820)]},
    "swings_d1": {"highs": [], "lows": [_make_swing(1.0750)]},
    "range_info": {"in_range": True, "range_high": 1.0880, "range_low": 1.0800},
}

smc5 = {
    "H4": {
        "demand_zones": [
            {"low": 1.0832, "high": 1.0848, "level": 1.0840, "strength": "moderate",
             "zone_score": 68, "confluence_count": 2, "consolidation_bars": 5,
             "freshness_bars": 20, "mitigated": False, "broken": False,
             "test_count": 0, "displacement_multiple": 2.0, "liquidity_sweep": True,
             "zone_location": "discount", "source": "smc", "type": "demand"},
        ],
        "supply_zones": [],
        "swings": {"highs": [], "lows": [_make_swing(1.0820)]},
        "liquidity_pools": {"equal_highs": [], "equal_lows": []},
        "bos": False,
        "displacement": "bullish",
        "choch": False,
        "fvg": False,
    },
}

regime_range = {"primary": "range"}

fixtures.append({
    "name": "buy_preferred_no_tp",
    "side": "buy",
    "request": _make_request(),
    "technical": tech5,
    "smc": smc5,
    "h1_candles": h1_flat,
    "m15_candles": m15_flat,
    "preferred_zone": pref5,
    "market_regime": regime_range,
    "spread_price": 0.00010,
})


# --- Fixture 6: sell + use_preferred, no valid TP found (tp1/tp2 = None) ---
price6 = 1.1150
atr6 = 0.0010
pref6 = _make_smc_zone(level=1.1160, low=1.1152, high=1.1168, strength="moderate",
                       zone_score=68, zone_location="premium")

tech6 = {
    "price": price6,
    "atr_h4": atr6,
    "atr_d1": 0.0012,
    "ema50_d1": 1.1120,
    "ema200_d1": 1.1080,
    "ema50_h4": 1.1150,
    "ema50_d1_slope": 0.0001,
    "ema200_d1_slope": 0.00005,
    "rsi_h4": 52.0,
    "rsi_h4_previous": 50.0,
    "macd_histogram_h4": {"value": -0.00001, "previous_value": 0.00001, "previous2_value": 0.00003, "direction": "decreasing"},
    "support_zones": [],  # No support → no TP from S/R
    "resistance_zones": [
        _make_zone(1.1200, 1.1190, 1.1210, strength="weak", zone_score=40),
    ],
    "structure_d1": "range",
    "structure_h4": "range",
    "swings_h4": {"highs": [_make_swing(1.1180)], "lows": []},
    "swings_d1": {"highs": [_make_swing(1.1250)], "lows": []},
    "range_info": {"in_range": True, "range_high": 1.1200, "range_low": 1.1120},
}

smc6 = {
    "H4": {
        "demand_zones": [],
        "supply_zones": [
            {"low": 1.1152, "high": 1.1168, "level": 1.1160, "strength": "moderate",
             "zone_score": 68, "confluence_count": 2, "consolidation_bars": 5,
             "freshness_bars": 20, "mitigated": False, "broken": False,
             "test_count": 0, "displacement_multiple": 2.0, "liquidity_sweep": True,
             "zone_location": "premium", "source": "smc", "type": "supply"},
        ],
        "swings": {"highs": [_make_swing(1.1180)], "lows": []},
        "liquidity_pools": {"equal_highs": [], "equal_lows": []},
        "bos": False,
        "displacement": "bearish",
        "choch": False,
        "fvg": False,
    },
}

fixtures.append({
    "name": "sell_preferred_no_tp",
    "side": "sell",
    "request": _make_request(),
    "technical": tech6,
    "smc": smc6,
    "h1_candles": h1_flat,
    "m15_candles": m15_flat,
    "preferred_zone": pref6,
    "market_regime": regime_range,
    "spread_price": 0.00010,
})


# --- Fixture 7: buy + NO preferred + clearly invalid (SL too tight → return None) ---
# Very close support with tiny ATR so SL guard reject
tech7 = {
    "price": 1.0850,
    "atr_h4": 0.0005,  # Very small ATR
    "atr_d1": 0.0006,
    "ema50_d1": 1.0830,
    "ema200_d1": 1.0800,
    "ema50_h4": 1.0845,
    "ema50_d1_slope": 0.00005,
    "ema200_d1_slope": 0.00003,
    "rsi_h4": 50.0,
    "rsi_h4_previous": 50.0,
    "macd_histogram_h4": {"value": 0.0, "previous_value": 0.0, "previous2_value": 0.0, "direction": "increasing"},
    "support_zones": [
        _make_zone(1.0845, 1.0843, 1.0847, strength="weak", zone_score=35),
    ],
    "resistance_zones": [
        _make_zone(1.0860, 1.0858, 1.0862, strength="weak", zone_score=35),
    ],
    "structure_d1": "range",
    "structure_h4": "range",
    "swings_h4": {"highs": [_make_swing(1.0860)], "lows": [_make_swing(1.0840)]},
    "swings_d1": {"highs": [_make_swing(1.0870)], "lows": [_make_swing(1.0830)]},
    "range_info": {"in_range": True, "range_high": 1.0860, "range_low": 1.0840},
}

smc7 = {
    "H4": {
        "demand_zones": [],
        "supply_zones": [],
        "swings": {"highs": [], "lows": []},
        "liquidity_pools": {"equal_highs": [], "equal_lows": []},
        "bos": False,
        "displacement": None,
        "choch": False,
        "fvg": False,
    },
}

fixtures.append({
    "name": "buy_invalid_sl_too_tight",
    "side": "buy",
    "request": _make_request(),
    "technical": tech7,
    "smc": smc7,
    "h1_candles": h1_flat,
    "m15_candles": m15_flat,
    "preferred_zone": None,
    "market_regime": {"primary": "unknown"},
    "spread_price": 0.00010,
})


# --- Fixture 8: sell + NO preferred + no valid TP → return None (non-use_preferred) ---
tech8 = {
    "price": 1.1150,
    "atr_h4": 0.0010,
    "atr_d1": 0.0012,
    "ema50_d1": 1.1120,
    "ema200_d1": 1.1080,
    "ema50_h4": 1.1150,
    "ema50_d1_slope": 0.0001,
    "ema200_d1_slope": 0.00005,
    "rsi_h4": 52.0,
    "rsi_h4_previous": 50.0,
    "macd_histogram_h4": {"value": -0.00001, "previous_value": 0.00001, "previous2_value": 0.00003, "direction": "decreasing"},
    "support_zones": [],  # No support below
    "resistance_zones": [
        _make_zone(1.1180, 1.1170, 1.1190, strength="strong", zone_score=70),
    ],
    "structure_d1": "range",
    "structure_h4": "range",
    "swings_h4": {"highs": [_make_swing(1.1180)], "lows": [_make_swing(1.1120)]},
    "swings_d1": {"highs": [_make_swing(1.1250)], "lows": [_make_swing(1.1100)]},
    "range_info": {"in_range": True, "range_high": 1.1200, "range_low": 1.1120},
}

smc8 = {
    "H4": {
        "demand_zones": [],
        "supply_zones": [],
        "swings": {"highs": [_make_swing(1.1180)], "lows": [_make_swing(1.1120)]},
        "liquidity_pools": {"equal_highs": [], "equal_lows": []},
        "bos": False,
        "displacement": None,
        "choch": False,
        "fvg": False,
    },
}

fixtures.append({
    "name": "sell_no_preferred_no_tp_return_none",
    "side": "sell",
    "request": _make_request(),
    "technical": tech8,
    "smc": smc8,
    "h1_candles": h1_down,
    "m15_candles": m15_down,
    "preferred_zone": None,
    "market_regime": regime_range,
    "spread_price": 0.00010,
})


# ---------------------------------------------------------------------------
# Run & snapshot
# ---------------------------------------------------------------------------

def main():
    results = {}
    for fx in fixtures:
        name = fx.pop("name")
        plan = build_trade_plan(**fx)
        results[name] = _snap_plan(plan)
        status = "None" if plan is None else f"plan (tp={plan.get('take_profit')})"
        print(f"  {name}: {status}")

    out_path = "scratch/build_trade_plan_baseline.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"\nBaseline saved to {out_path}")


if __name__ == "__main__":
    main()
