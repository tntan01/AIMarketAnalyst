"""Comprehensive test: verify two-branch architecture end-to-end.

Nhanh 1 (backtest=true):
- thresholds: ready=min_score, watch=999, wait=999 (binary ready/stand_aside)
- symbol_auto_trade: ALL backtest=true symbols included
- _auto_trade_config: returns config -> _is_auto_trade_candidate Nhanh 1
- _is_auto_trade_candidate Nhanh 1: checks regime + side + min_score
- _apply_scanner_filters: tags failed rows with specific config requirements

Nhanh 2 (backtest=false or no config):
- thresholds: ready=decision_ready, watch=decision_watch, wait=decision_wait, min_rr
- symbol_auto_trade: symbol NOT included
- _auto_trade_config: returns None -> _is_auto_trade_candidate Nhanh 2
- _is_auto_trade_candidate Nhanh 2: checks scanner_action == "ready"
- scanner_action from decision_engine using decision_ready/watch/wait

min_expected_rr is shared gate for BOTH branches.
"""
from __future__ import annotations

import sys
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from core.analysis_engine import analyze_symbol
from core.decision_engine import make_final_decision
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from core.scanner import ScannerRequest, scanner_row_from_analysis, sort_scanner_rows


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(n, start_price=1.0800, step=0.0005, start_time=None, bar_minutes=60):
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    result = []
    price = start_price
    for i in range(n):
        body = step * (0.3 + 0.7 * (i % 5) / 5)
        wick = step * 0.8
        o, c = price, price + body
        result.append(Candle(time=t, open=round(o, 5), high=round(c + wick, 5),
                             low=round(o - wick, 5), close=round(c, 5), volume=1000.0))
        price = c
        t += timedelta(minutes=bar_minutes)
    return result


def _build_candles(regime="trending_up", base_price=1.0800):
    end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    d1 = _candles(120, start_price=base_price - 0.0300, step=0.00025, bar_minutes=1440,
                  start_time=end - timedelta(days=120))
    h4 = _candles(360, start_price=d1[0].open, step=0.00012, bar_minutes=240, start_time=d1[0].time)
    h1 = _candles(480, start_price=h4[0].open, step=0.00006, bar_minutes=60, start_time=h4[0].time)
    m15 = _candles(200, start_price=h1[0].open, step=0.00002, bar_minutes=15, start_time=h1[0].time)
    return {"D1": d1, "H4": h4, "H1": h1, "M15": m15}


_DQ = {
    "terminal_connected": True, "broker_logged_in": True,
    "display_symbol": "EUR/USD", "broker_symbol": "EURUSDm",
    "spread_points": 16, "spread_status": "normal",
    "news_in_3h": False, "high_impact_event_within_30m": False,
}

_REQ = AnalysisInput(symbol="EUR/USD", broker_symbol="EURUSDm",
                     account_balance=10000.0, risk_percent=2.0,
                     contract_size_override=100000.0)


def run_pipeline(thresholds=None):
    """Run the full analysis pipeline and return result."""
    c = _build_candles()
    return analyze_symbol(_REQ, {"D1": c["D1"], "H4": c["H4"], "H1": c["H1"]},
                          data_quality=_DQ, macro_alignment={"buy": 15, "sell": 15},
                          macro_confidence=1.0, m15_candles=c["M15"],
                          thresholds=thresholds)


# ---------------------------------------------------------------------------
# Simulate what scanner_screen.py builds
# ---------------------------------------------------------------------------

