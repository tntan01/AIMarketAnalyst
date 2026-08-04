from __future__ import annotations

import logging
from typing import Any

from core.indicators import atr
from core.market_models import Candle
from core.smc_confluence import build_directional_confluence
from core.smc_lifecycle import analyze_zone_lifecycle
from core.smc_models import (
    SMC_DOMAIN_VERSION,
    SmcZone,
    build_zone_id,
)
from core.smc_sweep_linking import (
    SMC_SWEEP_LINK_VERSION,
    associate_sweeps_to_zones,
    build_sweep_id,
    empty_sweep_link_payload,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_SMC_MIN_CANDLES = 11
_SMC_LOOKBACK_EXTERNAL = 5
_SMC_LOOKBACK_FALLBACK = 2
_SMC_LOOKBACK_INTERNAL = 2
_ATR_FILTER_MIN_CANDLES = 15
_ATR_PERIOD = 14
_ATR_DISTANCE_MULT = 0.2
_LOOKBACK_WINDOW = 80
_MAX_FVG = 6
_MAX_ORDER_BLOCKS = 6
_MAX_SD_ZONES = 5
_MAX_LIQUIDITY_LEVELS = 3
_PD_THRESHOLD = 0.05
_LEG_STRONG = 3
_LEG_NORMAL = 2
_CHOCH_CONFIRMED_LEGS = 3
_ZONE_SCORE_BASE = 50
# Phase 16B shadow policy. Named constants keep every adjustment auditable;
# they must be calibrated on production snapshots before any consumer uses it.
_EFFECTIVE_ZONE_SCORE_BASE = 50
_EFFECTIVE_ZONE_FRESHNESS_BONUSES = ((3, 10), (8, 6), (16, 3))
_EFFECTIVE_ZONE_STALE_PENALTY = 12
_EFFECTIVE_ZONE_MITIGATED_PENALTY = 6
_EFFECTIVE_ZONE_MAX_RETEST_PENALTY = 20
_EFFECTIVE_ZONE_RETEST_PENALTY_STEP = 4
_EFFECTIVE_ZONE_NARROW_WIDTH_ATR = 0.35
_EFFECTIVE_ZONE_WIDE_WIDTH_ATR = 0.75
_EFFECTIVE_ZONE_NARROW_BONUS = 6
_EFFECTIVE_ZONE_MAX_WIDTH_PENALTY = 20
_EFFECTIVE_ZONE_WIDTH_PENALTY_PER_ATR = 12
_EFFECTIVE_ZONE_MAX_DISPLACEMENT_BONUS = 15
_EFFECTIVE_ZONE_LIQUIDITY_SWEEP_BONUS = 10
_EFFECTIVE_ZONE_LOCATION_CORRECT_BONUS = 12
_EFFECTIVE_ZONE_LOCATION_EQUILIBRIUM_BONUS = 4
_EFFECTIVE_ZONE_LOCATION_WRONG_PENALTY = 8

_DIRECTIONAL_ZONE_TYPES = {
    "buy": frozenset(
        {"demand_zone", "bullish_order_block", "bullish_fvg"}
    ),
    "sell": frozenset(
        {"supply_zone", "bearish_order_block", "bearish_fvg"}
    ),
}


def zone_matches_direction(
    zone: dict[str, Any] | None,
    direction: str,
) -> bool:
    """Return whether an SMC zone family is valid for the trade direction."""
    if not isinstance(zone, dict):
        return False
    normalized_direction = str(direction or "").strip().lower()
    allowed_types = _DIRECTIONAL_ZONE_TYPES.get(normalized_direction)
    if allowed_types is None:
        return False
    zone_type = str(
        zone.get("zone_type") or zone.get("type") or ""
    ).strip().lower()
    return zone_type in allowed_types
_ZONE_SCORE_STRONG = 75
_ZONE_SCORE_MODERATE = 55
_ZONE_MAX_TEST_BONUS = 20
_ZONE_TEST_POINTS = 5
_ZONE_MAX_FRESHNESS_BONUS = 10
_ZONE_FRESHNESS_DIVISOR = 5
_ZONE_BROKEN_PENALTY = 35
_ZONE_MAX_DISPLACEMENT_BONUS = 15
_ZONE_DISPLACEMENT_MULTIPLIER = 5
_ZONE_SWEEP_BONUS = 10
_ZONE_PD_CORRECT_BONUS = 12
_ZONE_PD_EQUILIBRIUM_BONUS = 4
_ZONE_PD_WRONG_PENALTY = 8


def build_smc_context(
    d1: list[Candle], h4: list[Candle], h1: list[Candle],
    *, scan_interval_min: int = 15, symbol: str = "",
) -> dict[str, Any]:
    d1_smc = _smc_for_timeframe(
        d1,
        tf_minutes=1440,
        scan_interval_min=scan_interval_min,
        symbol=symbol,
        timeframe="D1",
    )
    h4_smc = _smc_for_timeframe(
        h4,
        tf_minutes=240,
        scan_interval_min=scan_interval_min,
        symbol=symbol,
        timeframe="H4",
    )
    h1_smc = _smc_for_timeframe(
        h1,
        tf_minutes=60,
        scan_interval_min=scan_interval_min,
        symbol=symbol,
        timeframe="H1",
    )
    directional_confluence = build_directional_confluence(
        d1_smc,
        h4_smc,
        h1_smc,
    )
    confluence = directional_confluence.to_dict()
    return {
        "domain_version": SMC_DOMAIN_VERSION,
        "symbol": symbol,
        "D1": d1_smc,
        "H4": h4_smc,
        "H1": h1_smc,
        "confluence": confluence,
    }


def summarize_structure(candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 3:
        return {"structure": "insufficient_data"}
    swings = swing_points(candles, lookback=_SMC_LOOKBACK_EXTERNAL)
    bos_choch = detect_bos_choch(swings, candles)
    structure = bos_choch.get("structure", "unknown")
    return {
        "structure": structure,
        "bos": bos_choch.get("bos", False),
        "choch": bos_choch.get("choch", False),
        "displacement": bos_choch.get("displacement", "neutral"),
        "swings": swings,
    }


def _smc_for_timeframe(
    candles: list[Candle],
    *,
    tf_minutes: int = 60,
    scan_interval_min: int = 15,
    symbol: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    if len(candles) < _SMC_MIN_CANDLES:
        return {
            "domain_version": SMC_DOMAIN_VERSION,
            "symbol": symbol,
            "timeframe": timeframe,
            "structure": "insufficient_data",
            "bos": False,
            "choch": False,
            "displacement": "neutral",
            "bos_strength": "weak",
            "choch_confirmed": False,
            "swings": {"highs": [], "lows": []},
            "external_swings": {"highs": [], "lows": []},
            "internal_swings": {"highs": [], "lows": []},
            "leg_count": 0,
            "supply_zones": [],
            "demand_zones": [],
            "order_blocks": [],
            "fvg": [],
            "liquidity_pools": {"equal_highs": [], "equal_lows": [], "swing_highs": [], "swing_lows": []},
            "liquidity_sweeps": {"swept_highs": [], "swept_lows": []},
            "zone_link_sweeps": {"swept_highs": [], "swept_lows": []},
            "premium_discount": "unknown",
            "premium_discount_range": {"status": "unknown"},
        }
    swing_source = "standard"
    swings = swing_points(candles, lookback=_SMC_LOOKBACK_EXTERNAL)
    if len(swings["highs"]) == 0 and len(swings["lows"]) == 0:
        _log.warning("SMC swing_points returned empty with lookback=5, falling back to lookback=2")
        swings = swing_points(candles, lookback=_SMC_LOOKBACK_FALLBACK)
        swing_source = "fallback"
    swings = _filter_swings_by_atr(candles, swings)
    external_swings = swings
    internal_swings = _detect_internal_structure(candles, external_swings)
    leg_count = _count_trend_legs(external_swings)
    bos = detect_bos_choch(swings, candles, leg_count)
    liquidity = detect_liquidity_pools(candles, swings)
    premium_discount = classify_premium_discount(candles[-1].close, swings)
    premium_discount_range = premium_discount_bounds(swings)
    fvg = detect_fvg(candles)
    order_blocks = detect_order_blocks(candles, fvg)
    demand_zones, supply_zones = detect_supply_demand_zones(candles)
    liquidity_sweeps = detect_liquidity_sweeps(
        candles,
        swings,
        symbol=symbol,
        timeframe=timeframe,
    )
    zone_link_sweeps = detect_liquidity_sweeps(
        candles,
        swings,
        symbol=symbol,
        timeframe=timeframe,
        lookback_bars=_LOOKBACK_WINDOW,
        max_results=None,
        causal_only=True,
    )
    _attach_zone_sweep_links(
        (
            ("demand", demand_zones),
            ("supply", supply_zones),
            ("order_block", order_blocks),
            ("fvg", fvg),
        ),
        zone_link_sweeps,
        candles=candles,
        symbol=symbol,
        timeframe=timeframe,
        tf_minutes=tf_minutes,
    )
    demand_zones = enrich_zones(
        demand_zones, candles, "demand", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    supply_zones = enrich_zones(
        supply_zones, candles, "supply", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    order_blocks = enrich_zones(
        order_blocks, candles, "order_block", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    fvg = enrich_zones(
        fvg, candles, "fvg", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    return {
        "domain_version": SMC_DOMAIN_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "structure": bos.get("structure", "unknown"),
        "bos": bos.get("bos", False),
        "choch": bos.get("choch", False),
        "displacement": bos.get("displacement", "neutral"),
        "bos_strength": bos.get("bos_strength", "weak"),
        "choch_confirmed": bos.get("choch_confirmed", False),
        "swings": swings,
        "external_swings": external_swings,
        "internal_swings": internal_swings,
        "leg_count": leg_count,
        "supply_zones": supply_zones,
        "demand_zones": demand_zones,
        "order_blocks": order_blocks,
        "fvg": fvg,
        "liquidity_pools": liquidity,
        "liquidity_sweeps": liquidity_sweeps,
        "zone_link_sweeps": zone_link_sweeps,
        "premium_discount": premium_discount,
        "premium_discount_range": premium_discount_range,
        "swing_source": swing_source,
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


def _filter_swings_by_atr(candles: list[Candle], swings: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Filter swing points: keep only those at least 0.2×ATR from previous swing."""
    if len(candles) < _ATR_FILTER_MIN_CANDLES:
        return swings
    closes = [c.close for c in candles]
    highs_atr = [c.high for c in candles]
    lows_atr = [c.low for c in candles]
    atr_values = atr(highs_atr, lows_atr, closes, _ATR_PERIOD)
    atr_now = atr_values[-1] if atr_values and atr_values[-1] is not None else 0.0
    if atr_now <= 0:
        return swings
    min_distance = atr_now * _ATR_DISTANCE_MULT
    highs = swings["highs"]
    lows = swings["lows"]
    filtered_highs: list[dict[str, Any]] = []
    filtered_lows: list[dict[str, Any]] = []
    for h in highs:
        if not filtered_highs or abs(h["level"] - filtered_highs[-1]["level"]) >= min_distance:
            filtered_highs.append(h)
    for lo in lows:
        if not filtered_lows or abs(lo["level"] - filtered_lows[-1]["level"]) >= min_distance:
            filtered_lows.append(lo)
    return {"highs": filtered_highs, "lows": filtered_lows}


def _count_trend_legs(swings: dict[str, list[dict[str, Any]]]) -> int:
    """Count consecutive legs in the current trend direction.

    For HH/HL (uptrend): count consecutive pairs where high[i] > high[i-1]
    AND low[i] > low[i-1] going backwards from the most recent.
    For LH/LL (downtrend): count consecutive pairs where high[i] < high[i-1]
    AND low[i] < low[i-1].
    Returns 0 for mixed/unknown structure.
    """
    highs = swings["highs"]
    lows = swings["lows"]
    if len(highs) < 2 or len(lows) < 2:
        return 0
    last_h = highs[-1]["level"]
    prev_h = highs[-2]["level"]
    last_l = lows[-1]["level"]
    prev_l = lows[-2]["level"]
    if last_h > prev_h and last_l > prev_l:
        count = 1
        max_i = min(len(highs), len(lows))
        for i in range(2, max_i):
            if highs[-i]["level"] > highs[-(i + 1)]["level"] and lows[-i]["level"] > lows[-(i + 1)]["level"]:
                count += 1
            else:
                break
        return count
    elif last_h < prev_h and last_l < prev_l:
        count = 1
        max_i = min(len(highs), len(lows))
        for i in range(2, max_i):
            if highs[-i]["level"] < highs[-(i + 1)]["level"] and lows[-i]["level"] < lows[-(i + 1)]["level"]:
                count += 1
            else:
                break
        return count
    return 0


def _detect_internal_structure(candles: list[Candle], external_swings: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Detect internal (minor) swings within each leg between external swings.

    For each consecutive pair of external swing points, extracts the candle
    segment between them and runs swing_points(lookback=2) to find minor
    swings used for entry refinement.
    """
    if not candles:
        return {"highs": [], "lows": []}
    external_highs = external_swings.get("highs", [])
    external_lows = external_swings.get("lows", [])
    all_external = sorted(external_highs + external_lows, key=lambda s: s["index"])
    if len(all_external) < 2:
        return {"highs": [], "lows": []}

    internal_highs: list[dict[str, Any]] = []
    internal_lows: list[dict[str, Any]] = []
    for i in range(len(all_external) - 1):
        start_idx = all_external[i]["index"]
        end_idx = all_external[i + 1]["index"]
        if end_idx - start_idx < 6:
            continue
        segment = candles[start_idx:end_idx + 1]
        seg_swings = swing_points(segment, lookback=_SMC_LOOKBACK_INTERNAL)
        offset = start_idx
        for h in seg_swings["highs"]:
            h_copy = dict(h)
            h_copy["index"] = h["index"] + offset
            h_copy["leg"] = i
            internal_highs.append(h_copy)
        for lo in seg_swings["lows"]:
            lo_copy = dict(lo)
            lo_copy["index"] = lo["index"] + offset
            lo_copy["leg"] = i
            internal_lows.append(lo_copy)
    return {"highs": internal_highs, "lows": internal_lows}


def detect_bos_choch(swings: dict[str, list[dict[str, Any]]], candles: list[Candle], leg_count: int = 0) -> dict[str, Any]:
    highs = swings["highs"]
    lows = swings["lows"]
    if len(highs) < 2 or len(lows) < 2 or not candles:
        return {"structure": "unknown", "bos": False, "choch": False, "displacement": "neutral",
                "bos_strength": "weak", "choch_confirmed": False}

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

    if bos:
        bos_strength = "strong" if leg_count >= _LEG_STRONG else "normal" if leg_count >= _LEG_NORMAL else "weak"
    else:
        bos_strength = "weak"
    choch_confirmed = choch and leg_count >= _CHOCH_CONFIRMED_LEGS

    return {"structure": structure, "bos": bos, "choch": choch, "displacement": displacement,
            "bos_strength": bos_strength, "choch_confirmed": choch_confirmed}


def detect_fvg(candles: list[Candle]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if len(candles) < 3:
        return gaps
    start = max(0, len(candles) - _LOOKBACK_WINDOW)
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
                    "origin_index": index,
                    "origin_time": third.time.isoformat(),
                    "formation_start_index": index - 2,
                    "departure_end_index": index,
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
                    "origin_index": index,
                    "origin_time": third.time.isoformat(),
                    "formation_start_index": index - 2,
                    "departure_end_index": index,
                    "displacement_multiple": displacement_multiple_at(candles, index),
                }
            )
    return gaps[-_MAX_FVG:]


def detect_order_blocks(candles: list[Candle], fvg: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if len(candles) < 4:
        return blocks
    fvg_indices = {item["index"]: item for item in fvg}
    start = max(0, len(candles) - _LOOKBACK_WINDOW)
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
                    "origin_index": index,
                    "origin_time": candle.time.isoformat(),
                    "formation_start_index": index,
                    "departure_end_index": index + 1,
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
                    "origin_index": index,
                    "origin_time": candle.time.isoformat(),
                    "formation_start_index": index,
                    "departure_end_index": index + 1,
                    "has_fvg_below": (index + 2) in fvg_indices,
                    "displacement_multiple": displacement_multiple_at(candles, index + 1),
                }
            )
    return blocks[-_MAX_ORDER_BLOCKS:]


def detect_supply_demand_zones(candles: list[Candle]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(candles) < 8:
        return [], []

    avg_range = sum(candle.high - candle.low for candle in candles[-50:]) / max(1, min(50, len(candles)))
    impulse_threshold = avg_range * 1.5 if avg_range > 0 else 0.0

    # Dict keyed by (index, "demand"|"supply") -> best zone for that impulse
    best_by_impulse: dict[tuple[int, str], dict[str, Any]] = {}

    for consolidation_bars in (3, 5, 7, 10):
        if len(candles) < consolidation_bars + 2:
            continue
        max_base_range_mult = 1.2 + 0.06 * (consolidation_bars - 3)

        start = max(consolidation_bars, len(candles) - _LOOKBACK_WINDOW)
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
            if avg_range > 0 and base_range > avg_range * max_base_range_mult:
                continue

            is_bullish = impulse.close > impulse.open and impulse.close > base_high
            is_bearish = impulse.close < impulse.open and impulse.close < base_low
            if not (is_bullish or is_bearish):
                continue

            direction = "demand" if is_bullish else "supply"
            key = (index, direction)

            # Keep the zone with tightest base_range per impulse
            if key not in best_by_impulse or base_range < best_by_impulse[key]["_base_range"]:
                best_by_impulse[key] = {
                    "type": "demand_zone" if is_bullish else "supply_zone",
                    "low": base_low,
                    "high": base_high,
                    "index": index - 1,
                    "time": base[-1].time.isoformat(),
                    "origin_index": index - 1,
                    "origin_time": base[-1].time.isoformat(),
                    "formation_start_index": index - consolidation_bars,
                    "departure_end_index": index,
                    "consolidation_bars": consolidation_bars,
                    "displacement_multiple": round(impulse_size / avg_range, 2) if avg_range else 0,
                    "liquidity_sweep": (
                        swept_recent_low(impulse, candles[:index])
                        if is_bullish
                        else swept_recent_high(impulse, candles[:index])
                    ),
                    "_base_range": base_range,
                }

    # Split by type, sort by index descending, keep top _MAX_SD_ZONES
    demand_candidates = sorted(
        [z for z in best_by_impulse.values() if z["type"] == "demand_zone"],
        key=lambda z: z["index"], reverse=True,
    )[: _MAX_SD_ZONES]
    supply_candidates = sorted(
        [z for z in best_by_impulse.values() if z["type"] == "supply_zone"],
        key=lambda z: z["index"], reverse=True,
    )[: _MAX_SD_ZONES]

    # Clean up internal field
    for z in demand_candidates + supply_candidates:
        z.pop("_base_range", None)

    return demand_candidates, supply_candidates


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
        "equal_highs": equal_highs[-_MAX_LIQUIDITY_LEVELS:],
        "equal_lows": equal_lows[-_MAX_LIQUIDITY_LEVELS:],
        "swing_highs": swing_highs[-_MAX_LIQUIDITY_LEVELS:],
        "swing_lows": swing_lows[-_MAX_LIQUIDITY_LEVELS:],
    }


def classify_premium_discount(price: float, swings: dict[str, list[dict[str, Any]]]) -> str:
    highs = [item["level"] for item in swings["highs"][-_MAX_LIQUIDITY_LEVELS:]]
    lows = [item["level"] for item in swings["lows"][-_MAX_LIQUIDITY_LEVELS:]]
    if not highs or not lows:
        return "unknown"
    high = max(highs)
    low = min(lows)
    if high == low:
        return "equilibrium"
    midpoint = (high + low) / 2
    if price >= midpoint + (high - low) * _PD_THRESHOLD:
        return "premium"
    if price <= midpoint - (high - low) * _PD_THRESHOLD:
        return "discount"
    return "equilibrium"


def premium_discount_bounds(swings: dict[str, list[dict[str, Any]]]) -> dict[str, float | str]:
    highs = [item["level"] for item in swings["highs"][-_MAX_LIQUIDITY_LEVELS:]]
    lows = [item["level"] for item in swings["lows"][-_MAX_LIQUIDITY_LEVELS:]]
    if not highs or not lows:
        return {"status": "unknown"}
    high = max(highs)
    low = min(lows)
    return {"status": "ok", "high": high, "low": low, "midpoint": (high + low) / 2}


def detect_liquidity_sweeps(
    candles: list[Candle],
    swings: dict[str, list[dict[str, Any]]],
    *,
    symbol: str = "",
    timeframe: str = "",
    lookback_bars: int = 6,
    max_results: int | None = _MAX_LIQUIDITY_LEVELS,
    causal_only: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    if len(candles) < 3:
        return {"swept_highs": [], "swept_lows": []}
    safe_lookback = max(1, int(lookback_bars))
    recent_start = max(0, len(candles) - safe_lookback)
    swing_highs = swings["highs"][-safe_lookback:]
    swing_lows = swings["lows"][-safe_lookback:]
    swept_highs: list[dict[str, Any]] = []
    swept_lows: list[dict[str, Any]] = []
    for candle_index in range(recent_start, len(candles)):
        candle = candles[candle_index]
        for swing in swing_highs:
            if (
                causal_only
                and swing.get("index") is not None
                and int(swing["index"]) >= candle_index
            ):
                continue
            level = swing["level"]
            if candle.high > level and candle.close < level:
                occurred_at = candle.time.isoformat()
                swept_highs.append({
                    "sweep_id": build_sweep_id(
                        symbol=symbol,
                        timeframe=timeframe,
                        side="sell",
                        kind="swept_high",
                        level=level,
                        occurred_at=occurred_at,
                    ),
                    "side": "sell",
                    "kind": "swept_high",
                    "level": level,
                    "index": candle_index,
                    "time": occurred_at,
                    "source_swing_index": swing.get("index"),
                    "source_swing_time": swing.get("time"),
                    "sweep_link_version": SMC_SWEEP_LINK_VERSION,
                })
                break
        for swing in swing_lows:
            if (
                causal_only
                and swing.get("index") is not None
                and int(swing["index"]) >= candle_index
            ):
                continue
            level = swing["level"]
            if candle.low < level and candle.close > level:
                occurred_at = candle.time.isoformat()
                swept_lows.append({
                    "sweep_id": build_sweep_id(
                        symbol=symbol,
                        timeframe=timeframe,
                        side="buy",
                        kind="swept_low",
                        level=level,
                        occurred_at=occurred_at,
                    ),
                    "side": "buy",
                    "kind": "swept_low",
                    "level": level,
                    "index": candle_index,
                    "time": occurred_at,
                    "source_swing_index": swing.get("index"),
                    "source_swing_time": swing.get("time"),
                    "sweep_link_version": SMC_SWEEP_LINK_VERSION,
                })
                break
    if max_results is None:
        return {"swept_highs": swept_highs, "swept_lows": swept_lows}
    safe_limit = max(0, int(max_results))
    if safe_limit == 0:
        return {"swept_highs": [], "swept_lows": []}
    return {
        "swept_highs": swept_highs[-safe_limit:],
        "swept_lows": swept_lows[-safe_limit:],
    }


def _attach_zone_sweep_links(
    zone_groups: tuple[tuple[str, list[dict[str, Any]]], ...],
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    *,
    candles: list[Candle],
    symbol: str,
    timeframe: str,
    tf_minutes: int,
) -> None:
    """Attach canonical one-to-one sweep links across every zone family."""

    candidates: list[dict[str, Any]] = []
    for family, zones in zone_groups:
        for zone in zones:
            origin_index = int(
                zone.get("origin_index", zone.get("index", -1))
            )
            origin_time = str(
                zone.get("origin_time", zone.get("time", "")) or ""
            )
            direction = zone_side(zone, family)
            zone_id = str(zone.get("zone_id", "") or "").strip() or build_zone_id(
                symbol=symbol,
                timeframe=timeframe or str(tf_minutes),
                family=family,
                direction=direction,
                origin_time=origin_time,
                low=zone.get("low", 0),
                high=zone.get("high", 0),
            )
            zone.update({
                "zone_id": zone_id,
                "family": family,
                "direction": direction,
                "origin_index": origin_index,
                "origin_time": origin_time,
                "formation_start_index": int(
                    zone.get("formation_start_index", origin_index)
                ),
                "departure_end_index": int(
                    zone.get("departure_end_index", origin_index)
                ),
            })
            for key, value in empty_sweep_link_payload().items():
                zone.setdefault(key, value)
            candidates.append(zone)

    links = associate_sweeps_to_zones(
        candidates,
        liquidity_sweeps,
        atr_value=_latest_atr(candles),
    )
    sweep_to_zone: dict[str, str] = {}
    for zone in candidates:
        link = links.get(str(zone.get("zone_id", "")))
        if link is None:
            continue
        zone.update(link.to_zone_payload())
        sweep_to_zone[link.sweep_id] = link.zone_id

    for key in ("swept_lows", "swept_highs"):
        values = liquidity_sweeps.get(key, [])
        if not isinstance(values, list):
            continue
        for sweep in values:
            if not isinstance(sweep, dict):
                continue
            sweep_id = str(sweep.get("sweep_id", "") or "")
            sweep["linked_zone_id"] = sweep_to_zone.get(sweep_id)
            sweep["sweep_link_version"] = SMC_SWEEP_LINK_VERSION


def _latest_atr(candles: list[Candle]) -> float | None:
    if not candles:
        return None
    values = atr(
        [candle.high for candle in candles],
        [candle.low for candle in candles],
        [candle.close for candle in candles],
        _ATR_PERIOD,
    )
    value = values[-1] if values else None
    return float(value) if value is not None and value > 0 else None


def enrich_zones(
    zones: list[dict[str, Any]],
    candles: list[Candle],
    family: str,
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    premium_discount_range: dict[str, float | str],
    *,
    tf_minutes: int = 60,
    scan_interval_min: int = 15,
    symbol: str = "",
    timeframe: str = "",
) -> list[dict[str, Any]]:
    enriched = []
    stale_threshold = max(1, (scan_interval_min * 2) // tf_minutes)
    for zone in zones:
        item = dict(zone)
        for key, value in empty_sweep_link_payload().items():
            item.setdefault(key, value)
        index = int(
            item.get(
                "origin_index",
                item.get("index", len(candles) - 1),
            )
        )
        departure_end_index = int(
            item.get("departure_end_index", index)
        )
        future = candles[index + 1 :] if index + 1 < len(candles) else []
        low = float(item.get("low", 0.0))
        high = float(item.get("high", 0.0))
        side = zone_side(item, family)
        test_count = count_zone_tests(future, low, high)
        zone_broken_flag = zone_broken(future, low, high, side)
        mitigated = test_count > 0
        freshness_bars = max(0, len(candles) - 1 - index)
        stale = freshness_bars > stale_threshold
        zone_location = zone_premium_discount(low, high, premium_discount_range)
        liquidity_sweep = (
            bool(item.get("liquidity_sweep"))
            or _legacy_timeframe_has_sweep(side, liquidity_sweeps)
        )
        origin_time = str(
            item.get("origin_time", item.get("time", "")) or ""
        )
        zone_id = str(item.get("zone_id", "") or "").strip() or build_zone_id(
            symbol=symbol,
            timeframe=timeframe or str(tf_minutes),
            family=family,
            direction=side,
            origin_time=origin_time,
            low=low,
            high=high,
        )
        lifecycle = analyze_zone_lifecycle(
            candles=candles,
            low=low,
            high=high,
            side=side,
            origin_index=index,
            departure_end_index=departure_end_index,
            zone_id=zone_id,
            timeframe=timeframe,
            tf_minutes=tf_minutes,
        )
        item.update(
            {
                "zone_id": zone_id,
                "origin_index": index,
                "origin_time": origin_time,
                "freshness_bars": freshness_bars,
                "stale": stale,
                "mitigated": mitigated,
                "broken": zone_broken_flag,
                "test_count": test_count,
                "liquidity_sweep": liquidity_sweep,
                "zone_location": zone_location,
            }
        )
        item.update(lifecycle.to_dict())
        enriched.append(item)
    # Raw candidates carry no scorer score, so order by deterministic raw
    # lifecycle signals: actionable (non-broken, non-stale) and stronger
    # (tested, swept, recent, high displacement) zones first.
    return sorted(
        enriched,
        key=lambda zone: (
            bool(zone.get("broken", False)),
            bool(zone.get("stale", False)),
            -int(zone.get("test_count", 0) or 0),
            -int(bool(zone.get("liquidity_sweep", False))),
            -int(zone.get("origin_index", 0) or 0),
            -float(zone.get("displacement_multiple") or 0.0),
            str(zone.get("zone_id", "") or ""),
        ),
    )


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
    if center <= midpoint - width * _PD_THRESHOLD:
        return "discount"
    if center >= midpoint + width * _PD_THRESHOLD:
        return "premium"
    return "equilibrium"


def _legacy_timeframe_has_sweep(
    side: str,
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
) -> bool:
    """Compatibility-only broadcast for sweep-linking across timeframes."""

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
    score = _ZONE_SCORE_BASE
    test_count = int(zone.get("test_count", 0))
    # Zone da test nhieu lan + giu duoc = tin cay cao
    score += min(_ZONE_MAX_TEST_BONUS, test_count * _ZONE_TEST_POINTS)
    # Zone con moi: bonus nhe (moi la tin hieu tot nhung chua duoc kiem chung)
    freshness = int(zone.get("freshness_bars", 999))
    score += max(0, _ZONE_MAX_FRESHNESS_BONUS - freshness // _ZONE_FRESHNESS_DIVISOR)
    # Zone da bi broken = khong con gia tri
    score -= _ZONE_BROKEN_PENALTY if zone.get("broken") else 0
    # Displacement impulse: move cang manh → zone cang quan trong
    score += min(_ZONE_MAX_DISPLACEMENT_BONUS, int(float(zone.get("displacement_multiple", 0)) * _ZONE_DISPLACEMENT_MULTIPLIER))
    # Liquidity sweep: quet stop-loss truoc khi dao chieu = tin hieu manh
    score += _ZONE_SWEEP_BONUS if zone.get("liquidity_sweep") else 0
    # Vi tri trong cau truc premium/discount
    location = zone.get("zone_location")
    if (side == "buy" and location == "discount") or (side == "sell" and location == "premium"):
        score += _ZONE_PD_CORRECT_BONUS
    elif location == "equilibrium":
        score += _ZONE_PD_EQUILIBRIUM_BONUS
    elif location in {"premium", "discount"}:
        score -= _ZONE_PD_WRONG_PENALTY
    return max(0, min(100, int(score)))


def calculate_effective_zone_score(
    zone: dict[str, Any],
    side: str,
    atr_value: float | int | None,
) -> dict[str, Any]:
    """Return a conservative, shadow-only zone score and its breakdown.

    Unlike ``zone_quality_score``, repeated tests are treated as zone
    consumption, stale/mitigated state is explicit, and excessive source-zone
    width is penalized. Consumers must continue to use ``zone_score`` until
    shadow results justify a production migration.
    """
    normalized_side = str(side or "").strip().lower()

    test_count_available = zone.get("test_count") is not None
    try:
        test_count = max(0, int(zone.get("test_count", 0) or 0))
    except (TypeError, ValueError):
        test_count = 0
        test_count_available = False
    try:
        freshness_bars = max(0, int(zone.get("freshness_bars", 999) or 999))
    except (TypeError, ValueError):
        freshness_bars = 999
    try:
        displacement = max(0.0, float(zone.get("displacement_multiple", 0) or 0))
    except (TypeError, ValueError):
        displacement = 0.0

    stale = bool(zone.get("stale"))
    mitigated = bool(zone.get("mitigated"))
    broken = bool(zone.get("broken"))

    freshness_bonus = 0
    if not stale:
        for max_bars, bonus in _EFFECTIVE_ZONE_FRESHNESS_BONUSES:
            if freshness_bars <= max_bars:
                freshness_bonus = bonus
                break

    if not test_count_available:
        test_count_adjustment = 0
    elif test_count == 0:
        test_count_adjustment = 4
    elif test_count == 1:
        test_count_adjustment = 2
    elif test_count == 2:
        test_count_adjustment = 0
    else:
        test_count_adjustment = -min(
            _EFFECTIVE_ZONE_MAX_RETEST_PENALTY,
            (test_count - 2) * _EFFECTIVE_ZONE_RETEST_PENALTY_STEP,
        )

    width_atr = None
    try:
        low = float(zone.get("low"))
        high = float(zone.get("high"))
        atr = float(atr_value)
        if high > low and atr > 0:
            width_atr = (high - low) / atr
    except (TypeError, ValueError):
        pass

    width_adjustment = 0
    if width_atr is not None:
        if width_atr <= _EFFECTIVE_ZONE_NARROW_WIDTH_ATR:
            width_adjustment = _EFFECTIVE_ZONE_NARROW_BONUS
        elif width_atr > _EFFECTIVE_ZONE_WIDE_WIDTH_ATR:
            width_adjustment = -min(
                _EFFECTIVE_ZONE_MAX_WIDTH_PENALTY,
                round(
                    (width_atr - _EFFECTIVE_ZONE_WIDE_WIDTH_ATR)
                    * _EFFECTIVE_ZONE_WIDTH_PENALTY_PER_ATR
                ),
            )

    displacement_bonus = min(
        _EFFECTIVE_ZONE_MAX_DISPLACEMENT_BONUS,
        int(displacement * _ZONE_DISPLACEMENT_MULTIPLIER),
    )
    liquidity_sweep_bonus = (
        _EFFECTIVE_ZONE_LIQUIDITY_SWEEP_BONUS
        if zone.get("liquidity_sweep")
        else 0
    )

    location = str(zone.get("zone_location", "") or "").strip().lower()
    if (
        normalized_side == "buy"
        and location == "discount"
        or normalized_side == "sell"
        and location == "premium"
    ):
        premium_discount_adjustment = _EFFECTIVE_ZONE_LOCATION_CORRECT_BONUS
    elif location == "equilibrium":
        premium_discount_adjustment = _EFFECTIVE_ZONE_LOCATION_EQUILIBRIUM_BONUS
    elif (
        normalized_side in {"buy", "sell"}
        and location in {"premium", "discount"}
    ):
        premium_discount_adjustment = -_EFFECTIVE_ZONE_LOCATION_WRONG_PENALTY
    else:
        premium_discount_adjustment = 0

    stale_penalty = -_EFFECTIVE_ZONE_STALE_PENALTY if stale else 0
    mitigation_penalty = -_EFFECTIVE_ZONE_MITIGATED_PENALTY if mitigated else 0
    pre_clamp_total = sum(
        (
            _EFFECTIVE_ZONE_SCORE_BASE,
            freshness_bonus,
            stale_penalty,
            mitigation_penalty,
            test_count_adjustment,
            width_adjustment,
            displacement_bonus,
            liquidity_sweep_bonus,
            premium_discount_adjustment,
        )
    )
    effective_score = 0 if broken else max(0, min(100, int(pre_clamp_total)))

    return {
        "effective_zone_score": effective_score,
        "effective_zone_score_breakdown": {
            "base": _EFFECTIVE_ZONE_SCORE_BASE,
            "freshness_bonus": freshness_bonus,
            "stale_penalty": stale_penalty,
            "mitigation_penalty": mitigation_penalty,
            "test_count_adjustment": test_count_adjustment,
            "width_adjustment": width_adjustment,
            "displacement_bonus": displacement_bonus,
            "liquidity_sweep_bonus": liquidity_sweep_bonus,
            "premium_discount_adjustment": premium_discount_adjustment,
            "source_zone_width_atr": (
                round(width_atr, 4) if width_atr is not None else None
            ),
            "pre_clamp_total": pre_clamp_total,
            "broken_override": broken,
        },
    }


def score_to_strength(score: int) -> str:
    if score >= _ZONE_SCORE_STRONG:
        return "strong"
    if score >= _ZONE_SCORE_MODERATE:
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


def extract_smc_trade_flags(smc_context: dict[str, Any] | None, direction: str) -> dict[str, Any]:
    """Trich xuat cac flag SMC an toan cho trade gate.

    Tra ve dict cac flag doc tu SMC context, khong crash neu thieu du lieu.
    Dung H4 lam timeframe chinh cho structural signals, H1 cho liquidity.

    Chi tra ve structural flags (CHOCH, displacement, sweep). Selected zone
    khong duoc chon o day — selected zone luon den tu SMC result/consumer
    canonical.

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
            "choch_against_direction": bool,
            "liquidity_sweep_aligned": bool,
            "displacement_aligned": bool,
            "raw": dict,
        }
    """
    result: dict[str, Any] = {
        "choch_against_direction": False,
        "liquidity_sweep_aligned": False,
        "displacement_aligned": False,
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
