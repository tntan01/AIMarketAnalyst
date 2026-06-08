"""Phase 16.6 — test account guard action-specific block: open_new_trade vs close_trade."""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.account_guard import check_account_guard
from core.reason_codes import DAILY_LOSS_LIMIT_REACHED


_NOW = datetime.fromisoformat("2026-06-04T12:00:00+07:00")


def _loss_trades(daily_loss_pct: float = -2.1) -> list[dict]:
    return [
        {
            "symbol": "EUR/USD",
            "direction": "buy",
            "result_pct": -1.1,
            "result_r": -1.0,
            "closed_at": "2026-06-04T09:00:00+07:00",
        },
        {
            "symbol": "GBP/JPY",
            "direction": "sell",
            "result_pct": -1.0,
            "result_r": -1.0,
            "closed_at": "2026-06-04T11:00:00+07:00",
        },
    ]


def _settings(max_daily: float = 2.0) -> dict:
    return {
        "max_daily_loss_pct": max_daily,
        "max_weekly_loss_pct": 5.0,
        "max_consecutive_losses": 3,
        "max_open_risk_pct": 3.0,
        "trader_timezone": "Asia/Ho_Chi_Minh",
    }


# ---------------------------------------------------------------------------
# open_new_trade — blocked when daily loss reached
# ---------------------------------------------------------------------------


def test_open_new_trade_blocked():
    result = check_account_guard(
        closed_trades=_loss_trades(),
        settings=_settings(),
        action="open_new_trade",
        now=_NOW,
    )
    assert result["blocked"] is True
    assert result["allowed"] is False
    assert DAILY_LOSS_LIMIT_REACHED in result["block_codes"]


# ---------------------------------------------------------------------------
# close_trade — not blocked even when daily loss reached
# ---------------------------------------------------------------------------


def test_close_trade_not_blocked():
    result = check_account_guard(
        closed_trades=_loss_trades(),
        settings=_settings(),
        action="close_trade",
    )
    assert result["blocked"] is False
    assert result["allowed"] is True
    # block_codes may still contain DAILY_LOSS_LIMIT_REACHED for awareness


# ---------------------------------------------------------------------------
# move_sl_to_breakeven — risk-reducing, not blocked
# ---------------------------------------------------------------------------


def test_move_sl_to_breakeven_not_blocked():
    result = check_account_guard(
        closed_trades=_loss_trades(),
        settings=_settings(),
        action="move_sl_to_breakeven",
    )
    assert result["blocked"] is False
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# move_sl_closer — risk-reducing, not blocked
# ---------------------------------------------------------------------------


def test_move_sl_closer_not_blocked():
    result = check_account_guard(
        closed_trades=_loss_trades(),
        settings=_settings(),
        action="move_sl_closer",
    )
    assert result["blocked"] is False
    assert result["allowed"] is True


# ---------------------------------------------------------------------------
# increase_position — risk-increasing, blocked
# ---------------------------------------------------------------------------


def test_increase_position_blocked():
    result = check_account_guard(
        closed_trades=_loss_trades(),
        settings=_settings(),
        action="increase_position",
        now=_NOW,
    )
    assert result["blocked"] is True


# ---------------------------------------------------------------------------
# No loss → no block
# ---------------------------------------------------------------------------


def test_no_loss_open_allowed():
    result = check_account_guard(
        closed_trades=[],
        settings=_settings(),
        action="open_new_trade",
    )
    assert result["blocked"] is False
    assert result["allowed"] is True
