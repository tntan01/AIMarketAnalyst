"""Checkpoint-A acceptance cases for the gate72 fixture and contract audit.

These cases deliberately record the expected contract before F02-F10 core
changes.  The RED cases are not skipped or xfailed; they are the acceptance
ledger for the findings that remain with the implementation owner.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.market_models import Candle, candle_close_at, validate_smc_candles
from core.smc_confluence import build_d1_reaction_evidence
from core.smc_context import (
    _attach_zone_sweep_links,
    _smc_for_timeframe,
    atr_reference_before_event,
    atr_value_before_event,
    confirm_order_block_candidate,
    detect_liquidity_pools,
    detect_liquidity_sweeps,
    detect_order_block_candidates,
    enrich_zones,
    external_swing_points,
    internal_swing_points,
    measure_departure,
)
from core.smc_lifecycle import analyze_zone_lifecycle, update_fvg_fill
from core.smc_models import SmcZone
from core.smc_structure_replay import replay_smc_structure
from core.smc_sweep_linking import assign_sweep_ownership, associate_sweeps_to_zones


ROOT = Path(__file__).resolve().parents[1]
PROBE_PATH = ROOT / "docs" / "plans" / "probes" / "test_smc_gate72_review.py"
GATE56_PATH = ROOT / "tests" / "test_smc_gate56_review_regressions.py"
_probe_spec = importlib.util.spec_from_file_location("gate72_review_probe", PROBE_PATH)
assert _probe_spec and _probe_spec.loader
_probe = importlib.util.module_from_spec(_probe_spec)
_probe_spec.loader.exec_module(_probe)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _metadata_item(side="buy", **overrides):
    item = dict(
        zone_id="zone",
        type="bullish_ob" if side == "buy" else "bearish_ob",
        family="ob",
        direction=side,
        origin_index=0,
        departure_end_index=0,
        low=100,
        high=110,
        available_at=_probe.stamp(1),
        atr_current=1,
        lifecycle_status="confirmed",
        usable=True,
    )
    item.update(overrides)
    return item


def _metadata_result(item, *, values=None, tick_size=None):
    values = values or _probe.candles(
        [(112, 114, 111, 113), (100, 101, 99.95, 99.98)]
    )
    kwargs = {} if tick_size is None else {"tick_size": tick_size}
    return enrich_zones(
        [item], values, "ob", {}, {"status": "unknown"},
        timeframe="H1", **kwargs,
    )[0]


def _terminal_candles(side, reaction_index):
    if side == "buy":
        rows = [(112, 114, 111, 113)] * 23
        rows[19] = (109, 110, 105, 109)
        # A3-024: the exit candle must leave the widened zone (tolerance
        # max(1*tick, 0.05*ATR) = 0.1 for the consuming zone [100, 110], tick 0.1, ATR 1)
        # without reaching the 0.25*ATR displacement that would make it a reaction.
        zone_high, tick, atr = 110.0, 0.1, 1.0
        exit_row = (110.2, 110.22, 110.15, 110.2)
        assert exit_row[2] > zone_high + max(1 * tick, 0.05 * atr)
        assert exit_row[3] - zone_high < 0.25 * atr
        rows[20:23] = [exit_row] * 3
        # A3-025: the reaction candle is valid OHLC and clears the follow-through rule for
        # BUY (close >= zone_high + 0.25*ATR = 110.25) at the same zone/tick/ATR, so the
        # reacting cases do not pass merely because the validator accepted the rows.
        reaction_row = (112, 114, 111, 113)
        assert reaction_row[1] >= max(reaction_row[0], reaction_row[3])
        assert reaction_row[2] <= min(reaction_row[0], reaction_row[3])
        assert reaction_row[3] >= zone_high + 0.25 * atr
        rows[reaction_index] = reaction_row
    else:
        rows = [(98, 99, 96, 97)] * 23
        rows[19] = (101, 105, 99, 102)
        # A3-026: the exit and reaction rows are the exact mirror of the BUY rows around
        # 210 — (o, h, l, c) -> (210-o, 210-l, 210-h, 210-c) — so they carry the same exit
        # and reaction meaning below the zone [100, 110] (tolerance 0.1, reaction 0.25*ATR).
        def mirror(row):
            open_, high, low, close = row
            return (210 - open_, 210 - low, 210 - high, 210 - close)

        exit_row = (99.8, 99.85, 99.78, 99.8)
        reaction_row = (98, 99, 96, 97)
        assert exit_row == mirror((110.2, 110.22, 110.15, 110.2))
        assert reaction_row == mirror((112, 114, 111, 113))

        zone_low, tick, atr = 100.0, 0.1, 1.0
        assert exit_row[1] < zone_low - max(1 * tick, 0.05 * atr)
        assert zone_low - exit_row[3] < 0.25 * atr
        assert reaction_row[1] >= max(reaction_row[0], reaction_row[3])
        assert reaction_row[2] <= min(reaction_row[0], reaction_row[3])
        assert reaction_row[3] <= zone_low - 0.25 * atr
        rows[20:23] = [exit_row] * 3
        rows[reaction_index] = reaction_row
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    values = [
        Candle(
            time=start + timedelta(days=index),
            open=open_, high=high, low=low, close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    assert not validate_smc_candles(values, "D1")
    return values


def _h4_terminal_candles(side, reaction_index):
    """H4 counterpart of `_terminal_candles` (A3-033 timeline): lifetime is 30 bars.

    Touch at index 29, exit at index 30, terminal at index 31 and one candle after it at
    index 32, with H4 cadence (4h per candle).
    """

    zone_low, zone_high, tick, atr = 100.0, 110.0, 0.1, 1.0
    tolerance = max(1 * tick, 0.05 * atr)
    if side == "buy":
        rows = [(112, 114, 111, 113)] * 33
        rows[29] = (109, 110, 105, 109)
        exit_row = (110.2, 110.22, 110.15, 110.2)
        assert exit_row[2] > zone_high + tolerance
        assert exit_row[3] - zone_high < 0.25 * atr
        reaction_row = (112, 114, 111, 113)
        assert reaction_row[3] >= zone_high + 0.25 * atr
    else:
        rows = [(98, 99, 96, 97)] * 33
        rows[29] = (101, 105, 99, 102)
        exit_row = (99.8, 99.85, 99.78, 99.8)
        assert exit_row[1] < zone_low - tolerance
        assert zone_low - exit_row[3] < 0.25 * atr
        reaction_row = (98, 99, 96, 97)
        assert reaction_row[3] <= zone_low - 0.25 * atr
    rows[30:33] = [exit_row] * 3
    rows[reaction_index] = reaction_row

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    values = [
        Candle(
            time=start + timedelta(hours=4 * index),
            open=open_, high=high, low=low, close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    assert values[1].time - values[0].time == timedelta(hours=4)
    assert not validate_smc_candles(values, "H4")
    return values


def _h4_terminal_lifecycle(side, reaction_index, candles=None):
    return analyze_zone_lifecycle(
        candles=candles if candles is not None else _h4_terminal_candles(side, reaction_index),
        low=100,
        high=110,
        side=side,
        origin_index=0,
        departure_end_index=0,
        zone_id="h4-terminal-zone",
        timeframe="H4",
        tf_minutes=240,
        tick_size=0.1,
        atr_current=1,
    )


def _terminal_lifecycle(side, reaction_index, candles=None):
    return analyze_zone_lifecycle(
        candles=candles if candles is not None else _terminal_candles(side, reaction_index),
        low=100,
        high=110,
        side=side,
        origin_index=0,
        departure_end_index=0,
        zone_id="terminal-zone",
        timeframe="D1",
        tf_minutes=1440,
        tick_size=0.1,
        atr_current=1,
    )


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_01_acceptance_source_must_be_usable_at_sweep_close(side):
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (110, 111, 99.5, 100.1)
    source = dict(
        level=100 if side == "buy" else 110,
        index=0,
        swing_id="source",
        confirmed=True,
        usable=True,
        provisional=False,
        pivot_time=_probe.stamp(0),
        confirmed_at=_probe.stamp(6),
    )
    swings = {
        "highs": [] if side == "buy" else [source],
        "lows": [source] if side == "buy" else [],
    }
    values = _probe.candles(rows, side)
    pools = detect_liquidity_pools(values, swings, tick_size=0.1, atr_value=1)
    result = detect_liquidity_sweeps(
        values,
        swings,
        timeframe="H1",
        tick_size=0.1,
        atr_value=1,
        causal_only=True,
        lookback_bars=8,
        liquidity_pools=pools,
    )
    events = result["swept_lows" if side == "buy" else "swept_highs"]
    assert not events


def test_r72_02_acceptance_context_ranks_all_eligible_claims_by_causal_time():
    early = _probe.zone("early-child", "early", 13, 105.2, 106)
    late = _probe.zone("late-child", "late", 15, 100, 110)
    sweeps = _probe.sweep()
    _probe.attach([early, late], sweeps)
    assert sweeps["swept_lows"][0]["owner_setup_id"] == "early"


def test_r72_02_context_owner_follows_claim_time_under_input_permutation():
    """A3-069: the context caller enumerates, assigns and projects the earliest claim.

    Two eligible zones claim the same sweep: `early` (available at hour 13, farther away) and
    `late` (hour 15, nearer). `_attach_zone_sweep_links` must project the same assignment in both
    input orders, and that assignment must be the earliest claim rather than the nearest zone. The
    assertions read the projected sweep event itself, so this covers the caller's
    enumerate → assign → project chain and not only the ownership helper.
    """

    def context_event(zones):
        sweeps = _probe.sweep()
        _probe.attach(zones, sweeps)
        return sweeps["swept_lows"][0]

    early_zone = _probe.zone("early-child", "early", 13, 105.2, 106)
    late_zone = _probe.zone("late-child", "late", 15, 100, 110)
    forward = context_event([early_zone, late_zone])
    reverse = context_event([late_zone, early_zone])

    # The caller really projects an assignment onto the sweep event, in both orders.
    for event in (forward, reverse):
        assert event["owner_setup_id"]
        assert event["assignment_id"]
        assert event["consumed"] is True
        assert event["contribution_applied"] is True

    # Permutation must not change the projected assignment: identity is causal, not positional.
    assert reverse["owner_setup_id"] == forward["owner_setup_id"]
    assert reverse["assignment_id"] == forward["assignment_id"]
    assert reverse["linked_zone_id"] == forward["linked_zone_id"]
    assert reverse["claim_eligible_at"] == forward["claim_eligible_at"]

    # The winning owner is the earliest claim (A-D02), not the nearest zone, and the projected
    # claim time is that owner's availability.
    assert forward["owner_setup_id"] == "early"
    assert forward["linked_zone_id"] == "early-child"
    assert forward["claim_eligible_at"] == _probe.stamp(13)


def test_r72_02_opposite_side_claim_cannot_own_a_sweep():
    """A3-070: an opposite-side claim is rejected even when it is nearer, and the eligible
    same-side claim still wins.

    The wrong-side zone is a supply zone sitting on the swept low (a smaller price gap than the
    eligible demand zone 0.2 ATR away), so only the side rule can reject it. The link layer must
    skip it and the context caller must project the same-side owner in both input orders.
    """

    def context_event(zones):
        sweeps = _probe.sweep()
        _probe.attach(zones, sweeps)
        return sweeps["swept_lows"][0]

    def build_zones():
        wrong_side = dict(
            _probe.zone("wrong-side-child", "wrong-side", 13, 104.95, 105.05),
            type="supply_zone", direction="sell",
        )
        eligible = dict(
            _probe.zone("right-side-child", "right-side", 15, 105.2, 106),
            type="demand_zone", direction="buy",
        )
        return wrong_side, eligible

    wrong_side, eligible = build_zones()
    sweep_side = _probe.sweep()["swept_lows"][0]["side"]
    assert sweep_side == "buy"
    assert wrong_side["direction"] != sweep_side
    # Fixture geometry: the wrong-side zone is the nearer one, so price cannot be the reason it
    # is rejected (gap 0.05 vs 0.2 at ATR 1.0).
    assert abs(105.05 - 105.0) < (105.2 - 105.0)

    # Link layer: only the same-side zone links, with the fixture-derived distance.
    links = associate_sweeps_to_zones([wrong_side, eligible], _probe.sweep(), atr_value=1.0)
    assert list(links) == [eligible["zone_id"]]
    assert links[eligible["zone_id"]].distance_atr == pytest.approx(0.2)

    # Context caller: same projected owner and no link for the wrong-side zone, both orders.
    for zones in ([wrong_side, eligible], [eligible, wrong_side]):
        event = context_event(zones)
        assert event["owner_setup_id"] == "right-side"
        assert event["linked_zone_id"] == "right-side-child"
        by_id = {zone["zone_id"]: zone for zone in zones}
        assert by_id["wrong-side-child"]["liquidity_sweep_linked"] is False
        assert by_id["wrong-side-child"]["linked_sweep_id"] is None
        assert by_id["right-side-child"]["liquidity_sweep_linked"] is True
        assert by_id["right-side-child"]["linked_sweep_setup_id"] == "right-side"


def test_r72_02_claim_outside_distance_boundary_cannot_own_a_sweep():
    """A3-071: the sweep→zone distance boundary is inclusive and out-of-range claims lose.

    With sweep level 105 and ATR 1.0 the approved tolerance is 0.25 ATR, so there are three cases:
    the level inside the band (distance 0), a band edge exactly 0.25 away, and anything beyond it.

    The context caller derives its own ATR from the candle input it receives, so the context part of
    this case uses local fixture rows whose true range is 1.0 on every bar: the Wilder average of a
    constant true range is that same constant, hence caller ATR 1.0 and the caller's 0.25-ATR
    tolerance is the same 0.25 price gap as the helper control. A caller that used a different ATR
    would make the out-of-range zone eligible (0.26 / 2.0 = 0.13 ATR), so the standalone eligibility
    assertions below, not the pair ordering, are what pin the distance boundary down.
    """

    # Local candle input for the caller: TR = max(1.0, 0.5, 0.5) = 1.0 on every bar, so the
    # fixture-derived ATR is exactly 1.0 without reading any production value.
    context_rows = [(120.0, 120.5, 119.5, 120.0)] * 20
    fixture_atr = 1.0
    for open_, high, low, close in context_rows:
        assert max(high - low, abs(high - close), abs(low - close)) == fixture_atr

    def context_attach(zones):
        sweeps = _probe.sweep()
        _attach_zone_sweep_links(
            (("demand", zones),),
            sweeps,
            candles=_probe.candles(context_rows),
            symbol="EURUSD",
            timeframe="H1",
            tf_minutes=60,
        )
        return sweeps

    def link_for(bounds):
        zone = _probe.zone(f"distance-{bounds[0]}-{bounds[1]}", "distance", 15, *bounds)
        links = associate_sweeps_to_zones([zone], _probe.sweep(), atr_value=fixture_atr)
        return links.get(zone["zone_id"])

    # Helper control, explicit ATR: level 105 sits inside this band, so the price distance is zero.
    inside = link_for((104.0, 106.0))
    assert inside is not None
    assert inside.distance_atr == 0.0

    # Exactly at the approved boundary: a 0.25 ATR gap is still eligible.
    exact = link_for((105.25, 106.0))
    assert exact is not None
    assert exact.distance_atr == pytest.approx(0.25)

    # Beyond the boundary: no link at all (fail closed, no claim).
    assert link_for((105.26, 106.0)) is None

    # Same three zones one at a time through the caller, so each zone's eligibility and its
    # distance are proved against the caller's own ATR before the two zones are combined. An
    # eligible zone must be linked on its own payload *and* own the projected sweep event; the
    # out-of-range zone must do neither.
    def sole_event(zone_id, setup_id, low, high):
        zone = _probe.zone(zone_id, setup_id, 15, low, high)
        event = context_attach([zone])["swept_lows"][0]
        return zone, event

    inside_zone, inside_event = sole_event("inside-child", "inside", 104.0, 106.0)
    assert inside_zone["liquidity_sweep_linked"] is True
    assert inside_zone["linked_sweep_distance_atr"] == pytest.approx(0.0 / fixture_atr)
    assert inside_event["linked_zone_id"] == "inside-child"
    assert inside_event["owner_setup_id"] == "inside"
    assert inside_event["consumed"] is True

    exact_zone, exact_event = sole_event("exact-child", "exact", 105.25, 106.0)
    assert exact_zone["liquidity_sweep_linked"] is True
    assert exact_zone["linked_sweep_distance_atr"] == pytest.approx(0.25 / fixture_atr)
    assert exact_event["linked_zone_id"] == "exact-child"
    assert exact_event["owner_setup_id"] == "exact"
    assert exact_event["consumed"] is True

    outside_zone, outside_event = sole_event("outside-child", "outside", 105.26, 106.0)
    assert outside_zone["liquidity_sweep_linked"] is False
    assert outside_zone["linked_sweep_id"] is None
    assert outside_event["consumed"] is False
    assert outside_event["linked_zone_id"] is None
    assert "owner_setup_id" not in outside_event

    # Context (A3-071/c): the earlier out-of-range zone cannot win; the in-range zone owns the
    # sweep in both input orders. Each order gets a freshly built pair so neither run inherits a
    # link payload from the other, and the out-of-range zone is available *earlier*, so only the
    # distance rule can keep it from taking ownership.
    def build_pair():
        outside_early = _probe.zone("outside-early-child", "outside-early", 13, 105.26, 106.0)
        inside_late = _probe.zone("inside-late-child", "inside-late", 15, 104.0, 106.0)
        assert outside_early["available_at"] < inside_late["available_at"]
        return [outside_early, inside_late]

    events = []
    for zones in (build_pair(), build_pair()[::-1]):
        event = context_attach(zones)["swept_lows"][0]
        events.append(event)
        by_id = {zone["zone_id"]: zone for zone in zones}
        inside_zone = by_id["inside-late-child"]
        outside_zone = by_id["outside-early-child"]
        # The in-range zone is linked and is the projected owner of the sweep.
        assert inside_zone["liquidity_sweep_linked"] is True
        assert inside_zone["sweep_owner_setup_id"] == "inside-late"
        assert event["consumed"] is True
        assert event["owner_setup_id"] == "inside-late"
        assert event["linked_zone_id"] == "inside-late-child"
        # The earlier out-of-range zone takes no link, no owner and no assignment.
        assert outside_zone["liquidity_sweep_linked"] is False
        assert outside_zone["linked_sweep_id"] is None
        assert "sweep_owner_setup_id" not in outside_zone
        assert "sweep_assignment_id" not in outside_zone

    # Input order must not change the projected assignment.
    assert events[1]["owner_setup_id"] == events[0]["owner_setup_id"]
    assert events[1]["assignment_id"] == events[0]["assignment_id"]
    assert events[1]["linked_zone_id"] == events[0]["linked_zone_id"]
    assert events[1]["claim_eligible_at"] == events[0]["claim_eligible_at"]


def test_r72_02_claim_outside_time_window_cannot_own_a_sweep():
    """A3-072: the sweep→zone time window boundary is inclusive and out-of-window claims lose.

    With the sweep at index 10 and an explicit `max_time_bars=3`, the distance from the zone's
    formation start to the sweep is 2 (inside), 3 (exactly at the window) and 4 (outside). The
    window is the approved `max_time_bars` parameter, not a value tuned for this test. A zone whose
    formation/departure window ends before the sweep is also rejected, and at the context level
    such a zone cannot own the sweep even when it becomes available earlier.
    """

    def zone(zone_id, setup_id, available_hour, formation_start, departure_end):
        value = _probe.zone(zone_id, setup_id, available_hour, 104.0, 106.0)
        value.update(
            formation_start_index=formation_start, departure_end_index=departure_end,
        )
        return value

    def linked(zone_value):
        links = associate_sweeps_to_zones(
            [zone_value], _probe.sweep(), atr_value=1.0, max_time_bars=3,
        )
        return links.get(zone_value["zone_id"])

    sweep_index = _probe.sweep()["swept_lows"][0]["index"]
    assert sweep_index == 10
    window = 3
    assert sweep_index - 8 == 2 and sweep_index - 7 == window and sweep_index - 6 > window

    inside = linked(zone("inside-child", "inside", 15, 8, 12))
    assert inside is not None
    assert inside.distance_atr == 0.0

    # Exactly at the window boundary (delta == max_time_bars) is still eligible.
    boundary = linked(zone("boundary-child", "boundary", 15, 7, 12))
    assert boundary is not None

    # One bar beyond the window is rejected.
    assert linked(zone("outside-child", "outside", 15, 6, 12)) is None

    # A formation/departure window that ends before the sweep is rejected too.
    assert linked(zone("window-before-child", "window-before", 15, 0, 9)) is None

    # Context (default window): the earlier out-of-window zone cannot win; the in-window zone owns
    # the sweep in both input orders.
    window_before_early = zone("window-before-child", "window-before", 13, 0, 9)
    in_window_late = zone("in-window-child", "in-window", 15, 8, 12)
    assert window_before_early["available_at"] < in_window_late["available_at"]
    for zones in ([window_before_early, in_window_late], [in_window_late, window_before_early]):
        sweeps = _probe.sweep()
        _probe.attach(zones, sweeps)
        event = sweeps["swept_lows"][0]
        assert event["owner_setup_id"] == "in-window"
        assert event["linked_zone_id"] == "in-window-child"
        by_id = {zone_value["zone_id"]: zone_value for zone_value in zones}
        assert by_id["window-before-child"]["liquidity_sweep_linked"] is False
        assert by_id["in-window-child"]["liquidity_sweep_linked"] is True


def test_r72_02_context_same_time_tie_follows_stable_setup_id():
    """A3-073: with equal claim times the context caller must break the tie by stable setup ID.

    Two zones become available at the same hour and both link the same sweep, so they really tie.
    `alpha-setup` owns the smaller setup ID while `a-loser-child` owns the smaller zone ID, which
    makes a zone-ID based tie-break detectable. The helper-level tie-break is already covered by
    `test_r72_02_same_time_tie_is_stable_under_claim_permutation`; this node records the context
    caller's behaviour for the same input in both orders.
    """

    def context_event(swap=False):
        pair = [
            _probe.zone("z-winner-child", "alpha-setup", 13, 104.2, 105.2),
            _probe.zone("a-loser-child", "beta-setup", 13, 104.2, 105.2),
        ]
        if swap:
            pair.reverse()
        sweeps = _probe.sweep()
        _probe.attach(pair, sweeps)
        return sweeps["swept_lows"][0], pair

    reference = _probe.zone("z-winner-child", "alpha-setup", 13, 104.2, 105.2)
    rival = _probe.zone("a-loser-child", "beta-setup", 13, 104.2, 105.2)

    # Fixture: equal claim times, and the two candidate tie-break fields point at different zones.
    assert reference["available_at"] == rival["available_at"] == _probe.stamp(13)
    assert reference["setup_id"] < rival["setup_id"]
    assert rival["zone_id"] < reference["zone_id"]

    # Both zones qualify on their own (same side, distance and window), so the pair is a real tie
    # and the one-to-one sweep link has to choose between them.
    for zone_value in (reference, rival):
        single = associate_sweeps_to_zones([zone_value], _probe.sweep(), atr_value=1.0)
        assert list(single) == [zone_value["zone_id"]]

    forward, forward_zones = context_event()
    reverse, reverse_zones = context_event(swap=True)
    # The link is one-to-one: exactly one of the tied zones carries it, in either order.
    assert [zone["liquidity_sweep_linked"] for zone in forward_zones].count(True) == 1
    assert [zone["liquidity_sweep_linked"] for zone in reverse_zones].count(True) == 1

    # Input order must not decide, and the projected claim time is the shared availability.
    assert reverse["owner_setup_id"] == forward["owner_setup_id"]
    assert reverse["linked_zone_id"] == forward["linked_zone_id"]
    assert reverse["assignment_id"] == forward["assignment_id"]
    assert forward["claim_eligible_at"] == _probe.stamp(13)

    # The approved rule: the stable setup ID decides the tie.
    assert forward["owner_setup_id"] == "alpha-setup"
    assert forward["linked_zone_id"] == "z-winner-child"


def test_r72_03_acceptance_contribution_is_selected_within_owner_children():
    # Canonical callers declare the history window explicitly instead of leaning on
    # the helper default (A3-006): this fixture has complete history.
    claims = [
        _probe.claim("early", "z-owner", 13),
        _probe.claim("late", "a-nonowner", 15),
    ]
    # A3-075: the non-owner child carries the smaller zone ID, so it must not take the
    # contribution slot away from the owner's own child.
    assert "a-nonowner" < "z-owner"
    result = assign_sweep_ownership(claims, history_complete=True)
    owner_claim = next(c for c in result["claims"] if c["setup_id"] == "early")
    non_owner_claim = next(c for c in result["claims"] if c["setup_id"] == "late")
    assert result["assignments"]["sweep"]["owner_setup_id"] == "early"
    assert non_owner_claim["contribution_applied"] is False
    assert owner_claim["contribution_applied"] is True
    assert sum(c["contribution_applied"] for c in result["claims"]) == 1
    assert next(c for c in result["claims"] if c["contribution_applied"])["setup_id"] == "early"


def test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay():
    sweeps = _probe.sweep()
    _probe.attach([_probe.zone("old-child", "original-owner", 13, 100, 110)], sweeps)
    prior = copy.deepcopy(sweeps["swept_lows"][0])
    assert prior["consumed"] is True
    _probe.attach([_probe.zone("new-child", "later-owner", 15, 100, 110)], sweeps)
    event = sweeps["swept_lows"][0]
    assert event["owner_setup_id"] == prior["owner_setup_id"]
    assert event["assignment_id"] == prior["assignment_id"]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_05_acceptance_terminal_d1_lifecycle_cannot_supply_active_reaction(side):
    state = _probe.lifecycle(
        [(112, 114, 111, 113), (109, 110, 105, 109),
         (112, 114, 111, 113), (100, 101, 98, 99)],
        side,
    )
    assert state.lifecycle_broken
    assert state.visits[0].visit_state == "completed_reacted"
    evidence = build_d1_reaction_evidence(
        {"zone_id": "zone", "direction": side},
        state,
        as_of=_probe.stamp(4 * 24),
    )
    assert evidence["valid"] is False
    assert evidence["score"] == 0


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_06_acceptance_reaction_cannot_cross_expiry_boundary(side):
    rows = [(112, 114, 111, 113)] * 22
    rows[19] = (109, 110, 105, 109)
    rows[20] = (110.2, 110.22, 110.15, 110.2)
    rows[21] = (112, 114, 111, 113)
    prefix = _probe.lifecycle(rows[:21], side)
    assert prefix.visits[0].visit_state == "completed_unreacted"
    state = _probe.lifecycle(rows, side)
    assert state.lifecycle_expired and state.expiry_index == 21
    assert state.visits[0].reacted_at is None
    assert state.visits[0].visit_state == "completed_unreacted"


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_07_acceptance_explicit_tick_is_forwarded_to_lifecycle(side):
    values = _probe.candles(
        [(112, 114, 111, 113), (100, 101, 99.95, 99.98)],
        side,
    )
    item = dict(
        zone_id="zone",
        type="bullish_ob" if side == "buy" else "bearish_ob",
        family="ob",
        direction=side,
        origin_index=0,
        departure_end_index=0,
        low=100,
        high=110,
        available_at=_probe.stamp(1),
        atr_current=1,
        lifecycle_status="confirmed",
        usable=True,
    )
    result = enrich_zones(
        [item], values, "ob", {}, {"status": "unknown"},
        timeframe="H1", tick_size=0.1,
    )[0]
    assert result["invalidation_buffer"] == pytest.approx(0.1)
    assert result["lifecycle_broken"] is False


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_08_acceptance_invalidated_projection_is_not_confirmed_usable(side):
    values = _probe.candles([(112, 114, 111, 113), (100, 101, 98, 99)], side)
    item = dict(
        zone_id="zone",
        type="bullish_ob" if side == "buy" else "bearish_ob",
        family="ob",
        direction=side,
        origin_index=0,
        departure_end_index=0,
        low=100,
        high=110,
        available_at=_probe.stamp(1),
        atr_current=1,
        tick_size=0.1,
        lifecycle_status="confirmed",
        usable=True,
    )
    result = enrich_zones(
        [item], values, "ob", {}, {"status": "unknown"}, timeframe="H1",
    )[0]
    assert result["lifecycle_broken"] is True
    assert result["usable"] is False
    assert result["lifecycle_status"] == "invalid"


def test_r72_09_acceptance_corrected_task57_71_positive_fixtures_are_valid():
    factories = [
        ("task59", "tests/test_smc_zone_lifecycle_task59.py", [
            (112, 114, 111, 113), (112, 114, 111, 113),
            (105, 111, 105, 110), (112, 114, 110.2, 110.2),
        ]),
        ("task60", "tests/test_smc_zone_lifecycle_task60.py", [
            (112, 114, 111, 113), (112, 114, 111, 113),
            (105, 111, 105, 108), (112, 113, 110.2, 110.2),
            (111, 112, 110.3, 110.3), (112, 113, 110.5, 110.5),
        ]),
        ("task62", "tests/test_smc_fvg_fill_task62.py", [
            (100, 101, 99, 100), (100, 102, 99, 101),
            (102, 112, 102, 110), (110, 111, 105, 108),
        ]),
        ("task63", "tests/test_smc_zone_lifecycle_task63.py", [
            (112, 114, 111, 113), (112, 114, 111, 113),
            (105, 111, 105, 108), (112, 113, 110.2, 110.2),
        ]),
        ("task65", "tests/test_smc_lifecycle_task65.py", [
            (100, 101, 99, 100), (100, 103, 99.5, 102),
            (102, 112, 102, 110), (110, 111, 105, 108),
        ]),
    ]
    for name, relative_path, rows in factories:
        path = ROOT / relative_path
        spec = importlib.util.spec_from_file_location(f"{name}_fixture", path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        values = module._candles(rows)
        assert not validate_smc_candles(values, "H1"), name


def _pool_records(pools):
    """Return the canonical pool `records` entries of a `detect_liquidity_pools` payload.

    A3-005 fixes the record fields (`pool_id/kind/level/source_ids/sources/usable_at`)
    but leaves the container shape open, so lineage assertions select by source lineage
    and accept either a list of records or a mapping of kind to records.
    """

    raw = pools.get("records")
    if isinstance(raw, dict):
        values = [
            record
            for nested in raw.values()
            for record in (nested if isinstance(nested, list) else [nested])
        ]
    elif isinstance(raw, (list, tuple)):
        values = list(raw)
    else:
        values = []
    return [record for record in values if isinstance(record, dict)]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_01_positive_pool_keeps_source_lineage_and_usable_time(side):
    values = _probe.candles([(112, 114, 111, 113)] * 8, side)
    level_base = 100.0 if side == "buy" else 110.0
    level_offset = 0.05 if side == "buy" else -0.05
    source_a = dict(
        level=level_base,
        index=0,
        swing_id="source-a",
        confirmed=True,
        usable=True,
        provisional=False,
        pivot_time=_probe.stamp(0),
        confirmed_at=_probe.stamp(1),
        usable_at=_probe.stamp(1),
    )
    source_b = dict(source_a, swing_id="source-b", level=level_base + level_offset,
                    index=1, pivot_time=_probe.stamp(1), confirmed_at=_probe.stamp(2),
                    usable_at=_probe.stamp(2))
    numeric_key = "equal_lows" if side == "buy" else "equal_highs"
    swings = (
        {"highs": [], "lows": [source_a, source_b]}
        if side == "buy"
        else {"highs": [source_a, source_b], "lows": []}
    )
    pools = detect_liquidity_pools(values, swings, tick_size=0.1, atr_value=1)

    # Numeric keys stay the legacy projection: one pair-average level, never a dict.
    expected_level = (source_a["level"] + source_b["level"]) / 2.0
    assert pools[numeric_key] == [expected_level]
    assert all(not isinstance(level, dict) for level in pools[numeric_key])

    # Provenance lives in the canonical record, matched by its source lineage.
    matches = [
        record for record in _pool_records(pools)
        if record.get("source_ids") == ["source-a", "source-b"]
    ]
    assert len(matches) == 1
    record = matches[0]
    assert isinstance(record.get("kind"), str) and record["kind"].strip()
    assert isinstance(record.get("pool_id"), str) and record["pool_id"].strip()
    # Max usable time is computed from the fixture sources, not read back from output.
    assert record["usable_at"] == max(
        source["usable_at"] for source in (source_a, source_b)
    )

    # Per-source ID plus confirmed/usable times survive into the record.
    kept_sources = {source["swing_id"]: source for source in record["sources"]}
    assert sorted(kept_sources) == ["source-a", "source-b"]
    for expected_source in (source_a, source_b):
        kept = kept_sources[expected_source["swing_id"]]
        assert kept["confirmed_at"] == expected_source["confirmed_at"]
        assert kept["usable_at"] == expected_source["usable_at"]
        assert kept["provisional"] is False


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_01_canonical_sweep_requires_pool_records_not_numeric_levels(side):
    """Numeric pool levels alone cannot grant a canonical sweep (A3-005 rule 3, R72-01).

    The pool payload carries the legacy numeric level but no canonical `records`, while the
    candles really do excursion beyond that level and reclaim in the same candle, so the
    rejection has to come from the missing provenance — not from missing excursion.
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    level = 100.0 if side == "buy" else 110.0
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (110, 111, 99.5, 100.1)
    values = _probe.candles(rows, side)

    source = dict(
        level=level,
        index=0,
        swing_id="pool-source",
        confirmed=True,
        usable=True,
        provisional=False,
        pivot_time=_probe.stamp(0),
        confirmed_at=_probe.stamp(1),
        usable_at=_probe.stamp(1),
    )
    swings = (
        {"highs": [], "lows": [source]}
        if side == "buy"
        else {"highs": [source], "lows": []}
    )
    numeric_key = "swing_lows" if side == "buy" else "swing_highs"
    swept_key = "swept_lows" if side == "buy" else "swept_highs"
    pools = {
        "swing_lows": [],
        "swing_highs": [],
        "equal_lows": [],
        "equal_highs": [],
        numeric_key: [level],
    }

    # Preconditions: numeric level present, canonical provenance absent.
    assert pools[numeric_key] == [level]
    assert "records" not in pools

    # Preconditions from the fixture geometry: excursion past the level, reclaim in the
    # same candle, so an empty result cannot be blamed on a sweep-less fixture.
    sweep_candle = values[2]
    if side == "buy":
        assert sweep_candle.low < level - excursion
        assert sweep_candle.close > level
    else:
        assert sweep_candle.high > level + excursion
        assert sweep_candle.close < level

    common = dict(
        timeframe="H1", tick_size=tick, atr_value=atr, causal_only=True,
        lookback_bars=8,
    )
    canonical = detect_liquidity_sweeps(
        values, swings, liquidity_pools=pools, **common,
    )
    assert canonical[swept_key] == []
    assert canonical["swept_highs" if side == "buy" else "swept_lows"] == []

    # Control: the same candles/swings do sweep on the legacy adapter path (no pool
    # payload), so the empty canonical result above is provenance-specific.
    legacy = detect_liquidity_sweeps(values, swings, **common)
    assert [sweep["index"] for sweep in legacy[swept_key]] == [2]


