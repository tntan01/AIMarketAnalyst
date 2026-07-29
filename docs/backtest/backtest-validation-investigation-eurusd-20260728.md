# Điều tra Backtest Validation EUR/USD - 2026-07-28

## Phạm vi

Tài liệu này ghi lại kết quả điều tra vì sao sau khi chạy Backtest EUR/USD dữ liệu được tự động lưu nhưng Settings vẫn chưa tick cột "Dùng BT đã duyệt" và màn hình Backtest không hiện nút "Áp dụng cấu hình".

Điều tra chỉ đọc code và snapshot đã lưu, chưa sửa logic xử lý.

## Snapshot đã kiểm tra

- File: `C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260728T190322_0700.json`
- Symbol: `EUR/USD`
- Thời điểm lưu snapshot: `2026-07-28T19:03:22+07:00`
- Mode: `system_backtest`
- Primary request purpose trong payload: `RESEARCH`
- Run policy thực tế: `VALIDATION`
- Validation replay: `INCONCLUSIVE`
- Walk-Forward: `INCONCLUSIVE`
- Lifecycle cuối: `RESEARCH_ONLY`
- Lifecycle reason: `PURPOSE_OR_EVIDENCE_NOT_RELEASE_ELIGIBLE`

## Vì sao không hiện nút áp dụng

Nút hành động trên màn hình Backtest được quyết định bởi `result_action()` trong `core/backtest_presentation.py`.

Điều kiện hiện nút:

- `lifecycle.status` là `DRAFT`: hiện nút "Lưu đề xuất nháp".
- `lifecycle.status` là `VALIDATED` hoặc `RELEASE_READY`, hoặc `can_publish_config=True`: hiện nút "Áp dụng cấu hình".
- Các trạng thái khác, ví dụ `RESEARCH_ONLY`: không hiện nút.

Snapshot EUR/USD hiện có:

```text
lifecycle.status = RESEARCH_ONLY
result_action.kind = NONE
result_action.visible = False
result_action.reason = LIFECYCLE_RESEARCH_ONLY_NOT_ACTIONABLE
```

Vì vậy UI ẩn nút là đúng theo logic hiện tại.

## Vì sao Settings chưa tick "Dùng BT đã duyệt"

Settings chỉ tick checkbox khi cả hai điều kiện đúng:

```text
symbol_config.backtest == True
backtest_activation_status(symbol_config) == VALIDATED
```

Trạng thái Settings hiện tại của `EUR/USD`:

```text
backtest = False
backtest_status = DRAFT
backtest_config_id = rỗng
backtest_validated_at = rỗng
backtest_expires_at = rỗng
```

Kết luận: chưa có config Backtest đã duyệt được ghi vào Settings. Snapshot Backtest tự lưu chỉ là file kết quả, không tự đồng nghĩa với config đã được apply/validated.

## Nguyên nhân sâu

Validation replay cần tạo được `frozen_strategy_config` từ In-Sample Candidate Ledger. Hàm chọn config là `optimize_frozen_strategy()` trong `core/backtest_candidate_ledger.py`.

Optimizer yêu cầu tối thiểu 8 candidate hợp lệ thỏa các điều kiện chính:

```text
symbol == EUR/USD
base_eligible == True
research_only != True
setup_score != None
simulated_trade là object
expected_effective_rr != None
```

Nhưng snapshot EUR/USD hiện tại có:

```text
validation_replay.is_candidate_ledger = 4204 candidate
base_eligible=True = 0
simulated_trade đủ điều kiện optimizer = 0
```

Vì không có candidate hợp lệ, optimizer trả `None`, dẫn đến:

```text
validation_replay.status = INCONCLUSIVE
validation_replay.reason = IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
frozen_strategy_config = None
```

## Phân tích Candidate Ledger

Trong `validation_replay.is_candidate_ledger`:

```text
Tổng candidate: 4204
TRADE_SIMULATION_REJECTED: 3471
blocked_by_trade_gate: 623
no_trade_scenario: 67
blocked_by_permission: 43
base_eligible=True: 0
```

Nhóm `expected_effective_rr`:

```text
expected_effective_rr rỗng: 2669
expected_effective_rr có giá trị: 1535
```

Trong nhóm `expected_effective_rr` rỗng:

```text
TRADE_SIMULATION_REJECTED: 2124
blocked_by_trade_gate: 478
no_trade_scenario/khác: 67
có simulated_trade: 466
```

Các dòng rỗng RR nhưng vẫn có `simulated_trade` chủ yếu có pattern:

```text
decision = WATCH_ONLY
entry_status = watch_zone
m15_quality = None
entry_zone_source = smc_distant hoặc fallback
base_rejection_reason = blocked_by_trade_gate
```

Các dòng có RR hợp lệ và có `simulated_trade` chủ yếu đi với:

```text
entry_zone_source = smc_v2_selected
decision = WAITING_CONFIRMATION hoặc WATCH_ONLY
entry_status = confirmed_entry / waiting_confirmation / watch_zone
```

Kết luận: RR rỗng tập trung ở các setup dạng theo dõi, vùng xa, hoặc fallback; nhóm `smc_v2_selected` có chất lượng tốt hơn nhưng vẫn chưa đủ điều kiện strict validation.

## Điều tra `TRADE_SIMULATION_REJECTED`

Trong validation ledger, `TRADE_SIMULATION_REJECTED` là reason tổng quát. Snapshot hiện chưa lưu reason chi tiết tại sao `simulate_trade_from_analysis()` trả `None`.

Theo code trong `core/system_backtest_engine.py`, mô phỏng có thể trả `None` vì:

```text
side không phải buy/sell
scenario là research_only/fallback/synthetic trong validation
thiếu stop_loss hoặc take_profit hợp lệ
entry_zone không hợp lệ
không tìm được confirmation-close fill trên M15 trong setup_expiry
geometry entry/SL/TP sai sau khi tính cost/spread
thiếu quote conversion tại entry/exit
```

Top-level replay cùng snapshot có `skipped_setups` cho thêm dấu hiệu:

```text
skipped_setups: 4950
invalid_trade_plan: 4841
no_trade_scenario: 76
not_actionable: 33
```

Message chi tiết trong `skipped_setups`:

```text
Giá M15 chưa chạm entry zone trong thời hạn setup: 3834
Thiếu SL/TP hợp lệ: 1007
Không có scenario buy/sell hợp lệ: 76
Gate hoặc trade_permission chặn giao dịch: 18
Entry status chưa đạt yêu cầu: 14
Decision chưa đạt ngưỡng mở lệnh: 1
```

Phân bổ theo nguồn zone:

```text
smc_distant + M15 chưa chạm entry zone: 2022
smc_v2_selected + M15 chưa chạm entry zone: 1806
smc_distant + thiếu SL/TP hợp lệ: 545
smc_v2_selected + thiếu SL/TP hợp lệ: 462
fallback + M15 chưa chạm entry zone: 6
```

Lưu ý: `skipped_setups` là top-level primary replay, không phải chi tiết từng dòng validation ledger. Tuy nhiên nó cho thấy pattern rất mạnh: phần lớn reject liên quan đến entry không được fill trong hạn setup và một phần đáng kể thiếu SL/TP hợp lệ.

## Kết luận điều tra

Backtest dài 2.5 năm không tự tạo config vì hệ thống đang thiếu candidate "sạch" để phát hành.

Vấn đề chính không phải số lượng dữ liệu, mà là chất lượng candidate trong validation:

```text
base_eligible=True = 0
frozen_strategy_config = None
validation_replay = INCONCLUSIVE
lifecycle = RESEARCH_ONLY
```

Hai nút nghẽn chính:

1. Nhiều setup không fill được entry zone trên M15 trong `setup_expiry`.
2. Một phần scenario thiếu SL/TP hợp lệ.

Ngoài ra, snapshot có DataManifest warning:

```text
quality_status = WARNING
validation_eligible = False
```

Các warning chính:

```text
DATA_COVERAGE_END_MISSING
UNEXPECTED_DATA_GAP
```

Điều này cũng ngăn snapshot trở thành bằng chứng validation sạch.

## Đề xuất từng bước thực hiện

