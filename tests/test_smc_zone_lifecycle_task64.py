"""Task 64 contracts for canonical age decay and zone expiry."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle, candle_close_at
from core.smc_context import enrich_zones
from core.smc_lifecycle import analyze_zone_lifecycle


START = datetime(2026, 9, 11, tzinfo=timezone.utc)


def _candles(count, *, step_hours=4, close=113):
    return [
        Candle(
            time=START + timedelta(hours=step_hours * index),
            open=112,
            high=114,
            low=111,
            close=close,
            volume=100,
        )
        for index in range(count)
    ]


def _lifecycle(candles, *, timeframe="H4", tf_minutes=240, **kwargs):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side="buy",
        origin_index=0,
        departure_end_index=0,
        zone_id="smcz-task64",
        timeframe=timeframe,
        tf_minutes=tf_minutes,
        **kwargs,
    )


def test_age_decay_keeps_lifetime_boundary_alive_at_score_quarter():
    result = _lifecycle(_candles(31))

    assert result.age_bars == 30
    assert result.age_score == pytest.approx(0.25)
    assert result.lifecycle_stale is False
    assert result.lifecycle_expired is False
    assert result.expired_at is None


def test_age_one_past_lifetime_expires_at_that_close():
    candles = _candles(32)
    result = _lifecycle(candles)

    assert result.age_bars == 31
    assert result.age_score == 0.0
    assert result.lifecycle_stale is True
    assert result.lifecycle_expired is True
    assert result.expiry_index == 31
    assert result.expired_at == candle_close_at(candles[31].time, "H4").isoformat()


def test_age_anchor_starts_at_available_at_not_formation_index():
    candles = _candles(7)
    available_at = candle_close_at(candles[5].time, "H4")
    result = _lifecycle(candles, available_at=available_at)

    assert result.age_bars == 1
    assert result.age_score == pytest.approx(0.975)
    assert result.lifecycle_expired is False


def test_invalidation_wins_over_expiry_on_same_candle():
    candles = _candles(32)
    candles[31] = Candle(
        time=candles[31].time,
        open=99,
        high=100,
        low=98,
        close=99,
        volume=100,
    )
    # F02/r1: explicit synthetic metadata at the call site (TL-approved);
    # buffer = max(0.1, 0.05*2) = 0.1 keeps the invalidation close below the threshold.
    result = _lifecycle(candles, tick_size=0.1, atr_current=2.0)

    assert result.invalidation_index == 31
    assert result.lifecycle_broken is True
    assert result.lifecycle_expired is False
    assert result.expiry_index is None
    assert result.expired_at is None


def test_invalidation_before_lifetime_does_not_become_later_expiry():
    candles = _candles(40)
    candles[5] = Candle(
        time=candles[5].time,
        open=99,
        high=100,
        low=98,
        close=99,
        volume=100,
    )
    # F02/r1: explicit synthetic metadata at the call site (TL-approved);
    # buffer = max(0.1, 0.05*2) = 0.1 keeps the invalidation close below the threshold.
    result = _lifecycle(candles, tick_size=0.1, atr_current=2.0)

    assert result.lifecycle_broken is True
    assert result.invalidation_index == 5
    assert result.lifecycle_expired is False
    assert result.expiry_index is None


def test_enrichment_marks_expired_zone_unusable_and_keeps_history():
    candles = _candles(52, step_hours=1)
    zone = {
        "zone_id": "smcz-task64-enrich",
        "type": "demand_zone",
        "family": "supply_demand",
        "direction": "buy",
        "low": 100,
        "high": 110,
        "origin_index": 0,
        "origin_time": candles[0].time.isoformat(),
        "departure_end_index": 0,
    }
    result = enrich_zones(
        [zone], candles, "demand", {}, {"status": "unknown"},
        tf_minutes=60, timeframe="H1",
    )[0]

    assert result["lifecycle_status"] == "expired"
    assert result["usable"] is False
    assert result["lifecycle_expired"] is True
    assert result["expired_at"] is not None
    assert "ZONE_EXPIRED" in result["reason_codes"]
