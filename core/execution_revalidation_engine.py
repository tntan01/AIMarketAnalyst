"""Fail-closed realtime validation immediately before sending an order."""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from core.risk_engine import calculate_expected_effective_rr
from core.scanner_models import (
    ExecutionMarketSnapshot,
    ExecutionRevalidation,
    VALID_SIDES,
)
from core.scanner_strategy_engine import unique_codes


DEFAULT_MAX_TICK_AGE_SECONDS = 30.0
DEFAULT_MAX_SPREAD_POINTS = 50.0
_VOLUME_EPSILON = 1e-8


def revalidate_execution(
    proposal: dict[str, Any],
    snapshot: ExecutionMarketSnapshot | None,
    *,
    news_blackout: bool | None,
    account_allowed: bool | None,
    portfolio_allowed: bool | None,
    required_min_rr: float | None = None,
    max_tick_age_seconds: float = DEFAULT_MAX_TICK_AGE_SECONDS,
    max_spread_points: float = DEFAULT_MAX_SPREAD_POINTS,
    now: datetime | None = None,
) -> ExecutionRevalidation:
    """Validate a proposal using only fresh execution-time state.

    ``None`` is deliberately not treated as approval for any realtime guard.
    The proposal's snapshot price is never read.
    """

    checked_at = _as_utc(now or datetime.now(timezone.utc))
    blocks: list[str] = []
    reasons: list[str] = []

    if not isinstance(proposal, dict):
        proposal = {}
        blocks.append("INVALID_ORDER_PROPOSAL")

    side = str(proposal.get("side") or "").strip().lower()
    if side not in VALID_SIDES:
        blocks.append("INVALID_ORDER_SIDE")
        normalized_side: str | None = None
    else:
        normalized_side = side

    entry_low, entry_high = _entry_zone(proposal)
    if entry_low is None or entry_high is None:
        blocks.append("ENTRY_ZONE_UNAVAILABLE")

    stop_loss = _positive_float(proposal.get("stop_loss"))
    take_profit = _take_profit(proposal.get("take_profit"))
    if stop_loss is None:
        blocks.append("STOP_LOSS_UNAVAILABLE")
    if take_profit is None:
        blocks.append("TAKE_PROFIT_UNAVAILABLE")

    volume = _positive_float(proposal.get("volume"))
    if volume is None:
        blocks.append("VOLUME_INVALID")

    execution_price: float | None = None
    effective_rr: float | None = None
    live_price_valid = False
    news_allowed = news_blackout is False
    account_is_allowed = account_allowed is True
    portfolio_is_allowed = portfolio_allowed is True

    if snapshot is None:
        blocks.append("REALTIME_MARKET_DATA_UNAVAILABLE")
    else:
        reasons.extend(snapshot.reason_codes)
        if not snapshot.connected or not snapshot.logged_in:
            blocks.append("MT5_NOT_READY")
        if not snapshot.trade_allowed:
            blocks.append("ACCOUNT_TRADING_NOT_ALLOWED")
        if not snapshot.symbol_available:
            blocks.append("SYMBOL_UNAVAILABLE")
        if not _side_allowed_by_trade_mode(normalized_side, snapshot.symbol_trade_mode):
            blocks.append("SYMBOL_SIDE_NOT_TRADABLE")

        bid = _positive_float(snapshot.bid)
        ask = _positive_float(snapshot.ask)
        if bid is None or ask is None or ask < bid:
            blocks.append("BID_ASK_UNAVAILABLE")
        elif normalized_side == "buy":
            execution_price = ask
        elif normalized_side == "sell":
            execution_price = bid

        if snapshot.tick_time is None:
            blocks.append("TICK_TIME_UNAVAILABLE")
        else:
            tick_age = (checked_at - _as_utc(snapshot.tick_time)).total_seconds()
            if tick_age < -5 or tick_age > max(0.0, float(max_tick_age_seconds)):
                blocks.append("TICK_STALE")

        spread_points = _nonnegative_float(snapshot.spread_points)
        spread_price = _nonnegative_float(snapshot.spread_price)
        if spread_points is None or spread_price is None:
            blocks.append("SPREAD_UNAVAILABLE")
        elif spread_points > max(0.0, float(max_spread_points)):
            blocks.append("SPREAD_TOO_WIDE")

        if snapshot.symbol_state_available is not True:
            blocks.append("SYMBOL_POSITION_STATE_UNAVAILABLE")
        elif snapshot.has_open_position_or_order is not False:
            blocks.append("SYMBOL_ALREADY_ACTIVE")

        if volume is not None and not _valid_volume(volume, snapshot):
            blocks.append("VOLUME_OUTSIDE_BROKER_RULES")

        if (
            execution_price is not None
            and entry_low is not None
            and entry_high is not None
        ):
            live_price_valid = entry_low <= execution_price <= entry_high
            if not live_price_valid:
                blocks.append("PRICE_OUTSIDE_ENTRY_ZONE")

        if (
            normalized_side is not None
            and execution_price is not None
            and stop_loss is not None
            and take_profit is not None
        ):
            if not _valid_sl_tp_direction(
                normalized_side,
                execution_price,
                stop_loss,
                take_profit,
            ):
                blocks.append("SL_TP_WRONG_SIDE")
            elif spread_price is not None:
                effective_rr = calculate_expected_effective_rr(
                    normalized_side,
                    execution_price,
                    stop_loss,
                    take_profit,
                    spread_price,
                )

    min_rr = _positive_float(
        required_min_rr
        if required_min_rr is not None
        else proposal.get("required_min_rr", proposal.get("min_rr"))
    )
    if min_rr is None:
        blocks.append("REQUIRED_MIN_RR_UNAVAILABLE")
    elif effective_rr is None:
        blocks.append("EFFECTIVE_RR_UNAVAILABLE")
    elif effective_rr < min_rr:
        blocks.append("EFFECTIVE_RR_BELOW_MIN")

    if news_blackout is None:
        blocks.append("NEWS_STATUS_UNAVAILABLE")
    elif news_blackout:
        blocks.append("NEWS_BLACKOUT")
    if account_allowed is not True:
        blocks.append(
            "ACCOUNT_GUARD_UNAVAILABLE"
            if account_allowed is None
            else "ACCOUNT_GUARD_BLOCKED"
        )
    if portfolio_allowed is not True:
        blocks.append(
            "PORTFOLIO_GUARD_UNAVAILABLE"
            if portfolio_allowed is None
            else "PORTFOLIO_GUARD_BLOCKED"
        )

    block_codes = unique_codes(blocks)
    return ExecutionRevalidation(
        allowed=not block_codes,
        side=normalized_side,
        execution_price=execution_price,
        expected_effective_rr=effective_rr,
        required_min_rr=min_rr,
        volume=volume,
        live_price_valid=live_price_valid,
        news_allowed=news_allowed,
        account_allowed=account_is_allowed,
        portfolio_allowed=portfolio_is_allowed,
        checked_at=checked_at,
        reason_codes=unique_codes((*reasons, *block_codes)),
        block_codes=block_codes,
    )


