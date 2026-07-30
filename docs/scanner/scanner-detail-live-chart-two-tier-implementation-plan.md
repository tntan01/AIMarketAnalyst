# Kế hoạch triển khai biểu đồ live hai tầng cho Scanner Detail

**Phạm vi:** `ScannerDetailScreen` → tab **Tổng quan** → biểu đồ nến

**Phương án được chọn:** Phương án B — tách cập nhật nến nhanh và tính lại phân tích theo nến đóng

**Trạng thái tài liệu:** Đề xuất kỹ thuật để PO duyệt trước khi AI Coder triển khai

**Ngày lập:** 30/07/2026

---

## 1. Tóm tắt quyết định

Biểu đồ trong `ScannerDetailScreen` hiện không có luồng dữ liệu real-time riêng. Khi người dùng bấm quét:

1. Scanner tải dữ liệu D1/H4/H1/M15 cho từng symbol.
2. Pipeline phân tích và lưu dữ liệu nến vào `analysis_result["chart_payload"]`.
3. Khi người dùng mở một dòng, màn hình chi tiết dựng chart từ snapshot đó.
4. Sau thời điểm mở, chart không gọi MT5 để lấy nến mới.

Nếu chỉ thêm timer và gọi lại cơ chế render hiện tại mỗi 1–2 giây thì ứng dụng sẽ:

- tải và truyền lại quá nhiều dữ liệu;
- hủy rồi tạo lại toàn bộ chart;
- có nguy cơ giật, nhấp nháy và mất vị trí zoom;
- cạnh tranh MT5 lock với scanner và quản lý lệnh;
- nếu tái sử dụng toàn bộ `run_market_scan()`, có thể kích hoạt persistence, Telegram hoặc luồng auto-trade ngoài ý muốn.

Phương án triển khai được chọn là kiến trúc hai tầng:

- **Tầng nhanh — Live Candle:** mỗi 2 giây chỉ tải 1–2 nến của timeframe đang xem và cập nhật nến cuối bằng API incremental của Lightweight Charts. Không tính lại scoring, EMA, SMC, Entry, SL hoặc TP.
- **Tầng chậm — Closed-candle Recalculation:** khi xác nhận có nến M15 mới, tải lại dữ liệu cần thiết và chạy một pipeline phân tích một-symbol, chỉ phục vụ màn hình chi tiết. Kết quả mới cập nhật đồng bộ indicator, scoring, SMC zone, Entry, SL và TP.

Luồng tính lại chậm là **display-only**:

- không thay đổi kết quả/ranking gốc trong `ScannerScreen`;
- không gửi lệnh;
- không chạy auto-trade;
- không gửi Telegram;
- không tạo market brief bằng AI;
- không tự động ghi journal hoặc scanner snapshot;
- không phát candidate event của một lần quét thị trường.

Interval mặc định được khóa ở **2.000 ms**. Sau khi đo hiệu năng có thể cho phép cấu hình xuống 1.000–1.500 ms, nhưng không triển khai cấu hình UI trong phiên bản đầu.

---

## 2. Vấn đề hiện tại

### 2.1. Chart chỉ là snapshot

`ScannerScreen` sở hữu timer quét theo timeframe. Timer này phục vụ việc chạy lại toàn bộ scanner theo M5/M15/H1/H4, không phục vụ biểu đồ trong màn hình chi tiết.

`ScannerDetailScreen.set_analysis_result()` nhận `scanner_row` và `scanner_result` khi điều hướng. Sau đó `_refresh_chart()` gọi `build_full_chart_payload()` một lần và truyền payload sang `AnalysisChartView`.

Hệ quả:

- Giá và nến đứng yên tại thời điểm quét.
- Việc Scanner chạy lần tiếp theo không tự động đẩy row mới vào detail đang mở.
- Mở detail không gọi MT5 lại.
- Chuyển timeframe chỉ chuyển giữa các mảng nến đã lưu trong snapshot.

### 2.2. Dữ liệu chart đã có cho mọi symbol, nhưng chưa render

Trong mỗi symbol phân tích thành công, pipeline lưu:

```text
analysis_result
  └── chart_payload
      ├── D1:  danh sách OHLCV
      ├── H4:  danh sách OHLCV
      ├── H1:  danh sách OHLCV
      └── M15: danh sách OHLCV
```

Điều này có nghĩa dữ liệu nền đã nằm trong kết quả scan, nhưng QWebEngine/Lightweight Charts chỉ dựng chart cho symbol mà người dùng mở.

### 2.3. Render hiện tại là full redraw

Ở phía JavaScript:

- `setChartData()` gọi `_initChart()`.
- `_initChart()` gọi `_clearChart()`.
- `_clearChart()` gọi `_chart.remove()`.
- Candlestick series và EMA series được tạo lại.
- Toàn bộ dữ liệu được gán bằng `setData()`.
- Entry zone, source zone, SL, TP và current-price line được tạo lại.

Chuyển timeframe và refresh theme cũng có đường đi dựng lại chart.

Đây là cơ chế đúng cho:

- lần mở chart đầu tiên;
- đổi toàn bộ snapshot phân tích;
- đổi timeframe;
- recovery sau lỗi.

Đây không phải cơ chế phù hợp để cập nhật một nến mỗi 1–2 giây.

### 2.4. Python chưa biết timeframe người dùng chọn trong JavaScript

Timeframe selector nằm trong `assets/chart/index.html`. Khi người dùng bấm D1/H4/H1/M15, JavaScript gọi `switchTimeframe(tf)` trực tiếp.

`AnalysisChartView._active_tf` chỉ được thay đổi nếu Python chủ động gọi `switch_timeframe()`. Hiện không có bridge gửi sự kiện từ JavaScript về Python.

Nếu không sửa điểm này, backend không biết cần poll timeframe nào. Poll cả bốn timeframe mỗi 2 giây sẽ gây tải thừa.

### 2.5. MT5 được bảo vệ bởi lock chung

`MT5Service` dùng `RLock` để serialize thao tác MT5. Đây là invariant cần giữ nguyên.

Timer UI không được:

- import `MetaTrader5` trực tiếp;
- gọi `copy_rates_from_pos()` trực tiếp;
- bỏ qua `MT5Service`;
- chờ đồng bộ một lệnh MT5 trên GUI thread.

Mọi yêu cầu live chart phải đi qua singleton `app.mt5` và chạy trên worker thread.

### 2.6. Không thể dùng callback OnTick trực tiếp từ MT5 Python

`OnTick` là event của MQL5 Expert Advisor, không phải callback do package Python cung cấp. Python API vẫn theo mô hình gọi hàm để đọc tick/rates.

Do đó phiên bản đầu phải dùng polling có kiểm soát. Viết EA trung gian để push tick là một dự án khác, không thuộc phạm vi tài liệu này.

---

## 3. Mục tiêu và phi mục tiêu

### 3.1. Mục tiêu bắt buộc

