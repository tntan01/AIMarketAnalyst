"""Phase 11.5: verify calculate_execution_quality() basic scoring."""

from __future__ import annotations

from core.execution_quality_engine import calculate_execution_quality


class TestCleanTrade:
    def test_clean_trade_scores_100(self):
        result = calculate_execution_quality({"symbol": "EUR/USD", "result_r": 1.0})
        assert result["execution_quality_score"] == 100
        assert "EXECUTION_QUALITY_OK" in result["reason_codes"]
        assert result["penalty_codes"] == []
        assert result["score_breakdown"]["total_penalty"] == 0


class TestSinglePenalty:
    def test_chased_price_deducts_25(self):
        result = calculate_execution_quality({"chased_price": True})
        assert result["execution_quality_score"] == 75
        assert "EXECUTION_CHASED_PRICE" in result["penalty_codes"]
        assert result["score_breakdown"]["total_penalty"] == 25

    def test_oversized_position_deducts_30(self):
        result = calculate_execution_quality({"oversized_position": True})
        assert result["execution_quality_score"] == 70
        assert "EXECUTION_OVERSIZED" in result["penalty_codes"]
        assert result["score_breakdown"]["total_penalty"] == 30

    def test_moved_sl_further_deducts_30(self):
        result = calculate_execution_quality({"moved_sl_further": True})
        assert result["execution_quality_score"] == 70
        assert "EXECUTION_MOVED_SL_FURTHER" in result["penalty_codes"]
        assert result["score_breakdown"]["total_penalty"] == 30

    def test_revenge_trade_deducts_35(self):
        result = calculate_execution_quality({"revenge_trade": True})
        assert result["execution_quality_score"] == 65
        assert "EXECUTION_REVENGE_CONFIRMED" in result["penalty_codes"]
        assert result["score_breakdown"]["total_penalty"] == 35

    def test_revenge_trade_confirmed_deducts_35(self):
        result = calculate_execution_quality({"revenge_trade_confirmed": True})
        assert result["execution_quality_score"] == 65
        assert "EXECUTION_REVENGE_CONFIRMED" in result["penalty_codes"]


class TestViaTags:
    def test_chased_price_via_tag(self):
        result = calculate_execution_quality({"manual_mistake_tags": ["chased_price"]})
        assert result["execution_quality_score"] == 75
        assert "EXECUTION_CHASED_PRICE" in result["penalty_codes"]

    def test_moved_stop_loss_tag(self):
        result = calculate_execution_quality({"auto_mistake_tags": "moved_stop_loss"})
        assert result["execution_quality_score"] == 70
        assert "EXECUTION_MOVED_SL_FURTHER" in result["penalty_codes"]

    def test_revenge_tag(self):
        result = calculate_execution_quality({"execution_tags": ["revenge_trade"]})
        assert result["execution_quality_score"] == 65


class TestAllPenalties:
    def test_all_four_penalties_scores_zero(self):
        trade = {
            "chased_price": True,
            "oversized_position": True,
            "moved_sl_further": True,
            "revenge_trade_confirmed": True,
        }
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 0
        assert not result["execution_quality_score"] < 0
        # 25+30+30+35 = 120, but clamped at 0
        assert result["score_breakdown"]["total_penalty"] == 120
        assert len(result["penalty_codes"]) == 4


class TestNoDoublePenalty:
    def test_boolean_and_tag_deducts_only_once(self):
        trade = {
            "chased_price": True,
            "manual_mistake_tags": ["chased_price"],
        }
        result = calculate_execution_quality(trade)
        assert result["execution_quality_score"] == 75  # 25, not 50
        assert result["penalty_codes"].count("EXECUTION_CHASED_PRICE") == 1

    def test_two_tags_same_code_deducts_once(self):
        trade = {
            "manual_mistake_tags": ["moved_sl_further", "moved_stop_loss"],
        }
        result = calculate_execution_quality(trade)
        # Both map to EXECUTION_MOVED_SL_FURTHER
        assert result["execution_quality_score"] == 70  # 30, not 60
        assert result["penalty_codes"].count("EXECUTION_MOVED_SL_FURTHER") == 1


class TestNoneTrade:
    def test_none_trade_does_not_crash(self):
        result = calculate_execution_quality(None)
        assert result["execution_quality_score"] == 100
        assert "EXECUTION_DATA_INCOMPLETE" in result["warning_codes"]

    def test_not_a_dict_does_not_crash(self):
        result = calculate_execution_quality("not_a_dict")  # type: ignore[arg-type]
        assert result["execution_quality_score"] == 100
        assert "EXECUTION_DATA_INCOMPLETE" in result["warning_codes"]


class TestOutputStructure:
    def test_has_required_keys(self):
        result = calculate_execution_quality({"chased_price": True})
        for key in ("execution_quality_score", "reason_codes", "penalty_codes",
                     "warning_codes", "score_breakdown"):
            assert key in result
        bd = result["score_breakdown"]
        for key in ("base_score", "total_penalty", "penalties"):
            assert key in bd
