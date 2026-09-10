# Hướng dẫn sử dụng AIMarketAnalyst

## Mục lục

1. [Introduction (Giới thiệu)](#1-introduction-giới-thiệu)
2. [Setup & Launch (Cài đặt và khởi chạy)](#2-setup--launch-cài-đặt-và-khởi-chạy)
3. [Scanner (Bộ quét)](#3-scanner-bộ-quét)
4. [Journal (Nhật ký)](#4-journal-nhật-ký)
5. [Auto-trade (Giao dịch tự động)](#5-auto-trade-giao-dịch-tự-động)
6. [Diagnostics (Chẩn đoán)](#6-diagnostics-chẩn-đoán)
7. [Settings (Cài đặt)](#7-settings-cài-đặt)
8. [Troubleshooting (Khắc phục sự cố)](#8-troubleshooting-khắc-phục-sự-cố)

## 1. Introduction (Giới thiệu)

(Đang cập nhật)

## 2. Setup & Launch (Cài đặt và khởi chạy)

(Đang cập nhật)

## 3. Scanner (Bộ quét)

(Đang cập nhật)

> Ứng dụng hiện chạy Scanner. Đây là thiết kế đã được phê duyệt và là hành vi
> runtime hiện hành. Location đã được nối sau H01/H02 và R5 đã được Tech Lead duyệt ngày 10/09/2026;
> xem
> [`scanner-architecture.md`](../scanner/scanner-architecture.md).

### 3.1 Location nâng cấp — đã nối runtime, R5 đã duyệt

**Trạng thái 10/09/2026: runtime đã nối, Tech Lead đã duyệt R5 sau review lại.**
Chi tiết tại [plan Location](../plans/location-scoring-upgrade-plan.md).

Location cho biết giá close H1 có gần vùng H4 hỗ trợ hướng giao dịch
và còn khoảng trống tới vùng cản hay không. Trong chi tiết Scanner, người dùng
sẽ xem điểm 0–25, phần đóng góp vào điểm kỹ thuật, vùng tham chiếu, khoảng cách
theo ATR và lý do chấm điểm.

- Điểm thấp/0 có thể do không có vùng phù hợp, giá xa vùng hoặc đang ở vùng
  cản. “Không đủ dữ liệu” là trạng thái khác, không phải điểm 0.
- Điểm cao chỉ phản ánh vị trí theo dữ liệu đang xét; vẫn cần xem Momentum,
  Trend, SMC, macro/safety và plan entry/SL/TP. Close H1 có thể khác giá entry.
- Điểm kỹ thuật, hướng ưu tiên và thứ hạng có thể đổi sau nâng cấp. Tính năng
  không tự đóng lệnh đang mở hoặc sửa SL/TP, và không bảo đảm lợi nhuận.
- Bản lưu cũ giữ nguyên điểm. Nếu chưa có detail Location, giao diện sẽ báo
  rõ thay vì tính lại lịch sử bằng công thức mới.
- Bản runtime hiện chưa được nghiệm thu bằng smoke production; smoke hiện có
  chỉ intent-only, không gửi lệnh thật và không thay thế review R5.

Không cần nhập vùng hoặc tin thủ công để sử dụng Location bản đầu; không cần
đăng ký nguồn dữ liệu trả phí hay cài database mới riêng cho phần này.

## 4. Journal (Nhật ký)

Journal lưu analysis payload và correlation adjustment tổng hợp. Với VIX theo
pair, có thể so sánh outcome theo symbol/side/regime để phát hiện drift ở mức
tổng quát, nhưng phiên bản hiện tại chưa hiển thị riêng map version, factor,
direction hoặc chính xác bao nhiêu điểm đến từ VIX modulation.

## 5. Auto-trade (Giao dịch tự động)

(Đang cập nhật)

## 6. Diagnostics (Chẩn đoán)

(Đang cập nhật)

## 7. Settings (Cài đặt)

### VIX theo độ nhạy từng cặp tiền

Mở **Cài đặt → Nâng cao** và tìm checkbox:

> VIX theo độ nhạy từng cặp tiền (Bước 7 — cần dữ liệu hiệu chuẩn cặp)

Checkbox mặc định tắt. Khi tắt, VIX dùng penalty phẳng như trước. Khi bật, ứng
dụng chỉ điều chỉnh theo pair nếu loader tìm được map độ nhạy đủ điều kiện, còn
TTL và pair đó `actionable=true`. Candidate seed/stale/lỗi bị bỏ qua để thử
bundled fallback; chỉ khi không còn eligible candidate hoặc pair neutral mới
giữ penalty phẳng.

Trước khi bật:

1. chạy và review calibration theo
   [`macro_score_architecture.md`](../macro/macro_score_architecture.md), mục
   **Bước 7 — VIX Pair Sensitivity**;
2. kiểm tra window, sample overlap, p-value, factor, Yahoo ticker/proxy và mọi
   warning;
3. xác nhận người chịu trách nhiệm chấp nhận giới hạn thống kê;
4. lưu Settings và đợi tối đa khoảng 60 giây hoặc sang chu kỳ scan tiếp theo để
   cache advanced flags được refresh.

Runner hiện có trong source checkout, không nằm trong packaged UI. Nếu chỉ có
bản `.exe` mà không có quy trình calibration do operator cung cấp, giữ checkbox
OFF.

Snapshot ngày 09/08/2026 không xác nhận JPY là safe haven trong sample: cả 7
JPY pairs và AUD/NZD đều neutral; chỉ BTC/USD, XAG/USD và XAU/USD actionable
theo raw gate. Vì vậy bật flag hiện tại không làm JPY pairs được giảm phạt.

## 8. Troubleshooting (Khắc phục sự cố)

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Đã bật VIX theo pair nhưng điểm không đổi | Cache flag chưa refresh; loader không tìm được eligible candidate; symbol non-actionable; hoặc VIX không có base penalty âm | Đợi tối đa 60 giây, kiểm tra runbook/log, map source/expiry và mức VIX; không cố sửa map bằng tay |
| JPY vẫn bị phạt như các pair khác khi VIX cao | Bản đồ độ nhạy VIX hiện tại không xác nhận direction của JPY pair | Đây là fail-safe đúng; không hardcode JPY. Giữ flat hoặc chạy lại calibration trên regime đã phê duyệt |
| Runner báo `hypothesis_not_confirmed` | Đủ dữ liệu nhưng không pair nào qua effect/significance gate | Giữ flag OFF. Runner hiện để map cũ nguyên trạng, vì vậy không coi map cũ là tiếp tục được phê duyệt |
| Bản cài đặt không có nút chạy lại VIX calibration | Runner chưa được bundle vào packaged app | Operator phải chạy từ source checkout; người dùng packaged app giữ feature OFF |
| Checkbox bật nhưng APPDATA map stale | UI chưa hiển thị source/age/reason; loader có thể dùng bundled fallback thay vì flat | Tắt flag, kiểm tra log để xác định map thực sự được dùng, chạy re-validation và review report trước khi bật lại |
