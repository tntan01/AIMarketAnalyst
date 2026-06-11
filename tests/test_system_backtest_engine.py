from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.market_models import Candle
from core.system_backtest_engine import (
    BacktestRequest,
    BacktestTrade,
    build_skip_debug,
    build_breakdowns,
    find_entry_fill,
    resolve_exit,
    run_system_backtest,
    summarize_backtest_trades,
    trade_open_block_reason,
)


def _series(count: int, start: datetime, step: timedelta, close: float = 1.1) -> list[Candle]:
    candles: list[Candle] = []
    for index in range(count):
        value = close
        candles.append(
            Candle(
                time=start + step * index,
                open=value,
                high=value + 0.002,
                low=value - 0.002,
                close=value,
                volume=100,
            )
        )
    return candles


def _request(start: datetime, end: datetime) -> BacktestRequest:
    return BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=start,
        end=end,
        initial_balance=10_000,
        risk_percent=1.0,
        mode="strict",
    )


def _analysis_payload(side: str = "buy", ready: bool = True) -> dict:
    action = "READY_TO_TRADE" if ready else "WATCH_ONLY"
    return {
        "symbol": "EUR/USD",
        "trade_permission": {"status": "allowed", "reason": "ok"},
        "trade_gate": {"allowed": True, "decision_cap": None, "reasons": [], "warning_codes": [], "block_codes": []},
        "decision_engine": {"decision": action, "reason": "ok", "legacy_action": "ready" if ready else "watch"},
        "decision_summary": {
            "action": "ready" if ready else "watch",
            "best_side": side,
            "best_scenario": side,
            "score_gap": 24,
        },
        "scenario_scores": {
            "buy": {"signal_score": 84, "total": 84},
            "sell": {"signal_score": 60, "total": 60},
        },
        "market_regime": {"primary": "trend_up"},
        "final_score": 82,
        "smc_trade_flags": {
            "selected_zone_score": 81,
            "selected_zone_type": "demand_zone",
            "liquidity_sweep_aligned": True,
            "displacement_aligned": True,
            "choch_against_direction": False,
        },
        "reason_codes": ["TEST_REASON"],
        "warning_codes": [],
        "block_codes": [],
        "scenarios": [
            {
                "type": side,
                "ready_to_trade": ready,
                "entry_status": "confirmed_entry" if ready else "watch_zone",
                "m15_quality": "strict" if ready else "none",
                "entry_zone": [1.098, 1.102],
                "stop_loss": 1.09,
                "take_profit": [1.12],
                "expected_effective_rr": 2.0,
            }
        ],
    }


def test_resolve_exit_uses_conservative_same_bar_rule() -> None:
    candle = Candle(
        time=datetime(2026, 1, 1, 1, tzinfo=timezone.utc),
        open=1.10,
        high=1.13,
        low=1.08,
        close=1.11,
    )

    exit_time, exit_price, outcome, bars = resolve_exit(
        side="buy",
        entry_price=1.10,
        stop_loss=1.09,
        take_profit=1.12,
        future_candles=[candle],
        max_holding_bars=5,
        conservative_same_bar=True,
    )

    assert exit_time == candle.time.isoformat()
    assert exit_price == 1.09
    assert outcome == "loss"
    assert bars == 1


def test_find_entry_fill_waits_for_m15_zone_touch_and_applies_costs() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    request = _request(base, base + timedelta(hours=2))
    request = replace(request, spread_price=0.0002, slippage_price=0.0001)
    candles = [
        Candle(base + timedelta(minutes=15), 1.11, 1.112, 1.108, 1.109),
        Candle(base + timedelta(minutes=30), 1.105, 1.106, 1.101, 1.102),
    ]

    fill = find_entry_fill(
        side="buy",
        scenario={"entry_zone": [1.098, 1.102]},
        future_candles=candles,
        setup_expiry_bars=12,
        request=request,
    )

    assert fill is not None
    candle, entry_price, index = fill
    assert candle.time == candles[1].time
    assert round(entry_price, 5) == 1.1023
    assert index == 1


def test_find_entry_fill_returns_none_when_zone_is_not_touched_before_expiry() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    request = _request(base, base + timedelta(hours=2))
    candles = [
        Candle(base + timedelta(minutes=15), 1.11, 1.112, 1.108, 1.109),
        Candle(base + timedelta(minutes=30), 1.107, 1.108, 1.105, 1.106),
    ]

    fill = find_entry_fill(
        side="buy",
        scenario={"entry_zone": [1.098, 1.102]},
        future_candles=candles,
        setup_expiry_bars=2,
        request=request,
    )

    assert fill is None


