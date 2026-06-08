"""Phase 16.7 — test revenge trade warning/confirmed in trade_mistake_detector."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.trade_mistake_detector import detect_trade_mistakes
from core.reason_codes import (
    MISTAKE_REVENGE_TRADE_WARNING,
    MISTAKE_REVENGE_TRADE_CONFIRMED,
)


# ---------------------------------------------------------------------------
# Case 1: Revenge warning due to short time after loss
# ---------------------------------------------------------------------------


def test_revenge_warning_time():
    previous = [
        {
            "symbol": "EUR/USD",
            "direction": "buy",
            "result_r": -1.0,
            "closed_at": "2026-06-04T09:00:00Z",
            "actual_lot": 0.10,
        }
    ]
    current = {
        "symbol": "EUR/USD",
        "direction": "sell",
        "opened_at": "2026-06-04T09:03:00Z",
        "actual_lot": 0.10,
        "planned_lot": 0.10,
    }
    result = detect_trade_mistakes(current, previous_trades=previous)
    assert (
        "revenge_trade_warning" in result["auto_mistake_tags"]
        or MISTAKE_REVENGE_TRADE_WARNING in result["warning_codes"]
    )


# ---------------------------------------------------------------------------
# Case 2: Revenge warning due to increased lot after loss
# ---------------------------------------------------------------------------


def test_revenge_warning_lot():
    previous = [
        {
            "symbol": "EUR/USD",
            "direction": "buy",
            "result_r": -1.0,
            "closed_at": "2026-06-04T09:00:00Z",
            "actual_lot": 0.10,
        }
    ]
    current = {
        "symbol": "EUR/USD",
        "direction": "sell",
        "opened_at": "2026-06-04T09:30:00Z",  # 30 min later — time alone won't trigger
        "actual_lot": 0.20,  # 2x lot
        "planned_lot": 0.10,
    }
    result = detect_trade_mistakes(current, previous_trades=previous)
    assert (
        "revenge_trade_warning" in result["auto_mistake_tags"]
        or MISTAKE_REVENGE_TRADE_WARNING in result["warning_codes"]
    )


# ---------------------------------------------------------------------------
# Case 3: Revenge confirmed (both time + lot)
# ---------------------------------------------------------------------------


def test_revenge_confirmed():
    previous = [
        {
            "symbol": "EUR/USD",
            "direction": "buy",
            "result_r": -1.0,
            "closed_at": "2026-06-04T09:00:00Z",
            "actual_lot": 0.10,
        }
    ]
    current = {
        "symbol": "EUR/USD",
        "direction": "sell",
        "opened_at": "2026-06-04T09:03:00Z",  # within 5 min
        "actual_lot": 0.20,  # 2x lot
        "planned_lot": 0.10,
    }
    result = detect_trade_mistakes(current, previous_trades=previous)
    assert (
        "revenge_trade_confirmed" in result["auto_mistake_tags"]
        or MISTAKE_REVENGE_TRADE_CONFIRMED in result["mistake_codes"]
    )


# ---------------------------------------------------------------------------
# Case 4: No revenge (win then trade)
# ---------------------------------------------------------------------------


def test_no_revenge_after_win():
    previous = [
        {
            "symbol": "EUR/USD",
            "direction": "buy",
            "result_r": 1.5,
            "closed_at": "2026-06-04T09:00:00Z",
            "actual_lot": 0.10,
        }
    ]
    current = {
        "symbol": "EUR/USD",
        "direction": "sell",
        "opened_at": "2026-06-04T09:03:00Z",
        "actual_lot": 0.20,
        "planned_lot": 0.10,
    }
    result = detect_trade_mistakes(current, previous_trades=previous)
    assert "revenge_trade_warning" not in result["auto_mistake_tags"]
    assert "revenge_trade_confirmed" not in result["auto_mistake_tags"]


# ---------------------------------------------------------------------------
# Case 5: No revenge (long gap, normal lot)
# ---------------------------------------------------------------------------


def test_no_revenge_long_gap():
    previous = [
        {
            "symbol": "EUR/USD",
            "direction": "buy",
            "result_r": -1.0,
            "closed_at": "2026-06-04T09:00:00Z",
            "actual_lot": 0.10,
        }
    ]
    current = {
        "symbol": "EUR/USD",
        "direction": "sell",
        "opened_at": "2026-06-04T15:00:00Z",  # 6 hours later
        "actual_lot": 0.10,
        "planned_lot": 0.10,
    }
    result = detect_trade_mistakes(current, previous_trades=previous)
    assert "revenge_trade_confirmed" not in result["auto_mistake_tags"]


# ---------------------------------------------------------------------------
# No duplicates
# ---------------------------------------------------------------------------


def test_no_duplicate_tags():
    previous = [
        {
            "symbol": "EUR/USD",
            "direction": "buy",
            "result_r": -1.0,
            "closed_at": "2026-06-04T09:00:00Z",
            "actual_lot": 0.10,
        }
    ]
    current = {
        "symbol": "EUR/USD",
        "direction": "sell",
        "opened_at": "2026-06-04T09:03:00Z",
        "actual_lot": 0.20,
        "planned_lot": 0.10,
    }
    result = detect_trade_mistakes(current, previous_trades=previous)
    tags = result["auto_mistake_tags"]
    assert len(tags) == len(set(tags)), f"Duplicate tags: {tags}"
    codes = result["mistake_codes"]
    assert len(codes) == len(set(codes)), f"Duplicate codes: {codes}"
