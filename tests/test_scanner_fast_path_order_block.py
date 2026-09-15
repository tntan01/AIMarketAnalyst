"""D102-06 — `h1_order_block_v2` proves a canonical, BOS-confirmed order block.

The scenario owns a dedicated candle path (``_bearish_order_block_path``) whose
causal order makes the BOS source resolvable:

    history BOS -> anchor | new swing high after it | >= 5 confirming candles
    (no further BOS) | opposite-colour base | bearish departure | follow-through
    that closes through the tracked low

Everything below runs the REAL façade/snapshot/evaluator; nothing is injected.
"""

from __future__ import annotations

import importlib

from core.smc_canonical_context import build_canonical_timeframe_context
from core.smc_context import (
    _filter_swings_by_atr,
    atr_value_before_event,
    external_swing_points,
    structure_break_buffer,
)
from core.smc_snapshot import build_smc_snapshot, evaluate_smc_snapshot

_FIXTURES = importlib.import_module("tests.scanner_fast_path_fixtures")
_BASELINE = importlib.import_module("tests.test_scanner_fast_path_baseline")

TICK = _BASELINE._TICK_SIZE
OB_CASE = "h1_order_block_v2"


def _case(name: str) -> dict:
    return next(c for c in _BASELINE._CORPUS["cases"] if c["name"] == name)


def _candles(name: str = OB_CASE, *, control: bool = False):
    case = _case(name)
    return (
        _FIXTURES.make_order_block_control_candles(case)
        if control
        else _FIXTURES.make_candles(case)
    )


def _snapshot(candles):
    cutoff = _BASELINE._cutoff(candles)
    return build_smc_snapshot(
        candles,
        symbol="EUR/USD",
        as_of=cutoff,
        m15_as_of=cutoff,
        tick_size=TICK,
    )


def _selected_block(context, candles):
    """The canonical OB zone the sell side actually selected."""

    evaluation = evaluate_smc_snapshot(_snapshot(candles))
    selected_id = evaluation.selection("sell").selected_zone_id
    return next(
        zone for zone in context["order_blocks"] if zone.get("zone_id") == selected_id
    )


def _h1(candles):
    cutoff = _BASELINE._cutoff(candles)
    return [candle for candle in candles["H1"] if candle.time <= cutoff]


def _index_of_close(h1, occurred_at: str) -> int:
    """Index of the candle whose CLOSE boundary is *occurred_at*.

    ``occurred_at`` is a close instant, so it equals the NEXT candle's open
    time; matching on open time would report the following bar.
    """

    from datetime import timedelta

    target = str(occurred_at)
    for index, candle in enumerate(h1):
        close_at = candle.time + timedelta(hours=1)
        if close_at.isoformat() == target:
            return index
    raise AssertionError(f"no candle closes at {occurred_at}")


# ---------------------------------------------------------------------------
# 1. The selected candidate is the order block
# ---------------------------------------------------------------------------


def test_selected_candidate_is_the_confirmed_order_block():
    evaluation = evaluate_smc_snapshot(_snapshot(_candles()))
    selection = evaluation.selection("sell")

    # The block is confirmed; the side keeps a watch state because this corpus
    # case carries no plan (the order policy has no R:R floor), which is the
    # canonical ``watch_zone`` outcome and not a missing selection.
    assert selection.state in {"evaluated", "watch_zone"}
    assert selection.selected_zone_id
    selected = next(
        candidate
        for candidate in evaluation.candidate_sets["sell"].ordered
        if candidate.zone_id == selection.selected_zone_id
    )
    # ``ob`` is the canonical family name of an order block (BQLC spec §4.2).
    assert selected.family == "ob"
    assert selected.side == "sell"
    assert selected.lifecycle_status == "confirmed"
    assert selected.confirmation_event_id
    assert selected.quality_raw is not None
    # The buy side is not the one this scenario names.
    assert evaluation.selection("buy").selected_zone_id is None


def test_the_selected_identity_is_deterministic():
    first = evaluate_smc_snapshot(_snapshot(_candles()))
    second = evaluate_smc_snapshot(_snapshot(_candles()))
    assert first.selection("sell").selected_zone_id == (
        second.selection("sell").selected_zone_id
    )


def test_the_fvg_is_present_but_never_replaces_the_block():
    """The FVG is a sibling candidate, not a substitute for the OB evidence."""

    evaluation = evaluate_smc_snapshot(_snapshot(_candles()))
    ordered = evaluation.candidate_sets["sell"].ordered
    families = [candidate.family for candidate in ordered]
    assert "ob" in families and "fvg" in families
    selected_id = evaluation.selection("sell").selected_zone_id
    selected = next(c for c in ordered if c.zone_id == selected_id)
    assert selected.family == "ob"


