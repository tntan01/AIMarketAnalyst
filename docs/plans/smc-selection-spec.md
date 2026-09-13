# Đặc tả selection và plan SMC — task 13

> **Trạng thái:** DRAFT — chờ Tech Lead review tại task 16.  
> **Mục đích:** xác định duy nhất nơi chọn candidate cuối, thứ tự xét candidate, seam giữa scorer/planner/canonical result và cách xử lý candidate không tạo được plan.

## 1. Quyền sở hữu cuối cùng

`SelectionCoordinator` là owner duy nhất của quyết định selected candidate cuối cho mỗi side.

| Thành phần | Được làm | Không được làm |
|---|---|---|
| `smc_scorer` / candidate evaluator | Validate raw candidate, tính B/Q/L/C và quality, tạo rejection/eligibility evidence, trả tất cả candidate | Không gọi planner, không gọi network/UI/broker, không chọn selected cuối dựa trên R:R |
| `order_candidates` | Sắp xếp deterministic các evaluation đã có | Không tính lại quality, không dùng R:R/risk để đổi thứ tự |
| `SelectionCoordinator` | Lọc hard gate, gọi planner theo thứ tự, chọn candidate đầu tiên có plan, giữ trace/rejections và finalize canonical result | Không tự chấm scorer lần hai, không lách market/account gate bằng candidate khác |
| `plan_for_candidate` / scenario planner | Nhận một candidate + technical/risk policy trực tiếp và dựng plan pure hoặc trả rejection | Không đọc canonical result cuối, không gọi scorer, không chọn candidate khác |
| `SmcScoringResult` / canonical finalizer | Đóng gói selected setup/zone, quality, lifecycle, confirmation, plan ref, alternatives và trace | Không tự chọn lại, không dò raw zone tại consumer |
| Consumer/UI/persistence | Đọc canonical selected result và status | Không tính score, không chọn candidate khác, không bypass gate |

Đây là seam mục tiêu cho cả Analyze, Scanner live và replay. Các adapter chỉ khác nguồn snapshot/provenance; thứ tự đánh giá và coordinator phải giống nhau với cùng snapshot/cutoff.

## 2. Flow chuẩn

```text
immutable snapshot + canonical SMC inputs
  -> evaluate_candidates (quality + hard eligibility + per-candidate confirmation)
  -> order_candidates (deterministic)
  -> SelectionCoordinator
       -> plan_for_candidate(candidate_1)
       -> nếu reject geometry/plan: lưu reason, thử candidate_2...
       -> candidate đầu tiên có plan = selected
       -> finalize_canonical_result(selected, plan, trace)
  -> consumer đọc canonical result/plan/readiness, không chọn lại
```

Coordinator không gọi network, broker hoặc UI. Planner là pure function đối với input snapshot đã chụp; nếu order policy không có `min_rr`, planner trả `PLAN_POLICY_UNAVAILABLE`, không tự invent ngưỡng. Confirmation rank có thể làm selected candidate đổi khi M15 được thay: invariant chỉ áp dụng cho quality/lifecycle của **từng candidate**, không đóng băng selected ID của cả danh sách.

## 3. Hợp đồng evaluation và candidate

Mỗi `CandidateEvaluation` cần mang tối thiểu:

| Trường | Quy tắc |
|---|---|
| `candidate_id` | ID ổn định của child zone; không dựa index list |
| `setup_id` / `zone_id` | Setup lineage và child zone identity; giữ cả hai |
| `side` / `timeframe` / `family` | Đã normalize và direction-checked |
| `confirmation_state` | `confirmed`, `waiting`, `candidate`, `invalid`, `expired`, `conflict` |
| `quality_raw` / `quality_score` | Điểm của chính candidate; không tính theo plan/R:R |
| `B/Q/L/C` và breakdown | Contribution thật, mỗi component `[0,1]` theo task 11 |
| `lifecycle` / `visit` / `confirmation` | Canonical evidence tại cùng cutoff |
| `geometry` | Original/protective bounds, refined bounds nếu có, width/distance gate |
| `mandatory_passed` | Chỉ true khi đủ core data, đúng side, active, valid geometry và không hard-invalid |
| `rejection_codes` | Lý do loại candidate tại evaluator, không mất khi candidate khác được chọn |
| `available_at` | Candidate không được xét trước thời điểm này |

Evaluator phải trả toàn bộ candidate trong history hợp lệ sau lifecycle/eligibility; giới hạn top-K chỉ áp dụng sau đánh giá và không được làm candidate mới invalid che candidate cũ hợp lệ.

