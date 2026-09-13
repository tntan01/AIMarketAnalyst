# Đặc tả vùng SMC — task 9

> **Trạng thái:** DRAFT — chờ Tech Lead review tại task 56.  
> **Phạm vi:** điều kiện candidate/confirmed cho Order Block, Fair Value Gap và Supply/Demand; bounds gốc, refinement, setup chung và thời điểm zone được phép sử dụng.

## 1. Nguyên tắc chung

Một zone có bốn mức trạng thái khác nhau:

| Trạng thái | Ý nghĩa | Có được chấm quality? | Có được dùng entry/plan? |
|---|---|---:|---:|
| `candidate` | Hình học ban đầu đã được phát hiện nhưng còn thiếu một hoặc nhiều điều kiện xác nhận | Chỉ làm raw/audit evidence | Không |
| `confirmed` | Đã đạt toàn bộ điều kiện bắt buộc của family tại các nến đã đóng | Có, theo quality contract | Chưa chắc; còn phải kiểm tra lifecycle/geometry/current distance |
| `usable` | `confirmed`, đã tới `available_at`, còn hiệu lực, đủ dữ liệu và hợp geometry | Có | Có thể được đưa vào candidate coordinator |
| `invalid`/`expired` | Đã bị phá hoặc quá lifetime | Không cộng quality hiện hành | Không; chỉ giữ lịch sử |

`confirmed` không đồng nghĩa với “đang vào lệnh”. Một zone confirmed có thể vẫn là `watch` nếu chưa được visit, quá xa giá, M15 thiếu hoặc scenario planner không tạo được kế hoạch.

Mọi family phải tuân theo các quy tắc sau:

1. Chỉ dùng nến đã đóng trước cùng `as_of`; `available_at` không được sớm hơn thời điểm đóng của nến xác nhận.
2. `formation_start`, `formation_end`, `departure_end`, `confirmed_at` và `available_at` phải giữ lại. Không backdate zone về pivot/base để làm zone có vẻ sớm hơn.
3. Hướng zone là bất biến: demand/bullish chỉ cho BUY, supply/bearish chỉ cho SELL. Không tự đổi zone hỏng thành breaker/inverse zone trong bản đầu.
4. Zone phải có `zone_id` ổn định theo symbol, timeframe, family, direction và nguồn formation/event; không dựa vào index của rolling window.
5. `original_bounds` bất biến. Mọi bounds còn lại sau fill hoặc refinement đều là trường riêng và không được thay thế bounds dùng cho invalidation/SL.
6. Thiếu dữ liệu bắt buộc là `unknown/unavailable`, không phải candidate yếu có thể được nâng điểm để bù.

## 2. Hợp đồng dữ liệu zone

Mỗi child zone cần có tối thiểu:

| Trường | Quy tắc |
|---|---|
| `zone_id` | ID ổn định của một child zone; không đổi khi thêm nến hoặc retest |
| `setup_id` | ID nhóm các child cùng nguồn departure, cùng chiều và cùng bối cảnh |
| `family` | Một trong `ob`, `fvg`, `supply_demand` |
| `direction` | `buy` hoặc `sell`; không suy ra lại từ consumer |
| `timeframe` | TF của source zone: D1/H4/H1/M15 nếu có |
| `original_bounds` | `{low, high}` sau khi candle pattern hoàn tất; low < high và nằm trên tick grid trong tolerance |
| `refined_bounds` | Optional; child bounds dùng cho entry, không dùng thay original bounds cho SL/invalidation |
| `formation_start/end` | Khoảng candle tạo base/gap |
| `departure_end` | Nến cuối của displacement rời base/gap |
| `confirmation_event_id` | Event làm zone chuyển từ candidate sang confirmed; bắt buộc trừ trường hợp FVG/S-D confirmation chính là departure event |
| `confirmed_at` | Close time của confirmation candle/event |
| `available_at` | Thời điểm sớm nhất zone được đưa vào scoring/selection; luôn `>= confirmed_at` |
| `invalidated_at` / `expired_at` | Close time làm zone mất hiệu lực, nếu có |
| `evidence` | Body/ATR, body/range, close location, gap/base width, related structure và sweep link |
| `reason_codes` | Mã đạt, chờ hoặc loại; không dùng một boolean không có nguồn |

### Bounds và refinement

