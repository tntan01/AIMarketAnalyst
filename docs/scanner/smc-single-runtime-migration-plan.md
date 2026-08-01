# Kế hoạch chuyển SMC về một runtime duy nhất

> **Trạng thái:** Kế hoạch triển khai — chưa thay đổi runtime  
> **Ngày lập:** 2026-08-01  
> **Vai trò:** Product Owner (PO)  
> **Phạm vi:** SMC scoring trong Scanner, Backtest, persistence, telemetry, test và tài liệu liên quan  
> **Quyết định sản phẩm:** Thuật toán đang mang tên v2 trở thành **SMC chuẩn duy nhất**. Không còn SMC v1, không còn SMC shadow, không còn runtime mode để lựa chọn scorer.

## 1. Mục tiêu và cách dùng tài liệu

Tài liệu này là runbook triển khai. Mỗi bước được thiết kế đủ nhỏ để một AI Coder có thể:

1. đọc đúng phạm vi;
2. sửa một nhóm trách nhiệm rõ ràng;
3. chạy kiểm thử được chỉ định;
4. xác nhận điều kiện hoàn thành trước khi sang bước tiếp theo.

Không được gộp nhiều bước nếu chưa chứng minh bước trước đã xanh. Không được phát hành khi còn bất kỳ đường thực thi nào gọi scorer v1 hoặc SMC shadow.

Mục tiêu cuối cùng:

```text
SMC context
    -> score_smc() đúng một lần cho mỗi symbol
    -> kết quả BUY/SELL chuẩn duy nhất
    -> compose scenario score
    -> selected zone / trade gate / risk / UI / persistence
```

Tên runtime chuẩn sau migration:

- Module: `core.smc_scorer`
- Hàm public: `score_smc()`
- Kết quả: một contract SMC duy nhất cho cả BUY và SELL
- Provenance thuật toán: `smc-v2` chỉ là metadata bất biến để nhận diện công thức, không phải mode và không phải đường gọi thứ hai

## 2. Kết luận rà soát code hiện tại

### 2.1. Mode v2 hiện vẫn chạy v1

Luồng thực tế hiện tại:

```text
score_scenario(BUY)  -> smc_quality_score() v1
score_scenario(SELL) -> smc_quality_score() v1
build_smc_phase0_diagnostics() -> score_smc_v2()
decision = shadow
apply_smc_score_override() -> ghi đè phần SMC v1 bằng v2
```

Các vị trí chính:

- `core/analysis_pipeline.py`: `_step_score_scenarios()` gọi `score_scenario()` cho BUY/SELL trước khi gọi diagnostics v2.
- `core/signal_engine.py`: `score_scenario()` gọi vô điều kiện `smc_quality_score()`; đây là scorer v1.
- `core/smc_scoring_contract.py`: mode `v2` vẫn có `shadow_enabled=True`, đặt output v2 vào nhánh `shadow` rồi chọn nhánh này làm `decision`.
- `core/signal_engine.py`: `apply_smc_score_override()` ghi đè phần SMC của tổng điểm đã được tạo từ đường v1.

Do đó, chỉ xóa setting hoặc đổi default không đáp ứng yêu cầu.

### 2.2. Có hai khái niệm shadow khác nhau

Phải xóa:

- SMC scorer shadow dùng để so sánh v1/v2.
- SMC event `SMC_SHADOW_COMPARISON`.
- Các field `legacy`, `active`, `shadow`, `comparison`, `shadow_status`, `policy` trong contract SMC.
- Các metric direction/zone/score delta của SMC v1/v2.

Phải giữ:

- Scanner rollout stage `SHADOW`.
- `SHADOW_MODE_ORDER_SUPPRESSED`.
- Generic Scanner `SHADOW_DECISION_COMPARISON`.
- Generic Scanner release gate, kill switch, canary và rollback deployment.
- Các cơ chế shadow của Macro hoặc subsystem khác.

Scanner rollout `SHADOW` là lớp an toàn gửi lệnh, không phải SMC scorer shadow. Không được global replace hoặc global delete từ khóa `shadow` trên toàn repository.

### 2.3. Phạm vi ảnh hưởng

Rà soát tĩnh tìm thấy ít nhất 46 file có tham chiếu trực tiếp tới SMC mode/version/shadow, chưa tính toàn bộ docs và ảnh baseline UI.

| Nhóm | File trọng tâm | Tác động |
|---|---|---|
| Runtime scoring | `core/signal_engine.py`, `core/analysis_pipeline.py`, `core/smc_scorer_v2.py`, `core/smc_scoring_contract.py` | Loại bỏ v1 và router shadow; gọi SMC một lần |
| Consumer/fast path | `core/smc_consumer_contract.py`, `core/smc_prefilter.py` | Một contract và một kết quả được tái sử dụng |
| Domain model/context | `core/smc_models.py`, `core/smc_context.py`, `core/smc_confluence.py` | Bỏ score/selector/lifecycle alias chỉ phục vụ v1 |
| Scanner plumbing | `core/scanner.py`, `core/analysis_engine.py`, `controllers/scanner_controller.py`, `workers/scanner_worker.py` | Bỏ mode khỏi request và call chain |
| Settings/UI | `config/settings.py`, `services/settings_service.py`, `ui/screens/settings_screen.py`, `ui/screens/scanner_screen.py` | Bỏ setting, parser và selector SMC mode |
| Telemetry/rollout | `core/scanner_observability.py`, `core/scanner_rollout.py`, `services/scanner_rollout_service.py` | Bỏ riêng SMC comparison; giữ Scanner shadow |
| Backtest | `core/system_backtest_engine.py`, `core/backtest_config.py`, `core/backtest_config_validation.py`, `core/scanner_strategy_router.py` | Bỏ runtime mode; bump schema và revalidate |
| Persistence | `services/journal_models.py`, `services/journal_converters.py`, `data/migrations/009_add_scoring_provenance.sql` | Ngừng ghi mode; vẫn đọc dữ liệu lịch sử |
| Offline tools | `core/smc_validation.py`, `scripts/run_smc_validation.py`, `scripts/compare_scanner_fast_path.py`, `scripts/tier2_feasibility_gate.py` | Chuyển sang SMC-only hoặc retire |
| Tests/fixtures | `tests/test_smc_*`, Scanner integration/observability/backtest tests, `tests/fixtures/smc_*`, fast-path fixtures | Xóa ma trận legacy/shadow, thêm golden SMC chuẩn |

