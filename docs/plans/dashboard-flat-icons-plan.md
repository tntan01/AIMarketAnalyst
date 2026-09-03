# Kế hoạch: Bộ icon phẳng (flat SVG) cho Dashboard

> **TRẠNG THÁI: APPROVED — 2026-09-03.** Kế hoạch thực thi (runtime change), đã được
> owner duyệt. Phạm vi: chỉ màn hình Dashboard. Phương án B — SVG inline, không dùng
> thư viện icon bên thứ ba. File nguồn tham chiếu khi thực thi + tech leader review.

## Context (bối cảnh)

Dashboard (`ui/screens/dashboard_screen.py`) hiện dùng **emoji nhúng trong text** cho toàn bộ nút và icon trạng thái (🔄 ❓ 📍 🤖 ❌ 🔗 📅 🔌 👤 📊 ⚡). Emoji render theo font hệ thống (Segoe UI Emoji — nhiều màu, không phẳng), không đổi màu theo theme sáng/tối, không nhất quán về nét. Yêu cầu: chuyển các nút trên dashboard sang **giao diện phẳng với bộ icon phẳng monochrome**, tint theo semantic palette sẵn có.

**Phương án B (đã chốt)**: SVG inline — **KHÔNG** dùng thư viện icon bên thứ ba (không qtawesome).

**Phát hiện kỹ thuật then chốt (đã kiểm chứng bằng code chạy thật)**:
- `PyQt6.QtSvg` (QSvgRenderer) **đã khả dụng, zero dependency mới**: `QtSvg.pyd` nằm trong wheel `PyQt6`, `Qt6Svg.dll` nằm trong `PyQt6-Qt6` đã có sẵn. **Không thêm `PyQt6-QtSvg` vào requirements.txt** (trùng/shadow DLL).
- Test offscreen xác nhận: SVG dùng `stroke="currentColor"` → thay chuỗi bằng hex palette → `QSvgRenderer` render đúng màu (đã verify với `#10b981`).
- PyInstaller: `packaging/pyinstaller.spec` đã collect toàn bộ cây PyQt6/Qt6 (WebEngine kéo hết) → không cần sửa spec. Icon là **hằng chuỗi Python**, không phải file asset.
- QSS `color:` chỉ tint được TEXT glyph, **không tint được QIcon/QPixmap** → engine icon phải tự tint (cơ chế lazy-paint bên dưới).

## Kiến trúc chốt

### Module mới `ui/icons.py` (nguồn icon duy nhất)
- Registry `ICONS: dict[str, str]` — tên glyph → markup SVG (viewBox 24×24, `stroke="currentColor"`, stroke-width 2, round caps — feather-style, nét đẹp ở 16px).
- Template: `<svg xmlns="..." viewBox="0 0 24 24" fill="none">{body}</svg>`; hàm `_svg_bytes(name, color_hex)` thay `currentColor` → hex rồi encode.
- Cache: `_renderer_cache[(name, hex)]`, `_pixmap_cache[(name, hex, size, dpr)]` + `clear_icon_caches()`. Đổi theme → hex khác → key cache khác → **tự "invalidate" không cần signal** (app không có themeChanged signal).
- API công khai:
  - `flat_pixmap(name, role="text", *, size=16, palette=None) -> QPixmap` — resolve hex qua `color_for_role(palette or current_palette(), role)`, render QImage `size×dpr` ARGB32_Premultiplied + `setDevicePixelRatio`.
  - `flat_icon(name, role="text", *, size=16, disabled_role="muted", active_role=None) -> QIcon`.
- **`FlatIconEngine(QIconEngine)` — lazy tint (cơ chế trung tâm)**: `paint()` đọc `current_palette()` tại thời điểm vẽ → chọn role theo `QIcon.Mode` (Normal/Selected → role; Disabled → disabled_role; Active → active_role). Cùng tiền lệ với `NoteIconDelegate.paint()` trong journal_screen. Kết quả: **mọi QIcon tự đổi màu khi chuyển theme** (setStyleSheet gây repaint), không cần wiring refresh từng widget.
- **Ràng buộc style-lock**: `ui/icons.py` phải 0 hex literal, 0 `setStyleSheet` — màu đi qua `ui.theme.color_for_role` / `current_palette`.

