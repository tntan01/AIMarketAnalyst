"""Shared versioned SMC selection contract for downstream consumers."""

from __future__ import annotations

from typing import Any

from core.smc_scoring_result import SmcScoringResult


SMC_CONSUMER_CONTRACT_VERSION = "smc-consumer-v2"


def build_smc_consumer_from_canonical_result(
    *,
    result: SmcScoringResult | None,
) -> dict[str, Any]:
    """Build the decision-path consumer from one canonical scorer result.

    The canonical result already carries the selected zone for each side, so no
    shadow/legacy selection or context lookup is needed.
    """

    contract: dict[str, Any] = {
        "contract_version": SMC_CONSUMER_CONTRACT_VERSION,
        "sides": {},
    }
    for side in ("buy", "sell"):
        side_result = (
            result.side(side)
            if isinstance(result, SmcScoringResult)
            else None
        )
        contract["sides"][side] = {
            "side": side,
            "scoring_version": (
                result.scoring_version
                if isinstance(result, SmcScoringResult)
                else None
            ),
            "selected_zone": (
                side_result.selected_zone if side_result is not None else None
            ),
            "selected_zone_id": (
                side_result.selected_zone_id
                if side_result is not None
                else None
            ),
            "selected_zone_type": (
                side_result.selected_zone_type
                if side_result is not None
                else None
            ),
            "selected_zone_timeframe": (
                side_result.selected_zone_timeframe
                if side_result is not None
                else None
            ),
            "selected_zone_quality_score": (
                side_result.selected_zone_quality_score
                if side_result is not None
                else None
            ),
            "selected_zone_relevance_score": (
                side_result.selected_zone_relevance_score
                if side_result is not None
                else None
            ),
            "selected_zone_setup_score": (
                side_result.selected_zone_setup_score
                if side_result is not None
                else None
            ),
            "score_breakdown": (
                side_result.breakdown if side_result is not None else {}
            ),
        }
    return contract


def selected_zone_for_side(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """Return a copy of the decision-path selected zone for *side*."""

    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    return _copy_dict(item.get("selected_zone")) or None


def side_consumer_metadata(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any]:
    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    return dict(item)


def _copy_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
