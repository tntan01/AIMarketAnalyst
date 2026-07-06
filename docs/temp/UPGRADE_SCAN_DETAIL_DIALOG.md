# Nâng cấp Dialog "Xem đầy đủ chỉ số" — `ScannerDetailScreen`

> File áp dụng: `ui/screens/scanner_detail_screen.py`
> Method chính: `_show_scan_detail_dialog()`
> Điều kiện tiên quyết: File này áp dụng SAU khi đã thêm `_refresh_trade_panel()` và `_refresh_score_panel()` vào tab Tổng quan (xem file `NANG_CAP_TAB_TONG_QUAN_SCANNER_DETAIL.md`). Nếu chưa làm phần đó, dừng lại và làm trước.

---

## Vấn đề hiện tại

Dialog đang hiện 16 ô lặp lại gần hết nội dung đã có trên tab Tổng quan (Điểm tốt nhất, Điểm cuối, Mua/Bán, Gap, R:R, SL, TP, Vĩ mô, Chế độ TT, Quyền GD). Không phân nhóm, không cảnh báo khi dữ liệu ít, không giải thích thuật ngữ.

---

## Tổng quan thay đổi

| # | Hạng mục | Loại |
|---|----------|------|
| 1 | Bỏ 10 ô trùng lặp, chỉ giữ 6 ô còn giá trị riêng | Sửa |
| 2 | Nhóm 6 ô còn lại thành 2 khu vực có tiêu đề | Sửa |
| 3 | Cảnh báo khi mẫu nhật ký quá nhỏ | Thêm mới |
| 4 | Thêm tooltip giải thích thuật ngữ khó | Thêm mới |

**Không đụng:** `_build_entry_checklist()`, các method `_dialog_card_*()` (vẫn dùng lại nguyên trạng), style dialog tổng thể, nút Đóng.

---

## 1. Bỏ 10 ô trùng lặp

**Trong `_show_scan_detail_dialog()`**, tìm biến `card_defs`. Hiện có 16 dòng:

```python
card_defs = [
    ("Điểm tốt nhất", self._dialog_card_best(), "#ea580c"),
    ("Mua / Bán", self._dialog_card_buysell(), "#fb7185"),
    ("Điểm cuối", self._dialog_card_final(), "#10b981"),
    ("Chênh lệch", self._dialog_card_gap(), "#f59e0b"),
    ("Điểm vĩ mô", self._dialog_card_macro(), "#38bdf8"),
    ("Tỷ lệ R:R", self._dialog_card_rr(), "#ea580c"),
    ("Stop Loss", self._dialog_card_sl(), "#e11d48"),
    ("Take Profit", self._dialog_card_tp(), "#10b981"),
    ("Vùng vào lệnh", self._dialog_card_entry(), "#10b981"),
    ("Vị trí giá", self._dialog_card_position(), "#f59e0b"),
    ("Khung M15", self._dialog_card_m15(), "#f59e0b"),
    ("Nhóm scanner", self._dialog_card_group(), "#a78bfa"),
    ("Chế độ TT", self._dialog_card_regime(), "#fb7185"),
    ("Quyền giao dịch", self._dialog_card_permission(), "#e11d48"),
    ("Mẫu nhật ký", self._dialog_card_journal_sample(), "#9ca3af"),
    ("Kỳ vọng NK", self._dialog_card_journal_exp(), "#38bdf8"),
]
```

**Xóa toàn bộ biến `card_defs` và logic vòng lặp `for idx, (label_text, ...) in enumerate(card_defs): ...` cùng với `grid` (QGridLayout) render 16 ô.**

Thay bằng cấu trúc mới ở bước 2 dưới đây — dùng 2 nhóm có tiêu đề, không dùng grid 2 cột phẳng nữa.

---

## 2. Nhóm 6 ô còn lại thành 2 khu vực

Danh sách 6 ô giữ lại — chỉ những chỉ số **không có** trên tab Tổng quan:

**Nhóm A — 🔎 Ngữ cảnh mở rộng:**
- Vị trí giá (`_dialog_card_position()`)
- Nhóm scanner (`_dialog_card_group()`)
- Khung M15 chi tiết (`_dialog_card_m15()`)
- Điểm vĩ mô chi tiết (`_dialog_card_macro()`)

