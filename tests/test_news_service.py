"""Tests for news_service — macro scoring tier 1 (interest rate logic)."""

from __future__ import annotations

from unittest.mock import patch

from services.news_service import NewsService, currency_stance, stance_value


class TestCurrencyStance:
    def test_hawkish(self):
        result = currency_stance(
            ["Fed signals hike ahead", "Inflation remains elevated"],
            ["hike", "tightening", "hawkish"],
            ["cut", "easing", "dovish"],
        )
        assert result == "hawkish"

    def test_dovish(self):
        result = currency_stance(
            ["ECB signals cuts coming", "Growth slowdown expected"],
            ["hike", "tightening"],
            ["cut", "slowdown"],
        )
        assert result == "dovish"

    def test_neutral_when_equal(self):
        result = currency_stance(
            ["hike expected", "but also cuts possible"],
            ["hike"],
            ["cut"],
        )
        assert result == "neutral"

    def test_neutral_when_no_terms(self):
        result = currency_stance(
            ["Weather is nice today"],
            ["hike"],
            ["cut"],
        )
        assert result == "neutral"


class TestStanceValue:
    def test_values(self):
        assert stance_value("hawkish") == 1
        assert stance_value("neutral") == 0
        assert stance_value("dovish") == -1
        assert stance_value("unknown") == 0


class TestMacroTier1:
    @staticmethod
    def _make_service(rate_data: dict | None = None):
        """Create a NewsService with mocked interest rates."""
        service = NewsService()
        if rate_data is None:
            rate_data = {
                "USD": {"rate": 5.50, "rate_label": "5.50%", "trend": "hold"},
                "EUR": {"rate": 3.25, "rate_label": "3.25%", "trend": "cut"},
            }
        service._interest_rates = rate_data
        return service

    def test_hawkish_base_gives_buy_bias(self):
        service = self._make_service()
        buy, sell, detail = service._macro_tier1("USD", "EUR", "hawkish", "dovish")
        assert buy > sell  # USD hawkish + EUR dovish → buy EUR/USD gets higher score
        assert detail["base_stance"] == "hawkish"
        assert detail["quote_stance"] == "dovish"

    def test_both_neutral_is_balanced(self):
        service = self._make_service()
        buy, sell, detail = service._macro_tier1("USD", "EUR", "neutral", "neutral")
        # Both neutral, USD rate higher → slight advantage for short USD (=long EUR)
        assert buy >= sell

    def test_returns_valid_range(self):
        service = self._make_service()
        buy, sell, detail = service._macro_tier1("USD", "EUR", "hawkish", "hawkish")
        # Tier 1 max is 12 (rate_diff 0-2 + trend 0-5 + stance 0-5)
        assert 0 <= buy <= 12
        assert 0 <= sell <= 12

    def test_detail_has_required_keys(self):
        service = self._make_service()
        _, _, detail = service._macro_tier1("USD", "EUR", "neutral", "neutral")
        assert "base_rate" in detail
        assert "quote_rate" in detail
        assert "rate_differential" in detail
        assert "components" in detail
        assert "rate_diff" in detail["components"]
        assert "rate_trend" in detail["components"]
        assert "stance" in detail["components"]
