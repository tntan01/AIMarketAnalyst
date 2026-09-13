# Đặc tả cấu trúc SMC — trend, BOS và CHoCH

Ngày: 2026-09-10. Trạng thái: DRAFT — chờ Tech Lead duyệt tại task 16. Tài liệu này là quy tắc đầu vào cho task 25–37; chưa thay đổi runtime.

## 1. Đối tượng và nguyên tắc chung

- Cấu trúc được tính riêng cho external và internal; cùng semantics, khác pivot width đã khóa ở bảng tham số.
- Chỉ swing đã confirmed mới được dùng làm level, protected swing, liquidity pool hoặc trigger. Mỗi swing có `swing_id`, `pivot_time` và `confirmed_at`; không dùng index rolling làm identity.
- Mọi quyết định structure dùng candle đã đóng tại snapshot `as_of`. `occurred_at` của break là thời điểm đóng của candle phá mức; không backdate về pivot time. `confirmed_at` là thời điểm đủ điều kiện xác nhận follow-through.
- BUY và SELL là hai phép đối xứng: đổi hướng giá và đổi high/low, HH/HL ↔ LH/LL, bullish ↔ bearish, protected low ↔ protected high.
- Equal high/low trong tolerance được coi là một level/pool; không ghép high và low chỉ vì cùng vị trí trong hai danh sách độc lập.
- Wick vượt mức nhưng close quay lại không phải BOS/CHoCH. Đây là break observation/sweep candidate và không thay đổi trend hoặc protected level.

## 2. State cấu trúc

| State | Điều kiện vào | Ý nghĩa/đầu ra | Điều kiện rời |
|---|---|---|---|
| `unknown` | Chưa đủ confirmed high/low, dữ liệu thiếu, hoặc chuỗi không định hướng | Không có bias, BOS, CHoCH hay protected level usable; giữ reason | Đủ chuỗi swing hợp lệ → bullish/bearish; dữ liệu lỗi vẫn unknown |
| `bullish` (`HH/HL`) | High sau cao hơn high trước và low sau cao hơn low trước, với tolerance | Trend tăng; theo dõi continuation high và protected low | BOS tăng giữ bullish; close phá protected low mở bearish CHoCH candidate; dữ liệu mâu thuẫn có thể là mixed nhưng không tự đảo |
| `bearish` (`LH/LL`) | High sau thấp hơn high trước và low sau thấp hơn low trước, với tolerance | Trend giảm; theo dõi continuation low và protected high | BOS giảm giữ bearish; close phá protected high mở bullish CHoCH candidate; dữ liệu mâu thuẫn có thể là mixed nhưng không tự đảo |
| `mixed` | Hai chuỗi high/low mới nhất không cùng hướng hoặc không đủ quan hệ | Có lịch sử swing nhưng chưa có trend directional usable | Chỉ chuyển khi chuỗi mới thỏa điều kiện bullish/bearish; không gán mặc định up/down |
| `*_choch_candidate` | Close phá protected level ngược chiều với buffer | Ghi nhận khả năng đảo chiều; trend cũ còn là active context, candidate chưa được dùng như confirmed reversal | Reclaim → invalidated về trend cũ; follow-through đủ → `*_choch_confirmed`; timeout → expired, không xóa protected history |

## 3. Bootstrap

1. Không có ít nhất một cặp high/low đã confirmed và quan hệ directional rõ: `unknown`.
2. Có đủ swing nhưng high/low không đồng hướng, equal trong tolerance hoặc timestamp không hợp lệ: `mixed`/data-quality state, không phát event.
3. Khi đã có chuỗi HH/HL, state là bullish; khi có chuỗi LH/LL, state là bearish. Bootstrap không dùng leg count để biến một break đơn lẻ thành reversal confirmed.
4. Pivot phải chờ đủ nến bên phải theo pivot width. Một pivot nằm ở cuối snapshot nhưng chưa đủ nến xác nhận không được dùng, kể cả giá hiện tại đã vượt nó.
5. Nếu nhiều swing/break có cùng candle close time, xử lý theo event source/level identity ổn định; không phụ thuộc thứ tự list đầu vào.

## 4. BOS và protected swing

### Quy tắc tạo BOS

