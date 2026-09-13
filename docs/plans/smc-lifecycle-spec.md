# Đặc tả lifecycle SMC — task 10

> **Trạng thái:** DRAFT — chờ Tech Lead review tại task 72.  
> **Phạm vi:** formed, entered, exited, reacted, invalidated, expired; visit open/completed; tolerance, penetration, FVG fill và trigger expiry.

## 1. Nguyên tắc và thứ tự xử lý

Lifecycle được tính từ history nến đã đóng, sau khi detector đã hoàn tất departure và zone có `available_at`. Không dùng số lần scanner chạy để tăng tuổi, visit hoặc dwell.

Thứ tự xử lý cho mỗi candle tại cutoff:

```text
validate candle/time -> check availability -> check invalidation/expiry
-> update FVG fill -> classify overlap/entry/exit
-> update penetration/dwell -> evaluate reaction/follow-through
-> emit immutable event + current lifecycle state
```

Các mốc thời gian dùng `close_at` của candle/event. Pivot time, base time hoặc thời điểm wick chạm không được dùng làm thời điểm zone/visit có thể sử dụng.

## 2. Bảng sự kiện lifecycle

| Sự kiện | Điều kiện phát | Dữ liệu phải lưu | Ảnh hưởng |
|---|---|---|---|
| `formed` | Detector hoàn tất base/gap/departure trên candle đã đóng | `zone_id`, family, direction, original bounds, formation/departure indices và times | Tạo zone record; chưa mặc nhiên usable |
| `entered` | Sau `departure_end`/`available_at`, candle đã đóng overlap zone lần đầu sau trạng thái outside | `visit_id`, `entered_at`, start index, entry penetration | Mở một visit; không tính departure là retest |
| `exited` | Visit đang mở và candle đã đóng rời vùng vượt exit tolerance | `visit_id`, `exited_at`, end index, dwell, max penetration | Đóng visit; cho phép đánh giá reaction trong follow-through window |
| `reacted` | Visit đã exited và trong tối đa 3 bar có follow-through đúng hướng hoặc micro BOS | `visit_id`, `reacted_at`, trigger event, magnitude/reason | Đánh dấu phản ứng thành công; không phải mọi exit đều reacted |
| `invalidated` | Close phá protective/original distal boundary vượt break buffer | `invalidated_at`, invalidation candle, boundary, reason | Zone không còn usable; không đổi thành breaker/inverse |
| `expired` | Zone vượt lifetime theo timeframe/family hoặc trigger hết hạn theo policy | `expired_at`, expiry kind, threshold, reason | Không selected/READY; giữ history để replay |

`formed` và `entered` có thể tồn tại mà không có `exited`; `reacted` luôn phải tham chiếu một visit có `exited`. `invalidated` và `expired` là terminal đối với usability, nhưng event history vẫn bất biến.

## 3. Trạng thái zone và visit

### Zone state

| State | Điều kiện | Có chọn làm setup/entry? |
|---|---|---:|
| `candidate` | Detector thấy hình học nhưng zone chưa đạt confirmation của family | Không |
| `confirmed` | Zone đạt confirmation và `available_at` đã được xác định | Chỉ sau các gate lifecycle/geometry |
| `active` | Confirmed, available, chưa invalidated/expired | Có thể selection/watch |
| `tested` | Active đã có ít nhất một visit hoàn tất | Có, quality phản ánh visit |
| `reacted` | Có visit completed với follow-through đạt | Có, nếu các gate khác đạt |
| `filled` | FVG full fill; imbalance không còn active | Không chấm FVG như imbalance; child OB/S-D cùng setup có thể còn |
| `invalid` | Close phá protective boundary | Không |
| `expired` | Hết lifetime | Không |

### Visit state

| State | Điều kiện | Cách đếm |
|---|---|---|
| `open` | Đã `entered`, candle mới nhất vẫn overlap zone theo entry/exit policy | Không tính là retest hoàn tất hoặc reacted |
| `completed_unreacted` | Đã `exited` nhưng chưa có follow-through | Tính một independent visit, không tính reaction |
| `completed_reacted` | Đã `exited` và đạt follow-through trong window | Tính một independent visit và một reaction event |
| `closed_by_invalidation` | Zone bị invalidated trong lúc visit mở | Đóng visit với reason; invalidation không tự là reaction |

Các candle overlap liên tiếp thuộc cùng một visit. Chỉ sau khi visit đã exited, một chuỗi outside mới rồi overlap lại mới tạo `visit_id` mới. Mở lại ứng dụng hoặc chạy lại snapshot không được tạo visit mới.