### Bước 1 - Bổ sung diagnostics trước khi sửa logic

Thêm reason chi tiết vào Candidate Ledger khi `simulate_trade_from_analysis()` trả `None`.

Đề xuất các reason:

```text
INVALID_SIDE
VALIDATION_RESEARCH_ONLY_SCENARIO
MISSING_SL_TP
INVALID_ENTRY_ZONE
ENTRY_ZONE_NOT_TOUCHED
INVALID_TRADE_GEOMETRY
QUOTE_CONVERSION_MISSING
```

Mục tiêu: thay vì chỉ có `TRADE_SIMULATION_REJECTED`, snapshot sau sẽ biết chính xác rớt vì lý do nào.

### Bước 2 - Chạy lại EUR/USD ở chế độ Kiểm chứng

Sau khi có diagnostics, chạy lại EUR/USD với end date lùi 2-3 ngày giao dịch để tránh thiếu nến cuối.

Kết quả cần đọc:

```text
TRADE_SIMULATION_REJECTED theo từng reason
số candidate smc_v2_selected
số candidate có expected_effective_rr
số candidate có simulated_trade
số candidate base_eligible=True
```

### Bước 3 - Nếu reason chính là ENTRY_ZONE_NOT_TOUCHED

Kiểm tra lại rule fill:

```text
execution timeframe = M15
fill model = confirmation_close
setup_expiry_minutes = 180
```

Nếu chiến lược thực tế cho phép chờ entry zone lâu hơn, cân nhắc điều chỉnh `setup_expiry_minutes` hoặc rule fill cho đúng chiến lược.

Nếu chiến lược chỉ cho phép chờ ngắn, giữ nguyên. Khi đó các setup không chạm zone trong hạn là reject đúng.

### Bước 4 - Nếu reason chính là MISSING_SL_TP

Sửa phần tạo scenario/TP cho nhóm `smc_v2_selected`.

Nguyên tắc:

```text
smc_v2_selected có entry zone tốt thì phải có SL/TP hợp lệ
fallback và smc_distant không nên dùng để phát hành config
```

Không nên biến fallback/distant thành candidate validation nếu bản chất chỉ là vùng theo dõi.

### Bước 5 - Tách rõ research trade và validation candidate

Research backtest có thể tiếp tục mô phỏng rộng:

```text
WATCH_ONLY
WAITING_CONFIRMATION
fallback
smc_distant
```

Validation/frozen config chỉ nên xét candidate thật sự actionable:

```text
entry_zone_source = smc_v2_selected
decision = READY_TO_TRADE
entry_status = confirmed_entry
m15_quality = strict
expected_effective_rr != None
simulated_trade != None
research_only != True
```

### Bước 6 - Kiểm tra lại optimizer

Sau các bước trên, kiểm tra optimizer có đủ tối thiểu 8 candidate hợp lệ không.

Điều kiện cần:

```text
base_eligible >= 8
frozen_strategy_config != None
validation_replay.status = COMPLETE
```

### Bước 7 - Kiểm tra Walk-Forward và lifecycle

Khi validation replay đã complete, Walk-Forward mới có dữ liệu để đánh giá robustness.

Kết quả mong muốn:

```text
walk_forward.verdict = ROBUST hoặc ít nhất không INCONCLUSIVE do thiếu frozen config
lifecycle.status = DRAFT hoặc VALIDATED/RELEASE_READY tùy rule release
nút "Lưu đề xuất nháp" hoặc "Áp dụng cấu hình" hiện trên UI
```

### Bước 8 - Apply vào Settings khi đủ điều kiện

Sau khi có nút hành động:

```text
Click "Lưu đề xuất nháp" nếu lifecycle = DRAFT
Click "Áp dụng cấu hình" nếu lifecycle = VALIDATED/RELEASE_READY
```

Settings chỉ tick "Dùng BT đã duyệt" khi config thật sự VALIDATED.

## Kết quả cuối cùng mong muốn

Sau khi thực hiện đúng chuỗi sửa và chạy lại:

```text
EUR/USD có frozen_strategy_config
validation_replay.status = COMPLETE
base_eligible >= 8
walk_forward có kết quả đánh giá rõ ràng
Backtest UI hiện nút hành động
Settings có backtest_config_id sau khi lưu/apply
"Dùng BT đã duyệt" chỉ tick nếu validation thật sự đạt VALIDATED
```

Ví dụ config cuối có thể có dạng:

```text
symbol = EUR/USD
regime = trend_up hoặc trend_down
side = buy hoặc sell
min_score = 50/55/60/65
min_rr = 1.0/1.3/1.5/2.0
status = DRAFT hoặc VALIDATED
```

## Rủi ro cần tránh

Không nên sửa bằng cách:

```text
ép tick Settings thủ công
giảm MIN_LEDGER_CANDIDATES ngay lập tức
nới toàn bộ trade gate live
cho fallback/smc_distant trở thành config validation
bỏ qua DataManifest WARNING
```

Các cách trên có thể làm UI hiện "đã duyệt" nhưng không tạo ra bằng chứng backtest đáng tin cậy.

## Cập nhật 2026-07-29 - Kết quả Giai đoạn 2 và 3A

### Giai đoạn 2 đã chạy xong

Snapshot mới sau khi bổ sung `simulation_rejection_reason`:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260728T233227_0700.json
```

Trong `validation_replay.is_candidate_ledger`:

```text
total candidate: 2378
base_eligible=True: 0
simulated_trade: 351
TRADE_SIMULATION_REJECTED: 1979
ENTRY_ZONE_NOT_TOUCHED: 1608
MISSING_SL_TP: 367
INVALID_TRADE_GEOMETRY: 4
```

Kết luận route: `ENTRY_ZONE_NOT_TOUCHED` là reason lớn nhất, nên chuyển sang Giai đoạn 3A.

### Giai đoạn 3A - kiểm tra setup expiry/fill rule

Rule hiện tại đã xác nhận trong code:

```text
execution_timeframe = M15
fill_model = confirmation_close
setup_expiry_minutes = 180
```

Đã chạy probe cục bộ trên cửa sổ `2025-01-01` đến `2025-01-15` với cùng engine và dữ liệu MT5, so sánh `setup_expiry_minutes = 180` và `720`.

Kết quả:

```text
expiry 180:
candidate_rows = 90
trades = 7
simulated_trade_rows = 7
base_eligible = 0
ENTRY_ZONE_NOT_TOUCHED = 58
MISSING_SL_TP = 25

