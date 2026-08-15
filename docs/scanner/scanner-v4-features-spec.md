# Scanner V4 — Derivation Spec for candle → technical raws (Path B)

**Trạng thái: ĐÃ DUYỆT (2026-08-14) — §4 quyết định = (a).** Mọi công thức là **port
có tài liệu** từ V3 `core/signal_engine.py` (+ `core/technical_context.py`,
`core/indicators.py`), KHÔNG bịa, KHÔNG đổi threshold. Bắt đầu Bước 2 sau khi owner
nhìn lại bản cuối.

## 0. Mục tiêu và ranh giới

V4 scoring (`core/technical_signal_scorer.py:score_technical_signal`) CONSUMES các
raw đã tính sẵn: `trend`≤25, `momentum`≤20, `location`≤25, `smc`≤15 (+ `canonical_smc`).
Tầng target V4 HIỆN KHÔNG có candle→raw. Path B thêm module `core/scanner_v4_features.py`
(chưa tồn tại) để tạo 3 raw đầu từ d1/h4/h1, và xác định producer cho raw `smc`.

**Bounded refactor (bắt buộc để là "port có tài liệu", không bịa):**
- **Tái sử dụng** `core/technical_context.py:build_technical_snapshot` và
  `core/indicators.py` (EMA/RSI/MACD/ATR) — đây là 2 module tiền trang thấp KHÔNG nằm
  trong danh sách xóa V3 (cùng loại với `smc_models`). V3 `signal_engine`.
  `*_alignment_score` là thứ cần port.
- **Port công thức** của 3 raw từ `signal_engine` sang module mới (bản copy có kiểm
  chứng bằng parity test Bước 4), để sau khi xóa `signal_engine` đường V4 vẫn chạy.
- **Không sửa contract V4 đã khóa** (`scanner-v4`, `scanner-features-v4`, ...).
- **Fail-closed**: thiếu candle / raws không hợp lệ → trả None/UNKNOWN + reason code,
  tuyệt đối không số bịa.

## 1. Đầu vào sống (từ app / broker MT5)

Ba chuỗi Candle đã đóng (mỗi Candle: `open, high, low, close, time`):

| TF | yêu cầu tối thiểu | nguồn |
|---|---|---|
| D1  | ≥ 60 | history MT5 D1 |
| H4  | ≥ 60 | history MT5 H4 |
| H1  | ≥ 30 | history MT5 H1 |

**Thiếu → `TechnicalRawDerivationError` (fail-closed), không bịa.** Ngưỡng này chính
là ngưỡng của `build_technical_snapshot` (raise `ValueError` khi thiếu) — port giữ
nguyên, không tự đặt ngưỡng mới.

## 2. Bước trung gian (tái sử dụng `technical_context`)

`t = build_technical_snapshot(d1, h4, h1)` sinh dict chứa đúng các field mà 3 công
thức cần (giữ nguyên tên field để port mình bạch):

| field | nguồn tính | ghi chú |
|---|---|---|
| `price` | `h1[-1].close` | giá hiện tại |
| `ema50_d1`, `ema200_d1` | `indicators.ema(d1, 50/200)` | xác nhận trend D1 |
| `ema50_h4` | `indicators.ema(h4, 50)` | |
| `rsi_h4`, `rsi_h4_previous` | `indicators.rsi(h4, 14)` | wilder |
| `macd_histogram_h4` | `indicators.macd(h4,12,26,9).histogram` | dict `{value, previous_value, previous2_value, direction}` |
| `atr_h4`, `atr_d1` | `indicators.atr(h4/d1, 14)` | |
| `atr_avg_14d` | trung bình ATR D1 14 phiên | |
| `structure_d1`, `structure_h4` | `technical_context.detect_structure(swings)` | HH/HL | LH/LL | mixed | unknown |
| `support_zones`, `resistance_zones` | `technical_context.build_zones` | từ `swings[-6:]`, width=`max(atr*0.15, 0.0001)`, `confluence_count` từ swings[-10:] |
| `range_info` | `detect_range_window` | (không dùng bởi 3 raw này, giữ để tương thích) |

> **Finding vật lý (không bịa):** zone do `build_zones` tạo KHÔNG có key
> `test_count` hay `is_round_number`. Do đó trong `location_quality_score` (công thức
> bên dưới) hai hạng `test_count>=3 → -5` và `test_count>=5 → -3` luôn **inert** (test_count
> đọc = 0) khi nuôi bằng `build_technical_snapshot`; `is_round_number → +3` cũng inert.
> Chỉ `confluence_count>=3 → +5` từng kích hoạt. Port giữ NGUYÊN công thức V3 (kể cả
> các hạng inert) để parity tuyệt đối; không "tối ưu" gì cả.

