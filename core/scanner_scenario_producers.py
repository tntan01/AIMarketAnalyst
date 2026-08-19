"""Scanner live scenario-plan producers.

Builds at most ONE ``ScenarioPlan`` per side from the REAL live analysis inputs
(technical price/ATR + zones).  Discipline: every number comes from real data;
anything missing or invalid fails closed to ``None`` (never invented).

There is deliberately NO pure-ATR synthetic plan: the legacy's only structure-free
branch was tagged display-only / ``ready_to_trade: False`` /
``"non-smc-display-v1"`` (core/analysis_pipeline.py fallback) and must never
count as tradable evidence, so a side without a real protective zone + a real
opposite target simply has no plan (gate fails closed to WATCH/UNKNOWN).

Numeric provenance (the legacy factors, not invented here):
- SL buffer beyond the protective-zone edge: ``atr * 1.0``
  (core/analysis_pipeline.py "distant-zone" branch, SL at ~line 1563).
- TP: nearest opposite-side zone level beyond the protective zone's far edge
  (core/analysis_pipeline.py:1565-1572).

Entry is anchored on the protective zone's own edge (``zone_low`` for buy /
``zone_high`` for sell) — the same model for a canonical SMC zone and a
technical fallback zone, reproducing the legacy "distant-zone" branch — so the
risk is exactly the 1.0 * ATR stop buffer and the take-profit is the nearest
opposite-side zone level beyond the far edge.  The quoted R:R is the exact
pre-spread geometric ratio (``compute_scenario_rr``); per-symbol spread is
enforced separately by the market-safety gate on its 28-pair point map, not by
this producer.

A protective zone whose NEAREST edge is more than 3.0 ATR from the current
price is a distant watch, never a tradable plan (fail-closed to ``None``) — the
same hard distance the SMC scorer enforces (``ZONE_BEYOND_HARD_DISTANCE``).

``ScenarioPlan`` ordering is validated BEFORE construction so an invalid shape
returns ``None`` instead of raising.
"""

from __future__ import annotations

from fractions import Fraction
from math import isfinite
from typing import Any

from core.scanner_composition import (
    CompositionInputError,
    ScenarioPlan,
    compute_scenario_rr,
)
from core.smc_consumer_contract import (
    build_smc_consumer_from_canonical_result,
    selected_zone_for_side,
)

_VALID_SIDES = ("buy", "sell")

# Source tags recorded on the plan for observability (never scored).
_SOURCE_CANONICAL = "smc_canonical_zone"
_SOURCE_TECHNICAL = "technical_zone"

# A protective zone whose NEAREST edge is more than this far (in ATR) from the
# current price is a distant watch, never a tradable plan — the same hard
# distance the SMC scorer enforces (ZONE_BEYOND_HARD_DISTANCE).  This closes
# the "entry far from the market" gap that a pure zone-anchored construction
# would otherwise leave open.
_MAX_PROTECTIVE_ZONE_DISTANCE_ATR = 3.0

# A protective zone whose WIDTH (high - low) exceeds this multiple of ATR
# is too diffuse to anchor a tight entry.  A wide zone makes the entry band
# visually large on the chart and pushes the nearest opposite-side TP too close
# to the zone's far edge, producing a poor R:R even when the stop is tight.
_MAX_ZONE_WIDTH_ATR = 1.0

# Minimum geometric R:R for a produced scenario plan.  This is the fallback
# when no ``min_rr`` is supplied by the caller (i.e. no order-policy threshold
# is wired).  Scenarios below this threshold are rejected regardless of the
# gate's min_risk_reward — the chart would otherwise show a wide zone with a
# needle-thin TP distance.  The caller SHOULD pass the owner-configurable
# ``min_risk_reward`` from the run-time order policy; this constant exists only
# as a safety net for callers that haven't been updated yet.
_MIN_SCENARIO_RR = Fraction(3, 2)  # 1.5


def produce_scenario_plans(
    technical: dict[str, Any] | None,
    canonical_smc: object | None,
    min_rr: Fraction | None = None,
) -> dict[str, ScenarioPlan | None]:
    """Produce the per-side scenario plan (or None) from live analysis inputs.

    ``technical`` is the ``build_technical_snapshot`` mapping (price/ATR/zones);
    ``canonical_smc`` is the canonical ``SmcScoringResult`` whose per-side
    selected zone is preferred as the protective zone.  Any unreadable input
    fails closed to ``None`` for that side.

    ``min_rr`` is the minimum R:R from the run-time order policy threshold
    (``ComposeOptions.min_risk_reward``).  When ``None`` (no policy or caller
    hasn't wired it), the producer uses its own hard-coded floor
    (``_MIN_SCENARIO_RR = 1.5``) so no plan with a needle-thin TP distance
    reaches the chart.
    """
    return produce_scenario_plans_from_zones(
        technical, _canonical_zones_by_side(canonical_smc), min_rr=min_rr
    )


