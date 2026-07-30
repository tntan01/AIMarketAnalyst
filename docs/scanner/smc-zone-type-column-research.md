# Nghiên cứu thêm cột “Loại vùng” vào bảng Kết quả quét

> Phạm vi: nghiên cứu luồng dữ liệu và đề xuất phương án. Tài liệu này không bao gồm thay đổi code.

## Kết luận nhanh

- Cờ phân biệt nguồn vùng đã tồn tại dưới tên `entry_zone_source`.
- Giá trị `"fallback"` được gắn tại nhánh tạo vùng ATR giả lập trong `AnalysisPipeline._assemble_result()`.
- Field này đã được truyền lên từng scanner row, không cần đọc lại toàn bộ `analysis_result` để hiển thị.
- Bảng hiện không sort theo SMC/Fallback. UI tắt interactive sorting và giữ
  nguyên `execution_order` từ backend.
- Phương án B được chọn cho kiến trúc: giữ nguyên canonical
  `execution_order` cho auto-trade, AI Market Brief, Telegram, snapshot và
  observability; chỉ tạo `presentation_order` riêng trước khi nạp dữ liệu vào
  bảng UI.
- Vị trí đề xuất là helper thuần `ui/scanner_presentation.py`, được
  `ScannerScreen._scan_finished()` gọi trên display copies.
- Quyết định STT đã chốt: cột STT đọc `presentation_rank = 1..N`, được tính lại
  trong mỗi lần `ScannerTableModel.set_rows()`; execution `rank` vẫn giữ nguyên
  trên display-row copy nhưng không được dùng làm STT.
- Có `_sort_priority()` mang ý tưởng ưu tiên non-fallback nhưng hiện là code không được sử dụng.
- Logic nguồn vùng không hoàn toàn tập trung: có SMC, technical swing zone, ATR fallback, SMC watch-only fallback và backtest synthetic fallback. Cần chuẩn hóa semantics trước khi thêm cột.

## 1. Nguồn tạo vùng SMC và Fallback

### 1.1. Vùng SMC

Luồng chính nằm trong `core/smc_context.py`:

- `build_smc_context()` tại dòng 157 dựng SMC cho D1/H4/H1.
- `_smc_for_timeframe()` tại dòng 223 gọi các detector.
- `detect_fvg()` tại dòng 516.
- `detect_order_blocks()` tại dòng 557.
- `detect_supply_demand_zones()` tại dòng 605.
- `enrich_zones()` tại dòng 914 bổ sung score và lifecycle.

V2 đánh giá và chọn vùng tại:

- `evaluate_smc_zones()` trong `core/smc_scorer_v2.py`, dòng 60.
- `select_smc_zone_v2()` trong `core/smc_scorer_v2.py`, dòng 110.
- Vùng được chọn bởi V2 mang nguồn `"smc_v2_selected"` tại dòng 135.

Legacy selection nằm ở `get_preferred_zone()` trong `core/smc_context.py`, dòng 1298.

Không tìm thấy code detector cho Breaker/Breaker Block. Từ “Breaker” chỉ xuất hiện như yêu cầu tùy chọn trong `prompts/sections/technical_smc.md`, dòng 12; không có hàm sinh Breaker.

### 1.2. Fallback hiển thị của live scanner

Điểm quyết định chính xác nằm trong `AnalysisPipeline._assemble_result()` thuộc `core/analysis_pipeline.py`:

1. Nếu `_scenarios` rỗng nhưng còn ATR, giá và hướng hợp lệ, pipeline thử tìm SMC xa tại dòng 1446.
2. Nếu có vùng xa:
   - Tạo scenario với `"entry_zone_source": "smc_distant"` tại dòng 1492.
   - Comment tại dòng 1448 xác nhận đây vẫn là “real structure”, không phải ATR giả lập.
3. Nếu `distant_zone is None`, nhánh `else` tại dòng 1515 tạo:
   - Entry quanh giá hiện tại ± `0.25 ATR`.
   - SL `1.2 ATR`, TP `2.4 ATR`.
   - `entry_zone_score = 50`.
   - `"entry_zone_scoring_version": "non-smc-display-v1"`.
   - `"entry_zone_source": "fallback"` tại dòng 1540.

Kết quả cuối dùng `self._scenarios or fallback_scenarios` tại dòng 1638.

## 2. Cờ hiện có và tình trạng truyền dữ liệu

### 2.1. Field đã có

Field canonical hiện có là:

```text
entry_zone_source
```

Trong trade plan bình thường, giá trị được lấy từ `zone["source"]`, mặc định `"technical"` tại `core/risk_engine.py:780`, rồi ghi vào scenario tại `core/risk_engine.py:1341`.

`scanner_row_from_analysis()` trong `core/scanner.py`:

- Chọn `best_plan` đúng hướng tại dòng 124.
- Copy field lên scanner row tại dòng 239.
- Đồng thời giữ toàn bộ `analysis_result` tại dòng 256.

Vì vậy trong kết quả quét trực tiếp đã có:

```python
scan_result["rows"][i]["entry_zone_source"]
```

Không tìm thấy field vùng nào tên `is_fallback` hoặc `zone_source` ở scanner row. Các `is_fallback` khác trong codebase chủ yếu thuộc macro/news/backtest, không phải loại vùng của bảng quét.

`selected_zone_type` có nghĩa là loại cấu trúc như Order Block/FVG/demand/supply, không phải “SMC thật/Fallback”; không nên tái sử dụng tên này.

### 2.2. Các nguồn có thể gặp

- SMC thực: `"smc"`, `"smc_selected"`, `"smc_active_selected"`, `"smc_v2_selected"`.
- SMC thật nhưng ở xa, chỉ theo dõi: `"smc_distant"`.
- Vùng kỹ thuật swing: `"technical"`.
- ATR giả lập hiển thị: `"fallback"`.
- Không có plan/structural reject: `None` hoặc không có field.

Có một bất nhất sẵn có: `risk_engine` chỉ coi `"smc"` và `"smc_selected"` là SMC tại `core/risk_engine.py:790`, trong khi pipeline hiện có thể sinh `"smc_active_selected"` và `"smc_v2_selected"`. Logic cột mới không nên sao chép điều kiện thiếu này.

### 2.3. Persistence

Live `scan_result["rows"]` giữ field, nhưng snapshot dạng summary không giữ nó vì `SUMMARY_ROW_FIELDS` trong `services/scanner_persistence_service.py:24` chưa có `entry_zone_source`.

Snapshot full có thể lấy lại từ analysis document; snapshot summary định kỳ sẽ mất field. Nếu cột cần hoạt động khi nạp snapshot, whitelist cũng phải được cập nhật.

## 3. UI bảng “Kết quả quét”

File: `ui/screens/scanner_screen.py`.

Các class liên quan:

- `ScannerTableModel(QAbstractTableModel)` tại dòng 54.
- `ScannerScreen(QWidget)` tại dòng 712.

Bảng là `QTableView`, được gắn model tại dòng 1478.

### 3.1. Các cột hiện tại

`ScannerTableModel.COLUMNS` tại dòng 55 có 12 cột:

| Field | Tiêu đề |
|---|---|
| `rank` | STT |
| `symbol` | Mã |
| `candidate_status` | Trạng thái |
| `selected_side` | Hướng |
| `market_regime` | Bối cảnh TT |
| `setup_score` | Điểm thiết lập |
| `opportunity_rank` | Ưu tiên |
| `evidence_confidence` | Tin cậy LS |
| `execution_readiness` | Sẵn sàng |
| `expected_effective_rr` | R:R dự kiến |
| `auto_trade_branch` | Quy tắc |
| `strategy_config_status` | Cấu hình BT |

Không dùng DataFrame. Model giữ `rows: list[dict]`. `data()` lấy field tại dòng 113–120 bằng:

```python
key = self.COLUMNS[index.column()][0]
value = row.get(key)
```

Sau đó giá trị được format bằng `_display_value()`.

Khi scan xong, `ScannerScreen._scan_finished()` gọi thẳng `table_model.set_rows(rows)` tại dòng 1726–1732.

