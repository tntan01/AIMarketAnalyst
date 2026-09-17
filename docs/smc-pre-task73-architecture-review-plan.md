# Kế hoạch tổng quát rà soát kiến trúc và chỉnh cấu trúc trước task73

**Ngày:** 2026-09-14.

**Trạng thái:** KẾ HOẠCH TỔNG QUÁT — chưa bắt đầu rà soát hoặc refactor.

**Phạm vi:** một đợt có giới hạn trước task73; không refactor toàn repo, không đổi yêu cầu SMC đã được duyệt.

Nguồn tham chiếu: [kế hoạch triển khai](plans/smc-implementation-plan.md), [thiết kế SMC](plans/smc-scoring-upgrade-plan.md), [tiến độ](plans/smc-implementation-progress.md) và [nghiệm thu task72](plans/smc-task-72-response.md).

## 1. Mục tiêu

- Xác định phần khiến coder khó hiểu, sửa chồng chéo hoặc bỏ sót caller.
- Chỉ chỉnh cấu trúc cần thiết cho task73–144.
- Giữ nguyên hành vi đã nghiệm thu tại task72.
- Chuẩn bị cách giao 9 lô còn lại, không quay lại giao từng microtask.

Không lấy số dòng làm tiêu chí duy nhất. File lớn chỉ cần tách khi chứa các trách nhiệm độc lập, khó kiểm chứng hoặc thường phải sửa cùng nhiều nơi. Chưa chốt cấu trúc mới chỉ từ độ dài file.

## 2. Ba lô thực hiện và hai điểm duyệt

| Lô / điểm duyệt | Công việc | Đầu ra | Giới hạn |
|---|---|---|---|
| **Lô 1 — Rà kiến trúc và chốt phạm vi** | Kiểm trạng thái repo hiện tại; lập bản đồ module/caller; rà trách nhiệm, phụ thuộc, logic trùng và nơi chuyển đổi canonical/legacy | Danh sách **sửa ngay / sửa trong lô tương ứng / hoãn**, kèm bằng chứng và thiết kế đích tối thiểu | Chưa sửa code |
| **Duyệt phạm vi** | Chọn chính xác phần được refactor, interface cần giữ và cách kiểm chứng | Phạm vi đóng, tiêu chí hoàn thành rõ | Không duyệt danh sách chung chung “cải thiện kiến trúc” |
| **Lô 2 — Refactor có kiểm soát** | Tách hoặc gom các trách nhiệm đã duyệt; giữ interface tương thích khi cần; cập nhật import và test liên quan | Code dễ sửa hơn, hành vi không đổi, có bằng chứng trước–sau | Không thêm tính năng hoặc sửa thuật toán SMC |
| **Lô 3 — Nghiệm thu và chuẩn bị tiếp tục** | Kiểm đường chạy, regression, dependency và tài liệu; cập nhật kế hoạch task73–144 thành các lô bàn giao | Bản bàn giao cấu trúc mới, kế hoạch 9 lô và prompt lô đầu | Không tự triển khai task73 |
| **Duyệt kết thúc** | Xác nhận refactor đạt và đủ điều kiện tiếp tục | Quyết định cho phép bắt đầu lô73–79 | Không yêu cầu dọn mọi tồn tại |

Coder được tự chia bước nhỏ bên trong mỗi lô. Hai điểm duyệt là điểm dừng bắt buộc; không tự thực hiện phần phụ thuộc trước khi được duyệt.

## 3. Phạm vi rà soát

Tập trung vào ba nhóm, không quét mọi thứ với độ sâu như nhau.

### 3.1. Nhóm lõi hiện có

`smc_context`, models, lifecycle, sweep linking, confluence — đặc biệt chỗ một file vừa tính toán, vừa điều phối, vừa chuyển đổi dữ liệu.

### 3.2. Nhóm sắp phát triển

M15 confirmation, scorer, selection, scoring result và planner — chốt nơi sở hữu trách nhiệm trước khi thêm code.

### 3.3. Nhóm ranh giới tích hợp

Scanner, Analyze, replay, persistence và UI — rà cách nhận/trả dữ liệu và phụ thuộc; chưa refactor toàn bộ consumer trong đợt này.

### 3.4. Bằng chứng cần có cho mỗi vấn đề

- Nó gây khó khăn hoặc rủi ro cụ thể gì?
- Ảnh hưởng lô nào trong phần còn lại?
- Có cần sửa trước task73 không?
- Cách sửa nhỏ nhất là gì?
- Làm sao chứng minh không đổi hành vi?

## 4. Nguyên tắc chọn phần sửa ngay

Chỉ đưa vào lô refactor nếu có ít nhất một lý do rõ:

- Logic sắp được mở rộng đang nằm sai module hoặc có nhiều nơi cùng sở hữu.
- Phụ thuộc hiện tại có nguy cơ tạo import vòng.
- Caller/adapter đang che nguồn dữ liệu hoặc làm mất contract.
- Logic trùng khiến cùng một quy tắc có thể được sửa không đồng bộ.
- Không có ranh giới đủ rõ để kiểm thử độc lập phần sắp phát triển.

Không sửa ngay chỉ vì tên chưa đẹp, file dài, còn biến không dùng hoặc có thể viết “thanh lịch” hơn. Những việc đó chỉ làm kèm khi thật sự nằm trong phần đang chỉnh.

## 5. Cách refactor để tránh sửa đi sửa lại

- Mỗi lượt thay đổi trọn một trách nhiệm, không tách theo số dòng.
- Ưu tiên chuyển code và giữ interface trước; không đồng thời đổi công thức, defaults hoặc policy.
- Nếu cần lớp tương thích tạm, ghi rõ caller sử dụng và điều kiện gỡ bỏ; không tạo thêm đường tính toán độc lập.
- Test liên quan chạy sau từng khối; bộ kiểm chứng đầy đủ chạy ở điểm bàn giao.
- Phát hiện bug hành vi thì ghi riêng. Không âm thầm sửa chung vào refactor và gọi đó là “không đổi hành vi”.
- Nếu cùng lỗi refactor phải sửa lặp lại, rà lại ranh giới thiết kế thay vì tiếp tục vá từng assertion.
- Giữ thay đổi có sẵn của người dùng; không tự reset, xóa dữ liệu, commit hoặc rollout production.

