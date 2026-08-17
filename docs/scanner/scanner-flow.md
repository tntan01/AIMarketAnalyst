# Scanner V3 — Luồng runtime legacy (historical)

Runtime contract cập nhật: **09/08/2026**. Target V4: **11/08/2026**.
Cutover V4 xong: **14/08/2026**. Gỡ rollout/SHADOW, chạy thật: **15/08/2026**.

> **Hiện trạng:** Scanner V4 đang chạy live — tài liệu chuẩn là
> [`scanner-v4-architecture.md`](scanner-v4-architecture.md). Toàn bộ rollout
> machinery (stage ladder, kill switch, release/canary readiness) và chế độ
> SHADOW đã bị gỡ khỏi codebase ngày 15/08/2026 theo quyết định của owner.
> Nội dung bên dưới mô tả luồng V3 **trước cutover**, giữ lại để tra cứu lịch
> sử; riêng §11 đã được viết lại theo guard chain thực thi live hiện tại.

## 1. Tổng quan

```text
ScannerScreen
  → ScannerRequest
  → ScannerController.run()
      → tạo scan context và load RuntimeOrderPolicy (fail-closed)
      → lấy MT5/macro data
      → phân tích song song từng symbol
      → Candidate Engine
          → đánh giá BUY và SELL độc lập
          → Strategy Router
          → Execution Readiness tại thời điểm scan
      → lọc và canonical ranking
      → observability
      → build output
      → auto trade qua guard chain thực thi và shared execution path
      → scan health + Telegram + snapshot
```

Scanner không còn luồng “backtest ghi đè `stand_aside` thành `ready`”. Backtest chỉ là đầu vào của Strategy Router.

### SMC scorer đang hoạt động

- SMC là scorer chuẩn duy nhất (`core.smc_scorer.score_smc()`). Không còn
  mode `legacy/shadow/v2` để chọn scorer; `smc-v2` chỉ là metadata provenance
  của công thức, không phải một lựa chọn runtime.
- Mỗi symbol được chấm SMC đúng một lần cho cả BUY/SELL; selected zone của
  quyết định giao dịch chỉ đến từ kết quả SMC canonical này.
- SMC quyết định điểm SMC theo BUY/SELL và canonical zone được đưa vào
  scenario, trade plan và gate. Không có canonical zone hợp lệ thì không
  fallback sang technical zone để tạo plan. Nếu scorer lỗi, phân tích bị
  blocked/no-trade (`SMC_SCORING_ERROR`), không fallback sang scorer khác.
- Scanner contract hiện là `scanner-v3/scanner-features-v3`; backtest config
  dùng schema v9/`backtest-v9-statistical-validation-v1`, bắt buộc ghi rõ
  `smc_scorer_version="smc-v2"`,
  Candidate Ledger/frozen OOS replay,
  statistical power, recency và provenance code/data/execution,
  execution/cost/quote-conversion version và cost-model fingerprint,
  purpose `VALIDATION`, validation engine version và
  `execution_parity=true`, đồng thời phải có data manifest v1,
  point-in-time flag, quality `OK`, dataset hash và execution policy v1 nằm
  trong fingerprint. Policy validation bắt buộc M15, confirmation-close,
  exit từ nến kế tiếp, `STOP_FIRST` và cấm synthetic trade.
  Engine backtest hiện hành chỉ phát hành kết quả
  `RESEARCH`, vì vậy chưa thể tạo config live. Config cũ hoặc thiếu engine/SMC
  identity bị từ chối và cần chạy validation lại bằng engine mới.
- Đây là thay đổi nguồn quyết định phân tích, không phải mở quyền gửi lệnh.
  Lệnh thật vẫn chịu sự kiểm soát của RuntimeOrderPolicy (certified/fail-closed)
  và toàn bộ execution guard chain. (Trước 15/08/2026 lớp này là rollout stage
  ladder — đã gỡ bỏ.)

## 2. Tạo `ScannerRequest`

**Nguồn chính:** `ui/screens/scanner_screen.py`, `core/scanner.py`, `core/backtest_config.py`.

Request chứa:

- danh sách symbol và mode quét;
- balance/risk phục vụ preview;
- decision thresholds theo symbol;
- backtest config đã serialize theo symbol;
- trạng thái yêu cầu auto trade;
- các feature flag phục vụ provenance.

