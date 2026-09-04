# Kế hoạch: Icon phẳng cho mục "Phân rã điểm số" (tab Chẩn đoán — Chi tiết kết quả quét)

> **TRẠNG THÁI: HOÀN THÀNH — 2026-09-04.** Mỗi task gồm Phần 1 (mô tả + phân tích)
> và Phần 2 (tech leader review).

## Context (bối cảnh)

Màn "Chi tiết kết quả quét" (`ui/screens/scanner_detail_screen.py`), tab **Chẩn đoán**,
mục **"Phân rã điểm số"** (hàm `_diag_scores_html`, dòng ~3879–3978, route scanner/V4)
hiện đánh dấu hướng được chọn bằng emoji `✅` trong rich text:
`marker = " · ✅ đang chọn" if side == selected else ""` (dòng ~3951) — 4 marker trên 4
hàng thành phần của cột được chọn. Emoji không phẳng/không đổi màu theo theme.
Yêu cầu: chuyển sang icon phẳng của hệ thống `ui/icons.py`.

**Khảo sát đã chốt**:
- Biến thể legacy `_diag_score_breakdown_html` (heading trùng tên) **không có emoji**
  → không đụng.
- `✅` nằm trong HTML raw → `set_rich_html` → `QTextEdit` (`self.diag_text`).
  `ui/rich_text.compile_rich_html` chỉ rewrite thuộc tính `style=`, **không đụng thẻ
  `<img>`** → nhúng `<img src='data:image/png;base64,...'>` là an toàn.
- **Spike đã kiểm chứng (offscreen)**: Qt6 QTextEdit load được `<img>` data-URI
  (`document.resource(ImageResource, QUrl(data_uri))` trả pixmap non-null) → chọn
  data-URI làm cơ chế chính (không cần addResource/wiring).
- Pixel icon tint từ palette (role `success` — giữ ngữ nghĩa xanh của ✅), KHÔNG hardcode
  hex; HTML build theo theme hiện tại (`light` arg sẵn có).
- `_refresh_diagnostics` KHÔNG chạy lại khi đổi theme (`refresh_theme_styles` chỉ
  re-tint chart) → phải gọi lại để HTML + data-URI bắt kịp theme mới.
- Tests hiện có (`test_scanner_detail_v4_diagnostics.py` L100-109/156,
  `test_scanner_detail_diagnostics.py` L124/377) assert heading + label + MUA/BÁN,
  KHÔNG assert emoji → thay ✅ bằng `<img>` không phá vỡ.
- Phạm vi NGOÀI đợt này (follow-up): các legend emoji cùng tab (Cổng chặn
  `_diag_gates_html` ~4026, checklist legacy ~3613-3635, pipeline ~3721, route 🧭 3872,
  branch ⛔💡⚙️ ~2902-2997) — các hàm riêng, không chung helper, tách đợt sau.

## Kiến trúc chốt

- Thêm `flat_data_uri(name, role="text", *, size=16) -> str` vào `ui/icons.py`:
  render `flat_pixmap` → encode PNG base64 (`QByteArray.toBase64`) →
  `"data:image/png;base64,..."`; cache nhỏ theo (name, role, size). 0 hex literal.
- `_diag_scores_html`: thay `" · ✅ đang chọn"` bằng
  `" · <img src='{uri}' width='12' height='12'/> đang chọn"` với
  `uri = flat_data_uri("check", "success", size=12)` (glyph `check` đã có trong registry).
- `refresh_theme_styles` (dòng ~1842): thêm gọi lại `self._refresh_diagnostics()` khi
  `self.row` tồn tại, để rich text + icon bắt kịp theme.

---

## Danh sách công việc

### T0 — Lưu kế hoạch vào `docs/plans/flat-icons-score-breakdown-plan.md`
**Phần 1**: Copy kế hoạch này vào docs/plans/ (convention tiếng Việt, blockquote trạng thái). Bước đầu sau duyệt.
**Phần 2 — Review**: file tồn tại; đủ context, kiến trúc, 6 task, verification.

