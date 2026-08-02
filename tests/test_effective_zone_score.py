from __future__ import annotations

from copy import deepcopy

from core.risk_engine import build_source_zone_diagnostics
from core.scanner_ranking_engine import calculate_opportunity_score
from core.smc_context import (
    calculate_effective_zone_score,
)
from core.trade_gate_engine import check_trade_gates


ATR = 0.002


def _zone(**overrides: object) -> dict[str, object]:
    zone: dict[str, object] = {
        "type": "bullish_order_block",
        "low": 1.0980,
        "high": 1.0990,
        "zone_score": 80,
        "stale": False,
        "mitigated": False,
        "broken": False,
        "test_count": 1,
        "freshness_bars": 3,
        "displacement_multiple": 1.5,
        "liquidity_sweep": True,
        "zone_location": "discount",
    }
    zone.update(overrides)
    return zone


def _score(zone: dict[str, object], side: str = "buy") -> int:
    return calculate_effective_zone_score(zone, side, ATR)[
        "effective_zone_score"
    ]


def test_fresh_zone_scores_above_stale_zone() -> None:
    fresh = _zone(freshness_bars=2, stale=False)
    stale = _zone(freshness_bars=2, stale=True)

    assert _score(fresh) > _score(stale)


def test_unmitigated_zone_scores_above_mitigated_zone() -> None:
    assert _score(_zone(mitigated=False)) > _score(_zone(mitigated=True))


def test_repeatedly_tested_zone_scores_below_early_retest() -> None:
    assert _score(_zone(test_count=1)) > _score(_zone(test_count=7))


def test_wide_zone_scores_below_narrow_zone() -> None:
    narrow = _zone(low=1.0984, high=1.0990)
    wide = _zone(low=1.0940, high=1.0990)

    assert _score(narrow) > _score(wide)


def test_broken_zone_is_forced_to_zero() -> None:
    result = calculate_effective_zone_score(_zone(broken=True), "buy", ATR)

    assert result["effective_zone_score"] == 0
    assert result["effective_zone_score_breakdown"]["broken_override"] is True


def test_displacement_and_liquidity_sweep_are_visible_bonuses() -> None:
    weak = _zone(displacement_multiple=0.0, liquidity_sweep=False)
    strong = _zone(displacement_multiple=2.0, liquidity_sweep=True)

    result = calculate_effective_zone_score(strong, "buy", ATR)
    assert _score(strong) > _score(weak)
    assert result["effective_zone_score_breakdown"]["displacement_bonus"] > 0
    assert (
        result["effective_zone_score_breakdown"]["liquidity_sweep_bonus"]
        > 0
    )


def test_buy_sell_premium_discount_symmetry() -> None:
    buy_discount = _score(_zone(zone_location="discount"), "buy")
    sell_premium = _score(_zone(zone_location="premium"), "sell")
    buy_premium = _score(_zone(zone_location="premium"), "buy")
    sell_discount = _score(_zone(zone_location="discount"), "sell")

    assert buy_discount == sell_premium
    assert buy_premium == sell_discount
    assert buy_discount > buy_premium


def test_source_zone_exposes_raw_effective_and_breakdown() -> None:
    diagnostic = build_source_zone_diagnostics(_zone(), ATR, "buy")

    assert diagnostic is not None
    assert diagnostic["zone_score"] == 80
    assert isinstance(diagnostic["effective_zone_score"], int)
    assert diagnostic["displacement_multiple"] == 1.5
    assert diagnostic["liquidity_sweep"] is True
    assert diagnostic["zone_location"] == "discount"
    assert (
        diagnostic["effective_zone_score_breakdown"][
            "source_zone_width_atr"
        ]
        == 0.5
    )


def test_missing_test_count_is_neutral_not_fresh_zone_bonus() -> None:
    unknown = _zone()
    unknown.pop("test_count")
    explicit_zero = _zone(test_count=0)

    unknown_result = calculate_effective_zone_score(
        unknown,
        "buy",
        ATR,
    )
    explicit_result = calculate_effective_zone_score(
        explicit_zero,
        "buy",
        ATR,
    )
    assert (
        unknown_result["effective_zone_score_breakdown"][
            "test_count_adjustment"
        ]
        == 0
    )
    assert _score(explicit_zero) > _score(unknown)


def test_effective_score_does_not_affect_scanner_ranking() -> None:
    row = {
        "final_score": 70,
        "decision": "WATCH_ONLY",
        "entry_status": "watch_zone",
        "entry_zone_score": 80,
        "expected_effective_rr_base": 1.5,
        "source_zone": {
            "zone_score": 80,
            "effective_zone_score": 10,
        },
    }
    changed_shadow = deepcopy(row)
    changed_shadow["source_zone"]["effective_zone_score"] = 95

    assert calculate_opportunity_score(row) == calculate_opportunity_score(
        changed_shadow
    )


def test_effective_score_does_not_affect_trade_gate() -> None:
    context = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "data_quality_warning": False,
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "score_gap": 20,
        "min_buy_sell_score_gap": 10,
        "zone_broken": False,
        "daily_loss_limit_reached": False,
        "weekly_loss_limit_reached": False,
        "expected_effective_rr_for_gate": 1.5,
        "expected_effective_rr_source": "base",
        "min_expected_effective_rr": 1.3,
        "source_zone": {"effective_zone_score": 5},
    }
    changed_shadow = deepcopy(context)
    changed_shadow["source_zone"]["effective_zone_score"] = 100

    assert check_trade_gates(context) == check_trade_gates(changed_shadow)