_POOL_RECORD_LEVEL = 100.0


def _pool_record_fixture(**overrides):
    """A3-064 fixture: one canonical pool record (A3-005) with optional provenance defects.

    The record matches the swept swing-low level and carries complete source lineage unless an
    override removes one part of it, so each caller can name exactly one missing provenance case.
    """

    record = {
        "pool_id": "pool-swing-low-100",
        "kind": "swing_low",
        "level": _POOL_RECORD_LEVEL,
        "source_ids": ["pool-source"],
        "sources": [
            {
                "swing_id": "pool-source",
                "confirmed_at": _probe.stamp(1),
                "usable_at": _probe.stamp(1),
                "provisional": False,
            }
        ],
        "usable_at": _probe.stamp(1),
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize(
    "defect",
    [
        "record_for_other_level",
        "no_sources",
        "dangling_source_id",
        "source_without_provenance_id",
        "source_without_usable_at",
    ],
)
def test_r72_01_missing_pool_provenance_fails_closed(defect):
    """A3-064: every distinct missing source/provenance case fails closed on its own.

    Each case carries a canonical `records` container whose single record matches the swept level
    with one provenance defect named by `defect` (A3-005 rule 3: a canonical sweep with missing
    records or missing provenance fails closed and never falls back to the numeric level). The
    candles really excursion past the level and reclaim in the same candle and the legacy adapter
    path still sweeps, so the empty canonical result is attributable to the defect alone.
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    level = _POOL_RECORD_LEVEL
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (110, 111, 99.5, 100.1)
    values = _probe.candles(rows, "buy")
    source = dict(
        level=level, index=0, swing_id="pool-source", confirmed=True, usable=True,
        provisional=False, pivot_time=_probe.stamp(0), confirmed_at=_probe.stamp(1),
        usable_at=_probe.stamp(1),
    )
    swings = {"highs": [], "lows": [source]}

    defects = {
        # The records container exists but does not carry the swept level at all.
        "record_for_other_level": {"level": level + 5.0},
        # The record has no lineage: neither source IDs nor source entries.
        "no_sources": {"source_ids": [], "sources": []},
        # The record names a source that is absent from its own `sources` list.
        "dangling_source_id": {"source_ids": ["swing-missing"], "sources": []},
        # The source entry carries no provenance ID.
        "source_without_provenance_id": {
            "source_ids": [],
            "sources": [{"confirmed_at": _probe.stamp(1), "usable_at": _probe.stamp(1)}],
        },
        # The source entry carries no causal usable time.
        "source_without_usable_at": {
            "sources": [{"swing_id": "pool-source", "confirmed_at": _probe.stamp(1)}],
        },
    }
    pools = {
        "swing_lows": [level],
        "swing_highs": [],
        "equal_lows": [],
        "equal_highs": [],
        "records": [_pool_record_fixture(**defects[defect])],
    }

    # Preconditions: the record exists with exactly the named defect, and the numeric projection
    # still lists the level, so an empty result cannot be blamed on a missing level.
    record = pools["records"][0]
    assert pools["swing_lows"] == [level]
    if defect == "record_for_other_level":
        assert record["level"] != level
    elif defect == "no_sources":
        assert record["source_ids"] == [] and record["sources"] == []
    elif defect == "dangling_source_id":
        assert record["source_ids"] and not record["sources"]
    elif defect == "source_without_provenance_id":
        assert record["sources"] and not str(record["sources"][0].get("swing_id") or "").strip()
    else:
        assert record["sources"][0].get("usable_at") is None

    # Preconditions from the fixture geometry: excursion past the level and reclaim in the same
    # candle, so the fixture itself is sweep-capable.
    sweep_candle = values[2]
    assert sweep_candle.low < level - excursion
    assert sweep_candle.close > level

    common = dict(
        timeframe="H1", tick_size=tick, atr_value=atr, causal_only=True, lookback_bars=8,
    )
    canonical = detect_liquidity_sweeps(
        values, swings, liquidity_pools=pools, **common,
    )
    assert canonical["swept_lows"] == []
    assert canonical["swept_highs"] == []

    # Control: the same candles/swings do sweep on the legacy adapter path (no pool payload), so
    # the empty canonical result above is provenance-specific.
    legacy = detect_liquidity_sweeps(values, swings, **common)
    assert [sweep["index"] for sweep in legacy["swept_lows"]] == [2]


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("distance", ["below", "equal", "beyond"])
def test_r72_01_excursion_threshold_is_strict(distance, side):
    """A3-065: the approved excursion rule is strict — equality is not enough, exceeding it is.

    The sweep candle is built from the fixture excursion `max(2*tick, 0.10*ATR)` so its
    penetration is exactly `excursion + slack`, with slack `-0.05` (below), `0.0` (equality) and
    `+0.05` (beyond). Only the positive slack may sweep. In every case the candle reclaims the
    level inside the same candle and the source is confirmed, usable and non-provisional, so the
    outcome is attributable to the threshold rule alone. SELL reuses the same buy-shaped fixture
    mirrored by the probe.
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    slack = {"below": -0.05, "equal": 0.0, "beyond": 0.05}[distance]
    depth = excursion + slack
    base_level = 100.0
    level = base_level if side == "buy" else 210.0 - base_level
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (110, 111, base_level - depth, base_level + 0.1)
    values = _probe.candles(rows, side)
    source = dict(
        level=level, index=0, swing_id="pool-source", confirmed=True, usable=True,
        provisional=False, pivot_time=_probe.stamp(0), confirmed_at=_probe.stamp(1),
        usable_at=_probe.stamp(1),
    )
    if side == "buy":
        swings = {"highs": [], "lows": [source]}
        swept_key, other_key = "swept_lows", "swept_highs"
    else:
        swings = {"highs": [source], "lows": []}
        swept_key, other_key = "swept_highs", "swept_lows"

    # Preconditions from the fixture: the penetration is exactly excursion + slack, and the same
    # candle reclaims the level, so no case can be blamed on missing reclaim.
    candle = values[2]
    if side == "buy":
        assert level - candle.low == pytest.approx(depth)
        assert candle.close > level
    else:
        assert candle.high - level == pytest.approx(depth)
        assert candle.close < level
    assert source["confirmed"] is True and source["usable"] is True
    assert source["provisional"] is False

    result = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=tick, atr_value=atr,
        causal_only=True, lookback_bars=8,
    )
    sweeps = result[swept_key]
    if distance == "beyond":
        assert [sweep["index"] for sweep in sweeps] == [2]
        assert sweeps[0]["level"] == level
        assert sweeps[0]["depth"] == pytest.approx(depth)
        assert sweeps[0]["excursion_buffer"] == pytest.approx(excursion)
        assert sweeps[0]["source_swing_id"] == "pool-source"
    else:
        # Equality is not enough: the approved rule needs the penetration to exceed the buffer.
        assert sweeps == []
    assert result[other_key] == []


# --- A3-066: pool→sweep causal stability across prefix/batch and rolling index ---------------

# The A3-044 fixture (12 bars: confirmed pivot low at index 4, sweep at index 10) plus four
# extension bars that add a confirmed swing high at index 13 and a swept high at index 14.
_POOL_CAUSAL_ROWS = [
    (105, 106, 104, 105),
    (105, 106, 103, 104),
    (104, 105, 102, 103),
    (103, 104, 100.5, 101),
    (101, 102, 99.5, 101.5),
    (101.5, 103, 101, 102.5),
    (102.5, 104, 102, 103.5),
    (103.5, 105, 103, 104.5),
    (104.5, 106, 104, 105.5),
    (105.5, 106, 103, 104),
    (100, 100.6, 99.0, 100.2),
    (104, 105, 103, 104),
    (104.5, 105.0, 104.0, 104.8),
    (104.8, 106.5, 104.6, 106.2),
    (106.2, 106.4, 105.0, 105.2),
    (105.2, 105.6, 104.4, 104.8),
]
_POOL_CAUSAL_CUTOFF_INDEX = 11      # last bar of the prefix; its close is the shared cutoff
_POOL_CAUSAL_PIVOT_INDEX = 4        # confirmed swing low that becomes the pool
_POOL_CAUSAL_SWEEP_INDEX = 10       # bar that sweeps that swing
_POOL_CAUSAL_FUTURE_SWEEP_INDEX = 14  # swept high that only the extension bars create


