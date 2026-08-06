"""Phase 2A cache-contract tests for macro contexts."""

from __future__ import annotations

import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from threading import Barrier, Event, Thread
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from services.macro_market_cache import MacroMarketCache, reset_shared_cache, set_shared_cache
from services.market_data_service import fetch_macro_correlation_context
from services.news_service import MacroGlobalSnapshot, NewsService


def _snapshot() -> MacroGlobalSnapshot:
    now = datetime.now(UTC)
    return MacroGlobalSnapshot(
        fetched_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
        tnx=4.1,
        fvx=4.0,
        yield_spread_10y_5y=0.1,
        yield_steepening=True,
        vix=18.0,
        global_headlines=(),
        official_statements=(),
        calendar_payload={"events": [], "source": "frozen", "warning": ""},
        source_status={
            name: {
                "status": "fresh",
                "source": name,
                "checked_at_utc": now.isoformat(),
                "data_fetched_at_utc": now.isoformat(),
            }
            for name in ("^TNX", "^FVX", "^VIX", "global_headlines", "official_statements", "calendar")
        },
        stale_fields=(),
    )


def _context(symbol: str) -> dict[str, object]:
    return {
        "symbol": symbol,
        "source": "frozen",
        "events": [],
        "macro_alignment_scores": {"buy": 15, "sell": 15},
    }


class _FakeAI:
    def __init__(self, provider: str, model: str, api_key: str = "TOP-SECRET") -> None:
        self.config = SimpleNamespace(provider=provider, model=model, api_key=api_key)


def _stub_builder(service: NewsService, monkeypatch: pytest.MonkeyPatch) -> Mock:
    builder = Mock(side_effect=lambda symbol, *_args, **_kwargs: _context(symbol))
    monkeypatch.setattr(service, "_build_macro_context", builder)
    monkeypatch.setattr(service, "_get_global_macro_snapshot", lambda **_kwargs: _snapshot())
    return builder


