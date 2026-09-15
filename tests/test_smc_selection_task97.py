"""Task 97 — selection regressions: H1 beats H4, wide H4, next candidate.

Hand-computed expectations (ATR 2.00, formation ATR 2.00, tick 0.10, price
99.50, resistance 105.00, support 96.00):

* full-formation child   : formation .62, geometry .675, integrity .8775
                           -> Q .70825 ; B .8925 ; L 0 ; C .75
                           -> S = 4*.8925 + 7*.70825 + 2*0 + 2*.75 = 10.02775
                           -> raw 10
* floor-formation child  : formation 0 -> Q = .2*.675 + .3*.8775 = .39825
                           -> S = 3.57 + 2.78775 + 1.5 = 7.85775 -> raw 8
* H4 zone 98–100 with ATR 2.00 is exactly 1.00 ATR wide: the width gate passes
  but ``width_score`` is 0, so its geometry is .35 * (1 - 2/2) = 0.
"""

from __future__ import annotations

import importlib
from fractions import Fraction

from core.smc_geometry import GEOMETRY_WIDTH_TOO_WIDE
from core.smc_quality import evaluate_candidate_sets
from core.smc_selection import select_side_candidate

_COORD = importlib.import_module("tests.test_smc_selection_coordinator_task93")

_AS_OF = _COORD._AS_OF
_MIN_RR = Fraction(2, 1)
_TECHNICAL = {
    "price": 99.5,
    "atr_h4": 2.0,
    "resistance_zones": [{"level": 105.0}],
    "support_zones": [{"level": 96.0}],
}


def _child(zid, low, high, *, full_formation=True):
    return _COORD._ob(zid, low, high, full_formation=full_formation)


def _context(h4, h1):
    """H4/H1 children under one wide D1 parent (so C is measurable)."""

    context = _COORD._context([])
    context["H4"]["order_blocks"] = list(h4)
    context["H1"]["order_blocks"] = list(h1)
    return context


def _side(h4, h1, technical=None):
    return evaluate_candidate_sets(
        _context(h4, h1), technical or _TECHNICAL, as_of=_AS_OF
    )["buy"]


# -- H1 can beat H4 ------------------------------------------------------------


def test_h1_selected_when_its_quality_is_higher_than_h4():
    """H4 is not an absolute winner; quality decides first (selection §4.2)."""

    h4 = _child("smcz-h4-wide", 98.0, 100.0)
    h1 = _child("smcz-h1-tight", 98.5, 99.5)
    side = _side([h4], [h1])

    by_id = {candidate.candidate_id: candidate for candidate in side.candidates}
    assert by_id["smcz-h4-wide"].quality_raw == 9
    assert by_id["smcz-h1-tight"].quality_raw == 10
    assert [candidate.candidate_id for candidate in side.ordered] == [
        "smcz-h1-tight",
        "smcz-h4-wide",
    ]

    selection = select_side_candidate(side, _TECHNICAL, min_rr=_MIN_RR)

    assert selection.selected_candidate_id == "smcz-h1-tight"
    assert selection.selected_quality_raw == 10
    assert selection.plan.source == "smc_canonical_zone"
    assert (
        selection.plan.entry,
        selection.plan.stop_loss,
        selection.plan.take_profit,
    ) == (98.5, 96.5, 105.0)
    assert selection.trace[0].candidate_id == "smcz-h1-tight"


def test_equal_quality_resolves_by_distance_and_is_permutation_stable():
    """Same width/quality: the nearer zone is tried first, in any input order."""

    near = _child("smcz-near", 99.0, 100.0)
    far = _child("smcz-far", 97.5, 98.5)
    side = _side([far, near], [])

    by_id = {candidate.candidate_id: candidate for candidate in side.candidates}
    assert by_id["smcz-near"].quality_score == by_id["smcz-far"].quality_score
    assert by_id["smcz-near"].distance_atr == 0.0
    assert by_id["smcz-far"].distance_atr == 0.5
    assert [candidate.candidate_id for candidate in side.ordered] == [
        "smcz-near",
        "smcz-far",
    ]

    shuffled = type(side)(
        side=side.side,
        state=side.state,
        quality=side.quality,
        candidates=tuple(reversed(side.candidates)),
        reason_codes=side.reason_codes,
    )

    assert [c.candidate_id for c in shuffled.ordered] == ["smcz-near", "smcz-far"]
    assert (
        select_side_candidate(shuffled, _TECHNICAL, min_rr=_MIN_RR).selected_candidate_id
        == select_side_candidate(side, _TECHNICAL, min_rr=_MIN_RR).selected_candidate_id
        == "smcz-near"
    )


