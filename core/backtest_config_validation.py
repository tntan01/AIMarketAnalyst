"""Frozen OOS-replay validation contract for scanner configurations.

The optimizer may select a recommendation only from the in-sample segment.
The selected configuration is then evaluated, unchanged, on a later
out-of-sample segment.  A separate walk-forward result is required as
additional stability evidence before the configuration can auto-trade.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any

from core.backtest_contract import (
    BACKTEST_CONTRACT_VERSION,
    BACKTEST_PURPOSE_VALIDATION,
    VALIDATION_BACKTEST_ENGINE_VERSION,
    normalize_backtest_purpose,
)
from core.backtest_market_data import (
    BACKTEST_INTERVAL_CONVENTION,
    DATA_MANIFEST_VERSION,
    REQUIRED_BACKTEST_TIMEFRAMES,
)
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
from core.backtest_to_scanner_config import recommend_scanner_configs
from core.backtest_candidate_ledger import (
    CANDIDATE_LEDGER_VERSION,
    CANDIDATE_REPLAY_VERSION,
    FROZEN_STRATEGY_VERSION,
    candidate_ledger_fingerprint,
)
from core.backtest_provenance import (
    BACKTEST_PROVENANCE_VERSION,
    canonical_fingerprint,
    validate_backtest_provenance,
)
from core.backtest_statistics import (
    BACKTEST_STATISTICS_VERSION,
    MAX_ONE_SIDED_P_VALUE,
    MIN_BOOTSTRAP_PROBABILITY_POSITIVE_PCT,
    bootstrap_trade_uncertainty,
)
from core.backtest_release import validate_release_report
from core.walk_forward_engine import WALK_FORWARD_VERSION
from core.scanner_models import (
    SCANNER_FEATURE_VERSION,
    SCANNER_SCORER_VERSION,
    SETUP_SCORE_METRIC,
)
from core.smc_scoring_contract import SMC_MODE_V2
from core.smc_versions import SMC_SCORER_V2_VERSION


BACKTEST_CONFIG_SCHEMA_VERSION = 8
BACKTEST_FEATURE_VERSION = SCANNER_FEATURE_VERSION
BACKTEST_VALIDATION_VERSION = "backtest-v8-statistical-validation-v1"

MIN_IN_SAMPLE_TRADES = 10
MIN_OUT_OF_SAMPLE_TRADES = 8
MIN_WALK_FORWARD_WINDOWS = 2
MIN_OOS_EXPECTANCY_R = 0.10
MIN_OOS_PROFIT_FACTOR = 1.20
MAX_OOS_DRAWDOWN_R = 8.0
VALIDATION_TTL_DAYS = 90
MAX_VALIDATED_DATA_AGE_DAYS = 365

_FINGERPRINT_FIELDS = (
    "schema_version",
    "validation_version",
    "engine_contract_version",
    "engine_version",
    "purpose",
    "execution_parity",
    "data_manifest_version",
    "point_in_time_data",
    "dataset_hash",
    "data_quality_status",
    "execution_policy_version",
    "entry_fill_model",
    "exit_evaluation_model",
    "same_bar_ambiguity_policy",
    "execution_timeframe",
    "synthetic_trades_allowed",
    "execution_mode",
    "execution_model_version",
    "cost_model_version",
    "quote_conversion_model_version",
    "cost_model_fingerprint",
    "quote_conversion_fingerprint",
    "candidate_ledger_version",
    "candidate_replay_version",
    "frozen_strategy_version",
    "frozen_strategy_applied",
    "oos_replay",
    "provenance_version",
    "code_revision",
    "request_fingerprint",
    "execution_fingerprint",
    "provenance_fingerprint",
    "config_id",
    "status",
    "symbol",
    "allowed_regimes",
    "regime",
    "side",
    "score_metric",
    "min_score",
    "min_rr",
    "scorer_version",
    "feature_version",
    "smc_scorer_version",
    "smc_scoring_mode",
    "trained_from",
    "trained_to",
    "validated_from",
    "validated_to",
    "in_sample_trades",
    "out_of_sample_trades",
    "oos_expectancy_r",
    "oos_profit_factor",
    "oos_max_drawdown_r",
    "expectancy_ci_low",
    "expectancy_ci_high",
    "statistics_version",
    "probability_positive_edge_pct",
    "one_sided_p_value",
    "minimum_required_trades",
    "statistical_power_passed",
    "walk_forward_windows",
    "walk_forward_verdict",
    "validated_at",
    "expires_at",
    "release_report",
)


def build_backtest_config(
    result: dict[str, Any],
    *,
    symbol: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Build a config, validating only complete frozen OOS replay evidence.

    Legacy post-filtered results may still produce a reviewable DRAFT, but
    can no longer issue a VALIDATED scanner configuration.
    """

    replay = result.get("validation_replay")
    if isinstance(replay, dict) and replay.get("status") == "COMPLETE":
        return _build_from_frozen_replay(
            result,
            replay,
            symbol=symbol,
            now=now,
        )

    rows = _symbol_trades(result, symbol)
    if len(rows) < MIN_IN_SAMPLE_TRADES + MIN_OUT_OF_SAMPLE_TRADES:
        return None

    timestamps = [_trade_time(row) for row in rows]
    if any(value is None for value in timestamps):
        return _draft_without_split(result, rows, symbol, "TRADE_TIMESTAMP_MISSING")

    ordered = [
        row for _, row in sorted(
            zip(timestamps, rows),
            key=lambda item: item[0] or datetime.min.replace(tzinfo=timezone.utc),
        )
    ]
    split_index = max(
        MIN_IN_SAMPLE_TRADES,
        min(len(ordered) - MIN_OUT_OF_SAMPLE_TRADES, int(len(ordered) * 0.70)),
    )
    split_time = _trade_time(ordered[split_index])
    if split_time is None:
        return _draft_without_split(result, ordered, symbol, "TRADE_TIMESTAMP_MISSING")

    in_sample = [row for row in ordered if (_trade_time(row) or split_time) < split_time]
    out_of_sample = [row for row in ordered if (_trade_time(row) or split_time) >= split_time]
    if (
        len(in_sample) < MIN_IN_SAMPLE_TRADES
        or len(out_of_sample) < MIN_OUT_OF_SAMPLE_TRADES
    ):
        return _draft_without_split(result, ordered, symbol, "TIME_SPLIT_SAMPLE_TOO_SMALL")

    recommendation = _recommend_for_symbol(in_sample, symbol)
    if recommendation is None:
        return None

    trained_from = _iso(_trade_time(in_sample[0]))
    trained_to = _iso(_trade_time(in_sample[-1]))
    validated_from = _iso(_trade_time(out_of_sample[0]))
    validated_to = _iso(_trade_time(out_of_sample[-1]))
    current = _utc(now or datetime.now(timezone.utc))
    config = _base_config(
        recommendation,
        symbol=symbol,
        trained_from=trained_from,
        trained_to=trained_to,
        validated_from=validated_from,
        validated_to=validated_to,
        in_sample_trades=len(in_sample),
        scoring_contract=result.get("scoring_contract"),
        backtest_contract=result.get("backtest_contract"),
        data_manifest=result.get("data_manifest"),
        backtest_provenance=result.get("backtest_provenance"),
    )

    reasons: list[str] = []
    reasons.append("FROZEN_OOS_REPLAY_REQUIRED")
    reasons.extend(_validate_scoring_contract(result.get("scoring_contract")))
    reasons.extend(
        _validate_backtest_contract(result.get("backtest_contract"))
    )
    reasons.extend(_validate_data_manifest(result.get("data_manifest")))
    if any(
        row.get("research_only") is True
        or row.get("synthetic") is True
        or row.get("_fallback") is True
        or str(row.get("scenario_source") or "") == "synthetic_fallback"
        for row in rows
    ):
        reasons.append(
            "BACKTEST_VALIDATION_CONTAINS_RESEARCH_ONLY_TRADES"
        )
    selected_oos = _filter_config_trades(out_of_sample, config)
    metrics = _summarize(selected_oos)
    legacy_statistics = bootstrap_trade_uncertainty(
        [float(row.get("result_r", 0) or 0) for row in selected_oos],
        seed_material=config["config_id"],
    )
    ci_low = legacy_statistics["expectancy_r"]["p95_low"]
    ci_high = legacy_statistics["expectancy_r"]["p95_high"]
    config.update({
        "out_of_sample_trades": metrics["total_trades"],
        "oos_expectancy_r": metrics["expectancy_r"],
        "oos_profit_factor": metrics["profit_factor"],
        "oos_max_drawdown_r": metrics["max_drawdown_r"],
        "expectancy_ci_low": ci_low,
        "expectancy_ci_high": ci_high,
    })

    if trained_to >= validated_from:
        reasons.append("IS_OOS_OVERLAP")
    if metrics["total_trades"] < MIN_OUT_OF_SAMPLE_TRADES:
        reasons.append("OOS_SAMPLE_TOO_SMALL")
    if metrics["expectancy_r"] < MIN_OOS_EXPECTANCY_R:
        reasons.append("OOS_EXPECTANCY_TOO_LOW")
    if metrics["profit_factor"] < MIN_OOS_PROFIT_FACTOR:
        reasons.append("OOS_PROFIT_FACTOR_TOO_LOW")
    if metrics["max_drawdown_r"] > MAX_OOS_DRAWDOWN_R:
        reasons.append("OOS_DRAWDOWN_TOO_HIGH")
    if ci_low is None or ci_low <= 0:
        reasons.append("OOS_EXPECTANCY_CI_NOT_POSITIVE")

    wf_reasons, wf_metadata = _validate_walk_forward(result.get("walk_forward"))
    reasons.extend(wf_reasons)
    config.update(wf_metadata)

    config["validation_reasons"] = _unique(reasons)
    if not reasons:
        config["status"] = "VALIDATED"
        config["validated_at"] = current.isoformat(timespec="seconds")
        config["expires_at"] = (
            current + timedelta(days=VALIDATION_TTL_DAYS)
        ).isoformat(timespec="seconds")
        config["validation_fingerprint"] = validation_fingerprint(config)
    return config


