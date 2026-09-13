from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    _count_trend_legs,
    external_swing_points,
    normalize_swing_sequence,
    ordered_swing_sequence,
)


def plateau_history(second_high: float = 120.0) -> list[Candle]:
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    history = [
        Candle(
            time=start + timedelta(hours=4 * index),
            open=100.0,
            high=110.0,
            low=90.0,
            close=100.0,
        )
        for index in range(12)
    ]
    history[5] = Candle(history[5].time, 100.0, 120.0, 90.0, 100.0)
    history[6] = Candle(history[6].time, 100.0, second_high, 90.0, 100.0)
    return history


def test_equal_high_plateau_emits_one_earliest_representative():
    result = external_swing_points(
        plateau_history(),
        symbol="EURUSD",
        timeframe="H4",
    )

    assert [item["index"] for item in result["highs"]] == [5]
    assert result["highs"][0]["equal_level"] is True
    assert result["highs"][0]["plateau_size"] == 2


def test_equal_tolerance_groups_nearby_levels_without_duplicate_output():
    result = external_swing_points(
        plateau_history(second_high=119.9),
        symbol="EURUSD",
        timeframe="H4",
        equal_tolerance=0.2,
    )

    assert [item["index"] for item in result["highs"]] == [5]
    assert result["highs"][0]["level"] == 120.0
    assert result["highs"][0]["plateau_size"] == 2


def test_normalization_sorts_each_stream_by_time_not_input_index():
    swings = {
        "highs": [
            {"swing_id": "H2", "pivot_time": "2026-01-03T00:00:00+00:00", "index": 1},
            {"swing_id": "H1", "pivot_time": "2026-01-02T00:00:00+00:00", "index": 99},
        ],
        "lows": [
            {"swing_id": "L1", "pivot_time": "2026-01-02T12:00:00+00:00", "index": 0},
        ],
    }

    normalized = normalize_swing_sequence(swings)
    ordered = ordered_swing_sequence(swings)

    assert [item["swing_id"] for item in normalized["highs"]] == ["H1", "H2"]
    assert [item["swing_id"] for item in ordered] == ["H1", "L1", "H2"]


def test_trend_legs_use_independent_high_low_runs_not_positional_pairing():
    swings = {
        "highs": [
            {"swing_id": "H1", "pivot_time": "2026-01-01T00:00:00+00:00", "level": 100.0},
            {"swing_id": "H2", "pivot_time": "2026-01-03T00:00:00+00:00", "level": 110.0},
            {"swing_id": "H3", "pivot_time": "2026-01-05T00:00:00+00:00", "level": 120.0},
            {"swing_id": "H4", "pivot_time": "2026-01-07T00:00:00+00:00", "level": 130.0},
        ],
        "lows": [
            {"swing_id": "L1", "pivot_time": "2026-01-02T00:00:00+00:00", "level": 90.0},
            {"swing_id": "L2", "pivot_time": "2026-01-04T00:00:00+00:00", "level": 95.0},
        ],
    }

    assert _count_trend_legs(swings) == 1
