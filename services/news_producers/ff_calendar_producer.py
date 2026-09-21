"""ff_calendar_producer — JSON economic-calendar channel (plan batch L2.3).

Sole owner of "lấy và chuẩn hóa lịch kinh tế ForexFactory thành
``CalendarEvent``" (contract §6 / §11b, identity M5).  This batch ports the
JSON channel only: the two feeds of contract §6.1 (thisweek + nextweek JSON
endpoints), the transport of ``services/forex_factory_client.py`` verbatim
(inherited runtime — evidence label B5), the raw-dict-to-``CalendarEvent``
converter right at the boundary (R8/C2), the always-upsert write into
``NewsRepository`` and one ``ingest_runs`` row per producer run (contract §4.6).

The converter is the ONLY place where the raw ForexFactory dict shape
(``country``/``currency``/``date``/``title``/``impact``/``forecast``/``previous``)
is visible — nothing raw ever leaves this module's public API (R8).  The JSON
channel never carries an ``actual`` (contract §6.1: "JSON feed không có
actual"); the L2.1 repository merge rules then protect any actual already in
the database from being blanked.

Governance:

* **No user-facing strings, no scoring, no gating** (contract §8).
* **No disk cache** — ``_store_calendar_cache`` of the old client is
  deliberately NOT ported (B7 §3.1.2): the new system writes only ``news.db``.
* **No retry beyond the inherited loop** (3 attempts, §6.1 anti-abuse).
* **No policy keys** — ForexFactory has no cadence key (§7); the inherited
  transport numbers (UA, timeout, backoff) are runtime evidence, not policy.
* Legacy-difference markers, both Owner-confirmed for this batch: a date that
  does not parse is skipped (new schema ``event_time_utc`` is ISO-8601 NOT
  NULL); ``actual`` is always ``None`` even when the payload carries it.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
)
from services.calendar_helpers import _clean_economic_value, parse_event_time
from services.news_repository import ActualConflict, NewsRepository

__all__ = [
    "FFCalendarProducer",
    "JsonCalendarFetchError",
    "JsonCalendarResult",
]


def _utc_now() -> str:
    """Current UTC time in the khuôn ISO-8601 form: ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class JsonCalendarFetchError:
    """Typed per-feed failure of one JSON calendar run (contract §4.6 style:
    inherited transport error classification — ``Http429``/``UrlError``/
    ``InvalidJsonPayload``)."""

    feed: str
    error_type: str
    detail: str


@dataclass(frozen=True, slots=True)
class JsonCalendarResult:
    """Typed outcome of one JSON calendar producer run (contract §6.1 lượt 1/2).

    Carries the repository upsert summary, the run status logged into
    ``ingest_runs`` and the per-feed errors — no bare dict, no raw feed row
    ever crosses the boundary (C3/R8)."""

    inserted: int
    updated: int
    conflicts: tuple[ActualConflict, ...]
    run_status: IngestRunStatus
    run_id: int
    feed_errors: tuple[JsonCalendarFetchError, ...]


