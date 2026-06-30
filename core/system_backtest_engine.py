from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Any

from core.analysis_engine import analyze_symbol
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from core.safe_types import optional_float


AnalysisFn = Callable[..., dict[str, Any]]
BACKTEST_FUNNEL_KEYS = (
    "snapshots_evaluated",
    "no_trade_scenario",
    "setup_detected",
    "fallback_scenario",
    "blocked_by_trade_gate",
    "blocked_by_permission",
    "blocked_by_decision",
    "blocked_by_score",
    "blocked_by_entry_status",
    "blocked_by_m15",
    "blocked_by_rr",
    "entry_zone_not_touched",
    "invalid_trade_plan",
    "trade_opened",
)


@dataclass(frozen=True, slots=True)
class BacktestRequest:
    symbol: str
    broker_symbol: str
    start: datetime
    end: datetime
    initial_balance: float
    risk_percent: float
    account_currency: str = "USD"
    lot_step: float = 0.01
    minimum_lot: float = 0.01
    contract_size_override: float | None = None
    timezone_name: str = "Asia/Ho_Chi_Minh"
    spread_price: float = 0.0
    slippage_price: float = 0.0
    max_holding_bars: int = 96
    setup_expiry_bars: int = 12
    step_timeframe: str = "H1"
    allow_macro: bool = False
    conservative_same_bar: bool = True
    store_analysis_snapshots: bool = False
    account_guard_enabled: bool = False
    max_daily_loss_pct: float = 999.0
    max_weekly_loss_pct: float = 999.0
    max_consecutive_losses: int = 999
    max_open_risk_pct: float = 999.0
    min_final_score: int = 0
    correlation_context: dict[str, Any] | None = None
    macro_alignment_override: dict[str, int] | None = None


@dataclass(slots=True)
class BacktestTrade:
    symbol: str
    side: str
    decision: str
    entry_time: str
    exit_time: str | None
    entry_price: float
    stop_loss: float
    take_profit: float
    exit_price: float | None
    result: str
    result_r: float
    holding_bars: int
    final_score: int
    signal_score: int
    buy_score: int
    sell_score: int
    score_gap: float
    market_regime: str
    entry_status: str
    m15_quality: str | None
    expected_effective_rr: float | None
    selected_zone_score: int | None
    selected_zone_type: str | None
    entry_zone_score: int | None
    entry_zone_source: str | None
    liquidity_sweep_aligned: bool
    displacement_aligned: bool
    choch_against_direction: bool
    reason_codes: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    block_codes: list[str] = field(default_factory=list)
    analysis_snapshot: dict[str, Any] | None = None


@dataclass(slots=True)
class BacktestResult:
    request: BacktestRequest
    summary: dict[str, Any]
    trades: list[BacktestTrade]
    equity_curve: list[dict[str, Any]]
    breakdowns: dict[str, Any]
    skipped_setups: list[dict[str, Any]]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": "system_backtest",
            "request": _request_to_dict(self.request),
            "summary": self.summary,
            "trades": [asdict(trade) for trade in self.trades],
            "equity_curve": self.equity_curve,
            "breakdowns": self.breakdowns,
            "skipped_setups": self.skipped_setups,
            "diagnostics": self.diagnostics,
        }


