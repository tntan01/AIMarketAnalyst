"""Canonical Phase-2 router for scanner strategy selection.

The router owns all branch selection and strategy threshold logic.  A
configured backtest is executable only when its validation metadata is
current.  Invalid/expired configurations fall back to default analysis data
for display, but remain ineligible for automatic trading.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from typing import Any

from core.backtest_contract import (
    BACKTEST_CONTRACT_VERSION,
    BACKTEST_PURPOSE_VALIDATION,
    VALIDATION_BACKTEST_ENGINE_VERSION,
    normalize_backtest_purpose,
)
from core.backtest_market_data import DATA_MANIFEST_VERSION
from core.backtest_execution import (
    BACKTEST_EXECUTION_POLICY_VERSION,
    ENTRY_FILL_MODEL,
    EXIT_EVALUATION_MODEL,
    SAME_BAR_STOP_FIRST,
)
from core.backtest_execution_parity import (
    EXECUTION_COST_MODEL_VERSION,
    EXECUTION_MODE_PARITY,
    EXECUTION_PARITY_MODEL_VERSION,
    QUOTE_CONVERSION_MODEL_VERSION,
)
from core.backtest_candidate_ledger import (
    CANDIDATE_LEDGER_VERSION,
    CANDIDATE_REPLAY_VERSION,
    FROZEN_STRATEGY_VERSION,
)
from core.backtest_provenance import BACKTEST_PROVENANCE_VERSION
from core.backtest_statistics import (
    BACKTEST_STATISTICS_VERSION,
    MAX_ONE_SIDED_P_VALUE,
    MIN_BOOTSTRAP_PROBABILITY_POSITIVE_PCT,
)
from core.backtest_release import validate_release_report
from core.scanner_models import (
    BRANCH_BACKTEST_INVALID,
    BRANCH_BACKTEST_VALIDATED,
    BRANCH_DEFAULT_RULES,
    CONFIG_DISABLED,
    CONFIG_DRAFT,
    CONFIG_EXPIRED,
    CONFIG_INVALID,
    CONFIG_NOT_CONFIGURED,
    CONFIG_VALIDATED,
    CONFIG_VERSION_MISMATCH,
    SCANNER_FEATURE_VERSION,
    SCANNER_SCORER_VERSION,
    SETUP_SCORE_METRIC,
    SideEvaluation,
    StrategyEvaluation,
)
from core.smc_versions import SMC_SCORER_VERSION
from core.backtest_config_validation import (
    BACKTEST_CONFIG_SCHEMA_VERSION,
    BACKTEST_VALIDATION_VERSION,
    MAX_OOS_DRAWDOWN_R,
    MAX_VALIDATED_DATA_AGE_DAYS,
    MIN_IN_SAMPLE_TRADES,
    MIN_OOS_EXPECTANCY_R,
    MIN_OOS_PROFIT_FACTOR,
    MIN_OUT_OF_SAMPLE_TRADES,
    MIN_WALK_FORWARD_WINDOWS,
    has_valid_validation_fingerprint,
)
from core.scanner_strategy_engine import (
    evaluate_sides,
    finite_number,
    normalize_side,
    positive_number,
    unique_codes,
)


DEFAULT_MIN_SCORE = 65.0
DEFAULT_MIN_RR = 1.3
DEFAULT_MIN_SCORE_GAP = 10.0

_SIDE_DATA_CODES = frozenset({
    "MISSING_ANALYSIS",
    "MISSING_SELECTED_SIDE_SCENARIO",
    "FALLBACK_ENTRY_ZONE",
    "SIGNAL_SCORE_MISSING",
    "SETUP_SCORE_MISSING",
    "SETUP_SCORE_NOT_SELECTED_SIDE",
})


def route_strategy(
    row: dict[str, Any],
    backtest_config: dict[str, object] | None = None,
    *,
    side_evaluations: tuple[SideEvaluation, ...] | None = None,
    now: datetime | None = None,
) -> tuple[StrategyEvaluation, SideEvaluation | None]:
    """Route one symbol to exactly one strategy branch for this scan."""

    sides = (
        side_evaluations
        if side_evaluations is not None
        else evaluate_sides(row)
    )
    if backtest_config is None:
        return _evaluate_default_rules(row, sides)

    config_status, config_reasons = validate_backtest_config(
        backtest_config,
        row,
        now=now,
    )
    if config_status != CONFIG_VALIDATED:
        fallback, selected = _evaluate_default_rules(row, sides)
        reasons = unique_codes((
            "BACKTEST_CONFIG_INVALID",
            *config_reasons,
            *fallback.reason_codes,
        ))
        return (
            replace(
                fallback,
                branch=BRANCH_BACKTEST_INVALID,
                config_status=config_status,
                eligible=False,
                reason_codes=reasons,
            ),
            selected,
        )

    return _evaluate_validated_backtest(row, backtest_config, sides)


def validate_backtest_config(
    config: object,
    row: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> tuple[str, tuple[str, ...]]:
    """Validate lifecycle/schema metadata separately from row eligibility."""

    reasons: list[str] = []
    if not isinstance(config, dict):
        return CONFIG_INVALID, (
            "BACKTEST_CONFIG_INVALID",
            "BACKTEST_CONFIG_MALFORMED",
        )

    raw_status = str(config.get("status", "") or "").strip().upper()
    if raw_status != CONFIG_VALIDATED:
        if raw_status == CONFIG_EXPIRED:
            reasons.append("BACKTEST_CONFIG_EXPIRED")
        elif raw_status == CONFIG_DRAFT:
            reasons.append("BACKTEST_CONFIG_DRAFT")
        elif raw_status == CONFIG_DISABLED:
            reasons.append("BACKTEST_CONFIG_DISABLED")
        else:
            reasons.append("BACKTEST_STATUS_NOT_VALIDATED")

    if int(config.get("schema_version", 0) or 0) != BACKTEST_CONFIG_SCHEMA_VERSION:
        reasons.append("BACKTEST_SCHEMA_VERSION_MISMATCH")
    validation_version = str(
        config.get("validation_version", "") or ""
    ).strip()
    if validation_version != BACKTEST_VALIDATION_VERSION:
        reasons.append("BACKTEST_VALIDATION_VERSION_MISMATCH")

    engine_contract_version = str(
        config.get("engine_contract_version", "") or ""
    ).strip()
    if engine_contract_version != BACKTEST_CONTRACT_VERSION:
        reasons.append("BACKTEST_ENGINE_CONTRACT_VERSION_MISMATCH")
    engine_version = str(
        config.get("engine_version", "") or ""
    ).strip()
    if engine_version != VALIDATION_BACKTEST_ENGINE_VERSION:
        reasons.append("BACKTEST_ENGINE_VERSION_MISMATCH")
    if normalize_backtest_purpose(config.get("purpose")) != (
        BACKTEST_PURPOSE_VALIDATION
    ):
        reasons.append("BACKTEST_PURPOSE_NOT_VALIDATION")
    if config.get("execution_parity") is not True:
        reasons.append("BACKTEST_EXECUTION_PARITY_REQUIRED")
    if str(config.get("data_manifest_version", "") or "").strip() != (
        DATA_MANIFEST_VERSION
    ):
        reasons.append("BACKTEST_DATA_MANIFEST_VERSION_MISMATCH")
    if config.get("point_in_time_data") is not True:
        reasons.append("BACKTEST_POINT_IN_TIME_DATA_REQUIRED")
    if str(config.get("data_quality_status", "") or "").upper() != "OK":
        reasons.append("BACKTEST_DATA_QUALITY_NOT_OK")
    dataset_hash = str(config.get("dataset_hash", "") or "").strip().lower()
    if (
        len(dataset_hash) != 64
        or any(character not in "0123456789abcdef" for character in dataset_hash)
    ):
        reasons.append("BACKTEST_DATASET_HASH_INVALID")
    if str(config.get("execution_policy_version", "") or "") != (
        BACKTEST_EXECUTION_POLICY_VERSION
    ):
        reasons.append("BACKTEST_EXECUTION_POLICY_VERSION_MISMATCH")
    if str(config.get("entry_fill_model", "") or "") != ENTRY_FILL_MODEL:
        reasons.append("BACKTEST_ENTRY_FILL_MODEL_MISMATCH")
    if str(config.get("exit_evaluation_model", "") or "") != (
        EXIT_EVALUATION_MODEL
    ):
        reasons.append("BACKTEST_EXIT_EVALUATION_MODEL_MISMATCH")
    if str(
        config.get("same_bar_ambiguity_policy", "") or ""
    ).upper() != SAME_BAR_STOP_FIRST:
        reasons.append("BACKTEST_SAME_BAR_POLICY_MISMATCH")
    if str(config.get("execution_timeframe", "") or "").upper() != "M15":
        reasons.append("BACKTEST_EXECUTION_TIMEFRAME_MISMATCH")
    if config.get("synthetic_trades_allowed") is not False:
        reasons.append("BACKTEST_SYNTHETIC_TRADES_NOT_FORBIDDEN")
    if str(config.get("execution_mode", "") or "").upper() != (
        EXECUTION_MODE_PARITY
    ):
        reasons.append("BACKTEST_EXECUTION_MODE_MISMATCH")
    if str(config.get("execution_model_version", "") or "") != (
        EXECUTION_PARITY_MODEL_VERSION
    ):
        reasons.append("BACKTEST_EXECUTION_MODEL_VERSION_MISMATCH")
    if str(config.get("cost_model_version", "") or "") != (
        EXECUTION_COST_MODEL_VERSION
    ):
        reasons.append("BACKTEST_COST_MODEL_VERSION_MISMATCH")
    if str(config.get("quote_conversion_model_version", "") or "") != (
        QUOTE_CONVERSION_MODEL_VERSION
    ):
        reasons.append("BACKTEST_QUOTE_CONVERSION_MODEL_VERSION_MISMATCH")
    cost_fingerprint = str(
        config.get("cost_model_fingerprint", "") or ""
    ).lower()
    if (
        len(cost_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in cost_fingerprint)
    ):
        reasons.append("BACKTEST_COST_MODEL_FINGERPRINT_INVALID")
    quote_fingerprint = str(
        config.get("quote_conversion_fingerprint", "") or ""
    ).lower()
    if (
        len(quote_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in quote_fingerprint)
    ):
        reasons.append("BACKTEST_QUOTE_CONVERSION_FINGERPRINT_INVALID")
    if str(config.get("candidate_ledger_version", "") or "") != (
        CANDIDATE_LEDGER_VERSION
    ):
        reasons.append("BACKTEST_CANDIDATE_LEDGER_VERSION_MISMATCH")
    if str(config.get("candidate_replay_version", "") or "") != (
        CANDIDATE_REPLAY_VERSION
    ):
        reasons.append("BACKTEST_CANDIDATE_REPLAY_VERSION_MISMATCH")
    if str(config.get("frozen_strategy_version", "") or "") != (
        FROZEN_STRATEGY_VERSION
    ):
        reasons.append("BACKTEST_FROZEN_STRATEGY_VERSION_MISMATCH")
    if config.get("frozen_strategy_applied") is not True:
        reasons.append("BACKTEST_FROZEN_STRATEGY_REQUIRED")
    if config.get("oos_replay") is not True:
        reasons.append("BACKTEST_OOS_REPLAY_REQUIRED")
    if str(config.get("provenance_version") or "") != (
        BACKTEST_PROVENANCE_VERSION
    ):
        reasons.append("BACKTEST_PROVENANCE_VERSION_MISMATCH")
    code_revision = str(config.get("code_revision") or "").lower()
    if not 7 <= len(code_revision) <= 64 or any(
        character not in "0123456789abcdef" for character in code_revision
    ):
        reasons.append("BACKTEST_CODE_REVISION_INVALID")
    for field in (
        "request_fingerprint",
        "execution_fingerprint",
        "provenance_fingerprint",
    ):
        fingerprint = str(config.get(field) or "").lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            reasons.append(f"BACKTEST_{field.upper()}_INVALID")

    reasons.extend(validate_release_report(
        config.get("release_report"),
        dataset_hash=dataset_hash,
        provenance_fingerprint=str(
            config.get("provenance_fingerprint") or ""
        ),
    ))

    scorer_version = str(config.get("scorer_version", "") or "").strip()
    if scorer_version != SCANNER_SCORER_VERSION:
        reasons.append("BACKTEST_SCORER_VERSION_MISMATCH")
    feature_version = str(config.get("feature_version", "") or "").strip()
    if feature_version != SCANNER_FEATURE_VERSION:
        reasons.append("BACKTEST_FEATURE_VERSION_MISMATCH")
    smc_scorer_version = str(
        config.get("smc_scorer_version", "") or ""
    ).strip()
    if smc_scorer_version != SMC_SCORER_VERSION:
        reasons.append("BACKTEST_SMC_SCORER_VERSION_MISMATCH")
    if isinstance(row, dict):
        provenance = (
            row.get("scoring_provenance")
            if isinstance(row.get("scoring_provenance"), dict)
            else {}
        )
        runtime_smc_version = str(
            row.get("smc_scorer_version")
            or provenance.get("smc_scorer_version")
            or ""
        ).strip()
        if (
            runtime_smc_version
            and runtime_smc_version != smc_scorer_version
        ):
            reasons.append("BACKTEST_RUNTIME_SMC_VERSION_MISMATCH")

    metric = str(config.get("score_metric", "") or "").strip()
    if metric != SETUP_SCORE_METRIC:
        reasons.append("UNSUPPORTED_SCORE_METRIC")

    side = str(config.get("side", "") or "").strip().lower()
    if side not in {"buy", "sell", "best"}:
        reasons.append("BACKTEST_SIDE_INVALID")

    if not _configured_regimes(config):
        reasons.append("BACKTEST_REGIME_MISSING")

    if positive_number(config.get("min_score")) is None:
        reasons.append("BACKTEST_MIN_SCORE_MISSING")
    if positive_number(config.get("min_rr")) is None:
        reasons.append("BACKTEST_MIN_RR_MISSING")

    trained_from = _parse_datetime(str(config.get("trained_from", "") or ""))
    trained_to = _parse_datetime(str(config.get("trained_to", "") or ""))
    validated_from = _parse_datetime(
        str(config.get("validated_from", "") or "")
    )
    validated_to = _parse_datetime(str(config.get("validated_to", "") or ""))
    if None in (trained_from, trained_to, validated_from, validated_to):
        reasons.append("BACKTEST_VALIDATION_RANGE_MISSING")
    elif not (
        trained_from <= trained_to < validated_from <= validated_to
    ):
        reasons.append("BACKTEST_IS_OOS_RANGE_INVALID")

    if _integer(config.get("in_sample_trades")) < MIN_IN_SAMPLE_TRADES:
        reasons.append("BACKTEST_IS_SAMPLE_TOO_SMALL")
    if _integer(config.get("out_of_sample_trades")) < MIN_OUT_OF_SAMPLE_TRADES:
        reasons.append("BACKTEST_OOS_SAMPLE_TOO_SMALL")
    oos_expectancy = finite_number(config.get("oos_expectancy_r"))
    if oos_expectancy is None or oos_expectancy < MIN_OOS_EXPECTANCY_R:
        reasons.append("BACKTEST_OOS_EXPECTANCY_TOO_LOW")
    oos_profit_factor = finite_number(config.get("oos_profit_factor"))
    if oos_profit_factor is None or oos_profit_factor < MIN_OOS_PROFIT_FACTOR:
        reasons.append("BACKTEST_OOS_PROFIT_FACTOR_TOO_LOW")
    oos_drawdown = finite_number(config.get("oos_max_drawdown_r"))
    if (
        oos_drawdown is None
        or oos_drawdown < 0
        or oos_drawdown > MAX_OOS_DRAWDOWN_R
    ):
        reasons.append("BACKTEST_OOS_DRAWDOWN_INVALID")
    ci_low = finite_number(config.get("expectancy_ci_low"))
    ci_high = finite_number(config.get("expectancy_ci_high"))
    if ci_low is None or ci_high is None or ci_low <= 0 or ci_low > ci_high:
        reasons.append("BACKTEST_EXPECTANCY_CI_INVALID")
    if str(config.get("statistics_version") or "") != (
        BACKTEST_STATISTICS_VERSION
    ):
        reasons.append("BACKTEST_STATISTICS_VERSION_MISMATCH")
    positive_probability = finite_number(
        config.get("probability_positive_edge_pct")
    )
    if (
        positive_probability is None
        or positive_probability < MIN_BOOTSTRAP_PROBABILITY_POSITIVE_PCT
    ):
        reasons.append("BACKTEST_POSITIVE_EDGE_PROBABILITY_TOO_LOW")
    p_value = finite_number(config.get("one_sided_p_value"))
    if p_value is None or p_value < 0 or p_value > MAX_ONE_SIDED_P_VALUE:
        reasons.append("BACKTEST_EDGE_P_VALUE_INVALID")
    required_trades = _integer(config.get("minimum_required_trades"))
    if (
        config.get("statistical_power_passed") is not True
        or required_trades < MIN_OUT_OF_SAMPLE_TRADES
        or _integer(config.get("out_of_sample_trades")) < required_trades
    ):
        reasons.append("BACKTEST_STATISTICAL_POWER_INSUFFICIENT")
    if _integer(config.get("walk_forward_windows")) < MIN_WALK_FORWARD_WINDOWS:
        reasons.append("BACKTEST_WALK_FORWARD_WINDOWS_TOO_FEW")
    if str(
        config.get("walk_forward_verdict", "") or ""
    ).strip().upper() != "ROBUST":
        reasons.append("BACKTEST_WALK_FORWARD_NOT_ROBUST")
    if not has_valid_validation_fingerprint(config):
        reasons.append("BACKTEST_VALIDATION_FINGERPRINT_INVALID")

    config_symbol = _normalize_symbol(config.get("symbol"))
    row_symbol = _normalize_symbol(row.get("symbol")) if isinstance(row, dict) else ""
    if config_symbol and row_symbol and config_symbol != row_symbol:
        reasons.append("BACKTEST_SYMBOL_MISMATCH")

    validated_at = str(config.get("validated_at", "") or "").strip()
    if _parse_datetime(validated_at) is None:
        reasons.append("BACKTEST_VALIDATED_AT_INVALID")

    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    current = current.astimezone(timezone.utc)
    if validated_to is not None:
        if validated_to > current + timedelta(days=1):
            reasons.append("BACKTEST_VALIDATED_DATA_IN_FUTURE")
        elif current - validated_to > timedelta(
            days=MAX_VALIDATED_DATA_AGE_DAYS
        ):
            reasons.append("BACKTEST_VALIDATED_DATA_TOO_OLD")

    expires_at = str(config.get("expires_at", "") or "").strip()
    if not expires_at:
        reasons.append("BACKTEST_EXPIRY_MISSING")
    else:
        expiry = _parse_datetime(expires_at)
        if expiry is None:
            reasons.append("BACKTEST_EXPIRY_INVALID")
        else:
            if expiry <= current:
                reasons.append("BACKTEST_CONFIG_EXPIRED")

    codes = unique_codes(reasons)
    if not codes:
        return CONFIG_VALIDATED, ()
    if "BACKTEST_CONFIG_EXPIRED" in codes:
        return CONFIG_EXPIRED, codes
    if raw_status == CONFIG_DISABLED:
        return CONFIG_DISABLED, codes
    if raw_status == CONFIG_DRAFT:
        return CONFIG_DRAFT, codes
    if "BACKTEST_SCORER_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if "BACKTEST_FEATURE_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if "BACKTEST_ENGINE_CONTRACT_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if "BACKTEST_ENGINE_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if "BACKTEST_DATA_MANIFEST_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if "BACKTEST_EXECUTION_POLICY_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if "BACKTEST_SMC_SCORER_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if "BACKTEST_RUNTIME_SMC_VERSION_MISMATCH" in codes:
        return CONFIG_VERSION_MISMATCH, codes
    if any(code.startswith("BACKTEST_RELEASE_") for code in codes):
        return CONFIG_VERSION_MISMATCH, codes
    return CONFIG_INVALID, codes


def _evaluate_validated_backtest(
    row: dict[str, Any],
    config: dict[str, object],
    sides: tuple[SideEvaluation, ...],
) -> tuple[StrategyEvaluation, SideEvaluation | None]:
    reasons: list[str] = []
    if not isinstance(row, dict):
        reasons.append("INVALID_SCANNER_ROW")
        row = {}
    if not isinstance(row.get("analysis_result"), dict):
        reasons.append("MISSING_ANALYSIS")

    raw_best_side = str(row.get("best_side", "") or "").strip().lower()
    best_side = normalize_side(raw_best_side)
    if raw_best_side in {"neutral", "stand_aside", "skip"}:
        reasons.append("NO_TRADE_SIDE")
    elif best_side is None:
        reasons.append("INVALID_BEST_SIDE")

    configured_side = str(config.get("side", "") or "").strip().lower()
    selected_side = best_side if configured_side == "best" else normalize_side(
        configured_side
    )
    if selected_side is None:
        reasons.append("MISSING_SELECTED_SIDE")
    if (
        configured_side in {"buy", "sell"}
        and best_side is not None
        and selected_side != best_side
    ):
        reasons.append("CONFIG_SIDE_MISMATCH")

    side_evaluation = _side_map(sides).get(selected_side)
    _append_side_errors(reasons, side_evaluation)

    row_regime = str(row.get("market_regime", "") or "").strip().lower()
    if row_regime not in _configured_regimes(config):
        reasons.append("BACKTEST_REGIME_MISMATCH")

    score_value = (
        side_evaluation.setup_score if side_evaluation is not None else None
    )
    min_score = positive_number(config.get("min_score"))
    if score_value is None:
        reasons.append("SETUP_SCORE_MISSING")
    elif min_score is not None and score_value < min_score:
        reasons.append("SETUP_SCORE_BELOW_MIN")

    expected_rr = (
        side_evaluation.expected_effective_rr
        if side_evaluation is not None
        else None
    )
    min_rr = positive_number(config.get("min_rr"))
    if expected_rr is None:
        reasons.append("EXPECTED_RR_MISSING")
    elif min_rr is not None and expected_rr < min_rr:
        reasons.append("EXPECTED_RR_BELOW_MIN")

    reason_codes = unique_codes(reasons)
    return (
        StrategyEvaluation(
            branch=BRANCH_BACKTEST_VALIDATED,
            config_status=CONFIG_VALIDATED,
            selected_side=selected_side,
            score_metric=SETUP_SCORE_METRIC,
            score_value=score_value,
            min_score=min_score,
            expected_effective_rr=expected_rr,
            min_rr=min_rr,
            eligible=not reason_codes,
            reason_codes=reason_codes,
        ),
        side_evaluation,
    )


def _evaluate_default_rules(
    row: dict[str, Any],
    sides: tuple[SideEvaluation, ...],
) -> tuple[StrategyEvaluation, SideEvaluation | None]:
    reasons: list[str] = []
    if not isinstance(row, dict):
        row = {}
        reasons.append("INVALID_SCANNER_ROW")
    if not isinstance(row.get("analysis_result"), dict):
        reasons.append("MISSING_ANALYSIS")

    raw_best_side = str(row.get("best_side", "") or "").strip().lower()
    best_side = normalize_side(raw_best_side)
    if raw_best_side in {"neutral", "stand_aside", "skip"}:
        reasons.append("NO_TRADE_SIDE")
    elif best_side is None:
        reasons.append("INVALID_BEST_SIDE")

    direction_bias = (
        row.get("direction_bias")
        if isinstance(row.get("direction_bias"), dict)
        else {}
    )
    raw_score_gap = row.get("score_gap")
    if raw_score_gap is None:
        raw_score_gap = direction_bias.get("score_gap")
    score_gap = finite_number(raw_score_gap)
    min_gap = positive_number(
        direction_bias.get(
            "min_gap",
            row.get("min_score_gap", DEFAULT_MIN_SCORE_GAP),
        )
    ) or DEFAULT_MIN_SCORE_GAP
    if score_gap is None:
        reasons.append("SCORE_GAP_MISSING")
    elif score_gap < min_gap:
        reasons.append("SCORE_GAP_BELOW_MIN")
    if (
        "is_clear_bias" in direction_bias
        and direction_bias.get("is_clear_bias") is not True
    ):
        reasons.append("BEST_SIDE_NOT_CLEAR")

    side_evaluation = _side_map(sides).get(best_side)
    _append_side_errors(reasons, side_evaluation)

    min_score = positive_number(row.get("min_score")) or DEFAULT_MIN_SCORE
    score_value = (
        side_evaluation.setup_score if side_evaluation is not None else None
    )
    if score_value is None:
        reasons.append("SETUP_SCORE_MISSING")
    elif score_value < min_score:
        reasons.append("SETUP_SCORE_BELOW_DEFAULT_MIN")

    min_rr = positive_number(row.get("min_rr")) or DEFAULT_MIN_RR
    expected_rr = (
        side_evaluation.expected_effective_rr
        if side_evaluation is not None
        else None
    )
    if expected_rr is None:
        reasons.append("EXPECTED_RR_MISSING")
    elif expected_rr < min_rr:
        reasons.append("EXPECTED_RR_BELOW_DEFAULT_MIN")

    reason_codes = unique_codes(reasons)
    return (
        StrategyEvaluation(
            branch=BRANCH_DEFAULT_RULES,
            config_status=CONFIG_NOT_CONFIGURED,
            selected_side=best_side,
            score_metric=SETUP_SCORE_METRIC,
            score_value=score_value,
            min_score=min_score,
            expected_effective_rr=expected_rr,
            min_rr=min_rr,
            eligible=not reason_codes,
            reason_codes=reason_codes,
        ),
        side_evaluation,
    )


def _append_side_errors(
    reasons: list[str],
    side_evaluation: SideEvaluation | None,
) -> None:
    if side_evaluation is None:
        reasons.append("MISSING_SIDE_EVALUATION")
        return
    reasons.extend(
        code
        for code in side_evaluation.reason_codes
        if code in _SIDE_DATA_CODES
    )


def _side_map(
    sides: tuple[SideEvaluation, ...],
) -> dict[str, SideEvaluation]:
    return {item.side: item for item in sides}


def _configured_regimes(config: dict[str, object]) -> tuple[str, ...]:
    raw_allowed = config.get("allowed_regimes")
    values: list[str] = []
    if isinstance(raw_allowed, (list, tuple, set)):
        values.extend(str(item or "").strip().lower() for item in raw_allowed)
    raw_regime = str(config.get("regime", "") or "").strip().lower()
    if raw_regime:
        values.append(raw_regime)
    return unique_codes([value for value in values if value])


def _normalize_symbol(value: object) -> str:
    return "".join(char for char in str(value or "").upper() if char.isalnum())


def _parse_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _integer(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
