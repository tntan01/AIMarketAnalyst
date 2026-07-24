"""Execution-time news blackout contract tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from services.news_service import NewsService


NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def _service(events, source="calendar"):
    service = NewsService.__new__(NewsService)
    service.latest_macro_context = lambda *args, **kwargs: {
        "source": source,
        "events": events,
    }
    return service


def _event(minutes: int) -> dict:
    return {
        "currency": "EUR",
        "event": "Rate Decision",
        "impact": "High",
        "time_utc": (NOW + timedelta(minutes=minutes)).isoformat(),
    }


def test_news_blackout_covers_before_and_after_event():
    before = _service([_event(20)]).execution_news_status(
        "EUR/USD",
        before_minutes=30,
        after_minutes=15,
        now=NOW,
    )
    after = _service([_event(-10)]).execution_news_status(
        "EUR/USD",
        before_minutes=30,
        after_minutes=15,
        now=NOW,
    )

    assert before["available"] is True and before["blackout"] is True
    assert after["available"] is True and after["blackout"] is True


def test_news_outside_window_is_allowed():
    result = _service([_event(31), _event(-16)]).execution_news_status(
        "EUR/USD",
        before_minutes=30,
        after_minutes=15,
        now=NOW,
    )
    assert result["available"] is True
    assert result["blackout"] is False


def test_unavailable_calendar_fails_closed():
    result = _service([], source="unavailable").execution_news_status(
        "EUR/USD",
        now=NOW,
    )
    assert result["available"] is False
    assert result["blackout"] is None
    assert "NEWS_STATUS_UNAVAILABLE" in result["reason_codes"]
