"""Task 88 — B/Q/L/C arithmetic, families, invariants and candidate order.

Every expected number below is computed by hand from the approved contract
(docs/plans/smc-bqlc-spec.md §1–§9, parameter table P7/P10/P11) and written out
in the test; production helpers are never used to produce an expectation.

Covers the lot 80–91 blocks: B (80), Q formation/geometry/integrity (81–84),
L (85), C (86), S + rounding (87), the shared geometry seam (89) and the
deterministic candidate order (91).
"""

from __future__ import annotations

from math import isclose

from core.scanner_scenario_producers import (
    _MAX_PROTECTIVE_ZONE_DISTANCE_ATR,
    _MAX_ZONE_WIDTH_ATR,
)
from core.smc_geometry import (
    HARD_DISTANCE_ATR,
    MAX_ZONE_WIDTH_ATR,
    clamp01,
    evaluate_zone_geometry,
    family_geometry_score,
    inverse,
    linear,
    pre_plan_geometry_gate,
    width_score,
)
from core.smc_models import (
    CandidateEvaluation,
    SmcCandidateSet,
    SmcQualityBreakdown,
    candidate_order_key,
    round_half_up,
)
from core.smc_geometry import (  # noqa: F811  (R80-91-02 regression import)
    GEOMETRY_WIDTH_TOO_WIDE as ZONE_WIDTH_TOO_WIDE,
)
from core.smc_quality import (
    QUALITY_FORMATION_ATR_UNAVAILABLE,
    QUALITY_NO_RELATED_SWEEP,
    evaluate_candidate_sets,
    order_candidates,
)
from core.smc_readiness import evaluate_smc_readiness

_AS_OF = "2026-02-10T00:00:00+00:00"


def _zone(**overrides):
    """Canonical OB zone payload with fully known numbers (see the hand maths)."""

    zone = {
        "zone_id": "smcz-hand-1",
        "setup_id": "smcs-hand-1",
        "family": "ob",
        "direction": "buy",
        "type": "bullish_order_block",
        "lifecycle_status": "confirmed",
        "available_at": "2026-02-05T00:00:00+00:00",
        "confirmed_at": "2026-02-05T00:00:00+00:00",
        "original_bounds": {"low": 99.0, "high": 100.0},
        "low": 99.0,
        "high": 100.0,
        "tick_size": 0.1,
        "age_bars": 5,
        "age_score": 0.9,
        "confirmation_event_id": "smc-bos-hand-1",
        "departure_measurement": {
            "direction": "buy",
            "body_atr": 0.6,
            "body_range": 0.8,
            "directional_close_location": 0.86,
            "atr_before_event": 2.0,
            "status": "ok",
            "reason_codes": [],
        },
        "visits": [
            {
                "visit_id": "smcz-hand-1:visit-1",
                "visit_state": "completed_reacted",
                "max_penetration_ratio": 0.25,
                "bars_spent_inside": 1,
            }
        ],
        "linked_sweep_id": None,
        "liquidity_sweep_linked": False,
    }
    zone.update(overrides)
    return zone


def _context(zone, *, side="buy", structure="HH/HL", bos=True, displacement="bullish"):
    opposite_structure = "LH/LL" if side == "buy" else "HH/HL"
    timeframe_data = {
        "structure": structure if structure else opposite_structure,
        "bos": bos,
        "choch": False,
        "choch_confirmed": False,
        "displacement": displacement,
        "demand_zones": [zone] if side == "buy" else [],
        "supply_zones": [] if side == "buy" else [zone],
        "order_blocks": [],
        "fvg": [],
        "zone_link_sweeps": {},
    }
    parent_family = "demand_zones" if side == "buy" else "supply_zones"
    opposite_family = "supply_zones" if side == "buy" else "demand_zones"
    return {
        "symbol": "EUR/USD",
        "D1": {
            "structure": structure if structure else opposite_structure,
            "bos": bos,
            "displacement": displacement,
            "order_blocks": [],
            "fvg": [],
            # The same lineage as the D1 parent so parent-child containment is
            # measurable (C); the D1 reaction still needs its own visit evidence.
            parent_family: [zone],
            opposite_family: [],
            "zone_link_sweeps": {},
        },
        "H4": timeframe_data,
        "H1": {
            "structure": structure if structure else opposite_structure,
            "bos": bos,
            "displacement": displacement,
            "order_blocks": [],
            "fvg": [],
            parent_family: [],
            opposite_family: [],
            "zone_link_sweeps": {},
        },
        "confluence": {
            "timeframe_evidence": {
                "D1": {"direction": side},
                "H4": {"direction": side},
                "H1": {"direction": side},
            }
        },
    }


