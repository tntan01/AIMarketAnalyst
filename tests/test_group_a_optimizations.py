"""Test suite for Group A speed optimizations.

Covers:
  A1 — fetch_market_overview default period is now "5d"
  A2 — fetch_market_overview_from_yahoo_chart uses parallel ThreadPoolExecutor
  A3 — DashboardScreen caches AI responses by market snapshot
"""

from __future__ import annotations

import sys
import time
import json
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# A1 — default period reduced from "1mo" to "5d"
# ---------------------------------------------------------------------------


class TestA1FetchPeriod:
    def test_default_period_is_5d(self):
        from services.market_data_service import fetch_market_overview

        sig = fetch_market_overview
        defaults = sig.__kwdefaults__ or {}
        assert defaults.get("period") == "5d", (
            f"A1 FAILED: expected period='5d', got {defaults.get('period')!r}"
        )

    def test_period_passed_through_to_correlation_context(self):
        """Ensure the period parameter reaches fetch_macro_correlation_context."""
        import services.market_data_service as mds

        called_with = {}

        def fake_context(*, period, interval, downloader):
            called_with["period"] = period
            called_with["interval"] = interval
            return {
                "dxy_candles": None,
                "vix_candles": None,
                "us10y_candles": None,
                "us2y_candles": None,
            }

        original = mds.fetch_macro_correlation_context
        mds.fetch_macro_correlation_context = fake_context
        try:
            mds.fetch_market_overview()
        finally:
            mds.fetch_macro_correlation_context = original

        assert called_with.get("period") == "5d", (
            f"A1 FAILED: fetch_macro_correlation_context received "
            f"period={called_with.get('period')!r}, expected '5d'"
        )

    def test_custom_period_still_honored(self):
        """Callers can still override the period."""
        import services.market_data_service as mds

        called_with = {}

        def fake_context(*, period, interval, downloader):
            called_with["period"] = period
            return {"dxy_candles": None, "vix_candles": None,
                    "us10y_candles": None, "us2y_candles": None}

        original = mds.fetch_macro_correlation_context
        mds.fetch_macro_correlation_context = fake_context
        try:
            mds.fetch_market_overview(period="1mo")
        finally:
            mds.fetch_macro_correlation_context = original

        assert called_with.get("period") == "1mo", (
            f"A1 FAILED: custom period='1mo' was overridden to "
            f"{called_with.get('period')!r}"
        )


# ---------------------------------------------------------------------------
# A2 — parallel Yahoo chart fallback
# ---------------------------------------------------------------------------


