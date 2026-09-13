"""Task 54 detector matrix: accepted/rejected cases in both directions."""

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    confirm_order_block_candidate,
    confirm_supply_demand_candidate,
    detect_fvg_candidates,
    detect_order_block_candidates,
    detect_supply_demand_candidates,
    measure_fvg_gap,
    measure_fvg_middle_candle,
)


def _candles(rows, *, start=None, step=timedelta(hours=1)):
    start = start or datetime(2026, 9, 9, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + step * index,
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def test_ob_detector_accepts_buy_and_sell_bases_but_no_break_stays_pending():
    buy = detect_order_block_candidates(
        _candles([(100, 101, 99, 100), (101, 102, 99, 100), (100, 104, 100, 103)]),
        symbol="EUR/USD", timeframe="H1",
    )
    sell = detect_order_block_candidates(
        _candles([(100, 101, 99, 100), (99, 102, 98, 101), (100, 100, 96, 97)]),
        symbol="EUR/USD", timeframe="H1",
    )
    assert any(item["direction"] == "buy" for item in buy)
    assert any(item["direction"] == "sell" for item in sell)
    pending = confirm_order_block_candidate(buy[0], [])
    assert pending["lifecycle_status"] == "candidate"
    assert "OB_STRUCTURE_BREAK_MISSING" in pending["reason_codes"]


def test_fvg_detector_accepts_both_directions_and_rejects_small_or_weak_gaps():
    bullish = _candles([(100, 100, 99, 99.5), (100, 103, 99.5, 102.5), (102, 104, 101, 103)])
    bearish = _candles([(100, 102, 99, 101), (100, 101, 97, 98), (97, 98, 96, 97.5)])
    assert detect_fvg_candidates(
        bullish, symbol="EUR/USD", timeframe="H1", tick_size=0.1, atr_before_event=5.0,
    )[0]["direction"] == "buy"
    assert detect_fvg_candidates(
        bearish, symbol="EUR/USD", timeframe="H1", tick_size=0.1, atr_before_event=5.0,
    )[0]["direction"] == "sell"
    tiny = measure_fvg_gap(
        bullish[0], bullish[1], _candles([(100.2, 101, 100.05, 100.5)])[0],
        tick_size=0.1, atr_before_event=5.0,
    )
    weak = measure_fvg_middle_candle(
        _candles([(100, 104, 99, 100.5)])[0], direction="buy",
    )
    assert tiny["accepted"] is False
    assert "FVG_GAP_TOO_SMALL" in tiny["reason_codes"]
    assert weak["accepted"] is False
    assert "FVG_MIDDLE_CANDLE_WEAK" in weak["reason_codes"]


def test_fvg_session_only_gap_is_rejected_and_sd_wick_is_not_confirmed_in_both_sides():
    # Closure is after the middle; middle quality passes but never reaches
    # [102,104]. This replaces the old mislabeled reopen-at-edge negative.
    session_gap = _candles([
        (100, 102, 99, 100),
        (100, 101, 99, 101),
        (105, 106, 104, 105.5),
    ], start=datetime(2026, 9, 11, 20, tzinfo=timezone.utc))
    session_gap[2] = Candle(
        time=datetime(2026, 9, 13, 21, tzinfo=timezone.utc),
        open=105, high=106, low=104, close=105.5, volume=100,
    )
    assert detect_fvg_candidates(
        session_gap, symbol="EUR/USD", timeframe="H1", tick_size=0.1, atr_before_event=5.0,
    ) == []

    for direction, rows in (
        ("buy", [(100, 100.4, 99.8, 100.1), (100.1, 100.5, 99.9, 100.2), (100.2, 100.3, 99.9, 100.0), (100, 102, 100, 100.1)]),
        ("sell", [(100, 100.4, 99.8, 100.1), (100.1, 100.5, 99.9, 100.2), (100.2, 100.3, 99.9, 100.0), (100, 100, 98, 99.9)]),
    ):
        candles = _candles(rows)
        candidates = detect_supply_demand_candidates(
            candles, symbol="EUR/USD", timeframe="H1", average_range_before_departure={3: 0.6},
        )
        candidate = next(item for item in candidates if item["direction"] == direction)
        result = confirm_supply_demand_candidate(
            candidate, candles, timeframe="H1", atr_before_event=2.0,
        )
        assert result["lifecycle_status"] == "candidate"
        assert "SD_DEPARTURE_WICK_ONLY" in result["reason_codes"]
