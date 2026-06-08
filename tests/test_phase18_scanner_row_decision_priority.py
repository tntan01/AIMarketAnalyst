"""Phase 18 — test scanner_row_from_analysis passes decision_engine correctly.

Verify that core/scanner.scanner_row_from_analysis() extracts
decision_engine.{decision, legacy_action} and the resulting row flows
through enrich_scanner_row_with_ranking to produce the correct
scanner_group, even when legacy scanner_action would be "skip".
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import scanner_row_from_analysis
from core.scanner_ranking_engine import (
    READY_NOW,
    WATCH_ZONE,
    WAITING_CONFIRMATION,
    BLOCKED,
)

# ---------------------------------------------------------------------------
# Shared fixture: realistic analysis_result with WATCH_ONLY decision
# ---------------------------------------------------------------------------


def _make_watch_only_result():
    """Return an analysis_result where decision_engine says WATCH_ONLY
    but legacy classify_scanner_action would produce 'skip' (best_score < 60)."""
    return {
        "symbol": "XAU/USD",
        "data_quality": {"broker_symbol": "XAUUSD"},
        "technical": {"price": 2300.0, "atr_h4": 5.0},
        "market_regime": {"primary": "range"},
        "direction_bias": {"best_side": "buy", "score_gap": 14},
        "trade_permission": {"status": "caution", "reason": "Expected RR thap"},
        "scenario_scores": {
            "buy": {
                "signal_score": 57,
                "total": 57,
                "macro_alignment": 15,
                "macro_confidence": 1.0,
                "smc_quality": 8,
            },
            "sell": {
                "signal_score": 43,
                "total": 43,
                "macro_alignment": 15,
                "macro_confidence": 1.0,
                "smc_quality": 4,
            },
        },
        "decision_summary": {
            "action": "skip",
            "best_scenario": "buy",
            "best_score": 57,
            "score_gap": 14,
        },
        "decision_engine": {
            "decision": "WATCH_ONLY",
            "legacy_action": "watch",
        },
        "final_score": 62,
        "scenarios": [
            {
                "type": "buy",
                "entry_status": "waiting_confirmation",
                "entry_zone": [2298.0, 2302.0],
                "risk_reward": "1:1.7",
                "expected_effective_rr": 0.8,
                "ready_to_trade": False,
                "price_in_entry_zone": True,
                "h1_confirmation": False,
                "position_sizing": {"suggested_lot": 0.1},
            }
        ],
        "macro": {"ai_summary": ""},
    }


# ---------------------------------------------------------------------------
# Test case 1 — WATCH_ONLY decision + legacy skip → watch_zone
# ---------------------------------------------------------------------------


def test_scanner_row_watch_only_skip_becomes_watch_zone():
    """When decision_engine says WATCH_ONLY but legacy best_score < 60
    produces scanner_action='skip', the row must be watch_zone, not blocked."""
    analysis_result = _make_watch_only_result()
    row = scanner_row_from_analysis(analysis_result, broker_symbol="XAUUSD")

    # Decision engine fields passed through correctly
    assert row["scanner_decision"] == "WATCH_ONLY", (
        f"scanner_decision should be WATCH_ONLY, got {row['scanner_decision']}"
    )
    assert row["legacy_action"] == "watch", (
        f"legacy_action should be 'watch', got {row['legacy_action']}"
    )

    # Legacy scanner_action is 'skip' (best_score=57 < 60)
    assert row["scanner_action"] == "skip", (
        f"scanner_action should be 'skip' (best_score=57 < 60), got {row['scanner_action']}"
    )

    # Core assertion: scanner_group must be watch_zone, NOT blocked
    assert row["scanner_group"] == WATCH_ZONE, (
        f"Expected WATCH_ZONE but got {row['scanner_group']}. "
        f"WATCH_ONLY decision must win over legacy scanner_action='skip'."
    )
    assert row["opportunity_score"] > 20, (
        f"Expected opportunity_score > 20 but got {row['opportunity_score']}. "
        f"Non-blocked rows must not be capped."
    )
    assert row["trade_permission"] == "caution", (
        f"trade_permission should be 'caution', got {row['trade_permission']}"
    )


# ---------------------------------------------------------------------------
# Test case 2 — WAITING_CONFIRMATION decision + legacy skip → waiting_confirmation
# ---------------------------------------------------------------------------


def test_scanner_row_waiting_confirmation_skip_becomes_waiting():
    """When decision_engine says WAITING_CONFIRMATION but legacy
    scanner_action='skip', the row must be waiting_confirmation."""
    analysis_result = _make_watch_only_result()
    analysis_result["decision_engine"] = {
        "decision": "WAITING_CONFIRMATION",
        "legacy_action": "wait_for_confirmation",
    }
    # Keep best_score < 60 so legacy action is still 'skip'
    row = scanner_row_from_analysis(analysis_result, broker_symbol="XAUUSD")

    assert row["scanner_decision"] == "WAITING_CONFIRMATION", (
        f"scanner_decision should be WAITING_CONFIRMATION, got {row['scanner_decision']}"
    )
    assert row["scanner_group"] == WAITING_CONFIRMATION, (
        f"Expected WAITING_CONFIRMATION but got {row['scanner_group']}. "
        f"WAITING_CONFIRMATION decision must win over legacy scanner_action='skip'."
    )
    assert row["opportunity_score"] > 20, (
        f"Expected opportunity_score > 20 but got {row['opportunity_score']}"
    )


# ---------------------------------------------------------------------------
# Test case 3 — TRADE_BLOCKED + permission blocked → blocked
# ---------------------------------------------------------------------------


def test_scanner_row_trade_blocked_stays_blocked():
    """When decision_engine says TRADE_BLOCKED and trade_permission is blocked,
    the row must be blocked with capped opportunity_score."""
    analysis_result = _make_watch_only_result()
    analysis_result["decision_engine"] = {
        "decision": "TRADE_BLOCKED",
        "legacy_action": "stand_aside",
    }
    analysis_result["trade_permission"] = {
        "status": "blocked",
        "reason": "Spread abnormal",
    }

    row = scanner_row_from_analysis(analysis_result, broker_symbol="XAUUSD")

    assert row["scanner_decision"] == "TRADE_BLOCKED", (
        f"scanner_decision should be TRADE_BLOCKED, got {row['scanner_decision']}"
    )
    assert row["scanner_group"] == BLOCKED, (
        f"Expected BLOCKED but got {row['scanner_group']}"
    )
    assert row["opportunity_score"] <= 20, (
        f"Expected opportunity_score <= 20 but got {row['opportunity_score']}"
    )


# ---------------------------------------------------------------------------
# Test case 4 — READY_TO_TRADE not damaged by any legacy action
# ---------------------------------------------------------------------------


def test_scanner_row_ready_to_trade_stays_ready():
    """When decision_engine says READY_TO_TRADE, row must be ready_now
    regardless of legacy action."""
    analysis_result = _make_watch_only_result()
    # Bump scores so classify_scanner_action produces something other than skip
    analysis_result["scenario_scores"]["buy"]["signal_score"] = 84
    analysis_result["scenario_scores"]["buy"]["total"] = 84
    analysis_result["decision_summary"]["best_score"] = 84
    analysis_result["final_score"] = 84
    analysis_result["decision_engine"] = {
        "decision": "READY_TO_TRADE",
        "legacy_action": "ready",
    }
    analysis_result["trade_permission"] = {"status": "allowed", "reason": ""}
    analysis_result["scenarios"][0]["entry_status"] = "confirmed_entry"
    analysis_result["scenarios"][0]["ready_to_trade"] = True
    analysis_result["scenarios"][0]["risk_reward"] = "1:2.0"
    analysis_result["scenarios"][0]["expected_effective_rr"] = 1.8

    row = scanner_row_from_analysis(analysis_result, broker_symbol="XAUUSD")

    assert row["scanner_decision"] == "READY_TO_TRADE", (
        f"scanner_decision should be READY_TO_TRADE, got {row['scanner_decision']}"
    )
    assert row["scanner_group"] == READY_NOW, (
        f"Expected READY_NOW but got {row['scanner_group']}"
    )
    assert row["opportunity_score"] > row["final_score"], (
        f"Expected opportunity_score ({row['opportunity_score']}) "
        f"> final_score ({row['final_score']}) due to bonuses"
    )