## 4. Sort hiện tại và toàn bộ consumer của ranking

UI không sort:

- `self.table.setSortingEnabled(False)` tại `ui/screens/scanner_screen.py:1489`.
- `_scan_finished()` ghi rõ backend sở hữu thứ tự canonical và UI không được re-rank.

### 4.1. Call site của `rank_scanner_rows()` và `sort_scanner_rows()`

Call site production:

| Call site | Vai trò | Thứ tự cần dùng |
|---|---|---|
| `controllers/scanner_controller.py:814` | `_apply_scanner_filters()` gọi `sort_scanner_rows(rows)` sau khi gắn candidate decision | `execution_order` canonical cũ |
| `core/scanner.py:442` | `sort_scanner_rows()` là compatibility wrapper gọi `rank_scanner_rows(rows)` | `execution_order` canonical cũ |
| `core/scanner.py:466` | `ai_targets()` tự gọi lại `rank_scanner_rows(rows)` trước khi lấy top N | `execution_order` canonical cũ; không dùng cho presentation UI |
| `core/scanner_observability.py:400` | `replay_candidate_decision()` rank lại một reconstructed row để đối chiếu ranking contract | Logic canonical cũ; không có ý nghĩa presentation |

Không tìm thấy call site production nào khác của `rank_scanner_rows()` hoặc
`sort_scanner_rows()`. `ai_targets()` không có call site ngoài định nghĩa trong
codebase hiện tại.

Call site test trực tiếp:

- `tests/test_scanner_phase6_ranking.py:49,69,88,118,126,142,186,203`.
- `tests/test_scanner_observability.py:226`.

Sort thật nằm tại `core/scanner_ranking_engine.py:803`; `rank` được đánh lại
liên tục tại dòng 804–805.

Thứ tự hiện tại:

1. `candidate_status` tăng dần theo priority:
   `READY_NOW → WAITING_CONFIRMATION → WATCH_ZONE → OUT_OF_STRATEGY → BLOCKED → DATA_UNAVAILABLE`.
2. `opportunity_rank` giảm dần.
3. `strategy_confidence` giảm dần.
4. `execution_readiness` giảm dần.
5. `expected_effective_rr` giảm dần.
6. `symbol` tăng dần.

`setup_score` không phải khóa sort trực tiếp; nó chiếm 55% công thức `opportunity_rank` tại `core/scanner_ranking_engine.py:695`.

Đáng chú ý: `_sort_priority()` tại `core/scanner.py:430` đã mô tả `ready=0, non-fallback=1, fallback=2`, nhưng không được gọi ở đâu. Chỉ sửa hàm này sẽ không thay đổi bảng.

### 4.2. Luồng dùng danh sách đã canonical-sort

Sau `ScannerController._apply_scanner_filters()` ở
`controllers/scanner_controller.py:615`, cùng danh sách `rows` theo
`execution_order` được chuyển tuần tự tới:

| Consumer | File + dòng | Cách dùng | Thứ tự phải giữ |
|---|---|---|---|
| AI Market Brief | `controllers/scanner_controller.py:651-655`; `core/scanner_session_review.py:32-42` | Lọc eligible theo đúng thứ tự input rồi lấy tối đa 8 row | `execution_order` cũ |
| Scanner output | `controllers/scanner_controller.py:665`; `core/scanner.py:553-577` | Gắn nguyên list vào `output["rows"]` | `execution_order` cũ; đây là nguồn để UI tạo bản trình bày riêng |
| Auto-trade | `controllers/scanner_controller.py:681-685,1278-1292` | Duyệt `for row in rows` và thử thực thi từng candidate | `execution_order` cũ |
| Telegram candidate | `controllers/scanner_controller.py:731,1436-1517,1581-1596` | Duyệt list để dựng candidates; service gửi theo thứ tự list | `execution_order` cũ |
| Telegram summary | `services/telegram_alert_service.py:135-164` | Tách ready/waiting nhưng giữ relative order trong từng nhóm | Relative `execution_order` cũ |
| Snapshot | `controllers/scanner_controller.py:734,1710-1749,1785-1806` | Lưu `result["rows"]` và `rank` | `execution_order` cũ |
| UI table | `ui/screens/scanner_screen.py:1726-1732` | Hiện gọi `set_rows()` trực tiếp | Consumer duy nhất cần `presentation_order` mới |

Auto-trade **không đọc field `rank` để quyết định candidate nào được duyệt
trước**. Đoạn `controllers/scanner_controller.py:1291` chỉ dùng thứ tự vật lý
của list:

```python
for row in rows:
```

Không có `sorted(... rank ...)`, so sánh `rank`, hoặc lookup theo `rank` trong
`_execute_auto_trades()`. Tuy nhiên điều này không có nghĩa thứ tự không quan
trọng: list truyền vào đã được canonical-sort tại dòng 814, nên sửa
`_canonical_sort_key()` vẫn đổi trực tiếp thứ tự auto-trade thử lệnh.
`build_candidate_order_payload()` copy `rank` vào payload như metadata tại
`core/scanner_candidate_engine.py:236`; field này không phải eligibility gate
hoặc sort key của auto-trade.

Docstring của `calculate_canonical_ranking()` tại
`core/scanner_ranking_engine.py:686-690` nói ranking “only ... for
presentation”, nhưng data flow thực tế cho thấy list đã rank còn đi vào
auto-trade, Brief và Telegram. Khi triển khai phải tin data flow/call site ở
trên, không dựa vào câu docstring này để kết luận canonical order chỉ là UI.

### 4.3. Các nơi tiêu thụ field `rank`

| Nơi dùng `rank` | File + dòng | Ý nghĩa |
|---|---|---|
| Placeholder trước ranking | `core/scanner.py:201,366` | Normal/blocked row khởi tạo `rank = 0` |
| Gán rank canonical | `core/scanner_ranking_engine.py:804-805` | Vị trí trong `execution_order` |
| AI Market Brief payload | `core/scanner_session_review.py:167-180` | Tham chiếu hạng backend trong top setup |
| Telegram candidate payload | `controllers/scanner_controller.py:1503-1513` | Copy rank backend |
| Telegram summary text | `services/telegram_alert_service.py:168-181` | Hiển thị `#rank` |
| Candidate order payload | `core/scanner_candidate_engine.py:236` | Metadata truy vết; không quyết định eligibility |
| UI cột STT | `ui/screens/scanner_screen.py:55-68` | Hiện hiển thị rank backend |
| UI dialog lệnh | `ui/screens/scanner_screen.py:1366-1387` | Copy rank từ row của `scan_result` |
| UI giải thích row | `ui/screens/scanner_screen.py:2299-2308,2439-2444` | Diễn giải rank là vị trí ưu tiên canonical |
| Export detail | `ui/screens/scanner_detail_screen.py:3446-3455` | Dùng rank trong tên file JSON |
| Snapshot summary | `services/scanner_persistence_service.py:24-34` | Whitelist và lưu rank backend |
| Full analysis document | `core/scanner_observability.py:327-352` | `row_summary` giữ toàn bộ row ngoài `analysis_result`, gồm rank |

Double-click, nút “Xem chi tiết” và help **không lookup row theo `rank`**:
chúng lấy row theo model index qua `row_at(index.row())` tại
`ui/screens/scanner_screen.py:1507-1524,1808-1833`. Vì vậy re-order list dành
riêng cho model vẫn mở đúng object, miễn không tách sai row khỏi dữ liệu của nó.

Observability replay tại `core/scanner_observability.py:400` rank một list chỉ
có một row và chỉ so sánh `opportunity_rank`/ranking contract tại dòng 403–425;
nó không so sánh rank toàn cục. Snapshot và analysis document vẫn cần giữ
`rank` execution gốc để truy vết nhất quán.

## 5. Phương án đề xuất

### 5.1. Data layer

Không cần thay đổi detector SMC hay `AnalysisPipeline` chỉ để hiển thị cột, vì raw provenance đã có.

