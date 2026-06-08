"""Phase 17.11 — test migration from old DB (001+002) to 003 preserves data."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService, JournalEntry

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "data" / "migrations"


def _create_old_db(db_path: Path) -> None:
    """Simulate a DB with only migrations 001 and 002 applied, plus one row of data."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    # Apply 001
    conn.executescript((MIGRATIONS_DIR / "001_create_journal.sql").read_text(encoding="utf-8"))
    # Apply 002
    conn.executescript((MIGRATIONS_DIR / "002_add_account_guard_fields.sql").read_text(encoding="utf-8"))

    # Track versions
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at_utc TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO schema_migrations VALUES ('001_create_journal', '2026-06-01T00:00:00Z')")
    conn.execute("INSERT INTO schema_migrations VALUES ('002_add_account_guard_fields', '2026-06-02T00:00:00Z')")

    # Insert a row with old fields
    conn.execute(
        """INSERT INTO journal_entries
           (timestamp_utc, saved_at_utc, symbol, broker_symbol, mode, data_source,
            market_regime, decision, direction_bias, trade_permission,
            buy_score, sell_score, selected_scenario, entry_zone, stop_loss, take_profit,
            risk_reward, suggested_lot, ai_commentary, analysis_json,
            result_r, result_pct, closed_at, exit_reason, actual_lot, planned_lot)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            "2026-06-04T12:00:00Z", "2026-06-04T12:00:01Z",
            "EUR/USD", "EURUSD", "single_analysis", "MT5",
            "trend_up", "watch", "buy", "allowed",
            82, 55, "buy", "[1.10, 1.12]", "1.09", "[1.15]",
            "1:2.0", 0.10, "", "{}",
            -1.0, -0.8, "2026-06-04T14:00:00Z", "stop_loss", 0.20, 0.10,
        ),
    )
    conn.commit()
    conn.close()


def test_old_db_upgrades_without_data_loss(tmp_path):
    db_path = tmp_path / "test_phase17_old.db"
    _create_old_db(db_path)

    # Now open with JournalService (will apply migration 003)
    service = JournalService(db_path=db_path)

    # Old row still exists
    entries = service.list_entries()
    assert len(entries) >= 1
    old_entry = entries[0]
    assert old_entry.symbol == "EUR/USD"
    assert old_entry.buy_score == 82
    assert old_entry.sell_score == 55
    assert old_entry.result_r == -1.0
    assert old_entry.closed_at == "2026-06-04T14:00:00Z"
    assert old_entry.exit_reason == "stop_loss"
    assert old_entry.actual_lot == 0.20
    assert old_entry.planned_lot == 0.10
    # Đợt 2 fields are None for the old row
    assert old_entry.m15_quality is None
    assert old_entry.execution_quality_score is None


def test_schema_migrations_has_003(tmp_path):
    db_path = tmp_path / "test_phase17_old.db"
    _create_old_db(db_path)
    service = JournalService(db_path=db_path)

    with service._connect() as conn:
        row = conn.execute(
            "SELECT version FROM schema_migrations WHERE version = ?",
            ("003_add_journal_execution_fields",),
        ).fetchone()
    assert row is not None, "Migration 003 not tracked"


def test_new_entry_with_dot2_fields_after_upgrade(tmp_path):
    """After upgrade, inserting new entry with Đợt 2 fields works."""
    db_path = tmp_path / "test_phase17_old.db"
    _create_old_db(db_path)
    service = JournalService(db_path=db_path)

    new_entry = JournalEntry(
        id=None,
        timestamp_utc="2026-06-04T12:00:00Z",
        saved_at_utc="2026-06-04T12:00:01Z",
        symbol="GBP/JPY", broker_symbol="GBPJPY",
        mode="single_analysis", data_source="MT5",
        market_regime="trend_down", decision="wait", direction_bias="sell",
        trade_permission="allowed", buy_score=30, sell_score=75,
        selected_scenario="sell", entry_zone="", stop_loss="", take_profit="",
        risk_reward="1:2.0", suggested_lot=0.10, ai_commentary="", analysis_json="{}",
        m15_quality="strict", execution_quality_score=90,
        expected_effective_rr=1.8,
    )
    eid = service.create(new_entry)
    fetched = service.get_entry(eid)
    assert fetched is not None
    assert fetched.m15_quality == "strict"
    assert fetched.execution_quality_score == 90
    assert fetched.expected_effective_rr == 1.8
