"""Verify the compact scanner layout: no scrollbar, 8-col symbol grid,
29 symbols, thin progress bar, hidden stop button, full table columns.

Run:  python scripts/check_scanner_compact_layout.py
Requires: PyQt6, no MT5, no network.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication, QGridLayout, QScrollArea
from config.constants import SUPPORTED_SYMBOLS
from ui.screens.scanner_screen import ScannerScreen, ScannerTableModel


def main() -> int:
    app = QApplication([])

    with (
        mock.patch("services.mt5_service.MT5Service.connection_status"),
        mock.patch("services.mt5_service.MT5Service.configured_symbols_in_market_watch",
                   return_value=[]),
    ):
        screen = ScannerScreen()

    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # ---- critical controls ----
    check(hasattr(screen, "table"), "missing table")
    check(hasattr(screen, "scan_button"), "missing scan_button")
    check(hasattr(screen, "scan_mode_combo"), "missing scan_mode_combo")
    check(hasattr(screen, "scan_interval_combo"), "missing scan_interval_combo")
    check(hasattr(screen, "auto_trade_check"), "missing auto_trade_check")
    check(hasattr(screen, "stop_auto_scan_button"), "missing stop_auto_scan_button")
    check(hasattr(screen, "progress_bar"), "missing progress_bar")
    check(hasattr(screen, "status_summary_label"), "missing status_summary_label")
    check(hasattr(screen, "detail_button"), "missing detail_button")
    check(hasattr(screen, "save_button"), "missing save_button")
    check(hasattr(screen, "all_symbols_check"), "missing all_symbols_check")

    # ---- table columns ----
    col_count = screen.table_model.columnCount()
    check(col_count == len(ScannerTableModel.COLUMNS),
          f"columns: {col_count} != {len(ScannerTableModel.COLUMNS)}")

    # ---- symbol checkboxes: 29, no scroll, 8 cols ----
    n_symbols = len(screen.symbol_boxes)
    check(n_symbols == len(SUPPORTED_SYMBOLS),
          f"symbol_boxes: {n_symbols} != {len(SUPPORTED_SYMBOLS)}")

    scrolls = screen.findChildren(QScrollArea)
    symbol_scrolls = [s for s in scrolls if s.objectName() == "SymbolScroll"]
    check(len(symbol_scrolls) == 0,
          f"SymbolScroll should be removed, found {len(symbol_scrolls)}")

    # Find the QGridLayout holding the symbol checkboxes (the first checkbox's parent layout)
    grid_cols = 0
    grid_rows = 0
    if screen.symbol_boxes:
        first_box = screen.symbol_boxes[0]
        parent = first_box.parentWidget()
        if parent and parent.layout() and isinstance(parent.layout(), QGridLayout):
            gl = parent.layout()
            for i in range(gl.count()):
                row, col, _, _ = gl.getItemPosition(i)
                grid_rows = max(grid_rows, row + 1)
                grid_cols = max(grid_cols, col + 1)
    check(grid_cols == 8, f"grid columns: {grid_cols} != 8")
    check(grid_rows == 4, f"grid rows: {grid_rows} != 4 (29 symbols / 8 cols)")

    # ---- stop button hidden ----
    check(not screen.stop_auto_scan_button.isVisible(),
          "stop_auto_scan_button should be hidden by default")
    check(not screen.auto_trade_check.isChecked(),
          "auto_trade_check toggle button should be off by default")
    check(not screen.auto_trade_check.isEnabled(),
          "auto_trade_check toggle button should be disabled in one-shot scan mode")

    # ---- status_labels ----
    check(hasattr(screen, "status_labels"), "missing status_labels dict")
    for key in ("MT5", "Đã quét", "AI đã gọi", "Telegram", "Lần quét gần nhất"):
        check(key in screen.status_labels, f"status_labels missing '{key}'")

    # ---- progress bar: percent visible, adequate height, hidden idle ----
    pb_h = screen.progress_bar.height()
    check(18 <= pb_h <= 30, f"progress bar height {pb_h} not in [18, 30]")
    check(screen.progress_bar.isTextVisible(), "isTextVisible should be True")
    check(screen.progress_bar.format() == "%p%", f"format should be '%p%', got {screen.progress_bar.format()!r}")
    check(not screen.progress_bar.isVisible(),
          f"progress bar should be hidden idle, isVisible={screen.progress_bar.isVisible()}")
    check(screen.progress_bar.isHidden(),
          "progress bar should be explicitly hidden")

    # ---- output ----
    print(f"  Symbol boxes      = {n_symbols}")
    print(f"  Symbol grid       = {grid_cols} cols x {grid_rows} rows")
    print(f"  SymbolScroll      = {len(symbol_scrolls)} (expect 0)")
    print(f"  Table columns     = {col_count}")
    print(f"  Progress bar H    = {pb_h}px")
    print(f"  Progress text     = {screen.progress_bar.isTextVisible()}")
    print(f"  Progress format   = {screen.progress_bar.format()!r}")
    print(f"  Progress hidden   = {screen.progress_bar.isHidden()}")
    print(f"  Stop btn visible  = {screen.stop_auto_scan_button.isVisible()}")
    has_summary = len(screen.status_summary_label.text()) > 5
    print(f"  Status summary    = {'present' if has_summary else 'missing'}")

    app.quit()

    if errors:
        print(f"\nFAILED — {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
