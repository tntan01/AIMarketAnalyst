from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace
from unittest.mock import MagicMock

from controllers.backtest_controller import BacktestController
from services.mt5_service import MT5Service


def test_backtest_request_preparation_runs_with_backtest_task() -> None:
    controller = object.__new__(BacktestController)
    request = MagicMock()
    progress = MagicMock()
    controller.build_requests = MagicMock(return_value=[request])
    controller.run_backtest = MagicMock(return_value={"status": "ok"})

    result = controller.prepare_and_run_backtest(
        build_args={"symbols": ["EUR/USD"]},
        research_validation_enabled=True,
        monte_carlo_requested=False,
        _progress_callback=progress,
    )

    assert result == {"status": "ok"}
    controller.build_requests.assert_called_once_with(symbols=["EUR/USD"])
    controller.run_backtest.assert_called_once_with(
        request=request,
        research_validation_enabled=True,
        monte_carlo_requested=False,
        _progress_callback=progress,
    )
    progress.assert_any_call(5, "Đang chuẩn bị dữ liệu backtest...")


class _ConcurrentSymbolsMT5:
    def __init__(self) -> None:
        self.initialized = False
        self.active_calls = 0
        self.max_active_calls = 0
        self._lock = Lock()

    def initialize(self) -> bool:
        self.initialized = True
        return True

    def terminal_info(self):
        return SimpleNamespace(connected=True) if self.initialized else None

    def account_info(self):
        return SimpleNamespace(login=1) if self.initialized else None

    def symbols_get(self):
        with self._lock:
            self.active_calls += 1
            self.max_active_calls = max(self.max_active_calls, self.active_calls)
        time.sleep(0.03)
        with self._lock:
            self.active_calls -= 1
        return [SimpleNamespace(name="EURUSD", visible=True)]


def test_mt5_sdk_operations_are_serialized_per_service(monkeypatch, tmp_path) -> None:
    fake_mt5 = _ConcurrentSymbolsMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")
    service = MT5Service(profile_path)

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _unused: service.available_symbols(), range(2)))

    assert results == [["EURUSD"], ["EURUSD"]]
    assert fake_mt5.max_active_calls == 1
