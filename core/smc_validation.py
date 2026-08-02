"""Deterministic replay and calibration contract for the canonical SMC scorer.

Phase 7 proves scoring invariants and produces the calibration, out-of-sample
and walk-forward evidence for the canonical SMC scorer.  The module is
deliberately read-only: it executes ``score_smc()`` and never changes the
production decision path.  Legacy/shadow scorer comparisons no longer exist.
"""

from __future__ import annotations

from collections import defaultdict
from math import isfinite, sqrt
from statistics import mean, stdev
from typing import Any, Iterable

from core.scanner_observability import stable_hash
from core.smc_scorer import score_smc
from core.smc_versions import SMC_SCORER_VERSION


SMC_VALIDATION_CONTRACT_VERSION = "smc-phase7-validation-v2"
DEFAULT_MIN_OOS_SAMPLES = 30
DEFAULT_MIN_CALIBRATION_BUCKET_SAMPLES = 5
DEFAULT_MIN_WALK_FORWARD_WINDOWS = 2
DEFAULT_MIN_WALK_FORWARD_SAMPLES = 5

_SIDES = ("buy", "sell")
_READY_STATUSES = frozenset({"READY", "READY_NOW", "READY_TO_TRADE"})
_SCORE_BUCKETS = (
    (0, 3),
    (4, 7),
    (8, 11),
    (12, 15),
)
_PERCENT_BUCKETS = (
    (0, 19),
    (20, 39),
    (40, 59),
    (60, 79),
    (80, 100),
)


