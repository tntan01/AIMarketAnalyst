from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone, timedelta
from statistics import median
from typing import Any

from core.analysis_engine import analyze_symbol
from core.backtest_contract import (
    BACKTEST_PURPOSE_VALIDATION,
    BACKTEST_PURPOSE_RESEARCH,
    VALID_BACKTEST_PURPOSES,
    build_runtime_backtest_contract,
    normalize_backtest_purpose,
)
from core.backtest_market_data import (
    DataManifest,
    candle_close_time,
    closed_candle_snapshot,
    execution_candles_in_interval,
    in_half_open_interval,
    normalize_candle_series,
    normalize_utc,
    prepare_backtest_data,
    timeframe_duration,
    validation_quality_errors,
)
from core.backtest_candidate_ledger import (
    CANDIDATE_LEDGER_VERSION,
    CANDIDATE_REPLAY_VERSION,
    CandidateLedgerEntry,
    FrozenStrategyConfig,
    build_candidate_ledger_entry,
    candidate_ledger_fingerprint,
    evaluate_frozen_strategy,
    side_setup_score,
)
from core.backtest_execution import (
    BACKTEST_EXECUTION_POLICY_VERSION,
    ENTRY_FILL_MODEL,
    EXIT_EVALUATION_MODEL,
    SAME_BAR_STOP_FIRST,
    SAME_BAR_TARGET_FIRST,
    build_execution_events,
    find_confirmation_close_fill,
    resolve_post_fill_exit,
    valid_trade_geometry,
)
from core.backtest_execution_parity import (
    DEFAULT_SESSION_SPREAD_MULTIPLIERS,
    EXECUTION_COST_MODEL_VERSION,
    EXECUTION_MODE_PARITY,
    EXECUTION_MODE_RESEARCH,
    EXECUTION_PARITY_MODEL_VERSION,
    QUOTE_CONVERSION_MODEL_VERSION,
    VALID_EXECUTION_MODES,
    apply_execution_costs,
    cost_model_fingerprint,
    cost_model_manifest,
    normalize_execution_mode,
    quote_rate_at,
    quote_conversion_fingerprint,
    session_spread_price,
)
from core.market_models import Candle
from core.risk_engine import AnalysisInput, REGIME_TP_FALLBACK_MULT
from core.safe_types import optional_float
from core.risk_parameter_context import (
    RiskParameterOverrides,
    risk_parameter_scope,
)


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
    "blocked_by_frozen_strategy",
    "entry_zone_not_touched",
    "invalid_trade_plan",
    "trade_opened",
)

SIMULATION_REJECTION_REASON_KEY = "simulation_rejection_reason"
SIMULATION_REJECTION_DETAIL_KEY = "simulation_rejection_detail"
INVALID_SIDE = "INVALID_SIDE"
VALIDATION_RESEARCH_ONLY_SCENARIO = "VALIDATION_RESEARCH_ONLY_SCENARIO"
MISSING_SL_TP = "MISSING_SL_TP"
NO_VALID_TP1 = "NO_VALID_TP1"
INVALID_ENTRY_ZONE = "INVALID_ENTRY_ZONE"
ENTRY_ZONE_NOT_TOUCHED = "ENTRY_ZONE_NOT_TOUCHED"
INVALID_TRADE_GEOMETRY = "INVALID_TRADE_GEOMETRY"
QUOTE_CONVERSION_MISSING = "QUOTE_CONVERSION_MISSING"


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
    maximum_lot: float = 100.0
    contract_size_override: float | None = None
    timezone_name: str = "Asia/Ho_Chi_Minh"
    spread_price: float = 0.0
    slippage_price: float = 0.0
    entry_slippage_price: float | None = None
    exit_slippage_price: float | None = None
    commission_per_lot_round_turn: float = 0.0
    swap_long_per_lot_day: float = 0.0
    swap_short_per_lot_day: float = 0.0
    triple_swap_weekday: int = 2
    spread_session_multipliers: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_SESSION_SPREAD_MULTIPLIERS)
    )
    cost_model_configured: bool = False
    quote_conversion_symbol: str = ""
    quote_conversion_inverted: bool = False
    quote_conversion_candles: tuple[Candle, ...] = ()
    quote_to_account_rate: float | None = None
    max_holding_bars: int = 96
    setup_expiry_bars: int = 12
    max_holding_minutes: int = 1440
    setup_expiry_minutes: int = 180
    step_timeframe: str = "H1"
    execution_timeframe: str = "M15"
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
    purpose: str = BACKTEST_PURPOSE_RESEARCH
    execution_mode: str = EXECUTION_MODE_RESEARCH
    code_revision: str = ""
    frozen_strategy_config: FrozenStrategyConfig | None = None
    candidate_ledger_enabled: bool = True
    risk_parameter_overrides: RiskParameterOverrides = field(
        default_factory=RiskParameterOverrides
    )
    max_symbol_risk_pct: float = 999.0
    max_currency_exposure_pct: float = 999.0
    max_correlated_risk_pct: float = 999.0
    max_concurrent_positions: int = 999
    # Bước 6 (Major 5): flag AI Macro Verdict. Backtest chỉ đọc cache theo
    # (pair, date, side) qua assessor read-cache-only (is_backtest=True); flag
    # này điều khiển việc Guard 1 trong pipeline có mở cửa cho verdict không.
    macro_ai_verdict_enabled: bool = False


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
    selected_zone_id: str | None = None
    selected_zone_quality_score: int | None = None
    selected_zone_relevance_score: int | None = None
    selected_zone_setup_score: int | None = None
    selected_zone_scoring_version: str | None = None
    smc_score_breakdown: dict[str, Any] = field(default_factory=dict)
    scanner_scorer_version: str | None = None
    scanner_feature_version: str | None = None
    smc_scorer_version: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    warning_codes: list[str] = field(default_factory=list)
    block_codes: list[str] = field(default_factory=list)
    analysis_snapshot: dict[str, Any] | None = None
    execution_policy_version: str = BACKTEST_EXECUTION_POLICY_VERSION
    execution_timeframe: str = "M15"
    scenario_source: str = "pipeline"
    research_only: bool = False
    execution_events: list[dict[str, Any]] = field(default_factory=list)
    execution_mode: str = EXECUTION_MODE_RESEARCH
    execution_model_version: str = BACKTEST_EXECUTION_POLICY_VERSION
    cost_model_version: str = ""
    quote_conversion_model_version: str = ""
    raw_entry_price: float | None = None
    raw_exit_price: float | None = None
    gross_r: float = 0.0
    cost_r: float = 0.0
    net_r: float = 0.0
    gross_pnl_account: float = 0.0
    net_pnl_account: float = 0.0
    spread_slippage_account: float = 0.0
    commission_account: float = 0.0
    swap_account: float = 0.0
    position_lot: float = 0.0
    target_risk_account: float = 0.0
    planned_risk_account: float = 0.0
    quote_rate_entry: float = 1.0
    quote_rate_exit: float = 1.0
    execution_session: str = ""
    cost_breakdown: dict[str, Any] = field(default_factory=dict)
    setup_score: int | None = None
    candidate_id: str = ""
    frozen_config_id: str = ""


