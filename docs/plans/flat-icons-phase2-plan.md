# Kế hoạch Phase 2: Bộ icon phẳng cho 7 màn hình còn lại

> **TRẠNG THÁI: HOÀN THÀNH — 2026-09-03.** Phase 2 của đợt di cư emoji → icon phẳng
> (phase 1 dashboard đã hoàn thành + lưu tại `docs/plans/dashboard-flat-icons-plan.md`).
> Mỗi task gồm Phần 1 (mô tả + phân tích) và Phần 2 (tech leader review).

## Context (bối cảnh)

Phase 1 đã đưa dashboard sang icon phẳng và để lại hạ tầng dùng chung:
`ui/icons.py` (registry + `flat_icon`/`flat_pixmap`/`flat_icon_fixed` + `FlatIconEngine` lazy-tint),
`action_button(..., icon=, icon_role=, icon_disabled_role=)` trong `ui/screens/shared.py`.
7 màn còn lại (scanner, orders, settings, backtest, journal, journal_detail, scanner_detail)
vẫn còn **~75 nút `action_button` + 1 nút `QPushButton` trực tiếp** nhúng emoji trong text.
Phase 2 áp dụng đúng pattern phase 1 cho 7 màn; không thêm dependency; không đổi kiến trúc.

## Phạm vi (IN / OUT)

**IN** (xử lý đợt này):
- Mọi `action_button` có emoji → bỏ emoji khỏi text + truyền `icon=`/`icon_role=`.
- `QPushButton("🤖 Tự động vào lệnh MT5")` (scanner 871, `AutoTradeToggle`, checkable) → icon `bot`.
- setText động có emoji (reset nút) → bỏ emoji.
- Tiêu đề dialog/window, QLabel section titles, tab titles (QTabWidget.addTab) → bỏ emoji (KHÔNG thay bằng icon, giống phase 1).
- Checkbox `f"{symbol}  ✅"` (scanner 2175) → bỏ ✅.
- `NoteIconDelegate` (journal, vẽ 💬 bằng drawText) → vẽ pixmap `message-square` phẳng.
- Checklist icon QLabel ✅/❌/➖ (scanner_detail 1128/2195) → pixmap phẳng (pattern StatusIcon).
- `MissingRIcon` QLabel "⚠️" (journal 119) → pixmap `alert-triangle`.
- **Popup/dialog NGOÀI 7 màn hình**: `ui/main_window.py:171` sidebar
  `QPushButton("🔄 Khởi động lại")` (objectName `RestartButton`) → icon `refresh`;
  QMessageBox xác nhận restart của nó đã plain text (chỉ verify). Mọi dialog bật lên
  CỦA 7 màn được liệt kê tường minh trong từng task bên dưới (mục "Dialog phủ").

**OUT — follow-up** (ghi vào docs, KHÔNG đụng):
- Emoji trong rich-text HTML (backtest stats/verdicts, scanner_detail rich reports, scanner market-brief section icons 🌍⭐🚫…).
- Nhãn trạng thái BE/trailing trong bảng orders (`✅ BE`, `🟢 Trail Wide`… 685–718) — test `test_be_trailing_task6` đang khóa chuỗi này.
- KPI badge journal (🟢🎯… trong `PerformanceKPICard`).
- Emoji trong table cell data (`📋 {symbol}` scanner 266, tooltip 151/2138) → giữ nguyên.

## Bảng map emoji → glyph (dùng chung)

Glyph đã có (*): `refresh` (🔄/↻), `x` (❌/✖), `help-circle` (❓), `bot` (🤖), `bar-chart` (📊), `zap` (⚡).
Glyph MỚI cần thêm vào `ICONS` (21, feather/lucide-style, viewBox 24, stroke 2):
`search`🔍, `stop`⏹️, `clipboard`📋, `camera`📸, `check`✅, `crosshair`🎯, `trash`🗑️, `edit`✏️,
`alert-triangle`⚠️, `save`💾, `flask`🧪, `folder-open`📂, `play`▶️, `book-open`📖, `download`⬇️,
`arrow-left`⬅️, `upload`📤, `message-square`💬, `half`◐, `minus`➖. (🧹→`x`; 📐/💰/💵/🔬 chỉ gỡ emoji title, không cần glyph.)

