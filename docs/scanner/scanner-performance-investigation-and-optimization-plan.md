# Điều tra và kế hoạch tối ưu hiệu năng Scanner

**Phạm vi:** Chức năng **Quét thị trường** từ lúc người dùng bấm quét đến khi kết
quả xuất hiện và toàn bộ hậu xử lý hoàn tất

**Màn hình chính:** `ScannerScreen`

**Thành phần chính:** MT5, macro/news, analysis pipeline, candidate engine,
AI Market Brief, Telegram và scanner persistence

**Trạng thái:** Báo cáo điều tra và kế hoạch triển khai để PO duyệt trước khi sửa
code

**Ngày điều tra:** 30/07/2026

---

## 1. Kết luận điều hành

Scanner hiện chậm chủ yếu do I/O mạng và hậu xử lý bị lặp hoặc chạy tuần tự,
không phải do scoring pipeline.

Kết quả phân tích 15 lần quét đủ 28 symbol gần nhất:

| Chỉ số | Kết quả |
|---|---:|
| Tổng thời gian trung bình | **116,8 giây** |
| Lần nhanh nhất | 62,4 giây |
| Lần chậm nhất | 175,3 giây |
| Từ bắt đầu đến hoàn tất analysis/filter | **80,6 giây trung bình** |
| Công việc sau khi đã có kết quả lõi | **33,9 giây trung bình** |

Ba nguyên nhân quan trọng nhất:

1. **Lỗi chọn Telegram candidate:** các row không đủ điều kiện vẫn bị dựng fallback
   payload và gửi Telegram. Một lần scan có 27 `OUT_OF_STRATEGY` nhưng vẫn thử gửi
   27 alert tuần tự.
2. **Macro context bị tính lặp:** cache key khi preload khác cache key khi đọc có AI;
   yield/VIX là dữ liệu toàn cục nhưng bị tải lại theo từng symbol. Một full scan có
   thể phát sinh tới khoảng 168 lượt `yfinance.download()` chỉ cho
   TNX/FVX/VIX.
3. **UI phải chờ hậu xử lý:** AI brief, Telegram, persistence và retention đều chạy
   trước khi worker phát kết quả thành công. Progress lên 94% nhưng có thể đứng thêm
   20–90 giây.

Các yếu tố phụ:

- MT5 tải bốn timeframe tuần tự cho 28 symbol, tương đương khoảng 112
  `copy_rates_from_pos()` calls.
- Full persistence gần nhất ghi 28 file gzip, khoảng 4,65 MB, mất khoảng 7,2 giây.
- Có bằng chứng hai scan ID chồng thời gian; guard hiện tại chỉ bảo vệ một
  `ScannerScreen`, chưa phải khóa scanner toàn ứng dụng/process.
- Fast-reject/scoring optimization không phải ưu tiên: benchmark chính thức chỉ cho
  mức tiết kiệm khoảng 2,33% CPU wall time.

Kỳ vọng hợp lý sau khi sửa đúng thứ tự:

- đưa thời gian có kết quả trên UI từ khoảng 1–3 phút xuống **vài chục giây**;
- loại bỏ hoàn toàn alert Telegram sai;
- giảm hàng chục network calls lặp;
- giữ nguyên scoring, SMC, Entry/SL/TP và safety decision.

Mục tiêu số cụ thể phải được xác nhận lại bằng telemetry P50/P95 sau Phase 0; không
được coi ước lượng trên là cam kết trước benchmark.

---

## 2. Phạm vi điều tra

### 2.1. Đã điều tra

- Luồng tạo `ScannerRequest`.
- `ScannerWorker` và `QThread`.
- `ScannerController.run_market_scan()`.
- Các pha MT5, macro/news, analysis và candidate.
- AI Market Brief.
- Telegram alerts.
- Full/summary persistence.
- Runtime event log và scanner snapshots.
- Fast-path flags và benchmark sẵn có.
- Khả năng scan chạy chồng.

### 2.2. Không thực hiện trong quá trình điều tra

- Không chạy một scan thật mới.
- Không gọi MT5 để benchmark trực tiếp.
- Không gọi AI provider.
- Không gửi Telegram.
- Không sửa code hoặc settings.
- Không thay đổi dữ liệu runtime.

Lý do không chạy scan thật: flow hiện tại có thể lưu snapshot, gửi Telegram hoặc
thực hiện auto-trade tùy cấu hình. Bằng chứng runtime hiện có đã đủ để xác định các
bottleneck lớn.

---

## 3. Nguồn bằng chứng và phương pháp đo

### 3.1. Nguồn runtime

Các nguồn đã đọc ở chế độ read-only:

```text
%APPDATA%/ai-market-analyst/logs/scanner-events.jsonl
%APPDATA%/ai-market-analyst/scanner_snapshots/
%APPDATA%/ai-market-analyst/scanner_analysis/
```

Không đưa bot token, API key, account number hoặc nội dung nhạy cảm vào tài liệu.

### 3.2. Các mốc thời gian

Do code hiện chưa instrument đầy đủ từng phase, báo cáo sử dụng các mốc có sẵn:

| Mốc | Nguồn | Ý nghĩa |
|---|---|---|
| `SCAN_STARTED` | `scanner-events.jsonl` | Bắt đầu `run_market_scan()` |
| Candidate/shadow event cuối | `scanner-events.jsonl` | Analysis và filter đã hoàn tất |
| `output.timestamp` | Scanner snapshot | `build_scanner_output()` đã chạy, AI brief đã xong |
| `SCAN_COMPLETED` | `scanner-events.jsonl` | Telegram/persistence và toàn flow đã xong |
| Analysis file timestamps | `scanner_analysis/<scan_id>` | Khoảng thời gian ghi full persistence |

Các cột trong bảng runtime:

- `ToFilterSec`: từ `SCAN_STARTED` đến candidate/shadow event cuối.
- `BriefSec`: từ candidate/shadow event cuối đến `output.timestamp`.
- `PostSec`: từ `output.timestamp` đến `SCAN_COMPLETED`.

`BriefSec` là xấp xỉ cho AI brief và thao tác build output nhỏ. `PostSec` gồm
auto-trade/metrics/Telegram/persistence/retention. Chưa thể tách chính xác tất cả
subphase nếu không thêm instrumentation.

---

## 4. Số liệu runtime chi tiết

### 4.1. Các lần quét 28 symbol

`Scan` trong bảng là phần giờ-phút-giây của scan ID để dễ đọc.

