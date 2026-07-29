# Kế hoạch nâng cấp Scanner Fast-Reject SMC

> **Trạng thái:** Đề xuất triển khai, chưa sửa code
>
> **Ngày lập:** 2026-07-29
>
> **Phạm vi:** Bulk market scanner; không thay đổi công thức chấm điểm/gate và không thay đổi backtest/detail analysis
>
> **Phương án kiểm chứng:** Fast-track, chỉ dùng corpus/snapshot offline; không yêu cầu theo dõi dữ liệu live
>
> **Độ phức tạp tổng thể:** 8/10 (điểm khó nhất là tách candidate discovery và tái sử dụng cache mà không làm lệch SMC context)

Tài liệu này là runbook để một AI khác có thể đọc, sửa code, chạy test và nghiệm thu theo cùng một trình tự. Đây chưa phải runtime contract. Nếu triển khai thành công, phải cập nhật thêm `docs/scanner/scanner-flow.md` vì file đó là tài liệu runtime contract hiện hành.

## 1. Mục tiêu và giới hạn

### 1.1 Mục tiêu

Giảm thời gian/CPU của bulk scanner bằng hai tầng dừng sớm:

1. **Tầng 1 — post-context reject:** sau khi đã có full SMC context, nếu cả BUY và SELL đều không có canonical selected zone thì không chạy các bước sau.
2. **Tầng 2 — pre-SMC prefilter:** phát hiện mã không có raw SMC candidate trước khi chạy full `build_smc_context()`.

### 1.2 Không nằm trong phạm vi

- Không sửa công thức `signal_score`, `setup_score`, `final_score`.
- Không sửa ngưỡng hoặc công thức các gate.
- Không thay đổi scorer v2, scorer legacy hoặc trade-plan semantics.
- Không bật fast path cho backtest, replay, walk-forward hoặc màn hình phân tích một mã.
- Không cần chờ/giám sát live nhiều phiên; validation bắt buộc dùng corpus offline.

### 1.3 Thay đổi có chủ đích

Mã bị chứng minh không có setup sẽ không còn tạo fallback/watch scenario để hiển thị. Nó trả về `stand_aside`/`no_setup` và được đánh dấu là structural reject. Đây là thay đổi route và hiển thị, không phải thay đổi logic điểm/gate của các mã đi qua full path.

## 2. Bằng chứng hiện trạng trong code

| Bằng chứng | Vị trí |
|---|---|
| Bulk scanner fetch dữ liệu cho từng symbol rồi submit mọi packet hợp lệ vào pool phân tích | `controllers/scanner_controller.py:465-510` |
| `analyze_symbol()` chỉ là wrapper gọi `AnalysisPipeline.execute()` | `core/analysis_engine.py:19-69` |
| `execute()` gọi liên tiếp Step 1 rồi correlation, score, scenarios, direction, gate, final score, enrich và assemble | `core/analysis_pipeline.py:149-232` |
| Step 1 dựng technical snapshot và full SMC context | `core/analysis_pipeline.py:287-316` |
| `build_smc_context()` phân tích D1, H4 và H1 | `core/smc_context.py:157-205` |
| SMC v2 duyệt candidate H4/H1, gồm demand/supply/order block/FVG | `core/smc_scorer_v2.py:60-135`, `:587-606` |
| Chỉ mode v2 mới có `decision_impact_allowed=True` | `core/smc_scoring_contract.py:58-78` |
| Với v2, thiếu preferred zone thì `build_scenarios()` bỏ qua side | `core/analysis_pipeline.py:529-553`, `core/risk_engine.py:607-617` |
| `scanner_row_from_analysis()` tiêu thụ nhiều trường của full result | `core/scanner.py:64-336` |
| `blocked_scanner_row()` đặt `analysis_result=None`, dẫn đến nghĩa `DATA_UNAVAILABLE` | `core/scanner.py:339-365`, `core/scanner_ranking_engine.py:827-849` |
| Full output contract được khóa bởi integration tests | `tests/test_analysis_pipeline_integration.py:243-293` |
| UI diagnostics hiện chỉ biết các tên step hiện hành | `ui/screens/scanner_detail_screen.py:3257-3300` |