**Nhóm B — 📔 Thống kê nhật ký:**
- Mẫu nhật ký (`_dialog_card_journal_sample()`)
- Kỳ vọng NK (`_dialog_card_journal_exp()`)

**Code thay thế** (đặt vào đúng vị trí đã xóa `card_defs`/`grid` ở bước 1, TRƯỚC phần "Entry checklist section"):

```python
# ---- Nhóm A: Ngữ cảnh mở rộng ----
group_a_title = QLabel("🔎 Ngữ cảnh mở rộng")
group_a_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {value_color}; background: transparent; border: none;")
content_layout = QVBoxLayout(content)
content_layout.setSpacing(10)
content_layout.setContentsMargins(0, 0, 0, 0)
content_layout.addWidget(group_a_title)

group_a_defs = [
    ("Vị trí giá", self._dialog_card_position(), "#f59e0b",
     "Giá hiện tại đang ở đâu so với vùng vào lệnh đã xác định"),
    ("Nhóm scanner", self._dialog_card_group(), "#a78bfa",
     "Phân loại mã theo mức độ sẵn sàng vào lệnh của bộ quét"),
    ("Khung M15", self._dialog_card_m15(), "#f59e0b",
     "Độ chặt chẽ của tín hiệu xác nhận ở khung thời gian 15 phút"),
    ("Điểm vĩ mô", self._dialog_card_macro(), "#38bdf8",
     "Điểm đánh giá tác động của yếu tố vĩ mô, độ tin cậy thể hiện qua dấu chấm"),
]
group_a_grid = QGridLayout()
group_a_grid.setHorizontalSpacing(8)
group_a_grid.setVerticalSpacing(8)
for idx, (label_text, (value_text, detail_text, accent), _, tooltip_text) in enumerate(group_a_defs):
    row_i, col_i = divmod(idx, 2)
    cell = QFrame()
    cell.setStyleSheet(f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; }}")
    cell.setToolTip(tooltip_text)
    cell_l = QVBoxLayout(cell)
    cell_l.setContentsMargins(12, 8, 12, 8)
    cell_l.setSpacing(2)
    accent_used = accent if accent else "#ea580c"
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {label_color}; background: transparent; border: none;")
    lbl.setToolTip(tooltip_text)
    val = QLabel(value_text)
    val.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {accent_used}; background: transparent; border: none;")
    cell_l.addWidget(lbl)
    cell_l.addWidget(val)
    if detail_text:
        det = QLabel(detail_text)
        det.setStyleSheet(f"font-size: 11px; color: {label_color}; background: transparent; border: none;")
        cell_l.addWidget(det)
    group_a_grid.addWidget(cell, row_i, col_i)
content_layout.addLayout(group_a_grid)

# ---- Nhóm B: Thống kê nhật ký ----
group_b_title = QLabel("📔 Thống kê nhật ký")
group_b_title.setStyleSheet(f"font-weight: bold; font-size: 14px; color: {value_color}; background: transparent; border: none;")
content_layout.addWidget(group_b_title)

sample_val, _, sample_accent = self._dialog_card_journal_sample()
exp_val, _, exp_accent = self._dialog_card_journal_exp()
try:
    sample_num = int(sample_val)
except (TypeError, ValueError):
    sample_num = 0

group_b_defs = [
    ("Mẫu nhật ký", (sample_val, "", sample_accent),
     "Số lệnh đã ghi nhật ký khớp với thiết lập tương tự"),
    ("Kỳ vọng NK", (exp_val, "", exp_accent),
     "Kỳ vọng lợi nhuận trung bình theo R, tính từ lịch sử nhật ký"),
]
group_b_grid = QGridLayout()
group_b_grid.setHorizontalSpacing(8)
group_b_grid.setVerticalSpacing(8)
for idx, (label_text, (value_text, detail_text, accent), tooltip_text) in enumerate(group_b_defs):
    row_i, col_i = divmod(idx, 2)
    cell = QFrame()
    cell.setStyleSheet(f"QFrame {{ background: {bg}; border: 1px solid {border}; border-radius: 6px; }}")
    cell.setToolTip(tooltip_text)
    cell_l = QVBoxLayout(cell)
    cell_l.setContentsMargins(12, 8, 12, 8)
    cell_l.setSpacing(2)
    accent_used = accent if accent else "#ea580c"
    lbl = QLabel(label_text)
    lbl.setStyleSheet(f"font-size: 11px; font-weight: 600; color: {label_color}; background: transparent; border: none;")
    lbl.setToolTip(tooltip_text)
    val = QLabel(value_text)
    val.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {accent_used}; background: transparent; border: none;")
    cell_l.addWidget(lbl)
    cell_l.addWidget(val)
    group_b_grid.addWidget(cell, row_i, col_i)
content_layout.addLayout(group_b_grid)

# ---- Cảnh báo mẫu nhỏ (xem bước 3) ----
if sample_num < 20:
    warn_lbl = QLabel("⚠️ Mẫu quá ít, kỳ vọng chưa đáng tin")
    warn_lbl.setStyleSheet("font-size: 12px; color: #f59e0b; background: transparent; border: none; font-weight: 600;")
    content_layout.addWidget(warn_lbl)
```

