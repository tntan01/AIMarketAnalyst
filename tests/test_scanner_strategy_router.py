"""Phase-2 Strategy Router branch, validation and lifecycle tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.settings import SymbolScanSettings
from core.backtest_contract import validation_engine_contract
from controllers.scanner_controller import ScannerController
from core.backtest_config import (
    analysis_thresholds_for_symbol,
    apply_validated_backtest_config,
    preserve_or_invalidate_manual_config,
    serialize_backtest_config,
)
from core.backtest_config_validation import (
    BACKTEST_CONFIG_SCHEMA_VERSION,
    BACKTEST_VALIDATION_VERSION,
    validation_fingerprint,
)
from core.scanner_candidate_engine import evaluate_scanner_candidate
from core.scanner import ScannerRequest
from core.scanner_models import (
    BRANCH_BACKTEST_INVALID,
    BRANCH_BACKTEST_VALIDATED,
    BRANCH_DEFAULT_RULES,
    CONFIG_EXPIRED,
    CONFIG_VALIDATED,
    CONFIG_VERSION_MISMATCH,
    OUT_OF_STRATEGY,
    READY_NOW,
    SCANNER_SCORER_VERSION,
    STRATEGY_ROUTER_VERSION,
)
from core.scanner_strategy_router import (
    route_strategy,
    validate_backtest_config,
)
from services.settings_service import SettingsService
from tests.phase7_helpers import ready_release_report


def _scenario(side: str) -> dict:
    return {
        "type": side,
        "entry_zone": [1.0850, 1.0875],
        "entry_status": "confirmed_entry",
        "ready_to_trade": True,
        "m15_quality": "strict",
        "stop_loss": 1.0820 if side == "buy" else 1.0910,
        "take_profit": [1.0940] if side == "buy" else [1.0800],
        "expected_effective_rr": 2.0 if side == "buy" else 1.6,
    }


def _row(**overrides) -> dict:
    row = {
        "symbol": "EUR/USD",
        "best_side": "buy",
        "buy_score": 78,
        "sell_score": 61,
        "best_score": 78,
        "setup_score": 72,
        "min_score": 65,
        "min_rr": 1.3,
        "market_regime": "range",
        "direction_bias": {
            "best_side": "buy",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
        "score_gap": 17,
        "scanner_action": "ready",
        "scanner_decision": "READY_TO_TRADE",
        "scanner_group": "ready_now",
        "trade_permission": "allowed",
        "journal_feedback": {},
        "scoring_provenance": {
            "smc_scorer_version": "smc-v2",
            "smc_scoring_mode": "v2",
        },
        "smc_scorer_version": "smc-v2",
        "smc_scoring_mode": "v2",
        "analysis_result": {
            "side_scores": {
                "buy": {"signal_score": 78, "setup_score": 72},
                "sell": {"signal_score": 61, "setup_score": 64},
            },
            "scenario_scores": {
                "buy": {"signal_score": 78},
                "sell": {"signal_score": 61},
            },
            "decision_engine": {"decision": "READY_TO_TRADE"},
            "trade_gate": {"allowed": True, "decision_cap": None},
            "technical": {"price": 1.0860},
            "scenarios": [_scenario("buy"), _scenario("sell")],
        },
    }
    row.update(overrides)
    return row


def _validated_config(**overrides) -> dict:
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
        "symbol": "EUR/USD",
        "allowed_regimes": ["range"],
        "regime": "range",
        "side": "buy",
        "score_metric": "setup_score",
        "min_score": 65,
        "min_rr": 1.5,
        "scorer_version": SCANNER_SCORER_VERSION,
        "feature_version": "scanner-features-v3",
        "smc_scorer_version": "smc-v2",
        "smc_scoring_mode": "v2",
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


def test_previous_engine_config_is_invalid_after_phase0_lock():
    config = _validated_config()
    config["schema_version"] = 4
    config["validation_version"] = "phase8-smc-v2-oos-v1"
    config.pop("engine_contract_version")
    config.pop("engine_version")
    config.pop("purpose")
    config.pop("execution_parity")
    config["validation_fingerprint"] = validation_fingerprint(config)

    decision = evaluate_scanner_candidate(_row(), config)

    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert decision.strategy.config_status == CONFIG_VERSION_MISMATCH
    assert "BACKTEST_SCHEMA_VERSION_MISMATCH" in decision.reason_codes
    assert "BACKTEST_ENGINE_VERSION_MISMATCH" in decision.reason_codes


def test_missing_execution_policy_fails_closed_as_version_mismatch():
    config = _validated_config()
    config["execution_policy_version"] = ""

    status, reasons = validate_backtest_config(config, _row())

    assert status == CONFIG_VERSION_MISMATCH
    assert "BACKTEST_EXECUTION_POLICY_VERSION_MISMATCH" in reasons


def test_default_rules_pass_only_with_clear_gap_score_and_rr():
    decision = evaluate_scanner_candidate(_row())
    assert decision.branch == BRANCH_DEFAULT_RULES
    assert decision.status == READY_NOW
    assert decision.strategy_eligible is True


def test_default_rules_reject_unclear_score_gap():
    row = _row(
        score_gap=5,
        direction_bias={
            "best_side": "buy",
            "score_gap": 5,
            "is_clear_bias": False,
            "min_gap": 10,
        },
    )
    decision = evaluate_scanner_candidate(row)
    assert decision.status == OUT_OF_STRATEGY
    assert "SCORE_GAP_BELOW_MIN" in decision.reason_codes
    assert "BEST_SIDE_NOT_CLEAR" in decision.reason_codes


def test_default_rules_reject_setup_score_below_decision_threshold():
    row = _row()
    row["analysis_result"]["side_scores"]["buy"]["setup_score"] = 60
    decision = evaluate_scanner_candidate(row)
    assert decision.auto_trade_candidate is False
    assert "SETUP_SCORE_BELOW_DEFAULT_MIN" in decision.reason_codes


def test_default_rules_reject_rr_below_default_minimum():
    row = _row()
    row["analysis_result"]["scenarios"][0]["expected_effective_rr"] = 1.1
    decision = evaluate_scanner_candidate(row)
    assert decision.auto_trade_candidate is False
    assert "EXPECTED_RR_BELOW_DEFAULT_MIN" in decision.reason_codes


def test_validated_config_routes_to_backtest_validated():
    decision = evaluate_scanner_candidate(_row(), _validated_config())
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.strategy.config_status == CONFIG_VALIDATED
    assert decision.status == READY_NOW
    assert decision.to_dict()["strategy_router_version"] == STRATEGY_ROUTER_VERSION


def test_legacy_config_without_validation_metadata_routes_invalid():
    legacy = {
        "regime": "range",
        "side": "buy",
        "score_metric": "setup_score",
        "min_score": 65,
        "min_rr": 1.5,
    }
    decision = evaluate_scanner_candidate(_row(), legacy)
    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert decision.auto_trade_candidate is False
    assert decision.selected_side == "buy"
    assert "BACKTEST_CONFIG_INVALID" in decision.reason_codes
    assert "BACKTEST_STATUS_NOT_VALIDATED" in decision.reason_codes
    assert "BACKTEST_SCORER_VERSION_MISMATCH" in decision.reason_codes


def test_previous_scanner_v2_config_is_invalid_after_smc_v2_activation():
    decision = evaluate_scanner_candidate(
        _row(),
        _validated_config(
            scorer_version="scanner-v2",
            feature_version="scanner-features-v2",
        ),
    )
    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert decision.strategy.config_status == CONFIG_VERSION_MISMATCH
    assert "BACKTEST_SCORER_VERSION_MISMATCH" in decision.reason_codes


def test_config_without_explicit_smc_v2_identity_fails_closed():
    config = _validated_config()
    config["smc_scorer_version"] = ""
    config["smc_scoring_mode"] = ""
    config["validation_fingerprint"] = validation_fingerprint(config)

    decision = evaluate_scanner_candidate(_row(), config)

    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert decision.strategy.config_status == CONFIG_VERSION_MISMATCH
    assert "BACKTEST_SMC_SCORER_VERSION_MISMATCH" in (
        decision.reason_codes
    )
    assert "BACKTEST_SMC_SCORING_MODE_MISMATCH" in (
        decision.reason_codes
    )


def test_legacy_runtime_cannot_use_thresholds_calibrated_for_v2():
    row = _row(
        smc_scorer_version="smc-v1",
        smc_scoring_mode="legacy",
        scoring_provenance={
            "smc_scorer_version": "smc-v1",
            "smc_scoring_mode": "legacy",
        },
    )

    decision = evaluate_scanner_candidate(row, _validated_config())

    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert decision.strategy.config_status == CONFIG_VERSION_MISMATCH
    assert "BACKTEST_RUNTIME_SMC_VERSION_MISMATCH" in (
        decision.reason_codes
    )
    assert "BACKTEST_RUNTIME_SMC_MODE_MISMATCH" in (
        decision.reason_codes
    )


def test_expired_config_is_invalid():
    now = datetime(2026, 7, 24, tzinfo=timezone.utc)
    status, reasons = validate_backtest_config(
        _validated_config(expires_at=(now - timedelta(days=1)).isoformat()),
        _row(),
        now=now,
    )
    assert status == CONFIG_EXPIRED
    assert "BACKTEST_CONFIG_EXPIRED" in reasons


def test_side_best_locks_the_current_best_side():
    row = _row(
        best_side="sell",
        best_score=61,
        setup_score=64,
        score_gap=17,
        direction_bias={
            "best_side": "sell",
            "score_gap": 17,
            "is_clear_bias": True,
            "min_gap": 10,
        },
    )
    decision = evaluate_scanner_candidate(
        row,
        _validated_config(side="best"),
    )
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.selected_side == "sell"
    assert decision.setup_score == 64
    assert decision.scenario is not None
    assert decision.scenario["type"] == "sell"


def test_fixed_buy_never_uses_sell_scenario():
    row = _row()
    row["analysis_result"]["scenarios"] = [_scenario("sell")]
    decision = evaluate_scanner_candidate(row, _validated_config(side="buy"))
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.auto_trade_candidate is False
    assert decision.scenario is None
    assert "MISSING_SELECTED_SIDE_SCENARIO" in decision.reason_codes


def test_allowed_regimes_are_supported():
    config = _validated_config(regime="", allowed_regimes=["range", "trend_up"])
    decision = evaluate_scanner_candidate(_row(), config)
    assert decision.branch == BRANCH_BACKTEST_VALIDATED
    assert decision.strategy_eligible is True


def test_config_symbol_mismatch_is_invalid_not_default_branch():
    decision = evaluate_scanner_candidate(
        _row(),
        _validated_config(symbol="GBP/USD"),
    )
    assert decision.branch == BRANCH_BACKTEST_INVALID
    assert "BACKTEST_SYMBOL_MISMATCH" in decision.reason_codes


def test_invalid_config_falls_back_to_default_side_but_never_auto_trades():
    strategy, selected = route_strategy(
        _row(),
        _validated_config(status="DRAFT", side="sell"),
    )
    assert strategy.branch == BRANCH_BACKTEST_INVALID
    assert strategy.selected_side == "buy"
    assert strategy.eligible is False
    assert selected is not None and selected.side == "buy"


def test_controller_exposes_invalid_config_status_for_ui():
    controller = ScannerController.__new__(ScannerController)
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        symbol_auto_trade={
            "EUR/USD": _validated_config(status="DRAFT"),
        },
    )
    rows = controller._apply_scanner_filters([_row()], request)
    assert rows[0]["auto_trade_branch"] == BRANCH_BACKTEST_INVALID
    assert rows[0]["backtest_config_status"] == "BACKTEST_CONFIG_INVALID"
    assert rows[0]["auto_trade_candidate"] is False


def test_unvalidated_recommendation_is_saved_as_draft():
    settings = SymbolScanSettings()
    apply_validated_backtest_config(
        settings,
        symbol="EUR/USD",
        recommendation={
            "regime": "range",
            "side": "buy",
            "min_score": 68,
            "min_rr": 1.5,
        },
        now=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )
    assert settings.backtest is False
    assert settings.backtest_status == "DRAFT"
    assert settings.backtest_scorer_version == SCANNER_SCORER_VERSION
    assert settings.backtest_config_id.startswith("EURUSD-range-buy")
    assert settings.backtest_validated_at == ""


def test_serialized_payload_contains_router_validation_metadata():
    settings = SymbolScanSettings(
        backtest=True,
        backtest_config_id="cfg-1",
        backtest_status=CONFIG_VALIDATED,
        backtest_scorer_version=SCANNER_SCORER_VERSION,
        min_score=68,
        auto_trade_regime="range",
        auto_trade_side="best",
        min_expected_rr=1.5,
    )
    payload = serialize_backtest_config(settings, symbol="EUR/USD")
    assert payload is not None
    assert payload["status"] == CONFIG_VALIDATED
    assert payload["scorer_version"] == SCANNER_SCORER_VERSION
    assert payload["side"] == "best"
    assert payload["symbol"] == "EUR/USD"


def test_backtest_config_does_not_rewrite_decision_engine_thresholds():
    settings = SymbolScanSettings(
        backtest=True,
        min_score=80,
        decision_ready=65,
        decision_watch=60,
        decision_wait=55,
        min_expected_rr=2.0,
    )
    thresholds = analysis_thresholds_for_symbol(settings)
    assert thresholds == {
        "ready": 65,
        "watch": 60,
        "wait": 55,
        "min_score_gap": 10,
        "min_rr": 1.3,
    }


def test_manual_edit_invalidates_previously_validated_config():
    existing = SymbolScanSettings(
        backtest=True,
        backtest_config_id="cfg-1",
        backtest_status=CONFIG_VALIDATED,
        backtest_scorer_version=SCANNER_SCORER_VERSION,
        backtest_validated_at="2026-07-24T00:00:00+00:00",
        min_score=68,
        auto_trade_regime="range",
        auto_trade_side="buy",
        min_expected_rr=1.5,
    )
    proposed = SymbolScanSettings(
        backtest=True,
        min_score=70,
        auto_trade_regime="range",
        auto_trade_side="buy",
        min_expected_rr=1.5,
    )
    result = preserve_or_invalidate_manual_config(existing, proposed)
    assert result.backtest is False
    assert result.backtest_status == "DRAFT"
    assert result.backtest_config_id == ""
    assert result.backtest_validated_at == ""


def test_unchanged_manual_save_preserves_validation():
    existing = SymbolScanSettings(
        backtest=True,
        backtest_config_id="cfg-1",
        backtest_status=CONFIG_VALIDATED,
        backtest_scorer_version=SCANNER_SCORER_VERSION,
        backtest_validated_at="2026-07-24T00:00:00+00:00",
        min_score=68,
        auto_trade_regime="range",
        auto_trade_side="buy",
        min_expected_rr=1.5,
    )
    proposed = SymbolScanSettings(
        backtest=True,
        min_score=68,
        auto_trade_regime="range",
        auto_trade_side="buy",
        min_expected_rr=1.5,
    )
    result = preserve_or_invalidate_manual_config(existing, proposed)
    assert result.backtest_status == CONFIG_VALIDATED
    assert result.backtest_config_id == "cfg-1"


def test_settings_service_round_trips_validation_metadata(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    settings = service.load()
    symbol_settings = SymbolScanSettings()
    apply_validated_backtest_config(
        symbol_settings,
        symbol="EUR/USD",
        recommendation=_validated_config(),
    )
    settings.trading.symbol_settings["EUR/USD"] = symbol_settings
    service.save(settings)

    loaded = service.load().trading.symbol_settings["EUR/USD"]
    assert loaded.backtest_config_id == "EURUSD-range-buy-v3"
    assert loaded.backtest_status == CONFIG_VALIDATED
    assert loaded.backtest_scorer_version == SCANNER_SCORER_VERSION
    assert loaded.backtest_purpose == "VALIDATION"
    assert loaded.backtest_execution_parity is True
    assert loaded.backtest_data_manifest_version == (
        validation_engine_contract()["data_manifest_version"]
    )
    assert loaded.backtest_point_in_time_data is True
    assert loaded.backtest_dataset_hash == "a" * 64
    assert loaded.backtest_data_quality_status == "OK"
    engine_contract = validation_engine_contract()
    assert loaded.backtest_execution_policy_version == (
        engine_contract["execution_policy_version"]
    )
    assert loaded.backtest_entry_fill_model == "confirmation_close"
    assert (
        loaded.backtest_exit_evaluation_model
        == "next_execution_candle"
    )
    assert loaded.backtest_same_bar_ambiguity_policy == "STOP_FIRST"
    assert loaded.backtest_execution_timeframe == "M15"
    assert loaded.backtest_synthetic_trades_allowed is False
    assert (
        loaded.backtest_engine_version
        == "system-backtest-v2-execution-parity"
    )
    assert loaded.backtest_expires_at.startswith("2027-07-24")


def test_legacy_settings_load_as_unvalidated_and_fail_closed(tmp_path):
    service = SettingsService(tmp_path / "settings.json")
    service.storage.save({
        "ai": {},
        "trading": {
            "enabled_symbols": ["EUR/USD"],
            "symbol_settings": {
                "EUR/USD": {
                    "backtest": True,
                    "min_score": 68,
                    "auto_trade_regime": "range",
                    "auto_trade_side": "buy",
                    "min_expected_rr": 1.5,
                },
            },
        },
    })
    loaded = service.load().trading.symbol_settings["EUR/USD"]
    assert loaded.backtest is False
    assert loaded.backtest_status == "DRAFT"
    assert loaded.backtest_scorer_version == ""
    assert service.load().trading.enabled_symbols == []
