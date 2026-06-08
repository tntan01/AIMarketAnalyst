"""Phase 15.7 — test scanner row ranking metadata from scanner_row_from_analysis()."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import scanner_row_from_analysis, blocked_scanner_row
from core.scanner_ranking_engine import READY_NOW, BLOCKED


def _make_result(
    final_score: int = 82,
    best_side: str = "buy",
    entry_status: str = "confirmed_entry",
    decision: str = "READY_TO_TRADE",
    legacy_action: str = "ready",
    score_gap: int = 18,
    ready_to_trade: bool = True,
    m15_quality: str = "strict",
    expected_effective_rr: float = 1.8,
) -> dict:
    return {
        "symbol": "EUR/USD",
        "data_quality": {"broker_symbol": "EURUSDm"},
        "market_regime": {"primary": "trend_up"},
        "direction_bias": "buy",
        "trade_permission": {"status": "allowed", "reason": "ok"},
        "scenario_scores": {
            "buy": {"signal_score": 82, "total": 82, "macro_alignment": 18, "macro_confidence": 0.8},
            "sell": {"signal_score": 55, "total": 55, "macro_alignment": 10, "macro_confidence": 0.8},
        },
        "final_score": final_score,
        "decision_engine": {"decision": decision, "legacy_action": legacy_action},
        "decision_summary": {"best_score": final_score, "best_scenario": best_side, "score_gap": score_gap},
        "scenarios": [
            {
                "type": best_side,
                "entry_status": entry_status,
                "ready_to_trade": ready_to_trade,
                "m15_quality": m15_quality,
                "expected_effective_rr": expected_effective_rr,
                "entry_zone": [1.10, 1.12],
                "risk_reward": "1:2.0",
                "stop_loss": 1.09,
                "take_profit": [1.15],
                "price_in_entry_zone": True,
                "h1_confirmation": True,
            }
        ],
        "technical": {"price": 1.11, "atr_h4": 0.005},
    }


def test_row_has_new_metadata():
    result = _make_result()
    row = scanner_row_from_analysis(result)

    assert row["final_score"] == 82
    assert row["scanner_decision"] == "READY_TO_TRADE"
    assert row["legacy_action"] == "ready"
    assert row["score_gap"] == 18
    assert row["m15_quality"] == "strict"
    assert row["expected_effective_rr"] == 1.8


def test_row_has_opportunity_score():
    result = _make_result()
    row = scanner_row_from_analysis(result)

    assert "opportunity_score" in row
    assert row["opportunity_score"] > 80
    assert row["scanner_group"] == READY_NOW
    assert "ranking_reason_codes" in row
    assert "ranking_score_breakdown" in row


def test_row_backward_compatible():
    """Legacy fields still exist."""
    result = _make_result()
    row = scanner_row_from_analysis(result)

    assert "best_score" in row
    assert "scanner_action" in row
    assert "buy_score" in row
    assert "sell_score" in row
    assert "risk_reward" in row
    assert "analysis_result" in row


def test_blocked_row():
    row = blocked_scanner_row("EUR/USD", "MT5 not connected")
    assert row["final_score"] == 0
    assert row["scanner_decision"] == "TRADE_BLOCKED"
    assert row["scanner_group"] == BLOCKED
    assert row["opportunity_score"] <= 20
