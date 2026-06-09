# AI Market Analyst - Đặc tả sản phẩm

> Phiên bản tài liệu: 2026-06-09
> Trạng thái: cập nhật theo chương trình hiện tại
> Phạm vi: ứng dụng desktop PyQt6 phân tích Forex/XAU/USD bằng MT5, rule engine và AI commentary

## 1. Mục tiêu sản phẩm

AI Market Analyst là công cụ cá nhân hỗ trợ trader phân tích thị trường Forex và vàng. Sản phẩm tập trung vào:

- Lấy dữ liệu thật từ MT5 terminal đang đăng nhập broker.
- Tự tính indicator, market regime, direction bias, SMC context, macro context và risk.
- Tạo trade plan có Entry, SL, TP, R:R và lot theo risk settings.
- Quét nhiều mã để tìm setup đủ điều kiện.
- Gửi Telegram alert cho setup sẵn sàng.
- Có thể tự động vào lệnh MT5 khi người dùng chủ động bật quyền auto-entry trong Scanner auto-scan.

AI chỉ dùng để diễn giải dữ liệu đã tính và viết nhận định dễ hiểu. AI không được tự bịa giá, entry, SL, TP, lot hoặc trạng thái ready.

## 2. Phạm vi thị trường

Sản phẩm hỗ trợ:

- 28 cặp Forex chính/phụ theo `config.constants.SUPPORTED_SYMBOLS`.
- XAU/USD.

Broker symbol trong MT5 có thể có hậu tố như `m`, `c`, `.r`. Code phải resolve symbol ứng dụng như `EUR/USD` sang broker symbol thật trong Market Watch.

## 3. Chế độ phân tích

### 3.1 Single Analysis

Người dùng chọn một mã và chạy phân tích sâu. Kết quả phải có:

- Kết luận hành động.
- Market regime.
- Direction bias.
- Buy/Sell score.
- Final score.
- Trade permission.
- Trade plan.
- Entry checklist.
- Position sizing.
- Macro/news context.
- Replay/backtest summary.
- AI commentary nếu có cấu hình AI hợp lệ.

### 3.2 Scanner

Scanner quét danh sách mã đã chọn trong MT5 Market Watch. Scanner có hai chế độ:

- `Quét 1 lần`: chỉ quét và hiển thị kết quả, không tự động vào lệnh.
- `Quét theo khoảng thời gian`: dùng timer để quét lại theo nến/khung thời gian đã chọn.

Scanner không được chạy song song hai worker scan. Khi một worker đang chạy, lần quét tiếp theo phải chờ worker hiện tại kết thúc.

## 4. Trạng thái entry và hành động scanner

`core.entry_engine.py` là nơi duy nhất xác nhận trạng thái entry. Các module UI, controller và AI không được tự đặt trạng thái ready.

Trade plan phải tách:

- `watch_zone`: vùng theo dõi rộng.
- `entry_zone`: vùng xác nhận hẹp, dùng để tính `price_in_entry_zone` và `ready_to_trade`.

Một setup chỉ được xem là sẵn sàng vào lệnh khi:

- `scanner_action == "ready"`.
- `trade_permission == "allowed"`.
- Có `analysis_result`.
- Có scenario đúng `best_side`.
- Scenario có Entry/SL/TP và position sizing hợp lệ.

Các hành động scanner:

- `ready`: sẵn sàng vào lệnh nếu người dùng cho phép.
- `watch`: theo dõi.
- `wait`: chờ xác nhận.
- `skip`: bỏ qua hoặc bị chặn.

## 5. Quản trị rủi ro và lot

Lot phải được tính bằng `core.risk_engine.position_sizing()` dựa trên:

- Balance thật từ MT5 nếu có.
- `settings.trading.default_risk_percent`.
- Giới hạn bởi `settings.trading.max_risk_percent`.
- Khoảng cách Entry - SL.
- Contract size và quote-to-USD rate nếu cần.

Controller phải cap `risk_percent` theo `max_risk_percent` trước khi phân tích và trước khi auto-entry.

Auto-entry không được tự tăng lot lên broker minimum nếu điều đó có thể làm vượt mức rủi ro đã tính. Nếu lot sau chuẩn hóa theo broker `volume_step` thấp hơn `volume_min`, hệ thống phải bỏ qua lệnh.

## 6. MT5 data và execution

MT5 là nguồn dữ liệu và nơi execution chính:

- OHLCV lấy qua MetaTrader5 Python API.
- Tick bid/ask lấy từ MT5.
- Spread lấy từ MT5 symbol info/tick.
- Account balance lấy từ MT5 account info.
- Market order gửi qua MT5 terminal đang đăng nhập.

Nếu MT5 chưa mở, chưa connected, chưa logged in, thiếu symbol, không lấy được OHLCV hoặc spread bất thường, hệ thống phải chặn trạng thái ready/action thực chiến.

## 7. Auto-entry MT5

Auto-entry hiện được hỗ trợ có kiểm soát trong Scanner auto-scan.

Điều kiện bật:

- Scanner đang ở chế độ `Quét theo khoảng thời gian`.
- Người dùng bật nút chọn `Tự động vào lệnh MT5`.
- Nút chọn này phải được làm nổi bật khi active để người dùng thấy rõ hệ thống có thể đặt lệnh thật. Không hiển thị thêm ô checkbox nhỏ bên trong nút; toàn bộ nút là trạng thái bật/tắt.

Điều kiện đặt lệnh:

