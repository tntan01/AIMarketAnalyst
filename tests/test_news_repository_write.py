"""NewsRepository WRITE covenant tests (plan lô L2.1, contract §6.1/§6.4/§6.5/§8).

All tests run against a throwaway DB under ``tmp_path`` and the real
``data/migrations/news/*.sql`` migration folder — the production
``%APPDATA%`` tree (``news.db`` / ``journal.db``) is never touched.  Coverage
required by the batch:

1. migration runner: all 5 tables + ``schema_migrations``; re-running does not
   duplicate (version controlled); the news runner never touches ``journal.db``
   and never applies journal migrations to ``news.db``;
2. upsert/dedupe by ``dedupe_key``: insert / overwrite / no duplicate rows;
3. the 3 merge rules of contract §6.1, one dedicated test each;
4. ``delete_user_note`` only touches ``user_note`` rows (auto items stay);
5. ``purge_expired_runs`` takes its retention value as a parameter and never
   touches news/verdicts;
6. ``status`` stamped through ``core/news_freshness.classify_event_status``
   (the repository owns no status logic);
7. every write method returns a typed outcome — never a bare dict (C3).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.paths import PROJECT_ROOT
from core.news_freshness import classify_event_status
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    ImpactHint,
    IngestProducer,
    IngestRun,
    IngestRunStatus,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    RateSource,
    TrendVerdict,
    VerdictConfidence,
    VerdictDirection,
    VerdictHorizon,
    VerdictScopeType,
)
from core.news_policy import load_news_policy
from services.journal_service import JournalService
from services.news_repository import (
    ActualConflict,
    NewsRepository,
    UpsertEventsResult,
    UpsertItemsResult,
)

NEWS_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations" / "news"
JOURNAL_MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations"

NEWS_TABLES = {
    "news_events",
    "news_items",
    "interest_rates",
    "ai_trend_verdicts",
    "ingest_runs",
}


# ---- test scaffolding ----------------------------------------------------------


def _repo(tmp_path: Path) -> NewsRepository:
    return NewsRepository(
        db_path=tmp_path / "news.db",
        migrations_dir=NEWS_MIGRATIONS_DIR,
    )


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _read(db_path: Path, sql: str, params: tuple = ()) -> sqlite3.Row | None:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return conn.execute(sql, params).fetchone()
    finally:
        conn.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _event(
    dedupe: str,
    *,
    actual: str | None = None,
    source: EventSource = EventSource.FF_JSON,
    impact: EventImpact = EventImpact.HIGH,
    event_time: str = "2026-09-21T08:00:00Z",
    title: str = "CPI press conference",
    currency: str = "USD",
    actual_updated_at: str | None = None,
) -> CalendarEvent:
    return CalendarEvent(
        day_key=event_time[:10],
        event_time_utc=event_time,
        currency=currency,
        title=title,
        impact=impact,
        status=EventStatus.SCHEDULED,
        source=source,
        dedupe_key=dedupe,
        fetched_at="2026-09-21T01:00:00Z",
        forecast="0.3%",
        previous="0.2%",
        actual=actual,
        actual_updated_at=actual_updated_at,
    )


def _item(
    dedupe: str,
    *,
    kind: NewsItemKind = NewsItemKind.HEADLINE,
    source: NewsItemSource = NewsItemSource.GOOGLE_NEWS_RSS,
    title: str = "Fed holds rates steady",
    currencies: list[str] | None = None,
    content: str | None = None,
) -> NewsItem:
    return NewsItem(
        kind=kind,
        source=source,
        title=title,
        published_utc="2026-09-21T07:00:00Z",
        currencies=currencies if currencies is not None else ["USD"],
        dedupe_key=dedupe,
        fetched_at="2026-09-21T01:00:00Z",
        content=content,
        impact_hint=ImpactHint.HIGH if kind == NewsItemKind.USER_NOTE else None,
    )


def _rate(
    currency: str,
    observed_at: str,
    source: RateSource = RateSource.FRED,
    rate: float = 5.25,
) -> RateObservation:
    return RateObservation(
        currency=currency,
        rate=rate,
        observed_at=observed_at,
        source=source,
        fetched_at="2026-09-21T01:00:00Z",
    )


def _verdict() -> TrendVerdict:
    return TrendVerdict(
        created_at="2026-09-21T10:00:00Z",
        scope_type=VerdictScopeType.PAIR,
        scope_value="EUR/USD",
        horizon=VerdictHorizon.SHORT,
        direction=VerdictDirection.BULLISH,
        confidence=VerdictConfidence.MEDIUM,
        rationale="Đà tăng ngắn hạn",
        evidence_item_ids=[3, 7],
        input_snapshot={"window_days": 7, "events": 2, "items": 1},
        provider="sk-oracle",
        model="deepseek",
        prompt_hash="hash-1",
    )


def _run(
    finished_at: str,
    *,
    producer: IngestProducer = IngestProducer.RSS,
    status: IngestRunStatus = IngestRunStatus.OK,
) -> IngestRun:
    return IngestRun(
        producer=producer,
        started_at="2026-09-21T01:00:00Z",
        finished_at=finished_at,
        status=status,
        items_written=2,
    )


# ---- 1. migration runner --------------------------------------------------------


class TestMigrationRunner:
    def test_runner_creates_all_news_tables_and_versions(self, tmp_path):
        repo = _repo(tmp_path)
        tables = _table_names(repo.db_path)
        assert NEWS_TABLES <= tables
        assert "schema_migrations" in tables

        news_versions = {p.stem for p in NEWS_MIGRATIONS_DIR.glob("*.sql")}
        conn = sqlite3.connect(repo.db_path)
        try:
            applied = {
                row[0]
                for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
            }
        finally:
            conn.close()
        assert applied == news_versions
        # no journal migration ever leaks into the news runner's table
        assert not applied & {p.stem for p in JOURNAL_MIGRATIONS_DIR.glob("*.sql")}

    def test_rerun_does_not_duplicate_versions(self, tmp_path):
        repo = _repo(tmp_path)
        tables_before = _table_names(repo.db_path)
        conn = sqlite3.connect(repo.db_path)
        try:
            count_before = conn.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO news_events ("
                "day_key,event_time_utc,currency,title,impact,status,source,dedupe_key,fetched_at"
                ") VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "2026-09-21",
                    "2026-09-21T08:00:00Z",
                    "USD",
                    "CPI press conference",
                    "high",
                    "scheduled",
                    "ff_json",
                    "k-again",
                    "2026-09-21T01:00:00Z",
                ),
            )
            conn.commit()
        finally:
            conn.close()

        repo.migrate()

        tables_after = _table_names(repo.db_path)
        conn = sqlite3.connect(repo.db_path)
        try:
            count_after = conn.execute(
                "SELECT COUNT(*) FROM schema_migrations"
            ).fetchone()[0]
            events_after = conn.execute(
                "SELECT COUNT(*) FROM news_events"
            ).fetchone()[0]
        finally:
            conn.close()
        assert tables_after == tables_before
        assert count_after == count_before
        assert count_after == len(list(NEWS_MIGRATIONS_DIR.glob("*.sql")))
        assert events_after == 1

    def test_news_runner_never_touches_journal_db(self, tmp_path):
        journal_db = tmp_path / "journal.db"
        JournalService(db_path=journal_db, migrations_dir=JOURNAL_MIGRATIONS_DIR)
        journal_tables_before = _table_names(journal_db)
        assert "schema_migrations" in journal_tables_before

        _repo(tmp_path)  # news migration + writes only its own temp db

        journal_tables_after = _table_names(journal_db)
        assert journal_tables_after == journal_tables_before
        assert not (NEWS_TABLES & journal_tables_after)

    def test_news_db_contains_no_journal_tables(self, tmp_path):
        repo = _repo(tmp_path)
        tables = _table_names(repo.db_path)
        assert "schema_migrations" in tables
        assert "journal_entries" not in tables


# ---- 2. upsert / dedupe ---------------------------------------------------------


class TestUpsertDedupe:
    def test_events_insert_then_overwrite_by_dedupe_key(self, tmp_path):
        repo = _repo(tmp_path)
        first = repo.upsert_events([_event("k1", title="Old title")])
        assert first == UpsertEventsResult(inserted=1, updated=0, conflicts=())

        second = repo.upsert_events([_event("k1", title="New title")])
        assert second == UpsertEventsResult(inserted=0, updated=1, conflicts=())

        conn = sqlite3.connect(repo.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM news_events").fetchone()[0]
            row = conn.execute(
                "SELECT title FROM news_events WHERE dedupe_key='k1'"
            ).fetchone()
        finally:
            conn.close()
        assert count == 1
        assert row[0] == "New title"

    def test_items_insert_then_overwrite_by_dedupe_key(self, tmp_path):
        repo = _repo(tmp_path)
        first = repo.upsert_items([_item("i1", title="Old")])
        assert first == UpsertItemsResult(inserted=1, updated=0)

        second = repo.upsert_items([_item("i1", title="New")])
        assert second == UpsertItemsResult(inserted=0, updated=1)

        conn = sqlite3.connect(repo.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
            row = conn.execute(
                "SELECT title FROM news_items WHERE dedupe_key='i1'"
            ).fetchone()
        finally:
            conn.close()
        assert count == 1
        assert row[0] == "New"


# ---- 3. the three merge rules (contract §6.1) -----------------------------------


class TestMergeRules:
    def test_rule1_null_actual_never_overwrites_present_actual(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events(
            [_event("k1", source=EventSource.FF_HTML, actual="1.234",
                    actual_updated_at="2026-09-21T09:00:00Z")]
        )

        res = repo.upsert_events(
            [_event("k1", source=EventSource.FF_JSON, actual=None)]
        )
        assert res.updated == 1

        row = _read(
            repo.db_path,
            "SELECT actual, actual_updated_at FROM news_events WHERE dedupe_key='k1'",
        )
        assert row["actual"] == "1.234"
        assert row["actual_updated_at"] == "2026-09-21T09:00:00Z"

    def test_rule2_user_rows_are_never_auto_merged(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events(
            [_event("k1", source=EventSource.USER, actual="1.5", title="User typed")]
        )

        res = repo.upsert_events(
            [_event("k1", source=EventSource.FF_HTML, actual="1.8", title="auto title")]
        )
        assert res.updated == 0

        row = _read(
            repo.db_path,
            "SELECT actual, title FROM news_events WHERE dedupe_key='k1'",
        )
        assert row["actual"] == "1.5"
        assert row["title"] == "User typed"

    def test_rule2_user_items_are_never_auto_merged(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_items(
            [_item("i1", kind=NewsItemKind.USER_NOTE, source=NewsItemSource.USER,
                   title="My note")]
        )
        res = repo.upsert_items(
            [_item("i1", title="auto headline")]
        )
        assert res.updated == 0

        row = _read(
            repo.db_path,
            "SELECT title FROM news_items WHERE dedupe_key='i1'",
        )
        assert row["title"] == "My note"

    def test_rule3_user_actual_wins_and_conflict_is_returned_typed(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events(
            [_event("k1", source=EventSource.USER, actual="1.5")]
        )

        res = repo.upsert_events(
            [_event("k1", source=EventSource.FF_HTML, actual="1.8")]
        )
        assert res.updated == 0
        assert isinstance(res.conflicts, tuple)
        assert len(res.conflicts) == 1
        conflict = res.conflicts[0]
        assert isinstance(conflict, ActualConflict)
        assert conflict.dedupe_key == "k1"
        assert conflict.event_time_utc == "2026-09-21T08:00:00Z"
        assert conflict.currency == "USD"
        assert conflict.title == "CPI press conference"
        assert conflict.user_actual == "1.5"
        assert conflict.incoming_actual == "1.8"

        row = _read(
            repo.db_path,
            "SELECT actual FROM news_events WHERE dedupe_key='k1'",
        )
        assert row["actual"] == "1.5"

    def test_rule3_no_conflict_when_auto_matches_user_value(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_events(
            [_event("k1", source=EventSource.USER, actual="1.5")]
        )
        res = repo.upsert_events(
            [_event("k1", source=EventSource.FF_JSON, actual="1.5")]
        )
        assert res.conflicts == ()


# ---- 4. user_note protection ----------------------------------------------------


class TestUserNoteProtection:
    def test_delete_user_note_only_affects_user_notes(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_items(
            [
                _item("n1", kind=NewsItemKind.USER_NOTE,
                      source=NewsItemSource.USER, title="note", content="body"),
                _item("a1", title="auto headline"),
            ]
        )

        auto_id = _read(
            repo.db_path, "SELECT id FROM news_items WHERE dedupe_key='a1'"
        )["id"]
        assert repo.delete_user_note(auto_id) == 0

        conn = sqlite3.connect(repo.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
        finally:
            conn.close()
        assert count == 2

        note_id = _read(
            repo.db_path, "SELECT id FROM news_items WHERE dedupe_key='n1'"
        )["id"]
        assert repo.delete_user_note(note_id) == 1

        conn = sqlite3.connect(repo.db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
        finally:
            conn.close()
        assert count == 1
        assert _read(
            repo.db_path, "SELECT title FROM news_items WHERE dedupe_key='a1'"
        )["title"] == "auto headline"


# ---- 5. purge by explicit retention ---------------------------------------------


class TestPurgeRetention:
    def test_purge_expired_runs_keeps_content_and_honors_passed_value(self, tmp_path):
        repo = _repo(tmp_path)
        repo.record_run(_run("2020-01-01T00:00:00Z"))
        repo.record_run(_run(_utc_now()))
        repo.upsert_events([_event("k1")])
        repo.upsert_items([_item("i1")])
        repo.add_verdicts([_verdict()])

        deleted = repo.purge_expired_runs(retention_days=30)
        assert deleted == 1

        conn = sqlite3.connect(repo.db_path)
        try:
            runs_left = conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0]
            events_left = conn.execute("SELECT COUNT(*) FROM news_events").fetchone()[0]
            items_left = conn.execute("SELECT COUNT(*) FROM news_items").fetchone()[0]
            verdicts_left = conn.execute(
                "SELECT COUNT(*) FROM ai_trend_verdicts"
            ).fetchone()[0]
        finally:
            conn.close()

        assert runs_left == 1
        assert events_left == 1
        assert items_left == 1
        assert verdicts_left == 1

        # retention is caller-controlled, not hard-coded: a huge window deletes nothing
        assert repo.purge_expired_runs(retention_days=99999) == 0
        conn = sqlite3.connect(repo.db_path)
        try:
            runs_left = conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0]
        finally:
            conn.close()
        assert runs_left == 1


# ---- 6. status stamping (delegated to classify_event_status) --------------------


class TestStatusStamping:
    def test_upsert_stamps_status_via_classify_event_status(self, tmp_path):
        repo = _repo(tmp_path)
        now = datetime.now(timezone.utc)
        grace = timedelta(
            minutes=load_news_policy().event_stale_grace_minutes
        )

        released = _event("r1", actual="1.2")
        stale = _event("s1", actual=None, event_time="2020-01-01T08:00:00Z")
        scheduled = _event("c1", actual=None, event_time="2100-01-01T08:00:00Z")
        non_impact = _event(
            "n1", actual=None, event_time="2020-01-01T08:00:00Z", impact=EventImpact.NON
        )
        repo.upsert_events([released, stale, scheduled, non_impact])

        for dedupe, expected in {
            "r1": released,
            "s1": stale,
            "c1": scheduled,
            "n1": non_impact,
        }.items():
            row = _read(
                repo.db_path,
                "SELECT status FROM news_events WHERE dedupe_key=?",
                (dedupe,),
            )
            assert row["status"] == classify_event_status(
                expected, now, grace
            ).value

        assert _read(
            repo.db_path, "SELECT status FROM news_events WHERE dedupe_key='r1'"
        )["status"] == "released"
        assert _read(
            repo.db_path, "SELECT status FROM news_events WHERE dedupe_key='s1'"
        )["status"] == "stale"
        assert _read(
            repo.db_path, "SELECT status FROM news_events WHERE dedupe_key='c1'"
        )["status"] == "scheduled"
        assert _read(
            repo.db_path, "SELECT status FROM news_events WHERE dedupe_key='n1'"
        )["status"] == "scheduled"


# ---- 7. typed write results (no bare dict across the boundary) ------------------


class TestTypedWriteResults:
    def test_all_write_methods_return_typed_outcomes(self, tmp_path):
        repo = _repo(tmp_path)

        events = repo.upsert_events([_event("k1")])
        assert isinstance(events, UpsertEventsResult)
        assert isinstance(events.inserted, int)
        assert isinstance(events.conflicts, tuple)
        assert events.conflicts == ()

        items = repo.upsert_items([_item("i1")])
        assert isinstance(items, UpsertItemsResult)
        assert isinstance(items.inserted, int)

        rates = repo.add_rate_observations([_rate("USD", "2026-09-20")])
        assert isinstance(rates, int)
        assert rates == 1

        verdicts = repo.add_verdicts([_verdict()])
        assert isinstance(verdicts, int)
        assert verdicts == 1

        run_id = repo.record_run(_run(_utc_now()))
        assert isinstance(run_id, int)
        assert run_id > 0

        item_id = _read(
            repo.db_path, "SELECT id FROM news_items WHERE dedupe_key='i1'"
        )["id"]
        assert isinstance(repo.set_excluded(item_id, True), int)
        assert repo.set_excluded(item_id, True) == 1
        assert repo.delete_user_note(9_999_999) == 0
        assert isinstance(repo.purge_expired_runs(30), int)

    def test_rate_observations_upsert_never_duplicates_rows(self, tmp_path):
        repo = _repo(tmp_path)
        repo.add_rate_observations([_rate("USD", "2026-09-20", rate=5.25)])
        repo.add_rate_observations([_rate("USD", "2026-09-20", rate=5.50)])

        conn = sqlite3.connect(repo.db_path)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM interest_rates WHERE currency='USD' "
                "AND observed_at='2026-09-20' AND source='fred'"
            ).fetchone()[0]
            rate = conn.execute(
                "SELECT rate FROM interest_rates WHERE currency='USD' "
                "AND observed_at='2026-09-20' AND source='fred'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert count == 1
        assert rate == 5.50

        repo.add_rate_observations(
            [_rate("USD", "2026-09-20", source=RateSource.FF_HTML, rate=5.25)]
        )
        conn = sqlite3.connect(repo.db_path)
        try:
            distinct = conn.execute(
                "SELECT COUNT(*) FROM interest_rates WHERE currency='USD' "
                "AND observed_at='2026-09-20'"
            ).fetchone()[0]
        finally:
            conn.close()
        assert distinct == 2

    def test_typed_values_survive_json_columns(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_items([_item("i1", currencies=["USD", "JPY"])])
        repo.add_verdicts([_verdict()])

        item_row = _read(
            repo.db_path, "SELECT currencies_json FROM news_items WHERE dedupe_key='i1'"
        )
        assert json.loads(item_row["currencies_json"]) == ["USD", "JPY"]

        verdict_row = _read(
            repo.db_path,
            "SELECT evidence_item_ids_json, input_snapshot_json FROM ai_trend_verdicts LIMIT 1",
        )
        assert json.loads(verdict_row["evidence_item_ids_json"]) == [3, 7]
        assert json.loads(verdict_row["input_snapshot_json"]) == {
            "window_days": 7,
            "events": 2,
            "items": 1,
        }

    def test_set_excluded_toggles_flag_only_on_target_row(self, tmp_path):
        repo = _repo(tmp_path)
        repo.upsert_items([_item("i1"), _item("i2")])
        ids = [
            _read(
                repo.db_path, "SELECT id FROM news_items WHERE dedupe_key=?", (dedupe,)
            )["id"]
            for dedupe in ("i1", "i2")
        ]

        assert repo.set_excluded(ids[0], True) == 1
        row = _read(repo.db_path, "SELECT excluded FROM news_items WHERE id=?", (ids[0],))
        assert row["excluded"] == 1
        row = _read(repo.db_path, "SELECT excluded FROM news_items WHERE id=?", (ids[1],))
        assert row["excluded"] == 0

        assert repo.set_excluded(ids[0], False) == 1
        row = _read(repo.db_path, "SELECT excluded FROM news_items WHERE id=?", (ids[0],))
        assert row["excluded"] == 0

        assert repo.set_excluded(9_999_999, True) == 0


# ---- connection fabric -----------------------------------------------------------


class TestConnectionFabric:
    def test_connection_uses_wal_and_busy_timeout(self, tmp_path):
        repo = _repo(tmp_path)
        with repo._connect() as conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            busy_timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            synchronous = conn.execute("PRAGMA synchronous").fetchone()[0]
        assert journal_mode.lower() == "wal"
        assert busy_timeout >= 15000
        assert synchronous == 1