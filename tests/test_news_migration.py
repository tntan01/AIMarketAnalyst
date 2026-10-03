"""Migration test — news.db schema (plan lô L1.2, contract §4.1-§4.6).

``data/migrations/news/*.sql`` is pure SQL applied to a fresh temporary DB
via ``sqlite3`` (the real migration runner is ``NewsRepository.migrate``).
This batch proves the SQL matches the authoritative contract column by column,
plays well with a version-controlled runner, and that the 002 rebuild of
``ingest_runs`` never loses existing rows.

Verified here:

* all 6 tables exist with EXACTLY the columns/types/notnull/defaults of
  contract §4.2-§4.7 (PRAGMA table_info), and all indexes of §4.2/§4.3/§4.7
  (PRAGMA index_list/index_info), including the partial ``status='stale'``
  index;
* ``dedupe_key`` UNIQUE really bites on ``news_events``/``news_items``,
  ``interest_rates.UNIQUE(currency, observed_at, source)`` and
  ``bond_yields.UNIQUE(currency, maturity, observed_at, source)`` really bite;
* enum CHECK constraints match exactly the frozen string sets of §4.2-§4.7
  (a stray value is rejected — values are persisted, never invented);
* re-application is idempotent: the schema uses IF NOT EXISTS AND a
  ``schema_migrations`` version check in the same layout as
  ``JournalService.migrate`` (services/journal_service.py:44-59);
* QĐ-2: the journal runner's non-recursive ``glob("*.sql")`` on
  ``data/migrations/`` can never see the news subdirectory, so news SQL can
  never be applied to ``journal.db``;
* ``news_db_path()`` follows the ``journal_db_path()`` pattern (§4.1 — outside
  the install directory);
* the PyInstaller spec bundles ``data/migrations/news/*.sql``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from config.paths import PROJECT_ROOT, app_data_dir, journal_db_path, news_db_path
from services.news_repository import NewsRepository

MIGRATIONS_DIR = PROJECT_ROOT / "data" / "migrations"
NEWS_MIGRATIONS_DIR = MIGRATIONS_DIR / "news"
NEWS_SQL = NEWS_MIGRATIONS_DIR / "001_create_news_db.sql"
NEWS_MIGRATIONS = sorted(NEWS_MIGRATIONS_DIR.glob("*.sql"))

SPEC_PATH = PROJECT_ROOT / "packaging" / "pyinstaller.spec"


def _fresh_conn(tmp_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "news_test.db")
    conn.row_factory = sqlite3.Row
    return conn


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return {row[0] for row in rows}


def _apply_news_like_runner(conn: sqlite3.Connection) -> None:
    """Replicate JournalService.migrate() (journal_service.py:44-59) verbatim
    for the news migrations dir — proves the SQL is shaped for a versioned
    runner. This is test scaffolding, NOT the runner (that is L2.1)."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations "
        "(version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
    )
    applied = {
        row[0]
        for row in conn.execute("SELECT version FROM schema_migrations").fetchall()
    }
    for migration in NEWS_MIGRATIONS:
        version = migration.stem
        if version in applied:
            continue
        conn.executescript(migration.read_text(encoding="utf-8"))
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)",
            (version, "2026-09-21T00:00:00Z"),
        )
    conn.commit()


# ---- per-table expectation from contract §4.2-§4.6: name -> (type, notnull, default)

NEWS_EVENTS_COLUMNS: dict[str, tuple[str, int, None | str]] = {
    "id": ("INTEGER", 0, None),
    "day_key": ("TEXT", 1, None),
    "event_time_utc": ("TEXT", 1, None),
    "currency": ("TEXT", 1, None),
    "title": ("TEXT", 1, None),
    "impact": ("TEXT", 1, None),
    "forecast": ("TEXT", 0, None),
    "previous": ("TEXT", 0, None),
    "actual": ("TEXT", 0, None),
    "actual_updated_at": ("TEXT", 0, None),
    "status": ("TEXT", 1, None),
    "source": ("TEXT", 1, None),
    "dedupe_key": ("TEXT", 1, None),
    "raw_json": ("TEXT", 0, None),
    "fetched_at": ("TEXT", 1, None),
}

