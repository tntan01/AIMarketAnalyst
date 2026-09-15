"""Shared versioned SMC selection contract for downstream consumers."""

from __future__ import annotations

from math import isfinite
from typing import Any

from core.smc_scoring_result import (
    SELECTION_STATE_EVALUATED,
    SmcScoringResult,
    smc_selection_of,
    validate_smc_result,
    validate_smc_selection_result,
)


SMC_CONSUMER_CONTRACT_VERSION = "smc-consumer-v2"

# R114-01: the Analyze scenario builder consumes the risk-plan "preferred zone"
# shape (see ``core.risk_engine.build_trade_plan``).  The canonical FINAL
# selection is converted into that shape here, at the consumer boundary, so the
# scenario reads the SAME candidate the coordinator accepted.
#
# This is a READER: it copies the selected zone/setup identity, the selected band
# and the plan reference of that same candidate.  It never looks for another
# zone and never recomputes quality/B-Q-L-C, geometry, confirmation, lifecycle,
# score or the plan itself.
SELECTED_ZONE_SOURCE = "smc_selected"
PREFERRED_ZONE_PROVENANCE = "smc_canonical_selection"
# The directional zone type of the selection's own side.  ``risk_engine``
# matches a preferred zone against the side through this field, and the
# canonical selection's ``family`` (fvg / order_block / supply / demand) is not
# itself a zone type a direction can be matched against.
_BUY_ZONE_TYPE = "demand_zone"
_SELL_ZONE_TYPE = "supply_zone"


