"""NewsRepository — the single read/write access point of the News database.

Written per plan batch L2.1 ("NewsRepository phần GHI + runner migration").
This file implements the WRITE half of the contract section 8 plus the
versioned migration runner for ``data/migrations/news/``. Domain data crossing
this module's boundary is exactly the ``core/news_models.py`` dataclasses
(contract section 5, R8) — never a bare dict.  The write methods return typed
result structures (``UpsertEventsResult``/``UpsertItemsResult``) or a plain
``int`` count/id, so no raw dict ever crosses the boundary (C3, contract §8:
"tất cả trả số bản ghi đã ghi/lỗi có kiểu").

Connection fabric is copied from ``JournalService._connect()``
(services/journal_service.py:584-590): WAL, ``busy_timeout=15s``,
``row_factory=sqlite3.Row``, ``synchronous=NORMAL``, one connection per call
via a context manager.  The relationship to the journal DB is intentionally
nil: the news runner globs only its own ``data/migrations/news/`` subdirectory
(QD-2, plan §5) and never opens ``journal.db``.

Forbidden in this file (contract §8): scoring formulas, business/gating
decisions, display strings, network imports.  Status classification is
delegated to ``core/news_freshness.classify_event_status`` (contract §6.5)
and the ``grace`` input is read from the policy via
``core/news_policy.load_news_policy`` (R4 — no hard-coded operational number).
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config.paths import PROJECT_ROOT, news_db_path
from core.news_freshness import classify_event_status
from core.news_models import (
    CalendarEvent,
    EventImpact,
    EventSource,
    EventStatus,
    IngestRun,
    NewsItem,
    NewsItemKind,
    NewsItemSource,
    RateObservation,
    TrendVerdict,
)
from core.news_policy import load_news_policy
from services.journal_models import SQLITE_BUSY_TIMEOUT_MS, SQLITE_TIMEOUT_SECONDS

__all__ = [
    "ActualConflict",
    "NewsRepository",
    "UpsertEventsResult",
    "UpsertItemsResult",
]


def _utc_now() -> str:
    """Current UTC time in the khuôn ISO-8601 form: ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ActualConflict:
    """Rule-3 detection (contract §6.1): an automatic actual was rejected in
    favor of the user's manually entered value, so the producer can log it in
    ``ingest_runs``.  Typed report packet — never a dict across the boundary."""

    dedupe_key: str
    event_time_utc: str
    currency: str
    title: str
    user_actual: str
    incoming_actual: str


@dataclass(frozen=True, slots=True)
class UpsertEventsResult:
    """Typed outcome of one ``upsert_events`` call (contract §8)."""

    inserted: int
    updated: int
    conflicts: tuple[ActualConflict, ...]


@dataclass(frozen=True, slots=True)
class UpsertItemsResult:
    """Typed outcome of one ``upsert_items`` call (contract §8)."""

    inserted: int
    updated: int


