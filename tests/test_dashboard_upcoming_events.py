"""`_fetch_upcoming_red_events` (Dashboard) đọc `news.db` thay vì HTTP ForexFactory.

WI-DASH: giao-tạm cho ca đấu nối (a) — hàm giữ NGUYÊN hành vi cũ (không lọc
currency, bỏ event quá khứ, chỉ impact cao, sắp ASC, cap `limit`) và chỉ đổi
nguồn dữ liệu sang `NewsRepository.events_in_range`.

Test dùng repository GIẢ (monkeypatch `services.news_repository.NewsRepository`);
model thì dùng `CalendarEvent` THẬT để mapping không bị "fake nói dối".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
)
from ui.screens.dashboard_screen import _fetch_upcoming_red_events, _iso_utc_seconds

NOW = datetime.now(timezone.utc)


def _event(
    *,
    hours_ahead: float,
    currency: str = "USD",
    title: str = "Non-Farm Payrolls",
    impact: EventImpact = EventImpact.HIGH,
    forecast: str | None = "180K",
    previous: str | None = "175K",
) -> CalendarEvent:
    moment = datetime.now(UTC) + timedelta(hours=hours_ahead)
    return CalendarEvent(
        day_key=moment.strftime("%Y-%m-%d"),
        event_time_utc=_iso_utc_seconds(moment),
        currency=currency,
        title=title,
        impact=impact,
        status=EventStatus.SCHEDULED,
        source=EventSource.FF_JSON,
        dedupe_key=f"{currency}-{title}-{hours_ahead}",
        fetched_at=_iso_utc_seconds(NOW),
        forecast=forecast,
        previous=previous,
    )


class _FakeRepository:
    """Duck-type `events_in_range`; ghi lại cửa sổ đọc."""

    events: list = []
    fail: bool = False
    calls: list[tuple[str, str]] = []

    def events_in_range(self, from_utc, to_utc, currencies=None, include_non_impact=True):
        type(self).calls.append((from_utc, to_utc))
        if type(self).fail:
            raise RuntimeError("sqlite3.OperationalError: database is locked")
        return list(type(self).events)


class _FailingConstructor:
    def __init__(self) -> None:
        raise RuntimeError("no such table: news_events")


@pytest.fixture
def fake_repo(monkeypatch):
    _FakeRepository.events = []
    _FakeRepository.fail = False
    _FakeRepository.calls = []
    monkeypatch.setattr("services.news_repository.NewsRepository", _FakeRepository)
    return _FakeRepository


class TestUpcomingRedEvents:
    def test_high_impact_future_event_maps_to_the_expected_shape(self, fake_repo):
        fake_repo.events = [_event(hours_ahead=5.0, currency="USD", title="FOMC Statement")]

        events = _fetch_upcoming_red_events()

        assert len(events) == 1
        event = events[0]
        assert set(event) == {
            "currency", "event", "impact", "forecast", "previous", "time_utc", "display_time",
        }
        assert event["currency"] == "USD"
        assert event["event"] == "FOMC Statement"
        assert event["impact"] == "high"
        assert event["forecast"] == "180K"
        assert event["previous"] == "175K"
        assert event["time_utc"] == fake_repo.events[0].event_time_utc
        assert isinstance(event["display_time"], datetime)
        assert event["display_time"].tzinfo is not None

    def test_low_and_non_impact_events_are_filtered(self, fake_repo):
        fake_repo.events = [
            _event(hours_ahead=2.0, impact=EventImpact.LOW),
            _event(hours_ahead=3.0, impact=EventImpact.NON),
            _event(hours_ahead=4.0, impact=EventImpact.MEDIUM),
            _event(hours_ahead=5.0, impact=EventImpact.HIGH),
        ]

        events = _fetch_upcoming_red_events()

        assert [event["impact"] for event in events] == ["high"]

    def test_past_events_are_filtered(self, fake_repo):
        fake_repo.events = [
            _event(hours_ahead=-2.0, title="Đã qua"),
            _event(hours_ahead=1.0, title="Sắp tới"),
        ]

        events = _fetch_upcoming_red_events()

        assert [event["event"] for event in events] == ["Sắp tới"]

    def test_results_are_sorted_ascending_and_capped(self, fake_repo):
        fake_repo.events = [
            _event(hours_ahead=hours, title=f"Sự kiện {hours}")
            for hours in (30.0, 4.0, 12.0, 1.0, 60.0, 20.0)
        ]

        events = _fetch_upcoming_red_events()

        assert len(events) == 4
        assert [event["event"] for event in events] == [
            "Sự kiện 1.0", "Sự kiện 4.0", "Sự kiện 12.0", "Sự kiện 20.0",
        ]

    def test_limit_is_configurable(self, fake_repo):
        fake_repo.events = [_event(hours_ahead=float(index + 1)) for index in range(5)]

        assert len(_fetch_upcoming_red_events(limit=2)) == 2

    def test_rows_of_other_currencies_are_kept(self, fake_repo):
        """Bản cũ truyền ``[]`` = không lọc currency — giữ nguyên hành vi."""
        fake_repo.events = [
            _event(hours_ahead=3.0, currency="EUR"),
            _event(hours_ahead=2.0, currency="JPY"),
        ]

        events = _fetch_upcoming_red_events()

        # Sắp ASC theo thời gian: JPY (+2h) trước EUR (+3h).
        assert [event["currency"] for event in events] == ["JPY", "EUR"]

    def test_window_is_the_next_hours_ahead_in_repository_iso_format(self, fake_repo):
        fake_repo.events = [_event(hours_ahead=2.0)]

        _fetch_upcoming_red_events(hours_ahead=72)

        assert len(fake_repo.calls) == 1
        from_utc, to_utc = fake_repo.calls[0]
        assert from_utc.endswith("Z") and to_utc.endswith("Z")
        span = datetime.fromisoformat(to_utc.replace("Z", "+00:00")) - datetime.fromisoformat(
            from_utc.replace("Z", "+00:00")
        )
        assert span == timedelta(hours=72)

    def test_repository_read_error_returns_empty(self, fake_repo):
        fake_repo.fail = True

        assert _fetch_upcoming_red_events() == []

    def test_repository_construction_error_returns_empty(self, monkeypatch):
        monkeypatch.setattr("services.news_repository.NewsRepository", _FailingConstructor)

        assert _fetch_upcoming_red_events() == []

    def test_empty_store_returns_empty(self, fake_repo):
        assert _fetch_upcoming_red_events() == []


class TestIsoHelper:
    def test_formats_in_the_repository_string_khuon(self):
        moment = datetime(2026, 10, 3, 7, 5, 9, tzinfo=timezone.utc)

        assert _iso_utc_seconds(moment) == "2026-10-03T07:05:09Z"

    def test_naive_input_is_read_as_utc(self):
        assert _iso_utc_seconds(datetime(2026, 10, 3, 7, 5, 9)) == "2026-10-03T07:05:09Z"

    def test_non_utc_offset_is_converted(self):
        moment = datetime(2026, 10, 3, 14, 5, 9, tzinfo=timezone(timedelta(hours=7)))

        assert _iso_utc_seconds(moment) == "2026-10-03T07:05:09Z"
