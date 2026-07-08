"""Test suite for Group C — US2Y ticker fix.

C1 — US2Y ticker changed from ``2YY=F`` (futures) to ``^IRX`` (13-Week T-Bill index).
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# C1 — US2Y ticker is now ^IRX
# ---------------------------------------------------------------------------


class TestC1Ticker:
    def test_us2y_ticker_is_irx(self):
        from services.market_data_service import MARKET_TICKERS

        assert "US2Y" in MARKET_TICKERS, "C1 FAILED: US2Y missing from MARKET_TICKERS"
        assert MARKET_TICKERS["US2Y"] == "^IRX", (
            f"C1 FAILED: expected '^IRX', got {MARKET_TICKERS['US2Y']!r}"
        )

    def test_old_ticker_removed(self):
        from services.market_data_service import MARKET_TICKERS

        assert "2YY=F" not in MARKET_TICKERS.values(), (
            "C1 FAILED: old ticker '2YY=F' still present in MARKET_TICKERS"
        )

    def test_all_four_tickers_present(self):
        from services.market_data_service import MARKET_TICKERS

        assert set(MARKET_TICKERS.keys()) == {"DXY", "VIX", "US10Y", "US2Y"}, (
            f"C1 FAILED: unexpected keys: {set(MARKET_TICKERS.keys())}"
        )

    def test_correlation_keys_still_match(self):
        from services.market_data_service import _CORRELATION_KEYS, MARKET_TICKERS

        assert _CORRELATION_KEYS.keys() == MARKET_TICKERS.keys(), (
            "C1 FAILED: _CORRELATION_KEYS and MARKET_TICKERS keys diverged"
        )

    def test_irx_ticker_passed_to_yfinance(self):
        """Verify the new ticker is used when downloading data."""
        import services.market_data_service as mds

        tickers_seen = []

        def fake_download(ticker, *, period, interval, progress):
            tickers_seen.append(ticker)
            return type("EmptyDF", (), {"empty": True, "iterrows": lambda s: iter([])})()

        original = mds._yf_download
        mds._yf_download = fake_download
        try:
            mds.fetch_macro_correlation_context(force_refresh=True)
        finally:
            mds._yf_download = original

        assert "^IRX" in tickers_seen, (
            f"C1 FAILED: ^IRX not downloaded; tickers seen: {tickers_seen}"
        )
        assert "2YY=F" not in tickers_seen, (
            f"C1 FAILED: old ticker 2YY=F still being downloaded"
        )

    def test_irx_ticker_passed_to_yahoo_fallback(self):
        """Verify the new ticker is used in the Yahoo chart fallback."""
        from services.market_data_service import (
            fetch_market_overview_from_yahoo_chart,
            MARKET_TICKERS,
        )

        tickers_seen = []

        def fake_fetch(tag, ticker, *, timeout=10):
            tickers_seen.append(ticker)
            return tag, (4.10, -0.05)

        with patch(
            "services.yahoo_chart_fetcher.fetch_single_yahoo_chart",
            side_effect=fake_fetch,
        ):
            fetch_market_overview_from_yahoo_chart()

        assert "^IRX" in tickers_seen, (
            f"C1 FAILED: ^IRX not in fallback; tickers: {tickers_seen}"
        )
        assert "2YY=F" not in tickers_seen, (
            f"C1 FAILED: old ticker 2YY=F still in fallback"
        )


# ---------------------------------------------------------------------------
# Integration — full market overview with new ticker
# ---------------------------------------------------------------------------


class TestC1Integration:
    def test_us2y_present_in_overview_with_valid_data(self):
        """End-to-end: US2Y with ^IRX should be present when data exists."""
        import services.market_data_service as mds
        from datetime import datetime

        mds._CORRELATION_CACHE = None
        mds._CORRELATION_CACHE_TIME = None

        class FakeRow:
            def __init__(self, o, h, l, c, v):
                self.Open = o
                self.High = h
                self.Low = l
                self.Close = c
                self.Volume = v

            def __getitem__(self, key):
                return getattr(self, key)

        rows = [
            (datetime(2026, 7, 7), FakeRow(4.0, 4.1, 3.9, 4.0, 1000)),
            (datetime(2026, 7, 8), FakeRow(4.1, 4.2, 4.0, 4.1, 1100)),
        ]

        class FakeDF:
            empty = False

            def iterrows(self):
                return iter(rows)

        def fake_download(ticker, *, period, interval, progress):
            return FakeDF()

        def fake_fetch(tag, ticker, *, timeout=10):
            return None  # fallback not needed, yfinance mock supplies data

        with patch.object(mds, "_yf_download", side_effect=fake_download):
            with patch(
                "services.yahoo_chart_fetcher.fetch_single_yahoo_chart",
                side_effect=fake_fetch,
            ):
                overview = mds.fetch_market_overview()

        assert "US2Y" in overview, (
            f"C1 FAILED: US2Y missing from overview; got: {set(overview.keys())}"
        )
        close, change_pct = overview["US2Y"]
        assert close == 4.1
        assert change_pct == pytest.approx(2.5, rel=0.01)  # (4.1-4.0)/4.0*100


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
