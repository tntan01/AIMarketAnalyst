# Copy file này sang Windows, chạy từ thư mục dự án:
# python D:\Projects\AIMarketAnalyst\ai-market-analyst-v2.0\test_p0_parallel.py

import time, sys
sys.path.insert(0, '.')

print("=" * 70)
print("TEST P0 — load_primary_timeframes song song")
print("=" * 70)

from services.mt5_service import MT5Service
mt5 = MT5Service()

status = mt5.connection_status()
print(f"\nMT5: terminal={status.terminal_connected}, logged_in={status.logged_in}")

bars_by_tf = {"D1": 100, "H4": 100, "H1": 100, "M15": 200}
broker = mt5.resolve_symbol("EUR/USD", mt5.available_symbols(market_watch_only=True))
print(f"Symbol: {broker}\n")

# Tuần tự
print("--- Tuần tự ---")
t0 = time.time()
seq = {}
for tf, bars in bars_by_tf.items():
    seq[tf] = mt5.load_ohlcv(broker, tf, bars)
    print(f"  {tf}: {len(seq[tf])} candles")
ts = time.time() - t0
print(f"  Time: {ts:.3f}s\n")

# Song song
print("--- Song song ---")
t0 = time.time()
par = mt5.load_primary_timeframes(broker, bars_by_tf)
for tf in sorted(par):
    print(f"  {tf}: {len(par[tf])} candles")
tp = time.time() - t0
print(f"  Time: {tp:.3f}s\n")

# So sánh
speedup = ts / tp if tp > 0 else 999
print(f"Tuần tự: {ts:.3f}s | Song song: {tp:.3f}s | Speedup: {speedup:.1f}x")

all_ok = True
for tf in bars_by_tf:
    if seq[tf][-1].close != par[tf][-1].close:
        print(f"  FAIL: {tf} close khác")
        all_ok = False
if all_ok:
    print("  Kết quả khớp")

est = (ts - tp) * 29
print(f"\nƯớc tính scanner 29 symbols tiết kiệm: {est:.1f}s")
print("=" * 70)
print("PASS" if all_ok else "FAIL")
print("=" * 70)

input("\nEnter để thoát...")
