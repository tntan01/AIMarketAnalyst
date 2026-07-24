from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace

from services.mt5_service import MT5Service


class FakeMT5:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.initialized = False
        self.positions: tuple[SimpleNamespace, ...] = ()
        self.orders: tuple[SimpleNamespace, ...] = ()

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

    def symbol_select(self, symbol: str, enabled: bool) -> bool:
        return symbol == "EURUSD" and enabled

    def symbol_info(self, symbol: str) -> SimpleNamespace | None:
        if symbol != "EURUSD":
            return None
        return SimpleNamespace(
            trade_mode=4,
            point=0.0001,
            spread=2,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_tick_size=0.0001,
            trade_tick_value_loss=10.0,
            trade_tick_value=10.0,
            trade_contract_size=100000.0,
        )

    def symbol_info_tick(self, symbol: str) -> SimpleNamespace | None:
        if symbol != "EURUSD":
            return None
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            bid=1.1000,
            ask=1.1002,
            time=int(now.timestamp()),
            time_msc=int(now.timestamp() * 1000),
        )

    def positions_get(self, **kwargs) -> tuple:
        symbol = kwargs.get("symbol")
        return tuple(
            item
            for item in self.positions
            if not symbol or item.symbol == symbol
        )

    def orders_get(self, **kwargs) -> tuple:
        symbol = kwargs.get("symbol")
        return tuple(
            item
            for item in self.orders
            if not symbol or item.symbol == symbol
        )


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


def test_execution_snapshot_captures_tick_spread_volume_and_symbol_state(
    monkeypatch,
    tmp_path,
):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    snapshot = MT5Service(profile_path).execution_snapshot("EURUSD")

    assert snapshot.connected is True
    assert snapshot.logged_in is True
    assert snapshot.trade_allowed is True
    assert snapshot.symbol_available is True
    assert snapshot.symbol_trade_mode == 4
    assert snapshot.bid == 1.1000
    assert snapshot.ask == 1.1002
    assert round(float(snapshot.spread_points or 0), 6) == 2
    assert snapshot.volume_step == 0.01
    assert snapshot.symbol_state_available is True
    assert snapshot.has_open_position_or_order is False


def test_portfolio_snapshot_reads_positions_pending_orders_and_risk_metadata(
    monkeypatch,
    tmp_path,
):
    fake_mt5 = FakeMT5()
    fake_mt5.positions = (
        SimpleNamespace(
            ticket=11,
            symbol="EURUSD",
            type=0,
            volume=0.1,
            price_open=1.1000,
            price_current=1.1010,
            sl=1.0900,
        ),
    )
    fake_mt5.orders = (
        SimpleNamespace(
            ticket=12,
            symbol="EURUSD",
            type=3,
            volume_current=0.2,
            volume_initial=0.2,
            price_open=1.1050,
            sl=1.1150,
        ),
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    snapshot = MT5Service(profile_path).portfolio_snapshot()

    assert snapshot.available is True
    assert len(snapshot.positions) == 1
    assert len(snapshot.pending_orders) == 1
    position = snapshot.positions[0]
    pending = snapshot.pending_orders[0]
    assert position.side == "buy"
    assert pending.side == "sell"
    assert position.tick_size == 0.0001
    assert position.tick_value_loss == 10.0
    assert position.contract_size == 100000.0


def test_portfolio_snapshot_distinguishes_empty_from_unavailable(
    monkeypatch,
    tmp_path,
):
    class UnavailablePortfolioMT5(FakeMT5):
        def positions_get(self, **kwargs):
            return None

    fake_mt5 = UnavailablePortfolioMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    snapshot = MT5Service(profile_path).portfolio_snapshot()

    assert snapshot.available is False
    assert "PORTFOLIO_STATE_UNAVAILABLE" in snapshot.reason_codes