Nên tạo một helper chuẩn hóa dùng chung trong module mới
`core/scanner_zone_origin.py`, sau đó bổ sung field đã chuẩn hóa vào
`scanner_row_from_analysis()`. Tên field mới:

```text
zone_origin_class = "smc" | "technical" | "fallback" | "none"
```

Không nên đặt là `zone_type` vì tên đó đã mang nghĩa OB/FVG.

Mapping đề xuất:

- `smc`: các nguồn `smc`, `smc_selected`, `smc_active_selected`, `smc_v2_selected`, `smc_distant`.
- `technical`: nguồn `technical`; đây là vùng swing kỹ thuật có thật nhưng không phải SMC.
- `fallback`: chỉ nguồn `fallback`; đây là vùng ATR giả lập để hiển thị khi không có vùng phù hợp.
- `none`: không có selected-side plan, data unavailable hoặc structural reject.
- Nguồn lạ: không tự coi là SMC; giữ `none/unknown` để fail-safe.

`smc_distant` nên hiển thị “SMC thật” vì đó là vùng SMC thật, dù chỉ theo dõi và không phải nguồn sạch để auto-trade.

`watch_only_fallback` trong `core/smc_context.py:1435` cũng vẫn là vùng SMC thật nhưng chất lượng thấp; chữ “fallback” ở đây không đồng nghĩa ATR fallback.

UI phải tách riêng “Technical” và “Fallback”. Structural reject/data unavailable
hiển thị `--` để không nói rằng hệ thống đã tạo một vùng khi thực tế không có
selected-side plan.

Field mới cần được thêm vào `SUMMARY_ROW_FIELDS` để snapshot summary không làm mất trạng thái.

### 5.2. UI layer

Trong `ScannerTableModel.COLUMNS`, thêm:

```python
("zone_origin_class", "Loại vùng")
```

Nên đặt sau “Bối cảnh TT” và trước “Điểm thiết lập”.

Trong `_display_value()` map:

- `"smc"` → `"SMC thật"`.
- `"technical"` → `"Technical"`.
- `"fallback"` → `"Fallback"`.
- `"none"` hoặc không có → `"--"`.

Các nơi UI phụ cần cập nhật:

- `column_configs` tại `ui/screens/scanner_screen.py:1975` để đặt min-width.
- `ScannerColumnsHelpDialog.COLUMN_HELP` tại `ui/screens/scanner_screen.py:2953`.
- Màu/tooltip nếu muốn phân biệt trực quan.

### 5.3. Sort

Áp dụng Phương án B: không sửa `rank_scanner_rows()`,
`_canonical_sort_key()` hoặc `SCANNER_RANKING_VERSION`.

Tách rõ hai thứ tự:

```text
execution_order
  candidate_status priority ASC
  opportunity_rank DESC
  strategy_confidence DESC
  execution_readiness DESC
  expected_effective_rr DESC
  symbol ASC

presentation_order (chỉ bảng UI)
  zone_origin_priority ASC
  relative execution_order không đổi trong cùng zone_origin_class
```

Priority trình bày:

```text
SMC thật = 0
Technical = 1
Fallback = 2
None/unknown = 3
```

`presentation_order` nên được tạo bằng **stable sort** chỉ theo
`zone_origin_priority` trên input đã ở `execution_order`. Tính ổn định của sort
giữ nguyên mọi khóa phụ canonical mà không cần import private
`_canonical_sort_key()` hoặc sao chép tuple sort sang UI.

Không thêm `setup_score` làm khóa presentation riêng. Trong từng nhóm nguồn,
thứ tự vẫn đúng canonical cũ và `setup_score` đã đóng góp vào
`opportunity_rank`.

#### Vị trí tính `presentation_order`

Ba vị trí khả thi:

| Vị trí | Ưu điểm | Nhược điểm |
|---|---|---|
| `ScannerTableModel.set_rows()` | Mọi caller của model tự động có cùng presentation order | Hidden side effect; model vừa lưu vừa áp policy; khó phân biệt input execution với output presentation; test fixture gọi `set_rows()` cũng bị re-order ngầm |
| `ScannerScreen._scan_finished()` gọi helper UI thuần | Boundary rõ: chỉ table bị re-order; `scan_result` vẫn canonical; dễ đọc data flow | Nếu viết inline sẽ khó unit test và làm file `scanner_screen.py` lớn hơn |
| Hàm mới trong `core/scanner.py` | Pure function, dễ test, không phụ thuộc PyQt | Đặt policy trình bày vào core; tên gần `sort_scanner_rows()` dễ bị consumer vận hành dùng nhầm; tăng nguy cơ presentation order rò sang auto-trade/Telegram/AI Brief |

Đề xuất kỹ thuật cho Phương án B là tạo module thuần
`ui/scanner_presentation.py` với
`sort_scanner_rows_for_display(execution_rows)`, rồi chỉ gọi helper này trong
`ScannerScreen._scan_finished()` trước `table_model.set_rows()`. Module nằm ở UI
nhưng không import PyQt, nên vẫn unit-test độc lập được.

Helper phải tạo list mới và row dict mới; không mutate `result["rows"]`:

```python
def sort_scanner_rows_for_display(execution_rows):
    display_rows = [
        dict(row)
        for row in execution_rows
        if isinstance(row, dict)
    ]
    return sorted(
        display_rows,
        key=lambda row: PRESENTATION_ZONE_ORIGIN_PRIORITY[
            zone_origin_from_row(row)
        ],
    )
```

`sorted()` của Python là stable. Contract đầu vào của helper phải ghi rõ:
`execution_rows` đã được backend canonical-sort. Không gọi lại
`rank_scanner_rows()` trong helper.

### 5.4. Contract STT đã chốt: dùng `presentation_rank`

Cột STT chỉ đọc field UI-only:

```text
presentation_rank = 1..N theo presentation_order
```

Contract bắt buộc:

1. `presentation_rank` chỉ được tạo trên display-row copy thuộc
   `ScannerTableModel.rows`.
2. `ScannerTableModel.set_rows()` phải tính lại field này trong mọi lần gọi,
   sau khi đã nhận list ở presentation order.
3. Cột STT dùng key `presentation_rank`, không dùng key `rank`.
4. Execution `rank` vẫn tồn tại nguyên giá trị trên cùng display-row dict để
   đối chiếu ngược; không overwrite, xóa hoặc đổi nghĩa field này.
5. `presentation_rank` không được ghi vào `scan_result["rows"]`, candidate
   payload, snapshot, observability, journal hoặc detail export.

Không gán `row["rank"] = index`, kể cả trên display copy. Cách đó làm row được
mở ở detail mang nghĩa rank khác backend; hiện detail dùng `rank` trong phần
giải thích và tên file export tại
`ui/screens/scanner_detail_screen.py:3452-3453`. Hai field riêng biệt giữ được
cả presentation position lẫn execution reference.

Tác động:

- Double-click vẫn mở đúng row vì dùng model index, không lookup bằng rank.
- Snapshot thủ công dùng `self.scan_result` tại
  `ui/screens/scanner_screen.py:1946-1950`, không dùng `table_model.rows`; do đó
  vẫn lưu execution order/rank nếu UI không mutate `scan_result`.
- Observability được dựng ở controller trước `_scan_finished()` và không nhận
  presentation list; không bị đổi.
- Dialog “Hiển thị lệnh” đọc `scan_result["rows"]` tại
  `ui/screens/scanner_screen.py:950-973`, nên tiếp tục dùng execution order/rank.
- Detail nhận display-row copy. Trước khi export JSON hoặc gửi sang journal,
  phải tạo payload copy và bỏ `presentation_rank`; nếu không field UI-only sẽ
  bị persist ngoài `table_model.rows`.

## 6. Rủi ro và vùng ảnh hưởng

### 6.1. Thứ tự backend được nhiều consumer dùng chung

`rank_scanner_rows()` không chỉ phục vụ UI. Nếu sửa canonical sort sẽ đổi:

