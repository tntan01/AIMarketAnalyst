from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle, candle_close_at
from core.smc_context import (
    _smc_for_timeframe,
    external_swing_points,
)


def pivot_history(count: int = 11) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = []
    for index in range(count):
        candles.append(
            Candle(
                time=start + timedelta(hours=4 * index),
                open=100.0,
                high=110.0,
                low=90.0,
                close=100.0,
            )
        )
    # The center candle is the only external high and low in its width-5 window.
    candles[5] = Candle(
        time=candles[5].time,
        open=100.0,
        high=120.0,
        low=80.0,
        close=100.0,
    )
    return candles


def test_external_pivot_waits_for_five_right_candles_and_separates_times():
    history = pivot_history()

    result = external_swing_points(
        history,
        symbol="EURUSD",
        timeframe="H4",
        lookback=5,
    )

    assert [item["index"] for item in result["highs"]] == [5]
    assert [item["index"] for item in result["lows"]] == [5]
    high = result["highs"][0]
    assert high["pivot_time"] == history[5].time.isoformat()
    assert high["confirmed_at"] == candle_close_at(history[10].time, "H4").isoformat()
    assert high["pivot_time"] != high["confirmed_at"]
    assert high["confirmation_delay"] == 5
    assert high["confirmed"] is True
    assert high["usable"] is True
    assert high["provisional"] is False


def test_external_pivot_at_right_edge_is_not_emitted_early():
    history = pivot_history(10)

    result = external_swing_points(history, symbol="EURUSD", timeframe="H4")

    assert result == {"highs": [], "lows": []}


def test_external_swing_id_survives_rolling_prefix_shift():
    history = pivot_history()
    shifted = [
        Candle(
            time=history[0].time - timedelta(hours=4),
            open=100.0,
            high=105.0,
            low=95.0,
            close=100.0,
        )
    ] + history

    original = external_swing_points(history, symbol="EURUSD", timeframe="H4")
    moved = external_swing_points(shifted, symbol="EURUSD", timeframe="H4")

    assert moved["highs"][0]["index"] == original["highs"][0]["index"] + 1
    assert moved["highs"][0]["swing_id"] == original["highs"][0]["swing_id"]
    assert moved["highs"][0]["pivot_time"] == original["highs"][0]["pivot_time"]
    assert moved["highs"][0]["confirmed_at"] == original["highs"][0]["confirmed_at"]


def test_fallback_width_is_explicitly_provisional_and_not_usable():
    history = pivot_history()

    result = external_swing_points(
        history,
        symbol="EURUSD",
        timeframe="H4",
        lookback=2,
        provisional=True,
    )

    assert result["highs"]
    assert all(item["pivot_width"] == 2 for item in result["highs"])
    assert all(item["provisional"] is True for item in result["highs"])
    assert all(item["usable"] is False for item in result["highs"])
    assert all(item["pivot_time"] != item["confirmed_at"] for item in result["highs"])


def test_main_timeframe_path_keeps_legacy_swing_schema_until_gate_40():
    history = pivot_history()

    result = _smc_for_timeframe(
        history,
        symbol="EURUSD",
        timeframe="H4",
        tf_minutes=240,
    )

    assert result["swing_source"] == "standard"
    assert result["swings"]["highs"]
    assert all("time" in item for item in result["swings"]["highs"])
    assert all("pivot_time" not in item for item in result["swings"]["highs"])
    assert "structure_bos" not in result


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"lookback": 0}, "positive integer"),
        ({"timeframe": "M5"}, "Unsupported SMC timeframe"),
    ],
)
def test_external_pivot_contract_rejects_invalid_parameters(kwargs, message):
    with pytest.raises(ValueError, match=message):
        external_swing_points(pivot_history(), **kwargs)
