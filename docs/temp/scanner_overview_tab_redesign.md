# Nâng cấp giao diện — Tab "Tổng quan" trong `ScannerDetailScreen`

> File áp dụng: `ui/screens/scanner_detail_screen.py`  
> Mục tiêu: Hiển thị đủ thông tin cần thiết ngay trên tab "Tổng quan" mà không cần mở dialog.

---

## Tổng quan thay đổi

| # | Hạng mục | Loại | Phạm vi |
|---|----------|------|---------|
| 1 | Mở rộng hero bar thêm 5 chỉ số | Sửa | `_refresh_hero()` |
| 2 | Thêm panel "Số liệu giao dịch" cố định | Thêm mới | `_build_ui()`, `_refresh_trade_panel()` |
| 3 | Thêm panel "Điểm phân tích" cố định | Thêm mới | `_build_ui()`, `_refresh_score_panel()` |
| 4 | Đổi tooltip nút xem đầy đủ | Sửa nhỏ | `_build_ui()` |
| 5 | Xóa dead code `_refresh_cards()` | Xóa | `_refresh_cards()` và lời gọi của nó |
| 6 | Thêm Scrollbar cho panel "Điều kiện vào lệnh" | Sửa | `_refresh_entry_checklist()` |

---

## Thay đổi chi tiết

---

### 1. Mở rộng hero bar — `_refresh_hero()`

**Hiện tại** — hero bar chỉ hiển thị:
```
✅ READY  |  Hạng #2  |  Có thể xem xét, vẫn cần kiểm tra...
```

**Sau thay đổi** — thêm 5 chỉ số vào giữa hero bar:
```
✅ READY  |  Điểm: 78  |  R:R: 1:2.1  |  Buy/Sell: 80/45  |  Gap: +35  |  Vĩ mô: Thuận  |  Hạng #2
```

**Cách lấy dữ liệu** — đọc từ `self.row`, dùng các method helper sẵn có:

| Chỉ số | Key trong `self.row` | Method helper |
|--------|---------------------|---------------|
| Điểm tốt nhất | `best_score` | — |
| R:R | `risk_reward` | — |
| Buy score | `buy_score` | — |
| Sell score | `sell_score` | — |
| Gap | `score_gap` hoặc `direction_bias["score_gap"]` | `_gap_numbers()` |
| Vĩ mô | `macro_bias` | — |

**Hướng dẫn sửa `_refresh_hero()`:**

Sau khi xây dựng xong `action_text`, `rank`, `reason` (giữ nguyên logic hiện tại), thêm đoạn đọc dữ liệu sau:

```python
# Đọc 5 chỉ số bổ sung
best_score = self.row.get("best_score", "--")
rr = self.row.get("risk_reward", "--")
buy_s = self.row.get("buy_score", "--")
sell_s = self.row.get("sell_score", "--")
gap_num, _ = self._gap_numbers()
gap_str = f"+{int(gap_num)}" if gap_num is not None and gap_num >= 0 else (str(int(gap_num)) if gap_num is not None else "--")
macro_raw = str(self.row.get("macro_bias", "") or "").lower()
macro_vn = {"aligned": "Thuận", "conflict": "Xung đột", "neutral": "Trung lập", "unclear": "Chưa rõ"}.get(macro_raw, "—")
```

Sửa `self.hero_bar.setText(...)` — thêm các chỉ số vào phần `<td>` giữa dưới dạng HTML table cell:

