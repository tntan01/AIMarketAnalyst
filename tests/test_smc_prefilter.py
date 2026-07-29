"""Unit contracts for the Tier-1 canonical SMC prefilter predicate."""

from __future__ import annotations

from copy import deepcopy
from unittest.mock import patch

import pytest

from core.smc_prefilter import (
    NO_ACTIONABLE_SMC_ZONE,
    SMC_PREFILTER_ERROR_FAIL_OPEN,
    evaluate_post_context_prefilter,
)
from core.smc_scoring_contract import build_smc_phase0_diagnostics


_FAMILY_KEYS = {
    "demand": "demand_zones",
    "supply": "supply_zones",
    "order_block": "order_blocks",
    "fvg": "fvg",
}


def _technical() -> dict:
    return {
        "price": 100.0,
        "atr_h4": 10.0,
        "atr_d1": 12.0,
        "support_zones": [{"level": 92.5}],
        "resistance_zones": [{"level": 107.5}],
    }


def _context() -> dict:
    return {
        "symbol": "TEST",
        "H4": {key: [] for key in _FAMILY_KEYS.values()},
        "H1": {key: [] for key in _FAMILY_KEYS.values()},
        "confluence": {"buy_score": 0, "sell_score": 0},
    }


def _zone(family: str, side: str, *, zone_id: str) -> dict:
    bullish = side == "buy"
    zone_type = {
        "demand": "demand_zone",
        "supply": "supply_zone",
        "order_block": "bullish_order_block" if bullish else "bearish_order_block",
        "fvg": "bullish_fvg" if bullish else "bearish_fvg",
    }[family]
    return {
        "zone_id": zone_id,
        "type": zone_type,
        "family": family,
        "direction": side,
        "low": 90.0 if bullish else 105.0,
        "high": 95.0 if bullish else 110.0,
        "origin_index": 10,
        "departure_end_index": 11,
        "origin_time": "2026-07-01T10:00:00+00:00",
        "freshness_bars": 5,
        "age_bars": 5,
        "displacement_multiple": 2.0,
        "zone_location": "discount" if bullish else "premium",
        "broken": False,
        "stale": False,
        "test_count": 0,
    }


@pytest.mark.parametrize("timeframe", ("H4", "H1"))
@pytest.mark.parametrize("family", tuple(_FAMILY_KEYS))
def test_canonical_prefilter_survives_each_raw_family_and_timeframe(
    timeframe: str,
    family: str,
) -> None:
    context = _context()
    side = "buy" if family != "supply" else "sell"
    expected_id = f"{timeframe}-{family}-{side}"
    context[timeframe][_FAMILY_KEYS[family]].append(
        _zone(family, side, zone_id=expected_id)
    )

    decision = evaluate_post_context_prefilter(
        mode="v2",
        smc=context,
        technical=_technical(),
        market_regime={"primary": "trend_up"},
    )

    assert decision["should_reject"] is False
    assert decision["fail_open"] is False
    assert decision["selected_zone_ids"][side] == expected_id
    assert decision["raw_counts"][timeframe][family] == 1
    assert decision["precomputed_v2_result"][side]["selected_zone_id"] == expected_id


def test_canonical_prefilter_rejects_only_when_both_sides_lack_selected_zones() -> None:
    decision = evaluate_post_context_prefilter(
        mode="v2",
        smc=_context(),
        technical=_technical(),
        market_regime={"primary": "range"},
    )

    assert decision["should_reject"] is True
    assert decision["reason_code"] == NO_ACTIONABLE_SMC_ZONE
    assert decision["selected_zone_ids"] == {"buy": None, "sell": None}
    assert decision["fail_open"] is False


@pytest.mark.parametrize("invalid_field", ("broken", "origin_index"))
def test_broken_or_invalid_zone_uses_canonical_reject(
    invalid_field: str,
) -> None:
    context = _context()
    zone = _zone("demand", "buy", zone_id=f"invalid-{invalid_field}")
    zone[invalid_field] = True if invalid_field == "broken" else -1
    context["H4"]["demand_zones"].append(zone)

    decision = evaluate_post_context_prefilter(
        mode="v2",
        smc=context,
        technical=_technical(),
    )

    assert decision["should_reject"] is True
    assert decision["fail_open"] is False
    assert decision["reason_code"] == NO_ACTIONABLE_SMC_ZONE


