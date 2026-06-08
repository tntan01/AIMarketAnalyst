from __future__ import annotations

from typing import Any

from core.indicators import atr, ema, macd, rsi
from core.market_models import Candle


STRENGTH_RANK = {"strong": 3, "moderate": 2, "weak": 1}


def build_technical_snapshot(d1: list[Candle], h4: list[Candle], h1: list[Candle]) -> dict[str, Any]:
    if len(d1) < 60 or len(h4) < 60 or len(h1) < 30:
        raise ValueError("Không đủ dữ liệu D1/H4/H1 để dựng technical context.")

    d1_close = [item.close for item in d1]
    h4_close = [item.close for item in h4]
    h4_high = [item.high for item in h4]
    h4_low = [item.low for item in h4]
    d1_high = [item.high for item in d1]
    d1_low = [item.low for item in d1]

    d1_ema50 = ema(d1_close, 50)[-1]
    d1_ema200 = ema(d1_close, 200)[-1]
    d1_ema50_prev = ema(d1_close, 50)[-5] if len(d1_close) >= 60 else d1_ema50
    d1_ema200_prev = ema(d1_close, 200)[-5] if len(d1_close) >= 60 else d1_ema200
    h4_ema50 = ema(h4_close, 50)[-1]

    h4_rsi_values = [value for value in rsi(h4_close, 14) if value is not None]
    h4_macd = macd(h4_close)
    h4_atr_values = [value for value in atr(h4_high, h4_low, h4_close, 14) if value is not None]
    d1_atr_values = [value for value in atr(d1_high, d1_low, d1_close, 14) if value is not None]

    h4_swings = swing_points(h4, lookback=2)
    d1_swings = swing_points(d1, lookback=2)
    structure_h4 = detect_structure(h4_swings)
    structure_d1 = detect_structure(d1_swings)

    h4_atr_now = h4_atr_values[-1] if h4_atr_values else 0.0
    support_zones = build_zones("support", h4_swings["lows"], h4_atr_now)
    resistance_zones = build_zones("resistance", h4_swings["highs"], h4_atr_now)

    histogram = h4_macd["histogram"]
    histogram_now = histogram[-1] if histogram else 0.0
    histogram_prev = histogram[-2] if len(histogram) >= 2 else histogram_now
    histogram_prev2 = histogram[-3] if len(histogram) >= 3 else histogram_prev
    rsi_now = h4_rsi_values[-1] if h4_rsi_values else None
    rsi_prev = h4_rsi_values[-2] if len(h4_rsi_values) >= 2 else rsi_now

    range_info = detect_range_window(d1_swings, d1_ema50_prev, d1_ema200_prev, d1_ema50, d1_ema200,
                                      h4_atr_now,
                                      sum(d1_atr_values[-14:]) / min(len(d1_atr_values), 14) if d1_atr_values else 0.0)

    technical = {
        "price": h1[-1].close,
        "ema50_d1": d1_ema50,
        "ema200_d1": d1_ema200,
        "ema50_h4": h4_ema50,
        "ema50_d1_slope": d1_ema50 - d1_ema50_prev,
        "ema200_d1_slope": d1_ema200 - d1_ema200_prev,
        "rsi_h4": rsi_now,
        "rsi_h4_previous": rsi_prev,
        "macd_histogram_h4": {
            "value": histogram_now,
            "previous_value": histogram_prev,
            "previous2_value": histogram_prev2,
            "direction": "increasing" if histogram_now > histogram_prev else "decreasing",
        },
        "atr_d1": d1_atr_values[-1] if d1_atr_values else None,
        "atr_h4": h4_atr_now if h4_atr_values else None,
        "atr_avg_14d": sum(d1_atr_values[-14:]) / min(len(d1_atr_values), 14) if d1_atr_values else None,
        "support_zones": support_zones,
        "resistance_zones": resistance_zones,
        "structure_d1": structure_d1,
        "structure_h4": structure_h4,
        "swings_h4": h4_swings,
        "swings_d1": d1_swings,
        "range_info": range_info,
    }
    return technical


def swing_points(candles: list[Candle], lookback: int = 2) -> dict[str, list[dict[str, Any]]]:
    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []
    for index in range(lookback, len(candles) - lookback):
        window = candles[index - lookback : index + lookback + 1]
        candle = candles[index]
        if candle.high == max(item.high for item in window) and sum(candle.high == item.high for item in window) == 1:
            highs.append({"level": candle.high, "time": candle.time.isoformat(), "index": index})
        if candle.low == min(item.low for item in window) and sum(candle.low == item.low for item in window) == 1:
            lows.append({"level": candle.low, "time": candle.time.isoformat(), "index": index})
    return {"highs": highs, "lows": lows}


