# UI Style Standardization Plan

Ngày điều tra: 26/07/2026
Cập nhật gần nhất: 27/07/2026
Trạng thái: Toàn bộ Phase 0 đến Phase 7 đã hoàn thành.

## 0. Tiến độ thực hiện

### Phase 0 — Hoàn thành ngày 27/07/2026

Đã hoàn thành khóa an toàn mà không sửa giao diện sản phẩm:

- Tạo inventory tại `docs/ui-style-baseline.json`.
- Tạo allowlist có lý do và disposition tại
  `docs/ui-style-allowlist.json`.
- Tạo công cụ audit không phụ thuộc Qt tại `tools/ui_style_audit.py`.
- Tạo harness chụp ảnh cô lập MT5, mạng, worker và persistence tại
  `tools/capture_ui_style_baseline.py`.
- Chụp 74 ảnh trong `docs/ui-baseline/current`: 37 dark và 37 light.
- Ảnh bao phủ 8 màn hình, các tab chính, 14 dialog và 4 trạng thái component:
  default, focus, hover và pressed.
- Manifest có SHA-256 và kích thước ảnh tại
  `docs/ui-baseline/current/screenshot-manifest.json`.
- Thêm 3 guardrail test tại `tests/test_ui_style_phase0_guardrails.py`.

Lỗi nền được phát hiện trong quá trình chụp baseline và đã sửa trước Phase 2:

- `ScannerScreen._show_orders_dialog()` gọi trực tiếp
  `format_order_entry_tooltip`, `format_order_rr_text`,
  `format_order_rr_tooltip` và `enrich_order_note_with_current_rr` nhưng
  `scanner_screen.py` chưa import các formatter này. Đã bổ sung import từ
  `ui.scanner_rr_formatters`, bỏ shim trong harness và thêm kiểm thử import
  để dialog chạy đúng bằng mã sản phẩm.

### Phase 1 — Hoàn thành ngày 27/07/2026

Đã hoàn thành nền tảng theme thống nhất:

- Mở rộng `ui/theme.py` với immutable semantic palette cho dark/light.
- Bổ sung đầy đủ role: surface, text, muted, border, accent, success, warning,
  danger, info, buy, sell, neutral, focus và chart.
- Tạo `ui/theme_manager.py` làm điểm duy nhất resolve, nạp và áp dụng theme.
- Tạo helper `set_dynamic_property()` và `repolish()`.
- Tạo `ui/styles/base.qss` và pipeline nạp `base.qss` trước theme overlay.
- Trong giai đoạn chuyển tiếp, overlay vẫn là `ui/styles/dark.qss` và
  `ui/styles/light.qss` để bảo toàn pixel; Phase 2 mới chuyển các rule dùng
  chung vào `base.qss`.
- Toàn bộ code UI xác định light/dark qua Theme Manager. Settings chỉ đọc giá
  trị hiện tại để hiển thị combobox và gọi hot reload như trước.
- Cập nhật PyInstaller để đóng gói dark, light và base QSS.
- Thêm 6 test chuyên biệt tại `tests/test_theme_manager.py`.
- Ảnh Backtest dark và light sau Phase 1 trùng SHA-256 với baseline Phase 0.
- Toàn bộ test: `1640 passed, 12 skipped, 17 xfailed`.

### Phase 2 — Hoàn thành ngày 27/07/2026

Đã làm sạch stylesheet và chuẩn hóa cascade:

- Chuyển typography, kích thước, padding, border-radius và quy tắc bố cục dùng
  chung sang `ui/styles/base.qss`; file này không chứa màu theme.
- Giữ `ui/styles/dark.qss` và `ui/styles/light.qss` làm color/state overlay và bảo
  đảm hai file có cùng 425 selector.
- Bổ sung contract chung cho `InfoCard`, `BacktestResultText`,
  `BacktestVerdict`, `MarketBadge`, `BacktestAnalysisDialog` và
  `BacktestConfigDialog`.
- Bổ sung object name `BacktestAnalysisText` để QSS có thể quản lý nội dung
  dialog phân tích mà không phụ thuộc selector toàn cục.
