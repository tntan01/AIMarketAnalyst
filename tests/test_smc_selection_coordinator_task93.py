"""Task 93 — selection coordinator: try the approved order, keep the reasons.

The coordinator owns the final per-side choice (selection spec §1/§6).  It must
walk the order the scorer produced, keep every rejection reason, never hide a
later valid candidate behind a rejected one, never re-score and never dodge a
blocking gate by trying the next zone.

Hand-computed expectations live in the module docstrings; production helpers are
never used to produce an expected value.
"""

from __future__ import annotations

import importlib
from fractions import Fraction

import pytest

from core.smc_models import CandidateEvaluation, SmcCandidateSet
from core.smc_quality import evaluate_candidate_sets
from core.scanner_scenario_producers import PLAN_MIN_RR, PlanAttempt
from core.smc_selection import (
    EXTERNAL_STATUS_BLOCKED,
    SideSelection,
    finalize_canonical_result,
    select_canonical_sides,
    select_side_candidate,
)
from core.smc_scoring_result import (
    SELECTION_REASON_CORE_UNAVAILABLE,
    SELECTION_REASON_EXTERNAL_BLOCKED,
    SELECTION_REASON_NEXT_CANDIDATE,
    SELECTION_REASON_NO_VALID_SETUP,
    SELECTION_REASON_QUALITY_RANK,
    SELECTION_REASON_WATCH_NO_PLAN,
)

_QUALITY = importlib.import_module("tests.test_smc_quality_task88")

_AS_OF = _QUALITY._AS_OF
_ATR = 2.0
_PRICE = 101.5
_MIN_RR = Fraction(5, 2)


def _parent_zone():
    """Wide D1 parent so both children measure the same containment evidence."""

    return dict(
        _QUALITY._zone(),
        zone_id="smcz-parent",
        setup_id="smcs-parent",
        original_bounds={"low": 90.0, "high": 110.0},
        low=90.0,
        high=110.0,
    )


def _ob(zid: str, low: float, high: float, *, full_formation: bool = True):
    zone = _QUALITY._zone(
        zone_id=zid,
        setup_id=f"smcs-{zid}",
        original_bounds={"low": low, "high": high},
        low=low,
        high=high,
    )
    if not full_formation:
        # Every formation sub-feature at its floor: body/ATR .00 -> 0,
        # body/range .50 -> 0, close-location .70 -> 0.
        zone["departure_measurement"] = {
            "direction": "buy",
            "body_atr": 0.0,
            "body_range": 0.5,
            "directional_close_location": 0.70,
            "atr_before_event": _ATR,
            "status": "ok",
        }
    return zone


def _context(zones):
    return {
        "symbol": "EUR/USD",
        "D1": {
            "structure": "HH/HL",
            "bos": True,
            "displacement": "bullish",
            "order_blocks": [_parent_zone()],
            "fvg": [],
            "demand_zones": [],
            "supply_zones": [],
            "zone_link_sweeps": {},
        },
        "H4": {
            "structure": "HH/HL",
            "bos": True,
            "displacement": "bullish",
            "order_blocks": list(zones),
            "fvg": [],
            "demand_zones": [],
            "supply_zones": [],
            "zone_link_sweeps": {},
        },
        "H1": {
            "structure": "HH/HL",
            "bos": True,
            "displacement": "bullish",
            "order_blocks": [],
            "fvg": [],
            "demand_zones": [],
            "supply_zones": [],
            "zone_link_sweeps": {},
        },
        "confluence": {
            "timeframe_evidence": {
                "D1": {"direction": "buy"},
                "H4": {"direction": "buy"},
                "H1": {"direction": "buy"},
            }
        },
    }


def _technical(*, resistance=(105.0,), support=(96.0,)):
    return {
        "price": _PRICE,
        "atr_h4": _ATR,
        "resistance_zones": [{"level": level} for level in resistance],
        "support_zones": [{"level": level} for level in support],
    }


