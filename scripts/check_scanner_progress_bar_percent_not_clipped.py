"""Verify progress bar shows percentage text, has adequate height for
text+border, and container margins prevent bottom clipping.

Run:  python scripts/check_scanner_progress_bar_percent_not_clipped.py
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

from PyQt6.QtCore import QMargins
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
    pb = screen.progress_bar

    def check(cond, msg):
        if not cond:
            errors.append(msg)

    # ---- text visible + format ----
    check(pb.isTextVisible(), "isTextVisible() should be True")
    check(pb.format() == "%p%", f"format expected '%p%', got {pb.format()!r}")

    # ---- height adequate ----
    h = pb.height()
    check(18 <= h <= 30, f"height {h} not in [18, 30]")
    check(pb.maximumHeight() >= h, f"maximumHeight {pb.maximumHeight()} < {h}")

    # ---- container margins ----
    check(hasattr(screen, "progress_container"), "missing progress_container")
    pc = screen.progress_container
    layout = pc.layout()
    check(layout is not None, "progress_container has no layout")
    margins = layout.contentsMargins()
    check(margins.bottom() >= 4,
          f"container bottom margin {margins.bottom()} < 4 (may clip)")
    check(not pc.isVisible(), "progress_container should be hidden idle")
    check(pc.isHidden(), "progress_container.isHidden() should be True")

    # ---- simulate scan ----
    pc.setVisible(True)
    pb.setVisible(True)
    screen._scan_progress(35, "Dang tai tin tuc va phan tich vi mo...")
    check(pb.value() == 35, f"value should be 35, got {pb.value()}")

    # ---- simulate finished ----
    fake_result = {
        "rows": [], "symbols_scanned": 5, "ai_called": 0,
        "telegram_alerts": {"sent": 0, "errors": []},
        "timestamp": "2026-06-05T10:00:00",
    }
    screen._scan_finished(fake_result)
    check(pb.value() == 100, f"finished value={pb.value()}")
    check(not pb.isVisible(), "bar should be hidden after finish")
    check(not pc.isVisible(), "container should be hidden after finish")

    # ---- output ----
    print(f"  textVisible         = {pb.isTextVisible()}")
    print(f"  format              = {pb.format()}")
    print(f"  height              = {h}px")
    print(f"  container margins   = L:{margins.left()} T:{margins.top()} R:{margins.right()} B:{margins.bottom()}")
    print(f"  value after progress = {pb.value()}")
    print(f"  hidden after finish  = {not pb.isVisible()}")

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