## 3. Contract đích bắt buộc

### 3.1. Runtime API

Chỉ tồn tại một API public:

```python
score_smc(smc_context, *, precomputed=None) -> SmcScoringResult
```

Tên chính xác của tham số có thể được điều chỉnh theo code style, nhưng phải giữ các điều kiện:

- Không có tham số `mode`.
- Không có `legacy_score`.
- Không có `shadow_enabled`.
- Không có wrapper `score_smc_v2()` sau khi migration hoàn tất.
- Một invocation trả đủ kết quả BUY và SELL.
- Kết quả Tier-1 đã tính phải được truyền/tái sử dụng, không gọi scorer lần hai.

### 3.2. Output contract

Contract mục tiêu tối thiểu:

```json
{
  "contract_version": "smc-scoring-canonical-2026-08",
  "scoring_version": "smc-v2",
  "sides": {
    "buy": {},
    "sell": {}
  }
}
```

Lưu ý:

- `contract_version` là định danh schema của cấu trúc dữ liệu mới, không phải tên một scorer.
- `scoring_version="smc-v2"` là provenance của công thức hiện hành; không cho phép chọn scorer.
- Không nhân đôi cùng một side payload dưới các key `shadow` và `decision`.
- `smc_consumer` chỉ tồn tại một lần. Nếu được nhúng trong `smc_scoring`, không ghi thêm một bản giống hệt ở top-level.

### 3.3. Failure contract

- Thiếu dữ liệu hợp lệ: trả trạng thái no-zone/insufficient-data theo contract, không ném lỗi không kiểm soát.
- Scorer exception hoặc contract sai: kết quả phân tích phải bị blocked/no-trade.
- Reason code đề xuất: `SMC_SCORING_ERROR`.
- Không thử gọi v1.
- Không thử gọi lại SMC ở full route nếu Tier-1 đã ghi nhận scorer exception.

### 3.4. Tương thích dữ liệu lịch sử

- Không xóa migration SQL đã áp dụng.
- Không xóa journal, logs hoặc snapshots cũ.
- Reader được phép bỏ qua field thừa `legacy`, `shadow`, `comparison` trong dữ liệu cũ.
- Reader không được thực thi scorer v1 hoặc biến dữ liệu v1 thành đầu vào quyết định giao dịch mới.
- Source runtime không cần chứa literal `smc-v1`; version không phải `smc-v2` được coi là historical/unsupported một cách tổng quát.

## 4. Quy tắc triển khai

1. Mỗi bước phải bắt đầu bằng `git status --short` và không được sửa file ngoài phạm vi bước.
2. Thay đổi hiện có ở `config/interest_rates.json` thuộc người dùng; không sửa, format hoặc revert file này.
3. Mỗi bước phải chạy targeted tests trước khi chuyển trạng thái hoàn thành.
4. Không xóa v1 trước khi đã có golden test khóa kết quả cuối của mode v2 hiện tại.
5. Không đổi hằng version của raw zone một cách cơ học; raw candidate không được gắn nhãn là đã được scorer v2 đánh giá.
6. Không xóa `smc_consumer` nếu risk engine, scanner detail hoặc trade gate vẫn đang đọc selected zone từ contract đó.
7. Không dùng runtime feature flag để giữ v1 làm rollback.
8. Rollback sản phẩm dùng kill switch, Scanner rollout `SHADOW` và artifact phát hành trước.
9. Mọi commit sau bước cuối phải vượt qua static forbidden-symbol gate.

## 5. Kế hoạch triển khai từng bước

### Bước 00 — Xác nhận workspace và tạo điểm khôi phục

**Mục tiêu:** Bảo vệ thay đổi của người dùng và ghi nhận trạng thái trước migration.

**Thao tác:**

1. Chạy `git status --short`.
2. Ghi lại các file dirty có trước khi bắt đầu.
3. Xác nhận `config/interest_rates.json` không thuộc phạm vi.
4. Nếu quy trình dự án dùng branch, tạo branch với prefix `codex/`; không tự commit nếu chưa được yêu cầu.

**Kiểm tra:** `git diff -- config/interest_rates.json` không thay đổi do tác vụ này.

**Hoàn thành khi:** Có danh sách rõ file người dùng đang sửa và không file nào bị ghi đè.

### Bước 01 — Chạy baseline kiểm thử hiện tại

**Mục tiêu:** Có mốc xanh trước khi sửa runtime.

**Thao tác:** Chạy:

```powershell
python -m pytest -q tests/test_smc_scorer_v2.py tests/test_smc_scoring_phase0.py tests/test_smc_consumer_phase6.py tests/test_smc_prefilter.py tests/test_analysis_pipeline_integration.py tests/test_scanner_observability.py tests/test_smc_phase8_rollout.py tests/test_backtest_config_validation.py
```

