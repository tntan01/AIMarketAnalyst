"""Diagnostic script: trace RR and chart payload issues.

Issue 1: All scanner results show RR = 1:3.0
Issue 2: Chart only shows Entry+ / Entry-, no SL/TP
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput, build_scenarios
from core.smc_context import build_smc_context
from core.technical_context import build_technical_snapshot
from core.chart_payload import build_full_chart_payload


# ---------------------------------------------------------------------------
# Generate realistic trending-up candles (simulating EURUSD)
# ---------------------------------------------------------------------------

def _trending_candles(n, *, start_price=1.0800, step=0.0005, volatility=0.0010,
                      start_time=None, bar_minutes=60):
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    price = start_price
    for i in range(n):
        body = step * (0.3 + 0.7 * (i % 5) / 5)
        wick = volatility * 0.4
        open_price = price
        close_price = price + body
        high_price = close_price + wick * (0.3 + 0.7 * (i % 3) / 3)
        low_price = open_price - wick * (0.2 + 0.8 * (i % 4) / 4)
        candles.append(
            Candle(
                time=t,
                open=round(open_price, 5),
                high=round(high_price, 5),
                low=round(low_price, 5),
                close=round(close_price, 5),
                volume=float(1000 + i * 10),
            )
        )
        price = close_price
        t += timedelta(minutes=bar_minutes)
    return candles


def _range_candles(n, *, center=1.0800, amplitude=0.0020, start_time=None, bar_minutes=60):
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = []
    price = center
    direction = 1
    for i in range(n):
        if abs(price - center) > amplitude * 0.9:
            direction *= -1
        step = amplitude * 0.15 * direction
        open_price = price
        close_price = price + step
        high_price = max(open_price, close_price) + amplitude * 0.1
        low_price = min(open_price, close_price) - amplitude * 0.1
        candles.append(
            Candle(
                time=t,
                open=round(open_price, 5),
                high=round(high_price, 5),
                low=round(low_price, 5),
                close=round(close_price, 5),
                volume=float(800 + i * 5),
            )
        )
        price = close_price
        t += timedelta(minutes=bar_minutes)
    return candles


def build_all_timeframes(*, regime="trending_up", base_price=1.0800):
    end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
    if regime == "trending_up":
        d1 = _trending_candles(120, start_price=base_price - 0.0300, step=0.00025, bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012, bar_minutes=240, start_time=d1[0].time)
        h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006, bar_minutes=60, start_time=h4[0].time)
    else:
        cen = base_price
        d1 = _range_candles(120, center=cen, amplitude=0.0050, bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _range_candles(360, center=cen, amplitude=0.0040, bar_minutes=240, start_time=d1[0].time)
        h1 = _range_candles(480, center=cen, amplitude=0.0030, bar_minutes=60, start_time=h4[0].time)
    m15 = _trending_candles(200, start_price=h1[0].open, step=0.00002, bar_minutes=15, start_time=h1[0].time)
    return {"D1": d1, "H4": h4, "H1": h1, "M15": m15}


def run_diagnostics(regime="trending_up"):
    print(f"\n{'='*80}")
    print(f"DIAGNOSTIC: regime={regime}")
    print(f"{'='*80}")

    candles = build_all_timeframes(regime=regime)
    request = AnalysisInput(
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        account_balance=10_000.0,
        risk_percent=2.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    # Run full pipeline
    result = analyze_symbol(
        request,
        {"D1": candles["D1"], "H4": candles["H4"], "H1": candles["H1"]},
        data_quality={
            "price_source": "MT5",
            "terminal_connected": True,
            "broker_logged_in": True,
            "display_symbol": "EUR/USD",
            "broker_symbol": "EURUSDm",
            "spread_points": 16,
            "spread_status": "normal",
            "warning": None,
            "news_in_3h": False,
            "high_impact_event_within_30m": False,
        },
        macro_alignment={"buy": 15, "sell": 15},
        macro_confidence=1.0,
        m15_candles=candles["M15"],
        is_backtest=False,
    )

    # --- Check 1: scenarios ---
    scenarios = result.get("scenarios", [])
    print(f"\n--- Scenarios ({len(scenarios)}) ---")
    for i, sc in enumerate(scenarios):
        sc_type = sc.get("type", "?")
        entry_status = sc.get("entry_status", "?")
        rr = sc.get("risk_reward", "?")
        eff_rr = sc.get("expected_effective_rr", "?")
        sl = sc.get("stop_loss", "?")
        tp = sc.get("take_profit", "?")
        ez = sc.get("entry_zone", "?")
        print(f"  [{i}] type={sc_type}, entry={entry_status}, RR={rr}, effRR={eff_rr}")
        print(f"       entry_zone={ez}, SL={sl}, TP={tp}")

    # --- Check 2: Chart payload ---
    payload = build_full_chart_payload("EUR/USD", result)
    print(f"\n--- Chart Payload ---")
    tp = payload.get("trade_plan", {})
    print(f"  trade_plan.side        = {tp.get('side')}")
    print(f"  trade_plan.entry_zone  = {tp.get('entry_zone')}")
    print(f"  trade_plan.stop_loss   = {tp.get('stop_loss')}")
    print(f"  trade_plan.take_profit = {tp.get('take_profit')}")
    print(f"  trade_plan.entry_status= {tp.get('entry_status')}")
    print(f"  levels                 = {json.dumps(payload.get('levels', []))}")
    print(f"  zones                  = {json.dumps(payload.get('zones', []))}")

    # --- Check 3: Entry evaluation details ---
    if scenarios:
        best = scenarios[0]
        print(f"\n--- Entry Details (scenarios[0]) ---")
        for key in ["entry_status", "trigger_type", "confirmation_score", "m15_quality",
                     "m15_available", "m15_checked", "m15_confirmed", "m15_score_multiplier",
                     "ready_to_trade", "price_in_entry_zone", "h1_confirmation",
                     "entry_ladder", "sub_zone"]:
            print(f"  {key} = {best.get(key, 'N/A')}")

    # --- Check 4: Market regime ---
    mr = result.get("market_regime", {})
    print(f"\n--- Market Regime ---")
    print(f"  primary = {mr.get('primary')}")

    # --- Check 5: Decision summary ---
    ds = result.get("decision_summary", {})
    print(f"\n--- Decision Summary ---")
    print(f"  best_side   = {ds.get('best_side')}")
    print(f"  best_score  = {ds.get('best_score')}")
    print(f"  action      = {ds.get('action')}")
    print(f"  score_gap   = {ds.get('score_gap')}")

    # --- Check 6: SMC context zones ---
    smc = result.get("smc", {})
    h4 = smc.get("H4", {})
    print(f"\n--- SMC H4 Zones ---")
    print(f"  supply_zones  = {len(h4.get('supply_zones', []))}")
    print(f"  demand_zones  = {len(h4.get('demand_zones', []))}")
    print(f"  order_blocks  = {len(h4.get('order_blocks', []))}")
    print(f"  fvg           = {len(h4.get('fvg', []))}")
    print(f"  displacement  = {h4.get('displacement')}")
    print(f"  bos           = {h4.get('bos')}")
    print(f"  choch         = {h4.get('choch')}")

    return result, payload


if __name__ == "__main__":
    # Test with trending regime
    result1, payload1 = run_diagnostics("trending_up")

    # Test with range regime
    result2, payload2 = run_diagnostics("range")