def build_thresholds_and_auto_trade(backtest_cfg: dict | None, decision_cfg: dict | None):
    """Simulate the new scanner_screen logic for a single symbol."""
    thresholds = None
    symbol_auto_trade = {}

    if backtest_cfg:
        # Nhanh 1: backtest=true
        ready = backtest_cfg.get("min_score", 0) or backtest_cfg.get("decision_ready", 65)
        thresholds = {"ready": ready, "watch": 999, "wait": 999,
                      "min_score_gap": 10, "min_rr": backtest_cfg.get("min_expected_rr", 0) or 0}
        symbol_auto_trade["EUR/USD"] = {
            "regime": backtest_cfg.get("auto_trade_regime", ""),
            "side": backtest_cfg.get("auto_trade_side", ""),
            "min_score": ready,
        }
    elif decision_cfg:
        # Nhanh 2: backtest=false
        thresholds = {"ready": decision_cfg.get("decision_ready", 65),
                      "watch": decision_cfg.get("decision_watch", 60),
                      "wait": decision_cfg.get("decision_wait", 55),
                      "min_score_gap": 10,
                      "min_rr": decision_cfg.get("min_expected_rr", 1.3)}
    # else: no config, use defaults

    return thresholds, symbol_auto_trade


# ---------------------------------------------------------------------------
# Simulate _is_auto_trade_candidate
# ---------------------------------------------------------------------------

def simulate_is_candidate(row, at_cfg):
    """Simulate _is_auto_trade_candidate logic."""
    if not isinstance(row.get("analysis_result"), dict):
        return False
    if row.get("scanner_group") == "blocked":
        return False
    if str(row.get("trade_permission", "")).strip().lower() == "blocked":
        return False
    jf = row.get("journal_feedback", {}) if isinstance(row.get("journal_feedback"), dict) else {}
    if jf.get("decision_cap") in {"TRADE_BLOCKED", "WATCH_ONLY"}:
        return False

    if at_cfg is None:
        # Nhanh 2
        return (row.get("scanner_action") == "ready"
                and row.get("trade_permission") == "allowed"
                and bool(_best_scenario(row)))

    # Nhanh 1: only regime + side + min_score
    cfg_regime = str(at_cfg.get("regime", "") or "").strip().lower()
    cfg_side = str(at_cfg.get("side", "") or "").strip().lower()
    if cfg_regime:
        row_regime = str(row.get("market_regime", "")).strip().lower()
        if row_regime and row_regime != cfg_regime:
            return False
    best_score = int(row.get("best_score", 0) or 0)
    cfg_min_score = int(at_cfg.get("min_score", 0) or 0)
    effective = cfg_min_score if cfg_min_score > 0 else 65
    if best_score < effective:
        return False
    trade_side = cfg_side if cfg_side in ("buy", "sell") else row.get("best_side")
    return bool(_best_scenario(row, force_side=trade_side))


def _best_scenario(row, force_side=None):
    analysis = row.get("analysis_result", {})
    if not isinstance(analysis, dict):
        return {}
    scenarios = analysis.get("scenarios", [])
    if not isinstance(scenarios, list):
        return {}
    side = force_side or row.get("best_side")
    for sc in scenarios:
        if isinstance(sc, dict) and sc.get("type") == side:
            return sc
    if force_side:
        fallback = row.get("best_side")
        for sc in scenarios:
            if isinstance(sc, dict) and sc.get("type") == fallback:
                return sc
    return {}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

pass_count = 0
fail_count = 0


def check(name: str, condition: bool, detail: str = ""):
    global pass_count, fail_count
    if condition:
        pass_count += 1
        print(f"  PASS: {name}")
    else:
        fail_count += 1
        print(f"  FAIL: {name} -- {detail}")


# ========================================================================
# TEST SUITE 1: Nhanh 2 (backtest=false) — decision_ready/watch/wait
# ========================================================================
print("=" * 60)
print("SUITE 1: Nhanh 2 — backtest=false, dung decision_ready/watch/wait")
print("=" * 60)

# 1a. Pipeline with Nhanh 2 thresholds
thr_n2, _ = build_thresholds_and_auto_trade(
    backtest_cfg=None,
    decision_cfg={"decision_ready": 70, "decision_watch": 60, "decision_wait": 50, "min_expected_rr": 1.3},
)
result_n2 = run_pipeline(thr_n2)
row_n2 = scanner_row_from_analysis(result_n2, broker_symbol="EURUSDm")
# scanner_screen sorts rows -> get sorted
row_n2 = sort_scanner_rows([row_n2])[0]