## Quy tắc role (áp dụng chung, chốt từ phase 1)

- **PrimaryButton** (nền màu): `icon_role="selection_text"` + `icon_disabled_role="selection_text"`
  (id-selector thắng `QPushButton:disabled` → nền+text giữ màu khi disabled → icon trắng luôn).
- **SecondaryButton + btnColor=X**: `icon_role=X` (`danger`/`info`/`warning`), `icon_disabled_role=X`.
- **SecondaryButton thường** (nền trong suốt): `icon_role="text"`, `icon_disabled_role="text"`
  (QSS `#SecondaryButton` giữ màu text cả khi disabled).
- Không thêm objectName mới (giữ style-lock `object_name_calls` không tăng).

---

## Danh sách công việc

### P2-T0 — Lưu kế hoạch vào `docs/plans/flat-icons-phase2-plan.md`
**Phần 1**: Copy kế hoạch này vào docs/plans/ (convention tiếng Việt giống phase 1). Bước đầu sau duyệt.
**Phần 2 — Review**: file tồn tại; đủ mục phạm vi IN/OUT, bảng glyph, quy tắc role, 12 task, verification.

### P2-T1 — Thêm 21 glyph mới vào `ui/icons.py`
**Phần 1**: Mở rộng `ICONS` bằng 21 glyph trên (path data feather/lucide: search=circle+line, stop=square, clipboard, camera, check=polyline, crosshair, trash-2, edit-2, alert-triangle, save, flask-conical, folder-open, play, book-open, download, arrow-left, upload, message-square; `half`=circle+line dọc; `minus`=line ngang). Giữ 0 hex literal.
**Phân tích**: Tách riêng để khóa contract bằng test trước khi đụng screens.
**Phần 2 — Review**: chạy lại `pytest -q tests/test_flat_icons.py` (test registry tự phủ glyph mới: mọi entry render được + chứa currentColor); grep hex = 0; smoke offscreen render 21 glyph × 3 role.

### P2-T2 — scanner_screen.py
**Phần 1**: Nút (dòng → glyph/role-class): 843 search/sel; 885 search/sel; 887 stop/sel; 891 clipboard/sel; 1153 zap/sel; 1367 x/sec-danger; 1483 help-circle/sel; 1488 search/sel; 1491 camera/sel; 1494 bar-chart/sel; 1990 clipboard/sec-info; 1995 x/text; 2146 check/sel; 2147 x/sel; 2188 x/sec-danger; 2189 check/sel; 2272 x/text; 3212 x/text. Toggle 871: `QPushButton()` + `setIcon(flat_icon("bot","text"))` giữ objectName `AutoTradeToggle` + checkable. Reset: 1144 → "Thử lại"; 1856 → "Quét thị trường". 2175 bỏ " ✅". Titles: 1063/1189 bỏ 📋; 1924 bỏ 📊.
**Dialog phủ**: orders dialog (title 1063, OrderDialogTitle 1189, Vào lệnh 1153 + reset 1144, Đóng 1367); market-brief dialog (1924, Sao chép 1990, Đóng 1995); symbol-selection dialog (2146/2147/2188/2189 + checkbox 2175); columns-help (2272); row-explanation (3212). Rich-text body của market-brief (🌍⭐🚫…) = OUT.
**Phân tích**: `sel` = cặp role selection_text (primary); `sec-*` = secondary theo bảng role. Giữ nguyên signal/objectName.
**Phần 2 — Review**: grep emoji nút trong file = 0 (chừa OUT-scope); test `test_scanner_toolbar_layout`, `test_scanner_auto_trade_toggle`, `test_scanner_columns_help_dialog` xanh; smoke offscreen instantiate scanner với `_fake_app` (pattern tools/capture_ui_style_baseline.py) — mọi PrimaryButton có icon non-null.