- Row là setup `ready` + `allowed`.
- Có scenario đúng `best_side`.
- Có `position_sizing.suggested_lot`.
- Có `stop_loss`.
- Có ít nhất một `take_profit`.
- MT5 không có open position hoặc pending order cho cùng broker symbol.

Luồng đặt lệnh:

1. Controller quét xong toàn bộ danh sách.
2. Controller lọc các row đủ điều kiện.
3. Với từng broker symbol, gọi `MT5Service.has_open_position_or_order()`.
4. Nếu đã có position/order, bỏ qua symbol đó.
5. Nếu chưa có, gọi `MT5Service.place_market_order()`.
6. BUY dùng giá `ask`; SELL dùng giá `bid`.
7. SL lấy từ `scenario.stop_loss`.
8. TP dùng TP đầu tiên trong `scenario.take_profit`.
9. Volume dùng `scenario.position_sizing.suggested_lot` sau khi chuẩn hóa xuống theo broker step.
10. Kết quả trả về trong `output["auto_trade_results"]`.

`auto_trade_results` gồm:

- `enabled`.
- `attempted`.
- `opened`.
- `skipped`.
- `errors`.
- `orders`.
- `risk_percent`.

Manual/one-shot scan không được đặt lệnh MT5.

## 8. Telegram alert

Telegram được cấu hình trong Settings > Nâng cao:

- Bot token.
- Danh sách chat ID.
- Interval auto-scan mặc định.

Detailed alert chỉ gửi cho setup thật sự ready:

- `scanner_action == "ready"`.
- `trade_permission == "allowed"`.
- Có trade plan tương ứng.

Detailed alert phải dùng tiếng Việt có dấu, icon dễ nhìn và gạch đầu dòng rõ ràng. Nội dung gồm:

- Mã giao dịch và broker symbol.
- Hướng MUA/BÁN.
- Entry.
- Stop loss.
- Take profit.
- Lot gợi ý.
- R:R.
- Điểm setup.
- Lý do.
- Vốn MT5 nếu có.
- Nguồn.

Summary alert sau mỗi lần scan chỉ hiển thị:

- Thời gian dạng `dd-mm-yyyy HH:MM:SS`.
- Đã quét bao nhiêu mã.
- Sẵn sàng vào lệnh bao nhiêu mã.
- Danh sách mã ready kèm Entry/SL/TP.

Summary alert không hiển thị danh sách theo dõi.

## 9. UI/UX chính

Ứng dụng gồm các màn hình chính:

- Dashboard.
- Single Analysis Input.
- Single Analysis Result.
- Scanner.
- Scanner Detail.
- Journal.
- Journal Detail.
- Settings.

Yêu cầu UI:

- App mở maximized bằng `showMaximized()`.
- Không để UI bị đơ khi lấy dữ liệu MT5, gọi AI hoặc scan nhiều mã.
- Tác vụ nặng phải chạy qua worker/thread.
- Scanner table phải dùng model/view.
- Text phải là tiếng Việt có dấu, dễ hiểu.
- Các thuật ngữ trading phổ biến có thể giữ tiếng Anh kèm giải thích ngắn: Entry, SL, TP, R:R, lot, MT5.
- Control auto-entry phải nổi bật khi active vì có thể đặt lệnh thật.

## 10. Journal

Journal lưu phân tích và trade outcome để người dùng xem lại:

- Planned entry/SL/TP/lot.
- Actual entry/exit/lot nếu có.
- Result R.
- Execution quality.
- Manual mistake tags.
- Auto mistake tags.

Journal data nằm trong SQLite và phải có migration ổn định.

## 11. Backtest/replay

Backtest replay kiểm chứng trade plan trên dữ liệu lịch sử. Output nên gồm:

- Trade count.
- Win rate.
- Expectancy R.
- Average R.
- Average MFE/MAE.
- Max drawdown.
- Breakdown theo symbol/session nếu có.

Replay không thay thế quyết định realtime và không tự tạo lệnh MT5.

## 12. Packaging

Ứng dụng phải đóng gói được trên Windows:

- Include assets.
- Include QSS.
- Include chart assets.
- Include migrations.
- Include hidden imports cần cho PyQt6/PyQt6-WebEngine/MetaTrader5.
- User data lưu trong `%APPDATA%/AI Market Analyst/`.

## 13. Testing

Các nhóm test quan trọng:

- Core scoring/risk/entry engine.
- MT5 service với mock.
- Scanner controller.
- Telegram alert formatter.
- Auto-entry controller.
- Settings service.
- UI Scanner controls.
- Phase 16/17/18 regression nếu môi trường cho phép.

Lưu ý hiện tại:

- Full PyQt UI tests có thể bị access violation khi gom nhiều file trong cùng process trên Windows. Chạy từng file UI riêng thường ổn định hơn.
- Test worker scanner có thể flaky nếu dùng `NewsService` thật và network chậm.
- Phase 18 prompt status test có thể mâu thuẫn nếu tài liệu upgrade đã chuyển từ UNFINISH sang FINISH.

## 14. Nguyên tắc an toàn

- Không tự vào lệnh khi người dùng chưa bật nút chọn auto-entry.
- Không vào thêm nếu broker symbol đã có position hoặc pending order.
- Không bỏ qua risk settings.
- Không gửi lệnh nếu thiếu SL/TP/lot hợp lệ.
- Không dùng dữ liệu ngoài MT5 để tạo trạng thái ready thực chiến.
- Không để AI quyết định execution.
