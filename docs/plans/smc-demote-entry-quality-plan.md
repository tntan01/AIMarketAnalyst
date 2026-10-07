# Đề xuất: rút SMC khỏi TechnicalScore, dùng làm chất lượng entry (chờ duyệt)

> **Trạng thái:** KHÔNG TRIỂN KHAI — Owner chọn giữ nguyên tại CP1 (07/10/2026)
> sau khi đo trên corpus 1997 snapshot; xem
> [`reports/scanner/smc_demote/report.md`](../../reports/scanner/smc_demote/report.md)
> và §8 của [`smc-demote-task-plan.md`](smc-demote-task-plan.md). Không sửa
> code/contract.  
> **Ngày:** 07/10/2026.  
> **Phạm vi:** vai trò của thành phần `smc` trong `TechnicalSignalScore`
> (§3.1–3.3 của scanner-architecture). Không đổi công thức B/Q/L/C nội bộ, không
> đổi gate Macro/Safety, không đổi R:R hay order policy.  
> **Lưu ý về bằng chứng:** số liệu ở §3–§4 lấy từ mẫu nhỏ (58 snapshot) — đủ để
> chỉ ra vấn đề cấu trúc, **chưa đủ** để khẳng định cải thiện lợi nhuận. Bước
> hiệu chỉnh ở §6 là điều kiện trước khi chốt.

## 1. Hiện trạng

- `TechnicalSignalScore` gồm Trend (0–25), Momentum (0–20), Location (0–25),
  SMC (0–15), quy đổi theo trọng số regime (trending 40/20/20/20, ranging
  10/10/40/40, volatile 20/10/40/30, unknown 25×4). Chọn BUY/SELL chỉ từ điểm này.
- SMC raw = `quality_raw = round_half_up(4B + 7Q + 2L + 2C)` của **zone tốt nhất
  của mỗi side** ([`smc-bqlc-spec.md`](smc-bqlc-spec.md) §1), đọc qua
  `project_smc_quality_raw` (`core/technical_signal_scorer.py`).
- Theo đặc tả, `S` **cố ý không tính** khoảng cách giá–zone, phản ứng M15 hay
  R:R. Tức SMC đo "side này có một zone đẹp ở đâu đó", không đo "giá đang phản
  ứng tại zone nên đi hướng này".
- Thứ tự candidate: `confirmation_rank` → quality → distance
  (`candidate_order_key`, `core/smc_models.py`).

## 2. Chẩn đoán

| # | Vấn đề | Hệ quả |
|---|---|---|
| D1 | SMC là thuộc tính chất lượng entry nhưng được dùng như tín hiệu hướng | Cả hai side thường đều có zone → SMC ít phân biệt BUY/SELL |
| D2 | Dải điểm nén (phần lớn raw khác 0 nằm trong 5–9) | Ở trending, SMC ≈ hằng số ~9–12 điểm cộng cho cả hai side |
| D3 | Không có zone → raw 0 | Vách ~10 điểm technical; đủ để lật side dù Trend/Momentum/Location nghiêng hẳn phía kia |
| D4 | B (structure) trùng Trend (`structure_h4/d1 HH/HL`) | Đếm cấu trúc hai lần |
| D5 | Location và SMC cùng chấm "zone" bằng hai engine khác nhau | Chồng lấn khái niệm |
| D6 | Trọng số 4/7/2/2 là baseline chưa hiệu chỉnh (spec §1 tự ghi) | Q (chủ yếu hình dạng nến) chiếm 7/15 không có căn cứ dữ liệu |
| D7 | SMC thiếu dữ liệu → TechnicalScore fail-closed | Lỗi producer SMC (vd. L=0, `atr_current` thiếu — xem [`smc-bqlc-producer-gaps-plan.md`](smc-bqlc-producer-gaps-plan.md)) lan thẳng vào chọn hướng và chặn cả pair |

## 3. Số liệu đo trên corpus

**Cách tái lập:** replay `reports/scanner/smc_real_snapshots/corpus.jsonl.gz`
(58 snapshot, 13 symbol) qua `core.scanner_live_producers.derive_live_analysis`
đúng recipe của `scripts/smc_replay_parity.py` (500 nến D1/H4/H1, 100 nến M15,
không kèm `future_tail`). Outcome = `(close H1 thứ k sau cutoff − close H1 cuối
đã đóng) × hướng side / ATR(14) H1`, lấy từ `future_tail.H1` (24 bar). Script
phân tích là scratch, không commit.

Kết quả (105 side có `quality_raw` khác null, 50 pair có cả hai side):

- Phân bố raw SMC: `0×16, 4×3, 5×9, 6×8, 7×17, 8×30, 9×14, 10×5, 11×2, 12×1`.
  L>0 trên 17/105 side (sau khi producer sweep đã nối).
- |SMC BUY − SMC SELL| ≤ 1 ở 36% pair.
- Tương quan B với Trend 0.28, với Momentum 0.36; SMC với Location −0.21.

| Thành phần | Tương quan với outcome 24h | Hit-rate (outcome > 0) theo nhóm điểm |
|---|---|---|
| SMC | −0.04, không đơn điệu | 0–5: 64% · 6–7: 24% · 8: 53% · 9+: 50% |
| Trend | +0.06, tăng đơn điệu | 0–8: 38% · 9–16: 46% · 17–25: 61% |
| Momentum | +0.24 với outcome 8h | — |