1. Khi detail đang hiển thị và MT5 sẵn sàng, nến hiện tại được cập nhật tối đa mỗi 2 giây.
2. Không hủy và tạo lại chart trong các lần cập nhật nhanh.
3. Timeframe nào đang hiển thị thì chỉ timeframe đó được poll nhanh.
4. Khi nến M15 mới xuất hiện, hệ thống chạy lại phân tích một-symbol.
5. Indicator và các mức Entry/SL/TP chỉ đổi sau khi pipeline chậm hoàn tất thành công.
6. Chart, card và diagnostics phải nhận cùng một live analysis snapshot; không được hiển thị Entry/SL/TP của hai phiên bản khác nhau.
7. GUI không bị block bởi lời gọi MT5 hoặc pipeline phân tích.
8. Không có hai request live cùng loại chạy chồng lên nhau.
9. Kết quả trả về muộn của symbol/timeframe cũ phải bị bỏ.
10. Rời `ScannerDetailScreen` phải dừng timer; màn hình ẩn không được tiếp tục poll.
11. Lỗi live refresh không được xóa snapshot scan đang hiển thị.
12. Luồng live không được tạo side effect giao dịch hoặc thông báo.

### 3.2. Phi mục tiêu

Phiên bản đầu không thực hiện:

- stream từng tick ở tần suất dưới một giây;
- cập nhật đồng thời chart của mọi symbol trong kết quả scan;
- thay đổi ranking của bảng Scanner;
- tự động mở/đóng lệnh dựa trên live detail;
- đồng bộ live detail ngược về `ScannerScreen`;
- thêm setting UI để chỉnh interval;
- thêm M5 vào chart nếu payload hiện tại chưa có;
- thay đổi logic scoring/SMC;
- thay đổi font, theme hoặc bố cục tổng thể;
- thay Lightweight Charts bằng thư viện khác;
- xây MQL5 EA/ZeroMQ/socket bridge.

---

## 4. Các invariant an toàn

AI Coder phải giữ các invariant sau trong toàn bộ quá trình triển khai.

### INV-01 — Snapshot scan là bất biến

Row nhận từ `ScannerScreen` phải được giữ dưới dạng snapshot gốc. Live refresh không được mutate trực tiếp object thuộc `scanner_result["rows"]`.

Khi nhận payload mới:

- deep-copy hoặc tạo dict mới;
- giữ `source_scan_row` riêng;
- giữ `live_display_row` riêng.

### INV-02 — Live detail không có quyền execution

Không truyền `live_display_row` vào:

- `execute_order_candidate()`;
- auto-trade;
- rollout execution;
- Telegram alert;
- scanner event emitter;
- scanner persistence tự động.

Nếu UI có hành động lưu/xuất/AI audit, dữ liệu được dùng phải được quy định rõ:

- **Lưu nhật ký / Xuất JSON / AI audit:** dùng snapshot đang hiển thị, nhưng thêm metadata `snapshot_source="live_detail_refresh"` và `parent_scan_id`.
- **Mọi hành động có khả năng gửi lệnh:** phải dùng execution revalidation hiện có, không tin giá hoặc trade permission trong live preview.

Hiện `ScannerDetailScreen` không có nút gửi lệnh trực tiếp. Invariant này vẫn phải có test phòng ngừa.

### INV-03 — MT5 chỉ được gọi qua service chung

Tất cả thao tác mới phải gọi `app.mt5`/`MT5Service`. Không import trực tiếp SDK MT5 trong screen, worker hoặc chart component.

### INV-04 — UI chỉ cập nhật trên GUI thread

Worker chỉ trả DTO/dict qua signal. Worker không được:

- gọi `QWebEnginePage.runJavaScript()`;
- sửa `QLabel`;
- gọi `_render()`;
- truy cập widget.

### INV-05 — Một request đang chạy cho mỗi tầng

Tối đa:

- một fast fetch đang chạy;
- một M15 boundary check hoặc một slow recalculation đang chạy.

Nếu timer phát khi request trước chưa xong thì bỏ lượt hiện tại, không xếp hàng vô hạn.

### INV-06 — Kết quả phải đúng session

Mỗi lần `set_analysis_result()` tạo một `session_id` mới. Mọi request và response mang:

- `session_id`;
- `chart_revision`;
- `symbol`;
- `broker_symbol`;
- `timeframe`;
- `request_id`.

Screen chỉ áp dụng response nếu các trường trên còn khớp state hiện tại.

`chart_revision` tăng sau mỗi lần full payload được áp dụng, gồm snapshot ban đầu và
slow snapshot. Trường này chặn một fast response được lấy trước slow refresh nhưng
trả về sau đó ghi đè nến có cùng timestamp bằng OHLC cũ hơn.

### INV-07 — Fast layer không thay quyết định

Fast response chỉ được cập nhật:

- nến cuối của timeframe đang xem;
- current-price line;
- trạng thái “cập nhật lúc …” nếu có.

Không cập nhật:

- EMA;
- score;
- SMC;
- Entry;
- SL;
- TP;
- trade permission;
- candidate status.

### INV-08 — Slow snapshot phải nguyên tử

Sau khi slow recalculation thành công:

1. Tạo live row hoàn chỉnh trong worker/controller.
2. Build full chart payload từ chính `analysis_result` của live row đó.
3. Trên GUI thread, thay `live_display_row` một lần.
4. Render các card/diagnostics và full chart từ cùng snapshot.

Không áp dụng từng phần khi pipeline chưa hoàn tất.

---

## 5. Kiến trúc mục tiêu

```text
┌─────────────────────────────────────────────────────────────┐
│ ScannerDetailScreen — GUI thread                            │
│                                                             │
│  source_scan_row (immutable)                                │
│  live_display_row (optional)                                │
│  session_id / active_timeframe                              │
│                                                             │
│  QTimer fast: 2000 ms                                       │
│  QTimer slow: single-shot đến M15 boundary                  │
│       │                                                     │
│       ├── fast request ──────────────┐                       │
│       └── slow request ────────────┐ │                       │
└────────────────────────────────────┼─┼───────────────────────┘
                                     │ │ queued signals
┌───────────────────────────────┐  ┌────────────────────────────┐
│ LiveBarWorker                 │  │ LiveAnalysisWorker         │
│ dedicated fast QThread        │  │ dedicated slow QThread     │
│                               │  │                            │
│ fetch_live_bar(request)       │  │ recalculate_detail(request)│
│ confirm_m15_boundary(request) │  │                            │
│       │                       │  │       │                    │
│       └── MT5Service          │  │       ├── MT5Service       │
│           .load_latest_bars() │  │       └── ScannerController│
│                               │  │           .recalculate...  │
└──────────────────┬────────────┘  └─────────────┬──────────────┘
                   │ result/error signals        │
                   └─────────────────┬────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────┐
│ ScannerDetailScreen — GUI thread                            │
│                                                             │
│  fast result → AnalysisChartView.update_live_bar()          │
│  slow result → replace live_display_row atomically          │
│              → _render()                                    │
└────────────────────────────────────┬────────────────────────┘
                                     │
┌────────────────────────────────────▼────────────────────────┐
│ AnalysisChartView / QWebEngine                              │
│                                                             │
│  set_payload()      → full snapshot                         │
│  update_live_bar()  → one candle via series.update()        │
│  JS→Python timeframeChanged(tf) via QWebChannel             │
└─────────────────────────────────────────────────────────────┘
```

### 5.1. Vì sao dùng hai worker thread sống lâu

