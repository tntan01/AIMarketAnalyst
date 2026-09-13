# Đặc tả B/Q/L/C SMC — task 11

> **Trạng thái:** DRAFT — chờ Tech Lead review tại task 16.  
> **Mục đích:** biến chất lượng SMC thành công thức định lượng, tái lập được và tách khỏi readiness/entry/risk. Các số dưới đây là baseline triển khai, không phải xác suất thắng hay kết quả tối ưu hóa.

## 1. Công thức tổng

Với mỗi `side` và mỗi setup đã được đánh giá đủ dữ liệu:

```text
S = 4*B + 7*Q + 2*L + 2*C
Q = 0.50*formation + 0.20*geometry + 0.30*integrity
quality_score = 100*S/15
quality_raw = round_half_up(S)
```

- `B`, `Q`, `L`, `C` và mọi feature con đều bị chặn trong `[0,1]` trước khi ghép.
- `S` có miền `[0,15]`. Không cap/trừ điểm lần nữa sau công thức này.
- Component contribution giữ số thực; chỉ `quality_raw` được làm tròn một lần bằng round-half-up.
- `quality_score` là chất lượng setup theo thang 100, không phải `% thắng`.
- Khoảng cách tới giá, R:R, spread, macro, account risk, M15 và AI không làm đổi `S`; chúng thuộc eligibility/readiness hoặc lớp ngoài.

## 2. Quy tắc chuẩn hóa chung

Ký hiệu:

```text
clamp01(x) = min(1, max(0, x))
linear(x, a, b) = clamp01((x-a)/(b-a))       # b > a
inverse(x, a, b) = clamp01((b-x)/(b-a))       # b > a
```

Đối với feature theo hướng:

```text
directional_close = close_location       nếu BUY
directional_close = 1 - close_location   nếu SELL
```

Các mốc dùng chung từ task 8:

- body/ATR: bắt đầu có nghĩa tại `0.30`, đạt trần tại `1.00`;
- body/range: bắt đầu có nghĩa tại `0.50`, đạt trần tại `1.00`;
- directional close-location: bắt đầu có nghĩa tại `0.70`, đạt trần tại `0.90`;
- zone width: hẹp tốt đến `0.35 ATR`, giảm tuyến tính tới 0 tại `1.00 ATR`;
- break/reaction excursion: tối thiểu `0.10 ATR`, đạt trần tại `0.50 ATR`;
- full-fill FVG: `fill_ratio=1` làm imbalance integrity bằng 0, nhưng không xóa zone identity.

Feature không có bằng chứng sau khi đã đánh giá đủ dữ liệu có giá trị `0`. Dữ liệu bắt buộc bị thiếu/hỏng không được đổi thành `0`; khi đó toàn result là `DATA_UNAVAILABLE` với `quality_raw=null`.

## 3. B — Structure và trigger

### 3.1 Feature và công thức

| Feature | Ký hiệu/công thức | Mốc nội suy hoặc mapping | Owner bằng chứng | Không cộng trùng |
|---|---|---|---|---|
| Directional state | `state_score` | `unknown=0`; `mixed=0.25`; `HH/HL` hoặc `LH/LL` đã bootstrap `=0.60`; continuation BOS xác nhận `=0.85`; CHoCH confirmed + BOS mới `=1.00`; CHoCH candidate `=0.55` | Structure evaluator trong `smc_context.py` theo `smc-structure-spec.md` | Không cộng body/displacement của candle ở B |
| Event validity | `event_score` | `1.00` nếu BOS/CHoCH đúng object, close phá buffer, có event ID; `0.50` nếu chỉ event lịch sử còn state; `0` nếu wick-only, sai chiều hoặc invalidated | Structure event owner | Không tính sweep/reclaim; đó là L |
| Active trigger freshness | `trigger_score` | `linear(1-age/lifetime, 0, 1)` trong lifetime; `0` sau expiry; event lịch sử vẫn có thể giữ state_score | Trigger/event expiry owner | Không làm thay age lifecycle của zone ở Q |

```text
B = 0.55*state_score + 0.25*event_score + 0.20*trigger_score
```

Mục tiêu của B là tách “bias cấu trúc” khỏi “trigger còn hiệu lực”:

- Một BOS cũ hết hạn có thể vẫn giữ cấu trúc HH/HL/LH/LL, nhưng `trigger_score=0`.
- CHoCH candidate không nhận điểm như CHoCH confirmed.
- Wick vượt mức, equal-level observation hoặc sweep không tự tạo B event.
- Alignment cùng Trend/market regime không thuộc B; alignment do technical/regime owner sở hữu.

