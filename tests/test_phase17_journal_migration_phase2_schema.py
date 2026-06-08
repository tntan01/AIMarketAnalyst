"""Phase 17.3 — verify migration 003 adds all Đợt 2 fields and is idempotent."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService

DOT2_FIELDS = [
    "planned_entry",
    "actual_entry",
    "planned_sl",
    "actual_sl",
    "planned_tp",
    "actual_tp",
    "actual_exit",
    "setup_type",
    "regime",
    "session",
    "m15_quality",
    "spread_at_entry",
    "expected_effective_rr",
    "realized_effective_rr",
    "manual_mistake_tags",
    "auto_mistake_tags",
    "execution_quality_score",
]


def _column_names(db_path: Path) -> set[str]:
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    cols = {row[1] for row in conn.execute("PRAGMA table_info(journal_entries)")}
    conn.close()
    return cols


# ---------------------------------------------------------------------------
# Fresh DB
# ---------------------------------------------------------------------------


def test_dot2_fields_in_fresh_db(tmp_path):
    """Fresh DB with all 3 migrations → all Đợt 2 columns exist."""
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    cols = _column_names(service.db_path)
    for field in DOT2_FIELDS:
        assert field in cols, f"Đợt 2 field '{field}' missing"


# ---------------------------------------------------------------------------
# Migration on top of existing 001+002 (simulated order)
# ---------------------------------------------------------------------------


def test_dot2_on_top_of_existing_db(tmp_path):
    """Migration 003 runs cleanly after 001+002, no crash."""
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    cols = _column_names(service.db_path)
    for field in DOT2_FIELDS:
        assert field in cols

    # Also verify Đợt 1 still present
    dot1 = ["result_r", "result_pct", "closed_at", "exit_reason", "actual_lot", "planned_lot"]
    for field in dot1:
        assert field in cols, f"Đợt 1 field '{field}' lost"


# ---------------------------------------------------------------------------
# Idempotent
# ---------------------------------------------------------------------------


def test_migration_003_idempotent(tmp_path):
    """Multiple migrate() calls don't crash or duplicate columns."""
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    service.migrate()
    service.migrate()

    # schema_migrations không trùng version
    with service._connect() as conn:
        dups = conn.execute(
            "SELECT version, COUNT(*) FROM schema_migrations GROUP BY version HAVING COUNT(*) > 1"
        ).fetchall()
        assert len(dups) == 0, f"Duplicate versions: {dups}"

    cols = _column_names(service.db_path)
    for field in DOT2_FIELDS:
        assert field in cols


# ---------------------------------------------------------------------------
# schema_migrations tracking
# ---------------------------------------------------------------------------


def test_version_003_tracked(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    with service._connect() as conn:
        row = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            ("003_add_journal_execution_fields",),
        ).fetchone()
    assert row is not None, "Migration 003 not tracked in schema_migrations"


# ---------------------------------------------------------------------------
# NULL-able columns
# ---------------------------------------------------------------------------


def test_dot2_columns_accept_none(tmp_path):
    """Insert a minimal entry — Đợt 2 fields all NULL, no crash."""
    from services.journal_service import JournalEntry

    service = JournalService(db_path=tmp_path / "test_phase17.db")

    entry = JournalEntry(
        id=None,
        timestamp_utc="2026-06-04T12:00:00Z",
        saved_at_utc="2026-06-04T12:00:01Z",
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        mode="single_analysis",
        data_source="MT5",
        market_regime="unknown",
        decision="skip",
        direction_bias="neutral",
        trade_permission="blocked",
        buy_score=0,
        sell_score=0,
        selected_scenario="",
        entry_zone="",
        stop_loss="",
        take_profit="",
        risk_reward="",
        suggested_lot=None,
        ai_commentary="",
        analysis_json="{}",
    )
    entry_id = service.create(entry)
    assert entry_id > 0

    fetched = service.get_entry(entry_id)
    assert fetched is not None
