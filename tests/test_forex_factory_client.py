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


# ---------------------------------------------------------------------------
# Real ForexFactory HTML fixture with rowspan (captured from live site)
# ---------------------------------------------------------------------------

REAL_FF_HTML_ROWSPAN = """
<div class="calendar__timezone">Calendar Time Zone: Asia/Bangkok (GMT +7)</div>
<table>
<tr class="calendar__row" data-id="1" data-event-datetime="2026-07-20 08:00">
  <td class="calendar__cell calendar__date" rowspan="2">Mon Jul 20</td>
  <td class="calendar__time calendar__cell" rowspan="2">8:00am</td>
  <td class="calendar__currency calendar__cell">CNY</td>
  <td class="calendar__event-title calendar__cell">
    <span>1-y Loan Prime Rate</span>
  </td>
  <td class="calendar__impact calendar__cell">
    <span class="calendar__impact-icon--yellow"></span>
  </td>
  <td class="calendar__forecast calendar__cell">3.00%</td>
  <td class="calendar__previous calendar__cell">3.00%</td>
  <td class="calendar__actual calendar__cell revised">3.00%</td>
</tr>
<tr class="calendar__row" data-id="2" data-event-datetime="2026-07-20 08:00">
  <!-- date: rowspan from above -->
  <!-- time: rowspan from above -->
  <td class="calendar__currency calendar__cell">CNY</td>
  <td class="calendar__event-title calendar__cell">
    <span>5-y Loan Prime Rate</span>
  </td>
  <td class="calendar__impact calendar__cell">
    <span class="calendar__impact-icon--yellow"></span>
  </td>
  <td class="calendar__forecast calendar__cell">3.50%</td>
  <td class="calendar__previous calendar__cell">3.50%</td>
  <td class="calendar__actual calendar__cell revised">3.50%</td>
</tr>
</table>
"""


class TestRowspanParsing:
    """Tests for HTML parser with rowspan support (_RowContext architecture)."""

    def test_rowspan_time_inheritance(self):
        """Both events sharing a time slot get the same time_utc via rowspan."""
        client = ForexFactoryClient()
        rows = client._parse_html(REAL_FF_HTML_ROWSPAN)
        assert len(rows) == 2

        ev1 = [r for r in rows if "1-y" in str(r["event"])][0]
        ev5 = [r for r in rows if "5-y" in str(r["event"])][0]

        assert ev1["time_utc"] != "", "1-y should have time_utc"
        assert ev5["time_utc"] != "", "5-y should have time_utc (inherited via rowspan)"
        assert ev1["time_utc"] == ev5["time_utc"], (
            f"Both events at same time slot: {ev1['time_utc']} != {ev5['time_utc']}"
        )

    def test_rowspan_actual_values_not_mixed(self):
        """Each event keeps its own actual/forecast/previous — not inherited."""
        client = ForexFactoryClient()
        rows = client._parse_html(REAL_FF_HTML_ROWSPAN)

        ev1 = [r for r in rows if "1-y" in str(r["event"])][0]
        ev5 = [r for r in rows if "5-y" in str(r["event"])][0]

        assert ev1["actual"] == "3.00%", f"1-y actual: {ev1['actual']}"
        assert ev5["actual"] == "3.50%", f"5-y actual: {ev5['actual']}"
        assert ev1["forecast"] == "3.00%"
        assert ev5["forecast"] == "3.50%"
        assert ev1["previous"] == "3.00%"
        assert ev5["previous"] == "3.50%"

    def test_rowspan_both_events_parsed(self):
        """Both events appear in output with correct currency and event names."""
        client = ForexFactoryClient()
        rows = client._parse_html(REAL_FF_HTML_ROWSPAN)

        currencies = [r["currency"] for r in rows]
        events = [r["event"] for r in rows]
        assert currencies == ["CNY", "CNY"]
        assert "1-y Loan Prime Rate" in events
        assert "5-y Loan Prime Rate" in events

    def test_rowspan_output_schema_intact(self):
        """Output dict has all required fields with correct types after rowspan."""
        client = ForexFactoryClient()
        rows = client._parse_html(REAL_FF_HTML_ROWSPAN)

        for row in rows:
            assert isinstance(row, dict)
            assert "source" in row and row["source"] == "Forex Factory HTML"
            assert "currency" in row and isinstance(row["currency"], str)
            assert "event" in row and isinstance(row["event"], str)
            assert "impact" in row and isinstance(row["impact"], str)
            assert "time_utc" in row and isinstance(row["time_utc"], str)
            assert "hours_until" in row
            assert "forecast" in row and isinstance(row["forecast"], str)
            assert "previous" in row and isinstance(row["previous"], str)
            assert "actual" in row and isinstance(row["actual"], str)