## 4. Thứ tự xét candidate

### 4.1 Hard filter trước khi order

Loại khỏi danh sách có thể tạo plan nếu:

1. Core data/cutoff/ATR bắt buộc không hợp lệ.
2. Candidate chưa tới `available_at`, chưa confirmed, sai side hoặc source history không đủ.
3. Zone invalidated/expired; FVG full-filled khi đang xét imbalance; structure conflict hard hoặc countertrend chưa đạt rule.
4. Original bounds không hợp lệ, width vượt `1.00 ATR`, distance vượt `3.00 ATR` hoặc planner-required geometry thiếu.

Hard rejection phải có reason. Nếu toàn bộ candidate bị loại vì thiếu core data → `DATA_UNAVAILABLE`; nếu đã đánh giá đủ nhưng không còn candidate → `NO_VALID_SETUP`/`OUT_OF_STRATEGY` theo readiness spec, không giả lập selected zone.

### 4.2 Stable ordering

Trong candidate còn lại, sort theo tuple sau, từ ưu tiên cao tới thấp:

```text
(
  confirmation_rank ascending,
  quality_score descending,
  distance_to_zone_atr ascending,
  timeframe_tiebreak (H4 trước chỉ khi các khóa trên thật sự hòa),
  age_bars ascending,
  stable_candidate_id ascending,
)
```

`confirmation_rank` baseline:

| Rank | Trạng thái |
|---:|---|
| 0 | Confirmed + current entry confirmation còn hiệu lực |
| 1 | Confirmed + active nhưng đang chờ M15/visit/follow-through |
| 2 | Confirmed watch zone chưa có entry trigger |
| 3 | Candidate chưa confirmed |

Candidate invalid/expired không vào order list. Candidate có quality cao hơn nhưng không plan được vẫn được thử trước theo order, sau đó bị bỏ qua với reason; candidate H4 không thắng tuyệt đối H1 nếu các khóa ưu tiên trước chưa hòa.

Quality dùng `quality_score`/`quality_raw` của chính candidate. R:R, TP, risk, account policy và số lần retry không được đưa vào score hoặc dùng để reorder. Planner có thể reject R:R theo order policy, nhưng rejection đó chỉ quyết định thử candidate kế tiếp, không làm quality candidate thay đổi.

## 5. Hợp đồng `plan_for_candidate`

```text
plan_for_candidate(
    candidate,
    technical_context,
    execution_policy,
    snapshot_metadata,
) -> PlanAttempt
```

`PlanAttempt` có một trong hai dạng:

```text
PlanAttempt(
    plan=ScenarioPlan(...),
    plan_available=True,
    rejection_codes=(),
)

PlanAttempt(
    plan=None,
    plan_available=False,
    rejection_codes=("ZONE_WIDTH_TOO_WIDE", ...),
)
```

Planner phải kiểm tra cùng shared geometry với scorer/planner:

- original/protective bounds ordering và width;
- current distance/hard distance;
- entry/stop/TP ordering;
- min R:R từ policy caller, nếu policy có;
- required technical levels và field validity.

Planner không được thu hẹp protective zone tùy ý, chỉnh SL/TP hoặc risk floor để candidate đạt. Refined bounds chỉ hỗ trợ entry theo zone spec; invalidation/SL vẫn dựa original bounds. Không có plan là rejection có reason, không phải fallback sang plan tự chế.

## 6. Coordinator loop và candidate kế tiếp

Pseudo-contract:

```text
evaluations = evaluate_candidates(snapshot)
ordered = order_candidates(evaluations)

for candidate in ordered:
    attempt = plan_for_candidate(candidate, snapshot.technical, policy, snapshot.meta)
    trace.append(candidate_id, quality, attempt.rejection_codes)
    if attempt.plan_available:
        return finalize_canonical_result(
            selected=candidate,
            plan=attempt.plan,
            trace=trace,
            alternatives=remaining_candidates,
        )

return finalize_watch_or_no_plan_result(
    best_watch=first_confirmed_or_watch_candidate,
    trace=trace,
)
```

Quy tắc loop:

- Candidate đầu không tạo được plan vì geometry/technical level/TP/min-RR → thử candidate kế tiếp theo cùng order; không thay quality.
- Candidate planner exception/malformed input → ghi `PLANNER_INPUT_INVALID`/`PLANNER_ERROR`, fail-closed cho candidate đó và tiếp tục candidate sau nếu lỗi không phải lỗi snapshot chung.
- Nếu planner phát hiện core snapshot chung không hợp lệ, dừng và trả `DATA_UNAVAILABLE`, không thử candidate khác để che lỗi input.
- Nếu một market/account/safety/macro gate chặn toàn luận điểm, dừng ở selected candidate/trace hiện tại; không thử candidate khác để lách gate.
- Nếu không candidate nào có plan nhưng còn confirmed watch zone, selected watch zone có quality/lifecycle và `plan_available=false`; status không `READY_NOW`.
- Nếu không còn candidate confirmed/watch hợp lệ, selected null và status theo `NO_VALID_SETUP`.

## 7. Setup grouping, sibling và alternatives

- `setup_id` là cơ hội/lineage chung; `zone_id` là child cụ thể được planner thử.
- OB/FVG/S-D cùng departure có thể có nhiều child. Không cộng B/L/C nhiều lần; Q/geometry được đọc theo child đang thử.
- Nếu child 1 của setup A reject plan nhưng child 2 của setup A tạo được plan, chọn child 2 và giữ trace child 1; không coi đó là setup opportunity mới.
- `selected_setup_id`, `selected_zone_id`, selected quality, lifecycle, confirmation và `plan_reference` phải cùng lineage.
- Alternatives tối đa 2–3 để giải thích, giữ thứ tự ranking và rejection reasons; alternatives không được biến thành READY hoặc tự tạo scenario khác ở consumer.
- Không union bounds sibling, không đổi selected child tại UI, persistence hay technical projection.

## 8. Canonical result sau selection

Finalizer là nơi duy nhất ghi selected fields:

| Trường | Nội dung |
|---|---|
| `selected_setup_id` / `selected_zone_id` | Candidate confirmed/usable được chọn, kể cả khi watch/no-plan; chỉ null ở no-zone, core unavailable hoặc không có candidate hợp lệ |
| `selected_zone_quality_score` / `quality_raw` | Điểm của candidate selected, không phải điểm của candidate bị reject |
| `selected_lifecycle` / `selected_confirmation` | Evidence của cùng selected zone/visit/event |
| `plan` / `plan_available` | Plan attempt của selected candidate |
| `selection_reason_codes` | `QUALITY_RANK`, `NEXT_CANDIDATE_AFTER_REJECT`, `WATCH_NO_PLAN`, … |
| `candidate_trace` | Tất cả candidate đã xét, thứ tự, score và reject reason |
| `alternatives` | Candidate còn lại đã order, chỉ để giải thích |
| `selection_version` | Identity của policy/seam để replay/cache không lẫn logic cũ |

Consumer chỉ được đọc finalizer result. Nếu selected plan bị thiếu, result có thể giữ selected watch zone nhưng readiness phải là `WATCH_ZONE`, không READY. `canonical_smc` trước final selection không được public như selected chính thức.

## 9. Parity giữa các đường chạy

| Đường chạy | Evaluator input | Planner/coordinator | Output |
|---|---|---|---|
| Analyze | Snapshot technical + canonical SMC + market/risk context | Shared pure coordinator | Một canonical result/side dùng cho scenario |
| Scanner live | Live snapshot đã freeze cutoff + same canonical inputs | Cùng coordinator; không scorer riêng sau plan | Cùng selected ID/quality/plan nếu input giống |
| Fast prefilter | Cùng evaluation nhưng chỉ dùng early reject | Survivor reuse evaluation/canonical; không chấm lại | Không đổi selected result của survivor |
| Replay | Snapshot envelope/prefix tương ứng | Cùng evaluator/order/planner seam | So selected ID, trace, status và reasons |

Parity invariant: cùng symbol, cùng cutoff, cùng data/metadata/policy phải cho cùng candidate order, selected child, plan availability và rejection trace, không phụ thuộc list input permutation.

## 10. Anti-circular-import seam

Target dependency direction:

```text
smc_models / policy types
        ↑
smc_scorer -> smc_selection(coordinator/protocols) -> scenario planner
        ↓                         ↓
  smc_scoring_result <------------+
        ↑
 consumer/UI/persistence
```

Quy tắc module:

