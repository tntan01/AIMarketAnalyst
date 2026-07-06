"""Test fix for BUG #1: Persistent calendar cache accumulates past events.

Phuong an A: _store_calendar_cache always merges (not just same date),
with 7-day TTL cleanup.
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta, UTC
from pathlib import Path

from services.forex_factory_client import ForexFactoryClient


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_event(currency: str, title: str, time_str: str, actual: str = "",
                forecast: str = "", previous: str = "") -> dict[str, object]:
    return {
        "time_utc": time_str,
        "currency": currency,
        "event": title,
        "actual": actual,
        "forecast": forecast,
        "previous": previous,
        "impact": "medium",
    }


def _make_rows(*events: dict) -> list[dict[str, object]]:
    return [dict(e) for e in events]


# ---------------------------------------------------------------------------
# _store_calendar_cache — merge & cleanup
# ---------------------------------------------------------------------------


def test_store_cache_merges_with_existing_file():
    """New rows are merged into existing cache (not overwritten)."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        # Write initial cache with 2 events
        old_events = [
            _make_event("USD", "Old Event 1", "2026-07-01T10:00:00Z"),
            _make_event("EUR", "Old Event 2", "2026-07-02T12:00:00Z"),
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": "20260701",
                "stored_utc": "2026-07-01T00:00:00+00:00",
                "rows": old_events,
            }, f)

        # Store new rows (should merge, not overwrite)
        new_events = [
            _make_event("GBP", "New Event 1", "2026-07-05T14:00:00Z"),
        ]
        ff._store_calendar_cache(new_events)

        # Read back
        saved = ff._read_calendar_cache_file()
        saved_rows = saved["rows"]

        # Should have all 3 events (2 old + 1 new)
        assert len(saved_rows) == 3, f"Expected 3 rows, got {len(saved_rows)}"
        titles = {r["event"] for r in saved_rows}
        assert "Old Event 1" in titles
        assert "Old Event 2" in titles
        assert "New Event 1" in titles


def test_store_cache_dedup_by_key():
    """Duplicate events (same time+currency+event) are not duplicated."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        # Initial cache
        old_events = [
            _make_event("USD", "NFP", "2026-07-03T12:30:00Z"),
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": "20260701",
                "stored_utc": "2026-07-01T00:00:00+00:00",
                "rows": old_events,
            }, f)

        # Store same event again
        new_events = [
            _make_event("USD", "NFP", "2026-07-03T12:30:00Z"),
        ]
        ff._store_calendar_cache(new_events)

        saved = ff._read_calendar_cache_file()
        saved_rows = saved["rows"]
        assert len(saved_rows) == 1, f"Expected 1 row (dedup), got {len(saved_rows)}"


def test_store_cache_cleans_up_old_events():
    """Events older than 7 days are removed."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        now = datetime.now(UTC)

        # Old cache with events from 10 days ago
        old_time = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_events = [
            _make_event("USD", "Very Old Event", old_time),
            _make_event("EUR", "Also Old", (now - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": (now - timedelta(days=10)).strftime("%Y%m%d"),
                "stored_utc": (now - timedelta(days=10)).isoformat(),
                "rows": old_events,
            }, f)

        # Store new event from today
        new_time = (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        new_events = [
            _make_event("GBP", "Future Event", new_time),
        ]
        ff._store_calendar_cache(new_events)

        saved = ff._read_calendar_cache_file()
        saved_rows = saved["rows"]

        # Only the new event should remain (old ones cleaned up)
        assert len(saved_rows) == 1, f"Expected 1 row after cleanup, got {len(saved_rows)}"
        assert saved_rows[0]["event"] == "Future Event"


def test_store_cache_preserves_events_within_7_days():
    """Events within 7 days are preserved."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        now = datetime.now(UTC)

        # Events from 3 and 5 days ago
        old_events = [
            _make_event("USD", "Event 3d ago", (now - timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")),
            _make_event("EUR", "Event 5d ago", (now - timedelta(days=5)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": (now - timedelta(days=3)).strftime("%Y%m%d"),
                "stored_utc": (now - timedelta(days=3)).isoformat(),
                "rows": old_events,
            }, f)

        # Store new event
        new_events = [
            _make_event("GBP", "Today Event", (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")),
        ]
        ff._store_calendar_cache(new_events)

        saved = ff._read_calendar_cache_file()
        saved_rows = saved["rows"]

        # All 3 events should remain
        assert len(saved_rows) == 3, f"Expected 3 rows, got {len(saved_rows)}"
        titles = {r["event"] for r in saved_rows}
        assert "Event 3d ago" in titles
        assert "Event 5d ago" in titles
        assert "Today Event" in titles


def test_store_cache_preserves_events_without_time():
    """Events without time_utc are preserved (not cleaned up)."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        old_events = [
            {"currency": "USD", "event": "No Time Event", "impact": "high"},
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": "20260701",
                "stored_utc": "2026-07-01T00:00:00+00:00",
                "rows": old_events,
            }, f)

        new_events = [
            _make_event("GBP", "Has Time", "2026-07-06T10:00:00Z"),
        ]
        ff._store_calendar_cache(new_events)

        saved = ff._read_calendar_cache_file()
        saved_rows = saved["rows"]
        assert len(saved_rows) == 2, f"Expected 2 rows, got {len(saved_rows)}"


