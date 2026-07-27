# Dark Theme Surface Audit

Ngày điều tra: 27/07/2026
Trạng thái: Phase 0 đến Phase 5 hoàn thành.

## 1. Mục đích

Tạo inventory có thể kiểm chứng cho hiện tượng ứng dụng đang dùng dark theme
nhưng một số vùng vẫn lấy nền sáng. Phase này chỉ xác định vị trí, mức độ và
nguyên nhân; việc sửa được thực hiện từ Phase 1.

## 2. Phạm vi và phương pháp

- Đối chiếu 40 ảnh dark hiện tại: 8 màn hình, các tab, 14 dialog và 7 ảnh trạng
  thái component.
- Quét ảnh bằng `tools/ui_dark_surface_audit.py`.
- Pixel được coi là neutral-bright khi mọi kênh có giá trị tối thiểu 215 và độ
  lệch giữa các kênh không quá 30.
- Chỉ cảnh báo khi một vùng neutral-bright liên tục chiếm ít nhất 0,5% ảnh. Cách
  này bỏ qua phần lớn chữ/icon sáng nhưng phát hiện viewport, canvas và khoảng
  nền sáng lớn.
- Kiểm tra thủ công ảnh bị cảnh báo và đối chiếu QSS, object name, palette,
  WebEngine và Matplotlib trong code.

Báo cáo máy đọc được nằm tại `docs/dark-surface-report.json`.

## 3. Kết quả tổng hợp

- Đã kiểm tra: 40/40 ảnh dark trong manifest.
- Bị cảnh báo: 13 ảnh.
- Lỗi giao diện sản phẩm xác nhận được: 6 màn hình/tab.
- Lỗi của visual-test harness: 7 ảnh state gallery.
- Không phát hiện dialog nào có mảng nền sáng liên tục vượt ngưỡng 0,5%. Các
  control sáng nhỏ vẫn được kiểm tra bằng code review riêng.

## 4. Inventory lỗi giao diện sản phẩm

| ID | Màn hình/trạng thái | Tỷ lệ vùng sáng lớn nhất | Kết luận nguyên nhân | Phase xử lý |
|---|---|---:|---|---|
| DS-01 | Backtest — tab Đường cong vốn | 55,92% | `FigureCanvas` mang nền trắng mặc định từ lúc khởi tạo; màu semantic chỉ được đặt khi đã có dữ liệu và vẽ biểu đồ. | Phase 3 |
| DS-02 | Chi tiết kết quả quét — Tổng quan | 9,55% | Cột thông tin bên trái là `QWidget` không có semantic surface. Phần trống dưới các card lộ nền/palette sáng mặc định bên trong `QScrollArea` và `QSplitter`. Đây là vùng sáng người dùng đã phản ánh, không phải chart. | Phase 1/4 |
| DS-03 | Chi tiết nhật ký | 1,64% | `MainDetailScrollWidget` trong suốt nhưng viewport của `QScrollArea#MainDetailScroll` chưa có nền dark; khoảng spacing giữa card lộ nền trắng. | Phase 1/4 |
| DS-04 | Cài đặt — tab AI | 1,10% | Danh sách provider là `QListWidget#DataTable`, trong khi selector `DataTable` hiện chủ yếu áp cho `QTableView/QTableWidget`; viewport danh sách vẫn lấy màu hệ điều hành. | Phase 1/4 |
| DS-05 | Quét thị trường | 0,96% | Bảng chính là `QTableView#EconTable`; dark QSS có scrollbar dọc nhưng thiếu contract cho scrollbar ngang, làm track ngang hiển thị trắng. | Phase 1/4 |
| DS-06 | Backtest — Nghiên cứu nâng cao | 0,81% | `QScrollArea` và content widget của tab chưa có semantic surface, làm các gutter ngang/trên lộ nền sáng. Các `HelpButton` cũng đang dùng cùng nền sáng ở cả dark và light overlay. | Phase 1/4 |

## 5. Lỗi của baseline/harness

Các ảnh `state-default`, `state-focus`, `state-hover`, `state-pressed`,
`state-disabled`, `state-checked` và `state-validation` có vùng sáng liên tục
81,86%. State gallery là top-level dialog độc lập và chưa được ThemeManager áp
dark stylesheet. Vì vậy bảy ảnh này không phải bằng chứng dark hợp lệ.