| Scan | Symbols | Total (s) | To filter (s) | Brief (s) | Post (s) | Telegram attempts | Errors | Persistence |
|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 150423 | 28 | 130,8 | 65,4 | 1,6 | 63,8 | 27 | 0 | summary |
| 145749 | 28 | 175,3 | 85,4 | 1,4 | 88,5 | 27 | 1 | full |
| 120003 | 28 | 133,3 | 81,8 | 2,3 | 49,2 | 28 | 0 | summary |
| 114246 | 28 | 62,4 | 36,2 | 1,4 | 24,8 | 28 | 0 | summary |
| 110004 | 28 | 131,9 | 98,5 | 1,3 | 32,0 | 28 | 0 | full |
| 105913 | 28 | 137,6 | 112,4 | 1,4 | 23,8 | 28 | 0 | summary |
| 104504 | 28 | 126,8 | 101,3 | 1,3 | 24,1 | 28 | 0 | summary |
| 103004 | 28 | 88,2 | 63,1 | 1,8 | 23,3 | 27 | 0 | summary |
| 101503 | 28 | 96,6 | 60,6 | 12,0 | 24,1 | 28 | 0 | summary |
| 100003 | 28 | 103,7 | 71,2 | 1,2 | 31,4 | 28 | 0 | full |
| 094504 | 28 | 128,2 | 103,9 | 1,6 | 22,6 | 27 | 0 | summary |
| 093004 | 28 | 120,0 | 96,6 | 2,0 | 21,4 | 26 | 0 | summary |
| 091504 | 28 | 89,7 | 63,8 | 1,5 | 24,4 | 28 | 0 | summary |
| 090003 | 28 | 127,6 | 101,2 | 2,9 | 23,6 | 28 | 0 | summary |
| 084902 | 28 | 100,5 | 67,7 | 1,9 | 30,9 | 27 | 0 | full |

Tổng hợp:

```text
n = 15
total average = 116,8 giây
total min = 62,4 giây
total max = 175,3 giây
to-filter average = 80,6 giây
post average = 33,9 giây
```

### 4.2. Các lần quét một symbol

| Scan | Symbols | Total (s) | To filter (s) | Brief (s) | Post (s) | Telegram attempts | Persistence |
|---:|---:|---:|---:|---:|---:|---:|---|
| 113816 | 1 | 12,5 | 8,9 | 1,3 | 2,2 | 1 | summary |
| 112928 | 1 | 17,8 | 13,5 | 1,1 | 3,2 | 1 | full |
| 111633 | 1 | 12,3 | 8,3 | 1,3 | 2,8 | 1 | full |

Việc một symbol vẫn mất khoảng 12–18 giây cho thấy chi phí network/macro/AI và
Telegram có phần cố định đáng kể, không chỉ tăng theo số lượng symbol.

### 4.3. Timeline của lần full scan chậm nhất gần nhất

Scan ID:

```text
20260730T145749.190068Z-9e8994577499
```

Timeline giờ địa phương:

| Mốc | Thời gian | Khoảng từ mốc trước |
|---|---|---:|
| Scan bắt đầu | 21:57:49 | — |
| Candidate/shadow hoàn tất | 21:59:14 | ~85,4 giây |
| Output core được build | 21:59:16 | ~1,4 giây |
| File analysis đầu tiên được ghi | 22:00:37 | ~81 giây |
| File analysis cuối/snapshot hoàn tất | 22:00:44 | ~7,2 giây |

Telegram của scan này:

```text
attempted = 27
sent = 26
errors = 1 SSL handshake timeout
summary_sent = 1
```

Kết quả scanner:

```text
OUT_OF_STRATEGY = 27
DATA_UNAVAILABLE = 1
READY_NOW = 0
```

Đây là bằng chứng trực tiếp rằng Telegram candidate selection đang sai.

### 4.4. Analysis CPU thực tế

Từ 28 full analysis documents của cùng scan:

```text
count = 28
sum analysis_latency_ms = 5.667,31 ms
average = 202,404 ms/symbol
max = 518,611 ms
```

Top latency:

| Symbol | Analysis latency |
|---|---:|
| EUR/JPY | 518,611 ms |
| GBP/NZD | 430,499 ms |
| AUD/CAD | 312,943 ms |
| AUD/NZD | 292,023 ms |
| GBP/CHF | 261,734 ms |

Các symbol được phân tích bằng tối đa sáu CPU workers, nên tổng 5,67 giây không
phải wall time cộng dồn. Phần analysis wall time thực tế nhỏ hơn nhiều so với
80–112 giây của pha trước filter.

### 4.5. Full persistence

Lần full scan trên ghi:

```text
28 gzip analysis files
total compressed size = 4.648.385 bytes
write duration ≈ 7,2 giây
```

Đây không phải bottleneck lớn nhất, nhưng hiện vẫn chặn thời điểm worker phát
`succeeded`.

---

## 5. Luồng chạy hiện tại

```text
ScannerScreen._run_scan()
  └── ScannerController.create_scan_worker()
      └── ScannerWorker trong QThread
          └── ScannerController.run_market_scan()
              ├── tạo scan context/rollout
              ├── ensure MT5 ready
              ├── account + portfolio snapshot
              ├── song song:
              │   ├── fetch macro correlation
              │   └── preload macro/news cho toàn bộ symbol
              ├── lấy danh sách MT5 symbols
              ├── tuần tự từng symbol:
              │   ├── resolve broker symbol
              │   ├── D1/H4/H1/M15 OHLCV
              │   ├── symbol data quality
              │   ├── news/macro flags
              │   └── quote-to-USD
              ├── phân tích CPU song song tối đa 6 workers
              ├── Strategy Router + execution filters
              ├── observability + shadow comparison
              ├── AI Market Brief đồng bộ
              ├── build output
              ├── auto-trade nếu bật
              ├── rollout metrics
              ├── Telegram alerts đồng bộ
              ├── persistence + retention
              └── return output
          └── ScannerWorker.succeeded
              └── ScannerScreen hiển thị bảng
```

Vấn đề trải nghiệm chính: bảng chỉ được hiển thị ở cuối, dù kết quả phân tích lõi
đã tồn tại từ trước Telegram/persistence.

---

## 6. Nguyên nhân gốc số 1 — Telegram candidate fallback sai

### 6.1. Hành vi hiện tại

`_apply_scanner_filters()` gán:

```text
row["candidate_order_payload"] = candidate payload hoặc None
```

`None` là trạng thái hợp lệ của schema mới: row không phải candidate có thể thực
thi.

Nhưng `_get_alert_order_candidates()` đang xử lý:

```text
stored = row.get("candidate_order_payload")
if stored không phải dict:
    dựng fallback từ best scenario
```

Do đó:

- key tồn tại và có giá trị `None`;
- code vẫn đi vào compatibility fallback;
- một scenario chỉ dùng để hiển thị bị nâng thành alert payload;
- row `OUT_OF_STRATEGY` vẫn được gửi Telegram.

### 6.2. Tác động hiệu năng