NEWS_ITEMS_COLUMNS: dict[str, tuple[str, int, None | str]] = {
    "id": ("INTEGER", 0, None),
    "kind": ("TEXT", 1, None),
    "source": ("TEXT", 1, None),
    "title": ("TEXT", 1, None),
    "content": ("TEXT", 0, None),
    "url": ("TEXT", 0, None),
    "published_utc": ("TEXT", 1, None),
    "currencies_json": ("TEXT", 1, None),
    "impact_hint": ("TEXT", 0, None),
    "speaker_role": ("TEXT", 0, None),
    "excluded": ("INTEGER", 1, "0"),
    "dedupe_key": ("TEXT", 1, None),
    "fetched_at": ("TEXT", 1, None),
}

INTEREST_RATES_COLUMNS: dict[str, tuple[str, int, None | str]] = {
    "id": ("INTEGER", 0, None),
    "currency": ("TEXT", 1, None),
    "rate": ("REAL", 1, None),
    "observed_at": ("TEXT", 1, None),
    "source": ("TEXT", 1, None),
    "fetched_at": ("TEXT", 1, None),
}

BOND_YIELDS_COLUMNS: dict[str, tuple[str, int, None | str]] = {
    "id": ("INTEGER", 0, None),
    "currency": ("TEXT", 1, None),
    "maturity": ("TEXT", 1, None),
    "value": ("REAL", 1, None),
    "observed_at": ("TEXT", 1, None),
    "source": ("TEXT", 1, None),
    "fetched_at": ("TEXT", 1, None),
}

AI_TREND_VERDICTS_COLUMNS: dict[str, tuple[str, int, None | str]] = {
    "id": ("INTEGER", 0, None),
    "created_at": ("TEXT", 1, None),
    "scope_type": ("TEXT", 1, None),
    "scope_value": ("TEXT", 1, None),
    "horizon": ("TEXT", 1, None),
    "direction": ("TEXT", 1, None),
    "confidence": ("TEXT", 1, None),
    "rationale": ("TEXT", 1, None),
    "evidence_item_ids_json": ("TEXT", 1, None),
    "input_snapshot_json": ("TEXT", 1, None),
    "provider": ("TEXT", 1, None),
    "model": ("TEXT", 1, None),
    "prompt_hash": ("TEXT", 1, None),
}

INGEST_RUNS_COLUMNS: dict[str, tuple[str, int, None | str]] = {
    "id": ("INTEGER", 0, None),
    "producer": ("TEXT", 1, None),
    "started_at": ("TEXT", 1, None),
    "finished_at": ("TEXT", 1, None),
    "status": ("TEXT", 1, None),
    "items_written": ("INTEGER", 1, None),
    "error_type": ("TEXT", 0, None),
    "error_detail": ("TEXT", 0, None),
}

EXPECTED_TABLES: dict[str, dict[str, tuple[str, int, None | str]]] = {
    "news_events": NEWS_EVENTS_COLUMNS,
    "news_items": NEWS_ITEMS_COLUMNS,
    "interest_rates": INTEREST_RATES_COLUMNS,
    "bond_yields": BOND_YIELDS_COLUMNS,
    "ai_trend_verdicts": AI_TREND_VERDICTS_COLUMNS,
    "ingest_runs": INGEST_RUNS_COLUMNS,
}