Ba feature flag Scanner có giá trị mặc định mã nguồn là `false`; runtime hiện
đã lưu cả ba ở `true`. Các flag được ghi vào scan context nhưng không có quyền
khôi phục đường auto-trade V1 hoặc bỏ qua safety invariant; RuntimeOrderPolicy
và execution guard chain vẫn là gate cho execution.

`analysis_thresholds_for_symbol()` luôn giữ `decision_ready/watch/wait` độc lập với config backtest. Giá trị mặc định là 65/60/55; pipeline `min_rr` mặc định 1.3.

Nếu settings cũ chứa cấu hình backtest, migration chỉ tạo config `DRAFT`. Config đó không được thực thi như strategy đã validation.

Trạng thái runtime ngày 24/07/2026: toàn bộ 31 config `DRAFT` đã tắt cờ
`backtest` nhưng giữ nguyên metadata để dùng lại sau. Vì vậy ScannerRequest hiện
không mang backtest config và Strategy Router dùng `DEFAULT_RULES` cùng SMC.
Backtest/OOS không phải điều kiện để hiển thị quyết định v2. (Trước cutover nó
từng là điều kiện trước production rollout; lớp rollout đó đã gỡ bỏ.)

Settings/Symbols cũng áp dụng fail-closed tại nguồn:

- chỉ config được canonical validator xác nhận `VALIDATED`, đúng scorer SMC
  canonical và còn hạn mới có thể bật;
- config `DRAFT/INVALID/EXPIRED` được giữ metadata nhưng bắt buộc
  `backtest=false`, đồng thời bị loại khỏi `enabled_symbols`;
- Min Score/Regime/Hướng/RR của Backtest là dữ liệu chỉ đọc; Settings chỉ cho
  sửa độc lập các ngưỡng live `Ready/Watch/Wait`;
- dán config JSON chỉ tạo preview và chạy validator, không tự kích hoạt.

Vì vậy đường Settings bình thường không còn có thể tạo
`backtest=true + status=DRAFT` để đẩy Scanner vào `BACKTEST_INVALID`.
Nhánh `BACKTEST_INVALID` vẫn tồn tại để fail-closed với request/config bên
ngoài hoặc dữ liệu lỗi đi vòng qua Settings.

## 3. Khởi tạo scan và order policy

**Nguồn chính:** `controllers/scanner_controller.py`, `core/scanner_observability.py`, `core/scanner_v4_order_policy.py`.

Controller:

1. tạo `scan_id`, `settings_hash`, `request_hash` và timestamp;
2. đọc MT5 server và load `RuntimeOrderPolicy` từ
   `config/scanner_v4_order_policy.json` qua `load_runtime_order_policy()`;
3. phát event bắt đầu scan.

Order policy load **fail-closed**: file thiếu/hỏng hoặc `OrderPolicyError` →
raise `OrderPolicyLoadError`, controller giữ `DEFAULT_RUNTIME_ORDER_POLICY`
(`order_enabled=False` → mọi candidate BLOCKED) và emit observability event
`ORDER_POLICY_FAULT` (severity ERROR). Config hỏng không bao giờ làm crash scan.
(Trước 15/08/2026 bước này đọc rollout settings và tính canary/release
readiness — toàn bộ đã gỡ bỏ; lệnh không còn bị chặn bởi stage ladder hay
kill switch, mà bởi policy certification và execution guard chain.)

## 4. Thu thập và phân tích dữ liệu

Controller kiểm tra kết nối MT5, resolve broker symbol, lấy candle các timeframe cần thiết và macro context. Các symbol được phân tích song song.

Pipeline phân tích tạo dữ liệu kỹ thuật/macro, scenario theo từng side, score, entry status, gate result và R:R. Candidate Engine không được dùng scenario của BUY cho SELL hoặc ngược lại.

Trong runtime `scanner-v3`, macro raw/confidence/correlation vẫn được compose vào
`signal_score`, nên có thể ảnh hưởng best side, score gap, scenario, decision và
ranking. Proposal tách score không được dùng để diễn giải snapshot hiện hành.

Trong macro correlation, `vix_pair_aware_enabled` đi từ Advanced Settings qua
`NewsService.data_quality_flags` vào `AnalysisPipeline` cho cả BUY và SELL.
Flag mặc định OFF. Chỉ schema-2 map data-backed còn TTL và pair actionable mới
được modulate VIX penalty. Candidate seed/stale/malformed bị bỏ qua để loader
thử fallback; chỉ flag OFF, không còn eligible candidate hoặc pair
non-actionable mới giữ flat scoring. Trade thuận validated flow được giảm
penalty theo factor; trade ngược flow không được discount.

