"""Tests for worst-case (far-edge) position sizing (Mục 3 / Direction worst).

Sizing must anchor to the far edge of the execution zone (worst fill) so that
a fill anywhere inside the zone risks at most the configured percent.  Sizing
at the nearest edge (smallest distance -> biggest lot) would exceed the risk
budget whenever the fill lands deeper in the zone.
"""

from __future__ import annotations

import pytest

from core.risk_engine import AnalysisInput, position_sizing

from tests.test_zone_sl_cap import _plan_with_far_zone


class TestWorstCaseSizingGeometry:

    def test_buy_plan_sizing_uses_far_edge(self, monkeypatch):
        """BUY: sizing distance = entry_high (far edge) - SL, and the sizing
        block reports that anchor — while the plan's display entry_price stays
        at the nearest edge."""
        plan, _ = _plan_with_far_zone(
            "buy", monkeypatch, zone_distance_atr=1.3, effective_score=90,
        )
        assert plan is not None
        entry_low, entry_high = (float(v) for v in plan["entry_zone"])
        sl = float(plan["stop_loss"])
        sizing = plan["position_sizing"]
        assert sizing["price_distance"] == pytest.approx(entry_high - sl, abs=2e-5)
        assert sizing["entry_price"] == pytest.approx(entry_high, abs=2e-5)
        # Display entry is unchanged (nearest edge = best-case fill)
        assert float(plan["entry_price"]) == pytest.approx(entry_low, abs=2e-5)

    def test_sell_plan_sizing_uses_far_edge(self, monkeypatch):
        """SELL: sizing distance = SL - entry_low (far edge)."""
        plan, _ = _plan_with_far_zone(
            "sell", monkeypatch, zone_distance_atr=1.3, effective_score=90,
        )
        assert plan is not None
        entry_low, entry_high = (float(v) for v in plan["entry_zone"])
        sl = float(plan["stop_loss"])
        sizing = plan["position_sizing"]
        assert sizing["price_distance"] == pytest.approx(sl - entry_low, abs=2e-5)
        assert sizing["entry_price"] == pytest.approx(entry_low, abs=2e-5)
        assert float(plan["entry_price"]) == pytest.approx(entry_high, abs=2e-5)

    def test_plan_lot_equals_worst_edge_sizing(self, monkeypatch):
        """The plan's suggested lot must be exactly the lot computed from the
        far edge — never the bigger near-edge lot."""
        plan, _ = _plan_with_far_zone(
            "buy", monkeypatch, zone_distance_atr=1.3, effective_score=90,
        )
        assert plan is not None
        entry_low, entry_high = (float(v) for v in plan["entry_zone"])
        sl = float(plan["stop_loss"])
        sizing = plan["position_sizing"]
        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=float(sizing["account_balance"]),
            risk_percent=float(sizing["risk_pct"]),
            contract_size_override=100_000.0,
        )
        worst = position_sizing(request, entry_high, sl)
        best = position_sizing(request, entry_low, sl)
        assert sizing["suggested_lot"] == worst["suggested_lot"]
        assert worst["suggested_lot"] <= best["suggested_lot"]


class TestSizingMonotonicity:
    """Farther fill -> bigger risk distance -> smaller lot, at fixed %."""

    def _lot(self, entry: float, sl: float) -> float:
        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )
        return position_sizing(request, entry, sl, quote_to_usd_rate=1.0)[
            "suggested_lot"
        ]

    def test_buy_lot_shrinks_toward_far_edge(self):
        sl = 1.0900
        best_entry, base_entry, worst_entry = 1.0950, 1.0975, 1.1000
        lot_best = self._lot(best_entry, sl)
        lot_base = self._lot(base_entry, sl)
        lot_worst = self._lot(worst_entry, sl)
        assert lot_best >= lot_base >= lot_worst
        assert lot_worst < lot_best

    def test_worst_sizing_never_exceeds_risk_budget(self):
        """At the worst-edge lot, a fill at ANY zone price risks <= budget."""
        sl = 1.0900
        best_entry, worst_entry = 1.0950, 1.1000
        lot_worst = self._lot(worst_entry, sl)
        budget = 10_000.0 * 2.0 / 100
        for fill in (best_entry, 1.0975, worst_entry):
            risk = lot_worst * (fill - sl) * 100_000.0
            assert risk <= budget + 1e-6