def produce_scenario_plans_from_zones(
    technical: dict[str, Any] | None,
    zones_by_side: dict[str, dict[str, Any] | None] | None,
    min_rr: Fraction | None = None,
) -> dict[str, ScenarioPlan | None]:
    """Seam over :func:`produce_scenario_plans` with the per-side protective
    (canonical selected) zone supplied directly — keeps the geometry unit
    testable without constructing a full canonical SMC result."""
    tech = technical if isinstance(technical, dict) else {}
    zones = zones_by_side if isinstance(zones_by_side, dict) else {}
    return {
        side: _produce_for_side(side, tech, zones.get(side), min_rr=min_rr)
        for side in _VALID_SIDES
    }


def _produce_for_side(
    side: str,
    technical: dict[str, Any],
    canonical_zone: dict[str, Any] | None,
    min_rr: Fraction | None = None,
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
    if zone_low > zone_high:
        return None

    # Zone width gate: a protective zone whose band is too wide (in ATR) is too
    # diffuse to anchor a tight entry.  A wide zone makes the entry rectangle
    # visually large on the chart and pushes the nearest opposite-side TP too
    # close to the zone's far edge.
    if (zone_high - zone_low) / atr > _MAX_ZONE_WIDTH_ATR:
        return None

    # Price-proximity gate: a protective zone whose NEAREST edge is more than
    # ``_MAX_PROTECTIVE_ZONE_DISTANCE_ATR`` ATR from the current price is a
    # distant watch, never a tradable plan — reusing the SMC scorer's hard
    # distance (``ZONE_BEYOND_HARD_DISTANCE``).  Without this, a zone-anchored
    # Entry far below/above the market could still PASS the geometric R:R gate.
    if _distance_to_zone(price, zone_low, zone_high) / atr > _MAX_PROTECTIVE_ZONE_DISTANCE_ATR:
        return None

    # Legacy-aligned construction: anchor the entry AT the protective zone (the edge
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

    # Minimum R:R gate: reject scenarios with poor geometric ratio before
    # constructing the plan — the chart would otherwise render a wide zone
    # with a needle-thin TP distance.  The threshold comes from the caller's
    # ``min_rr`` parameter (owner-configurable, typically from the order-policy
    # ``min_risk_reward``), with a hard-coded fallback of 1.5 so no plan with a
    # needle-thin TP distance reaches the chart even when the caller hasn't
    # wired the policy yet.
    plan_rr = compute_scenario_rr(
        ScenarioPlan(
            direction=side,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source=zone_source,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
        ),
        side,
    )
    if plan_rr is None or plan_rr < (min_rr if min_rr is not None else _MIN_SCENARIO_RR):
        return None

    try:
        return ScenarioPlan(
            direction=side,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source=zone_source,
            # The REAL protective-zone band the entry is anchored to, so the UI can
            # draw the entry as the true zone rectangle (not a synthetic level).
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
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
    # A protective zone must carry a level (well-formedness; the technical
    # branch sorts candidates by level distance).
    if _as_float(zone.get("level")) is None:
        return False
    low = _as_float(zone.get("low"))
    high = _as_float(zone.get("high"))
    if low is None or high is None or low > high:
        return False
    # Test on the zone's band edges, not the midpoint level, so a zone whose
    # price sits in the upper band is still protective — matching the SMC
    # scorer's own side test (low <= price for buy, high >= price for sell).
    if side == "buy":
        return low <= price
    return high >= price


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


def _distance_to_zone(price: float, low: float, high: float) -> float:
    """Distance from price to the NEAREST zone edge (0 when inside the zone)."""
    if price < low:
        return low - price
    if price > high:
        return price - high
    return 0.0


def _finite_positive(value: object) -> float | None:
    result = _as_float(value)
    if result is None or result <= 0:
        return None
    return result


__all__ = ["produce_scenario_plans", "produce_scenario_plans_from_zones"]