- OB `original_bounds` là toàn bộ high/low của candle/base đối màu được chọn, bao gồm wick.
- FVG `original_bounds` là khoảng gap giữa candle thứ nhất và thứ ba. `remaining_bounds` dùng riêng cho phần gap chưa fill; full fill không xóa `original_bounds` hoặc `zone_id`.
- S/D `original_bounds` là toàn bộ base range của cụm nến nén, không phải riêng body của departure.
- `refined_bounds` chỉ được tạo sau `confirmed`, phải nằm trong `original_bounds` và có width tối thiểu `max(2*tick, ...)` theo bảng task 8. Nếu refined bounds không hợp lệ thì dùng original bounds cho entry, không nới original bounds.
- Protective SL và invalidation dùng original/protective bounds. Refined bounds chỉ làm giá vào lệnh chính xác hơn; không được dùng để biến một zone rộng hoặc đã phá thành zone hợp lệ.

## 3. Order Block (OB)

### Candidate

OB candidate được tạo khi tất cả điều kiện sau đúng trên candle đã đóng:

1. Có một candle/base đối màu ngay trước departure; baseline hiện tại là 1 candle.
2. Departure đi cùng hướng với OB và close vượt high/low của base theo hướng tương ứng.
3. Candle/base có thể lưu `formation_start`, `formation_end`, `departure_end`, original bounds và displacement evidence.
4. Dữ liệu ATR/tick/structure prefix cần cho kiểm tra có provenance hợp lệ.

Candidate OB chưa được dùng cho entry, chưa được gọi là setup confirmed và không nhận bonus “confirmed structure”. FVG hoặc sweep liên quan là evidence bổ sung, không phải điều kiện bắt buộc của mọi OB.

### Confirmed

OB chuyển sang confirmed khi có structure event cùng hướng liên quan đến departure:

- BUY: close phá continuation swing high với break buffer.
- SELL: close phá continuation swing low với break buffer.
- Structure event phải xảy ra trong tối đa 3 bar sau base/departure theo bảng task 8 và có `broken_level_id`/`event_id`.
- Nếu chưa có break, OB giữ `candidate` dù giá đã quay về base.
- Nếu structure break xảy ra trước khi departure hoàn tất hoặc chỉ là wick, không xác nhận OB.

`confirmed_at` và `available_at` là close time của break event, không phải thời gian candle base. Nếu break bị reclaim/invalidate trước khi snapshot được đọc thì zone không được nâng lại thành confirmed mới; giữ event history và trạng thái hiện tại.

### Ví dụ

**Đạt — BUY OB:**

- H4 candle đối màu ngày 2026-01-05 có bounds `[99.50, 101.00]`.
- Candle departure ngày 2026-01-06 bullish đóng ở `103.00`, vượt base; candidate được tạo sau close ngày 2026-01-06.
- H4 candle ngày 2026-01-07 đóng `104.00`, vượt protected swing high `103.50` cộng break buffer, tạo `BOS-H4-07`.
- OB confirmed và usable từ `available_at = close_at(2026-01-07)` nếu chưa invalidated, chưa stale và geometry đạt.

**Không đạt — BUY OB chưa break:**

- Base và departure giống ví dụ trên, nhưng ba candle tiếp theo không có close phá continuation swing high; chỉ có wick chạm/vượt.
- Kết quả: `candidate`, reason `OB_STRUCTURE_BREAK_MISSING` hoặc `OB_WICK_ONLY`; không được dùng entry dù giá quay lại vùng.

## 4. Fair Value Gap (FVG)

**Bổ sung contract ngày 2026-09-11:** nguồn FVG qua session closure được chốt tại [R56-01 session-origin contract](smc-r56-01-session-contract.md), cùng golden acceptance suite. Đây là quy ước tính toán bổ sung cho P5: phân biệt full directional coverage, partial/unknown và session-only; không thay gap bounds/quality thresholds. Contract đã chốt, implementation/gate56 vẫn chờ nghiệm thu.

### Candidate

FVG candidate dùng đúng mô hình ba candle đã đóng:

- Bullish: `first.high < third.low`.
- Bearish: `first.low > third.high`.
- Gap width đạt `max(2*tick, 0.10*ATR_formation)`.
- Middle candle cùng hướng departure; giữ body/range, close-location và displacement evidence.
- Gap không chỉ là session boundary. Nếu metadata session không đủ để phân loại, ghi `SESSION_GAP_UNKNOWN` và không promote tự động.

Candidate được ghi nhận khi candle thứ ba đóng, nhưng chưa confirmed nếu gap nhỏ, middle candle yếu, sai hướng hoặc thiếu ATR/tick reference.

