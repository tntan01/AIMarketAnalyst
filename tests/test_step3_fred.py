"""Test script for Step 3 — FRED API auto-update interest rates.

Usage: python tests/test_step3_fred.py
"""

from __future__ import annotations

import json
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch

from services.interest_rate_service import (
    _load_fallback,
    _fetch_from_fred,
    get_latest_rates,
    FRED_SERIES,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

SAMPLE_FALLBACK = {
    "USD": {
        "central_bank": "Federal Reserve",
        "rate": 5.50,
        "rate_label": "5.25-5.50%",
        "trend": "hold",
    },
    "EUR": {
        "central_bank": "ECB",
        "rate": 2.50,
        "rate_label": "2.50%",
        "trend": "cut",
    },
}


def _fred_obs_response(value1: str, value2: str, date1: str = "2026-06-15", date2: str = "2026-05-15"):
    """Build a FRED API observations JSON string."""
    return json.dumps({
        "observations": [
            {"date": date1, "value": value1},
            {"date": date2, "value": value2},
        ]
    })


# ---------------------------------------------------------------------------
# _load_fallback
# ---------------------------------------------------------------------------


def test_load_fallback_returns_currencies():
    """Fallback reads from interest_rates.json successfully."""
    rates = _load_fallback()
    assert "USD" in rates
    assert "EUR" in rates
    assert "rate" in rates["USD"]
    assert rates["USD"]["central_bank"] == "Federal Reserve"


def test_load_fallback_file_missing_returns_empty():
    """If JSON file doesn't exist, returns {}."""
    with patch("pathlib.Path.read_text", side_effect=FileNotFoundError):
        rates = _load_fallback()
        assert rates == {}


# ---------------------------------------------------------------------------
# get_latest_rates — fallback path (no API key)
# ---------------------------------------------------------------------------


def test_get_latest_rates_no_key_uses_fallback():
    """Without FRED key, returns data from JSON fallback."""
    rates = get_latest_rates(fred_api_key=None)
    assert "USD" in rates
    assert "rate" in rates["USD"]


def test_get_latest_rates_empty_key_uses_fallback():
    """Empty string key -> fallback."""
    rates = get_latest_rates(fred_api_key="")
    assert "USD" in rates


# ---------------------------------------------------------------------------
# get_latest_rates — cache
# ---------------------------------------------------------------------------


def test_get_latest_rates_cache_works():
    """Second call within TTL returns cached result."""
    import services.interest_rate_service as svc
    svc._CACHE = None
    svc._CACHE_TIME = None

    rates1 = get_latest_rates(fred_api_key=None)
    assert "USD" in rates1

    # Modify cache to verify second call hits cache
    svc._CACHE = {"USD": {"rate": 99.99, "trend": "test"}}
    svc._CACHE_TIME = datetime.now(UTC)
    rates2 = get_latest_rates(fred_api_key=None)
    assert rates2["USD"]["rate"] == 99.99

    # Cleanup
    svc._CACHE = None
    svc._CACHE_TIME = None


# ---------------------------------------------------------------------------
# _fetch_from_fred — successful fetch
# ---------------------------------------------------------------------------


def test_fetch_from_fred_updates_rates():
    """FRED returns valid data -> rates are updated from FRED."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(
        _fred_obs_response("5.75", "5.50")
    )

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    assert rates["USD"]["rate"] == 5.75
    assert rates["USD"]["rate_label"] == "5.75%"
    assert rates["USD"]["trend"] == "hike"  # 5.75 > 5.50 + 0.1
    assert rates["USD"]["_source"] == "FRED"


def test_fetch_from_fred_trend_hold():
    """Small rate change (<0.1) -> trend 'hold'."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(
        _fred_obs_response("5.55", "5.50")
    )

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    assert rates["USD"]["trend"] == "hold"


def test_fetch_from_fred_trend_cut():
    """Rate decrease >0.1 -> trend 'cut'."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(
        _fred_obs_response("5.00", "5.50")
    )

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    assert rates["USD"]["trend"] == "cut"


def test_fetch_from_fred_single_observation():
    """Only 1 valid observation -> prev_rate = latest_rate."""
    body = json.dumps({
        "observations": [
            {"date": "2026-06-15", "value": "5.50"},
            {"date": "2026-05-15", "value": "."},  # invalid
        ]
    })
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(body)

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    assert rates["USD"]["rate"] == 5.50
    assert rates["USD"]["trend"] == "hold"  # no change


def test_fetch_from_fred_keeps_fallback_fields():
    """FRED merge preserves fields from fallback not in FRED response."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(
        _fred_obs_response("5.75", "5.50")
    )

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    assert rates["USD"]["central_bank"] == "Federal Reserve"  # from fallback