### T1 — Helper `flat_data_uri` trong `ui/icons.py` + unit test
**Phần 1**: Implement như kiến trúc (dùng `QBuffer`/`QByteArray.toBase64`; import trong
module; cache dict riêng). Thêm vào `tests/test_flat_icons.py`: assert chuỗi bắt đầu
`data:image/png;base64,`, decode ra byte PNG hợp lệ (magic `\x89PNG`), khác role cho màu
khác nhau (decode → QImage → pixel khác transparent), cache hit.
**Phân tích**: Tách helper để khóa contract trước; reused cho các legend follow-up sau này.
**Phần 2 — Review**: `pytest -q tests/test_flat_icons.py` xanh; grep hex trong ui/icons.py = 0;
ui_style_audit --check không tăng debt.

### T2 — Di cư marker trong `_diag_scores_html`
**Phần 1**: Sửa dòng ~3951 theo kiến trúc; giữ nguyên mọi chuỗi khác (heading "Phân rã
điểm số", label 4 thành phần, MUA/BÁN, bảng phụ) để tests hiện tại xanh nguyên.
**Phân tích**: Marker nằm trong `<td>` có `color:{text_color}` — `<img>` không kế thừa màu
nhưng pixel đã tint role success → đúng ý "icon phẳng xanh".
**Phần 2 — Review**: grep "✅" trong `_diag_scores_html` = 0; AST parse file OK;
`pytest -q tests/test_scanner_detail_v4_diagnostics.py` xanh KHÔNG sửa test.

### T3 — Re-build diagnostics khi đổi theme
**Phần 1**: `refresh_theme_styles` thêm: `if getattr(self, "row", None) is not None:
self._refresh_diagnostics()` (đặt TRƯỚC/SĂU phần chart hiện có, giữ chart re-tint).
**Phân tích**: `_refresh_diagnostics` đọc `self.row` nội tại; guard row=None tránh crash khi
chưa chọn hàng. Không đổi signature.
**Phần 2 — Review**: smoke offscreen: tạo screen với row scanner (pattern `_fake_app` +
monkeypatch như test hiện có), gọi `refresh_theme_styles` sau khi lật `amaTheme` → html mới
chứa data-URI khác màu pixel; không exception khi row=None.

### T4 — Test khóa regression
**Phần 1**: Mở rộng `tests/test_scanner_detail_v4_diagnostics.py`: trong test có sẵn cho
`_diag_scores_html`, thêm assert: `"✅" not in html`, `"đang chọn" in html`,
`"data:image/png;base64" in html`. Thêm 1 test theme: html build light vs dark cho data-URI
khác nhau (decode pixel khác).
**Phân tích**: Khóa để không ai đưa emoji quay lại rich text mục này.
**Phần 2 — Review**: pytest xanh; đọc diff test — chỉ THÊM assert, không nới lỏng cái cũ.

### T5 — Verification tổng + docs
**Phần 1**: Chạy `pytest -q tests/test_scanner_detail_v4_diagnostics.py
tests/test_scanner_detail_diagnostics.py tests/test_flat_icons.py`, rồi full `pytest -q`;
`ui_style_audit --check` + `ui_density_audit --check`. Không cần regenerate baseline
(capture không phủ tab Chẩn đoán). Kiểm mắt bằng snippet offscreen render `diag_text`
thành PNG (dark+light) để soi icon check phẳng. Cập nhật `docs/ui/screen_design.md`:
chuyển mục "Phân rã điểm số" khỏi follow-up, ghi cơ chế `flat_data_uri`; follow-up còn:
legend Cổng chặn/checklist/pipeline/route/branch.
**Phần 2 — Review**: full suite 0 failed; số pass ≥ hiện tại; docs liệt kê đúng follow-up còn lại.

## Verification end-to-end

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_flat_icons.py tests/test_scanner_detail_v4_diagnostics.py tests/test_scanner_detail_diagnostics.py
python tools/ui_style_audit.py --check docs/ui/style/ui-style-lock.json
python -m pytest -q
```
Kèm snippet offscreen chụp `self.diag_text` (dark/light) để soi trực quan.

## File đụng đến
- Sửa: `ui/icons.py`, `ui/screens/scanner_detail_screen.py`,
  `tests/test_flat_icons.py`, `tests/test_scanner_detail_v4_diagnostics.py`,
  `docs/ui/screen_design.md`
- Mới: `docs/plans/flat-icons-score-breakdown-plan.md`
- KHÔNG đụng: `ui/rich_text.py`, các `_diag_*` legend khác, requirements.txt
