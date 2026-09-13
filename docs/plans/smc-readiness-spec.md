# Đặc tả SMC readiness — task 12

> **Trạng thái:** DRAFT — chờ Tech Lead review tại task 16.  
> **Mục đích:** ánh xạ state SMC sang trạng thái consumer, xác định khi nào được xét entry và bảo đảm thiếu dữ liệu/hỏng zone/countertrend không bị biến thành tín hiệu sẵn sàng.

## 1. Hai khái niệm cần tách

`SMC readiness` không phải lệnh giao dịch và không thay thế các gate hiện có.

| Trường | Ý nghĩa |
|---|---|
| `can_consider_entry` | SMC đã có một setup confirmed, active, đúng hướng, có plan/geometry hợp lệ và confirmation cần thiết; consumer được phép đưa vào entry workflow |
| `can_execute` | Chỉ true khi `can_consider_entry`, snapshot fresh, mọi gate safety/macro/account/portfolio/journal PASS, score floors đạt và execution revalidation trước dispatch PASS |
| `candidate_status` | Trạng thái consumer hiện có: `READY_NOW`, `WAITING_CONFIRMATION`, `WATCH_ZONE`, `OUT_OF_STRATEGY`, `BLOCKED`, `DATA_UNAVAILABLE` |
| `smc_state` | State chi tiết của SMC: data quality, zone lifecycle, structure, visit, M15 và plan; không bị ép mất thông tin khi ánh xạ sang status tổng |

`READY_NOW` nghĩa là đủ điều kiện để đưa sang bước revalidation/execution review, không có nghĩa tự động gửi lệnh. `can_execute` không được set true chỉ vì quality cao.

## 2. Bảng state SMC → consumer

| SMC state | `candidate_status` | `can_consider_entry` | `can_execute` | Reason tối thiểu |
|---|---|---:|---:|---|
| Core D1/H4/H1 thiếu, malformed, cutoff/ATR bắt buộc không hợp lệ | `DATA_UNAVAILABLE` | Không | Không | `SMC_CORE_DATA_UNAVAILABLE` + reason theo TF |
| Dữ liệu core đủ nhưng chưa có confirmed/usable zone nào | `WATCH_ZONE` | Không | Không | `SMC_NO_VALID_SETUP` |
| Chỉ có candidate chưa confirmed | `WATCH_ZONE` | Không | Không | `SMC_ZONE_PENDING_CONFIRMATION` |
| Zone confirmed nhưng chưa `available_at` hoặc source event còn ở tương lai | `WATCH_ZONE` | Không | Không | `SMC_ZONE_NOT_AVAILABLE_YET` |
| Tất cả zone bị invalidated/expired/full-filled theo family hoặc sai hướng | `OUT_OF_STRATEGY` | Không | Không | `SMC_ZONE_INVALID_OR_EXPIRED` |
| Zone active, chưa visit | `WATCH_ZONE` | Không | Không | `SMC_WAITING_FOR_ZONE_VISIT` |
| Parent H4/H1 visit open/completed nhưng chưa có M15 entry confirmation cần thiết | `WAITING_CONFIRMATION` | Không | Không | `SMC_WAITING_REACTION` |
| M15 entry visit confirmed trong khi parent H4/H1 còn open | `READY_NOW` nếu plan và gate khác pass; nếu chưa thì giữ blocker tương ứng | Có thể | Chưa, cần revalidation | `SMC_M15_CONFIRMED_PARENT_OPEN` |
| Visit reacted nhưng confirmation trigger đã timeout/reclaim/visit mới | `WAITING_CONFIRMATION` | Không | Không | `SMC_TRIGGER_EXPIRED` hoặc reason cụ thể |
| M15 thiếu/không đủ trong setup yêu cầu M15 | `WAITING_CONFIRMATION` | Không | Không | `M15_DATA_UNAVAILABLE` |
| M15 đủ nhưng chưa có micro break/rejection follow-through | `WAITING_CONFIRMATION` | Không | Không | `M15_NO_CONFIRMATION` |
| Countertrend so với external bias, CHoCH chưa confirmed | `WATCH_ZONE` | Không | Không | `SMC_COUNTERTREND_UNCONFIRMED` |
| Countertrend đã CHoCH confirmed nhưng chưa có đủ entry confirmation/plan | `WAITING_CONFIRMATION` | Không | Không | `SMC_COUNTERTREND_CONFIRMED_WAITING_ENTRY` |
| Setup SMC hợp lệ nhưng geometry/planner không tạo được plan | `WATCH_ZONE` | Không | Không | `SMC_PLAN_UNAVAILABLE` |
| Setup và entry confirmation đủ nhưng gate ngoài có CAUTION/UNKNOWN non-critical | `WATCH_ZONE` | Không | Không | Gate reason; không đổi thành PASS |
| Bất kỳ gate BLOCK hoặc critical UNKNOWN | `BLOCKED` | Không | Không | Block codes của safety/macro/account/portfolio/journal |
| SMC, entry confirmation, plan và tất cả gate PASS; snapshot fresh | `READY_NOW` | Có | Chưa, cần revalidation | `SMC_READY_FOR_REVALIDATION` |

