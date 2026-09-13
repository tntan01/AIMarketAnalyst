"""Task 66 contracts for confirmed/equal liquidity pools."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.smc_context import detect_liquidity_pools


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(count=8):
    return [
        Candle(
            time=START + timedelta(hours=index),
            open=100,
            high=101,
            low=99,
            close=100,
            volume=100,
        )
        for index in range(count)
    ]


def _swing(level, index, *, kind, confirmed=True, usable=True, provisional=False):
    return {
        "level": level,
        "index": index,
        "kind": kind,
        "swing_id": f"{kind}-{index}",
        "confirmed": confirmed,
        "usable": usable,
        "provisional": provisional,
    }


def test_only_confirmed_usable_non_provisional_swings_form_pools():
    result = detect_liquidity_pools(
        _candles(),
        {
            "highs": [
                _swing(110, 1, kind="high"),
                _swing(110.05, 2, kind="high", confirmed=False),
                _swing(110.02, 3, kind="high", usable=False),
                _swing(110.01, 4, kind="high", provisional=True),
            ],
            "lows": [],
        },
        tick_size=0.1,
        atr_value=1.0,
    )

    assert result["swing_highs"] == [110.0]
    assert result["equal_highs"] == []


def test_equal_high_tolerance_is_max_of_two_ticks_and_atr_fraction():
    result = detect_liquidity_pools(
        _candles(),
        {
            "highs": [
                _swing(110.0, 1, kind="high"),
                _swing(110.2, 2, kind="high"),  # exactly 2*tick
                _swing(110.41, 3, kind="high"),
            ],
            "lows": [],
        },
        tick_size=0.1,
        atr_value=1.0,
    )

    assert result["equal_tolerance"] == pytest.approx(0.2)
    assert result["equal_highs"] == [pytest.approx(110.1)]


def test_equal_lows_are_symmetric_and_boundary_is_inclusive():
    result = detect_liquidity_pools(
        _candles(),
        {
            "highs": [],
            "lows": [
                _swing(90.0, 1, kind="low"),
                _swing(90.2, 2, kind="low"),
            ],
        },
        tick_size=0.1,
        atr_current=1.0,
    )

    assert result["equal_lows"] == [pytest.approx(90.1)]
    assert result["swing_lows"] == [90.0, 90.2]


def test_typed_swings_without_tick_or_atr_fail_closed_for_equal_relation():
    result = detect_liquidity_pools(
        _candles(),
        {
            "highs": [
                _swing(110.0, 1, kind="high"),
                _swing(110.01, 2, kind="high"),
            ],
            "lows": [],
        },
    )

    assert result["equal_highs"] == []
    assert result["status"] == "unknown"
    assert "SMC_EQUAL_LEVEL_TOLERANCE_UNAVAILABLE" in result["reason_codes"]


def test_explicit_equal_tolerance_is_supported_and_output_is_bounded():
    result = detect_liquidity_pools(
        _candles(),
        {
            "highs": [_swing(110 + index * 0.01, index, kind="high") for index in range(10)],
            "lows": [_swing(90 + index * 0.01, index, kind="low") for index in range(10)],
        },
        equal_tolerance=0.01,
    )

    assert len(result["swing_highs"]) == 3
    assert len(result["swing_lows"]) == 3
    assert len(result["equal_highs"]) <= 3
    assert len(result["equal_lows"]) <= 3


def test_invalid_tolerance_metadata_is_rejected():
    swings = {"highs": [_swing(110, 1, kind="high")], "lows": []}
    with pytest.raises(ValueError):
        detect_liquidity_pools(_candles(), swings, tick_size=0, atr_value=1)
    with pytest.raises(ValueError):
        detect_liquidity_pools(_candles(), swings, equal_tolerance=-0.1)
