"""Task 47 tests for FVG candle continuity and session gaps."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle, candle_close_at
from core.smc_context import (
    classify_fvg_session_continuity,
    confirm_fvg_candidate,
    detect_fvg_candidates,
    fvg_session_continuity,
)


def _candles(times, rows=None):
    rows = rows or [(100, 101, 99, 100)] * len(times)
    return [
        Candle(
            time=time,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for time, (open_, high, low, close) in zip(times, rows)
    ]


def test_contiguous_candles_are_continuous():
    start = datetime(2026, 9, 9, 12, tzinfo=timezone.utc)
    candles = _candles([start + timedelta(hours=index) for index in range(3)])

    result = classify_fvg_session_continuity(
        candles,
        timeframe="H1",
        symbol="EUR/USD",
    )
    assert result == {"status": "continuous", "reason_codes": []}
    assert fvg_session_continuity(
        candles,
        timeframe="H1",
        symbol="EUR/USD",
    ) == result


def test_weekend_gap_with_session_only_jump_is_not_fvg_displacement():
    # Tech Lead correction: the old reopen-at-first.high fixture has valid
    # displacement and is now a positive in smc_r56_01_session_acceptance.json.
    # Here the third reopen creates the gap that the middle never reaches.
    times = [
        datetime(2026, 9, 11, 20, tzinfo=timezone.utc),
        datetime(2026, 9, 11, 21, tzinfo=timezone.utc),
        datetime(2026, 9, 13, 21, tzinfo=timezone.utc),
    ]
    rows = [
        (100, 102, 99, 100),
        (100, 101, 99, 101),
        (105, 106, 104, 105.5),
    ]
    for mirror in (False, True):
        mirrored_rows = rows
        if mirror:
            mirrored_rows = [(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in rows]
        candles = _candles(times, mirrored_rows)
        continuity = classify_fvg_session_continuity(
            candles,
            timeframe="H1",
            symbol="EUR/USD",
        )
        assert continuity["status"] == "session_gap"
        assert continuity["reason_codes"] == ["FVG_SESSION_GAP"]
        assert detect_fvg_candidates(
            candles,
            symbol="EUR/USD",
            timeframe="H1",
            tick_size=0.1,
            atr_before_event=5.0,
        ) == []


def test_session_gap_with_continuous_open_and_valid_displacement_is_candidate():
    candles = _candles([
        datetime(2026, 9, 11, 21, tzinfo=timezone.utc),
        datetime(2026, 9, 13, 21, tzinfo=timezone.utc),
        datetime(2026, 9, 13, 22, tzinfo=timezone.utc),
    ], [
        (101, 102, 99, 100),
        (100, 106, 99.8, 105.5),
        (105.5, 107, 103, 106),
    ])
    candidates = detect_fvg_candidates(
        candles, symbol="EUR/USD", timeframe="H1",
        tick_size=0.1, atr_before_event=5.0,
    )
    assert len(candidates) == 1
    assert candidates[0]["session_displacement_eligible"] is True


def test_session_gap_allows_in_session_third_open_tick_mismatch_buy_and_sell():
    times = [
        datetime(2026, 9, 11, 21, tzinfo=timezone.utc),
        datetime(2026, 9, 13, 21, tzinfo=timezone.utc),
        datetime(2026, 9, 13, 22, tzinfo=timezone.utc),
    ]
    rows = [(101, 102, 99, 100), (100, 106, 99.8, 105.5), (105.4, 107, 103, 106)]
    for mirror, direction in ((False, "buy"), (True, "sell")):
        mirrored_rows = rows
        if mirror:
            mirrored_rows = [(200 - o, 200 - l, 200 - h, 200 - c) for o, h, l, c in rows]
        candidates = detect_fvg_candidates(
            _candles(times, mirrored_rows), symbol="EUR/USD", timeframe="H1",
            tick_size=0.1, atr_before_event=5.0,
        )
        assert len(candidates) == 1
        assert candidates[0]["direction"] == direction
        assert candidates[0]["session_displacement_eligible"] is True
        confirmed = confirm_fvg_candidate(
            candidates[0], _candles(times, mirrored_rows), timeframe="H1",
            as_of=candle_close_at(times[2], "H1"),
        )
        assert confirmed["lifecycle_status"] == "confirmed"


def test_open_session_gap_is_unexpected_and_unknown_metadata_is_explicit():
    candles = _candles([
        datetime(2026, 9, 9, 12, tzinfo=timezone.utc),
        datetime(2026, 9, 9, 14, tzinfo=timezone.utc),
        datetime(2026, 9, 9, 15, tzinfo=timezone.utc),
    ])
    unexpected = classify_fvg_session_continuity(
        candles,
        timeframe="H1",
        symbol="EUR/USD",
    )
    unknown = classify_fvg_session_continuity(
        candles,
        timeframe="H1",
        symbol="",
    )
    assert unexpected["status"] == "unexpected_gap"
    assert unexpected["reason_codes"] == ["FVG_CANDLE_GAP_UNEXPECTED"]
    assert unknown["status"] == "unknown"
    assert unknown["reason_codes"] == ["SESSION_GAP_UNKNOWN"]
