"""Phase 13.5 — test calculate_final_score_from_payload() and pick_* helpers."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.final_score_engine import (
    pick_signal_score,
    pick_evidence_score,
    pick_execution_quality_score,
    calculate_final_score_from_payload,
    DEFAULT_SIGNAL_SCORE,
    DEFAULT_EVIDENCE_SCORE,
    DEFAULT_EXECUTION_QUALITY_SCORE,
)


# ---------------------------------------------------------------------------
# pick_signal_score
# ---------------------------------------------------------------------------


def test_pick_signal_side_buy_with_signal_score():
    payload = {
        "scenario_scores": {
            "buy": {"signal_score": 82},
            "sell": {"signal_score": 60},
        }
    }
    assert pick_signal_score(payload, "buy") == 82


def test_pick_signal_side_sell_with_signal_score():
    payload = {
        "scenario_scores": {
            "buy": {"signal_score": 82},
            "sell": {"signal_score": 60},
        }
    }
    assert pick_signal_score(payload, "sell") == 60


def test_pick_signal_falls_back_to_total():
    payload = {
        "scenario_scores": {
            "buy": {"total": 75},
        }
    }
    assert pick_signal_score(payload, "buy") == 75


def test_pick_signal_decision_summary_best_score():
    payload = {"decision_summary": {"best_score": 78}}
    assert pick_signal_score(payload, None) == 78


def test_pick_signal_direct_best_score_field():
    payload = {"best_score": 70}
    assert pick_signal_score(payload, None) == 70


def test_pick_signal_direct_signal_score_field():
    payload = {"signal_score": 65}
    assert pick_signal_score(payload, None) == 65


def test_pick_signal_side_not_found_falls_to_summary():
    payload = {
        "scenario_scores": {"buy": {"signal_score": 82}},
        "decision_summary": {"best_score": 55},
    }
    # side=sell but only buy exists → fallback to summary
    assert pick_signal_score(payload, "sell") == 55


def test_pick_signal_none_payload():
    assert pick_signal_score(None, "buy") == DEFAULT_SIGNAL_SCORE


def test_pick_signal_empty_payload():
    assert pick_signal_score({}, None) == DEFAULT_SIGNAL_SCORE


# ---------------------------------------------------------------------------
# pick_evidence_score
# ---------------------------------------------------------------------------


def test_pick_evidence_direct_key():
    payload = {"evidence_score": 68}
    assert pick_evidence_score(payload) == 68


def test_pick_evidence_evidence_block():
    payload = {"evidence": {"evidence_score": 72}}
    assert pick_evidence_score(payload) == 72


def test_pick_evidence_statistical_edge_block():
    payload = {"statistical_edge": {"evidence_score": 55}}
    assert pick_evidence_score(payload) == 55


def test_pick_evidence_precedence():
    """Direct key wins over block."""
    payload = {
        "evidence_score": 68,
        "evidence": {"evidence_score": 72},
    }
    assert pick_evidence_score(payload) == 68


def test_pick_evidence_none_payload():
    assert pick_evidence_score(None) == DEFAULT_EVIDENCE_SCORE


def test_pick_evidence_missing():
    assert pick_evidence_score({}) == DEFAULT_EVIDENCE_SCORE


# ---------------------------------------------------------------------------
# pick_execution_quality_score
# ---------------------------------------------------------------------------


def test_pick_exec_direct_key():
    payload = {"execution_quality_score": 88}
    assert pick_execution_quality_score(payload) == 88


def test_pick_exec_execution_quality_block():
    payload = {"execution_quality": {"execution_quality_score": 92}}
    assert pick_execution_quality_score(payload) == 92


def test_pick_exec_execution_block():
    payload = {"execution": {"execution_quality_score": 75}}
    assert pick_execution_quality_score(payload) == 75


def test_pick_exec_precedence():
    payload = {
        "execution_quality_score": 88,
        "execution_quality": {"execution_quality_score": 92},
    }
    assert pick_execution_quality_score(payload) == 88


def test_pick_exec_none_payload():
    assert pick_execution_quality_score(None) == DEFAULT_EXECUTION_QUALITY_SCORE


def test_pick_exec_missing():
    assert pick_execution_quality_score({}) == DEFAULT_EXECUTION_QUALITY_SCORE


# ---------------------------------------------------------------------------
# calculate_final_score_from_payload
# ---------------------------------------------------------------------------


def test_from_payload_with_side():
    payload = {
        "scenario_scores": {
            "buy": {"signal_score": 82},
            "sell": {"signal_score": 60},
        },
        "evidence": {"evidence_score": 50},
        "execution_quality": {"execution_quality_score": 100},
    }
    result = calculate_final_score_from_payload(payload, side="buy")
    expected = round(82 * 0.65 + 50 * 0.20 + 100 * 0.15)
    assert result["final_score"] == expected
    assert result["score_inputs"]["signal_score"] == 82


def test_from_payload_no_side():
    payload = {
        "decision_summary": {"best_score": 78},
        "evidence_score": 50,
        "execution_quality_score": 100,
    }
    result = calculate_final_score_from_payload(payload)
    expected = round(78 * 0.65 + 50 * 0.20 + 100 * 0.15)
    assert result["final_score"] == expected


def test_from_payload_missing_evidence_and_exec():
    """Missing evidence/exec → fallback to 50 and 100."""
    payload = {"scenario_scores": {"buy": {"signal_score": 80}}}
    result = calculate_final_score_from_payload(payload, side="buy")
    expected = round(80 * 0.65 + 50 * 0.20 + 100 * 0.15)
    assert result["final_score"] == expected


def test_from_payload_none_no_crash():
    result = calculate_final_score_from_payload(None)
    assert isinstance(result["final_score"], int)


def test_from_payload_score_breakdown_has_metadata():
    payload = {"signal_score": 70}
    result = calculate_final_score_from_payload(payload, side="buy")
    breakdown = result["score_breakdown"]
    assert breakdown.get("source") == "payload"
    assert breakdown.get("side") == "buy"


def test_from_payload_does_not_mutate_original():
    original = {
        "scenario_scores": {
            "buy": {"signal_score": 82},
        },
        "evidence_score": 50,
    }
    copy = {
        "scenario_scores": {
            "buy": {"signal_score": 82},
        },
        "evidence_score": 50,
    }
    calculate_final_score_from_payload(original, side="buy")
    assert original == copy


def test_from_payload_custom_weights():
    custom = {"signal_score": 0.50, "evidence_score": 0.30, "execution_quality_score": 0.20}
    payload = {"signal_score": 80, "evidence_score": 50, "execution_quality_score": 100}
    result = calculate_final_score_from_payload(payload, weights=custom)
    expected = round(80 * 0.50 + 50 * 0.30 + 100 * 0.20)
    assert result["final_score"] == expected


def test_pick_signal_clamps_out_of_range():
    payload = {"scenario_scores": {"buy": {"signal_score": 150}}}
    assert pick_signal_score(payload, "buy") == 100

    payload2 = {"scenario_scores": {"sell": {"signal_score": -20}}}
    assert pick_signal_score(payload2, "sell") == 0