def run_system_backtest(
    request: BacktestRequest,
    candles_by_timeframe: dict[str, list[Candle]],
    *,
    analysis_fn: AnalysisFn = analyze_symbol,
    progress_callback: Callable[[int, str], None] | None = None,
) -> BacktestResult:
    validate_backtest_input(request, candles_by_timeframe)
    progress = progress_callback or (lambda _percent, _message: None)
    step_candles = candles_by_timeframe.get(request.step_timeframe) or candles_by_timeframe.get("H1", [])
    m15_all = candles_by_timeframe.get("M15", [])
    trades: list[BacktestTrade] = []
    skipped: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    closed_for_guard: list[dict[str, Any]] = []
    funnel = {key: 0 for key in BACKTEST_FUNNEL_KEYS}
    balance = float(request.initial_balance)
    snapshots_evaluated = 0
    setups_detected = 0
    blocked_by_gate = 0
    analysis_errors = 0
    next_allowed_time: datetime | None = None
    pipeline_stats: dict[str, dict[str, int]] = {}  # step → {pass/fail/warning: count}
    gate_fail_counts: dict[str, int] = {}  # gate_name → fail count
    score_fail_count = 0  # snapshots where best_score < 50

    eligible_steps = [
        (index, candle)
        for index, candle in enumerate(step_candles)
        if request.start <= candle.time <= request.end
    ]
    total_steps = max(1, len(eligible_steps))

    for ordinal, (step_index, candle) in enumerate(eligible_steps, start=1):
        if next_allowed_time is not None and candle.time <= next_allowed_time:
            continue
        percent = 10 + int(ordinal / total_steps * 75)
        t = candle.time
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        gmt7 = t.astimezone(timezone(timedelta(hours=7)))
        time_str = gmt7.strftime("%d/%m/%Y %H:%M")
        progress(percent, f"Đang backtest {request.symbol} tại {time_str}")

        snapshot = slice_candles_until(candles_by_timeframe, candle.time)
        if not has_minimum_analysis_data(snapshot):
            skipped.append(_skip(candle.time, "insufficient_warmup", "Chưa đủ dữ liệu warmup."))
            continue

        try:
            analysis = _run_analysis_snapshot(
                request,
                snapshot,
                balance,
                closed_for_guard,
                candle.time,
                analysis_fn,
            )
        except Exception as exc:
            analysis_errors += 1
            skipped.append(_skip(candle.time, "analysis_error", str(exc)))
            continue

        snapshots_evaluated += 1
        funnel["snapshots_evaluated"] += 1

        # --- Aggregate pipeline diagnostics from this snapshot ---
        _aggregate_pipeline_diag(analysis, pipeline_stats, gate_fail_counts)
        if analysis.get("decision_summary", {}).get("best_score", 0) < 50:
            score_fail_count += 1

        scenario = select_trade_scenario(analysis)
        is_fallback = False
        if not scenario:
            scenario = build_fallback_scenario(analysis, candle)
            is_fallback = scenario is not None
        if not scenario:
            funnel["no_trade_scenario"] += 1
            skipped.append(
                _skip(
                    candle.time,
                    "no_trade_scenario",
                    "Không có scenario buy/sell hợp lệ.",
                    build_skip_debug(analysis, None),
                )
            )
            continue

        setups_detected += 1
        funnel["setup_detected"] += 1
        if is_fallback:
            funnel["fallback_scenario"] += 1
        block_reason = trade_open_block_reason(analysis, scenario, request.min_final_score)
        if block_reason is not None:
            if _gate_blocked(analysis):
                blocked_by_gate += 1
            if block_reason in funnel:
                funnel[block_reason] += 1
            skipped.append(
                _skip(
                    candle.time,
                    "not_actionable",
                    _skip_reason(analysis, scenario, block_reason),
                    build_skip_debug(analysis, scenario),
                )
            )
            # When account guard blocks (daily loss / consecutive losses),
            # skip to the next trading day to avoid wasted cycles.
            if _is_account_guard_block(analysis):
                from datetime import timedelta as _td
                from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
                try:
                    tz = ZoneInfo(request.timezone_name)
                except (ZoneInfoNotFoundError, KeyError):
                    tz = ZoneInfo("Asia/Ho_Chi_Minh")
                local = candle.time.astimezone(tz)
                next_day_local = local.replace(hour=0, minute=0, second=0, microsecond=0) + _td(days=1)
                next_allowed_time = next_day_local
            continue

        trade = simulate_trade_from_analysis(
            request=request,
            analysis=analysis,
            scenario=scenario,
            entry_candle=candle,
            future_candles=_future_execution_candles(candles_by_timeframe, candle.time),
        )
        if trade is None:
            skip_funnel_key, skip_message = trade_plan_skip_reason(scenario)
            funnel[skip_funnel_key] += 1
            skipped.append(
                _skip(
                    candle.time,
                    "invalid_trade_plan",
                    skip_message,
                    build_skip_debug(analysis, scenario),
                )
            )
            continue

        trades.append(trade)
        funnel["trade_opened"] += 1
        balance += (balance * request.risk_percent / 100.0) * trade.result_r
        equity_curve.append(
            {
                "time": trade.exit_time or trade.entry_time,
                "balance": round(balance, 2),
                "cumulative_r": round(sum(item.result_r for item in trades), 4),
                "drawdown_r": round(_current_drawdown([item.result_r for item in trades]), 4),
            }
        )
        closed_for_guard.insert(
            0,
            {
                "result_r": trade.result_r,
                "result_pct": trade.result_r * request.risk_percent,
                "closed_at": trade.exit_time,
                "exit_reason": trade.result,
                "symbol": trade.symbol,
                "direction": trade.side,
            },
        )
        next_allowed_time = _parse_time(trade.exit_time) if trade.exit_time else candle.time

    progress(92, "Đang tổng hợp kết quả backtest...")
    summary = summarize_backtest_trades(trades)
    diagnostics = {
        "data_range": {
            "start": request.start.isoformat(),
            "end": request.end.isoformat(),
        },
        "snapshots_evaluated": snapshots_evaluated,
        "setups_detected": setups_detected,
        "trades_opened": len(trades),
        "trades_skipped": len(skipped),
        "blocked_by_gate": blocked_by_gate,
        "gate_funnel": funnel,
        "account_guard": {
            "enabled": request.account_guard_enabled,
            "max_daily_loss_pct": request.max_daily_loss_pct,
            "max_weekly_loss_pct": request.max_weekly_loss_pct,
            "max_consecutive_losses": request.max_consecutive_losses,
            "max_open_risk_pct": request.max_open_risk_pct,
        },
        "analysis_errors": analysis_errors,
        "step_timeframe": request.step_timeframe,
        "execution_timeframe": "M15" if m15_all else "H1",
        "pipeline_stats": pipeline_stats,
        "gate_fail_counts": gate_fail_counts,
        "score_below_50_count": score_fail_count,
    }
    return BacktestResult(
        request=request,
        summary=summary,
        trades=trades,
        equity_curve=equity_curve,
        breakdowns=build_breakdowns(trades),
        skipped_setups=skipped,
        diagnostics=diagnostics,
    )