- Loại bỏ bộ selector `ActiveProviderCell`/`ActiveProviderCheck` đã không còn
  được mã giao diện sử dụng và bỏ variant `RoundedTab` không có consumer.
- Dark overlay giảm 96 dòng, light overlay giảm 67 dòng; số selector trùng
  giảm một ở mỗi file.
- Mở rộng audit để kiểm tra `base.qss`: không màu theme và không selector trùng.
- Thêm 4 kiểm thử contract Phase 2 tại `tests/test_ui_style_phase2.py`.
- Chụp và so sánh đủ 74 ảnh: 37 dark và 37 light đều khớp SHA-256 với baseline
  đã chốt. Baseline dark của dialog giải thích Scanner được cập nhật một lần do
  Phase 1 đã sửa đúng việc nhận diện theme, giúp nội dung không còn dùng nhầm
  màu chữ light trên nền dark.
- Toàn bộ test: `1645 passed, 12 skipped, 17 xfailed`.

### Phase 3 — Hoàn thành ngày 27/07/2026

Đã chuyển các quy tắc giao diện tĩnh còn nằm rải rác trong màn hình, dialog và
component về stylesheet dùng chung, không thay đổi logic nghiệp vụ hoặc
signal-slot:

- Loại bỏ toàn bộ lời gọi `setStyleSheet()` có chuỗi CSS tĩnh trong thư mục
  `ui`; các style còn lại đều là style động theo dữ liệu/trạng thái và được
  giữ trong allowlist để xử lý ở Phase 4.
- Hoàn tất các nhóm chính: cửa sổ chính, nút khởi động lại, chart surface,
  `InfoCard`, Backtest dialog/config/result, Dashboard dialog/tab,
  Orders dialog/tab, Scanner dialog/scroll/text, Journal và Journal Detail.
- Bổ sung object name/property ngữ nghĩa như `RestartButton`,
  `AnalysisChartSurface`, `MarketBriefDialog`, `ScannerDetailText`,
  `compactReadOnly`, `scannerOrderDialog` và `trailingDialog` để QSS dùng
  chung mà vẫn giữ được biến thể hiển thị cần thiết.
- Tách kiểu `ReadonlyText` compact của Journal Detail khỏi vùng văn bản phân
  tích AI, tránh làm mất nền/viền của các dialog khác.
- Số lời gọi `setStyleSheet()` giảm từ 184 xuống 72; bốn thành phần trọng tâm
  (`main_window`, `chart_view`, `info_card`, `journal_detail_screen`) không
  còn stylesheet cục bộ.
- Cập nhật allowlist Phase 3, guardrail test và baseline 74 ảnh (37 dark,
  37 light); ảnh hiện trạng đã được chụp lại sau khi chuẩn hóa cascade.
- Kiểm thử mục tiêu Phase 3: `49 passed`; audit stylesheet đạt trạng thái
  `UI style debt is within baseline`.
- Toàn bộ test sau Phase 3: `1651 passed, 12 skipped, 17 xfailed` (5 cảnh
  báo đã biết từ test hiện hữu).

### Phase 4 — Hoàn thành ngày 27/07/2026

Đã chuẩn hóa các component có trạng thái runtime bằng semantic property và
QSS chung:

- `PerformanceKPICard` dùng `kpiState` với các role `positive`, `negative`,
  `warning`, `neutral` và `muted`; màu viền, giá trị và mô tả do theme overlay
  quyết định.
- `MissingRBanner` dùng property `state` (`warning`/`hidden`) thay cho
  stylesheet tạo trực tiếp trong Python.
- Các số liệu live trong dialog Orders dùng `metricTone`; trạng thái Break
  Even dùng `statusTone` (`success`, `warning`, `danger`, `neutral`).
- Chỉ số P/L trên màn hình Orders dùng `metricRole="profit"` kết hợp
  `metricTone`, giữ riêng typography và màu semantic trong QSS.