# ---------------------------------------------------------------------------
# _fetch_from_fred — error handling
# ---------------------------------------------------------------------------


def test_fetch_from_fred_bad_status_skips_currency():
    """Non-200 status -> currency skipped, fallback value kept."""
    mock_resp = MagicMock()
    mock_resp.status_code = 500

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    # Fallback data preserved
    assert rates["USD"]["rate"] == 5.50


def test_fetch_from_fred_network_error_skips_currency():
    """Network error -> currency skipped, not crash."""
    with patch("services.interest_rate_service.requests.get",
               side_effect=ConnectionError("no net")):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    assert "USD" in rates


def test_fetch_from_fred_no_observations_skips():
    """Empty observations list -> currency skipped."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"observations": []}

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = _fetch_from_fred("valid_key")

    assert rates is not None
    assert "USD" in rates


# ---------------------------------------------------------------------------
# get_latest_rates — FRED path
# ---------------------------------------------------------------------------


def test_get_latest_rates_with_valid_key_uses_fred():
    """With valid API key, FRED data is used."""
    import services.interest_rate_service as svc
    svc._CACHE = None
    svc._CACHE_TIME = None

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = json.loads(
        _fred_obs_response("5.75", "5.50")
    )

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        with patch("services.interest_rate_service._load_fallback", return_value=dict(SAMPLE_FALLBACK)):
            rates = get_latest_rates(fred_api_key="valid_key")

    assert rates["USD"]["rate"] == 5.75
    assert rates["USD"]["_source"] == "FRED"

    svc._CACHE = None
    svc._CACHE_TIME = None


def test_get_latest_rates_bad_key_falls_back():
    """Invalid API key -> FRED returns error -> fallback to JSON."""
    import services.interest_rate_service as svc
    svc._CACHE = None
    svc._CACHE_TIME = None

    mock_resp = MagicMock()
    mock_resp.status_code = 400  # bad API key

    with patch("services.interest_rate_service.requests.get", return_value=mock_resp):
        rates = get_latest_rates(fred_api_key="bad_key")

    # All currencies skipped in FRED, fallback data returned
    assert "USD" in rates
    assert rates["USD"]["rate"] == 3.75  # from current fallback config

    svc._CACHE = None
    svc._CACHE_TIME = None


def test_get_latest_rates_fred_exception_falls_back():
    """FRED raises exception -> catch, log, fallback."""
    import services.interest_rate_service as svc
    svc._CACHE = None
    svc._CACHE_TIME = None

    with patch("services.interest_rate_service._fetch_from_fred",
               side_effect=RuntimeError("API down")):
        rates = get_latest_rates(fred_api_key="valid_key")

    assert "USD" in rates

    svc._CACHE = None
    svc._CACHE_TIME = None


# ---------------------------------------------------------------------------
# FRED_SERIES map
# ---------------------------------------------------------------------------


def test_fred_series_has_all_currencies():
    """FRED_SERIES covers all currencies in interest_rates.json fallback."""
    fallback = _load_fallback()
    for currency in fallback:
        assert currency in FRED_SERIES, f"Missing FRED series for {currency}"


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tests = [
        # _load_fallback
        test_load_fallback_returns_currencies,
        test_load_fallback_file_missing_returns_empty,
        # get_latest_rates — fallback
        test_get_latest_rates_no_key_uses_fallback,
        test_get_latest_rates_empty_key_uses_fallback,
        # cache
        test_get_latest_rates_cache_works,
        # _fetch_from_fred — success
        test_fetch_from_fred_updates_rates,
        test_fetch_from_fred_trend_hold,
        test_fetch_from_fred_trend_cut,
        test_fetch_from_fred_single_observation,
        test_fetch_from_fred_keeps_fallback_fields,
        # _fetch_from_fred — errors
        test_fetch_from_fred_bad_status_skips_currency,
        test_fetch_from_fred_network_error_skips_currency,
        test_fetch_from_fred_no_observations_skips,
        # get_latest_rates — FRED path
        test_get_latest_rates_with_valid_key_uses_fred,
        test_get_latest_rates_bad_key_falls_back,
        test_get_latest_rates_fred_exception_falls_back,
        # FRED_SERIES
        test_fred_series_has_all_currencies,
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
