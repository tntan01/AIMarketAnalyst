from datetime import datetime, timedelta, timezone

from core.market_models import Candle, candle_close_at
from core.smc_context import external_swing_points, internal_swing_points


def internal_history(count: int = 5) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = [
        Candle(
            time=start + timedelta(hours=4 * index),
            open=100.0,
            high=110.0,
            low=90.0,
            close=100.0,
        )
        for index in range(count)
    ]
    if count >= 5:
        history[2] = Candle(
            time=history[2].time,
            open=100.0,
            high=120.0,
            low=80.0,
            close=100.0,
        )
    return history


def test_internal_pivot_uses_width_two_and_same_confirmation_contract():
    history = internal_history()

    result = internal_swing_points(history, symbol="EURUSD", timeframe="H4")

    assert [item["index"] for item in result["highs"]] == [2]
    high = result["highs"][0]
    assert high["pivot_width"] == 2
    assert high["confirmation_delay"] == 2
    assert high["scope"] == "internal"
    assert high["pivot_time"] == history[2].time.isoformat()
    assert high["confirmed_at"] == candle_close_at(history[4].time, "H4").isoformat()
    assert high["pivot_time"] != high["confirmed_at"]
    assert high["usable"] is True


def test_internal_pivot_with_too_few_right_candles_is_not_emitted():
    result = internal_swing_points(internal_history(4), symbol="EURUSD", timeframe="H4")

    assert result == {"highs": [], "lows": []}


def test_internal_and_external_seams_have_different_required_widths():
    history = internal_history()

    internal = internal_swing_points(history, symbol="EURUSD", timeframe="H4")
    external = external_swing_points(history, symbol="EURUSD", timeframe="H4")

    assert internal["highs"]
    assert external == {"highs": [], "lows": []}


def test_internal_detector_keeps_stable_identity_when_prefix_shifts():
    history = internal_history()
    shifted = [
        Candle(
            time=history[0].time - timedelta(hours=4),
            open=100.0,
            high=105.0,
            low=95.0,
            close=100.0,
        )
    ] + history

    original = internal_swing_points(history, symbol="EURUSD", timeframe="H4")
    moved = internal_swing_points(shifted, symbol="EURUSD", timeframe="H4")

    assert moved["highs"][0]["index"] == original["highs"][0]["index"] + 1
    assert moved["highs"][0]["swing_id"] == original["highs"][0]["swing_id"]
