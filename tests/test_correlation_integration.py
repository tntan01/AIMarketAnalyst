"""
Comprehensive test suite for DXY/VIX/US10Y integration.
Tests all correlation functions with realistic market data and edge cases.
"""
from core.correlation_check import (
    compute_correlation_adjustment, _dxy_score, _vix_score, _us10y_score,
)
from core.signal_engine import score_scenario, clamp
from core.market_models import Candle
from datetime import datetime, timedelta

now = datetime.now()
d = timedelta(days=1)
passed = 0
failed = 0

def check(condition, msg):
    global passed, failed
    if condition:
        passed += 1
        print(f"  OK: {msg}")
    else:
        failed += 1
        print(f"  FAIL: {msg}")

print("=" * 60)
print("COMPREHENSIVE CORRELATION INTEGRATION TEST SUITE")
print("=" * 60)

# ==========================================
# 1. _vix_score
# ==========================================
print("\n[1] _vix_score")

check(_vix_score(None) == 0.0, "None -> 0")
check(_vix_score([]) == 0.0, "Empty -> 0")
check(_vix_score([Candle(time=now, open=0, high=0, low=0, close=0)]) == 0.0, "Zero close -> 0")
check(_vix_score([Candle(time=now, open=12, high=13, low=11, close=12.5)]) == 2.0, "VIX=12.5 -> +2 (calm)")
check(_vix_score([Candle(time=now, open=16, high=17, low=15, close=16.5)]) == 0.0, "VIX=16.5 -> 0 (normal)")
check(_vix_score([Candle(time=now, open=22, high=23, low=21, close=22.5)]) == -2.0, "VIX=22.5 -> -2 (tense)")
check(_vix_score([Candle(time=now, open=28, high=30, low=27, close=29.0)]) == -5.0, "VIX=29.0 -> -5 (risk-off)")
check(_vix_score([Candle(time=now, open=15, high=15, low=15, close=15.0)]) == 0.0, "VIX=15.0 -> 0 (boundary)")
check(_vix_score([Candle(time=now, open=14.9, high=15, low=14, close=14.9)]) == 2.0, "VIX=14.9 -> +2 (just below 15)")
check(_vix_score([Candle(time=now, open=20, high=20, low=20, close=20.0)]) == 0.0, "VIX=20.0 -> 0 (boundary)")
check(_vix_score([Candle(time=now, open=20.1, high=21, low=20, close=20.1)]) == -2.0, "VIX=20.1 -> -2 (just above 20)")
check(_vix_score([Candle(time=now, open=25, high=25, low=25, close=25.0)]) == -2.0, "VIX=25.0 -> -2 (boundary, not >25)")
check(_vix_score([Candle(time=now, open=25.1, high=26, low=25, close=25.1)]) == -5.0, "VIX=25.1 -> -5 (just above 25)")

# ==========================================
# 2. _dxy_score
# ==========================================
print("\n[2] _dxy_score")

# Empty/None
check(_dxy_score("buy", "EUR/USD", None) == 0.0, "None -> 0")
check(_dxy_score("buy", "EUR/USD", []) == 0.0, "Empty -> 0")
check(_dxy_score("buy", "EUR/USD", [Candle(time=now, open=1, high=1, low=1, close=1)]) == 0.0, "Single candle -> 0")

# Non-USD
dxy_up = [Candle(time=now-d, open=104.0, high=105.0, low=103.5, close=104.5),
          Candle(time=now, open=104.5, high=105.0, low=104.0, close=105.0)]
check(_dxy_score("buy", "EUR/GBP", dxy_up) == 0.0, "EUR/GBP (no USD) -> 0")
check(_dxy_score("sell", "GBP/JPY", dxy_up) == 0.0, "GBP/JPY (no USD) -> 0")

# Zero prev
dxy_bad = [Candle(time=now-d, open=0, high=0, low=0, close=0),
           Candle(time=now, open=105.0, high=106.0, low=104.0, close=105.0)]
check(_dxy_score("buy", "EUR/USD", dxy_bad) == 0.0, "Zero prev close -> 0")

# DXY up light (0.19%)
dxy_light = [Candle(time=now-d, open=104.0, high=104.5, low=103.8, close=104.5),
             Candle(time=now, open=104.5, high=105.0, low=104.4, close=104.7)]
check(_dxy_score("buy", "EUR/USD", dxy_light) == -2.0, "EUR/USD BUY + DXY up 0.19% -> -2.0")
check(_dxy_score("sell", "EUR/USD", dxy_light) == 1.0, "EUR/USD SELL + DXY up 0.19% -> +1.0")