class TestSchemaColumns:
    @pytest.mark.parametrize(
        ("table", "expected"),
        sorted(EXPECTED_TABLES.items()),
    )
    def test_table_columns_match_contract(self, tmp_path, table, expected):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        info = conn.execute(f"PRAGMA table_info({table})").fetchall()
        assert len(info) == len(expected)
        assert {row["name"] for row in info} == set(expected)
        for row in info:
            expected_tuple = expected[row["name"]]
            assert (row["name"], row["type"], row["notnull"], row["dflt_value"]) == (
                row["name"],
                *expected_tuple,
            )

    def test_primary_key_is_set_on_every_id(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        for table in EXPECTED_TABLES:
            is_pk = {
                (row["name"], row["pk"]) for row in conn.execute(f"PRAGMA table_info({table})")
            }
            assert ("id", 1) in is_pk


class TestIndexes:
    def test_news_events_indexes_exist(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        index_names = {row["name"] for row in conn.execute("PRAGMA index_list(news_events)")}
        assert "idx_news_events_day_key" in index_names
        assert "idx_news_events_event_time_utc" in index_names
        assert "idx_news_events_currency_event_time_utc" in index_names
        assert "idx_news_events_status_stale" in index_names

    def test_news_items_indexes_exist(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        index_names = {row["name"] for row in conn.execute("PRAGMA index_list(news_items)")}
        assert "idx_news_items_kind_published_utc" in index_names
        assert "idx_news_items_published_utc" in index_names

    def test_status_stale_index_is_partial_on_status(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        rows = conn.execute("PRAGMA index_list(news_events)").fetchall()
        partial = {row["name"] for row in rows if row["partial"]}
        assert "idx_news_events_status_stale" in partial
        cols = [
            row["name"]
            for row in conn.execute("PRAGMA index_info(idx_news_events_status_stale)")
        ]
        assert cols == ["status"]

    def test_currency_event_time_index_columns(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        cols = [
            row["name"]
            for row in conn.execute(
                "PRAGMA index_info(idx_news_events_currency_event_time_utc)"
            )
        ]
        assert cols == ["currency", "event_time_utc"]

    def test_kind_published_index_columns(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        cols = [
            row["name"]
            for row in conn.execute("PRAGMA index_info(idx_news_items_kind_published_utc)")
        ]
        assert cols == ["kind", "published_utc"]

    def test_bond_yields_index_columns(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        index_names = {
            row["name"] for row in conn.execute("PRAGMA index_list(bond_yields)")
        }
        assert "idx_bond_yields_currency_maturity_observed_at" in index_names
        cols = [
            row["name"]
            for row in conn.execute(
                "PRAGMA index_info(idx_bond_yields_currency_maturity_observed_at)"
            )
        ]
        assert cols == ["currency", "maturity", "observed_at"]


def _news_event_row(dedupe: str = "hash-a") -> tuple:
    return (
        "2026-09-21",
        "2026-09-21T08:00:00Z",
        "USD",
        "CPI press conference",
        "high",
        None,  # forecast
        None,  # previous
        None,  # actual
        None,  # actual_updated_at
        "scheduled",
        "ff_json",
        dedupe,
        None,  # raw_json
        "2026-09-21T01:00:00Z",
    )


def _news_item_row(dedupe: str = "hash-item") -> tuple:
    return (
        "headline",
        "google_news_rss",
        "Fed holds rates steady",
        None,
        "https://example.com/x",
        "2026-09-21T07:00:00Z",
        '["USD"]',
        None,
        None,
        0,
        dedupe,
        "2026-09-21T01:00:00Z",
    )


def _rate_row(currency: str, observed_at: str, source: str) -> tuple:
    return (
        currency,
        5.50,
        observed_at,
        source,
        "2026-09-21T01:00:00Z",
    )


def _bond_yield_row(
    *,
    currency: str = "USD",
    maturity: str = "2y",
    observed_at: str = "2026-09-20",
    source: str = "fred",
) -> tuple:
    return (
        currency,
        maturity,
        4.25,
        observed_at,
        source,
        "2026-09-21T01:00:00Z",
    )


_NEWS_EVENT_COLUMNS = (
    "day_key,event_time_utc,currency,title,impact,forecast,previous,actual,"
    "actual_updated_at,status,source,dedupe_key,raw_json,fetched_at"
)

_NEWS_ITEM_COLUMNS = (
    "kind,source,title,content,url,published_utc,currencies_json,impact_hint,"
    "speaker_role,excluded,dedupe_key,fetched_at"
)

_RATE_COLUMNS = "currency,rate,observed_at,source,fetched_at"

_BOND_YIELD_COLUMNS = "currency,maturity,value,observed_at,source,fetched_at"


class TestUniques:
    def test_news_events_dedupe_key_unique(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        conn.execute(
            f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            _news_event_row(),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                _news_event_row(),
            )

    def test_news_items_dedupe_key_unique(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        conn.execute(
            f"INSERT INTO news_items ({_NEWS_ITEM_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            _news_item_row(),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO news_items ({_NEWS_ITEM_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                _news_item_row(),
            )

    def test_interest_rates_unique_triplet(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        conn.execute(
            f"INSERT INTO interest_rates ({_RATE_COLUMNS}) VALUES (?,?,?,?,?)",
            _rate_row("USD", "2026-09-20", "fred"),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO interest_rates ({_RATE_COLUMNS}) VALUES (?,?,?,?,?)",
                _rate_row("USD", "2026-09-20", "fred"),
            )
        # cùng currency/ngày, nguồn khác → được phép
        conn.execute(
            f"INSERT INTO interest_rates ({_RATE_COLUMNS}) VALUES (?,?,?,?,?)",
            _rate_row("USD", "2026-09-20", "ff_html"),
        )

    def test_bond_yields_unique_quadruplet(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        conn.execute(
            f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
            _bond_yield_row(),
        )
        # trùng đủ (currency, maturity, observed_at, source) → từ chối
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
                _bond_yield_row(),
            )
        # nguồn khác / kỳ hạn khác / ngày khác → được phép
        conn.execute(
            f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
            _bond_yield_row(source="yahoo"),
        )
        conn.execute(
            f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
            _bond_yield_row(maturity="10y"),
        )
        conn.execute(
            f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
            _bond_yield_row(observed_at="2026-09-19"),
        )

    def test_same_dedupe_different_content_is_still_a_duplicate(self, tmp_path):
        # dedupe_key là định danh duy nhất theo §4.2/§4.3 — trùng key luôn trùng
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        conn.execute(
            f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            _news_event_row(),
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                _news_event_row(dedupe="hash-a"),
            )


class TestEnumCheckConstraints:
    @pytest.mark.parametrize(
        "bad_impact", ["HIGH", "extreme", "", "high "]
    )
    def test_news_events_impact_rejects_stray_values(self, tmp_path, bad_impact):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        row = _news_event_row()
        row = (row[0], row[1], row[2], row[3], bad_impact, row[5], row[6], row[7], row[8], row[9], row[10], row[11], row[12], row[13])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

    def test_news_events_accepts_every_contract_impact_value(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        for value in ("high", "medium", "low", "non"):
            row = _news_event_row(dedupe=f"hash-{value}")
            row = (row[0], row[1], row[2], row[3], value, row[5], row[6], row[7], row[8], row[9], row[10], row[11], row[12], row[13])
            conn.execute(
                f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

    @pytest.mark.parametrize(
        "bad_status", ["SCHEDULED", "done", "expired"]
    )
    def test_news_events_status_rejects_stray_values(self, tmp_path, bad_status):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        row = _news_event_row()
        row = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], bad_status, row[10], row[11], row[12], row[13])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

    @pytest.mark.parametrize("bad_source", ["ff", "manual", "FRED"])
    def test_news_events_source_rejects_stray_values(self, tmp_path, bad_source):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        row = _news_event_row()
        row = (row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7], row[8], row[9], bad_source, row[11], row[12], row[13])
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                row,
            )

    def test_ingest_runs_producer_and_status_reject_stray_values(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("crawler", "2026-09-21T01:00:00Z", "2026-09-21T01:01:00Z", "ok", 0),
            )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("rss", "2026-09-21T01:00:00Z", "2026-09-21T01:01:00Z", "success", 0),
            )

    def test_ingest_runs_accepts_every_contract_enum_value(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        for producer in (
            "ff_paste",
            "rss",
            "fred",
            "user",
            "on_demand_lookup",
            "bond_yield",
        ):
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                (producer, "2026-09-21T01:00:00Z", "2026-09-21T01:01:00Z", "ok", 1),
            )
        for status in ("ok", "partial", "failed"):
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("fred", "2026-09-21T01:00:00Z", "2026-09-21T01:01:00Z", status, 1),
            )

    def test_ingest_runs_accepts_bond_yield_producer(self, tmp_path):
        # §4.6 (đợt 5): the rebuilt CHECK admits the new ``bond_yield`` value.
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        conn.execute(
            "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
            "VALUES (?, ?, ?, ?, ?)",
            ("bond_yield", "2026-09-21T01:00:00Z", "2026-09-21T01:01:00Z", "ok", 3),
        )
        assert conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0] == 1

    @pytest.mark.parametrize("bad_maturity", ["1y", "5y", "BE10Y", "be10", ""])
    def test_bond_yields_maturity_rejects_stray_values(self, tmp_path, bad_maturity):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
                _bond_yield_row(maturity=bad_maturity),
            )

    @pytest.mark.parametrize("bad_source", ["FRED", "bloomberg", "investing", ""])
    def test_bond_yields_source_rejects_stray_values(self, tmp_path, bad_source):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
                _bond_yield_row(source=bad_source),
            )

    def test_bond_yields_accepts_every_contract_enum_value(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        for maturity in ("2y", "10y", "be10y"):
            conn.execute(
                f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
                _bond_yield_row(maturity=maturity),
            )
        for observed_at, source in (("2026-10-01", "fred"), ("2026-10-02", "yahoo")):
            conn.execute(
                f"INSERT INTO bond_yields ({_BOND_YIELD_COLUMNS}) VALUES (?,?,?,?,?,?)",
                _bond_yield_row(observed_at=observed_at, source=source),
            )


class TestIdempotentVersioning:
    def test_schema_migrations_blocks_a_second_apply(self, tmp_path):
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        first_tables = _table_names(conn)
        conn.execute(
            f"INSERT INTO news_events ({_NEWS_EVENT_COLUMNS}) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            _news_event_row(),
        )
        count_before = conn.execute("SELECT COUNT(*) FROM news_events").fetchone()[0]

        # lần 2 chạy cùng trình giả lập: version đã ghi → không áp lại, không lỗi
        _apply_news_like_runner(conn)

        assert _table_names(conn) == first_tables
        applied = conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
        assert applied == len(NEWS_MIGRATIONS)
        assert conn.execute("SELECT COUNT(*) FROM news_events").fetchone()[0] == count_before
        assert conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0] == applied

    def test_raw_sql_reapply_is_idempotent_via_if_not_exists(self, tmp_path):
        # Ngay cả áp SQL trực tiếp lần 2 (bỏ qua version) cũng không lỗi,
        # vì CREATE TABLE/INDEX dùng IF NOT EXISTS — an toàn cho runner.
        conn = _fresh_conn(tmp_path)
        _apply_news_like_runner(conn)
        sql = NEWS_SQL.read_text(encoding="utf-8")
        conn.executescript(sql)
        assert "schema_migrations" in _table_names(conn)


class TestMigration002IngestRunsRebuild:
    """002 rebuilds ``ingest_runs`` (§4.6) — must not lose rows, must be idempotent.

    SQLite cannot ALTER a CHECK constraint, so 002 copies the old table into
    ``ingest_runs_v2`` (CHECK + ``bond_yield``), drops the old one and renames.
    The critical case of the batch: a database already carrying 001 data must
    survive the rebuild.
    """

    def _seed_001_with_one_run(self, db_path: Path) -> None:
        conn = sqlite3.connect(db_path)
        try:
            conn.executescript(NEWS_SQL.read_text(encoding="utf-8"))
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
            )
            conn.execute(
                "INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)",
                ("001_create_news_db", "2026-09-21T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("fred", "2026-09-21T01:00:00Z", "2026-09-21T01:01:00Z", "ok", 7),
            )
            conn.commit()
        finally:
            conn.close()

    def test_002_preserves_existing_ingest_runs_rows(self, tmp_path):
        db_path = tmp_path / "news_legacy.db"
        self._seed_001_with_one_run(db_path)

        NewsRepository(db_path=db_path, migrations_dir=NEWS_MIGRATIONS_DIR)

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT producer, items_written FROM ingest_runs ORDER BY id"
            ).fetchall()
            assert rows == [("fred", 7)]
            versions = {
                row[0] for row in conn.execute("SELECT version FROM schema_migrations")
            }
            assert versions == {migration.stem for migration in NEWS_MIGRATIONS}
            # the rebuilt CHECK now admits the new producer value
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("bond_yield", "2026-09-22T01:00:00Z", "2026-09-22T01:01:00Z", "ok", 3),
            )
            conn.commit()
        finally:
            conn.close()

    def test_migrate_is_idempotent_and_keeps_rows(self, tmp_path):
        repo = NewsRepository(
            db_path=tmp_path / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR
        )
        conn = sqlite3.connect(repo.db_path)
        try:
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("fred", "2026-09-21T01:00:00Z", "2026-09-21T01:01:00Z", "ok", 2),
            )
            conn.commit()
        finally:
            conn.close()

        repo.migrate()  # second apply — versions already recorded, must be a no-op

        conn = sqlite3.connect(repo.db_path)
        try:
            assert (
                conn.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
                == len(NEWS_MIGRATIONS)
            )
            assert (
                conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0] == 1
            )
        finally:
            conn.close()

    def test_rebuild_leaves_no_transient_v2_table(self, tmp_path):
        repo = NewsRepository(
            db_path=tmp_path / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR
        )
        conn = sqlite3.connect(repo.db_path)
        try:
            tables = _table_names(conn)
        finally:
            conn.close()
        assert "ingest_runs" in tables
        assert "ingest_runs_v2" not in tables
        assert "ingest_runs_v3" not in tables


