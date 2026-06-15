from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest
import sqlite3

from services.journal_service import (
    JournalEntry,
    JournalFilter,
    JournalService,
    journal_entry_from_analysis,
    journal_entry_from_scanner_row,
    normalize_tag_list,
    normalize_trade_status,
    calculate_trade_outcome,
)

def test_migration_and_basic_crud(temp_db_path):
    # Initialize service and verify database migration
    service = JournalService(db_path=temp_db_path)
    
    # Verify tables exist
    with sqlite3.connect(temp_db_path) as conn:
        conn.row_factory = sqlite3.Row
        tables = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        assert "schema_migrations" in tables
        assert "journal_entries" in tables
        
        # Verify schema_migrations has version rows
        versions = [row[0] for row in conn.execute("SELECT version FROM schema_migrations").fetchall()]
        assert len(versions) > 0

    # Create dummy journal entry
    entry = JournalEntry(
        id=None,
        timestamp_utc="2026-06-15T15:00:00Z",
        saved_at_utc="2026-06-15T15:00:01Z",
        symbol="EUR/USD",
        broker_symbol="EURUSDm",
        mode="scanner_detail",
        data_source="MT5",
        market_regime="trending_up",
        decision="ready",
        direction_bias="buy",
        trade_permission="allowed",
        buy_score=85,
        sell_score=20,
        selected_scenario="buy",
        entry_zone="[1.0850, 1.0860]",
        stop_loss="1.0800",
        take_profit="[1.1000]",
        risk_reward="3.0",
        suggested_lot=0.1,
        ai_commentary="Strong upward momentum.",
        analysis_json="{}",
        user_action="",
        result="",
        note="Initial test note",
    )
    
    entry_id = service.create(entry)
    assert entry_id > 0
    
    # Retrieve entry
    retrieved = service.get_entry(entry_id)
    assert retrieved is not None
    assert retrieved.symbol == "EUR/USD"
    assert retrieved.note == "Initial test note"
    assert retrieved.trade_status == "planned"
    
    # List entries
    entries = service.list_entries()
    assert len(entries) == 1
    assert entries[0].id == entry_id
    
    # Filter entries
    filters = JournalFilter(symbol="EUR/USD")
    filtered = service.list_entries(filters)
    assert len(filtered) == 1
    
    filtered_none = service.list_entries(JournalFilter(symbol="GBP/USD"))
    assert len(filtered_none) == 0
    
    # Update note
    service.update_note(entry_id, "Updated test note")
    retrieved = service.get_entry(entry_id)
    assert retrieved.note == "Updated test note"
    
    # Delete entry
    service.delete_entry(entry_id)
    assert service.get_entry(entry_id) is None

def test_trade_lifecycle_outcomes(temp_db_path):
    service = JournalService(db_path=temp_db_path)
    
    entry = JournalEntry(
        id=None,
        timestamp_utc="2026-06-15T15:00:00Z",
        saved_at_utc="2026-06-15T15:00:01Z",
        symbol="GBP/USD",
        broker_symbol="GBPUSD",
        mode="scanner_detail",
        data_source="MT5",
        market_regime="ranging",
        decision="ready",
        direction_bias="buy",
        trade_permission="allowed",
        buy_score=75,
        sell_score=30,
        selected_scenario="buy",
        entry_zone="",
        stop_loss="",
        take_profit="",
        risk_reward="",
        suggested_lot=None,
        ai_commentary="",
        analysis_json="{}",
        # We set planned values
        planned_entry=1.2500,
        planned_sl=1.2400,
        planned_tp=1.2700,
        planned_lot=0.5,
    )
    
    entry_id = service.create(entry)
    
    # Update to 'opened' status
    res = service.update_lifecycle(entry_id, {
        "actual_entry": 1.2510,
        "actual_sl": 1.2410,
        "actual_tp": 1.2710,
        "actual_lot": 0.5,
        "opened_at": "2026-06-15T15:10:00Z",
    })
    
    updated = res["entry"]
    assert updated["trade_status"] == "opened"
    assert updated["actual_entry"] == 1.2510
    assert updated["result_r"] is None  # Trade is still open, so no outcome
    
    # Update to 'closed' status with profit (win)
    res_close = service.update_lifecycle(entry_id, {
        "actual_exit": 1.2710,
        "closed_at": "2026-06-15T16:00:00Z",
        "result_amount": 150.0,
        "exit_reason": "TP hit",
    })
    
    closed = res_close["entry"]
    assert closed["trade_status"] == "closed"
    assert closed["result"] == "win"
    # Risk = 1.2510 - 1.2410 = 0.0100
    # Gain = 1.2710 - 1.2510 = 0.0200
    # R-multiple = 2.0
    assert closed["result_r"] == 2.0
    assert closed["result_pct"] == pytest.approx(1.599, abs=1e-3)
    
    # Verify symbols and stats
    assert "GBP/USD" in service.symbols()
    stats = service.stats()
    assert stats["total"] == 1
    
    summary = service.performance_summary()
    assert summary["summary"]["win_rate"] == 100.0
    assert summary["summary"]["profit_factor"] is not None

def test_helpers_and_normalisation():
    # Tag normalization
    assert normalize_tag_list(None) == []
    assert normalize_tag_list('["FOMC", "FOMC", "chased"]') == ["fomc", "chased"]
    assert normalize_tag_list("FOMC, chased, FOMC") == ["fomc", "chased"]
    assert normalize_tag_list(["FOMC", "Chased"]) == ["fomc", "chased"]
    
    # Trade status normalization
    assert normalize_trade_status("plan") == "planned"
    assert normalize_trade_status("open") == "opened"
    assert normalize_trade_status("close") == "closed"
    assert normalize_trade_status("cancel") == "cancelled"
    assert normalize_trade_status("missed") == "missed"
    
    # Calculate outcome logic
    trade_buy = {
        "selected_scenario": "buy",
        "actual_entry": 1.0000,
        "actual_sl": 0.9900,
        "actual_exit": 1.0200,
    }
    outcome = calculate_trade_outcome(trade_buy)
    assert outcome["result_r"] == 2.0
    assert outcome["result"] == "win"
    
    trade_sell = {
        "selected_scenario": "sell",
        "actual_entry": 1.0000,
        "actual_sl": 1.0100,
        "actual_exit": 1.0200,
    }
    outcome_sell = calculate_trade_outcome(trade_sell)
    assert outcome_sell["result_r"] == -2.0
    assert outcome_sell["result"] == "loss"
