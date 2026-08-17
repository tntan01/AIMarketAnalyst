"""Regression tests for the account-guard loss-semantics fixes (B1/B2/B3).

B1: consecutive-loss streak must walk the *newest-first* order already given
    by ``list_closed_trades_for_account_guard`` (it was reversed, making the
    streak almost always 0).
B2: a losing trade whose ``result_pct``/``result_r`` are wiped (MT5 sync rows
    missing SL) must still count as a loss via ``result_amount``.
B3: daily/weekly loss must be expressed as % of account from ``result_amount``
    when a balance is provided, not as a sum of per-trade %-price moves.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.account_guard import (
    calculate_loss_stats,
    check_account_guard,
    DAILY_LOSS_LIMIT_REACHED,
    WEEKLY_LOSS_LIMIT_REACHED,
    MAX_CONSECUTIVE_LOSSES_REACHED,
)

TZ = "Asia/Ho_Chi_Minh"
NOW = datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc)  # Monday midday


def _trade(closed_at, result_pct=0.0, result_r=0.0, amount=None):
    trade = {
        "closed_at": closed_at.isoformat(),
        "result_pct": result_pct,
        "result_r": result_r,
    }
    if amount is not None:
        trade["result_amount"] = amount
    return trade


class TestConsecutiveLossesOrder:
    def test_streak_walks_newest_first_not_reversed(self):
        # list_closed_trades_for_account_guard returns newest-first.
        today_latest = _trade(NOW + timedelta(hours=1), -1.0, -1.0)
        today_older = _trade(NOW - timedelta(hours=1), -1.0, -1.0)
        yesterday_win = _trade(NOW - timedelta(days=1), 1.0, 1.0)
        trades = [today_latest, today_older, yesterday_win]
        stats = calculate_loss_stats(trades, now=NOW, timezone_name=TZ)
        # The two most recent trades (same day) are losses → streak 2.
        assert stats["consecutive_losses"] == 2

    def test_streak_breaks_at_first_non_loss_in_newest_first_order(self):
        win_newest = _trade(NOW, 1.0, 1.0)
        loss_older = _trade(NOW - timedelta(hours=1), -1.0, -1.0)
        stats = calculate_loss_stats([win_newest, loss_older], now=NOW, timezone_name=TZ)
        # Newest trade is a win → streak 0 (old loss does not count).
        assert stats["consecutive_losses"] == 0

    def test_only_today_closes_count_toward_streak(self):
        # A loss from yesterday must not extend today's streak.
        today = _trade(NOW, -1.0, -1.0)
        yesterday = _trade(NOW - timedelta(days=1), -1.0, -1.0)
        stats = calculate_loss_stats([today, yesterday], now=NOW, timezone_name=TZ)
        assert stats["consecutive_losses"] == 1


class TestLossDetectionUsesMoneyWhenPresent:
    def test_losing_trade_with_wiped_pct_and_r_still_counts_as_loss(self):
        # MT5-synced loser without SL has result_pct/result_r wiped to 0/None
        # but keeps negative result_amount.
        trades = [
            _trade(NOW, -1.0, -1.0),
            _trade(NOW - timedelta(hours=1), 0.0, 0.0, amount=-50.0),
        ]
        stats = calculate_loss_stats(trades, now=NOW, timezone_name=TZ)
        assert stats["consecutive_losses"] == 2

    def test_winning_trade_with_wiped_pct_breaks_streak(self):
        trades = [
            _trade(NOW, 0.0, 0.0, amount=30.0),   # win via money
            _trade(NOW - timedelta(hours=1), -1.0, -1.0),
        ]
        stats = calculate_loss_stats(trades, now=NOW, timezone_name=TZ)
        assert stats["consecutive_losses"] == 0

    def test_guard_blocks_on_money_only_losses(self):
        # Two actual money losers, each without pct/r but summed -300 on a
        # 1000 balance = -30% daily → exceeds the 2% daily cap.
        trades = [
            _trade(NOW, 0.0, 0.0, amount=-150.0),
            _trade(NOW - timedelta(hours=1), 0.0, 0.0, amount=-150.0),
        ]
        result = check_account_guard(
            closed_trades=trades,
            settings={
                "max_daily_loss_pct": 2.0,
                "max_weekly_loss_pct": 5.0,
                "max_consecutive_losses": 3,
                "trader_timezone": TZ,
            },
            action="open_new_trade",
            now=NOW,
            account_balance=1000.0,
        )
        assert result["allowed"] is False
        assert DAILY_LOSS_LIMIT_REACHED in result["block_codes"]


class TestDailyWeeklyAccountPercentage:
    def test_daily_loss_is_percent_of_account_when_balance_and_money_given(self):
        # Two -25 on a 1000 balance = -5% account (not -sum-of-price-moves).
        trades = [
            _trade(NOW, result_pct=-9.0, amount=-25.0),
            _trade(NOW - timedelta(hours=1), result_pct=-9.0, amount=-25.0),
        ]
        stats = calculate_loss_stats(
            trades, now=NOW, timezone_name=TZ, account_balance=1000.0
        )
        assert stats["daily_result_pct"] == -5.0
        assert stats["weekly_result_pct"] == -5.0

    def test_weekly_loss_aggregates_cross_days_and_is_account_percent(self):
        monday_loss = _trade(NOW, amount=-100.0)          # Monday
        wednesday_loss = _trade(NOW + timedelta(days=2), amount=-100.0)
        wednesday_dt = NOW + timedelta(days=2)
        stats = calculate_loss_stats(
            [wednesday_loss, monday_loss],
            now=wednesday_dt,
            timezone_name=TZ,
            account_balance=1000.0,
        )
        # -200 / 1000 = -20% account.
        assert stats["weekly_result_pct"] == -20.0

    def test_fallback_keeps_legacy_pct_semantics_without_balance(self):
        # Existing behaviour when no balance/amount is provided: keep summing
        # per-trade result_pct (so the pre-existing phase-4 tests still pass).
        trades = [
            _trade(NOW, result_pct=-1.0, result_r=-1.0),
            _trade(NOW - timedelta(hours=1), result_pct=-1.0, result_r=-1.0),
        ]
        stats = calculate_loss_stats(trades, now=NOW, timezone_name=TZ)
        assert stats["daily_result_pct"] == -2.0
        result = check_account_guard(
            closed_trades=trades,
            settings={
                "max_daily_loss_pct": 2.0,
                "max_weekly_loss_pct": 2.0,
                "max_consecutive_losses": 2,
                "trader_timezone": TZ,
            },
            action="open_new_trade",
            now=NOW,
        )
        assert DAILY_LOSS_LIMIT_REACHED in result["block_codes"]
        assert WEEKLY_LOSS_LIMIT_REACHED in result["block_codes"]
        assert MAX_CONSECUTIVE_LOSSES_REACHED in result["block_codes"]