### P2-T3 — orders_screen.py
**Phần 1**: 226 refresh/sel; 230 crosshair/sel; 235 trash/sel; 241 edit/sel; 247 half/sel; 253 x/sel; 258 x/sel; 263 edit/sel; 270 trash/sel; 277 alert-triangle/sel; 1308 x/sec-danger; 1313 refresh/sel; 1320 stop/sel; 1341 check/sel. Titles bỏ emoji: 128/131/134/137/140/143 (MiniStat), 855/865 🎯, 1123 🎯, 1150 📐, 1218 ✅, 1222 ⚠️, 1226 🟢, 1230 🟡, 1923 ⚠️. KHÔNG đụng phase_display/fallback 685–718 (OUT).
**Dialog phủ**: trailing dialog (title 855, ActionTitle 865, Đóng 1308, Cập nhật 1313, Tắt 1320, Bật 1341); Break-Even dialog (1123, status setText 1218/1222/1226/1230); flatten confirm QMessageBox (1923). Nhãn BE/trailing trong BẢNG (685–718) = OUT.
**Phần 2 — Review**: `pytest -q tests/test_orders_screen_enable_sync.py tests/test_order_management_settings_ui.py` xanh; smoke orders với `_fake_app`; bảng positions col 9 giữ nguyên chuỗi BE (grep "✅ BE" còn đúng chỗ cũ).

### P2-T4 — settings_screen.py
**Phần 1**: 176 refresh/sel; 186 flask/sel; 187 save/sel; 556 refresh/sel; 559 save/sel; 563 refresh/sel; 757 search/sel; 760 clipboard/sec-warning; 767 save/sel; 1307 save/sel; 1563 save/sel; 1588 save/sel; 1765 save/sel; 1910 save/sel. Reset 476 → "Kiểm tra". Tabs 92–97 bỏ emoji (🤖🔌💼🛡️⚙️). 1103 bỏ 💾 trong câu thông báo.
**Phần 2 — Review**: smoke settings với `_fake_app`; tab count = 6, tabText không emoji; `test_order_management_settings*` xanh; nút 563 KHÔNG phải RestartButton của main_window (không đụng main_window).

### P2-T5 — backtest_screen.py + core/backtest_presentation.py
**Phần 1**: Labels nguồn: `core/backtest_presentation.py:136` "📋 Áp dụng cấu hình"→"Áp dụng cấu hình", `:143` "💾 Lưu đề xuất nháp"→"Lưu đề xuất nháp"; GIỮ `backtest_screen.py:1376` `.replace("📋 ","").replace("💾 ","")` (chịu nhãn emoji do test monkeypatch). Nút: 244 search/sel; 303 play/sel; 312 clipboard/sel; 483 folder-open/sel; 619 bot/sel; 760 play/sel; 779 folder-open/sel; 3044 x/sec-danger; 3045 check/sel; 1484 → `action_button(action.label, primary=True, icon="clipboard" if action.kind==ACTION_APPLY else "save", icon_role="selection_text", ...)` (kiểm tên constant thật khi làm). Reset: 922/2441 → "Đang chạy..."; 948/958 → "Chạy quét"; 1224 → "Đang phân tích"; 1244/1301/1310 → "Phân tích AI"; 2465 → "Chạy"; 2592 giữ (label giờ sạch). Tabs 496/500/515/519 bỏ emoji.
**Dialog phủ**: backtest-config dialog (title 1376, apply 1484, re-arm 2592); AI analysis dialog (619, reset 1224/1244/1301/1310, Đóng 1291); symbol dialog (3044/3045). Rich-text stats/verdict body (1817+) = OUT.
**Phần 2 — Review**: `pytest -q tests/test_backtest_screen_layout.py tests/test_backtest_screen_improvements.py` xanh KHÔNG sửa test; smoke backtest với `_fake_app`; dialog config title vẫn sạch emoji với cả nhãn monkeypatch có emoji.

