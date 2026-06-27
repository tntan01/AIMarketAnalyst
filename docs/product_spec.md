# AI Market Analyst - Đặc tả sản phẩm

> Phiên bản tài liệu: 2026-06-11
> Trạng thái: cập nhật theo chương trình hiện tại
> Phạm vi: ứng dụng desktop PyQt6 phân tích Forex/XAU/USD/XAG/USD/BTC/USD bằng MT5/cTrader, rule engine, AI commentary, scanner, backtest và auto-trade

## 1. Mục tiêu sản phẩm

AI Market Analyst là công cụ cá nhân hỗ trợ trader phân tích thị trường Forex, kim loại quý và BTC/USD. Sản phẩm tập trung vào:

- Lấy dữ liệu thật từ broker (MT5, cTrader) thông qua kiến trúc Multi-Provider.
- Tự tính indicator, market regime, direction bias, SMC context, macro context và risk.
- Tạo trade plan có Entry, SL, TP, R:R và lot theo risk settings.
- Quét nhiều mã để tìm setup đủ điều kiện.
- Backtest hệ thống trên dữ liệu lịch sử để đo lường edge.
- Gửi Telegram alert cho setup sẵn sàng.
- Tự động vào lệnh (MT5/cTrader) khi người dùng bật auto-entry trong Scanner auto-scan, với bộ lọc riêng cho từng cặp dựa trên kết quả backtest.

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

Scanner là chế độ phân tích chính, quét danh sách mã đã chọn trong danh sách Symbol hệ thống (MT5/cTrader). Mỗi mã được phân tích đầy đủ qua pipeline `analyze_symbol()`, trả về kết quả gồm:

- Market regime, direction bias, buy/sell score, final score.
- Trade permission, decision engine, scanner group.
- Trade plan (entry zone, SL, TP, R:R, position sizing).
- Entry checklist, M15 quality, SMC flags.
- Macro/news context, macro alignment scores.
- AI commentary (nếu có cấu hình AI).

Scanner có hai chế độ:

- `Quét 1 lần`: quét và hiển thị kết quả, không tự động vào lệnh.
- `Quét theo khoảng thời gian`: dùng timer quét lại định kỳ. Khi bật auto-trade, có thể tự động vào lệnh MT5 với bộ lọc riêng cho từng cặp.

Mỗi cặp có thể được cấu hình ngưỡng quyết định riêng (`decision_ready`, `decision_watch`, `decision_wait`) trong `SymbolScanSettings`. Các ngưỡng này được truyền vào `decision_engine.make_final_decision()` để phân loại setup thành READY_TO_TRADE, WATCH_ONLY, WAITING_CONFIRMATION, hoặc STAND_ASIDE. Mặc định: ready=65, watch=60, wait=55.

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

## 6. Data và Execution (Multi-Provider)

Hệ thống kết nối thị trường qua giao diện `BaseDataProvider`:

- **MT5 (Local)**:
  - Lấy OHLCV, tick bid/ask qua MetaTrader5 Python API.
  - Account balance và lệnh market order gửi qua MT5 terminal đang đăng nhập.
- **cTrader (Cloud API)**:
  - Lấy OHLCV, báo giá và đặt lệnh qua cTrader Open API v2.

Nếu provider chưa kết nối, thiếu symbol, không lấy được OHLCV hoặc spread bất thường, hệ thống phải chặn trạng thái ready/action thực chiến.

## 7. Auto-entry

Auto-entry hoạt động theo cơ chế **hai nhánh** dựa trên cấu hình trong Settings > Dữ liệu. Cặp nào được bật Backtest và có filter riêng sẽ chạy **Nhánh B**, ngược lại chạy **Nhánh A**.

### 7.1 Nguồn dữ liệu cấu hình

Mỗi cặp được cấu hình trong `SymbolScanSettings` tại `config/settings.py`. Bảng cấu hình trong Settings > Dữ liệu gồm các cột:

| Cột | Trường | Mặc định | Ý nghĩa |
|---|---|---|---|
| Kiểm thử | `backtest` | OFF | Bật/tắt chế độ auto-trade riêng cho cặp |
| Điểm tối thiểu | `min_score` | (rỗng) | Ghi đè ngưỡng Ready khi backtest=ON. Rỗng = dùng `decision_ready` |
| Regime | `auto_trade_regime` | (rỗng) | Lọc regime, chỉ auto-trade khi khớp |
| Hướng | `auto_trade_side` | best | Hướng vào lệnh: buy/sell/best |
| RR tối thiểu | `min_expected_rr` | 1.3 | Ngưỡng effective R:R tối thiểu |
| Ready | `decision_ready` | **65** | final_score ≥ mức này → READY_TO_TRADE |
| Watch | `decision_watch` | **60** | final_score ≥ mức này → WATCH_ONLY |
| Wait | `decision_wait` | **55** | final_score ≥ mức này → WAITING_CONFIRMATION |

Các cột Ready, Watch, Wait **luôn hiển thị và có thể chỉnh sửa** cho mọi cặp, không phụ thuộc vào trạng thái Backtest. Cột Điểm tối thiểu **chỉ được nhập khi Backtest = ON**, ngược lại để trống và disabled.

