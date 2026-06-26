"""Tests for smc_context — swing points, BOS/CHOCH, FVG, liquidity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.smc_context import (
    detect_bos_choch,
    detect_fvg,
    detect_liquidity_pools,
    detect_liquidity_sweeps,
    swing_points,
)


def _make_candles(
    prices: list[tuple[float, float, float, float]],  # (open, high, low, close)
    *,
    bar_minutes: int = 240,
) -> list[Candle]:
    """Build candles from explicit OHLC tuples for precise swing testing."""
    t = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for o, h, l, c in prices:
        candles.append(
            Candle(
                time=t,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=1000.0,
            )
        )
        t += timedelta(minutes=bar_minutes)
    return candles


class TestSwingPoints:
    def test_finds_swing_high_and_low(self):
        """5 candles with middle candle as clear swing high and low."""
        candles = _make_candles([
            (1.1000, 1.1010, 1.0990, 1.1005),  # 0
            (1.1005, 1.1020, 1.1000, 1.1015),  # 1
            (1.1015, 1.1050, 1.0980, 1.1020),  # 2 — swing high + swing low
            (1.1020, 1.1030, 1.1010, 1.1025),  # 3
            (1.1025, 1.1040, 1.1020, 1.1035),  # 4
        ])
        result = swing_points(candles, lookback=2)
        highs = {h["level"] for h in result["highs"]}
        lows = {l["level"] for l in result["lows"]}
        assert 1.1050 in highs  # candle 2 high is max of window
        assert 1.0980 in lows   # candle 2 low is min of window

    def test_empty_on_insufficient_candles(self):
        candles = _make_candles([
            (1.1000, 1.1010, 1.0990, 1.1005),
            (1.1005, 1.1020, 1.1000, 1.1015),
        ])
        result = swing_points(candles, lookback=2)
        assert result["highs"] == []
        assert result["lows"] == []

    def test_no_swing_when_duplicate_high(self):
        """Two equal highs in window → not counted as swing (must be unique)."""
        candles = _make_candles([
            (1.1000, 1.1010, 1.0990, 1.1005),
            (1.1005, 1.1050, 1.1000, 1.1015),
            (1.1015, 1.1050, 1.1010, 1.1020),  # duplicate high → not unique
            (1.1020, 1.1030, 1.1010, 1.1025),
            (1.1025, 1.1040, 1.1020, 1.1035),
        ])
        result = swing_points(candles, lookback=2)
        levels = [h["level"] for h in result["highs"]]
        assert 1.1050 not in levels  # duplicate, should not be counted


class TestDetectBosChoch:
    def test_bullish_bos(self):
        """HH/HL + close above last high → BOS bullish."""
        swings = {
            "highs": [
                {"level": 1.1000, "index": 0, "time": ""},
                {"level": 1.1020, "index": 2, "time": ""},
            ],
            "lows": [
                {"level": 1.0980, "index": 1, "time": ""},
                {"level": 1.1000, "index": 3, "time": ""},
            ],
        }
        candles = _make_candles([
            (1.0990, 1.1000, 1.0980, 1.0990),
            (1.0990, 1.0995, 1.0980, 1.0990),
            (1.0990, 1.1020, 1.0980, 1.0990),
            (1.0990, 1.0995, 1.1000, 1.1030),  # close > last high (1.1020)
        ])[:1]  # We only need last candle
        candles = _make_candles([
            (1.0990, 1.1030, 1.0990, 1.1030),  # close > 1.1020
        ])
        result = detect_bos_choch(swings, candles)
        assert result["bos"] is True
        assert result["displacement"] == "bullish"

    def test_bearish_choch(self):
        """HH/HL uptrend + close below prev low → CHOCH bearish."""
        swings = {
            "highs": [
                {"level": 1.1000, "index": 0, "time": ""},
                {"level": 1.1020, "index": 2, "time": ""},  # HH
            ],
            "lows": [
                {"level": 1.0980, "index": 1, "time": ""},
                {"level": 1.1010, "index": 3, "time": ""},  # HL
            ],
        }
        # HH/HL = uptrend, close (1.0970) < prev low (1.0980) → CHOCH
        candles = _make_candles([
            (1.0990, 1.0990, 1.0970, 1.0970),
        ])
        result = detect_bos_choch(swings, candles)
        assert result["choch"] is True
        assert result["displacement"] == "bearish"


class TestDetectFVG:
    def test_bullish_fvg(self):
        """First high < third low → bullish FVG."""
        candles = _make_candles([
            (1.1000, 1.1010, 1.0990, 1.1005),
            (1.1005, 1.1008, 1.1000, 1.1002),
            (1.1002, 1.1030, 1.1020, 1.1025),  # low (1.1020) > first high (1.1010)
        ])
        result = detect_fvg(candles)
        assert len(result) > 0
        assert result[0]["type"] == "bullish_fvg"
        # Gap between first.high (1.1010) and third.low (1.1020)
        assert result[0]["low"] == 1.1010
        assert result[0]["high"] == 1.1020

    def test_bearish_fvg(self):
        """First low > third high → bearish FVG."""
        candles = _make_candles([
            (1.1000, 1.1010, 1.1006, 1.1008),  # low = 1.1006
            (1.1008, 1.1012, 1.1002, 1.1005),
            (1.1005, 1.1005, 1.0990, 1.0995),  # high = 1.1005 < first.low (1.1006) → gap!
        ])
        result = detect_fvg(candles)
        assert len(result) > 0
        assert result[0]["type"] == "bearish_fvg"
        assert result[0]["low"] == 1.1005  # third.high
        assert result[0]["high"] == 1.1006  # first.low


class TestDetectLiquidityPools:
    def test_equal_highs(self):
        """Equal highs detected when swing highs are within tolerance."""
        # Create swings manually with two close highs
        swings = {
            "highs": [
                {"level": 1.10500, "index": 1, "time": ""},
                {"level": 1.10502, "index": 5, "time": ""},
            ],
            "lows": [],
        }
        # Need candles for avg_range calculation
        candles = _make_candles([
            (1.1000, 1.1010, 1.0990, 1.1000),
            (1.1000, 1.1050, 1.0995, 1.1040),
            (1.1040, 1.1055, 1.1030, 1.1045),
            (1.1045, 1.1060, 1.1020, 1.1030),
            (1.1030, 1.1040, 1.1010, 1.1015),
            (1.1015, 1.1050, 1.1000, 1.1010),
        ])
        result = detect_liquidity_pools(candles, swings)
        # 1.10500 and 1.10502 differ by 0.00002, avg_range ~ 0.002
        # tolerance = max(avg_range * 0.15, 0.0001) ≈ 0.0003
        # 0.00002 < 0.0003 → equal highs
        assert len(result["equal_highs"]) > 0

    def test_no_equal_when_far_apart(self):
        candles = _make_candles([
            (1.1000, 1.1050, 1.0990, 1.1005),
            (1.1005, 1.1020, 1.1000, 1.1015),
            (1.1015, 1.1030, 1.1010, 1.1020),
            (1.1020, 1.1035, 1.1010, 1.1025),
            (1.1025, 1.1040, 1.1020, 1.1035),
        ])
        swings = swing_points(candles, lookback=2)
        result = detect_liquidity_pools(candles, swings)
        # All highs are different → no equal highs
        assert result["equal_highs"] == []


class TestDetectLiquiditySweeps:
    def test_swept_high(self):
        candles = _make_candles([
            (1.1000, 1.1050, 1.0990, 1.1005),
            (1.1005, 1.1020, 1.1000, 1.1015),
            (1.1015, 1.1060, 1.1000, 1.0990),  # high > 1.1050, close < 1.1050 → sweep
        ])
        swings = {
            "highs": [{"level": 1.1050, "index": 0, "time": ""}],
            "lows": [],
        }
        result = detect_liquidity_sweeps(candles, swings)
        assert len(result["swept_highs"]) > 0
        assert result["swept_highs"][0]["level"] == 1.1050

    def test_no_sweep_when_close_above(self):
        candles = _make_candles([
            (1.1000, 1.1050, 1.0990, 1.1005),
            (1.1005, 1.1060, 1.1010, 1.1060),  # high > 1.1050, close > 1.1050 → NOT a sweep
        ])
        swings = {
            "highs": [{"level": 1.1050, "index": 0, "time": ""}],
            "lows": [],
        }
        result = detect_liquidity_sweeps(candles, swings)
        assert result["swept_highs"] == []
