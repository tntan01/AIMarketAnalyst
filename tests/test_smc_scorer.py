"""Canonical SMC scorer contracts: zone selection, breakdown and determinism."""

from __future__ import annotations

import json

from dataclasses import replace

from core.scanner_observability import stable_hash
from core.smc_models import SmcZone
from core.smc_scorer import (
    AI_ZONE_WEAK_REASON,
    D1_ZONE_REACTION_BONUS_REASON,
    SELECTION_REASON_H1_FALLBACK,
    SELECTION_REASON_H4_PREFERRED,
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
    timeframe: str = "H4",
) -> EvaluatedSmcZone:
    model = SmcZone.from_dict(
        _zone("buy", zone_id=zone_id, age_bars=age),
        symbol="TEST",
        timeframe=timeframe,
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


def test_selection_prefers_h4_over_h1_and_records_reason():
    # Equal quality: the H4 zone wins over the nearer/fresher H1 zone.
    preferred = select_smc_zone((
        _evaluated("zone-h1", setup=80, distance=0.1, age=1, timeframe="H1"),
        _evaluated("zone-h4", setup=80, distance=0.5, age=20, timeframe="H4"),
    ))
    assert preferred and preferred.zone_id == "zone-h4"
    assert preferred.timeframe == "H4"
    assert SELECTION_REASON_H4_PREFERRED in preferred.selection_reason_codes

    # H4 still wins even when the H1 zone has a higher setup score: an H1
    # zone is only selectable when no eligible H4 zone exists.
    h4_over_better_h1 = select_smc_zone((
        _evaluated("zone-h1", setup=95, distance=0.1, age=1, timeframe="H1"),
        _evaluated("zone-h4", setup=60, distance=2.0, age=30, timeframe="H4"),
    ))
    assert h4_over_better_h1 and h4_over_better_h1.zone_id == "zone-h4"
    assert (
        SELECTION_REASON_H4_PREFERRED
        in h4_over_better_h1.selection_reason_codes
    )

    # No eligible H4: the H1 zone is selected and the fallback is recorded.
    fallback = select_smc_zone((
        _evaluated("zone-h1", setup=70, distance=0.2, age=3, timeframe="H1"),
    ))
    assert fallback and fallback.zone_id == "zone-h1"
    assert fallback.timeframe == "H1"
    assert SELECTION_REASON_H1_FALLBACK in fallback.selection_reason_codes


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


def _d1_zone(
    side: str,
    *,
    low: float = 98.0,
    high: float = 99.5,
    family: str = "order_block",
    broken: bool = False,
    mitigated: bool = False,
) -> dict:
    return {
        "zone_id": f"d1-{family}-{side}",
        "type": (
            f"{'bullish' if side == 'buy' else 'bearish'}_{family}"
        ),
        "family": family,
        "direction": side,
        "low": low,
        "high": high,
        "broken": broken,
        "mitigated": mitigated,
        "test_count": 1 if mitigated else 0,
    }


def _d1_context(
    side: str,
    *,
    d1_zone: dict | None = None,
    confluence_score: int = 2,
) -> dict:
    context = _smc(side)
    context["confluence"][f"{side}_score"] = confluence_score
    context["D1"] = {
        "structure": "HH/HL" if side == "buy" else "LH/LL",
        "demand_zones": [],
        "supply_zones": [],
        "order_blocks": (
            [d1_zone]
            if d1_zone is not None and d1_zone.get("family") != "fvg"
            else []
        ),
        "fvg": (
            [d1_zone]
            if d1_zone is not None and d1_zone.get("family") == "fvg"
            else []
        ),
    }
    return context


def test_d1_zone_reaction_bonus_lifts_confluence_and_keeps_h4_entry():
    context = _d1_context("buy", d1_zone=_d1_zone("buy"))
    result = score_smc(
        context,
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy")
    breakdown = result.breakdown

    assert breakdown["structure_score"] == 4
    assert D1_ZONE_REACTION_BONUS_REASON in breakdown["reason_codes"]
    assert (
        D1_ZONE_REACTION_BONUS_REASON
        in score_smc(
            context,
            _technical("buy"),
            {"primary": "trend_up"},
        ).side("buy").reason_codes
    )
    # The D1 zone never replaces the entry zone: selection stays on H4.
    assert result.selected_zone_id == "zone-buy"
    assert result.selected_zone_timeframe == "H4"

    sell_context = _d1_context("sell", d1_zone=_d1_zone("sell"))
    sell_result = score_smc(
        sell_context,
        _technical("sell"),
        {"primary": "trend_down"},
    ).side("sell")

    assert sell_result.breakdown["structure_score"] == 4
    assert (
        D1_ZONE_REACTION_BONUS_REASON
        in sell_result.breakdown["reason_codes"]
    )
    assert sell_result.selected_zone_timeframe == "H4"


def test_d1_zone_reaction_bonus_fvg_and_conditions():
    # An unmitigated D1 FVG also triggers the bonus.
    fvg_context = _d1_context(
        "buy",
        d1_zone=_d1_zone("buy", family="fvg"),
    )
    fvg_breakdown = score_smc(
        fvg_context,
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy").breakdown
    assert fvg_breakdown["structure_score"] == 4
    assert D1_ZONE_REACTION_BONUS_REASON in fvg_breakdown["reason_codes"]

    # Mitigated D1 zone: no bonus.
    mitigated = _d1_context("buy", d1_zone=_d1_zone("buy", mitigated=True))
    mitigated_breakdown = score_smc(
        mitigated,
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy").breakdown
    assert mitigated_breakdown["structure_score"] == 2
    assert (
        D1_ZONE_REACTION_BONUS_REASON
        not in mitigated_breakdown["reason_codes"]
    )

    # H4 not aligned with the D1 direction: no bonus.
    misaligned = _d1_context("buy", d1_zone=_d1_zone("buy"))
    misaligned["H4"]["structure"] = "unknown"
    misaligned_breakdown = score_smc(
        misaligned,
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy").breakdown
    assert misaligned_breakdown["structure_score"] == 2
    assert (
        D1_ZONE_REACTION_BONUS_REASON
        not in misaligned_breakdown["reason_codes"]
    )

    # Price far from the D1 zone: no bonus.
    far = _d1_context("buy", d1_zone=_d1_zone("buy"))
    far_breakdown = score_smc(
        far,
        _technical("buy", price=120),
        {"primary": "trend_up"},
    ).side("buy").breakdown
    assert far_breakdown["structure_score"] == 2
    assert D1_ZONE_REACTION_BONUS_REASON not in far_breakdown["reason_codes"]


def test_d1_zone_is_never_selected_as_entry_zone():
    context = _d1_context("buy", d1_zone=_d1_zone("buy"))
    context["H4"]["demand_zones"] = []
    context["H4"]["order_blocks"] = []
    context["H1"]["demand_zones"] = []
    result = score_smc(
        context,
        _technical("buy"),
        {"primary": "trend_up"},
    ).side("buy")

    assert result.selected_zone is None
    assert result.selected_zone_id is None
    assert result.selected_zone_timeframe is None
    # The confluence bonus still applies even without an entry zone.
    assert result.breakdown["structure_score"] == 4
    assert (
        D1_ZONE_REACTION_BONUS_REASON in result.breakdown["reason_codes"]
    )


class _FakeZoneAuditAIService:
    """Stands in for services.ai_service.AIService (mock AI responses)."""

    def __init__(self, response):
        self.response = response
        self.calls = []

    def analyze(self, prompt, *, max_tokens=4000):
        self.calls.append(prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _zone_audit_response(**overrides):
    payload = {
        "zone_validity": 9,
        "liquidity_setup": "strong",
        "displacement_quality": 8,
        "confidence": 0.95,
        "reasons": ["Zone sạch"],
    }
    payload.update(overrides)
    return json.dumps(payload, ensure_ascii=False)


def _score_buy(context, *, ai_service=None):
    return score_smc(
        context,
        _technical("buy"),
        {"primary": "trend_up"},
        ai_service=ai_service,
    ).side("buy")


def test_ai_zone_audit_subtracts_points_only_on_confident_weak_verdict():
    weak_ai = _FakeZoneAuditAIService(_zone_audit_response(
        zone_validity=2,
        displacement_quality=3,
        confidence=0.9,
    ))
    baseline = _score_buy(_smc("buy"))
    audited = _score_buy(_smc("buy"), ai_service=weak_ai)

    assert baseline.breakdown["subtotal"] >= 8
    assert len(weak_ai.calls) == 1
    assert audited.score == baseline.score - 2
    assert (
        audited.breakdown["penalty_points"]
        == baseline.breakdown["penalty_points"] + 2
    )
    assert AI_ZONE_WEAK_REASON in audited.breakdown["penalties"]
    assert AI_ZONE_WEAK_REASON in audited.breakdown["reason_codes"]
    # The audit never changes which zone is selected.
    assert audited.selected_zone_id == baseline.selected_zone_id


def test_ai_zone_audit_positive_verdict_never_adds_points():
    positive_ai = _FakeZoneAuditAIService(_zone_audit_response())
    baseline = _score_buy(_smc("buy"))
    audited = _score_buy(_smc("buy"), ai_service=positive_ai)

    assert audited.score == baseline.score
    assert audited.breakdown == baseline.breakdown


def test_ai_zone_audit_low_confidence_or_uncertain_is_ignored():
    baseline_score = _score_buy(_smc("buy")).score

    low_confidence = _FakeZoneAuditAIService(_zone_audit_response(
        zone_validity=1,
        displacement_quality=1,
        confidence=0.5,
    ))
    low_confidence_result = _score_buy(_smc("buy"), ai_service=low_confidence)
    assert low_confidence_result.score == baseline_score
    assert (
        AI_ZONE_WEAK_REASON not in low_confidence_result.breakdown["reason_codes"]
    )

    uncertain = _FakeZoneAuditAIService("không phải json")
    uncertain_result = _score_buy(_smc("buy"), ai_service=uncertain)
    assert uncertain_result.score == baseline_score
    assert (
        AI_ZONE_WEAK_REASON not in uncertain_result.breakdown["reason_codes"]
    )

    errored = _FakeZoneAuditAIService(RuntimeError("provider down"))
    assert _score_buy(_smc("buy"), ai_service=errored).score == baseline_score


def test_ai_zone_audit_is_skipped_below_subtotal_threshold():
    context = _smc("buy")
    context["confluence"]["buy_score"] = 0
    context["H1"].update({
        "structure": "unknown",
        "bos": False,
        "choch": False,
        "displacement": "neutral",
    })
    weak_ai = _FakeZoneAuditAIService(_zone_audit_response(
        zone_validity=0,
        displacement_quality=0,
        confidence=1.0,
    ))
    result = score_smc(
        context,
        {"price": 100, "atr_h4": 10, "atr_d1": 10},
        {"primary": "trend_up"},
        ai_service=weak_ai,
    ).side("buy")

    assert result.breakdown["subtotal"] < 8
    assert weak_ai.calls == []
    assert AI_ZONE_WEAK_REASON not in result.breakdown["reason_codes"]


def test_ai_zone_audit_does_not_override_existing_caps():
    weak_ai = _FakeZoneAuditAIService(_zone_audit_response(
        zone_validity=2,
        displacement_quality=2,
        confidence=0.85,
    ))
    result = score_smc(
        _smc("buy", h4_choch_against=True),
        _technical("buy"),
        {"primary": "trend_up"},
        ai_service=weak_ai,
    ).side("buy")

    assert result.breakdown["applied_cap"] == 4
    assert result.score == 4
    assert result.breakdown["penalty_points"] == 2
    assert AI_ZONE_WEAK_REASON in result.breakdown["penalties"]
    assert AI_ZONE_WEAK_REASON in result.breakdown["reason_codes"]