### 3.2 Biên và thiếu dữ liệu

- Không đủ swing bootstrap hoặc protected swing không xác định: `state_score=0`, `event_score=0`, reason `STRUCTURE_UNAVAILABLE` nếu thiếu dữ liệu bắt buộc.
- Mâu thuẫn cấu trúc đã đánh giá đủ: `state_score=0.25` (`mixed`), không tự chọn hướng có điểm cao hơn.
- Event invalidated/reclaim trước confirmation: `event_score=0`; không hồi sinh bằng scan sau.
- Nếu D1/H4/H1 core candles thiếu/hỏng, side result là `quality_raw=null`, state `DATA_UNAVAILABLE`; không thay B bằng zero rồi vẫn chấm Q/L/C.

## 4. Q — Chất lượng formation, geometry và integrity

```text
Q = 0.50*formation + 0.20*geometry + 0.30*integrity
```

### 4.1 Formation/departure — 50% của Q

| Feature | Công thức chuẩn hóa | Owner | Điều kiện biên |
|---|---|---|---|
| Departure body/ATR | `body_atr_score = linear(body/ATR, 0.30, 1.00)` | `smc_context.py` departure evaluator | ATR formation thiếu → missing bắt buộc; range/ATR không dương → feature 0 hoặc candidate bị reject |
| Body/range | `body_range_score = linear(body/range, 0.50, 1.00)` | Shared departure evaluator | Range bằng 0 → candidate invalid, không chia 0 |
| Close location | `close_score = linear(directional_close, 0.70, 0.90)` | Shared departure evaluator | Không đúng hướng hoặc wick-only → 0 |
| Family formation | OB: departure close-location score; FVG: `linear(gap/ATR, 0.10, 0.50)`; S/D: departure-efficiency score `linear(impulse_range/avg_range, 1.50, 3.00)` | Family detector | Detector minimum `1.50` maps to 0; `2.25` maps to .50; `>=3.00` maps to 1. Base-width/compression metrics belong only to family geometry below; family gate fail → candidate không được promoted |

```text
formation = 0.35*body_atr_score
           + 0.25*body_range_score
           + 0.20*close_score
           + 0.20*family_formation_score
```

Điều kiện detector là gate trước khi chấm: một zone không đạt gap minimum, base compression, close ra ngoài base hoặc OB structure association thì không trở thành confirmed chỉ vì formation subtotal cao.

### 4.2 Geometry — 20% của Q

Geometry không thưởng giá hiện tại đang gần zone. Khoảng cách chỉ là hard eligibility và tie-break có giải thích.

| Feature | Công thức chuẩn hóa | Owner | Điều kiện biên |
|---|---|---|---|
| Width | `width_score = 1` nếu `w/ATR <= 0.35`; `inverse(w/ATR, 0.35, 1.00)` nếu nằm giữa; `0` từ `1.00` | Shared zone geometry | Width < `2*tick`, không có ATR hoặc `w<=0` → reject geometry |
| Bounds validation | Hard gate: mọi bounds phải ordered, finite, dương theo tick và đúng family; không phải feature Q | Shared zone geometry | Invalid → candidate bị loại; valid chỉ cho phép chấm các feature khác, tự nó đóng góp `0` |

```text
geometry = 0.65*width_score + 0.35*family_geometry_score
```

`family_geometry_score` không được lấy từ việc bounds hợp lệ và không tái sử dụng metric formation: OB `ob_compactness = clamp(1 - base_width/(1.00*formation_atr), 0, 1)`; FVG `remaining_ratio = clamp(remaining_width/original_width, 0, 1)`; S/D `sd_compression = clamp(1 - base_width/(avg_range*compression_limit(n)), 0, 1)`. Thiếu ATR/avg range, base bounds hoặc FVG original width → geometry unavailable và candidate bị reject, không điền 0 để cứu plan. `refined_bounds` chỉ thay entry geometry khi nằm trong original bounds. Protective/SL/invalidation geometry luôn đọc original bounds, vì vậy không thể nâng geometry bằng cách thu hẹp zone tùy ý.

### 4.3 Integrity/lifecycle — 30% của Q

