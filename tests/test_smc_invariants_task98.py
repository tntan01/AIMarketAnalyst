"""Task 98 — selection invariants: scale, mirror, duplicates and M15.

* scaling every price (and tick/ATR) by a constant keeps the raw SMC quality and
  the decision, and scales the plan by the same factor;
* the SELL side of a mirrored market is the exact price mirror of the BUY side;
* a duplicated child of the same setup adds no evidence and creates no second
  selected result;
* M15 moves readiness/selection with a stated reason, but never the quality of a
  candidate.

Contract sources: design §12 ("Tính chất"), compatibility spec §2/§3, readiness
spec §9, selection spec §7.
"""

from __future__ import annotations

import copy
import importlib
from fractions import Fraction

from core.smc_geometry import GEOMETRY_WIDTH_TOO_WIDE
from core.smc_quality import evaluate_candidate_sets
from core.smc_selection import select_side_candidate

_COORD = importlib.import_module("tests.test_smc_selection_coordinator_task93")
_CALLER = importlib.import_module("tests.test_smc_canonical_caller_task91")

_AS_OF = _COORD._AS_OF
_MIN_RR = Fraction(2, 1)
_MIRROR = 100.0


def _zone(scale=1.0, *, zid="smcz-scale", low=99.0, high=100.0):
    zone = _COORD._ob(zid, low * scale, high * scale)
    zone["tick_size"] = 0.1 * scale
    zone["departure_measurement"] = dict(
        zone["departure_measurement"], atr_before_event=2.0 * scale
    )
    return zone


def _technical(scale=1.0, *, price=99.5):
    return {
        "price": price * scale,
        "atr_h4": 2.0 * scale,
        "resistance_zones": [{"level": 105.0 * scale}],
        "support_zones": [{"level": 96.0 * scale}],
    }


def _context(zones, scale=1.0):
    """The task93 context with every price (parent included) at the same scale."""

    context = _COORD._context(zones)
    parent = context["D1"]["order_blocks"][0]
    context["D1"]["order_blocks"] = [
        dict(
            parent,
            original_bounds={"low": 90.0 * scale, "high": 110.0 * scale},
            low=90.0 * scale,
            high=110.0 * scale,
            tick_size=0.1 * scale,
            departure_measurement=dict(
                parent["departure_measurement"], atr_before_event=2.0 * scale
            ),
        )
    ]
    return context


def _select(zones, technical, *, min_rr=_MIN_RR, m15_candles=None, as_of=_AS_OF,
            scale=1.0):
    candidate_set = evaluate_candidate_sets(
        _context(zones, scale),
        technical,
        as_of=as_of,
        m15_candles=m15_candles,
        m15_as_of=as_of if m15_candles is not None else None,
    )["buy"]
    return select_side_candidate(candidate_set, technical, min_rr=min_rr)


# -- Price scale ---------------------------------------------------------------


def test_scaling_every_price_keeps_the_quality_and_scales_the_plan():
    baseline = _select([_zone(1.0)], _technical(1.0), scale=1.0)
    scaled = _select([_zone(100.0)], _technical(100.0), scale=100.0)

    assert baseline.selected_quality_raw == scaled.selected_quality_raw == 10
    assert baseline.readiness.status == scaled.readiness.status
    assert baseline.selected_candidate_id == scaled.selected_candidate_id

    for field in (
        "entry",
        "stop_loss",
        "take_profit",
        "entry_zone_low",
        "entry_zone_high",
    ):
        assert getattr(scaled.plan, field) == getattr(baseline.plan, field) * 100.0


def test_scaling_does_not_change_the_decision():
    """The same geometry rejects the same way after a 100x price rescale."""

    baseline = _select([_zone(1.0)], _technical(1.0), scale=1.0)
    scaled = _select([_zone(100.0)], _technical(100.0), scale=100.0)

    assert baseline.state == scaled.state == "evaluated"
    assert baseline.readiness.status == scaled.readiness.status
    assert baseline.selection_reason_codes == scaled.selection_reason_codes


# -- BUY/SELL mirror -----------------------------------------------------------