def _build_from_frozen_replay(
    result: dict[str, Any],
    replay: dict[str, Any],
    *,
    symbol: str,
    now: datetime | None,
) -> dict[str, Any] | None:
    frozen = replay.get("frozen_strategy_config")
    if not isinstance(frozen, dict):
        return None
    allowed_regimes = frozen.get("allowed_regimes")
    if not isinstance(allowed_regimes, list) or not allowed_regimes:
        return None
    recommendation = {
        "regime": str(allowed_regimes[0] or "").lower(),
        "side": str(frozen.get("side") or "").lower(),
        "min_score": int(frozen.get("min_setup_score", 0) or 0),
        "min_rr": float(frozen.get("min_expected_rr", 0) or 0),
        "_evidence": "Frozen OOS replay",
    }
    is_ledger = replay.get("is_candidate_ledger")
    oos_ledger = replay.get("oos_candidate_ledger")
    if not isinstance(is_ledger, list) or not isinstance(oos_ledger, list):
        return None
    oos_rows = _symbol_trades(
        {"trades": replay.get("oos_trades", [])},
        symbol,
    )
    in_sample_count = sum(
        1 for row in is_ledger
        if isinstance(row, dict)
        and row.get("base_eligible") is True
        and isinstance(row.get("simulated_trade"), dict)
    )
    config = _base_config(
        recommendation,
        symbol=symbol,
        trained_from=_ledger_boundary(is_ledger, first=True),
        trained_to=_ledger_boundary(is_ledger, first=False),
        validated_from=_trade_boundary(oos_rows, first=True),
        validated_to=_trade_boundary(oos_rows, first=False),
        in_sample_trades=in_sample_count,
        scoring_contract=replay.get("scoring_contract"),
        backtest_contract=replay.get("backtest_contract"),
        data_manifest=replay.get("data_manifest"),
        backtest_provenance=replay.get("backtest_provenance"),
    )
    config["config_id"] = str(frozen.get("config_id") or config["config_id"])

    reasons: list[str] = []
    reasons.extend(_validate_scoring_contract(replay.get("scoring_contract")))
    reasons.extend(_validate_backtest_contract(replay.get("backtest_contract")))
    reasons.extend(_validate_data_manifest(replay.get("data_manifest")))
    reasons.extend(validate_backtest_provenance(replay.get("backtest_provenance")))
    provenance = (
        replay.get("backtest_provenance")
        if isinstance(replay.get("backtest_provenance"), dict)
        else {}
    )
    manifest = (
        replay.get("data_manifest")
        if isinstance(replay.get("data_manifest"), dict)
        else {}
    )
    if str(provenance.get("dataset_hash") or "") != str(
        manifest.get("dataset_hash") or ""
    ):
        reasons.append("BACKTEST_PROVENANCE_DATASET_MISMATCH")
    request_evidence = (
        dict(replay.get("request"))
        if isinstance(replay.get("request"), dict)
        else None
    )
    if request_evidence is None:
        reasons.append("BACKTEST_PROVENANCE_REQUEST_MISSING")
    else:
        request_evidence.pop("code_revision", None)
        if str(provenance.get("request_fingerprint") or "") != (
            canonical_fingerprint(request_evidence)
        ):
            reasons.append("BACKTEST_PROVENANCE_REQUEST_MISMATCH")
    for field, evidence in (
        ("execution_fingerprint", replay.get("backtest_contract")),
        ("scoring_fingerprint", replay.get("scoring_contract")),
        ("frozen_config_fingerprint", frozen),
    ):
        if not isinstance(evidence, dict) or str(provenance.get(field) or "") != (
            canonical_fingerprint(evidence if isinstance(evidence, dict) else {})
        ):
            reasons.append(f"BACKTEST_PROVENANCE_{field.upper()}_MISMATCH")
    if str(replay.get("replay_version") or "") != CANDIDATE_REPLAY_VERSION:
        reasons.append("CANDIDATE_REPLAY_VERSION_MISMATCH")
    if str(frozen.get("version") or "") != FROZEN_STRATEGY_VERSION:
        reasons.append("FROZEN_STRATEGY_VERSION_MISMATCH")
    if str(frozen.get("score_metric") or "") != SETUP_SCORE_METRIC:
        reasons.append("FROZEN_SCORE_METRIC_MISMATCH")
    if str(frozen.get("symbol") or "") != symbol:
        reasons.append("FROZEN_SYMBOL_MISMATCH")
    if any(
        not isinstance(row, dict)
        or str(row.get("version") or "") != CANDIDATE_LEDGER_VERSION
        for row in [*is_ledger, *oos_ledger]
    ):
        reasons.append("CANDIDATE_LEDGER_VERSION_MISMATCH")
    if candidate_ledger_fingerprint(is_ledger) != str(
        replay.get("is_candidate_ledger_fingerprint") or ""
    ):
        reasons.append("IS_CANDIDATE_LEDGER_FINGERPRINT_MISMATCH")
    if candidate_ledger_fingerprint(oos_ledger) != str(
        replay.get("oos_candidate_ledger_fingerprint") or ""
    ):
        reasons.append("OOS_CANDIDATE_LEDGER_FINGERPRINT_MISMATCH")
    frozen_id = str(frozen.get("config_id") or "")
    if any(
        str(row.get("frozen_config_id") or "") != frozen_id
        for row in oos_rows
    ):
        reasons.append("OOS_TRADE_FROZEN_CONFIG_MISMATCH")
    allowed = {
        str(value or "").lower() for value in allowed_regimes
    }
    frozen_side = str(frozen.get("side") or "").lower()
    frozen_min_score = float(frozen.get("min_setup_score", 0) or 0)
    frozen_min_rr = float(frozen.get("min_expected_rr", 0) or 0)
    if any(
        str(row.get("side") or "").lower() != frozen_side
        or str(row.get("market_regime") or "").lower() not in allowed
        or _finite_float(row.get("setup_score")) is None
        or float(row.get("setup_score") or 0) < frozen_min_score
        or _finite_float(row.get("expected_effective_rr")) is None
        or float(row.get("expected_effective_rr") or 0) < frozen_min_rr
        for row in oos_rows
    ):
        reasons.append("OOS_TRADE_FROZEN_STRATEGY_MISMATCH")
    executed_ids = {
        str(row.get("candidate_id") or "")
        for row in oos_ledger
        if isinstance(row, dict) and row.get("executed") is True
    }
    trade_candidate_ids = {
        str(row.get("candidate_id") or "") for row in oos_rows
    }
    if executed_ids != trade_candidate_ids:
        reasons.append("OOS_LEDGER_TRADE_SET_MISMATCH")
    if any(
        row.get("research_only") is True
        or str(row.get("scenario_source") or "") == "synthetic_fallback"
        for row in oos_rows
    ):
        reasons.append("BACKTEST_VALIDATION_CONTAINS_RESEARCH_ONLY_TRADES")

    metrics = _summarize(oos_rows)
    oos_values = [float(row.get("result_r", 0) or 0) for row in oos_rows]
    statistics = bootstrap_trade_uncertainty(
        oos_values,
        seed_material=config["config_id"],
    )
    ci_low = statistics["expectancy_r"]["p95_low"]
    ci_high = statistics["expectancy_r"]["p95_high"]
    config.update({
        "out_of_sample_trades": metrics["total_trades"],
        "oos_expectancy_r": metrics["expectancy_r"],
        "oos_profit_factor": metrics["profit_factor"],
        "oos_max_drawdown_r": metrics["max_drawdown_r"],
        "expectancy_ci_low": ci_low,
        "expectancy_ci_high": ci_high,
        "statistics_version": statistics["version"],
        "probability_positive_edge_pct": statistics[
            "probability_positive_edge_pct"
        ],
        "one_sided_p_value": statistics["one_sided_p_value"],
        "minimum_required_trades": statistics["minimum_required_trades"],
        "statistical_power_passed": statistics["statistical_power_passed"],
    })
    if in_sample_count < MIN_IN_SAMPLE_TRADES:
        reasons.append("IS_CANDIDATE_SAMPLE_TOO_SMALL")
    if metrics["total_trades"] < MIN_OUT_OF_SAMPLE_TRADES:
        reasons.append("OOS_SAMPLE_TOO_SMALL")
    if metrics["expectancy_r"] < MIN_OOS_EXPECTANCY_R:
        reasons.append("OOS_EXPECTANCY_TOO_LOW")
    if metrics["profit_factor"] < MIN_OOS_PROFIT_FACTOR:
        reasons.append("OOS_PROFIT_FACTOR_TOO_LOW")
    if metrics["max_drawdown_r"] > MAX_OOS_DRAWDOWN_R:
        reasons.append("OOS_DRAWDOWN_TOO_HIGH")
    if ci_low is None or ci_low <= 0:
        reasons.append("OOS_EXPECTANCY_CI_NOT_POSITIVE")
    if (
        statistics["probability_positive_edge_pct"] is None
        or statistics["probability_positive_edge_pct"]
        < MIN_BOOTSTRAP_PROBABILITY_POSITIVE_PCT
    ):
        reasons.append("OOS_POSITIVE_EDGE_PROBABILITY_TOO_LOW")
    if (
        statistics["one_sided_p_value"] is None
        or statistics["one_sided_p_value"] > MAX_ONE_SIDED_P_VALUE
    ):
        reasons.append("OOS_EDGE_P_VALUE_TOO_HIGH")
    if statistics["statistical_power_passed"] is not True:
        reasons.append("OOS_STATISTICAL_POWER_INSUFFICIENT")
    if str(replay.get("is_end") or "") != str(replay.get("oos_start") or ""):
        reasons.append("IS_OOS_BOUNDARY_NOT_CONTIGUOUS")
    reset = replay.get("account_state_reset")
    if not isinstance(reset, dict) or (
        int(reset.get("closed_trades", -1)) != 0
        or int(reset.get("open_positions", -1)) != 0
    ):
        reasons.append("OOS_ACCOUNT_STATE_NOT_RESET")

    wf_reasons, wf_metadata = _validate_walk_forward(result.get("walk_forward"))
    reasons.extend(wf_reasons)
    config.update(wf_metadata)
    raw_release_report = result.get("release_report")
    config["release_report"] = (
        dict(raw_release_report)
        if isinstance(raw_release_report, dict)
        else {}
    )
    reasons.extend(validate_release_report(
        config["release_report"],
        dataset_hash=str(config.get("dataset_hash") or ""),
        provenance_fingerprint=str(
            config.get("provenance_fingerprint") or ""
        ),
    ))
    current = _utc(now or datetime.now(timezone.utc))
    validated_to_time = _parse_datetime(config.get("validated_to"))
    if validated_to_time is None:
        reasons.append("VALIDATED_DATA_TIMESTAMP_MISSING")
    elif validated_to_time > current + timedelta(days=1):
        reasons.append("VALIDATED_DATA_IN_FUTURE")
    elif current - validated_to_time > timedelta(
        days=MAX_VALIDATED_DATA_AGE_DAYS
    ):
        reasons.append("VALIDATED_DATA_TOO_OLD")
    config["validation_reasons"] = _unique(reasons)
    if not reasons:
        config["status"] = "VALIDATED"
        config["validated_at"] = current.isoformat(timespec="seconds")
        config["expires_at"] = (
            current + timedelta(days=VALIDATION_TTL_DAYS)
        ).isoformat(timespec="seconds")
        config["validation_fingerprint"] = validation_fingerprint(config)
    return config


