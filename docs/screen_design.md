# Thiết kế màn hình phần mềm AI Market Analyst (Nhà phân tích thị trường AI)

> Tài liệu này được xây dựng từ bản phân tích phần mềm **AI Market Analyst (Nhà phân tích thị trường AI)**.  
> Quy ước hiển thị: giao diện ưu tiên tiếng Việt ngắn gọn. Thuật ngữ tiếng Anh chỉ giữ khi cần thiết và phải có giải thích tiếng Việt ở lần hiển thị đầu tiên, tooltip hoặc mô tả phụ. Ví dụ ưu tiên **Bảng điều khiển**, nếu cần có thể ghi **Bảng điều khiển (Dashboard)**.

---

## 1. Tổng quan số lượng màn hình

Phần mềm nên gồm **8 màn hình chính**:

| STT | Màn hình | Mục đích |
|---:|---|---|
| 1 | Dashboard (Bảng điều khiển tổng quan) | Xem trạng thái hệ thống và chọn chế độ sử dụng |
| 2 | Single Analysis Input (Màn hình nhập phân tích một mã) | Chọn mã giao dịch và thông số trước khi phân tích |
| 3 | Single Analysis Result (Màn hình kết quả phân tích một mã) | Hiển thị báo cáo phân tích đầy đủ cho một mã |
| 4 | Scanner (Màn hình quét thị trường) | Quét nhanh toàn bộ danh sách mã để tìm setup đáng chú ý |
| 5 | Scanner Detail (Màn hình chi tiết mã từ quét thị trường) | Xem phân tích chi tiết của một mã được chọn từ Scanner (màn hình quét thị trường) |
| 6 | Journal (Màn hình nhật ký phân tích) | Xem danh sách các phân tích đã lưu |
| 7 | Journal Detail (Màn hình chi tiết nhật ký) | Xem lại chi tiết một phân tích đã lưu và ghi chú thêm |
| 8 | Settings (Màn hình cài đặt) | Cấu hình AI (trí tuệ nhân tạo), MT5 (MetaTrader 5), giao dịch và hiển thị |

Nếu tính các tab (thẻ chức năng) bên trong Settings (Màn hình cài đặt), phần mềm có thể xem là **12 màn hình/tabs chức năng**:

1. Dashboard (Bảng điều khiển tổng quan)
2. Single Analysis Input (Màn hình nhập phân tích một mã)
3. Single Analysis Result (Màn hình kết quả phân tích một mã)
4. Scanner (Màn hình quét thị trường)
5. Scanner Detail (Màn hình chi tiết mã từ quét thị trường)
6. Journal (Màn hình nhật ký phân tích)
7. Journal Detail (Màn hình chi tiết nhật ký)
8. Settings - AI Provider (Cài đặt nhà cung cấp AI)
9. Settings - MT5 Data (Cài đặt dữ liệu MT5)
10. Settings - Trading (Cài đặt giao dịch)
11. Settings - Display (Cài đặt hiển thị)
12. Settings - Advanced (Cài đặt nâng cao)

---

## 1.1. Kiểm tra lại thiết kế trước khi code UI

Thiết kế màn hình cần được hiểu theo hướng **desktop app PyQt6**, không phải web page dài. Khi lập trình, AI phải ưu tiên bố cục làm việc gọn trong một cửa sổ, có navigation cố định, vùng nội dung chính co giãn và các panel/tabs để chứa thông tin dài.

Quyết định thiết kế bắt buộc:

- Dùng `QMainWindow` làm khung chính.
- Khi mở chương trình, cửa sổ chính phải tự động chiếm toàn bộ vùng làm việc của màn hình bằng `showMaximized()`. Yêu cầu này áp dụng cho mọi kích thước màn hình và mọi mức Windows scaling như 100%, 125%, 150%. Đây là chế độ maximized desktop window, không phải borderless game fullscreen, để người dùng vẫn dùng được taskbar, Alt+Tab và window controls bình thường.
- Dùng sidebar hoặc top navigation để chuyển giữa 5 khu vực chính: Bảng điều khiển, Phân tích, Quét thị trường, Nhật ký, Cài đặt.
- Dùng `QStackedWidget` hoặc router tương đương để quản lý 8 màn hình chính.
- Dùng `QSplitter`, `QGridLayout`, `QHBoxLayout`, `QVBoxLayout` và stretch factor để giao diện co giãn tốt trên màn hình 1366x768 trở lên.
- Dùng `QTableView` + `QAbstractTableModel` cho bảng Scanner và Journal; không dựng bảng bằng nhiều label thủ công.
- Dùng `QTabWidget` cho Settings và các phần chi tiết dài trong màn hình kết quả.
- Dùng `QWebEngineView` để nhúng chart web trong màn hình kết quả phân tích và chi tiết scanner.
- Không để màn hình kết quả phân tích trở thành một trang dài phải cuộn nhiều. Phần thấy ngay phải có: kết luận, thiên hướng, quyền giao dịch, điểm mua/bán, entry, SL, TP, R:R, lot và trạng thái dữ liệu.
- Entry phải hiển thị kèm `entry_status` và `confirmation_score`. Nếu trạng thái là `watch_zone` hoặc `waiting_confirmation`, UI phải thể hiện rõ đây là vùng theo dõi/chờ xác nhận, không phải lệnh đã sẵn sàng.
- Kết quả phân tích phải có checklist entry dễ đọc gồm: Xu hướng, Vùng POI, Xác nhận H1, Tin tức, Spread, R:R, Lot. Mỗi dòng hiển thị trạng thái `Đạt` hoặc `Chờ`, giá trị liên quan và ghi chú ngắn.
- Kết quả phân tích phải có phần Replay/Backtest tóm tắt: số lệnh replay, win rate, expectancy R, average R, MFE/MAE trung bình, max drawdown và hiệu quả theo phiên. Phần này không thay thế quyết định vào lệnh realtime, chỉ dùng để kiểm chứng setup có lịch sử hợp lý hay không.
- Kết quả phân tích phải có phần Vĩ mô hiển thị: điểm vĩ mô mua/bán, macro theme theo từng đồng tiền, Tin mới nhất, điểm nóng thế giới và lịch kinh tế. Nếu không có dữ liệu, phải hiển thị rõ “không có dữ liệu” thay vì để trống.
- Mục Tin mới nhất chỉ hiển thị headline thị trường và phát biểu đáng chú ý trong 24h qua, mỗi dòng riêng. Dòng tin mới nhất dùng mẫu `ngày-tháng-năm thời gian: nội dung tiếng Việt`; chỉ thêm `-> ảnh hưởng tới đồng tiền đang xét` khi đã có nhận định tác động cụ thể. Lịch kinh tế vẫn hiển thị tác động vì bản thân event có mức impact.
- Màn hình Scanner có phần Thiết lập quét cho phép chọn `Quét 1 lần` hoặc `Quét theo khoảng thời gian`; interval hỗ trợ 1 phút, 5 phút, 15 phút, 30 phút, 1 giờ, 4 giờ, 1 ngày. Khi đang auto-scan phải có nút `Dừng quét tự động`.
- Settings > Nâng cao có cấu hình Telegram gồm bot token, danh sách chat ID nhận alert và interval auto-scan mặc định. Chat ID có thể nhập nhiều giá trị, cách nhau bằng dấu phẩy.
- Các phần dài như nhận định AI, điểm thành phần, raw JSON, log kỹ thuật phải đưa vào tab, panel phụ hoặc dialog.
- Mọi tác vụ nặng như lấy dữ liệu MT5, gọi AI, quét 29 mã, tính indicator phải chạy qua worker/thread; UI không được bị đơ.

