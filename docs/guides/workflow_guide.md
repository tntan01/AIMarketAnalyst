# Quy trình vận hành Backtest → Scanner → Rollout

Trạng thái tài liệu: **hiện hành**, đồng bộ với runtime ngày 25/07/2026.

Khi phát hành cấu hình Backtest `VALIDATED`, thực hiện thêm quy trình golden,
shadow, forward-demo và review tại `docs/backtest/backtest-release-runbook.md`.
Không dùng OOS trade của snapshot validation thay cho forward evidence. Cần tạo
snapshot current-forward và legacy-forward trên đúng khoảng thời gian chạy demo,
rồi xuất các lệnh Scanner đã đóng bằng `scripts/export_mt5_forward_demo.py`.
Exporter sẽ từ chối tài khoản thật và các lệnh không có correlation `AMA-FWD:*`.

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

Luồng sử dụng hiện hành:

1. Bấm **Chọn** và đánh dấu một hoặc nhiều mã. Luồng chính luôn chạy mã đầu
   tiên. Muốn đánh giá nhiều mã, mở **Nghiên cứu nâng cao** và bật chủ động
   **Đánh giá danh mục nhiều mã**; tùy chọn này yêu cầu ít nhất hai mã và không
   dùng được trong Validation.
2. Chọn mục đích `Nghiên cứu` hoặc `Kiểm chứng`. Nghiên cứu tạo
   `RESEARCH_ONLY`; Kiểm chứng tự ép Mô phỏng MT5, tự chạy frozen IS/OOS và
   Walk-Forward. Hoàn tất replay tạo `DRAFT` và vẫn phải qua validator trước
   khi thành `VALIDATED`.
3. Luồng thông thường mặc định dùng **Mô phỏng MT5**. Chỉ vào tab
   **Nghiên cứu nâng cao** khi cần Nghiên cứu nhanh; chế độ này luôn
   `RESEARCH_ONLY` và không thể kết hợp với evidence Validation.
4. Với Research dùng Mô phỏng MT5, có thể chủ động chạy thêm IS/OOS và
   Walk-Forward trong phần nâng cao; kết quả vẫn không được phát hành.
5. Có thể bấm **Hủy**. Kết quả dở dang không tạo snapshot; sweep giữ checkpoint
   phần hoàn tất để lần chạy sau tiếp tục.
6. Monte Carlo tự chạy khi kết quả có ít nhất 30 lệnh. Với mẫu nhỏ, bật
   **Yêu cầu chạy Monte Carlo** nếu vẫn cần khảo sát uncertainty; kết quả luôn
   là bằng chứng nghiên cứu, không tự phát hành config.
7. Parameter sweep mặc định dùng mã và khoảng ngày trên form chính. Chỉ bật
   **Sweep tất cả mã đã chọn** khi chấp nhận workload lớn hơn; báo cáo sweep
   không tự áp tham số và phải được kiểm chứng lại bằng Validation mới.

Lưu `DRAFT`, config hết hạn hoặc sai version chỉ lưu evidence để xem lại và
không tự xóa symbol khỏi Scanner. Chỉ config `VALIDATED` mới được kích hoạt;
thao tác tắt đã xác nhận mới gỡ mã khỏi `enabled_symbols`.

Hành động trên kết quả phụ thuộc lifecycle:

- `RESEARCH_ONLY`, kết quả cũ, review chưa đạt và portfolio: chỉ xem/phân tích;
- `DRAFT`: **Lưu đề xuất nháp**, không kích hoạt Strategy Router;
- `VALIDATED`/`RELEASE_READY`: **Áp dụng cấu hình**;
- khi tải snapshot, luôn kiểm tra mã trên form đã tự đồng bộ đúng với file trước
  khi lưu. Hệ thống sẽ chặn nếu snapshot nhiều mã hoặc symbol không khớp.

1. Mở màn hình **Backtest**, chọn symbol, khoảng train và khoảng validation ngoài mẫu.
2. Chạy backtest và xem expectancy, profit factor, drawdown, confidence interval và walk-forward.
3. Chỉ config đáp ứng đầy đủ schema/validation hiện hành mới có status `VALIDATED`.
4. Config cũ được migrate thành `DRAFT`; hệ thống không tự nâng lên `VALIDATED`.
5. Config hết hạn, sai scorer/feature version, thiếu fingerprint hoặc thiếu bằng chứng OOS sẽ fail-closed.

Mỗi kết quả mới có `DataManifest`. Trước khi dùng làm bằng chứng validation,
kiểm tra:

- `quality_status=OK` và `validation_eligible=true`;
- timezone đã chuẩn hóa UTC;
- không có duplicate, duplicate xung đột hoặc OHLC lỗi;
- không có `UNEXPECTED_DATA_GAP` trong phiên hoặc trong quality lookback; cuối
  tuần, ngày lễ và khoảng bảo trì hợp lệ phải được session calendar có version
  phân loại và lưu riêng;