Thay đổi này chỉ sửa input macro component của đúng side, không bypass logic của
Decision Engine, Strategy Router, entry/trade gate hoặc execution.
Score thay đổi có thể làm kết quả threshold/decision/ranking downstream thay đổi
theo contract bình thường. Kết quả calibration hiện tại không xác nhận
JPY/AUD-NZD; runbook nằm tại
[`../macro/macro_score_architecture.md`](../macro/macro_score_architecture.md),
mục Bước 7.

Các lỗi dữ liệu phải được biểu diễn bằng status/reason code; không được coi giá trị thiếu là điều kiện đã đạt.

## 5. Candidate Engine

**Nguồn chính:** `core/scanner_candidate_engine.py`, `core/scanner_strategy_engine.py`, `core/scanner_models.py`.

Candidate Engine thực hiện ba bước:

### 5.1 Đánh giá hai side độc lập

Mỗi `SideEvaluation` giữ cùng một side cho:

- `signal_score`;
- `final_score`/`setup_score`;
- scenario;
- entry status;
- M15 quality;
- expected effective R:R;
- gate result và reason codes.

`setup_score` hiện là metric chuẩn và alias trực tiếp của `final_score`. Việc đổi metric sau này phải đổi version scorer/config.

### 5.2 Strategy Router

Router trả đúng một trong ba branch:

#### `BACKTEST_VALIDATED`

Chỉ dùng khi config:

- status `VALIDATED`;
- schema/version/scorer/feature đúng;
- symbol, side và regime hợp lệ;
- có `min_score`, `min_rr`;
- train và OOS không chồng lấn, đủ cỡ mẫu;
- expectancy, profit factor, drawdown và confidence interval đạt chuẩn;
- walk-forward có verdict `ROBUST`;
- data manifest v1, point-in-time flag, quality `OK` và dataset hash hợp lệ;
- execution policy/fill/exit/same-bar/timeframe đúng contract và không cho
  phép synthetic trade;
- fingerprint hợp lệ và chưa hết hạn.

Sau đó Router kiểm tra live regime, side đã khóa hoặc best side, setup score và effective R:R.

#### `DEFAULT_RULES`

Dùng khi không có config backtest. Router chọn best side, yêu cầu:

- dữ liệu side/scenario hợp lệ;
- score gap tối thiểu;
- `setup_score` đạt ngưỡng mặc định hoặc ngưỡng live thích hợp;
- effective R:R đạt tối thiểu.

#### `BACKTEST_INVALID`

Dùng khi đã cấu hình backtest nhưng config không hợp lệ. Router vẫn có thể chọn side mặc định để hiển thị, nhưng luôn đặt `eligible=false`.

### 5.3 Execution Readiness tại thời điểm scan

Đánh giá entry status và scan-time trade permission để xác định row có đủ điều kiện trở thành candidate hay không. Đây chưa phải xác nhận cuối cùng để gửi lệnh.

## 6. Trạng thái candidate

Candidate decision chuẩn hóa về sáu trạng thái:

| Status | Điều kiện khái quát |
|---|---|
| `READY_NOW` | Strategy eligible, entry ready và scan-time trade gate cho phép. |
| `WAITING_CONFIRMATION` | Strategy phù hợp nhưng entry còn chờ xác nhận. |
| `WATCH_ZONE` | Setup đáng theo dõi/chưa đạt mức thực thi. |
| `OUT_OF_STRATEGY` | Hiển thị **Chưa đạt quy tắc**: cặp vẫn được hỗ trợ nhưng setup chưa đáp ứng đủ quy tắc đang áp dụng. |
| `BLOCKED` | Gate an toàn hoặc trade permission chặn. |
| `DATA_UNAVAILABLE` | Thiếu dữ liệu/side/scenario cần thiết. |

Row được gắn:

- `scanner_candidate_decision`;
- `candidate_status`;
- `selected_side`;
- `auto_trade_branch`;
- `strategy_config_status`;
- `strategy_eligible`;
- `execution_ready`;
- `trade_allowed`;
- `auto_trade_candidate`;
- `candidate_order_payload`;
- `auto_trade_reason_codes`.

`candidate_order_payload` chỉ được tạo từ canonical decision và không nhúng toàn bộ `analysis_result`.

## 7. Lọc và xếp hạng

**Nguồn chính:** `core/scanner_ranking_engine.py`, `core/scanner.py`.

Xếp hạng chỉ chạy sau khi candidate đã được đánh giá. Thứ tự ưu tiên:

