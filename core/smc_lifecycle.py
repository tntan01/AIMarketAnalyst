"""Canonical SMC zone lifecycle analysis.

The lifecycle starts only after a detector's departure candle has completed.
It is deliberately independent from the scanner interval so replay, backtest,
and live scans derive the same state from the same candle history.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Any

from core.market_models import Candle
from core.smc_models import ZoneVisit


_STALE_AFTER_BARS = {
    "D1": 20,
    "H4": 30,
    "H1": 50,
    "M30": 60,
    "M15": 80,
    "M5": 120,
}


@dataclass(frozen=True, slots=True)
class ZoneLifecycle:
    departure_end_index: int
    first_retest_index: int | None
    first_retest_time: str | None
    independent_retest_count: int
    bars_spent_inside: int
    mitigation_ratio: float | None
    age_bars: int
    age_minutes: int | None
    invalidation_index: int | None
    invalidated_at: str | None
    lifecycle_mitigated: bool
    lifecycle_broken: bool
    lifecycle_stale: bool
    visits: tuple[ZoneVisit, ...]

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["visits"] = [visit.to_dict() for visit in self.visits]
        return payload


def analyze_zone_lifecycle(
    *,
    candles: list[Candle],
    low: float,
    high: float,
    side: str,
    origin_index: int,
    departure_end_index: int,
    zone_id: str,
    timeframe: str = "",
    tf_minutes: int = 60,
) -> ZoneLifecycle:
    """Derive visits, mitigation, invalidation, and age for one SMC zone.

    A visit is one complete ``outside -> inside -> outside`` transition.
    Consecutive overlapping candles belong to the same visit. The first candle
    eligible for a retest is always ``departure_end_index + 1``.
    """

    normalized_side = str(side or "").strip().lower()
    if normalized_side not in {"buy", "sell"}:
        raise ValueError(f"Invalid lifecycle side: {side}")

    zone_low, zone_high = sorted((_finite_float(low), _finite_float(high)))
    safe_origin = _bounded_index(origin_index, candles)
    safe_departure = max(safe_origin, _bounded_index(departure_end_index, candles))
    first_eligible = safe_departure + 1

    visits: list[ZoneVisit] = []
    active_start: int | None = None
    active_entered_at: str | None = None
    active_penetration = 0.0
    bars_spent_inside = 0
    first_retest_index: int | None = None
    first_retest_time: str | None = None
    invalidation_index: int | None = None
    invalidated_at: str | None = None
    max_mitigation: float | None = None

    for index in range(first_eligible, len(candles)):
        candle = candles[index]
        inside = _overlaps(candle, zone_low, zone_high)

        if inside:
            penetration = _penetration_ratio(
                candle,
                zone_low,
                zone_high,
                normalized_side,
            )
            bars_spent_inside += 1
            if active_start is None:
                active_start = index
                active_entered_at = candle.time.isoformat()
                active_penetration = penetration
                if first_retest_index is None:
                    first_retest_index = index
                    first_retest_time = active_entered_at
            else:
                active_penetration = max(active_penetration, penetration)
            max_mitigation = (
                penetration
                if max_mitigation is None
                else max(max_mitigation, penetration)
            )
        elif active_start is not None:
            visits.append(
                _visit(
                    zone_id=zone_id,
                    number=len(visits) + 1,
                    entered_at=active_entered_at,
                    exited_at=candle.time.isoformat(),
                    start_index=active_start,
                    end_index=index - 1,
                    penetration=active_penetration,
                )
            )
            active_start = None
            active_entered_at = None
            active_penetration = 0.0

        if _invalidates(candle, zone_low, zone_high, normalized_side):
            invalidation_index = index
            invalidated_at = candle.time.isoformat()
            if active_start is not None:
                visits.append(
                    _visit(
                        zone_id=zone_id,
                        number=len(visits) + 1,
                        entered_at=active_entered_at,
                        exited_at=invalidated_at,
                        start_index=active_start,
                        end_index=index,
                        penetration=active_penetration,
                    )
                )
                active_start = None
            break

    if active_start is not None:
        visits.append(
            _visit(
                zone_id=zone_id,
                number=len(visits) + 1,
                entered_at=active_entered_at,
                exited_at=None,
                start_index=active_start,
                end_index=None,
                penetration=active_penetration,
            )
        )

    age_bars = max(0, len(candles) - 1 - safe_origin) if candles else 0
    age_minutes = _age_minutes(candles, safe_origin)
    stale_threshold = stale_after_bars(timeframe, tf_minutes)

    return ZoneLifecycle(
        departure_end_index=safe_departure,
        first_retest_index=first_retest_index,
        first_retest_time=first_retest_time,
        independent_retest_count=len(visits),
        bars_spent_inside=bars_spent_inside,
        mitigation_ratio=(
            round(max_mitigation, 6)
            if max_mitigation is not None
            else None
        ),
        age_bars=age_bars,
        age_minutes=age_minutes,
        invalidation_index=invalidation_index,
        invalidated_at=invalidated_at,
        lifecycle_mitigated=bool(visits),
        lifecycle_broken=invalidation_index is not None,
        lifecycle_stale=age_bars > stale_threshold,
        visits=tuple(visits),
    )


def stale_after_bars(timeframe: str, tf_minutes: int) -> int:
    """Return the provisional v2 stale threshold, expressed only in bars."""

    normalized = str(timeframe or "").strip().upper()
    if normalized in _STALE_AFTER_BARS:
        return _STALE_AFTER_BARS[normalized]
    minutes = max(1, int(tf_minutes or 1))
    if minutes >= 1440:
        return _STALE_AFTER_BARS["D1"]
    if minutes >= 240:
        return _STALE_AFTER_BARS["H4"]
    if minutes >= 60:
        return _STALE_AFTER_BARS["H1"]
    if minutes >= 30:
        return _STALE_AFTER_BARS["M30"]
    if minutes >= 15:
        return _STALE_AFTER_BARS["M15"]
    return _STALE_AFTER_BARS["M5"]


def _visit(
    *,
    zone_id: str,
    number: int,
    entered_at: str | None,
    exited_at: str | None,
    start_index: int,
    end_index: int | None,
    penetration: float,
) -> ZoneVisit:
    return ZoneVisit(
        visit_id=f"{zone_id}:visit-{number}",
        entered_at=entered_at,
        exited_at=exited_at,
        start_index=start_index,
        end_index=end_index,
        max_penetration_ratio=round(penetration, 6),
    )


def _overlaps(candle: Candle, low: float, high: float) -> bool:
    return candle.low <= high and candle.high >= low


def _invalidates(candle: Candle, low: float, high: float, side: str) -> bool:
    return candle.close < low if side == "buy" else candle.close > high


def _penetration_ratio(
    candle: Candle,
    low: float,
    high: float,
    side: str,
) -> float:
    width = high - low
    if width <= 0:
        return 1.0
    if side == "buy":
        deepest = min(high, max(low, candle.low))
        ratio = (high - deepest) / width
    else:
        deepest = min(high, max(low, candle.high))
        ratio = (deepest - low) / width
    return max(0.0, min(1.0, ratio))


def _bounded_index(index: int, candles: list[Candle]) -> int:
    if not candles:
        return max(0, int(index))
    return max(0, min(int(index), len(candles) - 1))


def _age_minutes(candles: list[Candle], origin_index: int) -> int | None:
    if not candles:
        return None
    try:
        delta = candles[-1].time - candles[origin_index].time
    except (IndexError, TypeError):
        return None
    return max(0, int(delta.total_seconds() // 60))


def _finite_float(value: object) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"Invalid zone boundary: {value}") from error
    if not isfinite(result):
        raise ValueError(f"Invalid zone boundary: {value}")
    return result
