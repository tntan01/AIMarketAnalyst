"""Lifecycle and persistence helpers for scanner backtest configurations."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

from config.settings import SymbolScanSettings
from core.backtest_config_validation import (
    BACKTEST_CONFIG_SCHEMA_VERSION,
    BACKTEST_FEATURE_VERSION,
    BACKTEST_VALIDATION_VERSION,
)
from core.scanner_models import (
    CONFIG_DRAFT,
    CONFIG_NOT_CONFIGURED,
    CONFIG_VALIDATED,
    SCANNER_SCORER_VERSION,
    SETUP_SCORE_METRIC,
)
from core.scanner_strategy_router import validate_backtest_config
from core.smc_versions import SMC_SCORER_VERSION


_VALIDATION_SETTING_FIELDS = (
    "backtest_config_id",
    "backtest_status",
    "backtest_schema_version",
    "backtest_validation_version",
    "backtest_engine_contract_version",
    "backtest_engine_version",
    "backtest_purpose",
    "backtest_execution_parity",
    "backtest_data_manifest_version",
    "backtest_point_in_time_data",
    "backtest_dataset_hash",
    "backtest_data_quality_status",
    "backtest_execution_policy_version",
    "backtest_entry_fill_model",
    "backtest_exit_evaluation_model",
    "backtest_same_bar_ambiguity_policy",
    "backtest_execution_timeframe",
    "backtest_synthetic_trades_allowed",
    "backtest_execution_mode",
    "backtest_execution_model_version",
    "backtest_cost_model_version",
    "backtest_quote_conversion_model_version",
    "backtest_cost_model_fingerprint",
    "backtest_quote_conversion_fingerprint",
    "backtest_candidate_ledger_version",
    "backtest_candidate_replay_version",
    "backtest_frozen_strategy_version",
    "backtest_frozen_strategy_applied",
    "backtest_oos_replay",
    "backtest_provenance_version",
    "backtest_code_revision",
    "backtest_request_fingerprint",
    "backtest_execution_fingerprint",
    "backtest_provenance_fingerprint",
    "backtest_scorer_version",
    "backtest_feature_version",
    "backtest_smc_scorer_version",
    "backtest_score_metric",
    "backtest_trained_from",
    "backtest_trained_to",
    "backtest_validated_from",
    "backtest_validated_to",
    "backtest_in_sample_trades",
    "backtest_out_of_sample_trades",
    "backtest_oos_expectancy_r",
    "backtest_oos_profit_factor",
    "backtest_oos_max_drawdown_r",
    "backtest_expectancy_ci_low",
    "backtest_expectancy_ci_high",
    "backtest_statistics_version",
    "backtest_probability_positive_edge_pct",
    "backtest_one_sided_p_value",
    "backtest_minimum_required_trades",
    "backtest_statistical_power_passed",
    "backtest_walk_forward_windows",
    "backtest_walk_forward_verdict",
    "backtest_validation_fingerprint",
    "backtest_validation_reasons",
    "backtest_validated_at",
    "backtest_expires_at",
    "backtest_release_report",
)


def apply_validated_backtest_config(
    settings: SymbolScanSettings,
    *,
    symbol: str,
    recommendation: dict[str, Any],
    now: datetime | None = None,
) -> SymbolScanSettings:
    """Apply a recommendation; only validator output may become VALIDATED.

    ``now`` remains accepted for compatibility with older callers but no
    longer grants validation.  Phase-5 validation timestamps come from the
    immutable evidence payload.
    """

    regime = str(recommendation.get("regime", "") or "").strip().lower()
    side = str(recommendation.get("side", "") or "").strip().lower()
    min_score = int(recommendation.get("min_score", 0) or 0)
    min_rr = float(recommendation.get("min_rr", 0) or 0)
    normalized_symbol = "".join(
        char for char in str(symbol or "").upper() if char.isalnum()
    )
    lifecycle_status, _ = validate_backtest_config(
        recommendation,
        {"symbol": symbol},
        now=now,
    )
    validated = lifecycle_status == CONFIG_VALIDATED

    # A recommendation may be retained as DRAFT for a later backtest, but it
    # must never enter the live Strategy Router until the canonical validator
    # accepts its complete evidence payload.
    settings.backtest = validated
    settings.backtest_config_id = str(
        recommendation.get("config_id")
        or f"{normalized_symbol}-{regime}-{side}-{SCANNER_SCORER_VERSION}"
    )
    settings.backtest_status = CONFIG_VALIDATED if validated else CONFIG_DRAFT
    settings.backtest_schema_version = int(
        recommendation.get("schema_version", 0) or 0
    )
    settings.backtest_validation_version = str(
        recommendation.get("validation_version", "") or ""
    ).strip()
    settings.backtest_engine_contract_version = str(
        recommendation.get("engine_contract_version", "") or ""
    ).strip()
    settings.backtest_engine_version = str(
        recommendation.get("engine_version", "") or ""
    ).strip()
    settings.backtest_purpose = str(
        recommendation.get("purpose", "") or ""
    ).strip().upper()
    settings.backtest_execution_parity = (
        recommendation.get("execution_parity") is True
    )
    settings.backtest_data_manifest_version = str(
        recommendation.get("data_manifest_version", "") or ""
    ).strip()
    settings.backtest_point_in_time_data = (
        recommendation.get("point_in_time_data") is True
    )
    settings.backtest_dataset_hash = str(
        recommendation.get("dataset_hash", "") or ""
    ).strip().lower()
    settings.backtest_data_quality_status = str(
        recommendation.get("data_quality_status", "") or ""
    ).strip().upper()
    settings.backtest_execution_policy_version = str(
        recommendation.get("execution_policy_version", "") or ""
    ).strip()
    settings.backtest_entry_fill_model = str(
        recommendation.get("entry_fill_model", "") or ""
    ).strip()
    settings.backtest_exit_evaluation_model = str(
        recommendation.get("exit_evaluation_model", "") or ""
    ).strip()
    settings.backtest_same_bar_ambiguity_policy = str(
        recommendation.get("same_bar_ambiguity_policy", "") or ""
    ).strip().upper()
    settings.backtest_execution_timeframe = str(
        recommendation.get("execution_timeframe", "") or ""
    ).strip().upper()
    settings.backtest_synthetic_trades_allowed = (
        recommendation.get("synthetic_trades_allowed") is True
    )
    settings.backtest_execution_mode = str(
        recommendation.get("execution_mode", "") or ""
    )
    settings.backtest_execution_model_version = str(
        recommendation.get("execution_model_version", "") or ""
    )
    settings.backtest_cost_model_version = str(
        recommendation.get("cost_model_version", "") or ""
    )
    settings.backtest_quote_conversion_model_version = str(
        recommendation.get("quote_conversion_model_version", "") or ""
    )
    settings.backtest_cost_model_fingerprint = str(
        recommendation.get("cost_model_fingerprint", "") or ""
    )
    settings.backtest_quote_conversion_fingerprint = str(
        recommendation.get("quote_conversion_fingerprint", "") or ""
    )
    settings.backtest_candidate_ledger_version = str(
        recommendation.get("candidate_ledger_version", "") or ""
    )
    settings.backtest_candidate_replay_version = str(
        recommendation.get("candidate_replay_version", "") or ""
    )
    settings.backtest_frozen_strategy_version = str(
        recommendation.get("frozen_strategy_version", "") or ""
    )
    settings.backtest_frozen_strategy_applied = (
        recommendation.get("frozen_strategy_applied") is True
    )
    settings.backtest_oos_replay = recommendation.get("oos_replay") is True
    settings.backtest_provenance_version = str(
        recommendation.get("provenance_version", "") or ""
    )
    settings.backtest_code_revision = str(
        recommendation.get("code_revision", "") or ""
    )
    settings.backtest_request_fingerprint = str(
        recommendation.get("request_fingerprint", "") or ""
    )
    settings.backtest_execution_fingerprint = str(
        recommendation.get("execution_fingerprint", "") or ""
    )
    settings.backtest_provenance_fingerprint = str(
        recommendation.get("provenance_fingerprint", "") or ""
    )
    settings.backtest_scorer_version = str(
        recommendation.get("scorer_version", SCANNER_SCORER_VERSION)
        or SCANNER_SCORER_VERSION
    ).strip()
    settings.backtest_feature_version = str(
        recommendation.get("feature_version", "") or ""
    ).strip()
    settings.backtest_smc_scorer_version = str(
        recommendation.get("smc_scorer_version", "") or ""
    ).strip()
    settings.backtest_score_metric = str(
        recommendation.get("score_metric", SETUP_SCORE_METRIC)
        or SETUP_SCORE_METRIC
    ).strip()
    settings.backtest_trained_from = _text(recommendation, "trained_from")
    settings.backtest_trained_to = _text(recommendation, "trained_to")
    settings.backtest_validated_from = _text(recommendation, "validated_from")
    settings.backtest_validated_to = _text(recommendation, "validated_to")
    settings.backtest_in_sample_trades = _integer(
        recommendation, "in_sample_trades"
    )
    settings.backtest_out_of_sample_trades = _integer(
        recommendation, "out_of_sample_trades"
    )
    settings.backtest_oos_expectancy_r = _number(
        recommendation, "oos_expectancy_r"
    )
    settings.backtest_oos_profit_factor = _number(
        recommendation, "oos_profit_factor"
    )
    settings.backtest_oos_max_drawdown_r = _number(
        recommendation, "oos_max_drawdown_r"
    )
    settings.backtest_expectancy_ci_low = _optional_number(
        recommendation.get("expectancy_ci_low")
    )
    settings.backtest_expectancy_ci_high = _optional_number(
        recommendation.get("expectancy_ci_high")
    )
    settings.backtest_statistics_version = _text(
        recommendation, "statistics_version"
    )
    settings.backtest_probability_positive_edge_pct = _optional_number(
        recommendation.get("probability_positive_edge_pct")
    )
    settings.backtest_one_sided_p_value = _optional_number(
        recommendation.get("one_sided_p_value")
    )
    settings.backtest_minimum_required_trades = _integer(
        recommendation, "minimum_required_trades"
    )
    settings.backtest_statistical_power_passed = (
        recommendation.get("statistical_power_passed") is True
    )
    settings.backtest_walk_forward_windows = _integer(
        recommendation, "walk_forward_windows"
    )
    settings.backtest_walk_forward_verdict = _text(
        recommendation, "walk_forward_verdict"
    ).upper()
    settings.backtest_validation_fingerprint = (
        _text(recommendation, "validation_fingerprint") if validated else ""
    )
    raw_reasons = recommendation.get("validation_reasons", [])
    settings.backtest_validation_reasons = (
        [str(value) for value in raw_reasons if str(value).strip()]
        if isinstance(raw_reasons, list)
        else []
    )
    settings.backtest_validated_at = (
        _text(recommendation, "validated_at") if validated else ""
    )
    settings.backtest_expires_at = (
        _text(recommendation, "expires_at") if validated else ""
    )
    raw_release_report = recommendation.get("release_report")
    settings.backtest_release_report = (
        dict(raw_release_report)
        if isinstance(raw_release_report, dict)
        else {}
    )
    settings.auto_trade_regime = regime
    settings.auto_trade_side = side
    settings.min_score = min_score
    settings.min_expected_rr = min_rr
    return settings


def preserve_or_invalidate_manual_config(
    existing: SymbolScanSettings | None,
    proposed: SymbolScanSettings,
) -> SymbolScanSettings:
    """Preserve validation only when strategy-defining fields are unchanged."""

    if existing is not None and _same_strategy(existing, proposed):
        for field_name in _VALIDATION_SETTING_FIELDS:
            value = getattr(existing, field_name)
            if isinstance(value, list):
                value = list(value)
            elif isinstance(value, dict):
                value = dict(value)
            setattr(proposed, field_name, value)
        proposed.backtest = bool(
            proposed.backtest
            and proposed.backtest_status == CONFIG_VALIDATED
        )
        return proposed

    _clear_validation(proposed)
    proposed.backtest_status = CONFIG_DRAFT
    proposed.backtest_schema_version = BACKTEST_CONFIG_SCHEMA_VERSION
    proposed.backtest_validation_version = BACKTEST_VALIDATION_VERSION
    proposed.backtest_scorer_version = SCANNER_SCORER_VERSION
    proposed.backtest_feature_version = BACKTEST_FEATURE_VERSION
    proposed.backtest_smc_scorer_version = SMC_SCORER_VERSION
    proposed.backtest_score_metric = SETUP_SCORE_METRIC
    proposed.backtest = False
    return proposed


def serialize_backtest_config(
    settings: SymbolScanSettings | None,
    *,
    symbol: str,
    include_inactive: bool = False,
) -> dict[str, object] | None:
    """Build the only config payload shape accepted by Strategy Router."""

    if settings is None or (not settings.backtest and not include_inactive):
        return None
    min_score = int(
        settings.min_score or settings.decision_ready or 0
    )
    return {
        "config_id": settings.backtest_config_id,
        "status": settings.backtest_status,
        "schema_version": settings.backtest_schema_version,
        "validation_version": settings.backtest_validation_version,
        "engine_contract_version": (
            settings.backtest_engine_contract_version
        ),
        "engine_version": settings.backtest_engine_version,
        "purpose": settings.backtest_purpose,
        "execution_parity": settings.backtest_execution_parity,
        "data_manifest_version": settings.backtest_data_manifest_version,
        "point_in_time_data": settings.backtest_point_in_time_data,
        "dataset_hash": settings.backtest_dataset_hash,
        "data_quality_status": settings.backtest_data_quality_status,
        "execution_policy_version": (
            settings.backtest_execution_policy_version
        ),
        "entry_fill_model": settings.backtest_entry_fill_model,
        "exit_evaluation_model": settings.backtest_exit_evaluation_model,
        "same_bar_ambiguity_policy": (
            settings.backtest_same_bar_ambiguity_policy
        ),
        "execution_timeframe": settings.backtest_execution_timeframe,
        "synthetic_trades_allowed": (
            settings.backtest_synthetic_trades_allowed
        ),
        "execution_mode": settings.backtest_execution_mode,
        "execution_model_version": (
            settings.backtest_execution_model_version
        ),
        "cost_model_version": settings.backtest_cost_model_version,
        "quote_conversion_model_version": (
            settings.backtest_quote_conversion_model_version
        ),
        "cost_model_fingerprint": (
            settings.backtest_cost_model_fingerprint
        ),
        "quote_conversion_fingerprint": (
            settings.backtest_quote_conversion_fingerprint
        ),
        "candidate_ledger_version": (
            settings.backtest_candidate_ledger_version
        ),
        "candidate_replay_version": (
            settings.backtest_candidate_replay_version
        ),
        "frozen_strategy_version": (
            settings.backtest_frozen_strategy_version
        ),
        "frozen_strategy_applied": (
            settings.backtest_frozen_strategy_applied
        ),
        "oos_replay": settings.backtest_oos_replay,
        "provenance_version": settings.backtest_provenance_version,
        "code_revision": settings.backtest_code_revision,
        "request_fingerprint": settings.backtest_request_fingerprint,
        "execution_fingerprint": settings.backtest_execution_fingerprint,
        "provenance_fingerprint": settings.backtest_provenance_fingerprint,
        "symbol": symbol,
        "allowed_regimes": (
            [settings.auto_trade_regime]
            if settings.auto_trade_regime
            else []
        ),
        "regime": settings.auto_trade_regime,
        "side": settings.auto_trade_side,
        "min_score": min_score,
        "min_rr": float(settings.min_expected_rr or 0),
        "score_metric": settings.backtest_score_metric or SETUP_SCORE_METRIC,
        "scorer_version": settings.backtest_scorer_version,
        "feature_version": settings.backtest_feature_version,
        "smc_scorer_version": settings.backtest_smc_scorer_version,
        "trained_from": settings.backtest_trained_from,
        "trained_to": settings.backtest_trained_to,
        "validated_from": settings.backtest_validated_from,
        "validated_to": settings.backtest_validated_to,
        "in_sample_trades": settings.backtest_in_sample_trades,
        "out_of_sample_trades": settings.backtest_out_of_sample_trades,
        "oos_expectancy_r": settings.backtest_oos_expectancy_r,
        "oos_profit_factor": settings.backtest_oos_profit_factor,
        "oos_max_drawdown_r": settings.backtest_oos_max_drawdown_r,
        "expectancy_ci_low": settings.backtest_expectancy_ci_low,
        "expectancy_ci_high": settings.backtest_expectancy_ci_high,
        "statistics_version": settings.backtest_statistics_version,
        "probability_positive_edge_pct": (
            settings.backtest_probability_positive_edge_pct
        ),
        "one_sided_p_value": settings.backtest_one_sided_p_value,
        "minimum_required_trades": settings.backtest_minimum_required_trades,
        "statistical_power_passed": (
            settings.backtest_statistical_power_passed
        ),
        "walk_forward_windows": settings.backtest_walk_forward_windows,
        "walk_forward_verdict": settings.backtest_walk_forward_verdict,
        "validation_fingerprint": settings.backtest_validation_fingerprint,
        "validation_reasons": list(settings.backtest_validation_reasons),
        "validated_at": settings.backtest_validated_at,
        "expires_at": settings.backtest_expires_at,
        "release_report": dict(settings.backtest_release_report),
    }


def backtest_activation_status(
    settings: SymbolScanSettings | None,
    *,
    symbol: str,
    now: datetime | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Return whether a stored config may be activated for live routing.

    Inactive configs are included in this assessment so Settings can show a
    retained DRAFT/expired config without accidentally sending it to Scanner.
    """

    if settings is None or not _has_stored_backtest_config(settings):
        return CONFIG_NOT_CONFIGURED, ("BACKTEST_NOT_CONFIGURED",)
    payload = serialize_backtest_config(
        settings,
        symbol=symbol,
        include_inactive=True,
    )
    return validate_backtest_config(payload, {"symbol": symbol}, now=now)


