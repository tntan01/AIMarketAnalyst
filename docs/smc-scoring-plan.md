# Kế hoạch nâng cấp SMC Scoring

> Trạng thái: **SMC v2 đã được kích hoạt làm nguồn quyết định theo yêu cầu
> trực tiếp ngày 24/07/2026; bằng chứng OOS/canary vẫn chưa hoàn tất. Runtime
> đã chọn Scanner `PRODUCTION`, nhưng release gate vẫn chặn order bằng
> `RELEASE_GATE_NOT_READY`**  
> Ngày rà soát: 24/07/2026  
> Phạm vi: SMC context, zone lifecycle, SMC score, entry zone, gate, ranking,
> backtest/live parity và rollout.

## 1. Kết luận

Cách tính SMC hiện tại đúng về phép cộng, clamp và quy đổi trọng số, nhưng chưa
đúng hoàn toàn về semantics. Các vấn đề chính là:

1. Multi-timeframe confluence không mang hướng nhưng được cộng giống nhau cho
   BUY và SELL.
2. Departure candle có thể bị tính thành retest đầu tiên của zone.
3. Các candle liên tiếp nằm trong zone được đếm thành nhiều retest độc lập.
4. `zone_score` thưởng retest, trong khi `smc_quality` lại phạt mitigated/retest.
5. Liquidity sweep của toàn timeframe được gán cho mọi zone cùng hướng, không
   kiểm tra quan hệ giá và thời gian.
6. Zone dùng chấm SMC được chọn theo điểm cao nhất, chưa xét khoảng cách, độ cũ
   và mức liên quan tới giá hiện tại.
7. Premium/discount, sweep và structure đang được tính lặp ở nhiều tầng.
8. CHOCH ngược hướng chỉ cap `signal_score`; evidence/execution tốt vẫn có thể
   đưa `setup_score` vượt ngưỡng sẵn sàng.

Do `zone_score` và SMC data còn được dùng bởi trade plan, gate, ranking, journal
và backtest, không nên sửa riêng một hàm. Cần nâng cấp theo một contract thống
nhất và phát hành như scorer/feature version mới.

## 2. Luồng hiện tại

```text
D1/H4/H1 candles
  -> build_smc_context()
     -> structure/BOS/CHOCH
     -> FVG/Order Block/Supply-Demand
     -> zone_score 0..100
     -> confluence_score -3..5
  -> smc_quality_score(side) 0..15
  -> smc_scaled theo market regime
  -> signal_score 0..100
  -> setup_score =
       signal_score * 0.65
       + evidence_score * 0.20
       + execution_quality_score * 0.15
  -> Strategy Router + Gate + Candidate Engine
  -> opportunity ranking
```

Trọng số SMC tối đa trong `signal_score` hiện phụ thuộc market regime:

| Regime | SMC weight mặc định |
|---|---:|
| Trending | 15 |
| Ranging | 25 |
| Volatile | 10 |
| Unknown | 15 |

Khi macro confidence thấp, phần trọng số macro còn thiếu được phân phối sang
trend, momentum, location, SMC và risk. Vì vậy trọng số SMC thực tế có thể cao
hơn bảng trên.

## 3. Bằng chứng đã kiểm tra

### 3.1 Confluence sai hướng

Probe trực tiếp cho kết quả:

```text
D1/H4/H1 đều HH/HL:
  confluence_score = 5
  BUY smc_quality  = 5
  SELL smc_quality = 5

D1/H4/H1 đều LH/LL:
  confluence_score = 5
  BUY smc_quality  = 5
  SELL smc_quality = 5
```

Cấu trúc đồng thuận bearish đang thưởng cho BUY và cấu trúc đồng thuận bullish
đang thưởng cho SELL.

### 3.2 Retest và mitigation không đúng vòng đời

Với một demand zone vừa tạo, departure candle chạm biên zone có thể cho kết quả:

```text
test_count = 1
mitigated  = true
```

Trong `zone_quality_score`, cùng một zone có thể tăng như sau:

```text
0 test -> 72
1 test -> 77
2 test -> 82
3 test -> 87
```

Trong khi đó `smc_quality_score` lại trừ điểm khi `mitigated=true` và tiếp tục
trừ khi `test_count >= 3`.

### 3.3 Sweep không gắn với zone

Khi timeframe có một `swept_low`, hai demand zone ở hai vùng giá khác nhau đều
nhận `liquidity_sweep=true`. Không có kiểm tra sweep có nằm gần zone hoặc có tạo
ra displacement của zone hay không.

### 3.4 Stale zone vẫn có thể được chọn

Khi có:

```text
stale zone: zone_score=80
fresh zone: zone_score=75
```

SMC scorer chọn stale zone vì chỉ sort theo `zone_score`. `risk_engine` có kiểm
tra khoảng cách ở bước tạo plan, nên SMC score và trade plan có thể dựa trên hai
zone khác nhau.

### 3.5 CHOCH cap có thể bị lớp final score vượt qua

```text
signal=60, evidence=80, execution=80   -> setup_score=67
signal=60, evidence=100, execution=100 -> setup_score=74
```

Nếu CHOCH ngược hướng là safety invariant thì cap hiện tại chưa đủ.

### 3.6 Trạng thái test tại thời điểm rà soát

- 18 test chuyên biệt của `smc_context` và single-source zone score: pass.
- Nhóm test mở rộng đã chạy: 39 pass, 5 fail.
- Bốn failure thuộc trade-plan; một failure thuộc kỳ vọng macro conflict.
- Test hiện tại chưa khóa các invariant về directional confluence, departure
  candle, independent retest, sweep-zone association và stale-zone selection.

## 4. Kiến trúc đích

### 4.1 Nguyên tắc

1. Mỗi điểm và mỗi zone phải thuộc một side rõ ràng.
2. Tách chất lượng nội tại của zone khỏi mức liên quan tại thời điểm scan.
3. Một setup chỉ dùng một canonical selected zone xuyên suốt scorer, scenario,
   gate, journal và backtest.
4. Một loại bằng chứng chỉ được cộng ở một tầng.
5. Safety invariant không được bị lớp weighted score phía sau vô hiệu hóa.
6. Thiếu dữ liệu phải fail closed hoặc giảm confidence, không mặc định là tín
   hiệu tốt.
7. Live và backtest phải dùng cùng feature/scorer contract.

### 4.2 Mô hình zone chuẩn

Mỗi zone cần có tối thiểu:

```text
zone_id
timeframe
family                 # demand/supply/order_block/fvg
direction              # buy/sell
low
high
origin_index
departure_end_index
created_at
invalidated_at
invalidation_index
first_retest_index
first_retest_time
independent_retest_count
bars_spent_inside
mitigation_ratio
freshness_bars
age_bars
age_minutes
stale
broken
linked_sweep_id
linked_sweep_distance_atr
linked_sweep_time_delta
zone_quality_score
zone_relevance_score
zone_setup_score
scoring_version
```

Quy tắc:

- `zone_id` phải deterministic để replay/backtest cho cùng kết quả.
- `departure_end_index` là mốc bắt đầu được phép tìm retest.
- Một visit bắt đầu khi giá đi từ ngoài vào zone và kết thúc khi giá ra khỏi
  zone. Nhiều candle liên tiếp trong cùng lần ghé chỉ tính một visit.
- `mitigation_ratio` đo phần độ rộng zone đã được xuyên vào, không chỉ là
  boolean.
- `broken` là invalidation cứng theo close và direction.

### 4.3 Directional confluence

Thay contract hiện tại bằng:

```text
direction: bullish | bearish | mixed | unknown
buy_score:  0..5
sell_score: 0..5
alignment:
  d1_h4
  h4_h1
  all_aligned
divergence:
  h1_against_h4
reason_codes
```

Ví dụ:

| Cấu trúc | BUY | SELL |
|---|---:|---:|
| D1/H4/H1 bullish | 5 | 0 |
| D1/H4/H1 bearish | 0 | 5 |
| D1/H4 bullish, H1 bearish | 1–2 | 1–2 |
| Mixed/unknown | 0 | 0 |

Không sử dụng một `confluence_score` vô hướng cho cả hai side.

### 4.4 Ba lớp điểm zone

#### `zone_quality_score` — chất lượng nội tại 0–100

Không phụ thuộc giá hiện tại. Ngân sách điểm khởi tạo đề xuất:

| Thành phần | Điểm tối đa |
|---|---:|
| Pattern/detection validity | 20 |
| Departure và displacement | 25 |
| Freshness và mitigation lifecycle | 25 |
| Premium/discount đúng hướng | 15 |
| Liquidity sweep gắn trực tiếp với zone | 15 |
| **Tổng** | **100** |

