# AI Market Analyst - Đặc tả sản phẩm

> Phiên bản tài liệu: 2026-06-11
> Trạng thái: cập nhật theo chương trình hiện tại
> Phạm vi: ứng dụng desktop PyQt6 phân tích Forex/XAU/USD/XAG/USD/BTC/USD bằng MT5, rule engine, AI commentary, scanner, backtest và auto-trade MT5

## 1. Mục tiêu sản phẩm

AI Market Analyst là công cụ cá nhân hỗ trợ trader phân tích thị trường Forex, kim loại quý và BTC/USD. Sản phẩm tập trung vào:

- Lấy dữ liệu thật từ MT5 terminal đang đăng nhập broker.
- Tự tính indicator, market regime, direction bias, SMC context, macro context và risk.
- Tạo trade plan có Entry, SL, TP, R:R và lot theo risk settings.
- Quét nhiều mã để tìm setup đủ điều kiện.
- Backtest hệ thống trên dữ liệu lịch sử để đo lường edge.
- Gửi Telegram alert cho setup sẵn sàng.
- Tự động vào lệnh MT5 khi người dùng bật auto-entry trong Scanner auto-scan, với bộ lọc riêng cho từng cặp dựa trên kết quả backtest.

AI chỉ dùng để diễn giải dữ liệu đã tính và viết nhận định dễ hiểu. AI không được tự bịa giá, entry, SL, TP, lot hoặc trạng thái ready.

## 2. Phạm vi thị trường

Sản phẩm hỗ trợ:

- 28 cặp Forex chính/phụ theo `config.constants.SUPPORTED_SYMBOLS`.
- XAU/USD (vàng giao ngay so với USD).
- XAG/USD (bạc giao ngay so với USD).
- BTC/USD (Bitcoin so với USD).

Broker symbol trong MT5 có thể có hậu tố như `m`, `c`, `.r`. Code phải resolve symbol ứng dụng như `EUR/USD`, `XAG/USD` hoặc `BTC/USD` sang broker symbol thật trong Market Watch, ví dụ `XAGUSDm`, `BTCUSDm` hoặc dạng có hậu tố riêng của broker.

## 3. Chế độ phân tích

### 3.1 Scanner (chính)

Scanner là chế độ phân tích chính, quét danh sách mã đã chọn trong MT5 Market Watch. Mỗi mã được phân tích đầy đủ qua pipeline `analyze_symbol()`, trả về kết quả gồm:

- Market regime, direction bias, buy/sell score, final score.
- Trade permission, decision engine, scanner group.
- Trade plan (entry zone, SL, TP, R:R, position sizing).
- Entry checklist, M15 quality, SMC flags.
- Macro/news context, macro alignment scores.
- AI commentary (nếu có cấu hình AI).

Scanner có hai chế độ:

- `Quét 1 lần`: quét và hiển thị kết quả, không tự động vào lệnh.
- `Quét theo khoảng thời gian`: dùng timer quét lại định kỳ. Khi bật auto-trade, có thể tự động vào lệnh MT5 với bộ lọc riêng cho từng cặp.

### 3.2 Backtest

Backtest replay toàn bộ pipeline `analyze_symbol()` trên dữ liệu lịch sử để đo lường edge của hệ thống. Hỗ trợ 5 chế độ (Strict, Balanced, Legacy, Research, Backtest), multi-symbol batch, và breakdown 12 chiều (side, regime, score, M15 quality, SMC, R:R...).

Kết quả backtest dùng để xác định bộ lọc auto-trade tối ưu cho từng cặp, cấu hình trong Settings > MT5.

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

Quy tắc contract size:

- Forex dùng `settings.trading.contract_size_override`, mặc định `100000`, để tránh sai lot trên tài khoản cent.
- XAU/USD, XAG/USD và BTC/USD là symbol đặc biệt, được ưu tiên dùng `trade_contract_size` từ MT5 nếu broker trả về giá trị hợp lệ.
- Nếu MT5 không trả về contract size hợp lệ, fallback lần lượt là XAU/USD = `100`, XAG/USD = `5000`, BTC/USD = `1`.

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

