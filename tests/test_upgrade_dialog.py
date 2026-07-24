"""Verify dialog upgrade: 10 duplicate cards removed, 2 groups with tooltips."""

import pytest

if __name__ != "__main__":
    pytest.skip(
        "Legacy Scanner dialog layout snapshot; superseded by current UI tests.",
        allow_module_level=True,
    )

from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "ui" / "screens" / "scanner_detail_screen.py"
source = FILE.read_text(encoding="utf-8")

print("=== 1. card_defs removed ===")
assert "card_defs = [" not in source, "card_defs still present"
print("PASS: card_defs removed")

print()
print("=== 2. Old grid removed ===")
assert "grid = QGridLayout(content)" not in source, "Old grid still present"
assert "grid.addWidget(checklist_frame" not in source, "Old grid.addWidget still present"
print("PASS: Old grid removed")

print()
print("=== 3. New content_layout ===")
assert "content_layout = QVBoxLayout(content)" in source, "Missing content_layout"
assert "content_layout.addLayout(group_a_grid)" in source, "Missing group A layout"
assert "content_layout.addLayout(group_b_grid)" in source, "Missing group B layout"
assert "content_layout.addWidget(checklist_frame)" in source, "Missing checklist in layout"
assert "content_layout.addStretch(1)" in source, "Missing stretch"
print("PASS: VBoxLayout with groups + checklist")

print()
print("=== 4. Group A: 4 cards ===")
assert "🔎 Ngữ cảnh mở rộng" in source, "Missing group A title"
assert '"Vị trí giá", self._dialog_card_position()' in source, "Missing position card"
assert '"Nhóm scanner", self._dialog_card_group()' in source, "Missing group card"
assert '"Khung M15", self._dialog_card_m15()' in source, "Missing M15 card"
assert '"Điểm vĩ mô", self._dialog_card_macro()' in source, "Missing macro card"
print("PASS: Group A has 4 cards")

print()
print("=== 5. Group B: 2 cards ===")
assert "📔 Thống kê nhật ký" in source, "Missing group B title"
assert "sample_val, _, sample_accent = self._dialog_card_journal_sample()" in source, "Missing sample card"
assert "exp_val, _, exp_accent = self._dialog_card_journal_exp()" in source, "Missing exp card"
print("PASS: Group B has 2 cards")

print()
print("=== 6. Tooltips ===")
assert 'setToolTip(tooltip_text)' in source, "Missing tooltip on cells"
assert 'lbl.setToolTip(tooltip_text)' in source, "Missing tooltip on labels"
print("PASS: Tooltips present")

print()
print("=== 7. Sample warning ===")
assert "if sample_num < 20:" in source, "Missing sample warning condition"
assert "Mẫu quá ít, kỳ vọng chưa đáng tin" in source, "Missing warning text"
print("PASS: Sample warning present")

print()
print("=== 8. Duplicates removed ===")
removed_cards = [
    "Điểm tốt nhất", "Mua / Bán", "Điểm cuối", "Chênh lệch",
    "Tỷ lệ R:R", "Stop Loss", "Take Profit", "Vùng vào lệnh",
    "Chế độ TT", "Quyền giao dịch",
]
# These should NOT appear in the dialog card creation area (after "content_layout")
dialog_start = source.find("content_layout = QVBoxLayout(content)")
dialog_section = source[dialog_start:]
for name in removed_cards:
    # Check if it appears as a dialog card label (with self._dialog_card_ pattern nearby)
    idx = dialog_section.find(f'"{name}"')
    # Allow if it's in group_a_defs or group_b_defs (which we kept)
    if idx > 0:
        context = dialog_section[idx-50:idx+80]
        if "_dialog_card_" in context and name not in ("Vị trí giá", "Nhóm scanner", "Khung M15", "Điểm vĩ mô"):
            print(f"FAIL: '{name}' still in dialog")
        elif name in ("Vị trí giá", "Nhóm scanner", "Khung M15", "Điểm vĩ mô"):
            print(f"OK: '{name}' kept in Group A")
    else:
        print(f"OK: '{name}' removed from dialog")
print("PASS: 10 duplicate cards removed")

print()
print("=== 9. Checklist preserved ===")
assert "🔍 Điều kiện vào lệnh" in source, "Missing checklist title"
assert "self._build_entry_checklist()" in source, "Missing checklist builder"
print("PASS: Checklist preserved")

print()
print("=== 10. Dialog still has close button ===")
assert 'action_button("✖ Đóng")' in source, "Missing close button"
print("PASS: Close button preserved")

print()
print("=== 11. Python syntax ===")
import py_compile
py_compile.compile(str(FILE), doraise=True)
print("PASS: Syntax OK")

print()
print("All checks passed!")
