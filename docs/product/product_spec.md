# AI Market Analyst — Đặc tả sản phẩm

> Phiên bản tài liệu: 24/07/2026
>
> Trạng thái: đồng bộ với chương trình hiện tại
>
> Phạm vi: desktop PyQt6, MT5, phân tích, Scanner V2, backtest, journal, Telegram và order execution có kiểm soát

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
- signal/final/setup score;
- scenario Entry/SL/TP theo đúng side;
- trade permission, gate và entry status;
- Strategy Router decision;
- candidate status và reason codes;
- effective R:R, evidence/execution readiness;
- canonical ranking;
- observability, snapshot, shadow comparison;
- Telegram và auto-trade result khi áp dụng.

Scanner hỗ trợ quét một lần và quét định kỳ. Nút **Tự động vào lệnh MT5** chỉ
khả dụng trong chế độ quét định kỳ và mặc định không chọn. Khi người dùng chủ
động bật, request có `auto_trade_enabled=true`; khi chuyển sang quét một lần,
nút bị disable và reset. Auto trade và nút đặt lệnh thủ công cho candidate đều
đi qua cùng rollout và execution gates.

Việc lưu `stage=PRODUCTION` không bỏ qua release readiness hoặc safety gate.

### 3.2 Backtest

Backtest replay logic chiến lược trên dữ liệu lịch sử, hỗ trợ phân tích funnel/breakdown, equity/drawdown và validation ngoài mẫu.

Kết quả chỉ được dùng làm strategy config thực thi khi đạt contract validation hiện hành. Kết quả cũ hoặc chưa validation có status `DRAFT`/invalid và không được auto trade.

Replay dùng dữ liệu point-in-time: timestamp UTC, nến chỉ khả dụng sau khi
đóng, khoảng thời gian theo `[start, end)`, dữ liệu được sort/deduplicate và
đính kèm `DataManifest` v2 session-aware. Manifest ghi coverage, gap trong
phiên, khoảng đóng hợp lệ, session-policy fingerprint, duplicate, timezone,
OHLC quality và dataset hash. Lịch phiên xử lý riêng Forex, kim loại và crypto,
tự theo DST New York và lịch nghỉ/bảo trì có version. Backtest `VALIDATION` phải fail-closed nếu dữ
liệu không đủ chất lượng; `RESEARCH` có thể tiếp tục nhưng phải lưu/hiển thị
cảnh báo. Manifest version, point-in-time flag, quality status và dataset
hash là một phần của config fingerprint và được Strategy Router kiểm tra lại
sau khi load Settings.

Execution replay tuân theo policy có version: scenario exact-side, fill tại
close xác nhận, chỉ xét exit từ nến execution kế tiếp, xử lý gap SL/TP tại
open và ghi rõ chính sách mơ hồ khi một nến chạm cả SL/TP. Validation bắt
buộc M15, `STOP_FIRST` và không chứa synthetic/research-only trade. Thời hạn
setup/holding dùng phút thay vì số bar phụ thuộc timeframe.

Orchestration Backtest dùng `backtest-run-policy-v1`. Form chính chỉ yêu cầu
người dùng chọn `Nghiên cứu` hoặc `Kiểm chứng`: Research mặc định Mô phỏng MT5
và luôn `RESEARCH_ONLY`; Validation tự ép execution parity, tự chạy frozen
IS/OOS và Walk-Forward. Nghiên cứu nhanh chỉ có trong khu vực nâng cao, không
thể kết hợp với evidence Validation và không đủ điều kiện phát hành.

Presentation Backtest dùng `backtest-presentation-v1`. Thanh nhanh chỉ có số
lệnh, kỳ vọng, hệ số lợi nhuận, drawdown tối đa và Net R; số liệu còn lại vẫn
được giữ trong phần chi tiết/JSON. Nút cấu hình fail-closed theo lifecycle:
Research/legacy/portfolio không có nút, DRAFT chỉ lưu nháp, và chỉ kết quả đã
sẵn sàng phát hành mới được áp dụng. Snapshot phải là đơn mã và symbol phải
khớp trước khi ghi Settings.

Các công cụ chuyên sâu nằm trong tab **Nghiên cứu nâng cao**. Portfolio là lựa
chọn chủ động, mặc định tắt và bị vô hiệu hóa trong Validation; chọn nhiều mã
không tự động biến lần chạy chính thành portfolio. Portfolio, AI,
research-fast, Monte Carlo và parameter sweep đều là `RESEARCH_ONLY`, không
được áp thành cấu hình đơn mã. Monte Carlo tự chạy khi có ít nhất 30 lệnh hoặc
khi người dùng yêu cầu. Sweep dùng chung request factory, cost model và data
loader với Backtest chính, mặc định dùng mã/khoảng ngày đang chọn và lưu
dataset/provenance fingerprint trong checkpoint/report.

### 3.3 Journal và Order Management

Journal lưu kế hoạch, thực thi, outcome, R, chất lượng execution và mistake tags trong SQLite có migration. Order Management theo dõi position/order và các chức năng quản lý như break-even/trailing theo thiết kế tương ứng.

### 3.4 Settings

Settings quản lý AI provider, MT5/data, trading risk, symbol settings, display,
advanced, notification, feature flags và Scanner rollout. Hai flag Backtest cũ
`backtest_config_v2`/`backtest_engine_v2` đã bị loại khỏi runtime; Settings cũ
vẫn đọc được nhưng không ghi lại hai key này khi lưu.

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

Backtest không được nâng status hoặc bỏ qua entry, trade, portfolio, news hay rollout gate.

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