Auto-entry được hỗ trợ có kiểm soát trong Scanner auto-scan, với bộ lọc cấu hình riêng cho từng cặp trong Settings > MT5.

Điều kiện bật:

- Scanner đang ở chế độ `Quét theo khoảng thời gian`.
- Người dùng bật nút chọn `Tự động vào lệnh MT5`.

Điều kiện đặt lệnh (với cặp đã cấu hình auto-trade):

- Row không bị blocked (scanner_group != "blocked", trade_permission != "blocked").
- Market regime khớp với `auto_trade_regime` trong cấu hình (nếu được đặt).
- Expected effective R:R >= `auto_trade_min_rr` (nếu được đặt).
- Signal score >= 50.
- Có scenario đúng hướng đã cấu hình (`auto_trade_side`) hoặc `best_side`.
- Có `position_sizing.suggested_lot`, `stop_loss`, `take_profit`.
- MT5 không có open position hoặc pending order cho cùng broker symbol.

Đối với cặp chưa có cấu hình auto-trade (chưa backtest), hệ thống không tự động vào lệnh — chỉ hiển thị kết quả quét.

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

Ứng dụng gồm 5 màn hình chính:

- Dashboard — tổng quan trạng thái MT5, AI, thống kê nhanh.
- Scanner — quét thị trường, bảng xếp hạng cơ hội, auto-trade.
- Backtest — replay hệ thống trên dữ liệu lịch sử, phân tích edge.
- Journal — nhật ký giao dịch, xem lại phân tích đã lưu.
- Settings — cấu hình AI, MT5, giao dịch, auto-trade cho từng cặp.

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

## 11. Backtest

System backtest replay toàn bộ pipeline `analyze_symbol()` trên dữ liệu lịch sử để đo lường edge.

Tính năng chính:

- 5 chế độ vào lệnh: Strict, Balanced, Legacy, Research, Backtest.
- Multi-symbol batch backtest.
- Funnel diagnostics: snapshot → setup → gate → entry → trade.
- Breakdown 12 chiều: symbol, side, decision, score bucket, final score, M15 quality, regime, SMC zone, entry zone, liquidity sweep, displacement, CHOCH, R:R.
- Equity curve, drawdown tracking, account guard mô phỏng.
- Dữ liệu M15 load theo chunk 180 ngày, tự fallback sang H1 khi không có.

Kết quả backtest là cơ sở để cấu hình bộ lọc auto-trade cho từng cặp trong Settings > MT5.

## 12. Cấu hình auto-trade theo cặp

Mỗi cặp có thể được cấu hình auto-trade riêng trong Settings > MT5:

| Trường | Ý nghĩa |
|---|---|
| Min Score | Ngưỡng final score tối thiểu |
| Auto Regime | Chỉ auto-trade khi regime khớp. Để trống = không lọc |
| Auto Side | Hướng auto-trade (buy/sell/best) |
| Min RR | R:R kỳ vọng tối thiểu. 0 = không lọc |

Cặp chưa cấu hình (chưa backtest) sẽ không được auto-trade.

## 13. Packaging

Ứng dụng phải đóng gói được trên Windows:

- Include assets.
- Include QSS.
- Include chart assets.
- Include migrations.
- Include hidden imports cần cho PyQt6/PyQt6-WebEngine/MetaTrader5.
- User data lưu trong `%APPDATA%/AI Market Analyst/`.

## 14. Testing

Các nhóm test quan trọng:

- Core: scoring, risk, entry engine, signal engine, decision engine, trade gate.
- MT5 service, scanner controller, auto-trade controller.
- Backtest engine: system backtest, plan replay, feedback.
- Telegram alert, journal, settings service.
- Scanner ranking, opportunity score, scanner row contract.

## 15. Nguyên tắc an toàn

- Không tự vào lệnh khi người dùng chưa bật nút chọn auto-entry.
- Không vào thêm nếu broker symbol đã có position hoặc pending order.
- Không bỏ qua risk settings.
- Không gửi lệnh nếu thiếu SL/TP/lot hợp lệ.
- Không dùng dữ liệu ngoài MT5 để tạo trạng thái ready thực chiến.
- Không để AI quyết định execution.
