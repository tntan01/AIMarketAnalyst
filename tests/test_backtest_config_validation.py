"""Phase-5 OOS validation and config integrity tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from config.settings import SymbolScanSettings
from core.backtest_config import (
    apply_validated_backtest_config,
    backtest_activation_status,
    merge_symbol_scan_settings,
    serialize_backtest_config,
)
from core.backtest_config_validation import build_backtest_config
from core.scanner_models import CONFIG_VALIDATED
from core.scanner_strategy_router import validate_backtest_config


def _trade(index: int, result_r: float = 1.0, rr: float | None = 2.0) -> dict:
    opened = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(days=index)
    return {
        "symbol": "EUR/USD",
        "side": "buy",
        "market_regime": "range",
        "entry_time": opened.isoformat(),
        "final_score": 80,
        "signal_score": 82,
        "expected_effective_rr": rr,
        "result": "win" if result_r > 0 else "loss",
        "result_r": result_r,
    }


def _walk_forward() -> dict:
    return {
        "windows": [
            {
                "is_start": "2024-01-01T00:00:00+00:00",
                "is_end": "2024-06-30T00:00:00+00:00",
                "oos_start": "2024-07-01T00:00:00+00:00",
                "oos_end": "2024-09-30T00:00:00+00:00",
                "oos_summary": {"total_trades": 5},
            },
            {
                "is_start": "2024-04-01T00:00:00+00:00",
                "is_end": "2024-09-30T00:00:00+00:00",
                "oos_start": "2024-10-01T00:00:00+00:00",
                "oos_end": "2024-12-31T00:00:00+00:00",
                "oos_summary": {"total_trades": 5},
            },
        ],
        "aggregate_oos": {
            "total_trades": 10,
            "expectancy_r": 0.35,
            "profit_factor": 1.8,
        },
        "verdict": "ROBUST",
        "window_count": 2,
    }


def _result() -> dict:
    trades = [_trade(index) for index in range(30)]
    return {
        "trades": trades,
        "walk_forward": _walk_forward(),
        "scoring_contract": {
            "score_metric": "setup_score",
            "scorer_version": "scanner-v3",
            "feature_version": "scanner-features-v3",
            "smc_scorer_version": "smc-v2",
            "smc_scoring_mode": "v2",
        },
    }


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
    del result["scoring_contract"]
    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == "DRAFT"
    assert "BACKTEST_SCORING_CONTRACT_MISSING" in config["validation_reasons"]


def test_missing_rr_cannot_pass_oos_rr_filter():
    result = _result()
    for trade in result["trades"][21:]:
        trade["expected_effective_rr"] = None
    config = build_backtest_config(result, symbol="EUR/USD")

    assert config is not None
    assert config["status"] == "DRAFT"
    assert config["out_of_sample_trades"] == 0
    assert "OOS_SAMPLE_TOO_SMALL" in config["validation_reasons"]


def test_negative_oos_expectancy_keeps_config_draft():
    result = _result()
    for trade in result["trades"][21:]:
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
    assert payload["schema_version"] == 4
    assert payload["smc_scorer_version"] == "smc-v2"
    assert payload["smc_scoring_mode"] == "v2"
    assert payload["out_of_sample_trades"] == 9
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
