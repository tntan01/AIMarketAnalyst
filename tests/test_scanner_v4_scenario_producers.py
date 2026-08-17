"""Scanner V4 scenario-plan producer tests (live entry/SL/TP per side).

The producer must build a ``ScenarioPlan`` ONLY from real structure: a
protective zone (canonical SMC selection first, nearest same-side technical
zone as fallback) plus a real opposite-side target.  Every number is real data;
anything missing/invalid fails closed to ``None`` (never invented).  There is
deliberately NO pure-ATR synthetic plan — V3 tagged that branch display-only.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.scanner_v4_composition import ScenarioPlan, compute_scenario_rr
from core.scanner_v4_scenario_producers import (
    produce_scenario_plans,
    produce_scenario_plans_from_zones,
)


def _zone(level: float, half: float = 0.1) -> dict:
    return {"level": level, "low": level - half, "high": level + half}


def _technical(**over) -> dict:
    base = {
        "price": 100.0,
        "atr_h4": 1.0,
        "atr_d1": 1.2,
        # Support below price, resistance above price.
        "support_zones": [_zone(98.0)],
        "resistance_zones": [_zone(104.0)],
    }
    base.update(over)
    return base


def _buy_plan(**over):
    return produce_scenario_plans(_technical(**over), None)["buy"]


def _sell_plan(**over):
    return produce_scenario_plans(_technical(**over), None)["sell"]


def _buy_plan_from_zones(zones_by_side, **over):
    return produce_scenario_plans_from_zones(_technical(**over), zones_by_side)["buy"]


class TestBuyPlanFromTechnicalZone:
    def test_plan_geometry_from_real_structure(self):
        plan = _buy_plan()
        assert isinstance(plan, ScenarioPlan)
        assert plan.direction == "buy"
        # Entry is anchored at the protective support-zone edge (V3 alignment),
        # so the stop-loss buffer is the actual risk.
        assert plan.entry == 98.0 - 0.1
        # SL buffers the protective support-zone low by exactly 1.0 * ATR (V3).
        assert plan.stop_loss == 98.0 - 0.1 - 1.0
        # TP = nearest opposite (resistance) zone level beyond the zone's far edge.
        assert plan.take_profit == 104.0
        assert plan.source == "technical_zone_v4"

    def test_ordering_is_valid_and_rr_exact(self):
        plan = _buy_plan()
        assert plan.stop_loss < plan.entry < plan.take_profit
        rr = compute_scenario_rr(plan, "buy")
        # Risk = exactly the 1.0 * ATR stop buffer; reward = TP beyond the zone.
        assert plan.entry - plan.stop_loss == pytest.approx(1.0)
        assert plan.take_profit - plan.entry == pytest.approx(104.0 - (98.0 - 0.1))
        assert rr == Fraction(plan.take_profit - plan.entry) / Fraction(
            plan.entry - plan.stop_loss
        )

    def test_nearest_support_zone_is_chosen(self):
        plan = _buy_plan(support_zones=[_zone(90.0), _zone(98.0), _zone(95.0)])
        # Closest support below price wins (tightest protective stop).
        assert plan.stop_loss == 98.0 - 0.1 - 1.0

    def test_zone_above_price_is_not_protective(self):
        # A "support" zone above the market cannot protect a buy -> no plan.
        plan = _buy_plan(support_zones=[_zone(102.0)])
        assert plan is None


class TestSellPlanFromTechnicalZone:
    def test_plan_geometry_from_real_structure(self):
        plan = _sell_plan()
        assert isinstance(plan, ScenarioPlan)
        assert plan.direction == "sell"
        # Entry anchored at the protective resistance-zone edge (V3 alignment).
        assert plan.entry == 104.0 + 0.1
        # SL buffers the protective resistance-zone high by 1.0 * ATR (V3).
        assert plan.stop_loss == 104.0 + 0.1 + 1.0
        # TP = nearest opposite (support) zone level beyond the zone's far edge.
        assert plan.take_profit == 98.0
        assert plan.source == "technical_zone_v4"

    def test_ordering_is_valid(self):
        plan = _sell_plan()
        assert plan.take_profit < plan.entry < plan.stop_loss


class TestFailClosed:
    def test_no_protective_zone_no_plan(self):
        assert _buy_plan(support_zones=[]) is None
        assert _sell_plan(resistance_zones=[]) is None

    def test_no_opposite_target_no_plan(self):
        # Protective zone exists but there is no opposite-side TP zone -> the
        # producer refuses to invent a target.
        assert _buy_plan(resistance_zones=[]) is None
        assert _sell_plan(support_zones=[]) is None

    def test_opposite_zone_not_beyond_far_edge_no_plan(self):
        # Resistance at/below the protective zone's far edge cannot be a buy TP.
        assert _buy_plan(resistance_zones=[_zone(98.0)]) is None

    def test_missing_price_or_atr_no_plan(self):
        assert _buy_plan(price=None) is None
        assert _buy_plan(atr_h4=None, atr_d1=None) is None
        assert _buy_plan(atr_h4=0.0, atr_d1=0.0) is None

    def test_non_numeric_inputs_no_plan(self):
        assert _buy_plan(price="n/a") is None
        assert _buy_plan(atr_h4=float("nan"), atr_d1=float("nan")) is None

    def test_not_a_dict_fails_closed(self):
        plans = produce_scenario_plans(None, None)
        assert plans == {"buy": None, "sell": None}

    def test_malformed_zone_shapes_fail_closed(self):
        assert _buy_plan(support_zones=[{"level": 98.0}]) is None  # no low/high
        assert _buy_plan(support_zones=[{"low": 97.0, "high": 98.0}]) is None


class TestCanonicalZonePreference:
    def test_canonical_zone_preferred_when_protective(self):
        canonical = _zone(97.0, half=0.2)
        plan = _buy_plan_from_zones({"buy": canonical, "sell": None})
        assert plan is not None
        assert plan.source == "smc_canonical_zone_v4"
        assert plan.stop_loss == 97.0 - 0.2 - 1.0

    def test_canonical_not_protective_falls_back_to_technical(self):
        # Canonical zone on the wrong side of price -> technical zone is used.
        canonical = _zone(105.0, half=0.2)
        plan = _buy_plan_from_zones({"buy": canonical, "sell": None})
        assert plan is not None
        assert plan.source == "technical_zone_v4"
        assert plan.stop_loss == 98.0 - 0.1 - 1.0

    def test_absent_canonical_zone_falls_back_to_technical(self):
        plan = _buy_plan_from_zones({"buy": None, "sell": None})
        assert plan is not None
        assert plan.source == "technical_zone_v4"

    def test_non_dict_zones_mapping_is_ignored(self):
        plan = produce_scenario_plans_from_zones(_technical(), "not-a-mapping")["buy"]
        assert plan is not None
        assert plan.source == "technical_zone_v4"

    def test_malformed_canonical_smc_fails_closed_to_technical(self):
        # A garbage canonical result must not raise; extraction fails closed to
        # {} and the technical zone path still produces a plan.
        plan = produce_scenario_plans(_technical(), object())["buy"]
        assert plan is not None
        assert plan.source == "technical_zone_v4"


class TestRationalRRExceedsFloor:
    def test_tight_stop_far_target_meets_two_to_one(self):
        # Protective zone close to price (tight risk), target far (big reward).
        plan = _buy_plan(support_zones=[_zone(99.5)], resistance_zones=[_zone(110.0)])
        assert plan is not None
        assert compute_scenario_rr(plan, "buy") >= Fraction(2, 1)
