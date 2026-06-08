from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    build_smc_context,
    classify_premium_discount,
    detect_bos_choch,
    detect_fvg,
    detect_order_blocks,
    detect_supply_demand_zones,
    summarize_structure,
    swing_points,
)


def _series(values: list[tuple[float, float, float, float]]) -> list[Candle]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(
            time=base_time + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(values)
    ]


def test_swing_points_picks_local_extremes() -> None:
    candles = _series(
        [
            (1.0, 1.1, 0.9, 1.05),
            (1.05, 1.15, 1.00, 1.10),
            (1.10, 1.30, 1.05, 1.25),  # local high
            (1.25, 1.28, 1.10, 1.15),
            (1.15, 1.20, 0.80, 0.90),  # local low
            (0.90, 1.00, 0.85, 0.95),
            (0.95, 1.05, 0.90, 1.00),
        ]
    )
    swings = swing_points(candles, lookback=2)
    high_levels = [item["level"] for item in swings["highs"]]
    low_levels = [item["level"] for item in swings["lows"]]
    assert 1.30 in high_levels
    assert 0.80 in low_levels


def test_bullish_bos_detected_when_close_breaks_prev_high() -> None:
    swings = {
        "highs": [{"level": 1.20, "index": 5}, {"level": 1.30, "index": 12}],
        "lows": [{"level": 1.10, "index": 8}, {"level": 1.18, "index": 15}],
    }
    candles = _series([(1.30, 1.32, 1.28, 1.31), (1.31, 1.40, 1.30, 1.38)])
    bos = detect_bos_choch(swings, candles)
    assert bos["structure"] == "HH/HL"
    assert bos["bos"] is True
    assert bos["displacement"] == "bullish"


def test_choch_detected_when_close_breaks_prev_low_in_uptrend() -> None:
    swings = {
        "highs": [{"level": 1.20, "index": 5}, {"level": 1.30, "index": 12}],
        "lows": [{"level": 1.10, "index": 8}, {"level": 1.18, "index": 15}],
    }
    candles = _series([(1.20, 1.21, 1.05, 1.06)])
    bos = detect_bos_choch(swings, candles)
    assert bos["choch"] is True
    assert bos["displacement"] == "bearish"


def test_fvg_detected_when_three_candles_have_gap() -> None:
    rows = [
        (1.10, 1.11, 1.09, 1.10),
        (1.10, 1.12, 1.10, 1.11),
        (1.13, 1.16, 1.13, 1.15),  # low here > high of 2 candles ago -> bullish FVG
    ]
    fvg = detect_fvg(_series(rows))
    assert any(item["type"] == "bullish_fvg" for item in fvg)


def test_order_block_detected_after_impulse() -> None:
    rows = [
        (1.10, 1.11, 1.09, 1.10),
        (1.10, 1.12, 1.10, 1.11),
        (1.11, 1.115, 1.095, 1.098),  # bearish OB candidate
        (1.098, 1.140, 1.097, 1.135),  # impulse up close above prior high
        (1.135, 1.150, 1.130, 1.148),
    ]
    candles = _series(rows)
    fvg = detect_fvg(candles)
    blocks = detect_order_blocks(candles, fvg)
    assert any(block["type"] == "bullish_order_block" for block in blocks)


def test_supply_demand_zones_identified_after_consolidation() -> None:
    rows = [
        (1.10, 1.105, 1.095, 1.10),
        (1.10, 1.106, 1.094, 1.10),
        (1.10, 1.105, 1.095, 1.10),
        (1.10, 1.108, 1.094, 1.105),
        (1.105, 1.180, 1.103, 1.175),  # bullish impulse
        (1.175, 1.190, 1.170, 1.185),
        (1.185, 1.190, 1.175, 1.180),
        (1.180, 1.182, 1.178, 1.181),
        (1.181, 1.183, 1.179, 1.180),
        (1.180, 1.182, 1.150, 1.155),  # bearish impulse
        (1.155, 1.158, 1.150, 1.156),
    ]
    demand, supply = detect_supply_demand_zones(_series(rows))
    assert demand
    assert supply


def test_premium_discount_uses_swing_range() -> None:
    swings = {
        "highs": [{"level": 1.20}],
        "lows": [{"level": 1.00}],
    }
    assert classify_premium_discount(1.18, swings) == "premium"
    assert classify_premium_discount(1.02, swings) == "discount"
    assert classify_premium_discount(1.10, swings) == "equilibrium"


def test_summarize_structure_returns_dict_with_bos_keys() -> None:
    rows = [(1.10 + i * 0.001, 1.10 + i * 0.001 + 0.002, 1.10 + i * 0.001 - 0.002, 1.10 + i * 0.001 + 0.001) for i in range(20)]
    summary = summarize_structure(_series(rows))
    assert "structure" in summary
    assert "bos" in summary


def test_build_smc_context_returns_three_timeframes() -> None:
    rows = [(1.10 + i * 0.001, 1.10 + i * 0.001 + 0.002, 1.10 + i * 0.001 - 0.002, 1.10 + i * 0.001 + 0.001) for i in range(80)]
    candles = _series(rows)
    smc = build_smc_context(candles, candles, candles)
    assert set(smc.keys()) == {"D1", "H4", "H1"}
    assert "supply_zones" in smc["H4"]
    assert "demand_zones" in smc["H4"]
    assert "fvg" in smc["H4"]
    assert "order_blocks" in smc["H4"]
    assert "liquidity_pools" in smc["H4"]
