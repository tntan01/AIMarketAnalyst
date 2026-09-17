from __future__ import annotations

import json
from typing import Any


def decorate_chart_payload(payload: dict) -> dict:
    """Add the display labels the chart page renders (task 124).

    The canonical payload carries codes, not sentences.  The Vietnamese
    vocabulary of the SMC layer is owned by ``ui.scanner_presentation``, so the
    labels are attached here — at the UI boundary — and the chart page only
    draws what it is given.  The canonical payload itself is never mutated; a
    new mapping is returned, and a payload without an overlay is returned
    unchanged (so this stays a no-op for every other caller).
    """

    if not isinstance(payload, dict) or "smc_overlay" not in payload:
        return payload
    from ui.scanner_presentation import present_smc_overlay

    decorated: dict[str, Any] = dict(payload)
    decorated["smc_overlay"] = present_smc_overlay(payload.get("smc_overlay"))
    return decorated


def chart_update_script(payload: dict) -> str:
    """Generate JavaScript to update chart with full payload.

    payload matches build_full_chart_payload() output:
    {symbol, active_timeframe, current_price, timeframes, trade_plan, levels, zones}
    """
    return f"if(window.setChartData){{window.setChartData({json.dumps(decorate_chart_payload(payload), default=str)});}}"


def chart_switch_tf_script(timeframe: str) -> str:
    """Generate JavaScript to switch active timeframe."""
    return f"if(window.switchTimeframe){{window.switchTimeframe('{timeframe}');}}"


def chart_reload_script() -> str:
    """Generate JavaScript to force chart reload."""
    return "if(window.reloadChart){window.reloadChart();}"


def chart_resize_script() -> str:
    """Generate JavaScript to handle resize."""
    return "if(window.handleResize){window.handleResize();}"


def chart_theme_script(theme: str, palette: dict[str, str]) -> str:
    """Generate JavaScript that updates chart chrome without resetting data."""

    theme_json = json.dumps(str(theme))
    palette_json = json.dumps(palette, default=str)
    return (
        "if(window.applyChartTheme){"
        f"window.applyChartTheme({theme_json},{palette_json});"
        "}"
    )
