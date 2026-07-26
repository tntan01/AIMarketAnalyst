"""Phase-5 Monte Carlo facade with separate uncertainty and path risk."""

from __future__ import annotations

from typing import Any

from core.backtest_statistics import (
    BACKTEST_STATISTICS_VERSION,
    bootstrap_trade_uncertainty,
    permutation_sequence_risk,
)
from core.system_backtest_engine import BacktestTrade


MONTE_CARLO_VERSION = "backtest-monte-carlo-v2"


def run_monte_carlo(
    trades: list[BacktestTrade],
    num_simulations: int = 5000,
) -> dict[str, Any]:
    """Return bootstrap uncertainty and permutation sequence risk separately."""

    results = [float(trade.result_r) for trade in trades]
    seed = "|".join(
        str(getattr(trade, "candidate_id", "") or trade.entry_time)
        for trade in trades
    )
    bootstrap = bootstrap_trade_uncertainty(
        results,
        samples=num_simulations,
        seed_material=seed,
    )
    permutation = permutation_sequence_risk(
        results,
        samples=num_simulations,
        seed_material=seed,
    )
    # Compatibility fields remain while their statistical method is explicit.
    return {
        "version": MONTE_CARLO_VERSION,
        "statistics_version": BACKTEST_STATISTICS_VERSION,
        "bootstrap_uncertainty": bootstrap,
        "sequence_permutation": permutation,
        "expectancy_r": bootstrap["expectancy_r"],
        "profit_factor": bootstrap["profit_factor"],
        "win_rate": bootstrap["win_rate"],
        "max_drawdown_r": permutation["max_drawdown_r"],
        "max_consecutive_losses": permutation["max_consecutive_losses"],
        "probability_positive_edge_pct": bootstrap[
            "probability_positive_edge_pct"
        ],
        "prob_negative_expectancy": bootstrap[
            "probability_non_positive_edge_pct"
        ],
        "one_sided_p_value": bootstrap["one_sided_p_value"],
        "statistical_power_passed": bootstrap["statistical_power_passed"],
        "minimum_required_trades": bootstrap["minimum_required_trades"],
        "prob_dd_exceed_10r": permutation[
            "probability_drawdown_exceeds_threshold_pct"
        ],
        "simulation_count": bootstrap["simulation_count"],
    }
