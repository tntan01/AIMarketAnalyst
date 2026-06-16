from __future__ import annotations

import sys
from types import SimpleNamespace

from core.risk_engine import _resolve_quote_to_usd_rate


class FakeMT5:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.raise_on_tick = False
        self.already_connected = False

    def initialize(self) -> bool:
        self.initialize_calls += 1
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1

    def terminal_info(self) -> SimpleNamespace | None:
        return SimpleNamespace(connected=True) if self.already_connected else None

    def account_info(self) -> SimpleNamespace | None:
        return SimpleNamespace(login=123456) if self.already_connected else None

    def symbol_info_tick(self, pair_name: str) -> SimpleNamespace | None:
        if self.raise_on_tick:
            raise RuntimeError("MT5 tick failure")
        if pair_name == "EURUSD":
            return SimpleNamespace(bid=1.25)
        return None

    def symbols_get(self) -> list[object]:
        return []


def test_resolve_quote_to_usd_rate_shuts_down_after_initialize(monkeypatch):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    rate = _resolve_quote_to_usd_rate("GBP/EUR")

    assert rate == 1.25
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 1


def test_resolve_quote_to_usd_rate_does_not_shutdown_existing_mt5_connection(monkeypatch):
    fake_mt5 = FakeMT5()
    fake_mt5.already_connected = True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    rate = _resolve_quote_to_usd_rate("GBP/EUR")

    assert rate == 1.25
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 0


def test_resolve_quote_to_usd_rate_shuts_down_when_mt5_errors(monkeypatch):
    fake_mt5 = FakeMT5()
    fake_mt5.raise_on_tick = True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    rate = _resolve_quote_to_usd_rate("GBP/EUR")

    assert rate is None
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 1