def test_summarize_backtest_trades_reports_core_metrics() -> None:
    trades = [
        BacktestTrade("EUR/USD", "buy", "READY_TO_TRADE", "t1", "t2", 1, 0.9, 1.2, 1.2, "win", 2.0, 1, 80, 80, 80, 60, 20, "trend_up", "confirmed_entry", "strict", 2, 80, "demand", 80, "demand", True, True, False),
        BacktestTrade("EUR/USD", "buy", "READY_TO_TRADE", "t3", "t4", 1, 0.9, 1.2, 0.9, "loss", -1.0, 1, 80, 80, 80, 60, 20, "trend_up", "confirmed_entry", "strict", 2, 80, "demand", 80, "demand", True, True, False),
        BacktestTrade("EUR/USD", "buy", "READY_TO_TRADE", "t5", "t6", 1, 0.9, 1.2, 1.0, "expired", 0.0, 2, 80, 80, 80, 60, 20, "range", "confirmed_entry", "strict", 2, 40, "demand", None, "technical", False, True, False),
    ]

    summary = summarize_backtest_trades(trades)

    assert summary["total_trades"] == 3
    assert summary["wins"] == 1
    assert summary["losses"] == 1
    assert summary["expired"] == 1
    assert summary["expectancy_r"] == 0.3333
    assert summary["profit_factor"] == 2.0
    assert summary["max_consecutive_losses"] == 1


def test_build_breakdowns_groups_by_m15_and_smc_zone_score() -> None:
    trades = [
        BacktestTrade("EUR/USD", "buy", "READY_TO_TRADE", "t1", "t2", 1, 0.9, 1.2, 1.2, "win", 2.0, 1, 80, 80, 80, 60, 20, "trend_up", "confirmed_entry", "strict", 2, 80, "demand", 80, "demand", True, True, False),
        BacktestTrade("EUR/USD", "sell", "READY_TO_TRADE", "t3", "t4", 1, 1.1, 0.8, 1.1, "loss", -1.0, 1, 70, 70, 55, 70, 15, "range", "confirmed_entry", "loose", 1.2, 50, "supply", None, "technical", False, False, True),
    ]

    breakdowns = build_breakdowns(trades)

    assert breakdowns["by_m15_quality"]["strict"]["total_trades"] == 1
    assert breakdowns["by_m15_quality"]["loose"]["total_trades"] == 1
    assert breakdowns["by_smc_zone_score"][">=75"]["total_trades"] == 1
    assert breakdowns["by_smc_zone_score"]["<55"]["total_trades"] == 1


def test_build_skip_debug_includes_quantitative_fields() -> None:
    analysis = _analysis_payload(ready=False)
    scenario = analysis["scenarios"][0]

    debug = build_skip_debug(analysis, scenario)

    assert debug["decision"] == "WATCH_ONLY"
    assert debug["legacy_action"] == "watch"
    assert debug["final_score"] == 82
    assert debug["signal_score"] == 84
    assert debug["buy_score"] == 84
    assert debug["sell_score"] == 60
    assert debug["score_gap"] == 24
    assert debug["entry_status"] == "watch_zone"
    assert debug["m15_quality"] == "none"
    assert debug["gate_cap"] is None
    assert debug["expected_effective_rr"] == 2.0
    assert debug["selected_zone_score"] == 81
    assert debug["liquidity_sweep_aligned"] is True


def test_balanced_mode_requires_confirmed_entry_strict_m15_and_does_not_allow_watch_only() -> None:
    analysis = _analysis_payload(ready=True)
    scenario = analysis["scenarios"][0]
    analysis["decision_engine"]["decision"] = "WAITING_CONFIRMATION"
    analysis["trade_permission"]["status"] = "caution"
    scenario["ready_to_trade"] = False
    scenario["entry_status"] = "waiting_confirmation"
    scenario["m15_quality"] = "loose"

    assert trade_open_block_reason(analysis, scenario, "balanced") == "blocked_by_entry_status"

    scenario["entry_status"] = "confirmed_entry"
    assert trade_open_block_reason(analysis, scenario, "balanced") == "blocked_by_m15"
    scenario["m15_quality"] = "strict"
    assert trade_open_block_reason(analysis, scenario, "balanced") is None
    assert trade_open_block_reason(analysis, scenario, "strict") == "blocked_by_permission"

    analysis["decision_engine"]["decision"] = "WATCH_ONLY"
    assert trade_open_block_reason(analysis, scenario, "balanced") == "blocked_by_decision"