`TelegramAlertService.send_order_alerts()` gửi tuần tự:

```text
for candidate:
    for chat_id:
        urlopen(..., timeout=10)
```

Một scan có 27–28 candidates giả tạo ra 27–28 HTTP calls chi tiết, sau đó thêm một
summary call.

Nếu một request timeout, scanner chờ tối đa 10 giây cho request đó. Các request
khác vẫn tiếp tục tuần tự.

### 6.3. Tác động nghiệp vụ

Đây không chỉ là lỗi hiệu năng:

- người dùng nhận quá nhiều alert;
- alert có thể mô tả setup không đủ điều kiện;
- tên method và comment nói dùng canonical candidates nhưng behavior thực tế không
  tuân theo;
- alert volume che lấp tín hiệu thực sự.

### 6.4. Contract sửa bắt buộc

Quy tắc mới:

1. Nếu key `candidate_order_payload` tồn tại:
   - dict hợp lệ → dùng;
   - `None` hoặc giá trị khác dict → bỏ row;
   - tuyệt đối không compatibility fallback.
2. Chỉ compatibility fallback nếu key hoàn toàn không tồn tại, nghĩa là snapshot
   legacy thật sự.
3. Structural reject luôn bị bỏ.
4. Không tự suy luận candidate từ `best_scenario` cho row schema mới.
5. Nếu PO muốn gửi WATCH/WAIT alerts, phải có contract riêng
   `watch_alert_payload`; không dùng candidate order fallback để đạt mục đích đó.

Pseudocode:

```text
if structural_reject:
    continue

if "candidate_order_payload" in row:
    payload = row["candidate_order_payload"]
    if not is_dict(payload):
        continue
else:
    payload = build_legacy_compatibility_payload(row)

if payload is valid:
    candidates.append(payload)
```

### 6.5. Delivery policy đề xuất

Milestone đầu:

- giữ summary alert;
- chỉ gửi detail alert cho canonical candidate payload thật;
- với 0 candidate: một summary message;
- với 1–3 candidate: detail messages + summary;
- không gửi 28 detail messages.

Milestone sau:

- hỗ trợ một batched detail message/recipient;
- hoặc đưa Telegram sang aftercare worker.

---

## 7. Nguyên nhân gốc số 2 — Macro cache miss và global fetch lặp

### 7.1. Cache key không nhất quán

`latest_macro_context()` tạo key:

```text
symbol + include_latest_statements
```

Nếu có AI service, thêm:

```text
"_ai"
```

Ví dụ:

```text
EUR/USD_True_ai
```

Trong khi đó `preload_macro_contexts()` gọi hàm với AI service nhưng lưu kết quả
dưới:

```text
EUR/USD_True
```

Khi phase MT5 gọi:

```text
data_quality_flags(symbol, ai_service=ai_service)
```

`latest_macro_context()` tìm `EUR/USD_True_ai`, không thấy và tính lại.

Ngoài ra, `latest_macro_context()` chỉ đọc cache; kết quả vừa tính không được lưu
vào đúng cache key trước khi return.

### 7.2. Yield spread bị tải cho mọi cặp

`_macro_tier1()` luôn gọi `_fetch_yield_spread()`:

```text
download ^TNX
download ^FVX
```

Sau khi đã tải xong mới kiểm tra cặp có chứa USD hay không để áp dụng adjustment.

Hệ quả:

- cặp EUR/GBP vẫn tải TNX/FVX;
- XAU/USD và EUR/USD tải cùng dữ liệu lại từ đầu;
- dữ liệu toàn cục không được reuse.

### 7.3. VIX bị tải cho mọi cặp

`_macro_tier3()` luôn gọi:

```text
download ^VIX
```

VIX là market-global input nhưng bị fetch theo symbol.

### 7.4. Số lượt gọi tiềm năng

Một lượt tính macro đủ 28 symbol:

```text
28 × (^TNX + ^FVX + ^VIX) = 84 downloads
```

Vì preload cache miss ở phase symbol fetch, macro có thể chạy hai lần:

```text
84 × 2 = 168 downloads
```

Đây là con số tiềm năng theo code path. Số network request vật lý có thể thấp hơn
nếu thư viện/provider tự cache, nhưng ứng dụng không được dựa vào cache ẩn của thư
viện.

### 7.5. AI stance

Macro tier có thể gọi AI để đánh giá stance. `_stance_cache` giảm một phần số call
theo currency/headline, nhưng orchestration vẫn đi theo từng pair.

Hướng đúng:

- xác định tập currency duy nhất;
- tính stance một lần/currency/context;
- reuse cho mọi pair chứa currency đó.

### 7.6. Contract cache mới

Thêm helper duy nhất:

```text
macro_context_cache_key(
    symbol,
    include_latest_statements,
    ai_fingerprint,
)
```

`ai_fingerprint` chỉ chứa:

- provider;
- model;
- chế độ AI enabled/disabled.

Không chứa API key.

Mọi nơi đọc/ghi cache phải dùng helper này.

### 7.7. Global macro snapshot

Tạo một snapshot toàn cục cho mỗi TTL:

```text
MacroGlobalSnapshot
  fetched_at_utc
  expires_at_utc
  tnx
  fvx
  yield_spread_10y_5y
  yield_steepening
  vix
  global_headlines
  official_statements
  calendar_payload
  source_status
  stale_fields
```

Quy tắc:

- TTL mặc định 5 phút để khớp preload cache hiện tại.
- Một scan chỉ dùng một global snapshot nhất quán.
- Nếu refresh lỗi nhưng có snapshot cũ:
  - dùng stale-if-error trong giới hạn được định nghĩa;
  - gắn freshness/provenance;
  - không âm thầm coi dữ liệu cũ là mới.
- Nếu không có snapshot nào:
  - giữ fail-safe/fallback hiện có;
  - không crash toàn scan chỉ vì VIX/Yield phụ trợ không có.

### 7.8. Context per symbol

Sau khi có global snapshot:

1. Extract currencies của toàn bộ symbols.
2. Compute currency stance một lần/currency.
3. Compute pair-relative tier scores bằng dữ liệu đã có trong RAM.
4. Store đúng cache key.
5. `data_quality_flags()` chỉ đọc context, không gọi network lại.

---

## 8. Nguyên nhân số 3 — MT5 fetch tuần tự và full-history mỗi scan

### 8.1. Số lượng dữ liệu

Mỗi symbol:

```text
D1  = 500 bars
H4  = 500 bars
H1  = 500 bars
M15 = 100 bars
```

Với 28 symbol:

```text
1.600 bars/symbol
44.800 bars/scan
112 copy_rates_from_pos calls
```

Chưa tính:

- `symbol_info`;
- quote conversion;
- portfolio/account reads;
- symbol resolution.

