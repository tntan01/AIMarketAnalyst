# Kế hoạch thêm cột “Vùng” vào bảng Kết quả quét

> **Trạng thái:** Phương án triển khai — chưa sửa code  
> **Ngày lập:** 2026-07-30  
> **Vai trò lập kế hoạch:** Product Owner (PO)  
> **Phạm vi sản phẩm:** Scanner V2, bảng Kết quả quét  
> **Mức thay đổi:** UI và persistence; không thay đổi logic giao dịch

Tài liệu này ghi lại kết quả nghiên cứu code hiện tại và chuyển thành kế hoạch đủ
rõ để AI Coder triển khai. Đây chưa phải runtime contract. Sau khi triển khai và
nghiệm thu, AI Coder phải cập nhật các tài liệu runtime được liệt kê ở Bước 5.

## 1. Kết luận và quyết định sản phẩm

### 1.1. Phạm vi được chọn

Thêm một cột tên **“Vùng”** vào bảng Kết quả quét. Cột chỉ có hai trạng thái có
nghĩa nghiệp vụ:

- **Trong vùng:** giá tại thời điểm quét nằm trong vùng entry đã chọn, bao gồm
  cả hai biên.
- **Ngoài vùng:** giá tại thời điểm quét nằm thấp hơn biên dưới hoặc cao hơn
  biên trên.

Khi không đủ dữ liệu để kết luận, cột phải hiển thị `--`, không được gán nhầm là
“Ngoài vùng”.

### 1.2. Phương án PO chọn cho bản đầu tiên

| Quyết định | Phương án |
|---|---|
| Số trạng thái hiển thị | Hai: `Trong vùng`, `Ngoài vùng`; thiếu dữ liệu là `--` |
| Thời điểm tính | Một lần tại thời điểm quét |
| Giá dùng để hiển thị | Giá đã có trong kết quả phân tích của lần quét, hiện là close của nến H1 mới nhất |
| Cập nhật real-time | Không thêm timer, polling hoặc gọi tick MT5 từ bảng |
| Tác động giao dịch | Chỉ hiển thị; không thay đổi auto-trade, gate, score hoặc ranking |
| Snapshot | Lưu trạng thái dẫn xuất `price_vs_zone` trong summary snapshot |
| Vị trí cột | Ngay sau `Loại vùng`, trước `Điểm thiết lập` |
| Fallback/không có plan thật | Hiển thị `--` |

Lý do chọn phương án này:

1. Đáp ứng đúng nhu cầu đọc nhanh mà không tạo thêm khái niệm ngưỡng gần/xa trên
   UI.
2. Không cần lấy thêm live price, không phát sinh timer hoặc trạng thái stale.
3. Giữ nguyên dữ liệu chi tiết `in_zone`/`near_zone`/`far` mà ranking hiện đang
   sử dụng.
4. Snapshot mở lại vẫn phản ánh đúng trạng thái tại thời điểm quét.

### 1.3. Ngoài phạm vi

- Không thêm trạng thái “Gần vùng”, “Xa vùng” hoặc cấu hình ngưỡng ATR mới.
- Không đổi công thức `price_vs_entry_zone()`.
- Không đổi `opportunity_score`, `opportunity_rank`, `rank`,
  `execution_order` hoặc `presentation_order`.
- Không dùng cột này làm điều kiện cho auto-trade.
- Không thay gate revalidation giá trước khi gửi lệnh.
- Không thêm timer, worker, websocket hoặc lời gọi `get_live_price()` cho bảng.
- Không thay prompt hoặc payload của AI Market Brief và Telegram.
- Không thay schema database và không tạo setting mới.

## 2. Kết quả nghiên cứu code hiện tại

### 2.1. Dữ liệu có thể tái sử dụng