def validate_backtest_input(request: BacktestRequest, candles_by_timeframe: dict[str, list[Candle]]) -> None:
    if request.end <= request.start:
        raise ValueError("Ngày kết thúc backtest phải sau ngày bắt đầu.")
    if request.initial_balance <= 0:
        raise ValueError("Số dư ban đầu phải lớn hơn 0.")
    if request.risk_percent <= 0:
        raise ValueError("Risk percent phải lớn hơn 0.")
    for timeframe in ("D1", "H4", "H1"):
        if not candles_by_timeframe.get(timeframe):
            raise ValueError(f"Thiếu dữ liệu {timeframe} cho backtest.")


def slice_candles_until(
    candles_by_timeframe: dict[str, list[Candle]],
    moment: datetime,
) -> dict[str, list[Candle]]:
    return {
        timeframe: [candle for candle in candles if candle.time <= moment]
        for timeframe, candles in candles_by_timeframe.items()
    }


def has_minimum_analysis_data(snapshot: dict[str, list[Candle]]) -> bool:
    return (
        len(snapshot.get("D1", [])) >= 60
        and len(snapshot.get("H4", [])) >= 60
        and len(snapshot.get("H1", [])) >= 30
    )


def select_trade_scenario(analysis: dict[str, Any]) -> dict[str, Any] | None:
    summary = analysis.get("decision_summary", {}) if isinstance(analysis.get("decision_summary"), dict) else {}
    best_side = summary.get("best_side") or summary.get("best_scenario")
    scenarios = analysis.get("scenarios", [])
    if not isinstance(scenarios, list):
        return None
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("type") == best_side:
            return scenario
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("type") in {"buy", "sell"}:
            return scenario
    return None


def build_fallback_scenario(analysis: dict[str, Any], candle: Any) -> dict[str, Any] | None:
    """Synthetic scenario when analysis engine produces no tradeable plan.

    Uses current price + ATR to construct entry zone, SL, TP.
    Only used in backtest when the normal analysis pipeline is too conservative
    (e.g. support/resistance zones too far from price, M15 insufficient).
    """
    summary = analysis.get("decision_summary", {}) if isinstance(analysis.get("decision_summary"), dict) else {}
    best_side = summary.get("best_side") or summary.get("best_scenario")
    if best_side not in ("buy", "sell"):
        return None

    try:
        price = float(candle.close)
    except (TypeError, ValueError, AttributeError):
        return None

    technical = analysis.get("technical", {}) if isinstance(analysis.get("technical"), dict) else {}
    atr = float(technical.get("atr_h4") or technical.get("atr_d1") or 0)
    if atr <= 0:
        atr = price * 0.003  # fallback ~0.3% of price

    market_regime = analysis.get("market_regime", {}) if isinstance(analysis.get("market_regime"), dict) else {}
    regime_primary = market_regime.get("primary", "unknown") if isinstance(market_regime, dict) else "unknown"

    # Build zone / SL / TP from ATR
    zone_half = atr * 0.25
    entry_low = price - zone_half
    entry_high = price + zone_half

    if best_side == "buy":
        stop_loss = price - atr * 1.2
        take_profit = price + atr * 2.4  # 1:2 RR
    else:
        stop_loss = price + atr * 1.2
        take_profit = price - atr * 2.4

    # Guard: ensure SL and TP are on the correct side of price
    if best_side == "buy" and (stop_loss >= price or take_profit <= price):
        return None
    if best_side == "sell" and (stop_loss <= price or take_profit >= price):
        return None

    return {
        "type": best_side,
        "entry_zone": [round(entry_low, 5), round(entry_high, 5)],
        "stop_loss": round(stop_loss, 5),
        "take_profit": [round(take_profit, 5)],
        "entry_status": "watch_zone",
        "m15_quality": None,
        "expected_effective_rr": 1.5,
        "entry_zone_score": 50,
        "entry_zone_source": "fallback",
        "ready_to_trade": False,
        "_fallback": True,
        "_regime": regime_primary,
    }


def should_open_trade(analysis: dict[str, Any], scenario: dict[str, Any], min_final_score: int = 0) -> bool:
    return trade_open_block_reason(analysis, scenario, min_final_score) is None