def build_smc_consumer_from_canonical_result(
    *,
    result: SmcScoringResult | None,
) -> dict[str, Any]:
    """Build the decision-path consumer from one canonical scorer result.

    The canonical result already carries the selected zone for each side, so no
    shadow/legacy selection or context lookup is needed.  A malformed or
    incomplete result is rejected rather than silently producing empty sides.

    Task 107: the side payload also carries the FINAL ``selection`` — the
    selected candidate, its B/Q/L/C quality, lifecycle/confirmation evidence,
    readiness verdict and the plan reference of the SAME setup.  Consumers and
    the scenario producer read from there; the legacy ``selected_zone`` keys are
    kept only so stored/legacy payload readers keep working (removal condition:
    architecture review §9.4 lot 2E, after task 116 is APPROVED).
    """

    # A result that carries final selections is held to the FINAL invariant
    # (task 94/96), which is the owner of the canonical contract.  A stored
    # payload written before the canonical path has no selections and keeps the
    # legacy structural check, so history stays readable without weakening the
    # live path.
    if _carries_selection(result):
        if not validate_smc_selection_result(result):
            raise ValueError(
                "SMC final selection result is malformed or disagrees with its "
                "own quality/plan identity"
            )
    elif not validate_smc_result(result):
        raise ValueError("SMC scoring result is malformed or missing a side")

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
        selection = smc_selection_of(side_result)
        contract["sides"][side] = {
            "side": side,
            "scoring_version": (
                result.scoring_version
                if isinstance(result, SmcScoringResult)
                else None
            ),
            "selection": (
                selection.to_dict() if selection is not None else None
            ),
            "readiness": (
                dict(selection.readiness)
                if selection is not None and isinstance(selection.readiness, dict)
                else None
            ),
            "plan": (
                dict(selection.plan)
                if selection is not None and isinstance(selection.plan, dict)
                else None
            ),
            "plan_available": bool(
                selection is not None and selection.plan_available
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


def _carries_selection(result: SmcScoringResult | None) -> bool:
    if not isinstance(result, SmcScoringResult):
        return False
    return any(
        smc_selection_of(result.side(side)) is not None for side in ("buy", "sell")
    )


def selection_for_side(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """The final canonical selection payload of *side*, or ``None``.

    ``None`` means the side carries no selection at all (a legacy payload) —
    it is NOT the same as an evaluated side whose selection says ``no_zone``.
    A consumer must therefore read the state from here, never infer it from a
    missing zone.
    """

    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    return _copy_dict(item.get("selection")) or None


def selected_zone_for_side(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """Return a copy of the decision-path selected zone for *side*.

    This is the HISTORICAL zone payload (``SmcSideScoringResult.selected_zone``),
    which the canonical finalizer never fills: on a canonical contract it is
    ``None`` for every side.  A caller that needs the zone the canonical
    coordinator actually accepted reads :func:`scenario_preferred_zone_for_side`
    instead (R114-01).
    """

    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    return _copy_dict(item.get("selected_zone")) or None


def scenario_preferred_zone_for_side(
    contract: dict[str, Any] | None,
    side: str,
) -> dict[str, Any] | None:
    """The risk-plan "preferred zone" of *side*, read from the final selection.

    R114-01: the scenario builder must be driven by the canonical FINAL
    selection — the candidate the coordinator accepted — not by the legacy
    ``selected_zone`` field, which the canonical finalizer never fills.  This
    converts that selection into the zone shape ``build_trade_plan`` already
    consumes (``low``/``high``/``level``/``zone_type``/``source``/``zone_id``).

    Fail-closed: a side whose selection is absent but whose payload carries a
    canonical contract (``no_zone``, ``data_unavailable``, ``watch_zone``,
    ``out_of_strategy``), or whose selection has no accepted plan, no
    consistent zone/setup identity, or an unusable band, yields ``None``.  It
    never falls back to another zone — technical or legacy.

    A stored/legacy payload that carries NO canonical selection at all keeps its
    historical reader compatibility from ``selected_zone``.
    """

    payload = contract if isinstance(contract, dict) else {}
    sides = payload.get("sides") if isinstance(payload.get("sides"), dict) else {}
    item = sides.get(side) if isinstance(sides.get(side), dict) else {}
    selection = _copy_dict(item.get("selection")) or None
    if selection is None:
        # No canonical selection was ever written for this side: the payload is
        # a stored/legacy document, so the old reader stays in force.
        return _copy_dict(item.get("selected_zone")) or None
    return _preferred_zone_from_selection(selection)


def _preferred_zone_from_selection(
    selection: dict[str, Any],
) -> dict[str, Any] | None:
    """Convert one FINAL selection into the risk-plan zone shape, or ``None``.

    Only an ``evaluated`` selection with an accepted plan belonging to the SAME
    candidate can become a preferred zone.  Every value is copied from the
    selection/plan; ``level`` is the midpoint of the selection's own band, which
    is the same convention the retired ``SelectedSmcZone.from_zone`` used.
    """

    if selection.get("state") != SELECTION_STATE_EVALUATED:
        return None
    if selection.get("plan_available") is not True:
        return None
    plan = selection.get("plan")
    if not isinstance(plan, dict):
        return None

    side = str(selection.get("side") or "").strip().lower()
    zone_id = selection.get("selected_zone_id")
    setup_id = selection.get("selected_setup_id")
    if side not in ("buy", "sell") or not zone_id or not setup_id:
        return None
    # The plan must belong to the selected zone/setup: a mismatched pair is a
    # malformed selection, never a usable preferred zone.  Both the plan payload
    # and the selection's own plan reference are checked, so a selection that
    # names one zone in its plan and another in its reference is refused.
    if plan.get("zone_id") != zone_id or plan.get("setup_id") != setup_id:
        return None
    plan_zone_id = selection.get("plan_zone_id")
    if plan_zone_id is not None and plan_zone_id != zone_id:
        return None
    plan_setup_id = selection.get("plan_setup_id")
    if plan_setup_id is not None and plan_setup_id != setup_id:
        return None
    plan_direction = plan.get("direction")
    if plan_direction is not None and plan_direction != side:
        return None

    low = _finite_price(selection.get("zone_low"))
    high = _finite_price(selection.get("zone_high"))
    if low is None or high is None or high <= low:
        return None

    return {
        "zone_id": zone_id,
        "setup_id": setup_id,
        "direction": side,
        "side": side,
        "zone_type": _BUY_ZONE_TYPE if side == "buy" else _SELL_ZONE_TYPE,
        "type": _BUY_ZONE_TYPE if side == "buy" else _SELL_ZONE_TYPE,
        "family": selection.get("family"),
        "timeframe": selection.get("timeframe"),
        "low": low,
        "high": high,
        # Band midpoint, matching the retired ``SelectedSmcZone.from_zone``.
        "level": (low + high) / 2.0,
        "source": SELECTED_ZONE_SOURCE,
        "selection_status": selection.get("state"),
        "selection_reason_codes": list(selection.get("selection_reason_codes") or ()),
        "provenance": PREFERRED_ZONE_PROVENANCE,
        "plan_zone_id": selection.get("plan_zone_id"),
        "plan_setup_id": selection.get("plan_setup_id"),
    }


def _finite_price(value: object) -> float | None:
    """A real price level, or ``None`` — a boolean must not stand in for one."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if isfinite(number) else None


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
