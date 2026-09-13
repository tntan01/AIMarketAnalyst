from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    apply_protected_swing_from_bos,
    confirm_choch_candidate,
    detect_choch_candidate,
    detect_structure_bos,
    expire_structure_events,
    invalidate_choch_candidate_on_reclaim,
    initialize_structure_state,
    structure_break_buffer,
    structure_event_identity,
)


def swing(swing_id, kind, level, pivot, confirmed, *, provisional=False, usable=True):
    return {
        "swing_id": swing_id,
        "kind": kind,
        "level": level,
        "pivot_time": f"2026-01-{pivot:02d}T00:00:00Z",
        "confirmed_at": f"2026-01-{confirmed:02d}T00:00:00Z",
        "confirmed": True,
        "usable": usable,
        "provisional": provisional,
    }


def candle(day, hour, *, close, high=None, low=None):
    time = datetime(2026, 1, day, hour, tzinfo=timezone.utc)
    high = max(110.0, close) if high is None else high
    low = min(90.0, close) if low is None else low
    return Candle(time=time, open=100.0, high=high, low=low, close=close)


def bullish_swings():
    return {
        "highs": [
            swing("H0", "high", 105.0, 1, 2),
            swing("H1", "high", 110.0, 3, 4),
            # Confirmed after the break; it must not replace H1 in this prefix.
            swing("H2", "high", 116.0, 9, 10),
        ],
        "lows": [
            swing("L0", "low", 95.0, 2, 3),
            swing("L1", "low", 100.0, 4, 5),
            # Latest swing overall, but after the break and therefore not source.
            swing("L2", "low", 94.0, 9, 10),
        ],
    }


def bearish_swings():
    return {
        "highs": [
            swing("H0", "high", 105.0, 1, 2),
            swing("H1", "high", 103.0, 4, 5),
            swing("H2", "high", 108.0, 9, 10),
        ],
        "lows": [
            swing("L0", "low", 95.0, 2, 3),
            swing("L1", "low", 90.0, 3, 4),
            swing("L2", "low", 84.0, 9, 10),
        ],
    }


def test_break_buffer_uses_tick_and_atr_and_rejects_missing_inputs():
    assert structure_break_buffer(atr_value=10.0, tick_size=0.4) == 1.0
    assert structure_break_buffer(atr_value=1.0, tick_size=0.7) == 1.4
    assert structure_break_buffer(atr_value=None, tick_size=0.1) is None
    assert structure_break_buffer(atr_value=1.0, tick_size=0.0) is None


def test_bullish_bos_requires_strict_close_and_selects_causal_source_low():
    swings = bullish_swings()
    as_of = "2026-01-08T12:00:00Z"
    state = initialize_structure_state(swings, as_of=as_of)
    assert state["tracked_continuation_id"] == "H1"

    exact_boundary = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.0, high=113.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of=as_of,
    )
    assert exact_boundary["bos"] is False
    assert "SMC_WICK_ONLY_BREAK" in exact_boundary["reason_codes"]

    result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of=as_of,
    )
    assert result["bos"] is True
    assert result["event"]["event_type"] == "BOS"
    assert result["event"]["direction"] == "bullish"
    assert result["event"]["broken_level_id"] == "H1"
    assert result["event"]["source_swing_id"] == "L1"
    assert result["structure_state"]["protected_swing_id"] == "L1"
    assert result["structure_state"]["source_bos_id"] == result["event"]["event_id"]
    assert result["event"]["occurred_at"] == "2026-01-08T12:00:00+00:00"


