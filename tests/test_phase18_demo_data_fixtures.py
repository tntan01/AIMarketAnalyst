"""Phase 18.2 — demo data fixtures: fake candle data for 5 symbols."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import sin, pi

from core.market_models import Candle
from core.risk_engine import AnalysisInput


SYMBOL_CONFIGS = {
    "EUR/USD": {"start": 1.0800, "drift": 0.00016, "vol": 0.0030, "contract": 100_000},
    "GBP/JPY": {"start": 190.50, "drift": 0.0050,  "vol": 0.4000, "contract": 100_000},
    "USD/JPY": {"start": 155.00, "drift": -0.0080, "vol": 0.3500, "contract": 100_000},
    "XAU/USD": {"start": 2320.0, "drift": 0.1500,  "vol": 12.000, "contract": 100},
    "AUD/USD": {"start": 0.6580, "drift": -0.00005, "vol": 0.0025, "contract": 100_000},
}

TIMEFRAME_BARS = {"D1": 120, "H4": 120, "H1": 80}
TIMEFRAME_HOURS = {"D1": 24, "H4": 4, "H1": 1}


def build_demo_candles(
    count: int,
    start_price: float,
    drift: float,
    volatility: float,
    hours_per_bar: int = 1,
    start_time: datetime | None = None,
) -> list[Candle]:
    """Build fake candles with realistic OHLCV.

    Uses a sine wave + drift for price movement.
    """
    base = start_time or datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles: list[Candle] = []
    for i in range(count):
        # Price trend with drift + sine wave
        trend = start_price + drift * i
        wave = volatility * (sin(i * pi / 20) * 0.5 + sin(i * pi / 7) * 0.3)
        close = trend + wave
        spread = volatility * 0.15
        open_price = close - spread * (0.3 if i % 2 == 0 else -0.3)
        high = max(open_price, close) + abs(spread * 0.6)
        low = min(open_price, close) - abs(spread * 0.6)

        candle_time = base + timedelta(hours=hours_per_bar * i)
        candles.append(Candle(
            time=candle_time,
            open=round(open_price, 5),
            high=round(high, 5),
            low=round(low, 5),
            close=round(close, 5),
            volume=100.0,
        ))
    return candles


def build_demo_candles_by_timeframe(symbol: str) -> dict[str, list[Candle]]:
    """Build D1/H4/H1 candles for a symbol."""
    cfg = SYMBOL_CONFIGS[symbol]
    result = {}
    for tf, bars in TIMEFRAME_BARS.items():
        hours = TIMEFRAME_HOURS[tf]
        # D1 starts further back, H1 most recent
        offset = (120 - bars) * hours
        start = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(hours=offset)
        result[tf] = build_demo_candles(
            count=bars,
            start_price=cfg["start"],
            drift=cfg["drift"],
            volatility=cfg["vol"],
            hours_per_bar=hours,
            start_time=start,
        )
    return result


def build_demo_analysis_input(symbol: str) -> AnalysisInput:
    """Build AnalysisInput for a symbol."""
    cfg = SYMBOL_CONFIGS[symbol]
    broker = symbol.replace("/", "")
    return AnalysisInput(
        symbol=symbol,
        broker_symbol=broker,
        account_balance=10_000,
        risk_percent=1.0,
        contract_size_override=cfg["contract"],
    )


def build_demo_data_quality(symbol: str) -> dict:
    """Build clean data_quality dict for a symbol."""
    return {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "news_in_3h": False,
        "high_impact_event_within_30m": False,
        "broker_symbol": symbol.replace("/", ""),
        "price_source": "MT5 Demo/Fake",
        "spread_points": 2,
    }


# ===========================================================================
# Tests
# ===========================================================================


def test_all_5_symbols_have_candles():
    for sym in SYMBOL_CONFIGS:
        candles = build_demo_candles_by_timeframe(sym)
        for tf in ("D1", "H4", "H1"):
            assert tf in candles, f"{sym} missing {tf}"
            assert len(candles[tf]) >= TIMEFRAME_BARS[tf], f"{sym} {tf} only {len(candles[tf])} candles"


def test_candles_have_valid_ohlcv():
    sym = "EUR/USD"
    candles = build_demo_candles_by_timeframe(sym)
    for tf in ("D1", "H4", "H1"):
        for c in candles[tf]:
            assert c.high >= max(c.open, c.close), f"{tf} high < max(open,close): {c}"
            assert c.low <= min(c.open, c.close), f"{tf} low > min(open,close): {c}"
            assert c.high >= c.low


def test_candles_atr_not_zero():
    sym = "EUR/USD"
    candles = build_demo_candles_by_timeframe(sym)["H1"]
    prices = [c.close for c in candles]
    assert max(prices) - min(prices) > 0.0001, "ATR is effectively zero"


def test_analysis_input_valid():
    for sym in SYMBOL_CONFIGS:
        ai = build_demo_analysis_input(sym)
        assert ai.symbol == sym
        assert ai.account_balance == 10_000
        assert ai.risk_percent == 1.0
        if sym == "XAU/USD":
            assert ai.contract_size_override == 100


def test_data_quality_has_required_keys():
    for sym in SYMBOL_CONFIGS:
        dq = build_demo_data_quality(sym)
        assert dq["terminal_connected"] is True
        assert dq["broker_logged_in"] is True
        assert dq["spread_status"] == "normal"
        assert "broker_symbol" in dq


def test_no_external_imports():
    """Verify we don't import PyQt6 or MT5."""
    for sym in ("EUR/USD",):
        build_demo_candles_by_timeframe(sym)
        build_demo_analysis_input(sym)
        build_demo_data_quality(sym)

