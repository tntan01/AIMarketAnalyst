"""Canonical SMC scorer contracts: zone selection, breakdown and determinism."""

from __future__ import annotations

from dataclasses import replace

from core.scanner_observability import stable_hash
from core.smc_models import SmcZone
from core.smc_scorer import (
    EvaluatedSmcZone,
    evaluate_smc_zones,
    score_smc,
    select_smc_zone,
)
from core.smc_versions import SMC_SCORER_VERSION


def _zone(
    side: str,
    *,
    zone_id: str | None = None,
    low: float | None = None,
    high: float | None = None,
    broken: bool = False,
    stale: bool = False,
    age_bars: int = 5,
    visits: int = 0,
    mitigation_ratio: float | None = None,
    linked_sweep: bool = False,
) -> dict:
    is_buy = side == "buy"
    zone_low = low if low is not None else (90 if is_buy else 105)
    zone_high = high if high is not None else (95 if is_buy else 110)
    return {
        "zone_id": zone_id or f"zone-{side}",
        "type": "demand_zone" if is_buy else "supply_zone",
        "family": "demand" if is_buy else "supply",
        "direction": side,
        "low": zone_low,
        "high": zone_high,
        "index": 10,
        "origin_index": 10,
        "time": "2026-07-01T10:00:00+00:00",
        "origin_time": "2026-07-01T10:00:00+00:00",
        "formation_start_index": 7,
        "departure_end_index": 11,
        "freshness_bars": age_bars,
        "age_bars": age_bars,
        "age_minutes": age_bars * 240,
        "lifecycle_stale": stale,
        "lifecycle_broken": broken,
        "lifecycle_mitigated": visits > 0,
        "independent_retest_count": visits,
        "bars_spent_inside": visits,
        "mitigation_ratio": mitigation_ratio,
        "displacement_multiple": 2.0,
        "zone_location": "discount" if is_buy else "premium",
        "liquidity_sweep_linked": linked_sweep,
        "linked_sweep_id": f"sweep-{side}" if linked_sweep else None,
        "linked_sweep_distance_atr": 0.1 if linked_sweep else None,
        "linked_sweep_time_delta": 1 if linked_sweep else None,
        "zone_score": 70,
        "zone_quality_score": 70,
        "zone_setup_score": 70,
        "broken": broken,
        "stale": stale,
        "test_count": visits,
    }


def _smc(
    side: str,
    *,
    zone: dict | None = None,
    linked_h1_sweep: bool = False,
    h4_choch_against: bool = False,
    h1_choch_against: bool = False,
) -> dict:
    is_buy = side == "buy"
    expected_structure = "HH/HL" if is_buy else "LH/LL"
    expected_displacement = "bullish" if is_buy else "bearish"
    opposite_displacement = "bearish" if is_buy else "bullish"
    h1_sweeps = {
        "swept_lows" if is_buy else "swept_highs": [{
            "sweep_id": f"sweep-{side}",
            "linked_zone_id": (
                (zone or {}).get("zone_id", f"zone-{side}")
                if linked_h1_sweep
                else None
            ),
        }]
    }
    h4 = {
        "structure": expected_structure,
        "bos": True,
        "choch": h4_choch_against,
        "choch_confirmed": h4_choch_against,
        "displacement": (
            opposite_displacement
            if h4_choch_against
            else expected_displacement
        ),
        "demand_zones": [zone or _zone(side)] if is_buy else [],
        "supply_zones": [zone or _zone(side)] if not is_buy else [],
        "order_blocks": [],
        "fvg": [],
    }
    h1 = {
        "structure": expected_structure,
        "bos": not h1_choch_against,
        "choch": h1_choch_against,
        "choch_confirmed": h1_choch_against,
        "displacement": (
            opposite_displacement
            if h1_choch_against
            else expected_displacement
        ),
        "demand_zones": [],
        "supply_zones": [],
        "order_blocks": [],
        "fvg": [],
        "zone_link_sweeps": h1_sweeps,
    }
    return {
        "symbol": "TEST",
        "H4": h4,
        "H1": h1,
        "confluence": {
            "buy_score": 5 if is_buy else 0,
            "sell_score": 5 if not is_buy else 0,
            "buy_reason_codes": ["BUY_ALL_TIMEFRAMES_ALIGNED"]
            if is_buy else [],
            "sell_reason_codes": ["SELL_ALL_TIMEFRAMES_ALIGNED"]
            if not is_buy else [],
        },
    }


