from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace

from services.mt5_service import MT5Service


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