@dataclass(slots=True)
class BacktestResult:
    request: BacktestRequest
    summary: dict[str, Any]
    trades: list[BacktestTrade]
    equity_curve: list[dict[str, Any]]
    breakdowns: dict[str, Any]
    skipped_setups: list[dict[str, Any]]
    diagnostics: dict[str, Any]
    data_manifest: dict[str, Any] = field(default_factory=dict)
    candidate_ledger: list[dict[str, Any]] = field(default_factory=list)
    frozen_strategy_config: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        from core.scanner_models import (
            SCANNER_FEATURE_VERSION,
            SCANNER_SCORER_VERSION,
            SETUP_SCORE_METRIC,
        )
        from core.scoring_provenance import build_scoring_provenance
        from core.backtest_provenance import build_backtest_provenance

        provenance = build_scoring_provenance()
        parity_enabled = (
            normalize_execution_mode(self.request.execution_mode)
            == EXECUTION_MODE_PARITY
        )
        provenance.update({
            "backtest_execution_mode": normalize_execution_mode(
                self.request.execution_mode
            ),
            "backtest_execution_model_version": (
                EXECUTION_PARITY_MODEL_VERSION
                if parity_enabled
                else BACKTEST_EXECUTION_POLICY_VERSION
            ),
            "backtest_cost_model_version": (
                EXECUTION_COST_MODEL_VERSION if parity_enabled else ""
            ),
        })

        contract = build_runtime_backtest_contract(
            self.request.purpose,
            self.request.execution_mode,
        )
        contract.update({
            "execution_policy_version": (
                BACKTEST_EXECUTION_POLICY_VERSION
            ),
            "entry_fill_model": ENTRY_FILL_MODEL,
            "exit_evaluation_model": EXIT_EVALUATION_MODEL,
            "same_bar_ambiguity_policy": (
                SAME_BAR_STOP_FIRST
                if self.request.conservative_same_bar
                else SAME_BAR_TARGET_FIRST
            ),
            "execution_timeframe": self.diagnostics.get(
                "execution_timeframe",
                self.request.execution_timeframe,
            ),
            "cost_model": cost_model_manifest(self.request),
            "cost_model_fingerprint": cost_model_fingerprint(self.request),
            "quote_conversion_fingerprint": (
                quote_conversion_fingerprint(self.request)
            ),
            "frozen_strategy_applied": (
                self.request.frozen_strategy_config is not None
            ),
            "oos_replay": (
                normalize_backtest_purpose(self.request.purpose)
                == BACKTEST_PURPOSE_VALIDATION
                and self.request.frozen_strategy_config is not None
            ),
            "validation_eligible": (
                contract.get("validation_eligible") is True
                and self.request.frozen_strategy_config is not None
            ),
        })

        scoring_contract = {
            "score_metric": SETUP_SCORE_METRIC,
            "scorer_version": SCANNER_SCORER_VERSION,
            "feature_version": SCANNER_FEATURE_VERSION,
            "smc_scorer_version": provenance["smc_scorer_version"],
        }
        request_payload = _request_to_dict(self.request)
        backtest_provenance = build_backtest_provenance(
            code_revision=self.request.code_revision,
            request=request_payload,
            data_manifest=self.data_manifest,
            execution_contract=contract,
            scoring_contract=scoring_contract,
            frozen_strategy_config=self.frozen_strategy_config,
        )
        return {
            "mode": "system_backtest",
            "backtest_contract": contract,
            "scoring_provenance": provenance,
            "scoring_contract": scoring_contract,
            "backtest_provenance": backtest_provenance,
            "request": request_payload,
            "summary": self.summary,
            "trades": [asdict(trade) for trade in self.trades],
            "equity_curve": self.equity_curve,
            "breakdowns": self.breakdowns,
            "skipped_setups": self.skipped_setups,
            "diagnostics": self.diagnostics,
            "data_manifest": self.data_manifest,
            "candidate_ledger": self.candidate_ledger,
            "candidate_ledger_contract": {
                "version": CANDIDATE_LEDGER_VERSION,
                "replay_version": CANDIDATE_REPLAY_VERSION,
                "fingerprint": candidate_ledger_fingerprint(
                    self.candidate_ledger
                ),
                "candidate_count": len(self.candidate_ledger),
            },
            "frozen_strategy_config": self.frozen_strategy_config,
        }


