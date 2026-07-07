from __future__ import annotations

import random
from statistics import mean, median
from typing import Any

from core.system_backtest_engine import BacktestTrade


def run_monte_carlo(trades: list[BacktestTrade], num_simulations: int = 5000) -> dict[str, Any]:
    if not trades:
        return _empty_result(num_simulations)

    result_r_list = [t.result_r for t in trades]

    if num_simulations < 10:
        num_simulations = 10

    n = len(result_r_list)
    samples_exp: list[float] = []
    samples_dd: list[float] = []
    samples_pf: list[float] = []
    samples_wr: list[float] = []
    samples_cl: list[int] = []

    for _ in range(num_simulations):
        shuffled = result_r_list[:]
        random.shuffle(shuffled)

        equity = 0.0
        peak = 0.0
        max_dd = 0.0
        gross_profit = 0.0
        gross_loss = 0.0
        wins = 0
        max_cl = 0
        cur_cl = 0

        for r in shuffled:
            equity += r
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)

            if r > 0:
                gross_profit += r
                wins += 1
                cur_cl = 0
            elif r < 0:
                gross_loss += abs(r)
                cur_cl += 1
                max_cl = max(max_cl, cur_cl)
            else:
                cur_cl = 0

        pf = gross_profit / gross_loss if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)
        samples_exp.append(equity / n)
        samples_dd.append(max_dd)
        samples_pf.append(pf)
        samples_wr.append(wins / n * 100.0)
        samples_cl.append(max_cl)

    return {
        "expectancy_r": _dist(samples_exp),
        "max_drawdown_r": _dist(samples_dd),
        "profit_factor": _dist(samples_pf),
        "win_rate": _dist(samples_wr),
        "prob_negative_expectancy": round(
            sum(1 for e in samples_exp if e < 0) / num_simulations * 100, 2
        ),
        "prob_dd_exceed_10r": round(
            sum(1 for d in samples_dd if d > 10) / num_simulations * 100, 2
        ),
        "max_consecutive_losses": {
            "mean": round(mean(samples_cl), 2),
            "median": round(median(samples_cl), 2),
            "p95_high": round(_percentile(samples_cl, 97.5), 2),
        },
        "simulation_count": num_simulations,
    }


def _dist(samples: list[float]) -> dict[str, float | None]:
    return {
        "mean": round(mean(samples), 4),
        "median": round(median(samples), 4),
        "p95_low": round(_percentile(samples, 2.5), 4),
        "p95_high": round(_percentile(samples, 97.5), 4),
    }


def _percentile(data: list[float] | list[int], p: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    n = len(s)
    k = (p / 100.0) * (n - 1)
    f = int(k)
    c = k - f
    if f + 1 < n:
        return s[f] + c * (s[f + 1] - s[f])
    return float(s[f])


def _empty_result(count: int) -> dict[str, Any]:
    empty_dist: dict[str, float | None] = {
        "mean": None, "median": None, "p95_low": None, "p95_high": None,
    }
    empty_cl: dict[str, float | None] = {
        "mean": None, "median": None, "p95_high": None,
    }
    return {
        "expectancy_r": empty_dist,
        "max_drawdown_r": empty_dist,
        "profit_factor": empty_dist,
        "win_rate": empty_dist,
        "prob_negative_expectancy": None,
        "prob_dd_exceed_10r": None,
        "max_consecutive_losses": empty_cl,
        "simulation_count": count,
    }
