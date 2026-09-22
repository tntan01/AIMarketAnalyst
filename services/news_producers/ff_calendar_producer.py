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

Plan batch L2.4 adds the **HTML actual channel** (contract §6.1 — HTML only
fills ``actual``, never creates events) plus the **on-demand lookup** seam.  It
ports ``_fetch_html_events``/``_fetch_html_events_nextweek`` (single shot, no
retry, UA ``Mozilla/5.0 (compatible; AI Market Analyst/1.0)``), the
``_RowContext``/``_parse_html`` rowspan table parser,
``_detect_html_timezone``/``_parse_html_time`` and the HIGH-confidence match of
``_merge_actual_from_html`` (currency + normalized event name + date — the LOW
±30-min branch stays removed, CNY LPR bug history) as internal helpers; the
raw HTML dict rows never cross the module boundary (R8).  Three typed
entry points:

1. ``fetch_actual_html`` — the HTML part of the startup batch and the
   "Cập nhật actual" button (contract §6.1 lượt 1/3): reads
   ``events_pending_actual(now)``, targets ONLY the week URL that contains a
   pending event (no pending → zero network requests), merges actuals and logs
   one ``ingest_runs`` row (producer ``ff_crawler``).
2. ``lookup_event_actual`` — the on-demand seam (contract §6.1 lượt 4): one
   stale event → fetch its week, merge, log producer ``on_demand_lookup``.
3. The repository seam ``NewsRepository(lookup=...)`` (L2.2) is wired by
   L2.7; this module only exports the callable.

The three §6.1 merge rules are enforced by ``NewsRepository.upsert_events``
(L2.1) — never replicated here; the producer only forwards their
``ActualConflict`` reports into ``ingest_runs``.

Governance:

* **No user-facing strings, no scoring, no gating** (contract §8).
* **No disk cache** — ``_store_calendar_cache`` of the old client is
  deliberately NOT ported (B7 §3.1.2): the new system writes only ``news.db``.
* **No retry beyond the inherited loop** (3 attempts, §6.1 anti-abuse).
* **No HTML retry at all** (contract §6.1 anti-abuse: the HTML transport is
  one shot — a failure is logged, never re-polled).
* **No previous week** (contract §6.1: tuần trước KHÔNG thu — only ``this``/
  ``next`` URLs exist).
* **No disk cache** — ``_store_calendar_cache`` of the old client is
  deliberately NOT ported (B7 §3.1.2): the new system writes only ``news.db``.
* **No policy keys** — ForexFactory has no cadence key (§7); the inherited
  transport numbers (UA, timeout, backoff) are runtime evidence, not policy.
* Legacy-difference markers, both Owner-confirmed for this batch: a date that
  does not parse is skipped (new schema ``event_time_utc`` is ISO-8601 NOT
  NULL); ``actual`` is always ``None`` even when the payload carries it.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
)
from services.calendar_helpers import (
    _clean_economic_value,
    _event_time,
    _is_valid_actual_value,
    clean_text,
    parse_event_time,
)
from services.news_repository import ActualConflict, NewsRepository