### 8.2. Song song hiện tại không tạo parallel MT5 SDK

`load_primary_timeframes()` tạo một `ThreadPoolExecutor` cho timeframe, nhưng
`load_ohlcv()` được bảo vệ bởi cùng `RLock`.

Kết quả:

- SDK calls vẫn tuần tự;
- có thêm overhead futures/thread scheduling;
- behavior đúng về safety nhưng không nhanh hơn.

Không được bỏ lock để ép SDK chạy song song mà chưa có characterization test.

### 8.3. Rolling candle cache

Hướng tối ưu đề xuất:

#### Cold load

Lần đầu hoặc cache invalid:

- tải đủ 500/500/500/100 bars;
- validate timestamps;
- lưu memory cache.

#### Warm update

Mỗi scan tiếp theo:

- tải 2–5 bars cuối mỗi timeframe;
- merge theo timestamp;
- replace bar đang hình thành;
- append bar mới;
- trim về max history length.

#### Cache key

```text
server
account identity/fingerprint
broker_symbol
timeframe
```

Không dùng display symbol đơn thuần vì suffix/prefix broker có thể khác.

#### Full reload conditions

- server/account đổi;
- broker symbol đổi;
- timeframe config đổi;
- cache thiếu;
- timestamp đi lùi;
- phát hiện gap lớn hơn expected;
- MT5 trả lịch sử không liên tục;
- application restart, vì milestone đầu dùng memory cache;
- explicit refresh/debug command nếu có.

### 8.4. Dữ liệu forming bar

Không chỉ nến mới đóng mới quan trọng:

- D1/H4/H1 hiện có bar đang hình thành;
- giá close/high/low của bar đó có thể đổi giữa hai scan M15.

Do đó warm update vẫn phải refresh tail của cả D1/H4/H1/M15, không được chỉ tải
M15.

### 8.5. Không ưu tiên giảm bar count

Giảm 500 xuống 200/300 có thể:

- đổi EMA warm-up;
- đổi swing/SMC detection;
- đổi score/scenario;
- phá parity với backtest.

Chỉ làm nếu có benchmark chứng minh MT5 payload size là bottleneck còn lại và có
parity/backtest riêng.

---

## 9. Scoring/Fast path không phải ưu tiên

Pipeline CPU đã được song song hóa tối đa sáu workers.

Benchmark fast-reject chính thức:

```text
full baseline p50 total = 2,8979 ms/fixture
tier 1 p50 total = 2,8737 ms/fixture
paired scan wall p50 full = 23,1832 ms
paired scan wall p50 tier 1 = 22,9896 ms
estimated saving = 2,33%
decision = STOP_AFTER_TIER1
```

Runtime feature flags trong snapshot:

```text
scanner_fast_tier1 = false
scanner_fast_tier2 = false
```

Bật fast flag không giải quyết được scan 60–175 giây. Không được thay đổi scoring
logic chỉ để theo đuổi một tối ưu nhỏ trong khi I/O đang chiếm phần lớn.

---

## 10. AI Market Brief

### 10.1. Số liệu

Phần lớn scan:

```text
~1–3 giây
```

Có một outlier:

```text
12 giây
```

AI brief không phải bottleneck lớn nhất trung bình, nhưng là external I/O không cần
thiết để hiển thị bảng kết quả.

### 10.2. Hướng xử lý

- Không xóa tính năng.
- Tách khỏi critical path UI.
- Sau core result:
  - UI hiển thị bảng;
  - market brief hiển thị “Đang tạo…”;
  - khi AI hoàn tất, cập nhật section tương ứng.
- Có timeout và lỗi độc lập.
- Lỗi brief không được biến scan thành failed.

---

## 11. Persistence và retention

### 11.1. Hiện trạng

Manual scan dùng `persistence_mode="full"`:

- ghi một analysis document gzip/symbol;
- ghi summary snapshot;
- chạy retention prune.

Auto scan dùng summary mode, nhưng vẫn phải chờ Telegram.

### 11.2. Hướng tối ưu

Milestone an toàn:

- giữ schema và file layout;
- đưa full persistence ra khỏi thời điểm core result được hiển thị;
- summary metadata nhỏ có thể ghi trước nếu yêu cầu durability;
- full analysis gzip chạy background.

Không đổi schema hoặc gộp toàn bộ thành một archive ở phase đầu.

### 11.3. Invariant

- Core output sau khi phát cho UI phải được coi là immutable.
- Aftercare đọc snapshot bất biến, không mutate object UI đang dùng.
- `snapshot_path`, Telegram status và brief status được trả dưới dạng aftercare
  delta riêng.
- App shutdown phải có bounded flush hoặc ghi trạng thái incomplete rõ ràng.

---

## 12. Scan overlap

### 12.1. Bằng chứng

Runtime có trường hợp:

```text
scan A bắt đầu 10:59:13 UTC
scan B bắt đầu 11:00:04 UTC
scan A kết thúc 11:01:30 UTC
scan B kết thúc 11:02:16 UTC
```

### 12.2. Code hiện tại

Một `ScannerScreen` có guard:

```text
if self.scan_thread is not None:
    return
```

Do đó overlap có thể đến từ:

- hai app processes;
- hai main windows/controllers;
- test/tool khác dùng cùng runtime và terminal;
- lifecycle cũ không cùng screen instance.

### 12.3. Hướng xử lý

Phase đầu:

- thêm controller-level non-blocking scan lock;
- log rõ active scan ID nếu từ chối scan mới.

Phase sau nếu cần:

- single-instance application guard;
- hoặc OS/process-wide mutex.

Không dùng lock file không có stale-owner recovery.

---

## 13. Kiến trúc mục tiêu

```text
┌────────────────────────────────────────────────────────────┐
│ ScannerScreen                                              │
│  - tạo request                                             │
│  - hiển thị progress                                       │
│  - nhận core result sớm                                    │
│  - nhận aftercare delta sau                                │
└──────────────────────────┬─────────────────────────────────┘
                           │
┌──────────────────────────▼─────────────────────────────────┐
│ ScannerWorker / ScannerController                          │
│                                                            │
│  Phase Core                                                │
│  ├── readiness/account                                     │
│  ├── cached global macro snapshot                          │
│  ├── MT5 history warm update                               │
│  ├── CPU analysis                                          │
│  ├── candidate/filter/ranking                              │
│  └── emit core_result_ready                                │
└──────────────────────────┬─────────────────────────────────┘
                           │ immutable result
┌──────────────────────────▼─────────────────────────────────┐
│ Scanner Aftercare                                         │
│  ├── AI Market Brief                                      │
│  ├── canonical Telegram alerts                            │
│  ├── persistence                                          │
│  └── retention/metrics                                    │
└──────────────────────────┬─────────────────────────────────┘
                           │ delta/status
┌──────────────────────────▼─────────────────────────────────┐
│ ScannerScreen                                              │
│  - cập nhật AI/Telegram/save status                        │
│  - chỉ áp dụng nếu scan_id còn phù hợp                     │
└────────────────────────────────────────────────────────────┘
```

