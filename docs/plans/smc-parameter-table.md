# Bảng tham số SMC — task 8

> **Trạng thái:** DRAFT — chờ Tech Lead review ở task 16.  
> **Mục đích:** chốt một bộ giá trị khởi đầu có thể triển khai và replay được. Các giá trị ghi “quy ước khởi đầu” là baseline kỹ thuật, không phải kết quả tối ưu hóa hay khuyến nghị giao dịch.

## Quy ước đọc bảng

- `ATR` luôn là ATR của cùng timeframe, period 14, lấy từ các nến đã đóng trước thời điểm hình thành sự kiện.
- `tick` là `trade_tick_size`; nếu broker không cung cấp thì dùng `point` dương kèm provenance. Không suy ra tick size chỉ từ `digits`.
- `max(a, b)` là ngưỡng bảo vệ đồng thời khỏi nhiễu làm tròn giá và khác biệt biến động giữa các symbol.
- “Code hiện có” nghĩa là giá trị đã tồn tại trong runtime hiện tại. “Quy ước khởi đầu” nghĩa là giá trị được điền để loại bỏ khoảng trống của phụ lục P, chưa được gọi là tối ưu.
- Các ngưỡng có hướng phải áp dụng đối xứng cho BUY/SELL: BUY dùng close ở phía trên và SELL dùng close ở phía dưới, trừ khi bảng ghi rõ ngược lại.

## P1 — Nến, ATR và chất lượng dữ liệu

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| ATR period | `14` | bar, mọi TF | `core/smc_context.py:_ATR_PERIOD`; `core/indicators.py:atr` | Không thay period giữa formation và replay | Giữ cùng chuẩn ATR đang dùng trong SMC/technical. |
| ATR warm-up | `14` TR trước giá trị đầu tiên; yêu cầu tối thiểu `15` candle cho filter | bar | `_ATR_FILTER_MIN_CANDLES=15` | Thiếu warm-up → `SMC_ATR_REFERENCE_UNAVAILABLE` | Không dùng ATR rỗng hoặc ATR của tương lai. |
| Interval D1/H4/H1/M15 | `1d / 4h / 1h / 15m` | thời lượng candle | `services/mt5_service.py:_PRIMARY_TIMEFRAME_INTERVALS` | `close_at = open_time + interval` | Chuẩn hóa cutoff giữa live và replay. |
| Candle cutoff | `close_at <= as_of` | UTC timestamp | `docs/plans/smc-data-spec.md` | Candle đang hình thành bị loại; `as_of` duy nhất cho snapshot | Tránh look-ahead và chênh lệch live/replay. |
| Tick-size resolution | `trade_tick_size > 0`; fallback `point > 0` | giá/symbol | `services/mt5_service.py:execution_snapshot` | Cả hai thiếu hoặc không dương → `SMC_TICK_SIZE_UNAVAILABLE` | Threshold theo tick phải có nguồn đo được. |
| Session gap | Giữ gap hợp lệ theo lịch broker; gap không xác định không tự sinh candle | candle interval | `smc-data-spec.md` | Không nối giả, không dùng gap như displacement | Phân biệt nghỉ phiên với dữ liệu thiếu. |
| Minimum technical coverage | D1 `60`, H4 `60`, H1 `30` | candle/TF | `core/scanner_features.py`; `technical_context.py` | Thiếu một TF required → không tạo core snapshot | Đủ trend, ATR và momentum hiện hành. |
| Minimum M15 coverage | `15` cho evaluator; `48` cửa sổ xác nhận | candle | `smc_m15_confirmation.py` | Thiếu M15 không downgrade quality; entry yêu cầu M15 thì `WAITING_CONFIRMATION` | M15 chỉ sở hữu visit/confirmation của entry. |

