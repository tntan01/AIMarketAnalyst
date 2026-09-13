# Đặc tả compatibility SMC — task 14

> **Trạng thái:** DRAFT — chờ Tech Lead review tại task 16.  
> **Mục đích:** chốt cách lưu/đọc kết quả SMC qua thay đổi công thức, phân biệt null với no-zone, giữ tính tái lập của cache/replay và không đưa nhãn phiên bản kỹ thuật lên UI.

## 1. Ranh giới compatibility

Có ba lớp identity khác nhau, không được trộn:

| Lớp | Identity | Mục đích |
|---|---|---|
| Candle history cache | `server + account_fingerprint + broker_symbol + timeframe` | Cache rolling dữ liệu broker; khi connection/config/history invalid thì full reload |
| SMC result cache | `symbol + as_of + canonical input digest + rule identity` | Tái sử dụng evaluation đúng cùng snapshot/rule; không dùng cho dữ liệu khác cutoff |
| UI/persistence payload | `contract_version + provenance + semantic fields` | Đọc hiện tại/lịch sử; version chỉ là metadata nội bộ, không phải lựa chọn engine |

Kết quả SMC mới không được lấy từ cache nếu thiếu một phần identity hoặc rule identity. Cache là tối ưu, không phải nguồn sự thật; source history hợp lệ luôn có thể dựng lại kết quả.

## 2. Rounding và kiểu dữ liệu

### Canonical rule

```text
features/components: float hoặc Decimal, mỗi giá trị trong [0,1]
S = 4*B + 7*Q + 2*L + 2*C
quality_score = 100*S/15          # giữ độ phân giải đầy đủ
quality_raw = round_half_up(S)    # đúng một lần, miền 0..15
```

- Không làm tròn từng feature, component hoặc contribution trước khi cộng.
- `round_half_up` được thực hiện từ biểu diễn thập phân canonical của `S` (`Decimal(str(S))` hoặc tương đương), không phụ thuộc banker’s rounding của binary float.
- Nếu `S=10.50`, `quality_raw=11`; nếu `S=15`, raw tối đa 15; không có raw 16.
- Nếu do lỗi input `S<0` hoặc `S>15`, validator fail-closed; không tự clamp để che lỗi. Feature hợp lệ phải được clamp `[0,1]` trước khi ghép.
- `quality_score` có thể lưu số thực; nếu UI cần số nguyên thì đó là display formatting riêng, không thay raw/canonical value.
- Component contribution vẫn giữ phần thập phân trong breakdown để replay/audit; raw là số nguyên duy nhất của SMC quality.

### Tách khỏi TechnicalScore

- `SMC quality` dùng công thức B/Q/L/C và raw tối đa 15.
- `TechnicalScore` giữ bốn thành phần và trọng số đã sở hữu ở lớp technical, trong đó SMC projection là input/evidence riêng theo contract; không đưa Trend/Momentum/Location, regime, R:R hoặc risk vào `S`.
- Không dùng SMC raw để thay đổi trọng số Trend/Momentum/Location; không dùng TechnicalScore để tính ngược B/Q/L/C.
- Khi thay đổi M15/AI/readiness/market gate, quality SMC của cùng setup không đổi; chỉ projection/readiness/final decision có thể đổi.

## 3. Null, no-zone và absence

| Tình huống | `quality_raw` | Selected fields | Status/reason | Ý nghĩa |
|---|---:|---|---|---|
| Đã đánh giá đủ core data, không có zone hợp lệ | `0` | `selected_zone_id=null`, setup/plan null | `NO_VALID_SETUP` / `NO_ZONE` | Không tìm thấy setup, không phải lỗi dữ liệu |
| Core D1/H4/H1, cutoff, ATR formation hoặc metadata bắt buộc thiếu/hỏng | `null` | Không chứng nhận selected/plan | `DATA_UNAVAILABLE` + reason cụ thể | Chưa đủ dữ liệu để kết luận |
| Zone candidate chưa confirmed/available | Không phải selected quality | Selected null hoặc watch candidate riêng | `WATCH_ZONE` + pending reason | Chưa được dùng entry |
| Zone invalid/expired/full-filled FVG | Không dùng quality active | Selected null nếu không còn sibling hợp lệ | `OUT_OF_STRATEGY`/watch history | Zone cũ chỉ còn historical evidence |
| M15 thiếu nhưng core/zone đủ | Không đổi | Giữ selected zone/quality nếu đã có | `WAITING_CONFIRMATION` + `M15_DATA_UNAVAILABLE` | M15 là readiness, không phải quality |
| M15 trigger expired nhưng plan hình học đã tồn tại | Không đổi | Giữ selected zone/visit/quality và plan | `WAITING_CONFIRMATION` + `TRIGGER_EXPIRED`; `plan_available=true` | Expiry hủy quyền confirmation, không xóa plan |
| Feature optional không có evidence sau khi dữ liệu đã đủ | Feature đó `0` | Vẫn chấm bình thường | Reason absence nếu cần | Không renormalize trọng số |