`NO_ZONE` và `DATA_UNAVAILABLE` là hai kết quả khác nhau: `NO_ZONE` nghĩa đã đánh giá đủ dữ liệu nhưng không có setup; `DATA_UNAVAILABLE` nghĩa chưa thể kết luận. Nếu một số zone hỏng nhưng còn zone confirmed usable, coordinator bỏ zone hỏng và đánh giá zone còn lại; chỉ dùng `OUT_OF_STRATEGY` khi không còn candidate hợp lệ.

## 3. SMC state machine cho consumer

```text
DATA_UNAVAILABLE
  └─ core data đủ -> NO_ZONE hoặc ZONE_CANDIDATE

ZONE_CANDIDATE -> ZONE_CONFIRMED
  ├─ chưa available/structure còn chờ -> WATCH_ZONE
  ├─ active, chưa visit -> WATCH_ZONE
  ├─ parent visit open/completed chưa reaction và M15 chưa confirm -> WAITING_CONFIRMATION
  ├─ M15 entry visit confirmed dù parent còn open -> READY_NOW nếu plan/gate pass
  ├─ reacted nhưng M15 thiếu/chưa confirm -> WAITING_CONFIRMATION
  ├─ countertrend chưa CHoCH -> WATCH_ZONE
  ├─ plan/geometry không có -> WATCH_ZONE
  └─ đủ local entry + external PASS -> READY_NOW -> revalidation

ZONE_CONFIRMED/ACTIVE -> INVALIDATED hoặc EXPIRED -> OUT_OF_STRATEGY
READY_NOW -> revalidation fail -> WAITING_CONFIRMATION / BLOCKED / OUT_OF_STRATEGY
```

Một snapshot chỉ tạo một verdict hiện tại cho mỗi side, nhưng giữ `smc_state_trace` để biết state nào đã dẫn tới verdict. Scan/restart không được hồi sinh trigger, visit hay M15 confirmation hết hạn.

## 4. Điều kiện được phép xét entry

`can_consider_entry=true` chỉ khi tất cả điều kiện SMC-local sau đúng:

1. Core D1/H4/H1 data hợp lệ, cùng cutoff và đủ ATR/reference history.
2. Có child zone confirmed với `available_at <= as_of`, đúng side và chưa invalidated/expired; FVG full fill không được coi là imbalance active.
3. Structure event/bias không conflict. Countertrend chỉ được đi tiếp sau CHoCH confirmed + follow-through/BOS mới theo `smc-structure-spec.md`.
4. Lifecycle visit/reaction phù hợp với loại entry. Parent H4/H1 open tự nó không block khi M15 entry visit đã confirm; open/chạm đơn thuần chưa đủ nếu entry confirmation chưa đạt.
5. Nếu policy entry yêu cầu M15: M15 đủ dữ liệu, trigger thuộc visit hiện tại/vừa hoàn tất còn hiệu lực, micro break hoặc rejection follow-through đạt; M15 thiếu thì không xét entry.
6. Protective/original geometry hợp lệ, width/distance đạt shared policy và planner trả `plan_available=true`.
7. Selected setup, selected zone, selected entry visit, confirmation event và plan reference cùng lineage; `parent_lifecycle_visit_id` có thể null trước khi H4/H1 phát visit event và không nằm trong identity của M15 trigger. Consumer không tự dò zone khác.

Nếu một điều kiện trên fail, consumer vẫn có thể giữ `WATCH_ZONE` hoặc `WAITING_CONFIRMATION` để giải thích, nhưng `can_consider_entry=false`.

`can_execute=true` chỉ sau khi các điều kiện trên đúng và thêm:

