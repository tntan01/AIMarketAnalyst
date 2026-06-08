"""Phase 13.4 — test calculate_final_score() with the Phase 13 initial formula."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.final_score_engine import (
    calculate_final_score,
    FINAL_SCORE_OK,
    FINAL_SCORE_DATA_INCOMPLETE,
    FINAL_SCORE_SIGNAL_DOMINANT,
    FINAL_SCORE_EVIDENCE_NEUTRAL,
    FINAL_SCORE_EVIDENCE_POSITIVE,
    FINAL_SCORE_EVIDENCE_NEGATIVE,
    FINAL_SCORE_EXECUTION_STRONG,
    FINAL_SCORE_EXECUTION_WEAK,
)
from core.reason_codes import (
    FINAL_SCORE_OK as _OK,
    FINAL_SCORE_EVIDENCE_POSITIVE as _EV_POS,
    FINAL_SCORE_EVIDENCE_NEGATIVE as _EV_NEG,
    FINAL_SCORE_EXECUTION_WEAK as _EX_WEAK,
    FINAL_SCORE_DATA_INCOMPLETE as _DATA_INC,
)


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------


def test_calculate_standard_case():
    """signal=80, evidence=50, execution=100 → final=77"""
    result = calculate_final_score(80, 50, 100)
    assert result["final_score"] == 77
    assert FINAL_SCORE_OK in result["reason_codes"]


def test_calculate_evidence_good():
    """Evidence ≥65 gets POSITIVE code."""
    result = calculate_final_score(70, 80, 100)
    expected = round(70 * 0.65 + 80 * 0.20 + 100 * 0.15)
    assert result["final_score"] == expected
    assert FINAL_SCORE_EVIDENCE_POSITIVE in result["reason_codes"]


def test_calculate_evidence_bad_penalty():
    """Evidence ≤40 gets NEGATIVE penalty code."""
    result = calculate_final_score(80, 30, 100)
    expected = round(80 * 0.65 + 30 * 0.20 + 100 * 0.15)
    assert result["final_score"] == expected
    assert FINAL_SCORE_EVIDENCE_NEGATIVE in result["penalty_codes"]


def test_calculate_execution_weak_penalty():
    """Execution <70 gets WEAK penalty code."""
    result = calculate_final_score(80, 50, 40)
    expected = round(80 * 0.65 + 50 * 0.20 + 40 * 0.15)
    assert result["final_score"] == expected
    assert FINAL_SCORE_EXECUTION_WEAK in result["penalty_codes"]


def test_calculate_execution_strong():
    """Execution ≥85 gets STRONG reason code."""
    result = calculate_final_score(70, 50, 85)
    assert FINAL_SCORE_EXECUTION_STRONG in result["reason_codes"]


def test_calculate_evidence_neutral():
    """Evidence == 50 (default) gets NEUTRAL warning."""
    result = calculate_final_score(80, 50, 100)
    assert FINAL_SCORE_EVIDENCE_NEUTRAL in result["warning_codes"]


def test_calculate_signal_dominant():
    """Signal weight is largest → SIGNAL_DOMINANT."""
    result = calculate_final_score(80, 50, 100)
    assert FINAL_SCORE_SIGNAL_DOMINANT in result["reason_codes"]


def test_calculate_all_100():
    result = calculate_final_score(100, 100, 100)
    assert result["final_score"] == 100


def test_calculate_all_zero():
    result = calculate_final_score(0, 0, 0)
    expected = round(0 * 0.65 + 0 * 0.20 + 0 * 0.15)
    assert result["final_score"] == expected


# ---------------------------------------------------------------------------
# Dirty data
# ---------------------------------------------------------------------------


def test_dirty_data_no_crash():
    """Dirty data must not crash."""
    result = calculate_final_score("abc", None, None)
    assert isinstance(result["final_score"], int)
    assert FINAL_SCORE_DATA_INCOMPLETE in result["warning_codes"]


def test_dirty_data_fallback_values():
    """When inputs are dirty, fallback to defaults."""
    result = calculate_final_score("abc", None, None)
    # defaults: signal=0, evidence=50, execution=100
    expected = round(0 * 0.65 + 50 * 0.20 + 100 * 0.15)
    assert result["final_score"] == expected


def test_string_scores_still_valid():
    """Numeric strings are valid input, no DATA_INCOMPLETE."""
    result = calculate_final_score("80", "50", "100")
    assert result["final_score"] == 77
    assert FINAL_SCORE_DATA_INCOMPLETE not in result["warning_codes"]


def test_empty_string_is_dirty():
    """Empty string → fallback → DATA_INCOMPLETE."""
    result = calculate_final_score("", 50, 100)
    assert FINAL_SCORE_DATA_INCOMPLETE in result["warning_codes"]


def test_none_signal_is_dirty():
    result = calculate_final_score(None, 50, 100)
    assert FINAL_SCORE_DATA_INCOMPLETE in result["warning_codes"]


# ---------------------------------------------------------------------------
# Custom weights
# ---------------------------------------------------------------------------


def test_custom_weights():
    custom = {"signal_score": 0.50, "evidence_score": 0.25, "execution_quality_score": 0.25}
    result = calculate_final_score(80, 50, 100, weights=custom)
    expected = round(80 * 0.50 + 50 * 0.25 + 100 * 0.25)
    assert result["final_score"] == expected
    assert abs(result["score_weights"]["signal_score"] - 0.50) < 0.001


def test_custom_weights_no_normalize_needed():
    """Weights already sum to 1.0 should stay unchanged."""
    custom = {"signal_score": 0.50, "evidence_score": 0.30, "execution_quality_score": 0.20}
    result = calculate_final_score(80, 50, 100, weights=custom)
    assert abs(result["score_weights"]["signal_score"] - 0.50) < 0.001
    assert abs(result["score_weights"]["evidence_score"] - 0.30) < 0.001
    assert abs(result["score_weights"]["execution_quality_score"] - 0.20) < 0.001


# ---------------------------------------------------------------------------
# Output format
# ---------------------------------------------------------------------------


def test_output_has_all_required_keys():
    result = calculate_final_score(80, 50, 100)
    assert "final_score" in result
    assert "score_inputs" in result
    assert "score_weights" in result
    assert "weighted_components" in result
    assert "reason_codes" in result
    assert "penalty_codes" in result
    assert "warning_codes" in result
    assert "score_breakdown" in result
    assert "reason" in result


def test_weighted_components_keys():
    result = calculate_final_score(80, 50, 100)
    wc = result["weighted_components"]
    assert "signal_score" in wc
    assert "evidence_score" in wc
    assert "execution_quality_score" in wc


def test_score_breakdown_has_formula():
    result = calculate_final_score(80, 50, 100)
    sb = result["score_breakdown"]
    assert "raw_final_score" in sb
    assert "formula" in sb


def test_no_duplicate_codes():
    """reason/penalty/warning codes must not contain duplicates."""
    result = calculate_final_score(80, 35, 40)
    reasons = result["reason_codes"]
    penalties = result["penalty_codes"]
    warnings = result["warning_codes"]
    assert len(reasons) == len(set(reasons))
    assert len(penalties) == len(set(penalties))
    assert len(warnings) == len(set(warnings))


def test_final_score_is_int():
    result = calculate_final_score(80, 50, 100)
    assert isinstance(result["final_score"], int)


def test_clamp_above_100():
    result = calculate_final_score(200, 200, 200)
    assert result["final_score"] == 100
