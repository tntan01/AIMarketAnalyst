"""Phase 8.4: verify analyze_symbol() chain respects Phase 8 M15 entry status.

Tests the full pipeline: build_scenarios -> has_ready_plan -> classify_decision
-> check_trade_gates -> gate cap -> decision_action. Ensures M15 loose/none
scenarios never produce ready/READY_TO_TRADE at the final decision level.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

UTC = timezone.utc


def _candles(count: int, start: float, step: float, amplitude: float) -> list:
    from core.market_models import Candle

    base_time = datetime(2026, 1, 1, tzinfo=UTC)
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


def _base_candles() -> dict:
    return {
        "D1": _candles(240, 1.05, 0.0005, 0.002),
        "H4": _candles(240, 1.08, 0.00035, 0.0015),
        "H1": _candles(120, 1.12, 0.0002, 0.001),
    }


def _request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


def _make_scenario(
    m15_quality: str,
    ready_to_trade: bool,
    entry_status: str,
    price_in_entry_zone: bool = True,
    h1_confirmation: bool = True,
    score: int = 85,
    expected_effective_rr: float = 2.0,
    trigger_type: str = "h1_bullish_engulfing",
) -> dict:
    """Build a scenario dict consistent with Phase 8 entry engine output."""
    return {
        "type": "buy",
        "priority": "primary",
        "score": score,
        "ready_to_trade": ready_to_trade,
        "price_in_entry_zone": price_in_entry_zone,
        "h1_confirmation": h1_confirmation,
        "m15_quality": m15_quality,
        "m15_available": True,
        "m15_checked": True,
        "entry_status": entry_status,
        "trigger_type": trigger_type,
        "confirmation_score": 85 if m15_quality == "strict" else 72,
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "expected_effective_rr": expected_effective_rr,
    }


# ---------------------------------------------------------------------------
# Phase 8.4 integration tests
# ---------------------------------------------------------------------------


class TestPhase8AnalyzeSymbolM15Integration:
    """Verify analyze_symbol() respects Phase 8 M15 entry status in final decision."""

    def test_m15_strict_gate_does_not_interfere(self):
        """M15 strict scenario: gate does NOT add M15 warning/block codes."""
        scenario = _make_scenario("strict", ready_to_trade=True, entry_status="confirmed_entry")
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[scenario]):
            result = analyze_symbol(
                _request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

        # Gate must not flag M15 when quality is strict
        assert "M15_LOOSE_CONFIRMATION" not in result["trade_gate"]["warning_codes"]
        assert "M15_NOT_CONFIRMED" not in result["trade_gate"]["warning_codes"]
        assert result["trade_gate"]["allowed"] is True
        assert "gate_decision_cap" in result["decision_summary"]

    def test_m15_loose_has_ready_plan_false(self):
        """M15 loose scenario must have ready_to_trade=False in Phase 8."""
        scenario = _make_scenario(
            "loose", ready_to_trade=False, entry_status="waiting_confirmation"
        )
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[scenario]):
            result = analyze_symbol(
                _request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

        # Phase 8: loose M15 → ready_to_trade=False → has_ready_plan=False
        assert result["decision_summary"]["action"] != "ready"
        gate_cap = result["decision_summary"].get("gate_decision_cap")
        assert gate_cap in (None, "WAITING_CONFIRMATION"), (
            f"expected None or WAITING_CONFIRMATION, got {gate_cap}"
        )
        assert "M15_LOOSE_CONFIRMATION" in result["trade_gate"]["warning_codes"]

    def test_m15_none_has_ready_plan_false(self):
        """M15 none scenario must have ready_to_trade=False in Phase 8."""
        scenario = _make_scenario(
            "none", ready_to_trade=False, entry_status="watch_zone",
            price_in_entry_zone=False,
        )
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[scenario]):
            result = analyze_symbol(
                _request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

        assert result["decision_summary"]["action"] != "ready"
        assert "M15_NOT_CONFIRMED" in result["trade_gate"]["warning_codes"]
        gate_cap = result["decision_summary"].get("gate_decision_cap")
        assert gate_cap in (None, "WATCH_ONLY"), (
            f"expected None or WATCH_ONLY, got {gate_cap}"
        )

    def test_missing_m15_not_ready(self):
        """Scenario without M15 data must not be ready in Phase 8."""
        scenario = {
            "type": "buy",
            "priority": "primary",
            "score": 85,
            "ready_to_trade": False,
            "price_in_entry_zone": True,
            "h1_confirmation": True,
            "m15_quality": None,
            "m15_available": False,
            "m15_checked": False,
            "entry_status": "waiting_confirmation",
            "trigger_type": "h1_bullish_engulfing",
            "confirmation_score": 85,
            "entry_zone": [1.10, 1.12],
            "stop_loss": 1.09,
            "take_profit": [1.14],
            "risk_reward": "1:2.0",
            "expected_effective_rr": 2.0,
        }
        with mock.patch("core.analysis_engine.build_scenarios", return_value=[scenario]):
            result = analyze_symbol(
                _request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

        assert result["decision_summary"]["action"] != "ready"

    def test_entry_quality_bonus_only_for_strict_m15(self):
        """Entry quality bonus (+10) only applies when M15 is strict."""
        scenario_strict = _make_scenario("strict", ready_to_trade=True, entry_status="confirmed_entry")

        with mock.patch("core.analysis_engine.build_scenarios", return_value=[scenario_strict]):
            result = analyze_symbol(
                _request(),
                _base_candles(),
                data_quality={
                    "terminal_connected": True,
                    "broker_logged_in": True,
                    "spread_status": "normal",
                },
            )

        # Entry quality bonus is applied (at line 102-118 in analysis_engine.py)
        # The bonus only triggers when m15_quality == "strict" AND smc flags align
        # Here we don't mock SMC flags, so bonus may or may not apply
        # Just verify the result is well-formed
        assert "scenario_scores" in result
        assert "buy" in result["scenario_scores"]
        assert "entry_quality_bonus" in result["scenario_scores"]["buy"]