- Top 8 gửi vào AI Market Brief tại `core/scanner_session_review.py:32`.
- Thứ tự Telegram và candidate preview.
- Thứ tự vòng lặp auto-trade tại `controllers/scanner_controller.py:1291`. Khi portfolio/risk state thay đổi sau từng lệnh, thứ tự có thể ảnh hưởng lệnh nào được xử lý trước.
- Field `rank` lưu trong snapshot và observability.

Phương án B loại rủi ro này bằng cách không truyền presentation list ngược về
controller/core và không mutate `scan_result["rows"]`. Rủi ro còn lại là một
developer sau này vô tình:

- sort trực tiếp `result["rows"]`;
- overwrite `rank` trên cùng row dict;
- dùng `table_model.rows` thay cho `scan_result["rows"]` trong dialog lệnh,
  snapshot hoặc một consumer vận hành mới;
- gọi helper presentation từ controller.

Test phải khóa các boundary trên, không chỉ kiểm tra output trực quan của bảng.

### 6.2. Có nhiều định nghĩa fallback

Backend `_is_fallback_row()` tại `core/scanner.py:414` yêu cầu tất cả scenario có nguồn đúng bằng `"fallback"`.

UI `_is_fallback_row()` tại `ui/screens/scanner_screen.py:225` coi mọi dòng không có scenario nguồn khác `None/"fallback"` là fallback.

Hai định nghĩa này khác nhau với:

- Dòng không có scenario.
- Mixed scenarios.
- Technical source.
- Nguồn mới chưa được nhận diện.

Nên thay bằng một helper chuẩn hóa dùng chung.

### 6.3. Code nhận diện vùng hiện có nhưng không được dùng

`_zone_tier()` tại `ui/screens/scanner_screen.py:190` đã phân biệt `smc/technical/fallback`, nhưng hiện không được gọi. Không nên xây cột mới trực tiếp dựa vào hàm dead này mà chưa chuẩn hóa semantics.

`_sort_priority()` tại `core/scanner.py:430` cũng không tham gia sort hiện tại.

### 6.4. Các trường hợp dễ gắn nhãn sai

- `technical` là vùng swing thật nhưng không phải SMC. Gắn nó “SMC thật” chỉ vì `entry_zone_source != "fallback"` sẽ sai.
- `"smc_distant"` là vùng SMC thật nhưng chỉ theo dõi.
- `watch_only_fallback` là SMC thật chất lượng thấp, không phải ATR fallback.
- Structural reject/data unavailable có thể không có plan; không nên mặc định tuyên bố đã có vùng fallback.
- Các source `"smc_active_selected"` và `"smc_v2_selected"` hiện chưa được mọi helper SMC nhận diện thống nhất.

### 6.5. Tests cần cập nhật hoặc bổ sung khi triển khai

- `tests/test_scanner_phase6_ranking.py:39`: contract sort canonical hiện tại
  phải giữ nguyên.
- `tests/test_scanner_phase6_ranking.py:125-162`: AI Brief và Telegram đã assert
  giữ backend order; giữ các test này làm regression.
- `tests/test_scanner_phase6_ranking.py:165-168`: test hiện cấm UI sort tuyệt
  đối; phải thay bằng contract “UI được presentation-sort nhưng không mutate
  execution rows/rank”.
- `tests/test_scanner_phase6_ranking.py:185-199`: dialog lệnh phải tiếp tục dùng
  backend candidate payload/order.
- `tests/test_entry_tp_quality_diagnostics.py:595-614`: giữ regression
  `entry_zone_source` không làm đổi opportunity score.
- `tests/test_scanner_columns_help_dialog.py:20`: đang assert đúng 12 cột.
- `tests/test_scanner_ui_rr_contract.py:106`: semantics fallback của UI.
- `tests/test_scanner_persistence_service.py:22`: whitelist summary.
- Cần test mới cho `sort_scanner_rows_for_display()` và test auto-trade nhận
  execution list gốc.
- Nên bổ sung matrix test cho mọi nguồn:
  - `smc`
  - `smc_selected`
  - `smc_active_selected`
  - `smc_v2_selected`
  - `smc_distant`
  - `technical`
  - `fallback`
  - `None`
  - nguồn lạ

## 7. Danh sách file dự kiến bị tác động khi triển khai

| File | Mục đích thay đổi |
|---|---|
| `core/scanner_zone_origin.py` | Module mới: contract và helper phân loại nguồn vùng |
| `core/scanner.py` | Chuẩn hóa `zone_origin_class` khi dựng scanner row |
| `ui/scanner_presentation.py` | Module mới: tạo presentation copy và stable-sort chỉ cho UI |
| `ui/screens/scanner_screen.py` | Gọi presentation helper trước `set_rows()`; tạo `presentation_rank`; thêm cột, format, kích thước và help |
| `ui/screens/scanner_detail_screen.py` | Loại `presentation_rank` khỏi detail export/journal payload |
| `services/scanner_persistence_service.py` | Giữ field trong snapshot summary |
| `tests/test_scanner_zone_origin.py` | Test unit cho contract phân loại mới |
| `tests/test_scanner_presentation.py` | Test stable presentation order, `presentation_rank = 1..N`, raw rank và immutability |
| `tests/test_scanner_phase6_ranking.py` | Giữ canonical order/rank; sửa contract UI; regression Brief/Telegram/dialog lệnh |
| `tests/test_scanner_execution_controller.py` hoặc test controller tương đương | Regression auto-trade nhận và duyệt execution order cũ |
| `tests/test_scanner_columns_help_dialog.py` | Cập nhật contract số cột/help |
| `tests/test_scanner_ui_rr_contract.py` | Kiểm thử mapping SMC/Technical/Fallback |
| `tests/test_scanner_persistence_service.py` | Kiểm thử persistence field mới |

`core/scanner_ranking_engine.py` và `core/scanner_models.py` **không nằm trong
danh sách file sửa của Phương án B**. Nếu implementation diff chạm hai file này,
phải dừng review và chứng minh lý do; không được đổi canonical sort hoặc bump
`SCANNER_RANKING_VERSION` trong feature này.

## 8. Kế hoạch triển khai chi tiết

Phần này là đặc tả triển khai. Một mô hình AI khác phải thực hiện đúng thứ tự,
đúng contract và đúng phạm vi dưới đây; không tự thay đổi semantics nếu chưa có
yêu cầu mới từ người dùng.

### 8.1. Quyết định kiến trúc đã chốt

1. Dùng `entry_zone_source` làm dữ liệu gốc; không sửa detector SMC để phục vụ
   riêng cho cột UI.
2. Tạo field chuẩn hóa mới tên `zone_origin_class`.
3. `zone_origin_class` có đúng bốn giá trị nội bộ:

   ```text
   smc
   technical
   fallback
   none
   ```

4. UI hiển thị:

   | `zone_origin_class` | Giá trị cột “Loại vùng” |
   |---|---|
   | `smc` | `SMC thật` |
   | `technical` | `Technical` |
   | `fallback` | `Fallback` |
   | `none` | `--` |

5. Giữ nguyên `execution_order` trong `rank_scanner_rows()`:

   ```text
   candidate_status_priority ASC
   opportunity_rank DESC
   strategy_confidence DESC
   execution_readiness DESC
   expected_effective_rr DESC
   symbol ASC
   ```

6. Tạo `presentation_order` chỉ tại boundary UI. Đây là stable sort theo priority:

   ```text
   smc = 0
   technical = 1
   fallback = 2
   none = 3
   ```

   Các row cùng `zone_origin_class` giữ nguyên relative `execution_order`.
7. Không sửa `core/scanner_ranking_engine.py`, không bump
   `SCANNER_RANKING_VERSION`, không gọi `rank_scanner_rows()` từ UI.
8. Không thêm `setup_score` làm khóa sort riêng trong phạm vi thay đổi này.
   `setup_score` đã là thành phần 55% của `opportunity_rank`; giữ nguyên các khóa
   sort phụ hiện tại để tránh làm mất ranking safety/evidence.
9. Không thay đổi điều kiện cho phép giao dịch, Strategy Router, Trade Gate,
   auto-trade eligibility, position sizing hoặc detector SMC.
