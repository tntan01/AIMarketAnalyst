"""Phase 11.2: verify execution_quality_engine module imports and defaults."""

from __future__ import annotations

from core.execution_quality_engine import (
    DEFAULT_EXECUTION_QUALITY_SCORE,
    MAX_EXECUTION_QUALITY_SCORE,
    MIN_EXECUTION_QUALITY_SCORE,
    clamp_score,
    default_execution_quality_result,
)


class TestExecutionQualityEngineImport:

    def test_default_score_is_100(self):
        assert DEFAULT_EXECUTION_QUALITY_SCORE == 100

    def test_min_max_bounds(self):
        assert MIN_EXECUTION_QUALITY_SCORE == 0
        assert MAX_EXECUTION_QUALITY_SCORE == 100

    def test_default_result_score_is_100(self):
        result = default_execution_quality_result()
        assert result["execution_quality_score"] == 100

    def test_default_result_has_quality_ok_code(self):
        result = default_execution_quality_result()
        assert "EXECUTION_QUALITY_OK" in result["reason_codes"]

    def test_default_result_penalty_codes_empty(self):
        result = default_execution_quality_result()
        assert result["penalty_codes"] == []

    def test_default_result_warning_codes_empty(self):
        result = default_execution_quality_result()
        assert result["warning_codes"] == []

    def test_default_result_has_score_breakdown(self):
        result = default_execution_quality_result()
        assert "score_breakdown" in result

    def test_default_result_custom_reason(self):
        result = default_execution_quality_result(reason="test")
        assert result["reason"] == "test"


class TestClampScore:
    def test_within_range(self):
        assert clamp_score(80) == 80

    def test_clamps_above_max(self):
        assert clamp_score(120) == 100
        assert clamp_score(200, 0, 100) == 100

    def test_clamps_below_min(self):
        assert clamp_score(-5) == 0
        assert clamp_score(-10, 0, 100) == 0

    def test_parses_string(self):
        assert clamp_score("80") == 80
        assert clamp_score(" 95 ") == 95

    def test_float_rounded(self):
        assert clamp_score(75.6) == 76
        assert clamp_score(75.4) == 75

    def test_none_returns_min(self):
        assert clamp_score(None) == 0

    def test_nan_returns_min(self):
        assert clamp_score(float("nan")) == 0

    def test_inf_returns_max(self):
        assert clamp_score(float("inf")) == 100
        assert clamp_score(float("-inf")) == 0

    def test_garbage_string_returns_min(self):
        assert clamp_score("abc") == 0

    def test_custom_range(self):
        assert clamp_score(50, 35, 65) == 50
        assert clamp_score(10, 35, 65) == 35
        assert clamp_score(80, 35, 65) == 65