## 6. Baseline và điều kiện nghiệm thu

Mốc task72 là **983 test và 16 reviewer probes đã PASS**, nhưng trước khi sửa phải đo lại trên repo hiện tại. Không coi kết quả ngày trước là baseline hôm nay. Ghi snapshot/hash, command, kết quả và lỗi nền nếu có.

Đợt này chỉ kết thúc khi:

- Các trách nhiệm được chọn đã có nơi sở hữu rõ.
- Không phát sinh import vòng hoặc hai đường tính cùng một quy tắc.
- Caller và schema được cam kết vẫn tương thích.
- Các test nền, probes và kiểm chứng hành vi liên quan đạt.
- Không mất test hoặc nới expected để che thay đổi.
- Kế hoạch task73–144 đã chỉ rõ module đích, đầu vào/đầu ra và điểm nghiệm thu từng lô.

Test xanh là bằng chứng cần thiết, không thay cho việc đối chiếu interface và đường chạy chịu ảnh hưởng. Nếu coverage thiếu, bổ sung kiểm tra cần thiết cho trách nhiệm đang refactor, không mở rộng audit vô hạn.

## 7. Hồ sơ và cách giao coder

Dùng chính tài liệu này làm hồ sơ ngắn cho đợt rà soát/refactor; kế hoạch triển khai và nhật ký hiện có chỉ cập nhật trạng thái, liên kết tới đây khi bắt đầu thực hiện. Không tạo ma trận và báo cáo phụ cho từng chỉnh sửa.

Giao coder theo lô. Coder tự chia bước nội bộ, cập nhật kết quả theo khối trách nhiệm; không cần báo dừng sau từng hàm, import hay hash. Sửa định dạng/tham chiếu trong cùng lượt cập nhật hồ sơ, không tách thành task riêng.

Kết quả lô 1 sẽ cụ thể hóa phần được sửa, module đích, thứ tự refactor và bộ kiểm chứng. Chưa ấn định danh sách module mới hoặc yêu cầu tách `smc_context.py` trước khi có bằng chứng rà soát.

## 8. Bước tiếp theo

**Lô 1: rà code thực tế và lập danh sách đề xuất có bằng chứng, chưa sửa code.** Sau điểm duyệt phạm vi mới thực hiện refactor. Chưa bắt đầu task73 và không mở lại yêu cầu nghiệp vụ của task72 trong đợt chỉnh cấu trúc này.

---

## 9. Kết quả Lô 1 — snapshot, bản đồ và đề xuất phạm vi

**Trạng thái: Lô 1 hoàn tất — PHẠM VI ĐÃ ĐƯỢC CHẤP THUẬN. Khối 2A (task73–79) và 2B (task80–91) đã REVIEW PASS; Task100 của khối2C (task92–99) đã APPROVED sau R100-01, đủ điều kiện lập/giao 2D integration task101–116. Chưa rollout canonical production hoặc auto-entry.**

Quyết định phạm vi (người dùng chốt 2026-09-14, ghi lại ở đây theo §7):

- **Không refactor trước task 73.** Lô 1 không đề xuất refactor nào và phần đã chốt giữ nguyên; `smc_context` **không** bị tách vì số dòng, route legacy `_smc_for_timeframe` giữ nguyên trạng thái đã nghiệm thu ở task 72.
- **Chia lô 73–79 / 80–91 / 92–100 là triển khai tính năng, không phải refactor thuần.** Đây là cách giao việc theo khối contract (2A/2B/2C), không mở lại phạm vi chỉnh cấu trúc; 2D (task 101–116) vẫn chờ sau review task 100.
- **Adapter M15 tạm được chấp thuận** với điều kiện gỡ ở §9.4 bên dưới; adapter chỉ chuyển đổi dữ liệu từ typed record, không tạo bộ tính confirmation thứ hai.
- Việc đọc **dữ liệu lịch sử** qua adapter thuộc task 117–120, không phải điều kiện của lô 73–79.

Đợt rà này chỉ đọc code/test, chạy diagnostic và cập nhật chính tài liệu này. Không sửa code, test, tham số, golden/probe hay dữ liệu nghiệp vụ. Không có `AGENTS.md` trong repository tại thời điểm rà.

### 9.1 Snapshot và baseline chạy lại

| Hạng mục | Kết quả thực tế ngày 2026-09-14 (Asia/Saigon) |
|---|---|
| Điểm xuất phát | `main`, `HEAD 6079be0 Bổ sung hồ sơ thiết kế/review SMC; dọn plan cũ đã hoàn tất` |
| Worktree trước Lô 1 | Chỉ có `?? docs/smc-pre-task73-architecture-review-plan.md`; đây là tài liệu kế hoạch được giao cập nhật. Không thấy thay đổi tracked/staged khác. |
| Nguồn quyết định gate72 | Header cũ của `smc-implementation-plan.md` và `smc-scoring-upgrade-plan.md` (đều 2026-09-11) còn ghi gate72 `CHANGES_REQUESTED`; chúng mâu thuẫn record mới hơn. Đối chiếu `smc-implementation-progress.md` task72 và nguồn quyết định `smc-task-72-response.md` §0 (2026-09-12): checkpoint D PASS, **task72 APPROVED**, task73 chưa làm. Giới hạn canonical/legacy tại response §0 và §7 vẫn giữ hiệu lực. |
| Acceptance gate72 | `python -m pytest tests/test_smc_gate72_fix_acceptance.py -q --tb=line` → **129 passed** (0.40s). |
| Reviewer probes | `python -m pytest docs/plans/probes/test_smc_gate72_review.py -q --tb=line` → **16 passed** (0.10s). |
| Task57–71 | `$gate72Tests = @(rg --files tests -g '*task5[7-9].py' -g '*task6[0-9].py' -g '*task7[01].py'); python -m pytest @gate72Tests -q --tb=short` → **108 passed** (1.28s). |
| Retained SMC/Scanner | `$retainedSmcTests = @(rg --files tests -g 'test_smc*.py' \| Where-Object { $_ -notmatch 'test_smc_gate72_fix_acceptance.py$' }); python -m pytest @retainedSmcTests tests/test_technical_signal_scorer.py tests/test_scanner_features.py tests/test_scanner_live_producers.py tests/test_analysis_pipeline_integration.py tests/test_scanner_scenario_producers.py tests/test_scanner_replay.py -q --tb=line` → **854 passed** (9.47s). |

