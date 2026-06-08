"""Verify the "Xu hướng" (direction_bias) column displays correctly
and never leaks raw dict internals into the table.

Run:  python scripts/check_scanner_direction_bias_display.py
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


def main() -> int:
    app = QApplication([])

    with (
        mock.patch("services.mt5_service.MT5Service"),
        mock.patch("controllers.scanner_controller.ScannerController"),
    ):
        screen = ScannerScreen()

    model = screen.table_model
    col_keys = [k for k, _ in ScannerTableModel.COLUMNS]
    bias_col = col_keys.index("direction_bias")

    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # ---- build realistic rows ----
    rows = [
        {
            "rank": 1, "symbol": "GBP/CAD", "scanner_action": "skip",
            "direction_bias": {"best_side": "buy", "buy_score": 54.0, "sell_score": 44.0,
                              "score_gap": 10.0, "is_clear_bias": True, "min_gap": 10},
            "short_reason": "test",
        },
        {
            "rank": 2, "symbol": "EUR/USD", "scanner_action": "ready",
            "direction_bias": {"best_side": "sell", "buy_score": 44.0, "sell_score": 56.0,
                              "score_gap": 12.0, "is_clear_bias": True, "min_gap": 10},
            "short_reason": "test",
        },
        {
            "rank": 3, "symbol": "USD/JPY", "scanner_action": "watch",
            "direction_bias": {"best_side": "buy", "buy_score": 52.0, "sell_score": 46.0,
                              "score_gap": 6.0, "is_clear_bias": False, "min_gap": 10},
            "short_reason": "test",
        },
        {
            "rank": 4, "symbol": "XAU/USD", "scanner_action": "wait",
            "direction_bias": {"best_side": "sell", "buy_score": 48.0, "sell_score": 55.0,
                              "score_gap": 7.0, "is_clear_bias": False, "min_gap": 10},
            "short_reason": "test",
        },
        {
            "rank": 5, "symbol": "AUD/USD", "scanner_action": "skip",
            "direction_bias": {"best_side": "neutral", "buy_score": 50.0, "sell_score": 50.0,
                              "score_gap": 0.0, "is_clear_bias": False, "min_gap": 10},
            "short_reason": "test",
        },
        {
            "rank": 6, "symbol": "NZD/USD", "scanner_action": "watch",
            "direction_bias": "buy",
            "short_reason": "test",
        },
        {
            "rank": 7, "symbol": "USD/CHF", "scanner_action": "skip",
            "direction_bias": None,
            "short_reason": "test",
        },
    ]
    model.set_rows(rows)

    # ---- expected DisplayRole values ----
    expected_displays = [
        "BUY rõ",
        "SELL rõ",
        "BUY yếu",
        "SELL yếu",
        "Trung lập",
        "Mua",    # legacy string "buy" → BIAS_TEXT mapping
        "--",
    ]
    raw_leak_patterns = ["{", "}", "'best_side'", "buy_score", "sell_score"]

    for i, expected in enumerate(expected_displays):
        idx = model.index(i, bias_col)
        display = str(model.data(idx, Qt.ItemDataRole.DisplayRole) or "")

        check(display == expected,
              f"Row {i + 1}: expected '{expected}', got '{display}'")

        for pat in raw_leak_patterns:
            check(pat not in display,
                  f"Row {i + 1}: raw dict leaked in display — found '{pat}' in '{display}'")

        # Tooltip must not be raw dict
        tip = str(model.data(idx, Qt.ItemDataRole.ToolTipRole) or "")
        check("{" not in tip,
              f"Row {i + 1}: tooltip leaked raw dict — '{tip}'")

        # Tooltip for dict rows should have score info
        if i < 5:
            check(("/" in tip or "?" in tip or "Gap" in tip),
                  f"Row {i + 1}: tooltip missing score info — '{tip}'")

    # ---- header ----
    header = model.headerData(bias_col, Qt.Orientation.Horizontal, Qt.ItemDataRole.DisplayRole)
    check(header == "Xu hướng", f"Header expected 'Xu hướng', got '{header}'")

    # ---- no raw data leaked in any cell ----
    for i in range(len(rows)):
        idx = model.index(i, bias_col)
        display_text = str(model.data(idx, Qt.ItemDataRole.DisplayRole) or "")
        for pat in raw_leak_patterns:
            check(pat not in display_text,
                  f"Final check row {i + 1}: '{pat}' leaked in '{display_text}'")

    app.quit()

    if errors:
        print(f"\nFAILED — {len(errors)} assertion(s):")
        for e in errors:
            print(f"  - {e}")
        return 1

    # ---- summary ----
    print("=== Direction Bias Column Tests ===")
    print("  Header Xu huong           : OK")
    for i, expected in enumerate(expected_displays):
        label = expected.replace("õ", "o").replace("ế", "e").replace("ậ", "a").replace("ụ", "u").replace("ổ", "o")
        print(f"  Row {i + 1} ({label:12s}): OK")
    print("  No raw dict leaked        : OK")
    print("  Tooltips valid            : OK")
    print("\n[PASS] ALL ASSERTIONS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
