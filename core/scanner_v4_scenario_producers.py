"""Scanner V4 live scenario-plan producers.

Builds at most ONE ``ScenarioPlan`` per side from the REAL live analysis inputs
(technical price/ATR + zones).  Discipline: every number comes from real data;
anything missing or invalid fails closed to ``None`` (never invented).

There is deliberately NO pure-ATR synthetic plan: V3's only structure-free
branch was tagged display-only / ``ready_to_trade: False`` /
``"non-smc-display-v1"`` (core/analysis_pipeline.py fallback) and must never
count as tradable evidence, so a side without a real protective zone + a real
opposite target simply has no plan (gate fails closed to WATCH/UNKNOWN).

Numeric provenance (V3's own factors, not invented here):
- SL buffer beyond the protective-zone edge: ``atr * 1.0``
  (core/analysis_pipeline.py:1955).
- TP: nearest opposite-side zone level beyond the entry
  (core/analysis_pipeline.py:1957-1964).

Entry is anchored on the protective zone itself (the zone edge the stop-loss
buffer is measured from), reproducing V3's construction
(``core/analysis_pipeline.py`` "distant-zone" branch) so the risk is exactly the
1.0 * ATR stop buffer and the take-profit is the nearest opposite-side zone
level beyond the protective zone's far edge.  ``ScenarioPlan`` ordering is
validated BEFORE construction so an invalid shape returns ``None`` instead of
raising.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from core.scanner_v4_composition import CompositionInputError, ScenarioPlan
from core.smc_consumer_contract import (
    build_smc_consumer_from_canonical_result,
    selected_zone_for_side,
)

_VALID_SIDES = ("buy", "sell")

# Source tags recorded on the plan for observability (never scored).
_SOURCE_CANONICAL = "smc_canonical_zone_v4"
_SOURCE_TECHNICAL = "technical_zone_v4"


def produce_scenario_plans(
    technical: dict[str, Any] | None,
    canonical_smc: object | None,
) -> dict[str, ScenarioPlan | None]:
    """Produce the per-side scenario plan (or None) from live analysis inputs.

    ``technical`` is the ``build_technical_snapshot`` mapping (price/ATR/zones);
    ``canonical_smc`` is the canonical ``SmcScoringResult`` whose per-side
    selected zone is preferred as the protective zone.  Any unreadable input
    fails closed to ``None`` for that side.
    """
    return produce_scenario_plans_from_zones(
        technical, _canonical_zones_by_side(canonical_smc)
    )


def produce_scenario_plans_from_zones(
    technical: dict[str, Any] | None,
    zones_by_side: dict[str, dict[str, Any] | None] | None,
) -> dict[str, ScenarioPlan | None]:
    """Seam over :func:`produce_scenario_plans` with the per-side protective
    (canonical selected) zone supplied directly — keeps the geometry unit
    testable without constructing a full canonical SMC result."""
    tech = technical if isinstance(technical, dict) else {}
    zones = zones_by_side if isinstance(zones_by_side, dict) else {}
    return {
        side: _produce_for_side(side, tech, zones.get(side))
        for side in _VALID_SIDES
    }


def _produce_for_side(
    side: str,
    technical: dict[str, Any],
    canonical_zone: dict[str, Any] | None,
) -> ScenarioPlan | None:
    price = _finite_positive(technical.get("price"))
    atr = _finite_positive(technical.get("atr_h4")) or _finite_positive(
        technical.get("atr_d1")
    )
    if price is None or atr is None:
        return None

    zone, zone_source = _protective_zone(side, price, technical, canonical_zone)
    if zone is None:
        return None
    zone_low = _as_float(zone.get("low"))
    zone_high = _as_float(zone.get("high"))
    if zone_low is None or zone_high is None:
        return None

    # V3-aligned construction: anchor the entry AT the protective zone (the edge
    # the stop buffer is measured from) so the 1.0 * ATR buffer IS the risk, and
    # take profit at the nearest opposite-side zone level beyond the protective
    # zone's far edge — matching core/analysis_pipeline.py's "distant-zone"
    # branch (SL = edge +/- atr * 1.0; TP beyond the far edge).  This keeps the
    # risk and reward on a single, consistent reference (the zone) instead of
    # mixing a market entry with a zone-anchored stop.
    if side == "buy":
        entry = zone_low
        stop_loss = zone_low - atr
        take_profit = _nearest_opposite_level(
            technical.get("resistance_zones"), above=zone_high
        )
    else:
        entry = zone_high
        stop_loss = zone_high + atr
        take_profit = _nearest_opposite_level(
            technical.get("support_zones"), below=zone_low
        )
    if take_profit is None:
        return None

    if side == "buy" and not (stop_loss < entry < take_profit):
        return None
    if side == "sell" and not (take_profit < entry < stop_loss):
        return None

    try:
        return ScenarioPlan(
            direction=side,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source=zone_source,
        )
    except CompositionInputError:
        # Defensive: ordering/positivity already checked; never raise into the
        # scan.  Fail closed instead.
        return None


def _protective_zone(
    side: str,
    price: float,
    technical: dict[str, Any],
    canonical_zone: dict[str, Any] | None,
) -> tuple[dict[str, Any] | None, str]:
    """Choose the protective zone: canonical selection first, then the nearest
    same-side technical zone; ``source`` documents which one was used."""
    if _zone_on_protective_side(side, price, canonical_zone):
        return canonical_zone, _SOURCE_CANONICAL
    if side == "buy":
        zones = technical.get("support_zones")
    else:
        zones = technical.get("resistance_zones")
    candidates = [
        zone
        for zone in (zones if isinstance(zones, list) else [])
        if _zone_on_protective_side(side, price, zone)
    ]
    if not candidates:
        return None, ""
    best = min(
        candidates,
        key=lambda zone: abs((_as_float(zone.get("level")) or 0.0) - price),
    )
    return best, _SOURCE_TECHNICAL


def _zone_on_protective_side(
    side: str, price: float, zone: dict[str, Any] | None
) -> bool:
    if not isinstance(zone, dict):
        return False
    level = _as_float(zone.get("level"))
    if level is None:
        return False
    if zone.get("low") is None or _as_float(zone.get("low")) is None:
        return False
    if zone.get("high") is None or _as_float(zone.get("high")) is None:
        return False
    # A protective zone must sit on the protective side of the market-anchored
    # entry so the resulting stop is on the correct side.
    if side == "buy":
        return level <= price
    return level >= price


def _nearest_opposite_level(
    zones: object, *, above: float | None = None, below: float | None = None
) -> float | None:
    """Nearest opposite-side zone level beyond the entry (None if absent)."""
    levels: list[float] = []
    if not isinstance(zones, list):
        return None
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        level = _as_float(zone.get("level"))
        if level is None:
            continue
        if above is not None and level > above:
            levels.append(level)
        elif below is not None and level < below:
            levels.append(level)
    if not levels:
        return None
    return min(levels) if above is not None else max(levels)


def _canonical_zones_by_side(
    canonical_smc: object | None,
) -> dict[str, dict[str, Any] | None]:
    """Per-side canonical selected zone; malformed result fails closed to {}."""
    try:
        contract = build_smc_consumer_from_canonical_result(result=canonical_smc)
    except Exception:
        return {}
    zones: dict[str, dict[str, Any] | None] = {}
    for side in _VALID_SIDES:
        zones[side] = selected_zone_for_side(contract, side)
    return zones


def _as_float(value: object) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(result):
        return None
    return result


def _finite_positive(value: object) -> float | None:
    result = _as_float(value)
    if result is None or result <= 0:
        return None
    return result


__all__ = ["produce_scenario_plans", "produce_scenario_plans_from_zones"]
