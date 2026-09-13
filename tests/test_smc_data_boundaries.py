"""Fixture-driven boundary matrix for the SMC data contract (task 24)."""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from core.market_models import Candle, closed_candles_at_cutoff, validate_smc_candles
from core.smc_context import atr_reference_before_event
from core.smc_history import assess_smc_history


FIXTURE = Path(__file__).parent / "fixtures" / "smc_data_boundaries.json"


def _load_cases() -> dict[str, list[dict]]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["version"] == "smc-data-boundaries-v1"
    return payload["cases"]


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _candle(open_time: datetime, index: int = 0) -> Candle:
    return Candle(
        time=open_time,
        open=100.0 + index,
        high=101.0 + index,
        low=99.0 + index,
        close=100.5 + index,
    )


def _continuous(start: datetime, count: int, interval: timedelta) -> list[Candle]:
    return [_candle(start + index * interval, index) for index in range(count)]


def test_cutoff_fixture_has_pass_and_fail_boundary_cases():
    cases = _load_cases()["cutoff"]

    observed = {}
    for case in cases:
        candle = _candle(_time(case["open_time"]))
        kept = closed_candles_at_cutoff(
            (candle,),
            case["timeframe"],
            _time(case["cutoff"]),
        )
        observed[case["id"]] = "included" if kept else "excluded"

    assert observed == {case["id"]: case["expected_status"] for case in cases}


def test_duplicate_fixture_has_valid_and_rejected_sequences():
    cases = _load_cases()["duplicate"]

    observed = {}
    for case in cases:
        candles = tuple(_candle(_time(value), index) for index, value in enumerate(case["times"]))
        issues = validate_smc_candles(candles, "M15")
        observed[case["id"]] = "valid" if not issues else issues[0].code

    assert observed == {case["id"]: case["expected_status"] for case in cases}


def test_session_fixture_distinguishes_closure_from_in_session_gap():
    cases = _load_cases()["session_gap"]
    weekend_case, gap_case = cases

    # Fifteen weekday D1 candles span a weekend closure without synthesizing
    # Saturday/Sunday records.
    start = _time(weekend_case["start"])
    d1_times = []
    cursor = start
    while len(d1_times) < 15:
        if cursor.weekday() < 5:
            d1_times.append(cursor)
        cursor += timedelta(days=1)
    weekend_result = assess_smc_history(
        tuple(_candle(value, index) for index, value in enumerate(d1_times)),
        weekend_case["timeframe"],
        symbol=weekend_case["symbol"],
        origin_time=d1_times[0],
        minimum_candles=15,
    )

    # Remove one expected H1 slot while keeping 15 records, so warm-up does
    # not mask the coverage classification.
    gap_start = _time(gap_case["start"])
    h1 = _continuous(gap_start, 16, timedelta(hours=1))
    h1.pop(7)
    gap_result = assess_smc_history(
        tuple(h1),
        gap_case["timeframe"],
        symbol=gap_case["symbol"],
        origin_time=h1[0].time,
        minimum_candles=15,
    )

    assert weekend_result.status == weekend_case["expected_status"]
    assert weekend_result.session_coverage_status == "known"
    assert weekend_result.missing_slots == ()
    assert weekend_result.closed_session_slots > 0
    assert gap_result.status == gap_case["expected_status"]
    assert "SMC_COVERAGE_GAP" in gap_result.reason_codes
    assert len(gap_result.missing_slots) == 1


def test_warmup_fixture_has_unready_and_ready_statuses():
    cases = _load_cases()["warmup"]
    observed = {}
    start = datetime(2026, 1, 5, tzinfo=timezone.utc)
    for case in cases:
        result = assess_smc_history(
            tuple(_continuous(start, case["count"], timedelta(hours=1))),
            "H1",
            symbol="EURUSD",
            minimum_candles=1,
        )
        observed[case["id"]] = (
            "ready"
            if result.warmup_ready
            else "SMC_ATR_REFERENCE_UNAVAILABLE"
        )

    assert observed == {case["id"]: case["expected_status"] for case in cases}


def test_atr_reference_fixture_has_unavailable_and_available_events():
    cases = _load_cases()["atr_reference"]
    history = tuple(
        _continuous(
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            22,
            timedelta(hours=4),
        )
    )
    observed = {}
    for case in cases:
        reference = atr_reference_before_event(
            history,
            timeframe="H4",
            event_index=case["event_index"],
        )
        observed[case["id"]] = "available" if reference is not None else "SMC_ATR_REFERENCE_UNAVAILABLE"

    assert observed == {case["id"]: case["expected_status"] for case in cases}
