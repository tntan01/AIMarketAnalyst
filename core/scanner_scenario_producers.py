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

from core.smc_geometry import (
    CANONICAL_PROVENANCE_FIELDS,
    GEOMETRY_FORMATION_ATR_UNAVAILABLE,
    HARD_DISTANCE_ATR,
    MAX_ZONE_WIDTH_ATR,
    distance_to_zone as _shared_distance_to_zone,
    has_canonical_provenance,
    pre_plan_geometry_gate,
)

from dataclasses import dataclass
from fractions import Fraction
from math import isfinite
from typing import Any, Mapping

from core.scanner_composition import (
    CompositionInputError,
    ScenarioPlan,
    compute_scenario_rr,
)
from core.smc_consumer_contract import (
    build_smc_consumer_from_canonical_result,
    selected_zone_for_side,
)
from core.smc_models import CandidateEvaluation

_VALID_SIDES = ("buy", "sell")

# Source tags recorded on the plan for observability (never scored).
_SOURCE_CANONICAL = "smc_canonical_zone"
_SOURCE_TECHNICAL = "technical_zone"

# Plan-attempt rejection codes owned by this seam (selection spec §5/§6).  They
# are the reason a candidate produced no plan; they never change its quality.
PLAN_POLICY_UNAVAILABLE = "PLAN_POLICY_UNAVAILABLE"
PLAN_SNAPSHOT_UNAVAILABLE = "PLAN_SNAPSHOT_UNAVAILABLE"
PLAN_ZONE_UNAVAILABLE = "PLAN_ZONE_UNAVAILABLE"
PLAN_CANDIDATE_EVIDENCE_MISSING = "PLAN_CANDIDATE_EVIDENCE_MISSING"
PLAN_TP_MISSING = "PLAN_TP_MISSING"
PLAN_SHAPE_INVALID = "PLAN_SHAPE_INVALID"
PLAN_MIN_RR = "PLAN_MIN_RR"

# A protective zone whose NEAREST edge is more than this far (in ATR) from the
# current price is a distant watch, never a tradable plan — the same hard
# distance the SMC scorer enforces (ZONE_BEYOND_HARD_DISTANCE).  This closes
# the "entry far from the market" gap that a pure zone-anchored construction
# would otherwise leave open.
_MAX_PROTECTIVE_ZONE_DISTANCE_ATR = HARD_DISTANCE_ATR

# A protective zone whose WIDTH (high - low) exceeds this multiple of ATR
# is too diffuse to anchor a tight entry.  A wide zone makes the entry band
# visually large on the chart and pushes the nearest opposite-side TP too close
# to the zone's far edge, producing a poor R:R even when the stop is tight.
_MAX_ZONE_WIDTH_ATR = MAX_ZONE_WIDTH_ATR