def test_preload_and_ai_consumer_use_the_same_canonical_key(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    builder = _stub_builder(service, monkeypatch)
    ai = _FakeAI("deepseek", "deepseek-chat")

    service.preload_macro_contexts(["EUR/USD"], ai_service=ai)
    flags = service.data_quality_flags("EUR/USD", ai_service=ai)

    assert flags["macro_context"]["symbol"] == "EUR/USD"
    assert builder.call_count == 1
    assert len(service._tier_scores_cache) == 1


def test_ai_fingerprint_has_provider_model_enabled_but_never_secret():
    secret = "sk-this-must-never-enter-a-cache-key"
    ai = _FakeAI("provider-a", "model-a", secret)
    fingerprint = NewsService._ai_fingerprint(ai)
    key = NewsService._macro_context_cache_key("EUR/USD", True, fingerprint)

    assert "provider-a" in fingerprint
    assert "model-a" in fingerprint
    assert '"enabled":true' in fingerprint
    assert secret not in fingerprint
    assert secret not in key


def test_ai_disabled_and_provider_or_model_changes_are_independent_misses(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    builder = _stub_builder(service, monkeypatch)

    service.latest_macro_context("EUR/USD")
    service.latest_macro_context("EUR/USD", ai_service=_FakeAI("a", "m1"))
    service.latest_macro_context("EUR/USD", ai_service=_FakeAI("a", "m2"))
    service.latest_macro_context("EUR/USD", ai_service=_FakeAI("b", "m2"))

    assert builder.call_count == 4
    assert len(service._tier_scores_cache) == 4


def test_within_ttl_hits_and_consumer_mutation_cannot_corrupt_entry(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    builder = _stub_builder(service, monkeypatch)

    first = service.latest_macro_context("EUR/USD")
    first["events"].append({"event": "consumer mutation"})
    first["macro_alignment_scores"]["buy"] = 999
    second = service.latest_macro_context("EUR/USD")

    assert builder.call_count == 1
    assert second["events"] == []
    assert second["macro_alignment_scores"] == {"buy": 15, "sell": 15}


def test_expired_entry_recomputes_and_retains_ttl_provenance(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    builder = _stub_builder(service, monkeypatch)
    first = service.latest_macro_context("EUR/USD")
    fingerprint = service._ai_fingerprint(None)
    key = service._macro_context_cache_key("EUR/USD", True, fingerprint)
    entry = service._tier_scores_cache[key]
    service._tier_scores_cache[key] = replace(
        entry,
        expires_at_utc=datetime.now(UTC) - timedelta(seconds=1),
    )

    second = service.latest_macro_context("EUR/USD")

    assert builder.call_count == 2
    metadata = second["macro_cache"]
    assert metadata["ai_fingerprint"] == fingerprint
    assert metadata["source_freshness"]["source_status"]["^TNX"]["status"] == "fresh"
    assert datetime.fromisoformat(metadata["expires_at_utc"]) > datetime.fromisoformat(metadata["fetched_at_utc"])
    assert first["macro_alignment_scores"] == second["macro_alignment_scores"]


def test_build_exception_does_not_poison_cache(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    monkeypatch.setattr(service, "_get_global_macro_snapshot", lambda **_kwargs: _snapshot())
    builder = Mock(side_effect=[RuntimeError("frozen failure"), _context("EUR/USD")])
    monkeypatch.setattr(service, "_build_macro_context", builder)

    with pytest.raises(RuntimeError, match="frozen failure"):
        service.latest_macro_context("EUR/USD")
    assert service._tier_scores_cache == {}

    assert service.latest_macro_context("EUR/USD")["symbol"] == "EUR/USD"
    assert builder.call_count == 2


# ============================================================================
# Phase 2B Integration — full scanner flow with concurrent correlation + news
# ============================================================================

SYMBOLS_28 = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "NZD/USD", "USD/CAD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/NZD", "EUR/CAD", "GBP/JPY",
    "GBP/CHF", "GBP/AUD", "GBP/NZD", "GBP/CAD", "AUD/JPY", "AUD/CHF", "AUD/NZD",
    "AUD/CAD", "NZD/JPY", "NZD/CHF", "NZD/CAD", "CAD/JPY", "CAD/CHF", "CHF/JPY",
]


def _frame(values: list[float] | None = None) -> pd.DataFrame:
    """Return a DataFrame with full OHLCV columns and a datetime index.

    parse_yf_candles() requires Open, High, Low, Close, Volume columns.
    Without them it returns None, triggering an unintended _fetch_via_requests
    HTTP fallback.
    """
    vals = values or [4.0, 4.1]
    index = pd.to_datetime(["2026-07-30", "2026-07-31"])
    return pd.DataFrame(
        {
            "Open": vals,
            "High": [v + 0.05 for v in vals],
            "Low": [v - 0.05 for v in vals],
            "Close": vals,
            "Volume": [1000000, 1100000],
        },
        index=index,
    )


def _collection_result(value: list[dict[str, object]], **kw: object) -> dict[str, object]:
    result: dict[str, object] = {"status": "fresh", "value": value, "attempted_sources": 1, "successful_sources": 1, "error_types": []}
    result.update(kw)
    return result


def _patch_no_http_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent any test from accidentally making real HTTP fallback calls."""
    import services.market_data_service as mds

    monkeypatch.setattr(
        mds,
        "_fetch_via_requests",
        lambda ticker, period="5d": pytest.fail(
            f"Unexpected HTTP fallback for {ticker}"
        ),
    )


@pytest.fixture(autouse=True)
def _reset_shared_cache():
    reset_shared_cache()
    yield
    reset_shared_cache()


def _fresh_cache_and_service() -> tuple[MacroMarketCache, NewsService]:
    """Return a MacroMarketCache (set as singleton) and a fresh NewsService."""
    cache = MacroMarketCache()
    set_shared_cache(cache)
    service = NewsService()
    # Neutralize non-yahoo sources so only ticker downloads are tracked.
    service._interest_rates = {}
    return cache, service


def _patch_service_sources(service: NewsService):
    return (
        Mock(return_value={"events": [], "source": "frozen", "warning": ""}),
        Mock(return_value=_collection_result([])),
        Mock(return_value=_collection_result([])),
    )


# ============================================================================
# Integration Tests — full scanner flow
# ============================================================================

# All mocks must accept the new downloader signature:
#   (ticker, *, period, interval)
# since _fetch() calls self._downloader(ticker, period=period, interval=interval)

def _mock_download(*, calls: list[str], values: list[float] | None = None):
    """Factory: returns a downloader that records ticker + returns a valid OHLCV frame."""
    def _download(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        return _frame(values)
    return _download


def _mock_raise(error: type[Exception] = RuntimeError, msg: str = "offline"):
    """Factory: returns a downloader that always raises."""
    def _download(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        raise error(msg)
    return _download


def _wait_for_flight_waiters(
    cache: MacroMarketCache,
    cache_key: tuple[str, str, str],
    *,
    expected: int = 1,
    timeout: float = 5.0,
) -> None:
    """Wait for observable join state instead of relying on scheduler sleeps."""
    deadline = time.monotonic() + timeout
    while True:
        with cache._attempts_lock:
            state = cache._attempts.get(cache_key)
            joined = bool(
                state is not None
                and state.in_flight
                and state.active_flight is not None
                and state.active_flight.waiters >= expected
            )
        if joined:
            return
        if time.monotonic() >= deadline:
            pytest.fail(
                f"expected {expected} waiter(s) to join active flight {cache_key!r}"
            )
        time.sleep(0.001)


def _mock_split_download(
    *,
    calls: list[str],
    ok_tickers: set[str],
    fail_tickers: set[str],
    values: list[float] | None = None,
):
    """Factory: succeeds for ok_tickers, raises for fail_tickers."""
    def _download(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        if ticker in fail_tickers:
            raise RuntimeError(f"offline for {ticker}")
        return _frame(values)
    return _download


# ------------------------------------------------------------------
# Test A — Full concurrent scanner prefetch
# ------------------------------------------------------------------
def test_full_scanner_concurrent_cold_each_ticker_once(monkeypatch: pytest.MonkeyPatch):
    """Simulate scanner controller: fetch_macro_correlation_context + preload.

    Both run concurrently. Each Yahoo ticker must be downloaded exactly once.
    HTTP fallback must be 0.
    """
    cache, service = _fresh_cache_and_service()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    _patch_no_http_fallback(monkeypatch)

    cal_mock, headlines_mock, statements_mock = _patch_service_sources(service)

    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls)
    monkeypatch.setattr(service, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service, "_latest_official_statements_with_status", statements_mock)

    # Reset module-level correlation cache
    import services.market_data_service as mds
    mds._CORRELATION_CACHE = None
    mds._CORRELATION_CACHE_TIME = None
    mds._CORRELATION_CACHE_KEY = None

    with ThreadPoolExecutor(max_workers=2) as ex:
        corr_future = ex.submit(fetch_macro_correlation_context, _macro_cache=cache)
        preload_future = ex.submit(service.preload_macro_contexts, SYMBOLS_28)
        corr = corr_future.result()
        preload_future.result()

    counts = Counter(calls)
    assert counts == Counter({"^TNX": 1, "^FVX": 1, "^VIX": 1, "DX-Y.NYB": 1, "2YY=F": 1})
    assert len(calls) == 5

    # Correlation context has all 4 keys populated
    assert corr["dxy_candles"] is not None
    assert corr["vix_candles"] is not None
    assert corr["us10y_candles"] is not None
    assert corr["us2y_candles"] is not None


def test_full_scanner_concurrent_warm_within_ttl_zero_network_delta(monkeypatch: pytest.MonkeyPatch):
    """After preload, 28× data_quality_flags + second scan = zero additional downloads."""
    cache, service = _fresh_cache_and_service()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    _patch_no_http_fallback(monkeypatch)

    cal_mock, headlines_mock, statements_mock = _patch_service_sources(service)

    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls)
    monkeypatch.setattr(service, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service, "_latest_official_statements_with_status", statements_mock)

    # Cold scan
    service.preload_macro_contexts(SYMBOLS_28)
    cold_count = len(calls)
    calls.clear()

    # 28 data_quality_flags — must be cache hits
    for symbol in SYMBOLS_28:
        service.data_quality_flags(symbol)
    assert len(calls) == 0
    assert cold_count == 3  # ^TNX, ^FVX, ^VIX

    # Warm scan (second service, same shared cache)
    service2 = NewsService()
    monkeypatch.setattr(service2, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service2, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service2, "_latest_official_statements_with_status", statements_mock)

    service2.preload_macro_contexts(SYMBOLS_28)
    for symbol in SYMBOLS_28:
        service2.data_quality_flags(symbol)

    assert len(calls) == 0


# ------------------------------------------------------------------
# Test B — Consumer-order tests
# ------------------------------------------------------------------
def test_correlation_first_then_news_scoring_parity(monkeypatch: pytest.MonkeyPatch):
    """Correlation-first order: TNX/FVX/VIX fresh, scoring unchanged.

    Frozen fixture: TNX=[4.506, 4.507], FVX=[4.000, 4.000], VIX=[18, 18]
    Expected: Tier1=3/5, Tier2=5/5, Tier3=6/6, alignment=14/16
    """
    import services.market_data_service as mds
    mds._CORRELATION_CACHE = None
    mds._CORRELATION_CACHE_TIME = None
    mds._CORRELATION_CACHE_KEY = None

    cache, service = _fresh_cache_and_service()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    _patch_no_http_fallback(monkeypatch)

    frames = {
        "^TNX": _frame([4.506, 4.507]),
        "^FVX": _frame([4.000, 4.000]),
        "^VIX": _frame([18.0, 18.0]),
        "DX-Y.NYB": _frame([104.0, 105.0]),
        "2YY=F": _frame([4.3, 4.4]),
    }

    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls)

    # Override with specific frames per ticker
    def _framed_download(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        return frames.get(ticker, _frame())

    cache._downloader = _framed_download

    cal_mock, headlines_mock, statements_mock = _patch_service_sources(service)
    monkeypatch.setattr(service, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service, "_latest_official_statements_with_status", statements_mock)

    # Correlation FIRST
    corr = fetch_macro_correlation_context(force_refresh=True, _macro_cache=cache)
    assert corr["us10y_candles"] is not None
    assert corr["vix_candles"] is not None

    # News SECOND — must use same cached frames, no new downloads
    calls.clear()
    service.preload_macro_contexts(SYMBOLS_28)
    # Preload uses the shared cache → zero new downloads for TNX/FVX/VIX
    # But DXY and IRX are only in correlation, not preload. So preload only
    # calls ^TNX, ^FVX, ^VIX which are already cached.
    tnx_fvx_vix_calls = [c for c in calls if c in {"^TNX", "^FVX", "^VIX"}]
    # ^TNX and ^VIX were cached by correlation -> zero new downloads.
    # ^FVX is only used by NewsService -> one fresh download.
    assert "^TNX" not in calls
    assert "^VIX" not in calls
    assert Counter(calls) == Counter({"^FVX": 1})

    snapshot = service._get_global_macro_snapshot()
    assert snapshot.yield_spread_10y_5y == 0.51  # 4.507 - 4.000 = 0.507, rounded
    assert snapshot.yield_steepening is True

    result = service._compute_macro_tiers(
        "EUR/USD", ["EUR", "USD"], [], [], [], [],
        ai_service=None, global_snapshot=snapshot,
    )
    assert {k: result["tier1"][k] for k in ("buy", "sell")} == {"buy": 3, "sell": 5}
    assert {k: result["tier2"][k] for k in ("buy", "sell")} == {"buy": 5, "sell": 5}
    assert {k: result["tier3"][k] for k in ("buy", "sell")} == {"buy": 6, "sell": 6}
    assert result["raw_total"] == {"buy": 14, "sell": 16}
    assert result["alignment"] == {"buy": 14, "sell": 16}


def test_news_first_then_correlation_same_generation_and_scoring(monkeypatch: pytest.MonkeyPatch):
    """News-first order: same data generation, same scoring, no TypeError."""
    import services.market_data_service as mds
    mds._CORRELATION_CACHE = None
    mds._CORRELATION_CACHE_TIME = None
    mds._CORRELATION_CACHE_KEY = None

    cache, service = _fresh_cache_and_service()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    _patch_no_http_fallback(monkeypatch)

    frames = {
        "^TNX": _frame([4.506, 4.507]),
        "^FVX": _frame([4.000, 4.000]),
        "^VIX": _frame([18.0, 18.0]),
        "DX-Y.NYB": _frame([104.0, 105.0]),
        "2YY=F": _frame([4.3, 4.4]),
    }

    calls: list[str] = []
    def _framed_download(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        return frames.get(ticker, _frame())
    cache._downloader = _framed_download

    cal_mock, headlines_mock, statements_mock = _patch_service_sources(service)
    monkeypatch.setattr(service, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service, "_latest_official_statements_with_status", statements_mock)

    # News FIRST
    snapshot = service._get_global_macro_snapshot()
    assert snapshot.yield_spread_10y_5y == 0.51
    assert snapshot.yield_steepening is True

    result_news = service._compute_macro_tiers(
        "EUR/USD", ["EUR", "USD"], [], [], [], [],
        ai_service=None, global_snapshot=snapshot,
    )
    assert result_news["alignment"] == {"buy": 14, "sell": 16}

    # Correlation SECOND — must use same frames
    corr = fetch_macro_correlation_context(force_refresh=True, _macro_cache=cache)
    assert corr["us10y_candles"] is not None
    assert corr["vix_candles"] is not None

    # Recompute with the same snapshot → identical scoring
    result_corr = service._compute_macro_tiers(
        "EUR/USD", ["EUR", "USD"], [], [], [], [],
        ai_service=None, global_snapshot=snapshot,
    )
    for key in ("tier1", "tier2", "tier3", "raw_total", "alignment", "reasons", "macro_v2"):
        assert result_news[key] == result_corr[key]


# ------------------------------------------------------------------
# Test C — Cache contract tests
# ------------------------------------------------------------------
def test_different_periods_are_independent_misses():
    """5d/1d and 1mo/1h are independent cache entries."""
    cache = MacroMarketCache()
    set_shared_cache(cache)

    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls, values=[4.0, 4.1])

    cache.get_frame("^TNX", period="5d", interval="1d")
    assert len(calls) == 1
    calls.clear()

    cache.get_frame("^TNX", period="5d", interval="1d")
    assert len(calls) == 0  # cache hit

    cache.get_frame("^TNX", period="1mo", interval="1h")
    assert len(calls) == 1  # new key → new download

    cache.get_frame("^TNX", period="5d", interval="1d")
    assert len(calls) == 1  # still 1 (different key was downloaded, original key still cached)


def test_within_ttl_hit_expired_refreshes():
    """Within TTL = hit, expired = one refresh."""
    now = datetime.now(UTC)
    cache = MacroMarketCache(ttl=timedelta(seconds=1))
    set_shared_cache(cache)

    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls)

    cache.get_frame("^TNX", now=now)
    assert len(calls) == 1  # cold

    cache.get_frame("^TNX", now=now + timedelta(seconds=0.5))
    assert len(calls) == 1  # still within TTL → hit

    cache.get_frame("^TNX", now=now + timedelta(seconds=2))
    assert len(calls) == 2  # expired → refresh


def test_force_refresh_bypasses_ttl_but_still_single_flight(monkeypatch: pytest.MonkeyPatch):
    """force_refresh=True triggers a real download even if within TTL.

    Two concurrent force-refresh requests for the same key = single network call.
    """
    cache = MacroMarketCache(ttl=timedelta(minutes=5))
    set_shared_cache(cache)
    _patch_no_http_fallback(monkeypatch)

    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls)

    # Cold fill
    cache.get_frame("^TNX")
    assert len(calls) == 1
    calls.clear()

    # force_refresh → bypasses TTL, downloads again
    cache.get_frame("^TNX", force_refresh=True)
    assert len(calls) == 1  # one new download

    # Two concurrent force refreshes → single flight
    calls.clear()
    start_event = Event()
    entered = Event()

    def _slow_download(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        entered.set()
        start_event.wait()
        return _frame()

    cache._downloader = _slow_download

    results: list[object] = [None, None]
    def _t0():
        results[0] = cache.get_frame("^TNX", force_refresh=True)
    def _t1():
        results[1] = cache.get_frame("^TNX", force_refresh=True)

    t0 = Thread(target=_t0); t1 = Thread(target=_t1)
    t0.start(); entered.wait(timeout=5); t1.start()
    _wait_for_flight_waiters(cache, ("^TNX", "5d", "1d"))
    start_event.set()
    t0.join(timeout=5); t1.join(timeout=5)

    assert len(calls) == 1
    assert results[0] is not None
    assert results[0].equals(results[1])


def test_two_force_callers_prequeued_on_key_lock_share_one_download():
    """Ownership is published before either force caller can acquire key lock."""
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)
    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    cache.get_scalar("^TNX", now=t0)

    cache_key = ("^TNX", "5d", "1d")
    key_lock = cache._get_key_lock(cache_key)
    key_lock.acquire()
    released = False
    start = Barrier(3)
    calls: list[str] = []

    def download(ticker: str, *, period: str = "5d", interval: str = "1d"):
        calls.append(ticker)
        return _frame([5.0, 5.1])

    cache._downloader = download
    results: list[dict | None] = [None, None]
    errors: list[BaseException] = []

    def force_caller(index: int) -> None:
        try:
            start.wait(timeout=5)
            results[index] = cache.get_scalar(
                "^TNX", now=t0 + timedelta(minutes=1), force_refresh=True
            )
        except BaseException as exc:  # surfaced explicitly after both joins
            errors.append(exc)

    threads = [Thread(target=force_caller, args=(index,)) for index in range(2)]
    try:
        for thread in threads:
            thread.start()
        start.wait(timeout=5)

        # Wait on observable flight state, not an arbitrary scheduling sleep:
        # one owner is blocked on key_lock and the other caller has joined it.
        deadline = time.monotonic() + 5
        while True:
            with cache._attempts_lock:
                state = cache._attempts[cache_key]
                joined = bool(
                    state.in_flight
                    and state.active_flight is not None
                    and state.active_flight.waiters == 1
                )
            if joined:
                break
            if time.monotonic() >= deadline:
                pytest.fail("force callers did not claim/join the same queued flight")
            time.sleep(0.001)

        assert calls == []  # owner cannot reach downloader while lock is held
        key_lock.release()
        released = True
    finally:
        if not released:
            key_lock.release()
        for thread in threads:
            thread.join(timeout=5)

    assert errors == []
    assert all(not thread.is_alive() for thread in threads)
    assert calls == ["^TNX"]
    assert cache.attempt_counts() == {"^TNX/5d/1d": 2}
    assert results[0] == results[1]
    assert results[0]["status"] == "fresh"


def test_distinct_canonical_keys_download_in_parallel():
    cache = MacroMarketCache()
    set_shared_cache(cache)
    entered = Barrier(2)
    calls: list[str] = []

    def download(ticker: str, *, period: str = "5d", interval: str = "1d"):
        calls.append(ticker)
        entered.wait(timeout=5)
        return _frame([4.0, 4.1])

    cache._downloader = download
    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(cache.get_frame, ("^TNX", "^FVX")))

    assert Counter(calls) == Counter({"^TNX": 1, "^FVX": 1})
    assert all(not frame.empty for frame in outcomes)


def test_concurrent_same_key_single_network_call(monkeypatch: pytest.MonkeyPatch):
    """Two threads requesting the same key concurrently = single download."""
    cache = MacroMarketCache()
    set_shared_cache(cache)
    _patch_no_http_fallback(monkeypatch)

    calls: list[str] = []
    start_event = Event()
    entered = Event()

    def _slow_download(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        entered.set()
        start_event.wait()
        return _frame()

    cache._downloader = _slow_download

    results: list[object] = [None, None]
    def _t0():
        results[0] = cache.get_frame("^TNX")
    def _t1():
        results[1] = cache.get_frame("^TNX")

    t0 = Thread(target=_t0); t1 = Thread(target=_t1)
    t0.start(); entered.wait(timeout=5); t1.start()
    _wait_for_flight_waiters(cache, ("^TNX", "5d", "1d"))
    start_event.set()
    t0.join(timeout=5); t1.join(timeout=5)

    assert len(calls) == 1
    assert results[0] is not None
    assert results[0].equals(results[1])


def test_error_with_valid_stale_returns_stale_with_full_provenance():
    """Download error + valid prior entry → stale data with origin timestamps."""
    now = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    # First successful download
    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    first = cache.get_scalar("^TNX", now=now)
    assert first["status"] == "fresh"
    assert first["value"] == 4.1
    assert first["previous"] == 4.0
    assert first["fetched_at_utc"] != ""
    assert first["expires_at_utc"] != ""

    # Second: download fails, within stale window
    cache._downloader = _mock_raise(RuntimeError, "offline")
    second = cache.get_scalar("^TNX", now=now + timedelta(minutes=6))

    assert second["status"] == "stale"
    assert second["value"] == 4.1  # same stale value
    assert second["previous"] == 4.0
    assert second["fetched_at_utc"] != ""
    assert second["expires_at_utc"] != ""
    assert second["checked_at_utc"] != ""
    assert second["cache_key"] == ["^TNX", "5d", "1d"]
    assert "refresh_error_type" in second
    assert second["refresh_error_type"] == "RuntimeError"


def test_error_outside_stale_window_is_unavailable():
    """Download error + stale window exceeded → unavailable, never fresh."""
    now = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    cache.get_scalar("^TNX", now=now)

    cache._downloader = _mock_raise(RuntimeError, "offline")
    result = cache.get_scalar("^TNX", now=now + timedelta(minutes=31))

    assert result["status"] == "unavailable"
    assert result["value"] is None
    assert result["error_type"] == "RuntimeError"


def test_retry_gate_never_extends_hard_stale_deadline_and_keeps_provenance():
    """At +31m the +30m data deadline wins even though retry is gated to +34m."""
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    cache = MacroMarketCache(
        ttl=timedelta(minutes=5),
        stale_if_error=timedelta(minutes=30),
        retry_ttl=timedelta(minutes=5),
    )
    set_shared_cache(cache)
    key = ("^TNX", "5d", "1d")

    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    fresh = cache.get_scalar("^TNX", now=t0)
    assert fresh["refresh_error_type"] == ""

    calls: list[str] = []

    def fail(ticker: str, *, period: str = "5d", interval: str = "1d"):
        calls.append(ticker)
        raise RuntimeError("offline")

    cache._downloader = fail
    failed_at = t0 + timedelta(minutes=29)
    stale = cache.get_scalar("^TNX", now=failed_at)
    expected_stale_provenance = {
        "cache_key": ["^TNX", "5d", "1d"],
        "checked_at_utc": failed_at.isoformat(),
        "data_fetched_at_utc": t0.isoformat(),
        "origin_expires_at_utc": (t0 + timedelta(minutes=5)).isoformat(),
        "next_retry_at_utc": (t0 + timedelta(minutes=34)).isoformat(),
        "refresh_error_type": "RuntimeError",
    }
    assert stale["status"] == "stale"
    assert {field: stale[field] for field in expected_stale_provenance} == expected_stale_provenance

    at_deadline = cache.get_scalar("^TNX", now=t0 + timedelta(minutes=30))
    assert at_deadline["status"] == "unavailable"
    assert at_deadline["value"] is None
    assert at_deadline["checked_at_utc"] == (t0 + timedelta(minutes=30)).isoformat()

    # Retry remains gated, so no downloader call occurs; nevertheless the data
    # is unavailable after its independent hard stale deadline.
    after_deadline = t0 + timedelta(minutes=31)
    unavailable = cache.get_scalar("^TNX", now=after_deadline)
    assert unavailable["status"] == "unavailable"
    assert unavailable["value"] is None
    assert unavailable["checked_at_utc"] == after_deadline.isoformat()
    for field in (
        "cache_key",
        "data_fetched_at_utc",
        "origin_expires_at_utc",
        "next_retry_at_utc",
        "refresh_error_type",
    ):
        assert unavailable[field] == expected_stale_provenance[field]
    assert calls == ["^TNX"]
    assert cache._attempts[key].attempts == 2


def test_failed_force_refresh_cannot_turn_stale_back_to_fresh_via_origin_ttl():
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    cache = MacroMarketCache(
        ttl=timedelta(minutes=10),
        stale_if_error=timedelta(minutes=30),
        retry_ttl=timedelta(minutes=5),
    )
    set_shared_cache(cache)
    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    cache.get_scalar("^TNX", now=t0)

    failed_calls: list[str] = []

    def fail(ticker: str, *, period: str = "5d", interval: str = "1d"):
        failed_calls.append(ticker)
        raise RuntimeError("offline")

    cache._downloader = fail
    failed_at = t0 + timedelta(minutes=1)
    failed_force = cache.get_scalar("^TNX", now=failed_at, force_refresh=True)
    assert failed_force["status"] == "stale"

    # Origin TTL remains valid until +10m, but the failed refresh state remains
    # stale and retry-gated; it is never relabelled fresh without a success.
    during_gate = cache.get_scalar("^TNX", now=t0 + timedelta(minutes=2))
    assert during_gate["status"] == "stale"
    assert during_gate["refresh_error_type"] == "RuntimeError"
    assert during_gate["data_fetched_at_utc"] == t0.isoformat()
    assert during_gate["next_retry_at_utc"] == (
        failed_at + timedelta(minutes=5)
    ).isoformat()
    assert failed_calls == ["^TNX"]

    # Once the gate reopens, refresh even though the old origin TTL would still
    # be valid; only a successful downloader attempt can restore fresh status.
    success_calls: list[str] = []
    cache._downloader = _mock_download(calls=success_calls, values=[5.0, 5.1])
    recovered = cache.get_scalar("^TNX", now=t0 + timedelta(minutes=7))
    assert recovered["status"] == "fresh"
    assert recovered["value"] == 5.1
    assert recovered["refresh_error_type"] == ""
    assert success_calls == ["^TNX"]


def test_empty_frame_not_cached_as_fresh():
    """Empty frames are failed attempts: never cached fresh, shared in-cycle.

    An empty frame flows through stale-if-error like an exception: it records
    a failed attempt and opens a retry gate (so same-cycle/in-gate callers
    share the outcome) but never poisons the cache — once the retry gate
    reopens, the next refresh downloads again.
    """
    now = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    def _empty(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        return pd.DataFrame()

    cache._downloader = _empty
    result = cache.get_scalar("^TNX", now=now)
    assert result["status"] == "unavailable"
    assert result["refresh_error_type"] == "ValueError"
    assert result["next_retry_at_utc"] != ""

    # Same refresh cycle shares the failed attempt — no downloader call.
    same_cycle = cache.get_scalar("^TNX", now=now)
    assert same_cycle["status"] == "unavailable"
    assert same_cycle["refresh_error_type"] == "ValueError"

    # The empty frame was NOT cached and the retry gate is open: the next
    # refresh (after the gate) downloads again and wins.
    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls, values=[4.0, 4.1])
    result2 = cache.get_scalar("^TNX", now=now + timedelta(minutes=6))
    assert result2["status"] == "fresh"
    assert len(calls) == 1
    assert cache.attempt_counts() == {"^TNX/5d/1d": 2}
    assert cache.success_counts() == {"^TNX/5d/1d": 1}


def test_consumer_mutation_does_not_corrupt_cache():
    """Mutating a returned frame must not affect the cached entry."""
    now = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    first = cache.get_frame("^TNX", now=now)

    # Consumer mutates the LAST row of the returned DataFrame
    last_idx = len(first) - 1
    first.iloc[last_idx, first.columns.get_loc("Close")] = 999.0
    assert float(first["Close"].iloc[-1]) == 999.0

    second = cache.get_frame("^TNX", now=now)
    assert second is not None
    # The cached entry should still have the original Close value
    assert float(second["Close"].iloc[-1]) == 4.1


# ------------------------------------------------------------------
# Test D — Frozen-response parity
# ------------------------------------------------------------------
def test_frozen_fixture_1_tnx_fvx_vix_produces_correct_scoring(monkeypatch: pytest.MonkeyPatch):
    """Fixture 1: TNX=[4.506,4.507], FVX=[4.000,4.000], VIX=[18,18].

    Expected: Tier1=3/5, Tier2=5/5, Tier3=6/6, alignment=14/16.
    """
    service = NewsService()
    monkeypatch.setattr(NewsService, "_interest_rates", {})

    frames = {
        "^TNX": _frame([4.506, 4.507]),
        "^FVX": _frame([4.000, 4.000]),
        "^VIX": _frame([18.0, 18.0]),
    }

    with patch("services.macro_market_cache.yf.download",
               side_effect=lambda ticker, **_: frames[ticker]):
        cal_mock, headlines_mock, statements_mock = _patch_service_sources(service)
        with patch.object(service, "_fetch_global_calendar_payload", cal_mock), \
             patch.object(service, "_fetch_global_forex_headlines_with_status", headlines_mock), \
             patch.object(service, "_latest_official_statements_with_status", statements_mock):
            snapshot = service._get_global_macro_snapshot()

    result = service._compute_macro_tiers(
        "EUR/USD", ["EUR", "USD"], [], [], [], [],
        ai_service=None, global_snapshot=snapshot,
    )
    assert {k: result["tier1"][k] for k in ("buy", "sell")} == {"buy": 3, "sell": 5}
    assert {k: result["tier2"][k] for k in ("buy", "sell")} == {"buy": 5, "sell": 5}
    assert {k: result["tier3"][k] for k in ("buy", "sell")} == {"buy": 6, "sell": 6}
    assert result["raw_total"] == {"buy": 14, "sell": 16}
    assert result["alignment"] == {"buy": 14, "sell": 16}


def test_frozen_fixture_2_inverted_yield_produces_correct_scoring(monkeypatch: pytest.MonkeyPatch):
    """Fixture 2: TNX=4.10, FVX=4.35 (inverted), VIX=27.0.

    EUR=3.25%(cut), USD=5.50%(hold) — dovish EUR, hawkish USD.
    Expected: Tier1=3/7, Tier2=5/5, Tier3=3/7, alignment=11/19.
    """
    rates = {
        "EUR": {"rate": 3.25, "rate_label": "3.25%", "trend": "cut", "source": "frozen"},
        "USD": {"rate": 5.50, "rate_label": "5.50%", "trend": "hold", "source": "frozen"},
    }
    monkeypatch.setattr(NewsService, "_interest_rates", rates)
    service = NewsService()

    headlines = [
        {"title": "Fed stays hawkish as yields rise", "published_utc": "2026-07-31T00:00:00Z"},
        {"title": "ECB signals dovish rate cut amid slowdown", "published_utc": "2026-07-31T00:00:00Z"},
        {"title": "Risk-off war fears trigger sell-off", "published_utc": "2026-07-31T00:00:00Z"},
    ]
    now = datetime.now(UTC)
    snapshot = MacroGlobalSnapshot(
        fetched_at_utc=now, expires_at_utc=now + timedelta(minutes=5),
        tnx=4.10, fvx=4.35, yield_spread_10y_5y=-0.25, yield_steepening=False,
        vix=27.0,
        global_headlines=tuple(headlines), official_statements=(),
        calendar_payload={"events": [], "source": "frozen", "warning": ""},
        source_status={}, stale_fields=(),
    )
    themes = service._macro_themes("EUR/USD", ["EUR", "USD"], headlines)
    hotspots = service._geopolitical_hotspots(headlines)

    result = service._compute_macro_tiers(
        "EUR/USD", ["EUR", "USD"], headlines, [], themes, hotspots,
        ai_service=None, global_snapshot=snapshot,
    )
    assert {k: result["tier1"][k] for k in ("buy", "sell")} == {"buy": 3, "sell": 7}
    assert {k: result["tier2"][k] for k in ("buy", "sell")} == {"buy": 5, "sell": 5}
    assert {k: result["tier3"][k] for k in ("buy", "sell")} == {"buy": 3, "sell": 7}
    assert result["alignment"] == {"buy": 11, "sell": 19}
    assert result["raw_total"] == {"buy": 11, "sell": 19}
    expected_reason = (
        "[T1] EUR=3.25%(Nới lỏng) so với USD=5.50%(Thắt chặt) | "
        "[T2] Sự kiện lịch KT: base=0, quote=0 | "
        "[T3] Tâm lý TT=Né tránh rủi ro, điểm nóng=1"
    )
    assert result["reasons"] == {"buy": expected_reason, "sell": expected_reason}
    assert result["tier1"]["detail"]["yield_spread_adj"] == {"buy": 2, "sell": -2}
    assert result["tier3"]["detail"]["vix_adjustment"] == -2


# ------------------------------------------------------------------
# Test E — Single-flight over failure/empty paths, retry isolation,
# and attempt/success counters
# ------------------------------------------------------------------

def test_concurrent_expired_refresh_failure_single_flight_shares_stale():
    """Two concurrent expired refreshes hit RuntimeError: exactly ONE
    downloader attempt; both waiters receive the same stale result."""
    t0 = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    seed = cache.get_scalar("^TNX", now=t0)
    assert seed["status"] == "fresh"

    expired_at = t0 + timedelta(minutes=6)  # TTL expired, stale window open
    calls: list[str] = []
    entered, release = Event(), Event()

    def _slow_fail(ticker: str, *, period: str = "5d", interval: str = "1d"):
        calls.append(ticker)
        entered.set()
        assert release.wait(timeout=5)
        raise RuntimeError("offline")

    cache._downloader = _slow_fail
    results: list[dict | None] = [None, None]

    def _t0():
        results[0] = cache.get_scalar("^TNX", now=expired_at)

    def _t1():
        results[1] = cache.get_scalar("^TNX", now=expired_at)

    th0, th1 = Thread(target=_t0), Thread(target=_t1)
    th0.start()
    assert entered.wait(timeout=5)  # owner thread is inside the downloader
    th1.start()                     # waiter blocks on the per-key lock
    _wait_for_flight_waiters(cache, ("^TNX", "5d", "1d"))
    release.set()
    th0.join(timeout=5)
    th1.join(timeout=5)

    assert calls == ["^TNX"]  # exactly ONE downloader attempt
    for r in results:
        assert r["status"] == "stale"
        assert r["value"] == 4.1
        assert r["previous"] == 4.0
        assert r["refresh_error_type"] == "RuntimeError"
    # Both waiters share the SAME stale generation/provenance.
    assert results[0]["fetched_at_utc"] == results[1]["fetched_at_utc"] == seed["fetched_at_utc"]
    assert results[0]["expires_at_utc"] == results[1]["expires_at_utc"]

    # A same-cycle latecomer also shares the failed generation — still 1 call.
    again = cache.get_scalar("^TNX", now=expired_at)
    assert again["status"] == "stale"
    assert again["refresh_error_type"] == "RuntimeError"
    assert calls == ["^TNX"]
    assert cache.attempt_counts() == {"^TNX/5d/1d": 2}  # seed + one failed
    assert cache.success_counts() == {"^TNX/5d/1d": 1}


def test_concurrent_expired_refresh_empty_frame_single_flight_shares_stale():
    """Empty frames behave like exceptions: ONE attempt, waiters share the
    stale-if-error outcome with a ValueError provenance."""
    t0 = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    seed = cache.get_scalar("^TNX", now=t0)
    assert seed["status"] == "fresh"

    expired_at = t0 + timedelta(minutes=6)
    calls: list[str] = []
    entered, release = Event(), Event()

    def _slow_empty(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        entered.set()
        assert release.wait(timeout=5)
        return pd.DataFrame()

    cache._downloader = _slow_empty
    results: list[dict | None] = [None, None]

    def _t0():
        results[0] = cache.get_scalar("^TNX", now=expired_at)

    def _t1():
        results[1] = cache.get_scalar("^TNX", now=expired_at)

    th0, th1 = Thread(target=_t0), Thread(target=_t1)
    th0.start()
    assert entered.wait(timeout=5)
    th1.start()
    _wait_for_flight_waiters(cache, ("^TNX", "5d", "1d"))
    release.set()
    th0.join(timeout=5)
    th1.join(timeout=5)

    assert calls == ["^TNX"]  # empty frame counted as ONE failed attempt
    for r in results:
        assert r["status"] == "stale"
        assert r["value"] == 4.1
        assert r["refresh_error_type"] == "ValueError"
    assert results[0]["fetched_at_utc"] == results[1]["fetched_at_utc"] == seed["fetched_at_utc"]

    again = cache.get_scalar("^TNX", now=expired_at)
    assert again["status"] == "stale"
    assert calls == ["^TNX"]
    assert cache.attempt_counts() == {"^TNX/5d/1d": 2}
    assert cache.success_counts() == {"^TNX/5d/1d": 1}


def test_concurrent_cold_failure_single_flight_shares_unavailable():
    """Cold start, concurrent failures: exactly ONE attempt, both callers
    receive the same unavailable result."""
    now = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    calls: list[str] = []
    entered, release = Event(), Event()

    def _slow_fail(ticker: str, *, period: str = "5d", interval: str = "1d"):
        calls.append(ticker)
        entered.set()
        assert release.wait(timeout=5)
        raise RuntimeError("offline")

    cache._downloader = _slow_fail
    results: list[dict | None] = [None, None]

    def _t0():
        results[0] = cache.get_scalar("^TNX", now=now)

    def _t1():
        results[1] = cache.get_scalar("^TNX", now=now)

    th0, th1 = Thread(target=_t0), Thread(target=_t1)
    th0.start()
    assert entered.wait(timeout=5)
    th1.start()
    _wait_for_flight_waiters(cache, ("^TNX", "5d", "1d"))
    release.set()
    th0.join(timeout=5)
    th1.join(timeout=5)

    assert calls == ["^TNX"]  # exactly ONE attempt
    for r in results:
        assert r["status"] == "unavailable"
        assert r["value"] is None
        assert r["error_type"] == "RuntimeError"
        assert r["refresh_error_type"] == "RuntimeError"

    # Same-cycle latecomer shares the unavailable outcome — still ONE attempt.
    again = cache.get_scalar("^TNX", now=now)
    assert again["status"] == "unavailable"
    assert again["refresh_error_type"] == "RuntimeError"
    assert calls == ["^TNX"]
    assert cache.attempt_counts() == {"^TNX/5d/1d": 1}
    assert cache.success_counts() == {"^TNX/5d/1d": 0}


def test_failed_attempt_keeps_retry_state_separate_and_does_not_extend_expiry():
    """Retry metadata (incl. the retry gate) is stored separately from the
    data entry: a failed attempt never extends or refreshes the data expiry,
    and consumers reuse the stale outcome until the gate reopens."""
    t0 = datetime.now(UTC)
    ttl = timedelta(minutes=5)
    cache = MacroMarketCache(ttl=ttl)
    set_shared_cache(cache)
    key = ("^TNX", "5d", "1d")

    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    cache.get_scalar("^TNX", now=t0)
    assert cache._cache[key].fetched_at == t0
    assert cache._cache[key].expires_at == t0 + ttl

    cache._downloader = _mock_raise(RuntimeError, "offline")
    t1 = t0 + timedelta(minutes=6)
    stale = cache.get_scalar("^TNX", now=t1)
    assert stale["status"] == "stale"

    # Data expiry/fetch timestamps are untouched by the failed attempt.
    assert cache._cache[key].fetched_at == t0
    assert cache._cache[key].expires_at == t0 + ttl
    assert cache._cache[key].refresh_error_type == "RuntimeError"
    # Retry state (incl. the gate) lives in the separate attempt ledger.
    state = cache._attempts[key]
    assert state.last_attempt_at == t1
    assert state.next_retry_at == t1 + cache._retry_ttl
    assert state.last_error_type == "RuntimeError"
    assert (state.attempts, state.successes) == (2, 1)

    # Within the retry gate consumers reuse the stale outcome — the
    # downloader is never invoked and the data entry is not extended.
    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls, values=[9.0, 9.1])
    within = cache.get_scalar("^TNX", now=t1 + timedelta(minutes=1))
    assert within["status"] == "stale"
    assert within["value"] == 4.1
    assert calls == []
    assert cache._attempts[key].attempts == 2
    assert cache._cache[key].expires_at == t0 + ttl

    # After the gate reopens, a later cycle is free to retry; the success
    # legitimately replaces the data, proving the FAILED attempt never moved
    # the previous expiry (asserted above).
    t2 = t1 + timedelta(minutes=6)
    after = cache.get_scalar("^TNX", now=t2)
    assert after["status"] == "fresh"
    assert after["value"] == 9.1
    assert cache._attempts[key].attempts == 3
    assert cache._attempts[key].successes == 2


def test_success_path_attempt_and_success_counters_single_flight(monkeypatch: pytest.MonkeyPatch):
    """Success path: attempts == successes == exactly one per global source
    across preload + 28 consumer reads + a warm second scan."""
    cache, service = _fresh_cache_and_service()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    _patch_no_http_fallback(monkeypatch)

    cal_mock, headlines_mock, statements_mock = _patch_service_sources(service)
    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls)
    monkeypatch.setattr(service, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service, "_latest_official_statements_with_status", statements_mock)

    service.preload_macro_contexts(SYMBOLS_28)
    for symbol in SYMBOLS_28:
        service.data_quality_flags(symbol)

    # Warm second scan (new service, same shared cache).
    service2 = NewsService()
    monkeypatch.setattr(service2, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service2, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service2, "_latest_official_statements_with_status", statements_mock)
    service2.preload_macro_contexts(SYMBOLS_28)

    expected = {"^TNX/5d/1d": 1, "^FVX/5d/1d": 1, "^VIX/5d/1d": 1}
    assert cache.attempt_counts() == expected  # failed/empty attempts would show here
    assert cache.success_counts() == expected
    assert cache.call_counts() == expected  # backward-compatible alias
    assert len(calls) == 3


# ------------------------------------------------------------------
# Test F — Retry gate, force-refresh semantics, and the late-waiter race
# ------------------------------------------------------------------

def test_retry_gate_suppresses_failed_refresh_retries(monkeypatch: pytest.MonkeyPatch):
    """Within the retry gate, a failed macro refresh is served as stale with
    exactly ONE attempt per source: preload + consumer pass do not re-download
    and contexts are built once per symbol (3, never 6)."""
    cache, service = _fresh_cache_and_service()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    _patch_no_http_fallback(monkeypatch)
    cal_mock, headlines_mock, statements_mock = _patch_service_sources(service)
    monkeypatch.setattr(service, "_fetch_global_calendar_payload", cal_mock)
    monkeypatch.setattr(service, "_fetch_global_forex_headlines_with_status", headlines_mock)
    monkeypatch.setattr(service, "_latest_official_statements_with_status", statements_mock)

    # Seed stale data: a snapshot fetched ~6 minutes ago, so its entries and
    # the snapshot itself are already expired when the preload runs below.
    past = datetime.now(UTC) - timedelta(minutes=6)
    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    service._get_global_macro_snapshot(now=past)

    symbols = ["EUR/USD", "GBP/USD", "USD/JPY"]
    calls: list[str] = []

    def _failing(ticker: str, *, period: str = "5d", interval: str = "1d") -> pd.DataFrame:
        calls.append(ticker)
        raise RuntimeError("offline")

    cache._downloader = _failing

    with patch.object(service, "_build_macro_context", wraps=service._build_macro_context) as build:
        service.preload_macro_contexts(symbols)
        assert Counter(calls) == Counter({"^TNX": 1, "^FVX": 1, "^VIX": 1})
        calls.clear()

        for symbol in symbols:
            service.data_quality_flags(symbol)

    # Consumer pass + final inspection: zero additional downloads, and the
    # contexts were built once per symbol — never rebuilt for consumers.
    assert calls == []
    assert build.call_count == 3

    snapshot = service._get_global_macro_snapshot()
    assert snapshot.tnx == 4.1
    assert {"^TNX", "^FVX", "^VIX"} <= set(snapshot.stale_fields)
    for name in ("^TNX", "^FVX", "^VIX"):
        status = snapshot.source_status[name]
        assert status["status"] == "stale"
        assert status["refresh_error_type"] == "RuntimeError"
    assert calls == []


def test_retry_gate_after_ttl_allows_exactly_one_new_flight():
    """Once the retry gate reopens, a refresh performs exactly ONE new
    downloader attempt per source — no retry storm, single-flight preserved."""
    t0 = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)
    key = ("^TNX", "5d", "1d")

    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    cache.get_scalar("^TNX", now=t0)  # fresh seed

    cache._downloader = _mock_raise(RuntimeError, "offline")
    t1 = t0 + timedelta(minutes=6)
    assert cache.get_scalar("^TNX", now=t1)["status"] == "stale"  # 1st failed attempt
    assert cache._attempts[key].attempts == 2

    # Within the gate: several consumers, zero new attempts.
    for _ in range(3):
        assert cache.get_scalar("^TNX", now=t1 + timedelta(minutes=1))["status"] == "stale"
    assert cache._attempts[key].attempts == 2

    # After the gate: one new flight for the next refresh.
    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls, values=[5.0, 5.1])
    fresh = cache.get_scalar("^TNX", now=t1 + timedelta(minutes=6))
    assert fresh["status"] == "fresh"
    assert fresh["value"] == 5.1
    assert calls == ["^TNX"]
    assert cache._attempts[key].attempts == 3


def test_sequential_force_refresh_with_same_checked_at_performs_new_downloads():
    """Sequential force_refresh — even with the identical checked_at — performs
    a fresh download each time; only concurrent force refreshes share a flight."""
    t0 = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)
    calls: list[str] = []
    cache._downloader = _mock_download(calls=calls, values=[4.0, 4.1])

    cache.get_frame("^TNX", now=t0)  # cold fill
    assert len(calls) == 1

    cache.get_frame("^TNX", now=t0, force_refresh=True)  # sequential force
    assert len(calls) == 2  # NEW download, not shared
    cache.get_frame("^TNX", now=t0, force_refresh=True)  # again
    assert len(calls) == 3  # another NEW download
    assert cache.attempt_counts() == {"^TNX/5d/1d": 3}
    assert cache.success_counts() == {"^TNX/5d/1d": 3}


def test_late_force_waiter_shares_flight_after_outcome_recorded():
    """A force waiter that starts AFTER the owner recorded the failure outcome
    but BEFORE the owner released the per-key lock still shares that flight —
    exactly one downloader attempt (explicit in-flight state, not a timestamp
    delta)."""
    t0 = datetime.now(UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)
    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    cache.get_scalar("^TNX", now=t0)  # seed fresh

    expired_at = t0 + timedelta(minutes=6)
    calls: list[str] = []
    entered = Event()
    owner_blocked = Event()
    release = Event()
    waiter_read = Event()

    def _slow_fail(ticker: str, *, period: str = "5d", interval: str = "1d"):
        calls.append(ticker)
        entered.set()
        assert release.wait(timeout=5)
        raise RuntimeError("offline")

    cache._downloader = _slow_fail

    def _hook():
        # Owner has recorded the outcome but still holds the key lock.
        owner_blocked.set()
        assert waiter_read.wait(timeout=5)

    cache._after_flight_hook = _hook

    results: list[dict | None] = [None, None]

    def _owner():
        results[0] = cache.get_scalar("^TNX", now=expired_at, force_refresh=True)

    def _waiter():
        results[1] = cache.get_scalar("^TNX", now=expired_at, force_refresh=True)

    owner = Thread(target=_owner)
    waiter = Thread(target=_waiter)
    owner.start()
    assert entered.wait(timeout=5)  # owner inside the downloader
    release.set()  # let the downloader finish; owner now records the outcome
    assert owner_blocked.wait(timeout=5)  # owner recorded outcome, lock held
    waiter.start()  # late waiter: starts post-generation-update
    _wait_for_flight_waiters(cache, ("^TNX", "5d", "1d"))
    waiter_read.set()  # let the owner finish + release
    owner.join(timeout=5)
    waiter.join(timeout=5)
    cache._after_flight_hook = None

    assert calls == ["^TNX"]  # exactly one attempt
    for r in results:
        assert r["status"] == "stale"
        assert r["value"] == 4.1
        assert r["refresh_error_type"] == "RuntimeError"
    for field in (
        "cache_key",
        "checked_at_utc",
        "data_fetched_at_utc",
        "origin_expires_at_utc",
        "next_retry_at_utc",
        "refresh_error_type",
    ):
        assert results[0][field] == results[1][field]


# ------------------------------------------------------------------
# Test G — Cache-poison: non-empty but non-scalarizable frames
# ------------------------------------------------------------------

def test_malformed_frame_not_cached_as_fresh():
    """A non-empty DataFrame that cannot be converted to a scalar (missing
    Close column) is a FAILED attempt: unavailable, attempts=1/successes=0,
    no cache entry, no fabricated origin, retry-gated, and recovered by a
    valid frame once the retry TTL reopens."""
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)

    def _malformed(ticker: str, *, period: str = "5d", interval: str = "1d"):
        return pd.DataFrame({"Open": [1.0, 2.0], "High": [1.5, 2.5]})  # no Close

    cache._downloader = _malformed
    result = cache.get_scalar("^TNX", now=t0)

    # Same failure path as exceptions/empty frames: unavailable with error and
    # retry metadata reflecting THIS failed refresh.
    assert result["status"] == "unavailable"
    assert result["value"] is None
    assert result["refresh_error_type"] == "ValueError"
    assert result["checked_at_utc"] == t0.isoformat()
    assert result["next_retry_at_utc"] == (t0 + timedelta(minutes=5)).isoformat()
    # No valid origin exists — provenance must not fabricate one.
    assert result["data_fetched_at_utc"] == ""
    assert result["origin_expires_at_utc"] == ""

    # Not published: no cache entry and no success counter.
    assert ("^TNX", "5d", "1d") not in cache._cache
    assert cache.attempt_counts() == {"^TNX/5d/1d": 1}
    assert cache.success_counts() == {"^TNX/5d/1d": 0}

    # Within the retry TTL: consumers reuse the outcome, no re-download.
    calls: list[str] = []

    def _record_malformed(ticker: str, *, period: str = "5d", interval: str = "1d"):
        calls.append(ticker)
        return pd.DataFrame({"Open": [1.0, 2.0]})

    cache._downloader = _record_malformed
    within_gate = cache.get_scalar("^TNX", now=t0 + timedelta(minutes=1))
    assert within_gate["status"] == "unavailable"
    assert within_gate["refresh_error_type"] == "ValueError"
    assert calls == []

    # After the retry TTL, a valid frame recovers the cache.
    cache._downloader = _mock_download(calls=[], values=[4.0, 4.1])
    recovered = cache.get_scalar("^TNX", now=t0 + timedelta(minutes=6))
    assert recovered["status"] == "fresh"
    assert recovered["value"] == 4.1
    assert recovered["refresh_error_type"] == ""
    assert cache.attempt_counts() == {"^TNX/5d/1d": 2}
    assert cache.success_counts() == {"^TNX/5d/1d": 1}


def test_malformed_refresh_keeps_valid_stale_frame():
    """A malformed refresh must never overwrite a valid stale frame: the stale
    origin fetched/expiry are preserved and the malformed payload is never
    published to the cache."""
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)
    key = ("^TNX", "5d", "1d")

    seeded: list[pd.DataFrame] = []

    def _seed(ticker: str, *, period: str = "5d", interval: str = "1d"):
        frame = _frame([4.0, 4.1])
        seeded.append(frame)
        return frame

    cache._downloader = _seed
    seed = cache.get_scalar("^TNX", now=t0)
    assert seed["status"] == "fresh"

    def _malformed(ticker: str, *, period: str = "5d", interval: str = "1d"):
        return pd.DataFrame({"Open": [1.0], "High": [1.5]})  # non-empty, no Close

    cache._downloader = _malformed
    refresh_at = t0 + timedelta(minutes=6)  # origin expired, stale window open
    stale = cache.get_scalar("^TNX", now=refresh_at)

    # Stale-if-error serves the ORIGINAL frame with the malformed refresh error.
    assert stale["status"] == "stale"
    assert stale["value"] == 4.1
    assert stale["refresh_error_type"] == "ValueError"
    assert stale["checked_at_utc"] == refresh_at.isoformat()
    assert stale["next_retry_at_utc"] == (refresh_at + timedelta(minutes=5)).isoformat()
    # The ORIGINAL origin timestamps are retained — never fabricated/replaced.
    assert stale["data_fetched_at_utc"] == t0.isoformat()
    assert stale["origin_expires_at_utc"] == (t0 + timedelta(minutes=5)).isoformat()

    # The cached entry still holds the original valid frame with its origin
    # timestamps; the malformed payload was never published.
    entry = cache._cache[key]
    assert entry.data is seeded[0]
    assert entry.fetched_at == t0
    assert entry.expires_at == t0 + timedelta(minutes=5)
    assert entry.refresh_error_type == "ValueError"
    assert cache.attempt_counts() == {"^TNX/5d/1d": 2}
    assert cache.success_counts() == {"^TNX/5d/1d": 1}


def test_multiindex_frame_with_valid_scalar_is_cached_as_fresh():
    """A scalarizable MultiIndex frame (yfinance-style) is still cached as
    fresh — publish-time validation must support BOTH column layouts."""
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    cache = MacroMarketCache()
    set_shared_cache(cache)
    columns = pd.MultiIndex.from_tuples([("Price", "Close"), ("Price", "Open")])
    frame = pd.DataFrame([[4.0, 1.0], [4.1, 2.0]], columns=columns)

    cache._downloader = lambda ticker, *, period="5d", interval="1d": frame
    result = cache.get_scalar("^TNX", now=t0)
    assert result["status"] == "fresh"
    # iloc[-1, 0] is the established MultiIndex scalar rule — unchanged.
    assert result["value"] == 4.1
    assert result["previous"] == 4.0
    assert cache.success_counts() == {"^TNX/5d/1d": 1}
    assert ("^TNX", "5d", "1d") in cache._cache