### 7.2 Luồng pipeline chung (cả hai nhánh)

Mỗi cặp khi quét đều chạy qua 2 lớp trong pipeline `AnalysisPipeline`:

**Lớp 1 — Chấm điểm (Step 1→5):** Phân tích kỹ thuật (trend, momentum, location, SMC, risk, macro) → cho điểm BUY/SELL (0-100). Tạo scenario với Entry/SL/TP/R:R.

**Lớp 2 — Gate (Step 6):** 11 gate kiểm tra an toàn tuần tự: MT5, Spread, DataQuality, News, DailyWeeklyLoss, AccountGuard, Journal, M15, ExpectedRR, ScoreGap, ZoneBroken. Gate có thể Block (chặn cứng), Warning (hạ cap xuống WATCH_ONLY/WAITING_CONFIRMATION), hoặc Pass.

**Decision Engine (Step 7):** Kết hợp score + gate + entry status để ra quyết định cuối cùng. Thứ tự ưu tiên: Gate block → Gate cap → Score gap → Entry status → Score so với thresholds. `ready` threshold được lấy từ `min_score` (nếu > 0) hoặc `decision_ready`.

### 7.3 Nhánh A — Cặp KHÔNG có cấu hình auto-trade riêng (Backtest = OFF)

**Pipeline:** Dùng thresholds từ `decision_ready/watch/wait` (mặc định 65/60/55). Không có cơ chế override.

**Auto-trade:** `_is_auto_trade_candidate` yêu cầu điều kiện strict:
- `scanner_action == "ready"` (decision engine phải ra READY_TO_TRADE)
- `trade_permission == "allowed"`
- Có scenario hợp lệ (Entry/SL/TP/Lot)

**Tóm lại:** Chỉ vào lệnh khi pipeline tự tin 100%: score đạt ngưỡng, gate pass, entry confirmed.

### 7.4 Nhánh B — Cặp CÓ cấu hình auto-trade riêng (Backtest = ON, có ít nhất 1 filter)

**Pipeline:** Dùng thresholds từ Settings:
- Nếu `min_score > 0`: `ready = min_score` (vd: 55), ngược lại dùng `decision_ready` (65)
- `min_rr = min_expected_rr` (vd: 1.5) thay vì mặc định 1.3

**`_apply_symbol_override` (chạy sau pipeline, trước auto-trade):**
Nếu row đang `stand_aside` (entry invalidated hoặc score < wait), kiểm tra 4 điều kiện từ cấu hình backtest:
1. Regime khớp `auto_trade_regime` (nếu được đặt)
2. Side khớp `auto_trade_side` (nếu là buy/sell)
3. Score ≥ `min_score`
4. effective_rr ≥ `min_expected_rr`

Cả 4 đạt → nâng `scanner_action` lên `ready`. Cơ chế này cho phép backtest "phủ quyết" pipeline khi pipeline quá conservative.

**Auto-trade (`_execute_auto_trades`):** Không cần `scanner_action == "ready"`. Dùng bộ lọc backtest riêng:
- Không bị blocked (gate, permission, journal_feedback)
- Regime khớp (nếu được đặt)
- `expected_effective_rr >= min_expected_rr` (nếu > 0)
- `best_score >= min_score` (fallback 65 nếu min_score = 0)
- Có scenario đúng hướng với Entry/SL/TP/Lot hợp lệ
- Chưa có lệnh mở cho mã đó

→ Đạt tất cả: **đặt lệnh Market Order ngay**, không cần pipeline phê duyệt.

### 7.5 So sánh hai nhánh

| | Nhánh A (không backtest) | Nhánh B (có backtest) |
|---|---|---|
| Ngưỡng ready | `decision_ready` (65) | `min_score` nếu > 0, else `decision_ready` |
| Ngưỡng watch | `decision_watch` (60) | `decision_watch` (60) |
| Ngưỡng wait | `decision_wait` (55) | `decision_wait` (55) |
| Ngưỡng min_rr | 1.3 (cứng) | `min_expected_rr` |
| Override stand_aside | Không | Có, nếu khớp 4 điều kiện |
| Auto-trade điều kiện | `scanner_action == "ready"` | Vượt bộ lọc backtest |
| Regime filter | Không | Có, nếu đặt |
| Ai quyết định vào lệnh | Decision engine | Backtest config + gate |

### 7.6 Luồng đặt lệnh

1. Controller quét xong toàn bộ danh sách.
2. Với mỗi row, gọi `_apply_symbol_override` → gọi `_is_auto_trade_candidate`.
3. Nếu candidate pass, gọi `DataProvider.has_open_position_or_order()`.
4. Nếu chưa có lệnh, gọi `DataProvider.place_market_order()`.
5. BUY dùng giá `ask`; SELL dùng giá `bid`.
6. SL lấy từ `scenario.stop_loss`.
7. TP dùng TP đầu tiên trong `scenario.take_profit`.
8. Volume dùng `scenario.position_sizing.suggested_lot` sau khi chuẩn hóa theo broker step.
9. Kết quả trả về trong `output["auto_trade_results"]`.

`auto_trade_results` gồm: `enabled`, `attempted`, `opened`, `skipped`, `errors`, `orders`, `risk_percent`.

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
