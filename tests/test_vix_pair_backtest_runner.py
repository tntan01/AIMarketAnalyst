from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

import pandas as pd

from config.constants import SUPPORTED_SYMBOLS
from scripts.run_vix_pair_backtest import (
    DEFAULT_INTERVAL,
    DEFAULT_PERIOD,
    SPECIAL_YAHOO_TICKERS,
    VIX_TICKER,
    _build_parser,
    run_vix_pair_backtest,
    validate_backtest_result,
    yahoo_ticker_for_symbol,
)


def _history_frame(*, inverse: bool = False, periods: int = 270) -> pd.DataFrame:
    dates = pd.bdate_range("2024-01-02", periods=periods)
    close = 20.0 if not inverse else 150.0
    closes: list[float] = []
    pattern = (0.018, -0.011, 0.007, -0.004, 0.013, -0.009)
    for index in range(periods):
        change = pattern[index % len(pattern)]
        if inverse:
            change *= -0.45
        close *= 1.0 + change
        closes.append(close)
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [value * 1.001 for value in closes],
            "Low": [value * 0.999 for value in closes],
            "Close": closes,
            "Volume": [1000.0] * periods,
        },
        index=dates,
    )


class _FakeCache:
    def __init__(self, frames: dict[str, pd.DataFrame | Exception]) -> None:
        self.frames = frames
        self.calls: list[tuple[str, str, str, bool]] = []

    def get_frame(
        self,
        ticker: str,
        *,
        period: str,
        interval: str,
        force_refresh: bool,
    ) -> pd.DataFrame:
        self.calls.append((ticker, period, interval, force_refresh))
        value = self.frames[ticker]
        if isinstance(value, Exception):
            raise value
        return value.copy()


def test_ticker_mapping_covers_all_supported_symbols() -> None:
    assert len(SUPPORTED_SYMBOLS) == 31
    assert yahoo_ticker_for_symbol("EUR/USD") == "EURUSD=X"
    assert yahoo_ticker_for_symbol("USD/JPY") == "USDJPY=X"
    assert yahoo_ticker_for_symbol("XAU/USD") == "GC=F"
    assert yahoo_ticker_for_symbol("XAG/USD") == "SI=F"
    assert yahoo_ticker_for_symbol("BTC/USD") == "BTC-USD"
    assert set(SPECIAL_YAHOO_TICKERS) <= set(SUPPORTED_SYMBOLS)
    assert all(yahoo_ticker_for_symbol(symbol) for symbol in SUPPORTED_SYMBOLS)


def test_parser_defaults_to_two_years_252_days_and_all_symbols() -> None:
    args = _build_parser().parse_args([])
    assert args.period == "2y"
    assert args.lookback == 252
    assert args.symbols is None


def test_runner_uses_macro_market_cache_with_injected_downloader(
    tmp_path: Path,
) -> None:
    calls: list[tuple[str, str, str]] = []
    vix = _history_frame()
    pair = _history_frame(inverse=True)

    def downloader(ticker: str, *, period: str, interval: str):
        calls.append((ticker, period, interval))
        return vix.copy() if ticker == VIX_TICKER else pair.copy()

    output_path = tmp_path / "validated.json"
    stream = StringIO()
    run = run_vix_pair_backtest(
        symbols=["USD/JPY", "AUD/USD"],
        downloader=downloader,
        output_path=output_path,
        max_workers=1,
        stream=stream,
    )

    assert run.succeeded is True
    assert output_path.exists()
    assert calls == [
        (VIX_TICKER, DEFAULT_PERIOD, DEFAULT_INTERVAL),
        ("USDJPY=X", DEFAULT_PERIOD, DEFAULT_INTERVAL),
        ("AUDUSD=X", DEFAULT_PERIOD, DEFAULT_INTERVAL),
    ]
    saved = json.loads(output_path.read_text("utf-8"))
    assert saved["meta"]["status"] == "validated"
    assert saved["meta"]["is_seed"] is False
    assert saved["meta"]["lookback_days"] == 252
    assert saved["meta"]["validated_pair_count"] == 2
    assert set(saved["pairs"]) == {"USD/JPY", "AUD/USD"}
    assert "enable vix_pair_aware_enabled manually" in stream.getvalue()