def _mirror(zone):
    mirrored = copy.deepcopy(zone)
    mirrored["low"] = 2 * _MIRROR - zone["high"]
    mirrored["high"] = 2 * _MIRROR - zone["low"]
    mirrored["original_bounds"] = {
        "low": 2 * _MIRROR - zone["original_bounds"]["high"],
        "high": 2 * _MIRROR - zone["original_bounds"]["low"],
    }
    mirrored["direction"] = "sell"
    mirrored["type"] = "bearish_order_block"
    mirrored["departure_measurement"] = dict(
        zone["departure_measurement"], direction="sell"
    )
    return mirrored


def _sell_selection(zone):
    """SELL side of the mirrored market (mirrored structure, supply zones)."""

    context = _COORD._context([])
    parent = _mirror(_zone(1.0, zid="smcz-mirror-parent", low=90.0, high=110.0))
    for timeframe in ("D1", "H4", "H1"):
        context[timeframe]["demand_zones"] = []
        context[timeframe]["order_blocks"] = []
        context[timeframe]["supply_zones"] = []
        context[timeframe]["structure"] = "LH/LL"
        context[timeframe]["displacement"] = "bearish"
    context["D1"]["supply_zones"] = [parent]
    context["H4"]["supply_zones"] = [zone]
    context["confluence"]["timeframe_evidence"] = {
        timeframe: {"direction": "sell"} for timeframe in ("D1", "H4", "H1")
    }

    technical = _technical(1.0, price=2 * _MIRROR - 99.5)
    technical["resistance_zones"] = [{"level": 2 * _MIRROR - 96.0}]
    technical["support_zones"] = [{"level": 2 * _MIRROR - 105.0}]
    candidate_set = evaluate_candidate_sets(context, technical, as_of=_AS_OF)["sell"]
    return select_side_candidate(candidate_set, technical, min_rr=_MIN_RR)


def test_sell_side_is_the_exact_price_mirror_of_the_buy_side():
    buy = _select([_zone(1.0)], _technical(1.0))

    sell_zone = _mirror(_zone(1.0, zid="smcz-sell"))
    sell_zone["setup_id"] = "smcs-smcz-sell"
    sell = _sell_selection(sell_zone)

    assert buy.selected_quality_raw == sell.selected_quality_raw == 10
    assert sell.plan.direction == "sell"
    assert sell.plan.entry == 2 * _MIRROR - buy.plan.entry
    assert sell.plan.stop_loss == 2 * _MIRROR - buy.plan.stop_loss
    assert sell.plan.take_profit == 2 * _MIRROR - buy.plan.take_profit
    assert (sell.plan.entry_zone_low, sell.plan.entry_zone_high) == (
        2 * _MIRROR - buy.plan.entry_zone_high,
        2 * _MIRROR - buy.plan.entry_zone_low,
    )


# -- Duplicate evidence --------------------------------------------------------


def test_a_duplicated_child_of_the_same_setup_adds_no_evidence():
    single = _select([_zone(1.0)], _technical(1.0))

    duplicate = _zone(1.0, zid="smcz-scale-copy")
    duplicate["setup_id"] = "smcs-smcz-scale"  # same lineage as the original
    doubled = _select([_zone(1.0), duplicate], _technical(1.0))

    assert doubled.selected_quality_raw == single.selected_quality_raw == 10
    assert doubled.selected_zone_id == single.selected_zone_id
    # One selected setup, one plan: the copy never becomes a second result.
    assert doubled.plan is not None
    assert [entry.candidate_id for entry in doubled.alternatives] == [
        "smcz-scale-copy"
    ]
    assert all(entry.plan_available is False for entry in doubled.alternatives)


def test_a_sibling_of_the_same_setup_can_still_be_tried_after_a_rejection():
    """Selection spec §7: child 2 of the SAME setup is a retry, not a new one."""

    blocked = _zone(1.0, zid="smcz-blocked", low=101.0, high=102.0)
    blocked["setup_id"] = "smcs-shared"
    usable = _zone(1.0, zid="smcz-usable")
    usable["setup_id"] = "smcs-shared"

    technical = _technical(1.0, price=101.5)
    selection = _select([blocked, usable], technical, min_rr=Fraction(5, 2))

    assert selection.selected_zone_id == "smcz-usable"
    assert selection.selected_setup_id == "smcs-shared"
    assert [entry.candidate_id for entry in selection.trace] == [
        "smcz-blocked",
        "smcz-usable",
    ]
    assert selection.trace[0].plan_available is False
    assert selection.trace[0].rejection_codes == ("PLAN_MIN_RR",)