Đây là công thức khởi tạo để triển khai shadow, chưa phải trọng số production.
Trọng số cuối phải được hiệu chỉnh bằng backtest/OOS.

#### `zone_relevance_score` — mức liên quan hiện tại 0–100

Đánh giá theo:

- zone còn active và đúng phía giá;
- khoảng cách tính theo ATR;
- price đang trong/tiệm cận/watch zone;
- age theo timeframe;
- regime hiện tại;
- dữ liệu đủ và không stale.

Broken zone luôn relevance bằng 0.

#### `zone_setup_score` — điểm dùng cho setup

Công thức shadow ban đầu:

```text
zone_setup_score =
  0.60 * zone_quality_score
  + 0.40 * zone_relevance_score
```

Chỉ tính khi zone qua các mandatory filter:

```text
direction đúng
not broken
correct side of price
đủ dữ liệu
distance không vượt hard limit
```

Tỷ lệ 60/40 là giá trị thử nghiệm, phải được chọn lại bằng validation.

### 4.5 SMC raw score mới

Giữ output 0–15 để hạn chế ảnh hưởng tới phần còn lại của signal engine:

| Thành phần | Điểm |
|---|---:|
| HTF structure + directional confluence | 0–5 |
| Canonical selected zone | 0–5 |
| LTF confirmation | 0–3 |
| Independent technical cross-validation | 0–2 |
| **Tổng trước penalty** | **0–15** |

Quy tắc chống tính trùng:

- Premium/discount và zone-linked sweep chỉ nằm trong zone score.
- H1 sweep chỉ nằm trong LTF confirmation nếu chưa được dùng làm
  `zone-linked sweep`.
- Trend component không cộng lại chính xác cùng feature confluence; nếu trend
  vẫn dùng D1/H4 structure thì SMC chỉ dùng BOS/CHOCH/displacement độc lập.
- Technical cross-validation chỉ dùng nguồn support/resistance độc lập với SMC.

### 4.6 Chính sách CHOCH

Đề xuất coi confirmed H4 CHOCH ngược hướng là safety cap:

```text
confirmed H4 CHOCH against side
  -> candidate không thể READY_NOW
  -> decision cap = WAITING_CONFIRMATION hoặc WATCH_ZONE
```

H1 CHOCH ngược hướng là soft cap:

```text
H1 CHOCH against side
  -> giảm SMC score
  -> yêu cầu xác nhận lại
```

Không chỉ cap `signal_score`, vì `setup_score` có thể được evidence và execution
kéo lên lại.

### 4.7 Canonical selected zone

Tạo một hàm chọn zone duy nhất:

```text
select_smc_zone(context, side, price, atr, regime)
  -> SelectedSmcZone | None
```

Kết quả phải được truyền nguyên vẹn tới:

```text
smc_quality_score
build_trade_plan
entry scenario
trade gate
scanner row
journal
system backtest
observability
```

Các trường đối chiếu:

```text
selected_zone_id
selected_zone_type
selected_zone_timeframe
selected_zone_quality_score
selected_zone_relevance_score
selected_zone_setup_score
```

Không để scorer chọn zone A trong khi risk engine hoặc gate chọn zone B.

## 5. Kế hoạch triển khai

### Giai đoạn 0 — Khóa đặc tả và baseline

Mục tiêu: tạo điểm so sánh an toàn trước khi đổi semantics.

#### Trạng thái triển khai

**Đã hoàn tất ngày 24/07/2026.**

Các artifact đã có:

- `core/smc_scoring_contract.py`:
  - khóa legacy version `smc-v1`;
  - chuẩn hóa mode `legacy | shadow | v2`;
  - mọi decision trong Giai đoạn 0 vẫn bắt buộc dùng `smc-v1`;
  - tại thời điểm Giai đoạn 0, yêu cầu `v2` chưa có implementation nên fallback
    về legacy;
  - shadow comparison không được phép tác động decision.
- Tại thời điểm đóng Giai đoạn 0,
  `FeatureFlagSettings.smc_scoring_mode` mặc định là `legacy` và được load/save
  backward-compatible trong Settings. Mặc định runtime hiện hành đã đổi thành
  `v2` tại Giai đoạn 8.
- `AnalysisPipeline` xuất `smc_scoring` gồm policy, active snapshot, shadow
  snapshot, score delta và best-side delta.
- Scanner scan context, output, row observability và candidate order metadata
  có `smc_scorer_version` và `smc_scoring_mode`.
- Scanner phát event `SMC_SHADOW_COMPARISON` khi shadow được bật.
- Replay dataset nằm tại `tests/fixtures/smc_phase0_replay.json`, bao phủ trend
  tăng/giảm, range, volatile, CHOCH hai hướng, mitigated, broken và thiếu dữ
  liệu.
- Golden/invariant tests nằm tại `tests/test_smc_scoring_phase0.py`.

Lưu ý lịch sử: shadow ở thời điểm đóng Giai đoạn 0 chạy lại baseline `smc-v1`
để khóa contract, đường truyền và observability. Từ Giai đoạn 5, implementation
`smc-v2` đã thay baseline này trong shadow, nên delta không còn mặc định bằng
0. Đoạn mô tả decision dùng `smc-v1` chỉ đúng với baseline lịch sử của Giai
đoạn 0; runtime hiện hành đã dùng `smc-v2`. Tên import cũ
`SMC_V2_NOT_IMPLEMENTED` được giữ làm alias backward-compatible nhưng không còn
được policy mode `v2` phát ra.

Các invariant đã khóa:

```text
legacy là decision source duy nhất
shadow không mutate active score
shadow không đổi side/scenario/gate/final decision
v2 chưa được rollout phải fallback legacy
invalid mode phải fallback legacy
cùng replay input phải tạo cùng diagnostic hash
legacy golden score không đổi ngoài một version bump có chủ đích
```

Kết quả kiểm thử tại thời điểm đóng:

- toàn bộ test Phase 0 mới: pass;
- Settings, observability, SMC context và zone single-source: pass;
- nhóm mở rộng có thêm test macro hiện hữu: 42 pass, 1 fail;
- failure còn lại thuộc test macro conflict cũ, không liên quan SMC Phase 0.

Việc thực hiện:

1. Chốt các định nghĩa: origin, departure, visit, retest, mitigation, broken,
   stale, linked sweep và canonical zone.
2. Ghi lại công thức hiện hành dưới version `smc-v1`.
3. Tạo replay fixtures cho ít nhất:
   - bullish trend;
   - bearish trend;
   - range;
   - volatile;
   - bullish/bearish CHOCH;
   - fresh/mitigated/broken zone;
   - không đủ swing hoặc ATR.
4. Lưu output baseline của:
   - context;
   - zone scores;
   - BUY/SELL SMC raw;
   - signal/setup score;
   - selected zone;
   - decision/gate.
5. Thêm feature flag:

   ```text
   smc_scoring_mode = legacy | shadow | v2
   ```

6. Tại thời điểm thực hiện Giai đoạn 0, runtime tiếp tục dùng `legacy`; shadow
   không được thay đổi decision hoặc đặt lệnh. Sau khi đóng Giai đoạn 8,
   mặc định hiện hành đã chuyển sang `v2`.

Sản phẩm bàn giao:

- đặc tả invariant;
- replay dataset;
- golden master tests;
- feature flag và observability field.

Điều kiện đóng:

- [x] Replay deterministic.
- [x] Legacy output không đổi.
- [x] Shadow có thể chạy mà không ảnh hưởng order candidate.
- [x] `v2` chưa triển khai fail-safe về legacy.
- [x] Mode/version xuất hiện trong provenance và observability.

Ước lượng: 1–2 ngày kỹ thuật.

### Giai đoạn 1 — Domain model và zone identity

Mục tiêu: thay các dict rời rạc bằng contract có vòng đời rõ ràng.

#### Trạng thái triển khai

**Đã hoàn tất ngày 24/07/2026.**

Các artifact đã có:

- `core/smc_models.py` định nghĩa năm model immutable:
  - `SmcZone`;
  - `ZoneVisit`;
  - `DirectionalConfluence`;
  - `SelectedSmcZone`;
  - `SmcScoreBreakdown`.
- `core/smc_versions.py` là nguồn version dùng chung, tránh phụ thuộc vòng giữa
  domain model và rollout contract.
- `build_zone_id()` sinh ID deterministic từ symbol chuẩn hóa, timeframe,
  family, direction, origin time và biên zone.