def test_runner_accepts_fake_cache_and_passes_fetch_options(tmp_path: Path) -> None:
    cache = _FakeCache(
        {
            VIX_TICKER: _history_frame(),
            "USDJPY=X": _history_frame(inverse=True),
        }
    )
    run = run_vix_pair_backtest(
        symbols=["USD/JPY"],
        period="2y",
        lookback_days=252,
        output_path=tmp_path / "map.json",
        cache=cache,
        force_refresh=False,
        max_workers=1,
        stream=StringIO(),
    )

    assert run.succeeded is True
    assert cache.calls == [
        (VIX_TICKER, "2y", "1d", False),
        ("USDJPY=X", "2y", "1d", False),
    ]


def test_unavailable_vix_does_not_fetch_pairs_or_overwrite_file(
    tmp_path: Path,
) -> None:
    destination = tmp_path / "existing.json"
    destination.write_text('{"sentinel": true}', "utf-8")
    cache = _FakeCache({VIX_TICKER: RuntimeError("offline")})
    stream = StringIO()

    run = run_vix_pair_backtest(
        symbols=["USD/JPY"],
        cache=cache,
        output_path=destination,
        stream=stream,
    )

    assert run.succeeded is False
    assert run.result["meta"]["status"] == "insufficient_data"
    assert destination.read_text("utf-8") == '{"sentinel": true}'
    assert cache.calls == [(VIX_TICKER, "2y", "1d", True)]
    assert "NOT SAVED" in stream.getvalue()


def test_no_pair_with_enough_data_does_not_overwrite_file(tmp_path: Path) -> None:
    destination = tmp_path / "existing.json"
    destination.write_text('{"sentinel": true}', "utf-8")
    cache = _FakeCache(
        {
            VIX_TICKER: _history_frame(),
            "USDJPY=X": _history_frame(inverse=True, periods=5),
        }
    )

    run = run_vix_pair_backtest(
        symbols=["USD/JPY"],
        cache=cache,
        output_path=destination,
        max_workers=1,
        stream=StringIO(),
    )

    assert run.succeeded is False
    assert run.result["meta"]["status"] == "insufficient_data"
    assert run.valid_pairs == ()
    assert destination.read_text("utf-8") == '{"sentinel": true}'


def test_partial_fetch_failure_saves_only_data_backed_pairs(tmp_path: Path) -> None:
    cache = _FakeCache(
        {
            VIX_TICKER: _history_frame(),
            "USDJPY=X": _history_frame(inverse=True),
            "AUDUSD=X": RuntimeError("rate limited"),
        }
    )
    destination = tmp_path / "partial.json"
    stream = StringIO()

    run = run_vix_pair_backtest(
        symbols=["USD/JPY", "AUD/USD"],
        cache=cache,
        output_path=destination,
        max_workers=1,
        stream=stream,
    )

    assert run.succeeded is True
    assert run.valid_pairs == ("USD/JPY",)
    assert "AUD/USD" in run.fetch_errors
    saved = json.loads(destination.read_text("utf-8"))
    assert saved["meta"]["requested_pair_count"] == 2
    assert saved["meta"]["validated_pair_count"] == 1
    assert saved["meta"]["failed_pair_count"] == 1
    assert set(saved["pairs"]) == {"USD/JPY"}
    assert "FETCH_FAILED" in stream.getvalue()


def test_validate_rejects_engine_error_even_if_pairs_are_present() -> None:
    result = {
        "meta": {"status": "insufficient_data", "error": "bad VIX"},
        "pairs": {"USD/JPY": {"data_points": 251}},
    }
    accepted, pairs = validate_backtest_result(
        result,
        requested_symbols=["USD/JPY"],
    )
    assert accepted is False
    assert pairs == ()


def test_validate_requires_explicit_validated_engine_status() -> None:
    result = {
        "meta": {},
        "pairs": {"USD/JPY": {"data_points": 251}},
    }
    accepted, pairs = validate_backtest_result(
        result,
        requested_symbols=["USD/JPY"],
    )
    assert accepted is False
    assert pairs == ()


def test_summary_contains_review_table_and_manual_enable_warning(
    tmp_path: Path,
) -> None:
    cache = _FakeCache(
        {
            VIX_TICKER: _history_frame(),
            "USDJPY=X": _history_frame(inverse=True),
        }
    )
    stream = StringIO()
    run_vix_pair_backtest(
        symbols=["USD/JPY"],
        cache=cache,
        output_path=tmp_path / "map.json",
        max_workers=1,
        stream=stream,
    )

    output = stream.getvalue()
    assert "PAIR" in output
    assert "YAHOO" in output
    assert "CORR" in output
    assert "P-VALUE" in output
    assert "SIG" in output
    assert "USD/JPY" in output
    assert "VALID" in output
    assert "does not enable scoring automatically" in output
