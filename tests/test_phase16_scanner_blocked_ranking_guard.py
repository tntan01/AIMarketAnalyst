"""Phase 16.9 — verify blocked scanner rows never outrank ready/waiting/watch rows."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import sort_scanner_rows, scanner_summary, ai_targets
from core.scanner_ranking_engine import READY_NOW, WAITING_CONFIRMATION, WATCH_ZONE, BLOCKED


# ---------------------------------------------------------------------------
# Main test: blocked row has high final_score but stays last
# ---------------------------------------------------------------------------


def test_blocked_high_score_ranks_last():
    rows = [
        {
            "symbol": "XAU/USD", "final_score": 98, "best_score": 98,
            "opportunity_score": 20, "scanner_group": BLOCKED,
            "scanner_decision": "TRADE_BLOCKED", "trade_permission": "blocked",
            "risk_reward": "1:3.0",
        },
        {
            "symbol": "EUR/USD", "final_score": 82, "best_score": 82,
            "opportunity_score": 88, "scanner_group": READY_NOW,
            "scanner_decision": "READY_TO_TRADE", "trade_permission": "allowed",
            "risk_reward": "1:2.0",
        },
        {
            "symbol": "GBP/JPY", "final_score": 90, "best_score": 90,
            "opportunity_score": 86, "scanner_group": WAITING_CONFIRMATION,
            "scanner_decision": "WAITING_CONFIRMATION", "trade_permission": "allowed",
            "risk_reward": "1:2.5",
        },
        {
            "symbol": "USD/JPY", "final_score": 75, "best_score": 75,
            "opportunity_score": 78, "scanner_group": WATCH_ZONE,
            "scanner_decision": "WATCH_ONLY", "trade_permission": "allowed",
            "risk_reward": "1:1.5",
        },
    ]

    sorted_rows = sort_scanner_rows(rows)

    # Ready first
    assert sorted_rows[0]["symbol"] == "EUR/USD"
    assert sorted_rows[0]["rank"] == 1

    # Waiting second
    assert sorted_rows[1]["symbol"] == "GBP/JPY"

    # Watch third
    assert sorted_rows[2]["symbol"] == "USD/JPY"

    # Blocked last despite final_score=98
    assert sorted_rows[3]["symbol"] == "XAU/USD"
    assert sorted_rows[3]["rank"] == 4


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def test_summary_blocked_count():
    rows = [
        {"symbol": "A", "scanner_group": READY_NOW, "opportunity_score": 85},
        {"symbol": "B", "scanner_group": BLOCKED, "opportunity_score": 20},
    ]
    summary = scanner_summary(rows)
    assert summary["ready_now_count"] == 1
    assert summary["blocked_count"] == 1


# ---------------------------------------------------------------------------
# AI targets exclude blocked
# ---------------------------------------------------------------------------


def test_ai_targets_excludes_blocked():
    rows = [
        {"symbol": "BLK", "scanner_group": BLOCKED, "opportunity_score": 20, "final_score": 98, "trade_permission": "blocked"},
        {"symbol": "RDY", "scanner_group": READY_NOW, "opportunity_score": 85, "final_score": 82, "trade_permission": "allowed"},
        {"symbol": "WTC", "scanner_group": WAITING_CONFIRMATION, "opportunity_score": 80, "final_score": 78, "trade_permission": "allowed"},
    ]
    targets = ai_targets(rows, limit=3)
    symbols = [t["symbol"] for t in targets]
    assert "BLK" not in symbols
    assert len(targets) <= 3


# ---------------------------------------------------------------------------
# Legacy fallback
# ---------------------------------------------------------------------------


def test_legacy_rows_no_crash():
    """Old-style rows without scanner_group still sort safely."""
    rows = [
        {"symbol": "L1", "scanner_action": "ready", "trade_permission": "allowed", "best_score": 85, "risk_reward": "1:2.0"},
        {"symbol": "L2", "scanner_action": "watch", "trade_permission": "allowed", "best_score": 70, "risk_reward": "1:1.5"},
        {"symbol": "L3", "scanner_action": "skip", "trade_permission": "blocked", "best_score": 90, "risk_reward": None},
    ]
    sorted_rows = sort_scanner_rows(rows)
    assert len(sorted_rows) == 3
    assert sorted_rows[0]["rank"] == 1
    assert sorted_rows[2]["rank"] == 3
    # blocked should be last even in legacy mode
    assert sorted_rows[2]["symbol"] == "L3"
