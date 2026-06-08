from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.trade_gate_engine import check_trade_gates


def make_candles(count: int = 100, start_price: float = 1.0800, step: float = 0.0003) -> list[Candle]:
    """Tao du lieu nen gia giống that cho EUR/USD."""
    candles: list[Candle] = []
    t = datetime(2026, 1, 1, tzinfo=timezone.utc)
    price = start_price

    for i in range(count):
        open_ = price
        close = price + step
        high = max(open_, close) + 0.0002
        low = min(open_, close) - 0.0002

        candles.append(
            Candle(
                time=t + timedelta(hours=i),
                open=open_,
                high=high,
                low=low,
                close=close,
                volume=1000,
            )
        )
        price = close

    return candles


def _base_candles() -> dict[str, list[Candle]]:
    return {
        "D1": make_candles(240, 1.0500, 0.0005),
        "H4": make_candles(240, 1.0800, 0.00035),
        "H1": make_candles(120, 1.1000, 0.0002),
    }


def _base_request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


# ======================================================================
# Tests với analyze_symbol() — dữ liệu nến giả giống thật
# ======================================================================


class TestAnalyzeSymbolWithGate:
    """Integration tests: analyze_symbol() + trade gate."""

    def test_normal_data_gate_passes(self) -> None:
        """Dữ liệu bình thường, gate không chặn."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "high_impact_event_within_30m": False,
                "news_in_3h": False,
            },
        )

        assert "trade_gate" in result
        assert result["trade_gate"]["allowed"] is True
        # decision_cap có thể là None hoặc soft cap từ scenario, nhưng không phải TRADE_BLOCKED
        assert result["trade_gate"]["decision_cap"] != "TRADE_BLOCKED"
        assert "trade_permission" in result
        assert "decision_summary" in result

    def test_spread_abnormal_blocks(self) -> None:
        """Spread bất thường -> block."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "abnormal",
            },
        )

        assert result["trade_gate"]["allowed"] is False
        assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
        assert "SPREAD_ABNORMAL" in result["trade_gate"]["block_codes"]
        assert result["trade_permission"]["status"] == "blocked"
        assert result["decision_summary"]["action"] == "stand_aside"

    def test_high_impact_news_blocks(self) -> None:
        """Tin mạnh trong 30p -> block."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "high_impact_event_within_30m": True,
            },
        )

        assert result["trade_gate"]["allowed"] is False
        assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
        assert "HIGH_IMPACT_NEWS_NEARBY" in result["trade_gate"]["block_codes"]
        assert result["trade_permission"]["status"] == "blocked"
        assert result["decision_summary"]["action"] == "stand_aside"

    def test_data_quality_warning_blocks(self) -> None:
        """Cảnh báo chất lượng dữ liệu -> block."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "warning": "MT5 data delayed",
            },
        )

        assert result["trade_gate"]["allowed"] is False
        assert result["trade_gate"]["decision_cap"] == "TRADE_BLOCKED"
        assert "DATA_QUALITY_WARNING" in result["trade_gate"]["block_codes"]
        assert result["trade_permission"]["status"] == "blocked"

    def test_mt5_not_ready_blocks(self) -> None:
        """MT5 chưa sẵn sàng -> block."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": False,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

        assert result["trade_gate"]["allowed"] is False
        assert "MT5_NOT_READY" in result["trade_gate"]["block_codes"]
        assert result["trade_permission"]["status"] == "blocked"

    def test_decision_summary_has_all_gate_fields(self) -> None:
        """decision_summary có đầy đủ gate fields."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

        ds = result["decision_summary"]
        assert "gate_decision_cap" in ds
        assert "gate_allowed" in ds
        assert isinstance(ds["gate_block_codes"], list)
        assert isinstance(ds["gate_warning_codes"], list)
        assert "main_view" in ds
        assert "action" in ds
        assert "best_scenario" in ds
        assert "best_score" in ds

    def test_trade_permission_backward_compatible(self) -> None:
        """trade_permission giữ nguyên các key cũ."""
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )

        tp = result["trade_permission"]
        assert "status" in tp
        assert "reason" in tp
        assert "resume_after" in tp

    def test_decision_action_uses_old_states_only(self) -> None:
        """decision_action chỉ dùng state cũ: ready/watch/wait_for_confirmation/stand_aside."""
        valid_actions = {"ready", "watch", "wait_for_confirmation", "stand_aside"}

        # Test normal case
        request = _base_request()
        result = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )
        assert result["decision_summary"]["action"] in valid_actions

        # Test blocked case
        result_blocked = analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "abnormal",
            },
        )
        assert result_blocked["decision_summary"]["action"] in valid_actions
        assert result_blocked["decision_summary"]["action"] == "stand_aside"


# ======================================================================
# Tests trực tiếp check_trade_gates() với dữ liệu giống thật
# ======================================================================


