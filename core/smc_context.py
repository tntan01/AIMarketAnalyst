from __future__ import annotations

from typing import Any

from core.market_models import Candle


def build_smc_context(d1: list[Candle], h4: list[Candle], h1: list[Candle]) -> dict[str, Any]:
    return {
        "D1": _smc_for_timeframe(d1),
        "H4": _smc_for_timeframe(h4),
        "H1": _smc_for_timeframe(h1),
    }


def summarize_structure(candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 3:
        return {"structure": "insufficient_data"}
    swings = swing_points(candles, lookback=2)
    bos_choch = detect_bos_choch(swings, candles)
    structure = bos_choch.get("structure", "unknown")
    return {
        "structure": structure,
        "bos": bos_choch.get("bos", False),
        "choch": bos_choch.get("choch", False),
        "displacement": bos_choch.get("displacement", "neutral"),
        "swings": swings,
    }


def _smc_for_timeframe(candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 6:
        return {
            "structure": "insufficient_data",
            "bos": False,
            "choch": False,
            "displacement": "neutral",
            "swings": {"highs": [], "lows": []},
            "supply_zones": [],
            "demand_zones": [],
            "order_blocks": [],
            "fvg": [],
            "liquidity_pools": {"equal_highs": [], "equal_lows": [], "swing_highs": [], "swing_lows": []},
            "liquidity_sweeps": {"swept_highs": [], "swept_lows": []},
            "premium_discount": "unknown",
            "premium_discount_range": {"status": "unknown"},
        }
    swings = swing_points(candles, lookback=2)
    bos = detect_bos_choch(swings, candles)
    liquidity = detect_liquidity_pools(candles, swings)
    premium_discount = classify_premium_discount(candles[-1].close, swings)
    premium_discount_range = premium_discount_bounds(swings)
    fvg = detect_fvg(candles)
    order_blocks = detect_order_blocks(candles, fvg)
    demand_zones, supply_zones = detect_supply_demand_zones(candles)
    liquidity_sweeps = detect_liquidity_sweeps(candles, swings)
    demand_zones = enrich_zones(demand_zones, candles, "demand", liquidity_sweeps, premium_discount_range)
    supply_zones = enrich_zones(supply_zones, candles, "supply", liquidity_sweeps, premium_discount_range)
    order_blocks = enrich_zones(order_blocks, candles, "order_block", liquidity_sweeps, premium_discount_range)
    fvg = enrich_zones(fvg, candles, "fvg", liquidity_sweeps, premium_discount_range)
    return {
        "structure": bos.get("structure", "unknown"),
        "bos": bos.get("bos", False),
        "choch": bos.get("choch", False),
        "displacement": bos.get("displacement", "neutral"),
        "swings": swings,
        "supply_zones": supply_zones,
        "demand_zones": demand_zones,
        "order_blocks": order_blocks,
        "fvg": fvg,
        "liquidity_pools": liquidity,
        "liquidity_sweeps": liquidity_sweeps,
        "premium_discount": premium_discount,
        "premium_discount_range": premium_discount_range,
    }


def swing_points(candles: list[Candle], lookback: int = 2) -> dict[str, list[dict[str, Any]]]:
    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []
    for index in range(lookback, len(candles) - lookback):
        window = candles[index - lookback : index + lookback + 1]
        candle = candles[index]
        if candle.high == max(item.high for item in window) and sum(candle.high == item.high for item in window) == 1:
            highs.append({"level": candle.high, "index": index, "time": candle.time.isoformat()})
        if candle.low == min(item.low for item in window) and sum(candle.low == item.low for item in window) == 1:
            lows.append({"level": candle.low, "index": index, "time": candle.time.isoformat()})
    return {"highs": highs, "lows": lows}


def detect_bos_choch(swings: dict[str, list[dict[str, Any]]], candles: list[Candle]) -> dict[str, Any]:
    highs = swings["highs"]
    lows = swings["lows"]
    if len(highs) < 2 or len(lows) < 2 or not candles:
        return {"structure": "unknown", "bos": False, "choch": False, "displacement": "neutral"}

    last_high = highs[-1]["level"]
    prev_high = highs[-2]["level"]
    last_low = lows[-1]["level"]
    prev_low = lows[-2]["level"]
    last_close = candles[-1].close

    if last_high > prev_high and last_low > prev_low:
        structure = "HH/HL"
        prev_trend = "up"
    elif last_high < prev_high and last_low < prev_low:
        structure = "LH/LL"
        prev_trend = "down"
    else:
        structure = "mixed"
        prev_trend = "mixed"

    bos = False
    choch = False
    displacement = "neutral"

    if prev_trend == "up" and last_close > last_high:
        bos = True
        displacement = "bullish"
    elif prev_trend == "down" and last_close < last_low:
        bos = True
        displacement = "bearish"
    elif prev_trend == "up" and last_close < prev_low:
        choch = True
        displacement = "bearish"
    elif prev_trend == "down" and last_close > prev_high:
        choch = True
        displacement = "bullish"

    return {"structure": structure, "bos": bos, "choch": choch, "displacement": displacement}


def detect_fvg(candles: list[Candle]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if len(candles) < 3:
        return gaps
    start = max(0, len(candles) - 80)
    for index in range(start + 2, len(candles)):
        first = candles[index - 2]
        third = candles[index]
        if first.high < third.low:
            gaps.append(
                {
                    "type": "bullish_fvg",
                    "low": first.high,
                    "high": third.low,
                    "index": index,
                    "time": third.time.isoformat(),
                    "displacement_multiple": displacement_multiple_at(candles, index),
                }
            )
        elif first.low > third.high:
            gaps.append(
                {
                    "type": "bearish_fvg",
                    "low": third.high,
                    "high": first.low,
                    "index": index,
                    "time": third.time.isoformat(),
                    "displacement_multiple": displacement_multiple_at(candles, index),
                }
            )
    return gaps[-6:]


def detect_order_blocks(candles: list[Candle], fvg: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if len(candles) < 4:
        return blocks
    fvg_indices = {item["index"]: item for item in fvg}
    start = max(0, len(candles) - 80)
    for index in range(start + 1, len(candles) - 1):
        candle = candles[index]
        nxt = candles[index + 1]
        is_bearish = candle.close < candle.open
        is_bullish = candle.close > candle.open
        impulse_up = nxt.close > candle.high
        impulse_down = nxt.close < candle.low
        if is_bearish and impulse_up:
            blocks.append(
                {
                    "type": "bullish_order_block",
                    "low": candle.low,
                    "high": candle.high,
                    "index": index,
                    "time": candle.time.isoformat(),
                    "has_fvg_above": (index + 2) in fvg_indices,
                    "displacement_multiple": displacement_multiple_at(candles, index + 1),
                }
            )
        elif is_bullish and impulse_down:
            blocks.append(
                {
                    "type": "bearish_order_block",
                    "low": candle.low,
                    "high": candle.high,
                    "index": index,
                    "time": candle.time.isoformat(),
                    "has_fvg_below": (index + 2) in fvg_indices,
                    "displacement_multiple": displacement_multiple_at(candles, index + 1),
                }
            )
    return blocks[-6:]


def detect_supply_demand_zones(candles: list[Candle]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    demand: list[dict[str, Any]] = []
    supply: list[dict[str, Any]] = []
    if len(candles) < 8:
        return demand, supply

    avg_range = sum(candle.high - candle.low for candle in candles[-50:]) / max(1, min(50, len(candles)))
    impulse_threshold = avg_range * 1.5 if avg_range > 0 else 0.0
    consolidation_bars = 3

    start = max(consolidation_bars, len(candles) - 80)
    for index in range(start, len(candles) - 1):
        impulse = candles[index]
        impulse_size = impulse.high - impulse.low
        if impulse_size <= impulse_threshold:
            continue
        base = candles[index - consolidation_bars : index]
        if not base:
            continue
        base_high = max(candle.high for candle in base)
        base_low = min(candle.low for candle in base)
        base_range = base_high - base_low
        if avg_range > 0 and base_range > avg_range * 1.2:
            continue

        is_bullish_impulse = impulse.close > impulse.open and impulse.close > base_high
        is_bearish_impulse = impulse.close < impulse.open and impulse.close < base_low
        if is_bullish_impulse:
            demand.append(
                {
                    "type": "demand_zone",
                    "low": base_low,
                    "high": base_high,
                    "index": index - 1,
                    "time": base[-1].time.isoformat(),
                    "consolidation_bars": consolidation_bars,
                    "displacement_multiple": round(impulse_size / avg_range, 2) if avg_range else 0,
                    "liquidity_sweep": swept_recent_low(impulse, candles[:index]),
                }
            )
        elif is_bearish_impulse:
            supply.append(
                {
                    "type": "supply_zone",
                    "low": base_low,
                    "high": base_high,
                    "index": index - 1,
                    "time": base[-1].time.isoformat(),
                    "consolidation_bars": consolidation_bars,
                    "displacement_multiple": round(impulse_size / avg_range, 2) if avg_range else 0,
                    "liquidity_sweep": swept_recent_high(impulse, candles[:index]),
                }
            )
    return demand[-5:], supply[-5:]


def detect_liquidity_pools(candles: list[Candle], swings: dict[str, list[dict[str, Any]]]) -> dict[str, list[float]]:
    if not candles:
        return {"equal_highs": [], "equal_lows": [], "swing_highs": [], "swing_lows": []}

    avg_range = sum(candle.high - candle.low for candle in candles[-50:]) / max(1, min(50, len(candles)))
    tolerance = max(avg_range * 0.15, 0.0001)

    swing_highs = [item["level"] for item in swings["highs"][-8:]]
    swing_lows = [item["level"] for item in swings["lows"][-8:]]

    equal_highs: list[float] = []
    equal_lows: list[float] = []
    for index, value in enumerate(swing_highs):
        for other in swing_highs[index + 1 :]:
            if abs(value - other) <= tolerance:
                equal_highs.append((value + other) / 2)
                break
    for index, value in enumerate(swing_lows):
        for other in swing_lows[index + 1 :]:
            if abs(value - other) <= tolerance:
                equal_lows.append((value + other) / 2)
                break

    return {
        "equal_highs": equal_highs[-3:],
        "equal_lows": equal_lows[-3:],
        "swing_highs": swing_highs[-3:],
        "swing_lows": swing_lows[-3:],
    }


def classify_premium_discount(price: float, swings: dict[str, list[dict[str, Any]]]) -> str:
    highs = [item["level"] for item in swings["highs"][-3:]]
    lows = [item["level"] for item in swings["lows"][-3:]]
    if not highs or not lows:
        return "unknown"
    high = max(highs)
    low = min(lows)
    if high == low:
        return "equilibrium"
    midpoint = (high + low) / 2
    if price >= midpoint + (high - low) * 0.05:
        return "premium"
    if price <= midpoint - (high - low) * 0.05:
        return "discount"
    return "equilibrium"


def premium_discount_bounds(swings: dict[str, list[dict[str, Any]]]) -> dict[str, float | str]:
    highs = [item["level"] for item in swings["highs"][-3:]]
    lows = [item["level"] for item in swings["lows"][-3:]]
    if not highs or not lows:
        return {"status": "unknown"}
    high = max(highs)
    low = min(lows)
    return {"status": "ok", "high": high, "low": low, "midpoint": (high + low) / 2}


def detect_liquidity_sweeps(candles: list[Candle], swings: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    if len(candles) < 3:
        return {"swept_highs": [], "swept_lows": []}
    recent = candles[-6:]
    swing_highs = swings["highs"][-6:]
    swing_lows = swings["lows"][-6:]
    swept_highs: list[dict[str, Any]] = []
    swept_lows: list[dict[str, Any]] = []
    for candle in recent:
        for swing in swing_highs:
            level = swing["level"]
            if candle.high > level and candle.close < level:
                swept_highs.append({"level": level, "time": candle.time.isoformat()})
                break
        for swing in swing_lows:
            level = swing["level"]
            if candle.low < level and candle.close > level:
                swept_lows.append({"level": level, "time": candle.time.isoformat()})
                break
    return {"swept_highs": swept_highs[-3:], "swept_lows": swept_lows[-3:]}


def enrich_zones(
    zones: list[dict[str, Any]],
    candles: list[Candle],
    family: str,
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    premium_discount_range: dict[str, float | str],
) -> list[dict[str, Any]]:
    enriched = []
    for zone in zones:
        item = dict(zone)
        index = int(item.get("index", len(candles) - 1))
        future = candles[index + 1 :] if index + 1 < len(candles) else []
        low = float(item.get("low", 0.0))
        high = float(item.get("high", 0.0))
        side = zone_side(item, family)
        test_count = count_zone_tests(future, low, high)
        broken = zone_broken(future, low, high, side)
        mitigated = test_count > 0
        freshness_bars = max(0, len(candles) - 1 - index)
        zone_location = zone_premium_discount(low, high, premium_discount_range)
        item.update(
            {
                "freshness_bars": freshness_bars,
                "mitigated": mitigated,
                "broken": broken,
                "test_count": test_count,
                "zone_location": zone_location,
                "liquidity_sweep": bool(item.get("liquidity_sweep")) or zone_has_sweep(side, liquidity_sweeps),
            }
        )
        item["zone_score"] = zone_quality_score(item, side)
        item["strength"] = score_to_strength(item["zone_score"])
        enriched.append(item)
    return sorted(enriched, key=lambda zone: zone.get("zone_score", 0), reverse=True)


def zone_side(zone: dict[str, Any], family: str) -> str:
    zone_type = str(zone.get("type", ""))
    if "demand" in zone_type or "bullish" in zone_type:
        return "buy"
    if "supply" in zone_type or "bearish" in zone_type:
        return "sell"
    return "buy" if family == "demand" else "sell"


def count_zone_tests(candles: list[Candle], low: float, high: float) -> int:
    return sum(1 for candle in candles if candle.low <= high and candle.high >= low)


def zone_broken(candles: list[Candle], low: float, high: float, side: str) -> bool:
    if side == "buy":
        return any(candle.close < low for candle in candles)
    return any(candle.close > high for candle in candles)


def zone_premium_discount(low: float, high: float, bounds: dict[str, float | str]) -> str:
    if bounds.get("status") != "ok":
        return "unknown"
    midpoint = float(bounds["midpoint"])
    center = (low + high) / 2
    width = max(float(bounds["high"]) - float(bounds["low"]), 1e-9)
    if center <= midpoint - width * 0.05:
        return "discount"
    if center >= midpoint + width * 0.05:
        return "premium"
    return "equilibrium"


def zone_has_sweep(side: str, liquidity_sweeps: dict[str, list[dict[str, Any]]]) -> bool:
    return bool(liquidity_sweeps.get("swept_lows" if side == "buy" else "swept_highs"))


def zone_quality_score(zone: dict[str, Any], side: str) -> int:
    """Cham diem chat luong SMC zone (0-100).

    Nguyen tac: zone da duoc test nhieu lan va giu duoc = dang tin cay hon
    zone moi hinh thanh chua tung bi test. Diem thuong cho:
    - Da test va giu duoc (toi da +20)
    - Con moi (toi da +10)
    - Displacement lon (toi da +15)
    - Quet liquidity (+10)
    - Nam dung vi tri premium/discount (+12)
    """
    score = 50
    test_count = int(zone.get("test_count", 0))
    # Zone da test nhieu lan + giu duoc = tin cay cao
    score += min(20, test_count * 5)
    # Zone con moi: bonus nhe (moi la tin hieu tot nhung chua duoc kiem chung)
    freshness = int(zone.get("freshness_bars", 999))
    score += max(0, 10 - freshness // 5)
    # Zone da bi broken = khong con gia tri
    score -= 35 if zone.get("broken") else 0
    # Displacement impulse: move cang manh → zone cang quan trong
    score += min(15, int(float(zone.get("displacement_multiple", 0)) * 5))
    # Liquidity sweep: quet stop-loss truoc khi dao chieu = tin hieu manh
    score += 10 if zone.get("liquidity_sweep") else 0
    # Vi tri trong cau truc premium/discount
    location = zone.get("zone_location")
    if (side == "buy" and location == "discount") or (side == "sell" and location == "premium"):
        score += 12
    elif location == "equilibrium":
        score += 4
    elif location in {"premium", "discount"}:
        score -= 8
    return max(0, min(100, int(score)))


def score_to_strength(score: int) -> str:
    if score >= 75:
        return "strong"
    if score >= 55:
        return "moderate"
    return "weak"


def displacement_multiple_at(candles: list[Candle], index: int) -> float:
    if index < 0 or index >= len(candles):
        return 0.0
    candle = candles[index]
    window = candles[max(0, index - 20) : index]
    avg_range = sum(item.high - item.low for item in window) / len(window) if window else 0.0
    if avg_range <= 0:
        return 0.0
    return round((candle.high - candle.low) / avg_range, 2)


def swept_recent_low(candle: Candle, previous: list[Candle]) -> bool:
    lows = [item.low for item in previous[-8:]]
    return bool(lows and candle.low < min(lows) and candle.close > min(lows))


def swept_recent_high(candle: Candle, previous: list[Candle]) -> bool:
    highs = [item.high for item in previous[-8:]]
    return bool(highs and candle.high > max(highs) and candle.close < max(highs))



# ---------------------------------------------------------------------------
# Phase 5: Safe SMC flag extraction for trade gate decisions
# ---------------------------------------------------------------------------


def _find_best_zone_for_direction(tf: dict[str, Any], direction: str) -> dict[str, Any] | None:
    """Tim zone SMC co zone_score cao nhat phu hop voi huong giao dich."""
    if not isinstance(tf, dict):
        return None

    if direction == "buy":
        zone_keys = ["demand_zones", "order_blocks", "fvg"]
    else:
        zone_keys = ["supply_zones", "order_blocks", "fvg"]

    candidates: list[dict[str, Any]] = []
    for key in zone_keys:
        zones = tf.get(key, [])
        if not isinstance(zones, list):
            continue
        for zone in zones:
            if not isinstance(zone, dict) or zone.get("broken"):
                continue
            zone_type = str(zone.get("type", ""))
            if direction == "buy" and any(term in zone_type for term in ("bearish", "supply")):
                continue
            if direction == "sell" and any(term in zone_type for term in ("bullish", "demand")):
                continue
            candidates.append(zone)

    if not candidates:
        return None
    return sorted(candidates, key=lambda item: int(item.get("zone_score", 0) or 0), reverse=True)[0]


def get_preferred_zone(smc_context: dict[str, Any] | None, direction: str, price: float | None = None) -> dict[str, Any] | None:
    """Tra ve zone SMC tot nhat cho huong giao dich, dung de truyen vao build_trade_plan.

    Tra ve dict co low, high, level, zone_score, source="smc_selected",
    hoac None neu khong tim thay zone phu hop.

    Khi price duoc cung cap, uu tien zone nam dung phia so voi gia:
    - buy: zone level < price (support)
    - sell: zone level > price (resistance)
    """
    if not isinstance(smc_context, dict):
        return None
    h4 = smc_context.get("H4", {})
    if not isinstance(h4, dict):
        return None

    # Gather all valid candidates (same logic as _find_best_zone_for_direction)
    if direction == "buy":
        zone_keys = ["demand_zones", "order_blocks", "fvg"]
    else:
        zone_keys = ["supply_zones", "order_blocks", "fvg"]

    candidates: list[dict[str, Any]] = []
    for key in zone_keys:
        zones = h4.get(key, [])
        if not isinstance(zones, list):
            continue
        for zone in zones:
            if not isinstance(zone, dict) or zone.get("broken"):
                continue
            zone_type = str(zone.get("type", ""))
            if direction == "buy" and any(term in zone_type for term in ("bearish", "supply")):
                continue
            if direction == "sell" and any(term in zone_type for term in ("bullish", "demand")):
                continue
            candidates.append(zone)

    if not candidates:
        return None

    # Sort by zone_score descending
    candidates.sort(key=lambda item: int(item.get("zone_score", 0) or 0), reverse=True)

    # Pick the best zone on the correct side of price (if price provided)
    zone = None
    if price is not None:
        for candidate in candidates:
            low = candidate.get("low")
            high = candidate.get("high")
            if low is None or high is None:
                continue
            level = (float(low) + float(high)) / 2
            if direction == "buy" and level < price:
                zone = candidate
                break
            if direction == "sell" and level > price:
                zone = candidate
                break

    # Fallback: use the highest-scored zone regardless of position
    if zone is None:
        zone = candidates[0]

    low = zone.get("low")
    high = zone.get("high")
    if low is None or high is None:
        return None
    return {
        "low": float(low),
        "high": float(high),
        "level": (float(low) + float(high)) / 2,
        "zone_score": zone.get("zone_score", 0),
        "source": "smc_selected",
    }


def extract_smc_trade_flags(smc_context: dict[str, Any] | None, direction: str) -> dict[str, Any]:
    """Trich xuat cac flag SMC an toan cho trade gate.

    Tra ve dict cac flag doc tu SMC context, khong crash neu thieu du lieu.
    Dung H4 lam timeframe chinh cho structural signals, H1 cho liquidity.

    Parameters
    ----------
    smc_context : dict | None
        Output cua build_smc_context().
    direction : str
        "buy" hoac "sell".

    Returns
    -------
    dict
        {
            "zone_broken": bool,
            "choch_against_direction": bool,
            "liquidity_sweep_aligned": bool,
            "displacement_aligned": bool,
            "has_selected_zone": bool,
            "selected_zone_type": str | None,
            "selected_zone_score": int | None,
            "raw": dict,
        }
    """
    result: dict[str, Any] = {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": False,
        "displacement_aligned": False,
        "has_selected_zone": False,
        "selected_zone_type": None,
        "selected_zone_score": None,
        "raw": {},
    }

    if not isinstance(smc_context, dict):
        return result

    if direction not in ("buy", "sell"):
        return result

    h4 = smc_context.get("H4", {}) if isinstance(smc_context.get("H4"), dict) else {}
    h1 = smc_context.get("H1", {}) if isinstance(smc_context.get("H1"), dict) else {}

    # --- CHOCH against direction ---
    if direction == "buy":
        if h4.get("choch") and h4.get("displacement") == "bearish":
            result["choch_against_direction"] = True
        if h1.get("choch") and h1.get("displacement") == "bearish":
            result["choch_against_direction"] = True
    else:  # sell
        if h4.get("choch") and h4.get("displacement") == "bullish":
            result["choch_against_direction"] = True
        if h1.get("choch") and h1.get("displacement") == "bullish":
            result["choch_against_direction"] = True

    # --- Liquidity sweep aligned ---
    liq_sweeps = h1.get("liquidity_sweeps", {}) if isinstance(h1, dict) else {}
    if direction == "buy" and liq_sweeps.get("swept_lows"):
        result["liquidity_sweep_aligned"] = True
    elif direction == "sell" and liq_sweeps.get("swept_highs"):
        result["liquidity_sweep_aligned"] = True

    # --- Displacement aligned ---
    expected_disp = "bullish" if direction == "buy" else "bearish"
    if h4.get("displacement") == expected_disp:
        result["displacement_aligned"] = True

    # --- Selected zone ---
    zone = _find_best_zone_for_direction(h4, direction)
    if zone:
        result["has_selected_zone"] = True
        result["selected_zone_type"] = zone.get("type")
        result["selected_zone_score"] = zone.get("zone_score")
        if zone.get("broken"):
            result["zone_broken"] = True

    # --- Raw snapshot ---
    result["raw"] = {
        "h4_structure": h4.get("structure"),
        "h4_bos": h4.get("bos"),
        "h4_choch": h4.get("choch"),
        "h4_displacement": h4.get("displacement"),
        "h1_liquidity_sweeps": bool(
            (isinstance(liq_sweeps, dict) and (liq_sweeps.get("swept_lows") or liq_sweeps.get("swept_highs")))
        ),
    }

    return result