| Dữ liệu/logic | Vị trí hiện tại | Kết luận |
|---|---|---|
| Trade plan đúng hướng (`best_plan`) | `core/scanner.py:125` | Đã chọn sẵn đúng scenario BUY/SELL |
| Biên vùng entry | `core/risk_engine.py:1290`, truyền lên row tại `core/scanner.py:294` | Dùng trực tiếp `entry_zone = [low, high]`; không cần suy ra từ `entry_price` |
| Giá tại lần quét | `core/technical_context.py:56` | `technical["price"]` là close nến H1 mới nhất |
| Trạng thái giá so với vùng | `core/scanner.py:134-142`, gắn vào row tại `core/scanner.py:237` | Field `price_vs_zone` đã có trên scanner row |
| Hàm phân loại hiện hành | `core/scanner.py:654-669` | Trả `in_zone`, `near_zone`, `far` hoặc `unknown` |
| Nguồn/loại vùng | `core/scanner.py:126-131`, `:246-247` | Có đủ `entry_zone_source` và `zone_origin_class` để loại fallback |
| Giá live khi thực thi | `services/mt5_service.py:822-826` | BUY dùng ask, SELL dùng bid; chỉ dành cho luồng execution |
| Gate giá live | `core/execution_revalidation_engine.py:121-129` | Đã chặn `PRICE_OUTSIDE_ENTRY_ZONE` trước khi đặt lệnh |

Không thiếu dữ liệu cho phiên bản tính một lần tại thời điểm quét.

### 2.2. Công thức hiện tại

Hàm `price_vs_entry_zone(price, entry_zone, atr_value)` đang thực hiện:

```text
Nếu price hoặc entry_zone không hợp lệ:
    unknown
Nếu min(entry_zone) <= price <= max(entry_zone):
    in_zone
Nếu khoảng cách tới biên gần nhất <= 0.5 ATR:
    near_zone
Ngược lại:
    far
```

Với yêu cầu mới, không sửa công thức này. UI chỉ gộp trạng thái để hiển thị:

```text
in_zone              -> Trong vùng
near_zone hoặc far   -> Ngoài vùng
unknown/thiếu field  -> --
```

Giữ nguyên `near_zone` và `far` ở data layer là bắt buộc vì
`core/scanner_ranking_engine.py:712-717` đang cho ba trạng thái này mức chất
lượng proximity khác nhau trong opportunity ranking.

### 2.3. UI hiện tại

`ScannerTableModel` nằm trong `ui/screens/scanner_screen.py`.

- `COLUMNS` tại dòng 57-71 hiện có 13 cột và chưa chứa `price_vs_zone`.
- `ENTRY_ZONE_TEXT` tại dòng 77 đã có mapping ba mức cũ:
  `Trong vùng`/`Gần vùng`/`Còn xa`.
- `_display_value()` tại dòng 230-252 đã biết format `price_vs_zone`.
- `_foreground()` tại dòng 547-553 đã có màu riêng cho ba mức.
- tooltip tại dòng 139-141 đang dùng chung giải thích `entry_status`, chưa nói rõ
  trạng thái là tại thời điểm quét.
- `_configure_table_columns()` tại dòng 1992-2006 chưa có cấu hình độ rộng cho
  cột mới.
- `ScannerColumnsHelpDialog.COLUMN_HELP` tại dòng 2973-3094 đang mô tả đúng 13
  cột.

Vị trí đọc hợp lý:

```text
Bối cảnh TT | Loại vùng | Vùng | Điểm thiết lập
```

“Loại vùng” trả lời vùng đến từ đâu; “Vùng” trả lời giá đang ở trong hay ngoài
vùng đó. Hai thông tin liên quan trực tiếp nên đặt cạnh nhau.

### 2.4. Persistence hiện tại

`services/scanner_persistence_service.py:24-36` dùng whitelist
`SUMMARY_ROW_FIELDS`. Whitelist hiện có `entry_zone_source` và
`zone_origin_class`, nhưng chưa có `price_vs_zone`.

`controllers/scanner_controller.py:1785-1809` luôn tạo phần `rows` của snapshot
từ `summary_row(row)`, kể cả khi full analysis được lưu ở file tham chiếu riêng.
Vì vậy, nếu không bổ sung `price_vs_zone` vào whitelist, cột “Vùng” có thể mất
giá trị khi bảng được dựng từ summary snapshot.

Phương án PO:

- thêm `price_vs_zone` vào `SUMMARY_ROW_FIELDS`;
- không thêm toàn bộ `entry_zone` chỉ để phục vụ cột này;
- snapshot cũ không có field vẫn phải mở được và hiển thị `--`.

### 2.5. Luồng execution phải được giữ nguyên

`price_vs_zone` không phải chỉ là chuỗi trang trí: ba trạng thái nội bộ hiện là
một thành phần của opportunity ranking. Vì vậy AI Coder không được đổi field
backend thành boolean hoặc ghi đè `near_zone`/`far` thành cùng một giá trị.

Các bất biến phải giữ:

1. `result["rows"]` tiếp tục ở canonical execution order.
2. UI chỉ tạo display copies và presentation order tại
   `ui/screens/scanner_screen.py:1745-1749`.
3. Auto-trade tiếp tục duyệt execution order.
4. AI Market Brief và Telegram tiếp tục dùng thứ tự backend.
5. Trước khi gửi lệnh, execution tiếp tục lấy bid/ask mới và kiểm tra đúng
   `entry_zone`; nhãn trên bảng không thay thế gate này.

## 3. Contract chức năng

### 3.1. Truth table hiển thị

| `zone_origin_class` | `price_vs_zone` | Hiển thị | Màu ngữ nghĩa |
|---|---|---|---|
| `smc` hoặc `technical` | `in_zone` | `Trong vùng` | success/xanh |
| `smc` hoặc `technical` | `near_zone` | `Ngoài vùng` | muted/trung tính |
| `smc` hoặc `technical` | `far` | `Ngoài vùng` | muted/trung tính |
| `smc` hoặc `technical` | `unknown`, thiếu hoặc malformed | `--` | subtle/muted |
| `fallback` hoặc `none` | bất kỳ | `--` | subtle/muted |

Không được để giá trị lạ lọt thẳng ra UI. Ví dụ `price_vs_zone="invalid"` phải
hiển thị `--`, không hiển thị chữ `invalid`.

### 3.2. Quy tắc biên

Với `entry_zone=[low, high]`:

- `price == low`: Trong vùng.
- `price == high`: Trong vùng.
- `low < price < high`: Trong vùng.
- `price < low` hoặc `price > high`: Ngoài vùng.

Hàm backend hiện đã dùng điều kiện inclusive và không cần sửa.

### 3.3. Ý nghĩa thời gian

Cột phản ánh **giá tại thời điểm phân tích của lần quét**, không phải giá tick
đang chạy trên MT5. Tooltip phải nói rõ điều này để người dùng không hiểu đây là
chỉ báo real-time.

Giá có thể thay đổi sau khi quét. Khi người dùng quét lại, row mới sẽ mang trạng
thái mới. Khi người dùng chuẩn bị gửi lệnh, execution dùng bid/ask live và
revalidation độc lập.

### 3.4. Tooltip và trợ giúp

Tooltip đề xuất:

```text
Trạng thái giá tại thời điểm quét so với vùng entry đã chọn.
Trong vùng = giá nằm trong hoặc đúng biên vùng.
Ngoài vùng = giá nằm ngoài hai biên.
-- = chưa có vùng thật hoặc thiếu dữ liệu.
Giá sẽ được kiểm tra lại theo bid/ask live trước khi gửi lệnh.
```

Dialog “Giải thích Bảng kết quả quét” phải có mục “Vùng” cùng ý nghĩa trên và
phải cập nhật số cột từ 13 thành 14.

## 4. Phạm vi file cho AI Coder

### 4.1. File được phép sửa

| Nhóm | File | Mục đích |
|---|---|---|
| UI | `ui/screens/scanner_screen.py` | Thêm cột, mapping nhị phân, màu, tooltip, độ rộng và help dialog |
| Persistence | `services/scanner_persistence_service.py` | Giữ `price_vs_zone` trong summary snapshot |
| Test mới | `tests/test_scanner_zone_state_column.py` | Khóa truth table và UI contract của cột |
| Test hiện có | `tests/test_scanner_columns_help_dialog.py` | Khóa thứ tự/cấu trúc 14 cột và help dialog |
| Test hiện có | `tests/test_scanner_persistence_service.py` | Khóa persistence và backward compatibility |
| Runtime docs | `docs/scanner/scanner-flow.md` | Cập nhật contract bảng Scanner |
| Product docs | `docs/product/product_spec.md` | Cập nhật số lượng và danh sách cột |
| UI docs | `docs/ui/screen_design.md` | Thay contract ba mức cũ bằng hai mức mới |

