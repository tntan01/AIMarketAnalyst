"""Phase 18.1 — surface audit: verify all upgrade modules, migrations, and tests exist."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ===========================================================================
# Core modules
# ===========================================================================

EXPECTED_MODULES = [
    "core.reason_codes",
    "core.trade_gate_engine",
    "core.account_guard",
    "core.statistical_edge_engine",
    "core.execution_quality_engine",
    "core.trade_mistake_detector",
    "core.final_score_engine",
    "core.decision_engine",
    "core.scanner_ranking_engine",
    "core.scanner",
    "core.analysis_engine",
    "core.signal_engine",
    "core.risk_engine",
    "core.entry_engine",
    "core.backtest_engine",
    "core.smc_context",
    "core.technical_context",
    "core.correlation_check",
    "core.reason_codes",
]

EXPECTED_SERVICES = [
    "services.journal_service",
    "services.mt5_service",
    "services.ai_service",
    "services.news_service",
    "services.settings_service",
]

EXPECTED_MIGRATIONS = [
    "data/migrations/001_create_journal.sql",
    "data/migrations/002_add_account_guard_fields.sql",
    "data/migrations/003_add_journal_execution_fields.sql",
]

EXPECTED_PHASE_TESTS = [
    "tests/test_phase13_final_score_realistic.py",
    "tests/test_phase14_decision_engine_realistic.py",
    "tests/test_phase15_scanner_ranking_realistic.py",
    "tests/test_phase16_test_manifest_exists.py",
]


# ===========================================================================
# Tests
# ===========================================================================


def test_all_core_modules_importable():
    for mod_name in EXPECTED_MODULES:
        try:
            __import__(mod_name)
        except ImportError as e:
            assert False, f"Cannot import {mod_name}: {e}"


def test_all_services_importable():
    for mod_name in EXPECTED_SERVICES:
        try:
            __import__(mod_name)
        except ImportError as e:
            assert False, f"Cannot import {mod_name}: {e}"


def test_all_migrations_exist():
    for path in EXPECTED_MIGRATIONS:
        f = ROOT / path
        assert f.is_file(), f"Migration missing: {path}"


def test_migration_003_has_all_dot2_fields():
    """Migration 003 should add 17 columns."""
    sql = (ROOT / "data/migrations/003_add_journal_execution_fields.sql").read_text(encoding="utf-8")
    expected_cols = [
        "planned_entry", "actual_entry", "planned_sl", "actual_sl",
        "planned_tp", "actual_tp", "actual_exit",
        "setup_type", "regime", "session", "m15_quality",
        "spread_at_entry", "expected_effective_rr", "realized_effective_rr",
        "manual_mistake_tags", "auto_mistake_tags", "execution_quality_score",
    ]
    for col in expected_cols:
        assert f"ADD COLUMN {col}" in sql, f"Migration 003 missing column: {col}"


def test_phase_test_files_exist():
    for path in EXPECTED_PHASE_TESTS:
        f = ROOT / path
        assert f.is_file(), f"Test missing: {path}"


def test_all_phase16_tests_exist():
    phase16_dir = ROOT / "tests"
    files = sorted(phase16_dir.glob("test_phase16_*.py"))
    names = {f.name for f in files}
    assert "test_phase16_test_manifest_exists.py" in names
    assert "test_phase16_score_rename_signal_score.py" in names
    assert "test_phase16_trade_gate_matrix.py" in names


def test_journal_service_has_required_methods():
    import services.journal_service as js
    assert hasattr(js.JournalService, "update_trade_outcome")
    assert hasattr(js.JournalService, "apply_execution_analysis_to_entry")
    assert hasattr(js.JournalService, "list_closed_trades_for_account_guard")
    assert hasattr(js, "normalize_tag_list")
    assert hasattr(js, "tags_to_json")


def test_pyinstaller_spec_has_migrations():
    spec = ROOT / "packaging" / "pyinstaller.spec"
    content = spec.read_text(encoding="utf-8")
    assert "data/migrations" in content
