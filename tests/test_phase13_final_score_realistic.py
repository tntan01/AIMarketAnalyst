"""Phase 13.11 — realistic scenarios for final_score_engine."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.final_score_engine import (
    calculate_final_score,
    calculate_final_score_batch,
    summarize_final_scores,
    calculate_final_score_from_payload,
    FINAL_SCORE_EVIDENCE_NEGATIVE,
    FINAL_SCORE_EVIDENCE_POSITIVE,
    FINAL_SCORE_EXECUTION_WEAK,
    FINAL_SCORE_EXECUTION_STRONG,
    FINAL_SCORE_DATA_INCOMPLETE,
)


# Case 1 — Strong technical, neutral evidence, perfect execution
def test_case1_strong_signal_neutral_evidence():
    result = calculate_final_score(
        signal_score=84,
        evidence_score=50,
        execution_quality_score=100,
    )
    expected = round(84 * 0.65 + 50 * 0.20 + 100 * 0.15)
    assert result["final_score"] == expected
    # Neutral evidence → no positive code
    assert FINAL_SCORE_EVIDENCE_POSITIVE not in result["reason_codes"]


# Case 2 — Strong signal but bad evidence and weak execution
def test_case2_strong_signal_bad_evidence_weak_exec():
    result = calculate_final_score(
        signal_score=88,
        evidence_score=30,
        execution_quality_score=45,
    )
    expected = round(88 * 0.65 + 30 * 0.20 + 45 * 0.15)
    assert result["final_score"] == expected
    # final_score must be clearly lower than signal_score
    assert result["final_score"] < 88
    # Penalty codes
    assert FINAL_SCORE_EVIDENCE_NEGATIVE in result["penalty_codes"]
    assert FINAL_SCORE_EXECUTION_WEAK in result["penalty_codes"]


# Case 3 — Moderate signal but good evidence and execution
def test_case3_moderate_signal_good_evidence_exec():
    result = calculate_final_score(
        signal_score=68,
        evidence_score=80,
        execution_quality_score=95,
    )
    expected = round(68 * 0.65 + 80 * 0.20 + 95 * 0.15)
    assert result["final_score"] == expected
    # final_score rises vs signal, but not unreasonably
    assert result["final_score"] > 68
    assert result["final_score"] < 95  # not exceeding the best component
    # Reason codes
    assert FINAL_SCORE_EVIDENCE_POSITIVE in result["reason_codes"]
    assert FINAL_SCORE_EXECUTION_STRONG in result["reason_codes"]


# Case 4 — Dirty data
def test_case4_dirty_data_no_crash():
    result = calculate_final_score(
        signal_score="abc",
        evidence_score=None,
        execution_quality_score="nan",
    )
    assert isinstance(result["final_score"], int)
    assert 0 <= result["final_score"] <= 100
    assert FINAL_SCORE_DATA_INCOMPLETE in result["warning_codes"]
    # defaults: signal=0, evidence=50, execution=100
    assert result["score_inputs"]["signal_score"] == 0
    assert result["score_inputs"]["evidence_score"] == 50
    assert result["score_inputs"]["execution_quality_score"] == 100


# Case 5 — Batch realistic
def test_case5_batch_realistic():
    payloads = [
        {"signal_score": 82, "evidence_score": 55, "execution_quality_score": 100},
        {"signal_score": 76, "evidence_score": 35, "execution_quality_score": 65},
        {"signal_score": 90, "evidence_score": 50, "execution_quality_score": 60},
        {"signal_score": 58, "evidence_score": 80, "execution_quality_score": 95},
        {"signal_score": 35, "evidence_score": 30, "execution_quality_score": 20},
    ]
    results = calculate_final_score_batch(payloads)
    assert len(results) == 5

    # Verify individual results
    assert results[0]["final_score"] == round(82 * 0.65 + 55 * 0.20 + 100 * 0.15)  # 79
    assert results[1]["final_score"] == round(76 * 0.65 + 35 * 0.20 + 65 * 0.15)   # 66
    assert results[2]["final_score"] == round(90 * 0.65 + 50 * 0.20 + 60 * 0.15)   # 78
    assert results[3]["final_score"] == round(58 * 0.65 + 80 * 0.20 + 95 * 0.15)   # 68
    assert results[4]["final_score"] == round(35 * 0.65 + 30 * 0.20 + 20 * 0.15)  # 32

    # Case 2 (index 1): bad evidence + weak exec → penalty codes
    assert FINAL_SCORE_EVIDENCE_NEGATIVE in results[1]["penalty_codes"]
    assert FINAL_SCORE_EXECUTION_WEAK in results[1]["penalty_codes"]

    # Case 4 (index 3): good evidence + strong exec → reason codes
    assert FINAL_SCORE_EVIDENCE_POSITIVE in results[3]["reason_codes"]
    assert FINAL_SCORE_EXECUTION_STRONG in results[3]["reason_codes"]

    # Summary
    summary = summarize_final_scores(results)
    assert summary["count"] == 5
    expected_avg = round((79 + 66 + 78 + 68 + 32) / 5, 2)
    assert summary["average_final_score"] == expected_avg
    assert summary["min_final_score"] == 32
    assert summary["max_final_score"] == 79
    assert summary["strong_count"] == 0  # none ≥ 80
    assert summary["weak_count"] == 1     # only 32 < 50
    assert len(summary["penalty_code_counts"]) >= 1


# Case 6 — Payload-based realistic
def test_case6_payload_realistic():
    """Use calculate_final_score_from_payload with full scenario_scores structure."""
    payload = {
        "scenario_scores": {
            "buy": {"signal_score": 82},
            "sell": {"signal_score": 60},
        },
        "evidence": {"evidence_score": 55},
        "execution_quality_score": 85,
    }
    result = calculate_final_score_from_payload(payload, side="buy")
    expected = round(82 * 0.65 + 55 * 0.20 + 85 * 0.15)
    assert result["final_score"] == expected
    assert result["score_breakdown"]["source"] == "payload"
    assert result["score_breakdown"]["side"] == "buy"


# Case 7 — 100 signal + 100 evidence + 100 execution = 100
def test_case7_all_perfect():
    result = calculate_final_score(100, 100, 100)
    assert result["final_score"] == 100


# Case 8 — 0 signal + 0 evidence + 0 execution = 0
def test_case8_all_zero():
    result = calculate_final_score(0, 0, 0)
    assert result["final_score"] == 0


# Case 9 — Custom weights (realistic evolution scenario)
def test_case9_custom_weights_evolution():
    """Simulate Phase 13+ weights where evidence gains importance."""
    late_stage_weights = {
        "signal_score": 0.55,
        "evidence_score": 0.25,
        "execution_quality_score": 0.20,
    }
    result = calculate_final_score(80, 85, 90, weights=late_stage_weights)
    expected = round(80 * 0.55 + 85 * 0.25 + 90 * 0.20)
    assert result["final_score"] == expected
    # With higher evidence weight, evidence_pos is still a reason
    assert FINAL_SCORE_EVIDENCE_POSITIVE in result["reason_codes"]