### Quy ước tiếng Việt trên giao diện

Trên phần mềm, tất cả thuật ngữ phải cố gắng tối đa để dịch ra tiếng Việt ngắn gọn. Tiếng Anh chỉ giữ khi:

- Là tên riêng hoặc tên sản phẩm: MT5, DeepSeek, OpenAI, Claude, API Key.
- Là thuật ngữ trading rất phổ biến nhưng cần kèm tiếng Việt ngắn: SL (cắt lỗ), TP (chốt lời), R:R (rủi ro/lợi nhuận).
- Là mã kỹ thuật trong dữ liệu hoặc JSON.

Quy ước label:

| Không ưu tiên | Ưu tiên hiển thị |
|---|---|
| Dashboard | Bảng điều khiển |
| Single Analysis | Phân tích một mã |
| Scanner | Quét thị trường |
| Journal | Nhật ký |
| Settings | Cài đặt |
| AI Provider | Nhà cung cấp AI |
| Model | Mô hình |
| Test API Key | Kiểm tra khóa API |
| Entry Zone | Vùng vào lệnh |
| Stop Loss | Cắt lỗ |
| Take Profit | Chốt lời |
| Direction Bias | Thiên hướng |
| Trade Permission | Quyền giao dịch |

Trong code UI nên có file từ điển thuật ngữ dùng chung, ví dụ `config/terminology.json` hoặc `ui/terminology.py`, để không dịch rải rác trong từng màn hình.

### Cách tổ chức 8 màn hình trong PyQt6

8 màn hình trong tài liệu là 8 **view** logic. Khi code có thể gom trong 5 khu vực navigation chính:

| Khu vực navigation | View bên trong |
|---|---|
| Bảng điều khiển | Dashboard |
| Phân tích | Single Analysis Input, Single Analysis Result |
| Quét thị trường | Scanner, Scanner Detail |
| Nhật ký | Journal, Journal Detail |
| Cài đặt | Settings với các tab AI, MT5, Giao dịch, Hiển thị, Nâng cao |

Tên file UI đề xuất:

```text
ui/screens/
  dashboard_screen.py
  single_analysis_input_screen.py
  single_analysis_result_screen.py
  scanner_screen.py
  scanner_detail_screen.py
  journal_screen.py
  journal_detail_screen.py
  settings_screen.py
```

Nếu tách chart thành file riêng, file đó chỉ nên là component/view phụ dùng lại cho màn hình kết quả, không thay thế `single_analysis_result_screen.py`.

### Nguyên tắc thiết kế chart nhúng

Chart là một phần quan trọng của trải nghiệm, không phải phần phụ.

- Màn hình kết quả nên chia 2 vùng: bên trái là chart `QWebEngineView`, bên phải là panel quyết định và kế hoạch giao dịch.
- Chart nhận payload OHLCV/indicator/zone đã được Python chuẩn hóa, không tự gọi MT5.
- Các vùng SMC như supply/demand, order block, FVG, liquidity pool nên được truyền sang chart bằng JSON layer.
- Khi chưa có dữ liệu, chart hiển thị empty state tiếng Việt ngắn: `Chưa có dữ liệu biểu đồ`.
- Khi chart lỗi, UI không crash; hiển thị lỗi ngắn và có nút thử lại.

### Điểm cần tránh khi AI lập trình

- Không dựng toàn bộ app bằng một file `main.py`.
- Không dùng Streamlit, web server hoặc browser ngoài.
- Không đưa Base URL, temperature, max tokens, timeout, retry ra UI cấu hình AI chính.
- Không hard-code chỉ 7 cặp Forex chính; mọi dropdown và scanner phải lấy từ danh sách 28 cặp Forex + XAU/USD.
- Không giả định symbol MT5 luôn không có hậu tố; phải kiểm tra cả dạng `m` và `c`, ví dụ `USDCADm`, `USDCADc`, `NZDUSDm`, `NZDUSDc`.
- Không gọi AI cho toàn bộ 29 mã ngay trong Scanner; quét bằng rule engine trước, chỉ gọi AI cho mã thật sự đáng chú ý.
- Không để label tiếng Anh dài chiếm giao diện nếu có thể dịch ngắn sang tiếng Việt.

---

# 2. Thiết kế chi tiết từng màn hình

---

## Màn hình 1: Dashboard (Bảng điều khiển tổng quan)

### Mục đích

Dashboard (Bảng điều khiển tổng quan) là màn hình đầu tiên khi mở phần mềm. Màn hình này giúp người dùng biết ngay hệ thống đã sẵn sàng phân tích hay chưa.

Người dùng cần thấy rõ:

- MT5 Status (trạng thái MT5).
- Broker Login (trạng thái đăng nhập sàn giao dịch).
- AI Provider (nhà cung cấp AI) đã cấu hình hay chưa.
- Data Source (nguồn dữ liệu) đang dùng.
- Các nút vào Single Analysis Mode (chế độ phân tích một mã), Scanner Mode (chế độ quét thị trường), Journal (nhật ký) và Settings (cài đặt).

### Bố cục màn hình

```text
AI Market Analyst (Nhà phân tích thị trường AI)
Công cụ phân tích Forex (thị trường ngoại hối) cá nhân bằng dữ liệu MT5 (MetaTrader 5) và AI (trí tuệ nhân tạo)

--------------------------------------------------
SYSTEM STATUS (TRẠNG THÁI HỆ THỐNG)
--------------------------------------------------

MT5 Status (trạng thái MT5): Connected (đã kết nối) / Not Connected (chưa kết nối)
Broker Login (trạng thái đăng nhập sàn giao dịch): Logged In (đã đăng nhập) / Not Logged In (chưa đăng nhập)
AI Provider (nhà cung cấp AI): Configured (đã cấu hình) / Not Configured (chưa cấu hình)
Data Source (nguồn dữ liệu): MetaTrader5 (MetaTrader 5)
Timezone (múi giờ): Asia/Ho_Chi_Minh (giờ Việt Nam)

Nếu MT5 (MetaTrader 5) chưa kết nối:

🔴 Không kết nối được MT5 (MetaTrader 5).

Vui lòng:
1. Mở MetaTrader 5.
2. Đăng nhập tài khoản broker (sàn giao dịch).
3. Kiểm tra symbol (mã giao dịch) trong Market Watch (bảng theo dõi thị trường).
4. Bấm Retry (thử lại).

[Retry MT5 Connection (Thử kết nối lại MT5)]

--------------------------------------------------
SELECT ANALYSIS MODE (CHỌN CHẾ ĐỘ PHÂN TÍCH)
--------------------------------------------------

[Single Analysis Mode (Chế độ phân tích một mã)]
Dùng khi muốn phân tích kỹ một symbol (mã giao dịch) cụ thể như XAU/USD (vàng giao ngay so với USD) hoặc EUR/USD (Euro so với đô la Mỹ).

[Scanner Mode (Chế độ quét thị trường)]
Dùng khi muốn quét nhanh toàn bộ 28 cặp Forex + XAU/USD để tìm setup (thiết lập giao dịch) đáng chú ý.

[Open Journal (Mở nhật ký)]
Xem lại các phân tích đã lưu.

[Settings (Cài đặt)]
Cấu hình AI Provider (nhà cung cấp AI), MT5 Data (dữ liệu MT5), Trading Settings (cài đặt giao dịch) và Display Settings (cài đặt hiển thị).
```

