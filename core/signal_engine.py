from __future__ import annotations

from typing import Any

from core.reason_codes import (
    CHOCH_AGAINST_DIRECTION,
    MACRO_ALIGNED,
    MACRO_CONFLICT,
    MACRO_UNCLEAR,
    append_code,
    normalize_codes,
)


def clamp(value: float, min_value: float = 0.0, max_value: float = 100.0) -> float:
    return max(min_value, min(max_value, value))


def best_side(buy_score: float, sell_score: float, threshold: float = 10.0) -> str:
    delta = buy_score - sell_score
    if delta >= threshold:
        return "buy"
    if delta <= -threshold:
        return "sell"
    return "neutral"


DYNAMIC_WEIGHTS: dict[str, dict[str, int]] = {
    "trending_up":   {"trend": 25, "momentum": 15, "location": 15, "smc": 15, "risk": 15, "macro": 15},
    "trending_down": {"trend": 25, "momentum": 15, "location": 15, "smc": 15, "risk": 15, "macro": 15},
    "ranging":       {"trend": 10, "momentum": 10, "location": 25, "smc": 25, "risk": 15, "macro": 15},
    "volatile":      {"trend": 10, "momentum": 5,  "location": 15, "smc": 10, "risk": 40, "macro": 20},
    "unknown":       {"trend": 18, "momentum": 14, "location": 17, "smc": 15, "risk": 16, "macro": 20},
}


def _resolve_regime_key(market_regime: dict[str, Any]) -> str:
    primary = str(market_regime.get("primary", "unknown"))
    secondary: list[str] = market_regime.get("secondary", []) if isinstance(market_regime.get("secondary"), list) else []
    if "volatile" in secondary or primary == "volatile":
        return "volatile"
    if primary == "trend_up":
        return "trending_up"
    if primary == "trend_down":
        return "trending_down"
    if primary == "range":
        return "ranging"
    return "unknown"


def _detect_macro_status(macro_context: dict[str, Any] | None, direction: str) -> str:
    """Xac dinh macro aligned/conflict/unclear dua tren du lieu macro context.

    Ho tro:
    - bias key truc tiep: "buy"/"bullish"/"long" hoac "sell"/"bearish"/"short"
    - macro_alignment_scores: {"buy": N, "sell": M} — so sanh buy vs sell
    Tra ve "unclear" neu thieu du lieu hoac trung lap.
    """
    if not isinstance(macro_context, dict):
        return "unclear"

    bias = str(macro_context.get("bias", "")).lower()
    if bias in ("buy", "bullish", "long"):
        return "aligned" if direction == "buy" else "conflict"
    if bias in ("sell", "bearish", "short"):
        return "aligned" if direction == "sell" else "conflict"
    if bias in ("neutral", "mixed"):
        return "unclear"

    buy_score = macro_context.get("buy")
    sell_score = macro_context.get("sell")
    try:
        buy_score = int(buy_score) if buy_score is not None else 15
        sell_score = int(sell_score) if sell_score is not None else 15
    except (TypeError, ValueError):
        return "unclear"

    if direction == "buy" and buy_score > sell_score + 5:
        return "aligned"
    if direction == "sell" and sell_score > buy_score + 5:
        return "aligned"
    if direction == "buy" and sell_score > buy_score + 5:
        return "conflict"
    if direction == "sell" and buy_score > sell_score + 5:
        return "conflict"

    return "unclear"