### Confirmed

FVG chuyển sang confirmed tại close của candle thứ ba khi đồng thời đạt:

1. Gap minimum.
2. Middle body/range `>= 0.50`.
3. Close location BUY `>= 0.70`, SELL `<= 0.30`.
4. Middle candle và gap cùng direction.
5. Không phải session-only gap và không thiếu dữ liệu bắt buộc.

Không yêu cầu thêm BOS hoặc sweep để mọi FVG được confirmed; các event đó là evidence quality/linking. FVG chỉ usable từ `available_at = close_at(third candle)`. Full fill được đánh giá riêng trong lifecycle: `remaining_bounds` có thể thu hẹp, còn original bounds/ID giữ nguyên; full-filled FVG không còn là imbalance active.

### Ví dụ

**Đạt — bullish FVG:**

- Candle thứ nhất high `100.00`; candle giữa bullish range `2.00`, body `1.40`, close-location `0.80`; candle thứ ba low `101.00`.
- Với ATR `4.00` và tick `0.01`, gap `1.00` lớn hơn `max(0.02, 0.40)`; ba candle liên tục trong cùng session.
- FVG `[100.00, 101.00]` confirmed tại close candle thứ ba và usable từ thời điểm đó, cho BUY.

**Không đạt — gap nhỏ/middle yếu:**

- Gap chỉ `0.02` khi ATR `1.00`, đúng tick nhưng nhỏ hơn ngưỡng `0.10*ATR`; middle candle body/range `0.20`.
- Kết quả: candidate bị loại, reason `FVG_GAP_TOO_SMALL` và `FVG_MIDDLE_CANDLE_WEAK`; không tạo zone confirmed.

## 5. Supply/Demand (S/D)

### Candidate

S/D candidate được tìm từ base nén trước departure với số candle thuộc tập `{3, 5, 7, 10}`:

1. Base có đủ candle và được tính từ thống kê trước departure, không dùng nến tương lai.
2. Base range không vượt compression limit `1.20 + 0.06*(n-3)` lần average range.
3. Departure candle đóng ra ngoài base theo hướng demand/supply.
4. Lưu base bounds đầy đủ, base count, formation interval và departure evidence.

Candidate chưa confirmed nếu departure chỉ có wick, close còn trong base, average range/ATR không hợp lệ hoặc base vượt compression limit.

### Confirmed

S/D confirmed tại close của departure khi đồng thời đạt:

- Demand: departure bullish và close > base high.
- Supply: departure bearish và close < base low.
- Impulse range `>= 1.50 * avg_range` theo thống kê local trước departure.
- Body/range, close-location và ATR formation đạt ngưỡng chung ở task 8.
- Base compression đạt giới hạn tương ứng với số candle.

S/D không cần BOS riêng để confirmed nếu departure đã đạt toàn bộ điều kiện formation; BOS/sweep là evidence quality hoặc setup association. `available_at = close_at(departure)`, không phải thời điểm candle đầu tiên của base.

### Ví dụ

**Đạt — demand zone:**

- Base 3 H1 candle có bounds `[99.00, 100.00]`, range nằm dưới `1.20*avg_range`.
- Departure bullish có range `1.80*avg_range`, body/range `0.65`, close-location `0.85`, close `101.20` > base high.
- Demand `[99.00, 100.00]` confirmed và usable từ close departure nếu không bị invalidated/stale.

**Không đạt — supply có râu dài:**

- Base 5 candle đạt compression, nhưng departure có high/low mở rộng ra dưới base rồi đóng lại trong base; body/range `0.20`, close không nằm ngoài base.
- Kết quả: candidate bị loại với `SD_DEPARTURE_WICK_ONLY`/`SD_CLOSE_NOT_OUTSIDE_BASE`; không được dùng làm supply confirmed.

## 6. Setup chung và loại trùng

### Quy tắc nhóm

OB, FVG và S/D được gán cùng `setup_id` chỉ khi cùng:

- symbol và snapshot lineage;
- direction;
- anchor timeframe/bối cảnh;
- departure source/event trong cùng cửa sổ association;
- displacement lineage thực sự, không chỉ trùng mức giá hoặc overlap.

`setup_id` được tạo từ source identity ổn định, không từ thứ tự list. Một impulse có thể tạo nhiều child family nhưng chỉ một setup chung. Mỗi child vẫn giữ `zone_id`, family, original bounds và evidence riêng.

### Không gộp

