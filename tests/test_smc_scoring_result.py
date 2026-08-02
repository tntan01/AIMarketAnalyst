"""Unit tests for the neutral canonical SMC scoring result contract."""

from __future__ import annotations

import json
from typing import Any

import pytest

import core.smc_scoring_result as result_module
from core.smc_scoring_result import (
    SMC_SCORING_CONTRACT_VERSION,
    SmcScoringResult,
    SmcSideScoringResult,
)


def _side_payload(
    score: int | None = 12,
    *,
    zone: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "score": score,
        "breakdown": {
            "side": "buy",
            "total": score,
            "structure_score": 5,
            "zone_score": 4,
            "ltf_confirmation_score": 2,
            "technical_validation_score": 1,
            "subtotal": 12,
            "penalty_points": 0,
            "applied_cap": None,
            "penalties": [],
            "caps": [],
            "selected_zone_id": "z-buy" if zone else None,
            "reason_codes": ["CANONICAL_ZONE_SELECTED"],
            "scoring_version": "smc-v2",
        },
        "selected_zone": (
            {
                "zone_id": "z-buy",
                "direction": "buy",
                "timeframe": "H4",
                "family": "demand",
                "zone_type": "demand_zone",
                "low": 1.098,
                "high": 1.099,
                "level": 1.0985,
                "zone_quality_score": 82,
                "zone_relevance_score": 70,
                "zone_setup_score": 77,
            }
            if zone
            else None
        ),
        "selected_zone_id": "z-buy" if zone else None,
        "selected_zone_type": "demand_zone" if zone else None,
        "selected_zone_timeframe": "H4" if zone else None,
        "reason_codes": ["CANONICAL_ZONE_SELECTED"],
    }
    return payload


def _full_result() -> SmcScoringResult:
    return SmcScoringResult(
        scoring_version="smc-v2",
        sides={
            "buy": SmcSideScoringResult.from_dict(_side_payload(12, zone=True)),
            "sell": SmcSideScoringResult.from_dict(
                _side_payload(0, zone=False)
            ),
        },
    )


def test_contract_version_matches_plan():
    assert SMC_SCORING_CONTRACT_VERSION == "smc-scoring-canonical-2026-08"


def test_round_trip_preserves_all_fields():
    original = _full_result()
    restored = SmcScoringResult.from_dict(original.to_dict())

    assert restored == original
    assert restored.scoring_version == "smc-v2"
    assert restored.contract_version == SMC_SCORING_CONTRACT_VERSION
    assert set(restored.sides) == {"buy", "sell"}
    assert restored.side("buy").score == 12
    assert restored.side("buy").selected_zone_id == "z-buy"
    assert restored.side("buy").selected_zone_type == "demand_zone"
    assert restored.side("buy").selected_zone_timeframe == "H4"
    assert restored.side("buy").breakdown["total"] == 12
    assert restored.side("sell").score == 0
    assert restored.side("sell").selected_zone is None


def test_json_round_trip_is_deterministic_and_ordered():
    result = _full_result()
    first = json.dumps(result.to_dict(), sort_keys=False)
    second = json.dumps(result.to_dict(), sort_keys=False)

    assert first == second
    assert list(result.to_dict()["sides"]) == ["buy", "sell"]


