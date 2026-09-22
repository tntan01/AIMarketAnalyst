"""ff_calendar_producer HTML-channel + on-demand lookup tests (plan lô L2.4,
contract §6.1/§4.6/§8 seam).

Behavioral parity with the inherited runtime (B3): the HTML transport
(UA ``Mozilla/5.0 (compatible; AI Market Analyst/1.0)``, timeout=10, single
shot — no retry, no sleep), the rowspan ``_RowContext`` parser and the
HIGH-confidence (currency + normalized event name + date) actual match are
ported from ``forex_factory_client.py`` and compared function-by-function on
the SAME fixtures reused from ``tests/test_forex_factory_client.py``.  The LOW
±30-minute proximity branch stays removed (CNY Loan Prime Rate bug history).

The network and the backoff clock are fully mocked (no real HTTP, no real
waiting, ``%APPDATA%`` never touched — the DB is a throwaway temp DB).  The
two reference weekly pages are ``this`` = Mon 2026-07-20 .. Sun 2026-07-26 and
``next`` = Mon 2026-07-27 .. Sun 2026-08-02; all fixtures reference
``NOW = 2026-07-20T15:00:00Z`` (Monday 15:00 UTC).
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sqlite3
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from urllib.error import HTTPError, URLError

from config.paths import PROJECT_ROOT
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    IngestProducer,
    IngestRunStatus,
)
from services.forex_factory_client import ForexFactoryClient
from services.news_producers import ff_calendar_producer as ffmod
from services.news_producers.ff_calendar_producer import (
    FFCalendarProducer,
    HtmlCalendarFetchError,
    HtmlCalendarResult,
)
from services.news_repository import ActualConflict, NewsRepository

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"

THIS_HTML_URL = FFCalendarProducer.THISWEEK_HTML_URL
NEXT_HTML_URL = FFCalendarProducer.NEXTWEEK_HTML_URL

FIXTURE_HTML = (PROJECT_ROOT / "tests" / "fixtures" / "ff_calendar_week.html").read_text(encoding="utf-8")

# This week (Mon 2026-07-20) / next week (Mon 2026-07-27); grace is 15 min.
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)

# Fixtures reused from the old client's own test module (test B3 parity on the
# exact same inputs; loaded by file path so the import is collector-independent).
_OLD_TESTS_SPEC = importlib.util.spec_from_file_location(
    "test_forex_factory_client_fixtures",
    PROJECT_ROOT / "tests" / "test_forex_factory_client.py",
)
assert _OLD_TESTS_SPEC and _OLD_TESTS_SPEC.loader
_OLD_TESTS = importlib.util.module_from_spec(_OLD_TESTS_SPEC)
_OLD_TESTS_SPEC.loader.exec_module(_OLD_TESTS)
FAKE_FF_HTML = _OLD_TESTS.FAKE_FF_HTML
REAL_FF_HTML_ROWSPAN = _OLD_TESTS.REAL_FF_HTML_ROWSPAN


# ---- fixture scaffolding (temp DB + fully mocked transport) ---------------------


class _FakeResponse:
    def __init__(self, raw: bytes) -> None:
        self._raw = raw

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc) -> bool:
        return False

    def read(self) -> bytes:
        return self._raw


def _http(code: int) -> HTTPError:
    return HTTPError("https://www.forexfactory.com/calendar", code, "x", {}, io.BytesIO(b""))


def _repo(tmp_path: Path) -> NewsRepository:
    return NewsRepository(
        db_path=tmp_path / "news.db",
        migrations_dir=NEWS_MIGRATIONS_DIR,
    )


def _producer(tmp_path: Path) -> FFCalendarProducer:
    return FFCalendarProducer(_repo(tmp_path))


def _mock_transport(sequence: list[object], on_fetch=None):
    """Mock ``urlopen`` and ``time.sleep`` in the producer module namespace.
    Each item is raw bytes (a response body) or an exception to raise; the
    optional ``on_fetch`` callback runs per urlopen call right before the
    response (used to simulate a user editing the DB mid-run)."""
    queue = list(sequence)
    urlopen_calls: list[str] = []
    sleeps: list[float] = []

    def fake_urlopen(request, timeout=10):
        urlopen_calls.append(getattr(request, "full_url", str(request)))
        if on_fetch is not None:
            on_fetch()
        item = queue.pop(0)
        if isinstance(item, BaseException):
            raise item
        return _FakeResponse(item)

    def fake_sleep(seconds):
        sleeps.append(seconds)

    return (
        mock.patch.object(ffmod, "urlopen", fake_urlopen),
        mock.patch.object(ffmod.time, "sleep", fake_sleep),
        urlopen_calls,
        sleeps,
    )


def _seed_event(
    repo: NewsRepository,
    currency: str,
    title: str,
    event_time_utc: str,
    *,
    day_key: str | None = None,
    impact: EventImpact = EventImpact.HIGH,
    source: EventSource = EventSource.FF_JSON,
    actual: str | None = None,
    actual_updated_at: str | None = None,
) -> str:
    """Insert one calendar event with the producer's own dedupe formula."""
    dedupe = hashlib.sha256(f"{event_time_utc}|{currency}|{title}".encode("utf-8")).hexdigest()
    repo.upsert_events(
        [
            CalendarEvent(
                day_key=day_key or event_time_utc[:10],
                event_time_utc=event_time_utc,
                currency=currency,
                title=title,
                impact=impact,
                status=EventStatus.SCHEDULED,
                source=source,
                dedupe_key=dedupe,
                fetched_at="2026-07-20T00:00:00Z",
                forecast="0.3%" if currency == "USD" else None,
                previous="0.2%" if currency == "USD" else None,
                actual=actual,
                actual_updated_at=actual_updated_at,
            )
        ]
    )
    return dedupe


