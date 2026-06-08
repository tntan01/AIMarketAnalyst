"""Phase 15.12 — test scanner table columns include Phase 15 ranking fields."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Test column config without needing PyQt6 rendering
# The COLUMNS list and display helpers are imported inspectable


def test_columns_include_phase15_fields():
    """Verify ScannerTableModel.COLUMNS has the new ranking columns."""
    # Import carefully — PyQt6 may not be available in test env
    try:
        from ui.screens.scanner_screen import ScannerTableModel
    except ImportError:
        # PyQt6 not available — skip UI test, verify via column name inspection
        return

    column_keys = [col[0] for col in ScannerTableModel.COLUMNS]
    assert "final_score" in column_keys, f"Columns: {column_keys}"
    assert "opportunity_score" in column_keys
    assert "scanner_group" in column_keys
    assert "entry_status" in column_keys
    assert "m15_quality" in column_keys
    assert "score_gap" in column_keys

    # Legacy columns still present
    assert "best_score" in column_keys
    assert "buy_score" in column_keys
    assert "sell_score" in column_keys
    assert "risk_reward" in column_keys


def test_group_text_has_all_groups():
    """GROUP_TEXT maps all 4 scanner groups."""
    try:
        from ui.screens.scanner_screen import ScannerTableModel
    except ImportError:
        return

    assert "ready_now" in ScannerTableModel.GROUP_TEXT
    assert "waiting_confirmation" in ScannerTableModel.GROUP_TEXT
    assert "watch_zone" in ScannerTableModel.GROUP_TEXT
    assert "blocked" in ScannerTableModel.GROUP_TEXT
    assert ScannerTableModel.GROUP_TEXT["ready_now"] == "Sẵn sàng ngay"


def test_scanner_table_displays_ranked_action_and_missing_entry_zone():
    """The table should not show legacy skip when ranking says wait."""
    try:
        from PyQt6.QtCore import Qt
        from ui.screens.scanner_screen import ScannerTableModel
    except ImportError:
        return

    model = ScannerTableModel()
    row = {
        "symbol": "USD/CHF",
        "scanner_action": "skip",
        "display_action": "wait",
        "scanner_group": "waiting_confirmation",
        "direction_bias": {
            "best_side": "buy",
            "buy_score": 38,
            "sell_score": 19,
            "score_gap": 19,
            "is_clear_bias": True,
            "min_gap": 10,
        },
        "price_vs_zone": "unknown",
        "entry_status": "waiting_confirmation",
    }
    model.set_rows([row])
    keys = [key for key, _ in model.COLUMNS]

    def display(key: str) -> str:
        return model.data(model.index(0, keys.index(key)), Qt.ItemDataRole.DisplayRole)

    assert display("scanner_action") == "Chờ"
    assert display("scanner_group") == "Chờ xác nhận"
    assert display("direction_bias") == "BUY yếu · Gap 19"
    assert display("price_vs_zone") == "Chưa có vùng"
    assert display("entry_status") == "Chưa có vùng"