- `smc_scorer.py` chỉ trả evaluation/breakdown và import model/policy types; không import `scanner_scenario_producers.py`.
- `scanner_scenario_producers.py` expose pure `plan_for_candidate` seam; không import final canonical result để quyết định candidate.
- `smc_selection.py` (hoặc coordinator owner được Tech Lead chọn) chứa protocol/adapter type nhỏ, import scorer output và planner callable, không bị planner import ngược.
- `smc_scoring_result.py` chỉ serialize final result từ plain model/value types; không import pipeline/UI/network.
- `analysis_pipeline.py`, `scanner_release.py` và replay adapter gọi coordinator, không chứa bản chọn zone riêng.
- Consumer/technical projection chỉ đọc final canonical result; không gọi scorer hoặc planner lần nữa.

## 11. Case bắt buộc và expected

| Case | Candidate order/attempt | Expected |
|---|---|---|
| H4 quality 90 nhưng width >1 ATR; H1 quality 80 có plan | H4 trước theo quality, reject geometry; thử H1 | H1 selected, trace giữ H4 rejection, không H4 tuyệt đối |
| H4/H1 cùng quality/distance | Dùng timeframe tie-break H4 rồi stable ID | Kết quả deterministic |
| Candidate đầu thiếu TP; candidate sau có TP | Reject đầu `PLAN_TP_MISSING`, thử sau | Candidate sau selected; score không tính lại |
| Candidate đầu có plan nhưng Macro BLOCK | Dừng gate, không thử candidate khác | `BLOCKED`, không bypass bằng zone sau |
| Chỉ còn confirmed watch zone không plan | Không có successful attempt | Selected watch có `plan_available=false`, `WATCH_ZONE`, không READY |
| Tất cả zone invalid/expired | Không có usable candidate | `OUT_OF_STRATEGY`, selected null |
| Core data thiếu | Evaluator không tạo fake candidates | `DATA_UNAVAILABLE`, quality null |
| Candidate cùng setup, sibling khác family | Thử child theo order; dedupe evidence theo setup | Một selected child, không cộng B/L/C nhiều lần |

## 12. R16-05/R16-09 — shared planner policy và watch result

Đây là đề xuất semantics để Tech Lead duyệt, chưa thay runtime hoặc risk policy.

| Quyết định | Analyze hiện tại | Scanner hiện tại | Đề xuất owner chung / tác động cần duyệt |
|---|---|---|---|
| Candidate/entry/refinement | `risk_engine.py:build_trade_plan` hiện xây execution sub-zone | `scanner_scenario_producers.py:produce_scenario_plans` hiện neo entry tại original edge | Shared planner nhận `canonical_zone`; `refined_bounds` hợp lệ thì dùng làm entry rectangle, nếu thiếu thì gọi đúng một `refine_entry` từ original. BUY entry là proximal lower edge, SELL proximal upper edge; adapter không tự chọn child |
| Protective SL/invalidation | Hiện có thứ tự swing → preferred-zone boundary → ATR fallback, min-stop và SL floor | Hiện có `zone_low - atr`/`zone_high + atr` | Shared planner đề xuất dùng **đúng thứ tự risk_engine hiện hữu**: nearest structural swing + `swing_sl_buffer_atr`; thiếu swing thì distal original bound + `zone_sl_buffer_atr`; enforce `min_stop_distance=max(execution_atr*min_stop_distance_atr_mult, spread*min_stop_spread_mult)` và `sl_floor_buffer_atr`. Scanner adapter bỏ công thức 1 ATR riêng; đây là route behavior change chờ duyệt, không tự triển khai |
| TP | Hiện cascade equal-level → nearest target zone → Fib (non-range) → swing, validate sau far edge/clearance/RR | Hiện lấy nearest opposite technical level | Shared planner dùng một `take_profit_policy` với cascade risk_engine; thiếu candidate đạt ordering/clearance/min-RR trả `PLAN_TP_MISSING`, không tự bịa TP. Scanner adapter chuyển technical/SMC levels vào cùng cascade |
| Execution ATR | `atr_h4` finite-positive, fallback `atr_d1` | `atr_h4` finite-positive, fallback `atr_d1` | Shared input `execution_atr = first_finite_positive(technical.atr_h4, technical.atr_d1)` từ frozen snapshot; fallback D1 ghi `ATR_EXECUTION_FALLBACK_D1`; không dùng current/future. `formation_atr` vẫn chỉ phục vụ quality/zone formation |
| Width/distance | Có regime distance và execution-zone width | Có hard width `1 ATR` và distance `3 ATR` | Shared SMC pre-plan gate là width `<=1*formation_atr` và nearest-edge distance `<=3*execution_atr`; route-specific regime distance chỉ là outer risk gate, không được thay SMC gate. Analyze adapter có thể loại thêm nhưng không nới; chờ duyệt phần hợp nhất |
| min-RR/risk floor | Risk engine TP validator và minimum-stop guard | Producer tính `RR` và so `min_rr` | Shared planner tính `RR=abs(TP-entry)/abs(entry-SL)` trước spread; `plan_rr < min_rr` trả `PLAN_MIN_RR`; risk floor/account/portfolio là outer owner, không sửa S/B/Q/L/C hoặc đổi order |
| Technical fallback | Risk engine có technical support/resistance khi không preferred | Producer có technical levels | **Allowed proposal:** chỉ khi core SMC đã đánh giá đủ và không có confirmed/usable candidate (`NO_ZONE`) và caller bật `allow_technical_fallback`; output `source=technical_fallback`, selected SMC IDs null. **Blocked:** core unavailable, candidate invalid/expired, countertrend chưa CHoCH, hoặc selected SMC watch/no-plan; không dùng fallback để lách SMC/readiness |
| Cache dependency | Plan phụ thuộc technical/risk context hiện tại | Plan phụ thuộc technical ATR/levels | Tách evaluation cache và plan cache; plan key gồm snapshot/cutoff digest, canonical zone/refinement, technical levels, execution ATR, SL/TP/min-RR/risk policy. Không đưa route identity vào key; cùng semantic input qua Analyze/Scanner/replay phải có cùng plan |

