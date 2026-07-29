# Order Management — BE & Trailing Stop

> **Ngày:** 2026-07-08  
> **Trạng thái:** Design — chưa implement  
> **File liên quan:** `ui/screens/orders_screen.py`, `controllers/scanner_controller.py`

## Tổng quan

Hệ thống quản lý lệnh tự động theo dõi tất cả vị thế đang mở trên MT5 và tự động điều chỉnh Stop Loss (SL) theo chiến lược 3 giai đoạn:

1. **BE (Breakeven)** tại 1R — dời SL về entry khi lợi nhuận đạt khoảng cách SL ban đầu
2. **Trail rộng (2.5×ATR)** — sau khi BE, dời SL theo ATR để chạy theo xu hướng
3. **Trail chặt (1.5×ATR)** — khi lợi nhuận đạt 2R, siết chặt SL để khóa lợi nhuận

Hệ thống KHÔNG can thiệp vào Take Profit (TP). TP giữ nguyên như lúc vào lệnh.

## Kiến trúc

```
scanner_controller.py
  │  Sau khi mở lệnh MT5 thành công
  └─► orders_screen.auto_enable_tracking(pos_id, symbol, side, entry, sl, atr)
        │  Tạo config trong _trailing_configs[pos_id]
        │
        ▼
orders_screen.py._trailing_tick()  ← QTimer mỗi 1.5 giây
  │
  ├─ [GIAI ĐOẠN 1] Kiểm tra BE:
  │   - Tính be_trigger_price = entry ± abs(entry - initial_sl)
  │   - Nếu giá vượt be_trigger và be_done=False:
  │     → Gọi modify_position_sltp(sl = entry ± be_plus_pips)
  │     → be_done = True, trail_mode = "wide"
  │
  ├─ [GIAI ĐOẠN 2 & 3] Kiểm tra trailing:
  │   - Nếu profit ≥ 2R: trail_mode → "tight"
  │   - multiplier = 2.5 (wide) hoặc 1.5 (tight)
  │   - trail_price = atr_h1 × multiplier
  │   - SL mới = extreme_price ± trail_price
  │   - CHỈ dời SL nếu SL mới tốt hơn SL hiện tại (không bao giờ lùi)
  │
  └─ Cleanup: xóa config của lệnh đã đóng
```

## Chi tiết chiến lược

### Giai đoạn 1: BE (Breakeven)

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| **Trigger** | Profit ≥ 1R | Giá đã di chuyển đúng bằng khoảng cách SL ban đầu |
| **Hành động** | SL → entry ± 2 pips (BE+) | Cover spread, lệnh không thể lỗ |
| **Số lần dời** | 1 lần duy nhất | Sau BE, không dời SL lùi lại |
| **Công thức** | `be_trigger = entry + abs(entry - sl)` (BUY) | |

**Ví dụ NZD/USD BUY:**
- Entry: 0.60000, SL: 0.59870 (13 pips = 1R)
- Khi giá đạt 0.60130 → trigger BE → SL dời về 0.60020 (entry + 2 pips)
- Lệnh không thể lỗ, tối đa lời 2 pips nếu bị stop ngay

### Giai đoạn 2: Trail rộng (2.5×ATR H1)

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| **Trigger** | Sau khi BE xong | Tự động chuyển từ BE sang trail |
| **Multiplier** | 2.5× | Đủ rộng để không bị noise stop-out |
| **Công thức** | `trail_sl = extreme_price - (2.5 × ATR_H1)` | |
| **Ràng buộc** | SL mới ≥ SL cũ | Không bao giờ dời SL xa giá hơn |

**Ví dụ NZD/USD (ATR H1 = 0.0015 = 15 pips):**
- Trail distance = 2.5 × 0.0015 = 0.00375 (37.5 pips)
- Extreme = 0.60250 → SL mới = 0.60250 - 0.00375 = 0.59875
- Nhưng SL hiện tại đã là 0.60020 (BE+) → giữ nguyên 0.60020
- Extreme = 0.60400 → SL mới = 0.60400 - 0.00375 = 0.60025 → dời lên

### Giai đoạn 3: Trail chặt (1.5×ATR H1)

| Tham số | Giá trị | Mô tả |
|---------|---------|-------|
| **Trigger** | Profit ≥ 2R | Lợi nhuận gấp đôi risk |
| **Multiplier** | 1.5× | Chặt hơn để khóa lợi nhuận |
| **Công thức** | `trail_sl = extreme_price - (1.5 × ATR_H1)` | |

**Ví dụ NZD/USD (profit đạt 2R = 26 pips):**
- Trail distance = 1.5 × 0.0015 = 0.00225 (22.5 pips)
- Extreme = 0.60260 → SL mới = 0.60260 - 0.00225 = 0.60035

## Cấu trúc dữ liệu

### `_position_original_sl` dict (2026-07-17)

```python
_position_original_sl: dict[int, float] = {
    position_id: original_sl,  # SL ban đầu, ghi 1 lần, không bao giờ overwrite
}
```

