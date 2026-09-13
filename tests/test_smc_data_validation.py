from datetime import datetime, timezone
import math

import pytest

from core.market_models import (
    Candle,
    SmcCandleDataError,
    require_valid_smc_candles,
    validate_smc_candles,
)


def candle(
    minute: int,
    *,
    open_price: float = 100.0,
    high: float = 101.0,
    low: float = 99.0,
    close: float = 100.5,
) -> Candle:
    return Candle(
        time=datetime(2026, 1, 1, 0, minute, tzinfo=timezone.utc),
        open=open_price,
        high=high,
        low=low,
        close=close,
    )


def reason_codes(issues):
    return [issue.code for issue in issues]


def test_valid_candles_have_no_validation_reasons_and_are_not_rewritten():
    candles = (candle(0), candle(15, open_price=100.5, close=100.25))

    assert validate_smc_candles(candles, "M15") == ()
    assert require_valid_smc_candles(candles, "M15") == candles


@pytest.mark.parametrize(
    "kwargs",
    [
        {"high": 100.0},
        {"low": 100.5},
        {"high": 98.0, "low": 99.0},
        {"high": math.inf},
        {"low": math.nan},
    ],
)
def test_invalid_ohlc_returns_reason_and_keeps_original_record(kwargs):
    original = candle(0, **kwargs)
    issues = validate_smc_candles((original,), "H1")

    assert reason_codes(issues) == ["SMC_OHLC_INVALID"]
    assert original == candle(0, **kwargs)


def test_naive_timestamp_returns_timestamp_reason():
    invalid = Candle(
        time=datetime(2026, 1, 1, 0, 0),
        open=100.0,
        high=101.0,
        low=99.0,
        close=100.5,
    )

    issues = validate_smc_candles((invalid,), "D1")

    assert reason_codes(issues) == ["SMC_TIMESTAMP_INVALID"]


def test_decreasing_timestamp_is_an_order_error():
    issues = validate_smc_candles((candle(15), candle(0)), "M15")

    assert reason_codes(issues) == ["SMC_TIMESTAMP_ORDER_INVALID"]
    assert issues[0].detail == "timestamp is not strictly increasing"


def test_duplicate_timestamp_is_an_order_error_and_not_deduplicated():
    duplicate = candle(0, high=103.0, close=102.0)
    issues = validate_smc_candles((candle(0), duplicate), "M15")

    assert reason_codes(issues) == ["SMC_TIMESTAMP_ORDER_INVALID"]
    assert issues[0].detail == "duplicate open time"
    assert duplicate.close == 102.0


def test_require_wrapper_exposes_all_reasons_without_repairing_input():
    invalid = candle(0, high=98.0)
    duplicate = candle(0, high=103.0, close=102.0)

    with pytest.raises(SmcCandleDataError) as raised:
        require_valid_smc_candles((invalid, duplicate), "M15")

    error = raised.value
    assert error.reason_codes == ("SMC_OHLC_INVALID", "SMC_TIMESTAMP_ORDER_INVALID")
    assert [issue.to_dict()["code"] for issue in error.issues] == [
        "SMC_OHLC_INVALID",
        "SMC_TIMESTAMP_ORDER_INVALID",
    ]
    assert invalid.high == 98.0
    assert duplicate.close == 102.0


def test_unsupported_timeframe_is_a_contract_error():
    with pytest.raises(ValueError, match="Unsupported SMC timeframe"):
        validate_smc_candles((candle(0),), "M5")