Ví dụ expected của **policy đề xuất** (chưa phải runtime): cùng snapshot `BUY`, canonical entry `98.5`, SL `97.5`, TP `104`, `min_rr=3` cho `RR=5.5` → pass; nếu cùng entry/TP nhưng SL `96.5` thì `RR=2.75` → reject `PLAN_MIN_RR`. SELL `entry=101.5`, `SL=102.5`, `TP=96` cho `RR=5.5` → pass. Công thức duy nhất là `abs(TP-entry)/abs(entry-SL)`; spread không được lẫn vào pre-spread RR. Ví dụ ATR parity: H1 formation ATR `.80`, zone width `.60`, execution ATR lấy H4 `2.00`, entry distance `4.00` → width pass và distance pass vì `4.00 <= 6.00`; nếu H4 không hợp lệ thì dùng D1 ATR và ghi fallback reason. Cùng input/policy qua Analyze/Scanner/replay phải cho exact entry/SL/TP/ATR/RR/trace/IDs.

Confirmation-first selection example: A quality 90/M15 waiting và B quality 80/M15 confirmed đều có plan → rank chọn B; khi chỉ đổi M15 của A thành confirmed, rank chọn A. Quality của A và B, và quality của cùng candidate trước/sau M15, không đổi; selected ID có thể đổi theo selection policy.

Watch/no-plan canonical: nếu đã chọn zone confirmed/usable nhưng planner fail TP/min-RR/technical thì giữ `selected_setup_id`, `selected_zone_id`, quality và lifecycle; đặt `plan=null`, `plan_reference=null`, `plan_available=false`, status `WATCH_ZONE`. M15 expiry không xóa một plan đã tính hợp lệ: giữ `plan/reference`, `plan_available=true`, nhưng readiness là `WAITING_CONFIRMATION` và không được xét entry. Chỉ no-zone/core-unavailable/không có candidate hợp lệ mới selected IDs null. M15 thay đổi có thể đổi selected candidate theo confirmation rank, nhưng không đổi quality của candidate nào.

### Runtime tests tương lai (chưa chạy trong task 16)

Dùng cùng snapshot/policy để so Analyze/Scanner/replay exact entry/SL/TP/ATR/RR/trace/IDs; kiểm ATR H1/H4 khác nhau, TP missing, min-RR/risk floor, technical fallback, invalidation block và cold/warm cache. Đây là test sau khi Tech Lead duyệt owner, không phải bằng chứng runtime của hồ sơ này.

## 13. Tiêu chí hoàn thành task 13

- Đã chỉ rõ coordinator là nơi chọn cuối; scorer không chọn theo R:R và planner không chọn candidate.
- Đã chốt hard filter, thứ tự ranking, tie-break deterministic và cách thử candidate kế tiếp khi plan không hợp lệ.
- Đã chốt watch/no-plan, no-zone, core unavailable và market/account block không được lách bằng candidate khác.
- Đã chốt canonical result/trace/alternatives, parity Analyze/Scanner/Replay và seam chống import vòng.
- Không thay runtime trong task này. Việc triển khai coordinator/plan seam thuộc task 91–94 sau review task 16 và các mốc liên quan.