## 3. Nguyên tắc bất biến

1. **Full là mặc định.** Hai cờ fast mặc định false; khi cờ không được truyền, chạy nguyên pipeline hiện tại.
2. **Chỉ bulk scanner được phép fast.** Backtest, detail analysis và caller ngoài bulk scanner luôn dùng full.
3. **Chỉ v2 active mới được xét canonical SMC reject.** Legacy/shadow phải fail-open.
4. **Không chắc chắn thì chạy full.** Thiếu price/ATR, dữ liệu malformed, exception hoặc cache không hợp lệ đều không được reject.
5. **Survivor parity.** Mã không bị reject phải có selected zone, score, scenario, provenance và quyết định tương đương baseline.
6. **Không dùng `blocked_scanner_row()` cho “không có setup”.** `analysis_result` vẫn phải là dictionary đầy đủ.
7. **Không tạo lệnh từ fast result.** Structural reject không được trở thành auto-trade candidate, Telegram order hoặc order payload hợp lệ.
8. **Tách scorer khỏi route.** Fast path chỉ bỏ qua việc tính toán khi có bằng chứng không thể tạo setup; không đổi công thức điểm/gate.
9. **Không dùng cache global.** Cache discovery chỉ thuộc một pipeline/symbol, bất biến sau khi tạo và không rò dữ liệu giữa worker.
10. **Offline shadow là cổng bắt buộc.** Không theo dõi live không có nghĩa là bỏ qua đối chiếu full-vs-fast.
11. **Không tái sử dụng Scanner rollout `SHADOW`.** `ScannerRolloutSettings.stage` đang kiểm soát rollout quyết định/order của Scanner V2; fast-path dùng offline A/B và hai feature flag riêng.

## 4. Thuật ngữ và route đích

### 4.1 Thuật ngữ

- **Full:** pipeline hiện tại, đủ Step 1–9.
- **Raw candidate:** zone do detector ban đầu trả về, trước broken/quality/enrichment đầy đủ.
- **Canonical selected zone:** zone được chính scorer v2 chọn qua `evaluate_smc_zones()` và `select_smc_zone_v2()`.
- **Post-context reject:** Tầng 1, reject sau full SMC context.
- **Prefilter reject:** Tầng 2, reject trước full SMC context.
- **Trade false reject:** fast path reject nhưng full baseline có selected zone hoặc scenario BUY/SELL.
- **Watch false reject:** không có trade thật nhưng baseline có tín hiệu watch như BOS/CHOCH/sweep/watch zone.
- **Fail-open:** không đủ bằng chứng để reject thì chạy full.

### 4.2 Route đích

```text
Bulk scanner
  -> validate candle counts + technical tối thiểu
  -> Tầng 2 raw candidate discovery
       -> raw candidate rỗng
            -> prefilter_reject
       -> có raw candidate
            -> full SMC context (tái sử dụng raw cache)
                 -> Tầng 1 canonical selector
                      -> BUY/SELL đều không có selected zone
                           -> post_context_reject
                      -> có selected zone
                           -> correlation -> score -> scenarios
                              -> direction -> gates -> final -> assemble
```

### 4.3 State machine fast-path

Không thêm `analysis_profile` hoặc `prefilter_mode`. Chỉ dùng hai boolean cùng kiểu `ScannerRequest.feature_flags`:

```text
scanner_fast_tier1 = false
scanner_fast_tier2 = false
```

Quy tắc:

- `analyze_symbol()` và `AnalysisPipeline.execute()` nhận hai keyword boolean, mặc định false.
- Chỉ `_analyze_one_symbol()` của bulk scanner truyền giá trị từ `ScannerRequest.feature_flags`.
- `is_backtest=True` luôn ép cả hai cờ về false.
- Caller khác, gồm detail analysis và legacy `_scan_one_symbol()`, không truyền cờ nên luôn full.
- Tầng 2 chỉ có hiệu lực khi Tầng 1 đã được bật và cổng offline Tầng 1 đã đạt.
- Hai cờ mặc định `false` cho tới khi nghiệm thu.

Chuỗi truyền cờ bắt buộc phải hoàn chỉnh:

```text
Feature settings
 -> SettingsService._load_feature_flags()
 -> ScannerScreen tạo ScannerRequest.feature_flags
 -> ScannerController.run_market_scan
 -> analyze_kwargs
 -> _analyze_one_symbol
 -> analyze_symbol
 -> AnalysisPipeline.execute
```

Hiện `feature_flags` có trong request nhưng chưa được truyền vào analysis pipeline; phải bổ sung chuỗi này trước khi bật.

Không dùng `ScannerRolloutSettings.stage=SHADOW` để đại diện fast-path shadow. Hai khái niệm khác nhau:

- Scanner rollout shadow kiểm soát quyền phát hành quyết định/order;
- fast-path offline shadow chỉ so sánh `would_reject` với full baseline và không cần chờ dữ liệu live.

### 4.4 Truth table route

| Trường hợp | Route |
|---|---|
| Hai cờ tắt, backtest, detail, legacy caller, SMC legacy hoặc SMC shadow | `full` |
| Dữ liệu, price, ATR, discovery hoặc canonical precheck không đánh giá chắc chắn được | fail-open `full` |
| Tầng 2 active và toàn bộ raw family H4/H1 rỗng | `prefilter_reject` |
| Có raw zone nhưng canonical v2 không chọn được BUY lẫn SELL | `post_context_reject` |
| Có canonical selected zone ở ít nhất một side | `full` |

BOS/CHOCH/sweep đơn lẻ không phải raw zone và không ngăn Tầng 2 reject trong phiên bản fast-track ban đầu. Vì vậy một số baseline `WATCH` có thể trở thành `no_setup`; phải ghi vào `watch_false_reject_count` và chấp nhận rõ đây là thay đổi hiển thị. Nếu sản phẩm yêu cầu giữ mọi watch signal, phải đổi predicate thành fail-open khi có watch evidence và chạy lại toàn bộ cổng offline.

## 5. Contract thiết kế

### 5.1 Quyết định prefilter

Tạo helper riêng, ví dụ `core/smc_prefilter.py`. Không trả về boolean trần; trả về payload có thể audit:

```python
{
    "should_reject": bool,
    "stage": "pre_smc" | "post_context",
    "reason_code": str,
    "mode": "v2" | "legacy" | "shadow",
    "prefilter_version": str,
    "fast_path_version": str,
    "raw_counts": {
        "H4": {"demand": 0, "supply": 0, "order_block": 0, "fvg": 0},
        "H1": {"demand": 0, "supply": 0, "order_block": 0, "fvg": 0},
    },
    "selected_zone_ids": {"buy": None, "sell": None},
    "fail_open": bool,
}
```

### 5.2 Predicate Tầng 1

Tầng 1 chỉ reject khi:

1. `resolve_smc_scoring_policy(mode).decision_impact_allowed is True`;
2. price và ATR là số hữu hạn, dương;
3. chạy chính `score_smc_v2()` (nội bộ dùng canonical evaluate/select) hoặc trực tiếp `evaluate_smc_zones()` + `select_smc_zone_v2()` cho BUY và SELL;
4. cả hai selector đều trả `None`.

Không tự đặt `zone_score` threshold mới. Không dùng stale/broken heuristic riêng ngoài canonical scorer.

Để tránh survivor bị chậm vì scorer v2 chạy hai lần, ưu tiên gọi `score_smc_v2()` một lần trong precheck, lấy selected zone từ payload đó và lưu kết quả trong pipeline. Step 3/build diagnostics phải nhận optional precomputed v2 result và tái sử dụng nó. Nếu phiên bản đầu chưa cache được, phải đo overhead và không được bật khi full-route p95 vượt ngưỡng.

### 5.3 Predicate Tầng 2

Phiên bản đầu phải bảo thủ và rẻ:

- discovery trên cả H4 và H1;
- kiểm tra đủ bốn family: demand, supply, order block, FVG;
- chỉ reject khi tất cả family ở cả hai timeframe đều rỗng;
- `detect_order_blocks()` phụ thuộc FVG, nên cache phải lưu theo family và đúng thứ tự phát hiện;
- discovery exception/malformed thì fail-open.