- Trong bullish state, bullish BOS xảy ra khi một candle close vượt continuation swing high đang được theo dõi cộng break buffer.
- Trong bearish state, bearish BOS xảy ra khi close thấp hơn continuation swing low đang được theo dõi trừ break buffer.
- Chỉ close được dùng để xác nhận; wick-only lưu observation/sweep nhưng `bos=false`.
- Một `broken_level_id` chỉ phát một BOS gốc. Scan lại cùng cutoff hoặc các candle tiếp diễn không tạo event ID mới cho cùng một break.
- BOS giữ trend đang hoạt động và có thể cập nhật continuation level. Nó không tự xác nhận CHoCH, không cộng lại displacement đã được tính ở quality.

### Quy tắc protected level

- Protected low của bullish BOS là swing low được chọn bởi source algorithm §10.2 cho chính candle phá continuation high. Lưu `protected_swing_id`, level, `source_bos_id` và thời điểm.
- Protected high của bearish BOS là swing high được chọn bởi source algorithm §10.2 cho chính candle phá continuation low.
- Chỉ cập nhật protected level sau khi BOS liên quan được xác nhận. Swing mới nhất không tự động trở thành protected; nếu latest swing không dẫn đến BOS thì giữ protected level cũ.
- Event BOS hết hạn chỉ ngăn dùng nó làm trigger mới; không xóa protected state hoặc lịch sử event.
- Nếu chưa xác định được swing nguồn của BOS, ghi cấu trúc/quality là incomplete và không tạo protected level giả.

## 5. CHoCH lifecycle

### Candidate

- Bullish → bearish: candle close phá `protected_low - break_buffer` tạo `bearish_choch_candidate`.
- Bearish → bullish: candle close phá `protected_high + break_buffer` tạo `bullish_choch_candidate`.
- Candidate lưu `event_id`, `broken_level_id` (protected swing), `direction`, `occurred_at`, `confirmed_at=null`, `expires_at`, `invalidated_at=null`, reason và snapshot identity.
- Candidate không được gọi là confirmed CHoCH, không tự đổi trend và không cấp readiness/entry như một BOS mới.

### Confirmed

- Candidate bearish chỉ confirmed sau khi có follow-through bearish: hình thành lower high (LH) sau break và một bearish BOS phá mức cấu trúc mới theo hướng giảm. Candidate bullish đối xứng: higher low (HL) sau break và bullish BOS mới.
- Không dùng số leg của trend cũ để xác nhận. Leg count chỉ là metadata về lịch sử, không thay thế bằng chứng sau break.
- `confirmed_at` là close time của candle hoàn tất điều kiện follow-through; không dùng pivot time của LH/HL để backdate.
- Sau confirmed CHoCH, state đổi sang trend mới, protected level được dựng lại từ event BOS mới; protected state cũ vẫn còn trong history.

### Reclaim, invalidation và expiry

- Candidate bearish bị reclaim khi close `>= protected_low + buffer` trước khi follow-through; candidate chuyển `invalidated`, giữ reason `reclaim_before_confirmation`, trend cũ vẫn active. Candidate bullish đối xứng khi close `<= protected_high - buffer`.
- Candidate hết hạn tại `expires_at` nếu không có follow-through; không xóa BOS/protected history và không tái dùng làm trigger mới.
- Close phá vùng nhiều lần sau khi candidate đã invalidated không hồi sinh candidate cũ; phải có event ID/break hợp lệ mới.
- Giá chạm hoặc wick xuyên protected level rồi đóng lại không phải CHoCH; chỉ ghi penetration/sweep observation.

## 6. Bảng đối xứng BUY/SELL

| Thành phần | BUY / bullish | SELL / bearish |
|---|---|---|
| Continuation structure | HH/HL | LH/LL |
| Continuation BOS | Close > tracked high + buffer | Close < tracked low − buffer |
| Protected level | Protected low từ swing dẫn đến bullish BOS | Protected high từ swing dẫn đến bearish BOS |
| CHoCH candidate | Close < protected low − buffer | Close > protected high + buffer |
| Candidate direction | Bearish | Bullish |
| Reclaim trước confirm | Close trở lại trên protected low | Close trở lại dưới protected high |
| Follow-through confirm | LH sau break + bearish BOS mới | HL sau break + bullish BOS mới |
| Wick-only | Không BOS/CHoCH; sweep observation | Không BOS/CHoCH; sweep observation |
| Dữ liệu không đủ | Unknown/blocked evidence, không tự bullish | Unknown/blocked evidence, không tự bearish |