@pytest.mark.parametrize(
    ("family", "side"),
    (("demand", "buy"), ("supply", "sell")),
)
def test_buy_and_sell_selection_are_independent(family: str, side: str) -> None:
    context = _context()
    context["H4"][_FAMILY_KEYS[family]].append(
        _zone(family, side, zone_id=f"only-{side}")
    )

    decision = evaluate_post_context_prefilter(
        mode="v2",
        smc=context,
        technical=_technical(),
    )

    opposite = "sell" if side == "buy" else "buy"
    assert decision["should_reject"] is False
    assert decision["selected_zone_ids"] == {
        side: f"only-{side}",
        opposite: None,
    }


@pytest.mark.parametrize("mode", ("legacy", "shadow"))
def test_legacy_and_shadow_always_fail_open(mode: str) -> None:
    decision = evaluate_post_context_prefilter(
        mode=mode,
        smc=_context(),
        technical=_technical(),
    )

    assert decision["mode"] == mode
    assert decision["should_reject"] is False
    assert decision["fail_open"] is True
    assert decision["reason_code"] == SMC_PREFILTER_ERROR_FAIL_OPEN
    assert decision["precomputed_v2_result"] is None


@pytest.mark.parametrize(
    "technical",
    (
        {"price": 0, "atr_h4": 10},
        {"price": float("nan"), "atr_h4": 10},
        {"price": 100, "atr_h4": 0, "atr_d1": 0},
        {"price": 100, "atr_h4": float("inf")},
    ),
)
def test_invalid_price_or_atr_fails_open(technical: dict) -> None:
    decision = evaluate_post_context_prefilter(
        mode="v2",
        smc=_context(),
        technical=technical,
    )

    assert decision["should_reject"] is False
    assert decision["fail_open"] is True
    assert decision["reason_code"] == SMC_PREFILTER_ERROR_FAIL_OPEN


def test_malformed_context_fails_open() -> None:
    context = _context()
    context["H1"]["fvg"] = {"not": "a list"}

    decision = evaluate_post_context_prefilter(
        mode="v2",
        smc=context,
        technical=_technical(),
    )

    assert decision["should_reject"] is False
    assert decision["fail_open"] is True


def test_v2_scorer_exception_fails_open() -> None:
    with patch(
        "core.smc_prefilter.score_smc_v2",
        side_effect=RuntimeError("unexpected scorer error"),
    ):
        decision = evaluate_post_context_prefilter(
            mode="v2",
            smc=_context(),
            technical=_technical(),
        )

    assert decision["should_reject"] is False
    assert decision["fail_open"] is True
    assert decision["reason_code"] == SMC_PREFILTER_ERROR_FAIL_OPEN


def test_helper_matches_canonical_v2_step3_decision_and_preserves_context() -> None:
    context = _context()
    context["H4"]["demand_zones"].append(
        _zone("demand", "buy", zone_id="h4-buy")
    )
    context["H1"]["supply_zones"].append(
        _zone("supply", "sell", zone_id="h1-sell")
    )
    before = deepcopy(context)
    technical = _technical()
    regime = {"primary": "range"}

    decision = evaluate_post_context_prefilter(
        mode="v2",
        smc=context,
        technical=technical,
        market_regime=regime,
    )
    step3 = build_smc_phase0_diagnostics(
        requested_mode="v2",
        smc=context,
        technical=technical,
        active_scores={"buy": {}, "sell": {}},
        market_regime=regime,
    )

    assert context == before
    assert decision["selected_zone_ids"] == {
        side: step3["decision"][side]["selected_zone_id"]
        for side in ("buy", "sell")
    }
    assert decision["precomputed_v2_result"] == step3["decision"]
