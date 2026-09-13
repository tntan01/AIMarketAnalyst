from datetime import datetime, timedelta, timezone

import pytest

from core.indicators import atr
from core.market_models import Candle, candle_close_at
from core.smc_context import (
    SmcAtrReference,
    atr_reference_before_event,
    atr_value_before_event,
)


def candles(count: int = 22) -> tuple[Candle, ...]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return tuple(
        Candle(
            time=start + timedelta(hours=4 * index),
            open=100.0 + index * 0.2,
            high=101.0 + index * 0.2,
            low=99.0 + index * 0.2,
            close=100.5 + index * 0.2,
        )
        for index in range(count)
    )


def test_formation_atr_uses_only_prefix_before_event_and_freezes_against_future_data():
    base = list(candles())
    event_index = 15
    expected = atr(
        [item.high for item in base[:event_index]],
        [item.low for item in base[:event_index]],
        [item.close for item in base[:event_index]],
        14,
    )[-1]
    base[event_index] = Candle(
        time=base[event_index].time,
        open=100,
        high=250,
        low=1,
        close=200,
    )
    later = base + [
        Candle(
            time=base[-1].time + timedelta(hours=4),
            open=100,
            high=500,
            low=1,
            close=400,
        )
    ]

    reference = atr_reference_before_event(
        later,
        timeframe="H4",
        event_index=event_index,
        source_event_id="BOS-H4-1",
    )

    assert isinstance(reference, SmcAtrReference)
    assert reference.value == pytest.approx(expected)
    assert reference.reference_time == candle_close_at(base[event_index - 1].time, "H4").isoformat()
    assert reference.event_time == candle_close_at(base[event_index].time, "H4").isoformat()
    assert reference.source_event_id == "BOS-H4-1"
    assert atr_value_before_event(later, timeframe="H4", event_index=event_index) == pytest.approx(expected)


def test_event_time_selects_the_same_causal_event_candle():
    history = candles()
    event_time = candle_close_at(history[15].time, "H4")

    by_index = atr_reference_before_event(history, timeframe="H4", event_index=15)
    by_time = atr_reference_before_event(history, timeframe="H4", event_time=event_time)

    assert by_time == by_index


def test_event_candle_is_excluded_at_warmup_boundary():
    history = candles(16)

    assert atr_reference_before_event(history, timeframe="H4", event_index=14) is None
    assert atr_reference_before_event(history, timeframe="H4", event_index=15) is not None


def test_timeframe_controls_reference_and_event_close_boundaries():
    history = candles()
    reference = atr_reference_before_event(history, timeframe="H1", event_index=15)

    assert reference is not None
    assert reference.timeframe == "H1"
    assert reference.reference_time == candle_close_at(history[14].time, "H1").isoformat()
    assert reference.event_time == candle_close_at(history[15].time, "H1").isoformat()


def test_invalid_prefix_is_rejected_without_using_event_or_future_repair():
    history = list(candles())
    history[10] = Candle(
        time=history[10].time,
        open=100,
        high=98,
        low=99,
        close=100.5,
    )

    with pytest.raises(ValueError, match="Invalid SMC candle data") as raised:
        atr_reference_before_event(history, timeframe="H4", event_index=15)

    assert "SMC_OHLC_INVALID" in str(raised.value)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({}, "event_index or event_time is required"),
        ({"event_index": 99}, "outside candles"),
        ({"event_time": "2026-01-01T00:00:00Z"}, "match exactly one"),
        ({"event_index": 15, "event_time": "2026-01-03T00:00:00Z"}, "different candles"),
    ],
)
def test_event_selector_is_strict(kwargs, message):
    with pytest.raises(ValueError, match=message):
        atr_reference_before_event(candles(), timeframe="H4", **kwargs)


def test_invalid_timeframe_period_and_naive_event_time_are_rejected():
    with pytest.raises(ValueError, match="Unsupported SMC timeframe"):
        atr_reference_before_event(candles(), timeframe="M5", event_index=15)
    with pytest.raises(ValueError, match="period must be positive"):
        atr_reference_before_event(candles(), timeframe="H4", event_index=15, period=0)
    with pytest.raises(ValueError, match="timezone-aware UTC"):
        atr_reference_before_event(
            candles(),
            timeframe="H4",
            event_time="2026-01-03T12:00:00",
        )