def _id_for(repo: NewsRepository, dedupe: str) -> int:
    conn = sqlite3.connect(repo.db_path)
    try:
        conn.row_factory = sqlite3.Row
        return int(conn.execute("SELECT id FROM news_events WHERE dedupe_key=?", (dedupe,)).fetchone()["id"])
    finally:
        conn.close()


def _read(db_path: Path, sql: str, params: tuple = ()):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


# ---- helpers for the seam lookup (real clock) ------------------------------------


def _recent_stale_seed(
    repo: NewsRepository,
    title: str = "CPI m/m",
    currency: str = "USD",
) -> tuple[str, str]:
    """Seed a stale (6h past — so stale at ANY run moment) pending event whose
    ``day_key`` is pinned to the current Monday (so the on-demand lookup, which
    runs on the real clock, maps it to the ``this`` page deterministically)."""
    now = datetime.now(timezone.utc)
    this_monday = (now - timedelta(days=now.weekday())).date().isoformat()
    instant = (now - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:00Z")
    _seed_event(repo, currency, title, instant, day_key=this_monday)
    return _id_for(repo, _seed_dedupe(currency, title, instant)), instant


def _seed_dedupe(currency: str, title: str, event_time_utc: str) -> str:
    return hashlib.sha256(f"{event_time_utc}|{currency}|{title}".encode("utf-8")).hexdigest()


def _row_html(date_text: str, time_text: str, currency: str, title: str, actual: str,
              forecast: str = "0.3%", previous: str = "0.2%") -> str:
    return (
        '<tr class="calendar__row">'
        f'<td class="calendar__cell calendar__date">{date_text}</td>'
        f'<td class="calendar__time">{time_text}</td>'
        f'<td class="calendar__currency">{currency}</td>'
        f'<td class="calendar__event-title">{title}</td>'
        '<td class="calendar__impact"><span class="calendar__impact-icon--red">High Impact</span></td>'
        f'<td class="calendar__forecast">{forecast}</td>'
        f'<td class="calendar__previous">{previous}</td>'
        f'<td class="calendar__actual">{actual}</td>'
        "</tr>"
    )


def _page_html(*rows: str) -> bytes:
    return (
        '<div class="calendar__timezone">Calendar Time Zone: America/New_York (GMT -4)</div>\n<table>'
        + "".join(rows) + "</table>"
    ).encode("utf-8")


def _utc_cell(instant: str) -> tuple[str, str]:
    """``(date_text, time_text)`` of an ISO-8601 UTC instant displayed in UTC.

    The page header's America/New_York name does not decode through the
    inherited timezone regex (``.../New_``), so ``_parse_html_time`` treats the
    displayed clock as UTC — displaying UTC keeps the parsed date key exactly
    aligned with the seed at any run hour."""
    dt = datetime.fromisoformat(instant.replace("Z", "+00:00"))
    hour12 = dt.hour % 12 or 12
    return dt.strftime("%a %b %d"), f"{hour12}:{dt.minute:02d}{'am' if dt.hour < 12 else 'pm'}"


# ---- 1. parser: rowspan inheritance + timezone detect ---------------------------


class TestParseHtml:
    def test_rowspan_inheritance_and_actuals_not_mixed(self, tmp_path):
        producer = _producer(tmp_path)
        rows = producer._parse_html(REAL_FF_HTML_ROWSPAN)
        assert len(rows) == 2

        ev1 = [r for r in rows if "1-y" in str(r["event"])][0]
        ev5 = [r for r in rows if "5-y" in str(r["event"])][0]
        assert ev1["time_utc"] == "2026-07-20T01:00Z"          # 08:00 Asia/Bangkok = 01:00Z
        assert ev5["time_utc"] == "2026-07-20T01:00Z"          # rowspan inheritance
        assert ev1["actual"] == "3.00%"
        assert ev5["actual"] == "3.50%"                        # NEVER copied between rows

    def test_detect_html_timezone(self, tmp_path):
        producer = _producer(tmp_path)
        assert producer._detect_html_timezone(REAL_FF_HTML_ROWSPAN) == "Asia/Bangkok"
        # Inherited regex `[A-Z][a-z]+/[A-Z][a-z_]+` stops at the uppercase "Y"
        # of "New_York" — parity with the old client (B3), kept verbatim.
        assert producer._detect_html_timezone(FIXTURE_HTML) == "America/New_"

    def test_parse_html_time_converts_bangkok_to_utc(self, tmp_path):
        producer = _producer(tmp_path)
        parsed = producer._parse_html_time("08:30am", "Mon Jun 15", "Asia/Bangkok")
        assert parsed is not None
        assert parsed == datetime(2026, 6, 15, 1, 30, tzinfo=UTC)

    def test_all_day_and_tentative_have_no_time(self, tmp_path):
        producer = _producer(tmp_path)
        rows = producer._parse_html(FAKE_FF_HTML)
        eur = [r for r in rows if r["currency"] == "EUR"][0]
        assert eur["time_utc"] == ""

    def test_normalize_event_name_inherited(self, tmp_path):
        producer = _producer(tmp_path)
        assert producer._normalize_event_name("CNY 5-y Loan Prime Rate (Above)") == "cny 5 y loan prime rate"


# ---- 2. B3 function-level parity: new parser vs old client (same fixtures) ------


class TestParseHtmlParityB3:
    @staticmethod
    def _strip_volatile(rows):
        cleaned = []
        for row in rows:
            r = dict(row)
            r.pop("hours_until", None)  # volatile now-derived value, not part of the match
            cleaned.append(r)
        return sorted(cleaned, key=lambda r: (r["currency"], r["event"], r["time_utc"]))

    def test_new_parser_matches_inherited_client_on_rowspan_fixture(self, tmp_path):
        old = ForexFactoryClient()._parse_html(REAL_FF_HTML_ROWSPAN)
        new = _producer(tmp_path)._parse_html(REAL_FF_HTML_ROWSPAN)
        assert len(new) == len(old)
        assert self._strip_volatile(new) == self._strip_volatile(old)

    def test_new_parser_matches_inherited_client_on_basic_fixture(self, tmp_path):
        old = ForexFactoryClient()._parse_html(FAKE_FF_HTML)
        new = _producer(tmp_path)._parse_html(FAKE_FF_HTML)
        assert len(new) == len(old)
        assert self._strip_volatile(new) == self._strip_volatile(old)

    def test_normalize_event_name_parity(self, tmp_path):
        new = FFCalendarProducer._normalize_event_name
        old = ForexFactoryClient._normalize_event_name
        for name in ("CPI m/m", "1-y Loan Prime Rate (3m)", "US 10y Auction", "German ZEW!?", "  Core  CPI  y/y  "):
            assert new(name) == old(name), name


# ---- 3. targeted fetch: only the week containing pending events ----------------


class TestTargetedFetch:
    def test_pending_this_week_only_one_this_request(self, tmp_path):
        producer = _producer(tmp_path)
        _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")
        p1, p2, calls, sleeps = _mock_transport([FIXTURE_HTML.encode("utf-8")])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert isinstance(result, HtmlCalendarResult)
        assert result.weeks_fetched == ("this",)
        assert calls == [THIS_HTML_URL]
        assert sleeps == []
        assert result.run_status == IngestRunStatus.OK
        assert result.written == 1
        row = _read(producer._repo.db_path, "SELECT actual, source FROM news_events")
        assert row["actual"] == "0.4%"
        assert row["source"] == EventSource.FF_HTML.value

    def test_pending_two_weeks_two_requests(self, tmp_path):
        producer = _producer(tmp_path)
        # day_key "2026-07-27" puts the second pending event on the `next` page
        # (the grouping follows day_key — contract §6.1); its event time is past
        # so it is genuinely pending (stale).
        _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")
        _seed_event(
            producer._repo,
            "EUR",
            "German ZEW Economic Sentiment",
            "2026-07-20T05:00:00Z",
            day_key="2026-07-27",
        )
        p1, p2, calls, sleeps = _mock_transport([FIXTURE_HTML.encode("utf-8")] * 2)
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.weeks_fetched == ("this", "next")
        assert calls == [THIS_HTML_URL, NEXT_HTML_URL]
        assert sleeps == []
        assert result.run_status == IngestRunStatus.OK
        assert result.written == 2
        assert producer._repo.events_pending_actual(NOW) == []   # both got their actual
        assert {r["actual"] for r in _all_rows(producer._repo)} == {"0.4%", "4.2"}

    def test_no_pending_zero_network_requests(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, calls, sleeps = _mock_transport([])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.pending_count == 0
        assert result.weeks_fetched == ()
        assert calls == []
        assert sleeps == []
        assert result.run_status == IngestRunStatus.OK
        assert result.written == 0
        run = _read(
            producer._repo.db_path,
            "SELECT producer, status, items_written, error_type FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["producer"] == IngestProducer.FF_CRAWLER.value
        assert run["status"] == "ok"
        assert run["items_written"] == 0

    def test_pending_previous_week_is_not_targeted(self, tmp_path):
        producer = _producer(tmp_path)
        _seed_event(producer._repo, "NZD", "Trade Balance", "2026-07-13T10:00:00Z")
        p1, p2, calls, sleeps = _mock_transport([])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.weeks_fetched == ()
        assert calls == []                       # tuần trước KHÔNG thu — no URL exists
        assert result.run_status == IngestRunStatus.OK

    def test_unmatched_html_rows_are_ignored_no_event_created(self, tmp_path):
        producer = _producer(tmp_path)
        _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")
        p1, p2, *_ = _mock_transport([FIXTURE_HTML.encode("utf-8")])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.written == 1               # only the matched pending event
        n_gbp = _read(producer._repo.db_path, "SELECT COUNT(*) AS n FROM news_events WHERE currency='GBP'")
        assert n_gbp["n"] == 0                   # HTML never creates new events (§6.1)


# ---- 4. the three merge rules end-to-end (enforced by the repository) ----------


class TestMergeRules:
    def test_rule1_null_pending_never_blank_stored_actual_at_db_level(self, tmp_path):
        producer = _producer(tmp_path)
        # Stored released event with an actual already recorded (same week).
        _seed_event(
            producer._repo,
            "EUR",
            "ECB Main Refinancing Operations Rate",
            "2026-07-20T11:00:00Z",
            actual="0.0%",
            actual_updated_at="2026-07-20T12:00:00Z",
        )
        _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")
        p1, p2, *_ = _mock_transport([FIXTURE_HTML.encode("utf-8")])
        with p1, p2:
            producer.fetch_actual_html(now=NOW)

        ecb = _read(
            producer._repo.db_path,
            "SELECT actual, actual_updated_at FROM news_events WHERE currency='EUR'",
        )
        assert ecb["actual"] == "0.0%"              # not pending → untouched (DB-level)
        assert ecb["actual_updated_at"] == "2026-07-20T12:00:00Z"

    def test_rule2_user_source_event_is_never_auto_merged(self, tmp_path):
        producer = _producer(tmp_path)
        _seed_event(
            producer._repo,
            "USD",
            "CPI m/m",
            "2026-07-20T13:30:00Z",
            source=EventSource.USER,
        )
        p1, p2, *_ = _mock_transport([FIXTURE_HTML.encode("utf-8")])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.conflicts == ()
        row = _read(producer._repo.db_path, "SELECT actual, source FROM news_events")
        assert row["source"] == EventSource.USER.value   # protected
        assert row["actual"] is None                     # auto actual rejected

    def test_rule3_user_actual_wins_conflict_logged_in_ingest_runs(self, tmp_path):
        producer = _producer(tmp_path)
        dedupe = _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")
        event_id = _id_for(producer._repo, dedupe)

        def _user_edits_actual_mid_fetch():
            # Simulates the genuine race rule 3 guards: the user types an actual
            # while the fetch is in flight, so the pending snapshot (actual NULL)
            # and the upsert (now source=user + actual) disagree.
            conn = sqlite3.connect(producer._repo.db_path)
            try:
                conn.execute(
                    "UPDATE news_events SET source='user', actual='3.5%', "
                    "actual_updated_at='2026-07-20T15:30:00Z' WHERE id=?",
                    (event_id,),
                )
                conn.commit()
            finally:
                conn.close()

        p1, p2, calls, sleeps = _mock_transport([FIXTURE_HTML.encode("utf-8")], on_fetch=_user_edits_actual_mid_fetch)
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert calls == [THIS_HTML_URL]
        assert sleeps == []
        assert len(result.conflicts) == 1
        conflict = result.conflicts[0]
        assert isinstance(conflict, ActualConflict)
        assert conflict.currency == "USD"
        assert conflict.title == "CPI m/m"
        assert conflict.user_actual == "3.5%"
        assert conflict.incoming_actual == "0.4%"

        row = _read(producer._repo.db_path, "SELECT actual, source FROM news_events")
        assert row["actual"] == "3.5%"                      # user wins
        assert row["source"] == EventSource.USER.value

        run = _read(
            producer._repo.db_path,
            "SELECT status, items_written, error_type, error_detail FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["status"] == "ok"
        assert run["items_written"] == 0
        assert run["error_type"] == "ActualConflict"
        assert "0.4%" in run["error_detail"] and "3.5%" in run["error_detail"]


# ---- 5. on-demand lookup (contract §6.1 lượt 4, seam pluggable by L2.7) ---------


class TestOnDemandLookup:
    def _seam(self, tmp_path: Path) -> tuple[NewsRepository, FFCalendarProducer]:
        repo = _repo(tmp_path)
        producer = FFCalendarProducer(repo)
        repo.on_demand_lookup = producer.lookup_event_actual  # L2.7 wires this via __init__
        return repo, producer

    def test_stale_event_fetched_and_actual_returned(self, tmp_path):
        repo, producer = self._seam(tmp_path)
        event_id, instant = _recent_stale_seed(repo, title="CPI m/m", currency="USD")
        date_text, time_text = _utc_cell(instant)
        page = _page_html(_row_html(date_text, time_text, "USD", "CPI m/m", "0.4%"))

        p1, p2, calls, sleeps = _mock_transport([page])
        with p1, p2:
            event = repo.event_actual_or_lookup(event_id)

        assert event is not None
        assert event.id == event_id
        assert event.actual == "0.4%"
        assert calls == [THIS_HTML_URL]
        assert sleeps == []
        run = _read(
            repo.db_path,
            "SELECT producer, status, items_written, error_type FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["producer"] == IngestProducer.ON_DEMAND_LOOKUP.value
        assert run["status"] == "ok"
        assert run["items_written"] == 1

    def test_non_stale_event_never_triggers_network(self, tmp_path):
        repo, producer = self._seam(tmp_path)
        dedupe = _seed_event(repo, "USD", "CPI m/m", "2999-01-01T00:00:00Z")
        event_id = _id_for(repo, dedupe)

        p1, p2, calls, sleeps = _mock_transport([])
        with p1, p2:
            event = repo.event_actual_or_lookup(event_id)

        assert event is not None
        assert event.actual is None
        assert calls == []                                   # scheduled → no lookup
        assert sleeps == []
        n_runs = _read(repo.db_path, "SELECT COUNT(*) AS n FROM ingest_runs")
        assert n_runs["n"] == 0

    def test_unknown_id_returns_none_without_network(self, tmp_path):
        repo, producer = self._seam(tmp_path)
        p1, p2, calls, sleeps = _mock_transport([])
        with p1, p2:
            result = producer.lookup_event_actual(999999)
        assert result is None
        assert calls == []

    def test_fetch_error_returns_stored_event_and_failed_run(self, tmp_path):
        repo, producer = self._seam(tmp_path)
        event_id, _ = _recent_stale_seed(repo)

        p1, p2, calls, sleeps = _mock_transport([_http(429)])
        with p1, p2:
            event = repo.event_actual_or_lookup(event_id)

        assert event is not None
        assert event.id == event_id
        assert event.actual is None                          # stored state, not None for existing id
        assert calls == [THIS_HTML_URL]                      # one shot
        assert sleeps == []                                  # no retry backoff
        run = _read(
            repo.db_path,
            "SELECT producer, status, error_type FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["producer"] == IngestProducer.ON_DEMAND_LOOKUP.value
        assert run["status"] == "failed"
        assert run["error_type"] == "Http429"

    def test_empty_table_returns_stored_event_and_invalid_html_run(self, tmp_path):
        repo, producer = self._seam(tmp_path)
        event_id, _ = _recent_stale_seed(repo)

        p1, p2, calls, sleeps = _mock_transport([b"<html><body>No calendar here</body></html>"])
        with p1, p2:
            event = repo.event_actual_or_lookup(event_id)

        assert event is not None
        assert event.actual is None
        assert calls == [THIS_HTML_URL]
        assert sleeps == []
        run = _read(
            repo.db_path,
            "SELECT status, error_type, error_detail FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["status"] == "failed"
        assert run["error_type"] == "InvalidHtmlTable"
        assert run["error_detail"] == "không đọc được bảng HTML"

    def test_no_html_actual_returns_stored_event_ok_run(self, tmp_path):
        repo, producer = self._seam(tmp_path)
        event_id, instant = _recent_stale_seed(repo, title="FOMC Rate Decision")
        date_text, time_text = _utc_cell(instant)
        page = _page_html(_row_html(date_text, time_text, "USD", "CPI m/m", "0.4%"))

        p1, p2, calls, sleeps = _mock_transport([page])
        with p1, p2:
            event = repo.event_actual_or_lookup(event_id)

        assert event is not None
        assert event.id == event_id
        assert event.actual is None                          # no HTML row matched
        assert calls == [THIS_HTML_URL]
        run = _read(
            repo.db_path,
            "SELECT status, items_written FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["status"] == "ok"                         # the fetch itself ran
        assert run["items_written"] == 0


# ---- 6. errors: 429 / URLError / bảng rỗng — typed, one-shot, partial ----------


class TestErrors:
    def _seed_usd_cpi(self, producer: FFCalendarProducer) -> None:
        _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")

    def test_429_failed_typed_http_once_no_sleep(self, tmp_path):
        producer = _producer(tmp_path)
        self._seed_usd_cpi(producer)
        p1, p2, calls, sleeps = _mock_transport([_http(429)])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.run_status == IngestRunStatus.FAILED
        assert result.weeks_fetched == ("this",)
        assert calls == [THIS_HTML_URL]                      # one shot, no loop
        assert sleeps == []                                  # HTML transport never sleeps
        assert len(result.fetch_errors) == 1
        err = result.fetch_errors[0]
        assert isinstance(err, HtmlCalendarFetchError)
        assert err.week == "this"
        assert err.error_type == "Http429"
        assert err.detail == "HTTP 429"
        run = _read(
            producer._repo.db_path,
            "SELECT status, error_type FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["status"] == "failed"
        assert run["error_type"] == "Http429"

    def test_url_error_failed_typed_once(self, tmp_path):
        producer = _producer(tmp_path)
        self._seed_usd_cpi(producer)
        p1, p2, calls, sleeps = _mock_transport([URLError("boom")])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.run_status == IngestRunStatus.FAILED
        assert calls == [THIS_HTML_URL]
        assert sleeps == []
        assert result.fetch_errors[0].error_type == "UrlError"
        assert result.fetch_errors[0].detail == "boom"

    def test_empty_table_failed_invalid_html(self, tmp_path):
        producer = _producer(tmp_path)
        self._seed_usd_cpi(producer)
        p1, p2, calls, sleeps = _mock_transport([b"<html><body>No calendar here</body></html>"])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.run_status == IngestRunStatus.FAILED
        assert calls == [THIS_HTML_URL]
        assert sleeps == []
        assert result.fetch_errors[0].error_type == "InvalidHtmlTable"
        run = _read(
            producer._repo.db_path,
            "SELECT status, error_type FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["error_type"] == "InvalidHtmlTable"

    def test_one_week_fails_other_writes_partial(self, tmp_path):
        producer = _producer(tmp_path)
        _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")
        _seed_event(
            producer._repo,
            "EUR",
            "German ZEW Economic Sentiment",
            "2026-07-20T05:00:00Z",
            day_key="2026-07-27",
        )
        p1, p2, calls, sleeps = _mock_transport([_http(429), FIXTURE_HTML.encode("utf-8")])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert result.run_status == IngestRunStatus.PARTIAL
        assert calls == [THIS_HTML_URL, NEXT_HTML_URL]       # this failed, next wrote
        assert sleeps == []
        assert result.written == 1
        assert result.fetch_errors[0].error_type == "Http429"
        run = _read(
            producer._repo.db_path,
            "SELECT status, items_written, error_type FROM ingest_runs ORDER BY id DESC LIMIT 1",
        )
        assert run["status"] == "partial"
        assert run["items_written"] == 1
        assert run["error_type"] == "Http429"


# ---- 7. typed result, no raw dict leaks ----------------------------------------


class TestTypedResult:
    def test_result_is_typed_not_raw_dict(self, tmp_path):
        producer = _producer(tmp_path)
        _seed_event(producer._repo, "USD", "CPI m/m", "2026-07-20T13:30:00Z")
        p1, p2, *_ = _mock_transport([FIXTURE_HTML.encode("utf-8")])
        with p1, p2:
            result = producer.fetch_actual_html(now=NOW)

        assert not isinstance(result, dict)
        assert isinstance(result, HtmlCalendarResult)
        assert isinstance(result.pending_count, int)
        assert isinstance(result.weeks_fetched, tuple)
        assert isinstance(result.written, int)
        assert isinstance(result.run_status, IngestRunStatus)
        assert all(isinstance(e, HtmlCalendarFetchError) for e in result.fetch_errors)
        assert all(isinstance(c, ActualConflict) for c in result.conflicts)


def _all_rows(repo: NewsRepository) -> list[dict[str, object]]:
    conn = sqlite3.connect(repo.db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute("SELECT * FROM news_events").fetchall()]
    finally:
        conn.close()
