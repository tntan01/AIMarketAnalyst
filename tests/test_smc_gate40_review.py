import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from core.market_models import Candle, SmcCandleDataError
from core.smc_context import (
    atr_value_before_event,
    confirm_choch_candidate,
    detect_choch_candidate,
    detect_structure_bos,
    expire_structure_events,
    initialize_structure_state,
    structure_break_buffer,
)
from core.smc_models import SmcDataQualityState, SmcSnapshot, SmcTimeframeSnapshot
from core.smc_snapshot_cache import smc_snapshot_identity
from core.smc_structure_replay import replay_smc_structure


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "smc_gate40_structure_replay.json"


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _candles(rows: list[list[float]]) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(start + timedelta(hours=4 * index), *row)
        for index, row in enumerate(rows)
    ]


def _event_projection(result: dict) -> list[tuple[str, str, str | None]]:
    return [
        (event["event_type"], event["occurred_at"], event.get("confirmed_at"))
        for event in result["events"]
    ]


def test_gate40_fixture_replays_actual_ohlc_buy_sell_and_expected_ids_are_stable():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_id"] == "smc-gate40-structure-replay-v2"
    assert fixture["pivot_width"] == 5
    assert fixture["break_buffer_formula"] == "max(2*tick_size, 0.10*ATR_before_event)"
    for case in fixture["cases"]:
        candles = _candles(case["candles"])
        result = replay_smc_structure(
            candles,
            symbol=fixture["symbol"],
            timeframe=fixture["timeframe"],
            tick_size=fixture["tick_size"],
            pivot_width=fixture["pivot_width"],
        )
        expected = case["expected"]
        assert [item[0] for item in _event_projection(result)] == expected["event_types"]
        assert [event["event_id"] for event in result["events"]] == expected["event_ids"]
        assert [item[1] for item in _event_projection(result)] == expected["event_times"]
        assert all(event["event_id"] for event in result["events"])
        assert result["structure_state"]["state"] == expected["final_state"]
        assert result["structure_state"]["protected_swing_level"] == expected["final_protected_level"]
        for event in result["events"]:
            occurred = _time(event["occurred_at"])
            event_index = next(
                index for index, candle in enumerate(candles)
                if candle.time + timedelta(hours=4) == occurred
            )
            causal_atr = atr_value_before_event(
                candles[: event_index + 1], timeframe="H4", event_index=event_index
            )
            assert structure_break_buffer(
                atr_value=causal_atr, tick_size=fixture["tick_size"]
            ) is not None


def test_gate40_cold_cutoff_replay_matches_full_history_prefix_without_future_influence():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        candles = _candles(case["candles"])
        full = replay_smc_structure(
            candles,
            symbol=fixture["symbol"],
            timeframe=fixture["timeframe"],
            tick_size=fixture["tick_size"],
            pivot_width=fixture["pivot_width"],
        )
        for index, candle in enumerate(candles, start=1):
            cutoff = candle.time + timedelta(hours=4)
            prefix = replay_smc_structure(
                candles[:index],
                symbol=fixture["symbol"],
                timeframe=fixture["timeframe"],
                as_of=cutoff,
                tick_size=fixture["tick_size"],
                pivot_width=fixture["pivot_width"],
            )
            expected_events = [
                event
                for event in full["events"]
                if _time(
                    event.get("confirmed_at")
                    if event["event_type"] in {"BOS", "CHOCH_CONFIRMED"}
                    else event["occurred_at"]
                ) <= cutoff
            ]
            assert [event["event_id"] for event in prefix["events"]] == [
                event["event_id"] for event in expected_events
            ]
            expected_snapshot = full["snapshots"][index - 1]
            assert prefix["structure_state"].get("direction") == expected_snapshot.get("direction")
            assert prefix["structure_state"].get("source_bos_id") == expected_snapshot.get("source_bos_id")
            assert prefix["structure_state"].get("tracked_continuation_id") == expected_snapshot.get("tracked_continuation_id")
            assert prefix["structure_state"].get("protected_swing_id") == expected_snapshot.get("protected_swing_id")
            assert prefix["structure_state"].get("protected_swing_level") == expected_snapshot.get("protected_swing_level")