class TestParserRobustness:
    """Parser resilience against real-world HTML variations."""

    def test_nested_span_in_cells(self):
        """Cells with nested <span> still yield correct text."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date">Mon Jul 20</td>
          <td class="calendar__time">10:00am</td>
          <td class="calendar__currency">USD</td>
          <td class="calendar__event"><span><span>Nested Event</span></span></td>
          <td class="calendar__actual"><span class="revised">5.5%</span></td>
          <td class="calendar__forecast"><span>5.4%</span></td>
          <td class="calendar__previous"><span>5.3%</span></td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 1
        assert rows[0]["event"] == "Nested Event"
        assert rows[0]["actual"] == "5.5%"
        assert rows[0]["forecast"] == "5.4%"
        assert rows[0]["previous"] == "5.3%"

    def test_nested_div_in_cells(self):
        """Cells with nested <div> still yield correct text."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date">Mon Jul 20</td>
          <td class="calendar__time">10:00am</td>
          <td class="calendar__currency">EUR</td>
          <td class="calendar__event"><div>GDP Report</div></td>
          <td class="calendar__actual"><div>1.2%</div></td>
          <td class="calendar__forecast">1.0%</td>
          <td class="calendar__previous">0.9%</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 1
        assert rows[0]["event"] == "GDP Report"
        assert rows[0]["actual"] == "1.2%"

    def test_strong_and_em_in_cells(self):
        """Cells with <strong>/<em> yield text without tags."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date">Mon Jul 20</td>
          <td class="calendar__time">10:00am</td>
          <td class="calendar__currency">GBP</td>
          <td class="calendar__event"><strong>CPI</strong> <em>y/y</em></td>
          <td class="calendar__actual"><strong>2.1%</strong></td>
          <td class="calendar__forecast">2.0%</td>
          <td class="calendar__previous">1.9%</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 1
        assert rows[0]["event"] == "CPI y/y"
        assert rows[0]["actual"] == "2.1%"

    def test_missing_optional_cells_forecast_previous_actual(self):
        """Rows without forecast/previous/actual return empty strings."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date">Mon Jul 20</td>
          <td class="calendar__time">All Day</td>
          <td class="calendar__currency">JPY</td>
          <td class="calendar__event">Bank Holiday</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 1
        assert rows[0]["forecast"] == ""
        assert rows[0]["previous"] == ""
        assert rows[0]["actual"] == ""
        assert rows[0]["time_utc"] == ""

    def test_missing_impact_cell(self):
        """Row without impact cell returns empty string."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date">Mon Jul 20</td>
          <td class="calendar__time">10:00am</td>
          <td class="calendar__currency">NZD</td>
          <td class="calendar__event">Trade Balance</td>
          <td class="calendar__actual">-1.2B</td>
          <td class="calendar__forecast">-0.8B</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 1
        assert rows[0]["impact"] == ""

    def test_rowspan_triple_events(self):
        """Three events sharing the same time via rowspan="3"."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: America/New_York (GMT -4)</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date" rowspan="3">Wed Jul 15</td>
          <td class="calendar__time" rowspan="3">8:30am</td>
          <td class="calendar__currency">USD</td>
          <td class="calendar__event">CPI m/m</td>
          <td class="calendar__impact"><span class="calendar__impact-icon--red"></span></td>
          <td class="calendar__actual">0.3%</td>
          <td class="calendar__forecast">0.2%</td>
          <td class="calendar__previous">0.1%</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__currency">USD</td>
          <td class="calendar__event">Core CPI m/m</td>
          <td class="calendar__impact"><span class="calendar__impact-icon--red"></span></td>
          <td class="calendar__actual">0.3%</td>
          <td class="calendar__forecast">0.2%</td>
          <td class="calendar__previous">0.1%</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__currency">USD</td>
          <td class="calendar__event">Real Earnings m/m</td>
          <td class="calendar__impact"><span class="calendar__impact-icon--yellow"></span></td>
          <td class="calendar__actual">0.1%</td>
          <td class="calendar__forecast">0.0%</td>
          <td class="calendar__previous">-0.2%</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 3

        events = {r["event"]: r for r in rows}
        assert "CPI m/m" in events
        assert "Core CPI m/m" in events
        assert "Real Earnings m/m" in events

        # All 3 share the same time (inherited via rowspan="3")
        times = {r["time_utc"] for r in rows}
        assert len(times) == 1, f"All 3 events should share same time, got: {times}"
        assert "" not in times

        # Each has correct per-event data (not inherited)
        assert events["CPI m/m"]["actual"] == "0.3%"
        assert events["Core CPI m/m"]["actual"] == "0.3%"
        assert events["Real Earnings m/m"]["actual"] == "0.1%"
        assert events["CPI m/m"]["forecast"] == "0.2%"
        assert events["Core CPI m/m"]["forecast"] == "0.2%"
        assert events["Real Earnings m/m"]["forecast"] == "0.0%"
        assert events["CPI m/m"]["previous"] == "0.1%"
        assert events["Core CPI m/m"]["previous"] == "0.1%"
        assert events["Real Earnings m/m"]["previous"] == "-0.2%"

        # Impact is per-row (explicit in each)
        assert events["CPI m/m"]["impact"] == "High"
        assert events["Core CPI m/m"]["impact"] == "High"
        assert events["Real Earnings m/m"]["impact"] == "Low"

        for name, r in events.items():
            assert r["currency"] == "USD"

    def test_rowspan_time_not_inherited_across_dates(self):
        """Time does NOT carry over to a new date."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date" rowspan="2">Mon Jul 20</td>
          <td class="calendar__time" rowspan="2">8:00am</td>
          <td class="calendar__currency">CNY</td>
          <td class="calendar__event">Event A</td>
          <td class="calendar__actual">1.0%</td>
          <td class="calendar__forecast">1.0%</td>
          <td class="calendar__previous">1.0%</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__currency">CNY</td>
          <td class="calendar__event">Event B</td>
          <td class="calendar__actual">2.0%</td>
          <td class="calendar__forecast">2.0%</td>
          <td class="calendar__previous">2.0%</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__date">Tue Jul 21</td>
          <td class="calendar__time">10:00am</td>
          <td class="calendar__currency">USD</td>
          <td class="calendar__event">Event C</td>
          <td class="calendar__actual">3.0%</td>
          <td class="calendar__forecast">3.0%</td>
          <td class="calendar__previous">3.0%</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 3

        ev_a = [r for r in rows if r["event"] == "Event A"][0]
        ev_b = [r for r in rows if r["event"] == "Event B"][0]
        ev_c = [r for r in rows if r["event"] == "Event C"][0]

        # A and B share time (rowspan)
        assert ev_a["time_utc"] == ev_b["time_utc"]
        # C is on a different date — must NOT inherit 8:00am
        assert ev_c["time_utc"] != ev_a["time_utc"]

    def test_rowspan_all_day_does_not_inherit_time(self):
        """All Day event resets time context; next event doesn't get stale time."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date" rowspan="3">Mon Jul 20</td>
          <td class="calendar__time">8:00am</td>
          <td class="calendar__currency">USD</td>
          <td class="calendar__event">Timed Event</td>
          <td class="calendar__actual">1.0%</td>
          <td class="calendar__forecast">1.0%</td>
          <td class="calendar__previous">1.0%</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__time">All Day</td>
          <td class="calendar__currency">EUR</td>
          <td class="calendar__event">Holiday</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__time">10:00am</td>
          <td class="calendar__currency">GBP</td>
          <td class="calendar__event">After All Day</td>
          <td class="calendar__actual">2.0%</td>
          <td class="calendar__forecast">2.0%</td>
          <td class="calendar__previous">2.0%</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 3

        timed_ev = [r for r in rows if r["event"] == "Timed Event"][0]
        holiday = [r for r in rows if r["event"] == "Holiday"][0]
        after = [r for r in rows if r["event"] == "After All Day"][0]

        assert timed_ev["time_utc"] != ""
        assert holiday["time_utc"] == "", "All Day should not inherit time from previous row"
        assert after["time_utc"] != "", "Timed event after All Day should have its own time"
        assert after["time_utc"] != timed_ev["time_utc"], (
            "Event after All Day must NOT inherit time from before All Day"
        )

    def test_tentative_resets_time_context(self):
        """Tentative event resets time context same as All Day."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date" rowspan="3">Mon Jul 20</td>
          <td class="calendar__time">9:00am</td>
          <td class="calendar__currency">USD</td>
          <td class="calendar__event">Timed Event</td>
          <td class="calendar__actual">1.0%</td>
          <td class="calendar__forecast">1.0%</td>
          <td class="calendar__previous">1.0%</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__time">Tentative</td>
          <td class="calendar__currency">CAD</td>
          <td class="calendar__event">Tentative Event</td>
        </tr>
        <tr class="calendar__row">
          <td class="calendar__time">11:00am</td>
          <td class="calendar__currency">GBP</td>
          <td class="calendar__event">After Tentative</td>
          <td class="calendar__actual">2.0%</td>
          <td class="calendar__forecast">2.0%</td>
          <td class="calendar__previous">2.0%</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 3

        tentative = [r for r in rows if r["event"] == "Tentative Event"][0]
        after = [r for r in rows if r["event"] == "After Tentative"][0]

        assert tentative["time_utc"] == "", "Tentative should have no time"
        assert after["time_utc"] != "", "Timed event after Tentative should have its own time"

    def test_html_entity_and_unicode(self):
        """HTML entities and Unicode characters are decoded correctly."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date">Mon Jul 20</td>
          <td class="calendar__time">10:00am</td>
          <td class="calendar__currency">EUR</td>
          <td class="calendar__event">German GfK Consumer Climate&amp;Sentiment</td>
          <td class="calendar__actual">&euro;1.2B</td>
          <td class="calendar__forecast">1.0B</td>
          <td class="calendar__previous">0.9B</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 1
        # &amp; should be decoded to &
        assert "&amp;" not in rows[0]["event"]
        assert "Climate" in rows[0]["event"]
        assert "Sentiment" in rows[0]["event"]

    def test_empty_html_returns_empty_list(self):
        """Parser handles empty/missing table gracefully."""
        client = ForexFactoryClient()
        rows = client._parse_html("<html><body>No calendar here</body></html>")
        assert rows == []

    def test_malformed_html_does_not_crash(self):
        """Parser handles malformed HTML without raising exceptions."""
        html = """
        <div class="calendar__timezone">UTC</div>
        <table>
        <tr class="calendar__row">
          <td class="calendar__date">Mon Jul 20
          <td class="calendar__time">10:00am
          <td class="calendar__currency">USD
          <td class="calendar__event">Unclosed Tags
          <td class="calendar__actual">1.5%
        </tr>
        <tr class="calendar__row">
          <td class="calendar__currency">GBP</td>
          <td class="calendar__event">Missing Close</td>
        </table>"""
        client = ForexFactoryClient()
        # Must not raise
        rows = client._parse_html(html)
        assert isinstance(rows, list)

    def test_class_name_with_extra_classes(self):
        """Parser still matches when FF adds extra CSS classes."""
        html = """
        <div class="calendar__timezone">Calendar Time Zone: UTC</div>
        <table>
        <tr class="calendar__row new-feature extra">
          <td class="calendar__cell calendar__date today">Mon Jul 20</td>
          <td class="calendar__time calendar__cell highlighted">10:00am</td>
          <td class="calendar__currency calendar__cell">USD</td>
          <td class="calendar__event-title calendar__cell featured">Event With Extra Classes</td>
          <td class="calendar__actual calendar__cell revised bold">2.0%</td>
          <td class="calendar__forecast calendar__cell">1.5%</td>
          <td class="calendar__previous calendar__cell">1.0%</td>
        </tr>
        </table>"""
        client = ForexFactoryClient()
        rows = client._parse_html(html)
        assert len(rows) == 1
        assert rows[0]["event"] == "Event With Extra Classes"
        assert rows[0]["actual"] == "2.0%"

    def test_impact_variants_all_mapped(self):
        """All impact indicator variants are correctly classified."""
        test_cases = [
            ('<span class="calendar__impact-icon--red">High Impact</span>', "High"),
            ('<span class="calendar__impact-icon--orange">Medium Impact</span>', "Medium"),
            ('<span class="calendar__impact-icon--yellow">Low Impact</span>', "Low"),
            ('<span class="ff-impact-red"></span>', "High"),
            ('<span class="ff-impact-orange"></span>', "Medium"),
            ('<span class="ff-impact-yellow"></span>', "Low"),
            ("", ""),
        ]
        for impact_html, expected in test_cases:
            html = f"""
            <div class="calendar__timezone">UTC</div>
            <table>
            <tr class="calendar__row">
              <td class="calendar__date">Mon Jul 20</td>
              <td class="calendar__time">10:00am</td>
              <td class="calendar__currency">USD</td>
              <td class="calendar__event">Test Event</td>
              <td class="calendar__impact">{impact_html}</td>
              <td class="calendar__actual">1.0%</td>
              <td class="calendar__forecast">1.0%</td>
              <td class="calendar__previous">1.0%</td>
            </tr>
            </table>"""
            client = ForexFactoryClient()
            rows = client._parse_html(html)
            assert rows[0]["impact"] == expected, f"impact_html={impact_html!r} -> {rows[0]['impact']!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# Merge engine regression tests (Phase 3)
