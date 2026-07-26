from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import core.param_sensitivity as sensitivity
import core.risk_engine as risk_engine
import controllers.backtest_controller as controller_module
from controllers.backtest_controller import BacktestController
from core.backtest_config import reconcile_enabled_symbol
from core.backtest_portfolio_engine import PortfolioReplayLimits, replay_portfolio
from core.param_sensitivity import MarketPeriod, ParamSweepConfig
from core.risk_parameter_context import (
    RiskParameterOverrides,
    risk_parameter,
    risk_parameter_scope,
)
from core.system_backtest_engine import BacktestRequest, BacktestResult, BacktestTrade
from workers.backtest_worker import BacktestCancelled, BacktestWorker


def _trade(
    symbol: str,
    entry: str,
    exit_: str,
    *,
    side: str = "buy",
    risk: float = 100.0,
    pnl: float = 100.0,
) -> BacktestTrade:
    return BacktestTrade(
        symbol=symbol, side=side, decision="ready", entry_time=entry,
        exit_time=exit_, entry_price=1.0, stop_loss=0.99,
        take_profit=1.02, exit_price=1.02, result="win",
        result_r=1.0, holding_bars=1, final_score=80, signal_score=80,
        buy_score=80, sell_score=20, score_gap=60.0,
        market_regime="trend_up", entry_status="ready",
        m15_quality="confirmed", expected_effective_rr=2.0,
        selected_zone_score=80, selected_zone_type="order_block",
        entry_zone_score=80, entry_zone_source="smc",
        liquidity_sweep_aligned=True, displacement_aligned=True,
        choch_against_direction=False, planned_risk_account=risk,
        target_risk_account=risk, net_pnl_account=pnl,
    )


def _result(symbol: str, trades: list[BacktestTrade]) -> BacktestResult:
    request = BacktestRequest(
        symbol=symbol, broker_symbol=symbol.replace("/", ""),
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 2, 1, tzinfo=timezone.utc),
        initial_balance=10_000, risk_percent=1.0,
    )
    return BacktestResult(
        request=request, summary={"total_trades": len(trades)}, trades=trades,
        equity_curve=[], breakdowns={}, skipped_setups=[], diagnostics={},
    )


def test_portfolio_clock_accepts_non_overlapping_trades() -> None:
    first = _trade("EUR/USD", "2025-01-01T00:00:00+00:00", "2025-01-02T00:00:00+00:00")
    second = _trade("GBP/USD", "2025-01-02T00:00:00+00:00", "2025-01-03T00:00:00+00:00")
    payload = replay_portfolio(
        [_result("EUR/USD", [first]), _result("GBP/USD", [second])],
        initial_balance=10_000,
        limits=PortfolioReplayLimits(),
    )
    assert payload["accepted_trades"] == 2
    assert payload["rejected_trades"] == 0
    assert payload["final_balance"] == 10_200
    assert payload["equity_curve"][1]["event"] == "EXIT"


def test_portfolio_rejects_concurrent_open_risk_and_reports_symbol() -> None:
    first = _trade("EUR/USD", "2025-01-01T00:00:00+00:00", "2025-01-03T00:00:00+00:00", risk=200)
    second = _trade("GBP/JPY", "2025-01-02T00:00:00+00:00", "2025-01-04T00:00:00+00:00", risk=200)
    payload = replay_portfolio(
        [_result("EUR/USD", [first]), _result("GBP/JPY", [second])],
        initial_balance=10_000,
        limits=PortfolioReplayLimits(
            max_open_risk_pct=3.0,
            max_symbol_risk_pct=3.0,
            max_currency_exposure_pct=5.0,
            max_correlated_risk_pct=5.0,
            max_concurrent_positions=5,
        ),
    )
    assert payload["accepted_trades"] == 1
    assert payload["rejections"][0]["block_codes"] == ["PORTFOLIO_RISK_EXCEEDED"]
    assert payload["per_symbol"]["GBP/JPY"]["rejected_trades"] == 1


def test_risk_override_is_execution_local_and_restored() -> None:
    original = risk_engine._MIN_SL_DISTANCE_ATR
    overrides = RiskParameterOverrides.from_mapping({"min_sl_distance_atr": 0.91})
    with risk_parameter_scope(overrides):
        assert risk_parameter("min_sl_distance_atr", original) == 0.91
        assert risk_engine._MIN_SL_DISTANCE_ATR == original
    assert risk_parameter("min_sl_distance_atr", original) == original


