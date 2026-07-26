"""Phase-5 OOS validation and config integrity tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib

from config.settings import SymbolScanSettings
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    build_research_backtest_contract,
    validation_engine_contract,
)
from core.backtest_market_data import DATA_MANIFEST_VERSION
from core.backtest_candidate_ledger import (
    CANDIDATE_LEDGER_VERSION,
    CANDIDATE_REPLAY_VERSION,
    FROZEN_STRATEGY_VERSION,
    candidate_ledger_fingerprint,
)
from core.backtest_provenance import build_backtest_provenance
from core.walk_forward_engine import WALK_FORWARD_VERSION
from core.backtest_config import (
    apply_validated_backtest_config,
    backtest_activation_status,
    merge_symbol_scan_settings,
    serialize_backtest_config,
)
from core.backtest_config_validation import (
    BACKTEST_CONFIG_SCHEMA_VERSION,
    build_backtest_config,
)
from core.scanner_models import CONFIG_DRAFT, CONFIG_VALIDATED
from core.scanner_strategy_router import validate_backtest_config
from tests.phase7_helpers import ready_release_report


def _trade(index: int, result_r: float = 1.0, rr: float | None = 2.0) -> dict:
    opened = datetime(2026, 6, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return {
        "symbol": "EUR/USD",
        "side": "buy",
        "market_regime": "range",
        "entry_time": opened.isoformat(),
        "final_score": 80,
        "setup_score": 80,
        "signal_score": 82,
        "expected_effective_rr": rr,
        "result": "win" if result_r > 0 else "loss",
        "result_r": result_r,
    }


def _walk_forward() -> dict:
    return {
        "version": WALK_FORWARD_VERSION,
        "interval": "[start,end)",
        "calendar_periods": True,
        "deduplication_applied": True,
        "windows": [
            {
                "is_start": "2024-01-01T00:00:00+00:00",
                "is_end": "2024-07-01T00:00:00+00:00",
                "oos_start": "2024-07-01T00:00:00+00:00",
                "oos_end": "2024-09-30T00:00:00+00:00",
                "oos_summary": {"total_trades": 5},
                "frozen_strategy_config": {
                    "config_id": "wf-1",
                    "version": FROZEN_STRATEGY_VERSION,
                    "score_metric": "setup_score",
                },
                "optimization_source": "IS_CANDIDATE_LEDGER",
                "oos_replay": True,
                "interval": "[start,end)",
                "oos_trade_ids": [f"wf-1-{index}" for index in range(5)],
            },
            {
                "is_start": "2024-04-01T00:00:00+00:00",
                "is_end": "2024-10-01T00:00:00+00:00",
                "oos_start": "2024-10-01T00:00:00+00:00",
                "oos_end": "2024-12-31T00:00:00+00:00",
                "oos_summary": {"total_trades": 5},
                "frozen_strategy_config": {
                    "config_id": "wf-2",
                    "version": FROZEN_STRATEGY_VERSION,
                    "score_metric": "setup_score",
                },
                "optimization_source": "IS_CANDIDATE_LEDGER",
                "oos_replay": True,
                "interval": "[start,end)",
                "oos_trade_ids": [f"wf-2-{index}" for index in range(5)],
            },
        ],
        "aggregate_oos": {
            "total_trades": 10,
            "expectancy_r": 0.35,
            "profit_factor": 1.8,
        },
        "verdict": "ROBUST",
        "window_count": 2,
        "unique_oos_trade_count": 10,
        "duplicate_oos_trade_count": 0,
        "unique_oos_trade_fingerprint": hashlib.sha256(
            "|".join(
                sorted(
                    [f"wf-1-{index}" for index in range(5)]
                    + [f"wf-2-{index}" for index in range(5)]
                )
            ).encode("utf-8")
        ).hexdigest(),
    }


def _result() -> dict:
    trades = [_trade(index) for index in range(30)]
    contract = validation_engine_contract()
    manifest = {
        "version": DATA_MANIFEST_VERSION,
        "timezone": "UTC",
        "interval_convention": "[start,end)",
        "quality_status": "OK",
        "validation_eligible": True,
        "dataset_hash": "a" * 64,
        "timeframes": {"D1": {}, "H4": {}, "H1": {}, "M15": {}},
        "issues": [],
    }
    scoring = {
        "score_metric": "setup_score",
        "scorer_version": "scanner-v3",
        "feature_version": "scanner-features-v3",
        "smc_scorer_version": "smc-v2",
        "smc_scoring_mode": "v2",
    }
    frozen_id = "EURUSD-frozen-test"
    is_ledger = []
    for index, trade in enumerate(trades[:21]):
        is_ledger.append({
            "candidate_id": f"is-{index}",
            "symbol": "EUR/USD",
            "decision_time": trade["entry_time"],
            "side": "buy",
            "setup_score": 80,
            "setup_score_source": "side_scores.buy.setup_score",
            "signal_score": 82,
            "market_regime": "range",
            "expected_effective_rr": 2.0,
            "scenario_available": True,
            "base_eligible": True,
            "base_rejection_reason": None,
            "scenario_source": "pipeline",
            "research_only": False,
            "frozen_config_id": "",
            "strategy_eligible": True,
            "strategy_rejection_reasons": [],
            "simulated_trade": dict(trade),
            "executed": True,
            "version": CANDIDATE_LEDGER_VERSION,
        })
    oos_trades = []
    oos_ledger = []
    for index, trade in enumerate(trades[21:]):
        candidate_id = f"oos-{index}"
        persisted = dict(trade)
        persisted.update({
            "candidate_id": candidate_id,
            "frozen_config_id": frozen_id,
            "research_only": False,
            "scenario_source": "pipeline",
        })
        oos_trades.append(persisted)
        oos_ledger.append({
            "candidate_id": candidate_id,
            "symbol": "EUR/USD",
            "decision_time": trade["entry_time"],
            "side": "buy",
            "setup_score": 80,
            "setup_score_source": "side_scores.buy.setup_score",
            "signal_score": 82,
            "market_regime": "range",
            "expected_effective_rr": 2.0,
            "scenario_available": True,
            "base_eligible": True,
            "base_rejection_reason": None,
            "scenario_source": "pipeline",
            "research_only": False,
            "frozen_config_id": frozen_id,
            "strategy_eligible": True,
            "strategy_rejection_reasons": [],
            "simulated_trade": dict(persisted),
            "executed": True,
            "version": CANDIDATE_LEDGER_VERSION,
        })
    validation_replay = {
        "replay_version": CANDIDATE_REPLAY_VERSION,
        "status": "COMPLETE",
        "is_start": "2026-06-01T00:00:00+00:00",
        "is_end": "2026-06-22T00:00:00+00:00",
        "oos_start": "2026-06-22T00:00:00+00:00",
        "oos_end": "2026-07-01T00:00:00+00:00",
        "is_candidate_ledger": is_ledger,
        "is_candidate_ledger_fingerprint": candidate_ledger_fingerprint(is_ledger),
        "oos_candidate_ledger": oos_ledger,
        "oos_candidate_ledger_fingerprint": candidate_ledger_fingerprint(oos_ledger),
        "frozen_strategy_config": {
            "config_id": frozen_id,
            "symbol": "EUR/USD",
            "side": "buy",
            "allowed_regimes": ["range"],
            "min_setup_score": 50,
            "min_expected_rr": 1.0,
            "score_metric": "setup_score",
            "version": FROZEN_STRATEGY_VERSION,
            "selected_from": "IN_SAMPLE_CANDIDATE_LEDGER",
        },
        "oos_trades": oos_trades,
        "backtest_contract": contract,
        "data_manifest": manifest,
        "scoring_contract": scoring,
        "account_state_reset": {
            "initial_balance": 10_000,
            "closed_trades": 0,
            "open_positions": 0,
        },
        "request": {"symbol": "EUR/USD", "risk_percent": 1.0},
    }
    validation_replay["backtest_provenance"] = build_backtest_provenance(
        code_revision="b" * 40,
        request=validation_replay["request"],
        data_manifest=manifest,
        execution_contract=contract,
        scoring_contract=scoring,
        frozen_strategy_config=validation_replay["frozen_strategy_config"],
    )
    result = {
        "trades": trades,
        "walk_forward": _walk_forward(),
        "backtest_contract": contract,
        "data_manifest": manifest,
        "scoring_contract": scoring,
        "validation_replay": validation_replay,
    }
    result["release_report"] = ready_release_report(
        dataset_hash=manifest["dataset_hash"],
        provenance_fingerprint=validation_replay[
            "backtest_provenance"
        ]["provenance_fingerprint"],
    )
    return result


def test_build_config_selects_on_is_and_validates_on_later_oos():
    config = build_backtest_config(
        _result(),
        symbol="EUR/USD",
        now=datetime(2026, 7, 24, tzinfo=timezone.utc),
    )

    assert config is not None
    assert config["status"] == CONFIG_VALIDATED
    assert config["trained_to"] < config["validated_from"]
    assert config["in_sample_trades"] == 21
    assert config["out_of_sample_trades"] == 9
    assert config["expectancy_ci_low"] > 0
    assert config["walk_forward_windows"] == 2

    status, reasons = validate_backtest_config(
        config,
        {"symbol": "EUR/USD"},
        now=datetime(2026, 7, 25, tzinfo=timezone.utc),
    )
    assert status == CONFIG_VALIDATED
    assert reasons == ()


def test_missing_walk_forward_keeps_config_draft():
    result = _result()
    del result["walk_forward"]
    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == "DRAFT"
    assert "WALK_FORWARD_MISSING" in config["validation_reasons"]


def test_missing_scoring_contract_keeps_config_draft():
    result = _result()
    del result["validation_replay"]["scoring_contract"]
    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == "DRAFT"
    assert "BACKTEST_SCORING_CONTRACT_MISSING" in config["validation_reasons"]


def test_research_engine_result_cannot_issue_validated_config():
    result = _result()
    result["validation_replay"]["backtest_contract"] = build_research_backtest_contract(
        BACKTEST_PURPOSE_RESEARCH
    )

    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == "DRAFT"
    assert config["purpose"] == "RESEARCH"
    assert config["execution_parity"] is False
    assert "BACKTEST_ENGINE_VERSION_MISMATCH" in (
        config["validation_reasons"]
    )
    assert "BACKTEST_PURPOSE_NOT_VALIDATION" in (
        config["validation_reasons"]
    )
    assert "BACKTEST_EXECUTION_PARITY_REQUIRED" in (
        config["validation_reasons"]
    )


def test_missing_data_manifest_cannot_issue_validated_config():
    result = _result()
    result["validation_replay"].pop("data_manifest")

    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == CONFIG_DRAFT
    assert "BACKTEST_DATA_MANIFEST_MISSING" in config["validation_reasons"]


def test_non_ok_data_manifest_cannot_issue_validated_config():
    result = _result()
    manifest = result["validation_replay"]["data_manifest"]
    manifest["quality_status"] = "WARNING"
    manifest["validation_eligible"] = False
    manifest["issues"] = [
        {
            "code": "UNEXPECTED_DATA_GAP",
            "severity": "WARNING",
            "message": "Gap test",
        }
    ]

    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == CONFIG_DRAFT
    reasons = config["validation_reasons"]
    assert "BACKTEST_DATA_QUALITY_NOT_OK" in reasons
    assert "BACKTEST_DATA_NOT_VALIDATION_ELIGIBLE" in reasons
    assert "BACKTEST_DATA_QUALITY_ISSUES_PRESENT" in reasons


def test_research_only_trade_cannot_enter_validation_dataset():
    result = _result()
    trade = result["validation_replay"]["oos_trades"][0]
    trade["research_only"] = True
    trade["scenario_source"] = "synthetic_fallback"

    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == CONFIG_DRAFT
    assert (
        "BACKTEST_VALIDATION_CONTAINS_RESEARCH_ONLY_TRADES"
        in config["validation_reasons"]
    )


def test_missing_rr_cannot_pass_oos_rr_filter():
    result = _result()
    for trade in result["validation_replay"]["oos_trades"]:
        trade["expected_effective_rr"] = None
    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == "DRAFT"
    assert "OOS_TRADE_FROZEN_STRATEGY_MISMATCH" in config["validation_reasons"]


def test_negative_oos_expectancy_keeps_config_draft():
    result = _result()
    for trade in result["validation_replay"]["oos_trades"]:
        trade["result"] = "loss"
        trade["result_r"] = -1.0
    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == "DRAFT"
    assert "OOS_EXPECTANCY_TOO_LOW" in config["validation_reasons"]
    assert "OOS_EXPECTANCY_CI_NOT_POSITIVE" in config["validation_reasons"]


def test_tampered_evidence_fails_closed():
    config = build_backtest_config(_result(), symbol="EUR/USD")
    assert config is not None and config["status"] == CONFIG_VALIDATED
    config["min_score"] = int(config["min_score"]) + 1

    status, reasons = validate_backtest_config(config, {"symbol": "EUR/USD"})
    assert status != CONFIG_VALIDATED
    assert "BACKTEST_VALIDATION_FINGERPRINT_INVALID" in reasons


def test_stale_oos_data_cannot_issue_validated_config():
    config = build_backtest_config(
        _result(),
        symbol="EUR/USD",
        now=datetime(2028, 1, 1, tzinfo=timezone.utc),
    )

    assert config is not None
    assert config["status"] == CONFIG_DRAFT
    assert "VALIDATED_DATA_TOO_OLD" in config["validation_reasons"]


def test_tampered_provenance_cannot_issue_validated_config():
    result = _result()
    result["validation_replay"]["backtest_provenance"][
        "execution_fingerprint"
    ] = "f" * 64

    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == CONFIG_DRAFT
    assert "BACKTEST_PROVENANCE_FINGERPRINT_INVALID" in config[
        "validation_reasons"
    ]


def test_validated_config_round_trips_through_symbol_settings():
    config = build_backtest_config(_result(), symbol="EUR/USD")
    assert config is not None
    settings = SymbolScanSettings()
    apply_validated_backtest_config(
        settings,
        symbol="EUR/USD",
        recommendation=config,
    )
    payload = serialize_backtest_config(settings, symbol="EUR/USD")

    assert settings.backtest_status == CONFIG_VALIDATED
    assert payload is not None
    assert payload["schema_version"] == BACKTEST_CONFIG_SCHEMA_VERSION
    assert payload["purpose"] == "VALIDATION"
    assert payload["execution_parity"] is True
    assert payload["data_manifest_version"] == DATA_MANIFEST_VERSION
    assert payload["point_in_time_data"] is True
    assert payload["dataset_hash"] == "a" * 64
    assert payload["data_quality_status"] == "OK"
    assert payload["execution_policy_version"] == (
        config["execution_policy_version"]
    )
    assert payload["entry_fill_model"] == "confirmation_close"
    assert payload["exit_evaluation_model"] == "next_execution_candle"
    assert payload["same_bar_ambiguity_policy"] == "STOP_FIRST"
    assert payload["execution_timeframe"] == "M15"
    assert payload["synthetic_trades_allowed"] is False
    assert payload["execution_mode"] == "EXECUTION_PARITY"
    assert payload["execution_model_version"] == (
        "backtest-execution-parity-v1"
    )
    assert payload["cost_model_version"] == "backtest-cost-model-v1"
    assert payload["quote_conversion_model_version"] == (
        "point-in-time-close-v1"
    )
    assert len(payload["cost_model_fingerprint"]) == 64
    assert len(payload["quote_conversion_fingerprint"]) == 64
    assert payload["provenance_version"] == "backtest-provenance-v1"
    assert payload["code_revision"] == "b" * 40
    assert len(payload["request_fingerprint"]) == 64
    assert len(payload["execution_fingerprint"]) == 64
    assert len(payload["provenance_fingerprint"]) == 64
    assert payload["smc_scorer_version"] == "smc-v2"
    assert payload["smc_scoring_mode"] == "v2"
    assert payload["out_of_sample_trades"] == 9
    assert payload["statistics_version"] == "backtest-statistics-v1"
    assert payload["probability_positive_edge_pct"] == 100.0
    assert payload["one_sided_p_value"] == 0.0
    assert payload["statistical_power_passed"] is True
    assert payload["validation_fingerprint"] == config["validation_fingerprint"]


def test_disabled_draft_is_preserved_for_later_but_not_routed_now():
    settings = SymbolScanSettings(
        backtest=False,
        backtest_config_id="draft-for-later",
        backtest_status="DRAFT",
        backtest_schema_version=4,
        backtest_smc_scorer_version="smc-v2",
        backtest_smc_scoring_mode="v2",
        min_score=60,
    )

    payload = serialize_backtest_config(settings, symbol="EUR/USD")

    assert payload is None
    assert settings.backtest_config_id == "draft-for-later"
    assert settings.backtest_status == "DRAFT"
    assert settings.min_score == 60

    inactive_payload = serialize_backtest_config(
        settings,
        symbol="EUR/USD",
        include_inactive=True,
    )
    assert inactive_payload is not None
    assert inactive_payload["status"] == "DRAFT"


def test_settings_merge_cannot_activate_draft_but_preserves_it():
    existing = SymbolScanSettings(
        backtest=False,
        backtest_config_id="draft-for-later",
        backtest_status="DRAFT",
        backtest_schema_version=4,
        backtest_validation_version="phase8-smc-v2-oos-v1",
        backtest_scorer_version="scanner-v3",
        backtest_feature_version="scanner-features-v3",
        backtest_smc_scorer_version="smc-v2",
        backtest_smc_scoring_mode="v2",
        backtest_score_metric="setup_score",
        min_score=68,
        auto_trade_regime="range",
        auto_trade_side="buy",
        min_expected_rr=1.5,
    )

    merged = merge_symbol_scan_settings(
        existing,
        symbol="EUR/USD",
        activate_backtest=True,
        decision_ready=70,
        decision_watch=62,
        decision_wait=56,
    )

    assert merged.backtest is False
    assert merged.backtest_config_id == "draft-for-later"
    assert merged.backtest_status == "DRAFT"
    assert merged.min_score == 68
    assert merged.decision_ready == 70
    assert merged.decision_watch == 62
    assert merged.decision_wait == 56


def test_settings_merge_can_toggle_validated_config_without_losing_evidence():
    config = build_backtest_config(_result(), symbol="EUR/USD")
    assert config is not None and config["status"] == CONFIG_VALIDATED
    existing = SymbolScanSettings()
    apply_validated_backtest_config(
        existing,
        symbol="EUR/USD",
        recommendation=config,
    )
    config_id = existing.backtest_config_id

    disabled = merge_symbol_scan_settings(
        existing,
        symbol="EUR/USD",
        activate_backtest=False,
        decision_ready=66,
        decision_watch=61,
        decision_wait=56,
    )
    disabled_status, _ = backtest_activation_status(
        disabled,
        symbol="EUR/USD",
    )
    assert disabled.backtest is False
    assert disabled.backtest_status == CONFIG_VALIDATED
    assert disabled.backtest_config_id == config_id
    assert disabled_status == CONFIG_VALIDATED

    enabled = merge_symbol_scan_settings(
        disabled,
        symbol="EUR/USD",
        activate_backtest=True,
        decision_ready=66,
        decision_watch=61,
        decision_wait=56,
    )
    assert enabled.backtest is True
    assert enabled.backtest_config_id == config_id
