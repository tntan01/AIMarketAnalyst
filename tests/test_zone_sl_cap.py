"""Tests for the score-aware zone SL cap (Direction B + A).

Layer summary being verified:
  - high-quality zones (effective score >= zone_sl_high_score_threshold) earn
    the relaxed cap (zone_sl_cap_ratio_high_score) so the SL can sit behind
    real structure;
  - if a high-quality zone's structural SL still exceeds the relaxed cap, the
    plan is rejected instead of placing the stop inside the zone;
  - low-quality zones keep the legacy tight cap (zone_sl_cap_ratio).
"""

from __future__ import annotations

from typing import Any

import pytest

from core.risk_engine import (
    AnalysisInput,
    _ZONE_SL_BUFFER_ATR,
    _ZONE_SL_CAP_RATIO,
    _ZONE_SL_CAP_RATIO_HIGH_SCORE,
    _ZONE_SL_HIGH_SCORE_THRESHOLD,
    _calc_stop_loss_buy,
    _calc_stop_loss_sell,
    _zone_sl_cap_ratio,
    build_trade_plan,
)
from core.smc_context import build_smc_context
from core.technical_context import build_technical_snapshot

from tests.test_risk_engine import _build_test_data


class TestZoneSlCapRatio:
    """Cap ratio selection by effective zone score."""

    def test_config_defaults(self):
        assert _ZONE_SL_CAP_RATIO == pytest.approx(1.5)
        assert _ZONE_SL_CAP_RATIO_HIGH_SCORE == pytest.approx(2.5)
        assert _ZONE_SL_HIGH_SCORE_THRESHOLD == pytest.approx(80)

    def test_none_score_uses_legacy_cap(self):
        ratio, high = _zone_sl_cap_ratio(None)
        assert ratio == pytest.approx(_ZONE_SL_CAP_RATIO)
        assert high is False

    def test_below_threshold_uses_legacy_cap(self):
        ratio, high = _zone_sl_cap_ratio(_ZONE_SL_HIGH_SCORE_THRESHOLD - 1)
        assert ratio == pytest.approx(_ZONE_SL_CAP_RATIO)
        assert high is False

    def test_at_threshold_uses_relaxed_cap(self):
        ratio, high = _zone_sl_cap_ratio(_ZONE_SL_HIGH_SCORE_THRESHOLD)
        assert ratio == pytest.approx(_ZONE_SL_CAP_RATIO_HIGH_SCORE)
        assert high is True

    def test_backtest_override_is_respected(self):
        """Params must be tunable via risk_parameter_scope (no code edits)."""
        from core.risk_parameter_context import (
            RiskParameterOverrides,
            risk_parameter_scope,
        )

        overrides = RiskParameterOverrides.from_mapping({
            "zone_sl_high_score_threshold": 70.0,
            "zone_sl_cap_ratio_high_score": 3.0,
            "zone_sl_cap_ratio": 2.0,
        })
        with risk_parameter_scope(overrides):
            ratio, high = _zone_sl_cap_ratio(70)
            assert high is True
            assert ratio == pytest.approx(3.0)
            # low-score path must also honor the legacy-key override
            legacy_ratio, legacy_high = _zone_sl_cap_ratio(10)
            assert legacy_high is False
            assert legacy_ratio == pytest.approx(2.0)