Baseline đối chiếu là **983 passed** (= acceptance 129 + retained 854), kèm 16 probes và 108 test task57–71 xanh. Đây là kết quả chạy mới, không chỉ lặp lại mốc nghiệm thu cũ. Không có lỗi nền trong phạm vi các lệnh §5 đã chạy.

### 9.2 Bản đồ trách nhiệm và phụ thuộc thực tế

| Module / boundary | Trách nhiệm hiện tại, dữ liệu vào/ra | Caller/consumer thực tế | Nhận định ownership |
|---|---|---|---|
| `core/smc_models.py` | Model/ID/serialize cho snapshot, swing, event, `ZoneVisit`, `SmcZone`, setup và selected zone. | `smc_context`, lifecycle, confluence, scorer, technical projection; test round-trip. | Owner domain typed. Hiện import hằng version từ `smc_sweep_linking` tại dòng 17; đây là phụ thuộc ngược nhẹ, chưa tạo cycle. |
| `core/smc_lifecycle.py` | Phân tích visit, reaction, invalidation/expiry và FVG fill; trả `ZoneLifecycle`/payload lifecycle. | `smc_context.enrich_zones` (dòng 5334), D1 consumer qua zone đã enrich; test lifecycle/gate72 gọi trực tiếp. | Owner canonical lifecycle; task72 đã khóa terminal precedence. |
| `core/smc_sweep_linking.py` | Link sweep–zone, owner/assignment, consumed/dedupe. | `smc_context._attach_zone_sweep_links` (4892–5061); test task68, gate72 và probes gọi direct. | Owner ownership/claim, không bị scorer/consumer tính lại. |
| `core/smc_confluence.py` | Parent-child H1/H4 và D1 reaction evidence từ lifecycle. | `build_smc_context` gọi `build_directional_confluence`; test task70/71/gate72 gọi D1 builder direct. | Owner evidence đa timeframe; scorer cũ còn có `_d1_zone_reaction_bonus` riêng. |
| `core/smc_context.py` | Public builder D1/H4/H1; detector structure/zones/liquidity; orchestration link/enrich; legacy effective-zone helpers. Trả dict context. | Analyze (`analysis_pipeline` 542), Scanner (`scanner_live_producers` 306–309), tests/replay seams. | Orchestrator lẫn detector/adapter; file lớn có trách nhiệm độc lập, nhưng route production `_smc_for_timeframe` 890–1028 được giữ **legacy tường minh** theo quyết định task72, không phải lỗi gate72. |
| `core/smc_m15_confirmation.py` | Evaluator M15 cũ, nhận `side`, bounds, candle list; trả dict status/boolean/penalty/reasons. | Chỉ `smc_scorer._m15_confirmation_penalty` (842–876) trong production; test M15 gọi direct. | Owner detector M15, nhưng contract chưa mang zone/visit/event/time. Đây là đúng điểm task73–79 cần thay, không phải refactor độc lập trước task73. |
| `core/smc_scorer.py` | Evaluate H4/H1, score/select theo công thức cũ, gọi M15 để trừ penalty, phát `SmcScoringResult`. | Analyze 708–713; prefilter 61; Scanner 306–309; `smc_validation` 61. | Đang đồng sở hữu quality, selection cũ và M15 penalty; chặng D phải tách ownership theo task80–94. |
| `core/smc_scoring_result.py` + `smc_consumer_contract.py` | DTO side/result và adapter đọc selected zone/breakdown. | Analyze 738; scenario producer 287; technical scorer, scanner features, persistence/UI đọc projection sau đó. | Boundary canonical hiện chỉ mang selected zone/score; chưa mang confirmation/readiness/plan reference cùng candidate. |
| `core/scanner_scenario_producers.py` | Scanner plan từ selected zone hoặc fallback technical zone; `produce_scenario_plans_from_zones` là seam testable. | `scanner_release` 169–171; test scenario producer. Analyze dùng `risk_engine.build_trade_plan`, là seam khác. | Planner Scanner đã có seam nhưng chưa là `plan_for_candidate` chung; fallback hiện có phải được quyết định rõ ở task92–107. |
| Scanner / Analyze / replay / persistence / UI | Scanner live build/score (306–325), Analyze build/score/consumer (542, 708–754), replay scorer (`smc_validation` 45–61), persistence/UI đọc score/selected-zone projection. | Xem inventory task2 trong progress, cộng đối chiếu code ở trên. | Consumer hiện chỉ nhận/trả projection; không refactor mọi consumer trong Lô 1. |

Đồ thị import tĩnh của 16 module trọng tâm không có cycle đo được: `CYCLES=[]`. Chiều chính hiện tại là `models → (lifecycle/confluence/sweep contract data) → context`, `m15 → scorer → scoring_result → consumer/projection`; thực tế `smc_models → smc_sweep_linking` vì hằng version là ngoại lệ hướng ngược. Nguy cơ vòng chỉ xuất hiện nếu result/consumer bị để gọi lại planner hoặc nếu planner nhập scorer để chọn lại zone; hiện chưa xảy ra.

### 9.3 Vấn đề ảnh hưởng task73–144 và phân loại

