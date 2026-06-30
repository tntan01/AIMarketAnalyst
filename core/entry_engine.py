from __future__ import annotations

from typing import Any

from core.indicators import atr
from core.market_models import Candle
from core.reason_codes import (
    M15_DATA_UNAVAILABLE,
    M15_LOOSE_CONFIRMATION,
    M15_NOT_CONFIRMED,
    M15_STRICT_CONFIRMED,
    ZONE_BROKEN,
    append_code,
    normalize_codes,
)

_M15_QUALITY_LABELS = {
    "strict": "chặt (×1.0)",
    "loose": "lỏng (×0.85)",
    "none": "không đạt (×0.7)",
}

# Entry Ladder Phase 1: sub-zone size multipliers
_LADDER_SIZES = {"top": 0.4, "mid": 0.7, "bottom": 1.0}
_LADDER_LABELS = {
    "top": "Top zone (40% size, cần M15)",
    "mid": "Mid zone (70% size, cần H1+M15)",
    "bottom": "Bottom zone (100% size, cần H1+M15+sweep)",
}


def _classify_sub_zone(price: float, low: float, high: float, side: str) -> tuple[str | None, float]:
    """Classify price position within entry zone into top/mid/bottom sub-zone.

    Returns (sub_zone, depth_pct) where depth_pct is 0.0 at outer edge
    and 1.0 at deepest point.  Returns (None, 0.0) if zone is invalid.
    """
    zone_width = high - low
    if zone_width <= 0:
        return None, 0.0

    if side == "buy":
        # Price drops into support: 0% = entry_high (outer), 100% = entry_low (deepest)
        depth_pct = (high - price) / zone_width
    else:
        # Price rises into resistance: 0% = entry_low (outer), 100% = entry_high (deepest)
        depth_pct = (price - low) / zone_width

    depth_pct = max(0.0, min(1.0, depth_pct))

    if depth_pct <= 0.33:
        return "top", depth_pct
    elif depth_pct <= 0.66:
        return "mid", depth_pct
    else:
        return "bottom", depth_pct


def _find_swings_m15(candles: list[Candle], lookback: int = 5) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(lookback, len(candles) - lookback):
        window = candles[i - lookback : i + lookback + 1]
        c = candles[i]
        if c.high == max(x.high for x in window) and sum(1 for x in window if x.high == c.high) == 1:
            highs.append(c.high)
        if c.low == min(x.low for x in window) and sum(1 for x in window if x.low == c.low) == 1:
            lows.append(c.low)
    return highs, lows


def _confirm_m15_structure(candles: list[Candle], side: str) -> dict[str, Any]:
    if len(candles) < 12:
        return {"passed": False, "reason": "Không đủ nến M15 để đánh giá cấu trúc."}
    highs, lows = _find_swings_m15(candles)
    if side == "buy":
        if len(lows) >= 2 and lows[-1] > lows[-2]:
            return {"passed": True, "reason": "M15 higher low rõ"}
        return {"passed": False, "reason": "M15 chưa có higher low rõ"}
    else:
        if len(highs) >= 2 and highs[-1] < highs[-2]:
            return {"passed": True, "reason": "M15 lower high rõ"}
        return {"passed": False, "reason": "M15 chưa có lower high rõ"}


def _confirm_m15_displacement(candles: list[Candle], side: str, threshold_atr: float = 0.3) -> dict[str, Any]:
    if len(candles) < 15:
        return {"passed": False, "reason": "Không đủ nến M15 để đánh giá displacement."}
    highs_atr = [c.high for c in candles]
    lows_atr = [c.low for c in candles]
    closes = [c.close for c in candles]
    atr_values = atr(highs_atr, lows_atr, closes, 14)
    atr_now = atr_values[-1] if atr_values and atr_values[-1] is not None else 0.0
    if atr_now <= 0:
        return {"passed": False, "reason": "ATR M15 không xác định được."}
    threshold = threshold_atr * atr_now
    for candle in reversed(candles[-3:]):
        body = abs(candle.close - candle.open)
        if body < threshold:
            continue
        if side == "buy" and candle.close > candle.open:
            return {"passed": True, "reason": f"M15 displacement tăng (body={body:.5f} > {threshold:.5f})."}
        if side == "sell" and candle.close < candle.open:
            return {"passed": True, "reason": f"M15 displacement giảm (body={body:.5f} > {threshold:.5f})."}
    return {"passed": False, "reason": "M15 chưa có nến displacement đủ mạnh cùng hướng."}