# ---------------------------------------------------------------------------
# 2. The BOS is causal, in-window and the real source of the confirmation
# ---------------------------------------------------------------------------


def test_the_bos_is_causal_and_inside_the_task44_window():
    candles = _candles()
    h1 = _h1(candles)
    context = build_canonical_timeframe_context(
        candles["H1"],
        symbol="EUR/USD",
        timeframe="H1",
        as_of=_BASELINE._cutoff(candles),
        tick_size=TICK,
    )
    block = _selected_block(context, candles)
    departure_index = int(block["departure_end_index"])
    event_id = str(block["confirmation_event_id"])

    event = next(e for e in context["structure_events"] if e.get("event_id") == event_id)
    assert event["direction"] == "bearish"
    occurred_at = event["occurred_at"]
    bos_index = _index_of_close(h1, occurred_at)
    # Task44 window, measured on real candle indices.
    assert departure_index < bos_index <= departure_index + 3
    assert event["confirmed_at"] <= occurred_at or event["confirmed_at"] == occurred_at


def test_the_bos_source_swing_is_present_in_the_prefix():
    """The source swing high must exist in the prefix the BOS candle sees."""

    candles = _candles()
    h1 = _h1(candles)
    context = build_canonical_timeframe_context(
        candles["H1"],
        symbol="EUR/USD",
        timeframe="H1",
        as_of=_BASELINE._cutoff(candles),
        tick_size=TICK,
    )
    block = _selected_block(context, candles)
    event = next(
        e
        for e in context["structure_events"]
        if e.get("event_id") == block["confirmation_event_id"]
    )
    bos_index = _index_of_close(h1, event["occurred_at"])
    # The BOS lands inside the Task44 window; the exact delta is the design's
    # own (1..3), not a fixed number.
    delta = bos_index - int(block["departure_end_index"])
    assert 1 <= delta <= 3
    prefix = h1[:bos_index]
    swings = _filter_swings_by_atr(
        prefix,
        external_swing_points(
            prefix, symbol="EUR/USD", timeframe="H1", lookback=5
        ),
    )
    source_ids = {str(item.get("swing_id")) for item in swings["highs"]}
    assert str(event["source_swing_id"]) in source_ids
    # The pivot is after the previous protected update (the older history BOS).
    assert event["occurred_at"] > context["structure_events"][0]["occurred_at"]


def test_the_source_swing_satisfies_the_anchor_and_confirmation_bounds():
    """The four BOS-source conditions of D102-06, asserted on the swing record.

    ``detect_structure_bos`` will only use a swing high whose pivot is strictly
    after the anchor set by the previous protected update AND whose confirmation
    is already available at the BOS candle.  Both are read from the swing the
    event names, in the prefix that candle actually sees.
    """

    candles = _candles()
    h1 = _h1(candles)
    context = build_canonical_timeframe_context(
        candles["H1"],
        symbol="EUR/USD",
        timeframe="H1",
        as_of=_BASELINE._cutoff(candles),
        tick_size=TICK,
    )
    block = _selected_block(context, candles)
    event = next(
        e
        for e in context["structure_events"]
        if e.get("event_id") == block["confirmation_event_id"]
    )
    bos_index = _index_of_close(h1, event["occurred_at"])

    # (4) still inside the Task44 window.
    delta = bos_index - int(block["departure_end_index"])
    assert 1 <= delta <= 3

    # (3) the source swing exists in the prefix the BOS candle sees.
    prefix = h1[:bos_index]
    swings = _filter_swings_by_atr(
        prefix,
        external_swing_points(prefix, symbol="EUR/USD", timeframe="H1", lookback=5),
    )
    source = next(
        item
        for item in swings["highs"]
        if str(item.get("swing_id")) == str(event["source_swing_id"])
    )

    # (1) the pivot is strictly after the anchor the BOS candle itself saw.
    # The final state's anchor has already been moved BY this BOS, so the
    # prefix is replayed on its own to read the anchor that was in force.
    from core.smc_structure_replay import replay_smc_structure

    prefix_state = replay_smc_structure(
        prefix,
        symbol="EUR/USD",
        timeframe="H1",
        as_of=event["occurred_at"],
        tick_size=TICK,
    )["structure_state"]
    anchor_start = prefix_state["anchor_start_at"]
    assert anchor_start is not None
    assert source["pivot_time"] > anchor_start
    assert source["pivot_time"] < event["occurred_at"]

    # (2) the swing was already confirmed when the BOS candle closed.
    assert source["confirmed_at"] <= event["occurred_at"]
    assert source["confirmed"] is True
    assert source.get("provisional") is not True