| ID / loại | Bằng chứng và caller | Rủi ro cụ thể, phần bị ảnh hưởng | Phân loại và cách xử lý tối thiểu | Interface/hành vi giữ và kiểm chứng |
|---|---|---|---|---|
| A1 — **bug/contract cũ M15**, không phải refactor thuần | `smc_m15_confirmation.evaluate_m15_confirmation` 49–101 chỉ nhận side/bounds/candles, cắt 48 nến và chọn touch đầu tiên; `_result` 201–214 phát `confirmed`, `choch`, `reaction`, `penalty`. `smc_scorer._m15_confirmation_penalty` 842–876 biến nó thành điểm trừ. Caller production duy nhất là scorer. | Không thể gắn confirmation với `zone_id`, `visit_id`, trigger và lifecycle thời gian; confirmation cũ có thể sống qua visit mới/timeout. Trực tiếp chặn task73–79, sau đó readiness/selection. | **SỬA CÙNG LÔ TƯƠNG ỨNG (task73–79), không trước task73.** Thêm một `M15Confirmation` typed trong models; detector M15 chỉ tạo/invalid/expire result theo visit và trigger event. Để adapter dict tạm thời chỉ khi còn caller cũ, và mọi boolean còn lại phải suy ra từ status + trigger có ID/nguồn. | Không đổi lifecycle task72; giữ `ZoneVisit`/zone ID và round-trip. Dùng fixture 47 nến, ca visit mới/timeout/missing M15; giữ test analyzer forwarding M15 (`test_smc_m15_confirmation.py:422–442`) làm đối chứng. |
| A2 — **ownership scoring/readiness cũ** | `smc_scorer._score_side` 236–418 cộng structure/zone/LTF/technical rồi penalty/cap; `_zone_quality_components` 499–567 có pattern/location/lifecycle/liquidity; M15 trừ score. `select_smc_zone` 185–232 ưu tiên H4 tuyệt đối. | Khác công thức B/Q/L/C và nguyên tắc M15 không đổi quality; selection mới phải xét confirmation group và candidate trace. Sửa lẫn vào task73 sẽ vừa đổi behavior vừa khó isolate regression. | **SỬA CÙNG LÔ TƯƠNG ỨNG (task80–91).** Giữ evaluator candidate riêng, chuyển B/Q/L/C và readiness/ordering theo thứ tự checklist; không dọn scorer trước task73. | Giữ `score_smc`/result serialization trong giai đoạn chuyển, test score hiện hữu là đối chứng legacy; task88/97/98 thêm ví dụ tính tay, permutation, mirror và invariant “cùng setup đổi M15 không đổi quality”. |
| A3 — **hai owner geometry/plan eligibility** | Scorer hard-distance `_ZONE_HARD_DISTANCE_ATR = 3.0` (16, 445–457); Scanner planner có `_MAX_PROTECTIVE_ZONE_DISTANCE_ATR = 3.0`, `_MAX_ZONE_WIDTH_ATR = 1.0` (60–69, 135–143). Planner còn fallback technical trong `_protective_zone` 190–218. | Một candidate có thể được score/selected nhưng plan reject vì width, hoặc fallback vùng technical che việc thử candidate SMC kế tiếp. Ảnh hưởng task89, 92–97, 107/115. | **SỬA CÙNG LÔ TƯƠNG ỨNG (task89, 92–97), không trước task73.** Tạo seam geometry nhỏ, thuần dữ liệu (width/distance/ordering) dùng chung scorer và `plan_for_candidate`; không nhập risk/SL/TP hay sửa ngưỡng. | Giữ ngưỡng/plan shape hiện hành đến khi task89 đã có test; `produce_scenario_plans_from_zones` và test scenario là đối chứng. Gỡ duplicate constants chỉ sau khi seam có test H4 rộng, candidate kế tiếp và mirror BUY/SELL. |
| A4 — **result chưa bảo toàn cùng một candidate qua selection–plan** | `SmcSideScoringResult` 22–88 chỉ có score/selected-zone; consumer contract 37–80 chỉ copy zone/breakdown. Scanner release gọi planner sau result; Analyze đi qua `risk_engine.build_trade_plan` thay vì Scanner seam. | Task94 cần result chứa quality, lifecycle, confirmation và plan reference của **cùng** setup; nếu adapter tự chọn lại, candidate/plan có thể lệch. Cũng là nguy cơ import cycle tương lai nếu result gọi planner. | **SỬA CÙNG LÔ TƯƠNG ỨNG (task92–95, rồi 107).** Công bố `plan_for_candidate` pure từ planner; coordinator thử candidate đã order và mới finalize immutable result. Result/consumer chỉ là data, không import planner/scorer. | Tạm giữ `produce_scenario_plans` wrapper và selected-zone fields cho caller cũ; điều kiện gỡ adapter: task107 chuyển consumer, task113/114/120 chứng minh malformed/no-plan/round-trip. |
| A5 — **parity boundary chưa có ở Scanner** | Analyze truyền regime + M15 vào scorer (`analysis_pipeline` 708–713); Scanner live tại `scanner_live_producers` 275–327 chỉ nhận D1/H4/H1 và gọi `score_smc(context, technical)` trước khi resolve regime, không nhận M15. Test Scanner hiện kiểm valid/deterministic (`test_scanner_live_producers.py:267–292`), không có parity same-snapshot M15/readiness với Analyze. | Khi M15 thành readiness, Scanner và Analyze có thể cho result khác dù cùng cutoff; task101–116 và replay/UI/persistence sẽ nhận contract không nhất quán. Đây là gap caller coverage, chưa là lỗi baseline task72 (canonical rollout bị hoãn có chủ đích). | **SỬA CÙNG LÔ TƯƠNG ỨNG (task101–104, 114), không trước task73.** Bổ sung snapshot input chung gồm M15/metadata/cutoff, sau đó một evaluator/coordinator cho hai caller; không rollout canonical trong Lô 2 nếu chưa duyệt. | Giữ Scanner legacy route và task72 boundary tới task101; test task114 phải so raw, selected ID, confirmation/readiness/reasons và số lần evaluator giữa Analyze, Scanner, replay. |
| A6 — **context nhiều trách nhiệm, canonical/legacy boundary** | `smc_context.py` có builder 834, public legacy `_smc_for_timeframe` 890–1028, detector, pool/sweep 4235/4469, link 4892, enrich/lifecycle 5219. `_smc_for_timeframe` khai `pool_provenance="legacy"` và comment nêu rõ lý do. `smc-task-72-response.md` §0/§7.1 xác nhận chưa rollout canonical Analyze/Scanner. | File này khó định hướng khi mở task101; nhưng tách trước task73 sẽ di chuyển detector/orchestrator rộng, làm đụng route legacy đã được nghiệm thu mà chưa tạo seam mới cần cho task73. Không có evidence bug behavior ở baseline. | **HOÃN.** Không tách `smc_context` vì số dòng. Khi task101 cần snapshot/evaluator mới, chỉ bóc façade orchestration cần thiết; giữ `_smc_for_timeframe` legacy explicit cho đến khi parity task114 và quyết định rollout. | Giữ task72 acceptance/probes, retained 854; canonical/legacy assertions của gate72 là đối chứng. Không tự coi boundary legacy là task72 chưa hoàn tất. |
| A7 — **dependency direction quan sát được, chưa cycle** | Import graph đo bằng AST: không cycle; riêng `smc_models.py:17` import `SMC_SWEEP_LINK_VERSION` từ `smc_sweep_linking`, trong khi models là domain owner. | Có thể làm model khó giữ leaf nếu thêm M15/selection imports; hiện chỉ là hằng version, không chặn task73. | **HOÃN (cleanup task140 hoặc cùng một thay đổi chỉ nếu Lô 2 buộc tạo cycle).** Khi làm, chuyển hằng version sang `smc_versions`, không tách model hay đổi serialization. | Chạy import smoke + model round-trip/gate72; không chấp nhận dùng việc này làm phạm vi refactor riêng. |

