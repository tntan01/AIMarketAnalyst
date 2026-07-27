# UI Control Density Plan

Ngày rà soát: 27/07/2026
Trạng thái: Phase 0 đến Phase 6 hoàn thành.

## 1. Mục đích

Chuẩn hóa chiều cao control nhằm dành thêm không gian dọc nhưng vẫn bảo đảm chữ
tiếng Việt, icon và subcontrol không bị cắt ở Windows DPI 100–150%. Mọi quy tắc
trình bày phải nằm trong stylesheet chung; screen, dialog và component không được
tự gắn CSS/QSS.

Contract mục tiêu đã chốt:

- control một dòng, action button và tab thông thường: chiều cao render 24 px;
- control trong bảng, nút trợ giúp/icon và thành phần compact: 20 px;
- text nhiều dòng, chart và container: chiều cao theo nội dung hoặc bố cục;
- `ui/styles/base.qss` sở hữu kích thước, padding và typography;
- `ui/styles/dark.qss` và `ui/styles/light.qss` chỉ sở hữu màu theo theme.

## 2. Phase 0 — Kiểm kê và khóa baseline ✅

### 2.1. Công cụ và bằng chứng

- `tools/ui_density_audit.py` quét toàn bộ `ui/**/*.py`, ba QSS chung và đo
  representative control bằng Qt offscreen ở dark/light theme.
- `docs/ui-density-baseline.json` lưu inventory có thể kiểm tra lại.
- `tests/test_ui_density_phase0.py` không cho phát sinh chiều cao cục bộ hoặc rule
  QSS mới khi chưa được review.

Inventory hiện ghi nhận 67 lời gọi Python có ảnh hưởng đến chiều cao và 68 khối
QSS có khai báo `height/min-height/max-height`. Trong đó có 22 lời gọi Python và
20 khối QSS liên quan trực tiếp đến control tương tác; phần còn lại chủ yếu là
container, chart, text nhiều dòng, table, progress và subcontrol.

Lệnh tái tạo/kiểm tra:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/ui_density_audit.py --write docs/ui-density-baseline.json
python -m pytest -q tests/test_ui_density_phase0.py
```

### 2.2. Baseline render hiện tại

Dark và light đang cho cùng số đo nhưng tồn tại nhiều chuẩn:

| Thành phần đại diện | Chiều cao thực tế |
|---|---:|
| `QTabWidget#ContentTabs` tab | 18 px |
| `FilterField` LineEdit/ComboBox/SpinBox/DateEdit | 28 px |
| `FilterField` DateTimeEdit/TimeEdit | 25 px |
| `PrimaryButton` / `SecondaryButton` | 30 px |
| Button thông thường | 23 px |
| Control/button qua helper layout | 32 px |
| `HelpButton` | dark 22 px / light 20 px |
| Sidebar toggle | 33 px |

Điều này xác nhận không thể chỉ đổi một selector. Padding, border, min/max height,
specificity và các lệnh Python đều đang cùng quyết định chiều cao cuối.

### 2.3. Xung đột cần xử lý ở phase sau

1. `ui/layout_system.py` ép control, button và checkbox thành 32 px.
2. `ui/screens/backtest_screen.py` ép nhóm input, combo, button và checkbox thành
   22 px sau khi helper đã đặt 32 px.
3. `FilterField` đặt `min-height/max-height: 22px` trong cả hai theme overlay;
   cộng padding và border làm chiều cao thực tế thành 28 px.
4. Primary/Secondary button có `min-height: 24px` ở base và padding riêng trong
   overlay, tạo chiều cao thực tế 30 px.
5. Tab không có contract chiều cao rõ ràng và hiện render 18 px.
6. `QDateTimeEdit` và `QTimeEdit` chưa được bao phủ nhất quán bởi mọi selector
   input/filter và trạng thái theme.
7. Một số control riêng còn có override 24/28/32 px như auto-trade checkbox,
   scanner detail button và pip spinbox trong dialog lệnh.