---

## 14. Performance telemetry contract

### 14.1. Vì sao phải làm trước

Hiện chỉ có thể suy ra các phase lớn. Không có số chính xác cho:

- macro preload;
- MT5 total/per symbol;
- Telegram;
- persistence;
- retention.

Mọi tối ưu tiếp theo phải được đo trước/sau trên cùng workload.

### 14.2. Schema đề xuất

```text
performance:
  schema_version
  scan_id
  symbol_count
  started_at
  completed_at
  core_ready_at
  total_ms
  core_ready_ms
  aftercare_ms

  phases:
    settings_ms
    readiness_ms
    account_portfolio_ms
    correlation_ms
    macro_global_fetch_ms
    macro_pair_build_ms
    available_symbols_ms
    mt5_fetch_ms
    analysis_wall_ms
    candidate_filter_ms
    observability_ms
    market_brief_ms
    telegram_ms
    persistence_ms
    retention_ms

  counters:
    mt5_copy_rates_calls
    mt5_full_history_calls
    mt5_tail_calls
    macro_context_cache_hits
    macro_context_cache_misses
    macro_global_fetches
    yfinance_download_calls
    ai_stance_calls
    telegram_candidates
    telegram_requests
    telegram_errors
    analysis_documents_written

  symbols:
    <symbol>:
      fetch_ms
      macro_lookup_ms
      mt5_ms
      analysis_ms
      pipeline_route
```

### 14.3. Implementation guideline

- Dùng `perf_counter()` cho durations.
- UTC timestamp chỉ dùng cho observability.
- Không log toàn bộ candle payload.
- Không log secrets.
- Per-symbol telemetry có thể nằm trong full analysis; summary chỉ giữ aggregate.
- Emit một event `SCAN_PERFORMANCE_SUMMARY`.
- Nếu telemetry lỗi, scan vẫn chạy; instrumentation không có quyền thay đổi kết
  quả.

---

## 15. Kế hoạch triển khai theo phase

## Phase 0 — Instrumentation và baseline chuẩn

### Mục tiêu

Đo chính xác từng phase mà không thay behavior.

### File dự kiến

- `core/scanner_performance.py` — mới.
- `controllers/scanner_controller.py`.
- `core/scanner_observability.py`.
- `services/scanner_persistence_service.py` nếu cần persist summary metric.
- `tests/test_scanner_performance.py` — mới.

### Công việc

1. Tạo `ScanPerformanceTracker`.
2. Hỗ trợ:
   - `start_phase(name)`;
   - `end_phase(name)`;
   - context manager nếu project style phù hợp;
   - counter increment;
   - per-symbol timing;
   - finalize idempotent.
3. Bọc đúng ranh giới phase trong `run_market_scan()`.
4. Bọc `_fetch_one_symbol_mt5()` theo symbol.
5. Bọc `_send_telegram_alerts()`.
6. Tách timing persistence và retention thay vì gộp.
7. Đưa summary vào output/snapshot.
8. Emit event tổng hợp.

### Test bắt buộc

- Nested/duplicate phase không làm crash.
- Exception vẫn đóng/finalize phase.
- Counter đúng.
- Không có negative duration.
- Không chứa secret.
- Telemetry failure không thay scan output.

### Acceptance

- Một scan test/mocked có đủ phase.
- Tổng phase không vượt total ngoài tolerance.
- Có thể trả lời chính xác macro/MT5/Telegram/persistence mất bao lâu.

---

## Phase 1A — Sửa correctness của Telegram candidates

### Mục tiêu

Loại bỏ alert sai và giảm ngay 20–90 giây trong các scan hiện tại.

### File dự kiến

- `controllers/scanner_controller.py`.
- `tests/test_scanner_telegram_candidates.py` — mới hoặc mở rộng test hiện có.

### Công việc

1. Phân biệt key absent và key present-but-None.
2. Chỉ fallback cho true legacy row.
3. Structural reject luôn skip.
4. Validate canonical payload:
   - symbol/broker symbol;
   - side;
   - entry zone;
   - SL/TP;
   - candidate status/provenance.
5. Thêm counter:
   - canonical candidates;
   - legacy fallback candidates;
   - skipped non-candidates.

### Test matrix

| Case | Kỳ vọng |
|---|---|
| Key tồn tại, value dict | Dùng payload |
| Key tồn tại, value `None` | Skip |
| Key tồn tại, value sai type | Skip |
| Key không tồn tại, valid legacy scenario | Compatibility fallback |
| Structural reject | Skip |
| OUT_OF_STRATEGY schema mới | Skip |
| DATA_UNAVAILABLE schema mới | Skip |
| Canonical candidate | Một payload |

### Acceptance

Với fixture tương đương runtime:

```text
27 OUT_OF_STRATEGY + 1 DATA_UNAVAILABLE
```

Kết quả:

```text
telegram detail candidates = 0
summary candidates = 0
```

---

## Phase 1B — Giảm số Telegram HTTP calls

### Mục tiêu

Không để nhiều request tuần tự kéo dài scan.

### File dự kiến

- `services/telegram_alert_service.py`.
- `controllers/scanner_controller.py`.
- `tests/test_telegram_alert_service.py`.

### Milestone 1

- Giữ detail messages chỉ cho canonical candidates.
- Giữ một summary message.
- Thêm timing/request counters.
- Không retry vô hạn.

### Milestone 2

Chọn một:

1. Batch nhiều candidates thành một message/recipient, có giới hạn độ dài; hoặc
2. Gửi bounded concurrent với giới hạn workers nhỏ.

Khuyến nghị batch vì:

- ít HTTP calls;
- ít nguy cơ rate limit;
- dễ theo dõi một scan;
- giảm noise.

### Lỗi mạng

- Một recipient lỗi không chặn recipient khác.
- Không biến core scan thành failed.
- Timeout được ghi vào aftercare result.
- Không gửi lại toàn bộ batch tự động nếu không có idempotency strategy.

### Acceptance

- Scan không có candidate: tối đa một request/recipient.
- Scan có N candidates: không còn N+1 request bắt buộc nếu batch được bật.
- Không alert cho row bị loại.

---

## Phase 2A — Sửa macro cache contract

### Mục tiêu

Một symbol/context chỉ được build một lần/TTL và được đọc đúng ở phase MT5.

### File dự kiến

- `services/news_service.py`.
- `tests/test_news_service_macro_cache.py` — mới.

### Công việc

