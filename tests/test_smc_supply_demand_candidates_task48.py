"""Task 48 tests for compressed supply/demand base candidates."""

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.smc_context import (
    detect_supply_demand_candidates,
    measure_supply_demand_base,
)


def _candles(rows):
    start = datetime(2026, 9, 11, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=100,
        )
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def test_compressed_base_uses_candle_count_and_predeparture_average():
    base = _candles([
        (100, 100.4, 99.8, 100.1),
        (100.1, 100.5, 99.9, 100.2),
        (100.2, 100.3, 99.9, 100.0),
    ])
    result = measure_supply_demand_base(
        base,
        average_range=0.6,
        consolidation_bars=3,
    )

    assert result["accepted"] is True
    assert result["base_low"] == 99.8
    assert result["base_high"] == 100.5
    assert result["base_range"] == pytest.approx(0.7)
    assert result["compression_limit"] == pytest.approx(1.2)


def test_wide_base_is_rejected_with_explicit_reason():
    base = _candles([
        (100, 102, 99, 101),
        (101, 102, 99, 100),
        (100, 102, 99, 101),
    ])
    result = measure_supply_demand_base(
        base,
        average_range=1.0,
        consolidation_bars=3,
    )
    assert result["accepted"] is False
    assert result["reason_codes"] == ["SD_COMPRESSION_TOO_WIDE"]


def test_supply_demand_candidates_store_full_base_and_remain_unconfirmed():
    candles = _candles([
        (100, 100.4, 99.8, 100.1),
        (100.1, 100.5, 99.9, 100.2),
        (100.2, 100.3, 99.9, 100.0),
        (100.0, 102.0, 100.0, 101.8),  # departure, confirmation is Task 49
    ])
    candidates = detect_supply_demand_candidates(
        candles,
        symbol="EUR/USD",
        timeframe="H1",
        average_range_before_departure={3: 0.6},
    )
    candidate = next(item for item in candidates if item["departure_end_index"] == 3)

    assert candidate["family"] == "supply_demand"
    assert candidate["direction"] == "buy"
    assert candidate["type"] == "demand_zone"
    assert candidate["formation_start_index"] == 0
    assert candidate["formation_end_index"] == 2
    assert candidate["departure_end_index"] == 3
    assert candidate["original_bounds"] == {"low": 99.8, "high": 100.5}
    assert candidate["departure_close_outside_base"] is True
    assert candidate["lifecycle_status"] == "candidate"
    assert candidate["confirmed_at"] is None
    assert candidate["available_at"] is None
    assert candidate["entry_eligible"] is False
