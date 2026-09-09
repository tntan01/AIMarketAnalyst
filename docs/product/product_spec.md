# AI Market Analyst — Đặc tả sản phẩm

> Phiên bản tài liệu: 11/08/2026
>
> Trạng thái: đồng bộ với runtime `scanner` / `scanner-features`; đồng thời
> ghi nhận Scanner là **APPROVED DESIGN — NON-RUNTIME**
>
> Phạm vi: desktop PyQt6, MT5, phân tích, Candidate Engine V2/scorer,
> Scanner target, backtest, journal, Telegram và order execution có kiểm soát

## 1. Mục tiêu

AI Market Analyst hỗ trợ trader:

- lấy dữ liệu và trạng thái tài khoản từ MT5;
- phân tích kỹ thuật, SMC, market regime, macro/news và risk;
- tạo trade plan có Entry, SL, TP, R:R và lot;
- quét nhiều symbol, phân loại và xếp hạng cơ hội;
- backtest và validation chiến lược trên dữ liệu lịch sử;
- ghi journal và gửi Telegram alert;
- gửi lệnh MT5 khi người dùng yêu cầu và toàn bộ safety gate cho phép.

AI chỉ diễn giải dữ liệu đã tính. AI không tự tạo giá, score, trạng thái ready, lot hoặc quyền execution.

## 2. Phạm vi thị trường

`config.constants.SUPPORTED_SYMBOLS` hiện có 31 symbol:

- 28 cặp Forex;
- XAU/USD;
- XAG/USD;
- BTC/USD.

MT5 service phải resolve symbol chuẩn sang broker symbol thực, kể cả hậu tố như `m`, `c` hoặc hậu tố riêng của broker.

## 3. Các chức năng chính

### 3.1 Scanner

Scanner phân tích danh sách symbol qua pipeline đầy đủ và tạo:

- market regime và BUY/SELL evaluation;
- signal/final/setup score theo runtime hiện hành;
- scenario Entry/SL/TP theo đúng side;
- trade permission, gate và entry status;
- Strategy Router decision;
- candidate status và reason codes;
- effective R:R, evidence/execution readiness;
- canonical ranking;
- observability và snapshot;
- Telegram và auto-trade result khi áp dụng.

Scanner hỗ trợ quét một lần và quét định kỳ. Nút **Tự động vào lệnh MT5** chỉ
khả dụng trong chế độ quét định kỳ và mặc định không chọn. Khi người dùng chủ
động bật, request có `auto_trade_enabled=true`; khi chuyển sang quét một lần,
nút bị disable và reset. Auto trade và nút đặt lệnh thủ công cho candidate đều
đi qua cùng execution guard chain (không có override riêng).

### 3.2 Backtest — ĐÃ LOẠI BỎ (2026-09-09)

Tính năng Backtest (replay chiến lược trên dữ liệu lịch sử + validation
config) đã bị gỡ khỏi sản phẩm.
Scanner/auto-trade vận hành độc lập: quyền auto-trade per-symbol là lựa
chọn tường minh trong Settings, cấu hình chiến lược (regime/side/min
score/min RR) đọc từ dữ liệu đã lưu; DEFAULT_RULES cho mã không cấu hình.

### 3.3 Journal và Order Management

Journal lưu kế hoạch, thực thi, outcome, R, chất lượng execution và mistake tags trong SQLite có migration. Order Management theo dõi position/order và các chức năng quản lý như break-even/trailing theo thiết kế tương ứng.

### 3.4 Settings

Settings quản lý AI provider, MT5/data, trading risk, symbol settings, display,
advanced, notification và feature flags. (Tab Scanner rollout đã bị gỡ
bỏ ngày 15/08/2026.) Hai flag Backtest cũ
`backtest_config_v2`/`backtest_engine_v2` đã bị loại khỏi runtime; Settings cũ
vẫn đọc được nhưng không ghi lại hai key này khi lưu.

`advanced.vix_pair_aware_enabled` là kill-switch cho Bước 7, mặc định `false`.
Checkbox chỉ cho phép runtime thử dùng map VIX sensitivity. Candidate
seed/stale/schema cũ/thiếu bằng chứng bị bỏ qua; loader có thể dùng bundled
fallback hợp lệ và chỉ flat khi không còn candidate eligible. Runner calibration
không được tự bật flag.

## 4. Contract quyết định Scanner

### 4.1 Decision thresholds

