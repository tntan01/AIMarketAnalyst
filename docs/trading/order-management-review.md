# Rà soát tính năng quản lý lệnh

- Ngày rà soát: 09/08/2026
- Phạm vi: màn hình Orders, BE/Trailing Stop, đóng vị thế, lệnh chờ, tích hợp Scanner và MT5
- Trạng thái tài liệu: báo cáo review; không phải runtime contract
- Phương pháp: đọc mã nguồn, đối chiếu tài liệu thiết kế, chạy test và tái hiện trực tiếp các nhánh rủi ro

## Kết luận

Tính năng hiện phù hợp để theo dõi hoặc chạy demo, nhưng **chưa đủ an toàn để dùng như lớp bảo vệ đáng tin cậy trên tài khoản live**.

Rủi ro lớn nhất nằm ở chính engine BE/Trailing: có nhiều trường hợp giao diện và state nội bộ cho rằng vị thế đang được bảo vệ trong khi broker chưa nhận SL, tracking đã bị xóa, hoặc engine không lấy được tick đúng. Khuyến nghị chưa bật auto BE/Trailing trên tài khoản live cho đến khi hoàn tất các mục P0 trong báo cáo này.

## P0 — Cần sửa trước khi dùng live

### 1. Lỗi MT5 tạm thời có thể xóa toàn bộ trailing state

`MT5Service.get_open_positions()` chuyển cả `positions_get() is None`, lỗi import và exception thành danh sách rỗng:

- `services/mt5_service.py:1373-1403`

Orders Screen coi danh sách rỗng là snapshot xác nhận không còn vị thế, sau đó xóa toàn bộ trailing config và original SL:

- `ui/screens/orders_screen.py:276-287`
- `ui/screens/orders_screen.py:526-536`

Hậu quả: vị thế có thể vẫn mở trên broker nhưng mất quản lý BE/Trailing mà người dùng không được cảnh báo. Trạng thái đã xóa còn có thể được ghi đè xuống file persistence.

### 2. State machine chạy trailing trước BE và ghi nhận BE thành công giả

Khi chưa đạt `be_trigger_price`, code không dừng tick mà tiếp tục rơi xuống logic trailing:

- `ui/screens/orders_screen.py:563-643`

Điều này trái với invariant trong `docs/ui/screen_design.md:1333-1343`: trailing chỉ được chạy sau khi BE hoàn tất.

Khi broker từ chối `modify_position_sltp()`, `current_sl` chỉ được cập nhật khi thành công nhưng `be_done` vẫn luôn được đặt thành `True`:

- `ui/screens/orders_screen.py:576-585`

Từ tick tiếp theo hệ thống không retry BE và có thể hiển thị trạng thái Wide/Tight dù SL chưa từng được dời về hòa vốn.

Hai hành vi đã được tái hiện bằng cách gọi trực tiếp production `_trailing_tick()` với MT5 stub:

- Giá BUY chưa đạt BE vẫn phát sinh yêu cầu sửa SL.
- Broker trả `success=False` nhưng `be_done` sau tick vẫn là `True`.

### 3. Engine dùng sai phía giá để kích hoạt BE/Trailing

Engine dùng Ask cho BUY và Bid cho SELL:

- `ui/screens/orders_screen.py:554-559`
- `ui/screens/orders_screen.py:659-670`
- `ui/screens/orders_screen.py:1087-1110`

Giá đóng vị thế đúng phải là BUY tại Bid và SELL tại Ask. Chính close path đang dùng mapping đúng:

- `services/mt5_service.py:1460-1466`

Sai phía giá làm BE/Trailing kích hoạt sớm một spread, tính pip/R trong dialog sai và có thể tạo mức SL broker không chấp nhận.

### 4. Sửa SL có nguy cơ xóa TP hiện hữu

Các nhánh BE và trailing chỉ gọi `modify_position_sltp(..., sl=new_sl)`:

- `ui/screens/orders_screen.py:580`
- `ui/screens/orders_screen.py:641`

Service không đọc và điền TP hiện tại; request chỉ thêm `tp` khi caller truyền:

- `services/mt5_service.py:1498-1521`

