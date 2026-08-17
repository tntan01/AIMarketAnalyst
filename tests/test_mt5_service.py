from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace

from services.mt5_service import MT5Service


class FakeMT5:
    def __init__(self) -> None:
        self.initialize_calls = 0
        self.shutdown_calls = 0
        self.initialized = False
        self.positions: tuple[SimpleNamespace, ...] = ()
        self.orders: tuple[SimpleNamespace, ...] = ()

    def initialize(self) -> bool:
        self.initialize_calls += 1
        self.initialized = True
        return True

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        self.initialized = False

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


def test_connection_status_is_a_pure_query(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    status = MT5Service(profile_path).connection_status()

    assert fake_mt5.initialize_calls == 0
    assert status.initialized is False
    assert status.terminal_connected is False
    assert status.logged_in is False


def test_connect_initializes_mt5_and_connection_status_reports_it(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")
    service = MT5Service(profile_path)

    assert service.connect() is True
    assert service.connect() is True
    status = service.connection_status()

    assert fake_mt5.initialize_calls == 1
    assert status.initialized is True
    assert status.terminal_connected is True
    assert status.logged_in is True
    assert status.login == 123456


def test_connect_reuses_existing_mt5_connection(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    fake_mt5.initialized = True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    service = MT5Service(profile_path)
    assert service.connect() is True
    status = service.connection_status()

    assert fake_mt5.initialize_calls == 0
    assert status.terminal_connected is True


def test_disconnect_only_closes_connection_owned_by_service(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")
    service = MT5Service(profile_path)

    service.connect()
    service.disconnect()
    service.disconnect()

    assert fake_mt5.shutdown_calls == 1


def test_disconnect_does_not_close_preexisting_connection(monkeypatch, tmp_path):
    fake_mt5 = FakeMT5()
    fake_mt5.initialized = True
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")
    service = MT5Service(profile_path)

    service.connect()
    service.disconnect()

    assert fake_mt5.initialize_calls == 0
    assert fake_mt5.shutdown_calls == 0


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


class OrderMarginMT5(FakeMT5):
    """FakeMT5 with the broker margin-calculation surface."""

    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1

    def __init__(self) -> None:
        super().__init__()
        self.calc_margin_results: dict[tuple[int, str], float | None] = {}
        self.calc_margin_calls: list[tuple[int, str, float, float]] = []

    def order_calc_margin(self, order_type, symbol, volume, price):
        self.calc_margin_calls.append((order_type, symbol, volume, price))
        return self.calc_margin_results.get((order_type, symbol))


def _order_margin_service(monkeypatch, tmp_path, fake_mt5) -> MT5Service:
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")
    return MT5Service(profile_path)


def test_min_lot_order_margin_returns_conservative_max(monkeypatch, tmp_path):
    fake_mt5 = OrderMarginMT5()
    fake_mt5.calc_margin_results[(OrderMarginMT5.ORDER_TYPE_BUY, "EURUSD")] = 10.0
    fake_mt5.calc_margin_results[(OrderMarginMT5.ORDER_TYPE_SELL, "EURUSD")] = 12.5

    margin = _order_margin_service(monkeypatch, tmp_path, fake_mt5).min_lot_order_margin("EURUSD")

    assert margin == 12.5
    # Both directions are probed, always with the broker's minimum lot.
    assert len(fake_mt5.calc_margin_calls) == 2
    volumes = {call[2] for call in fake_mt5.calc_margin_calls}
    assert volumes == {0.01}
    directions = {call[0] for call in fake_mt5.calc_margin_calls}
    assert directions == {OrderMarginMT5.ORDER_TYPE_BUY, OrderMarginMT5.ORDER_TYPE_SELL}


def test_min_lot_order_margin_survives_one_side_failing(monkeypatch, tmp_path):
    fake_mt5 = OrderMarginMT5()
    fake_mt5.calc_margin_results[(OrderMarginMT5.ORDER_TYPE_BUY, "EURUSD")] = 9.0
    # SELL stays unmapped -> the fake returns None for it.

    margin = _order_margin_service(monkeypatch, tmp_path, fake_mt5).min_lot_order_margin("EURUSD")

    assert margin == 9.0


def test_min_lot_order_margin_none_for_unknown_symbol(monkeypatch, tmp_path):
    fake_mt5 = OrderMarginMT5()

    margin = _order_margin_service(monkeypatch, tmp_path, fake_mt5).min_lot_order_margin("GBPJPY")

    assert margin is None
    assert fake_mt5.calc_margin_calls == []


def test_min_lot_order_margin_none_when_broker_calc_fails(monkeypatch, tmp_path):
    fake_mt5 = OrderMarginMT5()
    # Both directions return None (broker refused to compute).

    margin = _order_margin_service(monkeypatch, tmp_path, fake_mt5).min_lot_order_margin("EURUSD")

    assert margin is None


def test_min_lot_order_margin_none_when_terminal_disconnected(monkeypatch, tmp_path):
    class DisconnectedOrderMarginMT5(OrderMarginMT5):
        def terminal_info(self):
            return None

    fake_mt5 = DisconnectedOrderMarginMT5()
    fake_mt5.calc_margin_results[(OrderMarginMT5.ORDER_TYPE_BUY, "EURUSD")] = 10.0

    margin = _order_margin_service(monkeypatch, tmp_path, fake_mt5).min_lot_order_margin("EURUSD")

    assert margin is None
    assert fake_mt5.calc_margin_calls == []


def test_min_lot_order_margin_none_when_mt5_package_missing(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "MetaTrader5", None)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    assert MT5Service(profile_path).min_lot_order_margin("EURUSD") is None


def test_connection_status_reports_margin_and_free_margin(monkeypatch, tmp_path):
    class MarginAccountMT5(FakeMT5):
        def account_info(self):
            return SimpleNamespace(
                login=123456,
                trade_allowed=True,
                company="Broker",
                server="Broker-Demo",
                balance=1000.0,
                margin=150.0,
                margin_free=850.0,
                currency="USD",
            )

    fake_mt5 = MarginAccountMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    status = MT5Service(profile_path).mt5_connection_status()

    assert status.balance == 1000.0
    assert status.margin == 150.0
    assert status.free_margin == 850.0


def _quality_service(monkeypatch, tmp_path, fake_mt5) -> MT5Service:
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")
    return MT5Service(profile_path)


def test_symbol_data_quality_reports_tick_time(monkeypatch, tmp_path):
    fixed = datetime(2026, 8, 16, 12, 0, 0, tzinfo=timezone.utc)

    class FixedTickMT5(FakeMT5):
        def symbol_info_tick(self, symbol):
            if symbol != "EURUSD":
                return None
            return SimpleNamespace(
                bid=1.1000,
                ask=1.1002,
                time=int(fixed.timestamp()),
                time_msc=int(fixed.timestamp() * 1000),
            )

    quality = _quality_service(monkeypatch, tmp_path, FixedTickMT5()).symbol_data_quality(
        "EUR/USD", "EURUSD"
    )

    # The tick timestamp is tz-aware UTC and mirrors the broker tick exactly.
    assert quality["tick_time"] == fixed
    assert quality["tick_time"].tzinfo is not None


def test_symbol_data_quality_tick_time_none_when_no_tick(monkeypatch, tmp_path):
    class NoTickMT5(FakeMT5):
        def symbol_info_tick(self, symbol):
            return None

    quality = _quality_service(monkeypatch, tmp_path, NoTickMT5()).symbol_data_quality(
        "EUR/USD", "EURUSD"
    )

    # Fail-closed: a missing tick never fabricates a freshness reference.
    assert quality["tick_time"] is None


def test_symbol_data_quality_tick_time_none_when_tick_has_no_timestamp(monkeypatch, tmp_path):
    class TimelessTickMT5(FakeMT5):
        def symbol_info_tick(self, symbol):
            return SimpleNamespace(bid=1.1000, ask=1.1002, time=0, time_msc=0)

    quality = _quality_service(monkeypatch, tmp_path, TimelessTickMT5()).symbol_data_quality(
        "EUR/USD", "EURUSD"
    )

    assert quality["tick_time"] is None