8. `HelpButton` render khác nhau giữa dark và light; sidebar toggle khai báo
   min/max 28 px nhưng tổng padding/border làm chiều cao thực tế thành 33 px.

### 2.4. Phân loại đã khóa

**Standard 24 px:** LineEdit, ComboBox, SpinBox, DoubleSpinBox, DateEdit,
DateTimeEdit, TimeEdit, action button và tab thông thường.

**Compact 20 px:** editor nằm trong bảng Symbols, HelpButton, icon-only button,
chip/badge nhỏ và control trong toolbar dày đặc. Các trường hợp này phải có
selector semantic chung, không có stylesheet cục bộ.

**Không áp dụng fixed control height:** QTextEdit, nội dung AI nhiều dòng, note,
chart/WebEngine canvas, progress đặc thù, card, table/header, scrollbar, status
bar và kích thước tối thiểu của dialog/window.

## 3. Các phase tiếp theo

### Phase 1 — QSS nền ✅

Đưa contract 24/20 px, padding, font, radius và kích thước subcontrol vào
`ui/styles/base.qss`. Chuẩn được xác nhận bằng chiều cao render thực, không hiểu
nhầm `min-height` là chiều cao tổng.

Đã hoàn thành:

- input một dòng, FilterField, action button, tab và button dạng tab render đúng
  24 px trên cả dark/light;
- HelpButton, icon/link button, TagChip, ResultTabArrow, tab scroller, editor
  trong bảng Symbols và Lifecycle control render đúng 20 px;
- toàn bộ rule `height/min-height/max-height` của control tương tác hiện chỉ nằm
  trong `ui/styles/base.qss`;
- padding, typography và kích thước subcontrol trùng nhau đã được chuyển khỏi hai
  theme overlay về base QSS;
- `docs/ui-density-lock.json` là lock đã review sau Phase 1; baseline Phase 0 vẫn
  được giữ nguyên làm bằng chứng trước thay đổi.

Lệnh kiểm tra:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/ui_density_audit.py --check docs/ui-density-lock.json
python -m pytest -q tests/test_ui_density_phase0.py tests/test_ui_density_phase1.py
```

### Phase 2 — Viền theo theme ✅

Dark/light overlay chỉ giữ màu nền, chữ, viền và trạng thái default/hover/focus/
open/disabled/invalid. Hai theme phải có cùng selector contract.

Đã hoàn thành:

- chuẩn hóa thang màu viền normal/hover/focus/disabled/invalid riêng cho dark và
  light theme;
- bổ sung đầy đủ `QDateTimeEdit` và `QTimeEdit` vào mọi trạng thái;
- FilterField dùng cùng thang màu semantic với input thông thường, không còn
  giữ màu active khi bị disabled;
- màu đường phân cách drop-down đi theo trạng thái của viền ngoài;
- editor compact trong bảng Symbols có đủ hover/focus/disabled/invalid;
- dynamic property chuẩn cho lỗi nhập liệu là
  `validationState="invalid"`; trạng thái invalid khi disabled quay về màu viền
  disabled để không gây hiểu nhầm control còn thao tác được;
- contract chiều cao 24/20 px từ Phase 1 được giữ nguyên.

### Phase 3 — Xóa nguồn chiều cao cục bộ ✅

Đã loại bỏ các lệnh `setFixedHeight()`, `setMinimumHeight()` và `setFixedSize()`
khỏi control tương tác để QSS chung là nguồn duy nhất quyết định chiều cao. Các helper
`configure_control()`, `configure_button()`, `configure_checkbox()` và
`configure_help_button()` nay chỉ cấu hình size policy, chiều rộng hoặc icon, không ép
chiều cao hình thức và không thêm `setStyleSheet()` vào Python.

Đã hoàn thành:

- xóa toàn bộ override chiều cao tương tác khỏi Backtest, Scanner, Orders, Journal và
  component dùng chung;
- đưa `QCheckBox`, `QRadioButton` và `FormLabel` về contract 24 px trong
  `ui/styles/base.qss`;
- giữ lại 33 lệnh kích thước đã phân loại hợp lệ cho container, text nhiều dòng,
  chart, table/header, progress và thành phần kết cấu;
- giảm inventory Python từ 67 lời gọi ở baseline Phase 0 xuống 33 ngoại lệ hợp lệ,
  với 0 mục `interactive` và 0 mục `review`;
- cập nhật `docs/ui-density-lock.json` và bổ sung guard
  `tests/test_ui_density_phase3.py` để ngăn helper hoặc screen tái chiếm quyền sở hữu
  chiều cao control;
- cập nhật audit responsive để kiểm tra đúng 24 px với control chuẩn và 20 px với
  control compact.

Lệnh kiểm tra:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/ui_density_audit.py --check docs/ui-density-lock.json
python -m pytest -q tests/test_ui_density_phase0.py tests/test_ui_density_phase1.py `
  tests/test_ui_density_phase2.py tests/test_ui_density_phase3.py
