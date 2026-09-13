# Đặc tả dữ liệu SMC

Ngày: 2026-09-10. Trạng thái: DRAFT — chờ Tech Lead duyệt tại task 16. Tài liệu này khóa quy tắc dữ liệu cho các task sau; chưa thay đổi runtime.

## 1. Cutoff point-in-time

- Mỗi snapshot có một `as_of` duy nhất, bắt buộc là datetime timezone-aware UTC.
- Live Scanner đóng băng cutoff một lần trước history fetch ở `controllers/scanner_controller.py:_fetch_one_symbol_mt5` (tham số `capture_cutoff`, lưu thành `v4_captured_at` và `location_cutoff`). Không tạo cutoff mới theo từng timeframe, worker hoặc symbol.
- `derive_live_analysis(..., captured_at=...)` và mọi D1/H4/H1/M15 context dùng cùng `as_of`. Analyze/replay phải mang cutoff trong snapshot/provenance; không dùng `datetime.now()` để quyết định dữ liệu của snapshot đã bắt đầu.
- `observed_at`/thời điểm fetch là metadata freshness, không thay thế `as_of`.
- Chỉ candle có `close_at <= as_of` được dùng cho structure, zone, lifecycle, score hoặc projection. Dữ liệu đến sau cutoff không được tham gia.

## 2. Thời điểm mở và đóng nến

`Candle.time` là thời điểm mở nến. Nguồn MT5 chuyển epoch sang UTC tại `services/mt5_service.py:load_ohlcv`. Interval canonical lấy từ `_PRIMARY_TIMEFRAME_INTERVALS`:

| Timeframe | Interval | close_at | Vai trò |
|---|---:|---|---|
| D1 | 1 ngày | `time + 1 day` | Bối cảnh/structure cấp cao |
| H4 | 4 giờ | `time + 4 hours` | Structure và entry-zone candidate chính |
| H1 | 1 giờ | `time + 1 hour` | Candidate bổ sung/refinement |
| M15 | 15 phút | `time + 15 minutes` | Readiness/entry confirmation |

Quy tắc lọc:

1. Chuẩn hóa timestamp về UTC trước khi so sánh.
2. Nến forming bị loại nếu `close_at > as_of`; không cắt mù phần tử cuối của list.
3. Timestamp phải tăng nghiêm ngặt theo từng timeframe; duplicate theo open time là lỗi dữ liệu, không tạo bản ghi thứ hai.
4. OHLC phải hữu hạn và thỏa `high >= max(open, close)`, `low <= min(open, close)`, `high >= low`; không tự sửa nến sai.
5. Gap cuối tuần/giờ nghỉ hợp lệ không tự ghi là missing. Gap trong phiên kỳ vọng hoặc không xác định được session coverage phải giữ trạng thái thiếu/không chắc chắn, không chèn nến tổng hợp.
6. Nến thiếu ở cuối history không được thay bằng giá hiện tại hoặc nến forming.

## 3. Tick size và metadata giá

- Canonical `tick_size` là số dương từ broker symbol metadata `trade_tick_size`.
- Nếu broker không trả `trade_tick_size`, chỉ được fallback sang `point` dương và phải ghi provenance `tick_size_source=point_fallback`. Không suy ra tick size chỉ từ `digits`.
- Nếu cả hai thiếu/không hợp lệ, các rule dùng tick tolerance, gap minimum, break buffer hoặc price rounding không được coi là đã đánh giá đủ; trả `SMC_TICK_SIZE_UNAVAILABLE`.
- Nguồn hiện có: `services/mt5_service.py:execution_snapshot` đọc `trade_tick_size` rồi fallback `point`; `symbol_data_quality` hiện chưa đưa tick size vào payload nên integration sau phải thread metadata này, không tự chế tại scorer.
- Lưu `symbol`, `broker_symbol`, `tick_size`, `point`, `digits` và source cùng snapshot khi có. Tick size chỉ phục vụ lượng tử hóa/tolerance và không thay thế close của candle cho structure break.

## 4. ATR tham chiếu

- Công thức dùng implementation hiện có `core.indicators.atr`, period 14, cùng OHLC đã lọc cutoff.
- ATR formation/event là ATR của chính timeframe, tính trên prefix các nến đã đóng trước event candle; không dùng event candle, nến sau event, ATR cuối snapshot hoặc ATR bị look-ahead.
- Lưu `atr_reference`, `atr_reference_time`, timeframe và source event cùng zone/structure event. Giá trị này bất biến sau khi formation.
- ATR hiện tại dùng cho khoảng cách/revalidation có thể được tính ở cutoff mới, nhưng phải mang tên/field khác và không ghi đè ATR formation.
- `core/smc_context.py` hiện dùng `_latest_atr` và `core/technical_context.py` dùng latest H4 ATR/14-day average D1 ATR cho context hiện tại. Những giá trị này là current context; không được dùng thay event ATR khi triển khai detector mới.
- Warm-up: ATR(14) cần ít nhất 14 true ranges hợp lệ; nếu chưa đủ hoặc ATR không dương, trả `SMC_ATR_REFERENCE_UNAVAILABLE`. Không fallback sang ATR timeframe khác cho formation event.