Quy tắc serialization:

- Các trường schema bắt buộc luôn có mặt; giá trị chưa biết dùng JSON `null`, không dùng `0`, chuỗi rỗng hoặc field giả.
- `selected_zone_id`, `selected_setup_id` giữ ID canonical của zone confirmed/usable kể cả watch/no-plan; `plan_reference` null khi planner chưa có plan và `confirmation_event_id` null khi chưa có confirmation. Chỉ no-zone/core-unavailable/không có candidate hợp lệ mới selected IDs null.
- `quality_raw=0` và `quality_raw=null` là hai contract khác nhau, validator/UI phải giữ khác nhau.
- Reader có thể nhận payload lịch sử thiếu field mới, nhưng phải gắn `compatibility_status=LEGACY_READER` và không tuyên bố payload đó là kết quả canonical hiện tại.

## 4. R16-03/R16-09 — legacy penalty và watch/no-plan

M15 là entry-visit/confirmation input, không phải B/Q/L/C input. Payload legacy có trường penalty có thể đọc để audit lịch sử, nhưng serializer current không được áp dụng penalty đó vào `S`, `quality_raw`, `quality_score` hay projected raw. Fixture stale expected sau fix là `penalty=0`, `quality_unchanged=true`, `WAITING_CONFIRMATION`.

Canonical watch/no-plan giữ `selected_setup_id`, `selected_zone_id`, selected quality và lifecycle của zone hợp lệ; chỉ `plan`, `plan_reference` là `null` và `plan_available=false`. `NO_ZONE` sau khi core đủ mới có selected IDs null và `quality_raw=0`; `DATA_UNAVAILABLE` có `quality_raw=null`. UI/consumer không được suy luận no-zone từ `plan=null`.

M15 confirmation ID là `<zone_id>:m15-visit-N:confirm-M`; `parent_lifecycle_visit_id` là nullable metadata/link khi parent event đã tồn tại, không nằm trong trigger identity. Nếu link được bổ sung sau H4 close, ID không đổi. `selected_visit_id` là `entry_visit_id` khi visit đã mở dù plan null; chưa có visit thì null. Thay hoặc thiếu M15 chỉ đổi readiness/confirmation fields. Đây là invariant serialization/cache, chưa triển khai runtime.

### 4.1 Rule identity và SMC result cache

### Canonical cache key

SMC result cache key được tạo từ canonical JSON có thứ tự key ổn định:

```text
smc-result:
  rule_identity=<canonical_rule_identity>
  :symbol=<normalized_symbol>
  :as_of=<UTC close cutoff>
  :sha256(canonical_input_json)[:16]
```

`canonical_input_json` phải bao gồm:

- symbol, `as_of`, interval/timeframe và candle content của D1/H4/H1/M15 đã đóng;
- OHLC, open time, close time/interval, thứ tự candle và gap/session metadata cần cho rule;
- tick size, nguồn tick size, ATR formation/current reference và data-quality/provenance ảnh hưởng eligibility;
- parameter policy identity: ATR/pivot, zone detector, lifecycle, sweep linking, B/Q/L/C, readiness và selection policy;
- source event/zone identity, original bounds, remaining/refined bounds, setup/visit/confirmation inputs;
- contract/scorer/structure/zone/lifecycle/selection identities nội bộ.

Không đưa `capture_source`, UI text, thứ tự dictionary hoặc comment AI vào digest nếu các trường đó không ảnh hưởng quyết định. Live và replay cùng dữ liệu/metadata phải hash giống nhau dù capture source khác.

### Rule identity

`canonical_rule_identity` là một record nội bộ, tối thiểu gồm:

```text
smc_scoring_contract = smc-scoring-canonical-2026-08
scorer_formula_identity = SMC_SCORER_VERSION hiện hành/đã được duyệt
structure_policy = protected-swing/BOS/CHoCH policy identity
zone_policy = OB/FVG/S-D policy identity
lifecycle_policy = visit/fill/expiry policy identity
selection_policy = coordinator/order/plan policy identity
parameter_digest = sha256(canonical parameter table)[:16]
```

Khi bất kỳ policy/parameter/contract nào đổi, rule identity đổi và cache/result cũ không được tái sử dụng như kết quả mới. Không đổi nhãn UI để lách cache compatibility.

### Invalidation

Cache/result phải bypass hoặc invalidate khi:

- candle broker sửa nội dung, timestamp, thứ tự hoặc gap làm thay causal history;
- `as_of`, symbol, timeframe, tick size source hoặc metadata execution ảnh hưởng rule thay đổi;
- thiếu history nguồn formation/lifetime, tail invalid, timestamp regression hoặc cache corrupt;
- parameter digest, scorer/contract/structure/zone/lifecycle/selection policy đổi;
- payload không parse được, digest mismatch hoặc provenance thiếu trường bắt buộc.

Thêm history cũ tương đương vào trước rolling window không được tạo ID zone mới nếu source identity/original bounds/as_of không đổi. Nếu source formation nằm ngoài history, kết quả phải `DATA_UNAVAILABLE`/coverage incomplete chứ không biến zone cũ thành fresh.

## 5. Đọc lịch sử và chuyển đổi payload

### Writer policy

- Writer mới chỉ ghi canonical contract hiện hành, `contract_version`, rule identity, snapshot/as_of, quality raw/score, selected setup/zone, lifecycle, confirmation, plan reference và reasons.
- Không ghi nhãn `v1`, `v2`, “legacy” hoặc lựa chọn engine lên UI. Version kỹ thuật chỉ nằm trong provenance/diagnostic/persistence để replay và migration.
- Không ghi đè journal, lệnh mở, SL/TP hoặc outcome lịch sử khi thay công thức.

### Reader policy

| Payload đọc được | Cách xử lý |
|---|---|
| Canonical contract + rule identity khớp | Đọc như current; có thể dùng cho consumer/replay cùng snapshot |
| Canonical contract khớp schema nhưng rule identity khác | Đọc như historical; không dùng làm current live result; recompute nếu cần |
| Legacy payload có score/zone cũ | Hiển thị theo ý nghĩa tại thời điểm tạo, gắn historical provenance; không diễn giải điểm cũ thành B/Q/L/C mới |
| Payload thiếu null/contract fields | Parse permissive nếu không mâu thuẫn; gắn legacy/compatibility reason; không tạo giá trị giả |
| Payload malformed/digest mismatch | Không dùng; trả compatibility/data error và yêu cầu dựng lại từ source |

Lịch sử cũ có thể được mở để người dùng xem “kết quả tại thời điểm tạo”. Reader không âm thầm chạy scorer mới trên payload thiếu nến rồi ghi đè kết quả cũ; replay mới phải có snapshot/cutoff/input đủ và ghi result mới riêng.

## 6. Compatibility với cache candle hiện có

`CandleHistoryCache` tiếp tục sở hữu identity broker hiện tại (`server`, `account_fingerprint`, `broker_symbol`, `timeframe`) và các fallback reason như cache missing, identity changed, configuration changed, tail invalid, timestamp regression, gap detected.

SMC layer xử lý kết quả cache như sau:

1. Nhận full history/tail đã validate, lọc candle đã đóng theo `as_of`.
2. Tính canonical input digest và rule identity.
3. Chỉ đọc SMC result cache khi cả hai identity khớp.
4. Nếu candle cache yêu cầu full reload, không báo result mới từ last-known-good tail; chờ history hợp lệ hoặc trả data unavailable.
5. Khi candle correction làm digest đổi, dựng result mới và giữ result cũ là historical artifact.

Candle cache identity thay đổi không tự đồng nghĩa công thức SMC đổi; ngược lại, rule identity đổi phải invalidate SMC result dù candle history không đổi.

## 7. Contract cho consumer, projection và UI

