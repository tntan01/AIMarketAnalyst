from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


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


def normalize_candles(candles: list[Candle]) -> list[Candle]:
    """Return candles with times normalized to aware UTC.

    Snapshot candle dicts and provider OHLCV may disagree on timezone awareness
    (one side naive, the other aware). Normalizing both to aware UTC keeps the
    time-keyed comparison in ``merge_candles`` safe.
    """
    result = []
    for candle in candles:
        t = candle.time
        if t.tzinfo is None:
            t = t.replace(tzinfo=timezone.utc)
        else:
            t = t.astimezone(timezone.utc)
        result.append(
            Candle(
                time=t,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
            )
        )
    return result


def candles_from_dicts(candles: list[dict]) -> list[Candle]:
    """Parse snapshot candle dicts into Candle objects, normalized to aware UTC."""
    result = []
    for candle in candles:
        raw = candle.get("time")
        if isinstance(raw, datetime):
            parsed = raw
        else:
            parsed = datetime.fromisoformat(str(raw))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        else:
            parsed = parsed.astimezone(timezone.utc)
        result.append(
            Candle(
                time=parsed,
                open=float(candle["open"]),
                high=float(candle["high"]),
                low=float(candle["low"]),
                close=float(candle["close"]),
                volume=float(candle.get("volume", 0.0)),
            )
        )
    return result


def candles_to_dicts(candles: list[Candle]) -> list[dict]:
    """Serialize Candle objects back to chart payload dicts (ISO time strings)."""
    return [
        {
            "time": candle.time.isoformat(),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]


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
