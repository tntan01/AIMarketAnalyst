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
    classify_decision,
    score_scenario,
)
from core.correlation_check import compute_correlation_adjustment
from core.final_score_engine import calculate_final_score, safe_score
from core.decision_engine import make_final_decision
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


def analyze_symbol(
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
    use_decision_engine_action: bool = False,
) -> dict[str, Any]:
    d1 = candles_by_timeframe.get("D1", [])
    h4 = candles_by_timeframe.get("H4", [])
    h1 = candles_by_timeframe.get("H1", [])
    if len(d1) < 60 or len(h4) < 60 or len(h1) < 30:
        raise ValueError("Không đủ dữ liệu D1/H4/H1 để phân tích.")

    technical = build_technical_snapshot(d1, h4, h1)
    smc = build_smc_context(d1, h4, h1)
    data_quality = build_data_quality(request, candles_by_timeframe, data_quality, technical)
    spread_status = data_quality.get("spread_status", "unknown")
    news_in_3h = bool(data_quality.get("news_in_3h", False))

    market_regime = detect_market_regime(technical, news_in_3h)
    risk_score = calc_risk_condition(
        technical["atr_h4"] or technical["atr_d1"] or 0.0,
        technical["atr_avg_14d"] or technical["atr_h4"] or technical["atr_d1"] or 0.0,
        news_in_3h,
        spread_status,
    )
    macro_alignment = macro_alignment or {"buy": 15, "sell": 15}

    # Tính correlation adjustment từ DXY/VIX/US10Y
    corr_ctx = correlation_context or {}
    buy_corr_adj = compute_correlation_adjustment(
        symbol=request.symbol,
        side="buy",
        dxy_candles=corr_ctx.get("dxy_candles"),
        us10y_candles=corr_ctx.get("us10y_candles"),
        vix_candles=corr_ctx.get("vix_candles"),
    )
    sell_corr_adj = compute_correlation_adjustment(
        symbol=request.symbol,
        side="sell",
        dxy_candles=corr_ctx.get("dxy_candles"),
        us10y_candles=corr_ctx.get("us10y_candles"),
        vix_candles=corr_ctx.get("vix_candles"),
    )

    scores = {
        "buy": score_scenario("buy", technical, smc, risk_score, macro_alignment.get("buy", 15), macro_confidence=macro_confidence, market_regime=market_regime, correlation_adjustment=buy_corr_adj, macro_context=macro_alignment),
        "sell": score_scenario("sell", technical, smc, risk_score, macro_alignment.get("sell", 15), macro_confidence=macro_confidence, market_regime=market_regime, correlation_adjustment=sell_corr_adj, macro_context=macro_alignment),
    }

    # ---- Entry quality bonus (Phase 5 Prompt 4, refactored Phase 1 backtest) ----
    # Bonus is checked for EACH side independently using that side's SMC flags
    # and scenario. This prevents the buy-biased feedback loop where only the
    # initial best_side was eligible for the bonus.
    buy_smc_flags = extract_smc_trade_flags(smc, "buy")
    sell_smc_flags = extract_smc_trade_flags(smc, "sell")
    scores["buy"]["entry_quality_bonus"] = 0
    scores["sell"]["entry_quality_bonus"] = 0

    # Build scenarios (pre-bonus scores are close enough for scenario construction)
    trade_permission_initial = calc_trade_permission(
        data_quality, risk_score,
        int(max(scores["buy"].get("signal_score", 0), scores["sell"].get("signal_score", 0))),
    )
    scenarios = build_scenarios(request, technical, smc, scores, trade_permission_initial, h1_candles=h1, m15_candles=m15_candles, correlation_context=correlation_context, quote_to_usd_rate=quote_to_usd_rate, spread_price=float(data_quality.get("spread_points") or 0))
    has_ready_plan = any(item.get("ready_to_trade") for item in scenarios)

    buy_scenario = _find_scenario(scenarios, "buy")
    sell_scenario = _find_scenario(scenarios, "sell")

    # Entry quality bonus removed (Phase 1 backtest improvement).
    # Analysis showed the bonus conditions (liquidity_sweep + displacement + M15 strict)
    # confirm entry too late — after the main move has already occurred. Trades receiving
    # the bonus had LOWER win rates than non-bonus trades in the same score bucket.
    # Bonus is kept as metadata only (recorded in score_scenario default = 0).

    # Calculate direction_bias ONCE with post-bonus scores (no recompute needed)
    direction_bias = calculate_direction_bias(scores["buy"], scores["sell"], min_gap=10)
    best_side = direction_bias["best_side"]
    if best_side == "neutral":
        if direction_bias["buy_score"] > direction_bias["sell_score"]:
            best_side = "buy"
        elif direction_bias["sell_score"] > direction_bias["buy_score"]:
            best_side = "sell"
        # Truly equal scores → stay neutral (very rare, no structural bias)
    best_score = int(max(direction_bias["buy_score"], direction_bias["sell_score"]))

    # Pick SMC flags matching the final best_side
    smc_trade_flags = buy_smc_flags if best_side == "buy" else sell_smc_flags
    primary_scenario = buy_scenario if best_side == "buy" else (sell_scenario if best_side == "sell" else (scenarios[0] if scenarios else {}))

    trade_permission = calc_trade_permission(data_quality, risk_score, best_score)

    decision_action = classify_decision(
        best_score,
        trade_permission["status"],
        has_ready_plan,
        price_in_entry_zone=bool(primary_scenario.get("price_in_entry_zone")),
        h1_confirmation=bool(primary_scenario.get("h1_confirmation")),
    )

    # --- Trade gate integration (Phase 2, enhanced Phase 5) ---------------
    gate_context = {
        "terminal_connected": data_quality.get("terminal_connected"),
        "broker_logged_in": data_quality.get("broker_logged_in"),
        "spread_status": data_quality.get("spread_status"),
        "data_quality_warning": data_quality.get("warning"),
        "high_impact_event_within_30m": data_quality.get("high_impact_event_within_30m"),
        "m15_quality": primary_scenario.get("m15_quality") if isinstance(primary_scenario, dict) else None,
        "expected_effective_rr": primary_scenario.get("expected_effective_rr") if isinstance(primary_scenario, dict) else None,
        "zone_broken": (
            smc_trade_flags.get("zone_broken", False)
            or (
                primary_scenario.get("entry_status") == "invalidated"
                or primary_scenario.get("trigger_type") == "zone_broken"
            ) if isinstance(primary_scenario, dict) else False
        ),
        "daily_loss_limit_reached": data_quality.get("daily_loss_limit_reached"),
        "weekly_loss_limit_reached": data_quality.get("weekly_loss_limit_reached"),
        "score_gap": direction_bias.get("score_gap"),
        "min_buy_sell_score_gap": direction_bias.get("min_gap", 10),
    }
    account_guard_result = check_account_guard(
        closed_trades=closed_trades or [],
        open_trades=open_trades or [],
        settings=account_guard_settings,
        action="open_new_trade",
        now=trade_date,
    )
    gate_context["account_guard"] = account_guard_result
    gate_context["daily_loss_limit_reached"] = DAILY_LOSS_LIMIT_REACHED in account_guard_result.get("block_codes", [])
    gate_context["weekly_loss_limit_reached"] = WEEKLY_LOSS_LIMIT_REACHED in account_guard_result.get("block_codes", [])
    gate_result = check_trade_gates(gate_context)

    # Merge gate result into trade_permission (backward-compatible)
    if not gate_result["allowed"]:
        trade_permission["status"] = "blocked"
        trade_permission["reason"] = "; ".join(gate_result["reasons"]) or trade_permission["reason"]
        trade_permission["gate_block_codes"] = gate_result["block_codes"]
        trade_permission["gate_warning_codes"] = gate_result["warning_codes"]
        trade_permission["decision_cap"] = gate_result["decision_cap"]
    elif gate_result["warning_codes"]:
        trade_permission["gate_warning_codes"] = gate_result["warning_codes"]
        trade_permission["decision_cap"] = gate_result["decision_cap"]

    # Apply gate cap to decision_action
    if gate_result["decision_cap"] == "TRADE_BLOCKED":
        decision_action = "stand_aside"
    elif gate_result["decision_cap"] == "WATCH_ONLY" and decision_action == "ready":
        decision_action = "watch"
    elif gate_result["decision_cap"] == "WAITING_CONFIRMATION" and decision_action == "ready":
        decision_action = "wait_for_confirmation"

    main_view = build_main_view(request.symbol, best_side, best_score, decision_action, trade_permission["status"])

    pattern_feedback: dict[str, Any] = {}
    if primary_scenario and h1:
        p_trigger = str(primary_scenario.get("trigger_type", ""))
        p_side = str(primary_scenario.get("type", ""))
        if p_trigger and p_trigger != "none" and p_side in ("buy", "sell"):
            pattern_feedback = compute_pattern_confidence(p_trigger, p_side, h1)
            adj = float(pattern_feedback.get("confidence_adjustment", 0.0))
            if adj != 0.0:
                macro_confidence = clamp(macro_confidence + adj, 0.3, 1.0)

    # ---- Phase 9: aggregate standardised reason codes ----
    best_side_scores = scores.get(best_side, {})
    scenario_codes: dict[str, Any] = primary_scenario if isinstance(primary_scenario, dict) else {}

    combined_reason_codes: list[str] = []
    combined_penalty_codes: list[str] = []
    combined_warning_codes: list[str] = []
    combined_block_codes: list[str] = []

    # From signal_engine scoring
    for code in best_side_scores.get("reason_codes", []):
        combined_reason_codes.append(code)
    for code in best_side_scores.get("penalty_codes", []):
        combined_penalty_codes.append(code)

    # From entry_engine / scenario
    for code in scenario_codes.get("reason_codes", []):
        combined_reason_codes.append(code)
    for code in scenario_codes.get("warning_codes", []):
        combined_warning_codes.append(code)
    for code in scenario_codes.get("block_codes", []):
        combined_block_codes.append(code)

    # From trade gate
    for code in gate_result.get("warning_codes", []):
        combined_warning_codes.append(code)
    for code in gate_result.get("block_codes", []):
        combined_block_codes.append(code)

    # From account guard
    for code in account_guard_result.get("warning_codes", []):
        combined_warning_codes.append(code)
    for code in account_guard_result.get("block_codes", []):
        combined_block_codes.append(code)

    reason_codes = normalize_codes(combined_reason_codes)
    penalty_codes = normalize_codes(combined_penalty_codes)
    warning_codes = normalize_codes(combined_warning_codes)
    block_codes = normalize_codes(combined_block_codes)
    all_codes = reason_codes + penalty_codes + warning_codes + block_codes
    reason_messages = codes_to_messages(all_codes)

    # ---- Phase 13: final_score metadata (metadata-only, does NOT affect decision/gate) ----
    best_side_scores_for_final = scores.get(best_side, {})
    best_signal_score = int(
        best_side_scores_for_final.get("signal_score")
        or best_side_scores_for_final.get("total")
        or best_score
    )
    # evidence_score: use real trades if caller provided them, else neutral (use signal_score).
    # execution_quality_score: use caller-provided value if valid, else neutral (use signal_score).
    if closed_trades and isinstance(closed_trades, list) and len(closed_trades) > 0:
        regime_key = market_regime.get("primary") if isinstance(market_regime, dict) else None
        evidence_result = calculate_evidence_score(
            closed_trades,
            symbol=request.symbol,
            direction=best_side,
            regime=regime_key,
        )
        evidence_score = evidence_result.get("evidence_score", best_signal_score)
    else:
        evidence_result = {"evidence_score": best_signal_score}
        evidence_score = best_signal_score

    eq_score, eq_source = _resolve_execution_quality(execution_quality_score, fallback=best_signal_score)
    final_score_result = calculate_final_score(
        signal_score=best_signal_score,
        evidence_score=evidence_score,
        execution_quality_score=eq_score,
    )

    # ---- Phase 14: decision_engine metadata (metadata-only, does NOT replace legacy decision) ----
    primary_entry_status = primary_scenario.get("entry_status") if isinstance(primary_scenario, dict) else None
    decision_engine_result = make_final_decision(
        final_score=final_score_result["final_score"],
        gate_result=gate_result,
        entry_status=primary_entry_status,
        score_gap=direction_bias.get("score_gap"),
        trade_permission=trade_permission,
    )

    return {
        "symbol": request.symbol,
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "data_quality": data_quality,
        "market_regime": market_regime,
        "direction_bias": direction_bias,
        "reason_codes": reason_codes,
        "penalty_codes": penalty_codes,
        "warning_codes": warning_codes,
        "block_codes": block_codes,
        "reason_messages": reason_messages,
        "trade_permission": trade_permission,
        "decision_summary": {
            "main_view": main_view,
            "action": decision_engine_result["legacy_action"] if use_decision_engine_action else decision_action,
            "best_scenario": best_side if best_score >= 50 else "stand_aside",
            "best_score": best_score,
            "best_side": direction_bias.get("best_side"),
            "score_gap": direction_bias.get("score_gap"),
            "is_clear_bias": direction_bias.get("is_clear_bias"),
            "min_score_gap": direction_bias.get("min_gap"),
            "gate_decision_cap": gate_result.get("decision_cap"),
            "gate_allowed": gate_result.get("allowed"),
            "gate_block_codes": gate_result.get("block_codes", []),
            "gate_warning_codes": gate_result.get("warning_codes", []),
            "account_guard_blocked": account_guard_result.get("blocked"),
            "account_guard_block_codes": account_guard_result.get("block_codes", []),
            "decision_engine_enabled": use_decision_engine_action,
            "decision_engine_decision": decision_engine_result["decision"],
        },
        "trade_gate": gate_result,
        "account_guard": account_guard_result,
        "technical": _public_technical(technical),
        "smc": smc,
        "smc_trade_flags": smc_trade_flags,
        "scenario_scores": scores,
        "macro": {
            "alignment_source": "AI" if ai_meta and ai_meta.get("provider_name") else "fallback_neutral",
            "ai_summary": ai_commentary or fallback_ai_commentary(request.symbol, best_side, best_score, trade_permission),
            "macro_confidence": macro_confidence,
        },
        "economic_events": [],
        "scenarios": scenarios or [
            {
                "type": "stand_aside",
                "priority": "primary",
                "reason": "No clean setup / đứng ngoài tốt hơn vì điểm kịch bản hoặc dữ liệu chưa đủ sạch.",
            }
        ],
        "entry_checklist": build_entry_checklist(
            primary_scenario,
            market_regime,
            trade_permission,
            data_quality,
            scores.get(best_side, {}),
        ),
        "backtest": replay_plan(request.symbol, primary_scenario, h1),
        "pattern_backtest": pattern_feedback,
        "why_not_opposite": why_not_opposite(best_side, scores),
        "confidence_reason": confidence_reason(
            technical,
            scores,
            trade_permission,
            smc,
            macro_confidence=macro_confidence,
            data_quality=data_quality,
        ),
        "risk_management": {
            "max_risk_pct": request.risk_percent,
            "warnings": [
                "Không vào lệnh 15 phút trước/sau tin đỏ.",
                "Luôn kiểm tra spread và giá broker trên MT5 trước khi vào lệnh.",
                "Nếu MT5 mất kết nối hoặc spread giãn bất thường, không vào lệnh.",
            ],
        },
        "ai_provider": ai_meta or {},
        "chart_payload": build_chart_payload(
            {**candles_by_timeframe, **({"M15": m15_candles} if m15_candles else {})}
        ),
        "final_score": final_score_result["final_score"],
        "final_score_detail": final_score_result,
        "evidence": evidence_result,
        "execution_quality": {
            "execution_quality_score": eq_score,
            "source": eq_source,
        },
        "decision_engine": decision_engine_result,
    }


