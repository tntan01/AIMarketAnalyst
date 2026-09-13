"""Canonical SMC zone lifecycle analysis.

The lifecycle starts only after a detector's departure candle has completed.
It is deliberately independent from the scanner interval so replay, backtest,
and live scans derive the same state from the same candle history.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Sequence

from core.market_models import Candle
from core.market_models import SMC_TIMEFRAME_INTERVALS, candle_close_at
from core.smc_models import ZoneVisit


_STALE_AFTER_BARS = {
    "D1": 20,
    "H4": 30,
    "H1": 50,
    "M30": 60,
    "M15": 80,
    "M5": 120,
}

# Data-quality reasons (A3-007 contract). These describe why a rule that depends on
# metadata cannot be computed; they are never lifecycle statuses.
SMC_METADATA_ATR_UNAVAILABLE = "SMC_METADATA_ATR_UNAVAILABLE"
SMC_METADATA_TICK_UNAVAILABLE = "SMC_METADATA_TICK_UNAVAILABLE"
SMC_METADATA_NONFINITE = "SMC_METADATA_NONFINITE"
SMC_METADATA_SOURCE_CONFLICT = "SMC_METADATA_SOURCE_CONFLICT"

METADATA_AVAILABLE = "available"
METADATA_UNKNOWN = "unknown"


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
    invalidation_buffer: float | None = None
    expiry_index: int | None = None
    expired_at: str | None = None
    lifecycle_expired: bool = False
    age_score: float = 1.0
    metadata_state: str = METADATA_AVAILABLE
    metadata_reason: str | None = None
    tick_size_source: str | None = None
    atr_source: str | None = None

    @property
    def dwell_bars(self) -> int:
        """Dwell of the current/last causal visit, not the zone total."""

        return self.visits[-1].bars_spent_inside if self.visits else 0

    @property
    def current_dwell_bars(self) -> int:
        """Explicit alias separating current dwell from total overlap bars."""

        return self.dwell_bars

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
    available_at: datetime | str | None = None,
    tick_size: float | None = None,
    atr_current: float | None = None,
    zone_tolerance: float | None = None,
    break_buffer: float | None = None,
    tick_conflict: bool = False,
    tick_size_source: str | None = None,
    atr_source: str | None = None,
    declared_terminal_status: str | None = None,
    declared_invalidated_at: str | None = None,
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
    normalized_timeframe = _timeframe_for(timeframe, tf_minutes)
    available_boundary = _parse_utc_timestamp(available_at, "available_at") if available_at is not None else None
    tolerance, tolerance_reason = _resolve_zone_tolerance(
        tick_size=tick_size,
        atr_current=atr_current,
        explicit=zone_tolerance,
        conflict=tick_conflict,
    )
    resolved_break_buffer, buffer_reason = _resolve_break_buffer(
        tick_size=tick_size,
        atr_current=atr_current,
        explicit=break_buffer,
        conflict=tick_conflict,
    )
    # A rule that cannot be computed from the declared metadata is a data-quality state:
    # it lowers usability and never fabricates a threshold, but it does not touch the
    # lifecycle status (A3-007). Unknown is not invalid.
    metadata_reason = buffer_reason or tolerance_reason
    metadata_state = METADATA_UNKNOWN if metadata_reason is not None else METADATA_AVAILABLE
    if tolerance is None:
        # No computable overlap rule: fall back to the un-widened zone for overlap only,
        # which cannot invalidate anything on its own.
        tolerance = 0.0
    # Threshold used for the invalidation *decision*. It stays `None` whenever the metadata
    # cannot compute the buffer, so the buffered rule never fires on a fabricated zero (B-R2).
    # A payload that already declares `invalid` still owns its terminal state; that is applied
    # through the declared-invalidation path after the loop, never by inventing a threshold.
    invalidation_threshold = resolved_break_buffer
    declared_invalid = (
        invalidation_threshold is None
        and str(declared_terminal_status or "").strip().lower() == "invalid"
    )

    visits: list[ZoneVisit] = []
    active_start: int | None = None
    active_entered_at: str | None = None
    active_penetration = 0.0
    active_bars_spent_inside = 0
    bars_spent_inside = 0
    first_retest_index: int | None = None
    first_retest_time: str | None = None
    invalidation_index: int | None = None
    invalidated_at: str | None = None
    max_mitigation: float | None = None
    age_anchor_index = _age_anchor_index(
        candles,
        safe_origin=safe_origin,
        available_at=available_boundary,
        timeframe=normalized_timeframe,
    )
    expiry_index: int | None = None
    expired_at: str | None = None
    age_at_index = 0
    lifetime_boundary = _expiry_boundary_index(
        candles,
        first_eligible=first_eligible,
        age_anchor_index=age_anchor_index,
        available_boundary=available_boundary,
        normalized_timeframe=normalized_timeframe,
        lifetime=stale_after_bars(timeframe, tf_minutes),
    )

    for index in range(first_eligible, len(candles)):
        candle = candles[index]
        candle_close = _candle_close(candle, normalized_timeframe)
        if available_boundary is not None and candle_close < available_boundary:
            continue
        age_at_index = max(0, index - age_anchor_index)
        invalidates_on_candle = _invalidates(
            candle,
            zone_low,
            zone_high,
            normalized_side,
            buffer=invalidation_threshold,
        )
        if age_at_index > stale_after_bars(timeframe, tf_minutes) and not invalidates_on_candle:
            expiry_index = index
            expired_at = candle_close.isoformat()
            break
        inside = _overlaps(candle, zone_low, zone_high, tolerance=tolerance)

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
                active_entered_at = candle_close.isoformat()
                active_penetration = penetration
                active_bars_spent_inside = 1
                if first_retest_index is None:
                    first_retest_index = index
                    first_retest_time = active_entered_at
            else:
                active_penetration = max(active_penetration, penetration)
                active_bars_spent_inside += 1
            max_mitigation = (
                penetration
                if max_mitigation is None
                else max(max_mitigation, penetration)
            )
        elif active_start is not None:
            invalidated_on_exit = _invalidates(
                candle,
                zone_low,
                zone_high,
                normalized_side,
                buffer=invalidation_threshold,
            )
            reaction_at = (
                None
                if invalidated_on_exit
                else _follow_through_reaction_at(
                    candles=candles,
                    exit_index=index,
                    zone_low=zone_low,
                    zone_high=zone_high,
                    side=normalized_side,
                    timeframe=normalized_timeframe,
                    atr_current=atr_current,
                    break_buffer=invalidation_threshold,
                    terminal_index=lifetime_boundary,
                )
            )
            visits.append(
                _visit(
                    zone_id=zone_id,
                    number=len(visits) + 1,
                    entered_at=active_entered_at,
                    exited_at=candle_close.isoformat(),
                    start_index=active_start,
                    end_index=index - 1,
                    penetration=active_penetration,
                    bars_spent_inside=active_bars_spent_inside,
                    reacted_at=reaction_at,
                    visit_state=(
                        "closed_by_invalidation"
                        if invalidated_on_exit
                        else ""
                    ),
                )
            )
            active_start = None
            active_entered_at = None
            active_penetration = 0.0
            active_bars_spent_inside = 0

        if invalidates_on_candle:
            invalidation_index = index
            invalidated_at = candle_close.isoformat()
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
                        bars_spent_inside=active_bars_spent_inside,
                        visit_state="closed_by_invalidation",
                    )
                )
                active_start = None
            break

    if declared_invalid and active_start is not None:
        # The payload already declares this zone invalid and the metadata cannot recompute the
        # derivation, so the declared terminal owns the outcome: the visit that was still open
        # is closed by that declaration rather than by a fabricated threshold. Its own
        # timestamp is used when the payload carried one.
        declared_close = (
            _parse_utc_timestamp(declared_invalidated_at, "invalidated_at")
            if declared_invalidated_at is not None
            else None
        )
        close_at = (
            declared_close.isoformat()
            if declared_close is not None
            else _candle_close(candles[-1], normalized_timeframe).isoformat()
        )
        visits.append(
            _visit(
                zone_id=zone_id,
                number=len(visits) + 1,
                entered_at=active_entered_at,
                exited_at=close_at,
                start_index=active_start,
                end_index=len(candles) - 1,
                penetration=active_penetration,
                bars_spent_inside=active_bars_spent_inside,
                visit_state="closed_by_invalidation",
            )
        )
        invalidation_index = (
            invalidation_index if invalidation_index is not None else len(candles) - 1
        )
        invalidated_at = invalidated_at or close_at
        active_start = None

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
                bars_spent_inside=active_bars_spent_inside,
            )
        )

    age_bars = max(0, len(candles) - 1 - age_anchor_index) if candles else 0
    age_minutes = _age_minutes(candles, age_anchor_index)
    stale_threshold = stale_after_bars(timeframe, tf_minutes)
    lifecycle_expired = (
        expiry_index is not None
        or (age_bars > stale_threshold and invalidation_index is None)
    )
    if lifecycle_expired and expired_at is None and candles:
        expired_at = _candle_close(candles[-1], normalized_timeframe).isoformat()
    age_score = _age_decay_score(age_bars, stale_threshold)

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
        lifecycle_stale=lifecycle_expired,
        visits=tuple(visits),
        invalidation_buffer=resolved_break_buffer,
        expiry_index=expiry_index,
        expired_at=expired_at,
        lifecycle_expired=lifecycle_expired,
        age_score=age_score,
        metadata_state=metadata_state,
        metadata_reason=metadata_reason,
        tick_size_source=tick_size_source,
        atr_source=atr_source,
    )


def update_fvg_fill(
    zone: dict[str, Any],
    candles: Sequence[Candle],
    *,
    tick_size: float | None = None,
    timeframe: str = "",
    tf_minutes: int = 60,
    as_of: datetime | str | None = None,
) -> dict[str, Any]:
    """Update remaining FVG bounds from valid candles after formation.

    Original bounds and identity are never changed.  The directional gap is
    measured independently for bullish and bearish FVGs so partial fill does
    not reuse the generic OB/S-D mitigation rule.
    """

    if not isinstance(zone, dict):
        raise ValueError("FVG zone must be a mapping")
    result = dict(zone)
    family = str(result.get("family", "") or "").strip().lower()
    zone_type = str(result.get("zone_type", result.get("type", "")) or "").strip().lower()
    if family != "fvg" and "fvg" not in zone_type:
        return result

    original_payload = result.get("original_bounds")
    original_low = result.get("original_low")
    original_high = result.get("original_high")
    if isinstance(original_payload, dict):
        if original_low is None:
            original_low = original_payload.get("low")
        if original_high is None:
            original_high = original_payload.get("high")
    if original_low is None:
        original_low = result.get("low")
    if original_high is None:
        original_high = result.get("high")
    low = _finite_float(original_low)
    high = _finite_float(original_high)
    if high <= low:
        raise ValueError("FVG original bounds must have positive width")

    direction = str(result.get("direction", "") or "").strip().lower()
    if direction not in {"buy", "sell"}:
        direction = "buy" if "bullish" in zone_type else "sell" if "bearish" in zone_type else ""
    if direction not in {"buy", "sell"}:
        raise ValueError("FVG direction is required")

    normalized_timeframe = _timeframe_for(timeframe, tf_minutes)
    cutoff = _parse_utc_timestamp(as_of, "as_of") if as_of is not None else None
    formation_index = result.get(
        "formation_end_index",
        result.get("origin_index", result.get("index", -1)),
    )
    try:
        first_scan_index = int(formation_index) + 1
    except (TypeError, ValueError, OverflowError):
        raise ValueError("FVG formation index must be an integer") from None

    tick = 0.0
    if tick_size is not None:
        tick = _finite_float(tick_size)
        if tick <= 0:
            raise ValueError("tick_size must be positive")
    width = high - low
    if direction == "buy":
        lowest_low = min(
            [high]
            + [
                float(candle.low)
                for candle in candles[first_scan_index:]
                if isinstance(candle, Candle)
                and (cutoff is None or _candle_close(candle, normalized_timeframe) <= cutoff)
            ]
        )
        remaining_low = low
        remaining_high = max(low, min(high, lowest_low))
        filled_distance = high - remaining_high
    else:
        highest_high = max(
            [low]
            + [
                float(candle.high)
                for candle in candles[first_scan_index:]
                if isinstance(candle, Candle)
                and (cutoff is None or _candle_close(candle, normalized_timeframe) <= cutoff)
            ]
        )
        remaining_low = min(high, max(low, highest_high))
        remaining_high = high
        filled_distance = remaining_low - low

    remaining_width = max(0.0, remaining_high - remaining_low)
    fill_tolerance = max(tick, 0.05 * width)
    if remaining_width <= fill_tolerance:
        fill_status = "filled"
        fill_ratio = 1.0
    else:
        fill_status = "partially_filled" if filled_distance > 0 else "unfilled"
        fill_ratio = max(0.0, min(1.0, filled_distance / width))

    result.update(
        {
            "original_low": low,
            "original_high": high,
            "original_bounds": {"low": low, "high": high},
            "remaining_low": remaining_low,
            "remaining_high": remaining_high,
            "remaining_bounds": {
                "low": remaining_low,
                "high": remaining_high,
            },
            "fill_status": fill_status,
            "fill_ratio": round(fill_ratio, 6),
            "full_fill_tolerance": fill_tolerance,
        }
    )
    return result


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
    bars_spent_inside: int,
    reacted_at: str | None = None,
    visit_state: str = "",
) -> ZoneVisit:
    return ZoneVisit(
        visit_id=ZoneVisit.build_id(zone_id, number),
        zone_id=zone_id,
        entered_at=entered_at,
        exited_at=exited_at,
        start_index=start_index,
        end_index=end_index,
        max_penetration_ratio=round(penetration, 6),
        reacted_at=reacted_at,
        visit_state=visit_state,
        bars_spent_inside=bars_spent_inside,
    )


def _overlaps(candle: Candle, low: float, high: float, *, tolerance: float = 0.0) -> bool:
    return candle.low <= high + tolerance and candle.high >= low - tolerance


def _finite_metadata(value: object) -> tuple[float | None, str | None]:
    """Metadata values become data-quality state, never an exception (A3-007/A3-017).

    Returns ``(value, None)`` when finite, ``(None, None)`` when absent and
    ``(None, SMC_METADATA_NONFINITE)`` when present but unusable.
    """

    if value is None:
        return None, None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None, SMC_METADATA_NONFINITE
    if not isfinite(result):
        return None, SMC_METADATA_NONFINITE
    return result, None


def _resolve_threshold(
    *,
    tick_size: float | None,
    atr_current: float | None,
    explicit: float | None,
    conflict: bool,
    explicit_error: str,
) -> tuple[float | None, str | None]:
    """Resolve a metadata-dependent threshold, or say why it is unknown.

    An explicit override replaces only its own rule, so it is honoured before the
    metadata is inspected; a same-scope conflict is unknown even when both values
    were declared, and a missing source never becomes a zero threshold.
    """

    if conflict:
        return None, SMC_METADATA_SOURCE_CONFLICT
    if explicit is not None:
        value = float(explicit)
        if not isfinite(value) or value < 0:
            raise ValueError(explicit_error)
        return value, None

    tick, tick_reason = _finite_metadata(tick_size)
    atr_value, atr_reason = _finite_metadata(atr_current)
    nonfinite_reason = tick_reason or atr_reason
    if nonfinite_reason is not None:
        return None, nonfinite_reason
    if tick is None or atr_value is None:
        if tick is None and atr_value is None:
            return None, SMC_METADATA_TICK_UNAVAILABLE
        return None, (
            SMC_METADATA_TICK_UNAVAILABLE if tick is None else SMC_METADATA_ATR_UNAVAILABLE
        )
    if tick <= 0 or atr_value <= 0:
        raise ValueError("tick_size and atr_current must be positive")
    return max(tick, 0.05 * atr_value), None


def _resolve_zone_tolerance(
    *,
    tick_size: float | None,
    atr_current: float | None,
    explicit: float | None,
    conflict: bool = False,
) -> tuple[float | None, str | None]:
    return _resolve_threshold(
        tick_size=tick_size,
        atr_current=atr_current,
        explicit=explicit,
        conflict=conflict,
        explicit_error="zone_tolerance must be non-negative",
    )


def _resolve_break_buffer(
    *,
    tick_size: float | None,
    atr_current: float | None,
    explicit: float | None,
    conflict: bool = False,
) -> tuple[float | None, str | None]:
    return _resolve_threshold(
        tick_size=tick_size,
        atr_current=atr_current,
        explicit=explicit,
        conflict=conflict,
        explicit_error="break_buffer must be non-negative",
    )


def _expiry_boundary_index(
    candles: list[Candle],
    *,
    first_eligible: int,
    age_anchor_index: int,
    available_boundary: datetime | None,
    normalized_timeframe: str,
    lifetime: int,
) -> int | None:
    """First index whose age exceeds the published lifetime, or ``None``.

    The main loop stops there, so no reaction may be sourced from that candle or any later
    one (A-D05: expiry is evaluated before the reaction of the same candle). This uses the
    same age anchor and availability gate as the main loop, so the follow-through window and
    the lifecycle boundary cannot drift apart.
    """

    for index in range(first_eligible, len(candles)):
        candle_close = _candle_close(candles[index], normalized_timeframe)
        if available_boundary is not None and candle_close < available_boundary:
            continue
        if max(0, index - age_anchor_index) > lifetime:
            return index
    return None


def _timeframe_for(timeframe: str, tf_minutes: int) -> str:
    normalized = str(timeframe or "").strip().upper()
    if normalized in SMC_TIMEFRAME_INTERVALS:
        return normalized
    minutes = max(1, int(tf_minutes or 1))
    if minutes >= 1440:
        return "D1"
    if minutes >= 240:
        return "H4"
    if minutes >= 60:
        return "H1"
    if minutes >= 15:
        return "M15"
    return "M15"


def _age_anchor_index(
    candles: list[Candle],
    *,
    safe_origin: int,
    available_at: datetime | None,
    timeframe: str,
) -> int:
    if not candles:
        return 0
    if available_at is None:
        return safe_origin
    for index in range(max(0, safe_origin), len(candles)):
        if _candle_close(candles[index], timeframe) >= available_at:
            return index
    return len(candles) - 1


def _age_decay_score(age_bars: int, lifetime: int) -> float:
    if age_bars > lifetime:
        return 0.0
    if lifetime <= 0:
        return 0.0
    return round(max(0.25, 1.0 - 0.75 * age_bars / lifetime), 6)


def _candle_close(candle: Candle, timeframe: str) -> datetime:
    return candle_close_at(candle.time, timeframe).astimezone(timezone.utc)


def _parse_utc_timestamp(value: datetime | str, field_name: str) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        parse_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(parse_text)
        except ValueError:
            raise ValueError(f"{field_name} must be an ISO timestamp") from None
    else:
        raise ValueError(f"{field_name} must be a timezone-aware UTC timestamp")
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be timezone-aware UTC")
    return parsed.astimezone(timezone.utc)


def _invalidates(
    candle: Candle,
    low: float,
    high: float,
    side: str,
    *,
    buffer: float | None = 0.0,
) -> bool:
    # ``None`` means the threshold is not computable from the declared metadata, so the
    # buffered-invalidation rule cannot fire at all (A3-007: unknown never becomes broken).
    if buffer is None:
        return False
    return (
        candle.close < low - buffer
        if side == "buy"
        else candle.close > high + buffer
    )


def _follow_through_reaction_at(
    *,
    candles: list[Candle],
    exit_index: int,
    zone_low: float,
    zone_high: float,
    side: str,
    timeframe: str,
    atr_current: float | None,
    break_buffer: float | None,
    terminal_index: int | None = None,
) -> str | None:
    """Return the first valid post-exit displacement close, if any.

    The exit candle is included deliberately: the lifecycle event ordering is
    ``exited`` followed by ``reacted`` at the same close when that candle also
    supplies the required follow-through.  Invalidation has terminal priority
    throughout the three-candle window, so a later reaction cannot rescue a
    zone already broken in that window.  ``terminal_index`` caps the window at
    the lifetime boundary: expiry is evaluated before the reaction of its own
    candle (A-D05), so neither the terminal candle nor any later one may supply
    a reaction for an earlier exit.
    """

    if atr_current is None:
        return None
    try:
        atr_value = float(atr_current)
    except (TypeError, ValueError, OverflowError):
        return None
    if not isfinite(atr_value) or atr_value <= 0:
        return None

    threshold = 0.25 * atr_value
    last_index = min(len(candles) - 1, exit_index + 3)
    if terminal_index is not None:
        last_index = min(last_index, terminal_index - 1)
    for index in range(exit_index, last_index + 1):
        candle = candles[index]
        if _invalidates(
            candle,
            zone_low,
            zone_high,
            side,
            buffer=break_buffer,
        ):
            return None
        close = _candle_close(candle, timeframe)
        if (
            side == "buy" and candle.close >= zone_high + threshold
        ) or (
            side == "sell" and candle.close <= zone_low - threshold
        ):
            return close.isoformat()
    return None


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
