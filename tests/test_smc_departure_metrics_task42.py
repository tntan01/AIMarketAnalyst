"""Task 42 tests for causal, symmetric departure measurements."""

from datetime import datetime, timezone

import pytest

from core.market_models import Candle
from core.smc_context import departure_metrics, measure_departure


def _candle(*, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        time=datetime(2026, 9, 10, 16, tzinfo=timezone.utc),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=100,
    )


def test_buy_and_sell_metrics_are_mirrored():
    buy = measure_departure(
        _candle(open_=100.0, high=104.0, low=99.0, close=103.0),
        direction="buy",
        atr_before_event=2.0,
    )
    sell = measure_departure(
        _candle(open_=100.0, high=101.0, low=96.0, close=97.0),
        direction="sell",
        atr_before_event=2.0,
    )

    assert buy["body_atr"] == sell["body_atr"] == 1.5
    assert buy["body_range"] == sell["body_range"] == 0.6
    assert buy["directional_close_location"] == sell["directional_close_location"] == 0.8
    assert buy["close_location"] == 0.8
    assert sell["close_location"] == 0.2
    assert departure_metrics(
        _candle(open_=100, high=104, low=99, close=103),
        direction="buy",
        atr_before_event=2,
    ) == buy


def test_atr_is_explicitly_causal_and_missing_is_not_substituted():
    result = measure_departure(
        _candle(open_=100, high=104, low=99, close=103),
        direction="buy",
        atr_before_event=None,
    )

    assert result["body"] == 3.0
    assert result["body_range"] == 0.6
    assert result["body_atr"] is None
    assert result["atr_before_event"] is None
    assert result["status"] == "unavailable"
    assert result["reason_codes"] == ["DEPARTURE_ATR_UNAVAILABLE"]


def test_zero_range_is_explicitly_invalid():
    result = measure_departure(
        _candle(open_=100, high=100, low=100, close=100),
        direction="sell",
        atr_before_event=2,
    )

    assert result["status"] == "invalid"
    assert result["range"] == 0
    assert result["body_range"] is None
    assert result["close_location"] is None
    assert result["reason_codes"] == ["DEPARTURE_RANGE_ZERO"]


def test_invalid_direction_or_atr_is_rejected_or_reported():
    with pytest.raises(ValueError):
        measure_departure(
            _candle(open_=100, high=104, low=99, close=103),
            direction="sideways",
            atr_before_event=2,
        )

    result = measure_departure(
        _candle(open_=100, high=104, low=99, close=103),
        direction="buy",
        atr_before_event=0,
    )
    assert result["body_atr"] is None
    assert result["reason_codes"] == ["DEPARTURE_ATR_INVALID"]