### Thành phần bắt buộc

- Card (thẻ thông tin) MT5 Status (trạng thái MT5).
- Card (thẻ thông tin) Broker Login (trạng thái đăng nhập sàn giao dịch).
- Card (thẻ thông tin) AI Provider (nhà cung cấp AI).
- Card (thẻ thông tin) Data Source (nguồn dữ liệu).
- Nút Retry MT5 Connection (thử kết nối lại MT5).
- Nút Single Analysis Mode (chế độ phân tích một mã).
- Nút Scanner Mode (chế độ quét thị trường).
- Nút Journal (nhật ký).
- Nút Settings (cài đặt).

---

## Màn hình 2: Single Analysis Input (Màn hình nhập phân tích một mã)

### Mục đích

Single Analysis Input (Màn hình nhập phân tích một mã) cho phép người dùng chọn symbol (mã giao dịch), broker symbol (mã giao dịch theo broker), số dư tài khoản và mức rủi ro trước khi chạy phân tích.

### Bố cục màn hình

```text
Single Analysis Mode (Chế độ phân tích một mã)

--------------------------------------------------
ANALYSIS INPUT (THÔNG TIN PHÂN TÍCH)
--------------------------------------------------

Symbol (mã giao dịch):
[ EUR/USD (Euro so với đô la Mỹ) ▼ ]

Broker Symbol (mã giao dịch theo broker):
[ EURUSDm ]

Timeframes (các khung thời gian sử dụng):
[x] D1 - Daily (nến ngày)
[x] H4 - 4-hour (nến 4 giờ)
[x] H1 - 1-hour (nến 1 giờ)

Data Source (nguồn dữ liệu):
MetaTrader5 Python API (API Python của MetaTrader 5)

--------------------------------------------------
ACCOUNT & RISK (TÀI KHOẢN VÀ RỦI RO)
--------------------------------------------------

Account Balance (số dư tài khoản):
[ 10000 ]

Risk Percent (phần trăm rủi ro mỗi lệnh):
[ 1.0 % ]

Timezone (múi giờ hiển thị):
[ Asia/Ho_Chi_Minh (giờ Việt Nam) ▼ ]

--------------------------------------------------
DATA CHECK (KIỂM TRA DỮ LIỆU)
--------------------------------------------------

MT5 Status (trạng thái MT5): Connected (đã kết nối)
Broker Login (trạng thái đăng nhập sàn giao dịch): Logged In (đã đăng nhập)
Spread (chênh lệch giá mua-bán): Normal (bình thường)
Last Candle Time (thời gian nến cuối): 2026-05-29 14:00 VN
Missing Candles (số nến thiếu): 0

[Analyze (Phân tích)]
```

### Trường dữ liệu

| Trường | Ý nghĩa |
|---|---|
| Symbol (mã giao dịch) | Mã hiển thị trong phần mềm, ví dụ XAU/USD, EUR/USD |
| Broker Symbol (mã giao dịch theo broker) | Mã thật trong MT5 (MetaTrader 5), ví dụ XAUUSDm, EURUSDm |
| Timeframes (các khung thời gian) | D1 (nến ngày), H4 (nến 4 giờ), H1 (nến 1 giờ) |
| Account Balance (số dư tài khoản) | Số dư dùng để tính Position Sizing (khối lượng vào lệnh) |
| Risk Percent (phần trăm rủi ro) | Tỷ lệ rủi ro tối đa cho mỗi lệnh |
| Timezone (múi giờ) | Múi giờ hiển thị dữ liệu |

### Logic hiển thị lỗi

Nếu MT5 (MetaTrader 5) chưa sẵn sàng, màn hình hiển thị:

```text
🔴 Không thể phân tích vì MT5 (MetaTrader 5) chưa sẵn sàng.

Trade Permission (quyền cho phép giao dịch): Blocked (bị chặn)
Reason (lý do): Không kết nối được MT5 (MetaTrader 5).

[Retry (Thử lại)]
[Open Settings (Mở cài đặt)]
```

Không cho bấm Analyze (phân tích) nếu:

- MT5 (MetaTrader 5) chưa kết nối.
- Broker (sàn giao dịch) chưa đăng nhập.
- Symbol Mapping (ánh xạ mã giao dịch) sai.
- Không lấy được OHLCV (giá mở cửa/cao nhất/thấp nhất/đóng cửa/khối lượng).

---

## Màn hình 3: Single Analysis Result (Màn hình kết quả phân tích một mã)

### Mục đích

Single Analysis Result (Màn hình kết quả phân tích một mã) là màn hình quan trọng nhất. Màn hình này hiển thị báo cáo đầy đủ gồm Decision (kết luận), Market Regime (trạng thái thị trường), Direction Bias (thiên hướng giao dịch), Setup Quality Score (điểm chất lượng kịch bản), Trade Plan (kế hoạch giao dịch), Position Sizing (tính khối lượng vào lệnh), Data Quality (chất lượng dữ liệu) và AI Commentary (nhận định AI).

### Bố cục màn hình