def detect_structure(swings: dict[str, list[dict[str, Any]]]) -> str:
    highs = [item["level"] for item in swings["highs"][-2:]]
    lows = [item["level"] for item in swings["lows"][-2:]]
    if len(highs) < 2 or len(lows) < 2:
        return "unknown"
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return "HH/HL"
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return "LH/LL"
    return "mixed"


def build_zones(kind: str, swings: list[dict[str, Any]], atr_value: float) -> list[dict[str, Any]]:
    width = max(atr_value * 0.15, 0.0001)
    zones: list[dict[str, Any]] = []
    for item in swings[-6:]:
        level = item["level"]
        confluence_count = 1 + sum(
            1 for other in swings[-10:] if other is not item and abs(other["level"] - level) <= width
        )
        zones.append(
            {
                "level": level,
                "low": level - width,
                "high": level + width,
                "type": "recent_swing_low" if kind == "support" else "recent_swing_high",
                "strength": classify_zone_strength("recent_swing", confluence_count, 1),
                "confluence_count": confluence_count,
                "consolidation_bars": 0,
                "source": "technical",
            }
        )
    return zones


def classify_zone_strength(zone_type: str, confluence_count: int, test_count: int) -> str:
    score = 0
    if zone_type in {"pivot_monthly", "pivot_weekly"}:
        score += 2
    if test_count >= 3:
        score += 2
    elif test_count >= 1:
        score += 1
    if confluence_count >= 2:
        score += 2
    if zone_type == "recent_swing":
        score += 1
    if score >= 4:
        return "strong"
    if score >= 2:
        return "moderate"
    return "weak"


def detect_market_regime(technical: dict[str, Any], news_in_3h: bool) -> dict[str, Any]:
    secondary: list[str] = []
    atr_h4 = technical["atr_h4"] or 0.0
    atr_avg = technical["atr_avg_14d"] or atr_h4
    if atr_avg and atr_h4 > 1.5 * atr_avg:
        secondary.append("volatile")
    if news_in_3h:
        secondary.append("news_sensitive")
    price = technical["price"]
    range_info = technical.get("range_info")
    if technical["ema50_d1"] > technical["ema200_d1"] and price > technical["ema50_d1"] and technical["structure_h4"] == "HH/HL":
        primary = "trend_up"
    elif technical["ema50_d1"] < technical["ema200_d1"] and price < technical["ema50_d1"] and technical["structure_h4"] == "LH/LL":
        primary = "trend_down"
    elif range_info and range_info.get("is_range"):
        primary = "range"
    elif abs(technical["ema50_d1"] - technical["ema200_d1"]) <= max(atr_h4, 0.0001) * 0.5:
        primary = "range"
    else:
        primary = "unknown"
    return {
        "primary": primary,
        "secondary": secondary,
        "structure": technical["structure_h4"],
        "explanation": (
            f"D1 EMA50={technical['ema50_d1']:.5f}, EMA200={technical['ema200_d1']:.5f}; "
            f"H4 structure={technical['structure_h4']}."
        ),
    }


def detect_range_window(
    d1_swings: dict[str, list[dict[str, Any]]],
    ema50_prev: float,
    ema200_prev: float,
    ema50_now: float,
    ema200_now: float,
    atr_h4: float,
    atr_avg_14d: float,
) -> dict[str, Any]:
    highs = [item["level"] for item in d1_swings["highs"][-5:]]
    lows = [item["level"] for item in d1_swings["lows"][-5:]]
    if len(highs) < 2 or len(lows) < 2:
        return {"is_range": False}
    range_high = max(highs)
    range_low = min(lows)
    mid_range = (range_high + range_low) / 2
    ema_flat = abs(ema50_now - ema50_prev) < max(atr_h4 * 0.05, 1e-6) and abs(ema200_now - ema200_prev) < max(atr_h4 * 0.05, 1e-6)
    atr_not_expanding = atr_avg_14d == 0 or atr_h4 <= 1.2 * atr_avg_14d
    return {
        "is_range": ema_flat and atr_not_expanding,
        "range_high": range_high,
        "range_low": range_low,
        "mid_range": mid_range,
    }


def summarize_trend(candles: list[Candle]) -> str:
    if len(candles) < 2:
        return "unknown"
    return "bullish" if candles[-1].close > candles[0].close else "bearish"


def price_in_zone(price: float, zone: dict[str, Any]) -> bool:
    return zone["low"] <= price <= zone["high"]


def distance_to_zone(price: float, zone: dict[str, Any]) -> float:
    if price < zone["low"]:
        return zone["low"] - price
    if price > zone["high"]:
        return price - zone["high"]
    return 0.0


def nearest_zone(price: float, zones: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not zones:
        return None
    return min(
        zones,
        key=lambda zone: (distance_to_zone(price, zone), -STRENGTH_RANK.get(zone.get("strength", "weak"), 0)),
    )
