"""Phase 10.5: verify expectancy-to-evidence-score mapping."""

from __future__ import annotations

from core.statistical_edge_engine import clamp_score, map_expectancy_to_score


class TestClampScore:

    def test_within_range(self):
        assert clamp_score(50.0) == 50
        assert clamp_score(0.0) == 0
        assert clamp_score(100.0) == 100

    def test_below_min(self):
        assert clamp_score(-10.0) == 0

    def test_above_max(self):
        assert clamp_score(150.0) == 100

    def test_custom_range(self):
        assert clamp_score(30.0, 35, 65) == 35
        assert clamp_score(70.0, 35, 65) == 65
        assert clamp_score(50.0, 35, 65) == 50


class TestMapExpectancyToScore:

    # -- insufficient samples --
    def test_small_sample_returns_50_even_with_good_expectancy(self):
        assert map_expectancy_to_score(0.8, 10) == 50

    def test_small_sample_returns_50_even_with_bad_expectancy(self):
        assert map_expectancy_to_score(-0.5, 10) == 50

    def test_none_expectancy_returns_50(self):
        assert map_expectancy_to_score(None, 50) == 50

    # -- strong positive (sample_size >= 30) --
    def test_0_50_expectancy_returns_85(self):
        assert map_expectancy_to_score(0.50, 30) == 85

    def test_0_30_expectancy_returns_75(self):
        assert map_expectancy_to_score(0.30, 30) == 75

    def test_0_15_expectancy_returns_65(self):
        assert map_expectancy_to_score(0.15, 30) == 65

    def test_very_high_expectancy_returns_85(self):
        assert map_expectancy_to_score(1.5, 30) == 85

    # -- near zero (sample_size >= 30) --
    def test_zero_expectancy_returns_near_50(self):
        score = map_expectancy_to_score(0.0, 30)
        assert 35 <= score <= 65
        assert score == 50  # 50 + 0*100 = 50

    def test_slightly_positive_returns_between_50_and_65(self):
        score = map_expectancy_to_score(0.10, 30)
        assert score == 60  # 50 + 10 = 60

    def test_slightly_negative_returns_between_35_and_50(self):
        score = map_expectancy_to_score(-0.10, 30)
        assert score == 40  # 50 - 10 = 40

    # -- negative --
    def test_negative_0_15_returns_35(self):
        assert map_expectancy_to_score(-0.15, 30) == 35

    def test_negative_0_30_returns_20(self):
        assert map_expectancy_to_score(-0.30, 30) == 20

    def test_very_negative_returns_20(self):
        assert map_expectancy_to_score(-1.0, 30) == 20

    # -- boundary: exactly at MIN_SAMPLE_SIZE --
    def test_at_min_sample_size_works(self):
        assert map_expectancy_to_score(0.50, 30) == 85
        assert map_expectancy_to_score(0.30, 30) == 75
