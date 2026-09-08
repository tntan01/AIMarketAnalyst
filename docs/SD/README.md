# Supply–Demand Trading (SD)

## 1. Mục đích

`SD` là tính năng phân tích giao dịch theo vùng cung–cầu dành cho nhu cầu sử
dụng cá nhân trong AI Market Analyst.

Tính năng đọc dữ liệu thị trường, phát hiện và theo dõi vùng Supply/Demand,
phân tích đa khung thời gian, xây dựng kế hoạch giao dịch tham khảo và cảnh báo
khi một thiết lập đáp ứng điều kiện vào lệnh.

`SD` là một miền nghiệp vụ độc lập. Kết quả của tính năng không phụ thuộc vào
SMC, Scanner, Strategy Router, Decision Engine, Risk Engine hoặc Backtest hiện
có của ứng dụng.

## 2. Phạm vi hiện tại

Phiên bản đầu tiên gồm:

- đọc dữ liệu OHLC của các khung D1, H4, H1 và M15;
- phát hiện các mẫu RBR, DBR, RBD và DBD;
- xác định biên proximal, distal và vùng vào lệnh;
- đánh giá chất lượng và vòng đời của vùng;
- phân tích quan hệ giữa vùng khung lớn và khung nhỏ;
- tạo kế hoạch gồm hướng giao dịch, Entry, Stop Loss, Take Profit và R:R;
- hiển thị vùng và kết quả phân tích trên màn hình riêng;
- UI dùng tốt và xem đầy đủ thông tin/thao tác trên cả màn hình 1366 × 768
  scale 100% và Full HD 1920 × 1080 scale 150%, theo `01` SD-NFR-11;
- theo dõi thiết lập và phát cảnh báo khi thiết lập chuyển sang trạng thái
  `READY`;
- lưu cấu hình và trạng thái cần thiết trên máy cá nhân.

Yêu cầu màn hình áp dụng trong vùng làm việc thực tế với taskbar và shell
ứng dụng; Full HD ở scale 150% có khoảng 1280 × 720 đơn vị logic trước khi
trừ các phần này. Cho phép tab/thu gọn/cuộn để xem đủ nội dung, không cắt mất
nút hoặc buộc giảm scale. Thiết kế theo `03` mục 12 và `04` mục 2.1, kiểm tra
riêng cả hai cấu hình theo `05` AC-16/17 khi triển khai trên máy cá nhân.

Định hướng PO đã được người dùng đồng ý lưu ngày 08/09/2026:

- **D1:** vùng cung–cầu lớn để đánh giá bối cảnh và vùng cản đối diện.
- **H4:** tìm setup trong bối cảnh D1.
- **H1:** xác định vùng vào lệnh chi tiết.
- **M15:** xác nhận phản ứng giá khi cần.

Chi tiết và ví dụ được lưu ở
[`01-scope-and-requirements.md`](01-scope-and-requirements.md), mục 3.3–3.4.
[`02-trading-rules.md`](02-trading-rules.md) đã đồng bộ quyết định TL-PO-01–09
từ mục 14 của `03`: D1 nhiều retest/TESTED, cản D1/H4, giá sau rounding,
mode không đổi ID, entry latch, evidence restore và watchlist/alert cá nhân.
Mục 11 giữ thang setup 100 điểm; D1 độc lập chỉ có formation score /50.
Lịch biên broker thực tế còn cần xác minh khi triển khai. Đồng bộ quyết định
không đồng nghĩa các quy tắc đã chuyển sang `APPROVED` hoặc đã có trong runtime.

## 3. Ngoài phạm vi hiện tại

Phiên bản đầu tiên không thực hiện:

- tự động, bán tự động hoặc thủ công gửi lệnh tới MT5;
- sửa, đóng hoặc hủy lệnh và vị thế;
- backtest OOS;
- forward demo;
- tối ưu tham số tự động;
- quản lý nhiều người dùng, phân quyền hoặc đồng bộ đám mây;
- tái sử dụng quyết định hoặc điểm số từ các chiến lược hiện có.

Mọi kết nối MT5 trong phạm vi SD phải ở chế độ chỉ đọc. Việc bổ sung khả năng
gửi lệnh trong tương lai cần được phê duyệt như một phạm vi riêng.

## 4. Nguyên tắc kiến trúc

SD tuân theo kiến trúc phân lớp hiện có của dự án:

- `core/`: model và logic nghiệp vụ thuần Python;
- `services/`: truy cập dữ liệu, lưu trạng thái và phát cảnh báo;
- `controllers/`: điều phối giữa UI, worker và service;
- `workers/`: thực hiện phân tích nền, không chặn UI thread;
- `ui/`: màn hình và thành phần trình bày;
- `config/`: cấu hình mặc định;
- `tests/`: kiểm thử tự động.