Không có finding nào yêu cầu refactor code **trước Task73**. A1 là thay đổi hành vi được chính Task73–79 đặc tả; A2–A5 chỉ an toàn khi làm ở lô sở hữu contract tương ứng. A6–A7 là nợ cấu trúc có chủ đích/đo được, chưa đủ bằng chứng để mở dọn dẹp.

### 9.4 Cấu trúc đích tối thiểu và thứ tự Lô 2

Không dựng framework/service/database. Đề xuất giữ đa số module hiện có, chỉ tạo seam nhỏ khi một rule phải do hai consumer dùng chung.

```text
smc_models (typed IDs, zone/visit/confirmation DTO; leaf sau cleanup)
    ↑
lifecycle / sweep_linking / confluence / m15_confirmation
    ↑                                      ↑
smc_context (producer/orchestrator)   scorer (B/Q/L/C + candidate evaluation)
                                           ↑                  ↑
                         candidate geometry (pure)     plan_for_candidate (pure)
                                           \                  /
                                            selection coordinator
                                                   ↓
                                      smc_scoring_result (data only)
                                                   ↓
                  consumer contract → Scanner / Analyze / replay / persistence / UI
```

| Khối Lô 2 | Phạm vi và đầu ra | Tiêu chí dừng / interface tương thích |
|---|---|---|
| **2A — Contract M15 (task73–79)** | `smc_models` có confirmation typed (zone, visit, trigger, confirmed/expires/invalidated/reason); `smc_m15_confirmation` đánh giá current/completed-effective visit, micro-break/rejection và invalidation. | Không score B/Q/L/C hay rollout caller. Có fixture 47 nến/new visit/timeout/missing; adapter dict chỉ là bridge có hạn nếu scorer cũ còn dùng. |
| **2B — Quality, geometry, readiness/order (task80–91)** | `smc_scorer` chuyển sang evaluate candidate theo B/Q/L/C; seam geometry là owner duy nhất width/distance; readiness tách quality; ordering deterministic theo contract mới. | Không gọi planner từ scorer. Có ví dụ tính tay, null/data unavailable, mirror/permutation; M15 thay đổi readiness/nhóm selection chứ không quality cùng candidate. |
| **2C — Plan candidate và finalize result (task92–100)** | Public pure `plan_for_candidate` (tách tối thiểu từ scenario producer); coordinator thử danh sách đã order, lưu reject reason, rồi phát `SmcScoringResult` có confirmation/readiness/plan reference cùng selected setup. | Result/consumer không import planner, planner không gọi scorer. Giữ wrapper Scanner/selected-zone fields đến task107; trình review task100 trước integration. |
| **2D — Integration có giới hạn (chỉ sau task100 APPROVED; task101–116)** | Một snapshot input gồm cutoff, M15, metadata; dùng evaluator/coordinator chung cho Scanner, Analyze, replay; chuyển prefilter/projection/consumer từng boundary. | Parity task114 cùng snapshot; fallback technical phải có source/decision rõ, không bypass SMC invalid. Giữ legacy task72 route tới khi kiểm chứng và quyết định rollout. |
| **2E — Deferred cleanup (task140 hoặc khi bị cycle thật)** | Chỉ sau khi 2D ổn định: bỏ adapter tạm, chuyển hằng version để models leaf, bóc façade hẹp khỏi `smc_context` nếu caller mới thật sự cần. | Không đổi behavior, không quét lại detector/lifecycle; retained/gate72 và integration parity xanh. |

Điều kiện gỡ adapter: (1) mọi caller inventory task2 đã chuyển sang final result/consumer contract tại task107; (2) task113–115 chứng minh no-zone/no-plan/data unavailable/fallback không bypass; (3) task120 chứng minh serialize/restart/historical reader — **REVIEW PASS 2026-09-16** trên Scanner/Analyze; (4) review task116 APPROVED — **đã APPROVED 2026-09-15**. Không giữ hai đường tính selection hoặc confirmation sau mốc này.

**Trạng thái bằng chứng cho (3):** Scanner và Analyze nay cùng forward block canonical: Scanner caller → writer → disk → instance mới/load/replay đã `canonical_compatible`; missing/tampered/malformed vẫn fail-closed, historical không current. Việc **gỡ** adapter vẫn chưa xảy ra và không thuộc lô này; review pass không là quyền cleanup.

Áp dụng cho adapter M15 đã triển khai ở khối 2A: `evaluate_m15_confirmation` (dict) chỉ chuyển đổi typed `M15Confirmation`; caller production `smc_scorer._m15_confirmation_reasons` đã đọc typed record, nên điều kiện gỡ là (1) + (4) — không còn caller cũ nào đọc dict và review 116 APPROVED. Adapter đọc dữ liệu lịch sử thuộc task117–120, không tính vào điều kiện này.

