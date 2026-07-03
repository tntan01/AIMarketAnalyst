# Bug Tracker — AI Market Analyst

**Ngày tạo:** 2026-07-03
**Mục đích:** Ghi nhận bug phát hiện trong quá trình điều tra, kèm trạng thái sửa.

Trạng thái: **ĐÃ FIX** | **CHƯA FIX**

---

## Risk Engine — Trade Plan Builder

Nguồn: Điều tra độc lập (2026-07-03)

### BUG-001 — TP1 nằm trong entry zone

- **Trạng thái:** CHƯA FIX
- **Mức độ:** Nghiêm trọng
- **File:** `core/risk_engine.py:505-506` (BUY), `575-576` (SELL)
- **Mô tả:** `nearest_target()` tìm S/R zone gần nhất `> entry_for_rr` nhưng **không kiểm tra `>= entry_high`** (BUY) hoặc `<= entry_low` (SELL). Với `_ENTRY_AGGRESSIVENESS = 0.0`, `entry_for_rr = entry_low`, một resistance zone nằm giữa `entry_low` và `entry_high` có thể vượt qua cả directional check lẫn R:R check và được chọn làm TP1 — dẫn đến TP1 nằm **trong** entry zone.

  **Dữ liệu thực tế (GBPNZD):**
  ```
  Entry-:  2.33590    TP1:     2.33773  ← nằm trong zone!
  Entry+:  2.33813    TP2:     2.34299
  SL:      2.33547    Current: 2.33972
  ```
  Với `entry_for_rr = entry_low = 2.33590`, risk = 0.000430. TP1 (2.33773) cho R:R = 4.26 — vượt qua check nhưng vẫn nằm trong entry zone.

  Cùng pattern tồn tại ở cả 4 tầng TP1 cascade: `_find_nearest_equal_level`, `nearest_target`, `_fib_extension_target`, `_find_nearest_swing_for_tp`.

- **Phạm vi ảnh hưởng:** BUY và SELL, mọi `entry_aggressiveness < ~0.32`. Tần suất phụ thuộc vào việc có S/R zone nằm trong entry zone hay không.

- **Phương án A:** Thêm guard clause trong `build_trade_plan` — sau TP1 cascade, nếu `tp1 <= entry_high` (BUY) hoặc `tp1 >= entry_low` (SELL) → reject, fall through.
  - Ưu: 2 dòng code, sửa dứt điểm mọi nguồn TP1. Nhược: nếu không có TP hợp lệ → plan bị hủy (hợp lý).

- **Phương án B:** Sửa từng hàm tìm TP riêng lẻ (`nearest_target`, `_find_nearest_equal_level`, `_find_nearest_swing_for_tp`, `_fib_extension_target`) — thêm tham số `entry_high`/`entry_low` để filter.
  - Ưu: mỗi hàm tự bảo vệ. Nhược: phải sửa 4-5 hàm, đổi signature, rủi ro regression cao.

- **Khuyến nghị:** Phương án A.

- **Test tái hiện:** `tests/test_tp1_inside_entry_zone_repro.py` (5 tests)

---

## Tổng kết

| ID | Mô tả ngắn | Mức độ | Trạng thái |
|----|-----------|--------|------------|
| BUG-001 | TP1 nằm trong entry zone | Nghiêm trọng | CHƯA FIX |
