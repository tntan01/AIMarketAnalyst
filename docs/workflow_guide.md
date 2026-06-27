# Hướng dẫn quy trình: Backtest → Cấu hình Ngưỡng → Quét & Auto Trade

Quy trình 3 bước để tối ưu ngưỡng quyết định (decision thresholds) cho từng cặp tiền và bật auto trade.

---

## Bước 1: Backtest để tìm ngưỡng quyết định tối ưu

**Mục tiêu:** Xác định mức `final_score` mà mỗi cặp bắt đầu có edge — tức ngưỡng `decision_ready`, `decision_watch`, `decision_wait` riêng cho từng cặp.

### Thao tác

1. Mở màn hình **Backtest**.
2. Chọn mã cần test (ô "Chọn mã"). Nên test từng mã một để có kết quả rõ ràng.
3. Chọn chế độ phù hợp:
   - `balanced` — mô phỏng sát thực tế nhất (có spread, slippage, gate).
   - `research` — nới lỏng gate để thấy toàn bộ tín hiệu.
4. Nhấn **"Chạy Backtest"** — đợi worker hoàn thành.

### Đọc kết quả

Sau khi chạy xong, xem bảng **Trades** và phần **Tổng quan**:

| Chỉ số | Ý nghĩa |
|--------|---------|
| Win Rate | Tỷ lệ thắng. > 40% là chấp nhận được với RR cao. |
| Profit Factor | Lợi nhuận gộp / thua lỗ gộp. > 1.2 là ổn, > 1.5 là tốt. |
| Expectancy (R) | Kỳ vọng trung bình mỗi lệnh tính theo R. Phải > 0. |
| Max Drawdown | Mức sụt giảm tối đa. < 10% là an toàn. |

Lọc theo cột `final_score` trong bảng trades:
- Tập trung vào nhóm lệnh có `final_score` cao (≥ 50, ≥ 60, ≥ 70...).
- Tìm ngưỡng thấp nhất mà tại đó tập lệnh vẫn có Profit Factor > 1.0 và Expectancy dương.
- **Ví dụ:** USDCHF có thể `decision_ready = 60` là đủ, trong khi GBPJPY cần `decision_ready = 75`.

Ba mức ngưỡng cần xác định cho mỗi cặp:

| Ngưỡng | Ý nghĩa | Cách xác định |
|--------|---------|---------------|
| `decision_ready` | Score ≥ mức này → READY_TO_TRADE (sẵn sàng vào lệnh) | Ngưỡng thấp nhất có Profit Factor > 1.2 |
| `decision_watch` | Score ≥ mức này → WATCH_ONLY (theo dõi) | Ngưỡng thấp nhất có Win Rate > 35% |
| `decision_wait` | Score ≥ mức này → WAITING_CONFIRMATION (chờ thêm) | Ngưỡng có Expectancy dương |

---

## Bước 2: Cấu hình ngưỡng quyết định trong Settings → MT5

Sau khi đã có ngưỡng cho từng cặp từ backtest, lưu vào cấu hình.

### Thao tác

1. Mở màn hình **Settings**.
2. Chọn tab **Dữ liệu**.
3. Kéo xuống bảng cấu hình mã — mỗi dòng là một cặp:

   | Cột | Ý nghĩa | Cách điền |
   |-----|---------|-----------|
   | Kiểm thử | Bật/tắt cấu hình riêng (Nhánh B) | Check ON để kích hoạt auto-trade cho mã này |
   | Điểm tối thiểu | Ghi đè ngưỡng Ready | Chỉ nhập khi Kiểm thử=ON. Rỗng = dùng Ready mặc định |
   | Regime tự động | Lọc theo chế độ thị trường | `range`, `trend_up`, `trend_down`, `volatile`, hoặc để trống |
   | Hướng tự động | Hướng vào lệnh | `buy`, `sell`, `best` |
   | RR tối thiểu | Tỷ lệ effective R:R tối thiểu | VD: `1.5`. Mặc định 1.3 |
   | **Ready** | Score ≥ mức này → READY_TO_TRADE | **Mặc định 65**. Áp dụng cho cả Nhánh A và B |
   | **Watch** | Score ≥ mức này → WATCH_ONLY | **Mặc định 60**. Áp dụng cho cả Nhánh A và B |
   | **Wait** | Score ≥ mức này → WAITING_CONFIRMATION | **Mặc định 55**. Áp dụng cho cả Nhánh A và B |

4. Nhấn **"💾 Lưu cấu hình mã quét"** ở cuối bảng.

### Ví dụ cấu hình

| Mã | Kiểm thử | Điểm tối thiểu | Regime | Hướng | RR tối thiểu | Ready | Watch | Wait |
|----|----------|---------------|--------|-------|-------------|-------|-------|------|
| USDCHF | ON | 60 | | best | 1.5 | 65 | 60 | 55 |
| GBPJPY | ON | 75 | | best | 2.0 | 65 | 60 | 55 |
| EURUSD | OFF | (rỗng) | | | 1.3 | 65 | 60 | 55 |

