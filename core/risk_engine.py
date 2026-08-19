from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from math import floor
from typing import Any, Protocol

import json
from pathlib import Path

from core.entry_engine import evaluate_entry
from core.market_models import Candle
from core.signal_engine import clamp
from core.correlation_check import get_correlation_warnings, summarize_correlation_context
from core.reason_codes import EXECUTION_ZONE_RR_EMPTY
from core.smc_context import (
    calculate_effective_zone_score,
    zone_matches_direction,
)
from core.risk_parameter_context import risk_parameter


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
    "XAU/USD": {"contract_size": 100.0, "quote_currency": "USD", "method": "price_distance_x_contract_size", "asset_class": "metals"},
    "XAG/USD": {"contract_size": 5000.0, "quote_currency": "USD", "method": "price_distance_x_contract_size", "asset_class": "metals"},
    "BTC/USD": {"contract_size": 1.0, "quote_currency": "USD", "method": "price_distance_x_contract_size", "asset_class": "crypto"},
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
# Relaxed zone-SL cap for high-quality zones: allows the stop to sit behind
# real structure instead of inside the zone.  Zones whose effective score is
# below _ZONE_SL_HIGH_SCORE_THRESHOLD keep the tight legacy cap.
_ZONE_SL_CAP_RATIO_HIGH_SCORE = _rp.get("zone_sl_cap_ratio_high_score", 2.5)
_ZONE_SL_HIGH_SCORE_THRESHOLD = _rp.get("zone_sl_high_score_threshold", 80)
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
_TP1_MIN_CLEARANCE_ATR = _rp.get("tp1_min_clearance_atr", 0.15)
_TP1_MIN_EFFECTIVE_RR_BASE = _rp.get("tp1_min_effective_rr_base", 1.3)
_TP_TARGET_BUFFER_ATR = _rp.get("tp_target_buffer_atr", 0.03)
_ENTRY_ZONE_BUFFER_ATR = _rp.get("entry_zone_buffer_atr", 0.05)
_ENTRY_ZONE_MAX_WIDTH_ATR = _rp.get("entry_zone_max_width_atr", 0.50)
_ENTRY_ZONE_HALF_WIDTH_ATR = _rp.get("entry_zone_half_width_atr", 0.25)
_EXECUTION_ZONE_WIDTH_ATR_BY_QUALITY = _rp.get(
    "execution_zone_width_atr_by_quality",
    {"strong": 0.12, "moderate": 0.18, "weak": 0.25},
)
_EXECUTION_ZONE_QUALITY_THRESHOLDS = _rp.get(
    "execution_zone_quality_thresholds",
    {"strong": 70, "moderate": 50},
)
_EXECUTION_ZONE_MIN_EFFECTIVE_RR = float(
    _rp.get("execution_zone_min_effective_rr", 1.3)
)
_EXECUTION_ZONE_RR_TOLERANCE = float(
    _rp.get("execution_zone_rr_tolerance", 0.0001)
)
_MIN_STOP_DISTANCE_ATR_MULT = _rp.get("min_sl_distance_atr_mult", 0.20)
_MIN_STOP_SPREAD_MULT = _rp.get("min_stop_spread_mult", 3)
_ENTRY_ZONE_WIDTH_MULT = _rp.get("entry_zone_width_mult", 0.5)
_WATCH_ZONE_OFFSET_ATR = _rp.get("watch_zone_offset_atr", 0.10)
_SL_FLOOR_BUFFER_ATR = _rp.get("sl_floor_buffer_atr", 0.10)
_WATCH_ZONE_ATR_VOLATILE = _rp.get("watch_zone_atr_volatile", 0.70)
_WATCH_ZONE_ATR_TREND = _rp.get("watch_zone_atr_trend", 0.40)
_WATCH_ZONE_ATR_RANGE = _rp.get("watch_zone_atr_range", 0.50)

# ── Asset class SL multiplier (applied on top of regime_sl_multiplier) ──
ASSET_CLASS_SL_MULTIPLIER: dict[str, float] = _rp.get("asset_class_sl_multiplier", {
    "forex": 1.0, "metals": 1.0, "crypto": 1.0,
})


def _asset_class_for(symbol: str) -> str:
    """Return the asset class for a given symbol.

    Looks up SYMBOL_CONFIG; returns "forex" for any symbol not explicitly listed
    (i.e. all standard FX pairs).
    """
    cfg = SYMBOL_CONFIG.get(symbol, {})
    return str(cfg.get("asset_class", "forex"))


def _price_digits_for_request(request: AnalysisInput) -> int:
    if isinstance(request.price_digits, int) and 0 <= request.price_digits <= 10:
        return request.price_digits
    normalized = "".join(
        char for char in str(request.symbol).upper() if char.isalpha()
    )
    return 3 if normalized.endswith("JPY") else 5


def _execution_zone_quality(effective_score: object) -> str:
    try:
        score = float(effective_score)
    except (TypeError, ValueError):
        score = 0.0
    try:
        strong = float(_EXECUTION_ZONE_QUALITY_THRESHOLDS.get("strong", 70))
        moderate = float(
            _EXECUTION_ZONE_QUALITY_THRESHOLDS.get("moderate", 50)
        )
    except (TypeError, ValueError):
        strong, moderate = 70.0, 50.0
    if score >= strong:
        return "strong"
    if score >= moderate:
        return "moderate"
    return "weak"


def _execution_zone_width_atr(effective_score: object) -> tuple[str, float]:
    quality = _execution_zone_quality(effective_score)
    try:
        width = float(
            _EXECUTION_ZONE_WIDTH_ATR_BY_QUALITY.get(quality, 0.25)
        )
    except (TypeError, ValueError):
        width = 0.25
    return quality, max(0.0, width)


def _build_execution_sub_zone(
    *,
    side: str,
    source_low: float,
    source_high: float,
    atr_value: float,
    effective_score: object,
    price_digits: int,
) -> dict[str, Any] | None:
    """Build a proximal, precision-safe sub-zone inside source boundaries."""
    if (
        side not in {"buy", "sell"}
        or source_high <= source_low
        or atr_value <= 0
    ):
        return None
    quality, width_atr_target = _execution_zone_width_atr(effective_score)
    width = min(
        source_high - source_low,
        atr_value * width_atr_target,
    )
    if side == "buy":
        raw_low = max(source_low, source_high - width)
        raw_high = source_high
    else:
        raw_low = source_low
        raw_high = min(source_high, source_low + width)

    execution_low = round_price_up(raw_low, price_digits)
    execution_high = round_price_down(raw_high, price_digits)
    if execution_high <= execution_low:
        return None
    return {
        "entry_zone": [execution_low, execution_high],
        "quality": quality,
        "width_atr_target": width_atr_target,
    }