# DXY up ro (0.48%)
dxy_med = [Candle(time=now-d, open=104.0, high=105.0, low=103.5, close=104.5),
           Candle(time=now, open=104.5, high=105.0, low=104.0, close=105.0)]
check(_dxy_score("buy", "EUR/USD", dxy_med) == -3.0, "EUR/USD BUY + DXY up 0.48% -> -3.0")
check(_dxy_score("sell", "EUR/USD", dxy_med) == 2.0, "EUR/USD SELL + DXY up 0.48% -> +2.0")

# DXY up manh (1.54%)
dxy_strong = [Candle(time=now-d, open=104.0, high=105.0, low=103.5, close=104.0),
              Candle(time=now, open=104.0, high=106.0, low=103.5, close=105.6)]
check(_dxy_score("buy", "EUR/USD", dxy_strong) == -5.0, "EUR/USD BUY + DXY up 1.54% -> -5.0")
check(_dxy_score("sell", "EUR/USD", dxy_strong) == 3.0, "EUR/USD SELL + DXY up 1.54% -> +3.0")
check(_dxy_score("buy", "USD/JPY", dxy_strong) == 3.0, "USD/JPY BUY + DXY up 1.54% -> +3.0")
check(_dxy_score("sell", "USD/JPY", dxy_strong) == -5.0, "USD/JPY SELL + DXY up 1.54% -> -5.0")

# DXY down manh (1.52%)
dxy_down = [Candle(time=now-d, open=105.0, high=105.5, low=104.5, close=105.0),
            Candle(time=now, open=105.0, high=105.2, low=103.0, close=103.4)]
check(_dxy_score("buy", "EUR/USD", dxy_down) == 3.0, "EUR/USD BUY + DXY down 1.52% -> +3.0")
check(_dxy_score("sell", "EUR/USD", dxy_down) == -5.0, "EUR/USD SELL + DXY down 1.52% -> -5.0")

# ==========================================
# 3. _us10y_score
# ==========================================
print("\n[3] _us10y_score")

us10y_up = [Candle(time=now-d, open=4.80, high=4.85, low=4.78, close=4.82),
            Candle(time=now, open=4.82, high=4.88, low=4.81, close=4.86)]

check(_us10y_score("buy", "EUR/USD", None) == 0.0, "None -> 0")
check(_us10y_score("buy", "EUR/USD", []) == 0.0, "Empty -> 0")
check(_us10y_score("buy", "EUR/USD", us10y_up) == 0.0, "EUR/USD (no XAU/JPY) -> 0")
check(_us10y_score("sell", "GBP/USD", us10y_up) == 0.0, "GBP/USD (no XAU/JPY) -> 0")

# XAU/USD: yield UP -> SELL favorable, BUY penalized
buy_xau = _us10y_score("buy", "XAU/USD", us10y_up)
sell_xau = _us10y_score("sell", "XAU/USD", us10y_up)
check(buy_xau < 0, f"XAU/USD BUY + yield up -> negative ({buy_xau})")
check(sell_xau > 0, f"XAU/USD SELL + yield up -> positive ({sell_xau})")

# XAU/USD: yield DOWN -> BUY favorable, SELL penalized
us10y_down = [Candle(time=now-d, open=4.86, high=4.90, low=4.82, close=4.85),
              Candle(time=now, open=4.85, high=4.86, low=4.50, close=4.50)]
buy_xau_d = _us10y_score("buy", "XAU/USD", us10y_down)
sell_xau_d = _us10y_score("sell", "XAU/USD", us10y_down)
check(buy_xau_d > 0, f"XAU/USD BUY + yield down -> positive ({buy_xau_d})")
check(sell_xau_d < 0, f"XAU/USD SELL + yield down -> negative ({sell_xau_d})")

# XAU/USD with yield > 5.5%
us10y_high = [Candle(time=now-d, open=5.60, high=5.65, low=5.55, close=5.62),
              Candle(time=now, open=5.62, high=5.70, low=5.60, close=5.68)]
sell_xau_h = _us10y_score("sell", "XAU/USD", us10y_high)
check(sell_xau_h < 1.5, f"XAU SELL + yield>5.5% dampened ({sell_xau_h})")

# USD/JPY: yield UP -> BUY favorable
buy_uj = _us10y_score("buy", "USD/JPY", us10y_up)
sell_uj = _us10y_score("sell", "USD/JPY", us10y_up)
check(buy_uj > 0, f"USD/JPY BUY + yield up -> positive ({buy_uj})")
check(sell_uj < 0, f"USD/JPY SELL + yield up -> negative ({sell_uj})")