Mỗi symbol có:

| Field | Mặc định | Vai trò |
|---|---:|---|
| `decision_ready` | 65 | Phân loại setup live mức ready. |
| `decision_watch` | 60 | Phân loại watch. |
| `decision_wait` | 55 | Phân loại waiting. |
| `min_expected_rr` | 1.3 | Ngưỡng R:R của pipeline. |

Các ngưỡng này không bị `min_score` backtest ghi đè.

### 4.2 Strategy Router

Router trả đúng một branch:

| Branch | Khi nào dùng | Có thể auto trade? |
|---|---|---|
| `BACKTEST_VALIDATED` | Có config hợp lệ, đúng version, đủ OOS/walk-forward, còn hạn. | Có, nếu strategy và mọi gate khác đạt. |
| `DEFAULT_RULES` | Không có config backtest. | Có, nếu default strategy và mọi gate khác đạt. |
| `BACKTEST_INVALID` | Có config nhưng draft/expired/malformed/sai version/thiếu evidence. | Không. |

Backtest không được nâng status hoặc bỏ qua entry, trade, portfolio, news hay execution gate.

### 4.3 Candidate status

Status chuẩn:

- `READY_NOW`;
- `WAITING_CONFIRMATION`;
- `WATCH_ZONE`;
- `OUT_OF_STRATEGY`;
- `BLOCKED`;
- `DATA_UNAVAILABLE`.

`READY_NOW` là sẵn sàng tại scan-time, không phải cam kết order sẽ được gửi.

## 5. Chấm điểm và xếp hạng

Các field dưới đây mô tả runtime hiện hành; chúng không được dùng để suy
diễn rằng target đã được triển khai:

- `signal_score`: tín hiệu thô của từng side.
- `final_score`: điểm setup đã điều chỉnh.
- `setup_score`: metric chuẩn dùng live/backtest, hiện alias `final_score`.
- `opportunity_rank`: điểm 0–100 dùng xếp hạng hiển thị.
- `opportunity_score`: compatibility alias, không phải gate.
- `evidence_confidence` và `execution_readiness`: tín hiệu bổ sung phục vụ hiểu/rank candidate.

Ranking diễn ra sau filter và ưu tiên status trước điểm cơ hội. Điểm cao không thể đưa row bị block lên trước row ready hoặc mở khóa order.

### 5.1 Runtime — VIX pair-aware trong macro component

VIX pair-aware chỉ modulate phần VIX trong `correlation_adjustment` của macro
score theo đúng symbol và side. Nó không sửa hoặc bypass contract của
Decision/Strategy/Trade Gate, portfolio guard hay execution
revalidation; score thay đổi vẫn có thể ảnh hưởng kết quả threshold, decision
và ranking downstream theo luồng bình thường.

Khi flag OFF hoặc không còn candidate map eligible, VIX giữ công thức phẳng.
Khi flag ON và pair actionable, trade thuận flow được giảm penalty theo
data-derived factor;
trade ngược flow không được discount và có thể tăng penalty tối đa 20%.
Mapping phải đến từ common-date ΔVIX-vs-return backtest, không được hardcode theo
tên currency. Runtime contract và bằng chứng hiện hành nằm tại
[kiến trúc macro](../macro/macro_score_architecture.md).

Calibration runner này không phải System Backtest. Historical replay hiện giữ
flat VIX scoring; chỉ được bổ sung parity khi có map point-in-time/versioned để
không dùng bằng chứng tương lai cho decision date quá khứ.

### 5.2 Scanner canonical — đã cutover

Scanner chỉ chấm bốn thành phần kỹ thuật theo từng side: Trend, Momentum, Location và
SMC. Trọng số theo regime và quy tắc rounding chỉ được định nghĩa tại tài liệu
canonical bên dưới. Final/Setup score blend Technical/Evidence/Execution theo tỷ
trọng 65/20/15. Risk chuyển sang safety gate; Macro được giữ như assessment theo
side và tác động qua policy/gate. Risk, Macro và output gate không được tái nhập
vào Technical/Final/Setup score hoặc một thành phần ranking số.

Tích hợp Scanner dùng **direct cutover** sang `scanner` /
`scanner-features`: không dual scoring, không shadow và
không giữ hai scorer live sau cutover. Cutover đã hoàn tất theo
[Scanner architecture](../scanner/scanner-architecture.md), nguồn chuẩn cho
runtime; [Scanner flow](../scanner/scanner-flow.md) còn giữ phần lịch sử và có
phụ lục luồng canonical. Việc nâng cấp Location dưới đây là thay đổi riêng,
chưa được triển khai.

