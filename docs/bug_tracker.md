# Bug Tracker — AI Market Analyst

**Ngày tạo:** 2026-07-03
**Mục đích:** Ghi nhận bug phát hiện trong quá trình điều tra, kèm trạng thái sửa.

Trạng thái: **ĐÃ FIX** | **CHƯA FIX**

---

## Risk Engine — Trade Plan Builder

Nguồn: Điều tra độc lập (2026-07-03)

### BUG-001 — TP1 nằm trong entry zone

- **Trạng thái:** ĐÃ FIX (2026-07-03)
- **Mức độ:** Nghiêm trọng
- **File:** `core/risk_engine.py:513-514` (BUY), `586-587` (SELL)
- **Mô tả:** `nearest_target()` tìm S/R zone gần nhất `> entry_for_rr` nhưng **không kiểm tra `>= entry_high`** (BUY) hoặc `<= entry_low` (SELL). Với `_ENTRY_AGGRESSIVENESS = 0.0`, `entry_for_rr = entry_low`, một resistance zone nằm giữa `entry_low` và `entry_high` có thể vượt qua cả directional check lẫn R:R check và được chọn làm TP1 — dẫn đến TP1 nằm **trong** entry zone.

  **Dữ liệu thực tế (GBPNZD):**
  ```
  Entry-:  2.33590    TP1:     2.33773  ← nằm trong zone!
  Entry+:  2.33813    TP2:     2.34299
  SL:      2.33547    Current: 2.33972
  ```
  Với `entry_for_rr = entry_low = 2.33590`, risk = 0.000430. TP1 (2.33773) cho R:R = 4.26 — vượt qua check nhưng vẫn nằm trong entry zone.

  Cùng pattern tồn tại ở cả 4 tầng TP1 cascade: `_find_nearest_equal_level`, `nearest_target`, `_fib_extension_target`, `_find_nearest_swing_for_tp`.

- **Fix:** Phương án A — thêm guard clause sau TP1 cascade, trước final fallback. BUY: `if tp1 is not None and tp1 <= entry_high → tp1 = None`. SELL: `if tp1 is not None and tp1 >= entry_low → tp1 = None`. Nếu không có TP hợp lệ → plan bị hủy (không vào lệnh với TP ảo).

- **Test:** `tests/test_tp1_zone_guard_fix.py` (5 tests) + `tests/test_tp1_inside_entry_zone_repro.py` (5 tests tái hiện)

### BUG-002 — TP2 gần như trùng TP1 (gap < 1 pip)

- **Trạng thái:** ĐÃ FIX (2026-07-03)
- **Mức độ:** Trung bình
- **File:** `core/risk_engine.py:530-531` (BUY), `607-608` (SELL) — guard trong `build_trade_plan`
- **Mô tả:** `next_target()` tìm S/R zone gần nhất `> TP1` nhưng **không có minimum distance check**. Nếu resistance zone nằm sát ngay trên TP1, TP2 được chọn dù chỉ cách TP1 vài pip — vô nghĩa thực tế.

  **Dữ liệu thực tế (AUDNZD):**
  ```
  TP2:       1.21703  ← cách TP1 đúng 0.4 pips!
  TP1:       1.21699
  Entry+:    1.21507
  Current:   1.21502
  Entry-:    1.21479
  SL:        1.21433
  ```
  `next_target(resistance_zones, tp1=1.21699, above=True)` tìm thấy resistance ở 1.21703 — level gần nhất > TP1 — và trả về ngay, không kiểm tra gap. GAP = 0.00004 = 3.3% ATR.

- **Phạm vi ảnh hưởng:** BUY và SELL, khi có 2 S/R zone gần như liền kề nhau. Tần suất thấp nhưng gây ra TP2 vô nghĩa.

- **Fix:** Phương án A — thêm constant `_TP2_MIN_GAP_ATR = 0.15` và guard clause sau khi TP2 được xác định. BUY: `if tp2 is not None and (tp2 - tp1) < atr_value * 0.15 → tp2 = None`. SELL: `if tp2 is not None and (tp1 - tp2) < atr_value * 0.15 → tp2 = None`. Bao phủ cả `next_target` và Fib fallback. TP2 = None an toàn — chỉ là không có target thứ hai, plan vẫn có TP1 hợp lệ.

- **Test:** `tests/test_tp2_min_gap_fix.py` (4 tests) + `tests/test_tp2_too_close_repro.py` (4 tests tái hiện)

---

## Tổng kết

| ID | Mô tả ngắn | Mức độ | Trạng thái |
|----|-----------|--------|------------|
| BUG-001 | TP1 nằm trong entry zone | Nghiêm trọng | ĐÃ FIX |
| BUG-002 | TP2 gần như trùng TP1 | Trung bình | ĐÃ FIX |
