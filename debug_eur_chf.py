"""Debug script: analyze EURCHF and dump TP/SL/Entry details."""
import json, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Fix Windows encoding
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from services.mt5_service import MT5Service
from services.news_service import NewsService
from services.market_data_service import fetch_macro_correlation_context
from core.analysis_engine import analyze_symbol
from core.analysis_pipeline import AnalysisInput

mt5 = MT5Service()
if not mt5.connect():
    print("ERROR: Cannot connect to MT5.")
    sys.exit(1)
print("MT5 connected.")

# ---- Resolve EURCHF broker symbol ----
available = mt5.available_symbols()
broker_symbol = mt5.resolve_symbol("EUR/CHF", available)
if not broker_symbol:
    print("ERROR: EURCHF not found.")
    sys.exit(1)
print(f"Broker symbol: {broker_symbol}")

# ---- Fetch data (same as _fetch_one_symbol_mt5) ----
all_candles = mt5.load_primary_timeframes(broker_symbol, {"D1": 250, "H4": 250, "H1": 250, "M15": 200})
data_quality = mt5.symbol_data_quality("EUR/CHF", broker_symbol)
news_svc = NewsService()
news_flags = news_svc.data_quality_flags("EUR/CHF")
macro_context = news_flags.pop("macro_context", {"events": []})
data_quality.update(news_flags)
quote_to_usd = mt5.quote_to_usd_rate("CHF")
correlation = fetch_macro_correlation_context()

# ---- Run analysis ----
analysis_input = AnalysisInput(
    symbol="EUR/CHF", broker_symbol=broker_symbol,
    account_balance=10000, risk_percent=1.0, account_currency="USD",
    lot_step=0.01, minimum_lot=0.01, timezone_name="Asia/Ho_Chi_Minh",
)
macro_align = macro_context.get("macro_alignment_scores") if isinstance(macro_context, dict) else None
macro_conf = float(macro_context.get("macro_data_quality", 1.0)) if isinstance(macro_context, dict) else 1.0

result = analyze_symbol(
    analysis_input,
    {"D1": all_candles["D1"], "H4": all_candles["H4"], "H1": all_candles["H1"]},
    data_quality=data_quality,
    macro_alignment=macro_align if isinstance(macro_align, dict) else None,
    macro_confidence=macro_conf,
    m15_candles=all_candles["M15"],
    correlation_context=correlation,
    quote_to_usd_rate=quote_to_usd,
    closed_trades=[], open_trades=[],
)

# ---- Dump ----
tech = result.get("technical", {})
regime = result.get("market_regime", {})
price = tech.get("price", 0) or 0
atr = tech.get("atr_h4", 0) or tech.get("atr_d1", 0) or 0.001

print(f"\n{'='*70}")
print(f"EUR/CHF ANALYSIS  |  Price={price:.5f}  ATR_H4={atr:.6f}  Regime={regime.get('primary','?')}")
print(f"{'='*70}")

print(f"\nSupport zones:  {tech.get('support_zones', [])}")
print(f"Resistance:     {tech.get('resistance_zones', [])}")

smc = result.get("smc", {})
for tf in ["H4", "H1"]:
    s = smc.get(tf, {})
    print(f"\nSMC {tf}:  demand={len(s.get('demand_zones',[]))}z  supply={len(s.get('supply_zones',[]))}z  "
          f"swing_highs={len(s.get('swing_highs',[]))}  swing_lows={len(s.get('swing_lows',[]))}")

scenarios = result.get("scenarios", [])
print(f"\nSCENARIOS ({len(scenarios)}):")
print("-" * 70)

for sc in scenarios:
    side = sc.get("type", "?")
    ez = sc.get("entry_zone", [])
    sl = sc.get("stop_loss")
    tp = sc.get("take_profit", [])
    rr = sc.get("risk_reward", "?")
    eff_rr = sc.get("expected_effective_rr", "?")
    status = sc.get("entry_status", "?")
    cond = sc.get("condition", "")
    inval = sc.get("invalidation", "")
    sizing = sc.get("position_sizing", {})

    print(f"\n  {side.upper():6s} | Entry: [{ez[0]:.5f} - {ez[1]:.5f}]" if len(ez) >= 2 else f"\n  {side.upper()}")
    print(f"         |  SL: {sl:.5f}" if sl else "         |  SL: N/A")
    print(f"         |  TP: {[f'{t:.5f}' for t in tp]}" if tp else "         |  TP: N/A")
    print(f"         |  R:R {rr}  |  Eff.RR={eff_rr}  |  Status={status}")
    print(f"         |  Lot={sizing.get('suggested_lot','?')}  |  Condition={cond}")
    print(f"         |  Invalidation={inval}")

    if len(ez) >= 2 and sl and tp:
        entry_pt = ez[1] if side == "buy" else ez[0]
        sl_dist = entry_pt - sl if side == "buy" else sl - entry_pt
        tp1_dist = tp[0] - entry_pt if side == "buy" else entry_pt - tp[0]
        price_dist = entry_pt - price if price < entry_pt else price - entry_pt
        print(f"         |  Price->Entry={price_dist:.5f} ({price_dist/atr:.1f}xATR)  "
              f"Entry->SL={sl_dist:.5f} ({sl_dist/atr:.1f}xATR)  "
              f"Entry->TP1={tp1_dist:.5f} ({tp1_dist/atr:.1f}xATR)")

# Decision
dec = result.get("decision_engine", {})
perm = result.get("trade_permission", {})
print(f"\nDECISION: {dec.get('decision','?')}  |  Action: {dec.get('legacy_action','?')}  |  "
      f"Score: {result.get('final_score','?')}")
print(f"PERMISSION: {perm.get('status','?')}  |  Reason: {perm.get('reason','?')}")
print("=" * 70)

mt5.shutdown()
