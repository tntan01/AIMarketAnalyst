from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

from core.backtest_advanced import (
    BACKTEST_ADVANCED_RESEARCH_VERSION,
    MONTE_CARLO_AUTO_MIN_TRADES,
    run_monte_carlo_if_eligible,
)
from core.param_sensitivity import (
    MarketPeriod,
    ParamSweepConfig,
    SweepResult,
    SweepRunResult,
    sweep_single_param,
)
from core.system_backtest_engine import BacktestRequest
from workers.param_sweep_worker import _result_from_dict


def _request(symbol: str = "EUR/USD") -> BacktestRequest:
    return BacktestRequest(
        symbol=symbol,
        broker_symbol=symbol.replace("/", ""),
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 2, 1, tzinfo=timezone.utc),
        initial_balance=12_345,
        risk_percent=0.7,
        spread_price=0.0002,
        entry_slippage_price=0.0001,
        exit_slippage_price=0.0003,
        commission_per_lot_round_turn=7.0,
        swap_long_per_lot_day=-1.2,
        maximum_lot=25.0,
        code_revision="1234567",
    )


def test_monte_carlo_skips_small_sample_unless_requested(monkeypatch) -> None:
    calls: list[int] = []
    monkeypatch.setattr(
        "core.monte_carlo.run_monte_carlo",
        lambda _trades, num_simulations: calls.append(num_simulations) or {
            "simulation_count": num_simulations,
        },
    )
    trades = [MagicMock() for _ in range(MONTE_CARLO_AUTO_MIN_TRADES - 1)]

    skipped = run_monte_carlo_if_eligible(trades)
    completed = run_monte_carlo_if_eligible(trades, requested=True)

    assert skipped["status"] == "SKIPPED"
    assert skipped["reason"] == "TRADE_SAMPLE_TOO_SMALL"
    assert completed["status"] == "COMPLETE"
    assert completed["trigger"] == "USER_REQUEST"
    assert completed["lifecycle"] == "RESEARCH_ONLY"
    assert calls == [2000]


def test_sweep_reuses_full_controller_request_context(monkeypatch) -> None:
    import core.param_sensitivity as sensitivity

    captured: list[BacktestRequest] = []

    class Result:
        trades = [SimpleNamespace(result_r=0.5)]

        def to_dict(self):
            return {
                "data_manifest": {"dataset_hash": "d" * 64},
                "backtest_provenance": {
                    "request_fingerprint": "r" * 64,
                    "provenance_fingerprint": "p" * 64,
                },
            }

    monkeypatch.setattr(sensitivity, "_load_candles", lambda request, _provider: captured.append(request) or {})
    monkeypatch.setattr(
        "core.system_backtest_engine.run_system_backtest",
        lambda _request, _candles, **_: Result(),
    )
    monkeypatch.setattr(
        "core.system_backtest_engine.summarize_backtest_trades",
        lambda _trades: {
            "total_trades": 1,
            "win_rate": 100.0,
            "expectancy_r": 0.5,
            "profit_factor": 2.0,
            "max_drawdown_r": 0.0,
        },
    )
    template = _request()
    result = sweep_single_param(
        ParamSweepConfig(
            "min_sl_distance_atr",
            "_MIN_SL_DISTANCE_ATR",
            [0.7],
        ),
        [MarketPeriod("Selected", "2026-03-01", "2026-04-01", "user_selected")],
        ["EUR/USD"],
        request_templates={"EUR/USD": template},
        data_provider=MagicMock(),
    )

    request = captured[0]
    assert request.spread_price == template.spread_price
    assert request.commission_per_lot_round_turn == 7.0
    assert request.maximum_lot == 25.0
    assert request.start.year == 2026 and request.start.month == 3
    assert request.purpose == "RESEARCH"
    assert request.risk_parameter_overrides.as_mapping()["min_sl_distance_atr"] == 0.7
    assert result.lifecycle == "RESEARCH_ONLY"
    assert result.can_apply_config is False
    assert result.runs[0].dataset_hash == "d" * 64


def test_sweep_checkpoint_contract_keeps_lifecycle_and_trace() -> None:
    source = SweepResult(
        json_key="x",
        attr_name="_X",
        runs=[SweepRunResult(
            param_value=1.0,
            period="Selected",
            symbol="EUR/USD",
            dataset_hash="d" * 64,
            request_fingerprint="r" * 64,
            provenance_fingerprint="p" * 64,
            execution_mode="PARITY",
        )],
        request_context={"symbols": ["EUR/USD"]},
    )

    restored = _result_from_dict(asdict(source))

    assert restored.lifecycle == "RESEARCH_ONLY"
    assert restored.can_apply_config is False
    assert restored.request_context == {"symbols": ["EUR/USD"]}
    assert restored.runs[0].provenance_fingerprint == "p" * 64


def test_advanced_portfolio_is_explicit_and_validation_disables_it() -> None:
    from PyQt6.QtWidgets import QApplication
    from ui.screens.backtest_screen import BacktestScreen
    from core.backtest_contract import BACKTEST_PURPOSE_VALIDATION

    app_instance = QApplication.instance() or QApplication([])
    app = MagicMock()
    screen = BacktestScreen(app=app)
    screen._set_selected_symbols(["EUR/USD", "GBP/USD"])
    app.backtest_controller.build_requests.return_value = [MagicMock()]
    app.backtest_controller.create_backtest_worker.return_value = (
        MagicMock(), MagicMock(),
    )

    screen._run_backtest()
    assert app.backtest_controller.build_requests.call_args.kwargs["symbols"] == [
        "EUR/USD"
    ]

    screen.portfolio_mode_checkbox.setChecked(True)
    screen._run_backtest()
    assert app.backtest_controller.build_requests.call_args.kwargs["symbols"] == [
        "EUR/USD", "GBP/USD"
    ]

    screen.purpose_combo.setCurrentIndex(
        screen.purpose_combo.findData(BACKTEST_PURPOSE_VALIDATION)
    )
    assert screen.portfolio_mode_checkbox.isChecked() is False
    assert screen.portfolio_mode_checkbox.isEnabled() is False
    assert screen.tabs.cornerWidget().isAncestorOf(screen.analyze_btn) is False
    assert screen._sweep_tab.isAncestorOf(screen.analyze_btn) is True
    assert app_instance is QApplication.instance()
    screen.close()


def test_advanced_manifest_is_versioned_and_never_publishable() -> None:
    from core.backtest_advanced import advanced_research_manifest

    manifest = advanced_research_manifest("portfolio")
    assert manifest["version"] == BACKTEST_ADVANCED_RESEARCH_VERSION
    assert manifest["lifecycle"] == "RESEARCH_ONLY"
    assert manifest["can_publish_config"] is False
    assert manifest["can_apply_symbol_config"] is False