def trade_open_block_reason(analysis: dict[str, Any], scenario: dict[str, Any], min_final_score: int = 0) -> str | None:
    """Standard backtest entry filter — single unified logic.

    Pipeline: trade_gate.allowed → permission allowed/caution →
    decision READY_TO_TRADE/WAITING_CONFIRMATION/AGGRESSIVE_SETUP/WATCH_ONLY →
    entry confirmed/waiting/watch_zone → optional min_score filter.
    """
    trade_permission = analysis.get("trade_permission", {}) if isinstance(analysis.get("trade_permission"), dict) else {}
    gate = analysis.get("trade_gate", {}) if isinstance(analysis.get("trade_gate"), dict) else {}
    decision_engine = analysis.get("decision_engine", {}) if isinstance(analysis.get("decision_engine"), dict) else {}

    if gate.get("allowed") is not True:
        return "blocked_by_trade_gate"

    permission_status = trade_permission.get("status")
    if permission_status not in {"allowed", "caution"}:
        return "blocked_by_permission"

    decision = decision_engine.get("decision")
    if decision not in {"READY_TO_TRADE", "WAITING_CONFIRMATION", "AGGRESSIVE_SETUP", "WATCH_ONLY"}:
        return "blocked_by_decision"

    if scenario.get("entry_status") not in {"confirmed_entry", "waiting_confirmation", "watch_zone"}:
        return "blocked_by_entry_status"

    if min_final_score > 0 and _safe_int(analysis.get("final_score")) is not None:
        if int(analysis.get("final_score") or 0) < min_final_score:
            return "blocked_by_score"

    return None


def _scenario_signal_score(analysis: dict[str, Any], scenario: dict[str, Any]) -> int | None:
    scores = analysis.get("scenario_scores", {}) if isinstance(analysis.get("scenario_scores"), dict) else {}
    side = str(scenario.get("type") or "")
    side_scores = scores.get(side, {}) if isinstance(scores.get(side), dict) else {}
    return _safe_int(side_scores.get("signal_score", side_scores.get("total")))


def simulate_trade_from_analysis(
    *,
    request: BacktestRequest,
    analysis: dict[str, Any],
    scenario: dict[str, Any],
    entry_candle: Candle,
    future_candles: list[Candle],
) -> BacktestTrade | None:
    side = str(scenario.get("type") or "")
    if side not in {"buy", "sell"}:
        return None
    try:
        stop_loss = float(scenario["stop_loss"])
        take_profit_raw = scenario.get("take_profit")
        take_profit = float(take_profit_raw[0] if isinstance(take_profit_raw, list) else take_profit_raw)
    except (KeyError, TypeError, ValueError):
        return None

    entry_fill = find_entry_fill(
        side=side,
        scenario=scenario,
        future_candles=future_candles,
        setup_expiry_bars=request.setup_expiry_bars,
        request=request,
    )
    if entry_fill is None:
        return None
    fill_candle, entry_price, fill_index = entry_fill
    if abs(entry_price - stop_loss) <= 0:
        return None

    exit_time, exit_price, outcome, holding_bars = resolve_exit(
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        future_candles=future_candles[fill_index:],
        max_holding_bars=request.max_holding_bars,
        conservative_same_bar=request.conservative_same_bar,
    )
    result = result_r(side, entry_price, stop_loss, exit_price) if exit_price is not None else 0.0
    return build_trade_record(
        request=request,
        analysis=analysis,
        scenario=scenario,
        side=side,
        decision=str((analysis.get("decision_engine") or {}).get("decision", "")),
        entry_candle=fill_candle,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        exit_time=exit_time,
        exit_price=exit_price,
        outcome=outcome,
        result_value=result,
        holding_bars=holding_bars,
    )


def find_entry_fill(
    *,
    side: str,
    scenario: dict[str, Any],
    future_candles: list[Candle],
    setup_expiry_bars: int,
    request: BacktestRequest,
) -> tuple[Candle, float, int] | None:
    """Tim diem vao lenh trong cac nen tuong lai.

    Yeu cau xac nhan dao chieu tai zone:
    - Buy: nen chạm zone VA close > zone_low (áp lực mua đẩy giá lên)
    - Sell: nen chạm zone VA close < zone_high (áp lực bán đẩy giá xuống)
    Fill tại close thay vì biên xấu nhất của zone.
    """
    zone = _entry_zone_bounds(scenario.get("entry_zone"))
    if zone is None:
        return None
    zone_low, zone_high = zone
    for index, candle in enumerate(future_candles[: max(1, setup_expiry_bars)]):
        if not _candle_touches_zone(candle, zone_low, zone_high):
            continue
        if side == "buy":
            if candle.close > zone_low:
                return candle, _entry_price_with_costs(side, candle.close, request), index
        else:
            if candle.close < zone_high:
                return candle, _entry_price_with_costs(side, candle.close, request), index
    return None


def trade_plan_skip_reason(scenario: dict[str, Any]) -> tuple[str, str]:
    if _entry_zone_bounds(scenario.get("entry_zone")) is None:
        return "invalid_trade_plan", "Thiếu entry zone hợp lệ."
    try:
        float(scenario["stop_loss"])
        take_profit_raw = scenario.get("take_profit")
        float(take_profit_raw[0] if isinstance(take_profit_raw, list) else take_profit_raw)
    except (KeyError, TypeError, ValueError):
        return "invalid_trade_plan", "Thiếu SL/TP hợp lệ."
    return "entry_zone_not_touched", "Giá M15 chưa chạm entry zone trong thời hạn setup."


def trade_plan_skip_message(scenario: dict[str, Any]) -> str:
    return trade_plan_skip_reason(scenario)[1]


