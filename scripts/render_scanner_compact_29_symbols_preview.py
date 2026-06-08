"""Render a preview of the new compact scanner layout with 29-symbol grid.

Run:  python scripts/render_scanner_compact_29_symbols_preview.py
Output: data/scanner_compact_29_symbols_preview.png
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
from config.constants import SUPPORTED_SYMBOLS


def main() -> int:
    app = QApplication([])

    with (
        mock.patch("services.mt5_service.MT5Service.connection_status"),
        mock.patch("services.mt5_service.MT5Service.configured_symbols_in_market_watch",
                   return_value=[]),
    ):
        screen = ScannerScreen()

    # Set fake rows for visual density
    fake_rows = []
    symbols_cycle = list(sorted(SUPPORTED_SYMBOLS))[:8]
    for repeat in range(3):
        for i, sym in enumerate(symbols_cycle):
            fake_rows.append({
                "rank": repeat * 8 + i + 1,
                "symbol": sym,
                "scanner_action": ["ready", "watch", "wait", "skip", "ready", "watch", "wait", "skip"][i],
                "direction_bias": ["buy", "sell", "buy", "neutral", "buy", "sell", "buy", "neutral"][i],
                "price_vs_zone": ["in_zone", "near_zone", "far", "far", "in_zone", "near_zone", "far", "in_zone"][i],
                "trade_permission": ["allowed", "caution", "caution", "blocked", "allowed", "caution", "caution", "allowed"][i],
                "best_score": 85 - i * 4,
                "final_score": 82 - i * 3,
                "opportunity_score": 108 - i * 5,
                "scanner_group": ["ready_now", "waiting_confirmation", "watch_zone", "blocked",
                                  "ready_now", "waiting_confirmation", "watch_zone", "watch_zone"][i],
                "entry_status": ["confirmed_entry", "waiting_confirmation", "watch_zone", "data_unavailable"][i % 4],
                "m15_quality": ["strict", "loose", "none", "none"][i % 4],
                "score_gap": 20 - i,
                "buy_score": 85 - i * 4,
                "sell_score": 65 - i * 2,
                "macro_score": 28 - i,
                "macro_bias": ["aligned", "neutral", "divergent", "neutral"][i % 4],
                "risk_reward": "1:2.0",
                "short_reason": f"Uu tien MUA, diem {85 - i * 4}/100; SMC 12/15.",
                "detail_action": "View",
                "macro_confidence": 0.9,
                "ai_summary_available": False,
                "permission_reason": "",
            })
    screen.table_model.set_rows(fake_rows)

    # Resize
    screen.resize(1440, 900)
    screen.show()
    app.processEvents()

    # Render
    output_dir = Path(__file__).resolve().parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "scanner_compact_29_symbols_preview.png"
    screen.grab().save(str(output_path))

    print(f"  Rendered = {output_path}")
    print(f"  Window   = {screen.width()}x{screen.height()}")
    print(f"  Symbols  = {len(screen.symbol_boxes)} boxes")
    print(f"  Table    = {screen.table_model.rowCount()} rows x {screen.table_model.columnCount()} cols")
    print(f"  Progress = {screen.progress_bar.height()}px")

    app.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
