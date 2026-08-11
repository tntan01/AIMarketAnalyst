# Đánh giá cách chấm điểm và hướng nâng cấp AI cho Scanner

## Kết luận

Scanner hiện được thiết kế khá tốt về an toàn, khả năng truy vết và tách biệt giữa score, gate và ranking. Điểm yếu chính nằm ở năng lực dự báo: điểm số hiện phản ánh “bao nhiêu quy tắc đang đồng thuận”, nhưng chưa trả lời được câu hỏi quan trọng nhất:

> Với bối cảnh hiện tại, xác suất TP trước SL và kỳ vọng lợi nhuận sau chi phí là bao nhiêu?

## Cách chấm điểm hiện tại

Luồng chính gồm:

1. `signal_score`: cộng điểm trend, momentum, location, SMC, risk và macro theo trọng số regime cố định tại `core/signal_engine.py`.
2. `setup_score`/`final_score`:

   `65% signal + 20% historical evidence + 15% execution quality`

   Công thức nằm trong `core/final_score_engine.py`.
3. Nếu không có chiến lược backtest hợp lệ, Strategy Router dùng các ngưỡng mặc định: score 65, R:R 1.3 và Buy/Sell gap 10 tại `core/scanner_strategy_router.py`.
4. Candidate sau đó mới đi qua entry readiness, gate và phân trạng thái.
5. `opportunity_rank` tiếp tục tổng hợp 55% setup score, 15% R:R, 10% vị trí giá, 10% evidence và 10% readiness, rồi trừ spread/news tại `core/scanner_ranking_engine.py`.

## Nhược điểm và hạn chế về mặt tính năng

### 1. Điểm không phải xác suất hay expected value

`setup_score = 65` không có nghĩa là xác suất thắng 65%, cũng không bảo đảm expectancy dương. Đây là trung bình có trọng số của nhiều thang điểm tự xây dựng.

Hệ quả:

- Khó so sánh thật sự giữa EUR/USD, XAU/USD, GBP/JPY và các thị trường khác.
- Hai setup cùng 70 điểm có thể có phân phối rủi ro hoàn toàn khác nhau.
- Không biết mức chênh 68 và 72 có ý nghĩa thống kê hay chỉ do quy tắc làm tròn hoặc chia bucket.

### 2. Trọng số và ngưỡng còn mang tính heuristic

Regime chỉ chọn một trong vài bộ trọng số cố định. Bên trong mỗi thành phần lại có nhiều mốc rời rạc như RSI, ATR, khoảng cách zone, news và spread.

Cách cộng tuyến tính này khó mô hình hóa các tương tác như:

- SMC tốt nhưng momentum đã quá muộn.
- Trend mạnh nhưng entry nằm cuối nhịp.
- Zone đẹp trong điều kiện thanh khoản hoặc session không phù hợp.
- Cùng một tín hiệu nhưng hiệu quả khác nhau theo symbol, phiên và chế độ biến động.

Ngưỡng mặc định 65/1.3/gap 10 vì thế khá “một cỡ cho tất cả”.

### 3. Bằng chứng lịch sử còn yếu hoặc chưa hoạt động đúng vai trò

Khi chưa đủ 30 lệnh phù hợp, `evidence_score` mặc định bằng 50 trong `core/statistical_edge_engine.py`. Khi thiếu dữ liệu execution, pipeline lại fallback execution quality về chính `signal_score` trong `core/analysis_pipeline.py`.

Điều đó khiến điểm cuối có vẻ đã kết hợp ba nguồn độc lập, nhưng trong nhiều trường hợp thực tế vẫn chủ yếu là điểm rule-based.

Ngoài ra, engine backtest hiện hành chỉ phát hành kết quả `RESEARCH`, không đủ điều kiện tạo config live validated. Do đó Router thường phải chạy `DEFAULT_RULES` thay vì chiến lược đã chứng minh OOS. Trạng thái này được ghi nhận trong `docs/scanner/technical-scoring-architecture.md`.

### 4. Có hiện tượng tái sử dụng cùng một thông tin ở nhiều tầng

Một số yếu tố như news, spread, journal evidence hoặc readiness xuất hiện trong signal/setup, journal cap và ranking. Dù từng tầng có mục đích khác nhau, kết quả chức năng có thể là một rủi ro bị phạt nhiều lần hoặc một evidence được tưởng thưởng nhiều lần.

Đặc biệt, “execution quality lịch sử của người dùng” được trộn vào “chất lượng setup thị trường”. Hai khái niệm này nên được nhìn riêng: setup tốt không nhất thiết trở thành setup xấu chỉ vì trước đây người dùng thường vào trễ hoặc quản lý lệnh kém.

### 5. Điểm là snapshot, chưa dự báo thời điểm vào lệnh

