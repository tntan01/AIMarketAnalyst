"""Phase 15.8 — test new sort_scanner_rows() with scanner_group + opportunity_score."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import sort_scanner_rows
from core.scanner_ranking_engine import READY_NOW, WAITING_CONFIRMATION, WATCH_ZONE, BLOCKED


# ---------------------------------------------------------------------------
# Group-based + opportunity sort
# ---------------------------------------------------------------------------


def test_sort_groups_blocked_last():
    rows = [
        {"symbol": "A", "scanner_group": BLOCKED,       "opportunity_score": 20, "final_score": 95, "risk_reward": "1:3.0"},
        {"symbol": "B", "scanner_group": WATCH_ZONE,             "opportunity_score": 75, "final_score": 70, "risk_reward": "1:1.5"},
        {"symbol": "C", "scanner_group": WAITING_CONFIRMATION, "opportunity_score": 82, "final_score": 78, "risk_reward": "1:2.0"},
        {"symbol": "D", "scanner_group": READY_NOW,             "opportunity_score": 85, "final_score": 80, "risk_reward": "1:1.8"},
        {"symbol": "E", "scanner_group": READY_NOW,             "opportunity_score": 90, "final_score": 75, "risk_reward": "1:2.0"},
    ]
    sorted_rows = sort_scanner_rows(rows)

    assert sorted_rows[0]["symbol"] == "E"  # ready_now, highest opportunity
    assert sorted_rows[1]["symbol"] == "D"  # ready_now, second
    assert sorted_rows[2]["symbol"] == "C"  # waiting
    assert sorted_rows[3]["symbol"] == "B"  # watch
    assert sorted_rows[4]["symbol"] == "A"  # blocked — last despite high final_score


def test_sort_rank_assigned():
    rows = [
        {"symbol": "X", "scanner_group": READY_NOW, "opportunity_score": 85, "final_score": 80},
        {"symbol": "Y", "scanner_group": READY_NOW, "opportunity_score": 90, "final_score": 75},
    ]
    sorted_rows = sort_scanner_rows(rows)
    assert sorted_rows[0]["rank"] == 1
    assert sorted_rows[1]["rank"] == 2


# ---------------------------------------------------------------------------
# Fallback: old rows without new fields
# ---------------------------------------------------------------------------


def test_sort_legacy_rows_no_crash():
    """Old rows with only scanner_action/best_score still sort without crashing."""
    rows = [
        {"symbol": "L1", "scanner_action": "ready", "trade_permission": "allowed", "best_score": 85, "risk_reward": "1:2.0"},
        {"symbol": "L2", "scanner_action": "watch", "trade_permission": "caution", "best_score": 70, "risk_reward": "1:1.5"},
        {"symbol": "L3", "scanner_action": "skip",  "trade_permission": "blocked", "best_score": 50, "risk_reward": None},
    ]
    sorted_rows = sort_scanner_rows(rows)
    assert len(sorted_rows) == 3
    assert sorted_rows[0]["rank"] == 1
    assert sorted_rows[2]["rank"] == 3


def test_sort_with_missing_opportunity():
    """Rows missing opportunity_score still sort (zero is used)."""
    rows = [
        {"symbol": "R", "scanner_group": READY_NOW, "opportunity_score": 80, "final_score": 80},
        {"symbol": "S", "scanner_group": READY_NOW, "final_score": 85},  # no opportunity_score
    ]
    sorted_rows = sort_scanner_rows(rows)
    # R has opportunity=80 > 0, so should be first
    assert sorted_rows[0]["symbol"] == "R"
