from __future__ import annotations

from dataclasses import dataclass
from math import floor
from typing import Any

import json
from pathlib import Path

from core.entry_engine import evaluate_entry
from core.market_models import Candle
from core.signal_engine import clamp
from core.correlation_check import get_correlation_warnings, summarize_correlation_context


def _load_risk_params() -> dict:
    params_file = Path(__file__).resolve().parents[1] / "config" / "risk_params.json"
    if params_file.exists():
        return json.loads(params_file.read_text())
    return {}


_rp = _load_risk_params()


# SYMBOL_CONFIG chỉ chứa symbol có contract_size khác mặc định 100,000 (forex standard).
# Với forex: contract_size luôn lấy từ controller (settings.trading.contract_size_override, mặc định 100,000),
# không dùng trade_contract_size từ MT5 vì cent account trả về 100 gây sai lot.
SYMBOL_CONFIG: dict[str, dict[str, Any]] = {
    "XAU/USD": {"contract_size": 100.0, "quote_currency": "USD", "method": "price_distance_x_contract_size"},
    "XAG/USD": {"contract_size": 5000.0, "quote_currency": "USD", "method": "price_distance_x_contract_size"},
    "BTC/USD": {"contract_size": 1.0, "quote_currency": "USD", "method": "price_distance_x_contract_size"},
}

STRENGTH_RANK = {"strong": 3, "moderate": 2, "weak": 1}

# ── Risk params loaded from config/risk_params.json ──
# Dynamic SL multiplier by market regime — wider stops in trends/volatile,
# tighter stops in ranges.
REGIME_SL_MULTIPLIER: dict[str, float] = _rp.get("regime_sl_multiplier", {
    "trend_up": 0.65, "trend_down": 0.65, "range": 0.70, "volatile": 0.85, "unknown": 0.50,
})
REGIME_ZONE_DISTANCE_MULT: dict[str, float] = _rp.get("regime_zone_distance_mult", {
    "trend_up": 3.5, "trend_down": 3.5, "range": 2.5, "volatile": 3.0, "unknown": 2.0,
})
# Dynamic TP fallback multiplier by market regime.
# Used by backtest fallback_scenario only (NOT by build_trade_plan).
# build_trade_plan returns None for RR/TP when no structural target is found.
REGIME_TP_FALLBACK_MULT: dict[str, float] = _rp.get("regime_tp_fallback_mult", {
    "trend_up": 2.0, "trend_down": 2.0, "range": 1.5, "volatile": 1.8, "unknown": 1.5,
})
_DEFAULT_TP_FALLBACK_MULT = 2.0
_DEFAULT_SL_MULT = _rp.get("default_sl_mult", 0.50)
_DEFAULT_ZONE_DISTANCE_MULT = _rp.get("default_zone_distance_mult", 1.5)
_ZONE_SL_BUFFER_ATR = _rp.get("zone_sl_buffer_atr", 0.10)
_ZONE_SL_CAP_RATIO = _rp.get("zone_sl_cap_ratio", 1.5)
ENTRY_ZONE_ATR_MULT = _rp.get("entry_zone_atr_mult", 0.35)
_ENTRY_ZONE_ATR_MIN = _rp.get("entry_zone_atr_min", 0.10)
_ENTRY_ZONE_ATR_MAX = _rp.get("entry_zone_atr_max", 0.30)
_ENTRY_AGGRESSIVENESS = _rp.get("entry_aggressiveness", 0.0)   # 0.0=nearest edge (display), 1.0=farthest
_MIN_SL_DISTANCE_ATR = _rp.get("min_sl_distance_atr", 0.5)
_SWING_SL_BUFFER_ATR = _rp.get("swing_sl_buffer_atr", 0.15)
_TP_SELECTION_AGGRESSIVENESS = _rp.get("tp_selection_aggressiveness", 0.5)  # midpoint anchor for TP validation
_EQ_TP_MAX_RR = _rp.get("eq_tp_max_rr", 3.0)
_TP2_MIN_GAP_ATR = _rp.get("tp2_min_gap_atr", 0.15)
_FIB_TP1 = _rp.get("fib_tp1", 0.382)
_FIB_TP2 = _rp.get("fib_tp2", 0.618)
_MIN_STOP_DISTANCE_ATR_MULT = _rp.get("min_stop_distance_atr_mult", 0.20)
_MIN_STOP_SPREAD_MULT = _rp.get("min_stop_spread_mult", 3)
_ENTRY_ZONE_WIDTH_MULT = _rp.get("entry_zone_width_mult", 0.5)
_WATCH_ZONE_OFFSET_ATR = _rp.get("watch_zone_offset_atr", 0.10)
_SL_FLOOR_BUFFER_ATR = _rp.get("sl_floor_buffer_atr", 0.10)
_WATCH_ZONE_ATR_VOLATILE = _rp.get("watch_zone_atr_volatile", 0.70)
_WATCH_ZONE_ATR_TREND = _rp.get("watch_zone_atr_trend", 0.40)
_WATCH_ZONE_ATR_RANGE = _rp.get("watch_zone_atr_range", 0.50)


