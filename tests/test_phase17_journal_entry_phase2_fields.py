"""Phase 17.4 — verify JournalEntry dataclass + create/get/list with Đợt 2 fields."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService, JournalEntry


DOT2_FIELD_DEFAULTS = {
    "planned_entry": 1.0850,
    "actual_entry": 1.0860,
    "planned_sl": 1.0800,
    "actual_sl": 1.0790,
    "planned_tp": 1.0950,
    "actual_tp": 1.0950,
    "actual_exit": 1.0920,
    "setup_type": "pullback",
    "regime": "trend_up",
    "session": "London",
    "m15_quality": "strict",
    "spread_at_entry": 0.0002,
    "expected_effective_rr": 1.6,
    "realized_effective_rr": 1.2,
    "manual_mistake_tags": '["closed_too_early"]',
    "auto_mistake_tags": '["chased_price"]',
    "execution_quality_score": 75,
}


def _base_entry(**overrides) -> JournalEntry:
    kwargs = {
        "id": None,
        "timestamp_utc": "2026-06-04T12:00:00Z",
        "saved_at_utc": "2026-06-04T12:00:01Z",
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "mode": "single_analysis",
        "data_source": "MT5",
        "market_regime": "trend_up",
        "decision": "watch",
        "direction_bias": "buy",
        "trade_permission": "allowed",
        "buy_score": 82,
        "sell_score": 55,
        "selected_scenario": "buy",
        "entry_zone": "[1.10, 1.12]",
        "stop_loss": "1.09",
        "take_profit": "[1.15]",
        "risk_reward": "1:2.0",
        "suggested_lot": 0.10,
        "ai_commentary": "",
        "analysis_json": "{}",
    }
    kwargs.update(overrides)
    return JournalEntry(**kwargs)


def test_journal_entry_has_all_dot2_fields():
    """JournalEntry dataclass has all 17 Đợt 2 annotations."""
    annotations = JournalEntry.__dataclass_fields__ if hasattr(JournalEntry, '__dataclass_fields__') else {}
    for f in DOT2_FIELD_DEFAULTS:
        assert f in annotations, f"JournalEntry missing Đợt 2 field: {f}"


def test_create_and_read_all_dot2_fields(tmp_path):
    """All Đợt 2 fields survive create → get_entry round-trip."""
    service = JournalService(db_path=tmp_path / "test_phase17.db")

    entry = _base_entry(**DOT2_FIELD_DEFAULTS)
    entry_id = service.create(entry)
    assert entry_id > 0

    fetched = service.get_entry(entry_id)
    assert fetched is not None
    for field, expected in DOT2_FIELD_DEFAULTS.items():
        actual = getattr(fetched, field)
        assert actual == expected, f"Field '{field}': expected {expected!r}, got {actual!r}"


def test_create_and_list_has_dot2_fields(tmp_path):
    """list_entries() also returns Đợt 2 fields correctly."""
    service = JournalService(db_path=tmp_path / "test_phase17.db")

    entry = _base_entry(**DOT2_FIELD_DEFAULTS)
    service.create(entry)

    results = service.list_entries()
    assert len(results) >= 1
    fetched = results[0]
    assert fetched.m15_quality == "strict"
    assert fetched.execution_quality_score == 75
    assert fetched.expected_effective_rr == 1.6


def test_legacy_entry_without_dot2_get_defaults(tmp_path):
    """Entries created without Đợt 2 fields get None defaults."""
    service = JournalService(db_path=tmp_path / "test_phase17.db")

    entry = _base_entry()  # no Đợt 2 fields
    entry_id = service.create(entry)

    fetched = service.get_entry(entry_id)
    assert fetched is not None
    assert fetched.m15_quality is None
    assert fetched.execution_quality_score is None
    assert fetched.auto_mistake_tags is None
