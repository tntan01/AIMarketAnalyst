"""Phase 15.6 — test enrich_scanner_row_with_ranking()."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_ranking_engine import (
    enrich_scanner_row_with_ranking,
    enrich_scanner_rows,
    BLOCKED,
)


def test_row_with_direct_final_score():
    row = {"final_score": 85, "decision": "READY_TO_TRADE", "entry_status": "confirmed_entry"}
    enriched = enrich_scanner_row_with_ranking(row)
    assert enriched["opportunity_score"] > 80
    assert "scanner_group" in enriched
    assert enriched["display_action"] in {"ready", "wait", "watch", "skip"}


def test_row_falls_back_to_analysis_result():
    row = {
        "analysis_result": {
            "final_score": 82,
            "decision_engine": {"decision": "READY_TO_TRADE"},
        },
        "entry_status": "confirmed_entry",
    }
    enriched = enrich_scanner_row_with_ranking(row)
    assert enriched["final_score"] == 82
    assert enriched["scanner_decision"] == "READY_TO_TRADE"


def test_row_decision_from_analysis_result():
    row = {
        "analysis_result": {
            "decision_engine": {"decision": "WATCH_ONLY"},
        },
    }
    enriched = enrich_scanner_row_with_ranking(row)
    assert enriched["scanner_decision"] == "WATCH_ONLY"


def test_row_score_gap_from_analysis_result():
    row = {
        "analysis_result": {
            "final_score": 80,
            "decision_summary": {"score_gap": 12},
        },
    }
    enriched = enrich_scanner_row_with_ranking(row)
    assert enriched["score_gap"] == 12


def test_row_expected_effective_rr_from_analysis_result():
    row = {
        "analysis_result": {
            "final_score": 80,
            "scenarios": [{"expected_effective_rr": 1.8}],
        },
    }
    enriched = enrich_scanner_row_with_ranking(row)
    assert enriched["expected_effective_rr"] == 1.8


def test_does_not_mutate_original():
    original = {"final_score": 80, "analysis_result": {"final_score": 90, "decision_engine": {"decision": "READY_TO_TRADE"}}}
    saved = {"final_score": 80, "analysis_result": {"final_score": 90, "decision_engine": {"decision": "READY_TO_TRADE"}}}
    enrich_scanner_row_with_ranking(original)
    assert original == saved


def test_none_no_crash():
    result = enrich_scanner_row_with_ranking(None)
    assert result["scanner_group"] == BLOCKED
    assert result["opportunity_score"] == 0


def test_enrich_batch():
    rows = [
        {"final_score": 85, "decision": "READY_TO_TRADE", "entry_status": "confirmed_entry"},
        {"final_score": 30, "decision": "TRADE_BLOCKED"},
    ]
    results = enrich_scanner_rows(rows)
    assert len(results) == 2
    assert results[0]["opportunity_score"] > 80
    assert results[1]["scanner_group"] == BLOCKED


def test_enrich_batch_none():
    assert enrich_scanner_rows(None) == []


# ---------------------------------------------------------------------------
# Proximity boolean fallback in enrich_scanner_row_with_ranking
# ---------------------------------------------------------------------------


def test_enrich_row_uses_boolean_price_in_entry_zone_true_for_proximity_bonus():
    """Row without price_vs_zone but with price_in_entry_zone=True must
    receive the +8 in_zone proximity bonus during enrichment."""
    row = {
        "final_score": 80,
        "decision": "READY_TO_TRADE",
        "entry_status": "confirmed_entry",
        "price_in_entry_zone": True,
        "risk_reward": "1:2.0",
    }
    enriched = enrich_scanner_row_with_ranking(row)

    assert enriched["ranking_score_breakdown"]["proximity_bonus"] == 8, (
        f"Expected proximity_bonus=8, got {enriched['ranking_score_breakdown']['proximity_bonus']}"
    )
    assert "SCANNER_PROXIMITY_IN_ZONE" in enriched["ranking_reason_codes"], (
        f"Expected SCANNER_PROXIMITY_IN_ZONE in ranking_reason_codes: {enriched['ranking_reason_codes']}"
    )
    assert enriched["opportunity_score"] > 80, (
        f"Expected opportunity_score > 80, got {enriched['opportunity_score']}"
    )
    # Original row must not be mutated
    assert "scanner_group" not in row


def test_enrich_row_uses_boolean_price_in_entry_zone_false_as_far():
    """Row without price_vs_zone but with price_in_entry_zone=False must
    receive 0 proximity bonus (far) during enrichment."""
    row = {
        "final_score": 80,
        "decision": "READY_TO_TRADE",
        "entry_status": "confirmed_entry",
        "price_in_entry_zone": False,
        "risk_reward": "1:2.0",
    }
    enriched = enrich_scanner_row_with_ranking(row)

    assert enriched["ranking_score_breakdown"]["proximity_bonus"] == 0, (
        f"Expected proximity_bonus=0, got {enriched['ranking_score_breakdown']['proximity_bonus']}"
    )
    assert "SCANNER_PROXIMITY_FAR" in enriched["ranking_reason_codes"], (
        f"Expected SCANNER_PROXIMITY_FAR in ranking_reason_codes: {enriched['ranking_reason_codes']}"
    )
