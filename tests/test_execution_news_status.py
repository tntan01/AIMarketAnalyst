"""Execution-time news blackout contract tests (rewrite WI-7 → `NewsMacroProvider`).

Giữ nguyên các ca hợp đồng của bản cũ (đen tối trước/sau sự kiện, ngoài cửa sổ
được phép, nguồn không khả dụng → fail-closed) nhưng nhắm provider đọc `news.db`
với **repository giả** thay vì `NewsService`. Trạng thái "khả dụng" của nguồn nay
suy từ `store_state().events_state` (scope sự kiện), không từ chuỗi `source`.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

from core.news_models import StoreState, StoreStatus
from services.news_macro_provider import NEWS_STATUS_UNAVAILABLE, NewsMacroProvider

NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _event(minutes: int) -> SimpleNamespace:
    return SimpleNamespace(
        currency="EUR",
        title="Rate Decision",
        impact="high",
        forecast=None,
        previous=None,
        actual=None,
        event_time_utc=_iso(NOW + timedelta(minutes=minutes)),
    )


class _FakeRepository:
    """Chỉ đủ cho `execution_news_status`: đọc cửa sổ sự kiện + trạng thái store."""

    def __init__(self, events=(), *, events_state: str = "fresh") -> None:
        self._events = list(events)
        self._state = StoreState(
            events_state=StoreStatus(events_state),
            items_state=StoreStatus.FRESH,
            rates_state=StoreStatus.FRESH,
            yields_state=StoreStatus.FRESH,
        )

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        return [
            event
            for event in self._events
            if from_utc <= event.event_time_utc <= to_utc
            and (not currencies or event.currency in currencies)
        ]

    def store_state(self):
        return self._state


class _FailingRepository(_FakeRepository):
    def events_in_range(self, *args, **kwargs):
        raise sqlite3.OperationalError("database is locked")


def _provider(events, *, events_state: str = "fresh") -> NewsMacroProvider:
    return NewsMacroProvider(
        _FakeRepository(events, events_state=events_state),
        observability=SimpleNamespace(emit=lambda *a, **k: None),
        clock=lambda: NOW,
    )


def test_news_blackout_covers_before_and_after_event():
    before = _provider([_event(20)]).execution_news_status(
        "EUR/USD",
        before_minutes=30,
        after_minutes=15,
        now=NOW,
    )
    after = _provider([_event(-10)]).execution_news_status(
        "EUR/USD",
        before_minutes=30,
        after_minutes=15,
        now=NOW,
    )

    assert before["available"] is True and before["blackout"] is True
    assert after["available"] is True and after["blackout"] is True


def test_news_outside_window_is_allowed():
    result = _provider([_event(31), _event(-16)]).execution_news_status(
        "EUR/USD",
        before_minutes=30,
        after_minutes=15,
        now=NOW,
    )
    assert result["available"] is True
    assert result["blackout"] is False


def test_unavailable_calendar_fails_closed():
    result = _provider([], events_state="unavailable").execution_news_status(
        "EUR/USD",
        now=NOW,
    )
    assert result["available"] is False
    assert result["blackout"] is None
    assert NEWS_STATUS_UNAVAILABLE in result["reason_codes"]


def test_degraded_calendar_still_serves_the_blackout():
    """`degraded` = dữ liệu CÓ thật (chỉ cũ) → vẫn available, vẫn chặn được."""
    result = _provider([_event(10)], events_state="degraded").execution_news_status(
        "EUR/USD",
        now=NOW,
    )

    assert result["available"] is True
    assert result["blackout"] is True
    assert result["reason_codes"] == ["NEWS_BLACKOUT"]


def test_read_failure_fails_closed():
    provider = NewsMacroProvider(
        _FailingRepository([]),
        observability=SimpleNamespace(emit=lambda *a, **k: None),
        clock=lambda: NOW,
    )

    result = provider.execution_news_status("EUR/USD", now=NOW)

    assert result["available"] is False
    assert result["blackout"] is None
    assert NEWS_STATUS_UNAVAILABLE in result["reason_codes"]
