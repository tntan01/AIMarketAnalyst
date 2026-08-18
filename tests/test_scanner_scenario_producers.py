"""Scanner scenario-plan producer tests (live entry/SL/TP per side).

The producer must build a ``ScenarioPlan`` ONLY from real structure: a
protective zone (canonical SMC selection first, nearest same-side technical
zone as fallback) plus a real opposite-side target.  Every number is real data;
anything missing/invalid fails closed to ``None`` (never invented).  There is
deliberately NO pure-ATR synthetic plan — legacy tagged that branch display-only.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.scanner_composition import ScenarioPlan, compute_scenario_rr
from core.scanner_scenario_producers import (
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
        # Support below price, resistance above price — both within the
        # protective-zone proximity cap (legacy ZONE_BEYOND_HARD_DISTANCE 3 ATR).
        "support_zones": [_zone(98.0)],
        "resistance_zones": [_zone(102.5)],
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
        # Entry is anchored at the protective support-zone edge (legacy alignment),
        # so the stop-loss buffer is the actual risk.
        assert plan.entry == 98.0 - 0.1
        # SL buffers the protective support-zone low by exactly 1.0 * ATR (legacy).
        assert plan.stop_loss == 98.0 - 0.1 - 1.0
        # TP = nearest opposite (resistance) zone level beyond the zone's far edge.
        assert plan.take_profit == 102.5
        assert plan.source == "technical_zone"

    def test_ordering_is_valid_and_rr_exact(self):
        plan = _buy_plan()
        assert plan.stop_loss < plan.entry < plan.take_profit
        rr = compute_scenario_rr(plan, "buy")
        # Risk = exactly the 1.0 * ATR stop buffer; reward = TP beyond the zone.
        assert plan.entry - plan.stop_loss == pytest.approx(1.0)
        assert plan.take_profit - plan.entry == pytest.approx(102.5 - (98.0 - 0.1))
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
        # Entry anchored at the protective resistance-zone edge (legacy alignment).
        assert plan.entry == 102.5 + 0.1
        # SL buffers the protective resistance-zone high by 1.0 * ATR (legacy).
        assert plan.stop_loss == 102.5 + 0.1 + 1.0
        # TP = nearest opposite (support) zone level beyond the zone's far edge.
        assert plan.take_profit == 98.0
        assert plan.source == "technical_zone"

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

    def test_protective_zone_far_from_price_is_distant_watch(self):
        # Finding #1: a protective zone whose NEAREST edge is beyond the legacy
        # 3.0-ATR hard distance (ZONE_BEYOND_HARD_DISTANCE) is a distant watch,
        # never a tradable plan — even though its geometric R:R would pass.
        assert _buy_plan(support_zones=[_zone(94.0)]) is None  # ~6 ATR below
        assert _sell_plan(resistance_zones=[_zone(106.0)]) is None  # ~6 ATR above

    def test_protective_zone_within_cap_still_produces_plan(self):
        # Nearest edge just inside the 3.0-ATR cap still yields a plan.
        plan = _buy_plan(support_zones=[_zone(97.0, half=0.1)])  # dist >97.1 -> 2.9
        assert plan is not None
        assert plan.stop_loss == 97.0 - 0.1 - 1.0


class TestCanonicalZonePreference:
    def test_canonical_zone_preferred_when_protective(self):
        canonical = _zone(97.0, half=0.2)
        plan = _buy_plan_from_zones({"buy": canonical, "sell": None})
        assert plan is not None
        assert plan.source == "smc_canonical_zone"
        assert plan.stop_loss == 97.0 - 0.2 - 1.0

    def test_canonical_not_protective_falls_back_to_technical(self):
        # Canonical zone on the wrong side of price -> technical zone is used.
        canonical = _zone(105.0, half=0.2)
        plan = _buy_plan_from_zones({"buy": canonical, "sell": None})
        assert plan is not None
        assert plan.source == "technical_zone"
        assert plan.stop_loss == 98.0 - 0.1 - 1.0

    def test_absent_canonical_zone_falls_back_to_technical(self):
        plan = _buy_plan_from_zones({"buy": None, "sell": None})
        assert plan is not None
        assert plan.source == "technical_zone"

    def test_non_dict_zones_mapping_is_ignored(self):
        plan = produce_scenario_plans_from_zones(_technical(), "not-a-mapping")["buy"]
        assert plan is not None
        assert plan.source == "technical_zone"

    def test_malformed_canonical_smc_fails_closed_to_technical(self):
        # A garbage canonical result must not raise; extraction fails closed to
        # {} and the technical zone path still produces a plan.
        plan = produce_scenario_plans(_technical(), object())["buy"]
        assert plan is not None
        assert plan.source == "technical_zone"


class TestRationalRRExceedsFloor:
    def test_tight_stop_far_target_meets_two_to_one(self):
        # Protective zone close to price (tight risk), target far (big reward).
        plan = _buy_plan(support_zones=[_zone(99.5)], resistance_zones=[_zone(110.0)])
        assert plan is not None
        assert compute_scenario_rr(plan, "buy") >= Fraction(2, 1)


class TestProtectiveZoneBandOnPlan:
    """The plan carries the REAL protective-zone band so the UI can draw the entry
    as the true zone rectangle (option 2), and the band survives serialization."""

    def test_buy_plan_keeps_the_zone_band(self):
        plan = _buy_plan(support_zones=[_zone(98.0)], resistance_zones=[_zone(102.5)])
        assert plan is not None
        assert plan.entry_zone_low == 98.0 - 0.1
        assert plan.entry_zone_high == 98.0 + 0.1
        # The anchored entry sits ON the protective zone's near edge.
        assert plan.entry == plan.entry_zone_low

    def test_sell_plan_keeps_the_zone_band(self):
        plan = _sell_plan(resistance_zones=[_zone(102.5)], support_zones=[_zone(98.0)])
        assert plan is not None
        assert plan.entry_zone_low == 102.5 - 0.1
        assert plan.entry_zone_high == 102.5 + 0.1
        assert plan.entry == plan.entry_zone_high

    def test_canonical_zone_band_flows_into_plan(self):
        canonical = _zone(97.0, half=0.2)
        plan = _buy_plan_from_zones({"buy": canonical, "sell": None})
        assert plan is not None
        assert plan.entry_zone_low == 97.0 - 0.2
        assert plan.entry_zone_high == 97.0 + 0.2
        assert plan.source == "smc_canonical_zone"

    def test_band_round_trips_through_canonical_dict(self):
        from core.scanner_composition import _scenario_plan_from_dict

        plan = _buy_plan()
        payload = plan.to_canonical_dict()
        assert payload["entry_zone_low"] == plan.entry_zone_low
        restored = _scenario_plan_from_dict(payload, path="p")
        assert restored.entry_zone_low == plan.entry_zone_low
        assert restored.entry_zone_high == plan.entry_zone_high
        assert restored.entry == plan.entry

    def test_band_requires_both_halves(self):
        from core.scanner_composition import CompositionInputError, ScenarioPlan

        with pytest.raises(CompositionInputError):
            ScenarioPlan("buy", 97.9, 96.9, 102.5, source="t", entry_zone_low=97.8)  # no high

    def test_band_must_contain_the_anchored_entry(self):
        from core.scanner_composition import CompositionInputError, ScenarioPlan

        # band 94.0..97.0 does NOT contain the anchored entry 97.9 -> refused.
        with pytest.raises(CompositionInputError):
            ScenarioPlan(
                "buy", 97.9, 96.9, 102.5, source="t",
                entry_zone_low=94.0, entry_zone_high=97.0,
            )

    def test_plan_without_zone_band_stays_legacy_shape(self):
        # A synthetic/legacy-style plan (no band) keeps the exact 5-key canonical
        # dict so old payloads round-trip unchanged.
        plan = _buy_plan()
        assert plan.entry_zone_low is not None  # producer always supplies the band
        # A hand-built band-less plan:
        from core.scanner_composition import _scenario_plan_from_dict

        legacy = {
            "direction": "buy",
            "entry": 97.9,
            "stop_loss": 96.9,
            "take_profit": 102.5,
            "source": "technical_zone",
        }
        restored = _scenario_plan_from_dict(legacy, path="p")
        assert restored.entry_zone_low is None
        assert restored.to_canonical_dict() == legacy