def test_balanced_mode_blocks_low_score_or_low_rr() -> None:
    analysis = _analysis_payload(ready=True)
    scenario = analysis["scenarios"][0]
    analysis["decision_engine"]["decision"] = "WAITING_CONFIRMATION"
    scenario["entry_status"] = "confirmed_entry"
    scenario["m15_quality"] = "strict"

    analysis["final_score"] = 67
    assert trade_open_block_reason(analysis, scenario, "balanced") == "blocked_by_score"

    analysis["final_score"] = 68
    analysis["scenario_scores"]["buy"]["signal_score"] = 64
    assert trade_open_block_reason(analysis, scenario, "balanced") == "blocked_by_score"

    analysis["scenario_scores"]["buy"]["signal_score"] = 65
    scenario["expected_effective_rr"] = 1.19
    assert trade_open_block_reason(analysis, scenario, "balanced") == "blocked_by_rr"


def test_run_system_backtest_replays_without_future_leak_and_opens_ready_trades() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d1 = _series(80, base - timedelta(days=79), timedelta(days=1))
    h4 = _series(120, base - timedelta(hours=4 * 119), timedelta(hours=4))
    h1 = _series(100, base - timedelta(hours=99), timedelta(hours=1), close=1.10)
    start = h1[80].time
    end = h1[85].time
    signal_times = {h1[80].time, h1[82].time}
    m15 = _series(500, h1[0].time, timedelta(minutes=15), close=1.10)
    for idx, candle in enumerate(m15):
        if candle.time == h1[80].time + timedelta(minutes=15):
            # close=1.105 > zone_low(1.098) → fills; high=1.121 >= TP(1.12) → win
            m15[idx] = Candle(candle.time, 1.10, 1.121, 1.099, 1.105)
        if candle.time == h1[82].time + timedelta(minutes=15):
            # close=1.099 > zone_low(1.098) → fills; low=1.088 < SL(1.09) → loss
            m15[idx] = Candle(candle.time, 1.10, 1.102, 1.088, 1.099)

    def fake_analyze(request, candles_by_timeframe, **kwargs):
        current = candles_by_timeframe["H1"][-1].time
        for rows in candles_by_timeframe.values():
            assert all(candle.time <= current for candle in rows)
        m15_rows = kwargs.get("m15_candles") or []
        assert all(candle.time <= current for candle in m15_rows)
        return _analysis_payload(ready=current in signal_times)

    result = run_system_backtest(
        _request(start, end),
        {"D1": d1, "H4": h4, "H1": h1, "M15": m15},
        analysis_fn=fake_analyze,
    )

    assert result.summary["total_trades"] == 2
    assert result.summary["wins"] == 1
    assert result.summary["losses"] == 1
    assert result.diagnostics["snapshots_evaluated"] >= 2
    assert result.diagnostics["gate_funnel"]["trade_opened"] == 2
    assert result.diagnostics["gate_funnel"]["setup_detected"] >= 2
    assert result.diagnostics["account_guard"]["enabled"] is False
    assert result.diagnostics["account_guard"]["max_consecutive_losses"] == 999
    assert result.trades[0].result == "win"
    assert result.trades[1].result == "loss"
    assert result.breakdowns["by_decision"]["READY_TO_TRADE"]["total_trades"] == 2


def test_run_system_backtest_skipped_setups_include_debug_payload() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d1 = _series(80, base - timedelta(days=79), timedelta(days=1))
    h4 = _series(120, base - timedelta(hours=4 * 119), timedelta(hours=4))
    h1 = _series(100, base - timedelta(hours=99), timedelta(hours=1), close=1.10)
    start = h1[80].time
    end = h1[81].time
    m15 = _series(500, h1[0].time, timedelta(minutes=15), close=1.10)

    result = run_system_backtest(
        _request(start, end),
        {"D1": d1, "H4": h4, "H1": h1, "M15": m15},
        analysis_fn=lambda *args, **kwargs: _analysis_payload(ready=False),
    )

    skipped = result.skipped_setups[0]
    assert skipped["reason"] == "not_actionable"
    assert skipped["debug"]["decision"] == "WATCH_ONLY"
    assert skipped["debug"]["final_score"] == 82
    assert skipped["debug"]["entry_status"] == "watch_zone"
    assert skipped["debug"]["m15_quality"] == "none"
    assert result.diagnostics["gate_funnel"]["blocked_by_decision"] >= 1