| Lớp | Được đọc | Không được làm |
|---|---|---|
| Canonical consumer | `quality_raw`, `quality_score`, selected IDs, readiness/status, provenance/reasons | Không map null thành 0 hoặc chọn lại zone |
| Technical projection | SMC raw/evidence theo projection contract | Không tái tạo B/Q/L/C hoặc thêm trọng số ngoài TechnicalScore |
| Scenario/entry | selected zone/plan/confirmation cùng lineage | Không dùng legacy score làm fallback current |
| Persistence | current và historical với compatibility marker | Không ghi đè lịch sử/lệnh mở để đổi công thức |
| UI | score semantic, zone, status, reasons, thời điểm | Không hiện nhãn phiên bản kỹ thuật, không gọi score là win rate |

Display semantics:

- `0` hiển thị “Chưa có setup hợp lệ” nếu status no-zone.
- `null` hiển thị “Thiếu dữ liệu” nếu status data unavailable.
- Zone confirmed nhưng chưa đủ readiness hiển thị “Theo dõi/Chờ xác nhận”, không hiển thị “sẵn sàng”.
- `READY_NOW` hiển thị “Đủ điều kiện kiểm tra lần cuối”, vì execution revalidation vẫn bắt buộc.

## 8. Compatibility matrix và ví dụ

| Input thay đổi | Snapshot digest | Rule identity | Expected |
|---|---|---|---|
| Chỉ đổi `capture_source`, cùng candle/cutoff/metadata | Giống | Giống | Cache hit; live/replay parity |
| Thêm M15 nhưng core/zone không đổi | SMC digest có thể đổi nếu M15 thuộc readiness input | SMC formula không đổi | Quality SMC giữ nguyên; readiness có thể đổi |
| Đổi ATR/pivot/zone threshold | Có thể cùng candle | Đổi | Cache miss; recompute, không dùng kết quả cũ làm current |
| Broker sửa một OHLC trước formation | Đổi | Giống | Cache miss; dựng lại zone/event/ID liên quan |
| Không có sweep sau khi đủ history | Đổi theo input nếu cần | Giống | `L=0`, không renormalize B/Q/C |
| Không có valid zone sau khi core đủ | Đổi theo snapshot | Giống | `quality_raw=0`, selected null, `NO_VALID_SETUP` |
| Thiếu H4 core data | Digest không hoàn chỉnh | Có thể giống | `quality_raw=null`, `DATA_UNAVAILABLE`, không fake no-zone |
| Đọc payload score cũ | Không dùng làm current key | Rule cũ | Historical display only; không diễn giải thành công thức mới |

Ví dụ rounding/maximum:

```text
B=Q=L=C=1 -> S=15 -> quality_raw=15
S=10.50   -> quality_raw=11
S>15 do input lỗi -> validator fail-closed, không trả raw=15 để che lỗi
```

## 9. Invariants cần khóa ở test sau review

- Cùng canonical input/rule identity cho cùng digest và cùng result; permutation dictionary/list không đổi hash/order.
- `quality_raw` chỉ nhận integer `[0,15]`; `quality_raw=null` chỉ dùng cho data unavailable, không dùng cho no-zone.
- Round-half-up đúng tại `.5`; không banker-round hoặc round từng component.
- Thay M15/AI/readiness/external gate không đổi SMC quality cùng setup.
- Rule identity/parameter digest đổi thì SMC cache miss; candle correction trước formation không giữ result cũ.
- Legacy result không được dùng làm current fallback; journal/lệnh mở/SL/TP không bị sửa.
- UI không hiển thị nhãn số thế hệ/engine; diagnostic vẫn truy được provenance và rule identity.

## 10. Tiêu chí hoàn thành task 14

- Đã chốt round-half-up một lần, component float/raw int, raw tối đa 15 và tách trọng số TechnicalScore ngoài SMC.
- Đã tách null/data-unavailable, no-zone/0, candidate pending và thiếu M15.
- Đã định nghĩa candle cache identity, SMC result cache key, rule identity, digest input và invalidation.
- Đã chốt đọc lịch sử theo ý nghĩa cũ, không diễn giải điểm cũ thành công thức mới, không đổi lệnh mở/historic artifact.
- Đã chốt UI không có nhãn số thế hệ/engine và consumer không tự chọn lại/fallback legacy.
- Không thay runtime trong task này. Việc đưa compatibility vào model/validator/cache/persistence/UI thuộc task 17–18, 38–39, 94–96 và 117–126 sau review tương ứng.
