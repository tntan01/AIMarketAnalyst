# Hướng dẫn sử dụng AIMarketAnalyst

## Mục lục

1. [Introduction (Giới thiệu)](#1-introduction-giới-thiệu)
2. [Setup & Launch (Cài đặt và khởi chạy)](#2-setup--launch-cài-đặt-và-khởi-chạy)
3. [Backtest (Kiểm thử chiến lược)](#3-backtest-kiểm-thử-chiến-lược)
   - [3.1 Backtest là gì trong ứng dụng này?](#31-backtest-là-gì-trong-ứng-dụng-này)
   - [3.2 Chuẩn bị dữ liệu đầu vào](#32-chuẩn-bị-dữ-liệu-đầu-vào)
   - [3.3 Các bước chạy Backtest](#33-các-bước-chạy-backtest)
   - [3.4 Đọc kết quả Backtest](#34-đọc-kết-quả-backtest)
   - [3.5 Dùng kết quả Backtest để cấu hình Scanner](#35-dùng-kết-quả-backtest-để-cấu-hình-scanner)
   - [3.6 Lỗi thường gặp khi Backtest](#36-lỗi-thường-gặp-khi-backtest)
4. [Scanner (Bộ quét)](#4-scanner-bộ-quét)
5. [Journal (Nhật ký)](#5-journal-nhật-ký)
6. [Auto-trade (Giao dịch tự động)](#6-auto-trade-giao-dịch-tự-động)
7. [Diagnostics (Chẩn đoán)](#7-diagnostics-chẩn-đoán)
8. [Settings (Cài đặt)](#8-settings-cài-đặt)
9. [Troubleshooting (Khắc phục sự cố)](#9-troubleshooting-khắc-phục-sự-cố)

## 1. Introduction (Giới thiệu)

(Đang cập nhật)

## 2. Setup & Launch (Cài đặt và khởi chạy)

(Đang cập nhật)

## 3. Backtest (Kiểm thử chiến lược)

### 3.1 Backtest là gì trong ứng dụng này?

Backtest (Kiểm thử chiến lược) phát lại hệ thống phân tích và lập kế hoạch giao dịch của AIMarketAnalyst trên dữ liệu nến lịch sử. Mỗi thời điểm đánh giá chỉ được nhìn thấy các nến đã đóng tại thời điểm đó, nhằm tránh dùng dữ liệu tương lai.

Ứng dụng lấy dữ liệu OHLCV (Giá mở cửa, cao nhất, thấp nhất, đóng cửa và khối lượng) trực tiếp từ MetaTrader 5 — MT5 (Nền tảng giao dịch MetaTrader 5). Hệ thống phân tích xu hướng và cấu trúc trên D1 (Khung ngày), H4 (Khung 4 giờ) và H1 (Khung 1 giờ); bước mô phỏng khớp lệnh ưu tiên M15 (Khung 15 phút). Nếu không có M15 trong một lần chạy nghiên cứu, engine (Bộ máy xử lý) có thể dùng H1 để mô phỏng thực thi; riêng Validation (Kiểm chứng) bắt buộc phải có khung thực thi.

Backtest mô phỏng điểm vào lệnh, Stop Loss — SL (Điểm dừng lỗ), Take Profit — TP (Điểm chốt lời), thời gian giữ lệnh, chi phí giao dịch, quy mô vị thế và các giới hạn rủi ro tài khoản. Hai mục đích chạy có ý nghĩa khác nhau:

- Research (Nghiên cứu): tạo kết quả `RESEARCH_ONLY` (Chỉ nghiên cứu), dùng để quan sát và thử nghiệm; không được kích hoạt làm cấu hình giao dịch cho Scanner (Bộ quét).
- Validation (Kiểm chứng): tự chạy In-Sample — IS (Trong mẫu), Out-of-Sample — OOS (Ngoài mẫu) và Walk-Forward (Kiểm tra cuốn chiếu). Kết quả chỉ có thể tham gia cấu hình Scanner khi toàn bộ bằng chứng và vòng đời cấu hình đạt trạng thái `VALIDATED` (Đã kiểm chứng).

### 3.2 Chuẩn bị dữ liệu đầu vào

#### Nguồn và phạm vi dữ liệu

Trước khi chạy, hãy mở MT5, đăng nhập tài khoản và bảo đảm mã giao dịch có trong Market Watch (Danh sách mã theo dõi). Khi bắt đầu Backtest, ứng dụng tự:

- lấy D1, H4 và H1 từ 520 ngày trước ngày bắt đầu đến ngày kết thúc;
- lấy M15 từ 90 ngày trước ngày bắt đầu đến ngày kết thúc;
- chuẩn hóa mốc thời gian về UTC (Giờ phối hợp quốc tế), sắp xếp nến, loại bản ghi trùng và kiểm tra khoảng trống dữ liệu;
- lấy spread (Chênh lệch giá mua/bán), bước lot (Bước khối lượng), lot tối thiểu, lot tối đa và thông tin hợp đồng của mã từ MT5 khi có.

Khoảng ngày trên giao diện được xử lý theo quy ước `[start, end)` (Tính ngày bắt đầu, không tính mốc kết thúc). Ứng dụng tự cộng thêm một ngày vào ngày “Đến”, vì vậy toàn bộ ngày người dùng chọn vẫn được đưa vào kiểm thử.

#### Mức dữ liệu tối thiểu

Code (Mã nguồn) không định nghĩa một con số duy nhất bảo đảm kết quả “có ý nghĩa”. Có ba lớp yêu cầu riêng:

1. Để bắt đầu phân tích tại một thời điểm, snapshot (Ảnh chụp dữ liệu tại thời điểm đó) phải có ít nhất 60 nến D1, 60 nến H4 và 30 nến H1.
2. Để tạo cấu hình kiểm chứng, mẫu IS phải có ít nhất 10 ứng viên đủ điều kiện và mẫu OOS phải có ít nhất 8 lệnh. Kiểm chứng còn yêu cầu OOS có Expectancy (Kỳ vọng) tối thiểu `0.10R`, Profit Factor (Hệ số lợi nhuận) tối thiểu `1.20`, Maximum Drawdown (Mức sụt giảm tối đa) không quá `8R`, khoảng tin cậy của kỳ vọng phải dương và đủ lực thống kê theo cỡ mẫu do engine tính.
3. Walk-Forward (Kiểm tra cuốn chiếu) mặc định dùng 6 tháng IS, 3 tháng OOS và bước dịch 3 tháng; cấu hình cần ít nhất 2 cửa sổ hợp lệ. Vì vậy khoảng ngày phải dài tối thiểu 12 tháng theo lịch mới có thể tạo 2 cửa sổ. Mặc định 6 tháng trên giao diện không đủ để vượt điều kiện này.

Đây là ngưỡng kỹ thuật và ngưỡng kiểm chứng trong code, không phải cam kết rằng cứ đạt đủ số lượng là chiến lược sẽ có lợi nhuận.

#### Tham số trong Settings (Cài đặt) có liên quan

Backtest đọc các giá trị dưới đây từ tab Settings > Giao dịch (Cài đặt > Giao dịch). Với giới hạn lot, dữ liệu riêng của mã từ MT5 được ưu tiên hơn giá trị dự phòng trong Settings (Cài đặt).

| Tên tham số | Ý nghĩa | Giá trị mặc định | Ghi chú |
|---|---|---:|---|
| Đồng tiền tài khoản | Đồng tiền dùng để tính P/L (Lãi/lỗ) và quy đổi giá trị giao dịch | `USD` (Đô la Mỹ) | Được truyền vào Backtest |
| Bước lot (Bước khối lượng) | Độ tăng/giảm nhỏ nhất của khối lượng lệnh | `0.01 lot` | Dùng giá trị MT5 nếu MT5 cung cấp |
| Lot tối thiểu (Khối lượng tối thiểu) | Khối lượng nhỏ nhất được phép | `0.01 lot` | Dùng giá trị MT5 nếu MT5 cung cấp |
| Lot tối đa (Khối lượng tối đa) | Khối lượng lớn nhất được phép | `100 lot` | Dùng giá trị MT5 nếu MT5 cung cấp |
| Quy mô hợp đồng | Số đơn vị tài sản trong một lot | `100000` | Là giá trị dự phòng; một số nhóm tài sản có quy mô riêng trong code |
| Trượt giá Backtest (Kiểm thử chiến lược) | Mức lệch giá giả định khi vào và thoát lệnh | `0.0` | Cùng một giá trị được áp cho chiều vào và chiều thoát |
| Phí khứ hồi Backtest (Kiểm thử chiến lược) | Tổng commission (Phí môi giới) cho một vòng mở–đóng trên mỗi lot | `0.0 / lot` | Được trừ trong mô hình chi phí |
| Swap BUY Backtest (Phí qua đêm lệnh mua) | Phí qua đêm mỗi lot mỗi ngày cho lệnh mua | `0.0 / lot/ngày` | Được tính theo thời gian giữ lệnh |
| Swap SELL Backtest (Phí qua đêm lệnh bán) | Phí qua đêm mỗi lot mỗi ngày cho lệnh bán | `0.0 / lot/ngày` | Được tính theo thời gian giữ lệnh |

Backtest cũng bật Account Guard (Bộ bảo vệ tài khoản) và đọc các giá trị nội bộ sau từ Settings (Cài đặt). Bản giao diện hiện tại chưa có ô chỉnh trực tiếp các giá trị này trong tab Giao dịch.

| Tên tham số | Ý nghĩa | Giá trị mặc định | Ghi chú |
|---|---|---:|---|
| `max_daily_loss_pct` (Mức lỗ ngày tối đa) | Giới hạn phần trăm lỗ trong ngày | `2.0%` | Có thể chặn ứng viên giao dịch |
| `max_weekly_loss_pct` (Mức lỗ tuần tối đa) | Giới hạn phần trăm lỗ trong tuần | `5.0%` | Có thể chặn ứng viên giao dịch |
| `max_consecutive_losses` (Số lệnh thua liên tiếp tối đa) | Giới hạn chuỗi thua | `3` | Có thể chặn ứng viên giao dịch |
| `max_open_risk_pct` (Rủi ro đang mở tối đa) | Giới hạn tổng rủi ro của các vị thế đang mở | `3.0%` | Được truyền vào Backtest |
| `max_symbol_risk_pct` (Rủi ro tối đa theo mã) | Giới hạn rủi ro trên một mã | `2.0%` | Được truyền vào Backtest |
| `max_currency_exposure_pct` (Mức phơi nhiễm tiền tệ tối đa) | Giới hạn mức phơi nhiễm theo đồng tiền | `2.0%` | Được truyền vào Backtest |
| `max_correlated_risk_pct` (Rủi ro tương quan tối đa) | Giới hạn rủi ro giữa các vị thế tương quan | `2.0%` | Được truyền vào Backtest |
| `max_concurrent_orders` (Số lệnh đồng thời tối đa) | Số vị thế/lệnh được phép đồng thời | `5` | Được truyền vào engine dưới tên giới hạn vị thế đồng thời |

Hai giá trị sau nằm ngay trên màn hình Backtest và ghi đè ngữ cảnh của lần chạy; chúng không lấy từ các ô Số dư MT5 hay Rủi ro mỗi lệnh trong Settings (Cài đặt):

| Tên tham số | Ý nghĩa | Giá trị mặc định | Ghi chú |
|---|---|---:|---|
| Vốn | Số dư ban đầu của lần mô phỏng | `10000` | Nhập trực tiếp trên màn hình Backtest |
| Rủi ro | Phần trăm vốn mục tiêu cho mỗi lệnh | `1.0%` | Nhập trực tiếp trên màn hình Backtest |

Spread (Chênh lệch giá mua/bán) không có ô nhập riêng trong Settings (Cài đặt); ứng dụng lấy từ thông tin mã của MT5 tại lúc tạo yêu cầu Backtest.

### 3.3 Các bước chạy Backtest

1. Mở MT5, đăng nhập và đưa mã cần kiểm thử vào Market Watch (Danh sách mã theo dõi).
2. Trong AIMarketAnalyst, mở Settings > Giao dịch (Cài đặt > Giao dịch), kiểm tra đồng tiền tài khoản, quy mô hợp đồng, trượt giá, commission (Phí môi giới) và swap (Phí qua đêm), rồi lưu nếu có thay đổi.
3. Chọn Backtest (Kiểm thử chiến lược) trên thanh điều hướng.
4. Bấm **Chọn** ở trường Mã. Luồng thông thường dùng một mã. Chế độ Portfolio (Danh mục) chỉ có trong Research (Nghiên cứu), cần ít nhất 2 mã và không thể phát hành thành cấu hình riêng cho một mã.
5. Chọn ngày Từ/Đến. Giao diện mặc định lấy 6 tháng gần nhất. Nếu mục tiêu là Validation (Kiểm chứng), chọn ít nhất 12 tháng để có khả năng tạo đủ 2 cửa sổ Walk-Forward (Kiểm tra cuốn chiếu), đồng thời vẫn phải đạt các ngưỡng số mẫu ở mục 3.2.
6. Nhập Vốn và Rủi ro.
7. Chọn Mục đích:
   - **Nghiên cứu** để xem hiệu năng và thử giả thuyết;
   - **Kiểm chứng** để tự chạy IS/OOS (Trong mẫu/Ngoài mẫu) và Walk-Forward (Kiểm tra cuốn chiếu).
8. Không cần chọn khung thời gian: giao diện không cung cấp bộ chọn này. Engine cố định bước đánh giá ở H1 và ưu tiên thực thi ở M15; D1 và H4 cung cấp bối cảnh phân tích.
9. Bấm **Chạy**. Theo dõi thanh tiến trình; có thể bấm **Hủy** để yêu cầu dừng an toàn.

Code không đặt thời lượng cố định và giao diện không tính ETA (Thời gian hoàn thành dự kiến). Thời gian chạy phụ thuộc khoảng ngày, số mã, số nến, mục đích Nghiên cứu/Kiểm chứng và các tùy chọn nâng cao. Validation (Kiểm chứng), Portfolio (Danh mục), Walk-Forward (Kiểm tra cuốn chiếu), Monte Carlo (Mô phỏng ngẫu nhiên) hoặc quét nhiều tham số sẽ chạy nhiều lượt phát lại hơn một Backtest nghiên cứu đơn mã.

Trong tab Nghiên cứu nâng cao:

- `MT5 parity` (Mô phỏng tương đương MT5) dùng mô hình chi phí/thực thi đầy đủ; Validation (Kiểm chứng) bắt buộc chế độ này.
- `Research nhanh` (Nghiên cứu nhanh) giảm yêu cầu tương đương thực thi và luôn chỉ dùng để nghiên cứu.
- Monte Carlo (Mô phỏng ngẫu nhiên) tự chạy khi có ít nhất 30 lệnh nếu người dùng không yêu cầu rõ; có thể chọn chạy thủ công.
- Quét độ nhạy có bộ 4 tham số ưu tiên, 6 tham số ưu tiên hoặc toàn bộ 10 tham số, chạy trên khoảng ngày đã chọn hoặc các giai đoạn mẫu có sẵn.

### 3.4 Đọc kết quả Backtest

Sau khi hoàn tất, màn hình có bốn tab:

- **Kết quả**: báo cáo tổng hợp, phân rã theo mã, hướng, tháng, vùng điểm, chế độ thị trường và các đặc trưng thiết lập.
- **Đường cong vốn**: vẽ Cumulative R (R tích lũy) và Drawdown (Mức sụt giảm) theo thời gian.
- **Lệnh**: liệt kê thời gian vào, hướng, kết quả, số R, điểm cuối, regime (Chế độ thị trường) và RR kỳ vọng.
- **Nghiên cứu nâng cao**: kết quả IS/OOS (Trong mẫu/Ngoài mẫu), Walk-Forward (Kiểm tra cuốn chiếu), Monte Carlo (Mô phỏng ngẫu nhiên) và quét độ nhạy nếu đã chạy.

Các chỉ số chính:

| Chỉ số | Cách hiểu trong ứng dụng |
|---|---|
| Total Trades (Tổng số lệnh) | Số bản ghi giao dịch được engine tạo ra |
| Wins/Losses/Breakeven (Thắng/Thua/Hòa vốn) | Phân loại theo `result_r`: dương là thắng, âm là thua, bằng 0 là hòa vốn |
| Win Rate (Tỷ lệ thắng) | `Số lệnh thắng / Tổng số lệnh × 100%`; không phản ánh riêng độ lớn của lệnh thắng và lệnh thua |
| R (Đơn vị rủi ro) | Một đơn vị rủi ro ban đầu của lệnh; kết quả mua là `(giá thoát - giá vào) / khoảng cách SL`, lệnh bán dùng chiều ngược lại |
| RR — Risk/Reward (Tỷ lệ rủi ro/lợi nhuận) | Mức lợi nhuận kỳ vọng so với rủi ro; cột “RR kỳ vọng” dùng tỷ lệ hiệu dụng sau khi xét kế hoạch vào lệnh |
| Expectancy R (Kỳ vọng theo R) | Trung bình `result_r` của mọi lệnh; `0.10R` nghĩa là trung bình mỗi lệnh tạo `0.10` đơn vị rủi ro |
| Profit Factor (Hệ số lợi nhuận) | Tổng R dương chia cho trị tuyệt đối của tổng R âm; lớn hơn `1` nghĩa là tổng lãi lớn hơn tổng lỗ |
| Maximum Drawdown R (Mức sụt giảm tối đa theo R) | Khoảng giảm lớn nhất từ đỉnh R tích lũy xuống đáy kế tiếp |
| Gross R (R trước chi phí) | Tổng kết quả trước chi phí thực thi |
| Cost R (Chi phí theo R) | Tổng spread (Chênh lệch giá mua/bán), trượt giá, commission (Phí môi giới) và swap (Phí qua đêm), quy đổi sang R |
| Net R (R sau chi phí) | Kết quả sau chi phí; được dùng cho đường cong vốn và Account Guard (Bộ bảo vệ tài khoản) |
| Average/Median R (R trung bình/trung vị) | Trung bình và trung vị của kết quả theo R |
| Maximum Consecutive Wins/Losses (Chuỗi thắng/thua dài nhất) | Số lệnh thắng hoặc thua liên tiếp lớn nhất |
| Average Holding Bars (Số nến giữ lệnh trung bình) | Số nến thực thi trung bình từ lúc vào đến lúc thoát |

Không nên đọc Win Rate (Tỷ lệ thắng) riêng lẻ. Một hệ thống có tỷ lệ thắng thấp vẫn có thể dương nếu lệnh thắng lớn hơn lệnh thua; ngược lại, tỷ lệ thắng cao vẫn có thể âm khi thua lỗ lớn hoặc chi phí cao. Hãy đọc đồng thời Expectancy (Kỳ vọng), Profit Factor (Hệ số lợi nhuận), Net R (R sau chi phí), Drawdown (Mức sụt giảm) và cỡ mẫu.

Mỗi lần chạy thành công tự lưu một snapshot JSON (Ảnh chụp kết quả ở định dạng JSON) vào:

- Windows: `%APPDATA%\ai-market-analyst\backtests`;
- hệ điều hành không có biến `APPDATA`: `~/.ai-market-analyst/backtests`.

Tên file có dạng `backtest_<mã>_<thời-gian>.json`; chạy danh mục dùng tiền tố `backtest_BATCH_<số-mã>_symbols_...json`. Đường dẫn đầy đủ cũng hiện dưới phần kết quả. Để xem lại, mở màn hình Backtest và bấm **Mở kết quả**, sau đó chọn file JSON (Tệp dữ liệu JSON) đã lưu. Ứng dụng nạp lại báo cáo, danh sách lệnh, đường cong vốn và trạng thái vòng đời có trong snapshot.

### 3.5 Dùng kết quả Backtest để cấu hình Scanner

#### Ánh xạ cấu hình theo mã

Backtest và Scanner dùng chung hợp đồng chấm điểm SMC-v2 (Phiên bản 2 của chấm điểm Smart Money Concepts — Khái niệm dòng tiền thông minh). Với một mã, Backtest tối ưu cấu hình trên dữ liệu IS (Trong mẫu), đóng băng cấu hình rồi phát lại nguyên trạng trên OOS (Ngoài mẫu). Bốn giá trị được chuyển sang cấu hình Scanner như sau:

| Giá trị Backtest | Trường hiển thị trong Settings > Dữ liệu | Trường lưu nội bộ | Tác dụng trong Scanner |
|---|---|---|---|
| `regime` (Chế độ thị trường) | Regime BT (Chế độ thị trường từ Backtest) | `auto_trade_regime` | Chỉ chấp nhận bối cảnh thị trường phù hợp |
| `side` (Hướng giao dịch) | Hướng BT (Hướng từ Backtest) | `auto_trade_side` | Giới hạn hướng mua, bán hoặc hướng tốt nhất |
| `min_score` (Điểm tối thiểu) | Min Score BT (Điểm tối thiểu từ Backtest) | `min_score` | Yêu cầu điểm thiết lập đạt ngưỡng |
| `min_rr` (RR tối thiểu) | RR tối thiểu BT (Tỷ lệ rủi ro/lợi nhuận tối thiểu từ Backtest) | `min_expected_rr` | Yêu cầu RR hiệu dụng đạt ngưỡng |

Các trường này bị khóa trong Settings (Cài đặt) vì chúng là bằng chứng do Backtest tạo, không phải ô chỉnh tay. Ngưỡng Ready/Watch/Wait (Sẵn sàng/Theo dõi/Chờ xác nhận) là ba ngưỡng phân loại riêng trong Settings; Backtest không ghi đè chúng.

Quy trình áp dụng:

1. Chạy một mã với mục đích **Kiểm chứng**.
2. Đọc trạng thái IS/OOS (Trong mẫu/Ngoài mẫu), Walk-Forward (Kiểm tra cuốn chiếu) và các lý do chặn trong Kết quả.
3. Khi nút cấu hình xuất hiện, bấm **Lưu bản nháp** hoặc **Áp dụng cấu hình**, tùy trạng thái vòng đời mà ứng dụng cho phép.
4. Đối chiếu cấu hình hiện tại và cấu hình đề xuất trong hộp thoại, rồi xác nhận.
5. Mở Settings > Dữ liệu (Cài đặt > Dữ liệu), kiểm tra dòng của mã và bấm **Lưu cấu hình mã quét** nếu đang dùng luồng dán/duyệt tại màn hình này.

Chỉ cấu hình `VALIDATED` (Đã kiểm chứng) còn hiệu lực mới được bật và đi vào Strategy Router (Bộ định tuyến chiến lược) của Scanner. Cấu hình `DRAFT` (Bản nháp) được lưu để xem xét nhưng bị tắt đối với giao dịch; kết quả `RESEARCH_ONLY` (Chỉ nghiên cứu), kết quả danh mục nhiều mã và kết quả quét độ nhạy không được áp dụng trực tiếp.

#### Tham số SL/TP từ quét độ nhạy

Quét độ nhạy tham số là luồng khác với bốn trường Scanner ở bảng trên. Kết quả được lưu tại thư mục `param_tuning` trong thư mục dữ liệu ứng dụng, gồm:

- `sensitivity_results.json` (Kết quả độ nhạy dạng JSON);
- `risk_params_optimized.json` (Tham số rủi ro đề xuất dạng JSON);
- `sensitivity_report.html` (Báo cáo độ nhạy dạng HTML).

Các file này mang trạng thái `RESEARCH_ONLY` (Chỉ nghiên cứu) và `can_apply_config: false` (Không cho phép áp dụng cấu hình). Không nhập “SL multiplier” (Hệ số nhân điểm dừng lỗ) vào Min Score BT, Regime BT, Hướng BT hay RR tối thiểu BT.

Ví dụ ánh xạ đúng theo code hiện tại:

- kết quả tối ưu `min_sl_distance_atr` (Khoảng SL tối thiểu theo ATR — Biên độ dao động trung bình) được xem xét và chép thủ công vào khóa cùng tên trong `config/risk_params.json`;
- `zone_sl_buffer_atr` (Đệm SL vùng theo ATR), `swing_sl_buffer_atr` (Đệm SL điểm xoay theo ATR) và `sl_floor_buffer_atr` (Đệm sàn SL theo ATR) cũng chép vào khóa cùng tên sau khi duyệt;
- `zone_sl_cap_ratio_high_score` (Trần SL nới cho vùng chất lượng cao) và `zone_sl_high_score_threshold` (Ngưỡng điểm hiệu dụng để vùng được coi là chất lượng cao) chỉnh trực tiếp trong `config/risk_params.json`: vùng đạt ngưỡng được nới trần để SL nằm sau cấu trúc thật; vùng chất lượng cao nhưng quá xa — SL cấu trúc vượt cả trần nới — bị từ chối kế hoạch thay vì đặt SL giữa vùng; vùng điểm thấp giữ trần chặt cũ;
- phải khởi động lại ứng dụng sau khi thay đổi `config/risk_params.json`, vì module (Mô-đun) rủi ro đọc file này khi được nạp.

Có một giới hạn cần lưu ý: bộ quét 10 tham số hiện xuất khóa `min_stop_distance_atr_mult` (Hệ số khoảng dừng tối thiểu theo ATR), trong khi cấu hình chạy thật đọc khóa `min_sl_distance_atr_mult` (Hệ số khoảng SL tối thiểu theo ATR). Do hai tên không trùng nhau, không chép khóa thứ 10 này theo suy đoán; cần sửa và kiểm chứng liên kết trong code trước khi dùng.

#### Tránh overfitting (Khớp quá mức)

- Không chọn tham số chỉ vì có kết quả tốt nhất trên một giai đoạn. Quét độ nhạy đã chạy nhiều giai đoạn và trả verdict (Kết luận) `STABLE` (Ổn định), `SUSPECT` (Đáng ngờ), `OVERFIT` (Khớp quá mức) hoặc `INSENSITIVE` (Ít nhạy).
- Ưu tiên cấu hình có kết quả ổn định ở nhiều chế độ thị trường, không chỉ giá trị có Net R (R sau chi phí) cao nhất.
- Dùng Validation (Kiểm chứng) để tối ưu trên IS (Trong mẫu) và đánh giá trên OOS (Ngoài mẫu) mà không thay đổi cấu hình giữa hai giai đoạn.
- Yêu cầu Walk-Forward (Kiểm tra cuốn chiếu) có ít nhất 2 cửa sổ hợp lệ, verdict (Kết luận) `ROBUST` (Vững) và tổng OOS đạt ít nhất 8 lệnh, `0.10R` kỳ vọng, Profit Factor (Hệ số lợi nhuận) `1.20`.
- Không kích hoạt bản nháp hoặc kết quả nghiên cứu cho giao dịch thật; validator (Bộ kiểm chứng) của Scanner sẽ từ chối cấu hình thiếu bằng chứng, hết hạn hoặc sai phiên bản.

### 3.6 Lỗi thường gặp khi Backtest

| Hiện tượng/thông báo | Nguyên nhân theo code | Cách xử lý |
|---|---|---|
| “MT5 chưa kết nối đầy đủ hoặc chưa đăng nhập” hoặc “Chưa cài package MetaTrader5” | Controller (Bộ điều khiển) kiểm tra kết nối và đăng nhập trước khi tải lịch sử; service (Dịch vụ) cũng cần gói Python MetaTrader5 | Cài đúng gói phụ thuộc, mở MT5, đăng nhập tài khoản, chờ terminal (Phần mềm đầu cuối) báo đã kết nối rồi chạy lại |
| “Không chọn được mã … trong MT5 Market Watch” hoặc “Không lấy được OHLCV…” | Mã broker (Nhà môi giới) không được chọn, tên mã không khớp hậu tố của broker hoặc broker không trả dữ liệu trong khoảng ngày | Thêm mã vào Market Watch (Danh sách mã theo dõi), dùng nút chọn mã/tự phát hiện mã broker trong Settings > Dữ liệu (Cài đặt > Dữ liệu), rồi kiểm tra lại khoảng lịch sử |
| “Thời điểm kết thúc phải sau thời điểm bắt đầu” | Ngày Đến không sau ngày Từ khi yêu cầu dữ liệu được tạo | Chọn lại khoảng ngày hợp lệ; nhớ ứng dụng tự bao gồm trọn ngày Đến |
| Validation (Kiểm chứng) báo thiếu khung thực thi hoặc dữ liệu không đạt chuẩn | Validation yêu cầu dữ liệu chất lượng không có cả cảnh báo/lỗi và phải có M15 để mô phỏng thực thi | Tải đủ D1/H4/H1/M15 từ MT5, chọn khoảng có lịch sử liên tục và tránh chạy khi broker chưa đồng bộ xong dữ liệu |
| Không có cấu hình áp dụng, cấu hình chỉ là `DRAFT` (Bản nháp), hoặc báo mẫu/cửa sổ quá ít | Khoảng mặc định 6 tháng không đủ 2 cửa sổ Walk-Forward; IS/OOS cũng có thể chưa đạt 10/8 mẫu hoặc các ngưỡng thống kê | Chọn ít nhất 12 tháng, bảo đảm dữ liệu đầy đủ và chạy mục đích Kiểm chứng. Nếu vẫn ít lệnh, xem funnel (Phễu lọc) và lý do bị chặn; không nới điều kiện chỉ để làm đẹp kết quả |

## 4. Scanner (Bộ quét)

(Đang cập nhật)

## 5. Journal (Nhật ký)

Journal lưu analysis payload và correlation adjustment tổng hợp. Với VIX theo
pair, có thể so sánh outcome theo symbol/side/regime để phát hiện drift ở mức
tổng quát, nhưng phiên bản hiện tại chưa hiển thị riêng map version, factor,
direction hoặc chính xác bao nhiêu điểm đến từ VIX modulation.

## 6. Auto-trade (Giao dịch tự động)

(Đang cập nhật)

## 7. Diagnostics (Chẩn đoán)

(Đang cập nhật)

## 8. Settings (Cài đặt)

### VIX theo độ nhạy từng cặp tiền

Mở **Cài đặt → Nâng cao** và tìm checkbox:

> VIX theo độ nhạy từng cặp tiền (Bước 7 — chỉ bật sau backtest)

Checkbox mặc định tắt. Khi tắt, VIX dùng penalty phẳng như trước. Khi bật, ứng
dụng chỉ điều chỉnh theo pair nếu loader tìm được map backtest đủ điều kiện, còn
TTL và pair đó `actionable=true`. Candidate seed/stale/lỗi bị bỏ qua để thử
bundled fallback; chỉ khi không còn eligible candidate hoặc pair neutral mới
giữ penalty phẳng.

Trước khi bật:

1. chạy và review calibration theo
   `../macro/step7_vix_pair_sensitivity_operations.md`;
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

## 9. Troubleshooting (Khắc phục sự cố)

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Đã bật VIX theo pair nhưng điểm không đổi | Cache flag chưa refresh; loader không tìm được eligible candidate; symbol non-actionable; hoặc VIX không có base penalty âm | Đợi tối đa 60 giây, kiểm tra runbook/log, map source/expiry và mức VIX; không cố sửa map bằng tay |
| JPY vẫn bị phạt như các pair khác khi VIX cao | Backtest hiện tại không xác nhận direction của JPY pair | Đây là fail-safe đúng; không hardcode JPY. Giữ flat hoặc chạy lại calibration trên regime đã phê duyệt |
| Runner báo `hypothesis_not_confirmed` | Đủ dữ liệu nhưng không pair nào qua effect/significance gate | Giữ flag OFF. Runner hiện để map cũ nguyên trạng, vì vậy không coi map cũ là tiếp tục được phê duyệt |
| Bản cài đặt không có nút chạy lại VIX calibration | Runner chưa được bundle vào packaged app | Operator phải chạy từ source checkout; người dùng packaged app giữ feature OFF |
| Checkbox bật nhưng APPDATA map stale | UI chưa hiển thị source/age/reason; loader có thể dùng bundled fallback thay vì flat | Tắt flag, kiểm tra log để xác định map thực sự được dùng, chạy re-validation và review report trước khi bật lại |
