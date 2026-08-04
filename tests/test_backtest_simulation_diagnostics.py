from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.backtest_candidate_ledger import (
    CandidateLedgerEntry,
    build_candidate_ledger_entry,
)
from core.backtest_contract import BACKTEST_PURPOSE_VALIDATION
from core.backtest_execution_parity import EXECUTION_MODE_PARITY
from core.market_models import Candle
from core.system_backtest_engine import (
    ENTRY_ZONE_NOT_TOUCHED,
    INVALID_ENTRY_ZONE,
    INVALID_SIDE,
    INVALID_TRADE_GEOMETRY,
    MISSING_SL_TP,
    NO_VALID_TP1,
    QUOTE_CONVERSION_MISSING,
    SIMULATION_REJECTION_DETAIL_KEY,
    SIMULATION_REJECTION_REASON_KEY,
    VALIDATION_RESEARCH_ONLY_SCENARIO,
    BacktestRequest,
    simulate_trade_from_analysis,
    trade_plan_skip_reason,
)


UTC = timezone.utc
BASE_TIME = datetime(2026, 1, 5, 10, 0, tzinfo=UTC)


def _candle(
    minute: int,
    *,
    open_price: float = 1.10,
    high: float = 1.15,
    low: float = 1.05,
    close: float = 1.10,
) -> Candle:
    return Candle(
        time=BASE_TIME + timedelta(minutes=minute),
        open=open_price,
        high=high,
        low=low,
        close=close,
        volume=100.0,
    )


def _request(**overrides: object) -> BacktestRequest:
    values: dict[str, object] = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "start": BASE_TIME,
        "end": BASE_TIME + timedelta(days=1),
        "initial_balance": 10_000.0,
        "risk_percent": 1.0,
        "setup_expiry_minutes": 60,
        "max_holding_minutes": 60,
    }
    values.update(overrides)
    return BacktestRequest(**values)


def _analysis() -> dict:
    return {
        "decision_engine": {"decision": "READY_TO_TRADE"},
        "scenario_scores": {
            "buy": {"signal_score": 70},
            "sell": {"signal_score": 30},
        },
        "decision_summary": {"best_side": "buy", "score_gap": 40},
        "market_regime": {"primary": "range"},
        "final_score": 70,
    }


def _scenario(**overrides: object) -> dict:
    value: dict[str, object] = {
        "type": "buy",
        "entry_zone": [1.08, 1.12],
        "stop_loss": 1.00,
        "take_profit": [1.20],
        "entry_status": "confirmed_entry",
        "scenario_source": "pipeline",
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    ("backtest_request", "scenario", "candles", "expected_reason"),
    [
        (
            _request(),
            _scenario(type="hold"),
            [_candle(0)],
            INVALID_SIDE,
        ),
        (
            _request(purpose=BACKTEST_PURPOSE_VALIDATION),
            _scenario(research_only=True),
            [_candle(0)],
            VALIDATION_RESEARCH_ONLY_SCENARIO,
        ),
        (
            _request(),
            _scenario(stop_loss=None),
            [_candle(0)],
            MISSING_SL_TP,
        ),
        (
            _request(),
            _scenario(take_profit=[]),
            [_candle(0)],
            NO_VALID_TP1,
        ),
        (
            _request(),
            _scenario(entry_zone="invalid"),
            [_candle(0)],
            INVALID_ENTRY_ZONE,
        ),
        (
            _request(),
            _scenario(),
            [
                _candle(
                    0,
                    open_price=1.30,
                    high=1.31,
                    low=1.29,
                    close=1.30,
                )
            ],
            ENTRY_ZONE_NOT_TOUCHED,
        ),
        (
            _request(),
            _scenario(),
            [
                _candle(
                    0,
                    open_price=1.10,
                    high=1.25,
                    low=1.09,
                    close=1.22,
                )
            ],
            INVALID_TRADE_GEOMETRY,
        ),
        (
            _request(
                symbol="EUR/JPY",
                broker_symbol="EURJPY",
                account_currency="USD",
                execution_mode=EXECUTION_MODE_PARITY,
                cost_model_configured=True,
            ),
            _scenario(),
            [
                _candle(0),
                _candle(
                    15,
                    open_price=1.10,
                    high=1.25,
                    low=1.05,
                    close=1.20,
                ),
            ],
            QUOTE_CONVERSION_MISSING,
        ),
    ],
)
def test_simulation_rejection_returns_detailed_reason(
    backtest_request: BacktestRequest,
    scenario: dict,
    candles: list[Candle],
    expected_reason: str,
) -> None:
    diagnostics: dict[str, object] = {}

    trade = simulate_trade_from_analysis(
        request=backtest_request,
        analysis=_analysis(),
        scenario=scenario,
        entry_candle=candles[0],
        future_candles=candles,
        execution_timeframe="M15",
        signal_time=BASE_TIME,
        diagnostics=diagnostics,
    )

    assert trade is None
    assert diagnostics[SIMULATION_REJECTION_REASON_KEY] == expected_reason