Hệ quả: baseline Phase 7 có đủ tên trạng thái nhưng chưa đủ giá trị để phát hiện
lỗi theme ở component độc lập. Harness phải được sửa trước khi chốt baseline
mới ở Phase 5.

## 6. Điểm mù cần xử lý

### WebEngine của Chi tiết kết quả quét

Harness đặt `QT_QPA_PLATFORM=offscreen`, còn `AnalysisChartView` chủ động tắt
WebEngine trong chế độ này. Ảnh baseline hiện chỉ chụp fallback label, không
chụp chart thật.

Code review cho thấy:

- `QWebEnginePage` đang dùng nền trong suốt.
- `html`, `body`, chart wrapper và chart container đều bắt buộc trong suốt.
- Màu nền chỉ được quyết định sau khi payload chart được gửi.

Do đó vẫn có nguy cơ lóe nền trắng hoặc hiện nền trắng ở loading/empty/error.
Thử capture WebEngine thật từ tiến trình kiểm thử riêng không tạo được ảnh ổn
định; đây được ghi nhận là coverage gap bắt buộc của Phase 2, không được coi là
đã đạt chỉ vì ảnh offscreen đang tối.

### Popup native

`QFileDialog` native có thể do Windows tự vẽ và không hoàn toàn chịu QSS. Cần
phân biệt dialog Qt có thể theme hóa với dialog native theo hệ điều hành. Các
`QMessageBox`, tooltip và dialog Qt hiện có selector dark nhưng vẫn phải kiểm tra
trực quan ở Phase 4.

### Vùng sáng nhỏ dưới ngưỡng

`QPushButton#HelpButton` trong dark overlay đang dùng nền `#e2e8f0`, giống light
overlay. Mỗi nút nhỏ hơn ngưỡng diện tích nên không làm ảnh bị cảnh báo, nhưng
vẫn là điểm không nhất quán cần xử lý trong Phase 4.

## 7. Kế hoạch còn lại

1. Phase 1 — áp palette/nền mặc định tập trung cho QApplication, root, viewport,
   scroll content, list/table và popup.
2. Phase 2 — sửa WebEngine/chart cho loading, empty, error, populated và hot
   theme switch.
3. Phase 3 — sửa nền khởi tạo và refresh của Matplotlib Backtest/Journal.
4. Phase 4 — xử lý sáu lỗi đã xác nhận và rà soát các control nhỏ còn lọt màu.
5. Phase 5 — sửa harness, chụp baseline mới, thêm visual guard, responsive và
   full regression.

## 8. Tiêu chí đóng Phase 0

- Có report quét đủ 40 ảnh dark: đạt.
- Có phân loại product issue và harness issue: đạt.
- Xác định được vùng người dùng phản ánh ở Chi tiết kết quả quét: đạt.
- Có danh sách coverage gap WebEngine/native dialog: đạt.
- Có unit test cho detector và kiểm tra report bao phủ manifest: đạt.
- Chưa thay đổi UI, logic hoặc signal-slot: đạt.

