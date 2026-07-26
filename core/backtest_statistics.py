"""Pure statistical evidence for backtest validation."""

from __future__ import annotations

import hashlib
import math
import random
from statistics import mean, median, pstdev
from typing import Any, Iterable


BACKTEST_STATISTICS_VERSION = "backtest-statistics-v1"
DEFAULT_BOOTSTRAP_SAMPLES = 2000
DEFAULT_PERMUTATION_SAMPLES = 2000
MIN_BOOTSTRAP_PROBABILITY_POSITIVE_PCT = 95.0
MAX_ONE_SIDED_P_VALUE = 0.05


def bootstrap_trade_uncertainty(
    values: Iterable[float],
    *,
    samples: int = DEFAULT_BOOTSTRAP_SAMPLES,
    seed_material: str = "",
) -> dict[str, Any]:
    """Bootstrap trades with replacement for uncertainty distributions."""

    observed = [float(value) for value in values if math.isfinite(float(value))]
    count = max(10, int(samples))
    if not observed:
        return _empty_bootstrap(count)
    rng = random.Random(_seed(observed, seed_material, "bootstrap"))
    size = len(observed)
    expectancy: list[float] = []
    profit_factor: list[float] = []
    win_rate: list[float] = []
    for _ in range(count):
        sample = [observed[rng.randrange(size)] for _ in range(size)]
        expectancy.append(sum(sample) / size)
        profit_factor.append(_profit_factor(sample))
        win_rate.append(sum(value > 0 for value in sample) / size * 100.0)

    non_positive = sum(value <= 0 for value in expectancy)
    probability_positive = (count - non_positive) / count * 100.0
    required = required_sample_size_for_positive_edge(observed)
    return {
        "version": BACKTEST_STATISTICS_VERSION,
        "method": "BOOTSTRAP_WITH_REPLACEMENT",
        "sample_size": size,
        "simulation_count": count,
        "expectancy_r": distribution(expectancy),
        "profit_factor": distribution(profit_factor),
        "win_rate": distribution(win_rate),
        "probability_positive_edge_pct": round(probability_positive, 2),
        "probability_non_positive_edge_pct": round(
            non_positive / count * 100.0,
            2,
        ),
        "one_sided_p_value": round(non_positive / count, 4),
        "minimum_required_trades": required,
        "statistical_power_passed": size >= required,
    }


def permutation_sequence_risk(
    values: Iterable[float],
    *,
    samples: int = DEFAULT_PERMUTATION_SAMPLES,
    seed_material: str = "",
    drawdown_threshold_r: float = 10.0,
) -> dict[str, Any]:
    """Permute order only for path-dependent drawdown/streak risk."""

    observed = [float(value) for value in values if math.isfinite(float(value))]
    count = max(10, int(samples))
    if not observed:
        return _empty_permutation(count, drawdown_threshold_r)
    rng = random.Random(_seed(observed, seed_material, "permutation"))
    drawdowns: list[float] = []
    loss_streaks: list[int] = []
    for _ in range(count):
        shuffled = list(observed)
        rng.shuffle(shuffled)
        drawdown, streak = _sequence_risk(shuffled)
        drawdowns.append(drawdown)
        loss_streaks.append(streak)
    return {
        "version": BACKTEST_STATISTICS_VERSION,
        "method": "PERMUTATION_WITHOUT_REPLACEMENT",
        "sample_size": len(observed),
        "simulation_count": count,
        "max_drawdown_r": distribution(drawdowns),
        "max_consecutive_losses": {
            "mean": round(mean(loss_streaks), 2),
            "median": round(median(loss_streaks), 2),
            "p95_high": round(percentile(loss_streaks, 97.5), 2),
        },
        "drawdown_threshold_r": float(drawdown_threshold_r),
        "probability_drawdown_exceeds_threshold_pct": round(
            sum(value > drawdown_threshold_r for value in drawdowns)
            / count
            * 100.0,
            2,
        ),
        "invariant_metrics": ["expectancy_r", "profit_factor", "win_rate"],
    }


def required_sample_size_for_positive_edge(values: Iterable[float]) -> int:
    """Estimate one-sided sample need from observed effect and dispersion."""

    observed = [float(value) for value in values if math.isfinite(float(value))]
    if not observed:
        return 8
    effect = mean(observed)
    dispersion = pstdev(observed) if len(observed) > 1 else 0.0
    if effect <= 0:
        return 200
    if dispersion <= 0:
        return 8
    # One-sided alpha=5% (1.645) and target power=80% (0.842).
    estimate = math.ceil(((1.645 + 0.842) * dispersion / effect) ** 2)
    return max(8, min(200, estimate))


def distribution(samples: list[float]) -> dict[str, float | None]:
    if not samples:
        return {"mean": None, "median": None, "p95_low": None, "p95_high": None}
    return {
        "mean": round(mean(samples), 4),
        "median": round(median(samples), 4),
        "p95_low": round(percentile(samples, 2.5), 4),
        "p95_high": round(percentile(samples, 97.5), 4),
    }


def percentile(data: list[float] | list[int], value: float) -> float:
    if not data:
        return 0.0
    ordered = sorted(data)
    position = value / 100.0 * (len(ordered) - 1)
    lower = int(position)
    fraction = position - lower
    if lower + 1 < len(ordered):
        return ordered[lower] + fraction * (ordered[lower + 1] - ordered[lower])
    return float(ordered[lower])


def _profit_factor(values: list[float]) -> float:
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = abs(sum(value for value in values if value < 0))
    if gross_loss > 0:
        return gross_profit / gross_loss
    return gross_profit if gross_profit > 0 else 0.0


def _sequence_risk(values: list[float]) -> tuple[float, int]:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    current_losses = 0
    max_losses = 0
    for value in values:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        if value < 0:
            current_losses += 1
            max_losses = max(max_losses, current_losses)
        else:
            current_losses = 0
    return drawdown, max_losses


def _seed(values: list[float], material: str, mode: str) -> int:
    canonical = "|".join((mode, material, *(format(value, ".12g") for value in values)))
    digest = hashlib.sha256(canonical.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big")


def _empty_bootstrap(count: int) -> dict[str, Any]:
    empty = distribution([])
    return {
        "version": BACKTEST_STATISTICS_VERSION,
        "method": "BOOTSTRAP_WITH_REPLACEMENT",
        "sample_size": 0,
        "simulation_count": count,
        "expectancy_r": dict(empty),
        "profit_factor": dict(empty),
        "win_rate": dict(empty),
        "probability_positive_edge_pct": None,
        "probability_non_positive_edge_pct": None,
        "one_sided_p_value": None,
        "minimum_required_trades": 8,
        "statistical_power_passed": False,
    }


def _empty_permutation(count: int, threshold: float) -> dict[str, Any]:
    return {
        "version": BACKTEST_STATISTICS_VERSION,
        "method": "PERMUTATION_WITHOUT_REPLACEMENT",
        "sample_size": 0,
        "simulation_count": count,
        "max_drawdown_r": distribution([]),
        "max_consecutive_losses": {"mean": None, "median": None, "p95_high": None},
        "drawdown_threshold_r": float(threshold),
        "probability_drawdown_exceeds_threshold_pct": None,
        "invariant_metrics": ["expectancy_r", "profit_factor", "win_rate"],
    }
