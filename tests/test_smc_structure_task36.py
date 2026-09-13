import json
from datetime import datetime, timezone
from pathlib import Path

from core.market_models import Candle
from core.smc_context import (
    confirm_choch_candidate,
    detect_choch_candidate,
    detect_structure_bos,
    expire_structure_events,
    initialize_structure_state,
    invalidate_choch_candidate_on_reclaim,
)


FIXTURE = json.loads(
    Path("tests/fixtures/smc_structure_task36.json").read_text(encoding="utf-8")
)


def _timestamp(value):
    text = str(value)
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc)


def _swings(payload):
    result = {"highs": [], "lows": []}
    for kind in ("highs", "lows"):
        for item in payload[kind]:
            result[kind].append(
                {
                    **item,
                    "confirmed": True,
                    "usable": True,
                    "provisional": False,
                }
            )
    return result


def _candle(payload):
    return Candle(
        time=_timestamp(payload["time"]),
        open=float(payload["open"]),
        high=float(payload["high"]),
        low=float(payload["low"]),
        close=float(payload["close"]),
    )


def _sell_swings():
    return _swings(
        {
            "highs": [
                {"swing_id": "H0", "kind": "high", "level": 110.0, "pivot_time": "2026-01-01T00:00:00Z", "confirmed_at": "2026-01-02T00:00:00Z"},
                {"swing_id": "H1", "kind": "high", "level": 103.0, "pivot_time": "2026-01-04T00:00:00Z", "confirmed_at": "2026-01-05T00:00:00Z"},
                {"swing_id": "H2", "kind": "high", "level": 108.0, "pivot_time": "2026-01-09T00:00:00Z", "confirmed_at": "2026-01-10T00:00:00Z"},
            ],
            "lows": [
                {"swing_id": "L0", "kind": "low", "level": 95.0, "pivot_time": "2026-01-02T00:00:00Z", "confirmed_at": "2026-01-03T00:00:00Z"},
                {"swing_id": "L1", "kind": "low", "level": 90.0, "pivot_time": "2026-01-03T00:00:00Z", "confirmed_at": "2026-01-04T00:00:00Z"},
                {"swing_id": "L2", "kind": "low", "level": 84.0, "pivot_time": "2026-01-09T00:00:00Z", "confirmed_at": "2026-01-10T00:00:00Z"},
            ],
        }
    )


def _case(case_id):
    return next(case for case in FIXTURE["cases"] if case["id"] == case_id)


def _buy_state(as_of="2026-01-08T12:00:00Z"):
    return initialize_structure_state(_swings(FIXTURE["base_swings"]), as_of=as_of)


def _sell_state(as_of="2026-01-08T12:00:00Z"):
    return initialize_structure_state(_sell_swings(), as_of=as_of)


def _buy_bos_state():
    swings = _swings(FIXTURE["base_swings"])
    result = detect_structure_bos(
        swings,
        [_candle(_case("buy-first-bos-source-is-L1-not-latest-L2")["candle"])],
        timeframe="H4",
        structure_state=_buy_state(),
        break_buffer=FIXTURE["break_buffer"],
        as_of="2026-01-08T12:00:00Z",
    )
    assert result["event"]["source_swing_id"] == "L1"
    return swings, result


def test_fixture_is_versioned_and_contains_independent_expected_cases():
    assert FIXTURE["fixture_id"] == "smc-structure-task36-v1"
    assert len(FIXTURE["cases"]) == 10
    assert all("expected" in case for case in FIXTURE["cases"])


def test_bootstrap_expected_buy_and_insufficient_boundary():
    insufficient = _case("bootstrap-insufficient-before-low-confirmation")["expected"]
    result = initialize_structure_state(
        _swings(FIXTURE["base_swings"]),
        as_of=_case("bootstrap-insufficient-before-low-confirmation")["as_of"],
    )
    assert {key: result[key] for key in insufficient} == insufficient

    expected = _case("bootstrap-buy")["expected"]
    result = _buy_state()
    assert {key: result[key] for key in expected} == expected


def test_bootstrap_sell_expected_is_mirror():
    expected = _case("bootstrap-sell")["expected"]
    result = _sell_state()
    assert {key: result[key] for key in expected} == expected


def test_first_bos_expected_source_and_protected_are_not_latest_swing():
    for case_id, state, swings in (
        ("buy-first-bos-source-is-L1-not-latest-L2", _buy_state(), _swings(FIXTURE["base_swings"])),
        ("sell-first-bos-source-is-H1", _sell_state(), _sell_swings()),
    ):
        case = _case(case_id)
        result = detect_structure_bos(
            swings,
            [_candle(case["candle"])],
            timeframe="H4",
            structure_state=state,
            break_buffer=FIXTURE["break_buffer"],
            as_of=case["as_of"],
        )
        expected = case["expected"]
        assert result["bos"] is expected["bos"]
        assert {key: result["event"][key] for key in expected if key not in {"bos", "protected_swing_id"}} == {
            key: value for key, value in expected.items() if key not in {"bos", "protected_swing_id"}
        }
        assert result["structure_state"]["protected_swing_id"] == expected["protected_swing_id"]