### 9.5 Kiểm chứng Lô 2 và các quyết định cần duyệt

Mỗi khối giữ baseline §9.1, chạy targeted tests của chính khối, sau đó acceptance/probes/task57–71/retained. Với 2D bổ sung parity Scanner–Analyze–replay ở cùng cutoff; không coi test xanh thay cho review task100/116.

**Quyết định đã chốt để bắt đầu Lô 2 (người dùng, 2026-09-14):**

1. **Phạm vi:** 2A–2C (task73–100) là Lô 2 đầu tiên; 2D integration task101–116 hoãn đến sau review task100. Không refactor trước task73; gate72 legacy boundary giữ nguyên.
2. **Compatibility M15/result:** adapter dict chỉ nội bộ/tạm thời trong lúc task73–100, với điều kiện gỡ ở §9.4; không mở public consumer mới từ boolean vô nguồn. Không dùng breaking contract ngay task73 để buộc cập nhật consumer ngoài phạm vi task73.
3. **Technical fallback:** **chưa chốt** — tiêu chí technical fallback nào là luận điểm độc lập hợp lệ vẫn phải Tech Lead quyết định trước task92/107; khối 2A–2C không tự suy diễn chính sách này.
4. **Canonical rollout:** `_smc_for_timeframe` Analyze/Scanner tiếp tục là legacy explicit cho tới task101–116 parity, đúng giới hạn task72 §0/§7; không đưa rollout này vào Lô 2A–2C.

