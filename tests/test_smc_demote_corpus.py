"""Synthetic tests for the frozen SMC demote corpus helpers (task SD-C1).

No MT5 terminal is required: ``windows_at`` is a pure function of the frozen
candle lists, so it is exercised with hand-built candles.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from scripts.smc_demote_corpus import TAIL_BARS, windows_at


def _h1_candles(start: datetime, count: int) -> list[Candle]:
    candles: list[Candle] = []
    for index in range(count):
        open_time = start + timedelta(hours=index)
        price = 1.0 + index * 0.001
        candles.append(
            Candle(
                time=open_time,
                open=price,
                high=price + 0.0005,
                low=price - 0.0005,
                close=price + 0.0002,
                volume=1.0,
            )
        )
    return candles


def _data(candles_by_timeframe: dict[str, list[Candle]]) -> dict:
    return {"candles": candles_by_timeframe}


def _fill_timeframes(h1: list[Candle]) -> dict[str, list[Candle]]:
    # Prefix length is only enforced for the timeframes under test here; reuse
    # the H1 series for every timeframe so ``windows_at`` has valid input.
    return {"D1": h1, "H4": h1, "H1": h1, "M15": h1}


def test_windows_at_prefix_never_closes_after_cutoff_and_cutoff_bar_is_tail() -> None:
    start = datetime(2026, 1, 5, 0, tzinfo=timezone.utc)
    h1 = _h1_candles(start, 200)
    data = _data(_fill_timeframes(h1))
    cutoff = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)

    prefix, tail = windows_at(data, cutoff)

    for timeframe, candles in prefix.items():
        interval = timedelta(hours=1)
        for candle in candles:
            assert candle.time + interval <= cutoff, timeframe

    # The H1 bar opening exactly at the cutoff has not closed yet: it belongs to
    # the future tail, never to the prefix.
    assert all(candle.time < cutoff for candle in prefix["H1"])
    assert tail["H1"][0].time == cutoff
    assert all(candle.time >= cutoff for candle in tail["H1"])
    assert len(tail["H1"]) == TAIL_BARS["H1"]


def test_future_candles_do_not_change_prefix_at_same_cutoff() -> None:
    start = datetime(2026, 1, 5, 0, tzinfo=timezone.utc)
    base_h1 = _h1_candles(start, 200)
    cutoff = datetime(2026, 1, 5, 12, 0, tzinfo=timezone.utc)

    base_prefix, _ = windows_at(_data(_fill_timeframes(base_h1)), cutoff)

    extended_h1 = base_h1 + _h1_candles(start + timedelta(hours=200), 100)
    extended_prefix, _ = windows_at(_data(_fill_timeframes(extended_h1)), cutoff)

    for timeframe in base_prefix:
        assert base_prefix[timeframe] == extended_prefix[timeframe]


def test_windows_at_naive_cutoff_raises_value_error() -> None:
    h1 = _h1_candles(datetime(2026, 1, 5, 0, tzinfo=timezone.utc), 10)
    data = _data(_fill_timeframes(h1))
    with pytest.raises(ValueError):
        windows_at(data, datetime(2026, 1, 5, 12, 0))
