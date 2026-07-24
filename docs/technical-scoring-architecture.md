# Kiến trúc chấm điểm Scanner V2

Trạng thái: **hiện hành**, cập nhật 24/07/2026.

## 1. Mục tiêu

Kiến trúc mới tách rõ bốn câu hỏi vốn từng bị trộn lẫn:

1. Setup kỹ thuật/macro mạnh đến đâu?
2. Setup có thuộc chiến lược đang áp dụng không?
3. Setup có sẵn sàng thực thi ở thời điểm scan không?
4. Trong các setup đã phân loại, setup nào nên hiển thị trước?

Một điểm số không được trả lời thay cả bốn câu hỏi.

## 2. Các metric chuẩn

| Metric | Phạm vi | Có quyền mở lệnh? |
|---|---|---|
| `signal_score` | Sức mạnh tín hiệu thô của từng side. | Không. |
| `final_score` | Điểm setup sau các điều chỉnh phân tích. | Không trực tiếp. |
| `setup_score` | Metric chuẩn dùng chung live/backtest; hiện alias `final_score`. | Chỉ là một điều kiện của Router. |
| `opportunity_rank` | Điểm 0–100 để xếp hạng hiển thị sau phân loại. | Không. |
| `opportunity_score` | Compatibility alias của ranking. | Không. |
| `evidence_confidence` | Độ tin cậy của bằng chứng/dữ liệu. | Không độc lập. |
| `execution_readiness` | Mức sẵn sàng tại scan-time. | Không thay revalidation cuối. |
| `expected_effective_rr` | R:R dự kiến sau chi phí/giá thực tế tương ứng. | Là điều kiện, không phải quyết định duy nhất. |

Mọi điểm phải thuộc đúng side. Không được lấy score của BUY rồi ghép scenario/SL/TP của SELL.

## 3. Decision thresholds và strategy thresholds

### Decision Engine

`decision_ready/watch/wait` phân loại chất lượng live. Mặc định:

```text
ready = 65
watch = 60
wait  = 55
pipeline min_rr = 1.3
```

### Strategy Router

`min_score` và `min_rr` trong backtest config mô tả vùng chiến lược đã validation. Chúng không ghi đè decision thresholds.

Vì vậy hai phép kiểm tra có thể cùng tồn tại:

```text
Decision Engine: setup live đang ở trạng thái nào?
Strategy Router: setup có nằm trong strategy contract không?
```

Chỉ khi strategy, entry, trade gate, portfolio và rollout đều cho phép mới có order candidate có thể thực thi.

## 4. Side evaluation

`SideEvaluation` là nguồn chuẩn cho mỗi BUY/SELL:

```text
side
signal_score
final_score / setup_score
expected_effective_rr
scenario
entry_status
m15_quality
gate_result
reason_codes
```

Thiếu score/scenario/entry/gate không được mặc định thành pass. Các trường thiếu sinh reason code và thường dẫn đến `DATA_UNAVAILABLE`, `WATCH_ZONE`, `OUT_OF_STRATEGY` hoặc `BLOCKED` tùy ngữ cảnh.

## 5. Strategy branch

### `BACKTEST_VALIDATED`

Được chọn khi có config và config vượt toàn bộ lifecycle validation. Điều kiện strategy live gồm:

- regime nằm trong tập cho phép;
- side khớp side khóa hoặc best side;
- `setup_score >= min_score`;
- `expected_effective_rr >= min_rr`;
- side evaluation đầy đủ.

### `DEFAULT_RULES`

Được chọn khi không có config backtest. Điều kiện gồm:

- best side xác định rõ;
- score gap đạt tối thiểu;
- setup score đạt ngưỡng mặc định;
- effective R:R đạt tối thiểu;
- dữ liệu/scenario hợp lệ.

### `BACKTEST_INVALID`

Được chọn khi config tồn tại nhưng draft/disabled/expired/malformed/sai version hoặc thiếu bằng chứng. Branch này luôn `eligible=false`.

Không fallback ngầm từ config lỗi sang một branch auto-trade mặc định. Fallback chỉ phục vụ phân tích/hiển thị.

## 6. Candidate decision

Candidate Engine kết hợp:

```text
SideEvaluation
  + StrategyEvaluation
  + ExecutionEvaluation (scan-time)
  → ScannerCandidateDecision
```

Status chuẩn:

- `READY_NOW`
- `WAITING_CONFIRMATION`
- `WATCH_ZONE`
- `OUT_OF_STRATEGY`
- `BLOCKED`
- `DATA_UNAVAILABLE`

`READY_NOW` chỉ nói candidate đã sẵn sàng ở snapshot scan. Nó không bỏ qua rollout guard hoặc execution revalidation.

## 7. Ranking

Ranking được tính sau khi hoàn tất filter/decision. Thứ tự sort canonical:

1. status priority;
2. `opportunity_rank`;
3. strategy confidence;
4. execution readiness;
5. expected effective R:R;
6. symbol.

`opportunity_rank` nằm trong 0–100 và dùng để so sánh cơ hội trong cùng bối cảnh hiển thị. Không có ngưỡng `opportunity_rank` nào tự động biến row thành order.

Các nguyên tắc:

- blocked/data unavailable không được leo lên trên ready chỉ vì điểm cao;
- kết quả phải deterministic;
- không rank trước filter rồi dùng rank như một gate;
- compatibility field không được trở thành nguồn quyết định mới.

## 8. Backtest/live parity

Backtest config version hiện hành:

- schema `v3`;
- validation `phase8-smc-v2-oos-v1`, schema v4;
- scorer `scanner-v3`;
- feature `scanner-features-v3`;
- metric `setup_score`.

Validation yêu cầu:

- train và OOS tách biệt;
- cỡ mẫu IS/OOS tối thiểu;
- OOS expectancy/profit factor/drawdown đạt;
- expectancy confidence interval dương;
- đủ walk-forward windows và verdict `ROBUST`;
- fingerprint toàn vẹn;
- config chưa hết hạn.

Khi scorer hoặc feature semantics đổi, version phải đổi và config cũ phải fail-closed.

## 9. Execution scoring/revalidation

Scan-time score không được dùng làm bằng chứng duy nhất tại execution. Shared execution path lấy giá mới và tính lại:

- execution-side price;
- spread và tick age;
- vị trí giá so với entry zone;
- hướng SL/TP;
- effective R:R;
- lot theo balance, risk, tick/contract data và volume step;
- news, account guard và portfolio limits.

Nếu dữ liệu cần thiết không lấy được, kết quả là block, không phải pass.

## 10. Observability

Mỗi quyết định cần truy được:

- scan/row ID;
- settings/request hash;
- scorer/feature/router/ranking version;
- side và metric đã chọn;
- branch/config status;
- threshold và giá trị thực tế;
- gate/reason/block codes;
- snapshot thời gian scan và execution;
- portfolio và rollout decision.

Reason code là contract cho UI, log, replay và kiểm thử; không chỉ là thông báo trang trí.

## 11. Các anti-pattern đã loại bỏ

- Backtest config ghi đè `stand_aside` thành `ready`.
- Có config là mặc nhiên dùng nhánh backtest.
- Vô hiệu hóa watch/wait bằng ngưỡng 999.
- So `best_score` của một side với scenario của side khác.
- Dùng `opportunity_score` 0–120 làm gate đặt lệnh.
- UI gọi MT5 order API trực tiếp.
- Dùng scan snapshot cũ để đặt lệnh mà không revalidate.
- Coi lỗi/thiếu dữ liệu là điều kiện đạt.

## 12. Nguồn code chuẩn

| Trách nhiệm | Module |
|---|---|
| Domain model/version | `core/scanner_models.py` |
| Side evaluation | `core/scanner_strategy_engine.py` |
| Strategy routing | `core/scanner_strategy_router.py` |
| Candidate decision | `core/scanner_candidate_engine.py` |
| Ranking | `core/scanner_ranking_engine.py` |
| Revalidation | `core/execution_revalidation_engine.py` |
| Portfolio risk | `core/portfolio_risk_engine.py` |
| Rollout | `core/scanner_rollout.py` |
| Observability | `core/scanner_observability.py` |
| Orchestration/execution | `controllers/scanner_controller.py` |