expiry 720:
candidate_rows = 90
trades = 7
simulated_trade_rows = 7
base_eligible = 0
ENTRY_ZONE_NOT_TOUCHED = 58
MISSING_SL_TP = 25
```

Nới thời gian chờ entry từ 3 giờ lên 12 giờ không tạo thêm fill trong cửa sổ mẫu. Vì vậy không có bằng chứng kỹ thuật đủ mạnh để đổi default `setup_expiry_minutes` ở Giai đoạn 3A.

Quyết định Giai đoạn 3A:

```text
Giữ nguyên M15 confirmation_close.
Giữ nguyên setup_expiry_minutes = 180.
Chấp nhận ENTRY_ZONE_NOT_TOUCHED là reject đúng với rule hiện tại.
Không sửa logic fill/expiry trong giai đoạn này.
```

Giai đoạn tiếp theo nên là Giai đoạn 3B: điều tra `MISSING_SL_TP`, ưu tiên nhóm `entry_zone_source = smc_v2_selected`.

### Giai đoạn 3B - kiểm tra MISSING_SL_TP

Trong snapshot Phase 2, `skipped_setups` có `570` dòng báo `Thiếu SL/TP hợp lệ.`

Cross-tab theo `entry_zone_source` cho thấy nhóm liên quan `smc_v2_selected` là:

```text
smc_v2_selected + WATCH_ONLY + strict: 115
smc_v2_selected + WATCH_ONLY + loose: 102
smc_v2_selected + WATCH_ONLY + none: 24
```

Tất cả `241` dòng `smc_v2_selected` này đều có:

```text
decision = WATCH_ONLY
ready_to_trade = False
expected_effective_rr = None
risk_reward = None
trade_permission = caution
gate_allowed = True
```

Gate reason điển hình:

```text
Chưa có điểm vào — không tính được R:R kỳ vọng.
```

Kiểm tra code cho thấy `risk_engine.build_trade_plan()` cho phép SMC preferred/selected zone trả plan dạng watch khi không tìm được TP1 hợp lệ. Đây là contract hiện có và đã có test bảo vệ: không ép TP fallback khi chưa có target sạch.

Quyết định Giai đoạn 3B:

```text
Không tạo TP giả cho smc_v2_selected.
Không nâng cấp watch-zone thành validation candidate.
Tách diagnostics: take_profit rỗng/không hợp lệ được ghi là NO_VALID_TP1 thay vì MISSING_SL_TP.
Candidate ledger lưu thêm entry_zone_source, m15_quality, entry_status, decision, tp1_source.
skipped_setups.debug lưu thêm entry_zone, stop_loss, take_profit, tp1_source, invalid_reason.
```

Probe ngắn trên dữ liệu thật `2025-01-01` đến `2025-01-05` xác nhận classification mới:

```text
trades = 1
ledger rows = 30
NO_VALID_TP1 = 17
ENTRY_ZONE_NOT_TOUCHED = 12
MISSING_SL_TP = 0
```

Kết luận: Phase 3B đã xử lý nhầm lẫn diagnostics. Các setup này vẫn bị reject đúng vì không có TP1 hợp lệ/actionable RR, không phải vì thiếu stop_loss hoặc lỗi mất plan.

Giai đoạn tiếp theo nên là Giai đoạn 3C nếu muốn kiểm tra nốt `INVALID_TRADE_GEOMETRY`; nếu bỏ qua do số lượng rất nhỏ, có thể chuyển sang Giai đoạn 4 để siết candidate phát hành config.

### Giai đoạn 3C - kiểm tra geometry và quote conversion

Trong snapshot Phase 2:

```text
top-level candidate_ledger:
INVALID_TRADE_GEOMETRY = 7
QUOTE_CONVERSION_MISSING = 0

validation_replay.is_candidate_ledger:
INVALID_TRADE_GEOMETRY = 4
QUOTE_CONVERSION_MISSING = 0
```

Nhóm validation IS chỉ có `4` dòng geometry, tất cả đều là `buy`, `market_regime = trend_up`. Tỉ trọng quá nhỏ so với `ENTRY_ZONE_NOT_TOUCHED` và `NO_VALID_TP1`, nên đây không phải bottleneck chính.

Thay đổi Phase 3C:

```text
Không ép pass geometry sai.
Không ép quote conversion fallback nếu thiếu dữ liệu.
Giữ reject như cũ.
Thêm simulation_rejection_detail vào candidate ledger.
```

Với `INVALID_TRADE_GEOMETRY`, detail mới lưu:

```text
side
raw_fill_price
execution_entry_price
stop_loss
take_profit
entry_spread
entry_slippage
parity_enabled
filled_at
```

Với `QUOTE_CONVERSION_MISSING`, detail mới lưu:

```text
quote_conversion_symbol
quote_conversion_inverted
entry_time
exit_time
quote_rate_entry_present
quote_rate_exit_present
```

Probe nhỏ xác nhận geometry detail:

```text
reason = INVALID_TRADE_GEOMETRY
detail.execution_entry_price = 1.22
detail.stop_loss = 1.0
detail.take_profit = 1.2
```

Kết luận: Phase 3C đã hoàn tất phần diagnostics. Geometry/quote conversion không phải nút nghẽn chính của EUR/USD snapshot này.

Giai đoạn tiếp theo nên là Giai đoạn 4: siết candidate phát hành config, đảm bảo optimizer chỉ xét candidate sạch/actionable và không dùng `fallback`, `smc_distant`, hoặc watch-zone/no-TP1.

### Giai đoạn 4 - siết candidate phát hành config

Optimizer trước đây đã yêu cầu các điều kiện cơ bản:

```text
symbol đúng
base_eligible = True
research_only != True
setup_score != None
simulated_trade là object
expected_effective_rr đạt ngưỡng trong từng bucket
```

Giai đoạn 4 bổ sung lớp `release_candidate_rejection_reasons()` để tách rõ candidate nào được phép dùng cho frozen config.

Candidate release sạch hiện cần:

```text
base_eligible = True
research_only != True
setup_score != None
simulated_trade là object
expected_effective_rr != None
scenario_source không phải fallback/synthetic_fallback
entry_zone_source thuộc smc / smc_selected / smc_v2_selected
entry_status = confirmed_entry
decision = READY_TO_TRADE
tp1_source có giá trị và khác none
```

Các reason loại mới:

```text
RELEASE_RESEARCH_ONLY_CANDIDATE
RELEASE_SETUP_SCORE_MISSING
RELEASE_SIMULATED_TRADE_MISSING
RELEASE_EXPECTED_RR_MISSING
RELEASE_SCENARIO_SOURCE_NOT_CLEAN
RELEASE_ENTRY_ZONE_SOURCE_NOT_CLEAN
RELEASE_ENTRY_STATUS_NOT_CONFIRMED
RELEASE_DECISION_NOT_READY
RELEASE_TP1_MISSING
```

Quyết định Phase 4:

```text
Optimizer chỉ dùng candidate không có release rejection.
OOS replay với frozen config cũng giải thích release rejection trong strategy_rejection_reasons.
Research run không có frozen config vẫn giữ behavior cũ để không làm méo màn hình nghiên cứu.
MIN_LEDGER_CANDIDATES vẫn giữ 8, không hạ ngưỡng.
```

Test đã thêm/xác nhận:

```text
optimizer bỏ qua fallback
optimizer bỏ qua smc_distant
optimizer bỏ qua watch_zone
optimizer bỏ qua tp1_source = none
release helper giải thích từng reason
```

Kết quả test Phase 4:

```text
tests/test_backtest_candidate_replay.py: 12 passed
tests/test_walk_forward.py + tests/test_backtest_phase5_validation.py: 12 passed
candidate replay + validation + diagnostics group: 64 passed
tests/test_backtest_config_validation.py: 16 passed
```

Giai đoạn tiếp theo nên là Giai đoạn 5: chạy lại EUR/USD ở chế độ kiểm chứng và đọc xem còn đủ `base_eligible >= 8`, có `frozen_strategy_config`, và `validation_replay.status = COMPLETE` hay chưa.

### Giai đoạn 5 - validation lại EUR/USD sau Phase 1-4

Đã chạy lại EUR/USD ở chế độ kiểm chứng/parity với khoảng:

```text
symbol = EUR/USD
start = 2025-01-01T00:00:00Z
end = 2026-06-01T00:00:00Z
purpose = VALIDATION
execution_mode = EXECUTION_PARITY
run_validation_replay = true
run_walk_forward = true
```

Snapshot mới:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260729T101538_0700.json
timestamp = 2026-07-29T10:15:38+07:00
```

Kết quả Phase 5:

```text
top_candidate_rows = 3255
top_base_eligible = 0
frozen_strategy_config = null
lifecycle.status = RESEARCH_ONLY
lifecycle.reasons = PURPOSE_OR_EVIDENCE_NOT_RELEASE_ELIGIBLE

validation_replay.status = INCONCLUSIVE
validation_replay.reason = IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
validation_replay.is_candidate_ledger rows = 2378
validation_replay base_eligible = 0
validation_replay release_clean = 0

walk_forward.verdict = INCONCLUSIVE
walk_forward.window_count = 3
walk_forward.successful_window_count = 0
walk_forward.aggregate_oos = null
```

Simulation rejection trong snapshot mới:

```text
Top ledger:
ENTRY_ZONE_NOT_TOUCHED = 2126
NO_VALID_TP1 = 570
<empty> = 552
INVALID_TRADE_GEOMETRY = 7

Validation IS ledger:
ENTRY_ZONE_NOT_TOUCHED = 1608
<empty> = 399
NO_VALID_TP1 = 367
INVALID_TRADE_GEOMETRY = 4
```

Release filter cho thấy không có candidate nào đủ sạch để optimizer sinh frozen config:

```text
Top ledger release clean = 0
Validation IS release clean = 0

Validation IS release rejection lớn nhất:
RELEASE_DECISION_NOT_READY = 2378
RELEASE_ENTRY_STATUS_NOT_CONFIRMED = 2376
RELEASE_SIMULATED_TRADE_MISSING = 2027
TRADE_SIMULATION_REJECTED = 1979
RELEASE_TP1_MISSING = 1433
RELEASE_EXPECTED_RR_MISSING = 1431
RELEASE_ENTRY_ZONE_SOURCE_NOT_CLEAN = 1265
```

Metadata phân bố trong Validation IS ledger:

```text
decision:
WATCH_ONLY = 1905
WAITING_CONFIRMATION = 467
TRADE_BLOCKED = 5
STAND_ASIDE = 1

entry_status:
watch_zone = 2295
waiting_confirmation = 39
confirmed_entry = 2
invalidated = 1
<empty> = 41

entry_zone_source:
smc_distant = 1187
smc_v2_selected = 1113
fallback = 37
<empty> = 41
```

Kết luận Phase 5:

```text
Phase 5 đã chạy xong.
Nhưng validation chưa COMPLETE.
Optimizer không thể sinh frozen_strategy_config vì base_eligible/release_clean vẫn bằng 0.
Nút nghẽn lớn nhất hiện không còn là thiếu diagnostics, mà là trade gate không phát hành candidate actionable:
- decision không có READY_TO_TRADE
- entry_status gần như toàn watch_zone/waiting_confirmation
- chỉ có 2 confirmed_entry trong IS, và vẫn không release-clean
```

Giai đoạn tiếp theo nên là Giai đoạn 6A: điều tra trade gate/entry confirmation pipeline để tìm vì sao EUR/USD validation không sinh `READY_TO_TRADE` + `confirmed_entry` candidate, trước khi quay lại UI/Settings release flow.

### Giai đoạn 6A - điều tra trade gate / entry confirmation pipeline

Kết quả điều tra:

```text
Main snapshot request.purpose = RESEARCH
run_policy.purpose = VALIDATION
top-level trades = 490
```

Điều này giải thích vì sao top-level vẫn có trade, nhưng validation replay không sinh được frozen config. Phần quyết định release thật nằm ở:

```text
validation_replay.is_candidate_ledger
```

Trong IS ledger của snapshot Phase 5:

```text
rows = 2378
simulated_trade rows = 351
base_eligible = 0
release_clean trước Phase 6A = 0

simulated rows:
base_rejection_reason:
  blocked_by_trade_gate = 321
  blocked_by_permission = 30

decision:
  WATCH_ONLY = 283
  WAITING_CONFIRMATION = 68

entry_status:
  watch_zone = 331
  waiting_confirmation = 19
  confirmed_entry = 1
```

Nguyên nhân:

```text
Phase 4 release filter dùng scan-time readiness:
decision = READY_TO_TRADE
entry_status = confirmed_entry

Nhưng validation/backtest execution model là confirmation-close fill:
scanner có thể thấy setup là watch_zone / waiting_confirmation tại decision_time,
sau đó M15 confirmation-close fill mới xác nhận entry thật.
```

Vì vậy `decision` và `entry_status` trong ledger là trạng thái tại thời điểm scan, không phải bằng chứng fill cuối cùng. Với validation replay, `simulated_trade` mới là bằng chứng entry đã được execution model xác nhận.

Fix Phase 6A:

```text
release_candidate_rejection_reasons() hỗ trợ 2 đường release sạch:

1. scan-ready:
   base_eligible = True
   decision = READY_TO_TRADE
   entry_status = confirmed_entry

2. simulated-fill-ready:
   simulated_trade là object
   base_rejection_reason thuộc nhóm soft scan-time blocker:
     blocked_by_trade_gate
     blocked_by_permission
     blocked_by_decision
     blocked_by_entry_status
   scenario/zone/TP/RR vẫn phải sạch
```

Các điều kiện vẫn giữ chặt:

```text
research_only != True
setup_score != None
simulated_trade != None
expected_effective_rr != None
scenario_source không phải fallback/synthetic_fallback
entry_zone_source thuộc smc / smc_selected / smc_v2_selected
tp1_source có giá trị và khác none
```

Không nới:

```text
fallback vẫn bị reject
smc_distant vẫn bị reject
candidate không có simulated_trade vẫn bị reject
candidate không có TP1/RR vẫn bị reject
hard simulation reject vẫn bị reject
```

Probe lại snapshot Phase 5 bằng code mới:

```text
validation IS release_clean = 115

release clean distribution:
side:
  buy = 94
  sell = 21

market_regime:
  trend_up = 95
  trend_down = 20

optimizer output:
config_id = EURUSD-frozen-883f843b5fdd
symbol = EUR/USD
side = sell
allowed_regimes = trend_down
min_setup_score = 50
min_expected_rr = 2.0
selected IS candidates = 12
IS expectancy ~= 0.203R
IS profit_factor ~= 1.47
```

Test Phase 6A:

```text
python -m py_compile core/backtest_candidate_ledger.py
python -m pytest tests/test_backtest_candidate_replay.py -q
  13 passed
python -m pytest tests/test_backtest_candidate_replay.py tests/test_backtest_phase5_validation.py tests/test_walk_forward.py tests/test_backtest_simulation_diagnostics.py -q
  39 passed
```

Kết luận Phase 6A:

```text
Phase 6A đã finish.
Root cause là release filter Phase 4 dùng readiness tại scan-time cho một backtest model vốn xác nhận entry bằng simulated fill sau đó.
Fix đã chuyển optimizer sang chấp nhận simulated-fill-ready candidate, nhưng vẫn giữ filter sạch về source/TP/RR/fallback.
```

Giai đoạn tiếp theo nên là Giai đoạn 6B: chạy lại full EUR/USD validation/walk-forward sau fix Phase 6A để xác nhận `validation_replay.status = COMPLETE`, OOS replay có trade, và walk-forward có `successful_window_count > 0`.

### Giai đoạn 6B - chạy lại full validation/walk-forward sau fix Phase 6A

Phase 6B đã chạy full EUR/USD validation/walk-forward bằng broker symbol thực tế `EURUSDc`.

Snapshot mới:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260729T114048_0700.json
```

Thông tin run:

```text
timestamp = 2026-07-29T11:40:48+07:00
run_policy.purpose = VALIDATION
run_policy.execution_mode = EXECUTION_PARITY
request.purpose = RESEARCH
request.execution_mode = EXECUTION_PARITY
lifecycle.status = RESEARCH_ONLY
lifecycle.reasons = ["PURPOSE_OR_EVIDENCE_NOT_RELEASE_ELIGIBLE"]
```

Kết quả top-level candidate ledger:

```text
rows = 3260
base_eligible = 0
release_clean = 148

simulation_rejection_reason:
- ENTRY_ZONE_NOT_TOUCHED = 2146
- NO_VALID_TP1 = 554
- <empty> = 553
- INVALID_TRADE_GEOMETRY = 7
```

Kết quả validation replay:

```text
validation_replay.status = INCONCLUSIVE
validation_replay.reason = IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
frozen_strategy_config = null
probe_config_from_is = null

IS rows = 2387
IS base_eligible = 0
IS release_clean = 116
OOS rows = 0
OOS release_clean = 0
```

Kết quả walk-forward:

```text
walk_forward.verdict = INCONCLUSIVE
window_count = 3
successful_window_count = 0
aggregate_is = null
aggregate_oos = null

window errors:
- wf-001: IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
- wf-002: IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
- wf-003: IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
```

Điểm mới so với Phase 5/6A:

```text
Release filter không còn là blocker chính.
Phase 6B tạo được 116 IS release-clean candidates, nhưng optimizer vẫn không phát frozen config vì nhóm clean có edge âm/không đạt ngưỡng.
```

Kiểm tra trực tiếp 116 IS release-clean candidates:

```text
all clean:
- n = 116
- wins = 44
- losses = 72
- total_r = -12.2708R
- expectancy = -0.1058R
- profit_factor = 0.8067

