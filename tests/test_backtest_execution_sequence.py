from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest_contract import (
    BACKTEST_PURPOSE_VALIDATION,
)
from core.backtest_execution import (
    SAME_BAR_STOP_FIRST,
    SAME_BAR_TARGET_FIRST,
    find_confirmation_close_fill,
    resolve_post_fill_exit,
)
from core.backtest_market_data import prepare_backtest_data
from core.market_models import Candle
from core.system_backtest_engine import (
    BacktestRequest,
    build_fallback_scenario,
    select_trade_scenario,
    simulate_trade_from_analysis,
    validate_backtest_input,
)


UTC = timezone.utc


def _candle(
    minute: int,
    *,
    open_price: float = 1.10,
    high: float = 1.15,
    low: float = 1.05,
    close: float = 1.10,
) -> Candle:
    return Candle(
        time=datetime(2026, 1, 5, 10, minute, tzinfo=UTC),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _request(**overrides) -> BacktestRequest:
    values = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "start": datetime(2026, 1, 5, tzinfo=UTC),
        "end": datetime(2026, 1, 6, tzinfo=UTC),
        "initial_balance": 10_000.0,
        "risk_percent": 1.0,
        "setup_expiry_minutes": 60,
        "max_holding_minutes": 60,
    }
    if overrides.get("purpose") == BACKTEST_PURPOSE_VALIDATION:
        values.update({
            "execution_mode": "EXECUTION_PARITY",
            "cost_model_configured": True,
        })
    values.update(overrides)
    return BacktestRequest(**values)


def _analysis() -> dict:
    return {
        "decision_engine": {"decision": "READY_TO_TRADE"},
        "scenario_scores": {
            "buy": {"signal_score": 70},
            "sell": {"signal_score": 30},
        },
        "decision_summary": {
            "best_side": "buy",
            "score_gap": 40,
        },
        "market_regime": {"primary": "range"},
        "final_score": 70,
    }


def _scenario(**overrides) -> dict:
    value = {
        "type": "buy",
        "entry_zone": [1.08, 1.12],
        "stop_loss": 1.00,
        "take_profit": [1.20],
        "entry_status": "confirmed_entry",
        "scenario_source": "pipeline",
    }
    value.update(overrides)
    return value


def test_fill_candle_high_low_never_resolves_exit() -> None:
    fill_candle = _candle(0, high=1.25, low=0.95, close=1.10)
    post_fill = _candle(15, high=1.15, low=1.05, close=1.11)

    trade = simulate_trade_from_analysis(
        request=_request(max_holding_minutes=15),
        analysis=_analysis(),
        scenario=_scenario(),
        entry_candle=fill_candle,
        future_candles=[fill_candle, post_fill],
        execution_timeframe="M15",
        signal_time=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )

    assert trade is not None
    assert trade.result == "expired"
    assert trade.holding_bars == 1
    assert trade.entry_time == "2026-01-05T10:15:00+00:00"
    assert trade.exit_time == "2026-01-05T10:30:00+00:00"
    assert [event["event"] for event in trade.execution_events] == [
        "SIGNAL_DETECTED",
        "SETUP_ACTIVATED",
        "ENTRY_CONFIRMED",
        "ENTRY_FILLED",
        "EXIT_FILLED",
    ]


@pytest.mark.parametrize(
    ("open_price", "expected_price", "expected_outcome", "expected_reason"),
    [
        (0.95, 0.95, "loss", "gap_through_stop"),
        (1.25, 1.25, "win", "gap_through_target"),
    ],
)
def test_buy_gap_exit_uses_next_open(
    open_price: float,
    expected_price: float,
    expected_outcome: str,
    expected_reason: str,
) -> None:
    fill_candle = _candle(0, close=1.10)
    gap_candle = _candle(
        15,
        open_price=open_price,
        high=max(open_price, 1.10),
        low=min(open_price, 1.10),
        close=open_price,
    )

    trade = simulate_trade_from_analysis(
        request=_request(),
        analysis=_analysis(),
        scenario=_scenario(),
        entry_candle=fill_candle,
        future_candles=[fill_candle, gap_candle],
        execution_timeframe="M15",
        signal_time=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )

    assert trade is not None
    assert trade.result == expected_outcome
    assert trade.exit_price == expected_price
    assert trade.execution_events[-1]["reason"] == expected_reason


@pytest.mark.parametrize(
    ("open_price", "expected_outcome", "expected_reason"),
    [
        (1.25, "loss", "gap_through_stop"),
        (0.95, "win", "gap_through_target"),
    ],
)
def test_sell_gap_exit_is_symmetric(
    open_price: float,
    expected_outcome: str,
    expected_reason: str,
) -> None:
    gap_candle = _candle(
        15,
        open_price=open_price,
        high=max(open_price, 1.10),
        low=min(open_price, 1.10),
        close=open_price,
    )

    resolution = resolve_post_fill_exit(
        side="sell",
        entry_price=1.10,
        stop_loss=1.20,
        take_profit=1.00,
        future_candles=[gap_candle],
        filled_at=datetime(2026, 1, 5, 10, 15, tzinfo=UTC),
        max_holding=timedelta(minutes=15),
        execution_timeframe="M15",
    )

    assert resolution.outcome == expected_outcome
    assert resolution.price == open_price
    assert resolution.reason == expected_reason


