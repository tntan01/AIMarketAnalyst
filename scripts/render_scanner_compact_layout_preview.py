"""Render a preview screenshot of the compact scanner layout.

Run:  python scripts/render_scanner_compact_layout_preview.py
Output: data/scanner_compact_layout_preview.png
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
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication
from ui.screens.scanner_screen import ScannerScreen


def main() -> int:
    app = QApplication([])

    with (
        mock.patch("services.mt5_service.MT5Service.connection_status"),
        mock.patch("services.mt5_service.MT5Service.configured_symbols_in_market_watch",
                   return_value=[]),
    ):
        screen = ScannerScreen()

    # Set some fake rows so the table is visible
    fake_rows = [
        {
            "rank": i, "symbol": sym, "scanner_action": act,
            "direction_bias": bias, "price_vs_zone": zone,
            "trade_permission": perm, "best_score": score,
            "final_score": fs, "opportunity_score": ops,
            "scanner_group": grp, "entry_status": es, "m15_quality": m15,
            "score_gap": gap, "buy_score": bs, "sell_score": ss,
            "macro_score": ms, "macro_bias": mb,
            "risk_reward": "1:2.0", "short_reason": "Test reason",
            "detail_action": "View", "macro_confidence": 0.9,
            "ai_summary_available": False, "permission_reason": "",
        }
        for i, (sym, act, bias, zone, perm, score, fs, ops, grp, es, m15, gap, bs, ss, ms, mb) in enumerate(
            [
                ("EUR/USD", "ready", "buy", "in_zone", "allowed", 85, 82, 108, "ready_now", "confirmed_entry", "strict", 20, 85, 60, 28, "aligned"),
                ("GBP/JPY", "watch", "buy", "near_zone", "caution", 76, 71, 90, "waiting_confirmation", "waiting_confirmation", "loose", 8, 76, 60, 20, "neutral"),
                ("XAU/USD", "wait", "sell", "far", "caution", 62, 60, 75, "watch_zone", "watch_zone", "none", 12, 45, 62, 15, "divergent"),
                ("USD/JPY", "skip", "neutral", "far", "blocked", 40, 0, 15, "blocked", "data_unavailable", "none", 0, 40, 50, 15, "neutral"),
                ("AUD/USD", "watch", "buy", "in_zone", "allowed", 78, 75, 100, "waiting_confirmation", "waiting_confirmation", "loose", 14, 78, 58, 22, "aligned"),
                ("NZD/USD", "wait", "sell", "near_zone", "caution", 65, 62, 78, "watch_zone", "watch_zone", "none", 9, 50, 65, 18, "neutral"),
                ("EUR/JPY", "ready", "buy", "in_zone", "allowed", 88, 85, 112, "ready_now", "confirmed_entry", "strict", 22, 88, 52, 30, "aligned"),
                ("GBP/USD", "watch", "sell", "near_zone", "caution", 72, 68, 85, "waiting_confirmation", "waiting_confirmation", "loose", 6, 55, 72, 20, "divergent"),
            ]
        )
    ] * 3  # 24 rows for visual density

    screen.table_model.set_rows(fake_rows)

    # Resize to typical window size
    screen.resize(1440, 900)
    screen.show()
    QGuiApplication.processEvents()

    # Render to PNG
    output_dir = Path(__file__).resolve().parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "scanner_compact_layout_preview.png"
    screen.grab().save(str(output_path))

    print(f"  Rendered = {output_path}")
    print(f"  Window size = {screen.width()}x{screen.height()}")
    print(f"  Table rows = {screen.table_model.rowCount()}")
    print(f"  Symbol scroll maxH = {screen.findChildren(type(screen).__bases__[0])}")

    # Print layout stats
    from PyQt6.QtWidgets import QScrollArea
    scrolls = [s for s in screen.findChildren(QScrollArea) if s.objectName() == "SymbolScroll"]
    if scrolls:
        print(f"  SymbolScroll maxH = {scrolls[0].maximumHeight()}")
    print(f"  Progress bar H = {screen.progress_bar.height()}")
    print(f"  Stop btn visible = {screen.stop_auto_scan_button.isVisible()}")
    print(f"  Has status_summary_label = {screen.status_summary_label.text() != ''}")

    app.quit()
    print("\nDone. Open the PNG to review the compact layout.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
