from __future__ import annotations

from core.reason_codes import (
    SCANNER_NEWS_PENALTY,
    SCANNER_PROXIMITY_IN_ZONE,
    SCANNER_RANKING_BLOCKED,
    SCANNER_RANKING_READY_NOW,
    SCANNER_RR_STRONG,
)
from core.scanner_ranking_engine import (
    BLOCKED,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    calculate_opportunity_score,
    classify_scanner_group,
    enrich_scanner_row_with_ranking,
)


def test_classify_scanner_group_uses_decision_engine_before_legacy_action():
    assert classify_scanner_group(decision="READY_TO_TRADE", scanner_action="skip") == READY_NOW
    assert classify_scanner_group(decision="WAITING_CONFIRMATION", scanner_action="ready", ready_to_trade=True) == WAITING_CONFIRMATION
    assert classify_scanner_group(decision="WATCH_ONLY", scanner_action="ready", ready_to_trade=True) == WATCH_ZONE


def test_classify_scanner_group_blocks_trade_permission_and_invalid_entry():
    assert classify_scanner_group(trade_permission={"status": "blocked"}, scanner_action="ready", ready_to_trade=True) == BLOCKED
    assert classify_scanner_group(entry_status="data_unavailable") == BLOCKED
    assert classify_scanner_group(scanner_action="skip") == BLOCKED


def test_calculate_opportunity_score_rewards_ready_in_zone_strong_rr():
    result = calculate_opportunity_score(
        {
            "final_score": 80,
            "decision": "READY_TO_TRADE",
            "price_vs_zone": "in_zone",
            "expected_effective_rr": 2.2,
            "spread_status": "normal",
        }
    )

    assert result["scanner_group"] == READY_NOW
    assert result["opportunity_score"] == 103
    assert SCANNER_RANKING_READY_NOW in result["reason_codes"]
    assert SCANNER_PROXIMITY_IN_ZONE in result["reason_codes"]
    assert SCANNER_RR_STRONG in result["reason_codes"]
    assert result["score_breakdown"]["base_final_score"] == 80
    assert result["score_breakdown"]["readiness_bonus"] == 10


def test_calculate_opportunity_score_caps_blocked_rows_and_keeps_penalties():
    result = calculate_opportunity_score(
        {
            "final_score": 90,
            "decision": "TRADE_BLOCKED",
            "price_vs_zone": "in_zone",
            "risk_reward": "1:2.5",
            "high_impact_event_within_30m": True,
        }
    )

    assert result["scanner_group"] == BLOCKED
    assert result["opportunity_score"] == 20
    assert SCANNER_RANKING_BLOCKED in result["reason_codes"]
    assert SCANNER_NEWS_PENALTY in result["penalty_codes"]


def test_enrich_scanner_row_uses_nested_analysis_without_mutating_original():
    row = {
        "symbol": "EUR/USD",
        "analysis_result": {
            "final_score": 82,
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "entry_status": "confirmed_entry",
            "scenarios": [{"expected_effective_rr": 2.0}],
        },
        "price_vs_zone": "near_zone",
    }

    enriched = enrich_scanner_row_with_ranking(row)

    assert "opportunity_score" not in row
    assert enriched["final_score"] == 82
    assert enriched["scanner_group"] == READY_NOW
    assert enriched["display_action"] == "ready"