@pytest.mark.parametrize(
    ("policy", "outcome", "price", "reason"),
    [
        (SAME_BAR_STOP_FIRST, "loss", 1.00, "same_bar_stop_first"),
        (
            SAME_BAR_TARGET_FIRST,
            "win",
            1.20,
            "same_bar_target_first",
        ),
    ],
)
def test_same_bar_ambiguity_policy_is_explicit(
    policy: str,
    outcome: str,
    price: float,
    reason: str,
) -> None:
    candle = _candle(15, high=1.25, low=0.95, close=1.10)

    resolution = resolve_post_fill_exit(
        side="buy",
        entry_price=1.10,
        stop_loss=1.00,
        take_profit=1.20,
        future_candles=[candle],
        filled_at=datetime(2026, 1, 5, 10, 15, tzinfo=UTC),
        max_holding=timedelta(minutes=15),
        execution_timeframe="M15",
        same_bar_policy=policy,
    )

    assert resolution.outcome == outcome
    assert resolution.price == price
    assert resolution.reason == reason


def test_holding_duration_excludes_candle_after_expiry() -> None:
    late_target = _candle(30, high=1.25, low=1.05, close=1.20)

    resolution = resolve_post_fill_exit(
        side="buy",
        entry_price=1.10,
        stop_loss=1.00,
        take_profit=1.20,
        future_candles=[late_target],
        filled_at=datetime(2026, 1, 5, 10, 15, tzinfo=UTC),
        max_holding=timedelta(minutes=15),
        execution_timeframe="M15",
    )

    assert resolution.outcome == "open"
    assert resolution.reason == "no_post_fill_data"


def test_entry_gap_that_never_trades_in_zone_is_not_filled() -> None:
    gap_below_zone = _candle(
        0,
        open_price=1.05,
        high=1.06,
        low=1.03,
        close=1.05,
    )

    fill = find_confirmation_close_fill(
        side="buy",
        zone_low=1.08,
        zone_high=1.12,
        future_candles=[gap_below_zone],
        setup_active_time=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
        setup_expiry=timedelta(minutes=30),
        execution_timeframe="M15",
    )

    assert fill is None


def test_fill_beyond_target_is_rejected_as_invalid_geometry() -> None:
    fill_beyond_target = _candle(
        0,
        open_price=1.10,
        high=1.25,
        low=1.09,
        close=1.22,
    )

    trade = simulate_trade_from_analysis(
        request=_request(),
        analysis=_analysis(),
        scenario=_scenario(),
        entry_candle=fill_beyond_target,
        future_candles=[fill_beyond_target],
        execution_timeframe="M15",
        signal_time=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )

    assert trade is None


def test_exact_side_invariant_does_not_select_opposite_scenario() -> None:
    analysis = {
        "decision_summary": {"best_side": "buy"},
        "scenarios": [{"type": "sell", "entry_status": "confirmed_entry"}],
    }

    assert select_trade_scenario(analysis) is None


def test_synthetic_fallback_is_research_only() -> None:
    fallback = build_fallback_scenario(
        {
            "decision_summary": {"best_side": "buy"},
            "technical": {"atr_h4": 0.01},
        },
        _candle(0),
    )

    assert fallback is not None
    assert fallback["synthetic"] is True
    assert fallback["research_only"] is True
    assert fallback["scenario_source"] == "synthetic_fallback"


def test_validation_request_rejects_synthetic_trade() -> None:
    fallback = build_fallback_scenario(
        {
            "decision_summary": {"best_side": "buy"},
            "technical": {"atr_h4": 0.01},
        },
        _candle(0),
    )
    assert fallback is not None

    trade = simulate_trade_from_analysis(
        request=_request(purpose=BACKTEST_PURPOSE_VALIDATION),
        analysis=_analysis(),
        scenario=fallback,
        entry_candle=_candle(0),
        future_candles=[_candle(0), _candle(15)],
        execution_timeframe="M15",
        signal_time=datetime(2026, 1, 5, 10, 0, tzinfo=UTC),
    )

    assert trade is None


def test_validation_requires_configured_execution_timeframe() -> None:
    raw = {
        timeframe: [_candle(0)]
        for timeframe in ("D1", "H4", "H1")
    }
    normalized, manifest = prepare_backtest_data(raw)

    with pytest.raises(ValueError, match="EXECUTION_TIMEFRAME_MISSING"):
        validate_backtest_input(
            _request(purpose=BACKTEST_PURPOSE_VALIDATION),
            normalized,
            data_manifest=manifest,
        )


def test_validation_rejects_non_m15_execution_policy() -> None:
    raw = {
        timeframe: [_candle(0)]
        for timeframe in ("D1", "H4", "H1", "M15")
    }
    normalized, manifest = prepare_backtest_data(raw)

    with pytest.raises(
        ValueError,
        match="EXECUTION_TIMEFRAME_MUST_BE_M15",
    ):
        validate_backtest_input(
            _request(
                purpose=BACKTEST_PURPOSE_VALIDATION,
                execution_timeframe="H1",
            ),
            normalized,
            data_manifest=manifest,
        )


def test_validation_requires_stop_first_ambiguity_policy() -> None:
    raw = {
        timeframe: [_candle(0)]
        for timeframe in ("D1", "H4", "H1", "M15")
    }
    normalized, manifest = prepare_backtest_data(raw)

    with pytest.raises(
        ValueError,
        match="SAME_BAR_POLICY_MUST_BE_STOP_FIRST",
    ):
        validate_backtest_input(
            _request(
                purpose=BACKTEST_PURPOSE_VALIDATION,
                conservative_same_bar=False,
            ),
            normalized,
            data_manifest=manifest,
        )
