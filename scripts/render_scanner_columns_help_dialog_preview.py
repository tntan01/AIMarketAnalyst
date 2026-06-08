"""Render ScannerColumnsHelpDialog offscreen to verify accents, icons, and cases.

Run:  python scripts/render_scanner_columns_help_dialog_preview.py
Output: data/scanner_columns_help_dialog_accents_icons_preview.png
Requires: PyQt6, no MT5, no network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QTableWidget,
)
from ui.screens.scanner_screen import ScannerColumnsHelpDialog, ScannerTableModel


def _ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode()


def main() -> int:
    app = QApplication([])

    dialog = ScannerColumnsHelpDialog()
    dialog.show()
    app.processEvents()

    errors: list[str] = []
    ok: list[str] = []

    def check(cond, msg):
        if cond:
            ok.append(msg)
        else:
            errors.append(msg)

    model_cols = len(ScannerTableModel.COLUMNS)
    help_items = len(ScannerColumnsHelpDialog.COLUMN_HELP)
    check(help_items == model_cols, f"Help items ({help_items}) != columns ({model_cols})")

    # ---- Dialog size ----
    dw, dh = dialog.width(), dialog.height()
    check(920 <= dw <= 1120, f"Width {dw}")
    check(520 <= dh <= 750, f"Height {dh}")
    mw, mh = dialog.minimumWidth(), dialog.minimumHeight()
    check(mw >= 700, f"MinWidth {mw}")
    check(mh >= 480, f"MinHeight {mh}")

    # ---- Window title with proper diacritics ----
    title = dialog.windowTitle()
    expected_title = "Giải thích Bảng kết quả quét"
    check(title == expected_title, f"Title: '{_ascii(title)}' (expected proper Vietnamese)")
    check("Giai thich" not in title, f"Title has legacy 'Giai thich': '{_ascii(title)}'")
    check("Bang ket qua quet" not in title, f"Title has legacy no-accents")

    # ---- Table structure ----
    table = dialog.help_table
    check(isinstance(table, QTableWidget), "help_table not QTableWidget")
    check(table.rowCount() == help_items, f"Rows {table.rowCount()}")
    check(table.columnCount() == 4, f"Cols {table.columnCount()}")
    check(table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
          "H-scroll policy != AlwaysOff")

    # ---- Column headers with proper diacritics ----
    header_texts = []
    for c in range(table.columnCount()):
        hdr_item = table.horizontalHeaderItem(c)
        header_texts.append(hdr_item.text() if hdr_item else "")
    check(header_texts[0] == "", f"Hdr0: '{_ascii(header_texts[0])}'")

    # These MUST have proper Vietnamese diacritics
    check("Cột" in header_texts[1], f"Hdr1: '{_ascii(header_texts[1])}' missing proper 'Cột'")
    check("Ý nghĩa" in header_texts[2], f"Hdr2: '{_ascii(header_texts[2])}' missing proper 'Ý nghĩa'")
    check("Trường hợp" in header_texts[3], f"Hdr3: '{_ascii(header_texts[3])}' missing proper 'Trường hợp'")

    # These must NOT appear
    for hdr_text in header_texts:
        for legacy in ("Cot", "Y nghia", "Truong hop thuong gap"):
            check(legacy not in hdr_text, f"Legacy '{legacy}' in header: '{_ascii(hdr_text)}'")

    # ---- Column widths ----
    hdr = table.horizontalHeader()
    check(58 <= hdr.sectionSize(0) <= 72, f"Icon width {hdr.sectionSize(0)}")
    check(170 <= hdr.sectionSize(1) <= 220, f"Name width {hdr.sectionSize(1)}")

    # ---- First 6 rows: column names must have proper diacritics ----
    first_cols_expected = ["Xếp hạng", "Mã", "Hành động", "Xu hướng", "Entry", "Quyền"]
    for row_idx, expected_col in enumerate(first_cols_expected):
        col_widget = table.cellWidget(row_idx, 1)
        actual = col_widget.text() if isinstance(col_widget, QLabel) else ""
        check(actual == expected_col,
              f"Row {row_idx} col name: '{_ascii(actual)}' != '{_ascii(expected_col)}'")

    # ---- Data content: lookup all cases ----
    lookup: dict[str, str] = {}
    for item in ScannerColumnsHelpDialog.COLUMN_HELP:
        lookup[item["column"]] = item.get("meaning", "") + " " + item.get("cases", "")

    # Xu hướng cases
    xu_huong = lookup.get("Xu hướng", "")
    for term in ("BUY rõ", "SELL rõ", "BUY yếu", "SELL yếu", "Trung lập"):
        check(term in xu_huong, f"Xu huong cases missing '{_ascii(term)}'")

    # Hành động cases
    hanh_dong = lookup.get("Hành động", "")
    for term in ("Sẵn sàng", "Theo dõi", "Chờ", "Bỏ qua"):
        check(term in hanh_dong, f"Hanh dong cases missing '{_ascii(term)}'")

    # Trạng thái entry cases
    tt_entry = lookup.get("Trạng thái entry", "")
    for term in ("Sẵn sàng", "Chờ xác nhận", "Theo dõi vùng", "Thiếu dữ liệu"):
        check(term in tt_entry, f"Trang thai entry cases missing '{_ascii(term)}'")

    # M15 cases
    m15_text = lookup.get("M15", "")
    for term in ("strict", "loose"):
        check(term in m15_text, f"M15 cases missing '{term}'")

    # Thuận vĩ mô cases
    tvm = lookup.get("Thuận vĩ mô", "")
    for term in ("Thuận", "Trung tính", "Ngược"):
        check(term in tvm, f"Thuan vi mo cases missing '{_ascii(term)}'")

    # ---- No legacy ASCII in any column/meaning/cases ----
    legacy_accents = ("Xep hang", "Hanh dong", "Trang thai entry", "Thuan vi mo",
                      "Ly do chinh", "Chi tiet", "Diem tot nhat", "Co hoi", "Nhom")
    for item in ScannerColumnsHelpDialog.COLUMN_HELP:
        combined = item["column"] + " " + item.get("meaning", "") + " " + item.get("cases", "")
        for legacy in legacy_accents:
            check(legacy not in combined,
                  f"'{_ascii(item['column'])}': legacy '{legacy}' in text")

    # ---- Emoji icons ----
    legacy_ascii_icons = {"#", "FX", ">>", "<>", "(+)", "(S)", "*", "V", "~",
                          "::", "(o)", "@", "~>", ":", "M5", "<->", "^", "v", '"', ">"}
    icons_set = 0
    for row in range(table.rowCount()):
        icon_item = table.item(row, 0)
        icon_text = icon_item.text() if icon_item else ""
        check(icon_text not in legacy_ascii_icons,
              f"Row {row} icon '{icon_text}' is legacy ASCII")
        icon_widget = table.cellWidget(row, 0)
        if isinstance(icon_widget, QLabel) and icon_widget.text().strip():
            icons_set += 1
            check(icon_widget.text() not in legacy_ascii_icons,
                  f"Row {row} emoji '{icon_widget.text()}' is legacy ASCII")
        else:
            check(False, f"Row {row} emoji icon label missing")
    check(icons_set == table.rowCount(), f"Emoji icons: {icons_set}/{table.rowCount()}")

    # ---- Wrapped text must not bleed into the next row ----
    min_row_height = getattr(ScannerColumnsHelpDialog, "MIN_ROW_HEIGHT", 74)
    for row in range(table.rowCount()):
        check(table.rowHeight(row) >= min_row_height,
              f"Row {row} height {table.rowHeight(row)} >= {min_row_height}")
    entry_row = next(
        i for i, item in enumerate(ScannerColumnsHelpDialog.COLUMN_HELP)
        if "entry" in item["column"].lower()
    )
    check(table.rowHeight(entry_row) > min_row_height,
          f"Entry status row height {table.rowHeight(entry_row)} > {min_row_height}")

    # ---- Close button ----
    buttons = dialog.findChildren(QDialogButtonBox)
    check(len(buttons) == 1, f"ButtonBoxes: {len(buttons)}")
    close_btn = buttons[0].button(QDialogButtonBox.StandardButton.Close)
    check(close_btn is not None, "Close btn missing")
    check("Đóng" in close_btn.text(), f"Close text: '{_ascii(close_btn.text())}'")
    check("Dong" not in close_btn.text(), f"Close has legacy 'Dong'")

    # ---- Render ----
    if hasattr(dialog, "_sync_help_table_layout"):
        dialog._sync_help_table_layout()
    app.processEvents()

    output_dir = Path(__file__).resolve().parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "scanner_columns_help_dialog_accents_icons_preview.png"
    dialog.grab().save(str(output_path))

    # ---- Print ----
    print("=" * 56)
    print("  ScannerColumnsHelpDialog - Preview Render")
    print("=" * 56)
    print(f"  Dialog:    {dw}x{dh} (min {mw}x{mh})")
    print(f"  Table:     {table.rowCount()} rows x {table.columnCount()} cols")
    print(f"  Title:     {_ascii(title)}")
    print(f"  Headers:   {[_ascii(h) for h in header_texts]}")
    print(f"  Icons:     {icons_set}/{table.rowCount()} emoji")
    print(f"  H-scroll:  {'active' if table.horizontalScrollBar().isVisible() else 'none'}")
    print(f"  Checks:    {len(ok)} passed / {len(errors)} failed")

    if errors:
        print(f"\n  FAILED ({len(errors)}):")
        for e in errors[:15]:
            print(f"    - {e}")
        if len(errors) > 15:
            print(f"    ... and {len(errors) - 15} more")
        dialog.close()
        app.quit()
        return 1

    print(f"  Render:    {output_path}")
    print(f"\n  Vietnamese accents: OK")
    print(f"  Icons:              OK")
    print(f"  Cases:              OK")
    print("\n[PASS] ALL ASSERTIONS PASSED")

    dialog.close()
    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
