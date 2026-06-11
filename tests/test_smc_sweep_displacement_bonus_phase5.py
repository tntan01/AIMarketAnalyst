from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.signal_engine import score_scenario


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _tech_bullish() -> dict:
    return {
        "price": 1.1000,
        "ema50_d1": 1.0900,
        "ema200_d1": 1.0700,
        "ema50_h4": 1.0950,
        "structure_h4": "HH/HL",
        "structure_d1": "HH/HL",
        "rsi_h4": 45.0,
        "rsi_h4_previous": 40.0,
        "macd_histogram_h4": {"value": 0.02, "previous_value": 0.01, "previous2_value": 0.0},
        "atr_h4": 0.005,
        "atr_d1": 0.008,
        "atr_avg_14d": 0.006,
        "support_zones": [
            {"level": 1.0900, "low": 1.0880, "high": 1.0920, "strength": "moderate",
             "confluence_count": 1, "consolidation_bars": 1}
        ],
        "resistance_zones": [
            {"level": 1.1150, "low": 1.1130, "high": 1.1170, "strength": "weak",
             "confluence_count": 0, "consolidation_bars": 0}
        ],
    }


def _smc_aligned_buy() -> dict:
    return {
        "H4": {
            "bos": True, "choch": False, "displacement": "bullish",
            "demand_zones": [
                {"type": "demand_zone", "zone_score": 80, "zone_location": "discount",
                 "liquidity_sweep": True, "broken": False, "mitigated": False, "test_count": 0}
            ],
        },
        "H1": {
            "bos": True, "choch": False, "displacement": "bullish",
            "liquidity_sweeps": {"swept_lows": [1.09]},
        },
    }


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


def _base_candles() -> dict[str, list[Candle]]:
    return {
        "D1": _candles(240, 1.05, 0.0005, 0.002),
        "H4": _candles(240, 1.08, 0.00035, 0.0015),
        "H1": _candles(120, 1.12, 0.0002, 0.001),
    }


def _base_request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


# ---------------------------------------------------------------------------
# Test 1 — Du 3 dieu kien -> bonus +10
# ---------------------------------------------------------------------------