def test_zone_quality_bonus_rewards_high_zone_score():
    """Row with entry_zone_score=90 should rank higher than identical row with score=20."""
    from core.scanner_ranking_engine import calculate_opportunity_score

    base_row = {
        "final_score": 70,
        "scanner_decision": "watch",
        "scanner_action": "watch",
        "trade_permission": "allowed",
        "price_in_entry_zone": True,
        "expected_effective_rr": 2.0,
        "spread_status": "normal",
    }

    row_good = dict(base_row, entry_zone_score=90)
    row_bad = dict(base_row, entry_zone_score=20)

    result_good = calculate_opportunity_score(row_good)
    result_bad = calculate_opportunity_score(row_bad)

    # zone_score=90: (90-50)/50=0.8 * 6 = 4.8 -> int=4
    # zone_score=20: 20<50 -> max(0, ...)=0 -> 0
    assert result_good["score_breakdown"]["zone_quality_bonus"] >= 4
    assert result_bad["score_breakdown"]["zone_quality_bonus"] == 0
    assert result_good["opportunity_score"] > result_bad["opportunity_score"], (
        f"Good zone ({result_good['opportunity_score']}) should outrank bad zone ({result_bad['opportunity_score']})"
    )


def test_missing_zone_score_does_not_crash():
    """Row without entry_zone_score should get zone_bonus=0, not crash."""
    from core.scanner_ranking_engine import calculate_opportunity_score

    row = {
        "final_score": 70,
        "scanner_decision": "watch",
        "scanner_action": "watch",
        "trade_permission": "allowed",
        "price_in_entry_zone": True,
        "expected_effective_rr": 2.0,
        "spread_status": "normal",
    }
    result = calculate_opportunity_score(row)
    assert result["score_breakdown"]["zone_quality_bonus"] == 0
    assert result["opportunity_score"] >= 0


# ---------------------------------------------------------------------------
# Phase 4A: base-case RR preferred in ranking
# ---------------------------------------------------------------------------


def test_rr_bonus_uses_base_case_when_available():
    """Row with best=2.5 but base=1.1 → RR bonus should use 1.1 (no bonus, < 1.3)."""
    result = calculate_opportunity_score(
        {
            "final_score": 80,
            "decision": "READY_TO_TRADE",
            "price_vs_zone": "in_zone",
            "expected_effective_rr": 2.5,
            "expected_effective_rr_base": 1.1,
            "spread_status": "normal",
        }
    )
    # RR=1.1 < 1.3 → rr_bonus=0 (no tier applies)
    assert result["score_breakdown"]["rr_bonus"] == 0
    # Without base override, best=2.5 → rr_bonus=5; total would be 80+8+10+5=103
    # With base=1.1, total should be 80+8+10+0=98
    assert result["opportunity_score"] == 98


def test_rr_bonus_falls_back_to_best_case_when_base_missing():
    """Row missing base but has best=2.0 → RR bonus uses 2.0."""
    result = calculate_opportunity_score(
        {
            "final_score": 80,
            "decision": "READY_TO_TRADE",
            "price_vs_zone": "in_zone",
            "expected_effective_rr": 2.0,
            "spread_status": "normal",
        }
    )
    assert result["score_breakdown"]["rr_bonus"] == 5
    assert result["opportunity_score"] == 103


def test_rr_bonus_falls_back_to_risk_reward_when_both_effective_missing():
    """Row missing both effective RR fields but has risk_reward='1:1.8'."""
    result = calculate_opportunity_score(
        {
            "final_score": 80,
            "decision": "READY_TO_TRADE",
            "price_vs_zone": "in_zone",
            "risk_reward": "1:1.8",
            "spread_status": "normal",
        }
    )
    # parse_risk_reward("1:1.8") → 1.8; 1.5 <= 1.8 < 2.0 → rr_bonus = 5*0.6 = 3
    assert result["score_breakdown"]["rr_bonus"] == 3


def test_rr_bonus_does_not_crash_with_invalid_values():
    """None, broken string, empty dict — must return 0 bonus, not crash."""
    for bad_value in (None, "abc", "", {}):
        result = calculate_opportunity_score(
            {
                "final_score": 70,
                "scanner_decision": "watch",
                "scanner_action": "watch",
                "trade_permission": "allowed",
                "price_in_entry_zone": True,
                "expected_effective_rr_base": bad_value,
                "expected_effective_rr": bad_value,
                "risk_reward": bad_value,
                "spread_status": "normal",
            }
        )
        assert result["score_breakdown"]["rr_bonus"] == 0, \
            f"Should get rr_bonus=0 for bad_value={bad_value!r}"
        assert result["opportunity_score"] >= 0


