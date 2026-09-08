# SD Acceptance Criteria

> Trạng thái: `DRAFT` — tiêu chí kiểm tra, chưa xác nhận code/test đã đạt.
> Phạm vi: phân tích và cảnh báo SD trên máy cá nhân, MT5 chỉ đọc.

## 1. Cách sử dụng

Dùng dữ liệu mẫu/giả lập để kiểm tra logic; thao tác trực tiếp để kiểm tra UI.
Mỗi lần kiểm tra ghi đầu vào/cấu hình, kết quả thực tế và **Đạt / Chưa đạt /
Chưa kiểm tra**. Không yêu cầu backtest, forward demo, lịch sử test hoặc
benchmark có sẵn. Lịch sử nến đủ cho thuật toán vẫn là điều kiện bắt buộc.

Phạm vi theo [01](01-scope-and-requirements.md), công thức theo
[02](02-trading-rules.md), kỹ thuật theo [03](03-technical-design.md), giao
diện theo [04](04-ui-and-alerts.md). Tài liệu này không bổ sung quy tắc mới.

## 2. Các kiểm tra chính

| Mã | Tình huống | Kết quả mong đợi |
|---|---|---|
| AC-01 | Thiếu nến/quote/ATR, sai OHLC, dữ liệu quá cũ hoặc chưa rõ biên nến broker | Không READY; có lý do theo symbol/timeframe. Nghỉ phiên không bị coi nhầm là gap/stale. |
| AC-02 | Chạy detector với bốn mẫu và mẫu không hợp lệ | RBR/DBR tạo Demand, RBD/DBD tạo Supply; biên/khử trùng đúng `02`. Không dùng nến chưa đóng hoặc dữ liệu tương lai. |
| AC-03 | H4/H1 kết thúc retest đầu; D1 kết thúc nhiều retest | H4/H1 hết hạn; D1 về TESTED và còn dùng nếu chưa broken/quá tuổi. Trạng thái cuối không hồi sinh. |
| AC-04 | H4 liên kết D1; H1 thiếu H4 cha; D1 mất hiệu lực | Đồng thuận đúng điều kiện `02`; H1 thiếu H4 cha không READY. D1 mất hiệu lực không tự vô hiệu H4. |
| AC-05 | Chấm điểm và đổi cấu hình base | Điểm thành phần/grade đúng `02`; D1 độc lập chỉ điểm hình thành /50. Base 5–10 nến bị từ chối, không clamp. |
| AC-06 | Có cản H4/D1, Entry trong cản, giá sát biên tick | TP chọn đúng cản; Entry trong cản chặn READY. Rounding trước risk/R:R/grade; RR 1.9996 không đạt ngưỡng 2.0. Thiếu TP không dựng giá giả. |
| AC-07 | Source chạm nhưng entry chưa chạm; entry đã chạm rồi giá rời | READY cần entry latch; latch giữ trong cùng first retest. Tick mili giây và nến M15 fallback được gắn đúng mốc. |
| AC-08 | A -> B -> A; mode M15 timeout; TOUCH hết cửa sổ | ID/latch/cửa sổ không reset. TOUCH không tự timeout vì thiếu M15; M15 timeout không được grade tăng hồi sinh. |
| AC-09 | Các gate READY đạt/không đạt và có conflict | Chỉ READY khi đủ mọi gate; tối đa một READY/symbol. Mất điều kiện thì cập nhật đúng state/lý do và ưu tiên terminal. |
| AC-10 | READY mới, quét lặp, READY -> WATCHING -> READY | Một sự kiện cho cùng alert key. Inbox luôn lưu sau commit; popup/âm thanh theo cài đặt, không phát lại khi reload/restart. |
| AC-11 | Restart, touch cũ, config đổi hoặc thiếu evidence | Replay đủ lịch sử/evidence, giữ terminal và ID; thiếu đầu vào giữ FULL_ANALYSIS_PENDING. Không lấy snapshot state làm sự thật. |
| AC-12 | Kết thúc restore; crash trước/sau commit | Không cảnh báo khi replay. Hiện READY an toàn và chưa key thì ghi RESTORE_CURRENT; không phát bù cơ hội đã hết. Commit lỗi không popup; key đã lưu không nhân đôi. |
| AC-13 | Mở ứng dụng, Start/Stop/Refresh, đổi màn hình/config | Khởi động IDLE, dùng watchlist đã lưu hoặc bốn mã mặc định. Không job chồng; Stop vẫn phản hồi khi chờ I/O; generation cũ không ghi đè/phát mới. |
| AC-14 | Xem bảng/chart/detail/inbox, dữ liệu thiếu hoặc kết quả cũ | Giá/vùng/mode/điểm khớp core; None khác 0; kết quả cũ có nhãn thời điểm. Payload cảnh báo lịch sử không bị plan mới ghi đè. Kiểm tra UI chi tiết theo SD-UI-01–19 của `04`. |
| AC-15 | Kiểm tra các đường gọi MT5 và dependency | Không gửi/sửa/đóng/hủy lệnh, không tự đổi Market Watch; SD không lấy quyết định từ Scanner/SMC/engine cũ. |
| AC-16 | Kiểm tra riêng 1366 × 768 scale 100% và Full HD 1920 × 1080 scale 150%, dark/light | SD-NFR-11: UI chạy tốt, xem đủ dữ liệu/thao tác theo mục 2.1 bên dưới; controls, dialog và popup không bị cắt; không buộc giảm scale/fullscreen/ẩn taskbar. Truy vết SD-UI-18 của `04`. |
| AC-17 | Resize/đổi scale, mở lại geometry cũ, đang nhập form và đang phân tích | Layout/nhãn/vùng bấm cập nhật đúng; cửa sổ/dialog còn trong vùng khả dụng, giữ selection và dữ liệu nhập; worker tiếp tục, state/ID/alert không thay vì layout. Truy vết SD-UI-19 của `04`, SD-NFR-11. |

