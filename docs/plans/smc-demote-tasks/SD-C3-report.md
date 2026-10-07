# SD-C3 report — Phân tích corpus: thành phần, chọn side, AUC SMC

Task: SD-C3 — Phân tích corpus
Commit code: `0b699ef` (5 file: `scripts/smc_demote_analyze.py`,
`tests/test_smc_demote_analyze.py`, `reports/scanner/smc_demote/analysis.json`,
`reports/scanner/smc_demote/analysis.md`, `reports/scanner/smc_demote/scorer_check.json`)

## Đã làm

- Thêm `scripts/smc_demote_analyze.py` (2 lệnh `check-scorer`, `analyze`).
- Công cụ thống kê tự viết (không scipy): rank trung bình, AUC Mann–Whitney,
  Spearman (Pearson trên rank), bootstrap theo cụm NGÀY (`cutoff[:10]`) với
  `numpy.random.default_rng(SEED)`.
- Hai biến thể TechnicalScore từ raw đã lưu: (a) `current` đúng công thức scorer
  (4 thành phần, `TECHNICAL_REGIME_WEIGHTS`, Fraction + round-half-up một lần,
  `smc_raw=None` → không chấm được); (b) `no_smc` 3 thành phần `NO_SMC_WEIGHTS`.
- `check-scorer`: 50 row ngẫu nhiên, so điểm (a) từ row với `score_technical_signal` thật.
- `analyze`: ghi đủ các khối `inputs`, `regime_distribution`, `raw_distribution`,
  `component_discrimination`, `side_selection`, `smc_tp_sl`, `q6_evidence`;
  sinh `analysis.md` tự động từ cùng dict.
- `analyze` kiểm sha256 `ROWS_PATH` khớp `rows_sha256` trong `replay_summary.json`
  trước khi tính (khác → `BLOCKED`, exit 2).
- Thêm `tests/test_smc_demote_analyze.py` (6 test).

## Kiểm tra đã chạy

```text
python -X utf8 -m pytest tests/test_smc_demote_analyze.py tests/test_smc_demote_replay.py tests/test_smc_demote_corpus.py -q
.................                                                        [100%]
17 passed in 0.72s
```

```text
python -X utf8 scripts/smc_demote_analyze.py check-scorer
check-scorer: 50 rows, 0 mismatches
report -> ...\scorer_check.json
```

```text
python -X utf8 scripts/smc_demote_analyze.py analyze
analyze: rows=1997 clusters=90
q4_condition_1={'diff': -0.0003830461752605566, 'ci95': [-0.09029027606769051, 0.08597674935793669], 'pass': False}
q4_condition_2={'n_resolved': 494, 'n_tp': 96, 'n_sl': 398, 'auc': 0.4669440954773869, 'ci95': [0.4069600236614648, 0.5273798299270344], 'pass': False, 'insufficient_samples': False}
```

Tất định `analysis.json` (hai lần `analyze` giống hệt byte):

```text
Get-FileHash reports/scanner/smc_demote/analysis.json -Algorithm SHA256
RUN1 3347FDD6295D368ECE4B27C48E7BDA13A4687B3AD75A0B86D44BBBACA2184AB6
RUN2 3347FDD6295D368ECE4B27C48E7BDA13A4687B3AD75A0B86D44BBBACA2184AB6
```

```text
git status --short --untracked-files=all
?? reports/scanner/smc_demote/analysis.json
?? reports/scanner/smc_demote/analysis.md
?? reports/scanner/smc_demote/scorer_check.json
?? scripts/smc_demote_analyze.py
?? tests/test_smc_demote_analyze.py
```
→ không file nào trong `reports/scanner/smc_demote/data/` xuất hiện.

## check-scorer

`scorer_check.json` = `{"checked": 100, "mismatches": []}` (50 row × 2 side).
Công thức (a) tính từ raw đã lưu trùng `score_technical_signal` thật trên mọi
side được kiểm. Không mismatch.

## Q4 — chép nguyên từ `analysis.json`

`q4_condition_1` (Q4 điều kiện 1 — chọn side):

