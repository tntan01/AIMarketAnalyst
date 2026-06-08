from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.backtest_engine import ReplaySetup, replay_plan, simulate_replay, summarize_trades
from core.market_models import Candle


def _candles(rows: list[tuple[float, float, float, float]]) -> list[Candle]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [
        Candle(base + timedelta(hours=index), open_, high, low, close, 100)
        for index, (open_, high, low, close) in enumerate(rows)
    ]


def test_replay_plan_reports_win_rate_expectancy_mfe_mae_drawdown_and_sessions() -> None:
    scenario = {
        "type": "buy",
        "entry_zone": [1.0, 1.02],
        "stop_loss": 0.98,
        "take_profit": [1.08],
        "risk_reward": "1:3.0",
    }
    candles = _candles(
        [
            (1.04, 1.05, 1.03, 1.04),
            (1.03, 1.04, 1.00, 1.01),
            (1.01, 1.09, 1.00, 1.08),
            (1.09, 1.10, 1.08, 1.09),
            (1.09, 1.10, 1.08, 1.09),
            (1.09, 1.10, 1.08, 1.09),
            (1.09, 1.10, 1.08, 1.09),
            (1.09, 1.10, 1.08, 1.09),
            (1.09, 1.10, 1.08, 1.09),
            (1.04, 1.05, 1.00, 1.01),
            (1.01, 1.02, 0.97, 0.98),
        ]
    )

    replay = replay_plan("EUR/USD", scenario, candles)
    summary = replay["summary"]

    assert summary["trade_count"] == 2
    assert summary["win_rate"] == 50.0
    assert "expectancy_r" in summary
    assert "average_mfe_r" in summary
    assert "average_mae_r" in summary
    assert "max_drawdown_r" in summary
    assert replay["by_symbol"]["EUR/USD"]["trade_count"] == 2
    assert replay["by_session"]


def test_summarize_trades_handles_empty_input() -> None:
    summary = summarize_trades([])

    assert summary["trade_count"] == 0
    assert summary["win_rate"] == 0.0


def test_simulate_replay_applies_cooldown_after_exit_to_avoid_duplicate_zone_entries() -> None:
    setup = ReplaySetup(
        symbol="EUR/USD",
        side="buy",
        entry_zone=(1.0, 1.02),
        stop_loss=0.98,
        take_profit=1.08,
        risk_reward=3.0,
        cooldown_bars=5,
    )
    candles = _candles(
        [
            (1.01, 1.02, 1.00, 1.01),
            (1.01, 1.015, 0.97, 0.98),
            (1.01, 1.02, 1.00, 1.01),
            (1.01, 1.02, 1.00, 1.01),
            (1.01, 1.02, 1.00, 1.01),
            (1.01, 1.02, 1.00, 1.01),
            (1.01, 1.02, 1.00, 1.01),
            (1.01, 1.02, 1.00, 1.01),
            (1.01, 1.015, 0.97, 0.98),
        ]
    )

    trades = simulate_replay(setup, candles)

    assert len(trades) == 2
    assert trades[0]["entry_time"] == candles[0].time.isoformat()
    assert trades[1]["entry_time"] == candles[7].time.isoformat()