### P2-T6 — journal_screen.py (+ NoteIconDelegate)
**Phần 1**: Nút: 128 edit/sel; 734 play/text; 738 x/text; 1138 search/sel; 1142 download/sel; 1212 book-open/text; 1216 refresh/text; 1220 download/sel; 1373 x/text; 1850/1876/2039 x/text. `NoteIconDelegate.paint()`: thay `drawText(💬)` bằng `painter.drawPixmap` pixmap từ API mới `flat_pixmap_fixed("message-square", palette.warning hoặc palette.accent_hover khi hover, size=16)` (thêm hàm này vào ui/icons.py — nhận hex ĐỘNG từ palette, không hardcode). Model 480 "📝"→"" (delegate vẽ icon). Titles bỏ emoji: 1246 🟢, 1273 🔵, 1298 📊, 1318 📑, 1357 📋. `MissingRIcon` 119: QLabel() + `setPixmap(flat_pixmap("alert-triangle","warning"))`; thêm re-tint vào `refresh_theme_styles` (journal 322). KHÔNG đụng KPI badge (OUT).
**Dialog phủ**: 3 QMessageBox "❌ Đóng" (1850/1876/2039) + MissingRBanner CTA (128).
**Phần 2 — Review**: `pytest -q tests/test_journal_feedback.py tests/test_monthly_breakdown.py` xanh; smoke journal với `_fake_app` render vài row có note → delegate vẽ pixmap non-null; theme switch re-tint MissingRIcon.

### P2-T7 — journal_detail_screen.py
**Phần 1**: 131 arrow-left/text; 132 upload/text; 133 trash/sel; 311 save/sel; 530 save/sel; 888/900/911 x/text. Card titles 238/246/254/299/318 bỏ emoji.
**Dialog phủ**: 3 QMessageBox "❌ Đóng" (888/900/911) — nút và title đều sạch emoji sau task.
**Phần 2 — Review**: smoke journal_detail với `_fake_app`; 5 card PanelTitle không emoji; test journal_detail liên quan xanh.

### P2-T8 — scanner_detail_screen.py
**Phần 1**: 242 clipboard/sel (giữ override objectName `ScannerDetailFullButton` ở 243); 343 search/sel; 361 arrow-left/text; 362 save/sel; 363 upload/text; 1151 x/text. Tabs 328/336/356 bỏ emoji. Titles bỏ emoji: 735/750 📋, 919 🔍, 943 🌐, 1072 🟢, 1079 🔴, 1100 🔍, 1993 🎯, 2068 📊, 2145 🔍, 2170 ⚠️, 2176 ➖. Checklist icon 1128/2195 (QLabel ✅/❌/➖) → `setPixmap(flat_pixmap("check"/"x"/"minus", role success/danger/muted))` (pattern StatusIcon; giữ mọi property/objectName hiện có).
**Dialog phủ**: scan-detail dialog (title 735, ScannerDialogTitle 750, Đóng 1151) + checklist panel (1100/1128/2170/2176/2195). Rich-text audit reports (2717+) = OUT.
**Phần 2 — Review**: `pytest -q tests/test_scanner_detail_entry_checklist.py tests/test_scanner_detail_v4_diagnostics.py` xanh KHÔNG sửa test (chỉ assert logic, không assert emoji — xác nhận khi làm); smoke scanner_detail với `_fake_app`.

