from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Any

import requests

from core.market_models import Candle


MARKET_TICKERS: dict[str, str] = {
    "DXY": "DX-Y.NYB",
    "VIX": "^VIX",
    "US10Y": "^TNX",
}

_CORRELATION_KEYS: dict[str, str] = {
    "DXY": "dxy_candles",
    "VIX": "vix_candles",
    "US10Y": "us10y_candles",
}

_CORRELATION_CACHE: dict[str, Any] | None = None
_CORRELATION_CACHE_TIME: datetime | None = None
_CORRELATION_CACHE_TTL = timedelta(minutes=15)


def parse_yf_candles(data: Any) -> list[Candle] | None:
    """Parse a yfinance DataFrame into Candle objects."""
    if data is None or bool(getattr(data, "empty", True)):
        return None

    candles: list[Candle] = []
    try:
        rows = data.iterrows()
    except AttributeError:
        return None

    for idx, row in rows:
        try:
            candles.append(
                Candle(
                    time=_coerce_time(idx),
                    open=float(_row_scalar(row, "Open")),
                    high=float(_row_scalar(row, "High")),
                    low=float(_row_scalar(row, "Low")),
                    close=float(_row_scalar(row, "Close")),
                    volume=float(_row_scalar(row, "Volume", default=0.0)),
                )
            )
        except (KeyError, TypeError, ValueError, OverflowError, AttributeError):
            continue

    return candles or None


def fetch_macro_correlation_context(
    *,
    period: str = "5d",
    interval: str = "1d",
    downloader: Any | None = None,
    force_refresh: bool = False,
) -> dict[str, list[Candle] | None]:
    """Fetch DXY/VIX/US10Y candles for correlation checks.

    Results are cached for _CORRELATION_CACHE_TTL (15 min) to avoid
    redundant yfinance downloads on repeated scans.
    """
    global _CORRELATION_CACHE, _CORRELATION_CACHE_TIME

    now = datetime.now()
    if (
        not force_refresh
        and _CORRELATION_CACHE is not None
        and _CORRELATION_CACHE_TIME is not None
        and now - _CORRELATION_CACHE_TIME < _CORRELATION_CACHE_TTL
    ):
        return _CORRELATION_CACHE

    context: dict[str, list[Candle] | None] = {
        "dxy_candles": None,
        "vix_candles": None,
        "us10y_candles": None,
    }
    download = downloader or _yf_download

    with ThreadPoolExecutor(max_workers=len(MARKET_TICKERS)) as ex:
        futures = {
            ex.submit(download, ticker, period=period, interval=interval, progress=False): tag
            for tag, ticker in MARKET_TICKERS.items()
        }
        for future in as_completed(futures):
            tag = futures[future]
            try:
                context[_CORRELATION_KEYS[tag]] = parse_yf_candles(future.result())
            except Exception:
                pass

    _CORRELATION_CACHE = context
    _CORRELATION_CACHE_TIME = now
    return context


def latest_change(candles: list[Candle] | None) -> tuple[float, float] | None:
    """Return ``(latest_close, percent_change)`` from the last two candles."""
    if not candles or len(candles) < 2:
        return None
    close = float(candles[-1].close)
    prev = float(candles[-2].close)
    change_pct = (close - prev) / prev * 100 if prev != 0 else 0.0
    return close, change_pct


def fetch_market_overview(
    *,
    period: str = "5d",
    interval: str = "1d",
    downloader: Any | None = None,
) -> dict[str, tuple[float, float]]:
    """Fetch dashboard market overview values keyed by DXY/VIX/US10Y."""
    context = fetch_macro_correlation_context(
        period=period,
        interval=interval,
        downloader=downloader,
    )
    overview: dict[str, tuple[float, float]] = {}
    for tag, context_key in _CORRELATION_KEYS.items():
        change = latest_change(context.get(context_key))
        if change is not None:
            overview[tag] = change

    if len(overview) == len(MARKET_TICKERS):
        return overview

    fallback = fetch_market_overview_from_yahoo_chart(skip_tags=set(overview))
    overview.update(fallback)
    return overview


def fetch_market_overview_from_yahoo_chart(
    *,
    skip_tags: set[str] | None = None,
    timeout: int = 10,
) -> dict[str, tuple[float, float]]:
    """Fallback dashboard fetch using Yahoo chart HTTP endpoint."""
    skip = skip_tags or set()
    overview: dict[str, tuple[float, float]] = {}
    headers = {"User-Agent": "Mozilla/5.0"}

    for tag, ticker in MARKET_TICKERS.items():
        if tag in skip:
            continue
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=5d&interval=1d"
            resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 429:
                import time

                time.sleep(2)
                resp = requests.get(url, headers=headers, timeout=timeout)
            if resp.status_code != 200:
                continue
            json_data = resp.json()
            result = json_data.get("chart", {}).get("result", [])
            if not result:
                continue
            quotes = result[0].get("indicators", {}).get("quote", [])
            if not quotes:
                continue
            closes = [float(c) for c in quotes[0].get("close", []) if c is not None]
            if len(closes) < 2:
                continue
            close = closes[-1]
            prev = closes[-2]
            overview[tag] = (close, (close - prev) / prev * 100 if prev != 0 else 0.0)
        except Exception:
            pass

    return overview


def candle_to_dict(candle: Candle) -> dict[str, Any]:
    return {
        "time": candle.time.isoformat(),
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


def serialize_correlation_context(value: object) -> object:
    """Convert Candle values inside correlation context to JSON-safe dicts."""
    if not isinstance(value, dict):
        return value
    result: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, list):
            result[key] = [candle_to_dict(c) if isinstance(c, Candle) else c for c in item]
        else:
            result[key] = item
    return result


def _yf_download(*args: Any, **kwargs: Any) -> Any:
    import yfinance as yf

    return yf.download(*args, **kwargs)


def _row_scalar(row: Any, column: str, *, default: float | None = None) -> Any:
    try:
        value = row[column]
    except KeyError:
        value = _multiindex_scalar(row, column, default=default)
    if hasattr(value, "iloc"):
        return value.iloc[0]
    return value


def _multiindex_scalar(row: Any, column: str, *, default: float | None = None) -> Any:
    index = getattr(row, "index", [])
    for key in index:
        if isinstance(key, tuple) and column in key:
            return row[key]
    if default is not None:
        return default
    raise KeyError(column)


def _coerce_time(value: Any) -> datetime:
    if hasattr(value, "to_pydatetime"):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