def test_gate40_production_builder_still_uses_legacy_swing_payload():
    from core.smc_context import _smc_for_timeframe

    rows = [[100.0, 100.5, 99.5, 100.0] for _ in range(90)]
    for index, high, low in (
        (10, 110.0, 99.0), (15, 104.0, 96.0), (20, 100.0, 90.0),
        (25, 106.0, 95.0), (30, 115.0, 100.0), (35, 108.0, 94.0),
        (40, 101.0, 85.0), (45, 107.0, 92.0), (50, 120.0, 101.0),
        (55, 110.0, 95.0), (60, 103.0, 88.0), (65, 108.0, 93.0),
        (70, 125.0, 102.0),
    ):
        rows[index] = [100.0, max(high, 100.0), min(low, 100.0), 100.0]
    candles = _candles(rows)
    saw_internal = False
    for timeframe, minutes in (("D1", 1440), ("H4", 240), ("H1", 60)):
        result = _smc_for_timeframe(candles, symbol="EURUSD", timeframe=timeframe, tf_minutes=minutes)
        assert result["external_swings"] == result["swings"]
        for item in result["internal_swings"]["highs"] + result["internal_swings"]["lows"]:
            saw_internal = True
            assert item.get("time")
            assert "pivot_time" not in item
            assert "confirmed_at" not in item
    assert "structure_bos" not in result
    assert saw_internal


def test_replay_validates_eligible_data_without_reordering_or_future_leak():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    candles = _candles(fixture["cases"][0]["candles"])
    invalid_ohlc = list(candles)
    invalid_ohlc[8] = Candle(
        invalid_ohlc[8].time, 100.0, 99.0, 100.0, 100.0
    )
    with pytest.raises(SmcCandleDataError) as ohlc_error:
        replay_smc_structure(invalid_ohlc, symbol="EURUSD", tick_size=0.01)
    assert "SMC_OHLC_INVALID" in ohlc_error.value.reason_codes

    with pytest.raises(SmcCandleDataError) as order_error:
        replay_smc_structure(list(reversed(candles)), symbol="EURUSD", tick_size=0.01)
    assert "SMC_TIMESTAMP_ORDER_INVALID" in order_error.value.reason_codes

    future_bad = Candle(
        candles[-1].time + timedelta(hours=4), 100.0, 99.0, 100.0, 100.0
    )
    clean = replay_smc_structure(
        candles, symbol="EURUSD", timeframe="H4", tick_size=0.01
    )
    cutoff = candles[-1].time + timedelta(hours=4)
    with_future = replay_smc_structure(
        candles + [future_bad], symbol="EURUSD", timeframe="H4",
        as_of=cutoff, tick_size=0.01,
    )
    assert [event["event_id"] for event in with_future["events"]] == [
        event["event_id"] for event in clean["events"]
    ]
    assert with_future["structure_state"]["state"] == clean["structure_state"]["state"]


def test_observation_width_two_is_provisional_and_cannot_confirm_structure():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    result = replay_smc_structure(
        _candles(fixture["cases"][0]["candles"]), symbol="EURUSD",
        timeframe="H4", tick_size=fixture["tick_size"], pivot_width=2,
    )
    assert result["events"] == []
    assert result["structure_state"]["direction"] is None