Raw-empty rate phải được đo trước khi refactor sâu. Nếu raw-empty quá thấp hoặc tiết kiệm không đạt ngưỡng, dừng sau Tầng 1 và không triển khai Tầng 2.

Reason code dùng constant, không dùng chuỗi rải rác:

```text
NO_RAW_SMC_CANDIDATE
NO_ACTIONABLE_SMC_ZONE
SMC_PREFILTER_ERROR_FAIL_OPEN
```

### 5.4 Structural-reject result

Kết quả fast phải tiếp tục dùng assembler/helper chung và giữ đủ contract:

- `symbol`, `timestamp`, `scoring_provenance`;
- `data_quality`, `market_regime`, `technical`, `smc`, `chart_payload`;
- `scenario_scores`, `side_scores` đủ BUY/SELL;
- `decision_summary`, `trade_gate`, `trade_permission`, `decision_engine`;
- `macro`, `economic_events`, `evidence`, `execution_quality`;
- `scenarios` chứa một scenario `stand_aside`;
- `pipeline_diagnostics`.

Trạng thái đề xuất:

```text
analysis_status   = "structural_reject"
pipeline_route    = "prefilter_reject" | "post_context_reject"
trade_permission  = {"status": "blocked", ...}
decision_engine   = {"decision": "STAND_ASIDE", "legacy_action": "stand_aside"}
entry_status      = "no_setup"
fast_path_version = "scanner-fast-path-v1"
reason_code       = "NO_RAW_SMC_CANDIDATE" | "NO_ACTIONABLE_SMC_ZONE"
```

`_ensure_safe_defaults()` hiện có nhưng không thể dùng nguyên trạng: side scores còn rỗng và reason mặc định là validation failed. Phải có helper structural reject riêng hoặc override đầy đủ trước khi gọi `_assemble_result()`. Đồng thời phải chặn ATR/watch fallback trong `_assemble_result()`.

Synthetic `trade_gate` phải ghi rõ gate chưa được chạy, ví dụ `evaluation_status="not_evaluated_due_to_fast_reject"`. Không tạo diagnostics giả như thể gate thật đã pass/fail.

Tầng 2 chưa chạy full SMC nên phải trả lightweight SMC payload trung thực:

- vẫn có `D1`, `H4`, `H1` để giữ schema;
- zone arrays rỗng;
- structure/liquidity dùng `not_evaluated`, không dùng `insufficient_data`;
- chứa `analysis_status`, route và reason;
- UI phải diễn giải là “không cần đánh giá sâu”, không phải lỗi dữ liệu.

Không bump SMC scorer/gate/strategy version vì công thức không đổi và backtest vẫn full. Dùng `fast_path_version` riêng; không bump global scanner feature version nếu việc đó làm invalid backtest config đã lưu.

## 6. Kế hoạch thực hiện tuần tự

### Bước 0 — Baseline và corpus offline

**Độ phức tạp: 4/10**

**File/test liên quan:**

- `tests/test_analysis_pipeline_integration.py`
- `tests/test_pipeline_diagnostics.py`
- `tests/test_smc_consumer_phase6.py`
- `tests/test_scanner_domain_models.py`
- đề xuất thêm `tests/fixtures/scanner_fast_path/`

**Việc làm:**

1. Chạy test baseline.
2. Tạo snapshot/fixture cho raw-empty, H1-only, FVG, order block, broken/invalid, setup BUY/SELL, legacy/shadow/v2.
3. Ưu tiên fixture candle deterministic; có thể export snapshot MT5 một lần nếu cần độ thực tế, nhưng không theo dõi live và không đặt lệnh.
4. Lưu output full làm oracle với cùng candles/request/threshold/config.
5. Ghi selected zone IDs, scenario types, candidate status và thời gian.
6. Khi so sánh JSON, normalize field biến động như timestamp/scan ID thay vì coi chúng là regression.

**Cổng nghiệm thu:**

- baseline xanh;
- mỗi nhóm edge case có fixture;
- có thể chạy lặp không cần MT5/network.

### Bước 1 — Flags và route schema

**Độ phức tạp: 4/10**

**File sửa:**