def _technical(price=99.5, atr=2.0):
    return {"price": price, "atr_h4": atr}


# -- Hand-computed B/Q/L/C (tasks 80–87) -------------------------------------


def test_hand_computed_quality_matches_the_approved_formula():
    """One OB candidate whose features are all known by hand.

    width/ATR = 1.00/2.00 = 0.50 -> width_score = inverse(.50, .35, 1.00) = .769230769
    ob_compactness = 1 - 1.00/2.00 = .50 -> geometry = .65*.769230769 + .35*.50 = .675
    body/ATR .60 -> (0.60-0.30)/0.70 = .428571429
    body/range .80 -> (0.80-0.50)/0.50 = .60
    close-location .86 -> (0.86-0.70)/0.20 = .80 (OB family formation = close score)
    formation = .35*.428571429 + .25*.60 + .20*.80 + .20*.80 = .62
    integrity = .35*1.00 (reacted) + .25*.75 (1-penetration) + .20*.80 (dwell 1) + .20*.90 (age) = .8775
    Q = .50*.62 + .20*.675 + .30*.8775 = .70825
    state .85 (HH/HL + BOS), event 1.00 (event id + BOS + matching displacement),
    trigger = linear(1-5/40, 0, 1) = .875  -> B = .55*.85 + .25*1 + .20*.875 = .8925
    L = 0 (no related sweep),  C = .60*1.0 (contained) + .25*0 + .15*1.0 = .75
    S = 4*.8925 + 7*.70825 + 2*0 + 2*.75 = 10.02775 -> raw 10, score 66.851666...
    """

    sets = evaluate_candidate_sets(
        _context(_zone()),
        _technical(),
        as_of=_AS_OF,
    )
    quality = sets["buy"].quality

    assert quality.state == "evaluated"
    assert isclose(quality.b, 0.8925, abs_tol=1e-9)
    assert isclose(quality.q, 0.70825, abs_tol=1e-9)
    assert quality.l == 0.0
    assert isclose(quality.c, 0.75, abs_tol=1e-9)
    expected_s = 4 * 0.8925 + 7 * 0.70825 + 2 * 0.0 + 2 * 0.75
    assert isclose(quality.total, expected_s, abs_tol=1e-9)
    assert quality.quality_raw == 10
    assert isclose(quality.quality_score, 100 * expected_s / 15, abs_tol=1e-9)

    candidate = sets["buy"].candidates[0]
    assert candidate.mandatory_passed is True
    assert candidate.rejection_codes == ()
    assert isclose(candidate.quality.feature("formation"), 0.62, abs_tol=1e-9)
    assert isclose(candidate.quality.feature("integrity"), 0.8775, abs_tol=1e-9)
    assert isclose(candidate.quality.feature("geometry"), 0.675, abs_tol=1e-9)


def test_interpolation_milestones_match_the_approved_table():
    assert linear(0.30, 0.30, 1.00) == 0.0
    assert linear(1.00, 0.30, 1.00) == 1.0
    assert isclose(linear(0.65, 0.30, 1.00), 0.5, abs_tol=1e-12)
    assert linear(0.50, 0.50, 1.00) == 0.0
    assert isclose(linear(0.75, 0.50, 1.00), 0.5, abs_tol=1e-12)
    assert linear(0.70, 0.70, 0.90) == 0.0
    assert isclose(linear(0.80, 0.70, 0.90), 0.5, abs_tol=1e-12)
    assert linear(0.90, 0.70, 0.90) == 1.0
    assert linear(0.20, 0.30, 1.00) == 0.0
    assert linear(1.20, 0.30, 1.00) == 1.0


def test_geometry_milestones_match_the_approved_table():
    assert width_score(0.35) == 1.0
    assert width_score(1.00) == 0.0
    assert isclose(width_score(0.70), 0.46153846153846156, abs_tol=1e-12)
    assert width_score(0.20) == 1.0
    assert width_score(1.40) == 0.0
    assert isclose(inverse(0.70, 0.35, 1.00), 0.46153846153846156, abs_tol=1e-12)
    assert clamp01(-3) == 0.0 and clamp01(7) == 1.0


