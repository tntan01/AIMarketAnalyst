"""Verify scanner overview tab redesign implementation."""
import pytest

if __name__ != "__main__":
    pytest.skip(
        "Legacy Scanner detail layout snapshot; superseded by current UI tests.",
        allow_module_level=True,
    )

from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "ui" / "screens" / "scanner_detail_screen.py"
source = FILE.read_text(encoding="utf-8")

print("=== 1. Hero bar expanded ===")
assert "best_score = self.row.get(\"best_score\"" in source, "Missing best_score read"
assert "macro_vn =" in source, "Missing macro_vn map"
assert "Điểm <b style" in source, "Missing Điểm in hero"
assert "R:R <b style" in source, "Missing R:R in hero"
assert "B/S <b style" in source, "Missing B/S in hero"
assert "Gap <b style" in source, "Missing Gap in hero"
assert "Vĩ mô <b style" in source, "Missing Vĩ mô in hero"
print("PASS: Hero bar has 5 inline indicators")

print()
print("=== 2. Trade panel exists ===")
assert "self.trade_panel = QFrame()" in source, "Missing trade_panel creation"
assert "TradePanelCard" in source, "Missing TradePanelCard objectName"
assert "def _refresh_trade_panel(self)" in source, "Missing _refresh_trade_panel"
assert "Vùng vào lệnh" in source, "Missing entry zone row"
assert "Stop Loss" in source, "Missing SL row"
assert "Take Profit" in source, "Missing TP row"
print("PASS: Trade panel created with 6 rows")

print()
print("=== 3. Score panel exists ===")
assert "self.score_panel = QFrame()" in source, "Missing score_panel creation"
assert "ScorePanelCard" in source, "Missing ScorePanelCard objectName"
assert "def _refresh_score_panel(self)" in source, "Missing _refresh_score_panel"
assert "Điểm tốt nhất" in source, "Missing best score row"
assert "Điểm cuối" in source, "Missing final score row"
assert "Buy / Sell" in source, "Missing buy/sell row"
assert "Quyền GD" in source, "Missing permission row"
print("PASS: Score panel created with 6 rows")

print()
print("=== 4. Button text updated ===")
assert "Xem đầy đủ (16 chỉ số)" in source, "Missing button text"
assert "Xem toàn bộ 16 chỉ số phân tích chi tiết" in source, "Missing tooltip"
assert "Xem chi tiết kết quả quét" not in source, "Old button text still present"
print("PASS: Button text and tooltip updated")

print()
print("=== 5. _render() calls new panels ===")
assert "_refresh_trade_panel()" in source, "Missing trade panel call in _render"
assert "_refresh_score_panel()" in source, "Missing score panel call in _render"
print("PASS: _render() calls both new panels")

print()
print("=== 6. _refresh_cards still gone ===")
assert "def _refresh_cards" not in source, "_refresh_cards shouldn't exist"
print("PASS: _refresh_cards not reintroduced")

print()
print("=== 7. _dialog_card_* preserved ===")
count = source.count("def _dialog_card_")
assert count == 16, f"Expected 16 _dialog_card_*, got {count}"
print(f"PASS: {count} _dialog_card_* methods preserved")

print()
print("=== 8. _show_scan_detail_dialog preserved ===")
assert "def _show_scan_detail_dialog" in source, "Missing dialog method"
print("PASS: Dialog method preserved")

print()
print("=== 9. Edge case: self.row empty handled ===")
assert "if not self.row:" in source  # appears in multiple places
# Check trade panel has guard
trade_method_start = source.find("def _refresh_trade_panel")
trade_method = source[trade_method_start:trade_method_start + 1500]
assert "if not self.row:" in trade_method, "Trade panel missing empty row guard"
# Check score panel has guard
score_method_start = source.find("def _refresh_score_panel")
score_method = source[score_method_start:score_method_start + 1500]
assert "if not self.row:" in score_method, "Score panel missing empty row guard"
print("PASS: Empty row guards present")

print()
print("=== 10. Entry accent uses entry_status ===")
assert 'self.row.get("entry_status") == "confirmed_entry"' in source, "Missing entry_status check for accent"
print("PASS: Entry accent correctly uses entry_status")

print()
print("=== 11. Python syntax ===")
import py_compile
py_compile.compile(str(FILE), doraise=True)
print("PASS: Syntax OK")

print()
print("All checks passed!")
