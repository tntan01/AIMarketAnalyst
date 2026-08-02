"""Auditable, fail-open decisions for Scanner SMC fast paths.

This module deliberately has no routing side effects.  The pipeline will
consume its Tier-1 decision in a later implementation step; keeping the
predicate isolated makes the canonical-selection parity testable first.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from core.smc_scorer import score_smc


SMC_PREFILTER_VERSION = "smc-prefilter-v1"
SCANNER_FAST_PATH_VERSION = "scanner-fast-path-v1"

STAGE_PRE_SMC = "pre_smc"
STAGE_POST_CONTEXT = "post_context"

NO_RAW_SMC_CANDIDATE = "NO_RAW_SMC_CANDIDATE"
NO_ACTIONABLE_SMC_ZONE = "NO_ACTIONABLE_SMC_ZONE"
SMC_PREFILTER_ERROR_FAIL_OPEN = "SMC_PREFILTER_ERROR_FAIL_OPEN"
SMC_SCORING_ERROR = "SMC_SCORING_ERROR"

_TIMEFRAMES = ("H4", "H1")
_RAW_FAMILIES = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}


def evaluate_post_context_prefilter(
    *,
    smc: dict[str, Any] | None,
    technical: dict[str, Any] | None,
    market_regime: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the canonical Tier-1 decision without changing the pipeline.

    A reject is allowed only after the same :func:`score_smc` used by the full
    route has selected neither BUY nor SELL zone.  Every schema, numeric, or
    scorer problem fails open so the caller can run the existing full path
    instead.
    """

    decision = _base_decision(raw_counts=_raw_counts(smc))
    # Missing/insufficient data is a legitimate no-score case, never a scorer
    # error: fail open so the full route can run its own safe no-zone path.
    if not _is_evaluable_context(smc, technical, market_regime):
        return _fail_open(decision)

    assert isinstance(smc, dict)
    assert isinstance(technical, dict)
    try:
        smc_result = score_smc(smc, technical, market_regime)
        selected_zone_ids = _selected_zone_ids(smc_result)
    except Exception:
        # A scorer exception is fail-closed: block the analysis instead of
        # retrying the full route or falling back to another scorer.
        decision["should_reject"] = True
        decision["reason_code"] = SMC_SCORING_ERROR
        decision["fail_open"] = False
        decision["scorer_error"] = True
        return decision

    decision["precomputed_smc"] = smc_result
    decision["selected_zone_ids"] = selected_zone_ids
    if all(selected_zone_ids[side] is None for side in ("buy", "sell")):
        decision["should_reject"] = True
        decision["reason_code"] = NO_ACTIONABLE_SMC_ZONE
    return decision


def _base_decision(
    *,
    raw_counts: dict[str, dict[str, int]],
) -> dict[str, Any]:
    return {
        "should_reject": False,
        "stage": STAGE_POST_CONTEXT,
        "reason_code": "",
        "prefilter_version": SMC_PREFILTER_VERSION,
        "fast_path_version": SCANNER_FAST_PATH_VERSION,
        "raw_counts": raw_counts,
        "selected_zone_ids": {"buy": None, "sell": None},
        "fail_open": False,
        # The full route reuses this payload instead of invoking the canonical
        # scorer a second time for symbols that remain on the full route.
        "precomputed_smc": None,
    }


def _fail_open(decision: dict[str, Any]) -> dict[str, Any]:
    decision["fail_open"] = True
    decision["reason_code"] = SMC_PREFILTER_ERROR_FAIL_OPEN
    return decision


def _raw_counts(smc: dict[str, Any] | None) -> dict[str, dict[str, int]]:
    source = smc if isinstance(smc, dict) else {}
    counts: dict[str, dict[str, int]] = {}
    for timeframe in _TIMEFRAMES:
        timeframe_data = source.get(timeframe)
        timeframe_data = timeframe_data if isinstance(timeframe_data, dict) else {}
        counts[timeframe] = {
            family: len(timeframe_data.get(key, []))
            if isinstance(timeframe_data.get(key, []), list)
            else 0
            for family, key in _RAW_FAMILIES.items()
        }
    return counts


def _is_evaluable_context(
    smc: dict[str, Any] | None,
    technical: dict[str, Any] | None,
    market_regime: dict[str, Any] | None,
) -> bool:
    if not isinstance(smc, dict) or not isinstance(technical, dict):
        return False
    if market_regime is not None and not isinstance(market_regime, dict):
        return False
    if not _is_positive_finite(technical.get("price")):
        return False
    # Match the scorer's canonical H4-then-D1 ATR fallback exactly.
    atr_value = technical.get("atr_h4") or technical.get("atr_d1")
    if not _is_positive_finite(atr_value):
        return False
    for timeframe in _TIMEFRAMES:
        timeframe_data = smc.get(timeframe)
        if not isinstance(timeframe_data, dict):
            return False
        for key in _RAW_FAMILIES.values():
            zones = timeframe_data.get(key, [])
            if not isinstance(zones, list) or any(
                not isinstance(zone, dict) for zone in zones
            ):
                return False
    return True


def _is_positive_finite(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return isfinite(number) and number > 0


def _selected_zone_ids(v2_result: object) -> dict[str, str | None]:
    if not isinstance(v2_result, dict):
        raise TypeError("SMC v2 result must be a dictionary")
    selected: dict[str, str | None] = {}
    for side in ("buy", "sell"):
        snapshot = v2_result.get(side)
        if not isinstance(snapshot, dict):
            raise TypeError(f"SMC v2 {side} result must be a dictionary")
        zone_id = snapshot.get("selected_zone_id")
        if zone_id is not None and not isinstance(zone_id, str):
            raise TypeError(f"SMC v2 {side} selected zone ID must be text")
        selected[side] = zone_id
    return selected