10. Không dùng tên `zone_type` cho field mới vì tên đó đã mang nghĩa
    Order Block/FVG/demand/supply.
11. Cột STT bắt buộc dùng `presentation_rank = 1..N`. Field này chỉ tồn tại
    trong display-row copy của `ScannerTableModel.rows`; execution `rank` vẫn
    giữ nguyên trên cùng copy và trên toàn bộ data flow backend.

### 8.2. Contract phân loại bắt buộc

Tạo file mới `core/scanner_zone_origin.py`. Module này là nguồn sự thật duy nhất
cho việc đổi raw source thành loại vùng.

Module phải khai báo các constant tương đương:

```python
ZONE_ORIGIN_SMC = "smc"
ZONE_ORIGIN_TECHNICAL = "technical"
ZONE_ORIGIN_FALLBACK = "fallback"
ZONE_ORIGIN_NONE = "none"

VALID_ZONE_ORIGIN_CLASSES = frozenset({
    ZONE_ORIGIN_SMC,
    ZONE_ORIGIN_TECHNICAL,
    ZONE_ORIGIN_FALLBACK,
    ZONE_ORIGIN_NONE,
})

SMC_ENTRY_ZONE_SOURCES = frozenset({
    "smc",
    "smc_selected",
    "smc_active_selected",
    "smc_v2_selected",
    "smc_distant",
})

TECHNICAL_ENTRY_ZONE_SOURCES = frozenset({
    "technical",
})

FALLBACK_ENTRY_ZONE_SOURCES = frozenset({
    "fallback",
})
```

Hàm phân loại raw source phải có behavior chính xác:

```python
def classify_entry_zone_source(source: object) -> str:
    normalized = str(source or "").strip().lower()
    if normalized in SMC_ENTRY_ZONE_SOURCES:
        return ZONE_ORIGIN_SMC
    if normalized in TECHNICAL_ENTRY_ZONE_SOURCES:
        return ZONE_ORIGIN_TECHNICAL
    if normalized in FALLBACK_ENTRY_ZONE_SOURCES:
        return ZONE_ORIGIN_FALLBACK
    return ZONE_ORIGIN_NONE
```

Không dùng điều kiện `source != "fallback"` vì sẽ gắn nhãn sai cho
`"technical"`, `None` và source lạ.

Không dùng điều kiện `source.startswith("smc")` trong phiên bản đầu tiên. Dùng
allowlist giúp source mới không được tự động tuyên bố là SMC thật khi chưa được
kiểm chứng. Khi pipeline thêm một source SMC mới, phải cập nhật allowlist và test
trong cùng thay đổi.

Module nên có thêm helper đọc scanner row:

```python
def zone_origin_from_row(row: object) -> str:
    ...
```

Thứ tự đọc bắt buộc của helper:

1. Nếu `row` không phải `dict`, trả `none`.
2. Nếu `row["zone_origin_class"]` là một giá trị hợp lệ, trả giá trị đó.
3. Nếu row có `entry_zone_source`, phân loại trực tiếp field này.
4. Chỉ để tương thích payload cũ, có thể đọc
   `row["analysis_result"]["scenarios"]`:
   - Chỉ xét scenario có `type` hoặc `side` là `buy`/`sell`.
   - Ưu tiên scenario trùng `selected_side`.
   - Nếu `selected_side` không hợp lệ, thử `best_side`.
   - Nếu không tìm được hướng nhưng chỉ có đúng một directional scenario, dùng
     scenario đó.
   - Nếu có nhiều scenario mà không xác định được scenario được chọn, trả
     `none`; không tự lấy scenario đầu tiên.
5. Source thiếu, rỗng hoặc không nằm trong allowlist trả `none`.

Không đặt sort priority hoặc hàm sort presentation trong
`core/scanner_zone_origin.py`. Module core chỉ chuẩn hóa semantics; priority
trình bày được đặt trong `ui/scanner_presentation.py` để consumer vận hành không
vô tình dùng nhầm.

### 8.3. Bước 0 — Ghi nhận baseline trước khi sửa

Trước khi thay đổi code:

1. Kiểm tra `git status --short`; không đụng vào thay đổi không liên quan của
   người dùng.
2. Chạy các test mục tiêu hiện có:

   ```powershell
   pytest -q `
     tests/test_scanner_phase6_ranking.py `
     tests/test_scanner_columns_help_dialog.py `
     tests/test_scanner_ui_rr_contract.py `
     tests/test_scanner_persistence_service.py
   ```

3. Nếu baseline fail, ghi lại test fail trước khi sửa. Không “sửa ké” lỗi không
   liên quan trong task này.

Kết quả mong đợi của bước này là biết rõ baseline và bảo đảm các thay đổi sau có
thể được quy đúng cho feature “Loại vùng”.

### 8.4. Bước 1 — Tạo module chuẩn hóa nguồn vùng

File thực hiện: `core/scanner_zone_origin.py`.

Việc cần làm:

1. Thêm constants và hai helper theo contract tại mục 8.2.
2. Module không được import UI, controller, MT5, AI, network hoặc service.
3. Module không được import `core.scanner` hoặc
   `core.scanner_ranking_engine`, nhằm tránh circular import.
4. Hàm phải thuần, không mutate row/scenario truyền vào và không raise với dữ
   liệu bẩn.
5. Thêm docstring giải thích:
   - `smc_distant` vẫn là SMC thật.
   - `technical` là một loại riêng: vùng kỹ thuật có thật, không phải SMC và
     không phải ATR fallback.
   - `none` dùng cho missing/unknown/no-plan.

Ngay sau bước này, tạo `tests/test_scanner_zone_origin.py` và kiểm thử tối thiểu:

| Input source | Kết quả |
|---|---|
| `"smc"` | `smc` |
| `"smc_selected"` | `smc` |
| `"smc_active_selected"` | `smc` |
| `"smc_v2_selected"` | `smc` |
| `"smc_distant"` | `smc` |
| `"technical"` | `technical` |
| `"fallback"` | `fallback` |
| `None` | `none` |
| `""` | `none` |
| `"keyword_fallback"` | `none` |
| `"smc_future_unknown"` | `none` |

Test thêm cho `zone_origin_from_row()`:

- Ưu tiên field `zone_origin_class` hợp lệ.
- Fallback sang row-level `entry_zone_source`.
- Đọc selected-side scenario từ payload cũ.
- Không lấy bừa scenario đầu tiên khi có nhiều hướng nhưng không xác định được
  selected side.
- Không mutate input.

### 8.5. Bước 2 — Gắn field chuẩn hóa vào scanner row

File thực hiện: `core/scanner.py`.

Tại `scanner_row_from_analysis()`:

1. Sau khi xác định `best_plan` tại khoảng dòng 124, tạo biến:

   ```python
   entry_zone_source = (
       best_plan.get("entry_zone_source")
       if isinstance(best_plan, dict)
       else None
   )
   zone_origin_class = classify_entry_zone_source(entry_zone_source)
   ```

2. Trong row dict:
   - Giữ nguyên raw field `entry_zone_source`.
   - Thêm `"zone_origin_class": zone_origin_class`.
3. Không suy ra loại vùng từ toàn bộ danh sách scenario; row phải đại diện cho
   đúng `best_plan`/selected side đang được bảng hiển thị.
4. Không thay đổi cách chọn `best_plan`.

Tại `blocked_scanner_row()`:

1. Thêm `"entry_zone_source": None`.
2. Thêm `"zone_origin_class": "none"`.

Đối với `_is_fallback_row()` cũ:

- Có thể giữ hàm để tương thích, nhưng implementation phải delegate sang
  `zone_origin_from_row(row) == "fallback"`.
- Không dùng lại logic “tất cả scenarios có source fallback”.

Đối với `_sort_priority()` cũ:

- Không wire hàm này vào canonical sort hoặc presentation sort.
- Giữ nguyên để tránh mở rộng scope; cleanup/deprecation là task riêng.
- Tuyệt đối không sửa `_canonical_sort_key()` trong Phương án B.

Test cần bổ sung vào test scanner phù hợp:

- Scenario `smc_v2_selected` tạo row có `zone_origin_class == "smc"`.
- Scenario `smc_distant` tạo row có `zone_origin_class == "smc"`.
- Scenario `technical` tạo row có `zone_origin_class == "technical"`.
- Scenario `fallback` tạo row có `zone_origin_class == "fallback"`.
- Không có best plan tạo `none`.
- Blocked row luôn là `none`.

### 8.6. Bước 3 — Tạo presentation sort riêng cho UI

File mới: `ui/scanner_presentation.py`.

Module phải là pure Python, không import PyQt và không import private API
`_canonical_sort_key`. Khai báo priority chỉ dành cho presentation:

```python
PRESENTATION_ZONE_ORIGIN_PRIORITY = {
    "smc": 0,
    "technical": 1,
    "fallback": 2,
    "none": 3,
}
```

Tạo hàm:

```python
def sort_scanner_rows_for_display(
    execution_rows: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    if not isinstance(execution_rows, list):
        return []
    display_rows = [
        dict(row)
        for row in execution_rows
        if isinstance(row, dict)
    ]
    return sorted(
        display_rows,
        key=lambda row: PRESENTATION_ZONE_ORIGIN_PRIORITY[
            zone_origin_from_row(row)
        ],
    )
```

Đoạn trên mô tả contract, implementation có thể viết rõ ràng hơn để tránh
comprehension hai tầng. Behavior bắt buộc:

1. Input là `None` hoặc không phải list thì trả `[]`.
2. Bỏ phần tử không phải dict theo cùng tinh thần của ranking engine hiện tại.
3. Tạo list mới và `dict(row)` mới; không mutate list/dict trong
   `scan_result["rows"]`.
4. Chỉ sort theo presentation priority.
5. Dựa vào stable sort để giữ nguyên relative execution order trong cùng class.
6. Không gọi `rank_scanner_rows()` hoặc `sort_scanner_rows()`.
7. Không thêm/sửa `candidate_status`, `opportunity_rank`, `ranking_contract`,
   `ranking_version` hoặc `rank`.
8. Không đọc `setup_score` làm khóa sort.

Ghi docstring/precondition rõ: caller phải truyền list đã canonical-sort từ
backend. Helper này không có trách nhiệm tính lại execution order.

Tạo `tests/test_scanner_presentation.py` với các case tối thiểu:

1. Input execution order có class trộn lẫn được trả thành
   `smc → technical → fallback → none`.
2. Trong từng class, thứ tự symbol và `rank` giống hệt relative order input.
3. Một Technical rank 1 và SMC rank 3 phải hiển thị SMC trước nhưng cả hai vẫn
   giữ raw `rank` lần lượt 3 và 1; `ScannerTableModel.set_rows()` sau đó gắn
   `presentation_rank` liên tục theo vị trí hiển thị.
4. Input list, từng source dict và nested payload không bị mutate.
5. Missing/unknown class đi về `none`, không crash.
6. `SCANNER_RANKING_VERSION` vẫn là `"phase6-ranking-v1"`.

Không sửa hoặc bổ sung zone priority vào:

- `core/scanner_ranking_engine.py`;
- `core/scanner_models.py`;
- `ranking_contract`;
- `ranking_score_breakdown`.

### 8.7. Bước 4 — Áp presentation order và thêm cột UI

File thực hiện: `ui/screens/scanner_screen.py`.

Trong `ScannerScreen._scan_finished()`:

```python
self.scan_result = result
execution_rows = list(result.get("rows", []))
presentation_rows = sort_scanner_rows_for_display(execution_rows)
self.table_model.set_rows(presentation_rows)
```

Ràng buộc:

1. Chỉ `presentation_rows` được truyền vào `ScannerTableModel`.
2. Không gán `result["rows"] = presentation_rows`.
3. Không gán `self.scan_result["rows"] = presentation_rows`.
4. Không sort in-place `execution_rows` hoặc source row dict.
5. `self.scan_result` phải tiếp tục giữ object backend gốc để snapshot, dialog
   lệnh và detail context dùng execution order.
6. Giữ `self.table.setSortingEnabled(False)`; presentation order là policy cố
   định, không phải interactive header sort.

Trong `ScannerTableModel.COLUMNS`:

1. Thay cột STT hiện tại:

   ```python
   ("rank", "STT")
   ```

   bằng:

   ```python
   ("presentation_rank", "STT")
   ```

2. Thêm cột loại vùng:

   ```python
   ("zone_origin_class", "Loại vùng")
   ```

3. Vị trí chính xác: sau `("market_regime", "Bối cảnh TT")` và trước
   `("setup_score", "Điểm thiết lập")`.
4. Tổng số cột sau thay đổi là 13.

Trong `ScannerTableModel.set_rows()`:

```python
def set_rows(self, rows):
    self.beginResetModel()
    display_rows = []
    for source in rows:
        if not isinstance(source, dict):
            continue
        display_row = dict(source)
        display_row.pop("presentation_rank", None)
        display_row["presentation_rank"] = len(display_rows) + 1
        display_rows.append(display_row)
    self.rows = display_rows
    self.endResetModel()
```

Behavior bắt buộc:

1. Tạo một top-level dict copy mới cho từng row; không giữ source dict để rồi
   gắn field UI vào đó.
2. Xóa mọi `presentation_rank` do caller truyền vào và luôn tính lại từ đầu.
3. Giá trị trong `self.rows` phải liên tục `1..N` theo đúng list presentation
   được truyền vào.
4. Giữ nguyên `display_row["rank"]` từ source.
5. Không ghi display row trở lại `scan_result`, `result["rows"]` hoặc
   `presentation_rows` đầu vào.
6. Nếu có phần tử không phải dict, bỏ phần tử đó trước khi đánh số để không tạo
   lỗ hổng trong dãy `1..N`.

Trong `_display_value()`:

```python
if key == "zone_origin_class":
    return {
        "smc": "SMC thật",
        "technical": "Technical",
        "fallback": "Fallback",
        "none": "--",
    }.get(str(value or "").strip().lower(), "--")
```

Không hiển thị raw source như `"smc_v2_selected"` trực tiếp trong ô.

Trong `_foreground()`:

- `smc`: dùng màu success.
- `technical`: dùng màu warning.
- `fallback`: dùng màu muted.
- `none`: dùng màu muted/subtle.
- Không hard-code mã màu mới nếu palette đã có semantic color.

Trong `_configure_table_columns()`:

- Thêm config cho `zone_origin_class`, ví dụ min-width đủ để không cắt
  `"SMC thật"`, `"Technical"` và `"Fallback"`.
- Vẫn để cơ chế dynamic content width quyết định kích thước cuối.

Trong `ScannerColumnsHelpDialog.COLUMN_HELP`:

1. Thêm entry ở đúng vị trí tương ứng với cột.
2. Nội dung phải giải thích:
   - “SMC thật” là vùng SMC canonical hoặc SMC distant thực.
   - “Technical” là vùng swing kỹ thuật thực nhưng không phải SMC.
   - “Fallback” chỉ là vùng ATR display fallback khi không có vùng phù hợp.
   - `--` là không có selected-side plan hoặc dữ liệu không đủ.
3. `COLUMN_HELP` phải giữ thứ tự và số lượng trùng tuyệt đối
   `ScannerTableModel.COLUMNS`.

Contract cột STT:

- Chỉ hiển thị `presentation_rank`.
- `presentation_rank` là số thứ tự dòng trên bảng, không phải mức chất lượng hay
  execution priority.
- Raw `rank` vẫn giữ trên display row để phần kỹ thuật/detail có thể đối chiếu,
  nhưng không được dùng làm giá trị cột STT.
- `rank` trong `scan_result`, candidate payload, snapshot, Brief, Telegram,
  observability và auto-trade phải không đổi.

Các điểm UI liên quan:

- Đổi config kích thước cột từ key `rank` sang `presentation_rank`; vẫn giữ
  min-width phù hợp cho STT.
- Help của cột STT phải giải thích đây là số dòng `1..N` theo thứ tự hiển thị
  SMC/Technical/Fallback/none.