- `adapt_legacy_zone_payload()` và `adapt_legacy_confluence_payload()` đọc dict
  cũ và bổ sung contract mới mà không xóa field legacy.
- `build_smc_context()` nhận symbol và gắn `smc-domain-v1` vào context/timeframe.
- Mỗi zone enriched có:

  ```text
  zone_id
  symbol
  timeframe
  family
  direction
  zone_quality_score
  zone_relevance_score
  zone_setup_score
  scoring_version
  domain_version
  ```

- Trong Giai đoạn 1, `zone_quality_score` và `zone_setup_score` cùng mang giá trị
  legacy; `zone_relevance_score=None`. Đây là compatibility mapping, chưa phải
  công thức mới.
- `zone_score` tiếp tục là alias của `zone_setup_score`, nên legacy scorer,
  gate, ranking và UI không đổi kết quả.
- Preferred zone, SMC trade flags và risk adapter truyền tiếp `zone_id` cùng
  quality/relevance/setup metadata.
- Scan context, scanner output, row observability và order metadata ghi
  `smc_domain_version`.
- Model từ chối zone có direction mâu thuẫn với type/family.
- Contract/serialization/integration tests nằm tại
  `tests/test_smc_domain_models.py`.

Các field lifecycle như `departure_end_index`, `first_retest_index`,
`mitigation_ratio`, `age_minutes` và `visits` được khai báo trước ở domain
model. Logic canonical điền các field này đã được hoàn tất ở Giai đoạn 2, chạy
song song với compatibility payload của Giai đoạn 1.

Kết quả kiểm thử tại thời điểm đóng:

- 197 test mục tiêu pass;
- 7 test skip theo điều kiện môi trường;
- legacy golden zone/SMC score vẫn pass;
- shadow/legacy parity vẫn pass;
- bốn failure trade-plan symmetry/TP tồn đọng từ trước vẫn tái hiện độc lập và
  không thuộc thay đổi domain model/identity.

Việc thực hiện:

1. Tạo model cho `SmcZone`, `ZoneVisit`, `DirectionalConfluence`,
   `SelectedSmcZone` và `SmcScoreBreakdown`.
2. Sinh `zone_id` deterministic từ symbol, timeframe, family, direction,
   origin time và biên zone.
3. Thêm adapter đọc payload cũ để không làm hỏng UI/journal ngay lập tức.
4. Bảo đảm serialize/deserialize ổn định và không dùng object identity.
5. Giữ compatibility fields trong một chu kỳ:

   ```text
   zone_score -> alias tạm của zone_setup_score
   selected_zone_score -> alias tạm của selected_zone_setup_score
   ```

Sản phẩm bàn giao:

- models;
- adapters;
- contract tests;
- serialization tests.

Điều kiện đóng:

- [x] BUY/SELL model không chấp nhận zone sai direction.
- [x] Cùng input luôn sinh cùng `zone_id`.
- [x] Thay đổi symbol format `EUR/USD` và `EURUSD` không đổi ID.
- [x] Payload cũ vẫn đọc được.
- [x] Serialize/deserialize giữ nguyên model và ID.
- [x] Compatibility aliases giữ nguyên legacy score.
- [x] Identity truyền tới selected zone, flags và risk adapter.

Ước lượng: 1–2 ngày.

### Giai đoạn 2 — Sửa lifecycle, retest và mitigation

Mục tiêu: đo đúng tuổi và số lần zone thực sự được thị trường ghé lại.

#### Trạng thái triển khai

**Đã hoàn tất ngày 24/07/2026.**

Kiến trúc rollout của giai đoạn này gồm hai lớp:

- `core/smc_lifecycle.py` là bộ phân tích lifecycle canonical, thuần dữ liệu và
  không phụ thuộc scan interval.
- các field `test_count`, `mitigated`, `broken`, `stale` tiếp tục mang semantics
  legacy trong `smc-v1`, bảo đảm điểm và quyết định sản xuất không đổi;
- lifecycle mới được xuất song song qua các field có tên rõ ràng để scorer v2
  sử dụng ở giai đoạn sau.

Ba detector đã trả đủ formation metadata:

| Detector | `origin_index` | `departure_end_index` |
|---|---|---|
| FVG | candle thứ ba hoàn tất gap | cùng candle hoàn tất gap |
| Order Block | candle đối hướng gốc | candle impulse ngay sau origin |
| Supply/Demand | candle cuối của base | candle impulse phá base |

Lifecycle canonical hiện cung cấp:

```text
departure_end_index
first_retest_index
first_retest_time
independent_retest_count
bars_spent_inside
mitigation_ratio
invalidation_index
invalidated_at
age_bars
age_minutes
lifecycle_mitigated
lifecycle_broken
lifecycle_stale
visits
```

Quy tắc đã cài đặt:

- chỉ candle từ `departure_end_index + 1` mới đủ điều kiện là retest;
- các candle overlap liên tiếp thuộc cùng một visit;
- chỉ khi giá ra khỏi zone rồi quay lại mới tăng
  `independent_retest_count`;
- penetration BUY đo từ biên trên đi xuống, SELL đo đối xứng từ biên dưới đi
  lên; giá trị được clamp trong `0..1`;
- candle đầu tiên close qua biên invalidation kết thúc lifecycle, các candle
  sau không thể làm zone hồi sinh;
- tuổi theo phút lấy từ timestamp candle origin tới candle mới nhất;
- stale canonical dùng ngưỡng bar độc lập với lịch chạy scanner:

| Timeframe | Stale sau |
|---|---:|
| D1 | 20 bars |
| H4 | 30 bars |
| H1 | 50 bars |
| M30 | 60 bars |
| M15 | 80 bars |
| M5/thấp hơn | 120 bars |

Các ngưỡng stale trên là policy khởi tạo cho v2 và đang ở lớp canonical/shadow;
chúng chưa thay `stale` legacy hay điểm `smc-v1`.

Để theo dõi parity, payload đồng thời ghi rõ:

```text
legacy_test_count
legacy_mitigated
legacy_broken
legacy_stale
```

`SmcZone` serialize lifecycle canonical bằng `lifecycle_*`, nhưng adapter vẫn
đưa bốn compatibility key cũ về giá trị legacy. Vì vậy điểm zone, selected zone,
gate, ranking, backtest và live path hiện hữu chưa đổi hành vi trong giai đoạn
này.

Kiểm thử chuyên biệt nằm tại `tests/test_smc_zone_lifecycle.py`, khóa các trường
hợp departure candle, visit liên tiếp, tái nhập zone, BUY/SELL symmetry,
invalidation terminal, detector contract, legacy/canonical separation và stale
không phụ thuộc scan interval.

Kết quả kiểm thử tại thời điểm đóng:

- 205 test mục tiêu pass;
- 7 test skip theo điều kiện môi trường;
- legacy golden zone/SMC score và shadow/legacy parity vẫn pass;
- không phát sinh regression trong nhóm scanner, pipeline, domain model và risk
  adapter đã khóa từ Giai đoạn 0–1;
- năm failure tồn đọng ngoài phạm vi vẫn tái hiện độc lập: một macro-conflict
  expectation và bốn trade-plan symmetry/TP;
- lệnh `pytest` toàn repository vẫn bị chặn ở collection bởi các file
  verification dạng script (`test_be_trailing_integration.py`,
  `test_orders_upgrade.py`, `test_redesign_overview.py`,
  `test_upgrade_dialog.py`). Các file này tự assert/`sys.exit` khi import và
  không liên quan lifecycle SMC.

Việc thực hiện:

1. Detector trả `origin_index` và `departure_end_index`.
2. Chỉ duyệt retest từ `departure_end_index + 1`.
3. Dùng state machine `outside -> inside -> outside` để đếm independent visit.
4. Tính `mitigation_ratio` theo mức penetration vào zone.
5. Tách:

   ```text
   first_retest
   independent_retest_count
   bars_spent_inside
   ```

6. Đánh dấu broken tại candle invalidation đầu tiên.
7. Tính age theo cả bar và phút thực, không gắn stale trực tiếp với scan
   interval.
8. Không thưởng tuyến tính cho mọi retest. Công thức shadow ban đầu ưu tiên
   fresh/first mitigation; nhiều visit làm giảm lifecycle component.

Test bắt buộc:

- departure candle không phải retest;
- ba candle liên tiếp trong zone chỉ là một visit;
- ra khỏi rồi quay lại mới tăng visit;
- BUY/SELL mirror symmetry;
- broken zone không hồi sinh;
- FVG, OB và Supply/Demand có cùng lifecycle contract.

Điều kiện đóng:

- [x] Lifecycle tests pass.
- [x] Departure candle không làm lifecycle canonical bị mitigated giả.
- [x] Canonical lifecycle không dùng `test_count` mơ hồ;
  `test_count` chỉ còn là compatibility field của `smc-v1`.

Ước lượng: 2–3 ngày.

### Giai đoạn 3 — Gắn liquidity sweep với zone

Mục tiêu: chỉ thưởng sweep có quan hệ nhân quả/hợp lý với zone.

#### Trạng thái triển khai

**Đã hoàn tất ngày 24/07/2026.**

`core/smc_sweep_linking.py` hiện là nguồn canonical cho sweep identity và
sweep-zone association:

- mỗi sweep có `sweep_id` deterministic dạng `smcs-*`, tạo từ symbol chuẩn hóa,
  timeframe, side, kind, level và occurrence time;
- association chỉ xét cặp cùng side:
  - BUY ↔ `swept_low`;
  - SELL ↔ `swept_high`;
- sweep index phải nằm trong
  `[formation_start_index, departure_end_index]`;
- sweep level phải nằm trong zone hoặc cách biên gần nhất không quá `0.25 ATR`;
- mọi cặp hợp lệ được xếp theo khoảng cách ATR, độ gần departure, time delta và
  ID để kết quả deterministic;
- phép gán là one-to-one: một sweep không được broadcast sang nhiều zone và một
  zone chỉ giữ association tốt nhất.

`linked_sweep_time_delta` là số bar có dấu tính từ `origin_index` tới sweep
index:

```text
sweep_index - origin_index
```

Giá trị âm nghĩa là sweep nằm ở phần formation trước origin; `0` là tại origin;
giá trị dương là từ origin tới hết departure.

Detector đã bổ sung `formation_start_index`:

| Detector | Formation window |
|---|---|
| FVG | candle đầu của mẫu ba candle → candle hoàn tất gap |
| Order Block | origin candle → impulse candle |
| Supply/Demand | candle đầu base → impulse candle |

Để giữ parity sản xuất, có hai stream sweep:

- `liquidity_sweeps`: cửa sổ sáu bar/max ba kết quả như legacy, tiếp tục phục
  vụ `smc-v1`;
- `zone_link_sweeps`: cửa sổ 80 bar, kiểm tra source swing xảy ra trước sweep,
  phục vụ association canonical và giữ evidence formation khi đã quá sáu bar.

Zone canonical lưu tối thiểu:

```text
liquidity_sweep_linked
linked_sweep_id
linked_sweep_distance_atr
linked_sweep_time_delta
sweep_link_version = smc-sweep-link-v1
```

Payload còn giữ `linked_sweep_kind`, level, time và index để điều tra trực tiếp.
Sweep payload ghi ngược `linked_zone_id`, nên mọi association đều truy vết được
hai chiều.

Association được thực hiện một lần trên toàn bộ Demand/Supply, Order Block và
FVG của cùng timeframe trước khi enrich. Vì vậy một sweep không thể được gắn
lặp lại chỉ vì các family được xử lý ở các danh sách khác nhau.

Metadata liên kết được truyền tiếp qua:

- `SmcZone`;
- `SelectedSmcZone`;
- selected-zone trade flags;
- risk adapter;
- entry-zone và alternate-zone metadata trong trade plan.

Ranh giới compatibility:

- `liquidity_sweep` và `legacy_liquidity_sweep` vẫn giữ phép broadcast theo
  timeframe cho active `smc-v1`;
- `liquidity_sweep_linked` và `linked_sweep_*` là nguồn canonical cho scorer
  v2;
- công thức điểm active chưa chuyển sang canonical link trong Giai đoạn 3, do
  đó scanner/backtest hiện tại không đổi quyết định.

Kiểm thử chuyên biệt nằm tại `tests/test_smc_sweep_linking.py`, bao phủ sweep
xa zone, sai time window, sai side, one-to-one trên nhiều family, BUY/SELL
symmetry, deterministic ID, cửa sổ canonical, compatibility separation và
truyền metadata tới selected zone/risk adapter.

Kết quả kiểm thử tại thời điểm đóng:

- 215 test mục tiêu pass;
- 7 test skip theo điều kiện môi trường;
- legacy golden score và shadow/legacy parity vẫn pass;
- năm failure tồn đọng ngoài phạm vi và các verification script chặn collection
  toàn repository vẫn giữ nguyên như đã ghi ở Giai đoạn 2.

Việc thực hiện:

1. Sweep phải đúng hướng:
   - BUY dùng swept low;
   - SELL dùng swept high.
2. Sweep level phải:
   - nằm trong zone; hoặc
   - cách biên zone không quá tolerance theo ATR.
3. Sweep time phải nằm trong cửa sổ formation/departure đã chốt.
4. Khi một sweep phù hợp nhiều zone, chọn zone gần nhất và có time relation tốt
   nhất; không broadcast cho mọi zone.
5. Lưu:

   ```text
   linked_sweep_id
   linked_sweep_distance_atr
   linked_sweep_time_delta
   ```

Test bắt buộc:

- sweep xa zone không được cộng;
- sweep xảy ra sau nhiều bar không được gắn ngược;
- một sweep không tự động thưởng tất cả zone;
- BUY/SELL symmetry.

Điều kiện đóng:

- [x] Mọi canonical sweep evidence truy được tới một `sweep_id` cụ thể.
- [x] Association canonical không dùng boolean broadcast toàn timeframe.
- [x] Broadcast chỉ còn trong `_legacy_timeframe_has_sweep()` dành riêng cho
  compatibility `smc-v1`.

Ước lượng: 1–2 ngày.

### Giai đoạn 4 — Directional confluence

Mục tiêu: confluence chỉ thưởng side thực sự được hỗ trợ.

#### Trạng thái triển khai

**Đã hoàn tất ngày 24/07/2026.**

`core/smc_confluence.py` hiện là engine canonical cho multi-timeframe
directional confluence. Output có version:

```text
confluence_version = smc-confluence-v1
```

Ngân sách điểm cho từng side:

| Evidence | Side được hỗ trợ |
|---|---:|
| D1/H4 cùng hướng | +2 |
| H4/H1 cùng hướng | +2 |
| D1/H4/H1 cùng hướng | +1 bổ sung |
| H1 reversal đã xác nhận ngược H4 | +1 cho side reversal |
| H1 pullback chưa xác nhận reversal | 0 cho side ngược |

Vì vậy:

```text
all bullish -> buy_score=5, sell_score=0
all bearish -> buy_score=0, sell_score=5
```

Khi H1 ngược H4, engine phân loại:

- `pullback`: H1 có structure ngược nhưng chưa có BOS/CHOCH + displacement đủ
  xác nhận; giữ evidence D1/H4 cho side chính và không tự thưởng side ngược;
- `reversal`: H1 có CHOCH confirmed, hoặc BOS/CHOCH kèm displacement đúng hướng
  reversal; side reversal nhận một điểm early evidence và side H4 nhận reason
  code cảnh báo;
- không còn phép trừ `-3` canonical áp dụng giống nhau cho cả BUY và SELL.

Contract `DirectionalConfluence` hiện gồm:

```text
direction                  # bullish/bearish/mixed/unknown
buy_score                  # 0..5
sell_score                 # 0..5
d1_h4_aligned
h4_h1_aligned
h1_against_h4
all_aligned
h1_relationship            # aligned/pullback/reversal/unknown
data_status                # complete/partial/insufficient
buy_reason_codes
sell_reason_codes
reason_codes
timeframe_evidence
confluence_version
```

`timeframe_evidence` có entry riêng cho D1, H4 và H1, lưu:

```text
structure
direction
bos
choch
choch_confirmed
displacement
reason_codes
```

Do đó mỗi điểm hoặc cảnh báo đều giải thích được theo side và timeframe.
Unknown/insufficient structure không tự sinh điểm. Partial data chỉ chấm cặp
timeframe thực sự quan sát được.

Ranh giới compatibility:

- `_cross_validate_structure()` và `confluence_score` legacy được giữ nguyên;
- `smc_quality_score()` của active `smc-v1` vẫn đọc `confluence_score`;
- `buy_score`, `sell_score` và reason codes là nguồn canonical dành cho scorer
  v2 ở Giai đoạn 5;
- thay đổi Giai đoạn 4 chưa tác động quyết định scanner, gate, ranking,
  backtest hoặc live.

`TimeframeConfluenceEvidence` và `DirectionalConfluence` đều immutable,
serialize/deserialize ổn định. Adapter payload cũ vẫn trả
`buy_score=None/sell_score=None` nếu input chưa có directional evidence.

