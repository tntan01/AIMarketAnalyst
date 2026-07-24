"""Phase-2 contracts for canonical SMC zone lifecycle semantics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.smc_context import (
    detect_fvg,
    detect_order_blocks,
    detect_supply_demand_zones,
    enrich_zones,
)
from core.smc_lifecycle import analyze_zone_lifecycle
from core.smc_models import SmcZone


def _candles(
    prices: list[tuple[float, float, float, float]],
    *,
    minutes: int = 60,
) -> list[Candle]:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(minutes=minutes * index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=1000,
        )
        for index, (open_, high, low, close) in enumerate(prices)
    ]


def _lifecycle(
    candles: list[Candle],
    *,
    side: str = "buy",
    departure_end_index: int = 1,
):
    return analyze_zone_lifecycle(
        candles=candles,
        low=100,
        high=110,
        side=side,
        origin_index=0,
        departure_end_index=departure_end_index,
        zone_id="smcz-test",
        timeframe="H1",
        tf_minutes=60,
    )


def test_departure_candle_is_not_counted_as_retest():
    result = _lifecycle(
        _candles([
            (112, 114, 111, 113),
            (108, 112, 105, 111),  # departure overlaps the zone
            (112, 114, 111, 113),
        ])
    )

    assert result.first_retest_index is None
    assert result.independent_retest_count == 0
    assert result.bars_spent_inside == 0
    assert result.lifecycle_mitigated is False


def test_consecutive_inside_bars_are_one_independent_visit():
    result = _lifecycle(
        _candles([
            (112, 114, 111, 113),
            (112, 114, 111, 113),
            (109, 112, 108, 109),
            (107, 109, 104, 106),
            (105, 108, 101, 104),
            (112, 114, 111, 113),
        ])
    )

    assert result.first_retest_index == 2
    assert result.independent_retest_count == 1
    assert result.bars_spent_inside == 3
    assert result.mitigation_ratio == pytest.approx(0.9)
    assert result.visits[0].start_index == 2
    assert result.visits[0].end_index == 4


def test_leaving_and_returning_creates_a_second_visit():
    result = _lifecycle(
        _candles([
            (112, 114, 111, 113),
            (112, 114, 111, 113),
            (109, 112, 106, 108),
            (112, 114, 111, 113),
            (108, 111, 103, 106),
            (112, 114, 111, 113),
        ])
    )

    assert result.independent_retest_count == 2
    assert result.bars_spent_inside == 2
    assert [visit.start_index for visit in result.visits] == [2, 4]


def test_buy_and_sell_mitigation_are_mirrored():
    buy = _lifecycle(
        _candles([
            (112, 114, 111, 113),
            (112, 114, 111, 113),
            (109, 111, 102, 105),
        ]),
        side="buy",
    )
    sell = _lifecycle(
        _candles([
            (98, 99, 96, 97),
            (98, 99, 96, 97),
            (101, 108, 99, 105),
        ]),
        side="sell",
    )

    assert buy.mitigation_ratio == pytest.approx(0.8)
    assert sell.mitigation_ratio == pytest.approx(0.8)


def test_first_invalidation_is_terminal_for_the_lifecycle():
    result = _lifecycle(
        _candles([
            (112, 114, 111, 113),
            (112, 114, 111, 113),
            (108, 111, 104, 106),
            (99, 99, 97, 98),     # first BUY invalidation
            (108, 111, 103, 106),  # must not resurrect the zone
        ])
    )

    assert result.lifecycle_broken is True
    assert result.invalidation_index == 3
    assert result.independent_retest_count == 1
    assert result.bars_spent_inside == 1


def test_enrichment_keeps_legacy_fields_while_exposing_canonical_lifecycle():
    candles = _candles([
        (112, 114, 111, 113),
        (108, 112, 105, 111),  # legacy counts this departure candle
        (112, 114, 111, 113),
    ])
    zone = {
        "type": "demand_zone",
        "low": 100,
        "high": 110,
        "index": 0,
        "origin_index": 0,
        "time": candles[0].time.isoformat(),
        "origin_time": candles[0].time.isoformat(),
        "departure_end_index": 1,
    }

    result = enrich_zones(
        [zone],
        candles,
        "demand",
        {},
        {"status": "unknown"},
        tf_minutes=60,
        scan_interval_min=15,
        symbol="EUR/USD",
        timeframe="H1",
    )[0]

    assert result["test_count"] == 1
    assert result["mitigated"] is True
    assert result["legacy_test_count"] == 1
    assert result["independent_retest_count"] == 0
    assert result["lifecycle_mitigated"] is False
    assert result["first_retest_index"] is None

    model = SmcZone.from_legacy_dict(result)
    assert model.independent_retest_count == 0
    assert model.lifecycle_mitigated is False
    assert model.legacy_test_count == 1
    assert model.legacy_mitigated is True
    assert SmcZone.from_legacy_dict(model.to_dict()) == model


def test_canonical_stale_state_does_not_depend_on_scan_interval():
    candles = _candles(
        [(112, 114, 111, 113)] * 8,
        minutes=240,
    )
    zone = {
        "type": "demand_zone",
        "low": 100,
        "high": 110,
        "index": 2,
        "time": candles[2].time.isoformat(),
        "departure_end_index": 2,
    }
    arguments = (
        [zone],
        candles,
        "demand",
        {},
        {"status": "unknown"},
    )

    frequent = enrich_zones(
        *arguments,
        tf_minutes=240,
        scan_interval_min=15,
        timeframe="H4",
    )[0]
    infrequent = enrich_zones(
        *arguments,
        tf_minutes=240,
        scan_interval_min=1440,
        timeframe="H4",
    )[0]

    assert frequent["stale"] is True
    assert infrequent["stale"] is False
    assert frequent["lifecycle_stale"] is False
    assert infrequent["lifecycle_stale"] is False
    assert frequent["age_bars"] == infrequent["age_bars"] == 5
    assert frequent["age_minutes"] == infrequent["age_minutes"] == 1200


def test_detectors_publish_origin_and_departure_contract():
    fvg_candles = _candles([
        (100, 101, 99, 100),
        (100, 101, 100, 101),
        (103, 104, 102, 103),
    ])
    fvg = detect_fvg(fvg_candles)[0]
    assert fvg["origin_index"] == fvg["index"] == 2
    assert fvg["departure_end_index"] == 2

    ob_candles = _candles([
        (100, 101, 99, 100),
        (101, 102, 99, 100),  # bearish origin
        (100, 104, 100, 103),  # bullish departure
        (103, 104, 102, 103),
    ])
    order_block = next(
        zone
        for zone in detect_order_blocks(ob_candles, [])
        if zone["type"] == "bullish_order_block"
    )
    assert order_block["origin_index"] == order_block["index"] == 1
    assert order_block["departure_end_index"] == 2

    sd_candles = _candles([
        (100.0, 100.2, 99.9, 100.1),
        (100.1, 100.3, 100.0, 100.2),
        (100.2, 100.4, 100.1, 100.3),
        (100.3, 100.5, 100.2, 100.4),
        (100.4, 100.6, 100.3, 100.5),
        (100.5, 100.7, 100.4, 100.6),
        (100.6, 111.0, 100.5, 110.0),  # demand impulse
        (110.0, 110.2, 109.8, 110.1),
    ])
    demand, _ = detect_supply_demand_zones(sd_candles)
    supply_demand = demand[0]
    assert supply_demand["origin_index"] == supply_demand["index"]
    assert supply_demand["departure_end_index"] == (
        supply_demand["origin_index"] + 1
    )
