"""Phase 17.13 — verify migration 003 is included in packaging."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_migration_003_file_exists():
    m003 = ROOT / "data" / "migrations" / "003_add_journal_execution_fields.sql"
    assert m003.is_file(), f"Migration 003 missing at {m003}"


def test_pyinstaller_spec_includes_migrations():
    spec_path = ROOT / "packaging" / "pyinstaller.spec"
    assert spec_path.is_file()
    content = spec_path.read_text(encoding="utf-8")
    assert "data/migrations" in content, (
        "pyinstaller.spec must include data/migrations for packaging"
    )
    assert "*.sql" in content or "003_add_journal_execution_fields" in content, (
        "pyinstaller.spec must glob *.sql or reference migration 003"
    )


def test_all_migrations_in_folder():
    """Every .sql file in data/migrations/ should be a valid migration."""
    mig_dir = ROOT / "data" / "migrations"
    sql_files = sorted(mig_dir.glob("*.sql"))
    assert len(sql_files) >= 3, f"Expected at least 3 migrations, got {len(sql_files)}: {[f.name for f in sql_files]}"
    for f in sql_files:
        text = f.read_text(encoding="utf-8").strip()
        assert len(text) > 0, f"Migration {f.name} is empty"
