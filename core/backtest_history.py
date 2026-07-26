"""Shared historical-data loading for Backtest and advanced research tools."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, MutableMapping

from core.market_models import Candle
from core.system_backtest_engine import BacktestRequest


BACKTEST_HISTORY_LOADER_VERSION = "backtest-history-loader-v1"


def load_backtest_history(
    provider: Any,
    request: BacktestRequest,
    *,
    cache: MutableMapping[
        tuple[str, str, str], dict[str, tuple[Any, ...]]
    ] | None = None,
    cache_limit: int = 8,
) -> dict[str, list[Candle]]:
    """Load the exact warm-up/data ranges used by the main Backtest flow."""

    cache_key = (
        request.broker_symbol,
        request.start.isoformat(),
        request.end.isoformat(),
    )
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return {
                timeframe: list(candles)
                for timeframe, candles in cached.items()
            }

    warmup_start = request.start - timedelta(days=520)
    ranges = {
        "D1": (warmup_start, request.end),
        "H4": (warmup_start, request.end),
        "H1": (warmup_start, request.end),
        "M15": (request.start - timedelta(days=90), request.end),
    }
    result: dict[str, list[Candle]] = {}
    for timeframe, (start, end) in ranges.items():
        if timeframe == "M15":
            result[timeframe] = load_m15_history(
                provider,
                request.broker_symbol,
                start,
                end,
            )
        else:
            result[timeframe] = provider.load_ohlcv_range(
                request.broker_symbol,
                timeframe,
                start,
                end,
            )

    if cache is None:
        return result
    cache[cache_key] = {
        timeframe: tuple(candles)
        for timeframe, candles in result.items()
    }
    while len(cache) > max(1, int(cache_limit)):
        cache.pop(next(iter(cache)))
    return {
        timeframe: list(candles)
        for timeframe, candles in cache[cache_key].items()
    }


def load_m15_history(
    provider: Any,
    broker_symbol: str,
    start: datetime,
    end: datetime,
    *,
    max_chunk_days: int = 180,
) -> list[Candle]:
    """Load M15 with the same fast path and chunk fallback everywhere."""

    try:
        candles = provider.load_ohlcv_range(
            broker_symbol,
            "M15",
            start,
            end,
        )
        if candles:
            return candles
    except RuntimeError:
        pass

    seen: set[int] = set()
    all_candles: list[Candle] = []
    chunk_start = start
    index = 0
    while chunk_start < end:
        chunk_end = min(
            chunk_start + timedelta(days=max(1, int(max_chunk_days))),
            end,
        )
        try:
            chunk = provider.load_ohlcv_range(
                broker_symbol,
                "M15",
                chunk_start,
                chunk_end,
                skip_select=(index > 0),
            )
        except TypeError:
            chunk = provider.load_ohlcv_range(
                broker_symbol,
                "M15",
                chunk_start,
                chunk_end,
            )
        except RuntimeError:
            chunk = []
        for candle in chunk or []:
            key = int(candle.time.timestamp())
            if key not in seen:
                seen.add(key)
                all_candles.append(candle)
        chunk_start = chunk_end
        index += 1
    return all_candles
