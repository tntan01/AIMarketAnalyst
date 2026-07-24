# Quy trình vận hành Backtest → Scanner → Rollout

Trạng thái tài liệu: **hiện hành**, đồng bộ với Scanner V2 ngày 24/07/2026.

## 1. Nguyên tắc cần hiểu trước

Scanner tách ba loại quyết định:

1. **Decision Engine** phân loại chất lượng setup theo ngưỡng `ready/watch/wait`.
2. **Strategy Router** chọn đúng một nhánh chiến lược và kiểm tra setup có thuộc chiến lược hay không.
3. **Execution/Portfolio/Rollout Gate** quyết định có được gửi lệnh tại thời điểm thực thi hay không.

Backtest không thay thế hai lớp còn lại và không được nâng một setup bị chặn thành setup được phép đặt lệnh.

Ngưỡng Decision Engine mặc định cho từng symbol:

| Thuộc tính | Mặc định | Mục đích |
|---|---:|---|
| `decision_ready` | 65 | Setup đủ mức sẵn sàng nếu các điều kiện khác cùng đạt. |
| `decision_watch` | 60 | Setup cần theo dõi. |
| `decision_wait` | 55 | Setup cần chờ xác nhận. |
| `min_expected_rr` | 1.3 | R:R tối thiểu của pipeline phân tích. |

Các ngưỡng này độc lập với `min_score` và `min_rr` của chiến lược đã backtest.

## 2. Chạy và xác thực backtest

1. Mở màn hình **Backtest**, chọn symbol, khoảng train và khoảng validation ngoài mẫu.
2. Chạy backtest và xem expectancy, profit factor, drawdown, confidence interval và walk-forward.
3. Chỉ config đáp ứng đầy đủ schema/validation hiện hành mới có status `VALIDATED`.
4. Config cũ được migrate thành `DRAFT`; hệ thống không tự nâng lên `VALIDATED`.
5. Config hết hạn, sai scorer/feature version, thiếu fingerprint hoặc thiếu bằng chứng OOS sẽ fail-closed.

Config được Router chấp nhận cần phù hợp với các version hiện hành:

- backtest config schema `v3`;
- scorer `scanner-v3`;
- feature `scanner-features-v3`;
- validation `phase8-smc-v2-oos-v1`, schema v4.

Ngoài version, config còn phải có symbol, side, regime, `min_score`, `min_rr`, khoảng train/OOS hợp lệ, cỡ mẫu, CI, walk-forward, fingerprint và thời hạn.

## 3. Cấu hình Scanner

Trong **Settings**, cấu hình riêng cho từng symbol:

- `decision_ready`, `decision_watch`, `decision_wait`: ngưỡng phân loại live.
- `min_expected_rr`: ngưỡng R:R của pipeline.
- cấu hình backtest: strategy side/regime/min score/min RR và metadata validation.

Không nhập `min_score` backtest để thay cho `decision_ready`. Hai giá trị phục vụ hai quyết định khác nhau.

Trong tab **Rollout**, cấu hình stage và safety gate:

| Stage | Hành vi |
|---|---|
| `DISABLED` | Không gửi lệnh. |
| `SHADOW` | So sánh V1/V2, ghi metrics, không gửi lệnh. Đây là mặc định của mã nguồn/settings mới. |
| `DEMO_LIMITED` | Chỉ demo account và symbol trong allowlist. |
| `DEMO_FULL` | Chỉ demo account. |
| `CANARY` | Yêu cầu canary readiness; áp trần risk. |
| `PRODUCTION` | Yêu cầu phê duyệt và toàn bộ release gate đạt. |

`kill_switch=true` luôn chặn lệnh, bất kể stage.

Runtime hiện tại trên máy này đã chọn `PRODUCTION`,
`production_approved=true` và không bắt buộc demo account. Release readiness
vẫn chưa đạt nên cấu hình này chưa được phép gửi lệnh thật. Xem
`runtime-status.md`.

## 4. Quét thị trường

1. Mở **Scanner** và chọn danh sách symbol.
2. Chọn quét một lần hoặc quét tự động theo thời gian. Nút
   **Tự động vào lệnh MT5** hiện bị disable trong cả hai chế độ, nên Scanner
   chỉ quét và không tự gửi lệnh.
3. Nhấn **Quét thị trường**.
4. Kiểm tra các cột chính: trạng thái, hướng, regime, setup score, opportunity rank, evidence confidence, execution readiness, R:R thực, branch và config status.
5. Mở chi tiết để xem `reason_codes`, gate, strategy evaluation và candidate payload.

Mỗi symbol được Router đưa vào đúng một branch:

### `BACKTEST_VALIDATED`

Áp dụng khi config backtest hợp lệ và còn hiệu lực. Router kiểm tra side/regime đã khóa, `setup_score >= min_score` và `expected_effective_rr >= min_rr`.