- dataset hash và coverage đúng khoảng dữ liệu dự kiến;
- train/OOS tuân theo `[start, end)`, boundary chỉ thuộc OOS.
- execution policy đúng version, fill model `confirmation_close`, exit model
  `next_execution_candle`, timeframe M15 và same-bar policy `STOP_FIRST`;
- không có trade `synthetic_fallback` hoặc `research_only`.

Kết quả `RESEARCH` có manifest `WARNING/INVALID` vẫn được lưu để điều tra,
nhưng không được phát hành config `VALIDATED`.
Các trường manifest/hash đã nằm trong validation fingerprint; sửa thủ công
Settings hoặc làm mất metadata sẽ khiến Router chuyển config sang
`BACKTEST_INVALID`/`VERSION_MISMATCH`.

Config được Router chấp nhận cần phù hợp với các version hiện hành:

- backtest config schema `v8`;
- engine contract `phase0-backtest-safety-v1`;
- purpose `VALIDATION`;
- engine `system-backtest-v2-execution-parity`;
- `execution_parity=true`;
- scorer `scanner-v3`;
- feature `scanner-features-v3`;
- validation `backtest-v8-statistical-validation-v1`;
- Candidate Ledger `backtest-candidate-ledger-v1`, frozen strategy
  `frozen-strategy-config-v1` và OOS replay `candidate-replay-v1`;
- `frozen_strategy_applied=true` và `oos_replay=true`;
- Walk-Forward calendar v2 đã khử duplicate OOS;
- bootstrap edge probability/statistical power đạt chuẩn;
- provenance có code revision hợp lệ và dữ liệu validation không quá 365 ngày;
- execution model `backtest-execution-parity-v1` và cost model
  `backtest-cost-model-v1` có fingerprint hợp lệ.

Ngoài version, config còn phải có symbol, side, regime, `min_score`, `min_rr`, khoảng train/OOS hợp lệ, cỡ mẫu, CI, walk-forward, fingerprint và thời hạn.

Màn hình Backtest mặc định chạy `EXECUTION_PARITY` để phản ánh spread,
slippage, commission, swap, lot constraints và quote conversion. Purpose
`RESEARCH` luôn là `RESEARCH_ONLY`; purpose `VALIDATION` tự tạo evidence nhưng
vẫn chỉ là `DRAFT` cho tới khi toàn bộ validator và release gate đạt.

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
   **Tự động vào lệnh MT5** chỉ khả dụng ở chế độ quét tự động và mặc định tắt.
   Chỉ bật khi thực sự muốn Scanner gửi candidate hợp lệ tới đường thực thi
   MT5; quét một lần không tự đặt lệnh.
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
trong dialog lệnh. Khi runtime là `PRODUCTION` và đã có production approval,
thao tác thủ công này bỏ qua riêng `RELEASE_GATE_NOT_READY`; auto trade vẫn
chịu release readiness. Cả hai vẫn đi qua revalidation và các guard còn lại.

Ngay trước khi gửi lệnh, hệ thống lấy snapshot mới và kiểm tra lại:

- kết nối, đăng nhập và quyền trade của MT5;
- bid/ask, độ cũ tick, spread và trạng thái symbol;
- entry zone, SL/TP và effective R:R theo giá mới;
- blackout tin tức;
- lot theo balance/risk và quy tắc volume của broker;
- daily/weekly loss, chuỗi thua;
- tổng open risk, risk theo symbol, currency/correlation exposure và số lệnh;
- rollout stage, kill switch, demo/allowlist/readiness/risk cap. Với thao tác
  thủ công ở `PRODUCTION`, chỉ riêng release readiness được override có chủ
  đích; các rollout block khác vẫn giữ nguyên.

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

Snapshot ngày 24/07/2026 lúc cập nhật tài liệu: shadow đã đạt `572/100`,
rollback đã đạt và không có side mismatch/unsafe disagreement. Các điều kiện
còn thiếu là `0/20` demo orders,
`0/5` canary orders, OOS evidence và demo evidence. Không sửa metrics bằng tay
để vượt checklist.

## 8. Xử lý tình huống thường gặp

- **Config hiện `DRAFT` hoặc `BACKTEST_INVALID`:** chạy lại validation theo schema hiện hành; không sửa status bằng tay.
- **Row `READY_NOW` nhưng không có lệnh:** xem `reason_codes`, rollout stage và kết quả execution revalidation.
- **Đang ở `SHADOW`:** hành vi không gửi lệnh là đúng, kể cả người dùng bấm đặt lệnh từ Scanner.
- **Đã chọn `PRODUCTION` nhưng Scanner không tự vào lệnh:** kiểm tra chế độ
  quét định kỳ và nút auto-entry đã được người dùng bật hay chưa. Auto trade
  vẫn bị chặn khi `release_readiness.block_codes` chưa rỗng.
- **Demo không được nhận diện:** kiểm tra tên server MT5 có thể hiện demo/trial/practice/contest.
- **Production bị chặn:** xem `release_readiness.block_codes` và bổ sung đúng bằng chứng còn thiếu.
