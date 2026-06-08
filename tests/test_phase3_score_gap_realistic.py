from __future__ import annotations

import copy
from datetime import datetime, timedelta, timezone
from unittest import mock

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.signal_engine import calculate_direction_bias


def make_trending_candles(count: int = 120, start_price: float = 1.0800, step: float = 0.00025) -> list[Candle]:
    """Tao du lieu nen xu huong tang gia lap."""
    candles: list[Candle] = []
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start_price
    for i in range(count):
        open_ = price
        close = price + step
        high = max(open_, close) + 0.00015
        low = min(open_, close) - 0.00015
        candles.append(Candle(
            time=t + timedelta(hours=i),
            open=open_, high=high, low=low, close=close,
            volume=1000 + i,
        ))
        price = close
    return candles


def make_ranging_candles(count: int = 120, base_price: float = 1.0800) -> list[Candle]:
    """Tao du lieu nen di ngang gia lap."""
    candles: list[Candle] = []
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(count):
        offset = 0.0005 if i % 2 == 0 else -0.0005
        open_ = base_price
        close = base_price + offset
        high = max(open_, close) + 0.0002
        low = min(open_, close) - 0.0002
        candles.append(Candle(
            time=t + timedelta(hours=i),
            open=open_, high=high, low=low, close=close,
            volume=1000 + i,
        ))
    return candles


def _base_candles() -> dict[str, list[Candle]]:
    return {
        "D1": make_trending_candles(240, 1.0500, 0.0005),
        "H4": make_trending_candles(240, 1.0800, 0.00035),
        "H1": make_trending_candles(120, 1.1000, 0.0002),
    }


def _base_request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


def _run_with_mocked_scores(buy_score: float, sell_score: float) -> dict:
    """Chay analyze_symbol voi score_scenario bi mock de kiem soat diem."""
    def fake_score_scenario(side, technical, smc, risk_score, macro_score, **kw):
        score = buy_score if side == "buy" else sell_score
        return {
            "signal_score": score, "total": score,
            "trend_alignment": 20, "momentum_alignment": 15,
            "location_quality": 20, "smc_quality": 10,
            "smc_reason": "test", "risk_condition": 10,
            "macro_alignment": 15, "macro_confidence": 1.0,
            "correlation_adjustment": 0.0,
            "regime_weights": {"trend": 22, "momentum": 14, "location": 13, "smc": 11, "risk": 10, "macro": 30},
            "rating": "can nhac duoc",
        }

    fake_scenario = [{
        "type": "buy", "priority": "primary", "score": buy_score,
        "ready_to_trade": True, "price_in_entry_zone": True,
        "h1_confirmation": True, "m15_quality": "strict",
        "entry_zone": [1.10, 1.12], "stop_loss": 1.09,
        "take_profit": [1.14], "risk_reward": "1:2.0",
        "entry_status": "waiting_confirmation", "trigger_type": "engulfing",
    }]

    with (
        mock.patch("core.analysis_engine.score_scenario", side_effect=fake_score_scenario),
        mock.patch("core.analysis_engine.build_scenarios", return_value=copy.deepcopy(fake_scenario)),
    ):
        return analyze_symbol(
            _base_request(),
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "high_impact_event_within_30m": False,
            },
        )


# ======================================================================
# Test 1: output co direction_bias (dung du lieu that, khong mock score)
# ======================================================================

class TestRealisticDataDirectionBias:

    def test_output_has_direction_bias_with_real_candles(self) -> None:
        """Phan tich voi du lieu nen gia that -> output co direction_bias."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "high_impact_event_within_30m": False,
            },
        )

        assert "direction_bias" in result
        db = result["direction_bias"]
        assert "score_gap" in db
        assert "is_clear_bias" in db
        assert "best_side" in db
        assert "buy_score" in db
        assert "sell_score" in db
        assert "min_gap" in db

    def test_decision_summary_has_score_gap_fields_with_real_candles(self) -> None:
        """decision_summary co score_gap va is_clear_bias."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "high_impact_event_within_30m": False,
            },
        )

        ds = result["decision_summary"]
        assert "score_gap" in ds
        assert "is_clear_bias" in ds
        assert "best_side" in ds
        assert "min_score_gap" in ds

    def test_output_has_direction_bias_with_ranging_candles(self) -> None:
        """Dung du lieu ranging cung phai co direction_bias."""
        ranging = {
            "D1": make_ranging_candles(240, 1.0500),
            "H4": make_ranging_candles(240, 1.0800),
            "H1": make_ranging_candles(120, 1.1000),
        }
        request = _base_request()
        result = analyze_symbol(
            request,
            ranging,
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "high_impact_event_within_30m": False,
            },
        )

        assert "direction_bias" in result
        assert "score_gap" in result["direction_bias"]
        assert "trade_gate" in result