### `DEFAULT_RULES`

Áp dụng khi symbol không có config backtest được cấu hình. Router chọn best side, yêu cầu score gap rõ, setup score và R:R đạt ngưỡng mặc định.

### `BACKTEST_INVALID`

Áp dụng khi có config nhưng config draft, malformed, hết hạn, sai version hoặc thiếu bằng chứng validation. Phân tích mặc định vẫn có thể hiển thị để người dùng tham khảo, nhưng `strategy_eligible=false` và không được auto trade.

## 5. Hiểu kết quả

Các trạng thái chuẩn:

| Trạng thái | Ý nghĩa |
|---|---|
| `READY_NOW` | Strategy phù hợp, entry và scan-time gate đạt. Chưa đồng nghĩa lệnh chắc chắn được gửi. |
| `WAITING_CONFIRMATION` | Setup cần thêm xác nhận. |
| `WATCH_ZONE` | Cơ hội đáng theo dõi nhưng chưa sẵn sàng. |
| `OUT_OF_STRATEGY` | Setup live không thuộc strategy branch đã chọn. |
| `BLOCKED` | Bị safety/trade gate chặn. |
| `DATA_UNAVAILABLE` | Thiếu hoặc lỗi dữ liệu cần thiết. |

`opportunity_rank` nằm trong thang 0–100 và chỉ dùng xếp hạng hiển thị. Nó không mở khóa đặt lệnh. `opportunity_score` nếu còn xuất hiện trong payload chỉ là compatibility alias.

## 6. Luồng đặt lệnh an toàn

Auto trade và thao tác đặt lệnh thủ công từ giao diện Scanner cùng đi qua:

`ScannerController.execute_order_candidate()`

Ở quét một lần, người dùng vẫn có thể chủ động bấm đặt một candidate hợp lệ
trong dialog lệnh; thao tác này cũng chịu cùng rollout và revalidation.

Ngay trước khi gửi lệnh, hệ thống lấy snapshot mới và kiểm tra lại:

- kết nối, đăng nhập và quyền trade của MT5;
- bid/ask, độ cũ tick, spread và trạng thái symbol;
- entry zone, SL/TP và effective R:R theo giá mới;
- blackout tin tức;
- lot theo balance/risk và quy tắc volume của broker;
- daily/weekly loss, chuỗi thua;
- tổng open risk, risk theo symbol, currency/correlation exposure và số lệnh;
- rollout stage, kill switch, demo/allowlist/readiness/risk cap.

Chỉ khi tất cả điều kiện đều đạt mới gọi `place_market_order`.

## 7. Checklist rollout trước production

Code và test nội bộ hoàn tất không đồng nghĩa production-ready. Cần tối thiểu:

- 100 shadow samples;
- unsafe disagreement rate không vượt 10%, không có side mismatch hoặc
  premature order;
- 20 demo orders;
- 5 canary orders;
- revalidation failure rate không vượt 5%;
- OOS và demo degradation không vượt 15%;
- đã ghi nhận OOS evidence, demo evidence và kiểm thử rollback;
- MT5 demo, UI và Telegram đã được soak test;
- `production_approved=true` chỉ sau review có trách nhiệm.

Metrics được lưu tại app-data trong `rollout/scanner-rollout-metrics.json`. Bằng chứng release được cập nhật qua `ScannerRolloutMetricsService.update_release_evidence()`.

Snapshot ngày 24/07/2026 lúc cập nhật tài liệu: shadow đã đạt `364/100`,
rollback đã đạt và không có side mismatch/unsafe disagreement. Các điều kiện
còn thiếu là `0/20` demo orders,
`0/5` canary orders, OOS evidence và demo evidence. Không sửa metrics bằng tay
để vượt checklist.

## 8. Xử lý tình huống thường gặp

- **Config hiện `DRAFT` hoặc `BACKTEST_INVALID`:** chạy lại validation theo schema hiện hành; không sửa status bằng tay.
- **Row `READY_NOW` nhưng không có lệnh:** xem `reason_codes`, rollout stage và kết quả execution revalidation.
- **Đang ở `SHADOW`:** hành vi không gửi lệnh là đúng, kể cả người dùng bấm đặt lệnh từ Scanner.
- **Đã chọn `PRODUCTION` nhưng Scanner không tự vào lệnh:** đây là hành vi
  hiện hành vì nút auto-entry đang bị disable và request từ UI luôn đặt
  `auto_trade_enabled=false`. Với lệnh thủ công, tiếp tục kiểm tra
  `release_readiness.block_codes`; runtime hiện còn bị chặn bởi
  `RELEASE_GATE_NOT_READY`.
- **Demo không được nhận diện:** kiểm tra tên server MT5 có thể hiện demo/trial/practice/contest.
- **Production bị chặn:** xem `release_readiness.block_codes` và bổ sung đúng bằng chứng còn thiếu.