# ---------------------------------------------------------------------------


class TestMergeEngine:
    """Verify _merge_actual_from_html correctness per the confidence model.

    - HIGH confidence (currency + norm_event + date): fill empty + overwrite
    - LOW confidence (time proximity): REMOVED — must NOT copy actual
    """

    @staticmethod
    def _make_json_row(currency, event, actual, forecast, previous, time_utc):
        return {
            "currency": currency,
            "event": event,
            "actual": actual,
            "forecast": forecast,
            "previous": previous,
            "time_utc": time_utc,
            "source": "Test",
        }

    @staticmethod
    def _make_html_row(currency, event, actual, time_utc):
        return {
            "currency": currency,
            "event": event,
            "actual": actual,
            "time_utc": time_utc,
        }

    # --- CASE 1: CNY 1-y + 5-y Loan Prime Rate (same time, same currency) ---

    def test_cny_loan_prime_rate_no_actual_copy(self):
        """Two CNY events at same time must NOT copy actual between them."""
        client = ForexFactoryClient()
        json_rows = [
            self._make_json_row("CNY", "1-y Loan Prime Rate", "", "3.00%", "3.00%", "2026-07-20T01:00Z"),
            self._make_json_row("CNY", "5-y Loan Prime Rate", "", "3.50%", "3.50%", "2026-07-20T01:00Z"),
        ]
        html_rows = [
            self._make_html_row("CNY", "1-y Loan Prime Rate", "3.00%", "2026-07-20T01:00Z"),
            self._make_html_row("CNY", "5-y Loan Prime Rate", "3.50%", "2026-07-20T01:00Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)

        ev1 = [r for r in json_rows if "1-y" in str(r["event"])][0]
        ev5 = [r for r in json_rows if "5-y" in str(r["event"])][0]
        assert ev1["actual"] == "3.00%", f"1-y should be 3.00%, got {ev1['actual']}"
        assert ev5["actual"] == "3.50%", f"5-y should be 3.50%, got {ev5['actual']}"

    def test_cny_loan_prime_rate_with_json_empty_actuals(self):
        """Step 3 is removed — if Step 1 misses, actual stays empty (no wrong copy)."""
        client = ForexFactoryClient()
        # JSON uses "CNY 5-y" (with currency prefix) — won't normalize-match HTML "5-y"
        json_rows = [
            self._make_json_row("CNY", "CNY 1-y Loan Prime Rate", "", "3.00%", "3.00%", "2026-07-20T01:00Z"),
            self._make_json_row("CNY", "CNY 5-y Loan Prime Rate", "", "3.50%", "3.50%", "2026-07-20T01:00Z"),
        ]
        html_rows = [
            self._make_html_row("CNY", "1-y Loan Prime Rate", "3.00%", "2026-07-20T01:00Z"),
            self._make_html_row("CNY", "5-y Loan Prime Rate", "3.50%", "2026-07-20T01:00Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)

        ev5 = [r for r in json_rows if "5-y" in str(r["event"])][0]
        # With Step 3 removed, if names don't match → actual stays empty
        # This is correct: empty is better than wrong
        assert ev5["actual"] in ("", "3.50%"), (
            f"5-y actual should be empty (no match) or 3.50% (if name matched), got {ev5['actual']}"
        )

    # --- CASE 2: USD NFP + Unemployment + Earnings (same time, same currency) ---

    def test_usd_nfp_triple_no_actual_copy(self):
        """Three USD events at 8:30am must each get their own actual."""
        client = ForexFactoryClient()
        json_rows = [
            self._make_json_row("USD", "Nonfarm Payrolls", "", "200K", "180K", "2026-07-10T12:30Z"),
            self._make_json_row("USD", "Unemployment Rate", "", "3.8%", "3.9%", "2026-07-10T12:30Z"),
            self._make_json_row("USD", "Average Hourly Earnings m/m", "", "0.3%", "0.2%", "2026-07-10T12:30Z"),
        ]
        html_rows = [
            self._make_html_row("USD", "Nonfarm Payrolls", "210K", "2026-07-10T12:30Z"),
            self._make_html_row("USD", "Unemployment Rate", "3.7%", "2026-07-10T12:30Z"),
            self._make_html_row("USD", "Average Hourly Earnings m/m", "0.4%", "2026-07-10T12:30Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)

        nfp = [r for r in json_rows if "Nonfarm" in str(r["event"])][0]
        unemp = [r for r in json_rows if "Unemployment" in str(r["event"])][0]
        ahe = [r for r in json_rows if "Hourly" in str(r["event"])][0]
        assert nfp["actual"] == "210K"
        assert unemp["actual"] == "3.7%"
        assert ahe["actual"] == "0.4%"

    # --- CASE 3: USD CPI + Core CPI (same time) ---

    def test_usd_cpi_pair_no_actual_copy(self):
        """CPI m/m and Core CPI m/m must not share actual values."""
        client = ForexFactoryClient()
        json_rows = [
            self._make_json_row("USD", "CPI m/m", "", "0.2%", "0.1%", "2026-07-15T12:30Z"),
            self._make_json_row("USD", "Core CPI m/m", "", "0.2%", "0.1%", "2026-07-15T12:30Z"),
        ]
        html_rows = [
            self._make_html_row("USD", "CPI m/m", "0.3%", "2026-07-15T12:30Z"),
            self._make_html_row("USD", "Core CPI m/m", "0.3%", "2026-07-15T12:30Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)

        cpi = [r for r in json_rows if r["event"] == "CPI m/m"][0]
        core = [r for r in json_rows if r["event"] == "Core CPI m/m"][0]
        assert cpi["actual"] == "0.3%"
        assert core["actual"] == "0.3%"

    # --- CASE 4: CAD CPI + Median + Trimmed (same time) ---

    def test_cad_cpi_triple_no_actual_copy(self):
        """Three CAD CPI variants at same time must each get own actual."""
        client = ForexFactoryClient()
        json_rows = [
            self._make_json_row("CAD", "CPI m/m", "", "0.2%", "0.3%", "2026-07-15T12:30Z"),
            self._make_json_row("CAD", "Median CPI y/y", "", "2.6%", "2.7%", "2026-07-15T12:30Z"),
            self._make_json_row("CAD", "Trimmed CPI y/y", "", "2.8%", "2.9%", "2026-07-15T12:30Z"),
        ]
        html_rows = [
            self._make_html_row("CAD", "CPI m/m", "0.1%", "2026-07-15T12:30Z"),
            self._make_html_row("CAD", "Median CPI y/y", "2.5%", "2026-07-15T12:30Z"),
            self._make_html_row("CAD", "Trimmed CPI y/y", "2.7%", "2026-07-15T12:30Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)

        cpi = [r for r in json_rows if r["event"] == "CPI m/m"][0]
        median = [r for r in json_rows if r["event"] == "Median CPI y/y"][0]
        trimmed = [r for r in json_rows if r["event"] == "Trimmed CPI y/y"][0]
        assert cpi["actual"] == "0.1%"
        assert median["actual"] == "2.5%"
        assert trimmed["actual"] == "2.7%"

    # --- CASE 5: Corrupted cache self-heals via High Confidence overwrite ---

    def test_self_heal_corrupted_cache(self):
        """Corrupted actual in cache is overwritten when HTML has different value."""
        client = ForexFactoryClient()
        # Simulate: cache has wrong actual='3.00%' for 5-y (from previous bug)
        json_rows = [
            self._make_json_row("CNY", "1-y Loan Prime Rate", "3.00%", "3.00%", "3.00%", "2026-07-20T01:00Z"),
            self._make_json_row("CNY", "5-y Loan Prime Rate", "3.00%", "3.50%", "3.50%", "2026-07-20T01:00Z"),
        ]
        html_rows = [
            self._make_html_row("CNY", "1-y Loan Prime Rate", "3.00%", "2026-07-20T01:00Z"),
            self._make_html_row("CNY", "5-y Loan Prime Rate", "3.50%", "2026-07-20T01:00Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)

        ev5 = [r for r in json_rows if "5-y" in str(r["event"])][0]
        # High Confidence match: HTML 3.50% overwrites corrupted cache 3.00%
        assert ev5["actual"] == "3.50%", (
            f"Cache should self-heal: 3.00% -> 3.50%, got {ev5['actual']}"
        )

    def test_self_heal_does_not_change_correct_cache(self):
        """When cache and HTML agree, no unnecessary overwrite (idempotent)."""
        client = ForexFactoryClient()
        json_rows = [
            self._make_json_row("CNY", "1-y Loan Prime Rate", "3.00%", "3.00%", "3.00%", "2026-07-20T01:00Z"),
        ]
        html_rows = [
            self._make_html_row("CNY", "1-y Loan Prime Rate", "3.00%", "2026-07-20T01:00Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)
        assert json_rows[0]["actual"] == "3.00%"  # unchanged

    # --- CASE 6: Medium confidence does not overwrite ---

    def test_no_overwrite_on_different_source_name(self):
        """When JSON and HTML event names differ enough to miss Step 1,
        the existing actual is preserved (not overwritten by time match)."""
        client = ForexFactoryClient()
        # Event names are completely different — no High Confidence match possible
        json_rows = [
            self._make_json_row("USD", "Federal Funds Rate Decision", "5.50%", "5.50%", "5.50%", "2026-07-10T18:00Z"),
        ]
        html_rows = [
            self._make_html_row("USD", "FOMC Interest Rate Decision", "5.25%", "2026-07-10T18:00Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)
        # Names don't normalize-match → no High Confidence → preserve existing
        # (The correct value is preserved rather than blindly overwritten)
        assert json_rows[0]["actual"] == "5.50%"

    def test_low_confidence_time_match_not_used(self):
        """Step 3 is removed — time-proximity alone never copies actual."""
        client = ForexFactoryClient()
        json_rows = [
            self._make_json_row("USD", "CPI m/m", "", "0.2%", "0.1%", "2026-07-15T12:30Z"),
        ]
        html_rows = [
            # Different event name, same time — Step 3 would have copied this
            self._make_html_row("USD", "Core CPI m/m", "0.3%", "2026-07-15T12:30Z"),
        ]
        client._merge_actual_from_html(json_rows, html_rows)
        # Step 3 removed → no match → actual stays empty (honest empty, not wrong data)
        assert json_rows[0]["actual"] == "", (
            f"Step 3 is removed; actual should stay empty, got {json_rows[0]['actual']}"
        )


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
