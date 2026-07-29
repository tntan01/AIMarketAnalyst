from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from config.settings import default_settings
from controllers.backtest_controller import BacktestController
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
    BACKTEST_RUN_POLICY_VERSION,
    resolve_backtest_run_policy,
)
from core.backtest_execution_parity import (
    EXECUTION_MODE_PARITY,
    EXECUTION_MODE_RESEARCH,
)


def test_validation_policy_forces_parity_and_all_evidence() -> None:
    policy = resolve_backtest_run_policy(
        BACKTEST_PURPOSE_VALIDATION,
        EXECUTION_MODE_RESEARCH,
        research_validation_enabled=False,
    )

    assert policy.version == BACKTEST_RUN_POLICY_VERSION
    assert policy.execution_mode == EXECUTION_MODE_PARITY
    assert policy.run_validation_replay is True
    assert policy.run_walk_forward is True
    assert policy.research_fast is False
    assert policy.release_candidate is True


def test_controller_request_factory_cannot_build_fast_validation() -> None:
    settings_service = MagicMock()
    settings_service.load.return_value = default_settings()
    mt5 = MagicMock()
    mt5.available_symbols.return_value = ["EURUSD"]
    mt5.resolve_symbol.return_value = "EURUSD"
    mt5.symbol_data_quality.return_value = {
        "spread_price": 0.0001,
        "contract_size": 100_000,
    }
    controller = BacktestController(settings_service, mt5)

    request = controller.build_request(
        symbol="EUR/USD",
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 7, 1, tzinfo=timezone.utc),
        initial_balance=10_000,
        risk_percent=1.0,
        purpose=BACKTEST_PURPOSE_VALIDATION,
        execution_mode=EXECUTION_MODE_RESEARCH,
    )

    assert request.purpose == BACKTEST_PURPOSE_VALIDATION
    assert request.execution_mode == EXECUTION_MODE_PARITY


@pytest.mark.parametrize(
    ("mode", "extra_evidence", "expected_evidence", "research_fast"),
    [
        (EXECUTION_MODE_PARITY, False, False, False),
        (EXECUTION_MODE_PARITY, True, True, False),
        (EXECUTION_MODE_RESEARCH, False, False, True),
        (EXECUTION_MODE_RESEARCH, True, False, True),
    ],
)
def test_research_policy_keeps_advanced_options_research_only(
    mode: str,
    extra_evidence: bool,
    expected_evidence: bool,
    research_fast: bool,
) -> None:
    policy = resolve_backtest_run_policy(
        BACKTEST_PURPOSE_RESEARCH,
        mode,
        research_validation_enabled=extra_evidence,
    )

    assert policy.execution_mode == mode
    assert policy.run_validation_replay is expected_evidence
    assert policy.run_walk_forward is expected_evidence
    assert policy.research_fast is research_fast
    assert policy.release_candidate is False


@pytest.mark.parametrize(
    ("purpose", "mode"),
    [
        ("", EXECUTION_MODE_PARITY),
        ("LIVE", EXECUTION_MODE_PARITY),
        (BACKTEST_PURPOSE_RESEARCH, "UNKNOWN"),
    ],
)
def test_run_policy_rejects_unknown_modes(purpose: str, mode: str) -> None:
    with pytest.raises(ValueError):
        resolve_backtest_run_policy(purpose, mode)


def test_research_fast_is_only_selected_from_advanced_ui() -> None:
    from PyQt6.QtWidgets import QApplication
    from ui.screens.backtest_screen import BacktestScreen

    app_instance = QApplication.instance() or QApplication([])
    app = MagicMock()
    screen = BacktestScreen(app=app)
    app.backtest_controller.create_backtest_worker_from_inputs.return_value = (
        MagicMock(),
        MagicMock(),
    )

    fast_index = screen.advanced_execution_combo.findData(
        EXECUTION_MODE_RESEARCH
    )
    screen.advanced_execution_combo.setCurrentIndex(fast_index)
    screen._run_backtest()

    assert app_instance is QApplication.instance()
    assert not hasattr(screen, "execution_combo")
    worker_call = app.backtest_controller.create_backtest_worker_from_inputs.call_args
    assert worker_call.kwargs["build_args"]["purpose"] == BACKTEST_PURPOSE_RESEARCH
    assert worker_call.kwargs["build_args"]["execution_mode"] == EXECUTION_MODE_RESEARCH
    assert worker_call.kwargs["research_validation_enabled"] is False
    assert screen.research_validation_checkbox.isEnabled() is False
    assert "Chỉ nghiên cứu" in screen.mode_summary_label.text()
    screen.close()


def test_switching_to_validation_resets_advanced_research_options() -> None:
    from PyQt6.QtWidgets import QApplication
    from ui.screens.backtest_screen import BacktestScreen

    app_instance = QApplication.instance() or QApplication([])
    screen = BacktestScreen(app=MagicMock())
    screen.advanced_execution_combo.setCurrentIndex(
        screen.advanced_execution_combo.findData(EXECUTION_MODE_RESEARCH)
    )
    screen.research_validation_checkbox.setChecked(True)

    screen.purpose_combo.setCurrentIndex(
        screen.purpose_combo.findData(BACKTEST_PURPOSE_VALIDATION)
    )

    assert app_instance is QApplication.instance()
    assert screen.advanced_execution_combo.currentData() == EXECUTION_MODE_PARITY
    assert screen.advanced_execution_combo.isEnabled() is False
    assert screen.research_validation_checkbox.isChecked() is False
    assert screen.research_validation_checkbox.isEnabled() is False
    assert "IS/OOS + Walk-Forward" in screen.mode_summary_label.text()
    screen.close()
