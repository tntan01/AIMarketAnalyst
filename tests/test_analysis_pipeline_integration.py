"""Integration test for the full analyze_symbol() pipeline.

CT-5: Locks the output contract of analyze_symbol() before refactoring
CT-1 (tach AnalysisPipeline).  All changes to the pipeline must keep
these tests green.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from typing import Any
from unittest.mock import patch

import pytest

from core.analysis_engine import analyze_symbol, build_analysis_context
from core.analysis_pipeline import AnalysisPipeline
from core.market_models import Candle
from core.risk_engine import AnalysisInput
from core.reason_codes import (
    MACRO_DATA_PARTIAL,
    MACRO_DATA_UNAVAILABLE,
    MACRO_HIGH_IMPACT_EVENT_NEARBY,
)
from core.scanner import scanner_row_from_analysis
from core.scanner_candidate_engine import (
    build_candidate_order_payload,
    evaluate_scanner_candidate,
)
from core.smc_prefilter import (
    NO_ACTIONABLE_SMC_ZONE,
    NO_RAW_SMC_CANDIDATE,
    SMC_SCORING_ERROR,
)
from core.smc_scorer import score_smc
from core.smc_scoring_result import SmcScoringResult, SmcSideScoringResult


class _Context:
    def __init__(self, timeframe: str, candles: list[Candle]) -> None:
        self.timeframe = timeframe
        self.candles = candles


# ---------------------------------------------------------------------------
# Synthetic candle generators
# ---------------------------------------------------------------------------


def _trending_up_candles(
    n: int,
    *,
    start_price: float = 1.0800,
    step: float = 0.0005,
    volatility: float = 0.0010,
    start_time: datetime | None = None,
    bar_minutes: int = 60,
) -> list[Candle]:
    """Generate *n* candles in a gentle uptrend with realistic OHLCV.

    Returns candles ordered oldest → newest.
    """
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    price = start_price
    for i in range(n):
        body = step * (0.3 + 0.7 * (i % 5) / 5)  # vary step slightly
        wick = volatility * 0.4
        open_price = price
        close_price = price + body
        high_price = close_price + wick * (0.3 + 0.7 * (i % 3) / 3)
        low_price = open_price - wick * (0.2 + 0.8 * (i % 4) / 4)
        candles.append(
            Candle(
                time=t,
                open=round(open_price, 5),
                high=round(high_price, 5),
                low=round(low_price, 5),
                close=round(close_price, 5),
                volume=float(1000 + i * 10),
            )
        )
        price = close_price
        t += timedelta(minutes=bar_minutes)
    return candles


def _range_candles(
    n: int,
    *,
    center: float = 1.0800,
    amplitude: float = 0.0020,
    start_time: datetime | None = None,
    bar_minutes: int = 60,
) -> list[Candle]:
    """Generate *n* candles oscillating around *center* (range market)."""
    t = start_time or datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    price = center
    direction = 1
    for i in range(n):
        if abs(price - center) > amplitude * 0.9:
            direction *= -1  # mean-revert
        step = amplitude * 0.15 * direction
        open_price = price
        close_price = price + step
        high_price = max(open_price, close_price) + amplitude * 0.1
        low_price = min(open_price, close_price) - amplitude * 0.1
        candles.append(
            Candle(
                time=t,
                open=round(open_price, 5),
                high=round(high_price, 5),
                low=round(low_price, 5),
                close=round(close_price, 5),
                volume=float(800 + i * 5),
            )
        )
        price = close_price
        t += timedelta(minutes=bar_minutes)
    return candles


def _build_candles_by_timeframe(
    *,
    regime: str = "trending_up",
    base_price: float = 1.0800,
) -> dict[str, list[Candle]]:
    """Build a full D1/H4/H1/M15 candle set for analyze_symbol().

    All timeframes cover the same date range and share a consistent
    price series so multi-timeframe analysis works correctly.
    """
    end = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    if regime == "trending_up":
        d1 = _trending_up_candles(120, start_price=base_price - 0.0300, step=0.00025, bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _trending_up_candles(360, start_price=d1[0].open, step=0.00012, bar_minutes=240, start_time=d1[0].time)
        h1 = _trending_up_candles(480, start_price=h4[0].open, step=0.00006, bar_minutes=60, start_time=h4[0].time)
    else:  # range
        cen = base_price
        d1 = _range_candles(120, center=cen, amplitude=0.0050, bar_minutes=1440, start_time=end - timedelta(days=120))
        h4 = _range_candles(360, center=cen, amplitude=0.0040, bar_minutes=240, start_time=d1[0].time)
        h1 = _range_candles(480, center=cen, amplitude=0.0030, bar_minutes=60, start_time=h4[0].time)

    m15 = _trending_up_candles(200, start_price=h1[0].open, step=0.00002, bar_minutes=15, start_time=h1[0].time)
    return {"D1": d1, "H4": h4, "H1": h1, "M15": m15}


# ---------------------------------------------------------------------------
# Shared analysis input
# ---------------------------------------------------------------------------


def _default_input(symbol: str = "EUR/USD") -> AnalysisInput:
    return AnalysisInput(
        symbol=symbol,
        broker_symbol="EURUSDm",
        account_balance=10_000.0,
        risk_percent=2.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100_000.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )


# ---------------------------------------------------------------------------
# Contract verification helpers
# ---------------------------------------------------------------------------


def _assert_valid_decision_summary(result: dict[str, Any]) -> None:
    ds = result["decision_summary"]
    assert isinstance(ds, dict), "decision_summary must be a dict"
    assert isinstance(ds.get("main_view"), str), "main_view missing"
    assert ds.get("action") in (
        "ready", "watch", "wait_for_confirmation", "stand_aside",
    ), f"unexpected action: {ds.get('action')}"
    assert isinstance(ds.get("best_score"), int), "best_score must be int"
    assert ds["best_score"] >= 0
    assert ds.get("best_side") in ("buy", "sell", "neutral", None)
    assert isinstance(ds.get("score_gap"), (int, float)), "score_gap must be numeric"


def _assert_valid_scenarios(result: dict[str, Any]) -> None:
    scenarios = result["scenarios"]
    assert isinstance(scenarios, list), "scenarios must be a list"
    assert len(scenarios) >= 1, "at least a stand_aside scenario expected"
    for sc in scenarios:
        assert isinstance(sc, dict), f"scenario must be dict, got {type(sc)}"
        assert "type" in sc, f"scenario missing type: {sc}"
        if sc["type"] in ("buy", "sell"):
            assert "entry_zone" in sc, f"{sc['type']} scenario missing entry_zone"
            assert "stop_loss" in sc, f"{sc['type']} scenario missing stop_loss"
            assert "take_profit" in sc, f"{sc['type']} scenario missing take_profit"
            assert "entry_status" in sc, f"{sc['type']} scenario missing entry_status"
            assert sc["entry_status"] in (
                "confirmed_entry", "waiting_confirmation", "watch_zone",
                "invalidated", "no_setup",
            ), f"unexpected entry_status: {sc['entry_status']}"


def _assert_valid_trade_gate(result: dict[str, Any]) -> None:
    gate = result["trade_gate"]
    assert isinstance(gate, dict), "trade_gate must be a dict"
    assert "allowed" in gate, "trade_gate missing allowed"
    assert isinstance(gate["allowed"], bool), "allowed must be bool"
    assert "block_codes" in gate, "trade_gate missing block_codes"
    assert isinstance(gate["block_codes"], list)
    assert "warning_codes" in gate, "trade_gate missing warning_codes"
    assert isinstance(gate["warning_codes"], list)
    assert "reasons" in gate, "trade_gate missing reasons"
    assert isinstance(gate["reasons"], list)


def _assert_valid_direction_bias(result: dict[str, Any]) -> None:
    db_ = result["direction_bias"]
    assert isinstance(db_, dict), "direction_bias must be a dict"
    for key in ("best_side", "buy_score", "sell_score", "score_gap", "is_clear_bias"):
        assert key in db_, f"direction_bias missing {key}"


def _assert_valid_reason_codes(result: dict[str, Any]) -> None:
    for key in ("reason_codes", "penalty_codes", "warning_codes", "block_codes"):
        val = result[key]
        assert isinstance(val, list), f"{key} must be a list"
        for code in val:
            assert isinstance(code, str), f"{key} item must be str, got {type(code)}"


def _assert_valid_side_scores(result: dict[str, Any]) -> None:
    side_scores = result["side_scores"]
    assert isinstance(side_scores, dict)
    assert set(side_scores) == {"buy", "sell"}
    for side in ("buy", "sell"):
        score = side_scores[side]
        assert score["side"] == side
        for key in (
            "signal_score",
            "evidence_score",
            "execution_quality_score",
            "setup_score",
            "final_score",
        ):
            assert isinstance(score[key], int), f"{side}.{key} must be int"
            assert 0 <= score[key] <= 100


def _assert_valid_chart_payload(result: dict[str, Any]) -> None:
    cp_ = result["chart_payload"]
    assert isinstance(cp_, dict), "chart_payload must be a dict"
    # build_chart_payload() returns {timeframe: [candle_dicts]}
    for tf in ("D1", "H4", "H1"):
        assert tf in cp_, f"chart_payload missing timeframe {tf}"
        candles = cp_[tf]
        assert isinstance(candles, list), f"{tf} candles must be a list"
        assert len(candles) > 0, f"{tf} candles must not be empty"


def _assert_full_contract(result: dict[str, Any]) -> None:
    """Verify every key contract that downstream consumers depend on."""
    # Top-level keys (complete list from analyze_symbol return)
    required_keys = {
        "symbol", "timestamp", "data_quality", "market_regime",
        "direction_bias", "reason_codes", "penalty_codes",
        "warning_codes", "block_codes", "reason_messages",
        "trade_permission", "decision_summary", "trade_gate",
        "journal_feedback", "journal_feedback_by_side", "account_guard",
        "technical", "smc", "smc_trade_flags", "scenario_scores",
        "side_scores", "macro", "economic_events",
        "scenarios", "entry_checklist", "backtest", "pattern_backtest",
        "why_not_opposite", "confidence_reason", "risk_management",
        "ai_provider", "chart_payload", "final_score", "final_score_detail",
        "evidence", "execution_quality", "decision_engine",
    }
    missing = required_keys - set(result.keys())
    assert not missing, f"Missing top-level keys: {missing}"

    # Final score range
    fs = result["final_score"]
    assert isinstance(fs, int), f"final_score must be int, got {type(fs)}"
    assert 0 <= fs <= 100, f"final_score {fs} out of range"

    # Sub-contracts
    _assert_valid_decision_summary(result)
    _assert_valid_scenarios(result)
    _assert_valid_trade_gate(result)
    _assert_valid_direction_bias(result)
    _assert_valid_reason_codes(result)
    _assert_valid_side_scores(result)
    _assert_valid_chart_payload(result)

    # Technical snapshot
    tech = result["technical"]
    assert isinstance(tech, dict)
    for key in ("price", "ema50_d1", "ema200_d1", "atr_h4", "structure_h4",
                "support_zones", "resistance_zones"):
        assert key in tech, f"technical missing {key}"

    # Trade permission
    tp = result["trade_permission"]
    assert isinstance(tp, dict)
    assert tp["status"] in ("allowed", "caution", "blocked")

    # Entry checklist
    cl = result["entry_checklist"]
    assert isinstance(cl, list)
    for item in cl:
        assert isinstance(item, dict)
        assert "label" in item and "status" in item


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_analyze_symbol_bullish_trend_full_contract():
    """End-to-end: trending-up market must produce a structurally valid result."""
    candles = _build_candles_by_timeframe(regime="trending_up", base_price=1.0800)
    request = _default_input("EUR/USD")

    result = analyze_symbol(request, candles)

    # Full contract
    _assert_full_contract(result)

    # Bullish trend invariants
    db_ = result["direction_bias"]
    assert db_["buy_score"] > 0, "Buy score should be positive in uptrend"
    assert isinstance(result["final_score"], int)


def test_analyze_symbol_sideways_range_full_contract():
    """End-to-end: range market must not crash and must produce valid output."""
    candles = _build_candles_by_timeframe(regime="range", base_price=1.0800)
    request = _default_input("EUR/USD")

    result = analyze_symbol(request, candles)

    _assert_full_contract(result)


def test_analyze_symbol_gold_xau_full_contract():
    """End-to-end: commodity (XAU/USD) with non-standard contract size."""
    candles = _build_candles_by_timeframe(regime="trending_up", base_price=2650.0)
    request = AnalysisInput(
        symbol="XAU/USD",
        broker_symbol="XAUUSDm",
        account_balance=5_000.0,
        risk_percent=1.0,
        account_currency="USD",
        lot_step=0.01,
        minimum_lot=0.01,
        contract_size_override=100.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )

    result = analyze_symbol(request, candles)

    _assert_full_contract(result)
    # XAU/USD contract size should be 100 (not default 100,000)
    dq = result["data_quality"]
    assert dq.get("contract_size") == 100.0, f"XAU/USD contract_size should be 100, got {dq.get('contract_size')}"


def test_analyze_symbol_with_closed_trades_evidence():
    """End-to-end: providing closed trades should compute evidence score."""
    candles = _build_candles_by_timeframe(regime="trending_up", base_price=1.0800)
    request = _default_input("EUR/USD")

    closed_trades = [
        {
            "symbol": "EUR/USD", "direction": "buy", "regime": "trend_up",
            "result_r": 2.0, "result_pct": 1.5, "closed_at": "2026-06-14T12:00:00Z",
        },
        {
            "symbol": "EUR/USD", "direction": "buy", "regime": "trend_up",
            "result_r": -1.0, "result_pct": -0.8, "closed_at": "2026-06-13T12:00:00Z",
        },
    ] * 15  # 30 trades total — enough to be statistically meaningful

    result = analyze_symbol(request, candles, closed_trades=closed_trades)

    _assert_full_contract(result)
    # Evidence should be present
    evidence = result.get("evidence")
    assert isinstance(evidence, dict), "evidence must be present"
    assert "evidence_score" in evidence, f"evidence missing evidence_score: {evidence}"
    js = result.get("journal_feedback")
    assert isinstance(js, dict), "journal_feedback must be present"


def test_analyze_symbol_insufficient_candles_raises():
    """analyze_symbol must raise ValueError when D1/H4/H1 data is too short."""
    request = _default_input()
    candles = {"D1": [], "H4": [], "H1": []}

    with pytest.raises(ValueError, match="Không đủ dữ liệu"):
        analyze_symbol(request, candles)


def test_build_analysis_context_remains_importable_from_analysis_engine():
    """Legacy helper remains available from core.analysis_engine after CT-1."""
    candles = _trending_up_candles(20)

    context = build_analysis_context([_Context("H1", candles)])

    assert "H1" in context
    assert "trend" in context["H1"]
    assert "smc" in context["H1"]


def test_analyze_symbol_all_keys_present():
    """Smoke-test that every documented top-level key exists in the result."""
    candles = _build_candles_by_timeframe(regime="trending_up")
    request = _default_input()

    result = analyze_symbol(request, candles)

    # This enumerates every key actually returned — if a future refactor
    # accidentally removes or renames one, this test catches it.
    expected_keys = {
        "symbol", "timestamp", "data_quality", "market_regime",
        "direction_bias", "reason_codes", "penalty_codes",
        "warning_codes", "block_codes", "reason_messages",
        "trade_permission", "decision_summary", "trade_gate",
        "journal_feedback", "journal_feedback_by_side", "account_guard",
        "technical", "smc", "smc_trade_flags", "scenario_scores",
        "side_scores", "macro", "economic_events",
        "scenarios", "entry_checklist", "backtest", "pattern_backtest",
        "why_not_opposite", "confidence_reason", "risk_management",
        "ai_provider", "chart_payload", "final_score", "final_score_detail",
        "evidence", "execution_quality", "decision_engine",
    }
    for key in expected_keys:
        assert key in result, f"Key '{key}' missing from analyze_symbol output"


def test_fast_flags_activate_tier1_and_backtest_forces_full_path():
    """Tier 1 can reject the scanner route, while backtests remain full."""
    candles = _build_candles_by_timeframe(regime="trending_up")
    request = _default_input()

    scanner_pipeline = AnalysisPipeline()
    scanner_result = scanner_pipeline.execute(
        request,
        candles,
        scanner_fast_tier1=True,
        scanner_fast_tier2=True,
    )
    assert scanner_pipeline._scanner_fast_tier1 is True
    assert scanner_pipeline._scanner_fast_tier2 is True
    assert scanner_result["analysis_status"] == "structural_reject"
    assert scanner_result["pipeline_route"] == "post_context_reject"
    assert scanner_result["fast_path_version"] == "scanner-fast-path-v1"
    assert scanner_result["fast_reject_reason"] == NO_ACTIONABLE_SMC_ZONE
    assert {item["step"] for item in scanner_result["pipeline_diagnostics"]} == {
        "validate", "structural_reject",
    }
    assert isinstance(scanner_result["evidence"], dict)
    assert isinstance(scanner_result["decision_engine"], dict)
    row = scanner_row_from_analysis(scanner_result)
    assert row["analysis_status"] == "structural_reject"
    assert row["pipeline_route"] == "post_context_reject"
    assert row["fast_path_version"] == "scanner-fast-path-v1"
    assert row["fast_reject_reason"] == NO_ACTIONABLE_SMC_ZONE
    assert row["entry_status"] == "no_setup"
    candidate = evaluate_scanner_candidate(row)
    assert candidate.status == "OUT_OF_STRATEGY"
    assert candidate.auto_trade_candidate is False
    assert build_candidate_order_payload(row, candidate) is None

    detail_pipeline = AnalysisPipeline()
    detail_result = detail_pipeline.execute(request, candles)
    assert detail_pipeline._scanner_fast_tier1 is False
    assert detail_pipeline._scanner_fast_tier2 is False
    assert detail_result["pipeline_route"] == "full"

    backtest_pipeline = AnalysisPipeline()
    backtest_result = backtest_pipeline.execute(
        request,
        candles,
        is_backtest=True,
        scanner_fast_tier1=True,
        scanner_fast_tier2=True,
    )
    assert backtest_pipeline._scanner_fast_tier1 is False
    assert backtest_pipeline._scanner_fast_tier2 is False
    assert backtest_result["pipeline_route"] == "full"


def test_structural_reject_builder_preserves_full_contract_and_blocks_fallbacks():
    """Step 3 prepares an honest result without activating the fast route."""
    candles = _build_candles_by_timeframe(regime="trending_up")
    pipeline = AnalysisPipeline()
    pipeline.execute(_default_input(), candles)

    pipeline._prepare_structural_reject(
        "post_context",
        {
            "reason_code": NO_ACTIONABLE_SMC_ZONE,
            "fast_path_version": "scanner-fast-path-v1",
            "prefilter_version": "smc-prefilter-v1",
        },
    )
    result = pipeline._assemble_result()

    _assert_full_contract(result)
    assert result["analysis_status"] == "structural_reject"
    assert result["pipeline_route"] == "post_context_reject"
    assert result["fast_reject_reason"] == NO_ACTIONABLE_SMC_ZONE
    assert result["scenarios"] == [{
        "type": "stand_aside",
        "priority": "primary",
        "entry_status": "no_setup",
        "reason": "Structural SMC reject: NO_ACTIONABLE_SMC_ZONE",
        "reason_code": NO_ACTIONABLE_SMC_ZONE,
    }]
    assert result["trade_permission"]["status"] == "blocked"
    assert result["decision_engine"]["decision"] == "STAND_ASIDE"
    assert result["decision_summary"]["decision_engine_enabled"] is False
    assert result["trade_gate"]["evaluation_status"] == (
        "not_evaluated_due_to_fast_reject"
    )
    reject_diag = result["pipeline_diagnostics"][-1]
    assert reject_diag["step"] == "structural_reject"
    assert reject_diag["status"] == "warning"
    assert "gate" in reject_diag["details"]["skipped_steps"]
    assert result["macro"]
    assert json.dumps(result)

    row = scanner_row_from_analysis(result)
    assert isinstance(row["analysis_result"], dict)


def test_structural_reject_builder_maps_pre_smc_to_prefilter_route():
    pipeline = AnalysisPipeline()
    pipeline.execute(
        _default_input(),
        _build_candles_by_timeframe(regime="range"),
    )

    pipeline._prepare_structural_reject(
        "pre_smc",
        {"reason_code": NO_RAW_SMC_CANDIDATE},
    )
    result = pipeline._assemble_result()

    assert result["analysis_status"] == "structural_reject"
    assert result["pipeline_route"] == "prefilter_reject"
    assert result["fast_reject_reason"] == NO_RAW_SMC_CANDIDATE


def test_tier1_reject_short_circuits_all_post_context_steps():
    """A verified Tier-1 reject returns before correlation through enrichment."""
    pipeline = AnalysisPipeline()
    decision = {
        "should_reject": True,
        "fail_open": False,
        "reason_code": NO_ACTIONABLE_SMC_ZONE,
        "fast_path_version": "scanner-fast-path-v1",
        "prefilter_version": "smc-prefilter-v1",
    }

    with (
        patch(
            "core.analysis_pipeline.evaluate_post_context_prefilter",
            return_value=decision,
        ) as prefilter,
        patch.object(
            pipeline,
            "_step_compute_correlation",
            side_effect=AssertionError("correlation must be skipped"),
        ) as correlation,
        patch.object(
            pipeline,
            "_step_score_scenarios",
            side_effect=AssertionError("score must be skipped"),
        ) as score,
        patch.object(
            pipeline,
            "_step_build_trade_scenarios",
            side_effect=AssertionError("scenarios must be skipped"),
        ) as scenarios,
        patch.object(
            pipeline,
            "_step_determine_direction",
            side_effect=AssertionError("direction must be skipped"),
        ) as direction,
        patch.object(
            pipeline,
            "_step_apply_gates",
            side_effect=AssertionError("gate must be skipped"),
        ) as gate,
        patch.object(
            pipeline,
            "_step_compute_final_score",
            side_effect=AssertionError("final score must be skipped"),
        ) as final_score,
        patch.object(
            pipeline,
            "_step_enrich",
            side_effect=AssertionError("enrichment must be skipped"),
        ) as enrich,
    ):
        result = pipeline.execute(
            _default_input(),
            _build_candles_by_timeframe(regime="range"),
            scanner_fast_tier1=True,
        )

    prefilter.assert_called_once()
    for skipped_step in (
        correlation, score, scenarios, direction, gate, final_score, enrich,
    ):
        skipped_step.assert_not_called()
    assert result["analysis_status"] == "structural_reject"
    assert result["pipeline_route"] == "post_context_reject"
    assert result["scenarios"][0]["type"] == "stand_aside"


def test_tier1_survivor_reuses_precomputed_smc_and_runs_full_pipeline():
    """Tier-1 must not score SMC twice for symbols that remain on full route."""
    pipeline = AnalysisPipeline()

    def survivor_decision(
        *,
        smc: dict[str, Any],
        technical: dict[str, Any],
        market_regime: dict[str, Any],
        **_: Any,
    ) -> dict[str, Any]:
        return {
            "should_reject": False,
            "fail_open": False,
            "precomputed_smc": score_smc(
                smc,
                technical,
                market_regime,
            ),
        }

    with (
        patch(
            "core.analysis_pipeline.evaluate_post_context_prefilter",
            side_effect=survivor_decision,
        ),
        patch(
            "core.analysis_pipeline.score_smc",
            side_effect=AssertionError("v2 result must be reused"),
        ),
        patch.object(
            pipeline,
            "_step_enrich",
            wraps=pipeline._step_enrich,
        ) as enrich,
    ):
        result = pipeline.execute(
            _default_input(),
            _build_candles_by_timeframe(regime="trending_up"),
            scanner_fast_tier1=True,
        )

    assert result["analysis_status"] == "completed"
    assert result["pipeline_route"] == "full"
    steps = [item["step"] for item in result["pipeline_diagnostics"]]
    assert {"correlation", "score", "scenarios", "direction", "gate", "final_score"} <= set(steps)
    enrich.assert_called_once()


def test_tier1_malformed_precomputed_smc_fails_closed():
    """A malformed precomputed SMC result must block with SMC_SCORING_ERROR."""
    pipeline = AnalysisPipeline()
    malformed = SmcScoringResult(
        scoring_version="smc-v2",
        sides={"buy": SmcSideScoringResult(score=12, breakdown={"total": 12})},
    )
    decision = {
        "should_reject": False,
        "fail_open": False,
        "precomputed_smc": malformed,
    }
    with patch(
        "core.analysis_pipeline.evaluate_post_context_prefilter",
        return_value=decision,
    ):
        result = pipeline.execute(
            _default_input(),
            _build_candles_by_timeframe(regime="range"),
            scanner_fast_tier1=True,
        )

    assert result["analysis_status"] == "structural_reject"
    assert result["pipeline_route"] == "post_context_reject"
    assert result["fast_reject_reason"] == SMC_SCORING_ERROR


def test_disabled_tier_flags_keep_exact_baseline_except_timestamp():
    candles = _build_candles_by_timeframe(regime="trending_up")
    baseline = analyze_symbol(_default_input(), candles)
    flags_off = analyze_symbol(
        _default_input(),
        candles,
        scanner_fast_tier1=False,
        scanner_fast_tier2=False,
    )

    baseline.pop("timestamp")
    flags_off.pop("timestamp")
    assert flags_off == baseline


def test_analyze_symbol_scenarios_have_required_fields():
    """Every buy/sell scenario must carry the fields the UI and auto-trade depend on."""
    candles = _build_candles_by_timeframe(regime="trending_up")
    request = _default_input()

    result = analyze_symbol(request, candles, m15_candles=candles.get("M15"))

    for sc in result["scenarios"]:
        if sc["type"] not in ("buy", "sell"):
            continue
        for field in (
            "entry_zone", "stop_loss", "take_profit", "risk_reward",
            "expected_effective_rr", "position_sizing", "entry_status",
            "trigger_type", "price_in_entry_zone", "ready_to_trade",
            "condition", "invalidation",
        ):
            assert field in sc, f"Scenario {sc['type']} missing field '{field}'"
        sizing = sc["position_sizing"]
        assert isinstance(sizing, dict)
        for f2 in ("suggested_lot", "risk_amount_usd", "entry_price", "stop_loss"):
            assert f2 in sizing, f"position_sizing missing '{f2}'"


# ---------------------------------------------------------------------------
# Macro confidence — thiếu dữ liệu correlation
# ---------------------------------------------------------------------------


def _corr_candle_list(closes: list[float]) -> list[Candle]:
    """Build minimal candle list for one correlation source."""
    return [
        Candle(time=datetime(2026, 6, 10, tzinfo=timezone.utc),
               open=c, high=c, low=c, close=c, volume=0)
        for c in closes
    ]


def _correlation_context(present: set[str]) -> dict[str, Any]:
    """Build a correlation context with only the given sources present."""
    sources = {
        "dxy_candles": _corr_candle_list([100.0, 100.5]),
        "vix_candles": _corr_candle_list([18.0, 18.5]),
        "us10y_candles": _corr_candle_list([4.2, 4.3]),
        "us2y_candles": _corr_candle_list([4.0, 4.1]),
    }
    return {k: v for k, v in sources.items() if k in present}


def _run_correlation_step(corr_ctx: dict[str, Any]) -> tuple[float, str | None]:
    """Run only the correlation step on a fresh pipeline; return (confidence, reason_code)."""
    pipe = AnalysisPipeline()
    pipe._diag = []
    pipe._request = _default_input("EUR/USD")
    pipe._correlation_context = corr_ctx
    pipe._data_quality = {}
    pipe._macro_confidence_in = 1.0
    pipe._macro_data_reason_code = None
    pipe._macro_event_reason_code = None
    pipe._step_compute_correlation()
    return pipe._macro_confidence_in, pipe._macro_data_reason_code


def test_macro_confidence_kept_when_all_sources_present():
    conf, code = _run_correlation_step(_correlation_context(
        {"dxy_candles", "vix_candles", "us10y_candles", "us2y_candles"}
    ))
    assert conf == 1.0
    assert code is None


def test_macro_confidence_reduced_when_partial_missing():
    conf, code = _run_correlation_step(_correlation_context({"dxy_candles"}))
    assert conf == 0.8
    assert code == MACRO_DATA_PARTIAL


def test_macro_confidence_reduced_strongly_when_all_missing():
    conf, code = _run_correlation_step({})
    assert conf == 0.4
    assert code == MACRO_DATA_UNAVAILABLE


def test_macro_data_reason_code_flows_into_result():
    """End-to-end: thiếu toàn bộ dữ liệu vĩ mô -> reason code xuất hiện trong kết quả."""
    candles = _build_candles_by_timeframe(regime="trending_up")
    request = _default_input("EUR/USD")

    result = analyze_symbol(request, candles, correlation_context={})

    assert MACRO_DATA_UNAVAILABLE in result["reason_codes"], (
        f"MACRO_DATA_UNAVAILABLE missing from reason_codes: {result['reason_codes']}"
    )
    assert result["macro"]["macro_confidence"] < 1.0


def _run_event_window_step(hours_until: float | None) -> tuple[float, str | None]:
    """Run correlation step với sự kiện high-impact USD cách `hours_until` giờ; return (confidence, event_reason_code)."""
    pipe = AnalysisPipeline()
    pipe._diag = []
    pipe._request = _default_input("EUR/USD")
    pipe._correlation_context = _correlation_context(
        {"dxy_candles", "vix_candles", "us10y_candles", "us2y_candles"}
    )
    pipe._macro_confidence_in = 1.0
    pipe._macro_data_reason_code = None
    pipe._macro_event_reason_code = None
    if hours_until is None:
        pipe._data_quality = {}
    else:
        event_time = datetime.now(timezone.utc) + timedelta(hours=hours_until)
        pipe._data_quality = {
            "next_high_impact_event": {
                "currency": "USD",
                "impact": "high",
                "time_utc": event_time.isoformat(),
            }
        }
    pipe._step_compute_correlation()
    return pipe._macro_confidence_in, pipe._macro_event_reason_code


def test_event_window_within_blackout_keeps_confidence():
    """Sự kiện trong vòng 30 phút (blackout hiện có) → không giảm macro confidence."""
    conf, code = _run_event_window_step(hours_until=0.2)
    assert conf == 1.0
    assert code is None


def test_event_window_within_4h_reduces_confidence():
    """Sự kiện trong 4 giờ tới (ngoài blackout 30 phút) → giảm macro confidence + reason code."""
    conf, code = _run_event_window_step(hours_until=2.0)
    assert conf == 0.8
    assert code == MACRO_HIGH_IMPACT_EVENT_NEARBY


def test_event_window_outside_4h_keeps_confidence():
    """Sự kiện ngoài 4 giờ tới → không giảm macro confidence."""
    conf, code = _run_event_window_step(hours_until=6.0)
    assert conf == 1.0
    assert code is None


def test_event_window_no_event_keeps_confidence():
    """Không có sự kiện high-impact → không giảm macro confidence."""
    conf, code = _run_event_window_step(hours_until=None)
    assert conf == 1.0
    assert code is None


def test_event_window_unrelated_currency_keeps_confidence():
    """Sự kiện high-impact không thuộc đồng tiền của cặp → không giảm."""
    pipe = AnalysisPipeline()
    pipe._diag = []
    pipe._request = _default_input("EUR/GBP")
    pipe._correlation_context = _correlation_context(
        {"dxy_candles", "vix_candles", "us10y_candles", "us2y_candles"}
    )
    pipe._macro_confidence_in = 1.0
    pipe._macro_data_reason_code = None
    pipe._macro_event_reason_code = None
    event_time = datetime.now(timezone.utc) + timedelta(hours=2.0)
    pipe._data_quality = {
        "next_high_impact_event": {
            "currency": "USD",
            "impact": "high",
            "time_utc": event_time.isoformat(),
        }
    }
    pipe._step_compute_correlation()
    assert pipe._macro_confidence_in == 1.0
    assert pipe._macro_event_reason_code is None


def test_event_window_reason_code_flows_into_result():
    """End-to-end: sự kiện high-impact liên quan trong 4h → reason code xuất hiện trong kết quả."""
    candles = _build_candles_by_timeframe(regime="trending_up")
    request = _default_input("EUR/USD")
    now = datetime.now(timezone.utc)
    event_time = now + timedelta(hours=2.0)
    data_quality = {
        "next_high_impact_event": {
            "currency": "USD",
            "impact": "high",
            "time_utc": event_time.isoformat(),
        }
    }

    result = analyze_symbol(
        request,
        candles,
        correlation_context=_correlation_context(
            {"dxy_candles", "vix_candles", "us10y_candles", "us2y_candles"}
        ),
        data_quality=data_quality,
    )

    assert MACRO_HIGH_IMPACT_EVENT_NEARBY in result["reason_codes"], (
        f"MACRO_HIGH_IMPACT_EVENT_NEARBY missing from reason_codes: {result['reason_codes']}"
    )
    assert result["macro"]["macro_confidence"] < 1.0