## P2 — Swing và structure

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| External pivot width | `5` | bar mỗi phía | `_SMC_LOOKBACK_EXTERNAL=5` | Chỉ swing đã xác nhận mới được dùng | Giữ cấu trúc ngoài ổn định hơn micro noise. |
| External fallback width | `2`, provisional only | bar mỗi phía | `_SMC_LOOKBACK_FALLBACK=2` | Chỉ bootstrap khi width 5 chưa có đủ cặp swing; không được phát BOS/CHoCH/protected confirmed; khi width 5 đủ thì tính lại theo cùng prefix/as_of | Có bootstrap quan sát nhưng không biến fallback causal thành tín hiệu chắc chắn. |
| Internal pivot width | `2` | bar mỗi phía | `_SMC_LOOKBACK_INTERNAL=2` | Không dùng làm protected swing của external BOS | Tách micro structure khỏi protected structure. |
| Equal-level tolerance | `max(2*tick, 0.10*ATR)` | giá | Quy ước khởi đầu | Giá trị không dương hoặc thiếu ATR/tick → level relation `unknown` | Đủ rộng cho rounding nhưng tránh gộp hai swing khác biệt. |
| Break/reclaim buffer | `max(2*tick, 0.10*ATR)` | giá | Quy ước khởi đầu; cùng loại tolerance với level comparison | Break chỉ hợp lệ khi close vượt level + buffer; reclaim phải đóng lại qua buffer | Wick-only không được gọi là BOS/CHoCH. |
| Bootstrap structure | Tối thiểu `2` confirmed highs + `2` confirmed lows và một quan hệ HH/HL hoặc LH/LL rõ | swing | `smc-structure-spec.md` | Không đủ hoặc conflict → `unknown`, không default trend | Tránh suy luận trend từ dữ liệu chưa đủ. |
| Structure-event lifetime | D1 `20`, H4 `40`, H1 `80`, M15 `48` | bar của TF | Quy ước khởi đầu, phù hợp cửa sổ hiện có | Hết hạn nếu chưa follow-through; event vẫn giữ trong audit history | Giới hạn tín hiệu cũ mà không xóa provenance. |
| Protected swing update | Chỉ cập nhật từ swing confirmed là nguồn của BOS gần nhất | event relation | `smc-structure-spec.md`; fixture task 5 | Latest swing không tự thay protected swing | Sửa lỗi dùng nhầm last swing khi tìm CHoCH. |

## P3 — Departure và impulse

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Minimum body/ATR | `0.30` | body / ATR | `smc_m15_confirmation.py:_M15_DISPLACEMENT_ATR_RATIO=0.3`; quy ước dùng chung ban đầu | `body/ATR < 0.30` không phải displacement | Có baseline hiện hữu cho M15 và không thổi phồng threshold. |
| Minimum body/range | `0.50` | tỷ lệ `[0,1]` | Quy ước khởi đầu | Range bằng 0 → reject departure | Nến phải có thân chiếm phần đáng kể của biên độ. |
| Close-location | BUY `>=0.70`, SELL `<=0.30` | vị trí close trong range | Quy ước khởi đầu | Range bằng 0 → không đạt | Xác nhận close gần phía phá vỡ, không chỉ có wick. |
| Formation lookback | `5` | bar trước event | Quy ước khởi đầu; external width hiện là 5 | Không đọc quá `as_of`; thiếu prefix → event unavailable | Có đủ bối cảnh mà vẫn giữ causal boundary. |
| OB wait-for-break | `3` | bar sau base | Quy ước khởi đầu | Quá 3 bar chưa break → không gắn OB với event đó | Tránh liên kết zone cũ với departure muộn. |

## P4 — Order block

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Opposite-color base candles | `1` | candle/OB | `detect_order_blocks` hiện lấy candle đối màu ngay trước impulse | Không có candle đối màu → không tạo OB | Phản ánh detector đang chạy và dễ audit. |
| Base width limit | `1.00*ATR` | giá | Quy ước khởi đầu, cùng hard width của zone | Width `>1 ATR` → zone candidate bị loại khỏi plan | Zone quá rộng làm entry/SL không xác định. |
| Structure-event association | Cùng hướng; departure trong `<=3` bar; `event_id` bắt buộc | bar/event | Quy ước khởi đầu + OB wait-for-break | Không có event tương ứng → OB vẫn raw candidate nhưng không được gọi confirmed | Tách phát hiện hình học khỏi xác nhận cấu trúc. |

