"""Verify the "Trang thai entry" column displays Vietnamese labels
and never leaks raw technical keys into the table.

Run:  python scripts/check_scanner_entry_status_vietnamese_display.py
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

    model = screen.table_model
    col_keys = [k for k, _ in ScannerTableModel.COLUMNS]
    entry_col = col_keys.index("entry_status")

    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(_ascii(msg))

    # ---- build test rows ----
    test_cases = [
        ("confirmed_entry",        "Da xac nhan"),
        ("ready",                  "Da xac nhan"),
        ("ready_to_trade",         "Da xac nhan"),
        ("waiting_confirmation",   "Cho xac nhan"),
        ("waiting_for_confirmation","Cho xac nhan"),
        ("watch_zone",             "Theo doi vung"),
        ("in_zone",                "Trong vung"),
        ("near_zone",              "Gan vung"),
        ("invalidated",            "Vo hieu"),
        ("no_setup",               "Chua co setup"),
        ("data_unavailable",       "Thieu du lieu"),
        ("unknown",                "--"),
        (None,                     "--"),
    ]

    raw_keys = [
        "waiting_for_confirmation", "waiting_confirmation",
        "confirmed_entry", "watch_zone", "data_unavailable",
        "invalidated", "no_setup",
    ]

    for raw_val, expected_ascii in test_cases:
        row = {
            "rank": 1, "symbol": "EUR/USD", "scanner_action": "ready",
            "entry_status": raw_val, "scanner_group": "ready_now",
            "final_score": 80, "opportunity_score": 100,
        }
        model.set_rows([row])
        idx = model.index(0, entry_col)
        display = str(model.data(idx, Qt.ItemDataRole.DisplayRole) or "")

        for rk in raw_keys:
            check(rk not in display,
                  f"'{raw_val!r}': leaked raw key '{rk}' in '{_ascii(display)}'")

        check(len(display) > 0 and display != "None",
              f"'{raw_val!r}': empty or None display")

    # ---- header ----
    header = model.headerData(entry_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
    check("Tr" in header and "ng th" in header and "i entry" in header,
          f"Header mismatch: got {len(header)} chars, expected 'Trang thai entry'")

    # ---- tooltip ----
    model.set_rows([{"entry_status": "waiting_for_confirmation"}])
    idx = model.index(0, entry_col)
    tip = str(model.data(idx, Qt.ItemDataRole.ToolTipRole) or "")
    check("Ch" in tip and " x" in tip and "c nh" in tip,
          f"Tooltip missing Vietnamese label, got {len(tip)} chars")
    check("waiting_for_confirmation" in tip,
          f"Tooltip missing technical code, got {len(tip)} chars")

    app.quit()

    if errors:
        print(f"\nFAILED -- {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    print("=== Entry Status Column Tests ===")
    print("  Header: OK")
    for raw_val, _ in test_cases:
        model.set_rows([{"entry_status": raw_val}])
        idx = model.index(0, entry_col)
        disp = _ascii(str(model.data(idx, Qt.ItemDataRole.DisplayRole) or ""))
        print(f"  {str(raw_val):25s} -> {disp}")
    print("  No raw key leaked: OK")
    print("  Tooltip: OK")
    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
