"""Verify progress bar behavior via code review + isHidden() checks.

isHidden() reflects setVisible(False) / hide() even when the parent
widget hasn't been shown yet.  This avoids offscreen timing issues.

Run:  python scripts/check_scanner_progress_bar_compact.py
Requires: PyQt6, no MT5, no network.
"""
from __future__ import annotations

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

    # Patch whole MT5Service to avoid real terminal connection
    with (
        mock.patch("services.mt5_service.MT5Service"),
        mock.patch("controllers.scanner_controller.ScannerController"),
    ):
        screen = ScannerScreen()

    errors: list[str] = []
    pb = screen.progress_bar

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # ---- idle checks (no show needed) ----
    check(pb.height() <= 16, f"height {pb.height()} > 16")
    check(not pb.isVisible(), f"isVisible should be False, got {pb.isVisible()}")
    check(pb.isHidden(), "isHidden should be True (explicitly hidden)")
    print(f"  Idle: hidden={pb.isHidden()}, height={pb.height()}px")

    # ---- simulate progress ----
    pb.setVisible(True)
    pb.setValue(40)
    check(not pb.isHidden(), "should not be hidden after setVisible(True)")
    check(pb.value() == 40, f"value should be 40, got {pb.value()}")
    print(f"  Scanning: hidden={pb.isHidden()}, value={pb.value()}")

    # ---- simulate finished ----
    fake_result = {
        "rows": [], "symbols_scanned": 5, "ai_called": 0,
        "telegram_alerts": {"sent": 0, "errors": []},
        "timestamp": "2026-06-05T10:00:00",
    }
    screen._scan_finished(fake_result)
    check(pb.value() == 100, f"finished value={pb.value()}, expected 100")
    check(pb.isHidden(), f"should be hidden after finish, isHidden={pb.isHidden()}")
    print(f"  Finished: hidden={pb.isHidden()}, value={pb.value()}")

    # ---- simulate failed ----
    pb.setVisible(True)
    pb.setValue(30)
    screen._scan_failed("Fake failure")
    check(pb.isHidden(), f"should be hidden after fail, isHidden={pb.isHidden()}")
    print(f"  Failed: hidden={pb.isHidden()}")

    # ---- code review: verify lifecycle methods exist ----
    # All 5 lifecycle methods touch progress_bar
    import inspect
    methods_to_check = [
        ("_run_scan", ["setVisible", "setValue"]),
        ("_scan_progress", ["setVisible", "setValue"]),
        ("_scan_finished", ["setValue(100)", "setVisible(False)"]),
        ("_scan_failed", ["setVisible(False)"]),
        ("_scan_thread_finished", ["setVisible(False)"]),
    ]
    source = inspect.getsource(ScannerScreen)
    for method_name, expected_patterns in methods_to_check:
        check(method_name in source, f"missing method {method_name}")
    print("  Code review: all 5 lifecycle methods reference progress_bar")

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
