from __future__ import annotations

import sys
from types import SimpleNamespace

from services.mt5_service import MT5Service


class FakeMT5:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.initialized = False

    def initialize(self) -> bool:
        self.initialize_calls += 1
        self.initialized = True
        return True

    def last_error(self) -> tuple[int, str]:
        return 0, ""

    def terminal_info(self) -> SimpleNamespace | None:
        if not self.initialized:
            return None
        return SimpleNamespace(connected=True, name="Terminal", path="C:/MT5")

    def account_info(self) -> SimpleNamespace | None:
        if not self.initialized:
            return None
        return SimpleNamespace(
            login=123456,
            trade_allowed=True,
            company="Broker",
            server="Broker-Demo",
            balance=1000.0,
            currency="USD",
        )

    def symbols_get(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(name="EURUSD", visible=True),
            SimpleNamespace(name="USDJPY", visible=False),
        ]


def test_connection_status_initializes_mt5(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    status = MT5Service(profile_path).connection_status()

    assert fake_mt5.initialize_calls == 1
    assert status.initialized is True
    assert status.terminal_connected is True
    assert status.logged_in is True
    assert status.login == 123456


def test_connection_status_reuses_existing_mt5_connection(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    fake_mt5.initialized = True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    status = MT5Service(profile_path).connection_status()

    assert fake_mt5.initialize_calls == 0
    assert status.terminal_connected is True


def test_available_symbols_initializes_mt5(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    symbols = MT5Service(profile_path).available_symbols(market_watch_only=True)

    assert fake_mt5.initialize_calls == 1
    assert symbols == ["EURUSD"]