- snapshot không stale/future-skew;
- MarketSafety, Macro, Account, Portfolio và Journal gate đều `PASS`;
- technical/setup score floors đã được policy chốt và đạt;
- execution revalidation tại cutoff mới xác nhận selected zone/visit/trigger còn sống;
- không có safety, macro, risk, account hoặc portfolio block.

Không được điều chỉnh SL/TP, risk floor, score floor, M15 policy hoặc đổi candidate để lách một gate.

## 5. Các trường hợp bắt buộc tách riêng

### 5.1 Thiếu M15

| Điều kiện | Quality B/Q/L/C | Consumer | Entry |
|---|---|---|---|
| D1/H4/H1 đủ, zone active, M15 chưa được fetch | Giữ nguyên | `WAITING_CONFIRMATION` + `M15_DATA_UNAVAILABLE` | Không xét entry cần M15 |
| M15 có nhưng <15 candle | Giữ nguyên | `WAITING_CONFIRMATION` + `M15_INSUFFICIENT_DATA` | Không |
| M15 đủ nhưng chưa trigger | Giữ nguyên | `WAITING_CONFIRMATION` + `M15_NO_CONFIRMATION` | Không |
| M15 trigger đạt và các gate khác pass | Không đổi quality vì M15 | Có thể `READY_NOW` | Được đưa sang revalidation |

Thiếu M15 không bị trừ quality, không biến thành no-zone và không tạo đường tắt “bỏ M15 để tăng số lệnh”.

### 5.2 Vùng hỏng hoặc hết hạn

- `invalidated`: close phá protective/original distal boundary với buffer; không được dùng refined bounds để cứu zone.
- `expired`: vượt zone lifetime hoặc trigger lifetime; trigger cũ không sống lại khi mở app/scan lại.
- `filled`: FVG full fill không còn contribution integrity của imbalance; original zone vẫn giữ history. OB/S-D sibling cùng setup được đánh giá độc lập.
- Nếu candidate đầu hỏng nhưng candidate sau cùng setup còn usable, coordinator thử candidate sau và giữ rejection reason; nếu không còn candidate thì `OUT_OF_STRATEGY`.

### 5.3 Countertrend

| Tình trạng | Consumer | Entry |
|---|---|---|
| H1/H4 đi ngược D1/external bias, chưa CHoCH confirmed | `WATCH_ZONE` + `SMC_COUNTERTREND_UNCONFIRMED` | Không |
| Có CHoCH candidate nhưng chưa follow-through/BOS mới | `WATCH_ZONE` hoặc `WAITING_CONFIRMATION` tùy visit | Không |
| CHoCH confirmed + structure mới cùng hướng setup | `WAITING_CONFIRMATION` cho tới khi M15/plan đủ | Chỉ sau các gate còn lại |
| External continuation ngược chiều đã confirmed | `OUT_OF_STRATEGY` hoặc `BLOCKED` nếu policy gate ghi block | Không |

Quality B/Q/L/C không được “cứu” countertrend chưa xác nhận. Countertrend không được gọi là aligned chỉ vì H1 đang gần zone.

### 5.4 No-zone

Sau khi core data đủ và toàn bộ candidate đã qua detector/lifecycle/geometry:

```text
smc_state=NO_ZONE
quality_raw=0
selected_zone_id=null
candidate_status=WATCH_ZONE
can_consider_entry=false
reason=SMC_NO_VALID_SETUP
```

No-zone không phải lỗi dữ liệu và không được biến thành `DATA_UNAVAILABLE` để che thiếu kiểm thử; cũng không tạo zone giả từ technical fallback.

### 5.5 Thiếu core data

```text
smc_state=DATA_UNAVAILABLE
quality_raw=null
selected_zone_id=null hoặc không chứng nhận
candidate_status=DATA_UNAVAILABLE
can_consider_entry=false
can_execute=false
```

Giữ reason cụ thể (`SMC_D1_MISSING`, `SMC_H4_COVERAGE_GAP`, `SMC_ATR_REFERENCE_UNAVAILABLE`, …). Không điền score 0 rồi gọi là đã đánh giá xong, không dùng H4 thay D1/H1 và không để technical fallback bypass SMC core gate.

## 6. Gate precedence và composition

Khi nhiều vấn đề đồng thời, dùng precedence sau để không báo optimistic status:

1. Snapshot/cutoff/core data unavailable → `DATA_UNAVAILABLE`.
2. Safety/macro/account/portfolio/journal `BLOCK` hoặc critical `UNKNOWN` → `BLOCKED`.
3. Không còn zone usable do invalid/expired/wrong-side → `OUT_OF_STRATEGY`.
4. Countertrend conflict chưa có reversal hoặc không có plan → `WATCH_ZONE`.
5. Zone/visit/M15 trigger đang chờ → `WAITING_CONFIRMATION`.
6. Zone active nhưng chưa đến visit hoặc không có setup → `WATCH_ZONE`.
7. Tất cả local/external conditions pass → `READY_NOW`, vẫn bắt buộc revalidation.

Một gate `CAUTION`/non-critical `UNKNOWN` không được trả `READY_NOW`; safety/macro không được mutate điểm Technical/SMC để làm status đạt. Gate blocked giữ score và scenario để giải thích, nhưng không cấp quyền entry.

## 7. Contract output cho consumer/UI/persistence

Mỗi side nên mang các trường sau, dù status là waiting/blocked/unavailable:

| Trường | Quy tắc |
|---|---|
| `smc_state` | State chi tiết trước khi ánh xạ status |
| `candidate_status` | Một trong sáu status hiện có |
| `can_consider_entry` / `can_execute` | Boolean được suy ra từ policy, không nhận từ raw zone |
| `quality_raw` / `quality_score` | `0` cho no-zone đã đánh giá đủ; `null` cho data unavailable |
| `selected_setup_id` / `selected_zone_id` | Giữ ID của zone confirmed/usable đã chọn cả khi watch/no-plan; chỉ null ở `NO_ZONE`, core unavailable hoặc không có candidate hợp lệ |
| `selected_visit_id` / `confirmation_event_id` | `selected_visit_id` là M15 `entry_visit_id` khi đã có entry visit, kể cả plan null; null khi chưa visit. `confirmation_event_id` chỉ có khi trigger confirm; `parent_lifecycle_visit_id` có thể null trước parent H4/H1 event |
| `m15_status` | `not_required`, `missing`, `waiting`, `confirmed`, `expired` |
| `plan_available` | Không được suy ra từ R:R để sửa SMC quality |
| `entry_blockers` | Reason codes có owner và thời điểm |
| `gate_snapshot` | Safety/macro/account/portfolio/journal status và freshness |
| `revalidation_required` | Luôn true trước dispatch, kể cả `READY_NOW` |

Consumer, UI và persistence chỉ đọc contract này. Không tự kiểm tra lại raw candle, không tự chọn zone thứ hai, không tự bỏ M15 và không map null thành 0.

## 8. Ví dụ mapping

| Input thực tế | `smc_state` | Consumer | Entry |
|---|---|---|---|
| H4 thiếu 20 candle, D1/H1 có | `DATA_UNAVAILABLE` | `DATA_UNAVAILABLE` | Không |
| 60/60/30 đủ, không OB/FVG/S-D đạt | `NO_ZONE` | `WATCH_ZONE` | Không |
| OB candidate có departure nhưng chưa BOS | `ZONE_CANDIDATE` | `WATCH_ZONE` | Không |
| H4 OB confirmed, chưa visit | `ACTIVE_WAITING_VISIT` | `WATCH_ZONE` | Không |
| Visit open trong zone | `VISIT_OPEN` | `WAITING_CONFIRMATION` | Không |
| Visit reacted, M15 fetch thất bại | `WAITING_M15` | `WAITING_CONFIRMATION` | Không |
| Visit reacted, M15 confirmed, H4 countertrend chưa CHoCH | `COUNTERTREND_UNCONFIRMED` | `WATCH_ZONE` | Không |
| Mọi SMC local gate pass, Macro gate CAUTION | `LOCAL_READY_EXTERNAL_CAUTION` | `WATCH_ZONE` | Không |
| Mọi gate PASS, snapshot fresh, plan và M15 pass | `READY_FOR_REVALIDATION` | `READY_NOW` | Được xét/revalidate, chưa tự dispatch |
| Zone selected close phá distal boundary | `ZONE_INVALIDATED` | `OUT_OF_STRATEGY` | Không |

## 9. Invariants cần khóa ở test sau review