def test_sweep_passes_immutable_override_without_monkeypatch(monkeypatch) -> None:
    captured: list[dict[str, float]] = []

    def fake_run(**kwargs):
        captured.append(kwargs["parameter_overrides"])
        return {"total_trades": 2, "win_rate": 50, "expectancy_r": 0.2,
                "profit_factor": 1.2, "max_drawdown_r": 1.0}

    monkeypatch.setattr(sensitivity, "_run_single_backtest", fake_run)
    original = risk_engine._MIN_SL_DISTANCE_ATR
    sensitivity.sweep_single_param(
        ParamSweepConfig("min_sl_distance_atr", "_MIN_SL_DISTANCE_ATR", [0.3, 0.7]),
        [MarketPeriod("sample", "2025-01-01", "2025-02-01", "mixed")],
        ["EUR/USD"],
    )
    assert captured == [
        {"min_sl_distance_atr": 0.3},
        {"min_sl_distance_atr": 0.7},
    ]
    assert risk_engine._MIN_SL_DISTANCE_ATR == original


def test_controller_build_requests_keeps_all_unique_symbols(monkeypatch) -> None:
    controller = object.__new__(BacktestController)
    monkeypatch.setattr(
        controller,
        "build_request",
        lambda **kwargs: kwargs["symbol"],
    )
    requests = controller.build_requests(
        symbols=["EUR/USD", "GBP/USD", "EUR/USD"],
        start=None, end=None, initial_balance=10_000, risk_percent=1.0,
    )
    assert requests == ["EUR/USD", "GBP/USD"]


def test_backtest_cancel_stops_before_snapshot_boundary() -> None:
    worker = BacktestWorker(lambda **_kwargs: {}, {})
    worker.cancel()
    try:
        worker._emit_progress(20, "running")
    except BacktestCancelled as exc:
        assert "chưa tạo snapshot" in str(exc)
    else:
        raise AssertionError("cancel must interrupt at the next progress boundary")


def test_controller_batch_returns_symbol_and_portfolio_aggregates(monkeypatch) -> None:
    controller = object.__new__(BacktestController)
    controller.mt5 = SimpleNamespace(
        connection_status=lambda: SimpleNamespace(
            connected=True, logged_in=True, provider_name="fixture"
        )
    )
    monkeypatch.setattr(controller, "_load_history", lambda _request: {})
    monkeypatch.setattr(controller, "_attach_quote_conversion_history", lambda request: request)
    monkeypatch.setattr(controller, "save_snapshot", lambda _payload: "batch.json")
    monkeypatch.setattr(
        controller_module,
        "run_system_backtest",
        lambda request, _candles, progress_callback=None: _result(
            request.symbol,
            [_trade(
                request.symbol,
                "2025-01-01T00:00:00+00:00",
                "2025-01-02T00:00:00+00:00",
            )],
        ),
    )
    requests = [
        BacktestRequest(
            symbol=symbol, broker_symbol=symbol.replace("/", ""),
            start=datetime(2025, 1, 1, tzinfo=timezone.utc),
            end=datetime(2025, 2, 1, tzinfo=timezone.utc),
            initial_balance=10_000, risk_percent=1.0,
        )
        for symbol in ("EUR/USD", "GBP/JPY")
    ]
    payload = controller._run_batch_backtest(
        requests, research_validation_enabled=False,
        progress=lambda _percent, _message: None,
    )
    assert payload["mode"] == "portfolio_backtest"
    assert len(payload["symbols"]) == 2
    assert set(payload["portfolio"]["per_symbol"]) == {"EUR/USD", "GBP/JPY"}
    assert payload["snapshot_path"] == "batch.json"


def test_saving_draft_preserves_scanner_membership() -> None:
    assert reconcile_enabled_symbol(
        ["EUR/USD"],
        symbol="EUR/USD",
        backtest_active=False,
        lifecycle_status="DRAFT",
        confirmed_disable=True,
    ) == ["EUR/USD"]
    assert reconcile_enabled_symbol(
        ["EUR/USD"],
        symbol="EUR/USD",
        backtest_active=False,
        lifecycle_status="VALIDATED",
        confirmed_disable=True,
    ) == []
