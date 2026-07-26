"""Parameter sensitivity scan for ATR-multiplier constants in risk_engine.py.

Runs system backtests across multiple market periods while varying one parameter
at a time, to measure how sensitive each constant is and whether the current
values are stable or overfit to a single market regime.

Usage (as module):
    from core.param_sensitivity import sweep_params, export_report
    results = sweep_params(configs, periods, symbols)
    export_report(results)

Usage (CLI):
    python param_sensitivity.py --full
    python param_sensitivity.py --param min_sl_distance_atr
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

import core.risk_engine as _re
from core.risk_parameter_context import RiskParameterOverrides


_CANDLE_CACHE: dict[tuple[str, str, str], dict[str, tuple[Any, ...]]] = {}
PARAM_SWEEP_VERSION = "parameter-sweep-v2-shared-context"


# ── Sweep configurations ─────────────────────────────────────────────────────

@dataclass
class ParamSweepConfig:
    """What to sweep for a single parameter."""
    json_key: str              # key in risk_params.json
    attr_name: str             # module attribute on risk_engine (e.g. "_MIN_SL_DISTANCE_ATR")
    test_values: list[float]   # values to test
    is_dict: bool = False      # True if the param is a dict (regime-specific)


# Priority params to sweep (matching proposal #2)
DEFAULT_SWEEP_CONFIGS = [
    ParamSweepConfig(
        json_key="min_sl_distance_atr",
        attr_name="_MIN_SL_DISTANCE_ATR",
        test_values=[0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    ),
    ParamSweepConfig(
        json_key="zone_sl_buffer_atr",
        attr_name="_ZONE_SL_BUFFER_ATR",
        test_values=[0.05, 0.10, 0.15, 0.20, 0.25],
    ),
    ParamSweepConfig(
        json_key="entry_aggressiveness",
        attr_name="_ENTRY_AGGRESSIVENESS",
        test_values=[0.0, 0.2, 0.5],
    ),
    ParamSweepConfig(
        json_key="tp_selection_aggressiveness",
        attr_name="_TP_SELECTION_AGGRESSIVENESS",
        test_values=[0.3, 0.5, 0.7],
    ),
    ParamSweepConfig(
        json_key="swing_sl_buffer_atr",
        attr_name="_SWING_SL_BUFFER_ATR",
        test_values=[0.05, 0.10, 0.15, 0.20, 0.25],
    ),
    ParamSweepConfig(
        json_key="sl_floor_buffer_atr",
        attr_name="_SL_FLOOR_BUFFER_ATR",
        test_values=[0.05, 0.10, 0.15, 0.20],
    ),
]

# Secondary params — less critical but useful for completeness
SECONDARY_SWEEP_CONFIGS = [
    ParamSweepConfig(
        json_key="eq_tp_max_rr",
        attr_name="_EQ_TP_MAX_RR",
        test_values=[2.0, 2.5, 3.0, 3.5, 4.0],
    ),
    ParamSweepConfig(
        json_key="tp2_min_gap_atr",
        attr_name="_TP2_MIN_GAP_ATR",
        test_values=[0.05, 0.10, 0.15, 0.20, 0.25],
    ),
    ParamSweepConfig(
        json_key="entry_zone_half_width_atr",
        attr_name="_ENTRY_ZONE_HALF_WIDTH_ATR",
        test_values=[0.20, 0.30, 0.35, 0.40, 0.50],
    ),
    ParamSweepConfig(
        json_key="min_stop_distance_atr_mult",
        attr_name="_MIN_STOP_DISTANCE_ATR_MULT",
        test_values=[0.10, 0.15, 0.20, 0.25, 0.30],
    ),
]


# ── Market periods ────────────────────────────────────────────────────────────

@dataclass
class MarketPeriod:
    """A representative market period for testing parameter stability."""
    name: str
    start: str          # YYYY-MM-DD
    end: str            # YYYY-MM-DD
    expected_regime: str  # "trend", "range", "volatile", "mixed"


DEFAULT_PERIODS = [
    MarketPeriod("Trending 2023 H1",   "2023-01-01", "2023-06-30", "trend"),
    MarketPeriod("Range 2024 H2",      "2024-07-01", "2024-12-31", "range"),
    MarketPeriod("Volatile 2025 H1",   "2025-01-01", "2025-06-30", "volatile"),
    MarketPeriod("Mixed Full 2024",    "2024-01-01", "2024-12-31", "mixed"),
]

DEFAULT_SYMBOLS = ["EUR/USD", "XAU/USD"]


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class SweepRunResult:
    param_value: float
    period: str
    symbol: str
    total_trades: int = 0
    win_rate: float = 0.0
    expectancy_r: float = 0.0
    profit_factor: float = 0.0
    max_drawdown_r: float = 0.0
    dataset_hash: str = ""
    request_fingerprint: str = ""
    provenance_fingerprint: str = ""
    execution_mode: str = ""
    lifecycle: str = "RESEARCH_ONLY"
    error: str | None = None


@dataclass
class SweepResult:
    json_key: str
    attr_name: str
    runs: list[SweepRunResult] = field(default_factory=list)
    stability_score: float | None = None   # 0-100, higher = more stable
    verdict: str = "UNKNOWN"               # STABLE / OVERFIT / INSENSITIVE / UNKNOWN
    recommendation: str | None = None       # human-readable recommendation
    version: str = PARAM_SWEEP_VERSION
    lifecycle: str = "RESEARCH_ONLY"
    can_apply_config: bool = False
    request_context: dict[str, Any] = field(default_factory=dict)


# ── Core sweep logic ──────────────────────────────────────────────────────────

def sweep_single_param(
    config: ParamSweepConfig,
    periods: list[MarketPeriod],
    symbols: list[str],
    *,
    progress_callback: Callable[[str], None] | None = None,
    data_provider: Any = None,
    backtest_settings: dict[str, Any] | None = None,
    request_templates: dict[str, Any] | None = None,
) -> SweepResult:
    """Sweep one parameter without mutating shared risk-engine globals."""
    log = progress_callback or (lambda _m: None)
    settings = backtest_settings or {}
    templates = request_templates or {}
    result = SweepResult(
        json_key=config.json_key,
        attr_name=config.attr_name,
        request_context={
            "symbols": list(symbols),
            "periods": [
                {
                    "name": period.name,
                    "start": period.start,
                    "end": period.end,
                    "expected_regime": period.expected_regime,
                }
                for period in periods
            ],
            "shared_request_templates": sorted(templates),
        },
    )

    total_runs = len(config.test_values) * len(periods) * len(symbols)
    run_idx = 0

    for val in config.test_values:
        for period in periods:
            for symbol in symbols:
                run_idx += 1
                label = f"[{run_idx}/{total_runs}] {config.attr_name}={val} | {period.name} | {symbol}"
                run_result = SweepRunResult(
                    param_value=val,
                    period=period.name,
                    symbol=symbol,
                )

                try:
                    summary = _run_single_backtest(
                        symbol=symbol,
                        start_str=period.start,
                        end_str=period.end,
                        data_provider=data_provider,
                        settings=settings,
                        parameter_overrides={config.json_key: val},
                        request_template=templates.get(symbol),
                    )
                    if summary:
                        run_result.total_trades = summary.get("total_trades", 0)
                        run_result.win_rate = summary.get("win_rate", 0.0)
                        run_result.expectancy_r = summary.get("expectancy_r", 0.0)
                        run_result.profit_factor = summary.get("profit_factor", 0.0)
                        run_result.max_drawdown_r = summary.get("max_drawdown_r", 0.0)
                        trace = summary.get("_sweep_trace", {})
                        if isinstance(trace, dict):
                            run_result.dataset_hash = str(trace.get("dataset_hash") or "")
                            run_result.request_fingerprint = str(
                                trace.get("request_fingerprint") or ""
                            )
                            run_result.provenance_fingerprint = str(
                                trace.get("provenance_fingerprint") or ""
                            )
                            run_result.execution_mode = str(
                                trace.get("execution_mode") or ""
                            )
                        log(f"  {label} ... {run_result.total_trades} trades, {run_result.expectancy_r:.2f}R")
                    else:
                        run_result.error = "no trades"
                        log(f"  {label} ... no trades")
                except Exception as exc:
                    import traceback as _tb
                    run_result.error = f"{exc}\n{_tb.format_exc()}"
                    log(f"  {label} ... ERROR: {exc}")

                result.runs.append(run_result)

    # Compute stability
    _compute_stability(result)

    return result


def sweep_params(
    configs: list[ParamSweepConfig],
    periods: list[MarketPeriod],
    symbols: list[str],
    *,
    progress_callback: Callable[[str], None] | None = None,
    data_provider: Any = None,
    backtest_settings: dict[str, Any] | None = None,
    request_templates: dict[str, Any] | None = None,
) -> list[SweepResult]:
    """Sweep multiple parameters. Returns one SweepResult per config."""
    log = progress_callback or (lambda _m: None)
    results: list[SweepResult] = []

    for i, config in enumerate(configs):
        log(f"\n{'='*60}")
        log(f"Param {i+1}/{len(configs)}: {config.attr_name} ({config.json_key})")
        log(f"Testing values: {config.test_values}")
        log(f"{'='*60}")

        result = sweep_single_param(
            config, periods, symbols,
            progress_callback=progress_callback,
            data_provider=data_provider,
            backtest_settings=backtest_settings,
            request_templates=request_templates,
        )
        results.append(result)

        log(f"  Verdict: {result.verdict} (stability={result.stability_score})")
        if result.recommendation:
            log(f"  Recommendation: {result.recommendation}")

    return results


# ── Backtest runner ───────────────────────────────────────────────────────────

def _run_single_backtest(
    symbol: str,
    start_str: str,
    end_str: str,
    data_provider: Any = None,
    settings: dict[str, Any] | None = None,
    parameter_overrides: dict[str, float] | None = None,
    request_template: Any = None,
) -> dict[str, Any] | None:
    """Run a single system backtest and return the trade summary."""
    from datetime import datetime as dt, timezone
    import traceback as _tb

    from core.system_backtest_engine import (
        BacktestRequest,
        run_system_backtest,
        summarize_backtest_trades,
    )

    start = dt.strptime(start_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    end = dt.strptime(end_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    overrides = RiskParameterOverrides.from_mapping(parameter_overrides)
    if isinstance(request_template, BacktestRequest):
        # The controller-created template contains broker metadata, costs,
        # account limits and execution mode. Only the research window and the
        # isolated parameter under test are changed here.
        request = replace(
            request_template,
            symbol=symbol,
            start=start,
            end=end,
            purpose="RESEARCH",
            risk_parameter_overrides=overrides,
            frozen_strategy_config=None,
        )
    else:
        # Compatibility path for CLI callers and legacy checkpoints.
        request = BacktestRequest(
            symbol=symbol,
            broker_symbol=_resolve_broker_symbol(symbol, data_provider),
            start=start,
            end=end,
            initial_balance=float(settings.get("initial_balance", 10000)),
            risk_percent=float(settings.get("risk_percent", 1.0)),
            account_currency=settings.get("account_currency", "USD"),
            lot_step=float(settings.get("lot_step", 0.01)),
            minimum_lot=float(settings.get("minimum_lot", 0.01)),
            maximum_lot=float(settings.get("maximum_lot", 100.0)),
            contract_size_override=settings.get("contract_size_override"),
            spread_price=float(settings.get("spread_price", 0.0)),
            entry_slippage_price=float(settings.get("entry_slippage_price", 0.0)),
            exit_slippage_price=float(settings.get("exit_slippage_price", 0.0)),
            commission_per_lot_round_turn=float(
                settings.get("commission_per_lot_round_turn", 0.0)
            ),
            swap_long_per_lot_day=float(settings.get("swap_long_per_lot_day", 0.0)),
            swap_short_per_lot_day=float(settings.get("swap_short_per_lot_day", 0.0)),
            risk_parameter_overrides=overrides,
        )

    # Load candles
    candles = _load_candles(request, data_provider)

    # Run backtest
    result = run_system_backtest(request, candles)
    summary = summarize_backtest_trades(result.trades)

    if summary.get("total_trades", 0) == 0:
        return None

    payload = result.to_dict()
    provenance = payload.get("backtest_provenance", {})
    manifest = payload.get("data_manifest", {})
    summary["_sweep_trace"] = {
        "dataset_hash": manifest.get("dataset_hash", "")
        if isinstance(manifest, dict) else "",
        "request_fingerprint": provenance.get("request_fingerprint", "")
        if isinstance(provenance, dict) else "",
        "provenance_fingerprint": provenance.get("provenance_fingerprint", "")
        if isinstance(provenance, dict) else "",
        "execution_mode": request.execution_mode,
        "lifecycle": "RESEARCH_ONLY",
    }
    return summary


def _resolve_broker_symbol(symbol: str, data_provider: Any = None) -> str:
    """Resolve display symbol to broker symbol. Falls back to strip-slash."""
    if data_provider is not None:
        try:
            available = data_provider.available_symbols(market_watch_only=True)
            resolved = data_provider.resolve_symbol(symbol, available)
            if resolved:
                return resolved
        except Exception:
            pass
    return symbol.replace("/", "")


def _load_candles(request: Any, data_provider: Any = None) -> dict[str, list]:
    """Load OHLCV candles for all required timeframes."""
    if data_provider is None:
        return {timeframe: [] for timeframe in ("D1", "H4", "H1", "M15")}
    from core.backtest_history import load_backtest_history

    return load_backtest_history(
        data_provider,
        request,
        cache=_CANDLE_CACHE,
        cache_limit=8,
    )


def _load_m15_chunked(data_provider: Any, broker_symbol: str, start: Any, end: Any) -> list:
    """Load M15 candles in chunks to avoid MT5 limits."""
    from core.backtest_history import load_m15_history

    return load_m15_history(data_provider, broker_symbol, start, end)


# ── Stability analysis ────────────────────────────────────────────────────────

def _compute_stability(result: SweepResult) -> None:
    """Compute stability score and verdict for a sweep result.

    Stability measures how consistent the optimal parameter value is across
    different market periods. High stability = same value works best everywhere.
    Low stability = different values optimal for different periods (overfit).
    """
    runs = [r for r in result.runs if r.error is None and r.total_trades > 0]
    if len(runs) < 2:
        result.stability_score = None
        result.verdict = "INCONCLUSIVE"
        result.recommendation = "Không đủ dữ liệu để đánh giá."
        return

    # Group runs by (period, symbol) and find best value per group
    from collections import defaultdict

    groups: dict[tuple[str, str], list[SweepRunResult]] = defaultdict(list)
    for r in runs:
        groups[(r.period, r.symbol)].append(r)

    # Find the best param_value for each group (by expectancy_r)
    best_values: list[float] = []
    for group_runs in groups.values():
        best = max(group_runs, key=lambda r: r.expectancy_r)
        best_values.append(best.param_value)

    if len(best_values) <= 1:
        result.stability_score = None
        result.verdict = "INCONCLUSIVE"
        result.recommendation = "Chỉ có 1 nhóm dữ liệu, không thể so sánh stability."
        return

    # Stability = inverse of coefficient of variation of best values
    mean_best = sum(best_values) / len(best_values)
    if mean_best == 0:
        result.stability_score = 0.0
        result.verdict = "OVERFIT"
        return

    variance = sum((v - mean_best) ** 2 for v in best_values) / len(best_values)
    cv = (variance ** 0.5) / abs(mean_best)  # coefficient of variation

    # CV = 0 → perfectly stable (score 100)
    # CV = 1.0 → highly unstable (score 0)
    score = max(0.0, min(100.0, 100.0 * (1.0 - cv)))
    result.stability_score = round(score, 1)

    # Verdict
    if score >= 70:
        result.verdict = "STABLE"
    elif score >= 40:
        result.verdict = "SUSPECT"
    else:
        result.verdict = "OVERFIT"

    # Check for insensitive params (all values give similar results)
    all_expectancy = [r.expectancy_r for r in runs]
    expectancy_range = max(all_expectancy) - min(all_expectancy)
    if expectancy_range < 0.05 and result.stability_score >= 60:
        result.verdict = "INSENSITIVE"
        result.stability_score = 100.0

    # Build recommendation
    current_val = getattr(_re, result.attr_name, None)
    best_overall = _find_best_value(runs)
    worst_overall = _find_worst_value(runs)

    if result.verdict == "STABLE":
        result.recommendation = (
            f"Giá trị hiện tại ({current_val}) ổn định. "
            f"Giá trị tối ưu trung bình: {best_overall:.3f}. "
            f"Giữ nguyên hoặc điều chỉnh nhẹ về {best_overall:.3f}."
        )
    elif result.verdict == "OVERFIT":
        conservative = _find_conservative_value(runs)
        result.recommendation = (
            f"KHÔNG ỔN ĐỊNH — mỗi period tối ưu ở 1 giá trị khác nhau. "
            f"Giá trị hiện tại: {current_val}. "
            f"Đề xuất dùng giá trị conservative: {conservative:.3f} "
            f"(không tốt nhất ở bất kỳ period nào nhưng an toàn nhất)."
        )
    elif result.verdict == "SUSPECT":
        result.recommendation = (
            f"Độ ổn định trung bình. Giá trị hiện tại: {current_val}. "
            f"Cân nhắc điều chỉnh về {best_overall:.3f} nếu muốn tối ưu, "
            f"hoặc giữ nguyên nếu ưu tiên ổn định."
        )
    elif result.verdict == "INSENSITIVE":
        result.recommendation = (
            f"Tham số ít ảnh hưởng đến kết quả. "
            f"Giá trị hiện tại ({current_val}) có thể giữ nguyên. "
            f"Không cần ưu tiên tối ưu."
        )
    else:
        result.recommendation = "Không đủ dữ liệu để đưa ra khuyến nghị."


def _find_best_value(runs: list[SweepRunResult]) -> float:
    """Find the param value with the highest mean expectancy across all runs."""
    from collections import defaultdict
    by_val: dict[float, list[float]] = defaultdict(list)
    for r in runs:
        by_val[r.param_value].append(r.expectancy_r)
    averages = {val: sum(exps) / len(exps) for val, exps in by_val.items()}
    return max(averages, key=averages.get)


def _find_worst_value(runs: list[SweepRunResult]) -> float:
    """Find the param value with the lowest mean expectancy."""
    from collections import defaultdict
    by_val: dict[float, list[float]] = defaultdict(list)
    for r in runs:
        by_val[r.param_value].append(r.expectancy_r)
    averages = {val: sum(exps) / len(exps) for val, exps in by_val.items()}
    return min(averages, key=averages.get)


def _find_conservative_value(runs: list[SweepRunResult]) -> float:
    """Find the most conservative param value — best worst-case performance.

    For each param value, compute the minimum expectancy across all periods.
    Pick the value with the highest minimum (maximin approach).
    """
    from collections import defaultdict
    by_val: dict[float, list[float]] = defaultdict(list)
    for r in runs:
        by_val[r.param_value].append(r.expectancy_r)
    min_by_val = {val: min(exps) for val, exps in by_val.items()}
    return max(min_by_val, key=min_by_val.get)


# ── Export ────────────────────────────────────────────────────────────────────

def export_results(
    results: list[SweepResult],
    output_dir: Path | str | None = None,
) -> Path:
    """Export sweep results as JSON + HTML report to output_dir.

    Returns the path to the HTML report.
    """
    if output_dir is None:
        from config.paths import app_data_dir
        output_dir = app_data_dir() / "param_tuning"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON export
    json_data = _results_to_dict(results)
    json_path = output_dir / "sensitivity_results.json"
    json_path.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Optimized params file
    optimized = _build_optimized_params(results)
    opt_path = output_dir / "risk_params_optimized.json"
    opt_path.write_text(json.dumps(optimized, indent=2, ensure_ascii=False), encoding="utf-8")

    # HTML report
    html = _build_html_report(results)
    html_path = output_dir / "sensitivity_report.html"
    html_path.write_text(html, encoding="utf-8")

    return html_path


def _results_to_dict(results: list[SweepResult]) -> dict:
    return {
        "version": PARAM_SWEEP_VERSION,
        "lifecycle": "RESEARCH_ONLY",
        "can_apply_config": False,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "results": [
            {
                "version": r.version,
                "lifecycle": r.lifecycle,
                "can_apply_config": r.can_apply_config,
                "request_context": r.request_context,
                "json_key": r.json_key,
                "attr_name": r.attr_name,
                "stability_score": r.stability_score,
                "verdict": r.verdict,
                "recommendation": r.recommendation,
                "runs": [
                    {
                        "param_value": run.param_value,
                        "period": run.period,
                        "symbol": run.symbol,
                        "total_trades": run.total_trades,
                        "win_rate": run.win_rate,
                        "expectancy_r": run.expectancy_r,
                        "profit_factor": run.profit_factor,
                        "max_drawdown_r": run.max_drawdown_r,
                        "dataset_hash": run.dataset_hash,
                        "request_fingerprint": run.request_fingerprint,
                        "provenance_fingerprint": run.provenance_fingerprint,
                        "execution_mode": run.execution_mode,
                        "lifecycle": run.lifecycle,
                        "error": run.error,
                    }
                    for run in r.runs
                ],
            }
            for r in results
        ],
    }


def _build_optimized_params(results: list[SweepResult]) -> dict:
    """Build a risk_params.json dict with recommended values."""
    # Start with current values
    params_file = Path(__file__).resolve().parents[1] / "config" / "risk_params.json"
    if params_file.exists():
        params = json.loads(params_file.read_text())
    else:
        params = {}

    # Update with recommendations
    for r in results:
        key = r.json_key
        if key not in params:
            continue
        if r.verdict in ("STABLE", "OVERFIT", "SUSPECT"):
            runs = [run for run in r.runs if run.error is None and run.total_trades > 0]
            if not runs:
                continue
            if r.verdict == "OVERFIT":
                params[key] = _find_conservative_value(runs)
            else:
                params[key] = _find_best_value(runs)

    params["_comment"] = (
        "Optimized values from param_sensitivity.py sweep. "
        "Review before copying to risk_params.json."
    )
    return params


# ── HTML report ───────────────────────────────────────────────────────────────

def _build_html_report(results: list[SweepResult]) -> str:
    rows_html = ""
    for r in results:
        verdict_color = {
            "STABLE": "#2ecc71", "OVERFIT": "#e74c3c",
            "SUSPECT": "#f39c12", "INSENSITIVE": "#95a5a6",
            "INCONCLUSIVE": "#95a5a6", "UNKNOWN": "#95a5a6",
        }.get(r.verdict, "#95a5a6")

        current_val = getattr(_re, r.attr_name, "N/A")

        # Build mini table for each value
        runs_html = _build_runs_table(r)

        rows_html += f"""
        <tr>
            <td><code>{r.attr_name}</code></td>
            <td><code>{r.json_key}</code></td>
            <td><code>{current_val}</code></td>
            <td style="color:{verdict_color};font-weight:bold">{r.verdict}</td>
            <td>{r.stability_score if r.stability_score is not None else '—'}</td>
            <td style="max-width:400px">{r.recommendation or '—'}</td>
        </tr>
        <tr>
            <td colspan="6" style="padding:0 0 16px 16px">{runs_html}</td>
        </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<title>Param Sensitivity Report</title>
