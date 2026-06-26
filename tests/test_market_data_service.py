from __future__ import annotations

from datetime import datetime

import pandas as pd

from core.market_models import Candle
from core.system_backtest_engine import BacktestRequest, _request_to_dict
from services.market_data_service import (
    fetch_macro_correlation_context,
    latest_change,
    parse_yf_candles,
    serialize_correlation_context,
)


def _sample_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [102.0, 103.0],
            "Low": [99.0, 100.0],
            "Close": [101.0, 102.0],
            "Volume": [10, 20],
        },
        index=pd.to_datetime(["2026-06-15", "2026-06-16"]),
    )


def test_parse_yf_candles_from_regular_dataframe():
    candles = parse_yf_candles(_sample_frame())

    assert candles is not None
    assert len(candles) == 2
    assert candles[-1].time == datetime(2026, 6, 16)
    assert candles[-1].open == 101.0
    assert candles[-1].high == 103.0
    assert candles[-1].low == 100.0
    assert candles[-1].close == 102.0
    assert candles[-1].volume == 20.0


def test_parse_yf_candles_from_yfinance_multiindex_dataframe():
    ticker = "DX-Y.NYB"
    columns = pd.MultiIndex.from_product(
        [["Open", "High", "Low", "Close", "Volume"], [ticker]],
    )
    frame = pd.DataFrame(
        [
            [100.0, 102.0, 99.0, 101.0, 10],
            [101.0, 103.0, 100.0, 102.0, 20],
        ],
        columns=columns,
        index=pd.to_datetime(["2026-06-15", "2026-06-16"]),
    )

    candles = parse_yf_candles(frame)

    assert candles is not None
    assert [c.close for c in candles] == [101.0, 102.0]
    assert [c.volume for c in candles] == [10.0, 20.0]


def test_latest_change_uses_last_two_candles():
    candles = parse_yf_candles(_sample_frame())

    assert latest_change(candles) == (102.0, 0.9900990099009901)


def test_fetch_macro_correlation_context_uses_downloader_and_candles():
    calls: list[str] = []

    def fake_download(ticker: str, **_kwargs):
        calls.append(ticker)
        return _sample_frame()

    context = fetch_macro_correlation_context(downloader=fake_download)

    assert set(calls) == {"DX-Y.NYB", "^VIX", "^TNX", "2YY=F"}
    assert context["dxy_candles"] is not None
    assert context["us2y_candles"] is not None
    assert context["vix_candles"] is not None
    assert context["us10y_candles"] is not None
    assert context["dxy_candles"][-1].close == 102.0


def test_serialize_correlation_context_converts_candles_to_dicts():
    candle = Candle(
        time=datetime(2026, 6, 16),
        open=1.0,
        high=2.0,
        low=0.5,
        close=1.5,
        volume=100.0,
    )

    result = serialize_correlation_context({"dxy_candles": [candle]})

    assert result == {
        "dxy_candles": [
            {
                "time": "2026-06-16T00:00:00",
                "open": 1.0,
                "high": 2.0,
                "low": 0.5,
                "close": 1.5,
                "volume": 100.0,
            }
        ]
    }


def test_backtest_request_serializes_candle_correlation_context():
    request = BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2026, 6, 15),
        end=datetime(2026, 6, 16),
        initial_balance=10000.0,
        risk_percent=1.0,
        correlation_context={
            "dxy_candles": [
                Candle(
                    time=datetime(2026, 6, 16),
                    open=1.0,
                    high=2.0,
                    low=0.5,
                    close=1.5,
                )
            ]
        },
    )

    result = _request_to_dict(request)

    assert result["correlation_context"]["dxy_candles"][0]["time"] == "2026-06-16T00:00:00"
    assert result["correlation_context"]["dxy_candles"][0]["close"] == 1.5
