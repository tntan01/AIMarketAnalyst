"""Phase-5 validation contract for scanner backtest configurations.

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
import random
from typing import Any

from core.backtest_to_scanner_config import recommend_scanner_configs
from core.scanner_models import (
    SCANNER_FEATURE_VERSION,
    SCANNER_SCORER_VERSION,
    SETUP_SCORE_METRIC,
)
from core.smc_scoring_contract import SMC_MODE_V2
from core.smc_versions import SMC_SCORER_V2_VERSION


BACKTEST_CONFIG_SCHEMA_VERSION = 4
BACKTEST_FEATURE_VERSION = SCANNER_FEATURE_VERSION
BACKTEST_VALIDATION_VERSION = "phase8-smc-v2-oos-v1"

MIN_IN_SAMPLE_TRADES = 10
MIN_OUT_OF_SAMPLE_TRADES = 8
MIN_WALK_FORWARD_WINDOWS = 2
MIN_OOS_EXPECTANCY_R = 0.10
MIN_OOS_PROFIT_FACTOR = 1.20
MAX_OOS_DRAWDOWN_R = 8.0
VALIDATION_TTL_DAYS = 90

_FINGERPRINT_FIELDS = (
    "schema_version",
    "validation_version",
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
    "walk_forward_windows",
    "walk_forward_verdict",
    "validated_at",
    "expires_at",
)


def build_backtest_config(
    result: dict[str, Any],
    *,
    symbol: str,
    now: datetime | None = None,
) -> dict[str, Any] | None:
    """Build a DRAFT or VALIDATED config from one backtest snapshot.

    The first 70% of chronological trades are the only rows visible to the
    recommendation optimizer.  The remaining 30% are held out and filtered
    using the selected configuration without re-optimization.
    """

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
    )

    reasons: list[str] = []
    reasons.extend(_validate_scoring_contract(result.get("scoring_contract")))
    selected_oos = _filter_config_trades(out_of_sample, config)
    metrics = _summarize(selected_oos)
    ci_low, ci_high = _bootstrap_expectancy_ci(
        [float(row.get("result_r", 0) or 0) for row in selected_oos],
        seed_material=config["config_id"],
    )
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
) -> dict[str, Any]:
    contract = (
        scoring_contract if isinstance(scoring_contract, dict) else {}
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
        "walk_forward_windows": 0,
        "walk_forward_verdict": "INCONCLUSIVE",
        "validated_at": "",
        "expires_at": "",
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
    for window in windows:
        if not isinstance(window, dict):
            boundaries_valid = False
            continue
        is_end = _parse_datetime(window.get("is_end"))
        oos_start = _parse_datetime(window.get("oos_start"))
        if is_end is None or oos_start is None or is_end > oos_start:
            boundaries_valid = False
            continue
        if isinstance(window.get("oos_summary"), dict):
            valid_windows += 1

    verdict = str(value.get("verdict", "INCONCLUSIVE") or "INCONCLUSIVE").upper()
    metadata = {
        "walk_forward_windows": valid_windows,
        "walk_forward_verdict": verdict,
    }
    reasons: list[str] = []
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


def _bootstrap_expectancy_ci(
    values: list[float],
    *,
    seed_material: str,
    samples: int = 1000,
) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    digest = hashlib.sha256(seed_material.encode("utf-8")).digest()
    rng = random.Random(int.from_bytes(digest[:8], "big"))
    size = len(values)
    means = sorted(
        sum(values[rng.randrange(size)] for _ in range(size)) / size
        for _ in range(samples)
    )
    return round(means[24], 4), round(means[974], 4)


def _trade_time(row: dict[str, Any]) -> datetime | None:
    return _parse_datetime(
        row.get("entry_time")
        or row.get("opened_at")
        or row.get("timestamp")
    )


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
