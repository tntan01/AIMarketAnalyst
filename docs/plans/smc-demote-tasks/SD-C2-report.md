# SD-C2 report — Replay corpus và gắn nhãn outcome

Task: SD-C2 — Replay corpus và gắn nhãn outcome
Commit code: `f6b4fcf` (5 file: `scripts/smc_demote_replay.py`,
`tests/test_smc_demote_replay.py`, `reports/scanner/smc_demote/replay_parity_c2.json`,
`reports/scanner/smc_demote/replay_trial.json`, `reports/scanner/smc_demote/replay_summary.json`)

## Đã làm

- Thêm `scripts/smc_demote_replay.py` với 3 lệnh `parity` / `run` / `summary`.
- `live_analysis_at` / `analyze_cutoff`: cắt cửa sổ bằng `windows_at` của SD-C1,
  chạy `derive_live_analysis` đúng như `_parity._live`, đọc plan bằng
  `plans_from_canonical_selection`, gắn nhãn bằng `label_side` (chỉ dùng tail).
- `label_side`: fwd 8h/24h theo ATR H1, TP/SL theo plan (STOP_FIRST, bỏ TP ở nến
  khớp), MFE/MAE theo R; fail-closed (`atr_h1_unavailable`, `tail_before_cutoff`).
- `run`: chạy song song `ProcessPoolExecutor`, cache dữ liệu theo symbol trong
  từng process, ghi tiếp được (resume theo `ROWS_PATH`), bắt mọi lỗi từng cutoff,
  `--redo`, `--trial`, đo `elapsed_s`/`peak_rss_mb`.
- `summary`: tổng hợp rows/lỗi/regime/`smc_state`/`tp_sl` theo side.
- Thêm `tests/test_smc_demote_replay.py` (8 test, nến tổng hợp, không MT5).

## Kiểm tra đã chạy

```text
python -X utf8 scripts/smc_demote_corpus.py verify
verify: 2010 cutoffs, 0 problems
```

```text
python -X utf8 -m pytest tests/test_smc_demote_replay.py tests/test_smc_demote_corpus.py -q
...........                                                              [100%]
11 passed in 0.60s
```

```text
python -X utf8 scripts/smc_demote_replay.py parity
parity: 58 rows, 0 mismatches
report -> D:\Projects\AIMarketAnalyst\reports\scanner\smc_demote\replay_parity_c2.json
```

```text
python -X utf8 scripts/smc_demote_replay.py run --symbols EUR/USD --from 2026-08-01 --to 2026-08-31 --workers 1 --trial
run: 21 snapshots, workers=1
run: done 21, errors 0, total 22.8s
trial -> ...\replay_trial.json
```

```text
python -X utf8 scripts/smc_demote_replay.py run --workers 8
run: 1989 snapshots, workers=8
...
run: done 1989, errors 13, total 800.2s
```

```text
python -X utf8 scripts/smc_demote_replay.py run --workers 8   # lần 2
run: 13 snapshots (0 new, 13 retry), workers=8
run: done 13, errors 13, total 5.6s
```

Lần chạy thứ hai **không chạy lại snapshot thành công nào** (0 new); 13 cutoff
đang lỗi được thử lại đúng như §3.5 ("lỗi cũ không bị bỏ qua").

```text
python -X utf8 scripts/smc_demote_replay.py summary
summary: cutoffs=2010 rows=1997 errors=13 missing=0
  error_rate=0.0065 error_types={'ValueError': 13}
  regime={'ranging': 130, 'trending_down': 632, 'trending_up': 1235}
  buy: smc_state={'data_unavailable': 105, 'evaluated': 649, 'out_of_strategy': 232, 'watch_zone': 1011}
  buy: tp_sl={'None': 1348, 'not_filled': 327, 'sl_first': 192, 'tp_first': 42, 'unresolved': 88}
  sell: smc_state={'data_unavailable': 148, 'evaluated': 677, 'out_of_strategy': 337, 'watch_zone': 835}
  sell: tp_sl={'None': 1320, 'not_filled': 300, 'sl_first': 206, 'tp_first': 54, 'unresolved': 117}
```

```text
git status --short --untracked-files=all
?? reports/scanner/smc_demote/replay_parity_c2.json
?? reports/scanner/smc_demote/replay_summary.json
?? reports/scanner/smc_demote/replay_trial.json
?? scripts/smc_demote_replay.py
?? tests/test_smc_demote_replay.py
```
→ không file nào trong `reports/scanner/smc_demote/data/` xuất hiện.

## Kết quả `parity`

- **58 rows, 0 mismatches.** So 1 (fingerprint 2 side × 7 field) và So 2 (field
  row đọc từ `canonical_smc`) đều khớp cho mọi row.
- `frozen_vs_corpus`: **compared = 33, fully_matched = 33, mismatches = []**.
  33 row cũ có symbol với file đóng băng đủ 500/500/500/100 nến tại `as_of`;
  5 row `broker_symbol_only` (BWPUSDm/SOLUSDm/DOGEUSDm/ADAUSDm) và các row quá
  khứ chưa đủ cửa sổ đóng băng không so được. Mọi prefix so được khớp hoàn toàn
  (time/open/high/low/close).
- Không so với `reports/scanner/smc_real_snapshots/replay_parity.json` (đã lỗi
  thời theo yêu cầu §3.4).

## Chạy thử, chọn N, tổng thời gian