## 9. Lệnh kiểm tra

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/ui_dark_surface_audit.py --write docs/dark-surface-report.json
python -m pytest -q tests/test_ui_dark_surface_phase0.py
```

Công cụ trả mã khác 0 khi còn ảnh bị cảnh báo; đây là hành vi mong muốn trước
khi các Phase 1–4 xử lý xong.

## 10. Kết quả Phase 1 — Nền Qt mặc định

Phase 1 đã chuẩn hóa lớp fallback của Qt mà không thay đổi logic hoặc
signal-slot:

- Thêm `build_qpalette()` trong `ui/theme_manager.py`, ánh xạ semantic palette
  sang các role Window, Base, AlternateBase, Text, Button, Highlight, Tooltip,
  Link, Placeholder và màu disabled.
- `ThemeManager.apply()` hiện cập nhật đồng thời application palette, root
  palette và QSS. Widget trung gian, viewport hoặc popup không có selector riêng
  sẽ không còn lấy light palette của Windows.
- Bổ sung selector đối xứng cho dark/light đối với `QAbstractScrollArea`,
  viewport, `QAbstractItemView`, scrollbar ngang/dọc, splitter và menu.
- Không thêm `setStyleSheet()` cục bộ trong screen/component.

Đo lại các ảnh thuộc Phase 1 bằng cùng detector:

| Màn hình | Trước Phase 1 | Sau Phase 1 | Kết quả |
|---|---:|---:|---|
| Chi tiết kết quả quét — Tổng quan | 9,5456% | 0,0064% | Không còn cảnh báo |
| Chi tiết nhật ký | 1,6433% | 0,0064% | Không còn cảnh báo |
| Cài đặt — tab AI | 1,1042% | 0,0044% | Không còn cảnh báo |
| Quét thị trường | 0,9600% | 0,0064% | Không còn cảnh báo |
| Backtest — Nghiên cứu nâng cao | 0,8139% | 0,0178% | Không còn cảnh báo |

`Backtest — Đường cong vốn` chưa được sửa trong Phase 1 vì đây là nền của
Matplotlib, không phải Qt fallback surface. Hạng mục này vẫn thuộc Phase 3.
Tại thời điểm đóng Phase 1, WebEngine thật chưa thay đổi; hạng mục này nay đã
được xử lý trong Phase 2 như mô tả tại mục 11.

Kiểm thử Phase 1 nằm tại `tests/test_dark_theme_surface_phase1.py`, bao phủ:

- Mapping semantic palette sang `QPalette` ở cả dark/light.
- Application và descendant palette khi hot-switch theme.
- Contract selector dark/light cho các họ surface mặc định.
- Guard không cho screen tái sử dụng stylesheet cục bộ.

Ảnh trong `docs/ui-baseline/current` vẫn là baseline Phase 0 để giữ bằng chứng
before/after. Baseline chính chỉ được thay thế đồng bộ dark/light sau khi hoàn
tất Phase 2–4 và kiểm định ở Phase 5.

## 11. Kết quả Phase 2 — WebEngine chart của Chi tiết kết quả quét

Phase 2 đã loại bỏ nguồn gây lóe/vùng sáng trong biểu đồ WebEngine mà không thay
đổi dữ liệu phân tích hoặc signal-slot:

- `QWebEnginePage` nhận màu nền semantic hiện hành trước khi nạp HTML, không còn
  dùng nền trong suốt.
- HTML chart được bootstrap với class `dark-theme`/`light-theme`, biến
  `--chart-background` và màu semantic trước lần vẽ đầu tiên. `html`, `body`,
  wrapper và container luôn có nền xác định trong cả hai theme.
- Chart view sở hữu theme của payload. Theme/palette cũ từ bên gọi không thể làm
  biểu đồ lệch với giao diện hiện hành.
- Hàng đợi JavaScript giữ toàn bộ lệnh phát sinh trước khi trang nạp xong và thực
  thi đúng thứ tự; thao tác cập nhật dữ liệu, đổi theme hoặc trạng thái không còn
  ghi đè lẫn nhau.
- Trạng thái rỗng và lỗi chủ động hủy chart cũ, xóa payload, ẩn trạng thái đối
  nghịch và ẩn tùy chọn vùng cấu trúc. Vì vậy dữ liệu cũ không còn nằm phía sau
  thông báo rỗng/lỗi.
- `ScannerDetailScreen.refresh_theme_styles()` chuyển theme nóng xuống WebEngine.
  Màu nền/chrome được cập nhật ngay và chart được dựng lại từ payload hiện tại để
  toàn bộ nến, EMA, mức giá và vùng dùng đúng palette mới.

Kiểm thử Phase 2 nằm tại `tests/test_dark_theme_surface_phase2.py`, bao phủ:

- Bootstrap dark/light trước lần vẽ đầu tiên.
- Contract nền tường minh và API loading/empty/error/theme của HTML chart.
- Màu nền trang WebEngine theo semantic palette.
- Hàng đợi JavaScript không làm mất lệnh và giữ đúng thứ tự.
- Quyền sở hữu theme/palette của chart view.
- Luồng chuyển theme nóng từ màn hình Chi tiết kết quả quét.

Đã kiểm tra cú pháp JavaScript bằng Node.js và chạy nhóm hồi quy liên quan với kết
quả 26 test đạt. Capture WebEngine thật vẫn là coverage gap của harness offscreen;
việc chụp/đối chiếu trực quan WebEngine thật trên Windows được giữ ở Phase 5. Phase
2 không sửa Matplotlib; hạng mục đó nay đã hoàn thành tại Phase 3 ở mục 12.

## 12. Kết quả Phase 3 — Biểu đồ Matplotlib

Phase 3 đã chuẩn hóa hai nơi nhúng Matplotlib là tab Đường cong vốn của Backtest
và biểu đồ hiệu suất trong Nhật ký:

- Thêm `ui/matplotlib_theme.py` làm contract dùng chung cho nền figure, axes,
  chữ, nhãn trục, offset, spine và legend. Màu lấy duy nhất từ semantic
  `chart_palette`, không tạo bảng màu riêng trong từng màn hình.
- Figure được nhận màu nền đúng theme ngay lúc khởi tạo, trước khi `FigureCanvas`
  được hiển thị. Điều này loại bỏ canvas trắng khi chưa chạy backtest hoặc chưa
  tải dữ liệu Nhật ký.
- Backtest luôn dựng trạng thái rỗng có nền semantic và thông báo rõ “Chưa có kết
  quả backtest để vẽ biểu đồ”. Khi có kết quả, đường equity, drawdown, lưới, trục
  và legend dùng palette hiện hành.
- `BacktestScreen.refresh_theme_styles()` vẽ lại equity chart khi đổi theme.
- `PerformanceChartWidget` lưu lại dữ liệu biểu đồ gần nhất và vẽ lại từ cache
  khi đổi theme; lựa chọn lọc theo mã không bị mất.
- `JournalScreen.refresh_theme_styles()` chuyển sự kiện hot-switch xuống chart.
- Trạng thái rỗng của hai biểu đồ Nhật ký không còn các tick 0–1 không mang ý
  nghĩa, chỉ giữ tiêu đề và thông báo dễ hiểu.

Kiểm thử Phase 3 nằm tại `tests/test_dark_theme_surface_phase3.py`, bao phủ helper
dùng chung, trạng thái rỗng của Backtest, dữ liệu cache của Nhật ký và chuyển
dark/light nóng. Nhóm hồi quy tập trung đạt 46 test.

Toàn bộ test suite sau thay đổi đạt `1688 passed, 12 skipped, 17 xfailed`; không
có test thất bại. Năm warning hiện hữu không liên quan đến Phase 3.

Đã chụp lại 6 ảnh dark ở độ phân giải 1440×900 cho Backtest, ba tab Backtest,
Nhật ký và tab Hiệu suất. Detector vùng sáng trả `flagged_count = 0`; riêng ảnh
tab Đường cong vốn giảm từ vùng sáng liên tục 55,92% trong baseline Phase 0 xuống
0,0049%. Ảnh kiểm chứng tạm không thay thế baseline chính; baseline dark/light
chỉ được cập nhật đồng bộ tại Phase 5.

## 13. Kết quả Phase 4 — Control nhỏ, dialog và popup

Phase 4 đã rà soát lại các surface sản phẩm còn lại sau khi xử lý Qt fallback,
WebEngine và Matplotlib:

- Chụp và quét 21 ảnh dark gồm các màn hình hiện có trong lượt capture ổn định,
  9 dialog runtime và 5 dialog explicit. Không ảnh nào có vùng sáng liên tục vượt
  ngưỡng 0,5% (`flagged_count = 0`).
- Đối chiếu thủ công ảnh dialog và quét toàn bộ khai báo `background` trong dark
  QSS để tìm control nhỏ nằm dưới ngưỡng detector.
- Phát hiện `QPushButton#HelpButton` vẫn dùng nền sáng `#e2e8f0` ở cả hai theme.
  Nút này xuất hiện thành các chấm trắng trong dialog Trailing Stop và phần trợ
  giúp Backtest. Dark overlay nay dùng nền `#1f2937`, chữ `#cbd5e1` và viền
  `#475569`; light overlay giữ surface sáng phù hợp.