- Phần kỹ thuật trong `ScannerRowExplanationDialog` có thể tiếp tục hiển thị
  raw `rank`, nhưng phải đổi label thành “Hạng vận hành” để không nhầm với STT.
- Trong `ScannerDetailScreen._export_json()` tại
  `ui/screens/scanner_detail_screen.py:3446-3455`, loại
  `presentation_rank` khỏi payload export.
- Trong `_save_to_journal()` tại
  `ui/screens/scanner_detail_screen.py:3457-3460`, gửi một row copy đã bỏ
  `presentation_rank`; không mutate row đang hiển thị.

Đối với `_has_real_plan()`, `_is_fallback_row()` và `_zone_tier()`:

- `_is_fallback_row()` phải dùng shared `zone_origin_from_row()`.
- `_is_fallback_row()` chỉ trả `True` khi class là `fallback`; không gộp
  `technical` hoặc `none`.
- `_has_real_plan()` trả `True` khi class thuộc `{smc, technical}` vì cả hai đều
  có vùng giá thật. Hàm này trả `False` với `{fallback, none}`.
- Các ô RR/price-vs-zone cần ẩn khi `not _has_real_plan(row)`, thay vì suy ra
  bằng điều kiện raw source.
- `_zone_tier()` hiện không được gọi; không dùng nó làm nguồn cho cột. Có thể
  giữ nguyên ngoài scope hoặc xóa trong một cleanup riêng, không trộn vào feature
  nếu không cần thiết.

UI vẫn phải giữ:

```python
self.table.setSortingEnabled(False)
```

nhưng `_scan_finished()` phải gọi
`set_rows(sort_scanner_rows_for_display(execution_rows))`, không gọi trực tiếp
`set_rows(execution_rows)`.

### 8.8. Bước 5 — Giữ field trong snapshot summary

File thực hiện: `services/scanner_persistence_service.py`.

Thêm vào `SUMMARY_ROW_FIELDS`:

```python
"entry_zone_source",
"zone_origin_class",
```

Lý do giữ cả hai:

- `entry_zone_source`: provenance/raw diagnostics.
- `zone_origin_class`: field ổn định phục vụ render và sort.

Không cần bump `persistence_schema_version` trong phạm vi feature này vì đây là
field optional được thêm theo hướng backward-compatible; code đọc snapshot cũ
phải chấp nhận field thiếu và resolver sẽ trả `none`.

Test bắt buộc:

- `summary_row()` giữ đúng hai field mới.
- Vẫn loại `analysis_result`, candle data và observability payload.
- Snapshot cũ thiếu field không làm UI/ranking crash.

### 8.9. Bước 6 — Cập nhật test UI và contract hiện có

Files tối thiểu:

- `tests/test_scanner_presentation.py`
- `tests/test_scanner_columns_help_dialog.py`
- `tests/test_scanner_ui_rr_contract.py`
- `tests/test_scanner_phase6_ranking.py`
- test controller chứa auto-trade regression
- `tests/test_scanner_persistence_service.py`

Thay đổi cụ thể:

1. Sửa assertion số cột từ 12 thành 13.
2. Vẫn assert help labels bằng chính xác labels trong `ScannerTableModel.COLUMNS`.
3. Thêm test display:
   - `smc` → `SMC thật`.
   - `technical` → `Technical`.
   - `fallback` → `Fallback`.
   - `none`, missing và invalid → `--`.
4. Thêm test màu bằng semantic palette, không assert màu tùy ý ngoài contract
   theme hiện có.
5. Giữ mọi expectation `ranking_version == "phase6-ranking-v1"`.
6. Thay `test_ui_does_not_sort_or_reassign_backend_rank()` tại
   `tests/test_scanner_phase6_ranking.py:165` bằng test behavior:
   - UI/model nhận presentation order;
   - `result["rows"]` vẫn giữ execution order;
   - raw `rank` không đổi;
   - không gọi canonical ranker lần hai.
7. Giữ nguyên và tăng độ rõ của:
   - `test_market_brief_preserves_backend_rank_order()` tại dòng 125;
   - `test_telegram_candidates_preserve_the_same_backend_order()` tại dòng 141;
   - `test_ui_order_dialog_reuses_backend_candidate_payload()` tại dòng 185.
8. Thêm regression auto-trade với hai candidate đủ điều kiện có
   `zone_origin_class` ngược priority presentation. Dùng spy/mock
   `execute_order_candidate()` ghi lại symbol và assert thứ tự call đúng input
   execution list/rank, không phải `smc → technical → fallback`.
9. Test STT đã chốt:
   - `ScannerTableModel.COLUMNS` dùng `presentation_rank` cho cột `STT` và không
     dùng `rank`;
   - sau mỗi lần `set_rows()`,
     `[row["presentation_rank"] for row in model.rows] == [1, ..., N]`;
   - gọi `set_rows()` lần hai với list khác phải tính lại từ 1, không tái sử
     dụng giá trị cũ hoặc giá trị caller truyền vào;
   - `[row["rank"] for row in model.rows]` vẫn đúng raw execution ranks tương
     ứng, kể cả khi không liên tục hoặc khác presentation rank;
   - source row dict, `scan_result["rows"]` và payload truyền vào `set_rows()`
     không bị thêm `presentation_rank`;
   - snapshot full/summary và analysis/observability document không chứa key
     `presentation_rank`;
   - detail export và journal payload không chứa `presentation_rank`.

### 8.10. Bước 7 — Kiểm thử tích hợp và regression

Chạy test mục tiêu:

```powershell
pytest -q `
  tests/test_scanner_zone_origin.py `
  tests/test_scanner_presentation.py `
  tests/test_scanner_phase6_ranking.py `
  tests/test_scanner_execution_controller.py `
  tests/test_scanner_columns_help_dialog.py `
  tests/test_scanner_ui_rr_contract.py `
  tests/test_scanner_persistence_service.py `
  tests/test_scanner_observability.py
```

Sau khi nhóm mục tiêu pass, chạy regression rộng:

```powershell
pytest -q tests
```

Nếu full suite quá lâu, tối thiểu phải chạy thêm các nhóm:

```powershell
pytest -q `
  tests/test_scanner_strategy*.py `
  tests/test_scanner_candidate*.py `
  tests/test_analysis_pipeline_integration.py `
  tests/test_smc_scorer_v2.py `
  tests/test_smc_consumer_phase6.py
```

Lưu ý PowerShell không tự expand wildcard theo cách giống Bash cho mọi chương
trình. Nếu pytest không nhận wildcard, lấy danh sách bằng `rg --files tests` rồi
truyền từng file scanner liên quan, hoặc chạy cả `tests`.

### 8.11. Bước 8 — Kiểm tra thủ công UI

Mở màn hình “Quét thị trường” và xác nhận:

1. Header “Loại vùng” nằm giữa “Bối cảnh TT” và “Điểm thiết lập”.
2. Header và cell không bị cắt ở DPI/độ rộng cửa sổ phổ biến.
3. Row có `smc_v2_selected`, `smc_active_selected`, `smc_selected`, `smc` hoặc
   `smc_distant` hiển thị “SMC thật”.
4. Row nguồn `technical` hiển thị “Technical”.
5. Row nguồn `fallback` hiển thị “Fallback”.
6. Row data unavailable/structural reject hiển thị `--`.
7. Tất cả row “SMC thật” nằm trên row “Technical”.
8. Tất cả row “Technical” nằm trên row “Fallback”.
9. Tất cả row “Fallback” nằm trên row `--`.
10. Cột STT hiển thị liên tục `1..N` theo presentation order; raw execution
    `rank` vẫn còn nguyên trên cùng display row nhưng không được dùng làm STT.
11. Double-click và nút “Xem chi tiết” vẫn mở đúng row sau khi thứ tự thay đổi.
12. Dialog “Hiển thị lệnh” vẫn theo execution order, không theo thứ tự bảng.
13. Save snapshot và mở dữ liệu summary không mất `zone_origin_class`; order và
    rank trong snapshot vẫn là execution order/rank.
14. Chế độ light/dark đều có màu chữ đọc được.

### 8.12. Bước 9 — Xác nhận presentation order không rò sang downstream

Phương án B chỉ thành công khi mọi consumer vận hành vẫn nhận đúng list canonical
trước feature. Kiểm tra:

1. AI Market Brief vẫn nhận top setup theo `execution_order` cũ và giữ nguyên
   execution `rank`.
2. Telegram order alerts/candidates vẫn theo `execution_order`; summary giữ
   relative execution order trong nhóm ready/waiting; `#rank` không đổi.