```text
Single Analysis Result (Kết quả phân tích một mã)

Symbol (mã giao dịch): XAU/USD (vàng giao ngay so với USD)
Broker Symbol (mã giao dịch theo broker): XAUUSDm
Analysis Time (thời gian phân tích): 2026-05-29 14:30 VN
Data Source (nguồn dữ liệu): MetaTrader5 (MetaTrader 5)

--------------------------------------------------
1. DECISION SUMMARY (TÓM TẮT QUYẾT ĐỊNH)
--------------------------------------------------

Decision (kết luận): Watch (theo dõi) / Ready (sẵn sàng) / Wait (chờ) / Stand Aside (đứng ngoài)

Preferred Scenario (kịch bản ưu tiên):
BUY (mua) XAU/USD nếu giá giữ trên vùng hỗ trợ 2330–2337.

Alternative Scenario (kịch bản thay thế):
SELL (bán) nếu H1 (nến 1 giờ) đóng dưới vùng hỗ trợ chính và MACD (chỉ báo động lượng MACD) tiếp tục suy yếu.

Stand Aside Reason (lý do đứng ngoài):
Đứng ngoài nếu giá nằm giữa vùng, Risk/Reward — R:R (tỷ lệ rủi ro/lợi nhuận) không đủ tốt hoặc có tin đỏ trong 3 giờ tới.

Trade Permission (quyền cho phép giao dịch):
Caution (cẩn trọng)

Reason (lý do):
Có tin USD (đô la Mỹ) quan trọng trong ngày, nên chờ xác nhận H1 (nến 1 giờ).

--------------------------------------------------
2. MARKET REGIME & DIRECTION BIAS (TRẠNG THÁI THỊ TRƯỜNG VÀ THIÊN HƯỚNG GIAO DỊCH)
--------------------------------------------------

Market Regime (trạng thái thị trường):
Primary (chính): trend_up (xu hướng tăng)
Secondary (phụ): news_sensitive (nhạy tin tức)

Direction Bias (thiên hướng giao dịch):
Buy (ưu tiên mua)

Giải thích:
D1 (nến ngày) đang trên EMA200 (đường trung bình động hàm mũ 200), H4 (nến 4 giờ) có cấu trúc tăng nhưng H1 (nến 1 giờ) cần xác nhận lại tại vùng hỗ trợ.

--------------------------------------------------
3. SETUP QUALITY SCORE (ĐIỂM CHẤT LƯỢNG KỊCH BẢN)
--------------------------------------------------

Buy Scenario Score (điểm kịch bản mua): 78 / 100
Sell Scenario Score (điểm kịch bản bán): 42 / 100

Bảng điểm BUY (mua):

Trend Alignment (mức độ thuận xu hướng): 22 / 25
Momentum Alignment (mức độ thuận động lượng): 14 / 20
Location Quality (chất lượng vị trí giá): 20 / 25
Risk Condition (điều kiện rủi ro): 10 / 15
Macro Alignment (mức độ thuận vĩ mô): 12 / 15

Bảng điểm SELL (bán):

Trend Alignment (mức độ thuận xu hướng): 5 / 25
Momentum Alignment (mức độ thuận động lượng): 10 / 20
Location Quality (chất lượng vị trí giá): 8 / 25
Risk Condition (điều kiện rủi ro): 10 / 15
Macro Alignment (mức độ thuận vĩ mô): 9 / 15

--------------------------------------------------
4. TRADE PLAN (KẾ HOẠCH GIAO DỊCH)
--------------------------------------------------

Kịch bản BUY (mua):

Entry Zone (vùng vào lệnh):
2330.0 – 2337.5

Stop Loss — SL (cắt lỗ):
2325.5

Take Profit — TP (chốt lời):
TP1 (mục tiêu chốt lời 1): 2355.0
TP2 (mục tiêu chốt lời 2): 2370.0

Risk/Reward — R:R (tỷ lệ rủi ro/lợi nhuận):
TP1: 1:2.1
TP2: 1:3.4

Condition to Enter (điều kiện kích hoạt lệnh):
- H1 (nến 1 giờ) đóng nến tăng tại vùng hỗ trợ.
- Giá không phá xuống dưới 2330.
- Spread (chênh lệch giá mua-bán) vẫn ở trạng thái Normal (bình thường).
- Không vào lệnh trong 15 phút trước/sau tin đỏ.

Invalidation (điều kiện vô hiệu kịch bản):
- H1 (nến 1 giờ) đóng dưới 2325.5.
- Spread (chênh lệch giá mua-bán) giãn bất thường.
- Tin tức làm giá phá mạnh ngược kịch bản.

--------------------------------------------------
5. POSITION SIZING (TÍNH KHỐI LƯỢNG VÀO LỆNH)
--------------------------------------------------

Account Balance (số dư tài khoản): 10,000 USD
Risk Percent (phần trăm rủi ro mỗi lệnh): 1%
Risk Amount (số tiền rủi ro): 100 USD
Entry Price Used (giá vào lệnh dùng để tính): 2335.0
Stop Loss — SL (cắt lỗ): 2325.5
Stop Distance (khoảng cách từ entry đến SL): 9.5 USD

Suggested Lot (khối lượng đề xuất):
0.10 lot

Ghi chú:
Lot (khối lượng giao dịch) chỉ là khối lượng tham khảo theo Contract Size (quy mô hợp đồng) từ broker (sàn giao dịch) trong MT5 (MetaTrader 5).

--------------------------------------------------
6. DATA QUALITY (CHẤT LƯỢNG DỮ LIỆU)
--------------------------------------------------

Price Source (nguồn giá): MT5 (MetaTrader 5)
Terminal Connected (kết nối terminal): True (đúng)
Broker Logged In (đã đăng nhập broker): True (đúng)
Broker (sàn giao dịch): Broker name
Last Candle Time UTC (thời gian nến cuối theo UTC): 2026-05-29T07:00:00Z
Last Candle Time VN (thời gian nến cuối theo giờ Việt Nam): 2026-05-29 14:00
Missing Candles (số nến thiếu): 0
Spread Points (spread theo point): 22
Spread Status (trạng thái spread): Normal (bình thường)
Warning (cảnh báo): None (không có)

--------------------------------------------------
7. AI COMMENTARY (NHẬN ĐỊNH AI)
--------------------------------------------------

Nhận định AI hiển thị dạng 4 mục bullet ngắn gọn, mỗi mục có giới hạn số dòng:

```text
1. Tình hình vĩ mô
- [tóm tắt yếu tố ảnh hưởng chính của base/quote currency, stance trung lập/hawkish/dovish]
- [nếu có latest_statements thì thêm dòng "Tin mới nhất:"]
- [nếu không có dữ liệu: "chưa đủ dữ liệu vĩ mô"]

2. Sự kiện kinh tế sắp tới
- DD-MM-YYYY HH:MM: tên sự kiện tiếng Việt -> ảnh hưởng tới đồng tiền đang xét
- [chỉ liệt kê high-impact, các sự kiện thấp hơn gộp 1 dòng]
- [nếu không có dữ liệu: "Chưa có dữ liệu sự kiện kinh tế sắp tới."]

3. Nhận định theo số liệu tính toán
- [trạng thái thị trường, thiên hướng, quyền giao dịch]
- [điểm mua/bán, vùng vào lệnh, SL/TP nếu có]
- [không tự bịa giá; chỉ dùng entry_context và computed_trade_plan]

4. Lời khuyên hành động
- [sẵn sàng / theo dõi / chờ / đứng ngoài]
- [điều kiện xác nhận, điều kiện vô hiệu]
- [nếu không có setup sạch: "Không có thiết lập giao dịch sạch (No clean setup)"]
```

Quy tắc format bắt buộc:
- Mỗi dòng là một bullet bắt đầu bằng "- ".
- Không dùng markdown bold/italic/dấu *.
- Mỗi lần thuật ngữ tiếng Anh xuất hiện lần đầu phải kèm tiếng Việt trong ngoặc đơn.
- Section 2 (sự kiện kinh tế) được sinh từ dữ liệu economic_events đã có sẵn, không qua AI.
- Giới hạn số bullet mỗi section: 3 / 5 / 5 / 3. Tổng tối đa 16 bullet.
- Tất cả thời gian hiển thị theo múi giờ người dùng đã chọn.
- Không dùng cụm "dữ liệu AI nội bộ"; ghi đúng là dữ liệu rule engine hoặc dữ liệu vĩ mô của app.

Khi AI chưa cấu hình: dùng template fallback có sẵn trong code, vẫn giữ đúng 4 section.

--------------------------------------------------
8. ACTIONS (THAO TÁC)
--------------------------------------------------

[Save to Journal (Lưu vào nhật ký)]
[Export JSON (Xuất dữ liệu JSON)]
[Run Again (Phân tích lại)]
[Back to Single Analysis (Quay lại phân tích một mã)]
```

### Thành phần bắt buộc

Mỗi kết quả phân tích phải luôn có:

- Preferred Scenario (kịch bản ưu tiên).
- Alternative Scenario (kịch bản thay thế).
- Stand Aside Reason (lý do đứng ngoài).
- Setup Quality Score (điểm chất lượng kịch bản).
- Condition to Enter (điều kiện kích hoạt lệnh).
- Invalidation (điều kiện vô hiệu kịch bản).
- Entry Zone (vùng vào lệnh).
- Stop Loss — SL (cắt lỗ).
- Take Profit — TP (chốt lời).
- Risk/Reward — R:R (tỷ lệ rủi ro/lợi nhuận).
- Position Sizing (tính khối lượng vào lệnh).
- Data Quality (chất lượng dữ liệu).