- Bổ sung selector tương ứng trong cả dark/light overlay, không thay đổi
  widget class hoặc signal-slot.
- Số lời gọi `setStyleSheet()` giảm tiếp từ 72 xuống 57.
- Cập nhật allowlist sang `phase-4-reviewed`, thêm guardrail
  `tests/test_ui_style_phase4.py`.
- Chụp lại các màn hình Orders/Journal và dialog liên quan sau khi chuyển
  trạng thái; baseline manifest đã được cập nhật.
- Kiểm thử mục tiêu Phase 4: `25 passed, 1 skipped`.
- Toàn bộ test sau Phase 4: `1654 passed, 12 skipped, 17 xfailed` (5 cảnh
  báo đã biết từ test hiện hữu).

### Phase 5 — Hoàn thành ngày 27/07/2026

Đã chuyển các cụm màn hình còn lại sang semantic property và stylesheet chung,
giữ nguyên logic nghiệp vụ và signal-slot:

- Dashboard: trạng thái thẻ, liên kết tin tức, nút AI và nhãn xu hướng dùng
  `state`, `linkTone` và `metricTone`.
- Backtest: ô thống kê và banner kết quả dùng `metricTone` và `verdictState`;
  nội dung báo cáo HTML vẫn giữ riêng để xử lý ở Phase 6.
- Scanner: thẻ trạng thái kế hoạch lệnh và nhãn hướng lệnh dùng
  `headerTone`, `manualOrder` và `direction`.
- Scanner detail: hero, summary, panel, checklist, macro và cảnh báo dùng
  property semantic tương ứng; các màu phụ thuộc dữ liệu và progress bar động
  được giữ trong allowlist để xử lý ở Phase 6.
- Số lời gọi `setStyleSheet()` trong code UI giảm từ 57 xuống 4: một loader
  stylesheet và ba trường hợp runtime/data-driven đã được ghi rõ trong allowlist.
- Thêm `tests/test_ui_style_phase5.py`, cập nhật test status card và fake widget
  để kiểm tra kiến trúc mới.
- Audit stylesheet đạt `UI style debt is within baseline`; ảnh dark/light đã
  được kiểm tra lại trước khi chốt baseline.
- Toàn bộ test sau Phase 5: `1658 passed, 12 skipped, 17 xfailed` (5 cảnh
  báo đã biết từ test hiện hữu).

### Phase 6 — Hoàn thành ngày 27/07/2026

Đã chuẩn hóa lớp trình bày không thể điều khiển trực tiếp bằng Qt QSS:

- Thêm `ui/rich_text.py` làm renderer chung cho `QTextEdit`, `QTextBrowser` và
  `QLabel` rich-text. Renderer chuyển các khai báo `style=` thành CSS class,
  chèn stylesheet theo palette đang chạy và ánh xạ màu cũ sang semantic role.
- Các màn hình Backtest, Dashboard, Journal Detail và Scanner Detail đều gửi
  HTML qua renderer; các trạng thái rỗng/lỗi/chờ dùng template chung.
- Bảng dữ liệu của Backtest, Dashboard, Orders, Journal và Scanner lấy màu từ
  `ThemePalette`; không còn `QColor("#...")` trong các nhánh render chính.
- Matplotlib Backtest/Journal và WebEngine chart dùng `chart_palette()` chung.
  Payload chart truyền palette semantic sang `assets/chart/index.html`; CSS
  control của chart dùng biến CSS theo theme.
- Đã loại bỏ toàn bộ `setStyleSheet()` cục bộ còn lại. Chỉ còn một lời gọi tại
  `ThemeManager`, là điểm nạp stylesheet tập trung duy nhất.
- Thêm kiểm thử contract tại `tests/test_ui_style_phase6.py`; cập nhật
  `tests/test_ui_style_phase5.py` để xác nhận scanner đã hoàn tất migration.
- Baseline dark/light đã được chụp lại và manifest vẫn giữ 74 ảnh (37 dark,
  37 light).