def _two_candidates_side():
    """`first` raw 10 with R:R 2.0; `second` raw 8 with R:R 3.5.

    first : entry 101 (zone 101–102), SL 99, TP 105 -> reward 4 / risk 2 = 2.0
    second: entry  98 (zone  98– 99), SL 96, TP 105 -> reward 7 / risk 2 = 3.5
    Quality: 4*B + 7*Q + 2*L + 2*C with B .8925, L 0, C .75 for both;
    Q .70825 (formation .62) -> S 10.02775 -> raw 10 for `first`;
    formation 0 -> Q .39825 -> S 7.85775 -> raw 8 for `second`.
    """

    zones = [
        _ob("smcz-first", 101.0, 102.0),
        _ob("smcz-second", 98.0, 99.0, full_formation=False),
    ]
    return evaluate_candidate_sets(
        _context(zones), _technical(), as_of=_AS_OF
    )["buy"]


# -- The approved order is walked, rejections are kept ------------------------


def test_first_candidate_without_a_plan_does_not_hide_the_next_one():
    side = _two_candidates_side()
    assert [candidate.candidate_id for candidate in side.ordered] == [
        "smcz-first",
        "smcz-second",
    ]

    selection = select_side_candidate(side, _technical(), min_rr=_MIN_RR)

    assert selection.state == "evaluated"
    assert selection.selected_candidate_id == "smcz-second"
    assert selection.selected_zone_id == "smcz-second"
    assert selection.selected_setup_id == "smcs-smcz-second"
    assert selection.plan is not None
    assert (selection.plan.entry, selection.plan.stop_loss, selection.plan.take_profit) == (
        98.0,
        96.0,
        105.0,
    )
    # The rejection of the first candidate is preserved, in order.
    assert [entry.candidate_id for entry in selection.trace] == [
        "smcz-first",
        "smcz-second",
    ]
    first, second = selection.trace
    assert first.plan_available is False
    assert first.rejection_codes == (PLAN_MIN_RR,)
    assert second.plan_available is True
    assert selection.selection_reason_codes == (SELECTION_REASON_NEXT_CANDIDATE,)


def test_the_first_candidate_is_reported_when_it_plans():
    side = _two_candidates_side()

    selection = select_side_candidate(side, _technical(), min_rr=Fraction(1, 1))

    assert selection.selected_candidate_id == "smcz-first"
    assert selection.selection_reason_codes == (SELECTION_REASON_QUALITY_RANK,)
    assert [entry.candidate_id for entry in selection.trace] == ["smcz-first"]


def test_selected_quality_lifecycle_and_plan_come_from_one_setup():
    side = _two_candidates_side()

    selection = select_side_candidate(side, _technical(), min_rr=_MIN_RR)
    selected = selection.selected
    assert isinstance(selected, CandidateEvaluation)

    assert selection.selected_quality_raw == selected.quality_raw == 8
    assert selection.selected_zone_id == selected.zone_id
    assert selection.selected_setup_id == selected.setup_id
    assert selection.plan_rejection_codes == ()
    assert selection.trace[-1].quality_raw == selected.quality_raw
    assert selection.trace[-1].zone_id == selected.zone_id


def test_alternatives_only_explain_and_never_carry_a_plan():
    side = _two_candidates_side()

    selection = select_side_candidate(side, _technical(), min_rr=_MIN_RR)

    assert [entry.candidate_id for entry in selection.alternatives] == ["smcz-first"]
    assert all(entry.plan_available is False for entry in selection.alternatives)


def test_quality_is_never_recomputed_by_the_coordinator(monkeypatch):
    """The loop must not call the scorer/evaluator again."""

    from core import smc_selection

    assert "evaluate_candidate_sets" not in dir(smc_selection)
    assert "score_smc" not in dir(smc_selection)

    side = _two_candidates_side()
    before = {c.candidate_id: c.quality_raw for c in side.candidates}
    select_side_candidate(side, _technical(), min_rr=_MIN_RR)
    after = {c.candidate_id: c.quality_raw for c in side.candidates}

    assert before == after == {"smcz-first": 10, "smcz-second": 8}


def test_plan_order_never_depends_on_the_input_list_order():
    side = _two_candidates_side()
    permuted = SmcCandidateSet(
        side=side.side,
        state=side.state,
        quality=side.quality,
        candidates=tuple(reversed(side.candidates)),
        reason_codes=side.reason_codes,
    )

    straight = select_side_candidate(side, _technical(), min_rr=_MIN_RR)
    shuffled = select_side_candidate(permuted, _technical(), min_rr=_MIN_RR)

    assert straight.selected_candidate_id == shuffled.selected_candidate_id
    assert [entry.candidate_id for entry in straight.trace] == [
        entry.candidate_id for entry in shuffled.trace
    ]