- `signal_score`: tín hiệu thô của từng side.
- `final_score`: điểm setup đã điều chỉnh.
- `setup_score`: metric chuẩn dùng live/backtest, hiện alias `final_score`.
- `opportunity_rank`: điểm 0–100 dùng xếp hạng hiển thị.
- `opportunity_score`: compatibility alias, không phải gate.
- `evidence_confidence` và `execution_readiness`: tín hiệu bổ sung phục vụ hiểu/rank candidate.

Ranking diễn ra sau filter và ưu tiên status trước điểm cơ hội. Điểm cao không thể đưa row bị block lên trước row ready hoặc mở khóa order.

## 6. Backtest config contract

Config được thực thi cần:

- schema `v8`;
- validation `backtest-v8-statistical-validation-v1`;
- release report `backtest-phase7-release-report-v1`, bắt buộc có
  `ready=true`, `approved=true`, reviewer, fingerprint và đúng
  dataset/provenance;
- validation snapshot, current-forward snapshot và legacy-forward snapshot là
  ba artifact riêng; hai snapshot forward phải cùng kỳ với giao dịch demo;
- giao dịch demo đối soát phải xuất phát từ Scanner và truy được qua correlation
  ID `AMA-FWD:*`; lịch sử tài khoản thật hoặc lệnh tay không phải release
  evidence;
- Candidate Ledger IS và frozen OOS replay là bằng chứng bắt buộc;
- Walk-Forward calendar đã khử duplicate, bootstrap probability/statistical
  power, recency và provenance đầy đủ là điều kiện phát hành;
- engine contract `phase0-backtest-safety-v1`;
- purpose `VALIDATION`, đúng validation engine version và
  `execution_parity=true`;
- execution/cost/quote-conversion version và cost-model fingerprint hợp lệ;
- scorer `scanner-v3`;
- feature `scanner-features-v3`;
- score metric `setup_score`;
- symbol, side, regime, min score và min R:R hợp lệ;
- train/OOS ranges đúng;
- cỡ mẫu, OOS metrics và confidence interval đạt;
- walk-forward `ROBUST`;
- validation fingerprint hợp lệ;
- `validated_at` và `expires_at` hợp lệ.

Sai một điều kiện bắt buộc phải fail-closed.

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
- kiểm tra rollout policy.

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

## 8. Rollout

Stage:

| Stage | Contract |
|---|---|
| `DISABLED` | Chặn mọi order Scanner. |
| `SHADOW` | Ghi V1/V2 comparison và metrics; chặn mọi order Scanner. Mặc định của mã nguồn/settings mới. |
| `DEMO_LIMITED` | Demo account và symbol allowlist. |
| `DEMO_FULL` | Demo account. |
| `CANARY` | Canary readiness và risk cap. |
| `PRODUCTION` | Approval và release readiness. |

`kill_switch` luôn chặn. Settings mới và settings migrate đều mặc định `SHADOW`.

Runtime hiện tại đã chọn `PRODUCTION`, bật V2 và
`production_approved=true`, nhưng release readiness vẫn `false`. Đây không
phải trạng thái production-ready và không bỏ qua các yêu cầu dưới đây. Xem
`runtime-status.md`.

Release readiness mặc định yêu cầu:

- ít nhất 100 shadow samples;
- ít nhất 20 demo orders;
- ít nhất 5 canary orders;
- unsafe disagreement rate ≤ 10%;
- revalidation failure rate ≤ 5%;
- performance degradation ≤ 15%;
- không side mismatch, premature order hoặc portfolio violation;
- có OOS/demo evidence và rollback đã kiểm thử.

## 9. Observability và dữ liệu runtime

Mỗi scan/row/order có ID, hash, version, timestamp, branch, side, score, gate, portfolio và rollout decision.

App-data lưu:

- `scanner_snapshots/scanner_{scan_id}.json`;
- `scanner_analysis/{scan_id}/{symbol}.json`;
- `logs/scanner-events.jsonl`;
- `rollout/scanner-rollout-metrics.json`;
- journal SQLite và settings theo `config.paths`.

Snapshot/replay không được chứa credential nhạy cảm.

## 10. Telegram

Detailed alert chỉ áp dụng cho candidate canonical `READY_NOW` có trade plan hợp lệ. Alert không có quyền gửi lệnh và không thay rollout/execution gate.

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
- hiển thị rõ candidate status, strategy branch/config status và rollout stage;
- Scanner Detail phải đọc canonical selected-side cho status, score,
  entry/SL/TP, vị trí giá, effective/nominal R:R, Gate và macro raw; thiếu dữ
  liệu hiển thị unknown thay vì mặc định pass;
- action có khả năng đặt lệnh phải nổi bật và luôn chịu rollout guard;
- text tiếng Việt dễ hiểu, thuật ngữ trading có thể giữ tiếng Anh kèm giải thích.

## 12. Packaging

Ứng dụng phải đóng gói được trên Windows, gồm assets, QSS, chart assets, migrations và hidden imports của PyQt6/PyQt6-WebEngine/MetaTrader5. User data nằm trong app-data, không ghi đè source/package.

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
- rollout/migration/readiness;
- MT5, Telegram, journal và backtest integration.

Code/tooling của kế hoạch Scanner 0–8 đã hoàn tất. Trạng thái production vẫn phụ thuộc validation thực tế: shadow, demo, canary, OOS/demo evidence, rollback và soak test.

## 14. Nguyên tắc an toàn bất biến

- Không đặt lệnh nếu người dùng không yêu cầu.
- Không đặt lệnh khi rollout policy chặn.
- Không đặt lệnh từ row ngoài canonical `READY_NOW`.
- Không dùng config backtest invalid.
- Không ghép score và scenario khác side.
- Không bỏ qua fresh-price revalidation.
- Không bỏ qua news/account/portfolio risk.
- Không để UI hoặc AI gọi MT5 order API trực tiếp.
- Không coi exception hoặc missing data là pass.