buy + trend_up:
- n = 96
- wins = 37
- losses = 59
- total_r = -7.3134R
- expectancy = -0.0762R
- profit_factor = 0.8584
- best threshold thử được: score >= 55, RR >= 1.0/1.3/1.5
  n = 40, total_r = +1.8618R, expectancy = +0.0465R, PF = 1.0869
  vẫn dưới optimizer gate expectancy >= 0.10 và PF >= 1.20

sell + trend_down:
- n = 19
- wins = 7
- losses = 12
- total_r = -3.9574R
- expectancy = -0.2083R
- profit_factor = 0.6342
- best threshold thử được: score >= 50, RR >= 2.0
  n = 10, total_r = -0.0496R, expectancy = -0.0050R, PF = 0.9901
```

Kết luận Phase 6B:

```text
Phase 6B đã finish về mặt chạy full runner/snapshot.
Phase 6B chưa finish mục tiêu validation pass.
Lý do: đã có release-clean candidates nhưng IS expectancy/profit-factor không đạt ngưỡng optimizer, nên không thể tạo frozen_strategy_config; vì không có config nên OOS replay và walk-forward vẫn INCONCLUSIVE.
```

Giai đoạn tiếp theo nên là Giai đoạn 6C: điều tra chất lượng edge của 116 release-clean candidates, ưu tiên phân tích vì sao setup `smc_v2_selected` có simulated fill nhưng expectancy âm; không nên hạ ngưỡng optimizer trước khi biết edge âm đến từ model entry/exit, scoring threshold, TP1 quality, cost/fill rule, hay market-regime split.

### Giai đoạn 6C - điều tra quality edge của release-clean candidates

Phase 6C phân tích 116 IS release-clean candidates từ snapshot Phase 6B:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260729T114048_0700.json
```

Kết quả tổng:

```text
release_clean trước Phase 6C = 116
wins = 44
losses = 72
total_r = -12.2708R
expectancy = -0.1058R
profit_factor = 0.8067
```

Bucket quan trọng nhất là M15 quality:

```text
m15_quality = strict:
- n = 37
- wins = 20
- losses = 17
- total_r = +7.8631R
- expectancy = +0.2125R
- profit_factor = 1.5084

m15_quality = loose:
- n = 60
- wins = 20
- losses = 40
- total_r = -10.5331R
- expectancy = -0.1756R
- profit_factor = 0.7034

m15_quality = none / M15_NOT_CONFIRMED:
- n = 19
- wins = 4
- losses = 15
- total_r = -9.6008R
- expectancy = -0.5053R
- profit_factor = 0.2315
```

Các bucket khác có tín hiệu yếu hơn hoặc không giải thích tốt bằng M15 quality:

```text
session:
- LONDON: n = 30, expectancy = +0.1899R, PF = 1.5213
- OVERLAP: n = 25, expectancy = -0.3434R, PF = 0.4751
- ASIA: n = 22, expectancy = -0.1678R, PF = 0.7334

tp1_source:
- target_zone: n = 88, expectancy = -0.0557R, PF = 0.8930
- equal_level: n = 16, expectancy = -0.1915R, PF = 0.6995
- fib_extension: n = 6, expectancy = -0.6078R, PF = 0.1443

setup_score:
- 50-54: n = 65, expectancy = -0.1672R, PF = 0.6915
- 55-59: n = 41, expectancy = +0.0135R, PF = 1.0260
- 60-64: n = 10, expectancy = -0.1954R, PF = 0.7208
```

Probe optimizer nếu chỉ cho `m15_quality = strict`:

```text
release_clean sau Phase 6C filter = 37
strict metrics:
- total_r = +7.8631R
- expectancy = +0.2125R
- profit_factor = 1.5084

optimizer output:
config_id = EURUSD-frozen-9966e2dd9446
symbol = EUR/USD
side = buy
allowed_regimes = ["trend_up"]
min_setup_score = 55
min_expected_rr = 1.5
```

Root cause Phase 6C:

```text
Phase 6A đã mở simulated-fill-ready quá rộng.
Nó đúng khi không bắt buộc READY_TO_TRADE/confirmed_entry tại scan-time, nhưng còn thiếu gate M15 strict.
Do đó release filter đã cho loose/not-confirmed M15 candidates seed optimizer; nhóm này có edge âm mạnh và kéo toàn bộ IS set xuống dưới ngưỡng.
```

Fix Phase 6C:

```text
core/backtest_candidate_ledger.py
- thêm RELEASE_M15_QUALITY = "strict"
- release_candidate_rejection_reasons() thêm reason RELEASE_M15_QUALITY_NOT_STRICT
- release candidate chỉ được seed frozen config khi M15 quality strict
- vẫn giữ simulated-fill-ready path cho scan-time WATCH/WAITING_CONFIRMATION nếu sau đó fill được xác nhận bằng backtest execution model
```

Tests Phase 6C:

```text
tests/test_backtest_candidate_replay.py
- test release candidate reject loose/missing M15 quality
- test simulated-fill-ready pending scan state chỉ pass khi M15 strict
- test optimizer bỏ qua loose M15 rows

tests/test_backtest_phase5_validation.py
- cập nhật fixture walk-forward release-clean giả lập với m15_quality = strict
```

Đã chạy:

```text
python -m pytest tests/test_backtest_candidate_replay.py -q
  14 passed

python -m pytest tests/test_backtest_candidate_replay.py tests/test_backtest_phase5_validation.py tests/test_walk_forward.py tests/test_backtest_simulation_diagnostics.py -q
  40 passed
```

Kết luận Phase 6C:

```text
Phase 6C đã finish.
Root cause là release filter thiếu M15 strict gate.
Fix đã siết release eligibility theo M15 quality và probe trên snapshot Phase 6B cho thấy optimizer sẽ tạo được frozen config từ nhóm strict-only.
```

Giai đoạn tiếp theo nên là Giai đoạn 6D: chạy lại full EUR/USD validation/walk-forward sau fix Phase 6C để xác nhận snapshot mới có `frozen_strategy_config != null`, `validation_replay.status = COMPLETE`, OOS replay có trade, và walk-forward có `successful_window_count > 0`.

### Giai đoạn 6D - chạy lại full validation/walk-forward sau fix Phase 6C

Snapshot mới:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260729T151508_0700.json
```

Kết quả:

```text
validation_replay.status = INCONCLUSIVE
validation_replay.reason = IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
frozen_strategy_config = null
is_rows = 2378
oos_trades = 0

walk_forward.verdict = INCONCLUSIVE
window_count = 3
successful_window_count = 1
```

Tổng snapshot:

```text
total_trades = 490
total_r = -42.3945R
expectancy = -0.0865R
profit_factor = 0.7952
```

Kết luận Phase 6D:

```text
Phase 6D đã finish về mặt chạy full runner/snapshot.
Nhưng mục tiêu validation pass chưa đạt.
EUR/USD vẫn không tạo được frozen_strategy_config vì IS candidate ledger còn không tối ưu được.
Walk-forward chỉ có 1/3 cửa sổ thành công, nên vẫn INCONCLUSIVE.
```

## Hướng xử lý tiếp theo sau Phase 6D

Chưa chạy lại full validation ngay và chưa chuyển sang Giai đoạn 7 - Chốt.

Lý do: probe ở Phase 6C cho thấy nhóm `m15_quality = strict` có thể tạo
`frozen_strategy_config`, nhưng runner thật ở Phase 6D vẫn trả
`IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE`. Cần giải thích sai lệch này trước khi
thay đổi thêm threshold hoặc release gate.

### Phase 7A - Candidate parity audit

Mục tiêu:

```text
Xác nhận probe Phase 6C và runner Phase 6D đưa đúng cùng một tập candidate vào optimizer.
Giải thích được vì sao probe dự báo optimizable nhưng runner thật không tạo được frozen config.
```

Thực hiện:

1. Xuất chính xác candidate IDs được đưa vào optimizer ở runner Phase 6D.
2. So sánh với tập candidate mà probe Phase 6C đã sử dụng.
3. So sánh toàn bộ điều kiện chọn candidate:

```text
entry_zone_source = smc_v2_selected
m15_quality = strict
expected_effective_rr != None
simulated_trade != None
research_only != True
base_eligible / simulated-fill-ready
setup_score
side
market_regime
```

4. Thống kê số lượng và lý do bị loại tại từng gate.
5. Tính lại expectancy, profit factor và số trade trên đúng tập candidate được
   truyền vào optimizer.
6. Thêm regression test để probe và runner dùng cùng một candidate selector.

Phase 7A finish khi:

```text
candidate set của probe và runner khớp hoàn toàn;
hoặc đã xác định được và sửa được nguyên nhân làm hai tập candidate khác nhau;
kết quả optimizer có thể tái lập bằng cùng một input.
```

Kết quả thực hiện Phase 7A - 2026-07-29:

```text
Code/diagnostic đã thêm:
- core/backtest_candidate_ledger.py
  - thêm release_optimizer_candidate_rows(): selector duy nhất cho input optimizer
  - thêm release_optimizer_diagnostics(): xuất candidate IDs, gate rejection counts,
    threshold buckets và best failing bucket
  - optimize_frozen_strategy() dùng lại selector chung này