`replay_trial.json` (1 worker, EUR/USD tháng 8, 21 snapshot):

| Chỉ số | Giá trị |
|---|---:|
| `seconds_per_snapshot_mean` | 1.056 |
| `seconds_per_snapshot_p95` | 1.103 |
| `peak_rss_mb_max` | 57.1 |
| `total_elapsed_s` | 22.85 |
| ước tính 2010 snapshot, 1 worker | 2 122 s |
| ước tính 2010 snapshot, 4 worker | 530 s |
| ước tính 2010 snapshot, 8 worker | 265 s |

**N = 8** (≤ 12; máy dev 16 core). Lý do: ước tính ~4,4 phút, để dư ~2× core dư
cho I/O/GC; RAM ~57 MB × 8 process ≈ 460 MB, an toàn. Chạy cả lô 1 worker sẽ
~35 phút nên không dùng.

**Tổng thời gian cả lô thật:** `run --workers 8` xử lý 1989 snapshot còn lại
trong **800,2 s** (~13,3 phút, ~2,49 snapshot/s); lần thử 21 snapshot trước đó
22,8 s.

## `summary`

| Chỉ số | Giá trị |
|---|---:|
| `cutoffs_total` | 2010 |
| `rows` | 1997 |
| `errors` | 13 |
| `error_rate` | 0,0065 (0,65 %) |
| `missing` | 0 |

Lỗi theo `error_type`: `ValueError` = 13. Tất cả 13 lỗi cùng một thông điệp:
`SMC M15 expires_at must follow confirmed_at` (lỗi bên trong pipeline SMC, không
sửa core theo §5). Ví dụ 3 cutoff lỗi:

- `CHF/JPY@2026-07-27T04:00:00+00:00` — `ValueError: SMC M15 expires_at must follow confirmed_at`
- `EUR/GBP@2026-08-03T12:00:00+00:00` — `ValueError: SMC M15 expires_at must follow confirmed_at`
- `XAU/USD@2026-08-03T12:00:00+00:00` — `ValueError: SMC M15 expires_at must follow confirmed_at`

Regime (`rows`):

| regime | rows |
|---|---:|
| trending_up | 1235 |
| trending_down | 632 |
| ranging | 130 |

`smc_state` theo side:

| state | buy | sell |
|---|---:|---:|
| evaluated | 649 | 677 |
| watch_zone | 1011 | 835 |
| out_of_strategy | 232 | 337 |
| data_unavailable | 105 | 148 |

`tp_sl` theo side (gồm cả side không có plan → `None`):

| tp_sl | buy | sell |
|---|---:|---:|
| None (không có plan) | 1348 | 1320 |
| not_filled | 327 | 300 |
| sl_first | 192 | 206 |
| tp_first | 42 | 54 |
| unresolved | 88 | 117 |

`rows_sha256` = `sha256:0c41acbcece0ce3c61776986c37cf3975f31fd494db369f7cb4b68a03990f5e2`.
`rule_versions` = `smc-v2` (scorer), `smc-selection-v1`, `smc-snapshot-v1`, …

## Giới hạn (theo yêu cầu ghi rõ)

- **Giá khớp luôn là `E`**: entry là lệnh limit tại mép zone; khi nến đã vượt E
  lúc mở, vẫn coi khớp tại E (không mô phỏng gap/slippage).
- **Bỏ qua TP ở nến khớp (`j == i`)**: không biết TP đến trước hay sau khi khớp,
  nên nến khớp chỉ xét SL.
- **Không tính spread/chi phí** (Q9).
- `mfe_r`/`mae_r` chỉ tính từ nến khớp đến nến kết thúc (hoặc hết tail); TP/SL
  cùng nến → SL (STOP_FIRST).
- 13/2010 cutoff lỗi pipeline SMC (0,65 %), nằm trong ngưỡng 2 %; không sửa
  core, không lọc bớt.

## Thay đổi hành vi/expected

Không có. Task chỉ thêm tool nghiên cứu + output, không sửa runtime Scanner và
không sửa file trong `core/`, `services/`, `controllers/`, `ui/`, `config/`,
`scripts/smc_real_snapshots.py`, `scripts/smc_replay_parity.py`,
`scripts/smc_demote_corpus.py`, `reports/scanner/smc_real_snapshots/`,
`reports/scanner/smc_demote/cutoffs.json`, `corpus_manifest.json`.

## Câu hỏi cho TL / điểm mơ hồ

- `error_rate` được định nghĩa = `errors / cutoffs_total` (0,65 %). Nếu TL muốn
  `errors / (rows + errors)` thì kết quả vẫn 0,65 % (13 / 2010 = 13 / 2010).
- 13 lỗi `SMC M15 expires_at must follow confirmed_at` là lỗi pipeline SMC trên
  dữ liệu thật (không phải lỗi harness): nên để SD-C3 bỏ qua (đã có trong
  `ERRORS_PATH`) hay TL muốn mở task điều tra riêng?

## Rủi ro còn lại

- `windows_at` lọc lại nến đóng cho cả 4 TF ở mỗi cutoff; `run` chấp nhận được
  nhưng SD-C3 đọc lại toàn bộ `replay_rows.jsonl` (≈ 7,6 MB) mỗi lần.
- `replay_rows.jsonl` / `replay_errors.jsonl` nằm trong `data/` (đã ignore) —
  không commit, nên SD-C3 phải chạy trên cùng máy/cùng bộ file này.
