"""Task 46 tests for FVG middle-candle quality."""

from datetime import datetime, timezone

from core.market_models import Candle
from core.smc_context import measure_fvg_middle_candle


def _candle(open_, high, low, close):
    return Candle(
        time=datetime(2026, 9, 10, tzinfo=timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def test_middle_candle_buy_requires_body_and_close_location():
    result = measure_fvg_middle_candle(
        _candle(100, 103, 99, 102.5),
        direction="buy",
    )
    assert result["middle_direction"] == "buy"
    assert result["body_range"] == 0.625
    assert result["close_location"] == 0.875
    assert result["directional_close_location"] == 0.875
    assert result["accepted"] is True


def test_middle_candle_sell_is_mirrored():
    result = measure_fvg_middle_candle(
        _candle(100, 101, 97, 97.5),
        direction="sell",
    )
    assert result["middle_direction"] == "sell"
    assert result["body_range"] == 0.625
    assert result["close_location"] == 0.125
    assert result["directional_close_location"] == 0.875
    assert result["accepted"] is True


def test_weak_body_or_bad_close_does_not_qualify_middle_candle():
    result = measure_fvg_middle_candle(
        _candle(100, 104, 99, 100.5),
        direction="buy",
    )
    assert result["accepted"] is False
    assert "FVG_MIDDLE_CANDLE_WEAK" in result["reason_codes"]

    wrong_direction = measure_fvg_middle_candle(
        _candle(100, 103, 99, 99.5),
        direction="buy",
    )
    assert wrong_direction["accepted"] is False
    assert "FVG_MIDDLE_DIRECTION_MISMATCH" in wrong_direction["reason_codes"]


def test_zero_range_middle_candle_fails_closed():
    result = measure_fvg_middle_candle(
        _candle(100, 100, 100, 100),
        direction="sell",
    )
    assert result["accepted"] is False
    assert result["body_range"] is None
    assert result["close_location"] is None
    assert result["reason_codes"] == ["FVG_MIDDLE_CANDLE_WEAK"]