```python
self.hero_bar.setText(
    f"<table width='100%' style='margin:0;padding:0;border:none;'><tr>"
    f"<td width='110' style='vertical-align:middle;'>"
    f"<span style='color:{accent};font-size:15px;font-weight:bold;'>{icon} {action_text.upper()}</span>"
    f"</td>"
    # --- 5 chỉ số mới ---
    f"<td style='vertical-align:middle;padding:0 10px;border-left:1px solid {border};'>"
    f"<span style='color:{text_color};font-size:12px;'>Điểm <b style='color:{bold_color};'>{best_score}</b></span>"
    f"</td>"
    f"<td style='vertical-align:middle;padding:0 10px;border-left:1px solid {border};'>"
    f"<span style='color:{text_color};font-size:12px;'>R:R <b style='color:#f59e0b;'>{rr}</b></span>"
    f"</td>"
    f"<td style='vertical-align:middle;padding:0 10px;border-left:1px solid {border};'>"
    f"<span style='color:{text_color};font-size:12px;'>B/S <b style='color:{bold_color};'>{buy_s}/{sell_s}</b></span>"
    f"</td>"
    f"<td style='vertical-align:middle;padding:0 10px;border-left:1px solid {border};'>"
    f"<span style='color:{text_color};font-size:12px;'>Gap <b style='color:{bold_color};'>{gap_str}</b></span>"
    f"</td>"
    f"<td style='vertical-align:middle;padding:0 10px;border-left:1px solid {border};'>"
    f"<span style='color:{text_color};font-size:12px;'>Vĩ mô <b style='color:{bold_color};'>{macro_vn}</b></span>"
    f"</td>"
    # --- Hạng + lý do (giữ nguyên, đẩy sang phải) ---
    f"<td style='vertical-align:middle;text-align:right;'>"
    f"<span style='color:{text_color};font-size:13px;'>"
    f"Hạng <b style='color:{bold_color};'>#{rank}</b> &nbsp;&bull;&nbsp; {reason}"
    f"</span>"
    f"</td>"
    f"</tr></table>"
)
```

---

### 2. Thêm panel "Số liệu giao dịch" — mới

**Mô tả:** QFrame cố định ở cột phải, hiển thị entry zone, SL, TP, R:R, Vĩ mô, Chế độ thị trường. Cập nhật mỗi khi `_render()` chạy.

**Bước A — thêm widget vào `_build_ui()`:**

Thêm đoạn sau, SAU khi tạo `self.show_detail_btn` và TRƯỚC khi tạo `self.right_scroll`:

```python
# -- Panel: Số liệu giao dịch --
self.trade_panel = QFrame()
self.trade_panel.setObjectName("TradePanelCard")
trade_panel_layout = QVBoxLayout(self.trade_panel)
trade_panel_layout.setContentsMargins(12, 10, 12, 10)
trade_panel_layout.setSpacing(4)
right_col.addWidget(self.trade_panel)
```

**Bước B — thêm method `_refresh_trade_panel()`:**

Thêm method mới vào class (đặt sau `_refresh_hero()`):

```python
def _refresh_trade_panel(self) -> None:
    """Cập nhật panel Số liệu giao dịch ở cột phải tab Tổng quan."""
    layout = self.trade_panel.layout()
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()

    try:
        light = self.settings_service.load().display.theme == "light"
    except Exception:
        light = False

    bg = "#ffffff" if light else "#1a1f2e"
    border_color = "#d1d5db" if light else "#2b3545"
    label_color = "#475569" if light else "#94a3b8"
    val_color = "#0f172a" if light else "#f1f5f9"

    self.trade_panel.setStyleSheet(
        f"QFrame#TradePanelCard {{ background: {bg}; border: 1px solid {border_color}; border-radius: 6px; }}"
    )

    # Tiêu đề
    title = QLabel("🎯 Số liệu giao dịch")
    title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {val_color}; margin-bottom: 4px;")
    layout.addWidget(title)

    if not self.row:
        layout.addWidget(QLabel("—"))
        return

    # Lấy dữ liệu — dùng lại các helper sẵn có
    entry_val, _, _ = self._dialog_card_entry()
    sl_val, _, _ = self._dialog_card_sl()
    tp_val, tp_detail, _ = self._dialog_card_tp()
    rr_val, rr_detail, _ = self._dialog_card_rr()
    macro_val, macro_detail, _ = self._dialog_card_macro()
    regime_val, _, _ = self._dialog_card_regime()

    rows = [
        ("Vùng vào lệnh", entry_val, "#22c55e" if "xác nhận" in entry_val.lower() else "#f59e0b"),
        ("Stop Loss", sl_val, "#e11d48"),
        ("Take Profit", f"{tp_val}{' · ' + tp_detail if tp_detail else ''}", "#10b981"),
        ("R:R", f"{rr_val}{' (' + rr_detail + ')' if rr_detail else ''}", "#f59e0b"),
        ("Vĩ mô", f"{macro_val} {macro_detail}".strip(), "#38bdf8"),
        ("Chế độ TT", regime_val, val_color),
    ]

    for label_text, value_text, accent in rows:
        row_w = QWidget()
        row_w.setStyleSheet("background: transparent;")
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 2, 0, 2)
        row_l.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"font-size: 12px; color: {label_color};")
        val = QLabel(value_text)
        val.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {accent};")
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        val.setWordWrap(True)
        row_l.addWidget(lbl, 1)
        row_l.addWidget(val, 1)
        layout.addWidget(row_w)
```

