"""Phase 13.2 — test import and basic behaviour of core/final_score_engine.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.final_score_engine import (
    DEFAULT_FINAL_SCORE_WEIGHTS,
    DEFAULT_SIGNAL_SCORE,
    DEFAULT_EVIDENCE_SCORE,
    DEFAULT_EXECUTION_QUALITY_SCORE,
    MIN_FINAL_SCORE,
    MAX_FINAL_SCORE,
    clamp_score,
    calculate_final_score,
    default_final_score_result,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_weights_sum_to_one():
    """DEFAULT_FINAL_SCORE_WEIGHTS must sum to ~1.0."""
    total = sum(DEFAULT_FINAL_SCORE_WEIGHTS.values())
    assert abs(total - 1.0) < 0.001, f"Weights sum to {total}, expected 1.0"


def test_default_constants_reasonable():
    """Default constants are within valid ranges."""
    assert 0 <= DEFAULT_SIGNAL_SCORE <= 100
    assert 0 <= DEFAULT_EVIDENCE_SCORE <= 100
    assert 0 <= DEFAULT_EXECUTION_QUALITY_SCORE <= 100
    assert MIN_FINAL_SCORE == 0
    assert MAX_FINAL_SCORE == 100


# ---------------------------------------------------------------------------
# clamp_score
# ---------------------------------------------------------------------------


def test_clamp_score_int_in_range():
    assert clamp_score(50) == 50
    assert clamp_score(0) == 0
    assert clamp_score(100) == 100


def test_clamp_score_above_max():
    assert clamp_score(120) == 100
    assert clamp_score(999) == 100


def test_clamp_score_below_min():
    assert clamp_score(-5) == 0
    assert clamp_score(-100) == 0


def test_clamp_score_float_rounds():
    assert clamp_score(72.5) == 72
    assert clamp_score(72.6) == 73
    assert clamp_score(99.4) == 99
    assert clamp_score(99.5) == 100


def test_clamp_score_numeric_string():
    assert clamp_score("72.5") == 72
    assert clamp_score("0") == 0
    assert clamp_score("100") == 100


def test_clamp_score_non_numeric():
    assert clamp_score("abc") == 0
    assert clamp_score("") == 0
    assert clamp_score(None) == 0


def test_clamp_score_nan_inf():
    assert clamp_score(float("nan")) == 0
    assert clamp_score(float("inf")) == 0
    assert clamp_score(float("-inf")) == 0


# ---------------------------------------------------------------------------
# default_final_score_result
# ---------------------------------------------------------------------------


def test_default_result_keys():
    result = default_final_score_result()
    assert result["final_score"] == 0
    assert isinstance(result["score_inputs"], dict)
    assert isinstance(result["score_weights"], dict)
    assert isinstance(result["warning_codes"], list)
    assert len(result["warning_codes"]) >= 1
    assert result["reason"] == "final_score_not_calculated"


def test_default_result_custom_reason():
    result = default_final_score_result("missing_input")
    assert result["reason"] == "missing_input"
    assert result["final_score"] == 0


# ---------------------------------------------------------------------------
# calculate_final_score
# ---------------------------------------------------------------------------


def test_calculate_with_valid_scores():
    result = calculate_final_score(80, 75, 90)
    expected = int(round(80 * 0.65 + 75 * 0.20 + 90 * 0.15))
    assert result["final_score"] == expected
    assert result["score_inputs"]["signal_score"] == 80
    assert result["score_inputs"]["evidence_score"] == 75
    assert result["score_inputs"]["execution_quality_score"] == 90
    assert "signal_score" in result["weighted_components"]


def test_calculate_with_none_falls_back():
    result = calculate_final_score(None, None, None)
    expected = int(round(
        DEFAULT_SIGNAL_SCORE * 0.65
        + DEFAULT_EVIDENCE_SCORE * 0.20
        + DEFAULT_EXECUTION_QUALITY_SCORE * 0.15
    ))
    assert result["final_score"] == expected


def test_calculate_clamps_to_100():
    result = calculate_final_score(200, 200, 200)
    assert result["final_score"] == 100


def test_calculate_clamps_to_0():
    result = calculate_final_score(-100, -100, -100)
    assert result["final_score"] == 0


def test_calculate_returns_reason_codes():
    result = calculate_final_score(80, 75, 90)
    assert isinstance(result["reason_codes"], list)
    assert isinstance(result["penalty_codes"], list)
    assert isinstance(result["warning_codes"], list)
    assert isinstance(result["score_breakdown"], dict)


def test_calculate_string_inputs():
    result = calculate_final_score("80", "75", "90")
    expected = int(round(80 * 0.65 + 75 * 0.20 + 90 * 0.15))
    assert result["final_score"] == expected
    assert result["score_inputs"]["signal_score"] == 80
    assert result["score_inputs"]["evidence_score"] == 75
    assert result["score_inputs"]["execution_quality_score"] == 90


def test_calculate_custom_weights():
    custom = {"signal_score": 0.50, "evidence_score": 0.30, "execution_quality_score": 0.20}
    result = calculate_final_score(80, 75, 90, weights=custom)
    expected = int(round(80 * 0.50 + 75 * 0.30 + 90 * 0.20))
    assert result["final_score"] == expected
    assert result["score_weights"] == custom