## P5 — Fair Value Gap

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Minimum gap | `max(2*tick, 0.10*ATR)` | giá | Quy ước khởi đầu; detector hiện chỉ kiểm tra gap dương | Gap nhỏ hơn ngưỡng → không tạo FVG | Không coi sai số giá là mất cân bằng. |
| Middle-candle body/range | `>=0.50` | tỷ lệ | Quy ước khởi đầu | Range bằng 0 → reject | FVG cần departure có thân, không chỉ khoảng trống tình cờ. |
| Middle-candle close location | BUY `>=0.70`, SELL `<=0.30` | tỷ lệ | Quy ước khởi đầu | Không đạt → raw gap không promoted | Đồng bộ contract displacement. |
| Session-gap policy | Reject gap chỉ do session boundary; giữ gap có candle displacement hợp lệ | event type | Quy ước từ `smc-data-spec.md`; [contract R56-01 chốt 2026-09-11](smc-r56-01-session-contract.md) bổ sung định nghĩa D/G | Known closure: D bao phủ toàn gap → đạt nguồn; giao một phần → unknown; không giao dương → session_only. Metadata không rõ → unknown | Không biến nghỉ phiên thành FVG; không dùng reopen equality/strict range làm veto. |
| Full-fill tolerance | `max(1*tick, 0.05*gap_width)` | giá | Quy ước khởi đầu | Fill chạm trong tolerance được coi là full fill; thiếu tick → dùng ATR nhánh dự phòng và ghi reason | Tránh flip state do rounding. |

## P6 — Supply/Demand

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Base candle-count candidates | `{3, 5, 7, 10}` | candle/base | `detect_supply_demand_zones` hiện có | Chọn base hẹp nhất trên cùng impulse; thiếu base → bỏ candidate | Giữ behavior hiện tại nhưng ghi rõ tập tham số. |
| Compression limit | `1.20 + 0.06*(n-3)` lần avg range | tỷ lệ, `n` là base count | Code hiện tại `max_base_range_mult` | Base range vượt limit → reject | Ngưỡng tăng nhẹ theo độ dài base. |
| Departure efficiency | impulse range `>=1.50*avg_range` | range/avg range | Code hiện tại `impulse_threshold` | `avg_range <=0` → không tạo zone | Đảm bảo departure có lực tương đối với nền. |
| Candidate expiry | Invalidated ngay khi close vượt zone; nếu chưa invalidated thì stale theo TF | event/lifecycle | `core/smc_lifecycle.py:_STALE_AFTER_BARS` | D1 `20`, H4 `30`, H1 `50`, M15 `80` bar | Có điều kiện kết thúc rõ ràng cho candidate. |

## P7 — Zone lifecycle

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Visit entry/exit tolerance | `max(1*tick, 0.05*ATR)` | giá | Quy ước khởi đầu | Overlap trong tolerance gộp cùng một visit; thiếu cả ATR/tick → lifecycle unknown | Không tạo nhiều visit vì một sai số nhỏ. |
| Reaction follow-through | Close ra khỏi zone ít nhất `0.25*ATR` hoặc tạo micro BOS trong `3` bar | giá/bar | Quy ước khởi đầu; micro window hiện là 3 | Không có follow-through → visit, không phải reaction | Phân biệt chạm vùng với phản ứng có hiệu lực. |
| Dwell score | `inverse(dwell_bars, 0, 5)` | hệ số `[0,1]` | `smc-bqlc-spec.md` | `0→1.00`, `1→0.80`, `5→0.00`, `>=6→0.00`; không dùng số lần polling | Một công thức duy nhất giữa bảng tham số, lifecycle và B/Q/L/C. |
| Penetration threshold | `0.50` | tỷ lệ độ sâu zone | Quy ước khởi đầu | `>=0.50` đánh dấu deep mitigation; close xuyên boundary là broken | Tách retest nông khỏi mitigation sâu. |
| Age-decay schedule | `max(0.25, 1 - 0.75*age_bars/lifetime)` trong `0..lifetime`; `0` sau lifetime | hệ số | `smc-bqlc-spec.md` | Với H4/L=30: age `3/4/8/9/30/31` → `.925/.900/.800/.775/.250/0`; D1/L=20: `.8875/.850/.700/.6625/.250/0` | Freshness bands chỉ là nhãn hiển thị; không có step schedule khác công thức scorer. |
| Zone lifetime — D1/H4/H1/M15 | `20 / 30 / 50 / 80` | bar/TF | `smc_lifecycle.py:_STALE_AFTER_BARS` | `age_bars > threshold` → stale; vẫn giữ record | Dùng đúng lifecycle stale policy hiện hành. |
| D1 reaction lifetime | `20` | D1 bar sau formation | Quy ước khởi đầu, đồng bộ D1 stale | Proximity không có visit/reaction không được tính bonus | Ngăn D1 “gần vùng” bị gọi là reaction. |