class TestCalcStopLossScoreAwareCap:
    """Unit tests of _calc_stop_loss_buy/_calc_stop_loss_sell.

    Numbers mirror the canonical failure case: ATR = 100 pips, sl_mult=0.50
    -> legacy cap 75 pips, relaxed cap 125 pips, buffer 10 pips.  A zone
    whose boundary sits 120 pips away needs a 130-pip structural stop.
    """

    LEVEL = 1.1000
    ATR = 0.0100
    SL_MULT = 0.50
    MIN_STOP = 0.0005

    def _buy(self, zone_low: float | None, score: float | None):
        zone = None
        if zone_low is not None:
            zone = {"level": self.LEVEL, "low": zone_low, "high": self.LEVEL}
        return _calc_stop_loss_buy(
            self.LEVEL, self.ATR, self.SL_MULT, self.MIN_STOP, zone,
            zone_score=score,
        )

    def _sell(self, zone_high: float | None, score: float | None):
        zone = None
        if zone_high is not None:
            zone = {"level": self.LEVEL, "low": self.LEVEL, "high": zone_high}
        return _calc_stop_loss_sell(
            self.LEVEL, self.ATR, self.SL_MULT, self.MIN_STOP, zone,
            zone_score=score,
        )

    # ── BUY ──

    def test_buy_close_zone_uses_structural_sl_for_any_score(self):
        """Zone 50 pips away: structural SL fits under BOTH caps — the score
        must not change anything."""
        zone_low = self.LEVEL - 0.0050
        expected = zone_low - self.ATR * _ZONE_SL_BUFFER_ATR
        for score in (None, 30, 90):
            assert self._buy(zone_low, score) == pytest.approx(expected)

    def test_buy_far_zone_low_score_keeps_legacy_cap(self):
        """Zone boundary 120 pips away, junk score -> legacy 75-pip cap
        (unchanged pre-fix behavior)."""
        zone_low = self.LEVEL - 0.0120
        legacy_cap = self.LEVEL - self.ATR * self.SL_MULT * _ZONE_SL_CAP_RATIO
        for score in (None, 30):
            assert self._buy(zone_low, score) == pytest.approx(legacy_cap)

    def test_buy_far_zone_high_score_within_relaxed_cap_uses_structural(self):
        """Zone boundary 110 pips away, score 90: structural 120-pip stop
        fits the relaxed 125-pip cap -> SL behind the zone, not the cap."""
        zone_low = self.LEVEL - 0.0110
        structural = zone_low - self.ATR * _ZONE_SL_BUFFER_ATR
        assert self._buy(zone_low, 90) == pytest.approx(structural)

    def test_buy_far_zone_high_score_beyond_relaxed_cap_returns_none(self):
        """Zone boundary 120 pips away, score 90: structural 130-pip stop
        exceeds the relaxed 125-pip cap -> refuse instead of hiding the SL
        inside the zone."""
        zone_low = self.LEVEL - 0.0120
        assert self._buy(zone_low, 90) is None

    def test_buy_threshold_boundary_score_treated_as_high(self):
        zone_low = self.LEVEL - 0.0120
        assert self._buy(zone_low, _ZONE_SL_HIGH_SCORE_THRESHOLD) is None
        assert self._buy(zone_low, _ZONE_SL_HIGH_SCORE_THRESHOLD - 0.01) is not None

    def test_buy_no_zone_returns_atr_sl_even_high_score(self):
        expected = self.LEVEL - max(self.ATR * self.SL_MULT, self.MIN_STOP)
        assert self._buy(None, 95) == pytest.approx(expected)

    def test_buy_zone_low_not_below_level_returns_atr_sl(self):
        expected = self.LEVEL - max(self.ATR * self.SL_MULT, self.MIN_STOP)
        assert self._buy(self.LEVEL, 95) == pytest.approx(expected)
        assert self._buy(self.LEVEL + 0.0010, 95) == pytest.approx(expected)

    # ── SELL (mirror) ──

    def test_sell_close_zone_uses_structural_sl_for_any_score(self):
        zone_high = self.LEVEL + 0.0050
        expected = zone_high + self.ATR * _ZONE_SL_BUFFER_ATR
        for score in (None, 30, 90):
            assert self._sell(zone_high, score) == pytest.approx(expected)

    def test_sell_far_zone_low_score_keeps_legacy_cap(self):
        zone_high = self.LEVEL + 0.0120
        legacy_cap = self.LEVEL + self.ATR * self.SL_MULT * _ZONE_SL_CAP_RATIO
        for score in (None, 30):
            assert self._sell(zone_high, score) == pytest.approx(legacy_cap)

    def test_sell_far_zone_high_score_within_relaxed_cap_uses_structural(self):
        zone_high = self.LEVEL + 0.0110
        structural = zone_high + self.ATR * _ZONE_SL_BUFFER_ATR
        assert self._sell(zone_high, 90) == pytest.approx(structural)

    def test_sell_far_zone_high_score_beyond_relaxed_cap_returns_none(self):
        zone_high = self.LEVEL + 0.0120
        assert self._sell(zone_high, 90) is None

    def test_sell_no_zone_returns_atr_sl_even_high_score(self):
        expected = self.LEVEL + max(self.ATR * self.SL_MULT, self.MIN_STOP)
        assert self._sell(None, 95) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Integration through build_trade_plan
# ---------------------------------------------------------------------------


def _plan_with_far_zone(
    side: str,
    monkeypatch,
    *,
    zone_distance_atr: float,
    effective_score: int,
    zone_source: str = "technical",
) -> tuple[dict[str, Any] | None, dict[str, float]]:
    """Build a plan whose selected zone boundary sits *zone_distance_atr*
    away from the entry level, forcing the zone-SL cap branch.

    Returns (plan, ctx) where ctx carries level/atr/boundary so tests can
    assert exact SL placement.
    """
    d1, h4, h1, m15 = _build_test_data()
    technical = build_technical_snapshot(d1, h4, h1)
    smc = build_smc_context(d1, h4, h1)
    price = technical["price"]
    atr = technical["atr_h4"] or technical["atr_d1"] or 0.0
    sign = 1 if side == "buy" else -1
    lvl = price - sign * atr * 0.5
    boundary = lvl - sign * atr * zone_distance_atr
    if side == "buy":
        fake_zone = {"level": lvl, "low": boundary, "high": lvl,
                     "zone_score": 80, "source": zone_source}
        fake_target = {"level": lvl + atr * 3.0, "low": lvl + atr * 3.0,
                       "high": lvl + atr * 3.2}
    else:
        fake_zone = {"level": lvl, "low": lvl, "high": boundary,
                     "zone_score": 80, "source": zone_source}
        fake_target = {"level": lvl - atr * 3.0, "high": lvl - atr * 3.0,
                       "low": lvl - atr * 3.2}
    tp = lvl + sign * atr * 3.0
    fake_score = {
        "effective_zone_score": effective_score,
        "effective_zone_score_breakdown": {},
    }

    request = AnalysisInput(
        symbol="EUR/USD", broker_symbol="EURUSDm",
        account_balance=10_000.0, risk_percent=2.0,
        contract_size_override=100_000.0,
    )

    with monkeypatch.context() as m:
        m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
        m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
        m.setattr("core.risk_engine._find_nearest_swing_for_sl", lambda *a, **kw: None)
        m.setattr("core.risk_engine.all_target_zones_sorted",
                  lambda *a, **kw: [fake_target])
        m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: tp)
        m.setattr("core.risk_engine.next_target",
                  lambda *a, **kw: tp + sign * atr * 1.0)
        m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
        m.setattr("core.risk_engine.calculate_effective_zone_score",
                  lambda *a, **kw: dict(fake_score))
        m.setattr("core.risk_engine.REGIME_SL_MULTIPLIER",
                  {"unknown": 0.65, "trend_up": 0.65, "trend_down": 0.65,
                   "range": 0.70, "volatile": 0.85})
        plan = build_trade_plan(side, request, technical, smc, h1, m15_candles=m15)
    return plan, {"level": lvl, "atr": atr, "boundary": boundary}


