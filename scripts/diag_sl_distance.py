"""Diagnostic: scan all forex pairs and report SL distance after config change.
Handles real scenarios AND fallback scenarios.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config.constants import SUPPORTED_SYMBOLS
from core.risk_engine import AnalysisInput
from core.analysis_pipeline import AnalysisPipeline
from core.market_models import Candle
from datetime import datetime, timezone

FOREX = [s for s in SUPPORTED_SYMBOLS if s not in ("XAU/USD", "XAG/USD", "BTC/USD")]

def load(symbol, tf_name, count=300):
    import MetaTrader5 as mt5
    import numpy as np
    tf_map = {"D1": mt5.TIMEFRAME_D1, "H4": mt5.TIMEFRAME_H4, "H1": mt5.TIMEFRAME_H1, "M15": mt5.TIMEFRAME_M15}
    broker = symbol.replace("/", "")
    for suffix in ["", "m", "c"]:
        sym = broker + suffix
        try:
            mt5.symbol_select(sym, True)
        except Exception:
            pass
        rates = mt5.copy_rates_from_pos(sym, tf_map[tf_name], 0, count)
        if rates is not None and len(rates) > 0:
            out = []
            for r in rates:
                t = r["time"]
                if isinstance(t, (int, float, np.integer)):
                    t = datetime.fromtimestamp(int(t), tz=timezone.utc)
                out.append(Candle(time=t, open=float(r["open"]), high=float(r["high"]), low=float(r["low"]), close=float(r["close"]), volume=float(r["tick_volume"])))
            return out
    return []

def main():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        print("ERROR: Cannot connect to MT5")
        return

    header = f"{'Symbol':<10} {'Price':>10} {'ATR':>10} {'Side':>5} {'Entry':>10} {'SL':>10} {'Dist':>8} {'ATR%':>7} {'Guard':>8} {'RR':>7} {'Source':>10}"
    print(header)
    print("-" * len(header))

    real_pass, real_fail, fallback, no_scenario, no_data = [], [], [], [], []

    for symbol in FOREX:
        candles = {tf: load(symbol, tf) for tf in ["D1", "H4", "H1", "M15"]}
        if not candles["H4"] or len(candles["H4"]) < 50:
            no_data.append(symbol)
            continue

        req = AnalysisInput(symbol=symbol, broker_symbol=symbol.replace("/", ""), account_balance=10000.0, risk_percent=1.0)

        try:
            pipe = AnalysisPipeline()
            result = pipe.execute(req, candles, m15_candles=candles.get("M15"), is_backtest=False)
        except Exception as e:
            no_data.append(symbol)
            continue

        tech = result.get("technical", {})
        price = float(tech.get("price", 0) or 0)
        atr = float(tech.get("atr_h4") or tech.get("atr_d1") or 0)
        if price <= 0 or atr <= 0:
            no_data.append(symbol)
            continue

        scenarios = result.get("scenarios", [])
        if not scenarios:
            no_scenario.append(symbol)
            continue

        for sc in scenarios:
            side = sc.get("type", "?")
            if side not in ("buy", "sell"):
                continue

            zone_src = sc.get("entry_zone_source", "?")
            entry_zone = sc.get("entry_zone", [])
            sl = sc.get("stop_loss")
            tp_list = sc.get("take_profit", [])
            tp1 = tp_list[0] if tp_list else None
            sl_src = sc.get("sl_source", "?")

            # Compute entry from zone midpoint if entry_price is None
            ep = sc.get("entry_price")
            if ep is None and isinstance(entry_zone, list) and len(entry_zone) == 2:
                ep = (entry_zone[0] + entry_zone[1]) / 2

            if ep is None or sl is None:
                continue

            dist = abs(ep - sl)
            atr_pct = round(dist / atr * 100, 1)
            guard_pass = dist >= atr * 0.35 - 1e-10

            rr_str = "-"
            if tp1 and dist > 0:
                rr = abs(tp1 - ep) / dist
                rr_str = f"1:{rr:.1f}"

            flag = "PASS" if guard_pass else "FAIL"
            row = f"{symbol:<10} {price:>10.5f} {atr:>10.5f} {side:>5} {ep:>10.5f} {sl:>10.5f} {dist:>8.5f} {atr_pct:>6.1f}% {flag:>8} {rr_str:>7} {zone_src:>10}"
            print(row)

            if zone_src == "fallback":
                fallback.append(symbol)
            elif guard_pass:
                real_pass.append({"symbol": symbol, "side": side, "dist_pct": atr_pct, "dist": dist})
            else:
                real_fail.append({"symbol": symbol, "side": side, "dist_pct": atr_pct, "dist": dist})

    mt5.shutdown()

    rp, rf, fb = len(real_pass), len(real_fail), len(fallback)
    print(f"\n{'='*60}")
    print(f"GUARD: min_sl_distance_atr_mult = 0.35")
    print(f"  Real plans PASS (>= 0.35 ATR): {rp}")
    print(f"  Real plans FAIL (<  0.35 ATR): {rf}")
    print(f"  Fallback (ATR-based SL):       {len(set(fallback))}")
    print(f"  No scenario:                   {len(no_scenario)}")
    print(f"  No data:                       {len(no_data)}")

    if real_pass:
        ds = [r["dist_pct"] for r in real_pass]
        print(f"\n  Real plans distance: {min(ds):.1f}% - {max(ds):.1f}% ATR (avg {sum(ds)/len(ds):.1f}%)")
    if real_fail:
        print(f"\n  FAILED (would be rejected):")
        for r in sorted(real_fail, key=lambda x: x["dist_pct"]):
            print(f"    {r['symbol']} {r['side']}: {r['dist_pct']:.1f}% ATR")

if __name__ == "__main__":
    main()
