import json
import sys
from types import SimpleNamespace

from services.mt5_service import MT5Service


def test_resolve_symbol_matches_exact_alias(tmp_path) -> None:
    path = tmp_path / "symbol_profiles.json"
    path.write_text(
        json.dumps({"EUR/USD": {"mt5_aliases": ["EURUSD", "EURUSDm"]}}),
        encoding="utf-8",
    )
    service = MT5Service(path)

    assert service.resolve_symbol("EUR/USD", ["EURUSDm"]) == "EURUSDm"


def test_resolve_symbol_matches_broker_suffix(tmp_path) -> None:
    path = tmp_path / "symbol_profiles.json"
    path.write_text(
        json.dumps({"EUR/USD": {"mt5_aliases": ["EURUSD", "EURUSDm"]}}),
        encoding="utf-8",
    )
    service = MT5Service(path)

    assert service.resolve_symbol("EUR/USD", ["EURUSD.r", "GBPUSD.r"]) == "EURUSD.r"


def test_resolve_symbol_returns_none_when_missing(tmp_path) -> None:
    path = tmp_path / "symbol_profiles.json"
    path.write_text(
        json.dumps({"EUR/USD": {"mt5_aliases": ["EURUSD", "EURUSDm"]}}),
        encoding="utf-8",
    )
    service = MT5Service(path)

    assert service.resolve_symbol("EUR/USD", ["GBPUSD.r"]) is None


def test_available_symbols_filters_market_watch_visible_symbols(tmp_path, monkeypatch) -> None:
    path = tmp_path / "symbol_profiles.json"
    path.write_text(json.dumps({}), encoding="utf-8")
    service = MT5Service(path)
    fake_mt5 = SimpleNamespace(
        initialize=lambda: True,
        symbols_get=lambda: [
            SimpleNamespace(name="EURUSD.r", visible=True),
            SimpleNamespace(name="GBPUSD.r", visible=True),
            SimpleNamespace(name="AUDUSD.r", visible=False),
        ],
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    assert service.available_symbols(market_watch_only=True) == ["EURUSD.r", "GBPUSD.r"]
    assert service.available_symbols(market_watch_only=False) == ["AUDUSD.r", "EURUSD.r", "GBPUSD.r"]


def test_configured_symbols_in_market_watch_returns_configured_matches_sorted(tmp_path, monkeypatch) -> None:
    path = tmp_path / "symbol_profiles.json"
    path.write_text(
        json.dumps(
            {
                "GBP/USD": {"mt5_aliases": ["GBPUSD"]},
                "EUR/USD": {"mt5_aliases": ["EURUSD"]},
                "AUD/USD": {"mt5_aliases": ["AUDUSD"]},
            }
        ),
        encoding="utf-8",
    )
    service = MT5Service(path)
    fake_mt5 = SimpleNamespace(
        initialize=lambda: True,
        symbols_get=lambda: [
            SimpleNamespace(name="GBPUSD.r", visible=True),
            SimpleNamespace(name="EURUSD.r", visible=True),
            SimpleNamespace(name="AUDUSD.r", visible=False),
        ],
    )
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)

    assert service.configured_symbols_in_market_watch() == [
        ("EUR/USD", "EURUSD.r"),
        ("GBP/USD", "GBPUSD.r"),
    ]