def _pool_causal_candles(rows, offset=0):
    """Build H1 candles exactly like the probe fixture, optionally shifting the start time.

    `offset` lets a caller drop leading bars while keeping every remaining bar's own timestamp,
    which is what a rolling window does.
    """

    start = datetime.fromisoformat(_probe.stamp(0))
    values = [
        Candle(
            time=start + timedelta(hours=index + offset),
            open=open_, high=high, low=low, close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    assert not validate_smc_candles(values, "H1")
    return values


def _pool_causal_run(values):
    """Run the real producer → pool → sweep chain over one candle series."""

    swings = external_swing_points(
        values, symbol="EURUSD", timeframe="H1", lookback=2, equal_tolerance=0.0,
    )
    pools = detect_liquidity_pools(values, swings, tick_size=0.1, atr_value=1.0)
    sweeps = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=0.1, atr_value=1.0,
        causal_only=True, lookback_bars=len(values), liquidity_pools=pools,
    )
    return swings, pools, sweeps


def _pool_causal_evidence(sweep):
    """Causal fields of a sweep: everything except the positional `index`."""

    return {
        "sweep_id": sweep["sweep_id"],
        "side": sweep["side"],
        "kind": sweep["kind"],
        "level": sweep["level"],
        "time": sweep["time"],
        "occurred_at": sweep["occurred_at"],
        "reclaimed_at": sweep["reclaimed_at"],
        "depth": sweep["depth"],
        "excursion_buffer": sweep["excursion_buffer"],
        "source_swing_id": sweep["source_swing_id"],
        "source_pool_id": sweep["source_pool_id"],
        "sweep_link_version": sweep["sweep_link_version"],
    }


def _reclaimed_by(sweep, cutoff):
    """Whether the sweeping candle has closed at or before `cutoff` (A3-066/a, A3R3-04).

    `time` is the *opening* of the sweeping candle, so an event that merely opens at the cutoff
    has not reclaimed yet and is not evidence the run could have used. The gate is inclusive on
    the close: a reclaim landing exactly on the cutoff is known.
    """

    return sweep["reclaimed_at"] <= cutoff


def _pool_record_for(pools, kind, source_ids):
    """Select the single canonical pool record by kind + sorted source-ID lineage (A3-005).

    Selection is by lineage and kind alone — never by list position, never by the caller's input
    order and never by matching the numeric level projection. `records` is the F06 contract, so a
    payload without it fails here naming what was actually present instead of silently comparing
    nothing.
    """

    wanted = list(source_ids)
    matches = [
        record for record in _pool_records(pools)
        if record.get("kind") == kind and record.get("source_ids") == wanted
    ]
    assert len(matches) == 1, (
        kind, wanted,
        sorted((str(record.get("kind")), str(record.get("source_ids")))
               for record in _pool_records(pools)),
    )
    return matches[0]


def _assert_pool_record_matches_source(record, swing):
    """The canonical record keeps the fixture source's identity and times (A3-005, A3-066/b)."""

    assert isinstance(record.get("pool_id"), str) and record["pool_id"].strip()
    assert [source["swing_id"] for source in record["sources"]] == [swing["swing_id"]]
    source = record["sources"][0]
    assert source["confirmed_at"] == swing["confirmed_at"]
    assert source["provisional"] is False
    # `usable_at` is the max over the record's own sources (A3-005). How one real swing derives
    # its usable time is still an open rule, so only the bound that cannot be wrong is locked:
    # usability never precedes confirmation.
    assert isinstance(source.get("usable_at"), str) and source["usable_at"].strip()
    assert record["usable_at"] == max(entry["usable_at"] for entry in record["sources"])
    assert datetime.fromisoformat(record["usable_at"]) >= datetime.fromisoformat(
        swing["confirmed_at"]
    )


def test_r72_01_pool_sweep_evidence_survives_future_bars():
    """A3-066: appending future bars cannot change the sweep evidence known before the cutoff.

    The prefix run sees 12 bars, the batch run the same 12 bars plus 4 extension bars, and both
    run the real producer → pool → sweep chain over their own series. The extension really adds a
    confirmed swing (and a later swept high), so the comparison is not vacuous. Expected levels and
    timestamps come from the fixture rows and the producer's documented causal contract.
    """

    prefix_values = _pool_causal_candles(_POOL_CAUSAL_ROWS[: _POOL_CAUSAL_CUTOFF_INDEX + 1])
    batch_values = _pool_causal_candles(_POOL_CAUSAL_ROWS)
    cutoff = _probe.stamp(_POOL_CAUSAL_CUTOFF_INDEX + 1)  # close of the last prefix bar

    prefix_swings, prefix_pools, prefix_sweeps = _pool_causal_run(prefix_values)
    batch_swings, batch_pools, batch_sweeps = _pool_causal_run(batch_values)

    # Preconditions: the extension changes the swing set, and the producer's causal identity and
    # timestamps for the pivot both runs see are unchanged (no backdating).
    expected_level = _POOL_CAUSAL_ROWS[_POOL_CAUSAL_PIVOT_INDEX][2]
    assert [swing["index"] for swing in prefix_swings["lows"]] == [_POOL_CAUSAL_PIVOT_INDEX]
    assert len(batch_swings["lows"]) == 2
    assert len(batch_swings["highs"]) == len(prefix_swings["highs"]) + 1
    prefix_swing = prefix_swings["lows"][0]
    batch_swing = next(
        swing for swing in batch_swings["lows"] if swing["index"] == _POOL_CAUSAL_PIVOT_INDEX
    )
    for field in ("swing_id", "level", "pivot_time", "confirmed_at", "usable_at",
                  "confirmed", "usable"):
        assert batch_swing[field] == prefix_swing[field], field
    assert prefix_swing["level"] == expected_level
    assert prefix_swing["pivot_time"] == _probe.stamp(_POOL_CAUSAL_PIVOT_INDEX)
    assert prefix_swing["confirmed_at"] == _probe.stamp(_POOL_CAUSAL_PIVOT_INDEX + 3)
    # The producer's usability instant is that same confirmation close, and appending future
    # bars cannot move it backwards (F06/r1).
    assert prefix_swing["usable_at"] == prefix_swing["confirmed_at"]
    assert prefix_swing["usable_at"] == _probe.stamp(_POOL_CAUSAL_PIVOT_INDEX + 3)
    assert prefix_swing["usable_at"] != prefix_swing["pivot_time"]
    assert prefix_pools["swing_lows"] == [expected_level]

    # The prefix chain really sweeps that pool level, and each event counts as known only once
    # its reclaim candle has closed — the sweeping candle's open time alone is not evidence.
    prefix_at_cutoff = [s for s in prefix_sweeps["swept_lows"] if _reclaimed_by(s, cutoff)]
    assert [s["index"] for s in prefix_at_cutoff] == [_POOL_CAUSAL_SWEEP_INDEX]
    assert all(s["reclaimed_at"] <= cutoff for s in prefix_at_cutoff)
    # Gate contract: the cutoff is inclusive on the close, so a reclaim at exactly the cutoff
    # is still known. The fixture has no event on that exact boundary, so the operator itself
    # is locked here rather than inferred from producer output.
    assert _reclaimed_by(dict(prefix_at_cutoff[0], reclaimed_at=cutoff), cutoff)

    # Contract: everything the batch knows before the cutoff is identical to the prefix run, and
    # the extra bars only add their own later evidence.
    batch_at_cutoff = [s for s in batch_sweeps["swept_lows"] if _reclaimed_by(s, cutoff)]
    assert all(s["reclaimed_at"] <= cutoff for s in batch_at_cutoff)
    assert len(batch_at_cutoff) == len(prefix_at_cutoff)
    assert _pool_causal_evidence(batch_at_cutoff[0]) == _pool_causal_evidence(prefix_at_cutoff[0])
    assert [s["index"] for s in batch_sweeps["swept_highs"]] == [_POOL_CAUSAL_FUTURE_SWEEP_INDEX]

    # A3-066/b — the canonical pool record is the authority behind that sweep, not the numeric
    # level projection (`prefix_pools["swing_lows"]`) and not the sweep's fallback swing ID.
    # The record is selected by kind + causal source lineage, so the batch's second swing low
    # cannot be picked up by accident. `records` is the F06 contract: this is EXPECTED
    # IMPLEMENTATION RED until core emits it, and it is asserted last so the causal parity
    # above still executes.
    prefix_record = _pool_record_for(prefix_pools, "swing_low", [prefix_swing["swing_id"]])
    _assert_pool_record_matches_source(prefix_record, prefix_swing)
    batch_record = _pool_record_for(batch_pools, "swing_low", [batch_swing["swing_id"]])
    _assert_pool_record_matches_source(batch_record, batch_swing)

    # The same pivot is the same canonical pool in both runs: its ID and usable time are minted
    # from the causal source lineage, so appending future bars cannot change them.
    assert batch_record["pool_id"] == prefix_record["pool_id"]
    assert batch_record["kind"] == prefix_record["kind"] == "swing_low"
    assert batch_record["source_ids"] == prefix_record["source_ids"]
    assert batch_record["usable_at"] == prefix_record["usable_at"]
    assert batch_record["level"] == expected_level

    # A3-066/c — the sweep's pool provenance must resolve to that canonical record, for both runs
    # and before the cutoff. The expected lineage and level come from the fixture, so two outputs
    # agreeing (and being wrong together) is not enough.
    for sweep, record, swing in (
        (prefix_at_cutoff[0], prefix_record, prefix_swing),
        (batch_at_cutoff[0], batch_record, batch_swing),
    ):
        assert sweep["source_swing_id"] == swing["swing_id"]
        assert record["source_ids"] == [swing["swing_id"]]
        assert sweep["source_pool_id"] == record["pool_id"]
        assert record["level"] == swing["level"] == expected_level

    # The batch really carries a second, different pool of the same kind (swing low at index 10,
    # level 99.0). Selecting by lineage must keep the two apart: a new source lineage is a new
    # pool, and the sweep stays linked to the pivot's pool rather than the last/nearest one.
    other_swing = next(
        swing for swing in batch_swings["lows"] if swing["index"] != _POOL_CAUSAL_PIVOT_INDEX
    )
    other_record = _pool_record_for(batch_pools, "swing_low", [other_swing["swing_id"]])
    assert other_record["level"] == other_swing["level"] != expected_level
    assert other_record["pool_id"] != batch_record["pool_id"]
    assert batch_at_cutoff[0]["source_pool_id"] != other_record["pool_id"]


def test_r72_01_pool_sweep_identity_survives_rolling_index():
    """A3-066: dropping the oldest bar shifts indices but not the causal identity.

    The rolled run drops the first bar and keeps every remaining bar's own timestamp (no newest
    bar is appended, so the comparison isolates identity from new evidence). The same pivot is then
    seen one index earlier: its swing ID, level and confirmation time must be unchanged, and the
    sweep must keep its ID and reclaim time while its positional index shifts by exactly one.
    """

    batch_values = _pool_causal_candles(_POOL_CAUSAL_ROWS)
    rolled_values = _pool_causal_candles(_POOL_CAUSAL_ROWS[1:], offset=1)

    batch_swings, batch_pools, batch_sweeps = _pool_causal_run(batch_values)
    rolled_swings, rolled_pools, rolled_sweeps = _pool_causal_run(rolled_values)

    # Preconditions: same wall-clock timestamps, one bar fewer, same pool levels.
    assert rolled_values[0].time == batch_values[1].time
    assert len(rolled_values) == len(batch_values) - 1
    assert rolled_pools["swing_lows"] == batch_pools["swing_lows"]

    # The pivot keeps its causal identity and timestamps; only its positional index moves.
    batch_swing = next(
        swing for swing in batch_swings["lows"] if swing["index"] == _POOL_CAUSAL_PIVOT_INDEX
    )
    rolled_swing = next(
        swing for swing in rolled_swings["lows"] if swing["index"] == _POOL_CAUSAL_PIVOT_INDEX - 1
    )
    assert batch_swing["pivot_time"] == rolled_swing["pivot_time"]
    assert batch_swing["confirmed_at"] == rolled_swing["confirmed_at"]
    assert batch_swing["swing_id"] == rolled_swing["swing_id"]
    assert batch_swing["level"] == rolled_swing["level"]
    # Dropping the oldest bar shifts positional indices only: the producer's usability instant
    # is the same confirmation close in both windows (F06/r1, A-D06).
    assert batch_swing["usable_at"] == rolled_swing["usable_at"] == batch_swing["confirmed_at"]

    # The sweep keeps its causal evidence; the positional index legitimately shifts by one.
    assert len(batch_sweeps["swept_lows"]) == 1
    assert len(rolled_sweeps["swept_lows"]) == 1
    batch_sweep = batch_sweeps["swept_lows"][0]
    rolled_sweep = rolled_sweeps["swept_lows"][0]
    assert batch_sweep["index"] == _POOL_CAUSAL_SWEEP_INDEX
    assert rolled_sweep["index"] == _POOL_CAUSAL_SWEEP_INDEX - 1
    assert _pool_causal_evidence(rolled_sweep) == _pool_causal_evidence(batch_sweep)

    # A3-066/d — the same canonical pool must survive the index shift. Its ID, source lineage
    # and usable time are minted from the causal source, so a rolled window cannot remint them.
    # Asserted last so the causal parity above still runs. `records` is the F06 contract, so
    # this is EXPECTED IMPLEMENTATION RED until core emits it.
    batch_record = _pool_record_for(batch_pools, "swing_low", [batch_swing["swing_id"]])
    rolled_record = _pool_record_for(rolled_pools, "swing_low", [rolled_swing["swing_id"]])
    _assert_pool_record_matches_source(batch_record, batch_swing)
    _assert_pool_record_matches_source(rolled_record, rolled_swing)
    assert rolled_record["pool_id"] == batch_record["pool_id"]
    assert rolled_record["source_ids"] == batch_record["source_ids"] == [batch_swing["swing_id"]]
    assert rolled_record["kind"] == batch_record["kind"] == "swing_low"
    assert rolled_record["level"] == batch_record["level"] == batch_swing["level"]
    assert rolled_record["usable_at"] == batch_record["usable_at"]

    # The sweep is linked to that same canonical pool on both runs: only the positional index
    # moved, the pool provenance did not.
    assert batch_sweep["source_pool_id"] == batch_record["pool_id"]
    assert rolled_sweep["source_pool_id"] == rolled_record["pool_id"]
    assert rolled_sweep["source_pool_id"] == batch_sweep["source_pool_id"]


def test_r72_01_pool_identity_survives_source_permutation():
    """A3-066/e: the same source set in either input order is the same canonical pool.

    `pool_id` is minted from `kind` + **sorted** `source_ids` + the per-source causal records, so
    `source_ids` must come back in stable sorted order — neither the caller's input order nor the
    causal order may leak into it. The fixture is built so those two candidate orders disagree:
    `source-z` pivots first but sorts last, `source-a` pivots later but sorts first. A test that
    only compared the two outputs would pass under either rule; this one pins the sorted rule and,
    separately, checks each source's own provenance keyed by its ID rather than by list position.

    Only pool identity is asserted here — no pool-priority rule, no sweep count and no dedupe
    behaviour is locked, and `core/` is not changed.
    """

    tick, atr = 0.1, 1.0
    # `source-z` has the earlier pivot; `source-a` has the later one, so causal order and sorted
    # ID order are exact reverses of each other.
    source_z = dict(
        level=100.0, index=0, swing_id="source-z", confirmed=True,
        usable=True, provisional=False, pivot_time=_probe.stamp(0),
        confirmed_at=_probe.stamp(1), usable_at=_probe.stamp(1),
    )
    source_a = dict(source_z, level=100.05, swing_id="source-a", index=1,
                    pivot_time=_probe.stamp(1), confirmed_at=_probe.stamp(2),
                    usable_at=_probe.stamp(2))
    values = _probe.candles([(112, 114, 111, 113)] * 8, "buy")

    first_order = [source_z, source_a]
    reversed_order = [source_a, source_z]

    # Preconditions: the input order really swaps, and the causal order is the reverse of the
    # sorted-ID order — so the assertion below can tell the two candidate rules apart.
    assert [s["swing_id"] for s in first_order] != [s["swing_id"] for s in reversed_order]
    causal_ids = [
        swing["swing_id"]
        for swing in sorted((source_z, source_a), key=lambda s: s["pivot_time"])
    ]
    expected_source_ids = sorted(swing["swing_id"] for swing in (source_z, source_a))
    assert causal_ids == ["source-z", "source-a"]
    assert expected_source_ids == ["source-a", "source-z"]
    assert causal_ids != expected_source_ids

    expected_sources = {source["swing_id"]: source for source in (source_z, source_a)}
    expected_usable_at = max(source["usable_at"] for source in expected_sources.values())
    expected_level = (source_z["level"] + source_a["level"]) / 2.0

    observed = {}
    for name, ordered in (("as_given", first_order), ("reversed", reversed_order)):
        pools = detect_liquidity_pools(
            values, {"highs": [], "lows": [dict(source) for source in ordered]},
            tick_size=tick, atr_value=atr,
        )
        # Selected by kind + sorted source-ID lineage, never by list position: the numeric
        # projection is only checked as a projection below.
        record = _pool_record_for(pools, "equal_low", expected_source_ids)
        assert record["source_ids"] == expected_source_ids
        assert record["usable_at"] == expected_usable_at
        assert pools["equal_lows"] == [expected_level]
        observed[name] = record

    # Reversing the inputs cannot remint the pool: identity, lineage and usable time are causal.
    assert observed["reversed"]["pool_id"] == observed["as_given"]["pool_id"]
    assert observed["reversed"]["source_ids"] == observed["as_given"]["source_ids"]
    assert observed["reversed"]["usable_at"] == observed["as_given"]["usable_at"]
    assert observed["reversed"]["kind"] == observed["as_given"]["kind"] == "equal_low"
    assert observed["reversed"]["level"] == observed["as_given"]["level"] == expected_level

    for record in observed.values():
        # Each source keeps its own identity and times, looked up by swing ID — never by its
        # position in `sources`, which the contract does not pin.
        assert len(record["sources"]) == len(expected_source_ids)
        by_id = {entry["swing_id"]: entry for entry in record["sources"]}
        assert sorted(by_id) == expected_source_ids
        for swing_id, expected in expected_sources.items():
            entry = by_id[swing_id]
            assert entry["confirmed_at"] == expected["confirmed_at"]
            assert entry["usable_at"] == expected["usable_at"]
            assert entry["provisional"] is False
        assert record["usable_at"] == max(entry["usable_at"] for entry in record["sources"])


def test_r72_01_provisional_source_cannot_create_a_sweep():
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (110, 111, 99.5, 100.1)
    source = dict(
        level=100, index=0, swing_id="provisional", confirmed=True,
        usable=True, provisional=True, pivot_time=_probe.stamp(0),
        confirmed_at=_probe.stamp(1),
    )
    values = _probe.candles(rows)
    pools = detect_liquidity_pools(
        values, {"highs": [], "lows": [source]}, tick_size=0.1, atr_value=1,
    )
    result = detect_liquidity_sweeps(
        values, {"highs": [], "lows": [source]}, timeframe="H1",
        tick_size=0.1, atr_value=1, causal_only=True, lookback_bars=8,
        liquidity_pools=pools,
    )
    assert result["swept_lows"] == []


def test_r72_01_equal_usable_at_reclaimed_is_temporally_eligible():
    """A3-039 + A3-041: a real excursion+reclaim candle sweeps the equal pool, and the candle's
    close is exactly the pool usable time — the boundary A-D01 treats as eligible.

    This is a **synthetic temporal seam**: the sources' `usable_at` is declared by the fixture, so
    the case proves the inclusive gate contract, not that a real pivot producer emits that time
    (that end-to-end positive is A3-044).

    The event is selected by target level and candle index, never by list position, and no total
    sweep count is asserted — pool priority, cardinality and dedupe stay unlocked. The canonical
    `records` block runs last so the temporal assertions above really execute; `records` is the
    F06 contract, so what remains after them is EXPECTED IMPLEMENTATION RED, not a temporal gap.
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    usable_at = _probe.stamp(2)
    source_a = dict(
        level=100, index=0, swing_id="source-a", confirmed=True,
        usable=True, provisional=False, pivot_time=_probe.stamp(0),
        confirmed_at=usable_at, usable_at=usable_at,
    )
    source_b = dict(source_a, level=100.05, index=1, swing_id="source-b",
                    pivot_time=_probe.stamp(1))
    rows = [(112, 114, 111, 113)] * 8
    rows[1] = (100.3, 100.5, 99.5, 100.3)
    values = _probe.candles(rows)
    swings = {"highs": [], "lows": [source_a, source_b]}
    pools = detect_liquidity_pools(
        values, swings, tick_size=tick, atr_value=atr,
    )

    # Numeric keys stay the legacy projection (float pair average, never a dict).
    expected_level = (source_a["level"] + source_b["level"]) / 2.0
    numeric_levels = pools["equal_lows"]
    assert numeric_levels == [expected_level]
    assert all(not isinstance(level, dict) for level in numeric_levels)

    # The seam this case locks (A3-039 / A3-041): every source becomes usable exactly when the
    # examined candle closes, so `pool_usable_at == reclaimed_at` — the inclusive boundary.
    # Computed from the fixture, never read back from the detector.
    pool_usable_at = max(source["usable_at"] for source in (source_a, source_b))
    assert pool_usable_at == usable_at == _probe.stamp(2)

    # Preconditions from the fixture: the examined candle really crosses the equal level by
    # more than the excursion buffer and reclaims within the same candle.
    sweep_candle = values[1]
    assert sweep_candle.low < expected_level - excursion
    assert sweep_candle.close > expected_level

    # The sweep detector must see that event at the examined candle, and its close must equal the
    # pool usable time (the inclusive boundary). A3-041: the equality below is the synthetic seam
    # — both sides come from the fixture, not from a pivot producer. Selection is by level and
    # candle index, so the total number of sweeps stays unasserted.
    sweeps = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=tick, atr_value=atr,
        causal_only=True, lookback_bars=8, liquidity_pools=pools,
    )
    target_events = [
        sweep for sweep in sweeps["swept_lows"]
        if sweep["level"] == expected_level and sweep["index"] == 1
    ]
    assert target_events, sweeps["swept_lows"]
    assert any(sweep["reclaimed_at"] == pool_usable_at for sweep in target_events)
    # No swing highs are declared, so no SELL-side pool can exist.
    assert sweeps["swept_highs"] == []

    # Canonical provenance is read from `records`, with the max source usable time. Kept after
    # the temporal seam so A3-039/A3-041 actually run; `records` is F06.
    records = [
        record for record in _pool_records(pools)
        if record.get("source_ids") == ["source-a", "source-b"]
    ]
    assert len(records) == 1
    assert records[0]["usable_at"] == pool_usable_at


def test_r72_01_equal_pool_usable_before_sweep_close_is_accepted():
    """A3-040: with the pool usable strictly before the sweep close, a valid excursion and
    reclaim are accepted — the positive side of the A-D01 temporal gate.

    Source and event times are asserted from the fixture (not just "list non-empty"): the
    sources are usable at stamp(2) and the accepted sweep closes at stamp(3). The event is
    selected by target level and candle index, never by list position, and no total sweep count
    is asserted — pool priority, cardinality and dedupe stay unlocked.
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    usable_at = _probe.stamp(2)
    source_a = dict(
        level=100, index=0, swing_id="source-a", confirmed=True,
        usable=True, provisional=False, pivot_time=_probe.stamp(0),
        confirmed_at=usable_at, usable_at=usable_at,
    )
    source_b = dict(source_a, level=100.05, index=1, swing_id="source-b",
                    pivot_time=_probe.stamp(1))
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (100.3, 100.5, 99.5, 100.3)
    values = _probe.candles(rows)
    swings = {"highs": [], "lows": [source_a, source_b]}
    pools = detect_liquidity_pools(values, swings, tick_size=tick, atr_value=atr)

    # Preconditions: both sources valid, usable, non-provisional; pool usable strictly
    # before the event close (H1 candles close one hour after opening).
    for source in (source_a, source_b):
        assert source["confirmed"] is True
        assert source["usable"] is True
        assert source["provisional"] is False
    pool_usable_at = max(source["usable_at"] for source in (source_a, source_b))
    assert pool_usable_at == usable_at
    open_time, event_close = _probe.stamp(2), _probe.stamp(3)
    assert pool_usable_at < event_close

    # The equal pool this case is about really exists at `expected_level`, and that level differs
    # from either single-source level — so filtering emitted events by it selects the equal pool
    # alone and cannot match a single-source event by accident.
    expected_level = (source_a["level"] + source_b["level"]) / 2.0
    assert pools["equal_lows"] == [expected_level]
    assert expected_level not in {source_a["level"], source_b["level"]}

    # Preconditions from the fixture geometry: excursion beyond the level, reclaim in candle.
    sweep_candle = values[2]
    assert sweep_candle.low < expected_level - excursion
    assert sweep_candle.close > expected_level

    sweeps = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=tick, atr_value=atr,
        causal_only=True, lookback_bars=8, liquidity_pools=pools,
    )
    # Selected by level and candle index, never by list position; the total number of sweeps is
    # not asserted, so an extra legitimate event could not fail this control.
    target_events = [
        sweep for sweep in sweeps["swept_lows"]
        if sweep["level"] == expected_level and sweep["index"] == 2
    ]
    assert target_events, sweeps["swept_lows"]
    matched = [
        sweep for sweep in target_events
        if sweep["kind"] == "swept_low"
        and sweep["side"] == "buy"
        and sweep["time"] == open_time
        and sweep["reclaimed_at"] == event_close
        and sweep["excursion_buffer"] == pytest.approx(excursion)
    ]
    assert matched, target_events
    # No swing highs are declared, so no SELL-side pool can exist.
    assert sweeps["swept_highs"] == []


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_01_source_usable_after_sweep_close_is_rejected(side):
    """A3-042: the same excursion and reclaim as the accepted control (A3-040), but the pool
    sources only become usable *after* the sweep close — a future source must not be used.

    The only difference from the control is the source usable time, so a sweep here can only
    come from the detector ignoring the A-D01 temporal gate (currently RED: the gate is not
    implemented yet, see F07).
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    future_usable_at = _probe.stamp(4)
    base_level = 110.0 if side == "sell" else 100.0
    offset = -0.05 if side == "sell" else 0.05
    source_a = dict(
        level=base_level, index=0, swing_id="source-a", confirmed=True,
        usable=True, provisional=False, pivot_time=_probe.stamp(0),
        confirmed_at=future_usable_at, usable_at=future_usable_at,
    )
    source_b = dict(source_a, level=base_level + offset, index=1, swing_id="source-b",
                    pivot_time=_probe.stamp(1))
    swings = (
        {"highs": [source_a, source_b], "lows": []}
        if side == "sell"
        else {"highs": [], "lows": [source_a, source_b]}
    )
    # Buy-shaped rows: `_probe.candles` mirrors them around 210 for SELL.
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (100.3, 100.5, 99.5, 100.3)
    values = _probe.candles(rows, side)
    pools = detect_liquidity_pools(values, swings, tick_size=tick, atr_value=atr)

    # Preconditions: both sources valid but usable strictly AFTER the event close, and the
    # same excursion/reclaim geometry as the accepted control.
    for source in (source_a, source_b):
        assert source["confirmed"] is True
        assert source["usable"] is True
        assert source["provisional"] is False
    pool_usable_at = max(source["usable_at"] for source in (source_a, source_b))
    open_time, event_close = _probe.stamp(2), _probe.stamp(3)
    assert pool_usable_at == future_usable_at
    assert pool_usable_at > event_close
    expected_level = (source_a["level"] + source_b["level"]) / 2.0
    sweep_candle = values[2]
    if side == "buy":
        assert sweep_candle.low < expected_level - excursion
        assert sweep_candle.close > expected_level
    else:
        assert sweep_candle.high > expected_level + excursion
        assert sweep_candle.close < expected_level

    sweeps = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=tick, atr_value=atr,
        causal_only=True, lookback_bars=8, liquidity_pools=pools,
    )
    tested, other = (
        ("swept_highs", "swept_lows") if side == "sell" else ("swept_lows", "swept_highs")
    )
    assert sweeps[tested] == []
    assert sweeps[other] == []
    # Sanity: the examined candle is the one that opened at stamp(2) and closed at stamp(3).
    assert sweep_candle.time == datetime.fromisoformat(open_time)


def test_r72_01_equal_pool_usable_time_is_max_of_both_sources():
    """A3-043/a: with the two sources confirmed at different times, the equal pool's usable time
    is the max of both — so a close lying between the two source times is not eligible.

    Using only the first source's time would accept this fixture, which is what makes the case
    discriminate "max of both" from "first source only" (RED until F07 implements the gate).

    The negative is scoped to the target equal pool: it asserts that no event of *that* pool is
    emitted, not that the whole `swept_lows` list is empty. `source-a` also forms a single-source
    pool whose source is usable before this candle closes, so a single-source sweep here would be
    legitimate and must not be forbidden by this node (its own control is A3-043/b).
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    early, late = _probe.stamp(1), _probe.stamp(3)
    source_a = dict(
        level=100, index=0, swing_id="source-a", confirmed=True,
        usable=True, provisional=False, pivot_time=_probe.stamp(0),
        confirmed_at=early, usable_at=early,
    )
    source_b = dict(source_a, level=100.05, index=1, swing_id="source-b",
                    pivot_time=_probe.stamp(1), confirmed_at=late, usable_at=late)
    rows = [(112, 114, 111, 113)] * 8
    rows[1] = (100.3, 100.5, 99.5, 100.3)
    values = _probe.candles(rows)
    swings = {"highs": [], "lows": [source_a, source_b]}
    pools = detect_liquidity_pools(values, swings, tick_size=tick, atr_value=atr)

    # Preconditions: the equal pool exists, the two usable times differ, and the examined
    # candle closes strictly between them.
    expected_level = (source_a["level"] + source_b["level"]) / 2.0
    assert pools["equal_lows"] == [expected_level]
    # The equal level differs from both single-source levels, so filtering emitted events by it
    # selects the equal pool alone and cannot silently match a single-source event.
    assert expected_level not in {source_a["level"], source_b["level"]}
    assert source_a["usable_at"] != source_b["usable_at"]
    pool_usable_at = max(source["usable_at"] for source in (source_a, source_b))
    assert pool_usable_at == late
    event_close = _probe.stamp(2)
    assert early < event_close < pool_usable_at
    sweep_candle = values[1]
    assert sweep_candle.low < expected_level - excursion
    assert sweep_candle.close > expected_level

    sweeps = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=tick, atr_value=atr,
        causal_only=True, lookback_bars=8, liquidity_pools=pools,
    )
    # Only the target equal pool is under test. `source-a` also forms a single-source pool
    # (level 100) that is usable at `early` and therefore sweeps this candle legitimately, so
    # asserting the whole `swept_lows` list is empty would forbid a valid single-source event and
    # lock pool priority/cardinality. The list is filtered by the equal pool's own level — never
    # by list position — and only that subset must be empty: the equal pool is not usable until
    # `late`, after this candle's close.
    equal_pool_events = [
        sweep for sweep in sweeps["swept_lows"] if sweep["level"] == expected_level
    ]
    assert equal_pool_events == []
    # No swing highs are declared, so no SELL-side pool can exist.
    assert sweeps["swept_highs"] == []


def test_r72_01_single_source_pool_usable_before_sweep_close_is_accepted():
    """A3-043/b: the same geometry with a single source really sweeps, so the A3-043/a negative
    must not forbid the whole `swept_lows` list.

    Same H1 fixture as A3-043/a but only `source-a` is declared, so no equal pool can exist. That
    source is usable at `stamp(1)`, before the sweeping candle's close `stamp(2)`, so its own
    single-source pool sweep is temporally eligible and is accepted. Only events of the target
    level are examined and no total sweep count, pool priority or dedupe is locked; canonical
    `records` is neither used nor required here.
    """

    tick, atr = 0.1, 1.0
    excursion = max(2.0 * tick, 0.10 * atr)
    level = 100.0
    usable_at = _probe.stamp(1)
    event_close = _probe.stamp(2)
    source_a = dict(
        level=level, index=0, swing_id="source-a", confirmed=True,
        usable=True, provisional=False, pivot_time=_probe.stamp(0),
        confirmed_at=usable_at, usable_at=usable_at,
    )
    rows = [(112, 114, 111, 113)] * 8
    rows[1] = (100.3, 100.5, 99.5, 100.3)
    values = _probe.candles(rows)
    swings = {"highs": [], "lows": [source_a]}

    # Preconditions: the declared source is confirmed/usable and non-provisional, its usable time
    # precedes the sweeping candle's close, and the fixture geometry really excursions past the
    # level and reclaims within that same candle.
    assert source_a["confirmed"] is True and source_a["usable"] is True
    assert source_a["provisional"] is False
    assert usable_at < event_close
    sweep_candle = values[1]
    assert sweep_candle.low < level - excursion
    assert sweep_candle.close > level

    pools = detect_liquidity_pools(values, swings, tick_size=tick, atr_value=atr)

    # A single source cannot form an equal pool; only its own swing pool remains.
    assert pools["equal_lows"] == []
    assert pools["swing_lows"] == [level]

    sweeps = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=tick, atr_value=atr,
        causal_only=True, lookback_bars=8, liquidity_pools=pools,
    )

    # Selected by the target level, never by list position. The total number of sweeps is not
    # asserted, so an extra legitimate event could not fail this control.
    target_events = [sweep for sweep in sweeps["swept_lows"] if sweep["level"] == level]
    assert target_events, "the single-source pool must sweep this candle"
    matched = [
        sweep for sweep in target_events
        if sweep["index"] == 1
        and sweep["reclaimed_at"] == event_close
        and sweep["source_swing_id"] == "source-a"
    ]
    assert matched, target_events
    assert matched[0]["level"] == level


def test_r72_01_equal_pool_without_usable_source_does_not_exist():
    """A3-043: an equal pool needs both sources usable — with one unusable source only the
    usable source's own single-source pool remains, so no equal pool can be swept."""

    tick, atr = 0.1, 1.0
    usable_at = _probe.stamp(2)
    source_a = dict(
        level=100, index=0, swing_id="source-a", confirmed=True,
        usable=True, provisional=False, pivot_time=_probe.stamp(0),
        confirmed_at=usable_at, usable_at=usable_at,
    )
    source_b = dict(source_a, level=100.05, index=1, swing_id="source-b", usable=False)
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (100.3, 100.5, 99.5, 100.3)
    values = _probe.candles(rows)
    pools = detect_liquidity_pools(
        values, {"highs": [], "lows": [source_a, source_b]},
        tick_size=tick, atr_value=atr,
    )

    # The unusable source is excluded from the pool projection: no equal pool forms and only
    # the usable source's own level survives, so there is nothing to sweep as an equal pool.
    assert source_b["usable"] is False
    assert pools["equal_lows"] == []
    assert pools["swing_lows"] == [source_a["level"]]


def test_r72_01_actual_swing_producer_feeds_pool_and_sweep():
    """A3-044: end-to-end positive from the real swing producer — fixture OHLC emits a
    confirmed swing, that swing becomes the pool, and a later candle sweeps it after the
    swing is usable.

    Expected level/pivot/close come from the fixture rows and the producer's documented
    causal contract (pivot time = pivot candle open, `confirmed_at` = close of pivot +
    lookback), not from the pool or sweep output. Separate from the synthetic temporal
    fixtures of A3-039…A3-043, where sources are declared by hand.
    """

    tick, atr = 0.1, 1.0
    lookback = 2
    excursion = max(2.0 * tick, 0.10 * atr)
    pivot_index, sweep_index = 4, 10
    rows = [
        (105, 106, 104, 105),
        (105, 106, 103, 104),
        (104, 105, 102, 103),
        (103, 104, 100.5, 101),
        (101, 102, 99.5, 101.5),
        (101.5, 103, 101, 102.5),
        (102.5, 104, 102, 103.5),
        (103.5, 105, 103, 104.5),
        (104.5, 106, 104, 105.5),
        (105.5, 106, 103, 104),
        (100, 100.6, 99.0, 100.2),
        (104, 105, 103, 104),
    ]
    values = _probe.candles(rows)
    swings = external_swing_points(
        values, symbol="EURUSD", timeframe="H1", lookback=lookback, equal_tolerance=0.0,
    )

    # The producer emits exactly the expected pivot, with the causal timestamps.
    expected_level = rows[pivot_index][2]
    assert [swing["index"] for swing in swings["lows"]] == [pivot_index]
    swing = swings["lows"][0]
    assert swing["level"] == expected_level
    assert swing["pivot_time"] == _probe.stamp(pivot_index)
    assert swing["confirmed_at"] == _probe.stamp(pivot_index + lookback + 1)
    assert swing["confirmed"] is True
    assert swing["usable"] is True
    assert swing["provisional"] is False
    assert swing["swing_id"]
    # The producer owns the usability instant: a confirmed, non-provisional pivot is usable
    # from the close of its right-side confirmation candle — not the pivot's open time.
    assert swing["usable_at"] == swing["confirmed_at"]
    assert swing["usable_at"] == _probe.stamp(pivot_index + lookback + 1)
    assert swing["usable_at"] != swing["pivot_time"]

    # The produced swing is what the pool is built from.
    pools = detect_liquidity_pools(values, swings, tick_size=tick, atr_value=atr)
    assert pools["swing_lows"] == [expected_level]

    # The canonical record for that pool keeps the source identity and the same usable time,
    # so a sweep can later be gated on when the level really became usable (A3-005, F06).
    record = _pool_record_for(pools, "swing_low", [swing["swing_id"]])
    assert record["level"] == expected_level
    assert record["sources"][0]["confirmed_at"] == swing["confirmed_at"]
    assert record["sources"][0]["usable_at"] == swing["usable_at"]
    assert record["usable_at"] == swing["usable_at"]

    # Preconditions from the fixture geometry: the sweep candle crosses the swing level by
    # more than the excursion buffer and reclaims within the same candle.
    sweep_candle = values[sweep_index]
    assert sweep_candle.low < expected_level - excursion
    assert sweep_candle.close > expected_level

    sweeps = detect_liquidity_sweeps(
        values, swings, timeframe="H1", tick_size=tick, atr_value=atr,
        causal_only=True, lookback_bars=8, liquidity_pools=pools,
    )
    assert [sweep["index"] for sweep in sweeps["swept_lows"]] == [sweep_index]
    sweep = sweeps["swept_lows"][0]
    assert sweep["level"] == expected_level
    assert sweep["reclaimed_at"] == _probe.stamp(sweep_index + 1)
    # The sweep traces back to the swing the producer emitted, and it happens strictly after
    # that swing became usable.
    assert sweep["source_swing_id"] == swing["swing_id"]
    assert swing["confirmed_at"] < sweep["reclaimed_at"]


