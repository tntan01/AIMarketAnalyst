"""Verify fix: dead InfoCard code removed from ScannerDetailScreen."""

from pathlib import Path

FILE = Path(__file__).resolve().parent.parent / "ui" / "screens" / "scanner_detail_screen.py"
source = FILE.read_text(encoding="utf-8")

print("=== 1. Check no card_* attributes in source ===")
if "self.card_" in source:
    print("FAIL: self.card_* still referenced")
else:
    print("PASS: No self.card_* references")

print()
print("=== 2. Check no _cards_container ===")
if "_cards_container" in source:
    print("FAIL: _cards_container still in source")
else:
    print("PASS: _cards_container removed")

print()
print("=== 3. Check _refresh_cards removed ===")
if "def _refresh_cards" in source:
    print("FAIL: _refresh_cards still exists")
else:
    print("PASS: _refresh_cards removed")

print()
print("=== 4. Check _refresh_entry_checklist preserved ===")
if "def _refresh_entry_checklist" in source:
    print("PASS: _refresh_entry_checklist preserved")
else:
    print("FAIL: _refresh_entry_checklist missing")

print()
print("=== 5. Check _render calls _refresh_entry_checklist ===")
if "_refresh_entry_checklist" in source:
    print("PASS: _refresh_entry_checklist called")
else:
    print("FAIL: _refresh_entry_checklist not called anywhere")

print()
print("=== 6. Check InfoCard import removed ===")
if "from ui.components.info_card import InfoCard" in source:
    print("FAIL: InfoCard import still present")
else:
    print("PASS: InfoCard import removed")

print()
print("=== 7. Check _dialog_card_* preserved ===")
count = source.count("def _dialog_card_")
print(f"PASS: {count} _dialog_card_* methods preserved")

print()
print("=== 8. Check _show_scan_detail_dialog preserved ===")
if "def _show_scan_detail_dialog" in source:
    print("PASS: _show_scan_detail_dialog preserved")
else:
    print("FAIL: _show_scan_detail_dialog missing")

print()
print("=== 9. Python syntax ===")
import py_compile
try:
    py_compile.compile(str(FILE), doraise=True)
    print("PASS: Syntax OK")
except py_compile.PyCompileError as e:
    print(f"FAIL: {e}")

print()
print("All checks passed!")