## 4. Entry/exit tolerance

Ngưỡng mặc định là:

```text
zone_tolerance = max(1 * tick, 0.05 * ATR_current_same_TF)
```

- `tick` lấy từ metadata broker theo contract task 6; thiếu tick/ATR phải ghi unknown cho rule phụ thuộc, không âm thầm chọn digits.
- Entry overlap được đánh giá với vùng mở rộng bởi tolerance: candle có `low <= high + tolerance` và `high >= low - tolerance` được xem là chạm/overlap.
- Candle departure và mọi candle trước `available_at` bị loại khỏi lifecycle visit.
- Một visit thoát khi candle đã đóng không còn overlap với vùng mở rộng bởi tolerance. Wick vượt biên nhưng candle vẫn overlap không tạo exit riêng.
- Để tránh rung biên, một candle nằm trong khoảng tolerance không được vừa exit vừa mở visit mới. Cần ít nhất một candle outside hợp lệ trước lần re-entry.
- `exit_tolerance` không làm thay original bounds, không nới protective invalidation boundary và không biến giá close sai hướng thành reaction.

## 5. Penetration và dwell

`penetration_ratio` nằm trong `[0, 1]`, đo độ sâu wick vào zone trong mỗi candle overlap:

- BUY: `depth = (zone_high - clamp(candle.low, zone_low, zone_high)) / width`.
- SELL: `depth = (clamp(candle.high, zone_low, zone_high) - zone_low) / width`.
- Width bằng 0 là geometry invalid; không tạo penetration giả.
- Lưu `max_penetration_ratio` của visit và `max_mitigation_ratio` của zone riêng nhau.
- `penetration >= 0.50` là deep mitigation theo bảng task 8; không đồng nghĩa invalidation.
- Close vượt distal boundary quá break buffer mới là invalidation. Wick xuyên boundary được ghi penetration/sweep evidence, không tự phá zone.
- `bars_spent_inside` đếm số candle đóng overlap trong visit; `dwell` là chuỗi liên tiếp của visit hiện tại, không cộng theo số lần polling.

## 6. Reacted và follow-through

Một visit chỉ được đánh dấu `reacted` khi đã exited và trong tối đa 3 candle sau exit có một bằng chứng cùng hướng:

- BUY: close ra phía trên zone bằng ít nhất `0.25*ATR_current`, hoặc tạo micro BOS bullish hợp lệ.
- SELL: close ra phía dưới zone bằng ít nhất `0.25*ATR_current`, hoặc tạo micro BOS bearish hợp lệ.
- Candle chỉ chạm zone, candle còn nằm trong zone, hoặc candle đóng cùng màu ở xa zone nhưng không thuộc cửa sổ follow-through đều không phải reaction.
- Nếu candle follow-through phá distal boundary trước khi đạt reaction hợp lệ, ưu tiên `invalidated`; không gán reaction để cứu zone.
- Open visit không được gọi là reacted. Nếu follow-through xảy ra cùng candle exit, emit `exited` trước rồi `reacted` cùng close time theo thứ tự event.
- Reaction của D1 chỉ có hiệu lực trong 20 D1 bar sau formation/visit theo task 8; proximity hiện tại không phải reaction.

## 7. FVG partial/full fill

FVG dùng original gap bounds và remaining gap riêng, không dùng một quy tắc mitigation chung với OB/S-D.

### Bullish FVG

Original bounds `[low, high] = [first.high, third.low]`, giá lấp từ `high` xuống `low`:

```text
remaining_low  = original_low
remaining_high = min(original_high, lowest_valid_low_since_formation)
```

`remaining_high` được clamp trong original bounds. Fill ratio là phần gap đã đi từ `original_high` về phía `original_low`, clamp `[0,1]`.

### Bearish FVG

Original bounds `[low, high] = [third.high, first.low]`, giá lấp từ `low` lên `high`:

```text
remaining_low  = max(original_low, highest_valid_high_since_formation)
remaining_high = original_high
```

`remaining_low` được clamp trong original bounds. Khi remaining width nhỏ hơn hoặc bằng:

```text
full_fill_tolerance = max(1 * tick, 0.05 * original_gap_width)
```

FVG chuyển `filled`, `fill_ratio=1.0`, không còn được chấm như imbalance active. Full fill không đổi `zone_id`, original bounds, formation time, protective geometry hoặc setup lineage. Nếu close tiếp tục phá protective boundary vượt buffer, emit thêm `invalidated`; full fill tự nó không phải breaker.