## P8 — Liquidity và sweep linking

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Liquidity-pool tolerance | `0.25*ATR` | giá | `SWEEP_ZONE_TOLERANCE_ATR=0.25` | Thiếu ATR → không link sweep-zone | Giá trị đã có trong sweep linker. |
| Sweep excursion | `max(2*tick, 0.10*ATR)` | giá | Quy ước khởi đầu | Wick phải vượt pool bằng excursion rồi close reclaim | Tách sweep khỏi chạm level thông thường. |
| Reclaim rule | Close trở lại phía trong pool trong `1` candle | candle/close | `smc-bqlc-spec.md` | `1` candle đạt `1.00`; `2/3/4` không đạt window hiện tại và cho `0` | Một boundary duy nhất, không có nhánh 2–3 candle. |
| Consumed policy | Một sweep có một `owner_setup_id` độc quyền; child cùng owner tham chiếu assignment nhưng chỉ đóng góp L một lần | pool/setup | `smc-bqlc-spec.md` | `claim_eligible_at=max(sweep_reclaim_at, setup_available_at)`; owner sớm nhất, cùng thời điểm mới tie-break stable setup ID; setup đến muộn không rút owner; thiếu owner history → `SWEEP_OWNER_HISTORY_INCOMPLETE` | Đảm bảo exclusive ownership causal giữa setup, không phụ thuộc rebuild/list order. |
| Zone-link distance | `<=0.25*ATR` | giá/ATR | `SWEEP_ZONE_TOLERANCE_ATR` | Ngoài tolerance → không link | Association phải price-aware. |
| Zone-link time window | Formation/departure window của zone; tối đa `20` bar | bar cùng TF | Quy ước khởi đầu + linker formation window | Ngoài window → giữ sweep độc lập | Không kéo sweep xa vào zone mới. |

## P9 — Multi-timeframe D1/H4/H1

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Parent-child containment | Child phải nằm trong parent sau mở rộng `max(1*tick, 0.05*ATR_parent)` | hình học | Quy ước khởi đầu | Không containment/overlap đủ → không coi là refinement | Bảo vệ quan hệ vùng giữa TF. |
| Minimum overlap alternative | `>=0.50` diện tích/chiều dài vùng giao nhau | tỷ lệ | Quy ước khởi đầu | Chỉ dùng khi containment không thể do rounding; hướng vẫn phải hợp lệ | Cho phép sai số biên nhỏ mà không nới quá rộng. |
| Valid direction | D1 bias → H4/H1 cùng hướng; countertrend chỉ `watch` | side | `smc-structure-spec.md` và direction contract | Countertrend không được READY nếu chưa có CHoCH confirmed | Không trộn bias trái chiều thành một setup. |
| D1 reaction lifetime | `20` | D1 bar | P7 | Sau 20 bar chỉ còn historical metadata | Cùng boundary với D1 lifecycle. |
| Countertrend rule | Cần CHoCH confirmed + BOS follow-through trước khi cho phép plan | state transition | `smc-structure-spec.md` | CHoCH candidate/reclaim chưa đủ | Không mở rộng quyền vào lệnh từ tín hiệu sớm. |