def test_rounding_is_single_round_half_up():
    assert round_half_up(10.50) == 11
    assert round_half_up(3.60) == 4
    assert round_half_up(15) == 15
    assert round_half_up(0) == 0
    assert round_half_up(7.5) == 8

    # S=10.50 plus a component that is not rounded first: 4*1 + 7*(1/3) ...
    low = SmcQualityBreakdown(b=0.50, q=0.50, l=0.25, c=0.50)
    assert isclose(low.total, 7.0, abs_tol=1e-12)
    assert low.quality_raw == 7

    # S = 15*0.366 = 5.49 rounds to 5; rounding each component to 0.37 first
    # would give 5.55 -> 6, which the contract forbids.
    third = SmcQualityBreakdown(b=0.366, q=0.366, l=0.366, c=0.366)
    assert isclose(third.total, 5.49, abs_tol=1e-9)
    assert third.quality_raw == 5
    assert round_half_up(4 * 0.37 + 7 * 0.37 + 2 * 0.37 + 2 * 0.37) == 6


# -- Missing data versus absence (tasks 84–87) -------------------------------


def test_no_zone_is_zero_and_core_unavailable_is_null():
    empty = SmcQualityBreakdown.no_zone("NO_VALID_SETUP")
    assert empty.quality_raw == 0 and empty.quality_score == 0.0
    unavailable = SmcQualityBreakdown.data_unavailable("SMC_H4_MISSING")
    assert unavailable.quality_raw is None and unavailable.quality_score is None
    assert empty.quality_raw != unavailable.quality_raw


def test_missing_formation_atr_makes_the_side_data_unavailable():
    """Required formation ATR missing is not an evaluated zero (BQLC §4.1, §7)."""

    zone = _zone(
        departure_measurement={
            "direction": "buy",
            "body_atr": None,
            "body_range": None,
            "directional_close_location": None,
            "atr_before_event": None,
            "status": "unavailable",
            "reason_codes": ["DEPARTURE_ATR_UNAVAILABLE"],
        }
    )
    sets = evaluate_candidate_sets(_context(zone), _technical(), as_of=_AS_OF)

    assert sets["buy"].state == "data_unavailable"
    assert sets["buy"].quality_raw is None
    assert QUALITY_FORMATION_ATR_UNAVAILABLE in sets["buy"].reason_codes
    assert sets["buy"].candidates[0].mandatory_passed is False


def test_core_unavailable_never_produces_a_zero_quality():
    sets = evaluate_candidate_sets(
        _context(_zone()),
        _technical(),
        as_of=_AS_OF,
        core_reason_codes=("SMC_H4_COVERAGE_GAP",),
    )
    assert sets["buy"].state == "data_unavailable"
    assert sets["buy"].quality_raw is None
    assert "SMC_H4_COVERAGE_GAP" in sets["buy"].reason_codes


def test_absent_sweep_is_l_zero_without_renormalization():
    """No related sweep keeps B/Q/C and only L drops (BQLC §5, §8)."""

    without = evaluate_candidate_sets(_context(_zone()), _technical(), as_of=_AS_OF)["buy"]
    zone = _zone(
        linked_sweep_id="sweep-1",
        liquidity_sweep_linked=True,
        linked_sweep_distance_atr=0.10,
        linked_sweep_time_delta=3,
    )
    context = _context(zone)
    context["H4"]["zone_link_sweeps"] = {
        "swept_lows": [
            {
                "sweep_id": "sweep-1",
                "source_pool_id": "pool-1",
                "depth_atr": 0.30,
                "reclaim_bars": 1,
                "owner_setup_id": "smcs-hand-1",
            }
        ]
    }
    with_sweep = evaluate_candidate_sets(context, _technical(), as_of=_AS_OF)["buy"]

    assert without.quality.l == 0.0
    assert QUALITY_NO_RELATED_SWEEP in without.reason_codes
    # depth = linear(.30, .10, .50) = .5 ; reclaim = 1 ; consumed = 1
    expected_l = 1.0 * 1.0 * (0.50 * 0.5 + 0.30 * 1.0 + 0.20 * 1.0)
    assert isclose(with_sweep.quality.l, expected_l, abs_tol=1e-9)
    # B, Q and C are untouched by the sweep evidence.
    assert isclose(with_sweep.quality.b, without.quality.b, abs_tol=1e-12)
    assert isclose(with_sweep.quality.q, without.quality.q, abs_tol=1e-12)
    assert isclose(with_sweep.quality.c, without.quality.c, abs_tol=1e-12)
    assert with_sweep.quality.total > without.quality.total