---

### 3. Thêm panel "Điểm phân tích" — mới

**Mô tả:** QFrame cố định ở cột phải, hiển thị điểm tốt nhất, điểm cuối, Buy/Sell, Gap, M15, Quyền giao dịch.

**Bước A — thêm widget vào `_build_ui()`:**

Thêm đoạn sau, SAU khi thêm `self.trade_panel` (bước 2A), TRƯỚC khi tạo `self.right_scroll`:

```python
# -- Panel: Điểm phân tích --
self.score_panel = QFrame()
self.score_panel.setObjectName("ScorePanelCard")
score_panel_layout = QVBoxLayout(self.score_panel)
score_panel_layout.setContentsMargins(12, 10, 12, 10)
score_panel_layout.setSpacing(4)
right_col.addWidget(self.score_panel)
```

**Bước B — thêm method `_refresh_score_panel()`:**

Thêm method mới ngay sau `_refresh_trade_panel()`:

```python
def _refresh_score_panel(self) -> None:
    """Cập nhật panel Điểm phân tích ở cột phải tab Tổng quan."""
    layout = self.score_panel.layout()
    while layout.count():
        item = layout.takeAt(0)
        if item.widget():
            item.widget().deleteLater()

    try:
        light = self.settings_service.load().display.theme == "light"
    except Exception:
        light = False

    bg = "#ffffff" if light else "#1a1f2e"
    border_color = "#d1d5db" if light else "#2b3545"
    label_color = "#475569" if light else "#94a3b8"
    val_color = "#0f172a" if light else "#f1f5f9"

    self.score_panel.setStyleSheet(
        f"QFrame#ScorePanelCard {{ background: {bg}; border: 1px solid {border_color}; border-radius: 6px; }}"
    )

    title = QLabel("📊 Điểm phân tích")
    title.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {val_color}; margin-bottom: 4px;")
    layout.addWidget(title)

    if not self.row:
        layout.addWidget(QLabel("—"))
        return

    # Lấy dữ liệu — dùng lại các helper sẵn có
    best_val, best_detail, best_accent = self._dialog_card_best()
    final_val, final_detail, final_accent = self._dialog_card_final()
    buysell_val, buysell_detail, _ = self._dialog_card_buysell()
    gap_val, gap_detail, gap_accent = self._dialog_card_gap()
    m15_val, _, m15_accent = self._dialog_card_m15()
    perm_val, _, perm_accent = self._dialog_card_permission()

    rows = [
        ("Điểm tốt nhất", f"{best_val} {best_detail}".strip(), best_accent),
        ("Điểm cuối", f"{final_val} {final_detail}".strip(), final_accent),
        ("Buy / Sell", f"{buysell_val} {buysell_detail}".strip(), val_color),
        ("Gap", f"{gap_val} ({gap_detail})", gap_accent),
        ("M15", m15_val, m15_accent),
        ("Quyền GD", perm_val, perm_accent),
    ]

    for label_text, value_text, accent in rows:
        row_w = QWidget()
        row_w.setStyleSheet("background: transparent;")
        row_l = QHBoxLayout(row_w)
        row_l.setContentsMargins(0, 2, 0, 2)
        row_l.setSpacing(6)
        lbl = QLabel(label_text)
        lbl.setStyleSheet(f"font-size: 12px; color: {label_color};")
        val = QLabel(value_text)
        val.setStyleSheet(f"font-size: 12px; font-weight: bold; color: {accent};")
        val.setAlignment(Qt.AlignmentFlag.AlignRight)
        val.setWordWrap(True)
        row_l.addWidget(lbl, 1)
        row_l.addWidget(val, 1)
        layout.addWidget(row_w)
```