**Trạng thái khối 2A/2B (2026-09-14):** 2A (task 73–79) **REVIEW PASS** (R73-01/R73-02 tái kiểm qua evaluator, scorer và Analyze seam). 2B (task 80–91: B/Q/L/C, geometry dùng chung, readiness, thứ tự candidate) **REVIEW PASS — đủ điều kiện giao 2C/task92–100**. R80-91-01 CLOSED: hard-reject không còn thắng quality/order. R80-91-02 CLOSED: planner runtime gọi shared gate với original bounds, formation ATR provenance cho width và frozen execution ATR cho distance; canonical evidence block thiếu ATR fail-closed, còn projection legacy không evidence block giữ compatibility tới khi được nối ở task94+/101+. R80-91-03 CLOSED theo lựa chọn A: `score_smc` gọi adapter canonical đúng một lần và đưa B/Q/L/C/order/readiness ra diagnostics nội bộ, không đổi legacy score/selected zone hay serialization, không gọi planner/coordinator. Geometry owner và caller boundary 2B đã có evidence runtime; parity Scanner/Analyze/replay, result finalization và consumer rollout vẫn thuộc lô sau. Chi tiết ở [nhật ký tiến độ §Lô 80–91](plans/smc-implementation-progress.md#lô-8091--bqlc-geometry-dùng-chung-readiness-và-thứ-tự-candidate). **Chưa APPROVED Task100, chưa task92, chưa rollout canonical.** Policy P10 và wiring cutoff thật Scanner/persistence vẫn hoãn theo phạm vi đã chốt.

**Trạng thái khối 2C (2026-09-14): `Task100 APPROVED`.** R100-01 đã CLOSED: coordinator khóa identity của `PlanAttempt`; final result/projection cùng một strict invariant cho plan/zone/setup, B/Q/L/C và scalar canonical. Evidence/decision ở [nhật ký tiến độ §Quyết định cuối Task100](plans/smc-implementation-progress.md#quyết-định-cuối-task100--approved-2026-09-14). **Đủ điều kiện lập/giao task101–116 (2D); chưa rollout canonical hay auto-entry.**

**Trạng thái 2D (cập nhật 2026-09-15): `TASK101–111 REVIEW PASS; TASK112–115 IMPLEMENTED — WAITING_REVIEW TASK116`.** Sau khi nối snapshot vào Scanner/Analyze, Tech Lead xác minh producer thực vẫn phát zone legacy thiếu canonical evidence, làm canonical evaluation thành `data_unavailable`. Quyết định D101-01 cho phép bóc **façade canonical hẹp** cho snapshot từ detector canonical hiện có, nhưng cấm thay `build_smc_context`/`_smc_for_timeframe` legacy trước parity Task114; đây là cách áp dụng đúng giới hạn A6, không phải rollout legacy replacement. D101-02 giữ tick-size là dependency theo rule thay vì core-unavailable toàn snapshot. D107-01 cấm technical fallback nâng quyền trên canonical route. D111-01 yêu cầu fresh snapshot tại revalidation/dispatch trước khi Task111 hoàn tất. Chi tiết và tiêu chí nghiệm thu ở [nhật ký lô 101–115](plans/smc-implementation-progress.md#quyết-định-tech-lead-sau-blocker--phạm-vi-tiếp-tục-bắt-buộc-2026-09-14). **Task112–115 đã IMPLEMENTED**, xem mục ngay dưới; parity Task114 đã có bằng chứng 3 route nhưng **chưa** vì thế mà cho phép thay đường legacy.

**Quyết định D103-02/D102-02 (2026-09-14):** Golden Analyze mang tên canonical phải re-baseline theo snapshot/evaluator canonical của Task103, có mapping từng expected và không dùng route legacy để ép xanh. Fast-path oracle canonical cần diagnostic provenance trước khi re-baseline; riêng `raw_empty_v2` có S/D output mới không được chấp nhận chỉ vì deterministic. Golden/probe/gate Task56/72 legacy giữ nguyên. Chi tiết tiêu chí ở [nhật ký lô 101–115](plans/smc-implementation-progress.md#quyết-định-tech-lead--golden-và-fast-path-oracle-2026-09-14).

**Quyết định D102-03/D103-03 (2026-09-15):** Diagnostic chứng minh zone mới có provenance nhưng corpus legacy làm tất cả scenario dương fail P11; do đó fixture canonical phải được dựng lại để giữ ý nghĩa scenario, không accept oracle “no setup” suy biến và không đổi threshold. Golden canonical dùng artifact versioned riêng từ candles/cutoff; artifact legacy, probe và gate72 giữ nguyên, `choch_cap` là characterization legacy explicit. Tiêu chí fixture/oracle ở [nhật ký lô 101–115](plans/smc-implementation-progress.md#quyết-định-tech-lead-bổ-sung--fixture-canonical-không-được-suy-biến-2026-09-15).

**Quyết định D102-04 (2026-09-15):** `h1_order_block_v2` phải giữ đúng nghĩa scenario: fixture canonical cần pivots/BOS causal để OB được confirm, eligible và selected; FVG không được thay thế bằng chứng đó. Giữ P11 và production logic; chi tiết acceptance/control BOS ở [nhật ký lô 101–115](plans/smc-implementation-progress.md#quyết-định-tech-lead-d102-04--h1_order_block_v2-phải-chứng-minh-ob-thật-2026-09-15).

**Quyết định D102-05 (2026-09-15):** Chấp thuận một fixture OB chuyên biệt, có history variable-amplitude và chuỗi base → departure → BOS hậu-departure trong cửa sổ Task44; không tiếp tục vá zigzag chung hay nới contract. D103-03 chỉ bắt đầu sau khi OB canonical được confirm/selected và control không-BOS chứng minh causal. Chi tiết tại [nhật ký lô 101–115](plans/smc-implementation-progress.md#quyết-định-tech-lead-d102-05--fixture-ob-chuyên-biệt-2026-09-15).

**Quyết định D102-06 (2026-09-15):** Cho phép đoạn xác nhận swing H1 có chủ đích: ít nhất năm nến phải sau swing high mới, trước base/departure/BOS trong window Task44. Đây là fixture-only cho `h1_order_block_v2`, không đổi production/threshold và không thay scenario bằng unit test. Chi tiết tại [nhật ký lô 101–115](plans/smc-implementation-progress.md#quyết-định-tech-lead-d102-06--cho-phép-đoạn-xác-nhận-swing-có-chủ-đích-2026-09-15).

**Tái kiểm D102-06 (2026-09-15): PASS.** Fast-path fixture chuyên biệt tạo OB canonical confirmed/selected sell qua BOS delta 2; 72 test targeted độc lập xanh. Được bắt đầu D103-03; bổ sung regression source-swing-after-anchor được mang vào lượt đó. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#tái-kiểm-tech-lead-d102-06--pass-2026-09-15).

**Tái kiểm D103-03 (2026-09-15): CHANGES_REQUESTED.** Golden canonical hiện kiểm seam snapshot/evaluator thuần chứ chưa chạy mỗi case qua Analyze; vì vậy chưa chứng minh Task103 caller/runtime. Phải chuyển golden expected sang output Analyze thật, giữ artifact legacy tách biệt và không rebaseline vô nguồn. Chi tiết finding D103-04 tại [nhật ký](plans/smc-implementation-progress.md#tái-kiểm-tech-lead-d103-03--changes_requested-2026-09-15).

**Tái kiểm D103-04 (2026-09-15): PASS.** Golden canonical nay chạy từng case qua `AnalysisPipeline.execute`, đọc consumer Analyze, và khóa cutoff/tick/M15/reuse/error path; 71 test targeted độc lập xanh. Artifact legacy giữ riêng. Lô integration vẫn chờ khôi phục 27 regression mới trước review Task101–111. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#tái-kiểm-tech-lead-d103-04--pass-2026-09-15).

**Quyết định regression 2D (2026-09-15):** Detail diagnostics phải có tick/cutoff fixture xác định để kiểm row `BLOCKED`; H02 dùng contract unavailable/absent thay `NO_VALID_ANCHOR` khi Location không được đánh giá; risk test không được tăng skip mà phải có sell-plan fixture/pure input hợp lệ. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#quyết-định-tech-lead-regression-còn-lại-2026-09-15).

**Quyết định DREG-04 (2026-09-15):** Bốn regression execution controller phải dùng fixture canonical thực sự dispatchable (`READY_NOW`, M15 `confirmed`, plan/identity cùng lineage) để kiểm dispatch/portfolio sau fresh revalidation; không mock hoặc bypass revalidation/M15, không fallback legacy. Chi tiết và controls bắt buộc tại [nhật ký](plans/smc-implementation-progress.md#quyết-định-tech-lead-dreg-04--execution-controller-cần-fixture-dispatchable-canonical-2026-09-15).

**Quyết định DREG-04a (2026-09-15):** Vì M15 confirmation có thể đổi winner, fixture dispatch phải hội tụ bounded trên winner sau M15 (tối đa ba bước, assert hội tụ); proposal/quote lấy từ final evaluation, còn control M15/identity lệch phải chặn. Không đổi engine/ordering. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#quyết-định-tech-lead-dreg-04a--fixture-dispatch-phải-hội-tụ-selection-sau-m15-2026-09-15).

**Quyết định DREG-04b (2026-09-15):** Không ép fixture execution ổn định qua wall-clock. Bổ sung clock dependency nội bộ ở dispatch, default UTC production và đọc một lần để chuyển cutoff vào Task111 revalidation; fixture inject clock xác định nhưng vẫn loader/evaluator thật. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#quyết-định-tech-lead-dreg-04b--clock-seam-tại-dispatch-không-ép-fixture-ổn-định-wall-clock-2026-09-15).

**Tái kiểm DREG-04b (2026-09-15): CHANGES_REQUESTED.** Targeted Task111/execution độc lập 32 passed và regression toàn suite đã về nền, nhưng `_utc_now()` hiện fail-open khi caller **đã inject** clock không callable: chỉ `clock=None` mới được fallback UTC production, còn junk phải `ValueError`. Giữ `smc_revalidation` output audit; source-age/freshness history là giới hạn **DEFERRED** cho Task115/gate safety vì chưa có owner/metadata/SLA route được chốt. Task112–115 vẫn chưa bắt đầu; lô 101–111 chưa `WAITING_REVIEW`. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#tái-kiểm-tech-lead-dreg-04b-2026-09-15--changes_requested-một-sửa-nhỏ).

**Tái kiểm R111-02 (2026-09-15): PASS.** Clock injected junk nay fail-closed, `None`/legacy instance giữ UTC production, và targeted dispatch/revalidation độc lập 32 passed. Task101–111 chuyển `WAITING_REVIEW`; Task112–115 vẫn chưa làm. Source-age freshness và rollout tiếp tục DEFERRED/no-rollout. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#tái-kiểm-tech-lead-r111-02-2026-09-15--pass-task101111-waiting_review).

**Review chính thức Task101–111 (2026-09-15): REVIEW PASS.** Chuỗi snapshot canonical → evaluation/selection/plan → consumer Scanner/Analyze → revalidation dispatch đã được kiểm độc lập; Task112–115 được phép thực hiện. Source-age freshness là DEFERRED cho Task115/gate safety. Không phải APPROVED Task116 hay rollout/auto-entry.

**Tái kiểm R114-01 (2026-09-15): PASS.** Analyze nay đọc preferred zone từ final selection qua adapter hẹp, còn gate scenario/risk/macro/safety giữ owner; mismatch/malformed fail-closed. Task112–115 vẫn `IMPLEMENTED — WAITING_REVIEW Task116`; source-age freshness tiếp tục DEFERRED, không rollout/auto-entry.

**Quyết định Task116 (2026-09-15): APPROVED.** Chuỗi 2D Task101–115 đã qua review flow/parity/blocked-unknown/fallback/revalidation; được bắt đầu Task117–120 persistence/cache. Không phải rollout canonical production hay auto-entry; source-age freshness và P10 vẫn deferred, adapter compatibility chỉ được gỡ sau evidence Task120.

**Lô Task117–120 (2026-09-16): REVIEW PASS — đủ điều kiện giao lô121–128.** Re-review Scanner persistence đã xác minh Scanner/Analyze cùng block canonical qua `services/scanner_persistence_service` trên instance mới; missing/tampered/malformed và unwrap đều fail-closed. Cache-record seam vẫn không được nối live. **Adapter compatibility vẫn CHƯA gỡ**; source-age freshness/P10 DEFERRED, không rollout/auto-entry. Chi tiết ở [nhật ký tiến độ](plans/smc-implementation-progress.md).

**R114-01 (2026-09-15): IMPLEMENTED — WAITING_REVIEW.** Finding BLOCKING "Analyze không đọc final canonical selection để dựng scenario" đã được xử lý đúng quyết định Tech Lead: **adapter reader-only `selection → preferred_zone`** tại consumer boundary (`core/smc_consumer_contract.scenario_preferred_zone_for_side`), dùng ở `_step_build_trade_scenarios`; `build_scenarios`/`build_trade_plan` và mọi gate risk/macro/safety/account/scenario/entry **giữ nguyên vai trò owner**. Không chuyển Analyze sang tự dựng plan, không điền ngược field legacy `selected_zone`, không fallback sang technical/legacy zone. Đo thật trước/sau: canonical buy `evaluated` + plan ⇒ trước là `_scenarios == []` + fallback hiển thị, sau là scenario `entry_zone_source="smc_selected"`, `entry_zone_id` = zone đã chọn. `selected_zone_for_side` giữ nguyên hành vi cho distant-zone và reader lịch sử nên Scanner live route/technical fallback **không đổi**. 28 test mới qua `AnalysisPipeline.execute` thật (positive/fail-closed/gate preservation/parity). Source-age freshness vẫn **DEFERRED**, không đặt SLA mới. Chi tiết ở [nhật ký](plans/smc-implementation-progress.md#r114-01--analyze-dựng-scenario-từ-final-canonical-selection-2026-09-15--implemented-waiting_review). Không tự ghi Task112–115 `WAITING_REVIEW`, không APPROVED Task116, không rollout/auto-entry.

**Lô Task112–115 (2026-09-15): IMPLEMENTED — WAITING_REVIEW Task116.** Bản đồ caller xác nhận AI penalty / cap CHOCH / subtotal legacy chỉ còn sống trên `score_smc` và **không** nằm trên đường canonical; AI gate độc lập ngoài SMC (`core/scanner_ai_auditor`, consumer ở `scanner_controller`) giữ nguyên. Đã gỡ import chết `score_smc` khỏi `analysis_pipeline`, và **gỡ chain canonical thứ hai**: `replay_canonical_snapshot` nay nhận `SmcSnapshotInput` và uỷ quyền cho `evaluate_smc_snapshot` (trước đó truyền snapshot thật bị degrade âm thầm thành `DATA_UNAVAILABLE`). 54 test mới chạy qua caller thật cho D107-01 (technical fallback không bypass `invalid`/`no_zone`/`data_unavailable`), contract consumer/composition, parity 3 route và gate/safety/macro/risk. **Đã chốt:** Analyze scenario seam ⇒ xem **R114-01** ngay trên. **Còn lại:** source-age freshness tiếp tục **DEFERRED** (chỉ characterize 2 owner hiện hữu: SLA composition 120s/30s và `DataFreshnessSource`). Chi tiết ở [nhật ký](plans/smc-implementation-progress.md#lô-task112115--implemented-waiting_review-task116-2026-09-15). Không phải APPROVED Task116, không rollout/auto-entry.

**Sửa R111-02 (2026-09-15):** Đã đóng finding. `_utc_now()` nay phân biệt rõ: `getattr(self, "_clock", None) is None` (kể cả instance thiếu field) ⇒ UTC production; **không callable ⇒ `ValueError`** (lỗi wiring, không fallback); callable trả non-`datetime`/naive/offset không xác định ⇒ `ValueError`; aware khác UTC ⇒ normalize. Vẫn một lần đọc trên đường dispatch, không dùng cho quote/tick/news/portfolio/risk; `smc_revalidation` giữ nguyên làm audit evidence. Kiểm chứng: execution+Task111 **32 passed**, targeted Task101–111 **227 passed**, gate72+probes **313 passed**, toàn suite **6 failed (FRED nền) / 4350 passed / 7 skipped / 16 xfailed**, collection **4379** không đổi, `git diff --check` sạch. Chi tiết tại [nhật ký](plans/smc-implementation-progress.md#sửa-r111-02-2026-09-15--clock-không-callable-phải-fail-closed-không-rơi-về-utc-thật).

Không có quyết định nào cần để bắt đầu riêng một refactor trước Task73, vì không đề xuất refactor đó.
