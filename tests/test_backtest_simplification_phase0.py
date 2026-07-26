"""Characterization baseline for the Backtest simplification project.

These tests intentionally describe the pre-simplification behavior. Later
phases may update an assertion only when the corresponding contract change is
implemented and documented.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import controllers.backtest_controller as controller_module
from controllers.backtest_controller import BacktestController
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BACKTEST_PURPOSE_VALIDATION,
)
from core.backtest_execution_parity import EXECUTION_MODE_PARITY
from core.backtest_market_data import _unexpected_gaps
from core.market_models import Candle
from core.system_backtest_engine import BacktestRequest, BacktestResult


BASELINE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "backtest_simplification_phase0_baseline.json"
)


def _baseline() -> dict:
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def _request(purpose: str, symbol: str = "EUR/USD") -> BacktestRequest:
    return BacktestRequest(
        symbol=symbol,
        broker_symbol=symbol.replace("/", ""),
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 2, 1, tzinfo=timezone.utc),
        initial_balance=10_000,
        risk_percent=1.0,
        purpose=purpose,
        execution_mode=EXECUTION_MODE_PARITY,
    )


def _engine_result(request: BacktestRequest) -> BacktestResult:
    return BacktestResult(
        request=request,
        summary={"total_trades": 0},
        trades=[],
        equity_curve=[],
        breakdowns={},
        skipped_setups=[],
        diagnostics={},
    )


def _controller(monkeypatch: pytest.MonkeyPatch) -> BacktestController:
    controller = object.__new__(BacktestController)
    controller.mt5 = SimpleNamespace(
        connection_status=lambda: SimpleNamespace(
            connected=True,
            logged_in=True,
            provider_name="phase0-fixture",
        )
    )
    controller._history_cache = {}
    monkeypatch.setattr(controller, "_load_history", lambda _request: {})
    monkeypatch.setattr(
        controller,
        "_attach_quote_conversion_history",
        lambda request: request,
    )
    monkeypatch.setattr(controller, "save_snapshot", lambda _payload: Path("baseline.json"))
    monkeypatch.setattr(
        controller_module,
        "run_system_backtest",
        lambda request, _candles, progress_callback=None: _engine_result(request),
    )
    monkeypatch.setattr(
        "core.monte_carlo.run_monte_carlo",
        lambda _trades, num_simulations=2000: {
            "baseline": True,
            "simulation_count": num_simulations,
        },
    )
    monkeypatch.setattr(
        "core.backtest_validation_replay.run_frozen_validation_replay",
        lambda request, _candles, progress_callback=None: {
            "status": "COMPLETE",
            "purpose": request.purpose,
        },
    )
    monkeypatch.setattr(
        "core.walk_forward_engine.run_walk_forward",
        lambda request, _candles, progress_callback=None: {
            "verdict": "BASELINE",
            "purpose": request.purpose,
        },
    )
    return controller


@pytest.mark.parametrize(
    (
        "purpose",
        "research_validation_enabled",
        "evidence_present",
        "lifecycle",
    ),
    [
        (BACKTEST_PURPOSE_RESEARCH, False, False, "RESEARCH_ONLY"),
        (BACKTEST_PURPOSE_RESEARCH, True, True, "RESEARCH_ONLY"),
        (BACKTEST_PURPOSE_VALIDATION, False, True, "DRAFT"),
        (BACKTEST_PURPOSE_VALIDATION, True, True, "DRAFT"),
    ],
)
def test_phase2_single_symbol_mode_matrix_is_orchestrated_by_purpose(
    monkeypatch: pytest.MonkeyPatch,
    purpose: str,
    research_validation_enabled: bool,
    evidence_present: bool,
    lifecycle: str,
) -> None:
    controller = _controller(monkeypatch)

    payload = controller._run_single_backtest(
        _request(purpose),
        research_validation_enabled=research_validation_enabled,
        progress=lambda _percent, _message: None,
        save_snapshot=True,
    )

    assert payload["lifecycle"]["status"] == lifecycle
    assert ("validation_replay" in payload) is evidence_present
    assert ("walk_forward" in payload) is evidence_present
    assert payload["run_policy"]["release_candidate"] is (
        purpose == BACKTEST_PURPOSE_VALIDATION
    )
    if purpose == BACKTEST_PURPOSE_VALIDATION:
        assert payload["backtest_contract"]["purpose"] == (
            BACKTEST_PURPOSE_RESEARCH
        )
        assert payload["validation_replay"]["purpose"] == (
            BACKTEST_PURPOSE_VALIDATION
        )
    assert payload["lifecycle"].get("can_publish_config", False) is False
    assert payload["snapshot_path"] == "baseline.json"


def test_portfolio_is_always_research_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    controller = _controller(monkeypatch)
    contract = _baseline()["portfolio_contract"]

    payload = controller._run_batch_backtest(
        [
            _request(BACKTEST_PURPOSE_VALIDATION, "EUR/USD"),
            _request(BACKTEST_PURPOSE_VALIDATION, "GBP/USD"),
        ],
        research_validation_enabled=False,
        progress=lambda _percent, _message: None,
    )

    assert payload["mode"] == contract["mode"]
    assert payload["lifecycle"]["status"] == contract["lifecycle"]
    assert all("validation_replay" in item for item in payload["symbols"])
    assert all("walk_forward" in item for item in payload["symbols"])
    assert contract["publishable_as_symbol_config"] is False


def test_phase2_ui_removes_duplicate_evidence_controls() -> None:
    from PyQt6.QtWidgets import QApplication
    from ui.screens.backtest_screen import BacktestScreen

    app_instance = QApplication.instance() or QApplication([])
    app = MagicMock()
    screen = BacktestScreen(app=app)
    app.backtest_controller.build_requests.return_value = [MagicMock()]
    app.backtest_controller.create_backtest_worker.return_value = (
        MagicMock(),
        MagicMock(),
    )
    validation_index = screen.purpose_combo.findData(
        BACKTEST_PURPOSE_VALIDATION
    )
    screen.purpose_combo.setCurrentIndex(validation_index)

    screen._run_backtest()

    assert app_instance is QApplication.instance()
    assert not hasattr(screen, "walk_forward_checkbox")
    assert not hasattr(screen, "is_oos_checkbox")
    request_call = app.backtest_controller.build_requests.call_args
    assert request_call.kwargs["purpose"] == BACKTEST_PURPOSE_VALIDATION
    assert request_call.kwargs["execution_mode"] == EXECUTION_MODE_PARITY
    worker_call = app.backtest_controller.create_backtest_worker.call_args
    assert worker_call.kwargs["research_validation_enabled"] is False
    assert screen.advanced_execution_combo.isEnabled() is False
    screen.close()


def test_phase1_resolves_recorded_weekend_gap_false_positive() -> None:
    baseline = _baseline()["known_issue_baseline"]
    friday_close = Candle(
        time=datetime(2026, 1, 9, 21, tzinfo=timezone.utc),
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
    )
    sunday_open = Candle(
        time=datetime(2026, 1, 11, 22, tzinfo=timezone.utc),
        open=1.0,
        high=1.0,
        low=1.0,
        close=1.0,
    )

    gaps = _unexpected_gaps(
        [friday_close, sunday_open],
        duration=timedelta(hours=1),
    )

    assert baseline["friday_21_to_sunday_22_h1_missing_intervals_reported"] == 2
    assert baseline["classification"] == "KNOWN_FALSE_POSITIVE_TO_FIX_IN_PHASE_1"
    assert gaps == []


def test_phase0_baseline_declares_no_runtime_change() -> None:
    baseline = _baseline()

    assert baseline["baseline_version"] == "backtest-simplification-phase0-v1"
    assert baseline["runtime_changed"] is False
    assert baseline["migration_inventory"]["deprecated_feature_flags"] == [
        "backtest_config_v2",
        "backtest_engine_v2",
    ]
    assert baseline["migration_inventory"]["legacy_snapshot_publishable"] is False