1. priority của candidate status;
2. `opportunity_rank` giảm dần;
3. strategy confidence;
4. execution readiness;
5. effective R:R;
6. symbol để bảo đảm kết quả deterministic.

`opportunity_rank` có thang 0–100. Nó tổng hợp tín hiệu phục vụ ưu tiên hiển thị, không phải gate vào lệnh. `opportunity_score` chỉ còn là compatibility alias.

Sau sort, `rank` được gán theo thứ tự canonical.

## 8. Observability

**Nguồn chính:** `core/scanner_observability.py`, `services/observability_service.py`.

(Shadow comparison V1/V2 của Candidate Engine thuộc code path V3 và đã bị xóa
cùng đường V3 ở Bước 12; SMC cũng chỉ còn một scorer canonical duy nhất.)

Mỗi scan/row/order có thể truy vết bằng:

- `scan_id`, `row_id`;
- settings/request hash;
- scorer, feature, router, ranking và runtime version;
- timestamp/freshness;
- branch, side, score, gates, portfolio và decision.

Đường dẫn trong app-data:

| Artifact | Đường dẫn |
|---|---|
| Scan summary | `scanner_snapshots/scanner_{scan_id}.json` |
| Full symbol analysis | `scanner_analysis/{scan_id}/{symbol}.json` |
| Event log | `logs/scanner-events.jsonl` |
| Scan health | `scan_health/scan-health.json` |

Replay helper dùng snapshot đã lưu để tái tạo và kiểm tra quyết định.

## 9. Build output và UI

Output gồm mode, thời gian, version, rows, summary, market brief, scan health,
order policy, auto-trade result, Telegram result và snapshot path.

Các cột hiện hành của `ScannerTableModel`:

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

Cột **Vùng** (`price_vs_zone`) ánh xạ nhị phân từ trạng thái nội bộ ba mức:
`in_zone` → **Trong vùng**; `near_zone` và `far` → **Ngoài vùng**;
`unknown`/thiếu dữ liệu/fallback → `--`. Trạng thái được tính một lần
tại thời điểm quét dựa trên giá close H1. Cột không tự cập nhật real-time,
không tác động auto-trade, và execution revalidation vẫn dùng bid/ask live
để kiểm tra `PRICE_OUTSIDE_ENTRY_ZONE` trước khi gửi lệnh.

UI hiển thị disagreement và gate status để tránh hiểu `READY_NOW` là đã được
phép đặt lệnh — quyết định cuối cùng vẫn thuộc execution guard chain.
Độ rộng tối thiểu của từng cột phải bao phủ toàn bộ tiêu đề theo font/DPI hiện
tại; khi cửa sổ không đủ rộng, bảng dùng thanh cuộn ngang thay vì cắt tiêu đề.
Dialog **Kế hoạch lệnh** đọc `auto_trade_results.enabled` của chính lần quét,
không đọc trạng thái toggle hiện tại. Nội dung phải phân biệt ứng viên, kết quả
kiểm tra và lệnh thực sự đã mở (`opened`) để không diễn giải nhầm.

Màn hình **Chi tiết kết quả quét** dùng
`scanner_candidate_decision` làm nguồn chuẩn:

- hero hiển thị candidate status, selected side và setup score/ngưỡng;
- Entry/SL/TP, vị trí giá, nominal/effective R:R và Gate đều thuộc cùng
  `selected_side`;
- vị trí giá được đối chiếu lại với entry zone của selected-side, không dùng
  `price_vs_zone` legacy của hướng khác;
- phần vĩ mô hiển thị `macro_raw/30`, confidence và macro status của
  selected-side, không gắn `/30` cho điểm macro đã co giãn theo trọng số;
- Gate canonical không mượn `pipeline_diagnostics` của legacy best-side;
- dữ liệu thiếu hiển thị `unknown/chưa kiểm tra`, không mặc định pass.

## 10. Auto trade và đặt lệnh thủ công

Nút **Tự động vào lệnh MT5** chỉ khả dụng trong chế độ quét theo khoảng thời
gian và mặc định unchecked. `ScannerScreen.AUTO_TRADE_UI_ENABLED=true`; khi
người dùng chủ động bật, `_auto_trade_enabled()` trả `true` và request có
`ScannerRequest.auto_trade_enabled=true`. Chuyển sang quét một lần sẽ disable
và reset nút. Việc bật nút chỉ tạo yêu cầu auto trade, không bỏ qua candidate
hoặc execution gates.

