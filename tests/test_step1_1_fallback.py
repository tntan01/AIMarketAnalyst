"""Test script for Step 1.1 — yfinance fallback to _fetch_via_requests.

Usage: python tests/test_step1_1_fallback.py
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from services.market_data_service import (
    _fetch_via_requests,
    fetch_macro_correlation_context,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_chart_response(timestamps, closes, opens=None, highs=None, lows=None, volumes=None):
    """Build a Yahoo Finance chart API JSON string."""
    n = len(timestamps)
    body = {
        "chart": {
            "result": [
                {
                    "timestamp": timestamps,
                    "indicators": {
                        "quote": [
                            {
                                "open": opens if opens else [None] * n,
                                "high": highs if highs else [None] * n,
                                "low": lows if lows else [None] * n,
                                "close": closes,
                                "volume": volumes if volumes else [None] * n,
                            }
                        ]
                    },
                }
            ]
        }
    }
    return json.dumps(body)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [10, 20],
        },
        index=pd.to_datetime(["2026-06-15", "2026-06-16"]),
    )


# ---------------------------------------------------------------------------
# Tests for _fetch_via_requests
# ---------------------------------------------------------------------------


def test_fetch_via_requests_returns_candles():
    """Valid chart response -> list[Candle]."""
    ts1 = int(datetime(2026, 7, 1).timestamp())
    ts2 = int(datetime(2026, 7, 2).timestamp())
    body = _make_chart_response(
        timestamps=[ts1, ts2],
        closes=[101.0, 102.0],
        opens=[100.0, 101.0],
        highs=[102.0, 103.0],
        lows=[99.0, 100.0],
        volumes=[1000, 2000],
    )
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(body)

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        candles = _fetch_via_requests("DX-Y.NYB", period="5d")

    assert candles is not None
    assert len(candles) == 2
    assert candles[0].close == 101.0
    assert candles[0].volume == 1000.0
    assert candles[1].close == 102.0
    assert candles[1].volume == 2000.0
    assert candles[1].time == datetime(2026, 7, 2)


def test_fetch_via_requests_handles_null_ohlc():
    """Missing open/high/low fall back to close value."""
    ts1 = int(datetime(2026, 7, 1).timestamp())
    body = _make_chart_response(timestamps=[ts1], closes=[105.0])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(body)

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        candles = _fetch_via_requests("^VIX")

    assert candles is not None
    assert len(candles) == 1
    c = candles[0]
    assert c.open == 105.0
    assert c.high == 105.0
    assert c.low == 105.0
    assert c.close == 105.0
    assert c.volume == 0.0


def test_fetch_via_requests_skips_rows_without_close():
    """Rows where close is None are skipped."""
    ts1 = int(datetime(2026, 7, 1).timestamp())
    ts2 = int(datetime(2026, 7, 2).timestamp())
    body = _make_chart_response(timestamps=[ts1, ts2], closes=[None, 102.0])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(body)

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        candles = _fetch_via_requests("^TNX")

    assert candles is not None
    assert len(candles) == 1
    assert candles[0].close == 102.0


def test_fetch_via_requests_http_429_retries():
    """HTTP 429 is retried once after sleep."""
    ts1 = int(datetime(2026, 7, 1).timestamp())
    body = _make_chart_response(timestamps=[ts1], closes=[99.0])
    bad_resp = MagicMock()
    bad_resp.status_code = 429
    good_resp = MagicMock()
    good_resp.status_code = 200
    good_resp.json.return_value = json.loads(body)

    with patch(
        "services.market_data_service.requests.get",
        side_effect=[bad_resp, good_resp],
    ) as mock_get:
        with patch("time.sleep", return_value=None):
            candles = _fetch_via_requests("2YY=F")

    assert mock_get.call_count == 2
    assert candles is not None
    assert candles[0].close == 99.0


def test_fetch_via_requests_non_200_returns_none():
    """Non-200 (and not 429) -> None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        candles = _fetch_via_requests("DX-Y.NYB")

    assert candles is None


def test_fetch_via_requests_empty_result_returns_none():
    """Empty chart.result -> None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"chart": {"result": []}}

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        candles = _fetch_via_requests("DX-Y.NYB")

    assert candles is None


def test_fetch_via_requests_no_indicators_returns_none():
    """Missing indicators -> None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"chart": {"result": [{"timestamp": [123]}]}}

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        candles = _fetch_via_requests("DX-Y.NYB")

    assert candles is None


def test_fetch_via_requests_network_error_returns_none():
    """requests.get raises -> None, no exception propagated."""
    with patch("services.market_data_service.requests.get", side_effect=ConnectionError("no net")):
        candles = _fetch_via_requests("DX-Y.NYB")

    assert candles is None


