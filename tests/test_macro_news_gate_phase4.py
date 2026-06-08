from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest import mock

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput
from core.trade_gate_engine import check_trade_gates


# ---------------------------------------------------------------------------
# Test 1 — Gate truc tiep: high_impact_event_within_30m = True -> block
# ---------------------------------------------------------------------------

def test_high_impact_nearby_gate_direct_block():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": True,
        "m15_quality": "strict",
        "score_gap": 30,
    }
    result = check_trade_gates(context)
    assert result["allowed"] is False
    assert result["decision_cap"] == "TRADE_BLOCKED"
    assert "HIGH_IMPACT_NEWS_NEARBY" in result["block_codes"]


# ---------------------------------------------------------------------------
# Test 2 — Gate truc tiep: khong co tin manh gan -> khong block boi news
# ---------------------------------------------------------------------------

def test_no_high_impact_nearby_no_news_block():
    context: dict = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
        "high_impact_event_within_30m": False,
        "m15_quality": "strict",
        "score_gap": 30,
    }
    result = check_trade_gates(context)
    assert "HIGH_IMPACT_NEWS_NEARBY" not in result["block_codes"]
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# Test 3 — analyze_symbol bi block khi high_impact_event_within_30m = True
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


def _base_candles() -> dict[str, list[Candle]]:
    return {
        "D1": _candles(240, 1.05, 0.0005, 0.002),
        "H4": _candles(240, 1.08, 0.00035, 0.0015),
        "H1": _candles(120, 1.12, 0.0002, 0.001),
    }


def _base_request() -> AnalysisInput:
    return AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)


def test_high_impact_news_nearby_blocks_analyze_symbol():
    """Du score co cao, neu high_impact_event_within_30m=True -> stand_aside."""
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


def test_no_high_impact_news_no_news_block_in_analyze_symbol():
    """Khong co tin manh gan -> gate khong block boi news."""
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

    assert "HIGH_IMPACT_NEWS_NEARBY" not in result["trade_gate"].get("block_codes", [])


# ---------------------------------------------------------------------------
# Test 4 — Gate context field duoc truyen dung tu data_quality
# ---------------------------------------------------------------------------

def test_high_impact_field_in_gate_context():
    """Kiem tra field high_impact_event_within_30m duoc truyen tu data_quality vao gate_context."""
    request = _base_request()

    with mock.patch("core.analysis_engine.check_trade_gates") as mock_gates:
        mock_gates.return_value = {
            "allowed": True,
            "decision_cap": None,
            "block_codes": [],
            "warning_codes": [],
            "reasons": [],
        }
        analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
                "high_impact_event_within_30m": True,
            },
        )
        call_context = mock_gates.call_args[0][0]
        assert call_context.get("high_impact_event_within_30m") is True


def test_high_impact_field_defaults_false():
    """Khi khong co field high_impact_event_within_30m, gate_context nhan False."""
    request = _base_request()

    with mock.patch("core.analysis_engine.check_trade_gates") as mock_gates:
        mock_gates.return_value = {
            "allowed": True,
            "decision_cap": None,
            "block_codes": [],
            "warning_codes": [],
            "reasons": [],
        }
        analyze_symbol(
            request,
            _base_candles(),
            data_quality={
                "terminal_connected": True,
                "broker_logged_in": True,
                "spread_status": "normal",
            },
        )
        call_context = mock_gates.call_args[0][0]
        assert call_context.get("high_impact_event_within_30m") is None
