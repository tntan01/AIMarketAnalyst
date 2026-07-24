from __future__ import annotations

from PyQt6.QtWidgets import QApplication

from ui.screens import scanner_screen
from ui.screens.scanner_screen import (
    ScannerColumnsHelpDialog,
    ScannerRowExplanationDialog,
    ScannerTableModel,
)


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_columns_help_matches_current_scanner_table_contract() -> None:
    app = _application()
    dialog = ScannerColumnsHelpDialog()

    expected_labels = [label for _key, label in ScannerTableModel.COLUMNS]
    help_labels = [item["column"] for item in dialog.COLUMN_HELP]

    assert help_labels == expected_labels
    assert dialog.help_table.rowCount() == len(expected_labels) == 13
    assert dialog.help_table.columnCount() == 3
    assert dialog.help_table.objectName() == "EconTable"
    assert dialog.help_table.showGrid() is False
    assert dialog.help_table.cellWidget(0, 0) is None
    assert app is QApplication.instance()

    dialog.close()


def test_help_button_opens_columns_dialog_without_selection(monkeypatch) -> None:
    opened: list[object] = []

    class _Dialog:
        def __init__(self, parent: object) -> None:
            opened.append(parent)

        def exec(self) -> None:
            opened.append("exec")

    monkeypatch.setattr(scanner_screen, "ScannerColumnsHelpDialog", _Dialog)
    owner = object()

    scanner_screen.ScannerScreen._show_columns_help(owner)

    assert opened == [owner, "exec"]


def test_help_button_opens_selected_row_explanation(monkeypatch) -> None:
    opened: list[object] = []
    row = {
        "symbol": "EUR/USD",
        "candidate_status": "OUT_OF_STRATEGY",
        "selected_side": "sell",
    }

    class _Index:
        def isValid(self) -> bool:
            return True

        def row(self) -> int:
            return 0

    class _Selection:
        def selectedRows(self) -> list[_Index]:
            return [_Index()]

    class _Table:
        def selectionModel(self) -> _Selection:
            return _Selection()

    class _Model:
        def row_at(self, index: int) -> dict[str, object] | None:
            return row if index == 0 else None

    class _Dialog:
        def __init__(
            self,
            selected_row: dict[str, object],
            table_model: object,
            parent: object,
        ) -> None:
            opened.extend([selected_row, table_model, parent])

        def exec(self) -> None:
            opened.append("exec")

    owner = type(
        "Owner",
        (),
        {"table": _Table(), "table_model": _Model()},
    )()
    monkeypatch.setattr(
        scanner_screen,
        "ScannerRowExplanationDialog",
        _Dialog,
    )

    scanner_screen.ScannerScreen._show_columns_help(owner)

    assert opened == [row, owner.table_model, owner, "exec"]


def test_selected_row_dialog_explains_actual_status_and_direction() -> None:
    app = _application()
    model = ScannerTableModel()
    row = {
        "rank": 4,
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSDm",
        "candidate_status": "OUT_OF_STRATEGY",
        "selected_side": "sell",
        "market_regime": "trend_down",
        "setup_score": 58,
        "opportunity_rank": 42,
        "evidence_confidence": 20,
        "execution_readiness": 0,
        "expected_effective_rr": 1.1,
        "auto_trade_branch": "BACKTEST_VALIDATED",
        "strategy_config_status": "VALIDATED",
        "detail_action": "View Detail",
        "min_score": 65,
        "min_rr": 1.3,
        "short_reason": "Setup thấp hơn ngưỡng chiến lược.",
        "analysis_result": {},
    }
    dialog = ScannerRowExplanationDialog(row, model)
    items = {item["param"]: item for item in dialog.row_items}
    visible_items = [
        item for item in dialog.row_items if not item["technical"]
    ]
    technical_indexes = [
        index
        for index, item in enumerate(dialog.row_items)
        if item["technical"]
    ]

    assert dialog.table.objectName() == "EconTable"
    assert len(visible_items) == 11
    assert dialog.table.rowCount() == 18
    assert items["Trạng thái"]["value"] == "Ngoài chiến lược"
    assert "không khớp quy tắc giao dịch" in items["Trạng thái"]["explanation"]
    assert "Setup thấp hơn ngưỡng" in items["Trạng thái"]["explanation"]
    assert items["Hướng đang đánh giá"]["value"] == "Bán"
    assert "kịch bản bán" in items["Hướng đang đánh giá"]["explanation"]
    assert (
        "chưa đạt mức yêu cầu 65"
        in items["Chất lượng thiết lập"]["explanation"]
    )
    assert items["Nên làm gì"]["value"] == "Bỏ qua trong lần quét hiện tại"
    assert all(dialog.table.isRowHidden(index) for index in technical_indexes)

    dialog.technical_check.setChecked(True)
    assert all(
        not dialog.table.isRowHidden(index)
        for index in technical_indexes
    )
    assert app is QApplication.instance()

    dialog.close()