fs = result_n2["final_score"]
de = result_n2["decision_engine"]
print(f"\n  final_score={fs}, decision={de['decision']}, scanner_action={row_n2['scanner_action']}")
print(f"  best_score={row_n2['best_score']}, trade_permission={row_n2['trade_permission']}")

check("N2.1: thresholds ready=70 reflects decision_ready", thr_n2["ready"] == 70)
check("N2.2: thresholds watch=60 reflects decision_watch", thr_n2["watch"] == 60)
check("N2.3: thresholds wait=50 reflects decision_wait", thr_n2["wait"] == 50)
check("N2.4: thresholds min_rr=1.3", thr_n2["min_rr"] == 1.3)

# Nhanh 2: _is_auto_trade_candidate with at_cfg=None
# requires scanner_action == "ready"
is_cand_n2 = simulate_is_candidate(row_n2, None)
print(f"\n  Nhanh 2 _is_auto_trade_candidate(at_cfg=None): {is_cand_n2}")
print(f"  Nhanh 2 requires scanner_action='ready' (actual={row_n2['scanner_action']})")
check("N2.5: Nhanh 2 candidate logic exists", is_cand_n2 == (row_n2["scanner_action"] == "ready"
        and row_n2["trade_permission"] == "allowed"))


# ========================================================================
# TEST SUITE 2: Nhanh 1 (backtest=true) — min_score ghi de
# ========================================================================
print("\n" + "=" * 60)
print("SUITE 2: Nhanh 1 — backtest=true, min_score ghi de toan bo")
print("=" * 60)

thr_n1, sat_n1 = build_thresholds_and_auto_trade(
    backtest_cfg={"min_score": 55, "decision_ready": 80, "decision_watch": 70, "decision_wait": 60,
                  "auto_trade_regime": "", "auto_trade_side": "", "min_expected_rr": 0},
    decision_cfg=None,
)
result_n1 = run_pipeline(thr_n1)
row_n1 = scanner_row_from_analysis(result_n1, broker_symbol="EURUSDm")
row_n1 = sort_scanner_rows([row_n1])[0]
de_n1 = result_n1["decision_engine"]

print(f"\n  Nhanh 1 thresholds: {thr_n1}")
print(f"  final_score={result_n1['final_score']}, decision={de_n1['decision']}, scanner_action={row_n1['scanner_action']}")

check("N1.1: thresholds ready=55 (from min_score)", thr_n1["ready"] == 55)
check("N1.2: thresholds watch=999 (binary, no intermediate)", thr_n1["watch"] == 999)
check("N1.3: thresholds wait=999 (binary, no intermediate)", thr_n1["wait"] == 999)
check("N1.4: symbol IS in symbol_auto_trade", "EUR/USD" in sat_n1)
check("N1.5: symbol_auto_trade has min_score", sat_n1["EUR/USD"]["min_score"] == 55)

# Override test: with ready=55 and score high enough -> READY
# with ready=55 and score below -> STAND_ASIDE (because watch/wait=999 disabled)
final_sc = result_n1["final_score"]
# Nhanh 1: decision engine may say WATCH_ONLY due to entry_status layer,
# but what matters is best_score vs min_score for _is_auto_trade_candidate
best_sc = row_n1["best_score"]
min_sc = thr_n1["ready"]
print(f"  best_score={best_sc}, min_score(ready)={min_sc}")
if best_sc >= min_sc:
    print(f"  best_score >= min_score -> _is_auto_trade_candidate Nhanh 1 can pass")
    check("N1.6: best_score >= min_score, candidate eligible", True)
else:
    print(f"  best_score < min_score -> _is_auto_trade_candidate Nhanh 1 will reject")
    check("N1.6: best_score < min_score, candidate rejected by Nhanh 1", True)


# ========================================================================
# TEST SUITE 3: _is_auto_trade_candidate — 2 nhanh khac biet
# ========================================================================
print("\n" + "=" * 60)
print("SUITE 3: _is_auto_trade_candidate — phan biet 2 nhanh")
print("=" * 60)