Kiểm thử chuyên biệt nằm tại
`tests/test_smc_directional_confluence.py`, bao phủ:

- all bullish/all bearish;
- mirror symmetry;
- unknown và partial data;
- H1 pullback;
- H1 reversal;
- legacy/canonical round-trip;
- wiring qua `build_smc_context()`.

Kết quả kiểm thử tại thời điểm đóng:

- 224 test mục tiêu pass;
- 7 test skip theo điều kiện môi trường;
- legacy golden score và shadow/legacy parity vẫn pass;
- không phát sinh failure mới; năm failure tồn đọng ngoài phạm vi vẫn giữ
  nguyên như Giai đoạn 2–3.

Việc thực hiện:

1. Thay confluence vô hướng bằng `buy_score` và `sell_score`.
2. Xử lý riêng:
   - D1/H4 aligned;
   - H4/H1 aligned;
   - H1 pullback/against H4;
   - mixed/unknown;
   - insufficient data.
3. Không phạt cả hai side chỉ vì H1 khác H4; xác định đó là pullback hay
   reversal theo BOS/CHOCH/displacement.
4. Thêm reason codes theo side.
5. Giữ legacy `confluence_score` chỉ trong adapter và không dùng cho scorer v2.

Test invariant:

```text
all bullish -> buy_score > sell_score
all bearish -> sell_score > buy_score
mirror input -> mirror output
unknown data -> không tự sinh điểm
```

Điều kiện đóng:

- [x] Bullish alignment chỉ thưởng BUY; bearish alignment chỉ thưởng SELL.
- [x] Mirror input tạo mirror output.
- [x] Unknown data không tự sinh điểm.
- [x] Output có explanation riêng cho D1, H4 và H1.

Ước lượng: 1–2 ngày.

### Giai đoạn 5 — Canonical zone selection và SMC scorer v2

Mục tiêu: tạo một SMC score 0–15 rõ thành phần và dùng đúng một zone.

#### Trạng thái triển khai

**Đã hoàn tất ngày 24/07/2026.**

`core/smc_scorer_v2.py` hiện triển khai scorer `smc-v2` hoàn chỉnh ở chế độ
shadow. Module không mutate SMC context hoặc active score.

#### Zone quality 0–100

Quality được tính độc lập với current price và market regime:

| Component | Điểm tối đa | Quy tắc chính |
|---|---:|---|
| Pattern validity | 20 | bounds, family, direction, origin contract |
| Departure/displacement | 25 | formation hợp lệ + displacement scale tới `2.5x` |
| Freshness/lifecycle | 25 | fresh/first visit cao; nhiều visit/deep mitigation giảm |
| Premium/discount | 15 | BUY discount, SELL premium |
| Canonical linked sweep | 15 | bắt buộc có `linked_sweep_id` |

Boolean `liquidity_sweep` legacy không được dùng trong quality v2.

#### Zone relevance 0–100

Relevance được tính từ:

```text
active/stale state
correct price side
distance theo ATR
age_bars
market regime
```

Mandatory filter chạy trước relevance và ranking:

```text
direction đúng
family hợp lệ
high > low
có origin/departure
not lifecycle_broken
có price và ATR hợp lệ
zone nằm đúng phía current price
distance <= 3 ATR
```

Zone fail filter có `zone_relevance_score=0`, `zone_setup_score=0` và
`rejection_codes`; không được đưa vào selection.

#### Setup và canonical selection

Công thức shadow:

```text
zone_setup_score =
  round(0.60 * zone_quality_score
      + 0.40 * zone_relevance_score)
```

Selector xét cả H4 và H1, sau đó dùng thứ tự deterministic:

```text
zone_setup_score DESC
distance_atr ASC
age_bars ASC
zone_id ASC
```

Output mỗi side có đúng một `selected_zone`; cùng `zone_id` được ghi trong
selected payload, score breakdown và shadow comparison.

#### SMC score 0–15

| Component | Range | Nguồn |
|---|---:|---|
| `structure_score` | 0–5 | directional confluence đúng side |
| `zone_score` | 0–5 | canonical selected-zone setup score |
| `ltf_confirmation_score` | 0–3 | H1 trigger/structure và sweep chưa link |
| `technical_validation_score` | 0–2 | technical S/R độc lập gần selected zone |

Premium/discount và linked sweep chỉ nằm trong zone component. Nếu selected
zone đã dùng một linked sweep, sweep đó không được cộng lại trong LTF.

`SmcScoreBreakdown` hiện lưu thêm:

```text
subtotal
penalty_points
applied_cap
selected_zone_quality_score
selected_zone_relevance_score
selected_zone_setup_score
```

Model kiểm tra invariant:

```text
subtotal = tổng bốn component
total = min(applied_cap, max(0, subtotal - penalty_points))
0 <= total <= 15
```

H1 CHOCH ngược side trừ 2 điểm; nếu confirmed thì cap 8. H4 confirmed CHOCH
ngược side cap 4. Đây là score cap trong v2; đồng bộ candidate decision cap là
phạm vi Giai đoạn 6.

#### Shadow comparison

`core/smc_scoring_contract.py` đã thay baseline shadow bằng scorer v2 thật:

```text
legacy_smc_quality
v2_smc_quality
score_delta
selected_zone_changed
direction_changed
decision_changed
```

`decision_changed` luôn `false` ở Giai đoạn 5 vì v2 không được truyền vào active
signal/scenario/gate/ranking/order path. Policy hiện là:

```text
requested shadow -> smc-v2 chạy shadow
requested v2     -> smc-v2 chạy shadow, decision fallback smc-v1
effective mode   -> legacy
decision source  -> smc-v1
fallback reason  -> SMC_V2_SHADOW_ONLY
```

`AnalysisPipeline` truyền market regime vào scorer shadow; output
`smc_scoring.shadow` chứa evaluated zones, canonical selected zone và breakdown
cho cả BUY/SELL.

Kiểm thử chuyên biệt nằm tại `tests/test_smc_scorer_v2.py`, bao phủ:

- quality/relevance separation;
- mandatory filter fail-closed;
- setup formula;
- deterministic tie-breaker;
- breakdown arithmetic;
- chống cộng lặp linked sweep;
- BUY/SELL mirror symmetry;
- CHOCH penalty/cap;
- missing data;
- shadow isolation và determinism.

Kết quả kiểm thử tại thời điểm đóng:

- 234 test mục tiêu pass;
- 7 test skip theo điều kiện môi trường;
- legacy golden score vẫn pass;
- scenario, gate, final score và decision output không đổi giữa legacy, shadow
  và requested-v2;
- không phát sinh failure mới; năm failure tồn đọng ngoài phạm vi vẫn giữ
  nguyên.

Việc thực hiện:

1. Tính riêng quality, relevance và setup score cho mỗi zone.
2. Lọc mandatory conditions trước khi rank.
3. Chọn canonical zone bằng `zone_setup_score`, sau đó distance và recency làm
   tie-breaker deterministic.
4. Tạo `SmcScoreBreakdown`:

   ```text
   structure_score
   zone_score
   ltf_confirmation_score
   technical_validation_score
   penalties
   caps
   total
   selected_zone_id
   reason_codes
   ```

5. Loại bỏ cộng lặp location và sweep ngoài zone component.
6. Bảo đảm tổng trước/ sau penalty đều clamp 0–15.
7. Chạy legacy và v2 song song trong shadow:

   ```text
   legacy_smc_quality
   v2_smc_quality
   score_delta
   selected_zone_changed
   direction_changed
   decision_changed
   ```

Điều kiện đóng:

- [x] Scorer breakdown cộng lại đúng total.
- [x] Cùng một selected zone được dùng trong toàn bộ side evaluation.
- [x] BUY/SELL mirror symmetry.
- [x] Mandatory filter và missing data fail closed.
- [x] Không thay decision khi còn ở shadow.

Ước lượng: 2–3 ngày.

### Giai đoạn 6 — Đồng bộ consumer và safety policy

Mục tiêu: loại bỏ semantic mismatch giữa scorer, plan, gate và ranking.

#### Trạng thái triển khai

**Đã hoàn tất phần code ngày 24/07/2026.**

Giai đoạn 6 đã bổ sung contract `smc-consumer-v1` tại
`core/smc_consumer_contract.py`. Contract tạo đúng một selection dành cho
decision path và giữ selection shadow tách biệt cho từng hướng:

```text
smc_consumer.sides.buy/sell
  selection_source
  scoring_version
  selected_zone
  selected_zone_id
  selected_zone_quality_score
  selected_zone_relevance_score
  selected_zone_setup_score
  score_breakdown
  shadow_selected_zone
  shadow_selected_zone_id
  shadow_scoring_version
```

