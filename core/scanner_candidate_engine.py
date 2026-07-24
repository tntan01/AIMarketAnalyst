"""Compose strategy and execution models into one scanner decision."""

from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from core.execution_readiness_engine import evaluate_execution_readiness
from core.scanner_models import (
    BLOCKED,
    DATA_UNAVAILABLE,
    OUT_OF_STRATEGY,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    ScannerCandidateDecision,
)
from core.scanner_strategy_engine import evaluate_sides, unique_codes
from core.scanner_strategy_router import route_strategy


_DATA_CODES = frozenset({
    "INVALID_SCANNER_ROW",
    "MISSING_ANALYSIS",
    "INVALID_BEST_SIDE",
    "MISSING_SELECTED_SIDE",
    "MISSING_SIDE_EVALUATION",
    "MISSING_SELECTED_SIDE_SCENARIO",
    "SIGNAL_SCORE_MISSING",
    "SETUP_SCORE_MISSING",
    "ENTRY_ZONE_MISSING",
    "STOP_LOSS_MISSING",
    "TAKE_PROFIT_MISSING",
})


def evaluate_scanner_candidate(
    row: dict[str, Any],
    backtest_config: dict[str, object] | None = None,
    *,
    now: datetime | None = None,
) -> ScannerCandidateDecision:
    """Return the canonical, serializable scanner candidate decision."""

    side_evaluations = evaluate_sides(row)
    strategy, side_evaluation = route_strategy(
        row,
        backtest_config,
        side_evaluations=side_evaluations,
        now=now,
    )
    execution = evaluate_execution_readiness(row, side_evaluation, strategy)
    candidate = (
        strategy.eligible
        and execution.entry_ready
        and execution.trade_allowed
    )
    reasons = unique_codes((*strategy.reason_codes, *execution.reason_codes))
    status = _candidate_status(
        row,
        candidate=candidate,
        strategy_eligible=strategy.eligible,
        trade_allowed=execution.trade_allowed,
        reason_codes=reasons,
    )
    return ScannerCandidateDecision(
        status=status,
        side_evaluation=side_evaluation,
        side_evaluations=side_evaluations,
        strategy=strategy,
        execution=execution,
        auto_trade_candidate=candidate,
        reason_codes=reasons,
    )