__all__ = [
    "FFCalendarProducer",
    "HtmlCalendarFetchError",
    "HtmlCalendarResult",
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


@dataclass(frozen=True, slots=True)
class HtmlCalendarFetchError:
    """Typed per-week failure of one targeted HTML actual run (contract §4.6
    style: inherited transport classification — ``Http<code>``/``UrlError``/
    ``InvalidHtmlTable``/``UntargetableWeek``)."""

    week: str
    error_type: str
    detail: str


@dataclass(frozen=True, slots=True)
class HtmlCalendarResult:
    """Typed outcome of one HTML actual run (contract §6.1 lượt 1/3).

    ``pending_count`` is the number of ``events_pending_actual`` considered;
    ``weeks_fetched`` the targeted ForexFactory weekly pages actually requested
    (empty when no pending event is targetable — zero network traffic);
    ``written`` the events upserted with a fresh actual; ``conflicts`` the §6.1
    rule-3 reports forwarded into ``ingest_runs``.  Errors surface typed here
    for the button to display later (UI is L3.3 — no display strings in this
    module)."""

    pending_count: int
    weeks_fetched: tuple[str, ...]
    written: int
    conflicts: tuple[ActualConflict, ...]
    run_status: IngestRunStatus
    run_id: int
    fetch_errors: tuple[HtmlCalendarFetchError, ...]


class FFCalendarProducer:
    """Producer of the ForexFactory economic-calendar signal — the JSON
    calendar channel (L2.3) and the targeted HTML actual channel + on-demand
    lookup (L2.4)."""

    # Inherited upstream endpoints (forex_factory_client.py:55-58, runtime).
    THISWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    NEXTWEEK_URL = "https://nfs.faireconomy.media/ff_calendar_nextweek.json"
    THISWEEK_HTML_URL = "https://www.forexfactory.com/calendar?week=this"
    NEXTWEEK_HTML_URL = "https://www.forexfactory.com/calendar?week=next"

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

    # --- public HTML channel (contract §6.1 lượt 1 phần HTML + lượt 3 nút) --------

    def fetch_actual_html(self, now: datetime | None = None) -> HtmlCalendarResult:
        """Targeted HTML actual fetch (contract §6.1 lượt 1/3).

        Reads ``events_pending_actual(now)`` and fetches ONLY the weekly HTML
        page (``this`` and/or ``next``) that contains a pending event by its
        ``day_key`` — no pending event → ``weeks_fetched`` is empty and no
        network request is ever issued.  Matched actuals are merged through
        ``NewsRepository.upsert_events`` (the three §6.1 rules live there, not
        here); rule-3 conflicts returned by the repository are written into the
        run's ``error_type``/``error_detail``.  Exactly one ``ingest_runs`` row
        (producer ``ff_crawler``) is logged per run (§10).  Errors are typed and
        never retried (the HTML transport is one shot — §6.1 anti-abuse).
        """
        started_at = _utc_now()
        now_dt = now if now is not None else datetime.now(timezone.utc)
        pending = self._repo.events_pending_actual(now_dt)

        weeks: dict[str, list[CalendarEvent]] = {}
        for event in pending:
            if not event.day_key:
                continue
            label = _html_week_label(event.day_key, now_dt)
            if label is not None:
                weeks.setdefault(label, []).append(event)

        fetched_at = _utc_now()
        fetch_errors: list[HtmlCalendarFetchError] = []
        updates: list[CalendarEvent] = []
        weeks_fetched: list[str] = []
        for week in ("this", "next"):
            if week not in weeks:
                continue
            weeks_fetched.append(week)
            try:
                html_rows = self._fetch_html_week(week)
            except Exception as exc:  # transport failure — that week fails alone
                fetch_errors.append(
                    HtmlCalendarFetchError(
                        week=week,
                        error_type=_classify_html_error(exc),
                        detail=str(exc),
                    )
                )
                continue
            updates.extend(self._build_actual_updates(weeks[week], html_rows, fetched_at))

        total_weeks = len(weeks)
        successful = total_weeks - len(fetch_errors)
        if total_weeks == 0 or successful == total_weeks:
            run_status = IngestRunStatus.OK
        elif successful == 0:
            run_status = IngestRunStatus.FAILED
        else:
            run_status = IngestRunStatus.PARTIAL

        upsert = self._repo.upsert_events(updates)
        error_type, error_detail = _run_error_fields(tuple(fetch_errors), upsert.conflicts)
        run_id = self._repo.record_run(
            IngestRun(
                producer=IngestProducer.FF_CRAWLER,
                started_at=started_at,
                finished_at=_utc_now(),
                status=run_status,
                items_written=upsert.inserted + upsert.updated,
                error_type=error_type,
                error_detail=error_detail,
            )
        )
        return HtmlCalendarResult(
            pending_count=len(pending),
            weeks_fetched=tuple(weeks_fetched),
            written=upsert.inserted + upsert.updated,
            conflicts=tuple(upsert.conflicts),
            run_status=run_status,
            run_id=run_id,
            fetch_errors=tuple(fetch_errors),
        )

    # --- on-demand lookup seam (contract §6.1 lượt 4) -----------------------------

    def lookup_event_actual(self, event_id: int) -> CalendarEvent | None:
        """On-demand actual lookup of one event (contract §6.1 lượt 4).

        Wired by L2.7 into ``NewsRepository(lookup=...)``; the repository calls
        it exactly once for a ``stale`` event.  The event is resolved through
        ``events_pending_actual(now)`` — never through ``event_actual_or_lookup``
        (that would recurse).  Fetches the weekly HTML page containing it,
        merges the actual and returns the post-merge database row (``None`` only
        for an unknown id).  On fetch error, untargetable week or no HTML
        actual, the current stored event is returned instead (never ``None``
        for an existing id) and the run status records the honest outcome
        (B4).  Every run logs producer ``on_demand_lookup`` (§10).  The HTML
        transport is one shot — never retried (§6.1 anti-abuse).
        """
        started_at = _utc_now()
        now = datetime.now(timezone.utc)
        pending = self._repo.events_pending_actual(now)
        target = next((event for event in pending if event.id == event_id), None)
        if target is None:
            return None

        label = _html_week_label(target.day_key, now)
        fetch_errors: list[HtmlCalendarFetchError] = []
        updates: list[CalendarEvent] = []
        if label is None:
            fetch_errors.append(
                HtmlCalendarFetchError(
                    week="",
                    error_type="UntargetableWeek",
                    detail=f"event {event_id} day_key {target.day_key} outside this/next week",
                )
            )
        else:
            fetched_at = _utc_now()
            try:
                html_rows = self._fetch_html_week(label)
            except Exception as exc:
                fetch_errors.append(
                    HtmlCalendarFetchError(
                        week=label,
                        error_type=_classify_html_error(exc),
                        detail=str(exc),
                    )
                )
            else:
                updates = self._build_actual_updates([target], html_rows, fetched_at)

        run_status = IngestRunStatus.FAILED if fetch_errors else IngestRunStatus.OK
        upsert = self._repo.upsert_events(updates)
        error_type, error_detail = _run_error_fields(tuple(fetch_errors), upsert.conflicts)
        self._repo.record_run(
            IngestRun(
                producer=IngestProducer.ON_DEMAND_LOOKUP,
                started_at=started_at,
                finished_at=_utc_now(),
                status=run_status,
                items_written=upsert.inserted + upsert.updated,
                error_type=error_type,
                error_detail=error_detail,
            )
        )
        if not updates:
            return target
        return self._read_event_by_id(target)

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

    def _fetch_html_week(self, week: str) -> list[dict[str, object]]:
        """Parse ONE weekly HTML calendar page.

        Inherited transport behavior (forex_factory_client.py:262-280/308-326):
        ``week`` ``"this"``/``"next"`` maps to the two fixed URLs; UA
        ``Mozilla/5.0 (compatible; AI Market Analyst/1.0)``, ``Accept
        text/html,application/xhtml+xml``, ``timeout=10``, ONE attempt with
        NO retry and NO sleep; HTTPError → ``RuntimeError("HTTP {code}")``,
        URLError → ``RuntimeError(str(reason))``; a page that parses to zero
        rows → ``RuntimeError("không đọc được bảng HTML"[" nextweek"])``.
        Parsed rows stay inside this module (R8)."""
        url = self.THISWEEK_HTML_URL if week == "this" else self.NEXTWEEK_HTML_URL
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; AI Market Analyst/1.0)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        try:
            with urlopen(request, timeout=10) as response:
                html = response.read().decode("utf-8", errors="ignore")
        except HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code}") from exc
        except URLError as exc:
            raise RuntimeError(str(exc.reason)) from exc
        rows = self._parse_html(html)
        if not rows:
            if week == "next":
                raise RuntimeError("không đọc được bảng HTML nextweek")
            raise RuntimeError("không đọc được bảng HTML")
        return rows

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

    # --- HTML parser (ported verbatim, forensic evidence: runtime in production) --

    class _RowContext:
        """Carries cell values forward when ForexFactory uses HTML rowspan.

        ForexFactory frequently uses rowspan for cells like date and time
        when consecutive events share the same value.  Without inheritance,
        rows after the first would get empty strings for those cells.

        _RowContext preserves the last seen value for each spanning cell
        (date, time, currency, impact) so every parsed event receives a
        complete context.  Per-event fields (event title, forecast,
        previous, actual) are NEVER inherited.

        Ported verbatim from ``forex_factory_client.py:366`` (B3).
        """

        __slots__ = ("date", "time_text", "currency", "impact")

        def __init__(self) -> None:
            self.date: str | None = None
            self.time_text: str = ""
            self.currency: str = ""
            self.impact: str = ""

        def update_date(self, new_date: str) -> None:
            """Set a new date and reset time (times don't span across days)."""
            self.date = new_date
            self.time_text = ""

    _DATE_RE = re.compile(
        r"(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}",
        re.IGNORECASE,
    )

    def _parse_html(self, html: str) -> list[dict[str, object]]:
        """Parse the ForexFactory calendar HTML table into raw rows.

        Ported verbatim from ``forex_factory_client.py:402`` (B3): the
        rowspan-aware ``_RowContext`` date/time/currency/impact inheritance,
        per-row event/forecast/previous/actual extraction and the timezone
        conversion.  The returned dict rows are the raw boundary shape and
        never leave this module (R8)."""
        now = datetime.now(UTC)
        rows: list[dict[str, object]] = []
        ctx = self._RowContext()

        html_tz = self._detect_html_timezone(html)

        row_blocks = re.findall(r"<tr[^>]*calendar__row[^>]*>(.*?)</tr>", html, flags=re.IGNORECASE | re.DOTALL)
        for block in row_blocks:
            # --- Date (rowspan-aware) ---
            date_text = self._html_cell_text(block, "calendar__date")
            if not date_text:
                date_text = self._html_cell_text(block, "calendar__cell")
            if date_text:
                date_clean = re.sub(r"<[^>]+>", "", date_text).strip()
                date_clean = re.sub(r"\s+", " ", date_clean)
                if self._DATE_RE.search(date_clean):
                    ctx.update_date(date_clean)
            # If no date cell in this row, inherit from context (rowspan)

            # --- Time (rowspan-aware) ---
            time_raw = self._html_raw_cell(block, "calendar__time")
            if time_raw:
                # Cell exists in this row — read its value
                time_text = re.sub(r"<[^>]+>", " ", time_raw).strip()
                if time_text.lower() in ("all day", "tentative"):
                    # Explicitly no specific time — reset context
                    ctx.time_text = ""
                    time_text = ""
                else:
                    ctx.time_text = time_text
            else:
                # No time cell in this row — inherit from context (rowspan)
                time_text = ctx.time_text

            # --- Currency (rowspan-aware) ---
            currency_raw = self._html_cell_text(block, "calendar__currency")
            if currency_raw:
                ctx.currency = currency_raw
            currency = ctx.currency

            # --- Event (NEVER inherited -- per-event data) ---
            event = self._html_cell_text(block, "calendar__event-title") or self._html_cell_text(block, "calendar__event")
            if not currency or not event:
                continue

            # --- Impact (rowspan-aware) ---
            impact_cell = self._html_raw_cell(block, "calendar__impact")
            if impact_cell:
                ctx.impact = self._html_impact(block)
            impact = ctx.impact

            # --- Per-event fields (NEVER inherited) ---
            event_time = self._parse_html_time(time_text, ctx.date, html_tz)

            hours_until = ((event_time - now).total_seconds() / 3600) if event_time else None
            actual_raw = self._html_cell_text(block, "calendar__actual")
            forecast_raw = self._html_cell_text(block, "calendar__forecast")
            previous_raw = self._html_cell_text(block, "calendar__previous")
            actual_cleaned = _clean_economic_value(actual_raw)
            forecast_cleaned = _clean_economic_value(forecast_raw)
            previous_cleaned = _clean_economic_value(previous_raw)
            rows.append(
                {
                    "source": "Forex Factory HTML",
                    "currency": currency,
                    "event": event,
                    "impact": impact,
                    "time_utc": event_time.isoformat(timespec="minutes").replace("+00:00", "Z") if event_time else "",
                    "hours_until": round(hours_until, 2) if hours_until is not None else None,
                    "forecast": forecast_cleaned,
                    "previous": previous_cleaned,
                    "actual": actual_cleaned,
                }
            )
        return rows

    def _detect_html_timezone(self, html: str) -> str:
        """Inherited timezone detection (forex_factory_client.py:479-489)."""
        tz_match = re.search(r"Calendar Time Zone:\s*([^<]+)", html)
        if tz_match:
            tz_text = tz_match.group(1).strip()
            tz_name = re.search(r"([A-Z][a-z]+/[A-Z][a-z_]+)", tz_text)
            if tz_name:
                return tz_name.group(1)
        tz_match = re.search(r"'User Timezone':\s*'([^']+)'", html)
        if tz_match:
            return tz_match.group(1)
        return str(datetime.now().astimezone().tzinfo)

    def _parse_html_time(self, time_text: str, date_text: str | None, html_tz: str = "UTC") -> datetime | None:
        """Inherited HTML clock parsing → aware UTC (forex_factory_client.py:491-521)."""
        if not time_text or not date_text:
            return None
        time_text = time_text.strip().lower()
        if time_text in ("all day", "tentative", ""):
            return None

        match = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_text)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2))
        ampm = match.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        try:
            parsed_date = datetime.strptime(date_text + f" {datetime.now(UTC).year}", "%a %b %d %Y")
        except ValueError:
            return None

        try:
            tz = ZoneInfo(html_tz)
        except Exception:
            tz = None
        dt_local = parsed_date.replace(hour=hour, minute=minute, tzinfo=tz)
        if tz:
            return dt_local.astimezone(UTC)
        return dt_local.replace(tzinfo=UTC)

    def _html_raw_cell(self, row_html: str, class_name: str) -> str:
        match = re.search(
            rf'<(?:td|span|div)[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</(?:td|span|div)>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return match.group(1) if match else ""

    def _html_cell_text(self, row_html: str, class_name: str) -> str:
        match = re.search(
            rf'<(?:td|span|div)[^>]*class="[^"]*{re.escape(class_name)}[^"]*"[^>]*>(.*?)</(?:td|span|div)>',
            row_html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return clean_text(re.sub(r"<[^>]+>", " ", match.group(1)))

    def _html_impact(self, row_html: str) -> str:
        lowered = row_html.lower()
        if "high impact" in lowered or "calendar__impact-icon--red" in lowered or "ff-impact-red" in lowered:
            return "High"
        if "medium impact" in lowered or "calendar__impact-icon--orange" in lowered or "ff-impact-orange" in lowered:
            return "Medium"
        if "low impact" in lowered or "calendar__impact-icon--yellow" in lowered or "ff-impact-yellow" in lowered:
            return "Low"
        return ""

    # --- HTML actual matching (ported merge semantics; HIGH confidence only) ------

    @staticmethod
    def _normalize_event_name(name: str) -> str:
        """Inherited event-name normalizer (forex_factory_client.py:580-586)."""
        n = name.lower()
        n = re.sub(r"\([^)]*\)", "", n)
        n = re.sub(r"[^a-z0-9 ]", " ", n)
        n = re.sub(r"\s+", " ", n).strip()
        return n

    def _build_actual_updates(
        self,
        pending_events: list[CalendarEvent],
        html_rows: list[dict[str, object]],
        fetched_at: str,
    ) -> list[CalendarEvent]:
        """Match pending events to parsed HTML actuals — the new-architecture
        form of the inherited ``_merge_actual_from_html``
        (forex_factory_client.py:588).

        HIGH-confidence key only: ``(currency.upper(), normalize(title), date
        of event_time_utc)``; the LOW ±30-minute proximity branch is REMOVED —
        it provably copied the wrong actual for same-time same-currency events
        (CNY 1-y/5-y Loan Prime Rate bug) and stays removed.  Only pending
        events matched to a ``_is_valid_actual_value`` HTML actual produce a
        ``CalendarEvent`` — identity (``dedupe_key``/``title``/``raw_json``) is
        inherited from the pending row, ``actual`` + ``actual_updated_at`` are
        stamped and ``source=ff_html``.  Unmatched rows/pending events are
        skipped: the HTML channel never creates events (contract §6.1)."""
        html_lookup: dict[tuple[str, str, str], str] = {}
        for row in html_rows:
            currency = str(row.get("currency", "")).upper()
            event = str(row.get("event", ""))
            actual = str(row.get("actual", "")).strip()
            ev_time = _event_time(row)
            date_key = ev_time.strftime("%Y%m%d") if ev_time else ""
            norm_event = self._normalize_event_name(event)
            # A valid actual must be non-sentinel (calendar_helpers.py, not copied here)
            if _is_valid_actual_value(actual) and currency and norm_event:
                html_lookup[(currency, norm_event, date_key)] = actual

        updates: list[CalendarEvent] = []
        for event in pending_events:
            ev_time = parse_event_time(event.event_time_utc)
            if not ev_time:
                continue
            date_key = ev_time.strftime("%Y%m%d")
            key = (event.currency.upper(), self._normalize_event_name(event.title), date_key)
            html_actual = html_lookup.get(key)
            if html_actual is None:
                continue
            updates.append(
                CalendarEvent(
                    day_key=event.day_key,
                    event_time_utc=event.event_time_utc,
                    currency=event.currency,
                    title=event.title,
                    impact=event.impact,
                    status=event.status,
                    source=EventSource.FF_HTML,
                    dedupe_key=event.dedupe_key,
                    fetched_at=fetched_at,
                    forecast=event.forecast,
                    previous=event.previous,
                    actual=html_actual,
                    actual_updated_at=fetched_at,
                    raw_json=event.raw_json,
                )
            )
        return updates

    def _read_event_by_id(self, event: CalendarEvent) -> CalendarEvent:
        """Re-read one event through the read contract after an upsert, so the
        on-demand lookup returns the true persisted state (B4 — never assume the
        write landed, e.g. rule 2/3 may have kept the stored row)."""
        window = self._repo.events_in_range(event.event_time_utc, event.event_time_utc)
        for row in window:
            if row.id == event.id:
                return row
        return event


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


def _html_week_label(day_key: str, now: datetime) -> str | None:
    """Map an event ``day_key`` (``YYYY-MM-DD`` UTC) to the ForexFactory weekly
    page that contains it: ``this`` when the day falls in the current
    Monday-Sunday week, ``next`` in the following one, ``None`` for any other
    week — ForexFactory exposes no previous-week page (contract §6.1: tuần
    trước KHÔNG thu).  The event week, not the fetch moment, decides the URL."""
    try:
        event_date = datetime.strptime(day_key, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None
    this_monday = now.date() - timedelta(days=now.date().weekday())
    delta_days = (event_date - this_monday).days
    if 0 <= delta_days < 7:
        return "this"
    if 7 <= delta_days < 14:
        return "next"
    return None


def _classify_html_error(exc: Exception) -> str:
    """Inherited transport classification for the HTML channel (khuôn
    ``_classify_error`` L2.3, contract §4.6 style): ``Http<code>`` for HTTP
    failures, ``UrlError`` for URLError, ``InvalidHtmlTable`` when the page
    carried no parseable calendar rows (the "không đọc được bảng HTML"
    RuntimeError)."""
    if isinstance(exc, RuntimeError):
        message = str(exc)
        if message.startswith("HTTP "):
            return "Http" + message[len("HTTP "):]
        if message.startswith("không đọc được bảng HTML"):
            return "InvalidHtmlTable"
        return "UrlError"
    return "InvalidHtml"


def _conflicts_detail(conflicts: tuple[ActualConflict, ...]) -> str:
    """Compact machine-readable summary of rule-3 conflicts (contract §6.1:
    user actual wins and the conflict is written into ``ingest_runs``)."""
    return "; ".join(
        f"{c.dedupe_key}|{c.currency}|{c.title}|user={c.user_actual}|auto={c.incoming_actual}"
        for c in conflicts
    )


def _run_error_fields(
    fetch_errors: tuple[HtmlCalendarFetchError, ...],
    conflicts: tuple[ActualConflict, ...],
) -> tuple[str | None, str | None]:
    """Map typed fetch failures + merge conflicts onto the ``ingest_runs`` error
    fields (contract §4.6): the first transport failure wins ``error_type``;
    rule-3 conflicts are appended to ``error_detail`` and, alone, mark
    ``error_type`` as ``ActualConflict`` — the producer only forwards what the
    repository reports (L2.1), it never re-derives the merge rules."""
    if fetch_errors:
        first = fetch_errors[0]
        if conflicts:
            return first.error_type, first.detail + " | ActualConflict: " + _conflicts_detail(conflicts)
        return first.error_type, first.detail
    if conflicts:
        return "ActualConflict", _conflicts_detail(conflicts)
    return None, None