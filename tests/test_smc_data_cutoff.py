"""Task 18 tests for causal closed-candle filtering."""

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import (
    Candle,
    candle_close_at,
    closed_candles_at_cutoff,
)


UTC = timezone.utc
BASE = datetime(2026, 9, 10, tzinfo=UTC)


def _candle(open_time: datetime, close: float = 1.0) -> Candle:
    return Candle(
        time=open_time,
        open=close,
        high=close + 0.1,
        low=close - 0.1,
        close=close,
    )


@pytest.mark.parametrize(
    ("timeframe", "interval"),
    [
        ("D1", timedelta(days=1)),
        ("H4", timedelta(hours=4)),
        ("H1", timedelta(hours=1)),
        ("M15", timedelta(minutes=15)),
    ],
)
def test_close_boundary_uses_real_timeframe_interval(timeframe, interval):
    assert candle_close_at(BASE, timeframe) == BASE + interval


def test_cutoff_includes_exact_close_and_excludes_forming_last_bar():
    candles = [
        _candle(BASE - timedelta(hours=8), 1.0),
        _candle(BASE - timedelta(hours=4), 2.0),
        _candle(BASE, 3.0),
    ]

    eligible = closed_candles_at_cutoff(candles, "H4", BASE)

    assert [item.close for item in eligible] == [1.0, 2.0]
    assert eligible[-1] is candles[1]


def test_cutoff_does_not_drop_last_bar_by_position_when_it_is_closed():
    candles = [
        _candle(BASE - timedelta(hours=8), 1.0),
        _candle(BASE - timedelta(hours=4), 2.0),
    ]

    eligible = closed_candles_at_cutoff(
        candles,
        "H4",
        BASE,
    )

    assert [item.close for item in eligible] == [1.0, 2.0]


def test_future_and_forming_candles_are_filtered_without_ohlc_repair():
    malformed_future = Candle(
        time=BASE,
        open=10.0,
        high=1.0,
        low=20.0,
        close=10.0,
    )
    candles = [_candle(BASE - timedelta(hours=4), 2.0), malformed_future]

    eligible = closed_candles_at_cutoff(candles, "H4", BASE)

    assert [item.close for item in eligible] == [2.0]


def test_cutoff_and_open_time_must_be_timezone_aware():
    with pytest.raises(ValueError, match="timezone-aware"):
        closed_candles_at_cutoff(
            [_candle(BASE - timedelta(hours=4))],
            "H4",
            datetime(2026, 9, 10),
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        closed_candles_at_cutoff(
            [_candle(datetime(2026, 9, 10))],
            "H4",
            BASE,
        )


def test_unsupported_timeframe_is_rejected():
    with pytest.raises(ValueError, match="Unsupported SMC timeframe"):
        closed_candles_at_cutoff([_candle(BASE)], "M5", BASE)
