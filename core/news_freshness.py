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


def _classify_events_signal(
    data_latest: datetime | None,
    coverage_latest: datetime | None,
    now: datetime,
    freshness_max_age: timedelta,
    coverage_min: timedelta,
) -> tuple[StoreStatus, str | None]:
    """Freshness of the ``events`` signal - HYBRID rule (contract section 6.5).

    ``fresh`` when the pasted calendar is recent (``now - data_latest`` within
    ``freshness_max_age``) OR still covers enough of the future
    (``coverage_latest - now >= coverage_min``); no row at all is
    ``unavailable`` (B4); anything else is ``degraded``.  The reported time is
    always the DATA timestamp (``fetched_at``), never a producer run label.
    """
    if data_latest is None:
        return StoreStatus.UNAVAILABLE, None
    age_ok = now - data_latest <= freshness_max_age
    coverage_ok = (
        coverage_latest is not None and coverage_latest - now >= coverage_min
    )
    if age_ok or coverage_ok:
        return StoreStatus.FRESH, data_latest.isoformat()
    return StoreStatus.DEGRADED, data_latest.isoformat()


def classify_store_state(
    last_success_by_producer: Mapping[IngestProducer, datetime],
    events_data_latest: datetime | None,
    now: datetime,
    max_age: timedelta,
    *,
    events_coverage_latest: datetime | None,
    event_freshness_max_age: timedelta,
    event_coverage_min: timedelta,
) -> StoreState:
    """Classify the freshness of the whole store - contract section 6.5/8.

    ``events`` follows a HYBRID rule (Owner decision 03/10/2026, option 3:
    "age OR coverage") instead of the shared ``_classify_signal``:

    * no event row at all -> ``unavailable`` (B4 - never a fabricated fresh);
    * else ``fresh`` when the data is recent enough
      (``now - events_data_latest <= event_freshness_max_age``) **OR** the
      calendar still covers the future far enough
      (``events_coverage_latest - now >= event_coverage_min``);
    * otherwise -> ``degraded``.

    Why: the calendar is a hand-pasted signal the Owner refreshes through the
    day, so the RSS cadence threshold (``ingest_freshness_hours``) is too strict
    for it - a paste that still covers the coming days IS current data.  The UI
    hint must only appear when the pasted calendar is genuinely outdated (stale
    paste AND exhausted coverage).  The label-based path was dropped entirely
    (03/10/2026 incident: runs written under ``ff_crawler``/``user`` while the
    calendar data was present).

    ``items``/``rates``/``yields`` keep the run-based rule via the shared
    ``_classify_signal`` and the caller's ``max_age`` (``rss``/``fred``/
    ``bond_yield`` each have a fixed, still-living producer owner - S6);
    producer keys outside that mapping (``user`` - manual note entry,
    ``on_demand_lookup``) feed no signal and are ignored.
    """
    items_latest = last_success_by_producer.get(IngestProducer.RSS)
    rates_latest = last_success_by_producer.get(IngestProducer.FRED)
    yields_latest = last_success_by_producer.get(IngestProducer.BOND_YIELD)
    events_status, events_success_at = _classify_events_signal(
        events_data_latest,
        events_coverage_latest,
        now,
        event_freshness_max_age,
        event_coverage_min,
    )
    items_status, items_success_at = _classify_signal(items_latest, now, max_age)
    rates_status, rates_success_at = _classify_signal(rates_latest, now, max_age)
    yields_status, yields_success_at = _classify_signal(yields_latest, now, max_age)
    return StoreState(
        events_state=events_status,
        items_state=items_status,
        rates_state=rates_status,
        yields_state=yields_status,
        events_last_success_at=events_success_at,
        items_last_success_at=items_success_at,
        rates_last_success_at=rates_success_at,
        yields_last_success_at=yields_success_at,
    )