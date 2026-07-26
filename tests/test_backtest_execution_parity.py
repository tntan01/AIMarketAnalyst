from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from config.settings import default_settings
from controllers.backtest_controller import BacktestController
from core.backtest_contract import (
    BACKTEST_PURPOSE_VALIDATION,
    build_runtime_backtest_contract,
)
from core.backtest_execution_parity import (
    EXECUTION_COST_MODEL_VERSION,
    EXECUTION_MODE_PARITY,
    EXECUTION_MODE_RESEARCH,
    apply_execution_costs,
    count_rollover_units,
    quote_rate_at,
    session_spread_price,
    size_position,
)
from core.market_models import Candle
from core.system_backtest_engine import (
    BacktestRequest,
    simulate_trade_from_analysis,
    summarize_backtest_trades,
    validate_backtest_input,
)


def _candle(
    moment: datetime,
    open_price: float,
    high: float,
    low: float,
    close: float,
) -> Candle:
    return Candle(moment, open_price, high, low, close, 100.0)


def _request(**overrides) -> BacktestRequest:
    values = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "start": datetime(2026, 1, 5, tzinfo=UTC),
        "end": datetime(2026, 1, 7, tzinfo=UTC),
        "initial_balance": 10_000.0,
        "risk_percent": 1.0,
        "execution_mode": EXECUTION_MODE_PARITY,
        "cost_model_configured": True,
        "spread_price": 0.0002,
        "entry_slippage_price": 0.00005,
        "exit_slippage_price": 0.00005,
        "commission_per_lot_round_turn": 7.0,
        "contract_size_override": 100_000.0,
        "setup_expiry_minutes": 60,
        "max_holding_minutes": 120,
    }
    values.update(overrides)
    return BacktestRequest(**values)


def _analysis() -> dict:
    return {
        "decision_engine": {"decision": "READY_TO_TRADE"},
        "scenario_scores": {
            "buy": {"signal_score": 72},
            "sell": {"signal_score": 40},
        },
        "decision_summary": {"best_side": "buy", "score_gap": 32},
        "market_regime": {"primary": "range"},
        "final_score": 72,
    }


def test_session_spread_model_uses_utc_bucket() -> None:
    spread, session = session_spread_price(
        0.0002,
        datetime(2026, 1, 5, 14, tzinfo=UTC),
    )
    assert session == "OVERLAP"
    assert spread == pytest.approx(0.00018)


def test_quote_conversion_is_point_in_time_and_can_be_inverted() -> None:
    candles = [
        _candle(datetime(2026, 1, 5, 10, tzinfo=UTC), 100, 101, 99, 100),
        _candle(datetime(2026, 1, 5, 11, tzinfo=UTC), 200, 201, 199, 200),
    ]
    rate = quote_rate_at(
        candles,
        datetime(2026, 1, 5, 11, 30, tzinfo=UTC),
        inverted=True,
    )
    assert rate == pytest.approx(0.01)


def test_position_size_floors_step_and_caps_maximum() -> None:
    normal = size_position(
        balance=10_000,
        risk_percent=1,
        entry_price=1.1,
        stop_loss=1.099,
        contract_size=100_000,
        quote_to_account_rate=1,
        lot_step=0.1,
        minimum_lot=0.1,
        maximum_lot=10,
    )
    capped = size_position(
        balance=1_000_000,
        risk_percent=10,
        entry_price=1.1,
        stop_loss=1.099,
        contract_size=100_000,
        quote_to_account_rate=1,
        lot_step=0.1,
        minimum_lot=0.1,
        maximum_lot=2,
    )
    assert normal.lot == 1.0
    assert capped.lot == 2.0
    assert capped.capped_by_maximum is True


def test_execution_costs_report_gross_cost_and_net() -> None:
    result = apply_execution_costs(
        side="buy",
        raw_entry_price=1.1000,
        raw_exit_price=1.1040,
        stop_loss=1.0980,
        entry_time=datetime(2026, 1, 5, 14, tzinfo=UTC),
        exit_time=datetime(2026, 1, 5, 18, tzinfo=UTC),
        balance=10_000,
        risk_percent=1,
        contract_size=100_000,
        quote_rate_entry=1,
        quote_rate_exit=1,
        lot_step=0.01,
        minimum_lot=0.01,
        maximum_lot=100,
        base_spread_price=0.0002,
        spread_session_multipliers=None,
        entry_slippage_price=0.00005,
        exit_slippage_price=0.00005,
        commission_per_lot_round_turn=7,
        swap_long_per_lot_day=0,
        swap_short_per_lot_day=0,
    )
    assert result.position.lot > 0
    assert result.gross_r > result.net_r
    assert result.cost_r == pytest.approx(result.gross_r - result.net_r)
    assert result.net_pnl_account < result.gross_pnl_account
    assert result.commission_account > 0
    assert result.spread_slippage_account > 0


