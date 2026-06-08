from __future__ import annotations

import copy
from unittest import mock

from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput


# --- Helpers ---

def _fake_scores(buy_score: float, sell_score: float) -> dict:
    return {
        "buy": {"signal_score": buy_score, "total": buy_score},
        "sell": {"signal_score": sell_score, "total": sell_score},
    }


def _base_request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


def _fake_build_scenarios_clear_bias():
    """Tra ve scenario co m15_quality=strict, ready_to_trade=True."""
    return [{
        "type": "buy",
        "priority": "primary",
        "score": 82,
        "ready_to_trade": True,
        "price_in_entry_zone": True,
        "h1_confirmation": True,
        "m15_quality": "strict",
        "entry_zone": [1.10, 1.12],
        "stop_loss": 1.09,
        "take_profit": [1.14],
        "risk_reward": "1:2.0",
        "entry_status": "waiting_confirmation",
        "trigger_type": "engulfing",
    }]


def _call_with_mocked_scoring(
    buy_score: float,
    sell_score: float,
    data_quality: dict | None = None,
    scenarios_override: list | None = None,
) -> dict:
    """Goi analyze_symbol() voi score_scenario va build_scenarios bi mock."""

    def fake_score_scenario(side, technical, smc, risk_score, macro_score, **kw):
        score = buy_score if side == "buy" else sell_score
        return {
            "signal_score": score,
            "total": score,
            "trend_alignment": 20,
            "momentum_alignment": 15,
            "location_quality": 20,
            "smc_quality": 10,
            "smc_reason": "test",
            "risk_condition": 10,
            "macro_alignment": 15,
            "macro_confidence": 1.0,
            "correlation_adjustment": 0.0,
        }

    scenarios = scenarios_override or _fake_build_scenarios_clear_bias()

    with (
        mock.patch("core.analysis_engine.score_scenario", side_effect=fake_score_scenario),
        mock.patch("core.analysis_engine.build_scenarios", return_value=copy.deepcopy(scenarios)),
    ):
        return analyze_symbol(
            _base_request(),
            {"D1": [], "H4": [], "H1": []},  # se bi ValueError, can mock them too
        )


# --- Real test approach: monkeypatch score_scenario and build_scenarios
# --- inside analyze_symbol to control buy/sell scores precisely


def _run_analysis_with_scores(
    buy_score: float,
    sell_score: float,
    *,
    data_quality: dict | None = None,
    scenarios: list | None = None,
) -> dict:
    """Chay analyze_symbol voi score_scenario & build_scenarios & candles bi mock."""
    from datetime import datetime, timedelta, timezone
    from core.market_models import Candle

    dq = dict(data_quality or {})
    dq.setdefault("terminal_connected", True)
    dq.setdefault("broker_logged_in", True)
    dq.setdefault("spread_status", "normal")

    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    candles = [
        Candle(time=base_time + timedelta(hours=i), open=1.1, high=1.1002, low=1.0998, close=1.1001, volume=100)
        for i in range(250)
    ]
    candles_by_tf = {"D1": candles, "H4": candles, "H1": candles}

    def fake_score_scenario(side, technical, smc, risk_score, macro_score, **kw):
        score = buy_score if side == "buy" else sell_score
        return {
            "signal_score": score,
            "total": score,
            "trend_alignment": 20,
            "momentum_alignment": 15,
            "location_quality": 20,
            "smc_quality": 10,
            "smc_reason": "test",
            "risk_condition": 10,
            "macro_alignment": 15,
            "macro_confidence": 1.0,
            "correlation_adjustment": 0.0,
            "regime_weights": {"trend": 22, "momentum": 14, "location": 13, "smc": 11, "risk": 10, "macro": 30},
            "rating": "cân nhắc được",
        }

    scens = scenarios or _fake_build_scenarios_clear_bias()

    with (
        mock.patch("core.analysis_engine.score_scenario", side_effect=fake_score_scenario),
        mock.patch("core.analysis_engine.build_scenarios", return_value=copy.deepcopy(scens)),
    ):
        return analyze_symbol(
            _base_request(),
            candles_by_tf,
            data_quality=dq,
        )