def test_typed_swing_round_trip_can_bootstrap_and_bos():
    from core.smc_context import external_swing_points
    from core.smc_models import SmcSwing

    candles = _candles([
        [100.0, 100.0, 90.0, 95.0], [100.0, 105.0, 95.0, 100.0], [100.0, 102.0, 92.0, 94.0],
        [100.0, 110.0, 100.0, 105.0], [100.0, 106.0, 96.0, 100.0], [100.0, 108.0, 98.0, 103.0],
    ])
    raw = external_swing_points(candles, symbol="EURUSD", timeframe="H4", lookback=1)
    typed = {"highs": [], "lows": []}
    for kind in ("highs", "lows"):
        for item in raw[kind]:
            typed[kind].append(
                SmcSwing(
                    swing_id=item["swing_id"], symbol="EURUSD", timeframe="H4",
                    kind=item["kind"], level=item["level"], pivot_time=item["pivot_time"],
                    confirmed_at=item["confirmed_at"],
                    provisional=item.get("provisional", False),
                    pivot_width=item.get("pivot_width"),
                    scope=item.get("scope"),
                ).to_dict()
            )
    state = initialize_structure_state(typed, as_of="2026-01-02T00:00:00Z")
    assert state["direction"] == "bullish"
    assert state["tracked_continuation_id"]

    fallback = external_swing_points(
        candles, symbol="EURUSD", timeframe="H4", lookback=2, provisional=True
    )
    fallback_item = next(iter(fallback["highs"] + fallback["lows"]))
    fallback_item = {
        **fallback_item,
        "symbol": "EURUSD",
        "timeframe": "H4",
    }
    fallback_typed = SmcSwing.from_dict(fallback_item).to_dict()
    assert fallback_typed["provisional"] is True
    assert fallback_typed["confirmed"] is True
    assert fallback_typed["usable"] is False

    unconfirmed = SmcSwing(
        swing_id="unconfirmed", symbol="EURUSD", timeframe="H4", kind="high",
        level=110.0, pivot_time="2026-01-01T00:00:00Z", confirmed_at=None,
        provisional=False, pivot_width=5, scope="external",
    ).to_dict()
    assert unconfirmed["confirmed"] is False
    assert unconfirmed["usable"] is False


def test_confirm_seam_rejects_reclaim_and_expiry_without_pre_set_expired_state():
    from tests.test_smc_bos import bullish_swings, candle

    swings = bullish_swings()
    state = initialize_structure_state(swings, as_of="2026-01-08T12:00:00Z")
    bos = detect_structure_bos(
        swings, [candle(8, 8, close=111.01, high=112.0)], timeframe="H4",
        symbol="EURUSD", structure_state=state, break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [candle(10, 8, close=98.9, high=101.0, low=98.0)], timeframe="H4",
        symbol="EURUSD", structure_state=bos["structure_state"], break_buffer=1.0,
        as_of="2026-01-10T12:00:00Z",
    )
    reclaimed = confirm_choch_candidate(
        swings, [
            candle(10, 8, close=98.9, high=101.0, low=98.0),
            candle(11, 8, close=101.0, high=102.0, low=99.0),
            candle(13, 8, close=95.9, high=101.0, low=95.0),
        ], timeframe="H4", symbol="EURUSD", structure_state=candidate["structure_state"],
        break_buffer=1.0, as_of="2026-01-13T12:00:00Z",
    )
    assert reclaimed["choch_confirmed"] is False
    assert reclaimed["structure_state"]["candidate_status"] == "invalidated"

    expired = confirm_choch_candidate(
        swings, [candle(10, 8, close=98.9, high=101.0, low=98.0)],
        timeframe="H4", symbol="EURUSD", structure_state=candidate["structure_state"],
        break_buffer=1.0, as_of="2026-01-17T04:00:00Z",
    )
    assert expired["choch_confirmed"] is False
    assert expired["structure_state"]["candidate_status"] == "expired"

    late_without_cutoff = confirm_choch_candidate(
        swings, [candle(18, 8, close=95.9, high=101.0, low=95.0)],
        timeframe="H4", symbol="EURUSD", structure_state=candidate["structure_state"],
        break_buffer=1.0,
    )
    assert late_without_cutoff["choch_confirmed"] is False
    assert late_without_cutoff["structure_state"]["candidate_status"] == "expired"

    bearish = __import__("tests.test_smc_bos", fromlist=["bearish_swings"]).bearish_swings()
    bearish_state = initialize_structure_state(bearish, as_of="2026-01-08T12:00:00Z")
    bearish_bos = detect_structure_bos(
        bearish, [candle(8, 8, close=88.99, low=87.0)], timeframe="H4",
        symbol="EURUSD", structure_state=bearish_state, break_buffer=1.0,
        as_of="2026-01-08T12:00:00Z",
    )
    bearish_candidate = detect_choch_candidate(
        [candle(10, 8, close=104.1, high=105.0, low=100.0)], timeframe="H4",
        symbol="EURUSD", structure_state=bearish_bos["structure_state"], break_buffer=1.0,
        as_of="2026-01-10T12:00:00Z",
    )
    bearish_late = confirm_choch_candidate(
        bearish, [candle(18, 8, close=110.0, high=111.0, low=100.0)],
        timeframe="H4", symbol="EURUSD", structure_state=bearish_candidate["structure_state"],
        break_buffer=1.0,
    )
    assert bearish_late["choch_confirmed"] is False
    assert bearish_late["structure_state"]["candidate_status"] == "expired"


