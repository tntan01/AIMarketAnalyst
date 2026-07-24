"""Phase-4 portfolio risk engine tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from core.portfolio_models import PortfolioRiskItem, PortfolioSnapshot
from core.portfolio_risk_engine import evaluate_portfolio_risk
from core.scanner_models import ExecutionMarketSnapshot


NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def _item(
    symbol: str = "EUR/USD",
    side: str = "buy",
    *,
    source: str = "position",
    ticket: int = 1,
    entry: float = 1.1000,
    current: float | None = 1.1000,
    stop: float | None = 1.0900,
    volume: float = 0.10,
    tick_size: float | None = 0.0001,
    tick_value: float | None = 10.0,
) -> PortfolioRiskItem:
    return PortfolioRiskItem(
        source=source,
        ticket=ticket,
        symbol=symbol,
        broker_symbol=symbol.replace("/", ""),
        side=side,
        entry_price=entry,
        current_price=current,
        stop_loss=stop,
        volume=volume,
        tick_size=tick_size,
        tick_value_loss=tick_value,
        contract_size=100000.0,
    )


def _portfolio(*items, pending=(), balance=10000.0, available=True):
    return PortfolioSnapshot(
        available=available,
        captured_at=NOW,
        account_balance=balance,
        account_currency="USD",
        positions=tuple(items),
        pending_orders=tuple(pending),
    )


def _market(symbol="EURUSD", bid=1.0998, ask=1.1000):
    return ExecutionMarketSnapshot(
        broker_symbol=symbol,
        captured_at=NOW,
        connected=True,
        logged_in=True,
        trade_allowed=True,
        symbol_available=True,
        symbol_trade_mode=4,
        bid=bid,
        ask=ask,
        point=0.0001,
        spread_points=2.0,
        spread_price=0.0002,
        tick_time=NOW,
        volume_min=0.01,
        volume_max=100.0,
        volume_step=0.01,
        symbol_state_available=True,
        has_open_position_or_order=False,
        trade_tick_size=0.0001,
        trade_tick_value_loss=10.0,
        contract_size=100000.0,
    )


def _proposal(symbol="GBP/USD", side="buy", volume=0.1, stop=1.09):
    return {
        "symbol": symbol,
        "broker_symbol": symbol.replace("/", ""),
        "side": side,
        "volume": volume,
        "stop_loss": stop,
    }


def test_current_and_proposed_risk_are_broker_valued():
    result = evaluate_portfolio_risk(
        _portfolio(_item()),
        proposal=_proposal(),
        market_snapshot=_market("GBPUSD"),
        now=NOW,
    )

    assert result.allowed is True
    assert result.current_open_risk_pct == 1.0
    assert result.proposed_risk_pct == 1.0
    assert result.projected_open_risk_pct == 2.0


def test_projected_total_open_risk_is_enforced():
    current = _item(volume=0.25)
    result = evaluate_portfolio_risk(
        _portfolio(current),
        proposal=_proposal(volume=0.1),
        market_snapshot=_market("GBPUSD"),
        limits={"max_open_risk_pct": 3.0},
        now=NOW,
    )

    assert result.current_open_risk_pct == 2.5
    assert result.projected_open_risk_pct == 3.5
    assert "PORTFOLIO_RISK_EXCEEDED" in result.block_codes


def test_missing_snapshot_or_balance_fails_closed():
    missing = evaluate_portfolio_risk(None, now=NOW)
    no_balance = evaluate_portfolio_risk(
        _portfolio(balance=None),
        now=NOW,
    )

    assert "PORTFOLIO_SNAPSHOT_UNAVAILABLE" in missing.block_codes
    assert "ACCOUNT_BALANCE_UNAVAILABLE" in no_balance.block_codes


def test_position_without_sl_blocks_new_risk():
    result = evaluate_portfolio_risk(
        _portfolio(_item(stop=None)),
        proposal=_proposal(),
        market_snapshot=_market("GBPUSD"),
        now=NOW,
    )
    assert "POSITION_WITHOUT_SL" in result.block_codes
    assert "PORTFOLIO_RISK_UNAVAILABLE" in result.block_codes


def test_missing_broker_valuation_fails_closed():
    result = evaluate_portfolio_risk(
        _portfolio(_item(tick_value=None)),
        now=NOW,
    )
    assert "PORTFOLIO_VALUATION_UNAVAILABLE" in result.block_codes


def test_symbol_risk_limit_is_enforced():
    result = evaluate_portfolio_risk(
        _portfolio(
            _item(ticket=1, volume=0.15),
            _item(ticket=2, volume=0.10),
        ),
        limits={"max_symbol_risk_pct": 2.0},
        now=NOW,
    )
    assert result.symbol_risk_pct["EUR/USD"] == 2.5
    assert "SYMBOL_RISK_EXCEEDED" in result.block_codes


def test_same_currency_direction_forms_correlated_cluster():
    result = evaluate_portfolio_risk(
        _portfolio(_item(symbol="EUR/USD")),
        proposal=_proposal(symbol="GBP/USD"),
        market_snapshot=_market("GBPUSD"),
        limits={
            "max_currency_exposure_pct": 1.5,
            "max_correlated_risk_pct": 1.5,
        },
        now=NOW,
    )

    assert result.currency_exposure_pct["USD"]["short"] == 2.0
    assert "CURRENCY_EXPOSURE_EXCEEDED" in result.block_codes
    assert "CORRELATED_RISK_EXCEEDED" in result.block_codes
    usd_cluster = next(
        cluster
        for cluster in result.correlation_clusters
        if cluster["currency"] == "USD"
    )
    assert usd_cluster["symbols"] == ["EUR/USD", "GBP/USD"]


def test_opposite_currency_directions_are_not_one_correlation_cluster():
    buy_eurusd = _item(symbol="EUR/USD", side="buy")
    sell_gbpusd = _item(
        symbol="GBP/USD",
        side="sell",
        entry=1.1000,
        current=1.1000,
        stop=1.1100,
        ticket=2,
    )
    result = evaluate_portfolio_risk(
        _portfolio(buy_eurusd, sell_gbpusd),
        now=NOW,
    )

    assert result.currency_exposure_pct["USD"]["net"] == 0.0
    assert not any(
        cluster["currency"] == "USD"
        for cluster in result.correlation_clusters
    )


def test_pending_orders_count_toward_risk_and_order_limit():
    pending = _item(
        source="pending_order",
        current=None,
        ticket=9,
    )
    result = evaluate_portfolio_risk(
        _portfolio(_item(), pending=(pending,)),
        proposal=_proposal(),
        market_snapshot=_market("GBPUSD"),
        limits={"max_concurrent_orders": 2},
        now=NOW,
    )

    assert result.current_open_risk_pct == 2.0
    assert result.projected_order_count == 3
    assert "MAX_CONCURRENT_ORDERS_EXCEEDED" in result.block_codes


def test_daily_weekly_and_consecutive_loss_guard_is_integrated():
    closed = [
        {
            "closed_at": NOW.isoformat(),
            "result_pct": -1.0,
            "result_r": -1.0,
        },
        {
            "closed_at": NOW.isoformat(),
            "result_pct": -1.0,
            "result_r": -1.0,
        },
    ]
    result = evaluate_portfolio_risk(
        _portfolio(),
        closed_trades=closed,
        limits={
            "max_daily_loss_pct": 2.0,
            "max_weekly_loss_pct": 2.0,
            "max_consecutive_losses": 2,
        },
        now=NOW,
    )

    assert result.account_allowed is False
    assert "DAILY_LOSS_LIMIT_REACHED" in result.block_codes
    assert "WEEKLY_LOSS_LIMIT_REACHED" in result.block_codes
    assert "MAX_CONSECUTIVE_LOSSES_REACHED" in result.block_codes


def test_locked_profit_position_has_zero_remaining_open_risk():
    locked = _item(current=1.1100, stop=1.1050)
    result = evaluate_portfolio_risk(_portfolio(locked), now=NOW)
    assert result.current_open_risk_pct == 0.5

    fully_protected = replace(locked, stop_loss=1.1100)
    protected_result = evaluate_portfolio_risk(
        _portfolio(fully_protected),
        now=NOW,
    )
    assert protected_result.current_open_risk_pct == 0.0


def test_current_only_post_trade_evaluation_has_zero_proposed_risk():
    result = evaluate_portfolio_risk(_portfolio(_item()), now=NOW)
    assert result.proposed_risk_pct == 0.0
    assert result.projected_open_risk_pct == result.current_open_risk_pct


def test_result_is_structured_and_versioned():
    payload = evaluate_portfolio_risk(_portfolio(), now=NOW).to_dict()
    assert payload["portfolio_engine_version"] == "phase4-portfolio-v1"
    assert isinstance(payload["symbol_risk_pct"], dict)
    assert isinstance(payload["currency_exposure_pct"], dict)
    assert isinstance(payload["correlation_clusters"], list)
    assert isinstance(payload["block_codes"], list)