def _entry_zone(proposal: dict[str, Any]) -> tuple[float | None, float | None]:
    raw = proposal.get("entry_zone")
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        low = _positive_float(raw[0])
        high = _positive_float(raw[1])
    else:
        low = _positive_float(proposal.get("entry_low"))
        high = _positive_float(proposal.get("entry_high"))
    if low is None or high is None:
        return None, None
    return (low, high) if low <= high else (high, low)


def _take_profit(value: object) -> float | None:
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return _positive_float(value)


def _positive_float(value: object) -> float | None:
    number = _finite_float(value)
    return number if number is not None and number > 0 else None


def _nonnegative_float(value: object) -> float | None:
    number = _finite_float(value)
    return number if number is not None and number >= 0 else None


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None


def _valid_sl_tp_direction(
    side: str,
    price: float,
    stop_loss: float,
    take_profit: float,
) -> bool:
    if side == "buy":
        return stop_loss < price < take_profit
    return take_profit < price < stop_loss


def _valid_volume(
    volume: float,
    snapshot: ExecutionMarketSnapshot,
) -> bool:
    minimum = _positive_float(snapshot.volume_min)
    maximum = _positive_float(snapshot.volume_max)
    step = _positive_float(snapshot.volume_step)
    if minimum is None or maximum is None or step is None:
        return False
    if volume < minimum - _VOLUME_EPSILON or volume > maximum + _VOLUME_EPSILON:
        return False
    steps = (volume - minimum) / step
    return abs(steps - round(steps)) <= _VOLUME_EPSILON


def _side_allowed_by_trade_mode(side: str | None, mode: int | None) -> bool:
    # MetaTrader 5: 0 disabled, 1 long only, 2 short only, 3 close only, 4 full.
    if side is None or mode is None:
        return False
    return mode in ({1, 4} if side == "buy" else {2, 4})


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
