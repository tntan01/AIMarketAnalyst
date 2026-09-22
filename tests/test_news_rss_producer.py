"""rss_producer tests (plan lô L2.5, contract §6.2/§4.3/§4.6).

Behavioral parity with the inherited runtime (B3): the Google News RSS parser
(caps [:8] per feed, UA, timeout=5, ``InvalidRSSStructure``), the extra-feed
parser ([:15], host fallback, UA, timeout=8), ``parse_rss_time``,
``_matches_currency`` and the ``_rss_collection_result`` status semantics are
compared function-by-function against ``services/news_service.py`` read-only
(imported for comparison, never modified).  The collection window comes from
the injected ``NewsPolicy`` (R4), the broader query/feed/statement lists are
the inherited constants, and the transport is fully mocked (no network, no
`%APPDATA%`); ``ThreadPoolExecutor`` runs for real over the mocked transport.
"""

from __future__ import annotations

import hashlib
import io
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from urllib.error import URLError

from config.paths import PROJECT_ROOT
from core.news_models import IngestProducer, IngestRunStatus, NewsItemKind, NewsItemSource
from core.news_policy import load_news_policy
from services.news_producers import rss_producer as rssmod
from services.news_producers.rss_producer import RssCollectionResult, RssProducer, RssSourceError, parse_rss_time
from services.news_repository import NewsRepository
from services.news_service import NewsService

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"
FIXTURES = PROJECT_ROOT / "tests" / "fixtures"

FIXTURE_BROAD = (FIXTURES / "rss_google_broad.xml").read_bytes()
FIXTURE_STATEMENTS = (FIXTURES / "rss_google_statements.xml").read_bytes()
FIXTURE_FXSTREET = (FIXTURES / "rss_fxstreet_news.xml").read_bytes()
FIXTURE_INVESTING = (FIXTURES / "rss_investing_news.xml").read_bytes()

NOW = datetime(2026, 7, 20, 12, 0, tzinfo=UTC)

_EMPTY_RSS = b'<?xml version="1.0"?><rss version="2.0"><channel><title>empty</title></channel></rss>'


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


def _repo(tmp_path: Path) -> NewsRepository:
    return NewsRepository(
        db_path=tmp_path / "news.db",
        migrations_dir=NEWS_MIGRATIONS_DIR,
    )


def _producer(tmp_path: Path, policy=None) -> RssProducer:
    return RssProducer(_repo(tmp_path), policy=policy)


def _read(db_path: Path, sql: str, params: tuple = ()):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _read_all(db_path: Path, sql: str, params: tuple = ()):
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()


def _rfc(dt: datetime) -> str:
    """RFC-2822 UTC string a parser can always read."""
    return dt.strftime("%a, %d %b %Y %H:%M:%S") + " GMT"