## 7. Nhiều break trên cùng candle

1. Đánh giá tất cả close-vs-level từ cùng snapshot state trước khi cập nhật state; không để việc cập nhật level đầu tiên làm mất break thứ hai.
2. Nếu một close đồng thời vượt continuation level của trend hiện tại và protected level ngược chiều, ghi cả hai break observations với cùng `occurred_at`, nhưng chỉ một state transition được phép: BOS của trend hiện tại được ghi trước; break protected mở candidate, chưa confirmed trong cùng candle.
3. Protected level chỉ cập nhật từ BOS có source swing hợp lệ; break đối nghịch không được ghi đè protected level hoặc tự biến thành reversal confirmed.
4. Nếu một candle không thỏa BOS continuation nhưng thỏa protected break, chỉ tạo CHoCH candidate. Tie-break phải dựa trên direction/state/level ID cố định, không dựa thứ tự list.
5. Nếu timestamp, level hoặc buffer không đủ để phân biệt, trả conflict/unknown với reason; không đoán hướng.

## 8. Event contract và ví dụ

Mỗi structure event phải có tối thiểu:

`event_id`, `event_type` (BOS/CHOCH_CANDIDATE/CHOCH_CONFIRMED), `direction`, `broken_level_id`, `source_swing_id` hoặc `protected_swing_id`, `occurred_at`, `confirmed_at`, `expires_at`, `invalidated_at`, `snapshot_id`, `reason_codes`.

Ví dụ BUY:

- `L1=100` là confirmed low làm nguồn cho `BOS-1` phá `H1=110` tại close 112 → state bullish, protected low = L1.
- `L2=94` xuất hiện sau đó nhưng không dẫn đến BOS. Close 95 phá L1 nhưng không phá L2 → tạo bearish candidate theo protected L1; không dùng L2 làm protected.
- Nếu close quay lại trên 100 trước follow-through → candidate invalidated/reclaim, bullish state giữ nguyên.
- Nếu sau break có LH rồi bearish BOS mới → CHoCH confirmed tại close của BOS mới; protected high mới lấy từ swing nguồn của BOS mới.

Ví dụ SELL là phép mirror: `H1` là protected high của bearish BOS; close vượt H1 tạo bullish candidate; HL + bullish BOS mới mới được confirmed; close quay lại dưới H1 là reclaim.

## 9. Tương tác downstream

- B/Q/L/C chỉ nhận structure event hợp lệ và còn hiệu lực; candidate có thể là evidence riêng nhưng không được đọc như confirmed reversal.
- Trend alignment thuộc lớp Technical/Trend; SMC không cộng lại cùng một alignment chỉ vì event có hướng giống nhau.
- Consumer phải phân biệt `unknown`, `mixed`, `candidate`, `confirmed`, `invalidated`, `expired`; không biến candidate/unknown thành no-zone hoặc READY.
- Chi tiết tham số pivot width, equal tolerance, break/reclaim buffer và event lifetime được khóa ở bảng tham số task 8. Nếu thiếu tham số hoặc source swing, trả data-quality reason thay vì fallback theo latest swing.

Tài liệu này là đầu vào để Tech Lead review task 16. Các thay đổi semantics sau review phải cập nhật tài liệu và mở lại review chịu ảnh hưởng.

## 10. R16-01 — thuật toán causal cho continuation, protected swing và đảo chiều

Phần này khóa các chi tiết còn thiếu của contract ở các mục trên.

### 10.1 Swing source và fallback

- Pivot chỉ được dùng khi `confirmed_at <= as_of`; `pivot_width=5` là external canonical. Fallback width `2` chỉ là provisional bootstrap khi width 5 chưa có ít nhất hai confirmed high và hai confirmed low, hoặc chưa có cặp quan hệ directional rõ.
- Fallback phải mang `pivot_width=2`, `provisional=true`, `provenance=external_fallback`. Nó chỉ cho `unknown/watch` và observation; không được phát confirmed BOS, CHoCH hoặc protected swing. Khi prefix sau này đủ width 5, evaluator tính lại từ cùng prefix/as_of; event canonical width 5 có ID riêng ổn định và không bị các candle tương lai viết ngược.
- Batch và replay prefix tại cùng cutoff phải chọn cùng swing, cùng candidate ID và cùng state; không dùng pivot chưa đủ right bars và không backdate event về pivot time.

### 10.2 Cursor, bootstrap và chọn continuation/protected swing

