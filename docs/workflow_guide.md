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
2. Chọn tab **MT5**.
3. Kéo xuống bảng cấu hình mã — mỗi dòng là một cặp:

   | Cột | Ý nghĩa | Cách điền |
   |-----|---------|-----------|
   | Backtest | Bật/tắt | Check ON để kích hoạt cấu hình riêng cho mã này |
   | Decision Ready | Ngưỡng `final_score` để READY | Nhập số (0-100). VD: `70` |
   | Decision Watch | Ngưỡng `final_score` để WATCH | Nhập số (0-100). VD: `55` |
   | Decision Wait | Ngưỡng `final_score` để WAIT | Nhập số (0-100). VD: `40` |
   | Min Score | Ngưỡng chặn cứng (không dùng nữa, để trống) | Giữ 0 |
   | Auto Trade Regime | Lọc theo chế độ thị trường | `range`, `trend_up`, `trend_down`, hoặc để trống |
   | Side | Hướng vào lệnh | `buy`, `sell`, `best`, hoặc để trống |
   | Min RR | Tỷ lệ Reward:Risk tối thiểu | VD: `1.5` |

4. Nhấn **"💾 Lưu cấu hình mã quét"** ở cuối bảng.

### Ví dụ cấu hình

| Mã | Backtest | Ready | Watch | Wait | Regime | Side | Min RR |
|----|----------|-------|-------|------|--------|------|--------|
| USDCHF | ON | 60 | 45 | 35 | | best | 1.5 |
| GBPJPY | ON | 75 | 60 | 50 | | best | 2.0 |
| EURUSD | OFF | 0 | 0 | 0 | | | |

- `backtest = OFF`: mã đó bỏ qua cấu hình riêng, dùng ngưỡng mặc định (ready=80, watch=65, wait=50).
- Các cột `Ready`, `Watch`, `Wait` = 0: tự động dùng ngưỡng mặc định.
- Để trống `Regime` và `Side` nếu muốn hệ thống tự quyết định.

---

## Bước 3: Quét thị trường & Auto Trade

### Quét thủ công (không auto trade)

1. Mở màn hình **Scanner**.
2. Chọn chế độ quét: `Toàn bộ 31 mã`, `Danh sách tùy chọn`, hoặc `Chỉ mã đã bật auto trade`.
3. Đảm bảo nút **"🤖 Tự động vào lệnh MT5"** đang TẮT (màu xám).
4. Nhấn **"Quét thị trường"**.
5. Kết quả hiển thị theo nhóm (do decision engine phân loại dựa trên ngưỡng của từng cặp):
   - **Sẵn sàng** — `final_score >= decision_ready`, entry confirmed, gate cho phép.
   - **Chờ xác nhận** — cần thêm tín hiệu M15 hoặc score chưa đạt ready.
   - **Theo dõi** — đáng chú ý nhưng chưa đạt (`final_score >= decision_watch`).
   - **Bị chặn** — gate chặn (spread, news, account guard, journal feedback).

### Bật Auto Trade

1. Chọn chế độ quét: `Chỉ mã đã bật auto trade` (chỉ quét những mã có `backtest = ON` trong Settings → MT5).
2. Bấm nút **"🤖 Tự động vào lệnh MT5"** — nút chuyển sang màu xanh (đã kích hoạt).
3. Nhấn **"Quét thị trường"**.
4. Hệ thống sẽ:
   - Quét toàn bộ mã đã bật auto trade.
   - Dùng ngưỡng `decision_ready/watch/wait` riêng của từng cặp để phân loại.
   - Kiểm tra regime, side, min_rr.
   - Kiểm tra gate (spread, news, account guard).
   - Nếu tất cả pass → **tự động đặt lệnh Market Order qua MT5** với SL/TP tính sẵn.

Kết quả auto trade hiển thị ở cuối màn hình Scanner: số lệnh đã mở, bị bỏ qua, và lỗi (nếu có).

---

## Tổng kết luồng hoạt động

```
Backtest từng mã
  → Tìm decision_ready/watch/wait có edge (Profit Factor > 1.0)
    → Lưu vào Settings → MT5 (bật backtest, nhập ngưỡng ready/watch/wait)
      → Mở Scanner, bật Auto Trade, quét
        → Hệ thống dùng ngưỡng riêng của từng cặp qua decision engine
          → Tự vào lệnh khi setup đạt READY_TO_TRADE
```

## Lưu ý quan trọng

- **Chạy backtest định kỳ:** Thị trường thay đổi, nên chạy lại backtest mỗi 1-2 tháng để cập nhật ngưỡng `decision_ready/watch/wait` cho phù hợp.
- **Bắt đầu an toàn:** Khi mới dùng auto trade, đặt `decision_ready` cao hơn mức backtest đề xuất 5-10 điểm để thêm biên an toàn.
- **Ngưỡng mặc định:** Nếu không cấu hình riêng cho một cặp, hệ thống dùng mặc định ready=80, watch=65, wait=50.
- **Account Guard:** Hệ thống luôn kiểm tra giới hạn thua lỗ ngày/tuần và số lệnh thua liên tiếp trước khi vào lệnh — bất kể score có đạt hay không.
- **Kiểm tra MT5:** Đảm bảo MT5 desktop đang mở, đã đăng nhập broker, và các mã cần quét có trong Market Watch.
- **Gate vẫn hoạt động:** Decision thresholds chỉ phân loại setup; gate layer (spread, news, M15, RR, account guard) vẫn có quyền chặn cứng bất kỳ setup nào.