### 5.3 Location target — chưa triển khai, 09/09/2026

Mục tiêu là đánh giá vị trí giá so với vùng H4 đúng phía, còn hiệu lực và có
khoảng trống theo hướng giao dịch; khắc phục điểm thưởng sai vùng, xung đột và
bước nhảy lớn của công thức cũ. Đặc tả và 32 task nằm trong
[plan Location](../plans/location-scoring-upgrade-plan.md).

Sau khi triển khai, người dùng xem được điểm Location, vùng làm mốc, vùng cản,
khoảng cách theo ATR và lý do điểm thấp/không tính được. Điểm dùng close H1,
không thay cho đánh giá vị trí entry thực tế. Điểm kỹ thuật, SetupScore, side,
thứ hạng và cơ hội đủ điều kiện đặt lệnh có thể khác dù threshold giữ nguyên.
Không cam kết điểm luôn thấp hơn, ít lệnh hơn hay lợi nhuận tăng.

Giữ bốn thành phần kỹ thuật, trọng số và guard hiện có. Tính năng này không
tự đóng vị thế hay sửa SL/TP của lệnh đang mở. Không yêu cầu dịch vụ trả phí,
database mới hoặc backtest dài hạn; kiểm tra logic và một số case biểu đồ theo
plan. Nghiệm thu theo năm mốc dừng 8/14/21/28/32, không duyệt riêng từng task.

## 6. Backtest config contract — ĐÃ LOẠI BỎ (2026-09-09)

Contract bằng chứng kiểm định (schema/validation/release report/walk-forward/
fingerprint) đã bị xóa cùng engine Backtest. Router live dùng lean validator
(`core/scanner_strategy_router.validate_auto_trade_config`): đúng mã, side/regime
hợp lệ, ngưỡng dương — fail-closed về DEFAULT_RULES. Dữ liệu evidence cũ trong
settings.json vẫn đọc được (migration suy dẫn quyền/ngưỡng) cho tới lần save kế tiếp.

## 7. Execution và quản trị rủi ro

Mọi lệnh phát sinh từ Scanner đi qua `ScannerController.execute_order_candidate()`.

Ngay trước execution, hệ thống phải:

- kiểm tra MT5 connected/logged-in/trade allowed;
- lấy bid/ask và symbol metadata mới;
- kiểm tra tick freshness, spread và duplicate position/order;
- kiểm tra giá còn trong entry zone, SL/TP đúng hướng;
- tính lại effective R:R;
- lấy trạng thái blackout tin tức;
- tính lại lot theo balance, risk, contract/tick value, quote conversion và broker volume rules;
- kiểm tra account guard và portfolio risk;
- xác nhận order policy `certified()` (RuntimeOrderPolicy).

Nếu dữ liệu bắt buộc thiếu hoặc service lỗi, order bị chặn.

Risk settings gồm:

- default/max risk percent;
- daily/weekly loss;
- consecutive losses;
- max open risk;
- max symbol risk;
- max currency exposure;
- max correlated risk;
- max concurrent orders.

Không tự nâng lot lên broker minimum nếu làm vượt risk được phép.

## 8. Thực thi live (từ 15/08/2026)

Theo quyết định của owner (phần mềm cá nhân), ứng dụng chạy thật trực tiếp.
Cơ chế rollout — stage ladder
`DISABLED → SHADOW → DEMO_LIMITED → DEMO_FULL → CANARY → PRODUCTION`,
`kill_switch`, release/canary readiness — đã bị gỡ bỏ hoàn toàn khỏi codebase
ngày 15/08/2026.

Các lớp bảo vệ còn lại (tất cả fail-closed):

- **Scanner:** RuntimeOrderPolicy owner-accepted
  (`config/scanner_order_policy.json`) phải `certified()`; config thiếu/hỏng
  → `ORDER_POLICY_FAULT` + mọi candidate BLOCKED. MarketSafetyGate/MacroGate.
  Auto-entry chỉ khi người dùng chủ động bật. Execution guard chain trong
  `execute_order_candidate()` (snapshot mới, lot recalc, news, account/portfolio,
  `revalidate_execution`).