- Audit hiện tại: `setStyleSheet=1`, `html style attributes=450` trong nguồn
  legacy (được compile trước khi giao cho widget), `hex literals=552`; không
  vượt baseline và toàn bộ literal còn lại đã thuộc palette/theme hoặc template
  rich-text được review.
- Toàn bộ test sau Phase 6: `1664 passed, 12 skipped, 17 xfailed` (5 cảnh
  báo đã biết từ test hiện hữu).

### Phase 7 — Hoàn thành ngày 27/07/2026

Đã hoàn tất kiểm thử, dọn dẹp và khóa kiến trúc giao diện:

- Thêm `tools/ui_layout_audit.py`, kiểm tra tự động 8 route trên cả dark/light
  với sáu profile màn hình 14", 15.6", 16", 24", 27" và 32". Báo cáo tại
  `docs/ui-responsive-report.json` đạt 96/96 lượt kiểm tra, 0 lỗi.
- Sửa chiều cao nút tự động vào lệnh của Scanner và chuyển hàng cấu hình
  Backtest sang lưới hai dòng. Khu nghiên cứu nâng cao dùng danh sách tùy chọn
  một cột để không chồng lấn trên viewport nhỏ; logic và signal-slot giữ nguyên.
- Bộ baseline được nâng từ 74 lên 80 ảnh: 40 dark và 40 light. Ngoài toàn bộ
  screen/tab/dialog hiện có, mỗi theme có đủ default, focus, hover, pressed,
  disabled, checked và validation state.
- Cải tiến harness ảnh dùng render offscreen, tránh phụ thuộc native window và
  không gọi dịch vụ MT5/mạng trong kiểm thử giao diện.
- Tạo strict lock tại `docs/ui-style-lock.json`; CI không cho tăng
  `setStyleSheet`, inline HTML style hoặc literal màu theo từng file. Toàn bộ
  screen hiện có 0 lời gọi `setStyleSheet`; chỉ `ThemeManager` được phép có một
  lời gọi để nạp stylesheet ứng dụng.
- Xóa palette dark-only `APP_COLORS`, `COLOR_UP`, `COLOR_DOWN` và helper màu
  liên kết Dashboard không còn consumer.
- Thêm năm contract test tại `tests/test_ui_style_phase7.py` và tài liệu quy
  chuẩn tại `docs/ui-style-guide.md`; allowlist chỉ còn disposition permanent
  hoặc centralized.
- Audit cuối: `setStyleSheet=1`, `html style attributes=450`, `hex literals=532`.
- Toàn bộ test sau Phase 7: `1669 passed, 12 skipped, 17 xfailed` (5 cảnh báo
  đã biết từ test hiện hữu).

## 1. Mục đích

Rà soát toàn bộ giao diện để đưa những quy tắc trình bày đang gắn trực tiếp trong
code về một hệ thống style dùng chung. Mục tiêu là:

- Bảo đảm các thành phần cùng loại có giao diện thống nhất.
- Giảm trùng lặp màu sắc, font, border, padding và trạng thái widget.
- Hạn chế sai lệch giữa theme tối và theme sáng.
- Giúp thay đổi giao diện có thể thực hiện tại một nguồn chung.
- Không thay đổi chức năng, logic nghiệp vụ hoặc signal-slot.

## 2. Phạm vi điều tra

Đã rà soát toàn bộ 32 file trong thư mục `ui`, bao gồm:

- Hai stylesheet dùng chung: `ui/styles/dark.qss` và `ui/styles/light.qss`.
- Cửa sổ chính và điều hướng.
- Tất cả màn hình, dialog và widget.
- Các component dùng chung.
- Style của nội dung HTML, bảng và biểu đồ được tạo trong code UI.
- Các test đang phụ thuộc vào style hoặc chuỗi CSS cụ thể.

Không thay đổi file nào trong giai đoạn điều tra.

## 3. Kết luận điều tra

Hệ thống đã có stylesheet chung nhưng chưa có một nguồn giao diện thống nhất.
Nhiều màn hình vẫn tự quyết định màu sắc, font, nền, border và trạng thái bằng
`setStyleSheet()` hoặc literal màu nằm trực tiếp trong Python.

