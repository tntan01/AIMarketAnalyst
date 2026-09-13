"""Task 44 tests for causal OB confirmation by related structure break."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    confirm_order_block_candidate,
    detect_order_block_candidates,
)


def _candles(rows):
    start = datetime(2026, 9, 10, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def _candidate():
    candidate = detect_order_block_candidates(
        _candles([
            (100, 101, 99, 100),
            (101, 102, 99, 100),
            (100, 104, 100, 103),
        ]),
        symbol="EUR/USD",
        timeframe="H4",
    )[0]
    # Task 56 makes causal ATR availability a required OB quality gate.
    candidate["departure_measurement"] = {
        "status": "ok",
        "body": 3.0,
        "range": 4.0,
        "body_range": 0.75,
        "body_atr": 1.5,
        "close_location": 0.75,
        "directional_close_location": 0.75,
        "atr_before_event": 2.0,
        "reason_codes": [],
    }
    return candidate


def test_related_same_direction_bos_promotes_candidate_at_break_close():
    candidate = _candidate()
    confirmed = confirm_order_block_candidate(
        candidate,
        [{
            "event_id": "bos-h4-1",
            "event_type": "BOS",
            "direction": "bullish",
            "occurred_index": 4,
            "broken_level_id": "swing-high-1",
            "occurred_at": "2026-09-10T14:00:00+00:00",
            "confirmed_at": "2026-09-10T14:00:00+00:00",
            "confirmed": True,
        }],
    )

    assert confirmed["lifecycle_status"] == "confirmed"
    assert confirmed["candidate"] is False
    assert confirmed["entry_eligible"] is False
    assert confirmed["confirmation_event_id"] == "bos-h4-1"
    assert confirmed["available_at"] == "2026-09-10T14:00:00+00:00"
    assert "ZONE_CONFIRMED" in confirmed["reason_codes"]


def test_missing_or_wrong_direction_break_keeps_candidate_waiting():
    candidate = _candidate()
    waiting = confirm_order_block_candidate(
        candidate,
        [{
            "event_id": "bos-h4-wrong-side",
            "event_type": "BOS",
            "direction": "bearish",
            "occurred_index": 4,
            "occurred_at": "2026-09-10T20:00:00+00:00",
            "confirmed_at": "2026-09-10T20:00:00+00:00",
            "confirmed": True,
        }],
    )

    assert waiting["lifecycle_status"] == "candidate"
    assert waiting["entry_eligible"] is False
    assert waiting["confirmation_event_id"] is None
    assert "OB_STRUCTURE_BREAK_MISSING" in waiting["reason_codes"]


def test_break_after_three_bars_or_wick_only_does_not_confirm():
    candidate = _candidate()
    events = [
        {
            "event_id": "bos-too-late",
            "event_type": "BOS",
            "direction": "bullish",
            "occurred_index": 6,
            "broken_level_id": "swing-high-late",
            "occurred_at": "2026-09-10T22:00:00+00:00",
            "confirmed_at": "2026-09-10T18:00:00+00:00",
            "confirmed": True,
        },
        {
            "event_id": "bos-wick",
            "event_type": "BOS",
            "direction": "bullish",
            "occurred_index": 4,
            "broken_level_id": "swing-high-wick",
            "occurred_at": "2026-09-10T20:00:00+00:00",
            "confirmed_at": "2026-09-10T20:00:00+00:00",
            "confirmed": True,
            "wick_only": True,
        },
    ]

    result = confirm_order_block_candidate(candidate, events)
    assert result["lifecycle_status"] == "candidate"
    assert result["confirmation_event_id"] is None
    assert result["available_at"] is None
