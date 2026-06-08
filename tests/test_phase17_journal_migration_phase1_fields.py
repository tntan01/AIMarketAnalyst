"""Phase 17.2 — verify Đợt 1 migration fields exist and are idempotent, journal read/write works."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService, JournalEntry, journal_entry_from_analysis

DOT1_FIELDS = [
    "result_r",
    "result_pct",
    "closed_at",
    "exit_reason",
    "actual_lot",
    "planned_lot",
]


# ---------------------------------------------------------------------------
# Migration schema tests
# ---------------------------------------------------------------------------


def test_dot1_fields_in_fresh_db(tmp_path):
    """Fresh DB with migrations → all Đợt 1 columns exist."""
    db_path = tmp_path / "test_phase17.db"
    service = JournalService(db_path=db_path)

    cols = _get_columns(db_path)
    for field in DOT1_FIELDS:
        assert field in cols, f"Đợt 1 field '{field}' missing"


def test_migration_idempotent(tmp_path):
    """Calling migrate() again does not crash or duplicate."""
    db_path = tmp_path / "test_phase17.db"
    service = JournalService(db_path=db_path)
    # Second call
    service.migrate()
    # Third call
    service.migrate()

    # schema_migrations should not have duplicate versions
    with service._connect() as conn:
        versions = conn.execute("SELECT version, COUNT(*) FROM schema_migrations GROUP BY version HAVING COUNT(*) > 1").fetchall()
        assert len(versions) == 0, f"Duplicate migration versions: {versions}"

    # Columns still present
    cols = _get_columns(db_path)
    for field in DOT1_FIELDS:
        assert field in cols, f"Đợt 1 field '{field}' lost after re-migrate"


# ---------------------------------------------------------------------------
# Journal create/get round-trip
# ---------------------------------------------------------------------------


def test_create_and_read_dot1_fields(tmp_path):
    """Insert a JournalEntry with Đợt 1 fields and read them back correctly."""
    db_path = tmp_path / "test_phase17.db"
    service = JournalService(db_path=db_path)

    entry = JournalEntry(
        id=None,
        timestamp_utc="2026-06-04T12:00:00Z",
        saved_at_utc="2026-06-04T12:00:01Z",
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        mode="single_analysis",
        data_source="MT5",
        market_regime="trend_up",
        decision="watch",
        direction_bias="buy",
        trade_permission="allowed",
        buy_score=82,
        sell_score=55,
        selected_scenario="buy",
        entry_zone="[1.10, 1.12]",
        stop_loss="1.09",
        take_profit="[1.15]",
        risk_reward="1:2.0",
        suggested_lot=0.10,
        ai_commentary="",
        analysis_json="{}",
        result_r=-1.0,
        result_pct=-0.8,
        closed_at="2026-06-04T14:00:00Z",
        exit_reason="stop_loss",
        actual_lot=0.20,
        planned_lot=0.10,
    )

    entry_id = service.create(entry)
    assert entry_id > 0

    fetched = service.get_entry(entry_id)
    assert fetched is not None
    assert fetched.result_r == -1.0
    assert fetched.result_pct == -0.8
    assert fetched.closed_at == "2026-06-04T14:00:00Z"
    assert fetched.exit_reason == "stop_loss"
    assert fetched.actual_lot == 0.20
    assert fetched.planned_lot == 0.10


def test_dot1_fields_nullable(tmp_path):
    """Đợt 1 fields accept NULL by default."""
    db_path = tmp_path / "test_phase17.db"
    service = JournalService(db_path=db_path)

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
        # No Đợt 1 fields — should default to None
    )

    entry_id = service.create(entry)
    fetched = service.get_entry(entry_id)
    assert fetched is not None
    assert fetched.result_r is None
    assert fetched.result_pct is None
    assert fetched.closed_at is None
    assert fetched.exit_reason is None
    assert fetched.actual_lot is None
    assert fetched.planned_lot is None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("PRAGMA table_info(journal_entries)")
    result = {row[1] for row in cursor.fetchall()}
    conn.close()
    return result
