"""Directional multi-timeframe confluence for the canonical SMC contract."""

from __future__ import annotations

from typing import Any

from core.smc_models import (
    DirectionalConfluence,
    TimeframeConfluenceEvidence,
)


_BULLISH_STRUCTURE = "HH/HL"
_BEARISH_STRUCTURE = "LH/LL"


def build_directional_confluence(
    d1_smc: dict[str, Any],
    h4_smc: dict[str, Any],
    h1_smc: dict[str, Any],
) -> DirectionalConfluence:
    """Build side-aware D1/H4/H1 confluence from canonical evidence."""

    d1 = _timeframe_evidence("D1", d1_smc)
    h4 = _timeframe_evidence("H4", h4_smc)
    h1 = _timeframe_evidence("H1", h1_smc)
    evidence = (d1, h4, h1)

    buy_score = 0
    sell_score = 0
    buy_reasons: list[str] = []
    sell_reasons: list[str] = []
    common_reasons: list[str] = []

    def award(side: str, points: int, code: str) -> None:
        nonlocal buy_score, sell_score
        if side == "buy":
            buy_score += points
            buy_reasons.append(code)
        elif side == "sell":
            sell_score += points
            sell_reasons.append(code)

    d1_h4_aligned = (
        d1.direction in {"buy", "sell"}
        and d1.direction == h4.direction
    )
    h4_h1_aligned = (
        h4.direction in {"buy", "sell"}
        and h4.direction == h1.direction
    )
    h1_against_h4 = (
        h4.direction in {"buy", "sell"}
        and h1.direction in {"buy", "sell"}
        and h4.direction != h1.direction
    )
    all_aligned = d1_h4_aligned and h4_h1_aligned

    if d1_h4_aligned:
        side_code = d1.direction.upper()
        award(d1.direction, 2, f"{side_code}_D1_H4_ALIGNED")
        common_reasons.append("D1_H4_ALIGNED")

    h1_relationship = "unknown"
    if h4_h1_aligned:
        side_code = h4.direction.upper()
        award(h4.direction, 2, f"{side_code}_H4_H1_ALIGNED")
        common_reasons.append("H4_H1_ALIGNED")
        h1_relationship = "aligned"
    elif h1_against_h4:
        if _is_h1_reversal_signal(h1):
            h1_relationship = "reversal"
            award(
                h1.direction,
                1,
                f"{h1.direction.upper()}_H1_REVERSAL_SIGNAL",
            )
            _append_side_reason(
                buy_reasons,
                sell_reasons,
                h4.direction,
                f"{h4.direction.upper()}_H1_REVERSAL_RISK",
            )
            common_reasons.append("H1_REVERSAL_AGAINST_H4")
        else:
            h1_relationship = "pullback"
            _append_side_reason(
                buy_reasons,
                sell_reasons,
                h4.direction,
                f"{h4.direction.upper()}_H1_PULLBACK_AGAINST_H4",
            )
            common_reasons.append("H1_PULLBACK_AGAINST_H4")
    elif h4.direction in {"buy", "sell"} and h1.direction == "unknown":
        h1_relationship = "unknown"

    if all_aligned:
        side_code = h4.direction.upper()
        award(
            h4.direction,
            1,
            f"{side_code}_ALL_TIMEFRAMES_ALIGNED",
        )
        common_reasons.append("ALL_TIMEFRAMES_ALIGNED")

    buy_score = max(0, min(5, buy_score))
    sell_score = max(0, min(5, sell_score))
    if buy_score > sell_score:
        direction = "bullish"
    elif sell_score > buy_score:
        direction = "bearish"
    elif buy_score or sell_score:
        direction = "mixed"
    else:
        direction = "unknown"

    known_count = sum(
        item.direction in {"buy", "sell"}
        for item in evidence
    )
    if known_count == 3:
        data_status = "complete"
    elif known_count:
        data_status = "partial"
        common_reasons.append("PARTIAL_TIMEFRAME_DATA")
    else:
        data_status = "insufficient"
        common_reasons.append("INSUFFICIENT_TIMEFRAME_DATA")

    return DirectionalConfluence(
        direction=direction,
        buy_score=buy_score,
        sell_score=sell_score,
        d1_h4_aligned=d1_h4_aligned,
        h4_h1_aligned=h4_h1_aligned,
        h1_against_h4=h1_against_h4,
        all_aligned=all_aligned,
        h1_relationship=h1_relationship,
        data_status=data_status,
        buy_reason_codes=tuple(buy_reasons),
        sell_reason_codes=tuple(sell_reasons),
        reason_codes=tuple(common_reasons),
        timeframe_evidence=evidence,
    )


def _timeframe_evidence(
    timeframe: str,
    payload: dict[str, Any],
) -> TimeframeConfluenceEvidence:
    value = payload if isinstance(payload, dict) else {}
    structure = str(value.get("structure", "unknown") or "unknown")
    direction = _structure_side(structure)
    displacement = str(
        value.get("displacement", "neutral") or "neutral"
    ).lower()
    bos = bool(value.get("bos", False))
    choch = bool(value.get("choch", False))
    choch_confirmed = bool(value.get("choch_confirmed", False))
    reasons = [f"{timeframe}_STRUCTURE_{direction.upper()}"]
    if bos:
        reasons.append(f"{timeframe}_BOS_{displacement.upper()}")
    if choch:
        suffix = "_CONFIRMED" if choch_confirmed else ""
        reasons.append(
            f"{timeframe}_CHOCH_{displacement.upper()}{suffix}"
        )
    if direction == "unknown":
        reasons.append(f"{timeframe}_STRUCTURE_UNAVAILABLE")
    return TimeframeConfluenceEvidence(
        timeframe=timeframe,
        structure=structure,
        direction=direction,
        bos=bos,
        choch=choch,
        choch_confirmed=choch_confirmed,
        displacement=displacement,
        reason_codes=tuple(reasons),
    )


def _structure_side(structure: str) -> str:
    if structure == _BULLISH_STRUCTURE:
        return "buy"
    if structure == _BEARISH_STRUCTURE:
        return "sell"
    return "unknown"


def _is_h1_reversal_signal(
    evidence: TimeframeConfluenceEvidence,
) -> bool:
    expected_displacement = (
        "bullish" if evidence.direction == "buy" else "bearish"
    )
    displacement_confirms = (
        evidence.displacement == expected_displacement
    )
    return (
        evidence.choch_confirmed
        or (evidence.choch and displacement_confirms)
        or (evidence.bos and displacement_confirms)
    )


def _append_side_reason(
    buy_reasons: list[str],
    sell_reasons: list[str],
    side: str,
    code: str,
) -> None:
    if side == "buy":
        buy_reasons.append(code)
    elif side == "sell":
        sell_reasons.append(code)