### 4.2. File không được sửa trong phạm vi này

- `core/scanner.py`
- `core/scanner_ranking_engine.py`
- `core/entry_engine.py`
- `core/risk_engine.py`
- `core/execution_revalidation_engine.py`
- `controllers/scanner_controller.py`
- `services/mt5_service.py`
- `services/telegram_alert_service.py`
- các prompt AI Market Brief

Nếu AI Coder thấy bắt buộc phải sửa một file trong danh sách này, phải dừng và
báo xung đột phạm vi cho PO; không tự mở rộng task.

## 5. Kế hoạch triển khai theo từng bước

### Bước 0 — Khóa baseline trước khi sửa

Mục tiêu: phân biệt lỗi có sẵn với regression do task.

1. Chạy `git status --short`; ghi lại file bẩn có sẵn và không đưa chúng vào
   commit của task.
2. Chạy nhóm test baseline:

   ```powershell
   $env:QT_QPA_PLATFORM='offscreen'
   python -m pytest `
     tests/test_scanner_columns_help_dialog.py `
     tests/test_scanner_persistence_service.py `
     tests/test_scanner_phase6_ranking.py `
     tests/test_scanner_presentation.py `
     tests/test_scanner_ui_rr_contract.py `
     tests/test_execution_revalidation.py `
     tests/test_telegram_alert_service.py -q
   ```

3. Nếu baseline fail, dừng và báo rõ test nào fail trước khi sửa code.

Đầu ra: log baseline pass và danh sách file bẩn ban đầu.

### Bước 1 — Viết test contract cho cột “Vùng”

Tạo `tests/test_scanner_zone_state_column.py` trước khi sửa UI, gồm tối thiểu:

1. Cột `("price_vs_zone", "Vùng")` nằm ngay sau
   `("zone_origin_class", "Loại vùng")`.
2. `in_zone` hiển thị “Trong vùng”.
3. `near_zone` và `far` cùng hiển thị “Ngoài vùng”.
4. `unknown`, thiếu field và giá trị lạ hiển thị `--`.
5. Fallback/none luôn hiển thị `--`, kể cả fixture cố tình truyền
   `price_vs_zone="in_zone"`.
6. Biên thấp, biên cao và giá giữa vùng được helper backend phân loại
   `in_zone`; giá ngoài hai biên không được phân loại `in_zone`.
7. Màu `near_zone` và `far` giống nhau; không còn ngụ ý hai mức trên UI.
8. Tooltip có cụm “tại thời điểm quét” và nhắc revalidation live.

Cập nhật `tests/test_scanner_columns_help_dialog.py`:

- số cột/help row từ 13 thành 14;
- danh sách help khớp chính xác `ScannerTableModel.COLUMNS`;
- khóa vị trí `Loại vùng -> Vùng -> Điểm thiết lập`;
- intro của dialog không còn hard-code 13.

Đầu ra: test mới fail đúng vì UI chưa triển khai, không fail vì fixture sai.

### Bước 2 — Triển khai UI nhị phân

Trong `ui/screens/scanner_screen.py`:

1. Thêm `("price_vs_zone", "Vùng")` ngay sau `zone_origin_class`.
2. Đổi mapping hiển thị:

   ```python
   {
       "in_zone": "Trong vùng",
       "near_zone": "Ngoài vùng",
       "far": "Ngoài vùng",
       "unknown": "--",
   }
   ```

3. `_display_value()` phải normalize chuỗi và fallback về `--`, không trả raw
   value lạ.
4. Giữ guard `_has_real_plan()` để fallback/none hiển thị `--`.
5. Cho `near_zone` và `far` cùng màu muted; `in_zone` dùng success;
   unknown/missing dùng subtle hoặc muted.
6. Tạo tooltip riêng cho `price_vs_zone`; không dùng tooltip
   `entry_status` chung như hiện tại.
7. Thêm cấu hình độ rộng cho cột. Điểm bắt đầu đề xuất:
   `weight=1`, `min_width=95`; sau đó xác nhận bằng test/visual check.
8. Thêm dòng trợ giúp “Vùng” vào đúng vị trí trong `COLUMN_HELP` và đổi nội
   dung intro thành 14 cột.

Không sửa row, không ghi đè `price_vs_zone`, không sort lại dữ liệu trong
`ScannerTableModel`.

Đầu ra: test Bước 1 pass.

### Bước 3 — Giữ trạng thái trong snapshot

Trong `services/scanner_persistence_service.py`:

1. Thêm `"price_vs_zone"` vào `SUMMARY_ROW_FIELDS`.
2. Không thêm `entry_zone` hoặc `analysis_result` vào summary whitelist.
3. Bổ sung test:
   - summary giữ nguyên `in_zone`, `near_zone`, `far`, `unknown`;
   - field nặng như `analysis_result` vẫn bị loại;
   - snapshot/row cũ không có `price_vs_zone` không crash.

Lưu giá trị nội bộ, không lưu text tiếng Việt. UI chịu trách nhiệm mapping nên
snapshot vẫn tương thích nếu wording thay đổi sau này.

Đầu ra: test persistence pass và kích thước summary chỉ tăng một field ngắn.

### Bước 4 — Khóa không ảnh hưởng execution order

Chạy lại và, nếu coverage chưa đủ, bổ sung regression assertion vào test hiện
có để xác nhận:

1. `result["rows"]` và `rank` không bị mutate khi nạp bảng.
2. `presentation_rank` vẫn được tính riêng cho display copies.
3. Auto-trade nhận rows theo execution order.
4. AI Market Brief giữ backend rank order.
5. Telegram candidates giữ backend rank order.
6. `PRICE_OUTSIDE_ENTRY_ZONE` vẫn chặn lệnh theo bid/ask live.
7. Giá trị nội bộ `near_zone` và `far` vẫn khác nhau trong
   `ranking_score_breakdown`, dù text UI giống nhau.

Không được sửa test để làm yếu các invariant hiện hành.

Đầu ra: nhóm regression execution/presentation pass.

### Bước 5 — Đồng bộ tài liệu runtime

Sau khi code pass:

1. `docs/scanner/scanner-flow.md`: thêm cột “Vùng”, mô tả scan-time và mapping
   nhị phân.
2. `docs/product/product_spec.md`: đổi bảng Scanner từ 13 thành 14 cột.
3. `docs/ui/screen_design.md`: thay mọi mô tả `Trong vùng/Gần vùng/Còn xa` của
   cột Scanner bằng `Trong vùng/Ngoài vùng/--`; không sửa phần nào đang mô tả
   trạng thái chi tiết ở màn hình Detail nếu Detail vẫn dùng ba mức.
4. Ghi rõ cột không tác động auto-trade và execution revalidation vẫn dùng
   live bid/ask.

Đầu ra: tài liệu và code không còn mâu thuẫn về số cột hoặc semantics.

### Bước 6 — Nghiệm thu

Chạy nhóm test trực tiếp:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest `
  tests/test_scanner_zone_state_column.py `
  tests/test_scanner_columns_help_dialog.py `
  tests/test_scanner_persistence_service.py -q
