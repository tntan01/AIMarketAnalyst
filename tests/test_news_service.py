from __future__ import annotations

from datetime import UTC, datetime, timedelta
from io import BytesIO
from urllib.error import HTTPError

import pytest

from services.news_service import NewsService


class _Response:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


@pytest.fixture(autouse=True)
def clear_news_cache(tmp_path) -> None:
    NewsService._calendar_cache.clear()
    NewsService.CALENDAR_CACHE_FILE = tmp_path / "calendar_cache.json"
    yield
    NewsService._calendar_cache.clear()
    NewsService.CALENDAR_CACHE_FILE = None


def test_news_service_filters_forex_factory_events(monkeypatch) -> None:
    future = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
    payload = (
        "["
        f'{{"country":"EUR","title":"ECB Speech","impact":"Medium","date":"{future}","forecast":"","previous":""}},'
        f'{{"country":"JPY","title":"BoJ Event","impact":"High","date":"{future}","forecast":"","previous":""}}'
        "]"
    ).encode("utf-8")

    monkeypatch.setattr("services.news_service.urlopen", lambda request, timeout=10: _Response(payload))

    context = NewsService().latest_macro_context("EUR/USD")

    assert context["source"] == "Forex Factory"
    assert len(context["events"]) == 1
    assert context["events"][0]["currency"] == "EUR"
    assert context["events"][0]["event"] == "ECB Speech"


def test_news_service_returns_no_data_warning_on_fetch_error(monkeypatch) -> None:
    def raise_error(request, timeout=10):
        raise RuntimeError("blocked")

    monkeypatch.setattr("services.news_service.urlopen", raise_error)

    context = NewsService().latest_macro_context("EUR/USD")

    assert context["events"] == []
    assert "Không lấy được lịch kinh tế" in context["warning"]


def test_news_service_keeps_macro_headlines_when_calendar_is_rate_limited(monkeypatch) -> None:
    recent = (datetime.now(UTC) - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    rss_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item><title>BOJ tightening bets rise as Japan wages stay firm</title><source>Reuters</source><link>https://example.com/boj</link><pubDate>{recent}</pubDate></item>
    </channel></rss>""".encode("utf-8")

    def fake_urlopen(request, timeout=10):
        url = getattr(request, "full_url", "")
        if "ff_calendar" in url:
            raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))
        return _Response(rss_payload)

    monkeypatch.setattr("services.news_service.urlopen", fake_urlopen)

    context = NewsService().latest_macro_context("USD/JPY")

    assert context["events"] == []
    assert "HTTP 429" in context["warning"]
    assert context["latest_headlines"]
    assert context["macro_alignment_scores"]["sell"] > context["macro_alignment_scores"]["buy"]


def test_news_service_filters_latest_headlines_to_previous_24_hours(monkeypatch) -> None:
    old = (datetime.now(UTC) - timedelta(hours=30)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    rss_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item><title>Old FX weekly note should be hidden</title><source>Research</source><link>https://example.com/old</link><pubDate>{old}</pubDate></item>
    </channel></rss>""".encode("utf-8")

    def fake_urlopen(request, timeout=10):
        url = getattr(request, "full_url", "")
        if "ff_calendar" in url:
            raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))
        return _Response(rss_payload)

    monkeypatch.setattr("services.news_service.urlopen", fake_urlopen)

    context = NewsService().latest_macro_context("EUR/USD")

    assert context["latest_headlines"] == []


def test_news_service_uses_forex_factory_html_when_json_is_rate_limited(monkeypatch) -> None:
    future = (datetime.now(UTC) + timedelta(hours=6)).isoformat()
    html = f"""
    <table>
      <tr class="calendar__row" data-event-datetime="{future}">
        <td class="calendar__currency">USD</td>
        <td class="calendar__impact"><span class="calendar__impact-icon--red">High Impact Expected</span></td>
        <td class="calendar__event"><span class="calendar__event-title">FOMC Statement</span></td>
        <td class="calendar__forecast">--</td>
        <td class="calendar__previous">--</td>
      </tr>
    </table>
    """.encode("utf-8")

    def fake_urlopen(request, timeout=10):
        url = getattr(request, "full_url", "")
        if "ff_calendar" in url:
            raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))
        return _Response(html)

    monkeypatch.setattr("services.news_service.urlopen", fake_urlopen)

    context = NewsService().latest_macro_context("EUR/USD")

    assert context["source"] == "Forex Factory HTML"
    assert context["events"][0]["currency"] == "USD"
    assert context["events"][0]["event"] == "FOMC Statement"


def test_news_service_uses_file_cache_when_live_calendar_sources_fail(monkeypatch) -> None:
    future = (datetime.now(UTC) + timedelta(hours=8)).isoformat(timespec="minutes").replace("+00:00", "Z")
    NewsService()._store_calendar_cache(
        [
            {
                "source": "Forex Factory",
                "currency": "USD",
                "event": "CPI",
                "impact": "High",
                "time_utc": future,
                "hours_until": 8,
            }
        ]
    )
    NewsService._calendar_cache.clear()

    def fake_urlopen(request, timeout=10):
        raise HTTPError(getattr(request, "full_url", ""), 429, "Too Many Requests", hdrs=None, fp=BytesIO(b""))

    monkeypatch.setattr("services.news_service.urlopen", fake_urlopen)

    context = NewsService().latest_macro_context("EUR/USD")

    assert context["source"] == "Calendar file cache"
    assert context["events"][0]["event"] == "CPI"
    assert "cache" in context["warning"]


def test_news_service_builds_data_quality_flags_for_high_impact_event(monkeypatch) -> None:
    future = (datetime.now(UTC) + timedelta(minutes=20)).isoformat()
    payload = (
        "["
        f'{{"country":"USD","title":"CPI","impact":"High","date":"{future}","forecast":"","previous":""}}'
        "]"
    ).encode("utf-8")
    monkeypatch.setattr("services.news_service.urlopen", lambda request, timeout=10: _Response(payload))

    flags = NewsService().data_quality_flags("EUR/USD")

    assert flags["news_in_3h"] is True
    assert flags["high_impact_event_within_30m"] is True
    assert flags["next_high_impact_event"]["event"] == "CPI"
    assert flags["resume_after"]


def test_news_service_adds_macro_headlines_themes_hotspots_and_scores(monkeypatch) -> None:
    future = (datetime.now(UTC) + timedelta(hours=12)).isoformat()
    recent = (datetime.now(UTC) - timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    ff_payload = (
        "["
        f'{{"country":"JPY","title":"Tokyo CPI","impact":"High","date":"{future}","forecast":"","previous":""}}'
        "]"
    ).encode("utf-8")
    rss_payload = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss><channel>
      <item><title>BOJ tightening bets rise as Japan wages and Tokyo CPI stay firm</title><source>Reuters</source><link>https://example.com/boj</link><pubDate>{recent}</pubDate></item>
      <item><title>Oil jumps on Middle East geopolitical risk</title><source>Investing.com</source><link>https://example.com/oil</link><pubDate>{recent}</pubDate></item>
    </channel></rss>""".encode("utf-8")

    def fake_urlopen(request, timeout=10):
        url = getattr(request, "full_url", "")
        return _Response(ff_payload if "ff_calendar" in url else rss_payload)

    monkeypatch.setattr("services.news_service.urlopen", fake_urlopen)

    context = NewsService().latest_macro_context("USD/JPY")

    assert context["latest_headlines"]
    assert context["macro_themes"]
    assert context["geopolitical_hotspots"]
    assert context["macro_alignment_scores"]["sell"] > context["macro_alignment_scores"]["buy"]
