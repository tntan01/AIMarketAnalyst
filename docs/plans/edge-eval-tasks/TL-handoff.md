# Bàn giao vai Tech Lead — đợt đo edge (EE)

> Dành cho phiên Claude nhận vai TL của đợt này. Trả lời Owner bằng tiếng Việt.

## 1. Vai trò và quy trình

Giống hệt đợt SMC demote: đọc
[`../smc-demote-tasks/TL-handoff.md`](../smc-demote-tasks/TL-handoff.md) §1,
§4, §5 (checklist review, ACCEPT/REWORK, câu dán cho Coder). Khác biệt duy nhất:
file giao việc/report nằm ở `docs/plans/edge-eval-tasks/`, commit dùng
`feat(research): [EE-xx] …` / `docs(edge): …`.

## 2. Đọc theo thứ tự

1. [`../edge-eval-plan.md`](../edge-eval-plan.md) — câu hỏi, sự thật đã kiểm
   chứng, quyết định E1–E9, task, quy tắc đọc kết quả E8.
2. File giao việc mới nhất `EE-xx.md` và report tương ứng.
3. Bối cảnh đợt trước: [`../../../reports/scanner/smc_demote/report.md`](../../../reports/scanner/smc_demote/report.md).

## 3. Trạng thái

- 07/10/2026: CP-E0 duyệt (E1–E9 như đề xuất; không tính commission).
  **EE-C1 đã giao**, chờ Coder.
- Thứ tự: EE-C1 → EE-C2 → EE-A1 → EE-A2 → **CP-E1** (trình Owner, không tự qua).

## 4. Ghi chú kỹ thuật cho task tới

**EE-C2:** import `windows_at`/`load_symbol_data` từ `scripts/edge_eval_corpus.py`
(trả thêm `tail_spread`), `live_analysis_at` từ `scripts/smc_demote_replay.py`
— nhưng `live_analysis_at` gọi `windows_at` của SD-C1 (tail 48): EE-C2 phải
gọi `derive_live_analysis` trên prefix của windows_at mới (cùng tham số như
`_parity._live`) hoặc tách hàm; không sửa script SD. Nhãn bid/ask: mua khớp
ask = bid + spread×point; SL mua chạm khi bid low ≤ SL; TP mua khi bid high ≥ TP;
bán ngược lại (SL bán chạm khi ask high ≥ SL, TP bán khi ask low ≤ TP).
Mô hình M: giá vào = open nến M15 đầu tail (+ spread×point nếu mua).
Đường lệnh thật E6: setup = 0,65×technical + 17,5. Công thức TechnicalScore
4 thành phần: `scripts/smc_demote_analyze.py:current_score` (đã khớp scorer thật).
