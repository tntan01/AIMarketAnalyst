"""Task 43 tests for unconfirmed order-block candidate detection."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import detect_order_block_candidates


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


def test_opposite_base_before_bullish_departure_is_candidate_only():
    candles = _candles([
        (100, 101, 99, 100),
        (101, 102, 99, 100),  # bearish base
        (100, 104, 100, 103),  # bullish departure
        (103, 104, 102, 103),
    ])

    candidates = detect_order_block_candidates(
        candles,
        symbol="EUR/USD",
        timeframe="H4",
    )
    candidate = next(item for item in candidates if item["direction"] == "buy")

    assert candidate["family"] == "ob"
    assert candidate["type"] == "bullish_order_block"
    assert candidate["lifecycle_status"] == "candidate"
    assert candidate["candidate"] is True
    assert candidate["entry_eligible"] is False
    assert candidate["formation_start_index"] == 1
    assert candidate["formation_end_index"] == 1
    assert candidate["departure_end_index"] == 2
    assert candidate["formation_start"] == candles[1].time.isoformat()
    assert candidate["formation_end"] == candles[1].time.isoformat()
    assert candidate["departure_end"] == candles[2].time.isoformat()
    assert candidate["original_bounds"] == {"low": 99, "high": 102}
    assert candidate["available_at"] is None
    assert candidate["confirmation_event_id"] is None
    assert candidate["reason_codes"] == [
        "ZONE_CANDIDATE",
        "DEPARTURE_ATR_UNAVAILABLE",
    ]


def test_bearish_departure_is_mirrored_and_ids_are_source_stable():
    candles = _candles([
        (100, 101, 99, 100),
        (99, 102, 98, 101),  # bullish base
        (100, 100, 96, 97),  # bearish departure
    ])
    first = detect_order_block_candidates(
        candles,
        symbol="EUR/USD",
        timeframe="H4",
    )
    extended = detect_order_block_candidates(
        candles + _candles([(97, 98, 96, 97)])[0:1],
        symbol="EUR/USD",
        timeframe="H4",
    )
    candidate = next(item for item in first if item["direction"] == "sell")
    same_source = next(
        item for item in extended
        if item["zone_id"] == candidate["zone_id"]
    )

    assert candidate["type"] == "bearish_order_block"
    assert candidate["original_bounds"] == {"low": 98, "high": 102}
    assert same_source["zone_id"] == candidate["zone_id"]
    assert same_source["original_bounds"] == candidate["original_bounds"]
