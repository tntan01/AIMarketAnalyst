# SD-C3 — Phân tích corpus: thành phần, chọn side, AUC SMC

> **Giao bởi:** Tech Lead · **Ngày:** 07/10/2026 · **Người làm:** Coder
> **Kế hoạch tổng:** [`../smc-demote-task-plan.md`](../smc-demote-task-plan.md)
> (chỉ cần đọc §0.2 "Quy tắc bắt buộc" và §2 Q4/Q5/Q6). File này là nguồn
> chính cho task; nếu thấy mâu thuẫn với plan → **dừng và hỏi**, không tự chọn.

## 1. Mục tiêu

Đọc kết quả replay của SD-C2 (`replay_rows.jsonl`, 1997 row) và tính các chỉ số
để TL/Owner quyết định tại CP1: (1) bỏ SMC khỏi TechnicalScore có làm chọn
side tệ đi không; (2) SMC `quality_score` có phân biệt TP-trước/SL-trước không.
Task này **chỉ tính số**, không viết kết luận (đó là SD-C4), không chạy lại
replay hàng loạt, không tối ưu trọng số.

## 2. Chuẩn bị

1. Làm trên `main`, `git status` sạch.
2. Đọc trước (không sửa):
   - `scripts/smc_demote_replay.py`: `ROWS_PATH`, `ERRORS_PATH`, `SUMMARY_PATH`,
     `read_jsonl`, `live_analysis_at`, `MANIFEST_PATH`; cấu trúc một row (mục
     3.2 của [`SD-C2.md`](SD-C2.md)).
   - `core/technical_signal_scorer.py`: `TECHNICAL_COMPONENT_RAW_MAX`,
     `TECHNICAL_REGIME_WEIGHTS`, `score_technical_signal`,
     `_round_half_up_once`.
3. Máy dev có `numpy`, **không có** `scipy` → tự viết AUC/Spearman/bootstrap
   theo mục 3.3 (không cài thêm package).

## 3. Việc cần làm

### 3.1 File mới `scripts/smc_demote_analyze.py`

Thêm `PROJECT_ROOT` và `PROJECT_ROOT / "scripts"` vào `sys.path` như các
script SD trước. Import, không copy:

```python
from smc_demote_replay import (ERRORS_PATH, MANIFEST_PATH, ROWS_PATH, SUMMARY_PATH,
                               live_analysis_at, read_jsonl)
from smc_demote_corpus import DATA_DIR, load_symbol_data
from core.technical_signal_scorer import (TECHNICAL_COMPONENT_RAW_MAX,
                                          TECHNICAL_REGIME_WEIGHTS, score_technical_signal)
```

Hằng số:

```python
OUTPUT_DIR = PROJECT_ROOT / "reports" / "scanner" / "smc_demote"
ANALYSIS_JSON = OUTPUT_DIR / "analysis.json"     # commit
ANALYSIS_MD = OUTPUT_DIR / "analysis.md"         # commit
SCORER_CHECK_JSON = OUTPUT_DIR / "scorer_check.json"  # commit
SEED = 20261007
BOOTSTRAP_N = 2000
MIN_SCORE_GAP = 5          # config/scanner_order_policy.json threshold.min_score_gap
Q4_DIFF_FLOOR = -0.05      # Q4 điều kiện (1)
Q4_AUC_FLOOR = 0.55        # Q4 điều kiện (2)
Q4_MIN_RESOLVED = 200
NO_SMC_WEIGHTS = {         # Q5 — Trend/Momentum/Location, tổng 100
    "trending_up":   {"trend": 50, "momentum": 25, "location": 25},
    "trending_down": {"trend": 50, "momentum": 25, "location": 25},
    "ranging":       {"trend": 17, "momentum": 17, "location": 66},
    "volatile":      {"trend": 29, "momentum": 14, "location": 57},
    "unknown":       {"trend": 34, "momentum": 33, "location": 33},
}
```

Hai lệnh con: `check-scorer`, `analyze`.

**Đầu vào bắt buộc khớp:** `analyze` tính sha256 bytes của `ROWS_PATH`, so với
`rows_sha256` trong `SUMMARY_PATH` (`reports/scanner/smc_demote/replay_summary.json`).
Khác → in `BLOCKED: replay_rows.jsonl khác replay_summary.json` và exit 2.
Ghi `rows_sha256` vào `ANALYSIS_JSON`.

### 3.2 Hai biến thể TechnicalScore (tính từ raw trong row)

Cho một side với `trend`, `momentum`, `location`, `smc_raw`, `regime` của row:

- **(a) `current`** — 4 thành phần, đúng công thức scorer:
  `total = Σ Fraction(clamp(raw_i, 0, max_i) * W[regime][i], max_i)` với
  `max = TECHNICAL_COMPONENT_RAW_MAX`, `W = TECHNICAL_REGIME_WEIGHTS`; clamp
  total vào [0, 100]; làm tròn **một lần** bằng round-half-up (viết lại đúng
  như `_round_half_up_once`: `q, r = divmod(num, den); q + int(2*r >= den)`).
  `smc_raw is None` → side **không chấm được** (fail-closed như scorer thật).
- **(b) `no_smc`** — 3 thành phần trend/momentum/location, cùng công thức,
  trọng số `NO_SMC_WEIGHTS`. Không cần SMC → luôn chấm được.

**Chọn side của một row (pair):** cả hai side chấm được →
`buy_score >= sell_score` → `"buy"`, ngược lại `"sell"` (hòa → BUY, như
`core/scanner_composition.py`). Một side không chấm được → `selected = None`.
`gap = abs(buy_score - sell_score)`; `gap_ok = gap >= MIN_SCORE_GAP`.

### 3.3 Công cụ thống kê (tự viết, numpy được dùng)

- **Rank trung bình** cho giá trị bằng nhau (ties).
- **AUC** (Mann–Whitney): `score` liên tục, `label` 0/1;
  `AUC = (sum_rank_pos - n_pos*(n_pos+1)/2) / (n_pos*n_neg)` dùng rank trung
  bình trên toàn mẫu. `n_pos == 0` hoặc `n_neg == 0` → `None`.
- **Spearman** = Pearson của hai dãy rank trung bình. Ít hơn 3 điểm hoặc
  phương sai 0 → `None`.
- **Bootstrap theo cụm — cụm = NGÀY UTC của cutoff** (`cutoff[:10]`; ~90 cụm).
  Mỗi vòng: rút có hoàn lại đúng số cụm, gom mọi row của cụm đã rút (cụm rút
  2 lần thì row vào 2 lần), tính lại thống kê. `BOOTSTRAP_N` vòng,
  `rng = numpy.random.default_rng(SEED)` tạo **một lần** cho mỗi thống kê theo
  thứ tự cố định trong code. CI95 = percentile 2.5 / 97.5
  (`numpy.percentile`, mặc định linear). Vòng nào thống kê `None` → bỏ vòng
  đó, ghi số vòng hợp lệ.
  (Plan ghi "cụm (symbol, ngày)"; mỗi symbol chỉ có 1 cutoff/ngày nên cụm đó
  trùng từng row — TL đã chốt dùng cụm theo ngày để bắt tương quan giữa các
  cặp cùng ngày.)

### 3.4 Lệnh `check-scorer` (chạy trước `analyze`)

Chứng minh công thức (a) ở 3.2 trùng scorer thật. Chọn 50 row bằng
`random.Random(SEED).sample(rows_có_cả_hai_smc_raw_khác_None, 50)`. Với mỗi row:
`data = load_symbol_data(DATA_DIR / f"{symbol bỏ '/'}.json.gz")`;
`analysis, _, _ = live_analysis_at(data, cutoff, min_rr của manifest)`; với mỗi
side gọi

```python
score_technical_signal(side, trend_raw=raws.trend, momentum_raw=raws.momentum,
                       location_raw=raws.location,
                       canonical_smc=analysis["canonical_smc"],
                       regime=analysis["regime"]).technical_signal_score
```

(`raws = analysis["raws"].per_side[side]`) và so với điểm (a) tính từ row đã
lưu. Ghi `SCORER_CHECK_JSON` `{checked, mismatches: [...]}`; in
`check-scorer: 50 rows, N mismatches`; exit 1 nếu N > 0.

### 3.5 Lệnh `analyze` — các khối kết quả (khóa trong `ANALYSIS_JSON`)

Row lỗi của SD-C2 (`ERRORS_PATH`) không có trong `ROWS_PATH` → chỉ ghi số
lượng (`inputs.errors`) và danh sách `error_type`/`message` đếm theo loại.

**`inputs`**: rows, errors, số cụm ngày, `rows_sha256`, seed, bootstrap_n.

**`regime_distribution`** (plan SD-C3 mục 6): số và tỷ lệ row theo regime
(`trending_up`, `trending_down`, `ranging`, `volatile`, `unknown` — regime
không xuất hiện ghi 0); bảng chéo regime × symbol; regime × tháng (`cutoff[:7]`).

**`raw_distribution`** (mục 1): với mỗi thành phần `trend`, `momentum`,
`location`, `smc_raw` và mỗi regime (+ `all`): `n`, `n_null`, mean, median,
min, max, và đếm theo từng giá trị raw (`{value: count}`). Tính trên side
(mỗi row góp 2 side).

