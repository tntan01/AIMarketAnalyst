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
