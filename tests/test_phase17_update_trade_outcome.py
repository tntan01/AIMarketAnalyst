"""Phase 17.9 — test update_trade_outcome() whitelist and field update."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService, JournalEntry


def _create_entry(service: JournalService) -> int:
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
    )
    return service.create(entry)


def test_update_result_r_and_pct(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = _create_entry(service)

    service.update_trade_outcome(eid, {
        "result_r": 1.5,
        "result_pct": 1.2,
        "closed_at": "2026-06-04T15:00:00Z",
        "exit_reason": "take_profit",
        "actual_exit": 1.0950,
    })

    fetched = service.get_entry(eid)
    assert fetched is not None
    assert fetched.result_r == 1.5
    assert fetched.result_pct == 1.2
    assert fetched.closed_at == "2026-06-04T15:00:00Z"
    assert fetched.exit_reason == "take_profit"
    assert fetched.actual_exit == 1.0950


def test_update_mistake_tags(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = _create_entry(service)

    service.update_trade_outcome(eid, {
        "manual_mistake_tags": ["closed_too_early", "oversized"],
        "auto_mistake_tags": ["chased_price"],
        "execution_quality_score": 80,
    })

    fetched = service.get_entry(eid)
    assert fetched is not None
    assert "closed_too_early" in (fetched.manual_mistake_tags or "")
    assert "oversized" in (fetched.manual_mistake_tags or "")
    assert "chased_price" in (fetched.auto_mistake_tags or "")
    assert fetched.execution_quality_score == 80


def test_whitelist_blocks_dangerous_fields(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = _create_entry(service)

    service.update_trade_outcome(eid, {
        "symbol": "HACKED",
        "analysis_json": "MALICIOUS",
        "timestamp_utc": "2099-01-01",
        "unknown_field": 999,
        "result_r": 2.0,  # this IS allowed
    })

    fetched = service.get_entry(eid)
    assert fetched is not None
    assert fetched.symbol == "EUR/USD"  # unchanged
    assert fetched.result_r == 2.0  # allowed field updated


def test_empty_updates_no_crash(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = _create_entry(service)
    service.update_trade_outcome(eid, {})
    service.update_trade_outcome(eid, None)  # type: ignore[arg-type]
    # No crash, entry still exists
    assert service.get_entry(eid) is not None


def test_note_update(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = _create_entry(service)
    service.update_trade_outcome(eid, {"note": "updated note text"})
    fetched = service.get_entry(eid)
    assert fetched.note == "updated note text"
