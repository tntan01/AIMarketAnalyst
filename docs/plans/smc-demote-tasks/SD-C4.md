# SD-C4 — Báo cáo CP1 (sinh tự động từ kết quả phân tích)

> **Giao bởi:** Tech Lead · **Ngày:** 07/10/2026 · **Người làm:** Coder
> **Kế hoạch tổng:** [`../smc-demote-task-plan.md`](../smc-demote-task-plan.md)
> (chỉ cần đọc §0.2 và §2 Q4, Q6, Q9). File này là nguồn chính; mâu thuẫn với
> plan → **dừng và hỏi**.

## 1. Mục tiêu

Tạo `reports/scanner/smc_demote/report.md`: báo cáo cho checkpoint CP1, nơi
TL/Owner áp quy tắc Q4. Mọi con số trong báo cáo phải **sinh bằng script** từ
các file kết quả đã commit — không gõ tay số, không tính thêm thống kê mới,
không chạy lại replay/analyze. Báo cáo **không đưa khuyến nghị** ngoài việc
chép đúng kết quả cơ học của quy tắc Q4.

## 2. Đầu vào (chỉ đọc)

| File | Dùng cho |
|---|---|
| `reports/scanner/smc_demote/analysis.json` | gần như mọi số |
| `reports/scanner/smc_demote/replay_summary.json` | rows, errors, error_types |
| `reports/scanner/smc_demote/corpus_manifest.json` | `fetched_at`, `min_rr`, số symbol `ok` |
| `reports/scanner/smc_demote/cutoffs.json` | khối `summary` (by_hour, by_month, rejected) |
| `reports/scanner/smc_demote/scorer_check.json` | `checked`, số mismatch |

Script phải kiểm `analysis.json["inputs"]["rows_sha256"] ==
replay_summary.json["rows_sha256"]`; khác → in `BLOCKED: ...`, exit 2.

## 3. Việc cần làm

### 3.1 File mới `scripts/smc_demote_report.py`

Một lệnh (không subcommand): đọc 5 file trên, ghi `REPORT_MD =
OUTPUT_DIR / "report.md"`. Tất định: không ghi `now()`, chạy hai lần ra file
giống hệt byte. Số thực in **3 chữ số thập phân** (`f"{x:.3f}"`), tỷ lệ in
dạng `%` 1 chữ số (`f"{x*100:.1f}%"`), `None` in `—`. Văn bản cố định dưới
đây chép **nguyên văn** (được đổi chỗ xuống dòng cho đẹp, không đổi ý).

### 3.2 Cấu trúc `report.md` (đúng thứ tự, đúng tiêu đề)

```
# Báo cáo CP1 — SMC demote (Giai đoạn 1)
```

Dòng ngay dưới tiêu đề (nguyên văn):

> Báo cáo sinh tự động bởi `scripts/smc_demote_report.py` từ
> `analysis.json` (rows_sha256 `<giá trị>`). Không chứa khuyến nghị; quyết
> định thuộc TL/Owner tại CP1.

**`## 1. Kết quả quy tắc Q4`**

Bảng:

| Điều kiện | Chỉ số | Giá trị | CI95 | Ngưỡng | Kết quả |
|---|---|---:|---|---|---|
| (1) Chọn side | mean fwd 24h (ATR) side chọn bởi 3 thành phần − 4 thành phần, trên pair cả hai chọn được | `side_selection.q4_condition_1.diff` | `[lo, hi]` | cận dưới ≥ −0,05 | ĐẠT / KHÔNG ĐẠT (theo `pass`) |
| (2) SMC phân biệt TP/SL | AUC `quality_score`, n resolved = `n_resolved` (TP `n_tp` / SL `n_sl`) | `smc_tp_sl.q4_condition_2.auc` | `[lo, hi]` | AUC ≥ 0,55 và cận dưới > 0,5; n ≥ 200 | ĐẠT / KHÔNG ĐẠT / KHÔNG ĐỦ MẪU |

Sau bảng, một dòng "**Kết quả cơ học của quy tắc Q4:**" chọn đúng **một**
câu theo `pass` của hai điều kiện:

- (1) không đạt → `Không đạt điều kiện (1) → giữ nguyên TechnicalScore 4 thành phần; TL cân nhắc phương án B.`
- (1) đạt, (2) không đạt → `Đạt (1), không đạt (2) → chọn A; TL quyết định lại Q6.`
- cả hai đạt → `Đạt cả hai điều kiện → chọn A.`