### Bảng kiểm kê icon (12 glyph, chỉ dashboard)
| Tên | Thay emoji | Hình học | Dùng ở |
|---|---|---|---|
| `refresh` | 🔄 | mũi tên vòng ~300° + đầu chevron | Thử lại, Làm mới |
| `help-circle` | ❓ | vòng tròn + móc hỏi + chấm | Giải thích chỉ số |
| `map-pin` | 📍 | pin + chấm r=2.5 | Xem tin sắp tới |
| `bot` | 🤖 | đầu robot + anten + 2 mắt | nút AI, status card "AI" |
| `x` | ❌ | 2 đường chéo | Đóng ×3 |
| `plug` | 🔌 | 2 chân cắm + thân + dây | status card "Kết nối" |
| `user` | 👤 | đầu + vai | status card "Broker" |
| `bar-chart` | 📊 | 3 cột dọc | status card "Nguồn dữ liệu" |
| `external-link` | 🔗 | khung + mũi tên góc | NewsIconButton |
| `calendar` | 📅 | lịch (dự phòng) | — |
| `zap` | ⚡ | tia sét (dự phòng) | — |
| `eye` | — | mắt (dự phòng) | — |

### Điểm tích hợp (dashboard only)
1. **`action_button` (ui/screens/shared.py:86)** — thêm kwarg `icon=None, icon_role=None` (backward-compatible cho 87 call site màn khác). Có icon → `setIcon(flat_icon(...))` + `setIconSize(16)`.
2. **4 nút chính + 6 nút dialog** — bỏ emoji khỏi text, truyền `icon=`/`icon_role=`. Nút nền màu (Primary-info, DialogAiButton cam) dùng `icon_role="selection_text"` (= #ffffff cả 2 theme). Trạng thái "Đang tải..." (setText reset + button disabled) → engine Disabled mode tự render màu muted; **giữ icon, chỉ đổi text** (mọi `setText("⏳ Đang...")` phải bỏ emoji). Không đụng markdown heading trong AI prompt (model-facing).
3. **News table**: `Xem` (NewsLinkButton L801) giữ text-only; `🔗` (L811) → icon-only `flat_icon("external-link", role theo zone)`, `setText("")`, giữ objectName `NewsIconButton` + `linkTone`. Hover: QPushButton không request QIcon mode Active → thêm `LinkToneHoverFilter` swap icon lighter(118)/darker(118) khi HoverEnter/Leave.
4. **Status cards**: `STATUS_CARD_FLAT_ICONS = {"Kết nối":"plug","Broker":"user","AI":"bot","Nguồn dữ liệu":"bar-chart"}`; QLabel giữ nguyên `StatusIcon` objectName + 28×28 + state property; đổi sang `setPixmap(flat_pixmap(name, role theo state: ok→success, warning→warning, danger→danger))`. `StatusCardEventFilter` **giữ nguyên tên class + thứ tự constructor** (test khóa), thêm re-set pixmap sau `set_dynamic_property`.
5. **QTabBar tabs**: bỏ 📅, giữ text ("Tuần trước/này/sau") — tab khóa 16px chiều cao, không đủ chỗ icon+text. **Zone header**: bỏ 📅/⚡, giữ separator + màu semantic (substring check `_scroll_to_nearest` vẫn match). Tiêu đề dialog/window: bỏ emoji.
6. **`refresh_theme_styles`**: thêm `_retint_status_icons()` (re-set pixmap 4 QLabel — QLabel cache pixel ngoài QIcon nên cần refresh tay). Mọi button khác tự re-tint qua engine.
7. **QSS tối thiểu (base.qss)**: `QPushButton#NewsIconButton` padding `2px 0` → `2px 2px` + `min-width: 20px` (audit responsive yêu cầu width ≥18px; NewsIconButton đã có trong `COMPACT_OBJECT_NAMES`). Không sửa overlay (linkTone color, StatusIcon bg giữ nguyên).

### Ngoài phạm vi (follow-up, ghi trong doc)
Emoji trong rich text dialog (⏰📰💱📈📉🔴🟡⚪✅…) — cần cơ chế `<img data:...>` trong `ui/rich_text.py`; 87 nút emoji ở 7 màn hình khác.

### Rủi ro chính
1. QSS không tint QIcon → engine-side tinting (đã giải quyết bằng FlatIconEngine).
2. Disabled phải có pixmap riêng (nếu không Qt tự grayscale xấu) → engine luôn phát `disabled_role`.
3. HiDPI: render `size×dpr` + devicePixelRatio; kiểm capture dpi-125/150.
4. **Cấm đổi tên** `__init__`, `_build_ui`, `_refresh_market_overview`, `_show_market_help`, class `MarketWorker` (test `inspect.getsource` nhóm group_a/b/d).
5. Style-lock: dashboard `hex_color_literals` giữ =1, `object_name_calls` không tăng (tái dùng objectName cũ); `ui/icons.py` vào lock với 0 debt.
6. Bỏ emoji làm label ngắn lại → báo cáo responsive (T12) xác nhận không overlap hàng market-overview/warning panel.

---

## Danh sách công việc (15 task tuần tự)

Mỗi task gồm **Phần 1: Mô tả & yêu cầu & phân tích** và **Phần 2: Tech leader review**.

### T0 — Lưu kế hoạch vào `docs/plans/dashboard-flat-icons-plan.md`
**Phần 1 — Mô tả**: Tạo file .md trong `docs/plans/` chứa toàn bộ kế hoạch này (theo quy ước doc trong `docs/ui/screen_design.md`: tiếng Việt, H1 + blockquote trạng thái/ngày, section đánh số, bảng). Đây là bước đầu tiên sau khi duyệt, trước khi đụng code.
**Phân tích**: Plan mode không cho ghi docs/; user đã xác nhận lưu sau khi duyệt. File là nguồn tham chiếu cho toàn bộ quá trình thực thi + review.
**Phần 2 — Review**: Xác nhận file tồn tại đúng đường dẫn; nội dung đủ các mục (kiến trúc, bảng icon, 15 task, verification); format markdown hợp lệ; ngày tháng + trạng thái "APPROVED" ghi rõ.

### T1 — Registry glyph + renderer + `flat_pixmap` trong `ui/icons.py` (mới)
**Phần 1 — Mô tả**: Tạo module với `ICONS` dict (9 glyph bắt buộc: refresh, help-circle, map-pin, bot, x, plug, user, bar-chart, external-link + 3 dự phòng), `_SVG_TEMPLATE`, `_svg_bytes(name, color_hex)`, `_renderer_cache`, `_get_renderer()`, `flat_pixmap(name, role, *, size, palette)` dùng `color_for_role` + QImage DPR-aware. Yêu cầu: 0 hex literal trong file; import từ `ui.theme` (color_for_role) và `ui.theme_manager` (current_palette); tác giả glyph dùng path data feather-style (stroke 2, round).
**Phân tích**: Tách registry/renderer khỏi engine (T2) để test được phần "vẽ tĩnh" trước. `flat_pixmap` là nền cho status cards (T7) — render 1 lần thành pixel, cache theo (name, hex, size, dpr).
**Phần 2 — Review**: (a) Đọc từng glyph trong `ICONS` — xác nhận mọi entry chứa `currentColor`, không hex, viewBox 24, stroke-based (không fill đặc → giữ "phẳng nét"); (b) chạy smoke offscreen: render 12 tên × role text/success/danger, assert pixmap không null, size đúng `size×dpr`, pixel khác transparent đúng màu kỳ vọng (sample pixel như đã verify); (c) grep `#[0-9a-fA-F]{3,6}` trong ui/icons.py = 0; (d) kiểm tra import không vòng (icons → theme_manager → theme).

### T2 — `FlatIconEngine` + `flat_icon` + `clear_icon_caches`
**Phần 1 — Mô tả**: Thêm class `FlatIconEngine(QIconEngine)` lưu **role, không lưu màu**; `paint(painter, rect, mode, state)` resolve palette lazy theo bảng mode→role (Normal/Selected→role, Disabled→disabled_role mặc định "muted", Active→active_role or role), gọi `_get_renderer(...).render(painter, QRectF(rect))`; implement `pixmap()` (DPR-aware), `actualSize()`, `key()`, `clone()`. `flat_icon()` trả `QIcon(engine)`. `clear_icon_caches()` xóa cả 2 cache (dùng trong test).
**Phân tích**: Lazy-paint là lựa chọn bắt buộc vì app không có themeChanged signal; flow đổi theme (`MainWindow._apply_styles` → setStyleSheet → repaint) sẽ tự kéo màu mới. Disabled mode riêng tránh auto-grayscale của Qt.
**Phần 2 — Review**: (a) Đọc `paint()` — assert không cache màu thành attribute, chỉ cache role; mapping đủ 4 mode; (b) test offscreen: `flat_icon("x").pixmap(16, mode=Disabled)` khác Normal; (c) giả lập đổi theme (đặt app property `amaTheme` hoặc ThemeManager.apply) → vẽ lại → màu đổi; (d) `clone()` trả engine cùng name/role; (e) cache bounded: gọi lặp 1000 lần cùng key → len cache không tăng.

### T3 — Test module icon: `tests/test_flat_icons.py`
**Phần 1 — Mô tả**: Test headless (`QT_QPA_PLATFORM=offscreen`, pattern `QApplication.instance() or QApplication([])` như tests hiện có): (1) mọi entry `ICONS` chứa `currentColor` + `QSvgRenderer.isValid()`; (2) `flat_pixmap` đúng size, có pixel khác trong suốt, màu khớp role; (3) `flat_icon` Normal vs Disabled khác nhau; (4) cache hit + `clear_icon_caches()`; (5) KeyError khi tên glyph không tồn tại.
**Phân tích**: Khóa hành vi engine trước khi tích hợp vào UI — mọi task sau dựa vào contract này.
**Phần 2 — Review**: Chạy `python -m pytest -q tests/test_flat_icons.py` với offscreen — xanh; đọc test xác nhận không phụ thuộc mạng/MT5/settings thật; không hardcode hex ngoài giá trị kỳ vọng lấy từ palette.

### T4 — Mở rộng `action_button` trong `ui/screens/shared.py`
**Phần 1 — Mô tả**: Thêm kwarg `icon: str | None = None`, `icon_role: str | None = None` (default None → hành vi cũ nguyên vẹn cho 87 call site). Khi `icon`: `button.setIcon(flat_icon(icon, icon_role or "text"))` + `button.setIconSize(QSize(LayoutTokens.ICON_SIZE, LayoutTokens.ICON_SIZE))`. Import `QSize`, `flat_icon`, `LayoutTokens`.
**Phân tích**: Thay đổi helper chung là điểm đòn bẩy duy nhất — nhưng phải backward-compatible tuyệt đối; icon size đặt code theo tiền lệ `configure_button()` (style guide cho phép helper quản lý icon).
**Phần 2 — Review**: (a) Diff shared.py — chỉ thêm, không sửa logic cũ; (b) test: gọi `action_button("X")` → `icon().isNull()` True; `action_button("X", icon="refresh")` → icon non-null, iconSize 16×16; (c) chạy nhanh 1-2 test màn khác (vd `pytest -q tests/test_dashboard_compact_cards.py`) xác nhận không regression.

### T5 — Di cư 4 nút chính dashboard (warning panel + market overview + news header)
**Phần 1 — Mô tả**: Trong dashboard_screen.py: L274 `🔄 Thử lại`→`action_button("Thử lại", primary=True, color="info", icon="refresh")`; L303 `❓ Giải thích chỉ số`→ icon="help-circle"; L349 `📍 Xem tin sắp tới`→ icon="map-pin"; L356 `🔄 Làm mới`→ icon="refresh"; kèm các chỗ reset text L402/L431/L446 (`"⏳ Đang tải..."`, `"🔄 Làm mới"`) bỏ emoji (icon đã gắn trên button, không mất). Giữ nguyên mọi kết nối signal.
**Phân tích**: Các nút này nền Primary-info (text trắng cả 2 theme) nên icon mặc định role "text" là chưa đúng màu — **phải truyền `icon_role="selection_text"`** để icon trắng trên nền accent (kiểm tra màu nền thực tế của btnColor=info ở dark/light trước khi chốt role; nếu nền nhạt thì dùng role tương phản). Ghi chú phân tích này vào từng nút khi làm.
**Phần 2 — Review**: (a) grep `🔄|❓|📍` trong dashboard_screen.py = 0 ở 4 vị trí; (b) chạy app offscreen chụp nhanh hoặc test cấu trúc: 4 nút có icon non-null; (c) đọc lại code reset text — không còn emoji, text tiếng Việt giữ nguyên; (d) test_dashboard_* vẫn xanh.

### T6 — Di cư nút dialog (3× AI + 3× Đóng)
**Phần 1 — Mô tả**: L982 `🤖 Tóm tắt AI`, L1176 `🤖 Xem tác động`, L1456 `🤖 Phân tích AI` → icon="bot"; L987/L1181/L1461 `❌ Đóng` → icon="x". `DialogAiButton` (nền cam #ea580c) truyền `icon_role="selection_text"`; `Đóng` (Secondary danger) role mặc định. Mọi `setText` động (`⏳ Đang tóm tắt...`, `🤖 Tóm tắt AI` trả về, placeholder) bỏ emoji. **Không sửa** emoji trong markdown prompt AI (L1243-1251 — nội dung gửi model, không phải UI).
**Phân tích**: Khi AI chạy, button disable + đổi text → engine Disabled mode tự vẽ icon màu muted, khớp text xám của `:disabled` QSS. Trả text về sau khi xong phải giữ icon (icon gắn 1 lần lúc tạo button).
**Phần 2 — Review**: (a) grep `🤖|❌` trong dashboard_screen.py chỉ còn trong prompt string (được phép) — UI string = 0; (b) kiểm tra từng cặp ai_btn/close_btn: icon gắn đúng, disabled state không grayscale tự động (test pixmap Disabled); (c) placeholder QTextEdit không còn emoji; (d) đọc prompt L1243-1251 xác nhận KHÔNG bị đụng.

### T7 — Status cards: emoji → flat pixmap
**Phần 1 — Mô tả**: Thay `STATUS_CARD_ICONS` bằng `STATUS_CARD_FLAT_ICONS = {"Kết nối":"plug","Broker":"user","AI":"bot","Nguồn dữ liệu":"bar-chart"}` + `_STATE_ICON_ROLES = {"ok":"success","warning":"warning","danger":"danger"}`. Trong `_status_card`: QLabel không text, `setPixmap(flat_pixmap(name, role theo state ban đầu, size=16))`, giữ objectName `StatusIcon`, `setFixedSize(28,28)`, AlignCenter, property state. `StatusCardEventFilter`: **giữ tên class + thứ tự tham số constructor**, thêm icon_name; sau `set_dynamic_property(self.icon,"state",state)` gọi lại `setPixmap` với role của state mới. Thêm method `_retint_status_icons()` re-set pixmap 4 card từ theme hiện hành.
**Phân tích**: Test khóa (`test_dashboard_status_cards.py`) assert: QLabel StatusIcon 28×28, không emoji ✅❌🟡, MockEvent DynamicPropertyChange → `icon.property("state")` đúng, selector QSS tồn tại — mọi thứ phải giữ. QSS nền tròn tint theo state (dark/light L1156/L1152) không đụng → glyph phẳng cùng màu state trên nền tròn mờ = đúng thiết kế phẳng.
**Phần 2 — Review**: (a) Chạy `pytest -q tests/test_dashboard_status_cards.py tests/test_dashboard_compact_cards.py` — xanh KHÔNG sửa test; (b) đọc diff StatusCardEventFilter — constructor signature cũ còn gọi được (dashboard + nơi khác nếu có); (c) mô phỏng đủ 3 state → pixmap đổi màu đúng role; (d) theme switch → `_retint_status_icons` được gọi từ `refresh_theme_styles`, pixmap màu light/dark đúng.

### T8 — Nút icon news table + hover filter + base.qss
**Phần 1 — Mô tả**: L811 `QPushButton("🔗")` → `QPushButton()` + `setIcon(flat_icon("external-link", role=_tone_role(zone)))`, `setText("")`, giữ objectName `NewsIconButton` + `linkTone` + tooltip. Thêm `_tone_role(zone, impact)`: past→subtle, nearest→success, future→warning, danger→danger, warning→warning (khớp bảng màu linkTone QSS hiện hành). Thêm `LinkToneHoverFilter(QObject)`: HoverEnter → set icon bản sáng hơn (lighter(118) dark / darker(118) light — resolve từ current_palette, KHÔNG hardcode), HoverLeave → icon gốc. base.qss: `QPushButton#NewsIconButton` padding `2px 2px` + `min-width: 20px`. Nút `Xem` (L801) giữ nguyên text-only.
**Phân tích**: QSS `color:` không tint QIcon nên phải resolve role trong code lúc tạo row (table rebuild mỗi lần render → theme switch tự đúng vì `refresh_news_section` rebuild rows). Audit responsive yêu cầu width ≥18px — icon 16 + padding 2+2 = 20px ✓; NewsIconButton đã trong `COMPACT_OBJECT_NAMES` (20px contract) ✓.
**Phần 2 — Review**: (a) grep `🔗` trong ui/ = 0; (b) test cấu trúc: row headline có NewsIconButton icon non-null, text rỗng, linkTone đúng zone; (c) chạy `python tools/ui_layout_audit.py` — width NewsIconButton ≥18px, không issue mới; (d) diff base.qss chỉ đụng block NewsIconButton, không overlay; (e) hover filter không leak (install 1 lần/button, không giữ ref mạnh gây leak — kiểm tra pattern event filter hiện có).

### T9 — Gỡ emoji bề mặt text (tabs, zone header, tiêu đề)
**Phần 1 — Mô tả**: Tabs L342-344 → "Tuần trước"/"Tuần này"/"Tuần sau". Zone header L858-861 → "─── ĐÃ QUA ───"/"─── SẮP TỚI GẦN NHẤT ───"/"─── SẮP TỚI ───" (giữ màu semantic + span). Tiêu đề dialog/window (`📰 Chi tiết tin tức`, `📊 Chi tiết sự kiện`, `📊 Hướng dẫn...`, title label trong dialog) bỏ emoji. Text lookup `✅ {result}`/`❌ Không tìm thấy` → chữ thuần ("Kết quả: …"/"Không tìm thấy"). Kiểm tra `_scroll_to_nearest`: substring "SẮP TỚI GẦN NHẤT"/"SẮP TỚI" vẫn match sau khi sửa.
**Phân tích**: Đây là bề mặt text thuần (không phải nút) — giữ text, bỏ emoji để đồng bộ "phẳng". Không thay tab bằng icon vì chiều cao tab khóa 16px + không có QSS `QTabBar::tab::icon`.
**Phần 2 — Review**: (a) grep emoji còn lại trong dashboard_screen.py — chỉ được phép tồn tại trong AI prompt + rich-text dialog (phạm vi follow-up đã ghi); (b) chạy thử logic scroll: tạo mock row, gọi `_scroll_to_nearest` không vỡ; (c) tab đổi text không ảnh hưởng `news_tab_keys` mapping; (d) test dashboard suite xanh.

### T10 — Test dashboard flat icons: `tests/test_dashboard_flat_icons.py`
**Phần 1 — Mô tả**: Offscreen, `DashboardScreen(None, app=None)` (pattern 2 test dashboard hiện có): (1) regex quét toàn bộ QPushButton/QTabBar text/StatusIcon label/zone item — không emoji trong phạm vi di cư; (2) 4 status icon: `text()==""`, pixmap non-null, 28×28, MockEvent state propagation còn đúng; (3) nút chính: icon non-null + iconSize 16; (4) re-tint theme: `ThemeManager().apply(..., "light")` + `refresh_theme_styles()` → pixmap/icon vẽ màu light; (5) `action_button` back-compat.
**Phân tích**: Khóa regression dài hạn — bất kỳ ai thêm emoji button mới vào dashboard sẽ bị test này bắt.
**Phần 2 — Review**: (a) pytest xanh offscreen; (b) test không flaky (không sleep chờ QTimer — dùng pattern mock `_patch_external_activity` nếu cần, tham khảo tools/capture_ui_style_baseline.py L213-240); (c) không phụ thuộc MT5/mạng; (d) đọc assert — đúng mức (không over-assert pixel).

### T11 — Audit + re-lock style lock
**Phần 1 — Mô tả**: Chạy `$env:QT_QPA_PLATFORM='offscreen'; python tools/ui_style_audit.py --check docs/ui/style/ui-style-lock.json`. Vì thêm file `ui/icons.py` + objectName không đổi, số đếm thay đổi → sau khi xác nhận thay đổi hợp lệ, cập nhật lock bằng chế độ ghi của tool (theo style-guide §5: chỉ cập nhật khi thay đổi kiến trúc đã review). Chạy thêm `python tools/ui_density_audit.py --check docs/ui/density/ui-density-lock.json --validate-contract`.
**Phân tích**: `ui/icons.py` phải vào lock với 0 debt (0 setStyleSheet, 0 hex). Dashboard `hex_color_literals` giữ 1, `object_name_calls` không tăng. Đây là cổng bắt buộc trước baseline.
**Phần 2 — Review**: (a) Số liệu lock mới: ui/icons.py debt = 0; dashboard hex=1; set_stylesheet_calls toàn app vẫn = 1; (b) diff lock JSON chỉ thay đổi dòng liên quan file mới/sửa; (c) `pytest -q tests/test_ui_style_phase5.py tests/test_ui_style_phase7.py tests/test_ui_density_phase4.py tests/test_ui_density_phase5.py tests/test_ui_density_phase6.py` xanh.

### T12 — Báo cáo responsive + baseline screenshot
**Phần 1 — Mô tả**: `python tools/ui_layout_audit.py --write docs/ui/reports/ui-responsive-report.json` — xác nhận `issue_count == 0` (phase7 yêu cầu đúng 288 results). `python tools/capture_ui_style_baseline.py --suite` tái tạo 80 captures (40/theme, cùng tên file) + manifest. Kiểm tra trực quan dark/light PNG của dashboard: icon nét, đúng màu, không lệch layout khi bỏ emoji.
**Phân tích**: Nhãn ngắn lại sau khi bỏ emoji → phải soi hàng market-overview + warning panel không overlap. dpi-125/150: icon DPR-aware phải nét.
**Phần 2 — Review**: (a) Report JSON issue_count=0, 288 results; (b) manifest 80 captures, không failure; (c) **mở PNG bằng mắt**: 4 status card icon phẳng cùng màu state; 4 nút chính icon trắng trên nền; NewsIconButton trong table; so sánh dark vs light tint đổi đúng; (d) không có widget vỡ layout.

### T13 — Toàn bộ test suite
**Phần 1 — Mô tả**: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q` toàn bộ. Đặc biệt nhóm nhạy cảm: test_dashboard_* (cấu trúc card), test_ui_style_phase5/6/7, test_ui_density_phase4/5/6, test_group_a/b/d_optimizations (inspect.getsource), test_theme_manager.
**Phân tích**: Đây là cổng cuối — suite hiện ~3600 test; mọi ràng buộc kiến trúc (setStyleSheet=1, density 24/20, method-name lock) được xác nhận đồng loạt.
**Phần 2 — Review**: (a) 100% pass, không skip mới; (b) nếu có test đỏ: KHÔNG sửa test để "cho qua" — chẩn đoán root cause (quy tắc style-guide §4); (c) đối chiếu số test pass trước/sau thay đổi.

### T14 — Cập nhật docs + danh sách follow-up
**Phần 1 — Mô tả**: Cập nhật `docs/ui/screen_design.md` (mục dashboard: icon phẳng, tham chiếu ui/icons.py) + `docs/ui/style-guide.md` nếu cần bổ sung quy ước icon (icon = flat SVG qua ui/icons.py, cấm emoji cho nút). Ghi danh sách follow-up: emoji rich-text dialog, 87 nút emoji màn khác, tab icon nếu nới chiều cao. Commit theo yêu cầu user.
**Phần 2 — Review**: (a) doc tiếng Việt đúng convention (blockquote trạng thái + ngày, section đánh số); (b) cross-link tương đối hoạt động; (c) follow-up list đủ 3 mục; (d) git diff cuối cùng chỉ gồm file dự kiến.

---

## Verification end-to-end (tóm tắt lệnh, PowerShell)

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_flat_icons.py tests/test_dashboard_flat_icons.py
python -m pytest -q tests/test_dashboard_status_cards.py tests/test_dashboard_compact_cards.py
python tools/ui_style_audit.py --check docs/ui/style/ui-style-lock.json
python tools/ui_density_audit.py --check docs/ui/density/ui-density-lock.json --validate-contract
python tools/ui_layout_audit.py --write docs/ui/reports/ui-responsive-report.json
python -m pytest -q tests/test_ui_style_phase5.py tests/test_ui_style_phase7.py tests/test_ui_density_phase4.py tests/test_ui_density_phase5.py tests/test_ui_density_phase6.py
python -m pytest -q
python tools/capture_ui_style_baseline.py --suite
```
Sau đó mở `docs/ui/baseline/current/{dark,light}/*dashboard*` kiểm tra trực quan cả 2 theme.

## File đụng đến
- Mới: `ui/icons.py`, `tests/test_flat_icons.py`, `tests/test_dashboard_flat_icons.py`, `docs/plans/dashboard-flat-icons-plan.md`
- Sửa: `ui/screens/dashboard_screen.py`, `ui/screens/shared.py`, `ui/styles/base.qss` (block NewsIconButton), `docs/ui/style/ui-style-lock.json` (re-lock), `docs/ui/reports/ui-responsive-report.json` + baseline PNG (tái tạo), docs UI liên quan
- KHÔNG đụng: 7 màn hình khác, dark.qss/light.qss, rich_text.py, requirements.txt
