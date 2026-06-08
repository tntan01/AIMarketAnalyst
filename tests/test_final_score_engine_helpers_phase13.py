"""Phase 13.3 — test helper functions in core/final_score_engine.py."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.final_score_engine import (
    DEFAULT_FINAL_SCORE_WEIGHTS,
    DEFAULT_SIGNAL_SCORE,
    DEFAULT_EVIDENCE_SCORE,
    DEFAULT_EXECUTION_QUALITY_SCORE,
    safe_score,
    normalize_weights,
    weighted_component,
    build_score_inputs,
)


# ---------------------------------------------------------------------------
# safe_score
# ---------------------------------------------------------------------------


def test_safe_score_valid_int():
    assert safe_score(80) == 80
    assert safe_score(0) == 0
    assert safe_score(100) == 100


def test_safe_score_out_of_range():
    assert safe_score(150) == 100
    assert safe_score(-10) == 0


def test_safe_score_numeric_string():
    assert safe_score("80") == 80
    assert safe_score("0") == 0
    assert safe_score("100") == 100


def test_safe_score_bad_string_returns_default():
    assert safe_score("abc", default=50) == 50
    assert safe_score("") == 0


def test_safe_score_none_returns_default():
    assert safe_score(None, default=50) == 50
    assert safe_score(None) == 0


def test_safe_score_nan_inf():
    assert safe_score(float("nan"), default=50) == 50
    assert safe_score(float("inf")) == 0
    assert safe_score(float("-inf"), default=50) == 50


def test_safe_score_default_clamped():
    # default outside 0–100 gets clamped
    assert safe_score(None, default=150) == 100
    assert safe_score(None, default=-10) == 0


# ---------------------------------------------------------------------------
# normalize_weights
# ---------------------------------------------------------------------------


def test_normalize_weights_none():
    result = normalize_weights(None)
    assert abs(sum(result.values()) - 1.0) < 0.001
    assert "signal_score" in result
    assert "evidence_score" in result
    assert "execution_quality_score" in result


def test_normalize_weights_defaults_sum_to_one():
    result = normalize_weights()
    total = sum(result.values())
    assert abs(total - 1.0) < 0.001


def test_normalize_weights_custom_normalizes():
    # 2:1:1 → 0.5:0.25:0.25
    result = normalize_weights({
        "signal_score": 2,
        "evidence_score": 1,
        "execution_quality_score": 1,
    })
    total = sum(result.values())
    assert abs(total - 1.0) < 0.001
    assert abs(result["signal_score"] - 0.5) < 0.001
    assert abs(result["evidence_score"] - 0.25) < 0.001
    assert abs(result["execution_quality_score"] - 0.25) < 0.001


def test_normalize_weights_partial_fills_missing():
    result = normalize_weights({"signal_score": 1.0})
    total = sum(result.values())
    assert abs(total - 1.0) < 0.001
    # The remaining keys should be filled from defaults, then normalized


def test_normalize_weights_negative_falls_back():
    result = normalize_weights({"signal_score": -0.5})
    # Negative weight should fall back to default for that key
    assert result["signal_score"] > 0


def test_normalize_weights_bogus_string_falls_back():
    result = normalize_weights({"signal_score": "abc"})  # type: ignore[dict-item]
    total = sum(result.values())
    assert abs(total - 1.0) < 0.001
    assert result["signal_score"] > 0


def test_normalize_weights_zero_sum_returns_default():
    result = normalize_weights({
        "signal_score": 0,
        "evidence_score": 0,
        "execution_quality_score": 0,
    })
    # All zero → fallback to defaults
    assert result == DEFAULT_FINAL_SCORE_WEIGHTS


def test_normalize_weights_does_not_mutate_input():
    original = {"signal_score": 2, "evidence_score": 1, "execution_quality_score": 1}
    copied = dict(original)
    normalize_weights(original)
    assert original == copied


def test_normalize_weights_extra_keys_ignored():
    result = normalize_weights({
        "signal_score": 1,
        "evidence_score": 1,
        "execution_quality_score": 1,
        "extra_junk": 999,
    })
    assert "extra_junk" not in result
    assert abs(sum(result.values()) - 1.0) < 0.001


# ---------------------------------------------------------------------------
# weighted_component
# ---------------------------------------------------------------------------


def test_weighted_component_basic():
    assert weighted_component(80, 0.5) == 40.0


def test_weighted_component_zero_weight():
    assert weighted_component(80, 0.0) == 0.0


def test_weighted_component_score_out_of_range():
    assert weighted_component(150, 1.0) == 100.0


def test_weighted_component_negative_weight():
    assert weighted_component(80, -0.5) == 0.0


def test_weighted_component_nan_weight():
    assert weighted_component(80, float("nan")) == 0.0


# ---------------------------------------------------------------------------
# build_score_inputs
# ---------------------------------------------------------------------------


def test_build_score_inputs_defaults():
    result = build_score_inputs(None, None, None)
    assert result == {
        "signal_score": DEFAULT_SIGNAL_SCORE,
        "evidence_score": DEFAULT_EVIDENCE_SCORE,
        "execution_quality_score": DEFAULT_EXECUTION_QUALITY_SCORE,
    }


def test_build_score_inputs_custom():
    result = build_score_inputs(80, 75, 90)
    assert result == {
        "signal_score": 80,
        "evidence_score": 75,
        "execution_quality_score": 90,
    }


def test_build_score_inputs_partial():
    result = build_score_inputs(80, None, None)
    assert result["signal_score"] == 80
    assert result["evidence_score"] == DEFAULT_EVIDENCE_SCORE
    assert result["execution_quality_score"] == DEFAULT_EXECUTION_QUALITY_SCORE


def test_build_score_inputs_bad_values():
    result = build_score_inputs("abc", None, 150)
    assert result["signal_score"] == DEFAULT_SIGNAL_SCORE
    assert result["evidence_score"] == DEFAULT_EVIDENCE_SCORE
    assert result["execution_quality_score"] == 100