def evaluate_entry(
    *,
    side: str,
    technical: dict[str, Any],
    smc: dict[str, Any],
    h1_candles: list[Candle],
    entry_zone: list[float],
    m15_candles: list[Candle] | None = None,
) -> dict[str, Any]:
    price = float(technical.get("price", 0.0))
    atr_value = float(technical.get("atr_h4") or technical.get("atr_d1") or 0.0)

    m15_available = m15_candles is not None and len(m15_candles) >= 10
    m15_quality = None

    if len(entry_zone) != 2 or price <= 0 or atr_value <= 0:
        reason = "Thiếu dữ liệu giá, ATR hoặc vùng vào lệnh."
        if not m15_available:
            reason += " | M15 data unavailable"
        return _result("no_setup", "none", 0, reason,
                       m15_available=m15_available)

    low, high = min(entry_zone), max(entry_zone)
    in_zone = low <= price <= high
    distance = _distance_to_zone(price, low, high)
    near_zone = distance <= atr_value * 0.5
    broken = price < low - atr_value * 0.25 if side == "buy" else price > high + atr_value * 0.25
    if broken:
        reason = "Giá đã phá vùng vào lệnh dự kiến."
        if not m15_available:
            reason += " | M15 data unavailable"
        return _result("invalidated", "zone_broken", 0, reason,
                       m15_available=m15_available,
                       warning_codes=[ZONE_BROKEN])

    candle_signal = _h1_confirmation(side, h1_candles)
    smc_signal = _smc_confirmation(side, smc)
    location_score = _location_score(side, smc)
    confirmation_score = 0
    confirmation_score += 25 if in_zone else 15 if near_zone else 0
    confirmation_score += candle_signal["score"]
    confirmation_score += smc_signal["score"]
    confirmation_score += location_score


    trigger_type = _first_trigger(candle_signal["trigger_type"], smc_signal["trigger_type"])

    # --- M15 confirmation layer ---
    m15_structure = None
    m15_displacement = None
    m15_score_multiplier = None
    if m15_available:
        m15_structure = _confirm_m15_structure(m15_candles, side)
        m15_displacement = _confirm_m15_displacement(m15_candles, side)
        struct_pass = m15_structure["passed"]
        disp_pass = m15_displacement["passed"]
        if struct_pass and disp_pass:
            m15_quality = "strict"
            m15_score_multiplier = 1.0
        elif struct_pass or disp_pass:
            m15_quality = "loose"
            m15_score_multiplier = 0.85
        else:
            m15_quality = "none"
            m15_score_multiplier = 0.7
        confirmation_score = int(confirmation_score * m15_score_multiplier)
    # ------------------------------

    # --- Phase 8 + Entry Ladder: sub-zone-aware entry decision ---
    trigger_valid = trigger_type != "none"
    score_passed = confirmation_score >= 70

    # Check for SMC liquidity sweep (used by bottom-zone requirement)
    has_sweep = False
    if side == "buy":
        sweeps = smc.get("H1", {}).get("liquidity_sweeps", {}) if isinstance(smc, dict) else {}
        has_sweep = bool(sweeps.get("swept_lows"))
    else:
        sweeps = smc.get("H1", {}).get("liquidity_sweeps", {}) if isinstance(smc, dict) else {}
        has_sweep = bool(sweeps.get("swept_highs"))

    # Without M15 data, fall back to legacy (can't classify sub-zone quality).
    if in_zone and trigger_valid and score_passed and not m15_available:
        return _result("waiting_confirmation", trigger_type, confirmation_score,
                       "Thiếu dữ liệu M15, không xác nhận entry.",
                       in_zone, False,
                       m15_structure=m15_structure, m15_displacement=m15_displacement,
                       m15_available=m15_available, m15_quality=m15_quality,
                       m15_score_multiplier=m15_score_multiplier,
                       warning_codes=[M15_DATA_UNAVAILABLE])

    if in_zone and trigger_valid and score_passed:
        sub_zone, depth_pct = _classify_sub_zone(price, low, high, side)
        entry_ladder = {
            "sub_zone": sub_zone,
            "depth_pct": round(depth_pct, 3),
            "size_multiplier": _LADDER_SIZES.get(sub_zone, 1.0),
            "label": _LADDER_LABELS.get(sub_zone, ""),
        }

        if sub_zone == "top":
            # Top zone: only need M15 (loose or strict), smallest size
            if m15_available and m15_quality in ("strict", "loose"):
                return _result("confirmed_entry", trigger_type, confirmation_score,
                               f"Top zone entry, size=40%. {_LADDER_LABELS['top']}",
                               in_zone, True,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               reason_codes=[M15_STRICT_CONFIRMED] if m15_quality == "strict" else [M15_LOOSE_CONFIRMATION],
                               entry_ladder=entry_ladder)
            else:
                entry_ladder["size_multiplier"] = 0.0
                return _result("waiting_confirmation", trigger_type, confirmation_score,
                               "Top zone — cần ít nhất M15 xác nhận lỏng.",
                               in_zone, False,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               warning_codes=[M15_NOT_CONFIRMED] if m15_quality == "none" else [M15_LOOSE_CONFIRMATION],
                               entry_ladder=entry_ladder)

        elif sub_zone == "mid":
            # Mid zone: need H1 trigger + M15 strict, medium size
            if m15_available and m15_quality == "strict":
                return _result("confirmed_entry", trigger_type, confirmation_score,
                               f"Mid zone entry, size=70%. {_LADDER_LABELS['mid']}",
                               in_zone, True,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               reason_codes=[M15_STRICT_CONFIRMED],
                               entry_ladder=entry_ladder)
            elif m15_available and m15_quality == "loose":
                entry_ladder["size_multiplier"] = 0.0
                return _result("waiting_confirmation", trigger_type, confirmation_score,
                               "Mid zone — M15 xác nhận lỏng, cần strict để vào lệnh.",
                               in_zone, False,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               warning_codes=[M15_LOOSE_CONFIRMATION],
                               entry_ladder=entry_ladder)
            else:
                entry_ladder["size_multiplier"] = 0.0
                return _result("watch_zone", trigger_type, confirmation_score,
                               "Mid zone — M15 chưa xác nhận.",
                               False, False,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               warning_codes=[M15_NOT_CONFIRMED],
                               entry_ladder=entry_ladder)

        elif sub_zone == "bottom":
            # Bottom zone: need H1 trigger + M15 strict + SMC sweep, full size
            if m15_available and m15_quality == "strict" and has_sweep:
                return _result("confirmed_entry", trigger_type, confirmation_score,
                               f"Bottom zone entry, size=100%. {_LADDER_LABELS['bottom']}",
                               in_zone, True,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               reason_codes=[M15_STRICT_CONFIRMED],
                               entry_ladder=entry_ladder)
            elif m15_available and m15_quality == "strict" and not has_sweep:
                # Bottom zone without sweep — degrade: treat like mid zone
                entry_ladder["size_multiplier"] = _LADDER_SIZES["mid"]
                entry_ladder["degraded"] = True
                return _result("confirmed_entry", trigger_type, confirmation_score,
                               "Bottom zone — thiếu SMC sweep, degrade xuống mid (70% size).",
                               in_zone, True,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               reason_codes=[M15_STRICT_CONFIRMED],
                               entry_ladder=entry_ladder)
            elif m15_available and m15_quality == "loose":
                entry_ladder["size_multiplier"] = 0.0
                return _result("waiting_confirmation", trigger_type, confirmation_score,
                               "Bottom zone — M15 xác nhận lỏng, cần strict + sweep.",
                               in_zone, False,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               warning_codes=[M15_LOOSE_CONFIRMATION],
                               entry_ladder=entry_ladder)
            else:
                entry_ladder["size_multiplier"] = 0.0
                return _result("watch_zone", trigger_type, confirmation_score,
                               "Bottom zone — M15 chưa xác nhận.",
                               False, False,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               warning_codes=[M15_NOT_CONFIRMED],
                               entry_ladder=entry_ladder)

        # Unknown sub-zone — fall through to legacy behavior
        if m15_available:
            if m15_quality == "strict":
                return _result("confirmed_entry", trigger_type, confirmation_score, "", in_zone, True,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               reason_codes=[M15_STRICT_CONFIRMED],
                               entry_ladder=entry_ladder)
            elif m15_quality == "loose":
                return _result("waiting_confirmation", trigger_type, confirmation_score,
                               "M15 xác nhận lỏng, chờ xác nhận chặt trước khi vào lệnh.",
                               in_zone, False,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               warning_codes=[M15_LOOSE_CONFIRMATION],
                               entry_ladder=entry_ladder)
            else:
                return _result("watch_zone", trigger_type, confirmation_score,
                               "M15 chưa xác nhận, chỉ theo dõi vùng giá.",
                               False, False,
                               m15_structure=m15_structure, m15_displacement=m15_displacement,
                               m15_available=m15_available, m15_quality=m15_quality,
                               m15_score_multiplier=m15_score_multiplier,
                               warning_codes=[M15_NOT_CONFIRMED],
                               entry_ladder=entry_ladder)
        else:
            return _result("waiting_confirmation", trigger_type, confirmation_score,
                           "Thiếu dữ liệu M15, không xác nhận entry.",
                           in_zone, False,
                           m15_structure=m15_structure, m15_displacement=m15_displacement,
                           m15_available=m15_available, m15_quality=m15_quality,
                           m15_score_multiplier=m15_score_multiplier,
                           warning_codes=[M15_DATA_UNAVAILABLE],
                           entry_ladder=entry_ladder)

    if in_zone:
        reason = "Giá đã vào vùng nhưng chưa đủ xác nhận H1/SMC."
        if not m15_available:
            reason += " | M15 data unavailable"
        elif m15_quality:
            reason += f" | M15: {_M15_QUALITY_LABELS.get(m15_quality, m15_quality)}"
        return _result(
            "waiting_confirmation",
            trigger_type,
            confirmation_score,
            reason,
            in_zone,
            False,
            m15_structure=m15_structure, m15_displacement=m15_displacement,
            m15_available=m15_available, m15_quality=m15_quality,
            m15_score_multiplier=m15_score_multiplier,
        )
    if near_zone:
        reason = "Giá đang gần vùng theo dõi, chưa vào đúng vùng."
        if not m15_available:
            reason += " | M15 data unavailable"
        elif m15_quality:
            reason += f" | M15: {_M15_QUALITY_LABELS.get(m15_quality, m15_quality)}"
        return _result(
            "watch_zone",
            trigger_type,
            confirmation_score,
            reason,
            False,
            False,
            m15_structure=m15_structure, m15_displacement=m15_displacement,
            m15_available=m15_available, m15_quality=m15_quality,
            m15_score_multiplier=m15_score_multiplier,
        )
    reason = "Giá còn xa vùng vào lệnh."
    if not m15_available:
        reason += " | M15 data unavailable"
    elif m15_quality:
        reason += f" | M15: {_M15_QUALITY_LABELS.get(m15_quality, m15_quality)}"
    return _result("watch_zone", "none", confirmation_score, reason, False, False,
                   m15_structure=m15_structure, m15_displacement=m15_displacement,
                   m15_available=m15_available, m15_quality=m15_quality,
                   m15_score_multiplier=m15_score_multiplier)