## 5. Bảng required/optional và cách xử lý thiếu

| Timeframe | Required cho snapshot SMC | Minimum history hiện có | Required/optional cho entry | Khi thiếu hoặc không đủ |
|---|---|---:|---|---|
| D1 | Required cho core context/confluence; technical builder cần D1 | 60 nến cho technical; SMC detector tối thiểu 11 nhưng không đủ để thay core history | Required | `SMC_D1_MISSING`, `SMC_D1_INSUFFICIENT_HISTORY` hoặc `SMC_D1_COVERAGE_GAP`; không dựng bias mặc định |
| H4 | Required cho structure và entry-zone candidates; technical builder cần H4 | 60 nến cho technical; SMC detector tối thiểu 11 | Required | `SMC_H4_MISSING`, `SMC_H4_INSUFFICIENT_HISTORY` hoặc `SMC_H4_COVERAGE_GAP`; không chọn zone thiếu nguồn |
| H1 | Required cho structure/candidate bổ sung; technical builder cần H1 | 30 nến cho technical; SMC detector tối thiểu 11 | Required khi dùng H1 candidate/refinement | `SMC_H1_MISSING`, `SMC_H1_INSUFFICIENT_HISTORY` hoặc `SMC_H1_COVERAGE_GAP`; H1 thiếu không được giả lập bằng H4 |
| M15 | Optional để dựng/hiển thị setup và quality SMC cơ bản | 15 nến cho ATR-based M15 evaluator; scanner fetch hiện yêu cầu 100 nến | Required cho entry confirmation cần M15 | Thiếu/không đủ trả `M15_DATA_UNAVAILABLE` và trạng thái chờ/unknown; không READY cho entry cần M15, không tự đổi thành no-zone |

Diễn giải:

- “Required” là required để đánh giá đầy đủ luận điểm tương ứng, không có nghĩa mọi consumer phải crash. Consumer phải giữ result với data-quality state và reason cụ thể.
- D1/H4/H1 thiếu core data: fail-closed cho structure/zone/entry, không gán `up/down`, score tốt hoặc selected zone giả. Giữ được phần lịch sử độc lập chỉ khi result ghi rõ partial/unknown.
- M15 thiếu: vẫn cho phép hiển thị zone/quality đã đánh giá từ dữ liệu đủ, nhưng readiness/entry confirmation trả warning/WAITING theo contract; dùng reason hiện có `M15_DATA_UNAVAILABLE`.
- Minimum history ở trên là các ngưỡng code hiện tại (`MIN_D1=60`, `MIN_H4=60`, `MIN_H1=30`, SMC raw detector `_SMC_MIN_CANDLES=11`, M15 evaluator `_M15_MIN_CANDLES=15`). Ngưỡng lifetime/coverage đủ để dựng zone cũ sẽ được khóa trong bảng tham số task 8; nếu không có source formation trong history thì zone không usable, không coi là fresh.

## 6. Canonical data-quality reasons

Các reason sau là contract nội bộ để task 18 map vào model/result; reason chi tiết không được thay bằng giả định:

- `SMC_CUTOFF_MISSING`: không có cutoff snapshot.
- `SMC_CUTOFF_NAIVE`: cutoff không timezone-aware.
- `SMC_CANDLE_FORMING`: candle chưa đóng tại cutoff.
- `SMC_TIMESTAMP_INVALID`: timestamp thiếu, naive hoặc không parse được.
- `SMC_TIMESTAMP_ORDER_INVALID`: timestamp giảm hoặc duplicate.
- `SMC_OHLC_INVALID`: OHLC không hợp lệ/hữu hạn.
- `SMC_TIMEFRAME_MISSING`: thiếu nhóm timeframe.
- `SMC_INSUFFICIENT_HISTORY`: số nến dưới minimum của timeframe.
- `SMC_COVERAGE_GAP`: gap bất thường trong coverage cần thiết.
- `SMC_SESSION_COVERAGE_UNKNOWN`: không xác định được gap là nghỉ hợp lệ hay thiếu dữ liệu.
- `SMC_TICK_SIZE_UNAVAILABLE`: thiếu tick size/point hợp lệ.
- `SMC_ATR_REFERENCE_UNAVAILABLE`: thiếu warm-up hoặc ATR formation không hợp lệ.
- `M15_DATA_UNAVAILABLE`: compatibility reason cho consumer/readiness khi M15 thiếu.

Không tự chuyển các reason trên thành `no-zone`, `neutral` hoặc `READY`. Mỗi result phải phân biệt “không có tín hiệu trên dữ liệu đủ” với “không đủ dữ liệu để kết luận”.

## 7. Provenance bắt buộc

Snapshot/data-quality payload cần giữ tối thiểu:

`as_of`, `observed_at` (nếu có), symbol/broker symbol, timeframe, interval, first/last eligible candle close time, count raw/eligible, cutoff filtering result, tick-size metadata/source, ATR period/reference/source, session-coverage status và reason codes.

Tài liệu này là đầu vào để Tech Lead duyệt tại task 16; các thay đổi contract, ngưỡng hoặc fallback sau đó phải mở lại review tương ứng.