Thống kê tĩnh:

- 32 file trong thư mục `ui`.
- 184 lần gọi `setStyleSheet()`.
- Khoảng 467 thuộc tính `style=` trong nội dung HTML.
- 1.024 literal màu HEX trong Python.
- `ui/styles/dark.qss`: 1.787 dòng, 286 block rule.
- `ui/styles/light.qss`: 1.742 dòng, 282 block rule.
- Có 32–33 selector được khai báo ở nhiều block trong mỗi theme.
- `ui/theme.py` mới có 8 màu của dark theme và gần như chưa được dùng làm nguồn
  màu chung.
- `ui/screens/settings_screen.py` không có `setStyleSheet()` trực tiếp và là
  màn hình gần với kiến trúc mong muốn nhất.

### 3.1. Các điểm nóng

| File | `setStyleSheet()` | HTML `style=` | Literal màu | Mức độ |
|---|---:|---:|---:|---|
| `ui/screens/scanner_detail_screen.py` | 56 | 196 | 370 | Rất cao |
| `ui/screens/backtest_screen.py` | 13 | 186 | 224 | Rất cao |
| `ui/screens/scanner_screen.py` | 30 | 5 | 119 | Cao |
| `ui/screens/journal_detail_screen.py` | 25 | 52 | 38 | Cao |
| `ui/screens/dashboard_screen.py` | 20 | 24 | 138 | Cao |
| `ui/screens/journal_screen.py` | 16 | 3 | 74 | Trung bình |
| `ui/screens/orders_screen.py` | 14 | 0 | 30 | Trung bình |
| `ui/main_window.py` | 4 | 0 | 10 | Thấp |
| `ui/components/info_card.py` | 4 | 0 | 12 | Thấp |
| `ui/components/chart_view.py` | 2 | 1 | 1 | Thấp |

### 3.2. Các vấn đề chính

1. Inline style có thể ghi đè QSS chung

   Ví dụ `StatusCard` trên Dashboard đã có selector theo property `state` trong
   cả hai stylesheet, nhưng màn hình vẫn tự gắn border và màu bằng
   `setStyleSheet()`. Inline style có độ ưu tiên cao hơn nên quy tắc chung có thể
   bị vô hiệu hóa.

2. Dark và light theme bị lặp gần như toàn bộ

   Hai file QSS có cấu trúc rất giống nhau, dẫn đến nguy cơ sửa một theme nhưng
   quên theme còn lại. Hai theme cũng đang có một số selector không tương xứng.

3. Selector trùng nằm ở nhiều vị trí

   Một số selector được tách thành base và variant có chủ đích, nhưng nhiều quy
   tắc phụ thuộc vào thứ tự xuất hiện trong file. Điều này khiến cascade khó theo
   dõi và dễ phát sinh override ngoài ý muốn.

4. Hệ thống màu chung chưa đầy đủ

   `ui/theme.py` chỉ chứa một phần nhỏ màu dark theme. Các màn hình tự khai báo
   lại những màu như success, warning, danger, buy, sell, text và border.

5. Component dùng chung chưa thực sự quản lý giao diện

   Nhiều class trong `ui/components` chỉ kế thừa widget mà chưa quy định role,
   density hoặc trạng thái. Riêng `InfoCard` là component dùng chung nhưng vẫn tự
   đọc settings và tạo stylesheet cho từng instance.

6. Theme được xử lý phân tán

   Nhiều màn hình tự gọi `SettingsService`, tự xác định light/dark rồi tự dựng
   stylesheet. Việc refresh theme vì vậy phụ thuộc vào từng màn hình.

7. Test đang khóa vào cách cài đặt CSS

   Một số test kiểm tra trực tiếp chuỗi inline CSS. Khi chuyển sang QSS chung,
   chúng cần được đổi sang kiểm tra object property hoặc giao diện hiệu lực.

## 4. Phân loại style

Không nên chuyển cơ học tất cả style vào QSS.

### 4.1. Nên chuyển vào QSS chung