Không nên tạo một `QThread` mới sau mỗi 2 giây vì:

- tăng chi phí khởi tạo/hủy thread;
- khó quản lý kết quả trả về muộn;
- tăng nguy cơ giữ reference sai;
- khó thực hiện backpressure.

Thiết kế đề xuất:

- tạo một fast `QThread` chứa `LiveBarWorker`;
- tạo một slow `QThread` chứa `LiveAnalysisWorker`;
- hai thread được khởi tạo lazy khi detail có payload hợp lệ;
- hai worker cùng dùng singleton `MT5Service`, do đó lời gọi SDK vẫn được serialize
  bởi lock chung;
- tách thread giúp fast polling có thể tiếp tục sau khi slow worker đã tải xong dữ
  liệu MT5 và đang chạy phần CPU/network không giữ MT5 lock;
- thread có thể sống đến khi ứng dụng đóng;
- khi screen bị ẩn chỉ dừng timer và vô hiệu hóa session, không `terminate()` thread;
- khi ứng dụng đóng: `quit()` và `wait()` từng thread với timeout hợp lý, không
  force terminate khi worker đang trong SDK call.

---

## 6. Mô hình state

### 6.1. State cần có trong `ScannerDetailScreen`

| State | Kiểu gợi ý | Ý nghĩa |
|---|---|---|
| `_source_scan_row` | `dict` | Bản sao bất biến của row lúc mở detail |
| `_live_display_row` | `dict \| None` | Kết quả phân tích live gần nhất |
| `_live_session_id` | `str` | UUID/generation token của symbol hiện tại |
| `_chart_revision` | `int` | Tăng sau mỗi full snapshot để loại fast response cũ |
| `_active_chart_tf` | `str` | Một trong D1/H4/H1/M15 |
| `_last_analyzed_m15_time` | UTC datetime/string | Timestamp M15 đã dùng cho slow analysis |
| `_fast_request_in_flight` | `bool` | Backpressure cho fast poll |
| `_slow_request_in_flight` | `bool` | Backpressure cho slow recalc |
| `_screen_is_active` | `bool` | Screen đang visible/current |
| `_fast_failures` | `int` | Số lỗi liên tiếp để backoff |
| `_slow_boundary_retries` | `int` | Retry xác nhận nến M15 mới |
| `_last_live_success_at` | UTC datetime | Telemetry/trạng thái freshness |

Không dùng `self.row` làm cả snapshot gốc và state live mà không có quy ước. Cách ít phá code nhất:

1. `self._source_scan_row` luôn giữ bản scan gốc.
2. `self.row` là row đang hiển thị.
3. Khi slow refresh thành công, gán `self.row` bằng một dict mới.
4. Các action cần dữ liệu gốc phải dùng `_source_scan_row`; các action được định nghĩa dùng snapshot hiển thị thì dùng `self.row` và gắn metadata nguồn.

AI Coder phải audit ba action hiện có:

- `_run_ai_audit`;
- `_export_json`;
- `_save_to_journal`.

### 6.2. State machine

```text
NO_PAYLOAD
   │ set_analysis_result(valid)
   ▼
READY_HIDDEN
   │ showEvent
   ▼
VISIBLE_IDLE
   │ fast timer
   ▼
FAST_IN_FLIGHT ──success/error──► VISIBLE_IDLE
   │
   └── hide/new payload ──► response bị bỏ theo session_id

VISIBLE_IDLE
   │ M15 boundary
   ▼
SLOW_CHECK_IN_FLIGHT
   ├── chưa có nến mới ─► schedule retry/next boundary
   ├── có nến mới ─────► SLOW_RECALC_IN_FLIGHT
   └── lỗi ────────────► giữ snapshot cũ + schedule next boundary

SLOW_RECALC_IN_FLIGHT
   ├── success ─► apply snapshot nguyên tử + schedule next boundary
   └── error ───► giữ snapshot cũ + schedule next boundary
```

---

## 7. Contract dữ liệu

Nên đặt dataclass trong module mới `core/live_chart_models.py`. Nếu repository ưu tiên dict để qua `pyqtSignal(object)`, vẫn phải giữ cùng field và validation.

### 7.1. `LiveBarRequest`

| Field | Bắt buộc | Nội dung |
|---|---|---|
| `request_id` | Có | UUID cho một request |
| `session_id` | Có | Session detail hiện tại |
| `chart_revision` | Có | Revision full chart tại lúc gửi request |
| `symbol` | Có | Symbol chuẩn, ví dụ `EUR/USD` |
| `broker_symbol` | Có | Mã thực tế trong MT5 |
| `timeframe` | Có | D1/H4/H1/M15 |
| `bars` | Có | Luôn bằng 2 ở fast path |
| `requested_at` | Có | UTC timestamp |

### 7.2. `LiveBarResult`

| Field | Nội dung |
|---|---|
| `request_id`, `session_id`, `chart_revision` | Echo từ request |
| `symbol`, `broker_symbol`, `timeframe` | Dùng để chống stale response |
| `bars` | Tối đa hai OHLCV đã chuẩn hóa |
| `current_price` | Close của bar hiện tại; không tự suy ra bid/ask |
| `fetched_at` | UTC timestamp |
| `mt5_latency_ms` | Metric |

Không bắt buộc gọi `symbol_info_tick()` ở fast path đầu tiên. `copy_rates_from_pos(..., 0, 2)` đã cung cấp OHLC đang hình thành và close gần nhất. Việc gọi thêm tick làm tăng call rate mà chưa mang lại lợi ích đủ lớn.

### 7.3. `SlowRecalculationRequest`

| Field | Nội dung |
|---|---|
| `request_id`, `session_id` | Chống stale result |
| `base_chart_revision` | Revision tại lúc bắt đầu slow refresh |
| `symbol`, `broker_symbol` | Symbol cần phân tích |
| `source_row` | Bản copy của scan row gốc |
| `source_scanner_result_meta` | Chỉ metadata cần thiết, không truyền toàn bộ object nếu không cần |
| `expected_new_m15_time` | Timestamp nến M15 vừa phát hiện |
| `requested_at` | UTC timestamp |

### 7.4. `SlowRecalculationResult`

| Field | Nội dung |
|---|---|
| `request_id`, `session_id`, `base_chart_revision` | Echo |
| `symbol`, `broker_symbol` | Echo |
| `m15_bar_time` | M15 bar mới đã dùng |
| `display_row` | Row hoàn chỉnh phục vụ render detail |
| `chart_payload` | Full payload build từ `display_row.analysis_result` |
| `completed_at` | UTC timestamp |
| `fetch_latency_ms` | Thời gian tải dữ liệu |
| `analysis_latency_ms` | Thời gian pipeline |
| `total_latency_ms` | Tổng thời gian |
| `snapshot_source` | Luôn là `live_detail_refresh` |
| `parent_scan_id` | Scan gốc |

---

## 8. Tầng nhanh — cập nhật nến mỗi 2 giây

### 8.1. Điều kiện được poll

Fast timer chỉ được chạy khi tất cả điều kiện đúng:

- screen đang visible;
- có `_source_scan_row`;
- symbol và broker symbol không rỗng;
- chart có payload;
- WebEngine page đã load hoặc component có thể queue script;
- không có fast request đang chạy;
- không có slow full recalculation đang áp dụng snapshot.

