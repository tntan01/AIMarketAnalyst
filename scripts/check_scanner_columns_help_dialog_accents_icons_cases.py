"""Check ScannerColumnsHelpDialog for diacritics, icons, and cases completeness.

Run:  python scripts/check_scanner_columns_help_dialog_accents_icons_cases.py
Requires: PyQt6, no MT5, no network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialogButtonBox, QLabel
from ui.screens.scanner_screen import ScannerColumnsHelpDialog, ScannerTableModel


LEGACY_ASCII_ICONS = {
    "#", "FX", ">>", "<>", "(+)", "(S)", "*", "V", "~", "::",
    "(o)", "M5", "<->", "^", "v", "@", "~>", ":", '"', ">",
}

LEGACY_ACCENTLESS = [
    "Giai thich", "Bang ket qua quet",
    "Cot", "Y nghia", "Truong hop thuong gap",
    "Xep hang", "Hanh dong", "Xu huong", "Quyen", "Diem tot nhat",
    "Co hoi", "Nhom", "Trang thai entry", "Vi mo", "Thuan vi mo",
    "Ly do chinh", "Chi tiet", "Dong",
]

# Must be present WITH proper diacritics
REQUIRED_COLUMNS_ACCENTED = [
    ("Xếp hạng", "Xep hang"),
    ("Mã", "Ma"),
    ("Hành động", "Hanh dong"),
    ("Xu hướng", "Xu huong"),
    ("Entry", "Entry"),
    ("Quyền", "Quyen"),
    ("Điểm tốt nhất", "Diem tot nhat"),
    ("Final", "Final"),
    ("Cơ hội", "Co hoi"),
    ("Nhóm", "Nhom"),
    ("Trạng thái entry", "Trang thai entry"),
    ("M15", "M15"),
    ("Gap", "Gap"),
    ("Điểm mua", "Diem mua"),
    ("Điểm bán", "Diem ban"),
    ("Vĩ mô (0-30)", "Vi mo (0-30)"),
    ("Thuận vĩ mô", "Thuan vi mo"),
    ("R:R", "R:R"),
    ("Lý do chính", "Ly do chinh"),
    ("Chi tiết", "Chi tiet"),
]

CASES_CHECKS_ACCENTED = [
    ("Hành động", ["Sẵn sàng", "Theo dõi", "Chờ", "Bỏ qua"]),
    ("Xu hướng", ["BUY rõ", "SELL rõ", "BUY yếu", "SELL yếu", "Trung lập"]),
    ("Entry", ["Trong vùng", "Gần vùng", "Còn xa"]),
    ("Quyền", ["Được phép", "Cẩn trọng", "Bị chặn"]),
    ("Nhóm", ["Sẵn sàng ngay", "Chờ xác nhận", "Theo dõi"]),
    ("Trạng thái entry", ["Sẵn sàng", "Chờ xác nhận", "Theo dõi vùng", "Thiếu dữ liệu"]),
    ("M15", ["strict", "loose"]),
    ("Thuận vĩ mô", ["Thuận", "Trung tính", "Ngược"]),
]


def _a(s: str) -> str:
    return s.encode("ascii", "replace").decode()


def main() -> int:
    app = QApplication([])
    dialog = ScannerColumnsHelpDialog()
    dialog.show()
    app.processEvents()

    errors: list[str] = []
    ok_count = 0

    def ok():
        nonlocal ok_count
        ok_count += 1

    help_items = ScannerColumnsHelpDialog.COLUMN_HELP
    model_cols = len(ScannerTableModel.COLUMNS)

    # ---- Count ----
    if len(help_items) == model_cols:
        ok()
    else:
        errors.append(f"Count: {len(help_items)}/{model_cols}")

    # ---- Required columns present with proper diacritics ----
    columns = [item["column"] for item in help_items]
    for accented, ascii_name in REQUIRED_COLUMNS_ACCENTED:
        if accented in columns:
            ok()
        elif ascii_name in columns:
            errors.append(f"Column '{ascii_name}' has no diacritics (expected proper Vietnamese)")
        else:
            errors.append(f"Column '{ascii_name}': MISSING entirely")

    # ---- No legacy unaccented column names ----
    for legacy in LEGACY_ACCENTLESS:
        if legacy in columns:
            errors.append(f"Legacy name '{legacy}' still in columns")
        else:
            ok()

    # ---- Fields non-empty, no legacy in meaning/cases ----
    for item in help_items:
        col = item["column"]
        for key in ("icon", "meaning", "cases"):
            if item.get(key, "").strip():
                ok()
            else:
                errors.append(f"{_a(col)}: empty {key}")

        combined = item.get("meaning", "") + " " + item.get("cases", "")
        for legacy in LEGACY_ACCENTLESS:
            if legacy in combined:
                errors.append(f"{_a(col)}: legacy '{legacy}' in text")
            else:
                ok()

    # ---- Icons not ASCII ----
    for item in help_items:
        icon = item.get("icon", "")
        if icon in LEGACY_ASCII_ICONS:
            errors.append(f"{_a(item['column'])}: icon is legacy ASCII '{icon}'")
        elif icon.strip():
            ok()
        else:
            errors.append(f"{_a(item['column'])}: empty icon")

    # ---- Cases completeness ----
    lookup: dict[str, str] = {}
    for item in help_items:
        lookup[item["column"]] = item.get("meaning", "") + " " + item.get("cases", "")
    for col_name, terms in CASES_CHECKS_ACCENTED:
        text = lookup.get(col_name, "")
        for term in terms:
            if term in text:
                ok()
            else:
                errors.append(f"{_a(col_name)} cases: missing '{_a(term)}'")

    # ---- Dialog UI ----
    table = dialog.help_table
    actual_title = dialog.windowTitle()
    expected_title = "Giải thích Bảng kết quả quét"
    if actual_title == expected_title:
        ok()
    else:
        errors.append(f"Title: '{_a(actual_title)}' != expected Vietnamese")

    if table.rowCount() == len(help_items):
        ok()
    else:
        errors.append(f"Rows: {table.rowCount()}")
    if table.columnCount() == 4:
        ok()
    else:
        errors.append(f"Cols: {table.columnCount()}")

    # Headers with diacritics
    header_texts = []
    for c in range(table.columnCount()):
        item = table.horizontalHeaderItem(c)
        header_texts.append(item.text() if item else "")
    if header_texts[0] == "":
        ok()
    else:
        errors.append(f"Hdr col0: '{_a(header_texts[0])}'")
    for idx, expected in [(1, "Cột"), (2, "Ý nghĩa"), (3, "Trường hợp")]:
        if expected in header_texts[idx]:
            ok()
        else:
            errors.append(f"Hdr col{idx}: '{_a(header_texts[idx])}' missing proper diacritics")

    # No legacy in headers
    all_hdr = " ".join(header_texts)
    for legacy in ("Giai thich", "Cot", "Y nghia", "Truong hop thuong gap"):
        if legacy not in all_hdr:
            ok()
        else:
            errors.append(f"Legacy '{legacy}' in headers")

    # H-scroll
    if table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
        ok()
    else:
        errors.append("H-scroll not AlwaysOff")

    # Close button
    buttons = dialog.findChildren(QDialogButtonBox)
    if len(buttons) == 1:
        ok()
    else:
        errors.append(f"ButtonBoxes: {len(buttons)}")
    if buttons:
        close_btn = buttons[0].button(QDialogButtonBox.StandardButton.Close)
        if close_btn:
            ct = close_btn.text()
            if "Đóng" in ct:
                ok()
            elif "Dong" in ct:
                errors.append(f"Close still 'Dong' (no diacritics)")
            else:
                errors.append(f"Close text: '{_a(ct)}'")
        else:
            errors.append("Close button None")

    # Emoji icons displayed as cell widgets
    icons_set = 0
    for row in range(table.rowCount()):
        item = table.item(row, 0)
        icon_text = item.text() if item else ""
        if icon_text in LEGACY_ASCII_ICONS:
            errors.append(f"Row {row}: legacy ASCII icon '{icon_text}'")
        else:
            ok()
        icon_widget = table.cellWidget(row, 0)
        if isinstance(icon_widget, QLabel) and icon_widget.text().strip():
            icons_set += 1
            if icon_widget.text() in LEGACY_ASCII_ICONS:
                errors.append(f"Row {row}: legacy ASCII emoji '{icon_widget.text()}'")
            else:
                ok()
        else:
            errors.append(f"Row {row}: missing emoji icon label")
    if icons_set == table.rowCount():
        ok()
    else:
        errors.append(f"Icons: {icons_set}/{table.rowCount()}")

    # ---- Print ----
    print("=" * 56)
    print("  ScannerColumnsHelpDialog - Quality Check")
    print("=" * 56)
    all_ok = len(errors) == 0
    print(f"  Vietnamese accents: {'OK' if all_ok else 'FAIL'}")
    print(f"  Icons:              {'OK' if icons_set == table.rowCount() else 'FAIL'}")
    print(f"  Cases coverage:     {'OK' if all_ok else 'FAIL'}")
    print(f"  Column coverage:    {'OK' if len(help_items) == model_cols else 'FAIL'}")
    print(f"  Checks passed:      {ok_count}")
    print(f"  Checks failed:      {len(errors)}")

    if errors:
        print("\n  FAILURES:")
        for e in errors[:20]:
            print(f"    - {e}")
        if len(errors) > 20:
            print(f"    ... and {len(errors) - 20} more")

    dialog.close()
    app.quit()

    if errors:
        print("\n[FAIL]")
        return 1
    print("\n[PASS] ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