**`component_discrimination`** (mục 2): trên tất cả side (bỏ side có raw
`None` của thành phần đó), cho mỗi thành phần:
- `spearman_fwd_8h`, `spearman_fwd_24h` (raw vs `labels.fwd_8h_atr` /
  `fwd_24h_atr`);
- `auc_fwd_24h_pos`: AUC của raw với nhãn `fwd_24h_atr > 0`;
- `hit_rate_by_bucket`: tỷ lệ `fwd_24h_atr > 0` và mean `fwd_24h_atr` theo
  bucket cố định:
  `trend` 0–8 / 9–16 / 17–25 · `momentum` 0–6 / 7–13 / 14–20 ·
  `location` 0 / 1–8 / 9–16 / 17–25 · `smc_raw` 0 / 1–5 / 6–7 / 8 / 9–15;
  mỗi bucket ghi `n`.
- Lặp lại cả khối cho từng regime (`by_regime`); regime có < 30 side ghi
  `"few_samples": true` (vẫn tính).
- Thêm `quality_score` (SMC, thang 0–100) như một thành phần, chỉ spearman/AUC.

**`side_selection`** (mục 3 — **Q4 điều kiện (1)**):
- Đếm: row cả hai biến thể chọn được side (`both`), chỉ (b) chọn được
  (`only_no_smc` — do SMC `data_unavailable`), không biến thể nào.
- Trên tập `both`: số row đổi side; với mỗi biến thể: mean `fwd_24h_atr` và
  `fwd_8h_atr` của side được chọn, hit-rate (`> 0`).
- **Chỉ số Q4(1)**: `diff = mean(fwd_24h(no_smc chọn) − fwd_24h(current chọn))`
  trên tập `both` (row không đổi side góp 0). Ước lượng điểm + CI95 bootstrap
  cụm ngày. Ghi `q4_condition_1 = {"diff": ..., "ci95": [lo, hi],
  "pass": lo >= Q4_DIFF_FLOOR}`. Ghi cùng chỉ số cho `fwd_8h` (mô tả, không
  dùng cho Q4).
- **Áp min score-gap:** với mỗi biến thể độc lập: số row `gap_ok`, mean
  `fwd_24h` và hit-rate của side chọn trong các row `gap_ok`. Thêm số row
  `gap_ok` ở biến thể này nhưng không ở biến thể kia (hai chiều).
- Trên tập `only_no_smc`: số row, mean `fwd_24h` của side (b) chọn.
- Danh sách mọi row đổi side: symbol, cutoff, regime, side (a)/(b), điểm
  buy/sell mỗi biến thể, `smc_raw` buy/sell, `fwd_24h_atr` của side (a) và (b).
- Tách theo regime (`by_regime`): `both`, đổi side, mean diff (không cần CI).
- Median `gap` mỗi biến thể trên tập `both`.

**`smc_tp_sl`** (mục 4 — **Q4 điều kiện (2)**):
- Đếm `labels.tp_sl` theo side và tổng (`tp_first`, `sl_first`,
  `unresolved`, `not_filled`, `plan_invalid`, `None`).
- Tập resolved = side có `tp_sl` ∈ {`tp_first`, `sl_first`}; nhãn 1 =
  `tp_first`. `n_resolved`, `n_tp`, `n_sl`.
- **Chỉ số Q4(2)**: AUC của `quality_score` trên tập resolved + CI95 bootstrap
  cụm ngày. `q4_condition_2 = {"n_resolved", "auc", "ci95",
  "pass": n_resolved >= Q4_MIN_RESOLVED and auc >= Q4_AUC_FLOOR and ci95[0] > 0.5,
  "insufficient_samples": n_resolved < Q4_MIN_RESOLVED}`.
- Mô tả thêm (không dùng cho Q4): AUC của `quality_raw`, `b`, `q`, `l`, `c`
  trên cùng tập; tỷ lệ `tp_first` theo bucket `quality_raw` (bucket như
  `smc_raw` ở trên); tỷ lệ `tp_first` theo `readiness_status`; mean `mfe_r`,
  `mae_r` theo nhãn.

**`q6_evidence`** (đầu vào để SD-C4 xác nhận Q6): áp ánh xạ Q6 cho mọi side —
`smc_state == "data_unavailable"` (hoặc `quality_raw is None`) → `None`;
`smc_state == "no_zone"` → `0`; còn lại → round-half-up(`quality_score`).
Ghi: đếm `None` / `0` / `>0`; phân phối (min, p25, median, p75, max) của giá
trị `>0`; đếm theo `smc_state`.

