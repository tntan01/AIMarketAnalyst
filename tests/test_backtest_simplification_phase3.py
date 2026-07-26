from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core.backtest_presentation import (
    ACTION_APPLY_VALIDATED,
    ACTION_NONE,
    ACTION_SAVE_DRAFT,
    lifecycle_reason_label,
    lifecycle_status_label,
    result_action,
    snapshot_symbols,
)


def _result(
    status: str,
    *,
    symbol: str = "EUR/USD",
    can_publish: bool = False,
) -> dict:
    return {
        "mode": "system_backtest",
        "request": {"symbol": symbol},
        "lifecycle": {
            "status": status,
            "can_publish_config": can_publish,
            "reasons": [],
        },
    }


@pytest.mark.parametrize(
    ("status", "can_publish", "kind", "visible"),
    [
        ("RESEARCH_ONLY", False, ACTION_NONE, False),
        ("LEGACY_RESEARCH", False, ACTION_NONE, False),
        ("REVIEW_REQUIRED", False, ACTION_NONE, False),
        ("DRAFT", False, ACTION_SAVE_DRAFT, True),
        ("VALIDATED", False, ACTION_APPLY_VALIDATED, True),
        ("RELEASE_READY", True, ACTION_APPLY_VALIDATED, True),
    ],
)
def test_action_is_derived_from_lifecycle(
    status: str,
    can_publish: bool,
    kind: str,
    visible: bool,
) -> None:
    action = result_action(
        _result(status, can_publish=can_publish),
        selected_symbol="EUR/USD",
    )

    assert action.kind == kind
    assert action.visible is visible


def test_action_fails_closed_for_wrong_symbol_and_portfolio() -> None:
    mismatch = result_action(
        _result("VALIDATED", symbol="GBP/USD"),
        selected_symbol="EUR/USD",
    )
    portfolio = result_action(
        {
            "mode": "portfolio_backtest",
            "request": {"symbols": ["EUR/USD", "GBP/USD"]},
            "lifecycle": {"status": "VALIDATED", "can_publish_config": True},
        },
        selected_symbol="EUR/USD",
    )

    assert mismatch.kind == ACTION_NONE
    assert mismatch.reason == "SNAPSHOT_SYMBOL_MISMATCH"
    assert portfolio.kind == ACTION_NONE


def test_snapshot_symbol_resolution_supports_validation_and_legacy_trades() -> None:
    validation = {
        "validation_replay": {"request": {"symbol": "XAU/USD"}},
    }
    legacy = {
        "trades": [
            {"symbol": "USD/JPY"},
            {"symbol": "USD/JPY"},
        ],
    }

    assert snapshot_symbols(validation) == ("XAU/USD",)
    assert snapshot_symbols(legacy) == ("USD/JPY",)


def test_lifecycle_status_and_reasons_are_explained_in_vietnamese() -> None:
    assert lifecycle_status_label("DRAFT") == "Bản nháp cần kiểm tra thêm"
    assert "ngoài mẫu" in lifecycle_reason_label("OOS_SAMPLE_TOO_SMALL")
    assert "chưa đủ bằng chứng" in lifecycle_reason_label(
        "PURPOSE_OR_EVIDENCE_NOT_RELEASE_ELIGIBLE"
    ).lower()


def test_quick_summary_contains_exactly_five_decision_metrics() -> None:
    from PyQt6.QtWidgets import QApplication, QLabel
    from ui.screens.backtest_screen import BacktestScreen

    app_instance = QApplication.instance() or QApplication([])
    screen = BacktestScreen(app=MagicMock())
    summary = {
        "total_trades": 25,
        "win_rate": 52.0,
        "expectancy_r": 0.25,
        "profit_factor": 1.4,
        "max_drawdown_r": 4.5,
        "gross_r": 10.0,
        "cost_r": 2.0,
        "net_r": 8.0,
        "average_win_r": 1.5,
        "average_loss_r": -1.0,
        "max_consecutive_losses": 3,
    }

    screen._set_summary(summary)
    titles: list[str] = []
    for index in range(screen.summary_row.count()):
        widget = screen.summary_row.itemAt(index).widget()
        if widget is None:
            continue
        label = widget.findChild(QLabel, "MiniStatTitleCompact")
        if label is not None:
            titles.append(label.text().rstrip(":"))

    assert app_instance is QApplication.instance()
    assert titles == ["Lệnh", "Kỳ vọng", "Hệ số LN", "DD tối đa", "Net"]
    assert summary["win_rate"] == 52.0
    assert summary["gross_r"] == 10.0
    screen.close()


def test_loading_snapshot_state_synchronizes_symbol_before_action() -> None:
    from PyQt6.QtWidgets import QApplication
    from ui.screens.backtest_screen import BacktestScreen

    app_instance = QApplication.instance() or QApplication([])
    screen = BacktestScreen(app=MagicMock())
    screen.result = _result("DRAFT", symbol="GBP/USD")

    screen._sync_symbols_from_result(screen.result)
    screen._update_result_action()

    assert app_instance is QApplication.instance()
    assert screen.selected_symbol == "GBP/USD"
    assert screen.selected_symbols == ["GBP/USD"]
    assert screen.symbol_summary.text() == "GBP/USD"
    assert screen.apply_config_btn.isHidden() is False
    assert "Lưu đề xuất nháp" in screen.apply_config_btn.text()
    screen.close()


def test_research_result_cannot_open_config_apply_flow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from ui.screens.backtest_screen import BacktestScreen
    import core.backtest_config_validation as validation

    app_instance = QApplication.instance() or QApplication([])
    screen = BacktestScreen(app=MagicMock())
    screen.result = _result("RESEARCH_ONLY")
    screen._sync_symbols_from_result(screen.result)
    build = MagicMock()
    monkeypatch.setattr(validation, "build_backtest_config", build)
    shown = MagicMock()
    monkeypatch.setattr(QMessageBox, "information", shown)

    screen._apply_scanner_config()

    assert app_instance is QApplication.instance()
    build.assert_not_called()
    shown.assert_called_once()
    screen.close()
