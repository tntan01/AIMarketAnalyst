"""Canonical SMC zone selection and side score."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Any

from core.smc_m15_confirmation import evaluate_m15_confirmation
from core.smc_models import SelectedSmcZone, SmcScoreBreakdown, SmcZone
from core.smc_scoring_result import SmcScoringResult, SmcSideScoringResult
from core.smc_versions import SMC_SCORER_VERSION
from core.smc_zone_ai_review import review_zone_with_cache


_ZONE_HARD_DISTANCE_ATR = 3.0
_VALID_FAMILIES = frozenset({
    "demand",
    "supply",
    "order_block",
    "fvg",
})

# Zone-selection timeframe priority.  H4 zones are structurally thicker and
# less prone to liquidity sweeps, so they are preferred whenever at least one
# eligible H4 zone exists.  An H1 zone is selectable only as a fallback when
# no eligible H4 zone is available.  The decision is recorded on the selected
# zone as a reason code for traceability.
ZONE_TIMEFRAME_H4 = "H4"
SELECTION_REASON_H4_PREFERRED = "H4_TIMEFRAME_PREFERRED"
SELECTION_REASON_H1_FALLBACK = "H1_TIMEFRAME_NO_VALID_H4"

# D1 zones never participate in entry-zone selection (evaluate_smc_zones only
# iterates H4/H1), but they still carry confluence evidence: when price reacts
# at an unmitigated D1 order block / FVG while H4 is aligned with the D1
# direction, a bonus is folded into the structure (confluence) component and
# traced with its own reason code.  The entry zone remains H4/H1.
D1_ZONE_REACTION_BONUS_REASON = "D1_ZONE_REACTION_BONUS"
_D1_REACTION_BONUS_POINTS = 2
_D1_REACTION_NEAR_ATR = 0.5
_D1_REACTION_FAMILIES = (
    ("order_block", "order_blocks"),
    ("fvg", "fvg"),
)

# Asymmetric AI audit of the selected zone.  The AI is consulted only when the
# deterministic subtotal already reaches the threshold, and only a confident
# weak verdict subtracts points; a positive verdict never adds any.  The
# penalty runs through the same penalty/cap pipeline, so the AI can never
# override the existing gates.
AI_ZONE_WEAK_REASON = "AI_ZONE_WEAK"
_AI_REVIEW_SUBTOTAL_THRESHOLD = 8
_AI_ZONE_WEAK_PENALTY = 2
_AI_REVIEW_MIN_CONFIDENCE = 0.7
_AI_ZONE_WEAK_COMBINED_THRESHOLD = 4.0


@dataclass(frozen=True, slots=True)
class EvaluatedSmcZone:
    zone: SmcZone
    mandatory_passed: bool
    distance_atr: float | None
    rejection_codes: tuple[str, ...]
    quality_components: tuple[tuple[str, int], ...]
    relevance_components: tuple[tuple[str, int], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.zone.to_dict(include_compatibility=False),
            "mandatory_passed": self.mandatory_passed,
            "distance_atr": self.distance_atr,
            "rejection_codes": list(self.rejection_codes),
            "quality_components": dict(self.quality_components),
            "relevance_components": dict(self.relevance_components),
        }


def score_smc(
    smc: dict[str, Any],
    technical: dict[str, Any],
    market_regime: dict[str, Any] | None = None,
    *,
    ai_service: Any | None = None,
    zone_audit_cache: dict[str, Any] | None = None,
    m15_candles: Any | None = None,
) -> SmcScoringResult:
    """Score BUY and SELL independently without mutating the active context.

    When ``ai_service`` is provided, sides whose deterministic subtotal
    reaches the audit threshold are reviewed by the AI zone auditor under
    asymmetric rules (a confident weak verdict subtracts points; a positive
    verdict never adds any).  Without it scoring stays fully deterministic.

    When ``zone_audit_cache`` is provided, AI verdicts are read and stored
    by zone id (see :mod:`core.smc_zone_ai_review`), so a backtest replay
    over the same data reuses cached verdicts instead of calling the AI
    again.

    When ``m15_candles`` is provided, the selected zone is checked for M15
    confirmation (small-timeframe CHoCH or clear price reaction): a tested
    zone without confirmation subtracts points, while confirmation and the
    warning cases only trace reason codes.  Without it the step is inert.
    """

    sides: dict[str, SmcSideScoringResult] = {}
    for side in ("buy", "sell"):
        side_payload = _score_side(
            side,
            smc if isinstance(smc, dict) else {},
            technical if isinstance(technical, dict) else {},
            market_regime if isinstance(market_regime, dict) else {},
            ai_service=ai_service,
            zone_audit_cache=zone_audit_cache,
            m15_candles=m15_candles,
        )
        sides[side] = SmcSideScoringResult(
            score=side_payload["smc_quality"],
            breakdown=side_payload["breakdown"],
            selected_zone=side_payload["selected_zone"],
            selected_zone_id=side_payload["selected_zone_id"],
            selected_zone_type=side_payload["selected_zone_type"],
            selected_zone_timeframe=side_payload["selected_zone_timeframe"],
            reason_codes=tuple(
                side_payload["breakdown"].get("reason_codes", [])
            ),
            smc_reason=side_payload["smc_reason"],
            selected_zone_score=side_payload["selected_zone_score"],
            selected_zone_quality_score=side_payload["selected_zone_quality_score"],
            selected_zone_relevance_score=side_payload["selected_zone_relevance_score"],
            selected_zone_setup_score=side_payload["selected_zone_setup_score"],
        )
    return SmcScoringResult(scoring_version=SMC_SCORER_VERSION, sides=sides)


def evaluate_smc_zones(
    smc: dict[str, Any],
    side: str,
    *,
    price: object,
    atr_value: object,
    market_regime: dict[str, Any] | None = None,
) -> tuple[EvaluatedSmcZone, ...]:
    """Evaluate every H4/H1 candidate for one side using the v2 contract."""

    normalized_side = _normalize_side(side)
    numeric_price = _positive_float(price)
    numeric_atr = _positive_float(atr_value)
    regime = market_regime if isinstance(market_regime, dict) else {}
    symbol = str(smc.get("symbol", "") or "")
    evaluations: list[EvaluatedSmcZone] = []
    seen_zone_ids: set[str] = set()

    for timeframe in ("H4", "H1"):
        timeframe_data = smc.get(timeframe, {})
        if not isinstance(timeframe_data, dict):
            continue
        for family, zone in _zone_payloads(timeframe_data, normalized_side):
            raw_direction = _zone_direction(zone, family)
            try:
                model = SmcZone.from_dict(
                    zone,
                    symbol=symbol,
                    timeframe=timeframe,
                    family=family,
                    direction=raw_direction,
                )
            except (TypeError, ValueError):
                continue
            if model.zone_id in seen_zone_ids:
                continue
            seen_zone_ids.add(model.zone_id)
            evaluation = _evaluate_zone(
                model,
                zone,
                normalized_side,
                price=numeric_price,
                atr_value=numeric_atr,
                market_regime=regime,
            )
            evaluations.append(evaluation)

    return tuple(evaluations)


def select_smc_zone(
    evaluations: tuple[EvaluatedSmcZone, ...],
) -> SelectedSmcZone | None:
    """Select the canonical zone for one side.

    Timeframe priority is applied first: eligible H4 zones are always
    preferred over H1 zones, so an H1 zone is only selectable when no
    eligible H4 zone exists.  Within the chosen timeframe tier the winner is
    picked by setup score, then distance, recency, and stable zone ID.  The
    timeframe decision is recorded on the returned zone as a reason code for
    traceability.
    """

    eligible = [
        evaluation
        for evaluation in evaluations
        if evaluation.mandatory_passed
    ]
    if not eligible:
        return None
    h4_eligible = [
        evaluation
        for evaluation in eligible
        if evaluation.zone.timeframe == ZONE_TIMEFRAME_H4
    ]
    if h4_eligible:
        candidates = h4_eligible
        selection_reason = SELECTION_REASON_H4_PREFERRED
    else:
        candidates = eligible
        selection_reason = SELECTION_REASON_H1_FALLBACK
    selected = min(
        candidates,
        key=lambda item: (
            -item.zone.zone_setup_score,
            (
                item.distance_atr
                if item.distance_atr is not None
                else float("inf")
            ),
            item.zone.age_bars,
            item.zone.zone_id,
        ),
    )
    return SelectedSmcZone.from_zone(
        selected.zone,
        source="smc_selected",
        selection_reason_codes=(selection_reason,),
    )


def _score_side(
    side: str,
    smc: dict[str, Any],
    technical: dict[str, Any],
    market_regime: dict[str, Any],
    ai_service: Any | None = None,
    zone_audit_cache: dict[str, Any] | None = None,
    m15_candles: Any | None = None,
) -> dict[str, Any]:
    price = _positive_float(technical.get("price"))
    atr_value = _positive_float(
        technical.get("atr_h4") or technical.get("atr_d1")
    )
    evaluations = evaluate_smc_zones(
        smc,
        side,
        price=price,
        atr_value=atr_value,
        market_regime=market_regime,
    )
    selected = select_smc_zone(evaluations)

    confluence = (
        smc.get("confluence")
        if isinstance(smc.get("confluence"), dict)
        else {}
    )
    structure_score = _bounded_component(
        confluence.get(f"{side}_score"),
        5,
    )
    d1_bonus, d1_bonus_reasons = _d1_zone_reaction_bonus(
        side,
        smc,
        price,
        atr_value,
    )
    structure_score = min(5, structure_score + d1_bonus)
    zone_score = _selected_zone_component(selected)
    ltf_score, ltf_reasons = _ltf_confirmation_score(
        side,
        smc,
        selected,
    )
    technical_score, technical_reasons = _technical_validation_score(
        side,
        selected,
        technical,
        atr_value,
    )

    subtotal = min(
        15,
        structure_score + zone_score + ltf_score + technical_score,
    )
    penalties: list[str] = []
    caps: list[str] = []
    penalty_points = 0
    applied_cap: int | None = None
    opposite = "bearish" if side == "buy" else "bullish"
    h4 = smc.get("H4", {}) if isinstance(smc.get("H4"), dict) else {}
    h1 = smc.get("H1", {}) if isinstance(smc.get("H1"), dict) else {}

    if h1.get("choch") and h1.get("displacement") == opposite:
        penalty_points += 2
        penalties.append("H1_CHOCH_AGAINST_SIDE")
        if h1.get("choch_confirmed"):
            applied_cap = 8
            caps.append("H1_CONFIRMED_CHOCH_CAP_8")

    if (
        h4.get("choch")
        and h4.get("choch_confirmed")
        and h4.get("displacement") == opposite
    ):
        applied_cap = 4 if applied_cap is None else min(applied_cap, 4)
        caps.append("H4_CONFIRMED_CHOCH_CAP_4")

    ai_penalty, ai_reasons = _ai_zone_review_penalty(
        side,
        selected,
        subtotal,
        smc,
        price,
        atr_value,
        ai_service,
        zone_audit_cache,
    )
    penalty_points += ai_penalty
    penalties.extend(ai_reasons)

    m15_penalty, m15_reasons = _m15_confirmation_penalty(
        side,
        selected,
        m15_candles,
    )
    penalty_points += m15_penalty
    if m15_penalty:
        penalties.extend(m15_reasons)

    total = max(0, subtotal - penalty_points)
    if applied_cap is not None:
        total = min(total, applied_cap)
    total = max(0, min(15, total))

    confluence_reasons = confluence.get(f"{side}_reason_codes", [])
    reason_codes = [
        str(code)
        for code in confluence_reasons
        if str(code).strip()
    ] if isinstance(confluence_reasons, list) else []
    if selected is None:
        reason_codes.append("NO_ELIGIBLE_CANONICAL_ZONE")
    else:
        reason_codes.extend([
            "CANONICAL_ZONE_SELECTED",
            f"ZONE_FAMILY_{selected.family.upper()}",
        ])
    reason_codes.extend(d1_bonus_reasons)
    reason_codes.extend(ltf_reasons)
    reason_codes.extend(technical_reasons)
    reason_codes.extend(ai_reasons)
    reason_codes.extend(m15_reasons)

    breakdown = SmcScoreBreakdown(
        side=side,
        total=total,
        structure_score=structure_score,
        zone_score=zone_score,
        ltf_confirmation_score=ltf_score,
        technical_validation_score=technical_score,
        subtotal=subtotal,
        penalty_points=penalty_points,
        applied_cap=applied_cap,
        penalties=tuple(penalties),
        caps=tuple(caps),
        selected_zone_id=selected.zone_id if selected else None,
        selected_zone_quality_score=(
            selected.zone_quality_score if selected else None
        ),
        selected_zone_relevance_score=(
            selected.zone_relevance_score if selected else None
        ),
        selected_zone_setup_score=(
            selected.zone_setup_score if selected else None
        ),
        reason_codes=tuple(reason_codes),
        scoring_version=SMC_SCORER_VERSION,
    )
    selected_payload = (
        selected.to_dict(include_compatibility=False)
        if selected is not None
        else None
    )
    return {
        "smc_quality": total,
        "smc_reason": "; ".join(reason_codes)
        if reason_codes
        else "SMC v2 has no qualified evidence.",
        "selected_zone": selected_payload,
        "selected_zone_id": selected.zone_id if selected else None,
        "selected_zone_type": selected.zone_type if selected else None,
        "selected_zone_timeframe": selected.timeframe if selected else None,
        "selected_zone_quality_score": (
            selected.zone_quality_score if selected else None
        ),
        "selected_zone_relevance_score": (
            selected.zone_relevance_score if selected else None
        ),
        "selected_zone_setup_score": (
            selected.zone_setup_score if selected else None
        ),
        "selected_zone_score": (
            selected.zone_setup_score if selected else None
        ),
        "breakdown": breakdown.to_dict(),
        "evaluated_zones": [
            evaluation.to_dict()
            for evaluation in evaluations
        ],
        "scoring_version": SMC_SCORER_VERSION,
    }


def _evaluate_zone(
    model: SmcZone,
    raw: dict[str, Any],
    side: str,
    *,
    price: float | None,
    atr_value: float | None,
    market_regime: dict[str, Any],
) -> EvaluatedSmcZone:
    rejection_codes: list[str] = []
    if model.direction != side:
        rejection_codes.append("DIRECTION_MISMATCH")
    if model.family not in _VALID_FAMILIES:
        rejection_codes.append("UNKNOWN_ZONE_FAMILY")
    if model.high <= model.low:
        rejection_codes.append("INVALID_ZONE_BOUNDS")
    if model.origin_index < 0 or model.departure_end_index is None:
        rejection_codes.append("MISSING_FORMATION_DATA")
    if model.broken:
        rejection_codes.append("ZONE_BROKEN")
    if price is None:
        rejection_codes.append("MISSING_PRICE")
    if atr_value is None:
        rejection_codes.append("MISSING_ATR")

    distance_atr: float | None = None
    if price is not None and atr_value is not None:
        correct_side = (
            model.low <= price
            if side == "buy"
            else model.high >= price
        )
        if not correct_side:
            rejection_codes.append("ZONE_ON_WRONG_PRICE_SIDE")
        price_distance = _distance_to_zone(price, model.low, model.high)
        distance_atr = round(price_distance / atr_value, 6)
        if distance_atr > _ZONE_HARD_DISTANCE_ATR:
            rejection_codes.append("ZONE_BEYOND_HARD_DISTANCE")

    quality_components = _zone_quality_components(model, raw, side)
    quality = min(100, sum(quality_components.values()))
    mandatory_passed = not rejection_codes
    relevance_components = (
        _zone_relevance_components(
            model,
            side,
            distance_atr=distance_atr,
            market_regime=market_regime,
        )
        if mandatory_passed
        else {}
    )
    relevance = (
        min(100, sum(relevance_components.values()))
        if mandatory_passed
        else 0
    )
    setup = (
        round(quality * 0.60 + relevance * 0.40)
        if mandatory_passed
        else 0
    )
    scored_model = replace(
        model,
        zone_quality_score=quality,
        zone_relevance_score=relevance,
        zone_setup_score=max(0, min(100, setup)),
        scoring_version=SMC_SCORER_VERSION,
    )
    return EvaluatedSmcZone(
        zone=scored_model,
        mandatory_passed=mandatory_passed,
        distance_atr=distance_atr,
        rejection_codes=tuple(rejection_codes),
        quality_components=tuple(quality_components.items()),
        relevance_components=tuple(relevance_components.items()),
    )


def _zone_quality_components(
    zone: SmcZone,
    raw: dict[str, Any],
    side: str,
) -> dict[str, int]:
    pattern = sum((
        5 if zone.high > zone.low else 0,
        5 if zone.family in _VALID_FAMILIES else 0,
        5 if zone.direction in {"buy", "sell"} else 0,
        5 if zone.origin_index >= 0 else 0,
    ))
    formation_valid = (
        zone.departure_end_index is not None
        and zone.departure_end_index >= zone.origin_index
    )
    displacement = max(
        0.0,
        _finite_float(raw.get("displacement_multiple"), 0.0),
    )
    departure = (
        (5 if formation_valid else 0)
        + round(min(2.5, displacement) / 2.5 * 20)
    )

    if zone.broken:
        lifecycle = 0
    else:
        freshness_points = 4 if zone.stale else 12
        visits = zone.independent_retest_count
        if visits == 0:
            visit_points = 10
        elif visits == 1:
            visit_points = 13
        elif visits == 2:
            visit_points = 8
        else:
            visit_points = max(0, 8 - (visits - 2) * 4)
        lifecycle = freshness_points + visit_points
        mitigation = zone.mitigation_ratio
        if mitigation is not None and mitigation >= 0.90:
            lifecycle -= 5
        elif mitigation is not None and mitigation >= 0.75:
            lifecycle -= 3
        lifecycle = max(0, min(25, lifecycle))

    location = str(raw.get("zone_location", "unknown") or "unknown")
    if (
        (side == "buy" and location == "discount")
        or (side == "sell" and location == "premium")
    ):
        location_points = 15
    elif location == "equilibrium":
        location_points = 7
    else:
        location_points = 0

    sweep_points = (
        15
        if zone.liquidity_sweep_linked and zone.linked_sweep_id
        else 0
    )
    return {
        "pattern_validity": pattern,
        "departure_displacement": departure,
        "freshness_lifecycle": lifecycle,
        "premium_discount": location_points,
        "linked_liquidity_sweep": sweep_points,
    }


def _zone_relevance_components(
    zone: SmcZone,
    side: str,
    *,
    distance_atr: float | None,
    market_regime: dict[str, Any],
) -> dict[str, int]:
    if distance_atr is None:
        return {}
    if distance_atr == 0:
        distance_points = 40
    elif distance_atr <= 0.5:
        distance_points = 35
    elif distance_atr <= 1.0:
        distance_points = 28
    elif distance_atr <= 2.0:
        distance_points = 18
    else:
        distance_points = 8

    if zone.age_bars <= 10:
        age_points = 15
    elif zone.age_bars <= 30:
        age_points = 12
    elif zone.age_bars <= 50:
        age_points = 8
    else:
        age_points = 4
    if zone.stale:
        age_points = min(age_points, 4)

    primary = str(market_regime.get("primary", "unknown") or "unknown")
    aligned = (
        (side == "buy" and primary == "trend_up")
        or (side == "sell" and primary == "trend_down")
    )
    opposite = (
        (side == "buy" and primary == "trend_down")
        or (side == "sell" and primary == "trend_up")
    )
    if aligned:
        regime_points = 10
    elif opposite:
        regime_points = 0
    elif primary == "range":
        regime_points = 8
    elif primary == "volatile":
        regime_points = 4
    else:
        regime_points = 5

    return {
        "active_state": 5 if zone.stale else 15,
        "correct_price_side": 20,
        "distance": distance_points,
        "age": age_points,
        "regime": regime_points,
    }


def _selected_zone_component(selected: SelectedSmcZone | None) -> int:
    if selected is None:
        return 0
    score = selected.zone_setup_score
    if score >= 85:
        return 5
    if score >= 70:
        return 4
    if score >= 55:
        return 3
    if score >= 40:
        return 2
    if score >= 25:
        return 1
    return 0


def _ltf_confirmation_score(
    side: str,
    smc: dict[str, Any],
    selected: SelectedSmcZone | None,
) -> tuple[int, list[str]]:
    h1 = smc.get("H1", {}) if isinstance(smc.get("H1"), dict) else {}
    expected_structure = "HH/HL" if side == "buy" else "LH/LL"
    expected_displacement = "bullish" if side == "buy" else "bearish"
    reasons: list[str] = []
    score = 0
    if (
        h1.get("displacement") == expected_displacement
        and (h1.get("bos") or h1.get("choch"))
    ):
        score += 2
        reasons.append("H1_DIRECTIONAL_TRIGGER")
    elif h1.get("structure") == expected_structure:
        score += 1
        reasons.append("H1_STRUCTURE_CONFIRMATION")

    selected_uses_sweep = bool(
        selected
        and selected.liquidity_sweep_linked
        and selected.linked_sweep_id
    )
    if not selected_uses_sweep and _has_unlinked_h1_sweep(h1, side):
        score += 1
        reasons.append("H1_UNLINKED_SWEEP_CONFIRMATION")
    return min(3, score), reasons


def _has_unlinked_h1_sweep(h1: dict[str, Any], side: str) -> bool:
    sweeps = h1.get("zone_link_sweeps", {})
    if not isinstance(sweeps, dict):
        return False
    key = "swept_lows" if side == "buy" else "swept_highs"
    values = sweeps.get(key, [])
    if not isinstance(values, list):
        return False
    return any(
        isinstance(sweep, dict) and not sweep.get("linked_zone_id")
        for sweep in values
    )


def _technical_validation_score(
    side: str,
    selected: SelectedSmcZone | None,
    technical: dict[str, Any],
    atr_value: float | None,
) -> tuple[int, list[str]]:
    if selected is None or atr_value is None:
        return 0, []
    key = "support_zones" if side == "buy" else "resistance_zones"
    zones = technical.get(key, [])
    if not isinstance(zones, list):
        return 0, []
    distances = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        level = _optional_float(zone.get("level"))
        if level is not None:
            distances.append(abs(level - selected.level) / atr_value)
    if not distances:
        return 0, []
    nearest = min(distances)
    if nearest <= 0.30:
        return 2, ["TECHNICAL_ZONE_CROSS_VALIDATED"]
    if nearest <= 0.60:
        return 1, ["TECHNICAL_ZONE_NEARBY"]
    return 0, []


def _d1_zone_reaction_bonus(
    side: str,
    smc: dict[str, Any],
    price: float | None,
    atr_value: float | None,
) -> tuple[int, list[str]]:
    """Confluence bonus when price reacts at an unmitigated D1 OB/FVG.

    The D1 zone only contributes evidence; it is never an entry-zone
    candidate (selection stays restricted to H4/H1).  The bonus is granted
    when price sits inside or near an unbroken, unmitigated D1 order block
    or FVG matching the side while the H4 structure is aligned with that D1
    direction.
    """

    if price is None or atr_value is None:
        return 0, []
    d1 = smc.get("D1", {}) if isinstance(smc.get("D1"), dict) else {}
    if not d1:
        return 0, []
    h4 = smc.get("H4", {}) if isinstance(smc.get("H4"), dict) else {}
    expected_structure = "HH/HL" if side == "buy" else "LH/LL"
    if h4.get("structure") != expected_structure:
        return 0, []
    near_distance = _D1_REACTION_NEAR_ATR * atr_value
    for family, key in _D1_REACTION_FAMILIES:
        zones = d1.get(key, [])
        if not isinstance(zones, list):
            continue
        for zone in zones:
            if not isinstance(zone, dict):
                continue
            if _zone_direction(zone, family) != side:
                continue
            if zone.get("broken") or zone.get("mitigated"):
                continue
            low = _optional_float(zone.get("low"))
            high = _optional_float(zone.get("high"))
            if low is None or high is None or high <= low:
                continue
            if _distance_to_zone(price, low, high) <= near_distance:
                return (
                    _D1_REACTION_BONUS_POINTS,
                    [D1_ZONE_REACTION_BONUS_REASON],
                )
    return 0, []


def _ai_zone_review_penalty(
    side: str,
    selected: SelectedSmcZone | None,
    subtotal: int,
    smc: dict[str, Any],
    price: float | None,
    atr_value: float | None,
    ai_service: Any | None,
    zone_audit_cache: dict[str, Any] | None = None,
) -> tuple[int, list[str]]:
    """Asymmetric AI audit of the selected zone.

    The AI is consulted only when the deterministic subtotal reaches the
    threshold and a zone was actually selected.  Only a confident weak
    verdict (combined zone_validity and displacement_quality at or below the
    weak threshold with confidence >= 0.7) subtracts points.  Positive or
    uncertain verdicts never change the score, and nothing is ever added.

    Verdicts are cached by zone id when ``zone_audit_cache`` is provided:
    a backtest replay over the same data reads the cached verdict (no AI
    call), keeping the replay reproducible and free.
    """

    if ai_service is None and zone_audit_cache is None:
        return 0, []
    if subtotal < _AI_REVIEW_SUBTOTAL_THRESHOLD:
        return 0, []
    if selected is None:
        return 0, []
    review = review_zone_with_cache(
        _ai_zone_review_data(side, selected, smc, price, atr_value),
        zone_audit_cache,
        ai_service,
    )
    if review.get("status") != "valid":
        return 0, []
    if float(review.get("confidence") or 0.0) < _AI_REVIEW_MIN_CONFIDENCE:
        return 0, []
    combined = (
        float(review.get("zone_validity") or 0.0)
        + float(review.get("displacement_quality") or 0.0)
    ) / 2
    if combined > _AI_ZONE_WEAK_COMBINED_THRESHOLD:
        return 0, []
    return _AI_ZONE_WEAK_PENALTY, [AI_ZONE_WEAK_REASON]


def _ai_zone_review_data(
    side: str,
    selected: SelectedSmcZone,
    smc: dict[str, Any],
    price: float | None,
    atr_value: float | None,
) -> dict[str, Any]:
    timeframe_data = smc.get(selected.timeframe, {})
    if not isinstance(timeframe_data, dict):
        timeframe_data = {}
    return {
        "zone_id": selected.zone_id,
        "symbol": smc.get("symbol"),
        "zone_type": selected.zone_type,
        "family": selected.family,
        "direction": side,
        "timeframe": selected.timeframe,
        "low": selected.low,
        "high": selected.high,
        "price": price,
        "atr": atr_value,
        "displacement": timeframe_data.get("displacement"),
        "liquidity": timeframe_data.get("zone_link_sweeps"),
        "liquidity_sweep_linked": selected.liquidity_sweep_linked,
    }


def _m15_confirmation_penalty(
    side: str,
    selected: SelectedSmcZone | None,
    m15_candles: Any | None,
) -> tuple[int, list[str]]:
    """M15 confirmation at the selected zone.

    When M15 candles are available and a zone was selected, the zone's M15
    reaction is evaluated.  A tested zone without confirmation subtracts
    points; confirmation, an untested zone and insufficient data only trace
    reason codes (asymmetric: confirmation never adds points).  Without M15
    data the step is inert, keeping callers that do not supply candles on
    the previous behaviour.
    """

    if m15_candles is None:
        return 0, []
    if selected is None:
        return 0, []
    result = evaluate_m15_confirmation(
        side,
        selected.low,
        selected.high,
        m15_candles,
    )
    penalty = int(result.get("penalty") or 0)
    reasons = [
        str(code)
        for code in result.get("reason_codes", [])
        if str(code).strip()
    ]
    return penalty, reasons


def _zone_payloads(
    timeframe_data: dict[str, Any],
    side: str,
):
    keys = (
        ("demand", "demand_zones"),
        ("order_block", "order_blocks"),
        ("fvg", "fvg"),
    ) if side == "buy" else (
        ("supply", "supply_zones"),
        ("order_block", "order_blocks"),
        ("fvg", "fvg"),
    )
    for family, key in keys:
        values = timeframe_data.get(key, [])
        if not isinstance(values, list):
            continue
        for value in values:
            if isinstance(value, dict):
                yield family, value


def _zone_direction(zone: dict[str, Any], family: str) -> str:
    explicit = str(zone.get("direction", "") or "").lower()
    if explicit in {"buy", "sell"}:
        return explicit
    zone_type = str(zone.get("type", "") or "").lower()
    if "bullish" in zone_type or "demand" in zone_type:
        return "buy"
    if "bearish" in zone_type or "supply" in zone_type:
        return "sell"
    return "buy" if family == "demand" else "sell"


def _distance_to_zone(price: float, low: float, high: float) -> float:
    if price < low:
        return low - price
    if price > high:
        return price - high
    return 0.0


def _normalize_side(value: object) -> str:
    side = str(value or "").strip().lower()
    if side not in {"buy", "sell"}:
        raise ValueError(f"Invalid SMC side: {value}")
    return side


def _bounded_component(value: object, maximum: int) -> int:
    try:
        return max(0, min(maximum, int(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _positive_float(value: object) -> float | None:
    result = _optional_float(value)
    return result if result is not None and result > 0 else None


def _finite_float(value: object, default: float) -> float:
    result = _optional_float(value)
    return result if result is not None else default


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if isfinite(result) else None