- **Order Management V2:** mặc định bật; gate = feature flag +
  `account.trade_allowed`. Không còn stage/kill switch/canary/demo gate.

Không còn kill switch phần mềm; dừng khẩn cấp = tắt feature flag, đóng lệnh ở
terminal broker hoặc ngắt kết nối MT5. Xem
[trạng thái runtime](../architecture/runtime-status.md).

## 9. Observability và dữ liệu runtime

Mỗi scan/row/order có ID, hash, version, timestamp, branch, side, score, gate và portfolio decision.

App-data lưu:

- `scanner_snapshots/scanner_{scan_id}.json`;
- `scanner_analysis/{scan_id}/{symbol}.json`;
- `logs/scanner-events.jsonl`;
- `scan_health/scan-health.json`;
- journal SQLite và settings theo `config.paths`.
- `vix_pair_sensitivity.json` do runner calibration ghi; runtime ưu tiên file
  này trước bundled fallback và recheck TTL 90 ngày.

Snapshot/replay không được chứa credential nhạy cảm.

Journal hiện chỉ cho phép audit VIX pair-aware gián tiếp qua analysis payload và
correlation adjustment tổng hợp; chưa có provenance riêng cho map/factor/VIX
contribution. Đây là giới hạn observability đang mở, không được mô tả là đã có
attribution đầy đủ.

## 10. Telegram

Detailed alert chỉ áp dụng cho candidate canonical `READY_NOW` có trade plan hợp lệ. Alert không có quyền gửi lệnh và không thay execution gate.

Nội dung nên gồm symbol, side, Entry, SL, TP, lot gợi ý, R:R, setup score, lý do và nguồn. Summary sau scan cho biết số symbol và nhóm trạng thái chính.

## 11. UI/UX

Các màn hình chính:

- Dashboard;
- Scanner và Scanner Detail;
- Backtest;
- Journal và Journal Detail;
- Orders;
- Settings.

Yêu cầu:

- tác vụ MT5/AI/scan chạy ngoài UI thread;
- Scanner dùng model/view;
- bảng Scanner dùng 14 cột theo `ScannerTableModel.COLUMNS`;
- hiển thị rõ candidate status và strategy branch/config status;
- Scanner Detail phải đọc canonical selected-side cho status, score,
  entry/SL/TP, vị trí giá, effective/nominal R:R, Gate và macro raw; thiếu dữ
  liệu hiển thị unknown thay vì mặc định pass;
- action có khả năng đặt lệnh phải nổi bật và luôn chịu execution guard chain;
- text tiếng Việt dễ hiểu, thuật ngữ trading có thể giữ tiếng Anh kèm giải thích.

## 12. Packaging

Ứng dụng phải đóng gói được trên Windows, gồm assets, QSS, chart assets,
migrations, validated `data/vix_pair_sensitivity.json` fallback và hidden
imports của PyQt6/PyQt6-WebEngine/MetaTrader5. User data nằm trong app-data,
không ghi đè source/package. Runner VIX calibration hiện là source-only và chưa
có luồng revalidate trong packaged UI.

## 13. Testing và tiêu chí hoàn thành

Nhóm test trọng yếu:

- scoring/decision/entry/trade gate;
- side and domain model;
- strategy router/config validation;
- execution revalidation/news;
- portfolio risk/settings;
- controller shared execution;
- ranking;
- observability/replay;
- order policy loader/fail-closed;
- MT5, Telegram, journal và backtest integration.
- VIX pair map eligibility/path/hot-reload, common-date calibration, side-aware
  scoring, runner failure handling và default-OFF wiring.

Code/tooling của kế hoạch Scanner đã hoàn tất và chạy live từ 15/08/2026 (chủ
động bỏ qua giai đoạn shadow/demo/canary theo quyết định của owner); an toàn
còn lại là các guard kỹ thuật fail-closed.

## 14. Nguyên tắc an toàn bất biến

- Không đặt lệnh nếu người dùng không yêu cầu.
- Không đặt lệnh khi order policy hoặc execution gate chặn.
- Không đặt lệnh từ row ngoài canonical `READY_NOW`.
- Không dùng config backtest invalid.
- Không ghép score và scenario khác side.
- Không bỏ qua fresh-price revalidation.
- Không bỏ qua news/account/portfolio risk.
- Không để UI hoặc AI gọi MT5 order API trực tiếp.
- Không coi exception hoặc missing data là pass.