- core/backtest_validation_replay.py
  - khi IS không tối ưu được, snapshot trả is_optimizer_diagnostics
- core/walk_forward_engine.py
  - window fail vì IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE cũng trả is_optimizer_diagnostics

Regression tests đã thêm:
- test_optimizer_and_diagnostics_share_release_selector
- test_validation_replay_reports_exact_optimizer_candidate_ids_when_inconclusive
```

Đã chạy:

```text
python -m pytest tests/test_backtest_candidate_replay.py -q
  16 passed

python -m pytest tests/test_backtest_candidate_replay.py tests/test_backtest_phase5_validation.py tests/test_walk_forward.py tests/test_backtest_simulation_diagnostics.py -q
  42 passed
```

Đối chiếu snapshot:

```text
Phase 6B snapshot:
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260729T114048_0700.json

IS rows = 2387
release candidates đưa vào optimizer = 37
passing threshold buckets = 8
optimizer tái lập được config:
- config_id = EURUSD-frozen-9966e2dd9446
- side = buy
- allowed_regimes = ["trend_up"]
- min_setup_score = 55
- min_expected_rr = 1.5

Best bucket 6B:
- selected_count = 13
- total_r = +4.5897R
- expectancy = +0.353054R
- profit_factor = 1.76495
- passes optimizer thresholds = true
```

```text
Phase 6D snapshot:
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260729T151508_0700.json

IS rows = 2378
release candidates đưa vào optimizer = 36
passing threshold buckets = 0
optimizer tái lập đúng kết quả runner: frozen_strategy_config = null

Best bucket 6D:
- market_regime = trend_up
- side = buy
- min_setup_score = 50
- min_expected_rr = 1.5
- selected_count = 25
- total_r = +1.5812R
- expectancy = +0.063248R
- profit_factor = 1.126454
- passes optimizer thresholds = false
```

So sánh candidate set:

```text
Phase 6B release candidates = 37
Phase 6D release candidates = 36
candidate trùng ID/time = 22
chỉ có ở 6B = 15
chỉ có ở 6D = 14
```

Lát cắt quan trọng trong Phase 6D:

```text
Tất cả release candidates:
- n = 36
- wins = 18
- losses = 18
- total_r = +6.1465R
- expectancy = +0.1707R
- profit_factor = 1.3951

setup_score < 50:
- n = 6
- wins = 5
- losses = 1
- total_r = +4.9794R
- expectancy = +0.8299R
- profit_factor = 5.9794

setup_score >= 50:
- n = 30
- wins = 13
- losses = 17
- total_r = +1.1671R
- expectancy = +0.0389R
- profit_factor = 1.0802
```

Kết luận Phase 7A:

```text
Phase 7A đã finish.

Không tìm thấy lỗi selector parity giữa probe logic và runner logic.
Optimizer hiện có thể tái lập đúng bằng cùng input:
- snapshot 6B IS input tạo được config
- snapshot 6D IS input không tạo được config

Sai lệch giữa kết quả tốt ở Phase 6C và runner 6D đến từ input sau khi chạy lại,
không phải do runner bỏ qua gate M15 strict.

Trong Phase 6D, tổng nhóm release candidate vẫn dương chủ yếu nhờ 6 candidate
có setup_score < 50. Nhưng optimizer không được phép chọn min_setup_score < 50.
Phần candidate nằm trong grid hợp lệ của optimizer không đạt ngưỡng
expectancy >= 0.10R và profit_factor >= 1.20, nên runner trả
IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE là đúng.
```

Phase tiếp theo nên là Phase 7B - IS edge decomposition và stability audit.

Lý do:

```text
Phase 7A xác nhận selector đúng và runner tái lập được.
Bây giờ cần phân rã edge thật trong IS theo setup_score, side, market_regime,
tháng/session và chi phí để xem nhóm setup_score < 50 là tín hiệu ổn định hay
chỉ là lát cắt nhỏ/overfit.
Không nên hạ min_setup_score xuống dưới 50 trước khi Phase 7B chứng minh edge
ổn định qua nhiều khoảng thời gian.
```

### Phase 7B - IS edge decomposition và stability audit

Chỉ thực hiện nếu Phase 7A xác nhận selector đúng nhưng tập IS thật sự không
optimizable.

Phân rã tập IS theo:

```text
m15_quality
side
market_regime
setup_score
tháng / session
transaction cost
```

So sánh 1 walk-forward window thành công với 2 window thất bại. Chỉ chấp nhận
một rule đơn giản nếu có đủ mẫu, expectancy và profit factor dương sau chi phí,
ổn định qua nhiều khoảng thời gian và không phụ thuộc vào một tháng hoặc một
bucket nhỏ.

Nếu edge chỉ xuất hiện ở lát cắt nhỏ, rất nhạy với threshold hoặc cần nhiều
ngoại lệ, kết luận Phase 7B là fail và giữ chiến lược ở `RESEARCH_ONLY`.

Kết quả thực hiện Phase 7B - 2026-07-29:

Nguồn dữ liệu chính:

```text
C:\Users\tntan\AppData\Roaming\ai-market-analyst\backtests\backtest_EURUSD_20260729T151508_0700.json

validation_replay.is_start = 2025-01-01T00:00:00+00:00
validation_replay.is_end = 2025-12-28T04:48:00+00:00
validation_replay.status = INCONCLUSIVE
validation_replay.reason = IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
```

Tập release candidates thật sự được đưa vào optimizer:

```text
n = 36
wins = 18
losses = 18
total_r = +6.1465R
expectancy = +0.1707R
profit_factor = 1.3951
gross_total_r = +7.6846R
gross_expectancy = +0.2135R
gross_profit_factor = 1.5192
cost_r = 1.5379R
avg_cost_r = 0.0427R/trade
```

Lát cắt theo score:

```text
setup_score < 50:
- n = 6
- wins = 5
- losses = 1
- total_r = +4.9794R
- expectancy = +0.8299R
- profit_factor = 5.9794
- nhận xét: quá ít mẫu; 5/6 trade nằm ở Q4/2025, nên rất dễ là lát cắt muộn/overfit.

setup_score >= 50:
- n = 30
- wins = 13
- losses = 17
- total_r = +1.1671R
- expectancy = +0.0389R
- profit_factor = 1.0802
- nhận xét: đây là phần nằm trong grid optimizer hiện tại, nhưng không đạt ngưỡng.
```

Lát cắt theo side/regime:

```text
buy / trend_up:
- n = 31
- wins = 15
- losses = 16
- total_r = +6.5606R
- expectancy = +0.2116R
- profit_factor = 1.4858
- nhưng theo quý:
  - Q2: +2.4436R, expectancy +0.3054R
  - Q3: -1.0775R, expectancy -0.1197R
  - Q4: +5.1945R, expectancy +0.3710R
- nhận xét: dương tổng thể nhưng không ổn định; Q3 âm rõ.

sell / trend_down:
- n = 5
- wins = 3
- losses = 2
- total_r = -0.4141R
- expectancy = -0.0828R
- profit_factor = 0.7983
- nhận xét: không có edge.
```

Lát cắt theo score bucket:

```text
50-54:
- n = 22
- total_r = -0.6461R
- expectancy = -0.0294R
- profit_factor = 0.9386