```

### Phase 4 — Áp dụng theo cụm màn hình ✅

Đã rà soát lần lượt Journal, Backtest, Settings, Scanner, Orders, Dashboard,
component dùng chung và các dialog. Các cụm này nhận contract 24/20 px từ QSS chung;
không còn screen/dialog tự đặt stylesheet hoặc chiều cao cho control tương tác.

Đã hoàn thành:

- chuyển kích thước indicator checkbox, typography của checkbox chọn mã Scanner,
  hình thức radio trong dialog trợ giúp và hình thức button của `QMessageBox` về
  `ui/styles/base.qss`;
- loại bỏ toàn bộ padding, spacing, font, kích thước và border-radius tương tác còn
  lặp trong `ui/styles/dark.qss` và `ui/styles/light.qss`; hai overlay giờ chỉ giữ màu và
  trạng thái theo theme;
- sửa radio thuộc `ScannerHelpDialog` từ chiều cao render 30 px về đúng 24 px trên
  cả dark và light, không cắt nội dung;
- xác nhận checkbox chọn symbol Scanner tiếp tục render 24 px trên cả hai theme;
- sửa phân loại audit cho `QDoubleSpinBox` và `QToolButton` để inventory không bỏ sót
  control tương tác;
- bổ sung `tests/test_ui_density_phase4.py` kiểm tra toàn bộ cụm màn hình, quyền sở
  hữu QSS và contract runtime của dialog Scanner;
- cập nhật `docs/ui-density-lock.json` sau khi các thay đổi được review.

Phase 4 không thay đổi nghiệp vụ, dữ liệu, signal-slot hoặc hành vi giao dịch.

Lệnh kiểm tra:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/ui_density_audit.py --check docs/ui-density-lock.json
python -m pytest -q tests/test_ui_density_phase0.py tests/test_ui_density_phase1.py `
  tests/test_ui_density_phase2.py tests/test_ui_density_phase3.py `
  tests/test_ui_density_phase4.py
```

### Phase 5 — Kiểm thử contract ✅

Đã tự động hóa việc kiểm tra 24 px standard, 20 px compact, parity dark/light,
không cắt nội dung theo chiều dọc và không phát sinh stylesheet cục bộ.

Đã hoàn thành:

- đưa danh sách control đại diện standard/compact về một nguồn duy nhất trong
  `tools/ui_density_audit.py`, dùng chung cho audit và test;
- bổ sung đại diện cho checkbox chọn symbol và radio trong dialog Scanner;
- lưu thêm `content_height` dựa trên font/icon thực tế của từng control;
- bổ sung `validate_runtime_contract()` để kiểm tra chiều cao render chính xác,
  khoảng trống dọc tối thiểu cho chữ/icon và parity giữa dark/light;
- thêm tùy chọn CLI `--validate-contract`, trả exit code khác 0 khi contract bị phá;
- bổ sung `tests/test_ui_density_phase5.py` để khóa coverage runtime và bảo đảm chỉ
  `ui/theme_manager.py` được gọi `setStyleSheet()`;
- cập nhật `docs/ui-density-lock.json` với tập số đo đã review.