---

### 4. Đổi tooltip nút xem đầy đủ

Trong `_build_ui()`, tìm dòng:
```python
self.show_detail_btn = action_button("📋 Xem chi tiết kết quả quét", primary=True, color="warning")
```

Sửa text nút và tooltip:
```python
self.show_detail_btn = action_button("📋 Xem đầy đủ (16 chỉ số)", primary=True, color="warning")
# ...
self.show_detail_btn.setToolTip("Xem toàn bộ 16 chỉ số phân tích chi tiết")
```

---

### 5. Xóa dead code `_refresh_cards()`

Kiểm tra xem file có method `_refresh_cards()` không. Nếu có, xóa toàn bộ method đó.

Kiểm tra các lời gọi tới `_refresh_cards()` trong `_render()` hoặc bất kỳ chỗ nào khác — xóa hết.

> **Lưu ý:** Không xóa các `_dialog_card_*()` — chúng vẫn được dùng bởi `_show_scan_detail_dialog()`, `_refresh_trade_panel()`, và `_refresh_score_panel()`.

### 6. Thêm Scrollbar cho panel "Điều kiện vào lệnh"

Bọc nội dung danh sách các điều kiện vào một `QScrollArea` bên trong `_refresh_entry_checklist()`, giữ tiêu đề nằm ngoài scroll area để tiêu đề luôn cố định khi cuộn.

```python
# ... (Phần tiêu đề QLabel giữ nguyên)
scroll_area = QScrollArea()
scroll_area.setWidgetResizable(True)
scroll_area.setFrameShape(QFrame.Shape.NoFrame)
scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")

content_widget = QWidget()
content_widget.setStyleSheet("background: transparent;")
content_layout = QVBoxLayout(content_widget)
content_layout.setContentsMargins(0, 0, 4, 0)
content_layout.setSpacing(4)

for item in items:
    # ... (Tạo row_w cho từng item giống như cũ)
    content_layout.addWidget(row_w)
    
content_layout.addStretch(1)
scroll_area.setWidget(content_widget)
self.entry_checklist_layout.addWidget(scroll_area)
```

---

### 7. Kết nối vào `_render()`

Trong method `_render()`, bổ sung 2 lời gọi mới sau `self._refresh_hero()`:

```python
self._refresh_hero()
self._refresh_trade_panel()   # ← thêm
self._refresh_score_panel()   # ← thêm
self._refresh_entry_checklist()
self._refresh_chart()
self._refresh_diagnostics()
self._refresh_ai_audit()
```

---

## Kiểm tra sau khi thực hiện

- [ ] Tab "Tổng quan" hiển thị hero bar với 5 chỉ số inline
- [ ] Panel "Số liệu giao dịch" hiển thị đúng entry zone, SL, TP, R:R, Vĩ mô, Chế độ TT
- [ ] Panel "Điểm phân tích" hiển thị đúng điểm, buy/sell, gap, M15, quyền GD
- [ ] Khi `self.row` rỗng: 2 panel hiện dấu `—`, không crash
- [ ] Dialog "Xem đầy đủ" vẫn hoạt động bình thường (không đụng vào `_show_scan_detail_dialog()`)
- [ ] Giao diện đúng cả light mode lẫn dark mode
- [ ] Không còn lời gọi `_refresh_cards()` nào trong file
- [ ] Panel "Điều kiện vào lệnh" có thanh cuộn mượt mà mà không cuộn cả tiêu đề "Điều kiện vào lệnh"

---

## Không thay đổi

- Logic `_show_scan_detail_dialog()` — giữ nguyên hoàn toàn
- Tất cả `_dialog_card_*()` — giữ nguyên, được tái sử dụng bởi 2 panel mới
- Tab "Chẩn đoán" và "Kiểm định AI" — không đụng vào
- `_build_entry_checklist()` — giữ nguyên logic tạo item
- `_refresh_chart()` — giữ nguyên