### 3.6 `ANALYSIS_MD`

Sinh tự động từ cùng dict (không viết tay số): bảng regime, bảng
`component_discrimination` (all), bảng `side_selection` (gồm dòng Q4(1)),
bảng `smc_tp_sl` (gồm dòng Q4(2)), bảng `q6_evidence`, danh sách row đổi side.
Số thực in 3 chữ số thập phân. Không viết nhận định/kết luận.

### 3.7 Tất định

`ANALYSIS_JSON` dùng `indent=2, sort_keys=True, ensure_ascii=False`; không ghi
thời gian chạy hay `now()` vào file. Chạy `analyze` hai lần phải cho file
giống hệt byte (so sha256).

### 3.8 Test `tests/test_smc_demote_analyze.py`

Số liệu tổng hợp, không đọc `data/`, không MT5:

1. AUC: `[1,2,3,4]` nhãn `[0,0,1,1]` → 1.0; nhãn `[1,1,0,0]` → 0.0; score
   bằng nhau hết → 0.5; chỉ một lớp → `None`.
2. Spearman với ties: ví dụ tính tay (≥ 5 điểm, có ít nhất một cặp bằng nhau).
3. Biến thể (a): một ví dụ trending (`trend=20, momentum=10, location=12,
   smc=8`) → tính tay `20/25*40 + 10/20*20 + 12/25*20 + 8/15*20 = 32 + 10 +
   9.6 + 10.666… = 62.266…` → **62**; `smc_raw=None` → không chấm được.
4. Biến thể (b) cùng raw, trending → `20/25*50 + 10/20*25 + 12/25*25 =
   40 + 12.5 + 12 = 64.5` → **65** (round-half-up, không phải 64).
5. Chọn side: điểm bằng nhau → `"buy"`; `gap < 5` → `gap_ok False`.
6. Bootstrap cụm: cùng seed hai lần → cùng CI; rút theo cụm (dữ liệu 2 cụm,
   mỗi cụm 3 row hằng số khác nhau → mọi mẫu bootstrap chỉ chứa bội số 3 row
   của từng cụm).

## 4. Lệnh nghiệm thu (chạy đủ, dán output thật vào report)

```powershell
python -X utf8 -m pytest tests/test_smc_demote_analyze.py tests/test_smc_demote_replay.py tests/test_smc_demote_corpus.py -q
python -X utf8 scripts/smc_demote_analyze.py check-scorer
python -X utf8 scripts/smc_demote_analyze.py analyze
Get-FileHash reports/scanner/smc_demote/analysis.json
python -X utf8 scripts/smc_demote_analyze.py analyze
Get-FileHash reports/scanner/smc_demote/analysis.json    # phải giống lần trước
git status --short     # data/ KHÔNG được xuất hiện
```

**Đạt khi:** test pass; `check-scorer` 0 mismatches (khác 0 → **dừng**, báo
TL, không chạy `analyze`); hai lần `analyze` cùng hash; có đủ các khối ở 3.5.

## 5. Không được làm

- Không sửa `core/`, `services/`, `controllers/`, `ui/`, `config/`, các script
  SD-C1/SD-C2, các file trong `reports/scanner/smc_demote/` do task trước tạo,
  `reports/scanner/smc_real_snapshots/`.
- Không chạy lại `smc_demote_replay.py run`/`fetch`; không gọi MT5.
- Không grid search / tối ưu / thử trọng số khác `NO_SMC_WEIGHTS` (Q5).
- Không loại bớt row để số đẹp hơn; không đổi bucket/ngưỡng Q4.
- Không viết kết luận A/B/giữ nguyên (SD-C4/CP1).
- Không bắt đầu SD-C4.

## 6. Commit và báo cáo

- Commit thẳng `main`:
  `feat(research): [SD-C3] phân tích corpus SMC demote`. Gồm
  `scripts/smc_demote_analyze.py`, `tests/test_smc_demote_analyze.py`,
  `analysis.json`, `analysis.md`, `scorer_check.json`. Không commit `data/`.
- Viết `docs/plans/smc-demote-tasks/SD-C3-report.md` theo mẫu §7 của plan (ghi
  hash commit code), commit riêng `docs(smc): [SD-C3] báo cáo`. Report gồm thêm:
  kết quả `check-scorer`; hai hash `analysis.json`; dòng Q4(1) và Q4(2) (số,
  CI, pass/fail) chép **nguyên** từ `analysis.json`; số row đổi side; bảng
  regime.
- Sau đó **dừng**, chờ TL review.

## Rework

_(TL ghi yêu cầu sửa ở đây nếu có.)_