def _trim_execution_zone_for_effective_rr(
    *,
    side: str,
    structural_zone: list[float],
    stop_loss: float,
    take_profit: float | None,
    spread_price: float,
    min_effective_rr: float,
    tolerance: float,
    price_digits: int,
) -> dict[str, Any]:
    """Intersect a structural execution zone with its effective-RR-valid range."""
    low, high = (float(structural_zone[0]), float(structural_zone[1]))
    diagnostics: dict[str, Any] = {
        "status": "not_applicable_no_tp1" if take_profit is None else "unchanged",
        "trimmed": False,
        "min_effective_rr": float(min_effective_rr),
        "tolerance": float(tolerance),
        "structural_zone": [low, high],
        "rr_boundary": None,
        "final_zone": [low, high],
        "pre_trim_effective_rr_worst": None,
        "post_trim_effective_rr_worst": None,
    }
    if take_profit is None:
        return diagnostics
    if side not in {"buy", "sell"} or high <= low or min_effective_rr <= 0:
        diagnostics.update({"status": "empty", "final_zone": None})
        return diagnostics

    worst_entry = high if side == "buy" else low
    diagnostics["pre_trim_effective_rr_worst"] = calculate_expected_effective_rr(
        direction=side,
        entry=worst_entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        spread_price=spread_price,
    )
    spread_cost = calculate_spread_cost(spread_price)
    denominator = 1.0 + min_effective_rr
    if side == "buy":
        boundary = (
            take_profit
            + min_effective_rr * stop_loss
            - denominator * spread_cost
        ) / denominator
        final_low = low
        final_high = min(high, round_price_down(boundary, price_digits))
    else:
        boundary = (
            take_profit
            + min_effective_rr * stop_loss
            + denominator * spread_cost
        ) / denominator
        final_low = max(low, round_price_up(boundary, price_digits))
        final_high = high
    diagnostics["rr_boundary"] = boundary

    if final_high <= final_low:
        diagnostics.update({"status": "empty", "final_zone": None})
        return diagnostics

    post_worst_entry = final_high if side == "buy" else final_low
    post_worst_rr = calculate_expected_effective_rr(
        direction=side,
        entry=post_worst_entry,
        stop_loss=stop_loss,
        take_profit=take_profit,
        spread_price=spread_price,
    )
    diagnostics["post_trim_effective_rr_worst"] = post_worst_rr
    if post_worst_rr is None or post_worst_rr + tolerance < min_effective_rr:
        diagnostics.update({"status": "empty", "final_zone": None})
        return diagnostics

    final_zone = [final_low, final_high]
    trimmed = final_low > low or final_high < high
    diagnostics.update(
        {
            "status": "trimmed" if trimmed else "unchanged",
            "trimmed": trimmed,
            "final_zone": final_zone,
        }
    )
    return diagnostics


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
    price_digits: int = 5,
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
        return _round_target_price(target, side, price_digits)
    else:
        target = end - impulse * fib_level
        if target >= end:
            return None
        return _round_target_price(target, side, price_digits)


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


def _zone_sl_cap_ratio(zone_score: float | None) -> tuple[float, bool]:
    """Pick the zone-SL cap ratio from the zone's effective quality score.

    High-quality zones (effective score >= ``zone_sl_high_score_threshold``)
    earn the relaxed ``zone_sl_cap_ratio_high_score`` cap so the stop can sit
    behind real structure.  Every other zone keeps the tight legacy
    ``zone_sl_cap_ratio`` cap that blocks garbage/anomalous far zones.

    Returns ``(cap_ratio, is_high_score)``.  A ``None`` score is treated as
    low-quality (legacy cap).  All three keys go through ``risk_parameter``
    so backtest sweeps can override them uniformly.
    """
    threshold = risk_parameter(
        "zone_sl_high_score_threshold", _ZONE_SL_HIGH_SCORE_THRESHOLD
    )
    if zone_score is not None and float(zone_score) >= threshold:
        return (
            risk_parameter(
                "zone_sl_cap_ratio_high_score", _ZONE_SL_CAP_RATIO_HIGH_SCORE
            ),
            True,
        )
    return risk_parameter("zone_sl_cap_ratio", _ZONE_SL_CAP_RATIO), False


def _calc_stop_loss_buy(
    level: float,
    atr_value: float,
    sl_mult: float,
    min_stop_distance: float,
    zone: dict[str, Any] | None,
    zone_score: float | None = None,
) -> float | None:
    """Calculate BUY stop loss: prefer below-zone-low, capped by zone quality.

    The widest allowed stop is ``level - ATR × sl_mult × cap_ratio`` where
    ``cap_ratio`` comes from :func:`_zone_sl_cap_ratio`.  For a high-quality
    zone whose structural stop (below the zone low) still exceeds even the
    relaxed cap, returns ``None`` — the caller must reject the plan rather
    than place the stop inside the zone, where normal oscillation sweeps it
    while position sizing simultaneously inflates the lot.
    """
    atr_sl = level - max(atr_value * sl_mult, min_stop_distance)

    zone_low = zone.get("low") if isinstance(zone, dict) else None
    if zone_low is None or zone_low >= level:
        return atr_sl  # no valid zone boundary below level, use ATR-based

    cap_ratio, high_score = _zone_sl_cap_ratio(zone_score)
    cap_sl = level - atr_value * sl_mult * cap_ratio  # widest allowed

    zone_sl = zone_low - atr_value * risk_parameter(
        "zone_sl_buffer_atr", _ZONE_SL_BUFFER_ATR
    )
    if zone_sl >= cap_sl:
        return zone_sl  # zone is close enough, place SL below it
    if high_score:
        return None     # structural SL beyond relaxed cap → refuse the plan
    return cap_sl       # low-score zone: keep the legacy tight cap