def replay_smc_cases(
    cases: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Execute the canonical SMC scorer and return normalized replay samples.

    A case supplies the immutable scorer inputs.  Status is explicit because
    Phase 7 must not route the canonical scorer into the production Candidate
    Engine.
    """

    samples: list[dict[str, Any]] = []
    for index, raw_case in enumerate(cases):
        case = raw_case if isinstance(raw_case, dict) else {}
        smc = _mapping(case.get("smc"))
        technical = _mapping(case.get("technical"))
        market_regime = _mapping(case.get("market_regime"))
        scored = score_smc(smc, technical, market_regime)
        side = _normalize_side(
            case.get("side")
            or _best_side(scored, score_key="smc_quality")
        )
        side_result = _mapping(scored.get(side))
        selected_zone = _mapping(side_result.get("selected_zone"))
        sample = {
            "sample_id": str(
                case.get("sample_id") or case.get("name") or f"sample-{index}"
            ),
            "dataset_split": _normalized_text(
                case.get("dataset_split"), "unknown"
            ),
            "observed_at": _optional_text(case.get("observed_at")),
            "walk_forward_window": _optional_text(
                case.get("walk_forward_window")
            ),
            "symbol": str(case.get("symbol") or "UNKNOWN"),
            "asset_class": _normalized_text(
                case.get("asset_class"), "unknown"
            ),
            "side": side,
            "market_regime": _regime_text(case.get("market_regime")),
            "zone_family": _normalized_text(
                selected_zone.get("family"), "none"
            ),
            "zone_quality_score": side_result.get(
                "selected_zone_quality_score"
            ),
            "zone_relevance_score": side_result.get(
                "selected_zone_relevance_score"
            ),
            "lifecycle_state": _zone_lifecycle(selected_zone),
            "linked_sweep": bool(
                selected_zone.get("liquidity_sweep_linked")
            ),
            "h4_confirmed_choch_against": (
                _h4_confirmed_choch_against(smc, side)
            ),
            "scores": {
                current_side: _mapping(scored.get(current_side)).get(
                    "smc_quality"
                )
                for current_side in _SIDES
            },
            "selected_zone_id": side_result.get("selected_zone_id"),
            "status": _normalize_status(case.get("status")),
            "result_r": case.get("result_r"),
            "scoring_version": side_result.get("scoring_version"),
        }
        normalized, reasons = normalize_smc_replay_sample(sample)
        normalized["valid"] = not reasons
        normalized["validation_reason_codes"] = reasons
        samples.append(normalized)
    return samples


def replay_sample_from_analysis_document(
    document: dict[str, Any],
    *,
    result_r: float | None = None,
    dataset_split: str = "unknown",
    asset_class: str = "unknown",
) -> dict[str, Any]:
    """Extract one replay sample from a saved scanner analysis document.

    Only the canonical ``smc_scoring.sides`` payload is used.  Documents that
    predate the canonical contract carry no ``sides`` and fail closed instead
    of selecting a legacy/shadow branch.
    """

    payload = document if isinstance(document, dict) else {}
    row = _mapping(payload.get("row_summary"))
    analysis = _mapping(payload.get("analysis_result"))
    diagnostics = _mapping(analysis.get("smc_scoring"))
    sides = _mapping(diagnostics.get("sides"))
    consumer = _mapping(diagnostics.get("consumer_contract"))
    consumer_sides = _mapping(consumer.get("sides"))
    candidate = _mapping(payload.get("candidate_decision"))
    side = _normalize_side(
        candidate.get("selected_side")
        or row.get("selected_side")
        or _best_side(sides, score_key="score")
    )
    side_result = _mapping(sides.get(side))
    consumer_side = _mapping(consumer_sides.get(side))
    selected_zone = _mapping(consumer_side.get("selected_zone"))
    smc = _mapping(analysis.get("smc"))

    sample = {
        "sample_id": str(
            row.get("row_id")
            or _mapping(payload.get("observability")).get("row_id")
            or f"{payload.get('symbol', 'UNKNOWN')}:{stable_hash(payload)[:12]}"
        ),
        "dataset_split": dataset_split,
        "observed_at": _optional_text(
            _mapping(payload.get("scan_context")).get("started_at")
            or analysis.get("timestamp")
            or row.get("timestamp")
        ),
        "walk_forward_window": _optional_text(
            _mapping(payload.get("validation_metadata")).get(
                "walk_forward_window"
            )
            or row.get("walk_forward_window")
        ),
        "symbol": str(payload.get("symbol") or row.get("symbol") or "UNKNOWN"),
        "asset_class": asset_class,
        "side": side,
        "market_regime": _regime_text(analysis.get("market_regime")),
        "zone_family": _normalized_text(
            selected_zone.get("family"), "none"
        ),
        "zone_quality_score": side_result.get(
            "selected_zone_quality_score"
        ),
        "zone_relevance_score": side_result.get(
            "selected_zone_relevance_score"
        ),
        "lifecycle_state": _zone_lifecycle(selected_zone),
        "linked_sweep": bool(selected_zone.get("liquidity_sweep_linked")),
        "h4_confirmed_choch_against": bool(
            row.get("h4_confirmed_choch_against_direction")
            or _mapping(analysis.get("trade_gate")).get(
                "h4_confirmed_choch_against_direction"
            )
            or _h4_confirmed_choch_against(smc, side)
        ),
        "scores": {
            current_side: _mapping(sides.get(current_side)).get("score")
            for current_side in _SIDES
        },
        "selected_zone_id": (
            side_result.get("selected_zone_id")
            or consumer_side.get("selected_zone_id")
        ),
        "status": _normalize_status(
            candidate.get("status") or row.get("candidate_status")
        ),
        "result_r": result_r,
        "scoring_version": side_result.get("scoring_version"),
    }
    normalized, reasons = normalize_smc_replay_sample(sample)
    normalized["valid"] = not reasons
    normalized["validation_reason_codes"] = reasons
    return normalized


def normalize_smc_replay_sample(
    value: dict[str, Any],
) -> tuple[dict[str, Any], list[str]]:
    """Normalize one sample and fail closed on missing scorer evidence."""

    raw = value if isinstance(value, dict) else {}
    reasons: list[str] = []
    sample_id = str(raw.get("sample_id") or "").strip()
    if not sample_id:
        reasons.append("SAMPLE_ID_MISSING")
        sample_id = "UNKNOWN"
    side = _normalize_side(raw.get("side"))
    if side not in _SIDES:
        reasons.append("SIDE_INVALID")
        side = "buy"

    scores = _normalize_scores(raw.get("scores"), reasons)
    result_r = _optional_finite(raw.get("result_r"))
    if raw.get("result_r") is not None and result_r is None:
        reasons.append("RESULT_R_INVALID")

    quality = _optional_bounded(raw.get("zone_quality_score"), 0, 100)
    relevance = _optional_bounded(
        raw.get("zone_relevance_score"), 0, 100
    )
    if (
        raw.get("zone_quality_score") is not None
        and quality is None
    ):
        reasons.append("ZONE_QUALITY_INVALID")
    if (
        raw.get("zone_relevance_score") is not None
        and relevance is None
    ):
        reasons.append("ZONE_RELEVANCE_INVALID")

    dataset_split = _normalized_text(
        raw.get("dataset_split"), "unknown"
    )
    observed_at = _optional_text(raw.get("observed_at"))
    if dataset_split == "oos" and result_r is not None and observed_at is None:
        reasons.append("OOS_OBSERVED_AT_MISSING")

    scoring_version = _optional_text(raw.get("scoring_version"))
    if scoring_version is None:
        reasons.append("SCORING_VERSION_MISSING")
    elif scoring_version != SMC_SCORER_VERSION:
        reasons.append("SCORING_VERSION_UNSUPPORTED")

    normalized = {
        "sample_id": sample_id,
        "dataset_split": dataset_split,
        "observed_at": observed_at,
        "walk_forward_window": _optional_text(
            raw.get("walk_forward_window")
        ),
        "symbol": str(raw.get("symbol") or "UNKNOWN").upper(),
        "asset_class": _normalized_text(
            raw.get("asset_class"), "unknown"
        ),
        "side": side,
        "market_regime": _normalized_text(
            raw.get("market_regime"), "unknown"
        ),
        "zone_family": _normalized_text(
            raw.get("zone_family"), "none"
        ),
        "zone_quality_score": quality,
        "zone_relevance_score": relevance,
        "quality_bucket": _bucket_label(quality, _PERCENT_BUCKETS),
        "relevance_bucket": _bucket_label(relevance, _PERCENT_BUCKETS),
        "lifecycle_state": _normalized_text(
            raw.get("lifecycle_state"), "unknown"
        ),
        "linked_sweep": bool(raw.get("linked_sweep")),
        "h4_confirmed_choch_against": bool(
            raw.get("h4_confirmed_choch_against")
        ),
        "scores": scores,
        "selected_zone_id": _optional_text(
            raw.get("selected_zone_id")
        ),
        "status": _normalize_status(raw.get("status")),
        "result_r": result_r,
        "scoring_version": scoring_version,
    }
    return normalized, _unique(reasons)


def build_smc_validation_report(
    samples: Iterable[dict[str, Any]],
    *,
    min_oos_samples: int = DEFAULT_MIN_OOS_SAMPLES,
    min_calibration_bucket_samples: int = (
        DEFAULT_MIN_CALIBRATION_BUCKET_SAMPLES
    ),
    min_walk_forward_windows: int = DEFAULT_MIN_WALK_FORWARD_WINDOWS,
    min_walk_forward_samples: int = DEFAULT_MIN_WALK_FORWARD_SAMPLES,
) -> dict[str, Any]:
    """Build deterministic replay, stratification and release-gate evidence."""

    normalized: list[dict[str, Any]] = []
    invalid: list[dict[str, Any]] = []
    for raw in samples:
        item, reasons = normalize_smc_replay_sample(raw)
        if reasons:
            invalid.append({
                "sample_id": item["sample_id"],
                "reason_codes": reasons,
            })
        else:
            normalized.append(item)
    normalized.sort(key=lambda item: item["sample_id"])
    duplicate_conflicts = _duplicate_conflicts(normalized)
    oos_samples = [
        sample
        for sample in normalized
        if sample["dataset_split"] == "oos"
    ]

    replay = _replay_metrics(normalized)
    calibration = _calibration_curve(
        oos_samples,
        min_bucket_samples=max(1, int(min_calibration_bucket_samples)),
    )
    stratification = _stratification(oos_samples)
    oos = _oos_quality(normalized)
    walk_forward = _walk_forward_validation(
        oos_samples,
        min_windows=max(1, int(min_walk_forward_windows)),
        min_samples=max(1, int(min_walk_forward_samples)),
    )

    blockers: list[str] = []
    if not normalized:
        blockers.append("NO_VALID_REPLAY_SAMPLES")
    if invalid:
        blockers.append("INVALID_REPLAY_SAMPLE")
    if duplicate_conflicts:
        blockers.append("NON_DETERMINISTIC_DUPLICATE_SAMPLE")
    if replay["choch_against_ready_count"]:
        blockers.append("CHOCH_AGAINST_READY")
    if oos["ready_sample_size"] < max(1, int(min_oos_samples)):
        blockers.append("OOS_SAMPLE_TOO_SMALL")
    elif oos["metrics"]["expectancy_r"] is None:
        blockers.append("OOS_EVIDENCE_MISSING")
    if not calibration["sample_guard_passed"]:
        blockers.append("CALIBRATION_INSUFFICIENT")
    elif not calibration["reasonable_relationship"]:
        blockers.append("CALIBRATION_NOT_MONOTONIC")
    if not walk_forward["sample_guard_passed"]:
        blockers.append("WALK_FORWARD_INSUFFICIENT")
    elif not walk_forward["robust"]:
        blockers.append("WALK_FORWARD_UNSTABLE")

    report = {
        "contract_version": SMC_VALIDATION_CONTRACT_VERSION,
        "scoring_version": SMC_SCORER_VERSION,
        "sample_count": len(normalized),
        "invalid_sample_count": len(invalid),
        "invalid_samples": invalid,
        "duplicate_conflicts": duplicate_conflicts,
        "thresholds": {
            "min_oos_samples": max(1, int(min_oos_samples)),
            "min_calibration_bucket_samples": max(
                1, int(min_calibration_bucket_samples)
            ),
            "min_walk_forward_windows": max(
                1, int(min_walk_forward_windows)
            ),
            "min_walk_forward_samples": max(
                1, int(min_walk_forward_samples)
            ),
        },
        "replay": replay,
        "oos": oos,
        "walk_forward": walk_forward,
        "calibration": calibration,
        "statistical_dataset_split": "oos",
        "stratification": stratification,
        "release_gate": {
            "ready": not blockers,
            "block_reason_codes": _unique(blockers),
        },
    }
    report["report_hash"] = stable_hash(report)
    return report


def _replay_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    gaps: list[float] = []
    no_zone = 0
    choch_against_ready = 0
    losing_ready = 0

    for sample in samples:
        gaps.append(abs(
            sample["scores"]["buy"]
            - sample["scores"]["sell"]
        ))
        if sample.get("selected_zone_id") is None:
            no_zone += 1
        losing_outcome = (
            sample.get("result_r") is not None
            and sample["result_r"] <= 0
        )
        if _is_ready(sample["status"]) and losing_outcome:
            losing_ready += 1
        if (
            _is_ready(sample["status"])
            and sample["h4_confirmed_choch_against"]
        ):
            choch_against_ready += 1

    return {
        "score_distribution": _score_distribution(samples, "scores"),
        "buy_sell_gap_mean": _rounded_mean(gaps),
        "losing_ready_count": losing_ready,
        "no_zone_count": no_zone,
        "choch_against_ready_count": choch_against_ready,
    }


def _oos_quality(
    samples: list[dict[str, Any]],
) -> dict[str, Any]:
    oos = [
        sample
        for sample in samples
        if sample["dataset_split"] == "oos"
    ]
    ready = [
        sample for sample in oos if _is_ready(sample["status"])
    ]
    return {
        "oos_sample_count": len(oos),
        "ready_sample_size": len(ready),
        "metrics": _outcome_metrics(ready),
    }


def _walk_forward_validation(
    samples: list[dict[str, Any]],
    *,
    min_windows: int,
    min_samples: int,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        window = sample.get("walk_forward_window")
        if window is not None and _is_ready(sample["status"]):
            grouped[str(window)].append(sample)

    windows: list[dict[str, Any]] = []
    for window, values in sorted(grouped.items()):
        metrics = _outcome_metrics(values)
        eligible = metrics["sample_size"] >= min_samples
        windows.append({
            "window": window,
            **metrics,
            "eligible": eligible,
        })
    eligible_windows = [
        window
        for window in windows
        if window["eligible"] and window["expectancy_r"] is not None
    ]
    positive_windows = sum(
        window["expectancy_r"] >= 0
        for window in eligible_windows
    )
    positive_rate = (
        round(positive_windows / len(eligible_windows), 4)
        if eligible_windows
        else None
    )
    aggregate = _outcome_metrics([
        sample
        for sample in samples
        if (
            sample.get("walk_forward_window") is not None
            and _is_ready(sample["status"])
        )
    ])
    sample_guard_passed = len(eligible_windows) >= min_windows
    robust = bool(
        sample_guard_passed
        and positive_rate is not None
        and positive_rate >= 0.5
        and aggregate["expectancy_r"] is not None
        and aggregate["expectancy_r"] >= 0
    )
    return {
        "windows": windows,
        "eligible_window_count": len(eligible_windows),
        "min_windows": min_windows,
        "min_samples_per_window": min_samples,
        "positive_window_rate": positive_rate,
        "aggregate": aggregate,
        "sample_guard_passed": sample_guard_passed,
        "robust": robust,
        "verdict": (
            "ROBUST"
            if robust
            else "WEAK"
            if sample_guard_passed
            else "INCONCLUSIVE"
        ),
    }


def _calibration_curve(
    samples: list[dict[str, Any]],
    *,
    min_bucket_samples: int,
) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        score = sample["scores"][sample["side"]]
        grouped[_bucket_label(score, _SCORE_BUCKETS)].append(sample)

    buckets: list[dict[str, Any]] = []
    for low, high in _SCORE_BUCKETS:
        label = f"{low}-{high}"
        values = grouped.get(label, [])
        metrics = _outcome_metrics(values)
        buckets.append({
            "bucket": label,
            "score_low": low,
            "score_high": high,
            **metrics,
            "eligible": metrics["sample_size"] >= min_bucket_samples,
        })
    eligible = [
        bucket
        for bucket in buckets
        if bucket["eligible"] and bucket["expectancy_r"] is not None
    ]
    expectancy_monotonic = _non_decreasing(
        [bucket["expectancy_r"] for bucket in eligible],
        tolerance=0.10,
    )
    win_rate_monotonic = _non_decreasing(
        [bucket["win_rate"] for bucket in eligible],
        tolerance=0.05,
    )
    enough = len(eligible) >= 2
    return {
        "buckets": buckets,
        "eligible_bucket_count": len(eligible),
        "min_bucket_samples": min_bucket_samples,
        "sample_guard_passed": enough,
        "expectancy_monotonic": expectancy_monotonic if enough else None,
        "win_rate_monotonic": win_rate_monotonic if enough else None,
        "reasonable_relationship": (
            enough and (expectancy_monotonic or win_rate_monotonic)
        ),
    }


def _stratification(
    samples: list[dict[str, Any]],
) -> dict[str, dict[str, dict[str, Any]]]:
    fields = (
        "symbol",
        "asset_class",
        "side",
        "market_regime",
        "zone_family",
        "quality_bucket",
        "relevance_bucket",
        "lifecycle_state",
        "linked_sweep",
        "h4_confirmed_choch_against",
        "scoring_version",
    )
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for field in fields:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for sample in samples:
            key = str(sample.get(field, "unknown")).lower()
            groups[key].append(sample)
        result[field] = {
            key: _outcome_metrics(values)
            for key, values in sorted(groups.items())
        }
    return result


def _outcome_metrics(samples: list[dict[str, Any]]) -> dict[str, Any]:
    results = [
        float(sample["result_r"])
        for sample in sorted(
            samples,
            key=lambda item: (
                str(item.get("observed_at") or ""),
                str(item.get("sample_id") or ""),
            ),
        )
        if sample.get("result_r") is not None
    ]
    if not results:
        return {
            "sample_size": 0,
            "win_rate": None,
            "expectancy_r": None,
            "expectancy_ci_low": None,
            "expectancy_ci_high": None,
            "profit_factor": None,
            "max_drawdown_r": None,
        }
    average = mean(results)
    if len(results) >= 2:
        margin = 1.96 * stdev(results) / sqrt(len(results))
        ci_low = average - margin
        ci_high = average + margin
    else:
        ci_low = ci_high = average
    gains = sum(value for value in results if value > 0)
    losses = abs(sum(value for value in results if value < 0))
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for value in results:
        equity += value
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return {
        "sample_size": len(results),
        "win_rate": round(
            sum(value > 0 for value in results) / len(results),
            4,
        ),
        "expectancy_r": round(average, 4),
        "expectancy_ci_low": round(ci_low, 4),
        "expectancy_ci_high": round(ci_high, 4),
        "profit_factor": (
            round(gains / losses, 4)
            if losses > 0
            else None
        ),
        "max_drawdown_r": round(drawdown, 4),
    }


def _score_distribution(
    samples: list[dict[str, Any]],
    field: str,
) -> dict[str, int]:
    counts = {f"{low}-{high}": 0 for low, high in _SCORE_BUCKETS}
    for sample in samples:
        for side in _SIDES:
            label = _bucket_label(sample[field][side], _SCORE_BUCKETS)
            counts[label] += 1
    return counts


def _duplicate_conflicts(
    samples: list[dict[str, Any]],
) -> list[str]:
    fingerprints: dict[str, str] = {}
    conflicts: list[str] = []
    for sample in samples:
        sample_id = sample["sample_id"]
        fingerprint = stable_hash(sample)
        previous = fingerprints.get(sample_id)
        if previous is not None and previous != fingerprint:
            conflicts.append(sample_id)
        fingerprints[sample_id] = fingerprint
    return sorted(set(conflicts))


def _normalize_scores(
    value: object,
    reasons: list[str],
) -> dict[str, float]:
    source = _mapping(value)
    result: dict[str, float] = {}
    for side in _SIDES:
        score = _optional_bounded(source.get(side), 0, 15)
        if score is None:
            reasons.append(f"{side.upper()}_SCORE_INVALID")
            score = 0.0
        result[side] = score
    return result


def _bucket_label(
    value: float | int | None,
    buckets: tuple[tuple[int, int], ...],
) -> str:
    if value is None:
        return "unknown"
    for low, high in buckets:
        if low <= value <= high:
            return f"{low}-{high}"
    return "unknown"


def _best_side(
    values: dict[str, Any],
    *,
    score_key: str,
) -> str:
    scores = {
        side: _optional_finite(_mapping(values.get(side)).get(score_key))
        or 0.0
        for side in _SIDES
    }
    return _best_side_from_scores(scores)


def _best_side_from_scores(scores: dict[str, float]) -> str:
    if scores["buy"] == scores["sell"]:
        return "neutral"
    return "buy" if scores["buy"] > scores["sell"] else "sell"


def _h4_confirmed_choch_against(
    smc: dict[str, Any],
    side: str,
) -> bool:
    h4 = _mapping(smc.get("H4"))
    opposite = "bearish" if side == "buy" else "bullish"
    return bool(
        h4.get("choch")
        and h4.get("choch_confirmed")
        and str(h4.get("displacement") or "").lower() == opposite
    )


def _zone_lifecycle(zone: dict[str, Any]) -> str:
    if not zone:
        return "none"
    if zone.get("broken") or zone.get("lifecycle_broken"):
        return "broken"
    visits = _optional_finite(
        zone.get(
            "independent_retest_count",
            zone.get("test_count"),
        )
    ) or 0
    if visits >= 2:
        return "multi_visit"
    if visits == 1:
        return "first_mitigation"
    return "fresh"


def _regime_text(value: object) -> str:
    if isinstance(value, dict):
        return _normalized_text(
            value.get("primary") or value.get("regime"),
            "unknown",
        )
    return _normalized_text(value, "unknown")


def _normalize_status(value: object) -> str:
    text = str(value or "").strip().upper()
    aliases = {
        "READY_TO_TRADE": "READY_NOW",
        "READY": "READY_NOW",
        "WAIT": "WAITING_CONFIRMATION",
        "WATCH": "WATCH_ZONE",
    }
    return aliases.get(text, text or "UNKNOWN")


def _normalize_side(value: object) -> str:
    return str(value or "").strip().lower()


def _is_ready(value: object) -> bool:
    return str(value or "").strip().upper() in _READY_STATUSES


def _mapping(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalized_text(value: object, default: str) -> str:
    return str(value or default).strip().lower() or default


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _optional_finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _optional_bounded(
    value: object,
    low: float,
    high: float,
) -> float | None:
    number = _optional_finite(value)
    if number is None or number < low or number > high:
        return None
    return number


def _rounded_mean(values: list[float]) -> float | None:
    return round(mean(values), 4) if values else None


def _non_decreasing(
    values: list[float],
    *,
    tolerance: float,
) -> bool:
    return all(
        current + tolerance >= previous
        for previous, current in zip(values, values[1:])
    )


def _unique(values: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value)))