def compose_scenario_score(
    side: str,
    technical: dict[str, Any],
    *,
    smc_quality: object,
    smc_reason: object = "",
    smc_flags: dict[str, Any] | None = None,
    risk_score: float = 0.0,
    macro_score: int = 0,
    macro_confidence: float = 1.0,
    market_regime: dict[str, Any] | None = None,
    correlation_adjustment: float = 0.0,
    macro_context: dict[str, Any] | None = None,
    scoring_version: object = None,
    smc_score_breakdown: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compose one side's scenario score from a precomputed SMC side result.

    This is the single composition path.  The caller supplies the already-scored
    SMC side (``smc_quality``, reason, flags, optional breakdown) so no SMC
    scorer is invoked here.  Regime weights, the CHOCH cap, penalty cleanup and
    score clamping are preserved exactly as in the legacy path.
    """

    trend = trend_alignment_score(side, technical)
    momentum = momentum_alignment_score(side, technical)
    location = location_quality_score(side, technical)
    try:
        quality = int(clamp(float(smc_quality), 0, 15))
    except (TypeError, ValueError, OverflowError):
        quality = 0

    base_weights = DYNAMIC_WEIGHTS.get(
        _resolve_regime_key(market_regime or {}),
        DYNAMIC_WEIGHTS["unknown"],
    )
    macro_cap = int(base_weights["macro"])
    conf = clamp(macro_confidence, 0.0, 1.0)
    effective_macro_weight = int(macro_cap * conf)
    weights = dict(base_weights)
    weights["macro"] = effective_macro_weight
    # Phase 15B: surplus weight from reduced macro confidence is DISCARDED,
    # NOT redistributed to technical categories.  This ensures lower
    # confidence never increases signal_score.

    trend_scaled = int(clamp(trend, 0, 25) * weights["trend"] / 25)
    momentum_scaled = int(clamp(momentum, 0, 20) * weights["momentum"] / 20)
    location_scaled = int(clamp(location, 0, 25) * weights["location"] / 25)
    smc_scaled = int(quality * weights["smc"] / 15)
    tech_raw = int(clamp(trend, 0, 25) + clamp(momentum, 0, 20) + clamp(location, 0, 25))
    technical_scaled = int(trend_scaled + momentum_scaled + location_scaled + smc_scaled)

    macro_raw = int(clamp(macro_score, 0, 30))
    macro_effective = int(macro_raw * effective_macro_weight / 30)
    macro_effective = int(clamp(macro_effective + int(correlation_adjustment), 0, effective_macro_weight))

    risk_scaled = int(clamp(risk_score, 0, 15) * weights["risk"] / 15)

    # Direct sum — weights already sum to 100, no normalization needed.
    # When macro data is weak or unavailable, the total naturally caps lower,
    # which is correct for cross-pair comparison.
    total = int(clamp(technical_scaled + risk_scaled + macro_effective, 0, 100))

    # ---- Macro status (display-only, does not affect score) ----
    macro_status = _detect_macro_status(macro_context, side)
    reason_codes: list[str] = []
    penalty_codes: list[str] = []

    if macro_status == "conflict":
        append_code(penalty_codes, MACRO_CONFLICT)
    elif macro_status == "unclear":
        append_code(penalty_codes, MACRO_UNCLEAR)
    elif macro_status == "aligned":
        append_code(reason_codes, MACRO_ALIGNED)

    # ---- SMC CHOCH cap (Phase 5 Prompt 3) ----
    flags = dict(smc_flags or {})
    smc_score_cap = None
    if flags.get("choch_against_direction"):
        total = min(total, 60)
        smc_score_cap = 60
        append_code(penalty_codes, CHOCH_AGAINST_DIRECTION)

    result = {
        "trend_alignment": int(clamp(trend, 0, 25)),
        "momentum_alignment": int(clamp(momentum, 0, 20)),
        "location_quality": int(clamp(location, 0, 25)),
        "smc_quality": quality,
        "smc_reason": str(smc_reason or ""),
        "technical_raw": tech_raw,
        "trend_scaled": trend_scaled,
        "momentum_scaled": momentum_scaled,
        "location_scaled": location_scaled,
        "smc_scaled": smc_scaled,
        "technical_scaled": technical_scaled,
        "risk_condition": risk_scaled,
        "macro_alignment": macro_effective,
        "macro_raw": macro_raw,
        "macro_confidence": round(macro_confidence, 2),
        "correlation_adjustment": correlation_adjustment,
        "regime_weights": weights,
        "signal_score": total,
        "total": total,  # deprecated, kept for backward compatibility
        "rating": score_rating(total),
        "macro_status": macro_status,
        "reason_codes": normalize_codes(reason_codes),
        "penalty_codes": normalize_codes(penalty_codes),
        "smc_score_cap": smc_score_cap,
        "smc_flags": flags,
    }
    if scoring_version is not None:
        result["smc_scoring_version"] = str(scoring_version or "")
    if smc_score_breakdown is not None:
        result["smc_score_breakdown"] = dict(smc_score_breakdown or {})
    return result


def score_rating(score: int) -> str:
    if score >= 80:
        return "chất lượng cao"
    if score >= 65:
        return "cân nhắc được"
    if score >= 50:
        return "chờ thêm tín hiệu"
    return "đứng ngoài"


def trend_alignment_score(side: str, t: dict[str, Any]) -> int:
    price = t["price"]
    if side == "buy":
        return sum(
            [
                8 if t["ema50_d1"] > t["ema200_d1"] else 0,
                5 if price > t["ema200_d1"] else 0,
                5 if price > t["ema50_d1"] or price > t["ema50_h4"] else 0,
                5 if t["structure_h4"] == "HH/HL" else 0,
                2 if t["structure_d1"] == "HH/HL" and t["structure_h4"] == "HH/HL" else 0,
            ]
        )
    return sum(
        [
            8 if t["ema50_d1"] < t["ema200_d1"] else 0,
            5 if price < t["ema200_d1"] else 0,
            5 if price < t["ema50_d1"] or price < t["ema50_h4"] else 0,
            5 if t["structure_h4"] == "LH/LL" else 0,
            2 if t["structure_d1"] == "LH/LL" and t["structure_h4"] == "LH/LL" else 0,
        ]
    )


def momentum_alignment_score(side: str, t: dict[str, Any]) -> int:
    value = t["rsi_h4"] or 50.0
    previous_value = t.get("rsi_h4_previous")
    prev_value = value if previous_value is None else previous_value
    rsi_rising = value > prev_value
    rsi_falling = value < prev_value
    hist = t["macd_histogram_h4"]
    now = hist["value"]
    prev = hist["previous_value"]
    prev2 = hist["previous2_value"]
    if side == "buy":
        rsi_score = _choose_one(
            [
                (30 <= value <= 50 and rsi_rising, 8),
                (40 <= value <= 60 and not rsi_falling, 6),
                (60 < value <= 70 and not rsi_falling, 3),
                (value > 75, 0),
            ]
        )
        macd_score = _choose_one(
            [
                (now > 0 and now > prev > prev2, 10),
                (now < 0 and now > prev > prev2, 6),
                (now > prev, 3),
                (now > 0 and now < prev, 5),
            ]
        )
    else:
        rsi_score = _choose_one(
            [
                (50 <= value <= 70 and rsi_falling, 8),
                (40 <= value <= 60 and not rsi_rising, 6),
                (30 <= value < 40 and not rsi_rising, 3),
                (value < 25, 0),
            ]
        )
        macd_score = _choose_one(
            [
                (now < 0 and now < prev < prev2, 10),
                (now > 0 and now < prev < prev2, 6),
                (now < prev, 3),
                (now < 0 and now > prev, 5),
            ]
        )
    macd_direction = hist.get("direction", "flat")
    macd_accel = macd_direction == "increasing"
    accel_bonus = 0
    if side == "buy":
        if rsi_rising and macd_accel:
            accel_bonus = 2
        elif not rsi_rising and not macd_accel:
            accel_bonus = -2
    else:
        if rsi_falling and not macd_accel:
            accel_bonus = 2
        elif not rsi_falling and macd_accel:
            accel_bonus = -2
    return int(clamp(rsi_score + macd_score + accel_bonus, 0, 20))


def _choose_one(candidates: list[tuple[bool, int]]) -> int:
    for condition, score in candidates:
        if condition:
            return score
    return 0


def location_quality_score(side: str, t: dict[str, Any]) -> int:
    from core.technical_context import distance_to_zone, nearest_zone, price_in_zone

    price = t["price"]
    atr_value = t["atr_h4"] or t["atr_d1"] or 0.0
    supports = t["support_zones"]
    resistances = t["resistance_zones"]
    nearest_support = nearest_zone(price, supports)
    nearest_resistance = nearest_zone(price, resistances)

    if side == "buy":
        if nearest_support and price_in_zone(price, nearest_support):
            base = 15
        elif nearest_support and distance_to_zone(price, nearest_support) <= atr_value * 0.5:
            base = 10
        elif nearest_resistance and price_in_zone(price, nearest_resistance):
            base = 0
        else:
            base = 3
        bonus_zone = nearest_support
    else:
        if nearest_resistance and price_in_zone(price, nearest_resistance):
            base = 15
        elif nearest_resistance and distance_to_zone(price, nearest_resistance) <= atr_value * 0.5:
            base = 10
        elif nearest_support and price_in_zone(price, nearest_support):
            base = 0
        else:
            base = 3
        bonus_zone = nearest_resistance

    bonus = 0
    if bonus_zone:
        test_count = bonus_zone.get("test_count", 0)
        if test_count >= 3:
            bonus -= 5
        if test_count >= 5:
            bonus -= 3
        if bonus_zone.get("confluence_count", 0) >= 3:
            bonus += 5
        if bonus_zone.get("is_round_number"):
            bonus += 3
    return int(clamp(base + bonus, 0, 25))


def calc_risk_condition(atr_current: float, atr_avg_14d: float, news_in_3h: bool, spread_status: str) -> int:
    """Market risk gate — volatility, news, spread. Distinct from trade-level risk in risk_engine.py."""
    score = 0
    if atr_avg_14d and atr_current > 0:
        ratio = atr_current / atr_avg_14d
        if 0.9 <= ratio <= 1.1:
            score += 6
        elif 0.8 <= ratio <= 1.2:
            score += 5
        elif 0.7 <= ratio <= 1.3:
            score += 3
        elif ratio <= 1.5:
            score += 1
    score += 0 if news_in_3h else 6
    score += 3 if spread_status == "normal" else 0
    return int(clamp(score, 0, 15))


def detect_direction_bias(
    side: str, best_score: int, scores: dict[str, dict[str, Any]], market_regime: dict[str, Any]
) -> str:
    buy_total = scores["buy"].get("signal_score", scores["buy"].get("total", 0))
    sell_total = scores["sell"].get("signal_score", scores["sell"].get("total", 0))
    if best_score < 50 or (buy_total < 50 and sell_total < 50):
        return "stand_aside"
    if market_regime["primary"] == "range" and best_score < 75:
        return "neutral"
    bias_result = calculate_direction_bias(scores["buy"], scores["sell"])
    if bias_result["is_clear_bias"] and bias_result["best_side"] == side:
        return side
    return "neutral"


def calculate_direction_bias(
    buy_result: dict[str, Any] | None,
    sell_result: dict[str, Any] | None,
    min_gap: float = 10.0,
) -> dict[str, Any]:
    """Tinh direction bias va score_gap giua BUY va SELL.

    Parameters
    ----------
    buy_result : dict | None
        Ket qua compose_scenario_score() cho phep mua.
    sell_result : dict | None
        Ket qua compose_scenario_score() cho phep ban.
    min_gap : float
        Nguong toi thieu de coi huong la ro rang (mac dinh 10.0).

    Returns
    -------
    dict
        {
            "best_side": "buy" | "sell" | "neutral",
            "buy_score": float,
            "sell_score": float,
            "score_gap": float,
            "is_clear_bias": bool,
            "min_gap": float,
        }
    """
    buy = buy_result if isinstance(buy_result, dict) else {}
    sell = sell_result if isinstance(sell_result, dict) else {}

    buy_score = float(buy.get("signal_score", buy.get("total", 0)) or 0)
    sell_score = float(sell.get("signal_score", sell.get("total", 0)) or 0)

    score_gap = abs(buy_score - sell_score)

    if buy_score > sell_score:
        best_side = "buy"
    elif sell_score > buy_score:
        best_side = "sell"
    else:
        best_side = "neutral"

    is_clear_bias = score_gap >= min_gap if best_side != "neutral" else False

    return {
        "best_side": best_side,
        "buy_score": buy_score,
        "sell_score": sell_score,
        "score_gap": score_gap,
        "is_clear_bias": is_clear_bias,
        "min_gap": min_gap,
    }