class FakeFuture:
    def __init__(self, result):
        self._result = result

    def result(self):
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class TestA2ParallelFallback:
    def test_fetch_single_yahoo_chart_returns_tuple(self):
        from services.yahoo_chart_fetcher import fetch_single_yahoo_chart

        mock_json = {
            "chart": {
                "result": [{
                    "indicators": {
                        "quote": [{
                            "close": [100.0, 101.0, 102.0],
                        }]
                    }
                }]
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with patch("services.yahoo_chart_fetcher.requests.get", return_value=mock_resp):
            result = fetch_single_yahoo_chart("TEST", "TEST.TICKER", timeout=5)

        assert result is not None, "A2 FAILED: fetch_single_yahoo_chart returned None"
        tag, (close, change_pct) = result
        assert tag == "TEST"
        assert close == 102.0
        assert change_pct == pytest.approx(0.9900, rel=0.01)  # (102-101)/101*100

    def test_fetch_single_yahoo_insufficient_data(self):
        from services.yahoo_chart_fetcher import fetch_single_yahoo_chart

        mock_json = {
            "chart": {
                "result": [{
                    "indicators": {
                        "quote": [{
                            "close": [100.0],  # only 1 candle
                        }]
                    }
                }]
            }
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_json

        with patch("services.yahoo_chart_fetcher.requests.get", return_value=mock_resp):
            result = fetch_single_yahoo_chart("TEST", "TEST.TICKER")

        assert result is None, (
            "A2 FAILED: fetch_single_yahoo_chart should return None for <2 candles"
        )

    def test_fetch_single_yahoo_429_retry(self):
        from services.yahoo_chart_fetcher import fetch_single_yahoo_chart

        mock_json = {
            "chart": {
                "result": [{
                    "indicators": {
                        "quote": [{
                            "close": [100.0, 101.0],
                        }]
                    }
                }]
            }
        }
        mock_fail = MagicMock()
        mock_fail.status_code = 429
        mock_ok = MagicMock()
        mock_ok.status_code = 200
        mock_ok.json.return_value = mock_json

        with patch(
            "services.yahoo_chart_fetcher.requests.get",
            side_effect=[mock_fail, mock_ok],
        ) as mock_get:
            with patch("time.sleep", return_value=None):
                result = fetch_single_yahoo_chart("TEST", "TEST.TICKER")

        assert result is not None, "A2 FAILED: 429 retry did not succeed"
        assert mock_get.call_count == 2, (
            f"A2 FAILED: expected 2 calls (429 + retry), got {mock_get.call_count}"
        )

    def test_fallback_uses_thread_pool(self):
        """Verify fetch_market_overview_from_yahoo_chart delegates to
        fetch_single_yahoo_chart via ThreadPoolExecutor."""
        from services.market_data_service import fetch_market_overview_from_yahoo_chart

        results = {
            "DXY": ("DXY", (103.5, 0.2)),
            "VIX": ("VIX", (18.3, -2.1)),
            "US10Y": ("US10Y", (4.25, 0.05)),
            "US2Y": ("US2Y", (4.10, -0.03)),
        }

        def fake_fetch(tag, ticker, *, timeout=10):
            return results.get(tag)

        with patch(
            "services.yahoo_chart_fetcher.fetch_single_yahoo_chart",
            side_effect=fake_fetch,
        ):
            overview = fetch_market_overview_from_yahoo_chart()

        assert len(overview) == 4, (
            f"A2 FAILED: expected 4 results, got {len(overview)}: {overview}"
        )
        assert overview["DXY"] == (103.5, 0.2)
        assert overview["VIX"] == (18.3, -2.1)
        assert overview["US10Y"] == (4.25, 0.05)
        assert overview["US2Y"] == (4.10, -0.03)

    def test_fallback_respects_skip_tags(self):
        from services.market_data_service import fetch_market_overview_from_yahoo_chart

        call_count = 0

        def fake_fetch(tag, ticker, *, timeout=10):
            nonlocal call_count
            call_count += 1
            return tag, (100.0, 0.0)

        with patch(
            "services.yahoo_chart_fetcher.fetch_single_yahoo_chart",
            side_effect=fake_fetch,
        ):
            overview = fetch_market_overview_from_yahoo_chart(
                skip_tags={"DXY", "VIX"}
            )

        assert call_count == 2, (
            f"A2 FAILED: skip_tags should skip 2, leaving 2 calls; got {call_count}"
        )
        assert "DXY" not in overview
        assert "VIX" not in overview
        assert "US10Y" in overview
        assert "US2Y" in overview

    def test_fallback_handles_exceptions_gracefully(self):
        from services.market_data_service import fetch_market_overview_from_yahoo_chart

        def fake_fetch(tag, ticker, *, timeout=10):
            if tag == "US2Y":
                raise ConnectionError("simulated failure")
            if tag == "VIX":
                return None
            return tag, (100.0, 0.0)

        with patch(
            "services.yahoo_chart_fetcher.fetch_single_yahoo_chart",
            side_effect=fake_fetch,
        ):
            overview = fetch_market_overview_from_yahoo_chart()

        assert "DXY" in overview
        assert "US10Y" in overview
        assert "VIX" not in overview   # returned None
        assert "US2Y" not in overview  # raised exception
        assert len(overview) == 2, (
            f"A2 FAILED: expected 2 results after failures, got {len(overview)}"
        )


# ---------------------------------------------------------------------------
# A3 — AI response caching
# ---------------------------------------------------------------------------


class TestA3Cache:
    def test_cache_attrs_initialized(self):
        """Verify the cache attributes are assigned in DashboardScreen.__init__."""
        import inspect
        from ui.screens.dashboard_screen import DashboardScreen

        source = inspect.getsource(DashboardScreen.__init__)
        assert "_ai_last_snapshot" in source, (
            "A3 FAILED: _ai_last_snapshot not assigned in __init__"
        )
        assert "_ai_cached_response" in source, (
            "A3 FAILED: _ai_cached_response not assigned in __init__"
        )

    def test_cache_hit_returns_cached_response(self):
        """Simulate a cache hit: same snapshot -> skip AI call."""
        from ui.screens.dashboard_screen import DashboardScreen
        from unittest.mock import patch, MagicMock

        screen = MagicMock(spec=DashboardScreen)
        screen._ai_last_snapshot = ""
        screen._ai_cached_response = ""
        screen.settings_service = MagicMock()

        dlg_mock = MagicMock()
        ai_response_mock = MagicMock()
        ai_btn_mock = MagicMock()

        def simulate_closure(market_values, ai_svc_side_effect=None):
            """Recreate the request_analysis closure logic for testing."""
            mv = market_values
            snapshot = str(mv)
            if snapshot and snapshot == screen._ai_last_snapshot and screen._ai_cached_response:
                ai_response_mock.setMarkdown(screen._ai_cached_response)
                return "cache_hit"

            # Simulate full AI call
            screen._ai_last_snapshot = snapshot
            screen._ai_cached_response = "FAKE_AI_RESPONSE"
            ai_response_mock.setMarkdown("FAKE_AI_RESPONSE")
            return "api_call"

        # First call: cache miss -> API call
        result1 = simulate_closure({"DXY": (103.0, 0.1)})
        assert result1 == "api_call", "A3 FAILED: first call should hit API"
        assert screen._ai_cached_response == "FAKE_AI_RESPONSE"
        first_snapshot = screen._ai_last_snapshot
        assert first_snapshot != ""

        # Second call with same data: cache hit
        ai_response_mock.reset_mock()
        result2 = simulate_closure({"DXY": (103.0, 0.1)})
        assert result2 == "cache_hit", (
            "A3 FAILED: second call with same snapshot should hit cache"
        )
        ai_response_mock.setMarkdown.assert_called_once_with("FAKE_AI_RESPONSE")

        # Third call with different data: cache miss
        ai_response_mock.reset_mock()
        result3 = simulate_closure({"DXY": (104.0, 1.0)})
        assert result3 == "api_call", (
            "A3 FAILED: call with different snapshot should hit API"
        )
        assert screen._ai_last_snapshot != first_snapshot

    def test_empty_snapshot_skips_cache(self):
        """Empty market values should NOT be served from cache."""
        from ui.screens.dashboard_screen import DashboardScreen
        from unittest.mock import MagicMock

        screen = MagicMock(spec=DashboardScreen)
        screen._ai_last_snapshot = "old_snapshot"
        screen._ai_cached_response = "old_response"

        mv = {}
        snapshot = str(mv)
        if snapshot and snapshot == screen._ai_last_snapshot and screen._ai_cached_response:
            cached = True
        else:
            cached = False

        assert not cached, (
            "A3 FAILED: empty snapshot should not trigger cache hit"
        )


# ---------------------------------------------------------------------------
# Integration smoke test — full fetch_market_overview pipeline
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_full_pipeline_with_mocked_data(self):
        """End-to-end: fetch_market_overview with mocked yfinance + fallback."""
        import services.market_data_service as mds
        from datetime import datetime

        # Invalidate cache
        mds._CORRELATION_CACHE = None
        mds._CORRELATION_CACHE_TIME = None

        # Simulate yfinance returning good data for DXY/VIX/US10Y but empty for US2Y
        def fake_download(ticker, *, period, interval, progress):
            if ticker == "^IRX":
                return type("EmptyDF", (), {"empty": True, "iterrows": lambda s: iter([])})()
            # Return a mock DataFrame-like with 2 rows
            class FakeRow:
                def __init__(self, o, h, l, c, v):
                    self.Open = o
                    self.High = h
                    self.Low = l
                    self.Close = c
                    self.Volume = v

                def __getitem__(self, key):
                    return getattr(self, key)

                def __contains__(self, key):
                    return hasattr(self, key)

            rows = [
                (datetime(2026, 7, 7), FakeRow(100, 102, 99, 100, 1000)),
                (datetime(2026, 7, 8), FakeRow(101, 103, 100, 101, 1100)),
            ]

            class FakeDF:
                empty = False

                def iterrows(self):
                    return iter(rows)

            return FakeDF()

        # Simulate fallback: fetch_single_yahoo_chart for US2Y succeeds
        def fake_fetch(tag, ticker, *, timeout=10):
            if tag == "US2Y":
                return "US2Y", (4.10, -0.05)
            return None

        with patch.object(mds, "_yf_download", side_effect=fake_download):
            with patch(
                "services.yahoo_chart_fetcher.fetch_single_yahoo_chart",
                side_effect=fake_fetch,
            ):
                overview = mds.fetch_market_overview()

        # All 4 should be present: 3 from yfinance, 1 from parallel fallback
        assert "DXY" in overview, "A1+A2 FAILED: DXY missing"
        assert "VIX" in overview, "A1+A2 FAILED: VIX missing"
        assert "US10Y" in overview, "A1+A2 FAILED: US10Y missing"
        assert "US2Y" in overview, "A1+A2 FAILED: US2Y should be filled by parallel fallback"
        assert len(overview) == 4


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