class NewsRepository:
    """Single access point of the News database — WRITE covenant, plan L2.1."""

    def __init__(
        self,
        db_path: Path | None = None,
        migrations_dir: Path | None = None,
    ) -> None:
        self.db_path = db_path or news_db_path()
        self.migrations_dir = migrations_dir or PROJECT_ROOT / "data" / "migrations" / "news"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.migrate()
        # Grace is an operational number: read from the policy loader (R4) —
        # no number hard-coded here or in the merge/status logic.
        self._event_stale_grace = timedelta(
            minutes=load_news_policy().event_stale_grace_minutes
        )

    # --- migration runner (khuôn: JournalService.migrate, journal_service.py:44-59) --

    def migrate(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
            )
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()}
            for migration in sorted(self.migrations_dir.glob("*.sql")):
                version = migration.stem
                if version in applied:
                    continue
                self._safe_execute_migration(conn, migration.read_text(encoding="utf-8"))
                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at_utc) VALUES (?, ?)",
                    (version, _utc_now()),
                )
            conn.commit()

    def _safe_execute_migration(self, conn: sqlite3.Connection, sql: str) -> None:
        """Execute migration SQL, skipping ALTER TABLE statements that would be
        no-ops on the current schema (khuôn: JournalService._safe_execute_migration,
        journal_service.py:61-122)."""
        lines = [line for line in sql.split("\n") if not line.strip().startswith("--")]
        clean_sql = "\n".join(lines)

        existing_columns: dict[str, set[str]] = {}

        statements = [s.strip() for s in clean_sql.split(";") if s.strip()]

        for stmt in statements:
            add_match = re.match(
                r"ALTER\s+TABLE\s+(\w+)\s+ADD\s+COLUMN\s+(\w+)",
                stmt,
                re.IGNORECASE,
            )
            rename_match = re.match(
                r"ALTER\s+TABLE\s+(\w+)\s+RENAME\s+COLUMN\s+(\w+)\s+TO\s+(\w+)",
                stmt,
                re.IGNORECASE,
            )
            if add_match:
                table_name = add_match.group(1)
                column_name = add_match.group(2)

                if table_name not in existing_columns:
                    rows = conn.execute(
                        f"PRAGMA table_info({table_name})"
                    ).fetchall()
                    existing_columns[table_name] = {row[1] for row in rows}

                if column_name in existing_columns[table_name]:
                    continue
                existing_columns[table_name].add(column_name)

            elif rename_match:
                table_name = rename_match.group(1)
                old_name = rename_match.group(2)
                new_name = rename_match.group(3)

                if table_name not in existing_columns:
                    rows = conn.execute(
                        f"PRAGMA table_info({table_name})"
                    ).fetchall()
                    existing_columns[table_name] = {row[1] for row in rows}

                if new_name in existing_columns[table_name] or old_name not in existing_columns[table_name]:
                    continue
                existing_columns[table_name].discard(old_name)
                existing_columns[table_name].add(new_name)

            conn.execute(stmt)

    # --- connection fabric (khuôn: JournalService._connect, journal_service.py:584-590) --

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=SQLITE_TIMEOUT_SECONDS)
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout={SQLITE_BUSY_TIMEOUT_MS}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    # --- WRITE: news_events ------------------------------------------------------

    def upsert_events(self, events: list[CalendarEvent]) -> UpsertEventsResult:
        """Insert or overwrite calendar events by ``dedupe_key`` (contract §4.2).

        Merger the three safe rules of contract §6.1:

        1. ``actual`` is only written when the incoming data carries a value —
           a fresh fetch (JSON calendar) never blanks an actual already present;
        2. a row whose ``source`` is ``user`` is never merged over by an
           automatic producer (only the user edits it);
        3. when an automatic actual conflicts with a user-entered actual, the
           manual value wins and an ``ActualConflict`` is returned so the
           producer can log it into ``ingest_runs``.

        ``status`` is stamped at upsert time via
        ``core.news_freshness.classify_event_status`` (contract §6.5 — the
        repository owns no status logic).
        """
        now = datetime.now(timezone.utc)
        now_utc = now.isoformat(timespec="seconds").replace("+00:00", "Z")
        inserted = 0
        updated = 0
        conflicts: list[ActualConflict] = []
        with self._connect() as conn:
            for event in events:
                existing = conn.execute(
                    "SELECT id, actual, actual_updated_at, source FROM news_events WHERE dedupe_key = ?",
                    (event.dedupe_key,),
                ).fetchone()

                if existing is None:
                    self._insert_event(conn, event, classify_event_status(event, now, self._event_stale_grace), now_utc)
                    inserted += 1
                    continue

                if existing["source"] == EventSource.USER.value and event.source != EventSource.USER:
                    if (
                        event.actual is not None
                        and existing["actual"] is not None
                        and event.actual != existing["actual"]
                    ):
                        conflicts.append(
                            ActualConflict(
                                dedupe_key=event.dedupe_key,
                                event_time_utc=event.event_time_utc,
                                currency=event.currency,
                                title=event.title,
                                user_actual=existing["actual"],
                                incoming_actual=event.actual,
                            )
                        )
                    continue

                if event.actual is not None:
                    merged_actual = event.actual
                    merged_actual_updated_at = event.actual_updated_at or now_utc
                else:
                    merged_actual = existing["actual"]
                    merged_actual_updated_at = existing["actual_updated_at"]

                self._update_event(
                    conn,
                    event,
                    merged_actual,
                    merged_actual_updated_at,
                    classify_event_status(self._status_event(event, merged_actual, now_utc), now, self._event_stale_grace),
                    existing["id"],
                    now_utc,
                )
                updated += 1
            conn.commit()
        return UpsertEventsResult(inserted=inserted, updated=updated, conflicts=tuple(conflicts))

    def _status_event(self, event: CalendarEvent, actual: str | None, actual_updated_at: str | None) -> CalendarEvent:
        """Copy a ``CalendarEvent`` carrying the merged ``actual`` so status is
        classified on the post-merge state (rule 1 keeps an existing actual)."""
        return CalendarEvent(
            day_key=event.day_key,
            event_time_utc=event.event_time_utc,
            currency=event.currency,
            title=event.title,
            impact=event.impact,
            status=event.status,
            source=event.source,
            dedupe_key=event.dedupe_key,
            fetched_at=event.fetched_at,
            actual=actual,
            actual_updated_at=actual_updated_at,
        )

    def _insert_event(
        self,
        conn: sqlite3.Connection,
        event: CalendarEvent,
        status: EventStatus,
        now_utc: str,
    ) -> None:
        conn.execute(
            "INSERT INTO news_events ("
            "day_key, event_time_utc, currency, title, impact, forecast, previous,"
            "actual, actual_updated_at, status, source, dedupe_key, raw_json, fetched_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                event.day_key,
                event.event_time_utc,
                event.currency,
                event.title,
                event.impact.value,
                event.forecast,
                event.previous,
                event.actual,
                _actual_updated_at(event, now_utc),
                status.value,
                event.source.value,
                event.dedupe_key,
                event.raw_json,
                event.fetched_at,
            ),
        )

    def _update_event(
        self,
        conn: sqlite3.Connection,
        event: CalendarEvent,
        actual: str | None,
        actual_updated_at: str | None,
        status: EventStatus,
        row_id: int,
        now_utc: str,
    ) -> None:
        conn.execute(
            "UPDATE news_events SET "
            "day_key=?, event_time_utc=?, currency=?, title=?, impact=?, forecast=?, previous=?,"
            "actual=?, actual_updated_at=?, status=?, source=?, raw_json=?, fetched_at=? "
            "WHERE id=?",
            (
                event.day_key,
                event.event_time_utc,
                event.currency,
                event.title,
                event.impact.value,
                event.forecast,
                event.previous,
                actual,
                actual_updated_at,
                status.value,
                event.source.value,
                event.raw_json,
                event.fetched_at,
                row_id,
            ),
        )

    # --- WRITE: news_items -------------------------------------------------------

    def upsert_items(self, items: list[NewsItem]) -> UpsertItemsResult:
        """Insert or overwrite news items by ``dedupe_key`` (contract §4.3).

        Applies contract §6.1 rule 2: a ``user`` row is never
        overwritten by an automatic producer; the user themselves may edit it
        (a ``user``-source row fed from the manual-entry controller updates
        normally).  ``currencies_json`` JSON encoding is this layer's job
        (docstring of ``core/news_models.py``).
        """
        inserted = 0
        updated = 0
        with self._connect() as conn:
            for item in items:
                existing = conn.execute(
                    "SELECT id, source FROM news_items WHERE dedupe_key = ?",
                    (item.dedupe_key,),
                ).fetchone()

                if existing is None:
                    self._insert_item(conn, item)
                    inserted += 1
                    continue

                if existing["source"] == NewsItemSource.USER.value and item.source != NewsItemSource.USER:
                    continue

                self._update_item(conn, item, existing["id"])
                updated += 1
            conn.commit()
        return UpsertItemsResult(inserted=inserted, updated=updated)

    def _insert_item(self, conn: sqlite3.Connection, item: NewsItem) -> None:
        conn.execute(
            "INSERT INTO news_items ("
            "kind, source, title, content, url, published_utc, currencies_json,"
            "impact_hint, speaker_role, excluded, dedupe_key, fetched_at"
            ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                item.kind.value,
                item.source.value,
                item.title,
                item.content,
                item.url,
                item.published_utc,
                json.dumps(item.currencies),
                item.impact_hint.value if item.impact_hint is not None else None,
                item.speaker_role,
                _bool_to_flag(item.excluded),
                item.dedupe_key,
                item.fetched_at,
            ),
        )

    def _update_item(self, conn: sqlite3.Connection, item: NewsItem, row_id: int) -> None:
        conn.execute(
            "UPDATE news_items SET "
            "kind=?, source=?, title=?, content=?, url=?, published_utc=?, currencies_json=?,"
            "impact_hint=?, speaker_role=?, excluded=?, fetched_at=? "
            "WHERE id=?",
            (
                item.kind.value,
                item.source.value,
                item.title,
                item.content,
                item.url,
                item.published_utc,
                json.dumps(item.currencies),
                item.impact_hint.value if item.impact_hint is not None else None,
                item.speaker_role,
                _bool_to_flag(item.excluded),
                item.fetched_at,
                row_id,
            ),
        )

    # --- WRITE: interest_rates ---------------------------------------------------

    def add_rate_observations(self, observations: list[RateObservation]) -> int:
        """Upsert rate observations keyed by the unique triplet
        ``(currency, observed_at, source)`` (contract §4.4) — a duplicate
        observation overwrites ``rate``/``fetched_at`` instead of duplicating a
        row.  Returns the number of observations written (typed count)."""
        count = 0
        with self._connect() as conn:
            for obs in observations:
                conn.execute(
                    "INSERT INTO interest_rates (currency, rate, observed_at, source, fetched_at) "
                    "VALUES (?,?,?,?,?) "
                    "ON CONFLICT (currency, observed_at, source) "
                    "DO UPDATE SET rate=excluded.rate, fetched_at=excluded.fetched_at",
                    (
                        obs.currency,
                        obs.rate,
                        obs.observed_at,
                        obs.source.value,
                        obs.fetched_at,
                    ),
                )
                count += 1
            conn.commit()
        return count

    # --- WRITE: ai_trend_verdicts -------------------------------------------------

    def add_verdicts(self, verdicts: list[TrendVerdict]) -> int:
        """Insert AI trend verdicts, one row per horizon (contract §4.5).

        ``evidence_item_ids_json`` and ``input_snapshot_json`` JSON encoding is
        this layer's job (docstring of ``core/news_models.py``).  Returns the
        number of verdict rows written (typed count)."""
        count = 0
        with self._connect() as conn:
            for verdict in verdicts:
                conn.execute(
                    "INSERT INTO ai_trend_verdicts ("
                    "created_at, scope_type, scope_value, horizon, direction, confidence,"
                    "rationale, evidence_item_ids_json, input_snapshot_json, provider, model, prompt_hash"
                    ") VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        verdict.created_at,
                        verdict.scope_type.value,
                        verdict.scope_value,
                        verdict.horizon.value,
                        verdict.direction.value,
                        verdict.confidence.value,
                        verdict.rationale,
                        json.dumps(verdict.evidence_item_ids),
                        json.dumps(verdict.input_snapshot),
                        verdict.provider,
                        verdict.model,
                        verdict.prompt_hash,
                    ),
                )
                count += 1
            conn.commit()
        return count

    # --- WRITE: ingest_runs -------------------------------------------------------

    def record_run(self, run: IngestRun) -> int:
        """Append one ingest run log row (contract §4.6).  Returns the new row
        id (typed, not a bare dict)."""
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO ingest_runs ("
                "producer, started_at, finished_at, status, items_written, error_type, error_detail"
                ") VALUES (?,?,?,?,?,?,?)",
                (
                    run.producer.value,
                    run.started_at,
                    run.finished_at,
                    run.status.value,
                    run.items_written,
                    run.error_type,
                    run.error_detail,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    # --- WRITE: user actions ------------------------------------------------------

    def set_excluded(self, item_id: int, excluded: bool) -> int:
        """Set the ``excluded`` flag on a news item (contract §4.3).  Auto items
        keep provenance — excluding is the only write path on them (§6.4);
        whether a given item may be excluded is a controller-level decision, not
        a repository gate.  Returns the number of rows flagged (0 or 1)."""
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE news_items SET excluded=? WHERE id=?",
                (_bool_to_flag(excluded), item_id),
            )
            conn.commit()
            return int(cursor.rowcount)

    def delete_user_note(self, item_id: int) -> int:
        """Physically delete one item — but only a ``user_note`` (contract
        §6.4).  An automatically harvested item has no physical-delete path and
        is merely rejected by this guard (rowcount 0).  Returns the number of
        rows deleted."""
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM news_items WHERE id=? AND kind=?",
                (item_id, NewsItemKind.USER_NOTE.value),
            )
            conn.commit()
            return int(cursor.rowcount)

    def purge_expired_runs(self, retention_days: int) -> int:
        """Delete operational ingest runs older than ``retention_days``
        (contract §4.6 retention: only the operational log; news and verdicts
        are never touched).

        ``retention_days`` is passed in — the caller reads it from the policy
        (``ingest_runs_retention_days``), so no operational number lives in
        this logic.  Returns the number of runs purged."""
        with self._connect() as conn:
            cutoff = (
                datetime.now(timezone.utc) - timedelta(days=retention_days)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            cursor = conn.execute(
                "DELETE FROM ingest_runs WHERE finished_at < ?",
                (cutoff,),
            )
            conn.commit()
            return int(cursor.rowcount)


def _actual_updated_at(event: CalendarEvent, now_utc: str) -> str | None:
    """Timestamp written alongside an actual: the producer's own stamp when it
    supplied one, otherwise the moment this write is happening."""
    if event.actual is None:
        return event.actual_updated_at
    return event.actual_updated_at or now_utc


def _bool_to_flag(value: bool) -> int:
    return 1 if value else 0