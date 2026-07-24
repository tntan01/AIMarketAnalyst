# Scanner V2 — Luồng chạy hiện hành

Cập nhật: **24/07/2026**. Tài liệu này là runtime contract cho tính năng Quét thị trường.

## 1. Tổng quan

```text
ScannerScreen
  → ScannerRequest
  → ScannerController.run()
      → tạo scan context và rollout policy
      → lấy MT5/macro data
      → phân tích song song từng symbol
      → Candidate Engine
          → đánh giá BUY và SELL độc lập
          → Strategy Router
          → Execution Readiness tại thời điểm scan
      → lọc và canonical ranking
      → observability + shadow V1/V2
      → build output
      → auto trade qua rollout guard và shared execution path
      → metrics/readiness + Telegram + snapshot
```

Scanner không còn luồng “backtest ghi đè `stand_aside` thành `ready`”. Backtest chỉ là đầu vào của Strategy Router.

### SMC scorer đang hoạt động

- Runtime mặc định và settings đã lưu dùng `smc_scoring_mode=v2`.
- SMC v2 quyết định điểm SMC theo BUY/SELL và canonical zone được đưa vào
  scenario, trade plan và gate. Không có canonical zone hợp lệ thì không
  fallback sang technical zone để tạo plan.
- SMC v1 vẫn chạy làm dữ liệu đối chiếu và có thể được chọn lại bằng mode
  `legacy`; mode `shadow` giữ quyết định v1 nhưng tính thêm v2 để so sánh.
- Scanner contract hiện là `scanner-v3/scanner-features-v3`; backtest config
  dùng schema v4/`phase8-smc-v2-oos-v1`, bắt buộc ghi rõ `smc-v2`; config cũ
  hoặc thiếu SMC identity bị từ chối và cần chạy backtest lại.
- Đây là thay đổi nguồn quyết định phân tích, không phải mở quyền gửi lệnh.
  Runtime hiện chọn stage `PRODUCTION`, nhưng release readiness, kill switch
  và các execution gate vẫn có quyền chặn. Giá trị mặc định của mã nguồn vẫn
  là `SHADOW`.

## 2. Tạo `ScannerRequest`

**Nguồn chính:** `ui/screens/scanner_screen.py`, `core/scanner.py`, `core/backtest_config.py`.

Request chứa:

- danh sách symbol và mode quét;
- balance/risk phục vụ preview;
- decision thresholds theo symbol;
- backtest config đã serialize theo symbol;
- trạng thái yêu cầu auto trade;
- các feature flag phục vụ rollout/provenance.

Ba feature flag Scanner có giá trị mặc định mã nguồn là `false`; runtime hiện
đã lưu cả ba ở `true`. Các flag được ghi vào scan context nhưng không có quyền
khôi phục đường auto-trade V1 hoặc bỏ qua safety invariant; rollout policy vẫn
là gate cho execution.

`analysis_thresholds_for_symbol()` luôn giữ `decision_ready/watch/wait` độc lập với config backtest. Giá trị mặc định là 65/60/55; pipeline `min_rr` mặc định 1.3.

Nếu settings cũ chứa cấu hình backtest, migration chỉ tạo config `DRAFT`. Config đó không được thực thi như strategy đã validation.

Trạng thái runtime ngày 24/07/2026: toàn bộ 31 config `DRAFT` đã tắt cờ
`backtest` nhưng giữ nguyên metadata để dùng lại sau. Vì vậy ScannerRequest hiện
không mang backtest config và Strategy Router dùng `DEFAULT_RULES` cùng SMC v2.
Backtest/OOS không phải điều kiện để hiển thị quyết định v2, nhưng vẫn là điều
kiện trước production rollout.

Settings/Symbols cũng áp dụng fail-closed tại nguồn:

- chỉ config được canonical validator xác nhận `VALIDATED`, đúng SMC-v2 và còn
  hạn mới có thể bật;
- config `DRAFT/INVALID/EXPIRED` được giữ metadata nhưng bắt buộc
  `backtest=false`, đồng thời bị loại khỏi `enabled_symbols`;
- Min Score/Regime/Hướng/RR của Backtest là dữ liệu chỉ đọc; Settings chỉ cho
  sửa độc lập các ngưỡng live `Ready/Watch/Wait`;
- dán config JSON chỉ tạo preview và chạy validator, không tự kích hoạt.

Vì vậy đường Settings bình thường không còn có thể tạo
`backtest=true + status=DRAFT` để đẩy Scanner vào `BACKTEST_INVALID`.
Nhánh `BACKTEST_INVALID` vẫn tồn tại để fail-closed với request/config bên
ngoài hoặc dữ liệu lỗi đi vòng qua Settings.

## 3. Khởi tạo scan và rollout

**Nguồn chính:** `controllers/scanner_controller.py`, `core/scanner_observability.py`, `core/scanner_rollout.py`.

Controller:

1. tạo `scan_id`, `settings_hash`, `request_hash` và timestamp;
2. đọc rollout settings và MT5 server;
3. tính canary/release readiness từ metrics bền vững;
4. tạo `ScannerRolloutPolicy`;
5. phát event bắt đầu scan.

Rollout guard fail-closed. `SHADOW` là mặc định và chặn order trước cả
execution snapshot. Runtime ngày 24/07/2026 đã chọn `PRODUCTION` và
`production_approved=true`, nhưng `release_ready=false`; vì vậy policy hiện
vẫn chặn bằng `RELEASE_GATE_NOT_READY`.

## 4. Thu thập và phân tích dữ liệu

Controller kiểm tra kết nối MT5, resolve broker symbol, lấy candle các timeframe cần thiết và macro context. Các symbol được phân tích song song.

