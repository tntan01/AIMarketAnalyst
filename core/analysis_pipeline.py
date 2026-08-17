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
from core.backtest_engine import replay_plan, empty_replay
from core.backtest_feedback import compute_pattern_confidence
from core.chart_payload import build_chart_payload
from core.market_models import Candle
from core.signal_engine import clamp
from core.risk_engine import (
    AnalysisInput,
    build_scenarios,
    build_source_zone_diagnostics,
    calc_trade_permission,
    calculate_expected_effective_rr,
    contract_size_for,
)
from core.signal_engine import (
    calc_risk_condition,
    calculate_direction_bias,
    compose_scenario_score,
)
from core.correlation_check import compute_correlation_adjustment
from core.final_score_engine import (
    calculate_final_score,
    default_final_score_result,
    safe_score,
)
from core.decision_engine import make_final_decision
from core.journal_feedback_engine import build_journal_feedback
from core.statistical_edge_engine import calculate_evidence_score
from core.reason_codes import (
    DAILY_LOSS_LIMIT_REACHED,
    MACRO_DATA_PARTIAL,
    MACRO_DATA_UNAVAILABLE,
    MACRO_HIGH_IMPACT_EVENT_NEARBY,
    WEEKLY_LOSS_LIMIT_REACHED,
    append_code as _append_reason_code,
    codes_to_messages,
    normalize_codes,
)
from core.smc_context import build_smc_context, extract_smc_trade_flags
from core.smc_consumer_contract import (
    build_smc_consumer_from_canonical_result,
    selected_zone_for_side,
    side_consumer_metadata,
)
from core.smc_prefilter import SMC_SCORING_ERROR, evaluate_post_context_prefilter
from core.smc_scorer import score_smc
from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SmcScoringResult,
    validate_smc_result,
)
from core.smc_versions import SMC_SCORER_VERSION
from core.scoring_provenance import build_scoring_provenance
from core.technical_context import build_technical_snapshot, detect_market_regime
from core.trade_gate_engine import check_trade_gates


def _find_scenario(scenarios: list[dict[str, Any]], side: str) -> dict[str, Any]:
    """Find the scenario dict for a given side ('buy' or 'sell') in the list."""
    for scenario in scenarios:
        if isinstance(scenario, dict) and scenario.get("type") == side:
            return scenario
    return {}


def _merge_active_smc_flags(
    base_flags: dict[str, Any],
    consumer_side: dict[str, Any],
) -> dict[str, Any]:
    """Attach the decision-path canonical zone to structural safety flags."""

    flags = dict(base_flags)
    selected = (
        consumer_side.get("selected_zone")
        if isinstance(consumer_side.get("selected_zone"), dict)
        else {}
    )
    selected_zone_id = consumer_side.get("selected_zone_id")
    flags.update({
        "has_selected_zone": bool(selected_zone_id),
        "selected_zone_id": selected_zone_id,
        "selected_zone_type": consumer_side.get("selected_zone_type"),
        "selected_zone_timeframe": consumer_side.get(
            "selected_zone_timeframe"
        ),
        "selected_zone_family": selected.get("family"),
        "selected_zone_score": consumer_side.get(
            "selected_zone_setup_score"
        ),
        "selected_zone_quality_score": consumer_side.get(
            "selected_zone_quality_score"
        ),
        "selected_zone_relevance_score": consumer_side.get(
            "selected_zone_relevance_score"
        ),
        "selected_zone_setup_score": consumer_side.get(
            "selected_zone_setup_score"
        ),
        "selected_zone_scoring_version": consumer_side.get(
            "scoring_version"
        ),
        "selected_zone_liquidity_sweep_linked": bool(
            selected.get("liquidity_sweep_linked")
        ),
        "selected_zone_linked_sweep_id": selected.get("linked_sweep_id"),
        "selected_zone_linked_sweep_distance_atr": selected.get(
            "linked_sweep_distance_atr"
        ),
        "selected_zone_linked_sweep_time_delta": selected.get(
            "linked_sweep_time_delta"
        ),
        "zone_broken": bool(
            selected.get("broken") or selected.get("lifecycle_broken")
        ),
        "smc_score_breakdown": dict(
            consumer_side.get("score_breakdown", {})
            if isinstance(consumer_side.get("score_breakdown"), dict)
            else {}
        ),
        "raw": selected,
    })
    return flags


