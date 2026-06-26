"""Tests for forex_factory_client — helper functions and HTML parser."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from services.forex_factory_client import (
    ForexFactoryClient,
    _event_time,
    _is_high_impact,
    clean_text,
    parse_event_time,
)


class TestParseEventTime:
    def test_valid_iso(self):
        result = parse_event_time("2026-06-15T14:30:00Z")
        assert result is not None
        assert result.year == 2026

    def test_with_offset(self):
        result = parse_event_time("2026-06-15T14:30:00+00:00")
        assert result is not None
        assert result.hour == 14

    def test_empty_returns_none(self):
        assert parse_event_time("") is None
        assert parse_event_time("not_a_date") is None


class TestCleanText:
    def test_strips_html_entities(self):
        assert clean_text("Fed&amp;Treasury") == "Fed&Treasury"

    def test_collapses_whitespace(self):
        assert clean_text("  hello   world  ") == "hello world"

    def test_empty(self):
        assert clean_text("") == ""


class TestIsHighImpact:
    def test_high(self):
        assert _is_high_impact("high")

    def test_red(self):
        assert _is_high_impact("red")

    def test_cao(self):
        assert _is_high_impact("cao")

    def test_medium_is_not(self):
        assert not _is_high_impact("medium")

    def test_low_is_not(self):
        assert not _is_high_impact("low")

    def test_empty_is_not(self):
        assert not _is_high_impact("")


class TestEventTime:
    def test_dict_with_time_utc(self):
        event = {"time_utc": "2026-06-15T14:30:00Z"}
        result = _event_time(event)
        assert result is not None
        assert result.year == 2026

    def test_non_dict_returns_none(self):
        assert _event_time("bad") is None

    def test_missing_key_returns_none(self):
        assert _event_time({}) is None


class TestNormalizeCalendarItems:
    def test_normalizes_valid_items(self):
        client = ForexFactoryClient()
        payload = [
            {
                "country": "USD",
                "date": "2026-06-15T14:30:00Z",
                "title": "FOMC Meeting",
                "impact": "high",
                "forecast": "5.5%",
                "previous": "5.5%",
                "actual": "5.5%",
            }
        ]
        result = client._normalize_calendar_items(payload, source="Forex Factory")
        assert len(result) == 1
        item = result[0]
        assert item["currency"] == "USD"
        assert item["event"] == "FOMC Meeting"
        assert item["impact"] == "high"
        assert item["time_utc"] == "2026-06-15T14:30Z"
        assert item["source"] == "Forex Factory"

    def test_skips_non_dict_items(self):
        client = ForexFactoryClient()
        result = client._normalize_calendar_items(["not_a_dict"], source="Test")
        assert result == []

    def test_skips_items_without_currency(self):
        client = ForexFactoryClient()
        payload = [{"title": "No currency", "date": "2026-06-15T14:30:00Z"}]
        result = client._normalize_calendar_items(payload, source="Test")
        assert result == []


class TestSelectCalendarEvents:
    def test_filters_by_currency(self):
        client = ForexFactoryClient()
        rows = [
            {"currency": "USD", "event": "FOMC", "impact": "high", "time_utc": "2026-06-15T14:30Z"},
            {"currency": "EUR", "event": "ECB", "impact": "high", "time_utc": "2026-06-15T14:30Z"},
            {"currency": "JPY", "event": "BOJ", "impact": "medium", "time_utc": "2026-06-15T14:30Z"},
        ]
        result = client._select_calendar_events(["USD"], rows)
        assert len(result) == 1
        assert result[0]["event"] == "FOMC"

    def test_falls_back_to_important_when_no_match(self):
        client = ForexFactoryClient()
        rows = [
            {"currency": "EUR", "event": "ECB", "impact": "low", "time_utc": "2026-06-15T14:30Z"},
            {"currency": "EUR", "event": "CPI", "impact": "high", "time_utc": "2026-06-15T14:30Z"},
        ]
        result = client._select_calendar_events(["USD"], rows)
        assert len(result) == 1
        assert result[0]["event"] == "CPI"


FAKE_FF_HTML = """
<div class="calendar__timezone">Calendar Time Zone: Asia/Bangkok (GMT +7)</div>
<table>
<tr class="calendar__row" data-id="1">
  <td class="calendar__cell calendar__date">Mon Jun 15</td>
  <td class="calendar__time">08:30am</td>
  <td class="calendar__currency">USD</td>
  <td class="calendar__event-title">CPI m/m</td>
  <td class="calendar__impact">
    <span class="calendar__impact-icon--red">High Impact</span>
  </td>
  <td class="calendar__forecast">0.3%</td>
  <td class="calendar__previous">0.2%</td>
  <td class="calendar__actual">0.4%</td>
</tr>
<tr class="calendar__row" data-id="2">
  <td class="calendar__time">All Day</td>
  <td class="calendar__currency">EUR</td>
  <td class="calendar__event">German Prelim GDP</td>
  <td class="calendar__impact">
    <span class="calendar__impact-icon--orange">Medium Impact</span>
  </td>
  <td class="calendar__forecast">0.1%</td>
  <td class="calendar__previous">-0.1%</td>
</tr>
</table>
"""


class TestParseHTML:
    def test_parses_real_html(self):
        client = ForexFactoryClient()
        rows = client._parse_html(FAKE_FF_HTML)
        assert len(rows) >= 1

        usd = [r for r in rows if r["currency"] == "USD"][0]
        assert usd["event"] == "CPI m/m"
        assert usd["impact"] == "High"
        assert usd["forecast"] == "0.3%"
        assert usd["previous"] == "0.2%"
        assert usd["actual"] == "0.4%"
        assert usd["source"] == "Forex Factory HTML"
        assert usd["time_utc"] != ""

    def test_all_day_events_have_no_time(self):
        """All Day events are included but with empty time_utc."""
        client = ForexFactoryClient()
        rows = client._parse_html(FAKE_FF_HTML)
        eur = [r for r in rows if r["currency"] == "EUR"]
        # All Day event is included but without a specific time
        assert len(eur) == 1
        assert eur[0]["time_utc"] == ""


class TestCacheFile:
    def test_cache_file_path_default(self):
        client = ForexFactoryClient()
        path = client._calendar_cache_file()
        assert path.name == "economic_calendar_thisweek.json"
        assert "cache" in str(path)

    def test_cache_file_custom_override(self):
        from pathlib import Path
        ForexFactoryClient.CALENDAR_CACHE_FILE = Path("/tmp/test_calendar.json")
        try:
            client = ForexFactoryClient()
            assert client._calendar_cache_file() == Path("/tmp/test_calendar.json")
        finally:
            ForexFactoryClient.CALENDAR_CACHE_FILE = None
