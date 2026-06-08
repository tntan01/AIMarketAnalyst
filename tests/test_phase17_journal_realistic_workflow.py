"""Phase 17.12 — realistic journal workflow: create → update → list → apply."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.journal_service import JournalService


def _fake_analysis() -> dict:
    return {
        "symbol": "EUR/USD",
        "timestamp": "2026-06-04T10:00:00Z",
        "broker_symbol": "EURUSD",
        "data_quality": {
            "broker_symbol": "EURUSD",
            "price_source": "MT5",
            "spread_points": 12,
            "spread_status": "normal",
            "terminal_connected": True,
            "broker_logged_in": True,
        },
        "market_regime": {"primary": "trend_up"},
        "direction_bias": "buy",
        "scenario_scores": {
            "buy": {"signal_score": 82, "total": 82},
            "sell": {"signal_score": 55, "total": 55},
        },
        "final_score": 77,
        "final_score_detail": {"final_score": 77},
        "decision_engine": {"decision": "READY_TO_TRADE", "legacy_action": "ready"},
        "decision_summary": {
            "action": "ready",
            "best_scenario": "buy",
            "best_score": 82,
            "score_gap": 27,
        },
        "trade_permission": {"status": "allowed", "reason": "ok"},
        "trade_gate": {"allowed": True, "decision_cap": None},
        "scenarios": [{
            "type": "buy",
            "entry_zone": [1.0840, 1.0860],
            "stop_loss": 1.0800,
            "take_profit": [1.0950, 1.1000],
            "risk_reward": "1:2.0",
            "expected_effective_rr": 1.75,
            "m15_quality": "strict",
            "trigger_type": "h1_bullish_break",
            "entry_status": "confirmed_entry",
            "ready_to_trade": True,
            "position_sizing": {"suggested_lot": 0.10},
        }],
        "execution_quality": {"execution_quality_score": 100},
        "macro": {"ai_summary": ""},
    }


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


def test_workflow_create_from_analysis(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = service.create_from_analysis(_fake_analysis(), mode="single_analysis")
    assert eid > 0

    entry = service.get_entry(eid)
    assert entry is not None
    assert entry.symbol == "EUR/USD"
    # Phase 17 Đợt 2 fields from analysis
    assert entry.planned_entry == 1.0850
    assert entry.planned_sl == 1.0800
    assert entry.planned_tp == 1.0950
    assert entry.m15_quality == "strict"
    assert entry.expected_effective_rr == 1.75
    assert entry.setup_type == "h1_bullish_break"
    assert entry.regime == "trend_up"
    assert entry.execution_quality_score == 100


def test_workflow_update_outcome(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = service.create_from_analysis(_fake_analysis(), mode="single_analysis")

    service.update_trade_outcome(eid, {
        "actual_entry": 1.0865,
        "actual_sl": 1.0790,
        "actual_exit": 1.0920,
        "result_r": 1.2,
        "result_pct": 1.0,
        "closed_at": "2026-06-04T12:00:00Z",
        "exit_reason": "manual_close",
        "auto_mistake_tags": ["closed_too_early"],
        "execution_quality_score": 80,
    })

    entry = service.get_entry(eid)
    assert entry.actual_entry == 1.0865
    assert entry.actual_sl == 1.0790
    assert entry.actual_exit == 1.0920
    assert entry.result_r == 1.2
    assert entry.result_pct == 1.0
    assert entry.closed_at == "2026-06-04T12:00:00Z"
    assert entry.exit_reason == "manual_close"
    assert "closed_too_early" in (entry.auto_mistake_tags or "")
    assert entry.execution_quality_score == 80


def test_workflow_list_closed_trades(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = service.create_from_analysis(_fake_analysis(), mode="single_analysis")
    service.update_trade_outcome(eid, {
        "result_r": 1.2, "result_pct": 1.0,
        "closed_at": "2026-06-04T12:00:00Z",
        "actual_entry": 1.0865, "auto_mistake_tags": ["closed_too_early"],
        "execution_quality_score": 80,
    })

    trades = service.list_closed_trades_for_account_guard()
    assert len(trades) == 1
    t = trades[0]
    assert t["result_r"] == 1.2
    assert t["actual_entry"] == 1.0865
    assert isinstance(t["auto_mistake_tags"], list)
    assert "closed_too_early" in t["auto_mistake_tags"]
    assert t["execution_quality_score"] == 80
    assert t["direction"] == "buy"


def test_workflow_apply_execution_analysis(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    eid = service.create_from_analysis(_fake_analysis(), mode="single_analysis")
    service.update_trade_outcome(eid, {
        "result_r": 0.5, "result_pct": 0.4,
        "closed_at": "2026-06-04T14:00:00Z",
        "actual_lot": 0.15, "planned_lot": 0.10,
    })

    result = service.apply_execution_analysis_to_entry(eid)
    assert result is not None
    assert "detection" in result
    assert "execution_quality" in result


def test_workflow_stats_no_crash(tmp_path):
    service = JournalService(db_path=tmp_path / "test_phase17.db")
    service.create_from_analysis(_fake_analysis(), mode="single_analysis")
    stats = service.stats()
    assert isinstance(stats, dict)
    assert "ready" in stats or "watch" in stats