Ghi số test pass/fail, thời gian và warning vào log triển khai. Baseline tại thời điểm lập kế hoạch là 98 test pass.

**Hoàn thành khi:** Baseline xanh hoặc mọi lỗi có trước được ghi rõ và được PO chấp nhận.

### Bước 02 — Tạo golden fixture của kết quả SMC chuẩn hiện tại

**Mục tiêu:** Khóa hành vi cuối cùng đang được mode v2 sử dụng trước khi xóa v1.

**File:** Tạo fixture mới dưới `tests/fixtures/smc_canonical/` và test characterization riêng.

**Case tối thiểu:**

- BUY có selected zone.
- SELL có selected zone.
- No-zone.
- FVG H1-only.
- Order block.
- Broken/stale zone.
- CHOCH cap.
- Thiếu dữ liệu nhưng hợp lệ.

**Field phải khóa:** SMC side score, selected zone ID/type/timeframe, score breakdown, scenario score cuối, direction, trade gate, candidate decision và order payload.

**Field được bỏ qua:** timestamp, scan ID, latency và giá trị không xác định theo thời gian.

**Hoàn thành khi:** Golden test pass trên code chưa refactor và không phụ thuộc trực tiếp vào payload `legacy/shadow/comparison`.

### Bước 03 — Khóa lớp an toàn Scanner rollout

**Mục tiêu:** Ngăn việc xóa nhầm generic Scanner shadow.

**File:** `tests/test_scanner_phase8_rollout.py`, `tests/test_scanner_observability.py`.

**Thêm/giữ assertions:**

- Stage `SHADOW` chặn order với `SHADOW_MODE_ORDER_SUPPRESSED`.
- `SHADOW_DECISION_COMPARISON` vẫn được emit khi generic comparison bật.
- Kill switch vẫn ưu tiên chặn execution.
- Release gate vẫn dùng generic sample/disagreement.

**Hoàn thành khi:** Có test đỏ nếu ai xóa generic Scanner shadow.

### Bước 04 — Định nghĩa kết quả SMC chuẩn duy nhất

**Mục tiêu:** Tạo contract đích trước khi đổi orchestration.

**File:** `core/smc_models.py` hoặc một module contract nhỏ có tên trung tính, không chứa `v1`, `v2`, `legacy` hoặc `shadow` trong tên public.

**Thao tác:**

1. Định nghĩa result chứa `contract_version`, `scoring_version` và `sides`.
2. Mỗi side chứa score, selected zone và breakdown cần cho consumer/risk/UI.
3. Thêm serializer/deserializer trung tính.
4. Parser phải bỏ qua key lạ để đọc snapshot cũ.

**Kiểm tra:** Unit test round-trip result mới; old payload có field thừa vẫn đọc được mà không chọn nhánh v1.

**Hoàn thành khi:** Contract mới đứng độc lập, chưa cần thay runtime, và không có mode selector.

### Bước 05 — Đổi scorer hiện tại thành module SMC canonical

**Mục tiêu:** Xóa tên public mang hậu tố v2 nhưng giữ nguyên công thức.

**File:** `core/smc_scorer_v2.py` -> `core/smc_scorer.py`, cùng các import trực tiếp.

**Thao tác:**

1. Chuyển implementation hiện tại sang module `core.smc_scorer`.
2. Đổi public function `score_smc_v2()` thành `score_smc()`.
3. Đổi tên type/helper public có hậu tố `_v2` nếu chúng không phải provenance dữ liệu.
4. Giữ nguyên công thức và threshold; không tối ưu trong bước này.
5. Không tạo compatibility wrapper runtime mang tên `score_smc_v2`.

**Kiểm tra:** Chuyển direct unit tests trong `tests/test_smc_scorer_v2.py` sang API canonical và xác nhận toàn bộ vector công thức vẫn pass.

**Hoàn thành khi:** Có một scorer canonical với output bằng implementation v2 cũ.

### Bước 06 — Chuẩn hóa version provenance

**Mục tiêu:** Chỉ còn một identity của scorer hiện hành.

**File:** `core/smc_versions.py`, `core/scoring_provenance.py`.

**Thao tác:**

1. Chỉ giữ một hằng public, ví dụ `SMC_SCORER_VERSION = "smc-v2"`.
2. Xóa `SMC_SCORER_V2_VERSION`, baseline v1 và shadow-only version constants.
3. `build_scoring_provenance()` không nhận mode và luôn trả scorer version canonical.
4. Chưa đổi default version của raw zone nếu raw zone chưa được tách khỏi evaluated zone; việc đó nằm ở Bước 24.

**Kiểm tra:** Provenance unit test không truyền mode và chỉ có một scorer version.

**Hoàn thành khi:** Version là metadata, không thể dùng để route sang một scorer khác.

### Bước 07 — Tách composition khỏi scorer v1

**Mục tiêu:** Giữ nguyên công thức tổng điểm trong khi loại dependency vào `smc_quality_score()`.

**File:** `core/signal_engine.py`.

**Thao tác:**

1. Tách phần non-SMC của `score_scenario()` thành hàm composition rõ ràng.
2. Hàm composition nhận SMC side score/breakdown đã tính sẵn.
3. Chuyển nguyên vẹn regime weight, CHOCH cap, penalty cleanup và score clamping.
4. Chưa xóa hàm v1 trong bước này; chỉ đảm bảo đường mới có thể tạo cùng kết quả cuối.

**Kiểm tra:** Unit test so sánh output composition mới với output cuối mode v2 trong golden fixture.