3. Auto-trade vẫn nhận cùng list đã sort tại
   `ScannerController._apply_scanner_filters()` và duyệt symbol theo thứ tự cũ.
   Không chỉ assert eligibility; phải dùng spy để assert thứ tự call
   `execute_order_candidate()`.
4. Fallback ATR vẫn bị Strategy Router đánh dấu `FALLBACK_ENTRY_ZONE`.
5. `technical` được hiển thị riêng là “Technical” nhưng không được tự động thêm
   một block giao dịch mới trong task này; thay đổi eligibility của technical
   source là quyết định nghiệp vụ riêng.
6. `build_scanner_output()` và `self.scan_result["rows"]` vẫn chứa execution
   list; chỉ `table_model.rows` chứa presentation list và
   `presentation_rank`.
7. Snapshot full/summary vẫn lưu execution order/rank và không lưu
   `presentation_rank`.
8. Observability replay vẫn dùng `"phase6-ranking-v1"` và tái tạo cùng
   `opportunity_rank`/ranking contract. Không viết test giả định replay một row
   có thể xác nhận global rank, vì code hiện không so sánh điều đó.
9. `core/scanner_ranking_engine.py`, `_canonical_sort_key()` và
   `SCANNER_RANKING_VERSION` không thay đổi trong diff.

Nếu bất kỳ downstream nào nhận presentation list, không đơn giản hóa bằng cách
quay lại sửa canonical sort. Dừng triển khai, tìm chỗ alias/mutation của
`result["rows"]` hoặc row dict và giữ đúng boundary
`scan_result → execution`, `table_model → presentation`.

### 8.13. Tiêu chí nghiệm thu

Feature chỉ được coi là hoàn tất khi thỏa tất cả điều kiện:

- [x] Mỗi live scanner row có `entry_zone_source` và `zone_origin_class`.
- [x] Blocked/no-plan row có `zone_origin_class == "none"`.
- [x] Không có logic UI tự đoán SMC bằng điều kiện `source != "fallback"`.
- [x] Cột “Loại vùng” xuất hiện đúng vị trí và hiển thị đúng bốn trạng thái.
- [x] SMC sources trong allowlist luôn hiển thị “SMC thật”.
- [x] `technical` luôn hiển thị “Technical”.
- [x] `"fallback"` luôn hiển thị “Fallback”.
- [x] Missing/unknown source hiển thị `--`, không bị nhận nhầm là SMC.
- [x] `execution_order` vẫn đúng canonical cũ:
      `candidate_status → opportunity_rank → strategy_confidence →
      execution_readiness → expected_effective_rr → symbol`.
- [x] Chỉ `presentation_order` của bảng là
      `smc → technical → fallback → none`; relative execution order trong mỗi
      class không đổi.
- [x] Cột STT đọc `presentation_rank` và hiển thị liên tục `1..N` theo
      presentation order sau mỗi lần `set_rows()`.
- [x] Mỗi display row vẫn giữ execution `rank` gốc, không bị overwrite bởi
      `presentation_rank`.
- [x] Auto-trade duyệt cùng symbol order và rank như trước feature.
- [x] AI Market Brief top setup order/rank không đổi so với trước feature.
- [x] Telegram candidate/summary relative order và rank không đổi so với trước
      feature.
- [x] `SCANNER_RANKING_VERSION == "phase6-ranking-v1"` và ranking contract
      không đổi.
- [x] Snapshot summary giữ raw source và normalized class.
- [x] Snapshot/observability giữ execution rank; không chứa
      `presentation_rank`.
- [x] Detail export và journal payload không chứa `presentation_rank`.
- [x] `presentation_rank` chỉ tồn tại trong display-row copies của
      `table_model.rows`.
- [x] `scan_result["rows"]` không bị mutate; chỉ `table_model.rows` được
      presentation-sort và đánh presentation rank.
- [x] UI không bật interactive sort và không gọi canonical ranker.
- [x] `core/scanner_ranking_engine.py` và `core/scanner_models.py` không bị sửa.
- [x] Có regression test chứng minh auto-trade/AI Brief/Telegram rank và order
      không đổi.
- [x] Test mục tiêu pass.
- [x] Regression scanner/SMC pass.
- [x] Không thay đổi detector, trade gate hoặc auto-trade eligibility.

### 8.14. Phạm vi không thực hiện

Không thực hiện các việc sau trong feature này:

- Không thêm detector Breaker Block.
- Không sửa thuật toán phát hiện FVG/Order Block/supply/demand.
- Không đổi ngưỡng điểm SMC.
- Không đổi cách chọn best side hoặc best plan.
- Không biến `smc_distant` thành auto-trade eligible.
- Không đổi `watch_only_fallback` thành ATR fallback.
- Không đổi điều kiện Strategy Router đối với `technical`.
- Không sửa canonical sort, opportunity score hoặc ranking contract.
- Không bump `SCANNER_RANKING_VERSION`.
- Không dùng presentation order cho auto-trade, AI Market Brief, Telegram,
  dialog lệnh, snapshot hoặc observability.
- Không overwrite field `rank` để tạo STT hiển thị.
- Không thêm sort click theo header trong UI.
- Không sửa các fallback không liên quan như macro, news, network hoặc synthetic
  backtest fallback.

### 8.15. Trình tự commit/triển khai khuyến nghị

Nếu chia nhỏ để review, thực hiện theo thứ tự:

1. Contract/helper `scanner_zone_origin` và unit test.
2. Gắn field vào scanner row và blocked row.
3. Presentation helper thuần trong `ui/scanner_presentation.py` và unit test.
4. Tích hợp presentation helper, thêm `presentation_rank` trong
   `ScannerTableModel.set_rows()`, đổi cột STT và cập nhật UI/help tests.
5. Persistence summary và persistence tests.
6. Regression execution order cho auto-trade/AI Brief/Telegram/snapshot.

Không triển khai UI trước data contract; làm như vậy sẽ buộc UI đọc nested
`analysis_result` và tái tạo đúng vấn đề duplicate semantics đang cần loại bỏ.

### 8.16. Kết quả triển khai và review

Trạng thái ngày 2026-07-30:

- Mục 6 trong danh sách 8.15 đã được review đủ bốn phần 8.9, 8.10, 8.11 và
  8.12; quyết định cuối cùng: **CHO QUA**.
- Bước 0 tại mục 8.3 đã được xác nhận trước khi triển khai; thay đổi ngoài task
  trong `config/interest_rates.json` được giữ nguyên và không đưa vào feature.
- Tất cả file implementation/test của feature nằm trong danh sách mục 7.
  `core/scanner_ranking_engine.py`, `core/scanner_models.py` và các downstream
  consumer không bị sửa.
- Bộ test mục tiêu theo mục 8.10: **157 passed**.
- Regression scanner/SMC bổ sung: **56 passed**.
- Full suite: **1984 passed, 9 failed, 12 skipped, 17 xfailed**. Chín failure
  còn lại thuộc baseline/ngoài feature (restart style, layout Detail 20/80,
  dữ liệu FRED và các UI density/style lock); không có failure của mục 6.
- Kiểm tra runtime UI dark/light xác nhận đúng header, bốn trạng thái, màu
  semantic, `presentation_rank = 1..N`, điều hướng Detail và dialog lệnh.
- Probe downstream xác nhận AI Market Brief, Telegram và auto-trade tiếp tục
  dùng execution order/rank; ATR fallback vẫn giữ reason
  `FALLBACK_ENTRY_ZONE`.