Giới hạn: mẫu nhỏ, các snapshot không độc lập, horizon 24h không phải TP/SL
thật, regime gần như toàn trending (56/58; ranging 2).

## 4. Mô phỏng: chọn side có SMC vs không có SMC

So sánh side được chọn bởi TechnicalScore hiện tại và TechnicalScore chỉ gồm
Trend/Momentum/Location (trọng số regime chia lại tỷ lệ về tổng 100). Chưa áp
min score-gap, gate hay plan.

- 50 pair: 46 giữ side, **4 đổi side**, cả 4 do SMC quyết định:

| Pair | Hiện tại | Không SMC | SMC BUY/SELL | Outcome 24h side hiện tại → side mới (ATR) |
|---|---|---|---|---|
| EUR/USD 2026-06-11 | SELL (gap −15.1) | BUY (+6.0) | 0 / 7 | −3.45 → +3.45 |
| XAU/USD 2026-09-03 | BUY (+4.9) | SELL (−10.5) | 10 / 0 | −3.33 → +3.33 |
| GBP/JPY 2026-02-19 | SELL (−2.7) | BUY (0.0, hòa → BUY) | 7 / 9 | −2.47 → +2.47 |
| NZD/USD 2026-08-03 | BUY (+0.3) | SELL (−1.2) | 9 / 8 | +0.08 → −0.08 |

- Toàn bộ 50 pair: hiện tại mean −0.01 ATR, hit 54%; không SMC mean
  +0.35 ATR, hit 58%. Khác biệt đến hoàn toàn từ 4 pair đổi side → chỉ là tín
  hiệu, không phải bằng chứng.
- Median |gap BUY−SELL|: 25.6 → 30.2 (bỏ phần cộng gần-hằng-số cho cả hai side).

## 5. Phương án

### A (khuyến nghị) — SMC thành chất lượng entry

1. `TechnicalSignalScore` = Trend + Momentum + Location; trọng số regime chia
   lại (giá trị cụ thể chốt sau §6). Chọn side chỉ từ ba thành phần này.
2. SMC `quality_raw` chuyển sang:
   - **Gate:** zone hợp lệ + `plan_available` là điều kiện READY (đã có trong
     selection/readiness — giữ nguyên).
   - **Thành phần của Evidence hoặc Execution** trong `setup_score` (độc lập với
     Technical, không ảnh hưởng chọn side).
   - **Tie-break ranking** giữa setup cùng trạng thái.
3. B bỏ khỏi SMC quality hoặc chỉ giữ `trigger_score` (cấu trúc thuộc Trend).
4. SMC `DATA_UNAVAILABLE` không còn làm TechnicalScore fail-closed; side vẫn
   được chấm, readiness là WAITING/không có plan.

**Lợi ích:** chọn side không bị vách "có/không zone" (D1–D3); hết đếm trùng
cấu trúc (D4); lỗi chuỗi SMC chỉ ảnh hưởng entry/ranking (D7); SMC dùng đúng
vai trò so sánh zone/setup cùng hướng; không nới điều kiện READY.

**Cái giá:** ranging mất thành phần trọng số 40% (Location vẫn gánh; ranging
hiếm); `TechnicalScore`/`setup_score` dịch phân bố → READY/WATCH thay đổi;
đổi version scorer/feature, đánh giá lại threshold, cập nhật UI breakdown và
test.

### B — giữ SMC trong TechnicalScore nhưng đổi ngữ nghĩa sang "đang kích hoạt"

SMC chỉ có điểm khi giá đang trong/sát zone đúng side **và** có phản ứng
(`completed_reacted`, M15 confirmation/CHoCH), có sweep link, không có zone
đối diện chặn gần; ngược lại 0 và trọng số trả về Trend/Location. Sát tinh
thần SMC (phản ứng tại POI) hơn nhưng phải viết lại `smc-bqlc-spec.md`.

## 6. Điều kiện trước khi chốt (cả A và B)

1. Mở rộng corpus bằng cách trượt cutoff offline trên lịch sử nến sẵn có
   (mục tiêu hàng nghìn snapshot, nhiều regime).
2. Nhãn outcome theo plan thật: TP-trước/SL-trước, MFE/MAE theo R; giữ cả
   outcome 8h/24h.
3. Đo khả năng phân biệt từng thành phần (AUC/hit-rate theo bucket), ablation
   `setup_score` có/không SMC, và so A với B.
4. Hiệu chỉnh trọng số regime (và 4/7/2/2 nếu giữ B) theo dữ liệu.

## 7. Ràng buộc quy trình

- Cập nhật [`scanner-architecture.md`](../scanner/scanner-architecture.md) §3
  **trước** khi sửa code (D1 trong architecture-rules).
- Ngữ nghĩa score đổi → đổi version scorer/feature; config cũ fail-closed.
- Không chỉnh threshold để giữ kết quả cũ; Owner đánh giá lại trên phân bố mới.
- Không chạy dual/shadow scorer trên live; snapshot/journal cũ giữ nguyên
  ngữ nghĩa (compatibility contract).

Kế hoạch giao việc chi tiết (TL → Coder):
[`smc-demote-task-plan.md`](smc-demote-task-plan.md).

## 8. Quyết định cần Owner

1. Chọn A, B, hay giữ nguyên chờ dữ liệu §6.
2. Duyệt phạm vi bước hiệu chỉnh §6 (kích thước corpus, định nghĩa outcome).
3. Với A: SMC vào Evidence hay Execution của `setup_score`.
