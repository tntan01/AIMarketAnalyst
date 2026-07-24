"""Phase-1 domain model and side-consistency tests."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.analysis_pipeline import AnalysisPipeline
from core.scanner import scanner_row_from_analysis
from core.scanner_candidate_engine import (
    build_candidate_order_payload,
    evaluate_scanner_candidate,
)
from core.scanner_models import (
    BLOCKED,
    DATA_UNAVAILABLE,
    OUT_OF_STRATEGY,
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
)
from core.scanner_strategy_engine import evaluate_sides
from core.backtest_config_validation import validation_fingerprint


def _scenario(side: str, **overrides) -> dict:
    payload = {
        "type": side,
        "entry_zone": [1.0850, 1.0875],
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "m15_quality": "strict",
        "stop_loss": 1.0820 if side == "buy" else 1.0950,
        "take_profit": [1.0920] if side == "buy" else [1.0850],
        "expected_effective_rr": 2.0 if side == "buy" else 1.5,
    }
    payload.update(overrides)
    return payload


def _row(**overrides) -> dict:
    analysis = {
        "scenario_scores": {
            "buy": {"signal_score": 78},
            "sell": {"signal_score": 61},
        },
        "side_scores": {
            "buy": {
                "signal_score": 78,
                "evidence_score": 70,
                "execution_quality_score": 75,
                "setup_score": 72,
            },
            "sell": {
                "signal_score": 61,
                "evidence_score": 66,
                "execution_quality_score": 70,
                "setup_score": 64,
            },
        },
        "decision_engine": {
            "decision": "READY_TO_TRADE",
            "legacy_action": "ready",
        },
        "trade_gate": {"allowed": True, "decision_cap": None},
        "scenarios": [_scenario("buy"), _scenario("sell")],
    }
    payload = {
        "symbol": "EUR/USD",
        "best_side": "buy",
        "buy_score": 78,
        "sell_score": 61,
        "best_score": 78,
        "final_score": 72,
        "setup_score": 72,
        "market_regime": "range",
        "direction_bias": {
            "best_side": "buy",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
        "score_gap": 17,
        "min_score": 65,
        "min_rr": 1.3,
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "journal_feedback": {},
        "analysis_result": analysis,
    }
    payload.update(overrides)
    return payload


def _backtest_config(**overrides) -> dict:
    payload = {
        "schema_version": 4,
        "validation_version": "phase8-smc-v2-oos-v1",
        "config_id": "EURUSD-range-buy-v3",
        "status": "VALIDATED",
        "scorer_version": "scanner-v3",
        "feature_version": "scanner-features-v3",
        "smc_scorer_version": "smc-v2",
        "smc_scoring_mode": "v2",
        "symbol": "EUR/USD",
        "allowed_regimes": ["range"],
        "regime": "range",
        "side": "buy",
        "min_score": 65,
        "min_rr": 1.5,
        "score_metric": "setup_score",
        "trained_from": "2025-01-01T00:00:00+00:00",
        "trained_to": "2025-06-30T00:00:00+00:00",
        "validated_from": "2025-07-01T00:00:00+00:00",
        "validated_to": "2025-12-31T00:00:00+00:00",
        "in_sample_trades": 120,
        "out_of_sample_trades": 46,
        "oos_expectancy_r": 0.24,
        "oos_profit_factor": 1.42,
        "oos_max_drawdown_r": 5.8,
        "expectancy_ci_low": 0.05,
        "expectancy_ci_high": 0.43,
        "walk_forward_windows": 3,
        "walk_forward_verdict": "ROBUST",
        "validated_at": "2026-07-24T00:00:00+00:00",
        "expires_at": "2027-07-24T00:00:00+00:00",
    }
    payload.update(overrides)
    payload["validation_fingerprint"] = validation_fingerprint(payload)
    return payload


def test_buy_and_sell_are_evaluated_independently():
    buy, sell = evaluate_sides(_row())

    assert buy.side == "buy"
    assert buy.signal_score == 78
    assert buy.setup_score == 72
    assert buy.scenario is not None and buy.scenario["type"] == "buy"
    assert buy.expected_effective_rr == 2.0
    assert buy.gate_result.get("allowed") is True

    assert sell.side == "sell"
    assert sell.signal_score == 61
    assert sell.setup_score == 64
    assert sell.scenario is not None and sell.scenario["type"] == "sell"
    assert sell.expected_effective_rr == 1.5
    assert sell.gate_result == {}


def test_legacy_row_does_not_borrow_selected_setup_score_for_opposite_side():
    row = _row()
    row["analysis_result"].pop("side_scores")
    _, sell = evaluate_sides(row)
    assert sell.setup_score is None
    assert "SETUP_SCORE_NOT_SELECTED_SIDE" in sell.reason_codes


def test_candidate_has_exactly_one_selected_side():
    decision = evaluate_scanner_candidate(_row())
    assert decision.status == READY_NOW
    assert decision.selected_side == "buy"
    assert decision.side_evaluation is not None
    assert decision.side_evaluation.side == decision.selected_side
    assert decision.scenario is not None
    assert decision.scenario["type"] == decision.selected_side


def test_score_rr_sl_tp_all_belong_to_selected_side():
    decision = evaluate_scanner_candidate(_row(), _backtest_config())
    selected = decision.side_evaluation
    assert selected is not None
    assert decision.setup_score == selected.setup_score == 72
    assert decision.strategy.expected_effective_rr == selected.expected_effective_rr
    assert selected.stop_loss == selected.scenario["stop_loss"]
    assert selected.take_profit == selected.scenario["take_profit"]


def test_shared_order_payload_is_derived_from_candidate_side():
    row = _row()
    decision = evaluate_scanner_candidate(row, _backtest_config())
    payload = build_candidate_order_payload(row, decision)

    assert payload is not None
    assert payload["side"] == decision.selected_side == "buy"
    assert payload["setup_score"] == decision.setup_score == 72
    assert payload["stop_loss"] == decision.side_evaluation.stop_loss
    assert payload["take_profit"] == decision.side_evaluation.take_profit[0]
    assert payload["entry_price"] == payload["entry_high"]


def test_shared_order_payload_rejects_snapshot_price_outside_entry_zone():
    row = _row()
    row["analysis_result"]["technical"] = {"price": 1.1000}
    decision = evaluate_scanner_candidate(row)

    assert build_candidate_order_payload(row, decision) is None
    assert (
        build_candidate_order_payload(
            row,
            decision,
            require_price_in_zone=False,
        )
        is not None
    )


def test_execution_readiness_requires_strict_m15():
    row = _row()
    row["analysis_result"]["scenarios"][0]["m15_quality"] = "loose"
    decision = evaluate_scanner_candidate(row)

    assert decision.auto_trade_candidate is False
    assert "M15_NOT_STRICT" in decision.reason_codes


def test_execution_readiness_requires_rr_at_strategy_threshold():
    row = _row()
    row["analysis_result"]["scenarios"][0]["expected_effective_rr"] = 1.2
    decision = evaluate_scanner_candidate(row)

    assert decision.auto_trade_candidate is False
    assert "EXPECTED_EFFECTIVE_RR_BELOW_MIN" in decision.reason_codes


def test_execution_readiness_rejects_broken_zone():
    row = _row()
    row["analysis_result"]["scenarios"][0]["zone_broken"] = True
    decision = evaluate_scanner_candidate(row)

    assert decision.auto_trade_candidate is False
    assert "ZONE_BROKEN" in decision.reason_codes


def test_execution_readiness_rejects_stale_analysis():
    row = _row()
    row["analysis_result"]["data_quality"] = {"is_delayed": True}
    decision = evaluate_scanner_candidate(row)

    assert decision.auto_trade_candidate is False
    assert "DATA_STALE" in decision.reason_codes


def test_execution_readiness_rejects_any_non_null_gate_cap():
    row = _row()
    row["analysis_result"]["trade_gate"]["decision_cap"] = "CUSTOM_CAP"
    decision = evaluate_scanner_candidate(row)

    assert decision.auto_trade_candidate is False
    assert "TRADE_GATE_DECISION_CAP" in decision.reason_codes


def test_pipeline_computes_setup_score_for_both_sides():
    pipeline = AnalysisPipeline.__new__(AnalysisPipeline)
    pipeline._scores = {
        "buy": {"signal_score": 80},
        "sell": {"signal_score": 60},
    }
    pipeline._best_side = "buy"
    pipeline._best_score = 80
    pipeline._market_regime = {"primary": "range"}
    pipeline._journal_feedback_by_side = {
        "buy": {
            "evidence": {"evidence_score": 70},
            "average_execution_quality": 90,
        },
        "sell": {
            "evidence": {"evidence_score": 40},
            "average_execution_quality": 50,
        },
    }
    pipeline._closed_trades = []
    pipeline._request = SimpleNamespace(symbol="EUR/USD")
    pipeline._execution_quality_score_in = None
    pipeline._primary_scenario = {"entry_status": "confirmed_entry"}
    pipeline._gate_result = {"allowed": True, "decision_cap": None}
    pipeline._direction_bias = {"score_gap": 20}
    pipeline._trade_permission = {"status": "allowed"}
    pipeline._thresholds = {
        "ready": 65,
        "watch": 60,
        "wait": 55,
        "min_score_gap": 10,
    }
    pipeline._diag = []

    pipeline._step_compute_final_score()

    buy = pipeline._side_score_results["buy"]
    sell = pipeline._side_score_results["sell"]
    assert buy["setup_score"] == 80
    assert sell["setup_score"] == 54
    assert pipeline._final_score_result["final_score"] == buy["setup_score"]
    assert pipeline._scores["buy"]["setup_score"] == 80
    assert pipeline._scores["sell"]["setup_score"] == 54


def test_opposite_configured_side_is_out_of_strategy():
    decision = evaluate_scanner_candidate(
        _row(),
        _backtest_config(side="sell"),
    )
    assert decision.status == OUT_OF_STRATEGY
    assert decision.auto_trade_candidate is False
    assert decision.selected_side == "sell"
    assert "CONFIG_SIDE_MISMATCH" in decision.reason_codes


def test_sell_candidate_uses_sell_setup_score_not_buy_alias():
    row = _row(
        best_side="sell",
        best_score=61,
        final_score=64,
        setup_score=64,
        direction_bias={
            "best_side": "sell",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
    )
    decision = evaluate_scanner_candidate(
        row,
        _backtest_config(side="sell", min_score=63, min_rr=1.4),
    )

    assert decision.status == READY_NOW
    assert decision.selected_side == "sell"
    assert decision.setup_score == 64
    assert decision.side_evaluation is not None
    assert decision.side_evaluation.signal_score == 61
    assert decision.scenario is not None
    assert decision.scenario["type"] == "sell"


def test_waiting_status_is_canonical():
    row = _row(
        scanner_action="wait_for_confirmation",
        scanner_decision="WAITING_CONFIRMATION",
    )
    row["analysis_result"]["decision_engine"]["decision"] = "WAITING_CONFIRMATION"
    row["analysis_result"]["scenarios"][0].update({
        "entry_status": "waiting_confirmation",
        "ready_to_trade": False,
    })
    decision = evaluate_scanner_candidate(row)
    assert decision.status == WAITING_CONFIRMATION
    assert decision.execution_ready is False


def test_watch_status_is_canonical():
    row = _row(scanner_action="watch", scanner_decision="WATCH_ONLY")
    row["analysis_result"]["decision_engine"]["decision"] = "WATCH_ONLY"
    row["analysis_result"]["scenarios"][0].update({
        "entry_status": "watch_zone",
        "ready_to_trade": False,
    })
    decision = evaluate_scanner_candidate(row)
    assert decision.status == WATCH_ZONE


def test_permission_block_maps_to_blocked():
    decision = evaluate_scanner_candidate(
        _row(trade_permission="blocked", scanner_group="blocked")
    )
    assert decision.status == BLOCKED
    assert decision.trade_allowed is False


def test_stand_aside_maps_to_out_of_strategy_not_data_error():
    decision = evaluate_scanner_candidate(
        _row(
            best_side="stand_aside",
            scanner_action="stand_aside",
            scanner_decision="STAND_ASIDE",
        )
    )
    assert decision.status == OUT_OF_STRATEGY
    assert "NO_TRADE_SIDE" in decision.reason_codes


def test_missing_analysis_maps_to_data_unavailable():
    decision = evaluate_scanner_candidate(_row(analysis_result=None))
    assert decision.status == DATA_UNAVAILABLE
    assert decision.auto_trade_candidate is False


def test_decision_serialization_is_structured_and_scenario_optional():
    decision = evaluate_scanner_candidate(_row(), _backtest_config())
    payload = decision.to_dict()
    assert payload["branch"] == "BACKTEST_VALIDATED"
    assert payload["selected_side"] == "buy"
    assert payload["strategy"]["eligible"] is True
    assert payload["execution"]["entry_ready"] is True
    assert set(payload["side_evaluations"]) == {"buy", "sell"}
    assert "scenario" not in payload


def test_scanner_row_never_falls_back_to_opposite_plan():
    result = {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {"signal_score": 80, "macro_alignment": 15},
            "sell": {"signal_score": 60, "macro_alignment": 15},
        },
        "direction_bias": {"best_side": "buy", "score_gap": 20},
        "trade_permission": {
            "status": "allowed",
            "min_score": 65,
            "min_rr": 1.3,
        },
        "decision_engine": {
            "decision": "READY_TO_TRADE",
            "legacy_action": "ready",
        },
        "decision_summary": {"score_gap": 20},
        "trade_gate": {"allowed": True, "decision_cap": None},
        "scenarios": [_scenario("sell")],
        "technical": {"price": 1.0860, "atr_h4": 0.01},
        "market_regime": {"primary": "range"},
        "data_quality": {},
        "final_score": 70,
    }
    row = scanner_row_from_analysis(result)
    assert row["best_side"] == "buy"
    assert row["best_score"] == 80
    assert row["expected_effective_rr"] is None
    assert row["entry_zone"] is None


def test_scanner_row_preserves_neutral_direction_as_stand_aside():
    result = {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {"signal_score": 70, "macro_alignment": 15},
            "sell": {"signal_score": 68, "macro_alignment": 15},
        },
        "direction_bias": {"best_side": "neutral", "score_gap": 2},
        "trade_permission": {"status": "caution"},
        "decision_engine": {
            "decision": "WAITING_CONFIRMATION",
            "legacy_action": "wait_for_confirmation",
        },
        "decision_summary": {"score_gap": 2},
        "trade_gate": {"allowed": True, "decision_cap": "WAITING_CONFIRMATION"},
        "scenarios": [_scenario("buy"), _scenario("sell")],
        "technical": {"price": 1.0860, "atr_h4": 0.01},
        "market_regime": {"primary": "range"},
        "data_quality": {},
        "final_score": 65,
    }
    row = scanner_row_from_analysis(result)
    assert row["best_side"] == "stand_aside"
    decision = evaluate_scanner_candidate(row)
    assert decision.status == OUT_OF_STRATEGY
    assert decision.selected_side is None


def run_all_tests() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} Phase-1 domain model tests")


if __name__ == "__main__":
    run_all_tests()