## 8. Invalidation và expiry

### Invalidation

Protective boundary là distal boundary của original zone:

- BUY: invalid nếu close `< original_low - max(1*tick, 0.05*ATR)`.
- SELL: invalid nếu close `> original_high + max(1*tick, 0.05*ATR)`.

Close đúng trong tolerance không invalid. Wick-only được ghi observation/penetration. Khi invalidation xảy ra trong open visit, đóng visit bằng `closed_by_invalidation`, rồi emit `invalidated`; visit không được xem là completed_reacted.

### Expiry của zone

Lifetime stale baseline theo timeframe là D1 `20`, H4 `30`, H1 `50`, M15 `80` bar; `age_bars > threshold` chuyển zone sang `expired` tại close candle vượt ngưỡng. Expiry không xóa protected state, original bounds, visit history hoặc setup ID.

### Expiry của trigger

Trigger expiry là thời hạn của một confirmation/entry trigger, độc lập với lifetime zone:

- M15 confirmation sau visit: confirmation close hợp lệ ở `delta=1..3`; trigger còn sống qua `delta=12`; candle đóng tại `delta=13` chuyển `TRIGGER_EXPIRED`.
- Structure trigger lifetime theo bảng task 8: D1 `20`, H4 `40`, H1 `80`, M15 `48` bar.
- Khi trigger hết hạn, gán `trigger_expired_at` và reason `TRIGGER_EXPIRED`; zone confirmed còn history nhưng không được dùng trigger cũ để READY.
- Re-entry/visit mới phải tạo trigger window mới từ visit mới; không hồi sinh confirmation cũ.

Nếu cùng một candle vừa chạm expiry vừa phá boundary, xử lý terminal theo thứ tự: `invalidated` nếu close phá boundary; nếu không thì `expired`. Không tạo event reaction sau terminal state.

## 9. Timeline mẫu

| Thời điểm | Giá/candle | Sự kiện | Kết quả |
|---|---|---|---|
| T0 close | Departure hoàn tất | `formed` | Zone có original bounds; lifecycle visit chưa bắt đầu |
| T1 close | Candle đầu tiên overlap sau `available_at` | `entered` | Visit-1 `open`, penetration được ghi |
| T2–T3 close | Vẫn overlap | — | Cùng Visit-1, dwell tăng, không tạo visit mới |
| T4 close | Candle outside vượt exit tolerance | `exited` | Visit-1 `completed_unreacted` tạm thời |
| T5 close | Close cùng hướng vượt `0.25 ATR` | `reacted` | Visit-1 `completed_reacted` |
| T6 close | Close phá distal boundary + buffer | `invalidated` | Zone terminal, không selection |
| Tn close | Tuổi vượt lifetime | `expired` | Zone historical only |

Nếu T4 close đồng thời phá distal boundary, T4 phát `exited` rồi `invalidated`; không phát `reacted`. Nếu T5 nằm ngoài trigger window, visit giữ `completed_unreacted` và trigger cũ hết hạn.

## 10. Bằng chứng và reason codes

| Trường/mã | Nội dung |
|---|---|
| `visit_id` | ID ổn định theo `zone_id` và thứ tự visit causal |
| `entered_at` / `exited_at` / `reacted_at` | Close time UTC của event tương ứng; null nếu chưa xảy ra |
| `visit_state` | `open`, `completed_unreacted`, `completed_reacted`, `closed_by_invalidation` |
| `max_penetration_ratio` | Độ sâu lớn nhất của một visit, `[0,1]` |
| `bars_spent_inside` | Dwell candle thực tế trong visit |
| `remaining_bounds` / `fill_ratio` | Chỉ cho FVG; original bounds bất biến |
| `invalidation_reason` | Boundary, direction, candle và buffer đã dùng |
| `expiry_reason` | Zone lifetime hay trigger lifetime; không gộp hai loại |
| `M15_NO_CONFIRMATION` | Trigger/visit không có follow-through hợp lệ hoặc đã timeout |
| `ZONE_INVALIDATED` | Close phá protective boundary |
| `ZONE_EXPIRED` | Zone vượt lifetime |
| `TRIGGER_EXPIRED` | Confirmation/entry trigger vượt cửa sổ |

## 11. R16-02 — quan hệ lifecycle H4/H1 và M15 entry visit

Đây là contract chuẩn khi mô tả visit, anchor và confirmation.