def validation_fingerprint(config: dict[str, Any]) -> str:
    """Return the deterministic integrity fingerprint for validated evidence."""

    payload = {key: config.get(key) for key in _FINGERPRINT_FIELDS}
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def has_valid_validation_fingerprint(config: dict[str, Any]) -> bool:
    fingerprint = str(config.get("validation_fingerprint", "") or "")
    return bool(fingerprint) and fingerprint == validation_fingerprint(config)


def _base_config(
    recommendation: dict[str, Any],
    *,
    symbol: str,
    trained_from: str,
    trained_to: str,
    validated_from: str,
    validated_to: str,
    in_sample_trades: int,
    scoring_contract: object,
    backtest_contract: object,
    data_manifest: object,
    backtest_provenance: object,
) -> dict[str, Any]:
    contract = (
        scoring_contract if isinstance(scoring_contract, dict) else {}
    )
    engine_contract = (
        backtest_contract if isinstance(backtest_contract, dict) else {}
    )
    manifest = data_manifest if isinstance(data_manifest, dict) else {}
    provenance = (
        backtest_provenance if isinstance(backtest_provenance, dict) else {}
    )
    regime = str(recommendation.get("regime", "") or "").strip().lower()
    side = str(recommendation.get("side", "") or "").strip().lower()
    normalized_symbol = "".join(
        character for character in symbol.upper() if character.isalnum()
    )
    identity = "|".join((
        normalized_symbol,
        regime,
        side,
        str(int(recommendation.get("min_score", 0) or 0)),
        str(float(recommendation.get("min_rr", 0) or 0)),
        str(contract.get("smc_scorer_version", "") or ""),
        str(contract.get("smc_scoring_mode", "") or ""),
        str(engine_contract.get("engine_version", "") or ""),
        str(engine_contract.get("purpose", "") or ""),
        trained_from,
        trained_to,
    ))
    identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10]
    config_id = (
        f"{normalized_symbol}-{regime}-{side}-v"
        f"{BACKTEST_CONFIG_SCHEMA_VERSION}-{identity_hash}"
    )
    return {
        "schema_version": BACKTEST_CONFIG_SCHEMA_VERSION,
        "validation_version": BACKTEST_VALIDATION_VERSION,
        "engine_contract_version": str(
            engine_contract.get("contract_version", "") or ""
        ),
        "engine_version": str(
            engine_contract.get("engine_version", "") or ""
        ),
        "purpose": normalize_backtest_purpose(
            engine_contract.get("purpose")
        ),
        "execution_parity": (
            engine_contract.get("execution_parity") is True
        ),
        "data_manifest_version": str(
            manifest.get("version", "") or ""
        ),
        "point_in_time_data": (
            engine_contract.get("point_in_time_data") is True
        ),
        "dataset_hash": str(manifest.get("dataset_hash", "") or ""),
        "data_quality_status": str(
            manifest.get("quality_status", "") or ""
        ).upper(),
        "execution_policy_version": str(
            engine_contract.get("execution_policy_version", "") or ""
        ),
        "entry_fill_model": str(
            engine_contract.get("entry_fill_model", "") or ""
        ),
        "exit_evaluation_model": str(
            engine_contract.get("exit_evaluation_model", "") or ""
        ),
        "same_bar_ambiguity_policy": str(
            engine_contract.get("same_bar_ambiguity_policy", "") or ""
        ).upper(),
        "execution_timeframe": str(
            engine_contract.get("execution_timeframe", "") or ""
        ).upper(),
        "synthetic_trades_allowed": (
            engine_contract.get("synthetic_trades_allowed") is True
        ),
        "execution_mode": str(
            engine_contract.get("execution_mode", "") or ""
        ).upper(),
        "execution_model_version": str(
            engine_contract.get("execution_model_version", "") or ""
        ),
        "cost_model_version": str(
            engine_contract.get("cost_model_version", "") or ""
        ),
        "quote_conversion_model_version": str(
            engine_contract.get("quote_conversion_model_version", "") or ""
        ),
        "cost_model_fingerprint": str(
            engine_contract.get("cost_model_fingerprint", "") or ""
        ),
        "quote_conversion_fingerprint": str(
            engine_contract.get("quote_conversion_fingerprint", "") or ""
        ),
        "candidate_ledger_version": str(
            engine_contract.get("candidate_ledger_version", "") or ""
        ),
        "candidate_replay_version": str(
            engine_contract.get("candidate_replay_version", "") or ""
        ),
        "frozen_strategy_version": str(
            engine_contract.get("frozen_strategy_version", "") or ""
        ),
        "frozen_strategy_applied": (
            engine_contract.get("frozen_strategy_applied") is True
        ),
        "oos_replay": engine_contract.get("oos_replay") is True,
        "provenance_version": str(provenance.get("version") or ""),
        "code_revision": str(provenance.get("code_revision") or ""),
        "request_fingerprint": str(
            provenance.get("request_fingerprint") or ""
        ),
        "execution_fingerprint": str(
            provenance.get("execution_fingerprint") or ""
        ),
        "provenance_fingerprint": str(
            provenance.get("provenance_fingerprint") or ""
        ),
        "config_id": config_id,
        "status": "DRAFT",
        "symbol": symbol,
        "allowed_regimes": [regime],
        "regime": regime,
        "side": side,
        "score_metric": SETUP_SCORE_METRIC,
        "min_score": int(recommendation.get("min_score", 0) or 0),
        "min_rr": float(recommendation.get("min_rr", 0) or 0),
        "scorer_version": SCANNER_SCORER_VERSION,
        "feature_version": BACKTEST_FEATURE_VERSION,
        "smc_scorer_version": str(
            contract.get("smc_scorer_version", "") or ""
        ),
        "smc_scoring_mode": str(
            contract.get("smc_scoring_mode", "") or ""
        ).lower(),
        "trained_from": trained_from,
        "trained_to": trained_to,
        "validated_from": validated_from,
        "validated_to": validated_to,
        "in_sample_trades": in_sample_trades,
        "out_of_sample_trades": 0,
        "oos_expectancy_r": 0.0,
        "oos_profit_factor": 0.0,
        "oos_max_drawdown_r": 0.0,
        "expectancy_ci_low": None,
        "expectancy_ci_high": None,
        "statistics_version": BACKTEST_STATISTICS_VERSION,
        "probability_positive_edge_pct": None,
        "one_sided_p_value": None,
        "minimum_required_trades": 0,
        "statistical_power_passed": False,
        "walk_forward_windows": 0,
        "walk_forward_verdict": "INCONCLUSIVE",
        "validated_at": "",
        "expires_at": "",
        "release_report": {},
        "validation_fingerprint": "",
        "validation_reasons": [],
        "_evidence": recommendation.get("_evidence", ""),
    }