---

## Màn hình 4: Scanner (Màn hình quét thị trường)

### Mục đích

Scanner (Màn hình quét thị trường) dùng để quét nhanh toàn bộ 28 cặp Forex + XAU/USD, xếp hạng setup (thiết lập giao dịch) đáng chú ý và giúp người dùng chọn mã cần xem chi tiết.

### Bố cục màn hình

```text
Scanner Mode (Chế độ quét thị trường)

--------------------------------------------------
SCAN SETTINGS (THIẾT LẬP QUÉT)
--------------------------------------------------

Symbol List (danh sách mã):
[x] All Supported Symbols (28 cặp Forex + XAU/USD)

Hoặc chọn thủ công:
[x] EUR/USD (Euro so với đô la Mỹ)
[x] GBP/USD (Bảng Anh so với đô la Mỹ)
[x] AUD/USD (đô la Úc so với đô la Mỹ)
[x] NZD/USD (đô la New Zealand so với đô la Mỹ)
[x] USD/JPY (đô la Mỹ so với Yên Nhật)
[x] USD/CAD (đô la Mỹ so với đô la Canada)
[x] USD/CHF (đô la Mỹ so với Franc Thụy Sĩ)
[x] EUR/GBP, EUR/JPY, EUR/CHF, EUR/AUD, EUR/NZD, EUR/CAD
[x] GBP/JPY, GBP/CHF, GBP/AUD, GBP/NZD, GBP/CAD
[x] CHF/JPY, AUD/JPY, NZD/JPY, CAD/JPY
[x] AUD/CHF, NZD/CHF, CAD/CHF, AUD/NZD, AUD/CAD, NZD/CAD
[x] XAU/USD (vàng giao ngay so với USD)

Account Balance (số dư tài khoản):
[ 10000 ]

Risk Percent (phần trăm rủi ro mỗi lệnh):
[ 1.0 % ]

AI Detail Limit (số mã tối đa gọi AI để viết chi tiết):
[ 3 ]

[Scan Market (Quét thị trường)]

--------------------------------------------------
SCAN STATUS (TRẠNG THÁI QUÉT)
--------------------------------------------------

MT5 Status (trạng thái MT5): Connected (đã kết nối)
Symbols Scanned (số mã đã quét): 7 / 7
AI Called For (số mã đã gọi AI): 2 symbols (2 mã)
Last Scan Time (thời gian quét gần nhất): 2026-05-29 14:35 VN

--------------------------------------------------
SCANNER RESULT TABLE (BẢNG KẾT QUẢ QUÉT)
--------------------------------------------------

| Rank (xếp hạng) | Symbol (mã) | Action (hành động) | Bias (thiên hướng) | Permission (quyền giao dịch) | Best Score (điểm tốt nhất) | Buy Score (điểm mua) | Sell Score (điểm bán) | R:R (tỷ lệ rủi ro/lợi nhuận) | Main Reason (lý do chính) | View (xem) |
|---:|---|---|---|---|---:|---:|---:|---|---|---|
| 1 | XAU/USD | Watch (theo dõi) | Buy (mua) | Caution (cẩn trọng) | 78 | 78 | 42 | 1:2.1 | Gần Support Zone (vùng hỗ trợ) mạnh | View Detail (xem chi tiết) |
| 2 | EUR/USD | Wait (chờ) | Neutral (trung lập) | Allowed (được phép) | 66 | 61 | 66 | - | Giá đang ở giữa vùng | View Detail (xem chi tiết) |
| 3 | USD/JPY | Skip (bỏ qua) | Sell (bán) | Blocked (bị chặn) | 48 | 35 | 48 | - | Có tin đỏ gần giờ | View Detail (xem chi tiết) |

--------------------------------------------------
ACTION MEANING (Ý NGHĨA HÀNH ĐỘNG)
--------------------------------------------------

Ready (sẵn sàng): Có thể xem xét vào lệnh nếu đủ xác nhận.
Watch (theo dõi): Đáng theo dõi, nhưng còn thiếu điều kiện vào lệnh.
Wait (chờ): Chờ thêm, setup (thiết lập giao dịch) chưa rõ.
Skip (bỏ qua): Bỏ qua vì điểm thấp hoặc rủi ro cao.
```

### Cột bắt buộc trong bảng Scanner (bảng quét thị trường)

| Cột | Ý nghĩa |
|---|---|
| Rank (xếp hạng) | Thứ tự ưu tiên theo Best Score (điểm tốt nhất) |
| Symbol (mã giao dịch) | Mã được quét |
| Action (hành động) | Ready (sẵn sàng), Watch (theo dõi), Wait (chờ), Skip (bỏ qua) |
| Bias (thiên hướng) | Buy (mua), Sell (bán), Neutral (trung lập), Stand Aside (đứng ngoài) |
| Permission (quyền giao dịch) | Allowed (được phép), Caution (cẩn trọng), Blocked (bị chặn) |
| Best Score (điểm tốt nhất) | Điểm cao nhất giữa Buy Score (điểm mua) và Sell Score (điểm bán) |
| Buy Score (điểm mua) | Điểm chất lượng kịch bản mua |
| Sell Score (điểm bán) | Điểm chất lượng kịch bản bán |
| R:R (tỷ lệ rủi ro/lợi nhuận) | Risk/Reward (tỷ lệ rủi ro/lợi nhuận), nếu có kế hoạch giao dịch |
| Main Reason (lý do chính) | Lý do mã được xếp hạng như vậy |
| View Detail (xem chi tiết) | Mở màn hình Scanner Detail (chi tiết mã từ quét thị trường) |

### Logic gọi AI trong Scanner (màn hình quét thị trường)

Scanner (màn hình quét thị trường) không gọi AI cho tất cả mã ngay từ đầu. AI chỉ được gọi khi:

```text
Best Score (điểm tốt nhất) >= 75
Trade Permission (quyền cho phép giao dịch) != Blocked (bị chặn)
```

Nếu có nhiều mã đạt điều kiện, MVP (phiên bản khả dụng tối thiểu) chỉ gọi AI cho tối đa 3 mã có điểm cao nhất.

---

## Màn hình 5: Scanner Detail (Màn hình chi tiết mã từ quét thị trường)

### Mục đích

Scanner Detail (Màn hình chi tiết mã từ quét thị trường) mở ra khi người dùng bấm View Detail (xem chi tiết) ở bảng Scanner (bảng quét thị trường). Màn hình này hiển thị phân tích đầy đủ của mã đã chọn.

### Bố cục màn hình