def _result(
    status: str,
    trigger_type: str,
    confirmation_score: int,
    invalid_reason: str,
    price_in_entry_zone: bool = False,
    h1_confirmation: bool = False,
    *,
    m15_available: bool = False,
    m15_structure: dict[str, Any] | None = None,
    m15_displacement: dict[str, Any] | None = None,
    m15_quality: str | None = None,
    m15_score_multiplier: float | None = None,
    reason_codes: list[str] | None = None,
    warning_codes: list[str] | None = None,
    block_codes: list[str] | None = None,
    entry_ladder: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "entry_status": status,
        "trigger_type": trigger_type,
        "confirmation_score": int(confirmation_score),
        "invalid_reason": invalid_reason,
        "price_in_entry_zone": price_in_entry_zone,
        "h1_confirmation": h1_confirmation,
        "ready_to_trade": status == "confirmed_entry",
        "m15_available": m15_available,
        "m15_checked": m15_structure is not None,
        "reason_codes": normalize_codes(reason_codes),
        "warning_codes": normalize_codes(warning_codes),
        "block_codes": normalize_codes(block_codes),
    }
    if entry_ladder is not None:
        result["entry_ladder"] = entry_ladder
    if m15_structure is not None:
        result["m15_structure"] = m15_structure
    if m15_displacement is not None:
        result["m15_displacement"] = m15_displacement
    if m15_structure is not None or m15_displacement is not None:
        m15_passed = (m15_structure and m15_structure.get("passed")) or (m15_displacement and m15_displacement.get("passed"))
        result["m15_confirmed"] = bool(m15_passed)
        result["m15_quality"] = m15_quality
        result["m15_score_multiplier"] = m15_score_multiplier
    return result