**Hoàn thành khi:** Có thể tính final scenario score mà không cần gọi `smc_quality_score()`.

### Bước 08 — Cho pipeline gọi SMC canonical đúng một lần

**Mục tiêu:** Chuyển đường quyết định chính sang SMC duy nhất.

**File:** `core/analysis_pipeline.py`.

**Thao tác:**

1. Sau khi có SMC context, gọi `score_smc()` một lần để nhận cả BUY/SELL.
2. Dùng side result tương ứng để compose BUY và SELL.
3. Tạo consumer từ cùng result.
4. Không gọi `build_smc_phase0_diagnostics()`.
5. Không gọi `apply_smc_score_override()`.
6. Không đọc `decision`, `active` hoặc `shadow`.

**Kiểm tra:** Golden parity test phải pass. Dùng spy/mock để xác nhận `score_smc()` được gọi đúng một lần mỗi symbol.

**Hoàn thành khi:** Full analysis không đi qua scorer v1 hoặc shadow router.

### Bước 09 — Tái sử dụng kết quả Tier-1 prefilter

**Mục tiêu:** Không chấm SMC hai lần với symbol sống sót qua fast path.

**File:** `core/smc_prefilter.py`, `core/analysis_pipeline.py`.

**Thao tác:**

1. Xóa tham số mode và policy resolution khỏi prefilter.
2. Prefilter gọi `score_smc()` và trả result canonical khi cần.
3. Full pipeline nhận `precomputed_smc` và tái sử dụng nguyên object/result.
4. Không serialize rồi deserialize chỉ để truyền nội bộ.

**Kiểm tra:** Integration test cho Tier-1 survivor xác nhận tổng call count vẫn là một.

**Hoàn thành khi:** Fast path và full route cùng dùng một scorer và một kết quả.

### Bước 10 — Định nghĩa fail-closed khi SMC lỗi

**Mục tiêu:** Không hồi sinh v1 dưới dạng fallback.

**File:** `core/smc_prefilter.py`, `core/analysis_pipeline.py`, `controllers/scanner_controller.py`.

**Thao tác:**

1. Phân biệt insufficient-data hợp lệ với scorer exception.

2. Scorer exception tạo blocked analysis với `SMC_SCORING_ERROR`.
3. Không retry bằng full route nếu prefilter đã gặp scorer exception.
4. Đảm bảo blocked row không thể tạo candidate hoặc order.

**Kiểm tra:** Test inject exception và assert không có scorer thứ hai, không có candidate, không có order.

**Hoàn thành khi:** Mọi lỗi scorer đều fail-closed và không có fallback.

### Bước 11 — Đơn giản hóa SMC consumer

**Mục tiêu:** Consumer chỉ đọc một result canonical.

**File:** `core/smc_consumer_contract.py`.

**Thao tác:**

1. Bỏ `resolve_smc_scoring_policy()`.
2. Bỏ active/shadow selection.
3. Xóa toàn bộ field `shadow_selected_zone*`.
4. Giữ selected zone, side score và breakdown mà risk engine/UI thực sự dùng.
5. Bump consumer contract version nếu shape thay đổi.

**Kiểm tra:** `tests/test_smc_consumer_phase6.py` dùng một result và xác nhận BUY/SELL selection.

**Hoàn thành khi:** Consumer không biết khái niệm mode hoặc shadow.

### Bước 12 — Xóa SMC scoring router cũ

**Mục tiêu:** Xóa điểm tập trung của legacy/shadow routing.

**File:** `core/smc_scoring_contract.py` và mọi import.

**Thao tác:**

1. Di chuyển phần contract thực sự cần thiết sang model/result canonical.
2. Xóa constants `SMC_MODE_LEGACY`, `SMC_MODE_SHADOW`, `SMC_MODE_V2`.
3. Xóa normalizer/fallback mode.
4. Xóa diagnostics builder và comparison builder.
5. Xóa file khi không còn import.

**Kiểm tra:** `rg -n "smc_scoring_contract|SMC_MODE_" core controllers services config ui scripts tests` không còn runtime import; test chỉ được tham chiếu nếu đang bị xóa trong cùng bước.

**Hoàn thành khi:** Không còn router có khả năng chọn v1/shadow.

### Bước 13 — Xóa scorer v1 và override path

**Mục tiêu:** Loại bỏ code thực thi v1 khỏi chương trình.

**File:** `core/signal_engine.py`.

**Xóa:**

- `smc_quality_score()`.
- `_best_smc_zone()` phục vụ scorer v1.
- `apply_smc_score_override()` sau khi composition mới đã thay thế đầy đủ.
- Import/constants/helper chỉ còn được các hàm trên dùng.

**Kiểm tra:** Golden tests và signal engine tests pass. `rg -n "smc_quality_score|apply_smc_score_override|_best_smc_zone" core controllers services` không có kết quả.

**Hoàn thành khi:** Source runtime không chứa thuật toán chấm điểm v1.

### Bước 14 — Thiết lập một nguồn selected zone duy nhất

**Mục tiêu:** Không còn zone selector v1 chạy ngầm sau khi scorer đã được thay.

**File:** `core/smc_context.py`, `core/analysis_pipeline.py`, `core/trade_gate_engine.py`, `core/risk_engine.py`.

**Thao tác:**

1. Tách phần structural flags của `extract_smc_trade_flags()` khỏi phần tự chọn zone.
2. Giữ CHOCH, displacement, sweep và các cờ cấu trúc cần thiết.
3. Xóa `_find_best_zone_for_direction()`/`get_preferred_zone()` cũ khi không còn caller.
4. Selected zone luôn lấy từ SMC result/consumer.
5. Khi selected zone canonical thiếu relevance bắt buộc, trade gate phải fail-closed thay vì dùng ngoại lệ legacy.

