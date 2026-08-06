"""Test suite for Group C — US2Y ticker fix.

C1 — US2Y ticker is ``2YY=F`` (2-Year Treasury futures), quoted in yield %.
The previous ``^IRX`` (13-Week T-Bill index) was the wrong instrument:
it tracks the 3-month T-bill, not the 2-year yield used to gauge Fed
short-rate expectations.
"""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# C1 — US2Y ticker is 2YY=F
# ---------------------------------------------------------------------------


class TestC1Ticker:
    def test_us2y_ticker_is_2yy(self):
        from services.market_data_service import MARKET_TICKERS

        assert "US2Y" in MARKET_TICKERS, "C1 FAILED: US2Y missing from MARKET_TICKERS"
        assert MARKET_TICKERS["US2Y"] == "2YY=F", (
            f"C1 FAILED: expected '2YY=F', got {MARKET_TICKERS['US2Y']!r}"
        )

    def test_wrong_irx_ticker_removed(self):
        from services.market_data_service import MARKET_TICKERS

        assert "^IRX" not in MARKET_TICKERS.values(), (
            "C1 FAILED: wrong ticker '^IRX' (13-week T-Bill) still present in MARKET_TICKERS"
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

    def test_2y_ticker_passed_to_yfinance(self):
        """Verify the new ticker is used when downloading data."""
        import services.market_data_service as mds

        tickers_seen = []

        def fake_download(ticker, *, period, interval, progress):
            tickers_seen.append(ticker)
            return type("EmptyDF", (), {"empty": True, "iterrows": lambda s: iter([])})()

        mds.fetch_macro_correlation_context(
            force_refresh=True,
            downloader=fake_download,
        )

        assert "2YY=F" in tickers_seen, (
            f"C1 FAILED: 2YY=F not downloaded; tickers seen: {tickers_seen}"
        )
        assert "^IRX" not in tickers_seen, (
            f"C1 FAILED: wrong ticker ^IRX still being downloaded"
        )

    def test_2y_ticker_passed_to_yahoo_fallback(self):
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

        assert "2YY=F" in tickers_seen, (
            f"C1 FAILED: 2YY=F not in fallback; tickers: {tickers_seen}"
        )
        assert "^IRX" not in tickers_seen, (
            f"C1 FAILED: wrong ticker ^IRX still in fallback"
        )


# ---------------------------------------------------------------------------
# Integration — full market overview with new ticker
# ---------------------------------------------------------------------------


class TestC1Integration:
    def test_us2y_present_in_overview_with_valid_data(self):
        """End-to-end: US2Y with 2YY=F should be present when data exists."""
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

        overview = mds.fetch_market_overview(downloader=fake_download)

        assert "US2Y" in overview, (
            f"C1 FAILED: US2Y missing from overview; got: {set(overview.keys())}"
        )
        close, change_pct = overview["US2Y"]
        assert close == 4.1
        assert change_pct == pytest.approx(2.5, rel=0.01)  # (4.1-4.0)/4.0*100

    def test_us2y_value_in_reasonable_yield_percent_range(self):
        """Scale guard: 2YY=F quotes yield % directly (not 10x like ^TNX).

        A real 2-year yield such as 4.15% must pass through unchanged and land
        inside a plausible percent-yield band (0 < value < 15). If the
        instrument were scaled 10x (like ^TNX), the value would exceed 15 and
        this test would fail.
        """
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
            (datetime(2026, 7, 7), FakeRow(4.10, 4.12, 4.08, 4.10, 1000)),
            (datetime(2026, 7, 8), FakeRow(4.15, 4.17, 4.13, 4.15, 1100)),
        ]

        class FakeDF:
            empty = False

            def iterrows(self):
                return iter(rows)

        def fake_download(ticker, *, period, interval, progress):
            return FakeDF()

        overview = mds.fetch_market_overview(downloader=fake_download)

        assert "US2Y" in overview, "C1 FAILED: US2Y missing from overview"
        close, _ = overview["US2Y"]
        assert 0.0 < close < 15.0, (
            f"C1 FAILED: US2Y value {close} is outside the plausible percent-yield "
            f"range (0, 15); instrument may be scaled 10x like ^TNX"
        )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))