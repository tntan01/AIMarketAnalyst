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


# ---- 6b. DEFECT L2.5-01: converter None never reaches upsert_items ---------------


class TestDefectL2501:
    def test_bad_extra_pubdates_skipped_round_survives(self, tmp_path):
        """An extra-feed item with an unparseable/empty pubDate must be dropped
        at the converter boundary, never handed as ``None`` to ``upsert_items``:
        the round writes the healthy item, logs exactly one ``ingest_runs`` row
        (§4.6/§10) and no row carries an empty ``published_utc`` (§4.3)."""
        producer = _producer(tmp_path)
        bad_extra = _rss_bytes(
            [
                ("Broken timestamp item", "https://e/broken", "not-a-date"),
                ("Empty timestamp item", "https://e/empty", ""),
                ("Healthy piece", "https://e/ok", _rfc(NOW - timedelta(hours=2))),
            ]
        )
        routes = {rssmod.EXTRA_RSS_FEEDS[0][0]: bad_extra}
        p1, p2, _, sleeps = _mock_routes(routes)
        with p1, p2:
            result = producer.fetch_round(now=NOW)     # must not raise

        assert result.inserted == 1
        assert result.updated == 0
        assert result.run_status is IngestRunStatus.OK
        assert sleeps == []

        rows = _items_in(producer._repo.db_path)
        assert len(rows) == 1
        assert rows[0]["title"] == "Healthy piece"
        assert rows[0]["published_utc"]                  # no empty published_utc row
        assert not any(r["published_utc"] == "" for r in rows)

        assert _read(producer._repo.db_path, "SELECT COUNT(*) AS n FROM ingest_runs")["n"] == 1
        run = _latest_run(producer._repo.db_path)
        assert run["producer"] == IngestProducer.RSS.value
        assert run["status"] == "ok"
        assert run["items_written"] == 1


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