55-59:
- n = 7
- total_r = +2.8132R
- expectancy = +0.4019R
- profit_factor = 1.9271
- nhận xét: chưa đủ min sample 8 khi tách theo side/regime để tạo config ổn định.

60-64:
- n = 1
- total_r = -1.0000R
```

Lát cắt theo tháng/quý:

```text
Q1/2025:
- n = 5
- total_r = -0.4141R
- expectancy = -0.0828R
- profit_factor = 0.7983

Q2/2025:
- n = 8
- total_r = +2.4436R
- expectancy = +0.3054R
- profit_factor = 2.6245

Q3/2025:
- n = 9
- total_r = -1.0775R
- expectancy = -0.1197R
- profit_factor = 0.8204

Q4/2025:
- n = 14
- total_r = +5.1945R
- expectancy = +0.3710R
- profit_factor = 1.8658
```

Nhận xét theo thời gian:

```text
Edge không ổn định theo quý.
Q3 âm, Q4 dương mạnh; riêng nhóm setup_score < 50 gần như chỉ xuất hiện tốt ở Q4.
Vì vậy không đủ cơ sở để hạ min_setup_score xuống dưới 50.
```

Lát cắt theo session:

```text
ASIA:
- n = 9
- total_r = +3.7657R
- expectancy = +0.4184R
- profit_factor = 2.2473
- nhưng positive_months = 2/5, và optimizer không tạo được passing bucket.

NEW_YORK:
- n = 8
- total_r = +0.8983R
- expectancy = +0.1123R
- profit_factor = 1.2246
- nhưng Q4 âm, và optimizer không tạo được passing bucket.

OVERLAP:
- n = 7
- total_r = +0.6320R
- expectancy = +0.0903R
- profit_factor = 1.2099
- không đủ mẫu và expectancy dưới 0.10R.

LONDON:
- n = 10
- total_r = -0.1899R
- expectancy = -0.0190R
- profit_factor = 0.9581
```

Lát cắt theo transaction cost:

```text
Tổng release candidates:
- gross_expectancy = +0.2135R
- net_expectancy = +0.1707R
- avg_cost_r = 0.0427R/trade

setup_score >= 50:
- gross_expectancy = +0.0823R
- net_expectancy = +0.0389R
- gross_profit_factor = 1.1785
- net_profit_factor = 1.0802

Nhận xét:
Chi phí có làm edge yếu hơn, nhưng không phải nguyên nhân duy nhất.
Ngay cả trước chi phí, phần score >= 50 vẫn chưa đạt cả expectancy 0.10R lẫn
profit factor 1.20.
```

Rule candidate nổi lên nhưng bị loại:

```text
Rule thử:
- tp1_source = target_zone
- base_rejection_reason = blocked_by_permission

Sau đó optimizer chọn:
- side = buy
- market_regime = trend_up
- min_setup_score = 50
- min_expected_rr = 1.5

Selected bucket:
- n = 14
- wins = 6
- losses = 8
- total_r = +2.4356R
- expectancy = +0.1740R
- profit_factor = 1.4027
```

Lý do không chấp nhận rule này:

```text
1. Mẫu chỉ có 14 trade, vẫn nhỏ.
2. Theo tháng chỉ dương 4/8 tháng.
3. Q4 chỉ còn expectancy +0.0387R và profit_factor 1.0646, dưới ngưỡng.
4. LONDON và OVERLAP trong bucket này đều âm.
5. base_rejection_reason = blocked_by_permission là trạng thái scan-time bị chặn,
   không phải tín hiệu thị trường ổn định. Dùng nó làm production gate là không
   hợp lý nếu chưa có giả thuyết mới về permission/decision logic.
```

So sánh walk-forward:

```text
walk_forward.verdict = INCONCLUSIVE
window_count = 3
successful_window_count = 1

wf-001:
- IS: 2025-01-01 -> 2025-07-01
- error = IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
- is_summary.total_trades = 164
- is_summary.total_r = -6.0805R
- is_summary.expectancy_r = -0.0371R
- is_summary.profit_factor = 0.8967

wf-002:
- IS: 2025-04-01 -> 2025-10-01
- frozen config tạo được:
  - side = buy
  - regime = trend_up
  - min_setup_score = 50
  - min_expected_rr = 1.5
- OOS: 2025-10-01 -> 2026-01-01
- oos_summary.total_trades = 0
- nhận xét: "successful" ở đây chỉ nghĩa là tạo được config và replay xong,
  không phải có OOS edge.

wf-003:
- IS: 2025-07-01 -> 2026-01-01
- error = IS_CANDIDATE_LEDGER_NOT_OPTIMIZABLE
- is_summary.total_trades = 193
- is_summary.total_r = -14.3094R
- is_summary.expectancy_r = -0.0741R
- is_summary.profit_factor = 0.8316
```

Giới hạn dữ liệu Phase 7B:

```text
Snapshot Phase 6D được tạo trước khi Phase 7A thêm is_optimizer_diagnostics cho
từng walk-forward window, nên không có candidate IDs chi tiết bên trong từng
WF window cũ. So sánh WF ở Phase 7B dùng window summary/config/error hiện có.
Các snapshot mới sau Phase 7A sẽ có diagnostic chi tiết hơn khi WF fail optimizer.
```

Kết luận Phase 7B:

```text
Phase 7B đã finish.

Không tìm được edge ổn định đủ tốt để chuyển sang Phase 7C.
Các lát cắt dương đều gặp ít nhất một vấn đề:
- mẫu nhỏ;
- phụ thuộc Q4/2025 hoặc vài tháng riêng lẻ;
- không ổn định qua quý;
- không tạo được passing optimizer bucket;
- hoặc dựa vào trạng thái scan-time không phù hợp để dùng làm production gate.

Do đó không hạ min_setup_score xuống dưới 50, không thêm session gate, không thêm
tp1/base_reason gate, và không ép tạo frozen_strategy_config.
Giữ EUR/USD ở RESEARCH_ONLY.
```

Phase tiếp theo:

```text
Không nên chạy Phase 7C cho nhánh release hiện tại.

Theo điều kiện dừng đã đặt trước đó:
Phase 7A không tìm thấy lỗi parity và Phase 7B không tìm được edge ổn định;
vì vậy dừng nhánh validation/release EUR/USD hiện tại.

Nếu tiếp tục nghiên cứu, bước tiếp theo không phải là tối ưu thêm threshold,
mà là mở một nhánh research mới với giả thuyết tín hiệu mới, ví dụ:
- sửa hoặc kiểm định lại decision/permission logic;
- nghiên cứu vì sao Q3 âm và Q4 dương;
- kiểm tra liệu M15 strict + target_zone có cần một feature thị trường khác
  để phân biệt giai đoạn tốt/xấu.