**Single Source of Truth cho SL gốc.** Được capture lần đầu khi position xuất hiện trong `refresh_orders()`, hoặc khi `auto_enable_tracking()` được gọi từ scanner. Sau khi ghi, không bao giờ bị overwrite.

**Dùng cho:**
- Tính R trong bảng Orders (`_render_position_row`)
- Tính `effective_initial_sl` trong dialog Trailing Stop (`_show_trailing_dialog`)
- Set `initial_sl` khi bật Trailing thủ công (`_handle_enable_trailing`)
- Set `initial_sl` khi auto-enable từ scanner (`auto_enable_tracking`)

**Persist:** Lưu trong `be_trailing_state.json` key `original_sl`.
**Cleanup:** Xóa entry khi position đóng (`_cleanup_trailing`).

### `_trailing_configs` dict

```python
_trailing_configs: dict[int, dict] = {
    position_id: {
        # Fields hiện có
        "symbol": str,
        "side": "buy" | "sell",
        "trail_pips": int,        # giữ lại cho manual mode
        "max_slippage": int,
        "active": bool,
        "extreme_price": float,

        # Fields mới (Task 1)
        "be_done": bool,           # Đã dời BE chưa
        "be_trigger_price": float, # Giá trigger BE
        "entry_price": float,      # Giá entry
        "initial_sl": float,       # SL ban đầu (copy từ _position_original_sl)
        "atr_h1": float,           # ATR(H1) của symbol
        "trail_mode": str,         # "wide" | "tight"
        "pip_multiplier": float,   # 10000 hoặc 100
    }
}
```

## Cấu hình (settings.json)

```json
{
  "order_management": {
    "enabled": true,
    "be_trigger_r": 1.0,
    "be_plus_pips": 2,
    "trail_wide_atr_multiplier": 2.5,
    "trail_tight_atr_multiplier": 1.5,
    "trail_tight_trigger_r": 2.0,
    "poll_interval_seconds": 5,
    "atr_timeframe": "H1"
  }
}
```

## Nguyên tắc bất biến

1. **SL không bao giờ lùi** — SL mới luôn ≥ SL cũ (BUY) hoặc ≤ SL cũ (SELL)
2. **BE chỉ dời 1 lần** cho mỗi lệnh
3. **Trail chỉ chạy sau BE** — không trail trước khi BE
4. **Không can thiệp TP** — TP giữ nguyên
5. **Chỉ quản lý lệnh do hệ thống mở** — bỏ qua lệnh manual
6. **Auto-enable khi vào lệnh từ scanner** — không cần user bật thủ công
7. **R luôn tính từ Initial SL gốc** — `_position_original_sl` ghi 1 lần, không overwrite. BE và Trailing chỉ update `current_sl`, không ảnh hưởng đến R.

## MT5 Integration

- Dùng `modify_position_sltp(pos_id, new_sl, new_tp=None)` để cập nhật SL
- `new_tp=None` → giữ nguyên TP hiện tại
- Polling mỗi 1.5 giây qua QTimer trong `orders_screen.py`
- Timer chạy NGAY CẢ KHI orders_screen tab không active

## UI Hiển thị

Cột "Trailing" trong bảng Orders Screen:

| Trạng thái | Hiển thị | Màu |
|-----------|----------|------|
| Chưa BE | `⏳ Chờ BE (còn X pips)` | Xám |
| Đã BE | `✅ BE` | Xanh lá |
| Trail wide | `🟢 Wide` | Xanh dương |
| Trail tight | `🔒 Tight` | Cam |

## Lộ trình triển khai

| Task | Mô tả | File | Test |
|------|-------|------|------|
| 1 | Thêm fields vào `_trailing_configs` | orders_screen.py | test_be_trailing_task1.py |
| 2 | Implement BE logic | orders_screen.py | test_be_trailing_task2.py |
| 3 | ATR multiplier thay pips cố định | orders_screen.py | test_be_trailing_task3.py |
| 4 | Auto-enable khi scanner mở lệnh | scanner_controller.py + orders_screen.py | test_be_trailing_task4.py |
| 5 | Đồng bộ orders_screen | main_window.py | test_be_trailing_task5.py |
| 6 | UI hiển thị giai đoạn | orders_screen.py | test_be_trailing_task6.py |
| 7 | Integration test | tests/ | test_be_trailing_integration.py |

## So sánh phương án (đã đánh giá)

| Phương án | Ưu | Nhược | Kết luận |
|-----------|-----|--------|----------|
| **ATR Trailing** | Tự thích nghi volatility, code đơn giản, ATR có sẵn | Cần calibrate multiplier | ✅ **CHỌN** |
| Swing HL Trailing | Bám sát cấu trúc giá | Cần module swing detection riêng | 🔮 Tương lai |
| Step Trailing | Đơn giản nhất | Cứng nhắc, không thích nghi | ❌ Loại |
| BE tại 1R | Chuẩn toán học, risk=0 sau confirm | Một số lệnh bị stop rồi đi tiếp | ✅ **CHỌN** |
| BE tại 2R | Ít stop-out sớm | Nhiều lệnh quay đầu lỗ 1.5R | ❌ Quá muộn |