1. Thêm `_macro_context_cache_key()`.
2. Dùng cùng helper trong:
   - `latest_macro_context()`;
   - `preload_macro_contexts()`;
   - `data_quality_flags()`.
3. Ghi cache trước khi return.
4. Cache entry chứa:
   - value;
   - fetched_at;
   - expiry;
   - AI fingerprint;
   - source freshness.
5. Không cache exception như success.
6. Trả copy hoặc immutable view nếu consumer có thể mutate.

### Test bắt buộc

- AI enabled key khớp preload/read.
- AI disabled key độc lập.
- Provider/model đổi → miss hợp lệ.
- Within TTL → hit.
- Expired → recompute.
- Error → không poison cache.
- Consumer không thể làm hỏng cache entry cho lần sau.

### Acceptance

Sau preload, 28 lượt `data_quality_flags()` phải có 28 cache hits và 0 macro
network rebuilds.

---

## Phase 2B — Globalize Yield/VIX/News inputs

### Mục tiêu

TNX/FVX/VIX chỉ được tải một lần/global TTL, không theo symbol.

### File dự kiến

- `services/news_service.py`.
- Có thể thêm `services/macro_market_snapshot.py`.
- `tests/test_macro_global_snapshot.py` — mới.

### Công việc

1. Tạo `MacroGlobalSnapshot`.
2. Fetch song song có giới hạn:
   - TNX;
   - FVX;
   - VIX;
   - RSS/statements nếu chưa có cache.
3. Compute yield spread một lần.
4. Truyền snapshot vào pair tier calculations.
5. `_macro_tier1()` không tự gọi yfinance.
6. `_macro_tier3()` không tự gọi yfinance.
7. Thêm stale-if-error/provenance.
8. Tính currency stance theo unique currencies.

### Test call-count

Với 28 symbols:

```text
^TNX download count <= 1/TTL
^FVX download count <= 1/TTL
^VIX download count <= 1/TTL
macro context build count <= 28/TTL
second consumer pass network count = 0
```

### Parity test

Với frozen external responses:

- tier1 scores không đổi;
- tier2 scores không đổi;
- tier3 scores không đổi;
- macro alignment/reasons không đổi;
- only provenance/cache metadata được thêm.

### Acceptance

Không còn yfinance call bên trong loop symbol.

---

## Phase 3 — Hiển thị core result trước aftercare

### Mục tiêu

Người dùng thấy bảng ngay khi analysis/filter xong.

### File dự kiến

- `workers/scanner_worker.py`.
- `controllers/scanner_controller.py`.
- `ui/screens/scanner_screen.py`.
- Có thể thêm `workers/scanner_aftercare_worker.py`.
- `tests/test_scanner_worker.py`.
- `tests/test_scanner_aftercare.py` — mới.

### Thiết kế milestone an toàn

Refactor:

```text
run_market_scan_core(request) -> core_output
run_market_scan_aftercare(core_output) -> aftercare_delta
```

Worker signals:

```text
core_succeeded(dict)
aftercare_progress(int, str)
aftercare_succeeded(dict)
failed(str)
finished()
```

Flow:

1. Core hoàn tất.
2. Emit `core_succeeded`.
3. UI hiển thị table/detail ngay.
4. Worker tiếp tục aftercare.
5. UI hiển thị “Đang gửi/lưu…”.
6. Aftercare trả delta.
7. UI merge delta nếu `scan_id` còn đúng.

Milestone này vẫn giữ worker thread sống đến aftercare xong, nên không cho scan mới
chồng. Tuy nhiên time-to-visible-result giảm ngay mà chưa cần queue phức tạp.

### Milestone mở rộng

Sau khi milestone an toàn ổn định:

- chuyển aftercare sang dedicated single-worker queue;
- scanner core thread có thể kết thúc sớm;
- queue có backpressure;
- không cho nhiều Telegram/persistence jobs chồng vô hạn.

### Immutable result invariant

Sau `core_succeeded`:

- core output không được mutate bởi worker;
- aftercare trả delta riêng;
- UI merge vào `self.scan_result` trên GUI thread;
- aftercare không giữ reference đến mutable table-model copies.

### UI behavior

Trạng thái gợi ý:

```text
Kết quả quét: Sẵn sàng
AI brief: Đang tạo...
Telegram: Đang gửi...
Snapshot: Đang lưu...
```

Không mở modal khi aftercare lỗi.

### Test bắt buộc

- Core signal phát trước Telegram.
- Core signal phát trước persistence.
- Slow Telegram không trì hoãn table update.
- Aftercare lỗi không xóa rows.
- Delta scan ID cũ không ghi đè scan mới.
- `finished` luôn phát.
- Auto-scan không overlap trong milestone an toàn.

---

## Phase 4 — Rolling MT5 candle cache

### Mục tiêu

Không tải lại 44.800 bars ở mọi scan.

### File dự kiến

- `services/mt5_service.py`.
- Có thể thêm `services/candle_history_cache.py`.
- `controllers/scanner_controller.py`.
- `tests/test_mt5_history_cache.py` — mới.
- `tests/test_mt5_operation_serialization.py`.

### Data contract

```text
get_primary_timeframes_cached(
    broker_symbol,
    bars_by_timeframe,
    cache_identity,
) -> {
    candles_by_timeframe,
    cache_status,
    fetch_metrics,
}
```

`cache_status`:

```text
cold_full
warm_tail
full_reload_gap
full_reload_identity_change
full_reload_validation_failure
```

### Merge algorithm

Cho mỗi timeframe:

1. Sort cached candles theo UTC timestamp.
2. Tải tail 3 bars.
3. Validate strictly increasing timestamps.
4. Với timestamp đã có: replace.
5. Với timestamp mới hơn: append.
6. Với timestamp cũ bất thường: invalidate.
7. Detect expected interval gap.
8. Trim đúng configured max count.
9. Trả list copy/immutable snapshot cho pipeline.

### Thread/lock

- Mọi SDK call vẫn qua `_serialized_mt5_operation`.
- Không tạo MT5 service mới/symbol.
- Không bỏ lock.
- Có thể bỏ internal `ThreadPoolExecutor` cho four timeframes nếu benchmark xác
  nhận nó chỉ tạo overhead.

### Test bắt buộc

- Cold load.
- Same forming bar replacement.
- New bar append.
- Multiple new bars.
- Gap fallback.
- Server/account change.
- Broker suffix change.
- Cache corruption.
- MT5 error giữ cache nhưng không báo fresh sai.
- Serialization max active SDK calls vẫn bằng 1.
- Output candles parity với full reload.

### Acceptance

Warm scan:

- không có full 500-bar call nếu cache hợp lệ;
- chỉ tail calls;
- analysis output parity với full reload trên frozen MT5 responses.

---