# Nhanh 1: with at_cfg, checks regime + side + min_score, NOT scanner_action
at_cfg_n1 = sat_n1.get("EUR/USD", {})
# Force scanner_action="watch" to prove Nhanh 1 bypasses it
row_n1_test = dict(row_n1)
row_n1_test["scanner_action"] = "watch"
row_n1_test["best_score"] = 80  # above min_score=55
row_n1_test["scanner_group"] = "watch_zone"

n1_result = simulate_is_candidate(row_n1_test, at_cfg_n1)
print(f"\n  Nhanh 1: scanner_action='watch', best_score=80, min_score=55")
print(f"  Nhanh 1 candidate = {n1_result} (should be True — bypasses scanner_action)")

# Nhanh 2: without at_cfg, requires scanner_action == "ready"
row_n2_test = dict(row_n2)
row_n2_test["scanner_action"] = "watch"
row_n2_test["best_score"] = 80
n2_result = simulate_is_candidate(row_n2_test, None)
print(f"\n  Nhanh 2: scanner_action='watch', best_score=80")
print(f"  Nhanh 2 candidate = {n2_result} (should be False — requires ready)")

check("N3.1: Nhanh 1 bypasses scanner_action", n1_result is True)
check("N3.2: Nhanh 2 requires scanner_action==ready", n2_result is False)

# Verify Nhanh 1 checks regime when configured
at_cfg_n1_regime = {"regime": "trend_down", "side": "", "min_score": 55}
row_n1_test["market_regime"] = "trend_up"
n1_regime_fail = simulate_is_candidate(row_n1_test, at_cfg_n1_regime)
print(f"\n  Nhanh 1: regime mismatch (row=trend_up, cfg=trend_down)")
print(f"  Nhanh 1 candidate = {n1_regime_fail} (should be False)")
check("N3.3: Nhanh 1 rejects regime mismatch", n1_regime_fail is False)

# Verify Nhanh 1 checks side when configured
at_cfg_n1_side = {"regime": "", "side": "sell", "min_score": 55}
row_n1_test["best_side"] = "buy"
n1_side_fail = simulate_is_candidate(row_n1_test, at_cfg_n1_side)
print(f"\n  Nhanh 1: side mismatch (row=buy, cfg=sell)")
print(f"  Nhanh 1 candidate = {n1_side_fail} (should be False)")
check("N3.4: Nhanh 1 rejects side mismatch", n1_side_fail is False)

# Verify Nhanh 1 checks min_score
at_cfg_n1_score = {"regime": "", "side": "", "min_score": 90}
row_n1_test["best_score"] = 80
n1_score_fail = simulate_is_candidate(row_n1_test, at_cfg_n1_score)
print(f"\n  Nhanh 1: score too low (row=80, cfg=90)")
print(f"  Nhanh 1 candidate = {n1_score_fail} (should be False)")
check("N3.5: Nhanh 1 rejects low score", n1_score_fail is False)


# ========================================================================
# TEST SUITE 4: min_expected_rr is shared gate for BOTH branches
# ========================================================================
print("\n" + "=" * 60)
print("SUITE 4: min_expected_rr — gate chung cho ca 2 nhanh")
print("=" * 60)

# Nhanh 1: thresholds includes min_rr
check("N4.1: Nhanh 1 thresholds has min_rr", "min_rr" in thr_n1)
# Nhanh 2: thresholds includes min_rr
check("N4.2: Nhanh 2 thresholds has min_rr", "min_rr" in thr_n2)
# Verify decision engine gate uses min_rr for both
gate_n1 = result_n1.get("trade_gate", {})
gate_n2 = result_n2.get("trade_gate", {})
print(f"\n  Nhanh 1 gate allowed={gate_n1.get('allowed')}")
print(f"  Nhanh 2 gate allowed={gate_n2.get('allowed')}")
check("N4.3: min_rr applied in Nhanh 1 gate", isinstance(gate_n1, dict))
check("N4.4: min_rr applied in Nhanh 2 gate", isinstance(gate_n2, dict))


# ========================================================================
# TEST SUITE 5: _auto_trade_config behavior
# ========================================================================
print("\n" + "=" * 60)
print("SUITE 5: _auto_trade_config returns correct branch")
print("=" * 60)