- **Nhánh A (Kiểm thử = OFF):** Điểm tối thiểu để trống, disabled. Hệ thống dùng Ready/Watch/Wait (65/60/55) làm ngưỡng. Chỉ auto-trade khi pipeline ra `scanner_action == "ready"`.
- **Nhánh B (Kiểm thử = ON):** Điểm tối thiểu ghi đè Ready khi > 0. Dùng bộ lọc regime/side/RR từ backtest. Có cơ chế override `stand_aside` → `ready` nếu khớp điều kiện. Auto-trade không cần `scanner_action == "ready"`.
- Để trống `Regime` và `Side` nếu muốn hệ thống tự quyết định.

---

## Bước 3: Quét thị trường & Auto Trade

### Quét thủ công (không auto trade)

1. Mở màn hình **Scanner**.
2. Chọn chế độ quét: `Toàn bộ 31 mã`, `Danh sách tùy chọn`, hoặc `Chỉ mã đã bật auto trade`.
3. Đảm bảo nút **"🤖 Tự động vào lệnh MT5"** đang TẮT (màu xám).
4. Nhấn **"Quét thị trường"**.
5. Kết quả hiển thị theo nhóm (do decision engine phân loại dựa trên ngưỡng của từng cặp):
   - **Sẵn sàng** — `final_score >= ready`, entry confirmed, gate cho phép.
   - **Chờ xác nhận** — cần thêm tín hiệu M15 hoặc score chưa đạt ready.
   - **Theo dõi** — đáng chú ý nhưng chưa đạt (`final_score >= watch`).
   - **Bị chặn** — gate chặn (spread, news, account guard, journal feedback).

### Bật Auto Trade

1. Chọn chế độ quét: `Chỉ mã đã bật auto trade` (chỉ quét những mã có `Kiểm thử = ON` trong Settings > Dữ liệu).
2. Bấm nút **"🤖 Tự động vào lệnh MT5"** — nút chuyển sang màu xanh (đã kích hoạt).
3. Nhấn **"Quét thị trường"**.
4. Hệ thống sẽ:
   - Quét toàn bộ mã đã bật auto trade.
   - **Nhánh B:** Dùng bộ lọc regime/side/RR từ Settings. Không cần `scanner_action == "ready"`, chỉ cần vượt bộ lọc backtest.
   - **Nhánh A:** Yêu cầu `scanner_action == "ready"` (pipeline phải ra READY_TO_TRADE).
   - Kiểm tra gate (spread, news, account guard).
   - Nếu tất cả pass → **tự động đặt lệnh Market Order qua MT5** với SL/TP tính sẵn.

Kết quả auto trade hiển thị ở cuối màn hình Scanner: số lệnh đã mở, bị bỏ qua, và lỗi (nếu có).

---

## Tổng kết luồng hoạt động

```
Cấu hình Settings > Dữ liệu cho từng cặp:
  Ready=65, Watch=60, Wait=55 (mặc định cho mọi cặp)
  Kiểm thử=ON + filter (regime/side/min_rr/min_score) cho cặp đã backtest
    │
    ▼
  Mở Scanner, chọn chế độ quét
    │
    ▼
  Pipeline (mọi cặp):
    Lớp 1: Chấm điểm SMC/kỹ thuật/vĩ mô → best_score, best_side
    Lớp 2: 11 gate kiểm tra an toàn
    Decision Engine: score + gate + entry → READY_TO_TRADE / WATCH / WAIT / STAND_ASIDE
    │
    ▼
  Controller (mỗi cặp):
    _apply_symbol_override: Nhánh B nâng stand_aside → ready nếu khớp backtest
    _is_auto_trade_candidate:
      Nhánh A → cần scanner_action == "ready"
      Nhánh B → chỉ cần vượt bộ lọc backtest
    → Đặt lệnh Market Order nếu pass
```

## Lưu ý quan trọng

- **Ngưỡng mặc định:** Ready=65, Watch=60, Wait=55. Áp dụng cho mọi cặp, có thể chỉnh riêng trong Settings > Dữ liệu.
- **Nhánh A (không backtest):** Chỉ auto-trade khi pipeline tự tin (READY_TO_TRADE). An toàn, conservative.
- **Nhánh B (có backtest):** Auto-trade theo điều kiện đã được chứng minh bởi dữ liệu lịch sử. Có thể vào lệnh ngay cả khi pipeline chưa ra READY.
- **Chạy backtest định kỳ:** Thị trường thay đổi, nên chạy lại backtest mỗi 1-2 tháng để cập nhật bộ lọc cho phù hợp.
- **Account Guard:** Hệ thống luôn kiểm tra giới hạn thua lỗ ngày/tuần và số lệnh thua liên tiếp trước khi vào lệnh — bất kể score có đạt hay không.
- **Kiểm tra MT5:** Đảm bảo MT5 desktop đang mở, đã đăng nhập broker, và các mã cần quét có trong Market Watch.
- **Gate vẫn hoạt động:** Decision thresholds chỉ phân loại setup; gate layer (spread, news, M15, RR, account guard) vẫn có quyền chặn cứng bất kỳ setup nào.
