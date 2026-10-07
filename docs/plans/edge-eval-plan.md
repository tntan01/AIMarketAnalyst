# Kế hoạch: đo edge của TechnicalScore và plan SMC (Tech Lead → Coder)

> **Trạng thái:** CP-E0 DUYỆT 07/10/2026 (E1–E9 như đề xuất). **EE-C1 đã giao:**
> [`edge-eval-tasks/EE-C1.md`](edge-eval-tasks/EE-C1.md). TL handoff:
> [`edge-eval-tasks/TL-handoff.md`](edge-eval-tasks/TL-handoff.md).  
> **Ngày lập:** 07/10/2026.  
> **Nguồn gốc:** đợt SMC demote đóng tại CP1
> ([`smc-demote-task-plan.md`](smc-demote-task-plan.md) §8,
> [`reports/scanner/smc_demote/report.md`](../../reports/scanner/smc_demote/report.md)).  
> **Quy trình TL/Coder:** giống hệt đợt SMC demote
> ([`smc-demote-task-plan.md`](smc-demote-task-plan.md) §0.2, §0.4, §7);
> file giao việc ở `docs/plans/edge-eval-tasks/`.  
> **Phạm vi:** chỉ đo, offline. Không sửa `core/`, `controllers/`, `ui/`,
> `services/`, `config/`, không đổi contract, không gửi lệnh.

## 1. Câu hỏi cần trả lời

1. **Chọn hướng:** side mà TechnicalScore hiện tại chọn có đi đúng hướng hơn
   chọn ngẫu nhiên không? Điểm/gap cao hơn có cho kết quả tốt hơn không?
2. **Plan SMC:** sau khi tính spread, kỳ vọng của plan (entry/SL/TP) theo R có
   dương không? Hỏng ở khâu nào (khớp lệnh, SL, TP, readiness, regime, symbol)?
3. **Đường lệnh thật:** những setup mà Scanner thực sự sẽ gửi lệnh có kỳ vọng
   dương không?

Kết quả dùng để quyết định sửa gì trước (CP-E1); bản thân đợt này **không**
sửa hay tối ưu gì.

## 2. Sự thật đã kiểm chứng (TL, 07/10/2026)

- **Lịch sử broker đủ sâu:** `copy_rates_range` trả M15/H1/H4 từ 01/07/2024
  (EUR/USD M15 56.437 nến, BTC/USD 79.483), `maxbars` terminal = 100.000.
- **Có spread theo từng nến:** cột `spread` (đơn vị point) trong rates MT5;
  trung vị EUR/USD 9 point (0,9 pip), XAU/USD 160 point (0,16), GBP/JPY 22,
  BTC/USD ~2.000. `Candle` của app **không** giữ spread → đợt này phải lưu
  riêng. Nến MT5 là giá **bid**.
- **Live đặt lệnh market, không đặt limit:** `services/mt5_service.py` gửi
  `TRADE_ACTION_DEAL` tại `tick.ask`/`tick.bid` kèm SL/TP của plan. Mô hình
  nhãn của SD-C2 (limit tại mép zone) đo chất lượng hình học plan, **không**
  phải đường lệnh thật.
- Công cụ dùng lại được: `scripts/smc_demote_corpus.py` (`windows_at`,
  `load_symbol_data`), `scripts/smc_demote_replay.py` (`live_analysis_at`,
  khung `run` chạy song song/chạy tiếp), `scripts/smc_demote_analyze.py`
  (AUC, Spearman, bootstrap cụm, công thức TechnicalScore đã khớp scorer
  thật). Tốc độ ~1,1 giây/snapshot/process; 8 process ổn (RAM ~60 MB/process).
- Corpus SMC demote (2010 snapshot, 3 tháng): side chọn fwd 24h −0,09 ATR, CI
  [−0,39; 0,20]; plan (mô hình limit, không spread) TP-trước 19 % (96/494).

## 3. Quyết định cần Owner duyệt (CP-E0)

Cột "Đề xuất" là khuyến nghị của TL; Owner duyệt/sửa trước khi giao EE-C1.

