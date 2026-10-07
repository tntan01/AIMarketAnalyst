# SD-C4 report — Báo cáo CP1 (sinh tự động)

Task: SD-C4 — Báo cáo CP1 (sinh tự động từ kết quả phân tích)
Commit code: `8526dfb` (3 file: `scripts/smc_demote_report.py`,
`tests/test_smc_demote_report.py`, `reports/scanner/smc_demote/report.md`)

## Đã làm

- Thêm `scripts/smc_demote_report.py` (một lệnh, không subcommand): đọc 5 file
  kết quả đã commit (`analysis.json`, `replay_summary.json`, `corpus_manifest.json`,
  `cutoffs.json`, `scorer_check.json`), kiểm `rows_sha256` khớp giữa
  `analysis.json` và `replay_summary.json` (khác → `BLOCKED`, exit 2), rồi ghi
  `reports/scanner/smc_demote/report.md`.
- Báo cáo gồm đủ 8 mục đúng tiêu đề; số thực 3 chữ số thập phân, tỷ lệ `%` 1
  chữ số, `None` → `—`; chỉ tính thêm `half_width`/`need`/`factor` và tỷ lệ
  TP hòa vốn; không ghi `now()` (chạy lại giống hệt byte).
- Thêm `tests/test_smc_demote_report.py` (4 test).

## Kiểm tra đã chạy

```text
python -X utf8 -m pytest tests/test_smc_demote_report.py -q
....                                                                     [100%]
4 passed in 0.08s
```

```text
python -X utf8 scripts/smc_demote_report.py
report -> D:\Projects\AIMarketAnalyst\reports\scanner\smc_demote\report.md
```

Tất định (`report.md` giống hệt byte qua hai lần chạy):

```text
Get-FileHash reports/scanner/smc_demote/report.md -Algorithm SHA256
RUN1 1CE832A785A1F9C6C67BD2359E74811EF2C9CBA9FC63E8FFD066772804384272
RUN2 1CE832A785A1F9C6C67BD2359E74811EF2C9CBA9FC63E8FFD066772804384272
```

```text
git status --short --untracked-files=all
?? reports/scanner/smc_demote/report.md
?? scripts/smc_demote_report.py
?? tests/test_smc_demote_report.py
```
→ không file nào trong `reports/scanner/smc_demote/data/` xuất hiện.

Đủ 8 mục đúng tiêu đề (`## 1.` … `## 8.`).

## Mục "1. Kết quả quy tắc Q4" của `report.md` (chép nguyên)

```markdown
## 1. Kết quả quy tắc Q4

| Điều kiện | Chỉ số | Giá trị | CI95 | Ngưỡng | Kết quả |
|---|---|---:|---|---|---|
| (1) Chọn side | mean fwd 24h (ATR) side chọn bởi 3 thành phần − 4 thành phần, trên pair cả hai chọn được | -0.000 | [-0.090, 0.086] | cận dưới ≥ −0,05 | KHÔNG ĐẠT |
| (2) SMC phân biệt TP/SL | AUC `quality_score`, n resolved = 494 (TP 96 / SL 398) | 0.467 | [0.407, 0.527] | AUC ≥ 0,55 và cận dưới > 0,5; n ≥ 200 | KHÔNG ĐẠT |

**Kết quả cơ học của quy tắc Q4:** Không đạt điều kiện (1) → giữ nguyên TechnicalScore 4 thành phần; TL cân nhắc phương án B.

**Độ rộng khoảng tin cậy (1):** half_width = 0.088, need = 0.050, factor = 3.2. Ước tính thô: nếu chênh lệch giữ nguyên, cần khoảng 3.2 lần số pair hiện tại để cận dưới CI95 đạt −0,05 (giả định độ rộng CI tỷ lệ 1/√n).
```

## Thay đổi hành vi/expected

Không có. Task chỉ thêm script sinh báo cáo + output, không sửa script/kết quả
SD-C1–C3, `core/`, `services/`, `controllers/`, `ui/`, `config/`, plan hay file
giao việc; không chạy lại `fetch`/`run`/`analyze`.

## Câu hỏi cho TL / điểm mơ hồ

- Không có. Đây là task cuối Giai đoạn 1; chờ TL/Owner tại CP1.

## Rủi ro còn lại

- Báo cáo phụ thuộc hoàn toàn vào các file kết quả đã commit; nếu `analysis.json`
  được sinh lại (đổi dữ liệu/phiên bản numpy), phải chạy lại script này để đồng bộ.
- Thứ tự bucket trong các bảng bucket là thứ tự chuỗi (do `analysis.json` ghi
  `sort_keys=True`), không phải thứ tự số; giá trị vẫn đúng.
