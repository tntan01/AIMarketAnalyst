"""Test that ScannerColumnsHelpDialog COLUMN_HELP covers all ScannerTableModel.COLUMNS.

Validates: proper Vietnamese diacritics, non-ASCII icons, complete cases fields,
correct table structure, and no regression to old unaccented text.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Old ASCII icon strings that must NOT appear
_LEGACY_ASCII_ICONS = {
    "#", "FX", ">>", "<>", "(+)", "(S)", "*", "V", "~", "::",
    "(o)", "M5", "<->", "^", "v", "@", "~>", ":", '"', ">",
}

# Old unaccented column names that must NOT appear anywhere in dialog
_LEGACY_ACCENTLESS = [
    "Giai thich", "Bang ket qua quet",
    "Cot", "Y nghia", "Truong hop thuong gap",
    "Xep hang", "Hanh dong", "Xu huong", "Quyen", "Diem tot nhat",
    "Co hoi", "Nhom", "Trang thai entry", "Vi mo", "Thuan vi mo",
    "Ly do chinh", "Chi tiet", "Dong",
]


# ---- Import-level tests (no QApplication needed) ----


def test_help_covers_all_columns():
    """Every column in ScannerTableModel.COLUMNS has a help entry."""
    try:
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog, ScannerTableModel
    except ImportError:
        return

    assert len(ScannerColumnsHelpDialog.COLUMN_HELP) == len(ScannerTableModel.COLUMNS), (
        f"COLUMN_HELP has {len(ScannerColumnsHelpDialog.COLUMN_HELP)} entries "
        f"but COLUMNS has {len(ScannerTableModel.COLUMNS)} columns"
    )


def test_help_entries_have_required_keys():
    """Each COLUMN_HELP entry has icon, column, meaning, cases — all non-empty."""
    try:
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog
    except ImportError:
        return

    for i, item in enumerate(ScannerColumnsHelpDialog.COLUMN_HELP):
        assert isinstance(item, dict), f"Entry {i} is not a dict"
        for key in ("icon", "column", "meaning", "cases"):
            assert key in item, f"Entry {i} missing '{key}'"
            assert item[key].strip(), f"Entry {i} has empty '{key}'"


def test_no_legacy_column_names():
    """Column headers have proper Vietnamese diacritics, not old ASCII names."""
    try:
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog
    except ImportError:
        return

    columns = [item["column"] for item in ScannerColumnsHelpDialog.COLUMN_HELP]

    for legacy in _LEGACY_ACCENTLESS:
        assert legacy not in columns, (
            f"Legacy unaccented column name '{legacy}' still in help columns"
        )

    required = [
        "Xếp hạng", "Mã", "Hành động", "Xu hướng", "Quyền",
        "Điểm tốt nhất", "Cơ hội", "Nhóm", "Trạng thái entry",
        "Vĩ mô (0-30)", "Thuận vĩ mô", "Lý do chính", "Chi tiết",
    ]
    for name in required:
        assert name in columns, f"Missing required column '{name}'"


def test_no_legacy_ascii_in_meaning_or_cases():
    """Meaning and cases fields must not contain old unaccented text."""
    try:
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog
    except ImportError:
        return

    for i, item in enumerate(ScannerColumnsHelpDialog.COLUMN_HELP):
        combined = item.get("meaning", "") + " " + item.get("cases", "")
        for legacy in _LEGACY_ACCENTLESS:
            assert legacy not in combined, (
                f"Entry {i} ('{item['column']}'): legacy text '{legacy}' in meaning/cases"
            )


def test_icons_not_ascii_fallback():
    """Icon strings must not be old ASCII fallbacks like '#', 'FX', '>>'."""
    try:
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog
    except ImportError:
        return

    for i, item in enumerate(ScannerColumnsHelpDialog.COLUMN_HELP):
        icon = item.get("icon", "")
        assert icon not in _LEGACY_ASCII_ICONS, (
            f"Entry {i} ('{item['column']}'): icon '{icon}' is legacy ASCII fallback"
        )
        assert icon.strip(), f"Entry {i}: empty icon"


def test_help_order_matches_columns():
    """Help entries are in the same order as table columns."""
    try:
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog, ScannerTableModel
    except ImportError:
        return

    help_columns = [item["column"] for item in ScannerColumnsHelpDialog.COLUMN_HELP]

    assert help_columns[0] == "Xếp hạng"
    assert help_columns[1] == "Mã"
    assert help_columns[2] == "Hành động"
    assert help_columns[3] == "Xu hướng"
    assert help_columns[4] == "Entry"
    assert help_columns[7] == "Final"
    assert help_columns[8] == "Cơ hội"
    assert help_columns[9] == "Nhóm"
    assert help_columns[10] == "Trạng thái entry"
    assert help_columns[11] == "M15"
    assert help_columns[12] == "Gap"
    assert help_columns[-1] == "Chi tiết"


def test_cases_cover_all_required_values():
    """Each column's 'cases' field mentions the common values users see."""
    try:
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog
    except ImportError:
        return

    lookup: dict[str, str] = {}
    for item in ScannerColumnsHelpDialog.COLUMN_HELP:
        lookup[item["column"]] = item.get("meaning", "") + " " + item.get("cases", "")

    # Hành động: 4 action levels
    for term in ("Sẵn sàng", "Theo dõi", "Chờ", "Bỏ qua"):
        assert term in lookup["Hành động"], f"Hành động cases missing '{term}'"

    # Xu hướng: direction granularity
    for term in ("BUY rõ", "SELL rõ", "BUY yếu", "SELL yếu", "Trung lập"):
        assert term in lookup["Xu hướng"], f"Xu hướng cases missing '{term}'"

    # Entry: zone proximity
    for term in ("Trong vùng", "Gần vùng", "Còn xa"):
        assert term in lookup["Entry"], f"Entry cases missing '{term}'"

    # Quyền: permission tiers
    for term in ("Được phép", "Cẩn trọng", "Bị chặn"):
        assert term in lookup["Quyền"], f"Quyền cases missing '{term}'"

    # Nhóm: all 4 scanner groups
    for term in ("Sẵn sàng ngay", "Chờ xác nhận", "Theo dõi"):
        assert term in lookup["Nhóm"], f"Nhóm cases missing '{term}'"

    # Trạng thái entry: all statuses
    entry_text = lookup["Trạng thái entry"]
    for term in ("Sẵn sàng", "Chờ xác nhận", "Theo dõi vùng", "Thiếu dữ liệu"):
        assert term in entry_text, f"Trạng thái entry cases missing '{term}'"

    # M15: quality levels
    for term in ("strict", "loose"):
        assert term in lookup["M15"], f"M15 cases missing '{term}'"

    # Thuận vĩ mô: alignment directions
    for term in ("Thuận", "Trung tính", "Ngược"):
        assert term in lookup["Thuận vĩ mô"], f"Thuận vĩ mô cases missing '{term}'"