| Feature | Công thức/mapping | Owner | Điều kiện biên |
|---|---|---|---|
| Lifecycle state | `1.00` fresh chưa visit hoặc completed_reacted; `0.80` completed_unreacted; `0.60` open visit; `0` invalid/expired/full-filled FVG | `smc_lifecycle.py` | Visit open không được gọi reacted |
| Penetration | `penetration_score = 1 - max_penetration_ratio` | Lifecycle owner | Ratio clamp `[0,1]`; `>=0.50` là deep mitigation, không tự invalid |
| Dwell | `dwell_score = clamp(1 - dwell_bars/5, 0, 1)` | Lifecycle owner | `0→1.00`, `1→0.80`, `5→0`, `>=6→0`; không tính số lần scan |
| Age | `age_score = max(0.25, 1 - 0.75*age/lifetime)` trong lifetime; `0` sau expiry | Lifecycle owner | Lifetime D1/H4/H1/M15 `20/30/50/80` bar; age bắt đầu tại `available_at` |

```text
integrity = 0.35*lifecycle_state_score
          + 0.25*penetration_score
          + 0.20*dwell_score
          + 0.20*age_score
```

Đối với FVG, `remaining_width/original_width` chỉ nằm trong geometry; full fill đồng thời đặt lifecycle state bằng 0 cho imbalance. OB hoặc S/D child cùng `setup_id` không bị làm mất giá trị chỉ vì FVG sibling full fill.

## 5. L — Liquidity

L chỉ nhận bằng chứng pool/sweep/reclaim có nguồn, đúng chiều, đúng thời gian và chưa bị khử trùng.

| Feature | Công thức chuẩn hóa | Owner | Loại bằng chứng bị loại |
|---|---|---|---|
| Pool quality | `pool_score = 1.00` confirmed swing/equal-level có source; `0.50` pool yếu nhưng có source; `0` pool chưa confirmed/unknown | Liquidity pool detector | Pivot chưa confirmed, pool sai chiều |
| Sweep depth | `depth_score = linear(excursion/ATR, 0.10, 0.50)` | Sweep detector | Chỉ chạm level hoặc excursion dưới minimum |
| Reclaim quality | `1.00` reclaim trong đúng 1 candle; `0` từ candle thứ 2 trở đi hoặc không reclaim | Sweep/reclaim owner | Wick chưa reclaim, close tiếp diễn xuyên level |
| Link validity | `1` nếu zone/setup link cùng side, distance `<=0.25 ATR`, time window `<=20 bar`; `0` nếu ngoài gate | `smc_sweep_linking.py` | Unrelated sweep hoặc link không có event ID |

```text
L = pool_score
  * link_validity
  * (0.50*sweep_depth_score + 0.30*reclaim_quality + 0.20*consumed_once_score)
```

`consumed_once_score=1` khi sweep được gán cho setup owner. Với mỗi sweep, tính mọi claim đủ điều kiện tại cutoff: cùng side, distance/time gate đạt, và `claim_eligible_at=max(sweep_reclaim_at, setup_available_at)`. Owner là claim có `claim_eligible_at` sớm nhất; nếu cùng thời điểm mới tie-break bằng `stable_setup_id`. Gán owner được ghi với `assignment_id`, `owner_setup_id`, `assigned_at` và không bị setup xuất hiện muộn rút lại. Child cùng owner setup tham chiếu assignment nhưng contribution L chỉ một lần; setup khác không được tái dùng. Prefix/rebuild thiếu lịch sử owner phải trả `SWEEP_OWNER_HISTORY_INCOMPLETE`, không tự trao sweep cho setup muộn. Nếu đã đánh giá đủ history nhưng không có sweep, `L=0` và không renormalize trọng số sang B/Q/C.

## 6. C — SMC context/confluence

C chỉ giữ bối cảnh SMC độc lập với structure event B, zone formation/integrity Q và liquidity L.

| Feature | Công thức/mapping | Owner | Không tính lại |
|---|---|---|---|
| Parent-child relation | `1.00` child containment cùng hướng; `0.75` overlap >= 0.50 cùng hướng; `0` không overlap hoặc sai hướng | `smc_confluence.py` | Không thưởng H1/H4 cùng HH/HL vì đó là B/Trend |
| Independent HTF reaction | `1.00` D1 visit đã exit và có reaction follow-through còn trong 20 D1 bar; `0` proximity-only, open, completed-unreacted hoặc stale | Confluence + canonical lifecycle | Exit chưa đạt reaction không cấp C; không tính khoảng cách hiện tại hoặc D1 reaction đã dùng ở B/Q/L |
| Direction agreement | `1` nếu parent/child cùng side; `0` nếu countertrend chưa CHoCH confirmed | Confluence owner | Countertrend rule là gate/readiness, không âm điểm Q |

