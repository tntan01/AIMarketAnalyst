import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.market_models import Candle, candle_close_at
from core.smc_context import (
    confirm_choch_candidate,
    detect_choch_candidate,
    detect_structure_bos,
    initialize_structure_state,
)
from core.smc_structure_replay import replay_smc_structure


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "smc_structure_task37.json"


def _timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _swings(case: dict) -> dict[str, list[dict]]:
    return {
        kind: [dict(item) for item in case["swings"][kind]]
        for kind in ("highs", "lows")
    }


def _prefix_swings(swings: dict[str, list[dict]], cutoff: str) -> dict[str, list[dict]]:
    limit = _timestamp(cutoff)
    return {
        kind: [
            dict(item)
            for item in swings[kind]
            if _timestamp(item["confirmed_at"]) <= limit
        ]
        for kind in ("highs", "lows")
    }


def _candle(value: dict) -> Candle:
    return Candle(
        time=_timestamp(value["time"]),
        open=float(value["open"]),
        high=float(value["high"]),
        low=float(value["low"]),
        close=float(value["close"]),
    )


def _candles(case: dict) -> list[Candle]:
    return [_candle(phase["candle"]) for phase in case["phases"] if "candle" in phase]


def _prefix_candles(candles: list[Candle], cutoff: str) -> list[Candle]:
    limit = _timestamp(cutoff)
    return [
        candle
        for candle in candles
        if candle_close_at(candle.time, "H4") <= limit
    ]


def _projection(event: dict | None, state: dict) -> dict:
    return {
        "event_id": event.get("event_id") if event else None,
        "event_type": event.get("event_type") if event else None,
        "confirmed_at": event.get("confirmed_at") if event else None,
        "state": state.get("state"),
        "protected_swing_id": state.get("protected_swing_id"),
        "protected_swing_level": state.get("protected_swing_level"),
    }


def _run_phase(
    phase: dict,
    *,
    swings: dict[str, list[dict]],
    candles: list[Candle],
    state: dict,
    symbol: str,
    break_buffer: float,
) -> tuple[dict, dict]:
    phase_id = phase["id"]
    cutoff = phase["as_of"]
    if phase_id == "bootstrap":
        return None, initialize_structure_state(swings, as_of=cutoff)
    if phase_id == "bos":
        result = detect_structure_bos(
            swings,
            candles,
            timeframe="H4",
            symbol=symbol,
            structure_state=state,
            break_buffer=break_buffer,
            as_of=cutoff,
        )
        return result.get("event"), result["structure_state"]
    if phase_id == "candidate":
        result = detect_choch_candidate(
            candles,
            timeframe="H4",
            symbol=symbol,
            structure_state=state,
            break_buffer=break_buffer,
            as_of=cutoff,
        )
        return result.get("candidate"), result["structure_state"]
    if phase_id == "confirmed":
        result = confirm_choch_candidate(
            swings,
            candles,
            timeframe="H4",
            symbol=symbol,
            structure_state=state,
            break_buffer=break_buffer,
            as_of=cutoff,
        )
        return result.get("candidate"), result["structure_state"]
    raise AssertionError(f"unknown fixture phase: {phase_id}")


def test_task37_fixture_is_complete_and_independent_expected_is_present():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["fixture_id"] == "smc-structure-task37-v1"
    assert len(fixture["cases"]) == 2
    assert all(len(case["phases"]) == 4 for case in fixture["cases"])
    for case in fixture["cases"]:
        for phase in case["phases"]:
            assert set(phase["expected"]) == {
                "event_id",
                "event_type",
                "confirmed_at",
                "state",
                "protected_swing_id",
                "protected_swing_level",
            }


def test_batch_replay_equals_each_causal_prefix_for_buy_and_sell():
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        all_swings = _swings(case)
        all_candles = _candles(case)
        batch_state = None
        prefix_state = None

        for phase in case["phases"]:
            prefix_swings = _prefix_swings(all_swings, phase["as_of"])
            prefix_candles = _prefix_candles(all_candles, phase["as_of"])
            batch_event, batch_state = _run_phase(
                phase,
                swings=all_swings,
                candles=all_candles,
                state=batch_state,
                symbol=fixture["symbol"],
                break_buffer=fixture["break_buffer"],
            )
            prefix_event, prefix_state = _run_phase(
                phase,
                swings=prefix_swings,
                candles=prefix_candles,
                state=prefix_state,
                symbol=fixture["symbol"],
                break_buffer=fixture["break_buffer"],
            )

            expected = phase["expected"]
            assert _projection(batch_event, batch_state) == expected
            assert _projection(prefix_event, prefix_state) == expected
            assert _projection(batch_event, batch_state) == _projection(
                prefix_event, prefix_state
            )

            # The batch path receives future records deliberately; as_of and
            # candle close/confirmed_at filters must make them unobservable.
            assert len(prefix_candles) <= len(all_candles)
            assert all(
                candle_close_at(candle.time, "H4") <= _timestamp(phase["as_of"])
                for candle in prefix_candles
            )
            assert all(
                _timestamp(item["confirmed_at"]) <= _timestamp(phase["as_of"])
                for kind in ("highs", "lows")
                for item in prefix_swings[kind]
            )


def test_task37_acceptance_also_covers_actual_ohlc_structure_replay():
    fixture_path = Path(__file__).parent / "fixtures" / "smc_gate40_structure_replay.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    for case in fixture["cases"]:
        candles = [
            Candle(
                time=_timestamp("2026-01-01T00:00:00Z") + timedelta(hours=4 * index),
                open=row[0],
                high=row[1],
                low=row[2],
                close=row[3],
            )
            for index, row in enumerate(case["candles"])
        ]
        result = replay_smc_structure(
            candles,
            symbol=fixture["symbol"],
            timeframe=fixture["timeframe"],
            tick_size=fixture["tick_size"],
            pivot_width=fixture["pivot_width"],
        )
        assert [event["event_id"] for event in result["events"]]
        assert [event["event_type"] for event in result["events"]] == case["expected"]["event_types"]
        assert result["structure_state"]["state"] == case["expected"]["final_state"]