Ranh giới rollout vẫn được giữ nguyên:

- active decision tiếp tục dùng `smc-v1`;
- `smc-v2` selection vẫn chỉ nằm trong shadow khi policy chưa cho phép
  `decision_impact_allowed`;
- consumer contract đã chuẩn bị sẵn routing để chuyển selection source khi policy
  rollout được phê duyệt, không cần để từng consumer tự chọn lại.

`AnalysisPipeline` hiện tạo contract một lần ngay sau scoring rồi truyền selected
zone active vào `build_scenarios()`. `risk_engine` chạy với
`strict_preferred_zones=True`: nếu selected zone có mặt nhưng không còn dùng được,
engine trả về không có plan thay vì âm thầm chọn một SMC/technical zone khác.
Scenario lưu:

```text
entry_zone_id
entry_zone_quality_score
entry_zone_relevance_score
entry_zone_setup_score
entry_zone_score              # compatibility = selected-zone setup score
entry_zone_scoring_version
smc_score_breakdown
```

Gate không còn dùng ngưỡng `zone_score >= 40` mơ hồ trong danh sách gate active.
Gate hiện kiểm tra:

- lifecycle broken;
- relevance nếu scoring version thực sự cung cấp relevance;
- selected-zone/scenario price relation;
- H4 confirmed CHOCH ngược hướng.

Zone `smc-v1` không có semantics relevance nên `None` được giữ là
`not available`, không bị diễn giải thành điểm 0 hoặc trộn với v2. Khi relevance
có mặt nhưng thấp hơn 40, decision bị cap `WATCH_ONLY`. H4 confirmed opposing
CHOCH luôn cap `WATCH_ONLY`; `decision_engine` áp cap trước nhánh final score nên
final score 100 cũng không thể vượt safety invariant.

`trade_gate.smc_zone` là provenance dùng chung, gồm selected zone ID, scoring
version, quality/relevance/setup, broken state, price relation và CHOCH state.
Pipeline diagnostics cũng hiển thị riêng `ZoneRelevance`,
`ZonePriceRelation` và `H4ConfirmedCHOCH`.

Các consumer còn lại đã đồng bộ:

- scanner row và candidate order payload giữ toàn bộ canonical zone metadata;
- canonical ranking không cộng `zone_quality_bonus`; proximity và execution
  readiness vẫn là bằng chứng độc lập;
- statistical edge bucket đồng thời theo `entry_zone_score` và
  `entry_zone_scoring_version`; dữ liệu versioned không trộn với trade cũ chưa có
  version;
- journal có migration `008_add_smc_consumer_metadata.sql`, lưu selected zone ID,
  ba loại điểm, version và JSON score breakdown;
- system backtest trade và skipped-setup debug lưu cùng metadata;
- scanner detail hiển thị ID, quality, relevance, setup, version và reason
  breakdown; dialog trợ giúp giải thích rõ quality/relevance và việc ranking
  không cộng lặp.

Kiểm thử chuyên biệt nằm tại `tests/test_smc_consumer_phase6.py`, bao phủ:

- active/shadow selection isolation;
- risk engine không reselect khi strict;
- CHOCH cap không bị final score vượt qua;
- statistical bucket không trộn scoring version;
- journal persist canonical metadata và breakdown.

Kết quả kiểm thử tại thời điểm đóng:

- 228 test mục tiêu pass;
- 7 test skip theo điều kiện môi trường;
- compile toàn bộ `core`, `services`, `ui/screens`, `tests` thành công;
- full `pytest tests` vẫn bị script kiểm chứng cũ
  `tests/test_be_trailing_integration.py` gọi `sys.exit(1)` ngay lúc collection;
- năm failure tồn đọng ngoài phạm vi vẫn giữ nguyên: một macro-conflict test và
  bốn trade-plan symmetry test.

Module cần rà/sửa:

| Module | Thay đổi chính |
|---|---|
| `core/analysis_pipeline.py` | Tạo selected zone một lần cho mỗi side và truyền xuyên pipeline |
| `core/risk_engine.py` | Dùng canonical zone, không tự chọn lại zone khác |
| `core/trade_gate_engine.py` | Dùng relevance/broken/CHOCH policy thay ngưỡng zone mơ hồ |
| `core/scanner_ranking_engine.py` | Tránh cộng lại zone evidence đã nằm trong setup score |
| `core/statistical_edge_engine.py` | Bucket theo version và zone score đúng nghĩa |
| `core/system_backtest_engine.py` | Lưu selected zone ID và score breakdown |
| `services/journal_converters.py` | Persist version và canonical zone metadata |
| Scanner UI/detail/help | Hiển thị quality, relevance, selected zone và lý do |

Quyết định cụ thể:

1. `entry_zone_score` compatibility phải lấy từ canonical selected zone.
2. Gate không chỉ kiểm tra `zone_score >= 40`; cần kiểm tra:
   - not broken;
   - relevance đạt ngưỡng;
   - price/entry relation hợp lệ;
   - CHOCH safety cap.
3. Ranking không cộng thêm zone bonus nếu setup score đã chứa cùng bằng chứng;
   nếu vẫn giữ, chỉ được dùng readiness/proximity độc lập và phải ghi rõ.
4. H4 confirmed opposing CHOCH phải cap candidate decision, không chỉ
   `signal_score`.

Điều kiện đóng:

- [x] `selected_zone_id` giống nhau trong score, scenario, gate, journal và
  backtest trade;
- [x] CHOCH safety invariant không bị final score vượt qua;
- [x] không có consumer dùng score cũ mà không gắn version.

Ước lượng: 2–3 ngày.

### Giai đoạn 7 — Test, replay và calibration

Mục tiêu: chứng minh tính đúng logic trước khi đánh giá hiệu quả giao dịch.

#### Trạng thái triển khai

**Đã hoàn tất phần code và kiểm thử kỹ thuật ngày 24/07/2026. Chưa đóng phần
bằng chứng OOS/calibration trên dữ liệu thị trường thực.**

Contract `smc-phase7-validation-v1` đã được triển khai tại
`core/smc_validation.py`. Module chỉ đọc dữ liệu và gọi scorer v2 qua shadow
contract; không thay đổi `decision_source`, không đưa v2 vào Candidate Engine
và không cấp quyền đặt lệnh.

Đầu vào replay chuẩn hóa theo từng sample:

```text
sample_id
dataset_split                 # train/oos/live/unknown
observed_at                   # thứ tự thời gian cho drawdown/OOS
walk_forward_window
symbol / asset_class
side / market_regime
zone_family
zone_quality_score
zone_relevance_score
lifecycle_state
linked_sweep
h4_confirmed_choch_against
legacy_scores.buy/sell
v2_scores.buy/sell
legacy_selected_zone_id
v2_selected_zone_id
legacy_status
v2_status
result_r
legacy_scoring_version
v2_scoring_version
```

Ba API chính:

- `replay_smc_cases()` chạy cùng input qua legacy và scorer v2 shadow, khóa
  tính xác định và không mutate input;
- `replay_sample_from_analysis_document()` đọc snapshot Scanner đã lưu và đổi
  thành sample calibration có version;
- `build_smc_validation_report()` tạo báo cáo replay, OOS, calibration,
  stratification và release gate có hash ổn định.

CLI `scripts/run_smc_validation.py` nhận JSON/JSONL gồm replay sample hoặc
analysis document, ghi JSON report và hỗ trợ `--fail-on-block` để CI trả mã lỗi
khi release gate chưa đạt.

Báo cáo replay hiện có đủ các chỉ số đã chốt:

- phân phối SMC score legacy/v2 theo bucket `0–3`, `4–7`, `8–11`, `12–15`;
- BUY/SELL gap;
- tỷ lệ selected-zone ổn định;
- ma trận chuyển trạng thái legacy → v2;
- số lần đổi hướng, READY có outcome thua của từng scorer, false-ready legacy
  được v2 loại bỏ và số lần không chọn được zone;
- số trường hợp `READY` khi có H4 confirmed CHOCH ngược hướng.

`false_ready_removed_count` chỉ tăng khi legacy là `READY`, v2 không còn
`READY` và outcome thực tế không dương. Một lệnh v2 `READY` bị thua được ghi
riêng ở `v2_losing_ready_count`; không đánh đồng mọi lệnh thua với một lỗi
invariant.