def _technical(side: str, *, price: float = 100, atr_value: float = 10) -> dict:
    is_buy = side == "buy"
    level = 92.5 if is_buy else 107.5
    return {
        "price": price,
        "atr_h4": atr_value,
        "atr_d1": atr_value,
        "support_zones": [{"level": level, "source": "technical"}],
        "resistance_zones": [{"level": level, "source": "technical"}],
    }


def test_quality_is_intrinsic_while_relevance_changes_with_price():
    context = _smc("buy")
    near = evaluate_smc_zones(
        context,
        "buy",
        price=100,
        atr_value=10,
        market_regime={"primary": "trend_up"},
    )[0]
    far = evaluate_smc_zones(
        context,
        "buy",
        price=120,
        atr_value=10,
        market_regime={"primary": "trend_up"},
    )[0]

    assert near.zone.zone_quality_score == far.zone.zone_quality_score
    assert near.zone.zone_relevance_score > far.zone.zone_relevance_score
    assert near.zone.zone_setup_score > far.zone.zone_setup_score
    assert near.zone.zone_setup_score == round(
        near.zone.zone_quality_score * 0.60
        + near.zone.zone_relevance_score * 0.40
    )


def test_mandatory_filters_fail_closed():
    broken = evaluate_smc_zones(
        _smc("buy", zone=_zone("buy", broken=True)),
        "buy",
        price=100,
        atr_value=10,
    )[0]
    wrong_side = evaluate_smc_zones(
        _smc("buy"),
        "buy",
        price=80,
        atr_value=10,
    )[0]
    too_far = evaluate_smc_zones(
        _smc("buy"),
        "buy",
        price=140,
        atr_value=10,
    )[0]
    missing_atr = evaluate_smc_zones(
        _smc("buy"),
        "buy",
        price=100,
        atr_value=None,
    )[0]

    assert "ZONE_BROKEN" in broken.rejection_codes
    assert "ZONE_ON_WRONG_PRICE_SIDE" in wrong_side.rejection_codes
    assert "ZONE_BEYOND_HARD_DISTANCE" in too_far.rejection_codes
    assert "MISSING_ATR" in missing_atr.rejection_codes
    assert all(
        evaluation.zone.zone_setup_score == 0
        for evaluation in (broken, wrong_side, too_far, missing_atr)
    )


def _evaluated(
    zone_id: str,
    *,
    setup: int,
    distance: float,
    age: int,
) -> EvaluatedSmcZone:
    model = SmcZone.from_dict(
        _zone("buy", zone_id=zone_id, age_bars=age),
        symbol="TEST",
        timeframe="H4",
    )
    model = replace(
        model,
        zone_quality_score=setup,
        zone_relevance_score=setup,
        zone_setup_score=setup,
        age_bars=age,
        scoring_version=SMC_SCORER_VERSION,
    )
    return EvaluatedSmcZone(
        zone=model,
        mandatory_passed=True,
        distance_atr=distance,
        rejection_codes=(),
        quality_components=(),
        relevance_components=(),
    )


def test_selection_uses_setup_then_distance_recency_and_id():
    higher_setup = select_smc_zone((
        _evaluated("zone-near", setup=70, distance=0.1, age=1),
        _evaluated("zone-high", setup=80, distance=2.0, age=20),
    ))
    nearest = select_smc_zone((
        _evaluated("zone-far", setup=80, distance=1.0, age=1),
        _evaluated("zone-near", setup=80, distance=0.5, age=20),
    ))
    newest = select_smc_zone((
        _evaluated("zone-old", setup=80, distance=0.5, age=20),
        _evaluated("zone-new", setup=80, distance=0.5, age=2),
    ))
    stable_id = select_smc_zone((
        _evaluated("zone-b", setup=80, distance=0.5, age=2),
        _evaluated("zone-a", setup=80, distance=0.5, age=2),
    ))

    assert higher_setup and higher_setup.zone_id == "zone-high"
    assert nearest and nearest.zone_id == "zone-near"
    assert newest and newest.zone_id == "zone-new"
    assert stable_id and stable_id.zone_id == "zone-a"


