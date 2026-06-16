from __future__ import annotations

from datetime import datetime, timedelta

from core.entry_engine import evaluate_entry
from core.market_models import Candle
from core.reason_codes import M15_DATA_UNAVAILABLE, ZONE_BROKEN


def _candle(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        time=datetime(2026, 6, 16) + timedelta(hours=index),
        open=open_,
        high=high,
        low=low,
        close=close,
    )


def _bullish_h1_confirmation() -> list[Candle]:
    return [
        _candle(0, 99.0, 100.0, 98.0, 99.5),
        _candle(1, 100.5, 101.0, 99.0, 100.0),
        _candle(2, 99.8, 102.0, 99.0, 101.5),
    ]


def _neutral_h1() -> list[Candle]:
    return [
        _candle(0, 99.0, 100.0, 98.0, 99.5),
        _candle(1, 99.5, 100.0, 98.5, 99.4),
        _candle(2, 99.4, 100.0, 98.5, 99.3),
    ]


def _buy_smc() -> dict:
    return {
        "H1": {
            "displacement": "bullish",
            "bos": True,
            "liquidity_sweeps": {"swept_lows": True},
        },
        "H4": {
            "displacement": "bullish",
            "bos": True,
            "premium_discount": "discount",
        },
    }


def test_entry_waits_when_h1_smc_confirm_but_m15_is_missing():
    result = evaluate_entry(
        side="buy",
        technical={"price": 100.5, "atr_h4": 2.0},
        smc=_buy_smc(),
        h1_candles=_bullish_h1_confirmation(),
        entry_zone=[100.0, 101.0],
        m15_candles=None,
    )

    assert result["entry_status"] == "waiting_confirmation"
    assert result["trigger_type"] == "h1_bullish_engulfing"
    assert result["price_in_entry_zone"] is True
    assert result["ready_to_trade"] is False
    assert M15_DATA_UNAVAILABLE in result["warning_codes"]


def test_entry_invalidates_when_price_breaks_zone():
    result = evaluate_entry(
        side="buy",
        technical={"price": 95.0, "atr_h4": 4.0},
        smc=_buy_smc(),
        h1_candles=_bullish_h1_confirmation(),
        entry_zone=[100.0, 101.0],
        m15_candles=None,
    )

    assert result["entry_status"] == "invalidated"
    assert result["trigger_type"] == "zone_broken"
    assert result["confirmation_score"] == 0
    assert ZONE_BROKEN in result["warning_codes"]


def test_entry_watch_zone_when_price_is_near_but_not_in_zone():
    result = evaluate_entry(
        side="buy",
        technical={"price": 102.5, "atr_h4": 4.0},
        smc={},
        h1_candles=_neutral_h1(),
        entry_zone=[100.0, 101.0],
        m15_candles=None,
    )

    assert result["entry_status"] == "watch_zone"
    assert result["price_in_entry_zone"] is False
    assert result["ready_to_trade"] is False


def test_entry_returns_no_setup_for_missing_price_atr_or_zone():
    result = evaluate_entry(
        side="buy",
        technical={"price": 0.0, "atr_h4": 0.0},
        smc={},
        h1_candles=[],
        entry_zone=[100.0],
        m15_candles=None,
    )

    assert result["entry_status"] == "no_setup"
    assert result["trigger_type"] == "none"
    assert result["confirmation_score"] == 0