Lệnh kiểm tra:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/ui_density_audit.py --check docs/ui-density-lock.json `
  --validate-contract
python -m pytest -q tests/test_ui_density_phase0.py tests/test_ui_density_phase1.py `
  tests/test_ui_density_phase2.py tests/test_ui_density_phase3.py `
  tests/test_ui_density_phase4.py tests/test_ui_density_phase5.py
```

### Phase 6 — Visual QA ✅

Đã kiểm tra dark/light tại DPI 100%, 125%, 150% và các viewport 14", 15.6", 16",
24", 27", 32"; đồng thời tạo baseline ảnh có font thật cho toàn bộ màn hình.

Đã hoàn thành:

- ban đầu sửa Scanner thành grid hai hàng để giảm minimum width từ 1646 xuống dưới
  1366 px; theo yêu cầu bố cục mới, đã đưa lại toàn bộ điều khiển Scanner lên một
  hàng theo thứ tự thao tác, dùng kích thước tự nhiên cố định theo nội dung và vẫn
  giữ minimum width dưới 1366 px ngay cả khi nút dừng quét đang hiển thị;
- sửa Journal từ chín nút lọc nhanh trên một hàng thành grid hai hàng; harness không
  còn bị dữ liệu `MagicMock` kéo giãn sai minimum width và màn hình vừa 1366 px;
- nâng `tools/ui_layout_audit.py` lên schema 2, chạy từng route trong process riêng,
  hỗ trợ ba DPI, sáu viewport và chạy song song có timeout;
- cố định DPI gốc 96 và nạp Segoe UI/Segoe UI Emoji trực tiếp cho Qt offscreen, giúp
  ảnh kiểm tra có chữ thật nhưng không bật cửa sổ hoặc gọi dịch vụ ngoài;
- chạy đủ 288 trường hợp responsive (`8 màn hình × 6 viewport × 3 DPI × 2 theme`),
  kết quả 0 lỗi tại `docs/ui-responsive-report.json`;
- tạo 48 ảnh baseline tại `docs/ui-baseline/density-phase6` cho 8 màn hình, 3 DPI và
  2 theme ở viewport 1366×768; manifest không có failure;
- kiểm tra trực quan Scanner và Journal tại 100%/150%: chữ, nút và cột không bị cắt,
  không chồng lấn, bố cục dark/light nhất quán;
- kiểm tra bổ sung riêng Scanner trên cả hai theme, ba mức DPI và sáu viewport:
  36/36 trường hợp không có lỗi layout;
- đưa toàn bộ trường cấu hình chính của Backtest lên một hàng; chuyển nhóm hành động
  sang cạnh thanh tiến trình để không tràn khi nút Hủy hoặc Áp dụng xuất hiện; kiểm
  tra bổ sung Backtest trên hai theme, ba mức DPI và sáu viewport đạt 36/36;
- bổ sung `tests/test_ui_density_phase6.py` để khóa coverage, DPI, kích thước viewport,
  hash và kích thước vật lý của ảnh.
- bổ sung `tests/test_scanner_toolbar_layout.py` để khóa thứ tự, căn giữa, kích thước
  tự nhiên và trường hợp rộng nhất khi nút dừng quét tự động đang hiện.

Phase 6 không thay đổi nghiệp vụ, signal-slot hoặc hành vi giao dịch.

Lệnh tái tạo/kiểm tra:

```powershell
python tools/ui_layout_audit.py --write docs/ui-responsive-report.json `
  --workers 3 --job-timeout 90
python tools/capture_ui_density_visuals.py --suite --replace `
  --output docs/ui-baseline/density-phase6 --viewport 1366x768 `
  --workers 3 --job-timeout 90
python -m pytest -q tests/test_ui_density_phase6.py
```

## 4. Tiêu chí đóng Phase 0

- Inventory Python/QSS đầy đủ và chạy lại được.
- Baseline có số đo dark/light và contract mục tiêu 24/20 px.
- Xung đột và ngoại lệ được phân loại rõ.
- Guard test ngăn phát sinh height rule chưa review.
- Không có thay đổi giao diện, nghiệp vụ hoặc signal-slot trong Phase 0.
