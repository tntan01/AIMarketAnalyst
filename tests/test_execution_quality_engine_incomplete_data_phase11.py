"""Phase 11.7: verify incomplete data handling in execution quality."""

from __future__ import annotations

from core.execution_quality_engine import calculate_execution_quality


class TestIncompleteData:
    def test_trade_with_only_symbol_and_result_r(self):
        """Old journal entries with no execution data must not be penalized."""
        trade = {"symbol": "EUR/USD", "direction": "buy", "result_r": 1.0, "closed_at": "2026-01-01T10:00:00"}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 100
        assert "EXECUTION_DATA_INCOMPLETE" in result["warning_codes"]
        assert result["score_breakdown"]["data_complete"] is False

    def test_trade_with_explicit_false_flag_is_complete(self):
        trade = {"chased_price": False}
        result = calculate_execution_quality(trade)
        assert result["score_breakdown"]["data_complete"] is True
        assert "EXECUTION_DATA_INCOMPLETE" not in result["warning_codes"]
        assert result["execution_quality_score"] == 100

    def test_trade_with_explicit_true_flag_is_complete(self):
        trade = {"chased_price": True}
        result = calculate_execution_quality(trade)
        assert result["score_breakdown"]["data_complete"] is True
        assert "EXECUTION_DATA_INCOMPLETE" not in result["warning_codes"]

    def test_trade_with_manual_mistake_tags_empty_list(self):
        """Empty list in mistake_tags still means execution data was checked."""
        trade = {"manual_mistake_tags": []}
        result = calculate_execution_quality(trade)
        assert result["score_breakdown"]["data_complete"] is True
        assert "EXECUTION_DATA_INCOMPLETE" not in result["warning_codes"]

    def test_trade_with_auto_mistake_tags_is_complete(self):
        trade = {"auto_mistake_tags": ["chased_price"]}
        result = calculate_execution_quality(trade)
        assert result["score_breakdown"]["data_complete"] is True

    def test_trade_with_manual_penalty_points_is_complete(self):
        trade = {"manual_penalty_points": 10}
        result = calculate_execution_quality(trade)
        assert result["score_breakdown"]["data_complete"] is True

    def test_trade_none_is_incomplete(self):
        result = calculate_execution_quality(None)
        assert "EXECUTION_DATA_INCOMPLETE" in result["warning_codes"]
        assert result["score_breakdown"]["data_complete"] is False

    def test_empty_dict_is_incomplete(self):
        result = calculate_execution_quality({})
        assert result["execution_quality_score"] == 100
        assert "EXECUTION_DATA_INCOMPLETE" in result["warning_codes"]
        assert result["score_breakdown"]["data_complete"] is False

    def test_data_incomplete_still_scores_100(self):
        """Score stays 100 — incomplete data is a warning, not a penalty."""
        trade = {"symbol": "EUR/USD"}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 100