# EUR/JPY BUY: yield up -> negative (not buy_usd)
eurjpy = _us10y_score("buy", "EUR/JPY", us10y_up)
check(eurjpy < 0, f"EUR/JPY BUY + yield up -> negative ({eurjpy})")

# Momentum 5-day
us10y_5d = [
    Candle(time=now-5*d, open=4.00, high=4.10, low=3.95, close=4.05),
    Candle(time=now-4*d, open=4.05, high=4.10, low=4.00, close=4.08),
    Candle(time=now-3*d, open=4.08, high=4.15, low=4.05, close=4.12),
    Candle(time=now-2*d, open=4.12, high=4.20, low=4.10, close=4.18),
    Candle(time=now-d, open=4.18, high=4.30, low=4.15, close=4.25),
    Candle(time=now, open=4.25, high=4.60, low=4.20, close=4.55),
]
# No XAU/JPY so 0 regardless
check(_us10y_score("buy", "EUR/USD", us10y_5d) == 0.0, "5d momentum but no XAU/JPY -> 0")
# XAU test with momentum: |4.55-4.05|=0.50, not >0.5, is >0.3 -> momentum=-1
# yield up + BUY XAU -> directional=-3, level: buy_usd=False -> 0
# total = -3*0.6 + 0 + (-1)*0.15 = -1.8 - 0.15 = -1.95 -> -2.0
mom_score = _us10y_score("buy", "XAU/USD", us10y_5d)
check(mom_score < -1.5, f"XAU BUY 5d momentum penalty ({mom_score})")

# ==========================================
# 4. compute_correlation_adjustment (integration)
# ==========================================
print("\n[4] compute_correlation_adjustment")

dxy_up_s = [Candle(time=now-d, open=104.0, high=105.0, low=103.5, close=104.0),
            Candle(time=now, open=104.0, high=106.0, low=103.5, close=105.6)]
vix_low = [Candle(time=now, open=14.0, high=14.5, low=13.8, close=14.2)]
vix_high = [Candle(time=now, open=28.0, high=29.0, low=27.0, close=28.5)]

# EUR/USD BUY: DXY strong up -> -5, VIX low -> +2, US10Y -> 0 -> -3
adj = compute_correlation_adjustment("EUR/USD", "buy", dxy_up_s, us10y_up, vix_low)
check(abs(adj - (-3.0)) < 0.1, f"EUR/USD BUY (DXY up, VIX low): {adj} (expected -3.0)")

# EUR/USD SELL: DXY -> +3, VIX -> +2 -> +5
adj = compute_correlation_adjustment("EUR/USD", "sell", dxy_up_s, us10y_up, vix_low)
check(abs(adj - 5.0) < 0.1, f"EUR/USD SELL (DXY up, VIX low): {adj} (expected 5.0)")

# VIX high overrides
adj = compute_correlation_adjustment("EUR/USD", "sell", dxy_up_s, us10y_up, vix_high)
check(abs(adj - (-2.0)) < 0.1, f"EUR/USD SELL (DXY up, VIX high): {adj} (expected -2.0)")

# No correlation data -> 0
adj = compute_correlation_adjustment("EUR/USD", "buy")
check(adj == 0.0, f"No data -> 0 ({adj})")

# Only VIX
adj = compute_correlation_adjustment("EUR/USD", "buy", vix_candles=vix_high)
check(abs(adj - (-5.0)) < 0.1, f"Only VIX high -> -5 ({adj})")

# Only DXY
adj = compute_correlation_adjustment("EUR/USD", "buy", dxy_candles=dxy_up_s)
check(abs(adj - (-5.0)) < 0.1, f"Only DXY up vs BUY EUR/USD -> -5 ({adj})")

# ==========================================
# 5. score_scenario with correlation_adjustment
# ==========================================
print("\n[5] score_scenario with correlation_adjustment")

tech = {
    "price": 1.0850,
    "ema50_d1": 1.0800, "ema200_d1": 1.0700,
    "ema50_h4": 1.0830,
    "structure_h4": "HH/HL", "structure_d1": "HH/HL",
    "rsi_h4": 52.0, "rsi_h4_previous": 48.0,
    "macd_histogram_h4": {"value": 0.0003, "previous_value": 0.0001, "previous2_value": -0.0001},
    "atr_h4": 0.0012, "atr_d1": 0.0045, "atr_avg_14d": 0.0050,
    "support_zones": [], "resistance_zones": [],
}

smc = {"H4": {}, "H1": {}}
regime = {"primary": "trend_up", "secondary": []}

