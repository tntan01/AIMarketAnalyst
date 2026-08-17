"""Phase-4 portfolio risk engine.

The engine is pure: MT5 collection happens in the service layer, while this
module values every live item and the proposed order against one snapshot.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import isfinite
from typing import Any

from core.account_guard import check_account_guard
from core.portfolio_models import (
    PortfolioEvaluation,
    PortfolioRiskItem,
    PortfolioSnapshot,
)
from core.scanner_models import ExecutionMarketSnapshot
from core.scanner_strategy_engine import unique_codes


DEFAULT_LIMITS: dict[str, float | int | str] = {
    "max_open_risk_pct": 3.0,
    "max_symbol_risk_pct": 2.0,
    "max_currency_exposure_pct": 2.0,
    "max_correlated_risk_pct": 2.0,
    "max_concurrent_orders": 5,
    "max_daily_loss_pct": 2.0,
    "max_weekly_loss_pct": 5.0,
    "max_consecutive_losses": 3,
    "trader_timezone": "Asia/Ho_Chi_Minh",
}


def evaluate_portfolio_risk(
    snapshot: PortfolioSnapshot | None,
    *,
    proposal: dict[str, Any] | None = None,
    market_snapshot: ExecutionMarketSnapshot | None = None,
    closed_trades: list[dict[str, object]] | None = None,
    limits: dict[str, object] | None = None,
    now: datetime | None = None,
) -> PortfolioEvaluation:
    """Return current/projected risk and fail closed on incomplete live data."""

    checked_at = _as_utc(now or datetime.now(timezone.utc))
    cfg = dict(DEFAULT_LIMITS)
    if limits:
        cfg.update(limits)

    max_open = _positive_limit(cfg.get("max_open_risk_pct"), 3.0)
    max_symbol = _positive_limit(cfg.get("max_symbol_risk_pct"), 2.0)
    max_currency = _positive_limit(
        cfg.get("max_currency_exposure_pct"),
        2.0,
    )
    max_correlated = _positive_limit(
        cfg.get("max_correlated_risk_pct"),
        2.0,
    )
    max_orders = max(1, int(cfg.get("max_concurrent_orders", 5) or 5))

    blocks: list[str] = []
    warnings: list[str] = []
    if snapshot is None or snapshot.available is not True:
        blocks.append("PORTFOLIO_SNAPSHOT_UNAVAILABLE")
    if snapshot is not None:
        blocks.extend(snapshot.reason_codes)

    balance = (
        _positive_float(snapshot.account_balance)
        if snapshot is not None
        else None
    )
    if balance is None:
        blocks.append("ACCOUNT_BALANCE_UNAVAILABLE")

    account_guard = check_account_guard(
        closed_trades=closed_trades,
        open_trades=[],
        settings={
            "max_daily_loss_pct": _positive_limit(
                cfg.get("max_daily_loss_pct"),
                2.0,
            ),
            "max_weekly_loss_pct": _positive_limit(
                cfg.get("max_weekly_loss_pct"),
                5.0,
            ),
            "max_consecutive_losses": max(
                1,
                int(cfg.get("max_consecutive_losses", 3) or 3),
            ),
            # Projected portfolio risk is evaluated below; avoid applying the
            # legacy current-only open-risk check a second time.
            "max_open_risk_pct": float("inf"),
            "trader_timezone": str(
                cfg.get("trader_timezone") or "Asia/Ho_Chi_Minh"
            ),
        },
        action="open_new_trade",
        now=checked_at,
        account_balance=balance,
    )
    account_allowed = account_guard.get("allowed") is True
    if not account_allowed:
        blocks.extend(
            str(code)
            for code in account_guard.get("block_codes", [])
        )

    valued: list[dict[str, Any]] = []
    if snapshot is not None and balance is not None:
        for item in (*snapshot.positions, *snapshot.pending_orders):
            exposure, item_blocks = _value_existing_item(item, balance)
            blocks.extend(item.reason_codes)
            blocks.extend(item_blocks)
            if exposure is not None:
                valued.append(exposure)

    current_risk = (
        round(sum(float(item["risk_pct"]) for item in valued), 4)
        if balance is not None and not _has_valuation_failure(blocks)
        else None
    )

    proposed: dict[str, Any] | None = None
    proposed_risk: float | None = 0.0 if proposal is None else None
    if proposal is not None and balance is not None:
        proposed, proposal_blocks = _value_proposal(
            proposal,
            market_snapshot,
            balance,
        )
        blocks.extend(proposal_blocks)
        if proposed is not None:
            proposed_risk = round(float(proposed["risk_pct"]), 4)

    all_exposures = [*valued, *([proposed] if proposed is not None else [])]
    projected_risk = (
        round(float(current_risk or 0.0) + float(proposed_risk or 0.0), 4)
        if current_risk is not None and proposed_risk is not None
        else None
    )

    symbol_risk = _symbol_risk(all_exposures)
    currency_exposure, currency_members = _currency_exposure(all_exposures)
    clusters = _correlation_clusters(currency_exposure, currency_members)

    if projected_risk is None:
        blocks.append("PORTFOLIO_RISK_UNAVAILABLE")
    elif projected_risk > max_open:
        blocks.append("PORTFOLIO_RISK_EXCEEDED")

    if any(value > max_symbol for value in symbol_risk.values()):
        blocks.append("SYMBOL_RISK_EXCEEDED")
    if any(
        max(values["long"], values["short"]) > max_currency
        for values in currency_exposure.values()
    ):
        blocks.append("CURRENCY_EXPOSURE_EXCEEDED")
    if any(
        float(cluster["risk_pct"]) > max_correlated
        for cluster in clusters
    ):
        blocks.append("CORRELATED_RISK_EXCEEDED")

    current_count = (
        len(snapshot.positions) + len(snapshot.pending_orders)
        if snapshot is not None
        else 0
    )
    projected_count = current_count + (1 if proposal is not None else 0)
    if projected_count > max_orders:
        blocks.append("MAX_CONCURRENT_ORDERS_EXCEEDED")

    block_codes = unique_codes(blocks)
    portfolio_only_codes = tuple(
        code
        for code in block_codes
        if code not in set(account_guard.get("block_codes", []))
    )
    portfolio_allowed = not portfolio_only_codes
    return PortfolioEvaluation(
        allowed=not block_codes,
        portfolio_allowed=portfolio_allowed,
        account_allowed=account_allowed,
        snapshot_available=bool(snapshot and snapshot.available),
        current_open_risk_pct=current_risk,
        proposed_risk_pct=proposed_risk,
        projected_open_risk_pct=projected_risk,
        max_open_risk_pct=max_open,
        current_order_count=current_count,
        projected_order_count=projected_count,
        max_concurrent_orders=max_orders,
        symbol_risk_pct=symbol_risk,
        currency_exposure_pct=currency_exposure,
        correlation_clusters=tuple(clusters),
        account_guard=account_guard,
        checked_at=checked_at,
        reason_codes=unique_codes((*block_codes, *warnings)),
        block_codes=block_codes,
        warning_codes=unique_codes(warnings),
    )


def _value_existing_item(
    item: PortfolioRiskItem,
    balance: float,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    side = _normalize_side(item.side)
    volume = _positive_float(item.volume)
    entry = _positive_float(item.entry_price)
    current = _positive_float(item.current_price)
    stop = _positive_float(item.stop_loss)
    if side is None or volume is None or entry is None:
        return None, ("PORTFOLIO_ITEM_INVALID",)
    if stop is None:
        return None, ("POSITION_WITHOUT_SL",)

    reference = current if item.source == "position" and current else entry
    distance = _adverse_distance(side, reference, stop)
    if distance is None:
        return None, ("POSITION_SL_WRONG_SIDE",)
    risk_amount = _broker_risk_amount(
        distance,
        volume,
        item.tick_size,
        item.tick_value_loss,
    )
    if risk_amount is None:
        return None, ("PORTFOLIO_VALUATION_UNAVAILABLE",)
    return _exposure_payload(
        item.symbol,
        side,
        risk_amount,
        balance,
        source=item.source,
        ticket=item.ticket,
    ), ()


def _value_proposal(
    proposal: dict[str, Any],
    market: ExecutionMarketSnapshot | None,
    balance: float,
) -> tuple[dict[str, Any] | None, tuple[str, ...]]:
    if market is None:
        return None, ("PROPOSED_RISK_MARKET_DATA_UNAVAILABLE",)
    side = _normalize_side(proposal.get("side"))
    volume = _positive_float(proposal.get("volume"))
    stop = _positive_float(proposal.get("stop_loss"))
    price = (
        _positive_float(market.ask)
        if side == "buy"
        else _positive_float(market.bid) if side == "sell" else None
    )
    if side is None or volume is None or stop is None or price is None:
        return None, ("PROPOSED_RISK_INPUT_INVALID",)
    distance = _adverse_distance(side, price, stop)
    if distance is None:
        return None, ("PROPOSED_SL_WRONG_SIDE",)
    risk_amount = _broker_risk_amount(
        distance,
        volume,
        market.trade_tick_size,
        market.trade_tick_value_loss,
    )
    if risk_amount is None:
        return None, ("PROPOSED_RISK_VALUATION_UNAVAILABLE",)
    return _exposure_payload(
        str(proposal.get("symbol") or market.broker_symbol),
        side,
        risk_amount,
        balance,
        source="proposal",
        ticket=0,
    ), ()


def _broker_risk_amount(
    distance: float,
    volume: float,
    tick_size: object,
    tick_value_loss: object,
) -> float | None:
    size = _positive_float(tick_size)
    value = _positive_float(tick_value_loss)
    if size is None or value is None:
        return None
    return max(distance / size * value * volume, 0.0)


def _adverse_distance(side: str, reference: float, stop: float) -> float | None:
    if side == "buy":
        return reference - stop if stop <= reference else None
    if side == "sell":
        return stop - reference if stop >= reference else None
    return None


def _exposure_payload(
    symbol: str,
    side: str,
    risk_amount: float,
    balance: float,
    *,
    source: str,
    ticket: int,
) -> dict[str, Any]:
    normalized_symbol = _display_symbol(symbol)
    return {
        "symbol": normalized_symbol,
        "side": side,
        "source": source,
        "ticket": ticket,
        "risk_amount": round(risk_amount, 2),
        "risk_pct": round(risk_amount / balance * 100.0, 4),
    }


def _symbol_risk(exposures: list[dict[str, Any]]) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in exposures:
        symbol = str(item["symbol"])
        result[symbol] = result.get(symbol, 0.0) + float(item["risk_pct"])
    return {key: round(value, 4) for key, value in sorted(result.items())}


def _currency_exposure(
    exposures: list[dict[str, Any]],
) -> tuple[
    dict[str, dict[str, float]],
    dict[tuple[str, str], list[dict[str, Any]]],
]:
    totals: dict[str, dict[str, float]] = {}
    members: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in exposures:
        symbol = str(item["symbol"])
        side = str(item["side"])
        risk = float(item["risk_pct"])
        base, quote = _currency_legs(symbol)
        legs = (
            ((base, "long"), (quote, "short"))
            if side == "buy"
            else ((base, "short"), (quote, "long"))
        )
        for currency, direction in legs:
            values = totals.setdefault(
                currency,
                {"long": 0.0, "short": 0.0, "net": 0.0},
            )
            values[direction] += risk
            values["net"] += risk if direction == "long" else -risk
            members.setdefault((currency, direction), []).append(item)
    rounded = {
        currency: {
            key: round(value, 4)
            for key, value in values.items()
        }
        for currency, values in sorted(totals.items())
    }
    return rounded, members


def _correlation_clusters(
    exposure: dict[str, dict[str, float]],
    members: dict[tuple[str, str], list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for (currency, direction), items in sorted(members.items()):
        symbols = sorted({str(item["symbol"]) for item in items})
        if len(symbols) < 2:
            continue
        clusters.append({
            "currency": currency,
            "direction": direction,
            "symbols": symbols,
            "risk_pct": exposure[currency][direction],
            "member_count": len(items),
        })
    return clusters


def _currency_legs(symbol: str) -> tuple[str, str]:
    if "/" in symbol:
        base, quote = symbol.split("/", 1)
        if base and quote:
            return base.upper(), quote.upper()
    compact = "".join(char for char in symbol.upper() if char.isalpha())
    if len(compact) >= 6:
        return compact[:3], compact[3:6]
    token = compact or symbol.upper()
    return token, f"{token}_COUNTER"


def _display_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if "/" in text:
        return text
    compact = "".join(char for char in text if char.isalpha())
    if len(compact) == 6:
        return f"{compact[:3]}/{compact[3:]}"
    return text


def _normalize_side(value: object) -> str | None:
    side = str(value or "").strip().lower()
    if side.startswith("buy"):
        return "buy"
    if side.startswith("sell"):
        return "sell"
    return None


def _positive_limit(value: object, default: float) -> float:
    number = _positive_float(value)
    return number if number is not None else default


def _positive_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) and number > 0 else None


def _has_valuation_failure(codes: list[str]) -> bool:
    return any(
        code in {
            "PORTFOLIO_ITEM_INVALID",
            "POSITION_WITHOUT_SL",
            "POSITION_SL_WRONG_SIDE",
            "PORTFOLIO_VALUATION_UNAVAILABLE",
        }
        for code in codes
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