def _resolve_execution_quality(value: int | float | str | None, fallback: int = 100) -> tuple[int, str]:
    """Resolve caller-provided execution_quality_score.

    Returns (score: int, source: str).  Invalid / missing input → (fallback, "fallback").
    """
    from core.final_score_engine import _is_valid_score_value

    if _is_valid_score_value(value):
        return safe_score(value, fallback), "provided"
    return fallback, "fallback_no_closed_trade_execution_data"


def build_data_quality(
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


def why_not_opposite(best_side: str, scores: dict[str, dict[str, Any]]) -> dict[str, str]:
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


def confidence_reason(
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

def build_main_view(symbol: str, side: str, score: int, action: str, permission: str) -> str:
    if action == "stand_aside":
        return f"{symbol}: No clean setup / đứng ngoài tốt hơn."
    return f"{symbol}: ưu tiên {side.upper()} có điều kiện, điểm {score}/100, quyền giao dịch {permission}."


def build_entry_checklist(
    scenario: dict[str, Any],
    market_regime: dict[str, Any],
    trade_permission: dict[str, Any],
    data_quality: dict[str, Any],
    score: dict[str, Any],
) -> list[dict[str, Any]]:
    trend_pass, trend_note = entry_trend_check(scenario, market_regime, score)
    return [
        checklist_item("Xu hướng", trend_pass, market_regime.get("primary", "unknown"), trend_note),
        checklist_item("Vùng POI", bool(scenario.get("entry_zone")) and scenario.get("entry_status") != "invalidated", scenario.get("entry_zone", "--"), "Cần có vùng entry/POI hợp lệ và chưa bị vô hiệu."),
        checklist_item("Xác nhận H1", bool(scenario.get("h1_confirmation")), scenario.get("trigger_type", "none"), scenario.get("invalid_reason") or "Cần nến H1 xác nhận tại vùng."),
        checklist_item("Tin tức", not data_quality.get("news_in_3h") and trade_permission.get("status") != "blocked", data_quality.get("next_high_impact_event") or "Không có tin tác động cao gần", "Tránh vào lệnh gần tin tác động cao."),
        checklist_item("Spread", data_quality.get("spread_status") == "normal", data_quality.get("spread_status", "unknown"), "Spread phải bình thường."),
        checklist_item("R:R", parse_rr(scenario.get("risk_reward")) >= 1.5, scenario.get("risk_reward", "--"), "R:R tối thiểu nên từ 1:1.5 trở lên."),
        checklist_item(
            "Lot",
            isinstance(scenario.get("position_sizing"), dict) and float(scenario.get("position_sizing", {}).get("suggested_lot", 0)) > 0,
            scenario.get("position_sizing", {}).get("suggested_lot", "--") if isinstance(scenario.get("position_sizing"), dict) else "--",
            "Lot chỉ tính khi entry đã xác nhận.",
        ),
    ]


def entry_trend_check(
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

def checklist_item(label: str, passed: bool, value: object, note: str) -> dict[str, Any]:
    return {"label": label, "status": "pass" if passed else "wait", "value": value, "note": note}


def parse_rr(value: object) -> float:
    text = str(value or "")
    if ":" not in text:
        return 0.0
    try:
        return float(text.split(":", 1)[1])
    except ValueError:
        return 0.0


def fallback_ai_commentary(symbol: str, best_side: str, best_score: int, trade_permission: dict[str, Any]) -> str:
    if trade_permission["status"] == "blocked" or best_score < 65:
        return (
            f"{symbol}: No clean setup / đứng ngoài tốt hơn. Hệ thống vẫn hiển thị số liệu kỹ thuật, "
            "nhưng AI chưa có nhận định riêng hoặc điều kiện giao dịch chưa sạch."
        )
    return (
        f"{symbol}: ưu tiên {best_side.upper()} có điều kiện. Chờ giá vào vùng entry, H1 xác nhận, "
        "spread bình thường và tuân thủ SL/TP do hệ thống đã tính."
    )


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