def _calc_stop_loss_sell(
    level: float,
    atr_value: float,
    sl_mult: float,
    min_stop_distance: float,
    zone: dict[str, Any] | None,
    zone_score: float | None = None,
) -> float | None:
    """Calculate SELL stop loss: prefer above-zone-high, capped by zone quality.

    Mirror of :func:`_calc_stop_loss_buy`.  Returns ``None`` when a
    high-quality zone's structural stop exceeds even the relaxed cap, so the
    caller rejects the plan instead of hiding the stop inside the zone.
    """
    atr_sl = level + max(atr_value * sl_mult, min_stop_distance)

    zone_high = zone.get("high") if isinstance(zone, dict) else None
    if zone_high is None or zone_high <= level:
        return atr_sl  # no valid zone boundary above level, use ATR-based

    cap_ratio, high_score = _zone_sl_cap_ratio(zone_score)
    cap_sl = level + atr_value * sl_mult * cap_ratio  # widest allowed

    zone_sl = zone_high + atr_value * risk_parameter(
        "zone_sl_buffer_atr", _ZONE_SL_BUFFER_ATR
    )
    if zone_sl <= cap_sl:
        return zone_sl  # zone is close enough, place SL above it
    if high_score:
        return None     # structural SL beyond relaxed cap → refuse the plan
    return cap_sl       # low-score zone: keep the legacy tight cap


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
    price_digits: int | None = None


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
    strict_preferred_zones: bool = False,
    require_preferred_zones: bool = False,
    is_backtest: bool = False,
) -> list[dict[str, Any]]:
    scenarios: list[dict[str, Any]] = []
    preferred = preferred_zones or {}
    for side in ("buy", "sell"):
        if (
            require_preferred_zones
            and not isinstance(preferred.get(side), dict)
        ):
            # Active canonical scoring cannot create a plan from an unrelated
            # technical level when its own mandatory zone selection failed.
            continue
        side_total = scores[side].get("signal_score", scores[side].get("total", 0))
        if side_total < 50 or trade_permission["status"] == "blocked":
            continue
        plan = build_trade_plan(
            side,
            request,
            technical,
            smc,
            h1_candles or [],
            m15_candles=m15_candles,
            correlation_context=correlation_context,
            quote_to_usd_rate=quote_to_usd_rate,
            spread_price=spread_price,
            market_regime=market_regime,
            preferred_zone=preferred.get(side),
            strict_preferred_zone=strict_preferred_zones,
            is_backtest=is_backtest,
        )
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
    entry_aggressiveness: float | None = None,
    preferred_zone: dict[str, Any] | None = None,
    strict_preferred_zone: bool = False,
    is_backtest: bool = False,
) -> dict[str, Any] | None:
    price = technical["price"]
    price_digits = _price_digits_for_request(request)
    atr_value = technical["atr_h4"] or technical["atr_d1"] or 0.0
    if atr_value <= 0:
        return None
    entry_aggressiveness = (
        risk_parameter("entry_aggressiveness", _ENTRY_AGGRESSIVENESS)
        if entry_aggressiveness is None
        else float(entry_aggressiveness)
    )
    min_stop_distance = max(
        atr_value * risk_parameter(
            "min_stop_distance_atr_mult", _MIN_STOP_DISTANCE_ATR_MULT
        ),
        spread_price * _MIN_STOP_SPREAD_MULT,
    )
    regime_primary = market_regime.get("primary", "unknown") if isinstance(market_regime, dict) else "unknown"
    sl_mult = REGIME_SL_MULTIPLIER.get(regime_primary, _DEFAULT_SL_MULT)
    # Apply asset-class multiplier on top of regime multiplier.
    # Default multiplier is 1.0 for all classes — no-op until tuned separately.
    asset_cls = _asset_class_for(request.symbol)
    sl_mult *= ASSET_CLASS_SL_MULTIPLIER.get(asset_cls, 1.0)
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

    bullish_order_blocks = [
        zone
        for zone in smc_order_blocks
        if zone_matches_direction(zone, "buy")
    ]
    bearish_order_blocks = [
        zone
        for zone in smc_order_blocks
        if zone_matches_direction(zone, "sell")
    ]

    support_zones = (
        list(technical["support_zones"])
        + smc_supports
        + bullish_order_blocks
    )
    resistance_zones = (
        list(technical["resistance_zones"])
        + smc_resistances
        + bearish_order_blocks
    )

    # Try preferred SMC zone first (canonical selected zone from the
    # SMC result/consumer).
    # Must be on the correct side of price AND within reasonable distance.
    # Without distance check, stale zones far from price produce meaningless plans.
    use_preferred = False
    preferred_zone_type = (
        preferred_zone.get("zone_type") or preferred_zone.get("type")
        if isinstance(preferred_zone, dict)
        else None
    )
    preferred_direction_ok = (
        zone_matches_direction(preferred_zone, side)
        or (
            isinstance(preferred_zone, dict)
            and not preferred_zone_type
            and preferred_zone.get("source") == "smc_selected"
        )
    )
    if (
        isinstance(preferred_zone, dict)
        and preferred_direction_ok
        and preferred_zone.get("low") is not None
        and preferred_zone.get("high") is not None
    ):
        pz_level = preferred_zone["level"]
        on_correct_side = (side == "buy" and pz_level < price) or (side == "sell" and pz_level > price)
        if on_correct_side:
            pz_distance = abs(price - pz_level)
            max_zone_distance = atr_value * zone_dist_mult
            if pz_distance <= max_zone_distance:
                use_preferred = True
    if strict_preferred_zone and isinstance(preferred_zone, dict) and not use_preferred:
        # A consumer-owned selection must never silently become another SMC
        # or technical zone.  An unusable selected zone means no plan.
        return None

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
    entry_zone_id = zone.get("zone_id")
    entry_zone_quality_score = zone.get(
        "zone_quality_score",
        entry_zone_score,
    )
    entry_zone_relevance_score = zone.get("zone_relevance_score")
    entry_zone_setup_score = zone.get(
        "zone_setup_score",
        entry_zone_score,
    )
    entry_zone_source = zone.get("source", "technical")
    source_zone = build_source_zone_diagnostics(zone, atr_value, side)
    effective_zone_score = (
        source_zone.get("effective_zone_score")
        if isinstance(source_zone, dict)
        else None
    )
    execution_zone_quality, execution_zone_width_atr_target = (
        _execution_zone_width_atr(effective_zone_score)
    )
    is_smc_zone = entry_zone_source in ("smc", "smc_selected")
    zone_low = zone.get("low")
    zone_high = zone.get("high")
    # Phase 16D: proximal execution sub-zone contained by the source zone.
    if zone_low is not None and zone_high is not None and zone_high > zone_low:
        execution_sub_zone = _build_execution_sub_zone(
            side=side,
            source_low=float(zone_low),
            source_high=float(zone_high),
            atr_value=atr_value,
            effective_score=effective_zone_score,
            price_digits=price_digits,
        )
        if execution_sub_zone is None:
            return None
        entry_low, entry_high = execution_sub_zone["entry_zone"]
        execution_zone_quality = execution_sub_zone["quality"]
        execution_zone_width_atr_target = execution_sub_zone[
            "width_atr_target"
        ]
    else:
        # Fallback: level ± half-width
        half_w = atr_value * risk_parameter(
            "entry_zone_half_width_atr", _ENTRY_ZONE_HALF_WIDTH_ATR
        )
        entry_low = round_price(level - half_w, price_digits)
        entry_high = round_price(level + half_w, price_digits)

    # Watch zone extends farther in trade direction
    watch_near = level - sign * atr_value * _WATCH_ZONE_OFFSET_ATR
    watch_far = level + sign * atr_value * watch_zone_atr_mult
    watch_low = min(watch_near, watch_far)
    watch_high = max(watch_near, watch_far)

    # --- Stop Loss ---
    sl_source = "atr"
    swing_sl = _find_nearest_swing_for_sl(smc, side, level)
    if swing_sl is not None:
        stop_loss = swing_sl - sign * atr_value * risk_parameter(
            "swing_sl_buffer_atr", _SWING_SL_BUFFER_ATR
        )
        if abs(level - stop_loss) < min_stop_distance:
            stop_loss = level - sign * min_stop_distance
        sl_source = "swing"
    elif use_preferred:
        sl_boundary = preferred_zone["low"] if side == "buy" else preferred_zone["high"]
        stop_loss = sl_boundary - sign * atr_value * risk_parameter(
            "zone_sl_buffer_atr", _ZONE_SL_BUFFER_ATR
        )
        if abs(level - stop_loss) < min_stop_distance:
            stop_loss = level - sign * min_stop_distance
        sl_source = "zone_boundary"
    elif side == "buy":
        stop_loss = _calc_stop_loss_buy(
            level, atr_value, sl_mult, min_stop_distance, zone,
            zone_score=effective_zone_score,
        )
    else:
        stop_loss = _calc_stop_loss_sell(
            level, atr_value, sl_mult, min_stop_distance, zone,
            zone_score=effective_zone_score,
        )
    if stop_loss is None:
        # High-quality zone sits too far away: its structural SL exceeds even
        # the relaxed cap.  Refuse the plan — placing the stop inside the zone
        # gets swept by normal oscillation while sizing inflates the lot
        # (doubly negative expectancy).
        return None

    # Guard: SL must be on the correct side of the entry zone
    sl_edge = (entry_low if side == "buy" else entry_high) - sign * atr_value * risk_parameter(
        "sl_floor_buffer_atr", _SL_FLOOR_BUFFER_ATR
    )
    if (stop_loss - sl_edge) * sign >= 0:
        stop_loss = sl_edge
    stop_loss = round_price(stop_loss, price_digits)

    # Entry price for DISPLAY (nearest edge = best-case RR shown to user)
    entry_for_rr = (
        entry_low + (entry_high - entry_low) * entry_aggressiveness
        if side == "buy" else
        entry_high + (entry_low - entry_high) * entry_aggressiveness
    )
    # Entry price for TP SELECTION (midpoint = conservative — TP must clear RR>=1
    # even when filled at zone center, not just the best edge)
    entry_for_selection = (
        entry_low + (entry_high - entry_low) * risk_parameter(
            "tp_selection_aggressiveness", _TP_SELECTION_AGGRESSIVENESS
        )
        if side == "buy" else
        entry_high + (entry_low - entry_high) * risk_parameter(
            "tp_selection_aggressiveness", _TP_SELECTION_AGGRESSIVENESS
        )
    )
    sel_risk_distance = abs(entry_for_selection - stop_loss)

    # Guard: skip plan if SL is too tight (relaxed for preferred/SMC zones)
    # Reference point: entry_for_rr (nearest edge, aggressiveness=0.0) — the
    # actual entry price used for position sizing. This is closer to SL than
    # entry_for_selection (midpoint), so the guard is stricter. A plan passing
    # this check guarantees adequate SL buffer at ALL fill prices within the zone.
    if use_preferred or is_smc_zone:
        _min_sl = atr_value * risk_parameter(
            "min_stop_distance_atr_mult", _MIN_STOP_DISTANCE_ATR_MULT
        )
    else:
        _min_sl = atr_value * risk_parameter(
            "min_sl_distance_atr", _MIN_SL_DISTANCE_ATR
        )
    rr_risk_distance = abs(entry_for_rr - stop_loss)
    if rr_risk_distance < _min_sl - 1e-10:
        return None

    # --- TP1 cascade: equal-level → S/R zones (iterated) → Fib → swing ---
    # Phase 13B: each candidate must pass quality validator.
    # Phase 13B.1: diagnostic tracking of rejection reasons.
    far_edge = entry_high if side == "buy" else entry_low
    tp1_source = "none"
    tp1 = None
    tp1_val_result: dict[str, Any] | None = None
    tp1_target_rank: int | None = None
    diag_candidates_checked = 0
    diag_rejected: dict[str, int] = {
        "invalid_candidate": 0,
        "wrong_direction": 0,
        "not_past_far_edge": 0,
        "clearance_too_low": 0,
        "nominal_rr_too_low": 0,
        "effective_rr_unavailable": 0,
        "effective_rr_too_low": 0,
        "equal_level_too_far": 0,
    }

    # ── 1. equal-level ──
    eq_tp = _find_nearest_equal_level(smc, side, entry_for_selection)
    if eq_tp is not None:
        eq_tp = _round_target_price(eq_tp, side, price_digits)
        if abs(eq_tp - entry_for_selection) > sel_risk_distance * risk_parameter(
            "eq_tp_max_rr", _EQ_TP_MAX_RR
        ):
            diag_rejected["equal_level_too_far"] += 1
        else:
            diag_candidates_checked += 1
            val = _validate_tp1_candidate(
                side=side, candidate=eq_tp,
                entry_for_selection=entry_for_selection, stop_loss=stop_loss,
                far_edge=far_edge, atr_value=atr_value, spread_price=spread_price,
            )
            if val["valid"]:
                tp1 = eq_tp
                tp1_source = "equal_level"
                tp1_val_result = val
            else:
                _count_rejection(diag_rejected, val["rejection_reason"])

    # ── 2. target zones (iterate nearest to farthest, using zone boundary) ──
    if tp1 is None:
        above = (side == "buy")
        sorted_zone_dicts = all_target_zones_sorted(
            target_zones, entry_for_selection, above=above,
            side=side, atr_value=atr_value, price_digits=price_digits,
        )
        for idx, z in enumerate(sorted_zone_dicts, start=1):
            cand = _target_price_from_zone(
                z,
                side,
                atr_value,
                price_digits,
            )
            if cand is None:
                continue
            diag_candidates_checked += 1
            val = _validate_tp1_candidate(
                side=side, candidate=cand,
                entry_for_selection=entry_for_selection, stop_loss=stop_loss,
                far_edge=far_edge, atr_value=atr_value, spread_price=spread_price,
            )
            if val["valid"]:
                tp1 = cand
                tp1_source = "target_zone"
                tp1_val_result = val
                tp1_target_rank = idx
                break
            else:
                _count_rejection(diag_rejected, val["rejection_reason"])

    # ── 3. fib extension ──
    if tp1 is None and regime_primary != "range":
        fib_tp = _fib_extension_target(
            smc,
            side,
            atr_value,
            _FIB_TP1,
            price_digits,
        )
        if fib_tp is not None:
            diag_candidates_checked += 1
            val = _validate_tp1_candidate(
                side=side, candidate=fib_tp,
                entry_for_selection=entry_for_selection, stop_loss=stop_loss,
                far_edge=far_edge, atr_value=atr_value, spread_price=spread_price,
            )
            if val["valid"]:
                tp1 = fib_tp
                tp1_source = "fib_extension"
                tp1_val_result = val
            else:
                _count_rejection(diag_rejected, val["rejection_reason"])

    # ── 4. swing ──
    if tp1 is None:
        sw_tp = _find_nearest_swing_for_tp(smc, side, entry_for_selection, sel_risk_distance)
        if sw_tp is not None:
            sw_tp = _round_target_price(sw_tp, side, price_digits)
            diag_candidates_checked += 1
            val = _validate_tp1_candidate(
                side=side, candidate=sw_tp,
                entry_for_selection=entry_for_selection, stop_loss=stop_loss,
                far_edge=far_edge, atr_value=atr_value, spread_price=spread_price,
            )
            if val["valid"]:
                tp1 = sw_tp
                tp1_source = "swing"
                tp1_val_result = val
            else:
                _count_rejection(diag_rejected, val["rejection_reason"])

    if tp1 is None:
        if use_preferred or is_smc_zone:
            tp1_source = "none"
            tp2 = None
        else:
            return None

    # --- TP2: next S/R zone, fallback to Fib 0.618 ---
    tp2 = None
    if tp1 is not None:
        tp2 = next_target(target_zones, tp1, above=(side == "buy"))
        if tp2 is None:
            if regime_primary != "range":
                tp2 = _fib_extension_target(
                    smc,
                    side,
                    atr_value,
                    _FIB_TP2,
                    price_digits,
                )
        if tp2 is not None:
            tp2 = _round_target_price(tp2, side, price_digits)
        # Guard: TP2 must be on the correct side of TP1 (farther target)
        if tp2 is not None and (tp2 - tp1) * sign <= 0:
            tp2 = None
        # Guard: TP2 must be strictly past the far edge of the entry zone
        if tp2 is not None and (tp2 - far_edge) * sign <= 0:
            tp2 = None
        # Guard: TP2 must be at least _TP2_MIN_GAP_ATR * ATR away from TP1
        if tp2 is not None and abs(tp2 - tp1) < atr_value * risk_parameter(
            "tp2_min_gap_atr", _TP2_MIN_GAP_ATR
        ):
            tp2 = None

    # --- Condition & Invalidation ---
    if side == "buy":
        condition = _build_buy_condition(h4_smc)
        invalidation = _build_buy_invalidation(stop_loss, h4_smc)
    else:
        condition = _build_sell_condition(h4_smc)
        invalidation = _build_sell_invalidation(stop_loss, h4_smc)

    structural_execution_zone = [
        round_price(entry_low, price_digits),
        round_price(entry_high, price_digits),
    ]
    rr_trim_diagnostics = _trim_execution_zone_for_effective_rr(
        side=side,
        structural_zone=structural_execution_zone,
        stop_loss=stop_loss,
        take_profit=tp1,
        spread_price=spread_price,
        min_effective_rr=_EXECUTION_ZONE_MIN_EFFECTIVE_RR,
        tolerance=_EXECUTION_ZONE_RR_TOLERANCE,
        price_digits=price_digits,
    )
    watch_zone = [
        round_price(watch_low, price_digits),
        round_price(watch_high, price_digits),
    ]
    final_zone = rr_trim_diagnostics.get("final_zone")
    if not isinstance(final_zone, list) or len(final_zone) != 2:
        reason = (
            "Execution zone không còn mức giá đạt effective R:R "
            f"{_EXECUTION_ZONE_MIN_EFFECTIVE_RR:.2f} với TP1 đã chọn."
        )
        return {
            "entry_zone": None,
            "execution_zone": None,
            "structural_execution_zone": structural_execution_zone,
            "rr_valid_zone": None,
            "rr_trimmed": False,
            "rr_trim_diagnostics": rr_trim_diagnostics,
            "execution_zone_quality": execution_zone_quality,
            "execution_zone_width_atr_target": execution_zone_width_atr_target,
            "price_digits": price_digits,
            "entry_price": None,
            "watch_zone": watch_zone,
            "stop_loss": round_price(stop_loss, price_digits),
            "take_profit": [
                round_price(value, price_digits)
                for value in (tp1, tp2)
                if value is not None
            ],
            "risk_reward": None,
            "risk_reward_base": None,
            "risk_reward_worst": None,
            "expected_effective_rr": None,
            "expected_effective_rr_base": None,
            "expected_effective_rr_worst": None,
            "risk_reward_range": {"best": None, "base": None, "worst": None},
            "risk_reward_effective_range": {
                "best": None,
                "base": None,
                "worst": None,
            },
            "condition": condition,
            "invalidation": invalidation,
            "position_sizing": {
                "account_balance": request.account_balance,
                "risk_pct": request.risk_percent,
                "risk_amount_usd": 0.0,
                "entry_price": None,
                "stop_loss": round_price(stop_loss, price_digits),
                "price_distance": None,
                "contract_size": contract_size_for(request),
                "suggested_lot": 0.0,
                "size_multiplier": 0.0,
            },
            "correlation_warnings": [],
            "correlation_context": None,
            "entry_zone_score": entry_zone_score,
            "entry_zone_source": entry_zone_source,
            "source_zone": source_zone,
            "sl_source": sl_source,
            "tp_source": tp1_source,
            "entry_ladder": {},
            "sub_zone": None,
            "entry_zone_width": None,
            "entry_zone_width_atr": None,
            "tp1_source": tp1_source,
            "tp1_clearance_from_far_edge": None,
            "tp1_clearance_atr": None,
            "tp1_effective_rr_base": None,
            "tp1_selection_diagnostics": {
                "candidates_checked": diag_candidates_checked,
                "rejected_by_reason": diag_rejected,
                "selected_source": tp1_source if tp1 is not None else None,
                "selected_target_rank": tp1_target_rank,
            },
            "alternate_zones": [
                {
                    "level": round_price(z["level"], price_digits),
                    "zone_score": z.get("zone_score", z.get("_effective_score")),
                    "source": z.get("source", "technical"),
                }
                for z in alternate_zones_raw
            ],
            "entry_status": "watch_zone",
            "ready_to_trade": False,
            "invalid_reason": reason,
            "reason_codes": [],
            "warning_codes": [EXECUTION_ZONE_RR_EMPTY],
            "block_codes": [],
        }

    entry_low, entry_high = float(final_zone[0]), float(final_zone[1])
    entry_zone = [entry_low, entry_high]
    entry_for_rr = (
        entry_low + (entry_high - entry_low) * entry_aggressiveness
        if side == "buy"
        else entry_high + (entry_low - entry_high) * entry_aggressiveness
    )
    entry_for_selection = (
        entry_low + (entry_high - entry_low) * risk_parameter(
            "tp_selection_aggressiveness", _TP_SELECTION_AGGRESSIVENESS
        )
        if side == "buy"
        else entry_high + (entry_low - entry_high) * risk_parameter(
            "tp_selection_aggressiveness", _TP_SELECTION_AGGRESSIVENESS
        )
    )
    entry_state = evaluate_entry(
        side=side,
        technical=technical,
        smc=smc,
        h1_candles=h1_candles or [],
        entry_zone=entry_zone,
        m15_candles=m15_candles,
        is_backtest=is_backtest,
    )
    if use_preferred and preferred_zone.get("watch_only_fallback"):
        entry_state = dict(entry_state)
        # Never upgrade an already-worse state (e.g. broken zone).
        if entry_state.get("entry_status") not in ("invalidated", "no_setup"):
            entry_state["entry_status"] = "watch_zone"
        entry_state["ready_to_trade"] = False
        fallback_reason = str(
            preferred_zone.get("selection_reason")
            or "effective_zone_fallback"
        )
        current_reason = str(entry_state.get("invalid_reason") or "").strip()
        entry_state["invalid_reason"] = (
            f"{current_reason} | Zone fallback: {fallback_reason}"
            if current_reason
            else f"Zone fallback: {fallback_reason}"
        )
    if tp1 is None:
        # SMC/preferred plan with no valid TP1: keep it visible for manual
        # monitoring but never tradeable.  Without this downgrade the decision
        # engine (entry_status + score only, no TP check) could judge
        # READY_TO_TRADE while the readiness engine blocks on
        # TAKE_PROFIT_MISSING — two contradictory verdicts for one plan, and
        # a manual trader would enter with no defined exit.
        entry_state = dict(entry_state)
        # Never upgrade an already-worse state (broken zone → STAND_ASIDE
        # must not become WATCH_ONLY); ready_to_trade and the reason still
        # apply to every TP-less plan.
        if entry_state.get("entry_status") not in ("invalidated", "no_setup"):
            entry_state["entry_status"] = "watch_zone"
        entry_state["ready_to_trade"] = False
        current_reason = str(entry_state.get("invalid_reason") or "").strip()
        entry_state["invalid_reason"] = (
            f"{current_reason} | Không có TP1 cấu trúc — chỉ theo dõi, chưa phải lệnh giao dịch."
            if current_reason
            else "Không có TP1 cấu trúc — chỉ theo dõi, chưa phải lệnh giao dịch."
        )
    # Entry Ladder Phase 1: scale size by price position within zone
    entry_ladder = entry_state.get("entry_ladder", {})
    size_multiplier = float(entry_ladder.get("size_multiplier", 1.0)) if isinstance(entry_ladder, dict) else 1.0
    # Conservative sizing anchor: the far edge of the execution zone (worst
    # fill, aggressiveness=1.0).  Sizing at the nearest edge (smallest risk
    # distance -> biggest lot) would exceed the risk budget whenever the fill
    # lands anywhere deeper in the zone.  Worst-edge sizing keeps real money
    # risk at or below the configured percent for EVERY fill inside the zone;
    # the price is only a slightly smaller lot.
    entry_worst = entry_high if side == "buy" else entry_low
    sizing = position_sizing(
        request, entry_worst, stop_loss,
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
        rr_best = round(reward_risk(entry_for_rr, stop_loss, tp1), 1)
        rr_base = round(reward_risk(entry_for_selection, stop_loss, tp1), 1)
        rr_worst = round(reward_risk(entry_worst, stop_loss, tp1), 1)
        risk_reward_str = f"1:{rr_best:.1f}"
        effective_rr = calculate_expected_effective_rr(
            direction=side,
            entry=entry_for_rr,
            stop_loss=stop_loss,
            take_profit=tp1,
            spread_price=spread_price,
        )
        effective_rr_base = calculate_expected_effective_rr(
            direction=side,
            entry=entry_for_selection,
            stop_loss=stop_loss,
            take_profit=tp1,
            spread_price=spread_price,
        )
        effective_rr_worst = calculate_expected_effective_rr(
            direction=side,
            entry=entry_worst,
            stop_loss=stop_loss,
            take_profit=tp1,
            spread_price=spread_price,
        )
        effective_rr_range = {
            "best": effective_rr,
            "base": effective_rr_base,
            "worst": effective_rr_worst,
        }
        # RR range across 3 fill positions within entry zone
        #   best  = mép gần nhất (aggressiveness 0.0) — same as risk_reward_str
        #   base  = trung điểm (aggressiveness 0.5)
        #   worst = mép xa nhất (aggressiveness 1.0)
        # All values are estimates, not verified against historical fill data.
        rr_range = {
            "best": rr_best,
            "base": rr_base,
            "worst": rr_worst,
        }
    else:
        risk_reward_str = None
        effective_rr = None
        rr_base = None
        rr_worst = None
        effective_rr_base = None
        effective_rr_worst = None
        rr_range = {"best": None, "base": None, "worst": None}
        effective_rr_range = {"best": None, "base": None, "worst": None}

    # Phase 13A: entry zone & TP1 quality diagnostics
    ez_width = (
        round_price(entry_high - entry_low, price_digits)
        if entry_high > entry_low
        else 0.0
    )
    ez_width_atr = round(ez_width / atr_value, 4) if atr_value > 0 else None
    if tp1 is not None:
        # Directional clearance: positive if TP1 is past the far edge
        if side == "buy":
            raw_clearance = tp1 - entry_high
        else:
            raw_clearance = entry_low - tp1
        if raw_clearance >= 0:
            tp1_clearance = round_price(raw_clearance, price_digits)
            tp1_clearance_atr = round(tp1_clearance / atr_value, 4) if atr_value > 0 else None
        else:
            tp1_clearance = None
            tp1_clearance_atr = None
        tp1_eff_rr_base = effective_rr_base
    else:
        tp1_clearance = None
        tp1_clearance_atr = None
        tp1_eff_rr_base = None

    return {
        "entry_zone": entry_zone,
        "execution_zone": entry_zone,
        "structural_execution_zone": structural_execution_zone,
        "rr_valid_zone": entry_zone if tp1 is not None else None,
        "rr_trimmed": bool(rr_trim_diagnostics.get("trimmed")),
        "rr_trim_diagnostics": rr_trim_diagnostics,
        "execution_zone_quality": execution_zone_quality,
        "execution_zone_width_atr_target": execution_zone_width_atr_target,
        "price_digits": price_digits,
        "entry_price": round_price(entry_for_rr, price_digits),
        "watch_zone": watch_zone,
        "stop_loss": round_price(stop_loss, price_digits),
        "take_profit": [
            round_price(value, price_digits)
            for value in (tp1, tp2)
            if value is not None
        ],
        "risk_reward": risk_reward_str,
        "risk_reward_base": rr_base,
        "risk_reward_worst": rr_worst,
        "expected_effective_rr": effective_rr,
        "expected_effective_rr_base": effective_rr_base,
        "expected_effective_rr_worst": effective_rr_worst,
        "risk_reward_range": rr_range,
        "risk_reward_effective_range": effective_rr_range,
        "condition": condition,
        "invalidation": invalidation,
        "position_sizing": sizing,
        "correlation_warnings": corr_warnings,
        "correlation_context": corr_context,
        "entry_zone_score": entry_zone_score,
        "entry_zone_id": entry_zone_id,
        "entry_zone_quality_score": entry_zone_quality_score,
        "entry_zone_relevance_score": entry_zone_relevance_score,
        "entry_zone_setup_score": entry_zone_setup_score,
        "entry_zone_scoring_version": zone.get("scoring_version"),
        "smc_score_breakdown": (
            dict(zone.get("smc_score_breakdown"))
            if isinstance(zone.get("smc_score_breakdown"), dict)
            else {}
        ),
        "entry_zone_liquidity_sweep_linked": bool(
            zone.get("liquidity_sweep_linked")
        ),
        "entry_zone_linked_sweep_id": zone.get("linked_sweep_id"),
        "entry_zone_linked_sweep_distance_atr": zone.get(
            "linked_sweep_distance_atr"
        ),
        "entry_zone_linked_sweep_time_delta": zone.get(
            "linked_sweep_time_delta"
        ),
        "entry_zone_source": entry_zone_source,
        "source_zone": source_zone,
        "sl_source": sl_source,
        "tp_source": tp1_source,
        "entry_ladder": entry_ladder,
        "sub_zone": entry_ladder.get("sub_zone") if isinstance(entry_ladder, dict) else None,
        # Phase 13A: entry zone & TP1 quality diagnostics
        "entry_zone_width": ez_width,
        "entry_zone_width_atr": ez_width_atr,
        "tp1_source": tp1_source,
        "tp1_clearance_from_far_edge": tp1_clearance,
        "tp1_clearance_atr": tp1_clearance_atr,
        "tp1_effective_rr_base": tp1_eff_rr_base,
        # Phase 13B.1: TP1 selection diagnostic summary
        "tp1_selection_diagnostics": {
            "candidates_checked": diag_candidates_checked,
            "rejected_by_reason": diag_rejected,
            "selected_source": tp1_source if tp1 is not None else None,
            "selected_target_rank": tp1_target_rank,
        },
        "alternate_zones": [
            {
                "level": round_price(z["level"]),
                "zone_id": z.get("zone_id"),
                "zone_score": z.get("zone_score", z.get("_effective_score")),
                "zone_quality_score": z.get("zone_quality_score"),
                "zone_relevance_score": z.get("zone_relevance_score"),
                "zone_setup_score": z.get("zone_setup_score"),
                "liquidity_sweep_linked": bool(
                    z.get("liquidity_sweep_linked")
                ),
                "linked_sweep_id": z.get("linked_sweep_id"),
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
                "zone_id": zone.get("zone_id"),
                "symbol": zone.get("symbol"),
                "timeframe": zone.get("timeframe"),
                "family": zone.get("family"),
                "direction": zone.get("direction"),
                "strength": zone.get("strength", "moderate"),
                "confluence_count": zone.get("confluence_count", 1),
                "consolidation_bars": zone.get("consolidation_bars", 0),
                "zone_score": zone.get("zone_score", 50),
                "zone_quality_score": zone.get(
                    "zone_quality_score",
                    zone.get("zone_score", 50),
                ),
                "zone_relevance_score": zone.get("zone_relevance_score"),
                "zone_setup_score": zone.get(
                    "zone_setup_score",
                    zone.get("zone_score", 50),
                ),
                "scoring_version": zone.get("scoring_version"),
                "domain_version": zone.get("domain_version"),
                "freshness_bars": zone.get("freshness_bars"),
                "stale": zone.get("stale"),
                "mitigated": zone.get("mitigated", False),
                "broken": zone.get("broken", False),
                "test_count": zone.get("test_count", 0),
                "displacement_multiple": zone.get("displacement_multiple", 0),
                "liquidity_sweep": zone.get("liquidity_sweep", False),
                "liquidity_sweep_linked": bool(
                    zone.get("liquidity_sweep_linked")
                ),
                "linked_sweep_id": zone.get("linked_sweep_id"),
                "linked_sweep_distance_atr": zone.get(
                    "linked_sweep_distance_atr"
                ),
                "linked_sweep_time_delta": zone.get(
                    "linked_sweep_time_delta"
                ),
                "sweep_link_version": zone.get("sweep_link_version"),
                "zone_location": zone.get("zone_location", "unknown"),
                "source": "smc",
            }
        )
    return converted


def build_source_zone_diagnostics(
    zone: dict[str, Any] | None,
    atr_value: float | int | None,
    side: str | None = None,
) -> dict[str, Any] | None:
    """Return additive metadata for the structural zone behind an entry zone."""
    if not isinstance(zone, dict):
        return None

    low = zone.get("low")
    high = zone.get("high")
    original_low = round_price(float(low)) if isinstance(low, (int, float)) else None
    original_high = round_price(float(high)) if isinstance(high, (int, float)) else None
    original_width = None
    original_width_atr = None
    if (
        original_low is not None
        and original_high is not None
        and original_high > original_low
    ):
        original_width = round_price(original_high - original_low)
        if isinstance(atr_value, (int, float)) and float(atr_value) > 0:
            original_width_atr = round(original_width / float(atr_value), 4)

    effective_score = calculate_effective_zone_score(
        zone,
        str(side or ""),
        atr_value,
    )
    return {
        "zone_type": zone.get("zone_type") or zone.get("type"),
        "source": zone.get("source", "technical"),
        "zone_score": zone.get("zone_score"),
        **effective_score,
        "selection_status": zone.get("selection_status"),
        "selection_reason": zone.get("selection_reason"),
        "watch_only_fallback": zone.get("watch_only_fallback"),
        "selection_distance": zone.get("selection_distance"),
        "strength": zone.get("strength"),
        "stale": zone.get("stale"),
        "mitigated": zone.get("mitigated"),
        "broken": zone.get("broken"),
        "test_count": zone.get("test_count"),
        "freshness_bars": zone.get("freshness_bars"),
        "displacement_multiple": zone.get("displacement_multiple"),
        "liquidity_sweep": zone.get("liquidity_sweep"),
        "zone_location": zone.get("zone_location"),
        "original_low": original_low,
        "original_high": original_high,
        "original_width": original_width,
        "original_width_atr": original_width_atr,
    }


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


def all_targets_sorted(
    zones: list[dict[str, Any]], reference: float, *, above: bool,
) -> list[float]:
    """Return all target levels sorted by distance from *reference*.

    Deduplicates equal levels.  Skips non-finite values.
    """
    levels: set[float] = set()
    for zone in zones:
        lv = zone.get("level") if isinstance(zone, dict) else None
        if not isinstance(lv, (int, float)):
            continue
        f = float(lv)
        if f == f and f != float("inf") and f != float("-inf"):
            levels.add(f)
    if not levels:
        return []
    if above:
        return sorted([l for l in levels if l > reference])
    return sorted([l for l in levels if l < reference], reverse=True)


# ---------------------------------------------------------------------------
# Phase 13C: target zone boundary-based TP1
# ---------------------------------------------------------------------------


def _target_price_from_zone(
    zone: dict[str, Any],
    side: str,
    atr_value: float,
    price_digits: int = 5,
) -> float | None:
    """Compute TP1 price from a zone's boundary with a small buffer.

    BUY (resistance zone): target = zone.low - buffer, fallback zone.level.
    SELL (support zone):    target = zone.high + buffer, fallback zone.level.
    Returns None if zone has no valid level at all.
    """
    buffer = atr_value * _TP_TARGET_BUFFER_ATR
    if side == "buy":
        low = zone.get("low") if isinstance(zone, dict) else None
        if isinstance(low, (int, float)) and low == low and low != float("inf"):
            return _round_target_price(
                float(low) - buffer,
                side,
                price_digits,
            )
    else:
        high = zone.get("high") if isinstance(zone, dict) else None
        if isinstance(high, (int, float)) and high == high and high != float("inf"):
            return _round_target_price(
                float(high) + buffer,
                side,
                price_digits,
            )
    # Fallback: zone level
    lv = zone.get("level") if isinstance(zone, dict) else None
    if isinstance(lv, (int, float)) and lv == lv and lv != float("inf"):
        return _round_target_price(float(lv), side, price_digits)
    return None


def all_target_zones_sorted(
    zones: list[dict[str, Any]], reference: float, *,
    above: bool,
    side: str = "buy",
    atr_value: float = 0.0,
    price_digits: int = 5,
) -> list[dict[str, Any]]:
    """Return zone dicts sorted by executable TP price (boundary ± buffer).

    Phase 13C: sorts by ``_target_price_from_zone`` output, not zone["level"].
    Deduplicates by executable TP.  Skips zones without valid executable TP.
    """
    seen: set[float] = set()
    result: list[dict[str, Any]] = []
    for z in zones:
        if not isinstance(z, dict):
            continue
        tp = _target_price_from_zone(
            z,
            side,
            atr_value,
            price_digits,
        )
        if tp is None:
            continue
        if tp != tp or tp == float("inf") or tp == float("-inf"):
            continue
        if tp in seen:
            continue
        seen.add(tp)
        if (above and tp > reference) or (not above and tp < reference):
            result.append((tp, z))
    # Sort by executable TP
    if above:
        result.sort(key=lambda item: item[0])
    else:
        result.sort(key=lambda item: item[0], reverse=True)
    return [z for _, z in result]


# ---------------------------------------------------------------------------
# Phase 13B: TP1 quality validator (shared by all TP1 sources)
# ---------------------------------------------------------------------------


def _validate_tp1_candidate(
    *,
    side: str,
    candidate: float,
    entry_for_selection: float,
    stop_loss: float,
    far_edge: float,
    atr_value: float,
    spread_price: float = 0.0,
) -> dict[str, Any]:
    """Validate a TP1 candidate against Phase 13B quality floors.

    Returns a dict with ``valid``, ``nominal_base_rr``,
    ``effective_base_rr``, ``clearance``, ``rejection_reason``.
    Never raises.
    """
    result: dict[str, Any] = {
        "valid": False,
        "nominal_base_rr": None,
        "effective_base_rr": None,
        "clearance": None,
        "rejection_reason": "",
    }

    try:
        cand = float(candidate)
    except (TypeError, ValueError):
        result["rejection_reason"] = "non_finite_candidate"
        return result
    if cand != cand or cand == float("inf") or cand == float("-inf") or cand <= 0:
        result["rejection_reason"] = "non_finite_candidate"
        return result

    # Directional check
    if side == "buy" and cand <= entry_for_selection:
        result["rejection_reason"] = "wrong_direction"
        return result
    if side == "sell" and cand >= entry_for_selection:
        result["rejection_reason"] = "wrong_direction"
        return result

    # Far edge check (directional clearance)
    if side == "buy":
        clearance = round(cand - far_edge, 5)
    else:
        clearance = round(far_edge - cand, 5)
    if clearance < 0:
        result["rejection_reason"] = "not_past_far_edge"
        return result

    result["clearance"] = clearance

    # Clearance floor
    if atr_value > 0 and clearance < _TP1_MIN_CLEARANCE_ATR * atr_value - 1e-10:
        result["rejection_reason"] = "clearance_below_min"
        return result

    # Nominal base RR (midpoint anchor)
    risk_dist = abs(entry_for_selection - stop_loss)
    if risk_dist <= 0:
        result["rejection_reason"] = "zero_risk_distance"
        return result
    nominal_base_rr = round(abs(cand - entry_for_selection) / risk_dist, 4)
    result["nominal_base_rr"] = nominal_base_rr
    if nominal_base_rr < 1.0 - 1e-10:
        result["rejection_reason"] = "nominal_rr_below_1.0"
        return result

    # Effective base RR (spread-adjusted)
    effective_base_rr = calculate_expected_effective_rr(
        direction=side,
        entry=entry_for_selection,
        stop_loss=stop_loss,
        take_profit=cand,
        spread_price=spread_price,
    )
    result["effective_base_rr"] = effective_base_rr
    if effective_base_rr is None or effective_base_rr <= 0:
        result["rejection_reason"] = "effective_rr_invalid"
        return result
    if effective_base_rr < _TP1_MIN_EFFECTIVE_RR_BASE - 1e-10:
        result["rejection_reason"] = "effective_rr_below_min"
        return result

    result["valid"] = True
    result["rejection_reason"] = ""
    return result


def _count_rejection(bucket: dict[str, int], reason: str) -> None:
    """Map a validator rejection_reason to the diagnostic counter bucket."""
    mapping = {
        "non_finite_candidate": "invalid_candidate",
        "wrong_direction": "wrong_direction",
        "not_past_far_edge": "not_past_far_edge",
        "clearance_below_min": "clearance_too_low",
        "zero_risk_distance": "invalid_candidate",
        "nominal_rr_below_1.0": "nominal_rr_too_low",
        "effective_rr_invalid": "effective_rr_unavailable",
        "effective_rr_below_min": "effective_rr_too_low",
    }
    key = mapping.get(reason, "invalid_candidate")
    bucket[key] += 1


class QuoteRateProvider(Protocol):
    """Boundary contract for quote-currency conversion outside the risk core."""

    def quote_to_usd_rate(self, quote_currency: str) -> float | None:
        ...


def position_sizing(
    request: AnalysisInput,
    entry_price: float,
    stop_loss: float,
    *,
    quote_to_usd_rate: float | None = None,
    quote_rate_provider: QuoteRateProvider | None = None,
    size_multiplier: float = 1.0,
) -> dict[str, Any]:
    price_digits = _price_digits_for_request(request)
    contract_size = contract_size_for(request)
    risk_amount = request.account_balance * request.risk_percent / 100 * size_multiplier
    price_distance = abs(entry_price - stop_loss)
    loss_per_lot = price_distance * contract_size
    if quote_to_usd_rate is None:
        quote_to_usd_rate = _resolve_quote_to_usd_rate(
            request.symbol,
            provider=quote_rate_provider,
        )
    if quote_to_usd_rate is not None and quote_to_usd_rate > 0:
        loss_per_lot = loss_per_lot * quote_to_usd_rate
    raw_lot = risk_amount / loss_per_lot if loss_per_lot else 0.0
    lot = round_lot(raw_lot, request.lot_step, request.minimum_lot)
    return {
        "account_balance": request.account_balance,
        "risk_pct": request.risk_percent,
        "risk_amount_usd": risk_amount,
        "entry_price": round_price(entry_price, price_digits),
        "stop_loss": round_price(stop_loss, price_digits),
        "price_distance": round_price(price_distance, price_digits),
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


def _resolve_quote_to_usd_rate(
    symbol: str,
    *,
    provider: QuoteRateProvider | None = None,
) -> float | None:
    """Resolve a quote-currency rate through an injected provider only."""
    if "/" not in symbol:
        return None
    quote = symbol.split("/")[-1]
    if quote == "USD":
        return 1.0
    if provider is None:
        return None
    try:
        return provider.quote_to_usd_rate(quote)
    except Exception:
        return None


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


def round_price(value: float, digits: int = 5) -> float:
    return round(value, digits)


def round_price_up(value: float, digits: int = 5) -> float:
    quantum = Decimal(1).scaleb(-digits)
    return float(
        Decimal(str(value)).quantize(quantum, rounding=ROUND_CEILING)
    )


def round_price_down(value: float, digits: int = 5) -> float:
    quantum = Decimal(1).scaleb(-digits)
    return float(
        Decimal(str(value)).quantize(quantum, rounding=ROUND_FLOOR)
    )


def _round_target_price(value: float, side: str, digits: int) -> float:
    return round_price(value, digits)


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


# ---------------------------------------------------------------------------
# Phase 5A: Current-price effective R:R (diagnostic only — does NOT block orders)
# ---------------------------------------------------------------------------


def calculate_current_effective_rr(
    direction: str,
    current_price: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    *,
    spread_price: float | int | str | None = 0.0,
    entry_zone: list[float] | None = None,
) -> dict[str, Any]:
    """Compute effective R:R using *current_price* instead of a zone anchor.

    This is a **diagnostic helper** for Phase 5A.  It does NOT change any
    trade-decision logic.  Callers use the returned dict to display or log
    the current-price RR alongside best/base/worst for comparison.

    Returns
    -------
    dict
        {
            "current_effective_rr": float | None,
            "current_rr_source": str,        # "current_price" | fallback reason
            "price_in_entry_zone": bool | None,
        }
    """
    result: dict[str, Any] = {
        "current_effective_rr": None,
        "current_rr_source": "no_current_price",
        "price_in_entry_zone": None,
    }

    # --- Guard: required inputs ---
    try:
        cp = float(current_price) if current_price is not None else None
        sl = float(stop_loss) if stop_loss is not None else None
        tp = float(take_profit) if take_profit is not None else None
    except (TypeError, ValueError):
        return result

    if cp is None or cp <= 0:
        result["current_rr_source"] = "no_current_price"
        return result
    if sl is None or sl <= 0:
        result["current_rr_source"] = "no_stop_loss"
        return result
    if tp is None or tp <= 0:
        result["current_rr_source"] = "no_take_profit"
        return result

    direction = str(direction).lower()
    if direction not in ("buy", "sell"):
        result["current_rr_source"] = "invalid_direction"
        return result

    # --- Price-in-zone check ---
    if isinstance(entry_zone, list) and len(entry_zone) >= 2:
        try:
            zone_low = float(entry_zone[0])
            zone_high = float(entry_zone[1])
        except (TypeError, ValueError):
            zone_low = zone_high = 0.0
        if zone_low > 0 and zone_high > 0 and zone_high > zone_low:
            result["price_in_entry_zone"] = zone_low <= cp <= zone_high
        else:
            result["price_in_entry_zone"] = None
    else:
        result["price_in_entry_zone"] = None

    # --- Compute effective RR at current price ---
    # Guard: price must be on correct side of SL
    if direction == "buy" and cp <= sl:
        result["current_rr_source"] = "price_behind_sl"
        return result
    if direction == "sell" and cp >= sl:
        result["current_rr_source"] = "price_behind_sl"
        return result

    rr = calculate_expected_effective_rr(
        direction=direction,
        entry=cp,
        stop_loss=sl,
        take_profit=tp,
        spread_price=spread_price,
    )

    if rr is not None and rr > 0:
        result["current_effective_rr"] = rr
        result["current_rr_source"] = "current_price"
    else:
        result["current_rr_source"] = "zero_or_invalid_rr"

    return result