Structure evaluator giữ cursor tường minh: `tracked_continuation_id/level`, `protected_swing_id/level`, `source_bos_id`, `source_history_anchor_at`, `bootstrap_ready_at`, `anchor_start_at`, cùng `candidate_id` khi có reversal candidate.

- Bootstrap directional pair chọn `tracked_continuation_id` là swing high/low cuối cùng của cặp HH/HL hoặc LH/LL đã confirmed. `bootstrap_ready_at = max(confirmed_at(H1), confirmed_at(L1))` là thời điểm đủ hai high + hai low và quan hệ directional; nó chỉ mở gate để đánh giá BOS đầu tiên, không phải điểm bắt đầu của source interval. `source_history_anchor_at` là pivot của swing đầu tiên trong bootstrap history; `anchor_start_at` dùng giá trị này ở BOS đầu tiên và dùng `break_candle_close` sau mỗi BOS. Vì vậy source pullback có pivot trước `bootstrap_ready_at` nhưng confirmed không muộn hơn break vẫn hợp lệ, và BOS đầu tiên không cần `previous_bos_close`.
- Với bullish BOS phá `tracked_high`, source interval là các confirmed low có `pivot_time > anchor_start_at` và `pivot_time < break_candle_close`, đồng thời `confirmed_at <= break_candle_close`; interval **không kết thúc ở `tracked_high.pivot_time`**, để giữ pullback low sau tracked high nhưng trước break. Chỉ đánh giá break khi `break_candle_close >= bootstrap_ready_at` (BOS không được backdate về pivot/ready time). Chọn low có `pivot_time` muộn nhất; nếu cùng thời điểm thì low thấp hơn, rồi `stable_swing_id`. Sau BOS, `anchor_start_at=break_candle_close` và continuation high tiếp theo được theo dõi từ các confirmed swing sau anchor.
- Bearish là mirror: phá `tracked_low` thì source interval là confirmed high với `pivot_time > anchor_start_at`, `pivot_time < break_candle_close`, `confirmed_at <= break_candle_close`; dùng cùng gate `break_candle_close >= bootstrap_ready_at`, chọn high muộn nhất, tie high cao hơn rồi stable ID. Không dùng latest swing xuất hiện sau break nếu `confirmed_at` vượt break.
- Nếu không có source confirmed, BOS có thể giữ lịch sử nhưng `protected_swing_id=null`, downstream structure evidence incomplete và không được tự lấy latest swing.

### 10.3 Candidate-local state machine

Bullish state khi close phá `protected_low - buffer` tạo `bearish_choch_candidate`, nhưng trend vẫn bullish và protected low cũ vẫn giữ nguyên. Candidate có các trường `broken_protected_swing_id`, `break_at`, `candidate_lh_id`, `candidate_continuation_low_id`, `reversal_bos_id`, `expires_at`.

1. Sau `break_at`, lấy confirmed high đầu tiên thỏa `high <= prebreak_tracked_high - equal_tolerance` làm `candidate_lh_id`.
2. Chỉ sau LH đó, lấy confirmed low đầu tiên sau LH làm `candidate_continuation_low_id`.
3. Chỉ khi close phá `candidate_continuation_low - buffer` mới ghi reversal BOS và `choch_confirmed_at` bằng close time của candle đó. Khi ấy state chuyển bearish và protected high mới lấy theo 10.2 từ source của reversal BOS.
4. Close reclaim `>= broken_protected_low + buffer` trước bước 3 hủy candidate; không hồi sinh bằng scan sau. Hết `structure-event lifetime` mà chưa bước 3 thì `expired`, trend cũ và protected history giữ nguyên.

Bearish mirror: break `protected_high + buffer` → candidate HL → candidate continuation high → bullish BOS phá `candidate_continuation_high + buffer` → confirmed bullish. Không xác nhận reversal trên cùng candle phá protected level.

### 10.4 Timeline BUY/SELL và expected boundary

Các mốc `t0…t9` dưới đây là close time UTC của H4 candle; `pivot_time` là open time của candle pivot và `confirmed_at` chỉ xuất hiện sau đủ right bars. `bootstrap_ready_at` không thay thế source-history anchor. `s0…s4` là timeline SELL tương tự.