def _build_canonical_smc_diagnostics(
    smc_result: SmcScoringResult,
    consumer_contract: dict[str, Any],
) -> dict[str, Any]:
    """Represent the single canonical SMC result for the assembled output."""

    sides: dict[str, Any] = {}
    for side in ("buy", "sell"):
        side_result = smc_result.side(side)
        sides[side] = {
            "score": side_result.score if side_result else None,
            "smc_reason": side_result.smc_reason if side_result else None,
            "selected_zone_id": (
                side_result.selected_zone_id if side_result else None
            ),
            "selected_zone_type": (
                side_result.selected_zone_type if side_result else None
            ),
            "selected_zone_timeframe": (
                side_result.selected_zone_timeframe if side_result else None
            ),
            "selected_zone_score": (
                side_result.selected_zone_score if side_result else None
            ),
            "selected_zone_quality_score": (
                side_result.selected_zone_quality_score
                if side_result
                else None
            ),
            "selected_zone_relevance_score": (
                side_result.selected_zone_relevance_score
                if side_result
                else None
            ),
            "selected_zone_setup_score": (
                side_result.selected_zone_setup_score
                if side_result
                else None
            ),
            "scoring_version": smc_result.scoring_version,
            "breakdown": side_result.breakdown if side_result else {},
        }
    return {
        "contract_version": SMC_SCORING_CONTRACT_VERSION,
        "scoring_version": smc_result.scoring_version or SMC_SCORER_VERSION,
        "sides": sides,
        "consumer_contract": consumer_contract,
    }


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
        thresholds: dict[str, int | float] | None = None,
        is_backtest: bool = False,
        scan_interval_min: int = 15,
        scanner_fast_tier1: bool = False,
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
        self._scan_interval_min = scan_interval_min
        self._execution_quality_score_in = execution_quality_score
        self._thresholds = thresholds
        self._is_backtest = is_backtest
        # Only the bulk scanner supplies this flag.  Backtests always retain
        # the full pipeline even if an external caller supplies a fast-path
        # flag.  (``scanner_fast_tier2`` was removed 16/08/2026 — it was set
        # but never branched on anywhere.)
        self._scanner_fast_tier1 = bool(scanner_fast_tier1) and not is_backtest
        self._structural_reject: dict[str, Any] | None = None
        self._precomputed_smc: SmcScoringResult | None = None
        self._decision_engine_enabled = True

        # ---- Pipeline diagnostics ------------------------------------------
        self._diag: list[dict[str, Any]] = []

        # ---- Step 1: validate + build context ------------------------------
        try:
            self._step_validate_and_build_context()
        except ValueError:
            self._log_step(
                "validate", "fail",
                f"VALIDATION FAILED: insufficient candles (D1={len(self._d1)}, H4={len(self._h4)}, H1={len(self._h1)})",
                {"d1_count": len(self._d1), "h4_count": len(self._h4), "h1_count": len(self._h1)},
            )
            raise

        # Tier 1 is a Scanner-only post-context optimisation.  The predicate
        # owns every reject decision and is fail-open by contract; an
        # unexpected integration error must likewise retain the full route.
        # Survivors retain the canonical v2 payload so Step 3 does not score
        # the same zones for a second time.
        if self._scanner_fast_tier1:
            try:
                fast_decision = evaluate_post_context_prefilter(
                    smc=self._smc,
                    technical=self._technical,
                    market_regime=self._market_regime,
                    m15_candles=self._m15_candles,
                )
            except Exception:
                fast_decision = None
            if isinstance(fast_decision, dict):
                precomputed_smc = fast_decision.get("precomputed_smc")
                if isinstance(precomputed_smc, SmcScoringResult):
                    self._precomputed_smc = precomputed_smc
                if (
                    fast_decision.get("should_reject") is True
                    and fast_decision.get("fail_open") is False
                ):
                    self._prepare_structural_reject(
                        "post_context",
                        fast_decision,
                    )
                    return self._assemble_result()

        # ---- Step 2: correlation adjustments -------------------------------
        self._step_compute_correlation()

        # ---- Step 3: score both sides --------------------------------------
        self._step_score_scenarios()
        if self._structural_reject is not None:
            return self._assemble_result()

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
    # Diagnostics helpers
    # ------------------------------------------------------------------

    def _log_step(self, step: str, status: str, summary: str, details: dict[str, Any] | None = None) -> None:
        self._diag.append({
            "step": step,
            "status": status,
            "summary": summary,
            "details": details or {},
        })

    def _ensure_safe_defaults(self) -> None:
        """Set safe defaults for attributes that _assemble_result expects."""
        for attr, default in [
            ("_technical", {"structure_h4": "unknown", "price": 0.0, "atr_h4": None, "atr_d1": None, "atr_avg_14d": None}),
            ("_smc", {"H4": {}, "H1": {}}), ("_data_quality", {}),
            ("_spread_status", "unknown"), ("_news_in_3h", False),
            ("_market_regime", {"primary": "unknown"}), ("_risk_score", 0),
            ("_macro_alignment", {"buy": 15, "sell": 15}),
            ("_macro_confidence_in", 1.0),
            ("_macro_data_reason_code", None),
            ("_macro_event_reason_code", None),
            ("_buy_corr_adj", 0), ("_sell_corr_adj", 0),
            ("_scores", {"buy": {}, "sell": {}}),
            ("_buy_smc_flags", {}), ("_sell_smc_flags", {}),
            ("_smc_scoring_diagnostics", {}),
            ("_smc_consumer_contract", {}),
            ("_scenarios", []), ("_has_ready_plan", False),
            ("_buy_scenario", {}), ("_sell_scenario", {}),
            ("_direction_bias", {"best_side": "neutral", "buy_score": 0, "sell_score": 0, "score_gap": 0, "is_clear_bias": False, "min_gap": 10}),
            ("_best_side", "neutral"), ("_best_score", 0),
            ("_smc_trade_flags", {}), ("_primary_scenario", {}),
            ("_trade_permission", {"status": "blocked", "reason": "validation failed"}),
            ("_decision_action", "stand_aside"),
            ("_journal_feedback", {}),
            ("_journal_feedback_by_side", {"buy": {}, "sell": {}}),
            ("_gate_result", {"allowed": False, "decision_cap": "TRADE_BLOCKED", "block_codes": [], "warning_codes": [], "reasons": ["Pipeline validation failed"]}),
            ("_account_guard_result", {"blocked": False, "block_codes": [], "warning_codes": []}),
            ("_main_view", "Validation failed"),
            ("_pattern_feedback", {}),
            ("_reason_codes", []), ("_penalty_codes", []), ("_warning_codes", []), ("_block_codes", []),
            ("_reason_messages", []),
            ("_evidence_result", {}), ("_eq_score", 0), ("_eq_source", "fallback"),
            ("_final_score_result", {"final_score": 0}),
            ("_side_score_results", {"buy": {}, "sell": {}}),
            ("_decision_engine_result", {"decision": "STAND_ASIDE", "legacy_action": "stand_aside"}),
            ("_decision_engine_enabled", True),
        ]:
            if not hasattr(self, attr):
                setattr(self, attr, default)

    def _prepare_structural_reject(
        self,
        stage: str,
        decision: dict[str, Any],
    ) -> None:
        """Prepare a full-schema, fail-closed result for a verified reject.

        This method intentionally performs no routing.  Step 4 will call it
        after Tier 1 has made a canonical decision; keeping the builder
        separate lets its output contract be verified before activation.
        """

        route_by_stage = {
            "pre_smc": "prefilter_reject",
            "post_context": "post_context_reject",
        }
        route = route_by_stage.get(stage)
        reason_code = str(decision.get("reason_code", "") or "").strip()
        if route is None or not reason_code:
            raise ValueError("Structural reject requires a valid stage and reason code.")

        self._ensure_safe_defaults()
        evaluation_status = "not_evaluated_due_to_fast_reject"
        reason = f"Structural SMC reject: {reason_code}"
        self._structural_reject = {
            "stage": stage,
            "pipeline_route": route,
            "reason_code": reason_code,
            "fast_path_version": str(
                decision.get("fast_path_version", "scanner-fast-path-v1")
                or "scanner-fast-path-v1"
            ),
            "prefilter_version": str(
                decision.get("prefilter_version", "smc-prefilter-v1")
                or "smc-prefilter-v1"
            ),
        }
        side_score = {
            "signal_score": 0,
            "total": 0,
            "smc_quality": 0,
            "smc_reason": reason,
            "reason_codes": [reason_code],
            "penalty_codes": [],
            "warning_codes": [],
            "block_codes": [reason_code],
            "smc_flags": {},
        }
        self._scores = {"buy": dict(side_score), "sell": dict(side_score)}
        self._side_score_results = {
            side: {
                "side": side,
                "signal_score": 0,
                "evidence_score": 0,
                "execution_quality_score": 0,
                "setup_score": 0,
                "final_score": 0,
            }
            for side in ("buy", "sell")
        }
        self._scenarios = [{
            "type": "stand_aside",
            "priority": "primary",
            "entry_status": "no_setup",
            "reason": reason,
            "reason_code": reason_code,
        }]
        self._primary_scenario = self._scenarios[0]
        self._buy_scenario = {}
        self._sell_scenario = {}
        self._has_ready_plan = False
        self._direction_bias = {
            "best_side": "neutral",
            "buy_score": 0,
            "sell_score": 0,
            "score_gap": 0,
            "is_clear_bias": False,
            "min_gap": 10,
        }
        self._best_side = "neutral"
        self._best_score = 0
        self._smc_trade_flags = {"buy": {}, "sell": {}}
        self._smc_scoring_diagnostics = {
            "evaluation_status": evaluation_status,
            "prefilter": dict(decision),
        }
        self._smc_consumer_contract = {
            "evaluation_status": evaluation_status,
            "buy": {},
            "sell": {},
        }
        self._trade_permission = {
            "status": "blocked",
            "reason": reason,
            "reason_code": reason_code,
            "min_score": self._thresholds.get("ready", 65) if self._thresholds else 65,
            "min_rr": self._thresholds.get("min_rr", 1.3) if self._thresholds else 1.3,
        }
        self._gate_result = {
            "allowed": False,
            "decision_cap": "TRADE_BLOCKED",
            "block_codes": [reason_code],
            "warning_codes": [],
            "reasons": [reason],
            "evaluation_status": evaluation_status,
        }
        self._account_guard_result = {
            "blocked": False,
            "block_codes": [],
            "warning_codes": [],
            "evaluation_status": evaluation_status,
        }
        self._decision_action = "stand_aside"
        self._main_view = "STAND_ASIDE — no actionable canonical SMC zone."
        self._journal_feedback = {"evaluation_status": evaluation_status}
        self._journal_feedback_by_side = {
            "buy": {"evaluation_status": evaluation_status},
            "sell": {"evaluation_status": evaluation_status},
        }
        self._pattern_feedback = {"evaluation_status": evaluation_status}
        self._reason_codes = [reason_code]
        self._penalty_codes = []
        self._warning_codes = []
        self._block_codes = [reason_code]
        self._reason_messages = [reason]
        self._evidence_result = {
            "evidence_score": 0,
            "evaluation_status": evaluation_status,
        }
        self._eq_score = 0
        self._eq_source = evaluation_status
        self._final_score_result = {
            "final_score": 0,
            "evaluation_status": evaluation_status,
        }
        self._decision_engine_result = {
            "decision": "STAND_ASIDE",
            "legacy_action": "stand_aside",
            "reason_codes": [reason_code],
            "evaluation_status": evaluation_status,
        }
        self._decision_engine_enabled = False
        self._log_step(
            "structural_reject",
            "warning",
            reason,
            {
                "stage": stage,
                "pipeline_route": route,
                "reason_code": reason_code,
                "skipped_steps": [
                    "correlation", "score", "scenarios", "direction",
                    "gate", "final_score", "enrich",
                ],
            },
        )

    # ------------------------------------------------------------------
    # Step 1 — validate inputs & build technical / SMC context
    # ------------------------------------------------------------------

    def _step_validate_and_build_context(self) -> None:
        if len(self._d1) < 60 or len(self._h4) < 60 or len(self._h1) < 30:
            raise ValueError("Không đủ dữ liệu D1/H4/H1 để phân tích.")

        self._technical = build_technical_snapshot(self._d1, self._h4, self._h1)
        self._smc = build_smc_context(
            self._d1,
            self._h4,
            self._h1,
            scan_interval_min=self._scan_interval_min,
            symbol=self._request.symbol,
        )
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

        _atr = self._technical.get("atr_h4") or 0
        self._log_step(
            "validate",
            "pass",
            f"D1={len(self._d1)}, H4={len(self._h4)}, H1={len(self._h1)} candles "
            f"| Regime: {self._market_regime.get('primary', '?')} "
            f"| Risk: {self._risk_score}/15 "
            f"| ATR: {float(_atr):.5f}",
            {
                "d1_count": len(self._d1),
                "h4_count": len(self._h4),
                "h1_count": len(self._h1),
                "market_regime": self._market_regime,
                "risk_score": self._risk_score,
                "spread_status": self._spread_status,
                "news_in_3h": self._news_in_3h,
                "atr_h4": self._technical.get("atr_h4"),
                "atr_d1": self._technical.get("atr_d1"),
                "structure_h4": self._technical.get("structure_h4"),
                "price": self._technical.get("price"),
            },
        )

    # ------------------------------------------------------------------
    # Step 2 — DXY / VIX / US10Y correlation
    # ------------------------------------------------------------------

    def _step_compute_correlation(self) -> None:
        corr_ctx = self._correlation_context or {}
        vix_pair_aware_enabled = bool(
            self._data_quality.get("vix_pair_aware_enabled", False)
        )
        self._buy_corr_adj = compute_correlation_adjustment(
            symbol=self._request.symbol, side="buy",
            dxy_candles=corr_ctx.get("dxy_candles"),
            us10y_candles=corr_ctx.get("us10y_candles"),
            us2y_candles=corr_ctx.get("us2y_candles"),
            vix_candles=corr_ctx.get("vix_candles"),
            vix_pair_aware_enabled=vix_pair_aware_enabled,
        )
        self._sell_corr_adj = compute_correlation_adjustment(
            symbol=self._request.symbol, side="sell",
            dxy_candles=corr_ctx.get("dxy_candles"),
            us10y_candles=corr_ctx.get("us10y_candles"),
            us2y_candles=corr_ctx.get("us2y_candles"),
            vix_candles=corr_ctx.get("vix_candles"),
            vix_pair_aware_enabled=vix_pair_aware_enabled,
        )

        has_dxy = bool(corr_ctx.get("dxy_candles"))
        has_vix = bool(corr_ctx.get("vix_candles"))
        has_us10y = bool(corr_ctx.get("us10y_candles"))
        has_us2y = bool(corr_ctx.get("us2y_candles"))
        any_macro = has_dxy or has_vix or has_us10y or has_us2y
        corr_status = "pass" if any_macro else "warning"

        # Thiếu dữ liệu correlation → giảm macro confidence (không sửa điểm trực tiếp).
        # Nhóm sức mạnh USD gồm 4 nguồn: DXY, VIX, US10Y, US2Y.
        missing_macro_sources = 4 - (int(has_dxy) + int(has_vix) + int(has_us10y) + int(has_us2y))
        if missing_macro_sources == 4:
            self._macro_confidence_in *= 0.4  # thiếu toàn bộ → giảm mạnh
            self._macro_data_reason_code = MACRO_DATA_UNAVAILABLE
        elif missing_macro_sources > 0:
            self._macro_confidence_in *= 0.8  # thiếu một phần → giảm nhẹ
            self._macro_data_reason_code = MACRO_DATA_PARTIAL
        else:
            self._macro_data_reason_code = None

        # Sự kiện vĩ mô tác động mạnh liên quan đến đồng tiền của cặp sắp diễn ra
        # trong 4 giờ tới (nhưng ngoài cửa sổ blackout 30 phút) → giảm macro confidence.
        # Cửa sổ blackout 30 phút hiện có được giữ nguyên, không thay đổi.
        self._macro_event_reason_code = None
        next_event = self._data_quality.get("next_high_impact_event")
        hours_until = self._hours_until_high_impact(next_event)
        if hours_until is not None and 0.5 < hours_until <= 4.0:
            event_currency = str(
                next_event.get("currency", "") if isinstance(next_event, dict) else ""
            ).upper()
            if event_currency and self._pair_involves_currency(event_currency):
                self._macro_confidence_in *= 0.8  # sự kiện sắp tới → giảm nhẹ
                self._macro_event_reason_code = MACRO_HIGH_IMPACT_EVENT_NEARBY

        # Floor an toàn chung cho macro_confidence sau tất cả các bước derate
        # (thiếu dữ liệu, Bước 3). Floor áp VÔ ĐIỀU KIỆN — input confidence đã
        # xuống dưới 0.15 từ trước vẫn được nâng lên 0.15 (chủ đích đã chốt;
        # xem test_macro_confidence_floor trong bộ integration tests).
        self._macro_confidence_in = max(self._macro_confidence_in, 0.15)

        corr_summary = (
            f"DXY={'yes' if has_dxy else 'no'}, VIX={'yes' if has_vix else 'no'}, "
            f"US10Y={'yes' if has_us10y else 'no'}, US2Y={'yes' if has_us2y else 'no'} "
            f"| Buy adj: {self._buy_corr_adj:+.0f} | Sell adj: {self._sell_corr_adj:+.0f}"
        )
        if not any_macro:
            corr_summary = "KHÔNG CÓ DỮ LIỆU VĨ MÔ — " + corr_summary
        self._log_step(
            "correlation",
            corr_status,
            corr_summary,
            {
                "has_dxy": has_dxy,
                "has_vix": has_vix,
                "has_us10y": has_us10y,
                "has_us2y": has_us2y,
                "buy_correlation_adjustment": self._buy_corr_adj,
                "sell_correlation_adjustment": self._sell_corr_adj,
            },
        )

    def _hours_until_high_impact(self, event: object) -> float | None:
        """Return giờ còn lại đến sự kiện high-impact (UTC), None nếu không xác định."""
        if not isinstance(event, dict):
            return None
        raw = str(event.get("time_utc") or "")
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        return (parsed - now).total_seconds() / 3600.0

    def _pair_involves_currency(self, currency: str) -> bool:
        """True nếu đồng tiền sự kiện thuộc cặp đang phân tích."""
        symbol = self._request.symbol.upper()
        if "/" in symbol:
            base, quote = symbol.split("/", 1)
            return currency in (base, quote)
        return currency in symbol

    # ------------------------------------------------------------------
    # Step 3 — score buy & sell scenarios + extract SMC flags
    # ------------------------------------------------------------------

    def _step_score_scenarios(self) -> None:
        # Score the canonical SMC sides exactly once.  Tier-1 survivors reuse
        # the precomputed canonical result instead of scoring a second time.
        try:
            if isinstance(self._precomputed_smc, SmcScoringResult):
                smc_sides = self._precomputed_smc
            else:
                smc_sides = score_smc(
                    self._smc,
                    self._technical,
                    self._market_regime,
                    m15_candles=self._m15_candles,
                )
        except Exception:
            # Scorer failure is fail-closed: block the analysis with
            # SMC_SCORING_ERROR instead of retrying or falling back.
            self._prepare_structural_reject("post_context", {
                "reason_code": SMC_SCORING_ERROR,
                "should_reject": True,
                "fail_open": False,
                "fast_path_version": "scanner-fast-path-v1",
                "prefilter_version": "smc-prefilter-v1",
            })
            return

        if not validate_smc_result(smc_sides):
            # A malformed or incomplete canonical result must fail closed with
            # SMC_SCORING_ERROR rather than synthesizing empty sides.
            self._prepare_structural_reject("post_context", {
                "reason_code": SMC_SCORING_ERROR,
                "should_reject": True,
                "fail_open": False,
                "fast_path_version": "scanner-fast-path-v1",
                "prefilter_version": "smc-prefilter-v1",
            })
            return

        self._smc_consumer_contract = build_smc_consumer_from_canonical_result(
            result=smc_sides,
        )
        self._smc_scoring_diagnostics = _build_canonical_smc_diagnostics(
            smc_sides,
            self._smc_consumer_contract,
        )

        self._scores = {}
        for side in ("buy", "sell"):
            side_result = smc_sides.side(side)
            base_flags = extract_smc_trade_flags(self._smc, side)
            consumer_side = side_consumer_metadata(
                self._smc_consumer_contract,
                side,
            )
            active_flags = _merge_active_smc_flags(base_flags, consumer_side)
            self._scores[side] = compose_scenario_score(
                side,
                self._technical,
                smc_quality=side_result.score if side_result else None,
                smc_reason=side_result.smc_reason if side_result else None,
                smc_flags=active_flags,
                risk_score=self._risk_score,
                macro_score=self._macro_alignment.get(side, 15),
                macro_confidence=self._macro_confidence_in,
                market_regime=self._market_regime,
                correlation_adjustment=(
                    self._buy_corr_adj
                    if side == "buy"
                    else self._sell_corr_adj
                ),
                macro_context=self._macro_alignment,
                scoring_version=smc_sides.scoring_version,
                smc_score_breakdown=(
                    side_result.breakdown if side_result else {}
                ),
            )
            if side == "buy":
                self._buy_smc_flags = active_flags
            else:
                self._sell_smc_flags = active_flags

        buy_sc = self._scores["buy"]
        sell_sc = self._scores["sell"]
        self._log_step(
            "score",
            "pass",
            f"BUY={buy_sc.get('signal_score', 0)}/100 "
            f"(T={buy_sc.get('trend_alignment', 0)} M={buy_sc.get('momentum_alignment', 0)} "
            f"L={buy_sc.get('location_quality', 0)} S={buy_sc.get('smc_quality', 0)} "
            f"R={buy_sc.get('risk_condition', 0)} Ma={buy_sc.get('macro_alignment', 0)}) "
            f"| SELL={sell_sc.get('signal_score', 0)}/100 "
            f"(T={sell_sc.get('trend_alignment', 0)} M={sell_sc.get('momentum_alignment', 0)} "
            f"L={sell_sc.get('location_quality', 0)} S={sell_sc.get('smc_quality', 0)} "
            f"R={sell_sc.get('risk_condition', 0)} Ma={sell_sc.get('macro_alignment', 0)})",
            {
                "buy": {k: v for k, v in buy_sc.items() if not k.startswith("_")},
                "sell": {k: v for k, v in sell_sc.items() if not k.startswith("_")},
            },
        )
        scoring_version = self._smc_scoring_diagnostics.get(
            "scoring_version",
            SMC_SCORER_VERSION,
        )
        self._log_step(
            "smc_scoring",
            "pass",
            f"canonical scoring_version={scoring_version}",
            self._smc_scoring_diagnostics,
        )

    # ------------------------------------------------------------------
    # Step 4 — build trade plans / scenarios
    # ------------------------------------------------------------------

    def _step_build_trade_scenarios(self) -> None:
        min_score = self._thresholds.get("ready", 65) if self._thresholds else 65
        trade_permission_initial = calc_trade_permission(
            self._data_quality, self._risk_score,
            int(max(
                self._scores["buy"].get("signal_score", 0),
                self._scores["sell"].get("signal_score", 0),
            )),
            min_score=min_score,
        )
        self._scenarios = build_scenarios(
            self._request, self._technical, self._smc, self._scores,
            trade_permission_initial,
            h1_candles=self._h1,
            m15_candles=self._m15_candles,
            correlation_context=self._correlation_context,
            quote_to_usd_rate=self._quote_to_usd_rate,
            spread_price=float(self._data_quality.get("spread_price") or 0),
            market_regime=self._market_regime,
            preferred_zones={
                "buy": selected_zone_for_side(
                    self._smc_consumer_contract,
                    "buy",
                ),
                "sell": selected_zone_for_side(
                    self._smc_consumer_contract,
                    "sell",
                ),
            },
            strict_preferred_zones=True,
            # The canonical scorer's selected zone is the only decision source.
            require_preferred_zones=True,
            is_backtest=self._is_backtest,
        )
        self._has_ready_plan = any(
            item.get("ready_to_trade") for item in self._scenarios
        )
        self._buy_scenario = _find_scenario(self._scenarios, "buy")
        self._sell_scenario = _find_scenario(self._scenarios, "sell")

        scenario_summaries = []
        for sc in self._scenarios:
            if isinstance(sc, dict):
                s_type = sc.get("type", "?")
                entry = sc.get("entry_status", "?")
                m15 = sc.get("m15_quality", "?")
                rr = sc.get("expected_effective_rr")
                rr_str = f"{float(rr):.1f}" if rr is not None else "?"
                ready = "READY" if sc.get("ready_to_trade") else "no"
                scenario_summaries.append(f"{s_type}(entry={entry}, m15={m15}, RR={rr_str}, {ready})")
        self._log_step(
            "scenarios",
            "pass" if self._scenarios else "warning",
            f"{len(self._scenarios)} scenarios: {'; '.join(scenario_summaries) if scenario_summaries else 'none'}",
            {
                "count": len(self._scenarios),
                "has_ready_plan": self._has_ready_plan,
                "trade_permission_status": trade_permission_initial.get("status"),
                "scenarios": [
                    {
                        "type": s.get("type"),
                        "entry_status": s.get("entry_status"),
                        "m15_quality": s.get("m15_quality"),
                        "expected_effective_rr": s.get("expected_effective_rr"),
                        "ready_to_trade": s.get("ready_to_trade"),
                        "trigger_type": s.get("trigger_type"),
                        "entry_zone": s.get("entry_zone"),
                    }
                    for s in self._scenarios if isinstance(s, dict)
                ],
            },
        )

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
            else self._sell_smc_flags if self._best_side == "sell"
            else {}
        )
        self._primary_scenario = (
            self._buy_scenario if self._best_side == "buy"
            else self._sell_scenario if self._best_side == "sell"
            else {}
        )
        # Never borrow an opposite-side scenario.  Missing selected-side data
        # must propagate to Decision Engine as not ready.

        gap = self._direction_bias.get("score_gap", 0)
        is_clear = self._direction_bias.get("is_clear_bias", False)
        self._log_step(
            "direction",
            "pass" if self._best_side != "neutral" else "warning",
            f"BUY={self._direction_bias.get('buy_score', 0)} vs SELL={self._direction_bias.get('sell_score', 0)} "
            f"| Gap={gap} | Best: {self._best_side.upper()} "
            f"| Clear bias: {'yes' if is_clear else 'no'}",
            {
                "buy_score": self._direction_bias.get("buy_score"),
                "sell_score": self._direction_bias.get("sell_score"),
                "score_gap": gap,
                "best_side": self._best_side,
                "is_clear_bias": is_clear,
                "min_gap": self._direction_bias.get("min_gap"),
            },
        )

    # ------------------------------------------------------------------
    # Step 6 — permission, journal feedback, legacy decision, gates
    # ------------------------------------------------------------------

    def _step_apply_gates(self) -> None:
        min_score = self._thresholds.get("ready", 65) if self._thresholds else 65
        min_rr = self._thresholds.get("min_rr", 1.3) if self._thresholds else 1.3
        self._trade_permission = calc_trade_permission(
            self._data_quality, self._risk_score, self._best_score,
            min_score=min_score,
        )
        self._trade_permission["min_rr"] = min_rr

        regime_key = (
            self._market_regime.get("primary")
            if isinstance(self._market_regime, dict) else None
        )
        smc_consumer_contract = getattr(
            self,
            "_smc_consumer_contract",
            {},
        )
        self._journal_feedback_by_side = {
            side: build_journal_feedback(
                self._closed_trades,
                symbol=self._request.symbol,
                direction=side,
                regime=regime_key,
                zone_score=side_consumer_metadata(
                    smc_consumer_contract,
                    side,
                ).get("selected_zone_setup_score"),
                zone_scoring_version=side_consumer_metadata(
                    smc_consumer_contract,
                    side,
                ).get("scoring_version"),
            )
            for side in ("buy", "sell")
        }
        # Compatibility alias: gates and legacy consumers still apply only to
        # the selected direction.  Score computation below uses both sides.
        self._journal_feedback = (
            self._journal_feedback_by_side.get(self._best_side, {})
            if self._best_side in {"buy", "sell"}
            else {}
        )

        # Decision action is now always sourced from the decision engine (CT-2).
        # This placeholder is only used as a fallback before the gate layer runs.
        self._decision_action = "stand_aside"

        # --- gate context ---------------------------------------------------
        # Gate data must belong to the selected side.  Missing selected-side
        # data intentionally yields a non-ready/fail-closed gate result.
        _gate_scenario = _find_scenario(
            self._scenarios,
            self._best_side,
        )
        _gate_zone = side_consumer_metadata(
            smc_consumer_contract,
            self._best_side,
        )
        smc_context = getattr(self, "_smc", {})
        if not isinstance(smc_context, dict):
            smc_context = {}
        _h4_smc = (
            smc_context.get("H4")
            if isinstance(smc_context.get("H4"), dict)
            else {}
        )
        _opposite_displacement = (
            "bearish" if self._best_side == "buy" else "bullish"
        )
        _h4_confirmed_choch_against = bool(
            self._best_side in {"buy", "sell"}
            and _h4_smc.get("choch")
            and _h4_smc.get("choch_confirmed")
            and _h4_smc.get("displacement") == _opposite_displacement
        )
        _scenario_zone_id = _gate_scenario.get("entry_zone_id")
        _selected_zone_id = _gate_zone.get("selected_zone_id")
        _price_relation_valid = bool(
            _gate_scenario
            and (
                not _selected_zone_id
                or _scenario_zone_id == _selected_zone_id
            )
        )

        # --- Compute base-case effective RR (midpoint anchor) for gate ---------
        _gate_sc_side = _gate_scenario.get("type") if isinstance(_gate_scenario, dict) else None
        _gate_sc_entry_zone = _gate_scenario.get("entry_zone") if isinstance(_gate_scenario, dict) else None
        _gate_sc_sl = _gate_scenario.get("stop_loss") if isinstance(_gate_scenario, dict) else None
        _gate_sc_tp_list = _gate_scenario.get("take_profit") if isinstance(_gate_scenario, dict) else None
        _gate_sc_tp1 = _gate_sc_tp_list[0] if isinstance(_gate_sc_tp_list, list) and _gate_sc_tp_list else None
        _gate_sc_best_eff_rr = _gate_scenario.get("expected_effective_rr") if isinstance(_gate_scenario, dict) else None
        _gate_sc_base_eff_rr = _gate_scenario.get("expected_effective_rr_base") if isinstance(_gate_scenario, dict) else None
        _gate_spread_price = float(self._data_quality.get("spread_price") or 0)

        expected_effective_rr_base = None
        expected_effective_rr_for_gate = None
        expected_effective_rr_source = "none"

        try:
            if _gate_sc_base_eff_rr is not None:
                _stored_base_rr = float(_gate_sc_base_eff_rr)
                if _stored_base_rr > 0:
                    expected_effective_rr_base = _stored_base_rr
                    expected_effective_rr_for_gate = _stored_base_rr
                    expected_effective_rr_source = "base"
        except (TypeError, ValueError):
            pass

        if (
            expected_effective_rr_for_gate is None
            and
            isinstance(_gate_sc_entry_zone, list) and len(_gate_sc_entry_zone) == 2
            and _gate_sc_sl is not None
            and _gate_sc_tp1 is not None
            and _gate_sc_side in ("buy", "sell")
        ):
            try:
                _entry_mid = (float(_gate_sc_entry_zone[0]) + float(_gate_sc_entry_zone[1])) / 2.0
                _base_rr = calculate_expected_effective_rr(
                    direction=str(_gate_sc_side),
                    entry=_entry_mid,
                    stop_loss=float(_gate_sc_sl),
                    take_profit=float(_gate_sc_tp1),
                    spread_price=_gate_spread_price,
                )
                if _base_rr is not None and _base_rr > 0:
                    expected_effective_rr_base = _base_rr
                    expected_effective_rr_for_gate = _base_rr
                    expected_effective_rr_source = "base"
            except (TypeError, ValueError):
                pass

        if expected_effective_rr_for_gate is None:
            expected_effective_rr_for_gate = _gate_sc_best_eff_rr
            if expected_effective_rr_for_gate is not None:
                expected_effective_rr_source = "best_case_fallback"

        gate_context: dict[str, Any] = {
            "terminal_connected": self._data_quality.get("terminal_connected"),
            "broker_logged_in": self._data_quality.get("broker_logged_in"),
            "spread_status": self._data_quality.get("spread_status"),
            "data_quality_warning": self._data_quality.get("warning"),
            "high_impact_event_within_30m": self._data_quality.get("high_impact_event_within_30m"),
            "m15_quality": (
                _gate_scenario.get("m15_quality") or "none"
                if isinstance(_gate_scenario, dict) else "none"
            ),
            "expected_effective_rr": (
                _gate_scenario.get("expected_effective_rr")
                if isinstance(_gate_scenario, dict) else None
            ),
            "expected_effective_rr_base": expected_effective_rr_base,
            "expected_effective_rr_for_gate": expected_effective_rr_for_gate,
            "expected_effective_rr_source": expected_effective_rr_source,
            "risk_reward": (
                _gate_scenario.get("risk_reward")
                if isinstance(_gate_scenario, dict) else None
            ),
            "min_expected_effective_rr": (
                self._thresholds.get("min_rr", 1.3) if self._thresholds else 1.3
            ),
            "zone_broken": (
                self._smc_trade_flags.get("zone_broken", False)
                or (
                    _gate_scenario.get("entry_status") == "invalidated"
                    or _gate_scenario.get("trigger_type") == "zone_broken"
                ) if isinstance(_gate_scenario, dict) else False
            ),
            "zone_score": (
                _gate_zone.get("selected_zone_setup_score")
            ),
            "zone_id": _selected_zone_id,
            "zone_scoring_version": _gate_zone.get("scoring_version"),
            "zone_quality_score": _gate_zone.get(
                "selected_zone_quality_score"
            ),
            "zone_relevance_score": _gate_zone.get(
                "selected_zone_relevance_score"
            ),
            "zone_setup_score": _gate_zone.get(
                "selected_zone_setup_score"
            ),
            "zone_price_relation_valid": _price_relation_valid,
            "h4_confirmed_choch_against_direction": (
                _h4_confirmed_choch_against
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

        # --- Gate diagnostics (per-gate breakdown) --------------------------
        gate_checks: list[dict[str, Any]] = []
        # 1. MT5 gate
        mt5_ok = not (
            gate_context.get("terminal_connected") is False
            or gate_context.get("broker_logged_in") is False
        )
        gate_checks.append({"gate": "MT5", "status": "pass" if mt5_ok else "block",
                            "detail": "Terminal & broker OK" if mt5_ok else "MT5 not ready"})
        # 2. Spread gate
        spread_ok = gate_context.get("spread_status") != "abnormal"
        gate_checks.append({"gate": "Spread", "status": "pass" if spread_ok else "block",
                            "detail": f"spread={gate_context.get('spread_status', '?')}"})
        # 3. Data quality gate
        dq_ok = not gate_context.get("data_quality_warning")
        gate_checks.append({"gate": "DataQuality", "status": "pass" if dq_ok else "block",
                            "detail": "no warning" if dq_ok else "data quality warning"})
        # 4. News gate
        news_ok = not gate_context.get("high_impact_event_within_30m")
        gate_checks.append({"gate": "News", "status": "pass" if news_ok else "block",
                            "detail": "no news nearby" if news_ok else "high impact news within 30m"})
        # 5. Daily/Weekly loss gate
        loss_ok = not (gate_context.get("daily_loss_limit_reached") or gate_context.get("weekly_loss_limit_reached"))
        gate_checks.append({"gate": "DailyWeeklyLoss", "status": "pass" if loss_ok else "block",
                            "detail": "within limits" if loss_ok else "loss limit reached"})
        # 6. Account guard gate
        ag_blocked = self._account_guard_result.get("blocked", False)
        gate_checks.append({"gate": "AccountGuard", "status": "pass" if not ag_blocked else "block",
                            "detail": "guard OK" if not ag_blocked else f"blocked: {self._account_guard_result.get('block_codes', [])}"})
        # 7. Journal feedback gate
        jf = self._journal_feedback if isinstance(self._journal_feedback, dict) else {}
        jf_warnings = jf.get("warnings", [])
        jf_blocks = jf.get("blocks", [])
        jf_ok = not jf_warnings and not jf_blocks
        gate_checks.append({"gate": "Journal", "status": "pass" if jf_ok else ("block" if jf_blocks else "warning"),
                            "detail": "no issues" if jf_ok else f"warnings={len(jf_warnings)}, blocks={len(jf_blocks)}"})
        # 8. M15 gate
        m15_q = gate_context.get("m15_quality")
        if m15_q in (None, "none"):
            m15_status, m15_detail = "warning", "M15 không xác nhận (→WATCH_ONLY)"
        elif m15_q == "loose":
            m15_status, m15_detail = "warning", "M15 xác nhận lỏng (→WAITING_CONFIRMATION)"
        elif m15_q == "strict":
            m15_status, m15_detail = "pass", "M15 xác nhận chặt"
        else:
            m15_status, m15_detail = "warning", f"m15={m15_q} (không rõ)"
        gate_checks.append({"gate": "M15", "status": m15_status, "detail": m15_detail})
        # 9. Expected R:R gate
        rr_val = gate_context.get("expected_effective_rr_for_gate")
        rr_source = str(gate_context.get("expected_effective_rr_source") or "")
        nominal_rr = gate_context.get("risk_reward", "")
        nominal_str = f" (danh nghĩa {nominal_rr})" if nominal_rr else ""
        if rr_val is not None:
            min_rr = gate_context.get("min_expected_effective_rr", 1.3)
            rr_ok = rr_val >= min_rr
            rr_label = "RR base" if rr_source == "base" else "RR"
            gate_checks.append({"gate": "ExpectedRR", "status": "pass" if rr_ok else "warning",
                                "detail": f"{rr_label}={float(rr_val):.1f} sau spread{nominal_str} vs min={min_rr}"})
        else:
            gate_checks.append({"gate": "ExpectedRR", "status": "warning", "detail": "chưa có điểm vào — không có RR"})
        # 10. Score gap gate
        gap_val = gate_context.get("score_gap")
        min_gap = gate_context.get("min_buy_sell_score_gap", 10)
        if gap_val is not None:
            gap_ok = gap_val >= min_gap
            gate_checks.append({"gate": "ScoreGap", "status": "pass" if gap_ok else "warning",
                                "detail": f"gap={gap_val} vs min={min_gap}"})
        else:
            gate_checks.append({"gate": "ScoreGap", "status": "pass", "detail": "không có chênh lệch (hướng trung lập)"})
        # 11. Zone broken gate
        zone_ok = not gate_context.get("zone_broken", False)
        gate_checks.append({"gate": "ZoneBroken", "status": "pass" if zone_ok else "warning",
                            "detail": "zone intact" if zone_ok else "zone broken"})
        zone_id = gate_context.get("zone_id")
        relevance = gate_context.get("zone_relevance_score")
        relevance_ok = (
            not zone_id
            or (
                relevance is not None
                and float(relevance) >= 40
            )
        )
        gate_checks.append({
            "gate": "ZoneRelevance",
            "status": "pass" if relevance_ok else "warning",
            "detail": (
                "not applicable"
                if not zone_id
                else f"zone={zone_id}, relevance={relevance}"
            ),
        })
        relation_ok = (
            not zone_id
            or gate_context.get("zone_price_relation_valid") is not False
        )
        gate_checks.append({
            "gate": "ZonePriceRelation",
            "status": "pass" if relation_ok else "warning",
            "detail": (
                "selected zone matches scenario"
                if relation_ok
                else "selected zone differs from scenario entry"
            ),
        })
        choch_safe = not gate_context.get(
            "h4_confirmed_choch_against_direction",
            False,
        )
        gate_checks.append({
            "gate": "H4ConfirmedCHOCH",
            "status": "pass" if choch_safe else "warning",
            "detail": (
                "no confirmed opposing H4 CHOCH"
                if choch_safe
                else "opposing confirmed H4 CHOCH -> WATCH_ONLY"
            ),
        })

        gate_status = "fail" if not self._gate_result["allowed"] else ("warning" if self._gate_result["warning_codes"] else "pass")
        self._log_step(
            "gate",
            gate_status,
            f"Allowed: {'yes' if self._gate_result['allowed'] else 'NO'} "
            f"| Cap: {self._gate_result.get('decision_cap') or 'none'} "
            f"| Blocks: {len(self._gate_result.get('block_codes', []))} "
            f"| Warnings: {len(self._gate_result.get('warning_codes', []))} "
            f"| Reasons: {'; '.join(self._gate_result.get('reasons', []))}",
            {
                "allowed": self._gate_result["allowed"],
                "decision_cap": self._gate_result["decision_cap"],
                "block_codes": self._gate_result["block_codes"],
                "warning_codes": self._gate_result["warning_codes"],
                "reasons": self._gate_result["reasons"],
                "gate_checks": gate_checks,
                "account_guard_blocked": ag_blocked,
                "account_guard_block_codes": self._account_guard_result.get("block_codes", []),
            },
        )

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

        if self._macro_data_reason_code:
            combined_reason_codes.append(self._macro_data_reason_code)
        if self._macro_event_reason_code:
            combined_reason_codes.append(self._macro_event_reason_code)

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
        regime_key = (
            self._market_regime.get("primary")
            if isinstance(self._market_regime, dict) else None
        )
        self._side_score_results = {}
        feedback_by_side = (
            self._journal_feedback_by_side
            if isinstance(self._journal_feedback_by_side, dict)
            else {}
        )

        # Compute setup quality independently for BUY and SELL.  The old
        # top-level final_score remains an alias of the selected direction.
        for side in ("buy", "sell"):
            raw_side_scores = self._scores.get(side, {})
            if not isinstance(raw_side_scores, dict):
                raw_side_scores = {}
            signal_score = safe_score(
                raw_side_scores.get("signal_score", raw_side_scores.get("total")),
                0,
            )
            side_feedback = feedback_by_side.get(side, {})
            if not isinstance(side_feedback, dict):
                side_feedback = {}

            evidence_result = side_feedback.get("evidence")
            if not isinstance(evidence_result, dict):
                evidence_result = calculate_evidence_score(
                    self._closed_trades,
                    symbol=self._request.symbol,
                    direction=side,
                    regime=regime_key,
                )
            evidence_score = safe_score(
                evidence_result.get("evidence_score"),
                signal_score,
            )

            feedback_eq = side_feedback.get("average_execution_quality")
            eq_input = (
                self._execution_quality_score_in
                if self._execution_quality_score_in is not None
                else feedback_eq
            )
            eq_score, eq_source = _resolve_execution_quality(
                eq_input,
                fallback=signal_score,
            )
            if self._execution_quality_score_in is not None:
                eq_source = "shared_provided"
            elif feedback_eq is not None:
                eq_source = "side_journal"

            final_result = calculate_final_score(
                signal_score=signal_score,
                evidence_score=evidence_score,
                execution_quality_score=eq_score,
            )
            setup_score = final_result["final_score"]
            side_result = {
                "side": side,
                "signal_score": signal_score,
                "evidence_score": evidence_score,
                "execution_quality_score": eq_score,
                "execution_quality_source": eq_source,
                "setup_score": setup_score,
                "final_score": setup_score,
                "final_score_detail": final_result,
                "evidence": evidence_result,
            }
            self._side_score_results[side] = side_result
            # Keep scenario_scores useful for old clients while exposing the
            # canonical side-specific setup score.
            raw_side_scores.update({
                "evidence_score": evidence_score,
                "execution_quality_score": eq_score,
                "setup_score": setup_score,
                "final_score": setup_score,
            })

        selected_result = self._side_score_results.get(self._best_side)
        if self._best_side in {"buy", "sell"} and selected_result:
            best_signal_score = selected_result["signal_score"]
            evidence_score = selected_result["evidence_score"]
            self._evidence_result = selected_result["evidence"]
            self._eq_score = selected_result["execution_quality_score"]
            self._eq_source = selected_result["execution_quality_source"]
            self._final_score_result = selected_result["final_score_detail"]
        else:
            best_signal_score = 0
            evidence_score = 0
            self._evidence_result = {}
            self._eq_score = 0
            self._eq_source = "not_applicable_no_selected_side"
            self._final_score_result = default_final_score_result(
                "no_selected_side"
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
            thresholds=self._thresholds,
        )

        final_sc = self._final_score_result["final_score"]
        decision = self._decision_engine_result.get("decision", "?")
        action = self._decision_engine_result.get("legacy_action", "?")
        self._log_step(
            "final_score",
            "pass" if final_sc >= (self._thresholds.get("ready", 65) if self._thresholds else 65) else "warning",
            f"Signal={best_signal_score} Evidence={evidence_score} Exec={self._eq_score} "
            f"| Final={final_sc}/100 | Decision: {decision} | Action: {action}",
            {
                "signal_score": best_signal_score,
                "evidence_score": evidence_score,
                "execution_quality_score": self._eq_score,
                "execution_quality_source": self._eq_source,
                "final_score": final_sc,
                "final_score_detail": self._final_score_result,
                "decision": decision,
                "legacy_action": action,
                "entry_status": primary_entry_status,
            },
        )

    # ------------------------------------------------------------------
    # Step 9 — assemble output dict
    # ------------------------------------------------------------------

    def _assemble_result(self) -> dict[str, Any]:
        best_side = self._best_side
        best_score = self._best_score
        primary_scenario = self._primary_scenario
        structural_reject = self._structural_reject

        atr = (self._technical.get("atr_h4") or self._technical.get("atr_d1") or 0.0)
        try:
            price = float(self._technical.get("price", 0.0))
        except (TypeError, ValueError):
            price = 0.0
        if structural_reject is not None:
            fallback_scenarios = list(self._scenarios)
        elif not self._scenarios and atr > 0 and price > 0 and best_side in ("buy", "sell"):
            # Try to find the best SMC zone even beyond zone_dist_mult
            # so the scanner shows real structure instead of fake ATR fallback.
            distant_zone = selected_zone_for_side(
                self._smc_consumer_contract,
                best_side,
            )
            if distant_zone is not None:
                zone_low = float(distant_zone["low"])
                zone_high = float(distant_zone["high"])
                zone_level = float(distant_zone["level"])
                zone_score = distant_zone.get("zone_score", 0)
                sl = round(zone_low - atr * 1.0, 5) if best_side == "buy" else round(zone_high + atr * 1.0, 5)
                # Find nearest TP from opposite-side zones — must be outside entry zone
                target_zones = self._technical.get("resistance_zones" if best_side == "buy" else "support_zones", [])
                far_edge = zone_high if best_side == "buy" else zone_low
                tp_candidates = [
                    z["level"] for z in target_zones
                    if (z["level"] > far_edge if best_side == "buy" else z["level"] < far_edge)
                ]
                tp = round(min(tp_candidates), 5) if best_side == "buy" and tp_candidates else \
                     round(max(tp_candidates), 5) if best_side == "sell" and tp_candidates else None
                fallback_scenarios = [{
                    "type": best_side,
                    "priority": "primary",
                    "entry_zone": [round(zone_low, 5), round(zone_high, 5)],
                    "stop_loss": round(sl, 5),
                    "take_profit": [round(tp, 5)] if tp is not None else None,
                    "entry_zone_score": zone_score,
                    "entry_zone_id": distant_zone.get("zone_id"),
                    "entry_zone_quality_score": distant_zone.get(
                        "zone_quality_score"
                    ),
                    "entry_zone_relevance_score": distant_zone.get(
                        "zone_relevance_score"
                    ),
                    "entry_zone_setup_score": distant_zone.get(
                        "zone_setup_score"
                    ),
                    "entry_zone_scoring_version": distant_zone.get(
                        "scoring_version"
                    ),
                    "smc_score_breakdown": distant_zone.get(
                        "smc_score_breakdown",
                        {},
                    ),
                    "entry_zone_source": "smc_distant",
                    "source_zone": build_source_zone_diagnostics(
                        distant_zone,
                        atr,
                        best_side,
                    ),
                    "entry_status": "watch_zone",
                    "m15_quality": None,
                    "expected_effective_rr": None,
                    "risk_reward": None,
                    "ready_to_trade": False,
                    "trigger_type": "none",
                    "price_in_entry_zone": None,
                    "condition": f"Zone SMC cách giá {abs(price - zone_level) / atr:.1f} ATR — chỉ theo dõi, chưa vào lệnh.",
                    "invalidation": f"H1 đóng {'dưới' if best_side == 'buy' else 'trên'} {sl:.5f} hoặc spread giãn bất thường.",
                    "position_sizing": {
                        "suggested_lot": 0.01,
                        "risk_amount_usd": 0.0,
                        "entry_price": round(zone_level, 5),
                        "stop_loss": round(sl, 5),
                    },
                    "sl_source": "zone_boundary",
                }]
            else:
                if best_side == "buy":
                    sl = round(price - atr * 1.2, 5)
                    tp = round(price + atr * 2.4, 5)
                else:
                    sl = round(price + atr * 1.2, 5)
                    tp = round(price - atr * 2.4, 5)
                zone_half = round(atr * 0.25, 5)
                entry_low = round(price - zone_half, 5)
                entry_high = round(price + zone_half, 5)
                fallback_scenarios = [{
                    "type": best_side,
                    "priority": "primary",
                    "entry_zone": [entry_low, entry_high],
                    "stop_loss": sl,
                    "take_profit": [tp],
                    "entry_zone_score": 50,
                    "entry_zone_id": None,
                    "entry_zone_quality_score": None,
                    "entry_zone_relevance_score": None,
                    "entry_zone_setup_score": 50,
                    # Display-only ATR fallback; it is not an SMC v1/v2 zone
                    # and must never be counted as scorer evidence.
                    "entry_zone_scoring_version": "non-smc-display-v1",
                    "smc_score_breakdown": {},
                    "entry_zone_source": "fallback",
                    "entry_status": "watch_zone",
                    "m15_quality": None,
                    "expected_effective_rr": None,
                    "risk_reward": None,
                    "ready_to_trade": False,
                    "trigger_type": "none",
                    "price_in_entry_zone": None,
                    "condition": "Chưa có SMC zone rõ ràng, cân nhắc thêm xác nhận.",
                    "invalidation": f"H1 đóng {'dưới' if best_side == 'buy' else 'trên'} {sl:.5f} hoặc spread giãn bất thường.",
                    "position_sizing": {
                        "suggested_lot": 0.01,
                        "risk_amount_usd": 0.0,
                        "entry_price": (entry_low + entry_high) / 2,
                        "stop_loss": sl,
                    },
                }]
        else:
            fallback_scenarios = [{
                "type": "stand_aside",
                "priority": "primary",
                "reason": (
                    "No clean setup / đứng ngoài tốt hơn vì điểm "
                    "kịch bản hoặc dữ liệu chưa đủ sạch."
                ),
            }]

        return {
            "symbol": self._request.symbol,
            "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "analysis_status": (
                "structural_reject" if structural_reject is not None else "completed"
            ),
            "pipeline_route": (
                structural_reject["pipeline_route"]
                if structural_reject is not None else "full"
            ),
            "fast_path_version": (
                structural_reject["fast_path_version"]
                if structural_reject is not None else None
            ),
            "fast_reject_reason": (
                structural_reject["reason_code"]
                if structural_reject is not None else None
            ),
            "scoring_provenance": build_scoring_provenance(),
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
                "best_scenario": best_side if best_score >= (self._thresholds.get("wait", 55) if self._thresholds else 55) else "stand_aside",
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
                "decision_engine_enabled": self._decision_engine_enabled,
                "decision_engine_decision": self._decision_engine_result["decision"],
            },
            "trade_gate": self._gate_result,
            "journal_feedback": self._journal_feedback,
            "journal_feedback_by_side": self._journal_feedback_by_side,
            "account_guard": self._account_guard_result,
            "technical": _public_technical(self._technical),
            "smc": self._smc,
            "smc_scoring": self._smc_scoring_diagnostics,
            "smc_consumer": self._smc_consumer_contract,
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
            "scenarios": self._scenarios or fallback_scenarios,
            "entry_checklist": (
                [{
                    "label": "Structural SMC fast reject",
                    "status": "blocked",
                    "detail": self._trade_permission["reason"],
                }]
                if structural_reject is not None
                else _build_entry_checklist(
                    primary_scenario,
                    self._market_regime,
                    self._trade_permission,
                    self._data_quality,
                    self._scores.get(best_side, {}),
                )
            ),
            "backtest": (
                {"evaluation_status": "not_evaluated_due_to_fast_reject"}
                if structural_reject is not None
                else _conditional_backtest(
                    self._request.symbol, primary_scenario, self._h1,
                    self._best_score,
                )
            ),
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
            "side_scores": self._side_score_results,
            "evidence": self._evidence_result,
            "execution_quality": {
                "execution_quality_score": self._eq_score,
                "source": self._eq_source,
            },
            "decision_engine": self._decision_engine_result,
            "pipeline_diagnostics": self._diag,
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
    min_threshold = trade_permission.get("min_score", 65)
    if trade_permission["status"] == "blocked" or best_score < min_threshold:
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
    min_rr = trade_permission.get("min_rr", 1.3)
    rr_display = scenario.get("risk_reward", "--")
    rr_note = f"R:R tối thiểu là 1:{min_rr:.1f}."
    rr_range = _rr_range_text(scenario.get("risk_reward_range"))
    rr_effective_range = _rr_range_text(scenario.get("risk_reward_effective_range"))
    rr_base = scenario.get("expected_effective_rr_base")
    rr_parts: list[str] = []
    if rr_range:
        rr_parts.append(f"dai {rr_range}")
    if rr_effective_range:
        rr_parts.append(f"dai thuc {rr_effective_range}")
    if rr_base is not None:
        try:
            rr_parts.append(f"base sau spread ~{float(rr_base):.1f}")
        except (TypeError, ValueError):
            pass
    if rr_parts:
        rr_note = f"{rr_note} " + " | ".join(rr_parts)
    return [
        _checklist_item("Xu hướng", trend_pass, market_regime.get("primary", "unknown"), trend_note),
        _checklist_item("Vùng POI", bool(scenario.get("entry_zone")) and scenario.get("entry_status") != "invalidated", scenario.get("entry_zone", "--"), "Cần có vùng entry/POI hợp lệ và chưa bị vô hiệu."),
        _checklist_item("Xác nhận H1", bool(scenario.get("h1_confirmation")), scenario.get("trigger_type", "none"), scenario.get("invalid_reason") or "Cần nến H1 xác nhận tại vùng."),
        _checklist_item("Tin tức", not data_quality.get("news_in_3h") and trade_permission.get("status") != "blocked", data_quality.get("next_high_impact_event") or "Không có tin tác động cao gần", "Tránh vào lệnh gần tin tác động cao."),
        _checklist_item("Spread", data_quality.get("spread_status") == "normal", data_quality.get("spread_status", "unknown"), "Spread phải bình thường."),
        _checklist_item("R:R", _parse_rr(scenario.get("risk_reward")) >= min_rr, rr_display, rr_note),
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


def _rr_range_text(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    try:
        best = float(value["best"]) if value.get("best") is not None else None
        worst = float(value["worst"]) if value.get("worst") is not None else None
    except (TypeError, ValueError):
        return ""
    if best is None or worst is None:
        return ""
    if best == worst:
        return f"{best:.1f}"
    return f"{worst:.1f}-{best:.1f}"


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


def _conditional_backtest(
    symbol: str,
    scenario: dict[str, Any],
    h1_candles: list[Candle],
    best_score: int,
) -> dict[str, Any]:
    """Run replay_plan only for symbols with meaningful scores (>=50)."""
    if best_score < 50 or not scenario or not h1_candles:
        return empty_replay("score below threshold or missing data")
    return replay_plan(symbol, scenario, h1_candles)


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
