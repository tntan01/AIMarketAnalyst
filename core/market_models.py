from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def merge_candles(old_candles: list[Candle], new_candles: list[Candle]) -> list[Candle]:
    """Merge two time-keyed candle lists, preferring the newest data.

    Candles sharing the same open time are replaced by the newer sample, which
    also refreshes the still-forming last candle. New candles are appended in
    time order; closed candles are never dropped and no duplicates are created.
    """
    by_time: dict[datetime, Candle] = {}
    for candle in old_candles:
        by_time[candle.time] = candle
    for candle in new_candles:
        by_time[candle.time] = candle
    return [by_time[time] for time in sorted(by_time)]


@dataclass(frozen=True, slots=True)
class MarketContext:
    symbol: str
    timeframe: str
    candles: list[Candle]


@dataclass(frozen=True, slots=True)
class TradeSetup:
    symbol: str
    side: str
    entry_zone: str
    invalidation: str
    targets: list[str]
    confidence: int
    rationale: str