## P10 — M15 entry confirmation

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Minimum data | `15` | M15 candle | `_M15_MIN_CANDLES=15` | Ít hơn → `M15_DATA_UNAVAILABLE`/not confirmed | Đủ ATR14 và candle kiểm tra. |
| Trigger lookback after visit | `48` | M15 bar, tối đa 12 giờ | `_M15_LOOKBACK_CANDLES=48` | Chỉ trigger sau visit hiện tại; rejection cũ ngoài visit không được tái dùng | Sửa stale-rejection false confirmation (fixture task 4). |
| Micro swing width | `3` | bar mỗi phía | `_M15_SWING_LOOKBACK=3` | Chưa đủ structure → không CHoCH | Giữ micro structure nhất quán với evaluator. |
| Follow-through limit | `3` | M15 bar | `core/smc_m15_confirmation.py:_M15_FOLLOW_THROUGH_BARS=3` | Quá cửa sổ → trigger hết hạn | Không giữ confirmation quá lâu sau visit. |
| Displacement threshold | `0.30*ATR14` | body/ATR | `_M15_DISPLACEMENT_ATR_RATIO=0.3` | Body dưới ngưỡng → no confirmation | Có lực phá vỡ tối thiểu. |
| Rejection wick/body/range | BUY `lower_wick=min(open,close)-low`, close `> open`; SELL `upper_wick=high-max(open,close)`, close `< open`; directional wick `>= max(0.80*body, 0.25*range)` | tỷ lệ/giá | `core/smc_m15_confirmation.py` | `range<=0` reject; equal threshold đạt; sai màu hoặc ngoài visit follow-through window reject | Ghi đúng directional wick của runtime hiện tại; không đảo upper/lower theo side. |
| Confirmation expiry | `12` | M15 bar sau `trigger_anchor_at` | Quy ước khởi đầu | Hết hạn → `M15_NO_CONFIRMATION`, `penalty=0`, quality/B/Q/L/C không đổi | Một visit không xác nhận vô thời hạn nhưng M15 không phạt raw score. |
| Maximum run from entry | `0.50*ATR` | giá | `core/smc_m15_confirmation.py:_M15_MAX_RUN_ATR=0.5` | **Áp ở CẢ HAI nhánh** (chốt Tech Lead sau Lô C): (a) **trước trigger** — nhánh chưa xác nhận, tại nến đánh giá, `status=waiting` + `M15_ENTRY_TOO_FAR`; (b) **hậu confirmation/invalidation** — trong `_invalidation()`, tại `last_allowed`, `status=invalidated` + `M15_ENTRY_TOO_FAR`. Cả hai đều không downgrade quality: B/Q/L/C và quality giữ nguyên, chỉ readiness/invalidation đổi | Tránh đuổi giá sau khi setup đã rời zone, kể cả khi đã có xác nhận. |

## P11 — Geometry, execution và output

| Tham số | Giá trị khởi đầu | Đơn vị/phạm vi | Căn cứ | Điều kiện biên | Lý do |
|---|---:|---|---|---|---|
| Minimum zone width | `2*tick` | giá | Quy ước khởi đầu | Width nhỏ hơn → invalid geometry | Zone phải biểu diễn được trên tick grid. |
| Maximum zone width | `1.00*ATR` | giá/ATR | `_MAX_ZONE_WIDTH_ATR=1.0` | Rộng hơn → không tạo protective plan | Giữ risk/entry geometry kiểm soát được. |
| Hard distance from price | `3.00*execution_atr` | giá/ATR | `_ZONE_HARD_DISTANCE_ATR=3.0`; scanner producer cùng giá trị | Xa hơn → không plan | Khoảng cách phải dùng một ATR execution chung giữa Analyze/Scanner. |
| Formation ATR | ATR của source zone timeframe | cùng TF | Formation snapshot/provenance | Thiếu hoặc không dương → width/quality geometry unavailable | Giữ width và family quality gắn với bối cảnh lúc hình thành zone. |
| Execution ATR | `first_finite_positive(technical.atr_h4, technical.atr_d1)` từ frozen snapshot | giá/ATR, H4→D1 fallback | Shared planner proposal R16-05 | Cả hai thiếu/hỏng → `EXECUTION_ATR_UNAVAILABLE`; ghi `atr_source`/fallback reason | Tất cả route dùng cùng hard-distance reference, không dùng current ATR riêng của zone TF. |

