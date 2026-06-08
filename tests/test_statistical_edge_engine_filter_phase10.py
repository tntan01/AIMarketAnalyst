"""Phase 10.8: verify filter_trades_by_symbol_direction."""

from __future__ import annotations

from core.statistical_edge_engine import (
    filter_trades_by_symbol_direction,
    filter_trades_by_symbol_direction_regime,
)

_TRADES = [
    {"symbol": "EUR/USD", "direction": "BUY", "result_r": 1.2},
    {"symbol": "EURUSD", "direction": "sell", "result_r": -1.0},
    {"symbol": "GBP/JPY", "direction": "buy", "result_r": 0.8},
    {"pair": "EUR_USD", "side": "long", "result_r": 1.0},
    {"symbol": "XAUUSD", "direction": "buy", "result_r": 2.0},
]


class TestFilterBySymbolDirection:

    def test_filter_eurusd_buy_returns_two_trades(self):
        result = filter_trades_by_symbol_direction(_TRADES, "eurusd", "buy")
        assert len(result) == 2
        # First: symbol=EUR/USD,BUY; Fourth: pair=EUR_USD,long
        assert result[0]["result_r"] == 1.2
        assert result[1]["result_r"] == 1.0

    def test_filter_eurusd_sell_returns_one_trade(self):
        result = filter_trades_by_symbol_direction(_TRADES, "EUR/USD", "sell")
        assert len(result) == 1
        assert result[0]["result_r"] == -1.0

    def test_filter_gbpjpy_buy_returns_one_trade(self):
        result = filter_trades_by_symbol_direction(_TRADES, "GBP-JPY", "buy")
        assert len(result) == 1
        assert result[0]["symbol"] == "GBP/JPY"

    def test_filter_xauusd_buy_returns_one_trade(self):
        result = filter_trades_by_symbol_direction(_TRADES, "XAU/USD", "buy")
        assert len(result) == 1
        assert result[0]["result_r"] == 2.0

    def test_unknown_symbol_returns_empty(self):
        result = filter_trades_by_symbol_direction(_TRADES, "USD/JPY", "buy")
        assert result == []

    def test_unknown_direction_returns_empty(self):
        result = filter_trades_by_symbol_direction(_TRADES, "eurusd", "hold")
        assert result == []

    def test_none_trades_returns_empty(self):
        assert filter_trades_by_symbol_direction(None, "eurusd", "buy") == []

    def test_not_a_list_returns_empty(self):
        assert filter_trades_by_symbol_direction("not_a_list", "eurusd", "buy") == []  # type: ignore[arg-type]

    def test_does_not_mutate_original(self):
        original = [dict(t) for t in _TRADES]
        filter_trades_by_symbol_direction(_TRADES, "eurusd", "buy")
        for i, trade in enumerate(_TRADES):
            assert trade == original[i]

    def test_empty_string_symbol_returns_empty(self):
        assert filter_trades_by_symbol_direction(_TRADES, "", "buy") == []

    def test_none_trade_items_skipped(self):
        trades: list = [*_TRADES, None]  # type: ignore[list-item]
        result = filter_trades_by_symbol_direction(trades, "eurusd", "buy")  # type: ignore[arg-type]
        assert len(result) == 2


class TestFilterByRegimeAlias:
    """Query regime aliases (e.g. 'trend_up' from analysis_engine) must
    match journal canonical regimes (e.g. 'trending_up')."""

    _REGIME_TRADES = [
        {"symbol": "EUR/USD", "direction": "buy", "regime": "trending_up",
         "result_r": 1.0, "status": "closed"},
        {"symbol": "EUR/USD", "direction": "buy", "regime": "trending_down",
         "result_r": -1.0, "status": "closed"},
        {"symbol": "EUR/USD", "direction": "sell", "regime": "trending_up",
         "result_r": 0.5, "status": "closed"},
    ]

    def test_trend_up_queries_match_trending_up_trades(self):
        matched = filter_trades_by_symbol_direction_regime(
            self._REGIME_TRADES, "EUR/USD", "buy", "trend_up"
        )
        assert len(matched) == 1
        assert matched[0]["regime"] == "trending_up"

    def test_trend_down_queries_match_trending_down_trades(self):
        matched = filter_trades_by_symbol_direction_regime(
            self._REGIME_TRADES, "EUR/USD", "buy", "trend_down"
        )
        assert len(matched) == 1
        assert matched[0]["regime"] == "trending_down"

    def test_trending_up_queries_still_match_trending_up_trades(self):
        matched = filter_trades_by_symbol_direction_regime(
            self._REGIME_TRADES, "EUR/USD", "buy", "trending_up"
        )
        assert len(matched) == 1

    def test_unknown_regime_returns_empty(self):
        matched = filter_trades_by_symbol_direction_regime(
            self._REGIME_TRADES, "EUR/USD", "buy", "choppy"
        )
        assert matched == []
