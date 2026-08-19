from __future__ import annotations

import pytest

import core.risk_engine as risk_engine
from core.risk_engine import (
    _build_execution_sub_zone,
    reward_risk,
)
from core.scanner import scanner_row_from_analysis
from tests.test_source_zone_diagnostics import (
    _preferred_zone,
    _valid_plan,
)


def test_approved_quality_widths_tier_by_zone_quality() -> None:
    assert risk_engine._EXECUTION_ZONE_WIDTH_ATR_BY_QUALITY == {
        "strong": 0.12,
        "moderate": 0.18,
        "weak": 0.25,
    }


def test_quality_tiers_are_configurable(monkeypatch) -> None:
    monkeypatch.setattr(
        risk_engine,
        "_EXECUTION_ZONE_WIDTH_ATR_BY_QUALITY",
        {"strong": 0.35, "moderate": 0.30, "weak": 0.25},
    )

    strong = _build_execution_sub_zone(
        side="buy",
        source_low=1.0900,
        source_high=1.1000,
        atr_value=0.0100,
        effective_score=80,
        price_digits=5,
    )
    moderate = _build_execution_sub_zone(
        side="buy",
        source_low=1.0900,
        source_high=1.1000,
        atr_value=0.0100,
        effective_score=60,
        price_digits=5,
    )
    weak = _build_execution_sub_zone(
        side="buy",
        source_low=1.0900,
        source_high=1.1000,
        atr_value=0.0100,
        effective_score=30,
        price_digits=5,
    )

    assert strong is not None and strong["width_atr_target"] == 0.35
    assert moderate is not None and moderate["width_atr_target"] == 0.30
    assert weak is not None and weak["width_atr_target"] == 0.25


def test_buy_sell_proximal_zones_are_symmetric_and_contained() -> None:
    buy = _build_execution_sub_zone(
        side="buy",
        source_low=100.0,
        source_high=102.0,
        atr_value=2.0,
        effective_score=60,
        price_digits=3,
    )
    sell = _build_execution_sub_zone(
        side="sell",
        source_low=100.0,
        source_high=102.0,
        atr_value=2.0,
        effective_score=60,
        price_digits=3,
    )

    assert buy is not None and buy["entry_zone"] == [101.64, 102.0]
    assert sell is not None and sell["entry_zone"] == [100.0, 100.36]
    assert 100.0 <= buy["entry_zone"][0] < buy["entry_zone"][1] <= 102.0
    assert 100.0 <= sell["entry_zone"][0] < sell["entry_zone"][1] <= 102.0


def test_narrow_source_zone_is_not_expanded() -> None:
    result = _build_execution_sub_zone(
        side="buy",
        source_low=1.0998,
        source_high=1.1000,
        atr_value=0.0020,
        effective_score=80,
        price_digits=5,
    )

    assert result is not None
    assert result["entry_zone"] == [1.0998, 1.1]


def test_jpy_and_five_digit_precision_stay_inside_source() -> None:
    jpy = _build_execution_sub_zone(
        side="buy",
        source_low=217.5182,
        source_high=218.2614,
        atr_value=0.380341,
        effective_score=39,
        price_digits=3,
    )
    five_digit = _build_execution_sub_zone(
        side="sell",
        source_low=1.085001,
        source_high=1.086219,
        atr_value=0.001037,
        effective_score=60,
        price_digits=5,
    )

    assert jpy is not None
    assert jpy["entry_zone"][0] >= 217.5182
    assert jpy["entry_zone"][1] <= 218.2614
    assert jpy["entry_zone"][0] * 1000 == pytest.approx(
        round(jpy["entry_zone"][0] * 1000)
    )
    assert jpy["entry_zone"][1] * 1000 == pytest.approx(
        round(jpy["entry_zone"][1] * 1000)
    )

    assert five_digit is not None
    assert five_digit["entry_zone"][0] >= 1.085001
    assert five_digit["entry_zone"][1] <= 1.086219
    assert five_digit["entry_zone"][0] * 100000 == pytest.approx(
        round(five_digit["entry_zone"][0] * 100000)
    )


def test_trade_plan_anchors_rr_and_lot_use_execution_zone() -> None:
    plan = _valid_plan(_preferred_zone())
    execution_low, execution_high = plan["execution_zone"]

    assert plan["entry_zone"] == plan["execution_zone"]
    assert plan["source_zone"]["original_low"] == 1.0968
    assert plan["source_zone"]["original_high"] == 1.0982
    assert 1.0968 <= execution_low < execution_high <= 1.0982
    assert plan["entry_price"] == execution_low
    # Sizing anchors the far edge (worst fill); display entry stays nearest.
    assert plan["position_sizing"]["entry_price"] == execution_high
    assert plan["position_sizing"]["stop_loss"] == plan["stop_loss"]
    assert plan["position_sizing"]["price_distance"] == pytest.approx(
        execution_high - float(plan["stop_loss"]), abs=1e-5
    )

    tp1 = plan["take_profit"][0]
    expected_best = round(
        reward_risk(plan["entry_price"], plan["stop_loss"], tp1),
        1,
    )
    assert plan["risk_reward"] == f"1:{expected_best:.1f}"


def test_scanner_row_exposes_execution_zone_without_replacing_entry_alias() -> None:
    plan = _valid_plan(_preferred_zone())
    plan["type"] = "buy"
    result = {
        "symbol": "EUR/USD",
        "scenario_scores": {
            "buy": {"signal_score": 80},
            "sell": {"signal_score": 40},
        },
        "trade_permission": {"status": "allowed"},
        "scenarios": [plan],
        "technical": {"price": 1.1000, "atr_h4": 0.0020},
        "decision_engine": {
            "legacy_action": "watch",
            "decision": "WATCH_ONLY",
        },
        "direction_bias": {"best_side": "buy"},
    }

    row = scanner_row_from_analysis(result)

    assert row["entry_zone"] == plan["execution_zone"]
    assert row["execution_zone"] == plan["execution_zone"]
    assert row["source_zone"] == plan["source_zone"]
    assert row["execution_zone_width_atr_target"] == 0.25
