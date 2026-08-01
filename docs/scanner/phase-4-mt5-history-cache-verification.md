# Phase 4 — Xác minh MT5 rolling history cache

Ngày xác minh: 2026-08-01.

## Phạm vi đã thực hiện

- Flag rollout `scanner_mt5_history_cache`, mặc định `False`; tắt flag giữ
  nguyên full-history path cũ.
- Cold path tải đủ `D1/H4/H1/M15 = 500/500/500/100` bars và lưu cache memory.
- Warm path tải tail 3 bars cho đủ bốn timeframe, merge theo UTC timestamp,
  replace forming bar, append bar mới và trim đúng count cấu hình.
- Cache key đầy đủ là `server + account fingerprint (broker/login) +
  broker_symbol + timeframe`.
- Gap, timestamp/validation lỗi hoặc identity/config đổi đều dùng full reload.
  Lỗi MT5 tail không trả cache cũ như dữ liệu fresh và không mutate cache.
- Mọi SDK operation của cached path vẫn ở trong
  `_serialized_mt5_operation`; batch cached chạy tuần tự, không tạo MT5
  service mới theo symbol.

## Characterization benchmark — 28 symbols

Đo phần history-fetch của `MT5Service` trên fake MT5 deterministic: 2 warm-up
và 12 mẫu đo cho mỗi path. Fake mô phỏng chi phí transport tỷ lệ với payload
(`10 µs/bar`); đây là benchmark regression có thể lặp lại, **không phải** số
P50/P95 từ MT5 terminal/broker thật.

| Chỉ số mỗi scan | Cold/full | Warm/tail |
|---|---:|---:|
| `copy_rates_from_pos()` calls | 112 | 112 |
| Full-history calls | 112 | 0 |
| Tail calls | 0 | 112 |
| Payload requested/received | 44.800 bars | 336 bars |
| MT5 history-fetch P50 | 594,58 ms | 132,33 ms |
| MT5 history-fetch P95 | 605,66 ms | 134,06 ms |

Warm path giảm payload 99,25% và giảm P50 mock 77,7%. Tổng số SDK calls giữ
nguyên là hành vi chủ đích để refresh forming bar của D1/H4/H1/M15 ở mọi scan.
Benchmark MT5 thật vẫn cần thực hiện riêng theo checklist rollout trước khi
đưa số latency này vào quyết định production.

## Kiểm tra bắt buộc

- Tiêu chí mục 22 #8: **PASS** — cache hit dùng `warm_tail`; gap/validation
  lỗi quay về full reload.
- MT5 lock còn nguyên, không có parallel call trái phép: **PASS** — cached
  entrypoint vẫn có `_serialized_mt5_operation`; concurrent test xác nhận
  `max_active == 1`.
- Full-vs-cache parity: **PASS** — cùng frozen MT5 snapshot, so sánh exact
  candles/input và toàn bộ `analyze_symbol()` output trừ timestamp wall-clock.
- Gap detection có test case: **PASS** — gap trả `full_reload_gap`, với 4 tail
  calls cộng 4 full fallback calls.
- Cache identity đầy đủ (`symbol + timeframe + broker`): **PASS** — key có
  server, broker/login fingerprint, broker symbol và timeframe; metadata cũ
  thiếu broker/login fail-safe về `None` identity/full path thay vì lỗi scan.

## Test evidence

```text
python -m pytest tests/test_candle_history_cache.py \
  tests/test_mt5_history_cache.py \
  tests/test_mt5_operation_serialization.py \
  tests/test_mt5_connection_characterization.py \
  tests/test_mt5_service.py \
  tests/test_scanner_phase0_settings.py \
  tests/test_scanner_performance.py -q
59 passed

python -m pytest tests/ -x -q
2080 passed, 12 skipped, 17 xfailed
```

Phase 5 không nằm trong thay đổi này và chưa được bắt đầu.
