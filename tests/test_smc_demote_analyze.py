"""Synthetic tests for the SD-C3 analysis helpers (no data/, no MT5)."""

from __future__ import annotations

import pytest

from scripts.smc_demote_analyze import (
    SEED,
    auc,
    bootstrap_clusters,
    current_score,
    no_smc_score,
    select_side,
    spearman,
)


def test_auc_mann_whitney() -> None:
    assert auc([1, 2, 3, 4], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert auc([1, 2, 3, 4], [1, 1, 0, 0]) == pytest.approx(0.0)
    assert auc([1, 1, 1, 1], [0, 0, 1, 1]) == pytest.approx(0.5)
    assert auc([1, 2, 3], [1, 1, 1]) is None
    assert auc([1, 2, 3], [0, 0, 0]) is None


def test_spearman_with_ties() -> None:
    xs = [1, 2, 2, 3, 4]
    ys = [2, 1, 3, 3, 5]
    assert spearman(xs, ys) == pytest.approx(0.7631578947368421)
    assert spearman([1, 2], [1, 2]) is None


def test_current_score_matches_hand_computation() -> None:
    score = current_score("trending_up", trend=20, momentum=10, location=12, smc_raw=8)
    assert score == 62
    assert current_score("trending_up", 20, 10, 12, None) is None


def test_no_smc_score_is_round_half_up() -> None:
    score = no_smc_score("trending_up", trend=20, momentum=10, location=12)
    assert score == 65


def test_select_side_tie_is_buy_and_gap_floor() -> None:
    assert select_side(62, 62) == ("buy", 0, False)
    assert select_side(62, 58) == ("buy", 4, False)
    assert select_side(62, 57) == ("buy", 5, True)
    assert select_side(40, 55) == ("sell", 15, True)
    assert select_side(None, 55) == (None, None, False)


def test_bootstrap_clusters_is_deterministic_and_cluster_drawn() -> None:
    day_items = {
        "d1": [1.0, 1.0, 1.0],
        "d2": [2.0, 2.0, 2.0],
    }
    lengths: list[int] = []

    def stat(items: list[float]) -> float | None:
        lengths.append(len(items))
        return sum(items) / len(items)

    low_a, high_a, valid_a = bootstrap_clusters(day_items, stat, seed=SEED, n=200)
    assert low_a is not None and high_a is not None
    assert all(length % 3 == 0 for length in lengths)
    assert all(length in (3, 6) for length in lengths)

    low_b, high_b, valid_b = bootstrap_clusters(day_items, stat, seed=SEED, n=200)
    assert (low_a, high_a, valid_a) == (low_b, high_b, valid_b)
