"""Phase 10.4: verify trade statistics calculation."""

from __future__ import annotations

from math import isclose

from core.statistical_edge_engine import calculate_trade_stats


class TestCalculateTradeStats:

    # Dataset 1: realistic mixed results
    # wins: 1.5, 2.0, 0.5, 1.0, 1.2 = sum 6.2 / 5 = 1.24
    # losses: -1.0, -1.0, -0.5, 0.0, -1.0 = sum -3.5, abs avg = 0.7
    # win_rate = 0.5, expectancy = 0.5*1.24 - 0.5*0.7 = 0.62 - 0.35 = 0.27
    _RESULTS: list[float] = [1.5, -1.0, 2.0, -1.0, 0.5, -0.5, 0.0, 1.0, -1.0, 1.2]

    def test_sample_size(self):
        stats = calculate_trade_stats(self._RESULTS)
        assert stats["sample_size"] == 10

    def test_win_count(self):
        stats = calculate_trade_stats(self._RESULTS)
        assert stats["win_count"] == 5  # 1.5, 2.0, 0.5, 1.0, 1.2

    def test_loss_count(self):
        stats = calculate_trade_stats(self._RESULTS)
        # -1.0, -1.0, -0.5, 0.0, -1.0 = 5 (breakeven counted as loss)
        assert stats["loss_count"] == 5

    def test_win_rate(self):
        stats = calculate_trade_stats(self._RESULTS)
        assert stats["win_rate"] == 0.5

    def test_avg_win_r(self):
        stats = calculate_trade_stats(self._RESULTS)
        expected = (1.5 + 2.0 + 0.5 + 1.0 + 1.2) / 5  # 1.24
        assert isclose(stats["avg_win_r"], expected)

    def test_avg_loss_r(self):
        stats = calculate_trade_stats(self._RESULTS)
        expected = abs((-1.0 - 1.0 - 0.5 + 0.0 - 1.0) / 5)  # 0.7
        assert isclose(stats["avg_loss_r"], expected)

    def test_expectancy_r(self):
        stats = calculate_trade_stats(self._RESULTS)
        expected = 0.5 * 1.24 - 0.5 * 0.7  # 0.27
        assert isclose(stats["expectancy_r"], expected)

    # Dataset 2: empty
    def test_empty_list_no_crash(self):
        stats = calculate_trade_stats([])
        assert stats["sample_size"] == 0
        assert stats["win_count"] == 0
        assert stats["loss_count"] == 0
        assert stats["win_rate"] is None
        assert stats["expectancy_r"] is None

    # Edge cases
    def test_all_wins(self):
        stats = calculate_trade_stats([1.0, 2.0, 0.5])
        assert stats["sample_size"] == 3
        assert stats["win_count"] == 3
        assert stats["loss_count"] == 0
        assert stats["win_rate"] == 1.0
        assert stats["avg_loss_r"] == 0.0
        assert stats["expectancy_r"] == (1.0 + 2.0 + 0.5) / 3  # all wins = avg win

    def test_all_losses(self):
        stats = calculate_trade_stats([-1.0, -2.0, -0.5])
        assert stats["sample_size"] == 3
        assert stats["win_count"] == 0
        assert stats["loss_count"] == 3
        assert stats["win_rate"] == 0.0
        assert stats["avg_win_r"] == 0.0
        assert stats["avg_loss_r"] == (1.0 + 2.0 + 0.5) / 3
        assert stats["expectancy_r"] < 0

    def test_single_trade_win(self):
        stats = calculate_trade_stats([3.0])
        assert stats["win_rate"] == 1.0
        assert stats["avg_win_r"] == 3.0

    def test_single_trade_loss(self):
        stats = calculate_trade_stats([-1.0])
        assert stats["win_rate"] == 0.0
        assert stats["avg_loss_r"] == 1.0