```text
Scanner Detail (Chi tiết mã từ Scanner - quét thị trường)

Symbol (mã giao dịch): XAU/USD (vàng giao ngay so với USD)
Rank in Scanner (xếp hạng trong bảng quét): #1
Scanner Action (hành động từ quét thị trường): Watch (theo dõi)
Best Score (điểm tốt nhất): 78 / 100
Trade Permission (quyền cho phép giao dịch): Caution (cẩn trọng)

[Back to Scanner (Quay lại màn hình quét thị trường)]

--------------------------------------------------
SCANNER SUMMARY (TÓM TẮT TỪ MÀN HÌNH QUÉT)
--------------------------------------------------

Lý do mã này được xếp hạng cao:
- Buy Score (điểm mua) cao hơn Sell Score (điểm bán).
- Giá gần Support Zone (vùng hỗ trợ) mạnh.
- Risk/Reward — R:R (tỷ lệ rủi ro/lợi nhuận) đạt yêu cầu.
- Tuy nhiên có yếu tố tin tức nên Trade Permission (quyền giao dịch) là Caution (cẩn trọng).

--------------------------------------------------
FULL ANALYSIS (PHÂN TÍCH ĐẦY ĐỦ)
--------------------------------------------------

1. Decision Summary (tóm tắt quyết định)
2. Market Regime (trạng thái thị trường)
3. Direction Bias (thiên hướng giao dịch)
4. Setup Quality Score (điểm chất lượng kịch bản)
5. Trade Plan (kế hoạch giao dịch)
6. Position Sizing (tính khối lượng vào lệnh)
7. Data Quality (chất lượng dữ liệu)
8. AI Commentary (nhận định AI)
9. Actions (thao tác)
```

### Nút chức năng

```text
[Back to Scanner (Quay lại màn hình quét thị trường)]
[Save to Journal (Lưu vào nhật ký)]
[Export JSON (Xuất dữ liệu JSON)]
[Run Full Analysis Again (Chạy lại phân tích đầy đủ)]
```

---

## Màn hình 6: Journal (Màn hình nhật ký phân tích)

### Mục đích

Journal (Màn hình nhật ký phân tích) hiển thị danh sách các phân tích đã lưu vào SQLite (cơ sở dữ liệu SQLite). Người dùng có thể lọc theo ngày, mã giao dịch, kết luận và điểm số.

### Bố cục màn hình

```text
Journal (Nhật ký phân tích)

--------------------------------------------------
FILTERS (BỘ LỌC)
--------------------------------------------------

Date Range (khoảng thời gian):
[ 2026-05-01 ] đến [ 2026-05-29 ]

Symbol (mã giao dịch):
[ All (tất cả) ▼ ]

Decision (kết luận):
[ All (tất cả) / Ready (sẵn sàng) / Watch (theo dõi) / Wait (chờ) / Stand Aside (đứng ngoài) ▼ ]

Trade Permission (quyền cho phép giao dịch):
[ All (tất cả) / Allowed (được phép) / Caution (cẩn trọng) / Blocked (bị chặn) ▼ ]

Minimum Score (điểm tối thiểu):
[ 0 ]

[Apply Filter (Áp dụng bộ lọc)]
[Clear Filter (Xóa bộ lọc)]

--------------------------------------------------
JOURNAL LIST (DANH SÁCH NHẬT KÝ)
--------------------------------------------------

| Time (thời gian) | Symbol (mã) | Mode (chế độ) | Decision (kết luận) | Bias (thiên hướng) | Buy Score (điểm mua) | Sell Score (điểm bán) | Permission (quyền giao dịch) | Saved Note (ghi chú đã lưu) | Open (mở) |
|---|---|---|---|---|---:|---:|---|---|---|
| 2026-05-29 14:35 | XAU/USD | Scanner Detail (chi tiết từ quét) | Watch (theo dõi) | Buy (mua) | 78 | 42 | Caution (cẩn trọng) | Chờ H1 xác nhận | Open (mở) |
| 2026-05-29 10:20 | EUR/USD | Single Analysis (phân tích một mã) | Wait (chờ) | Neutral (trung lập) | 58 | 61 | Allowed (được phép) | Giá giữa vùng | Open (mở) |

--------------------------------------------------
QUICK STATS (THỐNG KÊ NHANH)
--------------------------------------------------

Total Analyses (tổng số phân tích): 24
Ready (sẵn sàng): 3
Watch (theo dõi): 7
Wait (chờ): 9
Stand Aside (đứng ngoài): 5

Most Analyzed Symbol (mã được phân tích nhiều nhất): XAU/USD (vàng giao ngay so với USD)
```

### Dữ liệu cần lưu trong Journal (nhật ký)

- Analysis Time (thời gian phân tích).
- Symbol (mã giao dịch).
- Broker Symbol (mã giao dịch theo broker).
- Mode (chế độ phân tích).
- Decision (kết luận).
- Direction Bias (thiên hướng giao dịch).
- Trade Permission (quyền cho phép giao dịch).
- Buy Score (điểm mua).
- Sell Score (điểm bán).
- Entry Zone (vùng vào lệnh), nếu có.
- Stop Loss — SL (cắt lỗ), nếu có.
- Take Profit — TP (chốt lời), nếu có.
- Suggested Lot (khối lượng đề xuất), nếu có.
- AI Commentary (nhận định AI).
- Raw JSON Output (dữ liệu JSON gốc).
- User Note (ghi chú cá nhân).

---

## Màn hình 7: Journal Detail (Màn hình chi tiết nhật ký)

### Mục đích

Journal Detail (Màn hình chi tiết nhật ký) dùng để xem lại một bản phân tích đã lưu. Người dùng có thể thêm hoặc sửa User Note (ghi chú cá nhân).

### Bố cục màn hình

```text
Journal Detail (Chi tiết nhật ký)

[Back to Journal (Quay lại nhật ký)]

--------------------------------------------------
GENERAL INFO (THÔNG TIN CHUNG)
--------------------------------------------------

Saved Time (thời gian lưu): 2026-05-29 14:35 VN
Symbol (mã giao dịch): XAU/USD (vàng giao ngay so với USD)
Broker Symbol (mã giao dịch theo broker): XAUUSDm
Mode (chế độ): Scanner Detail (chi tiết từ quét thị trường)
Data Source (nguồn dữ liệu): MT5 (MetaTrader 5)

--------------------------------------------------
SAVED DECISION (KẾT LUẬN ĐÃ LƯU)
--------------------------------------------------

Decision (kết luận): Watch (theo dõi)
Direction Bias (thiên hướng giao dịch): Buy (mua)
Trade Permission (quyền cho phép giao dịch): Caution (cẩn trọng)

Buy Score (điểm mua): 78 / 100
Sell Score (điểm bán): 42 / 100

--------------------------------------------------
SAVED TRADE PLAN (KẾ HOẠCH GIAO DỊCH ĐÃ LƯU)
--------------------------------------------------

Entry Zone (vùng vào lệnh): 2330.0 – 2337.5
Stop Loss — SL (cắt lỗ): 2325.5
Take Profit 1 — TP1 (chốt lời 1): 2355.0
Take Profit 2 — TP2 (chốt lời 2): 2370.0
Risk/Reward — R:R (tỷ lệ rủi ro/lợi nhuận) TP1: 1:2.1
Suggested Lot (khối lượng đề xuất): 0.10 lot

--------------------------------------------------
SAVED AI COMMENTARY (NHẬN ĐỊNH AI ĐÃ LƯU)
--------------------------------------------------

XAU/USD (vàng giao ngay so với USD) đang có thiên hướng tăng nhưng chưa nên mua đuổi...

--------------------------------------------------
USER NOTE (GHI CHÚ CÁ NHÂN)
--------------------------------------------------

[Chờ H1 (nến 1 giờ) đóng nến xác nhận rồi mới xem xét.]

[Save Note (Lưu ghi chú)]

--------------------------------------------------
ACTIONS (THAO TÁC)
--------------------------------------------------

[Run New Analysis With Same Symbol (Chạy phân tích mới với cùng mã)]
[Export JSON (Xuất dữ liệu JSON)]
[Delete Journal Entry (Xóa bản ghi nhật ký)]
```

