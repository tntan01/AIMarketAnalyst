"""Phase 10.9: verify regime-aware group selection."""

from __future__ import annotations

from core.statistical_edge_engine import (
    filter_trades_by_symbol_direction_regime,
    normalize_regime,
    select_evidence_group,
)


def _trade(symbol: str, direction: str, result_r: float, regime: str) -> dict:
    return {
        "symbol": symbol,
        "direction": direction,
        "result_r": result_r,
        "regime": regime,
        "closed_at": f"2026-06-01T10:00:00",
    }


# Build test datasets
# 60 EURUSD buy ranging
_EURUSD_BUY_RANGING = [_trade("EUR/USD", "BUY", 1.2 if i % 2 == 0 else -0.8, "ranging") for i in range(60)]
# 80 EURUSD buy trending_up
_EURUSD_BUY_TRENDING = [_trade("EUR/USD", "BUY", 1.5 if i % 2 == 0 else -1.0, "trending_up") for i in range(80)]
# 20 GBPJPY buy ranging
_GBPJPY_BUY_RANGING = [_trade("GBP/JPY", "buy", 0.5, "ranging") for _ in range(20)]

_ALL_TRADES = [*_EURUSD_BUY_RANGING, *_EURUSD_BUY_TRENDING, *_GBPJPY_BUY_RANGING]


# ---------------------------------------------------------------------------
# normalize_regime
# ---------------------------------------------------------------------------


class TestNormalizeRegime:
    def test_standard_regimes(self):
        assert normalize_regime("trending_up") == "trending_up"
        assert normalize_regime("trending_down") == "trending_down"
        assert normalize_regime("ranging") == "ranging"
        assert normalize_regime("volatile") == "volatile"

    def test_maps_range_to_ranging(self):
        assert normalize_regime("range") == "ranging"

    def test_case_insensitive(self):
        assert normalize_regime("RANGING") == "ranging"
        assert normalize_regime("Trending_Up") == "trending_up"

    def test_whitespace(self):
        assert normalize_regime("  ranging  ") == "ranging"

    def test_none_returns_none(self):
        assert normalize_regime(None) is None

    def test_empty_returns_none(self):
        assert normalize_regime("") is None


# ---------------------------------------------------------------------------
# filter_trades_by_symbol_direction_regime
# ---------------------------------------------------------------------------


class TestFilterByRegime:
    def test_eurusd_buy_ranging_returns_60(self):
        result = filter_trades_by_symbol_direction_regime(
            _ALL_TRADES, "EUR/USD", "buy", "ranging"
        )
        assert len(result) == 60

    def test_eurusd_buy_trending_returns_80(self):
        result = filter_trades_by_symbol_direction_regime(
            _ALL_TRADES, "EUR/USD", "buy", "trending_up"
        )
        assert len(result) == 80

    def test_gbpjpy_buy_ranging_returns_20(self):
        result = filter_trades_by_symbol_direction_regime(
            _ALL_TRADES, "GBP/JPY", "buy", "ranging"
        )
        assert len(result) == 20

    def test_no_match_returns_empty(self):
        result = filter_trades_by_symbol_direction_regime(
            _ALL_TRADES, "EUR/USD", "buy", "volatile"
        )
        assert result == []


# ---------------------------------------------------------------------------
# select_evidence_group
# ---------------------------------------------------------------------------


class TestSelectEvidenceGroup:
    def test_eurusd_buy_ranging_selects_regime_group(self):
        group = select_evidence_group(_ALL_TRADES, "EUR/USD", "buy", regime="ranging")
        assert group["group_used"] == "symbol_direction_regime"
        assert group["sample_size"] == 60

    def test_eurusd_buy_volatile_falls_back_to_symbol_direction(self):
        # No volatile trades exist, but symbol_direction has 140 total >= 50
        group = select_evidence_group(_ALL_TRADES, "EUR/USD", "buy", regime="volatile")
        assert group["group_used"] == "symbol_direction"
        assert group["sample_size"] == 140

    def test_gbpjpy_buy_ranging_insufficient_falls_back_none(self):
        # 20 < 50 => group_used None
        group = select_evidence_group(_ALL_TRADES, "GBP/JPY", "buy", regime="ranging")
        assert group["group_used"] is None
        assert group["sample_size"] == 20

    def test_no_regime_uses_symbol_direction(self):
        group = select_evidence_group(_ALL_TRADES, "EUR/USD", "buy", regime=None)
        assert group["group_used"] == "symbol_direction"
        assert group["sample_size"] == 140

    def test_unknown_symbol_returns_none_group(self):
        group = select_evidence_group(_ALL_TRADES, "USD/JPY", "buy")
        assert group["group_used"] is None
        assert group["sample_size"] == 0

    def test_sample_size_counts_valid_rr_only(self):
        """Trades with dirty result_r are not counted."""
        trades = [
            *_EURUSD_BUY_RANGING[:10],
            {"symbol": "EUR/USD", "direction": "BUY", "result_r": "abc", "regime": "ranging", "closed_at": "2026-06-01T10:00:00"},
        ]
        group = select_evidence_group(trades, "EUR/USD", "buy", regime="ranging", min_group_size=5)
        # Only 10 clean trades counted, not 11
        assert group["sample_size"] == 10
        assert group["group_used"] == "symbol_direction_regime"