# ======================================================================
# Tests
# ======================================================================


class TestScoreGapIntegration:

    def test_clear_bias_buy_no_gate_cap(self) -> None:
        """Buy 82, Sell 65 -> gap 17, ro rang, khong bi cap."""
        result = _run_analysis_with_scores(82, 65)

        assert result["direction_bias"]["best_side"] == "buy"
        assert result["direction_bias"]["score_gap"] == 17
        assert result["direction_bias"]["is_clear_bias"] is True
        assert "BUY_SELL_SCORE_GAP_LOW" not in result["trade_gate"]["warning_codes"]
        assert "decision_summary" in result
        assert result["decision_summary"]["best_side"] == "buy"
        assert result["decision_summary"]["score_gap"] == 17
        assert result["decision_summary"]["is_clear_bias"] is True

    def test_low_score_gap_gate_caps_waiting_confirmation(self) -> None:
        """Buy 80, Sell 77 -> gap 3, khong ro rang, gate cap WAITING_CONFIRMATION."""
        result = _run_analysis_with_scores(80, 77)

        assert result["direction_bias"]["best_side"] == "buy"
        assert result["direction_bias"]["score_gap"] == 3
        assert result["direction_bias"]["is_clear_bias"] is False
        assert "BUY_SELL_SCORE_GAP_LOW" in result["trade_gate"]["warning_codes"]
        assert result["trade_gate"]["decision_cap"] == "WAITING_CONFIRMATION"
        assert result["decision_summary"]["action"] != "ready"

    def test_clear_bias_sell(self) -> None:
        """Buy 61, Sell 79 -> sell ro rang."""
        result = _run_analysis_with_scores(61, 79)

        assert result["direction_bias"]["best_side"] == "sell"
        assert result["direction_bias"]["score_gap"] == 18
        assert result["direction_bias"]["is_clear_bias"] is True

    def test_equal_scores_neutral_with_cap(self) -> None:
        """Buy 70, Sell 70 -> neutral, gap 0, bi cap."""
        result = _run_analysis_with_scores(70, 70)

        assert result["direction_bias"]["best_side"] == "neutral"
        assert result["direction_bias"]["score_gap"] == 0
        assert result["direction_bias"]["is_clear_bias"] is False
        assert "BUY_SELL_SCORE_GAP_LOW" in result["trade_gate"]["warning_codes"]
        assert result["decision_summary"]["action"] != "ready"

    def test_score_gap_passed_to_trade_gate(self) -> None:
        """Kiem tra score_gap duoc truyen vao gate_context."""
        result = _run_analysis_with_scores(85, 70)

        # Gate khong bi cap vi gap 15 >= 10
        assert "BUY_SELL_SCORE_GAP_LOW" not in result["trade_gate"]["warning_codes"]
        assert result["trade_gate"]["allowed"] is True

    def test_decision_summary_has_all_new_fields(self) -> None:
        """decision_summary co day du cac field moi tu direction_bias."""
        result = _run_analysis_with_scores(82, 65)

        ds = result["decision_summary"]
        assert "best_side" in ds
        assert "score_gap" in ds
        assert "is_clear_bias" in ds
        assert "min_score_gap" in ds
        assert ds["min_score_gap"] == 10

    def test_backward_compatible_direction_bias_output(self) -> None:
        """direction_bias trong output la dict, co du cac key can thiet."""
        result = _run_analysis_with_scores(75, 60)

        db = result["direction_bias"]
        assert isinstance(db, dict)
        assert "best_side" in db
        assert "buy_score" in db
        assert "sell_score" in db
        assert "score_gap" in db
        assert "is_clear_bias" in db
        assert "min_gap" in db

    def test_trade_permission_still_present(self) -> None:
        """trade_permission cu van ton tai."""
        result = _run_analysis_with_scores(82, 65)

        tp = result["trade_permission"]
        assert "status" in tp
        assert "reason" in tp
        assert "resume_after" in tp