def test_breakdown_arithmetic_and_selected_zone_are_consistent():
    result = score_smc(
        _smc("buy"),
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy")
    breakdown = result.breakdown

    assert breakdown["subtotal"] == sum((
        breakdown["structure_score"],
        breakdown["zone_score"],
        breakdown["ltf_confirmation_score"],
        breakdown["technical_validation_score"],
    ))
    expected = max(0, breakdown["subtotal"] - breakdown["penalty_points"])
    if breakdown["applied_cap"] is not None:
        expected = min(expected, breakdown["applied_cap"])
    assert breakdown["total"] == expected == result.score
    assert breakdown["selected_zone_id"] == result.selected_zone_id
    assert result.selected_zone["zone_id"] == result.selected_zone_id
    assert result.selected_zone["scoring_version"] == SMC_SCORER_VERSION


def test_zone_linked_sweep_is_not_counted_again_in_ltf_component():
    linked_zone = _zone("buy", linked_sweep=True)
    context = _smc(
        "buy",
        zone=linked_zone,
        linked_h1_sweep=True,
    )
    context["H1"].update({
        "structure": "unknown",
        "bos": False,
        "choch": False,
        "displacement": "neutral",
    })
    linked = score_smc(
        context,
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy").breakdown

    unlinked_context = _smc("buy", zone=_zone("buy"))
    unlinked_context["H1"].update({
        "structure": "unknown",
        "bos": False,
        "choch": False,
        "displacement": "neutral",
    })
    unlinked = score_smc(
        unlinked_context,
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy").breakdown

    assert linked["ltf_confirmation_score"] == 0
    assert unlinked["ltf_confirmation_score"] == 1


def test_buy_sell_mirror_symmetry():
    buy = score_smc(
        _smc("buy", zone=_zone("buy", linked_sweep=True)),
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy")
    sell = score_smc(
        _smc("sell", zone=_zone("sell", linked_sweep=True)),
        _technical("sell"),
        {"primary": "trend_down"},
    ).side("sell")

    assert buy.score == sell.score
    assert buy.selected_zone_quality_score == sell.selected_zone_quality_score
    assert buy.selected_zone_relevance_score == sell.selected_zone_relevance_score
    assert buy.selected_zone_setup_score == sell.selected_zone_setup_score
    assert buy.breakdown["structure_score"] == sell.breakdown["structure_score"]
    assert buy.breakdown["zone_score"] == sell.breakdown["zone_score"]


def test_choch_penalty_and_caps_are_applied_after_subtotal():
    h1_cap = score_smc(
        _smc("buy", h1_choch_against=True),
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy").breakdown
    h4_cap = score_smc(
        _smc("buy", h4_choch_against=True),
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy").breakdown

    assert h1_cap["penalty_points"] == 2
    assert h1_cap["applied_cap"] == 8
    assert h1_cap["total"] <= 8
    assert h4_cap["applied_cap"] == 4
    assert h4_cap["total"] <= 4


def test_missing_market_data_cannot_select_a_zone():
    result = score_smc(
        _smc("buy"),
        {},
        {"primary": "trend_up"},
    ).side("buy")

    assert result.selected_zone is None
    assert result.selected_zone_id is None
    assert result.breakdown["zone_score"] == 0
    assert 0 <= result.score <= 15


def test_scoring_is_deterministic():
    context = _smc("buy", zone=_zone("buy", linked_sweep=True))
    first = score_smc(
        context,
        _technical("buy"),
        {"primary": "trend_up"},
    )
    second = score_smc(
        context,
        _technical("buy"),
        {"primary": "trend_up"},
    )

    assert stable_hash(first) == stable_hash(second)
