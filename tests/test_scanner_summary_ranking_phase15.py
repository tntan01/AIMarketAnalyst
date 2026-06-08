"""Phase 15.9 — test updated scanner_summary() with group counts."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import scanner_summary
from core.scanner_ranking_engine import READY_NOW, WAITING_CONFIRMATION, WATCH_ZONE, BLOCKED


def test_summary_new_group_counts():
    rows = [
        {"scanner_action": "ready", "scanner_group": READY_NOW, "opportunity_score": 90},
        {"scanner_action": "ready", "scanner_group": READY_NOW, "opportunity_score": 85},
        {"scanner_action": "wait",  "scanner_group": WAITING_CONFIRMATION, "opportunity_score": 78},
        {"scanner_action": "watch", "scanner_group": WATCH_ZONE, "opportunity_score": 65},
        {"scanner_action": "skip",  "scanner_group": BLOCKED, "opportunity_score": 15},
    ]
    summary = scanner_summary(rows)

    # Legacy counts
    assert summary["ready_count"] == 2
    assert summary["watch_count"] == 1
    assert summary["wait_count"] == 1
    assert summary["skip_count"] == 1

    # New group counts
    assert summary["ready_now_count"] == 2
    assert summary["waiting_confirmation_count"] == 1
    assert summary["watch_zone_count"] == 1
    assert summary["blocked_count"] == 1


def test_summary_top_and_average():
    rows = [
        {"scanner_group": READY_NOW, "opportunity_score": 90},
        {"scanner_group": READY_NOW, "opportunity_score": 80},
    ]
    summary = scanner_summary(rows)
    assert summary["top_opportunity_score"] == 90
    assert summary["average_opportunity_score"] == 85.0


def test_summary_fallback_from_scanner_action():
    """Rows missing scanner_group fall back to scanner_action."""
    rows = [
        {"scanner_action": "ready"},
        {"scanner_action": "wait"},
        {"scanner_action": "watch"},
        {"scanner_action": "skip"},
    ]
    summary = scanner_summary(rows)
    assert summary["ready_now_count"] == 1
    assert summary["waiting_confirmation_count"] == 1
    assert summary["watch_zone_count"] == 1
    assert summary["blocked_count"] == 1


def test_summary_empty_no_crash():
    summary = scanner_summary([])
    assert summary["ready_count"] == 0
    assert summary["ready_now_count"] == 0
    assert summary["top_opportunity_score"] is None
    assert summary["average_opportunity_score"] == 0
