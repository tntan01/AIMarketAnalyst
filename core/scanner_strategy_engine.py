"""Build side-consistent evaluations.

Branch selection lives exclusively in :mod:`core.scanner_strategy_router`.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from core.scanner_models import (
    BUY,
    SETUP_SCORE_METRIC,
    SideEvaluation,
    SELL,
    StrategyEvaluation,
    VALID_SIDES,
)


def evaluate_sides(row: dict[str, Any]) -> tuple[SideEvaluation, SideEvaluation]:
    """Evaluate BUY and SELL independently in a stable order."""
    return evaluate_side(row, BUY), evaluate_side(row, SELL)


def evaluate_side(row: dict[str, Any], side: str) -> SideEvaluation:
    """Build one side without borrowing score or scenario from the other."""

    normalized_side = normalize_side(side)
    if normalized_side is None:
        return SideEvaluation(
            side=str(side or ""),
            signal_score=None,
            final_score=None,
            expected_effective_rr=None,
            scenario=None,
            entry_status="data_unavailable",
            m15_quality="",
            gate_result={},
            reason_codes=("INVALID_SIDE",),
        )

    reasons: list[str] = []
    analysis = row.get("analysis_result") if isinstance(row, dict) else None
    if not isinstance(analysis, dict):
        reasons.append("MISSING_ANALYSIS")
        analysis = {}

    scenario = scenario_for_side(analysis, normalized_side)
    if scenario is None:
        reasons.append("MISSING_SELECTED_SIDE_SCENARIO")
    elif scenario.get("entry_zone_source") == "fallback":
        reasons.append("FALLBACK_ENTRY_ZONE")

    scenario_scores = (
        analysis.get("scenario_scores")
        if isinstance(analysis.get("scenario_scores"), dict)
        else {}
    )
    legacy_side_scores = (
        scenario_scores.get(normalized_side)
        if isinstance(scenario_scores.get(normalized_side), dict)
        else {}
    )
    score_results = (
        analysis.get("side_scores")
        if isinstance(analysis.get("side_scores"), dict)
        else {}
    )
    side_scores = (
        score_results.get(normalized_side)
        if isinstance(score_results.get(normalized_side), dict)
        else {}
    )
    best_side = normalize_side(row.get("best_side") if isinstance(row, dict) else None)
    row_side_score = row.get(f"{normalized_side}_score") if isinstance(row, dict) else None
    if row_side_score is None and best_side == normalized_side and isinstance(row, dict):
        # Legacy scanner snapshots may only carry best_score.  It is safe to
        # use solely for the explicitly matching best side.
        row_side_score = row.get("best_score")
    signal_score = finite_number(
        side_scores.get(
            "signal_score",
            legacy_side_scores.get(
                "signal_score",
                legacy_side_scores.get(
                    "total",
                    row_side_score,
                ),
            ),
        )
    )
    if signal_score is None:
        reasons.append("SIGNAL_SCORE_MISSING")

    # Canonical payloads contain a setup score for both sides.  The row-level
    # alias is accepted only for the matching selected side in legacy data.
    side_setup_score = side_scores.get(
        "setup_score",
        side_scores.get(
            "final_score",
            legacy_side_scores.get(
                "setup_score",
                legacy_side_scores.get("final_score"),
            ),
        ),
    )
    has_side_setup_score = finite_number(side_setup_score) is not None
    final_score = finite_number(side_setup_score)
    if final_score is None and best_side == normalized_side and isinstance(row, dict):
        final_score = finite_number(row.get(SETUP_SCORE_METRIC))
    if final_score is None:
        if best_side == normalized_side:
            reasons.append("SETUP_SCORE_MISSING")
        elif not has_side_setup_score:
            reasons.append("SETUP_SCORE_NOT_SELECTED_SIDE")

    expected_rr = (
        positive_number(scenario.get("expected_effective_rr"))
        if scenario is not None
        else None
    )
    gate_result = (
        dict(analysis.get("trade_gate"))
        if best_side == normalized_side
        and isinstance(analysis.get("trade_gate"), dict)
        else {}
    )
    if best_side != normalized_side:
        reasons.append("GATE_RESULT_NOT_SELECTED_SIDE")

    return SideEvaluation(
        side=normalized_side,
        signal_score=signal_score,
        final_score=final_score,
        expected_effective_rr=expected_rr,
        scenario=dict(scenario) if scenario is not None else None,
        entry_status=str(
            scenario.get("entry_status", "") if scenario is not None else ""
        ).strip().lower(),
        m15_quality=str(
            scenario.get("m15_quality", "") if scenario is not None else ""
        ).strip().lower(),
        gate_result=gate_result,
        reason_codes=unique_codes(reasons),
    )


def evaluate_strategy(
    row: dict[str, Any],
    backtest_config: dict[str, object] | None = None,
    *,
    side_evaluations: tuple[SideEvaluation, ...] | None = None,
) -> tuple[StrategyEvaluation, SideEvaluation | None]:
    """Compatibility wrapper for the canonical Phase-2 Strategy Router."""

    from core.scanner_strategy_router import route_strategy

    return route_strategy(
        row,
        backtest_config,
        side_evaluations=side_evaluations,
    )


def normalize_side(value: object) -> str | None:
    side = str(value or "").strip().lower()
    return side if side in VALID_SIDES else None


def scenario_for_side(
    analysis: dict[str, Any],
    side: str,
) -> dict[str, Any] | None:
    scenarios = analysis.get("scenarios")
    if not isinstance(scenarios, list):
        return None
    for scenario in scenarios:
        if (
            isinstance(scenario, dict)
            and normalize_side(scenario.get("type")) == side
        ):
            return scenario
    return None


def finite_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def positive_number(value: object) -> float | None:
    number = finite_number(value)
    return number if number is not None and number > 0 else None


def valid_entry_zone(value: object) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return False
    low = positive_number(value[0])
    high = positive_number(value[1])
    return low is not None and high is not None and low <= high


def valid_take_profit(value: object) -> bool:
    if isinstance(value, (list, tuple)):
        return bool(value) and positive_number(value[0]) is not None
    return positive_number(value) is not None


def unique_codes(codes: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(code) for code in codes if str(code)))
