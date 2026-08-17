"""Phase 2B global snapshot, call-count, stale fallback, and parity tests."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from services.macro_market_cache import MacroMarketCache, reset_shared_cache, set_shared_cache
from services.news_service import MacroGlobalSnapshot, NewsService


SYMBOLS_28 = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD", "NZD/USD", "USD/CAD",
    "EUR/GBP", "EUR/JPY", "EUR/CHF", "EUR/AUD", "EUR/NZD", "EUR/CAD", "GBP/JPY",
    "GBP/CHF", "GBP/AUD", "GBP/NZD", "GBP/CAD", "AUD/JPY", "AUD/CHF", "AUD/NZD",
    "AUD/CAD", "NZD/JPY", "NZD/CHF", "NZD/CAD", "CAD/JPY", "CAD/CHF", "CHF/JPY",
]


@pytest.fixture(autouse=True)
def _reset_shared_cache():
    """Ensure each test starts with a fresh shared macro cache singleton."""
    reset_shared_cache()
    yield
    reset_shared_cache()


class _FakeAI:
    config = SimpleNamespace(provider="deepseek", model="frozen-model", api_key="SECRET")

    def analyze(self, *_args, **_kwargs):
        return "neutral"


def _frame(values: list[float] | None = None) -> pd.DataFrame:
    return pd.DataFrame({"Close": values or [4.0, 4.1]})


def _pre_refactor_yield_payload(
    tnx_frame: pd.DataFrame,
    fvx_frame: pd.DataFrame,
) -> dict[str, object]:
    """Frozen reference for the original raw-steepening/rounded-output order."""
    tnx = float(tnx_frame["Close"].iloc[-1])
    fvx = float(fvx_frame["Close"].iloc[-1])
    raw_spread = tnx - fvx
    previous_raw_spread = (
        float(tnx_frame["Close"].iloc[-2]) - float(fvx_frame["Close"].iloc[-2])
    )
    return {
        "tnx": tnx,
        "fvx": fvx,
        "spread": round(raw_spread, 2),
        "steepening": raw_spread > previous_raw_spread,
    }


def _collection_result(
    value: list[dict[str, object]],
    *,
    status: str = "fresh",
    attempted_sources: int = 1,
    successful_sources: int = 1,
    error_types: list[str] | None = None,
) -> dict[str, object]:
    return {
        "status": status,
        "value": value,
        "attempted_sources": attempted_sources,
        "successful_sources": successful_sources,
        "error_types": error_types or [],
    }


def _patch_non_yahoo_sources(service: NewsService):
    return (
        patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}),
        patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=_collection_result([])),
        patch.object(service, "_latest_official_statements_with_status", return_value=_collection_result([])),
    )


# ---------------------------------------------------------------------------
# Tests that need the download patched at the shared cache level
# (services.macro_market_cache.yf.download), since _download_macro_source
# now delegates to get_shared_cache().get_scalar().
# ---------------------------------------------------------------------------

_YF_PATCH_TARGET = "services.macro_market_cache.yf.download"


def test_28_symbols_fetch_each_yahoo_source_once_and_second_pass_zero(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    calls: list[str] = []

    def download(ticker: str, **_kwargs):
        calls.append(ticker)
        return _frame()

    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, side_effect=download), \
         patch.object(service, "_build_macro_context", wraps=service._build_macro_context) as build:
        ai = _FakeAI()
        service.preload_macro_contexts(SYMBOLS_28, ai_service=ai)
        for symbol in SYMBOLS_28:
            service.data_quality_flags(symbol, ai_service=ai)

    assert Counter(calls) == Counter({"^TNX": 1, "^FVX": 1, "^VIX": 1})
    assert build.call_count == 28


def test_positive_steepening_frozen_responses_match_pre_refactor_scores(monkeypatch: pytest.MonkeyPatch):
    """Exercise provider frames -> snapshot -> scoring for the rounding edge case."""
    service = NewsService()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    frames = {
        "^TNX": _frame([4.506, 4.507]),
        "^FVX": _frame([4.000, 4.000]),
        "^VIX": _frame([18.0, 18.0]),
    }
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, side_effect=lambda ticker, **_kwargs: frames[ticker]):
        snapshot = service._get_global_macro_snapshot()

    result = service._compute_macro_tiers(
        "EUR/USD",
        ["EUR", "USD"],
        [],
        [],
        [],
        [],
        ai_service=None,
        global_snapshot=snapshot,
    )
    reference_yield = _pre_refactor_yield_payload(frames["^TNX"], frames["^FVX"])
    baseline_snapshot = MacroGlobalSnapshot(
        fetched_at_utc=snapshot.fetched_at_utc,
        expires_at_utc=snapshot.expires_at_utc,
        tnx=float(reference_yield["tnx"]),
        fvx=float(reference_yield["fvx"]),
        yield_spread_10y_5y=float(reference_yield["spread"]),
        yield_steepening=bool(reference_yield["steepening"]),
        vix=18.0,
        global_headlines=(),
        official_statements=(),
        calendar_payload={"events": [], "source": "frozen", "warning": ""},
        source_status={},
        stale_fields=(),
    )
    baseline = service._compute_macro_tiers(
        "EUR/USD",
        ["EUR", "USD"],
        [],
        [],
        [],
        [],
        ai_service=None,
        global_snapshot=baseline_snapshot,
    )

    assert snapshot.yield_spread_10y_5y == 0.51
    assert snapshot.yield_steepening is True
    for key in ("tier1", "tier2", "tier3", "raw_total", "alignment", "reasons"):
        assert result[key] == baseline[key]
    expected_reason = (
        "[T1] EUR=--(Trung tính) so với USD=--(Trung tính) | "
        "[T2] Sự kiện lịch KT: base=0, quote=0 | "
        "[T3] Tâm lý TT=Trung tính, điểm nóng=0"
    )
    assert result["reasons"] == {"buy": expected_reason, "sell": expected_reason}
    assert result["tier1"]["detail"]["yield_spread_adj"] == {"buy": -1, "sell": 1}
    assert {key: result["tier1"][key] for key in ("buy", "sell")} == {"buy": 3, "sell": 5}
    assert {key: result["tier2"][key] for key in ("buy", "sell")} == {"buy": 5, "sell": 5}
    assert {key: result["tier3"][key] for key in ("buy", "sell")} == {"buy": 6, "sell": 6}
    assert result["raw_total"] == {"buy": 14, "sell": 16}
    assert result["alignment"] == {"buy": 14, "sell": 16}


def test_expired_snapshot_uses_bounded_stale_values_with_provenance():
    service = NewsService()
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        first = service._get_global_macro_snapshot()

    refresh_at = first.expires_at_utc + timedelta(seconds=1)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, side_effect=RuntimeError("offline")):
        second = service._get_global_macro_snapshot(now=refresh_at)

    assert (second.tnx, second.fvx, second.vix) == (first.tnx, first.fvx, first.vix)
    assert {"^TNX", "^FVX", "^VIX"}.issubset(second.stale_fields)
    assert all(second.source_status[name]["status"] == "stale" for name in ("^TNX", "^FVX", "^VIX"))
    assert all("data_fetched_at_utc" in second.source_status[name] for name in ("^TNX", "^FVX", "^VIX"))

    outside_stale_window = first.fetched_at_utc + timedelta(minutes=31)
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=_collection_result([])), \
         patch.object(service, "_latest_official_statements_with_status", return_value=_collection_result([])), \
         patch(_YF_PATCH_TARGET, side_effect=RuntimeError("offline")):
        expired = service._get_global_macro_snapshot(now=outside_stale_window)

    assert expired.tnx is None and expired.fvx is None and expired.vix is None
    assert all(expired.source_status[name]["status"] == "unavailable" for name in ("^TNX", "^FVX", "^VIX"))


def test_stale_snapshot_deadline_and_full_context_provenance(monkeypatch: pytest.MonkeyPatch):
    """Origin +30m bounds stale snapshot even while retries are gated to +34m."""
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    cache = MacroMarketCache(
        ttl=timedelta(minutes=5),
        stale_if_error=timedelta(minutes=30),
        retry_ttl=timedelta(minutes=5),
    )
    set_shared_cache(cache)
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    service = NewsService()
    cache._downloader = lambda _ticker, **_kwargs: _frame([4.0, 4.1])

    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch:
        first = service._get_global_macro_snapshot(now=t0)

    failed_at = t0 + timedelta(minutes=29)
    failed_calls: list[str] = []

    def fail(ticker: str, **_kwargs):
        failed_calls.append(ticker)
        raise RuntimeError("offline")

    cache._downloader = fail
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch:
        stale = service._get_global_macro_snapshot(now=failed_at)

    assert (stale.tnx, stale.fvx, stale.vix) == (first.tnx, first.fvx, first.vix)
    assert stale.expires_at_utc == t0 + timedelta(minutes=30)
    assert Counter(failed_calls) == Counter({"^TNX": 1, "^FVX": 1, "^VIX": 1})
    expected_fields = {
        "checked_at_utc": failed_at.isoformat(),
        "data_fetched_at_utc": t0.isoformat(),
        "origin_expires_at_utc": (t0 + timedelta(minutes=5)).isoformat(),
        "next_retry_at_utc": (t0 + timedelta(minutes=34)).isoformat(),
        "refresh_error_type": "RuntimeError",
    }
    for ticker in ("^TNX", "^FVX", "^VIX"):
        provenance = stale.source_status[ticker]
        assert provenance["status"] == "stale"
        assert provenance["cache_key"] == [ticker, "5d", "1d"]
        for field, expected in expected_fields.items():
            assert provenance[field] == expected

    context = service.latest_macro_context("EUR/USD", _snapshot=stale)
    context_cache = context["macro_cache"]
    assert context_cache["expires_at_utc"] == stale.expires_at_utc.isoformat()
    assert (
        context_cache["source_freshness"]["source_status"]
        == stale.source_status
    )

    # +31m is still inside the +34m retry gate, but stale data is already dead.
    after_deadline = t0 + timedelta(minutes=31)
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch:
        unavailable = service._get_global_macro_snapshot(now=after_deadline)

    assert unavailable.expires_at_utc == t0 + timedelta(minutes=34)
    assert unavailable.tnx is None and unavailable.fvx is None and unavailable.vix is None
    assert not ({"^TNX", "^FVX", "^VIX"} & set(unavailable.stale_fields))
    # Retry gate suppressed every downloader; the count remains the +29m calls.
    assert Counter(failed_calls) == Counter({"^TNX": 1, "^FVX": 1, "^VIX": 1})
    for ticker in ("^TNX", "^FVX", "^VIX"):
        provenance = unavailable.source_status[ticker]
        assert provenance["status"] == "unavailable"
        assert provenance["cache_key"] == [ticker, "5d", "1d"]
        assert provenance["checked_at_utc"] == after_deadline.isoformat()
        for field in (
            "data_fetched_at_utc",
            "origin_expires_at_utc",
            "next_retry_at_utc",
            "refresh_error_type",
        ):
            assert provenance[field] == expected_fields[field]

    unavailable_context = service.latest_macro_context(
        "EUR/USD", _snapshot=unavailable
    )
    assert (
        unavailable_context["macro_cache"]["source_freshness"]["source_status"]
        == unavailable.source_status
    )


def test_partial_yield_refresh_reuses_the_prior_coherent_curve():
    service = NewsService()
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, return_value=_frame([4.0, 4.1])):
        first = service._get_global_macro_snapshot()

    def partial_download(ticker: str, **_kwargs):
        if ticker == "^FVX":
            raise RuntimeError("offline")
        return _frame([8.0, 9.0])

    refresh_at = first.expires_at_utc + timedelta(seconds=1)
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, side_effect=partial_download):
        second = service._get_global_macro_snapshot(now=refresh_at)

    assert (second.tnx, second.fvx) == (first.tnx, first.fvx)
    assert second.yield_spread_10y_5y == first.yield_spread_10y_5y
    assert second.yield_steepening == first.yield_steepening
    assert second.source_status["^TNX"]["status"] == "stale"
    assert second.source_status["^FVX"]["status"] == "stale"
    assert second.source_status["^TNX"]["refresh_discarded_for_curve_consistency"] is True


@pytest.mark.parametrize("first_available", ["^TNX", "^FVX"])
def test_partial_curve_history_never_combines_opposite_single_legs(
    first_available: str,
    monkeypatch: pytest.MonkeyPatch,
):
    service = NewsService()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    second_available = "^FVX" if first_available == "^TNX" else "^TNX"

    def source_result(available: str):
        def fetch(ticker: str):
            if ticker == "^VIX":
                return {"status": "fresh", "value": 18.0, "previous": 18.0}
            if ticker == available:
                return {"status": "fresh", "value": 4.6, "previous": 4.5}
            return {"status": "unavailable", "value": None, "previous": None, "error_type": "TimeoutError"}
        return fetch

    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch.object(service, "_download_macro_source", side_effect=source_result(first_available)):
        first = service._get_global_macro_snapshot()

    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch.object(service, "_download_macro_source", side_effect=source_result(second_available)):
        second = service._get_global_macro_snapshot(now=first.expires_at_utc + timedelta(seconds=1))

    for snapshot in (first, second):
        assert snapshot.tnx is None
        assert snapshot.fvx is None
        assert snapshot.yield_spread_10y_5y is None
        assert snapshot.source_status["^TNX"]["discarded_for_curve_consistency"] is True
        assert snapshot.source_status["^FVX"]["discarded_for_curve_consistency"] is True
        buy, sell, detail = service._macro_tier1(
            "EUR",
            "USD",
            "neutral",
            "neutral",
            yield_spread_data=snapshot.yield_spread_payload(),
        )
        assert (buy, sell) == (4, 4)
        assert detail["yield_spread_adj"] == {"buy": 0, "sell": 0}


def test_rss_failure_uses_stale_collections_and_records_error_provenance():
    service = NewsService()
    headlines = [{"title": "frozen headline", "published_utc": "2026-07-31T00:00:00Z"}]
    statements = [{"title": "frozen statement", "published_utc": "2026-07-31T00:00:00Z"}]
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=_collection_result(headlines, attempted_sources=3, successful_sources=3)), \
         patch.object(service, "_latest_official_statements_with_status", return_value=_collection_result(statements, attempted_sources=6, successful_sources=6)), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        first = service._get_global_macro_snapshot()

    unavailable_headlines = _collection_result(
        [], status="unavailable", attempted_sources=3, successful_sources=0, error_types=["URLError"]
    )
    unavailable_statements = _collection_result(
        [], status="unavailable", attempted_sources=6, successful_sources=0, error_types=["TimeoutError"]
    )
    refresh_at = first.expires_at_utc + timedelta(seconds=1)
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=unavailable_headlines), \
         patch.object(service, "_latest_official_statements_with_status", return_value=unavailable_statements), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        second = service._get_global_macro_snapshot(now=refresh_at)

    assert second.global_headlines == first.global_headlines
    assert second.official_statements == first.official_statements
    for name, error_type, attempts in (
        ("global_headlines", "URLError", 3),
        ("official_statements", "TimeoutError", 6),
    ):
        assert name in second.stale_fields
        assert second.source_status[name]["status"] == "stale"
        assert second.source_status[name]["data_fetched_at_utc"] == first.source_status[name]["data_fetched_at_utc"]
        assert second.source_status[name]["refresh_error_types"] == [error_type]
        assert second.source_status[name]["attempted_sources"] == attempts
        assert second.source_status[name]["successful_sources"] == 0


def test_rss_stale_snapshot_is_also_bounded_by_origin_deadline():
    t0 = datetime(2026, 7, 31, 0, 0, tzinfo=UTC)
    service = NewsService()
    headlines = [{"title": "frozen", "published_utc": t0.isoformat()}]
    fresh_empty = _collection_result([])
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=_collection_result(headlines)), \
         patch.object(service, "_latest_official_statements_with_status", return_value=fresh_empty), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        first = service._get_global_macro_snapshot(now=t0)

    unavailable = _collection_result(
        [],
        status="unavailable",
        attempted_sources=3,
        successful_sources=0,
        error_types=["URLError"],
    )
    failed_at = t0 + timedelta(minutes=29)
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=unavailable), \
         patch.object(service, "_latest_official_statements_with_status", return_value=fresh_empty), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        stale = service._get_global_macro_snapshot(now=failed_at)

    assert stale.global_headlines == first.global_headlines
    assert stale.source_status["global_headlines"]["status"] == "stale"
    assert stale.expires_at_utc == t0 + timedelta(minutes=30)

    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=unavailable), \
         patch.object(service, "_latest_official_statements_with_status", return_value=fresh_empty), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        after_deadline = service._get_global_macro_snapshot(
            now=t0 + timedelta(minutes=31)
        )

    assert after_deadline.global_headlines == ()
    assert after_deadline.source_status["global_headlines"]["status"] == "unavailable"
    assert "global_headlines" not in after_deadline.stale_fields


def test_degraded_rss_refresh_prefers_stale_prior_without_staling_healthy_source():
    service = NewsService()
    old_headlines = [{"title": "complete old feed", "published_utc": "2026-07-31T00:00:00Z"}]
    old_statements = [{"title": "old statement", "published_utc": "2026-07-31T00:00:00Z"}]
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=_collection_result(old_headlines, attempted_sources=3, successful_sources=3)), \
         patch.object(service, "_latest_official_statements_with_status", return_value=_collection_result(old_statements, attempted_sources=6, successful_sources=6)), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        first = service._get_global_macro_snapshot()

    partial_headlines = _collection_result(
        [{"title": "partial new feed", "published_utc": "2026-07-31T00:01:00Z"}],
        status="degraded",
        attempted_sources=3,
        successful_sources=1,
        error_types=["TimeoutError"],
    )
    fresh_statements = [{"title": "fresh statement", "published_utc": "2026-07-31T00:01:00Z"}]
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=partial_headlines), \
         patch.object(service, "_latest_official_statements_with_status", return_value=_collection_result(fresh_statements, attempted_sources=6, successful_sources=6)), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        second = service._get_global_macro_snapshot(now=first.expires_at_utc + timedelta(seconds=1))

    assert second.global_headlines == first.global_headlines
    assert second.source_status["global_headlines"]["status"] == "stale"
    assert second.source_status["global_headlines"]["refresh_error_types"] == ["TimeoutError"]
    assert second.official_statements == tuple(fresh_statements)
    assert second.source_status["official_statements"]["status"] == "fresh"
    assert "official_statements" not in second.stale_fields


def test_unavailable_rss_snapshot_never_becomes_false_stale():
    service = NewsService()
    unavailable = _collection_result(
        [], status="unavailable", attempted_sources=3, successful_sources=0, error_types=["URLError"]
    )
    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=unavailable), \
         patch.object(service, "_latest_official_statements_with_status", return_value=unavailable), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        first = service._get_global_macro_snapshot()
        second = service._get_global_macro_snapshot(now=first.expires_at_utc + timedelta(seconds=1))

    assert first.source_status["global_headlines"]["status"] == "unavailable"
    assert second.source_status["global_headlines"]["status"] == "unavailable"
    assert "global_headlines" not in second.stale_fields
    assert "data_fetched_at_utc" not in second.source_status["global_headlines"]


def test_valid_empty_rss_is_fresh_and_legacy_api_remains_fail_soft():
    service = NewsService()

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def read():
            return b"<rss><channel></channel></rss>"

    with patch("services.news_service.urlopen", return_value=_Response()):
        rows, status = service._rss_items_with_status("https://example.invalid/rss", query="frozen")
    assert rows == []
    assert status == {"status": "fresh", "error_type": ""}

    with patch("services.news_service.urlopen", side_effect=OSError("offline")):
        assert service._rss_items("https://example.invalid/rss", query="frozen") == []
        rows, status = service._rss_items_with_status("https://example.invalid/rss", query="frozen")
    assert rows == []
    assert status["status"] == "unavailable"
    assert status["error_type"] == "OSError"

    class _MalformedResponse(_Response):
        @staticmethod
        def read():
            return b"<rss><channel>"

    with patch("services.news_service.urlopen", return_value=_MalformedResponse()):
        rows, status = service._rss_items_with_status("https://example.invalid/rss", query="frozen")
    assert rows == []
    assert status == {"status": "unavailable", "error_type": "ParseError"}

    class _NonRssResponse(_Response):
        @staticmethod
        def read():
            return b"<html><body><p>gateway error</p></body></html>"

    with patch("services.news_service.urlopen", return_value=_NonRssResponse()):
        rows, status = service._rss_items_with_status("https://example.invalid/rss", query="frozen")
    assert rows == []
    assert status == {"status": "unavailable", "error_type": "InvalidRSSStructure"}


def test_rss_aggregators_expose_all_failed_and_partial_query_provenance():
    service = NewsService()
    unavailable = ([], {"status": "unavailable", "error_type": "URLError"})
    with patch.object(service, "_rss_items_with_status", return_value=unavailable):
        headlines = service._fetch_global_forex_headlines_with_status()
        statements = service._latest_official_statements_with_status()

    assert headlines == {
        "status": "unavailable",
        "value": [],
        "attempted_sources": 3,
        "successful_sources": 0,
        "error_types": ["URLError"],
    }
    assert statements == {
        "status": "unavailable",
        "value": [],
        "attempted_sources": 6,
        "successful_sources": 0,
        "error_types": ["URLError"],
    }

    def partial(_url: str, *, query: str):
        if query.startswith("global macro risk"):
            return [], {"status": "fresh", "error_type": ""}
        return unavailable

    with patch.object(service, "_rss_items_with_status", side_effect=partial):
        degraded = service._fetch_global_forex_headlines_with_status()
    assert degraded["status"] == "degraded"
    assert degraded["attempted_sources"] == 3
    assert degraded["successful_sources"] == 1
    assert degraded["error_types"] == ["URLError"]


def test_no_snapshot_and_failed_yahoo_sources_is_fail_safe_not_fresh():
    service = NewsService()
    with patch.object(service, "_fetch_global_calendar_payload", side_effect=RuntimeError("offline")), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=_collection_result([])), \
         patch.object(service, "_latest_official_statements_with_status", return_value=_collection_result([])), \
         patch(_YF_PATCH_TARGET, side_effect=RuntimeError("offline")):
        snapshot = service._get_global_macro_snapshot()

    assert snapshot.tnx is None and snapshot.fvx is None and snapshot.vix is None
    assert all(snapshot.source_status[name]["status"] == "unavailable" for name in ("^TNX", "^FVX", "^VIX"))
    assert snapshot.expires_at_utc > snapshot.fetched_at_utc


def test_pair_tiers_never_call_yfinance_themselves(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    with patch(_YF_PATCH_TARGET, side_effect=AssertionError("unexpected download")):
        service._macro_tier1("EUR", "USD", "neutral", "neutral")
        service._macro_tier3(["EUR", "USD"], [], [], ai_service=None)


def test_preload_computes_ai_stance_once_per_unique_currency(monkeypatch: pytest.MonkeyPatch):
    service = NewsService()
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    currencies = sorted({part for symbol in SYMBOLS_28 for part in symbol.split("/")})
    headlines = [
        {"title": f"{currency} central bank policy update", "published_utc": "2026-07-31T00:00:00Z"}
        for currency in currencies
    ]
    ai = Mock()
    ai.config = SimpleNamespace(provider="deepseek", model="frozen-model", api_key="SECRET")
    ai.analyze.return_value = "neutral"

    with patch.object(service, "_fetch_global_calendar_payload", return_value={"events": [], "source": "frozen", "warning": ""}), \
         patch.object(service, "_fetch_global_forex_headlines_with_status", return_value=_collection_result(headlines)), \
         patch.object(service, "_latest_official_statements_with_status", return_value=_collection_result([])), \
         patch(_YF_PATCH_TARGET, return_value=_frame()):
        service.preload_macro_contexts(SYMBOLS_28, ai_service=ai)

    assert ai.analyze.call_count == len(currencies)


def test_frozen_input_scoring_parity_with_pre_refactor_golden(monkeypatch: pytest.MonkeyPatch):
    """Golden captured from the pre-Phase-2 formulas with these exact inputs."""
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
        fetched_at_utc=now,
        expires_at_utc=now + timedelta(minutes=5),
        tnx=4.10,
        fvx=4.35,
        yield_spread_10y_5y=-0.25,
        yield_steepening=False,
        vix=27.0,
        global_headlines=tuple(headlines),
        official_statements=(),
        calendar_payload={"events": [], "source": "frozen", "warning": ""},
        source_status={},
        stale_fields=(),
    )
    themes = service._macro_themes("EUR/USD", ["EUR", "USD"], headlines)
    hotspots = service._geopolitical_hotspots(headlines)

    result = service._compute_macro_tiers(
        "EUR/USD",
        ["EUR", "USD"],
        headlines,
        [],
        themes,
        hotspots,
        ai_service=None,
        global_snapshot=snapshot,
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


def test_partial_fvx_failure_keeps_real_runtime_error_and_origin_provenance(
    monkeypatch: pytest.MonkeyPatch,
):
    """Coherent-curve fallback must keep the failed leg's REAL source error
    (RuntimeError) and its origin fetched/expires timestamps; only the healthy
    leg whose fresh value is discarded gets the generic peer label."""
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    service = NewsService()
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, return_value=_frame([4.0, 4.1])):
        first = service._get_global_macro_snapshot()

    def partial_download(ticker: str, **_kwargs):
        if ticker == "^FVX":
            raise RuntimeError("offline")
        return _frame([8.0, 9.0])

    refresh_at = first.expires_at_utc + timedelta(seconds=1)
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, side_effect=partial_download):
        second = service._get_global_macro_snapshot(now=refresh_at)

    # Coherent prior curve retained for BOTH legs.
    assert (second.tnx, second.fvx) == (first.tnx, first.fvx)
    assert {"^TNX", "^FVX"} <= set(second.stale_fields)

    # The failed leg keeps its real error + origin provenance from the
    # shared-cache stale entry — not YieldCurvePeerUnavailable.
    fvx = second.source_status["^FVX"]
    assert fvx["status"] == "stale"
    assert fvx["refresh_error_type"] == "RuntimeError"
    assert fvx["cache_key"] == ["^FVX", "5d", "1d"]
    assert fvx["checked_at_utc"] == refresh_at.isoformat()
    assert fvx["data_fetched_at_utc"] == first.source_status["^FVX"]["data_fetched_at_utc"]
    assert fvx["origin_expires_at_utc"] == first.source_status["^FVX"]["origin_expires_at_utc"]
    assert fvx["next_retry_at_utc"] == (refresh_at + timedelta(minutes=5)).isoformat()
    assert fvx["refresh_discarded_for_curve_consistency"] is False

    # The healthy leg (fresh value discarded for curve consistency) gets the
    # peer label and the previous — actually served — value's origin fetched
    # AND expiry: discarding its fresh value must not lose its origin expiry.
    tnx = second.source_status["^TNX"]
    assert tnx["status"] == "stale"
    assert tnx["refresh_error_type"] == "YieldCurvePeerUnavailable"
    assert tnx["cache_key"] == ["^TNX", "5d", "1d"]
    assert tnx["checked_at_utc"] == refresh_at.isoformat()
    assert tnx["refresh_discarded_for_curve_consistency"] is True
    assert tnx["data_fetched_at_utc"] == first.source_status["^TNX"]["data_fetched_at_utc"]
    assert tnx["origin_expires_at_utc"] == first.source_status["^TNX"]["origin_expires_at_utc"]
    assert tnx["next_retry_at_utc"] == ""
    # The canonical origin describes the prior value actually served, while
    # this nested record preserves the healthy observation that was discarded.
    discarded = tnx["discarded_refresh_provenance"]
    assert discarded == {
        "cache_key": ["^TNX", "5d", "1d"],
        "checked_at_utc": refresh_at.isoformat(),
        "data_fetched_at_utc": refresh_at.isoformat(),
        "origin_expires_at_utc": (refresh_at + timedelta(minutes=5)).isoformat(),
        "next_retry_at_utc": "",
        "refresh_error_type": "",
    }
    context = service.latest_macro_context("EUR/USD", _snapshot=second)
    assert (
        context["macro_cache"]["source_freshness"]["source_status"]
        == second.source_status
    )


def test_context_expiry_is_clamped_to_snapshot_expiry(monkeypatch: pytest.MonkeyPatch):
    """A snapshot with only 1s of TTL left must not grant cached contexts a
    fresh 5-minute lifetime; _fresh_context_entry misses once the source
    snapshot has expired."""
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    service = NewsService()
    now = datetime.now(UTC)
    snapshot = MacroGlobalSnapshot(
        fetched_at_utc=now,
        expires_at_utc=now + timedelta(seconds=1),  # only 1s of source TTL left
        tnx=4.1,
        fvx=4.0,
        yield_spread_10y_5y=0.1,
        yield_steepening=True,
        vix=18.0,
        global_headlines=(),
        official_statements=(),
        calendar_payload={"events": [], "source": "frozen", "warning": ""},
        source_status={},
        stale_fields=(),
    )
    builder = Mock(side_effect=lambda symbol, *args, **kwargs: {"symbol": symbol, "events": []})
    monkeypatch.setattr(service, "_build_macro_context", builder)
    monkeypatch.setattr(service, "_get_global_macro_snapshot", lambda **_kwargs: snapshot)

    context = service.latest_macro_context("EUR/USD")
    metadata = context["macro_cache"]
    # The context must NOT silently extend the source's remaining 1s to 5 min.
    assert metadata["expires_at_utc"] == snapshot.expires_at_utc.isoformat()
    assert metadata["expires_at_utc"] < (now + timedelta(seconds=2)).isoformat()

    fingerprint = service._ai_fingerprint(None)
    key = service._macro_context_cache_key("EUR/USD", True, fingerprint)
    entry = service._tier_scores_cache[key]
    assert entry.expires_at_utc == snapshot.expires_at_utc
    # Fresh before the source expiry...
    assert service._fresh_context_entry(key, now, snapshot) is entry
    # ...and a guaranteed miss once the snapshot/source has expired —
    # old data is never silently treated as fresh.
    assert service._fresh_context_entry(
        key, snapshot.expires_at_utc + timedelta(seconds=1), snapshot
    ) is None
    assert builder.call_count == 1


def test_malformed_frame_refresh_keeps_stale_snapshot_and_context_provenance(
    monkeypatch: pytest.MonkeyPatch,
):
    """A malformed (non-empty, no Close) frame during a snapshot refresh must
    not poison the cache: the snapshot keeps its stale values with the ORIGINAL
    origin timestamps, records the real error (ValueError), and that provenance
    propagates raw cache -> snapshot -> macro context."""
    monkeypatch.setattr(NewsService, "_interest_rates", {})
    service = NewsService()
    calendar_patch, headlines_patch, statements_patch = _patch_non_yahoo_sources(service)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, return_value=_frame([4.0, 4.1])):
        first = service._get_global_macro_snapshot()

    def malformed(ticker: str, **_kwargs):
        return pd.DataFrame({"Open": [1.0, 2.0], "High": [1.5, 2.5]})  # no Close

    refresh_at = first.expires_at_utc + timedelta(seconds=1)
    with calendar_patch, headlines_patch, statements_patch, \
         patch(_YF_PATCH_TARGET, side_effect=malformed):
        second = service._get_global_macro_snapshot(now=refresh_at)
        context = service.latest_macro_context("EUR/USD", _snapshot=second)

    # Stale values kept with the ORIGINAL origin and the malformed refresh error.
    assert (second.tnx, second.fvx, second.vix) == (first.tnx, first.fvx, first.vix)
    for name in ("^TNX", "^FVX", "^VIX"):
        assert name in second.stale_fields
        status = second.source_status[name]
        assert status["status"] == "stale"
        assert status["refresh_error_type"] == "ValueError"
        assert status["data_fetched_at_utc"] == first.source_status[name]["data_fetched_at_utc"]
        assert status["origin_expires_at_utc"] == first.source_status[name]["origin_expires_at_utc"]

    # Provenance propagates raw cache -> snapshot -> macro context.
    ctx_status = context["macro_cache"]["source_freshness"]["source_status"]
    for name in ("^TNX", "^FVX", "^VIX"):
        assert ctx_status[name]["status"] == "stale"
        assert ctx_status[name]["refresh_error_type"] == "ValueError"
        assert ctx_status[name]["data_fetched_at_utc"] == first.source_status[name]["data_fetched_at_utc"]
