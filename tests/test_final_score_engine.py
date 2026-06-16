from __future__ import annotations

from core.final_score_engine import (
    calculate_final_score,
    calculate_final_score_batch,
    calculate_final_score_from_payload,
)
from core.reason_codes import (
    FINAL_SCORE_DATA_INCOMPLETE,
    FINAL_SCORE_EVIDENCE_NEUTRAL,
    FINAL_SCORE_EVIDENCE_POSITIVE,
    FINAL_SCORE_EXECUTION_STRONG,
    FINAL_SCORE_SIGNAL_DOMINANT,
)


def test_calculate_final_score_blends_signal_evidence_and_execution_layers():
    result = calculate_final_score(80, 70, 90)

    assert result["final_score"] == 80
    assert result["score_inputs"] == {
        "signal_score": 80,
        "evidence_score": 70,
        "execution_quality_score": 90,
    }
    assert result["weighted_components"] == {
        "signal_score": 52.0,
        "evidence_score": 14.0,
        "execution_quality_score": 13.5,
    }
    assert FINAL_SCORE_SIGNAL_DOMINANT in result["reason_codes"]
    assert FINAL_SCORE_EVIDENCE_POSITIVE in result["reason_codes"]
    assert FINAL_SCORE_EXECUTION_STRONG in result["reason_codes"]


def test_calculate_final_score_uses_safe_fallbacks_for_dirty_inputs():
    result = calculate_final_score(None, "bad", "nan")

    assert result["final_score"] == 25
    assert result["score_inputs"] == {
        "signal_score": 0,
        "evidence_score": 50,
        "execution_quality_score": 100,
    }
    assert FINAL_SCORE_DATA_INCOMPLETE in result["warning_codes"]
    assert FINAL_SCORE_EVIDENCE_NEUTRAL in result["warning_codes"]


def test_calculate_final_score_from_payload_uses_side_specific_precedence():
    payload = {
        "signal_score": 10,
        "best_score": 20,
        "scenario_scores": {
            "buy": {"signal_score": 88},
            "sell": {"total": 45},
        },
        "evidence": {"evidence_score": 65},
        "execution_quality": {"execution_quality_score": 75},
    }

    result = calculate_final_score_from_payload(payload, side="buy")

    assert result["score_inputs"]["signal_score"] == 88
    assert result["score_inputs"]["evidence_score"] == 65
    assert result["score_inputs"]["execution_quality_score"] == 75
    assert result["score_breakdown"]["source"] == "payload"
    assert result["score_breakdown"]["side"] == "buy"


def test_calculate_final_score_batch_keeps_safe_result_for_bad_items():
    results = calculate_final_score_batch([{"signal_score": 80}, None])

    assert len(results) == 2
    assert results[0]["reason"] == "final_score_calculated"
    assert results[1]["reason"] == "batch_item_not_a_dict"
    assert FINAL_SCORE_DATA_INCOMPLETE in results[1]["warning_codes"]
