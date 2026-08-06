"""M15 entry confirmation for the selected SMC zone.

After the canonical H4/H1 zone is selected, the recent M15 window is
checked for confirmation at that zone: a small-timeframe CHoCH-like
structure shift in the trade direction (higher low for buy / lower high
for sell) or a clear price reaction (rejection wick at the zone or a
displacement candle away from it).  A zone that was tested without any
confirmation subtracts points from the setup score; every outcome maps
to a reason code so the step is never skipped silently.  The evaluator
is asymmetric: a confirmation only traces a reason code and never adds
points.
"""

from __future__ import annotations

from math import isfinite
from typing import Any

from core.indicators import atr


# Reason codes traced on the side breakdown for every M15 outcome.
M15_CONFIRMATION_REASON = "M15_CONFIRMATION"
M15_NO_CONFIRMATION_REASON = "M15_NO_CONFIRMATION"
M15_INSUFFICIENT_DATA_REASON = "M15_INSUFFICIENT_DATA"
M15_ZONE_NOT_TESTED_REASON = "M15_ZONE_NOT_TESTED"

# Statuses returned by the evaluator.
M15_CONFIRMED = "confirmed"
M15_NOT_CONFIRMED = "not_confirmed"
M15_ZONE_NOT_TESTED = "zone_not_tested"
M15_INSUFFICIENT_DATA = "insufficient_data"

# A tested zone without M15 confirmation lowers the setup score, mirroring
# the other asymmetric scorer penalties.
_M15_NO_CONFIRMATION_PENALTY = 2

_M15_MIN_CANDLES = 15               # min candles for the ATR-based checks
_M15_LOOKBACK_CANDLES = 48          # only the last 12h can confirm the zone
_M15_SWING_LOOKBACK = 3             # fractal pivot width for the micro CHoCH
_M15_MIN_STRUCTURE_CANDLES = 12     # min candles after the touch for a CHoCH
_M15_REJECTION_BODY_RATIO = 0.8     # same contract as the H1 rejection check
_M15_REJECTION_RANGE_RATIO = 0.25
_M15_DISPLACEMENT_ATR_RATIO = 0.3
_M15_ATR_PERIOD = 14
_M15_DISPLACEMENT_WINDOW = 3


def evaluate_m15_confirmation(
    side: str,
    zone_low: float,
    zone_high: float,
    m15_candles: list[Any] | None,
) -> dict[str, Any]:
    """Evaluate M15 confirmation at the selected zone for one side.

    Returns a dict with ``status`` (``confirmed`` / ``not_confirmed`` /
    ``zone_not_tested`` / ``insufficient_data``), ``confirmed``,
    ``penalty`` and ``reason_codes``.  Only a tested-but-unconfirmed zone
    carries a penalty; every status maps to at least one reason code so
    the step is never skipped silently.
    """

    if side not in {"buy", "sell"}:
        return _result(M15_INSUFFICIENT_DATA, 0, [M15_INSUFFICIENT_DATA_REASON])
    if (
        not isinstance(m15_candles, (list, tuple))
        or len(m15_candles) < _M15_MIN_CANDLES
    ):
        return _result(M15_INSUFFICIENT_DATA, 0, [M15_INSUFFICIENT_DATA_REASON])
    low = _finite(zone_low)
    high = _finite(zone_high)
    if low is None or high is None or high <= low:
        return _result(M15_INSUFFICIENT_DATA, 0, [M15_INSUFFICIENT_DATA_REASON])

    candles = list(m15_candles)[-_M15_LOOKBACK_CANDLES:]
    touch_index = None
    for index, candle in enumerate(candles):
        if candle.low <= high and candle.high >= low:
            touch_index = index
            break
    if touch_index is None:
        return _result(M15_ZONE_NOT_TESTED, 0, [M15_ZONE_NOT_TESTED_REASON])

    choch = _m15_choch(candles[touch_index:], side)
    reaction = _m15_price_reaction(candles, touch_index, side, low, high)
    if choch or reaction:
        return _result(
            M15_CONFIRMED,
            0,
            [M15_CONFIRMATION_REASON],
            choch=choch,
            reaction=reaction,
        )
    return _result(
        M15_NOT_CONFIRMED,
        _M15_NO_CONFIRMATION_PENALTY,
        [M15_NO_CONFIRMATION_REASON],
        choch=False,
        reaction=False,
    )