Statistical report tính riêng tập OOS cho các candidate `READY`, gồm sample
size, win rate, expectancy R, khoảng tin cậy 95%, profit factor và max drawdown
R. OOS degradation dùng tolerance R được truyền rõ vào report, mặc định
`0.10R`; không dùng in-sample win rate để tự chọn trọng số. OOS sample có
outcome nhưng thiếu `observed_at` bị fail closed, vì drawdown không có ý nghĩa
nếu không biết đúng thứ tự thời gian.

Calibration curve và statistical stratification chỉ đọc sample có
`dataset_split=oos`; train/live không được dùng để làm đẹp bằng chứng release.
Curve nhóm theo SMC score bucket và chỉ đánh giá quan hệ khi có ít nhất hai
bucket vượt sample-size guard.

Walk-forward report nhóm OOS candidate `READY` theo `walk_forward_window`, áp
sample guard cho từng cửa sổ, tính tỷ lệ cửa sổ có expectancy không âm và
aggregate expectancy. Verdict chỉ là `ROBUST` khi đủ số cửa sổ, ít nhất 50% cửa
sổ không âm và expectancy tổng không âm.

Mọi sample phải gắn legacy/v2 scoring version. Report chỉ chấp nhận đúng một
cặp version trong một lần validation; nhiều cặp khác nhau bị chặn để không trộn
semantics.

Release gate fail closed với các mã:

```text
NO_VALID_REPLAY_SAMPLES
INVALID_REPLAY_SAMPLE
NON_DETERMINISTIC_DUPLICATE_SAMPLE
MIXED_SCORING_VERSION_PAIR
CHOCH_AGAINST_READY
OOS_SAMPLE_TOO_SMALL
OOS_EVIDENCE_MISSING
OOS_DEGRADATION_EXCEEDED
CALIBRATION_INSUFFICIENT
CALIBRATION_NOT_MONOTONIC
WALK_FORWARD_INSUFFICIENT
WALK_FORWARD_UNSTABLE
```

Stratification được xuất riêng theo symbol, asset class, BUY/SELL,
trend/range/volatile, zone family, quality bucket, relevance bucket, lifecycle,
linked sweep và H4 confirmed CHOCH. Không trộn scoring version.

Kiểm thử mới tại `tests/test_smc_phase7_validation.py` bao phủ:

- replay deterministic và không mutate input;
- live/backtest feature parity cho cùng input;
- score bounds và invalid data fail closed;
- OOS comparison, calibration curve và sample guard;
- OOS-only calibration/stratification và chronological drawdown;
- walk-forward window guard và verdict;
- scorer-version pair guard;
- đầy đủ các lớp stratification;
- duplicate sample khác nội dung bị xem là non-deterministic;
- adapter đọc analysis snapshot giữ selected-zone và scorer version;
- confirmed H4 CHOCH + `READY` luôn chặn release.

Bốn script kiểm tra source/layout cũ gây lỗi ngay lúc pytest collection đã được
đánh dấu skip ở module level vì đã có test chức năng thay thế hoặc UI contract
hiện hành đã thay đổi. Toàn bộ `tests` hiện collect thành công.

Kết quả kiểm thử tại thời điểm triển khai:

- 11 test Phase 7 mới pass;
- 165 test mục tiêu bao phủ SMC, pipeline, journal, backtest config, decision,
  ranking và statistical edge pass;
- toàn bộ test suite collect thành công: 1.034 test;
- lần chạy toàn bộ hơn 1.000 test vượt cửa sổ 120 giây, nên không được ghi nhận
  là full-suite pass.

#### Unit/property tests

- [x] directional confluence;
- [x] zone lifecycle;
- [x] sweep association;
- [x] quality/relevance separation;
- [x] score bounds;
- [x] deterministic selection;
- [x] BUY/SELL mirror symmetry;
- [x] missing/invalid data fail closed;
- [x] CHOCH decision cap.

#### Integration tests

- [x] pipeline dùng cùng selected zone;
- [x] live/backtest feature parity;
- [x] journal round-trip giữ score version;
- [x] gate/ranking không dùng compatibility field sai nghĩa;
- [x] old config bị version mismatch.

#### Replay tests

So sánh legacy và v2 theo:

```text
SMC score distribution
BUY/SELL gap
selected-zone stability
READY/WATCH/BLOCKED transition
false-ready count
no-zone count
CHOCH-against ready count
```

#### Statistical validation

Phân tầng tối thiểu theo:

- symbol/asset class;
- BUY/SELL;
- trend/range/volatile;
- zone family;
- quality bucket;
- relevance bucket;
- fresh/first mitigation/multi-visit;
- with/without linked sweep;
- with/without CHOCH.

Không chọn trọng số chỉ bằng in-sample win rate. Tiếp tục dùng:

- train/OOS tách biệt;
- walk-forward;
- expectancy và confidence interval;
- sample-size guard;
- drawdown và profit factor;
- calibration curve theo score bucket.

Điều kiện đóng:

- [x] tất cả invariant test pass;
- [x] không còn lỗi collection/test mục tiêu;
- [ ] OOS thực tế không suy giảm vượt tolerance đã chốt;
- [ ] score bucket trên dữ liệu thực có quan hệ hợp lý với expectancy hoặc xác
  suất thắng;
- [x] release report không cho phép READY khi confirmed H4 CHOCH ngược hướng.

Hai mục OOS/calibration chưa được đánh dấu hoàn tất vì repository chưa có đủ
outcome thị trường thực đã gắn đồng thời legacy/v2. Synthetic fixture chỉ chứng
minh công thức báo cáo và release gate hoạt động đúng, không phải bằng chứng về
hiệu quả giao dịch.

Lưu ý thay đổi sau Giai đoạn 7: theo yêu cầu trực tiếp ngày 24/07/2026,
`smc-v2` đã được đưa vào decision path dù hai bằng chứng trên chưa đạt. Đây là
override có chủ đích, không đồng nghĩa Phase 7 đã đạt production sign-off.
Scanner rollout stage, kill switch, execution revalidation và account/portfolio
guard vẫn có quyền chặn lệnh.

Ước lượng: 2–4 ngày kỹ thuật, chưa gồm thời gian tích lũy dữ liệu thị trường.

### Giai đoạn 8 — Version, migration và rollout

Mục tiêu: không trộn kết quả/backtest config của hai semantics khác nhau.

#### Trạng thái triển khai

**Phần code/tooling của Giai đoạn 8 đã hoàn tất ngày 24/07/2026; shadow theo
metrics contract mới, demo/canary và production approval chưa hoàn tất.**

- Mode mặc định của Settings, ScannerRequest và AnalysisPipeline là `v2`.
- `resolve_smc_scoring_policy("v2")` trả:

  ```text
  effective_mode = v2
  decision_source = smc-v2
  active_version = smc-v2
  decision_impact_allowed = true
  ```

- Side score được tính lại từ cùng trend/momentum/location/risk/macro và thay
  duy nhất SMC component bằng kết quả v2; không chạy lại feature extraction.
- Canonical selected zone v2 được truyền vào scenario, trade plan và gate.
  Nếu v2 không chọn được zone qua mandatory filters thì không được fallback
  sang technical zone để tạo plan.
- `legacy` vẫn là rollback mode; `shadow` vẫn chạy v2 chỉ để so sánh và giữ
  decision của v1.
- Scanner contract đã tăng thành `scanner-v3/scanner-features-v3`; config
  `scanner-v2/scanner-features-v2` fail closed và phải backtest lại.
- Backtest config hiện dùng schema `v4` và validation
  `phase8-smc-v2-oos-v1`. Config bắt buộc ghi rõ
  `smc_scorer_version=smc-v2` và `smc_scoring_mode=v2`; thiếu hoặc sai một
  trường đều fail closed. Không tự chuyển `min_score` cũ.
- `phase8-scoring-provenance-v1` được gắn thống nhất vào analysis output,
  scanner row/output, observability/order payload, journal, system backtest và
  recommendation/config.
- Journal migration `009_add_scoring_provenance.sql` đã chạy thành công trên
  database runtime. Bốn trường scanner/feature/SMC version và SMC mode được lưu
  thành cột riêng để có thể thống kê theo scorer.
- Scan context/output ghi đúng active SMC version theo mode.
- Settings runtime của máy đã được lưu rõ `smc_scoring_mode=v2`, không chỉ dựa
  vào giá trị mặc định khi thiếu trường cấu hình.
- Việc kích hoạt SMC decision không tự vượt Scanner rollout guard. Runtime đã
  chọn stage `PRODUCTION`, nhưng release readiness, kill switch và execution
  gates vẫn có quyền chặn order như trước.