- `config/settings.py`
- `services/settings_service.py`
- `ui/screens/scanner_screen.py`
- `core/analysis_engine.py`
- `core/analysis_pipeline.py`
- `core/scanner.py`
- `controllers/scanner_controller.py`

**Việc làm:**

1. Thêm hai keyword boolean tương ứng vào `analyze_symbol()`/`AnalysisPipeline.execute()`, mặc định false.
2. Thêm hai flag `scanner_fast_tier1`, `scanner_fast_tier2` vào feature settings/request, mặc định false.
3. Truyền cờ qua toàn bộ chuỗi caller ở mục 4.3.
4. Ép `is_backtest` và caller không phải bulk scanner về full.
5. Thêm route/status fields nhưng chưa short-circuit.
6. Giai đoạn fast-track không cần thêm UI toggle; lưu/đọc flags qua settings service. Nếu cần điều khiển từ UI, tách thành task sản phẩm riêng.
7. Khi nghiệm thu xong, bật bằng cấu hình đã lưu thay vì đổi source default; mặc định false vẫn là đường rollback an toàn.

**Test/cổng:**

- flag off exact baseline;
- backtest/detail không nhận fast;
- settings cũ load được;
- request fingerprint/scan context không bị lỗi.

### Bước 2 — Helper canonical post-context

**Độ phức tạp: 6/10**

**File mới/sửa:**

- `core/smc_prefilter.py`
- `core/smc_scorer_v2.py` (chỉ import/tái sử dụng nếu cần)
- `core/smc_scoring_contract.py` (chỉ khi cần helper policy chung)

**Việc làm:**

1. Implement predicate Tầng 1 theo mục 5.2.
2. Trả payload decision có counts, selected IDs và reason.
3. Fail-open khi mode không phải v2 hoặc dữ liệu không hợp lệ.
4. So sánh selected zone của helper với selected zone được tạo trong Step 3 khi chạy full.
5. Lưu optional precomputed v2 result để Step 3 không score/evaluate zone lần hai.

**Test/cổng:**

- BUY/SELL độc lập;
- H4/H1 và đủ bốn family;
- invalid ATR/price;
- legacy/shadow luôn full;
- parity với canonical Step 3.

### Bước 3 — Structural-reject builder

**Độ phức tạp: 7/10**

**File sửa:**

- `core/analysis_pipeline.py`
- `core/scanner.py`
- có thể thêm `core/structural_reject.py` nếu helper quá lớn

**Việc làm:**

1. Tạo `_prepare_structural_reject(stage, decision)`.
2. Đặt fail-closed defaults đúng schema.
3. Giữ context đã có và chart payload.
4. Tạo scenario `stand_aside`; không tạo buy/sell fallback.
5. Chặn fallback trong `_assemble_result()`.
6. Diagnostics dùng status `warning` với metadata `skipped_steps`; không thêm status `skipped` nếu chưa sửa UI/test.

**Test/cổng:**

- `_assert_full_contract()` pass;
- `analysis_result` vẫn là dict;
- `macro` tồn tại cho `_analyze_one_symbol()`;
- round-trip JSON pass.

### Bước 4 — Short-circuit Tầng 1

**Độ phức tạp: 5/10**

**File sửa:**

- `core/analysis_pipeline.py`
- `core/analysis_engine.py`

**Việc làm:**

1. Sau `_step_validate_and_build_context()`, gọi helper nếu `scanner_fast_tier1=True`.
2. Nếu reject, gọi structural builder và return.
3. Nếu không reject, truyền precomputed v2 result vào Step 3 rồi giữ nguyên Step 2–9.
4. Khi hai cờ tắt, không tạo precheck/cache và không thay đổi full path.

**Test/cổng:**

- spy chứng minh correlation/score/scenarios/direction/gate/final/enrich không chạy khi reject;
- survivor chạy đủ;
- hai cờ tắt cho kết quả exact baseline.

### Bước 5 — Scanner adapter, safety, UI và persistence

**Độ phức tạp: 7/10**

**File sửa:**