def test_the_width_rejection_reason_survives_the_scale_change():
    wide = _zone(1.0, low=90.0, high=100.0)
    wide_scaled = _zone(100.0, low=90.0, high=100.0)

    for scale, zone, technical in (
        (1.0, wide, _technical(1.0)),
        (100.0, wide_scaled, _technical(100.0)),
    ):
        candidate_set = evaluate_candidate_sets(
            _context([zone], scale), technical, as_of=_AS_OF
        )["buy"]
        assert candidate_set.ordered == ()
        assert GEOMETRY_WIDTH_TOO_WIDE in candidate_set.candidates[0].rejection_codes


# -- M15 is readiness, never quality -------------------------------------------


def test_m15_never_changes_the_quality_of_a_candidate():
    zone = _zone(1.0, zid="smcz-m15")
    technical = _technical(1.0)
    window = _CALLER._m15_confirming_zone()

    def candidate_set(as_of, m15):
        return evaluate_candidate_sets(
            _context([zone]),
            technical,
            as_of=as_of,
            m15_candles=m15,
            m15_as_of=as_of if m15 is not None else None,
        )["buy"]

    without = candidate_set(_AS_OF, None)
    confirmed = candidate_set(_CALLER._AS_OF, window)
    moved = candidate_set(_CALLER._AS_OF, _window_that_stops_confirming(window))

    baseline = without.candidates[0]
    assert confirmed.candidates[0].quality_raw == baseline.quality_raw == 10
    assert moved.candidates[0].quality_raw == baseline.quality_raw
    assert (
        confirmed.candidates[0].quality.to_dict()
        == moved.candidates[0].quality.to_dict()
        == baseline.quality.to_dict()
    )
    # ... while the M15 state really did move.
    assert confirmed.candidates[0].m15_status == "confirmed"
    assert moved.candidates[0].m15_status == "waiting"


def test_a_different_m15_can_change_the_selection_with_a_stated_reason():
    """`smcz-high` is the nearest zone, but this window expires its trigger.

    Without M15 both candidates rank 0, so quality/distance pick the nearest
    one; with the window `smcz-confirmed` carries the live trigger (rank 0)
    while `smcz-high` drops to rank 2 (`watch` / expired), so the coordinator
    picks the other zone and the trace states the rank that decided it.
    """

    high_quality = _zone(1.0, zid="smcz-high", low=101.0, high=102.0)
    high_quality["setup_id"] = "smcs-high"
    confirmed_zone = _zone(1.0, zid="smcz-confirmed")
    confirmed_zone["setup_id"] = "smcs-confirmed"

    technical = _technical(1.0, price=101.5)
    window = _CALLER._m15_confirming_zone()

    def candidates(m15_candles):
        return evaluate_candidate_sets(
            _context([high_quality, confirmed_zone]),
            technical,
            as_of=_CALLER._AS_OF if m15_candles is not None else _AS_OF,
            m15_candles=m15_candles,
            m15_as_of=_CALLER._AS_OF if m15_candles is not None else None,
        )["buy"]

    without_set = candidates(None)
    with_set = candidates(window)
    without_m15 = select_side_candidate(without_set, technical, min_rr=_MIN_RR)
    with_m15 = select_side_candidate(with_set, technical, min_rr=_MIN_RR)

    assert without_m15.selected_candidate_id == "smcz-high"
    assert with_m15.selected_candidate_id == "smcz-confirmed"
    # The quality of every candidate is untouched by the M15 swap.
    before = {c.candidate_id: c.quality_raw for c in without_set.candidates}
    after = {c.candidate_id: c.quality_raw for c in with_set.candidates}
    assert before == after == {"smcz-high": 10, "smcz-confirmed": 10}
    # The change is explained by the confirmation rank, not by a score change.
    ranks = {c.candidate_id: c.confirmation_rank for c in with_set.candidates}
    assert ranks["smcz-confirmed"] == 0 < ranks["smcz-high"]
    assert with_m15.trace[0].candidate_id == "smcz-confirmed"


def _window_that_stops_confirming(window):
    """The same window plus 20 bars that run away from the zone."""

    extra = [
        _CALLER._candle(len(window) + index, 106.0, 106.3, 105.9, 106.2)
        for index in range(20)
    ]
    return list(window) + extra
