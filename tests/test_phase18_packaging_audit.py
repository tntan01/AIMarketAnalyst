"""Phase 18.8 — packaging audit: ensure migrations and assets are included."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

ROOT = Path(__file__).resolve().parent.parent


def test_all_migrations_exist():
    for name in [
        "001_create_journal.sql",
        "002_add_account_guard_fields.sql",
        "003_add_journal_execution_fields.sql",
    ]:
        f = ROOT / "data" / "migrations" / name
        assert f.is_file(), f"Migration missing: {name}"


def test_pyinstaller_spec_exists():
    spec = ROOT / "packaging" / "pyinstaller.spec"
    assert spec.is_file()


def test_build_script_exists():
    ps1 = ROOT / "packaging" / "build_windows.ps1"
    assert ps1.is_file()


def test_pyinstaller_spec_includes_migrations():
    spec = ROOT / "packaging" / "pyinstaller.spec"
    content = spec.read_text(encoding="utf-8")
    assert "data/migrations" in content, (
        "pyinstaller.spec must include data/migrations for packaging"
    )
    assert "*.sql" in content, (
        "pyinstaller.spec must glob *.sql files"
    )


def test_pyinstaller_spec_includes_assets():
    spec = ROOT / "packaging" / "pyinstaller.spec"
    content = spec.read_text(encoding="utf-8")
    assert "assets" in content, "pyinstaller.spec must include assets"
    assert "config" in content, "pyinstaller.spec must include config"
    assert "prompts" in content, "pyinstaller.spec must include prompts"


def test_installer_notes_exist():
    notes = ROOT / "packaging" / "installer_notes.md"
    assert notes.is_file()