- Hai zone cùng chiều chỉ overlap nhưng khác departure event → hai setup.
- OB/FVG/S-D khác chiều → không gộp.
- Một FVG hình thành nhiều bar sau departure hoặc một sweep không liên quan → evidence độc lập, không làm chung setup.
- Không union bounds của các child thành vùng lớn mới. Selection chọn child/plan cụ thể; setup chỉ là quan hệ nguồn và khử cộng điểm trùng.

### Trạng thái setup và thời điểm sử dụng

| Tình huống | `setup` | Child usable? | Quy tắc `available_at` |
|---|---|---:|---|
| Có child candidate, chưa family nào confirmed | `candidate` | Không | Chưa có `available_at` hợp lệ |
| Có ít nhất một child confirmed còn hiệu lực | `confirmed` | Có, theo từng child | `available_at` của child đó; không chờ family khác |
| Có child confirmed nhưng quá xa/stale/no-plan | `watch` | Không cho READY | Giữ zone để theo dõi, không bypass geometry/planner |
| Mọi child bị invalidated/expired/full-filled theo family | `invalid`/`expired` | Không | Giữ lịch sử và reason |

Setup không được dùng evidence tương lai để làm child cũ confirmed sớm. Nếu OB confirmed ở ngày 7 nhưng FVG chỉ hình thành ở ngày 8, snapshot ngày 7 chỉ được thấy OB; snapshot ngày 8 mới được thấy cả hai child cùng setup.

## 7. Điều kiện usable dùng chung

Một child zone được đưa vào selection/planning khi:

```text
confirmed
and available_at <= as_of
and required source history is complete
and not invalidated
and not expired/stale
and original_bounds are valid
and current distance <= hard distance
and width <= max zone width
```

Các bước lifecycle sau đó có thể chuyển zone sang visited, reacted, mitigated, partially-filled hoặc broken. Những trạng thái này không được làm thay `original_bounds`, `formation_at` hay `confirmed_at`.

Refinement không phải điều kiện để zone confirmed. Nếu refinement được tạo sau visit hoặc theo cấu trúc thấp hơn, phải lưu `refined_at`, source evidence và quan hệ `parent_zone_id`; nếu refinement hết hợp lệ thì quay về original zone chỉ trong phạm vi policy entry, không phục hồi zone đã invalidated.

## 8. Mã lý do tối thiểu

| Mã | Ý nghĩa |
|---|---|
| `ZONE_CANDIDATE` | Hình học ban đầu đã tìm thấy, còn chờ xác nhận |
| `ZONE_CONFIRMED` | Đạt điều kiện family tại candle/event đã đóng |
| `ZONE_NOT_AVAILABLE_YET` | `as_of` còn trước `available_at` |
| `OB_STRUCTURE_BREAK_MISSING` | OB chưa có break cùng hướng |
| `OB_WICK_ONLY` | Break chỉ là wick |
| `FVG_GAP_TOO_SMALL` | Gap dưới ngưỡng tick/ATR |
| `FVG_MIDDLE_CANDLE_WEAK` | Body hoặc close-location của middle candle không đạt |
| `SESSION_GAP_UNKNOWN` | Chưa đủ metadata để promote gap |
| `SD_COMPRESSION_TOO_WIDE` | Base vượt compression limit |
| `SD_DEPARTURE_WICK_ONLY` | Departure không có close/body đủ nghĩa |
| `SD_CLOSE_NOT_OUTSIDE_BASE` | Close chưa thoát base |
| `ZONE_INVALIDATED` | Close phá protective/original boundary theo policy |
| `ZONE_EXPIRED` | Vượt lifetime của timeframe/family |
| `ZONE_GEOMETRY_REJECTED` | Width/distance không thể tạo plan |

## 9. Tiêu chí hoàn thành task 9

- OB, FVG và S/D đều có điều kiện candidate, confirmed, invalid/expired và usable.
- Mỗi family có một ví dụ đạt và một ví dụ không đạt, với kết quả và reason cụ thể.
- `available_at` luôn gắn với close của nến/event xác nhận; không zone nào được dùng trước thời điểm đó.
- Original bounds, remaining bounds và refined bounds được tách; refinement không thay protective/SL/invalidation bounds.
- Setup chung chỉ nhóm cùng nguồn departure/cùng chiều; không gộp chỉ vì overlap và không cộng bằng chứng trùng nhiều lần.
- Không thay runtime trong task này. Việc chuyển đặc tả thành model/detector/tests thuộc task 41–55 sau khi task 40 được APPROVED.