Pipeline phân tích tạo dữ liệu kỹ thuật/macro, scenario theo từng side, score, entry status, gate result và R:R. Candidate Engine không được dùng scenario của BUY cho SELL hoặc ngược lại.

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
| `OUT_OF_STRATEGY` | Setup không khớp branch chiến lược. |
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

## 8. Shadow comparison và observability

**Nguồn chính:** `core/scanner_rollout.py`, `core/scanner_observability.py`, `services/observability_service.py`.

Nếu bật shadow comparison, hệ thống tạo bản ghi V1/V2 cho từng symbol:

- status, side và trade/wait decision;
- score gate;
- disagreement codes;
- cờ `v2_order_suppressed`.

Mỗi scan/row/order có thể truy vết bằng:

- `scan_id`, `row_id`;
- settings/request hash;
- scorer, feature, router, ranking, rollout và runtime version;
- timestamp/freshness;
- branch, side, score, gates, portfolio và decision.

Đường dẫn trong app-data:

| Artifact | Đường dẫn |
|---|---|
| Scan summary | `scanner_snapshots/scanner_{scan_id}.json` |
| Full symbol analysis | `scanner_analysis/{scan_id}/{symbol}.json` |
| Event log | `logs/scanner-events.jsonl` |
| Rollout metrics | `rollout/scanner-rollout-metrics.json` |

Replay helper dùng snapshot đã lưu để tái tạo và kiểm tra quyết định.

## 9. Build output và UI

Output gồm mode, thời gian, version, rows, summary, market brief, shadow report, rollout policy, auto-trade result, metrics/readiness, Telegram result và snapshot path.

Các cột hiện hành của `ScannerTableModel`:

| Key | Nhãn |
|---|---|
| `rank` | STT |
| `symbol` | Mã |
| `candidate_status` | Trạng thái |
| `selected_side` | Hướng |
| `market_regime` | Chế độ TT |
| `setup_score` | Setup |
| `opportunity_rank` | Cơ hội |
| `evidence_confidence` | Bằng chứng |
| `execution_readiness` | Thực thi |
| `expected_effective_rr` | R:R thực |
| `auto_trade_branch` | Nhánh |
| `strategy_config_status` | Config |
| `detail_action` | Chi tiết |

UI hiển thị rollout stage, disagreement và gate status để tránh hiểu `READY_NOW` là đã được phép đặt lệnh production.

Màn hình **Chi tiết kết quả quét** dùng
`scanner_candidate_decision` làm nguồn chuẩn:

- hero hiển thị candidate status, selected side, setup score/ngưỡng và rollout;
- Entry/SL/TP, vị trí giá, nominal/effective R:R và Gate đều thuộc cùng
  `selected_side`;
- vị trí giá được đối chiếu lại với entry zone của selected-side, không dùng
  `price_vs_zone` legacy của hướng khác;
- phần vĩ mô hiển thị `macro_raw/30`, confidence và macro status của
  selected-side, không gắn `/30` cho điểm macro đã co giãn theo trọng số;
- Gate canonical không mượn `pipeline_diagnostics` của legacy best-side;
- dữ liệu thiếu hiển thị `unknown/chưa kiểm tra`, không mặc định pass.

## 10. Auto trade và đặt lệnh thủ công

Nút **Tự động vào lệnh MT5** hiện được hiển thị ở trạng thái disable và
unchecked trong mọi chế độ quét. `ScannerScreen.AUTO_TRADE_UI_ENABLED=false`
khóa `_auto_trade_enabled()` về `false`, nên mọi request tạo từ giao diện đều
có `ScannerRequest.auto_trade_enabled=false`. Thay đổi chế độ sang auto-scan
hoặc stage sang `PRODUCTION` không thể bật lại nút.

Controller vẫn giữ đường auto-trade và canonical
`auto_trade_candidate=true` để phục vụ kiến trúc, kiểm thử và một rollout có
chủ đích trong tương lai; UI hiện hành không yêu cầu thực thi đường này.

Quét một lần có thể hiển thị nút đặt lệnh thủ công cho candidate hợp lệ. Nút
này vẫn gọi shared execution path, không gọi MT5 trực tiếp.

Mọi order từ Scanner, gồm auto và thao tác thủ công, đi qua:

```text
ScannerController.execute_order_candidate(proposal)
  → rollout guard
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

## 11. Rollout và release gate

Stage hợp lệ:

`DISABLED → SHADOW → DEMO_LIMITED → DEMO_FULL → CANARY → PRODUCTION`

- `DEMO_LIMITED`: demo server và allowlist.
- `DEMO_FULL`: demo server.
- `CANARY`: canary readiness; risk tối đa theo `canary_risk_percent`.
- `PRODUCTION`: `production_approved=true` và release readiness đạt.
- `kill_switch`: luôn thắng mọi cấu hình khác.

Readiness kiểm tra số mẫu shadow/demo/canary, disagreement, side mismatch, premature order, portfolio violation, revalidation failure, performance degradation, OOS/demo evidence và rollback.

Trạng thái runtime hiện tại:

- stage `PRODUCTION`, kill switch tắt, real account được phép;
- nút auto-entry bị disable và request từ UI luôn mang
  `auto_trade_enabled=false`;
- release readiness `false` do thiếu 20 demo orders, 5 canary orders,
  OOS evidence và demo evidence;
- do đó Scanner không thể tự động gọi MT5 từ giao diện hiện tại.

Chi tiết thay đổi theo thời điểm xem tại `docs/runtime-status.md`.

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
| Rollout | `phase8-rollout-v1` |
| Runtime | `scanner-runtime-v2` |

Config hoặc snapshot không tương thích version phải bị từ chối hoặc chỉ dùng cho mục đích hiển thị/replay có kiểm soát.
