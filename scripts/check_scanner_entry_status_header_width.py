"""Verify the "Trang thai entry" column header has sufficient width
and is not clipped, after the TABLE_EXTRA_COLUMN_PADDING fix.

Run:  python scripts/check_scanner_entry_status_header_width.py
Requires: PyQt6, no MT5, no network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication
from ui.screens.scanner_screen import ScannerScreen, ScannerTableModel


def _ascii(s: str) -> str:
    return s.encode("ascii", "replace").decode()


def main() -> int:
    app = QApplication([])

    with (
        mock.patch("services.mt5_service.MT5Service"),
        mock.patch("controllers.scanner_controller.ScannerController"),
    ):
        screen = ScannerScreen()

    col_keys = [k for k, _ in ScannerTableModel.COLUMNS]
    entry_col = col_keys.index("entry_status")

    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(_ascii(msg))

    # ---- verify extra padding config ----
    extra = ScannerScreen.TABLE_EXTRA_COLUMN_PADDING.get(entry_col, 0)
    check(extra >= 18, f"TABLE_EXTRA_COLUMN_PADDING[{entry_col}] = {extra}, need >= 18")

    # ---- set realistic rows ----
    rows = [
        {
            "rank": 1, "symbol": "EUR/USD", "scanner_action": "ready",
            "entry_status": "waiting_for_confirmation",
            "scanner_group": "waiting_confirmation",
            "final_score": 80, "opportunity_score": 100,
            "short_reason": "test",
        },
        {
            "rank": 2, "symbol": "GBP/CAD", "scanner_action": "watch",
            "entry_status": "confirmed_entry",
            "scanner_group": "ready_now",
            "final_score": 85, "opportunity_score": 110,
            "short_reason": "test",
        },
        {
            "rank": 3, "symbol": "XAU/USD", "scanner_action": "wait",
            "entry_status": "watch_zone",
            "scanner_group": "watch_zone",
            "final_score": 65, "opportunity_score": 80,
            "short_reason": "test",
        },
        {
            "rank": 4, "symbol": "USD/JPY", "scanner_action": "skip",
            "entry_status": "data_unavailable",
            "scanner_group": "blocked",
            "final_score": 0, "opportunity_score": 15,
            "short_reason": "test",
        },
    ]
    screen.table_model.set_rows(rows)
    screen.resize(1450, 850)
    screen.show()
    app.processEvents()
    screen._configure_table_columns()
    app.processEvents()

    header = screen.table.horizontalHeader()

    # ---- header label ----
    header_label = screen.table_model.headerData(
        entry_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole
    )
    check("Tr" in header_label and "ng th" in header_label and "i entry" in header_label,
          f"Header label mismatch, got {len(header_label)} chars")

    # ---- width check ----
    section_width = header.sectionSize(entry_col)
    text_width = header.fontMetrics().horizontalAdvance(header_label)
    padding = section_width - text_width
    check(padding >= 24,
          f"Padding {padding}px too small (width={section_width}, text={text_width})")

    # ---- display value check ----
    idx = screen.table_model.index(0, entry_col)
    display = str(screen.table_model.data(idx, Qt.ItemDataRole.DisplayRole) or "")
    check("Ch" in display and " x" in display and "c nh" in display,
          f"DisplayRole mismatch: {_ascii(display)}")

    # ---- resize mode ----
    from PyQt6.QtWidgets import QHeaderView
    mode = header.sectionResizeMode(entry_col)
    check(mode == QHeaderView.ResizeMode.Fixed,
          f"ResizeMode should be Fixed, got {mode}")

    app.quit()

    if errors:
        print(f"\nFAILED -- {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("=== Entry Status Header Width Test ===")
    print(f"  entry_status column index : {entry_col}")
    print(f"  TABLE_EXTRA_COLUMN_PADDING: {extra}px")
    print(f"  section width             : {section_width}px")
    print(f"  header text width         : {text_width}px")
    print(f"  padding                   : {padding}px")
    print("  Header width: OK")
    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