def test_sweep_outside_the_link_gate_does_not_score():
    zone = _zone(
        linked_sweep_id="sweep-far",
        liquidity_sweep_linked=True,
        linked_sweep_distance_atr=0.90,
        linked_sweep_time_delta=3,
    )
    context = _context(zone)
    context["H4"]["zone_link_sweeps"] = {
        "swept_lows": [
            {
                "sweep_id": "sweep-far",
                "source_pool_id": "pool-1",
                "depth_atr": 0.40,
                "reclaim_bars": 1,
                "owner_setup_id": "smcs-hand-1",
            }
        ]
    }
    side = evaluate_candidate_sets(context, _technical(), as_of=_AS_OF)["buy"]
    assert side.quality.l == 0.0
    assert "SWEEP_LINK_OUT_OF_GATE" in side.reason_codes


def test_second_family_child_does_not_double_count_setup_evidence():
    """OB and FVG children of one setup share B/L/C but keep their own Q (BQLC §8)."""

    fvg = _zone(
        zone_id="smcz-hand-fvg",
        family="fvg",
        type="bullish_fvg",
        original_bounds={"low": 99.0, "high": 100.0},
        remaining_low=99.75,
        remaining_high=100.0,
        fill_status="unfilled",
        fill_ratio=0.5,
        gap_measurement={
            "direction": "buy",
            "gap_low": 99.0,
            "gap_high": 100.0,
            "gap_width": 0.6,
            "minimum_gap": 0.2,
            "accepted": True,
        },
    )
    ob = _zone()
    context = _context(ob)
    context["H4"]["order_blocks"] = [ob]
    context["H4"]["demand_zones"] = []
    context["H4"]["fvg"] = [fvg]

    side = evaluate_candidate_sets(context, _technical(), as_of=_AS_OF)["buy"]
    by_id = {candidate.candidate_id: candidate for candidate in side.candidates}
    ob_candidate = by_id["smcz-hand-1"]
    fvg_candidate = by_id["smcz-hand-fvg"]

    assert isclose(ob_candidate.quality.b, fvg_candidate.quality.b, abs_tol=1e-12)
    assert isclose(ob_candidate.quality.c, fvg_candidate.quality.c, abs_tol=1e-12)
    # The FVG child reads its own remaining ratio: .25/1.00 = .25.
    assert isclose(
        fvg_candidate.quality.feature("family_geometry_score"), 0.25, abs_tol=1e-12
    )
    assert ob_candidate.quality.feature("family_geometry_score") != fvg_candidate.quality.feature(
        "family_geometry_score"
    )
    # One setup, one contribution: the side quality is a single candidate's.
    assert side.quality.quality_raw in {ob_candidate.quality_raw, fvg_candidate.quality_raw}


def test_changing_m15_never_changes_quality_of_the_same_candidate():
    from tests.test_smc_m15_confirmation_task79 import _micro_break_candles, _close_at

    candles = _micro_break_candles()
    as_of = _close_at(candles[-1])
    without = evaluate_candidate_sets(
        _context(_zone()), _technical(), as_of=_AS_OF, m15_candles=None
    )["buy"]
    with_m15 = evaluate_candidate_sets(
        _context(_zone()), _technical(), as_of=_AS_OF, m15_candles=candles, m15_as_of=as_of
    )["buy"]

    assert without.candidates[0].quality.to_dict() == with_m15.candidates[0].quality.to_dict()
    assert without.quality == with_m15.quality


def test_buy_and_sell_are_price_mirrors():
    from tests.test_smc_m15_confirmation_task79 import _ZONE_ID  # noqa: F401

    def mirror_zone(zone):
        mirrored = dict(zone)
        low = zone["original_bounds"]["low"]
        high = zone["original_bounds"]["high"]
        mirrored["direction"] = "sell"
        mirrored["type"] = "bearish_order_block"
        mirrored["original_bounds"] = {"low": 200.0 - high, "high": 200.0 - low}
        mirrored["low"] = 200.0 - high
        mirrored["high"] = 200.0 - low
        measurement = dict(zone["departure_measurement"])
        measurement["direction"] = "sell"
        mirrored["departure_measurement"] = measurement
        return mirrored

    buy_side = evaluate_candidate_sets(
        _context(_zone(), side="buy"), {"price": 99.5, "atr_h4": 2.0}, as_of=_AS_OF
    )["buy"]

    sell_zone = mirror_zone(_zone())
    sell_context = _context(sell_zone, side="sell", structure="LH/LL", displacement="bearish")
    sell_side = evaluate_candidate_sets(
        sell_context, {"price": 100.5, "atr_h4": 2.0}, as_of=_AS_OF
    )["sell"]

    assert buy_side.state == sell_side.state == "evaluated"
    for name in ("b", "q", "l", "c"):
        assert isclose(
            getattr(buy_side.quality, name), getattr(sell_side.quality, name), abs_tol=1e-9
        ), name
    assert buy_side.quality.quality_raw == sell_side.quality.quality_raw