def test_r72_01_internal_producer_declares_usable_at_at_confirmation_close():
    """F06/r1: the shared producer contract holds for the internal seam too.

    `internal_swing_points` and `external_swing_points` run the same confirmation seam, so an
    internal pivot must declare the same usability instant — the close of its right-side
    confirmation candle, not the pivot's open time — and the canonical pool built from it must
    carry that exact time back out.
    """

    start = datetime.fromisoformat(_probe.stamp(0))
    rows = [(100.0, 110.0, 90.0, 100.0)] * 5
    rows[2] = (100.0, 120.0, 80.0, 100.0)
    values = [
        Candle(
            time=start + timedelta(hours=4 * index),
            open=open_, high=high, low=low, close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    assert not validate_smc_candles(values, "H4")

    swings = internal_swing_points(values, symbol="EURUSD", timeframe="H4")
    assert [swing["index"] for swing in swings["highs"]] == [2]
    swing = swings["highs"][0]
    # Expected instant from the fixture and the documented contract: close of pivot + width.
    expected_usable_at = candle_close_at(values[4].time, "H4").isoformat()
    assert swing["scope"] == "internal"
    assert swing["provisional"] is False
    assert swing["usable"] is True
    assert swing["usable_at"] == swing["confirmed_at"] == expected_usable_at
    assert swing["usable_at"] != swing["pivot_time"]

    pools = detect_liquidity_pools(values, swings, tick_size=0.1, atr_value=1.0)
    assert pools["swing_highs"] == [swing["level"]]
    record = _pool_record_for(pools, "swing_high", [swing["swing_id"]])
    assert record["level"] == swing["level"]
    assert record["sources"][0]["swing_id"] == swing["swing_id"]
    assert record["sources"][0]["usable_at"] == expected_usable_at
    assert record["usable_at"] == expected_usable_at


def test_r72_01_provisional_producer_declares_no_usable_at_and_no_canonical_record():
    """F06/r1: a provisional pivot never hands out an effective usability instant.

    The producer still emits the fallback-width pivot, but with `usable=False` and no usable
    time. The canonical pool layer must therefore emit no record for it: it is excluded, not
    silently downgraded to the legacy numeric projection (A3-005 rule 3, A-D06).
    """

    values = _pool_causal_candles(_POOL_CAUSAL_ROWS)
    swings = external_swing_points(
        values, symbol="EURUSD", timeframe="H1", lookback=2, provisional=True,
    )
    # Precondition: the fallback-width pivots are still emitted, so the absence below is not
    # caused by an empty swing set.
    assert swings["highs"] and swings["lows"]
    for swing in [*swings["highs"], *swings["lows"]]:
        assert swing["provisional"] is True
        assert swing["usable"] is False
        assert not swing.get("usable_at")

    pools = detect_liquidity_pools(values, swings, tick_size=0.1, atr_value=1.0)
    assert pools["swing_highs"] == [] and pools["swing_lows"] == []
    assert pools["records"] == []


# --- F07/r1: the public Analyze/Scanner route keeps its legacy pool sweeps -------------------

# Diagnostic fixture (12 H1 bars, below the 15-bar ATR-filter threshold): the legacy
# `swing_points` producer emits one pivot low at index 4 (level 99.5), and bar 10 crosses that
# level downwards before closing back above it.
_PUBLIC_ROUTE_ROWS = [
    (105, 106, 104, 105),
    (105, 106, 103, 104),
    (104, 105, 102, 103),
    (103, 104, 100.5, 101),
    (101, 102, 99.5, 101.5),   # pivot low, level 99.5
    (101.5, 103, 101, 102.5),
    (102.5, 104, 102, 103.5),
    (103.5, 105, 103, 104.5),
    (104.5, 106, 104, 105.5),
    (105.5, 106, 103, 104),
    (100, 100.6, 99.0, 100.2),  # sweeps 99.5: low below it, close above it
    (104, 105, 103, 104),
]

# Equal-pool control: two pivot lows at 99.5 (index 4) and 99.55 (index 7), whose mean 99.525 is
# the equal level; bar 10 crosses that mean downwards and closes back above it.
_PUBLIC_ROUTE_EQUAL_ROWS = [
    (105, 106, 104, 105),
    (105, 106, 103, 104),
    (104, 105, 102, 103),
    (103, 104, 100.5, 101),
    (101, 102, 99.5, 101.5),    # first pivot low, level 99.5
    (101.5, 103, 101, 102.5),
    (102.5, 104, 102, 103.5),
    (103.5, 105, 99.55, 104.5),  # second pivot low, level 99.55
    (104.5, 106, 104, 105.5),
    (105.5, 106, 103, 104),
    (100, 100.6, 99.0, 100.2),  # crosses the 99.525 mean, reclaims in candle
    (104, 105, 103, 104),
]


def _public_route_context(rows):
    """Run the real public per-timeframe builder over one H1 fixture."""

    start = datetime.fromisoformat(_probe.stamp(0))
    values = [
        Candle(
            time=start + timedelta(hours=index),
            open=open_, high=high, low=low, close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    assert not validate_smc_candles(values, "H1")
    return values, _smc_for_timeframe(
        values, tf_minutes=60, scan_interval_min=15, symbol="EURUSD", timeframe="H1",
    )


def test_r72_01_public_route_keeps_legacy_pool_sweeps():
    """F07/r1: `_smc_for_timeframe` explicitly keeps the legacy pool sweeps it always had.

    The public Analyze/Scanner route runs the legacy unannotated `swing_points` producer, whose
    pools carry no canonical provenance (`records` is empty and swings declare no `usable_at`).
    The caller therefore selects the legacy numeric branch explicitly, and its sweeps must stay
    exactly what the fixture geometry describes — restoring the events the canonical default
    would fail closed on, without inventing any canonical ID or usable time.
    """

    values, context = _public_route_context(_PUBLIC_ROUTE_ROWS)
    pivot_index, sweep_index = 4, 10
    level = _PUBLIC_ROUTE_ROWS[pivot_index][2]
    pools = context["liquidity_pools"]

    # Precondition: the legacy producer really declares no canonical provenance here, so the
    # branch below is required rather than decorative.
    assert pools["swing_lows"] == [level]
    assert pools["records"] == []
    assert not any("usable_at" in swing for swing in context["swings"]["lows"])

    # Expected event from the fixture: bar 10 crosses the level and closes back above it, so the
    # reclaim time is that bar's close (H1 closes one hour after opening).
    sweep_candle = values[sweep_index]
    assert sweep_candle.low < level and sweep_candle.close > level
    expected_reclaim = _probe.stamp(sweep_index + 1)

    for key in ("liquidity_sweeps", "zone_link_sweeps"):
        events = context[key]["swept_lows"]
        assert [(event["index"], event["level"]) for event in events] == [(sweep_index, level)], key
        event = events[0]
        assert event["reclaimed_at"] == expected_reclaim
        assert event["side"] == "buy" and event["kind"] == "swept_low"
        # Legacy numeric pool identity, and no fabricated canonical provenance.
        assert event["source_pool_id"] == f"swing_low:{level:.15g}"
        assert not event["source_swing_id"]
        assert "source_ids" not in event and "source_pool_usable_at" not in event
        assert context[key]["swept_highs"] == []

    # Control: the very same pool payload read on the canonical default still fails closed,
    # because an empty `records` container is never treated as legacy by the detector itself.
    canonical = detect_liquidity_sweeps(
        values, context["swings"], timeframe="H1", causal_only=True, lookback_bars=8,
        liquidity_pools=pools,
    )
    assert canonical["swept_lows"] == [] and canonical["swept_highs"] == []


def test_r72_01_public_route_keeps_legacy_equal_pool_sweep():
    """F07/r1 equal-pool control: the legacy route keeps the equal pool and its sweep.

    Two pivot lows 0.05 apart form an equal pool at their mean 99.525, and bar 10 crosses that
    mean before reclaiming. `zone_link_sweeps` scans the whole fixture, so the first pivot bar —
    whose own low sits just below the mean and which closes above it — is an expected event too;
    both are derived from the fixture rows, not from the output.
    """

    values, context = _public_route_context(_PUBLIC_ROUTE_EQUAL_ROWS)
    first_pivot, second_pivot, sweep_index = 4, 7, 10
    first_level = _PUBLIC_ROUTE_EQUAL_ROWS[first_pivot][2]
    second_level = _PUBLIC_ROUTE_EQUAL_ROWS[second_pivot][2]
    mean_level = (first_level + second_level) / 2.0
    pools = context["liquidity_pools"]

    # Precondition from the fixture: the two lows sit inside the unannotated range tolerance and
    # no canonical record is available on this route.
    assert pools["swing_lows"] == [first_level, second_level]
    assert pools["equal_lows"] == [mean_level]
    assert pools["records"] == []

    sweep_candle = values[sweep_index]
    assert sweep_candle.low < mean_level and sweep_candle.close > mean_level

    events = context["liquidity_sweeps"]["swept_lows"]
    assert [(event["index"], event["level"]) for event in events] == [(sweep_index, mean_level)]
    assert events[0]["reclaimed_at"] == _probe.stamp(sweep_index + 1)
    assert events[0]["source_pool_id"] == f"equal_low:{mean_level:.15g}"
    assert events[0]["source_swing_id"] is None

    # `zone_link_sweeps` scans from the first bar, and the first pivot bar itself crosses the
    # mean (low below it, close above it), so both bars are expected events.
    linked = context["zone_link_sweeps"]["swept_lows"]
    assert [(event["index"], event["level"]) for event in linked] == [
        (first_pivot, mean_level), (sweep_index, mean_level),
    ]
    assert [event["reclaimed_at"] for event in linked] == [
        _probe.stamp(first_pivot + 1), _probe.stamp(sweep_index + 1),
    ]
    assert context["zone_link_sweeps"]["swept_highs"] == []


def test_r72_02_same_time_tie_is_stable_under_claim_permutation():
    claims = [_probe.claim("early", "z-owner", 13),
              _probe.claim("late", "a-nonowner", 13)]
    first = assign_sweep_ownership(claims, history_complete=True)
    second = assign_sweep_ownership(list(reversed(claims)), history_complete=True)
    assert first["assignments"]["sweep"]["owner_setup_id"] == "early"
    assert second["assignments"]["sweep"]["owner_setup_id"] == "early"


@pytest.mark.parametrize("missing_field", ["reclaimed_at", "setup_available_at"])
def test_r72_02_missing_canonical_claim_time_fails_closed(missing_field):
    """A-D02: a canonical claim needs both claim times; missing either fails closed.

    Everything else on the claim stays valid — the remaining time plus pool lineage — so
    the empty result cannot be blamed on another missing field, and neither time is
    allowed to stand in for the other.
    """

    claim = _probe.claim("setup", "child", 13)
    claim.update({"pool_id": "pool-1", "source_ids": ["swing-1"]})
    claim.pop(missing_field)
    kept_field = "setup_available_at" if missing_field == "reclaimed_at" else "reclaimed_at"
    kept_expected = _probe.stamp(13) if missing_field == "reclaimed_at" else _probe.stamp(11)

    assert missing_field not in claim
    assert claim[kept_field] == kept_expected
    assert claim["pool_id"] == "pool-1"
    assert claim["source_ids"] == ["swing-1"]

    result = assign_sweep_ownership([claim], history_complete=True)
    assert result["assignments"] == {}
    assert "SWEEP_CLAIM_TIME_MISSING" in result["reason_codes"]

    # Positive control (A3-014): the same claim with both canonical times does win
    # ownership, so the empty result above comes from the missing field alone and the
    # claim is not being rejected for some unrelated reason.
    complete = _probe.claim("setup", "child", 13)
    complete.update({"pool_id": "pool-1", "source_ids": ["swing-1"]})
    control = assign_sweep_ownership([complete], history_complete=True)
    assert control["assignments"]["sweep"]["owner_setup_id"] == "setup"
    # Both stamps share the same UTC offset, so max() is the A-D02 causal order.
    assert control["assignments"]["sweep"]["claim_eligible_at"] == max(
        _probe.stamp(11), _probe.stamp(13)
    )


def test_r72_03_contribution_is_counted_per_sweep_not_per_list():
    """A3-074: contribution is one per sweep even when the owner claims through many children.

    Two independent sweeps are claimed by the same owner through children from different zone
    families, one duplicate row and extra metadata. Each sweep must carry exactly one contribution
    from that owner and the list-wide total must be two — a cap of one across the whole list would
    be wrong. The contributing child is the deterministic first child of the owner and must not
    change under input permutation.
    """

    def claim(sweep_id, setup_id, zone_id, **extra):
        value = _probe.claim(setup_id, zone_id, 13)
        value["sweep_id"] = sweep_id
        value.update(extra)
        return value

    def contributions(rows):
        result = assign_sweep_ownership(rows, history_complete=True)
        per_sweep: dict[str, int] = {}
        winners: dict[str, str] = {}
        for row in result["claims"]:
            sweep_id = row["sweep_id"]
            applied = bool(row.get("contribution_applied"))
            per_sweep[sweep_id] = per_sweep.get(sweep_id, 0) + int(applied)
            if applied:
                winners[sweep_id] = row["zone_id"]
        return result, per_sweep, winners

    claims = [
        claim("sweep-a", "owner-1", "child-b"),
        claim("sweep-a", "owner-1", "child-a", family="fvg"),
        claim("sweep-a", "owner-1", "child-c", family="ob", note="metadata"),
        claim("sweep-b", "owner-1", "child-d"),
        claim("sweep-b", "owner-1", "child-e", family="fvg"),
    ]

    result, per_sweep, winners = contributions(claims)

    # One owner per sweep; exactly one contribution per sweep; no list-wide cap of one.
    assert {
        sweep_id: assignment["owner_setup_id"]
        for sweep_id, assignment in result["assignments"].items()
    } == {"sweep-a": "owner-1", "sweep-b": "owner-1"}
    assert per_sweep == {"sweep-a": 1, "sweep-b": 1}
    assert sum(per_sweep.values()) == 2
    # Multi-family and metadata rows neither add nor remove a contribution: the deterministic
    # first child of the owner (smallest zone ID) is the only one credited.
    assert winners == {"sweep-a": "child-a", "sweep-b": "child-d"}

    # Permutation keeps both the per-sweep count and the contributing child.
    _permuted, permuted_per_sweep, permuted_winners = contributions(list(reversed(claims)))
    assert permuted_per_sweep == per_sweep
    assert permuted_winners == winners


def test_r72_03_historical_owner_without_current_child_gets_zero_contribution():
    first = assign_sweep_ownership([_probe.claim("owner", "child", 13)], history_complete=True)
    restored = assign_sweep_ownership(
        [], assignment_history=first["assignments"], history_complete=True,
    )
    # A3-076: the owner that survives only in history keeps both its owner and its assignment
    # record, and this window has no child left to contribute from (current contribution 0).
    assert restored["claims"] == []
    assert restored["assignments"]["sweep"] == first["assignments"]["sweep"]
    assert restored["assignments"]["sweep"]["owner_setup_id"] == "owner"


def test_r72_03_duplicate_owner_children_keep_one_contribution_under_permutation():
    claims = [_probe.claim("owner", "child-b", 13),
              _probe.claim("owner", "child-a", 13),
              _probe.claim("owner", "child-a", 13)]
    for ordered in (claims, list(reversed(claims))):
        result = assign_sweep_ownership(ordered, history_complete=True)
        assert sum(c["contribution_applied"] for c in result["claims"]) == 1
        assert all(c["setup_id"] == "owner" for c in result["claims"])


def test_r72_04_context_repeat_after_json_restore_keeps_assignment():
    """A3-078: first run → JSON restore → repeat on the context caller keeps owner and assignment.

    The sweep payload produced by `_attach_zone_sweep_links` is serialized and reloaded before the
    second run, so this is not the in-RAM replay of
    `test_r72_04_acceptance_context_preserves_consumed_assignment_on_replay` (A3-004/A3-046): the
    restored payload itself must stay authoritative for the sweep.
    """

    sweeps = _probe.sweep()
    _probe.attach([_probe.zone("old-child", "original-owner", 13, 100, 110)], sweeps)
    first = copy.deepcopy(sweeps["swept_lows"][0])
    assert first["owner_setup_id"] == "original-owner"
    assert first["consumed"] is True

    # JSON restore: an independent payload, and the recorded assignment survives the round-trip
    # before the repeat touches it.
    restored = json.loads(json.dumps(sweeps))
    assert restored is not sweeps
    restored_event = restored["swept_lows"][0]
    assert restored_event["owner_setup_id"] == first["owner_setup_id"]
    assert restored_event["assignment_id"] == first["assignment_id"]
    assert restored_event["consumed"] is True

    # Repeat on the restored payload with a later child: the recorded assignment stays
    # authoritative, so the later setup takes neither the owner nor a new assignment.
    _probe.attach([_probe.zone("new-child", "later-owner", 15, 100, 110)], restored)
    repeated = restored["swept_lows"][0]
    assert repeated["owner_setup_id"] == first["owner_setup_id"]
    assert repeated["assignment_id"] == first["assignment_id"]
    assert repeated["linked_zone_id"] == first["linked_zone_id"]
    assert repeated["claim_eligible_at"] == first["claim_eligible_at"]
    assert repeated["consumed"] is True


def test_r72_04_assignment_survives_json_restore_with_late_only_window():
    first = assign_sweep_ownership([_probe.claim("original", "child", 13)], history_complete=True)
    restored_history = json.loads(json.dumps(first["assignments"]))
    result = assign_sweep_ownership(
        [_probe.claim("later", "late-child", 15)],
        assignment_history=restored_history,
        history_complete=True,
    )
    assert result["assignments"]["sweep"]["owner_setup_id"] == "original"
    assert result["claims"][0]["owner_setup_id"] == "original"
    assert result["claims"][0]["contribution_applied"] is False


def test_r72_04_caller_same_pool_observation_keeps_consumption():
    """C-R1: the context caller keeps a consumed pool's owner for a later observation.

    `_attach_zone_sweep_links` has to hand the claim its sweep's canonical pool lineage and the
    real reclaim time. If it drops them the claim reads as legacy, the same-pool lookup never runs
    and a new observation of an already-consumed pool is granted a fresh owner.
    """

    sweeps = _probe.sweep()
    # Canonical lineage, exactly what a canonical pool record carries (F06/F07).
    sweeps["swept_lows"][0].update({"source_pool_id": "pool-A", "source_ids": ["source-A"]})
    _probe.attach([_probe.zone("old-child", "original", 13, 100, 110)], sweeps)
    original = copy.deepcopy(sweeps["swept_lows"][0])
    assert original["consumed"] is True
    assert original["owner_setup_id"] == "original"
    assert original["assignment_id"]
    assert original["claim_eligible_at"] == _probe.stamp(13)

    # A NEW observation of the same causal pool: different sweep identity and reclaim time, same
    # pool/source lineage. The consumed sweep stays in the payload, so the history is available.
    observation = _probe.sweep()["swept_lows"][0]
    observation.update({
        "sweep_id": "sweep-later",
        "reclaimed_at": _probe.stamp(12),
        "source_pool_id": "pool-A",
        "source_ids": ["source-A"],
    })
    assert observation["sweep_id"] != original["sweep_id"]
    assert observation["reclaimed_at"] != original["reclaimed_at"]
    assert observation["source_pool_id"] == original["source_pool_id"]
    sweeps["swept_lows"].append(observation)

    # JSON restore between the two runs: the restored payload alone must stay authoritative.
    restored = json.loads(json.dumps(sweeps))
    assert restored is not sweeps
    late_zone = _probe.zone("new-child", "later", 15, 100, 110)
    _probe.attach([late_zone], restored)
    later = restored["swept_lows"][-1]
    assert later["sweep_id"] == "sweep-later"
    assert later["owner_setup_id"] == original["owner_setup_id"]
    assert later["assignment_id"] == original["assignment_id"]
    # The late child owns nothing, so its current contribution stays zero.
    assert late_zone["sweep_owner_setup_id"] == "original"
    assert late_zone["sweep_contribution_applied"] is False
    # The already-consumed sweep keeps its own record through the same pass.
    assert restored["swept_lows"][0]["owner_setup_id"] == original["owner_setup_id"]
    assert restored["swept_lows"][0]["assignment_id"] == original["assignment_id"]

    # Control: an observation of a genuinely different pool is independent of that consumption.
    other = _probe.sweep()["swept_lows"][0]
    other.update({
        "sweep_id": "sweep-other",
        "reclaimed_at": _probe.stamp(12),
        "source_pool_id": "pool-B",
        "source_ids": ["source-B"],
    })
    other_payload = {"swept_lows": [other], "swept_highs": []}
    other_zone = _probe.zone("other-child", "other-setup", 15, 100, 110)
    _probe.attach([other_zone], other_payload)
    fresh = other_payload["swept_lows"][0]
    assert fresh["source_pool_id"] != original["source_pool_id"]
    assert fresh["owner_setup_id"] == "other-setup"
    assert fresh["assignment_id"] != original["assignment_id"]


def test_r72_04_caller_canonical_claim_without_reclaim_time_gets_no_owner():
    """C-R1 (rest): the caller hands the helper the *real* reclaim close, or nothing.

    A canonical sweep that carries pool lineage but no `reclaimed_at` must not have its open time
    substituted for the missing claim time: the claim has to stay incomplete so the ownership step
    fails closed instead of granting an owner, a consumption and a contribution.
    """

    sweeps = _probe.sweep()
    event = sweeps["swept_lows"][0]
    event.update({"source_pool_id": "pool-A", "source_ids": ["source-A"]})
    event.pop("reclaimed_at")
    # Preconditions: canonical lineage, and the open time is still declared while the reclaim
    # close is genuinely missing — so a substituted value could only come from that alias.
    assert event["source_ids"] == ["source-A"]
    assert event["time"] == _probe.stamp(10)
    assert "reclaimed_at" not in event

    incomplete_zone = _probe.zone("child", "owner", 13, 100, 110)
    _probe.attach([incomplete_zone], sweeps)
    incomplete = sweeps["swept_lows"][0]
    # The sweep still links; what is withheld is ownership, consumption and contribution.
    assert incomplete_zone["liquidity_sweep_linked"] is True
    assert incomplete.get("consumed") is not True
    assert not incomplete.get("owner_setup_id")
    assert not incomplete.get("assignment_id")
    assert not incomplete_zone.get("sweep_owner_setup_id")
    assert incomplete_zone.get("sweep_contribution_applied") is not True

    # Control: the same canonical sweep with its real reclaim close does get the owner, so the
    # empty result above comes from the missing claim time alone.
    complete_payload = _probe.sweep()
    complete_payload["swept_lows"][0].update(
        {"source_pool_id": "pool-A", "source_ids": ["source-A"]}
    )
    complete_zone = _probe.zone("child", "owner", 13, 100, 110)
    _probe.attach([complete_zone], complete_payload)
    complete = complete_payload["swept_lows"][0]
    assert complete["consumed"] is True
    assert complete["owner_setup_id"] == "owner"
    assert complete_zone["sweep_owner_setup_id"] == "owner"
    assert complete_zone["sweep_contribution_applied"] is True

    # Legacy compatibility stays green: a sweep without canonical source lineage keeps the
    # documented alias resolution, so one that only declares its open time still gets its owner.
    legacy_payload = _probe.sweep()
    legacy_event = legacy_payload["swept_lows"][0]
    legacy_event.pop("reclaimed_at")
    legacy_event["time"] = _probe.stamp(10)
    legacy_zone = _probe.zone("child", "owner", 13, 100, 110)
    _probe.attach([legacy_zone], legacy_payload)
    legacy = legacy_payload["swept_lows"][0]
    assert legacy["consumed"] is True
    assert legacy["owner_setup_id"] == "owner"
    assert legacy_zone["sweep_contribution_applied"] is True


# --- F11: end-to-end chain from the actual producer to ownership and restore ------------------

def test_r72_chain_actual_producer_pool_sweep_reaches_owner_and_survives_restore():
    """F11(a): the whole chain runs with real producers, not dict-built intermediates.

    The swing producer → pool → sweep chain is the one `_pool_causal_run` already runs (A3-044);
    here its **actual** sweep events are fed to the real `_attach_zone_sweep_links` over the same
    real candles, so the owner, the consumption, the contribution and the assignment identity all
    come from the detector's own evidence. Expected values are derived from the fixture (pivot low
    at index 4, sweeping bar at index 10) and from the zones declared here.
    """

    values = _pool_causal_candles(_POOL_CAUSAL_ROWS)
    _swings, pools, sweeps = _pool_causal_run(values)
    assert [sweep["index"] for sweep in sweeps["swept_lows"]] == [_POOL_CAUSAL_SWEEP_INDEX]
    produced = sweeps["swept_lows"][0]
    level = _POOL_CAUSAL_ROWS[_POOL_CAUSAL_PIVOT_INDEX][2]
    assert produced["level"] == level
    assert produced["reclaimed_at"] == _probe.stamp(_POOL_CAUSAL_SWEEP_INDEX + 1)
    # Precondition: the sweep carries the canonical pool lineage its own record declares.
    record = _pool_record_for(pools, "swing_low", produced["source_ids"])
    assert produced["source_pool_id"] == record["pool_id"]

    def attach(zones, payload):
        _attach_zone_sweep_links(
            (("demand", zones),), payload,
            candles=values, symbol="EURUSD", timeframe="H1", tf_minutes=60,
        )

    owner_zone = _probe.zone("producer-child", "producer-setup", 13, 99.0, 100.0)
    late_zone = _probe.zone("later-child", "later-setup", 15, 99.0, 100.0)
    attach([owner_zone, late_zone], sweeps)

    consumed = sweeps["swept_lows"][0]
    # A-D02: eligibility is the later of the reclaim close and the setup's availability.
    assert consumed["consumed"] is True
    assert consumed["owner_setup_id"] == "producer-setup"
    assert consumed["claim_eligible_at"] == max(
        _probe.stamp(_POOL_CAUSAL_SWEEP_INDEX + 1), _probe.stamp(13)
    )
    assert consumed["linked_zone_id"] == "producer-child"
    assignment_id = consumed["assignment_id"]
    assert assignment_id
    assert owner_zone["sweep_owner_setup_id"] == "producer-setup"
    assert owner_zone["sweep_contribution_applied"] is True
    # The later setup is eligible but loses on claim time, so it takes nothing.
    assert late_zone["liquidity_sweep_linked"] is False
    assert not late_zone.get("sweep_owner_setup_id")
    assert late_zone.get("sweep_contribution_applied") is not True

    # Repeat on the same payload: the recorded consumption keeps the sweep.
    attach([owner_zone], sweeps)
    assert sweeps["swept_lows"][0]["owner_setup_id"] == "producer-setup"
    assert sweeps["swept_lows"][0]["assignment_id"] == assignment_id

    # JSON restore with a late-only window: the restored payload alone stays authoritative.
    restored = json.loads(json.dumps(sweeps))
    assert restored is not sweeps
    late_only = _probe.zone("later-child", "later-setup", 15, 99.0, 100.0)
    attach([late_only], restored)
    repeated = restored["swept_lows"][0]
    assert repeated["owner_setup_id"] == "producer-setup"
    assert repeated["assignment_id"] == assignment_id
    assert repeated["linked_zone_id"] == "producer-child"
    assert repeated["claim_eligible_at"] == consumed["claim_eligible_at"]


def test_r72_04_conflicting_history_is_order_independent_and_fails_closed():
    """C-R2: history that disagrees with itself fails closed, whatever the dict order.

    Two records tied to the same causal pool declare different owners/assignments. Honouring the
    first one found would make the outcome depend on insertion order, so the sweep gets no
    assignment and the conflict group's own reason instead.
    """

    def later_claim():
        return dict(
            _probe.claim("later", "child", 15),
            sweep_id="new-observation",
            reclaimed_at=_probe.stamp(11),
            setup_available_at=_probe.stamp(15),
            pool_id="pool-A",
            source_ids=["source-A"],
        )

    def history(pairs):
        return {
            name: {
                "owner_setup_id": owner,
                "assignment_id": assignment_id,
                "assigned_at": _probe.stamp(13),
                "claim_eligible_at": _probe.stamp(13),
                "pool_id": "pool-A",
                "source_ids": ["source-A"],
            }
            for name, owner, assignment_id in pairs
        }

    conflicting = [("old-1", "first", "id-first"), ("old-2", "second", "id-second")]
    # Precondition: the two orders really differ, so order-independence is what is being tested.
    assert [name for name, _, _ in conflicting] != [
        name for name, _, _ in reversed(conflicting)
    ]

    for ordered in (conflicting, list(reversed(conflicting))):
        result = assign_sweep_ownership(
            [later_claim()], assignment_history=history(ordered), history_complete=True,
        )
        assert result["assignments"] == {}
        assert "SWEEP_OWNER_HISTORY_CONFLICT" in result["reason_codes"]
        # This is the conflict group, not the missing-coverage group.
        assert "SWEEP_OWNER_HISTORY_INCOMPLETE" not in result["reason_codes"]

    # Control: several observations of one pool that agree on the same owner and assignment are
    # consistent, so they stay honourable and report no conflict.
    consistent = history([("old-1", "first", "id-first"), ("old-2", "first", "id-first")])
    control = assign_sweep_ownership(
        [later_claim()], assignment_history=consistent, history_complete=True,
    )
    assert control["reason_codes"] == []
    assert control["assignments"]["new-observation"]["owner_setup_id"] == "first"
    assert control["assignments"]["new-observation"]["assignment_id"] == "id-first"


def test_r72_04_incomplete_history_returns_explicit_reason():
    # The caller declares an unknown/incomplete history window explicitly (A3-006); the
    # claim itself stays canonical, so the empty result cannot be blamed on another
    # missing field (A-D02 claim times, A-D06 pool lineage).
    claim = _probe.claim("late", "child", 15)
    claim.update({"pool_id": "pool-1", "source_ids": ["swing-1"]})
    assert claim["reclaimed_at"] == _probe.stamp(11)
    assert claim["setup_available_at"] == _probe.stamp(15)
    assert claim["pool_id"] == "pool-1"
    assert claim["source_ids"] == ["swing-1"]

    result = assign_sweep_ownership([claim], history_complete=False)
    assert result["assignments"] == {}
    assert result["reason_codes"] == ["SWEEP_OWNER_HISTORY_INCOMPLETE"]


def test_r72_04_same_pool_observation_cannot_bypass_consumption():
    # A3-045: state and verify the initial assignment explicitly — pool/source lineage on the
    # claim, an early owner, an assignment ID, a complete history and a history that survives
    # a JSON round-trip before the next observation is evaluated.
    first_claim = _probe.claim("original", "child", 13)
    first_claim.update({"pool_id": "pool-1", "source_ids": ["swing-1"], "index": 7})
    assert first_claim["pool_id"] == "pool-1"
    assert first_claim["source_ids"] == ["swing-1"]
    assert first_claim["reclaimed_at"] == _probe.stamp(11)
    assert first_claim["setup_available_at"] == _probe.stamp(13)

    first = assign_sweep_ownership([first_claim], history_complete=True)
    assert first["reason_codes"] == []
    initial = first["assignments"]["sweep"]
    assert initial["owner_setup_id"] == "original"
    assert initial["assignment_id"]
    # A-D02: eligibility is the max of the two canonical claim times.
    assert initial["claim_eligible_at"] == max(_probe.stamp(11), _probe.stamp(13))
    assert initial["assigned_at"] == initial["claim_eligible_at"]
    restored_history = json.loads(json.dumps(first["assignments"]))
    assert restored_history == first["assignments"]

    # A3-046: a NEW observation of the same causal pool — different sweep id, observation
    # time and rolling index, but the same pool/source identity — must not bypass the
    # consumption the first observation established.
    later_claim = _probe.claim("later", "late-child", 15)
    later_claim.update({
        "sweep_id": "sweep-later",
        "reclaimed_at": _probe.stamp(17),
        "index": 99,
        "pool_id": "pool-1",
        "source_ids": ["swing-1"],
    })
    # Preconditions: same causal pool identity, different observation identity.
    assert later_claim["pool_id"] == first_claim["pool_id"]
    assert later_claim["source_ids"] == first_claim["source_ids"]
    assert later_claim["sweep_id"] != first_claim["sweep_id"]
    assert later_claim["reclaimed_at"] != first_claim["reclaimed_at"]
    assert later_claim["index"] != first_claim["index"]

    result = assign_sweep_ownership(
        [later_claim], assignment_history=restored_history,
        history_complete=True,
    )
    # The same causal pool keeps the original owner and assignment; the late setup gets no
    # contribution (A-D06).
    assert result["assignments"]["sweep-later"]["owner_setup_id"] == "original"
    assert result["assignments"]["sweep-later"]["assignment_id"] == initial["assignment_id"]
    assert result["claims"][0]["contribution_applied"] is False

    # A3-047 control: a claim on a genuinely NEW pool (new source IDs / causal lineage) is not
    # blocked by the old pool's consumption, so the same-pool rule cannot over-block.
    new_claim = _probe.claim("new-setup", "new-child", 19)
    new_claim.update({
        "sweep_id": "sweep-new",
        "reclaimed_at": _probe.stamp(21),
        "index": 199,
        "pool_id": "pool-2",
        "source_ids": ["swing-2"],
    })
    # Preconditions: new pool identity, not a relabelled copy of the consumed one, and both
    # canonical claim times still valid (from `_probe.claim`).
    assert new_claim["pool_id"] != first_claim["pool_id"]
    assert new_claim["source_ids"] != first_claim["source_ids"]
    assert new_claim["sweep_id"] != first_claim["sweep_id"]
    assert new_claim["reclaimed_at"] == _probe.stamp(21)
    assert new_claim["setup_available_at"] == _probe.stamp(19)

    control = assign_sweep_ownership(
        [new_claim], assignment_history=restored_history,
        history_complete=True,
    )
    assert control["reason_codes"] == []
    assert control["assignments"]["sweep-new"]["owner_setup_id"] == "new-setup"
    assert control["claims"][0]["contribution_applied"] is True


def test_r72_04_conflicting_assignment_history_fails_closed():
    """A3-048: a history record that claims an owner for the sweep without the fields needed
    to honour it conflicts with the current claim — the sweep must not be silently re-granted
    to the current setup, and an explicit reason must be reported.

    The claim itself carries both canonical times and pool lineage, so a failure cannot come
    from missing fixture timestamps.
    """

    claim = _probe.claim("late", "child", 15)
    claim.update({"pool_id": "pool-1", "source_ids": ["swing-1"], "index": 3})

    # Preconditions: the claim is canonical (both times valid, lineage declared).
    assert claim["reclaimed_at"] == _probe.stamp(11)
    assert claim["setup_available_at"] == _probe.stamp(15)
    assert claim["pool_id"] == "pool-1"
    assert claim["source_ids"] == ["swing-1"]

    conflicting_history = {"sweep": {"sweep_id": "sweep", "owner_setup_id": "original"}}
    result = assign_sweep_ownership(
        [claim], assignment_history=conflicting_history, history_complete=True,
    )

    # A3-077: this is the conflict group, not the missing-coverage group — the caller declares a
    # complete history and a record exists — so it must not be reported as missing history.
    assert "SWEEP_OWNER_HISTORY_INCOMPLETE" not in result["reason_codes"]

    # Fail closed: no fresh owner/assignment for the sweep (the history is not reset and the
    # current setup is not granted the sweep), and this group's own reason must be reported.
    assert result["assignments"] == {}
    assert result["reason_codes"]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_05_serialized_terminal_mapping_overrides_legacy_reaction_flags(side):
    state = _probe.lifecycle(
        [(112, 114, 111, 113), (109, 110, 105, 109),
         (112, 114, 111, 113), (100, 101, 98, 99)], side,
    )
    payload = state.to_dict()
    payload.update({
        "lifecycle_status": "invalid",
        "lifecycle_broken": False,
        "broken": False,
        "d1_reaction": True,
        "proximity": True,
    })
    evidence = build_d1_reaction_evidence(
        {"zone_id": "zone", "direction": side}, payload,
        as_of=_probe.stamp(4 * 24),
    )
    assert evidence["valid"] is False
    assert evidence["score"] == 0


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_05_cutoff_equal_invalidated_at_is_terminal(side):
    # A3-049: the chain is outside → touch → exit + reaction → invalidation, so the prefix
    # (the same chain without the invalidation candle) is a real D1 positive — the later
    # terminal assertions cannot pass merely because no reaction ever happened.
    if side == "buy":
        rows = [(112, 114, 111, 113), (105, 111, 105, 108),
                (112, 114, 111, 113), (99, 100, 98, 99)]
    else:
        rows = [(98, 99, 96, 97), (101, 105, 99, 102),
                (98, 99, 96, 97), (111, 112, 109, 111)]
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    values = [Candle(start + timedelta(days=i), *row, volume=100)
              for i, row in enumerate(rows)]
    assert not validate_smc_candles(values, "D1")

    # Prefix positive (A3-049): the visit reacts on the exit candle (D1 close = open + 1 day)
    # and the same zone/visit is reported by the D1 consumer at the pre-terminal cutoff.
    prefix_cutoff = (start + timedelta(days=3)).isoformat()
    prefix = analyze_zone_lifecycle(
        candles=values[:3], low=100, high=110, side=side,
        origin_index=0, departure_end_index=0, zone_id="equal-terminal",
        timeframe="D1", tf_minutes=1440, tick_size=0.1, atr_current=1,
    )
    prefix_visit = prefix.visits[0]
    assert prefix_visit.visit_state == "completed_reacted"
    assert prefix_visit.reacted_at == prefix_cutoff
    positive = build_d1_reaction_evidence(
        {"zone_id": "equal-terminal", "direction": side}, prefix,
        as_of=prefix_cutoff,
    )
    assert positive["valid"] is True
    assert positive["score"] > 0
    assert positive["zone_id"] == "equal-terminal"
    assert positive["source_visit_id"] == prefix_visit.visit_id

    state = analyze_zone_lifecycle(
        candles=values, low=100, high=110, side=side,
        origin_index=0, departure_end_index=0, zone_id="equal-terminal",
        timeframe="D1", tf_minutes=1440, tick_size=0.1, atr_current=1,
    )
    # A3-050: the terminal close (cutoff == invalidated_at) must block the active D1 evidence
    # while the reaction recorded before it stays in the visit history. The rejection must not
    # come from a missing reaction — the prefix positive above proves it completed.
    assert state.invalidated_at == (start + timedelta(days=4)).isoformat()
    assert state.visits[0].reacted_at == prefix_cutoff
    evidence = build_d1_reaction_evidence(
        {"zone_id": "equal-terminal", "direction": side}, state,
        as_of=state.invalidated_at,
    )
    assert evidence["valid"] is False
    assert evidence["score"] == 0
    assert "D1_REACTION_NOT_COMPLETED_REACTED" not in evidence["reason_codes"]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_05_cutoff_equal_expired_at_is_terminal(side):
    """A3-051: the expiry counterpart of the invalidation cutoff — the same chain cut at
    `expired_at` must serve no active D1 evidence while keeping the pre-expiry reaction.

    Before expiry the very same chain is a valid positive (cutoff after the reaction), so a
    pass here cannot come from a stale/no-reaction fixture or from a cutoff set before the
    reaction.
    """

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    values = _terminal_candles(side, 20)
    reaction_close = (start + timedelta(days=21)).isoformat()

    # Pre-expiry positive: the reaction at index 20 is live at its own close.
    prefix = analyze_zone_lifecycle(
        candles=values[:21], low=100, high=110, side=side,
        origin_index=0, departure_end_index=0, zone_id="terminal-zone",
        timeframe="D1", tf_minutes=1440, tick_size=0.1, atr_current=1,
    )
    prefix_visit = prefix.visits[0]
    assert prefix_visit.visit_state == "completed_reacted"
    assert prefix_visit.reacted_at == reaction_close
    positive = build_d1_reaction_evidence(
        {"zone_id": "terminal-zone", "direction": side}, prefix,
        as_of=reaction_close,
    )
    assert positive["valid"] is True
    assert positive["score"] > 0

    state = analyze_zone_lifecycle(
        candles=values, low=100, high=110, side=side,
        origin_index=0, departure_end_index=0, zone_id="terminal-zone",
        timeframe="D1", tf_minutes=1440, tick_size=0.1, atr_current=1,
    )
    # Expiry lands on the first candle past the D1 lifetime (index 21, §Timeline D1 terminal)
    # and the reaction recorded before it stays in the visit history.
    assert state.expiry_index == 21
    assert state.expired_at == (start + timedelta(days=22)).isoformat()
    assert state.visits[0].reacted_at == reaction_close
    evidence = build_d1_reaction_evidence(
        {"zone_id": "terminal-zone", "direction": side}, state,
        as_of=state.expired_at,
    )
    assert evidence["valid"] is False
    assert evidence["score"] == 0
    assert "D1_REACTION_NOT_COMPLETED_REACTED" not in evidence["reason_codes"]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_06_h4_reaction_before_terminal_is_retained(side):
    """A3-034: with the H4 lifetime of 30 bars a reaction at age 30 still precedes the
    terminal candle (index 31), and it keeps the close of its own candle.

    Expected times come from the fixture convention only: H4 close = open + 4h with the
    fixture starting 2026-09-01, so index 29/30/31 close at 00:00/04:00/08:00 on 2026-09-06.
    """

    state = _h4_terminal_lifecycle(side, 30)
    visit = state.visits[0]
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    entry_close = (start + timedelta(hours=4 * 29 + 4)).isoformat()
    exit_close = (start + timedelta(hours=4 * 30 + 4)).isoformat()
    terminal_close = (start + timedelta(hours=4 * 31 + 4)).isoformat()

    assert visit.entered_at == entry_close
    assert visit.exited_at == exit_close
    assert visit.bars_spent_inside >= 1
    # Exit and reaction share the age-30 close, which is still before the terminal candle.
    assert visit.reacted_at == exit_close
    assert visit.visit_state == "completed_reacted"
    assert state.lifecycle_expired is True
    assert state.expiry_index == 31
    assert state.expired_at == terminal_close


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_06_h4_reaction_at_terminal_is_blocked(side):
    """A3-035: an H4 reaction placed on the terminal candle (index 31) must not be created —
    the terminal gate runs before the reaction of that same candle (A-D05).

    The visit really does enter and exit the zone first, so a blocked reaction cannot be
    explained by a zone that was never visited.
    """

    state = _h4_terminal_lifecycle(side, 31)
    visit = state.visits[0]
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    entry_close = (start + timedelta(hours=4 * 29 + 4)).isoformat()
    exit_close = (start + timedelta(hours=4 * 30 + 4)).isoformat()
    terminal_close = (start + timedelta(hours=4 * 31 + 4)).isoformat()

    # Precondition: the reaction candle is exactly the terminal candle (index 31).
    assert state.expiry_index == 31

    assert visit.entered_at == entry_close
    assert visit.exited_at == exit_close
    assert visit.bars_spent_inside >= 1
    assert state.lifecycle_expired is True
    assert state.expired_at == terminal_close
    assert visit.reacted_at is None
    assert visit.visit_state == "completed_unreacted"


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_06_h4_reaction_after_terminal_is_blocked(side):
    """A3-036: an H4 reaction placed after the terminal candle (index 32) must not be
    created, and the visit history established before the terminal candle is retained.

    The trimmed run drops the post-terminal candle, so it shows what the history should be
    once that candle contributes nothing.
    """

    state = _h4_terminal_lifecycle(side, 32)
    visit = state.visits[0]
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    entry_close = (start + timedelta(hours=4 * 29 + 4)).isoformat()
    exit_close = (start + timedelta(hours=4 * 30 + 4)).isoformat()
    terminal_close = (start + timedelta(hours=4 * 31 + 4)).isoformat()

    # Precondition: the terminal candle is index 31 even though the reaction is at 32.
    assert state.expiry_index == 31

    assert visit.entered_at == entry_close
    assert visit.exited_at == exit_close
    assert visit.bars_spent_inside >= 1
    assert state.lifecycle_expired is True
    assert state.expired_at == terminal_close
    assert visit.reacted_at is None
    assert visit.visit_state == "completed_unreacted"

    # The post-terminal candle must not change the visit history.
    trimmed = _h4_terminal_lifecycle(
        side, 32, candles=_h4_terminal_candles(side, 32)[:32],
    )
    assert trimmed.visits[0] == visit


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("reaction_index", [20, 21, 22])
def test_r72_06_terminal_order_before_reaction_is_explicit(side, reaction_index):
    state = _terminal_lifecycle(side, reaction_index)
    visit = state.visits[0]
    if reaction_index == 20:
        # A3-030: the reaction lands on the age-20 candle close (index 20, D1 close =
        # open + 1 day for the fixture starting 2026-09-01) and keeps that exact timestamp
        # after the terminal candle is appended — history is retained, not re-timed.
        expected_reacted_at = (
            datetime(2026, 9, 1, tzinfo=timezone.utc) + timedelta(days=21)
        ).isoformat()
        prefix = _terminal_lifecycle(
            side, reaction_index, candles=_terminal_candles(side, reaction_index)[:21],
        )
        assert prefix.visits[0].reacted_at == expected_reacted_at
        assert prefix.visits[0].visit_state == "completed_reacted"
        assert prefix.lifecycle_expired is False
        assert visit.reacted_at == expected_reacted_at
        assert visit.visit_state == "completed_reacted"
    else:
        # A3-031/A3-032: the zone really is entered and exited before the terminal candle,
        # so "no reaction" cannot pass because the zone was never visited. The terminal
        # index and its close come from the fixture (D1 close = open + 1 day, start
        # 2026-09-01) plus the D1 lifetime of 20 bars — see §Timeline D1 terminal.
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        assert visit.entered_at == (start + timedelta(days=20)).isoformat()
        assert visit.exited_at == (start + timedelta(days=21)).isoformat()
        assert visit.bars_spent_inside >= 1
        assert state.lifecycle_expired is True
        assert state.expiry_index == 21
        assert state.expired_at == (start + timedelta(days=22)).isoformat()
        assert visit.reacted_at is None
        assert visit.visit_state == "completed_unreacted"
        # A3-032: the post-terminal candle must not change the visit history — dropping it
        # (same fixture without the last candle) yields exactly the same visit.
        trimmed = _terminal_lifecycle(
            side, reaction_index, candles=_terminal_candles(side, reaction_index)[:22],
        )
        assert trimmed.visits[0] == visit


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_06_invalidation_precedes_expiry_and_reaction(side):
    # A3-037: the invalidation sits on the candle that ends the D1 lifetime (age 21 = index
    # 21, see §Timeline D1 terminal), where expiry would also apply. The exit at index 20
    # opens the follow-through window (20…23) and the invalidation inside that window blocks
    # the prospective reaction; no candle both breaks the distal boundary and reacts the
    # opposite way.
    if side == "buy":
        rows = [(112, 114, 111, 113)] * 22
        rows[19] = (109, 110, 105, 109)
        rows[20] = (110.2, 110.22, 110.15, 110.2)
        rows[21] = (99, 100, 98, 99)
    else:
        rows = [(98, 99, 96, 97)] * 22
        rows[19] = (101, 105, 99, 102)
        rows[20] = (99.8, 99.85, 99.78, 99.8)
        rows[21] = (111, 112, 109, 111)
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    values = [Candle(start + timedelta(days=i), *row, volume=100)
              for i, row in enumerate(rows)]
    assert not validate_smc_candles(values, "D1")
    state = analyze_zone_lifecycle(
        candles=values, low=100, high=110, side=side,
        origin_index=0, departure_end_index=0, zone_id="terminal-zone",
        timeframe="D1", tf_minutes=1440, tick_size=0.1, atr_current=1,
    )
    assert state.lifecycle_broken is True
    assert state.invalidation_index == 21
    assert state.invalidated_at == (start + timedelta(days=22)).isoformat()
    # Invalidation takes priority over expiry on the same lifetime-boundary candle.
    assert state.expiry_index is None
    assert state.lifecycle_expired is False
    visit = state.visits[0]
    assert visit.entered_at == (start + timedelta(days=20)).isoformat()
    assert visit.exited_at == (start + timedelta(days=21)).isoformat()
    assert visit.visit_state == "completed_unreacted"
    assert visit.reacted_at is None


@pytest.mark.parametrize("side", ["buy", "sell"])
@pytest.mark.parametrize("terminal_kind", ["expired", "invalid"])
def test_r72_06_terminal_state_survives_enrich_restore_enrich(side, terminal_kind):
    """A3-038: a terminal zone keeps its state — status, usability, terminal time and the
    reaction history from before the terminal candle — across enrich → serialize → restore →
    enrich, and it creates no new reaction.

    Expected values come from the fixture plus the D1 rules (§Timeline D1 terminal): the
    reaction lands on the age-20 close and the terminal candle is index 21.
    """

    if terminal_kind == "expired":
        # Same shape as `_terminal_candles(side, 20)`: reaction at age 20, lifetime ends at
        # index 21 without an invalidation.
        values = _terminal_candles(side, 20)
        expected_status = "expired"
    else:
        # Same chain, but the lifetime-boundary candle invalidates instead of expiring.
        start = datetime(2026, 9, 1, tzinfo=timezone.utc)
        if side == "buy":
            rows = [(112, 114, 111, 113)] * 23
            rows[19] = (109, 110, 105, 109)
            rows[20] = (112, 114, 111, 113)
            rows[21] = (99, 100, 98, 99)
        else:
            rows = [(98, 99, 96, 97)] * 23
            rows[19] = (101, 105, 99, 102)
            rows[20] = (98, 99, 96, 97)
            rows[21] = (111, 112, 109, 111)
        values = [
            Candle(start + timedelta(days=i), *row, volume=100)
            for i, row in enumerate(rows)
        ]
        assert not validate_smc_candles(values, "D1")
        expected_status = "invalid"

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    expected_reacted_at = (start + timedelta(days=21)).isoformat()
    terminal_close = (start + timedelta(days=22)).isoformat()
    item = _metadata_item(side, tick_size=0.1)

    context = enrich_zones(
        [item], values, "ob", {}, {"status": "unknown"},
        timeframe="D1", tf_minutes=1440,
    )[0]
    restored = enrich_zones(
        [json.loads(json.dumps(context))], values, "ob", {}, {"status": "unknown"},
        timeframe="D1", tf_minutes=1440,
    )[0]

    # Same zone identity and terminal state after the round-trip.
    assert restored["zone_id"] == context["zone_id"]
    assert context["lifecycle_status"] == expected_status
    assert restored["lifecycle_status"] == expected_status
    assert restored["usable"] is False

    # The reaction from before the terminal candle is retained and no new one appears.
    first_visits = [(visit["reacted_at"], visit["visit_state"]) for visit in context["visits"]]
    second_visits = [(visit["reacted_at"], visit["visit_state"]) for visit in restored["visits"]]
    assert first_visits[0][0] == expected_reacted_at
    assert second_visits == first_visits

    if terminal_kind == "invalid":
        assert restored["invalidated_at"] == terminal_close
        assert restored["invalidation_index"] == 21
        assert restored["lifecycle_expired"] is False
    else:
        assert restored["expired_at"] == terminal_close
        assert restored["expiry_index"] == 21
        assert restored["lifecycle_broken"] is False

    # The D1 consumer still refuses to serve the terminal zone as active evidence.
    evidence = build_d1_reaction_evidence(
        {"zone_id": restored["zone_id"], "direction": side}, restored,
        as_of=terminal_close,
    )
    assert evidence["valid"] is False
    assert evidence["score"] == 0


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_07_item_and_argument_tick_sources_have_parity(side):
    """A3-019 / A-D07: item-only, argument-only and equal-both declare the same tick scope.

    Each variant must reach the same absolute threshold and state derived from the fixture
    (tick 0.1, ATR 1 ⇒ max(tick, 0.05*ATR) = 0.1); comparing the three results with each
    other alone would also pass if all three were wrong.
    """

    # Close 99.98 (mirrored for SELL) stays inside the 0.1 buffer, so the zone stays live.
    values = _probe.candles([(112, 114, 111, 113), (100, 101, 99.95, 99.98)], side)
    item_with_tick = _metadata_item(side, tick_size=0.1)
    item_without_tick = _metadata_item(side)

    # The three variants really do declare the tick differently.
    assert item_with_tick["tick_size"] == 0.1
    assert "tick_size" not in item_without_tick

    results = {
        "item_only": _metadata_result(item_with_tick, values=values),
        "argument_only": _metadata_result(item_without_tick, values=values, tick_size=0.1),
        "equal_both": _metadata_result(item_with_tick, values=values, tick_size=0.1),
    }

    for name, result in results.items():
        assert result["invalidation_buffer"] == pytest.approx(0.1), name
        assert result["lifecycle_broken"] is False, name
        assert result["lifecycle_status"] == "confirmed", name


def test_r72_07_missing_canonical_atr_is_unknown_and_unusable():
    """A3-015: a valid tick with a missing ATR must not fall back to a zero threshold.

    The zone is not terminal (close inside the zone, no expiry), so lifecycle keeps
    `confirmed`/`broken=False` while the ATR-dependent threshold becomes unknown.
    """

    values = _probe.candles([(112, 114, 111, 113), (102, 103, 101, 102.5)])
    item = _metadata_item(atr_current=None, tick_size=0.1)

    # Preconditions: tick valid, zone not terminal.
    assert item["tick_size"] == 0.1
    assert item["atr_current"] is None
    assert item["low"] < values[-1].close < item["high"]

    result = _metadata_result(item, values=values)

    # No terminal evidence: lifecycle status and broken flag are kept as-is.
    assert result["lifecycle_expired"] is False
    assert result["lifecycle_status"] == "confirmed"
    assert result["broken"] is False

    # Missing ATR is a data-quality state, not a lifecycle status.
    assert result["metadata_state"] == "unknown"
    assert isinstance(result["metadata_reason"], str) and result["metadata_reason"].strip()
    assert result["usable"] is False
    # The threshold depending on ATR is not computable: None, never 0 or NaN.
    assert result["invalidation_buffer"] is None

    # Positive control: the same fixture with a valid ATR yields a computable threshold
    # (max(tick, 0.05*ATR) = 0.1) and keeps the zone non-terminal, so the None above is
    # specific to the missing ATR rather than to the fixture.
    control = _metadata_result(_metadata_item(tick_size=0.1), values=values)
    assert control["invalidation_buffer"] == pytest.approx(0.1)
    assert control["lifecycle_status"] == "confirmed"
    assert control["broken"] is False


def test_r72_07_missing_canonical_tick_is_unknown_and_unusable():
    """A3-016: a valid ATR with a missing tick must not fall back to digits or threshold 0.

    Same semantics as the missing-ATR case: the zone is not terminal, so lifecycle keeps
    `confirmed`/`broken=False` while the tick-dependent threshold becomes unknown.
    """

    values = _probe.candles([(112, 114, 111, 113), (102, 103, 101, 102.5)])
    item = _metadata_item()

    # Preconditions: ATR valid, no tick source declared at all (no digits/point fallback),
    # zone not terminal.
    assert item["atr_current"] == 1
    assert all(key not in item for key in ("tick_size", "digits", "point"))
    assert item["low"] < values[-1].close < item["high"]

    result = _metadata_result(item, values=values)

    # No terminal evidence: lifecycle status and broken flag are kept as-is.
    assert result["lifecycle_expired"] is False
    assert result["lifecycle_status"] == "confirmed"
    assert result["broken"] is False

    # Missing tick is a data-quality state, not a lifecycle status.
    assert result["metadata_state"] == "unknown"
    assert isinstance(result["metadata_reason"], str) and result["metadata_reason"].strip()
    assert result["usable"] is False
    # The threshold is not computable: None, never a digits-derived or zero threshold.
    assert result["invalidation_buffer"] is None

    # Positive control: the same fixture with a declared tick yields a computable threshold
    # (max(tick, 0.05*ATR) = 0.1), so the None above is specific to the missing tick.
    control = _metadata_result(_metadata_item(tick_size=0.1), values=values)
    assert control["invalidation_buffer"] == pytest.approx(0.1)
    assert control["lifecycle_status"] == "confirmed"
    assert control["broken"] is False


@pytest.mark.parametrize("terminal_state", ["expired_by_age", "already_invalid"])
def test_r72_07_unknown_metadata_does_not_revive_terminal_zone(terminal_state):
    """A3-020: unknown metadata keeps the terminal zone terminal — it neither becomes
    `confirmed` again nor regains `usable`, and the visit/reaction history stays.

    Expiry is age-based, so it does not depend on the missing tick; the invalid case starts
    from a zone that already carries terminal evidence in the input payload.
    """

    if terminal_state == "expired_by_age":
        rows = [(105, 106, 104, 105.5)] * 52   # H1 lifetime is 50 bars
        item = _metadata_item()
        expected_status, expected_visit = "expired", "open"
    else:
        rows = [(112, 114, 111, 113), (99, 100, 98, 99)]
        item = _metadata_item(lifecycle_status="invalid", broken=True, usable=False)
        expected_status, expected_visit = "invalid", "closed_by_invalidation"
    values = _probe.candles(rows)

    # Preconditions: ATR valid, no tick source declared at all.
    assert item["atr_current"] == 1
    assert all(key not in item for key in ("tick_size", "digits", "point"))

    result = _metadata_result(item, values=values)

    # The terminal state and its history survive; the zone is not revived.
    assert result["lifecycle_status"] == expected_status
    assert result["lifecycle_status"] != "confirmed"
    assert result["lifecycle_expired"] is (terminal_state == "expired_by_age")
    assert result["usable"] is False
    assert result["visits"], "visit/reaction history must be retained"
    assert result["visits"][0]["visit_state"] == expected_visit

    # Metadata is unknown, never a silent zero threshold.
    assert result["metadata_state"] == "unknown"
    assert isinstance(result["metadata_reason"], str) and result["metadata_reason"].strip()
    assert result["invalidation_buffer"] is None

    # Control: the same fixture with a declared tick reaches the same terminal state, so the
    # terminal evidence does not come from the missing metadata.
    control = _metadata_result({**item, "tick_size": 0.1}, values=values)
    assert control["lifecycle_status"] == expected_status
    assert control["usable"] is False


def test_r72_07_metadata_survives_context_to_typed_round_trip():
    """A3-021: the metadata representation must survive lifecycle → context → typed → JSON.

    Expected values come from the A3-007 contract (unknown ⇒ unusable, threshold `None`),
    not from the production payload: a missing ATR leaves the threshold uncomputable and the
    zone unusable.  The identity assertions are the control that the round-trip itself works.
    """

    values = _probe.candles([(112, 114, 111, 113), (102, 103, 101, 102.5)])
    item = _metadata_item(atr_current=None, tick_size=0.1)

    # Preconditions: tick valid, ATR missing, zone not terminal.
    assert item["tick_size"] == 0.1
    assert item["atr_current"] is None
    assert item["low"] < values[-1].close < item["high"]

    context = _metadata_result(item, values=values)

    # lifecycle → context: unknown metadata is represented explicitly.
    assert context["metadata_state"] == "unknown"
    assert isinstance(context["metadata_reason"], str) and context["metadata_reason"].strip()
    assert context["usable"] is False
    assert context["invalidation_buffer"] is None

    # context → typed → JSON: the same representation is kept.
    restored = SmcZone.from_dict(json.loads(json.dumps(context))).to_dict()
    assert restored["metadata_state"] == "unknown"
    assert isinstance(restored["metadata_reason"], str) and restored["metadata_reason"].strip()
    assert restored["usable"] is False

    # Control: the round-trip carries the rest of the lifecycle projection, so a missing
    # metadata field is a real gap rather than a broken round-trip.
    assert restored["zone_id"] == "zone"
    assert (restored["low"], restored["high"]) == (100.0, 110.0)
    assert restored["lifecycle_status"] == "confirmed"
    assert len(restored["visits"]) == 1


def test_r72_05_zone_nonterminal_defaults_cannot_mask_active_lifecycle_terminal():
    """B-R1: terminal evidence on the actual lifecycle must not be masked by default or
    explicitly non-terminal flags on the zone mapping (F05, `build_d1_reaction_evidence`).

    The lifecycle below really is broken after a completed reaction, so the consumer must
    reject it; a zone that merely carries `confirmed`/False/`age_bars=0` defaults cannot
    overwrite that. The control keeps the same non-terminal zone shape against a lifecycle
    that is genuinely not terminal, so the rejection is attributable to the terminal source.
    """

    terminal_state = _probe.lifecycle(
        [(112, 114, 111, 113), (109, 110, 105, 109),
         (112, 114, 111, 113), (99, 100, 98, 99)],
        "buy",
    )
    assert terminal_state.lifecycle_broken is True
    assert terminal_state.visits[0].visit_state == "completed_reacted"

    defaulted_zone = {
        "zone_id": "zone",
        "direction": "buy",
        "lifecycle_status": "confirmed",
        "broken": False,
        "lifecycle_broken": False,
        "lifecycle_expired": False,
        "lifecycle_stale": False,
        "age_bars": 0,
    }
    evidence = build_d1_reaction_evidence(defaulted_zone, terminal_state)
    assert evidence["valid"] is False
    assert evidence["score"] == 0
    assert evidence["reason_codes"] == ["D1_REACTION_STALE"]

    # Control: same non-terminal zone shape, but neither source is terminal ⇒ valid positive.
    live_state = _probe.lifecycle(
        [(112, 114, 111, 113), (109, 110, 105, 109), (112, 114, 111, 113)], "buy",
    )
    assert live_state.lifecycle_broken is False
    assert live_state.lifecycle_expired is False
    live = build_d1_reaction_evidence(defaulted_zone, live_state)
    assert live["valid"] is True
    assert live["score"] > 0


def test_r72_07_known_expired_is_preserved_when_metadata_is_missing():
    """B-R2: a payload that already declares `expired` keeps its terminal kind, timestamp and
    history when the metadata cannot recompute it — no invalidation is invented from an
    unavailable threshold (A3-007 §4)."""

    values = _probe.candles(
        [(112, 114, 111, 113), (112, 114, 111, 113), (100, 101, 99.9, 99.98)]
    )
    expired_at = _probe.stamp(2)
    item = dict(
        zone_id="zone", type="bullish_ob", family="ob", direction="buy",
        origin_index=0, departure_end_index=1, low=100, high=110,
        available_at=_probe.stamp(1), atr_current=1,
        lifecycle_status="expired", usable=False, expired_at=expired_at,
    )
    result = enrich_zones(
        [item], values, "ob", {}, {"status": "unknown"}, timeframe="H1",
    )[0]

    # Preconditions: the metadata really is unusable, so nothing can be recomputed from it.
    assert result["metadata_state"] == "unknown"
    assert result["invalidation_buffer"] is None

    # The known terminal is preserved verbatim rather than converted into an invalidation.
    assert result["lifecycle_status"] == "expired"
    assert result["expired_at"] == expired_at
    assert result["lifecycle_expired"] is True
    assert result["lifecycle_broken"] is False
    assert result["broken"] is False
    assert result["usable"] is False
    assert "ZONE_INVALIDATED" not in result["reason_codes"]

    # B-R2 (over-lifetime window): with a D1 series long enough that the derivation really
    # expires, the declared terminal still outranks it. Anchor = index 0 (first close already
    # >= available_at), lifetime D1 = 20 ⇒ the first over-lifetime index is 21 and its close is
    # open + 1 day = stamp(24 * 22) — computed from the fixture, not read from the output.
    long_values = _probe.candles([(112, 114, 111, 113)] * 25, hours=24)
    long_item = dict(item, expired_at=_probe.stamp(48))
    long_result = enrich_zones(
        [long_item], long_values, "ob", {}, {"status": "unknown"},
        timeframe="D1", tf_minutes=1440,
    )[0]
    assert long_result["metadata_state"] == "unknown"
    assert long_result["invalidation_buffer"] is None
    assert long_result["lifecycle_status"] == "expired"
    assert long_result["expired_at"] == _probe.stamp(48)
    assert long_result["expired_at"] != _probe.stamp(24 * 22)  # not the derived boundary
    assert long_result["lifecycle_expired"] is True
    assert long_result["lifecycle_broken"] is False
    assert long_result["usable"] is False


def test_r72_07_known_invalid_is_preserved_when_metadata_is_missing():
    """B-R2 (invalid counterpart): a declared `invalid` keeps its own terminal kind and the
    timestamp it came with when the metadata cannot recompute the derivation."""

    values = _probe.candles([(112, 114, 111, 113), (99, 100, 98, 99)])
    invalidated_at = _probe.stamp(2)
    item = dict(
        zone_id="zone", type="bullish_ob", family="ob", direction="buy",
        origin_index=0, departure_end_index=1, low=100, high=110,
        available_at=_probe.stamp(1), atr_current=1,
        lifecycle_status="invalid", usable=False, broken=True,
        invalidated_at=invalidated_at,
    )
    result = enrich_zones(
        [item], values, "ob", {}, {"status": "unknown"}, timeframe="H1",
    )[0]

    assert result["metadata_state"] == "unknown"
    assert result["invalidation_buffer"] is None
    assert result["lifecycle_status"] == "invalid"
    assert result["invalidated_at"] == invalidated_at
    assert result["broken"] is True
    assert result["lifecycle_broken"] is True
    assert result["usable"] is False
    assert "ZONE_INVALIDATED" in result["reason_codes"]
    assert result["expired_at"] is None

    # B-R2 (over-lifetime window): the derivation would expire here (same D1 series as above),
    # yet the declared invalidation keeps both its kind and its own timestamp.
    long_values = _probe.candles([(112, 114, 111, 113)] * 25, hours=24)
    long_item = dict(item, invalidated_at=_probe.stamp(48))
    long_result = enrich_zones(
        [long_item], long_values, "ob", {}, {"status": "unknown"},
        timeframe="D1", tf_minutes=1440,
    )[0]
    assert long_result["metadata_state"] == "unknown"
    assert long_result["invalidation_buffer"] is None
    assert long_result["lifecycle_status"] == "invalid"
    assert long_result["invalidated_at"] == _probe.stamp(48)
    assert long_result["broken"] is True
    assert long_result["lifecycle_broken"] is True
    assert long_result["lifecycle_expired"] is False
    assert long_result["expired_at"] is None
    assert long_result["usable"] is False
    assert "ZONE_INVALIDATED" in long_result["reason_codes"]
    assert "ZONE_EXPIRED" not in long_result["reason_codes"]

    # B-R2 (history): when the metadata cannot recompute the derivation, the history the payload
    # already carries is preserved — the terminal visit must not be rewritten into a reaction
    # past the known invalidation, and the caller's own payload must not be mutated.
    history_rows = [
        (112, 114, 111, 113), (109, 110, 105, 109), (112, 114, 111, 113),
        (99, 100, 98, 99), (109, 110, 105, 109), (112, 114, 111, 113),
    ]
    history_state = _probe.lifecycle(history_rows, "buy")
    state_payload = history_state.to_dict()
    assert history_state.invalidated_at == _probe.stamp(96)  # close of index 3
    assert [(visit["visit_state"], visit["reacted_at"]) for visit in state_payload["visits"]] == [
        ("completed_reacted", _probe.stamp(72)),
        ("closed_by_invalidation", None),
    ]

    history_item = dict(
        zone_id="zone", type="bullish_ob", family="ob", direction="buy",
        origin_index=0, departure_end_index=0, low=100, high=110, atr_current=1,
        lifecycle_status="invalid", broken=True, usable=False,
        invalidated_at=state_payload["invalidated_at"],
        invalidation_index=state_payload["invalidation_index"],
        visits=copy.deepcopy(state_payload["visits"]),
    )
    snapshot = copy.deepcopy(history_item)
    history_result = enrich_zones(
        [history_item], _probe.candles(history_rows, hours=24), "ob", {},
        {"status": "unknown"}, timeframe="D1", tf_minutes=1440,
    )[0]

    assert history_item == snapshot, "the caller's payload must not be mutated"
    assert history_result["metadata_state"] == "unknown"
    assert history_result["lifecycle_status"] == "invalid"
    assert history_result["invalidated_at"] == _probe.stamp(96)
    visits = history_result["visits"]
    assert len(visits) == 2
    assert visits[0]["visit_state"] == "completed_reacted"
    assert visits[0]["reacted_at"] == _probe.stamp(72)
    assert visits[1]["visit_state"] == "closed_by_invalidation"
    assert visits[1]["reacted_at"] is None
    # No reaction may appear at or after the known terminal.
    assert all(
        visit["reacted_at"] is None
        or datetime.fromisoformat(visit["reacted_at"])
        <= datetime.fromisoformat(_probe.stamp(96))
        for visit in visits
    )


@pytest.mark.parametrize("nonfinite_field", ["atr_current", "tick_size"])
def test_r72_07_nonfinite_canonical_metadata_is_unknown_and_unusable(nonfinite_field):
    """A3-017: a non-finite ATR or tick is unknown — separate from a missing field and
    never a zero threshold.

    The other metadata field stays valid and the zone is not terminal, so the unknown
    state can only come from the non-finite value.
    """

    valid_values = {"atr_current": 1, "tick_size": 0.1}
    other_field = "tick_size" if nonfinite_field == "atr_current" else "atr_current"
    values = _probe.candles([(112, 114, 111, 113), (102, 103, 101, 102.5)])
    item = _metadata_item(**{**valid_values, nonfinite_field: float("nan")})

    # Preconditions: the other field valid, the field under test non-finite, zone open.
    assert item[other_field] == valid_values[other_field]
    assert math.isnan(item[nonfinite_field])
    assert item["low"] < values[-1].close < item["high"]

    result = _metadata_result(item, values=values)

    # No terminal evidence: lifecycle status and broken flag are kept as-is.
    assert result["lifecycle_expired"] is False
    assert result["lifecycle_status"] == "confirmed"
    assert result["broken"] is False

    # Non-finite metadata is a data-quality state, not a lifecycle status.
    assert result["metadata_state"] == "unknown"
    assert isinstance(result["metadata_reason"], str) and result["metadata_reason"].strip()
    assert result["usable"] is False
    # Not computable from a non-finite input: None, never 0 or NaN.
    assert result["invalidation_buffer"] is None


def test_r72_07_conflicting_same_scope_tick_sources_fail_closed():
    """A3-018 / A-D07: the item tick and the argument tick are the same scope, so a
    conflict is unknown data quality — never a lifecycle status, and neither declared
    value may win silently.
    """

    argument_tick = 0.1
    values = _probe.candles([(112, 114, 111, 113), (102, 103, 101, 102.5)])
    item = _metadata_item(tick_size=0.2)

    # Preconditions: two declared same-scope tick values that disagree, a valid ATR, and a
    # zone that is not terminal — so "unknown" can only come from the conflict itself.
    assert item["tick_size"] == 0.2
    assert item["tick_size"] != argument_tick
    assert item["atr_current"] == 1
    assert item["low"] < values[-1].close < item["high"]

    result = _metadata_result(item, values=values, tick_size=argument_tick)

    # No terminal evidence: lifecycle status and broken flag are kept as-is.
    assert result["lifecycle_expired"] is False
    assert result["lifecycle_status"] == "confirmed"
    assert result["broken"] is False

    # The conflict is a data-quality state, not a lifecycle status.
    assert result["metadata_state"] == "unknown"
    assert isinstance(result["metadata_reason"], str) and result["metadata_reason"].strip()
    assert result["usable"] is False
    # Neither declared value (0.1 or 0.2) is used as the threshold.
    assert result["invalidation_buffer"] is None


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_07_equal_and_outside_buffer_buy_sell(side):
    if side == "buy":
        exact_rows = [(112, 114, 111, 113), (100, 101, 99.9, 99.9)]
        beyond_rows = [(112, 114, 111, 113), (99.89, 100, 98, 99.89)]
    else:
        exact_rows = [(98, 99, 96, 97), (110, 110.1, 109.5, 110.1)]
        beyond_rows = [(98, 99, 96, 97), (110.11, 111, 109, 110.11)]
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def run(rows):
        # A3-028: the fixture is H1, so the cadence is one hour per candle — a day step
        # would silently exercise a different gap path than the timeframe under test.
        values = [Candle(start + timedelta(hours=i), *row, volume=100)
                  for i, row in enumerate(rows)]
        assert values[1].time - values[0].time == timedelta(hours=1)
        assert not validate_smc_candles(values, "H1")
        return analyze_zone_lifecycle(
            candles=values, low=100, high=110, side=side,
            origin_index=0, departure_end_index=0, zone_id="buffer-boundary",
            timeframe="H1", tf_minutes=60, tick_size=0.1, atr_current=2,
        )

    exact = run(exact_rows)
    beyond = run(beyond_rows)
    assert exact.invalidation_buffer == pytest.approx(0.1)
    assert exact.lifecycle_broken is False
    assert beyond.lifecycle_broken is True


def test_r72_08_invalid_canonical_zone_survives_typed_round_trip_consistently():
    payload = {
        "type": "bullish_order_block", "symbol": "EUR/USD", "timeframe": "H4",
        "family": "ob", "direction": "buy", "zone_id": "invalid-zone",
        "low": 99, "high": 101, "origin_index": 3,
        "origin_time": "2026-09-10T08:00:00+00:00",
        "created_at": "2026-09-10T08:00:00+00:00",
        "lifecycle_status": "invalid", "lifecycle_broken": True, "broken": True,
        "usable": False, "invalidated_at": "2026-09-10T12:00:00+00:00",
        "invalidation_index": 4, "reason_codes": ["ZONE_INVALIDATED"],
    }
    restored = SmcZone.from_dict(payload)
    round_trip = restored.to_dict()
    assert restored.lifecycle_status == "invalid"
    assert restored.broken is True
    assert round_trip["lifecycle_status"] == "invalid"
    assert round_trip["usable"] is False


@pytest.mark.parametrize("legacy_broken", [False, True])
def test_r72_08_canonical_invalid_status_wins_legacy_boolean(legacy_broken):
    payload = {
        "type": "bullish_order_block", "symbol": "EUR/USD", "timeframe": "H4",
        "family": "ob", "direction": "buy", "zone_id": "invalid-zone",
        "low": 99, "high": 101, "origin_index": 3,
        "origin_time": "2026-09-10T08:00:00+00:00",
        "created_at": "2026-09-10T08:00:00+00:00", "lifecycle_status": "invalid",
        "lifecycle_broken": legacy_broken, "broken": legacy_broken,
        "usable": False, "reason_codes": ["ZONE_INVALIDATED"],
    }
    restored = SmcZone.from_dict(payload)
    assert restored.lifecycle_status == "invalid"
    assert restored.broken is True


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_08_typed_terminal_projection_reaches_d1_consumer(side):
    # A3-052: the D1 consumer must read a real typed `SmcZone` round-trip — the payload keeps
    # the lifecycle visit's zone id, declares the D1 timeframe, and the cutoff is strictly
    # after the reaction, so the verdict cannot come from an id mismatch or a cutoff set
    # before the reaction.
    state = _probe.lifecycle(
        [(112, 114, 111, 113), (109, 110, 105, 109),
         (112, 114, 111, 113)], side,
    )
    visit = state.visits[0]
    assert visit.visit_state == "completed_reacted"
    assert visit.reacted_at == _probe.stamp(3 * 24)
    cutoff = _probe.stamp(4 * 24)
    assert visit.reacted_at < cutoff

    payload = SmcZone.from_dict({
        "zone_id": visit.zone_id,
        "direction": side,
        "timeframe": "D1",
        "family": "ob",
        "zone_type": "bullish_ob" if side == "buy" else "bearish_ob",
        "low": 100.0,
        "high": 110.0,
        "origin_index": 0,
        "origin_time": _probe.stamp(0),
        "lifecycle_status": "invalid",
        "broken": True,
        "invalidated_at": cutoff,
    }).to_dict()
    assert payload["zone_id"] == visit.zone_id
    assert payload["timeframe"] == "D1"
    assert payload["lifecycle_status"] == "invalid"

    evidence = build_d1_reaction_evidence(payload, state, as_of=cutoff)
    assert evidence["valid"] is False
    assert evidence["score"] == 0
    # The verdict must not come from a mismatched zone id or a pre-reaction cutoff.
    assert "D1_REACTION_NOT_COMPLETED_REACTED" not in evidence["reason_codes"]
    assert "D1_REACTION_AFTER_CUTOFF" not in evidence["reason_codes"]


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_08_typed_d1_projection_keeps_valid_reaction(side):
    """A3-053: control for the typed D1 path — a non-terminal zone round-tripped through
    `SmcZone.from_dict(...).to_dict()` keeps its id, bounds, times and visits, and the D1
    consumer still serves the valid reaction. Without this, the terminal case could look
    "correct" merely because the typed payload fails for every zone.
    """

    state = _probe.lifecycle(
        [(112, 114, 111, 113), (109, 110, 105, 109),
         (112, 114, 111, 113)], side,
    )
    visit = state.visits[0]
    assert visit.visit_state == "completed_reacted"
    cutoff = _probe.stamp(4 * 24)
    assert visit.reacted_at < cutoff

    payload = SmcZone.from_dict({
        "zone_id": visit.zone_id,
        "direction": side,
        "timeframe": "D1",
        "family": "ob",
        "zone_type": "bullish_ob" if side == "buy" else "bearish_ob",
        "low": 100.0,
        "high": 110.0,
        "origin_index": 0,
        "origin_time": _probe.stamp(0),
        "available_at": _probe.stamp(24),
        "lifecycle_status": "confirmed",
        "broken": False,
        "visits": [visit.to_dict()],
    }).to_dict()

    assert payload["zone_id"] == visit.zone_id
    assert (payload["low"], payload["high"]) == (100.0, 110.0)
    assert payload["available_at"] == _probe.stamp(24)
    assert payload["lifecycle_status"] == "confirmed"
    assert len(payload["visits"]) == 1
    assert payload["visits"][0]["visit_id"] == visit.visit_id
    assert payload["visits"][0]["reacted_at"] == visit.reacted_at
    assert payload["visits"][0]["visit_state"] == "completed_reacted"

    evidence = build_d1_reaction_evidence(payload, state, as_of=cutoff)
    assert evidence["valid"] is True
    assert evidence["score"] > 0
    assert evidence["zone_id"] == visit.zone_id
    assert evidence["source_visit_id"] == visit.visit_id


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_08_typed_invalid_projection_beats_conflicting_legacy_flags(side):
    """A3-054: the same D1 source as the A3-053 control, but the zone is canonically invalid
    while legacy flags claim an active reaction — the canonical state must win, so the D1
    consumer serves no active evidence.
    """

    state = _probe.lifecycle(
        [(112, 114, 111, 113), (109, 110, 105, 109),
         (112, 114, 111, 113)], side,
    )
    visit = state.visits[0]
    assert visit.visit_state == "completed_reacted"
    cutoff = _probe.stamp(4 * 24)
    assert visit.reacted_at < cutoff

    payload = SmcZone.from_dict({
        "zone_id": visit.zone_id,
        "direction": side,
        "timeframe": "D1",
        "family": "ob",
        "zone_type": "bullish_ob" if side == "buy" else "bearish_ob",
        "low": 100.0,
        "high": 110.0,
        "origin_index": 0,
        "origin_time": _probe.stamp(0),
        "available_at": _probe.stamp(24),
        "lifecycle_status": "invalid",
        "broken": True,
        "invalidated_at": cutoff,
        "visits": [visit.to_dict()],
        "d1_reaction": True,
        "proximity": True,
    }).to_dict()

    # Preconditions: the canonical invalid state survives the typed round-trip, and the legacy
    # reaction flags are not part of the canonical typed payload.
    assert payload["lifecycle_status"] == "invalid"
    assert payload["broken"] is True
    assert payload["invalidated_at"] == cutoff
    assert "d1_reaction" not in payload
    assert "proximity" not in payload

    # The lifecycle payload keeps legacy flags that contradict the canonical invalid state.
    lifecycle_payload = dict(state.to_dict())
    lifecycle_payload.update({
        "lifecycle_status": "invalid",
        "lifecycle_broken": False,
        "broken": False,
        "d1_reaction": True,
        "proximity": True,
    })

    evidence = build_d1_reaction_evidence(payload, lifecycle_payload, as_of=cutoff)
    assert evidence["valid"] is False
    assert evidence["score"] == 0


@pytest.mark.parametrize("side", ["buy", "sell"])
def test_r72_08_typed_expired_projection_blocks_d1_and_keeps_history(side):
    """A3-055: an expired zone restored through `SmcZone.from_dict(...).to_dict()` keeps its
    reacted history but supplies no active D1 evidence at the expiry cutoff.

    The payload carries the visit's own zone id, so a passing verdict cannot come from a
    mismatched id.
    """

    state = _terminal_lifecycle(side, 20)
    visit = state.visits[0]
    assert state.lifecycle_expired is True
    assert state.expiry_index == 21
    assert visit.visit_state == "completed_reacted"
    reaction_close = _probe.stamp(21 * 24)
    expired_at = _probe.stamp(22 * 24)
    assert visit.reacted_at == reaction_close
    assert state.expired_at == expired_at

    payload = SmcZone.from_dict({
        "zone_id": visit.zone_id,
        "direction": side,
        "timeframe": "D1",
        "family": "ob",
        "zone_type": "bullish_ob" if side == "buy" else "bearish_ob",
        "low": 100.0,
        "high": 110.0,
        "origin_index": 0,
        "origin_time": _probe.stamp(0),
        "available_at": _probe.stamp(24),
        "lifecycle_status": "expired",
        "broken": False,
        "expired_at": expired_at,
        "visits": [visit.to_dict()],
    }).to_dict()

    # Preconditions: same zone id as the visit, canonical expired state kept, and the reacted
    # history is still part of the restored payload.
    assert payload["zone_id"] == visit.zone_id
    assert payload["lifecycle_status"] == "expired"
    assert payload["expired_at"] == expired_at
    assert len(payload["visits"]) == 1
    assert payload["visits"][0]["reacted_at"] == reaction_close

    evidence = build_d1_reaction_evidence(payload, state, as_of=expired_at)
    assert evidence["valid"] is False
    assert evidence["score"] == 0
    assert evidence["zone_id"] == visit.zone_id


def test_r72_09_h1_candidate_chain_reaches_d1_consumer_smoke():
    """A3-056: H1 **smoke** case for detector → context → typed → D1.

    The gate56 fixture yields an order-block **candidate** (not a confirmed zone) and the H1
    lifecycle below is computed here with an explicitly assigned ATR, so this case only checks
    the plumbing (ids/bounds survive and the D1 consumer answers). It is **not** evidence for
    the confirmed-D1 end-to-end rule — that is A3-057…A3-062.
    """

    module = _load_module(GATE56_PATH, "gate56_fixture_for_r72_09")
    candles = module._candles(module._fixture_rows())
    assert not validate_smc_candles(candles, "H1")
    candidate = detect_order_block_candidates(
        candles, symbol="EUR/USD", timeframe="H1",
    )[0]
    # Smoke scope: this fixture emits a candidate, not a confirmed zone.
    assert candidate["lifecycle_status"] == "candidate"
    assert candidate.get("confirmed") is not True
    enriched = enrich_zones(
        [candidate], candles, "ob", {}, {"status": "unknown"},
        symbol="EUR/USD", timeframe="H1", tf_minutes=60, tick_size=0.1,
    )[0]
    typed = SmcZone.from_dict(enriched, symbol="EUR/USD", timeframe="H1")
    restored = SmcZone.from_dict(typed.to_dict())
    lifecycle = analyze_zone_lifecycle(
        candles=candles, low=typed.low, high=typed.high, side=typed.direction,
        origin_index=typed.origin_index,
        departure_end_index=typed.departure_end_index or typed.origin_index,
        zone_id=typed.zone_id, timeframe="H1", tf_minutes=60,
        # ATR assigned by this smoke case; the confirmed-D1 chain uses the fixture's own
        # metadata instead (A3-057…A3-062).
        tick_size=0.1, atr_current=5.0,
    )
    evidence = build_d1_reaction_evidence(
        restored.to_dict(), lifecycle,
        as_of=candles[-1].time.isoformat(),
    )
    assert candidate["zone_id"] == typed.zone_id == restored.zone_id
    assert typed.original_bounds == {"low": 99.0, "high": 101.0}
    # A3-056 removed an assertion that compared the lifecycle with its own serialization
    # (`lifecycle.to_dict()["visits"] == [visit.to_dict() ...]`), which could not fail.
    assert evidence["valid"] is False
    assert evidence["score"] == 0


# --- A3-057: D1 confirmed source fixture (detector + causal structure replay) ----------------

_D1_SOURCE_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
_D1_BASE_INDEX = 32
_D1_DEPARTURE_INDEX = 33
_D1_BREAK_INDEX = 34
# Fixture metadata handed to the real structure replay and to the canonical lifecycle; the
# ATR is the fixture's declared current ATR (the A3-058 retest bars are designed against
# 0.25 x and 0.05 x of it). The zone receives no metadata from production output.
_D1_SYMBOL = "EUR/USD"
_D1_TICK_SIZE = 0.1
_D1_ATR_CURRENT = 1.0

# 37 closed D1 bars. Bars 0..31 carry the warm-up/zigzag the causal structure replay needs to
# bootstrap a bullish state from its own swings: two confirmed higher highs (bar 14 at 102.0,
# bar 26 at 103.0) and two confirmed higher lows (bar 8 at 96.4, bar 20 at 97.8). Bar 32 is the
# bearish base bar of the order block, bar 33 the bullish departure bar, bar 34 the bar whose
# close breaks the last confirmed swing high, and bars 35..36 extend the closed history.
# Every level below is fixture input; none of it is copied from a production result.
_D1_SOURCE_ROWS = [
    (100.6, 100.8, 99.8, 100.0),
    (100.0, 100.2, 99.2, 99.4),
    (99.4, 99.6, 98.6, 98.8),
    (98.8, 99.0, 98.0, 98.2),
    (98.2, 98.4, 97.6, 97.8),
    (97.8, 98.0, 97.2, 97.4),
    (97.4, 97.6, 96.9, 97.1),
    (97.1, 97.4, 96.6, 97.0),
    (97.0, 97.3, 96.4, 97.2),
    (97.2, 98.2, 97.0, 98.0),
    (98.0, 99.0, 97.8, 98.8),
    (98.8, 99.8, 98.6, 99.6),
    (99.6, 100.6, 99.4, 100.4),
    (100.4, 101.4, 100.2, 101.2),
    (101.2, 102.0, 101.0, 101.4),
    (101.4, 101.6, 100.6, 100.8),
    (100.8, 101.0, 100.0, 100.2),
    (100.2, 100.4, 99.4, 99.6),
    (99.6, 99.8, 98.8, 99.0),
    (99.0, 99.2, 98.2, 98.4),
    (98.4, 98.6, 97.8, 98.2),
    (98.2, 99.2, 98.0, 99.0),
    (99.0, 100.0, 98.8, 99.8),
    (99.8, 100.8, 99.6, 100.6),
    (100.6, 101.6, 100.4, 101.4),
    (101.4, 102.4, 101.2, 102.2),
    (102.2, 103.0, 102.0, 102.4),
    (102.4, 102.6, 101.6, 101.8),
    (101.8, 102.0, 101.0, 101.2),
    (101.2, 101.4, 100.4, 100.6),
    (100.6, 100.8, 100.0, 100.2),
    (100.2, 100.4, 99.6, 99.8),
    (100.0, 100.2, 99.2, 99.4),
    (99.4, 101.4, 99.3, 101.2),
    (101.2, 104.0, 101.0, 103.8),
    (103.8, 104.6, 103.4, 104.4),
    (104.4, 105.2, 104.0, 105.0),
]


def _d1_source_candles(rows=None):
    source_rows = _D1_SOURCE_ROWS if rows is None else rows
    values = [
        Candle(
            time=_D1_SOURCE_START + timedelta(days=index),
            open=open_, high=high, low=low, close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(source_rows)
    ]
    assert not validate_smc_candles(values, "D1")
    return values


def _d1_confirmed_source(rows=None):
    """A3-057 fixture: a D1 zone confirmed by the fixture's own structure break.

    The order-block candidate comes from `detect_order_block_candidates` and the BOS that
    promotes it comes from `replay_smc_structure` over the same D1 bars, so both the zone
    bounds and the confirming source are produced by the fixture. Swings are read causally up
    to and including the fixture's break bar, so appending later retest bars (A3-058) cannot
    move the confirming swing. The break bar is derived as the first bar closing above that
    swing high; its close is the independently derived availability time (a D1 bar closes at
    its open time + 1 day).
    """

    candles = _d1_source_candles(rows)
    swings = external_swing_points(
        candles[: _D1_BREAK_INDEX + 1], symbol=_D1_SYMBOL, timeframe="D1", lookback=5,
    )
    swing_high = swings["highs"][-1]
    break_index = next(
        index for index, candle in enumerate(candles) if candle.close > swing_high["level"]
    )
    events = replay_smc_structure(
        candles, symbol=_D1_SYMBOL, timeframe="D1", pivot_width=5, tick_size=_D1_TICK_SIZE,
    )["events"]
    bos = next(
        event for event in events
        if event.get("event_type") == "BOS" and event.get("direction") == "bullish"
    )
    candidates = detect_order_block_candidates(candles, symbol=_D1_SYMBOL, timeframe="D1")
    candidate = next(
        item for item in candidates
        if item["direction"] == "buy" and item["origin_index"] == _D1_BASE_INDEX
    )
    confirmed = confirm_order_block_candidate(candidate, [bos], candles=candles)
    return candles, swings, break_index, bos, candidates, candidate, confirmed


def test_r72_09_d1_source_is_confirmed_by_fixture_break():
    """A3-057: the D1 zone later used by the D1 chain is confirmed by a real fixture BOS.

    Preconditions are asserted on the fixture before any lifecycle call: validated D1 bars,
    enough warm-up for the causal ATR reference, a detector candidate whose departure
    measurement is usable, and a bullish BOS produced by the causal structure replay that
    breaks the fixture's own last confirmed swing high. `confirmed` is never assigned here:
    the production confirmation step under test is what promotes the candidate, and the
    expected availability time is computed from the fixture bar that breaks the swing level.
    """

    candles, swings, break_index, bos, candidates, candidate, confirmed = _d1_confirmed_source()
    base_open, base_high, base_low, base_close = _D1_SOURCE_ROWS[_D1_BASE_INDEX]
    departure_open, departure_high, departure_low, departure_close = (
        _D1_SOURCE_ROWS[_D1_DEPARTURE_INDEX]
    )

    # Fixture geometry: a bearish base bar and a bullish departure closing above the base high.
    assert base_close < base_open
    assert departure_close > departure_open
    assert departure_close > base_high
    # Warm-up: the causal ATR reference needs at least 15 closed bars before the departure bar.
    assert _D1_DEPARTURE_INDEX >= 15

    # Precondition 1: the detector emitted exactly one unconfirmed buy candidate at the
    # fixture's base bar (earlier zigzag bars may form unrelated candidates).
    assert [
        item["origin_index"] for item in candidates
        if item["direction"] == "buy" and item["origin_index"] == _D1_BASE_INDEX
    ] == [_D1_BASE_INDEX]
    assert candidate["origin_index"] == _D1_BASE_INDEX
    assert candidate["departure_end_index"] == _D1_DEPARTURE_INDEX
    # Fixture metadata carried by the candidate.
    assert candidate["symbol"] == _D1_SYMBOL
    assert candidate["timeframe"] == "D1"
    assert candidate["family"] == "ob"
    assert candidate["lifecycle_status"] == "candidate"
    assert candidate["available_at"] is None
    assert candidate["confirmed_at"] is None
    assert candidate["confirmation_event_id"] is None
    assert candidate["departure_measurement"]["status"] == "ok"
    assert candidate["original_bounds"] == {"low": base_low, "high": base_high}

    # Precondition 2: the confirming BOS is a real confirmed event from the fixture's replay,
    # and its broken level is the fixture's own last confirmed swing high.
    swing_high = swings["highs"][-1]
    assert bos["status"] == "confirmed"
    assert bos["event_type"] == "BOS"
    assert bos["direction"] == "bullish"
    assert bos["broken_level_id"] == swing_high["swing_id"]
    assert candles[break_index].close > swing_high["level"]
    assert break_index == _D1_DEPARTURE_INDEX + 1

    # Expected availability: the close of the fixture bar that breaks the swing high.
    expected_available_at = (candles[break_index].time + timedelta(days=1)).isoformat()
    assert bos["occurred_at"] == expected_available_at

    # Contract: the confirmation step promotes the same candidate and stamps that source.
    assert confirmed["lifecycle_status"] == "confirmed"
    assert confirmed["candidate"] is False
    assert confirmed["entry_eligible"] is False
    assert confirmed["confirmed_at"] == expected_available_at
    assert confirmed["available_at"] == expected_available_at
    assert confirmed["confirmation_event_id"] == bos["event_id"]
    assert confirmed["related_structure_event_id"] == bos["event_id"]
    assert confirmed["broken_level_id"] == swing_high["swing_id"]
    assert "ZONE_CONFIRMED" in confirmed["reason_codes"]
    # Bounds come from the fixture base bar, not from the confirmation step.
    assert confirmed["low"] == base_low
    assert confirmed["high"] == base_high
    assert confirmed["original_bounds"] == {"low": base_low, "high": base_high}
    # Source identity is carried over from the candidate.
    for field in (
        "zone_id", "setup_id", "type", "family", "symbol", "timeframe", "direction",
        "origin_index", "origin_time", "departure_end_index", "departure_end",
        "departure_source_id",
    ):
        assert confirmed[field] == candidate[field], field

    # The confirmation step must not mutate the candidate that was passed in.
    assert candidate["lifecycle_status"] == "candidate"
    assert candidate["available_at"] is None


# --- A3-058: the confirmed D1 source retests through the canonical lifecycle ------------------

_D1_RETEST_ENTER_INDEX = 38
_D1_RETEST_EXIT_INDEX = 40
_D1_RETEST_REACTION_INDEX = 41

# Five bars appended to the A3-057 chain: a decline toward the confirmed demand zone
# [99.2, 100.2], two inside bars, an upward exit bar and a follow-through bar. The geometry is
# asserted in `_d1_retest_candles` against the fixture's own tick size and declared ATR, so the
# expected enter/exit/reaction times are the closes of the bars derived here.
_D1_RETEST_ROWS = _D1_SOURCE_ROWS + [
    (105.0, 105.2, 101.5, 102.0),
    (102.0, 102.2, 99.0, 100.0),
    (100.0, 100.2, 99.3, 99.8),
    (100.4, 100.7, 100.35, 100.35),
    (100.4, 101.8, 100.35, 101.6),
]


def _d1_retest_candles():
    """A3-058 fixture: the A3-057 chain plus a retest of the confirmed demand zone.

    The appended bars are designed against the fixture's own metadata: the zone tolerance is
    `max(1 tick, 0.05 x ATR)`, the invalidation buffer is `max(2 tick, 0.10 x ATR)` and the
    reaction threshold is `0.25 x ATR`. The assertions below hold on the bars themselves, so
    the expected timeline does not depend on any production result.
    """

    values = _d1_source_candles(_D1_RETEST_ROWS)
    _, zone_high, zone_low, _ = _D1_SOURCE_ROWS[_D1_BASE_INDEX]
    tolerance = max(_D1_TICK_SIZE, 0.05 * _D1_ATR_CURRENT)
    invalidate_buffer = max(2 * _D1_TICK_SIZE, 0.10 * _D1_ATR_CURRENT)
    reaction_threshold = 0.25 * _D1_ATR_CURRENT

    # No bar from the confirmation window down to the entry bar reaches the zone.
    for index in range(_D1_DEPARTURE_INDEX + 1, _D1_RETEST_ENTER_INDEX):
        assert values[index].low > zone_high + tolerance, index
    # The entry bar is the first overlap with the zone.
    assert values[_D1_RETEST_ENTER_INDEX].low <= zone_high + tolerance
    assert values[_D1_RETEST_ENTER_INDEX].high >= zone_low - tolerance
    # The exit bar leaves the zone upward without yet supplying the reaction close.
    assert values[_D1_RETEST_EXIT_INDEX].low > zone_high + tolerance
    assert values[_D1_RETEST_EXIT_INDEX].close < zone_high + reaction_threshold
    # The next bar closes beyond the reaction threshold.
    assert values[_D1_RETEST_REACTION_INDEX].close >= zone_high + reaction_threshold
    # Nothing in the retest closes through the invalidation buffer.
    for index in range(_D1_RETEST_ENTER_INDEX, len(values)):
        assert values[index].close >= zone_low - invalidate_buffer, index
    return values


def test_r72_09_d1_confirmed_zone_timeline_comes_from_fixture_retest():
    """A3-058: the confirmed D1 zone goes through the canonical lifecycle in `enrich_zones`.

    The zone is the one confirmed by A3-057 (real detector candidate + real replay BOS) and it
    carries only fixture metadata. The expected enter/exit/reaction times are the closes of the
    fixture's retest bars derived in `_d1_retest_candles`; the timeline under test is the one
    `enrich_zones` produced, so no second `analyze_zone_lifecycle` call with a locally assigned
    ATR is used to substitute it.
    """

    # Asserts the retest geometry of `_D1_RETEST_ROWS` before it is used below.
    _d1_retest_candles()
    zone_rows = _D1_SOURCE_ROWS[_D1_BASE_INDEX]
    candles, _swings, break_index, _bos, _candidates, _candidate, confirmed = (
        _d1_confirmed_source(_D1_RETEST_ROWS)
    )
    assert confirmed["lifecycle_status"] == "confirmed"

    zone = dict(confirmed)
    zone["tick_size"] = _D1_TICK_SIZE
    zone["atr_current"] = _D1_ATR_CURRENT

    enriched = enrich_zones(
        [zone], candles, "ob", {}, {"status": "unknown"},
        tf_minutes=1440, symbol=_D1_SYMBOL, timeframe="D1", tick_size=_D1_TICK_SIZE,
    )[0]

    # Expected timeline, computed from the fixture bars (D1 closes at open + 1 day).
    expected_available_at = (candles[break_index].time + timedelta(days=1)).isoformat()
    expected_entered_at = (
        candles[_D1_RETEST_ENTER_INDEX].time + timedelta(days=1)
    ).isoformat()
    expected_exited_at = (
        candles[_D1_RETEST_EXIT_INDEX].time + timedelta(days=1)
    ).isoformat()
    expected_reacted_at = (
        candles[_D1_RETEST_REACTION_INDEX].time + timedelta(days=1)
    ).isoformat()

    # Preconditions: the enriched zone is the same confirmed fixture zone with its own metadata.
    assert confirmed["available_at"] == expected_available_at
    assert enriched["zone_id"] == confirmed["zone_id"]
    assert enriched["low"] == zone_rows[2]
    assert enriched["high"] == zone_rows[1]
    assert enriched["origin_index"] == _D1_BASE_INDEX
    assert enriched["departure_end_index"] == _D1_DEPARTURE_INDEX
    assert enriched["available_at"] == expected_available_at
    assert enriched["tick_size"] == _D1_TICK_SIZE
    assert enriched["atr_current"] == _D1_ATR_CURRENT

    # Contract: the canonical lifecycle timeline is the fixture's retest, not a substitute.
    assert enriched["first_retest_index"] == _D1_RETEST_ENTER_INDEX
    assert enriched["first_retest_time"] == expected_entered_at
    assert enriched["independent_retest_count"] == 1
    assert enriched["bars_spent_inside"] == 2
    assert enriched["lifecycle_mitigated"] is True
    assert enriched["lifecycle_broken"] is False
    assert enriched["lifecycle_stale"] is False
    assert enriched["invalidation_index"] is None
    assert enriched["invalidated_at"] is None
    assert enriched["expiry_index"] is None
    assert enriched["expired_at"] is None

    visits = enriched["visits"]
    assert len(visits) == 1
    visit = visits[0]
    assert visit["zone_id"] == confirmed["zone_id"]
    assert visit["start_index"] == _D1_RETEST_ENTER_INDEX
    assert visit["end_index"] == _D1_RETEST_EXIT_INDEX - 1
    assert visit["entered_at"] == expected_entered_at
    assert visit["exited_at"] == expected_exited_at
    assert visit["reacted_at"] == expected_reacted_at
    assert visit["visit_state"] == "completed_reacted"


# --- A3-059: the enriched D1 zone through the typed model ------------------------------------

def _d1_close_at(candles, index):
    """Fixture-side D1 close: a D1 bar closes one day after its open time."""

    return (candles[index].time + timedelta(days=1)).isoformat()


def _d1_enriched_source(rows=None):
    """A3-059…A3-062 entry point: an enriched confirmed zone and its fixture chain.

    Returns `(candles, break_index, bos, enriched)`; the zone is the A3-057 confirmed source
    enriched by the canonical lifecycle, carrying only fixture metadata. With no `rows` the
    A3-058 retest chain is used and its geometry is asserted first; later steps may pass the
    invalidation chain instead.
    """

    if rows is None:
        # Asserts the retest geometry of `_D1_RETEST_ROWS` before it is used below.
        _d1_retest_candles()
        rows = _D1_RETEST_ROWS
    candles, _swings, break_index, bos, _candidates, _candidate, confirmed = (
        _d1_confirmed_source(rows)
    )
    enriched = enrich_zones(
        [dict(confirmed, tick_size=_D1_TICK_SIZE, atr_current=_D1_ATR_CURRENT)],
        candles, "ob", {}, {"status": "unknown"},
        tf_minutes=1440, symbol=_D1_SYMBOL, timeframe="D1", tick_size=_D1_TICK_SIZE,
    )[0]
    return candles, break_index, bos, enriched


def test_r72_09_d1_enriched_zone_survives_typed_restore():
    """A3-059: identity, bounds and the fixture timeline survive the typed restore.

    The zone is the A3-058 enriched confirmed zone. Bounds and every timeline value are checked
    against the fixture's own bars (the base bar and the retest bar closes), so the check is not
    a comparison of two serializations produced from the same object: the typed zone and the
    restored zone are each compared to the fixture-derived expectation.
    """

    candles, break_index, bos, enriched = _d1_enriched_source()
    _, zone_high, zone_low, _ = _D1_SOURCE_ROWS[_D1_BASE_INDEX]

    typed = SmcZone.from_dict(enriched, symbol=_D1_SYMBOL, timeframe="D1")
    restored = SmcZone.from_dict(typed.to_dict())

    expected_available_at = _d1_close_at(candles, break_index)
    expected_entered_at = _d1_close_at(candles, _D1_RETEST_ENTER_INDEX)
    expected_exited_at = _d1_close_at(candles, _D1_RETEST_EXIT_INDEX)
    expected_reacted_at = _d1_close_at(candles, _D1_RETEST_REACTION_INDEX)

    for model in (typed, restored):
        # Identity and bounds come from the fixture, not from the other serialization.
        assert model.zone_id == enriched["zone_id"]
        assert model.symbol == _D1_SYMBOL.replace("/", "")
        assert model.timeframe == "D1"
        assert model.family == "ob"
        assert model.direction == "buy"
        assert model.low == zone_low
        assert model.high == zone_high
        assert model.original_low == zone_low
        assert model.original_high == zone_high
        assert model.origin_index == _D1_BASE_INDEX
        assert model.departure_end_index == _D1_DEPARTURE_INDEX
        # The confirmation source and availability survive the restore.
        assert model.confirmation_event_id == bos["event_id"]
        assert model.confirmed_at == expected_available_at
        assert model.available_at == expected_available_at
        assert model.lifecycle_status == "confirmed"
        # The lifecycle timeline is the fixture retest, not a copy of another serialization.
        assert model.first_retest_index == _D1_RETEST_ENTER_INDEX
        assert model.first_retest_time == expected_entered_at
        assert model.independent_retest_count == 1
        assert model.bars_spent_inside == 2
        assert model.lifecycle_mitigated is True
        assert model.broken is False
        assert model.invalidation_index is None
        assert model.invalidated_at is None
        assert model.expired_at is None
        assert len(model.visits) == 1
        visit = model.visits[0]
        assert visit.zone_id == enriched["zone_id"]
        assert visit.start_index == _D1_RETEST_ENTER_INDEX
        assert visit.end_index == _D1_RETEST_EXIT_INDEX - 1
        assert visit.bars_spent_inside == 2
        assert visit.entered_at == expected_entered_at
        assert visit.exited_at == expected_exited_at
        assert visit.reacted_at == expected_reacted_at
        assert visit.visit_state == "completed_reacted"


def test_r72_09_d1_reaction_positive_reads_canonical_lifecycle():
    """A3-060: the confirmed D1 source yields a positive D1 reaction before any terminal.

    The payload is the restored typed zone (A3-059) and the lifecycle is the canonical one
    produced by `enrich_zones` (A3-058), so no second lifecycle call runs here. The cutoff is
    the fixture's last closed bar: after the zone's availability and after the retest reaction,
    with no invalidation or expiry in the fixture. A control removes the canonical reacted
    visit while setting the legacy `d1_reaction`/`proximity` flags to True, so a pass cannot
    come from those legacy flags.
    """

    candles, break_index, bos, enriched = _d1_enriched_source()
    typed = SmcZone.from_dict(enriched, symbol=_D1_SYMBOL, timeframe="D1")
    payload = typed.to_dict()

    expected_available_at = _d1_close_at(candles, break_index)
    expected_entered_at = _d1_close_at(candles, _D1_RETEST_ENTER_INDEX)
    expected_reacted_at = _d1_close_at(candles, _D1_RETEST_REACTION_INDEX)
    cutoff = _d1_close_at(candles, len(candles) - 1)

    # Preconditions: the canonical payload carries no legacy reaction flags, the canonical
    # lifecycle has exactly the fixture's reacted visit, and the cutoff is after availability.
    assert "d1_reaction" not in payload
    assert "proximity" not in payload
    assert len(enriched["visits"]) == 1
    assert enriched["visits"][0]["visit_state"] == "completed_reacted"
    assert enriched["visits"][0]["entered_at"] == expected_entered_at
    assert enriched["visits"][0]["reacted_at"] == expected_reacted_at
    assert enriched["available_at"] == expected_available_at
    assert expected_available_at < cutoff
    assert expected_reacted_at <= cutoff
    # Before terminal: the fixture holds no invalidation and no expiry for this zone.
    assert enriched["invalidation_index"] is None
    assert enriched["invalidated_at"] is None
    assert enriched["expiry_index"] is None
    assert enriched["expired_at"] is None

    evidence = build_d1_reaction_evidence(payload, enriched, as_of=cutoff)

    assert evidence["valid"] is True
    assert evidence["score"] > 0
    assert evidence["zone_id"] == enriched["zone_id"]
    assert evidence["source_visit_id"] == typed.visits[0].visit_id
    assert evidence["reacted_at"] == expected_reacted_at
    assert evidence["reason_codes"] == ["D1_REACTION_COMPLETED_REACTED"]

    # Control: without the canonical reacted visit, the legacy flags alone cannot pass.
    legacy_payload = dict(payload, visits=[], d1_reaction=True, proximity=True)
    legacy_lifecycle = dict(enriched, visits=[])
    legacy_evidence = build_d1_reaction_evidence(
        legacy_payload, legacy_lifecycle, as_of=cutoff,
    )
    assert legacy_evidence["valid"] is False
    assert legacy_evidence["score"] == 0
    assert legacy_evidence["reason_codes"] == ["D1_REACTION_NOT_COMPLETED_REACTED"]


# --- A3-061: the invalidated D1 source through the D1 consumer -------------------------------

_D1_INVALIDATION_INDEX = 43

# Two bars appended to the retest chain: a bar that stays outside the zone, then the bar that
# closes through the invalidation buffer `max(2 tick, 0.10 x ATR) = 0.2` below the zone low, so
# the terminal sits at the fixture's last closed bar.
_D1_INVALIDATION_ROWS = _D1_RETEST_ROWS + [
    (101.6, 101.7, 100.35, 100.4),
    (100.4, 100.5, 98.5, 98.6),
]


def _d1_invalidated_candles():
    """A3-061 fixture: the A3-058 retest chain plus a terminal breakdown of the zone.

    The breakdown bar closes the fixture's invalidation buffer below the zone low and no earlier
    retest bar did, while the first visit's reaction close still happens before the breakdown.
    """

    values = _d1_source_candles(_D1_INVALIDATION_ROWS)
    _, zone_high, zone_low, _ = _D1_SOURCE_ROWS[_D1_BASE_INDEX]
    invalidate_buffer = max(2 * _D1_TICK_SIZE, 0.10 * _D1_ATR_CURRENT)
    assert values[_D1_INVALIDATION_INDEX].close < zone_low - invalidate_buffer
    for index in range(_D1_RETEST_ENTER_INDEX, _D1_INVALIDATION_INDEX):
        assert values[index].close >= zone_low - invalidate_buffer, index
    assert _D1_RETEST_REACTION_INDEX < _D1_INVALIDATION_INDEX
    assert (
        values[_D1_RETEST_REACTION_INDEX].close
        >= zone_high + 0.25 * _D1_ATR_CURRENT
    )
    return values


def test_r72_09_d1_invalidated_source_is_terminal_for_the_consumer():
    """A3-061: at the invalidation close the zone is terminal and its D1 reaction is gone.

    The fixture places the reaction before the breakdown, so the earlier reaction history must
    survive while the canonical zone turns invalid/unusable (R72-08) and the D1 consumer stops
    reading a reaction at the terminal close (A-D04). The append ends at that close — the terminal
    cutoff is the snapshot's own last bar, never a rewound one — and the positive control is a real
    prefix of this chain enriched on its own (A3R3-03).
    """

    _d1_invalidated_candles()
    candles, break_index, bos, enriched = _d1_enriched_source(_D1_INVALIDATION_ROWS)
    typed = SmcZone.from_dict(enriched, symbol=_D1_SYMBOL, timeframe="D1")
    payload = typed.to_dict()

    expected_available_at = _d1_close_at(candles, break_index)
    expected_entered_at = _d1_close_at(candles, _D1_RETEST_ENTER_INDEX)
    expected_exited_at = _d1_close_at(candles, _D1_RETEST_EXIT_INDEX)
    expected_reacted_at = _d1_close_at(candles, _D1_RETEST_REACTION_INDEX)
    terminal_at = _d1_close_at(candles, _D1_INVALIDATION_INDEX)

    # The append ends exactly at the invalidation close: the breakdown bar is the snapshot's own
    # last bar, and the terminal cutoff used below is that same close. Nothing here rewinds a
    # terminal snapshot to an earlier cutoff (A3R3-03).
    assert _D1_INVALIDATION_INDEX == len(candles) - 1
    assert terminal_at == _d1_close_at(candles, len(candles) - 1)

    # Preconditions: the canonical lifecycle is terminal at the fixture's breakdown bar, and the
    # availability stamped by A3-057 is unchanged.
    assert enriched["available_at"] == expected_available_at
    assert enriched["invalidation_index"] == _D1_INVALIDATION_INDEX
    assert enriched["invalidated_at"] == terminal_at
    assert enriched["lifecycle_broken"] is True
    assert enriched["broken"] is True
    assert enriched["expiry_index"] is None
    assert enriched["expired_at"] is None

    # History: the earlier reaction survives the breakdown, and the breakdown bar opens its own
    # visit that is closed by invalidation.
    assert enriched["independent_retest_count"] == 2
    first_visit, last_visit = enriched["visits"]
    assert first_visit["visit_state"] == "completed_reacted"
    assert first_visit["entered_at"] == expected_entered_at
    assert first_visit["exited_at"] == expected_exited_at
    assert first_visit["reacted_at"] == expected_reacted_at
    assert last_visit["visit_state"] == "closed_by_invalidation"
    assert last_visit["start_index"] == _D1_INVALIDATION_INDEX
    assert last_visit["end_index"] == _D1_INVALIDATION_INDEX
    assert last_visit["reacted_at"] is None

    # Positive control: a **real prefix** of the fixture -- the retest chain without the two
    # terminal bars -- enriched on its own, so the consumer reads a snapshot whose own last close
    # *is* the cutoff. Rewinding `as_of` on the terminal payload would not be a prefix snapshot
    # (data spec §1); this reuses the A3-060 positive construction on the prefix instead.
    prefix_candles, _prefix_break_index, _pbos, prefix_enriched = _d1_enriched_source()
    prefix_typed = SmcZone.from_dict(prefix_enriched, symbol=_D1_SYMBOL, timeframe="D1")
    prefix_payload = prefix_typed.to_dict()
    prefix_cutoff = _d1_close_at(prefix_candles, len(prefix_candles) - 1)

    # The prefix is not terminal, and its identity/history match the appended version, so the
    # terminal reading below belongs to this same zone and cannot be blamed on a missing reaction.
    assert prefix_enriched["lifecycle_status"] == "confirmed"
    assert prefix_enriched["broken"] is False
    assert prefix_enriched["invalidation_index"] is None
    assert prefix_enriched["invalidated_at"] is None
    assert prefix_enriched["expiry_index"] is None
    assert prefix_enriched["expired_at"] is None
    assert prefix_enriched["zone_id"] == enriched["zone_id"]
    assert (prefix_enriched["low"], prefix_enriched["high"]) == (
        enriched["low"], enriched["high"],
    )
    assert prefix_enriched["available_at"] == enriched["available_at"]
    assert prefix_enriched["visits"][0] == first_visit
    assert prefix_cutoff == expected_reacted_at

    pre_terminal = build_d1_reaction_evidence(
        prefix_payload, prefix_enriched, as_of=prefix_cutoff,
    )
    assert pre_terminal["valid"] is True
    assert pre_terminal["score"] > 0
    assert pre_terminal["source_visit_id"] == prefix_typed.visits[0].visit_id
    assert pre_terminal["reacted_at"] == expected_reacted_at

    # Contract at the terminal close: invalid/unusable zone (R72-08) and no active D1 reaction
    # (A-D04), while the rejection is never "reaction missing".
    assert enriched["lifecycle_status"] == "invalid"
    assert enriched.get("usable") is False
    evidence = build_d1_reaction_evidence(payload, enriched, as_of=terminal_at)
    assert evidence["valid"] is False
    assert evidence["score"] == 0
    assert "D1_REACTION_NOT_COMPLETED_REACTED" not in evidence["reason_codes"]


# --- A3-062: the expired D1 source through the D1 consumer -----------------------------------

_D1_EXPIRY_INDEX = 55

# Fourteen bars appended to the retest chain that stay above the zone (out of tolerance) and
# never close through the invalidation buffer, so no new visit opens. The zone's age measured
# from its anchor bar (the confirmation bar 34) therefore reaches the published D1 lifetime of
# 20 bars at index 55, the fixture's last bar.
_D1_EXPIRY_ROWS = _D1_RETEST_ROWS + [
    (101.6, 102.4, 101.4, 102.2),
    (102.2, 103.0, 102.0, 102.8),
    (102.8, 103.4, 102.4, 103.0),
    (103.0, 103.2, 102.4, 102.6),
    (102.6, 103.0, 101.8, 102.0),
    (102.0, 102.6, 101.6, 102.4),
    (102.4, 103.2, 102.2, 103.0),
    (103.0, 103.6, 102.6, 103.2),
    (103.2, 103.8, 102.8, 103.4),
    (103.4, 104.0, 103.0, 103.6),
    (103.6, 104.2, 103.2, 103.8),
    (103.8, 104.4, 103.4, 104.0),
    (104.0, 104.6, 103.6, 104.2),
    (104.2, 104.8, 103.8, 104.4),
]


def _d1_expired_candles():
    """A3-062 fixture: the A3-058 retest chain grown past the D1 lifetime.

    Every appended bar stays outside the zone above the tolerance and never closes through the
    invalidation buffer, so the only visit remains the retest reaction and the zone expires by
    age at the fixture's last bar.
    """

    values = _d1_source_candles(_D1_EXPIRY_ROWS)
    _, zone_high, zone_low, _ = _D1_SOURCE_ROWS[_D1_BASE_INDEX]
    tolerance = max(_D1_TICK_SIZE, 0.05 * _D1_ATR_CURRENT)
    invalidate_buffer = max(2 * _D1_TICK_SIZE, 0.10 * _D1_ATR_CURRENT)
    for index in range(_D1_RETEST_REACTION_INDEX + 1, len(values)):
        assert values[index].low > zone_high + tolerance, index
        assert values[index].close >= zone_low - invalidate_buffer, index
    # The anchor is the confirmation bar 34 and the expiry bar is 20 bars later.
    assert _D1_EXPIRY_INDEX == _D1_BREAK_INDEX + 21
    assert _D1_EXPIRY_INDEX == len(values) - 1
    return values


def test_r72_09_d1_expired_source_is_terminal_for_the_consumer():
    """A3-062: at the lifetime expiry the zone is expired/unusable and its D1 reaction is gone.

    The fixture grows the A3-060 chain past the D1 lifetime with bars that stay outside the zone,
    so the zone expires by age at the fixture's last bar while the earlier reaction history stays
    intact. A3-060 is the positive control on the same zone before expiry, so the rejection here
    is the staleness gate and never a missing reaction or missing metadata.
    """

    _d1_expired_candles()
    candles, break_index, bos, enriched = _d1_enriched_source(_D1_EXPIRY_ROWS)
    typed = SmcZone.from_dict(enriched, symbol=_D1_SYMBOL, timeframe="D1")
    payload = typed.to_dict()

    expected_available_at = _d1_close_at(candles, break_index)
    expected_entered_at = _d1_close_at(candles, _D1_RETEST_ENTER_INDEX)
    expected_exited_at = _d1_close_at(candles, _D1_RETEST_EXIT_INDEX)
    expected_reacted_at = _d1_close_at(candles, _D1_RETEST_REACTION_INDEX)
    expected_expired_at = _d1_close_at(candles, _D1_EXPIRY_INDEX)

    # Precondition: the canonical lifecycle expires at the fixture's last bar, by age, with the
    # fixture metadata still present so the terminal is not a metadata gap.
    assert enriched["tick_size"] == _D1_TICK_SIZE
    assert enriched["atr_current"] == _D1_ATR_CURRENT
    assert enriched["available_at"] == expected_available_at
    assert enriched["expiry_index"] == _D1_EXPIRY_INDEX
    assert enriched["expired_at"] == expected_expired_at
    assert enriched["lifecycle_expired"] is True
    assert enriched["lifecycle_stale"] is True
    assert enriched["lifecycle_broken"] is False
    assert enriched["broken"] is False
    assert enriched["invalidation_index"] is None
    assert enriched["invalidated_at"] is None
    assert enriched["age_bars"] == _D1_EXPIRY_INDEX - _D1_BREAK_INDEX

    # History: the reacted visit of the retest is still part of the expired zone.
    assert enriched["independent_retest_count"] == 1
    visit = enriched["visits"][0]
    assert visit["visit_state"] == "completed_reacted"
    assert visit["entered_at"] == expected_entered_at
    assert visit["exited_at"] == expected_exited_at
    assert visit["reacted_at"] == expected_reacted_at

    # Contract at the expiry close: expired/unusable zone and no active D1 reaction, with the
    # rejection classified as staleness rather than a missing reaction.
    assert enriched["lifecycle_status"] == "expired"
    assert enriched.get("usable") is False
    assert "ZONE_EXPIRED" in enriched["reason_codes"]
    evidence = build_d1_reaction_evidence(payload, enriched, as_of=expected_expired_at)
    assert evidence["valid"] is False
    assert evidence["score"] == 0
    assert evidence["reason_codes"] == ["D1_REACTION_STALE"]
    assert "D1_REACTION_NOT_COMPLETED_REACTED" not in evidence["reason_codes"]


# --- A3-067: explicit metadata overrides replace one rule each -------------------------------

def _override_source(level=100.0, **overrides):
    """A3-067 fixture: one eligible swing source, optionally made ineligible by an override."""

    source = dict(
        level=level, index=0, swing_id="override-source", confirmed=True, usable=True,
        provisional=False, pivot_time=_probe.stamp(0), confirmed_at=_probe.stamp(1),
        usable_at=_probe.stamp(1),
    )
    source.update(overrides)
    return source


def test_r72_07_excursion_override_only_replaces_its_own_rule():
    """A3-067: `excursion_buffer` replaces the excursion rule and nothing else.

    The sweep candle penetrates 0.10 past the level, below the computed
    `max(2*tick, 0.10*ATR) = 0.2` but above the explicit `excursion_buffer=0.05`, so the override
    is what allows the sweep. It must not make an ineligible source acceptable.
    """

    tick, atr = 0.1, 1.0
    level = 100.0
    rows = [(112, 114, 111, 113)] * 8
    rows[2] = (110, 111, 99.9, 100.1)
    values = _probe.candles(rows, "buy")
    assert level - values[2].low == pytest.approx(0.10)   # penetration from the fixture
    assert values[2].close > level                        # reclaim in the same candle

    common = dict(timeframe="H1", causal_only=True, lookback_bars=8)
    eligible = {"highs": [], "lows": [_override_source()]}

    # Control: under the computed excursion this fixture does not sweep.
    computed = detect_liquidity_sweeps(
        values, eligible, tick_size=tick, atr_value=atr, **common,
    )
    assert computed["swept_lows"] == []

    # The override replaces exactly that rule: the same fixture now sweeps.
    overridden = detect_liquidity_sweeps(values, eligible, excursion_buffer=0.05, **common)
    assert [sweep["index"] for sweep in overridden["swept_lows"]] == [2]
    assert overridden["swept_lows"][0]["excursion_buffer"] == pytest.approx(0.05)

    # It cannot rescue a different requirement: the source must still be eligible.
    for ineligible in ({"provisional": True}, {"usable": False}, {"confirmed": False}):
        swings = {"highs": [], "lows": [_override_source(**ineligible)]}
        result = detect_liquidity_sweeps(values, swings, excursion_buffer=0.05, **common)
        assert result["swept_lows"] == [], ineligible


def test_r72_07_equal_tolerance_override_only_replaces_its_own_rule():
    """A3-067: `equal_tolerance` replaces the equal-level rule and nothing else.

    Two swing lows 0.05 apart form an equal pool under the computed tolerance
    `max(2*tick, 0.10*ATR) = 0.2`. The explicit `equal_tolerance=0.01` removes the pair while the
    swing levels themselves survive, and a generous override cannot count an ineligible source.
    """

    values = _probe.candles([(112, 114, 111, 113)] * 4, "buy")
    levels = (100.0, 100.05)
    assert abs(levels[0] - levels[1]) == pytest.approx(0.05)
    eligible = {
        "highs": [],
        "lows": [
            _override_source(level=levels[0], swing_id="level-a"),
            _override_source(level=levels[1], swing_id="level-b"),
        ],
    }

    computed = detect_liquidity_pools(values, eligible, tick_size=0.1, atr_value=1.0)
    assert computed["equal_tolerance"] == pytest.approx(0.2)
    assert computed["equal_lows"] == [pytest.approx(100.025)]

    tighter = detect_liquidity_pools(values, eligible, equal_tolerance=0.01)
    assert tighter["equal_tolerance"] == pytest.approx(0.01)
    assert tighter["equal_lows"] == []
    assert tighter["swing_lows"] == [levels[0], levels[1]]

    # A generous override still cannot pair an ineligible source with an eligible one.
    ineligible = {
        "highs": [],
        "lows": [
            _override_source(level=levels[0], swing_id="level-a"),
            _override_source(level=levels[1], swing_id="level-b", usable=False),
        ],
    }
    generous = detect_liquidity_pools(values, ineligible, equal_tolerance=1.0)
    assert generous["equal_tolerance"] == pytest.approx(1.0)
    assert generous["equal_lows"] == []


def test_r72_07_lifecycle_threshold_overrides_only_replace_their_own_rule():
    """A3-067: `zone_tolerance` and `break_buffer` replace one lifecycle rule each.

    `zone_tolerance=0.5` registers a touch the computed tolerance rejects while the invalidation
    buffer stays at the computed value, and `break_buffer=0.05` breaks a zone the default buffer
    keeps intact. Each override is also run against the other rule's fixture, so a leaked override
    would show up as a moved threshold or a moved overlap result. Neither override invents metadata:
    when tick/ATR are absent the metadata-dependent threshold is *not computable*, so it is `None`
    with `metadata_state == "unknown"` and a non-empty reason (`0.0` is a valid threshold value,
    never the meaning of "unknown").
    """

    touch_values = _probe.candles(
        [(112, 114, 111, 113), (110.4, 111.0, 110.3, 110.8)], "buy",
    )

    def touch_lifecycle(**kwargs):
        return analyze_zone_lifecycle(
            candles=touch_values, low=100, high=110, side="buy", origin_index=0,
            departure_end_index=0, zone_id="override-zone", timeframe="H1", tf_minutes=60,
            **kwargs,
        )

    default = touch_lifecycle(tick_size=0.1, atr_current=1.0)
    assert default.visits == ()
    assert default.invalidation_buffer == pytest.approx(0.1)

    overridden = touch_lifecycle(tick_size=0.1, atr_current=1.0, zone_tolerance=0.5)
    assert len(overridden.visits) == 1
    assert overridden.invalidation_buffer == pytest.approx(0.1)   # only the overlap rule moved
    assert overridden.lifecycle_broken is False

    # Cross-control: `break_buffer` moves the invalidation threshold and nothing else. The overlap
    # rule still rejects this candle (`visits == ()`, exactly as in the default above), so the new
    # threshold cannot be what registered a touch.
    invalidation_leak = touch_lifecycle(tick_size=0.1, atr_current=1.0, break_buffer=0.05)
    assert invalidation_leak.invalidation_buffer == pytest.approx(0.05)
    assert invalidation_leak.visits == ()
    assert invalidation_leak.lifecycle_broken is False

    break_values = _probe.candles(
        [(112, 114, 111, 113), (105, 106, 99.90, 99.93)], "buy",
    )

    def break_lifecycle(**kwargs):
        return analyze_zone_lifecycle(
            candles=break_values, low=100, high=110, side="buy", origin_index=0,
            departure_end_index=0, zone_id="override-zone", timeframe="H1", tf_minutes=60,
            **kwargs,
        )

    intact = break_lifecycle(tick_size=0.1, atr_current=1.0)
    assert intact.invalidation_buffer == pytest.approx(0.1)
    assert intact.lifecycle_broken is False

    broken = break_lifecycle(tick_size=0.1, atr_current=1.0, break_buffer=0.05)
    assert broken.invalidation_buffer == pytest.approx(0.05)
    assert broken.lifecycle_broken is True

    # Cross-control: `zone_tolerance` moves the overlap rule and nothing else. The invalidation
    # threshold stays at the computed 0.1 (a leaked override would show up as 0.5) and the zone is
    # left unbroken, exactly as without the override.
    overlap_leak = break_lifecycle(tick_size=0.1, atr_current=1.0, zone_tolerance=0.5)
    assert overlap_leak.invalidation_buffer == pytest.approx(0.1)
    assert overlap_leak.lifecycle_broken is False

    # Missing metadata: the explicit overlap override still applies on its own (it needs no
    # metadata), but the metadata-dependent buffer is not computable.
    without_metadata = touch_lifecycle(zone_tolerance=0.5)
    assert len(without_metadata.visits) == 1
    assert without_metadata.metadata_state == "unknown"
    assert isinstance(without_metadata.metadata_reason, str)
    assert without_metadata.metadata_reason.strip()
    # A threshold that cannot be computed is None -- never 0, which is a real threshold value.
    assert without_metadata.invalidation_buffer is None
    # Unknown metadata lowers usability; it must not invent terminal evidence.
    assert without_metadata.lifecycle_broken is False

    # The same close with missing metadata: a zero buffer would read `99.93 < 100.0` as an
    # invalidation, but an unknown threshold cannot (A3R3-02). The zone keeps no break evidence.
    without_metadata_break = break_lifecycle()
    assert without_metadata_break.metadata_state == "unknown"
    assert without_metadata_break.invalidation_buffer is None
    assert without_metadata_break.lifecycle_broken is False


# --- A3-068: ATR/tick sources are read at the point of evaluation ----------------------------

_ATR_WARMUP_BARS = 16
_ATR_DEPARTURE_INDEX = 17


def _atr_source_candles(extra_rows=()):
    """A3-068 fixture: calm warm-up, bearish base, bullish departure, tail, plus extra bars.

    `extra_rows` lets a caller append future bars (volatility) after the event, which must not
    change any formation reference taken at the event.
    """

    start = datetime.fromisoformat(_probe.stamp(0))
    rows = (
        [(100, 101, 99, 100.5)] * _ATR_WARMUP_BARS
        + [(101, 101.5, 99.0, 99.5)]
        + [(99.6, 104.0, 99.5, 103.5)]
        + [(103.5, 104.5, 103.0, 104.0), (104.0, 105.0, 103.5, 104.5)]
        + list(extra_rows)
    )
    values = [
        Candle(
            time=start + timedelta(hours=index), open=open_, high=high, low=low,
            close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    assert not validate_smc_candles(values, "H1")
    return values


def test_r72_07_formation_atr_is_causal_and_never_latest_fallback():
    """A3-068: the formation ATR is read causally at the event, never replaced by a latest ATR.

    The reference sits on the close strictly before the event bar, later volatile bars cannot move
    it, and before the published warm-up boundary the source stays missing: `measure_departure`
    reports `unavailable`, the detector candidate keeps that status, and even a valid BOS cannot
    promote such a candidate. The same valid BOS does confirm a candidate whose formation ATR
    exists, so the refusal is about the missing source.
    """

    values = _atr_source_candles()
    reference = atr_reference_before_event(
        values, timeframe="H1", event_index=_ATR_DEPARTURE_INDEX,
    )
    assert reference is not None
    assert reference.timeframe == "H1"
    assert reference.period == 14
    # Cutoff alignment: the reference is the close before the event bar, not the series end.
    assert reference.reference_time == _probe.stamp(_ATR_DEPARTURE_INDEX)
    assert reference.event_time == _probe.stamp(_ATR_DEPARTURE_INDEX + 1)

    # Future volatility cannot change a formation reference.
    volatile = [(90, 120, 80, 110)] * 5
    formation_at_event = atr_value_before_event(
        values, timeframe="H1", event_index=_ATR_DEPARTURE_INDEX,
    )
    formation_with_future = atr_value_before_event(
        _atr_source_candles(volatile), timeframe="H1", event_index=_ATR_DEPARTURE_INDEX,
    )
    assert formation_at_event is not None
    assert formation_with_future == formation_at_event

    # Before the warm-up boundary there is no source at all — no latest fallback.
    start = datetime.fromisoformat(_probe.stamp(0))
    short_rows = (
        [(100, 101, 99, 100.5)] * 10
        + [(101, 101.5, 99.0, 99.5)]
        + [(99.6, 104.0, 99.5, 103.5)]
    )
    short_values = [
        Candle(
            time=start + timedelta(hours=index), open=open_, high=high, low=low,
            close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(short_rows)
    ]
    assert not validate_smc_candles(short_values, "H1")
    short_departure_index = 11
    assert atr_reference_before_event(
        short_values, timeframe="H1", event_index=short_departure_index,
    ) is None

    measured = measure_departure(
        short_values[short_departure_index], direction="buy", atr_before_event=None,
    )
    assert measured["status"] == "unavailable"
    assert measured["reason_codes"] == ["DEPARTURE_ATR_UNAVAILABLE"]

    short_candidate = next(
        item for item in detect_order_block_candidates(short_values, symbol="EUR/USD", timeframe="H1")
        if item["departure_end_index"] == short_departure_index
    )
    assert short_candidate["departure_measurement"]["status"] == "unavailable"

    # A valid BOS for the warm-up chain: the confirmation step must still refuse.
    def bos_event(index):
        return dict(
            event_type="BOS", direction="bullish", event_id=f"atr-bos-{index}",
            broken_level_id=f"atr-level-{index}", status="confirmed", confirmed=True,
            confirmed_at=_probe.stamp(index + 1), occurred_at=_probe.stamp(index + 1),
            timeframe="H1", occurred_index=index,
        )

    refused = confirm_order_block_candidate(
        short_candidate, [bos_event(short_departure_index + 1)], candles=short_values,
    )
    assert refused["lifecycle_status"] == "candidate"
    assert refused["available_at"] is None
    assert "OB_DEPARTURE_MEASUREMENT_UNAVAILABLE" in refused["reason_codes"]

    # Control: the same event shape confirms the candidate whose formation ATR exists.
    long_candidate = next(
        item for item in detect_order_block_candidates(values, symbol="EUR/USD", timeframe="H1")
        if item["departure_end_index"] == _ATR_DEPARTURE_INDEX
    )
    assert long_candidate["departure_measurement"]["status"] == "ok"
    confirmed = confirm_order_block_candidate(
        long_candidate,
        [bos_event(_ATR_DEPARTURE_INDEX + 1)],
        candles=values,
    )
    assert confirmed["lifecycle_status"] == "confirmed"
    assert confirmed["available_at"] == _probe.stamp(_ATR_DEPARTURE_INDEX + 2)


def test_r72_07_formation_and_current_atr_keep_their_own_source():
    """A3-068: formation ATR and current ATR are read from their own points in time.

    The fixture ends with volatile bars, so the causal ATR before the departure bar and the
    current ATR at the last bar differ by design. The detector must use the formation value, while
    the lifecycle thresholds follow the current value passed in — neither substitutes the other.
    An unsupported timeframe, or an event time that matches no candle close, is rejected instead
    of silently defaulting to the latest value.
    """

    volatile = [(90, 120, 80, 110)] * 4
    values = _atr_source_candles(volatile)
    formation = atr_value_before_event(
        values, timeframe="H1", event_index=_ATR_DEPARTURE_INDEX,
    )
    current = atr_value_before_event(values, timeframe="H1", event_index=len(values) - 1)
    assert formation is not None and current is not None
    assert current > formation  # the fixture keeps the two sources distinguishable

    candidate = next(
        item for item in detect_order_block_candidates(values, symbol="EUR/USD", timeframe="H1")
        if item["departure_end_index"] == _ATR_DEPARTURE_INDEX
    )
    assert candidate["departure_measurement"]["atr_before_event"] == pytest.approx(formation)

    tick = 0.1

    def lifecycle(atr_current):
        return analyze_zone_lifecycle(
            candles=values, low=99.0, high=101.5, side="buy",
            origin_index=_ATR_DEPARTURE_INDEX - 1,
            departure_end_index=_ATR_DEPARTURE_INDEX, zone_id="atr-source",
            timeframe="H1", tf_minutes=60, tick_size=tick, atr_current=atr_current,
        )

    from_current = lifecycle(current)
    from_formation = lifecycle(formation)
    assert from_current.invalidation_buffer == pytest.approx(max(1 * tick, 0.05 * current))
    assert from_formation.invalidation_buffer == pytest.approx(max(1 * tick, 0.05 * formation))
    assert from_current.invalidation_buffer != from_formation.invalidation_buffer

    # Timeframe and cutoff rules fail closed instead of defaulting.
    with pytest.raises(ValueError):
        atr_value_before_event(values, timeframe="M1", event_index=_ATR_DEPARTURE_INDEX)
    with pytest.raises(ValueError):
        atr_reference_before_event(values, timeframe="H1", event_time=_probe.stamp(999))


# --- A3-079: FVG fill keeps identity and is not a break --------------------------------------

def test_r72_09_full_fvg_fill_is_not_a_break():
    """A3-079: a fully filled FVG keeps its identity and is a fill, not an invalidation.

    The fixture is the task62 full-fill case (valid H1 OHLC, the gap created at bar 2 and swept by
    bar 3), reused here instead of a new one. Original bounds, the zone's own low/high and the
    identity fields stay untouched, and the fill step itself must not raise terminal/broken state —
    the fill is a state of its own.
    """

    rows = [
        (100, 101, 99, 100),
        (100, 102, 99, 101),
        (102, 112, 102, 110),
        (110, 111, 99, 100),
    ]
    start = datetime(2026, 9, 1, tzinfo=timezone.utc)
    values = [
        Candle(
            time=start + timedelta(hours=index), open=open_, high=high, low=low,
            close=close, volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]
    assert not validate_smc_candles(values, "H1")
    zone = {
        "zone_id": "smcz-full-fill",
        "setup_id": "smcs-full-fill",
        "type": "bullish_fvg",
        "zone_type": "bullish_fvg",
        "family": "fvg",
        "direction": "buy",
        "low": 100.0,
        "high": 110.0,
        "original_bounds": {"low": 100.0, "high": 110.0},
        "origin_index": 2,
        "formation_end_index": 2,
        "lifecycle_status": "confirmed",
        "broken": False,
    }

    result = update_fvg_fill(zone, values, tick_size=0.1, timeframe="H1")

    # Fill state expected from the fixture rows: the gap is swept by the last candle.
    assert result["fill_status"] == "filled"
    assert result["fill_ratio"] == 1.0
    assert result["remaining_bounds"] == {"low": 100.0, "high": 100.0}

    # Identity and original bounds are untouched by the fill step.
    assert result["zone_id"] == zone["zone_id"]
    assert result["setup_id"] == zone["setup_id"]
    assert result["original_bounds"] == zone["original_bounds"]
    assert result["low"] == zone["low"]
    assert result["high"] == zone["high"]

    # A full fill is not a break: no terminal state may be raised by filling the gap.
    assert result["broken"] is False
    assert result["lifecycle_status"] == "confirmed"


def test_r72_09_intentional_invalid_data_reports_its_own_reason():
    """A3-080: the intentional invalid fixture is separated from the positives by its own reason.

    The invalid bar is the R72-09 example shape (close `110.2` below low `111.2`); the control below
    is the same bar with the low corrected to `110.2`, which is what the F01-T60-BUY fixture fix
    did. So the validator reason is driven by the data, not by the bar family, and every positive
    fixture in this file stays on the clean side of the same validator.
    """

    start = datetime(2026, 9, 1, tzinfo=timezone.utc)

    def build(tail):
        rows = [(112, 114, 111, 113)] * 4 + [tail]
        return [
            Candle(
                time=start + timedelta(hours=index), open=open_, high=high, low=low,
                close=close, volume=100,
            )
            for index, (open_, high, low, close) in enumerate(rows)
        ]

    invalid_values = build((112, 113, 111.2, 110.2))
    assert invalid_values[4].close < invalid_values[4].low

    issues = validate_smc_candles(invalid_values, "H1")
    # The negative side names its own reason, with the offending bar.
    assert [issue.code for issue in issues] == ["SMC_OHLC_INVALID"]
    assert issues[0].index == 4
    assert issues[0].field == "ohlc"

    # Control: the same bar with the F01-T60-BUY correction is clean, so the positive fixtures of
    # this file and this negative share one validator and differ only by the data.
    fixed_values = build((112, 113, 110.2, 110.2))
    assert fixed_values[4].close == fixed_values[4].low
    assert validate_smc_candles(fixed_values, "H1") == ()
    # The earlier bars are identical in both series, so nothing else can explain the reason.
    assert [candle.close for candle in invalid_values[:4]] == [
        candle.close for candle in fixed_values[:4]
    ]
    assert [candle.low for candle in invalid_values[:4]] == [
        candle.low for candle in fixed_values[:4]
    ]
