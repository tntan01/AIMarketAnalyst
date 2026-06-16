"""Analysis pipeline — orchestrated multi-step market analysis.

CT-1: Extracted from the monolithic :func:`analyze_symbol` into a class so each
step is independently readable and testable.  The public entry point is
:meth:`AnalysisPipeline.execute`, which accepts the same inputs and returns
the same output dict as the original function.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from core.account_guard import check_account_guard
from core.backtest_engine import replay_plan
from core.backtest_feedback import compute_pattern_confidence
from core.chart_payload import build_chart_payload
from core.market_models import Candle
from core.signal_engine import clamp
from core.risk_engine import (
    AnalysisInput,
    build_scenarios,
    calc_trade_permission,
    contract_size_for,
)
from core.signal_engine import (
    calc_risk_condition,
    calculate_direction_bias,
    score_scenario,
)
from core.correlation_check import compute_correlation_adjustment
from core.final_score_engine import calculate_final_score, safe_score
from core.decision_engine import make_final_decision
from core.journal_feedback_engine import build_journal_feedback
from core.statistical_edge_engine import calculate_evidence_score
from core.reason_codes import (
    DAILY_LOSS_LIMIT_REACHED,
    WEEKLY_LOSS_LIMIT_REACHED,
    codes_to_messages,
    normalize_codes,
)
from core.smc_context import build_smc_context, extract_smc_trade_flags
from core.technical_context import build_technical_snapshot, detect_market_regime
from core.trade_gate_engine import check_trade_gates


def _find_scenario(scenarios: list[dict[str, Any]], side: str) -> dict[str, Any]:
    """Find the scenario dict for a given side ('buy' or 'sell') in the list."""
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("type") == side:
            return scenario
    return {}


# ---------------------------------------------------------------------------
# Pipeline class
# ---------------------------------------------------------------------------


class AnalysisPipeline:
    """Orchestrate the full market-analysis pipeline step by step.

    Usage::

        pipeline = AnalysisPipeline()
        result = pipeline.execute(request, candles_by_timeframe, **kwargs)

    Each ``_step_*`` method reads from and writes to ``self`` so the order
    of calls in :meth:`execute` defines the pipeline contract.
    """

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def execute(
        self,
        request: AnalysisInput,
        candles_by_timeframe: dict[str, list[Candle]],
        *,
        data_quality: dict[str, Any] | None = None,
        macro_alignment: dict[str, int] | None = None,
        macro_confidence: float = 1.0,
        ai_commentary: str | None = None,
        ai_meta: dict[str, Any] | None = None,
        m15_candles: list[Candle] | None = None,
        correlation_context: dict[str, Any] | None = None,
        quote_to_usd_rate: float | None = None,
        closed_trades: list[dict[str, Any]] | None = None,
        open_trades: list[dict[str, Any]] | None = None,
        account_guard_settings: dict[str, Any] | None = None,
        trade_date: datetime | None = None,
        execution_quality_score: int | float | str | None = None,
    ) -> dict[str, Any]:
        # ---- Step 0: stash inputs ------------------------------------------
        self._request = request
        self._candles = candles_by_timeframe
        self._d1 = candles_by_timeframe.get("D1", [])
        self._h4 = candles_by_timeframe.get("H4", [])
        self._h1 = candles_by_timeframe.get("H1", [])
        self._data_quality_raw = data_quality
        self._macro_alignment_in = macro_alignment
        self._macro_confidence_in = macro_confidence
        self._ai_commentary = ai_commentary
        self._ai_meta = ai_meta
        self._m15_candles = m15_candles
        self._correlation_context = correlation_context
        self._quote_to_usd_rate = quote_to_usd_rate
        self._closed_trades = closed_trades or []
        self._open_trades = open_trades or []
        self._account_guard_settings = account_guard_settings
        self._trade_date = trade_date
        self._execution_quality_score_in = execution_quality_score

        # ---- Step 1: validate + build context ------------------------------
        self._step_validate_and_build_context()

        # ---- Step 2: correlation adjustments -------------------------------
        self._step_compute_correlation()

        # ---- Step 3: score both sides --------------------------------------
        self._step_score_scenarios()

        # ---- Step 4: build trade scenarios ---------------------------------
        self._step_build_trade_scenarios()

        # ---- Step 5: direction bias + best side ---------------------------
        self._step_determine_direction()

        # ---- Step 6: permission, journal, gates ---------------------------
        self._step_apply_gates()

        # ---- Step 7: final score + decision engine -------------------------
        self._step_compute_final_score()

        # ---- Step 8: enrichment (view, pattern, reason codes) --------------
        self._step_enrich()

        # ---- Step 9: assemble output ---------------------------------------
        return self._assemble_result()

    # ------------------------------------------------------------------
    # Step 1 — validate inputs & build technical / SMC context
    # ------------------------------------------------------------------

    def _step_validate_and_build_context(self) -> None:
        if len(self._d1) < 60 or len(self._h4) < 60 or len(self._h1) < 30:
            raise ValueError("Không đủ dữ liệu D1/H4/H1 để phân tích.")

        self._technical = build_technical_snapshot(self._d1, self._h4, self._h1)
        self._smc = build_smc_context(self._d1, self._h4, self._h1)
        self._data_quality = _build_data_quality(
            self._request, self._candles, self._data_quality_raw, self._technical,
        )
        self._spread_status = self._data_quality.get("spread_status", "unknown")
        self._news_in_3h = bool(self._data_quality.get("news_in_3h", False))

        self._market_regime = detect_market_regime(self._technical, self._news_in_3h)
        self._risk_score = calc_risk_condition(
            self._technical["atr_h4"] or self._technical["atr_d1"] or 0.0,
            self._technical["atr_avg_14d"] or self._technical["atr_h4"] or self._technical["atr_d1"] or 0.0,
            self._news_in_3h,
            self._spread_status,
        )
        self._macro_alignment = self._macro_alignment_in or {"buy": 15, "sell": 15}

    # ------------------------------------------------------------------
    # Step 2 — DXY / VIX / US10Y correlation
    # ------------------------------------------------------------------

    def _step_compute_correlation(self) -> None:
        corr_ctx = self._correlation_context or {}
        self._buy_corr_adj = compute_correlation_adjustment(
            symbol=self._request.symbol, side="buy",
            dxy_candles=corr_ctx.get("dxy_candles"),
            us10y_candles=corr_ctx.get("us10y_candles"),
            vix_candles=corr_ctx.get("vix_candles"),
        )
        self._sell_corr_adj = compute_correlation_adjustment(
            symbol=self._request.symbol, side="sell",
            dxy_candles=corr_ctx.get("dxy_candles"),
            us10y_candles=corr_ctx.get("us10y_candles"),
            vix_candles=corr_ctx.get("vix_candles"),
        )

    # ------------------------------------------------------------------
    # Step 3 — score buy & sell scenarios + extract SMC flags
    # ------------------------------------------------------------------

    def _step_score_scenarios(self) -> None:
        self._scores = {
            "buy": score_scenario(
                "buy", self._technical, self._smc, self._risk_score,
                self._macro_alignment.get("buy", 15),
                macro_confidence=self._macro_confidence_in,
                market_regime=self._market_regime,
                correlation_adjustment=self._buy_corr_adj,
                macro_context=self._macro_alignment,
            ),
            "sell": score_scenario(
                "sell", self._technical, self._smc, self._risk_score,
                self._macro_alignment.get("sell", 15),
                macro_confidence=self._macro_confidence_in,
                market_regime=self._market_regime,
                correlation_adjustment=self._sell_corr_adj,
                macro_context=self._macro_alignment,
            ),
        }

        # Entry quality bonus (Phase 5 / Phase 1 backtest) — always 0
        self._buy_smc_flags = extract_smc_trade_flags(self._smc, "buy")
        self._sell_smc_flags = extract_smc_trade_flags(self._smc, "sell")
        self._scores["buy"]["entry_quality_bonus"] = 0
        self._scores["sell"]["entry_quality_bonus"] = 0

    # ------------------------------------------------------------------
    # Step 4 — build trade plans / scenarios
    # ------------------------------------------------------------------

    def _step_build_trade_scenarios(self) -> None:
        trade_permission_initial = calc_trade_permission(
            self._data_quality, self._risk_score,
            int(max(
                self._scores["buy"].get("signal_score", 0),
                self._scores["sell"].get("signal_score", 0),
            )),
        )
        self._scenarios = build_scenarios(
            self._request, self._technical, self._smc, self._scores,
            trade_permission_initial,
            h1_candles=self._h1,
            m15_candles=self._m15_candles,
            correlation_context=self._correlation_context,
            quote_to_usd_rate=self._quote_to_usd_rate,
            spread_price=float(self._data_quality.get("spread_points") or 0),
        )
        self._has_ready_plan = any(
            item.get("ready_to_trade") for item in self._scenarios
        )
        self._buy_scenario = _find_scenario(self._scenarios, "buy")
        self._sell_scenario = _find_scenario(self._scenarios, "sell")

    # ------------------------------------------------------------------
    # Step 5 — direction bias, best side, primary scenario
    # ------------------------------------------------------------------

    def _step_determine_direction(self) -> None:
        self._direction_bias = calculate_direction_bias(
            self._scores["buy"], self._scores["sell"], min_gap=10,
        )
        best_side = self._direction_bias["best_side"]
        if best_side == "neutral":
            if self._direction_bias["buy_score"] > self._direction_bias["sell_score"]:
                best_side = "buy"
            elif self._direction_bias["sell_score"] > self._direction_bias["buy_score"]:
                best_side = "sell"
        self._best_side = best_side
        self._best_score = int(max(
            self._direction_bias["buy_score"],
            self._direction_bias["sell_score"],
        ))

        # Pick SMC flags matching final best_side
        self._smc_trade_flags = (
            self._buy_smc_flags if self._best_side == "buy"
            else self._sell_smc_flags
        )
        self._primary_scenario = (
            self._buy_scenario if self._best_side == "buy"
            else self._sell_scenario if self._best_side == "sell"
            else (self._scenarios[0] if self._scenarios else {})
        )

    # ------------------------------------------------------------------
    # Step 6 — permission, journal feedback, legacy decision, gates
    # ------------------------------------------------------------------

    def _step_apply_gates(self) -> None:
        self._trade_permission = calc_trade_permission(
            self._data_quality, self._risk_score, self._best_score,
        )

        regime_key = (
            self._market_regime.get("primary")
            if isinstance(self._market_regime, dict) else None
        )
        self._journal_feedback = (
            build_journal_feedback(
                self._closed_trades,
                symbol=self._request.symbol,
                direction=self._best_side if self._best_side in {"buy", "sell"} else "",
                regime=regime_key,
            )
            if self._best_side in {"buy", "sell"}
            else {}
        )

        # Decision action is now always sourced from the decision engine (CT-2).
        # This placeholder is only used as a fallback before the gate layer runs.
        self._decision_action = "stand_aside"

        # --- gate context ---------------------------------------------------
        gate_context: dict[str, Any] = {
            "terminal_connected": self._data_quality.get("terminal_connected"),
            "broker_logged_in": self._data_quality.get("broker_logged_in"),
            "spread_status": self._data_quality.get("spread_status"),
            "data_quality_warning": self._data_quality.get("warning"),
            "high_impact_event_within_30m": self._data_quality.get("high_impact_event_within_30m"),
            "m15_quality": (
                self._primary_scenario.get("m15_quality")
                if isinstance(self._primary_scenario, dict) else None
            ),
            "expected_effective_rr": (
                self._primary_scenario.get("expected_effective_rr")
                if isinstance(self._primary_scenario, dict) else None
            ),
            "zone_broken": (
                self._smc_trade_flags.get("zone_broken", False)
                or (
                    self._primary_scenario.get("entry_status") == "invalidated"
                    or self._primary_scenario.get("trigger_type") == "zone_broken"
                ) if isinstance(self._primary_scenario, dict) else False
            ),
            "daily_loss_limit_reached": self._data_quality.get("daily_loss_limit_reached"),
            "weekly_loss_limit_reached": self._data_quality.get("weekly_loss_limit_reached"),
            "score_gap": self._direction_bias.get("score_gap"),
            "min_buy_sell_score_gap": self._direction_bias.get("min_gap", 10),
            "journal_feedback": self._journal_feedback,
        }

        self._account_guard_result = check_account_guard(
            closed_trades=self._closed_trades,
            open_trades=self._open_trades,
            settings=self._account_guard_settings,
            action="open_new_trade",
            now=self._trade_date,
        )
        gate_context["account_guard"] = self._account_guard_result
        gate_context["daily_loss_limit_reached"] = (
            DAILY_LOSS_LIMIT_REACHED in self._account_guard_result.get("block_codes", [])
        )
        gate_context["weekly_loss_limit_reached"] = (
            WEEKLY_LOSS_LIMIT_REACHED in self._account_guard_result.get("block_codes", [])
        )

        self._gate_result = check_trade_gates(gate_context)

        # Merge gate result into trade_permission
        tp = self._trade_permission
        if not self._gate_result["allowed"]:
            tp["status"] = "blocked"
            tp["reason"] = "; ".join(self._gate_result["reasons"]) or tp["reason"]
            tp["gate_block_codes"] = self._gate_result["block_codes"]
            tp["gate_warning_codes"] = self._gate_result["warning_codes"]
            tp["decision_cap"] = self._gate_result["decision_cap"]
        elif self._gate_result["warning_codes"]:
            tp["gate_warning_codes"] = self._gate_result["warning_codes"]
            tp["decision_cap"] = self._gate_result["decision_cap"]

        # Apply gate cap to decision_action (used by main_view only).
        # The authoritative decision is always from the decision engine (CT-2).
        cap = self._gate_result["decision_cap"]
        if cap == "TRADE_BLOCKED":
            self._decision_action = "stand_aside"
        elif cap == "WATCH_ONLY":
            self._decision_action = "watch"
        elif cap == "WAITING_CONFIRMATION":
            self._decision_action = "wait_for_confirmation"

    # ------------------------------------------------------------------
    # Step 7 — main view, pattern feedback, reason codes
    # ------------------------------------------------------------------

    def _step_enrich(self) -> None:
        self._main_view = _build_main_view(
            self._request.symbol, self._best_side, self._best_score,
            self._decision_action, self._trade_permission["status"],
        )

        # Pattern feedback (H1 backtest confidence)
        self._pattern_feedback: dict[str, Any] = {}
        if self._primary_scenario and self._h1:
            p_trigger = str(self._primary_scenario.get("trigger_type", ""))
            p_side = str(self._primary_scenario.get("type", ""))
            if p_trigger and p_trigger != "none" and p_side in ("buy", "sell"):
                self._pattern_feedback = compute_pattern_confidence(
                    p_trigger, p_side, self._h1,
                )
                adj = float(self._pattern_feedback.get("confidence_adjustment", 0.0))
                if adj != 0.0:
                    self._macro_confidence_in = clamp(
                        self._macro_confidence_in + adj, 0.3, 1.0,
                    )

        # --- Aggregate reason codes from all layers -------------------------
        best_side_scores = self._scores.get(self._best_side, {})
        scenario_codes: dict[str, Any] = (
            self._primary_scenario if isinstance(self._primary_scenario, dict) else {}
        )

        combined_reason_codes: list[str] = []
        combined_penalty_codes: list[str] = []
        combined_warning_codes: list[str] = []
        combined_block_codes: list[str] = []

        for code in best_side_scores.get("reason_codes", []):
            combined_reason_codes.append(code)
        for code in best_side_scores.get("penalty_codes", []):
            combined_penalty_codes.append(code)

        for code in scenario_codes.get("reason_codes", []):
            combined_reason_codes.append(code)
        for code in scenario_codes.get("warning_codes", []):
            combined_warning_codes.append(code)
        for code in scenario_codes.get("block_codes", []):
            combined_block_codes.append(code)

        for code in self._gate_result.get("warning_codes", []):
            combined_warning_codes.append(code)
        for code in self._gate_result.get("block_codes", []):
            combined_block_codes.append(code)

        for code in self._account_guard_result.get("warning_codes", []):
            combined_warning_codes.append(code)
        for code in self._account_guard_result.get("block_codes", []):
            combined_block_codes.append(code)

        self._reason_codes = normalize_codes(combined_reason_codes)
        self._penalty_codes = normalize_codes(combined_penalty_codes)
        self._warning_codes = normalize_codes(combined_warning_codes)
        self._block_codes = normalize_codes(combined_block_codes)
        all_codes = (
            self._reason_codes + self._penalty_codes
            + self._warning_codes + self._block_codes
        )
        self._reason_messages = codes_to_messages(all_codes)

    # ------------------------------------------------------------------
    # Step 8 — final_score, evidence, execution quality, decision engine
    # ------------------------------------------------------------------

    def _step_compute_final_score(self) -> None:
        best_side_scores = self._scores.get(self._best_side, {})
        best_signal_score = int(
            best_side_scores.get("signal_score")
            or best_side_scores.get("total")
            or self._best_score
        )

        regime_key = (
            self._market_regime.get("primary")
            if isinstance(self._market_regime, dict) else None
        )

        # Evidence score
        if isinstance(self._journal_feedback, dict) and self._journal_feedback.get("evidence"):
            evidence_result = self._journal_feedback.get("evidence")
            evidence_score = evidence_result.get("evidence_score", best_signal_score)
        elif self._closed_trades:
            evidence_result = calculate_evidence_score(
                self._closed_trades,
                symbol=self._request.symbol,
                direction=self._best_side,
                regime=regime_key,
            )
            evidence_score = evidence_result.get("evidence_score", best_signal_score)
        else:
            evidence_result = {"evidence_score": best_signal_score}
            evidence_score = best_signal_score
        self._evidence_result = evidence_result

        # Execution quality
        feedback_eq = (
            self._journal_feedback.get("average_execution_quality")
            if isinstance(self._journal_feedback, dict) else None
        )
        eq_input = (
            self._execution_quality_score_in
            if self._execution_quality_score_in is not None
            else feedback_eq
        )
        self._eq_score, self._eq_source = _resolve_execution_quality(
            eq_input, fallback=best_signal_score,
        )

        # Final score blending
        self._final_score_result = calculate_final_score(
            signal_score=best_signal_score,
            evidence_score=evidence_score,
            execution_quality_score=self._eq_score,
        )

        # Decision engine
        primary_entry_status = (
            self._primary_scenario.get("entry_status")
            if isinstance(self._primary_scenario, dict) else None
        )
        self._decision_engine_result = make_final_decision(
            final_score=self._final_score_result["final_score"],
            gate_result=self._gate_result,
            entry_status=primary_entry_status,
            score_gap=self._direction_bias.get("score_gap"),
            trade_permission=self._trade_permission,
        )

    # ------------------------------------------------------------------
    # Step 9 — assemble output dict
    # ------------------------------------------------------------------

    def _assemble_result(self) -> dict[str, Any]:
        best_side = self._best_side
        best_score = self._best_score
        primary_scenario = self._primary_scenario

        return {
            "symbol": self._request.symbol,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "data_quality": self._data_quality,
            "market_regime": self._market_regime,
            "direction_bias": self._direction_bias,
            "reason_codes": self._reason_codes,
            "penalty_codes": self._penalty_codes,
            "warning_codes": self._warning_codes,
            "block_codes": self._block_codes,
            "reason_messages": self._reason_messages,
            "trade_permission": self._trade_permission,
            "decision_summary": {
                "main_view": self._main_view,
                "action": self._decision_engine_result["legacy_action"],
                "best_scenario": best_side if best_score >= 50 else "stand_aside",
                "best_score": best_score,
                "best_side": self._direction_bias.get("best_side"),
                "score_gap": self._direction_bias.get("score_gap"),
                "is_clear_bias": self._direction_bias.get("is_clear_bias"),
                "min_score_gap": self._direction_bias.get("min_gap"),
                "gate_decision_cap": self._gate_result.get("decision_cap"),
                "gate_allowed": self._gate_result.get("allowed"),
                "gate_block_codes": self._gate_result.get("block_codes", []),
                "gate_warning_codes": self._gate_result.get("warning_codes", []),
                "account_guard_blocked": self._account_guard_result.get("blocked"),
                "account_guard_block_codes": self._account_guard_result.get("block_codes", []),
                "decision_engine_enabled": True,
                "decision_engine_decision": self._decision_engine_result["decision"],
            },
            "trade_gate": self._gate_result,
            "journal_feedback": self._journal_feedback,
            "account_guard": self._account_guard_result,
            "technical": _public_technical(self._technical),
            "smc": self._smc,
            "smc_trade_flags": self._smc_trade_flags,
            "scenario_scores": self._scores,
            "macro": {
                "alignment_source": (
                    "AI"
                    if self._ai_meta and self._ai_meta.get("provider_name")
                    else "fallback_neutral"
                ),
                "ai_summary": self._ai_commentary or _fallback_ai_commentary(
                    self._request.symbol, best_side, best_score,
                    self._trade_permission,
                ),
                "macro_confidence": self._macro_confidence_in,
            },
            "economic_events": [],
            "scenarios": self._scenarios or [
                {
                    "type": "stand_aside",
                    "priority": "primary",
                    "reason": (
                        "No clean setup / đứng ngoài tốt hơn vì điểm "
                        "kịch bản hoặc dữ liệu chưa đủ sạch."
                    ),
                }
            ],
            "entry_checklist": _build_entry_checklist(
                primary_scenario,
                self._market_regime,
                self._trade_permission,
                self._data_quality,
                self._scores.get(best_side, {}),
            ),
            "backtest": replay_plan(self._request.symbol, primary_scenario, self._h1),
            "pattern_backtest": self._pattern_feedback,
            "why_not_opposite": _why_not_opposite(best_side, self._scores),
            "confidence_reason": _confidence_reason(
                self._technical,
                self._scores,
                self._trade_permission,
                self._smc,
                macro_confidence=self._macro_confidence_in,
                data_quality=self._data_quality,
            ),
            "risk_management": {
                "max_risk_pct": self._request.risk_percent,
                "warnings": [
                    "Không vào lệnh 15 phút trước/sau tin đỏ.",
                    "Luôn kiểm tra spread và giá broker trên MT5 trước khi vào lệnh.",
                    "Nếu MT5 mất kết nối hoặc spread giãn bất thường, không vào lệnh.",
                ],
            },
            "ai_provider": self._ai_meta or {},
            "chart_payload": build_chart_payload(
                {
                    **self._candles,
                    **({"M15": self._m15_candles} if self._m15_candles else {}),
                }
            ),
            "final_score": self._final_score_result["final_score"],
            "final_score_detail": self._final_score_result,
            "evidence": self._evidence_result,
            "execution_quality": {
                "execution_quality_score": self._eq_score,
                "source": self._eq_source,
            },
            "decision_engine": self._decision_engine_result,
        }


# ---------------------------------------------------------------------------
# Free functions (shared with legacy analyze_symbol wrapper)
# ---------------------------------------------------------------------------


def _resolve_execution_quality(
    value: int | float | str | None, fallback: int = 100,
) -> tuple[int, str]:
    from core.final_score_engine import _is_valid_score_value

    if _is_valid_score_value(value):
        return safe_score(value, fallback), "provided"
    return fallback, "fallback_no_closed_trade_execution_data"


def _build_data_quality(
    request: AnalysisInput,
    candles_by_timeframe: dict[str, list[Candle]],
    data_quality: dict[str, Any] | None,
    technical: dict[str, Any],
) -> dict[str, Any]:
    quality = dict(data_quality or {})
    last_candle = candles_by_timeframe.get("H1", [])[-1]
    quality.setdefault("price_source", "MT5")
    quality.setdefault("terminal_connected", True)
    quality.setdefault("broker_logged_in", True)
    quality.setdefault("display_symbol", request.symbol)
    quality.setdefault("broker_symbol", request.broker_symbol)
    quality.setdefault(
        "last_candle_time_utc",
        last_candle.time.astimezone(timezone.utc).isoformat()
        if last_candle.time.tzinfo
        else last_candle.time.isoformat(),
    )
    quality.setdefault("last_candle_time_vn", last_candle.time.isoformat())
    quality.setdefault("is_delayed", False)
    quality.setdefault("missing_candles", 0)
    quality.setdefault("spread_points", None)
    quality.setdefault("spread_status", "normal")
    quality.setdefault("contract_size", contract_size_for(request))
    quality.setdefault("warning", None)
    quality.setdefault("technical_price", technical["price"])
    return quality


def _public_technical(technical: dict[str, Any]) -> dict[str, Any]:
    public = dict(technical)
    public.pop("swings_h4", None)
    public.pop("swings_d1", None)
    return public


def _why_not_opposite(best_side: str, scores: dict[str, dict[str, Any]]) -> dict[str, str]:
    if best_side not in ("buy", "sell"):
        return {}
    opposite = "sell" if best_side == "buy" else "buy"
    opp_score = scores[opposite].get("signal_score", scores[opposite].get("total", 0))
    best_sc = scores[best_side].get("signal_score", scores[best_side].get("total", 0))
    return {
        opposite: (
            f"{opposite.upper()} yếu hơn vì tổng điểm {opp_score}/100 thấp hơn "
            f"{best_side.upper()} {best_sc}/100."
        )
    }


def _confidence_reason(
    technical: dict[str, Any],
    scores: dict[str, dict[str, Any]],
    trade_permission: dict[str, Any],
    smc: dict[str, Any],
    *,
    macro_confidence: float = 1.0,
    data_quality: dict[str, Any] | None = None,
) -> list[str]:
    data_quality = data_quality or {}
    reasons = [
        f"H4 structure: {technical['structure_h4']}.",
        f"Buy/Sell score: {scores['buy'].get('signal_score', scores['buy'].get('total', 0))} / {scores['sell'].get('signal_score', scores['sell'].get('total', 0))}.",
        (
            "BUY components: "
            f"trend={scores['buy'].get('trend_alignment', 0)}, "
            f"momentum={scores['buy'].get('momentum_alignment', 0)}, "
            f"location={scores['buy'].get('location_quality', 0)}, "
            f"smc={scores['buy'].get('smc_quality', 0)}, "
            f"risk={scores['buy'].get('risk_condition', 0)}, "
            f"macro={scores['buy'].get('macro_alignment', 0)}."
        ),
        (
            "SELL components: "
            f"trend={scores['sell'].get('trend_alignment', 0)}, "
            f"momentum={scores['sell'].get('momentum_alignment', 0)}, "
            f"location={scores['sell'].get('location_quality', 0)}, "
            f"smc={scores['sell'].get('smc_quality', 0)}, "
            f"risk={scores['sell'].get('risk_condition', 0)}, "
            f"macro={scores['sell'].get('macro_alignment', 0)}."
        ),
        f"BUY SMC: {scores['buy'].get('smc_quality', 0)}/15 - {scores['buy'].get('smc_reason', '--')}",
        f"SELL SMC: {scores['sell'].get('smc_quality', 0)}/15 - {scores['sell'].get('smc_reason', '--')}",
        f"Trade permission: {trade_permission['status']} - {trade_permission['reason']}",
    ]
    if macro_confidence < 0.8:
        reasons.append(
            f"Macro confidence low ({macro_confidence:.2f}) because macro/headline coverage is incomplete or fallback data is being used."
        )
    if trade_permission.get("status") == "caution":
        event = data_quality.get("next_high_impact_event") or data_quality.get("resume_after")
        if event:
            reasons.append(f"Caution event/context: {event}.")
    h4_smc = smc.get("H4", {}) if isinstance(smc, dict) else {}
    if h4_smc.get("bos") or h4_smc.get("choch"):
        reasons.append(
            "SMC H4: "
            + ("BOS " if h4_smc.get("bos") else "")
            + ("CHOCH " if h4_smc.get("choch") else "")
            + f"displacement={h4_smc.get('displacement', 'neutral')}."
        )
    return reasons


def _build_main_view(symbol: str, side: str, score: int, action: str, permission: str) -> str:
    if action == "stand_aside":
        return f"{symbol}: No clean setup / đứng ngoài tốt hơn."
    return f"{symbol}: ưu tiên {side.upper()} có điều kiện, điểm {score}/100, quyền giao dịch {permission}."


def _fallback_ai_commentary(symbol: str, best_side: str, best_score: int, trade_permission: dict[str, Any]) -> str:
    if trade_permission["status"] == "blocked" or best_score < 65:
        return (
            f"{symbol}: No clean setup / đứng ngoài tốt hơn. Hệ thống vẫn hiển thị số liệu kỹ thuật, "
            "nhưng AI chưa có nhận định riêng hoặc điều kiện giao dịch chưa sạch."
        )
    return (
        f"{symbol}: ưu tiên {best_side.upper()} có điều kiện. Chờ giá vào vùng entry, H1 xác nhận, "
        "spread bình thường và tuân thủ SL/TP do hệ thống đã tính."
    )


def _build_entry_checklist(
    scenario: dict[str, Any],
    market_regime: dict[str, Any],
    trade_permission: dict[str, Any],
    data_quality: dict[str, Any],
    score: dict[str, Any],
) -> list[dict[str, Any]]:
    trend_pass, trend_note = _entry_trend_check(scenario, market_regime, score)
    return [
        _checklist_item("Xu hướng", trend_pass, market_regime.get("primary", "unknown"), trend_note),
        _checklist_item("Vùng POI", bool(scenario.get("entry_zone")) and scenario.get("entry_status") != "invalidated", scenario.get("entry_zone", "--"), "Cần có vùng entry/POI hợp lệ và chưa bị vô hiệu."),
        _checklist_item("Xác nhận H1", bool(scenario.get("h1_confirmation")), scenario.get("trigger_type", "none"), scenario.get("invalid_reason") or "Cần nến H1 xác nhận tại vùng."),
        _checklist_item("Tin tức", not data_quality.get("news_in_3h") and trade_permission.get("status") != "blocked", data_quality.get("next_high_impact_event") or "Không có tin tác động cao gần", "Tránh vào lệnh gần tin tác động cao."),
        _checklist_item("Spread", data_quality.get("spread_status") == "normal", data_quality.get("spread_status", "unknown"), "Spread phải bình thường."),
        _checklist_item("R:R", _parse_rr(scenario.get("risk_reward")) >= 1.5, scenario.get("risk_reward", "--"), "R:R tối thiểu nên từ 1:1.5 trở lên."),
        _checklist_item(
            "Lot",
            isinstance(scenario.get("position_sizing"), dict) and float(scenario.get("position_sizing", {}).get("suggested_lot", 0)) > 0,
            scenario.get("position_sizing", {}).get("suggested_lot", "--") if isinstance(scenario.get("position_sizing"), dict) else "--",
            "Lot chỉ tính khi entry đã xác nhận.",
        ),
    ]


def _entry_trend_check(
    scenario: dict[str, Any],
    market_regime: dict[str, Any],
    score: dict[str, Any],
) -> tuple[bool, str]:
    side = scenario.get("type")
    primary = market_regime.get("primary")
    if side == "buy" and primary == "trend_up":
        return True, "Xu hướng tăng phù hợp với kịch bản mua."
    if side == "sell" and primary == "trend_down":
        return True, "Xu hướng giảm phù hợp với kịch bản bán."
    if primary == "range":
        has_valid_zone = bool(scenario.get("entry_zone")) and scenario.get("entry_status") != "invalidated"
        good_location = int(score.get("location_quality", 0) or 0) >= 10
        if has_valid_zone and good_location:
            return True, "Thị trường đi ngang nhưng có vùng POI/biên giá đủ tốt để theo dõi."
        return False, "Thị trường đi ngang; chỉ ưu tiên nếu setup nằm ở biên range rõ ràng."
    if side == "buy" and primary == "trend_down":
        return False, "Kịch bản mua đang ngược xu hướng giảm chính."
    if side == "sell" and primary == "trend_up":
        return False, "Kịch bản bán đang ngược xu hướng tăng chính."
    return False, "Xu hướng chính chưa rõ hoặc chưa khớp với kịch bản."


def _checklist_item(label: str, passed: bool, value: object, note: str) -> dict[str, Any]:
    return {"label": label, "status": "pass" if passed else "wait", "value": value, "note": note}


def _parse_rr(value: object) -> float:
    text = str(value or "")
    if ":" not in text:
        return 0.0
    try:
        return float(text.split(":", 1)[1])
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Legacy compatibility helper
# ---------------------------------------------------------------------------


def build_analysis_context(contexts: list[Any]) -> dict[str, Any]:
    """Giữ tương thích cho test/đoạn code cũ chỉ cần trend + structure."""
    from core.smc_context import summarize_structure
    from core.technical_context import summarize_trend

    return {
        item.timeframe: {
            "trend": summarize_trend(item.candles),
            "smc": summarize_structure(item.candles),
        }
        for item in contexts
    }
