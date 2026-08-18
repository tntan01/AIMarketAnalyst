# Thiết kế màn hình phần mềm AI Market Analyst (Nhà phân tích thị trường AI)

> Tài liệu này được xây dựng từ bản phân tích phần mềm **AI Market Analyst (Nhà phân tích thị trường AI)**.
> Quy ước hiển thị: giao diện ưu tiên tiếng Việt ngắn gọn. Thuật ngữ tiếng Anh chỉ giữ khi cần thiết và phải có giải thích tiếng Việt ở lần hiển thị đầu tiên, tooltip hoặc mô tả phụ. Ví dụ ưu tiên **Bảng điều khiển**, nếu cần có thể ghi **Bảng điều khiển (Dashboard)**.
>
> Scanner V2/Candidate Engine và scorer vẫn là runtime hiện hành. Thiết kế
> Scanner ngày 11/08/2026 là **APPROVED DESIGN — NON-RUNTIME**; các yêu cầu
> trong tài liệu này chỉ là target sau direct cutover.

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
| 8 | Settings (Màn hình cài đặt) | Cấu hình AI, dữ liệu MT5, giao dịch, hiển thị và nâng cao |
| 9 | Orders (Quản lý lệnh) | Theo dõi vị thế đang mở, lệnh chờ, BE & trailing stop tự động |

Nếu tính các tab (thẻ chức năng) bên trong Settings (Màn hình cài đặt), phần mềm có thể xem là **12 màn hình/tabs chức năng**:

1. Dashboard (Bảng điều khiển tổng quan)
2. Single Analysis Input (Màn hình nhập phân tích một mã)
3. Single Analysis Result (Màn hình kết quả phân tích một mã)
4. Scanner (Màn hình quét thị trường)
5. Scanner Detail (Màn hình chi tiết mã từ quét thị trường)
6. Journal (Màn hình nhật ký phân tích)
7. Journal Detail (Màn hình chi tiết nhật ký)
8. Settings - AI (Cài đặt AI)
9. Settings - Dữ liệu (Cài đặt dữ liệu MT5)
10. Settings - Trading (Cài đặt giao dịch)
11. Settings - Display (Cài đặt hiển thị)
12. Settings - Advanced (Cài đặt nâng cao)
13. Orders (Quản lý lệnh) — tab riêng trong sidebar

---

## 1.1. Kiểm tra lại thiết kế trước khi code UI

Thiết kế màn hình cần được hiểu theo hướng **desktop app PyQt6**, không phải web page dài. Khi lập trình, AI phải ưu tiên bố cục làm việc gọn trong một cửa sổ, có navigation cố định, vùng nội dung chính co giãn và các panel/tabs để chứa thông tin dài.

Quyết định thiết kế bắt buộc:

