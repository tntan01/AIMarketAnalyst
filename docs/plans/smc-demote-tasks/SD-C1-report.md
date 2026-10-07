# SD-C1 report — Lấy lịch sử MT5 và lập danh sách cutoff

Task: SD-C1 — Lấy lịch sử nến MT5 và lập danh sách cutoff cho corpus SMC demote
Commit code: `3d9d4a5` (5 file: `.gitignore`, `scripts/smc_demote_corpus.py`,
`tests/test_smc_demote_corpus.py`, `reports/scanner/smc_demote/corpus_manifest.json`,
`reports/scanner/smc_demote/cutoffs.json`)

## Đã làm

- Thêm `scripts/smc_demote_corpus.py` với 3 lệnh `fetch` / `plan` / `verify`;
  dùng lại `_candle_payload`, `_candle_from_payload`, `_digest`, `_live_min_rr`
  của `scripts/smc_real_snapshots.py`, luôn lọc nến đóng bằng
  `closed_candles_at_cutoff`.
- `fetch`: đọc lịch sử D1/H4/H1/M15 một lần qua `MT5Service`, đóng băng mỗi
  symbol vào `reports/scanner/smc_demote/data/<symbol>.json.gz` (ghi atomic),
  ghi `corpus_manifest.json` (hash sha256 từng file, số nến + first/last mỗi TF,
  `min_rr`).
- `plan`: lập cutoff 1/ngày, giờ xoay vòng 04/12/20 UTC, bỏ ngày không có nến,
  thiếu lịch sử, thiếu tail; ghi `cutoffs.json` + `summary`.
- `verify`: kiểm lại toàn bộ cutoff bằng `windows_at` (prefix không đóng sau
  cutoff, tail H1=48, tail M15>0, prefix đủ `WINDOW_BARS`, hash khớp manifest)
  mà không gọi MT5, không gọi `now()`.
- Thêm hàm dùng chung `load_symbol_data` / `windows_at` cho SD-C2 import.
- Thêm `reports/scanner/smc_demote/data/` vào `.gitignore`.
- Thêm `tests/test_smc_demote_corpus.py` (3 test, nến tổng hợp, không cần MT5).

## Kiểm tra đã chạy

```text
python -X utf8 scripts/smc_demote_corpus.py fetch
```
→ `fetch: 31/31 symbols ok in 12.8s` (min_rr=2.0, loaded). Chi tiết trong bảng dưới.

```text
python -X utf8 scripts/smc_demote_corpus.py plan
plan: 2010 cutoffs
  by_hour: {'4': 660, '12': 690, '20': 660}
  by_month: {'2026-07': 595, '2026-08': 661, '2026-09': 690, '2026-10': 64}
  rejected: {'market_closed': 780, 'insufficient_history': 0, 'insufficient_tail': 93}
```

```text
python -X utf8 scripts/smc_demote_corpus.py verify
verify: 2010 cutoffs, 0 problems
```

```text
python -X utf8 -m pytest tests/test_smc_demote_corpus.py -q
...                                                                      [100%]
3 passed in 0.52s
```

```text
git status --short --untracked-files=all
 M .gitignore
?? reports/scanner/smc_demote/corpus_manifest.json
?? reports/scanner/smc_demote/cutoffs.json
?? scripts/smc_demote_corpus.py
?? tests/test_smc_demote_corpus.py
```
→ không file nào trong `reports/scanner/smc_demote/data/` xuất hiện.

Thời gian `fetch`: **12.8 s**. Dung lượng `data/`: **31 file, 7.29 MB**.

## Bảng symbol

`min_rr = 2.0` (`min_rr_status = loaded`). Số nến là số nến đã đóng tại thời
điểm fetch (`2026-10-07T06:44:42Z`).