def test_safe_rr_prefers_base_over_best_over_risk_reward():
    """Verify _safe_rr priority: base → best → risk_reward string."""
    from core.scanner import _safe_rr

    # base available: use it
    assert _safe_rr({
        "expected_effective_rr_base": 1.1,
        "expected_effective_rr": 2.5,
        "risk_reward": "1:3.0",
    }) == 1.1

    # base missing, best available
    assert _safe_rr({
        "expected_effective_rr": 2.0,
        "risk_reward": "1:3.0",
    }) == 2.0

    # both missing, fallback to risk_reward string
    assert _safe_rr({
        "risk_reward": "1:1.8",
    }) == 1.8

    # all missing
    assert _safe_rr({}) == 0.0

    # base is None, best available
    assert _safe_rr({
        "expected_effective_rr_base": None,
        "expected_effective_rr": 1.5,
    }) == 1.5

    # base is invalid string, best available
    assert _safe_rr({
        "expected_effective_rr_base": "abc",
        "expected_effective_rr": 1.5,
    }) == 1.5


# ---------------------------------------------------------------------------
# Micro-fix: _find_scenario_for_side matches both "type" and "side" keys
# ---------------------------------------------------------------------------


def test_enrich_picks_scenario_by_type_key_not_first_element():
    """When best_side='sell', enrichment must pick the 'sell' scenario even if
    a 'buy' scenario comes first in the list (scenarios use 'type' key)."""
    row = {
        "symbol": "EUR/USD",
        "analysis_result": {
            "final_score": 80,
            "decision_summary": {"best_side": "sell"},
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "scenarios": [
                {"type": "buy", "expected_effective_rr_base": 2.5, "entry_zone_score": 90},
                {"type": "sell", "expected_effective_rr_base": 1.1, "entry_zone_score": 60},
            ],
        },
        "price_vs_zone": "near_zone",
    }
    enriched = enrich_scanner_row_with_ranking(row)

    # Must pick the sell scenario (index 1), not the buy scenario (index 0)
    assert enriched["expected_effective_rr_base"] == 1.1
    assert enriched["entry_zone_score"] == 60
    # RR bonus should use base=1.1 (no bonus: < 1.3)
    assert enriched["opportunity_score"] < 100  # would be higher if bonus from 2.5


def test_enrich_matches_scenario_by_side_key_backward_compat():
    """Scenario using 'side' key instead of 'type' must still be found."""
    row = {
        "symbol": "EUR/USD",
        "analysis_result": {
            "final_score": 80,
            "decision_summary": {"best_side": "sell"},
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "scenarios": [
                {"side": "buy", "expected_effective_rr_base": 3.0},
                {"side": "sell", "expected_effective_rr_base": 1.8},
            ],
        },
        "price_vs_zone": "in_zone",
    }
    enriched = enrich_scanner_row_with_ranking(row)

    assert enriched["expected_effective_rr_base"] == 1.8


def test_enrich_scenario_fallback_to_first_when_best_side_not_found():
    """When best_side matches neither 'type' nor 'side', fall back to scenarios[0]."""
    row = {
        "symbol": "EUR/USD",
        "analysis_result": {
            "final_score": 75,
            "decision_summary": {"best_side": "sell"},
            "decision_engine": {"decision": "WATCH_ONLY"},
            "scenarios": [
                {"type": "buy", "expected_effective_rr_base": 2.0},
                # No sell scenario — only buy
            ],
        },
        "price_vs_zone": "far",
    }
    enriched = enrich_scanner_row_with_ranking(row)

    # Falls back to scenarios[0] (buy) since no sell match
    assert enriched["expected_effective_rr_base"] == 2.0
