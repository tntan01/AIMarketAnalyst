from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.entry_engine import evaluate_entry
from core.market_models import Candle

UTC = timezone.utc


def _candles(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(base + timedelta(hours=index), open_, high, low, close, 100)
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def _m15_candles(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Candle(base + timedelta(minutes=15 * index), open_, high, low, close, 100)
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def _m15_strict_bullish() -> list[Candle]:
    """Minimal M15 candles forming higher-low structure + bullish displacement."""
    candles: list[Candle] = []
    base = datetime(2026, 1, 1, tzinfo=UTC)
    p = 1.1000
    # downtrend to first swing low
    for i in range(5):
        candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0005, p - 0.0012, p - 0.0010, 100))
        p -= 0.0010
    # first swing low
    candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0004, p - 0.0015, p + 0.0002, 100))
    # uptrend
    p = candles[-1].close
    for _ in range(6):
        candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0012, p - 0.0003, p + 0.0010, 100))
        p += 0.0010
    # shallow dip to second swing low
    for _ in range(4):
        candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0004, p - 0.0010, p - 0.0008, 100))
        p -= 0.0008
    # second swing low (higher)
    candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0004, p - 0.0010, p + 0.0003, 100))
    # uptrend
    p = candles[-1].close
    for _ in range(7):
        candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0010, p - 0.0003, p + 0.0008, 100))
        p += 0.0008
    # fill to 47
    while len(candles) < 47:
        candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0013, p - 0.0003, p + 0.0010, 100))
        p += 0.0010
    # last 3: strong bullish displacement
    for _ in range(3):
        candles.append(Candle(base + timedelta(minutes=15 * len(candles)), p, p + 0.0035, p - 0.0002, p + 0.0030, 100))
        p += 0.0030
    return candles


def test_entry_engine_confirms_buy_only_when_price_in_zone_and_h1_rejects() -> None:
    state = evaluate_entry(
        side="buy",
        technical={"price": 1.101, "atr_h4": 0.01},
        smc={"H1": {"displacement": "bullish", "bos": True}, "H4": {"premium_discount": "discount"}},
        h1_candles=_candles(
            [
                (1.102, 1.104, 1.100, 1.101),
                (1.101, 1.103, 1.098, 1.099),
                (1.099, 1.106, 1.095, 1.105),
            ]
        ),
        entry_zone=[1.098, 1.104],
        m15_candles=_m15_strict_bullish(),
    )

    assert state["entry_status"] == "confirmed_entry"
    assert state["ready_to_trade"] is True
    assert state["h1_confirmation"] is True
    assert state["m15_quality"] == "strict"


def test_entry_engine_keeps_watch_zone_without_confirmation() -> None:
    state = evaluate_entry(
        side="sell",
        technical={"price": 1.19, "atr_h4": 0.01},
        smc={"H1": {"displacement": "neutral"}, "H4": {"premium_discount": "premium"}},
        h1_candles=_candles([(1.18, 1.182, 1.177, 1.181), (1.181, 1.183, 1.179, 1.182)]),
        entry_zone=[1.195, 1.2],
    )

    assert state["entry_status"] == "watch_zone"
    assert state["ready_to_trade"] is False