Quét một lần có thể hiển thị nút đặt lệnh thủ công cho candidate hợp lệ. Nút
này vẫn gọi shared execution path, không gọi MT5 trực tiếp, và không có bất
kỳ override nào — mọi guard và execution revalidation áp dụng như nhau.

Mọi order từ Scanner, gồm auto và thao tác thủ công, đi qua:

```text
ScannerController.execute_order_candidate(proposal)
  → MT5 execution snapshot mới
  → tính lại lot theo giá/balance/risk/broker volume
  → news status
  → portfolio + account guard
  → execution revalidation
  → place_market_order (chỉ khi tất cả pass)
```

Revalidation kiểm tra fail-closed:

- broker/session/symbol/trade mode;
- bid/ask và tick freshness;
- spread;
- duplicate position/order;
- side, zone, SL/TP;
- effective R:R với giá thực thi;
- news blackout;
- account và portfolio limits;
- volume hợp lệ.

Không module UI nào được gọi `place_market_order` trực tiếp.

## 11. Guard chain thực thi (live từ 15/08/2026)

Toàn bộ rollout machinery của V3 — stage ladder
`DISABLED → SHADOW → DEMO_LIMITED → DEMO_FULL → CANARY → PRODUCTION`,
kill switch, release/canary readiness gates — đã bị gỡ bỏ theo quyết định của
owner (phần mềm cá nhân, chạy thật trực tiếp, không cần rollout). Không còn
chế độ SHADOW/paper cho Scanner.

Lệnh thật hiện được kiểm soát bởi các lớp kỹ thuật sau (tất cả fail-closed):

1. **RuntimeOrderPolicy** (`config/scanner_v4_order_policy.json`): phải
   `certified()` — đủ threshold floors, safety, macro và portfolio/journal —
   thì `order_enabled=True`. Config thiếu/hỏng → `ORDER_POLICY_FAULT` +
   `DEFAULT_RUNTIME_ORDER_POLICY` (`order_enabled=False`) → mọi candidate BLOCKED.
2. **MarketSafetyGate / MacroGate** tại thời điểm scan: dữ liệu thiếu hoặc thị
   trường không an toàn → `BLOCKED`/`DATA_UNAVAILABLE`, không có candidate lệnh.
3. **Auto-trade consent**: request chỉ mang `auto_trade_enabled=true` khi người
   dùng chủ động bật cho lần quét đó.
4. **`execute_order_candidate`** — chuỗi guard duy nhất cho cả auto lẫn thủ
   công: MT5 execution snapshot mới → tính lại lot → news status →
   portfolio + account guard → `revalidate_execution` → `place_market_order`.
   Manual order không có override nào.
5. **Revalidation fail-closed**: broker/session/symbol/trade mode, bid/ask và
   tick freshness, spread, duplicate position/order, side/zone/SL/TP,
   effective R:R với giá thực thi, news blackout, account/portfolio limits,
   volume hợp lệ.
6. **Khóa cấu trúc payload**: candidate payload luôn là intent
   (`sends_real_order=False`); dispatch chỉ đi qua `execute_order_candidate`.

Lưu ý vận hành: không còn kill switch phần mềm. Dừng khẩn cấp = đóng lệnh ở
terminal broker hoặc ngắt kết nối MT5 (lựa chọn có chủ đích của owner).
Chi tiết trạng thái runtime xem tại `docs/architecture/runtime-status.md`.

## 12. Version contract

| Thành phần | Version |
|---|---|
| Phase 0 safety | `phase0-safety-v1` |
| Scorer | `scanner-v3` |
| Feature | `scanner-features-v3` |
| Strategy Router | `phase2-router-v1` |
| Execution revalidation | `phase3-revalidation-v1` |
| Portfolio | `phase4-portfolio-v1` |
| Ranking | `phase6-ranking-v1` |
| Observability | `phase7-observability-v1` |
| Runtime | `scanner-runtime-v2` |

Config hoặc snapshot không tương thích version phải bị từ chối hoặc chỉ dùng cho mục đích hiển thị/replay có kiểm soát.

Target V4 đã hoàn tất: runtime là `scanner-v4` / `scanner-features-v4` sau
direct cutover (Bước 12). Score/config/snapshot V3 bị fail-closed cho live và
chỉ phục vụ replay có kiểm soát; không có router dual-score V3/V4. Chi tiết và
trạng thái từng bước nằm tại
[`scanner-v4-architecture.md`](scanner-v4-architecture.md).
