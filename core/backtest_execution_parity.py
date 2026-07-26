"""Deterministic MT5-like execution and transaction-cost model for backtest."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
from math import floor
from typing import Any, Iterable

from core.backtest_market_data import candle_close_time, normalize_utc
from core.market_models import Candle


EXECUTION_MODE_RESEARCH = "RESEARCH"
EXECUTION_MODE_PARITY = "EXECUTION_PARITY"
VALID_EXECUTION_MODES = frozenset({
    EXECUTION_MODE_RESEARCH,
    EXECUTION_MODE_PARITY,
})

EXECUTION_PARITY_MODEL_VERSION = "backtest-execution-parity-v1"
EXECUTION_COST_MODEL_VERSION = "backtest-cost-model-v1"
QUOTE_CONVERSION_MODEL_VERSION = "point-in-time-close-v1"

DEFAULT_SESSION_SPREAD_MULTIPLIERS: dict[str, float] = {
    "ASIA": 1.15,
    "LONDON": 1.0,
    "OVERLAP": 0.9,
    "NEW_YORK": 1.0,
    "OFF_HOURS": 1.35,
}


@dataclass(frozen=True, slots=True)
class PositionSize:
    raw_lot: float
    lot: float
    target_risk_account: float
    planned_risk_account: float
    contract_size: float
    quote_to_account_rate: float
    capped_by_minimum: bool
    capped_by_maximum: bool


@dataclass(frozen=True, slots=True)
class ExecutionCostResult:
    raw_entry_price: float
    raw_exit_price: float
    entry_price: float
    exit_price: float
    entry_spread_price: float
    exit_spread_price: float
    entry_slippage_price: float
    exit_slippage_price: float
    commission_account: float
    swap_account: float
    spread_slippage_account: float
    gross_pnl_account: float
    net_pnl_account: float
    gross_r: float
    cost_r: float
    net_r: float
    rollover_units: int
    session: str
    position: PositionSize


def normalize_execution_mode(value: object) -> str:
    return str(value or "").strip().upper()


def market_session(moment: datetime) -> str:
    """Return a stable UTC session bucket used by the spread model."""

    hour = normalize_utc(moment)[0].hour
    if 0 <= hour < 7:
        return "ASIA"
    if 7 <= hour < 13:
        return "LONDON"
    if 13 <= hour < 16:
        return "OVERLAP"
    if 16 <= hour < 21:
        return "NEW_YORK"
    return "OFF_HOURS"


def session_spread_price(
    base_spread_price: float,
    moment: datetime,
    multipliers: dict[str, float] | None = None,
) -> tuple[float, str]:
    session = market_session(moment)
    configured = dict(DEFAULT_SESSION_SPREAD_MULTIPLIERS)
    if isinstance(multipliers, dict):
        for key, value in multipliers.items():
            try:
                configured[str(key).upper()] = max(0.0, float(value))
            except (TypeError, ValueError):
                continue
    return (
        max(0.0, float(base_spread_price or 0.0))
        * configured.get(session, 1.0),
        session,
    )


def quote_rate_at(
    candles: Iterable[Candle] | None,
    moment: datetime,
    *,
    inverted: bool = False,
    timeframe: str = "H1",
    fallback_rate: float | None = None,
) -> float | None:
    """Use only a conversion candle that had closed by *moment*."""

    selected: Candle | None = None
    normalized_moment = normalize_utc(moment)[0]
    for candle in candles or ():
        if candle_close_time(candle, timeframe) > normalized_moment:
            continue
        if selected is None or normalize_utc(candle.time)[0] > normalize_utc(selected.time)[0]:
            selected = candle
    if selected is None:
        return _positive_or_none(fallback_rate)
    value = _positive_or_none(selected.close)
    if value is None:
        return _positive_or_none(fallback_rate)
    return 1.0 / value if inverted else value


def size_position(
    *,
    balance: float,
    risk_percent: float,
    entry_price: float,
    stop_loss: float,
    contract_size: float,
    quote_to_account_rate: float,
    lot_step: float,
    minimum_lot: float,
    maximum_lot: float,
) -> PositionSize:
    target = max(0.0, float(balance)) * max(0.0, float(risk_percent)) / 100.0
    distance = abs(float(entry_price) - float(stop_loss))
    contract = max(0.0, float(contract_size))
    conversion = max(0.0, float(quote_to_account_rate))
    loss_per_lot = distance * contract * conversion
    raw = target / loss_per_lot if loss_per_lot > 0 else 0.0
    step = max(float(lot_step or 0.01), 1e-12)
    minimum = max(0.0, float(minimum_lot or 0.0))
    maximum = max(minimum, float(maximum_lot or minimum))
    floored = floor(raw / step + 1e-9) * step if raw > 0 else 0.0
    lot = min(maximum, max(minimum, floored)) if raw > 0 else 0.0
    precision = _step_precision(step)
    lot = round(lot, precision)
    return PositionSize(
        raw_lot=round(raw, 8),
        lot=lot,
        target_risk_account=round(target, 8),
        planned_risk_account=round(loss_per_lot * lot, 8),
        contract_size=contract,
        quote_to_account_rate=conversion,
        capped_by_minimum=bool(raw > 0 and floored < minimum),
        capped_by_maximum=bool(raw > maximum),
    )


def apply_execution_costs(
    *,
    side: str,
    raw_entry_price: float,
    raw_exit_price: float,
    stop_loss: float,
    entry_time: datetime,
    exit_time: datetime,
    balance: float,
    risk_percent: float,
    contract_size: float,
    quote_rate_entry: float,
    quote_rate_exit: float,
    lot_step: float,
    minimum_lot: float,
    maximum_lot: float,
    base_spread_price: float,
    spread_session_multipliers: dict[str, float] | None,
    entry_slippage_price: float,
    exit_slippage_price: float,
    commission_per_lot_round_turn: float,
    swap_long_per_lot_day: float,
    swap_short_per_lot_day: float,
    triple_swap_weekday: int = 2,
) -> ExecutionCostResult:
    """Apply bid/ask, adverse slippage, commission and rollover swap.

    Historical OHLC is treated as Bid data, matching MT5 chart semantics:
    BUY opens on Ask and closes on Bid; SELL opens on Bid and closes on Ask.
    """

    normalized_side = str(side or "").lower()
    if normalized_side not in {"buy", "sell"}:
        raise ValueError(f"Hướng giao dịch không hỗ trợ: {side}")
    spread_entry, session = session_spread_price(
        base_spread_price,
        entry_time,
        spread_session_multipliers,
    )
    spread_exit, _exit_session = session_spread_price(
        base_spread_price,
        exit_time,
        spread_session_multipliers,
    )
    entry_slippage = max(0.0, float(entry_slippage_price or 0.0))
    exit_slippage = max(0.0, float(exit_slippage_price or 0.0))
    if normalized_side == "buy":
        entry_price = float(raw_entry_price) + spread_entry + entry_slippage
        exit_price = float(raw_exit_price) - exit_slippage
    else:
        entry_price = float(raw_entry_price) - entry_slippage
        exit_price = float(raw_exit_price) + spread_exit + exit_slippage

    position = size_position(
        balance=balance,
        risk_percent=risk_percent,
        entry_price=entry_price,
        stop_loss=stop_loss,
        contract_size=contract_size,
        quote_to_account_rate=quote_rate_entry,
        lot_step=lot_step,
        minimum_lot=minimum_lot,
        maximum_lot=maximum_lot,
    )
    units = position.lot * position.contract_size
    direction = 1.0 if normalized_side == "buy" else -1.0
    gross_pnl = (
        direction
        * (float(raw_exit_price) - float(raw_entry_price))
        * units
        * float(quote_rate_exit)
    )
    execution_pnl = (
        direction
        * (exit_price - entry_price)
        * units
        * float(quote_rate_exit)
    )
    spread_slippage_cost = max(0.0, gross_pnl - execution_pnl)
    commission = max(0.0, float(commission_per_lot_round_turn or 0.0)) * position.lot
    rollover_units = count_rollover_units(
        entry_time,
        exit_time,
        triple_swap_weekday=triple_swap_weekday,
    )
    swap_rate = (
        swap_long_per_lot_day
        if normalized_side == "buy"
        else swap_short_per_lot_day
    )
    swap = max(0.0, float(swap_rate or 0.0)) * position.lot * rollover_units
    net_pnl = execution_pnl - commission - swap
    denominator = position.planned_risk_account
    gross_r = gross_pnl / denominator if denominator > 0 else 0.0
    net_r = net_pnl / denominator if denominator > 0 else 0.0
    cost_r = gross_r - net_r
    return ExecutionCostResult(
        raw_entry_price=float(raw_entry_price),
        raw_exit_price=float(raw_exit_price),
        entry_price=entry_price,
        exit_price=exit_price,
        entry_spread_price=spread_entry if normalized_side == "buy" else 0.0,
        exit_spread_price=spread_exit if normalized_side == "sell" else 0.0,
        entry_slippage_price=entry_slippage,
        exit_slippage_price=exit_slippage,
        commission_account=round(commission, 8),
        swap_account=round(swap, 8),
        spread_slippage_account=round(spread_slippage_cost, 8),
        gross_pnl_account=round(gross_pnl, 8),
        net_pnl_account=round(net_pnl, 8),
        gross_r=round(gross_r, 6),
        cost_r=round(cost_r, 6),
        net_r=round(net_r, 6),
        rollover_units=rollover_units,
        session=session,
        position=position,
    )


def count_rollover_units(
    entry_time: datetime,
    exit_time: datetime,
    *,
    rollover_hour_utc: int = 21,
    triple_swap_weekday: int = 2,
) -> int:
    """Count broker rollover charges; Wednesday defaults to triple swap."""

    start = normalize_utc(entry_time)[0]
    end = normalize_utc(exit_time)[0]
    if end <= start:
        return 0
    cursor = start.replace(
        hour=rollover_hour_utc,
        minute=0,
        second=0,
        microsecond=0,
    )
    if cursor <= start:
        cursor += timedelta(days=1)
    total = 0
    while cursor <= end:
        if cursor.weekday() < 5:
            total += 3 if cursor.weekday() == triple_swap_weekday else 1
        cursor += timedelta(days=1)
    return total


def cost_model_manifest(config: Any) -> dict[str, Any]:
    """Return immutable, JSON-safe settings used by one replay."""

    return {
        "execution_model_version": EXECUTION_PARITY_MODEL_VERSION,
        "cost_model_version": EXECUTION_COST_MODEL_VERSION,
        "quote_conversion_model_version": QUOTE_CONVERSION_MODEL_VERSION,
        "ohlc_price_side": "BID",
        "spread_model": "symbol_base_x_utc_session",
        "base_spread_price": float(getattr(config, "spread_price", 0.0) or 0.0),
        "spread_session_multipliers": dict(
            getattr(config, "spread_session_multipliers", None)
            or DEFAULT_SESSION_SPREAD_MULTIPLIERS
        ),
        "entry_slippage_price": float(
            getattr(config, "entry_slippage_price", None)
            if getattr(config, "entry_slippage_price", None) is not None
            else getattr(config, "slippage_price", 0.0)
        ),
        "exit_slippage_price": float(
            getattr(config, "exit_slippage_price", None)
            if getattr(config, "exit_slippage_price", None) is not None
            else getattr(config, "slippage_price", 0.0)
        ),
        "commission_per_lot_round_turn": float(
            getattr(config, "commission_per_lot_round_turn", 0.0) or 0.0
        ),
        "swap_long_per_lot_day": float(
            getattr(config, "swap_long_per_lot_day", 0.0) or 0.0
        ),
        "swap_short_per_lot_day": float(
            getattr(config, "swap_short_per_lot_day", 0.0) or 0.0
        ),
        "lot_step": float(getattr(config, "lot_step", 0.01) or 0.01),
        "minimum_lot": float(getattr(config, "minimum_lot", 0.01) or 0.01),
        "maximum_lot": float(getattr(config, "maximum_lot", 100.0) or 100.0),
        "contract_size": float(
            getattr(config, "contract_size_override", 0.0) or 0.0
        ),
        "configured": bool(getattr(config, "cost_model_configured", False)),
    }


def cost_model_fingerprint(config: Any) -> str:
    payload = cost_model_manifest(config)
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def quote_conversion_fingerprint(config: Any) -> str:
    candles = getattr(config, "quote_conversion_candles", ()) or ()
    payload = {
        "model_version": QUOTE_CONVERSION_MODEL_VERSION,
        "symbol": str(getattr(config, "quote_conversion_symbol", "") or ""),
        "inverted": bool(
            getattr(config, "quote_conversion_inverted", False)
        ),
        "fallback_rate": getattr(config, "quote_to_account_rate", None),
        "candles": [
            [
                normalize_utc(candle.time)[0].isoformat(),
                candle.open,
                candle.high,
                candle.low,
                candle.close,
            ]
            for candle in candles
            if isinstance(candle, Candle)
        ],
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _positive_or_none(value: object) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _step_precision(step: float) -> int:
    text = f"{step:.10f}".rstrip("0")
    return len(text.split(".", 1)[1]) if "." in text else 0