- `core/scanner.py`
- `core/scanner_ranking_engine.py` hoặc candidate engine nếu cần
- `controllers/scanner_controller.py`
- `ui/screens/scanner_detail_screen.py`
- `services/scanner_persistence_service.py`
- test scanner/detail/observability tương ứng

**Việc làm:**

1. Map không có scenario sang `entry_status="no_setup"`.
2. Structural reject không thành `DATA_UNAVAILABLE`.
3. Candidate router không tạo order payload/auto-trade candidate.
4. UI hiển thị route/reason rõ ràng.
5. Snapshot full và summary giữ `pipeline_route`/`fast_reject_reason`.
6. Kiểm tra AI targets, market brief, Telegram và summary không coi reject là data error.
7. Rejected row không được vào order alert/candidate; tuy nhiên số lượng group/status và nội dung market brief/summary toàn scan có thể thay đổi. Test phải khóa thay đổi mong đợi thay vì giả định mọi downstream đều giữ nguyên.

**Test/cổng:**

- canonical candidate status là `OUT_OF_STRATEGY`; không dùng `DATA_UNAVAILABLE`;
- legacy group/action phải được đồng bộ để không biến structural reject thành data error hoặc order candidate;
- không có order;
- UI/chart/persistence không lỗi;
- backward snapshot đọc được.

### Bước 6 — Offline A/B và bật Tầng 1

**Độ phức tạp: 5/10**

**File/script đề xuất:**

- `scripts/compare_scanner_fast_path.py`
- `tests/test_scanner_fast_path.py`

**Việc làm:**

1. Với mỗi fixture, chạy full baseline.
2. Tính `would_post_context_reject` nhưng chưa dùng để bỏ qua.
3. Chạy lại Tầng 1 active trên cùng input.
4. So sánh selected zone, scenario, candidate status và contract.
5. Ghi riêng trade false reject và watch false reject.
6. Normalize timestamp/scan ID; không bỏ qua field quyết định, provenance hoặc zone ID.

**Cổng bật:**

- trade false reject = 0;
- không có exception;
- survivor parity đạt;
- contract/UI/safety pass.

Sau cổng này mới bật `scanner_fast_tier1=true`. Không cần chờ live monitoring.

Khác biệt được phép:

- survivor: không được khác selected zone, score, scenario, decision hoặc provenance;
- Tầng 1 reject: được bỏ score/gate/fallback phía sau nhưng technical và full SMC context phải giữ nguyên;
- Tầng 2 reject: được dùng lightweight SMC contract theo mục 5.4;
- summary/brief: được thay đổi theo số structural reject, nhưng không được tạo order/candidate mới.

### Bước 7 — Feasibility gate cho Tầng 2

**Độ phức tạp: 3/10**

Đây là cổng quyết định có đáng refactor Tầng 2 hay không.

**Việc làm:**

1. Trên corpus hiện có, đếm tỷ lệ raw-empty H4/H1.
2. Đo tỷ trọng thời gian của:
   - technical;
   - full SMC;
   - post-SMC.
3. Ước lượng wall-clock savings nếu chỉ bỏ raw-empty.

**Quyết định:**

- Nếu raw-empty rate đủ cao và saving đạt ngưỡng đã chốt: tiếp tục Bước 8.
- Nếu raw-empty rate thấp hoặc saving không đáng kể: dừng sau Tầng 1, không refactor rủi ro 9/10.

### Bước 8 — Raw candidate discovery và cache

**Độ phức tạp: 9/10**

**File sửa:**

- `core/smc_context.py`
- `core/smc_prefilter.py`
- có thể thêm `core/smc_discovery.py`

**Việc làm:**

1. Tách `discover_smc_candidates()` cho H4/H1.
2. Gọi detector theo đúng dependency: FVG trước, rồi order block; supply/demand theo detector hiện tại.
3. Lưu raw candidates immutable theo `symbol/timeframe/family`.
4. Cho `_smc_for_timeframe()` nhận raw cache để không chạy detector hai lần.
5. Full survivor vẫn phải chạy swings, liquidity, premium/discount, sweep links, enrichment và D1 đầy đủ.
6. Không dùng global/shared mutable cache; clone dữ liệu nếu helper/enrichment có mutate.
7. Discovery lỗi, ownership không rõ hoặc payload malformed thì fail-open full.