# -- Shared geometry seam (task 89) ------------------------------------------


def test_geometry_seam_owns_the_thresholds_the_planner_uses():
    assert _MAX_ZONE_WIDTH_ATR == MAX_ZONE_WIDTH_ATR == 1.0
    assert _MAX_PROTECTIVE_ZONE_DISTANCE_ATR == HARD_DISTANCE_ATR == 3.0


def test_scorer_and_planner_geometry_gates_agree():
    cases = (
        {"low": 99.0, "high": 100.0, "price": 99.5, "atr": 2.0},
        {"low": 99.0, "high": 103.5, "price": 99.5, "atr": 2.0},   # width 2.25 ATR
        {"low": 90.0, "high": 100.0, "price": 100.5, "atr": 2.0},  # distance 0.25 ATR
        {"low": 99.0, "high": 100.0, "price": 108.0, "atr": 2.0},  # distance 4 ATR
    )
    for case in cases:
        scorer = evaluate_zone_geometry(
            family="ob",
            side="buy",
            original_low=case["low"],
            original_high=case["high"],
            formation_atr=case["atr"],
            execution_atr=case["atr"],
            price=case["price"],
            tick_size=0.1,
        )
        planner = pre_plan_geometry_gate(
            side="buy",
            original_low=case["low"],
            original_high=case["high"],
            formation_atr=case["atr"],
            execution_atr=case["atr"],
            price=case["price"],
            tick_size=0.1,
        )
        assert scorer.within_width_gate == planner.within_width_gate, case
        assert scorer.within_distance_gate == planner.within_distance_gate, case
        assert scorer.plan_eligible == planner.plan_eligible, case


def test_family_geometry_features_use_the_approved_inputs():
    assert isclose(family_geometry_score("ob", base_width=1.0, formation_atr=1.0), 0.0)
    assert isclose(family_geometry_score("ob", base_width=0.35, formation_atr=1.0), 0.65)
    assert isclose(
        family_geometry_score("fvg", remaining_width=0.5, original_width=1.0), 0.5
    )
    assert isclose(
        family_geometry_score(
            "supply_demand", base_width=0.66, average_range=1.0, compression_limit=1.32
        ),
        0.5,
        abs_tol=1e-12,
    )
    # Missing inputs are unavailable, never silently zero.
    assert family_geometry_score("ob", base_width=1.0, formation_atr=None) is None
    assert family_geometry_score("fvg", remaining_width=None, original_width=1.0) is None
    assert (
        family_geometry_score(
            "supply_demand", base_width=0.66, average_range=None, compression_limit=1.32
        )
        is None
    )


def test_invalid_bounds_are_rejected_and_contribute_nothing():
    geometry = evaluate_zone_geometry(
        family="ob",
        side="buy",
        original_low=100.0,
        original_high=99.0,
        formation_atr=2.0,
        execution_atr=2.0,
        price=100.0,
        tick_size=0.1,
    )
    assert geometry.bounds_valid is False
    assert geometry.geometry is None
    assert geometry.plan_eligible is False
    assert "INVALID_ZONE_BOUNDS" in geometry.rejection_codes


# -- Candidate order (task 91) -----------------------------------------------


def _candidate(candidate_id, *, rank, quality, distance, timeframe="H4"):
    return CandidateEvaluation(
        candidate_id=candidate_id,
        zone_id=candidate_id,
        side="buy",
        timeframe=timeframe,
        family="ob",
        confirmation_state="confirmed",
        quality=SmcQualityBreakdown(b=quality, q=quality, l=quality, c=quality),
        distance_atr=distance,
        mandatory_passed=True,
        confirmation_rank=rank,
    )