**Kiểm tra:** Test BUY/SELL/no-zone/broken-zone xác nhận selected zone ID khớp golden và gate không đổi với dữ liệu hợp lệ.

**Hoàn thành khi:** Chỉ scorer canonical có quyền chọn zone cho quyết định giao dịch.

### Bước 15 — Xóa setting SMC mode

**Mục tiêu:** Người dùng và file cấu hình không thể chọn lại v1.

**File:** `config/settings.py`, `services/settings_service.py`.

**Thao tác:**

1. Xóa `FeatureFlagSettings.smc_scoring_mode`.
2. Xóa parser cho `legacy`, `shadow`, `v2`.
3. Settings JSON cũ có key này phải được bỏ qua.
4. Khi save lần tiếp theo, key cũ không được ghi lại.
5. Không thêm environment variable thay thế.

**Kiểm tra:** Test load settings cũ với `legacy`, `shadow`, `v2`, invalid và missing; tất cả tạo cùng runtime SMC canonical. Test round-trip xác nhận key biến mất.

**Hoàn thành khi:** Không có config path nào kích hoạt scorer khác.

### Bước 16 — Xóa SMC mode khỏi UI

**Mục tiêu:** UI chỉ thể hiện một SMC.

**File:** `ui/screens/settings_screen.py`, `ui/screens/scanner_screen.py`.

**Thao tác:**

1. Xóa selector “SMC scoring mode”, tooltip, load/save binding.
2. Scanner screen không đọc hoặc truyền SMC mode.
3. Giữ Scanner rollout controls.
4. Đổi label `shadow_compare_enabled` thành “So sánh Scanner V1/V2” hoặc tên tương đương để phân biệt subsystem.

**Kiểm tra:** UI test/screenshot baseline; mở Settings không còn SMC mode nhưng rollout stage và generic comparison vẫn hiện.

**Hoàn thành khi:** Không có control SMC v1/v2/shadow trên UI.

### Bước 17 — Xóa mode khỏi Scanner call chain

**Mục tiêu:** Signature runtime không còn khái niệm lựa chọn scorer.

**File:** `core/scanner.py`, `core/analysis_engine.py`, `controllers/scanner_controller.py`, `workers/scanner_worker.py` và call sites.

**Thao tác:**

1. Xóa `smc_scoring_mode` khỏi `ScannerRequest` và kết quả runtime mới.
2. Xóa tham số khỏi `analyze_symbol()` và `AnalysisPipeline`.
3. Xóa propagation từ UI -> worker -> controller -> engine -> pipeline.
4. Giữ `smc_scorer_version` trong provenance nếu consumer cần audit.

**Kiểm tra:** Scanner integration tests và static search `smc_scoring_mode` trong các thư mục runtime.

**Hoàn thành khi:** Không có mode trong Scanner API hoặc call chain.

### Bước 18 — Đơn giản hóa observability và provenance

**Mục tiêu:** Log mới mô tả SMC canonical, không mô tả quyết định shadow.

**File:** `core/scanner_observability.py`, `core/scoring_provenance.py`.

**Thao tác:**

1. Bỏ policy lookup và mode fields khỏi event mới.
2. Ghi một scorer version và contract version.
3. Không ghi `decision_source=shadow`.
4. Reader/log viewer phải chịu được event lịch sử còn field cũ.

**Kiểm tra:** Observability tests assert event mới không chứa SMC legacy/shadow keys.

**Hoàn thành khi:** Telemetry mới chỉ có SMC canonical provenance.

### Bước 19 — Xóa SMC shadow event

**Mục tiêu:** Dừng hoàn toàn telemetry so sánh v1/v2.

**File:** `controllers/scanner_controller.py`.

**Xóa:**

- `_compact_smc_shadow_payload()`.
- Schema `smc-shadow-summary-v1`.
- Emit path `SMC_SHADOW_COMPARISON`.
- Helper/import chỉ còn phục vụ event này.

**Kiểm tra:** Test scan xác nhận không phát sinh event `SMC_SHADOW_COMPARISON`; generic `SHADOW_DECISION_COMPARISON` vẫn phát sinh khi được bật.

**Hoàn thành khi:** Không còn SMC comparison event trong code runtime.

### Bước 20 — Tách SMC metrics khỏi generic Scanner rollout

**Mục tiêu:** Giữ lớp rollout an toàn nhưng không chạy/đo v1 SMC.

**File:** `core/scanner_rollout.py`, `services/scanner_rollout_service.py`.

**Thao tác:**

1. Trong `build_shadow_report()`, giữ status/side/trade comparison của Scanner Candidate Engine.
2. Xóa phần đọc `analysis_result.smc_scoring.comparison`.
3. Xóa `smc_direction_changes`, `smc_zone_changes`, `smc_score_delta_*`.
4. Nếu cần health metric, tạo metric độc lập như `smc_no_zone_rate`; không gọi là shadow comparison.
5. Bump `ROLLOUT_METRICS_VERSION`.
6. Metrics cũ được archive theo cơ chế `legacy_metrics`, không đưa vào gate mới.

**Kiểm tra:** Generic rollout tests pass; metrics mới không chứa SMC comparison counters.

**Hoàn thành khi:** Scanner shadow còn nguyên nhưng không tham chiếu SMC v1/v2 comparison.

### Bước 21 — Cập nhật rollback drill

**Mục tiêu:** Rollback không phụ thuộc v1.