def _distance_to_zone(price: float, low: float, high: float) -> float:
    if price < low:
        return low - price
    if price > high:
        return price - high
    return 0.0


def _h1_confirmation(side: str, candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 3:
        return {"score": 0, "trigger_type": "none"}
    last = candles[-1]
    prev = candles[-2]
    body = abs(last.close - last.open)
    candle_range = max(last.high - last.low, 1e-9)
    upper_wick = last.high - max(last.open, last.close)
    lower_wick = min(last.open, last.close) - last.low

    if side == "buy":
        bullish = last.close > last.open
        engulfing = bullish and last.close > prev.high and last.open <= prev.close
        rejection = bullish and lower_wick >= max(body * 0.8, candle_range * 0.25)
        micro_break = last.close > max(item.high for item in candles[-3:-1])
        if engulfing:
            return {"score": 35, "trigger_type": "h1_bullish_engulfing"}
        if rejection:
            return {"score": 30, "trigger_type": "h1_bullish_rejection"}
        if micro_break:
            return {"score": 25, "trigger_type": "h1_bullish_break"}
    else:
        bearish = last.close < last.open
        engulfing = bearish and last.close < prev.low and last.open >= prev.close
        rejection = bearish and upper_wick >= max(body * 0.8, candle_range * 0.25)
        micro_break = last.close < min(item.low for item in candles[-3:-1])
        if engulfing:
            return {"score": 35, "trigger_type": "h1_bearish_engulfing"}
        if rejection:
            return {"score": 30, "trigger_type": "h1_bearish_rejection"}
        if micro_break:
            return {"score": 25, "trigger_type": "h1_bearish_break"}
    return {"score": 0, "trigger_type": "none"}


def _smc_confirmation(side: str, smc: dict[str, Any]) -> dict[str, Any]:
    h1 = smc.get("H1", {}) if isinstance(smc, dict) else {}
    h4 = smc.get("H4", {}) if isinstance(smc, dict) else {}
    expected = "bullish" if side == "buy" else "bearish"
    score = 0
    trigger = "none"
    if h1.get("displacement") == expected and (h1.get("bos") or h1.get("choch")):
        score += 20
        trigger = f"h1_{'bos' if h1.get('bos') else 'choch'}_{expected}"
    if h4.get("displacement") == expected and h4.get("bos"):
        score += 10
        trigger = trigger if trigger != "none" else f"h4_bos_{expected}"
    sweeps = h1.get("liquidity_sweeps", {})
    if side == "buy" and sweeps.get("swept_lows"):
        score += 10
        trigger = trigger if trigger != "none" else "liquidity_sweep_low"
    if side == "sell" and sweeps.get("swept_highs"):
        score += 10
        trigger = trigger if trigger != "none" else "liquidity_sweep_high"
    return {"score": min(score, 30), "trigger_type": trigger}


def _location_score(side: str, smc: dict[str, Any]) -> int:
    h4 = smc.get("H4", {}) if isinstance(smc, dict) else {}
    premium_discount = h4.get("premium_discount")
    if side == "buy" and premium_discount == "discount":
        return 15
    if side == "sell" and premium_discount == "premium":
        return 15
    if premium_discount == "equilibrium":
        return 8
    return 0


def _first_trigger(*triggers: str) -> str:
    for trigger in triggers:
        if trigger and trigger != "none":
            return trigger
    return "none"
