"""Phase-1 contracts for immutable SMC domain models and zone identity."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.market_models import Candle
from core.risk_engine import _smc_zones_to_levels
from core.smc_context import (
    enrich_zones,
    extract_smc_trade_flags,
    get_preferred_zone,
)
from core.smc_models import (
    SMC_DOMAIN_VERSION,
    DirectionalConfluence,
    SelectedSmcZone,
    SmcScoreBreakdown,
    SmcZone,
    ZoneVisit,
    adapt_legacy_confluence_payload,
    adapt_legacy_zone_payload,
    build_zone_id,
)
from core.smc_versions import SMC_RAW_ZONE_VERSION


def _legacy_zone(**overrides) -> dict:
    payload = {
        "type": "bullish_order_block",
        "low": 1.0950,
        "high": 1.0970,
        "index": 12,
        "time": "2026-07-01T00:00:00+00:00",
        "zone_score": 78,
        "freshness_bars": 4,
        "stale": False,
        "broken": False,
        "test_count": 1,
    }
    payload.update(overrides)
    return payload


def test_zone_id_is_deterministic_and_normalizes_symbol():
    first = build_zone_id(
        symbol="EUR/USD",
        timeframe="h4",
        family="order_block",
        direction="buy",
        origin_time="2026-07-01T00:00:00+00:00",
        low=1.095,
        high=1.0970,
    )
    second = build_zone_id(
        symbol="eurusd",
        timeframe="H4",
        family="order_block",
        direction="buy",
        origin_time="2026-07-01T00:00:00+00:00",
        low="1.0950",
        high="1.097",
    )
    changed = build_zone_id(
        symbol="EUR/USD",
        timeframe="H4",
        family="order_block",
        direction="buy",
        origin_time="2026-07-01T00:00:00+00:00",
        low=1.0951,
        high=1.0970,
    )

    assert first == second
    assert first.startswith("smcz-")
    assert changed != first


def test_legacy_zone_adapter_adds_contract_without_changing_score():
    adapted = adapt_legacy_zone_payload(
        _legacy_zone(),
        symbol="EUR/USD",
        timeframe="H4",
        family="order_block",
        direction="buy",
    )

    assert adapted["zone_id"].startswith("smcz-")
    assert adapted["symbol"] == "EURUSD"
    assert adapted["timeframe"] == "H4"
    assert adapted["family"] == "order_block"
    assert adapted["direction"] == "buy"
    assert adapted["zone_quality_score"] == 78
    assert adapted["zone_relevance_score"] is None
    assert adapted["zone_setup_score"] == 78
    assert adapted["zone_score"] == 78
    assert adapted["scoring_version"] == SMC_RAW_ZONE_VERSION
    assert adapted["domain_version"] == SMC_DOMAIN_VERSION


def test_zone_model_round_trip_is_stable_and_immutable():
    visit = ZoneVisit(
        visit_id="visit-1",
        entered_at="2026-07-02T00:00:00+00:00",
        exited_at=None,
        start_index=13,
        end_index=None,
        max_penetration_ratio=0.25,
    )
    payload = _legacy_zone(
        visits=[visit.to_dict()],
        zone_quality_score=78,
        zone_setup_score=78,
    )
    first = SmcZone.from_legacy_dict(
        payload,
        symbol="EUR/USD",
        timeframe="H4",
        family="order_block",
        direction="buy",
    )
    second = SmcZone.from_legacy_dict(first.to_dict())

    assert first == second
    assert first.zone_score == 78
    assert first.visits == (visit,)
    with pytest.raises((AttributeError, TypeError)):
        first.zone_setup_score = 99


def test_model_rejects_direction_conflicting_with_zone_type():
    with pytest.raises(ValueError):
        SmcZone.from_legacy_dict(
            _legacy_zone(),
            symbol="EUR/USD",
            timeframe="H4",
            family="order_block",
            direction="sell",
        )


def test_selected_zone_keeps_compatibility_aliases():
    zone = SmcZone.from_legacy_dict(
        _legacy_zone(),
        symbol="EUR/USD",
        timeframe="H4",
        family="order_block",
        direction="buy",
    )
    selected = SelectedSmcZone.from_zone(zone)
    payload = selected.to_dict()

    assert selected.selected_zone_score == 78
    assert payload["zone_id"] == zone.zone_id
    assert payload["zone_score"] == 78
    assert payload["selected_zone_score"] == 78
    assert payload["source"] == "smc_selected"


def test_directional_confluence_adapter_preserves_legacy_contract():
    legacy = {
        "h1_aligns_h4": True,
        "h4_aligns_d1": True,
        "h1_against_h4": False,
        "all_aligned": True,
        "confluence_score": 5,
    }
    adapted = adapt_legacy_confluence_payload(legacy)
    model = DirectionalConfluence.from_legacy_dict(adapted)

    assert adapted["confluence_score"] == 5
    assert adapted["direction"] == "unknown"
    assert adapted["buy_score"] is None
    assert adapted["sell_score"] is None
    assert model.legacy_score == 5
    assert model.all_aligned is True


def test_legacy_score_breakdown_is_typed_and_bounded():
    breakdown = SmcScoreBreakdown.from_legacy_score(
        "buy",
        18,
        selected_zone_id="smcz-example",
        reason="legacy baseline",
    )

    assert breakdown.total == 15
    assert breakdown.selected_zone_id == "smcz-example"
    assert breakdown.to_dict()["reason_codes"] == ["legacy baseline"]


def _candles(count: int) -> list[Candle]:
    start = datetime(2026, 7, 1, tzinfo=timezone.utc)
    return [
        Candle(
            time=start + timedelta(hours=4 * index),
            open=1.1000,
            high=1.1010,
            low=1.0990,
            close=1.1005,
            volume=1000,
        )
        for index in range(count)
    ]


def test_enriched_zone_identity_reaches_selection_flags_and_risk_adapter():
    zone = {
        "type": "demand_zone",
        "low": 1.0950,
        "high": 1.0960,
        "index": 18,
        "time": "2026-07-04T00:00:00+00:00",
        "displacement_multiple": 2.0,
    }
    enriched = enrich_zones(
        [zone],
        _candles(20),
        "demand",
        {},
        {
            "status": "ok",
            "low": 1.0900,
            "high": 1.1100,
            "midpoint": 1.1000,
        },
        tf_minutes=240,
        symbol="EUR/USD",
        timeframe="H4",
    )[0]
    context = {
        "domain_version": SMC_DOMAIN_VERSION,
        "symbol": "EUR/USD",
        "H4": {"demand_zones": [enriched]},
        "H1": {},
    }

    preferred = get_preferred_zone(context, "buy", price=1.1000)
    flags = extract_smc_trade_flags(context, "buy")
    levels = _smc_zones_to_levels([enriched])

    assert preferred is not None
    assert preferred["zone_id"] == enriched["zone_id"]
    assert flags["selected_zone_id"] == enriched["zone_id"]
    assert flags["selected_zone_quality_score"] == enriched["zone_score"]
    assert flags["selected_zone_setup_score"] == enriched["zone_score"]
    assert levels[0]["zone_id"] == enriched["zone_id"]
    assert levels[0]["zone_setup_score"] == enriched["zone_score"]