```

### Phase 7C - Minimal gate refinement và locked validation

Chỉ thực hiện khi Phase 7A tìm thấy lỗi parity hoặc Phase 7B tìm được một tập
candidate có edge ổn định.

1. Sửa lỗi parity hoặc thêm release gate tối thiểu.
2. Thêm test cho selector và optimizer.
3. Khóa rule trước khi xem kết quả OOS.
4. Chạy lại full EUR/USD validation/walk-forward.
5. Không tiếp tục chỉnh rule dựa trên OOS của lần chạy này.

Tiêu chí validation pass:

```text
frozen_strategy_config != null
validation_replay.status = COMPLETE
oos_trades > 0
walk_forward.successful_window_count >= 2/3
OOS expectancy > 0 sau chi phí
OOS profit_factor > 1
drawdown nằm trong release limit
```

Điều kiện dừng:

```text
Phase 7A không tìm thấy lỗi parity và Phase 7B không tìm được edge ổn định;
hoặc Phase 7C fail trên locked OOS;
hoặc walk-forward vẫn chỉ đạt 1/3 và hiệu quả sau chi phí tiếp tục âm.
```

Khi gặp điều kiện dừng, không hạ ngưỡng optimizer để ép trạng thái
`VALIDATED`. Giữ EUR/USD ở `RESEARCH_ONLY` và chỉ mở lại nghiên cứu khi có giả
thuyết tín hiệu mới.

### Phase 8 - Cross-symbol validation

Chỉ thực hiện sau khi Phase 7C hoàn thành và EUR/USD đạt `VALIDATED`. Kết quả
tốt của EUR/USD không được xem là bằng chứng chiến lược đúng với mọi cặp.

Mục tiêu:

```text
Kiểm tra chiến lược trên từng cặp độc lập.
Xác định phần logic nào có thể dùng chung và cặp nào thực sự có edge.
Tạo frozen_strategy_config riêng cho từng cặp đạt validation.
```

Nguyên tắc:

1. Dùng cùng phiên bản mã nguồn, scoring contract và execution contract.
2. Mỗi cặp có data manifest, IS/OOS split, candidate ledger và walk-forward
   riêng.
3. Không dùng `frozen_strategy_config` của EUR/USD cho cặp khác.
4. Không mặc định tái sử dụng threshold, side hoặc market regime được tối ưu từ
   EUR/USD.
5. Khóa rule của từng cặp trước khi chạy OOS và không chỉnh lại rule sau khi xem
   OOS.
6. Chỉ áp dụng cấu hình cho cặp có symbol khớp và đạt `VALIDATED`.

Thực hiện cho từng cặp:

```text
chạy IS research
chọn candidate và tạo frozen config riêng
chạy locked OOS validation
chạy walk-forward
phân loại VALIDATED / RESEARCH_ONLY / INCONCLUSIVE
```

Tiêu chí pass cho từng cặp:

```text
frozen_strategy_config != null
frozen_strategy_config.symbol khớp cặp đang kiểm chứng
validation_replay.status = COMPLETE
oos_trades > 0
walk_forward.successful_window_count >= 2/3
OOS expectancy > 0 sau chi phí
OOS profit_factor > 1
drawdown nằm trong release limit
```

Phase 8 finish khi:

```text
tất cả cặp nằm trong phạm vi kiểm chứng đã được phân loại;
mỗi cặp VALIDATED có frozen config riêng;
cặp fail hoặc thiếu bằng chứng vẫn giữ RESEARCH_ONLY/INCONCLUSIVE;
không có config nào được dùng chéo symbol.
```

Chỉ kết luận rule có khả năng tổng quát khi nó vượt validation trên nhiều cặp
độc lập. Không kết luận chiến lược đúng với mọi cặp chỉ từ kết quả EUR/USD.

## Phương án thực hiện tuần tự

Phương án dưới đây chia nhỏ công việc để dễ thực hiện, dễ test và tránh sửa nhầm vào gate live.

### Giai đoạn 1 - Bổ sung chẩn đoán

1. Thêm field `simulation_rejection_reason` vào candidate ledger khi `simulate_trade_from_analysis()` trả `None`.

2. Tách reason chi tiết trong hàm mô phỏng:

```text
INVALID_SIDE
VALIDATION_RESEARCH_ONLY_SCENARIO
MISSING_SL_TP
INVALID_ENTRY_ZONE
ENTRY_ZONE_NOT_TOUCHED
INVALID_TRADE_GEOMETRY
QUOTE_CONVERSION_MISSING
```

3. Giữ nguyên behavior hiện tại: vẫn reject như cũ, chỉ lưu thêm lý do.

4. Thêm test nhỏ xác nhận mỗi nhánh reject trả đúng reason.

5. Chạy `pytest tests/ -x -q`.

### Giai đoạn 2 - Chạy lại và đọc kết quả

6. Chạy lại EUR/USD ở chế độ `Kiểm chứng`, chọn end date lùi 2-3 ngày giao dịch để tránh thiếu nến cuối.

7. Đọc snapshot mới và thống kê:

```text
base_eligible
TRADE_SIMULATION_REJECTED theo simulation_rejection_reason
expected_effective_rr rỗng/có giá trị
entry_zone_source
m15_quality
decision
```

8. Nếu `ENTRY_ZONE_NOT_TOUCHED` chiếm lớn nhất, chuyển sang Giai đoạn 3A.

9. Nếu `MISSING_SL_TP` chiếm lớn nhất, chuyển sang Giai đoạn 3B.

10. Nếu `QUOTE_CONVERSION_MISSING` hoặc `INVALID_TRADE_GEOMETRY` chiếm lớn, chuyển sang Giai đoạn 3C.

### Giai đoạn 3A - Nếu entry không được fill

11. Kiểm tra rule hiện tại:

```text
execution_timeframe = M15
fill_model = confirmation_close
setup_expiry_minutes = 180
```

12. So với chiến lược thực tế: setup có được phép chờ lâu hơn 3 giờ không.

13. Nếu có, tăng hoặc cấu hình hóa `setup_expiry_minutes` cho validation/backtest.

14. Nếu không, giữ nguyên rule và chấp nhận các setup đó bị loại.

15. Chạy test backtest execution fill.

### Giai đoạn 3B - Nếu thiếu SL/TP

16. Chỉ soi nhóm `entry_zone_source = smc_v2_selected`.

17. Tìm vì sao scenario có entry zone nhưng thiếu `take_profit` hoặc `stop_loss`.

18. Sửa phần tạo scenario để `smc_v2_selected` có SL/TP hợp lệ nếu đủ dữ liệu.

19. Không nâng cấp `fallback` hoặc `smc_distant` thành validation candidate.

20. Thêm test cho scenario `smc_v2_selected` phải có SL/TP hợp lệ.

### Giai đoạn 3C - Nếu geometry hoặc quote conversion lỗi

21. Với `INVALID_TRADE_GEOMETRY`, log entry/SL/TP sau cost để biết bị đảo chiều hay spread làm hỏng geometry.

22. Nếu spread/cost làm entry vượt SL/TP, giữ reject nhưng hiển thị lý do rõ.

23. Với `QUOTE_CONVERSION_MISSING`, kiểm tra dữ liệu quote conversion có đủ tại entry/exit không.

24. Nếu thiếu dữ liệu, xử lý ở data manifest hoặc loader, không ép pass.

### Giai đoạn 4 - Siết candidate cho config

25. Chỉ cho optimizer dùng candidate phát hành từ nguồn sạch:

```text
entry_zone_source = smc_v2_selected
expected_effective_rr != None
simulated_trade != None
research_only != True
```

26. Không dùng `fallback`.

27. Không dùng `smc_distant`.

28. Giữ `MIN_LEDGER_CANDIDATES = 8`, chưa giảm ngưỡng.

29. Thêm test optimizer không chọn fallback/distant.

### Giai đoạn 5 - Validation lại

30. Chạy lại EUR/USD `Kiểm chứng`.

31. Kiểm tra:

```text
base_eligible >= 8
frozen_strategy_config != null
validation_replay.status = COMPLETE
```

32. Nếu chưa đủ 8 candidate, quay lại đúng reason lớn nhất còn lại.

33. Nếu đã complete, kiểm tra Walk-Forward:

```text
walk_forward.successful_window_count
walk_forward.verdict
aggregate_oos
```

### Giai đoạn 6 - UI và Settings

34. Nếu lifecycle là `DRAFT`, UI phải hiện "Lưu đề xuất nháp".

35. Nếu lifecycle là `VALIDATED` hoặc `RELEASE_READY`, UI phải hiện "Áp dụng cấu hình".

36. Sau khi apply, kiểm tra Settings:

```text
backtest_config_id có giá trị
backtest_status = DRAFT hoặc VALIDATED
backtest = True chỉ khi VALIDATED
```

37. Xác nhận "Dùng BT đã duyệt" chỉ tick khi `backtest_status=VALIDATED`.

### Giai đoạn 7 - Chốt

38. Chạy `pytest tests/ -x -q`.

39. Lưu snapshot/chẩn đoán mới vào docs nếu kết quả thay đổi đáng kể.

40. Commit từng nhóm nhỏ:

```text
commit 1: diagnostics
commit 2: sửa scenario/fill theo reason thật
commit 3: test + docs cập nhật
```

Kết quả cuối cùng mong muốn:

```text
EUR/USD tạo được frozen_strategy_config
validation_replay.status không còn INCONCLUSIVE
UI hiện nút hành động phù hợp
Settings chỉ tick "Dùng BT đã duyệt" khi cấu hình thật sự đạt VALIDATED
```