Theo [MQL5 Trade Request Structure](https://www.mql5.com/en/docs/constants/structures/mqltraderequest), thao tác `TRADE_ACTION_SLTP` cần các trường `action`, `symbol`, `sl`, `tp` và `position`. TP bị bỏ trống có thể trở thành `0` hoặc làm request bị broker từ chối. Hành vi này cũng trái yêu cầu “TP giữ nguyên” tại:

- `docs/ui/screen_design.md:1343`
- `docs/architecture/architecture.md:749`

### 5. Close thất bại hoặc khớp một phần vẫn làm mất tracking

UI xóa trailing config bất kể kết quả đóng lệnh:

- `ui/screens/orders_screen.py:1501-1508`
- `ui/screens/orders_screen.py:1531-1542`

Trong khi đó, service coi cả `TRADE_RETCODE_PLACED` và `TRADE_RETCODE_DONE_PARTIAL` là thành công:

- `services/mt5_service.py:1481-1493`

Không có bước re-query để xác nhận vị thế đã biến mất hoặc lấy remaining volume. Vì vậy vị thế bị reject, đang chờ xử lý hoặc chỉ đóng một phần có thể vẫn còn mở nhưng không còn được BE/Trailing bảo vệ.

### 6. Auto-tracking từ Scanner dùng sai symbol và vi phạm Qt thread affinity

Scanner Worker được chuyển sang `QThread`:

- `controllers/scanner_controller.py:218-229`

Sau khi đặt lệnh, worker gọi trực tiếp `OrdersScreen.auto_enable_tracking()`:

- `controllers/scanner_controller.py:1635-1669`

Method này thay đổi state, khởi động save timer và render QWidget:

- `ui/screens/orders_screen.py:1379-1403`

Theo [Qt Threads and QObjects](https://doc.qt.io/qt-6/threads-qobject.html), QWidget chỉ được sử dụng từ main thread và timer phải được start/stop trong thread sở hữu nó. Việc gọi trực tiếp từ Scanner Worker có thể gây race, cảnh báo timer hoặc crash không xác định.

Controller còn truyền app/display symbol như `EUR/USD` thay vì broker symbol như `EURUSDm`. Trailing engine dùng symbol này trực tiếp để gọi `symbol_info_tick()`:

- `controllers/scanner_controller.py:1653-1656`
- `ui/screens/orders_screen.py:550-558`

Với broker dùng alias hoặc suffix, auto-trailing có thể không bao giờ nhận được tick và thất bại im lặng.

## P1 — Rủi ro vận hành cao

### 7. State persistence không gắn với tài khoản và có thể phục hồi state cũ

State chỉ được khóa theo position ticket trong một file dùng chung toàn ứng dụng, không có server, login, broker, symbol identity hoặc schema version:

- `ui/screens/orders_screen.py:1425-1468`

Khi đổi tài khoản và ticket được tái sử dụng, cấu hình của tài khoản cũ có thể tác động lên vị thế mới.

Ngoài ra:

- `refresh_orders()` chạy trước `_load_trailing_state()` tại `ui/screens/orders_screen.py:67-83`.
- Runtime `extreme_price`, `current_sl` và chuyển Wide → Tight không được lưu sau từng thay đổi tại `ui/screens/orders_screen.py:597-643`.
- SL broker chỉ được đọc lại khi cached `current_sl == 0` tại `ui/screens/orders_screen.py:629-635`.
- Save/load lỗi đều bị nuốt tại `ui/screens/orders_screen.py:1432-1468`.
- Shutdown không flush save debounce tại `controllers/app_controller.py:98-111`.

Sau restart hoặc khi người dùng siết SL trực tiếp trên MT5, engine có thể dùng cache cũ và gửi một SL kém an toàn hơn SL broker đang giữ.

### 8. Pip, giá và broker constraints bị hard-code

Pip multiplier chỉ phân loại JPY và non-JPY:

- `ui/screens/orders_screen.py:39-49`
- `ui/screens/orders_screen.py:1195`
- `ui/screens/orders_screen.py:1381`

Hệ thống lại hỗ trợ XAU, XAG và BTC. Engine không sử dụng metadata quan trọng của broker như:

- `digits`
- `point`
- `trade_tick_size`
- `SYMBOL_TRADE_STOPS_LEVEL`
- `SYMBOL_TRADE_FREEZE_LEVEL`

Fixed trail và BE +2 pip vì vậy có thể sai nhiều bậc độ lớn, tạo stop quá sát hoặc bị broker reject.

Việc chọn filling mode cũng coi `SYMBOL_FILLING_MODE` như một enum thay vì bitmask tại `services/mt5_service.py:1554-1562`; close path còn hard-code IOC tại `services/mt5_service.py:1478-1480`. Quy tắc chính thức được mô tả tại [MQL5 Symbol Properties](https://www.mql5.com/en/docs/constants/environment_state/marketinfoconstants).

### 9. Engine phụ thuộc UI và thiếu observability

Hai timer chạy trên thread sở hữu Orders Screen:

- `ui/screens/orders_screen.py:69-77`

Refresh, lấy tick, lấy position và gửi lệnh MT5 đều chạy đồng bộ trong UI thread. Khi MT5 hoặc scanner chậm, giao diện có thể đứng và trailing bị trễ.

Ngoài ra, nhiều lỗi tick/persistence bị `except: pass`; card “Trailing” chỉ đếm config có `enabled=True`, không phản ánh:

- kết nối MT5 hiện tại;
- lần sửa SL thành công gần nhất;
- số lần broker reject;
- symbol alias có resolve được hay không;
- state đang stale hay healthy.

Do đó giao diện có thể phát tín hiệu an toàn giả. Automation cũng chỉ hoạt động khi ứng dụng, MT5 terminal và event loop còn chạy nhưng UI chưa giải thích rõ giới hạn này.

## P2 — Thiếu sót chức năng và UX

### Lệnh chờ gần như chỉ để xem

Khi chuyển sang tab pending, toàn bộ action bị ẩn:

- `ui/screens/orders_screen.py:334-339`

Thiếu các thao tác:

- hủy pending order;
- sửa entry, SL, TP hoặc expiration;
- hiển thị đầy đủ loại limit/stop/stop-limit;
- hiển thị order ticket và setup time.

### “Đóng tất cả” không phải emergency flatten hoàn chỉnh

Hành động chỉ đóng `_positions`, không hủy `_pending_orders`. Pending order có thể khớp ngay sau khi người dùng tưởng tài khoản đã được flatten.

Màn hình còn lấy toàn bộ position của tài khoản, không lọc theo magic/comment AMA. Do đó “Đóng tất cả” có thể đóng cả lệnh manual hoặc lệnh của EA khác, trái phạm vi được mô tả tại `docs/ui/screen_design.md:1344`.

### Thiếu thao tác quản lý vị thế phổ biến

- Không có partial close trên UI.
- Không sửa SL/TP thủ công.
- Không lọc theo symbol, chiến lược, magic hoặc nguồn lệnh.
- Không hiển thị account login/server, live/demo và trade permission trước hành động hàng loạt.
- Không hiển thị last refresh hoặc trạng thái dữ liệu stale.

### Một số bất nhất hiển thị

- Tiền tệ bị hard-code thành `$` dù account có thể dùng currency khác.
- Giá luôn hiển thị 5 chữ số, không theo `digits` của symbol.
- P/L trong dialog không cộng commission, trong khi bảng và tổng P/L có cộng.
- Nút xóa trailing không có xác nhận hoặc feedback rõ ràng.
- Thiếu ticket, open time, comment/magic và provenance để phân biệt nhiều vị thế cùng mã.

## Khoảng trống kiểm thử

Các test liên quan hiện có đều pass nhưng nhiều test chỉ tự mô phỏng lại công thức thay vì gọi production `_trailing_tick()`:

- `tests/test_be_trailing_task2.py:11-38`
- `tests/test_be_trailing_task5.py:40-56`

Chưa có test production cho các trường hợp:

- broker reject BE hoặc trailing;
- `positions_get()` trả `None` hoặc exception;
- Bid/Ask đúng theo side;
- TP được giữ nguyên khi sửa SL;
- close fail, `PLACED` hoặc `DONE_PARTIAL`;
- đổi account hoặc ticket được tái sử dụng;
- người dùng sửa SL trực tiếp trên MT5;
- app symbol khác broker symbol;
- QThread/QTimer và Qt event loop thật;
- state file corrupt hoặc save thất bại;
- danh sách position thay đổi trong lúc dialog xác nhận đang mở.

## Kết quả xác minh

- Test tập trung Order Management: **61 passed**.
- Toàn bộ test suite: **2615 passed, 8 skipped, 17 xfailed, 0 failed**.
- Hai lỗi state machine đã được tái hiện trực tiếp trên production `_trailing_tick()` bằng MT5 stub.

Việc test hiện tại đều qua không phủ định các phát hiện trên, vì các nhánh rủi ro chính chưa được kiểm thử end-to-end.

## Thứ tự khắc phục đề xuất

1. Tách engine quản lý lệnh khỏi QWidget thành service/state machine độc lập, có account identity và authoritative broker snapshot.
2. Phân biệt rõ `unavailable`, `stale`, `confirmed empty`; tuyệt đối không cleanup khi trạng thái broker chưa xác định.
3. Chỉ chuyển state sau khi broker xác nhận postcondition; re-query position sau BE, trailing và close.
4. Sửa Bid/Ask, bảo toàn TP, normalize theo tick size và kiểm tra stop/freeze level.
5. Resolve broker symbol và position ticket bằng post-trade reconciliation, không dựa trên display symbol hoặc fallback order/deal ticket.
6. Đưa mọi cập nhật QWidget về main thread bằng queued signal; serialize toàn bộ MT5 SDK calls qua một boundary duy nhất.
7. Thêm heartbeat, last successful modification, retry/error counters và audit log cho từng position.
8. Bổ sung release-gate tests cho toàn bộ nhánh P0 trước khi mở lại trên tài khoản live.