def test_store_cache_no_existing_file_creates_new():
    """When no cache file exists, creates a new one."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        new_events = [
            _make_event("USD", "First Event", "2026-07-06T10:00:00Z"),
        ]
        ff._store_calendar_cache(new_events)

        saved = ff._read_calendar_cache_file()
        assert saved is not None
        assert len(saved["rows"]) == 1


def test_store_cache_empty_rows_preserves_existing():
    """Empty rows -> return early, don't touch existing cache."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        old_events = [
            _make_event("USD", "Existing", "2026-07-04T10:00:00Z"),
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": "20260704",
                "stored_utc": "2026-07-04T00:00:00+00:00",
                "rows": old_events,
            }, f)

        # Store empty -> should be no-op
        ff._store_calendar_cache([])

        saved = ff._read_calendar_cache_file()
        assert len(saved["rows"]) == 1
        assert saved["rows"][0]["event"] == "Existing"


# ---------------------------------------------------------------------------
# _cached_calendar_events — still works
# ---------------------------------------------------------------------------


def test_cached_calendar_events_reads_file():
    """_cached_calendar_events returns events from persistent file."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        now = datetime.now(UTC)
        events = [
            _make_event("USD", "File Event", now.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": now.strftime("%Y%m%d"),
                "stored_utc": now.isoformat(),
                "rows": events,
            }, f)

        # Clear in-memory cache
        ff._calendar_cache = {}
        result = ff._cached_calendar_events()
        assert len(result) == 1
        assert result[0]["event"] == "File Event"


def test_cached_calendar_events_expired_file_returns_empty():
    """Expired file cache -> returns empty (forces re-fetch)."""
    ff = ForexFactoryClient()

    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = Path(tmpdir) / "test_calendar.json"
        ff.CALENDAR_CACHE_FILE = cache_file

        old_time = datetime.now(UTC) - timedelta(hours=25)  # exceeds 24h TTL
        events = [
            _make_event("USD", "Stale Event", old_time.strftime("%Y-%m-%dT%H:%M:%SZ")),
        ]
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "date": old_time.strftime("%Y%m%d"),
                "stored_utc": old_time.isoformat(),
                "rows": events,
            }, f)

        ff._calendar_cache = {}
        result = ff._cached_calendar_events()
        # File is expired -> returns empty, will trigger re-fetch + merge
        assert result == []


# ---------------------------------------------------------------------------
# runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    tests = [
        test_store_cache_merges_with_existing_file,
        test_store_cache_dedup_by_key,
        test_store_cache_cleans_up_old_events,
        test_store_cache_preserves_events_within_7_days,
        test_store_cache_preserves_events_without_time,
        test_store_cache_no_existing_file_creates_new,
        test_store_cache_empty_rows_preserves_existing,
        test_cached_calendar_events_reads_file,
        test_cached_calendar_events_expired_file_returns_empty,
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
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n{'='*50}")
    print(f"Results: {passed} PASS, {failed} FAIL out of {len(tests)}")
    sys.exit(0 if failed == 0 else 1)
