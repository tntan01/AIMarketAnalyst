"""Phase 15.5 — test calculate_opportunity_score()."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_ranking_engine import (
    calculate_opportunity_score,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
    SCANNER_PROXIMITY_IN_ZONE,
    SCANNER_RANKING_READY_NOW,
    SCANNER_SPREAD_PENALTY,
    SCANNER_NEWS_PENALTY,
    SCANNER_RR_WEAK,
)


# ---------------------------------------------------------------------------
# Ready case
# ---------------------------------------------------------------------------


def test_ready_case():
    row = {
        "final_score": 85,
        "decision": "READY_TO_TRADE",
        "entry_status": "confirmed_entry",
        "price_vs_zone": "in_zone",
        "risk_reward": "1:2.0",
        "spread_status": "normal",
    }
    result = calculate_opportunity_score(row)
    # base 85 + prox 8 + readiness 10 + rr 5 = 108
    assert result["opportunity_score"] == 108
    assert result["scanner_group"] == READY_NOW
    assert SCANNER_RANKING_READY_NOW in result["reason_codes"]
    assert SCANNER_PROXIMITY_IN_ZONE in result["reason_codes"]
    assert "base_final_score" in result["score_breakdown"]


# ---------------------------------------------------------------------------
# Waiting case
# ---------------------------------------------------------------------------


def test_waiting_case():
    row = {
        "final_score": 80,
        "decision": "WAITING_CONFIRMATION",
        "entry_status": "waiting_confirmation",
        "price_vs_zone": "near_zone",
        "risk_reward": "1:1.5",
        "spread_status": "normal",
    }
    result = calculate_opportunity_score(row)
    # base 80 + prox 4 + readiness 3 + rr 3 = 90
    assert result["opportunity_score"] == 90
    assert result["scanner_group"] == WAITING_CONFIRMATION


# ---------------------------------------------------------------------------
# Blocked high score override
# ---------------------------------------------------------------------------


def test_blocked_high_score_capped():
    row = {
        "final_score": 95,
        "decision": "TRADE_BLOCKED",
        "trade_permission": {"status": "blocked"},
        "entry_status": "confirmed_entry",
        "risk_reward": "1:2.0",
        "spread_status": "normal",
    }
    result = calculate_opportunity_score(row)
    assert result["scanner_group"] == BLOCKED
    assert result["opportunity_score"] <= 20


# ---------------------------------------------------------------------------
# News / spread penalties
# ---------------------------------------------------------------------------


def test_news_spread_penalties():
    row = {
        "final_score": 80,
        "decision": "READY_TO_TRADE",
        "entry_status": "confirmed_entry",
        "price_vs_zone": "in_zone",
        "risk_reward": "1:2.0",
        "spread_status": "abnormal",
        "high_impact_event_within_30m": True,
    }
    result = calculate_opportunity_score(row)
    assert SCANNER_SPREAD_PENALTY in result["penalty_codes"]
    assert SCANNER_NEWS_PENALTY in result["penalty_codes"]
    # base 80 + prox 8 + readiness 10 + rr 5 - spread 8 - news 10 = 85
    assert result["opportunity_score"] == 85


# ---------------------------------------------------------------------------
# Weak R:R penalty
# ---------------------------------------------------------------------------


def test_weak_rr_penalty():
    row = {
        "final_score": 75,
        "decision": "WATCH_ONLY",
        "entry_status": "watch_zone",
        "risk_reward": "1:1.1",
        "spread_status": "normal",
    }
    result = calculate_opportunity_score(row)
    assert SCANNER_RR_WEAK in result["penalty_codes"]
    assert result["scanner_group"] == WATCH_ZONE


# ---------------------------------------------------------------------------
# Dirty data
# ---------------------------------------------------------------------------


def test_dirty_data_no_crash():
    result = calculate_opportunity_score(None)
    assert result["scanner_group"] == WATCH_ZONE
    assert result["opportunity_score"] == 0


def test_empty_dict():
    result = calculate_opportunity_score({})
    assert result["scanner_group"] == WATCH_ZONE


def test_no_mutate():
    row = {"final_score": 80, "decision": "READY_TO_TRADE"}
    original = dict(row)
    calculate_opportunity_score(row)
    assert row == original


# ---------------------------------------------------------------------------
# Proximity boolean fallback (price_in_entry_zone when price_vs_zone missing)
# ---------------------------------------------------------------------------


def test_opportunity_uses_price_in_entry_zone_true_when_price_vs_zone_missing():
    """price_in_entry_zone=True means price is in zone → +8 proximity bonus."""
    row = {
        "final_score": 80,
        "decision": "READY_TO_TRADE",
        "entry_status": "confirmed_entry",
        "price_in_entry_zone": True,
        "risk_reward": "1:2.0",
    }
    result = calculate_opportunity_score(row)
    assert result["score_breakdown"]["proximity_bonus"] == 8, (
        f"Expected proximity_bonus=8, got {result['score_breakdown']['proximity_bonus']}"
    )
    assert "SCANNER_PROXIMITY_IN_ZONE" in result["reason_codes"], (
        f"Expected SCANNER_PROXIMITY_IN_ZONE in reason_codes: {result['reason_codes']}"
    )


def test_opportunity_uses_price_in_entry_zone_false_as_far_when_price_vs_zone_missing():
    """price_in_entry_zone=False means price is far → 0 proximity bonus."""
    row = {
        "final_score": 80,
        "decision": "READY_TO_TRADE",
        "entry_status": "confirmed_entry",
        "price_in_entry_zone": False,
        "risk_reward": "1:2.0",
    }
    result = calculate_opportunity_score(row)
    assert result["score_breakdown"]["proximity_bonus"] == 0, (
        f"Expected proximity_bonus=0, got {result['score_breakdown']['proximity_bonus']}"
    )
    assert "SCANNER_PROXIMITY_FAR" in result["reason_codes"], (
        f"Expected SCANNER_PROXIMITY_FAR in reason_codes: {result['reason_codes']}"
    )
