"""Phase 11.6: verify manual penalty support in execution quality."""

from __future__ import annotations

from core.execution_quality_engine import calculate_execution_quality


class TestManualPenaltyPoints:
    def test_manual_10_points_scores_90(self):
        trade = {"manual_penalty_points": 10}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 90
        assert "EXECUTION_MANUAL_PENALTY" in result["penalty_codes"]
        assert result["score_breakdown"]["total_penalty"] == 10

    def test_manual_points_capped_at_50(self):
        trade = {"manual_penalty_points": 999}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 50  # 100 - 50
        assert result["score_breakdown"]["total_penalty"] == 50

    def test_manual_execution_penalty_alias(self):
        trade = {"manual_execution_penalty": 20}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 80
        assert result["score_breakdown"]["total_penalty"] == 20

    def test_manual_points_string(self):
        trade = {"manual_penalty_points": "15"}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 85

    def test_manual_points_negative_converted(self):
        trade = {"manual_penalty_points": -20}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 80  # abs(-20) = 20

    def test_manual_points_garbage_no_crash(self):
        trade = {"manual_penalty_points": "abc"}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 100

    def test_manual_points_zero_ignored(self):
        trade = {"manual_penalty_points": 0}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 100
        # Manual 0 points shouldn't generate a penalty item
        assert "EXECUTION_MANUAL_PENALTY" not in result["penalty_codes"]


class TestManualMistakeTags:
    def test_manual_tag_chased_price(self):
        trade = {"manual_mistake_tags": ["chased_price"]}
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 75
        assert "EXECUTION_CHASED_PRICE" in result["penalty_codes"]

    def test_manual_and_auto_same_tag_deduct_once(self):
        trade = {
            "manual_mistake_tags": ["chased_price"],
            "auto_mistake_tags": ["chased_price"],
        }
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 75  # 25, not 50
        assert result["penalty_codes"].count("EXECUTION_CHASED_PRICE") == 1


class TestManualCombined:
    def test_manual_points_plus_tag(self):
        trade = {
            "manual_penalty_points": 10,
            "manual_mistake_tags": ["oversized_position"],
        }
        result = calculate_execution_quality(trade)
        # 10 (manual) + 30 (oversized) = 40, score = 60
        assert result["execution_quality_score"] == 60
        assert "EXECUTION_MANUAL_PENALTY" in result["penalty_codes"]
        assert "EXECUTION_OVERSIZED" in result["penalty_codes"]
        assert len(result["penalty_codes"]) == 2