- Font-size, font-weight và font-family cố định.
- Nền, border, border-radius và padding cố định.
- Style tĩnh của button, label, input, card, table, tab, dialog và scroll area.
- Các variant có thể biểu diễn bằng object name hoặc dynamic property.
- Trạng thái hover, pressed, checked, focus và disabled.
- Nền dialog theo theme.

### 4.2. Nên dùng semantic token và dynamic property

- Success, warning, danger và neutral.
- Buy, sell và breakeven.
- Active, selected, highlighted và dimmed.
- Trạng thái kết nối, validation và chất lượng dữ liệu.

Ví dụ:

```python
widget.setProperty("tone", "danger")
widget.setProperty("state", "active")
```

Sau khi property thay đổi, widget cần được repolish theo một helper thống nhất.

### 4.3. Không thể chuyển trực tiếp sang Qt QSS

- Màu từng cell phụ thuộc vào giá trị lời/lỗ.
- Màu đường và vùng trong biểu đồ Matplotlib.
- CSS bên trong `QTextEdit.setHtml()` hoặc WebEngine HTML.
- Màu semantic được tạo theo dữ liệu runtime.

Các trường hợp này vẫn cần tạo động trong Python hoặc HTML, nhưng phải lấy màu,
typography và spacing từ token/theme chung, không ghi mã HEX tùy ý trong từng
màn hình.

## 5. Kiến trúc mục tiêu

Không nên dồn toàn bộ quy tắc vào một QSS khổng lồ. Nguồn giao diện chung nên
được tổ chức thành base và theme overlay:

```text
ui/
├── styles/
│   ├── base.qss
│   ├── dark.qss
│   └── light.qss
├── theme.py
├── theme_manager.py
└── layout_system.py
```

Trách nhiệm của từng thành phần:

- `base.qss`: typography, kích thước, padding, border-radius, component và trạng
  thái không phụ thuộc màu.
- `dark.qss`: màu sắc dành riêng cho dark theme.
- `light.qss`: màu sắc dành riêng cho light theme.
- `theme.py`: semantic palette dùng trong Python, HTML và biểu đồ.
- `theme_manager.py`: nạp `base.qss` cùng theme overlay và cung cấp cơ chế refresh
  tập trung.
- `layout_system.py`: margin, spacing, chiều cao control và layout token.

Thứ tự nạp:

```text
base.qss → dark.qss
```

hoặc:

```text
base.qss → light.qss
```

## 6. Kế hoạch thực hiện

Tổng cộng 8 giai đoạn, từ Phase 0 đến Phase 7.

### Phase 0 — Khóa giao diện hiện tại ✅

Mục đích: tạo đường chuẩn để nhận biết việc chuyển style có làm thay đổi chức
năng hoặc làm hỏng giao diện hay không.

Thực hiện:

1. Chụp baseline tất cả màn hình, tab và dialog ở dark/light theme.
2. Ghi nhận hover, pressed, checked, disabled, focus và validation state.
3. Ghi nhận các trạng thái dữ liệu như success, warning, danger, buy và sell.
4. Lập allowlist những nơi được phép giữ style động.
5. Chạy toàn bộ test hiện tại và lưu kết quả baseline.
6. Chưa thay đổi giao diện hoặc logic trong phase này.

Tiêu chí hoàn thành:

- Có danh mục ảnh và trạng thái baseline.
- Có allowlist rõ ràng.
- Toàn bộ test hiện tại đạt hoặc các lỗi nền đã được ghi nhận.

### Phase 1 — Xây dựng hệ thống theme thống nhất ✅

Mục đích: tạo một nguồn semantic token dùng chung cho QSS, Python, HTML và biểu
đồ.

Thực hiện:

1. Mở rộng `theme.py` với palette cho dark và light.
2. Định nghĩa các role: surface, text, muted, border, accent, success, warning,
   danger, buy, sell và neutral.
3. Tạo `theme_manager.py`.
4. Tạo loader ghép `base.qss` với theme overlay.
5. Tạo helper cập nhật dynamic property và repolish widget.
6. Giữ tương thích với cơ chế chọn theme trong Settings.