- File picker tải kết quả Backtest trước đây dùng dialog native của Windows nên
  có thể hiện sáng trong dark theme. Lượt mở file nay dùng
  `QFileDialog.Option.DontUseNativeDialog`, nhờ đó dialog Qt nhận QPalette và QSS
  chung của ứng dụng.
- Xác nhận các contract cho `QDialog`, `QMenu`, `QCalendarWidget`, tooltip và
  `QMessageBox` tồn tại đối xứng ở cả dark/light.
- Không thay đổi chức năng tải file, dữ liệu Backtest, logic giao dịch hoặc
  signal-slot.

Kiểm thử Phase 4 nằm tại `tests/test_dark_theme_surface_phase4.py`, gồm guard
không cho nền sáng trung tính quay lại dark QSS, kiểm tra pixel render thực của
HelpButton, cờ non-native của file picker và contract popup/message box. Nhóm hồi
quy dark-theme/style đạt 51 test.

Toàn bộ test suite sau Phase 4 đạt `1694 passed, 12 skipped, 17 xfailed`; không
có test thất bại. Năm warning hiện hữu không liên quan đến thay đổi này. Style
architecture lock và `git diff --check` đều đạt.

Một lượt capture lặp lại toàn bộ screen bị treo ở tiến trình harness sau khi đã
ghi một số ảnh, trong khi các lượt dialog và capture chọn lọc trước đó hoàn tất.
Tiến trình capture riêng đã được dừng, không tác động tới `main.py` đang chạy.
Việc làm cho harness hoàn tất ổn định, chụp lại đồng bộ dark/light và thay baseline
chính vẫn thuộc Phase 5.

