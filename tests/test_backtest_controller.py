from __future__ import annotations

from datetime import datetime, timedelta, timezone

from PyQt6.QtCore import QThread

from controllers.backtest_controller import BacktestController
from core.market_models import Candle
from core.system_backtest_engine import BacktestRequest
from workers.backtest_worker import BacktestWorker


class _Status:
    terminal_connected = True
    logged_in = True


class _SettingsService:
    def load(self):
        from config.settings import default_settings

        return default_settings()


class _MT5Service:
    def available_symbols(self, market_watch_only=True):
        return ["EURUSD", "GBPUSD"]

    def resolve_symbol(self, app_symbol, available_symbols):
        return app_symbol.replace("/", "")

    def symbol_data_quality(self, display_symbol, broker_symbol):
        return {
            "contract_size": 100000,
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        }

    def connection_status(self):
        return _Status()

    def load_ohlcv_range(self, broker_symbol, timeframe, start, end):
        step = {
            "D1": timedelta(days=1),
            "H4": timedelta(hours=4),
            "H1": timedelta(hours=1),
            "M15": timedelta(minutes=15),
        }[timeframe]
        rows = []
        current = start
        while current <= end:
            rows.append(Candle(current, 1.10, 1.102, 1.098, 1.10, 100))
            current += step
        return rows


def test_backtest_controller_creates_qthread_worker() -> None:
    controller = BacktestController(settings_service=_SettingsService(), mt5_service=_MT5Service())
    request = BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        end=datetime(2026, 1, 2, tzinfo=timezone.utc),
        initial_balance=10_000,
        risk_percent=1.0,
    )

    thread, worker = controller.create_backtest_worker(request)

    try:
        assert isinstance(thread, QThread)
        assert isinstance(worker, BacktestWorker)
        assert worker.request["request"] == request
        assert worker.thread() is thread
    finally:
        thread.quit()
        thread.wait(1000)


def test_backtest_controller_build_request_resolves_symbol_and_settings() -> None:
    controller = BacktestController(settings_service=_SettingsService(), mt5_service=_MT5Service())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)

    request = controller.build_request(
        symbol="EUR/USD",
        start=start,
        end=end,
        initial_balance=10_000,
        risk_percent=1.0,
        mode="strict",
    )

    assert request.symbol == "EUR/USD"
    assert request.broker_symbol == "EURUSD"
    assert request.start == start
    assert request.end == end
    assert request.mode == "strict"
    assert request.account_guard_enabled is False
    assert request.max_consecutive_losses == 999


def test_backtest_controller_build_requests_supports_multiple_symbols() -> None:
    controller = BacktestController(settings_service=_SettingsService(), mt5_service=_MT5Service())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)

    requests = controller.build_requests(
        symbols=["EUR/USD", "GBP/USD", "EUR/USD"],
        start=start,
        end=end,
        initial_balance=10_000,
        risk_percent=1.0,
        mode="backtest",
    )

    assert [request.symbol for request in requests] == ["EUR/USD", "GBP/USD"]
    assert [request.broker_symbol for request in requests] == ["EURUSD", "GBPUSD"]
    assert all(request.mode == "backtest" for request in requests)


def test_backtest_controller_builds_batch_payload_summary_by_symbol() -> None:
    controller = BacktestController(settings_service=_SettingsService(), mt5_service=_MT5Service())
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = datetime(2026, 1, 2, tzinfo=timezone.utc)
    requests = controller.build_requests(
        symbols=["EUR/USD", "GBP/USD"],
        start=start,
        end=end,
        initial_balance=10_000,
        risk_percent=1.0,
        mode="backtest",
    )
    runs = [
        {
            "request": {"symbol": "EUR/USD"},
            "summary": {"total_trades": 1, "expectancy_r": 2.0},
            "trades": [
                {
                    "symbol": "EUR/USD",
                    "side": "buy",
                    "decision": "WAITING_CONFIRMATION",
                    "entry_time": "2026-01-01T00:00:00+00:00",
                    "exit_time": "2026-01-01T01:00:00+00:00",
                    "entry_price": 1.1,
                    "stop_loss": 1.09,
                    "take_profit": 1.12,
                    "exit_price": 1.12,
                    "result": "win",
                    "result_r": 2.0,
                    "holding_bars": 1,
                }
            ],
            "diagnostics": {"snapshots_evaluated": 10, "setups_detected": 2, "trades_skipped": 1},
        },
        {"request": {"symbol": "GBP/USD"}, "summary": {"total_trades": 0}, "trades": [], "diagnostics": {}},
    ]

    payload = controller._build_batch_payload(requests, runs)

    assert payload["mode"] == "system_backtest_batch"
    assert payload["request"]["symbols"] == ["EUR/USD", "GBP/USD"]
    assert payload["summary"]["total_trades"] == 1
    assert payload["summary"]["expectancy_r"] == 2.0
    assert payload["breakdowns"]["by_symbol"]["EUR/USD"]["total_trades"] == 1
    assert payload["diagnostics"]["symbols_tested"] == 2