Khi slow worker đang giữ MT5 lock để tải toàn bộ lịch sử, fast request có thể phải
chờ lock. In-flight guard phải ngăn timer xếp thêm request. Sau khi phần tải MT5
hoàn tất, slow worker chuyển sang phân tích còn fast worker có thể tiếp tục lấy
nến mới.

### 8.2. Lời gọi MT5

Thêm method public vào `MT5Service`, ví dụ:

```text
load_latest_bars(broker_symbol, timeframe, count=2) -> list[Candle]
```

Contract:

- đi qua `_serialized_mt5_operation`;
- validate timeframe bằng `_timeframe_id`;
- select symbol nếu cần;
- gọi `copy_rates_from_pos(..., 0, count)`;
- trả Candle theo UTC;
- không tự connect/disconnect cho mỗi poll nếu service hiện quản lý connection dùng chung;
- không spawn `ThreadPoolExecutor`;
- không swallow lỗi; worker chuyển lỗi thành signal.

### 8.3. Áp dụng kết quả vào JavaScript

Thêm public function JavaScript:

```text
window.updateLiveBar(update)
```

Function phải:

1. Validate `_payload`, `_chart`, `_candleSeries`.
2. Validate `update.symbol === _payload.symbol`.
3. Validate `update.timeframe === _activeTF`.
4. Chuẩn hóa timestamp giống `_renderCandles()`.
5. So sánh với timestamp nến cuối trong `_payload.timeframes[_activeTF].candles`.
6. Nếu cùng timestamp:
   - thay phần tử cuối trong cached payload;
   - gọi `_candleSeries.update(bar)`.
7. Nếu timestamp lớn hơn:
   - append bar mới;
   - gọi `_candleSeries.update(bar)`.
8. Nếu timestamp nhỏ hơn:
   - bỏ vì response cũ.
9. Cập nhật `_payload.current_price`.
10. Cập nhật current-price line hiện có bằng `applyOptions({price})`.
11. Không gọi `_initChart()`, `setData()`, `_renderLevels()` hoặc `_fitPriceScale()`.

Cần tách `_currentPriceLine` khỏi `_priceLines` để có thể cập nhật trực tiếp. Khi full redraw, `_clearChart()` phải reset cả reference này.

### 8.4. Không làm gì với EMA ở fast layer

EMA hiện được build thành các series tĩnh. Trong fast path:

- không cập nhật điểm EMA cuối;
- không chạy lại `core.indicators.ema`;
- không thêm một EMA point tạm;
- không xóa EMA.

EMA được cập nhật ở slow layer sau khi có nến M15 mới. Đây là quyết định cố ý để tránh tạo hai nguồn tính indicator khác nhau giữa Python và JavaScript.

### 8.5. Backoff

Đề xuất:

| Lỗi liên tiếp | Interval tiếp theo |
|---|---|
| 0 | 2 giây |
| 1–2 | 5 giây |
| 3–5 | 15 giây |
| >5 | 30 giây, hiển thị trạng thái stale |

Sau một lần thành công, reset về 2 giây.

Không hiển thị dialog/modal cho lỗi polling. Chỉ cập nhật trạng thái không gây gián đoạn, ví dụ “MT5 tạm thời không cập nhật — đang hiển thị dữ liệu gần nhất”.

---

## 9. Đồng bộ timeframe JavaScript → Python

### 9.1. Cơ chế

Dùng `QWebChannel`, không dùng polling DOM hoặc parse URL.

Python:

- tạo bridge `QObject`;
- expose slot `timeframeChanged(str)`;
- đăng ký object với `QWebChannel`;
- `AnalysisChartView` phát signal `active_timeframe_changed(str)`.

JavaScript:

- load `qrc:///qtwebchannel/qwebchannel.js`;
- khởi tạo channel sau khi document sẵn sàng;
- sau khi `switchTimeframe(tf)` thành công, gọi bridge `timeframeChanged(tf)`.

`ScannerDetailScreen` nhận signal và:

1. validate timeframe thuộc `{D1, H4, H1, M15}`;
2. cập nhật `_active_chart_tf`;
3. tăng một `timeframe_generation` hoặc tạo request mới;
4. bỏ response fast của timeframe cũ;
5. yêu cầu fast refresh ngay cho timeframe mới nếu screen đang active.

### 9.2. Tránh vòng lặp

Khi Python chủ động gọi `switch_timeframe(tf)`, JavaScript có thể báo ngược lại cùng timeframe. Handler phải idempotent:

- nếu timeframe mới bằng `_active_chart_tf`, không tạo thêm request;
- không gọi lại `switch_timeframe()` từ handler.

---

## 10. Tầng chậm — tính lại khi nến M15 đóng

### 10.1. Không poll M15 mỗi 2 giây khi đang xem timeframe khác

Dùng một `QTimer` single-shot riêng cho boundary M15.

Nguồn timestamp ban đầu:

- lấy timestamp cuối trong `analysis_result["chart_payload"]["M15"]`;
- lưu vào `_last_analyzed_m15_time`.

Tính lịch:

```text
expected_next_m15 = last_m15_time + 15 phút
fire_at = expected_next_m15 + grace_period
```

Grace period mặc định: **3 giây**.

Tất cả timestamp phải dùng UTC/epoch; không dựa vào timezone hiển thị của người dùng.

Nếu detail được mở sau boundary dự kiến, chạy boundary check ngay.

### 10.2. Xác nhận nến mới

Khi slow timer phát:

1. Nếu screen ẩn hoặc session đã đổi: dừng.
2. Lấy 2 nến M15 mới nhất qua worker.
3. So sánh timestamp nến cuối với `_last_analyzed_m15_time`.
4. Chỉ chạy pipeline nếu timestamp mới lớn hơn.
5. Nếu chưa có bar mới:
   - retry sau 2 giây;
   - lần hai sau 5 giây;
   - lần ba sau 15 giây;
   - sau đó dừng retry và lên lịch boundary M15 kế tiếp.

Nếu active timeframe là M15, fast result cũng có thể phát hiện timestamp mới. Hai nguồn trigger phải đi qua cùng một hàm coalescing để chỉ tạo một slow request.

### 10.3. Dữ liệu cần tải lại

Slow recalculation tải lại đúng bộ dữ liệu pipeline đang dùng:

- D1: số bar theo settings hiện hành, mặc định 500;
- H4: số bar theo settings hiện hành, mặc định 500;
- H1: số bar theo settings hiện hành, mặc định 500;
- M15: 100 bar.

Không tải lịch sử này trong fast path.

### 10.4. Contract nến đóng và nến đang hình thành

Đây là điểm bắt buộc phải xử lý rõ. `copy_rates_from_pos(..., 0, ...)` trả cả bar
đang hình thành. Khi timestamp M15 mới xuất hiện:

- bar M15 mới nhất là bar **đang hình thành**;
- bar ngay trước nó mới là bar **vừa đóng**.

Pipeline chậm không được dùng bar M15 mới đang hình thành để xác nhận tín hiệu của
bar vừa đóng. Cách chuẩn:

1. Tải đủ M15 để có cả bar mới và lịch sử.
2. Lấy `new_forming_m15_time` từ bar cuối.
3. Tạo `analysis_m15_candles` chỉ gồm các bar có
   `time < new_forming_m15_time`.
4. Bar cuối của `analysis_m15_candles` chính là bar đã đóng dùng cho scoring.
5. Ghi metadata:
   - `analysis_trigger="m15_close"`;
   - `analysis_cutoff_m15_time`;
   - `new_forming_m15_time`.

Chart vẫn phải hiển thị bar mới đang hình thành. Vì vậy cần phân biệt:

- `analysis_m15_candles`: không chứa bar đang hình thành, dùng cho pipeline;
- `display_m15_candles`: có bar đang hình thành, dùng cho chart payload.

Sau khi `analyze_symbol()` trả kết quả, controller có thể thay phần M15 trong
`analysis_result["chart_payload"]` bằng `display_m15_candles`, đồng thời giữ
metadata cutoff nói trên. Không được để pipeline vô tình dùng lại danh sách đã
được thay cho mục đích hiển thị.

Với D1/H4/H1, milestone đầu giữ semantics hiện tại của scanner để tránh một thay
đổi scoring ngoài phạm vi: dữ liệu có thể bao gồm bar đang hình thành. Chuyển toàn
bộ pipeline sang closed-bar-only cho mọi timeframe là một thay đổi sản phẩm khác,
phải được đánh giá và backtest riêng.

### 10.5. Public entry point side-effect-free

Không gọi `ScannerController.run_market_scan()`.

Thêm một public method có contract rõ ràng, ví dụ:

```text
ScannerController.recalculate_detail_symbol(
    symbol,
    broker_symbol,
    source_row,
    source_scanner_meta,
) -> dict
```

Method này chỉ được:

1. Load settings hiện hành.
2. Load current MT5 balance/data quality cần cho `AnalysisInput`.
3. Load D1/H4/H1/M15 cho một symbol.
4. Xây macro/correlation context theo policy bên dưới.
5. Gọi `analyze_symbol()`.
6. Gọi `scanner_row_from_analysis()`.
7. Chạy canonical `evaluate_scanner_candidate()` để các card đọc được một decision đồng bộ.
8. Build `scanner_candidate_decision` và các display field cần thiết.
9. Gắn metadata live preview.
10. Trả row; không ghi hoặc gửi bất cứ thứ gì.

Method tuyệt đối không được:

- gọi `_emit_candidate_events`;
- gọi `_execute_auto_trade`;
- ghi scanner snapshot;
- gọi Telegram;
- gọi AI market brief;
- cập nhật rollout metrics;
- thay đổi `ScannerScreen.scan_result`;
- xây candidate order có thể được tự động thực thi.

Nếu cần dùng `_apply_scanner_filters()` để giữ canonical decision, phải refactor phần đánh giá một row thành helper thuần túy. Không gọi toàn bộ flow filter nếu flow đó gắn observability hoặc execution side effect.

### 10.6. Policy cho context không phải giá

Phiên bản đầu áp dụng policy sau:

- **Settings/risk/account balance:** đọc mới tại thời điểm slow refresh.
- **Data quality/spread:** đọc mới từ MT5.
- **News/macro context:** refresh qua `NewsService` nhưng không gọi AI provider. Nếu nguồn macro lỗi, giữ macro context của live snapshot thành công gần nhất và gắn `macro_context_stale=true`.
- **Correlation context:** refresh tối đa một lần mỗi 15 phút; dùng cache nếu service đã có cache. Nếu lỗi, dùng context của snapshot trước và gắn stale metadata.
- **Closed trades/account guard:** đọc mới từ `JournalService`.
- **Open trades:** giữ đúng policy hiện tại của scanner analysis; không tự ý đổi semantics trong task live chart.
- **Backtest config/strategy thresholds:** resolve lại bằng cùng helper mà scanner dùng cho symbol. Không tự copy một vài field rời rạc nếu có canonical resolver.
- **SMC scoring mode/feature flags:** lấy từ settings hiện hành và ghi provenance vào live snapshot.

Nếu việc refresh macro/correlation làm tăng scope quá lớn, có thể triển khai theo hai milestone:

1. Milestone đầu dùng context từ scan gốc và gắn `context_policy="frozen_from_scan"`.
2. Milestone sau refresh context mỗi M15.

Không được âm thầm trộn context cũ/mới mà không có metadata.

### 10.7. Áp dụng slow result

Trên GUI thread:

1. Kiểm tra session/symbol/request.
2. Kiểm tra `base_chart_revision` vẫn khớp revision mà slow request được tạo từ
   đó, hoặc áp dụng policy cho phép slow result trở thành revision mới của cùng
   session.
3. Kiểm tra `m15_bar_time > _last_analyzed_m15_time`.
4. Gán `self.row = copy(display_row)`.
5. Giữ `_source_scan_row` không đổi.
6. Cập nhật `_last_analyzed_m15_time`.
7. Tăng `_chart_revision` trước khi nhận fast response tiếp theo.
8. Gọi `_render()` để card và diagnostics dùng cùng row.
9. Full payload được set một lần; đây là lần full redraw có chủ đích.
10. Khôi phục active timeframe trước đó, không ép về D1.
11. Gửi một fast request mới theo revision mới để bảo đảm nến đang hình thành là
    bản mới nhất.
12. Lên lịch boundary M15 tiếp theo.

Hiện `_refresh_chart()` hard-code `active_timeframe="D1"`. Khi triển khai phải thay bằng `_active_chart_tf`, nếu timeframe đó tồn tại trong payload; fallback về D1 nếu thiếu.

---

## 11. Vòng đời màn hình

`MainWindow` tạo toàn bộ screen một lần và giữ trong `QStackedWidget`. Vì vậy chỉ tạo timer trong constructor là chưa đủ; timer có thể tiếp tục chạy khi screen bị ẩn.

### 11.1. `set_analysis_result()`

Thứ tự bắt buộc:

1. Dừng fast và slow timer cũ.
2. Tăng/đổi `session_id`.
3. Tăng `_chart_revision`.
4. Reset in-flight flags ở phía UI; response cũ vẫn có thể về nhưng sẽ bị
   session/revision guard bỏ.
5. Deep-copy row gốc vào `_source_scan_row`.
6. Gán bản copy ban đầu vào `self.row`.
7. Reset `_live_display_row`.
8. Resolve symbol/broker symbol.
9. Lấy `_last_analyzed_m15_time` từ payload.
10. Render snapshot gốc.
11. Nếu screen đang visible, start live lifecycle.

### 11.2. `showEvent()`

Nếu payload hợp lệ:

- đánh dấu active;
- đảm bảo cả fast và slow worker thread đã chạy;
- start fast timer;
- gửi một fast request ngay, không cần chờ 2 giây;
- schedule M15 boundary.

Phải gọi `super().showEvent(event)`.

### 11.3. `hideEvent()`

- đánh dấu inactive;
- stop hai timer;
- tăng generation hoặc invalidate session-active flag;
- không force terminate worker nào;
- không xóa chart/snapshot đang hiển thị.

Phải gọi `super().hideEvent(event)`.

### 11.4. Shutdown