### Ghi chú thiết kế

Journal Detail (Màn hình chi tiết nhật ký) không tự cập nhật dữ liệu mới. Đây là bản chụp lại phân tích tại thời điểm đã lưu. Nếu muốn cập nhật dữ liệu mới, người dùng bấm Run New Analysis With Same Symbol (chạy phân tích mới với cùng mã).

---

## Màn hình 8: Settings (Màn hình cài đặt)

### Mục đích

Settings (Màn hình cài đặt) dùng để cấu hình toàn bộ phần mềm. Màn hình này cần dễ hiểu với người không chuyên lập trình.

Settings (Màn hình cài đặt) nên chia thành 5 tab (thẻ chức năng):

```text
Settings (Cài đặt)

Tabs (các thẻ chức năng):
[AI Provider (Nhà cung cấp AI)]
[MT5 Data (Dữ liệu MT5)]
[Trading (Giao dịch)]
[Display (Hiển thị)]
[Advanced (Nâng cao)]
```

---

## 8.1. Tab AI Provider (Nhà cung cấp AI)

### Mục tiêu

Màn hình cấu hình AI phải cực kỳ đơn giản. Người dùng không cần hiểu Base URL, API format, timeout, token hoặc retry.

Người dùng chỉ làm 4 việc:

1. Chọn nhà cung cấp.
2. Chọn model.
3. Nhập API key.
4. Bấm kiểm tra API key.

Toàn bộ cấu hình kỹ thuật khác chạy ngầm theo default trong code.

### Bố cục

```text
Cài đặt AI

AI Enabled (bật AI):
[ On (bật) / Off (tắt) ]

Nhà cung cấp AI:
[ DeepSeek ▼ ]

Options:
- DeepSeek
- OpenAI
- Anthropic
- Claude

Model:
[ deepseek-v4-flash ▼ ]

API Key:
[ •••••••••••••••••••••••••••••••• ]

API Key đã lưu:
sk-****abcd

[Test API Key (Kiểm tra khóa API)]
[Save (Lưu)]
```

### Hành vi UI

- Khi đổi nhà cung cấp, dropdown Model tự đổi theo danh sách model của provider đó.
- API Key luôn nhập bằng ô password/masked.
- Nếu đã lưu API key, chỉ hiện preview dạng `sk-****abcd`.
- Không hiển thị Base URL, API Format, Temperature, Max Tokens, Timeout, Retry Count ở UI chính.
- Nút `Test API Key` bị disabled nếu thiếu provider, model hoặc API key.
- Khi test thành công, hiển thị: `Kết nối AI thành công`.
- Khi test thất bại, hiển thị lỗi ngắn: `Không kiểm tra được API key. Kiểm tra lại khóa, model hoặc kết nối mạng.`

### Cấu hình chạy ngầm

Các giá trị sau do app tự cấu hình theo provider/model:

- Base URL.
- API format.
- Temperature.
- Max tokens.
- Timeout seconds.
- Retry count.
- Model dùng cho macro và model dùng viết nhận định nếu cần tách nội bộ.

Không đưa các trường này ra giao diện người dùng phổ thông.

---

## 8.2. Tab MT5 Data (Dữ liệu MT5)

### Bố cục

```text
MT5 Data Settings (Cài đặt dữ liệu MT5)

--------------------------------------------------
CONNECTION STATUS (TRẠNG THÁI KẾT NỐI)
--------------------------------------------------

MT5 Status (trạng thái MT5): Connected (đã kết nối) / Not Connected (chưa kết nối)
Broker Login (trạng thái đăng nhập sàn giao dịch): Logged In (đã đăng nhập) / Not Logged In (chưa đăng nhập)
Broker Name (tên sàn giao dịch): Broker name
Account Server (máy chủ tài khoản): Server name

[Retry Connection (Thử kết nối lại)]

--------------------------------------------------
SYMBOL MAPPING (ÁNH XẠ MÃ GIAO DỊCH)
--------------------------------------------------

| Display Symbol (mã hiển thị) | Broker Symbol (mã trên broker) | Status (trạng thái) | Test (kiểm tra) |
|---|---|---|---|
| EUR/USD (Euro so với đô la Mỹ) | EURUSDm | OK (đạt) | Test (kiểm tra) |
| GBP/USD (Bảng Anh so với đô la Mỹ) | GBPUSDm | OK (đạt) | Test (kiểm tra) |
| AUD/USD (đô la Úc so với đô la Mỹ) | AUDUSDm | OK (đạt) | Test (kiểm tra) |
| NZD/USD (đô la New Zealand so với đô la Mỹ) | NZDUSDm hoặc NZDUSDc | OK (đạt) | Test (kiểm tra) |
| USD/JPY (đô la Mỹ so với Yên Nhật) | USDJPYm | OK (đạt) | Test (kiểm tra) |
| USD/CHF (đô la Mỹ so với Franc Thụy Sĩ) | USDCHFm | OK (đạt) | Test (kiểm tra) |
| USD/CAD (đô la Mỹ so với đô la Canada) | USDCADm hoặc USDCADc | OK (đạt) | Test (kiểm tra) |
| EUR/GBP (Euro so với Bảng Anh) | EURGBPm hoặc EURGBPc | OK (đạt) | Test (kiểm tra) |
| GBP/JPY (Bảng Anh so với Yên Nhật) | GBPJPYm hoặc GBPJPYc | OK (đạt) | Test (kiểm tra) |
| AUD/NZD (đô la Úc so với đô la New Zealand) | AUDNZDm hoặc AUDNZDc | OK (đạt) | Test (kiểm tra) |
| XAU/USD (vàng giao ngay so với USD) | XAUUSDm | OK (đạt) | Test (kiểm tra) |

Lưu ý: bảng mapping phải hỗ trợ đầy đủ 28 cặp Forex + XAU/USD. Nhiều broker MT5 thêm hậu tố `m` hoặc `c` vào symbol, ví dụ `USDCADm`, `USDCADc`, `NZDUSDm`, `NZDUSDc`; code không được giả định symbol luôn là dạng không hậu tố.

[Add Custom Mapping (Thêm ánh xạ tùy chỉnh)]
[Auto Detect Broker Symbols (Tự động phát hiện mã broker)]
[Save Mapping (Lưu ánh xạ)]

--------------------------------------------------
SPREAD THRESHOLD (NGƯỠNG CHÊNH LỆCH GIÁ MUA-BÁN)
--------------------------------------------------

| Symbol (mã) | Max Normal Spread (spread bình thường tối đa) | Current Spread (spread hiện tại) | Status (trạng thái) |
|---|---:|---:|---|
| XAU/USD (vàng giao ngay so với USD) | 30 points | 22 points | Normal (bình thường) |
| EUR/USD (Euro so với đô la Mỹ) | 20 points | 8 points | Normal (bình thường) |

--------------------------------------------------
MARKET WATCH (BẢNG THEO DÕI THỊ TRƯỜNG)
--------------------------------------------------

Auto-select symbol in Market Watch (tự động chọn mã trong bảng theo dõi thị trường):
[ On (bật) / Off (tắt) ]

[Save MT5 Settings (Lưu cài đặt MT5)]
```