def test_all_three_conditions_grant_bonus():
    """liquidity_sweep_aligned + displacement_aligned + M15 strict = bonus."""
    fake_smc_flags = {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 80,
        "raw": {},
    }

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
        "entry_status": "confirmed_entry",
        "trigger_type": "engulfing",
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
            result = analyze_symbol(
                _base_request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

    # Bonus removed in Phase 1 backtest improvement — conditions confirmed entry
    # too late (after main move). Bonus is kept as metadata only (always 0).
    assert result["scenario_scores"]["buy"]["entry_quality_bonus"] == 0
    assert "SWEEP_DISPLACEMENT_M15_ALIGNED" not in result["scenario_scores"]["buy"].get("reason_codes", [])
    assert "entry_quality_bonus" in result["scenario_scores"]["sell"]
    assert result["scenario_scores"]["sell"]["entry_quality_bonus"] == 0


# ---------------------------------------------------------------------------
# Test 2 — M15 loose -> khong bonus
# ---------------------------------------------------------------------------

def test_m15_loose_no_bonus():
    """M15 loose thi khong duoc bonus."""
    fake_smc_flags = {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 80,
        "raw": {},
    }

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 85,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "loose",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "waiting_confirmation",
        "trigger_type": "none",
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
            result = analyze_symbol(
                _base_request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

    assert result["scenario_scores"]["buy"]["entry_quality_bonus"] == 0
    assert "SWEEP_DISPLACEMENT_M15_ALIGNED" not in result["scenario_scores"]["buy"].get("reason_codes", [])


# ---------------------------------------------------------------------------
# Test 3 — Thieu displacement -> khong bonus
# ---------------------------------------------------------------------------

def test_no_displacement_no_bonus():
    fake_smc_flags = {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": False,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 70,
        "raw": {},
    }

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 75,
        "ready_to_trade": False,
        "price_in_entry_zone": False,
        "h1_confirmation": False,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "waiting_confirmation",
        "trigger_type": "none",
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
            result = analyze_symbol(
                _base_request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

    assert result["scenario_scores"]["buy"]["entry_quality_bonus"] == 0


# ---------------------------------------------------------------------------
# Test 4 — Thieu liquidity sweep -> khong bonus
# ---------------------------------------------------------------------------

def test_no_sweep_no_bonus():
    fake_smc_flags = {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": False,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 70,
        "raw": {},
    }

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 75,
        "ready_to_trade": False,
        "price_in_entry_zone": False,
        "h1_confirmation": False,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "waiting_confirmation",
        "trigger_type": "none",
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
            result = analyze_symbol(
                _base_request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

    assert result["scenario_scores"]["buy"]["entry_quality_bonus"] == 0


# ---------------------------------------------------------------------------
# Test 5 — CHOCH nguoc huong -> khong bonus (CHOCH cap thang)
# ---------------------------------------------------------------------------

def test_choch_against_prevents_bonus():
    """CHOCH nguoc huong -> bonus khong duoc ap dung."""
    fake_smc_flags = {
        "zone_broken": False,
        "choch_against_direction": True,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": False,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 70,
        "raw": {},
    }

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 55,
        "ready_to_trade": False,
        "price_in_entry_zone": False,
        "h1_confirmation": False,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "invalidated",
        "trigger_type": "none",
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
            result = analyze_symbol(
                _base_request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

    assert result["scenario_scores"]["buy"]["entry_quality_bonus"] == 0
    assert "SWEEP_DISPLACEMENT_M15_ALIGNED" not in result["scenario_scores"]["buy"].get("reason_codes", [])


# ---------------------------------------------------------------------------
# Test 6 — Score khong vuot 100 sau bonus
# ---------------------------------------------------------------------------

def test_bonus_does_not_exceed_100():
    """Bonus +10 tren score cao van khong vuot 100."""
    result = score_scenario("buy", _tech_bullish(), _smc_aligned_buy(), 15, 30,
                            macro_confidence=1.0, macro_context={"buy": 28, "sell": 5})
    # score_scenario mac dinh entry_quality_bonus=0
    assert result["entry_quality_bonus"] == 0
    assert result["signal_score"] <= 100
    assert result["signal_score"] == result["total"]


# ---------------------------------------------------------------------------
# Test 7 — Zone broken gate van thang bonus
# ---------------------------------------------------------------------------

def test_zone_broken_gate_wins_over_bonus():
    """Zone broken + bonus -> gate van WATCH_ONLY, action != ready."""
    fake_smc_flags = {
        "zone_broken": True,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 80,
        "raw": {},
    }

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 90,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "confirmed_entry",
        "trigger_type": "engulfing",
    }

    with mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags):
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]):
            result = analyze_symbol(
                _base_request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

    assert result["smc_trade_flags"]["zone_broken"] is True
    assert result["trade_gate"]["decision_cap"] == "WATCH_ONLY"
    assert "ZONE_BROKEN" in result["trade_gate"]["warning_codes"]
    assert result["decision_summary"]["action"] != "ready"
    # Bonus removed in Phase 1 — zone_broken gate still works independently
    assert result["scenario_scores"]["buy"]["entry_quality_bonus"] == 0


# ---------------------------------------------------------------------------
# Test 8 — score_scenario mac dinh entry_quality_bonus = 0
# ---------------------------------------------------------------------------

def test_score_scenario_default_entry_quality_bonus_zero():
    result = score_scenario("buy", _tech_bullish(), _smc_aligned_buy(), 12, 20)
    assert "entry_quality_bonus" in result
    assert result["entry_quality_bonus"] == 0


# ---------------------------------------------------------------------------
# Test 9 — bonus recomputes score_gap for gate and decision engine
# ---------------------------------------------------------------------------


def test_entry_quality_bonus_recomputes_score_gap_for_gate_and_decision():
    """When entry_quality_bonus widens the Buy/Sell gap from <10 to >=10,
    direction_bias, gate, and decision_engine must all see the new gap."""
    fake_smc_flags = {
        "zone_broken": False,
        "choch_against_direction": False,
        "liquidity_sweep_aligned": True,
        "displacement_aligned": True,
        "has_selected_zone": True,
        "selected_zone_type": "demand_zone",
        "selected_zone_score": 80,
        "raw": {},
    }

    fake_scenario = {
        "type": "buy",
        "priority": "primary",
        "score": 72,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "expected_effective_rr": 2.0,
        "entry_status": "confirmed_entry",
        "trigger_type": "engulfing",
    }

    def fake_score_scenario(side, technical, smc, risk_score, macro_score, **kw):
        score = 72 if side == "buy" else 65
        return {
            "signal_score": score,
            "total": score,
            "trend_alignment": 18,
            "momentum_alignment": 12,
            "location_quality": 18,
            "smc_quality": 10,
            "smc_reason": "BOS H4 bullish",
            "risk_condition": 8,
            "macro_alignment": 15,
            "macro_confidence": 1.0,
            "correlation_adjustment": 0.0,
            "regime_weights": {"trend": 22, "momentum": 14, "location": 13, "smc": 11, "risk": 10, "macro": 30},
            "rating": "cân nhắc được",
            "reason_codes": [],
            "penalty_codes": [],
        }

    with (
        mock.patch("core.analysis_engine.extract_smc_trade_flags", return_value=fake_smc_flags),
        mock.patch("core.analysis_engine.build_scenarios", return_value=[fake_scenario]),
        mock.patch("core.analysis_engine.score_scenario", side_effect=fake_score_scenario),
    ):
        result = analyze_symbol(
            _base_request(),
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

    # Bonus removed in Phase 1 — scores unchanged by bonus
    assert result["scenario_scores"]["buy"]["entry_quality_bonus"] == 0
    assert result["scenario_scores"]["buy"]["signal_score"] == 72
    assert result["scenario_scores"]["buy"]["total"] == 72

    # direction_bias reflects raw (non-bonus) scores
    assert result["direction_bias"]["buy_score"] == 72
    assert result["direction_bias"]["sell_score"] == 65
    assert result["direction_bias"]["score_gap"] == 7
    assert result["direction_bias"]["is_clear_bias"] is False

    # decision_summary consistent
    assert result["decision_summary"]["score_gap"] == 7
    assert result["decision_summary"]["is_clear_bias"] is False

    # Gate warns about low score gap (gap=7 < min_gap=10)
    assert "BUY_SELL_SCORE_GAP_LOW" in result["trade_gate"]["warning_codes"]

    # Decision engine may warn about low score gap (gap=7 < min_gap=10)
    assert "DECISION_SCORE_GAP_LOW" not in result["decision_engine"]["warning_codes"]

    # final_score_detail uses raw signal_score (no bonus)
    assert result["final_score_detail"]["score_inputs"]["signal_score"] == 72