- Core missing luôn khác no-zone: `null/DATA_UNAVAILABLE` không bị đổi thành `0/WATCH_ZONE`.
- M15 thay đổi không làm đổi B/Q/L/C hoặc quality; chỉ đổi readiness/entry confirmation.
- Zone invalid/expired/full-filled không thể trở thành `READY_NOW` nhờ score cao, refined bounds hoặc technical fallback.
- Countertrend chưa CHoCH confirmed không được `can_consider_entry`.
- `READY_NOW` luôn `revalidation_required=true`; bất kỳ gate block/caution/unknown phù hợp đều ngăn execution.
- No-zone không tạo selected zone/plan; candidate pending không tạo entry. Watch zone hợp lệ không phải no-zone: giữ selected IDs/quality/lifecycle nhưng `plan=null`, `plan_reference=null`, `plan_available=false`.
- Consumer đọc đúng selected setup/zone/visit/event cùng lineage; không tự chọn lại hoặc bypass gate khác.

## 10. R16-02/R16-03/R16-09 — visit entry và canonical watch-no-plan

Lifecycle parent của H4/H1 là owner của quality; M15 chỉ tạo `entry_visit_id` và có thể liên kết nullable tới `parent_lifecycle_visit_id`. Nếu H4/H1 chưa phát canonical visit event tại lúc M15 touch thì link là `null`; confirmation ID không phụ thuộc link và không đổi khi link được bổ sung sau H4 close. Anchor là M15 đầu tiên overlap sau `available_at`, follow-through `3` bar, trigger còn sống tới `delta=12` và hết hạn tại candle `delta=13`. Confirmation hoặc expiry của M15 không sửa B/Q/L/C, `quality_raw/score`, selected candidate quality hay parent lifecycle. M15 thiếu/stale/expired trả `WAITING_CONFIRMATION`, `M15_DATA_UNAVAILABLE` hoặc `M15_NO_CONFIRMATION`, không có quality downgrade/penalty mới.

Canonical result có ba trường hợp khác nhau:

| Trường hợp | selected IDs/quality/lifecycle | plan/reference | `plan_available`/status |
|---|---|---|---|
| Zone hợp lệ có plan | Giữ ID và snapshot của zone/visit đã chọn | Có cùng lineage | `true` / READY hoặc gate ngoài |
| Zone hợp lệ nhưng TP/min-RR/technical plan chưa đạt | Giữ ID, quality và lifecycle của watch zone | `null` | `false` / WATCH_ZONE + `SMC_PLAN_UNAVAILABLE` |
| M15 trigger expired nhưng geometric plan vẫn hợp lệ | Giữ ID, quality, lifecycle và plan đã tính | Giữ plan/reference | `true` về mặt plan; readiness `WAITING_CONFIRMATION` + `TRIGGER_EXPIRED`, không được xét entry |
| Core đủ nhưng không có zone hợp lệ | `null`, quality raw `0` | `null` | `false` / WATCH_ZONE + `SMC_NO_VALID_SETUP` |

Candidate chưa confirmed không được gọi là selected usable watch zone; nó chỉ là pending trace. Vì vậy `watch-no-plan` và `no-zone` không thể bị gộp bởi serializer/UI.

BUY: H4 `Z4` available 08:00, M15 touch 08:15 và confirm 08:45 khi H4 chưa đóng → `entry_visit_id=Z4:m15-visit-1`, `parent_lifecycle_visit_id=null`, có thể READY nếu plan/gate pass. Khi H4 đóng 12:00, parent link có thể được bổ sung mà trigger ID không đổi. Nếu M15 hết hạn tại delta 13 → selected candidate/quality/lifecycle và plan còn hợp lệ được giữ, `plan_available=true` nhưng readiness `WAITING_CONFIRMATION`. Nếu không có plan từ đầu mới là `WATCH_ZONE`/`plan_available=false`. SELL là mirror. Thay chuỗi M15 không được làm đổi quality của từng candidate.

## 11. Tiêu chí hoàn thành task 12

- Có bảng SMC state → consumer status và cờ `can_consider_entry`/`can_execute`.
- Thiếu M15, zone hỏng/hết hạn, countertrend, no-zone và thiếu core data có kết quả/reason riêng.
- Có điều kiện `READY_NOW` rõ ràng, luôn giữ execution revalidation và không bypass safety/macro/risk/account/portfolio/journal gate.
- Có precedence, contract output, ví dụ mapping và invariants để viết tests.
- Không thay runtime trong task này. Việc đưa readiness vào scorer/result/composition/execution thuộc task 90 và 101–116 sau review task 16/100/116.