**File:** `core/scanner_rollout.py`, `scripts/run_scanner_rollback_drill.py`.

**Thao tác:**

1. Xóa kiểm tra “rollback SMC về legacy/v1”.
2. Drill phải xác nhận kill switch chặn order.
3. Drill phải xác nhận Scanner stage `SHADOW` chặn order.
4. Runbook deployment phải trỏ tới artifact phát hành trước.

**Kiểm tra:** Rollback drill pass mà không import scorer v1.

**Hoàn thành khi:** Có rollback vận hành đầy đủ dù code hiện tại chỉ có SMC canonical.

### Bước 22 — Xóa mode khỏi Backtest runtime

**Mục tiêu:** Backtest và live dùng cùng một SMC.

**File:** `core/system_backtest_engine.py`, controller/call sites liên quan.

**Thao tác:**

1. Xóa `smc_scoring_mode` khỏi `BacktestRequest`.
2. Xóa propagation vào `analyze_symbol()`.
3. Kết quả trade mới chỉ ghi scorer version canonical.
4. Backtest gặp scorer error phải fail-closed theo cùng contract live.

**Kiểm tra:** Backtest/live parity trên golden corpus; request không còn mode.

**Hoàn thành khi:** Không thể chạy backtest bằng v1 hoặc shadow.

### Bước 23 — Bump Backtest config schema và revalidation

**Mục tiêu:** Không giữ mode giả trong fingerprint/config mới.

**File:** `core/backtest_config.py`, `core/backtest_config_validation.py`, `core/scanner_strategy_router.py`.

**Thao tác:**

1. Bump `BACKTEST_CONFIG_SCHEMA_VERSION` từ 8 lên version kế tiếp.
2. Xóa `smc_scoring_mode` khỏi schema, ID và fingerprint.
3. Vẫn yêu cầu `smc_scorer_version == "smc-v2"` cho config mới.
4. Config schema cũ phải chuyển DRAFT/invalid và yêu cầu revalidation; không tự coi là hợp lệ.
5. Kiểm kê config đang enabled trên môi trường phát hành trước deployment.

**Kiểm tra:** Validation tests cho config mới pass; config cũ fail-closed với reason rõ ràng; strategy router không route v1.

**Hoàn thành khi:** Mọi Backtest config được dùng cho Scanner đều chứng minh chạy SMC canonical.

### Bước 24 — Dọn domain model và producer legacy

**Mục tiêu:** Xóa dữ liệu/logic v1 còn chạy ngầm trong zone enrichment.

**File:** `core/smc_models.py`, `core/smc_context.py`, `core/smc_confluence.py`, `core/risk_engine.py`.

**Thao tác theo thứ tự:**

1. Tách raw zone candidate khỏi evaluated SMC zone nếu hiện cùng model.
2. Raw candidate chỉ chứa identity, geometry, timeframe và lifecycle canonical; không mang scorer version/score giả.
3. Evaluated zone nhận score/version từ `score_smc()`.
4. Xóa `legacy_test_count`, `legacy_mitigated`, `legacy_stale`, `legacy_broken`, `legacy_liquidity_sweep` khỏi record mới.
5. Xóa scalar confluence chỉ phục vụ v1 nếu không còn consumer.
6. Xóa legacy zone score producer `zone_quality_score()` nếu không còn caller.
7. Giữ `calculate_effective_zone_score()` chỉ khi đã xác nhận đây là diagnostic/risk signal độc lập, không phải scorer v1 trá hình.
8. Đổi parser `from_legacy_dict` thành parser trung tính hoặc cô lập ở historical reader; sau khi call sites được chuyển, xóa public legacy adapter khỏi runtime model.

**Kiểm tra:** Domain/lifecycle/sweep/risk tests; static caller search trước khi xóa từng helper; record mới không có legacy fields.

**Hoàn thành khi:** Runtime domain model không sản xuất hoặc dùng score/lifecycle alias v1.

### Bước 25 — Cập nhật persistence và historical reader

**Mục tiêu:** Dữ liệu mới sạch nhưng dữ liệu cũ vẫn mở được.

**File:** `services/journal_models.py`, `services/journal_converters.py`, snapshot readers và migrations liên quan.

**Thao tác:**

1. Ngừng ghi `smc_scoring_mode` cho record mới.
2. Giữ `smc_scorer_version`, selected zone metadata và score breakdown cần audit.
3. Không xóa `data/migrations/009_add_scoring_provenance.sql`.
4. Không drop cột SQLite trong release này.
5. Converter chỉ map field dataclass hiện hành và bỏ qua cột dư.
6. Snapshot cũ có `legacy/shadow/comparison` được đọc như historical payload và không tham gia quyết định mới.
7. Snapshot mới chỉ chứa một SMC result.

**Kiểm tra:** Round-trip journal mới; mở journal/snapshot cũ; assert new write không có mode/shadow.

**Hoàn thành khi:** Không mất dữ liệu lịch sử và không có đường tái kích hoạt v1.

### Bước 26 — Chuyển offline validation sang SMC-only

**Mục tiêu:** Công cụ nội bộ không giữ v1 như baseline executable.

**File:** `core/smc_validation.py`, `scripts/run_smc_validation.py`.

**Thao tác:**

1. Xóa imports và replay path của scorer v1.
2. Xóa metrics chênh lệch legacy-vs-v2.
3. Giữ calibration, out-of-sample, walk-forward và absolute quality checks hữu ích cho SMC canonical.
4. Nếu module không còn giá trị sau khi bỏ comparison, retire module và script cùng tests trong một bước có kiểm chứng caller.

