# Kế hoạch: Icon phẳng cho mục "Cổng chặn" (tab Chẩn đoán — Chi tiết kết quả quét)

> **TRẠNG THÁI: HOÀN THÀNH — 2026-09-04.** Mỗi task gồm Phần 1 (mô tả + phân tích)
> và Phần 2 (tech leader review). **Ràng buộc chủ đạo: KHÔNG thay đổi logic** —
> chỉ thay phần tử icon trong HTML.

## Context (bối cảnh)

Mục **"Cổng chặn"** (hàm `_diag_gates_html`, `ui/screens/scanner_detail_screen.py`
~4026–4102, route scanner/V4) vẽ mỗi nhóm cổng một icon emoji theo trạng thái:
`_status_vn` ~4033–4045 trả `(icon, text, color)`:
PASS 🟢 / BLOCK 🔴 / CAUTION 🟡 / CAP 🟡 / UNKNOWN ⚪ (kèm fallback ⚪ và rỗng "").
Icon nằm trong `<td width:24px>` riêng (~4088) → thay bằng `<img>` data-URI icon phẳng
là thay đổi thuần trình bày: **text ("Qua/Chặn/…"), màu label, `_aggregate`, cấu trúc
bảng giữ nguyên 100%**.

**Hạ tầng sẵn có (reuse, không thêm gì mới)**:
- `flat_data_uri(name, role, size)` trong `ui/icons.py` (phase 3) — data-URI PNG tint
  theo palette; Qt6 QTextEdit đã chứng minh load được; `compile_rich_html` không đụng
  thẻ `<img>`.
- Glyph đủ sẵn trong registry: `check`, `x`, `alert-triangle`, `minus`.
- Map glyph nhất quán với tiền lệ cùng file (`_checklist_pixmap` ~44–52:
  pass→check/success, fail→x/danger, unknown→minus/muted).
- Theme: `refresh_theme_styles` đã gọi lại `_refresh_diagnostics` (phase 3) → tab Chẩn
  đoán tự build lại khi đổi theme; không cần hook mới.

**Map emoji → glyph phẳng**:
| Status | Emoji cũ | Glyph / role mới |
|---|---|---|
| PASS | 🟢 | `check` / `success` |
| BLOCK | 🔴 | `x` / `danger` |
| CAUTION | 🟡 | `alert-triangle` / `warning` |
| CAP | 🟡 | `alert-triangle` / `warning` |
| UNKNOWN + fallback | ⚪ | `minus` / `muted` |
| status rỗng | (không icon) | giữ `""` |

**Tests hiện có** (`test_scanner_detail_v4_diagnostics.py` L142–156, L187) chỉ assert
label 6 nhóm + text mã chặn dịch + heading "Cổng chặn" — KHÔNG assert emoji → an toàn.

**Ngoài phạm vi**: legend emoji các mục khác cùng tab (checklist legacy ~3613,
pipeline ~3721, route 🧭 ~3872, branch ~2902) — follow-up riêng.

---

## Danh sách công việc

### T0 — Lưu kế hoạch vào `docs/plans/flat-icons-gates-plan.md`
**Phần 1**: Copy kế hoạch này vào docs/plans/ (convention tiếng Việt + blockquote trạng thái).
**Phần 2 — Review**: file tồn tại; đủ context, bảng map, 5 task, verification.

### T1 — Thay emoji bằng `<img>` phẳng trong `_diag_gates_html`
**Phần 1**: Trong `_diag_gates_html`, thêm helper nội bộ `_status_icon(status)` trả
chuỗi `<img src='{flat_data_uri(name, role, size=12)}' width='12' height='12'/>` theo
bảng map trên (status rỗng → `""`); sửa `_status_vn` để phần tử icon =
`_status_icon(status)` — **giữ nguyên** dict text/color, fallback, `_aggregate`, nhóm
`groups`, toàn bộ HTML bảng. Không đổi signature hàm.
**Phân tích**: Icon trong `<td>` riêng nên không ảnh hưởng căn cột; màu icon theo
palette (theme-aware) trong khi màu label giữ hex hiện tại — đúng ngôn ngữ thiết kế
phase 1–3; logic bất biến.
**Phần 2 — Review**: diff chỉ chạm khối `_status_vn` + thêm helper; AST parse OK;
grep 🟢🔴⚪ trong `_diag_gates_html` = 0; `pytest -q tests/test_scanner_detail_v4_diagnostics.py`
xanh KHÔNG sửa test.

### T2 — Test khóa regression
**Phần 1**: Mở rộng `test_gates_html_lists_all_gate_groups` (chỉ THÊM assert):
`"🟢" not in html`, `"🔴" not in html`, `"🟡" not in html`, `"⚪" not in html`,
`"data:image/png;base64" in html`, và 5 label trạng thái
("Qua", "Chặn", "Cảnh báo", "Giới hạn" hoặc "Chưa đủ dữ liệu" — theo row stub BLOCKED:
"Chặn" phải xuất hiện) giữ nguyên.
**Phân tích**: Khóa để emoji không quay lại mục này.
**Phần 2 — Review**: pytest xanh; diff test chỉ thêm assert.

### T3 — Verification tổng + trực quan
**Phần 1**: `pytest -q tests/test_scanner_detail_v4_diagnostics.py
tests/test_flat_icons.py`; full `pytest -q`; `ui_style_audit --check` +
`ui_density_audit --check` (không đổi debt: không objectName/setStyleSheet/hex mới trong
screen — hex trong `_status_vn` là cũ, giữ nguyên). Render offscreen fragment
`_diag_gates_html` (pattern snippet phase 3: `_stub_screen(_blocked_row())` +
`set_rich_html` vào QTextEdit, grab PNG dark+light) và soi mắt: 6 hàng cổng có icon
phẳng (row BLOCKED → icon x đỏ), label màu giữ nguyên.
**Phần 2 — Review**: full suite 0 failed (số pass ≥ 3694); PNG 2 theme: icon đổi màu
theo palette, bảng không lệch cột.

### T4 — Docs
**Phần 1**: `docs/ui/screen_design.md`: gạch "Cổng chặn" khỏi follow-up, ghi đã di cư
bằng `flat_data_uri`; follow-up còn: checklist legacy, pipeline steps, route 🧭,
branch ⛔💡⚙️ + các rich text khác/BE-trailing/KPI badge. Đặt trạng thái HOÀN THÀNH
cho `docs/plans/flat-icons-gates-plan.md` khi xong.
**Phần 2 — Review**: docs liệt kê đúng phần còn lại; diff git chỉ gồm file dự kiến.

## Verification end-to-end

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_scanner_detail_v4_diagnostics.py tests/test_flat_icons.py
python tools/ui_style_audit.py --check docs/ui/style/ui-style-lock.json
python -m pytest -q
```
Kèm PNG offscreen dark/light của fragment "Cổng chặn" để soi trực quan.

## File đụng đến
- Sửa: `ui/screens/scanner_detail_screen.py`, `tests/test_scanner_detail_v4_diagnostics.py`,
  `docs/ui/screen_design.md`
- Mới: `docs/plans/flat-icons-gates-plan.md`
- KHÔNG đụng: `ui/icons.py` (glyph đủ sẵn), logic `_aggregate`/`_status_vn` text-color,
  các `_diag_*` khác, requirements.txt