def _find_impulse_swing(
    swing_highs: list[dict[str, Any]],
    swing_lows: list[dict[str, Any]],
    side: str,
) -> tuple[float, float] | None:
    """Find the best completed impulse pair (start, end) for Fib projection.

    For BUY: find a swing low → later swing high (upward impulse).
    For SELL: find a swing high → later swing low (downward impulse).
    Returns (start_level, end_level) or None if insufficient swing data.
    """
    if side == "buy":
        if len(swing_lows) < 1 or len(swing_highs) < 1:
            return None
        # Use the most recent swing low as impulse start
        low = swing_lows[-1]
        # Find the highest swing high AFTER this low
        best_high = None
        for h in swing_highs:
            if h["index"] > low["index"]:
                if best_high is None or h["level"] > best_high["level"]:
                    best_high = h
        if best_high is None:
            return None
        return (low["level"], best_high["level"])
    else:
        if len(swing_highs) < 1 or len(swing_lows) < 1:
            return None
        # Use the most recent swing high as impulse start
        high = swing_highs[-1]
        # Find the lowest swing low AFTER this high
        best_low = None
        for lo in swing_lows:
            if lo["index"] > high["index"]:
                if best_low is None or lo["level"] < best_low["level"]:
                    best_low = lo
        if best_low is None:
            return None
        return (high["level"], best_low["level"])


def _fib_extension_target(
    smc: dict[str, Any] | None,
    side: str,
    atr_value: float,
    fib_level: float,
) -> float | None:
    """Calculate Fibonacci extension target from H4 swings.

    For BUY: projects upward from the last completed upward impulse.
    For SELL: projects downward from the last completed downward impulse.

    Returns the Fib extension price, or None if swing data is unavailable.
    """
    if not isinstance(smc, dict):
        return None
    h4 = smc.get("H4", {})
    if not isinstance(h4, dict):
        return None
    swings = h4.get("swings", {})
    if not isinstance(swings, dict):
        return None

    highs = swings.get("highs", [])
    lows = swings.get("lows", [])
    if not isinstance(highs, list) or not isinstance(lows, list):
        return None

    pair = _find_impulse_swing(highs, lows, side)
    if pair is None:
        return None

    start, end = pair
    impulse = abs(end - start)

    if side == "buy":
        target = end + impulse * fib_level
        # Sanity: TP must be above entry area and at least 0.3 ATR away
        if target <= end:
            return None
        return round_price(target)
    else:
        target = end - impulse * fib_level
        if target >= end:
            return None
        return round_price(target)


def _find_nearest_swing_for_sl(
    smc: dict[str, Any] | None,
    side: str,
    price: float,
) -> float | None:
    """Find the nearest swing low (buy) or swing high (sell) from H4/H1 for SL.

    Searches both H4 and H1 swing data, returns the swing level closest to
    *price* that is structurally on the correct side.  Returns None when no
    suitable swing exists — the caller should fall back to ATR/zone-based SL.
    """
    if not isinstance(smc, dict):
        return None

    all_candidates: list[float] = []
    for tf in ("H4", "H1"):
        tf_data = smc.get(tf, {})
        if not isinstance(tf_data, dict):
            continue
        swings = tf_data.get("swings", {})
        if not isinstance(swings, dict):
            continue
        swing_list = swings.get("lows" if side == "buy" else "highs", [])
        if not isinstance(swing_list, list):
            continue
        for s in swing_list:
            if not isinstance(s, dict):
                continue
            level = s.get("level")
            if isinstance(level, (int, float)):
                all_candidates.append(float(level))

    if not all_candidates:
        return None

    if side == "buy":
        below = [l for l in all_candidates if l < price]
        return max(below) if below else None
    else:
        above = [h for h in all_candidates if h > price]
        return min(above) if above else None


def _find_nearest_equal_level(
    smc: dict[str, Any] | None,
    side: str,
    price: float,
) -> float | None:
    """Find the nearest equal high (buy) or equal low (sell) for TP1 placement.

    Searches H4 and H1 liquidity_pools for equal highs/lows — clusters where
    price is likely drawn to sweep stop-losses.  Returns None when no suitable
    level exists, so the caller falls back to S/R zones.
    """
    if not isinstance(smc, dict):
        return None

    candidates: list[float] = []
    for tf in ("H4", "H1"):
        tf_data = smc.get(tf, {})
        if not isinstance(tf_data, dict):
            continue
        pools = tf_data.get("liquidity_pools", {})
        if not isinstance(pools, dict):
            continue
        key = "equal_highs" if side == "buy" else "equal_lows"
        levels = pools.get(key, [])
        if isinstance(levels, list):
            for v in levels:
                if isinstance(v, (int, float)):
                    candidates.append(float(v))

    if not candidates:
        return None

    if side == "buy":
        above = [l for l in candidates if l > price]
        return min(above) if above else None
    else:
        below = [l for l in candidates if l < price]
        return max(below) if below else None


def _calc_stop_loss_buy(
    level: float,
    atr_value: float,
    sl_mult: float,
    min_stop_distance: float,
    zone: dict[str, Any] | None,
) -> float:
    """Calculate BUY stop loss: prefer below-zone-low, capped at 1.5× ATR."""
    atr_sl = level - max(atr_value * sl_mult, min_stop_distance)
    max_sl = level - atr_value * sl_mult * _ZONE_SL_CAP_RATIO  # widest allowed

    zone_low = zone.get("low") if isinstance(zone, dict) else None
    if zone_low is None or zone_low >= level:
        return atr_sl  # no valid zone boundary below level, use ATR-based

    zone_sl = zone_low - atr_value * _ZONE_SL_BUFFER_ATR
    if zone_sl >= max_sl:
        return zone_sl  # zone is close enough, place SL below it
    return max_sl       # zone too far, cap at 1.5×


