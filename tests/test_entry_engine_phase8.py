"""Phase 8 tests: M15 must decide entry status, not just multiply score.

Current behavior (pre-Phase 8):
  - M15 acts as a score multiplier (strict=1.0, loose=0.85, none=0.7)
  - confirmed_entry only checks: in_zone AND confirmation_score >= 70 AND trigger != "none"
  - A high base score can pass even with M15 "none" (e.g. 100 * 0.7 = 70 >= 70)

Phase 8 target:
  - m15_quality == "strict" AND score >= 70 AND trigger valid => confirmed_entry
  - m15_quality == "loose" AND score >= 70 => waiting_confirmation
  - m15_quality == "none" => watch_zone
  - Missing M15 data => max waiting_confirmation (safe default)

These tests encode Phase 8 target behaviour. They WILL fail on current code
because evaluate_entry() treats M15 as a score multiplier, not a status decider.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.entry_engine import evaluate_entry
from core.market_models import Candle

UTC = timezone.utc
_M15_START = datetime(2026, 6, 1, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# H1 candle helpers (simple, same as existing tests)
# ---------------------------------------------------------------------------


def _make_h1(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    base = datetime(2026, 6, 1, 0, tzinfo=UTC)
    return [
        Candle(base + timedelta(hours=i), o, h, l, c, 100)
        for i, (o, h, l, c) in enumerate(rows)
    ]


def _h1_bullish_engulfing() -> list[Candle]:
    return _make_h1(
        [
            (1.100, 1.103, 1.098, 1.101),
            (1.101, 1.102, 1.097, 1.098),
            (1.098, 1.107, 1.095, 1.106),  # engulfing: close > prev.high
        ]
    )


def _h1_bearish_engulfing() -> list[Candle]:
    return _make_h1(
        [
            (1.100, 1.103, 1.098, 1.101),
            (1.101, 1.104, 1.100, 1.103),
            (1.103, 1.104, 1.095, 1.096),  # engulfing: close < prev.low
        ]
    )


# ---------------------------------------------------------------------------
# M15 candle helpers
#
# Swing detection (lookback=5) needs a unique local min/max in an 11-candle
# window. Each swing low/high is created as an isolated single-candle extreme.
# ---------------------------------------------------------------------------


def _add_m15(candles: list[Candle], o: float, h: float, l: float, c: float) -> None:
    t = len(candles)
    candles.append(Candle(_M15_START + timedelta(minutes=15 * t), o, h, l, c, 100))


def _m15_strict_bullish() -> list[Candle]:
    """M15: 2 swing lows (higher low) + strong bullish displacement last 3."""
    candles: list[Candle] = []
    p = 1.1000

    # downtrend to first swing low (5 candles)
    for _ in range(5):
        _add_m15(candles, p, p + 0.0005, p - 0.0012, p - 0.0010)
        p -= 0.0010
    # FIRST SWING LOW (unique minimum in its 11-candle window)
    _add_m15(candles, p, p + 0.0004, p - 0.0015, p + 0.0002)

    # uptrend recovery (6 candles)
    p = candles[-1].close
    for _ in range(6):
        _add_m15(candles, p, p + 0.0012, p - 0.0003, p + 0.0010)
        p += 0.0010

    # shallow downtrend to second swing low (4 candles)
    for _ in range(4):
        _add_m15(candles, p, p + 0.0004, p - 0.0010, p - 0.0008)
        p -= 0.0008
    # SECOND SWING LOW (higher than first)
    _add_m15(candles, p, p + 0.0004, p - 0.0010, p + 0.0003)

    # uptrend (7 candles)
    p = candles[-1].close
    for _ in range(7):
        _add_m15(candles, p, p + 0.0010, p - 0.0003, p + 0.0008)
        p += 0.0008

    # fill to 47 with mild uptrend (bodies ~0.001, enough for normal ATR baseline)
    while len(candles) < 47:
        _add_m15(candles, p, p + 0.0013, p - 0.0003, p + 0.0010)
        p += 0.0010

    # last 3: strong bullish displacement (body ~0.003 >> 0.3*ATR)
    for _ in range(3):
        _add_m15(candles, p, p + 0.0035, p - 0.0002, p + 0.0030)
        p += 0.0030

    return candles


def _m15_strict_bearish() -> list[Candle]:
    """M15: 2 swing highs (lower high) + strong bearish displacement last 3."""
    candles: list[Candle] = []
    p = 1.1000

    # uptrend to first swing high (5 candles)
    for _ in range(5):
        _add_m15(candles, p, p + 0.0012, p - 0.0005, p + 0.0010)
        p += 0.0010
    # FIRST SWING HIGH
    _add_m15(candles, p, p + 0.0015, p - 0.0004, p - 0.0002)

    # downtrend (6 candles)
    p = candles[-1].close
    for _ in range(6):
        _add_m15(candles, p, p + 0.0003, p - 0.0012, p - 0.0010)
        p -= 0.0010

    # shallow uptrend to second swing high (4 candles)
    for _ in range(4):
        _add_m15(candles, p, p + 0.0010, p - 0.0004, p + 0.0008)
        p += 0.0008
    # SECOND SWING HIGH (lower than first)
    _add_m15(candles, p, p + 0.0010, p - 0.0004, p - 0.0003)

    # downtrend (7 candles)
    p = candles[-1].close
    for _ in range(7):
        _add_m15(candles, p, p + 0.0003, p - 0.0010, p - 0.0008)
        p -= 0.0008

    # fill to 47
    while len(candles) < 47:
        _add_m15(candles, p, p + 0.0005, p - 0.0013, p - 0.0010)
        p -= 0.0010

    # last 3: strong bearish displacement
    for _ in range(3):
        _add_m15(candles, p, p + 0.0002, p - 0.0035, p - 0.0030)
        p -= 0.0030

    return candles


def _m15_loose_bullish() -> list[Candle]:
    """M15: structure passes (higher low) but NO displacement (tiny bodies)."""
    candles = _m15_strict_bullish()
    # Replace last 3 displacement candles with tiny-body doji-like candles
    for i in range(-3, 0):
        old = candles[i]
        candles[i] = Candle(old.time, old.open, old.open + 0.0001, old.open - 0.0001, old.open + 0.00005, 100)
    return candles


def _m15_loose_bearish() -> list[Candle]:
    """M15: structure passes (lower high) but NO displacement."""
    candles = _m15_strict_bearish()
    for i in range(-3, 0):
        old = candles[i]
        candles[i] = Candle(old.time, old.open, old.open + 0.0001, old.open - 0.0001, old.open - 0.00005, 100)
    return candles


def _m15_none() -> list[Candle]:
    """M15: choppy sideways — neither structure nor displacement passes.

    Wide candle ranges (wicks) inflate ATR so tiny bodies fail the 0.3*ATR
    displacement threshold. Alternating directions prevent any swing structure
    from forming.
    """
    candles: list[Candle] = []
    p = 1.1000
    for i in range(20):
        direction = 1 if i % 2 == 0 else -1
        o = p
        c = p + direction * 0.0003
        # wide wicks create large candle ranges -> higher ATR
        _add_m15(candles, o, o + 0.0020, o - 0.0020, c)
        p = c
    return candles


# ---------------------------------------------------------------------------
# SMC helpers
# ---------------------------------------------------------------------------


def _bullish_smc() -> dict:
    return {
        "H1": {"displacement": "bullish", "bos": True},
        "H4": {"displacement": "bullish", "bos": True, "premium_discount": "discount"},
    }


def _bearish_smc() -> dict:
    return {
        "H1": {"displacement": "bearish", "bos": True},
        "H4": {"displacement": "bearish", "bos": True, "premium_discount": "premium"},
    }


# ---------------------------------------------------------------------------
# Phase 8 test cases
# ---------------------------------------------------------------------------


class TestPhase8M15DecidesEntryStatus:
    """M15 quality must determine entry_status, not just multiply score.

    All tests encode Phase 8 TARGET behaviour. They WILL FAIL on the current
    codebase because evaluate_entry() only uses M15 as a score multiplier.
    """

    # -- Case 1: M15 strict => confirmed_entry (buy) --------------------------

    def test_m15_strict_allows_confirmed_entry_buy(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish_engulfing(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_strict_bullish(),
        )
        assert result["m15_quality"] == "strict", (
            f"expected strict, got {result.get('m15_quality')}"
        )
        assert result["entry_status"] == "confirmed_entry", (
            f"M15 strict must give confirmed_entry, got {result['entry_status']}"
        )
        assert result["ready_to_trade"] is True

    # -- Case 2: M15 loose => waiting_confirmation (buy) ----------------------

    def test_m15_loose_demotes_to_waiting_confirmation_buy(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish_engulfing(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_loose_bullish(),
        )
        assert result["m15_quality"] == "loose", (
            f"expected loose, got {result.get('m15_quality')}"
        )
        assert result["entry_status"] == "waiting_confirmation", (
            f"M15 loose must give waiting_confirmation, got {result['entry_status']}"
        )
        assert result["ready_to_trade"] is False

    # -- Case 3: M15 none => watch_zone (buy) ---------------------------------

    def test_m15_none_demotes_to_watch_zone_buy(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish_engulfing(),
            entry_zone=[1.098, 1.104],
            m15_candles=_m15_none(),
        )
        assert result["m15_quality"] == "none", (
            f"expected none, got {result.get('m15_quality')}"
        )
        assert result["entry_status"] == "watch_zone", (
            f"M15 none must give watch_zone, got {result['entry_status']}"
        )
        assert result["ready_to_trade"] is False

    # -- Case 4: M15 strict => confirmed_entry (sell) -------------------------

    def test_m15_strict_allows_confirmed_entry_sell(self):
        result = evaluate_entry(
            side="sell",
            technical={"price": 1.103, "atr_h4": 0.01},
            smc=_bearish_smc(),
            h1_candles=_h1_bearish_engulfing(),
            entry_zone=[1.100, 1.106],
            m15_candles=_m15_strict_bearish(),
        )
        assert result["m15_quality"] == "strict", (
            f"expected strict, got {result.get('m15_quality')}"
        )
        assert result["entry_status"] == "confirmed_entry", (
            f"M15 strict sell must give confirmed_entry, got {result['entry_status']}"
        )
        assert result["ready_to_trade"] is True

    # -- Case 5: M15 loose (sell) => waiting_confirmation ---------------------

    def test_m15_loose_demotes_to_waiting_confirmation_sell(self):
        result = evaluate_entry(
            side="sell",
            technical={"price": 1.103, "atr_h4": 0.01},
            smc=_bearish_smc(),
            h1_candles=_h1_bearish_engulfing(),
            entry_zone=[1.100, 1.106],
            m15_candles=_m15_loose_bearish(),
        )
        assert result["m15_quality"] == "loose", (
            f"expected loose, got {result.get('m15_quality')}"
        )
        assert result["entry_status"] == "waiting_confirmation", (
            f"M15 loose sell must give waiting_confirmation, got {result['entry_status']}"
        )
        assert result["ready_to_trade"] is False

    # -- Case 6: Missing M15 => max waiting_confirmation ----------------------

    def test_missing_m15_caps_at_waiting_confirmation(self):
        result = evaluate_entry(
            side="buy",
            technical={"price": 1.101, "atr_h4": 0.01},
            smc=_bullish_smc(),
            h1_candles=_h1_bullish_engulfing(),
            entry_zone=[1.098, 1.104],
            # m15_candles not provided
        )
        assert result["entry_status"] != "confirmed_entry", (
            f"missing M15 must not auto-confirm, got {result['entry_status']}"
        )
        assert result["ready_to_trade"] is False
        assert result["entry_status"] in ("waiting_confirmation", "watch_zone"), (
            f"missing M15 must cap at waiting_confirmation/watch_zone, got {result['entry_status']}"
        )
