"""Shared versioned SMC selection contract for downstream consumers."""

from __future__ import annotations

from typing import Any

from core.smc_models import SelectedSmcZone, SmcZone


SMC_CONSUMER_CONTRACT_VERSION = "smc-consumer-v1"


def build_smc_consumer_contract(
    *,
    smc: dict[str, Any] | None,
    scoring_diagnostics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Resolve exactly one active and one optional shadow zone per side."""

    context = smc if isinstance(smc, dict) else {}
    diagnostics = (
        scoring_diagnostics
        if isinstance(scoring_diagnostics, dict)
        else {}
    )
    policy = (
        diagnostics.get("policy")
        if isinstance(diagnostics.get("policy"), dict)
        else {}
    )
    active = (
        diagnostics.get("active")
        if isinstance(diagnostics.get("active"), dict)
        else {}
    )
    shadow = (
        diagnostics.get("shadow")
        if isinstance(diagnostics.get("shadow"), dict)
        else {}
    )

    sides: dict[str, dict[str, Any]] = {}
    for side in ("buy", "sell"):
        active_snapshot = (
            active.get(side)
            if isinstance(active.get(side), dict)
            else {}
        )
        active_zone = _find_selected_zone(
            context,
            side=side,
            zone_id=active_snapshot.get("selected_zone_id"),
        )
        if active_zone is not None:
            active_zone["smc_score_breakdown"] = _copy_dict(
                active_snapshot.get("breakdown")
            )

        shadow_snapshot = (
            shadow.get(side)
            if isinstance(shadow.get(side), dict)
            else {}
        )
        shadow_zone = _copy_dict(shadow_snapshot.get("selected_zone"))
        if shadow_zone:
            shadow_zone["smc_score_breakdown"] = _copy_dict(
                shadow_snapshot.get("breakdown")
            )

        # Policy chooses one decision-path zone; the other selection remains
        # available for comparison and rollback diagnostics.
        use_shadow = bool(
            policy.get("decision_impact_allowed")
            and policy.get("decision_source") == shadow_snapshot.get(
                "scoring_version"
            )
        )
        selected = shadow_zone if use_shadow else active_zone
        selected_snapshot = shadow_snapshot if use_shadow else active_snapshot
        scoring_version = (
            selected.get("scoring_version")
            if isinstance(selected, dict)
            else None
        )
        scoring_version = (
            scoring_version
            or selected_snapshot.get("scoring_version")
            or policy.get("active_version")
        )

        sides[side] = {
            "side": side,
            "selection_source": "v2" if use_shadow else "legacy",
            "scoring_version": scoring_version,
            "selected_zone": selected,
            "selected_zone_id": (
                selected.get("zone_id")
                if isinstance(selected, dict)
                else None
            ),
            "selected_zone_type": (
                selected.get("zone_type", selected.get("type"))
                if isinstance(selected, dict)
                else None
            ),
            "selected_zone_timeframe": (
                selected.get("timeframe")
                if isinstance(selected, dict)
                else None
            ),
            "selected_zone_quality_score": (
                selected.get("zone_quality_score")
                if isinstance(selected, dict)
                else None
            ),
            "selected_zone_relevance_score": (
                selected.get("zone_relevance_score")
                if isinstance(selected, dict)
                else None
            ),
            "selected_zone_setup_score": (
                selected.get("zone_setup_score")
                if isinstance(selected, dict)
                else None
            ),
            "score_breakdown": _copy_dict(
                selected_snapshot.get("breakdown")
            ),
            "shadow_selected_zone": shadow_zone,
            "shadow_selected_zone_id": (
                shadow_zone.get("zone_id") if shadow_zone else None
            ),
            "shadow_scoring_version": shadow_snapshot.get(
                "scoring_version"
            ),
        }

    return {
        "contract_version": SMC_CONSUMER_CONTRACT_VERSION,
        "decision_source": policy.get("decision_source"),
        "decision_impact_allowed": bool(
            policy.get("decision_impact_allowed")
        ),
        "sides": sides,
    }


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


def _find_selected_zone(
    smc: dict[str, Any],
    *,
    side: str,
    zone_id: object,
) -> dict[str, Any] | None:
    target = str(zone_id or "").strip()
    if not target:
        return None
    symbol = str(smc.get("symbol", "") or "")
    for timeframe in ("H4", "H1"):
        timeframe_data = smc.get(timeframe)
        if not isinstance(timeframe_data, dict):
            continue
        for family in ("demand_zones", "supply_zones", "order_blocks", "fvg"):
            values = timeframe_data.get(family)
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, dict):
                    continue
                if str(value.get("zone_id", "") or "") != target:
                    continue
                try:
                    zone = SmcZone.from_legacy_dict(
                        value,
                        symbol=symbol,
                        timeframe=timeframe,
                        family={
                            "demand_zones": "demand",
                            "supply_zones": "supply",
                            "order_blocks": "order_block",
                            "fvg": "fvg",
                        }[family],
                        direction=side,
                    )
                    return SelectedSmcZone.from_zone(
                        zone,
                        source="smc_active_selected",
                    ).to_dict(include_compatibility=True)
                except (TypeError, ValueError):
                    return None
    return None


def _copy_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}