# -- The planner seam is the shared one ---------------------------------------


def test_the_coordinator_uses_the_injected_seam_without_its_own_rule():
    calls: list[tuple[str, object]] = []

    def spy(candidate, technical, min_rr=None, snapshot_metadata=None):
        calls.append((candidate.candidate_id, min_rr))
        return PlanAttempt(candidate_id=candidate.candidate_id, zone_id=candidate.zone_id)

    side = _two_candidates_side()
    selection = select_side_candidate(
        side, _technical(), min_rr=_MIN_RR, plan_for=spy
    )

    assert [call[0] for call in calls] == ["smcz-first", "smcz-second"]
    assert selection.state == "watch_zone"
    assert selection.selected_candidate_id == "smcz-first"


def test_the_coordinator_forwards_the_snapshot_metadata_to_the_planner():
    seen: dict[str, object] = {}

    def spy(candidate, technical, min_rr=None, snapshot_metadata=None):
        seen["metadata"] = snapshot_metadata
        return PlanAttempt(candidate_id=candidate.candidate_id, zone_id=candidate.zone_id)

    select_side_candidate(
        _two_candidates_side(),
        _technical(),
        min_rr=_MIN_RR,
        plan_for=spy,
        snapshot_metadata={"symbol": "EURUSD", "as_of": _AS_OF},
    )

    assert seen["metadata"] == {"symbol": "EURUSD", "as_of": _AS_OF}


# -- Special states ------------------------------------------------------------


def test_watch_zone_keeps_its_quality_without_a_plan():
    side = _two_candidates_side()

    selection = select_side_candidate(side, _technical(resistance=()), min_rr=_MIN_RR)

    assert selection.state == "watch_zone"
    assert selection.plan is None
    assert selection.plan_available is False
    assert selection.selected_candidate_id == "smcz-first"
    assert selection.selected_quality_raw == 10
    assert selection.selection_reason_codes == (SELECTION_REASON_WATCH_NO_PLAN,)
    assert selection.readiness.status != "READY_NOW"
    assert selection.readiness.plan_available is False


def test_no_zone_is_an_evaluated_zero_not_a_missing_value():
    side = evaluate_candidate_sets(
        _context([]), _technical(), as_of=_AS_OF
    )["buy"]
    assert side.state == "no_zone"

    selection = select_side_candidate(side, _technical(), min_rr=_MIN_RR)

    assert selection.state == "no_zone"
    assert selection.selected is None
    assert selection.selected_zone_id is None
    assert selection.quality.quality_raw == 0
    assert selection.selection_reason_codes == (SELECTION_REASON_NO_VALID_SETUP,)
    assert selection.readiness.status == "WATCH_ZONE"


def test_missing_core_data_is_unavailable_and_no_candidate_is_attempted():
    side = evaluate_candidate_sets(
        _context([_ob("smcz-first", 101.0, 102.0)]),
        _technical(),
        as_of=_AS_OF,
        core_reason_codes=("SMC_H4_COVERAGE_GAP",),
    )["buy"]
    attempted: list[str] = []

    def spy(candidate, technical, min_rr=None, snapshot_metadata=None):
        attempted.append(candidate.candidate_id)
        return PlanAttempt(candidate_id=candidate.candidate_id, zone_id=candidate.zone_id)

    selection = select_side_candidate(
        side, _technical(), min_rr=_MIN_RR, plan_for=spy
    )

    assert attempted == []
    assert selection.state == "data_unavailable"
    assert selection.selected is None
    assert selection.quality.quality_raw is None
    assert selection.selection_reason_codes == (SELECTION_REASON_CORE_UNAVAILABLE,)
    assert selection.readiness.status == "DATA_UNAVAILABLE"
    assert selection.readiness.quality_raw is None