## R16 — Boundary contract dùng chung

Các bảng B/Q/L/C, lifecycle và readiness phải đọc đúng các hàm dưới đây; không diễn giải lại theo freshness band hay penalty legacy:

```text
dwell_score(d) = clamp(1 - d/5, 0, 1)
age_score(a, L) = 0                         nếu a > L
                 max(0.25, 1 - 0.75*a/L)    nếu 0 <= a <= L
reclaim_quality(r) = 1.00 nếu r = 1; 0.00 nếu r >= 2 hoặc không có reclaim
```

`dwell_bars` là số candle M15/H1/H4/D1 đã đóng overlap liên tiếp trong một visit, không phải số lần scanner chạy. `age_bars` bắt đầu tại `available_at`; `age=L` còn `.25`, còn `age=L+1` là `0`/expired. Reclaim window tính từ candle sweep đầu tiên và là inclusive đúng một candle.

Consumed evidence có owner độc quyền theo thời gian: với mỗi `sweep_id`, claim hợp lệ là cùng side và đạt distance/time gate; `claim_eligible_at=max(sweep_reclaim_at, setup_available_at)`. Claim sớm nhất nhận `owner_setup_id`; chỉ khi cùng timestamp mới tie-break `stable_setup_id`. Child cùng owner setup cùng tham chiếu `assignment_id` nhưng L đóng góp một lần; setup khác không được mượn lại. Owner đã gắn không bị setup xuất hiện muộn rút lại. Prefix/rebuild thiếu lịch sử owner trả `SWEEP_OWNER_HISTORY_INCOMPLETE`, không gán lại theo ID nhỏ nhất.

Ví dụ planner parity: một H1 zone có `formation_atr_H1=.80`, width `.60` nên qua hard width `<=.80`; tại cùng frozen snapshot `technical.atr_h4=2.00`, `technical.atr_d1=2.40`, execution ATR là `2.00`. Nếu entry tới zone cách `4.00`, distance pass vì `4.00 <= 3*2.00 = 6.00`; cả Analyze và Scanner phải cho cùng kết quả. Nếu H4 ATR thiếu/không finite nhưng D1 là `2.40`, distance ceiling là `7.20` và phải ghi fallback D1. Không được thay bằng current H1 ATR hoặc ATR tương lai của source zone.

Các biên M15 rejection phải dùng `range=high-low`, `body=abs(close-open)`, và chỉ đạt nếu directional wick đạt ngưỡng **và** close đúng màu **và** event nằm trong visit/follow-through window. `equal` đạt, `under` không đạt; doji/range zero không tạo rejection. Những con số này là contract tài liệu; việc đổi detector là quyết định riêng chờ Tech Lead.

Ví dụ độc lập từ OHLC (không chép nhãn runtime):

| Side/case | O/C/H/L | range | body | directional wick | threshold | Expected |
|---|---|---:|---:|---:|---:|---|
| BUY đạt, bằng ngưỡng | 100/100.4/100.68/99.68 | 1.00 | .40 | `.32` lower wick | `max(.32,.25)=.32` | rejection=true |
| BUY dưới wick | 100/100.4/100.5/99.9 | .60 | .40 | `.10` | `.32` | false |
| SELL đạt, bằng ngưỡng | 100/99.6/100.375/98.875 | 1.50 | .40 | `.375` upper wick | `max(.32,.375)=.375` | rejection=true |
| SELL dưới wick | 100/99.6/100.1/99.0 | 1.10 | .40 | `.10` | `.32` | false |
| Doji/range dương | 100/100/100.4/99.6 | .80 | 0 | `.40` lower/upper wick | `.20` | false vì close không có màu |
| Range zero | 100/100/100/100 | 0 | 0 | 0 | 0 | false vì `range<=0` |