| Side | Timeline causal | Expected state/IDs |
|---|---|---|
| BUY bootstrap/first BOS | `H0` pivot 2026-01-01 00:00/confirmed 2026-01-02 00:00; `L0` pivot 2026-01-02 00:00/confirmed 2026-01-03 00:00; `H1=110` pivot 2026-01-03 00:00/confirmed 2026-01-04 00:00; `L1=100` pivot 2026-01-04 00:00/confirmed 2026-01-05 00:00; `bootstrap_ready_at=2026-01-05 00:00`; close 2026-01-05 12:00 phá `H1+buffer` | `source_history_anchor_at=H0.pivot_time`; `BOS-B1.source=L1`, vì `L1.pivot_time < break_close` và `L1.confirmed_at <= break_close`; BOS chỉ xảy ra tại close 12:00, không backdate về ready; `tracked_high=H1`, protected=`L1` |
| BUY tiếp diễn | BOS cũ tại `t0=2026-01-05T12:00Z`; `H2=116` pivot `t1=2026-01-06T00:00Z`; `L2=103` pivot `t2=2026-01-07T00:00Z`, confirmed `t3=2026-01-08T00:00Z`; close phá H2 `t4=2026-01-08T12:00Z` | source interval `t0 < pivot_time(L2) < t4`; `BOS-B2.source=L2`, không bị mất vì rule không cắt tại H2 |
| BUY → bearish candidate | `L1=100` source `BOS-B1`; `H2=116` tracked; close `99.0` tại `2026-01-09T00:00Z` phá `100-buffer` | `C-B1`, broken=`L1`, protected vẫn `L1`; candidate-local IDs chưa có; latest swing không tự thay protected |
| BUY reversal | `H3=105` pivot `2026-01-10T00:00Z`, confirmed `2026-01-11T00:00Z` → `LH-B1`; `L3=97` pivot `2026-01-12T00:00Z`, confirmed `2026-01-13T00:00Z`; close `2026-01-13T12:00Z` phá `L3-buffer` | `BOS-R1` rồi `CHOCH-C1.confirmed`; state bearish; protected high là source của `BOS-R1` |
| BUY reclaim/timeout | close `>=100+buffer` tại `2026-01-10T12:00Z` reclaim, hoặc không có LH+low trước expiry | candidate `invalidated`/`expired`; state bullish; protected=`L1` |
| SELL bootstrap/first BOS | `L0` pivot/confirmed theo bootstrap history; `L1=90` tracked; `H2=103` pivot `s1=2026-01-04T00:00Z`, confirmed `s2=2026-01-05T00:00Z`; `bootstrap_ready_at=s2`; close phá L1 `s3=2026-01-05T12:00Z` | `source_history_anchor_at` là pivot đầu tiên của bootstrap history; `BOS-S1.source=H2` vì H2 là high muộn nhất trong source interval và đã confirmed trước break; protected=`H2` |
| SELL tiếp diễn | BOS-S1 tại `s3=2026-01-05T12:00Z`; `L2=84` pivot `s4=2026-01-06T00:00Z`; `H3=99` pivot `s5=2026-01-07T00:00Z`, confirmed `s6=2026-01-08T00:00Z`; close phá L2 tại `s7=2026-01-08T12:00Z` | source interval `s3 < pivot_time(H3) < s7`, `confirmed_at(H3) <= s7`; `BOS-S2.source=H3`, protected high mới=`H3` |
| SELL → bullish candidate/reversal | close `104.0` tại `2026-01-09T00:00Z` phá protected high; `L3=95` pivot `2026-01-10T00:00Z`, confirmed `2026-01-11T00:00Z` → `HL-S1`; `H4=103` pivot `2026-01-12T00:00Z`, confirmed `2026-01-13T00:00Z`; close `104.0+buffer` tại `2026-01-13T12:00Z` | candidate rồi `BOS-R2`/`CHOCH-C2.confirmed`; state bullish; protected low là source reversal BOS |

Break bullish chỉ đạt khi `close > level + buffer`; bearish chỉ đạt khi `close < level - buffer`. Candidate bearish reclaim là `close >= protected_low + buffer`; candidate bullish reclaim là `close <= protected_high - buffer`; dấu bằng là reclaim. Wick-only không đổi state. Pivot tại snapshot chưa đủ right bars, fallback provisional, hoặc candidate có source thiếu đều không thể tạo confirmed reversal. Các ví dụ trên phải cho cùng kết quả khi chạy từng prefix hoặc batch tại cùng `as_of`.
