"""Policies shared by optional, research-only Backtest tools."""

from __future__ import annotations

from typing import Any

from core.system_backtest_engine import BacktestTrade


BACKTEST_ADVANCED_RESEARCH_VERSION = "backtest-advanced-research-v1"
MONTE_CARLO_AUTO_MIN_TRADES = 30
MONTE_CARLO_SIMULATIONS = 2000


def advanced_research_manifest(
    tool: str,
    *,
    requested: bool = True,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe an advanced output without making it release eligible."""

    payload: dict[str, Any] = {
        "version": BACKTEST_ADVANCED_RESEARCH_VERSION,
        "tool": str(tool or "").strip().upper(),
        "requested": bool(requested),
        "lifecycle": "RESEARCH_ONLY",
        "can_publish_config": False,
        "can_apply_symbol_config": False,
    }
    if details:
        payload["details"] = dict(details)
    return payload


def run_monte_carlo_if_eligible(
    trades: list[BacktestTrade],
    *,
    requested: bool = False,
    minimum_trades: int = MONTE_CARLO_AUTO_MIN_TRADES,
    simulations: int = MONTE_CARLO_SIMULATIONS,
) -> dict[str, Any]:
    """Run Monte Carlo for a useful sample, or when explicitly requested."""

    trade_count = len(trades)
    threshold = max(1, int(minimum_trades))
    explicitly_requested = bool(requested)
    if not explicitly_requested and trade_count < threshold:
        return {
            "version": BACKTEST_ADVANCED_RESEARCH_VERSION,
            "status": "SKIPPED",
            "reason": "TRADE_SAMPLE_TOO_SMALL",
            "trade_count": trade_count,
            "minimum_trades": threshold,
            "requested": False,
            "lifecycle": "RESEARCH_ONLY",
        }

    from core.monte_carlo import run_monte_carlo

    result = run_monte_carlo(trades, num_simulations=simulations)
    result.update({
        "status": "COMPLETE",
        "trigger": "USER_REQUEST" if explicitly_requested else "SAMPLE_ELIGIBLE",
        "trade_count": trade_count,
        "minimum_trades": threshold,
        "requested": explicitly_requested,
        "lifecycle": "RESEARCH_ONLY",
        "advanced_research_version": BACKTEST_ADVANCED_RESEARCH_VERSION,
    })
    return result
