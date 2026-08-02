"""Shared versioned SMC selection contract for downstream consumers."""

from __future__ import annotations

from typing import Any


SMC_CONSUMER_CONTRACT_VERSION = "smc-consumer-v2"


def build_smc_consumer_from_canonical_result(
    *,
    result: dict[str, dict[str, Any]] | None,
) -> dict[str, Any]:
    """Build the decision-path consumer from one canonical scorer result.

    The canonical result already carries the selected zone for each side, so no
    shadow/legacy selection or context lookup is needed.
    """

    sides = result if isinstance(result, dict) else {}
    contract: dict[str, Any] = {
        "contract_version": SMC_CONSUMER_CONTRACT_VERSION,
        "sides": {},
    }
    for side in ("buy", "sell"):
        side_result = (
            sides.get(side)
            if isinstance(sides.get(side), dict)
            else {}
        )
        contract["sides"][side] = {
            "side": side,
            "scoring_version": side_result.get("scoring_version"),
            "selected_zone": side_result.get("selected_zone"),
            "selected_zone_id": side_result.get("selected_zone_id"),
            "selected_zone_type": side_result.get("selected_zone_type"),
            "selected_zone_timeframe": side_result.get(
                "selected_zone_timeframe"
            ),
            "selected_zone_quality_score": side_result.get(
                "selected_zone_quality_score"
            ),
            "selected_zone_relevance_score": side_result.get(
                "selected_zone_relevance_score"
            ),
            "selected_zone_setup_score": side_result.get(
                "selected_zone_setup_score"
            ),
            "score_breakdown": side_result.get("breakdown"),
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