**Kiểm tra:** Validation script chạy trên golden/current dataset mà không import v1.

**Hoàn thành khi:** Offline tooling cũng chỉ gọi `score_smc()`.

### Bước 27 — Cập nhật fast-path và feasibility scripts

**Mục tiêu:** Không còn ma trận chạy `legacy/shadow/v2` ngoài runtime chính.

**File:** `scripts/compare_scanner_fast_path.py`, `scripts/tier2_feasibility_gate.py`, `scripts/backfill_zone_metadata.py` và reports sinh từ chúng.

**Thao tác:**

1. Xóa input/loop theo SMC mode.
2. Chỉ dùng SMC canonical result.
3. Rewrite hoặc retire `backfill_zone_metadata.py` nếu còn gọi legacy zone score.
4. Regenerate feasibility reports không chứa mode legacy/shadow.

**Kiểm tra:** Scripts chạy thành công và `rg` không thấy SMC mode trong scripts.

**Hoàn thành khi:** Không có công cụ vận hành nào có thể gọi v1.

### Bước 28 — Viết lại tests và fixtures phụ thuộc v1/shadow

**Mục tiêu:** Test suite khóa kiến trúc mới thay vì khóa hành vi shadow cũ.

**Xóa/viết lại trọng tâm:**

- `tests/test_smc_scoring_phase0.py`: thay mode matrix bằng canonical contract, migration và golden parity.
- `tests/test_smc_scorer_v2.py`: đổi tên file/test về scorer canonical; bỏ shadow promotion tests.
- `tests/test_smc_consumer_phase6.py`: một result/selected zone.
- `tests/test_smc_prefilter.py`: không parametrized legacy/shadow.
- `tests/test_smc_phase7_validation.py`: SMC-only validation hoặc retire.
- `tests/test_smc_phase8_rollout.py`: bỏ SMC comparison/rollback-v1; giữ generic rollout assertions ở suite phù hợp.
- `tests/test_scanner_observability.py`: assert không emit `SMC_SHADOW_COMPARISON`.
- Fast-path corpus/oracles: xóa `mode_legacy`, `mode_shadow`.
- `tests/fixtures/smc_phase0_replay.json`: thay bằng canonical golden fixture.

**Compatibility tests:** Chỉ giữ test đọc historical snapshot/journal; đặt tên rõ `historical` và không import scorer v1.

**Hoàn thành khi:** Không test nào coi v1 là runtime option và targeted suite xanh.

### Bước 29 — Thêm static forbidden-symbol gate

**Mục tiêu:** Ngăn v1/shadow SMC quay lại qua refactor sau này.

**Phạm vi gate:** `core`, `controllers`, `services`, `config`, `ui`, `workers`, `scripts`.

**Danh sách cấm tối thiểu:**

```text
SMC_MODE_LEGACY
SMC_MODE_SHADOW
SMC_SHADOW_BASELINE_VERSION
SMC_V2_SHADOW_ONLY
SMC_SHADOW_COMPARISON
smc_quality_score
score_smc_v2
smc_scorer_v2
smc_scoring_mode
smc-v1
```

**Lệnh kiểm tra thủ công:**

```powershell
rg -n "SMC_MODE_LEGACY|SMC_MODE_SHADOW|SMC_SHADOW_BASELINE_VERSION|SMC_V2_SHADOW_ONLY|SMC_SHADOW_COMPARISON|smc_quality_score|score_smc_v2|smc_scorer_v2|smc_scoring_mode|smc-v1" core controllers services config ui workers scripts
```

Kết quả mong đợi: không có match.

Thêm gate ngược để bảo vệ Scanner rollout:

```powershell
rg -n "ROLLOUT_SHADOW|SHADOW_MODE_ORDER_SUPPRESSED|SHADOW_DECISION_COMPARISON" core controllers services tests
```

Kết quả mong đợi: các symbol generic Scanner vẫn tồn tại và có tests.

**Hoàn thành khi:** Gate được tự động hóa trong test/CI và pass.

### Bước 30 — Cập nhật tài liệu runtime và UI baseline

**Mục tiêu:** Tài liệu không hướng dẫn người dùng chọn v1/shadow.

**File tối thiểu:**

- `docs/scanner/scanner-flow.md`.
- `docs/scanner/technical-scoring-architecture.md`.
- `docs/architecture/runtime-status.md`.
- `docs/scanner/scanner-scoring-review.md`.
- `docs/scanner/smc-scoring-plan.md`.
- `docs/ui/screen_design.md`.
- Các screenshot/manifest Settings bị ảnh hưởng.

**Thao tác:**

1. Runtime docs gọi scorer là `SMC`, không phải SMC v1/v2 mode.
2. Tài liệu lịch sử về rollout v1/v2 được chuyển vào `docs/archive` hoặc gắn banner rõ không phải runtime contract.
3. Scanner rollout `SHADOW` được ghi rõ là Candidate Engine safety stage.
4. Regenerate Settings screenshots sau khi xóa selector.

**Hoàn thành khi:** Tìm kiếm trong docs hiện hành không cho thấy v1 là lựa chọn đang hỗ trợ.

### Bước 31 — Chạy regression đầy đủ

**Mục tiêu:** Xác minh thay đổi không ảnh hưởng chương trình đang chạy.

**Thứ tự kiểm tra:**

1. Static forbidden-symbol gate.
2. Direct SMC unit tests.
3. Golden parity tests.
4. Prefilter/full-route call-count tests.
5. Scanner integration và observability tests.
6. Generic Scanner rollout safety tests.
7. Backtest validation/router/system backtest tests.
8. Journal/snapshot historical compatibility tests.
9. Full suite:

```powershell
python -m pytest -q
```

10. PyInstaller build và startup smoke theo `packaging/build_windows.ps1`.

**Hoàn thành khi:** Tất cả test/build xanh; không có test bị skip chỉ để né lỗi migration.

### Bước 32 — Benchmark và kiểm tra artifact

**Mục tiêu:** Chứng minh việc bỏ dual-run không gây regression hiệu năng hoặc dữ liệu.

**Đo:**

- Số lần gọi scorer mỗi symbol: tối đa 1.
- p50/p95 analysis latency: không tăng so với baseline; kỳ vọng giảm.
- Kích thước snapshot mới: không còn payload nhân đôi `shadow/decision`.
- Error rate và blocked reason.
- No-zone rate.
- Candidate/order count không đổi ngoài case scorer error được fail-closed.

**Hoàn thành khi:** Không có regression ngoài ngưỡng đã được PO phê duyệt.

### Bước 33 — Phát hành có kiểm soát

**Mục tiêu:** Đưa SMC canonical vào production mà không dựa vào v1 rollback.

**Trước phát hành:**

1. Lưu artifact/build hiện tại để deployment rollback.
2. Backup settings và runtime DB.
3. Kiểm kê Backtest configs đang enabled và revalidate schema mới.
4. Chạy kill-switch/Scanner-SHADOW drill.

**Trong phát hành:**

1. Khởi động ở Scanner rollout `SHADOW` hoặc chế độ không gửi lệnh phù hợp với runbook.
2. Chạy smoke scan trên tập symbol chuẩn.
3. Xác nhận provenance SMC canonical và không có SMC shadow event.
4. Chuyển canary/production theo release gate Scanner hiện hành.

**Sau phát hành:** Theo dõi latency, SMC error, no-zone rate, blocked reason, candidate và order volume.

**Hoàn thành khi:** Production ổn định qua cửa sổ theo dõi được PO/QA quy định.

### Bước 34 — Rollback nếu có sự cố

**Mục tiêu:** Phục hồi dịch vụ mà không tái kích hoạt v1 trong build mới.

**Thứ tự:**

1. Bật kill switch.
2. Đưa Scanner rollout về `SHADOW` để chặn order.
3. Thu thập snapshot/log của lỗi.
4. Redeploy artifact phát hành trước.
5. Khôi phục settings backup nếu schema settings có vấn đề.
6. Không thêm lại feature flag v1 vào nhánh mới.

**Lưu ý:** Rollback artifact có thể là build cũ từng chứa dual-run; đó là biện pháp vận hành khẩn cấp. Nhánh phát triển hiện hành vẫn phải giữ invariant không có v1.

## 6. Definition of Done

Migration chỉ hoàn thành khi đồng thời thỏa tất cả điều kiện:

- Chỉ còn module `core.smc_scorer` và API `score_smc()` cho scoring SMC.
- Không còn production import/call tới scorer v1.
- Không còn runtime mode `legacy/shadow/v2` của SMC.
- Không còn SMC shadow router, comparison payload, metric hoặc event.
- Mỗi symbol được chấm SMC tối đa một lần; Tier-1 result được tái sử dụng.
- SMC exception fail-closed; không fallback, không retry sang đường khác.
- Selected zone cho quyết định giao dịch chỉ đến từ SMC canonical result.
- Settings/UI/Scanner/Backtest không nhận SMC mode.
- Record mới chỉ ghi một SMC result và scorer provenance canonical.
- Journal/snapshot cũ vẫn đọc được nhưng không thể kích hoạt v1.
- Generic Scanner rollout `SHADOW`, kill switch và order suppression vẫn hoạt động.
- Backtest config schema mới đã revalidate và fail-closed với config cũ.
- Static forbidden-symbol gate pass.
- Golden parity, full pytest, build và startup smoke pass.
- Tài liệu runtime và UI baseline đã cập nhật.

## 7. Thứ tự commit/PR đề xuất

Để review dễ và giảm rủi ro, chia thành các đơn vị sau:

1. **PR A — Characterization:** Bước 00–04, chỉ thêm baseline, golden và contract mới.
2. **PR B — Canonical runtime:** Bước 05–14, chuyển call chain và xóa executable v1/shadow.
3. **PR C — Config và contracts:** Bước 15–25, xóa mode xuyên tầng, migration Backtest/persistence/telemetry.
4. **PR D — Tooling và cleanup:** Bước 26–30, xóa fixtures/scripts/docs cũ và thêm static gate.
5. **PR E — Release evidence:** Bước 31–34, regression, build, benchmark và release record.

Không merge PR B nếu golden parity chưa xanh. Không phát hành sau PR B nếu PR C/D và toàn bộ Definition of Done chưa hoàn tất.

## 8. Ước lượng

| Giai đoạn | Ước lượng |
|---|---:|
| Baseline và golden characterization | 0,5–1 ngày |
| Canonical runtime và xóa executable v1 | 1,5–2 ngày |
| Config, telemetry, Backtest và persistence | 1,5–2 ngày |
| Domain cleanup, tools, tests và docs | 1,5–2 ngày |
| Full QA, build, benchmark và release | 1–2 ngày |
| **Tổng** | **6–9 ngày kỹ thuật + 1–2 ngày QA** |

Ước lượng giả định một kỹ sư thực hiện tuần tự. Có thể rút ngắn thời gian lịch khi chia độc lập phần runtime, persistence và test/docs, nhưng thứ tự dependency và các quality gate trong tài liệu này vẫn bắt buộc.