def run_system_backtest(
    request: BacktestRequest,
    candles_by_timeframe: dict[str, list[Candle]],
    *,
    analysis_fn: AnalysisFn = analyze_symbol,
    progress_callback: Callable[[int, str], None] | None = None,
    phase_label: str = "",
) -> BacktestResult:
    normalized_candles, data_manifest = prepare_backtest_data(
        candles_by_timeframe,
        symbol=request.symbol,
        requested_start=request.start,
        requested_end=request.end,
    )
    validate_backtest_input(
        request,
        normalized_candles,
        data_manifest=data_manifest,
    )
    progress = progress_callback or (lambda _percent, _message: None)
    step_timeframe = (
        request.step_timeframe
        if normalized_candles.get(request.step_timeframe)
        else "H1"
    )
    step_candles = normalized_candles.get(step_timeframe, [])
    requested_execution_timeframe = str(
        request.execution_timeframe or "M15"
    ).upper()
    execution_timeframe = (
        requested_execution_timeframe
        if normalized_candles.get(requested_execution_timeframe)
        else "H1"
    )
    request_start = normalize_utc(request.start)[0]
    request_end = normalize_utc(request.end)[0]
    normalized_correlation_context = _normalize_correlation_context(
        request.correlation_context
    )
    trades: list[BacktestTrade] = []
    skipped: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []
    closed_for_guard: list[dict[str, Any]] = []
    candidate_ledger: list[CandidateLedgerEntry] = []
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
        (index, candle, candle_close_time(candle, step_timeframe))
        for index, candle in enumerate(step_candles)
        if in_half_open_interval(
            candle_close_time(candle, step_timeframe),
            request_start,
            request_end,
        )
    ]
    total_steps = max(1, len(eligible_steps))

    for ordinal, (_step_index, candle, decision_time) in enumerate(
        eligible_steps,
        start=1,
    ):
        if (
            next_allowed_time is not None
            and decision_time <= next_allowed_time
        ):
            continue
        percent = 10 + int(ordinal / total_steps * 75)
        gmt7 = decision_time.astimezone(timezone(timedelta(hours=7)))
        time_str = gmt7.strftime("%d/%m/%Y %H:%M")
        progress(percent, f"Đang backtest {request.symbol} tại {time_str} | {phase_label}")

        snapshot = slice_candles_until(
            normalized_candles,
            decision_time,
        )
        if not has_minimum_analysis_data(snapshot):
            skipped.append(_skip(decision_time, "insufficient_warmup", "Chưa đủ dữ liệu warmup."))
            continue

        try:
            analysis = _run_analysis_snapshot(
                request,
                snapshot,
                balance,
                closed_for_guard,
                decision_time,
                analysis_fn,
                correlation_context=normalized_correlation_context,
            )
        except Exception as exc:
            analysis_errors += 1
            skipped.append(_skip(decision_time, "analysis_error", str(exc)))
            continue

        snapshots_evaluated += 1
        funnel["snapshots_evaluated"] += 1

        # --- Aggregate pipeline diagnostics from this snapshot ---
        _aggregate_pipeline_diag(analysis, pipeline_stats, gate_fail_counts)
        if analysis.get("decision_summary", {}).get("best_score", 0) < 50:
            score_fail_count += 1

        scenario = select_trade_scenario(analysis)
        is_fallback = False
        if (
            not scenario
            and normalize_backtest_purpose(request.purpose)
            == BACKTEST_PURPOSE_RESEARCH
        ):
            scenario = build_fallback_scenario(analysis, candle)
            is_fallback = scenario is not None
        strict_execution = (
            normalize_backtest_purpose(request.purpose)
            == BACKTEST_PURPOSE_VALIDATION
        )
        base_block_reason = (
            trade_open_block_reason(
                analysis,
                scenario,
                0,
                strict_execution=strict_execution,
            )
            if scenario is not None
            else "no_trade_scenario"
        )
        ledger_block_reason = (
            trade_open_block_reason(
                analysis,
                scenario,
                0,
                strict_execution=True,
            )
            if scenario is not None
            else "no_trade_scenario"
        )
        ledger_entry = build_candidate_ledger_entry(
            symbol=request.symbol,
            decision_time=decision_time,
            analysis=analysis,
            scenario=scenario,
            base_rejection_reason=ledger_block_reason,
        )
        if request.candidate_ledger_enabled:
            candidate_ledger.append(ledger_entry)
        if not scenario:
            funnel["no_trade_scenario"] += 1
            skipped.append(
                _skip(
                    decision_time,
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
        block_reason = base_block_reason
        if block_reason is not None:
            if _gate_blocked(analysis):
                blocked_by_gate += 1
            if block_reason in funnel:
                funnel[block_reason] += 1
            skipped.append(
                _skip(
                    decision_time,
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
                local = decision_time.astimezone(tz)
                next_day_local = local.replace(hour=0, minute=0, second=0, microsecond=0) + _td(days=1)
                next_allowed_time = next_day_local
            continue

        simulation_diagnostics: dict[str, str] = {}
        trade = simulate_trade_from_analysis(
            request=request,
            analysis=analysis,
            scenario=scenario,
            entry_candle=candle,
            future_candles=_future_execution_candles(
                normalized_candles,
                decision_time,
                request_end,
                execution_timeframe=execution_timeframe,
            ),
            execution_timeframe=execution_timeframe,
            signal_time=decision_time,
            account_balance=balance,
            diagnostics=simulation_diagnostics,
        )
        if trade is None:
            ledger_entry.base_eligible = False
            ledger_entry.base_rejection_reason = "TRADE_SIMULATION_REJECTED"
            ledger_entry.simulation_rejection_reason = (
                simulation_diagnostics.get(SIMULATION_REJECTION_REASON_KEY)
            )
            detail = simulation_diagnostics.get(SIMULATION_REJECTION_DETAIL_KEY)
            ledger_entry.simulation_rejection_detail = (
                dict(detail) if isinstance(detail, dict) else None
            )
            skip_funnel_key, skip_message = trade_plan_skip_reason(scenario)
            funnel[skip_funnel_key] += 1
            skipped.append(
                _skip(
                    decision_time,
                    "invalid_trade_plan",
                    skip_message,
                    build_skip_debug(analysis, scenario),
                )
            )
            continue

        trade.candidate_id = ledger_entry.candidate_id
        ledger_entry.simulated_trade = asdict(trade)
        frozen_allowed, frozen_reasons = evaluate_frozen_strategy(
            ledger_entry,
            request.frozen_strategy_config,
        )
        if request.frozen_strategy_config is None and request.min_final_score > 0:
            if ledger_entry.setup_score is None:
                frozen_allowed = False
                frozen_reasons.append("LEGACY_SETUP_SCORE_MISSING")
            elif ledger_entry.setup_score < request.min_final_score:
                frozen_allowed = False
                frozen_reasons.append("LEGACY_SETUP_SCORE_BELOW_MIN")
        ledger_entry.frozen_config_id = (
            request.frozen_strategy_config.config_id
            if request.frozen_strategy_config is not None
            else ""
        )
        ledger_entry.strategy_eligible = frozen_allowed
        ledger_entry.strategy_rejection_reasons = list(
            dict.fromkeys(frozen_reasons)
        )
        trade.frozen_config_id = ledger_entry.frozen_config_id
        ledger_entry.simulated_trade = asdict(trade)
        if not frozen_allowed:
            funnel["blocked_by_frozen_strategy"] += 1
            skipped.append(
                _skip(
                    decision_time,
                    "blocked_by_frozen_strategy",
                    "; ".join(ledger_entry.strategy_rejection_reasons),
                    build_skip_debug(analysis, scenario),
                )
            )
            continue

        ledger_entry.executed = True
        trades.append(trade)
        funnel["trade_opened"] += 1
        balance_before_trade = balance
        if normalize_execution_mode(request.execution_mode) == EXECUTION_MODE_PARITY:
            balance += trade.net_pnl_account
        else:
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
                "result_pct": (
                    trade.net_pnl_account / balance_before_trade * 100.0
                    if balance_before_trade > 0
                    and normalize_execution_mode(request.execution_mode)
                    == EXECUTION_MODE_PARITY
                    else trade.result_r * request.risk_percent
                ),
                "closed_at": trade.exit_time,
                "exit_reason": trade.result,
                "symbol": trade.symbol,
                "direction": trade.side,
            },
        )
        next_allowed_time = (
            _parse_time(trade.exit_time)
            if trade.exit_time
            else decision_time
        )

    progress(92, f"Đang tổng hợp kết quả backtest... | {phase_label}")
    summary = summarize_backtest_trades(trades)
    diagnostics = {
        "data_range": {
            "start": request_start.isoformat(),
            "end": request_end.isoformat(),
            "interval": "[start,end)",
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
        "step_timeframe": step_timeframe,
        "execution_timeframe": execution_timeframe,
        "execution_policy": {
            "version": BACKTEST_EXECUTION_POLICY_VERSION,
            "entry_fill_model": ENTRY_FILL_MODEL,
            "exit_evaluation_model": EXIT_EVALUATION_MODEL,
            "same_bar_ambiguity_policy": (
                SAME_BAR_STOP_FIRST
                if request.conservative_same_bar
                else SAME_BAR_TARGET_FIRST
            ),
            "setup_expiry_minutes": request.setup_expiry_minutes,
            "max_holding_minutes": request.max_holding_minutes,
        },
        "execution_parity": {
            "enabled": (
                normalize_execution_mode(request.execution_mode)
                == EXECUTION_MODE_PARITY
            ),
            "mode": normalize_execution_mode(request.execution_mode),
            **cost_model_manifest(request),
        },
        "data_quality": {
            "status": data_manifest.quality_status,
            "validation_eligible": data_manifest.validation_eligible,
            "dataset_hash": data_manifest.dataset_hash,
            "issue_count": len(data_manifest.issues),
            "correlation_context_point_in_time": bool(
                request.allow_macro and normalized_correlation_context
            ),
        },
        "pipeline_stats": pipeline_stats,
        "gate_fail_counts": gate_fail_counts,
        "score_below_50_count": score_fail_count,
        "candidate_ledger": {
            "version": CANDIDATE_LEDGER_VERSION,
            "replay_version": CANDIDATE_REPLAY_VERSION,
            "candidate_count": len(candidate_ledger),
            "base_eligible_count": sum(
                1 for entry in candidate_ledger if entry.base_eligible
            ),
            "strategy_eligible_count": sum(
                1 for entry in candidate_ledger
                if entry.strategy_eligible is True
            ),
            "executed_count": sum(
                1 for entry in candidate_ledger if entry.executed
            ),
            "fingerprint": candidate_ledger_fingerprint(
                candidate_ledger
            ),
            "frozen_config_id": (
                request.frozen_strategy_config.config_id
                if request.frozen_strategy_config is not None
                else ""
            ),
        },
    }
    return BacktestResult(
        request=request,
        summary=summary,
        trades=trades,
        equity_curve=equity_curve,
        breakdowns=build_breakdowns(trades),
        skipped_setups=skipped,
        diagnostics=diagnostics,
        data_manifest=data_manifest.to_dict(),
        candidate_ledger=[entry.to_dict() for entry in candidate_ledger],
        frozen_strategy_config=(
            request.frozen_strategy_config.to_dict()
            if request.frozen_strategy_config is not None
            else None
        ),
    )


def validate_backtest_input(
    request: BacktestRequest,
    candles_by_timeframe: dict[str, list[Candle]],
    *,
    data_manifest: DataManifest | None = None,
) -> None:
    request_timezone_missing = (
        request.start.tzinfo is None
        or request.start.utcoffset() is None
        or request.end.tzinfo is None
        or request.end.utcoffset() is None
    )
    request_start = normalize_utc(request.start)[0]
    request_end = normalize_utc(request.end)[0]
    if request_end <= request_start:
        raise ValueError("Ngày kết thúc backtest phải sau ngày bắt đầu.")
    if request.initial_balance <= 0:
        raise ValueError("Số dư ban đầu phải lớn hơn 0.")
    if request.risk_percent <= 0:
        raise ValueError("Risk percent phải lớn hơn 0.")
    execution_mode = normalize_execution_mode(request.execution_mode)
    if execution_mode not in VALID_EXECUTION_MODES:
        raise ValueError(
            "Execution mode phải là RESEARCH hoặc EXECUTION_PARITY."
        )
    if request.lot_step <= 0 or request.minimum_lot <= 0:
        raise ValueError("Lot step và minimum lot phải lớn hơn 0.")
    if request.maximum_lot < request.minimum_lot:
        raise ValueError("Maximum lot phải lớn hơn hoặc bằng minimum lot.")
    if request.contract_size_override is not None and request.contract_size_override <= 0:
        raise ValueError("Contract size phải lớn hơn 0.")
    if any(
        value < 0
        for value in (
            request.spread_price,
            request.slippage_price,
            request.entry_slippage_price or 0.0,
            request.exit_slippage_price or 0.0,
            request.commission_per_lot_round_turn,
            request.swap_long_per_lot_day,
            request.swap_short_per_lot_day,
        )
    ):
        raise ValueError("Các thành phần chi phí execution không được âm.")
    if request.setup_expiry_minutes <= 0:
        raise ValueError("Thời hạn setup theo phút phải lớn hơn 0.")
    if request.max_holding_minutes <= 0:
        raise ValueError("Thời gian giữ lệnh theo phút phải lớn hơn 0.")
    if normalize_backtest_purpose(request.purpose) not in VALID_BACKTEST_PURPOSES:
        raise ValueError(
            "Mục đích backtest phải là RESEARCH hoặc VALIDATION."
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and execution_mode != EXECUTION_MODE_PARITY
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "EXECUTION_PARITY_REQUIRED."
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and request.cost_model_configured is not True
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "EXECUTION_COST_MODEL_NOT_CONFIGURED."
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and _quote_conversion_required(request)
        and not request.quote_conversion_candles
        and not request.quote_to_account_rate
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "POINT_IN_TIME_QUOTE_CONVERSION_MISSING."
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and request_timezone_missing
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "REQUEST_TIMEZONE_MISSING: start/end phải có timezone."
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and request.conservative_same_bar is not True
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "SAME_BAR_POLICY_MUST_BE_STOP_FIRST."
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and str(request.execution_timeframe or "").upper() != "M15"
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "EXECUTION_TIMEFRAME_MUST_BE_M15."
        )
    timeframe_duration(request.step_timeframe)
    timeframe_duration(request.execution_timeframe)
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and data_manifest is not None
        and not data_manifest.validation_eligible
    ):
        details = "; ".join(validation_quality_errors(data_manifest))
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: " + details
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and not candles_by_timeframe.get(
            str(request.execution_timeframe or "").upper()
        )
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "EXECUTION_TIMEFRAME_MISSING."
        )
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and request.frozen_strategy_config is None
    ):
        raise ValueError(
            "Dữ liệu không đạt chuẩn VALIDATION: "
            "FROZEN_STRATEGY_CONFIG_REQUIRED."
        )
    for timeframe in ("D1", "H4", "H1"):
        if not candles_by_timeframe.get(timeframe):
            raise ValueError(f"Thiếu dữ liệu {timeframe} cho backtest.")


