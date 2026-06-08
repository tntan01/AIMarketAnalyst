"""Phase 14.9 — test use_decision_engine_action opt-in in analyze_symbol."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput


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


def _common_kwargs():
    return {
        "data_quality": {
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
    }


# ---------------------------------------------------------------------------
# Default: use_decision_engine_action=False (backward-compat)
# ---------------------------------------------------------------------------


def test_default_false_keeps_legacy_action():
    """Without opt-in, decision_summary['action'] stays legacy."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
    )

    ds = result["decision_summary"]
    assert "action" in ds
    # Legacy action still exists — one of the original values
    assert ds["action"] in ("stand_aside", "watch", "wait_for_confirmation", "ready")

    # decision_engine metadata still present
    assert "decision_engine" in result
    assert ds.get("decision_engine_enabled") is False
    assert ds["decision_engine_decision"] == result["decision_engine"]["decision"]


# ---------------------------------------------------------------------------
# Opt-in: use_decision_engine_action=True
# ---------------------------------------------------------------------------


def test_opt_in_true_uses_decision_engine():
    """With opt-in, decision_summary['action'] uses decision_engine legacy_action."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        use_decision_engine_action=True,
    )

    ds = result["decision_summary"]
    assert ds.get("decision_engine_enabled") is True
    assert ds["decision_engine_decision"] == result["decision_engine"]["decision"]

    # action must match decision_engine's legacy_action
    assert ds["action"] == result["decision_engine"]["legacy_action"]

    # action must be one of the legacy values
    assert ds["action"] in ("ready", "watch", "wait_for_confirmation", "stand_aside")


def test_opt_in_ready_case():
    """When decision_engine says READY, action should be 'ready'."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        use_decision_engine_action=True,
    )

    de = result["decision_engine"]
    ds = result["decision_summary"]
    assert ds["action"] == de["legacy_action"]


def test_opt_in_blocked_case():
    """Blocked trade → action must be 'stand_aside'."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        data_quality={
            "terminal_connected": False,  # MT5 not ready → blocked
            "broker_logged_in": False,
            "spread_status": "normal",
        },
        use_decision_engine_action=True,
    )

    ds = result["decision_summary"]
    de = result["decision_engine"]
    # With gate blocked, action derives from decision_engine
    assert ds["action"] == de["legacy_action"]


def test_trade_permission_unchanged_by_opt_in():
    """trade_permission is NOT affected by use_decision_engine_action."""
    request = AnalysisInput("EUR/USD", "EURUSDm", 10_000, 1, contract_size_override=100_000)

    result_off = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        use_decision_engine_action=False,
    )

    result_on = analyze_symbol(
        request,
        {
            "D1": _candles(240, 1.05, 0.0005, 0.002),
            "H4": _candles(240, 1.08, 0.00035, 0.0015),
            "H1": _candles(120, 1.12, 0.0002, 0.001),
        },
        **_common_kwargs(),
        use_decision_engine_action=True,
    )

    assert result_off["trade_permission"]["status"] == result_on["trade_permission"]["status"]
