"""Tests for the no-TP1 watch downgrade (Mục 2 / Direction B).

An SMC/preferred plan that survives without any valid TP1 must be downgraded
to watch_zone + ready_to_trade=False with an explicit reason, so that:
  - the decision engine (entry_status + score only) can no longer judge
    READY_TO_TRADE while the readiness engine blocks TAKE_PROFIT_MISSING;
  - manual traders see the plan is not a tradeable order.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.decision_engine import (
    READY_TO_TRADE,
    STAND_ASIDE,
    WATCH_ONLY,
    make_final_decision,
)
from core.risk_engine import AnalysisInput, build_trade_plan
from core.smc_context import build_smc_context
from core.technical_context import build_technical_snapshot

from tests.test_risk_engine import _build_test_data

NO_TP1_REASON = "Không có TP1 cấu trúc"


def _smc_plan(
    side: str,
    monkeypatch,
    *,
    with_tp: bool,
) -> dict[str, Any] | None:
    """Build an SMC-zone plan; when with_tp=False every TP1 source fails so
    the plan survives only via the SMC no-TP branch (tp1_source='none')."""
    d1, h4, h1, m15 = _build_test_data()
    technical = build_technical_snapshot(d1, h4, h1)
    smc = build_smc_context(d1, h4, h1)
    price = technical["price"]
    atr = technical["atr_h4"] or technical["atr_d1"] or 0.0
    sign = 1 if side == "buy" else -1
    lvl = price - sign * atr * 0.5
    if side == "buy":
        fake_zone = {"level": lvl, "low": lvl, "high": lvl + atr * 0.1,
                     "zone_score": 80, "source": "smc"}
        fake_target = {"level": lvl + atr * 3.0, "low": lvl + atr * 3.0,
                       "high": lvl + atr * 3.2}
    else:
        fake_zone = {"level": lvl, "low": lvl - atr * 0.1, "high": lvl,
                     "zone_score": 80, "source": "smc"}
        fake_target = {"level": lvl - atr * 3.0, "high": lvl - atr * 3.0,
                       "low": lvl - atr * 3.2}
    tp = lvl + sign * atr * 3.0

    request = AnalysisInput(
        symbol="EUR/USD", broker_symbol="EURUSDm",
        account_balance=10_000.0, risk_percent=2.0,
        contract_size_override=100_000.0,
    )

    with monkeypatch.context() as m:
        m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: fake_zone)
        m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [fake_zone])
        m.setattr("core.risk_engine._find_nearest_swing_for_sl", lambda *a, **kw: None)
        m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
        m.setattr("core.risk_engine.all_target_zones_sorted",
                  lambda *a, **kw: [fake_target] if with_tp else [])
        m.setattr("core.risk_engine.nearest_target",
                  lambda *a, **kw: tp if with_tp else None)
        m.setattr("core.risk_engine.next_target",
                  lambda *a, **kw: (tp + sign * atr) if with_tp else None)
        m.setattr("core.risk_engine._fib_extension_target", lambda *a, **kw: None)
        m.setattr("core.risk_engine._find_nearest_swing_for_tp", lambda *a, **kw: None)
        m.setattr("core.risk_engine.REGIME_SL_MULTIPLIER",
                  {"unknown": 0.65, "trend_up": 0.65, "trend_down": 0.65,
                   "range": 0.70, "volatile": 0.85})
        return build_trade_plan(side, request, technical, smc, h1, m15_candles=m15)


class TestNoTp1WatchDowngrade:

    def test_buy_smc_plan_without_tp1_is_downgraded_to_watch(self, monkeypatch):
        plan = _smc_plan("buy", monkeypatch, with_tp=False)
        assert plan is not None, "SMC no-TP plan must survive for monitoring"
        # No defined exit...
        assert plan["take_profit"] == []
        assert plan["risk_reward"] is None
        assert plan["tp_source"] == "none"
        assert plan["tp1_source"] == "none"
        # ...so it must not look tradeable
        assert plan["entry_status"] == "watch_zone"
        assert plan["ready_to_trade"] is False
        assert NO_TP1_REASON in str(plan.get("invalid_reason") or "")

    def test_sell_smc_plan_without_tp1_is_downgraded_to_watch(self, monkeypatch):
        plan = _smc_plan("sell", monkeypatch, with_tp=False)
        assert plan is not None
        assert plan["take_profit"] == []
        assert plan["entry_status"] == "watch_zone"
        assert plan["ready_to_trade"] is False
        assert NO_TP1_REASON in str(plan.get("invalid_reason") or "")

    def test_smc_plan_with_tp1_is_not_downgraded(self, monkeypatch):
        plan = _smc_plan("buy", monkeypatch, with_tp=True)
        assert plan is not None
        assert plan["take_profit"], "plan with valid TP1 keeps its targets"
        assert plan["tp1_source"] != "none"
        assert NO_TP1_REASON not in str(plan.get("invalid_reason") or "")

    def test_downgraded_plan_decision_is_watch_only_not_ready(self, monkeypatch):
        """Resolves the verdict contradiction: even with a strong score, the
        downgraded entry_status must yield WATCH_ONLY — never READY_TO_TRADE —
        matching the readiness engine's TAKE_PROFIT_MISSING block."""
        plan = _smc_plan("buy", monkeypatch, with_tp=False)
        assert plan is not None
        result = make_final_decision(
            final_score=95,
            gate_result={"allowed": True},
            entry_status=plan["entry_status"],
            score_gap=30,
        )
        assert result["decision"] == WATCH_ONLY
        assert result["decision"] != READY_TO_TRADE

    def test_no_tp_does_not_upgrade_invalidated_to_watch(self, monkeypatch):
        """A broken zone (entry_status='invalidated') that also lacks TP1 must
        keep 'invalidated' — the downgrade must never upgrade a worse state to
        watch_zone (STAND_ASIDE must not silently become WATCH_ONLY)."""
        monkeypatch.setattr(
            "core.risk_engine.evaluate_entry",
            lambda **kw: {
                "entry_status": "invalidated",
                "ready_to_trade": False,
                "invalid_reason": "Giá đã phá vùng vào lệnh dự kiến.",
            },
        )
        plan = _smc_plan("buy", monkeypatch, with_tp=False)
        assert plan is not None
        assert plan["entry_status"] == "invalidated", (
            f"expected invalidated to be preserved, got {plan['entry_status']}"
        )
        assert plan["ready_to_trade"] is False
        reason = str(plan.get("invalid_reason") or "")
        assert "Giá đã phá vùng" in reason
        assert NO_TP1_REASON in reason
        # decision engine: invalidated -> STAND_ASIDE, not WATCH_ONLY
        result = make_final_decision(
            final_score=95, gate_result={"allowed": True},
            entry_status=plan["entry_status"], score_gap=30,
        )
        assert result["decision"] == STAND_ASIDE

    def test_watch_only_fallback_and_no_tp_reasons_compose(self, monkeypatch):
        """When both the preferred-zone fallback and the no-TP downgrade fire,
        both reasons must be visible (pipe-separated), not overwrite each
        other."""
        d1, h4, h1, m15 = _build_test_data()
        technical = build_technical_snapshot(d1, h4, h1)
        smc = build_smc_context(d1, h4, h1)
        price = technical["price"]
        atr = technical["atr_h4"] or technical["atr_d1"] or 0.0
        lvl = price - atr * 0.5
        # Zone deep enough that (entry edge -> SL) clears the 0.35*ATR
        # min-SL guard: gap = zone_width - sub_zone_width + buffer_atr.
        preferred = {
            "level": lvl, "low": lvl - atr * 0.6, "high": lvl + atr * 0.1,
            "zone_score": 80, "source": "smc_selected",
            "watch_only_fallback": True,
            "selection_reason": "stale_zone",
            "zone_type": "demand_zone",
        }
        request = AnalysisInput(
            symbol="EUR/USD", broker_symbol="EURUSDm",
            account_balance=10_000.0, risk_percent=2.0,
            contract_size_override=100_000.0,
        )
        with monkeypatch.context() as m:
            m.setattr("core.risk_engine.select_best_level", lambda *a, **kw: preferred)
            m.setattr("core.risk_engine.select_top_levels", lambda *a, **kw: [preferred])
            m.setattr("core.risk_engine._find_nearest_swing_for_sl", lambda *a, **kw: None)
            m.setattr("core.risk_engine._find_nearest_equal_level", lambda *a, **kw: None)
            m.setattr("core.risk_engine.all_target_zones_sorted", lambda *a, **kw: [])
            m.setattr("core.risk_engine.nearest_target", lambda *a, **kw: None)
            m.setattr("core.risk_engine.next_target", lambda *a, **kw: None)
            m.setattr("core.risk_engine._fib_extension_target", lambda *a, **kw: None)
            m.setattr("core.risk_engine._find_nearest_swing_for_tp", lambda *a, **kw: None)
            m.setattr("core.risk_engine.REGIME_SL_MULTIPLIER",
                      {"unknown": 0.65, "trend_up": 0.65, "trend_down": 0.65,
                       "range": 0.70, "volatile": 0.85})
            plan = build_trade_plan(
                "buy", request, technical, smc, h1, m15_candles=m15,
                preferred_zone=preferred,
            )
        assert plan is not None
        reason = str(plan.get("invalid_reason") or "")
        assert "Zone fallback" in reason
        assert NO_TP1_REASON in reason
        assert plan["entry_status"] == "watch_zone"
        assert plan["ready_to_trade"] is False