def slice_candles_until(
    candles_by_timeframe: dict[str, list[Candle]],
    moment: datetime,
) -> dict[str, list[Candle]]:
    return closed_candle_snapshot(candles_by_timeframe, moment)


def has_minimum_analysis_data(snapshot: dict[str, list[Candle]]) -> bool:
    return (
        len(snapshot.get("D1", [])) >= 60
        and len(snapshot.get("H4", [])) >= 60
        and len(snapshot.get("H1", [])) >= 30
    )


def select_trade_scenario(analysis: dict[str, Any]) -> dict[str, Any] | None:
    summary = analysis.get("decision_summary", {}) if isinstance(analysis.get("decision_summary"), dict) else {}
    best_side = str(
        summary.get("best_side")
        or summary.get("best_scenario")
        or ""
    ).lower()
    scenarios = analysis.get("scenarios", [])
    if not isinstance(scenarios, list):
        return None
    if best_side not in {"buy", "sell"}:
        return None
    for scenario in scenarios:
        if (
            isinstance(scenario, dict)
            and str(scenario.get("type") or "").lower() == best_side
        ):
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

    tp_mult = REGIME_TP_FALLBACK_MULT.get(regime_primary, 2.0)
    if best_side == "buy":
        stop_loss = price - atr * 1.2
        take_profit = price + atr * 1.2 * tp_mult
    else:
        stop_loss = price + atr * 1.2
        take_profit = price - atr * 1.2 * tp_mult

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
        "synthetic": True,
        "research_only": True,
        "scenario_source": "synthetic_fallback",
        "_regime": regime_primary,
    }


def should_open_trade(analysis: dict[str, Any], scenario: dict[str, Any], min_final_score: int = 0) -> bool:
    return trade_open_block_reason(analysis, scenario, min_final_score) is None


