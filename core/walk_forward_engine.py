from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from typing import Any, Callable

from core.system_backtest_engine import (
    BacktestRequest,
    BacktestTrade,
    run_system_backtest,
    summarize_backtest_trades,
)


def run_walk_forward(
    request: BacktestRequest,
    candles_by_timeframe: dict[str, list],
    is_months: int = 6,
    oos_months: int = 3,
    step_months: int = 3,
    progress_callback: Callable[[int, str], None] | None = None,
) -> dict[str, Any]:
    total_span = request.end - request.start
    min_span = timedelta(days=(is_months + oos_months) * 31)
    if total_span < min_span:
        return {
            "error": (
                f"Khoảng thời gian quá ngắn. Cần ít nhất {is_months + oos_months} tháng, "
                f"hiện có {total_span.days} ngày."
            ),
            "windows": [],
            "aggregate_is": None,
            "aggregate_oos": None,
            "oos_is_expectancy_ratio": None,
            "robustness_score": None,
            "verdict": "INCONCLUSIVE",
            "window_count": 0,
        }

    progress = progress_callback or (lambda _p, _m: None)
    windows: list[dict[str, Any]] = []
    all_is_trades: list[BacktestTrade] = []
    all_oos_trades: list[BacktestTrade] = []

    current = request.start
    window_index = 0
    while True:
        is_start = current
        is_end = is_start + timedelta(days=is_months * 31)
        oos_start = is_end
        oos_end = oos_start + timedelta(days=oos_months * 31)
        if oos_end > request.end:
            break

        window_index += 1
        progress(
            int(window_index * 100 / max(1, (total_span.days // (step_months * 31)))),
            f"Walk-Forward: window {window_index} IS={is_start.strftime('%Y-%m')} OOS={oos_start.strftime('%Y-%m')}",
        )

        is_request = replace(request, start=is_start, end=is_end)
        oos_request = replace(request, start=oos_start, end=oos_end)

        try:
            is_result = run_system_backtest(is_request, candles_by_timeframe, progress_callback=progress)
            oos_result = run_system_backtest(oos_request, candles_by_timeframe, progress_callback=progress)
        except Exception as exc:
            windows.append({
                "is_start": is_start.isoformat(),
                "is_end": is_end.isoformat(),
                "oos_start": oos_start.isoformat(),
                "oos_end": oos_end.isoformat(),
                "is_summary": None,
                "oos_summary": None,
                "error": str(exc),
            })
            current += timedelta(days=step_months * 31)
            continue

        is_summary = summarize_backtest_trades(is_result.trades)
        oos_summary = summarize_backtest_trades(oos_result.trades)

        if is_summary["total_trades"] == 0 or oos_summary["total_trades"] == 0:
            current += timedelta(days=step_months * 31)
            continue

        all_is_trades.extend(is_result.trades)
        all_oos_trades.extend(oos_result.trades)

        windows.append({
            "is_start": is_start.isoformat(),
            "is_end": is_end.isoformat(),
            "oos_start": oos_start.isoformat(),
            "oos_end": oos_end.isoformat(),
            "is_summary": is_summary,
            "oos_summary": oos_summary,
        })

        current += timedelta(days=step_months * 31)

    aggregate_is = summarize_backtest_trades(all_is_trades) if all_is_trades else None
    aggregate_oos = summarize_backtest_trades(all_oos_trades) if all_oos_trades else None

    if aggregate_is is None or aggregate_oos is None or len(windows) == 0:
        return {
            "windows": windows,
            "aggregate_is": aggregate_is,
            "aggregate_oos": aggregate_oos,
            "oos_is_expectancy_ratio": None,
            "robustness_score": None,
            "verdict": "INCONCLUSIVE",
            "window_count": len(windows),
        }

    is_exp = float(aggregate_is.get("expectancy_r", 0) or 0)
    oos_exp = float(aggregate_oos.get("expectancy_r", 0) or 0)
    ratio = round(oos_exp / is_exp, 4) if is_exp > 0 else 0.0

    if ratio >= 1.0:
        score = 100.0
    elif ratio < 0.3:
        score = 0.0
    else:
        score = round((ratio - 0.3) / 0.7 * 100.0, 1)

    if score >= 70:
        verdict = "ROBUST"
    elif score >= 40:
        verdict = "SUSPECT"
    else:
        verdict = "OVERFITTING"

    return {
        "windows": windows,
        "aggregate_is": aggregate_is,
        "aggregate_oos": aggregate_oos,
        "oos_is_expectancy_ratio": ratio,
        "robustness_score": score,
        "verdict": verdict,
        "window_count": len(windows),
    }
