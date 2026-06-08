"""Phase 10.7: verify symbol/direction normalisation helpers."""

from __future__ import annotations

from core.statistical_edge_engine import normalize_direction, normalize_regime, normalize_symbol


class TestNormalizeSymbol:
    def test_slash_format(self):
        assert normalize_symbol("EUR/USD") == "EURUSD"

    def test_with_whitespace(self):
        assert normalize_symbol(" gbp_jpy ") == "GBPJPY"

    def test_dash_format(self):
        assert normalize_symbol("XAU-USD") == "XAUUSD"

    def test_underscore_format(self):
        assert normalize_symbol("GBP_JPY") == "GBPJPY"

    def test_already_clean(self):
        assert normalize_symbol("EURUSD") == "EURUSD"

    def test_lowercase(self):
        assert normalize_symbol("eurusd") == "EURUSD"

    def test_none_returns_none(self):
        assert normalize_symbol(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_symbol("") is None

    def test_whitespace_only_returns_none(self):
        assert normalize_symbol("   ") is None

    def test_non_string_returns_none(self):
        assert normalize_symbol(123) is None
        assert normalize_symbol([]) is None

    def test_clean_result(self):
        """Verify no separators remain."""
        result = normalize_symbol("EUR/USD-XAU")
        assert "/" not in result
        assert "-" not in result
        assert "_" not in result
        assert " " not in result


class TestNormalizeDirection:
    def test_buy_upper(self):
        assert normalize_direction("BUY") == "buy"

    def test_buy_lower(self):
        assert normalize_direction("buy") == "buy"

    def test_buy_mixed(self):
        assert normalize_direction("Buy") == "buy"

    def test_long_lower(self):
        assert normalize_direction("long") == "buy"

    def test_long_upper(self):
        assert normalize_direction("LONG") == "buy"

    def test_sell_upper(self):
        assert normalize_direction("SELL") == "sell"

    def test_sell_lower(self):
        assert normalize_direction("sell") == "sell"

    def test_short_lower(self):
        assert normalize_direction("short") == "sell"

    def test_short_upper(self):
        assert normalize_direction("SHORT") == "sell"

    def test_whitespace(self):
        assert normalize_direction("  BUY  ") == "buy"
        assert normalize_direction(" sell ") == "sell"

    def test_unknown_returns_none(self):
        assert normalize_direction("hold") is None
        assert normalize_direction("neutral") is None

    def test_none_returns_none(self):
        assert normalize_direction(None) is None

    def test_empty_returns_none(self):
        assert normalize_direction("") is None

    def test_non_string_returns_none(self):
        assert normalize_direction(1) is None


class TestNormalizeRegimeAnalysisEngineAliases:
    """Regime aliases from detect_market_regime / analysis_engine must map
    to the canonical forms used in journal trade data."""

    def test_trend_up_maps_to_trending_up(self):
        assert normalize_regime("trend_up") == "trending_up"

    def test_trend_down_maps_to_trending_down(self):
        assert normalize_regime("trend_down") == "trending_down"

    def test_uptrend_maps_to_trending_up(self):
        assert normalize_regime("uptrend") == "trending_up"

    def test_downtrend_maps_to_trending_down(self):
        assert normalize_regime("downtrend") == "trending_down"

    def test_trending_up_unchanged(self):
        assert normalize_regime("trending_up") == "trending_up"

    def test_trending_down_unchanged(self):
        assert normalize_regime("trending_down") == "trending_down"

    def test_range_still_maps_to_ranging(self):
        assert normalize_regime("range") == "ranging"

    def test_case_insensitive_trend_up(self):
        assert normalize_regime("TREND_UP") == "trending_up"
        assert normalize_regime("Trend_Up") == "trending_up"