Rồi đoạn **"Độ rộng khoảng tin cậy (1)"** — in ba số tính từ `q4_condition_1`:
`half_width = (hi − lo)/2`; `need = diff − (−0,05)` (khoảng cách từ ước lượng
điểm đến ngưỡng); nếu `need > 0`: `factor = (half_width / need)²` và in câu
nguyên văn
`Ước tính thô: nếu chênh lệch giữ nguyên, cần khoảng <factor:.1f> lần số pair hiện tại để cận dưới CI95 đạt −0,05 (giả định độ rộng CI tỷ lệ 1/√n).`;
nếu `need <= 0` in `Ước lượng điểm đã dưới ngưỡng −0,05.`

**`## 2. Dữ liệu`**

- Gạch đầu dòng: `fetched_at`; số symbol `ok` / tổng symbol trong manifest;
  `min_rr`; tổng cutoff (`cutoffs.json` summary total); cutoff theo giờ và
  theo tháng; số cutoff bị bỏ theo lý do; rows; errors và `error_types`; số
  cụm ngày (`inputs.day_clusters`); `bootstrap_n`, `seed`.
- `check-scorer`: `<checked> side, <n> mismatch`.
- Bảng phân bố regime (`regime_distribution.distribution`: regime, số row, tỷ lệ),
  đủ 5 regime kể cả 0.

**`## 3. Chọn side: 4 thành phần (hiện tại) vs 3 thành phần (Q5)`**

- Bảng đếm: `both`, `only_no_smc`, `neither`, `changed_side`.
- Bảng so sánh hai biến thể (cột `current`, `no_smc`), các dòng:
  `mean_fwd_24h`, `mean_fwd_8h`, `hit_rate`, `median_gap`, `gap_ok_count`,
  `gap_ok_mean_fwd_24h`, `gap_ok_hit_rate`.
- Dòng: `gap_ok` chỉ ở current / chỉ ở no_smc (`gap_ok_only_one_variant`).
- Dòng: chênh lệch fwd 8h (`descriptive_fwd_8h` diff + CI) — ghi "mô tả, không
  thuộc Q4".
- Dòng: `only_no_smc_mean_fwd_24h` với chú thích nguyên văn
  `Pair mà biến thể hiện tại không chấm được vì SMC data_unavailable ở ít nhất một side (fail-closed).`
- Bảng `by_regime`: regime, both, changed, mean_diff_fwd_24h.

**`## 4. Khả năng phân biệt từng thành phần`**

Bảng từ `component_discrimination.all`: thành phần (`trend`, `momentum`,
`location`, `smc_raw`, `quality_score`), `n`, `spearman_fwd_8h`,
`spearman_fwd_24h`, `auc_fwd_24h_pos`. Sau đó bảng hit-rate theo bucket cho
từng thành phần có bucket (bucket, n, hit-rate, mean fwd 24h). Không in
`by_regime` chi tiết (đã có trong `analysis.md`); thêm một dòng trỏ tới
`analysis.md`.

**`## 5. SMC trên side có plan (TP/SL)`**

- Bảng `counts_total` của `tp_sl` (đủ 6 giá trị).
- Bảng AUC: `quality_score` (từ `q4_condition_2`) + `auc_extra` (`quality_raw`,
  `b`, `q`, `l`, `c`): AUC, CI95.
- Bảng tỷ lệ `tp_first` theo bucket `quality_raw` và theo `readiness_status`
  (n, tỷ lệ).
- Dòng: tỷ lệ `tp_first` chung = `n_tp / n_resolved`; dòng nguyên văn
  `Với R:R tối thiểu <min_rr>, tỷ lệ TP-trước hòa vốn (bỏ qua chi phí) là 1/(1+R:R) = <x>.`
  với `x = 1/(1+min_rr)` in dạng %.
- Mean `mfe_r` / `mae_r` theo nhãn.

**`## 6. Ánh xạ Q6 (SMC → evidence_score) — dữ kiện`**

Bảng `q6_evidence`: n None / 0 / >0; phân phối >0 (min, p25, median, p75,
max); đếm theo `smc_state`. Không viết nhận định.

**`## 7. Giới hạn`** — in **nguyên văn** danh sách sau (số trong `<>` lấy từ file):