**Lưu ý quan trọng:** Đoạn code trên dùng `content_layout = QVBoxLayout(content)` — kiểm tra xem `content` (QWidget) đã được set layout trước đó chưa (biến `grid` cũ dùng `QGridLayout(content)`). Nếu đã xóa `grid` ở bước 1 thì áp dụng `QVBoxLayout(content)` là hợp lệ. Nếu Claude Code thấy `content` đã có layout khác, phải xóa layout cũ trước khi gán mới.

---

## 3. Cảnh báo mẫu nhật ký quá nhỏ

Đã lồng vào code ở bước 2 (điều kiện `if sample_num < 20`). Không cần làm gì thêm — chỉ cần đảm bảo đoạn `if sample_num < 20: ...` được thêm sau khối Nhóm B, trước phần "Entry checklist section".

Ngưỡng `20` là số lệnh tối thiểu để coi kỳ vọng R đáng tin — có thể để nguyên hoặc điều chỉnh nếu dự án có ngưỡng khác đã thống nhất trước đó.

---

## 4. Tooltip giải thích thuật ngữ

Đã lồng vào code bước 2 qua tham số `tooltip_text` gọi `cell.setToolTip(...)` và `lbl.setToolTip(...)`. Không cần thêm gì khác ngoài đảm bảo mọi ô trong Nhóm A và Nhóm B đều có tooltip khi tạo.

---

## 5. Phần checklist (giữ nguyên vị trí, chỉ đổi cách gắn vào layout)

Đoạn "Entry checklist section" hiện tại dùng:
```python
grid.addWidget(checklist_frame, len(card_defs) // 2, 0, 1, 2)
grid.setRowStretch(len(card_defs) // 2 + 1, 1)
```

Vì `grid` và `card_defs` đã bị xóa ở bước 1, đổi 2 dòng này thành:
```python
content_layout.addWidget(checklist_frame)
content_layout.addStretch(1)
```

Toàn bộ nội dung bên trong `checklist_frame` (tiêu đề "🔍 Điều kiện vào lệnh", vòng lặp `for item in self._build_entry_checklist(): ...`) **giữ nguyên không đổi**.

---

## Kiểm tra sau khi thực hiện

- [ ] Dialog không còn hiện 10 ô trùng lặp (Điểm tốt nhất, Điểm cuối, Mua/Bán, Gap, R:R, SL, TP, Vĩ mô, Chế độ TT, Quyền GD)
- [ ] Dialog hiện đúng 2 nhóm có tiêu đề: "🔎 Ngữ cảnh mở rộng" (4 ô) và "📔 Thống kê nhật ký" (2 ô)
- [ ] Hover vào từng ô trong 2 nhóm hiện được tooltip giải thích
- [ ] Khi mẫu nhật ký < 20 lệnh → hiện dòng cảnh báo màu cam
- [ ] Khi mẫu nhật ký ≥ 20 lệnh → không hiện cảnh báo
- [ ] Checklist "Điều kiện vào lệnh" vẫn hiển thị đầy đủ, đúng vị trí dưới cùng
- [ ] Dialog vẫn mở/đóng bình thường, không lỗi layout, đúng cả light mode và dark mode
- [ ] Không còn biến `card_defs` hoặc `grid` (QGridLayout cũ) tồn tại trong method
