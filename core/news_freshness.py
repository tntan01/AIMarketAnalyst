"""Owns the News domain data-status classification as the single owner
registered at contract section 6.5 - event status and per-signal store
freshness.

Two pure classifiers, both returning existing frozen string enums declared by
``core/news_models.py`` (never a bare string, never a display label, L3/C3):

* ``classify_event_status`` maps a ``CalendarEvent`` under ``now``/``grace``
  to ``EventStatus`` (``scheduled``/``released``/``stale``).
* ``classify_store_state`` maps the last successful ingest of each signal to a
  ``StoreState`` with one ``StoreStatus`` (``fresh``/``degraded``/
  ``unavailable``) per signal + the last successful ingest time of each.

Governance:

* **Pure (L2).** No I/O, no Qt, no policy read - ``now``/``grace``/``max_age``
  are parameters and the caller converts the policy keys of contract section 7
  into the ``datetime``/``timedelta`` values passed in, so this module never
  imports ``news_policy``.  A ``core/`` module never imports
  services/ui/controllers and never touches the network or filesystem.
* **Fail-closed (B4).** A signal with no successful ingest ever reported is
  ``unavailable``, never silently assumed fresh - the MacroMarketCache
  precedent (architecture-rules appendix C).
* **No fabricated number (B5).** ``grace`` and ``max_age`` carry no default
  here; the policy file supplies every operational number.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventStatus,
    IngestProducer,
    StoreState,
    StoreStatus,
)


def _parse_event_time_utc(value: str) -> datetime:
    """Decode the ``news_events.event_time_utc`` ISO-8601 string to aware UTC.

    Accepts the persisted ``Z``-suffixed form and an explicit UTC offset; a
    naive string is treated as UTC (the column declares UTC by name).
    """
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def classify_event_status(
    event: CalendarEvent,
    now: datetime,
    grace: timedelta,
) -> EventStatus:
    """Classify one calendar event - contract section 6.5.

    ``released`` whenever the event carries an actual (no grace applies);
    otherwise ``stale`` only when the event is impact-relevant (``impact !=
    non``), strictly past ``event_time_utc + grace`` and still missing its
    actual; every other case is ``scheduled``.
    """
    event_time = _parse_event_time_utc(event.event_time_utc)
    if event.actual is not None:
        return EventStatus.RELEASED
    if event.impact == EventImpact.NON:
        return EventStatus.SCHEDULED
    if now > event_time + grace:
        return EventStatus.STALE
    return EventStatus.SCHEDULED


def _classify_signal(
    last_success: datetime | None,
    now: datetime,
    max_age: timedelta,
) -> tuple[StoreStatus, str | None]:
    """Freshness of one signal from its last successful ingest time."""
    if last_success is None:
        return StoreStatus.UNAVAILABLE, None
    if now - last_success <= max_age:
        return StoreStatus.FRESH, last_success.isoformat()
    return StoreStatus.DEGRADED, last_success.isoformat()


def classify_store_state(
    last_success_by_producer: Mapping[IngestProducer, datetime],
    now: datetime,
    max_age: timedelta,
) -> StoreState:
    """Classify the freshness of the whole store - contract section 6.5/8.

    One signal per producer owner of the registry (contract section 6):
    ``ff_crawler`` feeds ``events``, ``rss`` feeds ``items``, ``fred`` feeds
    ``rates``.  Producer keys outside that mapping (``user``,
    ``on_demand_lookup``) have no clause in section 6.5 and are ignored; a
    missing key means that signal never had a successful ingest and is
    reported ``unavailable`` with a ``None`` last-success time (B4).
    """
    events_latest = last_success_by_producer.get(IngestProducer.FF_CRAWLER)
    items_latest = last_success_by_producer.get(IngestProducer.RSS)
    rates_latest = last_success_by_producer.get(IngestProducer.FRED)
    events_status, events_success_at = _classify_signal(events_latest, now, max_age)
    items_status, items_success_at = _classify_signal(items_latest, now, max_age)
    rates_status, rates_success_at = _classify_signal(rates_latest, now, max_age)
    return StoreState(
        events_state=events_status,
        items_state=items_status,
        rates_state=rates_status,
        events_last_success_at=events_success_at,
        items_last_success_at=items_success_at,
        rates_last_success_at=rates_success_at,
    )