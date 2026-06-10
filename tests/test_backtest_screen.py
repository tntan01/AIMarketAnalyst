from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QLabel, QAbstractSpinBox, QDialogButtonBox
from PyQt6.QtWidgets import QHeaderView

from ui.navigation import NAV_ITEMS
from ui.screens.backtest_screen import BacktestInputHelpDialog, BacktestScreen


def test_backtest_navigation_item_exists() -> None:
    assert ("backtest", "Backtest") in NAV_ITEMS


def test_backtest_screen_renders_summary_and_trade_rows() -> None:
    app = QApplication.instance() or QApplication([])
    screen = BacktestScreen()

    screen._set_summary(
        {
            "total_trades": 2,
            "win_rate": 50.0,
            "expectancy_r": 0.25,
            "profit_factor": 1.5,
            "max_drawdown_r": 1.0,
            "total_r": 1234.5,
        }
    )
    screen._set_trades(
        [
            {
                "entry_time": "2026-01-01T00:00:00+00:00",
                "side": "buy",
                "result": "win",
                "result_r": 2.0,
                "entry_price": 1.1,
                "stop_loss": 1.09,
                "take_profit": 1.12,
                "final_score": 82,
                "signal_score": 84,
                "m15_quality": "strict",
                "market_regime": "trend_up",
                "selected_zone_score": 81,
            }
        ]
    )

    assert screen.table.rowCount() == 1
    assert screen.table.item(0, 0).text() == "01-01-2026 07:00:00"
    assert screen.table.item(0, 1).text() == "buy"
    assert screen.table.item(0, 2).text() == "win"
    assert screen.table.item(0, 3).text() == "2.00"
    assert screen.table.item(0, 4).text() == "1.10000"
    assert not screen.table.verticalHeader().isVisible()
    assert not screen.table.horizontalHeader().stretchLastSection()
    assert screen.table.horizontalHeader().sectionResizeMode(11) == QHeaderView.ResizeMode.Fixed
    screen.table.resize(1200, 320)
    screen._resize_trade_columns_to_viewport()
    total_column_width = sum(screen.table.columnWidth(column) for column in range(screen.table.columnCount()))
    assert total_column_width == screen.table.viewport().width()
    assert screen.table.columnWidth(11) < screen.table.columnWidth(0)
    assert screen.table.columnWidth(11) < screen.table.columnWidth(4)
    assert screen.summary_row.count() >= 6
    summary_values = [
        labels[1].text()
        for index in range(screen.summary_row.count())
        if (widget := screen.summary_row.itemAt(index).widget())
        if (labels := widget.findChildren(QLabel))
    ]
    assert "1,234.50R" in summary_values
    assert screen.balance_input.text() == "10,000.00"
    assert screen.start_date.displayFormat() == "dd/MM/yyyy"
    assert screen.end_date.displayFormat() == "dd/MM/yyyy"
    assert screen.balance_input.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons
    screen.max_holding_input.setValue(2000)
    assert screen.max_holding_input.text() == "2,000"
    screen.deleteLater()
    app.processEvents()


def test_backtest_input_help_dialog_explains_all_fields() -> None:
    app = QApplication.instance() or QApplication([])
    screen = BacktestScreen()
    dialog = BacktestInputHelpDialog(screen)

    assert screen.help_button.text() == "Giải thích"
    assert dialog.windowTitle() == "Giải thích tham số backtest"
    assert dialog.objectName() == "ScannerHelpDialog"
    assert dialog.table.rowCount() == 9
    labels = [dialog.table.item(row, 0).text() for row in range(dialog.table.rowCount())]
    assert labels == [
        "Mã",
        "Từ ngày",
        "Đến ngày",
        "Số dư",
        "Rủi ro",
        "Chế độ",
        "Số nến",
        "Spread",
        "Slippage",
    ]
    assert "người mới" in dialog.table.horizontalHeaderItem(2).text().lower()
    button_box = dialog.findChild(QDialogButtonBox)
    assert button_box is not None
    close_btn = button_box.button(QDialogButtonBox.StandardButton.Close)
    assert close_btn is not None
    assert close_btn.text() == "Đóng"
    assert close_btn.objectName() == "PrimaryButton"

    dialog.deleteLater()
    screen.deleteLater()
    app.processEvents()
