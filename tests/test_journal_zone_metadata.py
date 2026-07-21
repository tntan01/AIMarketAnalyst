"""Tests for zone metadata fields in JournalEntry and converters."""

from services.journal_converters import (
    entry_from_row,
    entry_to_record,
    journal_entry_from_analysis,
    journal_entry_from_scanner_row,
    journal_entry_from_mt5_trade,
)


def test_journal_entry_from_analysis_maps_zone_score():
    analysis = {
        "symbol": "EURUSD",
        "timestamp": "2026-01-01T00:00:00Z",
        "scenario_scores": {},
        "scenarios": [
            {
                "type": "buy",
                "entry_zone": [1.0840, 1.0860],
                "stop_loss": 1.0820,
                "take_profit": [1.0900],
                "risk_reward": "1:2",
                "entry_zone_score": 75,
                "entry_zone_source": "smc",
                "sub_zone": "mid",
                "expected_effective_rr": 2.0,
            },
        ],
        "decision_summary": {"action": "ready", "best_scenario": "buy"},
        "trade_permission": {"status": "allowed"},
        "data_quality": {"price_source": "MT5"},
        "market_regime": {"primary": "trend"},
        "macro": {"ai_summary": ""},
    }
    entry = journal_entry_from_analysis(analysis, mode="scanner_detail")
    assert entry.entry_zone_score == 75
    assert entry.entry_zone_source == "smc"
    assert entry.sub_zone == "mid"


def test_journal_entry_from_analysis_no_zone_score():
    analysis = {
        "symbol": "EURUSD",
        "timestamp": "2026-01-01T00:00:00Z",
        "scenario_scores": {},
        "scenarios": [
            {
                "type": "buy",
                "entry_zone": [1.0840, 1.0860],
                "stop_loss": 1.0820,
                "take_profit": [1.0900],
                "risk_reward": "1:2",
                "expected_effective_rr": 2.0,
            },
        ],
        "decision_summary": {"action": "ready", "best_scenario": "buy"},
        "trade_permission": {"status": "allowed"},
        "data_quality": {"price_source": "MT5"},
        "market_regime": {"primary": "trend"},
        "macro": {"ai_summary": ""},
    }
    entry = journal_entry_from_analysis(analysis, mode="scanner_detail")
    assert entry.entry_zone_score is None
    assert entry.entry_zone_source is None
    assert entry.sub_zone is None


def test_zone_metadata_round_trip():
    analysis = {
        "symbol": "EURUSD",
        "timestamp": "2026-01-01T00:00:00Z",
        "scenario_scores": {},
        "scenarios": [
            {
                "type": "buy",
                "entry_zone": [1.0840, 1.0860],
                "stop_loss": 1.0820,
                "take_profit": [1.0900],
                "risk_reward": "1:2",
                "entry_zone_score": 82,
                "entry_zone_source": "smc",
                "sub_zone": "bottom",
                "expected_effective_rr": 2.5,
            },
        ],
        "decision_summary": {"action": "ready", "best_scenario": "buy"},
        "trade_permission": {"status": "allowed"},
        "data_quality": {"price_source": "MT5"},
        "market_regime": {"primary": "trend"},
        "macro": {"ai_summary": ""},
    }
    entry = journal_entry_from_analysis(analysis, mode="scanner_detail")
    record = entry_to_record(entry)
    row = type("Row", (), {"keys": lambda: record.keys(), "__getitem__": lambda self, k: record.get(k)})()
    restored = entry_from_row(row)
    assert restored.entry_zone_score == 82
    assert restored.entry_zone_source == "smc"
    assert restored.sub_zone == "bottom"


def test_mt5_trade_has_none_zone_metadata():
    trade = {
        "symbol": "EURUSD",
        "broker_symbol": "EURUSDm",
        "side": "buy",
        "opened_at": "2026-01-01T00:00:00Z",
        "closed_at": "2026-01-02T00:00:00Z",
        "actual_entry": 1.0850,
        "actual_exit": 1.0900,
        "actual_lot": 0.1,
        "result_amount": 50.0,
    }
    entry = journal_entry_from_mt5_trade(trade)
    assert entry.entry_zone_score is None
    assert entry.entry_zone_source is None
    assert entry.sub_zone is None