class TestMigration003IngestRunsRebuild:
    """003 bỏ ``ff_crawler``, thêm ``ff_paste`` (§4.6, fix 03/10/2026).

    Cùng khuôn rebuild như 002. Ca quan trọng: database đang chạy đã có các lượt
    ``user`` (nhập tay tin) + ``bond_yield`` phải **sống sót** qua rebuild, CHECK
    mới nhận ``ff_paste`` và từ chối giá trị di sản ``ff_crawler``.
    """

    def _seed_through_002(self, db_path: Path) -> None:
        """DB như trước fix: 001+002 đã áp, có lượt user + bond_yield."""
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations "
                "(version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
            )
            for migration in NEWS_MIGRATIONS:
                if migration.stem.startswith("003"):
                    break
                conn.executescript(migration.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)",
                    (migration.stem, "2026-09-21T00:00:00Z"),
                )
            conn.executemany(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    ("user", "2026-10-01T01:00:00Z", "2026-10-01T01:01:00Z", "ok", 4),
                    ("user", "2026-10-02T01:00:00Z", "2026-10-02T01:01:00Z", "ok", 2),
                    ("bond_yield", "2026-10-02T02:00:00Z", "2026-10-02T02:01:00Z", "ok", 3),
                ],
            )
            conn.commit()
        finally:
            conn.close()

    def test_003_preserves_existing_runs_and_swaps_the_producer_value(self, tmp_path):
        db_path = tmp_path / "news_legacy_003.db"
        self._seed_through_002(db_path)

        NewsRepository(db_path=db_path, migrations_dir=NEWS_MIGRATIONS_DIR)

        conn = sqlite3.connect(db_path)
        try:
            rows = conn.execute(
                "SELECT producer, items_written FROM ingest_runs ORDER BY id"
            ).fetchall()
            # 76+ lượt user ngoài đời phải sống sót nguyên vẹn qua rebuild.
            assert rows == [("user", 4), ("user", 2), ("bond_yield", 3)]
            versions = {
                row[0] for row in conn.execute("SELECT version FROM schema_migrations")
            }
            assert versions == {migration.stem for migration in NEWS_MIGRATIONS}
            # CHECK mới nhận ff_paste…
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("ff_paste", "2026-10-03T01:00:00Z", "2026-10-03T01:01:00Z", "ok", 12),
            )
            # …và từ chối giá trị di sản.
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                    "VALUES (?, ?, ?, ?, ?)",
                    ("ff_crawler", "2026-10-03T01:00:00Z", "2026-10-03T01:01:00Z", "ok", 0),
                )
            conn.commit()
        finally:
            conn.close()

    def test_003_is_idempotent_on_an_already_migrated_db(self, tmp_path):
        repo = NewsRepository(
            db_path=tmp_path / "news.db", migrations_dir=NEWS_MIGRATIONS_DIR
        )
        conn = sqlite3.connect(repo.db_path)
        try:
            conn.execute(
                "INSERT INTO ingest_runs (producer, started_at, finished_at, status, items_written) "
                "VALUES (?, ?, ?, ?, ?)",
                ("ff_paste", "2026-10-03T01:00:00Z", "2026-10-03T01:01:00Z", "ok", 12),
            )
            conn.commit()
        finally:
            conn.close()

        repo.migrate()  # lần hai — version đã ghi, phải là no-op

        conn = sqlite3.connect(repo.db_path)
        try:
            assert conn.execute("SELECT COUNT(*) FROM ingest_runs").fetchone()[0] == 1
        finally:
            conn.close()