class FFCalendarProducer:
    """Producer of the ForexFactory economic-calendar JSON signal."""

    # Inherited upstream endpoints (forex_factory_client.py:55-56, runtime).
    THISWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    NEXTWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"

    def __init__(self, repo: NewsRepository) -> None:
        self._repo = repo

    # --- public channel (contract §6.1 lượt 1 phần JSON + lượt 2 nút "Lấy lịch) --

    def fetch_calendar_json(self) -> JsonCalendarResult:
        """Fetch thisweek + nextweek JSON, upsert every converted event and log
        one ingest run (producer ``ff_crawler``).

        Each week is fetched independently (khuôn ``calendar_events_window``,
        forex_factory_client.py:122-133): a failing week never blocks the
        other.  The run status is ``ok`` when both weeks fetched, ``partial``
        when one fetched, ``failed`` when none fetched (contract §4.6).  The
        upsert is always an overwrite — the repository is never read first to
        "skip if exists" (§6.1 lượt 2 / §13)."""
        started_at = _utc_now()
        events: list[CalendarEvent] = []
        feed_errors: list[JsonCalendarFetchError] = []
        for feed, url in (("thisweek", self.THISWEEK_URL), ("nextweek", self.NEXTWEEK_URL)):
            try:
                payload = self._fetch_json_feed(url)
            except Exception as exc:  # transport error — one week fails alone
                feed_errors.append(
                    JsonCalendarFetchError(
                        feed=feed,
                        error_type=_classify_error(exc),
                        detail=str(exc),
                    )
                )
                continue
            fetched_at = _utc_now()
            events.extend(self._convert_payload(payload, fetched_at))

        run_status = _run_status_for(2 - len(feed_errors))
        first_error = feed_errors[0] if feed_errors else None
        upsert = self._repo.upsert_events(events)
        run = IngestRun(
            producer=IngestProducer.FF_CRAWLER,
            started_at=started_at,
            finished_at=_utc_now(),
            status=run_status,
            items_written=upsert.inserted + upsert.updated,
            error_type=first_error.error_type if first_error else None,
            error_detail=first_error.detail if first_error else None,
        )
        run_id = self._repo.record_run(run)
        return JsonCalendarResult(
            inserted=upsert.inserted,
            updated=upsert.updated,
            conflicts=tuple(upsert.conflicts),
            run_status=run_status,
            run_id=run_id,
            feed_errors=tuple(feed_errors),
        )

    # --- transport (ported verbatim, forensic evidence: runtime in production) ---

    def _fetch_json_feed(self, url: str) -> list[dict[str, object]]:
        """GET one JSON calendar feed.

        Inherited transport behavior (forex_factory_client.py:236-260/282-306):
        UA ``AI Market Analyst/1.0``, ``timeout=10``, 3 attempts; HTTPError →
        ``RuntimeError(f"HTTP {code}")``, 429 with remaining attempts sleeps
        ``2*(attempt+1)``; URLError → ``RuntimeError(str(reason))``, sleeping
        ``1`` — a JSON decode failure is never retried (propagates)."""
        last_error: RuntimeError | None = None
        for attempt in range(3):
            try:
                request = Request(
                    url,
                    headers={"User-Agent": "AI Market Analyst/1.0"},
                )
                with urlopen(request, timeout=10) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                return payload if isinstance(payload, list) else []
            except HTTPError as exc:
                last_error = RuntimeError(f"HTTP {exc.code}")
                if exc.code == 429 and attempt < 2:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise last_error from exc
            except URLError as exc:
                last_error = RuntimeError(str(exc.reason))
                if attempt < 2:
                    time.sleep(1)
                    continue
                raise last_error from exc

    # --- converter (raw dict -> CalendarEvent, the only boundary to the raw shape)

    def _convert_payload(
        self, payload: list[dict[str, object]], fetched_at: str
    ) -> list[CalendarEvent]:
        """Map raw ForexFactory JSON rows to ``CalendarEvent`` (R8/C2).

        Field mapping (plan batch L2.3, section 3.1): currency from
        ``country`` falling back to ``currency``; ``event_time_utc`` re-uses
        ``parse_event_time`` with the minutes-and-``Z`` khuôn format of the old
        client; ``title`` passes through untouched (the JSON channel does not
        normalize names — that is the HTML channel, L2.4); ``impact`` maps
        ``high``/``medium``/``low`` and everything else to ``non``; a date that
        does not parse is skipped; ``actual`` is always ``None`` for this
        channel; ``dedupe_key`` is a stable sha256 of
        ``event_time_utc|currency|title``; each event keeps its whole raw dict
        as provenance in ``raw_json`` (§10)."""
        events: list[CalendarEvent] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            currency = str(item.get("country") or item.get("currency") or "")
            if not currency:
                continue
            parsed_time = parse_event_time(str(item.get("date") or ""))
            if parsed_time is None:
                continue
            event_time_utc = parsed_time.isoformat(timespec="minutes").replace("+00:00", "Z")
            title = str(item.get("title") or "")
            forecast = _clean_economic_value(item.get("forecast", "")) or None
            previous = _clean_economic_value(item.get("previous", "")) or None
            events.append(
                CalendarEvent(
                    day_key=event_time_utc[:10],
                    event_time_utc=event_time_utc,
                    currency=currency,
                    title=title,
                    impact=_map_impact(item.get("impact", "")),
                    status=EventStatus.SCHEDULED,
                    source=EventSource.FF_JSON,
                    dedupe_key=hashlib.sha256(
                        f"{event_time_utc}|{currency}|{title}".encode("utf-8")
                    ).hexdigest(),
                    fetched_at=fetched_at,
                    forecast=forecast,
                    previous=previous,
                    actual=None,
                    raw_json=json.dumps(item),
                )
            )
        return events


def _map_impact(raw: object) -> EventImpact:
    """``high``/``medium``/``low`` map to their frozen enum member; any other
    label (``holiday``, ``non-economic``, empty, unknown) is ``non`` — a stray
    label must never masquerade as an impacting event (contract §4.2)."""
    value = str(raw).strip().lower()
    if value == EventImpact.HIGH.value:
        return EventImpact.HIGH
    if value == EventImpact.MEDIUM.value:
        return EventImpact.MEDIUM
    if value == EventImpact.LOW.value:
        return EventImpact.LOW
    return EventImpact.NON


def _classify_error(exc: Exception) -> str:
    """Inherited transport error classification for ``ingest_runs.error_type``:
    ``Http<code>`` for HTTP failures, ``UrlError`` for URLError, otherwise the
    payload is unusable — ``InvalidJsonPayload`` (contract §4.6 style)."""
    if isinstance(exc, RuntimeError):
        message = str(exc)
        if message.startswith("HTTP "):
            return "Http" + message[len("HTTP "):]
        return "UrlError"
    return "InvalidJsonPayload"


def _run_status_for(success_weeks: int) -> IngestRunStatus:
    """Map the number of successfully fetched weeks to a run status: both
    weeks → ``ok``, one → ``partial``, none → ``failed`` (contract §4.6)."""
    if success_weeks >= 2:
        return IngestRunStatus.OK
    if success_weeks == 1:
        return IngestRunStatus.PARTIAL
    return IngestRunStatus.FAILED