def test_order_prefers_the_confirmation_group_before_quality():
    confirmed = _candidate("a", rank=0, quality=0.5, distance=0.5)
    waiting = _candidate("b", rank=1, quality=0.9, distance=0.1)
    ordered = order_candidates((waiting, confirmed))
    assert [item.candidate_id for item in ordered] == ["a", "b"]


def test_order_is_quality_then_distance_then_h4_tiebreak_then_id():
    high = _candidate("z", rank=0, quality=0.9, distance=0.9)
    low = _candidate("y", rank=0, quality=0.5, distance=0.1)
    assert [item.candidate_id for item in order_candidates((low, high))] == ["z", "y"]

    near = _candidate("near", rank=0, quality=0.7, distance=0.1)
    far = _candidate("far", rank=0, quality=0.7, distance=0.4)
    assert [item.candidate_id for item in order_candidates((far, near))] == ["near", "far"]

    h4 = _candidate("h4", rank=0, quality=0.7, distance=0.2, timeframe="H4")
    h1 = _candidate("h1", rank=0, quality=0.7, distance=0.2, timeframe="H1")
    assert [item.candidate_id for item in order_candidates((h1, h4))] == ["h4", "h1"]

    first = _candidate("aaa", rank=0, quality=0.7, distance=0.2)
    second = _candidate("bbb", rank=0, quality=0.7, distance=0.2)
    assert [item.candidate_id for item in order_candidates((second, first))] == [
        "aaa",
        "bbb",
    ]


def test_h1_can_beat_h4_when_quality_is_higher():
    h4 = _candidate("h4-weak", rank=0, quality=0.4, distance=0.1, timeframe="H4")
    h1 = _candidate("h1-strong", rank=0, quality=0.9, distance=0.3, timeframe="H1")
    assert [item.candidate_id for item in order_candidates((h4, h1))] == [
        "h1-strong",
        "h4-weak",
    ]


def test_order_is_permutation_invariant_and_skips_hard_rejected():
    a = _candidate("a", rank=0, quality=0.7, distance=0.2)
    b = _candidate("b", rank=1, quality=0.7, distance=0.2)
    rejected = _candidate("z", rank=0, quality=1.0, distance=0.0)
    rejected = CandidateEvaluation(
        candidate_id="z",
        zone_id="z",
        side="buy",
        timeframe="H4",
        family="ob",
        confirmation_state="invalid",
        quality=None,
        mandatory_passed=False,
        rejection_codes=("ZONE_INVALID_OR_EXPIRED",),
        confirmation_rank=3,
    )
    first = order_candidates((a, b, rejected))
    second = order_candidates((rejected, b, a))
    assert [item.candidate_id for item in first] == ["a", "b"]
    assert first == second
    assert candidate_order_key(a) < candidate_order_key(b)


def test_side_quality_follows_the_best_candidate_not_the_first_payload():
    strong = _zone(zone_id="smcz-strong")
    weak = _zone(
        zone_id="smcz-weak",
        age_score=0.3,
        visits=[
            {
                "visit_id": "smcz-weak:visit-1",
                "visit_state": "open",
                "max_penetration_ratio": 0.9,
                "bars_spent_inside": 5,
            }
        ],
    )
    context = _context(strong)
    context["H4"]["demand_zones"] = [weak, strong]
    side = evaluate_candidate_sets(context, _technical(), as_of=_AS_OF)["buy"]

    assert side.candidates[0].candidate_id == "smcz-weak"
    assert side.quality.quality_raw >= evaluate_candidate_sets(
        _context(strong), _technical(), as_of=_AS_OF
    )["buy"].quality.quality_raw
    assert side.quality == max(
        (candidate.quality for candidate in side.candidates if candidate.quality.state == "evaluated"),
        key=lambda quality: quality.total,
    )


def test_candidate_set_ordered_matches_order_candidates():
    a = _candidate("a", rank=0, quality=0.7, distance=0.2)
    b = _candidate("b", rank=1, quality=0.7, distance=0.2)
    candidate_set = SmcCandidateSet(
        side="buy",
        state="evaluated",
        quality=a.quality,
        candidates=(b, a),
    )
    assert candidate_set.ordered == order_candidates((b, a)) == (a, b)


# -- R80-91-01: a hard-rejected candidate never wins quality or order ---------


