# UI Style Guide

Tài liệu này là quy chuẩn bắt buộc khi thêm hoặc sửa giao diện AI Market
Analyst. Mục tiêu là giữ dark/light nhất quán, không phát sinh CSS cục bộ và
không làm vỡ bố cục ở các kích thước màn hình được hỗ trợ.

## 1. Kiến trúc style

- `ui/styles/base.qss`: typography, kích thước, padding, border-radius và quy
  tắc bố cục không phụ thuộc theme. Không đặt màu theme trong file này.
- `ui/styles/dark.qss` và `ui/styles/light.qss`: màu và trạng thái tương tác của dark
  và light theme. Hai overlay phải có contract selector tương ứng.
- `ui/theme.py`: nguồn semantic palette duy nhất cho Python, rich text và chart.
- `ui/theme_manager.py`: điểm duy nhất được phép gọi `setStyleSheet()` để nạp
  `base.qss` và overlay đang chọn.
- `ui/rich_text.py`: renderer chung cho nội dung HTML của label/text widget.

Không gọi `setStyleSheet()` trong screen, dialog hoặc component. Không thêm mã
màu HEX trực tiếp vào screen; dùng semantic palette, dynamic property và
selector QSS.

Theme overlay không được khai báo padding, margin, spacing, font, kích thước,
border-radius hoặc căn lề cho control tương tác. Các thuộc tính trình bày này phải
nằm trong `ui/styles/base.qss`; overlay chỉ được thay đổi màu, border màu và trạng
thái tương tác theo theme.

## 2. Quy tắc component và trạng thái

- Dùng `objectName` cho kiểu component ổn định và dynamic property cho trạng
  thái dữ liệu như `success`, `warning`, `danger`, `buy`, `sell`.
- Sau khi đổi dynamic property, dùng helper trong `ui/theme_manager.py` để
  repolish widget.
- Mọi control tương tác phải có biểu diễn phù hợp cho: default, hover, focus,
  pressed, disabled, checked và validation.
- Input một dòng dùng `validationState="invalid"` cho dữ liệu không hợp lệ.
  Viền dark theo thang `#475569 → #64748b → #38bdf8`; viền light theo thang
  `#B5B0A6 → #A19B90 → #0284C7`. Trạng thái invalid dùng màu danger của theme,
  còn invalid + disabled phải hiển thị như disabled.
- Bảng, biểu đồ Qt, Matplotlib và WebEngine lấy màu từ `ThemePalette` hoặc
  `chart_palette()`, không duy trì palette riêng.
- Rich text phải đi qua `set_rich_html()`, `compile_rich_html()` hoặc template
  dùng chung; không đưa HTML có style tùy ý trực tiếp vào widget.
- Icon trên nút/thẻ phải là glyph phẳng từ `ui/icons.py` (`flat_icon`,
  `flat_pixmap`, `FlatIconEngine`) — monochrome, tint theo semantic role,
  tự đổi màu khi đổi theme. Không dùng emoji làm icon nút; thêm glyph mới
  vào registry `ICONS` (viewBox 24, stroke-based) thay vì hardcode asset.
  Module `ui/icons.py` giữ 0 hex literal — màu resolve từ palette.

## 3. Bố cục

- Ưu tiên `QGridLayout`, `QVBoxLayout`, `QHBoxLayout`, stretch và `SizePolicy`.
- Dùng token và helper trong `ui/layout_system.py` cho margin, spacing, control,
  button, table, progress và dialog.
- Input một dòng, action button và tab thông thường phải render đúng 24 px;
  editor trong bảng, nút trợ giúp/icon, chip và control compact render đúng
  20 px. Chiều cao và padding do `ui/styles/base.qss` sở hữu, không đặt trực tiếp
  trong screen/dialog/component.
- Các helper `configure_control()`, `configure_button()`, `configure_checkbox()` và
  `configure_help_button()` chỉ quản lý layout policy, chiều rộng và icon; tuyệt đối
  không gọi API đặt chiều cao hoặc kích thước cố định cho control tương tác.
- Chỉ được đặt chiều cao bằng Python cho ngoại lệ có bản chất bố cục như chart,
  text nhiều dòng, progress, table/header, thành phần kết cấu hoặc container/dialog.
  Ngoại lệ mới phải được audit và review, không dùng để thay thế contract 24/20 px.
- Không dùng `move()`, `resize()` hoặc `setGeometry()` để căn giao diện thông
  thường.
- Nội dung dài phải co giãn, word-wrap, dùng scroll area hoặc tách thành nhiều
  hàng hợp lý; không để control chồng lấn.

Ma trận responsive bắt buộc gồm 14", 15.6", 16", 24", 27" và 32" cho cả dark
và light theme. Báo cáo chuẩn nằm tại `docs/ui/reports/ui-responsive-report.json`.

## 4. Ngoại lệ

Ngoại lệ chỉ hợp lệ khi có lý do kỹ thuật và được ghi trong
`docs/ui/style/ui-style-allowlist.json`. Không thêm ngoại lệ tạm thời sau Phase 7. Các
nhóm hợp lệ hiện tại là loader stylesheet tập trung, semantic palette, runtime
chart palette và rich-text template đã được review.

## 5. Kiểm tra trước khi hoàn thành thay đổi UI

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python tools/ui_style_audit.py --check docs/ui/style/ui-style-lock.json
python tools/ui_density_audit.py --check docs/ui/density/ui-density-lock.json --validate-contract
python tools/ui_layout_audit.py --write docs/ui/reports/ui-responsive-report.json
python tools/capture_ui_density_visuals.py --suite --replace `
  --output docs/ui/baseline/density-phase6 --viewport 1366x768
python -m pytest -q tests/test_ui_density_phase5.py
python -m pytest -q tests/test_ui_density_phase6.py
python -m pytest -q tests/test_ui_style_phase7.py
python -m pytest -q
```

Nếu thay đổi hình thức có chủ đích, chụp lại dark/light bằng
`tools/capture_ui_style_baseline.py`, kiểm tra trực quan rồi tạo lại manifest.
Chỉ cập nhật `docs/ui/style/ui-style-lock.json` khi thay đổi kiến trúc đã được review;
không cập nhật lock chỉ để làm test hết lỗi.

## 6. Location target — chưa triển khai, 09/09/2026

Nội dung và trạng thái lấy từ
[screen design — Location target](screen_design.md) và
[plan Location](../plans/location-scoring-upgrade-plan.md). Bản đầu thêm phần
giải thích gọn trong breakdown hiện có, không thêm màn hình/dashboard riêng.

- Giữ typography, spacing, theme và component chung ở §1–§3; không hardcode
  màu hay chiều cao để chứa detail.
- Có nhãn chữ phân biệt điểm 0 hợp lệ, xung đột, thiếu dữ liệu và bản lưu cũ;
  màu chỉ hỗ trợ, không thay cho lý do bằng chữ.
- Hiển thị raw/25 và contribution thành hai thông tin phân biệt; khoảng cách
  phải có đơn vị ATR, giá phải có nhãn close H1/thời điểm.
- Nội dung dài dùng wrap/tooltip phù hợp. Không yêu cầu chart overlay hay
  bảng cấu hình nâng cao cho bản đầu.
- Khi thực sự sửa UI, làm kiểm tra liên quan ở §5 và task 26–28 của plan;
  mốc R4 sau task 28 là bắt buộc. Lần đồng bộ Markdown này không phải bằng
  chứng UI đã được triển khai hoặc đã kiểm tra trực quan.
