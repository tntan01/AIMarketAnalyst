"""Phase-3 fail-closed execution revalidation tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from core.execution_revalidation_engine import revalidate_execution
from core.scanner_models import ExecutionMarketSnapshot


NOW = datetime(2026, 7, 24, 8, 0, tzinfo=timezone.utc)


def _proposal(**overrides) -> dict:
    payload = {
        "symbol": "EUR/USD",
        "broker_symbol": "EURUSD",
        "side": "buy",
        "entry_zone": [1.0990, 1.1015],
        "entry_price": 9.9999,  # Must never be used by final revalidation.
        "current_price": 9.9999,
        "stop_loss": 1.0950,
        "take_profit": 1.1120,
        "volume": 0.10,
        "required_min_rr": 1.5,
    }
    payload.update(overrides)
    return payload


def _snapshot(**overrides) -> ExecutionMarketSnapshot:
    values = {
        "broker_symbol": "EURUSD",
        "captured_at": NOW,
        "connected": True,
        "logged_in": True,
        "trade_allowed": True,
        "symbol_available": True,
        "symbol_trade_mode": 4,
        "bid": 1.1000,
        "ask": 1.1002,
        "point": 0.0001,
        "spread_points": 2.0,
        "spread_price": 0.0002,
        "tick_time": NOW,
        "volume_min": 0.01,
        "volume_max": 100.0,
        "volume_step": 0.01,
        "symbol_state_available": True,
        "has_open_position_or_order": False,
        "reason_codes": (),
    }
    values.update(overrides)
    return ExecutionMarketSnapshot(**values)


def _validate(proposal=None, snapshot=None, **overrides):
    arguments = {
        "news_blackout": False,
        "account_allowed": True,
        "portfolio_allowed": True,
        "now": NOW,
    }
    arguments.update(overrides)
    return revalidate_execution(
        proposal if proposal is not None else _proposal(),
        snapshot if snapshot is not None else _snapshot(),
        **arguments,
    )


def test_valid_buy_uses_fresh_ask_and_passes():
    result = _validate()

    assert result.allowed is True
    assert result.execution_price == 1.1002
    assert result.expected_effective_rr is not None
    assert result.expected_effective_rr >= 1.5
    assert result.block_codes == ()


def test_snapshot_prices_in_proposal_are_never_used():
    result = _validate(snapshot=None, proposal=_proposal())
    assert result.execution_price == 1.1002
    assert result.execution_price != 9.9999


def test_missing_market_snapshot_fails_closed():
    result = revalidate_execution(
        _proposal(),
        None,
        news_blackout=False,
        account_allowed=True,
        portfolio_allowed=True,
        now=NOW,
    )
    assert result.allowed is False
    assert "REALTIME_MARKET_DATA_UNAVAILABLE" in result.block_codes


def test_stale_tick_is_blocked():
    result = _validate(
        snapshot=_snapshot(tick_time=NOW - timedelta(seconds=31))
    )
    assert "TICK_STALE" in result.block_codes


def test_wide_or_missing_spread_is_blocked():
    assert "SPREAD_TOO_WIDE" in _validate(
        snapshot=_snapshot(spread_points=51)
    ).block_codes
    assert "SPREAD_UNAVAILABLE" in _validate(
        snapshot=_snapshot(spread_points=None)
    ).block_codes


def test_live_execution_price_must_remain_in_zone():
    result = _validate(snapshot=_snapshot(ask=1.1020))
    assert "PRICE_OUTSIDE_ENTRY_ZONE" in result.block_codes
    assert result.live_price_valid is False


def test_sl_and_tp_must_be_on_correct_side():
    result = _validate(proposal=_proposal(stop_loss=1.1050))
    assert "SL_TP_WRONG_SIDE" in result.block_codes


def test_rr_is_recomputed_after_live_spread():
    result = _validate(proposal=_proposal(take_profit=1.1030))
    assert "EFFECTIVE_RR_BELOW_MIN" in result.block_codes


def test_volume_must_match_broker_limits_and_step():
    result = _validate(proposal=_proposal(volume=0.105))
    assert "VOLUME_OUTSIDE_BROKER_RULES" in result.block_codes


def test_existing_symbol_position_or_order_blocks():
    result = _validate(
        snapshot=_snapshot(has_open_position_or_order=True),
        portfolio_allowed=False,
    )
    assert "SYMBOL_ALREADY_ACTIVE" in result.block_codes
    assert "PORTFOLIO_GUARD_BLOCKED" in result.block_codes


def test_news_and_guard_unknown_states_fail_closed():
    result = _validate(
        news_blackout=None,
        account_allowed=None,
        portfolio_allowed=None,
    )
    assert {
        "NEWS_STATUS_UNAVAILABLE",
        "ACCOUNT_GUARD_UNAVAILABLE",
        "PORTFOLIO_GUARD_UNAVAILABLE",
    }.issubset(result.block_codes)


def test_news_blackout_blocks_order():
    result = _validate(news_blackout=True)
    assert "NEWS_BLACKOUT" in result.block_codes


def test_sell_uses_bid_and_direction_specific_trade_mode():
    proposal = _proposal(
        side="sell",
        entry_zone=[1.0990, 1.1015],
        stop_loss=1.1050,
        take_profit=1.0900,
    )
    result = _validate(
        proposal=proposal,
        snapshot=_snapshot(symbol_trade_mode=2),
    )
    assert result.allowed is True
    assert result.execution_price == 1.1000


def test_trade_mode_and_position_state_must_be_known():
    mode_result = _validate(snapshot=replace(_snapshot(), symbol_trade_mode=None))
    state_result = _validate(
        snapshot=replace(
            _snapshot(),
            symbol_state_available=False,
            has_open_position_or_order=None,
        ),
        portfolio_allowed=None,
    )
    assert "SYMBOL_SIDE_NOT_TRADABLE" in mode_result.block_codes
    assert "SYMBOL_POSITION_STATE_UNAVAILABLE" in state_result.block_codes
