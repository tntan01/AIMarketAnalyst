from __future__ import annotations

from copy import deepcopy

from core.smc_context import get_preferred_zone
from tests.test_source_zone_diagnostics import _valid_plan


ATR = 0.002
PRICE = 1.1000


def _zone(**overrides: object) -> dict[str, object]:
    zone: dict[str, object] = {
        "type": "bullish_order_block",
        "low": 1.0975,
        "high": 1.0985,
        "zone_score": 80,
        "stale": False,
        "mitigated": False,
        "broken": False,
        "test_count": 1,
        "freshness_bars": 4,
        "displacement_multiple": 1.0,
        "liquidity_sweep": False,
        "zone_location": "discount",
        "strength": "strong",
    }
    zone.update(overrides)
    return zone


def _context(*zones: dict[str, object]) -> dict[str, object]:
    return {"H4": {"order_blocks": list(zones)}}


def test_consumed_zone_cannot_beat_healthy_preferred_zone() -> None:
    consumed = _zone(
        low=1.0960,
        high=1.0970,
        zone_score=99,
        stale=True,
        test_count=5,
        displacement_multiple=3.0,
        liquidity_sweep=True,
    )
    healthy = _zone(
        low=1.0980,
        high=1.0990,
        zone_score=75,
        freshness_bars=20,
        test_count=2,
        displacement_multiple=0.0,
    )

    selected = get_preferred_zone(
        _context(consumed, healthy),
        "buy",
        PRICE,
        ATR,
    )

    assert selected is not None
    assert selected["low"] == 1.0980
    assert selected["selection_status"] == "preferred"
    assert selected["watch_only_fallback"] is False


def test_only_consumed_zone_becomes_watch_only_fallback() -> None:
    consumed = _zone(
        stale=True,
        test_count=8,
        displacement_multiple=3.0,
        liquidity_sweep=True,
    )

    selected = get_preferred_zone(
        _context(consumed),
        "buy",
        PRICE,
        ATR,
    )

    assert selected is not None
    assert selected["selection_status"] == "watch_only_fallback"
    assert selected["selection_reason"] == "stale_high_test_count"
    assert selected["watch_only_fallback"] is True


def test_tie_breaks_freshness_then_distance_then_width() -> None:
    fresher = _zone(
        low=1.0950,
        high=1.0960,
        freshness_bars=4,
    )
    nearer_but_older = _zone(
        low=1.0980,
        high=1.0990,
        freshness_bars=5,
    )
    selected = get_preferred_zone(
        _context(nearer_but_older, fresher),
        "buy",
        PRICE,
        ATR,
    )
    assert selected is not None
    assert selected["low"] == 1.0950

    farther = _zone(low=1.0965, high=1.0975, freshness_bars=4)
    nearer = _zone(low=1.0980, high=1.0990, freshness_bars=4)
    selected = get_preferred_zone(
        _context(farther, nearer),
        "buy",
        PRICE,
        ATR,
    )
    assert selected is not None
    assert selected["low"] == 1.0980

    narrow = _zone(low=1.0975, high=1.0985, freshness_bars=4)
    wide = _zone(low=1.0974, high=1.0986, freshness_bars=4)
    selected = get_preferred_zone(
        _context(wide, narrow),
        "buy",
        PRICE,
        ATR,
    )
    assert selected is not None
    assert selected["low"] == 1.0975


def test_selection_is_deterministic_when_input_order_reverses() -> None:
    first = _zone(low=1.0975, high=1.0985)
    second = deepcopy(first)

    selected_a = get_preferred_zone(
        _context(first, second),
        "buy",
        PRICE,
        ATR,
    )
    selected_b = get_preferred_zone(
        _context(second, first),
        "buy",
        PRICE,
        ATR,
    )

    assert selected_a == selected_b


def test_wrong_side_and_broken_zones_are_filtered_for_buy_and_sell() -> None:
    broken_buy = _zone(broken=True)
    wrong_price_buy = _zone(low=1.1010, high=1.1020)
    valid_buy = _zone(low=1.0980, high=1.0990)
    selected_buy = get_preferred_zone(
        _context(broken_buy, wrong_price_buy, valid_buy),
        "buy",
        PRICE,
        ATR,
    )
    assert selected_buy is not None
    assert selected_buy["low"] == 1.0980

    valid_sell = _zone(
        type="bearish_order_block",
        low=1.1010,
        high=1.1020,
        zone_location="premium",
    )
    wrong_family = _zone(
        type="bullish_order_block",
        low=1.1020,
        high=1.1030,
    )
    selected_sell = get_preferred_zone(
        _context(wrong_family, valid_sell),
        "sell",
        PRICE,
        ATR,
    )
    assert selected_sell is not None
    assert selected_sell["type"] == "bearish_order_block"


def test_gbpjpy_fixture_selects_less_consumed_alternate_as_watch() -> None:
    raw_96 = _zone(
        low=217.518,
        high=218.261,
        zone_score=96,
        stale=True,
        mitigated=True,
        test_count=12,
        freshness_bars=12,
        displacement_multiple=1.3,
    )
    raw_95 = _zone(
        low=218.003,
        high=218.215,
        zone_score=95,
        stale=True,
        mitigated=True,
        test_count=4,
        freshness_bars=4,
        displacement_multiple=0.69,
    )

    selected = get_preferred_zone(
        _context(raw_96, raw_95),
        "buy",
        218.466,
        0.3803414856657719,
    )

    assert selected is not None
    assert selected["zone_score"] == 95
    assert selected["effective_zone_score"] == 39
    assert selected["low"] == 218.003
    assert selected["selection_status"] == "watch_only_fallback"


def test_watch_only_fallback_cannot_become_confirmed_entry(
    monkeypatch,
) -> None:
    fallback = _zone(
        low=1.0968,
        high=1.0982,
        stale=True,
        mitigated=True,
        test_count=8,
        freshness_bars=20,
        displacement_multiple=0.0,
        liquidity_sweep=False,
    )
    selected = get_preferred_zone(
        _context(fallback),
        "buy",
        PRICE,
        ATR,
    )
    assert selected is not None
    assert selected["watch_only_fallback"] is True

    monkeypatch.setattr(
        "core.risk_engine.evaluate_entry",
        lambda **kwargs: {
            "entry_status": "confirmed_entry",
            "ready_to_trade": True,
            "invalid_reason": "",
            "entry_ladder": {},
        },
    )
    plan = _valid_plan(selected)

    assert plan["entry_status"] == "watch_zone"
    assert plan["ready_to_trade"] is False
    assert "Zone fallback" in plan["invalid_reason"]
    assert plan["source_zone"]["selection_status"] == "watch_only_fallback"