def test_sell_pays_spread_on_exit_not_entry() -> None:
    result = apply_execution_costs(
        side="sell",
        raw_entry_price=1.1000,
        raw_exit_price=1.0960,
        stop_loss=1.1020,
        entry_time=datetime(2026, 1, 5, 14, tzinfo=UTC),
        exit_time=datetime(2026, 1, 5, 18, tzinfo=UTC),
        balance=10_000,
        risk_percent=1,
        contract_size=100_000,
        quote_rate_entry=1,
        quote_rate_exit=1,
        lot_step=0.01,
        minimum_lot=0.01,
        maximum_lot=100,
        base_spread_price=0.0002,
        spread_session_multipliers=None,
        entry_slippage_price=0,
        exit_slippage_price=0,
        commission_per_lot_round_turn=0,
        swap_long_per_lot_day=0,
        swap_short_per_lot_day=0,
    )
    assert result.entry_spread_price == 0
    assert result.exit_spread_price > 0
    assert result.exit_price > result.raw_exit_price


def test_rollover_uses_wednesday_triple_swap() -> None:
    assert count_rollover_units(
        datetime(2026, 1, 6, 20, tzinfo=UTC),
        datetime(2026, 1, 8, 22, tzinfo=UTC),
    ) == 5


def test_simulated_parity_trade_persists_cost_trace() -> None:
    base = datetime(2026, 1, 5, 12, tzinfo=UTC)
    candles = [
        _candle(base, 1.1000, 1.1008, 1.0995, 1.1000),
        _candle(base + timedelta(minutes=15), 1.1000, 1.1045, 1.0998, 1.1040),
    ]
    scenario = {
        "type": "buy",
        "entry_zone": [1.0990, 1.1010],
        "stop_loss": 1.0980,
        "take_profit": [1.1040],
        "entry_status": "confirmed_entry",
    }
    trade = simulate_trade_from_analysis(
        request=_request(),
        analysis=_analysis(),
        scenario=scenario,
        entry_candle=candles[0],
        future_candles=candles,
        signal_time=base,
        account_balance=10_000,
    )
    assert trade is not None
    assert trade.execution_mode == EXECUTION_MODE_PARITY
    assert trade.result_r == trade.net_r
    assert trade.gross_r > trade.net_r
    assert trade.cost_r > 0
    assert trade.position_lot > 0
    assert trade.cost_breakdown["commission_account"] > 0
    summary = summarize_backtest_trades([trade])
    assert summary["gross_net_difference_r"] == pytest.approx(trade.cost_r)


def test_validation_requires_parity_and_configured_cost_model() -> None:
    candles = {timeframe: [_candle(datetime(2026, 1, 5, tzinfo=UTC), 1, 1, 1, 1)] for timeframe in ("D1", "H4", "H1", "M15")}
    with pytest.raises(ValueError, match="EXECUTION_PARITY_REQUIRED"):
        validate_backtest_input(
            _request(
                purpose=BACKTEST_PURPOSE_VALIDATION,
                execution_mode=EXECUTION_MODE_RESEARCH,
            ),
            candles,
        )
    with pytest.raises(ValueError, match="EXECUTION_COST_MODEL_NOT_CONFIGURED"):
        validate_backtest_input(
            _request(
                purpose=BACKTEST_PURPOSE_VALIDATION,
                cost_model_configured=False,
            ),
            candles,
        )


def test_runtime_contract_locks_execution_and_cost_versions() -> None:
    contract = build_runtime_backtest_contract(
        BACKTEST_PURPOSE_VALIDATION,
        EXECUTION_MODE_PARITY,
    )
    assert contract["execution_parity"] is True
    assert contract["execution_mode"] == EXECUTION_MODE_PARITY
    assert contract["cost_model_version"] == EXECUTION_COST_MODEL_VERSION


class _SettingsService:
    def __init__(self) -> None:
        self.settings = default_settings()
        self.settings.trading.maximum_lot = 3.0
        self.settings.trading.backtest_slippage_price = 0.00005
        self.settings.trading.backtest_commission_per_lot_round_turn = 7.0
        self.settings.trading.max_daily_loss_pct = 1.5

    def load(self):
        return self.settings


class _MT5:
    def available_symbols(self, market_watch_only=True):
        return ["EURUSD"]

    def resolve_symbol(self, symbol, available):
        return "EURUSD"

    def symbol_data_quality(self, display_symbol, broker_symbol):
        return {"spread_price": 0.0002, "contract_size": 100_000}


def test_controller_maps_settings_to_execution_parity_request() -> None:
    controller = BacktestController(_SettingsService(), _MT5())
    request = controller.build_request(
        symbol="EUR/USD",
        start=datetime(2026, 1, 1, tzinfo=UTC),
        end=datetime(2026, 1, 2, tzinfo=UTC),
        initial_balance=10_000,
        risk_percent=1,
    )
    assert request.execution_mode == EXECUTION_MODE_PARITY
    assert request.account_guard_enabled is True
    assert request.max_daily_loss_pct == 1.5
    assert request.maximum_lot == 3.0
    assert request.spread_price == pytest.approx(0.0002)
    assert request.commission_per_lot_round_turn == 7.0