def test_fetch_via_requests_invalid_json_returns_none():
    """Malformed JSON -> None."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("bad json")

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        candles = _fetch_via_requests("DX-Y.NYB")

    assert candles is None


# ---------------------------------------------------------------------------
# Tests for fetch_macro_correlation_context fallback
# ---------------------------------------------------------------------------


def test_fetch_context_fallback_when_yfinance_raises():
    """When yfinance download raises, fallback to _fetch_via_requests."""
    ts1 = int(datetime(2026, 7, 1).timestamp())
    ts2 = int(datetime(2026, 7, 2).timestamp())
    body = _make_chart_response(timestamps=[ts1, ts2], closes=[101.0, 102.0])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(body)

    def failing_download(ticker, **_kwargs):
        raise RuntimeError("yfinance not installed")

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        context = fetch_macro_correlation_context(
            downloader=failing_download, force_refresh=True
        )

    assert context["dxy_candles"] is not None
    assert len(context["dxy_candles"]) == 2
    assert context["dxy_candles"][-1].close == 102.0
    assert context["vix_candles"] is not None
    assert context["us10y_candles"] is not None
    assert context["us2y_candles"] is not None


def test_fetch_context_fallback_when_yfinance_returns_empty():
    """When yfinance returns empty DataFrame, fallback to _fetch_via_requests."""
    ts1 = int(datetime(2026, 7, 1).timestamp())
    body = _make_chart_response(timestamps=[ts1], closes=[105.0])
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(body)

    def empty_download(ticker, **_kwargs):
        return pd.DataFrame()  # empty -> parse_yf_candles returns None

    with patch("services.market_data_service.requests.get", return_value=mock_resp):
        context = fetch_macro_correlation_context(
            downloader=empty_download, force_refresh=True
        )

    assert context["dxy_candles"] is not None
    assert len(context["dxy_candles"]) == 1
    assert context["dxy_candles"][0].close == 105.0


def test_fetch_context_no_fallback_when_yfinance_succeeds():
    """Normal path: yfinance returns valid data, fallback is NOT called."""
    def good_download(ticker, **_kwargs):
        return _sample_frame()

    with patch("services.market_data_service._fetch_via_requests") as mock_fallback:
        context = fetch_macro_correlation_context(
            downloader=good_download, force_refresh=True
        )

    # fallback should never be called
    mock_fallback.assert_not_called()
    assert context["dxy_candles"] is not None
    assert context["dxy_candles"][-1].close == 102.0


def test_fetch_context_fallback_returns_none_on_double_failure():
    """If both yfinance AND requests API fail, None is stored for that key."""
    def failing_download(ticker, **_kwargs):
        raise RuntimeError("yfinance crash")

    with patch(
        "services.market_data_service.requests.get",
        side_effect=ConnectionError("no net"),
    ):
        context = fetch_macro_correlation_context(
            downloader=failing_download, force_refresh=True
        )

    # All 4 keys still present but values are None
    assert "dxy_candles" in context
    assert context["dxy_candles"] is None
    assert "vix_candles" in context
    assert context["vix_candles"] is None


def test_fetch_context_cache_still_works():
    """Cache is not broken by fallback logic."""
    def good_download(ticker, **_kwargs):
        return _sample_frame()

    ctx1 = fetch_macro_correlation_context(downloader=good_download, force_refresh=True)
    # second call without force_refresh should hit cache
    ctx2 = fetch_macro_correlation_context(downloader=good_download)
    assert ctx1 is ctx2  # same dict object from cache


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tests = [
        # _fetch_via_requests
        test_fetch_via_requests_returns_candles,
        test_fetch_via_requests_handles_null_ohlc,
        test_fetch_via_requests_skips_rows_without_close,
        test_fetch_via_requests_http_429_retries,
        test_fetch_via_requests_non_200_returns_none,
        test_fetch_via_requests_empty_result_returns_none,
        test_fetch_via_requests_no_indicators_returns_none,
        test_fetch_via_requests_network_error_returns_none,
        test_fetch_via_requests_invalid_json_returns_none,
        # fetch_macro_correlation_context fallback
        test_fetch_context_fallback_when_yfinance_raises,
        test_fetch_context_fallback_when_yfinance_returns_empty,
        test_fetch_context_no_fallback_when_yfinance_succeeds,
        test_fetch_context_fallback_returns_none_on_double_failure,
        test_fetch_context_cache_still_works,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"FAIL  {test.__name__}: {e}")
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} PASS, {failed} FAIL out of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