def trade_open_block_reason(
    analysis: dict[str, Any],
    scenario: dict[str, Any],
    min_final_score: int = 0,
    *,
    strict_execution: bool = False,
) -> str | None:
    """Standard backtest entry filter — single unified logic.

    Pipeline: trade_gate.allowed → permission allowed/caution →
    decision READY_TO_TRADE/WAITING_CONFIRMATION/AGGRESSIVE_SETUP/WATCH_ONLY →
    entry confirmed/waiting/watch_zone → optional min_score filter.
    """
    trade_permission = analysis.get("trade_permission", {}) if isinstance(analysis.get("trade_permission"), dict) else {}
    gate = analysis.get("trade_gate", {}) if isinstance(analysis.get("trade_gate"), dict) else {}
    decision_engine = analysis.get("decision_engine", {}) if isinstance(analysis.get("decision_engine"), dict) else {}

    if gate.get("allowed") is not True or (
        strict_execution and gate.get("decision_cap") is not None
    ):
        return "blocked_by_trade_gate"

    permission_status = trade_permission.get("status")
    allowed_permissions = {"allowed"} if strict_execution else {"allowed", "caution"}
    if permission_status not in allowed_permissions:
        return "blocked_by_permission"

    decision = decision_engine.get("decision")
    allowed_decisions = (
        {"READY_TO_TRADE"}
        if strict_execution
        else {
            "READY_TO_TRADE",
            "WAITING_CONFIRMATION",
            "AGGRESSIVE_SETUP",
            "WATCH_ONLY",
        }
    )
    if decision not in allowed_decisions:
        return "blocked_by_decision"

    allowed_entry_statuses = (
        {"confirmed_entry"}
        if strict_execution
        else {"confirmed_entry", "waiting_confirmation", "watch_zone"}
    )
    if scenario.get("entry_status") not in allowed_entry_statuses:
        return "blocked_by_entry_status"
    if strict_execution and (
        scenario.get("ready_to_trade") is not True
        or str(scenario.get("m15_quality") or "").lower() != "strict"
    ):
        return "blocked_by_entry_status"
    journal = (
        analysis.get("journal_feedback")
        if isinstance(analysis.get("journal_feedback"), dict)
        else {}
    )
    if strict_execution and journal.get("decision_cap") in {
        "TRADE_BLOCKED",
        "WATCH_ONLY",
    }:
        return "blocked_by_permission"

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
    execution_timeframe: str = "M15",
    signal_time: datetime | None = None,
    account_balance: float | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> BacktestTrade | None:
    if diagnostics is not None:
        diagnostics.pop(SIMULATION_REJECTION_REASON_KEY, None)
        diagnostics.pop(SIMULATION_REJECTION_DETAIL_KEY, None)
    side = str(scenario.get("type") or "")
    if side not in {"buy", "sell"}:
        return _reject_trade_simulation(diagnostics, INVALID_SIDE)
    if (
        normalize_backtest_purpose(request.purpose)
        == BACKTEST_PURPOSE_VALIDATION
        and (
            scenario.get("research_only") is True
            or scenario.get("_fallback") is True
            or scenario.get("synthetic") is True
        )
    ):
        return _reject_trade_simulation(
            diagnostics,
            VALIDATION_RESEARCH_ONLY_SCENARIO,
        )
    try:
        stop_loss = float(scenario["stop_loss"])
    except (KeyError, TypeError, ValueError):
        return _reject_trade_simulation(diagnostics, MISSING_SL_TP)
    take_profit = _scenario_tp1(scenario.get("take_profit"))
    if take_profit is None:
        return _reject_trade_simulation(diagnostics, NO_VALID_TP1)

    zone = _entry_zone_bounds(scenario.get("entry_zone"))
    if zone is None:
        return _reject_trade_simulation(diagnostics, INVALID_ENTRY_ZONE)
    if signal_time is not None:
        active_at = normalize_utc(signal_time)[0]
    elif isinstance(getattr(entry_candle, "time", None), datetime):
        active_at = candle_close_time(
            entry_candle,
            request.step_timeframe,
        )
    elif future_candles:
        active_at = normalize_utc(future_candles[0].time)[0]
    else:
        return _reject_trade_simulation(diagnostics, ENTRY_ZONE_NOT_TOUCHED)
    setup_expiry = timedelta(minutes=request.setup_expiry_minutes)
    parity_enabled = (
        normalize_execution_mode(request.execution_mode)
        == EXECUTION_MODE_PARITY
    )
    entry_fill = find_confirmation_close_fill(
        side=side,
        zone_low=zone[0],
        zone_high=zone[1],
        future_candles=future_candles,
        setup_active_time=active_at,
        setup_expiry=setup_expiry,
        execution_timeframe=execution_timeframe,
        spread_price=(0.0 if parity_enabled else request.spread_price),
        slippage_price=(0.0 if parity_enabled else request.slippage_price),
    )
    if entry_fill is None:
        return _reject_trade_simulation(diagnostics, ENTRY_ZONE_NOT_TOUCHED)
    execution_entry_price = entry_fill.price
    if parity_enabled:
        entry_spread = session_spread_price(
            request.spread_price,
            entry_fill.filled_at,
            request.spread_session_multipliers,
        )[0]
        entry_slippage = (
            request.entry_slippage_price
            if request.entry_slippage_price is not None
            else request.slippage_price
        )
        execution_entry_price = (
            entry_fill.price + entry_spread + max(0.0, entry_slippage)
            if side == "buy"
            else entry_fill.price - max(0.0, entry_slippage)
        )
    if not valid_trade_geometry(
        side,
        execution_entry_price,
        stop_loss,
        take_profit,
    ):
        _set_simulation_rejection_detail(
            diagnostics,
            {
                "side": side,
                "raw_fill_price": round(entry_fill.price, 8),
                "execution_entry_price": round(execution_entry_price, 8),
                "stop_loss": round(stop_loss, 8),
                "take_profit": round(take_profit, 8),
                "entry_spread": round(entry_spread, 8) if parity_enabled else 0.0,
                "entry_slippage": (
                    round(max(0.0, entry_slippage), 8)
                    if parity_enabled
                    else round(max(0.0, request.slippage_price), 8)
                ),
                "parity_enabled": parity_enabled,
                "filled_at": entry_fill.filled_at.isoformat(),
            },
        )
        return _reject_trade_simulation(diagnostics, INVALID_TRADE_GEOMETRY)

    same_bar_policy = (
        SAME_BAR_STOP_FIRST
        if request.conservative_same_bar
        else SAME_BAR_TARGET_FIRST
    )
    exit_resolution = resolve_post_fill_exit(
        side=side,
        entry_price=execution_entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        future_candles=future_candles[entry_fill.candle_index + 1:],
        filled_at=entry_fill.filled_at,
        max_holding=timedelta(minutes=request.max_holding_minutes),
        execution_timeframe=execution_timeframe,
        same_bar_policy=same_bar_policy,
    )
    execution_costs: dict[str, Any] | None = None
    effective_entry_price = execution_entry_price
    effective_exit_price = exit_resolution.price
    if parity_enabled and exit_resolution.price is not None and exit_resolution.exited_at is not None:
        quote_rate_entry = _quote_rate_for_request(
            request,
            entry_fill.filled_at,
        )
        quote_rate_exit = _quote_rate_for_request(
            request,
            exit_resolution.exited_at,
        )
        if quote_rate_entry is None or quote_rate_exit is None:
            _set_simulation_rejection_detail(
                diagnostics,
                {
                    "quote_conversion_symbol": request.quote_conversion_symbol,
                    "quote_conversion_inverted": request.quote_conversion_inverted,
                    "entry_time": entry_fill.filled_at.isoformat(),
                    "exit_time": exit_resolution.exited_at.isoformat(),
                    "quote_rate_entry_present": quote_rate_entry is not None,
                    "quote_rate_exit_present": quote_rate_exit is not None,
                },
            )
            return _reject_trade_simulation(
                diagnostics,
                QUOTE_CONVERSION_MISSING,
            )
        contract_size = float(request.contract_size_override or 100000.0)
        parity = apply_execution_costs(
            side=side,
            raw_entry_price=entry_fill.price,
            raw_exit_price=exit_resolution.price,
            stop_loss=stop_loss,
            entry_time=entry_fill.filled_at,
            exit_time=exit_resolution.exited_at,
            balance=(
                float(account_balance)
                if account_balance is not None
                else request.initial_balance
            ),
            risk_percent=request.risk_percent,
            contract_size=contract_size,
            quote_rate_entry=quote_rate_entry,
            quote_rate_exit=quote_rate_exit,
            lot_step=request.lot_step,
            minimum_lot=request.minimum_lot,
            maximum_lot=request.maximum_lot,
            base_spread_price=request.spread_price,
            spread_session_multipliers=request.spread_session_multipliers,
            entry_slippage_price=(
                request.entry_slippage_price
                if request.entry_slippage_price is not None
                else request.slippage_price
            ),
            exit_slippage_price=(
                request.exit_slippage_price
                if request.exit_slippage_price is not None
                else request.slippage_price
            ),
            commission_per_lot_round_turn=(
                request.commission_per_lot_round_turn
            ),
            swap_long_per_lot_day=request.swap_long_per_lot_day,
            swap_short_per_lot_day=request.swap_short_per_lot_day,
            triple_swap_weekday=request.triple_swap_weekday,
        )
        effective_entry_price = parity.entry_price
        effective_exit_price = parity.exit_price
        result = parity.net_r
        execution_costs = {
            "raw_entry_price": parity.raw_entry_price,
            "raw_exit_price": parity.raw_exit_price,
            "gross_r": parity.gross_r,
            "cost_r": parity.cost_r,
            "net_r": parity.net_r,
            "gross_pnl_account": parity.gross_pnl_account,
            "net_pnl_account": parity.net_pnl_account,
            "spread_slippage_account": parity.spread_slippage_account,
            "commission_account": parity.commission_account,
            "swap_account": parity.swap_account,
            "position_lot": parity.position.lot,
            "target_risk_account": parity.position.target_risk_account,
            "planned_risk_account": parity.position.planned_risk_account,
            "quote_rate_entry": quote_rate_entry,
            "quote_rate_exit": quote_rate_exit,
            "execution_session": parity.session,
            "rollover_units": parity.rollover_units,
            "entry_spread_price": parity.entry_spread_price,
            "exit_spread_price": parity.exit_spread_price,
            "entry_slippage_price": parity.entry_slippage_price,
            "exit_slippage_price": parity.exit_slippage_price,
            "raw_lot": parity.position.raw_lot,
            "capped_by_minimum": parity.position.capped_by_minimum,
            "capped_by_maximum": parity.position.capped_by_maximum,
        }
    else:
        result = (
            result_r(
                side,
                effective_entry_price,
                stop_loss,
                effective_exit_price,
            )
            if effective_exit_price is not None
            else 0.0
        )
    events = build_execution_events(
        signal_time=active_at,
        setup_expires_at=active_at + setup_expiry,
        fill=entry_fill,
        exit_resolution=exit_resolution,
    )
    if parity_enabled:
        for event in events:
            if event.get("event") == "ENTRY_FILLED":
                event["price"] = round(effective_entry_price, 8)
            elif event.get("event") == "EXIT_FILLED":
                event["price"] = (
                    round(effective_exit_price, 8)
                    if effective_exit_price is not None
                    else None
                )
    return build_trade_record(
        request=request,
        analysis=analysis,
        scenario=scenario,
        side=side,
        decision=str((analysis.get("decision_engine") or {}).get("decision", "")),
        entry_candle=entry_fill.candle,
        entry_price=effective_entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        exit_time=(
            exit_resolution.exited_at.isoformat()
            if exit_resolution.exited_at is not None
            else None
        ),
        exit_price=effective_exit_price,
        outcome=exit_resolution.outcome,
        result_value=result,
        holding_bars=exit_resolution.holding_bars,
        entry_timeframe=execution_timeframe,
        execution_timeframe=execution_timeframe,
        execution_events=events,
        execution_costs=execution_costs,
    )


