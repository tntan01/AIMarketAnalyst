from __future__ import annotations

import pytest
from unittest import mock

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import (
    AnalysisInput,
    build_trade_plan,
    calculate_expected_effective_rr,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _candles(count: int, start: float, step: float, amplitude: float) -> list[Candle]:
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for index in range(count):
        wave = amplitude * ((index % 10) - 5) / 5
        close = start + index * step + wave
        open_price = close - step * 0.2
        rows.append(
            Candle(
                time=base_time + timedelta(hours=index),
                open=open_price,
                high=max(open_price, close) + amplitude * 0.8,
                low=min(open_price, close) - amplitude * 0.8,
                close=close,
                volume=100,
            )
        )
    return rows


def _strong_bullish_candles() -> dict[str, list[Candle]]:
    """Xu huong tang manh de sinh scenario hop le."""
    return {
        "D1": _candles(240, 1.08, 0.0008, 0.002),
        "H4": _candles(240, 1.10, 0.0006, 0.0015),
        "H1": _candles(120, 1.14, 0.0004, 0.001),
    }


def _tech_stub() -> dict:
    return {
        "price": 1.1000,
        "atr_h4": 0.005,
        "atr_d1": 0.008,
        "support_zones": [
            {"level": 1.0960, "low": 1.094, "high": 1.098, "strength": "strong",
             "confluence_count": 2, "consolidation_bars": 3}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.113, "high": 1.117, "strength": "moderate",
             "confluence_count": 0, "consolidation_bars": 1}
        ],
    }


def _tech_stub_sell() -> dict:
    return {
        "price": 1.1000,
        "atr_h4": 0.005,
        "atr_d1": 0.008,
        "support_zones": [
            {"level": 1.0850, "low": 1.083, "high": 1.087, "strength": "moderate",
             "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1040, "low": 1.102, "high": 1.106, "strength": "strong",
             "confluence_count": 2, "consolidation_bars": 3}
        ],
    }


# ---------------------------------------------------------------------------
# Test 1 — build_trade_plan directly: expected_effective_rr co mat
# ---------------------------------------------------------------------------

def test_build_trade_plan_has_expected_effective_rr():
    plan = build_trade_plan(
        side="buy",
        request=AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        technical=_tech_stub(),
        smc={"H4": {}},
        h1_candles=[],
        spread_price=0.0002,
    )
    assert plan is not None
    assert "expected_effective_rr" in plan
    assert plan["expected_effective_rr"] > 0


# ---------------------------------------------------------------------------
# Test 2 — expected_effective_rr nho hon ideal R:R
# ---------------------------------------------------------------------------

def test_effective_rr_lower_than_ideal():
    plan = build_trade_plan(
        side="buy",
        request=AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        technical=_tech_stub(),
        smc={"H4": {}},
        h1_candles=[],
        spread_price=0.0002,
    )
    ideal_rr = float(plan["risk_reward"].split(":", 1)[1])
    effective_rr = plan["expected_effective_rr"]
    assert effective_rr <= ideal_rr


# ---------------------------------------------------------------------------
# Test 3 — spread 0 → effective = ideal
# ---------------------------------------------------------------------------

def test_zero_spread_effective_equals_ideal():
    plan = build_trade_plan(
        side="buy",
        request=AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        technical=_tech_stub(),
        smc={"H4": {}},
        h1_candles=[],
        spread_price=0.0,
    )
    ideal_rr = float(plan["risk_reward"].split(":", 1)[1])
    assert plan["expected_effective_rr"] == pytest.approx(ideal_rr, rel=0.01)


# ---------------------------------------------------------------------------
# Test 4 — sell cung co expected_effective_rr
# ---------------------------------------------------------------------------

def test_sell_plan_has_expected_effective_rr():
    plan = build_trade_plan(
        side="sell",
        request=AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        technical=_tech_stub_sell(),
        smc={"H4": {}},
        h1_candles=[],
        spread_price=0.0002,
    )
    assert plan is not None
    assert "expected_effective_rr" in plan
    assert plan["expected_effective_rr"] > 0


# ---------------------------------------------------------------------------
# Test 5 — analyze_symbol integration: scenario co expected_effective_rr
# ---------------------------------------------------------------------------

def test_analyze_symbol_scenario_has_expected_effective_rr():
    result = analyze_symbol(
        AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        _strong_bullish_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "spread_points": 0.0002,
        },
    )

    scenarios = result.get("scenarios", [])
    assert len(scenarios) > 0
    primary = scenarios[0]
    # Primary co the la trade plan hoac stand_aside
    if primary.get("type") != "stand_aside":
        assert "expected_effective_rr" in primary
        assert primary["expected_effective_rr"] > 0


# ---------------------------------------------------------------------------
# Test 6 — legacy output keys preserved
# ---------------------------------------------------------------------------

def test_legacy_risk_reward_preserved():
    plan = build_trade_plan(
        side="buy",
        request=AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000),
        technical=_tech_stub(),
        smc={"H4": {}},
        h1_candles=[],
    )
    assert "risk_reward" in plan
    assert "entry_zone" in plan
    assert "stop_loss" in plan
    assert "take_profit" in plan
    assert "expected_effective_rr" in plan