class TestTradeGateDirectRealistic:
    """Unit tests: check_trade_gates() với context giống thật."""

    def test_normal_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "high_impact_event_within_30m": False,
            "m15_quality": "strict",
            "expected_effective_rr": 1.8,
        })
        assert result["allowed"] is True
        assert result["decision_cap"] is None
        assert result["block_codes"] == []
        assert result["warning_codes"] == []

    def test_spread_abnormal_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "abnormal",
            "m15_quality": "strict",
        })
        assert result["allowed"] is False
        assert result["decision_cap"] == "TRADE_BLOCKED"
        assert "SPREAD_ABNORMAL" in result["block_codes"]
        assert len(result["reasons"]) >= 1

    def test_m15_none_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "m15_quality": "none",
            "expected_effective_rr": 1.6,
        })
        assert result["allowed"] is True
        assert result["decision_cap"] == "WATCH_ONLY"
        assert "M15_NOT_CONFIRMED" in result["warning_codes"]
        assert len(result["reasons"]) >= 1

    def test_m15_loose_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "m15_quality": "loose",
            "expected_effective_rr": 2.0,
        })
        assert result["allowed"] is True
        assert result["decision_cap"] == "WAITING_CONFIRMATION"
        assert "M15_LOOSE_CONFIRMATION" in result["warning_codes"]

    def test_high_impact_news_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "high_impact_event_within_30m": True,
            "m15_quality": "strict",
        })
        assert result["allowed"] is False
        assert result["decision_cap"] == "TRADE_BLOCKED"
        assert "HIGH_IMPACT_NEWS_NEARBY" in result["block_codes"]

    def test_empty_context_neutral(self) -> None:
        """Thiếu tất cả key -> neutral, không block nhầm."""
        result = check_trade_gates({})
        assert result["allowed"] is True
        assert result["decision_cap"] is None
        assert result["block_codes"] == []
        assert result["warning_codes"] == []
        assert result["reasons"] == []

    def test_reasons_are_strings_not_none(self) -> None:
        """reasons luôn là list string, không chứa None."""
        result = check_trade_gates({
            "terminal_connected": False,
            "spread_status": "abnormal",
        })
        assert all(isinstance(r, str) for r in result["reasons"])
        assert len(result["reasons"]) >= 1

    def test_block_and_warning_together_block_wins(self) -> None:
        """Vừa có block vừa có warning -> block thắng."""
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "abnormal",  # block
            "m15_quality": "loose",  # warning
        })
        assert result["allowed"] is False
        assert result["decision_cap"] == "TRADE_BLOCKED"
        assert "SPREAD_ABNORMAL" in result["block_codes"]
        assert "M15_LOOSE_CONFIRMATION" in result["warning_codes"]

    def test_daily_loss_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "daily_loss_limit_reached": True,
        })
        assert result["allowed"] is False
        assert result["decision_cap"] == "TRADE_BLOCKED"
        assert "DAILY_LOSS_LIMIT_REACHED" in result["block_codes"]

    def test_weekly_loss_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "weekly_loss_limit_reached": True,
        })
        assert result["allowed"] is False
        assert result["decision_cap"] == "TRADE_BLOCKED"
        assert "WEEKLY_LOSS_LIMIT_REACHED" in result["block_codes"]

    def test_expected_rr_low_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "m15_quality": "strict",
            "expected_effective_rr": 1.1,
        })
        assert result["allowed"] is True
        assert result["decision_cap"] == "WATCH_ONLY"
        assert "EXPECTED_RR_TOO_LOW" in result["warning_codes"]

    def test_score_gap_low_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "m15_quality": "strict",
            "score_gap": 5,
        })
        assert result["allowed"] is True
        assert result["decision_cap"] == "WAITING_CONFIRMATION"
        assert "BUY_SELL_SCORE_GAP_LOW" in result["warning_codes"]

    def test_zone_broken_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "zone_broken": True,
        })
        assert result["allowed"] is True
        assert result["decision_cap"] == "WATCH_ONLY"
        assert "ZONE_BROKEN" in result["warning_codes"]

    def test_data_quality_warning_context(self) -> None:
        result = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "data_quality_warning": "MT5 data delayed",
        })
        assert result["allowed"] is False
        assert result["decision_cap"] == "TRADE_BLOCKED"
        assert "DATA_QUALITY_WARNING" in result["block_codes"]

    def test_min_expected_rr_customizable(self) -> None:
        """Có thể tùy chỉnh min_expected_effective_rr qua context."""
        # Default 1.3: 1.4 >= 1.3 -> pass
        result_pass = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "expected_effective_rr": 1.4,
        })
        assert "EXPECTED_RR_TOO_LOW" not in result_pass["warning_codes"]

        # Custom 1.5: 1.4 < 1.5 -> fail
        result_fail = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "expected_effective_rr": 1.4,
            "min_expected_effective_rr": 1.5,
        })
        assert "EXPECTED_RR_TOO_LOW" in result_fail["warning_codes"]

    def test_min_score_gap_customizable(self) -> None:
        """Có thể tùy chỉnh min_buy_sell_score_gap qua context."""
        # Default 10: 12 >= 10 -> pass
        result_pass = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "score_gap": 12,
        })
        assert "BUY_SELL_SCORE_GAP_LOW" not in result_pass["warning_codes"]

        # Custom 15: 12 < 15 -> fail
        result_fail = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "score_gap": 12,
            "min_buy_sell_score_gap": 15,
        })
        assert "BUY_SELL_SCORE_GAP_LOW" in result_fail["warning_codes"]

    def test_m15_strict_no_cap(self) -> None:
        """M15 strict hoặc thiếu m15_quality -> không cap."""
        result_strict = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "m15_quality": "strict",
        })
        assert result_strict["decision_cap"] is None
        assert "M15_NOT_CONFIRMED" not in result_strict["warning_codes"]
        assert "M15_LOOSE_CONFIRMATION" not in result_strict["warning_codes"]

        result_missing = check_trade_gates({
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        })
        assert result_missing["decision_cap"] is None
        assert "M15_NOT_CONFIRMED" not in result_missing["warning_codes"]
        assert "M15_LOOSE_CONFIRMATION" not in result_missing["warning_codes"]