| Symbol | Broker | Status | D1 | H4 | H1 | M15 | Cutoffs |
|---|---|---|---:|---:|---:|---:|---:|
| AUD/CAD | AUDCADm | ok | 856 | 1762 | 3777 | 8252 | 64 |
| AUD/CHF | AUDCHFm | ok | 856 | 1762 | 3777 | 8251 | 64 |
| AUD/JPY | AUDJPYm | ok | 856 | 1762 | 3777 | 8253 | 64 |
| AUD/NZD | AUDNZDm | ok | 856 | 1762 | 3777 | 8246 | 64 |
| AUD/USD | AUDUSDm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| BTC/USD | BTCUSDm | ok | 999 | 2399 | 5279 | 11519 | 90 |
| CAD/CHF | CADCHFm | ok | 856 | 1762 | 3777 | 8250 | 64 |
| CAD/JPY | CADJPYm | ok | 856 | 1762 | 3777 | 8252 | 64 |
| CHF/JPY | CHFJPYm | ok | 856 | 1762 | 3775 | 8234 | 64 |
| EUR/AUD | EURAUDm | ok | 856 | 1762 | 3777 | 8248 | 64 |
| EUR/CAD | EURCADm | ok | 856 | 1762 | 3777 | 8252 | 64 |
| EUR/CHF | EURCHFm | ok | 856 | 1762 | 3777 | 8254 | 64 |
| EUR/GBP | EURGBPm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| EUR/JPY | EURJPYm | ok | 856 | 1762 | 3777 | 8250 | 64 |
| EUR/NZD | EURNZDm | ok | 856 | 1762 | 3777 | 8252 | 64 |
| EUR/USD | EURUSDm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| GBP/AUD | GBPAUDm | ok | 856 | 1762 | 3777 | 8251 | 64 |
| GBP/CAD | GBPCADm | ok | 856 | 1762 | 3777 | 8235 | 64 |
| GBP/CHF | GBPCHFm | ok | 856 | 1762 | 3777 | 8252 | 64 |
| GBP/JPY | GBPJPYm | ok | 856 | 1762 | 3777 | 8249 | 64 |
| GBP/NZD | GBPNZDm | ok | 856 | 1762 | 3777 | 8228 | 64 |
| GBP/USD | GBPUSDm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| NZD/CAD | NZDCADm | ok | 856 | 1762 | 3777 | 8247 | 64 |
| NZD/CHF | NZDCHFm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| NZD/JPY | NZDJPYm | ok | 856 | 1762 | 3777 | 8247 | 64 |
| NZD/USD | NZDUSDm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| USD/CAD | USDCADm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| USD/CHF | USDCHFm | ok | 856 | 1762 | 3777 | 8255 | 64 |
| USD/JPY | USDJPYm | ok | 856 | 1762 | 3777 | 8254 | 64 |
| XAG/USD | XAGUSDm | ok | 852 | 1752 | 3584 | 7869 | 64 |
| XAU/USD | XAUUSDm | ok | 852 | 1752 | 3584 | 7869 | 64 |

Tổng cutoff: **2010** (trong khoảng mục tiêu 1.500–2.300).

## Symbol bị loại và lý do

Không có. Cả 31/31 symbol trong `SUPPORTED_SYMBOLS` resolve được broker symbol
và tải đủ lịch sử ở cả 4 timeframe (`status = ok`).

## Cutoff bị bỏ theo từng lý do

| Lý do | Số cutoff |
|---|---:|
| `market_closed` (không có nến H1 trong `[cutoff − 4h, cutoff)`) | 780 |
| `insufficient_history` (prefix thiếu `WINDOW_BARS`) | 0 |
| `insufficient_tail` (tail H1 < 48) | 93 |

`market_closed` là các ngày cuối tuần/ngày nghỉ (31 symbol × ~26 ngày ngoài
lịch giao dịch; BTC/USD giao dịch cuối tuần nên nhiều cutoff hơn: 90). 93 cutoff
`insufficient_tail` là ~3 ngày cuối kỳ mỗi symbol (05–07/10) chưa đủ 48 nến H1
tương lai tại thời điểm fetch.

Phân bố cutoff: theo giờ 04:00/12:00/20:00 UTC = 660/690/660; theo tháng
2026-07/08/09/10 = 595/661/690/64.

## Thay đổi hành vi/expected

Không có. Task chỉ thêm script tool + dữ liệu nghiên cứu, không sửa runtime
Scanner, không sửa file trong `core/`, `services/`, `controllers/`, `ui/`,
`config/`, `scripts/smc_real_snapshots.py`, `reports/scanner/smc_real_snapshots/`.

## Câu hỏi cho TL / điểm mơ hồ

- `market_closed` và `insufficient_tail` được đếm độc lập cho từng lý do bỏ
  (một cutoff có thể tăng nhiều bộ đếm). Trong dữ liệu này hai lý do không trùng
  nhau vì cutoff cuối tuần vẫn có ≥48 nến H1 *sau* cutoff (nến của phiên kế
  tiếp), nên chỉ bị loại bởi `market_closed`. Nếu TL muốn chỉ đếm cutoff theo
  lý do đầu tiên (hay đếm số cutoff bị loại thay vì số lượt lý do), báo để sửa.

## Rủi ro còn lại

- Dữ liệu đóng băng tại `2026-10-07T06:44Z`; chạy lại `fetch` về sau sẽ đổi
  `fetched_at`, hash file và số cutoff (các ngày mới). Manifest + hash đủ để
  kiểm chứng tái lập, nhưng SD-C2 nên dùng đúng bộ file đã commit ở task này.
- `windows_at` lọc lại `closed_candles_at_cutoff` trên toàn bộ chuỗi mỗi cutoff;
  `plan`/`verify` chạy vài chục giây trên 2010 cutoff — chấp nhận được, nhưng
  SD-C2 (chạy Scanner mỗi cutoff) cần cân nhắc cache.