### P2-T9 — ui/main_window.py: RestartButton (popup/dialog ngoài 7 màn)
**Phần 1**: `main_window.py:171` `QPushButton("🔄 Khởi động lại")` → `QPushButton("Khởi động lại")` + `setIcon(flat_icon("refresh", "accent"))` + `setIconSize(16)`; giữ objectName `RestartButton` + mọi kết nối. Nền trong suốt, text màu accent (dark #0d9488 / light #D94625, id-selector thắng cả `:disabled`) → `icon_role="accent"`, `icon_disabled_role="accent"`. QMessageBox xác nhận restart (204–209) đã plain text — verify không đổi. Cập nhật `tests/test_restart_button_style.py`: thay literal token grep `QPushButton("🔄 Khởi động lại")` → `QPushButton("Khởi động lại")`, thêm assert `setIcon`/`flat_icon` xuất hiện trong block (test khóa chi tiết cài đặt nên phải đổi theo quyết định kiến trúc đã duyệt).
**Phân tích**: Đây là widget emoji DUY NHẤT ngoài 7 screens; đưa vào để sau phase 2 toàn app không còn emoji làm icon nút.
**Phần 2 — Review**: `pytest -q tests/test_restart_button_style.py` xanh sau cập nhật; smoke main_window offscreen (pattern test hiện có) — RestartButton icon non-null; sidebar layout không tràn (nút nằm footer sidebar).

### P2-T10 — Test khóa phase 2: `tests/test_phase2_flat_icons.py`
**Phần 1**: (a) Static scan nguồn 7 file screens + `ui/main_window.py`: regex emoji trong literal `action_button(` và `QPushButton(` = 0 (chừa chuỗi OUT-scope bằng danh sách dòng cho phép rõ ràng); (b) instantiate 3 màn đại diện (scanner, orders, journal) với `_fake_app` (import từ tools.capture_ui_style_baseline) offscreen: mọi PrimaryButton có `icon().isNull()==False`, iconSize 16; (c) tab titles 3 màn có tabs không emoji; (d) `flat_pixmap_fixed` render đúng màu truyền vào.
**Phân tích**: Static scan rẻ + chắc; runtime instantiate chặn regression icon null.
**Phần 2 — Review**: pytest xanh offscreen; đọc test — danh sách dòng cho phép khớp đúng OUT-scope, không rộng hơn.

### P2-T11 — Audit + lock + baseline
**Phần 1**: `ui_style_audit --check` (object_name_calls không tăng; ui/icons.py 0 debt) → nếu tăng hợp lệ mới `--write-baseline`; `ui_density_audit --check --validate-contract`; `ui_layout_audit --write docs/ui/reports/ui-responsive-report.json` (288 checks, 0 issues); xóa + `capture_ui_style_baseline.py --suite` (80 captures) + regenerate `ui_dark_surface_audit --write`.
**Phần 2 — Review**: số liệu lock: dashboard+7 screens không phát sinh setStyleSheet/hex mới; report 288/0; manifest 80 captures 0 failure.

### P2-T12 — Kiểm tra trực quan baseline
**Phần 1**: Mở PNG dark+light của 7 screens: icon phẳng đúng màu nền (primary trắng, secondary theo tone), không vỡ layout khi label ngắn lại, tab titles sạch.
**Phần 2 — Review**: checklist mắt 7 screens × 2 theme; so sánh không overlap/đứt hàng (đặc biệt orders toolbar, settings header, backtest toolbar).

### P2-T13 — Full test suite
**Phần 1**: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`.
**Phần 2 — Review**: 0 failed; nếu đỏ → chẩn đoán root cause, KHÔNG sửa test cho qua; đối chiếu số pass với baseline 3676+ (tăng theo test mới).

### P2-T14 — Docs + follow-up
**Phần 1**: Cập nhật `docs/ui/screen_design.md` (note phase 2 hoàn thành, danh sách follow-up mới: rich-text emoji, BE/trailing labels, KPI badge); `docs/ui/style-guide.md` không đổi nếu không cần.
**Phần 2 — Review**: follow-up list đủ 3 mục; diff git chỉ gồm file dự kiến.

## Verification end-to-end (PowerShell)

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_flat_icons.py tests/test_phase2_flat_icons.py tests/test_dashboard_flat_icons.py
python tools/ui_style_audit.py --check docs/ui/style/ui-style-lock.json
python tools/ui_density_audit.py --check docs/ui/density/ui-density-lock.json --validate-contract
python tools/ui_layout_audit.py --write docs/ui/reports/ui-responsive-report.json
python -m pytest -q
python tools/capture_ui_style_baseline.py --suite
```
Soi PNG 7 screens × 2 theme trong `docs/ui/baseline/current/`.

## File đụng đến
- Sửa: `ui/icons.py`, `ui/screens/{scanner,orders,settings,backtest,journal,journal_detail,scanner_detail}_screen.py`, `core/backtest_presentation.py`, `ui/main_window.py`, `tests/test_restart_button_style.py`
- Mới: `tests/test_phase2_flat_icons.py`, `docs/plans/flat-icons-phase2-plan.md`
- Tái tạo: lock/report/baseline artifacts
- KHÔNG đụng: `services/`, rich-text blocks, dashboard (đã xong), requirements.txt