def test_identical_candidates_fall_back_to_the_stable_id():
    """Nothing but the id separates them, and the id order never flips."""

    first = _child("smcz-tie-a", 99.0, 100.0)
    second = _child("smcz-tie-b", 99.0, 100.0)
    side = _side([second, first], [])

    assert [c.candidate_id for c in side.ordered] == ["smcz-tie-a", "smcz-tie-b"]
    shuffled = type(side)(
        side=side.side,
        state=side.state,
        quality=side.quality,
        candidates=tuple(reversed(side.candidates)),
        reason_codes=side.reason_codes,
    )
    assert [c.candidate_id for c in shuffled.ordered] == ["smcz-tie-a", "smcz-tie-b"]


# -- A rejected H4 must not block the H1 candidate -----------------------------


def test_wide_h4_is_rejected_and_the_h1_child_is_selected():
    wide_h4 = _child("smcz-h4-wide", 90.0, 100.0)
    h1 = _child("smcz-h1-tight", 98.5, 99.5)
    side = _side([wide_h4], [h1])

    by_id = {candidate.candidate_id: candidate for candidate in side.candidates}
    assert by_id["smcz-h4-wide"].mandatory_passed is False
    assert GEOMETRY_WIDTH_TOO_WIDE in by_id["smcz-h4-wide"].rejection_codes
    assert [candidate.candidate_id for candidate in side.ordered] == ["smcz-h1-tight"]

    selection = select_side_candidate(side, _TECHNICAL, min_rr=_MIN_RR)

    assert selection.selected_candidate_id == "smcz-h1-tight"
    assert selection.selected_zone_id == "smcz-h1-tight"
    assert [entry.candidate_id for entry in selection.trace] == ["smcz-h1-tight"]


# -- The next candidate really owns the plan ----------------------------------


def test_the_selected_plan_and_quality_come_from_the_same_next_candidate():
    """`first` raw 10 but R:R 2.0 < 2.5; `second` raw 8 with R:R 3.5."""

    first = _child("smcz-first", 101.0, 102.0)
    second = _child("smcz-second", 98.0, 99.0, full_formation=False)
    # Price sits inside `first` so that candidate is eligible on its own merits.
    technical = dict(_TECHNICAL, price=101.5)
    side = _side([first, second], [], technical)

    selection = select_side_candidate(side, technical, min_rr=Fraction(5, 2))

    assert selection.selected_candidate_id == "smcz-second"
    assert selection.selected_quality_raw == 8
    plan = selection.plan
    assert plan is not None
    assert plan.source == "smc_canonical_zone"
    # The plan is anchored on the SELECTED candidate's own band, not the first
    # candidate's (101–102).
    assert (plan.entry_zone_low, plan.entry_zone_high) == (98.0, 99.0)
    assert (plan.entry, plan.stop_loss, plan.take_profit) == (98.0, 96.0, 105.0)
    assert selection.trace[0].rejection_codes == ("PLAN_MIN_RR",)
    assert [entry.candidate_id for entry in selection.alternatives] == ["smcz-first"]


def test_a_wide_zone_never_reaches_the_plan_stage():
    """The scorer's gate and the planner's gate are the same gate (task 89)."""

    wide = _child("smcz-wide", 90.0, 100.0)
    side = _side([wide], [])

    assert side.ordered == ()
    selection = select_side_candidate(side, _TECHNICAL, min_rr=_MIN_RR)

    assert selection.state == "out_of_strategy"
    assert selection.plan is None
    assert selection.plan_available is False
    assert selection.trace == ()