Khi widget/app bị đóng:

- stop timer;
- disconnect hoặc invalidate request source;
- gọi `quit()` cho cả hai thread;
- `wait(timeout)` từng thread ở shutdown path, không ở mỗi lần hide;
- không gọi `thread.terminate()`.

---

## 12. Xử lý lỗi và freshness

### 12.1. Fast fetch lỗi

- Giữ nguyên nến cuối đã render.
- Không gọi `showError()` vì việc đó xóa chart.
- Tăng failure count và backoff.
- Log lỗi có request/session/symbol/timeframe.
- Sau success, reset failure count.

### 12.2. Slow recalculation lỗi

- Giữ toàn bộ live snapshot thành công gần nhất.
- Không áp dụng row nửa chừng.
- Không reset Entry/SL/TP.
- Hiển thị trạng thái “Phân tích live chưa cập nhật; đang dùng snapshot lúc …”.
- Schedule boundary tiếp theo.

### 12.3. MT5 disconnect

- Không tự connect/disconnect liên tục mỗi 2 giây nếu connection manager hiện có thể tái sử dụng.
- Fast path backoff đến 30 giây.
- Slow path giữ snapshot.
- Khi `MT5Service` báo kết nối trở lại, lần success tiếp theo tự reset interval.

### 12.4. Market đóng cửa

Khi không có bar M15 mới:

- không chạy pipeline;
- không retry vô hạn ở interval ngắn;
- sau retry giới hạn, lên lịch boundary kế tiếp;
- fast path có thể tiếp tục ở backoff dài hơn nếu dữ liệu không đổi.

### 12.5. Response đến sai thứ tự

Ví dụ:

1. Người dùng đang xem EUR/USD D1.
2. Fast request A được gửi.
3. Người dùng chuyển H1, request B được gửi.
4. Response A về sau B.

Response A phải bị bỏ vì timeframe không còn khớp. Tương tự, nếu người dùng mở GBP/USD thì mọi response EUR/USD cũ phải bị bỏ theo `session_id`.

---

## 13. File/module dự kiến thay đổi

| File/module | Thay đổi dự kiến |
|---|---|
| `core/live_chart_models.py` | Mới: request/result DTO và validation |
| `services/mt5_service.py` | Thêm `load_latest_bars()` dùng lock chung |
| `workers/live_chart_worker.py` | Mới: `LiveBarWorker` và `LiveAnalysisWorker`; chỉ phát signal |
| `controllers/scanner_controller.py` | Thêm entry point phân tích một-symbol side-effect-free; factor helper candidate evaluation nếu cần |
| `ui/screens/scanner_detail_screen.py` | Timer, session state, worker lifecycle, apply fast/slow result, show/hide |
| `ui/components/chart_view.py` | `update_live_bar()`, QWebChannel bridge, signal active timeframe |
| `ui/chart_bridge.py` | Script builder cho incremental update |
| `assets/chart/index.html` | `window.updateLiveBar`, giữ current-price line, bridge timeframe |
| `controllers/app_controller.py` | Chỉ sửa nếu quyết định tạo singleton controller riêng; không cần nếu dùng `app.scanner_controller` |
| `tests/test_mt5_service.py` | Test latest bars |
| `tests/test_live_chart_worker.py` | Mới: worker, DTO, error, stale metadata |
| `tests/test_chart_live_update.py` | Mới: bridge/script contract, không full redraw |
| `tests/test_scanner_detail_live_chart.py` | Mới: timer lifecycle, session guard, active timeframe, slow apply |
| `tests/test_scanner_detail_rerender.py` | Bổ sung regression nếu phù hợp |
| `tests/test_mt5_operation_serialization.py` | Chứng minh live fetch vẫn serialize với scan/order calls |

Không dự kiến sửa:

- QSS/style;
- các tab Chẩn đoán/AI ngoài việc chúng đọc snapshot mới sau slow refresh;
- logic indicator/scoring;
- màn hình Orders;
- dữ liệu hiển thị tĩnh;
- schema scanner persistence gốc.

---

## 14. Kế hoạch thực hiện theo từng bước

Mỗi bước phải có test trước khi chuyển sang bước kế tiếp.

### Bước 0 — Khóa baseline

1. Chạy toàn bộ test hiện hành:

   ```text
   pytest tests/ -x -q
   ```

2. Ghi nhận:
   - test pass/fail baseline;
   - thời gian chạy;
   - trạng thái MT5/WebEngine test có skip hay không.
3. Chụp một baseline thủ công:
   - mở scanner detail;
   - chọn từng timeframe;
   - zoom chart;
   - ghi nhận chart đứng yên sau 5–10 giây.
4. Không sửa test cũ chỉ để hợp thức hóa behavior mới.

**Điều kiện hoàn tất:** baseline có thể tái lập và không có lỗi không liên quan chưa được ghi nhận.

### Bước 1 — Tạo DTO và validation

1. Thêm `core/live_chart_models.py`.
2. Tạo request/result type cho fast và slow.
3. Chuẩn hóa:
   - timeframe uppercase;
   - UTC timestamps;
   - OHLC finite;
   - `high >= max(open, close, low)`;
   - `low <= min(open, close, high)`;
   - volume không âm.
4. Từ chối timeframe ngoài D1/H4/H1/M15.
5. Viết unit test cho dữ liệu hợp lệ/không hợp lệ.

**Điều kiện hoàn tất:** worker/UI không cần tự kiểm tra cấu trúc dict rải rác.

### Bước 2 — Thêm MT5 latest-bars API

1. Thêm `MT5Service.load_latest_bars()`.
2. Dùng decorator/lock hiện có.
3. Không tạo service MT5 mới trong worker.
4. Test:
   - đúng timeframe id;
   - `count=2`;
   - dữ liệu được map thành Candle UTC;
   - rates rỗng phát lỗi rõ ràng;
   - lời gọi serialize với operation khác.

**Điều kiện hoàn tất:** có thể lấy 2 nến mà không tải full history và không bypass lock.

### Bước 3 — Implement incremental JavaScript

1. Thêm `_currentPriceLine`.
2. Thêm `updateLiveBar(update)`.
3. Update cached payload và candlestick series.
4. Không gọi `_initChart()` trong function này.
5. Không gọi `setData()`.
6. Export `window.updateLiveBar`.
7. Thêm `chart_live_bar_script()` trong `ui/chart_bridge.py`.
8. Thêm `AnalysisChartView.update_live_bar()`.
9. Test script:
   - JSON escape an toàn;
   - function đúng tên;
   - không chứa lệnh full reset;
   - wrong timeframe bị bỏ ở JS contract.

**Điều kiện hoàn tất:** cập nhật cùng timestamp thay nến cuối; timestamp mới append nến; chart object không đổi.

### Bước 4 — Đồng bộ active timeframe

1. Tạo QWebChannel bridge trong `AnalysisChartView`.
2. Phát `active_timeframe_changed`.
3. Gọi bridge sau `switchTimeframe()` thành công.
4. Screen cập nhật `_active_chart_tf`.
5. Bỏ response timeframe cũ.
6. Test D1 → H1 → M15, bao gồm signal lặp.

**Điều kiện hoàn tất:** Python luôn biết timeframe đang hiển thị mà không poll bốn timeframe.

