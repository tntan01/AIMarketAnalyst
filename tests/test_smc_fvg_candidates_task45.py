"""Task 45 tests for three-candle FVG candidate geometry."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import detect_fvg_candidates, measure_fvg_gap


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


def test_bullish_and_bearish_gaps_use_symmetric_bounds_and_threshold():
    bullish = measure_fvg_gap(
        _candles([(100, 100, 99, 99.5)])[0],
        _candles([(100, 102, 99, 101)])[0],
        _candles([(102, 103, 101, 102.5)])[0],
        tick_size=0.1,
        atr_before_event=5.0,
    )
    bearish = measure_fvg_gap(
        _candles([(100, 102, 99, 101)])[0],
        _candles([(100, 101, 97, 98)])[0],
        _candles([(97, 98, 96, 97.5)])[0],
        tick_size=0.1,
        atr_before_event=5.0,
    )

    assert bullish["direction"] == "buy"
    assert bullish["gap_low"] == 100
    assert bullish["gap_high"] == 101
    assert bullish["minimum_gap"] == 0.5
    assert bullish["accepted"] is True
    assert bearish["direction"] == "sell"
    assert bearish["gap_low"] == 98
    assert bearish["gap_high"] == 99
    assert bearish["accepted"] is True


def test_tiny_gap_is_rejected_without_middle_candle_promotion():
    candles = _candles([
        (100, 100, 99, 99.5),
        (100, 100.3, 99.5, 100.1),
        (100.2, 101, 100.05, 100.5),
    ])
    result = detect_fvg_candidates(
        candles,
        symbol="EUR/USD",
        timeframe="H1",
        tick_size=0.1,
        atr_before_event=5.0,
    )
    assert result == []
    measurement = measure_fvg_gap(
        candles[0], candles[1], candles[2],
        tick_size=0.1, atr_before_event=5.0,
    )
    assert measurement["accepted"] is False
    assert "FVG_GAP_TOO_SMALL" in measurement["reason_codes"]


def test_accepted_fvg_is_candidate_only_and_preserves_formation_lineage():
    candles = _candles([
        (100, 100, 99, 99.5),
        (100, 103, 99.5, 102.5),
        (102, 104, 101, 103),
    ])
    result = detect_fvg_candidates(
        candles,
        symbol="EUR/USD",
        timeframe="H1",
        tick_size=0.1,
        atr_before_event=5.0,
    )
    candidate = result[0]
    assert candidate["type"] == "bullish_fvg"
    assert candidate["family"] == "fvg"
    assert candidate["formation_start_index"] == 0
    assert candidate["formation_end_index"] == 2
    assert candidate["departure_end_index"] == 2
    assert candidate["lifecycle_status"] == "candidate"
    assert candidate["available_at"] is None
    assert candidate["entry_eligible"] is False