def _near_zone():
    """Weak BUY OB inside the entry band, quality raw 7, mandatory gate passes."""

    return _zone(
        zone_id="smcz-near",
        original_bounds={"low": 109.0, "high": 110.0},
        low=109.0,
        high=110.0,
        departure_measurement={
            "direction": "buy",
            "body_atr": 0.35,
            "body_range": 0.55,
            "directional_close_location": 0.72,
            "atr_before_event": 2.0,
            "status": "ok",
        },
        visits=[
            {
                "visit_id": "smcz-near:visit-1",
                "visit_state": "completed_reacted",
                "max_penetration_ratio": 0.5,
                "bars_spent_inside": 1,
            }
        ],
        age_score=0.8,
    )


def _far_zone():
    """Good BUY OB far below price: distance 4.75 ATR -> hard distance reject."""

    return _zone(zone_id="smcz-far")


def _two_zone_context():
    context = _context(_near_zone())
    context["H4"]["demand_zones"] = []
    context["H4"]["order_blocks"] = [_far_zone(), _near_zone()]
    context["D1"]["demand_zones"] = []
    context["D1"]["order_blocks"] = [_far_zone()]
    return context


# Hand numbers for the two candidates (same context, so B/L are shared):
# B = .8925, L = 0, C = .15 when the D1 parent does not relate to the child.
# near: formation .35*.0714286 + .25*.10 + .20*.10 + .20*.10 = .09
#       geometry .675, integrity .35*1 + .25*.5 + .20*.8 + .20*.8 = .795
#       Q = .5*.09 + .2*.675 + .3*.795 = .4185 -> S = 3.57 + 2.9295 + .30 = 6.7995 -> raw 7
# far : Q = .70825 -> S = 3.57 + 4.95775 + .30 = 8.82775 .. with the containing D1
#       parent (C = .75) S = 3.57 + 4.95775 + 1.50 = 10.02775 -> raw 10


def test_hard_rejected_candidate_never_wins_side_quality_or_order():
    """R80-91-01: distance 4.75 ATR rejects `far`; `near` owns the side verdict."""

    context = _two_zone_context()
    side = evaluate_candidate_sets(
        context, _technical(price=109.5, atr=2.0), as_of=_AS_OF
    )["buy"]

    by_id = {candidate.candidate_id: candidate for candidate in side.candidates}
    near = by_id["smcz-near"]
    far = by_id["smcz-far"]

    # The rejected candidate really did measure a higher raw quality and fail the
    # mandatory gate only because of its distance.
    assert far.quality is not None and far.quality.quality_raw == 10
    assert far.mandatory_passed is False
    assert "ZONE_BEYOND_HARD_DISTANCE" in far.rejection_codes
    assert isclose(far.distance_atr, 4.75, abs_tol=1e-9)
    assert near.mandatory_passed is True and near.rejection_codes == ()
    assert near.quality.quality_raw == 7

    # Side verdict comes from `near`, never from the rejected `far`.
    assert side.quality.quality_raw == 7
    assert side.quality == near.quality
    assert side.state == "evaluated"
    assert ZONE_WIDTH_TOO_WIDE not in side.reason_codes
    assert far.rejection_codes == ("ZONE_BEYOND_HARD_DISTANCE",)

    # `.ordered` shares order_candidates() semantics: eligible candidates only.
    assert side.ordered == order_candidates(side.candidates) == (near,)
    assert len(side.candidates) == 2, "full history including rejections is kept"

    # Readiness takes the same eligible candidate.
    verdict = evaluate_smc_readiness(side, plan_available=True)
    assert verdict.selected_zone_id == "smcz-near"
    assert verdict.quality_raw == 7


def test_side_with_only_hard_rejected_candidates_reports_no_usable_setup():
    """No eligible candidate: the side never leaks a rejected candidate's raw."""

    context = _context(_far_zone())
    side = evaluate_candidate_sets(
        context, _technical(price=109.5, atr=2.0), as_of=_AS_OF
    )["buy"]

    assert side.candidates[0].mandatory_passed is False
    assert side.candidates[0].quality.quality_raw == 10  # kept for the trace
    assert side.state == "no_zone"
    assert side.quality.state == "no_zone"
    assert side.quality_raw == 0
    assert side.quality.b is None and side.quality.q is None
    assert side.ordered == ()

    verdict = evaluate_smc_readiness(side, plan_available=True)
    assert verdict.status == "OUT_OF_STRATEGY"
    assert verdict.quality_raw == 0
    assert verdict.selected_zone_id is None
