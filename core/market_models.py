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