## 3. Công thức được port (bản mình bạch, theo `signal_engine.py`)

Với mỗi side `buy` / `sell`:

### 3.1 `trend` ≤ 25
`signal_engine.trend_alignment_score(side, t)`:

- **buy** = Σ của: `8` nếu `ema50_d1 > ema200_d1`; `5` nếu `price > ema200_d1`;
  `5` nếu `(price > ema50_d1 or price > ema50_h4)`; `5` nếu `structure_h4 == "HH/HL"`;
  `2` nếu `(structure_d1 == "HH/HL" and structure_h4 == "HH/HL")`.
- **sell** = phản chiếu: `ema50_d1 < ema200_d1`; `price < ema200_d1`;
  `(price < ema50_d1 or price < ema50_h4)`; `structure_h4 == "LH/LL"`;
  `structure_d1 == "LH/LL" and structure_h4 == "LH/LL"`.
- kẹp `clamp(result, 0, 25)` (kết quả vốn ≤25 do Σ hạng dương).

### 3.2 `momentum` ≤ 20
`signal_engine.momentum_alignment_score(side, t)`:
- `value = rsi_h4 or 50.0`; `prev = rsi_h4_previous` (nếu None → `value`),
  `rsi_rising = value > prev`, `rsi_falling = value < prev`.
- `hist = macd_histogram_h4`; `now/prev/prev2` = value/previous_value/previous2_value.
- **buy**:
  - rsi_score = `_choose_one([(30<=value<=50 and rsi_rising, 8), (40<=value<=60 and not rsi_falling, 6), (60<value<=70 and not rsi_falling, 3), (value>75, 0)])`
  - macd_score = `_choose_one([(now>0 and now>prev>prev2, 10), (now<0 and now>prev>prev2, 6), (now>prev, 3), (now>0 and now<prev, 5)])`
- **sell**:
  - rsi_score = `_choose_one([(50<=value<=70 and rsi_falling, 8), (40<=value<=60 and not rsi_rising, 6), (30<=value<40 and not rsi_rising, 3), (value<25, 0)])`
  - macd_score = `_choose_one([(now<0 and now<prev<prev2, 10), (now>0 and now<prev<prev2, 6), (now<prev, 3), (now<0 and now>prev, 5)])`
- `macd_accel = (hist.direction == "increasing")`; `accel_bonus`:
  - **buy**: `+2` nếu `rsi_rising and macd_accel`; `-2` nếu `not rsi_rising and not macd_accel`.
  - **sell**: `+2` nếu `rsi_falling and not macd_accel`; `-2` nếu `not rsi_falling and macd_accel`.
- trả `clamp(rsi_score + macd_score + accel_bonus, 0, 20)`.
- `_choose_one(candidates)` = hạng TRUE đầu tiên (thứ tự bất biến), else 0.

### 3.3 `location` ≤ 25
`signal_engine.location_quality_score(side, t)` (dùng `nearest_zone`, `price_in_zone`,
`distance_to_zone` từ `technical_context`):
- `price`, `atr_value = atr_h4 or atr_d1 or 0.0`.
- **buy**: `base = 15` nếu in support; `10` nếu `dist(support) <= atr*0.5`; `0` nếu in
  resistance; else `3`. **sell** đối xứng dùng resistance làm bonus_zone.
- `bonus_zone` = support (buy) / resistance (sell); bonus:
  - `test_count>=3 → -5`; `test_count>=5 → -3` (cả hai **inert** với zone technical, xem §2)
  - `confluence_count>=3 → +5`
  - `is_round_number → +3` (inert với zone technical)
- trả `clamp(base + bonus, 0, 25)`.

### 3.4 `smc` ≤ 15 — QUYẾT ĐỊNH CHỜ (xem §4)
Raw này KHÔNG derive từ candles đơn thuần; nó là *canonical SMC* = `SmcScoringResult`
mà V4 `project_smc_technical_raw` đòi đúng `scoring_version == "smc-v2"` và
`contract_version == "smc-scoring-canonical-2026-08"`.

## 4. Quyết định producer cho raw `smc` — cần owner chọn

**Sự thật vật lý:** `project_smc_technical_raw` (V4, `technical_signal_scorer.py:641`)
yêu cầu một thể hiện `SmcScoringResult` với `scoring_version == "smc-v2"` (=
`SMC_SCORER_VERSION`) và `contract_version == "smc-scoring-canonical-2026-08"`.
Producer duy nhất của object này là `core/smc_scorer.py:score_smc(smc, technical, ...)`
(trong đó `smc` từ `core/smc_context.py:build_smc_context`) — và **`smc_scorer.py` nằm
trong danh sách xóa V3** của plan Bước 12.