| ID | Câu hỏi | Đề xuất | Lý do |
|---|---|---|---|
| E1 | Khoảng thời gian | Cutoff từ **01/07/2025** đến hết ngày còn đủ tail (~03/10/2026), **~15 tháng**. Lịch sử fetch lùi đủ cửa sổ 500 nến D1 trước cutoff đầu (D1 ~1.300 ngày, H4 ~600, H1 ~520, M15 ~500) | Đủ nhiều tháng và nhiều trạng thái thị trường; M15 có từ 07/2024 nên tail M15 đủ cho mọi cutoff |
| E2 | Mật độ cutoff | **3 cutoff/ngày, cố định 04:00, 12:00, 20:00 UTC**, mọi ngày có nến (BTC cả cuối tuần). Ước tính ~30.000 snapshot, ~70 phút với 8 process | Phủ cả phiên Á/Âu/Mỹ mỗi ngày; các cutoff cùng ngày tương quan → xử lý bằng bootstrap cụm ngày (E8) |
| E3 | Giá và chi phí | Nến MT5 = bid; **ask = bid + spread×point của chính nến đó**. Mua khớp/đóng theo ask/bid đúng chiều; **không** tính commission/swap (Owner xác nhận loại tài khoản). Luôn tính song song nhãn **không chi phí** để so | Spread là chi phí lớn nhất và có sẵn theo từng nến; giữ bản không chi phí để tách "edge" khỏi "chi phí" |
| E4 | Horizon | Tail **96 H1 / 384 M15** (4 ngày giao dịch). Hết horizon chưa chạm TP/SL → đóng theo giá cuối (mark-to-market, ra R) và đếm riêng | Corpus cũ có 205 unresolved + 627 not_filled / 1.326 plan với tail 48 H1; horizon dài hơn giảm số bị bỏ |
| E5 | Mô hình vào lệnh | Hai mô hình cho mọi side có plan: **(L) limit tại E** như SD-C2 (đo hình học plan); **(M) market tại cutoff**: vào ở giá mở nến M15 đầu tiên sau cutoff (+spread nếu mua), SL/TP của plan; plan có SL/TP sai phía so với giá vào → `invalid_at_market` | (M) giống live (`TRADE_ACTION_DEAL`); (L) cho biết vấn đề ở hình học hay ở thời điểm vào |
| E6 | "Đường lệnh thật" (xấp xỉ) | Side được chọn bởi TechnicalScore 4 thành phần **và** gap ≥ 5 **và** technical ≥ 40 **và** setup ≥ 35 (setup = 0,65×technical + 17,5 vì evidence/execution live đang neutral 50) **và** plan có **và** readiness `READY_NOW` **và** R:R ≥ 2. **Không** mô phỏng Macro/Safety/news/portfolio | Các gate ngoài không tái lập được offline; ghi rõ là xấp xỉ. Nếu nhóm này quá ít mẫu (< 200), báo "không đủ mẫu" thay vì kết luận |
| E7 | Kiểm độ ổn định | Không fit gì nên không cần train/test thật; chia **hai nửa thời gian** (~01/07/2025–31/01/2026 và 01/02/2026–hết) + theo quý; báo mọi chỉ số cho cả hai nửa | Edge thật phải cùng dấu ở cả hai nửa |
| E8 | Quy tắc đọc kết quả | **Có edge chọn hướng** nếu mean fwd 24h (ATR) side chọn có cận dưới CI95 > 0 **và** cả hai nửa > 0. **Plan có edge** (theo từng mô hình L/M, có spread) nếu kỳ vọng R có cận dưới CI95 > 0 **và** cả hai nửa > 0. CI = bootstrap cụm ngày UTC, 2.000 vòng, seed cố định | Quy tắc định trước, không chọn sau khi xem số |
| E9 | Lưu trữ | Như Q8 đợt trước: nến gốc + spread lưu một lần, `data/` không commit; commit manifest (hash), cutoffs, kết quả phân tích. Thư mục `reports/scanner/edge_eval/`. Script mới `scripts/edge_eval_*.py`, **import** helper SD, **không sửa** script SD (giữ đợt cũ tái lập được) | Giống quy trình đã chạy tốt |

## 4. Các task

Toàn bộ code ở `scripts/`, output ở `reports/scanner/edge_eval/`.

### EE-C1 — Corpus 15 tháng có spread

- `scripts/edge_eval_corpus.py`: `fetch` (D1/H4/H1/M15 theo E1, lưu thêm
  spread H1/M15 theo từng nến, `point` của symbol), `plan` (cutoff theo E1/E2,
  bỏ `market_closed`/`insufficient_history`/`insufficient_tail` với tail 96
  H1), `verify` (không nến prefix đóng sau cutoff, tail bắt đầu sau cutoff và
  đủ dài, hash khớp manifest). Dùng lại `closed_candles_at_cutoff`, cùng
  `WINDOW_BARS` với SD-C1.
