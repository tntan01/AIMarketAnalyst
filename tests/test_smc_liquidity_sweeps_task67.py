"""Task 67 contract tests for excursion-qualified liquidity sweeps."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.smc_context import detect_liquidity_sweeps


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(*rows: tuple[float, float, float, float]) -> list[Candle]:
    return [
        Candle(
            time=START + timedelta(hours=index),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_price, high, low, close) in enumerate(rows)
    ]


def _swing(level: float, *, kind: str, index: int = 0) -> dict[str, object]:
    return {
        "level": level,
        "index": index,
        "time": (START + timedelta(hours=index)).isoformat(),
        "pivot_time": (START + timedelta(hours=index)).isoformat(),
        "kind": kind,
        "swing_id": f"{kind}-{index}",
        "confirmed": True,
        "usable": True,
        "provisional": False,
    }


def test_high_sweep_requires_strict_excursion_and_records_reclaim_provenance():
    result = detect_liquidity_sweeps(
        _candles(
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 110.21, 99.5, 109.9),
        ),
        {"highs": [_swing(110, kind="high")], "lows": []},
        symbol="EURUSD",
        timeframe="H1",
        tick_size=0.1,
        atr_value=1.0,
    )

    assert len(result["swept_highs"]) == 1
    sweep = result["swept_highs"][0]
    assert sweep["depth"] == pytest.approx(0.21)
    assert sweep["depth_atr"] == pytest.approx(0.21)
    assert sweep["reclaim_bars"] == 1
    assert sweep["reclaimed_at"] == (START + timedelta(hours=3)).isoformat()
    assert sweep["source_pool_id"] == "high-0"


def test_exact_excursion_boundary_is_not_a_sweep():
    result = detect_liquidity_sweeps(
        _candles(
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 110.2, 99.5, 109.9),
        ),
        {"highs": [_swing(110, kind="high")], "lows": []},
        tick_size=0.1,
        atr_value=1.0,
    )

    assert result["swept_highs"] == []


def test_low_sweep_is_mirrored():
    result = detect_liquidity_sweeps(
        _candles(
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 100.5, 89.79, 90.1),
        ),
        {"highs": [], "lows": [_swing(90, kind="low")]},
        timeframe="H1",
        tick_size=0.1,
        atr_current=1.0,
    )

    assert len(result["swept_lows"]) == 1
    sweep = result["swept_lows"][0]
    assert sweep["side"] == "buy"
    assert sweep["depth"] == pytest.approx(0.21)
    assert sweep["source_pool_id"] == "low-0"


@pytest.mark.parametrize(
    "close, expected",
    [(110.01, False), (109.99, True)],
)
def test_wick_only_or_reclaim_close_controls_high_sweep(close: float, expected: bool):
    result = detect_liquidity_sweeps(
        _candles(
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 110.3, 99.5, close),
        ),
        {"highs": [_swing(110, kind="high")], "lows": []},
        tick_size=0.1,
        atr_value=1.0,
    )

    assert bool(result["swept_highs"]) is expected


def test_typed_sweep_without_causal_excursion_metadata_fails_closed():
    result = detect_liquidity_sweeps(
        _candles(
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 110.3, 99.5, 109.9),
        ),
        {"highs": [_swing(110, kind="high")], "lows": []},
    )

    assert result == {"swept_highs": [], "swept_lows": []}


def test_pool_levels_are_used_when_explicitly_supplied():
    result = detect_liquidity_sweeps(
        _candles(
            (100, 101, 99, 100),
            (100, 101, 99, 100),
            (100, 110.31, 99.5, 109.9),
        ),
        {"highs": [], "lows": []},
        liquidity_pools={
            "equal_highs": [110.0],
            "equal_lows": [],
            "swing_highs": [],
            "swing_lows": [],
        },
        tick_size=0.1,
        atr_value=1.0,
    )

    assert result["swept_highs"][0]["source_pool_id"] == "equal_high:110"


def test_invalid_excursion_buffer_is_rejected():
    with pytest.raises(ValueError):
        detect_liquidity_sweeps(
            _candles((100, 101, 99, 100), (100, 101, 99, 100), (100, 111, 99, 100)),
            {"highs": [_swing(110, kind="high")], "lows": []},
            excursion_buffer=-0.1,
        )