@dataclass(frozen=True, slots=True)
class PlanAttempt:
    """Result of planning ONE candidate (selection spec §5, task 92).

    ``plan_available`` is the only thing the coordinator may branch on; when it
    is false the attempt keeps the reasons so the trace can explain why the
    candidate was skipped and the next one tried.  The seam is pure: it reads
    the candidate, the frozen technical context and the caller's policy, never
    a canonical result, and never calls the scorer.

    ``candidate_id``/``zone_id``/``setup_id`` are the identity of the candidate
    the plan was actually built for.  R100-01: the coordinator must compare them
    with the candidate it is currently trying, so a plan that belongs to another
    zone/setup can never be attached to the selected one.
    """

    candidate_id: str | None
    zone_id: str | None
    plan: ScenarioPlan | None = None
    plan_available: bool = False
    rejection_codes: tuple[str, ...] = ()
    setup_id: str | None = None

    def __post_init__(self) -> None:
        if self.plan_available != (self.plan is not None):
            raise ValueError("PlanAttempt.plan_available must match the plan")
        object.__setattr__(
            self,
            "rejection_codes",
            tuple(dict.fromkeys(str(code) for code in self.rejection_codes if str(code))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "zone_id": self.zone_id,
            "setup_id": self.setup_id,
            "plan_available": self.plan_available,
            "plan": plan_to_dict(
                self.plan, zone_id=self.zone_id, setup_id=self.setup_id
            ),
            "rejection_codes": list(self.rejection_codes),
        }


def plan_for_candidate(
    candidate: CandidateEvaluation,
    technical: Mapping[str, Any] | None,
    min_rr: Fraction | None = None,
    snapshot_metadata: Mapping[str, Any] | None = None,
) -> PlanAttempt:
    """Build the plan of ONE evaluated candidate without a canonical result.

    ``candidate`` is the typed evaluation the scorer produced; its
    ``plan_zone`` evidence is exactly what the shared geometry gate validated,
    so the planner and the scorer never disagree about the same bounds.  A
    candidate that carries no such evidence fails closed with
    ``PLAN_CANDIDATE_EVIDENCE_MISSING`` — it is never re-derived from the
    snapshot, which would let a rejected candidate sneak back in.

    ``min_rr`` is the run-time order-policy floor; without it the planner
    reports ``PLAN_POLICY_UNAVAILABLE`` instead of inventing a threshold.
    ``snapshot_metadata`` is accepted as the frozen snapshot descriptor
    (cutoff/symbol); the plan rule itself does not read it yet, so nothing here
    can silently vary with it.
    """

    if not isinstance(candidate, CandidateEvaluation):
        raise ValueError("plan_for_candidate requires a CandidateEvaluation")
    if snapshot_metadata is not None and not isinstance(snapshot_metadata, Mapping):
        raise ValueError("snapshot_metadata must be a mapping")

    candidate_id = candidate.candidate_id
    zone_id = candidate.zone_id or None
    zone = candidate.plan_zone
    if not isinstance(zone, dict):
        return PlanAttempt(
            candidate_id=candidate_id,
            zone_id=zone_id,
            rejection_codes=(PLAN_CANDIDATE_EVIDENCE_MISSING,),
        )
    attempt = _plan_attempt_for_zone(
        candidate.side,
        zone,
        technical,
        min_rr=min_rr,
        canonical=True,
    )
    return PlanAttempt(
        candidate_id=candidate_id,
        zone_id=zone_id,
        plan=attempt.plan,
        plan_available=attempt.plan_available,
        rejection_codes=attempt.rejection_codes,
        setup_id=candidate.setup_id,
    )


def plan_to_dict(
    plan: ScenarioPlan | None,
    *,
    zone_id: str | None = None,
    setup_id: str | None = None,
) -> dict[str, Any] | None:
    """Plain-data form of a plan so the result contract stays planner-free.

    ``zone_id``/``setup_id`` stamp WHICH candidate the plan was built for
    (R100-01), so the plan reference can be checked against the selected setup
    instead of being trusted on its own.
    """

    if plan is None:
        return None
    payload: dict[str, Any] = {
        "direction": plan.direction,
        "entry": plan.entry,
        "stop_loss": plan.stop_loss,
        "take_profit": plan.take_profit,
        "source": plan.source,
        "entry_zone_low": plan.entry_zone_low,
        "entry_zone_high": plan.entry_zone_high,
    }
    if zone_id is not None:
        payload["zone_id"] = zone_id
    if setup_id is not None:
        payload["setup_id"] = setup_id
    return payload

def produce_scenario_plans(
    technical: dict[str, Any] | None,
    canonical_smc: object | None,
    min_rr: Fraction | None = None,
) -> dict[str, ScenarioPlan | None]:
    """HISTORICAL reader — no longer on the live route (task 107).

    It is kept because stored/legacy payloads and the parity fixtures use the
    pre-107 shape: build a plan from the canonical result's *selected zone*.
    The live Scanner reads the plan of the FINAL SELECTION instead (see
    :func:`plans_from_canonical_selection`), because only the coordinator knows
    which candidate was actually accepted and with which geometry.

    ``technical`` is the ``build_technical_snapshot`` mapping (price/ATR/zones);
    ``canonical_smc`` is the canonical ``SmcScoringResult`` whose per-side
    selected zone is preferred as the protective zone.  Any unreadable input
    fails closed to ``None`` for that side.

    ``min_rr`` is the minimum R:R from the run-time order policy threshold
    (``ComposeOptions.min_risk_reward``).  When ``None`` (no certified policy),
    no plan is produced; the producer never invents an R:R floor.

    Removal condition (architecture review §9.4, lot 2E): once every caller has
    moved to the final selection and task 116 is APPROVED.
    """
    return produce_scenario_plans_from_zones(
        technical, _canonical_zones_by_side(canonical_smc), min_rr=min_rr
    )


def plans_from_canonical_selection(
    canonical_smc: object | None,
) -> dict[str, ScenarioPlan | None]:
    """Read the accepted plan of each side's FINAL selection (task 107).

    The scenario and the selected zone therefore come from one and the same
    candidate: the producer never looks for another zone, never re-runs the
    planner and never re-checks R:R — the coordinator already did that when it
    accepted the candidate.  A side without an accepted plan (watch zone,
    no-zone, core unavailable, blocked) yields ``None`` so the composition's
    scenario gate fails closed as before.
    """

    from core.smc_scoring_result import SmcScoringResult, smc_selection_of

    if type(canonical_smc) is not SmcScoringResult:
        return {side: None for side in _VALID_SIDES}
    plans: dict[str, ScenarioPlan | None] = {}
    for side in _VALID_SIDES:
        selection = smc_selection_of(canonical_smc.side(side))
        plans[side] = scenario_plan_from_payload(
            None if selection is None else selection.plan
        )
    return plans


def scenario_plan_from_payload(plan: object) -> ScenarioPlan | None:
    """Convert one canonical plan payload into a ``ScenarioPlan`` or ``None``.

    Only the plan shape is converted; the candidate/zone/setup identity the
    payload carries is validated by the final-selection invariant, not here.
    """

    if not isinstance(plan, Mapping):
        return None
    try:
        return ScenarioPlan(
            direction=plan.get("direction"),
            entry=plan.get("entry"),
            stop_loss=plan.get("stop_loss"),
            take_profit=plan.get("take_profit"),
            source=str(plan.get("source") or ""),
            entry_zone_low=plan.get("entry_zone_low"),
            entry_zone_high=plan.get("entry_zone_high"),
        )
    except (CompositionInputError, TypeError, ValueError):
        return None


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

    # One owner for the plan rule: the legacy per-side producer and the
    # candidate seam (task 92) both go through _plan_attempt_for_zone, so a
    # candidate can never be planned under different geometry than the scorer
    # validated it with.
    return _plan_attempt_for_zone(
        side,
        zone,
        technical,
        min_rr=min_rr,
        canonical=zone_source == _SOURCE_CANONICAL,
    ).plan


def _plan_attempt_for_zone(
    side: str,
    zone: dict[str, Any],
    technical: dict[str, Any] | None,
    *,
    min_rr: Fraction | None,
    canonical: bool,
) -> PlanAttempt:
    """The single plan rule: geometry gate, entry/SL/TP shape and R:R floor.

    ``canonical`` says whether the zone carries canonical formation evidence
    (candidate zone / selected canonical zone) or is the technical fallback
    zone, which by construction has no source-timeframe ATR.
    """

    tech = technical if isinstance(technical, dict) else {}
    candidate_id = _optional_text(zone.get("zone_id"))
    zone_id = candidate_id

    def _reject(*codes: str) -> PlanAttempt:
        return PlanAttempt(
            candidate_id=candidate_id,
            zone_id=zone_id,
            rejection_codes=tuple(codes),
        )

    price = _finite_positive(tech.get("price"))
    atr = _finite_positive(tech.get("atr_h4")) or _finite_positive(tech.get("atr_d1"))
    if price is None or atr is None:
        # The shared execution snapshot is unusable: the coordinator must stop
        # instead of trying the next candidate to paper over a bad snapshot.
        return _reject(PLAN_SNAPSHOT_UNAVAILABLE)

    zone_low = _as_float(zone.get("low"))
    zone_high = _as_float(zone.get("high"))
    if zone_low is None or zone_high is None or zone_low > zone_high:
        return _reject(PLAN_ZONE_UNAVAILABLE)

    # Shared SMC pre-plan geometry gate (task 89, R80-91-02): the planner and
    # the scorer must reject the same candidate, so both evaluate the SAME
    # protective bounds and the SAME ATR references.  Per parameter table P11
    # the width/family geometry uses the zone's own FORMATION ATR (source
    # timeframe) while the hard distance uses the frozen-snapshot EXECUTION ATR;
    # the two are never interchanged.
    gate_bounds = zone.get("original_bounds")
    if not isinstance(gate_bounds, dict):
        gate_bounds = zone
    gate_low = _as_float(gate_bounds.get("low"))
    gate_high = _as_float(gate_bounds.get("high"))
    if gate_low is None or gate_high is None:
        gate_low, gate_high = zone_low, zone_high
    if canonical:
        formation_atr, provenance = _canonical_formation_atr(zone)
        if formation_atr is None and provenance:
            # Canonical evidence is present but its ATR is missing/invalid: the
            # geometry cannot be measured, so fail closed instead of borrowing
            # the execution ATR.
            return _reject(GEOMETRY_FORMATION_ATR_UNAVAILABLE)
        if formation_atr is None:
            # Legacy projection with no canonical evidence block: keep the
            # existing reference (documented boundary, R80-91-02 note).
            formation_atr = atr
    else:
        # The technical fallback zone carries no source-timeframe ATR by
        # construction, so its existing reference (the frozen execution ATR)
        # stays exactly as before.
        formation_atr = atr
    geometry = pre_plan_geometry_gate(
        side=side,
        require_tick=canonical and has_canonical_provenance(zone),
        original_low=gate_low,
        original_high=gate_high,
        formation_atr=formation_atr,
        execution_atr=atr,
        price=price,
        tick_size=_as_float(zone.get("tick_size")),
    )
    if not geometry.plan_eligible:
        return _reject(*geometry.rejection_codes)

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
            tech.get("resistance_zones"), above=zone_high
        )
    else:
        entry = zone_high
        stop_loss = zone_high + atr
        take_profit = _nearest_opposite_level(
            tech.get("support_zones"), below=zone_low
        )
    if take_profit is None:
        return _reject(PLAN_TP_MISSING)

    if side == "buy" and not (stop_loss < entry < take_profit):
        return _reject(PLAN_SHAPE_INVALID)
    if side == "sell" and not (take_profit < entry < stop_loss):
        return _reject(PLAN_SHAPE_INVALID)

    # Minimum R:R gate: reject scenarios with poor geometric ratio before
    # constructing the plan — the chart would otherwise render a wide zone
    # with a needle-thin TP distance.  The threshold comes from the caller's
    # ``min_rr`` parameter from the owner-configurable order-policy
    # ``min_risk_reward``.  No policy means no plan.
    try:
        candidate_plan = ScenarioPlan(
            direction=side,
            entry=entry,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source=_SOURCE_CANONICAL if canonical else _SOURCE_TECHNICAL,
            entry_zone_low=zone_low,
            entry_zone_high=zone_high,
        )
    except CompositionInputError:
        # Defensive: ordering/positivity already checked; never raise into the
        # scan.  Fail closed instead.
        return _reject(PLAN_SHAPE_INVALID)

    plan_rr = compute_scenario_rr(candidate_plan, side)
    if min_rr is None:
        return _reject(PLAN_POLICY_UNAVAILABLE)
    if plan_rr is None or plan_rr < min_rr:
        return _reject(PLAN_MIN_RR)

    return PlanAttempt(
        candidate_id=candidate_id,
        zone_id=zone_id,
        plan=candidate_plan,
        plan_available=True,
    )


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