- **Chấp nhận:** `verify` 0 problems; số cutoff trong khoảng dự kiến (báo lý
  do nếu lệch); manifest có spread trung vị theo symbol; test tổng hợp cho
  `windows_at` mới (nếu viết hàm mới) và cho việc ghép spread đúng nến.

### EE-C2 — Replay và nhãn có chi phí

- `scripts/edge_eval_replay.py`: chạy `live_analysis_at` (import từ SD-C2) tại
  mọi cutoff, song song, chạy tiếp được; row giống SD-C2 + điểm TechnicalScore
  4 thành phần, gap, setup, cờ "đường lệnh thật" (E6).
- Nhãn mỗi side: fwd 8h/24h/48h (ATR H1, theo nến H1); plan theo E5 × {không
  chi phí, có spread}: kết quả (`tp`, `sl`, `timeout`, `not_filled`,
  `invalid`), R thực nhận, số nến tới khớp/kết thúc, MFE/MAE theo R.
- **Chấp nhận:** parity 58 snapshot như SD-C2; với cutoff trùng corpus SD-C1
  (cùng symbol/giờ), field điểm/SMC khớp `replay_rows.jsonl` cũ; test nhãn
  (bid/ask, STOP_FIRST, timeout mark-to-market, không dùng dữ liệu ≤ cutoff);
  error_rate ≤ 2 %.

### EE-A1 — Phân tích

- `scripts/edge_eval_analyze.py`, chỉ số theo E7/E8:
  1. Chọn hướng: mean/hit fwd 8h/24h/48h của side chọn, CI; theo bucket
     điểm technical và gap (có đơn điệu không); theo regime, symbol; AUC từng
     thành phần.
  2. Plan (L và M, có/không spread): tỷ lệ khớp, phân bố kết quả, kỳ vọng R +
     CI; theo readiness, regime, symbol, timeframe/family zone, khoảng cách SL
     (ATR), R:R; phần chi phí spread chiếm bao nhiêu R.
  3. Đường lệnh thật (E6): số setup, kỳ vọng R mô hình M có spread, CI.
  4. Mọi mục trên cho hai nửa thời gian và theo quý.
- **Chấp nhận:** tất định (hai lần chạy cùng hash); kiểm lại công thức
  TechnicalScore với scorer thật trên mẫu (như `check-scorer`).

### EE-A2 — Báo cáo → CP-E1

- `reports/scanner/edge_eval/report.md` sinh bằng script: kết quả quy tắc E8
  cho chọn hướng, plan L, plan M, đường lệnh thật; bảng phân rã chính; giới
  hạn. Không khuyến nghị.
- **CP-E1 — Owner:** dựa trên báo cáo + nhận định của TL, chọn việc sửa
  tiếp theo (vd. chọn hướng, entry/readiness, SL/TP, symbol/regime), hoặc
  dừng. Mỗi việc sửa là plan riêng.

## 5. Ngoài phạm vi

- Sửa scorer, trọng số, threshold, plan SMC, order policy, `live_order_permitted`.
- Mô phỏng Macro/Safety/news/portfolio, slippage, commission/swap.
- Lỗi pipeline SMC 13 cutoff và phân loại regime (việc riêng; đợt này chỉ
  đếm lỗi và báo phân bố regime).

## 6. Rủi ro

- `READY_NOW` hiếm (9/3.994 side ở corpus cũ) → đường lệnh thật có thể không
  đủ mẫu dù corpus lớn hơn 15 lần; khi đó kết luận dựa trên mô hình M cho mọi
  side có plan, ghi rõ.
- Spread trong rates MT5 là một giá trị/nến, không phải spread lúc khớp thật.
- Kết quả có thể cho thấy hệ thống **không có edge**; đó là kết quả hợp lệ,
  không chỉnh tham số trong đợt này để "cứu" số.

## 7. Nhật ký quyết định

| Ngày | Quyết định | Người chốt | Ghi chú |
|---|---|---|---|
| 07/10/2026 | **CP-E0: duyệt E1–E9 như đề xuất** | Owner | Commission/swap không tính (Owner không nêu loại tài khoản có commission) — ghi trong giới hạn báo cáo |
| | CP-E1 | | |
