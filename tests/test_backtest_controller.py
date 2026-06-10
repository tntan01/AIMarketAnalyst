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
        return ["EURUSD"]

    def resolve_symbol(self, app_symbol, available_symbols):
        return "EURUSD"

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
