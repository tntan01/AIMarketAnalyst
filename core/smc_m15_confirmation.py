"""M15 entry confirmation for the selected SMC zone (tasks 73–79).

The evaluator no longer scans the last 48 M15 candles for the first arbitrary
touch.  It rebuilds the M15 *entry visits* of the zone — the first closed
candle that overlaps the zone after ``available_at`` opens the visit,
consecutive overlapping candles keep it, and a candle that leaves the zone
closes it — and only the current visit or a just-completed one still inside its
trigger window can confirm an entry.  Events that happened before
``available_at`` are never eligible, and a rejection candle from an older visit
can never confirm again.

A confirmation is a typed :class:`core.smc_models.M15Confirmation` bound to the
zone, the M15 entry visit and the trigger event, carrying ``confirmed_at``,
``expires_at``, ``invalidated_at`` and a reason for every state; nothing here
reports a boolean without a source.  M15 owns readiness only: it never adds or
subtracts quality points (R16-03, parameter table P10), so a tested-but-
unconfirmed zone keeps its B/Q/L/C and quality and only its readiness changes.

Boundary contract used here (lifecycle spec §11 R16-02, parameter table P10):

* anchor = close of the first overlapping M15 candle after ``available_at``;
  ``trigger_anchor_at == visit_anchor_at``.
* the confirmation close is valid at ``1 <= delta <= 3`` bars after the anchor.
* the trigger stays alive through ``delta = 12`` and expires when the candle at
  ``delta = 13`` closes.
* the trigger is cancelled by a new entry visit, a close beyond the zone's
  distal boundary plus buffer, a reclaim back into the zone, price running more
  than ``0.50 * ATR`` away from the entry boundary, or timeout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any

from core.indicators import atr
from core.smc_models import (
    M15_STATUS_CONFIRMED,
    M15_STATUS_EXPIRED,
    M15_STATUS_INSUFFICIENT_DATA,
    M15_STATUS_INVALIDATED,
    M15_STATUS_WAITING,
    M15_STATUS_ZONE_NOT_TESTED,
    M15_TRIGGER_MICRO_BREAK,
    M15_TRIGGER_REJECTION,
    M15Confirmation,
    build_m15_confirmation_id,
    build_m15_entry_visit_id,
    build_m15_trigger_event_id,
)

# Reason codes traced for every M15 outcome.
M15_CONFIRMATION_REASON = "M15_CONFIRMATION"
M15_NO_CONFIRMATION_REASON = "M15_NO_CONFIRMATION"
M15_INSUFFICIENT_DATA_REASON = "M15_INSUFFICIENT_DATA"
M15_DATA_UNAVAILABLE_REASON = "M15_DATA_UNAVAILABLE"
M15_ZONE_NOT_TESTED_REASON = "M15_ZONE_NOT_TESTED"
M15_NEW_VISIT_REASON = "M15_NEW_VISIT"
M15_RECLAIM_AGAINST_REASON = "M15_RECLAIM_AGAINST"
M15_ENTRY_TOO_FAR_REASON = "M15_ENTRY_TOO_FAR"
TRIGGER_EXPIRED_REASON = "TRIGGER_EXPIRED"
ZONE_INVALIDATED_REASON = "ZONE_INVALIDATED"

# Canonical snapshot-cutoff reasons (data spec §6).  Without a usable `as_of`
# the closed-candle boundary cannot be established, so the M15 entry
# confirmation is not evaluated and the readiness state is "missing"
# (readiness spec §5.1) instead of a fabricated confirmation.
SMC_CUTOFF_MISSING_REASON = "SMC_CUTOFF_MISSING"
SMC_CUTOFF_NAIVE_REASON = "SMC_CUTOFF_NAIVE"
# A candle whose open time cannot be parsed cannot be placed on either side of
# the cutoff, so it is never silently dropped (R73-02).
SMC_TIMESTAMP_INVALID_REASON = "SMC_TIMESTAMP_INVALID"

# Legacy status vocabulary kept for readers of the old dict contract.  The
# evaluator reports the canonical states above; `not_confirmed` is now split
# into `waiting` / `expired` / `invalidated`.
M15_CONFIRMED = M15_STATUS_CONFIRMED
M15_NOT_CONFIRMED = "not_confirmed"
M15_ZONE_NOT_TESTED = M15_STATUS_ZONE_NOT_TESTED
M15_INSUFFICIENT_DATA = M15_STATUS_INSUFFICIENT_DATA

_M15_MIN_CANDLES = 15               # P10 minimum data for the ATR checks
_M15_LOOKBACK_CANDLES = 48          # caller window covering the trigger life
_M15_FOLLOW_THROUGH_BARS = 3        # confirmation close valid at delta 1..3
_M15_TRIGGER_WINDOW_BARS = 12       # trigger alive through delta 12
_M15_SWING_LOOKBACK = 3             # fractal pivot width for the micro break
_M15_REJECTION_BODY_RATIO = 0.8     # same contract as the H1 rejection check
_M15_REJECTION_RANGE_RATIO = 0.25
_M15_DISPLACEMENT_ATR_RATIO = 0.3
_M15_BREAK_ATR_RATIO = 0.10         # structure break buffer, ATR term
_M15_BREAK_TICK_MULTIPLE = 2.0      # structure break buffer, tick term
_M15_EXIT_ATR_RATIO = 0.05          # visit exit tolerance, ATR term
_M15_EXIT_TICK_MULTIPLE = 1.0       # visit exit tolerance, tick term
_M15_INVALIDATION_ATR_RATIO = 0.05  # zone break buffer, ATR term
_M15_INVALIDATION_TICK_MULTIPLE = 1.0
_M15_MAX_RUN_ATR = 0.5              # P10 maximum run from the entry boundary
_M15_ATR_PERIOD = 14
_M15_INTERVAL = timedelta(minutes=15)


@dataclass(frozen=True, slots=True)
class _EntryVisit:
    ordinal: int
    anchor_index: int
    anchor_at: str


@dataclass(frozen=True, slots=True)
class _Trigger:
    kind: str
    index: int
    at: str


def evaluate_m15_entry_confirmation(
    side: str,
    zone_low: object,
    zone_high: object,
    m15_candles: object,
    *,
    zone_id: object = "",
    available_at: object = None,
    as_of: object = None,
    tick_size: object = None,
    parent_lifecycle_visit_id: object = None,
) -> M15Confirmation:
    """Evaluate the M15 entry confirmation of one zone side.

    ``as_of`` is the snapshot cutoff and is mandatory for a confirmation: only
    candles whose ``close_at <= as_of`` take part, so a forming or
    future-relative candle can neither confirm nor invalidate an entry (data
    spec §1–2).  A missing or naive cutoff fails closed with the canonical
    cutoff reason instead of evaluating the window.

    ``available_at`` is the zone availability boundary: an M15 candle that
    closed before it can neither open nor confirm an entry visit.  ``tick_size``
    feeds the tick term of the break/exit/invalidation buffers and is optional;
    without it those buffers keep their ATR term.  ``zone_id`` names the zone
    the confirmation belongs to and is required: a confirmation is a claim
    about one specific zone, so a record that cannot name it is not produced.
    """

    zone = str(zone_id or "").strip()
    if not zone:
        raise ValueError("SMC M15 entry confirmation requires zone_id")
    normalized_side = _side(side)
    parent_visit = _optional_text(parent_lifecycle_visit_id)
    if normalized_side is None:
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_INSUFFICIENT_DATA,
            [M15_DATA_UNAVAILABLE_REASON],
        )
    if m15_candles is None or not isinstance(m15_candles, (list, tuple)):
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_INSUFFICIENT_DATA,
            [M15_DATA_UNAVAILABLE_REASON],
            parent_lifecycle_visit_id=parent_visit,
        )
    low = _finite(zone_low)
    high = _finite(zone_high)
    if low is None or high is None or high <= low:
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_INSUFFICIENT_DATA,
            [M15_INSUFFICIENT_DATA_REASON],
            parent_lifecycle_visit_id=parent_visit,
        )
    cutoff, cutoff_reason = _snapshot_cutoff(as_of)
    if cutoff_reason is not None:
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_INSUFFICIENT_DATA,
            [cutoff_reason],
            parent_lifecycle_visit_id=parent_visit,
            zone_low=low,
            zone_high=high,
        )
    # R73-02: eligibility is decided before any candle content is validated, so
    # a candle after the cutoff can never fail the snapshot it is excluded from.
    candles, timestamps_usable = _eligible_candles(list(m15_candles), cutoff)
    if not timestamps_usable:
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_INSUFFICIENT_DATA,
            [SMC_TIMESTAMP_INVALID_REASON],
            parent_lifecycle_visit_id=parent_visit,
            zone_low=low,
            zone_high=high,
        )
    if not _ohlc_is_finite(candles):
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_INSUFFICIENT_DATA,
            [M15_INSUFFICIENT_DATA_REASON],
            parent_lifecycle_visit_id=parent_visit,
            zone_low=low,
            zone_high=high,
        )
    if len(candles) < _M15_MIN_CANDLES:
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_INSUFFICIENT_DATA,
            [M15_INSUFFICIENT_DATA_REASON],
            parent_lifecycle_visit_id=parent_visit,
            zone_low=low,
            zone_high=high,
        )

    closes = [_candle_close_at(candle) for candle in candles]
    tick = _finite(tick_size)
    atr_values = _atr_series(candles)
    current_atr = atr_values[-1] if atr_values else None
    eligible_from = 0
    boundary = _finite_time(available_at)
    if boundary is not None:
        eligible_from = len(candles)
        for index, close_at in enumerate(closes):
            if close_at is not None and close_at > boundary:
                eligible_from = index
                break

    visits = _entry_visits(
        candles,
        closes,
        low,
        high,
        _exit_tolerance(tick, current_atr),
        eligible_from,
    )
    if not visits:
        return _empty(
            zone,
            normalized_side,
            M15_STATUS_ZONE_NOT_TESTED,
            [M15_ZONE_NOT_TESTED_REASON],
            parent_lifecycle_visit_id=parent_visit,
            zone_low=low,
            zone_high=high,
        )

    attempts = [
        (
            visit,
            _find_trigger(
                candles,
                atr_values,
                visit,
                normalized_side,
                low,
                high,
                tick,
            ),
        )
        for visit in visits
    ]
    effective = visits[-1]
    confirming = [
        (visit, trigger)
        for visit, trigger in attempts
        if trigger is not None
    ]
    latest_visit, latest_trigger = confirming[-1] if confirming else (None, None)

    if latest_visit is effective and latest_trigger is not None:
        return _confirmed_record(
            zone_id=zone,
            side=normalized_side,
            low=low,
            high=high,
            candles=candles,
            closes=closes,
            atr_values=atr_values,
            visit=effective,
            trigger=latest_trigger,
            tick=tick,
            parent_lifecycle_visit_id=parent_visit,
        )

    superseded = latest_visit is not None
    expired = _bars_since_anchor(candles, effective) > _M15_TRIGGER_WINDOW_BARS
    reasons = [M15_NO_CONFIRMATION_REASON]
    if superseded:
        reasons.append(M15_NEW_VISIT_REASON)
    if not expired and _too_far_at(
        candles,
        atr_values,
        len(candles) - 1,
        normalized_side,
        low,
        high,
    ):
        reasons.append(M15_ENTRY_TOO_FAR_REASON)
    if expired:
        reasons.append(TRIGGER_EXPIRED_REASON)
    return _visit_record(
        zone_id=zone,
        side=normalized_side,
        low=low,
        high=high,
        candles=candles,
        closes=closes,
        visit=effective,
        status=M15_STATUS_EXPIRED if expired else M15_STATUS_WAITING,
        reasons=reasons,
        parent_lifecycle_visit_id=parent_visit,
    )


def evaluate_m15_confirmation(
    side: str,
    zone_low: object,
    zone_high: object,
    m15_candles: object,
    *,
    zone_id: object = "",
    available_at: object = None,
    as_of: object = None,
    tick_size: object = None,
    parent_lifecycle_visit_id: object = None,
) -> dict[str, Any]:
    """Legacy dict adapter over :func:`evaluate_m15_entry_confirmation`.

    Temporary bridge for the published dict contract: it only converts the
    typed record, it never evaluates a second confirmation.  ``penalty`` is
    always ``0`` because M15 owns readiness only (R16-03); legacy readers that
    applied it must stop doing so.  ``choch``/``reaction`` are derived from the
    recorded trigger kind, and every boolean is derived from ``status``.

    Callers: legacy dict readers and diagnostics.  The production scorer reads
    the typed record directly.  ``zone_id`` and ``as_of`` are required for the
    same reason the typed evaluator requires them.  Removal condition: after
    task 106/107 no caller in the task 2 inventory reads this dict and review
    116 is APPROVED.
    """

    confirmation = evaluate_m15_entry_confirmation(
        side,
        zone_low,
        zone_high,
        m15_candles,
        zone_id=zone_id,
        available_at=available_at,
        as_of=as_of,
        tick_size=tick_size,
        parent_lifecycle_visit_id=parent_lifecycle_visit_id,
    )
    return {
        "status": confirmation.status,
        "confirmed": confirmation.confirmed,
        "penalty": 0,
        "reason_codes": list(confirmation.reason_codes),
        "choch": confirmation.trigger_kind == M15_TRIGGER_MICRO_BREAK,
        "reaction": confirmation.trigger_kind == M15_TRIGGER_REJECTION,
        "zone_id": confirmation.zone_id,
        "entry_visit_id": confirmation.entry_visit_id,
        "trigger_event_id": confirmation.trigger_event_id,
        "confirmation_id": confirmation.confirmation_id,
        "trigger_kind": confirmation.trigger_kind,
        "confirmed_at": confirmation.confirmed_at,
        "expires_at": confirmation.expires_at,
        "invalidated_at": confirmation.invalidated_at,
        "invalidation_reason": confirmation.invalidation_reason,
        "m15_status": confirmation.m15_status,
    }


# -- Visit reconstruction ----------------------------------------------------


def _entry_visits(
    candles: list[Any],
    closes: list[datetime | None],
    low: float,
    high: float,
    tolerance: float,
    eligible_from: int,
) -> list[_EntryVisit]:
    """Rebuild the M15 entry visits of the zone in causal order."""

    visits: list[_EntryVisit] = []
    start: int | None = None
    for index in range(eligible_from, len(candles)):
        candle = candles[index]
        if _overlaps(candle, low, high, tolerance):
            if start is None:
                start = index
        elif start is not None:
            visits.append(_visit_record_from(start, closes, len(visits) + 1))
            start = None
    if start is not None:
        visits.append(_visit_record_from(start, closes, len(visits) + 1))
    return visits


def _visit_record_from(
    start: int,
    closes: list[datetime | None],
    ordinal: int,
) -> _EntryVisit:
    anchor = closes[start]
    assert anchor is not None
    return _EntryVisit(
        ordinal=ordinal,
        anchor_index=start,
        anchor_at=anchor.isoformat(),
    )


def _find_trigger(
    candles: list[Any],
    atr_values: list[float | None],
    visit: _EntryVisit,
    side: str,
    low: float,
    high: float,
    tick: float | None,
) -> _Trigger | None:
    """Find the trigger of one entry visit inside its follow-through window.

    The first structurally valid trigger wins; the maximum-run guard is applied
    afterwards on the evaluation point, because it describes the current
    distance from the entry and not the trigger candle itself.
    """

    last = len(candles) - 1
    for delta in range(1, _M15_FOLLOW_THROUGH_BARS + 1):
        index = visit.anchor_index + delta
        if index > last:
            break
        kind = _trigger_kind(
            candles,
            atr_values,
            index,
            side,
            low,
            high,
            tick,
        )
        if kind is None:
            continue
        close_at = _candle_close_at(candles[index])
        assert close_at is not None
        return _Trigger(kind=kind, index=index, at=close_at.isoformat())
    return None


def _trigger_kind(
    candles: list[Any],
    atr_values: list[float | None],
    index: int,
    side: str,
    low: float,
    high: float,
    tick: float | None,
) -> str | None:
    if _micro_break(candles, atr_values, index, side, low, high, tick):
        return M15_TRIGGER_MICRO_BREAK
    if _rejection(candles, index, side, low, high):
        return M15_TRIGGER_REJECTION
    return None


def _micro_break(
    candles: list[Any],
    atr_values: list[float | None],
    index: int,
    side: str,
    low: float,
    high: float,
    tick: float | None,
) -> bool:
    """Micro break of a confirmed level plus departure out of the zone.

    A lone higher low / lower high or a break of a level that is not confirmed
    yet never qualifies; the confirmation candle itself must carry the
    displacement body and close out of the zone.
    """

    atr_value = _atr_at(atr_values, index)
    if atr_value is None or atr_value <= 0:
        return False
    candle = candles[index]
    body = abs(candle.close - candle.open)
    if body < _M15_DISPLACEMENT_ATR_RATIO * atr_value:
        return False
    level = _confirmed_micro_level(candles, index, side)
    if level is None:
        return False
    buffer = _buffer(tick, _M15_BREAK_TICK_MULTIPLE, atr_value, _M15_BREAK_ATR_RATIO)
    if side == "buy":
        if candle.close <= candle.open or candle.close <= high:
            return False
        return candle.close > level + buffer
    if candle.close >= candle.open or candle.close >= low:
        return False
    return candle.close < level - buffer


def _confirmed_micro_level(candles: list[Any], index: int, side: str) -> float | None:
    """Most recent confirmed micro pivot still overhead before ``index``.

    A pivot needs its full right side before it counts as confirmed, so only
    pivots at ``index - (2 * width)`` or earlier are eligible; the search stops
    at the trigger lookback window.  A pivot that the previous candle already
    closed beyond is no longer a level to break.
    """

    previous_close = candles[index - 1].close
    first = max(_M15_SWING_LOOKBACK, index - _M15_LOOKBACK_CANDLES)
    for pivot in range(index - _M15_SWING_LOOKBACK - 1, first - 1, -1):
        window = candles[pivot - _M15_SWING_LOOKBACK : pivot + _M15_SWING_LOOKBACK + 1]
        candle = candles[pivot]
        if side == "buy":
            extreme = max(item.high for item in window)
            if candle.high == extreme and _unique_extreme(window, candle.high, "high"):
                if candle.high > previous_close:
                    return candle.high
        else:
            extreme = min(item.low for item in window)
            if candle.low == extreme and _unique_extreme(window, candle.low, "low"):
                if candle.low < previous_close:
                    return candle.low
    return None


def _unique_extreme(window: list[Any], level: float, attribute: str) -> bool:
    return sum(1 for item in window if getattr(item, attribute) == level) == 1


def _rejection(
    candles: list[Any],
    index: int,
    side: str,
    low: float,
    high: float,
) -> bool:
    """Rejection at the zone with follow-through out of it.

    The candle must touch the zone, print a directional wick over the shared
    threshold and close outside the zone in the expected direction; a same
    colour candle far from the zone, or a wick without follow-through, never
    qualifies.
    """

    candle = candles[index]
    if not (candle.low <= high and candle.high >= low):
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
        if candle.close <= candle.open or candle.close <= high:
            return False
        wick = min(candle.open, candle.close) - candle.low
    else:
        if candle.close >= candle.open or candle.close >= low:
            return False
        wick = candle.high - max(candle.open, candle.close)
    return wick > 0 and wick >= threshold


def _within_max_run(
    candle: Any,
    side: str,
    low: float,
    high: float,
    atr_value: float | None,
) -> bool:
    """Price must not have run further than ``0.50 * ATR`` from the entry.

    The entry reference is the zone boundary the entry sits at (``high`` for a
    buy, ``low`` for a sell).  Unknown ATR fails closed: an unmeasurable run is
    never treated as an acceptable one.
    """

    if atr_value is None or not isfinite(atr_value) or atr_value <= 0:
        return False
    limit = _M15_MAX_RUN_ATR * atr_value
    if side == "buy":
        return candle.close - high <= limit
    return low - candle.close <= limit


# -- Result builders ---------------------------------------------------------


def _confirmed_record(
    *,
    zone_id: str,
    side: str,
    low: float,
    high: float,
    candles: list[Any],
    closes: list[datetime | None],
    atr_values: list[float | None],
    visit: _EntryVisit,
    trigger: _Trigger,
    tick: float | None,
    parent_lifecycle_visit_id: str | None,
) -> M15Confirmation:
    entry_visit_id = build_m15_entry_visit_id(zone_id, visit.ordinal)
    trigger_event_id = build_m15_trigger_event_id(entry_visit_id, 1)
    confirmation_id = build_m15_confirmation_id(entry_visit_id, 1)
    expires_at = _expires_at(visit, closes)
    invalidation = _invalidation(
        candles=candles,
        atr_values=atr_values,
        visit=visit,
        trigger_index=trigger.index,
        side=side,
        low=low,
        high=high,
        tick=tick,
    )
    common = {
        "zone_id": zone_id,
        "side": side,
        "entry_visit_id": entry_visit_id,
        "visit_ordinal": visit.ordinal,
        "visit_anchor_at": visit.anchor_at,
        "bars_since_anchor": len(candles) - 1 - visit.anchor_index,
        "trigger_event_id": trigger_event_id,
        "trigger_kind": trigger.kind,
        "trigger_at": trigger.at,
        "confirmation_id": confirmation_id,
        "confirmed_at": trigger.at,
        "expires_at": expires_at,
        "parent_lifecycle_visit_id": parent_lifecycle_visit_id,
        "zone_low": low,
        "zone_high": high,
    }
    if invalidation is None:
        if _bars_since_anchor(candles, visit) > _M15_TRIGGER_WINDOW_BARS:
            return M15Confirmation(
                status=M15_STATUS_EXPIRED,
                reason_codes=(TRIGGER_EXPIRED_REASON,),
                **common,
            )
        return M15Confirmation(
            status=M15_STATUS_CONFIRMED,
            reason_codes=(M15_CONFIRMATION_REASON,),
            **common,
        )
    invalidated_index, reason = invalidation
    invalidated_at = closes[invalidated_index]
    return M15Confirmation(
        status=M15_STATUS_INVALIDATED,
        invalidated_at=invalidated_at.isoformat() if invalidated_at else None,
        invalidation_reason=reason,
        reason_codes=(reason,),
        **common,
    )


def _invalidation(
    *,
    candles: list[Any],
    atr_values: list[float | None],
    visit: _EntryVisit,
    trigger_index: int,
    side: str,
    low: float,
    high: float,
    tick: float | None,
) -> tuple[int, str] | None:
    """First terminal event after the confirmation inside the trigger window.

    Precedence per candle: a close beyond the distal boundary plus buffer
    (``ZONE_INVALIDATED``) beats a reclaim (``M15_RECLAIM_AGAINST``).  The
    maximum-run guard is evaluated once, at the evaluation point, because it
    describes the current distance from the entry and not a past candle.
    """

    last_allowed = min(len(candles) - 1, visit.anchor_index + _M15_TRIGGER_WINDOW_BARS)
    for index in range(trigger_index + 1, last_allowed + 1):
        candle = candles[index]
        atr_value = _atr_at(atr_values, index)
        if atr_value is None or not isfinite(atr_value) or atr_value <= 0:
            continue
        buffer = _buffer(
            tick,
            _M15_INVALIDATION_TICK_MULTIPLE,
            atr_value,
            _M15_INVALIDATION_ATR_RATIO,
        )
        if side == "buy" and candle.close < low - buffer:
            return index, ZONE_INVALIDATED_REASON
        if side == "sell" and candle.close > high + buffer:
            return index, ZONE_INVALIDATED_REASON
        if side == "buy" and candle.close < high:
            return index, M15_RECLAIM_AGAINST_REASON
        if side == "sell" and candle.close > low:
            return index, M15_RECLAIM_AGAINST_REASON
    if _too_far_at(candles, atr_values, last_allowed, side, low, high):
        return last_allowed, M15_ENTRY_TOO_FAR_REASON
    return None


def _too_far_at(
    candles: list[Any],
    atr_values: list[float | None],
    index: int,
    side: str,
    low: float,
    high: float,
) -> bool:
    """Whether the candle at ``index`` has run past ``0.50 * ATR`` from entry.

    Unknown ATR fails closed: an unmeasurable run is never treated as an
    acceptable one.
    """

    if index < 0 or index >= len(candles):
        return False
    atr_value = _atr_at(atr_values, index)
    if atr_value is None or not isfinite(atr_value) or atr_value <= 0:
        return True
    return not _within_max_run(candles[index], side, low, high, atr_value)


def _visit_record(
    *,
    zone_id: str,
    side: str,
    low: float,
    high: float,
    candles: list[Any],
    closes: list[datetime | None],
    visit: _EntryVisit,
    status: str,
    reasons: list[str],
    parent_lifecycle_visit_id: str | None,
) -> M15Confirmation:
    return M15Confirmation(
        zone_id=zone_id,
        side=side,
        status=status,
        entry_visit_id=build_m15_entry_visit_id(zone_id, visit.ordinal),
        visit_ordinal=visit.ordinal,
        visit_anchor_at=visit.anchor_at,
        bars_since_anchor=len(candles) - 1 - visit.anchor_index,
        expires_at=_expires_at(visit, closes),
        parent_lifecycle_visit_id=parent_lifecycle_visit_id,
        zone_low=low,
        zone_high=high,
        reason_codes=tuple(reasons),
    )


def _empty(
    zone_id: str,
    side: str | None,
    status: str,
    reasons: list[str],
    *,
    parent_lifecycle_visit_id: str | None = None,
    zone_low: float | None = None,
    zone_high: float | None = None,
) -> M15Confirmation:
    return M15Confirmation(
        zone_id=zone_id,
        side=side or "",
        status=status,
        parent_lifecycle_visit_id=parent_lifecycle_visit_id,
        zone_low=zone_low,
        zone_high=zone_high,
        reason_codes=tuple(reasons),
    )


def _expires_at(visit: _EntryVisit, closes: list[datetime | None]) -> str | None:
    anchor = closes[visit.anchor_index]
    if anchor is None:
        return None
    return (anchor + _M15_INTERVAL * _M15_TRIGGER_WINDOW_BARS).isoformat()


def _bars_since_anchor(candles: list[Any], visit: _EntryVisit) -> int:
    return len(candles) - 1 - visit.anchor_index


# -- Small numeric/calendar helpers -----------------------------------------


def _atr_at(atr_values: list[float | None], index: int) -> float | None:
    """Nearest known ATR at or before ``index``; still strictly causal."""

    for position in range(min(index, len(atr_values) - 1), -1, -1):
        value = atr_values[position]
        if value is not None:
            return value
    return None


def _atr_series(candles: list[Any]) -> list[float | None]:
    highs = [float(candle.high) for candle in candles]
    lows = [float(candle.low) for candle in candles]
    closes = [float(candle.close) for candle in candles]
    return atr(highs, lows, closes, _M15_ATR_PERIOD)


def _overlaps(candle: Any, low: float, high: float, tolerance: float) -> bool:
    return candle.low <= high + tolerance and candle.high >= low - tolerance


def _exit_tolerance(tick: float | None, atr_value: float | None) -> float:
    """Visit exit tolerance: ``max(1 * tick, 0.05 * ATR)`` (lifecycle §visit)."""

    return _buffer(tick, _M15_EXIT_TICK_MULTIPLE, atr_value or 0.0, _M15_EXIT_ATR_RATIO)


def _buffer(
    tick: float | None,
    tick_multiple: float,
    atr_value: float,
    atr_ratio: float,
) -> float:
    values: list[float] = []
    if tick is not None and tick > 0:
        values.append(tick_multiple * tick)
    if isfinite(atr_value) and atr_value > 0:
        values.append(atr_ratio * atr_value)
    return max(values) if values else 0.0


def _snapshot_cutoff(value: object) -> tuple[datetime | None, str | None]:
    """Parse the snapshot cutoff; return its canonical reason when unusable."""

    if value is None:
        return None, SMC_CUTOFF_MISSING_REASON
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            return None, SMC_CUTOFF_NAIVE_REASON
        return value.astimezone(timezone.utc), None
    text = str(value).strip()
    if not text:
        return None, SMC_CUTOFF_MISSING_REASON
    parse_text = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(parse_text)
    except ValueError:
        return None, SMC_CUTOFF_MISSING_REASON
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None, SMC_CUTOFF_NAIVE_REASON
    return parsed.astimezone(timezone.utc), None


def _eligible_candles(
    candles: list[Any],
    cutoff: datetime,
) -> tuple[list[Any], bool]:
    """Candles closed at the cutoff, plus whether every timestamp was readable.

    Eligibility is decided by candle close time and never by dropping the last
    element of the list (data spec §2).  A candle whose open time cannot be
    parsed cannot be placed on either side of the cutoff, so it is never
    silently dropped: the second value is ``False`` and the caller reports the
    canonical timestamp reason instead (R73-02).  Only the eligible candles are
    later validated for OHLC content.
    """

    closed: list[Any] = []
    for candle in candles:
        close_at = _candle_close_at(candle)
        if close_at is None:
            return closed, False
        if close_at > cutoff:
            continue
        closed.append(candle)
    return closed, True


def _ohlc_is_finite(candles: list[Any]) -> bool:
    """Whether every given candle carries finite OHLC."""

    for candle in candles:
        values = (
            _finite(getattr(candle, "open", None)),
            _finite(getattr(candle, "high", None)),
            _finite(getattr(candle, "low", None)),
            _finite(getattr(candle, "close", None)),
        )
        if any(value is None for value in values):
            return False
    return True


def _candle_close_at(candle: Any) -> datetime | None:
    """Close time of an M15 candle, or ``None`` when it cannot be placed.

    A naive open time has no defined instant, so it is not usable on the
    eligibility path (data spec §2/§6): the caller reports
    ``SMC_TIMESTAMP_INVALID`` instead of assuming UTC.
    """

    opened = _aware_utc_time(getattr(candle, "time", None))
    return opened + _M15_INTERVAL if opened is not None else None


def _aware_utc_time(value: object) -> datetime | None:
    """Parse a timezone-aware timestamp to UTC; naive/unparseable -> ``None``.

    Timezone-aware input is normalized to UTC whatever its offset; a value
    without a defined offset is rejected rather than silently assumed to be UTC
    (data spec §6: ``SMC_TIMESTAMP_INVALID``).
    """

    if value is None:
        return None
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        parse_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(parse_text)
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _finite_time(value: object, *, offset: timedelta | None = None) -> datetime | None:
    """Lenient time parser for the zone availability boundary.

    Kept exactly as R73-01 shipped it (naive input normalized to UTC); the M15
    eligibility path uses :func:`_aware_utc_time` instead, which rejects a naive
    candle timestamp.  Changing this boundary is a separate decision.
    """

    if value is None:
        return None
    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        parse_text = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(parse_text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed + offset if offset is not None else parsed


def _side(value: object) -> str | None:
    normalized = str(value or "").strip().lower()
    return normalized if normalized in {"buy", "sell"} else None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _finite(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if isfinite(number) else None
