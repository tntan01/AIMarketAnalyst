"""Phase-3 contracts for canonical liquidity-sweep/zone association."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.risk_engine import _smc_zones_to_levels
from core.smc_context import (
    _attach_zone_sweep_links,
    detect_liquidity_sweeps,
    enrich_zones,
    extract_smc_trade_flags,
    get_preferred_zone,
)
from core.smc_models import SmcZone
from core.smc_sweep_linking import (
    SMC_SWEEP_LINK_VERSION,
    associate_sweeps_to_zones,
    build_sweep_id,
)


def _zone(
    zone_id: str,
    *,
    side: str,
    low: float = 100,
    high: float = 110,
    formation_start: int = 8,
    origin: int = 10,
    departure: int = 12,
) -> dict:
    return {
        "zone_id": zone_id,
        "direction": side,
        "low": low,
        "high": high,
        "formation_start_index": formation_start,
        "origin_index": origin,
        "departure_end_index": departure,
    }


def _sweep(
    sweep_id: str,
    *,
    side: str,
    level: float,
    index: int = 11,
) -> dict:
    return {
        "sweep_id": sweep_id,
        "side": side,
        "kind": "swept_low" if side == "buy" else "swept_high",
        "level": level,
        "index": index,
        "time": f"2026-07-01T{index:02d}:00:00+00:00",
    }


def _sweep_collection(*sweeps: dict) -> dict[str, list[dict]]:
    return {
        "swept_lows": [
            sweep for sweep in sweeps if sweep["side"] == "buy"
        ],
        "swept_highs": [
            sweep for sweep in sweeps if sweep["side"] == "sell"
        ],
    }


def _candles(count: int, *, minutes: int = 60) -> list[Candle]:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(minutes=minutes * index),
            open=120,
            high=121,
            low=119,
            close=120,
            volume=1000,
        )
        for index in range(count)
    ]


def test_sweep_farther_than_atr_tolerance_is_not_linked():
    links = associate_sweeps_to_zones(
        [_zone("zone-buy", side="buy")],
        _sweep_collection(_sweep("sweep-low", side="buy", level=96)),
        atr_value=10,
    )

    assert links == {}


def test_sweep_outside_formation_departure_window_is_not_back_linked():
    links = associate_sweeps_to_zones(
        [_zone("zone-buy", side="buy")],
        _sweep_collection(
            _sweep("sweep-late", side="buy", level=105, index=20)
        ),
        atr_value=10,
    )

    assert links == {}


def test_one_sweep_is_assigned_to_only_one_best_zone():
    zones = [
        _zone(
            "zone-departure-near",
            side="buy",
            low=100,
            high=110,
            departure=11,
        ),
        _zone(
            "zone-departure-far",
            side="buy",
            low=102,
            high=112,
            departure=12,
        ),
    ]
    links = associate_sweeps_to_zones(
        zones,
        _sweep_collection(_sweep("sweep-shared", side="buy", level=105)),
        atr_value=10,
    )

    assert list(links) == ["zone-departure-near"]
    assert links["zone-departure-near"].sweep_id == "sweep-shared"


def test_one_sweep_is_not_broadcast_across_zone_families():
    candles = _candles(20)
    origin_time = candles[10].time.isoformat()
    demand = {
        "type": "demand_zone",
        "low": 100,
        "high": 110,
        "index": 10,
        "time": origin_time,
        "formation_start_index": 8,
        "departure_end_index": 12,
    }
    fvg = {
        "type": "bullish_fvg",
        "low": 102,
        "high": 112,
        "index": 10,
        "time": origin_time,
        "formation_start_index": 8,
        "departure_end_index": 12,
    }
    sweeps = _sweep_collection(
        _sweep("sweep-cross-family", side="buy", level=105)
    )

    _attach_zone_sweep_links(
        (("demand", [demand]), ("fvg", [fvg])),
        sweeps,
        candles=candles,
        symbol="EUR/USD",
        timeframe="H1",
        tf_minutes=60,
    )

    linked_zones = [
        zone
        for zone in (demand, fvg)
        if zone["liquidity_sweep_linked"]
    ]
    assert len(linked_zones) == 1
    assert linked_zones[0]["linked_sweep_id"] == "sweep-cross-family"
    assert sweeps["swept_lows"][0]["linked_zone_id"] == linked_zones[0]["zone_id"]


def test_buy_and_sell_distance_association_is_symmetric():
    links = associate_sweeps_to_zones(
        [
            _zone("zone-buy", side="buy"),
            _zone("zone-sell", side="sell"),
        ],
        _sweep_collection(
            _sweep("sweep-low", side="buy", level=98),
            _sweep("sweep-high", side="sell", level=112),
        ),
        atr_value=10,
    )

    assert links["zone-buy"].distance_atr == pytest.approx(0.2)
    assert links["zone-sell"].distance_atr == pytest.approx(0.2)
    assert links["zone-buy"].time_delta == 1
    assert links["zone-sell"].time_delta == 1


def test_wrong_side_sweep_never_links_even_when_price_and_time_match():
    links = associate_sweeps_to_zones(
        [_zone("zone-buy", side="buy")],
        _sweep_collection(_sweep("sweep-high", side="sell", level=105)),
        atr_value=10,
    )

    assert links == {}


def test_sweep_identity_is_deterministic_and_detector_emits_trace_metadata():
    first = build_sweep_id(
        symbol="EUR/USD",
        timeframe="h4",
        side="buy",
        kind="swept_low",
        level="1.0950",
        occurred_at="2026-07-01T00:00:00+00:00",
    )
    second = build_sweep_id(
        symbol="eurusd",
        timeframe="H4",
        side="buy",
        kind="swept_low",
        level=1.095,
        occurred_at="2026-07-01T00:00:00+00:00",
    )
    assert first == second
    assert first.startswith("smcs-")

    candles = [
        Candle(
            time=datetime(2026, 7, 1, tzinfo=timezone.utc)
            + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=1000,
        )
        for index, (open_, high, low, close) in enumerate([
            (100, 101, 99, 100),
            (100, 103, 99, 100),
            (100, 106, 99, 102),
        ])
    ]
    detected = detect_liquidity_sweeps(
        candles,
        {
            "highs": [{"level": 104, "index": 1, "time": ""}],
            "lows": [],
        },
        symbol="EUR/USD",
        timeframe="H1",
    )["swept_highs"][0]

    assert detected["sweep_id"].startswith("smcs-")
    assert detected["side"] == "sell"
    assert detected["kind"] == "swept_high"
    assert detected["index"] == 2
    assert detected["source_swing_index"] == 1


def test_canonical_sweep_window_retains_formation_evidence_beyond_six_bars():
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    prices = [
        (100, 101, 99, 100),
        (100, 103, 99, 100),
        (100, 106, 99, 102),  # sweep of level 104
        *((102, 103, 101, 102) for _ in range(7)),
    ]
    candles = [
        Candle(
            time=start + timedelta(hours=index),
            open=open_,
            high=high,
            low=low,
            close=close,
            volume=1000,
        )
        for index, (open_, high, low, close) in enumerate(prices)
    ]
    swings = {
        "highs": [{"level": 104, "index": 1, "time": ""}],
        "lows": [],
    }

    legacy = detect_liquidity_sweeps(candles, swings)
    canonical = detect_liquidity_sweeps(
        candles,
        swings,
        lookback_bars=10,
        max_results=None,
        causal_only=True,
    )

    assert legacy["swept_highs"] == []
    assert canonical["swept_highs"][0]["index"] == 2


def test_enrichment_preserves_legacy_broadcast_but_canonical_link_is_explicit():
    candles = _candles(4)
    zone = {
        "type": "demand_zone",
        "low": 100,
        "high": 110,
        "index": 1,
        "origin_index": 1,
        "time": candles[1].time.isoformat(),
        "origin_time": candles[1].time.isoformat(),
        "departure_end_index": 1,
    }
    distant_sweep = _sweep(
        "sweep-distant",
        side="buy",
        level=50,
        index=1,
    )
    result = enrich_zones(
        [zone],
        candles,
        "demand",
        _sweep_collection(distant_sweep),
        {"status": "unknown"},
        tf_minutes=60,
        scan_interval_min=15,
        symbol="EUR/USD",
        timeframe="H1",
    )[0]

    assert result["liquidity_sweep"] is True
    assert result["legacy_liquidity_sweep"] is True
    assert result["liquidity_sweep_linked"] is False
    assert result["linked_sweep_id"] is None
    assert result["sweep_link_version"] == SMC_SWEEP_LINK_VERSION


def test_link_metadata_survives_zone_model_round_trip():
    payload = {
        "type": "demand_zone",
        "direction": "buy",
        "family": "demand",
        "low": 100,
        "high": 110,
        "index": 10,
        "time": "2026-07-01T10:00:00+00:00",
        "zone_score": 70,
        "liquidity_sweep": True,
        "legacy_liquidity_sweep": True,
        "liquidity_sweep_linked": True,
        "linked_sweep_id": "smcs-example",
        "linked_sweep_kind": "swept_low",
        "linked_sweep_level": 99,
        "linked_sweep_time": "2026-07-01T11:00:00+00:00",
        "linked_sweep_index": 11,
        "linked_sweep_distance_atr": 0.2,
        "linked_sweep_time_delta": 1,
    }
    first = SmcZone.from_legacy_dict(
        payload,
        symbol="EUR/USD",
        timeframe="H1",
    )
    second = SmcZone.from_legacy_dict(first.to_dict())

    assert first == second
    assert first.liquidity_sweep_linked is True
    assert first.linked_sweep_id == "smcs-example"
    assert first.linked_sweep_distance_atr == pytest.approx(0.2)
    assert first.legacy_liquidity_sweep is True

    adapted = first.to_dict()
    context = {
        "symbol": "EUR/USD",
        "H4": {"demand_zones": [adapted]},
        "H1": {},
    }
    selected = get_preferred_zone(context, "buy", price=120)
    flags = extract_smc_trade_flags(context, "buy")
    levels = _smc_zones_to_levels([adapted])

    assert selected is not None
    assert selected["linked_sweep_id"] == "smcs-example"
    assert selected["liquidity_sweep_linked"] is True
    assert flags["selected_zone_linked_sweep_id"] == "smcs-example"
    assert flags["selected_zone_liquidity_sweep_linked"] is True
    assert levels[0]["linked_sweep_id"] == "smcs-example"
    assert levels[0]["linked_sweep_distance_atr"] == pytest.approx(0.2)
