"""Diagnostic: test build_trade_plan with SMC preferred zone to reproduce RR=1:3.0"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.risk_engine import AnalysisInput, build_trade_plan
from core.smc_context import build_smc_context, get_preferred_zone
from core.technical_context import build_technical_snapshot


def _trending_candles(n, start_price=1.0800, step=0.0005, volatility=0.0010,
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
        candles.append(Candle(
            time=t, open=round(open_price,5), high=round(high_price,5),
            low=round(low_price,5), close=round(close_price,5), volume=1000.0))
        price = close_price
        t += timedelta(minutes=bar_minutes)
    return candles


end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
d1 = _trending_candles(120, start_price=1.0500, step=0.00025, bar_minutes=1440,
                       start_time=end - timedelta(days=120))
h4 = _trending_candles(360, start_price=d1[0].open, step=0.00012, bar_minutes=240,
                       start_time=d1[0].time)
h1 = _trending_candles(480, start_price=h4[0].open, step=0.00006, bar_minutes=60,
                       start_time=h4[0].time)

technical = build_technical_snapshot(d1, h4, h1)
smc = build_smc_context(d1, h4, h1)
price = technical["price"]
atr = technical["atr_h4"] or technical["atr_d1"] or 0.0

print(f"Price: {price}, ATR: {atr}")
print(f"H4 supply_zones: {len(smc['H4'].get('supply_zones', []))}")
print(f"H4 demand_zones: {len(smc['H4'].get('demand_zones', []))}")
print(f"H4 fvg: {len(smc['H4'].get('fvg', []))}")
print(f"H4 order_blocks: {len(smc['H4'].get('order_blocks', []))}")

# Check preferred zone
pz_buy = get_preferred_zone(smc, "buy", price=price)
pz_sell = get_preferred_zone(smc, "sell", price=price)
print(f"\nPreferred zone (buy): {pz_buy}")
print(f"Preferred zone (sell): {pz_sell}")

request = AnalysisInput(
    symbol="EUR/USD", broker_symbol="EURUSDm",
    account_balance=10_000.0, risk_percent=2.0,
    contract_size_override=100_000.0,
)

market_regime = {"primary": "trend_up"}

# Test with preferred zone
for side in ("buy", "sell"):
    pz = get_preferred_zone(smc, side, price=price)
    print(f"\n=== {side.upper()} ===")
    plan = build_trade_plan(
        side, request, technical, smc, h1,
        m15_candles=None,
        spread_price=16,
        market_regime=market_regime,
        preferred_zone=pz,
        is_backtest=False,
    )
    if plan:
        print(f"  RR: {plan.get('risk_reward')}")
        print(f"  Eff RR: {plan.get('expected_effective_rr')}")
        print(f"  Entry zone: {plan.get('entry_zone')}")
        print(f"  SL: {plan.get('stop_loss')}")
        print(f"  TP: {plan.get('take_profit')}")
        print(f"  Entry status: {plan.get('entry_status')}")
        print(f"  Zone source: {plan.get('entry_zone_source')}")
        print(f"  Zone score: {plan.get('entry_zone_score')}")
    else:
        print("  NO PLAN (returned None)")
