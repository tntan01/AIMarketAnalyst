"""Canonical SMC quality evaluation: B, Q, L, C and S (tasks 80–87).

The evaluator owns the approved BQLC contract (docs/plans/smc-bqlc-spec.md): it
validates each candidate, measures the structure (B), zone (Q), liquidity (L)
and SMC-context (C) components from canonical evidence, keeps every rejection
reason, and never chooses the final selected candidate or reads a plan.

Invariants owned here:

* every component and sub-feature stays inside ``[0, 1]`` and only
  ``quality_raw`` is rounded, exactly once (round-half-up);
* an optional feature without evidence after a complete evaluation is ``0`` and
  the weights are never renormalized; a *required* input that is missing makes
  the side ``DATA_UNAVAILABLE`` with ``quality_raw=null`` instead of ``0``;
* no evidence is counted twice, and M15/AI/distance/regime/R:R never change S;
* ATR formation is the causal same-timeframe reference of the source zone and is
  never replaced by the current ATR.
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Sequence

from core.smc_confluence import (
    build_d1_reaction_evidence,
    build_parent_child_relation,
)
from core.smc_geometry import (
    GEOMETRY_BEYOND_HARD_DISTANCE,
    GEOMETRY_FORMATION_ATR_UNAVAILABLE,
    GEOMETRY_TICK_SIZE_UNAVAILABLE,
    HARD_DISTANCE_ATR,
    has_canonical_provenance,
    ZoneGeometryState,
    clamp01,
    evaluate_zone_geometry,
    linear,
)
from core.smc_m15_confirmation import evaluate_m15_entry_confirmation
from core.smc_models import (
    CONFIRMATION_RANK_BY_STATE,
    CONFIRMATION_RANK_CANDIDATE,
    SMC_QUALITY_STATE_DATA_UNAVAILABLE,
    SMC_QUALITY_STATE_EVALUATED,
    SMC_QUALITY_STATE_NO_ZONE,
    CandidateEvaluation,
    SmcCandidateSet,
    SmcQualityBreakdown,
    candidate_order_key,
    candidate_plan_zone,
)

# Structure-event lifetime by timeframe (parameter table P2); the trigger
# feature decays inside it and reaches 0 once the event expired.
STRUCTURE_TRIGGER_LIFETIME_BARS = {"D1": 20, "H4": 40, "H1": 80, "M15": 48}
# Sweep/zone link gate (BQLC spec §5, contract of task 68).
POOL_LINK_DISTANCE_ATR = 0.25
POOL_LINK_WINDOW_BARS = 20

# Feature weights (BQLC spec §3, §4, §5, §6) — approved values, unchanged.
B_STATE_WEIGHT = 0.55
B_EVENT_WEIGHT = 0.25
B_TRIGGER_WEIGHT = 0.20
FORMATION_BODY_ATR_WEIGHT = 0.35
FORMATION_BODY_RANGE_WEIGHT = 0.25
FORMATION_CLOSE_WEIGHT = 0.20
FORMATION_FAMILY_WEIGHT = 0.20
Q_FORMATION_WEIGHT = 0.50
Q_GEOMETRY_WEIGHT = 0.20
Q_INTEGRITY_WEIGHT = 0.30
INTEGRITY_LIFECYCLE_WEIGHT = 0.35
INTEGRITY_PENETRATION_WEIGHT = 0.25
INTEGRITY_DWELL_WEIGHT = 0.20
INTEGRITY_AGE_WEIGHT = 0.20
L_DEPTH_WEIGHT = 0.50
L_RECLAIM_WEIGHT = 0.30
L_CONSUMED_WEIGHT = 0.20
C_PARENT_CHILD_WEIGHT = 0.60
C_REACTION_WEIGHT = 0.25
C_DIRECTION_WEIGHT = 0.15

# Reason codes owned by the quality evaluation.
QUALITY_STRUCTURE_UNAVAILABLE = "STRUCTURE_UNAVAILABLE"
QUALITY_STRUCTURE_AGAINST_SIDE = "STRUCTURE_AGAINST_SIDE"
QUALITY_STRUCTURE_EVENT_INVALIDATED = "STRUCTURE_EVENT_INVALIDATED"
QUALITY_STRUCTURE_HISTORICAL_ONLY = "STRUCTURE_HISTORICAL_ONLY"
QUALITY_EVENT_TIME_UNAVAILABLE = "STRUCTURE_EVENT_TIME_UNAVAILABLE"
QUALITY_FORMATION_ATR_UNAVAILABLE = GEOMETRY_FORMATION_ATR_UNAVAILABLE
QUALITY_FORMATION_UNAVAILABLE = "FORMATION_MEASUREMENT_UNAVAILABLE"
QUALITY_FAMILY_FORMATION_UNAVAILABLE = "FAMILY_FORMATION_UNAVAILABLE"
QUALITY_LIFECYCLE_UNAVAILABLE = "LIFECYCLE_EVIDENCE_UNAVAILABLE"
QUALITY_AGE_UNAVAILABLE = "AGE_SCORE_UNAVAILABLE"
QUALITY_FVG_IMBALANCE_FILLED = "FVG_IMBALANCE_FILLED"
QUALITY_NO_RELATED_SWEEP = "NO_RELATED_SWEEP"
QUALITY_SWEEP_SOURCE_UNKNOWN = "SWEEP_POOL_SOURCE_UNKNOWN"
QUALITY_SWEEP_LINK_OUT_OF_GATE = "SWEEP_LINK_OUT_OF_GATE"
QUALITY_SWEEP_NOT_CLAIMED = "SWEEP_NOT_CLAIMED_BY_SETUP"
QUALITY_PARENT_CHILD_UNAVAILABLE = "PARENT_CHILD_UNAVAILABLE"
QUALITY_D1_REACTION_UNAVAILABLE = "D1_REACTION_UNAVAILABLE"
QUALITY_COUNTERTREND_UNCONFIRMED = "COUNTERTREND_UNCONFIRMED"
QUALITY_NO_VALID_SETUP = "NO_VALID_SETUP"
QUALITY_WRONG_SIDE = "DIRECTION_MISMATCH"
QUALITY_ZONE_INVALID = "ZONE_INVALID_OR_EXPIRED"
QUALITY_ZONE_FAMILY_UNKNOWN = "UNKNOWN_ZONE_FAMILY"
QUALITY_CONFIRMATION_PENDING = "ZONE_PENDING_CONFIRMATION"
QUALITY_ZONE_NOT_AVAILABLE = "ZONE_NOT_AVAILABLE_YET"
QUALITY_CORE_UNAVAILABLE = "SMC_CORE_DATA_UNAVAILABLE"
# D101-02: a rule that quantizes price cannot conclude without the canonical
# tick size.  It is a per-candidate missing dependency, not a snapshot verdict.
QUALITY_TICK_SIZE_UNAVAILABLE = GEOMETRY_TICK_SIZE_UNAVAILABLE

# Only these rejections mean "required data was missing" (BQLC spec §7): they
# turn the side into DATA_UNAVAILABLE instead of an evaluated zero.
MANDATORY_MISSING_REJECTIONS = frozenset({
    QUALITY_FORMATION_ATR_UNAVAILABLE,
    QUALITY_TICK_SIZE_UNAVAILABLE,
})


def evaluate_candidate_sets(
    smc: dict[str, Any],
    technical: dict[str, Any] | None = None,
    *,
    as_of: Any | None = None,
    core_reason_codes: Sequence[str] = (),
    m15_candles: Any | None = None,
    m15_as_of: Any | None = None,
) -> dict[str, SmcCandidateSet]:
    """Evaluate both sides with the canonical B/Q/L/C contract.

    ``core_reason_codes`` carries the caller's core-data verdict: a non-empty
    sequence means the snapshot itself is not good enough, so every side is
    ``DATA_UNAVAILABLE`` with ``quality_raw=null`` and no candidate is invented.
    """

    context = smc if isinstance(smc, dict) else {}
    technical_context = technical if isinstance(technical, dict) else {}
    return {
        side: _evaluate_side_candidates(
            side,
            context,
            technical_context,
            as_of=as_of,
            core_reason_codes=tuple(core_reason_codes),
            m15_candles=m15_candles,
            m15_as_of=m15_as_of,
        )
        for side in ("buy", "sell")
    }


def order_candidates(
    evaluations: Sequence[CandidateEvaluation],
) -> tuple[CandidateEvaluation, ...]:
    """Deterministic candidate order (task 91, selection spec §4.2).

    Candidates whose mandatory gate failed stay in the evaluation list with
    their reasons but never enter the order, so a rejected candidate can never
    hide a later valid one.
    """

    eligible = [
        evaluation for evaluation in evaluations if evaluation.mandatory_passed
    ]
    return tuple(sorted(eligible, key=candidate_order_key))


def _evaluate_side_candidates(
    side: str,
    smc: dict[str, Any],
    technical: dict[str, Any],
    *,
    as_of: Any | None,
    core_reason_codes: tuple[str, ...],
    m15_candles: Any | None,
    m15_as_of: Any | None,
) -> SmcCandidateSet:
    if core_reason_codes:
        return SmcCandidateSet(
            side=side,
            state=SMC_QUALITY_STATE_DATA_UNAVAILABLE,
            quality=SmcQualityBreakdown.data_unavailable(
                QUALITY_CORE_UNAVAILABLE,
                *core_reason_codes,
            ),
            reason_codes=(QUALITY_CORE_UNAVAILABLE, *core_reason_codes),
        )

    price = _positive_float(technical.get("price"))
    execution_atr = _positive_float(technical.get("atr_h4") or technical.get("atr_d1"))
    candidates: list[CandidateEvaluation] = []
    missing_mandatory_reasons: list[str] = []
    for timeframe in ("H4", "H1"):
        timeframe_data = smc.get(timeframe, {})
        if not isinstance(timeframe_data, dict):
            continue
        for family, zone in zone_payloads(timeframe_data, side):
            evaluation, mandatory_missing = evaluate_candidate(
                side=side,
                timeframe=timeframe,
                family=family,
                zone=zone if isinstance(zone, dict) else {},
                timeframe_data=timeframe_data,
                smc=smc,
                price=price,
                execution_atr=execution_atr,
                as_of=as_of,
                m15_candles=m15_candles,
                m15_as_of=m15_as_of,
            )
            if mandatory_missing:
                missing_mandatory_reasons.append(QUALITY_FORMATION_ATR_UNAVAILABLE)
            if QUALITY_TICK_SIZE_UNAVAILABLE in evaluation.rejection_codes:
                missing_mandatory_reasons.append(QUALITY_TICK_SIZE_UNAVAILABLE)
            candidates.append(evaluation)

    # R80-91-01: only a candidate that passed the mandatory gate may carry the
    # side verdict.  A geometry/invalidity hard-reject keeps its measured
    # quality for the trace but can never win the side quality or the order.
    evaluated = [
        candidate
        for candidate in candidates
        if candidate.mandatory_passed
        and candidate.quality is not None
        and candidate.quality.state == SMC_QUALITY_STATE_EVALUATED
    ]
    if not evaluated:
        if missing_mandatory_reasons:
            missing_reasons = tuple(dict.fromkeys(missing_mandatory_reasons))
            return SmcCandidateSet(
                side=side,
                state=SMC_QUALITY_STATE_DATA_UNAVAILABLE,
                quality=SmcQualityBreakdown.data_unavailable(*missing_reasons),
                candidates=tuple(candidates),
                reason_codes=missing_reasons,
            )
        return SmcCandidateSet(
            side=side,
            state=SMC_QUALITY_STATE_NO_ZONE,
            quality=SmcQualityBreakdown.no_zone(QUALITY_NO_VALID_SETUP),
            candidates=tuple(candidates),
            reason_codes=(QUALITY_NO_VALID_SETUP,),
        )

    # Side-level quality reports the current best *eligible* candidate; the
    # planning order is the same list through order_candidates().
    best = min(evaluated, key=candidate_order_key)
    assert best.quality is not None
    return SmcCandidateSet(
        side=side,
        state=SMC_QUALITY_STATE_EVALUATED,
        quality=best.quality,
        candidates=tuple(candidates),
        reason_codes=best.reason_codes,
    )


def evaluate_candidate(
    *,
    side: str,
    timeframe: str,
    family: str,
    zone: dict[str, Any],
    timeframe_data: dict[str, Any],
    smc: dict[str, Any],
    price: float | None,
    execution_atr: float | None,
    as_of: Any | None,
    m15_candles: Any | None,
    m15_as_of: Any | None,
) -> tuple[CandidateEvaluation, bool]:
    """Validate one candidate and measure its B/Q/L/C quality."""

    zone_id = str(zone.get("zone_id") or "").strip()
    normalized_family = _quality_family(family, zone)
    direction = _zone_direction(zone, normalized_family or family)
    reasons: list[str] = []
    rejections: list[str] = []

    if not zone_id:
        rejections.append("MISSING_ZONE_ID")
    if direction != side:
        rejections.append(QUALITY_WRONG_SIDE)
    if normalized_family is None:
        rejections.append(QUALITY_ZONE_FAMILY_UNKNOWN)

    lifecycle_status = str(zone.get("lifecycle_status") or "candidate").strip().lower()
    available_at = _optional_text(zone.get("available_at"))
    confirmation_state = _candidate_confirmation_state(
        zone,
        lifecycle_status,
        available_at=available_at,
        as_of=as_of,
    )
    if confirmation_state in {"invalid", "expired"}:
        rejections.append(QUALITY_ZONE_INVALID)
    elif confirmation_state == "candidate":
        reasons.append(QUALITY_CONFIRMATION_PENDING)
    elif confirmation_state == "waiting" and available_at is None:
        reasons.append(QUALITY_ZONE_NOT_AVAILABLE)

    original_bounds = zone.get("original_bounds")
    bounds = original_bounds if isinstance(original_bounds, dict) else zone
    low = _optional_float(bounds.get("low"))
    high = _optional_float(bounds.get("high"))
    formation_atr = _formation_atr(zone)
    tick_size = _optional_float(zone.get("tick_size"))

    geometry = evaluate_zone_geometry(
        family=normalized_family or "",
        side=side,
        original_low=low,
        original_high=high,
        formation_atr=formation_atr,
        execution_atr=execution_atr,
        price=price,
        tick_size=tick_size,
        family_inputs=_family_geometry_inputs(normalized_family, zone),
        require_family_geometry=normalized_family is not None,
        require_tick=has_canonical_provenance(zone),
    )
    rejections.extend(geometry.rejection_codes)
    reasons.extend(geometry.reason_codes)

    structure, structure_reasons, structure_rejections = _structure_features(
        side,
        zone,
        timeframe_data,
        timeframe=timeframe,
    )
    formation, formation_reasons, mandatory_missing = _formation_features(
        normalized_family,
        zone,
        formation_atr=formation_atr,
    )
    integrity, integrity_reasons = _integrity_features(
        normalized_family,
        zone,
        lifecycle_status=lifecycle_status,
    )
    liquidity, liquidity_reasons = _liquidity_features(side, zone, timeframe_data)
    context, context_reasons = _context_features(
        side,
        zone,
        smc,
        timeframe=timeframe,
        as_of=as_of,
        tick_size=tick_size,
    )
    reasons.extend(structure_reasons)
    reasons.extend(formation_reasons)
    reasons.extend(integrity_reasons)
    reasons.extend(liquidity_reasons)
    reasons.extend(context_reasons)
    rejections.extend(structure_rejections)

    if (
        geometry.distance_atr is not None
        and geometry.distance_atr > HARD_DISTANCE_ATR
    ):
        rejections.append(GEOMETRY_BEYOND_HARD_DISTANCE)

    # A wrong-side or unknown-family payload is a rejection, not a scored
    # candidate: it never contributes to the side-level quality.
    scorable = (
        normalized_family is not None
        and direction == side
        and not mandatory_missing
    )
    quality: SmcQualityBreakdown | None = None
    if scorable:
        quality = _assemble_quality(
            structure=structure,
            formation=formation,
            integrity=integrity,
            geometry=geometry,
            liquidity=liquidity,
            context=context,
            reason_codes=reasons,
        )

    m15_status, m15_reason = _candidate_m15_status(
        side,
        low,
        high,
        zone_id,
        available_at=available_at,
        m15_candles=m15_candles,
        m15_as_of=m15_as_of,
    )
    if m15_reason:
        reasons.append(m15_reason)
    confirmation_state = _apply_m15_confirmation_state(
        confirmation_state,
        m15_status,
        quality is not None,
    )
    if confirmation_state in {"invalid", "expired"}:
        rejections.append(QUALITY_ZONE_INVALID)
        quality = None
    if not scorable:
        quality = None

    passed = (
        quality is not None
        and quality.state == SMC_QUALITY_STATE_EVALUATED
        and not rejections
    )
    return (
        CandidateEvaluation(
            candidate_id=zone_id or "unknown-candidate",
            zone_id=zone_id,
            setup_id=_optional_text(zone.get("setup_id")),
            side=side,
            timeframe=timeframe,
            family=normalized_family or "unknown",
            confirmation_state=confirmation_state,
            quality=quality,
            lifecycle_status=lifecycle_status,
            visit_id=_visit_id(zone),
            available_at=available_at,
            confirmation_event_id=_optional_text(zone.get("confirmation_event_id")),
            m15_status=m15_status,
            geometry=geometry.to_dict(),
            distance_atr=geometry.distance_atr,
            mandatory_passed=passed,
            rejection_codes=tuple(dict.fromkeys(rejections)),
            reason_codes=tuple(dict.fromkeys(reasons)),
            confirmation_rank=CONFIRMATION_RANK_BY_STATE.get(
                confirmation_state,
                CONFIRMATION_RANK_CANDIDATE,
            ),
            # The exact canonical payload subset the shared plan seam must use
            # (task 92): the planner reads the same bounds/ATR/provenance this
            # evaluation gated on instead of resolving the zone a second time.
            plan_zone=candidate_plan_zone(zone),
        ),
        mandatory_missing,
    )


def _assemble_quality(
    *,
    structure: dict[str, float],
    formation: dict[str, float],
    integrity: dict[str, float],
    geometry: ZoneGeometryState,
    liquidity: dict[str, float],
    context: dict[str, float],
    reason_codes: list[str],
) -> SmcQualityBreakdown:
    """Combine the measured features into B, Q, L, C and S (tasks 84, 87)."""

    state_score = structure["state_score"]
    event_score = structure["event_score"]
    trigger_score = structure["trigger_score"]
    b = (
        B_STATE_WEIGHT * state_score
        + B_EVENT_WEIGHT * event_score
        + B_TRIGGER_WEIGHT * trigger_score
    )

    formation_score = (
        FORMATION_BODY_ATR_WEIGHT * formation["body_atr_score"]
        + FORMATION_BODY_RANGE_WEIGHT * formation["body_range_score"]
        + FORMATION_CLOSE_WEIGHT * formation["close_score"]
        + FORMATION_FAMILY_WEIGHT * formation["family_formation_score"]
    )
    geometry_score = geometry.geometry or 0.0
    integrity_score = (
        INTEGRITY_LIFECYCLE_WEIGHT * integrity["lifecycle_state_score"]
        + INTEGRITY_PENETRATION_WEIGHT * integrity["penetration_score"]
        + INTEGRITY_DWELL_WEIGHT * integrity["dwell_score"]
        + INTEGRITY_AGE_WEIGHT * integrity["age_score"]
    )
    q = (
        Q_FORMATION_WEIGHT * formation_score
        + Q_GEOMETRY_WEIGHT * geometry_score
        + Q_INTEGRITY_WEIGHT * integrity_score
    )

    pool_score = liquidity["pool_score"]
    link_validity = liquidity["link_validity"]
    l = (
        pool_score
        * link_validity
        * (
            L_DEPTH_WEIGHT * liquidity["sweep_depth_score"]
            + L_RECLAIM_WEIGHT * liquidity["reclaim_quality"]
            + L_CONSUMED_WEIGHT * liquidity["consumed_once_score"]
        )
    )

    c = (
        C_PARENT_CHILD_WEIGHT * context["parent_child_score"]
        + C_REACTION_WEIGHT * context["independent_htf_reaction_score"]
        + C_DIRECTION_WEIGHT * context["direction_agreement_score"]
    )

    features: list[tuple[str, float]] = []
    for section in (structure, formation, integrity, liquidity, context):
        features.extend((name, clamp01(value) or 0.0) for name, value in section.items())
    if geometry.width_score is not None:
        features.append(("width_score", clamp01(geometry.width_score) or 0.0))
    if geometry.family_geometry_score is not None:
        features.append(
            ("family_geometry_score", clamp01(geometry.family_geometry_score) or 0.0)
        )
    features.extend((
        ("formation", clamp01(formation_score) or 0.0),
        ("geometry", clamp01(geometry_score) or 0.0),
        ("integrity", clamp01(integrity_score) or 0.0),
    ))

    return SmcQualityBreakdown(
        state=SMC_QUALITY_STATE_EVALUATED,
        b=clamp01(b),
        q=clamp01(q),
        l=clamp01(l),
        c=clamp01(c),
        formation=clamp01(formation_score),
        geometry=clamp01(geometry_score),
        integrity=clamp01(integrity_score),
        features=tuple(features),
        reason_codes=tuple(dict.fromkeys(reason_codes)),
    )


def _structure_features(
    side: str,
    zone: dict[str, Any],
    timeframe_data: dict[str, Any],
    *,
    timeframe: str,
) -> tuple[dict[str, float], list[str], list[str]]:
    """B — directional structure state, event validity and trigger freshness."""

    reasons: list[str] = []
    rejections: list[str] = []
    structure = str(timeframe_data.get("structure") or "unknown").strip()
    expected = "HH/HL" if side == "buy" else "LH/LL"
    opposite = "LH/LL" if side == "buy" else "HH/HL"
    bos = bool(timeframe_data.get("bos"))
    choch = bool(timeframe_data.get("choch"))
    choch_confirmed = bool(timeframe_data.get("choch_confirmed"))
    displacement = str(timeframe_data.get("displacement") or "neutral")
    expected_displacement = "bullish" if side == "buy" else "bearish"

    if structure in {"", "unknown", "None"}:
        state_score = 0.0
        reasons.append(QUALITY_STRUCTURE_UNAVAILABLE)
    elif structure == "mixed":
        state_score = 0.25
    elif choch and choch_confirmed and bos:
        state_score = 1.00
    elif bos and structure == expected:
        state_score = 0.85
    elif choch and not choch_confirmed:
        state_score = 0.55
    elif structure == expected:
        state_score = 0.60
    else:
        state_score = 0.0
        reasons.append(QUALITY_STRUCTURE_AGAINST_SIDE)

    event_id = _optional_text(zone.get("confirmation_event_id")) or _optional_text(
        zone.get("related_structure_event_id")
    )
    terminal = (
        _optional_text(zone.get("invalidated_at")) is not None
        or bool(zone.get("lifecycle_expired"))
        or bool(zone.get("broken"))
    )
    if terminal:
        event_score = 0.0
        reasons.append(QUALITY_STRUCTURE_EVENT_INVALIDATED)
    elif event_id and (bos or choch) and displacement == expected_displacement:
        event_score = 1.00
    elif structure == expected:
        event_score = 0.50
        reasons.append(QUALITY_STRUCTURE_HISTORICAL_ONLY)
    else:
        event_score = 0.0

    lifetime = STRUCTURE_TRIGGER_LIFETIME_BARS.get(timeframe, 80)
    age_bars = _optional_float(zone.get("structure_event_age_bars"))
    if age_bars is None:
        age_bars = _optional_float(zone.get("age_bars"))
        if age_bars is not None:
            reasons.append(QUALITY_EVENT_TIME_UNAVAILABLE)
    if age_bars is None or lifetime <= 0:
        trigger_score = 0.0
    else:
        trigger_score = linear(1.0 - age_bars / lifetime, 0.0, 1.0)
    return (
        {
            "state_score": state_score,
            "event_score": event_score,
            "trigger_score": trigger_score,
        },
        reasons,
        rejections,
    )


def _formation_features(
    family: str | None,
    zone: dict[str, Any],
    *,
    formation_atr: float | None,
) -> tuple[dict[str, float], list[str], bool]:
    """Q — formation/departure features (task 81) plus the mandatory ATR gate."""

    reasons: list[str] = []
    measurement = zone.get("departure_measurement")
    if not isinstance(measurement, dict) or not measurement:
        measurement = zone.get("middle_measurement")
    measurement = measurement if isinstance(measurement, dict) else {}

    body_atr = _optional_float(measurement.get("body_atr"))
    body_range = _optional_float(measurement.get("body_range"))
    directional_close = _optional_float(measurement.get("directional_close_location"))
    status = str(measurement.get("status") or "").strip().lower()

    atr = _positive_float(measurement.get("atr_before_event")) or _positive_float(
        formation_atr
    )
    mandatory_missing = False
    if body_atr is None and (atr is None or status in {"unavailable", "invalid"}):
        # Required formation ATR is missing: the candidate cannot be measured.
        mandatory_missing = True
        reasons.append(QUALITY_FORMATION_ATR_UNAVAILABLE)
    if body_atr is None and body_range is None and directional_close is None:
        mandatory_missing = True
        reasons.append(QUALITY_FORMATION_UNAVAILABLE)

    body_atr_score = (
        linear(body_atr, 0.30, 1.00) if body_atr is not None else 0.0
    )
    body_range_score = (
        linear(body_range, 0.50, 1.00) if body_range is not None else 0.0
    )
    close_score = (
        linear(directional_close, 0.70, 0.90)
        if directional_close is not None
        else 0.0
    )

    family_score = _family_formation_score(family, zone, close_score, atr)
    if family_score is None:
        family_score = 0.0
        reasons.append(QUALITY_FAMILY_FORMATION_UNAVAILABLE)
    return (
        {
            "body_atr_score": body_atr_score,
            "body_range_score": body_range_score,
            "close_score": close_score,
            "family_formation_score": family_score,
        },
        reasons,
        mandatory_missing,
    )


def _family_formation_score(
    family: str | None,
    zone: dict[str, Any],
    close_score: float,
    atr: float | None,
) -> float | None:
    """Family formation feature (BQLC spec §4.1)."""

    if family == "ob":
        return close_score
    if family == "fvg":
        gap = zone.get("gap_measurement")
        gap = gap if isinstance(gap, dict) else {}
        gap_width = _positive_float(gap.get("gap_width"))
        reference = _positive_float(gap.get("atr_before_event")) or atr
        if gap_width is None or reference is None:
            return None
        return linear(gap_width / reference, 0.10, 0.50)
    if family == "supply_demand":
        efficiency = _positive_float(zone.get("departure_efficiency"))
        if efficiency is None:
            return None
        return linear(efficiency, 1.50, 3.00)
    return None


def _integrity_features(
    family: str | None,
    zone: dict[str, Any],
    *,
    lifecycle_status: str,
) -> tuple[dict[str, float], list[str]]:
    """Q — lifecycle integrity features (task 83)."""

    reasons: list[str] = []
    visits = zone.get("visits")
    visits = visits if isinstance(visits, list) else []
    filled = (
        family == "fvg"
        and str(zone.get("fill_status") or "").strip().lower() == "filled"
    )
    terminal = lifecycle_status in {"invalid", "expired"} or bool(zone.get("broken"))

    if terminal or filled:
        lifecycle_state_score = 0.0
        if filled:
            reasons.append(QUALITY_FVG_IMBALANCE_FILLED)
    elif not visits:
        lifecycle_state_score = 1.00
    else:
        last_visit = visits[-1] if isinstance(visits[-1], dict) else {}
        state = str(last_visit.get("visit_state") or "").strip().lower()
        if state == "completed_reacted":
            lifecycle_state_score = 1.00
        elif state == "completed_unreacted":
            lifecycle_state_score = 0.80
        elif state == "open":
            lifecycle_state_score = 0.60
        elif state == "closed_by_invalidation":
            lifecycle_state_score = 0.0
        else:
            lifecycle_state_score = 0.80
            reasons.append(QUALITY_LIFECYCLE_UNAVAILABLE)

    last_visit = visits[-1] if visits and isinstance(visits[-1], dict) else {}
    penetration_ratio = _optional_float(last_visit.get("max_penetration_ratio"))
    if penetration_ratio is None:
        reasons.append(QUALITY_LIFECYCLE_UNAVAILABLE)
    penetration_score = 1.0 - min(1.0, max(0.0, penetration_ratio or 0.0))

    dwell_bars = _optional_float(last_visit.get("bars_spent_inside"))
    if dwell_bars is None and not visits:
        dwell_bars = 0.0
    dwell_score = clamp01(1.0 - (dwell_bars or 0.0) / 5.0) or 0.0

    age_score = _optional_float(zone.get("age_score"))
    if age_score is None:
        reasons.append(QUALITY_AGE_UNAVAILABLE)
        age_score = 0.0
    return (
        {
            "lifecycle_state_score": lifecycle_state_score,
            "penetration_score": penetration_score,
            "dwell_score": dwell_score,
            "age_score": age_score,
        },
        reasons,
    )


def _liquidity_features(
    side: str,
    zone: dict[str, Any],
    timeframe_data: dict[str, Any],
) -> tuple[dict[str, float], list[str]]:
    """L — liquidity evidence related to this setup (task 85)."""

    reasons: list[str] = []
    linked_id = _optional_text(zone.get("linked_sweep_id"))
    linked = bool(zone.get("liquidity_sweep_linked")) and linked_id is not None
    if not linked:
        return (
            {
                "pool_score": 0.0,
                "link_validity": 0.0,
                "sweep_depth_score": 0.0,
                "reclaim_quality": 0.0,
                "consumed_once_score": 0.0,
            },
            [QUALITY_NO_RELATED_SWEEP],
        )

    sweep = _find_sweep(timeframe_data, side, linked_id)
    pool_score = 1.00
    if sweep is None or not _sweep_has_source(sweep):
        pool_score = 0.50 if sweep is not None else 0.0
        reasons.append(QUALITY_SWEEP_SOURCE_UNKNOWN)

    distance = _optional_float(zone.get("linked_sweep_distance_atr"))
    time_delta = _optional_float(zone.get("linked_sweep_time_delta"))
    link_validity = 0.0
    if (
        (distance is None or distance <= POOL_LINK_DISTANCE_ATR)
        and (time_delta is None or time_delta <= POOL_LINK_WINDOW_BARS)
    ):
        link_validity = 1.0
    else:
        reasons.append(QUALITY_SWEEP_LINK_OUT_OF_GATE)

    depth_atr = None
    reclaim_bars = None
    if sweep is not None:
        depth_atr = _optional_float(sweep.get("depth_atr"))
        reclaim_bars = _optional_float(sweep.get("reclaim_bars"))
    sweep_depth_score = (
        linear(depth_atr, 0.10, 0.50) if depth_atr is not None else 0.0
    )
    reclaim_quality = 1.00 if (reclaim_bars is not None and reclaim_bars <= 1) else 0.0

    consumed_once_score = 0.0
    if sweep is not None and _sweep_owned_by(sweep, zone):
        consumed_once_score = 1.0
    else:
        reasons.append(QUALITY_SWEEP_NOT_CLAIMED)

    return (
        {
            "pool_score": pool_score,
            "link_validity": link_validity,
            "sweep_depth_score": sweep_depth_score,
            "reclaim_quality": reclaim_quality,
            "consumed_once_score": consumed_once_score,
        },
        reasons,
    )


def _context_features(
    side: str,
    zone: dict[str, Any],
    smc: dict[str, Any],
    *,
    timeframe: str,
    as_of: Any | None,
    tick_size: float | None,
) -> tuple[dict[str, float], list[str]]:
    """C — independent SMC context evidence (task 86)."""

    reasons: list[str] = []
    parent = _parent_zone(side, zone, smc, timeframe=timeframe)
    parent_child_score = 0.0
    if parent is None:
        reasons.append(QUALITY_PARENT_CHILD_UNAVAILABLE)
    else:
        relation = build_parent_child_relation(
            parent,
            zone,
            tick_size=tick_size,
            atr_parent=_formation_atr(parent),
        )
        parent_child_score = clamp01(relation.get("score")) or 0.0
        reasons.extend(
            str(code)
            for code in relation.get("reason_codes") or []
            if str(code).strip()
        )

    d1_zone = _d1_reaction_zone(side, zone, smc)
    reaction_score = 0.0
    if d1_zone is None:
        reasons.append(QUALITY_D1_REACTION_UNAVAILABLE)
    else:
        lifecycle = d1_zone.get("lifecycle")
        reaction = build_d1_reaction_evidence(
            d1_zone,
            lifecycle if lifecycle is not None else d1_zone,
            as_of=as_of,
        )
        reaction_score = clamp01(reaction.get("score")) or 0.0
        reasons.extend(
            str(code)
            for code in reaction.get("reason_codes") or []
            if str(code).strip()
        )

    direction_score = 1.0
    d1_direction = _timeframe_direction(smc, "D1")
    if d1_direction not in {"unknown", "", side}:
        structure = smc.get(timeframe, {})
        structure = structure if isinstance(structure, dict) else {}
        if not (structure.get("choch") and structure.get("choch_confirmed")):
            direction_score = 0.0
            reasons.append(QUALITY_COUNTERTREND_UNCONFIRMED)

    return (
        {
            "parent_child_score": parent_child_score,
            "independent_htf_reaction_score": reaction_score,
            "direction_agreement_score": direction_score,
        },
        reasons,
    )


def _candidate_confirmation_state(
    zone: dict[str, Any],
    lifecycle_status: str,
    *,
    available_at: str | None,
    as_of: Any | None,
) -> str:
    """Baseline confirmation state of one candidate (without M15)."""

    broken = bool(zone.get("broken"))
    if lifecycle_status == "expired":
        return "expired"
    if broken or lifecycle_status == "invalid":
        return "invalid"
    if lifecycle_status in {"candidate", "watch"} or bool(zone.get("candidate")):
        return "candidate"
    if available_at is None:
        return "candidate"
    return "confirmed"


def _candidate_m15_status(
    side: str,
    low: float | None,
    high: float | None,
    zone_id: str,
    *,
    available_at: str | None,
    m15_candles: Any | None,
    m15_as_of: Any | None,
) -> tuple[str, str | None]:
    """M15 readiness of one candidate; never changes its quality (R16-03)."""

    if m15_candles is None:
        return "missing", "M15_DATA_UNAVAILABLE"
    if low is None or high is None or not zone_id:
        return "missing", "M15_DATA_UNAVAILABLE"
    confirmation = evaluate_m15_entry_confirmation(
        side,
        low,
        high,
        m15_candles,
        zone_id=zone_id,
        available_at=available_at,
        as_of=m15_as_of,
    )
    return confirmation.m15_status, None


def _apply_m15_confirmation_state(
    state: str,
    m15_status: str,
    quality_evaluated: bool,
) -> str:
    """M15 only moves the confirmation state, never the quality (task 90/78)."""

    if state in {"invalid", "expired"}:
        return state
    if not quality_evaluated:
        return state
    if m15_status == "confirmed":
        return "confirmed"
    if m15_status == "waiting":
        return "waiting"
    if m15_status == "expired":
        return "watch"
    return state


def _family_geometry_inputs(family: str | None, zone: dict[str, Any]) -> dict[str, Any]:
    inputs: dict[str, Any] = {}
    original_bounds = zone.get("original_bounds")
    if isinstance(original_bounds, dict):
        low = _optional_float(original_bounds.get("low"))
        high = _optional_float(original_bounds.get("high"))
        if low is not None and high is not None:
            inputs["original_width"] = max(0.0, high - low)
            inputs["base_width"] = max(0.0, high - low)
    if family == "fvg":
        remaining_low = _optional_float(zone.get("remaining_low"))
        remaining_high = _optional_float(zone.get("remaining_high"))
        original_width = inputs.get("original_width")
        if original_width is None:
            bounds = zone.get("original_bounds")
            bounds = bounds if isinstance(bounds, dict) else {}
            low = _optional_float(bounds.get("low"))
            high = _optional_float(bounds.get("high"))
            if low is not None and high is not None:
                original_width = max(0.0, high - low)
        if remaining_low is not None and remaining_high is not None:
            inputs["remaining_width"] = max(0.0, remaining_high - remaining_low)
        inputs["original_width"] = original_width
    if family == "supply_demand":
        measurement = zone.get("base_measurement")
        measurement = measurement if isinstance(measurement, dict) else {}
        base_low = _optional_float(measurement.get("base_low"))
        base_high = _optional_float(measurement.get("base_high"))
        if base_low is not None and base_high is not None:
            inputs["base_width"] = max(0.0, base_high - base_low)
        inputs["average_range"] = _positive_float(measurement.get("average_range"))
        inputs["compression_limit"] = _positive_float(
            measurement.get("compression_limit")
        )
    return inputs


def _quality_family(family: str, zone: dict[str, Any]) -> str | None:
    # The zone payload's own family field is authoritative; the list key only
    # says which payload list it came from ("demand_zones" holds OB children).
    normalized = str(zone.get("family") or family or "").strip().lower()
    if normalized in {"ob", "order_block"}:
        return "ob"
    if normalized == "fvg":
        return "fvg"
    if normalized in {"supply_demand", "demand", "supply", "sd"}:
        return "supply_demand"
    return None


def _formation_atr(zone: dict[str, Any]) -> float | None:
    measurement = zone.get("departure_measurement")
    measurement = measurement if isinstance(measurement, dict) else {}
    atr = _positive_float(measurement.get("atr_before_event"))
    if atr is not None:
        return atr
    return _positive_float(zone.get("formation_atr"))


def _visit_id(zone: dict[str, Any]) -> str | None:
    visits = zone.get("visits")
    if isinstance(visits, list) and visits and isinstance(visits[-1], dict):
        return _optional_text(visits[-1].get("visit_id"))
    return None


def _find_sweep(
    timeframe_data: dict[str, Any],
    side: str,
    sweep_id: str,
) -> dict[str, Any] | None:
    sweeps = timeframe_data.get("zone_link_sweeps")
    keys = ("swept_lows", "swept_highs") if side == "buy" else ("swept_highs", "swept_lows")
    if not isinstance(sweeps, dict):
        return None
    for key in keys:
        values = sweeps.get(key)
        if not isinstance(values, list):
            continue
        for sweep in values:
            if isinstance(sweep, dict) and _optional_text(sweep.get("sweep_id")) == sweep_id:
                return sweep
    return None


def _sweep_has_source(sweep: dict[str, Any]) -> bool:
    if _optional_text(sweep.get("source_pool_id")) is not None:
        return True
    pool = sweep.get("source_pool")
    if isinstance(pool, dict):
        return bool(pool.get("pool_id") or pool.get("source_ids"))
    source_ids = sweep.get("source_ids")
    return isinstance(source_ids, (list, tuple)) and bool(source_ids)


def _sweep_owned_by(sweep: dict[str, Any], zone: dict[str, Any]) -> bool:
    owner = _optional_text(sweep.get("owner_setup_id"))
    setup_id = _optional_text(zone.get("setup_id"))
    if owner is None:
        assignment = sweep.get("assignment")
        if isinstance(assignment, dict):
            owner = _optional_text(assignment.get("owner_setup_id"))
    if owner is None or setup_id is None:
        return False
    return owner == setup_id


def _parent_zone(
    side: str,
    zone: dict[str, Any],
    smc: dict[str, Any],
    *,
    timeframe: str,
) -> dict[str, Any] | None:
    parent_timeframe = "D1" if timeframe == "H4" else "H4"
    parent_data = smc.get(parent_timeframe, {})
    if not isinstance(parent_data, dict):
        return None
    for family, candidate in zone_payloads(parent_data, side):
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("lifecycle_status") or "").lower() in {"invalid", "expired"}:
            continue
        return candidate
    return None


def _d1_reaction_zone(
    side: str,
    zone: dict[str, Any],
    smc: dict[str, Any],
) -> dict[str, Any] | None:
    d1_data = smc.get("D1", {})
    if not isinstance(d1_data, dict):
        return None
    for family, candidate in zone_payloads(d1_data, side):
        if isinstance(candidate, dict):
            return candidate
    return None


def _timeframe_direction(smc: dict[str, Any], timeframe: str) -> str:
    confluence = smc.get("confluence")
    confluence = confluence if isinstance(confluence, dict) else {}
    evidence = confluence.get("timeframe_evidence")
    evidence = evidence if isinstance(evidence, dict) else {}
    entry = evidence.get(timeframe)
    entry = entry if isinstance(entry, dict) else {}
    direction = str(entry.get("direction") or "").strip().lower()
    if direction in {"buy", "sell"}:
        return direction
    data = smc.get(timeframe, {})
    data = data if isinstance(data, dict) else {}
    structure = str(data.get("structure") or "").strip()
    if structure == "HH/HL":
        return "buy"
    if structure == "LH/LL":
        return "sell"
    return "unknown"


def zone_payloads(timeframe_data: dict[str, Any], side: str):
    """Family payload keys of one side, shared with the legacy scorer route."""

    keys = (
        ("demand", "demand_zones"),
        ("order_block", "order_blocks"),
        ("fvg", "fvg"),
    ) if side == "buy" else (
        ("supply", "supply_zones"),
        ("order_block", "order_blocks"),
        ("fvg", "fvg"),
    )
    for family, key in keys:
        values = timeframe_data.get(key)
        if not isinstance(values, list):
            continue
        for zone in values:
            if isinstance(zone, dict):
                yield family, zone


def _zone_direction(zone: dict[str, Any], family: str) -> str:
    """Direction from the explicit field, else from the family/type token."""

    explicit = str(zone.get("direction") or "").strip().lower()
    if explicit in {"buy", "sell"}:
        return explicit
    zone_type = str(zone.get("zone_type") or zone.get("type") or "").lower()
    if "bullish" in zone_type or family == "demand":
        return "buy"
    if "bearish" in zone_type or family == "supply":
        return "sell"
    return "unknown"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _positive_float(value: object) -> float | None:
    number = _finite(value)
    return number if number is not None and number > 0 else None


def _optional_float(value: object) -> float | None:
    return _finite(value)


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None