“Bằng ngưỡng” ở đây là directional wick đúng bằng `threshold`; khi kiểm thử tạo đúng giá trị bằng decimal/tick grid thì expected là true nếu close đúng màu. Một rejection đúng vẫn chỉ được dùng nếu thuộc entry visit hiện tại và follow-through không quá 3 M15 bar; rejection cũ ngoài visit/đã quá 12 bar là `M15_NO_CONFIRMATION`.
| Protective vs refined zone | Protective bounds là original zone; refined bounds chỉ dùng entry | boundary type | Quy ước khởi đầu | SL/invalidation không được dùng refined bounds để nới rủi ro | Tách precision entry khỏi bảo vệ cấu trúc. |
| Top-K display per family | `6` FVG/OB; `5` S/D; liquidity `3` | item/family | `_MAX_FVG=6`, `_MAX_ORDER_BLOCKS=6`, `_MAX_SD_ZONES=5`, `_MAX_LIQUIDITY_LEVELS=3` | Sort deterministic; vượt K thì giữ record raw ngoài display nếu persistence cần | Giữ payload bounded và khớp runtime. |
| Alternative zones | `3` | zone/side | Quy ước khởi đầu; phù hợp consumer/risk alternatives | Không có selected zone → alternatives không tự thành READY | Hỗ trợ fallback có giới hạn. |
| History coverage | Lifetime + `14` ATR warm-up + `48` M15 confirmation lag + `5` pivot context | bar theo TF | Tổng hợp P1/P2/P7/P10 | Nếu không đủ phải gắn `coverage_incomplete`, không lấp dữ liệu | Đủ replay deterministic cho tuổi thọ đã chọn. |
| Numeric precision | Internal float; serialize tối đa `15` significant digits; comparisons theo tick/ATR tolerance | số | Cách serialize hiện hành + tick policy | Không round giữa các bước tính; round một lần lúc output | Tránh drift do làm tròn từng bước. |
| Scan performance target | p50 `<=2s`, p95 `<=5s` cho một symbol/snapshot trên máy cá nhân chuẩn | wall-clock | Quy ước khởi đầu, target kiểm chứng task 15 | Đo warm-cache và cold-cache riêng; vượt target phải có profile | Đặt mục tiêu đo được, không gọi là tối ưu. |
| Scorer evaluation count | `1` lần/snapshot; prefilter reuse canonical result | call/snapshot | Caller inventory task 2 | Fast path không chấm lại survivor | Giảm bất nhất giữa Analyze và Scanner. |

## Ma trận nguồn và trách nhiệm review

| Nhóm | Giá trị lấy trực tiếp từ code | Giá trị quy ước khởi đầu cần review |
|---|---|---|
| Dữ liệu/ATR | ATR14, warm-up 15, TF interval, coverage 60/60/30/15, cutoff đã đóng, tick-size fallback | Session-gap handling khi metadata provider không đủ |
| Structure | Pivot 5/2, ATR filter 0.2, structure event window M15 48, protected swing semantics | Equal-level/break buffer 0.10 ATR + 2 tick, bootstrap, lifetime D1/H4/H1 |
| Zone detector | FVG/OB/SD limits, OB 1 candle, SD base 3/5/7/10, SD impulse 1.5 avg range | FVG quality thresholds, OB association, S/D expiry semantics |
| Lifecycle | Stale D1/H4/H1/M15 20/30/50/80, freshness bands 3/8/16 | Visit tolerance, reaction follow-through, dwell/penetration, D1 reaction lifetime |
| M15/geometry/output | M15 15/48/3/0.3, zone hard distance 3 ATR, max width 1 ATR, top-K family limits | M15 expiry/max-run, minimum zone width, overlap, numeric/performance targets |

## Tiêu chí hoàn thành task 8

- Mọi ngưỡng bắt buộc trong phụ lục P đã có giá trị, đơn vị, nguồn/căn cứ, lý do và điều kiện biên.
- Không để trống hoặc bỏ ngỏ một ngưỡng bắt buộc; các giá trị chưa có bằng chứng runtime đều được ghi là quy ước khởi đầu.
- Không thay đổi runtime trong task này. Việc chuyển bảng thành constants/contracts và viết regression tests thuộc các task triển khai sau, sau khi Tech Lead review.
