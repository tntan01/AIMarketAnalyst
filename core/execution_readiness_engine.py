"""Shared Phase-1 execution-readiness evaluation for scanner candidates."""

from __future__ import annotations

from typing import Any

from core.scanner_models import (
    ExecutionEvaluation,
    SideEvaluation,
    StrategyEvaluation,
)
from core.scanner_strategy_engine import (
    positive_number,
    unique_codes,
    valid_entry_zone,
    valid_take_profit,
)


def evaluate_execution_readiness(
    row: dict[str, Any],
    side_evaluation: SideEvaluation | None,
    strategy: StrategyEvaluation | None = None,
) -> ExecutionEvaluation:
    """Evaluate READY/entry checks separately from permission/risk gates."""

    if not isinstance(row, dict):
        return ExecutionEvaluation(
            entry_ready=False,
            trade_allowed=False,
            live_price_valid=None,
            portfolio_allowed=None,
            reason_codes=("INVALID_SCANNER_ROW",),
            block_codes=("INVALID_SCANNER_ROW",),
        )

    analysis = row.get("analysis_result")
    if not isinstance(analysis, dict):
        return ExecutionEvaluation(
            entry_ready=False,
            trade_allowed=False,
            live_price_valid=None,
            portfolio_allowed=None,
            reason_codes=("MISSING_ANALYSIS",),
            block_codes=("MISSING_ANALYSIS",),
        )

    entry_reasons: list[str] = []
    if str(row.get("scanner_action", "") or "").strip().lower() != "ready":
        entry_reasons.append("SCANNER_NOT_READY")

    decision_engine = (
        analysis.get("decision_engine")
        if isinstance(analysis.get("decision_engine"), dict)
        else {}
    )
    scanner_decision = str(
        row.get("scanner_decision")
        or decision_engine.get("decision")
        or ""
    ).strip().upper()
    if scanner_decision != "READY_TO_TRADE":
        entry_reasons.append("DECISION_NOT_READY")

    if side_evaluation is None or side_evaluation.scenario is None:
        entry_reasons.append("MISSING_SELECTED_SIDE_SCENARIO")
    else:
        scenario = side_evaluation.scenario
        if side_evaluation.entry_status != "confirmed_entry":
            entry_reasons.append("ENTRY_NOT_CONFIRMED")
        if scenario.get("ready_to_trade") is not True:
            entry_reasons.append("SCENARIO_NOT_READY")
        if side_evaluation.m15_quality != "strict":
            entry_reasons.append("M15_NOT_STRICT")
        if not valid_entry_zone(side_evaluation.entry_zone):
            entry_reasons.append("ENTRY_ZONE_MISSING")
        if positive_number(side_evaluation.stop_loss) is None:
            entry_reasons.append("STOP_LOSS_MISSING")
        if not valid_take_profit(side_evaluation.take_profit):
            entry_reasons.append("TAKE_PROFIT_MISSING")
        required_min_rr = (
            positive_number(strategy.min_rr)
            if strategy is not None
            else positive_number(row.get("min_rr"))
        )
        if required_min_rr is None:
            entry_reasons.append("REQUIRED_MIN_RR_MISSING")
        elif (
            side_evaluation.expected_effective_rr is None
            or side_evaluation.expected_effective_rr < required_min_rr
        ):
            entry_reasons.append("EXPECTED_EFFECTIVE_RR_BELOW_MIN")
        if _zone_is_broken(scenario, analysis):
            entry_reasons.append("ZONE_BROKEN")
        if _data_is_stale(scenario, analysis):
            entry_reasons.append("DATA_STALE")

    trade_reasons: list[str] = []
    if str(row.get("scanner_group", "") or "").strip().lower() == "blocked":
        trade_reasons.append("SCANNER_GROUP_BLOCKED")

    permission = str(row.get("trade_permission", "") or "").strip().lower()
    if permission != "allowed":
        trade_reasons.append("TRADE_PERMISSION_NOT_ALLOWED")

    journal_feedback = (
        row.get("journal_feedback")
        if isinstance(row.get("journal_feedback"), dict)
        else {}
    )
    if journal_feedback.get("decision_cap") in {"TRADE_BLOCKED", "WATCH_ONLY"}:
        trade_reasons.append("JOURNAL_DECISION_CAP")

    trade_gate = (
        side_evaluation.gate_result
        if side_evaluation is not None
        else {}
    )
    if not isinstance(trade_gate, dict) or trade_gate.get("allowed") is not True:
        trade_reasons.append("TRADE_GATE_NOT_ALLOWED")
    elif trade_gate.get("decision_cap") is not None:
        trade_reasons.append("TRADE_GATE_DECISION_CAP")

    entry_codes = unique_codes(entry_reasons)
    trade_codes = unique_codes(trade_reasons)
    return ExecutionEvaluation(
        entry_ready=not entry_codes,
        trade_allowed=not trade_codes,
        live_price_valid=None,
        portfolio_allowed=None,
        reason_codes=unique_codes((*entry_codes, *trade_codes)),
        block_codes=trade_codes,
    )


def _zone_is_broken(
    scenario: dict[str, Any],
    analysis: dict[str, Any],
) -> bool:
    if (
        scenario.get("zone_broken") is True
        or scenario.get("broken") is True
        or str(scenario.get("trigger_type") or "").strip().lower() == "zone_broken"
        or str(scenario.get("entry_status") or "").strip().lower() == "invalidated"
    ):
        return True
    trade_gate = analysis.get("trade_gate")
    if not isinstance(trade_gate, dict):
        return False
    return "ZONE_BROKEN" in {
        str(code).strip().upper()
        for key in ("block_codes", "warning_codes", "reason_codes")
        for code in (
            trade_gate.get(key)
            if isinstance(trade_gate.get(key), (list, tuple, set))
            else []
        )
    }


def _data_is_stale(
    scenario: dict[str, Any],
    analysis: dict[str, Any],
) -> bool:
    if scenario.get("stale") is True or scenario.get("is_stale") is True:
        return True
    quality = (
        analysis.get("data_quality")
        if isinstance(analysis.get("data_quality"), dict)
        else {}
    )
    return any(
        quality.get(key) is True
        for key in ("is_delayed", "is_stale", "stale")
    )