def merge_symbol_scan_settings(
    existing: SymbolScanSettings | None,
    *,
    symbol: str,
    activate_backtest: bool,
    decision_ready: int,
    decision_watch: int,
    decision_wait: int,
    recommendation: dict[str, Any] | None = None,
    now: datetime | None = None,
) -> SymbolScanSettings:
    """Merge Settings/Symbols without losing stored backtest evidence.

    Ready/Watch/Wait belong to the default Decision Engine and are always
    editable. Backtest-derived fields can only be replaced by a canonical
    recommendation and only VALIDATED evidence may become active.
    """

    result = replace(existing) if existing is not None else SymbolScanSettings()
    result.backtest_validation_reasons = list(
        result.backtest_validation_reasons
    )
    if recommendation is not None:
        apply_validated_backtest_config(
            result,
            symbol=symbol,
            recommendation=recommendation,
            now=now,
        )

    result.decision_ready = int(decision_ready)
    result.decision_watch = int(decision_watch)
    result.decision_wait = int(decision_wait)

    lifecycle_status, lifecycle_reasons = backtest_activation_status(
        result,
        symbol=symbol,
        now=now,
    )
    result.backtest = bool(
        activate_backtest and lifecycle_status == CONFIG_VALIDATED
    )
    if (
        result.backtest_status == CONFIG_VALIDATED
        and lifecycle_status != CONFIG_VALIDATED
    ):
        result.backtest_status = lifecycle_status
        result.backtest_validation_reasons = list(lifecycle_reasons)
    return result


