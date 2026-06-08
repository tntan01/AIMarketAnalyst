"""Phase 17.6 — verify journal_entry_from_analysis() populates Đợt 2 fields."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import journal_entry_from_analysis


def _fake_analysis() -> dict:
    return {
        "symbol": "EUR/USD",
        "timestamp": "2026-06-04T12:00:00Z",
        "broker_symbol": "EURUSD",
        "data_quality": {
            "broker_symbol": "EURUSD",
            "price_source": "MT5",
            "spread_points": 12,
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        "market_regime": {"primary": "trend_up"},
        "direction_bias": "buy",
        "scenario_scores": {
            "buy": {"signal_score": 82, "total": 82},
            "sell": {"signal_score": 55, "total": 55},
        },
        "decision_summary": {
            "action": "ready",
            "best_scenario": "buy",
            "best_score": 82,
        },
        "trade_permission": {"status": "allowed", "reason": "ok"},
        "scenarios": [{
            "type": "buy",
            "entry_zone": [1.0840, 1.0860],
            "stop_loss": 1.0800,
            "take_profit": [1.0950, 1.1000],
            "risk_reward": "1:2.0",
            "expected_effective_rr": 1.75,
            "m15_quality": "strict",
            "trigger_type": "h1_bullish_break",
            "position_sizing": {"suggested_lot": 0.1},
        }],
        "execution_quality": {"execution_quality_score": 88},
        "auto_mistake_tags": ["ignored_news"],
        "macro": {"ai_summary": ""},
    }


def test_planned_entry_from_zone():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.planned_entry == 1.0850


def test_planned_sl():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.planned_sl == 1.0800


def test_planned_tp_first():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.planned_tp == 1.0950


def test_setup_type():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.setup_type == "h1_bullish_break"


def test_regime():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.regime == "trend_up"


def test_m15_quality():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.m15_quality == "strict"


def test_expected_effective_rr():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.expected_effective_rr == 1.75


def test_execution_quality_score():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.execution_quality_score == 88


def test_auto_mistake_tags():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.auto_mistake_tags is not None
    assert "ignored_news" in entry.auto_mistake_tags


def test_actual_fields_none():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.actual_entry is None
    assert entry.actual_sl is None
    assert entry.actual_tp is None
    assert entry.actual_exit is None
    assert entry.realized_effective_rr is None


def test_legacy_fields_still_present():
    entry = journal_entry_from_analysis(_fake_analysis(), mode="single_analysis")
    assert entry.symbol == "EUR/USD"
    assert entry.buy_score == 82
    assert entry.trade_permission == "allowed"
    assert entry.risk_reward == "1:2.0"