### Bước 5 — Tạo fast worker và fast polling

1. Tạo `LiveBarWorker(QObject)`.
2. Move worker sang dedicated fast `QThread`.
3. Tạo queued signal từ screen sang worker.
4. Implement in-flight guard.
5. Thêm fast `QTimer` 2.000 ms.
6. Implement `showEvent`, `hideEvent`, session invalidation.
7. Apply fast response qua `chart.update_live_bar()`.
8. Implement backoff.
9. Test:
   - timer chỉ chạy khi visible;
   - không overlap;
   - response symbol/session/timeframe/revision cũ bị bỏ;
   - worker không gọi GUI;
   - lỗi giữ chart cũ.

**Điều kiện hoàn tất:** nến hiện tại chạy live ổn định mà score/overlay không đổi.

### Bước 6 — Scheduler M15

1. Parse M15 timestamp cuối từ snapshot.
2. Thêm single-shot slow timer.
3. Tính boundary bằng UTC timestamp + 15 phút + 3 giây.
4. Xác nhận bar mới bằng latest-bars API.
5. Coalesce trigger từ fast M15 và slow timer.
6. Implement retry 2/5/15 giây.
7. Test:
   - mở trước boundary;
   - mở sau boundary;
   - MT5 chưa tạo bar mới;
   - market đóng;
   - trigger trùng;
   - session đổi giữa boundary check.

**Điều kiện hoàn tất:** mỗi M15 bar chỉ tạo tối đa một slow recalculation cho một session.

### Bước 7 — Tách single-symbol recalculation

1. Refactor context assembly từ scanner controller thành helper có thể tái sử dụng.
2. Tạo `LiveAnalysisWorker` trên một dedicated slow `QThread`.
3. Tạo public entry point side-effect-free.
4. Tách `analysis_m15_candles` khỏi `display_m15_candles`; không đưa bar M15
   đang hình thành vào scoring.
5. Chạy `analyze_symbol()` trên một symbol.
6. Tạo row bằng `scanner_row_from_analysis()`.
7. Chạy candidate evaluation thuần túy để display fields đồng bộ.
8. Gắn:
   - `snapshot_source`;
   - `parent_scan_id`;
   - `recalculated_at`;
   - `analysis_cutoff_m15_time`;
   - `new_forming_m15_time`;
   - context policy/stale flags;
   - latency metrics.
9. Test bằng mock:
   - không gọi Telegram;
   - không gọi persistence;
   - không gọi auto-trade;
   - không emit scanner events;
   - không thay input row;
   - M15 bar đang hình thành chỉ có trong chart payload, không có trong input
     scoring;
   - output chứa chart payload và decision đồng bộ.

**Điều kiện hoàn tất:** method có thể gọi độc lập mà không sinh bất kỳ side effect scanner nào.

### Bước 8 — Tích hợp slow snapshot vào detail

1. Giữ `_source_scan_row`.
2. Chuyển `self.row` sang live row bằng assignment nguyên tử.
3. Giữ active timeframe khi full payload mới được set.
4. Render toàn bộ read-only detail từ cùng row.
5. Audit save/export/AI audit.
6. Không cập nhật `ScannerScreen.scan_result`.
7. Test:
   - cards và chart đọc cùng `analysis_result`;
   - Entry/SL/TP trên chart khớp card;
   - quay lại scanner không đổi ranking;
   - mở lại row tạo session mới;
   - slow result cũ không ghi đè row mới.

**Điều kiện hoàn tất:** detail phản ánh analysis M15 mới nhưng scanner table vẫn là snapshot scan gốc.

### Bước 9 — Telemetry và trạng thái UI

1. Log ở mức debug/info:
   - fast request latency;
   - skipped timer count;
   - slow fetch/analysis latency;
   - stale response count;
   - failure/backoff count.
2. Nếu thêm trạng thái UI, dùng một label nhỏ không làm đổi layout card.
3. Không spam log mỗi 2 giây ở production nếu thành công; dùng sampling hoặc debug level.
4. Không log toàn bộ payload nến.

**Điều kiện hoàn tất:** có thể chẩn đoán lag/disconnect mà không tạo log quá lớn.

### Bước 10 — Kiểm thử đầy đủ và review

1. Chạy test tập trung.
2. Chạy:

   ```text
   pytest tests/ -x -q
   ```

3. Manual test với MT5:
   - D1/H4/H1/M15;
   - chuyển timeframe liên tục;
   - zoom/pan trong lúc fast update;
   - mở symbol khác khi request đang chạy;
   - rời detail 30 giây và kiểm tra không có poll;
   - ngắt/kết nối lại MT5;
   - chờ qua boundary M15;
   - xác minh Entry/SL/TP chỉ đổi sau slow refresh;
   - xác minh không có order/Telegram/snapshot mới.
4. Dùng profiler/log để xác minh không full redraw ở fast path.
5. Gửi diff để review trước commit.

---

## 15. Ma trận kiểm thử bắt buộc

### 15.1. Unit test

| Nhóm | Case |
|---|---|
| DTO | timeframe sai, OHLC sai, timestamp sai, NaN/Infinity |
| MT5 service | rates rỗng, 1 bar, 2 bars, mapping UTC, lock |
| Bridge | JSON Unicode/symbol đặc biệt, function đúng |
| Boundary | trước/sau boundary, weekend, retry |
| Session guard | session/symbol/timeframe/request mismatch |
| Candidate refresh | side/score/scenario đồng bộ, không mutate input |
| Closed M15 contract | pipeline dùng bar vừa đóng; chart vẫn có bar đang hình thành |

### 15.2. Qt/component test

| Case | Kỳ vọng |
|---|---|
| Detail hidden | timer dừng |
| Detail visible | request ngay + interval |
| Request đang chạy | tick tiếp theo bị skip |
| Chuyển timeframe | request cũ bị bỏ |
| Mở symbol mới | session mới, response cũ bị bỏ |
| Slow full snapshot | tăng revision; fast response của revision cũ bị bỏ |
| WebEngine unavailable/offscreen | không crash, worker/timer được kiểm soát |
| Slow result thành công | một full render |
| Slow result lỗi | snapshot cũ giữ nguyên |

### 15.3. JavaScript/manual

| Case | Kỳ vọng |
|---|---|
| Update cùng candle time | thân/râu nến đổi, số nến không tăng |
| New candle time | thêm đúng một nến |
| Older candle | bỏ |
| User zoom/pan | không reset khi fast update |
| Source zone toggle | không reset khi fast update |
| Slow full update | active timeframe được giữ |
| Theme refresh | chart vẫn hoạt động sau reload |

### 15.4. Safety regression

Mock/spies phải chứng minh live flow không gọi:

- `place_market_order*`;
- `execute_order_candidate`;
- Telegram service;
- scanner snapshot storage;
- scanner observability candidate event;
- AI market brief;
- auto-trade executor.

---

## 16. Ngân sách hiệu năng

Mục tiêu ban đầu:

| Chỉ số | Ngân sách |
|---|---|
| Fast MT5 calls | 1 call mỗi 2 giây cho một detail đang visible |
| Fast payload | Tối đa 2 candle + metadata |
| Fast GUI work | Một `runJavaScript()` nhỏ |
| Fast redraw | 0 full redraw |
| Fast overlap | 0 |
| Slow frequency | Tối đa 1 lần mỗi M15 bar/session |
| Slow full history | D1/H4/H1/M15, một symbol |
| Slow full redraw | 1 sau analysis success |
| Hidden-screen MT5 calls | 0 |

Không đặt hard timeout ngắn để kill MT5 thread. Dùng in-flight guard và telemetry để phát hiện operation chậm.

---

## 17. Rollout và rollback

### 17.1. Rollout đề xuất

1. Implement sau feature flag nội bộ, mặc định `false`.
2. Test fast layer độc lập trước; slow layer vẫn tắt.
3. Bật fast layer cho development.
4. Đo CPU, latency, chart stability.
5. Bật slow M15 refresh.
6. Sau khi ổn định mới cân nhắc mặc định `true`.

Feature flag có thể là code-level/config-level, nhưng không cần thêm UI setting trong phiên bản đầu.

### 17.2. Rollback

Rollback phải đơn giản:

- tắt feature flag;
- detail quay lại dùng snapshot scan;
- các API mới không ảnh hưởng scanner cũ;
- không cần migration dữ liệu;
- không cần sửa QSS;
- không thay schema snapshot gốc.

---

## 18. Tiêu chí nghiệm thu

Task chỉ được coi là hoàn tất khi tất cả điều kiện sau đạt:

1. Nến đang hình thành thay đổi trên chart trong vòng 2–4 giây khi MT5 có dữ liệu mới.
2. Fast update không gọi `_chart.remove()`, `_initChart()` hoặc `setData()`.
3. Zoom/pan không bị reset trong fast update.
4. Python nhận đúng timeframe khi người dùng bấm selector.
5. Hidden screen không gọi MT5.
6. Không có request fast chồng nhau.
7. Response cũ không thể ghi đè symbol/timeframe mới.
8. Pipeline chậm chỉ chạy khi có timestamp M15 mới.
9. EMA/SMC/Entry/SL/TP/score đổi cùng một snapshot sau slow success.
10. Slow failure không làm mất snapshot cũ.
11. Scanner table/ranking gốc không thay đổi.
12. Không có Telegram, auto-trade, persistence hoặc candidate event từ live detail.
13. Toàn bộ `pytest tests/ -x -q` pass.
14. Manual test disconnect/reconnect MT5 pass.
15. Diff được PO review trước commit.

---

## 19. Những cách triển khai bị cấm

AI Coder không được:

- gọi `run_market_scan()` mỗi 1–2 giây;
- gọi `build_full_chart_payload()` mỗi fast tick;
- gọi `setChartData()` mỗi fast tick;
- gọi `reloadChart()` mỗi fast tick;
- tải D1/H4/H1/M15 full history mỗi fast tick;
- gọi MT5 trực tiếp trong GUI thread;
- import SDK MetaTrader5 trong `ScannerDetailScreen`;
- tạo QThread mới cho mỗi timer tick;
- dùng `thread.terminate()`;
- mutate row đang nằm trong `scanner_result["rows"]`;
- áp dụng response mà không kiểm tra session/symbol/timeframe;
- tính EMA riêng trong JavaScript;
- chạy scoring trên nến đang hình thành mỗi 2 giây;
- rút gọn hoặc thay đổi dữ liệu Entry/SL/TP để làm nhẹ payload;
- coi live preview là tín hiệu đã được phép giao dịch.

---

## 20. Tài liệu và vị trí code tham chiếu

Code hiện tại cần đọc trước khi implement:

- `ui/screens/scanner_detail_screen.py`
  - `set_analysis_result()`
  - `_render()`
  - `_refresh_chart()`
  - `_run_ai_audit()`
  - `_export_json()`
  - `_save_to_journal()`
- `ui/components/chart_view.py`
  - `AnalysisChartView.set_payload()`
  - `_run_chart_script()`
  - `refresh_theme()`
- `ui/chart_bridge.py`
- `assets/chart/index.html`
  - `_clearChart()`
  - `_initChart()`
  - `_renderCandles()`
  - `setChartData()`
  - `switchTimeframe()`
- `services/mt5_service.py`
  - `_serialized_mt5_operation`
  - `load_ohlcv()`
  - `load_primary_timeframes()`
  - `get_live_price()`
- `controllers/scanner_controller.py`
  - `create_scan_worker()`
  - `run_market_scan()`
  - `_fetch_one_symbol_mt5()`
  - `_analyze_one_symbol()`
  - `_apply_scanner_filters()`
- `core/analysis_engine.py`
  - `analyze_symbol()`
- `core/analysis_pipeline.py`
  - `AnalysisPipeline.execute()`
  - `_assemble_result()`
- `core/chart_payload.py`
  - `build_chart_payload()`
  - `build_full_chart_payload()`
- `core/scanner.py`
  - `scanner_row_from_analysis()`
- `core/scanner_candidate_engine.py`
  - `evaluate_scanner_candidate()`

Tài liệu chính thức:

- MT5 Python integration: <https://www.mql5.com/en/docs/python_metatrader5>
- MT5 `copy_rates_from_pos`: <https://www.mql5.com/en/docs/python_metatrader5/mt5copyratesfrompos_py>
- MT5 `symbol_info_tick`: <https://www.mql5.com/en/docs/python_metatrader5/mt5symbolinfotick_py>
- MQL5 `OnTick`: <https://www.mql5.com/en/docs/event_handlers/ontick>
- Qt `QTimer`: <https://doc.qt.io/qt-6/qtimer.html>
- Qt Threads and QObjects: <https://doc.qt.io/qt-6/threads-qobject.html>
- Lightweight Charts realtime updates: <https://tradingview.github.io/lightweight-charts/docs>
- Lightweight Charts `ISeriesApi.update`: <https://tradingview.github.io/lightweight-charts/docs/api/interfaces/ISeriesApi>

---

## 21. Checklist bàn giao cho AI Coder

Trước khi code:

- [ ] Đọc toàn bộ tài liệu này.
- [ ] Đọc các file tham chiếu ở mục 20.
- [ ] Chạy test baseline.
- [ ] Xác nhận không có thay đổi không liên quan trong file dự kiến sửa.

Trong khi code:

- [ ] Giữ snapshot scan bất biến.
- [ ] MT5 qua singleton service và lock.
- [ ] Fast path dùng đúng 2 bars.
- [ ] Fast path dùng `series.update()`.
- [ ] Fast path không cập nhật indicator/scoring.
- [ ] Slow path chỉ chạy sau M15 timestamp mới.
- [ ] Slow method không có side effect.
- [ ] Mọi response có session guard.
- [ ] Timer dừng khi screen ẩn.
- [ ] Không force terminate thread.

Trước khi gửi review:

- [ ] Chạy test tập trung.
- [ ] Chạy `pytest tests/ -x -q`.
- [ ] Test thật với MT5.
- [ ] Xác minh không có order/Telegram/snapshot phát sinh.
- [ ] Gửi diff cụ thể.
- [ ] Mô tả kết quả đo latency/CPU.
- [ ] Không commit trước khi PO duyệt nếu workflow yêu cầu review trước commit.
