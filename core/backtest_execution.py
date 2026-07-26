from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from core.backtest_market_data import candle_close_time, normalize_utc
from core.market_models import Candle


BACKTEST_EXECUTION_POLICY_VERSION = "backtest-execution-sequence-v1"
ENTRY_FILL_MODEL = "confirmation_close"
EXIT_EVALUATION_MODEL = "next_execution_candle"

SAME_BAR_STOP_FIRST = "STOP_FIRST"
SAME_BAR_TARGET_FIRST = "TARGET_FIRST"
VALID_SAME_BAR_POLICIES = frozenset({
    SAME_BAR_STOP_FIRST,
    SAME_BAR_TARGET_FIRST,
})


@dataclass(frozen=True, slots=True)
class EntryFill:
    candle: Candle
    candle_index: int
    filled_at: datetime
    price: float
    reason: str


@dataclass(frozen=True, slots=True)
class ExitResolution:
    exited_at: datetime | None
    price: float | None
    outcome: str
    holding_bars: int
    reason: str


def find_confirmation_close_fill(
    *,
    side: str,
    zone_low: float,
    zone_high: float,
    future_candles: list[Candle],
    setup_active_time: datetime,
    setup_expiry: timedelta,
    execution_timeframe: str,
    spread_price: float = 0.0,
    slippage_price: float = 0.0,
) -> EntryFill | None:
    """Fill only after a post-signal candle closes with valid confirmation.

    A candle that gaps completely across the entry zone without trading inside
    it is not considered touched and therefore cannot create a fill.
    """

    normalized_side = str(side or "").lower()
    if normalized_side not in {"buy", "sell"}:
        return None
    active_at = normalize_utc(setup_active_time)[0]
    expires_at = active_at + setup_expiry
    cost = max(0.0, float(spread_price or 0.0)) + max(
        0.0,
        float(slippage_price or 0.0),
    )

    for index, candle in enumerate(future_candles):
        closed_at = candle_close_time(candle, execution_timeframe)
        if closed_at <= active_at:
            continue
        if closed_at > expires_at:
            break
        if not (candle.low <= zone_high and candle.high >= zone_low):
            continue
        if normalized_side == "buy" and candle.close > zone_low:
            return EntryFill(
                candle=candle,
                candle_index=index,
                filled_at=closed_at,
                price=float(candle.close) + cost,
                reason="confirmation_close",
            )
        if normalized_side == "sell" and candle.close < zone_high:
            return EntryFill(
                candle=candle,
                candle_index=index,
                filled_at=closed_at,
                price=float(candle.close) - cost,
                reason="confirmation_close",
            )
    return None


def resolve_post_fill_exit(
    *,
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    future_candles: list[Candle],
    filled_at: datetime,
    max_holding: timedelta,
    execution_timeframe: str,
    same_bar_policy: str = SAME_BAR_STOP_FIRST,
) -> ExitResolution:
    """Resolve exit using candles that close strictly after the fill.

    Gap checks use the next candle open before intrabar high/low checks. When
    both SL and TP occur in one post-fill candle and no lower-timeframe path is
    available, the explicit same-bar policy decides the result.
    """

    normalized_side = str(side or "").lower()
    policy = str(same_bar_policy or "").upper()
    if policy not in VALID_SAME_BAR_POLICIES:
        raise ValueError(f"Same-bar policy không hỗ trợ: {same_bar_policy}")
    if not valid_trade_geometry(
        normalized_side,
        entry_price,
        stop_loss,
        take_profit,
    ):
        return ExitResolution(None, None, "invalid", 0, "invalid_geometry")

    normalized_fill = normalize_utc(filled_at)[0]
    expires_at = normalized_fill + max_holding
    selected: list[Candle] = []
    for candle in future_candles:
        closed_at = candle_close_time(candle, execution_timeframe)
        if closed_at <= normalized_fill:
            continue
        if closed_at > expires_at:
            break
        selected.append(candle)

    if not selected:
        return ExitResolution(None, None, "open", 0, "no_post_fill_data")

    for holding_bars, candle in enumerate(selected, start=1):
        closed_at = candle_close_time(candle, execution_timeframe)
        gap_result = _gap_exit(
            normalized_side,
            candle,
            stop_loss,
            take_profit,
        )
        if gap_result is not None:
            price, outcome, reason = gap_result
            return ExitResolution(
                normalize_utc(candle.time)[0],
                price,
                outcome,
                holding_bars,
                reason,
            )

        if normalized_side == "buy":
            stop_hit = candle.low <= stop_loss
            target_hit = candle.high >= take_profit
        else:
            stop_hit = candle.high >= stop_loss
            target_hit = candle.low <= take_profit

        if stop_hit and target_hit:
            if policy == SAME_BAR_STOP_FIRST:
                return ExitResolution(
                    closed_at,
                    stop_loss,
                    "loss",
                    holding_bars,
                    "same_bar_stop_first",
                )
            return ExitResolution(
                closed_at,
                take_profit,
                "win",
                holding_bars,
                "same_bar_target_first",
            )
        if stop_hit:
            return ExitResolution(
                closed_at,
                stop_loss,
                "loss",
                holding_bars,
                "stop_loss",
            )
        if target_hit:
            return ExitResolution(
                closed_at,
                take_profit,
                "win",
                holding_bars,
                "take_profit",
            )

    last = selected[-1]
    return ExitResolution(
        candle_close_time(last, execution_timeframe),
        float(last.close),
        "expired",
        len(selected),
        "max_holding_expired",
    )


def build_execution_events(
    *,
    signal_time: datetime,
    setup_expires_at: datetime,
    fill: EntryFill,
    exit_resolution: ExitResolution,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = [
        {
            "event": "SIGNAL_DETECTED",
            "time": normalize_utc(signal_time)[0].isoformat(),
        },
        {
            "event": "SETUP_ACTIVATED",
            "time": normalize_utc(signal_time)[0].isoformat(),
            "expires_at": normalize_utc(setup_expires_at)[0].isoformat(),
        },
        {
            "event": "ENTRY_CONFIRMED",
            "time": fill.filled_at.isoformat(),
            "reason": fill.reason,
        },
        {
            "event": "ENTRY_FILLED",
            "time": fill.filled_at.isoformat(),
            "price": round(fill.price, 8),
            "reason": fill.reason,
        },
    ]
    if exit_resolution.exited_at is not None:
        events.append(
            {
                "event": "EXIT_FILLED",
                "time": exit_resolution.exited_at.isoformat(),
                "price": (
                    round(exit_resolution.price, 8)
                    if exit_resolution.price is not None
                    else None
                ),
                "outcome": exit_resolution.outcome,
                "reason": exit_resolution.reason,
            }
        )
    else:
        events.append(
            {
                "event": "POSITION_OPEN",
                "time": fill.filled_at.isoformat(),
                "reason": exit_resolution.reason,
            }
        )
    return events


def valid_trade_geometry(
    side: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
) -> bool:
    if side == "buy":
        return stop_loss < entry_price < take_profit
    if side == "sell":
        return take_profit < entry_price < stop_loss
    return False


def _gap_exit(
    side: str,
    candle: Candle,
    stop_loss: float,
    take_profit: float,
) -> tuple[float, str, str] | None:
    opened_at = float(candle.open)
    if side == "buy":
        if opened_at <= stop_loss:
            return opened_at, "loss", "gap_through_stop"
        if opened_at >= take_profit:
            return opened_at, "win", "gap_through_target"
    else:
        if opened_at >= stop_loss:
            return opened_at, "loss", "gap_through_stop"
        if opened_at <= take_profit:
            return opened_at, "win", "gap_through_target"
    return None
