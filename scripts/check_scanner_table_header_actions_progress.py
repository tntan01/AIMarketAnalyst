"""Verify table header action buttons and progress bar container behavior.

Checks: detail/save buttons in header (not bottom row), disabled by default,
progress container hidden idle, visible during scan, hidden after finish.

Run:  python scripts/check_scanner_table_header_actions_progress.py
Requires: PyQt6, no MT5, no network.
"""
from __future__ import annotations

import inspect
import os
import sys
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QApplication
from ui.screens.scanner_screen import ScannerScreen


def main() -> int:
    app = QApplication([])

    with (
        mock.patch("services.mt5_service.MT5Service"),
        mock.patch("controllers.scanner_controller.ScannerController"),
    ):
        screen = ScannerScreen()

    errors: list[str] = []

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # ---- critical controls ----
    check(hasattr(screen, "table"), "missing table")
    check(hasattr(screen, "help_button"), "missing help_button")
    check(hasattr(screen, "detail_button"), "missing detail_button")
    check(hasattr(screen, "save_button"), "missing save_button")
    check(not screen.detail_button.isEnabled(), "detail_button should be disabled")
    check(not screen.save_button.isEnabled(), "save_button should be disabled")
    check(hasattr(screen, "progress_bar"), "missing progress_bar")
    check(18 <= screen.progress_bar.height() <= 30,
          f"progress bar height {screen.progress_bar.height()} not in [18,30]")
    check(screen.progress_bar.isTextVisible(), "isTextVisible should be True")
    check(screen.progress_bar.format() == "%p%",
          f"format expected '%p%', got {screen.progress_bar.format()!r}")

    # ---- progress container ----
    check(hasattr(screen, "progress_container"), "missing progress_container")
    check(not screen.progress_container.isVisible(),
          f"progress_container should be hidden idle, isVisible={screen.progress_container.isVisible()}")
    check(screen.progress_container.isHidden(),
          "progress_container.isHidden() should be True")

    # ---- simulate scan progress ----
    screen.progress_container.setVisible(True)
    screen.progress_bar.setVisible(True)
    screen._scan_progress(35, "Dang quet EUR/USD...")
    check(screen.progress_bar.value() == 35, f"value should be 35, got {screen.progress_bar.value()}")

    # ---- simulate finished ----
    fake_result = {
        "rows": [], "symbols_scanned": 5, "ai_called": 0,
        "telegram_alerts": {"sent": 0, "errors": []},
        "timestamp": "2026-06-05T10:00:00",
    }
    screen._scan_finished(fake_result)
    check(screen.progress_bar.value() == 100, f"finished value={screen.progress_bar.value()}")
    check(not screen.progress_bar.isVisible(), "bar should be hidden after finish")
    check(not screen.progress_container.isVisible(), "container should be hidden after finish")

    # ---- code review: verify _table_card structure ----
    source = inspect.getsource(ScannerScreen._table_card)
    has_header_buttons = (
        "self .detail_button" in source and "self .save_button" in source and
        "header_layout .addWidget" in source
    )
    check(has_header_buttons, "detail/save buttons must be in header_layout")
    # Confirm no separate actions row below table
    no_bottom_actions = "actions =QHBoxLayout" not in source
    check(no_bottom_actions, "bottom actions layout should be removed")

    # ---- output ----
    print(f"  detail_button disabled = {not screen.detail_button.isEnabled()}")
    print(f"  save_button disabled   = {not screen.save_button.isEnabled()}")
    print(f"  progress bar height    = {screen.progress_bar.height()}px")
    print(f"  progress idle hidden   = {screen.progress_container.isHidden()}")
    print(f"  progress value (scan)  = {screen.progress_bar.value()}")
    print(f"  progress hidden (fin)  = {not screen.progress_bar.isVisible()}")
    print(f"  container hidden (fin) = {not screen.progress_container.isVisible()}")

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