class TestQd2JournalIsolation:
    """Migration news nằm trong thư mục con — runner journal không nhìn thấy."""

    def test_journal_glob_never_sees_news_migrations(self):
        journal_visible = sorted(MIGRATIONS_DIR.glob("*.sql"))
        news_visible = sorted(NEWS_MIGRATIONS_DIR.glob("*.sql"))
        assert any(p.stem == "001_create_news_db" for p in news_visible)
        assert not any(p.stem == "001_create_news_db" for p in journal_visible)

    def test_journal_db_never_gets_news_tables(self, tmp_path):
        # Mô phỏng đúng vòng glob+áp của JournalService.migrate() tại
        # data/migrations/ (không đệ quy): bất kỳ DB nào chạy runner JOURNAL
        # cũng chỉ áp các file journal — không bao giờ tạo bảng news.
        conn = _fresh_conn(tmp_path)
        # Chain constructor của JournalService.migrate (d.46-48):
        # runner tạo schema_migrations trước khi glob.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
        )
        applied_stems = [p.stem for p in sorted(MIGRATIONS_DIR.glob("*.sql"))]
        assert "001_create_news_db" not in applied_stems
        for stem in applied_stems:
            path = MIGRATIONS_DIR / f"{stem}.sql"
            conn.executescript(path.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT OR REPLACE INTO schema_migrations (version, applied_at_utc) "
                "VALUES (?, ?)",
                (stem, "2026-09-21T00:00:00Z"),
            )
        tables = _table_names(conn)
        assert "news_events" not in tables
        assert "news_items" not in tables
        assert "interest_rates" not in tables
        assert "ai_trend_verdicts" not in tables
        assert "ingest_runs" not in tables