# Fields that mark a zone payload as carrying canonical formation evidence.
_CANONICAL_PROVENANCE_FIELDS = CANONICAL_PROVENANCE_FIELDS


def _canonical_formation_atr(zone: dict[str, Any]) -> tuple[float | None, bool]:
    """Formation ATR of a canonical zone and whether provenance was present.

    Same priority and validation as the scorer (``departure_measurement
    .atr_before_event``, then ``formation_atr``).  The second value says whether
    the payload carries a canonical formation-evidence block at all:

    * ``True`` — the zone claims canonical provenance, so an unusable ATR is a
      real defect: the caller fails the geometry gate closed and never
      substitutes the execution ATR (P11).
    * ``False`` — a legacy/selected-zone projection with no provenance block
      (the live Scanner route serialises only bounds/quality today).  There is
      no source-timeframe ATR to honour, so the existing reference is kept and
      bringing canonical evidence into that projection stays with task 94+/101+.
    """

    provenance = any(field in zone for field in _CANONICAL_PROVENANCE_FIELDS)
    measurement = zone.get("departure_measurement")
    measurement = measurement if isinstance(measurement, dict) else {}
    atr = _finite_positive(measurement.get("atr_before_event"))
    if atr is not None:
        return atr, provenance
    return _finite_positive(zone.get("formation_atr")), provenance


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
    """Distance from price to the NEAREST zone edge (0 when inside the zone).

    Delegates to the shared geometry seam (task 89) so the planner and the
    scorer measure distance with one rule.
    """

    distance = _shared_distance_to_zone(price, low, high)
    return 0.0 if distance is None else distance


def _finite_positive(value: object) -> float | None:
    result = _as_float(value)
    if result is None or result <= 0:
        return None
    return result


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "PlanAttempt",
    "plan_for_candidate",
    "plan_to_dict",
    "plans_from_canonical_selection",
    "produce_scenario_plans",
    "produce_scenario_plans_from_zones",
    "scenario_plan_from_payload",
]
