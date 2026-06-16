from __future__ import annotations

from typing import Any

from core.reason_codes import (
    EXECUTION_QUALITY_OK,
    EXECUTION_DATA_INCOMPLETE,
    EXECUTION_MANUAL_PENALTY,
    FINAL_SCORE_EVIDENCE_NEGATIVE,
    FINAL_SCORE_EXECUTION_WEAK,
    STAT_EDGE_NEGATIVE,
    STAT_EDGE_NOT_ENOUGH_DATA,
    STAT_EDGE_POSITIVE,
)
from core.safe_types import optional_float
from core.statistical_edge_engine import calculate_evidence_score, coerce_result_r


MIN_WARNING_SAMPLE = 8
MIN_CAP_SAMPLE = 12
MIN_BLOCK_SAMPLE = 25


def build_journal_feedback(
    closed_trades: list[dict[str, Any]] | None,
    *,
    symbol: str,
    direction: str,
    regime: str | None = None,
) -> dict[str, Any]:
    """Build conservative live feedback from journal outcomes.

    This module is intentionally rule-based and sample-size aware. It never
    blocks a setup for missing data, and only hard-blocks when a large enough
    historical sample is clearly bad.
    """
    trades = closed_trades if isinstance(closed_trades, list) else []
    evidence = calculate_evidence_score(trades, symbol=symbol, direction=direction, regime=regime)
    matched = _matching_trades(trades, symbol=symbol, direction=direction, regime=regime)
    results = [rr for rr in (coerce_result_r(trade.get("result_r")) for trade in matched) if rr is not None]
    sample_size = len(results)
    wins = [value for value in results if value > 0]
    losses = [value for value in results if value < 0]
    win_rate = len(wins) / sample_size if sample_size else None
    expectancy = sum(results) / sample_size if sample_size else None
    quality_values = [
        float(value)
        for value in (_safe_float(trade.get("execution_quality_score")) for trade in matched)
        if value is not None
    ]
    avg_quality = sum(quality_values) / len(quality_values) if quality_values else None

    warning_codes: list[str] = []
    block_codes: list[str] = []
    reasons: list[str] = []
    decision_cap: str | None = None
    opportunity_penalty = 0

    if sample_size < MIN_WARNING_SAMPLE:
        warning_codes.append(STAT_EDGE_NOT_ENOUGH_DATA)
        reasons.append(f"Phản hồi nhật ký: chỉ có {sample_size} lệnh đóng phù hợp; chưa đủ dữ liệu để phạt.")
    else:
        if expectancy is not None and expectancy > 0.15:
            warning_codes.append(STAT_EDGE_POSITIVE)
            reasons.append(f"Phản hồi nhật ký tích cực: kỳ vọng {expectancy:.2f}R trên {sample_size} lệnh.")
        if expectancy is not None and expectancy < -0.15:
            warning_codes.extend([STAT_EDGE_NEGATIVE, FINAL_SCORE_EVIDENCE_NEGATIVE])
            opportunity_penalty -= 8
            reasons.append(f"Phản hồi nhật ký tiêu cực: kỳ vọng {expectancy:.2f}R trên {sample_size} lệnh.")
            if sample_size >= MIN_CAP_SAMPLE:
                decision_cap = "WATCH_ONLY"
            if sample_size >= MIN_BLOCK_SAMPLE and expectancy <= -0.45 and (win_rate is not None and win_rate < 0.35):
                decision_cap = "TRADE_BLOCKED"
                block_codes.append(STAT_EDGE_NEGATIVE)

    if avg_quality is None:
        warning_codes.append(EXECUTION_DATA_INCOMPLETE)
    elif avg_quality >= 80:
        warning_codes.append(EXECUTION_QUALITY_OK)
    elif avg_quality < 65 and len(quality_values) >= 5:
        warning_codes.extend([FINAL_SCORE_EXECUTION_WEAK, EXECUTION_MANUAL_PENALTY])
        opportunity_penalty -= 5
        reasons.append(f"Phản hồi nhật ký: chất lượng thực thi trung bình {avg_quality:.1f}/100 còn yếu.")
        if decision_cap is None:
            decision_cap = "WAITING_CONFIRMATION"

    return {
        "sample_size": sample_size,
        "win_rate": round(win_rate * 100, 2) if win_rate is not None else None,
        "expectancy_r": round(expectancy, 3) if expectancy is not None else None,
        "evidence_score": evidence.get("evidence_score", 50),
        "evidence": evidence,
        "average_execution_quality": round(avg_quality, 1) if avg_quality is not None else None,
        "execution_quality_sample": len(quality_values),
        "decision_cap": decision_cap,
        "opportunity_penalty": opportunity_penalty,
        "warning_codes": _dedupe(warning_codes),
        "block_codes": _dedupe(block_codes),
        "reasons": _dedupe(reasons),
    }


def _matching_trades(
    trades: list[dict[str, Any]],
    *,
    symbol: str,
    direction: str,
    regime: str | None,
) -> list[dict[str, Any]]:
    norm_symbol = _normalize_symbol(symbol)
    norm_direction = direction.strip().lower()
    norm_regime = (regime or "").strip().lower()
    matched: list[dict[str, Any]] = []
    for trade in trades:
        if not isinstance(trade, dict):
            continue
        if _normalize_symbol(str(trade.get("symbol") or "")) != norm_symbol:
            continue
        trade_direction = str(trade.get("direction") or trade.get("selected_scenario") or "").strip().lower()
        if trade_direction != norm_direction:
            continue
        if norm_regime:
            trade_regime = str(trade.get("regime") or "").strip().lower()
            if trade_regime and trade_regime != norm_regime:
                continue
        if coerce_result_r(trade.get("result_r")) is None:
            continue
        matched.append(trade)
    return matched


def _normalize_symbol(value: str) -> str:
    return "".join(char for char in value.upper() if char.isalnum())


def _safe_float(value: object) -> float | None:
    return optional_float(value)


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result