def _reject_trade_simulation(
    diagnostics: dict[str, Any] | None,
    reason: str,
) -> None:
    if diagnostics is not None:
        diagnostics[SIMULATION_REJECTION_REASON_KEY] = reason
    return None


def _set_simulation_rejection_detail(
    diagnostics: dict[str, Any] | None,
    detail: dict[str, Any],
) -> None:
    if diagnostics is not None:
        diagnostics[SIMULATION_REJECTION_DETAIL_KEY] = detail


def find_entry_fill(
    *,
    side: str,
    scenario: dict[str, Any],
    future_candles: list[Candle],
    setup_expiry_bars: int,
    request: BacktestRequest,
    setup_active_time: datetime | None = None,
    execution_timeframe: str = "M15",
    setup_expiry_minutes: int | None = None,
) -> tuple[Candle, float, int] | None:
    """Compatibility wrapper for the versioned confirmation-close policy."""
    zone = _entry_zone_bounds(scenario.get("entry_zone"))
    if zone is None or not future_candles:
        return None
    duration = timeframe_duration(execution_timeframe)
    active_at = setup_active_time or (
        normalize_utc(future_candles[0].time)[0] - duration
    )
    expiry_minutes = (
        setup_expiry_minutes
        if setup_expiry_minutes is not None
        else max(1, setup_expiry_bars)
        * int(duration.total_seconds() // 60)
    )
    fill = find_confirmation_close_fill(
        side=side,
        zone_low=zone[0],
        zone_high=zone[1],
        future_candles=future_candles,
        setup_active_time=active_at,
        setup_expiry=timedelta(minutes=expiry_minutes),
        execution_timeframe=execution_timeframe,
        spread_price=request.spread_price,
        slippage_price=request.slippage_price,
    )
    if fill is None:
        return None
    return fill.candle, fill.price, fill.candle_index


def trade_plan_skip_reason(scenario: dict[str, Any]) -> tuple[str, str]:
    if _entry_zone_bounds(scenario.get("entry_zone")) is None:
        return "invalid_trade_plan", "Thiếu entry zone hợp lệ."
    try:
        float(scenario["stop_loss"])
    except (KeyError, TypeError, ValueError):
        return "invalid_trade_plan", "Thiếu stop_loss hợp lệ."
    if _scenario_tp1(scenario.get("take_profit")) is None:
        return "invalid_trade_plan", "Không có TP1 hợp lệ."
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


def _scenario_tp1(value: object) -> float | None:
    raw = (
        value[0]
        if isinstance(value, (list, tuple)) and len(value) > 0
        else value
    )
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


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
    execution_timeframe: str = "M15",
    filled_at: datetime | None = None,
    max_holding_minutes: int | None = None,
) -> tuple[str | None, float | None, str, int]:
    if not future_candles:
        return None, None, "open", 0
    duration = timeframe_duration(execution_timeframe)
    normalized_fill = filled_at or normalize_utc(
        future_candles[0].time
    )[0]
    holding_minutes = (
        max_holding_minutes
        if max_holding_minutes is not None
        else max(1, max_holding_bars)
        * int(duration.total_seconds() // 60)
    )
    resolution = resolve_post_fill_exit(
        side=side,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        future_candles=future_candles,
        filled_at=normalized_fill,
        max_holding=timedelta(minutes=holding_minutes),
        execution_timeframe=execution_timeframe,
        same_bar_policy=(
            SAME_BAR_STOP_FIRST
            if conservative_same_bar
            else SAME_BAR_TARGET_FIRST
        ),
    )
    return (
        (
            resolution.exited_at.isoformat()
            if resolution.exited_at is not None
            else None
        ),
        resolution.price,
        resolution.outcome,
        resolution.holding_bars,
    )


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
    gross_results = [trade.gross_r for trade in trades]
    cost_results = [trade.cost_r for trade in trades]
    net_results = [trade.net_r for trade in trades]
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
        "gross_r": round(sum(gross_results), 4) if gross_results else 0.0,
        "cost_r": round(sum(cost_results), 4) if cost_results else 0.0,
        "net_r": round(sum(net_results), 4) if net_results else 0.0,
        "gross_pnl_account": round(
            sum(trade.gross_pnl_account for trade in trades), 2
        ),
        "net_pnl_account": round(
            sum(trade.net_pnl_account for trade in trades), 2
        ),
        "total_transaction_cost_account": round(
            sum(
                trade.spread_slippage_account
                + trade.commission_account
                + trade.swap_account
                for trade in trades
            ),
            2,
        ),
        "gross_net_difference_r": round(
            sum(cost_results), 4
        ) if trades else 0.0,
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


def build_monthly_breakdown(trades: list[BacktestTrade]) -> dict[str, dict[str, Any]]:
    groups: dict[str, list[BacktestTrade]] = {}
    for trade in trades:
        try:
            parsed = datetime.fromisoformat(trade.entry_time.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            continue
        month_key = parsed.strftime("%Y-%m")
        groups.setdefault(month_key, []).append(trade)
    result: dict[str, dict[str, Any]] = {}
    for month_key in sorted(groups):
        month_trades = groups[month_key]
        base = summarize_backtest_trades(month_trades)
        r_values = [t.result_r for t in month_trades]
        base["trades_count"] = base["total_trades"]
        base["best_trade_r"] = round(max(r_values), 4) if r_values else 0.0
        base["worst_trade_r"] = round(min(r_values), 4) if r_values else 0.0
        result[month_key] = base
    return result


def build_breakdowns(trades: list[BacktestTrade]) -> dict[str, Any]:
    return {
        "by_symbol": breakdown_by(trades, lambda trade: trade.symbol),
        "by_side": breakdown_by(trades, lambda trade: trade.side),
        "by_decision": breakdown_by(trades, lambda trade: trade.decision or "unknown"),
        "by_month": build_monthly_breakdown(trades),
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
    entry_timeframe: str = "M15",
    execution_timeframe: str = "M15",
    execution_events: list[dict[str, Any]] | None = None,
    execution_costs: dict[str, Any] | None = None,
) -> BacktestTrade:
    from core.scoring_provenance import normalize_scoring_provenance

    scores = analysis.get("scenario_scores", {}) if isinstance(analysis.get("scenario_scores"), dict) else {}
    side_score = scores.get(side, {}) if isinstance(scores.get(side), dict) else {}
    decision_summary = analysis.get("decision_summary", {}) if isinstance(analysis.get("decision_summary"), dict) else {}
    market_regime = analysis.get("market_regime", {}) if isinstance(analysis.get("market_regime"), dict) else {}
    smc_flags = analysis.get("smc_trade_flags", {}) if isinstance(analysis.get("smc_trade_flags"), dict) else {}
    scoring_provenance = normalize_scoring_provenance(
        analysis.get("scoring_provenance"),
    )
    costs = execution_costs if isinstance(execution_costs, dict) else {}
    normalized_execution_mode = normalize_execution_mode(
        request.execution_mode
    )
    explicit_setup_score, _setup_score_source = side_setup_score(
        analysis,
        side,
    )
    gross_r = float(costs.get("gross_r", result_value) or 0.0)
    cost_r = float(costs.get("cost_r", 0.0) or 0.0)
    net_r = float(costs.get("net_r", result_value) or 0.0)
    return BacktestTrade(
        symbol=request.symbol,
        side=side,
        decision=decision,
        entry_time=candle_close_time(
            entry_candle,
            entry_timeframe,
        ).isoformat(),
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
        selected_zone_id=(
            str(scenario.get("entry_zone_id"))
            if scenario.get("entry_zone_id")
            else None
        ),
        selected_zone_quality_score=_safe_int(
            scenario.get("entry_zone_quality_score")
        ),
        selected_zone_relevance_score=_safe_int(
            scenario.get("entry_zone_relevance_score")
        ),
        selected_zone_setup_score=_safe_int(
            scenario.get("entry_zone_setup_score")
        ),
        selected_zone_scoring_version=(
            str(scenario.get("entry_zone_scoring_version"))
            if scenario.get("entry_zone_scoring_version")
            else None
        ),
        smc_score_breakdown=(
            dict(scenario.get("smc_score_breakdown"))
            if isinstance(scenario.get("smc_score_breakdown"), dict)
            else {}
        ),
        scanner_scorer_version=scoring_provenance[
            "scanner_scorer_version"
        ],
        scanner_feature_version=scoring_provenance[
            "scanner_feature_version"
        ],
        smc_scorer_version=scoring_provenance["smc_scorer_version"],
        reason_codes=list(analysis.get("reason_codes", []) or []),
        warning_codes=list(analysis.get("warning_codes", []) or []),
        block_codes=list(analysis.get("block_codes", []) or []),
        analysis_snapshot=analysis if request.store_analysis_snapshots else None,
        execution_policy_version=BACKTEST_EXECUTION_POLICY_VERSION,
        execution_timeframe=execution_timeframe,
        scenario_source=str(
            scenario.get("scenario_source")
            or (
                "synthetic_fallback"
                if scenario.get("_fallback") is True
                else "pipeline"
            )
        ),
        research_only=bool(
            scenario.get("research_only") is True
            or scenario.get("_fallback") is True
            or scenario.get("synthetic") is True
        ),
        execution_events=list(execution_events or []),
        execution_mode=normalized_execution_mode,
        execution_model_version=(
            EXECUTION_PARITY_MODEL_VERSION
            if normalized_execution_mode == EXECUTION_MODE_PARITY
            else BACKTEST_EXECUTION_POLICY_VERSION
        ),
        cost_model_version=(
            EXECUTION_COST_MODEL_VERSION
            if normalized_execution_mode == EXECUTION_MODE_PARITY
            else ""
        ),
        quote_conversion_model_version=(
            QUOTE_CONVERSION_MODEL_VERSION
            if normalized_execution_mode == EXECUTION_MODE_PARITY
            else ""
        ),
        raw_entry_price=optional_float(costs.get("raw_entry_price")),
        raw_exit_price=optional_float(costs.get("raw_exit_price")),
        gross_r=round(gross_r, 4),
        cost_r=round(cost_r, 4),
        net_r=round(net_r, 4),
        gross_pnl_account=round(
            float(costs.get("gross_pnl_account", 0.0) or 0.0), 4
        ),
        net_pnl_account=round(
            float(costs.get("net_pnl_account", 0.0) or 0.0), 4
        ),
        spread_slippage_account=round(
            float(costs.get("spread_slippage_account", 0.0) or 0.0), 4
        ),
        commission_account=round(
            float(costs.get("commission_account", 0.0) or 0.0), 4
        ),
        swap_account=round(
            float(costs.get("swap_account", 0.0) or 0.0), 4
        ),
        position_lot=round(
            float(costs.get("position_lot", 0.0) or 0.0), 4
        ),
        target_risk_account=round(
            float(costs.get("target_risk_account", 0.0) or 0.0), 4
        ),
        planned_risk_account=round(
            float(costs.get("planned_risk_account", 0.0) or 0.0), 4
        ),
        quote_rate_entry=float(costs.get("quote_rate_entry", 1.0) or 1.0),
        quote_rate_exit=float(costs.get("quote_rate_exit", 1.0) or 1.0),
        execution_session=str(costs.get("execution_session", "") or ""),
        cost_breakdown=dict(costs),
        setup_score=explicit_setup_score,
    )


def _run_analysis_snapshot(
    request: BacktestRequest,
    snapshot: dict[str, list[Candle]],
    balance: float,
    closed_trades: list[dict[str, Any]],
    current_time: datetime,
    analysis_fn: AnalysisFn,
    *,
    correlation_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    point_in_time_quote_rate = _quote_rate_for_request(
        request,
        current_time,
    )
    if point_in_time_quote_rate is None:
        point_in_time_quote_rate = 1.0
    analysis_spread = float(request.spread_price or 0.0)
    if normalize_execution_mode(request.execution_mode) == EXECUTION_MODE_PARITY:
        analysis_spread = session_spread_price(
            request.spread_price,
            current_time,
            request.spread_session_multipliers,
        )[0]
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
        "spread_points": analysis_spread,
        "spread_price": analysis_spread,
        "spread_status": "normal",
        "warning": None,
        "news_in_3h": False,
        "high_impact_event_within_30m": False,
        # Bước 6 (Major 5): flag AI Macro Verdict để pipeline mở Guard 1. AI
        # KHÔNG được gọi trong backtest — assessor chạy read-cache-only khi
        # is_backtest=True (miss → skip trung tính, reproducible).
        "macro_ai_verdict_enabled": bool(request.macro_ai_verdict_enabled),
    }
    macro_alignment = (
        request.macro_alignment_override if request.allow_macro and request.macro_alignment_override
        else None if request.allow_macro
        else {"buy": 15, "sell": 15}
    )
    point_in_time_correlation = (
        _slice_correlation_context(correlation_context, current_time)
        if request.allow_macro
        else None
    )
    with risk_parameter_scope(request.risk_parameter_overrides):
        return analysis_fn(
            analysis_input,
            {"D1": snapshot["D1"], "H4": snapshot["H4"], "H1": snapshot["H1"]},
            data_quality=data_quality,
            macro_alignment=macro_alignment,
            macro_confidence=1.0,
            ai_commentary=None,
            ai_meta=None,
            m15_candles=snapshot.get("M15"),
            correlation_context=point_in_time_correlation,
            quote_to_usd_rate=point_in_time_quote_rate,
            closed_trades=_closed_trades_for_guard(request, closed_trades),
            open_trades=[],
            account_guard_settings=_account_guard_settings(request),
            trade_date=current_time,
            is_backtest=True,
        )


def _normalize_correlation_context(
    value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, list) and all(
            isinstance(candle, Candle) for candle in item
        ):
            normalized[key] = normalize_candle_series(item, "D1")
        else:
            normalized[key] = item
    return normalized


def _slice_correlation_context(
    value: dict[str, Any] | None,
    decision_time: datetime,
) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    sliced: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, list) and all(
            isinstance(candle, Candle) for candle in item
        ):
            sliced[key] = [
                candle
                for candle in item
                if candle_close_time(candle, "D1") <= decision_time
            ]
        else:
            sliced[key] = item
    return sliced


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


def _symbol_currencies(symbol: str) -> tuple[str, str]:
    normalized = "".join(
        character for character in str(symbol or "").upper()
        if character.isalpha()
    )
    if len(normalized) < 6:
        return "", ""
    return normalized[:3], normalized[-3:]


def _quote_conversion_required(request: BacktestRequest) -> bool:
    _base, quote = _symbol_currencies(request.symbol)
    account = str(request.account_currency or "USD").upper()
    return bool(quote and account and quote != account)


def _quote_rate_for_request(
    request: BacktestRequest,
    moment: datetime,
) -> float | None:
    if not _quote_conversion_required(request):
        return 1.0
    return quote_rate_at(
        request.quote_conversion_candles,
        moment,
        inverted=request.quote_conversion_inverted,
        timeframe="H1",
        fallback_rate=request.quote_to_account_rate,
    )


def _future_execution_candles(
    candles_by_timeframe: dict[str, list[Candle]],
    moment: datetime,
    end: datetime | None = None,
    execution_timeframe: str | None = None,
) -> list[Candle]:
    requested = str(execution_timeframe or "M15").upper()
    timeframe = (
        requested if candles_by_timeframe.get(requested) else "H1"
    )
    execution = candles_by_timeframe.get(timeframe, [])
    upper_bound = end or datetime.max.replace(tzinfo=timezone.utc)
    return execution_candles_in_interval(
        execution,
        timeframe,
        start=moment,
        end=upper_bound,
    )


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
        "entry_zone": scenario.get("entry_zone"),
        "stop_loss": scenario.get("stop_loss"),
        "take_profit": scenario.get("take_profit"),
        "tp1_source": scenario.get("tp1_source"),
        "invalid_reason": scenario.get("invalid_reason"),
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
        "selected_zone_id": scenario.get("entry_zone_id"),
        "selected_zone_quality_score": _safe_int(
            scenario.get("entry_zone_quality_score")
        ),
        "selected_zone_relevance_score": _safe_int(
            scenario.get("entry_zone_relevance_score")
        ),
        "selected_zone_setup_score": _safe_int(
            scenario.get("entry_zone_setup_score")
        ),
        "selected_zone_scoring_version": scenario.get(
            "entry_zone_scoring_version"
        ),
        "smc_score_breakdown": (
            dict(scenario.get("smc_score_breakdown"))
            if isinstance(scenario.get("smc_score_breakdown"), dict)
            else {}
        ),
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
    conversion = list(request.quote_conversion_candles)
    data["quote_conversion_candles"] = {
        "count": len(conversion),
        "symbol": request.quote_conversion_symbol or None,
        "inverted": request.quote_conversion_inverted,
        "from": (
            conversion[0].time.isoformat() if conversion else None
        ),
        "to": (
            conversion[-1].time.isoformat() if conversion else None
        ),
    }
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
