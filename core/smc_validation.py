"""Deterministic replay and calibration contract for SMC scorer v2.

Phase 7 proves scoring invariants and produces the evidence required by the
rollout phase.  The module is deliberately read-only: it executes v2 through
the existing shadow contract and never changes the active decision path.
"""

from __future__ import annotations

from collections import defaultdict
from math import isfinite, sqrt
from statistics import mean, stdev
from typing import Any, Iterable

from core.scanner_observability import stable_hash
from core.smc_scorer import score_smc
from core.smc_versions import SMC_RAW_ZONE_VERSION


SMC_VALIDATION_CONTRACT_VERSION = "smc-phase7-validation-v1"
DEFAULT_MIN_OOS_SAMPLES = 30
DEFAULT_MIN_CALIBRATION_BUCKET_SAMPLES = 5
DEFAULT_OOS_DEGRADATION_TOLERANCE_R = 0.10
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
    """Execute canonical SMC scoring and return normalized replay samples.

    A case supplies the immutable scorer inputs plus the observed legacy-side
    scores.  Status is explicit because Phase 7 must not route the canonical
    scorer into the production Candidate Engine.
    """

    samples: list[dict[str, Any]] = []
    for index, raw_case in enumerate(cases):
        case = raw_case if isinstance(raw_case, dict) else {}
        smc = _mapping(case.get("smc"))
        technical = _mapping(case.get("technical"))
        market_regime = _mapping(case.get("market_regime"))
        shadow = score_smc(smc, technical, market_regime)
        active = _legacy_side_snapshots(_mapping(case.get("active_scores")))
        side = _normalize_side(
            case.get("side") or _best_side(active, score_key="signal_score")
        )
        shadow_side = _mapping(shadow.get(side))
        selected_zone = _mapping(shadow_side.get("selected_zone"))
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
            "zone_quality_score": shadow_side.get(
                "selected_zone_quality_score"
            ),
            "zone_relevance_score": shadow_side.get(
                "selected_zone_relevance_score"
            ),
            "lifecycle_state": _zone_lifecycle(selected_zone),
            "linked_sweep": bool(
                selected_zone.get("liquidity_sweep_linked")
            ),
            "h4_confirmed_choch_against": (
                _h4_confirmed_choch_against(smc, side)
            ),
            "legacy_scores": {
                current_side: _mapping(active.get(current_side)).get(
                    "smc_quality"
                )
                for current_side in _SIDES
            },
            "v2_scores": {
                current_side: _mapping(shadow.get(current_side)).get(
                    "smc_quality"
                )
                for current_side in _SIDES
            },
            "legacy_selected_zone_id": _mapping(active.get(side)).get(
                "selected_zone_id"
            ),
            "v2_selected_zone_id": shadow_side.get("selected_zone_id"),
            "legacy_status": _normalize_status(case.get("legacy_status")),
            "v2_status": _normalize_status(case.get("v2_status")),
            "result_r": case.get("result_r"),
            "legacy_scoring_version": _mapping(active.get(side)).get(
                "scoring_version"
            ),
            "v2_scoring_version": shadow_side.get("scoring_version"),
        }
        normalized, reasons = normalize_smc_replay_sample(sample)
        normalized["valid"] = not reasons
        normalized["validation_reason_codes"] = reasons
        samples.append(normalized)
    return samples


