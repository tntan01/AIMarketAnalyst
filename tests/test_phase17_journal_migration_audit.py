"""Phase 17.1 — audit journal migration state: Đợt 1 already done, Đợt 2 pending."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.paths import app_data_dir


# Đợt 1 fields (should exist already from migration 002)
DOT1_FIELDS = [
    "result_r",
    "result_pct",
    "closed_at",
    "exit_reason",
    "actual_lot",
    "planned_lot",
]

# Đợt 2 fields (NOT yet in any migration — Phase 17 will add them)
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


def _temp_db_path() -> Path:
    return Path(app_data_dir()) / "test_phase17_audit.db"


def _run_migrations(db_path: Path) -> None:
    """Run all existing migrations on a fresh temp DB."""
    migrations_dir = Path(__file__).resolve().parent.parent / "data" / "migrations"
    conn = sqlite3.connect(str(db_path))
    migrated = set()
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = sql_file.stem.split("_")[0]
        if version in migrated:
            continue
        conn.executescript(sql_file.read_text(encoding="utf-8"))
        migrated.add(version)
    conn.commit()
    conn.close()


def test_dot1_fields_exist_in_schema():
    """All Đợt 1 fields exist after running migrations 001+002."""
    db_path = _temp_db_path()
    db_path.unlink(missing_ok=True)
    _run_migrations(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("PRAGMA table_info(journal_entries)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    for field in DOT1_FIELDS:
        assert field in columns, f"Đợt 1 field '{field}' missing in schema"

    db_path.unlink(missing_ok=True)


def test_dot2_fields_now_exist_in_schema():
    """Đợt 2 fields SHOULD exist after migration 003 was created in Phase 17.3."""
    db_path = _temp_db_path()
    db_path.unlink(missing_ok=True)
    _run_migrations(db_path)

    conn = sqlite3.connect(str(db_path))
    cursor = conn.execute("PRAGMA table_info(journal_entries)")
    columns = {row[1] for row in cursor.fetchall()}
    conn.close()

    for field in DOT2_FIELDS:
        assert field in columns, f"Đợt 2 field '{field}' missing — migration 003 may not have run"

    db_path.unlink(missing_ok=True)


def test_journal_entry_dataclass_has_dot1_fields():
    """JournalEntry dataclass has all Đợt 1 fields."""
    from services.journal_service import JournalEntry
    fields = {k for k in JournalEntry.__dict__.get("__annotations__", {})}
    for f in DOT1_FIELDS:
        assert f in fields, f"JournalEntry missing Đợt 1 field: {f}"


def test_no_migration_003_exists():
    """Verify migration 003.sql EXISTS (created in Phase 17.3 as 003_add_journal_execution_fields.sql)."""
    m003 = Path(__file__).resolve().parent.parent / "data" / "migrations" / "003_add_journal_execution_fields.sql"
    assert m003.exists(), "003 migration missing — Đợt 2 not applied"