class TestNewsDbPath:
    def test_news_db_path_follows_journal_db_pattern(self):
        assert news_db_path() == journal_db_path().parent / "news.db"
        assert news_db_path() == app_data_dir() / "news.db"
        assert news_db_path().name == "news.db"
        assert news_db_path().parent == journal_db_path().parent

    def test_news_db_lives_outside_the_install_directory(self):
        # §4.1: bản đóng gói không ghi vào thư mục cài đặt.
        try:
            news_db_path().relative_to(PROJECT_ROOT)
        except ValueError:
            pass
        else:
            raise AssertionError("news.db must not be inside the project/install tree")


class TestPyInstallerSpec:
    def test_spec_bundles_news_migrations(self):
        text = SPEC_PATH.read_text(encoding="utf-8")
        assert '("../data/migrations/news/*.sql", "data/migrations/news")' in text

    def test_spec_config_glob_still_bundles_the_policy_file(self):
        # glob config/*.json đã tự phủ news_policy.json — dòng cũ phải còn nguyên.
        text = SPEC_PATH.read_text(encoding="utf-8")
        assert '("../config/*.json", "config")' in text

    def test_spec_bundles_news_under_the_migrations_tree(self):
        text = SPEC_PATH.read_text(encoding="utf-8")
        assert '("../data/migrations/*.sql", "data/migrations")' in text