### 2.1 Cách kiểm tra màn hình tối thiểu — AC-16/17

Thực hiện riêng ở **1366 × 768/100%** và **1920 × 1080/150%** với taskbar
hiện, cửa sổ ứng dụng maximized và shell/điều hướng đầy đủ. Full HD ở 150%
chỉ còn khoảng **1280 × 720 đơn vị logic** trước khi trừ taskbar/khung cửa sổ;
không thay phép kiểm tra này bằng ảnh/viewport 1920 × 1080 ở scale 100%.

1. Dùng dữ liệu mẫu có nhiều dòng, số giá dài, đủ điểm thành phần, bối cảnh D1,
   lý do nhiều dòng, dữ liệu thiếu/lỗi và inbox có nội dung dài; kiểm tra cả
   dark/light. Không cần lịch sử test hoặc giao dịch thực tế.
2. Mở watchlist, chọn setup và các tab chart/detail, chuyển D1/H4/H1/M15,
   cuộn bảng/form và mở inbox. Mọi trường bắt buộc phải đọc được đầy đủ;
   tab/panel thu gọn/cuộn là hợp lệ, ẩn mất dữ liệu hoặc cắt chữ số là lỗi.
3. Kiểm tra Start/Stop/Refresh, trạng thái và lối mở cấu hình/inbox. Mở editor
   watchlist, cấu hình/session, lỗi validation, detail cảnh báo và popup.
   Không tràn vùng làm việc; nút đóng/Áp dụng/Hủy dùng được bằng chuột và
   bàn phím, không cần kéo cửa sổ vượt màn hình để tìm controls.
4. Khi chạy phân tích nền, thao tác UI vẫn phản hồi theo SD-NFR-06. Resize/
   đổi scale và khôi phục geometry đã lưu không mất form/selection, không
   chồng chữ/sai vùng bấm, không dừng worker hoặc phát lại alert.

Ghi độ phân giải, scale, theme, vùng client thực tế, kết quả và lỗi quan sát
cho từng cấu hình. Chưa chạy cấu hình nào thì ghi **Chưa kiểm tra** cấu hình
đó; không suy ra đạt cả hai từ một màn hình. Không đặt số lượt hoặc benchmark
hiệu năng; ảnh chụp có thể dùng để ghi nhận lỗi bố cục khi kiểm tra.

## 3. Ghi nhận hoàn thành

- Kiểm tra phần nào khi triển khai phần đó; không đánh dấu đạt nếu chưa chạy.
- Lỗi giá, state, restore, chống lặp hoặc quyền MT5 phải được sửa và kiểm tra
  lại trước khi dùng phần chức năng liên quan.
- Xác minh lịch biên broker thực tế khi tích hợp; chưa đủ thì chặn READY của
  symbol liên quan, không đoán dữ liệu để vượt kiểm tra.
- Lỗi cắt nội dung/nút, dialog ngoài màn hình hoặc không thao tác được ở một
  trong hai cấu hình tối thiểu là chưa đạt SD-NFR-11; sửa và kiểm tra lại UI
  liên quan. Việc cập nhật đặc tả không đồng nghĩa UI đã được kiểm tra thực tế.
- PO chốt rules `APPROVED` trước khi bật runtime. Hoàn thành kiểm tra không
  đồng nghĩa chứng minh lợi nhuận hoặc chứng nhận sản phẩm thương mại.