Tiêu chí hoàn thành:

- Theme chỉ được xác định ở một nơi.
- Có API lấy semantic color dùng cho Python/HTML/chart.
- Việc đổi theme refresh được toàn bộ màn hình.

### Phase 2 — Làm sạch stylesheet hiện tại ✅

Mục đích: giảm trùng lặp và chuẩn hóa cascade trước khi chuyển inline style.

Thực hiện:

1. Phân nhóm selector theo shell, typography, form, button, card, table, tab,
   dialog và state.
2. Hợp nhất những selector trùng không cần thiết.
3. Tách base rule khỏi color overlay.
4. Kiểm tra parity dark/light.
5. Loại bỏ selector chắc chắn không còn được sử dụng.
6. Bổ sung selector chung cho các object đang phải style trực tiếp, gồm
   `InfoCard`, `BacktestResultText`, `BacktestVerdict`, `MarketBadge` và các
   Backtest dialog.

Tiêu chí hoàn thành:

- Mỗi selector có vị trí và mục đích rõ ràng.
- Không còn phụ thuộc vào override khó giải thích.
- Dark và light có cùng cấu trúc component/state.

### Phase 3 — Chuyển inline style tĩnh ✅

Mục đích: loại bỏ các `setStyleSheet()` không phụ thuộc dữ liệu.

Ưu tiên chuyển:

1. `background: transparent`.
2. `border: none`.
3. Font-size/font-weight cố định.
4. Padding và border-radius cố định.
5. Nền dialog theo theme.
6. Tab bar, scroll area và text panel tĩnh.
7. Nút khởi động lại.
8. Component `InfoCard`.

Biện pháp:

- Gắn object name hoặc property.
- Đưa selector vào QSS chung.
- Không thay đổi signal-slot hoặc logic runtime.

Tiêu chí hoàn thành:

- Không còn inline style tĩnh trong các file thuộc phạm vi phase.
- Giao diện trước/sau tương đương ở cả hai theme.

### Phase 4 — Chuẩn hóa component và trạng thái ✅

Mục đích: các widget cùng vai trò dùng chung một quy tắc giao diện.

Thực hiện:

1. Chuẩn hóa button role: primary, secondary, ghost, danger, link và icon.
2. Chuẩn hóa card role: panel, status, metric, warning và success.
3. Chuẩn hóa input density và validation state.
4. Chuyển các trạng thái runtime sang dynamic property.
5. Dùng helper repolish chung sau khi state thay đổi.
6. Không thay class widget hoặc kết nối signal nếu không cần thiết.

Tiêu chí hoàn thành:

- Cùng một role cho kết quả giống nhau trên mọi màn hình.
- Không có màn hình tự định nghĩa lại style của component chung.

### Phase 5 — Chuyển đổi theo từng cụm màn hình ✅

Mục đích: kiểm soát rủi ro bằng các đợt nhỏ.

Thứ tự:

1. `main_window`, `components`, `settings`.
2. `dashboard`, `orders`.
3. `journal`, `journal_detail`.
4. `backtest`.
5. `scanner`.
6. `scanner_detail` cuối cùng vì phạm vi lớn nhất.

Với mỗi đợt:

1. Di chuyển style.
2. Kiểm tra dark/light.
3. So sánh ảnh baseline.
4. Chạy test của màn hình.
5. Chỉ chuyển sang đợt tiếp theo khi đợt hiện tại đạt.

### Phase 6 — Chuẩn hóa HTML, bảng và biểu đồ ✅

Mục đích: xử lý các style không thể điều khiển trực tiếp bằng Qt QSS.

Thực hiện:

1. Tạo helper sinh CSS cho nội dung `setHtml()`.
2. Tạo template chung cho heading, paragraph, table, badge và warning block.
3. HTML chỉ truyền nội dung và semantic role.
4. `QTableWidgetItem.setForeground()` lấy màu từ semantic palette.
5. Matplotlib và WebEngine dùng chart palette chung.
6. Loại bỏ mã HEX trùng lặp trong các hàm render.

