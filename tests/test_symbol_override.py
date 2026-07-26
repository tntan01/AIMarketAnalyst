"""Phase-0 scanner auto-trade safety tests.

These tests intentionally assert the opposite of the legacy override behavior:
WATCH/WAIT/STAND_ASIDE never execute and a configured side never falls back to
the opposite scenario.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.scanner_safety import (
    BRANCH_BACKTEST_INVALID,
    BRANCH_BACKTEST_CONFIGURED,
    BRANCH_DEFAULT_RULES,
    evaluate_auto_trade_safety,
)
from core.backtest_contract import validation_engine_contract
from core.backtest_config_validation import (
    BACKTEST_CONFIG_SCHEMA_VERSION,
    BACKTEST_VALIDATION_VERSION,
    validation_fingerprint,
)
from tests.phase7_helpers import ready_release_report


def _scenario(side: str = "buy", **overrides) -> dict:
    value = {
        "type": side,
        "entry_zone": [1.0850, 1.0875],
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "m15_quality": "strict",
        "stop_loss": 1.0820 if side == "buy" else 1.0950,
        "take_profit": [1.0920] if side == "buy" else [1.0850],
        "expected_effective_rr": 2.5,
        "risk_reward": "1:2.5",
        "position_sizing": {"suggested_lot": 0.1},
    }
    value.update(overrides)
    return value


def _make_row(**overrides) -> dict:
    row = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "best_side": "buy",
        "best_score": 75,
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
        "expected_effective_rr": 2.5,
        "journal_feedback": {},
        "analysis_result": {
            "trade_gate": {"allowed": True, "decision_cap": None},
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "technical": {"price": 1.0860},
            "scenarios": [_scenario()],
        },
    }
    row.update(overrides)
    return row


def _backtest_config(**overrides) -> dict:
    engine_contract = validation_engine_contract()
    config = {
        "schema_version": BACKTEST_CONFIG_SCHEMA_VERSION,
        "validation_version": BACKTEST_VALIDATION_VERSION,
        "engine_contract_version": engine_contract["contract_version"],
        "engine_version": engine_contract["engine_version"],
        "purpose": engine_contract["purpose"],
        "execution_parity": engine_contract["execution_parity"],
        "data_manifest_version": engine_contract[
            "data_manifest_version"
        ],
        "point_in_time_data": engine_contract["point_in_time_data"],
        "dataset_hash": "a" * 64,
        "data_quality_status": "OK",
        "execution_policy_version": engine_contract[
            "execution_policy_version"
        ],
        "entry_fill_model": engine_contract["entry_fill_model"],
        "exit_evaluation_model": engine_contract[
            "exit_evaluation_model"
        ],
        "same_bar_ambiguity_policy": engine_contract[
            "same_bar_ambiguity_policy"
        ],
        "execution_timeframe": engine_contract["execution_timeframe"],
        "synthetic_trades_allowed": engine_contract[
            "synthetic_trades_allowed"
        ],
        "execution_mode": engine_contract["execution_mode"],
        "execution_model_version": engine_contract[
            "execution_model_version"
        ],
        "cost_model_version": engine_contract["cost_model_version"],
        "quote_conversion_model_version": engine_contract[
            "quote_conversion_model_version"
        ],
        "cost_model_fingerprint": engine_contract[
            "cost_model_fingerprint"
        ],
        "quote_conversion_fingerprint": engine_contract[
            "quote_conversion_fingerprint"
        ],
        "candidate_ledger_version": engine_contract["candidate_ledger_version"],
        "candidate_replay_version": engine_contract["candidate_replay_version"],
        "frozen_strategy_version": engine_contract["frozen_strategy_version"],
        "frozen_strategy_applied": engine_contract["frozen_strategy_applied"],
        "oos_replay": engine_contract["oos_replay"],
        "provenance_version": "backtest-provenance-v1",
        "code_revision": "b" * 40,
        "request_fingerprint": "c" * 64,
        "execution_fingerprint": "d" * 64,
        "provenance_fingerprint": "e" * 64,
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
        "min_rr": 2.0,
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
        "statistics_version": "backtest-statistics-v1",
        "probability_positive_edge_pct": 97.5,
        "one_sided_p_value": 0.025,
        "minimum_required_trades": 8,
        "statistical_power_passed": True,
        "walk_forward_windows": 3,
        "walk_forward_verdict": "ROBUST",
        "validated_at": "2026-07-24T00:00:00+00:00",
        "expires_at": "2027-07-24T00:00:00+00:00",
        "release_report": ready_release_report(),
    }
    config.update(overrides)
    config["validation_fingerprint"] = validation_fingerprint(config)
    return config


def test_default_branch_ready_passes():
    decision = evaluate_auto_trade_safety(_make_row())
    assert decision.branch == BRANCH_DEFAULT_RULES
    assert decision.auto_trade_candidate is True


def test_default_branch_watch_fails():
    decision = evaluate_auto_trade_safety(
        _make_row(scanner_action="watch", scanner_decision="WATCH_ONLY")
    )
    assert decision.auto_trade_candidate is False
    assert "SCANNER_NOT_READY" in decision.reason_codes
    assert "DECISION_NOT_READY" in decision.reason_codes


def test_backtest_branch_stand_aside_fails_even_when_thresholds_pass():
    decision = evaluate_auto_trade_safety(
        _make_row(
            scanner_action="stand_aside",
            scanner_decision="STAND_ASIDE",
            scanner_group="blocked",
        ),
        _backtest_config(),
    )
    assert decision.branch == BRANCH_BACKTEST_CONFIGURED
    assert decision.strategy_eligible is True
    assert decision.execution_ready is False
    assert decision.auto_trade_candidate is False


def test_backtest_branch_wait_fails_even_when_thresholds_pass():
    decision = evaluate_auto_trade_safety(
        _make_row(
            scanner_action="wait_for_confirmation",
            scanner_decision="WAITING_CONFIRMATION",
        ),
        _backtest_config(),
    )
    assert decision.auto_trade_candidate is False


def test_forced_side_mismatch_fails_closed():
    decision = evaluate_auto_trade_safety(
        _make_row(best_side="sell"),
        _backtest_config(side="buy"),
    )
    assert decision.auto_trade_candidate is False
    assert "CONFIG_SIDE_MISMATCH" in decision.reason_codes


def test_forced_buy_never_falls_back_to_sell_scenario():
    row = _make_row(
        best_side="buy",
        analysis_result={
            "trade_gate": {"allowed": True, "decision_cap": None},
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "scenarios": [_scenario("sell")],
        },
    )
    decision = evaluate_auto_trade_safety(row, _backtest_config(side="buy"))
    assert decision.scenario is None
    assert decision.auto_trade_candidate is False
    assert "MISSING_SELECTED_SIDE_SCENARIO" in decision.reason_codes


def test_backtest_uses_setup_score_not_best_score():
    decision = evaluate_auto_trade_safety(
        _make_row(best_score=99, final_score=55, setup_score=55),
        _backtest_config(min_score=65),
    )
    assert decision.auto_trade_candidate is False
    assert "SETUP_SCORE_BELOW_MIN" in decision.reason_codes


def test_missing_setup_score_fails_closed():
    row = _make_row()
    row.pop("setup_score")
    decision = evaluate_auto_trade_safety(row, _backtest_config())
    assert decision.auto_trade_candidate is False
    assert "SETUP_SCORE_MISSING" in decision.reason_codes


def test_default_branch_missing_setup_score_fails_closed():
    row = _make_row()
    row.pop("setup_score")
    decision = evaluate_auto_trade_safety(row)
    assert decision.auto_trade_candidate is False
    assert "SETUP_SCORE_MISSING" in decision.reason_codes


def test_missing_backtest_min_rr_fails_closed():
    decision = evaluate_auto_trade_safety(
        _make_row(),
        _backtest_config(min_rr=0),
    )
    assert decision.auto_trade_candidate is False
    assert "BACKTEST_MIN_RR_MISSING" in decision.reason_codes


def test_malformed_backtest_config_routes_invalid_and_fails_closed():
    decision = evaluate_auto_trade_safety(_make_row(), "invalid")  # type: ignore[arg-type]
    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert decision.auto_trade_candidate is False
    assert "BACKTEST_CONFIG_INVALID" in decision.reason_codes
    assert "BACKTEST_CONFIG_MALFORMED" in decision.reason_codes


def test_selected_scenario_rr_is_used():
    row = _make_row(
        expected_effective_rr=9.0,
        analysis_result={
            "trade_gate": {"allowed": True, "decision_cap": None},
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "scenarios": [_scenario(expected_effective_rr=1.2)],
        },
    )
    decision = evaluate_auto_trade_safety(row, _backtest_config(min_rr=2.0))
    assert decision.auto_trade_candidate is False
    assert "EXPECTED_RR_BELOW_MIN" in decision.reason_codes


def test_trade_gate_must_be_explicitly_allowed():
    row = _make_row()
    row["analysis_result"]["trade_gate"] = {"allowed": "yes"}
    decision = evaluate_auto_trade_safety(row)
    assert decision.auto_trade_candidate is False
    assert "TRADE_GATE_NOT_ALLOWED" in decision.reason_codes


def test_entry_must_be_confirmed_and_ready():
    row = _make_row(
        analysis_result={
            "trade_gate": {"allowed": True, "decision_cap": None},
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "scenarios": [
                _scenario(
                    entry_status="waiting_confirmation",
                    ready_to_trade=False,
                )
            ],
        },
    )
    decision = evaluate_auto_trade_safety(row)
    assert decision.auto_trade_candidate is False
    assert "ENTRY_NOT_CONFIRMED" in decision.reason_codes
    assert "SCENARIO_NOT_READY" in decision.reason_codes


def test_missing_execution_data_fails_closed():
    row = _make_row(
        analysis_result={
            "trade_gate": {"allowed": True, "decision_cap": None},
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "scenarios": [
                _scenario(entry_zone=None, stop_loss=None, take_profit=None)
            ],
        },
    )
    decision = evaluate_auto_trade_safety(row)
    assert decision.auto_trade_candidate is False
    assert "ENTRY_ZONE_MISSING" in decision.reason_codes
    assert "STOP_LOSS_MISSING" in decision.reason_codes
    assert "TAKE_PROFIT_MISSING" in decision.reason_codes


def run_all_tests() -> None:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
    print(f"PASS: {len(tests)} Phase-0 scanner safety tests")


if __name__ == "__main__":
    run_all_tests()