Các file mới nằm trực tiếp trong những thư mục trên và dùng tiền tố
`supply_demand_`, ví dụ:

```text
core/supply_demand_zone_detector.py
services/supply_demand_service.py
controllers/supply_demand_controller.py
workers/supply_demand_worker.py
ui/screens/supply_demand_screen.py
tests/test_supply_demand_zone_detector.py
```

Không tạo một kiến trúc feature-first riêng và không đưa logic SD vào các file
`smc_*`, `scanner_*` hoặc các engine giao dịch cũ.

SD chỉ được dùng chung hạ tầng trung tính khi cần thiết, chẳng hạn kết nối MT5
và nguồn nến. Adapter của SD phải chuyển dữ liệu dùng chung thành contract riêng
trước khi đưa vào logic nghiệp vụ.

## 5. Luồng xử lý

```text
Dữ liệu OHLC và giá hiện tại
    -> phát hiện base, departure và mẫu hình
    -> tạo vùng Supply/Demand
    -> cập nhật vòng đời vùng
    -> đánh giá chất lượng và đa khung thời gian
    -> chọn thiết lập phù hợp
    -> tạo Entry, SL, TP và R:R
    -> cập nhật trạng thái thiết lập
    -> hiển thị và cảnh báo khi READY
```

Các trạng thái chính của thiết lập:

```text
DETECTED -> WATCHING -> READY
                    |-> INVALIDATED
                    `-> EXPIRED
```

Cảnh báo phải gắn với lần chuyển trạng thái, có định danh ổn định và không được
phát lặp lại ở mỗi chu kỳ quét cho cùng một sự kiện.

## 6. Bộ tài liệu chuẩn

Đọc tài liệu theo thứ tự sau:

1. [`01-scope-and-requirements.md`](01-scope-and-requirements.md): phạm vi,
   yêu cầu chức năng và yêu cầu phi chức năng.
2. [`02-trading-rules.md`](02-trading-rules.md): quy tắc giao dịch có thể lập
   trình và điều kiện `READY`.
3. [`03-technical-design.md`](03-technical-design.md): kiến trúc module, model,
   contract dữ liệu và điểm tích hợp.
4. [`04-ui-and-alerts.md`](04-ui-and-alerts.md): hành vi giao diện, biểu đồ và
   cảnh báo.
5. [`05-acceptance-criteria.md`](05-acceptance-criteria.md): tiêu chí nghiệm thu
   và các trường hợp kiểm thử bắt buộc.
6. [`06-implementation-plan.md`](06-implementation-plan.md): kế hoạch cho
   coder gồm 172 bước đánh số tăng dần, đầu ra và cách kiểm tra từng bước;
   không thay thế phạm vi/quy tắc trong tài liệu 01–05.

Video, bài viết và biểu đồ bên ngoài chỉ là nguồn tham khảo để xây dựng quy tắc.
Coder không được diễn giải trực tiếp nguồn tham khảo trong lúc triển khai hoặc
tự bổ sung quy tắc chưa được ghi trong bộ tài liệu này.

## 7. Thứ tự ưu tiên khi triển khai

- Phạm vi và điều kiện ngoài phạm vi được xác định trong
  `01-scope-and-requirements.md`.
- Hành vi nghiệp vụ được xác định trong `02-trading-rules.md`.
- Cấu trúc code và contract được xác định trong `03-technical-design.md`.
- Hành vi trình bày được xác định trong `04-ui-and-alerts.md`.
- Kết quả mong đợi được xác nhận bằng `05-acceptance-criteria.md` và fixture
  tương ứng.

Nếu tài liệu, fixture và code mâu thuẫn, không được tự chọn một cách hiểu. Cần
cập nhật và chốt lại nguồn chuẩn trước khi tiếp tục triển khai.

## 8. Nguyên tắc phát triển

- Logic phát hiện và đánh giá vùng phải xác định, có thể kiểm thử và không phụ
  thuộc UI hoặc AI.
- Không sử dụng nến tương lai để xác nhận vùng hoặc thiết lập.
- Mọi ngưỡng phải có tên, đơn vị, giá trị mặc định và giới hạn hợp lệ.
- Kết quả phải kèm lý do chọn, loại hoặc thay đổi trạng thái.
- Dữ liệu thiếu, lỗi hoặc quá cũ không được tạo trạng thái `READY`.
- Thay đổi thuật toán phải có test và cập nhật tài liệu liên quan.
- Tính năng phục vụ cá nhân nhưng vẫn phải ưu tiên tính đúng đắn, khả năng truy
  nguyên và an toàn dữ liệu.

## 9. Trạng thái dự án

Hiện tại SD đang ở giai đoạn đặc tả. Chưa có mã nguồn nghiệp vụ và chưa được kết
nối vào runtime của AI Market Analyst.
