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
from core.smc_context import extract_smc_trade_flags


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


def score_scenario(
    side: str,
    technical: dict[str, Any],
    smc: dict[str, Any] | None,
    risk_score: float,
    macro_score: int,
    *,
    macro_confidence: float = 1.0,
    market_regime: dict[str, Any] | None = None,
    correlation_adjustment: float = 0.0,
    macro_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    trend = trend_alignment_score(side, technical)
    momentum = momentum_alignment_score(side, technical)
    location = location_quality_score(side, technical)
    smc_quality, smc_reason = smc_quality_score(side, smc or {})

    weights = DYNAMIC_WEIGHTS.get(
        _resolve_regime_key(market_regime or {}),
        DYNAMIC_WEIGHTS["unknown"],
    )

    trend_scaled = int(clamp(trend, 0, 25) * weights["trend"] / 25)
    momentum_scaled = int(clamp(momentum, 0, 20) * weights["momentum"] / 20)
    location_scaled = int(clamp(location, 0, 25) * weights["location"] / 25)
    smc_scaled = int(clamp(smc_quality, 0, 15) * weights["smc"] / 15)
    tech_raw = int(clamp(trend, 0, 25) + clamp(momentum, 0, 20) + clamp(location, 0, 25))
    technical_scaled = int(trend_scaled + momentum_scaled + location_scaled + smc_scaled)

    macro_raw = int(clamp(macro_score, 0, 30))
    macro_cap = int(weights["macro"])
    macro_effective = int(macro_raw * clamp(macro_confidence, 0.0, 1.0) * macro_cap / 30)
    macro_effective = int(clamp(macro_effective + int(correlation_adjustment), 0, macro_cap))

    risk_scaled = int(clamp(risk_score, 0, 15) * weights["risk"] / 15)

    # ── Normalized scoring: scale technical+risk to fill budget not occupied by macro ──
    # When macro data is unavailable (neutral 15/15), macro_effective only reaches
    # ~50% of macro_cap. Without normalization, total scores are artificially depressed.
    # This scales the non-macro portion so 0-100 means "best possible given available data".
    non_macro_weight_keys = ["trend", "momentum", "location", "smc", "risk"]
    non_macro_max = sum(int(weights[k]) for k in non_macro_weight_keys)
    non_macro_score = technical_scaled + risk_scaled
    available_budget = max(0, 100 - macro_effective)

    if non_macro_max > 0:
        normalized_non_macro = int(non_macro_score * available_budget / non_macro_max)
    else:
        normalized_non_macro = 0

    total = int(clamp(normalized_non_macro + macro_effective, 0, 100))

    # ---- Macro modifier (Phase 4 Prompt 2) ----
    macro_status = _detect_macro_status(macro_context, side)
    reason_codes: list[str] = []
    penalty_codes: list[str] = []
    macro_modifier = 0

    if macro_status == "conflict":
        macro_modifier = int(-15 * macro_confidence)
        append_code(penalty_codes, MACRO_CONFLICT)
    elif macro_status == "unclear":
        append_code(penalty_codes, MACRO_UNCLEAR)
    elif macro_status == "aligned":
        macro_modifier = int(5 * macro_confidence)
        append_code(reason_codes, MACRO_ALIGNED)

    total = int(clamp(total + macro_modifier, 0, 100))

    # ---- SMC CHOCH cap (Phase 5 Prompt 3) ----
    smc_flags = extract_smc_trade_flags(smc, side)
    smc_score_cap = None
    if smc_flags.get("choch_against_direction"):
        total = min(total, 60)
        smc_score_cap = 60
        append_code(penalty_codes, CHOCH_AGAINST_DIRECTION)

    return {
        "trend_alignment": int(clamp(trend, 0, 25)),
        "momentum_alignment": int(clamp(momentum, 0, 20)),
        "location_quality": int(clamp(location, 0, 25)),
        "smc_quality": smc_quality,
        "smc_reason": smc_reason,
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
        "macro_modifier": macro_modifier,
        "reason_codes": normalize_codes(reason_codes),
        "penalty_codes": normalize_codes(penalty_codes),
        "smc_score_cap": smc_score_cap,
        "smc_flags": smc_flags,
        "entry_quality_bonus": 0,
    }


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
    return int(clamp(rsi_score + macd_score, 0, 20))


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


def smc_quality_score(side: str, smc: dict[str, Any]) -> tuple[int, str]:
    h4 = smc.get("H4", {}) if isinstance(smc, dict) else {}
    h1 = smc.get("H1", {}) if isinstance(smc, dict) else {}
    expected = "bullish" if side == "buy" else "bearish"
    opposite = "bearish" if side == "buy" else "bullish"
    score = 0
    reasons: list[str] = []

    if h4.get("displacement") == expected and h4.get("bos"):
        score += 3
        reasons.append(f"H4 BOS {expected}")
    if h1.get("displacement") == expected and (h1.get("bos") or h1.get("choch")):
        score += 3
        reasons.append(f"H1 {'BOS' if h1.get('bos') else 'CHOCH'} {expected}")

    zone = _best_smc_zone(side, h4)
    if zone:
        zone_score = int(zone.get("zone_score", 0) or 0)
        if zone_score >= 75:
            zone_points = 4
        elif zone_score >= 55:
            zone_points = 3
        else:
            zone_points = 1
        if zone.get("broken"):
            zone_points = 0
        if zone.get("mitigated"):
            zone_points = max(0, zone_points - 1)
        if int(zone.get("test_count", 0) or 0) >= 3:
            zone_points = max(0, zone_points - 1)
        score += zone_points
        reasons.append(f"zone_score={zone_score}")

        location = str(zone.get("zone_location", "unknown"))
        if (side == "buy" and location == "discount") or (side == "sell" and location == "premium"):
            score += 3
            reasons.append(location)
        elif location == "equilibrium":
            score += 1
            reasons.append("equilibrium")
        elif location in {"premium", "discount"}:
            score -= 2
            reasons.append(f"ngược vị trí {location}")

        if zone.get("liquidity_sweep"):
            score += 1
            reasons.append("liquidity sweep")
    else:
        reasons.append("không có SMC zone thuận")

    sweeps = h1.get("liquidity_sweeps", {}) if isinstance(h1, dict) else {}
    if side == "buy" and sweeps.get("swept_lows"):
        score += 2
        reasons.append("sweep low H1")
    if side == "sell" and sweeps.get("swept_highs"):
        score += 2
        reasons.append("sweep high H1")

    if h4.get("choch") and h4.get("displacement") == opposite:
        score = min(score, 4)
        reasons.append(f"cap: H4 CHOCH {opposite}")
    if h1.get("choch") and h1.get("displacement") == opposite:
        score = min(score, 6)
        reasons.append(f"cap: H1 CHOCH {opposite}")

    score = int(clamp(score, 0, 15))
    return score, "; ".join(reasons) if reasons else "SMC chưa có tín hiệu rõ."


def _best_smc_zone(side: str, h4: dict[str, Any]) -> dict[str, Any] | None:
    zone_keys = ["demand_zones", "order_blocks", "fvg"] if side == "buy" else ["supply_zones", "order_blocks", "fvg"]
    candidates: list[dict[str, Any]] = []
    for key in zone_keys:
        zones = h4.get(key, [])
        if not isinstance(zones, list):
            continue
        for zone in zones:
            if not isinstance(zone, dict) or zone.get("broken"):
                continue
            zone_type = str(zone.get("type", ""))
            if side == "buy" and any(term in zone_type for term in ("bearish", "supply")):
                continue
            if side == "sell" and any(term in zone_type for term in ("bullish", "demand")):
                continue
            candidates.append(zone)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: int(item.get("zone_score", 0) or 0), reverse=True)[0]


def calc_risk_condition(atr_current: float, atr_avg_14d: float, news_in_3h: bool, spread_status: str) -> int:
    score = 0
    if atr_avg_14d and 0.8 * atr_avg_14d <= atr_current <= 1.2 * atr_avg_14d:
        score += 6
    elif atr_avg_14d and atr_current <= 1.5 * atr_avg_14d:
        score += 3
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
        Ket qua score_scenario() cho phep mua.
    sell_result : dict | None
        Ket qua score_scenario() cho phep ban.
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