def _rss_bytes(items) -> bytes:
    """Inline RSS document; ``items`` = iterable of (title, link, rfc2822)."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0"><channel><title>t</title>',
    ]
    for title, link, published in items:
        parts.append(
            "<item><title>{}</title><link>{}</link>"
            "<source url='https://x'>Src</source><pubDate>{}</pubDate></item>".format(
                title, link, published
            )
        )
    parts.append("</channel></rss>")
    return "".join(parts).encode("utf-8")


def _broad_urls() -> dict[str, bytes]:
    return {rssmod._google_news_url(q): FIXTURE_BROAD for q in rssmod.BROAD_QUERIES}


def _statement_urls(body: bytes) -> dict[str, bytes]:
    return {rssmod._google_news_url(q): body for q, _ in rssmod.STATEMENT_SOURCES}


def _mock_routes(routes: dict[str, object], default: bytes = _EMPTY_RSS):
    """Route urlopen by full URL; each value is bytes or an exception to raise.
    ``rssmod.time.sleep`` is patched too (khuôn ``_mock_transport``) — the RSS
    transport must never sleep, asserted via the ``sleeps`` list."""
    urlopen_calls: list[str] = []
    sleeps: list[float] = []

    def fake_urlopen(request, timeout=10):
        url = getattr(request, "full_url", str(request))
        urlopen_calls.append(url)
        item = routes.get(url, default)
        if isinstance(item, BaseException):
            raise item
        return _FakeResponse(item)

    def fake_sleep(seconds):
        sleeps.append(seconds)

    return (
        mock.patch.object(rssmod, "urlopen", fake_urlopen),
        mock.patch.object(rssmod.time, "sleep", fake_sleep),
        urlopen_calls,
        sleeps,
    )


def _items_in(db_path: Path) -> list[dict[str, object]]:
    return _read_all(db_path, "SELECT * FROM news_items ORDER BY id ASC")


def _latest_run(db_path: Path) -> dict[str, object]:
    return _read_all(db_path, "SELECT * FROM ingest_runs ORDER BY id DESC LIMIT 1")[0]


# ---- 1. parse_rss_time port parity ----------------------------------------------


class TestParseRssTimeParity:
    def test_parity_with_inherited_function(self, tmp_path):
        from services import news_service as newsmod

        old = newsmod.parse_rss_time
        cases = [
            "Mon, 20 Jul 2026 06:00:00 GMT",
            "Mon, 20 Jul 2026 08:30:00 +0700",
            "Mon, 20 Jul 2026 08:30:00 EST",
            "Mon, 20 Jul 2026 08:30:00",           # naive RFC-2822
            "2026-07-20T06:00:00Z",                # ISO-8601 fallback
            "2026-07-20T06:00:00",                 # naive ISO-8601
            "",
            "not a date at all",
        ]
        for value in cases:
            assert parse_rss_time(value) == old(value), value

    def test_known_conversions(self, tmp_path):
        assert parse_rss_time("Mon, 20 Jul 2026 06:00:00 GMT") == datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
        assert parse_rss_time("Mon, 20 Jul 2026 08:30:00 +0700") == datetime(2026, 7, 20, 1, 30, tzinfo=UTC)
        assert parse_rss_time("2026-07-20T06:00:00Z") == datetime(2026, 7, 20, 6, 0, tzinfo=UTC)
        assert parse_rss_time("Mon, 20 Jul 2026 08:30:00") == datetime(2026, 7, 20, 8, 30, tzinfo=UTC)
        assert parse_rss_time("") is None
        assert parse_rss_time("nonsense") is None


# ---- 2. Google News parser + extra-feed parser (B3 parity on same fixture) ------


class TestGoogleParserParityB3:
    @staticmethod
    def _old_rows(url: str, body: bytes):
        from services import news_service as newsmod

        with mock.patch.object(newsmod, "urlopen", _returning(body)):
            rows, status = NewsService.__new__(NewsService)._rss_items_with_status(url, query="parity")
        return rows, status

    @staticmethod
    def _new_rows(producer: RssProducer, url: str, body: bytes):
        with mock.patch.object(rssmod, "urlopen", _returning(body)):
            rows, status = producer._fetch_rss_items(url, query="parity")
        return rows, status

    @staticmethod
    def _projected(rows):
        return [
            {k: r[k] for k in ("source", "query", "title", "url", "published_utc")}
            for r in rows
        ]

    def test_rows_equivalent_and_fresh_on_google_fixture(self, tmp_path):
        url = rssmod._google_news_url("parity query")
        old_rows, old_status = self._old_rows(url, FIXTURE_BROAD)
        new_rows, new_status = self._new_rows(_producer(tmp_path), url, FIXTURE_BROAD)
        assert self._projected(new_rows) == self._projected(old_rows)
        assert new_status == {"status": "fresh", "error_type": ""}
        assert old_status == new_status

    def test_cap_eight_items_per_google_feed(self, tmp_path):
        many = _rss_bytes(
            [(f"Item number {i}", f"https://x/{i}", _rfc(NOW - timedelta(hours=1))) for i in range(10)]
        )
        url = rssmod._google_news_url("parity query")
        old_rows, _ = self._old_rows(url, many)
        new_rows, _ = self._new_rows(_producer(tmp_path), url, many)
        assert len(old_rows) == 8
        assert len(new_rows) == 8
        assert self._projected(new_rows) == self._projected(old_rows)

    @staticmethod
    def _structural(body: bytes):
        from services import news_service as newsmod

        url = rssmod._google_news_url("parity query")
        with mock.patch.object(newsmod, "urlopen", _returning(body)):
            _, old_status = NewsService.__new__(NewsService)._rss_items_with_status(url, query="parity")
        producer = RssProducer.__new__(RssProducer)
        with mock.patch.object(rssmod, "urlopen", _returning(body)):
            _, new_status = producer._fetch_rss_items(url, query="parity")
        return old_status, new_status

    def test_non_rss_root_is_invalid_structure(self, tmp_path):
        old_status, new_status = self._structural(b"<html><body>oops</body></html>")
        assert old_status["error_type"] == "InvalidRSSStructure"
        assert new_status == old_status

    def test_rss_without_channel_is_invalid_structure(self, tmp_path):
        old_status, new_status = self._structural(b'<rss version="2.0"><item/></rss>')
        assert old_status["error_type"] == "InvalidRSSStructure"
        assert new_status == old_status

    def test_parse_error_type_is_exception_name(self, tmp_path):
        old_status, new_status = self._structural(b"<not-xml")
        assert old_status["error_type"] == "ParseError"
        assert new_status == old_status


class TestExtraFeedParityB3:
    def test_rows_equivalent_and_cutoff_skip(self, tmp_path):
        from services import news_service as newsmod

        url = rssmod.EXTRA_RSS_FEEDS[0][0]
        cutoff = NOW - timedelta(hours=24)
        with mock.patch.object(newsmod, "urlopen", _returning(FIXTURE_FXSTREET)):
            old_rows = NewsService.__new__(NewsService)._fetch_extra_rss(url, cutoff)
        producer = _producer(tmp_path)
        with mock.patch.object(rssmod, "urlopen", _returning(FIXTURE_FXSTREET)):
            new_rows = producer._fetch_extra_rss(url, cutoff)

        assert len(old_rows) == 3          # "Stale extra item out of window" skipped
        assert len(new_rows) == 3
        projected = lambda rows: [{k: r[k] for k in ("source", "title", "url", "published_utc")} for r in rows]
        assert projected(new_rows) == projected(old_rows)

    def test_host_fallback_when_source_missing(self, tmp_path):
        from services import news_service as newsmod

        url = rssmod.EXTRA_RSS_FEEDS[0][0]
        cutoff = NOW - timedelta(hours=24)
        with mock.patch.object(newsmod, "urlopen", _returning(FIXTURE_FXSTREET)):
            old_rows = NewsService.__new__(NewsService)._fetch_extra_rss(url, cutoff)
        producer = _producer(tmp_path)
        with mock.patch.object(rssmod, "urlopen", _returning(FIXTURE_FXSTREET)):
            new_rows = producer._fetch_extra_rss(url, cutoff)
        no_source = [r for r in new_rows if "no source" in str(r["title"])][0]
        old_no_source = [r for r in old_rows if "no source" in str(r["title"])][0]
        assert no_source["source"] == "fxstreet.com"
        assert no_source["source"] == old_no_source["source"]

    def test_cap_fifteen_items_per_extra_feed(self, tmp_path):
        from services import news_service as newsmod

        many = _rss_bytes(
            [("Extra item %02d" % i, f"https://e/{i}", _rfc(NOW - timedelta(hours=1))) for i in range(20)]
        )
        url = rssmod.EXTRA_RSS_FEEDS[1][0]
        cutoff = NOW - timedelta(hours=24)
        with mock.patch.object(newsmod, "urlopen", _returning(many)):
            old_rows = NewsService.__new__(NewsService)._fetch_extra_rss(url, cutoff)
        producer = _producer(tmp_path)
        with mock.patch.object(rssmod, "urlopen", _returning(many)):
            new_rows = producer._fetch_extra_rss(url, cutoff)
        assert len(old_rows) == 15
        assert len(new_rows) == 15


def _returning(body: bytes):
    def fake(request, timeout=10):
        return _FakeResponse(body)

    return fake


# ---- 3. status / currency helper parity ------------------------------------------


class TestHelpersParity:
    def test_collection_status_matches_inherited_mapping(self, tmp_path):
        for successful, attempted in [(0, 11), (5, 11), (11, 11), (1, 1), (0, 1)]:
            old_status = NewsService._rss_collection_result(
                [], attempted_sources=attempted, successful_sources=successful, error_types=[]
            )["status"]
            new = rssmod._collection_status(successful, attempted)
            assert (old_status == "fresh") is (new is IngestRunStatus.OK), (successful, attempted)
            assert (old_status == "degraded") is (new is IngestRunStatus.PARTIAL), (successful, attempted)
            assert (old_status == "unavailable") is (new is IngestRunStatus.FAILED), (successful, attempted)

    def test_matches_currency_parity(self, tmp_path):
        old = NewsService.__new__(NewsService)._matches_currency
        cases = [
            ("Fed Powell speech dollar treasury yields latest", "USD", True),
            ("Fed Powell speech dollar treasury yields latest", "EUR", False),
            ("ECB Lagarde remarks euro inflation latest", "EUR", True),
            ("Gold analysis no source tag", "XAU", True),
            ("Dow futures steady into the open", "USD", False),
            ("Bitcoin ETF on-chain flows", "BTC", True),
        ]
        for title, currency, expected in cases:
            assert rssmod._matches_currency(title, currency) is expected, (title, currency)
            assert rssmod._matches_currency(title, currency) == old({"title": title}, currency)

    def test_currency_derivation_on_title(self, tmp_path):
        producer = _producer(tmp_path)
        row = {"title": "Fed Powell speech dollar treasury yields latest", "url": "https://a",
               "published_utc": "2026-07-20T06:00Z"}
        item = producer._to_news_item(
            row, kind=NewsItemKind.HEADLINE, source=NewsItemSource.GOOGLE_NEWS_RSS,
            speaker_role=None, fetched_at="2026-07-20T12:00:00Z",
        )
        assert item is not None
        assert item.currencies == ["USD"]


# ---- 4. one full headline round --------------------------------------------------


class TestHeadlineRound:
    def test_all_sources_write_typed_news_items(self, tmp_path):
        producer = _producer(tmp_path)
        routes = _broad_urls()
        routes[rssmod.EXTRA_RSS_FEEDS[0][0]] = FIXTURE_FXSTREET
        routes[rssmod.EXTRA_RSS_FEEDS[1][0]] = FIXTURE_INVESTING
        p1, p2, calls, sleeps = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        assert isinstance(result, RssCollectionResult)
        assert result.inserted == 9          # 4 broad + 3 fxstreet + 2 investing (in-window)
        assert result.updated == 0
        assert result.run_status is IngestRunStatus.OK
        assert result.attempted_sources == 11
        assert result.successful_sources == 11
        assert result.source_errors == ()
        assert sleeps == []

        rows = {r["title"]: r for r in _items_in(producer._repo.db_path)}
        assert len(rows) == 9
        fed = rows["Fed Powell speech dollar treasury yields latest"]
        assert fed["kind"] == NewsItemKind.HEADLINE.value
        assert fed["source"] == NewsItemSource.GOOGLE_NEWS_RSS.value
        assert fed["published_utc"] == "2026-07-20T06:00Z"
        assert fed["currencies_json"] == '["USD"]'
        assert fed["url"] == "https://news.example.com/fed-powell"
        assert fed["content"] is None
        assert fed["speaker_role"] is None
        gold = rows["Gold analysis no source tag"]
        assert gold["source"] == NewsItemSource.FXSTREET_RSS.value   # enum, not the host string
        assert rows["Dow futures steady into the open"]["currencies_json"] == "[]"

        run = _latest_run(producer._repo.db_path)
        assert run["producer"] == IngestProducer.RSS.value
        assert run["status"] == "ok"
        assert run["items_written"] == 9
        assert run["error_type"] is None
        assert _read(producer._repo.db_path, "SELECT COUNT(*) AS n FROM ingest_runs")["n"] == 1

    def test_window_reads_policy_not_hardcoded_24h(self, tmp_path):
        w24 = tmp_path / "w24"
        w48 = tmp_path / "w48"
        producer24 = RssProducer(
            NewsRepository(db_path=w24 / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR)
        )
        producer48 = RssProducer(
            NewsRepository(db_path=w48 / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR),
            policy=replace(load_news_policy(), rss_window_hours=48),
        )
        routes = _broad_urls()
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            result24 = producer24.fetch_round(now=NOW)
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            result48 = producer48.fetch_round(now=NOW)

        assert result24.inserted == 4        # "Old gold rally before window" (19 Jul 06:00) excluded at 24h
        assert result48.inserted == 5        # same item inside the 48h window

    def test_in_round_dedupe_title_first_wins_across_feeds(self, tmp_path):
        producer = _producer(tmp_path)
        dup = _rfc(NOW - timedelta(hours=2))
        routes = {
            rssmod._google_news_url(rssmod.BROAD_QUERIES[0]): _rss_bytes(
                [("Fed Powell speech dollar treasury yields latest", "https://a/title", dup)]
            ),
            rssmod.EXTRA_RSS_FEEDS[0][0]: _rss_bytes(
                [("FED POWELL speech dollar treasury yields latest", "https://b/title-other", dup)]
            ),
        }
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        assert result.inserted == 1          # same title (case-insensitive) → one item
        assert _read(producer._repo.db_path, "SELECT COUNT(*) AS n FROM news_items")["n"] == 1

    def test_second_round_upserts_not_duplicates(self, tmp_path):
        producer = _producer(tmp_path)
        routes = _broad_urls()
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            first = producer.fetch_round(now=NOW)
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            second = producer.fetch_round(now=NOW)

        assert first.inserted == 4
        assert second.inserted == 0
        assert second.updated == 4
        assert _read(producer._repo.db_path, "SELECT COUNT(*) AS n FROM news_items")["n"] == 4

    def test_dedupe_key_formula_both_branches(self, tmp_path):
        url_dk = rssmod._dedupe_key(url="https://news.example.com/fed-powell", title="T", published_utc="P")
        assert url_dk == hashlib.sha256("https://news.example.com/fed-powell".encode()).hexdigest()
        no_url = rssmod._dedupe_key(url=None, title="Title X", published_utc="2026-07-20T06:00Z")
        assert no_url == hashlib.sha256("Title X|2026-07-20T06:00Z".encode()).hexdigest()
        assert no_url != rssmod._dedupe_key(url=None, title="Title X", published_utc="2026-07-20T07:00Z")

        producer = _producer(tmp_path)
        routes = _broad_urls()
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            producer.fetch_round(now=NOW)
        row = _read(
            producer._repo.db_path,
            "SELECT dedupe_key FROM news_items WHERE title='Fed Powell speech dollar treasury yields latest'",
        )
        assert row["dedupe_key"] == url_dk


# ---- 5. statements ---------------------------------------------------------------


class TestStatements:
    def test_statements_fixture_written_as_kind_statement(self, tmp_path):
        producer = _producer(tmp_path)
        routes = _statement_urls(FIXTURE_STATEMENTS)
        p1, p2, calls, sleeps = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        assert result.inserted == 5
        rows = _items_in(producer._repo.db_path)
        assert {r["kind"] for r in rows} == {NewsItemKind.STATEMENT.value}
        assert {r["source"] for r in rows} == {NewsItemSource.GOOGLE_NEWS_RSS.value}
        assert all(r["speaker_role"] in {"US President", "Fed official", "JP PM", "UK PM", "EU official"}
                   for r in rows)
        for query, _ in rssmod.STATEMENT_SOURCES:
            assert rssmod._google_news_url(query) in calls
        assert sleeps == []

    def test_speaker_role_mapped_per_query(self, tmp_path):
        producer = _producer(tmp_path)
        roles = dict(rssmod.STATEMENT_SOURCES)
        routes: dict[str, bytes] = {}
        expected: dict[str, str] = {}
        published = _rfc(NOW - timedelta(hours=2))
        for index, (query, role) in enumerate(rssmod.STATEMENT_SOURCES):
            title = "Statement Topic %02d" % index
            routes[rssmod._google_news_url(query)] = _rss_bytes(
                [(title, "https://s/%02d" % index, published)]
            )
            expected[title] = role
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            producer.fetch_round(now=NOW)

        rows = {r["title"]: r["speaker_role"] for r in _items_in(producer._repo.db_path)}
        assert len(rows) == 6
        assert rows == expected

    def test_statements_capped_at_ten_total(self, tmp_path):
        producer = _producer(tmp_path)
        published = _rfc(NOW - timedelta(hours=2))
        routes: dict[str, bytes] = {}
        for index, (query, _) in enumerate(rssmod.STATEMENT_SOURCES):
            items = [
                ("Cap Topic %02d pair %d" % (index, n), "https://c/%02d/%d" % (index, n), published)
                for n in range(8)
            ]
            routes[rssmod._google_news_url(query)] = _rss_bytes(items)
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        # 6 queries × 8 unique items = 48, inherited cap keeps at most 10 (d.2674-2675).
        assert result.inserted == 10
        rows = _items_in(producer._repo.db_path)
        assert len(rows) == 10
        assert {r["kind"] for r in rows} == {NewsItemKind.STATEMENT.value}


# ---- 6. dead sources -> partial/failed, one run row per round -------------------


class TestErrors:
    def test_single_dead_query_partial_others_still_written(self, tmp_path):
        producer = _producer(tmp_path)
        dead_query = rssmod.STATEMENT_SOURCES[0][0]
        routes = {rssmod._google_news_url(dead_query): URLError("boom")}
        routes.update(_broad_urls())
        p1, p2, calls, sleeps = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        assert result.run_status is IngestRunStatus.PARTIAL
        assert result.attempted_sources == 11
        assert result.successful_sources == 10
        assert result.inserted == 4                     # broad items still written
        assert len(result.source_errors) == 1
        err = result.source_errors[0]
        assert isinstance(err, RssSourceError)
        assert err.source == dead_query
        assert err.kind is NewsItemKind.STATEMENT
        assert err.error_type == "URLError"
        assert sleeps == []
        assert rssmod._google_news_url(dead_query) in calls   # one shot, no loop

        run = _latest_run(producer._repo.db_path)
        assert run["producer"] == IngestProducer.RSS.value
        assert run["status"] == "partial"
        assert run["error_type"] == "URLError"
        assert run["items_written"] == 4
        assert _read(producer._repo.db_path, "SELECT COUNT(*) AS n FROM ingest_runs")["n"] == 1

    def test_all_sources_dead_failed_nothing_written(self, tmp_path):
        producer = _producer(tmp_path)
        routes = {rssmod._google_news_url(q): URLError("boom") for q in rssmod.BROAD_QUERIES}
        routes.update({url: URLError("boom") for url, _ in rssmod.EXTRA_RSS_FEEDS})
        routes.update({rssmod._google_news_url(q): URLError("boom") for q, _ in rssmod.STATEMENT_SOURCES})
        p1, p2, calls, sleeps = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        assert result.run_status is IngestRunStatus.FAILED
        assert result.successful_sources == 0
        assert result.inserted == 0
        assert len(result.source_errors) == 11
        run = _latest_run(producer._repo.db_path)
        assert run["status"] == "failed"
        assert run["error_type"] == "URLError"
        assert run["items_written"] == 0
        assert sleeps == []

    def test_all_sources_ok_empty_feeds_ok(self, tmp_path):
        producer = _producer(tmp_path)
        p1, p2, _, sleeps = _mock_routes({})
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        assert result.run_status is IngestRunStatus.OK
        assert result.successful_sources == 11
        assert result.inserted == 0
        assert result.source_errors == ()
        assert sleeps == []
        run = _latest_run(producer._repo.db_path)
        assert run["status"] == "ok"
        assert run["error_type"] is None


# ---- 7. typed result -------------------------------------------------------------


class TestTypedResult:
    def test_result_is_typed_not_raw_dict(self, tmp_path):
        producer = _producer(tmp_path)
        routes = _broad_urls()
        p1, p2, *_ = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)

        assert not isinstance(result, dict)
        assert isinstance(result, RssCollectionResult)
        assert isinstance(result.inserted, int)
        assert isinstance(result.updated, int)
        assert isinstance(result.run_status, IngestRunStatus)
        assert isinstance(result.run_id, int)
        assert isinstance(result.source_errors, tuple)
        assert all(isinstance(e, RssSourceError) for e in result.source_errors)