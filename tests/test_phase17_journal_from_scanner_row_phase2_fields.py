"""Phase 17.7 — verify journal_entry_from_scanner_row() populates Đợt 2 fields."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import journal_entry_from_scanner_row, JournalService


def _fake_scanner_row() -> dict:
    return {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "market_regime": "trend_up",
        "scanner_action": "watch",
        "direction_bias": "buy",
        "trade_permission": "allowed",
        "buy_score": 82,
        "sell_score": 60,
        "best_side": "buy",
        "short_reason": "test",
        "risk_reward": "1:1.8",
        "entry_status": "waiting_confirmation",
        "m15_quality": "loose",
        "expected_effective_rr": 1.45,
        "entry_zone": [1.0840, 1.0860],
        "stop_loss": 1.0800,
        "take_profit": [1.0950],
        "planned_lot": 0.10,
        "auto_mistake_tags": ["ignored_m15"],
    }


def test_regime():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.regime == "trend_up"


def test_m15_quality():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.m15_quality == "loose"


def test_expected_effective_rr():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.expected_effective_rr == 1.45


def test_planned_entry():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.planned_entry == 1.0850


def test_planned_sl():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.planned_sl == 1.0800


def test_planned_tp():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.planned_tp == 1.0950


def test_planned_lot():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.planned_lot == 0.10


def test_auto_mistake_tags():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.auto_mistake_tags is not None
    assert "ignored_m15" in entry.auto_mistake_tags


def test_setup_type():
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    assert entry.setup_type == "waiting_confirmation"


def test_persist_via_service(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    entry = journal_entry_from_scanner_row(_fake_scanner_row())
    entry_id = service.create(entry)
    fetched = service.get_entry(entry_id)
    assert fetched is not None
    assert fetched.m15_quality == "loose"
    assert fetched.expected_effective_rr == 1.45
    assert fetched.planned_lot == 0.10