# Without correlation adjustment
base = score_scenario("buy", tech, smc, 10, 20, macro_confidence=1.0, market_regime=regime)
print(f"  Base score (no corr): macro_alignment={base['macro_alignment']}, total={base['total']}")

# With positive correlation adjustment (+5)
boosted = score_scenario("buy", tech, smc, 10, 20, macro_confidence=1.0, market_regime=regime, correlation_adjustment=5.0)
print(f"  Boosted (+5 corr): macro_alignment={boosted['macro_alignment']}, total={boosted['total']}")
check(boosted["macro_alignment"] >= base["macro_alignment"], "Corr +5 -> macro_alignment >= base")
check("correlation_adjustment" in boosted, "correlation_adjustment in return dict")
check(boosted["correlation_adjustment"] == 5.0, "correlation_adjustment value correct")

# With negative correlation adjustment (-5)
penalized = score_scenario("buy", tech, smc, 10, 20, macro_confidence=1.0, market_regime=regime, correlation_adjustment=-10.0)
print(f"  Penalized (-10 corr): macro_alignment={penalized['macro_alignment']}, total={penalized['total']}")
check(penalized["macro_alignment"] >= 0, "macro_alignment clamped to >= 0")
check(penalized["macro_alignment"] <= 30, "macro_alignment clamped to <= 30")

# Test that correlation affects total score
check(boosted["total"] >= base["total"], "Positive corr increases or maintains total")
check(penalized["total"] <= base["total"], "Negative corr decreases or maintains total")

# ==========================================
# 6. Backward compatibility: signal_engine
# ==========================================
print("\n[6] Backward compatibility")

import inspect
sig = inspect.signature(score_scenario)
params = list(sig.parameters.keys())
check("correlation_adjustment" in params, "correlation_adjustment param exists")
check(sig.parameters["correlation_adjustment"].default == 0.0, "default is 0.0")

# Default call (no correlation_adjustment) should work
result = score_scenario("buy", tech, smc, 10, 20, macro_confidence=1.0, market_regime=regime)
check(isinstance(result, dict) and "total" in result, "Default call works and returns valid dict")

# ==========================================
# 7. _parse_yf_candles (scanner_controller)
# ==========================================
print("\n[7] _parse_yf_candles")

from controllers.scanner_controller import _parse_yf_candles
check(_parse_yf_candles(None) is None, "None -> None")

import pandas as pd
empty_df = pd.DataFrame()
check(_parse_yf_candles(empty_df) is None, "Empty DataFrame -> None")

# Realistic mock data
mock_data = pd.DataFrame({
    "Open": [104.0, 104.5, 105.0],
    "High": [104.5, 105.0, 105.5],
    "Low": [103.5, 104.0, 104.5],
    "Close": [104.2, 104.8, 105.2],
}, index=pd.DatetimeIndex([now-2*d, now-d, now]))

candles = _parse_yf_candles(mock_data)
check(candles is not None and len(candles) == 3, f"3 candles parsed ({len(candles) if candles else 0})")
check(abs(candles[0].close - 104.2) < 0.01, f"Close[0] = {candles[0].close} (expected 104.2)")
check(abs(candles[-1].close - 105.2) < 0.01, f"Close[-1] = {candles[-1].close} (expected 105.2)")

# ==========================================
# 8. mt5_service backward compat
# ==========================================
print("\n[8] mt5_service load_ohlcv signature")

from services.mt5_service import MT5Service
sig2 = inspect.signature(MT5Service.load_ohlcv)
params2 = list(sig2.parameters.keys())
check("skip_select" in params2, "skip_select param exists")
check(sig2.parameters["skip_select"].default == False, "skip_select default is False")

# ==========================================
# 9. ScannerScreen imports
# ==========================================
print("\n[9] UI imports")

from ui.screens.scanner_screen import ScannerScreen
check(True, "ScannerScreen imports OK")

# ==========================================
# 10. End-to-end: analysis_engine with correlation_context
# ==========================================
print("\n[10] End-to-end: analyze_symbol + correlation_context")

from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput

# This tests that the correlation_context param flows through correctly
# Note: We can't fully run analyze_symbol without real MT5 data,
# but we can verify the import and param signature
sig3 = inspect.signature(analyze_symbol)
params3 = list(sig3.parameters.keys())
check("correlation_context" in params3, "correlation_context param in analyze_symbol")

# ==========================================
# SUMMARY
# ==========================================
print("\n" + "=" * 60)
print(f"RESULTS: {passed} passed, {failed} failed out of {passed + failed} tests")
if failed == 0:
    print("ALL TESTS PASSED")
else:
    print(f"{failed} TESTS FAILED")
print("=" * 60)