```json
{"ci95": [-0.09029027606769051, 0.08597674935793669], "diff": -0.0003830461752605566, "pass": false}
```

`q4_condition_2` (Q4 điều kiện 2 — AUC SMC trên side có plan):

```json
{"auc": 0.4669440954773869, "ci95": [0.4069600236614648, 0.5273798299270344], "insufficient_samples": false, "n_resolved": 494, "n_sl": 398, "n_tp": 96, "pass": false}
```

Số row đổi side: **91** (`side_selection.counts.changed_side`).
`counts` = `{"both": 1793, "only_no_smc": 204, "neither": 0, "changed_side": 91}`.
`only_no_smc_mean_fwd_24h` = -0.24962896321040262.

(Điểm `diff` mô tả `fwd_8h`: `{"ci95": [-0.028623399307066696, 0.03879567271799188], "diff": 0.005247797253859528}`.)

## Bảng regime

`regime_distribution` (rows = 1997):

| regime | count | fraction |
|---|---:|---:|
| trending_up | 1235 | 0.618 |
| trending_down | 632 | 0.316 |
| ranging | 130 | 0.065 |
| volatile | 0 | 0.000 |
| unknown | 0 | 0.000 |

## Các khối khác (tóm tắt)

- `inputs` = rows 1997, errors 13, day_clusters 90, `rows_sha256` =
  `sha256:0c41acbcece0ce3c61776986c37cf3975f31fd494db369f7cb4b68a03990f5e2`,
  seed 20261007, bootstrap_n 2000.
- `component_discrimination.all` (n = 3994 side; `smc_raw`/`quality_score` n = 3741):

  | component | spearman_fwd_8h | spearman_fwd_24h | auc_fwd_24h_pos |
  |---|---:|---:|---:|
  | trend | 0.039 | 0.011 | 0.515 |
  | momentum | -0.040 | -0.001 | 0.500 |
  | location | 0.026 | -0.011 | 0.493 |
  | smc_raw | -0.023 | 0.009 | 0.503 |
  | quality_score | -0.023 | 0.008 | 0.502 |

- `side_selection`: median `gap` 22 (current) / 27 (no_smc); `gap_ok_count`
  1598 / 1650; `gap_ok_mean_fwd_24h` -0.075 / -0.100.
- `smc_tp_sl` (tổng theo side, gồm cả side không có plan):
  `tp_first` 96, `sl_first` 398, `unresolved` 205, `not_filled` 627,
  `plan_invalid` 0, `None` 2668; `n_resolved` 494.
- `q6_evidence`: None 253, `0` 569, `>0` 3172; `>0` min/p25/median/p75/max =
  18 / 45 / 52 / 59 / 89; `counts_by_state` = `data_unavailable` 253,
  `evaluated` 1326, `watch_zone` 1846, `out_of_strategy` 569.

## Thay đổi hành vi/expected

Không có. Task chỉ thêm tool phân tích + output, không sửa runtime Scanner và
không sửa `core/`, `services/`, `controllers/`, `ui/`, `config/`, các script
SD-C1/SD-C2, hay `reports/scanner/smc_real_snapshots/`.

## Câu hỏi cho TL / điểm mơ hồ

- Cụm bootstrap dùng NGÀY UTC của cutoff (`cutoff[:10]`, 90 cụm) như TL đã chốt
  ở §3.3.
- `raw_distribution` tính trên side: `n` = tổng số side trong nhóm, `n_null` =
  số side có raw `None`; mean/median/min/max/value_counts tính trên non-null.
- `error_rate` không nằm trong task này; 13 row lỗi SD-C2 chỉ được đếm trong
  `inputs.errors` / `inputs.error_types`.

## Rủi ro còn lại

- AUC SMC trên tập resolved chỉ 494 side (< 2000), CI95 rộng; kết luận thuộc
  SD-C4/CP1, không phải task này.
- `analysis.json` giá trị bootstrap phụ thuộc phiên bản `numpy` (cùng máy hai
  lần chạy giống hệt byte; máy/numpy khác có thể lệch nhỏ ở chữ số cuối).