def _draft_without_split(
    result: dict[str, Any],
    rows: list[dict[str, Any]],
    symbol: str,
    reason: str,
) -> dict[str, Any] | None:
    recommendation = _recommend_for_symbol(rows, symbol)
    if recommendation is None:
        return None
    config = _base_config(
        recommendation,
        symbol=symbol,
        trained_from="",
        trained_to="",
        validated_from="",
        validated_to="",
        in_sample_trades=len(rows),
        scoring_contract=result.get("scoring_contract"),
        backtest_contract=result.get("backtest_contract"),
        data_manifest=result.get("data_manifest"),
        backtest_provenance=result.get("backtest_provenance"),
    )
    config["validation_reasons"] = [reason]
    return config


def _symbol_trades(
    result: dict[str, Any],
    symbol: str,
) -> list[dict[str, Any]]:
    normalized_symbol = _normalize_symbol(symbol)
    raw_trades = result.get("trades", []) if isinstance(result, dict) else []
    return [
        row
        for row in raw_trades
        if isinstance(row, dict)
        and _normalize_symbol(row.get("symbol")) == normalized_symbol
    ]


def _recommend_for_symbol(
    rows: list[dict[str, Any]],
    symbol: str,
) -> dict[str, Any] | None:
    recommendations = recommend_scanner_configs({"trades": rows})
    normalized_symbol = _normalize_symbol(symbol)
    for candidate_symbol, recommendation in recommendations.items():
        if _normalize_symbol(candidate_symbol) == normalized_symbol:
            return recommendation
    return None