### Cảnh báo bắt buộc

```text
🔴 Nếu MT5 (MetaTrader 5) chưa mở hoặc chưa đăng nhập broker (sàn giao dịch), hệ thống không tạo trạng thái Ready To Enter (sẵn sàng vào lệnh).
```

---

## 8.3. Tab Trading (Giao dịch)

### Bố cục

```text
Trading Settings (Cài đặt giao dịch)

Account Balance (số dư tài khoản mặc định):
[ 10000 ]

Account Currency (đồng tiền tài khoản):
[ USD (đô la Mỹ) ▼ ]

Default Risk Percent (phần trăm rủi ro mặc định mỗi lệnh):
[ 1.0 % ]

Max Risk Percent (phần trăm rủi ro tối đa cho phép):
[ 2.0 % ]

Lot Step (bước lot):
[ 0.01 ]

Minimum Lot (lot tối thiểu):
[ 0.01 ]

Maximum Lot (lot tối đa):
[ 5.00 ]

--------------------------------------------------
CONTRACT SIZE OVERRIDE (GHI ĐÈ QUY MÔ HỢP ĐỒNG)
--------------------------------------------------

| Symbol (mã) | Use Broker Value (dùng giá trị từ broker) | Contract Size Override (giá trị quy mô hợp đồng ghi đè) |
|---|---|---:|
| XAU/USD (vàng giao ngay so với USD) | Yes (có) | 100 |
| EUR/USD (Euro so với đô la Mỹ) | Yes (có) | 100000 |

[Save Trading Settings (Lưu cài đặt giao dịch)]
```

---

## 8.4. Tab Display (Hiển thị)

### Bố cục

```text
Display Settings (Cài đặt hiển thị)

Language (ngôn ngữ):
[ Vietnamese (tiếng Việt) ▼ ]

Timezone (múi giờ):
[ Asia/Ho_Chi_Minh (giờ Việt Nam) ▼ ]

Term Explanation Mode (chế độ giải thích thuật ngữ):
[ Always Show (luôn hiển thị) ▼ ]

Options (lựa chọn):
- Always Show (luôn hiển thị giải thích tiếng Việt)
- First Time Only (chỉ hiển thị lần đầu trên mỗi màn hình)
- Tooltip (hiển thị giải thích bằng chú thích nổi)

Number Format (định dạng số):
[ 1,234.56 ]

Theme (giao diện):
[ Light (sáng) / Dark (tối) ]

Default Landing Screen (màn hình mở mặc định):
[ Dashboard (bảng điều khiển tổng quan) ▼ ]

[Save Display Settings (Lưu cài đặt hiển thị)]
```

---

## 8.5. Tab Advanced (Nâng cao)

### Bố cục

```text
Advanced Settings (Cài đặt nâng cao)

Data Bars Per Timeframe (số nến lấy cho mỗi khung thời gian):
D1 - Daily (nến ngày): [ 500 ]
H4 - 4-hour (nến 4 giờ): [ 500 ]
H1 - 1-hour (nến 1 giờ): [ 500 ]

Scanner AI Detail Limit (số mã tối đa gọi AI trong màn hình quét):
[ 3 ]

High Impact News Block Before (thời gian chặn trước tin tức quan trọng):
[ 30 minutes (30 phút) ]

High Impact News Block After (thời gian chặn sau tin tức quan trọng):
[ 30 minutes (30 phút) ]

SQLite Database Path (đường dẫn cơ sở dữ liệu SQLite):
[ ./data/journal.db ]

Settings Storage (nơi lưu cài đặt):
[ settings.json ▼ ]

[Backup Settings (Sao lưu cài đặt)]
[Restore Settings (Khôi phục cài đặt)]
[Reset to Default (Đặt lại mặc định)]
```

---

# 3. Cấu trúc menu đề xuất

```text
AI Market Analyst (Nhà phân tích thị trường AI)
│
├── Dashboard (Bảng điều khiển tổng quan)
│
├── Single Analysis (Phân tích một mã)
│   ├── Single Analysis Input (Nhập phân tích một mã)
│   └── Single Analysis Result (Kết quả phân tích một mã)
│
├── Scanner (Quét thị trường)
│   ├── Scanner Table (Bảng quét thị trường)
│   └── Scanner Detail (Chi tiết mã từ quét thị trường)
│
├── Journal (Nhật ký phân tích)
│   ├── Journal List (Danh sách nhật ký)
│   └── Journal Detail (Chi tiết nhật ký)
│
└── Settings (Cài đặt)
    ├── AI Provider (Nhà cung cấp AI)
    ├── MT5 Data (Dữ liệu MT5)
    ├── Trading (Giao dịch)
    ├── Display (Hiển thị)
    └── Advanced (Nâng cao)
```

---

# 4. Kết luận

Phần mềm **AI Market Analyst (Nhà phân tích thị trường AI)** nên triển khai theo **8 màn hình chính** để đủ rõ ràng, dễ dùng và phù hợp với MVP (phiên bản khả dụng tối thiểu).

Cách tổ chức hợp lý nhất:

- Dashboard (Bảng điều khiển tổng quan) để kiểm tra hệ thống.
- Single Analysis (Phân tích một mã) để phân tích sâu từng mã.
- Scanner (Quét thị trường) để tìm nhanh mã đáng chú ý.
- Journal (Nhật ký phân tích) để lưu và xem lại phân tích.
- Settings (Cài đặt) để cấu hình AI (trí tuệ nhân tạo), MT5 (MetaTrader 5), rủi ro và giao diện.

Với MVP (phiên bản khả dụng tối thiểu), nên coi Settings (Cài đặt) là một màn hình lớn có nhiều tab (thẻ chức năng), thay vì tách thành nhiều màn hình riêng, để giao diện gọn và dễ thao tác hơn.

## Logic Updates

- Scanner table phai co cot Entry hien thi `price_vs_zone`: `Trong vung`, `Gan vung`, `Con xa` hoac `--`, kem mau xanh/vang/xam de trader thay ngay gia dang o dau so voi entry zone.
- Entry checklist muc `Xu huong` phai xet theo side cua setup; range market co the dat neu setup nam tai POI/bien gia tot, khong mac dinh fail.
- Man hinh ket qua nen hien `confidence_reason` co breakdown diem trend/momentum/location/risk/macro, macro confidence va event caution gan nhat neu co.

## Current Scanner Automation Behavior

- Scanner has two modes: one-shot scan and auto-scan.
- Auto-entry is attached only to auto-scan mode and requires the user to check `Tự động vào lệnh MT5`. The UI must not place MT5 orders from one-shot scan.
- The `Tự động vào lệnh MT5` toggle button must be visually highlighted when active, because enabling it can place real MT5 orders. Do not show a separate checkbox indicator inside this button; the whole button is the state indicator.
- When auto-scan is active and a row becomes `ready`, the user-facing result should still show the normal scanner table and Telegram alert. Auto-entry execution status is returned separately as `auto_trade_results`.
- Auto-entry status should be displayed or logged with these counts when surfaced in UI: attempted, opened, skipped, and errors.
- A skipped auto-entry is not a UI failure when the reason is "already has position/order"; it is the intended one-order-per-symbol guard.
- Telegram summary should remain short: scanned count, ready count, ready symbol list with Entry/SL/TP. Watch-only symbols are intentionally omitted from Telegram summary.
