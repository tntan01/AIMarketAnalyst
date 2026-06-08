"""Phase 10.2: verify statistical_edge_engine module imports and basics."""

from __future__ import annotations

from core.statistical_edge_engine import (
    DEFAULT_EVIDENCE_SCORE,
    MIN_SAMPLE_SIZE,
    STRONG_SAMPLE_SIZE,
    neutral_evidence_result,
)


class TestStatisticalEdgeEngineImport:

    def test_default_evidence_score_is_50(self):
        assert DEFAULT_EVIDENCE_SCORE == 50

    def test_min_sample_size_is_30(self):
        assert MIN_SAMPLE_SIZE == 30

    def test_strong_sample_size_is_50(self):
        assert STRONG_SAMPLE_SIZE == 50

    def test_neutral_result_returns_score_50(self):
        result = neutral_evidence_result()
        assert result["evidence_score"] == 50

    def test_neutral_result_has_not_enough_data_code(self):
        result = neutral_evidence_result()
        assert "STAT_EDGE_NOT_ENOUGH_DATA" in result["reason_codes"]
        assert "STAT_EDGE_NOT_ENOUGH_DATA" in result["warning_codes"]

    def test_neutral_result_sample_size_zero(self):
        result = neutral_evidence_result()
        assert result["sample_size"] == 0

    def test_neutral_result_confidence_low(self):
        result = neutral_evidence_result()
        assert result["confidence"] == "low"

    def test_neutral_result_stats_all_none(self):
        result = neutral_evidence_result()
        s = result["stats"]
        assert s["win_rate"] is None
        assert s["avg_win_r"] is None
        assert s["avg_loss_r"] is None
        assert s["expectancy_r"] is None

    def test_neutral_result_group_used_none(self):
        result = neutral_evidence_result()
        assert result["group_used"] is None

    def test_neutral_result_custom_reason(self):
        result = neutral_evidence_result(reason="custom reason")
        assert result["reason"] == "custom reason"
