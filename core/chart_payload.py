from __future__ import annotations

from typing import Any

from core.market_models import Candle


def candles_to_chart_payload(candles: list[Candle]) -> list[dict[str, float | int]]:
    return [
        {
            "time": int(candle.time.timestamp()),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
        }
        for candle in candles
    ]


def build_chart_payload(candles_by_timeframe: dict[str, list[Candle]]) -> dict[str, list[dict[str, Any]]]:
    return {
        timeframe: [
            {
                "time": candle.time.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
            }
            for candle in candles
        ]
        for timeframe, candles in candles_by_timeframe.items()
    }


def build_full_chart_payload(symbol: str, result: dict, active_timeframe: str = "H1") -> dict:
    """Build complete chart payload for QWebEngineView rendering.

    Returns a dict with:
    - symbol
    - active_timeframe
    - timeframes: {D1/H4/H1: {candles, indicators, smc_zones}}
    - trade_plan: entry_zone, stop_loss, take_profit, side
    - levels: SL/TP price lines
    - zones: entry zone rectangles
    """
    from core.indicators import ema

    chart_payload = result.get("chart_payload", {})
    if not isinstance(chart_payload, dict):
        chart_payload = {}

    # Build timeframe data
    timeframes_data = {}
    for tf, candles in chart_payload.items():
        if not candles:
            continue
        tf_data = {"candles": candles}
        # EMA indicators from close prices
        closes = [c["close"] for c in candles if isinstance(c, dict) and "close" in c]
        if len(closes) >= 20:
            ema20 = ema(closes, 20)
            ema50 = ema(closes, 50) if len(closes) >= 50 else None
            ema200 = ema(closes, 200) if len(closes) >= 200 else None
            indicators = []
            for i in range(len(candles)):
                point = {"time": candles[i]["time"]}
                if i < len(ema20):
                    point["ema20"] = round(ema20[i], 5)
                if ema50 and i < len(ema50):
                    point["ema50"] = round(ema50[i], 5)
                if ema200 and i < len(ema200):
                    point["ema200"] = round(ema200[i], 5)
                indicators.append(point)
            tf_data["indicators"] = indicators
        # SMC zones
        smc = result.get("smc", {})
        if isinstance(smc, dict):
            tf_smc = smc.get(tf, {})
            if isinstance(tf_smc, dict):
                zones = []
                for key in ["supply_zones", "demand_zones", "order_blocks", "fvg"]:
                    items = tf_smc.get(key, [])
                    if isinstance(items, list):
                        for item in items:
                            if isinstance(item, dict) and "high" in item and "low" in item:
                                zones.append({
                                    "from": item["low"],
                                    "to": item["high"],
                                    "type": key,
                                    "label": item.get("type", key),
                                })
                tf_data["smc_zones"] = zones
        timeframes_data[tf] = tf_data

    # Trade plan from scenarios
    trade_plan = {"side": "neutral", "entry_zone": None, "stop_loss": None, "take_profit": None, "entry_status": "no_setup"}
    scenarios = result.get("scenarios", [])
    if isinstance(scenarios, list) and scenarios:
        primary = scenarios[0]
        if isinstance(primary, dict):
            trade_plan["side"] = primary.get("type", "neutral")
            trade_plan["entry_zone"] = primary.get("entry_zone")
            trade_plan["stop_loss"] = primary.get("stop_loss")
            trade_plan["take_profit"] = primary.get("take_profit")
            trade_plan["entry_status"] = primary.get("entry_status", "no_setup")

    def _to_float(value: Any) -> float | None:
        try:
            if value in (None, "", "--", "-"):
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    # Build levels (horizontal price lines for SL/TP)
    levels = []
    sl = _to_float(trade_plan["stop_loss"])
    if sl is not None:
        levels.append({"price": sl, "label": "SL", "type": "stop_loss"})
    tp = trade_plan["take_profit"]
    if isinstance(tp, list):
        for idx, tp_price in enumerate(tp, 1):
            price = _to_float(tp_price)
            if price is not None:
                levels.append({"price": price, "label": f"TP{idx}", "type": "take_profit"})
    elif tp is not None:
        price = _to_float(tp)
        if price is not None:
            levels.append({"price": price, "label": "TP", "type": "take_profit"})

    # Build zones (entry zone rectangle)
    zones = []
    entry = trade_plan["entry_zone"]
    if isinstance(entry, list) and len(entry) == 2:
        entry_from = _to_float(entry[0])
        entry_to = _to_float(entry[1])
        if entry_from is not None and entry_to is not None:
            zones.append({
                "from": entry_from,
                "to": entry_to,
                "label": "Entry",
                "type": "entry_zone",
            })

    # Current price
    technical = result.get("technical", {})
    current_price = None
    if isinstance(technical, dict):
        current_price = technical.get("price")

    return {
        "symbol": symbol,
        "active_timeframe": active_timeframe,
        "current_price": current_price,
        "timeframes": timeframes_data,
        "trade_plan": trade_plan,
        "levels": levels,
        "zones": zones,
    }
