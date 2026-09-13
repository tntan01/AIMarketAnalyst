from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Sequence


SMC_TIMEFRAME_INTERVALS = {
    "D1": timedelta(days=1),
    "H4": timedelta(hours=4),
    "H1": timedelta(hours=1),
    "M15": timedelta(minutes=15),
}


@dataclass(frozen=True, slots=True)
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True, slots=True)
class SmcCandleValidationIssue:
    """A deterministic, non-mutating explanation of one invalid SMC candle."""

    code: str
    index: int
    field: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "index": self.index,
            "field": self.field,
            "detail": self.detail,
        }


class SmcCandleDataError(ValueError):
    """Raised when SMC candle data violates the approved data contract."""

    def __init__(self, issues: Sequence[SmcCandleValidationIssue]) -> None:
        self.issues = tuple(issues)
        self.reason_codes = tuple(dict.fromkeys(issue.code for issue in self.issues))
        summary = ", ".join(self.reason_codes) or "SMC_DATA_INVALID"
        super().__init__(f"Invalid SMC candle data: {summary}")


def _utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return None
    return value.astimezone(timezone.utc)


def _finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def _valid_ohlc(candle: Candle) -> bool:
    values = (candle.open, candle.high, candle.low, candle.close)
    if not all(_finite_number(value) for value in values):
        return False
    open_price = float(candle.open)
    high_price = float(candle.high)
    low_price = float(candle.low)
    close_price = float(candle.close)
    return (
        high_price >= max(open_price, close_price)
        and low_price <= min(open_price, close_price)
        and high_price >= low_price
    )


def validate_smc_candles(
    candles: Sequence[Candle],
    timeframe: str,
) -> tuple[SmcCandleValidationIssue, ...]:
    """Return data-contract reasons without repairing or reordering candles.

    Timestamp comparisons are made only after conversion to UTC.  A duplicate
    open time is an order error, so callers must reject the input rather than
    silently keeping one of the records.
    """

    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")
    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")

    issues: list[SmcCandleValidationIssue] = []
    previous_time: datetime | None = None
    for index, candle in enumerate(candles):
        if not isinstance(candle, Candle):
            raise ValueError("candles must contain Candle objects")

        normalized_time = _utc_timestamp(candle.time)
        if normalized_time is None:
            issues.append(
                SmcCandleValidationIssue(
                    code="SMC_TIMESTAMP_INVALID",
                    index=index,
                    field="time",
                    detail="timestamp must be a timezone-aware datetime",
                )
            )
        elif previous_time is not None and normalized_time <= previous_time:
            kind = "duplicate open time" if normalized_time == previous_time else "timestamp is not strictly increasing"
            issues.append(
                SmcCandleValidationIssue(
                    code="SMC_TIMESTAMP_ORDER_INVALID",
                    index=index,
                    field="time",
                    detail=kind,
                )
            )
        if normalized_time is not None:
            previous_time = normalized_time

        if not _valid_ohlc(candle):
            issues.append(
                SmcCandleValidationIssue(
                    code="SMC_OHLC_INVALID",
                    index=index,
                    field="ohlc",
                    detail="OHLC must be finite and satisfy high >= max(open, close), low <= min(open, close), high >= low",
                )
            )
    return tuple(issues)


def require_valid_smc_candles(
    candles: Sequence[Candle],
    timeframe: str,
) -> tuple[Candle, ...]:
    """Return the original candle records or raise with canonical reasons."""

    issues = validate_smc_candles(candles, timeframe)
    if issues:
        raise SmcCandleDataError(issues)
    return tuple(candles)


def candle_close_at(open_time: datetime, timeframe: str) -> datetime:
    """Return the canonical UTC close boundary for one candle.

    This task deliberately validates only the timestamp/cutoff contract.
    OHLC validity, ordering and duplicate detection belong to task 19.
    """

    if not isinstance(open_time, datetime):
        raise ValueError("candle open time must be a datetime")
    if open_time.tzinfo is None or open_time.utcoffset() is None:
        raise ValueError("candle open time must be timezone-aware")
    interval = SMC_TIMEFRAME_INTERVALS.get(str(timeframe or "").strip().upper())
    if interval is None:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    return open_time.astimezone(timezone.utc) + interval


def closed_candles_at_cutoff(
    candles: Sequence[Candle],
    timeframe: str,
    cutoff: datetime,
) -> tuple[Candle, ...]:
    """Keep candles whose real close boundary is at or before ``cutoff``.

    The function does not drop the last list element by position and does not
    apply a history limit.  A last candle is retained when its close is at the
    cutoff, while an earlier forming/future candle is excluded by its actual
    close time.  OHLC, timestamp order and duplicate policies are intentionally
    deferred to task 19.
    """

    if not isinstance(cutoff, datetime):
        raise ValueError("cutoff must be a datetime")
    if cutoff.tzinfo is None or cutoff.utcoffset() is None:
        raise ValueError("cutoff must be timezone-aware")
    cutoff_utc = cutoff.astimezone(timezone.utc)
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")

    result: list[Candle] = []
    for candle in candles:
        if not isinstance(candle, Candle):
            raise ValueError("candles must contain Candle objects")
        if candle_close_at(candle.time, timeframe) <= cutoff_utc:
            result.append(candle)
    return tuple(result)


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