def test_the_bos_candle_clears_the_break_buffer():
    candles = _candles()
    h1 = _h1(candles)
    cutoff = _BASELINE._cutoff(candles)
    context = build_canonical_timeframe_context(
        candles["H1"],
        symbol="EUR/USD",
        timeframe="H1",
        as_of=cutoff,
        tick_size=TICK,
    )
    block = _selected_block(context, candles)
    event = next(
        e
        for e in context["structure_events"]
        if e.get("event_id") == block["confirmation_event_id"]
    )
    bos_index = _index_of_close(h1, event["occurred_at"])
    prefix = h1[:bos_index]
    atr = atr_value_before_event(prefix, timeframe="H1", event_index=bos_index - 1)
    buffer = structure_break_buffer(atr_value=atr, tick_size=TICK)
    tracked = float(context["structure_state"]["tracked_continuation_level"])
    assert buffer is not None and buffer > 0
    assert h1[bos_index].close < tracked - buffer


# ---------------------------------------------------------------------------
# 3. The block carries canonical evidence and passes the mandatory geometry
# ---------------------------------------------------------------------------


def test_the_order_block_carries_canonical_evidence_and_passes_geometry():
    candles = _candles()
    evaluation = evaluate_smc_snapshot(_snapshot(candles))
    selected = next(
        candidate
        for candidate in evaluation.candidate_sets["sell"].ordered
        if candidate.zone_id == evaluation.selection("sell").selected_zone_id
    )
    assert selected.mandatory_passed is True
    assert selected.rejection_codes == ()
    geometry = selected.geometry or {}
    assert geometry.get("bounds_valid") is True
    assert geometry.get("within_width_gate") is True
    assert geometry.get("within_distance_gate") is True

    context = build_canonical_timeframe_context(
        candles["H1"],
        symbol="EUR/USD",
        timeframe="H1",
        as_of=_BASELINE._cutoff(candles),
        tick_size=TICK,
    )
    zone = next(
        z for z in context["order_blocks"] if z.get("zone_id") == selected.zone_id
    )
    bounds = zone["original_bounds"]
    assert bounds["low"] < bounds["high"]
    measurement = zone["departure_measurement"]
    assert measurement["status"] == "ok"
    assert measurement["body_atr"] > 0
    assert (
        zone["formation_atr"]
        == measurement["atr_before_event"]
    ), "the formation ATR must be the causal reference of the departure"
    assert zone["tick_size"] == TICK
    assert zone["available_at"] == zone["confirmed_at"]
    assert selected.available_at == zone["available_at"]


# ---------------------------------------------------------------------------
# 4. Causal control: same history, no post-departure BOS
# ---------------------------------------------------------------------------


def test_without_the_post_departure_bos_the_block_is_not_confirmed():
    """The control differs ONLY in the follow-through candle."""

    live = evaluate_smc_snapshot(_snapshot(_candles()))
    control = evaluate_smc_snapshot(_snapshot(_candles(control=True)))

    live_ob = next(
        candidate
        for candidate in live.candidate_sets["sell"].ordered
        if candidate.family == "ob"
        and candidate.zone_id == live.selection("sell").selected_zone_id
    )
    assert live_ob.lifecycle_status == "confirmed"
    assert live_ob.confirmation_event_id

    control_blocks = [
        candidate
        for candidate in control.candidate_sets["sell"].candidates
        if candidate.family == "ob"
    ]
    assert control_blocks, "the same history must still produce the block"
    assert all(
        candidate.confirmation_event_id is None
        and candidate.lifecycle_status == "candidate"
        for candidate in control_blocks
    ), "without the BOS no order block may be confirmed"


# ---------------------------------------------------------------------------
# 5/6. The other scenarios keep their semantics
# ---------------------------------------------------------------------------


def test_the_fvg_scenario_still_selects_its_fvg():
    evaluation = evaluate_smc_snapshot(_snapshot(_candles("h1_only_fvg_v2")))
    selection = evaluation.selection("buy")
    assert selection.selected_zone_id
    selected = next(
        candidate
        for candidate in evaluation.candidate_sets["buy"].ordered
        if candidate.zone_id == selection.selected_zone_id
    )
    assert selected.family == "fvg"
    assert evaluation.selection("sell").selected_zone_id is None


def test_the_other_scenarios_keep_their_expected_shape():
    expected = {
        "raw_empty_v2": (None, None),
        "buy_setup_v2": ("buy", None),
        "sell_setup_v2": (None, "sell"),
        "broken_invalid_v2": (None, None),
    }
    for name, (buy_sided, sell_sided) in expected.items():
        evaluation = evaluate_smc_snapshot(_snapshot(_candles(name)))
        buy = evaluation.selection("buy")
        sell = evaluation.selection("sell")
        assert (buy.selected_zone_id is not None) is (buy_sided == "buy"), name
        assert (sell.selected_zone_id is not None) is (sell_sided == "sell"), name