## Phase 5 — Persistence/retention aftercare và scan lock

### Mục tiêu

Loại full gzip write khỏi critical UI path và ngăn overlap.

### File dự kiến

- `services/scanner_persistence_service.py`.
- `services/runtime_retention_service.py`.
- `controllers/scanner_controller.py`.
- `workers/scanner_aftercare_worker.py` nếu Phase 3 đã tạo.
- `tests/test_scanner_persistence_aftercare.py`.
- `tests/test_scanner_scan_lock.py`.

### Công việc persistence

1. Giữ summary/full mode.
2. Ghi compact summary sớm nếu durability yêu cầu.
3. Full analysis files chạy aftercare.
4. Retention prune chạy sau write.
5. Delta trả:
   - snapshot path;
   - manifest;
   - write count;
   - duration;
   - errors.
6. Không mutate core output.

### Công việc locking

1. Thêm controller-level non-blocking lock.
2. Lock owner có scan ID.
3. Scan mới khi bận trả lỗi “Scanner đang chạy” có active ID.
4. `finally` luôn release.
5. Không dùng destructive recovery.
6. Nếu cần cross-process, thiết kế riêng với OS mutex.

### Acceptance

- Không có hai `run_market_scan_core()` cùng controller.
- Full persistence không trì hoãn core result.
- App shutdown không corrupt gzip/snapshot.

---

## 16. File/module dự kiến bị tác động

| File/module | Vai trò |
|---|---|
| `controllers/scanner_controller.py` | Phase timing, candidate fix, core/aftercare split, scan lock |
| `workers/scanner_worker.py` | Core/aftercare signals |
| `workers/scanner_aftercare_worker.py` | Mới nếu tách queue/thread |
| `ui/screens/scanner_screen.py` | Hiển thị core sớm và aftercare status |
| `services/telegram_alert_service.py` | Batch/request policy và timing |
| `services/news_service.py` | Cache key, global snapshot, unique currency stance |
| `services/macro_market_snapshot.py` | Mới nếu tách global macro state |
| `services/mt5_service.py` | Tail loading/cache integration |
| `services/candle_history_cache.py` | Mới nếu không đặt cache trong MT5Service |
| `services/scanner_persistence_service.py` | Async/aftercare write contract |
| `services/runtime_retention_service.py` | Timing và aftercare |
| `core/scanner_performance.py` | Mới: telemetry tracker |
| `core/scanner_observability.py` | Performance summary event |
| `tests/` | Unit, integration, parity, performance characterization |

Không dự kiến thay:

- scoring formula;
- SMC logic;
- Entry/SL/TP calculation;
- candidate status semantics;
- backtest logic;
- QSS/font/layout;
- ScannerDetail chart trong task này;
- order execution safety.

---

## 17. Test strategy tổng thể

### 17.1. Unit tests

| Nhóm | Nội dung |
|---|---|
| Telegram candidates | Key absent/present/None, legacy fallback, structural reject |
| Telegram delivery | Batch, recipient errors, timeout, zero candidates |
| Macro key | AI fingerprint, TTL, error, mutation safety |
| Global macro | TNX/FVX/VIX call count, stale fallback |
| MT5 cache | Cold/warm/merge/gap/identity |
| Performance tracker | Phase/counter/finalize/exception |
| Scan lock | Concurrent calls, release on error |

### 17.2. Integration tests

- Mock full scan 28 symbols.
- Assert macro network call count.
- Assert MT5 call count cold/warm.
- Assert analysis parity.
- Assert candidate and ranking parity.
- Assert UI core signal trước aftercare.
- Assert Telegram không nhận rejected rows.
- Assert snapshot schema giữ tương thích.

### 17.3. Characterization benchmark

Workload cố định:

```text
1 symbol cold
1 symbol warm
28 symbols cold
28 symbols warm
Telegram disabled
Telegram enabled, 0 candidates
Telegram enabled, 3 candidates
summary persistence
full persistence
```

Mỗi workload:

- warm-up tối thiểu 2 lần nếu phù hợp;
- đo tối thiểu 10 lần với mock/deterministic services;
- test thật MT5 ít nhất 5 lần cho P50/P95;
- không dùng một lần chạy duy nhất để kết luận.

### 17.4. Regression

Chạy:

```text
pytest tests/ -x -q
```

So sánh trước/sau:

- row count/order;
- candidate status;
- selected side;
- setup score;
- entry zone;
- SL/TP;
- opportunity rank;
- macro score với frozen input;
- scanner output schema;
- snapshot replay.

---

## 18. Ngân sách và mục tiêu hiệu năng

Các mục tiêu sau là acceptance target ban đầu, cần điều chỉnh nếu Phase 0 chứng minh
giới hạn khác.

### 18.1. Time to core result — 28 symbols

| Metric | Baseline | Target warm |
|---|---:|---:|
| P50 | khoảng 80 giây | ≤ 30 giây |
| P95 | trên 100 giây | ≤ 45 giây |

### 18.2. Aftercare

| Metric | Target |
|---|---:|
| Telegram ảnh hưởng core-ready | 0 ms |
| Persistence ảnh hưởng core-ready | 0 ms hoặc compact summary budget nhỏ |
| Detail alert cho 0 candidate | 0 |
| Summary requests | 1/recipient |
| TNX/FVX/VIX downloads | tối đa 1 mỗi source/TTL |

### 18.3. Correctness

```text
false Telegram candidate count = 0
analysis parity failures = 0
candidate/ranking parity failures = 0
overlapping core scan/controller = 0
```

---

## 19. Rủi ro và biện pháp giảm thiểu

### 19.1. Cache stale

Rủi ro:

- macro hoặc candle cũ bị coi là mới.

Giảm thiểu:

- TTL;
- fetched/expires timestamps;
- stale flags;
- full reload on gap;
- fail-safe data quality;
- cache metrics.

### 19.2. Async aftercare mất dữ liệu khi app đóng

Rủi ro:

- Telegram/snapshot chưa xong.

Giảm thiểu:

- bounded shutdown wait;
- compact summary trước;
- job status/incomplete marker;
- không force terminate giữa file write.

### 19.3. Core output bị mutate giữa threads

Rủi ro:

- race và snapshot không nhất quán.

Giảm thiểu:

- immutable convention;
- aftercare delta riêng;
- UI merge trên GUI thread;
- test stale scan ID.

### 19.4. Macro parity thay đổi

Rủi ro:

- refactor cache vô tình đổi score.

Giảm thiểu:

- frozen-response parity fixtures;
- cùng global snapshot cho before/after;
- không đổi formulas.

### 19.5. MT5 history cache gap

Rủi ro:

- thiếu candle làm sai indicator.

Giảm thiểu:

- strict timestamp validation;
- gap detection;
- fallback full reload;
- cache identity đầy đủ.