**Test/cổng:**

- detector call count đúng một lần;
- không rò cache giữa symbol/worker;
- raw payload không bị mutate ngoài ownership;
- full context survivor parity sâu: selected IDs, scores, scenario, provenance.

### Bước 9 — Short-circuit Tầng 2

**Độ phức tạp: 7/10**

**File sửa:**

- `core/analysis_pipeline.py`
- `core/analysis_engine.py`
- `controllers/scanner_controller.py`

**Luồng:**

```text
validate candle counts
 -> technical tối thiểu
 -> raw discovery
    -> mọi family H4/H1 rỗng: prefilter_reject
    -> có candidate: full SMC bằng cache
       -> Tầng 1 canonical safety net
       -> Step 2–9
```

**Quy tắc:**

- chỉ active khi `scanner_fast_tier1` và `scanner_fast_tier2` đều true;
- chỉ v2 active; legacy/shadow, backtest/detail và caller không truyền fast flags luôn full;
- route ghi `prefilter_reject`, stage `pre_smc`;
- dùng cùng structural-reject builder Bước 3.

**Test/cổng:**

- raw-empty không gọi full `build_smc_context()`;
- H1-only/FVG/order block không bị reject;
- discovery exception chạy full;
- Tier 1 vẫn bắt post-context no-zone;
- backtest/detail exact full.

### Bước 10 — Regression và benchmark offline

**Độ phức tạp: 6/10**

**Việc làm:**

1. Chạy corpus với tỷ lệ mã rỗng 0/25/50/75/100%.
2. Warm-up rồi lặp tối thiểu 20 lần.
3. Đo p50/p95/max từng route và wall-clock toàn scan.
4. Chạy test full suite.
5. Kiểm tra settings/snapshot backward compatibility.

**Cổng bật Tầng 2:**

- trade false reject = 0;
- survivor parity đạt;
- full-route p95 không tăng quá ngưỡng đã chốt (đề xuất 5%);
- wall-clock giảm có ý nghĩa;
- không có lỗi safety/UI/persistence.

Không dùng timing assertion trong unit test; unit test kiểm tra lời gọi và kết quả, benchmark riêng dùng để đo hiệu năng.

### Bước 11 — Nghiệm thu và rollback

**Độ phức tạp: 4/10**

**Việc làm:**

1. Bật Tầng 1/Tầng 2 theo thứ tự.
2. Giữ hai flag độc lập để rollback Tầng 2 trước nếu cần.
3. Ghi lại version prefilter và route trong output.
4. Cập nhật `docs/scanner/scanner-flow.md` và `docs/README.md` nếu hành vi runtime đã đổi.
5. Chốt commit và checklist release.

**Rollback:**

```text
scanner_fast_tier2 = false  -> tắt Tầng 2, giữ Tầng 1
scanner_fast_tier1 = false  -> tắt cả fast path
hai cờ mặc định false       -> caller cũ chạy nguyên pipeline
```

## 7. Định nghĩa lỗi và fail-open

| Tình huống | Hành động |
|---|---|
| Mode legacy/shadow | Chạy full |
| `is_backtest=True` | Chạy full |
| Thiếu candle tối thiểu | Giữ lỗi validation hiện tại |
| Price/ATR không hợp lệ | Chạy full hoặc giữ data-quality error |
| Discovery exception | Chạy full |
| Cache thiếu/không đúng owner | Bỏ cache, chạy full |
| Raw zone có bất kỳ family/timeframe nào | Chạy full |
| Không có canonical selected zone cả hai side sau full context | Tầng 1 reject |
| Structural reject result thiếu field | Không active; sửa contract trước |

## 8. Bộ test bắt buộc

### 8.1 Predicate

- raw-empty cả H4/H1;
- H4 demand/supply;
- H1 demand/supply;
- H1 FVG;
- H4/H1 order block;
- broken/invalid zone;
- stale zone;
- BOS/CHOCH/sweep;
- invalid price/ATR;
- legacy/shadow/v2.

### 8.2 Control-flow