- `zone_lifecycle_visit_id` của H4/H1 do chính candle H4/H1 sở hữu. Formation, exit, reaction, invalidation, expiry và B/Q/L/C chỉ đọc timeframe nguồn; M15 không được đóng/mở visit H4/H1 và không được thay đổi quality.
- M15 có visit riêng `entry_visit_id = <zone_id>:m15-visit-N`, mở bởi candle M15 đầu tiên overlap sau `available_at`; parent H4/H1 có thể vẫn `open` vì candle H4/H1 chưa đóng hoặc chỉ wick-overlap. `parent_lifecycle_visit_id` là **nullable**: nếu tại thời điểm M15 touch chưa có canonical visit event của H4/H1 thì giữ `null`, không chặn entry visit.
- `visit_anchor_at` là close time của M15 candle đầu tiên overlap. Các candle overlap liên tiếp giữ cùng entry visit; candle đóng ngoài exit tolerance kết thúc visit, re-entry sau đó tạo visit mới. `trigger_anchor_at=visit_anchor_at`; confirmation hợp lệ khi `1 <= m15_bars_since_anchor <= 3`, trigger expiry ở candle thứ `13` (`delta=12` là biên cuối còn sống).
- `confirmation_event_id = <zone_id>:m15-visit-N:confirm-M` không chứa parent visit ID nên bất biến khi parent link được bổ sung sau H4 close. Nếu H4/H1 sau đó phát canonical visit, projection chỉ điền `parent_lifecycle_visit_id` vào record/audit, không đổi trigger ID. M15 thiếu, stale, expired hoặc đổi visit chỉ đổi `m15_status/readiness/confirmation_event_id`; quality, B/Q/L/C, original bounds và parent lifecycle giữ nguyên.

### Timeline BUY/SELL

| Side | H4/H1 lifecycle | M15 entry visit | Expected |
|---|---|---|---|
| BUY | H4 zone `Z4` available 08:00; candle H4 08:00–12:00 chưa đóng, M15 touch 08:15 | `Z4:m15-visit-1`, `parent_lifecycle_visit_id=null`; confirm 08:45 (`delta=2`) | M15 confirmed; parent link null hợp lệ; plan/readiness có thể pass nếu gate khác pass; B/Q/L/C không đổi |
| BUY | H4 đóng 12:00 và canonical parent visit được tạo sau đó | Giữ `Z4:m15-visit-1:confirm-1`; projection điền parent ID nếu có | Trigger ID không đổi; quality/lifecycle parent được tính theo H4, không backdate M15 thành H4 visit |
| BUY | M15 overlap 08:15 rồi không confirm đến delta 12; candle delta 13 đóng | visit-1 trigger expired; re-entry tạo visit-2 với anchor mới | Confirmation quyền bị hủy, nhưng geometric `plan` còn hợp lệ thì giữ plan/plan_available; readiness `WAITING_CONFIRMATION` |
| SELL | H1 `Z1` open, M15 wick overlap 09:15 nhưng close sai màu; sau đó rời và vào lại | visit-1 rejected/exit; re-entry `Z1:m15-visit-2` | H1 lifecycle/quality không đổi; confirmation ID mới chỉ khi visit-2 đạt |

Thay toàn bộ chuỗi M15 bằng chuỗi khác nhưng giữ snapshot H4/H1 và cùng canonical candidate phải cho cùng B/Q/L/C, quality và parent lifecycle của candidate đó. Selection có thể đổi `selected_setup_id`/`selected_zone_id` hoặc final raw nếu confirmation rank đổi (ví dụ B→A trong selection spec); đó không phải thay đổi quality hay lifecycle của cùng candidate. Đây là invariant cho runtime test tương lai; phần này chỉ sửa hồ sơ.

## 12. Tiêu chí hoàn thành task 10

- Có bảng và state transition cho `formed`, `entered`, `exited`, `reacted`, `invalidated`, `expired`.
- Visit open/completed được phân biệt; departure không tính retest; candle overlap liên tiếp không tạo visit giả.
- Entry/exit tolerance, penetration, dwell, reaction follow-through và D1 reaction lifetime đã có giá trị/điều kiện biên.
- FVG partial/full fill có remaining bounds và fill ratio riêng; full fill không đổi original bounds/ID và không tự thành breaker.
- Zone expiry và trigger expiry là hai khái niệm riêng; trigger hết hạn không hồi sinh bằng scan sau.
- Không thay runtime trong task này. Việc đưa lifecycle contract vào `smc_models.py`/`smc_lifecycle.py` và viết regression tests thuộc task 57–65 sau review task 56.