def test_only_hard_rejected_candidates_are_out_of_strategy():
    wide = _QUALITY._zone(
        zone_id="smcz-wide",
        original_bounds={"low": 90.0, "high": 100.0},
    )
    side = evaluate_candidate_sets(
        _QUALITY._context(wide), _QUALITY._technical(), as_of=_AS_OF
    )["buy"]
    assert side.candidates and side.ordered == ()

    selection = select_side_candidate(side, _QUALITY._technical(), min_rr=_MIN_RR)

    assert selection.state == "out_of_strategy"
    assert selection.selected is None
    assert "SMC_ZONE_INVALID_OR_EXPIRED" in selection.selection_reason_codes


def test_a_blocking_external_gate_stops_the_loop_without_trying_zones():
    side = _two_candidates_side()
    attempted: list[str] = []

    def spy(candidate, technical, min_rr=None, snapshot_metadata=None):
        attempted.append(candidate.candidate_id)
        return PlanAttempt(candidate_id=candidate.candidate_id, zone_id=candidate.zone_id)

    selection = select_side_candidate(
        side,
        _technical(),
        min_rr=_MIN_RR,
        plan_for=spy,
        external_status=EXTERNAL_STATUS_BLOCKED,
        external_reason_codes=("MACRO_BLOCK",),
    )

    assert attempted == []
    assert selection.state == "blocked"
    assert selection.selected is None
    assert selection.selection_reason_codes == (SELECTION_REASON_EXTERNAL_BLOCKED,)
    assert selection.readiness.status == "BLOCKED"
    assert "MACRO_BLOCK" in selection.readiness.reason_codes


def test_an_unusable_shared_snapshot_stops_instead_of_trying_again():
    side = _two_candidates_side()
    broken = _technical()
    broken["atr_h4"] = None
    broken["atr_d1"] = None
    attempted: list[str] = []

    def spy(candidate, technical, min_rr=None, snapshot_metadata=None):
        from core.scanner_scenario_producers import (
            PLAN_SNAPSHOT_UNAVAILABLE,
        )

        attempted.append(candidate.candidate_id)
        return PlanAttempt(
            candidate_id=candidate.candidate_id,
            zone_id=candidate.zone_id,
            rejection_codes=(PLAN_SNAPSHOT_UNAVAILABLE,),
        )

    selection = select_side_candidate(side, broken, min_rr=_MIN_RR, plan_for=spy)

    assert attempted == ["smcz-first"], "the loop stops at the first unusable snapshot"
    assert selection.state == "data_unavailable"
    assert selection.readiness.status == "DATA_UNAVAILABLE"


def test_readiness_describes_the_selected_candidate_not_the_first_ordered_one():
    side = _two_candidates_side()

    selection = select_side_candidate(side, _technical(), min_rr=_MIN_RR)

    assert selection.readiness.selected_zone_id == "smcz-second"
    assert selection.readiness.quality_raw == 8


# -- Both sides and the finalized result --------------------------------------


def test_both_sides_are_selected_and_finalized_into_one_result():
    buy = _two_candidates_side()
    sell = evaluate_candidate_sets(
        _context([]), _technical(), as_of=_AS_OF
    )["sell"]

    selections = select_canonical_sides(
        {"buy": buy, "sell": sell}, _technical(), min_rr=_MIN_RR
    )
    result = finalize_canonical_result(selections)

    assert set(result.sides) == {"buy", "sell"}
    buy_selection = result.side("buy").selection
    sell_selection = result.side("sell").selection
    assert buy_selection.selected_candidate_id == "smcz-second"
    assert buy_selection.plan_available is True
    assert sell_selection.selected_candidate_id is None
    assert sell_selection.quality_raw == 0
    assert sell_selection.plan_available is False


def test_coordinator_rejects_a_non_candidate_set():
    with pytest.raises(ValueError):
        select_side_candidate({"buy": {}}, _technical(), min_rr=_MIN_RR)


def test_side_selection_is_not_a_second_selected_result():
    """Alternatives/trace are explanation data, never a plan or a zone source."""

    side = _two_candidates_side()
    selection = select_side_candidate(side, _technical(), min_rr=_MIN_RR)

    assert isinstance(selection, SideSelection)
    assert all(entry.plan_available is False for entry in selection.alternatives)
    assert selection.plan is not None
    assert selection.plan.direction == "buy"
    assert [entry.candidate_id for entry in selection.trace] == [
        "smcz-first",
        "smcz-second",
    ]