---

## 20. Rollout và rollback

### 20.1. Rollout

Thứ tự:

```text
Phase 0 telemetry
  ↓
Phase 1 Telegram correctness
  ↓
Phase 2 macro caching/globalization
  ↓
Phase 3 core result early
  ↓
Phase 4 MT5 rolling cache
  ↓
Phase 5 persistence/locking
```

Không gộp tất cả vào một commit lớn.

Mỗi phase:

1. Unit tests.
2. Full tests.
3. Runtime benchmark.
4. Diff review.
5. Commit riêng.

### 20.2. Feature flags

Khuyến nghị flag cho các thay đổi kiến trúc:

```text
scanner_core_result_early
scanner_macro_global_cache
scanner_mt5_history_cache
scanner_aftercare_worker
```

Telegram correctness bug fix không nên giữ behavior sai phía sau flag; chỉ legacy
fallback phải được test.

### 20.3. Rollback

- Tắt flag tương ứng.
- Core scanner quay lại flow cũ.
- Không cần migration dữ liệu.
- Candle cache memory-only nên rollback không cần dọn disk.
- Snapshot schema giữ backward compatible.

---

## 21. Những cách tối ưu bị cấm hoặc không khuyến nghị

AI Coder không được:

- bỏ MT5 lock để ép parallel calls;
- chạy 28 MT5 service instances;
- giảm bar count mà không parity/backtest;
- tắt scoring/SMC để tăng tốc;
- bỏ Telegram error handling;
- coi `candidate_order_payload=None` là legacy;
- gửi alert cho OUT_OF_STRATEGY/DATA_UNAVAILABLE;
- cache macro không có TTL/provenance;
- chia sẻ mutable output giữa thread mà không có invariant;
- chạy nhiều aftercare jobs không giới hạn;
- bỏ persistence âm thầm;
- dùng một benchmark run để tuyên bố thành công;
- bật fast Tier 1/2 như giải pháp chính cho bottleneck network;
- sửa UI progress mà không sửa critical path thật.

---

## 22. Tiêu chí nghiệm thu cuối

Implementation được coi là hoàn tất khi:

1. Có performance telemetry đầy đủ.
2. 28 rejected rows tạo 0 detail Telegram alerts.
3. Không có compatibility fallback cho key present-but-None.
4. TNX/FVX/VIX chỉ fetch một lần/source/TTL.
5. Macro context không bị build hai lần cùng key trong một scan.
6. Core result hiển thị trước Telegram/full persistence.
7. Telegram/persistence error không xóa core result.
8. Warm MT5 scan dùng tail update và có full fallback.
9. Không có hai core scan cùng controller.
10. Scoring/candidate/ranking parity pass.
11. Snapshot/replay tests pass.
12. `pytest tests/ -x -q` pass.
13. Benchmark 28-symbol P50/P95 được báo cáo.
14. Không có side effect mới ngoài phạm vi.
15. Diff được PO review trước commit.

---

## 23. Code cần đọc trước khi triển khai

### Scanner orchestration

- `ui/screens/scanner_screen.py`
  - `_run_scan()`
  - `_scan_finished()`
  - `_scan_thread_finished()`
  - auto-scan scheduling
- `workers/scanner_worker.py`
- `controllers/scanner_controller.py`
  - `run_market_scan()`
  - `_apply_scanner_filters()`
  - `_get_alert_order_candidates()`
  - `_send_telegram_alerts()`
  - `save_snapshot()`
  - `_fetch_one_symbol_mt5()`
  - `_analyze_one_symbol()`

### Services

- `services/telegram_alert_service.py`
  - `send_order_alerts()`
  - `send_summary_alert()`
  - `_send_message()`
- `services/news_service.py`
  - `latest_macro_context()`
  - `data_quality_flags()`
  - `preload_macro_contexts()`
  - `_ai_currency_stance()`
  - `_fetch_yield_spread()`
  - `_fetch_vix()`
  - `_macro_tier1()`
  - `_macro_tier3()`
- `services/mt5_service.py`
  - `_serialized_mt5_operation`
  - `load_ohlcv()`
  - `load_primary_timeframes()`
- `services/scanner_persistence_service.py`
- `services/runtime_retention_service.py`

### Core

- `core/analysis_engine.py`
- `core/analysis_pipeline.py`
- `core/scanner_candidate_engine.py`
- `core/scanner_rollout.py`
- `core/scanner_observability.py`

### Existing performance evidence

- `docs/scanner/scanner-fast-reject-plan.md`
- `tests/test_scanner_fast_path.py`
- `tests/fixtures/scanner_fast_path/full-oracles.json`
- `tests/test_mt5_operation_serialization.py`

---

## 24. Checklist bàn giao cho AI Coder

### Trước khi code

- [ ] Đọc toàn bộ tài liệu.
- [ ] Đọc các file ở mục 23.
- [ ] Chạy `git status`.
- [ ] Chạy baseline tests.
- [ ] Ghi baseline runtime/performance.
- [ ] Không chạy scan thật nếu auto-trade/Telegram chưa được vô hiệu hóa an toàn.

### Phase 0

- [ ] Instrument đủ phase.
- [ ] Không đổi behavior.
- [ ] Persist performance summary.
- [ ] Thêm test instrumentation failure.

### Telegram

- [ ] Phân biệt key absent và `None`.
- [ ] Canonical payload là nguồn duy nhất cho schema mới.
- [ ] Structural reject skip.
- [ ] Test 27 rejected → 0 alerts.
- [ ] Đo request count và duration.

### Macro

- [ ] Một cache-key helper.
- [ ] AI fingerprint không chứa secret.
- [ ] Context được write-through cache.
- [ ] TNX/FVX/VIX global snapshot.
- [ ] Unique currency stance.
- [ ] Frozen-input parity.

### Core/aftercare

- [ ] Core result phát sớm.
- [ ] Output immutable.
- [ ] Aftercare delta riêng.
- [ ] Scan ID guard.
- [ ] Lỗi aftercare không fail core.

### MT5 cache

- [ ] Cold/full path.
- [ ] Warm/tail path.
- [ ] Forming bar replace.
- [ ] Gap fallback.
- [ ] Identity invalidation.
- [ ] MT5 lock vẫn được giữ.
- [ ] Full-vs-cache parity.

### Trước review

- [ ] Chạy focused tests.
- [ ] Chạy `pytest tests/ -x -q`.
- [ ] Báo cáo P50/P95.
- [ ] Báo cáo network/MT5/Telegram call counts.
- [ ] Xác minh không có alert sai.
- [ ] Xác minh không có scan overlap.
- [ ] Gửi diff từng phase.
- [ ] Không commit trước khi PO duyệt nếu workflow yêu cầu.