def _entry_zone_bounds(value: object) -> tuple[float, float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        first = float(value[0])
        second = float(value[1])
    except (TypeError, ValueError):
        return None
    return min(first, second), max(first, second)


def _candle_touches_zone(candle: Candle, zone_low: float, zone_high: float) -> bool:
    return candle.low <= zone_high and candle.high >= zone_low


def resolve_exit(
    *,
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    future_candles: list[Candle],
    max_holding_bars: int,
    conservative_same_bar: bool = True,
) -> tuple[str | None, float | None, str, int]:
    selected = future_candles[: max(1, max_holding_bars)]
    if not selected:
        return None, None, "open", 0
    for index, candle in enumerate(selected, start=1):
        if side == "buy":
            stop_hit = candle.low <= stop_loss
            target_hit = candle.high >= take_profit
        else:
            stop_hit = candle.high >= stop_loss
            target_hit = candle.low <= take_profit
        if stop_hit and target_hit:
            if conservative_same_bar:
                return candle.time.isoformat(), stop_loss, "loss", index
            return candle.time.isoformat(), take_profit, "win", index
        if stop_hit:
            return candle.time.isoformat(), stop_loss, "loss", index
        if target_hit:
            return candle.time.isoformat(), take_profit, "win", index
    last = selected[-1]
    return last.time.isoformat(), last.close, "expired", len(selected)


def result_r(side: str, entry_price: float, stop_loss: float, exit_price: float | None) -> float:
    if exit_price is None:
        return 0.0
    risk = abs(entry_price - stop_loss)
    if risk <= 0:
        return 0.0
    if side == "buy":
        return round((exit_price - entry_price) / risk, 4)
    return round((entry_price - exit_price) / risk, 4)


def summarize_backtest_trades(trades: list[BacktestTrade]) -> dict[str, Any]:
    results = [trade.result_r for trade in trades]
    wins = [value for value in results if value > 0]
    losses = [value for value in results if value < 0]
    breakeven = [value for value in results if value == 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakeven),
        "expired": sum(1 for trade in trades if trade.result == "expired"),
        "win_rate": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "loss_rate": round(len(losses) / len(trades) * 100, 2) if trades else 0.0,
        "total_r": round(sum(results), 4) if results else 0.0,
        "average_r": round(sum(results) / len(results), 4) if results else 0.0,
        "median_r": round(median(results), 4) if results else 0.0,
        "expectancy_r": round(sum(results) / len(results), 4) if results else 0.0,
        "average_win_r": round(sum(wins) / len(wins), 4) if wins else 0.0,
        "average_loss_r": round(sum(losses) / len(losses), 4) if losses else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 4) if gross_loss > 0 else (round(gross_profit, 4) if gross_profit > 0 else 0.0),
        "max_drawdown_r": round(max_drawdown(results), 4),
        "max_consecutive_losses": max_consecutive(trades, "loss"),
        "max_consecutive_wins": max_consecutive(trades, "win"),
        "average_holding_bars": round(sum(trade.holding_bars for trade in trades) / len(trades), 2) if trades else 0.0,
    }


def build_breakdowns(trades: list[BacktestTrade]) -> dict[str, Any]:
    return {
        "by_symbol": breakdown_by(trades, lambda trade: trade.symbol),
        "by_side": breakdown_by(trades, lambda trade: trade.side),
        "by_decision": breakdown_by(trades, lambda trade: trade.decision or "unknown"),
        "by_score_bucket": breakdown_by(trades, lambda trade: score_bucket(trade.signal_score)),
        "by_final_score_bucket": breakdown_by(trades, lambda trade: score_bucket(trade.final_score)),
        "by_m15_quality": breakdown_by(trades, lambda trade: trade.m15_quality or "missing"),
        "by_market_regime": breakdown_by(trades, lambda trade: trade.market_regime or "unknown"),
        "by_smc_zone_score": breakdown_by(trades, lambda trade: zone_score_bucket(trade.selected_zone_score)),
        "by_entry_zone_score": breakdown_by(trades, lambda trade: zone_score_bucket(trade.entry_zone_score)),
        "by_liquidity_sweep": breakdown_by(trades, lambda trade: str(bool(trade.liquidity_sweep_aligned))),
        "by_displacement": breakdown_by(trades, lambda trade: str(bool(trade.displacement_aligned))),
        "by_choch_against": breakdown_by(trades, lambda trade: str(bool(trade.choch_against_direction))),
        "by_expected_effective_rr": breakdown_by(trades, lambda trade: rr_bucket(trade.expected_effective_rr)),
    }


def breakdown_by(trades: list[BacktestTrade], key_fn: Callable[[BacktestTrade], str]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[BacktestTrade]] = {}
    for trade in trades:
        groups.setdefault(key_fn(trade), []).append(trade)
    return {key: summarize_backtest_trades(rows) for key, rows in sorted(groups.items())}


