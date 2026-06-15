from __future__ import annotations

import pytest
from core.journal_feedback_engine import build_journal_feedback
from core.reason_codes import (
    STAT_EDGE_NEGATIVE,
    STAT_EDGE_NOT_ENOUGH_DATA,
    STAT_EDGE_POSITIVE,
    FINAL_SCORE_EVIDENCE_NEGATIVE,
    FINAL_SCORE_EXECUTION_WEAK,
    EXECUTION_MANUAL_PENALTY,
)

def test_insufficient_data():
    # Less than 8 trades
    trades = [
        {"symbol": "EUR/USD", "direction": "buy", "result_r": 1.5, "closed_at": "2026-06-15T00:00:00Z"},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z"},
    ]
    fb = build_journal_feedback(trades, symbol="EUR/USD", direction="buy")
    assert fb["sample_size"] == 2
    assert STAT_EDGE_NOT_ENOUGH_DATA in fb["warning_codes"]
    assert fb["decision_cap"] is None

def test_positive_expectancy():
    # 8 trades, positive expectancy
    trades = [
        {"symbol": "EUR/USD", "direction": "buy", "result_r": 2.0, "closed_at": "2026-06-15T00:00:00Z"},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z"},
    ] * 4 # 8 trades total: 4 wins of 2R, 4 losses of -1R = +4R total, expectancy = 0.5R
    fb = build_journal_feedback(trades, symbol="EUR/USD", direction="buy")
    assert fb["sample_size"] == 8
    assert fb["expectancy_r"] == 0.5
    assert STAT_EDGE_POSITIVE in fb["warning_codes"]
    assert fb["decision_cap"] is None

def test_negative_expectancy_warning():
    # 8 trades, negative expectancy
    trades = [
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z"},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": 0.5, "closed_at": "2026-06-15T00:00:00Z"},
    ] * 4 # 8 trades total: 4 losses of -1R, 4 wins of 0.5R = -2R total, expectancy = -0.25R
    fb = build_journal_feedback(trades, symbol="EUR/USD", direction="buy")
    assert fb["sample_size"] == 8
    assert fb["expectancy_r"] == -0.25
    assert STAT_EDGE_NEGATIVE in fb["warning_codes"]
    assert FINAL_SCORE_EVIDENCE_NEGATIVE in fb["warning_codes"]
    assert fb["decision_cap"] is None # Needs at least 12 sample size to cap decision

def test_negative_expectancy_watch_only():
    # 12 trades, negative expectancy
    trades = [
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z"},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": 0.5, "closed_at": "2026-06-15T00:00:00Z"},
    ] * 6 # 12 trades total: 6 losses of -1R, 6 wins of 0.5R = -3R total, expectancy = -0.25R
    fb = build_journal_feedback(trades, symbol="EUR/USD", direction="buy")
    assert fb["sample_size"] == 12
    assert fb["decision_cap"] == "WATCH_ONLY"

def test_negative_expectancy_blocked():
    # 25 trades, expectancy <= -0.45, win rate < 35%
    trades = [
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z"},
    ] * 20 + [
        {"symbol": "EUR/USD", "direction": "buy", "result_r": 1.0, "closed_at": "2026-06-15T00:00:00Z"},
    ] * 5 # 25 trades total: 20 losses of -1R, 5 wins of 1R = -15R total, expectancy = -0.6R, WR = 20%
    fb = build_journal_feedback(trades, symbol="EUR/USD", direction="buy")
    assert fb["sample_size"] == 25
    assert fb["win_rate"] == 20.0
    assert fb["expectancy_r"] == -0.6
    assert fb["decision_cap"] == "TRADE_BLOCKED"

def test_execution_quality_penalty():
    # 5 trades with weak average quality (< 65)
    trades = [
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z", "execution_quality_score": 50},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z", "execution_quality_score": 60},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z", "execution_quality_score": 55},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z", "execution_quality_score": 65},
        {"symbol": "EUR/USD", "direction": "buy", "result_r": -1.0, "closed_at": "2026-06-15T00:00:00Z", "execution_quality_score": 62},
    ] # 5 trades, avg quality = 58.4
    fb = build_journal_feedback(trades, symbol="EUR/USD", direction="buy")
    assert fb["average_execution_quality"] == 58.4
    assert FINAL_SCORE_EXECUTION_WEAK in fb["warning_codes"]
    assert EXECUTION_MANUAL_PENALTY in fb["warning_codes"]
    assert fb["decision_cap"] == "WAITING_CONFIRMATION"
