"""Phase 18 — verify that use_decision_engine_action=True makes
decision_summary["action"] use decision_engine["legacy_action"].

Tests call analyze_symbol directly with realistic candle data to
confirm the opt-in flag works end-to-end without touching controllers.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.market_models import Candle
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candles(count: int, start: float, step: float, amplitude: float) -> list[Candle]:
    """Build realistic trending candles with mild oscillation."""
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[Candle] = []
    for index in range(count):
        wave = amplitude * ((index % 10) - 5) / 5
        close = start + index * step + wave
        open_price = close - step * 0.2
        rows.append(Candle(
            time=base_time + timedelta(hours=index),
            open=open_price,
            high=max(open_price, close) + amplitude * 0.8,
            low=min(open_price, close) - amplitude * 0.8,
            close=close,
            volume=100,
        ))
    return rows


def _base_kwargs():
    return {
        "macro_alignment": {"buy": 15, "sell": 15},
        "macro_confidence": 1.0,
    }


def _make_request():
    return AnalysisInput("EUR/USD", "EURUSD", 10_000, 1, contract_size_override=100_000)


def _make_candles():
    return {
        "D1": _candles(240, 1.05, 0.0005, 0.002),
        "H4": _candles(240, 1.08, 0.00035, 0.0015),
        "H1": _candles(120, 1.12, 0.0002, 0.001),
    }


# ---------------------------------------------------------------------------
# Scenario 1 — normal spread, gate allowed
# ---------------------------------------------------------------------------


def test_opt_in_true_action_matches_decision_engine_legacy_action():
    """With use_decision_engine_action=True and normal conditions,
    decision_summary['action'] must equal decision_engine['legacy_action']."""
    request = _make_request()
    result = analyze_symbol(
        request,
        _make_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        **_base_kwargs(),
        use_decision_engine_action=True,
    )

    ds = result["decision_summary"]
    de = result["decision_engine"]

    # Opt-in flag reflected
    assert ds["decision_engine_enabled"] is True, (
        f"Expected decision_engine_enabled=True, got {ds['decision_engine_enabled']}"
    )
    # decision_engine_decision matches the engine's output
    assert ds["decision_engine_decision"] == de["decision"], (
        f"decision_engine_decision={ds['decision_engine_decision']} "
        f"!= decision_engine.decision={de['decision']}"
    )
    # action is the legacy_action from decision engine
    assert ds["action"] == de["legacy_action"], (
        f"action={ds['action']} != legacy_action={de['legacy_action']}. "
        f"With opt-in, action must come from decision engine."
    )
    # legacy_action must be a valid string
    assert de["legacy_action"] in ("ready", "watch", "wait_for_confirmation", "stand_aside"), (
        f"Unexpected legacy_action: {de['legacy_action']}"
    )


def test_opt_in_false_keeps_legacy_action():
    """With use_decision_engine_action=False (default), action stays legacy
    but decision_engine metadata is still present."""
    request = _make_request()
    result = analyze_symbol(
        request,
        _make_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
        },
        **_base_kwargs(),
        use_decision_engine_action=False,
    )

    ds = result["decision_summary"]
    de = result["decision_engine"]

    # Flag reflected as disabled
    assert ds["decision_engine_enabled"] is False, (
        f"Expected decision_engine_enabled=False, got {ds['decision_engine_enabled']}"
    )
    # decision_engine metadata still present
    assert isinstance(de, dict), "decision_engine must be a dict"
    assert "decision" in de, "decision_engine must have 'decision'"
    assert "legacy_action" in de, "decision_engine must have 'legacy_action'"
    # decision_engine_decision still recorded
    assert ds["decision_engine_decision"] == de["decision"], (
        f"decision_engine_decision={ds['decision_engine_decision']} "
        f"!= decision_engine.decision={de['decision']}"
    )
    # action is legacy (may or may not equal decision engine's legacy_action)
    assert ds["action"] in (
        "stand_aside", "watch", "wait_for_confirmation", "ready"
    ), f"Unexpected legacy action: {ds['action']}"


# ---------------------------------------------------------------------------
# Scenario 2 — gate blocked (spread abnormal / MT5 disconnected)
# ---------------------------------------------------------------------------


def test_opt_in_true_gate_blocked_still_wins():
    """Even with use_decision_engine_action=True, a blocked gate must
    produce TRADE_BLOCKED decision and legacy_action='stand_aside'."""
    request = _make_request()
    result = analyze_symbol(
        request,
        _make_candles(),
        data_quality={
            "terminal_connected": False,   # triggers gate block
            "broker_logged_in": False,
            "spread_status": "abnormal",
        },
        **_base_kwargs(),
        use_decision_engine_action=True,
    )

    ds = result["decision_summary"]
    de = result["decision_engine"]

    # Gate blocked → decision must be TRADE_BLOCKED
    assert de["decision"] == "TRADE_BLOCKED", (
        f"Expected TRADE_BLOCKED, got {de['decision']}"
    )
    # legacy_action must be stand_aside for blocked trades
    assert de["legacy_action"] == "stand_aside", (
        f"Expected legacy_action='stand_aside', got {de['legacy_action']}"
    )
    # action must come from decision engine
    assert ds["action"] == de["legacy_action"], (
        f"action={ds['action']} != legacy_action={de['legacy_action']}"
    )
    # action = stand_aside
    assert ds["action"] == "stand_aside", (
        f"Blocked gate must produce action='stand_aside', got {ds['action']}"
    )
    # flag is enabled
    assert ds["decision_engine_enabled"] is True


def test_opt_in_false_gate_blocked_also_blocked():
    """Without opt-in, a blocked gate still blocks via legacy action path."""
    request = _make_request()
    result = analyze_symbol(
        request,
        _make_candles(),
        data_quality={
            "terminal_connected": False,
            "broker_logged_in": False,
            "spread_status": "abnormal",
        },
        **_base_kwargs(),
        use_decision_engine_action=False,
    )

    ds = result["decision_summary"]
    de = result["decision_engine"]

    # Gate blocked → decision engine says TRADE_BLOCKED
    assert de["decision"] == "TRADE_BLOCKED", (
        f"Expected TRADE_BLOCKED, got {de['decision']}"
    )
    # Legacy action path: gate cap TRADE_BLOCKED → decision_action = stand_aside (line 188)
    # So legacy action should be stand_aside even without opt-in
    assert ds["action"] == "stand_aside", (
        f"Blocked gate must produce action='stand_aside', got {ds['action']}"
    )
    assert ds["decision_engine_enabled"] is False


# ---------------------------------------------------------------------------
# Scenario 3 — high_impact_event_within_30m
# ---------------------------------------------------------------------------


def test_opt_in_true_high_impact_news_within_30m_blocked():
    """High impact news in 30 min must trigger TRADE_BLOCKED via gate."""
    request = _make_request()
    result = analyze_symbol(
        request,
        _make_candles(),
        data_quality={
            "terminal_connected": True,
            "broker_logged_in": True,
            "spread_status": "normal",
            "high_impact_event_within_30m": True,
        },
        **_base_kwargs(),
        use_decision_engine_action=True,
    )

    de = result["decision_engine"]
    ds = result["decision_summary"]

    assert de["decision"] == "TRADE_BLOCKED", (
        f"Expected TRADE_BLOCKED with high_impact_event_within_30m, got {de['decision']}"
    )
    assert ds["action"] == "stand_aside"
    assert ds["action"] == de["legacy_action"]


# ---------------------------------------------------------------------------
# Sanity — trade_permission is unaffected by the flag
# ---------------------------------------------------------------------------


def test_trade_permission_identical_regardless_of_opt_in():
    """trade_permission status must be the same regardless of the flag."""
    request = _make_request()
    candles = _make_candles()
    dq = {
        "terminal_connected": True,
        "broker_logged_in": True,
        "spread_status": "normal",
    }

    result_off = analyze_symbol(
        request, candles, data_quality=dq, **_base_kwargs(),
        use_decision_engine_action=False,
    )
    result_on = analyze_symbol(
        request, candles, data_quality=dq, **_base_kwargs(),
        use_decision_engine_action=True,
    )

    assert result_off["trade_permission"]["status"] == result_on["trade_permission"]["status"], (
        f"trade_permission must be identical: "
        f"off={result_off['trade_permission']['status']}, "
        f"on={result_on['trade_permission']['status']}"
    )