def test_equal_boundary_and_wick_only_expected_for_both_sides():
    for case_id, state, swings in (
        ("buy-break-equal-boundary-is-wick-only", _buy_state(), _swings(FIXTURE["base_swings"])),
        ("sell-break-equal-boundary-is-wick-only", _sell_state(), _sell_swings()),
    ):
        case = _case(case_id)
        result = detect_structure_bos(
            swings,
            [_candle(case["candle"])],
            timeframe="H4",
            structure_state=state,
            break_buffer=FIXTURE["break_buffer"],
            as_of=case["as_of"],
        )
        assert result["bos"] is case["expected"]["bos"]
        assert case["expected"]["reason"] in result["reason_codes"]
        assert result["structure_state"].get("protected_swing_id") is case["expected"]["protected_swing_id"]


def test_buy_reclaim_expected_invalidates_at_inclusive_boundary():
    swings, bos = _buy_bos_state()
    case = _case("buy-choch-reclaim-inclusive")
    candidate = detect_choch_candidate(
        [_candle(case["candidate_candle"])],
        timeframe="H4",
        structure_state=bos["structure_state"],
        break_buffer=FIXTURE["break_buffer"],
    )
    expected = case["expected"]
    assert candidate["candidate"]["direction"] == expected["candidate_direction"]
    assert candidate["candidate"]["protected_swing_id"] == expected["candidate_protected_swing_id"]
    invalidated = invalidate_choch_candidate_on_reclaim(
        [_candle(case["reclaim_candle"])],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=FIXTURE["break_buffer"],
    )
    assert invalidated["invalidated"] is expected["invalidated"]
    assert invalidated["event"]["invalidated_at"] == expected["invalidated_at"]
    assert invalidated["structure_state"]["state"] == expected["state_after"]


def test_sell_confirmation_expected_is_mirror_and_uses_new_source():
    case = _case("sell-choch-confirmed-mirror")
    swings = _sell_swings()
    for kind in ("highs", "lows"):
        swings[kind].extend(_swings(case["extra_swings"])[kind])
    bos = detect_structure_bos(
        swings,
        [_candle({"time": "2026-01-08T08:00:00Z", "open": 100, "high": 101, "low": 87, "close": 88.99})],
        timeframe="H4",
        structure_state=_sell_state(),
        break_buffer=FIXTURE["break_buffer"],
        as_of="2026-01-08T12:00:00Z",
    )
    candidate = detect_choch_candidate(
        [_candle(case["candidate_candle"])],
        timeframe="H4",
        structure_state=bos["structure_state"],
        break_buffer=FIXTURE["break_buffer"],
    )
    result = confirm_choch_candidate(
        swings,
        [_candle(case["confirmation_candle"])],
        timeframe="H4",
        structure_state=candidate["structure_state"],
        break_buffer=FIXTURE["break_buffer"],
        as_of="2026-01-13T12:00:00Z",
    )
    expected = case["expected"]
    assert result["choch_confirmed"] is expected["choch_confirmed"]
    assert result["reversal_bos"]["direction"] == expected["reversal_bos_direction"]
    assert result["reversal_bos"]["broken_level_id"] == expected["reversal_broken_level_id"]
    assert result["reversal_bos"]["source_swing_id"] == expected["reversal_source_swing_id"]
    assert result["structure_state"]["state"] == expected["state_after"]
    assert result["structure_state"]["protected_swing_id"] == expected["protected_after"]
    assert result["candidate"]["confirmed_at"] == expected["confirmed_at"]


def test_buy_candidate_expiry_expected_keeps_protected_history_and_blocks_trigger():
    swings, bos = _buy_bos_state()
    case = _case("buy-choch-expiry-preserves-protected-history")
    candidate = detect_choch_candidate(
        [_candle(case["candidate_candle"])],
        timeframe="H4",
        structure_state=bos["structure_state"],
        break_buffer=FIXTURE["break_buffer"],
    )
    expired = expire_structure_events(
        candidate["structure_state"],
        as_of=case["expiry_as_of"],
    )
    expected = case["expected"]
    state = expired["structure_state"]
    assert expired["expired"] is expected["expired"]
    assert state["candidate_status"] == expected["candidate_status"]
    assert state["protected_swing_id"] == expected["protected_swing_id"]
    assert state["candidate_confirmed_at"] is expected["confirmed_at"]
    assert state["candidate_event"]["invalidated_at"] is expected["invalidated_at"]
    late = confirm_choch_candidate(
        swings,
        [_candle({"time": "2026-01-18T08:00:00Z", "open": 100, "high": 101, "low": 94, "close": 95})],
        timeframe="H4",
        structure_state=state,
        break_buffer=FIXTURE["break_buffer"],
    )
    assert late["choch_confirmed"] is False
    assert "SMC_CHOCH_CANDIDATE_EXPIRED" in late["reason_codes"]