def test_old_payload_with_legacy_shadow_fields_reads_canonical_sides():
    old_payload = {
        "contract_version": "smc-phase8-active-v2",
        "policy": {
            "requested_mode": "shadow",
            "effective_mode": "v2",
            "decision_source": "smc-v2",
            "shadow_enabled": True,
            "decision_impact_allowed": True,
        },
        "legacy": {"buy": {"smc_quality": 5}, "sell": {"smc_quality": 5}},
        "active": {"buy": {"smc_quality": 5}, "sell": {"smc_quality": 5}},
        "shadow": {
            "buy": {"smc_quality": 12},
            "sell": {"smc_quality": 0},
        },
        "decision": {
            "buy": {"smc_quality": 12},
            "sell": {"smc_quality": 0},
        },
        "comparison": {
            "score_delta": {"buy": 7, "sell": -5},
            "decision_changed": True,
        },
        "shadow_status": "v2_active_with_legacy_comparison",
        "sides": {
            "buy": _side_payload(12, zone=True),
            "sell": _side_payload(0, zone=False),
        },
    }

    result = SmcScoringResult.from_dict(old_payload)

    # The canonical sides are read; the legacy/shadow payload is inert.
    assert result.scoring_version == "smc-v2"
    assert result.side("buy").score == 12
    assert result.side("buy").selected_zone_id == "z-buy"
    assert result.side("sell").score == 0
    assert result.side("sell").selected_zone is None
    # No v1 branch was selected: the parsed result exposes no legacy score.
    assert result.side("buy").breakdown["total"] == 12
    assert "legacy" not in result.to_dict()
    assert "shadow" not in result.to_dict()
    assert "comparison" not in result.to_dict()


def test_from_dict_ignores_unknown_and_malformed_keys():
    payload = {
        "contract_version": "smc-scoring-canonical-2026-08",
        "scoring_version": "smc-v2",
        "sides": {
            "buy": _side_payload(9),
            "sell": "not-a-dict",
            "weird_side": _side_payload(3),
        },
        "extra_unknown": {"anything": 1},
    }

    result = SmcScoringResult.from_dict(payload)

    assert result.side("buy").score == 9
    assert result.side("sell") is None
    assert set(result.sides) == {"buy"}
    assert result.to_dict()["sides"] == {"buy": result.side("buy").to_dict()}


def test_from_dict_missing_sides_returns_empty_result():
    result = SmcScoringResult.from_dict({"scoring_version": "smc-v2"})

    assert result.sides == {}
    assert result.side("buy") is None
    assert result.scoring_version == "smc-v2"
    assert result.contract_version == SMC_SCORING_CONTRACT_VERSION


def test_from_dict_tolerates_non_dict_input():
    for value in (None, "text", [], 42):
        result = SmcScoringResult.from_dict(value)
        assert result.sides == {}
        assert result.scoring_version == "smc-v2"


def test_scoring_version_defaults_to_canonical_when_absent():
    result = SmcScoringResult.from_dict({"sides": {}})

    assert result.scoring_version == "smc-v2"


def test_side_payload_round_trip_ignores_unknown_keys():
    side = SmcSideScoringResult.from_dict(
        {
            **_side_payload(11),
            "shadow_selected_zone": {"zone_id": "ghost"},
            "legacy_score": 5,
            "active_version": "smc-v1",
        }
    )

    restored = SmcSideScoringResult.from_dict(side.to_dict())

    assert restored == side
    assert restored.score == 11
    assert "shadow_selected_zone" not in restored.to_dict()
    assert "legacy_score" not in restored.to_dict()
    assert "active_version" not in restored.to_dict()


@pytest.mark.parametrize(
    "name",
    [
        "resolve_smc_scoring_policy",
        "normalize_smc_scoring_mode",
        "SMC_MODE_LEGACY",
        "SMC_MODE_SHADOW",
        "SMC_MODE_V2",
        "build_smc_phase0_diagnostics",
        "apply_smc_score_override",
    ],
)
def test_contract_has_no_mode_selector_api(name):
    assert not hasattr(result_module, name)


def test_public_names_are_neutral():
    expected_public = {
        "SMC_SCORING_CONTRACT_VERSION",
        "VALID_SIDES",
        "SmcScoringResult",
        "SmcSideScoringResult",
    }
    assert set(result_module.__dict__) >= expected_public
    # The versioned constant stays private so no v2/legacy/shadow name leaks
    # into the module's public surface.
    assert "SMC_SCORER_V2_VERSION" not in result_module.__dict__
    for name in expected_public:
        lowered = name.lower()
        for forbidden in ("v1", "v2", "legacy", "shadow"):
            assert forbidden not in lowered, name
