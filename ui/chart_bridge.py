from __future__ import annotations

import json


def chart_update_script(payload: dict) -> str:
    """Generate JavaScript to update chart with full payload.

    payload matches build_full_chart_payload() output:
    {symbol, active_timeframe, current_price, timeframes, trade_plan, levels, zones}
    """
    return f"if(window.setChartData){{window.setChartData({json.dumps(payload, default=str)});}}"


def chart_switch_tf_script(timeframe: str) -> str:
    """Generate JavaScript to switch active timeframe."""
    return f"if(window.switchTimeframe){{window.switchTimeframe('{timeframe}');}}"


def chart_reload_script() -> str:
    """Generate JavaScript to force chart reload."""
    return "if(window.reloadChart){window.reloadChart();}"


def chart_resize_script() -> str:
    """Generate JavaScript to handle resize."""
    return "if(window.handleResize){window.handleResize();}"