# ---- QApplication-level tests ----


def test_dialog_widget_structure():
    """Open the dialog with QApplication and verify table, icons, headers."""
    try:
        from PyQt6.QtCore import Qt
        from PyQt6.QtWidgets import QApplication, QLabel, QTableWidget, QDialogButtonBox
        from ui.screens.scanner_screen import ScannerColumnsHelpDialog, ScannerTableModel
    except ImportError:
        return

    app = QApplication([])
    dialog = ScannerColumnsHelpDialog()
    dialog.show()
    app.processEvents()

    try:
        # Window title
        assert dialog.windowTitle() == "Giải thích Bảng kết quả quét", (
            f"Window title: '{dialog.windowTitle()}'"
        )

        assert hasattr(dialog, "help_table")
        table = dialog.help_table
        assert isinstance(table, QTableWidget)
        assert table.rowCount() == len(ScannerColumnsHelpDialog.COLUMN_HELP)
        assert table.columnCount() == 4
        assert table.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff

        # Header labels — must have proper Vietnamese with diacritics
        header_texts = []
        for c in range(table.columnCount()):
            item = table.horizontalHeaderItem(c)
            header_texts.append(item.text() if item else "")
        assert header_texts[0] == ""
        assert "Cột" in header_texts[1], f"Header col 1: '{header_texts[1]}'"
        assert "Ý nghĩa" in header_texts[2], f"Header col 2: '{header_texts[2]}'"
        assert "Trường hợp" in header_texts[3], f"Header col 3: '{header_texts[3]}'"

        # No legacy unaccented text in any header
        all_headers = " ".join(header_texts)
        for legacy in ("Giai thich", "Cot", "Y nghia", "Truong hop thuong gap"):
            assert legacy not in all_headers, f"Legacy text '{legacy}' in headers"

        assert dialog.isModal()
        assert dialog.objectName() == "ScannerHelpDialog"

        # Close button text
        buttons = dialog.findChildren(QDialogButtonBox)
        assert len(buttons) == 1
        close_btn = buttons[0].button(QDialogButtonBox.StandardButton.Close)
        assert close_btn is not None
        assert "Đóng" in close_btn.text()
        assert "Dong" not in close_btn.text(), "Close button still has 'Dong'"

        # Icons: lively emoji labels, no legacy ASCII-only fallbacks.
        old_ascii_icons = {"#", "FX", ">>", "<>", "(+)", "(S)", "*", "V", "~", "::", "(o)", "@", "~>", ":"}
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            icon_text = item.text() if item else ""
            assert icon_text not in old_ascii_icons, (
                f"Row {row}: icon text '{icon_text}' is legacy ASCII fallback"
            )
            icon_widget = table.cellWidget(row, 0)
            assert isinstance(icon_widget, QLabel), f"Row {row}: icon widget missing"
            assert icon_widget.text().strip(), f"Row {row}: emoji icon is empty"
            assert icon_widget.text() not in old_ascii_icons, (
                f"Row {row}: emoji icon '{icon_widget.text()}' is legacy ASCII fallback"
            )

        # Long wrapped text must get enough row height; otherwise it bleeds
        # into the next row in the rendered dialog.
        for row in range(table.rowCount()):
            assert table.rowHeight(row) >= ScannerColumnsHelpDialog.MIN_ROW_HEIGHT
        entry_row = next(
            i for i, item in enumerate(ScannerColumnsHelpDialog.COLUMN_HELP)
            if "entry" in item["column"].lower()
        )
        assert table.rowHeight(entry_row) > ScannerColumnsHelpDialog.MIN_ROW_HEIGHT

    finally:
        dialog.close()
        app.quit()