def test_confirmed_candidate_remains_terminal_when_trigger_deadline_passes():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    case = fixture["cases"][0]
    result = replay_smc_structure(
        _candles(case["candles"]), symbol=fixture["symbol"],
        timeframe=fixture["timeframe"], tick_size=fixture["tick_size"],
        pivot_width=fixture["pivot_width"],
    )
    assert result["structure_state"]["candidate_status"] == "confirmed"
    later = expire_structure_events(
        result["structure_state"], as_of="2026-01-20T00:00:00Z"
    )
    assert later["structure_state"]["candidate_status"] == "confirmed"
    assert later["structure_state"]["choch_confirmed"] is True
    assert later["structure_state"]["state"] == "bearish"


def test_snapshot_rejects_future_atr_and_noncanonical_intervals():
    payload = {
        "timeframe": "H1", "interval_seconds": 14400,
        "first_eligible_close_at": "2026-01-01T00:00:00Z",
        "last_eligible_close_at": "2026-01-01T01:00:00Z", "raw_count": 2,
        "eligible_count": 2, "cutoff_filtered": 0, "session_coverage_status": "known",
        "atr_period": 14, "atr_reference": 1.0,
        "atr_reference_time": "2026-01-02T00:00:00Z",
        "atr_reference_source": "formation_prefix", "reason_codes": [],
    }
    with pytest.raises(ValueError, match="interval_seconds"):
        SmcSnapshot.from_dict({
            "symbol": "EURUSD", "as_of": "2026-01-01T04:00:00Z",
            "timeframes": [payload],
            "data_quality": {"status": "partial", "reason_codes": [], "missing_timeframes": ["D1", "H4", "M15"]},
        })
    payload["interval_seconds"] = 3600
    with pytest.raises(ValueError, match="ATR reference"):
        SmcSnapshot.from_dict({
            "symbol": "EURUSD", "as_of": "2026-01-01T04:00:00Z",
            "timeframes": [payload],
            "data_quality": {"status": "partial", "reason_codes": [], "missing_timeframes": ["D1", "H4", "M15"]},
        })


@pytest.mark.parametrize(
    ("timeframe", "interval"),
    [("D1", 86400), ("H4", 14400), ("H1", 3600), ("M15", 900)],
)
def test_snapshot_round_trip_accepts_each_canonical_timeframe_interval(timeframe, interval):
    frame = SmcTimeframeSnapshot(
        timeframe=timeframe,
        interval_seconds=interval,
        first_eligible_close_at="2026-01-01T00:00:00Z",
        last_eligible_close_at="2026-01-01T00:00:00Z",
        raw_count=1,
        eligible_count=1,
        cutoff_filtered=0,
        session_coverage_status="known",
        atr_period=14,
        atr_reference=1.0,
        atr_reference_time="2025-12-31T23:00:00Z",
        atr_reference_source="formation_prefix",
    )
    snapshot = SmcSnapshot(
        symbol="EURUSD",
        as_of="2026-01-01T04:00:00Z",
        timeframes=(frame,),
        data_quality=SmcDataQualityState(
            status="partial",
            reason_codes=(),
            missing_timeframes=tuple(
                other for other in ("D1", "H4", "H1", "M15") if other != timeframe
            ),
        ),
    )
    assert SmcSnapshot.from_dict(snapshot.to_dict()) == snapshot


def test_cache_identity_distinguishes_metadata_type_and_keeps_order_invariant():
    from tests.test_smc_snapshot_cache_task38 import _base_input

    fixture = json.loads(Path("tests/fixtures/smc_snapshot_cache_task38.json").read_text(encoding="utf-8"))
    base = _base_input(fixture)
    same = {**base, "metadata": dict(reversed(tuple(base["metadata"].items())))}
    typed_change = {**base, "metadata": {**base["metadata"], "tick_size": "0.0001"}}
    assert smc_snapshot_identity(**same) == smc_snapshot_identity(**base)
    assert smc_snapshot_identity(**typed_change) != smc_snapshot_identity(**base)