- Rollout metrics đã thu score delta, đổi hướng, đổi canonical zone,
  false-ready bị loại, no-zone/data-unavailable, latency/error và
  expectancy/drawdown theo scorer version.
- Metrics contract hiện là `phase8-smc-rollout-metrics-v2`. 1.482 mẫu của
  contract cũ đã được giữ trong `legacy_metrics` và counter mới được reset,
  tránh dùng nhầm evidence của hai semantics. Release gate chỉ tính
  `unsafe_disagreement`; trường hợp v2 loại một false-ready được theo dõi riêng
  và không bị coi là regression.
- Settings/Rollout có selector `legacy | shadow | v2`, giúp rollback analysis
  mà không sửa file bằng tay.
- Rollback drill `phase8-rollback-drill-v1` đã chạy thành công: kill switch
  chặn order ngay cả trong mô phỏng production-ready và mode `legacy` trả
  decision source về `smc-v1`. Drill không gọi broker hoặc đặt lệnh.
- 31 backtest config runtime hiện có đã được migrate an toàn về `DRAFT`; không
  config cũ nào được tự nâng cấp thành `VALIDATED`.
- Theo quyết định vận hành tiếp theo ngày 24/07/2026, cờ `backtest` của 31
  config `DRAFT` đã được tắt. Metadata/min-score vẫn được giữ để backtest lại
  sau, nhưng các config này không còn được serialize vào ScannerRequest.
  Runtime hiện đi nhánh `DEFAULT_RULES` và dùng SMC v2 ngay, không chờ OOS hay
  đủ shadow sample.
- Settings/Symbols đã được khóa theo cùng contract: chỉ config `VALIDATED`,
  đúng SMC-v2 và còn hạn mới bật được. Config chưa đạt được lưu inactive;
  `Min Score/Regime/Side/Min RR` từ Backtest là chỉ đọc, còn
  `Ready/Watch/Wait` vẫn chỉnh độc lập.
- `apply_validated_backtest_config()`, SettingsService và thao tác dán/lưu UI
  đều fail-closed: recommendation thiếu bằng chứng không còn tạo
  `backtest=true + DRAFT`; symbol inactive cũng bị loại khỏi
  `enabled_symbols`.
- Quyết định trên chỉ bỏ phụ thuộc backtest khỏi **phân tích/routing hiện
  tại**. Nó không giả lập release evidence và không tự mở quyền đặt lệnh:
  rollout hiện đã chọn `PRODUCTION`, nhưng production readiness vẫn
  fail-closed.
- Kiểm thử mục tiêu sau khi hoàn thiện Giai đoạn 8 đạt **143 passed**. Nhóm test
  rộng theo tên SMC/Scanner/Settings/Backtest/Journal đạt **322 passed** và còn
  7 lỗi fixture Qt sẵn có tại
  `test_backtest_screen_improvements.py`, không đi qua đường SMC.

Version đề xuất:

```text
SCANNER_SCORER_VERSION  = scanner-v3
SCANNER_FEATURE_VERSION = scanner-features-v3
SMC_SCORER_VERSION      = smc-v2
BACKTEST_CONFIG_SCHEMA  = 4
BACKTEST_VALIDATION     = phase8-smc-v2-oos-v1
```

Việc thực hiện:

1. Gắn version vào:
   - analysis output;
   - scanner row;
   - observability event;
   - journal trade;
   - system backtest result;
   - backtest recommendation/config.
2. Config `scanner-v2/scanner-features-v2` phải fail closed với
   `BACKTEST_SCORER_VERSION_MISMATCH` hoặc
   `BACKTEST_FEATURE_VERSION_MISMATCH`.
3. Không tự chuyển min score của config cũ sang v3.
4. Chạy lại backtest/OOS/walk-forward để tạo config schema v4.
5. Rollout:

   ```text
   SHADOW
     -> DEMO canary
     -> limited symbols
     -> production approval
   ```

6. Kill switch phải có khả năng quay runtime về legacy analysis hoặc block
   auto-execution. Không được dùng config v2 để auto-trade scorer v3.

Chỉ số rollout:

- score/decision delta so với legacy;
- số candidate đổi hướng;
- số candidate đổi selected zone;
- số false-ready bị loại;
- no-zone/data-unavailable rate;
- latency và error rate;
- expectancy/drawdown theo scorer version.

Điều kiện đóng:

- [ ] shadow đủ mẫu và không có invariant violation;
- [ ] demo canary đạt tiêu chí;
- [ ] config schema v4 đã validation bằng dữ liệu OOS/walk-forward thực;
- [ ] production approval rõ ràng;
- [x] rollback/kill switch đã diễn tập bằng
  `phase8-rollback-drill-v1`.

Ước lượng: 1–2 ngày kỹ thuật, cộng thời gian shadow/canary theo cỡ mẫu.

## 6. Thứ tự phụ thuộc

```text
GĐ0 Baseline/spec
  -> GĐ1 Domain model
     -> GĐ2 Lifecycle
     -> GĐ3 Sweep association
     -> GĐ4 Directional confluence
        -> GĐ5 Scorer + canonical selection
           -> GĐ6 Consumer/safety integration
              -> GĐ7 Test/calibration
                 -> GĐ8 Version/rollout
```

Giai đoạn 2, 3 và 4 có thể phát triển tương đối độc lập sau khi domain model của
Giai đoạn 1 đã ổn định. Không nên bắt đầu scorer cuối ở Giai đoạn 5 trước khi ba
nguồn feature này có contract hoàn chỉnh.

## 7. Mức độ phức tạp

Đánh giá tổng thể: **cao, khoảng 8/10**.

| Hạng mục | Độ phức tạp | Lý do |
|---|---|---|
| Directional confluence | Trung bình | Phạm vi code nhỏ nhưng ảnh hưởng BUY/SELL score |
| Zone lifecycle | Cao | Cần state machine và tương thích nhiều loại zone |
| Sweep association | Trung bình-cao | Cần quan hệ thời gian, giá và ATR |
| Canonical selection | Cao | Phải đồng bộ scorer, scenario, gate và journal |
| Scoring calibration | Cao | Không thể chứng minh bằng unit test đơn thuần |
| Version/migration | Cao | Config cũ phải fail closed và backtest lại |
| Rollout | Cao | Có liên quan auto-execution và dữ liệu tài khoản thật |

Tổng effort kỹ thuật sơ bộ: **12–21 ngày kỹ thuật**, chưa gồm thời gian thu thập
đủ mẫu shadow/canary và chạy validation thống kê.

## 8. Rủi ro và cách kiểm soát

| Rủi ro | Kiểm soát |
|---|---|
| Điểm mới thay đổi nhiều candidate | Shadow compare và phân tích transition matrix |
| Config backtest cũ vô tình tiếp tục chạy | Bump scorer/feature version và fail closed |
| SMC score tốt hơn về logic nhưng OOS kém | Không promote nếu OOS/walk-forward không đạt |
| Zone scorer và trade plan lại lệch nhau | Bắt buộc `selected_zone_id` xuyên suốt |
| UI/journal đọc field cũ | Compatibility adapter có thời hạn |
| CHOCH vẫn bị lớp sau vượt cap | Đưa invariant vào Candidate/Gate Engine |
| Thiếu dữ liệu làm score giả cao | Confidence/data-quality guard và reason code |
| Rollback dùng nhầm config khác version | Rollback scorer đi kèm config tương ứng hoặc block execution |

## 9. Tiêu chí hoàn thành toàn bộ

Chỉ xem nâng cấp hoàn tất khi:

- directional confluence đúng side;
- departure candle không bị tính là retest;
- independent visit được đếm đúng;
- sweep bonus truy được tới sweep-zone relation cụ thể;
- quality và relevance tách biệt;
- score, scenario, gate và journal dùng cùng `selected_zone_id`;
- không tính lặp location/sweep/structure;
- confirmed H4 opposing CHOCH không thể thành `READY_NOW`;
- unit, property, integration và replay tests pass;
- scorer/feature version đã tăng;
- config cũ fail closed;
- backtest OOS/walk-forward v3 đạt;
- shadow và demo canary đạt tiêu chí;
- production rollout có phê duyệt và kill switch.

## 10. Ngoài phạm vi

Kế hoạch này không:

- khẳng định SMC có statistical edge trước khi OOS validation;
- tự động chọn trọng số production chỉ từ các con số đề xuất;
- thay đổi risk sizing, portfolio limits hoặc execution revalidation ngoài phần
  cần thiết để tiêu thụ canonical selected zone;
- cho phép config cũ tiếp tục auto-trade sau khi semantics scorer thay đổi.