def build_candidate_order_payload(
    row: dict[str, Any],
    decision: ScannerCandidateDecision,
    *,
    require_price_in_zone: bool = True,
) -> dict[str, Any] | None:
    """Normalize one executable order payload from the canonical decision.

    Controller, alerts and UI share this adapter so they cannot independently
    select a side or pair one side's score with the opposite scenario.
    """

    if (
        not isinstance(row, dict)
        or not decision.auto_trade_candidate
        or decision.side_evaluation is None
        or decision.scenario is None
        or decision.selected_side not in {"buy", "sell"}
    ):
        return None

    scenario = decision.scenario
    entry_zone = scenario.get("entry_zone")
    if not isinstance(entry_zone, (list, tuple)) or len(entry_zone) < 2:
        return None
    entry_low = _positive_float(entry_zone[0])
    entry_high = _positive_float(entry_zone[1])
    if entry_low is None or entry_high is None:
        return None
    if entry_low > entry_high:
        entry_low, entry_high = entry_high, entry_low

    stop_loss = _positive_float(scenario.get("stop_loss"))
    raw_take_profit = scenario.get("take_profit")
    if isinstance(raw_take_profit, (list, tuple)):
        raw_take_profit = raw_take_profit[0] if raw_take_profit else None
    take_profit = _positive_float(raw_take_profit)
    if stop_loss is None or take_profit is None:
        return None

    explicit_entry = _positive_float(scenario.get("entry_price"))
    entry_price = explicit_entry or (
        entry_high if decision.selected_side == "buy" else entry_low
    )

    analysis = row.get("analysis_result")
    technical = (
        analysis.get("technical")
        if isinstance(analysis, dict)
        and isinstance(analysis.get("technical"), dict)
        else {}
    )
    current_price = _positive_float(technical.get("price"))
    if (
        require_price_in_zone
        and current_price is not None
        and not entry_low <= current_price <= entry_high
    ):
        return None

    sizing = scenario.get("position_sizing")
    if not isinstance(sizing, dict):
        sizing = {}

    return {
        "symbol": str(row.get("symbol") or "--"),
        "broker_symbol": str(row.get("broker_symbol") or "").strip(),
        "side": decision.selected_side,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "volume": sizing.get("suggested_lot"),
        "risk_reward": scenario.get("risk_reward", row.get("risk_reward", "")),
        "risk_reward_range": (
            scenario.get("risk_reward_range") or row.get("risk_reward_range")
        ),
        "entry_zone": [entry_low, entry_high],
        "selected_zone_id": scenario.get("entry_zone_id"),
        "entry_zone_id": scenario.get("entry_zone_id"),
        "entry_zone_score": scenario.get("entry_zone_score"),
        "entry_zone_quality_score": scenario.get(
            "entry_zone_quality_score"
        ),
        "entry_zone_relevance_score": scenario.get(
            "entry_zone_relevance_score"
        ),
        "entry_zone_setup_score": scenario.get(
            "entry_zone_setup_score"
        ),
        "entry_zone_scoring_version": scenario.get(
            "entry_zone_scoring_version"
        ),
        "smc_score_breakdown": (
            dict(scenario.get("smc_score_breakdown"))
            if isinstance(scenario.get("smc_score_breakdown"), dict)
            else {}
        ),
        "entry_low": entry_low,
        "entry_high": entry_high,
        "current_price": current_price,
        "market_regime": str(row.get("market_regime", "")),
        "expected_effective_rr": decision.strategy.expected_effective_rr,
        "required_min_rr": decision.strategy.min_rr,
        "setup_score": decision.setup_score,
        "best_score": row.get("best_score", 0),
        "scanner_action": str(row.get("scanner_action", "")),
        "trade_permission": str(row.get("trade_permission", "")),
        "short_reason": str(
            row.get("short_reason") or row.get("permission_reason") or ""
        ),
        "scanner_group": str(row.get("scanner_group", "")),
        "rank": row.get("rank"),
        "candidate_status": str(row.get("candidate_status", "")),
        "opportunity_rank": row.get("opportunity_rank"),
        "evidence_confidence": row.get("evidence_confidence"),
        "execution_readiness": row.get("execution_readiness"),
        "strategy_branch": row.get("auto_trade_branch"),
        "config_health": row.get("strategy_config_status"),
        "ranking_version": row.get("ranking_version"),
        "scan_id": row.get("scan_id"),
        "row_id": row.get("row_id"),
        "settings_hash": row.get("settings_hash"),
        "backtest_config_id": (
            row.get("observability", {}).get("backtest_config_id")
            if isinstance(row.get("observability"), dict)
            else ""
        ),
        "scorer_version": (
            row.get("observability", {}).get("scorer_version")
            if isinstance(row.get("observability"), dict)
            else ""
        ),
        "analysis_result": analysis,
    }


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and number > 0 else None


def _candidate_status(
    row: object,
    *,
    candidate: bool,
    strategy_eligible: bool,
    trade_allowed: bool,
    reason_codes: tuple[str, ...],
) -> str:
    if "NO_TRADE_SIDE" in reason_codes:
        return OUT_OF_STRATEGY
    if any(code in _DATA_CODES for code in reason_codes):
        return DATA_UNAVAILABLE
    if not strategy_eligible:
        return OUT_OF_STRATEGY
    if not trade_allowed:
        return BLOCKED
    if candidate:
        return READY_NOW

    action = (
        str(row.get("scanner_action", "") or "").strip().lower()
        if isinstance(row, dict)
        else ""
    )
    if action in {"wait", "wait_for_confirmation"}:
        return WAITING_CONFIRMATION
    if action == "watch":
        return WATCH_ZONE
    return OUT_OF_STRATEGY