def test_successful_simulation_clears_stale_rejection_reason() -> None:
    diagnostics = {
        SIMULATION_REJECTION_REASON_KEY: INVALID_SIDE,
        SIMULATION_REJECTION_DETAIL_KEY: {"stale": True},
    }
    candles = [
        _candle(0),
        _candle(
            15,
            open_price=1.10,
            high=1.25,
            low=1.05,
            close=1.20,
        ),
    ]

    trade = simulate_trade_from_analysis(
        request=_request(),
        analysis=_analysis(),
        scenario=_scenario(),
        entry_candle=candles[0],
        future_candles=candles,
        execution_timeframe="M15",
        signal_time=BASE_TIME,
        diagnostics=diagnostics,
    )

    assert trade is not None
    assert diagnostics == {}


def test_invalid_geometry_records_price_detail() -> None:
    diagnostics: dict[str, object] = {}

    trade = simulate_trade_from_analysis(
        request=_request(),
        analysis=_analysis(),
        scenario=_scenario(),
        entry_candle=_candle(0),
        future_candles=[
            _candle(
                0,
                open_price=1.10,
                high=1.25,
                low=1.09,
                close=1.22,
            )
        ],
        execution_timeframe="M15",
        signal_time=BASE_TIME,
        diagnostics=diagnostics,
    )

    assert trade is None
    assert diagnostics[SIMULATION_REJECTION_REASON_KEY] == INVALID_TRADE_GEOMETRY
    assert diagnostics[SIMULATION_REJECTION_DETAIL_KEY] == {
        "side": "buy",
        "raw_fill_price": 1.22,
        "execution_entry_price": 1.22,
        "stop_loss": 1.0,
        "take_profit": 1.2,
        "entry_spread": 0.0,
        "entry_slippage": 0.0,
        "parity_enabled": False,
        "filled_at": "2026-01-05T10:15:00+00:00",
    }


def test_quote_conversion_missing_records_rate_detail() -> None:
    diagnostics: dict[str, object] = {}

    trade = simulate_trade_from_analysis(
        request=_request(
            symbol="EUR/JPY",
            broker_symbol="EURJPY",
            account_currency="USD",
            execution_mode=EXECUTION_MODE_PARITY,
            cost_model_configured=True,
            quote_conversion_symbol="JPYUSD",
        ),
        analysis=_analysis(),
        scenario=_scenario(),
        entry_candle=_candle(0),
        future_candles=[
            _candle(0),
            _candle(
                15,
                open_price=1.10,
                high=1.25,
                low=1.05,
                close=1.20,
            ),
        ],
        execution_timeframe="M15",
        signal_time=BASE_TIME,
        diagnostics=diagnostics,
    )

    assert trade is None
    assert diagnostics[SIMULATION_REJECTION_REASON_KEY] == QUOTE_CONVERSION_MISSING
    assert diagnostics[SIMULATION_REJECTION_DETAIL_KEY] == {
        "quote_conversion_symbol": "JPYUSD",
        "quote_conversion_inverted": False,
        "entry_time": "2026-01-05T10:15:00+00:00",
        "exit_time": "2026-01-05T10:30:00+00:00",
        "quote_rate_entry_present": False,
        "quote_rate_exit_present": False,
    }


def test_candidate_ledger_serializes_simulation_rejection_reason() -> None:
    entry = CandidateLedgerEntry(
        candidate_id="candidate-rejected",
        symbol="EUR/USD",
        decision_time=BASE_TIME.isoformat(),
        side="buy",
        setup_score=70,
        setup_score_source="side_scores.buy.setup_score",
        signal_score=70,
        market_regime="range",
        expected_effective_rr=1.5,
        scenario_available=True,
        base_eligible=False,
        base_rejection_reason="TRADE_SIMULATION_REJECTED",
        simulation_rejection_reason=ENTRY_ZONE_NOT_TOUCHED,
        simulation_rejection_detail={"zone_low": 1.08},
    )

    assert (
        entry.to_dict()["simulation_rejection_reason"]
        == ENTRY_ZONE_NOT_TOUCHED
    )
    assert entry.to_dict()["simulation_rejection_detail"] == {"zone_low": 1.08}


def test_candidate_ledger_serializes_execution_metadata() -> None:
    entry = build_candidate_ledger_entry(
        symbol="EUR/USD",
        decision_time=BASE_TIME,
        analysis={
            **_analysis(),
            "decision_engine": {"decision": "WATCH_ONLY"},
        },
        scenario=_scenario(
            entry_zone_source="smc_selected",
            m15_quality="strict",
            entry_status="watch_zone",
            tp1_source="none",
        ),
        base_rejection_reason="TRADE_SIMULATION_REJECTED",
    )

    payload = entry.to_dict()

    assert payload["entry_zone_source"] == "smc_selected"
    assert payload["m15_quality"] == "strict"
    assert payload["entry_status"] == "watch_zone"
    assert payload["decision"] == "WATCH_ONLY"
    assert payload["tp1_source"] == "none"


def test_trade_plan_skip_reason_distinguishes_missing_tp1() -> None:
    reason, message = trade_plan_skip_reason(_scenario(take_profit=[]))

    assert reason == "invalid_trade_plan"
    assert message == "Không có TP1 hợp lệ."