Tiêu chí hoàn thành:

- HTML cùng loại có hình thức giống nhau giữa các màn hình.
- Màu dữ liệu vẫn phản ánh đúng ý nghĩa nghiệp vụ.
- Dark/light hoạt động đúng với HTML và biểu đồ.

### Phase 7 — Kiểm thử, dọn dẹp và khóa kiến trúc ✅

Mục đích: ngăn inline style và màu tùy ý quay trở lại.

Thực hiện:

1. Kiểm tra screenshot toàn bộ màn hình/dialog ở dark/light.
2. Kiểm tra độ phân giải đại diện cho màn hình 14", 15.6", 16", 24", 27" và
   32".
3. Kiểm tra hover, focus, pressed, disabled, checked và validation.
4. Chạy toàn bộ regression test.
5. Thêm kiểm tra CI không cho `setStyleSheet()` mới ngoài allowlist.
6. Thêm kiểm tra CI không cho literal màu mới trong screen ngoài allowlist.
7. Xóa helper/style cũ sau khi xác nhận không còn được sử dụng.
8. Cập nhật tài liệu quy chuẩn UI.

Tiêu chí hoàn thành:

- Không thay đổi chức năng hoặc signal-slot.
- Không có lỗi vỡ layout hoặc sai theme.
- Toàn bộ test đạt.
- Inline style còn lại đều có lý do và nằm trong allowlist.

## 7. Rủi ro và biện pháp kiểm soát

### Rủi ro 1 — Test đang kiểm tra chuỗi CSS

Một số test hiện kiểm tra trực tiếp inline stylesheet. Khi chuyển style, cần đổi
test sang kiểm tra object property, trạng thái hoặc giao diện hiệu lực.

### Rủi ro 2 — Chuyển nhầm style dữ liệu

Không chuyển cơ học màu lời/lỗ, buy/sell hoặc mức cảnh báo vào một selector tĩnh.
Phải giữ semantic state và lấy màu từ palette chung.

### Rủi ro 3 — HTML không chịu ảnh hưởng của Qt QSS

CSS bên trong `QTextEdit`/WebEngine phải dùng helper/template HTML riêng. Không
coi đây là ngoại lệ để tiếp tục khai báo màu tùy ý trong từng màn hình.

### Rủi ro 4 — Thay đổi đồng loạt quá lớn

Không chuyển cả 184 vị trí trong một lần. Mỗi cụm màn hình phải được hoàn thành,
so sánh và kiểm thử độc lập.

### Rủi ro 5 — Theme refresh không đồng bộ

Việc đọc Settings và refresh theme phải được tập trung vào Theme Manager, tránh
để từng màn hình tự đọc cấu hình và tự dựng QSS.

## 8. Đánh giá độ phức tạp

Độ phức tạp tổng thể: **cao**.

Nguyên nhân:

- Phạm vi trải rộng trên toàn bộ UI.
- Hai theme đang lặp gần như toàn bộ stylesheet.
- Nhiều style phụ thuộc trạng thái runtime.
- Scanner Detail và Backtest chứa lượng lớn HTML.
- Một số test phụ thuộc trực tiếp vào cách cài đặt CSS hiện tại.

Tuy nhiên, rủi ro có thể kiểm soát nếu thực hiện tuần tự theo 8 phase, có baseline
ảnh, allowlist và test cho từng cụm màn hình.

## 9. Nguyên tắc bắt buộc khi triển khai

- Không thay đổi chức năng hoặc logic nghiệp vụ.
- Không thay đổi signal-slot.
- Không thay đổi layout nếu không cần thiết cho việc chuẩn hóa style.
- Không chuyển style bằng tìm–thay hàng loạt thiếu kiểm chứng.
- Dark và light phải được thực hiện đồng thời.
- Mỗi thay đổi phải có test hoặc kiểm tra ảnh trước/sau.
- Chỉ giữ inline style khi có lý do kỹ thuật rõ ràng và đã đưa vào allowlist.