def _legacy_side_snapshots(
    active_scores: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Normalize the observed legacy-side scores into a replay snapshot."""

    source = active_scores if isinstance(active_scores, dict) else {}
    result: dict[str, dict[str, Any]] = {}
    for side in _SIDES:
        score = (
            source.get(side)
            if isinstance(source.get(side), dict)
            else {}
        )
        flags = (
            score.get("smc_flags")
            if isinstance(score.get("smc_flags"), dict)
            else {}
        )
        result[side] = {
            "smc_quality": _safe_score(score.get("smc_quality")),
            "smc_reason": str(score.get("smc_reason", "") or ""),
            "signal_score": _safe_score(score.get("signal_score")),
            "scoring_version": SMC_RAW_ZONE_VERSION,
            "selected_zone_id": flags.get("selected_zone_id"),
            "selected_zone_type": flags.get("selected_zone_type"),
            "selected_zone_score": flags.get("selected_zone_score"),
            "selected_zone_quality_score": flags.get(
                "selected_zone_quality_score"
            ),
            "selected_zone_relevance_score": flags.get(
                "selected_zone_relevance_score"
            ),
            "selected_zone_setup_score": flags.get(
                "selected_zone_setup_score"
            ),
        }
    return result


def replay_sample_from_analysis_document(
    document: dict[str, Any],
    *,
    result_r: float | None = None,
    dataset_split: str = "unknown",
    asset_class: str = "unknown",
    v2_status: str | None = None,
) -> dict[str, Any]:
    """Extract one replay sample from a saved scanner analysis document."""

    payload = document if isinstance(document, dict) else {}
    row = _mapping(payload.get("row_summary"))
    analysis = _mapping(payload.get("analysis_result"))
    diagnostics = _mapping(analysis.get("smc_scoring"))
    active = _mapping(diagnostics.get("active"))
    shadow = _mapping(diagnostics.get("shadow"))
    candidate = _mapping(payload.get("candidate_decision"))
    side = _normalize_side(
        candidate.get("selected_side")
        or row.get("selected_side")
        or _best_side(active, score_key="signal_score")
    )
    active_side = _mapping(active.get(side))
    shadow_side = _mapping(shadow.get(side))
    shadow_zone = _mapping(shadow_side.get("selected_zone"))
    consumer = _mapping(diagnostics.get("consumer_contract"))
    consumer_side = _mapping(_mapping(consumer.get("sides")).get(side))
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
            shadow_zone.get("family"), "none"
        ),
        "zone_quality_score": shadow_side.get(
            "selected_zone_quality_score"
        ),
        "zone_relevance_score": shadow_side.get(
            "selected_zone_relevance_score"
        ),
        "lifecycle_state": _zone_lifecycle(shadow_zone),
        "linked_sweep": bool(shadow_zone.get("liquidity_sweep_linked")),
        "h4_confirmed_choch_against": bool(
            row.get("h4_confirmed_choch_against_direction")
            or _mapping(analysis.get("trade_gate")).get(
                "h4_confirmed_choch_against_direction"
            )
            or _h4_confirmed_choch_against(smc, side)
        ),
        "legacy_scores": {
            current_side: _mapping(active.get(current_side)).get("smc_quality")
            for current_side in _SIDES
        },
        "v2_scores": {
            current_side: _mapping(shadow.get(current_side)).get("smc_quality")
            for current_side in _SIDES
        },
        "legacy_selected_zone_id": (
            active_side.get("selected_zone_id")
            or consumer_side.get("selected_zone_id")
        ),
        "v2_selected_zone_id": (
            shadow_side.get("selected_zone_id")
            or consumer_side.get("selected_zone_id")
        ),
        "legacy_status": _normalize_status(
            candidate.get("status") or row.get("candidate_status")
        ),
        "v2_status": _normalize_status(
            v2_status
            or row.get("shadow_candidate_status")
            or _mapping(payload.get("smc_validation")).get("v2_status")
        ),
        "result_r": result_r,
        "legacy_scoring_version": active_side.get("scoring_version"),
        "v2_scoring_version": shadow_side.get("scoring_version"),
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

    legacy_scores = _normalize_scores(raw.get("legacy_scores"), reasons, "LEGACY")
    v2_scores = _normalize_scores(raw.get("v2_scores"), reasons, "V2")
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
        "legacy_scores": legacy_scores,
        "v2_scores": v2_scores,
        "legacy_selected_zone_id": _optional_text(
            raw.get("legacy_selected_zone_id")
        ),
        "v2_selected_zone_id": _optional_text(
            raw.get("v2_selected_zone_id")
        ),
        "legacy_status": _normalize_status(raw.get("legacy_status")),
        "v2_status": _normalize_status(raw.get("v2_status")),
        "result_r": result_r,
        "legacy_scoring_version": _optional_text(
            raw.get("legacy_scoring_version")
        ),
        "v2_scoring_version": _optional_text(
            raw.get("v2_scoring_version")
        ),
    }
    if normalized["legacy_scoring_version"] is None:
        reasons.append("LEGACY_SCORING_VERSION_MISSING")
    if normalized["v2_scoring_version"] is None:
        reasons.append("V2_SCORING_VERSION_MISSING")
    if (
        normalized["legacy_scoring_version"] is not None
        and normalized["legacy_scoring_version"]
        == normalized["v2_scoring_version"]
    ):
        reasons.append("SCORING_VERSION_PAIR_INVALID")
    return normalized, _unique(reasons)


def build_smc_validation_report(
    samples: Iterable[dict[str, Any]],
    *,
    min_oos_samples: int = DEFAULT_MIN_OOS_SAMPLES,
    min_calibration_bucket_samples: int = (
        DEFAULT_MIN_CALIBRATION_BUCKET_SAMPLES
    ),
    oos_degradation_tolerance_r: float = (
        DEFAULT_OOS_DEGRADATION_TOLERANCE_R
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
    version_pairs = sorted({
        (
            str(sample["legacy_scoring_version"]),
            str(sample["v2_scoring_version"]),
        )
        for sample in normalized
    })
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
    oos = _oos_comparison(
        normalized,
        tolerance_r=max(0.0, float(oos_degradation_tolerance_r)),
    )
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
    if len(version_pairs) > 1:
        blockers.append("MIXED_SCORING_VERSION_PAIR")
    if replay["choch_against_ready_count"]:
        blockers.append("CHOCH_AGAINST_READY")
    if oos["v2_ready_sample_size"] < max(1, int(min_oos_samples)):
        blockers.append("OOS_SAMPLE_TOO_SMALL")
    elif oos["degradation_r"] is None:
        blockers.append("OOS_EVIDENCE_MISSING")
    elif oos["degradation_exceeded"]:
        blockers.append("OOS_DEGRADATION_EXCEEDED")
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
        "sample_count": len(normalized),
        "invalid_sample_count": len(invalid),
        "invalid_samples": invalid,
        "duplicate_conflicts": duplicate_conflicts,
        "scoring_version_pairs": [
            {
                "legacy": legacy_version,
                "v2": v2_version,
            }
            for legacy_version, v2_version in version_pairs
        ],
        "thresholds": {
            "min_oos_samples": max(1, int(min_oos_samples)),
            "min_calibration_bucket_samples": max(
                1, int(min_calibration_bucket_samples)
            ),
            "oos_degradation_tolerance_r": max(
                0.0, float(oos_degradation_tolerance_r)
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
    transitions: dict[str, int] = defaultdict(int)
    legacy_gaps: list[float] = []
    v2_gaps: list[float] = []
    stable_zones = 0
    comparable_zones = 0
    direction_changes = 0
    legacy_losing_ready = 0
    v2_losing_ready = 0
    false_ready_removed = 0
    no_zone = 0
    choch_against_ready = 0

    for sample in samples:
        transitions[
            f"{sample['legacy_status']}->{sample['v2_status']}"
        ] += 1
        legacy_gaps.append(abs(
            sample["legacy_scores"]["buy"]
            - sample["legacy_scores"]["sell"]
        ))
        v2_gaps.append(abs(
            sample["v2_scores"]["buy"]
            - sample["v2_scores"]["sell"]
        ))
        legacy_best = _best_side_from_scores(sample["legacy_scores"])
        v2_best = _best_side_from_scores(sample["v2_scores"])
        if legacy_best != v2_best:
            direction_changes += 1
        legacy_zone = sample.get("legacy_selected_zone_id")
        v2_zone = sample.get("v2_selected_zone_id")
        if legacy_zone is not None or v2_zone is not None:
            comparable_zones += 1
            if legacy_zone == v2_zone:
                stable_zones += 1
        if v2_zone is None:
            no_zone += 1
        losing_outcome = (
            sample.get("result_r") is not None
            and sample["result_r"] <= 0
        )
        if _is_ready(sample["legacy_status"]) and losing_outcome:
            legacy_losing_ready += 1
        if _is_ready(sample["v2_status"]) and losing_outcome:
            v2_losing_ready += 1
        if (
            _is_ready(sample["legacy_status"])
            and not _is_ready(sample["v2_status"])
            and losing_outcome
        ):
            false_ready_removed += 1
        if (
            _is_ready(sample["v2_status"])
            and sample["h4_confirmed_choch_against"]
        ):
            choch_against_ready += 1

    return {
        "score_distribution": {
            "legacy": _score_distribution(samples, "legacy_scores"),
            "v2": _score_distribution(samples, "v2_scores"),
        },
        "buy_sell_gap": {
            "legacy_mean": _rounded_mean(legacy_gaps),
            "v2_mean": _rounded_mean(v2_gaps),
        },
        "selected_zone_stability": {
            "comparable_count": comparable_zones,
            "stable_count": stable_zones,
            "stable_rate": (
                round(stable_zones / comparable_zones, 4)
                if comparable_zones
                else None
            ),
        },
        "status_transitions": dict(sorted(transitions.items())),
        "direction_changed_count": direction_changes,
        # Compatibility alias: the unresolved false-ready count under v2.
        "false_ready_count": v2_losing_ready,
        "legacy_losing_ready_count": legacy_losing_ready,
        "v2_losing_ready_count": v2_losing_ready,
        "false_ready_removed_count": false_ready_removed,
        "no_zone_count": no_zone,
        "choch_against_ready_count": choch_against_ready,
    }


def _oos_comparison(
    samples: list[dict[str, Any]],
    *,
    tolerance_r: float,
) -> dict[str, Any]:
    oos = [
        sample
        for sample in samples
        if sample["dataset_split"] == "oos"
    ]
    legacy_ready = [
        sample for sample in oos if _is_ready(sample["legacy_status"])
    ]
    v2_ready = [
        sample for sample in oos if _is_ready(sample["v2_status"])
    ]
    legacy = _outcome_metrics(legacy_ready)
    v2 = _outcome_metrics(v2_ready)
    degradation = None
    if legacy["expectancy_r"] is not None and v2["expectancy_r"] is not None:
        degradation = round(
            legacy["expectancy_r"] - v2["expectancy_r"],
            4,
        )
    return {
        "oos_sample_count": len(oos),
        "legacy_ready_sample_size": legacy["sample_size"],
        "v2_ready_sample_size": v2["sample_size"],
        "legacy": legacy,
        "v2": v2,
        "degradation_r": degradation,
        "tolerance_r": round(tolerance_r, 4),
        "degradation_exceeded": (
            degradation is not None and degradation > tolerance_r
        ),
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
        if window is not None and _is_ready(sample["v2_status"]):
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
            and _is_ready(sample["v2_status"])
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
        score = sample["v2_scores"][sample["side"]]
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
        "legacy_scoring_version",
        "v2_scoring_version",
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
    prefix: str,
) -> dict[str, float]:
    source = _mapping(value)
    result: dict[str, float] = {}
    for side in _SIDES:
        score = _optional_bounded(source.get(side), 0, 15)
        if score is None:
            reasons.append(f"{prefix}_{side.upper()}_SCORE_INVALID")
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


def _safe_score(value: object) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, min(100, number))


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