```text
C = 0.60*parent_child_score
  + 0.25*independent_htf_reaction_score
  + 0.15*direction_agreement_score
```

Proximity D1 chỉ là metadata. D1 reaction phải tham chiếu visit/event sau formation và lifecycle canonical còn hiệu lực. Nếu cùng một BOS tạo ra B và cũng được dùng làm parent-child evidence thì event chỉ thuộc B; C không được cộng lại.

## 7. Missing-data policy và owner boundary

| Tình huống | B/Q/L/C | Result |
|---|---|---|
| Không có zone confirmed/usable sau khi dữ liệu core đã đánh giá đủ | `0/0/0/0` | `quality_raw=0`, `selected_zone=null`, reason `NO_VALID_SETUP` |
| Core D1/H4/H1 missing, malformed, thiếu cutoff/ATR source bắt buộc | Không tính component | `quality_raw=null`, state `DATA_UNAVAILABLE`, reason cụ thể |
| M15 thiếu | Không đổi B/Q/L/C | Quality giữ nguyên; readiness/entry confirmation là WAITING/`M15_DATA_UNAVAILABLE` |
| Không có sweep trong history đủ | `L=0` | Không tăng lại trọng số B/Q/C |
| Không có parent-child hoặc D1 reaction sau khi các TF đủ | Phần C tương ứng `0` | Không suy ra C từ alignment Trend |
| AI không có/uncertain | Không đổi B/Q/L/C | AI chỉ diễn giải/audit độc lập, không penalty raw |
| Khoảng cách hiện tại > hard distance, width quá lớn, sai side | Quality không dùng để bypass | Candidate bị loại ở eligibility/planner với reason hình học |
| R:R/risk/account/macro/spread gate fail | Không đổi S | Scenario/readiness blocked ở lớp ngoài |

Owner boundary:

| Bằng chứng | Owner duy nhất | Consumer được đọc |
|---|---|---|
| Swing, protected level, BOS/CHoCH, trigger expiry | Structure evaluator | B và readiness |
| Departure/base/gap và original/refined geometry | Family detector + shared geometry | Q |
| Visit, reaction, penetration, dwell, age, FVG fill | Canonical lifecycle | Q, C và readiness |
| Pool/sweep/reclaim/link/consumed | Liquidity detector/linker | L và evidence display |
| Parent-child, D1 reaction độc lập, countertrend context | Confluence owner | C và readiness |
| Trend alignment, M15, technical, AI, risk, R:R, distance | Lớp sở hữu tương ứng | Không được sửa B/Q/L/C |

## 8. Ví dụ tính tay

### No-zone

Không có confirmed/usable zone sau khi dữ liệu core đủ:

```text
B=Q=L=C=0
S=0
quality_raw=round_half_up(0)=0
quality_score=0
selected_zone=null, reason=NO_VALID_SETUP
```

### Setup chất lượng cao

Tất cả feature đạt trần và zone còn active:

```text
B=1, Q=1, L=1, C=1
S = 4*1 + 7*1 + 2*1 + 2*1 = 15
quality_raw=15
quality_score=100
```

### Setup chất lượng thấp nhưng vẫn đủ dữ liệu

```text
B=0.25, Q=0.30, L=0, C=0.25
S = 4*0.25 + 7*0.30 + 2*0 + 2*0.25
  = 1.00 + 2.10 + 0.00 + 0.50
  = 3.60
quality_raw=round_half_up(3.60)=4
quality_score=100*3.60/15=24.00
```

### Đúng điểm làm tròn

```text
B=0.50, Q=0.50, L=0.25, C=0.50
S = 2.00 + 3.50 + 0.50 + 1.00 = 7.00
quality_raw=7
```

Một case boundary khác có `S=10.50` phải cho `quality_raw=11` theo round-half-up, không dùng banker’s rounding xuống 10.

### Không có sweep

Giả sử B=`0.80`, Q=`0.70`, L=`0`, C=`0.60` sau khi đã đánh giá đủ history:

```text
S = 4*0.80 + 7*0.70 + 2*0 + 2*0.60
  = 3.20 + 4.90 + 0.00 + 1.20
  = 9.30
quality_raw=9
quality_score=62.00
```

Không chia lại cho tổng trọng số còn lại; absence of sweep là `L=0`, không phải missing data.

### Thiếu core data và thiếu M15