- Dùng `QMainWindow` làm khung chính.
- Khi mở chương trình, cửa sổ chính phải tự động chiếm toàn bộ vùng làm việc của màn hình bằng `showMaximized()`. Yêu cầu này áp dụng cho mọi kích thước màn hình và mọi mức Windows scaling như 100%, 125%, 150%. Đây là chế độ maximized desktop window, không phải borderless game fullscreen, để người dùng vẫn dùng được taskbar, Alt+Tab và window controls bình thường.
- Dùng sidebar hoặc top navigation để chuyển giữa 5 khu vực chính: Bảng điều khiển, Phân tích, Quét thị trường, Nhật ký, Cài đặt.
- Sidebar footer hiển thị dòng "Dữ liệu: MT5..." và nút "🔄 Khởi động lại" (font 11px, màu accent #0d9488 ở giao diện tối / #D94625 ở giao diện sáng, nền trong suốt, không border, hover: chữ sáng #2dd4bf ở giao diện tối / #E0533C ở giao diện sáng + underline, không đổi nền ở tất cả các trạng thái — phân biệt rõ với NavButton có background khi hover). Khi bấm: xác nhận Yes/No → shutdown MT5 → khởi chạy process mới → quit process hiện tại.
- Dùng `QStackedWidget` hoặc router tương đương để quản lý 8 màn hình chính.
- Dùng `QSplitter`, `QGridLayout`, `QHBoxLayout`, `QVBoxLayout` và stretch factor để giao diện co giãn tốt trên màn hình 1366x768 trở lên.
- Dùng `QTableView` + `QAbstractTableModel` cho bảng Scanner và Journal; không dựng bảng bằng nhiều label thủ công.
- Dùng `QTabWidget` cho Settings và các phần chi tiết dài trong màn hình kết quả.
- Dùng `QWebEngineView` để nhúng chart web trong màn hình kết quả phân tích và chi tiết scanner.
- Không để màn hình kết quả phân tích trở thành một trang dài phải cuộn nhiều. Phần thấy ngay phải có: kết luận, thiên hướng, quyền giao dịch, điểm mua/bán, entry, SL, TP, R:R, lot và trạng thái dữ liệu.
- Entry phải hiển thị kèm `entry_status` và `confirmation_score`. Nếu trạng thái là `watch_zone` hoặc `waiting_confirmation`, UI phải thể hiện rõ đây là vùng theo dõi/chờ xác nhận, không phải lệnh đã sẵn sàng.
- Kết quả phân tích phải có checklist entry dễ đọc gồm: Xu hướng, Vùng POI, Xác nhận H1, Tin tức, Spread, R:R, Lot. Mỗi dòng hiển thị trạng thái `Đạt` hoặc `Chờ`, giá trị liên quan và ghi chú ngắn.
- Kết quả phân tích phải có phần Replay/Backtest tóm tắt: số lệnh replay, win rate, expectancy R, average R, MFE/MAE trung bình, max drawdown và hiệu quả theo phiên. Phần này không thay thế quyết định vào lệnh realtime, chỉ dùng để kiểm chứng setup có lịch sử hợp lý hay không.
- Kết quả phân tích phải có phần Vĩ mô hiển thị assessment BUY/SELL, confidence,
  status, macro theme theo từng đồng tiền, Tin mới nhất, điểm nóng thế giới và
  lịch kinh tế. Trong target, phần này không được trình bày như component hay
  contribution của score. Nếu không có dữ liệu, phải hiển thị rõ “không có dữ
  liệu” thay vì để trống.
- Mục Tin mới nhất chỉ hiển thị headline thị trường và phát biểu đáng chú ý trong 24h qua, mỗi dòng riêng. Dòng tin mới nhất dùng mẫu `ngày-tháng-năm thời gian: nội dung tiếng Việt`; chỉ thêm `-> ảnh hưởng tới đồng tiền đang xét` khi đã có nhận định tác động cụ thể. Lịch kinh tế vẫn hiển thị tác động vì bản thân event có mức impact.
- Màn hình Scanner có phần Thiết lập quét cho phép chọn `Quét 1 lần` hoặc `Quét theo khoảng thời gian`; interval hỗ trợ M5, M15, H1, H4. Khi đang auto-scan phải có nút `Dừng quét tự động`.
- Khi mở tab Scanner lần đầu trong phiên, tự động chọn tất cả mã, đặt chế độ
  quét tự động M5 và chạy quét lần đầu sau 1.5 giây. Nút auto-trade khả dụng
  nhưng mặc định unchecked; lượt quét tự khởi động không yêu cầu đặt lệnh nếu
  người dùng chưa chủ động bật nút.
- Settings > Nâng cao có cấu hình Telegram gồm bot token, danh sách chat ID nhận alert và interval auto-scan mặc định. Chat ID có thể nhập nhiều giá trị, cách nhau bằng dấu phẩy.
- Các phần dài như nhận định AI, điểm thành phần, raw JSON, log kỹ thuật phải đưa vào tab, panel phụ hoặc dialog.
- Mọi tác vụ nặng như lấy dữ liệu MT5, gọi AI, quét 31 mã, tính indicator phải chạy qua worker/thread; UI không được bị đơ.

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
| Trade Permission | Cho phép đặt lệnh |

Trong code UI nên có file từ điển thuật ngữ dùng chung, ví dụ `config/terminology.json` hoặc `ui/terminology.py`, để không dịch rải rác trong từng màn hình.

### Cách tổ chức 8 màn hình trong PyQt6

8 màn hình trong tài liệu là 8 **view** logic. Khi code có thể gom trong 5 khu vực navigation chính:

| Khu vực navigation | View bên trong |
|---|---|
| Bảng điều khiển | Dashboard |
| Phân tích | Single Analysis Input, Single Analysis Result |
| Quét thị trường | Scanner, Scanner Detail |
| Nhật ký | Journal, Journal Detail |
| Cài đặt | Settings với các tab AI, Dữ liệu, Giao dịch, Hiển thị, Nâng cao |

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
- Không hard-code chỉ 7 cặp Forex chính; mọi dropdown và scanner phải lấy từ danh sách 28 cặp Forex + XAU/USD + XAG/USD + BTC/USD.
- Không giả định symbol MT5 luôn không có hậu tố; phải kiểm tra cả dạng `m` và `c`, ví dụ `USDCADm`, `USDCADc`, `NZDUSDm`, `NZDUSDc`.
- Không gọi AI cho toàn bộ danh sách mã ngay trong Scanner; quét bằng rule engine trước, chỉ gọi AI cho mã thật sự đáng chú ý.
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
Dùng khi muốn quét nhanh toàn bộ 28 cặp Forex + XAU/USD + XAG/USD + BTC/USD để tìm setup (thiết lập giao dịch) đáng chú ý.

[Open Journal (Mở nhật ký)]
Xem lại các phân tích đã lưu.

[Settings (Cài đặt)]
Cấu hình AI, dữ liệu MT5, giao dịch và hiển thị.
```

### Thành phần bắt buộc

- Card (thẻ thông tin) MT5 Status (trạng thái MT5) dạng 1 dòng ngang: chấm tròn màu 8px bên trái + text có emoji trạng thái (✅/🔴) và font 13px semi-bold, border 1px solid theo state (ok=#10b981, danger=#ef4444, warning=#f59e0b), chiều cao cố định 40px, nền transparent, không wrap text.
- Card (thẻ thông tin) Broker Login (trạng thái đăng nhập sàn giao dịch) đã thiết kế lại chuyên nghiệp tương tự.
- Card (thẻ thông tin) AI Provider (nhà cung cấp AI) đã thiết kế lại chuyên nghiệp tương tự.
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

Mẫu target Scanner (APPROVED DESIGN — NON-RUNTIME), regime `trending_up`:

Final / Setup Score BUY (điểm cuối/thiết lập mua): 78 / 100
Final / Setup Score SELL (điểm cuối/thiết lập bán): 42 / 100

Technical Signal BUY: 78 / 100
Evidence BUY: 80 / 100
Execution Quality BUY: 75 / 100

Technical Signal SELL: 42 / 100
Evidence SELL: 45 / 100
Execution Quality SELL: 38 / 100

Bảng điểm BUY (mua):

Trend contribution (đóng góp xu hướng): 34 điểm
Momentum contribution (đóng góp động lượng): 14 điểm
Location contribution (đóng góp vị trí): 14 điểm
SMC contribution (đóng góp cấu trúc SMC): 16 điểm

Bảng điểm SELL (bán):

Trend contribution (đóng góp xu hướng): 8 điểm
Momentum contribution (đóng góp động lượng): 10 điểm
Location contribution (đóng góp vị trí): 8 điểm
SMC contribution (đóng góp cấu trúc SMC): 16 điểm

Đánh giá tách khỏi bảng điểm:

- Market Safety Gate: CAUTION — có tin đỏ sau 30 phút nhưng trong 3 giờ tới.
- Macro Assessment BUY: aligned, confidence cao.
- Macro Assessment SELL: conflict, confidence trung bình.
- Macro Gate cho side đã chọn BUY: PASS — không cộng điểm.

Final/Setup score trong mẫu được blend `Technical × 65% + Evidence × 20% +
Execution × 15%` rồi làm tròn để hiển thị. Risk/Macro và output gate không được
tái nhập vào score; Gate hiển thị `PASS/CAUTION/BLOCK/UNKNOWN`, decision cap và
reason code.

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

## Màn hình 4: Scanner V2 — runtime contract hiện hành (25/07/2026)

> **Ranh giới version:** phần runtime bên dưới mô tả Candidate Engine V2 với
> scorer `scanner-v3` / `scanner-features-v3`. Target sẽ chuyển trực tiếp sang
> scorer/feature, không chạy song song và không dùng shadow làm score
> so sánh. Nguồn chuẩn target:
> [Scanner architecture](../scanner/scanner-architecture.md).

Ở target, breakdown điểm chỉ có Trend/Momentum/Location/SMC; UI đọc metadata
weight/breakdown theo contract và không định nghĩa lại bảng regime. UI phải
đặt `MarketSafetyGate`, `MacroAssessment` và `MacroGate` thành card/section riêng,
không đặt trong bảng cộng điểm. Final/Setup score phải ghi rõ ba input
Technical/Evidence/Execution theo tỷ trọng 65/20/15; không hiển thị Risk/Macro
như input thứ tư/thứ năm.

### Mục đích

Quét danh sách symbol, hiển thị canonical candidate decision và cho phép người
dùng mở chi tiết. Giao diện không tự suy luận trạng thái, side hoặc quyền đặt
lệnh từ các field legacy.

### Thành phần bắt buộc

- Bộ chọn phạm vi symbol, quét một lần/quét định kỳ và nút bắt đầu/dừng.
- Nút **Tự động vào lệnh MT5** chỉ được enable trong chế độ quét định kỳ, mặc
  định unchecked và được làm nổi khi người dùng bật. Trong quét một lần, nút
  phải disable và reset về unchecked. Tooltip phải cảnh báo việc bật nút có
  thể gửi lệnh thật nhưng vẫn chịu execution safety gates.
- Sau mỗi lần quét, chỉ hiển thị dòng trạng thái ngắn: số mã đã quét và thời
  gian quét gần nhất.
- Progress và thống kê theo sáu trạng thái candidate.
- Bảng model/view theo đúng `ScannerTableModel.COLUMNS`.
- Trong tab **Tổng quan**, cột card thông tin và biểu đồ dùng tỷ lệ mặc định
  `30% / 70%`. Biểu đồ mở mặc định ở khung **D1 (Ngày)**; nếu snapshot không
  có D1 thì lần lượt fallback H4, H1, M15. Mật độ nến mặc định ở mức trung bình
  (100 nến nhìn thấy, `barSpacing=7`) để không phóng nến quá lớn.
- Nút **Giải thích** có hai chế độ:
  - chưa chọn dòng: mở dialog ba cột theo style `EconTable`, mô tả chung đúng
    14 cột Scanner V2 bằng thuật ngữ tiếng Việt;
  - đã chọn một dòng: mở dialog `Giải thích chi tiết - <mã>`, ưu tiên 11 thông
    tin hỗ trợ quyết định: trạng thái, hướng, việc nên làm, lý do chính, chất
    lượng thiết lập, tỷ lệ lời/lỗ, mức sẵn sàng, bối cảnh thị trường, độ tin
    cậy dữ liệu lịch sử, điểm ưu tiên và nguồn quy tắc.
- Dialog theo dòng không diễn giải các điểm số thành xác suất thắng và luôn so
  sánh chất lượng thiết lập/tỷ lệ lời lỗ với ngưỡng tương ứng.
- ID, tên mã tại broker, chi tiết tính điểm, metadata vùng giá, phiên bản cách
  chấm và mã lý do nội bộ được đưa vào **Thông tin kỹ thuật**, ẩn mặc định và
  chỉ hiện khi người dùng bật `Hiển thị thông tin kỹ thuật`.
- Khu vực kết quả auto trade, Telegram và lỗi có reason code.
- Nút **Kế hoạch lệnh** phải mô tả đúng kết quả của chính lần quét đã lưu,
  không suy ngược từ trạng thái hiện tại của nút auto-entry. Dialog phải tách
  rõ số lệnh đã mở, đã kiểm tra, bỏ qua và bị guard chặn; không dùng câu
  “đã vào MT5” khi `opened=0`. Mã chặn phổ biến phải có giải thích tiếng Việt.

### Cột bảng hiện hành

| Key | Nhãn |
|---|---|
| `presentation_rank` | STT |
| `symbol` | Mã |
| `candidate_status` | Trạng thái |
| `selected_side` | Hướng |
| `market_regime` | Bối cảnh TT |
| `zone_origin_class` | Loại vùng |
| `price_vs_zone` | Vùng |
| `setup_score` | Điểm thiết lập |
| `opportunity_rank` | Ưu tiên |
| `evidence_confidence` | Tin cậy LS |
| `execution_readiness` | Sẵn sàng |
| `expected_effective_rr` | R:R dự kiến |
| `auto_trade_branch` | Quy tắc |
| `strategy_config_status` | Cấu hình BT |

Cột **Vùng** ánh xạ nhị phân: `in_zone` → **Trong vùng**; `near_zone`/`far` →
**Ngoài vùng**; `unknown`/thiếu dữ liệu/fallback → `--`. Trạng thái được tính
một lần tại thời điểm quét; không tự cập nhật real-time. Cột không tác động
auto-trade, không thay thế execution revalidation (vẫn dùng bid/ask live).

`opportunity_rank` là điểm xếp hạng 0–100, không phải gate vào lệnh.
Trạng thái chuẩn gồm `READY_NOW`, `WAITING_CONFIRMATION`, `WATCH_ZONE`,
`OUT_OF_STRATEGY`, `BLOCKED` và `DATA_UNAVAILABLE`.
Nhãn người dùng của `OUT_OF_STRATEGY` là **Chưa đạt quy tắc**, phải giải thích
rõ cặp vẫn được hỗ trợ nhưng còn thiếu một hay nhiều điều kiện của bộ quy tắc
hiện tại. Tiêu đề cột không được elide/cắt chữ; độ rộng tối thiểu phải tính từ
font tiêu đề và padding, cho phép cuộn ngang nếu tổng độ rộng vượt viewport.

### Hành vi đặt lệnh

UI chỉ phát yêu cầu auto order khi đang quét định kỳ và người dùng chủ động bật
nút: khi đó `ScannerRequest.auto_trade_enabled=true`. Nút đặt candidate thủ
công vẫn gọi `ScannerController.execute_order_candidate()`. Ở `PRODUCTION` đã
phê duyệt, nút manual truyền override giới hạn cho `RELEASE_GATE_NOT_READY`;
auto order không có override này. Không được gọi MT5 trực tiếp.

### Thiết kế Scanner V1 lưu để tham chiếu lịch sử

Phần dưới đây mô tả giao diện trước Scanner V2. Không dùng tên cột, thang điểm
hoặc logic automation trong phần lịch sử làm runtime contract.

## Màn hình 4 (lịch sử): Scanner trước V2

<details>
<summary>Mở thiết kế Scanner V1 lịch sử</summary>

### Mục đích

Scanner (Màn hình quét thị trường) dùng để quét nhanh toàn bộ 28 cặp Forex + XAU/USD + XAG/USD + BTC/USD, xếp hạng setup (thiết lập giao dịch) đáng chú ý và giúp người dùng chọn mã cần xem chi tiết.

### Bố cục màn hình

```text
Scanner Mode (Chế độ quét thị trường)

--------------------------------------------------
SCAN SETTINGS (THIẾT LẬP QUÉT)
--------------------------------------------------

Symbol List (danh sách mã):
[x] All Supported Symbols (28 cặp Forex + XAU/USD + XAG/USD + BTC/USD)

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
[x] XAG/USD (bạc giao ngay so với USD)
[x] BTC/USD (Bitcoin so với USD)

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

| Rank (xếp hạng) | Symbol (mã) | Nhóm | Bias (thiên hướng) | Chế độ TT | Entry | M15 | Điểm | R:R thực | Vĩ mô |
|---:|---|---|---|---|---|---:|---:|---:|---:|
| 1 | XAU/USD | Sẵn sàng ngay | Buy (mua) | trend_up | Trong vùng | Chặt | 115 | 2.1 | Thuận |
| 2 | EUR/USD | Chờ xác nhận | Neutral (trung lập) | range | Gần vùng | Lỏng | 88 | 1.6 | Trung tính |
| 3 | USD/JPY | Bị chặn | Sell (bán) | trend_down | Còn xa | Không đạt | 42 | — | Ngược |

--------------------------------------------------
NHÓM (SCANNER GROUP)
--------------------------------------------------

Sẵn sàng ngay (ready_now): Entry đã xác nhận, gate cho phép, có thể xem xét vào lệnh.
Chờ xác nhận (waiting_confirmation): Setup thú vị, đang chờ thêm tín hiệu xác nhận.
Theo dõi (watch_zone): Đáng theo dõi, nhưng chưa thể hành động.
Bị chặn (blocked): Bị gate hoặc dữ liệu chặn, không nên giao dịch.
```

### Cột bắt buộc trong bảng Scanner (bảng quét thị trường)

| Cột | Ý nghĩa |
|---|---|
| Rank (xếp hạng) | Thứ tự ưu tiên theo scanner_group > opportunity_score |
| Symbol (mã giao dịch) | Mã được quét |
| Nhóm | ready_now / waiting_confirmation / watch_zone / blocked |
| Bias (thiên hướng) | Buy (mua), Sell (bán), Neutral (trung lập) |
| Chế độ TT | trend_up / trend_down / range / volatile — bối cảnh thị trường |
| Entry | Vị trí giá so với vùng: Trong vùng / Gần vùng / Còn xa (+ tooltip entry_status) |
| M15 | Chất lượng xác nhận M15: Chặt / Lỏng / Không đạt |
| Điểm | opportunity_score (0-120) — điểm xếp hạng cơ hội (+ tooltip final_score breakdown) |
| R:R thực | `expected_effective_rr` best-case ở cột chính; base/current hiển thị trong breakdown/tooltip phù hợp |
| Vĩ mô | Thuận / Trung tính / Ngược — mức độ đồng thuận của vĩ mô với hướng trade |

### Logic gọi AI trong Scanner (màn hình quét thị trường)

Scanner (màn hình quét thị trường) không gọi AI cho tất cả mã ngay từ đầu. AI chỉ được gọi khi:

```text
Best Score (điểm tốt nhất) >= 75
Trade Permission (quyền cho phép giao dịch) != Blocked (bị chặn)
```

Nếu có nhiều mã đạt điều kiện, MVP (phiên bản khả dụng tối thiểu) chỉ gọi AI cho tối đa 3 mã có điểm cao nhất.

### Lưu ý về Giao diện & Styling
- **Tiêu đề phụ (Subtitle):** Phần tiêu đề phụ dưới "Quét thị trường" được để trống để giữ giao diện tối giản và hiện đại.
- **Chiều cao dòng (Row Height):** Để hiển thị được tối đa số lượng cơ hội quét đồng thời trên một màn hình, vertical padding của các ô bảng (`::item`) và tiêu đề cột (`QHeaderView::section`) thuộc bảng kết quả quét (`#EconTable`) được cấu hình tối ưu ở mức `4px` (giữ nguyên horizontal padding là `8px`).

---

</details>

## Màn hình 5: Scanner Detail (Màn hình chi tiết mã từ quét thị trường)

### Mục đích

Scanner Detail (Màn hình chi tiết mã từ quét thị trường) mở ra khi người dùng bấm View Detail (xem chi tiết) ở bảng Scanner (bảng quét thị trường). Màn hình này hiển thị phân tích đầy đủ của mã đã chọn.

R:R ưu tiên field top-level của scanner row và fallback sang scenario khớp `best_side`. Nếu đã có entry zone nhưng chưa có TP1 hợp lệ, màn hình hiển thị `N/A` cùng ghi chú chưa có TP1 hợp lệ nên chưa tính R:R; không hiển thị RR giả.

### Hiển thị zone theo contract Phase 16

- `Execution zone` là final `entry_zone` của scenario khớp chính xác
  `best_side`. Đây là vùng duy nhất được dùng cho trạng thái in/out zone và
  execution guard.
- `Source zone` phải được gắn nhãn tham khảo; không dùng màu hoặc wording làm
  người dùng hiểu nhầm đây là vùng có thể vào lệnh.
- Trên chart chi tiết, source zone bị ẩn mặc định. Trader có thể bật
  `Vùng cấu trúc` để xem hai biên nét thưa với một nhãn `Source zone`; control
  phải ghi rõ đây là vùng tham khảo, không dùng để vào lệnh. Khi ẩn, source
  zone không được ảnh hưởng đến price scale của chart.
- Card/tooltip hiển thị đồng thời source zone, execution zone, width theo pip
  và ATR, cùng lý do `unchanged`, `trimmed`, `not_applicable_no_tp1` hoặc
  reject/empty.
- Order dialog dùng final execution zone trong cột Entry và tooltip. Source
  zone chỉ xuất hiện trong breakdown.
- Chart vẽ source zone bằng style tham khảo và final execution zone bằng style
  Entry. Payload source có `execution_eligible=false`; final entry có
  `execution_eligible=true`.
- Nếu không có final execution zone, UI hiển thị `--`/lý do reject và không
  được fallback sang source zone hoặc scenario đối diện.

### Bố cục màn hình

**Tab Tổng quan** — chia 2 cột (20%/80%):
- Cột trái (20%, font 11px, padding 6/4, spacing 1px):
  - Nút "📋 Xem đầy đủ" — mở dialog bối cảnh kỹ thuật, vĩ mô và checklist của
    kết quả quét.
  - Card "🎯 Số liệu giao dịch" — hướng phân tích canonical, vùng vào lệnh,
    SL, TP, R:R thực sau spread/chi phí và chế độ thị trường.
  - Card "📊 Điểm phân tích" — trạng thái candidate, setup score/ngưỡng,
    điểm ưu tiên, độ tin cậy bằng chứng và mức sẵn sàng.
  - Card "🔍 Điều kiện vào lệnh" — 6 điều kiện lấy từ đúng hướng đã chọn:
    chiến lược, điểm thiết lập, vùng vào lệnh, R:R, xác nhận điểm vào lệnh và
    quyền đặt lệnh tại lúc quét. Trạng thái có ba mức ✅ đạt / ❌ không đạt /
    ➖ chưa có dữ liệu.
- Cột phải (80%): Hero verdict canonical + Chart (OHLCV, indicator, SMC
  zones) full height. Hero không dùng `best_score` để gọi “MUA/BÁN mạnh”; nó
  hiển thị `candidate_status`, hướng phân tích và setup/ngưỡng.

**Tab Chẩn đoán** — nhánh chiến lược → phân rã điểm BUY/SELL → Gate → checklist
pipeline → các bước pipeline → setup score của hướng đã chọn. Quyết định
canonical của Scanner được hiển thị trước; Decision Engine cũ chỉ là thông tin
tham khảo. Gate thiếu dữ liệu phải hiện "chưa kiểm tra", không được mặc định
"qua". Khi Strategy Router chọn hướng khác hướng legacy có điểm cao nhất,
Gate và scenario phải lấy đúng `selected_side`; không được mượn kết quả Gate
của hướng còn lại.

Khi cutover, phần phân rã BUY/SELL chỉ có bốn dòng
Trend/Momentum/Location/SMC. `MarketSafetyGate`, `MacroAssessment` và kết quả
`MacroGate` nằm sau bảng điểm dưới dạng đánh giá độc lập; PASS/aligned không cộng
điểm, CAUTION/conflict chỉ cap hoặc block theo policy và không sửa số đã hiển thị.

**Tab Kiểm định AI** — nút chạy kiểm định + kết quả AI audit

### Nút chức năng

```text
[Back to Scanner (Quay lại màn hình quét thị trường)]
[Save to Journal (Lưu vào nhật ký)]
[Export JSON (Xuất dữ liệu JSON)]
[Run Full Analysis Again (Chạy lại phân tích đầy đủ)]
```

### Lưu ý về Giao diện & Styling
- **Bảng HTML nội bộ (Inline HTML Tables):** Toàn bộ các bảng hiển thị chi tiết (bảng chấm điểm kịch bản, bảng kiểm tra gate, bảng điều kiện vào lệnh, bảng chẩn đoán 7 bước, bảng điểm cuối cùng) đều có padding dọc cho thẻ `<td>` và `<th>` được đặt cố định ở mức `4px` để tối ưu hóa không gian hiển thị theo chiều dọc, tránh việc người dùng phải cuộn chuột quá nhiều.
- **Nguồn dữ liệu chuẩn:** `scanner_candidate_decision` quyết định trạng thái,
  hướng, setup score, ngưỡng, R:R thực và quyền tại thời điểm quét. Dữ liệu
  legacy chỉ dùng để đọc snapshot cũ. Vị trí giá được đối chiếu lại với vùng
  entry của đúng hướng đã chọn; R:R danh nghĩa/dải R:R trong phần giải thích
  cũng lấy từ scenario của hướng này.
- **Vĩ mô runtime:** giá trị hiển thị `/30` là `macro_raw` của đúng hướng đã
  chọn, không phải `macro_alignment` đã co giãn theo trọng số chế độ thị trường.
  Ở target, raw này chỉ là diagnostic trong `MacroAssessment`, đi kèm
  confidence/status và tuyệt đối không mang nhãn contribution hoặc được cộng vào
  Technical/Final/Setup score.
- **Không giả dữ liệu:** thiếu điểm vĩ mô/Gate/evidence phải hiển thị `--`,
  “chưa rõ” hoặc “chưa kiểm tra”; không tự điền điểm trung lập hay coi Gate là
  đạt.

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
[AI (Trí tuệ nhân tạo)]
[Dữ liệu (MT5)]
[Trading (Giao dịch)]
[Display (Hiển thị)]
[Advanced (Nâng cao)]
```

---

## 8.1. Tab AI (Trí tuệ nhân tạo)

### Mục tiêu

Màn hình cấu hình AI dùng kiến trúc Provider-Centric. Người dùng làm 4 việc:

1. Chọn nhà cung cấp từ danh sách bên trái.
2. Xem capabilities của provider (Streaming, Vision, Model Discovery, ...).
3. Nhập API Key và chọn Model (combobox editable, tự động populate từ catalog).
4. Bấm "Kiểm tra" — nếu thành công, tự động fetch model mới nhất từ API.

API Key được lưu an toàn qua Windows Credential Manager (không plaintext trong settings.json).

### Bố cục (hiện tại — Provider-Centric)

```text
Cài đặt → AI

┌──────────────────────┬────────────────────────────────────────┐
│ Nhà cung cấp         │  Gemini                                │
│                      │  Chat · Model Discovery · Vision       │
│  DeepSeek            │                                        │
│  OpenAI              │  [x] Đặt làm nhà cung cấp mặc định     │
│  Anthropic           │                                        │
│  Gemini              │  API Key                               │
│                      │  [••••••••••••••••••••••••••••••••]   │
│                      │                                        │
│                      │  Model                                 │
│                      │  [gemini-3.5-flash          ▼] [↻]    │
│                      │                                        │
│                      │  [🧪 Kiểm tra]  [💾 Lưu]              │
│                      │                                        │
│                      │  Đã cập nhật 3 model.                  │
└──────────────────────┴────────────────────────────────────────┘
```

### Hành vi UI

- Panel trái: danh sách provider từ `ProviderCatalog` (QListWidget).
- Panel phải: hiển thị capabilities tự động từ `ProviderCapability` IntFlag (không hard-code).
- Nút ↻ (Đồng bộ model) chỉ hiển thị với provider có `MODEL_DISCOVERY` capability. Gọi API của provider đó để lấy model mới nhất. Cache 30 phút trong memory + disk.
- API Key lưu qua `CredentialService` (Windows Credential Manager), không lưu plaintext trong `settings.json`.
- Model combobox editable — user có thể chọn từ danh sách hoặc gõ model tùy chỉnh.
- Khi test API Key thành công → tự động fetch model mới nhất.
- Nếu discovery lỗi → hiển thị lỗi rõ ràng, không crash.

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

## 8.2. Tab Dữ liệu (MT5)

### Bố cục

```text
--------------------------------------------------
TRẠNG THÁI KẾT NỐI
--------------------------------------------------

MT5 đã kết nối | Broker | Server | Login

[💾 Lưu cấu hình] [🔄 Khởi động lại] [🔄 Thử kết nối lại]

--------------------------------------------------
BẢNG CẤU HÌNH MÃ QUÉT
--------------------------------------------------

| STT | Mã hiển thị | Mã MT5 | Trạng thái | Kiểm tra | Dùng BT đã duyệt | Min Score BT | Regime BT | Hướng BT | RR tối thiểu BT | Ready | Watch | Wait |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | EUR/USD | EURUSDm | OK | -- | [x] Đã duyệt | 65 | range | best | 1.3 | 65 | 60 | 55 |

Bảng hỗ trợ đầy đủ 28 cặp Forex + XAU/USD + XAG/USD + BTC/USD.

Nút chức năng:
[🔍 Tự phát hiện mã broker] [📋 Dán cấu hình Backtest] [💾 Lưu cấu hình mã quét]
```

Quy tắc phần Symbols:

- `Ready/Watch/Wait` là ngưỡng live của Decision Engine và được phép chỉnh.
- `Min Score BT/Regime BT/Hướng BT/RR tối thiểu BT` là bằng chứng do Backtest
  tạo, chỉ đọc tại Settings; muốn đổi phải chạy lại Backtest.
- Chỉ config `VALIDATED`, đúng contract SMC và còn hạn mới cho phép tick
  **Dùng BT đã duyệt**.
- `DRAFT/INVALID/EXPIRED` vẫn được hiển thị và lưu để kiểm tra lại sau nhưng
  luôn inactive. Scanner của mã đó dùng SMC + `DEFAULT_RULES`.
- Dán JSON phải chạy canonical validator trước khi cho phép kích hoạt; thao tác
  dán hoặc tick không được tự nâng một bản nháp thành `VALIDATED`.

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
| XAG/USD (bạc giao ngay so với USD) | Yes (có) | 5000 |
| BTC/USD (Bitcoin so với USD) | Yes (có) | 1 |
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

[ ] Chặn giao dịch quanh tin đỏ
[ ] Đánh giá sự kiện lớn trước 4-48h cho MacroGate (Bước 5; target)
[ ] AI veto/cap vĩ mô cho tín hiệu mạnh (Bước 6; target)
[ ] VIX theo độ nhạy từng cặp tiền (Bước 7 — chỉ bật sau backtest)

Auto-scan mặc định: [ 5 phút ▼ ]
Telegram bot token: [ ... ]
Telegram chat ID: [ ... ]

[Backup Settings (Sao lưu cài đặt)]
[Restore Settings (Khôi phục cài đặt)]
[Reset to Default (Đặt lại mặc định)]
```

Checkbox VIX pair-aware mặc định unchecked, phải load/save qua
`AdvancedSettings.vix_pair_aware_enabled` và không được tự bật sau calibration.
Flag ON không bảo đảm modulation được áp dụng: candidate
seed/stale/schema cũ/malformed bị bỏ qua để thử fallback; runtime chỉ flat nếu
không còn candidate eligible hoặc pair không actionable. UI hiện hành mới có
toggle; chưa có nút revalidate hay trạng thái map source/age/expiry. Đây là gap
vận hành cần hiển thị trước khi coi tính năng production-complete.

Ảnh `docs/ui/baseline/current/*/screen-settings*.png` chưa được capture lại
trong thay đổi Bước 7 này, nên chưa phải bằng chứng visual cho checkbox mới.
Phải regenerate baseline trước khi dùng bộ ảnh đó làm release evidence UI.

---

## 8.6. Tab Rollout Scanner (đã gỡ bỏ)

Tab Rollout của Scanner V2 — stage (`DISABLED`, `SHADOW`, `DEMO_LIMITED`,
`DEMO_FULL`, `CANARY`, `PRODUCTION`), kill switch, shadow comparison V1/V2,
allowlist, canary risk, require-demo/production approval và readiness
metrics — đã bị gỡ bỏ hoàn toàn khỏi UI và codebase ngày 15/08/2026 theo
quyết định của owner (phần mềm cá nhân, chạy thật trực tiếp). Thay thế cho
kiểm soát thực thi hiện là: RuntimeOrderPolicy (Scanner) và tab **Quản lý
lệnh** trong Settings (Order Management V2: bật/tắt + phạm vi AMA/ALL).

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
    ├── AI (Trí tuệ nhân tạo)
    ├── Dữ liệu (MT5)
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

- Scanner table co cot **Vung** hien thi trang thai gia tai thoi diem quet so voi vung entry: `Trong vung` (gia nam trong hoac dung bien vung), `Ngoai vung` (gia nam ngoai hai bien), hoac `--` (chua co vung that hoac thieu du lieu). Cot khong tu cap nhat real-time; execution revalidation van dung bid/ask live truoc khi gui lenh.
- Entry checklist muc `Xu huong` phai xet theo side cua setup; range market co the dat neu setup nam tai POI/bien gia tot, khong mac dinh fail.
- Màn hình kết quả target hiển thị `confidence_reason` với breakdown điểm chỉ
  gồm trend/momentum/location/SMC; safety gate, macro status/confidence và event
  caution gần nhất nằm ở assessment riêng, không có điểm contribution.

## Legacy Scanner Automation Behavior (đã bị thay thế bởi Scanner V2)

> Nội dung trong mục này chỉ lưu lại hành vi trước migration. Runtime contract
> hiện hành nằm tại “Màn hình 4: Scanner V2” và
> [Scanner flow](../scanner/scanner-flow.md). Các hàm
> `_best_scenario`, `_is_auto_trade_candidate` kiểu cũ và mô hình Nhánh 1/2
> không còn là nguồn quyết định đặt lệnh.

<details>
<summary>Mở hành vi automation V1 lịch sử</summary>

- Scanner has two modes: one-shot scan and auto-scan.
- Auto-entry is attached only to auto-scan mode and requires the user to check `Tự động vào lệnh MT5`. The UI must not place MT5 orders from one-shot scan.
- The `Tự động vào lệnh MT5` toggle button must be visually highlighted when active, because enabling it can place real MT5 orders. Do not show a separate checkbox indicator inside this button; the whole button is the state indicator.
- When auto-scan is active and a row becomes `ready`, the user-facing result should still show the normal scanner table and Telegram alert. Auto-entry execution status is returned separately as `auto_trade_results`.
- Trước khi đặt auto order, controller lấy live ask/bid, kiểm tra giá còn trong entry zone và tính current effective RR. Lệnh bị skip nếu giá ngoài zone hoặc current RR thấp hơn `min_rr`; manual order bị block với cảnh báo tương ứng.
- Order dialog giữ best-case RR ở text chính; tooltip hiển thị best/base/current. Entry tooltip hiển thị zone, live price và trạng thái in/out zone.
- Auto-entry status should be displayed or logged with these counts when surfaced in UI: attempted, opened, skipped, and errors.
- A skipped auto-entry is not a UI failure when the reason is "already has position/order"; it is the intended one-order-per-symbol guard.
- Telegram summary should remain short: scanned count, ready count, ready symbol list with Entry/SL/TP. Watch-only symbols are intentionally omitted from Telegram summary.
- Telegram detail dùng base effective RR làm giá trị chính khi có, fallback best effective, và giữ best nominal RR làm tham chiếu; current RR không thay thế dòng RR chính.

### Fallback Scenario Filtering

- Khi pipeline không tìm được SMC/technical zone thật, `_assemble_result()` tạo fallback scenario với `entry_zone_source = "fallback"`, `entry_zone_score = 50`, `RR = 1:2.0`.
- Fallback scenario **vẫn hiển thị trong bảng scanner** (để trader tham khảo), nhưng bị chặn khỏi:
  - **"Hiển thị lệnh" dialog** (`_build_order_rows` skip `entry_zone_source == "fallback"`)
  - **Auto-trade** (`_best_scenario` skip fallback → `_is_auto_trade_candidate` trả về False)
  - **Telegram alerts** (`_get_alert_order_candidates` skip fallback)
- Logic này áp dụng cho cả Nhánh 1 (backtest=true) và Nhánh 2 (backtest=false).

</details>

---

## Orders Screen (Quản lý lệnh) — BE & Trailing Stop

> Thiết kế mới 2026-07-08. Chi tiết triển khai nằm tại `ui/screens/orders_screen.py`.

### Tổng quan

Màn hình Quản lý lệnh cho phép theo dõi tất cả vị thế đang mở và lệnh chờ trên MT5, kèm tính năng tự động BE (Breakeven) và Trailing Stop theo ATR.

### Bố cục

- **Status bar:** 5 card mini — BALANCE, LỆNH MỞ, LỆNH CHỜ, P/L, TRAILING
- **Tab bar:** "Vị thế đang mở" | "Lệnh chờ"
- **Bảng lệnh:** 10 cột — Mã, Hướng, KL, Entry, Hiện tại, SL, TP, P/L, Trailing (trạng thái BE/trail), Action
- **Action bar:** Làm mới, Trailing Stop (manual), Xóa trailing, Đóng lệnh đã chọn, Đóng tất cả

### BE & Trailing tự động

Khi scanner mở lệnh qua auto-trade, hệ thống tự động đăng ký BE + Trailing:

1. **Chờ BE:** Hiển thị "⏳ Chờ BE (còn X pips)" — màu xám
2. **Đã BE:** Profit ≥ 1R → SL dời về entry + 2 pips → hiển thị "✅ BE" — màu xanh lá
3. **Trail rộng:** Sau BE, SL dời theo extreme - 2.5×ATR(H1) → hiển thị "🟢 Wide" — xanh dương
4. **Trail chặt:** Profit ≥ 2R → multiplier giảm còn 1.5×ATR → hiển thị "🔒 Tight" — cam

### Nguyên tắc

- SL **không bao giờ lùi** xa hơn vị trí cũ
- BE chỉ dời **1 lần** duy nhất
- Trail chỉ chạy **sau khi BE**
- TP **giữ nguyên**, không can thiệp
- Chỉ quản lý lệnh **do hệ thống mở** (comment prefix "AMA")
- Timer chạy **ngay cả khi tab không active**