def _m15_choch(candles: list[Any], side: str) -> bool:
    """Small-timeframe CHoCH after the zone touch.

    A structure shift in the trade direction: the last two M15 swing lows
    form a higher low (buy) or the last two swing highs form a lower high
    (sell), mirroring the entry engine's M15 structure contract.
    """

    if len(candles) < _M15_MIN_STRUCTURE_CANDLES:
        return False
    highs, lows = _m15_swings(candles)
    if side == "buy":
        return len(lows) >= 2 and lows[-1] > lows[-2]
    return len(highs) >= 2 and highs[-1] < highs[-2]


def _m15_swings(
    candles: list[Any],
    lookback: int = _M15_SWING_LOOKBACK,
) -> tuple[list[float], list[float]]:
    highs: list[float] = []
    lows: list[float] = []
    for i in range(lookback, len(candles) - lookback):
        window = candles[i - lookback : i + lookback + 1]
        candle = candles[i]
        if (
            candle.high == max(item.high for item in window)
            and sum(1 for item in window if item.high == candle.high) == 1
        ):
            highs.append(candle.high)
        if (
            candle.low == min(item.low for item in window)
            and sum(1 for item in window if item.low == candle.low) == 1
        ):
            lows.append(candle.low)
    return highs, lows


def _m15_price_reaction(
    candles: list[Any],
    touch_index: int,
    side: str,
    zone_low: float,
    zone_high: float,
) -> bool:
    """Clear price reaction at the zone: rejection wick or displacement."""

    for candle in candles[touch_index:]:
        if _m15_rejection(candle, side, zone_low, zone_high):
            return True
    return _m15_displacement(candles, touch_index, side)


def _m15_rejection(
    candle: Any,
    side: str,
    zone_low: float,
    zone_high: float,
) -> bool:
    if not (candle.low <= zone_high and candle.high >= zone_low):
        return False
    candle_range = candle.high - candle.low
    if candle_range <= 0:
        return False
    body = abs(candle.close - candle.open)
    threshold = max(
        body * _M15_REJECTION_BODY_RATIO,
        candle_range * _M15_REJECTION_RANGE_RATIO,
    )
    if side == "buy":
        lower_wick = min(candle.open, candle.close) - candle.low
        return candle.close > candle.open and lower_wick >= threshold
    upper_wick = candle.high - max(candle.open, candle.close)
    return candle.close < candle.open and upper_wick >= threshold


def _m15_displacement(candles: list[Any], touch_index: int, side: str) -> bool:
    highs = [candle.high for candle in candles]
    lows = [candle.low for candle in candles]
    closes = [candle.close for candle in candles]
    atr_values = atr(highs, lows, closes, _M15_ATR_PERIOD)
    atr_now = atr_values[-1] if atr_values and atr_values[-1] is not None else 0.0
    if atr_now <= 0:
        return False
    threshold = _M15_DISPLACEMENT_ATR_RATIO * atr_now
    recent_start = max(touch_index, len(candles) - _M15_DISPLACEMENT_WINDOW)
    for candle in candles[recent_start:]:
        body = abs(candle.close - candle.open)
        if body < threshold:
            continue
        if side == "buy" and candle.close > candle.open:
            return True
        if side == "sell" and candle.close < candle.open:
            return True
    return False


def _result(
    status: str,
    penalty: int,
    reason_codes: list[str],
    *,
    choch: bool = False,
    reaction: bool = False,
) -> dict[str, Any]:
    return {
        "status": status,
        "confirmed": status == M15_CONFIRMED,
        "penalty": penalty,
        "reason_codes": list(reason_codes),
        "choch": choch,
        "reaction": reaction,
    }


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None