- Thiếu H4 history/ATR formation: `quality_raw=null`, `DATA_UNAVAILABLE`; không xuất `0` rồi gọi là no-zone.
- Thiếu M15 nhưng D1/H4/H1 đủ: B/Q/L/C và quality giữ nguyên; chỉ readiness/entry trả WAITING, không phạt M15 vào S.

### Family trùng cùng departure

OB, FVG và S/D cùng departure, cùng side, cùng lineage:

```text
setup_id = setup(source_departure_event)
quality = tính trên setup/selected child một lần
B/L/C evidence = cap một lần theo source event
Q giữ feature riêng của child được chọn
```

Không cộng B/Q/L/C ba lần chỉ vì có ba tên family; child zone vẫn giữ `zone_id`, bounds và evidence riêng để audit/selection.

## 9. R16 boundary examples và validation gate

Với H4 lifetime `L=30`, `age=3/4/8/9/30/31` cho `age_score=.925/.900/.800/.775/.250/0`. Với D1 lifetime `L=20`, các giá trị tương ứng là `.8875/.850/.700/.6625/.250/0`. Dwell `0/1/5/6` cho `1/.8/0/0`. Reclaim ở candle `1/2/3/4` cho `1/0/0/0`.

Ví dụ tính từ raw input. Trong toàn bảng, `B=.80`, `L=.20`, `C=.30` là subtotal giả định để minh họa tác động tới `S`; `integrity` cũng ghi rõ theo từng dòng và không phải kết quả runtime cố định. Với OB/FVG, `formation` là subtotal normalized giả định vì chưa dựng đầy đủ departure/gap history. Hai dòng S/D bên dưới là chuỗi BUY/SELL OHLC hợp lệ: `avg_range=1`, `formation_atr=2`, base/zone width `.66`, `n=5`, compression limit `1.32`; formation được tính từ OHLC và family feature, còn integrity `.80` là giả định.

| Family/case | Raw input → normalized feature | `bounds_valid` | `width_score` | `family_geometry_score` | `geometry` | `Q` | `S` |
|---|---|---:|---:|---:|---:|---:|---:|
| OB yếu BUY, `base_width=zone_width=1.00`, `formation_atr=1` | `ob_compactness=clamp(1-1.00/1,0,1)=0`; `formation=.60` và `integrity=.80` là subtotal giả định | 1 (gate) | 0.00 | 0.00 | `.65*0+.35*0=0` | `.50*.60+.20*0+.30*.80=.540` | `3.2+7*.540+.4+.6=7.980` |
| OB tốt SELL, `base_width=zone_width=.35`, `formation_atr=1` | `ob_compactness=1-.35/1=.65`; `formation=.80` và `integrity=.90` là subtotal giả định | 1 (gate) | 1.00 | .65 | `.65*1+.35*.65=.8775` | `.50*.80+.20*.8775+.30*.90=.84550` | `3.2+7*.84550+.4+.6=10.11850` |
| FVG partial, original width `1.00`, remaining width `.50`, zone width ratio `.70` | `remaining_ratio=.50/1=.50`; `width_score=inverse(.70,.35,1)=.4615385`; `formation=.70`, `integrity=.80` là subtotal giả định | 1 (gate) | .4615385 | .50 | `.65*.4615385+.35*.50=.4750000` | `.50*.70+.20*.475+.30*.80=.685` | `3.2+7*.685+.4+.6=8.995` |
| S/D detector minimum, BUY `O/H/L/C=100.09/101.50/100/101.29`, SELL mirror `99.91/100/98.50/98.71`, impulse range `1.50` | BUY/SELL: `body/range=.80 → body_range_score=.60`; `body/ATR=1.20/2=.60 → body_atr_score=3/7`; `directional_close=(C-L)/range=.86` BUY hoặc `(H-C)/range=.86` SELL → `close_score=.80`; `sd_departure_score=0`; `sd_compression=1-.66/1.32=.50` | 1 (gate) | 1.00 (`.66/2=.33`) | .50 | `.65*1+.35*.50=.825` | `formation=.35*(3/7)+.25*.60+.20*.80+.20*0=.460; Q=.50*.460+.20*.825+.30*.80=.635` | `3.2+7*.635+.4+.6=8.645` |
| S/D trên minimum, BUY `O/H/L/C=100.135/102.25/100/101.935`, SELL mirror `99.865/100/97.75/98.065`, impulse range `2.25` | BUY/SELL: `body/range=.80 → .60`; `body/ATR=1.80/2=.90 → body_atr_score=6/7`; directional close `.86 → .80`; `sd_departure_score=.50`; `sd_compression=.50` | 1 (gate) | 1.00 (`.66/2=.33`) | .50 | `.825` | `formation=.35*(6/7)+.25*.60+.20*.80+.20*.50=.710; Q=.50*.710+.20*.825+.30*.80=.760` | `3.2+7*.760+.4+.6=9.520` |
| OB bounds đảo/NaN | Không tính feature | 0 | — | — | reject | 0 | 0 |

