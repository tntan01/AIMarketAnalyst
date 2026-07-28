import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PyQt6.QtWidgets import QApplication, QLabel, QWidget
from PyQt6.QtCore import QEvent
from ui.screens.scanner_detail_screen import ScannerDetailScreen

def test_refresh_checklist_panel_no_duplicates():
    app = QApplication.instance() or QApplication(sys.argv)
    
    screen = ScannerDetailScreen()
    mock_row = {
        "best_score": 85,
        "score_gap": 15,
        "buy_score": 85,
        "sell_score": 70,
        "trade_permission": "allowed",
        "entry_status": "watch_zone",
        "m15_quality": "strict",
        "price_vs_zone": "in_zone",
        "risk_reward": "1:2.3",
        "min_score": 65,
        "analysis_result": {"trade_gate": {"allowed": True, "reasons": []}}
    }
    screen.row = mock_row

    # First refresh
    screen._refresh_checklist_panel()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    labels_after_first = screen.checklist_panel.findChildren(QLabel)
    first_count = len(labels_after_first)

    # Second refresh
    screen._refresh_checklist_panel()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    labels_after_second = screen.checklist_panel.findChildren(QLabel)
    second_count = len(labels_after_second)

    print(f"First refresh QLabel count: {first_count}")
    print(f"Second refresh QLabel count: {second_count}")

    assert first_count == second_count, f"Duplicate labels detected! First: {first_count}, Second: {second_count}"
    print("PASS: No duplicate widgets detected after consecutive refreshes.")


def test_overview_splitter_defaults_to_30_70_information_chart_ratio():
    app = QApplication.instance() or QApplication(sys.argv)
    screen = ScannerDetailScreen()

    screen.resize(1200, 800)
    screen.show()
    app.processEvents()

    sizes = screen.overview_splitter.sizes()
    assert sum(sizes) > 0
    information_ratio = sizes[0] / sum(sizes)
    assert 0.27 <= information_ratio <= 0.33

    screen.close()
    assert app is QApplication.instance()


def test_trade_panel_renders_tp1_and_tp2_on_separate_rows():
    app = QApplication.instance() or QApplication(sys.argv)
    screen = ScannerDetailScreen()
    screen.row = {
        "entry_zone": [1.1000, 1.1010],
        "take_profit": [1.1050, 1.1100],
    }

    screen._refresh_trade_panel()

    labels = [
        label.text()
        for label in screen.trade_panel.findChildren(QLabel)
        if label.objectName() == "ScannerPanelLabel"
    ]
    values = [
        label.text()
        for label in screen.trade_panel.findChildren(QLabel)
        if label.objectName() == "ScannerPanelValue"
    ]

    assert "TP1" in labels
    assert "TP2" in labels
    assert "Take Profit" not in labels
    assert "1.10500" in values
    assert "1.11000" in values

    screen.close()
    assert app is QApplication.instance()


if __name__ == "__main__":
    test_refresh_checklist_panel_no_duplicates()