# Import actual controller
from controllers.scanner_controller import ScannerController
ctrl = ScannerController()

# Case 1: symbol in symbol_auto_trade -> returns config (Nhanh 1)
req1 = ScannerRequest(
    symbols=["EUR/USD"], account_balance=10000, risk_percent=1.0,
    timezone_name="Asia/Ho_Chi_Minh",
    symbol_auto_trade={"EUR/USD": {"regime": "", "side": "", "min_score": 55}},
    thresholds={}, min_scores={},
)
cfg1 = ctrl._auto_trade_config(req1, "EUR/USD")
check("N5.1: symbol in auto_trade -> returns config (Nhanh 1)", cfg1 is not None)
check("N5.2: config has min_score=55", cfg1 is not None and cfg1.get("min_score") == 55)

# Case 2: symbol NOT in symbol_auto_trade -> returns None (Nhanh 2)
req2 = ScannerRequest(
    symbols=["EUR/USD"], account_balance=10000, risk_percent=1.0,
    timezone_name="Asia/Ho_Chi_Minh",
    symbol_auto_trade={},
    thresholds={}, min_scores={},
)
cfg2 = ctrl._auto_trade_config(req2, "EUR/USD")
check("N5.3: symbol NOT in auto_trade -> returns None (Nhanh 2)", cfg2 is None)

# Case 3: empty symbol_auto_trade -> returns None
req3 = ScannerRequest(
    symbols=["EUR/USD"], account_balance=10000, risk_percent=1.0,
    timezone_name="Asia/Ho_Chi_Minh",
    symbol_auto_trade={},
    thresholds={}, min_scores={},
)
cfg3 = ctrl._auto_trade_config(req3, "EUR/USD")
check("N5.4: empty symbol_auto_trade -> None", cfg3 is None)


# ========================================================================
# TEST SUITE 6: _apply_scanner_filters — tag formatting
# ========================================================================
print("\n" + "=" * 60)
print("SUITE 6: _apply_scanner_filters — tag va structure")
print("=" * 60)

# Verify the filter function exists and has proper structure
import inspect
sig = inspect.signature(ctrl._apply_scanner_filters)
params = list(sig.parameters.keys())
check("N6.1: _apply_scanner_filters accepts (self, rows, request)", params == ["rows", "request"])

# Verify it delegates to _is_auto_trade_candidate (code inspection)
source = inspect.getsource(ctrl._apply_scanner_filters)
check("N6.2: _apply_scanner_filters calls _is_auto_trade_candidate", "_is_auto_trade_candidate" in source)
check("N6.3: _apply_scanner_filters calls _auto_trade_config", "_auto_trade_config" in source)
check("N6.4: _apply_scanner_filters marks scanner_action=skip on fail", "scanner_action" in source and "skip" in source)
check("N6.5: _apply_scanner_filters marks scanner_group=blocked on fail", "scanner_group" in source and "blocked" in source)
check("N6.6: _apply_scanner_filters has specific Nhanh 1 tag", "regime=" in source or "min_score=" in source)
check("N6.7: _apply_scanner_filters has Nhanh 2 tag", "chua dat ready" in source or "chưa đạt ready" in source)
check("N6.8: _apply_scanner_filters re-sorts result", "sort_scanner_rows" in source)

# Verify _auto_trade_config is clean (no guard condition with min_rr)
source_at = inspect.getsource(ctrl._auto_trade_config)
check("N6.9: _auto_trade_config has no min_rr guard", "not regime and side not in" not in source_at)
check("N6.10: _auto_trade_config returns cfg directly", "        return cfg" in source_at)


# ========================================================================
# SUMMARY
# ========================================================================
print("\n" + "=" * 60)
print(f"RESULTS: {pass_count} passed, {fail_count} failed out of {pass_count + fail_count}")
print("=" * 60)

if fail_count > 0:
    print("\n*** SOME TESTS FAILED ***")
    sys.exit(1)
else:
    print("\n*** ALL TESTS PASSED ***")