1. `Quy mô nhỏ: <rows> snapshot, <day_clusters> ngày, ~3 tháng; regime gần như chỉ có trending (ranging <n_ranging>, volatile <n_volatile>).`
2. `Không tính spread/chi phí (Q9).`
3. `fwd 8h/24h tính theo số nến H1 (nến thứ 8/24 sau cutoff), không theo giờ đồng hồ; qua cuối tuần thì dài hơn 24 giờ.`
4. `TP/SL: entry là lệnh limit tại mép zone, giá khớp coi là đúng entry; nến khớp chỉ xét SL; cùng nến chạm TP và SL tính SL (STOP_FIRST); không khớp trong 48 H1 → not_filled.`
5. `Tỷ lệ chưa có kết quả: unresolved <n_unresolved>, not_filled <n_not_filled> trên <n_plan> side có plan.` (`n_plan` = tổng `tp_first+sl_first+unresolved+not_filled+plan_invalid`)
6. `<errors> cutoff (<error_rate>) lỗi pipeline SMC (<error_types>) bị loại khỏi phân tích.`
7. `Trọng số 3 thành phần là mặc định chia lại tỷ lệ (Q5), chưa tối ưu.`
8. `Không có bằng chứng lợi nhuận; mọi chỉ số chỉ mang tính so sánh tương đối.`

**`## 8. Pair đổi side`**

Bảng mọi phần tử `side_selection.changed_rows` (sắp theo symbol, cutoff):
symbol, cutoff, regime, side hiện tại → side mới, điểm buy/sell mỗi biến thể,
smc_raw buy/sell, fwd 24h hiện tại → mới.

### 3.3 Test `tests/test_smc_demote_report.py`

Dict tổng hợp nhỏ (không đọc file thật), tối thiểu:

1. Chọn đúng câu "Kết quả cơ học" cho 3 tổ hợp `pass` (F/F→câu 1, T/F→câu 2,
   T/T→câu 3; F/T cũng ra câu 1).
2. `factor`: `diff=0.0, ci=[-0.09, 0.09]` → `half_width=0.09`, `need=0.05`,
   `factor=3.24` → in `3.2`; `diff=-0.06` → in câu "đã dưới ngưỡng".
3. Định dạng: `None` → `—`; `0.12345` → `0.123`; tỷ lệ `0.3333` → `33.3%`.
4. Hash `rows_sha256` lệch → hàm kiểm trả lỗi (BLOCKED).

## 4. Lệnh nghiệm thu (dán output thật vào report)

```powershell
python -X utf8 -m pytest tests/test_smc_demote_report.py -q
python -X utf8 scripts/smc_demote_report.py
Get-FileHash reports/scanner/smc_demote/report.md
python -X utf8 scripts/smc_demote_report.py
Get-FileHash reports/scanner/smc_demote/report.md    # phải giống lần trước
git status --short
```

**Đạt khi:** test pass; hai hash giống nhau; `report.md` có đủ 8 mục đúng
tiêu đề; số Q4 trong mục 1 trùng `analysis.json`.

## 5. Không được làm

- Không sửa script/kết quả của SD-C1–C3, `core/`, `services/`, `controllers/`,
  `ui/`, `config/`, plan, file giao việc.
- Không chạy lại `fetch`/`run`/`analyze`; không tính thống kê mới ngoài
  `half_width`/`need`/`factor`/tỷ lệ hòa vốn ở trên.
- Không viết khuyến nghị, nhận định, "nên chọn…" ngoài câu cơ học ở mục 1.
- Không ghi vào §8 của plan (TL làm tại CP1). Không bắt đầu task giai đoạn 2.

## 6. Commit và báo cáo

- Commit `main`: `feat(research): [SD-C4] báo cáo CP1 SMC demote`. Gồm
  `scripts/smc_demote_report.py`, `tests/test_smc_demote_report.py`,
  `reports/scanner/smc_demote/report.md`.
- Viết `docs/plans/smc-demote-tasks/SD-C4-report.md` (mẫu §7 plan, ghi hash
  commit code), commit riêng `docs(smc): [SD-C4] báo cáo`. Kèm: hai hash
  `report.md`, và chép nguyên mục "1. Kết quả quy tắc Q4" của `report.md`.
- Sau đó **dừng**. Đây là task cuối Giai đoạn 1 — chờ TL/Owner tại CP1.

## Rework

_(TL ghi yêu cầu sửa ở đây nếu có.)_