def reconcile_enabled_symbol(
    enabled_symbols: list[str],
    *,
    symbol: str,
    backtest_active: bool,
    lifecycle_status: str,
    confirmed_disable: bool = False,
) -> list[str]:
    """Update membership without treating a retained DRAFT as user disable.

    Only an active validated config adds a new symbol.  A symbol is removed
    only when the user explicitly disables a config that is otherwise still
    VALIDATED.  Saving DRAFT/expired/version-mismatch evidence preserves the
    previous scanner membership.
    """

    result = list(dict.fromkeys(enabled_symbols))
    if backtest_active:
        if symbol not in result:
            result.append(symbol)
    elif confirmed_disable and lifecycle_status == CONFIG_VALIDATED:
        result = [item for item in result if item != symbol]
    return result


def analysis_thresholds_for_symbol(
    settings: SymbolScanSettings | None,
) -> dict[str, int | float] | None:
    """Keep Decision Engine thresholds independent from backtest strategy."""

    if settings is None:
        return None
    return {
        "ready": settings.decision_ready,
        "watch": settings.decision_watch,
        "wait": settings.decision_wait,
        "min_score_gap": 10,
        # A backtest min_rr belongs to Strategy Router only.
        "min_rr": (
            1.3
            if settings.backtest
            else settings.min_expected_rr or 1.3
        ),
    }