def _calc_stop_loss_sell(
    level: float,
    atr_value: float,
    sl_mult: float,
    min_stop_distance: float,
    zone: dict[str, Any] | None,
) -> float:
    """Calculate SELL stop loss: prefer above-zone-high, capped at 1.5× ATR."""
    atr_sl = level + max(atr_value * sl_mult, min_stop_distance)
    min_sl = level + atr_value * sl_mult * _ZONE_SL_CAP_RATIO  # tightest allowed

    zone_high = zone.get("high") if isinstance(zone, dict) else None
    if zone_high is None or zone_high <= level:
        return atr_sl  # no valid zone boundary above level, use ATR-based

    zone_sl = zone_high + atr_value * _ZONE_SL_BUFFER_ATR
    if zone_sl <= min_sl:
        return zone_sl  # zone is close enough, place SL above it
    return min_sl       # zone too far, cap at 1.5×


@dataclass(frozen=True, slots=True)
class AnalysisInput:
    symbol: str
    broker_symbol: str
    account_balance: float
    risk_percent: float
    account_currency: str = "USD"
    lot_step: float = 0.01
    minimum_lot: float = 0.01
    contract_size_override: float | None = None
    timezone_name: str = "Asia/Ho_Chi_Minh"


def reward_risk(entry: float, stop: float, target: float) -> float:
    risk = abs(entry - stop)
    if risk == 0:
        raise ValueError("stop must differ from entry")
    return abs(target - entry) / risk


def calc_trade_permission(data_quality: dict[str, Any], risk_score: int, best_score: int, *, min_score: int = 65) -> dict[str, Any]:
    if not data_quality.get("terminal_connected", False) or not data_quality.get("broker_logged_in", False):
        return {"status": "blocked", "reason": "MT5 chưa sẵn sàng hoặc broker chưa đăng nhập.", "resume_after": None}
    if data_quality.get("spread_status") == "abnormal":
        return {"status": "blocked", "reason": "Spread đang bất thường, cần kiểm tra lại dữ liệu mới.", "resume_after": None}
    if data_quality.get("warning"):
        return {"status": "blocked", "reason": data_quality["warning"], "resume_after": None}
    if data_quality.get("high_impact_event_within_30m"):
        return {
            "status": "blocked",
            "reason": "Có tin kinh tế tác động cao rất gần, không nên vào lệnh trước/sau tin.",
            "resume_after": data_quality.get("resume_after"),
        }
    if data_quality.get("news_in_3h"):
        return {
            "status": "caution",
            "reason": "Có tin kinh tế tác động cao trong 3 giờ tới, chỉ theo dõi và chờ sau tin.",
            "resume_after": data_quality.get("resume_after"),
        }
    if risk_score < 9 or best_score < min_score:
        return {"status": "caution", "reason": f"Điểm setup {best_score} chưa đạt ngưỡng {min_score}, cần chờ xác nhận.", "resume_after": None, "min_score": min_score}
    return {"status": "allowed", "reason": "Dữ liệu ổn, không có cảnh báo rủi ro chính.", "resume_after": None, "min_score": min_score}


def _find_nearest_swing_for_tp(
    smc: dict[str, Any] | None,
    side: str,
    price: float,
    min_distance: float,
) -> float | None:
    """Find nearest swing high (buy) or swing low (sell) for TP target.

    Only returns swings that are at least *min_distance* away from *price*
    to ensure minimum R:R.  Searches H4 first, then H1.
    """
    if not isinstance(smc, dict):
        return None
    all_candidates: list[float] = []
    for tf in ("H4", "H1"):
        tf_data = smc.get(tf, {})
        if not isinstance(tf_data, dict):
            continue
        swings = tf_data.get("swings", {})
        if not isinstance(swings, dict):
            continue
        # BUY → swing highs above price; SELL → swing lows below price
        swing_list = swings.get("highs" if side == "buy" else "lows", [])
        if not isinstance(swing_list, list):
            continue
        for s in swing_list:
            if not isinstance(s, dict):
                continue
            level = s.get("level")
            if isinstance(level, (int, float)):
                lv = float(level)
                if side == "buy" and lv > price + min_distance:
                    all_candidates.append(lv)
                elif side == "sell" and lv < price - min_distance:
                    all_candidates.append(lv)
    if all_candidates:
        return min(all_candidates) if side == "buy" else max(all_candidates)
    return None