class TestScoreAwareZoneSlCapIntegration:
    """build_trade_plan end-to-end behavior with the score-aware cap.

    Patched regime sl_mult = 0.65 -> legacy cap = 0.975x ATR,
    relaxed cap = 1.625x ATR (structural distance = zone_distance + 0.10).
    """

    def test_buy_high_score_zone_beyond_relaxed_cap_rejects_plan(self, monkeypatch):
        """d=1.70 -> structural 1.80x ATR > relaxed 1.625x ATR -> no plan."""
        plan, _ = _plan_with_far_zone(
            "buy", monkeypatch, zone_distance_atr=1.7, effective_score=90,
        )
        assert plan is None

    def test_buy_low_score_zone_beyond_relaxed_cap_keeps_legacy_plan(self, monkeypatch):
        """Same far zone with junk score -> legacy cap still produces a plan
        (SL lands inside the zone — accepted trade-off for junk zones)."""
        plan, ctx = _plan_with_far_zone(
            "buy", monkeypatch, zone_distance_atr=1.7, effective_score=40,
        )
        assert plan is not None
        sl = float(plan["stop_loss"])
        legacy_cap = ctx["level"] - ctx["atr"] * 0.65 * _ZONE_SL_CAP_RATIO
        assert sl == pytest.approx(legacy_cap, abs=2e-5)
        assert sl > ctx["boundary"], "legacy behavior: cap SL inside junk zone"

    def test_buy_high_score_zone_within_relaxed_cap_uses_structural_sl(self, monkeypatch):
        """d=1.30 -> structural 1.40x ATR fits relaxed 1.625x ATR -> SL sits
        behind the zone, never inside it."""
        plan, ctx = _plan_with_far_zone(
            "buy", monkeypatch, zone_distance_atr=1.3, effective_score=90,
        )
        assert plan is not None
        sl = float(plan["stop_loss"])
        structural = ctx["boundary"] - ctx["atr"] * _ZONE_SL_BUFFER_ATR
        assert sl == pytest.approx(structural, abs=2e-5)
        assert sl < ctx["boundary"], "SL must sit behind the zone structure"

    def test_buy_wider_structural_sl_shrinks_lot_vs_legacy_cap(self, monkeypatch):
        """Layer-3 math: same 2% risk, wider structural SL -> smaller lot.

        High-score plan (structural 1.40x ATR) must size smaller than the
        legacy-capped plan (0.975x ATR) built from the same data.
        """
        plan_struct, _ = _plan_with_far_zone(
            "buy", monkeypatch, zone_distance_atr=1.3, effective_score=90,
        )
        plan_capped, _ = _plan_with_far_zone(
            "buy", monkeypatch, zone_distance_atr=1.3, effective_score=40,
        )
        assert plan_struct is not None and plan_capped is not None
        lot_struct = float(plan_struct["position_sizing"]["suggested_lot"])
        lot_capped = float(plan_capped["position_sizing"]["suggested_lot"])
        assert lot_struct < lot_capped, (
            f"structural-SL lot {lot_struct} must be < capped lot {lot_capped}"
        )

    def test_sell_high_score_zone_beyond_relaxed_cap_rejects_plan(self, monkeypatch):
        plan, _ = _plan_with_far_zone(
            "sell", monkeypatch, zone_distance_atr=1.7, effective_score=90,
        )
        assert plan is None

    def test_sell_high_score_zone_within_relaxed_cap_uses_structural_sl(self, monkeypatch):
        plan, ctx = _plan_with_far_zone(
            "sell", monkeypatch, zone_distance_atr=1.3, effective_score=90,
        )
        assert plan is not None
        sl = float(plan["stop_loss"])
        structural = ctx["boundary"] + ctx["atr"] * _ZONE_SL_BUFFER_ATR
        assert sl == pytest.approx(structural, abs=2e-5)
        assert sl > ctx["boundary"], "SL must sit behind the zone structure"