def test_run_system_backtest_requires_warmup_and_records_skips() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    request = _request(base, base + timedelta(hours=3))
    result = run_system_backtest(
        request,
        {
            "D1": _series(10, base, timedelta(days=1)),
            "H4": _series(10, base, timedelta(hours=4)),
            "H1": _series(10, base, timedelta(hours=1)),
        },
        analysis_fn=lambda *args, **kwargs: _analysis_payload(),
    )

    assert result.summary["total_trades"] == 0
    assert any(item["reason"] == "insufficient_warmup" for item in result.skipped_setups)


def test_backtest_mode_blocks_watch_only_but_accepts_loose_m15_and_watch_zone() -> None:
    analysis = _analysis_payload(ready=True)
    scenario = analysis["scenarios"][0]
    analysis["decision_engine"]["decision"] = "WATCH_ONLY"
    analysis["trade_permission"]["status"] = "caution"
    scenario["ready_to_trade"] = False
    scenario["entry_status"] = "watch_zone"
    scenario["m15_quality"] = "none"

    assert trade_open_block_reason(analysis, scenario, "backtest") == "blocked_by_decision"

    analysis["decision_engine"]["decision"] = "WAITING_CONFIRMATION"
    scenario["m15_quality"] = "loose"
    assert trade_open_block_reason(analysis, scenario, "backtest") is None

    scenario["entry_status"] = "waiting_confirmation"
    assert trade_open_block_reason(analysis, scenario, "backtest") is None

    analysis["decision_engine"]["decision"] = "AGGRESSIVE_SETUP"
    assert trade_open_block_reason(analysis, scenario, "backtest") is None

    analysis["trade_permission"]["status"] = "allowed"
    assert trade_open_block_reason(analysis, scenario, "backtest") is None

    # Should block invalid states
    analysis["trade_permission"]["status"] = "denied"
    assert trade_open_block_reason(analysis, scenario, "backtest") == "blocked_by_permission"

    analysis["trade_permission"]["status"] = "caution"
    analysis["decision_engine"]["decision"] = "STAND_ASIDE"
    assert trade_open_block_reason(analysis, scenario, "backtest") == "blocked_by_decision"

    analysis["decision_engine"]["decision"] = "READY_TO_TRADE"
    scenario["entry_status"] = "invalidated"
    assert trade_open_block_reason(analysis, scenario, "backtest") == "blocked_by_entry_status"

    # Gate blocked still blocks even in backtest mode
    analysis["trade_gate"]["allowed"] = False
    assert trade_open_block_reason(analysis, scenario, "backtest") == "blocked_by_trade_gate"


def test_backtest_disables_account_guard_history_by_default() -> None:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    d1 = _series(80, base - timedelta(days=79), timedelta(days=1))
    h4 = _series(120, base - timedelta(hours=4 * 119), timedelta(hours=4))
    h1 = _series(100, base - timedelta(hours=99), timedelta(hours=1), close=1.10)
    start = h1[80].time
    end = h1[83].time
    m15 = _series(500, h1[0].time, timedelta(minutes=15), close=1.10)
    seen_closed_counts: list[int] = []

    for idx, candle in enumerate(m15):
        if candle.time in {h1[80].time + timedelta(minutes=15), h1[82].time + timedelta(minutes=15)}:
            m15[idx] = Candle(candle.time, 1.10, 1.121, 1.099, 1.12)

    def fake_analyze(request, candles_by_timeframe, **kwargs):
        seen_closed_counts.append(len(kwargs.get("closed_trades") or []))
        return _analysis_payload(ready=True)

    run_system_backtest(
        _request(start, end),
        {"D1": d1, "H4": h4, "H1": h1, "M15": m15},
        analysis_fn=fake_analyze,
    )

    assert seen_closed_counts
    assert set(seen_closed_counts) == {0}
