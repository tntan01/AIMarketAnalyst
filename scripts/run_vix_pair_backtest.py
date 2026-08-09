#!/usr/bin/env python3
"""Run the data-backed VIX/pair sensitivity validation.

The live scanner intentionally does not enable pair-aware VIX scoring merely
because this script produced a file.  Review the summary first, then enable
``vix_pair_aware_enabled`` manually in Advanced Settings.

Usage::

    python scripts/run_vix_pair_backtest.py
    python scripts/run_vix_pair_backtest.py --output data/vix_pair_sensitivity.json
    python scripts/run_vix_pair_backtest.py --symbols USD/JPY AUD/JPY AUD/USD
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence, TextIO


# Windows consoles may default to cp1252/cp1258; warnings contain Vietnamese.
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


# Make direct execution (``python scripts/...``) resolve project packages.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import SUPPORTED_SYMBOLS
from core.vix_pair_backtest import (
    DEFAULT_LOOKBACK_DAYS,
    MIN_LOOKBACK_DAYS,
    compute_vix_pair_sensitivity,
    is_sensitivity_map_eligible,
    save_sensitivity_map,
)
from services.macro_market_cache import MacroMarketCache
from services.market_data_service import parse_yf_candles


DEFAULT_PERIOD = "2y"
DEFAULT_INTERVAL = "1d"
DEFAULT_MAX_WORKERS = 8
VIX_TICKER = "^VIX"

SPECIAL_YAHOO_TICKERS: dict[str, str] = {
    "XAU/USD": "GC=F",
    "XAG/USD": "SI=F",
    "BTC/USD": "BTC-USD",
}


@dataclass(frozen=True, slots=True)
class BacktestRun:
    """Outcome returned by :func:`run_vix_pair_backtest`."""

    result: dict[str, Any]
    saved_path: Path | None
    valid_pairs: tuple[str, ...]
    fetch_errors: dict[str, str]

    @property
    def succeeded(self) -> bool:
        return self.saved_path is not None


def yahoo_ticker_for_symbol(symbol: str) -> str:
    """Translate an application symbol into its Yahoo Finance ticker."""

    normalized = str(symbol).strip().upper()
    special = SPECIAL_YAHOO_TICKERS.get(normalized)
    if special is not None:
        return special

    parts = normalized.split("/")
    if len(parts) != 2 or not all(len(part) == 3 for part in parts):
        raise ValueError(f"Unsupported symbol format: {symbol!r}")
    return f"{parts[0]}{parts[1]}=X"


def _normalize_symbols(symbols: Sequence[str] | None) -> list[str]:
    requested = list(SUPPORTED_SYMBOLS if symbols is None else symbols)
    supported = set(SUPPORTED_SYMBOLS)
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in requested:
        symbol = str(raw).strip().upper()
        if symbol not in supported:
            raise ValueError(f"Unsupported symbol: {raw!r}")
        if symbol not in seen:
            normalized.append(symbol)
            seen.add(symbol)
    if not normalized:
        raise ValueError("At least one supported symbol is required")
    return normalized


def _fetch_candles(
    cache: Any,
    ticker: str,
    *,
    period: str,
    interval: str,
    force_refresh: bool,
) -> tuple[list[Any] | None, str | None]:
    try:
        frame = cache.get_frame(
            ticker,
            period=period,
            interval=interval,
            force_refresh=force_refresh,
        )
        candles = parse_yf_candles(frame)
    except Exception as exc:  # one missing pair must not abort all other pairs
        return None, f"{type(exc).__name__}: {exc}"
    if not candles:
        return None, "empty or unparseable Yahoo response"
    return candles, None


def _fetch_pair_histories(
    cache: Any,
    symbols: Sequence[str],
    *,
    period: str,
    interval: str,
    force_refresh: bool,
    max_workers: int,
) -> tuple[dict[str, list[Any]], dict[str, str]]:
    histories: dict[str, list[Any]] = {}
    errors: dict[str, str] = {}
    workers = min(max_workers, len(symbols))

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for symbol in symbols:
            ticker = yahoo_ticker_for_symbol(symbol)
            future = executor.submit(
                _fetch_candles,
                cache,
                ticker,
                period=period,
                interval=interval,
                force_refresh=force_refresh,
            )
            futures[future] = (symbol, ticker)

        for future in as_completed(futures):
            symbol, ticker = futures[future]
            candles, error = future.result()
            if candles is not None:
                histories[symbol] = candles
            else:
                errors[symbol] = f"{ticker}: {error or 'unknown fetch error'}"

    return histories, errors


def _data_points(pair_data: object) -> int:
    if not isinstance(pair_data, dict):
        return 0
    try:
        return int(pair_data.get("data_points", 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def validate_backtest_result(
    result: dict[str, Any],
    *,
    requested_symbols: Sequence[str],
) -> tuple[bool, tuple[str, ...]]:
    """Mark a successful engine result as validated only when data supports it.

    The computation engine also returns structured ``insufficient_data``
    results.  Those must never overwrite the last usable runtime mapping.
    Neutral correlations are valid observations; only missing/undersized
    samples are rejected here.
    """

    meta = result.get("meta")
    pairs = result.get("pairs")
    if not isinstance(meta, dict) or not isinstance(pairs, dict):
        return False, ()

    engine_status = str(meta.get("status", "")).strip().lower()
    if engine_status != "validated":
        return False, ()
    if meta.get("error"):
        return False, ()

    minimum_points = max(3, MIN_LOOKBACK_DAYS)
    valid_pairs = tuple(
        symbol
        for symbol in requested_symbols
        if _data_points(pairs.get(symbol)) >= minimum_points
    )
    if not valid_pairs:
        meta["status"] = "insufficient_data"
        meta.setdefault(
            "error",
            f"No pair has the required {minimum_points} aligned observations",
        )
        return False, ()

    actionable_pairs = tuple(
        symbol
        for symbol in valid_pairs
        if isinstance(pairs.get(symbol), dict)
        and pairs[symbol].get("actionable") is True
    )
    if not actionable_pairs:
        meta["status"] = "hypothesis_not_confirmed"
        meta["actionable_pair_count"] = 0
        meta.setdefault(
            "error",
            "No pair passed both the effect-size and significance gates",
        )
        return False, valid_pairs

    meta.update(
        {
            "status": "validated",
            "is_seed": False,
            "requested_pair_count": len(requested_symbols),
            "validated_pair_count": len(valid_pairs),
            "failed_pair_count": len(requested_symbols) - len(valid_pairs),
            "actionable_pair_count": len(actionable_pairs),
        }
    )
    if not is_sensitivity_map_eligible(result):
        meta["status"] = "ineligible"
        meta.setdefault("error", "Result failed the runtime eligibility contract")
        return False, valid_pairs
    return True, valid_pairs


def _format_float(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError, OverflowError):
        return "n/a"


def print_summary(
    result: dict[str, Any],
    *,
    symbols: Sequence[str],
    valid_pairs: Sequence[str],
    fetch_errors: dict[str, str],
    stream: TextIO,
) -> None:
    """Print a compact review table without changing scoring state."""

    pairs = result.get("pairs") if isinstance(result.get("pairs"), dict) else {}
    valid = set(valid_pairs)
    print("", file=stream)
    print("VIX pair sensitivity backtest", file=stream)
    print(
        f"{'PAIR':<9} {'YAHOO':<11} {'CORR':>7} {'P-VALUE':>8} "
        f"{'SIG':>3} {'FACTOR':>7} {'N':>5} {'DIRECTION':<20} STATUS",
        file=stream,
    )
    print("-" * 94, file=stream)
    for symbol in symbols:
        pair_data = pairs.get(symbol, {}) if isinstance(pairs, dict) else {}
        direction = (
            str(pair_data.get("vix_direction", "unknown"))
            if isinstance(pair_data, dict)
            else "unknown"
        )
        if symbol in valid:
            status = "VALID"
        elif symbol in fetch_errors:
            status = "FETCH_FAILED"
        else:
            status = "INSUFFICIENT"
        significant = (
            "Y" if isinstance(pair_data, dict)
            and pair_data.get("statistically_significant") is True else "N"
        )
        print(
            f"{symbol:<9} {yahoo_ticker_for_symbol(symbol):<11} "
            f"{_format_float(pair_data.get('correlation') if isinstance(pair_data, dict) else None):>7} "
            f"{_format_float(pair_data.get('p_value') if isinstance(pair_data, dict) else None, 4):>8} "
            f"{significant:>3} "
            f"{_format_float(pair_data.get('sensitivity_factor') if isinstance(pair_data, dict) else None, 2):>7} "
            f"{_data_points(pair_data):>5} {direction:<20.20} {status}",
            file=stream,
        )

    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        print("", file=stream)
        print("Warnings:", file=stream)
        for warning in warnings:
            print(f"- {warning}", file=stream)


def run_vix_pair_backtest(
    *,
    symbols: Sequence[str] | None = None,
    period: str = DEFAULT_PERIOD,
    interval: str = DEFAULT_INTERVAL,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    output_path: Path | None = None,
    cache: Any | None = None,
    downloader: Callable[..., Any] | None = None,
    force_refresh: bool = True,
    max_workers: int = DEFAULT_MAX_WORKERS,
    stream: TextIO | None = None,
) -> BacktestRun:
    """Fetch, compute, validate, optionally save, and print one backtest run."""

    if cache is not None and downloader is not None:
        raise ValueError("Pass either cache or downloader, not both")
    if not period.strip():
        raise ValueError("period must not be empty")
    if lookback_days < MIN_LOOKBACK_DAYS:
        raise ValueError(
            f"lookback_days must be >= MIN_LOOKBACK_DAYS ({MIN_LOOKBACK_DAYS})"
        )
    if max_workers < 1:
        raise ValueError("max_workers must be >= 1")

    selected_symbols = _normalize_symbols(symbols)
    output = stream or sys.stdout
    market_cache = (
        cache if cache is not None else MacroMarketCache(downloader=downloader)
    )

    print(
        f"Fetching {VIX_TICKER} and {len(selected_symbols)} pairs "
        f"(period={period}, interval={interval}, lookback={lookback_days})...",
        file=output,
    )
    vix_candles, vix_error = _fetch_candles(
        market_cache,
        VIX_TICKER,
        period=period,
        interval=interval,
        force_refresh=force_refresh,
    )
    if vix_candles is None:
        result: dict[str, Any] = {
            "meta": {
                "status": "insufficient_data",
                "lookback_days": lookback_days,
                "error": f"Unable to fetch VIX history: {vix_error}",
            },
            "pairs": {},
            "warnings": [f"{VIX_TICKER}: {vix_error}"],
        }
        print_summary(
            result,
            symbols=selected_symbols,
            valid_pairs=(),
            fetch_errors={symbol: "VIX unavailable" for symbol in selected_symbols},
            stream=output,
        )
        print("", file=output)
        print("NOT SAVED: VIX history is unavailable or insufficient.", file=output)
        return BacktestRun(result, None, (), {VIX_TICKER: vix_error or "unknown"})

    pair_histories, fetch_errors = _fetch_pair_histories(
        market_cache,
        selected_symbols,
        period=period,
        interval=interval,
        force_refresh=force_refresh,
        max_workers=max_workers,
    )
    result = compute_vix_pair_sensitivity(
        vix_candles,
        pair_histories,
        lookback_days=lookback_days,
    )
    result_meta = result.get("meta")
    if isinstance(result_meta, dict):
        result_meta.update({
            "data_provider": "Yahoo Finance via yfinance",
            "fetch_period": period,
            "fetch_interval": interval,
            "vix_ticker": VIX_TICKER,
            "pair_ticker_convention": (
                "FX=BASEQUOTE=X; XAU/USD=GC=F; XAG/USD=SI=F; "
                "BTC/USD=BTC-USD"
            ),
        })
    result_warnings = result.setdefault("warnings", [])
    if not isinstance(result_warnings, list):
        result_warnings = []
        result["warnings"] = result_warnings
    for symbol in selected_symbols:
        if symbol in fetch_errors:
            result_warnings.append(f"{symbol}: {fetch_errors[symbol]}")

    validated, valid_pairs = validate_backtest_result(
        result,
        requested_symbols=selected_symbols,
    )
    print_summary(
        result,
        symbols=selected_symbols,
        valid_pairs=valid_pairs,
        fetch_errors=fetch_errors,
        stream=output,
    )

    saved_path: Path | None = None
    print("", file=output)
    if validated:
        saved_path = save_sensitivity_map(result, output_path)
        print(f"Saved validated map: {saved_path}", file=output)
        print(
            "Review the correlations and sample coverage first. The runner does "
            "not enable scoring automatically; enable vix_pair_aware_enabled "
            "manually in Advanced Settings only after approval.",
            file=output,
        )
    else:
        print(
            "NOT SAVED: the result is not validated or no pair has enough data. "
            "The previous map, if any, was left untouched.",
            file=output,
        )

    return BacktestRun(result, saved_path, valid_pairs, fetch_errors)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Backtest daily VIX changes against returns for supported pairs.",
    )
    parser.add_argument("--period", default=DEFAULT_PERIOD, help="Yahoo range (default: 2y)")
    parser.add_argument(
        "--lookback",
        type=int,
        default=DEFAULT_LOOKBACK_DAYS,
        help="Trading-day lookback used by the engine (default: 252)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Destination JSON. Default is the application's data directory.",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        choices=SUPPORTED_SYMBOLS,
        default=None,
        help="Optional subset. Default: all 31 supported symbols.",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help="Maximum concurrent Yahoo requests (default: 8)",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Allow a TTL-valid cached frame instead of forcing refresh.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        run = run_vix_pair_backtest(
            symbols=args.symbols,
            period=args.period,
            lookback_days=args.lookback,
            output_path=args.output,
            force_refresh=not args.use_cache,
            max_workers=args.max_workers,
        )
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0 if run.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