def _filter_config_trades(
    rows: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[dict[str, Any]]:
    regimes = {
        str(value or "").strip().lower()
        for value in config.get("allowed_regimes", [])
    }
    side = str(config.get("side", "") or "").lower()
    min_score = float(config.get("min_score", 0) or 0)
    min_rr = float(config.get("min_rr", 0) or 0)
    selected: list[dict[str, Any]] = []
    for row in rows:
        rr = _finite_float(row.get("expected_effective_rr"))
        score = _finite_float(row.get("final_score"))
        if (
            str(row.get("market_regime", "") or "").lower() in regimes
            and str(row.get("side", "") or "").lower() == side
            and score is not None
            and score >= min_score
            and rr is not None
            and rr >= min_rr
        ):
            selected.append(row)
    return selected


def _validate_walk_forward(value: Any) -> tuple[list[str], dict[str, Any]]:
    metadata = {
        "walk_forward_windows": 0,
        "walk_forward_verdict": "INCONCLUSIVE",
    }
    if not isinstance(value, dict):
        return ["WALK_FORWARD_MISSING"], metadata

    windows = value.get("windows")
    windows = windows if isinstance(windows, list) else []
    valid_windows = 0
    boundaries_valid = True
    all_oos_ids: list[str] = []
    for window in windows:
        if not isinstance(window, dict):
            boundaries_valid = False
            continue
        is_end = _parse_datetime(window.get("is_end"))
        oos_start = _parse_datetime(window.get("oos_start"))
        if is_end is None or oos_start is None or is_end != oos_start:
            boundaries_valid = False
            continue
        raw_ids = window.get("oos_trade_ids")
        if isinstance(raw_ids, list):
            all_oos_ids.extend(str(value) for value in raw_ids if str(value))
        if (
            isinstance(window.get("oos_summary"), dict)
            and isinstance(window.get("frozen_strategy_config"), dict)
            and window["frozen_strategy_config"].get("version")
            == FROZEN_STRATEGY_VERSION
            and window["frozen_strategy_config"].get("score_metric")
            == SETUP_SCORE_METRIC
            and window.get("optimization_source") == "IS_CANDIDATE_LEDGER"
            and window.get("oos_replay") is True
            and window.get("interval") == BACKTEST_INTERVAL_CONVENTION
        ):
            valid_windows += 1

    verdict = str(value.get("verdict", "INCONCLUSIVE") or "INCONCLUSIVE").upper()
    metadata = {
        "walk_forward_windows": valid_windows,
        "walk_forward_verdict": verdict,
    }
    reasons: list[str] = []
    if str(value.get("version") or "") != WALK_FORWARD_VERSION:
        reasons.append("WALK_FORWARD_VERSION_MISMATCH")
    if value.get("calendar_periods") is not True:
        reasons.append("WALK_FORWARD_CALENDAR_PERIODS_REQUIRED")
    if str(value.get("interval") or "") != BACKTEST_INTERVAL_CONVENTION:
        reasons.append("WALK_FORWARD_INTERVAL_MISMATCH")
    if value.get("deduplication_applied") is not True:
        reasons.append("WALK_FORWARD_OOS_DEDUPLICATION_REQUIRED")
    if not boundaries_valid:
        reasons.append("WALK_FORWARD_BOUNDARY_INVALID")
    if valid_windows < MIN_WALK_FORWARD_WINDOWS:
        reasons.append("WALK_FORWARD_WINDOWS_TOO_FEW")
    if verdict != "ROBUST":
        reasons.append("WALK_FORWARD_NOT_ROBUST")

    aggregate = value.get("aggregate_oos")
    if not isinstance(aggregate, dict):
        reasons.append("WALK_FORWARD_OOS_MISSING")
    else:
        if int(aggregate.get("total_trades", 0) or 0) < MIN_OUT_OF_SAMPLE_TRADES:
            reasons.append("WALK_FORWARD_OOS_SAMPLE_TOO_SMALL")
        if float(aggregate.get("expectancy_r", 0) or 0) < MIN_OOS_EXPECTANCY_R:
            reasons.append("WALK_FORWARD_OOS_EXPECTANCY_TOO_LOW")
        if float(aggregate.get("profit_factor", 0) or 0) < MIN_OOS_PROFIT_FACTOR:
            reasons.append("WALK_FORWARD_OOS_PROFIT_FACTOR_TOO_LOW")
        unique_count = len(set(all_oos_ids))
        reported_unique = int(value.get("unique_oos_trade_count", -1) or 0)
        reported_duplicates = int(
            value.get("duplicate_oos_trade_count", -1) or 0
        )
        if reported_unique != unique_count or reported_unique != int(
            aggregate.get("total_trades", 0) or 0
        ):
            reasons.append("WALK_FORWARD_OOS_UNIQUE_COUNT_MISMATCH")
        if reported_duplicates != len(all_oos_ids) - unique_count:
            reasons.append("WALK_FORWARD_OOS_DUPLICATE_COUNT_MISMATCH")
        expected_fingerprint = hashlib.sha256(
            "|".join(sorted(set(all_oos_ids))).encode("utf-8")
        ).hexdigest()
        if str(value.get("unique_oos_trade_fingerprint") or "") != (
            expected_fingerprint
        ):
            reasons.append("WALK_FORWARD_OOS_FINGERPRINT_MISMATCH")
    return _unique(reasons), metadata


def _validate_scoring_contract(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["BACKTEST_SCORING_CONTRACT_MISSING"]
    reasons: list[str] = []
    if str(value.get("score_metric", "") or "") != SETUP_SCORE_METRIC:
        reasons.append("BACKTEST_SCORE_METRIC_MISMATCH")
    if str(value.get("scorer_version", "") or "") != SCANNER_SCORER_VERSION:
        reasons.append("BACKTEST_SCORER_VERSION_MISMATCH")
    if str(value.get("feature_version", "") or "") != BACKTEST_FEATURE_VERSION:
        reasons.append("BACKTEST_FEATURE_VERSION_MISMATCH")
    if (
        str(value.get("smc_scorer_version", "") or "")
        != SMC_SCORER_V2_VERSION
    ):
        reasons.append("BACKTEST_SMC_SCORER_VERSION_MISMATCH")
    if str(value.get("smc_scoring_mode", "") or "").lower() != SMC_MODE_V2:
        reasons.append("BACKTEST_SMC_SCORING_MODE_MISMATCH")
    return reasons


def _validate_backtest_contract(value: Any) -> list[str]:
    """Require explicit execution-parity evidence for live validation."""

    if not isinstance(value, dict):
        return ["BACKTEST_ENGINE_CONTRACT_MISSING"]

    reasons: list[str] = []
    if str(value.get("contract_version", "") or "") != (
        BACKTEST_CONTRACT_VERSION
    ):
        reasons.append("BACKTEST_ENGINE_CONTRACT_VERSION_MISMATCH")
    if str(value.get("engine_version", "") or "") != (
        VALIDATION_BACKTEST_ENGINE_VERSION
    ):
        reasons.append("BACKTEST_ENGINE_VERSION_MISMATCH")
    if normalize_backtest_purpose(value.get("purpose")) != (
        BACKTEST_PURPOSE_VALIDATION
    ):
        reasons.append("BACKTEST_PURPOSE_NOT_VALIDATION")
    if value.get("execution_parity") is not True:
        reasons.append("BACKTEST_EXECUTION_PARITY_REQUIRED")
    if value.get("validation_eligible") is not True:
        reasons.append("BACKTEST_ENGINE_NOT_VALIDATION_ELIGIBLE")
    if str(value.get("data_manifest_version", "") or "") != (
        DATA_MANIFEST_VERSION
    ):
        reasons.append("BACKTEST_DATA_MANIFEST_VERSION_MISMATCH")
    if value.get("point_in_time_data") is not True:
        reasons.append("BACKTEST_POINT_IN_TIME_DATA_REQUIRED")
    if str(value.get("execution_policy_version", "") or "") != (
        BACKTEST_EXECUTION_POLICY_VERSION
    ):
        reasons.append("BACKTEST_EXECUTION_POLICY_VERSION_MISMATCH")
    if str(value.get("entry_fill_model", "") or "") != ENTRY_FILL_MODEL:
        reasons.append("BACKTEST_ENTRY_FILL_MODEL_MISMATCH")
    if str(value.get("exit_evaluation_model", "") or "") != (
        EXIT_EVALUATION_MODEL
    ):
        reasons.append("BACKTEST_EXIT_EVALUATION_MODEL_MISMATCH")
    if str(
        value.get("same_bar_ambiguity_policy", "") or ""
    ).upper() != SAME_BAR_STOP_FIRST:
        reasons.append("BACKTEST_SAME_BAR_POLICY_MISMATCH")
    if str(value.get("execution_timeframe", "") or "").upper() != "M15":
        reasons.append("BACKTEST_EXECUTION_TIMEFRAME_MISMATCH")
    if value.get("synthetic_trades_allowed") is not False:
        reasons.append("BACKTEST_SYNTHETIC_TRADES_NOT_FORBIDDEN")
    if str(value.get("execution_mode", "") or "").upper() != (
        EXECUTION_MODE_PARITY
    ):
        reasons.append("BACKTEST_EXECUTION_MODE_MISMATCH")
    if str(value.get("execution_model_version", "") or "") != (
        EXECUTION_PARITY_MODEL_VERSION
    ):
        reasons.append("BACKTEST_EXECUTION_MODEL_VERSION_MISMATCH")
    if str(value.get("cost_model_version", "") or "") != (
        EXECUTION_COST_MODEL_VERSION
    ):
        reasons.append("BACKTEST_COST_MODEL_VERSION_MISMATCH")
    if str(value.get("quote_conversion_model_version", "") or "") != (
        QUOTE_CONVERSION_MODEL_VERSION
    ):
        reasons.append("BACKTEST_QUOTE_CONVERSION_MODEL_VERSION_MISMATCH")
    if str(value.get("candidate_ledger_version", "") or "") != (
        CANDIDATE_LEDGER_VERSION
    ):
        reasons.append("BACKTEST_CANDIDATE_LEDGER_VERSION_MISMATCH")
    if str(value.get("candidate_replay_version", "") or "") != (
        CANDIDATE_REPLAY_VERSION
    ):
        reasons.append("BACKTEST_CANDIDATE_REPLAY_VERSION_MISMATCH")
    if str(value.get("frozen_strategy_version", "") or "") != (
        FROZEN_STRATEGY_VERSION
    ):
        reasons.append("BACKTEST_FROZEN_STRATEGY_VERSION_MISMATCH")
    if value.get("frozen_strategy_applied") is not True:
        reasons.append("BACKTEST_FROZEN_STRATEGY_REQUIRED")
    if value.get("oos_replay") is not True:
        reasons.append("BACKTEST_OOS_REPLAY_REQUIRED")
    cost_model = value.get("cost_model")
    if not isinstance(cost_model, dict) or cost_model.get("configured") is not True:
        reasons.append("BACKTEST_COST_MODEL_NOT_CONFIGURED")
    cost_fingerprint = str(
        value.get("cost_model_fingerprint", "") or ""
    ).lower()
    if (
        len(cost_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in cost_fingerprint)
    ):
        reasons.append("BACKTEST_COST_MODEL_FINGERPRINT_INVALID")
    quote_fingerprint = str(
        value.get("quote_conversion_fingerprint", "") or ""
    ).lower()
    if (
        len(quote_fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in quote_fingerprint)
    ):
        reasons.append("BACKTEST_QUOTE_CONVERSION_FINGERPRINT_INVALID")
    return reasons


def _validate_data_manifest(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return ["BACKTEST_DATA_MANIFEST_MISSING"]

    reasons: list[str] = []
    if str(value.get("version", "") or "") != DATA_MANIFEST_VERSION:
        reasons.append("BACKTEST_DATA_MANIFEST_VERSION_MISMATCH")
    if str(value.get("timezone", "") or "").upper() != "UTC":
        reasons.append("BACKTEST_DATA_TIMEZONE_NOT_UTC")
    if str(value.get("interval_convention", "") or "") != (
        BACKTEST_INTERVAL_CONVENTION
    ):
        reasons.append("BACKTEST_DATA_INTERVAL_MISMATCH")
    if str(value.get("quality_status", "") or "").upper() != "OK":
        reasons.append("BACKTEST_DATA_QUALITY_NOT_OK")
    if value.get("validation_eligible") is not True:
        reasons.append("BACKTEST_DATA_NOT_VALIDATION_ELIGIBLE")

    dataset_hash = str(value.get("dataset_hash", "") or "")
    if (
        len(dataset_hash) != 64
        or any(character not in "0123456789abcdef" for character in dataset_hash.lower())
    ):
        reasons.append("BACKTEST_DATASET_HASH_INVALID")

    timeframes = (
        value.get("timeframes")
        if isinstance(value.get("timeframes"), dict)
        else {}
    )
    if any(timeframe not in timeframes for timeframe in REQUIRED_BACKTEST_TIMEFRAMES):
        reasons.append("BACKTEST_REQUIRED_TIMEFRAME_MANIFEST_MISSING")
    if "M15" not in timeframes:
        reasons.append(
            "BACKTEST_EXECUTION_TIMEFRAME_MANIFEST_MISSING"
        )

    issues = value.get("issues")
    if not isinstance(issues, list):
        reasons.append("BACKTEST_DATA_ISSUES_INVALID")
    elif any(
        isinstance(issue, dict)
        and str(issue.get("severity", "") or "").upper()
        in {"WARNING", "ERROR"}
        for issue in issues
    ):
        reasons.append("BACKTEST_DATA_QUALITY_ISSUES_PRESENT")
    return reasons


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    results = [float(row.get("result_r", 0) or 0) for row in rows]
    wins = [value for value in results if value > 0]
    losses = [value for value in results if value < 0]
    gross_loss = abs(sum(losses))
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in results:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "total_trades": len(results),
        "expectancy_r": round(sum(results) / len(results), 4) if results else 0.0,
        "profit_factor": (
            round(sum(wins) / gross_loss, 4)
            if gross_loss > 0
            else (round(sum(wins), 4) if wins else 0.0)
        ),
        "max_drawdown_r": round(drawdown, 4),
    }


def _trade_time(row: dict[str, Any]) -> datetime | None:
    return _parse_datetime(
        row.get("entry_time")
        or row.get("opened_at")
        or row.get("timestamp")
    )


def _ledger_boundary(rows: list[dict[str, Any]], *, first: bool) -> str:
    values = [
        _parse_datetime(str(row.get("decision_time") or ""))
        for row in rows
        if isinstance(row, dict)
    ]
    present = [value for value in values if value is not None]
    if not present:
        return ""
    return _iso(min(present) if first else max(present))


def _trade_boundary(rows: list[dict[str, Any]], *, first: bool) -> str:
    values = [_trade_time(row) for row in rows]
    present = [value for value in values if value is not None]
    if not present:
        return ""
    return _iso(min(present) if first else max(present))


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str:
    return value.isoformat(timespec="seconds") if value is not None else ""


def _normalize_symbol(value: Any) -> str:
    return "".join(
        character for character in str(value or "").upper() if character.isalnum()
    )


def _finite_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