def _same_strategy(
    existing: SymbolScanSettings,
    proposed: SymbolScanSettings,
) -> bool:
    return (
        existing.min_score == proposed.min_score
        and existing.auto_trade_regime == proposed.auto_trade_regime
        and existing.auto_trade_side == proposed.auto_trade_side
        and float(existing.min_expected_rr) == float(proposed.min_expected_rr)
    )


def _has_stored_backtest_config(settings: SymbolScanSettings) -> bool:
    return bool(
        settings.backtest_config_id
        or settings.backtest_status
        or settings.backtest_schema_version
        or settings.backtest_validation_version
        or settings.backtest_validated_at
        or settings.backtest_expires_at
        or settings.backtest_release_report
    )


def _clear_validation(settings: SymbolScanSettings) -> None:
    defaults = SymbolScanSettings()
    for field_name in _VALIDATION_SETTING_FIELDS:
        value = getattr(defaults, field_name)
        if isinstance(value, list):
            value = list(value)
        elif isinstance(value, dict):
            value = dict(value)
        setattr(settings, field_name, value)


def _text(payload: dict[str, Any], key: str) -> str:
    return str(payload.get(key, "") or "").strip()


def _integer(payload: dict[str, Any], key: str) -> int:
    try:
        return int(payload.get(key, 0) or 0)
    except (TypeError, ValueError):
        return 0


def _number(payload: dict[str, Any], key: str) -> float:
    return _optional_number(payload.get(key)) or 0.0


def _optional_number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
