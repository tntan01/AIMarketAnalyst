from __future__ import annotations

from core.signal_engine import calculate_direction_bias


class TestCalculateDirectionBias:
    """Unit tests for calculate_direction_bias()."""

    def test_buy_clear_bias(self) -> None:
        buy = {"signal_score": 82}
        sell = {"signal_score": 65}
        result = calculate_direction_bias(buy, sell)
        assert result["best_side"] == "buy"
        assert result["buy_score"] == 82
        assert result["sell_score"] == 65
        assert result["score_gap"] == 17
        assert result["is_clear_bias"] is True

    def test_sell_clear_bias(self) -> None:
        buy = {"signal_score": 60}
        sell = {"signal_score": 78}
        result = calculate_direction_bias(buy, sell)
        assert result["best_side"] == "sell"
        assert result["score_gap"] == 18
        assert result["is_clear_bias"] is True

    def test_buy_sell_close(self) -> None:
        buy = {"signal_score": 80}
        sell = {"signal_score": 77}
        result = calculate_direction_bias(buy, sell)
        assert result["best_side"] == "buy"
        assert result["score_gap"] == 3
        assert result["is_clear_bias"] is False

    def test_tie_scores(self) -> None:
        buy = {"signal_score": 70}
        sell = {"signal_score": 70}
        result = calculate_direction_bias(buy, sell)
        assert result["best_side"] == "neutral"
        assert result["score_gap"] == 0
        assert result["is_clear_bias"] is False

    def test_fallback_to_total(self) -> None:
        buy = {"total": 76}
        sell = {"total": 61}
        result = calculate_direction_bias(buy, sell)
        assert result["best_side"] == "buy"
        assert result["buy_score"] == 76
        assert result["sell_score"] == 61
        assert result["score_gap"] == 15
        assert result["is_clear_bias"] is True

    def test_empty_dicts(self) -> None:
        buy: dict = {}
        sell: dict = {}
        result = calculate_direction_bias(buy, sell)
        assert result["best_side"] == "neutral"
        assert result["buy_score"] == 0
        assert result["sell_score"] == 0
        assert result["score_gap"] == 0
        assert result["is_clear_bias"] is False

    def test_none_inputs(self) -> None:
        result = calculate_direction_bias(None, None)
        assert result["best_side"] == "neutral"
        assert result["buy_score"] == 0
        assert result["sell_score"] == 0
        assert result["score_gap"] == 0
        assert result["is_clear_bias"] is False

    def test_signal_score_takes_priority_over_total(self) -> None:
        buy = {"signal_score": 88, "total": 50}
        sell = {"signal_score": 72, "total": 90}
        result = calculate_direction_bias(buy, sell)
        assert result["buy_score"] == 88
        assert result["sell_score"] == 72
        assert result["score_gap"] == 16

    def test_custom_min_gap(self) -> None:
        buy = {"signal_score": 82}
        sell = {"signal_score": 72}
        # Default min_gap=10: 10 >= 10 -> clear
        result_default = calculate_direction_bias(buy, sell)
        assert result_default["is_clear_bias"] is True
        # Custom min_gap=15: 10 < 15 -> not clear
        result_custom = calculate_direction_bias(buy, sell, min_gap=15)
        assert result_custom["is_clear_bias"] is False
        assert result_custom["min_gap"] == 15

    def test_output_has_all_required_keys(self) -> None:
        buy = {"signal_score": 80}
        sell = {"signal_score": 60}
        result = calculate_direction_bias(buy, sell)
        assert set(result.keys()) == {"best_side", "buy_score", "sell_score", "score_gap", "is_clear_bias", "min_gap"}

    def test_sell_bias_edge(self) -> None:
        buy = {"signal_score": 45}
        sell = {"signal_score": 77}
        result = calculate_direction_bias(buy, sell)
        assert result["best_side"] == "sell"
        assert result["score_gap"] == 32
        assert result["is_clear_bias"] is True

    def test_buy_bias_exact_threshold(self) -> None:
        buy = {"signal_score": 75}
        sell = {"signal_score": 65}
        result = calculate_direction_bias(buy, sell)
        assert result["score_gap"] == 10
        assert result["is_clear_bias"] is True  # 10 >= 10

    def test_buy_bias_just_below_threshold(self) -> None:
        buy = {"signal_score": 74}
        sell = {"signal_score": 65}
        result = calculate_direction_bias(buy, sell, min_gap=10.0)
        assert result["score_gap"] == 9
        assert result["is_clear_bias"] is False
