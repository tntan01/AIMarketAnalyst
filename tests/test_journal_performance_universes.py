"""Regression test for the performance-summary universe split (F2).

The headline ``win_rate`` / ``profit_factor`` / ``net_amount`` must share the SAME
money population (trades with a ``result_amount``). The R-sample metrics
(``expectancy_r``, ``total_r``, ``r_win_rate``) are reported separately and are
allowed to differ when some closed trades carry an amount but no SL (no ``result_r``).
"""

from __future__ import annotations

from services.journal_converters import build_performance_summary


def _trade(result_r, result_amount):
    return {
        "symbol": "EUR/USD",
        "direction": "buy",
        "selected_scenario": "buy",
        "result_r": result_r,
        "result_amount": result_amount,
        "closed_at": "2026-08-10T00:00:00Z",
    }


def test_headline_win_rate_uses_money_population_not_r_population():
    # 2 R-trades (1 win +2R, 1 loss -1R) + 8 amount-only trades (3 wins, 5 losses).
    trades = [
        _trade(-1.0, -50.0),   # R loss, amount loss
        _trade(2.0, 100.0),    # R win,  amount win
        _trade(None, 100.0),   # amount-only win  ×3
        _trade(None, 100.0),
        _trade(None, 100.0),
        _trade(None, -50.0),   # amount-only loss ×5
        _trade(None, -50.0),
        _trade(None, -50.0),
        _trade(None, -50.0),
        _trade(None, -50.0),
    ]
    summary = build_performance_summary(trades)["summary"]

    # Money population (10 trades): 4 wins, 6 losses.
    assert summary["closed_trades"] == 10
    assert summary["amount_trades"] == 10
    assert summary["win_count"] == 4
    assert summary["loss_count"] == 6
    assert summary["amount_win_rate"] == 40.0
    assert summary["win_rate"] == 40.0
    assert summary["net_amount"] == 100.0

    # R population (2 trades): 1 win, 1 loss — MUST differ from headline.
    assert summary["r_trades"] == 2
    assert summary["r_win_count"] == 1
    assert summary["r_loss_count"] == 1
    assert summary["r_win_rate"] == 50.0
    assert summary["expectancy_r"] == 0.5

    # Headline and R win rate differ — the old code silently flipped to 50%.
    assert summary["win_rate"] != summary["r_win_rate"]


def test_all_amount_only_trades_still_yield_win_rate():
    # No R anywhere: headline must still reflect the money population (no flip to 0).
    trades = [
        _trade(None, 100.0),
        _trade(None, -50.0),
        _trade(None, -50.0),
    ]
    summary = build_performance_summary(trades)["summary"]
    assert summary["r_trades"] == 0
    assert summary["amount_trades"] == 3
    assert summary["win_rate"] == 33.33
    assert summary["r_win_rate"] == 0.0


def test_group_performance_money_consistent():
    from services.journal_converters import group_performance

    grouped = group_performance(
        [_trade(None, 100.0), _trade(None, -50.0), _trade(None, -50.0)],
        "symbol",
    )
    assert grouped[0]["win_rate"] == 33.33
    assert grouped[0]["net_amount"] == 0.0