## 14. Kết quả Phase 5 — Visual guard, baseline và responsive

Phase 5 đã chốt lớp kiểm chứng tự động cho toàn bộ thay đổi dark-theme:

- State gallery nhận `ThemeManager` theo theme trước khi chụp. Bảy ảnh trạng thái
  dark không còn dùng palette sáng giả như baseline Phase 0.
- `capture_ui_style_baseline.py --suite` cô lập từng route và nhóm dialog/state
  thành 22 tiến trình con, có timeout và retry. Output phải là thư mục trống để
  không trộn ảnh cũ; suite chỉ thành công khi có đúng 40 dark + 40 light với tập
  tên đối xứng.
- Cơ chế retry đã được kiểm chứng thực tế: job Backtest light timeout ở lượt đầu
  và hoàn tất đủ bốn ảnh ở lượt thứ hai, thay vì treo toàn bộ harness.
- Manifest lưu đúng canvas được yêu cầu, hỗ trợ đường dẫn output ngoài workspace
  và khóa SHA-256 cho từng ảnh.
- Baseline chính tại `docs/ui-baseline/current` đã được thay bằng 80 ảnh mới,
  không có failure. State default dark/light đã được kiểm tra trực quan.
- `docs/dark-surface-report.json` được tạo lại từ baseline mới: 40/40 ảnh dark,
  `flagged_count = 0`.
- `ui_layout_audit.py` cũng cô lập dark/light thành tiến trình riêng, có timeout
  và retry trước khi hợp nhất báo cáo. Lượt light đã timeout một lần rồi thành
  công; báo cáo cuối đạt 96/96 trường hợp, 0 lỗi.
- Thêm `tests/test_dark_theme_surface_phase5.py` khóa theme thật của state gallery,
  sơ đồ job cô lập, độ phủ/hashes của baseline, dark-surface report và ma trận
  responsive.

Kiểm thử mục tiêu Phase 5 và các guard liên quan đạt 35 test. Toàn bộ test suite
đạt `1699 passed, 12 skipped, 17 xfailed`; không có test thất bại. Năm warning
hiện hữu không liên quan đến thay đổi dark-theme. Style architecture lock và
`git diff --check` đều đạt.

### Giới hạn kiểm chứng WebEngine thật

Harness chuẩn vẫn chạy `QT_QPA_PLATFORM=offscreen`; `AnalysisChartView` chủ động
dùng fallback trong chế độ này. Phase 5 đã thử thêm một tiến trình Qt/Windows cô
lập để chụp QWebEngine thật, đặt cửa sổ ngoài vùng nhìn thấy, nhưng tiến trình
WebEngine kết thúc bất thường và không tạo ảnh. Thử nghiệm không ảnh hưởng tới
`main.py` đang chạy.

Vì vậy baseline tự động vẫn không chứa canvas WebEngine thật. Phần này được khóa
bằng contract/unit test của Phase 2: màu nền `QWebEnginePage`, bootstrap trước lần
vẽ đầu, nền HTML tường minh, trạng thái empty/error và hot theme switch. Việc xác
nhận pixel QWebEngine thật cần chạy trực tiếp màn hình Chi tiết kết quả quét trên
máy Windows có WebEngine hoạt động; đây là giới hạn môi trường kiểm thử đã biết,
không phải vùng sáng còn phát hiện trong baseline.