def score_bucket(score: int | float | None) -> str:
    value = int(score or 0)
    if value < 50:
        return "<50"
    if value >= 90:
        return "90-100"
    low = (value // 10) * 10
    return f"{low}-{low + 9}"


def zone_score_bucket(score: int | None) -> str:
    if score is None:
        return "no_selected_zone"
    if score >= 75:
        return ">=75"
    if score >= 55:
        return "55-74"
    return "<55"


def rr_bucket(value: float | None) -> str:
    if value is None:
        return "missing"
    if value < 1.0:
        return "<1.0"
    if value < 1.3:
        return "1.0-1.29"
    if value < 1.5:
        return "1.3-1.49"
    if value < 2.0:
        return "1.5-1.99"
    return ">=2.0"


def max_drawdown(results: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for value in results:
        equity += value
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def max_consecutive(trades: list[BacktestTrade], result_name: str) -> int:
    best = 0
    current = 0
    for trade in trades:
        if trade.result == result_name:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def build_trade_record(
    *,
    request: BacktestRequest,
    analysis: dict[str, Any],
    scenario: dict[str, Any],
    side: str,
    decision: str,
    entry_candle: Candle,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    exit_time: str | None,
    exit_price: float | None,
    outcome: str,
    result_value: float,
    holding_bars: int,
) -> BacktestTrade:
    scores = analysis.get("scenario_scores", {}) if isinstance(analysis.get("scenario_scores"), dict) else {}
    side_score = scores.get(side, {}) if isinstance(scores.get(side), dict) else {}
    decision_summary = analysis.get("decision_summary", {}) if isinstance(analysis.get("decision_summary"), dict) else {}
    market_regime = analysis.get("market_regime", {}) if isinstance(analysis.get("market_regime"), dict) else {}
    smc_flags = analysis.get("smc_trade_flags", {}) if isinstance(analysis.get("smc_trade_flags"), dict) else {}
    return BacktestTrade(
        symbol=request.symbol,
        side=side,
        decision=decision,
        entry_time=entry_candle.time.isoformat(),
        exit_time=exit_time,
        entry_price=round(entry_price, 5),
        stop_loss=round(stop_loss, 5),
        take_profit=round(take_profit, 5),
        exit_price=round(exit_price, 5) if exit_price is not None else None,
        result=outcome,
        result_r=round(result_value, 4),
        holding_bars=holding_bars,
        final_score=int(analysis.get("final_score", 0) or 0),
        signal_score=int(side_score.get("signal_score", side_score.get("total", 0)) or 0),
        buy_score=int((scores.get("buy", {}) or {}).get("signal_score", (scores.get("buy", {}) or {}).get("total", 0)) or 0),
        sell_score=int((scores.get("sell", {}) or {}).get("signal_score", (scores.get("sell", {}) or {}).get("total", 0)) or 0),
        score_gap=float(decision_summary.get("score_gap", 0) or 0),
        market_regime=str(market_regime.get("primary", "unknown")),
        entry_status=str(scenario.get("entry_status", "unknown")),
        m15_quality=scenario.get("m15_quality"),
        expected_effective_rr=optional_float(scenario.get("expected_effective_rr")),
        selected_zone_score=_safe_int(smc_flags.get("selected_zone_score")),
        selected_zone_type=smc_flags.get("selected_zone_type"),
        entry_zone_score=_safe_int(scenario.get("entry_zone_score")),
        entry_zone_source=scenario.get("entry_zone_source"),
        liquidity_sweep_aligned=bool(smc_flags.get("liquidity_sweep_aligned")),
        displacement_aligned=bool(smc_flags.get("displacement_aligned")),
        choch_against_direction=bool(smc_flags.get("choch_against_direction")),
        reason_codes=list(analysis.get("reason_codes", []) or []),
        warning_codes=list(analysis.get("warning_codes", []) or []),
        block_codes=list(analysis.get("block_codes", []) or []),
        analysis_snapshot=analysis if request.store_analysis_snapshots else None,
    )


def _run_analysis_snapshot(
    request: BacktestRequest,
    snapshot: dict[str, list[Candle]],
    balance: float,
    closed_trades: list[dict[str, Any]],
    current_time: datetime,
    analysis_fn: AnalysisFn,
) -> dict[str, Any]:
    analysis_input = AnalysisInput(
        symbol=request.symbol,
        broker_symbol=request.broker_symbol,
        account_balance=balance,
        risk_percent=request.risk_percent,
        account_currency=request.account_currency,
        lot_step=request.lot_step,
        minimum_lot=request.minimum_lot,
        contract_size_override=request.contract_size_override,
        timezone_name=request.timezone_name,
    )
    data_quality = {
        "price_source": "BACKTEST",
        "terminal_connected": True,
        "broker_logged_in": True,
        "display_symbol": request.symbol,
        "broker_symbol": request.broker_symbol,
        "spread_points": request.spread_price,
        "spread_status": "normal",
        "warning": None,
        "news_in_3h": False,
        "high_impact_event_within_30m": False,
    }
    macro_alignment = (
        request.macro_alignment_override if request.allow_macro and request.macro_alignment_override
        else None if request.allow_macro
        else {"buy": 15, "sell": 15}
    )
    correlation_context = request.correlation_context if request.allow_macro else None
    return analysis_fn(
        analysis_input,
        {"D1": snapshot["D1"], "H4": snapshot["H4"], "H1": snapshot["H1"]},
        data_quality=data_quality,
        macro_alignment=macro_alignment,
        macro_confidence=1.0,
        ai_commentary=None,
        ai_meta=None,
        m15_candles=snapshot.get("M15"),
        correlation_context=correlation_context,
        quote_to_usd_rate=1.0,
        closed_trades=_closed_trades_for_guard(request, closed_trades),
        open_trades=[],
        account_guard_settings=_account_guard_settings(request),
        trade_date=current_time,
    )


def _closed_trades_for_guard(request: BacktestRequest, closed_trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return closed_trades if request.account_guard_enabled else []


def _account_guard_settings(request: BacktestRequest) -> dict[str, Any]:
    return {
        "max_daily_loss_pct": float(request.max_daily_loss_pct),
        "max_weekly_loss_pct": float(request.max_weekly_loss_pct),
        "max_consecutive_losses": int(request.max_consecutive_losses),
        "max_open_risk_pct": float(request.max_open_risk_pct),
        "trader_timezone": request.timezone_name,
    }


def _future_execution_candles(candles_by_timeframe: dict[str, list[Candle]], moment: datetime) -> list[Candle]:
    execution = candles_by_timeframe.get("M15") or candles_by_timeframe.get("H1", [])
    return [candle for candle in execution if candle.time > moment]


def _entry_price_with_costs(side: str, close: float, request: BacktestRequest) -> float:
    cost = max(0.0, float(request.spread_price or 0.0)) + max(0.0, float(request.slippage_price or 0.0))
    if side == "buy":
        return close + cost
    return close - cost


def _gate_blocked(analysis: dict[str, Any]) -> bool:
    gate = analysis.get("trade_gate", {}) if isinstance(analysis.get("trade_gate"), dict) else {}
    return gate.get("allowed") is False


def _is_account_guard_block(analysis: dict[str, Any]) -> bool:
    """Check if the gate block was triggered by account guard limits."""
    gate = analysis.get("trade_gate", {}) if isinstance(analysis.get("trade_gate"), dict) else {}
    if gate.get("allowed") is not False:
        return False
    block_codes = gate.get("block_codes", [])
    if not isinstance(block_codes, list):
        return False
    from core.reason_codes import DAILY_LOSS_LIMIT_REACHED, WEEKLY_LOSS_LIMIT_REACHED, MAX_CONSECUTIVE_LOSSES_REACHED
    return bool(
        set(block_codes) & {DAILY_LOSS_LIMIT_REACHED, WEEKLY_LOSS_LIMIT_REACHED, MAX_CONSECUTIVE_LOSSES_REACHED}
    )


def _skip_reason(analysis: dict[str, Any], scenario: dict[str, Any], block_reason: str | None = None) -> str:
    reason_labels = {
        "blocked_by_trade_gate": "Gate hoặc trade_permission chặn giao dịch.",
        "blocked_by_permission": "Trade permission chưa cho phép giao dịch.",
        "blocked_by_decision": "Decision chưa đạt ngưỡng mở lệnh.",
        "blocked_by_score": "Final score chưa đạt ngưỡng tối thiểu.",
        "blocked_by_entry_status": "Entry status chưa đạt yêu cầu.",
        "blocked_by_m15": "M15 quality chưa đạt yêu cầu.",
        "blocked_by_rr": "Expected RR chưa đạt yêu cầu.",
    }
    if block_reason in reason_labels:
        return reason_labels[block_reason]
    decision = analysis.get("decision_engine", {}) if isinstance(analysis.get("decision_engine"), dict) else {}
    gate = analysis.get("trade_gate", {}) if isinstance(analysis.get("trade_gate"), dict) else {}
    return str(
        decision.get("reason")
        or "; ".join(gate.get("reasons", []) or [])
        or scenario.get("invalid_reason")
        or "Setup chưa đạt điều kiện vào lệnh."
    )


def build_skip_debug(analysis: dict[str, Any] | None, scenario: dict[str, Any] | None) -> dict[str, Any]:
    """Build compact numeric/debug context for skipped setups.

    This intentionally avoids storing the full analysis payload by default.
    Full snapshots can be very large in multi-month backtests.
    """
    analysis = analysis if isinstance(analysis, dict) else {}
    scenario = scenario if isinstance(scenario, dict) else {}
    scores = analysis.get("scenario_scores", {}) if isinstance(analysis.get("scenario_scores"), dict) else {}
    decision_summary = analysis.get("decision_summary", {}) if isinstance(analysis.get("decision_summary"), dict) else {}
    decision_engine = analysis.get("decision_engine", {}) if isinstance(analysis.get("decision_engine"), dict) else {}
    trade_gate = analysis.get("trade_gate", {}) if isinstance(analysis.get("trade_gate"), dict) else {}
    trade_permission = analysis.get("trade_permission", {}) if isinstance(analysis.get("trade_permission"), dict) else {}
    smc_flags = analysis.get("smc_trade_flags", {}) if isinstance(analysis.get("smc_trade_flags"), dict) else {}
    market_regime = analysis.get("market_regime", {}) if isinstance(analysis.get("market_regime"), dict) else {}
    best_side = str(decision_summary.get("best_side") or decision_summary.get("best_scenario") or scenario.get("type") or "")
    side_scores = scores.get(best_side, {}) if isinstance(scores.get(best_side), dict) else {}
    buy_scores = scores.get("buy", {}) if isinstance(scores.get("buy"), dict) else {}
    sell_scores = scores.get("sell", {}) if isinstance(scores.get("sell"), dict) else {}
    gate_reasons = trade_gate.get("reasons", []) if isinstance(trade_gate.get("reasons"), list) else []

    return {
        "decision": decision_engine.get("decision"),
        "legacy_action": decision_engine.get("legacy_action") or decision_summary.get("action"),
        "decision_reason": decision_engine.get("reason"),
        "final_score": _safe_int(analysis.get("final_score")),
        "signal_score": _safe_int(side_scores.get("signal_score", side_scores.get("total"))),
        "buy_score": _safe_int(buy_scores.get("signal_score", buy_scores.get("total"))),
        "sell_score": _safe_int(sell_scores.get("signal_score", sell_scores.get("total"))),
        "score_gap": optional_float(decision_summary.get("score_gap")),
        "best_side": best_side or None,
        "trade_permission": trade_permission.get("status"),
        "gate_allowed": trade_gate.get("allowed"),
        "gate_cap": trade_gate.get("decision_cap"),
        "gate_reasons": gate_reasons[:3],
        "entry_status": scenario.get("entry_status"),
        "ready_to_trade": scenario.get("ready_to_trade"),
        "trigger_type": scenario.get("trigger_type"),
        "m15_quality": scenario.get("m15_quality"),
        "m15_available": scenario.get("m15_available"),
        "expected_effective_rr": optional_float(scenario.get("expected_effective_rr")),
        "risk_reward": scenario.get("risk_reward"),
        "market_regime": market_regime.get("primary"),
        "selected_zone_score": _safe_int(smc_flags.get("selected_zone_score")),
        "selected_zone_type": smc_flags.get("selected_zone_type"),
        "entry_zone_score": _safe_int(scenario.get("entry_zone_score")),
        "entry_zone_source": scenario.get("entry_zone_source"),
        "liquidity_sweep_aligned": bool(smc_flags.get("liquidity_sweep_aligned")),
        "displacement_aligned": bool(smc_flags.get("displacement_aligned")),
        "choch_against_direction": bool(smc_flags.get("choch_against_direction")),
        "reason_codes": list(analysis.get("reason_codes", []) or [])[:8],
        "warning_codes": list(analysis.get("warning_codes", []) or [])[:8],
        "block_codes": list(analysis.get("block_codes", []) or [])[:8],
    }


def _skip(moment: datetime, reason: str, message: str, debug: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"time": moment.isoformat(), "reason": reason, "message": message}
    if debug:
        payload["debug"] = debug
    return payload


def _request_to_dict(request: BacktestRequest) -> dict[str, Any]:
    data = asdict(request)
    data["start"] = request.start.isoformat()
    data["end"] = request.end.isoformat()
    data["correlation_context"] = _serialize_correlation_context(request.correlation_context)
    return data


def _serialize_correlation_context(value: object) -> object:
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, list):
            result[key] = [
                {
                    "time": candle.time.isoformat(),
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                }
                if isinstance(candle, Candle)
                else candle
                for candle in item
            ]
        else:
            result[key] = item
    return result


def _current_drawdown(results: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    current_dd = 0.0
    for value in results:
        equity += value
        peak = max(peak, equity)
        current_dd = peak - equity
    return current_dd


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _aggregate_pipeline_diag(
    analysis: dict[str, Any],
    pipeline_stats: dict[str, dict[str, int]],
    gate_fail_counts: dict[str, int],
) -> None:
    """Aggregate pipeline diagnostics from one analysis snapshot into running totals."""
    diags = analysis.get("pipeline_diagnostics")
    if not isinstance(diags, list):
        return
    for entry in diags:
        if not isinstance(entry, dict):
            continue
        step = str(entry.get("step", "unknown"))
        status = str(entry.get("status", "pass"))
        if step not in pipeline_stats:
            pipeline_stats[step] = {"pass": 0, "fail": 0, "warning": 0}
        pipeline_stats[step][status] = pipeline_stats[step].get(status, 0) + 1

        # Count per-gate failures from ALL gate steps (not just failed ones)
        if step == "gate":
            details = entry.get("details", {}) if isinstance(entry.get("details"), dict) else {}
            for gc in details.get("gate_checks", []) or []:
                if isinstance(gc, dict) and gc.get("status") in ("block", "warning"):
                    gate_name = str(gc.get("gate", "?"))
                    gate_fail_counts[gate_name] = gate_fail_counts.get(gate_name, 0) + 1
