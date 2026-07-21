"""Diagnostic script: trace EURUSD through the entire signal pipeline.

Chay doc lap, khong can mo app.
Ket noi MT5, lay du lieu thuc te, chay analysis pipeline,
in ra KET QUA TUNG BUOC de xac dinh diem that bai.

Usage: python scratch/diagnose_eurusd_signal.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Fix Windows console encoding for box-drawing chars
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ── Step 0: Check MT5 connection ──────────────────────────────────────────
def step0_mt5_connection() -> tuple[bool, str]:
    """Kiem tra ket noi MT5."""
    try:
        import MetaTrader5 as mt5

        initialized = mt5.initialize()
        if not initialized:
            return False, f"MT5 initialize() failed: {mt5.last_error()}"
        term_info = mt5.terminal_info()
        if term_info is None:
            return False, "MT5 terminal_info() returned None"
        return True, f"MT5 connected: {term_info.name}, build {term_info.build}"
    except ImportError:
        return False, "MetaTrader5 module not found"
    except Exception as e:
        return False, f"MT5 error: {e}"


# ── Step 1: Load market data ──────────────────────────────────────────────
def step1_load_data(symbol: str) -> dict[str, Any]:
    """Load D1, H4, H1, M15 candles for a symbol from MT5."""
    import MetaTrader5 as mt5

    from services.mt5_service import MT5Service

    mt5_svc = MT5Service()
    available = mt5_svc.available_symbols(market_watch_only=True)
    broker = mt5_svc.resolve_symbol(symbol, available)
    if not broker:
        return {"error": f"Symbol {symbol} not found in Market Watch. Available: {available[:10]}..."}

    bars = {"D1": 120, "H4": 360, "H1": 480, "M15": 200}
    all_candles = mt5_svc.load_primary_timeframes(broker, bars)

    result = {
        "broker_symbol": broker,
        "candles": {},
        "data_quality": mt5_svc.symbol_data_quality(symbol, broker),
    }
    for tf in ["D1", "H4", "H1", "M15"]:
        candles = all_candles.get(tf, [])
        result["candles"][tf] = candles
        if candles:
            last = candles[-1]
            result[f"{tf}_last"] = {
                "time": str(last.time),
                "open": last.open,
                "high": last.high,
                "low": last.low,
                "close": last.close,
                "count": len(candles),
            }
        else:
            result[f"{tf}_last"] = {"error": "NO CANDLES", "count": 0}

    # Also get tick data
    try:
        tick = mt5.symbol_info_tick(broker)
        if tick is not None:
            result["tick"] = {"bid": tick.bid, "ask": tick.ask, "spread": tick.ask - tick.bid}
    except Exception:
        result["tick"] = {"error": "Cannot get tick"}

    return result


# ── Step 2: Build technical snapshot ──────────────────────────────────────
def step2_technical(d1, h4, h1) -> dict[str, Any]:
    """Build technical snapshot and print key values."""
    from core.technical_context import build_technical_snapshot, detect_market_regime

    tech = build_technical_snapshot(d1, h4, h1)
    regime = detect_market_regime(tech, False)

    keys = [
        "price", "atr_h4", "atr_d1", "atr_h1", "atr_avg_14d",
        "ema50_d1", "ema200_d1", "ema50_h4",
        "structure_h4", "structure_d1",
        "rsi_h4", "macd_histogram_h4",
    ]
    summary = {k: tech.get(k) for k in keys}
    summary["market_regime"] = regime
    summary["support_zones_count"] = len(tech.get("support_zones", []))
    summary["resistance_zones_count"] = len(tech.get("resistance_zones", []))

    # Print supports/resistances
    supports = tech.get("support_zones", [])
    resistances = tech.get("resistance_zones", [])
    summary["supports"] = [{"level": z.get("level"), "test_count": z.get("test_count")} for z in supports[:5]]
    summary["resistances"] = [{"level": z.get("level"), "test_count": z.get("test_count")} for z in resistances[:5]]

    return summary, tech, regime


# ── Step 3: Build SMC context ──────────────────────────────────────────────
def step3_smc(d1, h4, h1) -> dict[str, Any]:
    """Build SMC context."""
    from core.smc_context import build_smc_context, get_preferred_zone

    smc = build_smc_context(d1, h4, h1)
    price = h1[-1].close if h1 else 0.0

    h4_smc = smc.get("H4", {})
    h1_smc = smc.get("H1", {})

    summary = {
        "H4_displacement": h4_smc.get("displacement"),
        "H4_bos": h4_smc.get("bos"),
        "H4_choch": h4_smc.get("choch"),
        "H4_demand_zones": len(h4_smc.get("demand_zones", [])),
        "H4_supply_zones": len(h4_smc.get("supply_zones", [])),
        "H4_fvg": len(h4_smc.get("fvg", [])),
        "H4_order_blocks": len(h4_smc.get("order_blocks", [])),
        "H4_premium_discount": h4_smc.get("premium_discount"),
        "H1_displacement": h1_smc.get("displacement"),
        "H1_bos": h1_smc.get("bos"),
        "H1_choch": h1_smc.get("choch"),
        "H1_liquidity_sweeps": h1_smc.get("liquidity_sweeps"),
        "H1_internal_swings": {
            "highs_count": len(h1_smc.get("internal_swings", {}).get("highs", [])),
            "lows_count": len(h1_smc.get("internal_swings", {}).get("lows", [])),
        },
    }

    pz_buy = get_preferred_zone(smc, "buy", price=price)
    pz_sell = get_preferred_zone(smc, "sell", price=price)
    summary["preferred_zone_buy"] = {
        "level": pz_buy.get("level") if pz_buy else None,
        "zone_score": pz_buy.get("zone_score") if pz_buy else None,
        "source": pz_buy.get("source") if pz_buy else None,
    } if pz_buy else None
    summary["preferred_zone_sell"] = {
        "level": pz_sell.get("level") if pz_sell else None,
        "zone_score": pz_sell.get("zone_score") if pz_sell else None,
        "source": pz_sell.get("source") if pz_sell else None,
    } if pz_sell else None

    return summary, smc


# ── Step 4: Score scenarios ───────────────────────────────────────────────
def step4_score(side: str, technical, smc, risk_score, macro_alignment, macro_confidence, market_regime, corr_adj, macro_context) -> dict[str, Any]:
    """Score one scenario side."""
    from core.signal_engine import score_scenario

    result = score_scenario(
        side, technical, smc, risk_score,
        macro_alignment.get(side, 15),
        macro_confidence=macro_confidence,
        market_regime=market_regime,
        correlation_adjustment=corr_adj,
        macro_context=macro_context,
    )
    return {
        "signal_score": result.get("signal_score"),
        "total": result.get("total"),
        "trend_alignment": result.get("trend_alignment"),
        "momentum_alignment": result.get("momentum_alignment"),
        "location_quality": result.get("location_quality"),
        "smc_quality": result.get("smc_quality"),
        "smc_reason": result.get("smc_reason"),
        "risk_condition": result.get("risk_condition"),
        "macro_alignment": result.get("macro_alignment"),
        "macro_status": result.get("macro_status"),
        "rating": result.get("rating"),
        "reason_codes": result.get("reason_codes"),
        "penalty_codes": result.get("penalty_codes"),
        "smc_score_cap": result.get("smc_score_cap"),
    }, result


# ── Step 5: Build trade plan ───────────────────────────────────────────────
def step5_trade_plan(side: str, request, technical, smc, h1, m15, spread_price, market_regime, preferred_zone, is_backtest=False) -> dict[str, Any]:
    """Build trade plan for one side."""
    from core.risk_engine import build_trade_plan

    plan = build_trade_plan(
        side, request, technical, smc, h1,
        m15_candles=m15,
        spread_price=spread_price,
        market_regime=market_regime,
        preferred_zone=preferred_zone,
        is_backtest=is_backtest,
    )
    if plan is None:
        return {"error": "build_trade_plan returned None (no valid zone found)", "plan": None}

    return {
        "entry_zone": plan.get("entry_zone"),
        "entry_status": plan.get("entry_status"),
        "trigger_type": plan.get("trigger_type"),
        "confirmation_score": plan.get("confirmation_score"),
        "ready_to_trade": plan.get("ready_to_trade"),
        "invalid_reason": plan.get("invalid_reason"),
        "price_in_entry_zone": plan.get("price_in_entry_zone"),
        "m15_quality": plan.get("m15_quality"),
        "m15_available": plan.get("m15_available"),
        "m15_confirmed": plan.get("m15_confirmed"),
        "m15_structure": plan.get("m15_structure"),
        "m15_displacement": plan.get("m15_displacement"),
        "stop_loss": plan.get("stop_loss"),
        "take_profit": plan.get("take_profit"),
        "risk_reward": plan.get("risk_reward"),
        "expected_effective_rr": plan.get("expected_effective_rr"),
        "risk_reward_range": plan.get("risk_reward_range"),
        "entry_ladder": plan.get("entry_ladder"),
        "internal_structure": plan.get("internal_structure"),
        "reason_codes": plan.get("reason_codes"),
        "warning_codes": plan.get("warning_codes"),
        "block_codes": plan.get("block_codes"),
    }, plan


# ── Step 6: Trade permission ──────────────────────────────────────────────
def step6_permission(data_quality, risk_score, best_score, min_score=65) -> dict[str, Any]:
    """Calculate trade permission."""
    from core.risk_engine import calc_trade_permission

    tp = calc_trade_permission(data_quality, risk_score, best_score, min_score=min_score)
    return {
        "status": tp.get("status"),
        "reason": tp.get("reason"),
        "min_score": tp.get("min_score"),
    }, tp


# ── Step 7: Trade gates ──────────────────────────────────────────────────
def step7_gates(gate_context: dict[str, Any]) -> dict[str, Any]:
    """Check trade gates."""
    from core.trade_gate_engine import check_trade_gates

    result = check_trade_gates(gate_context)
    return {
        "allowed": result.get("allowed"),
        "decision_cap": result.get("decision_cap"),
        "block_codes": result.get("block_codes"),
        "warning_codes": result.get("warning_codes"),
        "reasons": result.get("reasons"),
    }, result


# ── Step 8: Decision engine ──────────────────────────────────────────────
def step8_decision(final_score, gate_result, entry_status, score_gap, trade_permission, thresholds) -> dict[str, Any]:
    """Run decision engine."""
    from core.decision_engine import make_final_decision

    result = make_final_decision(
        final_score=final_score,
        gate_result=gate_result,
        entry_status=entry_status,
        score_gap=score_gap,
        trade_permission=trade_permission,
        thresholds=thresholds,
    )
    return {
        "decision": result.get("decision"),
        "legacy_action": result.get("legacy_action"),
        "final_score": result.get("final_score"),
        "allowed": result.get("allowed"),
        "reason": result.get("reason"),
        "reason_codes": result.get("reason_codes"),
        "warning_codes": result.get("warning_codes"),
        "block_codes": result.get("block_codes"),
        "decision_cap": result.get("decision_cap"),
        "score_breakdown": result.get("score_breakdown"),
    }, result


# ── Step 9: Scanner row creation ──────────────────────────────────────────
def step9_scanner_row(result: dict[str, Any]) -> dict[str, Any]:
    """Convert analysis result to scanner row."""
    from core.scanner import scanner_row_from_analysis

    row = scanner_row_from_analysis(result)
    return {
        "symbol": row.get("symbol"),
        "scanner_action": row.get("scanner_action"),
        "scanner_group": row.get("scanner_group"),
        "scanner_decision": row.get("scanner_decision"),
        "legacy_action": row.get("legacy_action"),
        "trade_permission": row.get("trade_permission"),
        "best_side": row.get("best_side"),
        "best_score": row.get("best_score"),
        "final_score": row.get("final_score"),
        "opportunity_score": row.get("opportunity_score"),
        "display_action": row.get("display_action"),
        "entry_status": row.get("entry_status"),
        "price_vs_zone": row.get("price_vs_zone"),
        "m15_quality": row.get("m15_quality"),
        "expected_effective_rr": row.get("expected_effective_rr"),
        "short_reason": row.get("short_reason"),
        "permission_reason": row.get("permission_reason"),
    }, row


# ── Step 10: Scanner filter simulation ────────────────────────────────────
def step10_filter_check(row: dict[str, Any], at_cfg: dict | None = None) -> dict[str, Any]:
    """Simulate _is_auto_trade_candidate and _apply_scanner_filters."""
    checks = {}

    # Check 1: analysis_result exists
    checks["has_analysis_result"] = isinstance(row.get("analysis_result"), dict)

    # Check 2: scanner_group not blocked
    checks["scanner_group_not_blocked"] = row.get("scanner_group") != "blocked"

    # Check 3: trade_permission not blocked
    tp = str(row.get("trade_permission", "")).strip().lower()
    checks["trade_permission_not_blocked"] = tp != "blocked"

    # Check 4: journal feedback cap
    jf = row.get("journal_feedback") if isinstance(row.get("journal_feedback"), dict) else {}
    jf_cap = str(jf.get("decision_cap", ""))
    checks["journal_not_blocking"] = jf_cap not in ("TRADE_BLOCKED", "WATCH_ONLY")

    # Pre-checks
    pre_checks_pass = all([
        checks["has_analysis_result"],
        checks["scanner_group_not_blocked"],
        checks["trade_permission_not_blocked"],
        checks["journal_not_blocking"],
    ])

    # Check 5A: No config — strict criteria
    checks["scanner_action_is_ready"] = row.get("scanner_action") == "ready"
    checks["trade_permission_is_allowed"] = row.get("trade_permission") == "allowed"
    has_scenario = False
    analysis = row.get("analysis_result", {})
    if isinstance(analysis, dict):
        scenarios = analysis.get("scenarios", [])
        if isinstance(scenarios, list):
            best_side = row.get("best_side")
            for s in scenarios:
                if isinstance(s, dict) and s.get("type") == best_side and s.get("entry_zone_source") != "fallback":
                    has_scenario = True
                    break
    checks["has_valid_scenario"] = has_scenario

    no_config_pass = all([
        checks["scanner_action_is_ready"],
        checks["trade_permission_is_allowed"],
        checks["has_valid_scenario"],
    ])

    overall = pre_checks_pass and (no_config_pass if at_cfg is None else True)

    return {
        "pre_checks": pre_checks_pass,
        "strict_checks": no_config_pass,
        "overall_pass": overall,
        "detail": checks,
    }


# ═══════════════════════════════════════════════════════════════════════════
# MAIN DIAGNOSTIC
# ═══════════════════════════════════════════════════════════════════════════

def diagnose_eurusd():
    symbol = "EURUSD"

    print("=" * 70)
    print(f"  DIAGNOSTIC: Signal Pipeline Trace for {symbol}")
    print("=" * 70)

    # ── Step 0 ──
    print("\n── Step 0: MT5 Connection ──")
    ok, msg = step0_mt5_connection()
    print(f"  Status: {'OK' if ok else 'FAIL'}")
    print(f"  Detail: {msg}")
    if not ok:
        print("\n  >>> CANNOT CONTINUE: MT5 not connected <<<")
        return

    # ── Step 1 ──
    print(f"\n── Step 1: Load Market Data for {symbol} ──")
    data = step1_load_data(symbol)
    if "error" in data:
        print(f"  ERROR: {data['error']}")
        return
    print(f"  Broker symbol: {data['broker_symbol']}")
    for tf in ["D1", "H4", "H1", "M15"]:
        info = data.get(f"{tf}_last", {})
        if "error" in info:
            print(f"  {tf}: ERROR - {info['error']}")
        else:
            print(f"  {tf}: {info['count']} candles, last={info['time']}, close={info['close']}")
    tick = data.get("tick", {})
    if "error" not in tick:
        print(f"  TICK: bid={tick['bid']}, ask={tick['ask']}, spread={tick['spread']}")

    d1 = data["candles"].get("D1", [])
    h4 = data["candles"].get("H4", [])
    h1 = data["candles"].get("H1", [])
    m15 = data["candles"].get("M15", [])

    # Validation
    if len(d1) < 60:
        print(f"\n  >>> FAIL: D1 candles insufficient ({len(d1)} < 60) <<<")
        return
    if len(h4) < 60:
        print(f"\n  >>> FAIL: H4 candles insufficient ({len(h4)} < 60) <<<")
        return
    if len(h1) < 30:
        print(f"\n  >>> FAIL: H1 candles insufficient ({len(h1)} < 30) <<<")
        return

    m15_available = len(m15) >= 10
    print(f"\n  M15 candles: {len(m15)} (need ≥10 for entry confirmation)")
    print(f"  M15 available for entry: {'YES' if m15_available else 'NO — THIS BLOCKS ENTRY CONFIRMATION'}")

    dq = data["data_quality"]
    spread_price = float(dq.get("spread_price", 0) or 0)
    spread_status = dq.get("spread_status", "unknown")
    news_in_3h = bool(dq.get("news_in_3h", False))
    high_impact_30m = bool(dq.get("high_impact_event_within_30m", False))
    print(f"  Spread: {spread_price}, status={spread_status}")
    print(f"  News in 3h: {news_in_3h}")
    print(f"  High impact within 30m: {high_impact_30m}")

    # ── Step 2 ──
    print(f"\n── Step 2: Technical Snapshot ──")
    tech_summary, technical, market_regime = step2_technical(d1, h4, h1)
    for k, v in tech_summary.items():
        if k not in ("supports", "resistances"):
            print(f"  {k}: {v}")
    print(f"  Supports (top 5):")
    for s in tech_summary.get("supports", []):
        print(f"    level={s['level']}, tests={s['test_count']}")
    print(f"  Resistances (top 5):")
    for r in tech_summary.get("resistances", []):
        print(f"    level={r['level']}, tests={r['test_count']}")

    # ── Step 3 ──
    print(f"\n── Step 3: SMC Context ──")
    smc_summary, smc = step3_smc(d1, h4, h1)
    for k, v in smc_summary.items():
        print(f"  {k}: {v}")

    # ── Risk Score ──
    from core.signal_engine import calc_risk_condition
    risk_score = calc_risk_condition(
        technical["atr_h4"] or technical["atr_d1"] or 0.0,
        technical["atr_avg_14d"] or technical["atr_h4"] or technical["atr_d1"] or 0.0,
        news_in_3h,
        spread_status,
    )
    print(f"\n  Risk condition score: {risk_score}/15")

    # ── Step 4 ──
    print(f"\n── Step 4: Score Scenarios ──")
    macro_alignment = {"buy": 15, "sell": 15}  # neutral fallback
    macro_confidence = 1.0
    corr_adj_buy = 0.0
    corr_adj_sell = 0.0

    buy_summary, buy_full = step4_score("buy", technical, smc, risk_score, macro_alignment, macro_confidence, market_regime, corr_adj_buy, macro_alignment)
    sell_summary, sell_full = step4_score("sell", technical, smc, risk_score, macro_alignment, macro_confidence, market_regime, corr_adj_sell, macro_alignment)

    print(f"  BUY  score={buy_summary['signal_score']}/100 (T={buy_summary['trend_alignment']} M={buy_summary['momentum_alignment']} L={buy_summary['location_quality']} S={buy_summary['smc_quality']} R={buy_summary['risk_condition']} Ma={buy_summary['macro_alignment']})")
    print(f"       rating={buy_summary['rating']}, macro_status={buy_summary['macro_status']}")
    print(f"       smc_reason={buy_summary['smc_reason']}")
    print(f"       reason_codes={buy_summary['reason_codes']}, penalty_codes={buy_summary['penalty_codes']}")
    if buy_summary['smc_score_cap']:
        print(f"       ⚠️  SMC score cap: {buy_summary['smc_score_cap']}")

    print(f"  SELL score={sell_summary['signal_score']}/100 (T={sell_summary['trend_alignment']} M={sell_summary['momentum_alignment']} L={sell_summary['location_quality']} S={sell_summary['smc_quality']} R={sell_summary['risk_condition']} Ma={sell_summary['macro_alignment']})")
    print(f"       rating={sell_summary['rating']}, macro_status={sell_summary['macro_status']}")
    print(f"       smc_reason={sell_summary['smc_reason']}")
    print(f"       reason_codes={sell_summary['reason_codes']}, penalty_codes={sell_summary['penalty_codes']}")
    if sell_summary['smc_score_cap']:
        print(f"       ⚠️  SMC score cap: {sell_summary['smc_score_cap']}")

    # ── Determine best side ──
    from core.signal_engine import calculate_direction_bias
    direction_bias = calculate_direction_bias(buy_full, sell_full, min_gap=10)
    best_side = direction_bias["best_side"]
    best_score = int(max(direction_bias["buy_score"], direction_bias["sell_score"]))
    score_gap = direction_bias["score_gap"]
    is_clear = direction_bias["is_clear_bias"]

    if best_side == "neutral":
        # fallback to raw comparison
        if direction_bias["buy_score"] > direction_bias["sell_score"]:
            best_side = "buy"
            best_score = int(direction_bias["buy_score"])
        elif direction_bias["sell_score"] > direction_bias["buy_score"]:
            best_side = "sell"
            best_score = int(direction_bias["sell_score"])

    print(f"\n  Direction bias: BUY={direction_bias['buy_score']} vs SELL={direction_bias['sell_score']}")
    print(f"  Best side: {best_side.upper()}, Best score: {best_score}/100")
    print(f"  Score gap: {score_gap} (min 10), Clear bias: {'YES' if is_clear else 'NO'}")

    # ── Step 5 ──
    print(f"\n── Step 5: Build Trade Plan ──")
    from core.smc_context import get_preferred_zone
    from core.risk_engine import AnalysisInput

    request = AnalysisInput(
        symbol=symbol,
        broker_symbol=data["broker_symbol"],
        account_balance=10000.0,
        risk_percent=2.0,
        contract_size_override=100000.0,
    )

    price = technical["price"]
    atr = technical["atr_h4"] or technical["atr_d1"] or 0.0
    print(f"  Current price: {price}, ATR: {atr}")

    # Check both sides
    for side in ("buy", "sell"):
        pz = get_preferred_zone(smc, side, price=price)
        plan_summary, plan = step5_trade_plan(
            side, request, technical, smc, h1, m15,
            spread_price, market_regime, pz,
            is_backtest=False,
        )
        print(f"\n  --- {side.upper()} ---")
        if plan is None:
            print(f"    >>> build_trade_plan returned None <<<")
            print(f"    Meaning: No valid support/resistance zone found on correct side of price")
            continue

        print(f"    Entry zone: {plan_summary['entry_zone']}")
        print(f"    Entry status: {plan_summary['entry_status']}")
        print(f"    Trigger type: {plan_summary['trigger_type']}")
        print(f"    Confirmation score: {plan_summary['confirmation_score']} (need ≥70)")
        print(f"    Ready to trade: {plan_summary['ready_to_trade']}")
        print(f"    Price in zone: {plan_summary['price_in_entry_zone']}")
        print(f"    Invalid reason: {plan_summary['invalid_reason']}")
        print(f"    M15 available: {plan_summary['m15_available']}")
        print(f"    M15 quality: {plan_summary['m15_quality']}")
        print(f"    M15 confirmed: {plan_summary['m15_confirmed']}")
        if plan_summary['m15_structure']:
            print(f"    M15 structure: {plan_summary['m15_structure']}")
        if plan_summary['m15_displacement']:
            print(f"    M15 displacement: {plan_summary['m15_displacement']}")
        if plan_summary['entry_ladder']:
            el = plan_summary['entry_ladder']
            print(f"    Entry ladder: sub_zone={el.get('sub_zone')}, depth={el.get('depth_pct')}, size_mult={el.get('size_multiplier')}")
        if plan_summary['internal_structure']:
            ist = plan_summary['internal_structure']
            print(f"    Internal structure: passed={ist.get('passed')}, reason={ist.get('reason')}")
        print(f"    SL: {plan_summary['stop_loss']}, TP: {plan_summary['take_profit']}")
        print(f"    R:R: {plan_summary['risk_reward']}, Expected RR: {plan_summary['expected_effective_rr']}")
        print(f"    Reason codes: {plan_summary['reason_codes']}")
        print(f"    Warning codes: {plan_summary['warning_codes']}")
        print(f"    Block codes: {plan_summary['block_codes']}")

    # ── Step 6 ──
    print(f"\n── Step 6: Trade Permission ──")
    perm_summary, trade_permission = step6_permission(data["data_quality"], risk_score, best_score)
    print(f"  Status: {perm_summary['status']}")
    print(f"  Reason: {perm_summary['reason']}")
    print(f"  Min score: {perm_summary['min_score']}")

    # ── Step 7 ──
    print(f"\n── Step 7: Trade Gates ──")
    # Build gate context
    best_plan = None
    best_entry_status = None
    for side in ("buy", "sell"):
        if side == best_side:
            pz = get_preferred_zone(smc, side, price=price)
            _, plan = step5_trade_plan(side, request, technical, smc, h1, m15, spread_price, market_regime, pz)
            if plan:
                best_plan = plan
                best_entry_status = plan.get("entry_status")
            break

    m15_q = best_plan.get("m15_quality") if best_plan else None
    eff_rr = best_plan.get("expected_effective_rr") if best_plan else None
    nominal_rr = best_plan.get("risk_reward") if best_plan else None

    gate_context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": spread_status,
        "data_quality_warning": bool(dq.get("warning")),
        "high_impact_event_within_30m": high_impact_30m,
        "m15_quality": m15_q,
        "expected_effective_rr": eff_rr,
        "risk_reward": nominal_rr,
        "min_expected_effective_rr": 1.3,
        "zone_broken": best_plan.get("entry_status") == "invalidated" if best_plan else False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
        "score_gap": score_gap,
        "min_buy_sell_score_gap": 10,
        "journal_feedback": {},
    }

    gate_summary, gate_result = step7_gates(gate_context)
    print(f"  Allowed: {gate_summary['allowed']}")
    print(f"  Decision cap: {gate_summary['decision_cap']}")
    print(f"  Block codes: {gate_summary['block_codes']}")
    print(f"  Warning codes: {gate_summary['warning_codes']}")
    for r in gate_summary['reasons']:
        print(f"  Reason: {r}")

    # ── Step 8 ──
    print(f"\n── Step 8: Decision Engine ──")
    thresholds = {"ready": 65, "watch": 60, "wait": 55, "min_score_gap": 10}
    dec_summary, decision_result = step8_decision(
        best_score, gate_result, best_entry_status,
        score_gap, trade_permission, thresholds,
    )
    print(f"  Decision: {dec_summary['decision']}")
    print(f"  Legacy action: {dec_summary['legacy_action']}")
    print(f"  Final score: {dec_summary['final_score']}")
    print(f"  Allowed: {dec_summary['allowed']}")
    print(f"  Reason: {dec_summary['reason']}")
    print(f"  Decision cap: {dec_summary['decision_cap']}")
    print(f"  Score breakdown: {dec_summary['score_breakdown']}")
    print(f"  Reason codes: {dec_summary['reason_codes']}")
    print(f"  Warning codes: {dec_summary['warning_codes']}")
    print(f"  Block codes: {dec_summary['block_codes']}")

    # ── Step 9 ──
    print(f"\n── Step 9: Scanner Row ──")
    # Build full analysis result
    mock_result = {
        "symbol": symbol,
        "decision_summary": {
            "best_side": best_side,
            "best_score": best_score,
            "score_gap": score_gap,
            "is_clear_bias": is_clear,
        },
        "trade_permission": trade_permission,
        "scenario_scores": {"buy": buy_full, "sell": sell_full},
        "scenarios": [best_plan] if best_plan else [],
        "decision_engine": decision_result,
        "technical": technical,
        "market_regime": market_regime,
        "trade_gate": gate_result,
        "journal_feedback": {},
        "direction_bias": direction_bias,
        "final_score": best_score,
        "data_quality": {"broker_symbol": data["broker_symbol"]},
    }
    if best_plan:
        best_plan["type"] = best_side

    row_summary, scanner_row = step9_scanner_row(mock_result)
    print(f"  Symbol: {row_summary['symbol']}")
    print(f"  Scanner action: {row_summary['scanner_action']}")
    print(f"  Scanner group: {row_summary['scanner_group']}")
    print(f"  Scanner decision: {row_summary['scanner_decision']}")
    print(f"  Legacy action: {row_summary['legacy_action']}")
    print(f"  Trade permission: {row_summary['trade_permission']}")
    print(f"  Best side: {row_summary['best_side']}")
    print(f"  Best score: {row_summary['best_score']}")
    print(f"  Final score: {row_summary['final_score']}")
    print(f"  Opportunity score: {row_summary['opportunity_score']}")
    print(f"  Display action: {row_summary['display_action']}")
    print(f"  Entry status: {row_summary['entry_status']}")
    print(f"  Price vs zone: {row_summary['price_vs_zone']}")
    print(f"  M15 quality: {row_summary['m15_quality']}")
    print(f"  Expected RR: {row_summary['expected_effective_rr']}")
    print(f"  Short reason: {row_summary['short_reason']}")

    # ── Step 10 ──
    print(f"\n── Step 10: Scanner Filter Check ──")
    filter_result = step10_filter_check(scanner_row, at_cfg=None)
    print(f"  Pre-checks pass: {filter_result['pre_checks']}")
    print(f"  Strict checks pass: {filter_result['strict_checks']}")
    print(f"  OVERALL: {'PASS — would show in table' if filter_result['overall_pass'] else 'FAIL — WOULD BE MARKED AS BLOCKED'}")
    for check_name, check_val in filter_result['detail'].items():
        status = "✅" if check_val else "❌"
        print(f"    {status} {check_name}: {check_val}")

    # ── FINAL DIAGNOSIS ──
    print("\n" + "=" * 70)
    print("  FINAL DIAGNOSIS")
    print("=" * 70)

    failure_points = []

    if not m15_available:
        failure_points.append("M15 data not available (< 10 candles) → entry_status will NEVER be 'confirmed_entry' → decision will NEVER be 'READY_TO_TRADE' → scanner_action will NEVER be 'ready' → WILL NOT SHOW AS READY SIGNAL")

    if best_plan is None:
        failure_points.append("NO valid trade plan found → no entry zone → no signal possible")

    if best_plan and best_plan.get("entry_status") != "confirmed_entry":
        failure_points.append(f"Entry status = '{best_plan.get('entry_status')}' (NOT 'confirmed_entry') → decision engine outputs {best_entry_status} → legacy_action = '{decision_result.get('legacy_action')}' → scanner_action = '{scanner_row.get('scanner_action')}' → NOT 'ready'")

    if gate_result and not gate_result.get("allowed"):
        failure_points.append(f"Trade gate BLOCKED: {gate_result.get('reasons')}")

    if decision_result.get("decision") != "READY_TO_TRADE":
        failure_points.append(f"Decision is '{decision_result.get('decision')}' not 'READY_TO_TRADE'. Reason: {decision_result.get('reason')}")

    if not filter_result["overall_pass"]:
        failure_points.append("Scanner filter _apply_scanner_filters() would mark this row as 'blocked'. The row still appears in the table but in the 'blocked' group, not as a tradeable signal.")

    if not failure_points:
        failure_points.append("ALL CHECKS PASSED — signal should appear in table. If it does NOT appear, check:\n  - UI table model refresh (set_rows was called?)\n  - Symbol not in selected scan symbols\n  - Symbol not in Market Watch\n  - Proxy/sort filter model hiding the row")

    for i, fp in enumerate(failure_points, 1):
        print(f"\n  [{i}] {fp}")

    print("\n" + "=" * 70)
    print("  SUMMARY TABLE")
    print("=" * 70)
    print(f"  {'Check':<45} {'Result':<20} {'Required':<20}")
    print(f"  {'-'*45} {'-'*20} {'-'*20}")
    print(f"  {'D1 candles':<45} {f'{len(d1)} candles':<20} {'≥ 60':<20}")
    print(f"  {'H4 candles':<45} {f'{len(h4)} candles':<20} {'≥ 60':<20}")
    print(f"  {'H1 candles':<45} {f'{len(h1)} candles':<20} {'≥ 30':<20}")
    print(f"  {'M15 candles':<45} {f'{len(m15)} candles':<20} {'≥ 10':<20}")
    print(f"  {'Spread status':<45} {spread_status:<20} {'normal':<20}")
    print(f"  {'News in 3h':<45} {str(news_in_3h):<20} {'False':<20}")
    print(f"  {'High impact 30m':<45} {str(high_impact_30m):<20} {'False':<20}")
    buy_sc = buy_summary.get("signal_score", "?")
    sell_sc = sell_summary.get("signal_score", "?")
    print(f"  {'BUY score':<45} {str(buy_sc) + '/100':<20} {'≥ 50':<20}")
    print(f"  {'SELL score':<45} {str(sell_sc) + '/100':<20} {'≥ 50':<20}")
    print(f"  {'Best score':<45} {f'{best_score}/100':<20} {'≥ 65 (ready)':<20}")
    print(f"  {'Score gap':<45} {f'{score_gap}':<20} {'≥ 10':<20}")
    print(f"  {'Trade plan exists':<45} {str(best_plan is not None):<20} {'True':<20}")
    if best_plan:
        print(f"  {'Entry status':<45} {str(best_plan.get('entry_status')):<20} {'confirmed_entry':<20}")
        print(f"  {'Price in zone':<45} {str(best_plan.get('price_in_entry_zone')):<20} {'True':<20}")
        print(f"  {'H1 trigger':<45} {str(best_plan.get('trigger_type')):<20} {'!= none':<20}")
        conf_score = best_plan.get('confirmation_score')
        print(f"  {'Confirmation score':<45} {str(conf_score) + '/100':<20} {'≥ 70':<20}")
        print(f"  {'M15 quality':<45} {str(best_plan.get('m15_quality')):<20} {'strict/loose':<20}")
    print(f"  {'Trade permission':<45} {trade_permission.get('status', '?'):<20} {'allowed':<20}")
    print(f"  {'Gate allowed':<45} {str(gate_result.get('allowed')):<20} {'True':<20}")
    print(f"  {'Decision':<45} {str(decision_result.get('decision')):<20} {'READY_TO_TRADE':<20}")
    print(f"  {'Scanner action':<45} {str(scanner_row.get('scanner_action')):<20} {'ready':<20}")
    print(f"  {'Scanner group':<45} {str(scanner_row.get('scanner_group')):<20} {'ready_now':<20}")
    print(f"  {'Filter passes':<45} {str(filter_result['overall_pass']):<20} {'True':<20}")


if __name__ == "__main__":
    diagnose_eurusd()