- Tầng 1 reject không gọi Step 2–9;
- Tầng 2 reject không gọi full SMC;
- survivor gọi mỗi detector đúng một lần;
- hai cờ tắt cho kết quả baseline tương đương;
- symbols chạy song song không dùng nhầm cache.

### 8.3 Contract và safety

- full output contract;
- `analysis_result` luôn là dict;
- `entry_status="no_setup"`;
- không `DATA_UNAVAILABLE` vì structural reject;
- không order payload/auto-trade/Telegram order;
- `candidate_order_payload` rỗng/không khả dụng và `auto_trade_candidate=False`;
- summary/market brief phản ánh đúng số structural reject;
- UI/detail/chart render;
- snapshot full/summary round-trip.

### 8.4 Parity

Với mọi survivor, so sánh tối thiểu:

- selected zone ID và timeframe;
- zone score/relevance/setup score;
- BUY/SELL signal score;
- scenario type/entry zone/SL/TP/RR;
- decision engine và candidate status;
- scoring provenance và SMC version.

### 8.5 Existing suites phải chạy lại

- `tests/test_analysis_pipeline_integration.py`
- `tests/test_pipeline_diagnostics.py`
- `tests/test_smc_scorer_v2.py`
- `tests/test_smc_context.py`
- `tests/test_smc_consumer_phase6.py`
- `tests/test_scanner_domain_models.py`
- `tests/test_scanner_phase6_ranking.py`
- `tests/test_scanner_observability.py`
- `tests/test_scanner_persistence_service.py`
- `tests/test_scanner_detail_diagnostics.py`
- các test backtest execution/parity để chứng minh fast flags không tác động backtest.

## 9. Benchmark offline

Không gọi MT5, news API, AI provider hoặc order API. Dùng cùng candle/request cho baseline và fast path.

Báo cáo tối thiểu:

```text
fixture_count
raw_empty_rate
post_context_reject_rate
prefilter_reject_rate
full_latency_p50/p95
fast_latency_p50/p95
scan_wall_latency_p50/p95
trade_false_reject_count
watch_false_reject_count
error_count_by_route
```

Nếu raw-empty rate thấp hoặc Tầng 2 không giảm wall-clock đáng kể, dừng ở Tầng 1; không tiếp tục refactor chỉ vì mục tiêu “đủ hai tầng”.

## 10. Checklist nghiệm thu cuối

- [ ] Công thức điểm và gate không đổi.
- [ ] Hai cờ tắt, backtest và detail cho kết quả baseline tương đương.
- [ ] Hai flag mặc định tắt trước release.
- [ ] Tầng 1 đã qua offline A/B, trade false reject bằng 0.
- [ ] Tầng 2 đã qua feasibility gate.
- [ ] Tầng 2 cache không chạy detector lặp và không rò dữ liệu.
- [ ] Survivor parity đạt.
- [ ] Structural reject không bị coi là data error.
- [ ] Không phát sinh order từ fast result.
- [ ] UI, ranking, AI target, persistence và snapshot pass.
- [ ] Benchmark cho thấy wall-clock cải thiện.
- [ ] Rollback từng tầng đã kiểm tra.
- [ ] `docs/scanner/scanner-flow.md` và tài liệu liên quan đã cập nhật sau khi runtime thay đổi.

## 11. Hướng dẫn cho AI thực hiện

AI thực hiện phải tuân thủ thứ tự sau:

1. Đọc `AGENTS.md`, tài liệu này, `docs/scanner/scanner-flow.md` và các file evidence trong mục 2.
2. Kiểm tra `git status`; không xóa hoặc reset thay đổi có sẵn.
3. Chỉ làm một bước mỗi lần; chạy cổng nghiệm thu của bước đó trước khi sang bước kế tiếp.
4. Dùng `apply_patch` cho sửa file.
5. Không sửa scorer/gate để làm prefilter pass.
6. Khi test fail, dừng ở bước hiện tại và sửa nguyên nhân; không bật flag để che lỗi.
7. Ghi lại file đã sửa, test đã chạy, số false reject và quyết định tiếp tục/dừng.
8. Nếu Bước 7 feasibility không đạt, kết thúc ở Tầng 1 và báo rõ lý do không triển khai Tầng 2.