```

Chạy nhóm regression:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest `
  tests/test_scanner_phase6_ranking.py `
  tests/test_scanner_presentation.py `
  tests/test_scanner_ui_rr_contract.py `
  tests/test_execution_revalidation.py `
  tests/test_telegram_alert_service.py -q
```

Cuối cùng chạy toàn bộ suite:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q
```

Kiểm tra thủ công tối thiểu ở dark và light theme:

- header và nội dung “Trong vùng”/“Ngoài vùng” không bị cắt;
- cột nằm đúng cạnh “Loại vùng”;
- fallback và dữ liệu thiếu là `--`;
- tooltip nói rõ “tại thời điểm quét”;
- resize ở chiều rộng nhỏ không làm mất khả năng đọc các cột quan trọng.

## 6. Acceptance criteria

- [ ] **AC-01:** Bảng Scanner có đúng 14 cột; “Vùng” nằm sau “Loại vùng”.
- [ ] **AC-02:** `in_zone` hiển thị “Trong vùng”.
- [ ] **AC-03:** `near_zone` và `far` đều hiển thị “Ngoài vùng”.
- [ ] **AC-04:** `unknown`, missing, malformed, fallback và none hiển thị `--`.
- [ ] **AC-05:** Giá đúng biên dưới hoặc biên trên được coi là “Trong vùng”.
- [ ] **AC-06:** Cột chỉ phản ánh thời điểm quét và không tự cập nhật real-time.
- [ ] **AC-07:** Summary snapshot giữ `price_vs_zone`; snapshot cũ vẫn mở được.
- [ ] **AC-08:** Không thêm `entry_zone`/`analysis_result` vào summary chỉ để
  phục vụ cột.
