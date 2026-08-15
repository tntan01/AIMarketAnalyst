"""Scanner V4 Step 03: pure four-component TechnicalSignalScore."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from decimal import Inexact, ROUND_DOWN, getcontext
from fractions import Fraction
import inspect
import random
from pathlib import Path

import pytest

from core.reason_codes import TECHNICAL_DATA_UNAVAILABLE
from core.scanner_models import SCANNER_FEATURE_VERSION, SCANNER_SCORER_VERSION
from core.scanner_v4_models import SCANNER_V4_SCORING_VERSION
from core.smc_models import SMC_DOMAIN_VERSION
from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SmcScoringResult,
    SmcSideScoringResult,
)
from core.smc_scorer import score_smc
from core.smc_versions import SMC_SCORER_VERSION, SMC_TECHNICAL_RAW_VERSION
from core.technical_signal_scorer import (
    TECHNICAL_COMPONENT_RAW_MAX,
    TECHNICAL_REGIME_WEIGHTS,
    TECHNICAL_WEIGHT_POLICY_VERSION,
    TechnicalScoreDataError,
    TechnicalSignalScoreResult,
    project_smc_technical_raw,
    score_technical_signal,
    technical_signal_score_gap,
)


_REGIMES = (
    "trending_up",
    "trending_down",
    "ranging",
    "volatile",
    "unknown",
)
_EXPECTED_WEIGHTS = {
    "trending_up": (40, 20, 20, 20),
    "trending_down": (40, 20, 20, 20),
    "ranging": (10, 10, 40, 40),
    "volatile": (20, 10, 40, 30),
    "unknown": (25, 25, 25, 25),
}
_UNSET = object()


def _smc_components(subtotal: int) -> tuple[int, int, int, int]:
    remaining = subtotal
    structure = min(5, remaining)
    remaining -= structure
    zone = min(5, remaining)
    remaining -= zone
    ltf = min(3, remaining)
    remaining -= ltf
    technical = min(2, remaining)
    return structure, zone, ltf, technical


def _smc_side(
    side: str,
    *,
    subtotal: int,
    penalty_points: int = 0,
    applied_cap: int | None = None,
    evidence_code: str = "CANONICAL_STRUCTURE_EVIDENCE",
    selected_zone: bool | None = None,
) -> SmcSideScoringResult:
    structure, zone, ltf, technical = _smc_components(subtotal)
    has_selected_zone = zone > 0 if selected_zone is None else selected_zone
    setup_score = {1: 25, 2: 40, 3: 55, 4: 70, 5: 85}.get(zone)
    source_score = max(0, subtotal - penalty_points)
    if applied_cap is not None:
        source_score = min(source_score, applied_cap)
    zone_id = f"zone-{side}" if has_selected_zone else None
    penalties = [evidence_code] if penalty_points else []
    caps = [evidence_code] if applied_cap is not None else []
    reasons = [evidence_code]
    breakdown = {
        "side": side,
        "total": source_score,
        "structure_score": structure,
        "zone_score": zone,
        "ltf_confirmation_score": ltf,
        "technical_validation_score": technical,
        "subtotal": subtotal,
        "penalty_points": penalty_points,
        "applied_cap": applied_cap,
        "penalties": penalties,
        "caps": caps,
        "selected_zone_id": zone_id,
        "selected_zone_quality_score": 80 if has_selected_zone else None,
        "selected_zone_relevance_score": 70 if has_selected_zone else None,
        "selected_zone_setup_score": setup_score if has_selected_zone else None,
        "reason_codes": reasons,
        "scoring_version": SMC_SCORER_VERSION,
        "domain_version": SMC_DOMAIN_VERSION,
    }
    zone_payload = (
        {
            "zone_id": zone_id,
            "direction": side,
            "timeframe": "H4",
            "family": "demand" if side == "buy" else "supply",
            "zone_type": "demand_zone" if side == "buy" else "supply_zone",
            "low": 90.0 if side == "buy" else 105.0,
            "high": 95.0 if side == "buy" else 110.0,
            "level": 92.5 if side == "buy" else 107.5,
            "zone_quality_score": 80,
            "zone_relevance_score": 70,
            "zone_setup_score": setup_score,
            "liquidity_sweep_linked": False,
            "linked_sweep_id": None,
            "linked_sweep_distance_atr": None,
            "linked_sweep_time_delta": None,
            "source": "smc_selected",
            "scoring_version": SMC_SCORER_VERSION,
            "domain_version": SMC_DOMAIN_VERSION,
            "selection_reason_codes": ("H4_TIMEFRAME_PREFERRED",),
            "type": "demand_zone" if side == "buy" else "supply_zone",
        }
        if has_selected_zone
        else None
    )
    return SmcSideScoringResult(
        score=source_score,
        breakdown=breakdown,
        selected_zone=zone_payload,
        selected_zone_id=zone_id,
        selected_zone_type=("demand_zone" if side == "buy" else "supply_zone")
        if has_selected_zone
        else None,
        selected_zone_timeframe="H4" if has_selected_zone else None,
        reason_codes=tuple(reasons),
        smc_reason=evidence_code,
        selected_zone_score=setup_score if has_selected_zone else None,
        selected_zone_quality_score=80 if has_selected_zone else None,
        selected_zone_relevance_score=70 if has_selected_zone else None,
        selected_zone_setup_score=setup_score if has_selected_zone else None,
    )


def _canonical_smc(
    *,
    buy_subtotal: int = 10,
    sell_subtotal: int = 8,
    buy_penalty: int = 0,
    sell_penalty: int = 0,
    buy_cap: int | None = None,
    sell_cap: int | None = None,
    buy_evidence: str = "BUY_CANONICAL_EVIDENCE",
    sell_evidence: str = "SELL_CANONICAL_EVIDENCE",
) -> SmcScoringResult:
    return SmcScoringResult(
        scoring_version=SMC_SCORER_VERSION,
        contract_version=SMC_SCORING_CONTRACT_VERSION,
        sides={
            "buy": _smc_side(
                "buy",
                subtotal=buy_subtotal,
                penalty_points=buy_penalty,
                applied_cap=buy_cap,
                evidence_code=buy_evidence,
            ),
            "sell": _smc_side(
                "sell",
                subtotal=sell_subtotal,
                penalty_points=sell_penalty,
                applied_cap=sell_cap,
                evidence_code=sell_evidence,
            ),
        },
    )


def _score(
    *,
    side: str = "buy",
    trend: int = 20,
    momentum: int = 15,
    location: int = 20,
    smc: int = 10,
    regime: str = "trending_up",
    canonical_smc: object = _UNSET,
) -> TechnicalSignalScoreResult:
    source = (
        _canonical_smc(
            buy_subtotal=smc if side == "buy" else 10,
            sell_subtotal=smc if side == "sell" else 8,
        )
        if canonical_smc is _UNSET
        else canonical_smc
    )
    return score_technical_signal(
        side,
        trend_raw=trend,
        momentum_raw=momentum,
        location_raw=location,
        canonical_smc=source,
        regime=regime,
    )


@pytest.mark.parametrize("regime", _REGIMES)
def test_all_zero_is_zero_in_every_regime(regime: str):
    result = _score(trend=0, momentum=0, location=0, smc=0, regime=regime)

    assert result.technical_signal_score == 0
    assert tuple(result.technical_breakdown.to_dict()) == (
        "trend",
        "momentum",
        "location",
        "smc",
    )
    assert all(
        item["contribution"] == 0.0
        for item in result.technical_breakdown.to_dict().values()
    )


@pytest.mark.parametrize("regime", _REGIMES)
def test_all_max_is_100_and_breakdown_uses_locked_profile(regime: str):
    result = _score(
        trend=25,
        momentum=20,
        location=25,
        smc=15,
        regime=regime,
    )
    breakdown = result.technical_breakdown.to_dict()
    weights = tuple(item["weight"] for item in breakdown.values())
    raw_max = tuple(item["raw_max"] for item in breakdown.values())

    assert result.technical_signal_score == 100
    assert weights == _EXPECTED_WEIGHTS[regime]
    assert sum(weights) == 100
    assert raw_max == (25, 20, 25, 15)
    assert tuple(TECHNICAL_REGIME_WEIGHTS[regime].values()) == weights


def test_exact_2_point_5_total_rounds_half_up_to_3_once_at_end():
    result = _score(
        trend=0,
        momentum=5,
        location=0,
        smc=0,
        regime="volatile",
    )

    assert result.technical_breakdown.momentum.contribution == 2.5
    assert result.technical_signal_score == 3


def test_fractional_contributions_are_not_truncated_per_component():
    result = _score(
        trend=1,
        momentum=1,
        location=1,
        smc=1,
        regime="trending_up",
    )
    breakdown = result.technical_breakdown

    assert breakdown.trend.contribution == pytest.approx(1.6)
    assert breakdown.momentum.contribution == pytest.approx(1.0)
    assert breakdown.location.contribution == pytest.approx(0.8)
    assert breakdown.smc.contribution == pytest.approx(4 / 3)
    assert result.technical_signal_score == 5


def test_result_carries_only_target_versions_and_structured_smc_evidence():
    canonical = _canonical_smc(
        buy_subtotal=12,
        buy_penalty=4,
        buy_cap=7,
        buy_evidence="H4_CONFIRMED_CHOCH_CAP_4",
    )
    result = _score(canonical_smc=canonical, smc=12)
    payload = result.to_dict()

    assert result.scoring_version == SCANNER_V4_SCORING_VERSION == "scanner-v4"
    assert result.weight_policy_version == TECHNICAL_WEIGHT_POLICY_VERSION
    assert result.smc_raw_semantics_version == SMC_TECHNICAL_RAW_VERSION
    assert result.smc_source_scoring_version == SMC_SCORER_VERSION
    assert result.technical_breakdown.smc.raw == 12
    assert payload["smc_evidence"] == {
        "side": "buy",
        "raw_semantics_version": SMC_TECHNICAL_RAW_VERSION,
        "source_scoring_version": SMC_SCORER_VERSION,
        "source_contract_version": SMC_SCORING_CONTRACT_VERSION,
        "source_domain_version": SMC_DOMAIN_VERSION,
        "raw_subtotal": 12,
        "base_components": {
            "structure_score": 5,
            "zone_score": 5,
            "ltf_confirmation_score": 2,
            "technical_validation_score": 0,
        },
        "source_score": 7,
        "penalty_points": 4,
        "applied_cap": 7,
        "penalties": ["H4_CONFIRMED_CHOCH_CAP_4"],
        "caps": ["H4_CONFIRMED_CHOCH_CAP_4"],
        "reason_codes": ["H4_CONFIRMED_CHOCH_CAP_4"],
        "smc_reason": "H4_CONFIRMED_CHOCH_CAP_4",
        "selected_zone": {
            "zone_id": "zone-buy",
            "direction": "buy",
            "timeframe": "H4",
            "family": "demand",
            "zone_type": "demand_zone",
            "low": 90.0,
            "high": 95.0,
            "level": 92.5,
            "zone_quality_score": 80,
            "zone_relevance_score": 70,
            "zone_setup_score": 85,
            "liquidity_sweep_linked": False,
            "linked_sweep_id": None,
            "linked_sweep_distance_atr": None,
            "linked_sweep_time_delta": None,
            "source": "smc_selected",
            "scoring_version": SMC_SCORER_VERSION,
            "domain_version": SMC_DOMAIN_VERSION,
            "selection_reason_codes": ["H4_TIMEFRAME_PREFERRED"],
            "type": "demand_zone",
        },
        "selected_zone_id": "zone-buy",
        "selected_zone_type": "demand_zone",
        "selected_zone_timeframe": "H4",
    }
    assert "risk_condition" not in payload
    assert "macro_alignment" not in payload
    assert "total" not in payload
    assert "rating" not in payload


@pytest.mark.parametrize(
    ("evidence_code", "penalty", "cap"),
    [
        ("AI_ZONE_WEAK", 2, None),
        ("M15_NO_CONFIRMATION", 3, None),
        ("H1_CONFIRMED_CHOCH_CAP_8", 2, 8),
        ("H4_CONFIRMED_CHOCH_CAP_4", 0, 4),
    ],
)
def test_ai_m15_and_choch_evidence_never_mutates_smc_raw_or_technical_score(
    evidence_code: str,
    penalty: int,
    cap: int | None,
):
    baseline = _canonical_smc(buy_subtotal=12)
    gated = _canonical_smc(
        buy_subtotal=12,
        buy_penalty=penalty,
        buy_cap=cap,
        buy_evidence=evidence_code,
    )

    base_result = _score(canonical_smc=baseline, smc=12)
    gated_result = _score(canonical_smc=gated, smc=12)

    assert base_result.technical_signal_score == gated_result.technical_signal_score
    assert base_result.technical_breakdown == gated_result.technical_breakdown
    assert gated_result.smc_evidence.source_score == gated.side("buy").score
    assert evidence_code in gated_result.smc_evidence.reason_codes


def test_excluded_domains_cannot_be_supplied_to_the_pure_scorer():
    parameters = tuple(inspect.signature(score_technical_signal).parameters)

    assert parameters == (
        "side",
        "trend_raw",
        "momentum_raw",
        "location_raw",
        "canonical_smc",
        "regime",
    )
    excluded = {
        "risk",
        "news",
        "spread",
        "atr",
        "macro",
        "correlation",
        "ai_adjustment",
        "choch",
    }
    assert excluded.isdisjoint(parameters)


@pytest.mark.parametrize(
    ("overrides", "expected_path"),
    [
        ({"side": None}, "side"),
        ({"side": "BUY"}, "side"),
        ({"side": "neutral"}, "side"),
        ({"regime": None}, "regime"),
        ({"regime": "trend_up"}, "regime"),
        ({"regime": ""}, "regime"),
        ({"trend": None}, "trend_raw"),
        ({"trend": True}, "trend_raw"),
        ({"trend": 1.0}, "trend_raw"),
        ({"trend": "1"}, "trend_raw"),
        ({"trend": -1}, "trend_raw"),
        ({"trend": 26}, "trend_raw"),
        ({"momentum": None}, "momentum_raw"),
        ({"momentum": False}, "momentum_raw"),
        ({"momentum": -1}, "momentum_raw"),
        ({"momentum": 21}, "momentum_raw"),
        ({"location": None}, "location_raw"),
        ({"location": True}, "location_raw"),
        ({"location": -1}, "location_raw"),
        ({"location": 26}, "location_raw"),
        ({"canonical_smc": None}, "canonical_smc"),
    ],
)
def test_missing_or_invalid_inputs_raise_typed_data_error_without_score(
    overrides: dict[str, object],
    expected_path: str,
):
    arguments: dict[str, object] = {
        "side": "buy",
        "trend": 20,
        "momentum": 15,
        "location": 20,
        "smc": 10,
        "regime": "trending_up",
        "canonical_smc": _canonical_smc(),
    }
    arguments.update(overrides)

    with pytest.raises(TechnicalScoreDataError) as exc_info:
        _score(**arguments)

    assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE
    assert exc_info.value.path == expected_path


def test_truly_omitted_inputs_raise_typed_data_error_instead_of_type_error():
    canonical = _canonical_smc()
    calls = (
        lambda: score_technical_signal(
            trend_raw=1,
            momentum_raw=1,
            location_raw=1,
            canonical_smc=canonical,
            regime="unknown",
        ),
        lambda: score_technical_signal(
            "buy",
            momentum_raw=1,
            location_raw=1,
            canonical_smc=canonical,
            regime="unknown",
        ),
        lambda: score_technical_signal(
            "buy",
            trend_raw=1,
            location_raw=1,
            canonical_smc=canonical,
            regime="unknown",
        ),
        lambda: score_technical_signal(
            "buy",
            trend_raw=1,
            momentum_raw=1,
            canonical_smc=canonical,
            regime="unknown",
        ),
        lambda: score_technical_signal(
            "buy",
            trend_raw=1,
            momentum_raw=1,
            location_raw=1,
            regime="unknown",
        ),
        lambda: score_technical_signal(
            "buy",
            trend_raw=1,
            momentum_raw=1,
            location_raw=1,
            canonical_smc=canonical,
        ),
    )

    for call in calls:
        with pytest.raises(TechnicalScoreDataError) as exc_info:
            call()
        assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE


def test_canonical_smc_must_have_both_valid_sides_and_exact_versions():
    one_side = SmcScoringResult(
        scoring_version=SMC_SCORER_VERSION,
        sides={"buy": _smc_side("buy", subtotal=10)},
    )
    wrong_scorer = replace(_canonical_smc(), scoring_version="smc-v999")
    wrong_contract = replace(_canonical_smc(), contract_version="smc-contract-old")

    for value, path in (
        (one_side, "canonical_smc.sides"),
        (wrong_scorer, "canonical_smc.scoring_version"),
        (wrong_contract, "canonical_smc.contract_version"),
    ):
        with pytest.raises(TechnicalScoreDataError) as exc_info:
            _score(canonical_smc=value)
        assert exc_info.value.path == path
        assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("structure_score", True),
        ("structure_score", 6),
        ("zone_score", -1),
        ("ltf_confirmation_score", 4),
        ("technical_validation_score", None),
        ("subtotal", 15),
        ("penalty_points", -1),
        ("applied_cap", 16),
        ("total", 15),
        ("scoring_version", "smc-v1"),
        ("domain_version", "smc-domain-old"),
    ],
)
def test_malformed_smc_breakdown_is_typed_fail_closed(field: str, value: object):
    canonical = _canonical_smc(buy_subtotal=10)
    canonical.side("buy").breakdown[field] = value

    with pytest.raises(TechnicalScoreDataError) as exc_info:
        _score(canonical_smc=canonical)

    assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE
    assert exc_info.value.path.startswith("canonical_smc.sides.buy")


def test_malformed_unselected_smc_side_also_invalidates_canonical_result():
    canonical = _canonical_smc()
    canonical.side("sell").breakdown["subtotal"] = 15

    with pytest.raises(TechnicalScoreDataError) as exc_info:
        _score(side="buy", canonical_smc=canonical)

    assert exc_info.value.path == "canonical_smc.sides.sell.breakdown.subtotal"


def test_nonfinite_or_inconsistent_selected_zone_evidence_is_rejected():
    nonfinite = _canonical_smc()
    nonfinite.side("buy").selected_zone["distance"] = float("nan")
    wrong_direction = _canonical_smc()
    wrong_direction.side("buy").selected_zone["direction"] = "sell"

    for canonical in (nonfinite, wrong_direction):
        with pytest.raises(TechnicalScoreDataError) as exc_info:
            _score(canonical_smc=canonical)
        assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE


@pytest.mark.parametrize(
    "field",
    ("low", "high", "level", "linked_sweep_distance_atr"),
)
def test_unrepresentably_large_selected_zone_numbers_are_typed_fail_closed(
    field: str,
):
    canonical = _canonical_smc()
    canonical.side("buy").selected_zone[field] = 10**10_000

    with pytest.raises(TechnicalScoreDataError) as exc_info:
        _score(canonical_smc=canonical)

    assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE
    assert exc_info.value.path.endswith(field)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("low", "not-a-number"),
        ("high", float("inf")),
        ("level", 999.0),
        ("family", "unexpected"),
        ("timeframe", "M15"),
        ("liquidity_sweep_linked", "false"),
        ("zone_quality_score", 101),
        ("zone_setup_score", True),
        ("scoring_version", "smc-v1"),
        ("domain_version", "smc-domain-old"),
        ("source", "forged-source"),
    ],
)
def test_every_malformed_selected_zone_field_is_typed_fail_closed(
    field: str,
    value: object,
):
    canonical = _canonical_smc(buy_subtotal=12)
    canonical.side("buy").selected_zone[field] = value

    with pytest.raises(TechnicalScoreDataError) as exc_info:
        _score(canonical_smc=canonical, smc=12)

    assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE
    assert exc_info.value.path.startswith("canonical_smc.sides.buy.selected_zone")


def test_selected_zone_family_and_type_must_each_match_side():
    conflicting_family = _canonical_smc()
    conflicting_family.side("buy").selected_zone["family"] = "supply"
    conflicting_type = _canonical_smc()
    conflicting_type.side("buy").selected_zone["zone_type"] = "supply_zone"
    conflicting_type.side("buy").selected_zone["type"] = "supply_zone"

    for canonical in (conflicting_family, conflicting_type):
        with pytest.raises(TechnicalScoreDataError) as exc_info:
            _score(canonical_smc=canonical)
        assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE


def test_unknown_or_non_string_smc_keys_are_typed_fail_closed():
    cases = []
    unknown_breakdown = _canonical_smc()
    unknown_breakdown.side("buy").breakdown["risk_condition"] = 15
    cases.append(unknown_breakdown)
    unknown_zone = _canonical_smc()
    unknown_zone.side("buy").selected_zone["extra"] = "value"
    cases.append(unknown_zone)
    mixed_zone_keys = _canonical_smc()
    mixed_zone_keys.side("buy").selected_zone[1] = "value"
    cases.append(mixed_zone_keys)

    for canonical in cases:
        with pytest.raises(TechnicalScoreDataError) as exc_info:
            _score(canonical_smc=canonical)
        assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE


def test_zone_component_and_no_zone_arithmetic_cannot_inflate_smc_raw():
    inconsistent_zone = _canonical_smc(buy_subtotal=12)
    inconsistent_zone.side("buy").breakdown["zone_score"] = 4
    inconsistent_zone.side("buy").breakdown["ltf_confirmation_score"] = 3
    no_zone = _canonical_smc(buy_subtotal=5)
    no_zone.side("buy").breakdown["zone_score"] = 1
    no_zone.side("buy").breakdown["structure_score"] = 4

    for canonical in (inconsistent_zone, no_zone):
        with pytest.raises(TechnicalScoreDataError) as exc_info:
            _score(canonical_smc=canonical)
        assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE


def test_real_canonical_smc_result_is_accepted_by_target_projection():
    canonical = score_smc(
        {
            "confluence": {
                "buy_score": 3,
                "sell_score": 2,
                "buy_reason_codes": ["BUY_STRUCTURE"],
                "sell_reason_codes": ["SELL_STRUCTURE"],
            },
            "H4": {},
            "H1": {},
        },
        {
            "price": 100.0,
            "atr_h4": 1.0,
            "atr_d1": 1.0,
            "support_zones": [],
            "resistance_zones": [],
        },
        {"primary": "trend_up"},
    )

    result = _score(canonical_smc=canonical, smc=3)

    assert result.technical_breakdown.smc.raw == 3
    assert result.smc_evidence.base_components == {
        "structure_score": 3,
        "zone_score": 0,
        "ltf_confirmation_score": 0,
        "technical_validation_score": 0,
    }


def test_real_canonical_selected_zone_and_linked_sweep_are_preserved_as_evidence():
    zone = {
        "zone_id": "smcz-live-buy",
        "type": "demand_zone",
        "family": "demand",
        "direction": "buy",
        "low": 90.0,
        "high": 95.0,
        "index": 10,
        "origin_index": 10,
        "time": "2026-07-01T10:00:00+00:00",
        "origin_time": "2026-07-01T10:00:00+00:00",
        "formation_start_index": 7,
        "departure_end_index": 11,
        "freshness_bars": 5,
        "age_bars": 5,
        "age_minutes": 1_200,
        "lifecycle_stale": False,
        "lifecycle_broken": False,
        "lifecycle_mitigated": False,
        "independent_retest_count": 0,
        "bars_spent_inside": 0,
        "mitigation_ratio": None,
        "displacement_multiple": 2.0,
        "zone_location": "discount",
        "liquidity_sweep_linked": True,
        "linked_sweep_id": "sweep-live-buy",
        "linked_sweep_distance_atr": 0.1,
        "linked_sweep_time_delta": -1,
        "broken": False,
        "stale": False,
        "test_count": 0,
    }
    canonical = score_smc(
        {
            "symbol": "TEST",
            "confluence": {
                "buy_score": 5,
                "sell_score": 0,
                "buy_reason_codes": ["BUY_STRUCTURE"],
                "sell_reason_codes": [],
            },
            "H4": {
                "structure": "HH/HL",
                "bos": True,
                "choch": False,
                "displacement": "bullish",
                "demand_zones": [zone],
                "supply_zones": [],
                "order_blocks": [],
                "fvg": [],
            },
            "H1": {
                "structure": "HH/HL",
                "bos": True,
                "choch": False,
                "displacement": "bullish",
                "demand_zones": [],
                "supply_zones": [],
                "order_blocks": [],
                "fvg": [],
                "zone_link_sweeps": {"swept_lows": []},
            },
        },
        {
            "price": 100.0,
            "atr_h4": 10.0,
            "atr_d1": 10.0,
            "support_zones": [{"level": 92.5, "source": "technical"}],
            "resistance_zones": [],
        },
        {"primary": "trend_up"},
    )
    source = canonical.side("buy")

    result = _score(
        canonical_smc=canonical,
        smc=source.breakdown["subtotal"],
    )

    assert result.smc_evidence.selected_zone == source.selected_zone
    assert result.smc_evidence.selected_zone["linked_sweep_id"] == "sweep-live-buy"
    assert result.smc_evidence.selected_zone["linked_sweep_time_delta"] == -1
    assert result.smc_evidence.raw_subtotal == source.breakdown["subtotal"]
    assert result.technical_breakdown.smc.raw == source.breakdown["subtotal"]


def test_smc_projection_uses_subtotal_not_adjusted_source_score():
    canonical = _canonical_smc(
        buy_subtotal=15,
        buy_penalty=7,
        buy_cap=4,
        buy_evidence="H4_CONFIRMED_CHOCH_CAP_4",
    )

    projection = project_smc_technical_raw(canonical, "buy")

    assert projection.raw == 15
    assert projection.evidence.source_score == 4
    assert projection.evidence.penalty_points == 7
    assert projection.evidence.applied_cap == 4


def test_scorer_does_not_mutate_inputs_and_evidence_snapshot_is_deeply_immutable():
    canonical = _canonical_smc(buy_subtotal=12)
    before = deepcopy(canonical.to_dict())

    result = _score(canonical_smc=canonical, smc=12)

    assert canonical.to_dict() == before
    with pytest.raises(TypeError):
        result.smc_evidence.selected_zone["zone_id"] = "changed"
    with pytest.raises(TypeError):
        result.smc_evidence.selected_zone["selection_reason_codes"][0] = "changed"


def test_gap_is_only_the_absolute_difference_between_two_technical_scores():
    canonical = _canonical_smc(buy_subtotal=15, sell_subtotal=0)
    buy = _score(
        side="buy",
        trend=25,
        momentum=20,
        location=25,
        smc=15,
        canonical_smc=canonical,
    )
    sell = _score(
        side="sell",
        trend=0,
        momentum=0,
        location=0,
        smc=0,
        canonical_smc=canonical,
    )

    assert technical_signal_score_gap(buy, sell) == 100
    assert technical_signal_score_gap(None, sell) is None
    assert technical_signal_score_gap(buy, None) is None


def test_gap_rejects_side_swaps_instead_of_guessing():
    canonical = _canonical_smc()
    buy = _score(side="buy", canonical_smc=canonical)
    sell = _score(side="sell", canonical_smc=canonical)

    with pytest.raises(TechnicalScoreDataError):
        technical_signal_score_gap(replace(buy, side="sell"), sell)


def test_seeded_property_score_is_bounded_deterministic_monotonic_and_exact():
    rng = random.Random(20260813)
    maxima = (25, 20, 25, 15)
    for _ in range(1_000):
        regime = rng.choice(_REGIMES)
        side = rng.choice(("buy", "sell"))
        trend = rng.randint(0, 25)
        momentum = rng.randint(0, 20)
        location = rng.randint(0, 25)
        smc = rng.randint(0, 15)
        penalty = rng.randint(0, smc)
        cap = rng.choice((None, rng.randint(0, 15)))
        canonical = _canonical_smc(
            buy_subtotal=smc if side == "buy" else rng.randint(0, 15),
            sell_subtotal=smc if side == "sell" else rng.randint(0, 15),
            buy_penalty=penalty if side == "buy" else 0,
            sell_penalty=penalty if side == "sell" else 0,
            buy_cap=cap if side == "buy" else None,
            sell_cap=cap if side == "sell" else None,
        )
        result = _score(
            side=side,
            trend=trend,
            momentum=momentum,
            location=location,
            smc=smc,
            regime=regime,
            canonical_smc=canonical,
        )
        repeated = _score(
            side=side,
            trend=trend,
            momentum=momentum,
            location=location,
            smc=smc,
            regime=regime,
            canonical_smc=canonical,
        )

        assert type(result.technical_signal_score) is int
        assert 0 <= result.technical_signal_score <= 100
        assert result == repeated
        assert result.to_dict() == repeated.to_dict()

        raw = (trend, momentum, location, smc)
        weights = _EXPECTED_WEIGHTS[regime]
        exact_total = sum(
            (
                Fraction(value * weight, maximum)
                for value, maximum, weight in zip(raw, maxima, weights)
            ),
            Fraction(0, 1),
        )
        quotient, remainder = divmod(exact_total.numerator, exact_total.denominator)
        expected = quotient + int(remainder * 2 >= exact_total.denominator)
        assert result.technical_signal_score == expected

        component_index = rng.randrange(4)
        if raw[component_index] < maxima[component_index]:
            increased = list(raw)
            increased[component_index] += 1
            increased_smc = _canonical_smc(
                buy_subtotal=increased[3] if side == "buy" else 0,
                sell_subtotal=increased[3] if side == "sell" else 0,
            )
            raised = _score(
                side=side,
                trend=increased[0],
                momentum=increased[1],
                location=increased[2],
                smc=increased[3],
                regime=regime,
                canonical_smc=increased_smc,
            )
            assert raised.technical_signal_score >= result.technical_signal_score


def test_rounding_is_independent_of_callers_global_decimal_context():
    context = getcontext()
    original_precision = context.prec
    original_rounding = context.rounding
    original_inexact_trap = context.traps[Inexact]
    try:
        context.prec = 2
        context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        first = _score(trend=1, momentum=1, location=1, smc=1)
        context.prec = 50
        second = _score(trend=1, momentum=1, location=1, smc=1)
    finally:
        context.prec = original_precision
        context.rounding = original_rounding
        context.traps[Inexact] = original_inexact_trap

    assert first == second
    assert first.technical_signal_score == 5


def test_forged_public_result_is_rejected_before_gap_calculation():
    canonical = _canonical_smc()
    buy = _score(side="buy", canonical_smc=canonical)

    for field, value in (
        ("technical_signal_score", -999),
        ("technical_signal_score", None),
        ("technical_signal_score", True),
        ("scoring_version", "scanner-v3"),
        ("regime", "trend_up"),
    ):
        with pytest.raises(TechnicalScoreDataError):
            replace(buy, **{field: value})


def test_public_smc_evidence_is_self_validating_and_deeply_immutable():
    result = _score(smc=12, canonical_smc=_canonical_smc(buy_subtotal=12))
    evidence = result.smc_evidence
    invalid_overrides = (
        {"source_contract_version": "forged-contract"},
        {"source_domain_version": "forged-domain"},
        {"source_score": -1},
        {"penalty_points": -1},
        {"base_components": {"structure_score": 999}},
        {"raw_subtotal": 11},
        {"side": "sell"},
    )

    for overrides in invalid_overrides:
        with pytest.raises(TechnicalScoreDataError) as exc_info:
            replace(evidence, **overrides)
        assert exc_info.value.code == TECHNICAL_DATA_UNAVAILABLE

    refrozen = replace(
        evidence,
        base_components=dict(evidence.base_components),
        selected_zone=dict(evidence.selected_zone),
    )
    with pytest.raises(TypeError):
        refrozen.base_components["structure_score"] = 0
    with pytest.raises(TypeError):
        refrozen.selected_zone["zone_id"] = "forged"


def test_projection_and_result_bind_smc_evidence_to_their_side_and_raw():
    result = _score(smc=3, canonical_smc=_canonical_smc(buy_subtotal=3))
    projection = project_smc_technical_raw(_canonical_smc(buy_subtotal=3), "buy")

    with pytest.raises(TechnicalScoreDataError):
        replace(projection, raw=2)

    sell_evidence = replace(result.smc_evidence, side="sell")
    with pytest.raises(TechnicalScoreDataError):
        replace(result, smc_evidence=sell_evidence)


def test_locked_constants_are_immutable_and_complete():
    assert dict(TECHNICAL_COMPONENT_RAW_MAX) == {
        "trend": 25,
        "momentum": 20,
        "location": 25,
        "smc": 15,
    }
    assert set(TECHNICAL_REGIME_WEIGHTS) == set(_REGIMES)
    with pytest.raises(TypeError):
        TECHNICAL_COMPONENT_RAW_MAX["trend"] = 99
    with pytest.raises(TypeError):
        TECHNICAL_REGIME_WEIGHTS["ranging"]["trend"] = 99


def test_step03_module_is_not_wired_into_live_runtime():
    project_root = Path(__file__).resolve().parents[1]
    runtime_consumers = (
        project_root / "core" / "analysis_pipeline.py",
        project_root / "core" / "scanner.py",
        project_root / "core" / "system_backtest_engine.py",
        project_root / "controllers" / "scanner_controller.py",
    )

    assert SCANNER_SCORER_VERSION == "scanner-v3"
    assert SCANNER_FEATURE_VERSION == "scanner-features-v3"
    for consumer in runtime_consumers:
        assert "technical_signal_scorer" not in consumer.read_text(encoding="utf-8")