Đây là mâu thuẫn contract: contract V4 đã khóa không cho phép thay đổi `smc-v2`, nên
không thể "bịa" một producer mới sinh ra chuỗi `smc-v2` từ một module "V4" mà không
tạo ra identity mơ hồ. Ba phương án (owner chọn 1):

- **(a) Giữ `smc_context` + `smc_scorer` như producer canonical-SMC retained** (cùng
  tầng `indicators`/`technical_context`), KHÔNG xóa. Document rõ: đây là producer
  contract mà V4 đòi, không phải "đường executable scoring V3". Mâu thuẫn với danh
  sách xóa nhưng tôn trọng contract V4 khóa.
- **(b) Port toàn bộ `score_smc`/`build_smc_context` sang module V4 mới** và tạo
  `SmcScoringResult` kèm `scoring_version="smc-v2"` — nhưng chuỗi version vẫn là chuỗi
  "V3", tạo identity khó giải thích; chi phí port 949+1223 dòng, có nhánh AI-zone-
  auditor/backtest-cache bị cắt.
- **(c) Chỉ port 3 raw đầu (trend/momentum/location) trong Path B**, và sau này (Bước
  12 C2/E) chuyển sang 1 producer SMC chính thống của V4 riêng — nhưng hiện tại V4
  require khóa `smc-v2` nên phương án này để lỗ hổng smc chưa được feed.

**khuyến nghị:** (a) — giữ 2 module SMC low-level, vì đường build SMC không thuộc
"scoring executable" mà là producer contract mà V4 đã khóa; phù hợp nhất với
"không sửa contract V4 đã khóa" và "không bịa".

### QUYẾT ĐỊNH OWNER (2026-08-14): **(a) — giữ `smc_context` + `smc_scorer` như
producer canonical-SMC retained.** `score_smc(...)` là nguồn `smc` raw (≤15) cho
V4; `smc_context`/`smc_scorer` KHÔNG nằm trong danh sách xóa Bước 12 — chúng là
producer contract mà V4 khóa (cùng tầng `indicators`/`technical_context`), không
phải "đường executable scoring V3". Raw `smc` sẽ gắn `SmcScoringResult` từ
`score_smc` qua `project_smc_technical_raw`. *(Lưu ý: điều này thu hẹp danh sách
xóa so với plan gốc — `smc_scorer.py`/`smc_context.py` được rút khỏi deleted set.)*

## 5. Hợp đồng module mới `core/scanner_v4_features.py`

- Version raw: **`scanner-v4-features-v1`**.
- API: `derive_technical_raws(d1, h4, h1, canonical_smc=None) -> TechnicalRawsV4`, với
  `TechnicalRawsV4` mang: `features_version`, `symbol`, `captured_at`, `per_side`:
  `{buy: {trend, momentum, location, smc}, sell: {...}}` (trong đó `smc` =
  `project_smc_technical_raw(canonical_smc, side)` khi `canonical_smc` được cung;
  None nếu không — fail-closed), `derivation` (nguồn trace), `reason_codes`,
  `deterministic_fingerprint`.
- Deterministic: cùng candles → cùng raws (byte-reproducible).
- Fail-closed: thiếu candle → `TechnicalRawDerivationError`; kết quả clamp/None kèm
  reason nếu dữ liệu lệch.
- KHÔNG import `signal_engine`/`analysis_engine`/`analysis_pipeline`… Được import
  `technical_context`, `indicators`, `reason_codes`, và `smc_scorer`/`smc_context`
  (retained canonical-SMC producer, quyết định §4-a) + `smc_scoring_result`.

## 6. Bước 4 parity test (sẽ viết sau khi duyệt)

- (ai) polynomial freeze: cùng fixture candles → `scanner_v4_features` raws ==
  `signal_engine.*_alignment_score` raw (đến khi xóa V3).
- (b) property: range (0-25/0-20/0-25 ≤), deterministic, fail-closed khi thiếu candle.
- (c) fail-closed: d1<60 / h4<60 / h1<30 → error, không số bịa.

## 7. Điều KHÔNG đổi
- Threshold DEFAULT 40/35/5/2:1 (`scanner-threshold-policy-v4`) — không bịa, không đổi.
- Contract version V4 khóa không đổi.
- Order payload là intent; chỉ dispatch sau fresh revalidation.
- Không xóa bất kỳ gì cho tới khi parity test xanh + consumer đã rewrite.

---

*Chờ duyệt toàn bộ spec (§3 + quyết định §4) rồi mới code module Bước 2.*