`bounds_valid=1` ở các dòng hợp lệ chỉ cho phép tính; nó không tự sinh `geometry` hay Q. BUY/SELL S/D dùng phép mirror `price'=200-price`, nên cùng range/body/close-location và cùng kết quả. Khi impulse range đổi từ `1.50` sang `2.25` với ATR giữ nguyên, body/ATR score đổi từ `3/7` sang `6/7`; không giữ mọi normalized feature cố định rồi gọi là cùng raw input.

`linear(x,a,b)=clamp((x-a)/(b-a),0,1)` và `inverse(x,a,b)=clamp((b-x)/(b-a),0,1)`. `width_score` dùng `1` khi `width/ATR<=.35`, giảm tuyến tính tới `0` tại `1.00`; family feature có endpoint `0` khi metric xấu/thiếu và `1` khi compactness/compression hoặc remaining đạt trần. `formation_atr`, `avg_range`, original/remaining bounds và base bounds thiếu hoặc không finite → candidate geometry unavailable/reject, không thay bằng 0. Các family feature ở đây không tái sử dụng metric formation: OB formation đọc departure close-location, FVG đọc gap/ATR, S/D đọc departure efficiency với endpoint `[1.50,3.00]`; base width/remaining/compression chỉ được đọc tại geometry.

### Exclusive sweep ownership theo thời gian

| Mốc | Sự kiện | Expected assignment/contribution |
|---|---|---|
| `10:00` | Sweep `S1` reclaim xong | Chưa có owner nếu chưa có setup claim đủ điều kiện |
| `10:05` | Setup `Z` available và đạt link gate | `owner_setup_id=Z`, `assigned_at=10:05`, child của Z dùng cùng assignment, L tính một lần |
| `10:20` | Setup `A` (ID nhỏ hơn Z) mới xuất hiện và cũng đạt gate | A không lấy lại S1; Z vẫn owner vì `claim_eligible_at` sớm hơn |
| `10:05` đồng thời | Setup `A` và `Z` cùng đủ điều kiện | Chọn stable setup ID nhỏ hơn; tie-break không dựa list order |
| Rebuild/prefix sau `10:20` | Batch thấy cả Z và A | Kết quả vẫn owner Z; nếu prefix thiếu lịch sử assignment thì `SWEEP_OWNER_HISTORY_INCOMPLETE`, không đổi owner cho A |

Assignment ownership, pool consumption và child contribution là ba lớp khác nhau: pool có thể được quan sát nhiều lần, một owner setup nhận assignment một lần, và mọi child cùng owner chỉ nhận một contribution đã cap. Setup đến muộn không làm contribution đã gắn biến mất chỉ vì snapshot mới.

## 10. Invariants cần khóa ở test sau review

- Mọi component và feature con nằm trong `[0,1]`; `quality_raw` chỉ làm tròn một lần.
- BUY/SELL mirror cho close-location, structure direction, sweep và parent-child.
- Thay M15, R:R, distance hoặc AI verdict không đổi quality của cùng setup.
- Thêm cùng một sweep/structure event vào nhiều child cùng setup không làm B/L/C tăng nhiều lần.
- Full-filled FVG có Q integrity bằng 0 cho imbalance, nhưng không xóa original bounds/ID hoặc sibling OB/S-D.
- No-zone khác data-unavailable: lần lượt `0` và `null`.
- Reordering input candidates không đổi điểm hoặc owner evidence của cùng setup.

## 11. Tiêu chí hoàn thành task 11

- Có công thức số cho `S`, `Q`, `quality_score`, `quality_raw` và công thức cho mọi feature con.
- Có mapping/mốc nội suy, expected tại biên, owner bằng chứng và loại trừ cộng trùng cho B/Q/L/C.
- Có missing-data policy phân biệt absence sau khi đánh giá đủ với dữ liệu bắt buộc bị thiếu; M15 không làm đổi quality.
- Có ví dụ tính tay no-zone, quality thấp/cao, rounding, no-sweep, thiếu core, thiếu M15 và family trùng.
- Không thay runtime trong task này. Việc chuyển công thức thành scorer/model/tests thuộc task 80–90 sau review task 16.