<style>
  body {{ font-family: -apple-system, 'Segoe UI', sans-serif; margin: 24px; background: #fff; color: #222; }}
  h1 {{ font-size: 22px; }}
  h2 {{ font-size: 16px; margin-top: 32px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; vertical-align: top; }}
  th {{ background: #f5f5f5; font-weight: 600; }}
  code {{ background: #f0f0f0; padding: 1px 5px; border-radius: 3px; font-size: 13px; }}
  .runs-table {{ font-size: 12px; margin: 4px 0; }}
  .runs-table th {{ background: #fafafa; font-size: 11px; }}
  .runs-table td {{ padding: 2px 8px; }}
</style>
</head>
<body>
<h1>Param Sensitivity Scan — Báo cáo</h1>
<p>Generated: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}</p>

<h2>Tổng quan</h2>
<table>
<tr>
    <th>Attribute</th>
    <th>JSON Key</th>
    <th>Hiện tại</th>
    <th>Verdict</th>
    <th>Stability</th>
    <th>Recommendation</th>
</tr>
{rows_html}
</table>

<h2>Hướng dẫn</h2>
<ul>
<li><strong>STABLE</strong>: Giá trị hiện tại ổn định trên mọi period — giữ nguyên.</li>
<li><strong>OVERFIT</strong>: Mỗi period tối ưu ở 1 giá trị khác nhau — cần chọn giá trị conservative.</li>
<li><strong>SUSPECT</strong>: Độ ổn định trung bình — cân nhắc điều chỉnh.</li>
<li><strong>INSENSITIVE</strong>: Tham số ít ảnh hưởng — không cần ưu tiên tối ưu.</li>
</ul>
<p>File JSON đề xuất: <code>risk_params_optimized.json</code> — copy các giá trị đồng ý vào <code>config/risk_params.json</code>.</p>
</body>
</html>"""


def _build_runs_table(result: SweepResult) -> str:
    """Build a mini HTML table showing per-value results across periods."""
    if not result.runs:
        return ""

    # Group by param_value, then by period
    from collections import defaultdict
    by_val: dict[float, list[SweepRunResult]] = defaultdict(list)
    for run in result.runs:
        by_val[run.param_value].append(run)

    periods = sorted(set(r.period for r in result.runs))
    symbols = sorted(set(r.symbol for r in result.runs))

    header = "<tr><th>Value</th>"
    for period in periods:
        for sym in symbols:
            header += f"<th>{period}<br>{sym}</th>"
    header += "<th>Avg E[R]</th></tr>"

    rows = ""
    for val in sorted(by_val.keys()):
        rows += f"<tr><td><code>{val}</code></td>"
        val_runs = {(r.period, r.symbol): r for r in by_val[val]}
        avg_exp = 0.0
        count = 0
        for period in periods:
            for sym in symbols:
                run = val_runs.get((period, sym))
                if run and run.error is None and run.total_trades > 0:
                    rows += (
                        f"<td>{run.total_trades}t "
                        f"{run.expectancy_r:+.2f}R "
                        f"WR:{run.win_rate:.0%}</td>"
                    )
                    avg_exp += run.expectancy_r
                    count += 1
                elif run and run.error:
                    rows += f"<td style='color:#e74c3c'>{run.error}</td>"
                else:
                    rows += "<td>—</td>"
        avg_exp = avg_exp / count if count > 0 else 0.0
        rows += f"<td><strong>{avg_exp:+.2f}R</strong></td></tr>"

    return f'<table class="runs-table">{header}{rows}</table>'


# ── Quick-start helper ────────────────────────────────────────────────────────

def quick_sweep(
    *,
    data_provider: Any = None,
    settings: dict[str, Any] | None = None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[SweepResult]:
    """Run a quick sweep on the 4 priority params with 2 periods and 1 symbol.

    Good for a first-pass check (~5 minutes). For a full sweep, use sweep_params().
    """
    log = progress_callback or (lambda _m: None)
    log("Quick sweep: 4 priority params x 2 periods x 1 symbol")

    quick_periods = [
        MarketPeriod("Trend 2023", "2023-01-01", "2023-06-30", "trend"),
        MarketPeriod("Range 2024", "2024-07-01", "2024-12-31", "range"),
    ]
    quick_symbols = ["EUR/USD"]

    return sweep_params(
        DEFAULT_SWEEP_CONFIGS[:4],
        quick_periods,
        quick_symbols,
        progress_callback=progress_callback,
        data_provider=data_provider,
        backtest_settings=settings,
    )
