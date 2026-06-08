"""Phase 17.8 — verify list_closed_trades_for_account_guard() returns Đợt 2 fields."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService, JournalEntry


def _insert_closed_trade(service: JournalService, **overrides):
    base = {
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
        "result_r": -1.0,
        "result_pct": -0.8,
        "closed_at": "2026-06-04T14:00:00Z",
        "exit_reason": "stop_loss",
        "actual_lot": 0.20,
        "planned_lot": 0.10,
        "planned_entry": 1.0850,
        "actual_entry": 1.0860,
        "planned_sl": 1.0800,
        "actual_sl": 1.0790,
        "planned_tp": 1.0950,
        "actual_tp": 1.0920,
        "actual_exit": 1.0805,
        "setup_type": "pullback",
        "regime": "trend_up",
        "session": "London",
        "m15_quality": "strict",
        "spread_at_entry": 0.0002,
        "expected_effective_rr": 1.75,
        "realized_effective_rr": 1.2,
        "manual_mistake_tags": '["closed_too_early"]',
        "auto_mistake_tags": '["chased_price"]',
        "execution_quality_score": 88,
    }
    base.update(overrides)
    entry = JournalEntry(**base)
    return service.create(entry)


def test_legacy_keys_present(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    _insert_closed_trade(service)
    trades = service.list_closed_trades_for_account_guard()
    assert len(trades) == 1
    t = trades[0]
    assert t["result_r"] == -1.0
    assert t["result_pct"] == -0.8
    assert t["closed_at"] == "2026-06-04T14:00:00Z"
    assert t["direction"] == "buy"


def test_dot2_fields_present(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    _insert_closed_trade(service)
    t = service.list_closed_trades_for_account_guard()[0]

    assert t["planned_entry"] == 1.0850
    assert t["actual_entry"] == 1.0860
    assert t["m15_quality"] == "strict"
    assert t["expected_effective_rr"] == 1.75
    assert t["realized_effective_rr"] == 1.2
    assert t["execution_quality_score"] == 88
    assert t["setup_type"] == "pullback"
    assert t["regime"] == "trend_up"
    assert t["session"] == "London"
    assert t["spread_at_entry"] == 0.0002


def test_tags_parsed_as_lists(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    _insert_closed_trade(service)
    t = service.list_closed_trades_for_account_guard()[0]

    assert isinstance(t["manual_mistake_tags"], list)
    assert "closed_too_early" in t["manual_mistake_tags"]
    assert isinstance(t["auto_mistake_tags"], list)
    assert "chased_price" in t["auto_mistake_tags"]


def test_null_fields_return_none(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    _insert_closed_trade(
        service,
        m15_quality=None, execution_quality_score=None,
        expected_effective_rr=None, manual_mistake_tags=None, auto_mistake_tags=None,
        actual_entry=None, planned_sl=None, actual_sl=None, planned_tp=None, actual_tp=None,
        actual_exit=None, setup_type=None, regime=None, session=None, spread_at_entry=None,
        realized_effective_rr=None,
    )
    t = service.list_closed_trades_for_account_guard()[0]
    assert t["m15_quality"] is None
    assert t["execution_quality_score"] is None
    assert t["manual_mistake_tags"] == []
    assert t["auto_mistake_tags"] == []
