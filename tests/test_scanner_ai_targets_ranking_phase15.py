"""Phase 15.10 — test updated ai_targets() with scanner_group + opportunity_score."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner import ai_targets
from core.scanner_ranking_engine import READY_NOW, WAITING_CONFIRMATION, WATCH_ZONE, BLOCKED


def test_ai_targets_prioritizes_ready():
    rows = [
        {"symbol": "A", "scanner_group": READY_NOW,             "opportunity_score": 90, "final_score": 82, "trade_permission": "allowed"},
        {"symbol": "B", "scanner_group": WAITING_CONFIRMATION, "opportunity_score": 85, "final_score": 80, "trade_permission": "allowed"},
        {"symbol": "C", "scanner_group": WATCH_ZONE,           "opportunity_score": 88, "final_score": 85, "trade_permission": "allowed"},
    ]
    result = ai_targets(rows, 2)
    assert len(result) == 2
    assert result[0]["symbol"] == "A"  # READY_NOW first
    assert result[1]["symbol"] == "B"  # WAITING second (priority beats opportunity score for C)


def test_ai_targets_excludes_blocked():
    rows = [
        {"symbol": "X", "scanner_group": READY_NOW, "opportunity_score": 95, "final_score": 90, "trade_permission": "allowed"},
        {"symbol": "Y", "scanner_group": BLOCKED,   "opportunity_score": 20, "final_score": 85, "trade_permission": "blocked"},
    ]
    result = ai_targets(rows, 3)
    assert len(result) == 1
    assert result[0]["symbol"] == "X"


def test_ai_targets_limit_zero():
    rows = [
        {"symbol": "A", "scanner_group": READY_NOW, "opportunity_score": 90, "trade_permission": "allowed"},
    ]
    assert ai_targets(rows, 0) == []


def test_ai_targets_legacy_fallback():
    """Old rows without scanner_group use best_score >= 75 filter."""
    rows = [
        {"symbol": "L1", "best_score": 80, "trade_permission": "allowed"},
        {"symbol": "L2", "best_score": 60, "trade_permission": "allowed"},
        {"symbol": "L3", "best_score": 85, "trade_permission": "allowed"},
    ]
    result = ai_targets(rows, 5)
    symbols = [r["symbol"] for r in result]
    assert "L2" not in symbols  # score < 75
    assert "L1" in symbols
    assert "L3" in symbols