def test_bearish_bos_is_mirror_and_uses_high_source():
    swings = bearish_swings()
    as_of = "2026-01-08T12:00:00Z"
    state = initialize_structure_state(swings, as_of=as_of)
    assert state["tracked_continuation_id"] == "L1"

    result = detect_structure_bos(
        swings,
        [candle(8, 8, close=88.99, low=87.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of=as_of,
    )
    assert result["bos"] is True
    assert result["event"]["direction"] == "bearish"
    assert result["event"]["broken_level_id"] == "L1"
    assert result["event"]["source_swing_id"] == "H1"
    assert result["structure_state"]["protected_swing_id"] == "H1"


def test_wick_only_bearish_break_does_not_update_protected_state():
    swings = bearish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    result = detect_structure_bos(
        swings,
        [candle(8, 8, close=89.0, low=87.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
    )
    assert result["bos"] is False
    assert "SMC_WICK_ONLY_BREAK" in result["reason_codes"]
    assert result["structure_state"].get("protected_swing_id") is None


def test_provisional_fallback_never_creates_confirmed_bos():
    swings = bullish_swings()
    swings["highs"][1]["provisional"] = True
    state = {
        **initialize_structure_state(bullish_swings()),
        "tracked_continuation_id": "H1",
        "tracked_continuation_level": 110.0,
        "direction": "bullish",
        "state": "bullish",
        "bootstrap_ready_at": "2026-01-05T00:00:00+00:00",
        "anchor_start_at": "2026-01-01T00:00:00+00:00",
    }
    result = detect_structure_bos(
        swings,
        [candle(8, 8, close=112.0, high=113.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
    )
    assert result["bos"] is False
    assert "SMC_CONTINUATION_REFERENCE_UNAVAILABLE" in result["reason_codes"]
    assert result["structure_state"].get("protected_swing_id") is None


def test_missing_source_is_fail_closed_without_fabricating_latest_protected_swing():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    state["anchor_start_at"] = "2026-01-08T00:00:00Z"
    result = detect_structure_bos(
        swings,
        [candle(8, 8, close=112.0, high=113.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
    )
    assert result["bos"] is False
    assert "SMC_BOS_SOURCE_UNAVAILABLE" in result["reason_codes"]
    assert result["structure_state"].get("protected_swing_id") is None


def test_replay_prefix_and_continuation_scan_do_not_reemit_same_broken_level():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    first = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    replay = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
        existing_events=first["events"],
    )
    continuation = detect_structure_bos(
        swings,
        [
            candle(8, 8, close=111.01, high=112.0),
            candle(9, 8, close=113.0, high=114.0),
        ],
        timeframe="H4",
        structure_state=first["structure_state"],
        break_buffer=1.0,
        as_of="2026-01-09T12:00:00Z",
    )
    event_id = first["event"]["event_id"]
    assert event_id == structure_event_identity(
        symbol="",
        timeframe="H4",
        direction="bullish",
        broken_level_id="H1",
        occurred_at="2026-01-08T12:00:00Z",
    )
    assert replay["bos"] is False
    assert replay["event"] is None
    assert replay["replayed_event_id"] == event_id
    assert "SMC_BOS_ALREADY_EMITTED" in replay["reason_codes"]
    assert continuation["bos"] is False
    assert continuation["replayed_event_id"] == event_id


def test_different_broken_level_remains_eligible_after_prior_bos():
    swings = bullish_swings()
    initial_state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    first = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=initial_state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    next_state = dict(first["structure_state"])
    next_state.update(
        {
            "tracked_continuation_id": "H2",
            "tracked_continuation_level": 116.0,
        }
    )
    second = detect_structure_bos(
        swings,
        [candle(11, 8, close=117.01, high=118.0)],
        timeframe="H4",
        structure_state=next_state,
        break_buffer=1.0,
        as_of="2026-01-11T12:00:00Z",
    )
    assert second["bos"] is True
    assert second["event"]["broken_level_id"] == "H2"
    assert second["event"]["event_id"] != first["event"]["event_id"]
    assert second["structure_state"]["structure_events"][-1]["event_id"] == second["event"]["event_id"]


def test_protected_consumer_preserves_bullish_source_provenance_not_latest_swing():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    applied = apply_protected_swing_from_bos(
        state,
        bos_result["event"],
        swings,
        as_of="2026-01-08T12:00:00Z",
    )
    assert applied["protected_swing_id"] == "L1"
    assert applied["protected_swing_level"] == 100.0
    assert applied["protected_swing_kind"] == "low"
    assert applied["source_bos_id"] == bos_result["event"]["event_id"]
    assert applied["protected_provenance"]["bos_broken_level_id"] == "H1"
    assert applied["protected_provenance"]["protected_swing_id"] == "L1"


def test_protected_consumer_is_symmetric_for_bearish_bos():
    swings = bearish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=88.99, low=87.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    applied = apply_protected_swing_from_bos(state, bos_result["event"], swings)
    assert applied["protected_swing_id"] == "H1"
    assert applied["protected_swing_level"] == 103.0
    assert applied["protected_swing_kind"] == "high"
    assert applied["protected_provenance"]["bos_direction"] == "bearish"


def test_protected_consumer_rejects_wrong_or_missing_source_without_fallback():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    wrong_kind = dict(bos_result["event"])
    wrong_kind["source_swing_id"] = "H1"
    wrong_kind_swings = {
        "highs": list(swings["highs"]),
        "lows": list(swings["lows"]) + [dict(swings["highs"][1])],
    }
    rejected_kind = apply_protected_swing_from_bos(
        state,
        wrong_kind,
        wrong_kind_swings,
    )
    assert rejected_kind.get("protected_swing_id") is None
    assert "SMC_PROTECTED_SOURCE_NOT_CAUSAL" in rejected_kind["reason_codes"]

    missing_source = dict(bos_result["event"])
    missing_source["source_swing_id"] = None
    missing_source["protected_swing_id"] = "L2"
    rejected_missing = apply_protected_swing_from_bos(state, missing_source, swings)
    assert rejected_missing.get("protected_swing_id") is None
    assert "SMC_PROTECTED_SOURCE_MISSING" in rejected_missing["reason_codes"]


def test_older_bos_cannot_overwrite_newer_protected_cursor_and_same_event_is_idempotent():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    first = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    synced = apply_protected_swing_from_bos(state, first["event"], swings)
    repeated = apply_protected_swing_from_bos(synced, first["event"], swings)
    assert repeated["protected_swing_id"] == "L1"
    assert "SMC_PROTECTED_ALREADY_SYNCED" in repeated["reason_codes"]

    older = dict(first["event"])
    older["event_id"] = "smc-bos-older"
    older["occurred_at"] = "2026-01-07T12:00:00Z"
    older["confirmed_at"] = "2026-01-07T12:00:00Z"
    rejected = apply_protected_swing_from_bos(synced, older, swings)
    assert rejected["protected_swing_id"] == "L1"
    assert rejected["source_bos_id"] == first["event"]["event_id"]
    assert "SMC_PROTECTED_BOS_STALE" in rejected["reason_codes"]


def test_bullish_state_creates_bearish_choch_candidate_from_protected_low_only():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    result = detect_choch_candidate(
        [candle(10, 8, close=98.9, low=98.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
        as_of="2026-01-10T12:00:00Z",
    )
    assert result["choch_candidate"] is True
    assert result["candidate"]["event_type"] == "CHOCH_CANDIDATE"
    assert result["candidate"]["direction"] == "bearish"
    assert result["candidate"]["confirmed_at"] is None
    assert result["candidate"]["broken_level_id"] == "L1"
    assert result["candidate"]["protected_swing_id"] == "L1"
    assert result["structure_state"]["state"] == "bullish"
    assert result["structure_state"]["protected_swing_id"] == "L1"
    assert result["structure_state"]["candidate_source_bos_id"] == bos_result["event"]["event_id"]


def test_bearish_state_creates_bullish_candidate_symmetrically():
    swings = bearish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=88.99, low=87.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    result = detect_choch_candidate(
        [candle(10, 8, close=104.1, high=105.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
        as_of="2026-01-10T12:00:00Z",
    )
    assert result["choch_candidate"] is True
    assert result["candidate"]["direction"] == "bullish"
    assert result["candidate"]["broken_level_id"] == "H1"
    assert result["structure_state"]["state"] == "bearish"
    assert result["structure_state"]["protected_swing_kind"] == "high"


def test_candidate_boundary_and_wick_only_are_not_confirmed_breaks():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    result = detect_choch_candidate(
        [candle(10, 8, close=99.0, low=97.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    assert result["choch_candidate"] is False
    assert "SMC_WICK_ONLY_CHOCH_BREAK" in result["reason_codes"]
    assert result["structure_state"].get("candidate_id") is None


def test_missing_or_inconsistent_protected_provenance_is_fail_closed():
    result = detect_choch_candidate(
        [candle(10, 8, close=98.0, low=97.0)],
        timeframe="H4",
        structure_state={
            "state": "bullish",
            "direction": "bullish",
            "protected_swing_id": "L1",
            "protected_swing_level": 100.0,
            "source_bos_id": "BOS-1",
            "protected_updated_at": "2026-01-08T12:00:00Z",
            "protected_provenance": {
                "source_bos_id": "different-bos",
                "protected_swing_id": "L1",
            },
        },
        break_buffer=1.0,
    )
    assert result["choch_candidate"] is False
    assert "SMC_PROTECTED_SOURCE_UNAVAILABLE" in result["reason_codes"]


def test_active_candidate_is_not_reemitted_and_does_not_change_trend():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    first = detect_choch_candidate(
        [candle(10, 8, close=98.9, low=98.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    second = detect_choch_candidate(
        [candle(11, 8, close=98.0, low=97.0)],
        timeframe="H4",
        structure_state=first["structure_state"],
        break_buffer=1.0,
    )
    assert first["choch_candidate"] is True
    assert second["choch_candidate"] is False
    assert "SMC_CHOCH_CANDIDATE_ALREADY_ACTIVE" in second["reason_codes"]
    assert second["structure_state"]["state"] == "bullish"
    assert second["structure_state"]["protected_swing_id"] == "L1"


def test_bullish_candidate_reclaim_at_inclusive_boundary_is_invalidated_causally():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=98.9, low=98.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    result = invalidate_choch_candidate_on_reclaim(
        [
            candle(9, 8, close=98.0, low=97.0),  # before candidate: ignored
            candle(11, 8, close=101.0, high=102.0),  # exact inclusive reclaim
        ],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
        as_of="2026-01-11T12:00:00Z",
    )
    assert result["invalidated"] is True
    assert result["event"]["event_type"] == "CHOCH_CANDIDATE"
    assert result["event"]["invalidated_at"] == "2026-01-11T12:00:00+00:00"
    assert result["event"]["confirmed_at"] is None
    assert "CHOCH_RECLAIM_BEFORE_CONFIRMATION" in result["event"]["reason_codes"]
    assert result["structure_state"]["candidate_status"] == "invalidated"
    assert result["structure_state"]["candidate_confirmed_at"] is None
    assert result["structure_state"]["state"] == "bullish"
    assert result["structure_state"]["protected_swing_id"] == "L1"


def test_bearish_candidate_reclaim_is_symmetric():
    swings = bearish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=88.99, low=87.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=104.1, high=105.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    result = invalidate_choch_candidate_on_reclaim(
        [candle(11, 8, close=102.0, low=101.0)],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
    )
    assert result["invalidated"] is True
    assert result["event"]["direction"] == "bullish"
    assert result["event"]["protected_swing_id"] == "H1"
    assert result["structure_state"]["state"] == "bearish"
    assert result["structure_state"]["protected_swing_kind"] == "high"


def test_reclaim_scan_is_idempotent_and_no_reclaim_keeps_candidate_active():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=98.9, low=98.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    no_reclaim = invalidate_choch_candidate_on_reclaim(
        [candle(11, 8, close=100.5, high=101.0, low=99.0)],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
    )
    assert no_reclaim["invalidated"] is False
    assert no_reclaim["structure_state"]["candidate_status"] == "candidate"
    assert "SMC_CHOCH_RECLAIM_NOT_CONFIRMED" in no_reclaim["reason_codes"]

    invalidated = invalidate_choch_candidate_on_reclaim(
        [candle(11, 8, close=101.0, high=102.0)],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
    )
    replay = invalidate_choch_candidate_on_reclaim(
        [candle(11, 8, close=101.0, high=102.0)],
        timeframe="H4",
        structure_state=invalidated["structure_state"],
        break_buffer=1.0,
    )
    assert invalidated["invalidated"] is True
    assert replay["invalidated"] is False
    assert replay["event"] is None
    assert replay["invalidated_event_id"] == invalidated["event"]["event_id"]
    assert "SMC_CHOCH_CANDIDATE_ALREADY_INVALIDATED" in replay["reason_codes"]


def test_bullish_to_bearish_choch_requires_lh_then_low_then_new_bos():
    swings = bullish_swings()
    swings["highs"].append(swing("H3", "high", 105.0, 11, 12))
    swings["lows"].append(swing("L3", "low", 97.0, 12, 13))
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=98.9, low=98.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    candidate["structure_state"]["leg_count"] = 0
    result = confirm_choch_candidate(
        swings,
        [candle(13, 8, close=95.9, low=95.0)],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
        as_of="2026-01-13T12:00:00Z",
    )
    assert result["choch_confirmed"] is True
    assert result["reversal_bos"]["event_type"] == "BOS"
    assert result["reversal_bos"]["direction"] == "bearish"
    assert result["reversal_bos"]["broken_level_id"] == "L3"
    assert result["reversal_bos"]["source_swing_id"] == "H3"
    assert result["candidate"]["event_type"] == "CHOCH_CONFIRMED"
    assert result["candidate"]["confirmed_at"] == "2026-01-13T12:00:00+00:00"
    assert result["candidate"]["occurred_at"] == "2026-01-10T12:00:00+00:00"
    assert result["candidate"]["protected_swing_id"] == "L1"
    assert result["structure_state"]["state"] == "bearish"
    assert result["structure_state"]["direction"] == "bearish"
    assert result["structure_state"]["protected_swing_id"] == "H3"
    assert result["structure_state"]["source_bos_id"] == result["reversal_bos"]["event_id"]
    assert result["structure_state"]["candidate_status"] == "confirmed"


def test_bearish_to_bullish_choch_is_mirror():
    swings = bearish_swings()
    swings["lows"].append(swing("L3", "low", 95.0, 11, 12))
    swings["highs"].append(swing("H3", "high", 103.0, 12, 13))
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=88.99, low=87.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=104.1, high=105.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    result = confirm_choch_candidate(
        swings,
        [candle(13, 8, close=104.1, high=105.0)],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
        as_of="2026-01-13T12:00:00Z",
    )
    assert result["choch_confirmed"] is True
    assert result["reversal_bos"]["direction"] == "bullish"
    assert result["reversal_bos"]["broken_level_id"] == "H3"
    assert result["reversal_bos"]["source_swing_id"] == "L3"
    assert result["structure_state"]["state"] == "bullish"
    assert result["structure_state"]["protected_swing_id"] == "L3"


def test_missing_follow_through_keeps_candidate_without_confirmation():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=98.9, low=98.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    no_lh = confirm_choch_candidate(
        swings,
        [candle(13, 8, close=95.9, low=95.0)],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
    )
    assert no_lh["choch_confirmed"] is False
    assert no_lh["candidate"]["event_type"] == "CHOCH_CANDIDATE"
    assert no_lh["structure_state"]["state"] == "bullish"
    assert "SMC_CHOCH_WAITING_LH" in no_lh["reason_codes"]

    swings["highs"].append(swing("H3", "high", 105.0, 11, 12))
    only_lh = confirm_choch_candidate(
        swings,
        [candle(13, 8, close=95.9, low=95.0)],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=1.0,
    )
    assert only_lh["choch_confirmed"] is False
    assert "SMC_CHOCH_WAITING_CONTINUATION_SWING" in only_lh["reason_codes"]

    swings["lows"].append(swing("L3", "low", 97.0, 12, 13))
    boundary = confirm_choch_candidate(
        swings,
        [candle(13, 8, close=96.0, low=95.0)],
        timeframe="H4",
        structure_state=only_lh["structure_state"],
        break_buffer=1.0,
    )
    assert boundary["choch_confirmed"] is False
    assert "SMC_CHOCH_WAITING_REVERSAL_BOS" in boundary["reason_codes"]


def test_bos_expiry_keeps_history_and_protected_state_but_removes_trigger():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    event = bos_result["event"]
    before_expiry = expire_structure_events(
        bos_result["structure_state"],
        as_of="2026-01-15T03:59:59Z",
    )
    assert before_expiry["expired"] is False
    assert before_expiry["structure_state"]["protected_swing_id"] == "L1"
    at_expiry = expire_structure_events(
        before_expiry["structure_state"],
        as_of="2026-01-15T04:00:00Z",
    )
    assert at_expiry["expired"] is True
    assert event["event_id"] in at_expiry["expired_event_ids"]
    assert at_expiry["structure_state"]["event_lifecycle"][event["event_id"]] == "expired"
    assert at_expiry["structure_state"]["protected_swing_id"] == "L1"
    assert at_expiry["structure_state"]["source_bos_id"] == event["event_id"]
    assert at_expiry["events"][0]["event_id"] == event["event_id"]
    assert event["event_id"] not in at_expiry["structure_state"]["active_trigger_event_ids"]

    replay = expire_structure_events(
        at_expiry["structure_state"],
        as_of="2026-01-16T00:00:00Z",
    )
    assert replay["expired"] is False
    assert replay["expired_event_ids"] == []
    assert replay["events"][0]["event_id"] == event["event_id"]


def test_candidate_expiry_preserves_candidate_history_and_blocks_later_trigger_use():
    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos_result = detect_structure_bos(
        swings,
        [candle(8, 8, close=111.01, high=112.0)],
        timeframe="H4",
        structure_state=state,
        break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=98.9, low=98.0)],
        timeframe="H4",
        structure_state=bos_result["structure_state"],
        break_buffer=1.0,
    )
    expired = expire_structure_events(
        candidate["structure_state"],
        as_of="2026-01-17T04:00:00Z",
    )
    state_after = expired["structure_state"]
    assert expired["expired"] is True
    assert state_after["candidate_status"] == "expired"
    assert state_after["candidate_confirmed_at"] is None
    assert state_after["choch_confirmed"] is False
    assert state_after["protected_swing_id"] == "L1"
    assert state_after["candidate_event"]["event_type"] == "CHOCH_CANDIDATE"
    assert state_after["candidate_event"]["invalidated_at"] is None
    assert state_after["candidate_event_id"] in state_after["expired_event_ids"]

    late_confirm = confirm_choch_candidate(
        swings,
        [candle(18, 8, close=95.0, low=94.0)],
        timeframe="H4",
        structure_state=state_after,
        break_buffer=1.0,
    )
    late_reclaim = invalidate_choch_candidate_on_reclaim(
        [candle(18, 8, close=101.0, high=102.0)],
        timeframe="H4",
        structure_state=state_after,
        break_buffer=1.0,
    )
    assert late_confirm["choch_confirmed"] is False
    assert "SMC_CHOCH_CANDIDATE_EXPIRED" in late_confirm["reason_codes"]
    assert late_reclaim["invalidated"] is False
    assert "SMC_CHOCH_CANDIDATE_EXPIRED" in late_reclaim["reason_codes"]
