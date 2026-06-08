from __future__ import annotations

import pytest
from unittest import mock

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import (
    AnalysisInput,
    calculate_expected_effective_rr,
    calculate_spread_cost,
)
from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# Test 1 — effective RR thap hon ideal RR (co spread)
# ---------------------------------------------------------------------------

def test_effective_rr_lower_than_ideal_with_spread_realistic():
    """Buy: entry=1.1000, SL=1.0950, TP=1.1070, spread=0.0003."""
    ideal_rr = abs(1.1070 - 1.1000) / abs(1.1000 - 1.0950)  # 0.007 / 0.005 = 1.4
    effective_rr = calculate_expected_effective_rr(
        direction="buy", entry=1.1000, stop_loss=1.0950,
        take_profit=1.1070, spread_price=0.0003,
    )
    assert effective_rr < ideal_rr
    assert effective_rr == pytest.approx(1.2641, rel=1e-3)


# ---------------------------------------------------------------------------
# Test 2 — sell effective RR thap hon ideal
# ---------------------------------------------------------------------------

def test_sell_effective_rr_lower_than_ideal():
    """Sell: entry=1.1000, SL=1.1050, TP=1.0930, spread=0.0003."""
    ideal_rr = abs(1.1000 - 1.0930) / abs(1.1050 - 1.1000)  # 0.007 / 0.005 = 1.4
    effective_rr = calculate_expected_effective_rr(
        direction="sell", entry=1.1000, stop_loss=1.1050,
        take_profit=1.0930, spread_price=0.0003,
    )
    assert effective_rr < ideal_rr
    assert effective_rr == pytest.approx(1.2641, rel=1e-3)


# ---------------------------------------------------------------------------
# Test 3 — RR thap bi gate WATCH_ONLY
# ---------------------------------------------------------------------------

def test_low_effective_rr_triggers_gate_watch_only():
    effective_rr = calculate_expected_effective_rr(
        direction="buy", entry=1.1000, stop_loss=1.0950,
        take_profit=1.1070, spread_price=0.0003,
    )
    # effective_rr ≈ 1.264 < 1.3
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "score_gap": 30,
        "expected_effective_rr": effective_rr,
        "min_expected_effective_rr": 1.3,
    }
    gate = check_trade_gates(context)
    assert gate["decision_cap"] == "WATCH_ONLY"
    assert "EXPECTED_RR_TOO_LOW" in gate["warning_codes"]
    assert gate["allowed"] is True  # soft cap, not hard block


# ---------------------------------------------------------------------------
# Test 4 — RR du tot (TP xa hon) khong cap
# ---------------------------------------------------------------------------

def test_good_effective_rr_no_cap_realistic():
    """TP=1.1120 → ideal RR=0.012/0.005=2.4, effective > 1.3."""
    effective_rr = calculate_expected_effective_rr(
        direction="buy", entry=1.1000, stop_loss=1.0950,
        take_profit=1.1120, spread_price=0.0003,
    )
    assert effective_rr > 1.3
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "m15_quality": "strict",
        "score_gap": 30,
        "expected_effective_rr": effective_rr,
    }
    gate = check_trade_gates(context)
    assert "EXPECTED_RR_TOO_LOW" not in gate["warning_codes"]


# ---------------------------------------------------------------------------
# Test 5 — spread_cost hoạt động an toàn
# ---------------------------------------------------------------------------

def test_spread_cost_safe_realistic():
    assert calculate_spread_cost(0.0003) == 0.0003
    assert calculate_spread_cost(None) == 0.0
    assert calculate_spread_cost("0.00015") == 0.00015
    assert calculate_spread_cost(-0.001) == 0.0
    assert calculate_spread_cost("abc") == 0.0


# ---------------------------------------------------------------------------
# Test 6 — effective_rr an toan voi input thieu
# ---------------------------------------------------------------------------

def test_effective_rr_safe_with_missing_inputs():
    assert calculate_expected_effective_rr("buy", None, 1.0, 1.2, 0.0001) == 0.0
    assert calculate_expected_effective_rr("buy", 1.1, None, 1.2, 0.0001) == 0.0
    assert calculate_expected_effective_rr("buy", 1.1, 1.0, None, 0.0001) == 0.0
    assert calculate_expected_effective_rr("hold", 1.1, 1.0, 1.2, 0.0001) == 0.0
    assert calculate_expected_effective_rr("buy", 1.1, 1.1, 1.2, 0.0) == 0.0  # SL=entry


# ---------------------------------------------------------------------------
# Test 7 — analyze_symbol: RR thap → action != ready
# ---------------------------------------------------------------------------

def _candles_for_test(count=120, start=1.08, step=0.0004):
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for i in range(count):
        close = start + i * step
        rows.append(Candle(
            time=base_time + timedelta(hours=i),
            open=close - 0.0001,
            high=close + 0.0003,
            low=close - 0.0003,
            close=close,
            volume=100,
        ))
    return rows


def test_analyze_symbol_low_rr_not_ready():
    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 88,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "expected_effective_rr": 1.1,
        "entry_status": "confirmed_entry",
        "trigger_type": "engulfing",
    }

    h1 = _candles_for_test(200)
    candles = {"D1": h1, "H4": h1, "H1": h1}
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
        result = analyze_symbol(
            request, candles,
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

    assert "EXPECTED_RR_TOO_LOW" in result["trade_gate"]["warning_codes"]
    assert result["trade_gate"]["decision_cap"] == "WATCH_ONLY"
    assert result["decision_summary"]["action"] != "ready"


# ---------------------------------------------------------------------------
# Test 8 — Output cac phase truoc van con
# ---------------------------------------------------------------------------

def test_all_phase_output_keys_preserved():
    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 85,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "expected_effective_rr": 1.8,
        "entry_status": "confirmed_entry",
        "trigger_type": "engulfing",
    }

    h1 = _candles_for_test(200)
    candles = {"D1": h1, "H4": h1, "H1": h1}
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
        result = analyze_symbol(request, candles, data_quality={
            "terminal_connected": True, "broker_logged_in": True, "spread_status": "normal",
        })

    # Phase 1-3 keys
    assert "signal_score" in result["scenario_scores"]["buy"]
    assert "trade_gate" in result
    assert "direction_bias" in result
    assert "decision_summary" in result

    # Phase 4 keys
    assert "macro_status" in result["scenario_scores"]["buy"]

    # Phase 5 keys
    assert "smc_trade_flags" in result

    # Phase 6 keys
    assert "expected_effective_rr" in result["scenarios"][0]