# ======================================================================
# Test 2: Low score gap -> gate cap (dung mock score)
# ======================================================================

class TestLowScoreGapGateCap:

    def test_low_gap_triggers_waiting_confirmation(self) -> None:
        """Buy 80, Sell 77 -> gap 3 -> WAITING_CONFIRMATION, khong ready."""
        result = _run_with_mocked_scores(80, 77)

        assert result["direction_bias"]["score_gap"] == 3
        assert result["direction_bias"]["is_clear_bias"] is False
        assert "BUY_SELL_SCORE_GAP_LOW" in result["trade_gate"]["warning_codes"]
        assert result["trade_gate"]["decision_cap"] == "WAITING_CONFIRMATION"
        assert result["decision_summary"]["action"] != "ready"

    def test_clear_gap_no_warning(self) -> None:
        """Buy 83, Sell 62 -> gap 21 -> khong warning, khong cap."""
        result = _run_with_mocked_scores(83, 62)

        assert result["direction_bias"]["score_gap"] == 21
        assert result["direction_bias"]["is_clear_bias"] is True
        assert "BUY_SELL_SCORE_GAP_LOW" not in result["trade_gate"]["warning_codes"]

    def test_equal_scores_neutral_and_capped(self) -> None:
        """Buy 70, Sell 70 -> neutral, gap 0 -> cap WAITING_CONFIRMATION."""
        result = _run_with_mocked_scores(70, 70)

        assert result["direction_bias"]["best_side"] == "neutral"
        assert result["direction_bias"]["score_gap"] == 0
        assert result["direction_bias"]["is_clear_bias"] is False
        assert "BUY_SELL_SCORE_GAP_LOW" in result["trade_gate"]["warning_codes"]
        assert result["decision_summary"]["action"] != "ready"

    def test_exact_threshold_gap_passes(self) -> None:
        """Buy 75, Sell 65 -> gap 10 >= 10 -> clear, khong warning."""
        result = _run_with_mocked_scores(75, 65)

        assert result["direction_bias"]["score_gap"] == 10
        assert result["direction_bias"]["is_clear_bias"] is True
        assert "BUY_SELL_SCORE_GAP_LOW" not in result["trade_gate"]["warning_codes"]


# ======================================================================
# Test 3: score_gap in gate_context
# ======================================================================

class TestScoreGapInTradeGate:

    def test_trade_gate_receives_score_gap(self) -> None:
        """trade_gate output co score gap context."""
        result = _run_with_mocked_scores(82, 65)

        tg = result["trade_gate"]
        assert tg["allowed"] is True
        # Gap 17 >= 10 nen khong co warning score gap
        assert "BUY_SELL_SCORE_GAP_LOW" not in tg["warning_codes"]

    def test_trade_gate_does_not_hard_block_on_low_gap(self) -> None:
        """Score gap thap chi la warning, khong block cung tai khoan."""
        result = _run_with_mocked_scores(80, 77)

        tg = result["trade_gate"]
        assert tg["allowed"] is True  # van cho phep, chi cap mem
        assert tg["decision_cap"] == "WAITING_CONFIRMATION"
        assert "BUY_SELL_SCORE_GAP_LOW" in tg["warning_codes"]
        assert "BUY_SELL_SCORE_GAP_LOW" not in tg["block_codes"]

    def test_trade_permission_not_blocked_by_low_gap(self) -> None:
        """Score gap thap khong lam trade_permission thanh blocked."""
        result = _run_with_mocked_scores(80, 77)

        tp = result["trade_permission"]
        assert tp["status"] != "blocked"


# ======================================================================
# Test 4: calculate_direction_bias helper safe with real-like data
# ======================================================================

class TestCalculateDirectionBiasEdgeCases:

    def test_input_none_safe(self) -> None:
        result = calculate_direction_bias(None, None)
        assert result["best_side"] == "neutral"
        assert result["buy_score"] == 0
        assert result["sell_score"] == 0
        assert result["score_gap"] == 0

    def test_input_empty_dict_safe(self) -> None:
        result = calculate_direction_bias({}, {})
        assert result["best_side"] == "neutral"
        assert result["score_gap"] == 0

    def test_fallback_to_total_when_no_signal_score(self) -> None:
        buy = {"total": 76}
        sell = {"total": 58}
        result = calculate_direction_bias(buy, sell)
        assert result["buy_score"] == 76
        assert result["sell_score"] == 58
        assert result["score_gap"] == 18
        assert result["best_side"] == "buy"

    def test_signal_score_priority_over_total(self) -> None:
        buy = {"signal_score": 90, "total": 30}
        sell = {"signal_score": 70, "total": 80}
        result = calculate_direction_bias(buy, sell)
        assert result["buy_score"] == 90
        assert result["sell_score"] == 70