Scanner biết trạng thái hiện tại nhưng chưa dự báo:

- Khả năng zone còn giữ được trong 2–4 nến tới.
- Xác suất M15 xác nhận trong một khoảng thời gian cụ thể.
- Setup đã quá muộn hay còn dư địa.
- Khi nào candidate nên hết hạn.

Bởi vậy một row xếp hạng cao vẫn có thể nhanh chóng mất chất lượng giữa hai lần scan.

### 6. AI hiện mới là lớp audit hẹp

AI đã tồn tại nhưng quyền hạn rất hạn chế:

- AI review SMC zone chỉ được trừ 2 điểm khi nhận định yếu; không được cộng điểm. Logic nằm tại `core/smc_scorer.py` và `core/smc_zone_ai_review.py`.
- Macro AI mặc định tắt, chỉ xét side đã được rule engine chọn, chỉ được trừ tối đa 5 điểm hoặc veto. Direction đã được chọn trước khi Macro AI chạy trong `core/analysis_pipeline.py`, nên AI không thể đánh giá lại đầy đủ BUY và SELL.
- Setup Auditor hiện là thao tác thủ công sau scan; scan chính ghi `ai_called=0` trong `controllers/scanner_controller.py`. Kết quả audit không tham gia score, candidate status hay ranking.

AI chủ yếu đọc các số liệu tóm tắt do rule engine tạo ra, chưa nhìn chuỗi giá đa khung thời gian hay học trực tiếp từ outcome.

## Ba nâng cấp AI nên ưu tiên

### 1. AI Meta-Scorer dự báo xác suất và expectancy

Huấn luyện model trên Candidate Ledger và journal point-in-time để dự báo riêng cho BUY và SELL:

- `P(TP trước SL)`.
- Expected R sau spread/slippage.
- Xác suất invalidation.
- MFE/MAE dự kiến.
- Khoảng tin cậy và trạng thái out-of-distribution.

Model nên dùng toàn bộ component hiện tại cộng symbol, regime, session, spread, news và trạng thái zone. Đầu ra này nên trở thành một metric mới như `predicted_edge`, không giả làm `setup_score`.

Điểm tích hợp phù hợp nhất là giữa `SideEvaluation` và Strategy Router. Chỉ cho phép ảnh hưởng live sau walk-forward/OOS calibration; khi model thiếu tin cậy hoặc bị data drift thì fallback về rule engine. Đây là nâng cấp có giá trị cao nhất.

### 2. Model chuỗi đa khung thời gian để đánh giá zone và timing

Thay vì cho LLM đọc vài trường JSON, dùng model time-series nhìn trực tiếp:

- OHLC/tick D1–H4–H1–M15.
- Mask của OB/FVG/liquidity sweep/entry zone.
- Quá trình tiếp cận zone, displacement và phản ứng giá.
- Spread và session tại từng thời điểm.

Model dự báo `zone_hold_probability`, `confirmation_probability_next_N_bars`, fake-breakout risk và thời gian hết hạn setup.

Ứng dụng thực tế:

- Phân biệt “zone đẹp nhưng chưa nên vào” với “zone đang bắt đầu phản ứng”.
- Chuyển WAITING sang READY có cơ sở xác suất.
- Loại setup cuối nhịp hoặc xác nhận quá muộn.
- Cải thiện timing mà vẫn để Risk Engine quyết định entry/SL/TP.

### 3. AI Context Engine toàn thị trường và portfolio-aware

Xây một lớp AI chung cho cả lần scan, thay vì phân tích từng symbol gần như độc lập. Lớp này kết hợp:

- DXY, yield curve, VIX, commodities và currency strength.
- Nội dung và surprise của tin kinh tế, không chỉ mức impact.
- Tương quan động giữa các candidate.
- Vị thế đang mở và mức phơi nhiễm theo từng currency.
- Session, thanh khoản và mức độ crowded của cùng một market thesis.

Đầu ra nên là **marginal expected value**: thêm candidate này vào danh mục hiện tại có thực sự làm portfolio tốt hơn không. Nó giúp tránh trường hợp top 3 của bảng thực chất đều là cùng một cược “USD mạnh” dưới ba symbol khác nhau.

Các account/news/portfolio/execution gate hiện tại vẫn phải giữ quyền phủ quyết cuối cùng; AI chỉ nâng chất lượng chọn cơ hội và thời điểm.

## Định hướng tổng quát

Scanner hiện là một rule engine có safety tốt, chưa phải một hệ thống học edge. Hướng nâng cấp hợp lý không phải cho LLM tự quyết định vào lệnh, mà là thêm các dự báo đã calibration về xác suất, expectancy, timing và rủi ro liên thị trường trước các gate xác định hiện có.