- [ ] **AC-09:** `near_zone` và `far` vẫn tồn tại riêng trong backend/ranking.
- [ ] **AC-10:** `rank`, `opportunity_rank`, `execution_order` và
  `presentation_order` không đổi semantics.
- [ ] **AC-11:** Auto-trade, AI Market Brief và Telegram tiếp tục dùng execution
  order cũ.
- [ ] **AC-12:** Execution vẫn revalidate bid/ask live và chặn
  `PRICE_OUTSIDE_ENTRY_ZONE`.
- [ ] **AC-13:** Dialog trợ giúp mô tả đúng 14 cột và đúng nghĩa scan-time.
- [ ] **AC-14:** Tài liệu runtime liên quan được đồng bộ.
- [ ] **AC-15:** Nhóm test trực tiếp, regression và full `pytest` đều pass.

## 7. Rủi ro và cách kiểm soát

| Rủi ro | Hậu quả | Kiểm soát |
|---|---|---|
| Gộp `near_zone`/`far` ngay ở backend | Làm thay đổi opportunity ranking và execution order | Chỉ map ở `_display_value()` |
| Gọi live tick từ UI | Tăng độ phức tạp, race condition, stale/disconnect và khác semantics scan | Không có timer/polling trong phiên bản này |
| Hiển thị unknown là “Ngoài vùng” | Người dùng hiểu sai là có vùng thật | Unknown/missing/fallback luôn là `--` |
| Không persist field | Snapshot summary mở lại mất giá trị | Whitelist `price_vs_zone` |
| Persist text tiếng Việt | Khó đổi wording và xử lý tương thích | Persist enum nội bộ, map ở UI |
| Hai text giống nhau nhưng màu near/far khác nhau | UI ngầm giữ ba mức dù sản phẩm nói hai mức | Near và far cùng màu muted |
| Tăng số cột làm chật bảng | Header/nội dung bị cắt ở cửa sổ nhỏ | Cấu hình min width và kiểm tra responsive |
| Tài liệu cũ còn ghi ba mức | AI Coder sau hiểu sai contract | Đồng bộ scanner-flow, product spec và screen design |

## 8. Checklist bàn giao của AI Coder

AI Coder phải báo cáo theo đúng thứ tự:

1. File đã sửa; xác nhận không có file ngoài phạm vi mục 4.1.
2. Truth table thực tế sau triển khai.
3. Kết quả test trực tiếp.
4. Kết quả regression execution/presentation.
5. Kết quả full `pytest`.
6. Xác nhận snapshot summary và backward compatibility.
7. Xác nhận auto-trade/AI Market Brief/Telegram vẫn dùng execution order cũ.
8. Xác nhận không thêm real-time polling và không sửa logic ranking.
9. Danh sách acceptance criteria AC-01 đến AC-15: ĐẠT/CHƯA ĐẠT.

Nếu có xung đột giữa kế hoạch này và runtime contract/code mới hơn tại thời điểm
triển khai, AI Coder phải dừng và báo PO; không tự chọn thay đổi semantics giao
dịch.