def build_scenarios(
    request: AnalysisInput,
    technical: dict[str, Any],
    smc: dict[str, Any],
    scores: dict[str, dict[str, Any]],
    trade_permission: dict[str, Any],
    h1_candles: list[Candle] | None = None,
    m15_candles: list[Candle] | None = None,
    correlation_context: dict[str, Any] | None = None,
    quote_to_usd_rate: float | None = None,
    spread_price: float = 0.0,
    market_regime: dict[str, Any] | None = None,
    preferred_zones: dict[str, dict[str, Any] | None] | None = None,
    is_backtest: bool = False,
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    preferred = preferred_zones or {}
    for side in ("buy", "sell"):
        side_total = scores[side].get("signal_score", scores[side].get("total", 0))
        if side_total < 50 or trade_permission["status"] == "blocked":
            continue
        plan = build_trade_plan(side, request, technical, smc, h1_candles or [], m15_candles=m15_candles, correlation_context=correlation_context, quote_to_usd_rate=quote_to_usd_rate, spread_price=spread_price, market_regime=market_regime, preferred_zone=preferred.get(side), is_backtest=is_backtest)
        if not plan:
            continue
        plan.update({
            "type": side,
            "priority": "primary" if not scenarios else "secondary",
            "score": side_total,
        })
        scenarios.append(plan)
    return sorted(scenarios, key=lambda item: item["score"], reverse=True)


def build_trade_plan(
    side: str,
    request: AnalysisInput,
    technical: dict[str, Any],
    smc: dict[str, Any],
    h1_candles: list[Candle] | None = None,
    *,
    m15_candles: list[Candle] | None = None,
    correlation_context: dict[str, Any] | None = None,
    quote_to_usd_rate: float | None = None,
    spread_price: float = 0.0,
    market_regime: dict[str, Any] | None = None,
    entry_aggressiveness: float = _ENTRY_AGGRESSIVENESS,
    preferred_zone: dict[str, Any] | None = None,
    is_backtest: bool = False,
) -> dict[str, Any] | None:
    price = technical["price"]
    atr_value = technical["atr_h4"] or technical["atr_d1"] or 0.0
    if atr_value <= 0:
        return None
    min_stop_distance = max(atr_value * _MIN_STOP_DISTANCE_ATR_MULT, spread_price * _MIN_STOP_SPREAD_MULT)
    regime_primary = market_regime.get("primary", "unknown") if isinstance(market_regime, dict) else "unknown"
    sl_mult = REGIME_SL_MULTIPLIER.get(regime_primary, _DEFAULT_SL_MULT)
    zone_dist_mult = REGIME_ZONE_DISTANCE_MULT.get(regime_primary, _DEFAULT_ZONE_DISTANCE_MULT)
    if regime_primary == "volatile":
        watch_zone_atr_mult = _WATCH_ZONE_ATR_VOLATILE
    elif "trend" in regime_primary:
        watch_zone_atr_mult = _WATCH_ZONE_ATR_TREND
    elif regime_primary == "range":
        watch_zone_atr_mult = _WATCH_ZONE_ATR_RANGE
    else:
        watch_zone_atr_mult = _WATCH_ZONE_ATR_RANGE
    h4_smc = smc.get("H4", {}) if isinstance(smc, dict) else {}
    smc_supports = _smc_zones_to_levels(h4_smc.get("demand_zones", []))
    smc_resistances = _smc_zones_to_levels(h4_smc.get("supply_zones", []))
    smc_order_blocks = _smc_zones_to_levels(h4_smc.get("order_blocks", []))

    support_zones = list(technical["support_zones"]) + smc_supports + smc_order_blocks
    resistance_zones = list(technical["resistance_zones"]) + smc_resistances + smc_order_blocks

    # Try preferred SMC zone first (from get_preferred_zone)
    # Must be on the correct side of price AND within reasonable distance.
    # Without distance check, stale zones far from price produce meaningless plans.
    use_preferred = False
    if isinstance(preferred_zone, dict) and preferred_zone.get("low") is not None and preferred_zone.get("high") is not None:
        pz_level = preferred_zone["level"]
        on_correct_side = (side == "buy" and pz_level < price) or (side == "sell" and pz_level > price)
        if on_correct_side:
            pz_distance = abs(price - pz_level)
            max_zone_distance = atr_value * zone_dist_mult
            if pz_distance <= max_zone_distance:
                use_preferred = True

    sign = 1 if side == "buy" else -1
    zones = support_zones if side == "buy" else resistance_zones
    target_zones = resistance_zones if side == "buy" else support_zones

    below = side == "buy"
    if use_preferred:
        zone = preferred_zone
    else:
        zone = select_best_level(zones, price, atr_value * zone_dist_mult, below=below)
    if not zone:
        return None

    alternate_zones_raw = select_top_levels(zones, price, atr_value * zone_dist_mult, below=below, top_n=3)

    level = zone["level"]
    entry_zone_score = zone.get("zone_score")
    entry_zone_source = zone.get("source", "technical")
    is_smc_zone = entry_zone_source in ("smc", "smc_selected")
    zone_low = zone.get("low")
    zone_high = zone.get("high")
    if zone_low is not None and zone_high is not None and zone_high > zone_low:
        zone_width_atr = (zone_high - zone_low) / atr_value
        entry_zone_atr_mult = max(_ENTRY_ZONE_ATR_MIN, min(_ENTRY_ZONE_ATR_MAX, zone_width_atr * _ENTRY_ZONE_WIDTH_MULT))
    else:
        entry_zone_atr_mult = ENTRY_ZONE_ATR_MULT

    # Watch zone extends farther in trade direction; near side gets a small offset
    watch_near = level - sign * atr_value * _WATCH_ZONE_OFFSET_ATR
    watch_far = level + sign * atr_value * watch_zone_atr_mult
    watch_low = min(watch_near, watch_far)
    watch_high = max(watch_near, watch_far)

    entry_low = level - atr_value * entry_zone_atr_mult
    entry_high = level + atr_value * entry_zone_atr_mult

    # --- Stop Loss ---
    sl_source = "atr"
    if use_preferred:
        sl_boundary = preferred_zone["low"] if side == "buy" else preferred_zone["high"]
        stop_loss = sl_boundary - sign * atr_value * _ZONE_SL_BUFFER_ATR
        if abs(level - stop_loss) < min_stop_distance:
            stop_loss = level - sign * min_stop_distance
        sl_source = "zone_boundary"
    else:
        swing_sl = _find_nearest_swing_for_sl(smc, side, level)
        if swing_sl is not None:
            stop_loss = swing_sl - sign * atr_value * _SWING_SL_BUFFER_ATR
            if abs(level - stop_loss) < min_stop_distance:
                stop_loss = level - sign * min_stop_distance
            sl_source = "swing"
        elif side == "buy":
            stop_loss = _calc_stop_loss_buy(level, atr_value, sl_mult, min_stop_distance, zone)
        else:
            stop_loss = _calc_stop_loss_sell(level, atr_value, sl_mult, min_stop_distance, zone)

    # Guard: SL must be on the correct side of the entry zone
    sl_edge = (entry_low if side == "buy" else entry_high) - sign * atr_value * _SL_FLOOR_BUFFER_ATR
    if (stop_loss - sl_edge) * sign >= 0:
        stop_loss = sl_edge

    # Guard: skip plan if SL is too tight (relaxed for preferred/SMC zones)
    if use_preferred or is_smc_zone:
        _min_sl = atr_value * _MIN_STOP_DISTANCE_ATR_MULT
    else:
        _min_sl = atr_value * _MIN_SL_DISTANCE_ATR
    if abs(level - stop_loss) < _min_sl:
        return None

    # Entry price for DISPLAY (nearest edge = best-case RR shown to user)
    entry_for_rr = (
        entry_low + (entry_high - entry_low) * entry_aggressiveness
        if side == "buy" else
        entry_high + (entry_low - entry_high) * entry_aggressiveness
    )
    # Entry price for TP SELECTION (midpoint = conservative — TP must clear RR>=1
    # even when filled at zone center, not just the best edge)
    entry_for_selection = (
        entry_low + (entry_high - entry_low) * _TP_SELECTION_AGGRESSIVENESS
        if side == "buy" else
        entry_high + (entry_low - entry_high) * _TP_SELECTION_AGGRESSIVENESS
    )
    sel_risk_distance = abs(entry_for_selection - stop_loss)

    # --- TP1 cascade: equal-level → S/R zone → Fib extension → swing ---
    # ALL RR checks use entry_for_selection (conservative anchor) for TP validity.
    # TP targets are searched relative to entry_for_selection for consistency.
    tp1 = _find_nearest_equal_level(smc, side, entry_for_selection)
    if tp1 is not None and abs(tp1 - entry_for_selection) > sel_risk_distance * _EQ_TP_MAX_RR:
        tp1 = None  # equal level too far, fall through
    if tp1 is None or abs(tp1 - entry_for_selection) < sel_risk_distance:
        tp1 = nearest_target(target_zones, entry_for_selection, above=(side == "buy"))
    if tp1 is None or abs(tp1 - entry_for_selection) < sel_risk_distance:
        if regime_primary != "range":
            tp1 = _fib_extension_target(smc, side, atr_value, _FIB_TP1)
    if tp1 is None or abs(tp1 - entry_for_selection) < sel_risk_distance:
        tp1 = _find_nearest_swing_for_tp(smc, side, entry_for_selection, sel_risk_distance)

    # Guard: TP1 must be strictly past the far edge of the entry zone
    far_edge = level + sign * atr_value * entry_zone_atr_mult
    if tp1 is not None and (tp1 - far_edge) * sign <= 0:
        tp1 = None

    if tp1 is None or abs(tp1 - entry_for_selection) < sel_risk_distance:
        if use_preferred or is_smc_zone:
            tp1 = None   # không có TP thật → để trống
            tp2 = None
        else:
            return None

    # --- TP2: next S/R zone, fallback to Fib 0.618 ---
    tp2 = None
    if tp1 is not None:
        tp2 = next_target(target_zones, tp1, above=(side == "buy"))
        if tp2 is None:
            if regime_primary != "range":
                tp2 = _fib_extension_target(smc, side, atr_value, _FIB_TP2)
        # Guard: TP2 must be on the correct side of TP1 (farther target)
        if tp2 is not None and (tp2 - tp1) * sign <= 0:
            tp2 = None
        # Guard: TP2 must be strictly past the far edge of the entry zone
        if tp2 is not None and (tp2 - far_edge) * sign <= 0:
            tp2 = None
        # Guard: TP2 must be at least _TP2_MIN_GAP_ATR * ATR away from TP1
        if tp2 is not None and abs(tp2 - tp1) < atr_value * _TP2_MIN_GAP_ATR:
            tp2 = None

    # --- Condition & Invalidation ---
    if side == "buy":
        condition = _build_buy_condition(h4_smc)
        invalidation = _build_buy_invalidation(stop_loss, h4_smc)
    else:
        condition = _build_sell_condition(h4_smc)
        invalidation = _build_sell_invalidation(stop_loss, h4_smc)

    entry_zone = [round_price(entry_low), round_price(entry_high)]
    watch_zone = [round_price(watch_low), round_price(watch_high)]
    entry_state = evaluate_entry(
        side=side,
        technical=technical,
        smc=smc,
        h1_candles=h1_candles or [],
        entry_zone=entry_zone,
        m15_candles=m15_candles,
        is_backtest=is_backtest,
    )
    # Entry Ladder Phase 1: scale size by price position within zone
    entry_ladder = entry_state.get("entry_ladder", {})
    size_multiplier = float(entry_ladder.get("size_multiplier", 1.0)) if isinstance(entry_ladder, dict) else 1.0
    sizing = position_sizing(
        request, entry_for_rr, stop_loss,
        quote_to_usd_rate=quote_to_usd_rate,
        size_multiplier=size_multiplier,
    )

    corr_warnings: list[str] = []
    corr_context: dict[str, Any] | None = None
    if correlation_context:
        corr_dxy = correlation_context.get("dxy_candles")
        corr_us10y = correlation_context.get("us10y_candles")
        corr_us2y = correlation_context.get("us2y_candles")
        corr_vix = correlation_context.get("vix_candles")
        corr_warnings = get_correlation_warnings(request.symbol, side, dxy_candles=corr_dxy, us10y_candles=corr_us10y, us2y_candles=corr_us2y, vix_candles=corr_vix)
        corr_context = summarize_correlation_context(request.symbol, side, dxy_candles=corr_dxy, us10y_candles=corr_us10y, us2y_candles=corr_us2y, vix_candles=corr_vix)

    # Build RR strings only when TP is real (not fallback)
    if tp1 is not None:
        risk_reward_str = f"1:{reward_risk(entry_for_rr, stop_loss, tp1):.1f}"
        effective_rr = calculate_expected_effective_rr(
            direction=side,
            entry=entry_for_rr,
            stop_loss=stop_loss,
            take_profit=tp1,
            spread_price=spread_price,
        )
        # RR range across 3 fill positions within entry zone
        #   best  = mép gần nhất (aggressiveness 0.0) — same as risk_reward_str
        #   base  = trung điểm (aggressiveness 0.5)
        #   worst = mép xa nhất (aggressiveness 1.0)
        # All values are estimates, not verified against historical fill data.
        entry_worst = (
            entry_high if side == "buy" else entry_low
        )
        rr_range = {
            "best": round(reward_risk(entry_for_rr, stop_loss, tp1), 1),
            "base": round(reward_risk(entry_for_selection, stop_loss, tp1), 1),
            "worst": round(reward_risk(entry_worst, stop_loss, tp1), 1),
        }
    else:
        risk_reward_str = None
        effective_rr = None
        rr_range = {"best": None, "base": None, "worst": None}

    return {
        "entry_zone": entry_zone,
        "entry_price": round_price(entry_for_rr),
        "watch_zone": watch_zone,
        "stop_loss": round_price(stop_loss),
        "take_profit": [round_price(value) for value in (tp1, tp2) if value is not None],
        "risk_reward": risk_reward_str,
        "expected_effective_rr": effective_rr,
        "risk_reward_range": rr_range,
        "condition": condition,
        "invalidation": invalidation,
        "position_sizing": sizing,
        "correlation_warnings": corr_warnings,
        "correlation_context": corr_context,
        "entry_zone_score": entry_zone_score,
        "entry_zone_source": entry_zone_source,
        "sl_source": sl_source,
        "tp_source": "none" if tp1 is None else "structure",
        "entry_ladder": entry_ladder,
        "sub_zone": entry_ladder.get("sub_zone") if isinstance(entry_ladder, dict) else None,
        "alternate_zones": [
            {
                "level": round_price(z["level"]),
                "zone_score": z.get("zone_score", z.get("_effective_score")),
                "source": z.get("source", "technical"),
            }
            for z in alternate_zones_raw
        ],
        **entry_state,
    }


def _smc_zones_to_levels(zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for zone in zones[:4]:
        if zone.get("broken"):
            continue
        low = zone.get("low")
        high = zone.get("high")
        if low is None or high is None:
            continue
        level = (low + high) / 2
        converted.append(
            {
                "level": level,
                "low": low,
                "high": high,
                "type": zone.get("type", "smc_zone"),
                "strength": zone.get("strength", "moderate"),
                "confluence_count": zone.get("confluence_count", 1),
                "consolidation_bars": zone.get("consolidation_bars", 0),
                "zone_score": zone.get("zone_score", 50),
                "freshness_bars": zone.get("freshness_bars"),
                "mitigated": zone.get("mitigated", False),
                "broken": zone.get("broken", False),
                "test_count": zone.get("test_count", 0),
                "displacement_multiple": zone.get("displacement_multiple", 0),
                "liquidity_sweep": zone.get("liquidity_sweep", False),
                "zone_location": zone.get("zone_location", "unknown"),
                "source": "smc",
            }
        )
    return converted


def _build_buy_condition(h4_smc: dict[str, Any]) -> str:
    base = "Chỉ cân nhắc nếu H1 đóng nến tăng tại vùng hỗ trợ và spread vẫn bình thường."
    extras: list[str] = []
    if h4_smc.get("bos") and h4_smc.get("displacement") == "bullish":
        extras.append("BOS H4 đã xác nhận theo hướng tăng")
    if h4_smc.get("demand_zones"):
        extras.append("ưu tiên khớp khi giá vào demand zone gần nhất")
    if h4_smc.get("fvg"):
        extras.append("nếu giá lấp FVG bullish, ưu tiên xác nhận thêm")
    if not extras:
        return base
    return base + " " + "; ".join(extras) + "."


def _build_buy_invalidation(stop_loss: float, h4_smc: dict[str, Any]) -> str:
    base = f"H1 đóng dưới {stop_loss:.5f} hoặc spread giãn bất thường."
    if h4_smc.get("choch") and h4_smc.get("displacement") == "bearish":
        return base + " Cảnh báo CHOCH bearish trên H4 — ưu tiên đứng ngoài."
    return base


def _build_sell_condition(h4_smc: dict[str, Any]) -> str:
    base = "Chỉ cân nhắc nếu H1 đóng nến giảm tại vùng kháng cự và spread vẫn bình thường."
    extras: list[str] = []
    if h4_smc.get("bos") and h4_smc.get("displacement") == "bearish":
        extras.append("BOS H4 đã xác nhận theo hướng giảm")
    if h4_smc.get("supply_zones"):
        extras.append("ưu tiên khớp khi giá vào supply zone gần nhất")
    if h4_smc.get("fvg"):
        extras.append("nếu giá lấp FVG bearish, ưu tiên xác nhận thêm")
    if not extras:
        return base
    return base + " " + "; ".join(extras) + "."


def _build_sell_invalidation(stop_loss: float, h4_smc: dict[str, Any]) -> str:
    base = f"H1 đóng trên {stop_loss:.5f} hoặc spread giãn bất thường."
    if h4_smc.get("choch") and h4_smc.get("displacement") == "bullish":
        return base + " Cảnh báo CHOCH bullish trên H4 — ưu tiên đứng ngoài."
    return base


_STRENGTH_FALLBACK_SCORE = {"strong": 80, "moderate": 60, "weak": 45}


def _effective_zone_score(zone: dict[str, Any]) -> float:
    """Lấy zone_score thực nếu có, fallback về ước lượng từ strength bucket
    cho zone technical thường (không có zone_score gốc)."""
    score = zone.get("zone_score")
    if score is not None:
        return float(score)
    return float(_STRENGTH_FALLBACK_SCORE.get(zone.get("strength", "weak"), 45))


def select_best_level(
    zones: list[dict[str, Any]], price: float, max_distance: float, *, below: bool
) -> dict[str, Any] | None:
    if below:
        candidates = [
            zone for zone in zones
            if zone["level"] <= price and (price - zone["level"]) <= max_distance
        ]
    else:
        candidates = [
            zone for zone in zones
            if zone["level"] >= price and (zone["level"] - price) <= max_distance
        ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda zone: (-_effective_zone_score(zone), abs(zone["level"] - price)),
    )[0]


def select_top_levels(
    zones: list[dict[str, Any]], price: float, max_distance: float, *,
    below: bool, top_n: int = 3,
) -> list[dict[str, Any]]:
    """Giống select_best_level nhưng trả về top-N candidate đã sort theo
    zone_score, dùng cho hiển thị 'plan B/C'. Không thay đổi hành vi chọn
    zone chính trong select_best_level."""
    if below:
        candidates = [z for z in zones if z["level"] <= price and (price - z["level"]) <= max_distance]
    else:
        candidates = [z for z in zones if z["level"] >= price and (z["level"] - price) <= max_distance]
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda z: (-_effective_zone_score(z), abs(z["level"] - price)))
    return ranked[:top_n]


def nearest_target(zones: list[dict[str, Any]], reference: float, *, above: bool) -> float | None:
    levels = sorted(
        {zone["level"] for zone in zones if zone["level"] > reference}
        if above
        else {zone["level"] for zone in zones if zone["level"] < reference},
        reverse=not above,
    )
    return levels[0] if levels else None


def next_target(zones: list[dict[str, Any]], first_target: float, *, above: bool) -> float | None:
    levels = sorted(
        {zone["level"] for zone in zones if zone["level"] > first_target}
        if above
        else {zone["level"] for zone in zones if zone["level"] < first_target},
        reverse=not above,
    )
    return levels[0] if levels else None


def position_sizing(request: AnalysisInput, entry_price: float, stop_loss: float, *, quote_to_usd_rate: float | None = None, size_multiplier: float = 1.0) -> dict[str, Any]:
    contract_size = contract_size_for(request)
    risk_amount = request.account_balance * request.risk_percent / 100 * size_multiplier
    price_distance = abs(entry_price - stop_loss)
    loss_per_lot = price_distance * contract_size
    if quote_to_usd_rate is None:
        quote_to_usd_rate = _resolve_quote_to_usd_rate(request.symbol)
    if quote_to_usd_rate is not None and quote_to_usd_rate > 0:
        loss_per_lot = loss_per_lot * quote_to_usd_rate
    raw_lot = risk_amount / loss_per_lot if loss_per_lot else 0.0
    lot = round_lot(raw_lot, request.lot_step, request.minimum_lot)
    return {
        "account_balance": request.account_balance,
        "risk_pct": request.risk_percent,
        "risk_amount_usd": risk_amount,
        "entry_price": round_price(entry_price),
        "stop_loss": round_price(stop_loss),
        "price_distance": round_price(price_distance),
        "contract_size": contract_size,
        "suggested_lot": lot,
        "size_multiplier": size_multiplier,
    }


def recalc_execution_lot(
    *,
    symbol: str,
    broker_symbol: str,
    account_balance: float,
    risk_percent: float,
    account_currency: str,
    lot_step: float,
    minimum_lot: float,
    contract_size_override: float | None,
    entry_price: float,
    stop_loss: float,
    quote_to_usd_rate: float | None,
    fallback_lot: float,
) -> float:
    """Tính lại lot ngay trước khi vào lệnh, có quote_to_usd_rate.

    Nếu không lấy được tỷ giá quy đổi cho non-USD quote, fallback về
    *fallback_lot* (suggested_lot từ scan đã được tính đúng trước đó).
    """
    if quote_to_usd_rate is None:
        quote_currency = symbol.split("/")[-1] if "/" in symbol else symbol[-3:]
        if quote_currency != "USD":
            if fallback_lot <= 0:
                fallback_lot = minimum_lot
            return fallback_lot
    sizing = position_sizing(
        AnalysisInput(
            symbol=symbol,
            broker_symbol=broker_symbol,
            account_balance=account_balance,
            risk_percent=risk_percent,
            account_currency=account_currency,
            lot_step=lot_step,
            minimum_lot=minimum_lot,
            contract_size_override=contract_size_override,
        ),
        entry_price,
        stop_loss,
        quote_to_usd_rate=quote_to_usd_rate,
    )
    return sizing["suggested_lot"]


def _resolve_quote_to_usd_rate(symbol: str) -> float | None:
    """Try to get quote-currency to USD conversion rate from MT5."""
    if "/" not in symbol:
        return None
    quote = symbol.split("/")[-1]
    if quote == "USD":
        return 1.0
    mt5 = None
    initialized = False
    owned_connection = False
    try:
        import MetaTrader5 as mt5

        try:
            owned_connection = mt5.terminal_info() is None and mt5.account_info() is None
        except Exception:
            owned_connection = True
        initialized = mt5.initialize()
        if not initialized:
            return None
        for pair_name in (quote + "USD", "USD" + quote):
            tick = mt5.symbol_info_tick(pair_name)
            if tick is None:
                symbols = mt5.symbols_get()
                for sym in (symbols or []):
                    name = getattr(sym, "name", "")
                    if name.upper().startswith(pair_name.upper()):
                        mt5.symbol_select(name, True)
                        tick = mt5.symbol_info_tick(name)
                        break
            if tick and tick.bid:
                rate = float(tick.bid)
                return rate if pair_name.startswith(quote) else 1.0 / rate
        return None
    except Exception:
        return None
    finally:
        if initialized and owned_connection and mt5 is not None:
            mt5.shutdown()


def contract_size_for(request: AnalysisInput) -> float:
    # Flow ưu tiên:
    # 1. Controller override (symbols đặc biệt lấy từ MT5, forex luôn lấy từ settings 100,000)
    # 2. SYMBOL_CONFIG lookup (chỉ chứa symbol đặc biệt như XAU/USD, XAG/USD, BTC/USD)
    # 3. Fallback mặc định 100,000 (standard forex lot)
    if request.contract_size_override and request.contract_size_override > 0:
        return request.contract_size_override
    return float(SYMBOL_CONFIG.get(request.symbol, {}).get("contract_size", 100000.0))


def contract_size_override_for_symbol(
    symbol: str,
    data_quality: dict[str, Any],
    forex_contract_size: float,
) -> float | None:
    if symbol in SYMBOL_CONFIG:
        broker_contract_size = data_quality.get("contract_size")
        if broker_contract_size:
            try:
                broker_value = float(broker_contract_size)
            except (TypeError, ValueError):
                broker_value = 0.0
            if broker_value > 0:
                return broker_value
        return float(SYMBOL_CONFIG[symbol]["contract_size"])
    return forex_contract_size


def round_lot(value: float, step: float, minimum: float) -> float:
    if value <= 0:
        return 0.0
    step = step or 0.01
    rounded = floor(value / step) * step
    return round(max(minimum, rounded), 2)


def round_price(value: float) -> float:
    return round(value, 5)


# ---------------------------------------------------------------------------
# Phase 6: Expected effective R:R (spread-adjusted)
# ---------------------------------------------------------------------------


def calculate_spread_cost(spread_price: float | int | str | None) -> float:
    """Chuyen spread_price thanh float an toan.

    Tra ve 0.0 neu None, am, hoac khong convert duoc.
    Neu gia tri > 1, coi la points (MT5) va chuyen sang gia (points / 100000).
    """
    try:
        value = float(spread_price or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if value < 0:
        return 0.0
    # MT5 returns spread in points (e.g. 16). Convert to price (0.00016).
    if value > 1.0:
        value = value / 100000.0
    return value


def calculate_expected_effective_rr(
    direction: str,
    entry: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    spread_price: float | int | str | None = 0.0,
) -> float:
    """Tinh expected effective R:R sau khi tru spread.

    Spread lam tang risk (effective_risk = risk + spread_cost)
    va giam reward (effective_reward = reward - spread_cost).

    Returns
    -------
    float
        Effective R:R, lam tron 4 chu so thap phan.
        Tra 0.0 neu input khong hop le hoac effective_risk <= 0.
    """
    try:
        direction = str(direction).lower()
        entry_val = float(entry) if entry is not None else None
        sl_val = float(stop_loss) if stop_loss is not None else None
        tp_val = float(take_profit) if take_profit is not None else None
    except (TypeError, ValueError):
        return 0.0

    if entry_val is None or sl_val is None or tp_val is None:
        return 0.0

    if direction not in ("buy", "sell"):
        return 0.0

    if direction == "buy":
        risk = abs(entry_val - sl_val)
        reward = abs(tp_val - entry_val)
    else:  # sell
        risk = abs(sl_val - entry_val)
        reward = abs(entry_val - tp_val)

    spread_cost = calculate_spread_cost(spread_price)

    effective_risk = risk + spread_cost
    effective_reward = reward - spread_cost

    if effective_risk <= 0:
        return 0.0

    return round(max(effective_reward / effective_risk, 0.0), 4)
