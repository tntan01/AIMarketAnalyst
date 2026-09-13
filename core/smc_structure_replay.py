"""Pure, causal structure evaluator for the stage-B acceptance seam.

The public SMC builder is intentionally not imported by this evaluator's
callers.  This module replays actual OHLC in close order and owns the
bootstrap/BOS/CHoCH transition ordering used by the stage-B tests.  It is not
wired into Scanner/Analyze before gate 40 approval.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Sequence

from core.market_models import Candle, candle_close_at, require_valid_smc_candles
from core.smc_context import (
    _filter_swings_by_atr,
    atr_value_before_event,
    confirm_choch_candidate,
    detect_choch_candidate,
    detect_structure_bos,
    external_swing_points,
    expire_structure_events,
    initialize_structure_state,
    invalidate_choch_candidate_on_reclaim,
    normalize_swing_sequence,
    structure_break_buffer,
)


def replay_smc_structure(
    candles: Sequence[Candle],
    *,
    symbol: str,
    timeframe: str = "H4",
    as_of: datetime | str | None = None,
    break_buffer: float | None = None,
    tick_size: float | None = None,
    pivot_width: int = 5,
) -> dict[str, Any]:
    """Replay structure over each closed candle without look-ahead.

    Pivots and the ATR distance filter are rebuilt from the actual prefix
    ending at each candle close.  Bootstrap happens once when a directional
    state first becomes available.  Later confirmed swings refresh only the
    tracked continuation cursor; protected state changes only through BOS or
    the confirmed CHoCH transition.
    """

    normalized_timeframe = str(timeframe or "").strip().upper()
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")
    if not str(symbol or "").strip():
        raise ValueError("symbol is required")
    cutoff = _parse_timestamp(as_of) if as_of is not None else None
    eligible_input: list[Candle] = []
    for item in candles:
        if not isinstance(item, Candle):
            raise ValueError("candles must contain Candle objects")
        close_at = candle_close_at(item.time, normalized_timeframe)
        if cutoff is None or close_at <= cutoff:
            eligible_input.append(item)
    # Validate without repairing order. Future records may be malformed when
    # they are outside an explicit cutoff, but eligible records must satisfy
    # the task-19 OHLC/timestamp/duplicate contract before detection.
    ordered = list(require_valid_smc_candles(eligible_input, normalized_timeframe))
    if pivot_width not in {2, 5}:
        raise ValueError("pivot_width must be canonical external width 5 or observation width 2")
    provisional_fallback = pivot_width == 2
    if tick_size is not None:
        tick_size = float(tick_size)
        if tick_size <= 0:
            raise ValueError("tick_size must be positive")
    if break_buffer is not None:
        break_buffer = float(break_buffer)
        if break_buffer <= 0:
            raise ValueError("break_buffer must be positive")

    state: dict[str, Any] | None = None
    events: list[dict[str, Any]] = []
    snapshots: list[dict[str, Any]] = []

    for index, current in enumerate(ordered):
        current_close = candle_close_at(current.time, normalized_timeframe)
        prefix = ordered[: index + 1]
        swings = external_swing_points(
            prefix,
            symbol=symbol,
            timeframe=normalized_timeframe,
            lookback=pivot_width,
            provisional=provisional_fallback,
        )
        # This filter is causal because both its ATR and swing input are the
        # current prefix, never the complete input passed to the function.
        swings = _filter_swings_by_atr(prefix, swings)

        if state is None:
            candidate_state = initialize_structure_state(swings, as_of=current_close)
            if candidate_state.get("direction") in {"bullish", "bearish"}:
                state = candidate_state

        if state is None:
            snapshots.append(_snapshot(current_close, None, None))
            continue

        causal_atr = atr_value_before_event(
            prefix,
            timeframe=normalized_timeframe,
            event_index=len(prefix) - 1,
        )
        derived_buffer = structure_break_buffer(
            atr_value=causal_atr,
            tick_size=tick_size,
        )
        if break_buffer is not None and (
            derived_buffer is None or abs(break_buffer - derived_buffer) > 1e-9
        ):
            raise ValueError(
                "break_buffer must equal max(2*tick_size, 0.10*causal ATR)"
            )
        event_buffer = derived_buffer
        state = _refresh_continuation(state, swings, current_close)
        bos_result = detect_structure_bos(
            swings,
            [current],
            timeframe=normalized_timeframe,
            symbol=symbol,
            structure_state=state,
            break_buffer=event_buffer,
            as_of=current_close,
        )
        state = bos_result["structure_state"]
        if bos_result.get("event") is not None:
            _append_event(events, bos_result["event"])

        candidate_result = detect_choch_candidate(
            [current],
            timeframe=normalized_timeframe,
            symbol=symbol,
            structure_state=state,
            break_buffer=event_buffer,
            as_of=current_close,
        )
        state = candidate_result["structure_state"]
        if candidate_result.get("candidate") is not None:
            _append_event(events, candidate_result["candidate"])

        # Transition order is part of the evaluator contract: reclaim and
        # timeout are applied before a same/late close can confirm CHoCH.
        reclaim_result = invalidate_choch_candidate_on_reclaim(
            prefix,
            timeframe=normalized_timeframe,
            structure_state=state,
            as_of=current_close,
            break_buffer=event_buffer,
        )
        state = reclaim_result["structure_state"]
        if reclaim_result.get("event") is not None:
            _replace_event(events, reclaim_result["event"])

        expiry_result = expire_structure_events(state, as_of=current_close)
        state = expiry_result["structure_state"]
        for event in expiry_result.get("events", ()):
            _append_event(events, event)

        confirmation_result = confirm_choch_candidate(
            swings,
            prefix,
            timeframe=normalized_timeframe,
            symbol=symbol,
            structure_state=state,
            as_of=current_close,
            break_buffer=event_buffer,
        )
        state = confirmation_result["structure_state"]
        if confirmation_result.get("candidate") is not None:
            _replace_event(events, confirmation_result["candidate"])
        if confirmation_result.get("reversal_bos") is not None:
            _append_event(events, confirmation_result["reversal_bos"])

        snapshots.append(_snapshot(current_close, state, confirmation_result))

    return {
        "symbol": symbol,
        "timeframe": normalized_timeframe,
        "as_of": cutoff.isoformat() if cutoff is not None else None,
        "events": events,
        "snapshots": snapshots,
        "structure_state": state or initialize_structure_state({"highs": [], "lows": []}),
    }


def _refresh_continuation(
    state: dict[str, Any],
    swings: dict[str, list[dict[str, Any]]],
    as_of: datetime,
) -> dict[str, Any]:
    direction = str(state.get("direction") or "").strip().lower()
    kind = "high" if direction == "bullish" else "low"
    eligible = []
    for item in normalize_swing_sequence(swings)[kind + "s"]:
        if item.get("confirmed") is not True or item.get("usable") is False:
            continue
        if item.get("provisional") is True:
            continue
        try:
            confirmed_at = _parse_timestamp(item.get("confirmed_at"))
        except (TypeError, ValueError):
            continue
        if confirmed_at <= as_of:
            eligible.append(item)
    if not eligible:
        return state
    latest = max(
        eligible,
        key=lambda item: (
            _parse_timestamp(item.get("pivot_time", item.get("time"))),
            _parse_timestamp(item.get("confirmed_at")),
            str(item.get("swing_id") or ""),
        ),
    )
    updated = dict(state)
    updated["tracked_continuation_id"] = str(latest["swing_id"])
    updated["tracked_continuation_level"] = float(latest["level"])
    return updated


def _append_event(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return
    if not any(str(item.get("event_id") or "") == event_id for item in events):
        events.append(dict(event))


def _replace_event(events: list[dict[str, Any]], event: dict[str, Any]) -> None:
    event_id = str(event.get("event_id") or "")
    for index, item in enumerate(events):
        if str(item.get("event_id") or "") == event_id:
            events[index] = dict(event)
            return
    _append_event(events, event)


def _snapshot(
    close_at: datetime,
    state: dict[str, Any] | None,
    confirmation: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "close_at": close_at.isoformat(),
        "event_id": (
            confirmation.get("candidate", {}).get("event_id")
            if confirmation and isinstance(confirmation.get("candidate"), dict)
            else None
        ),
        "choch_confirmed": bool(confirmation and confirmation.get("choch_confirmed")),
        "state": state.get("state") if state else None,
        "direction": state.get("direction") if state else None,
        "source_bos_id": state.get("source_bos_id") if state else None,
        "tracked_continuation_id": state.get("tracked_continuation_id") if state else None,
        "protected_swing_id": state.get("protected_swing_id") if state else None,
        "protected_swing_level": state.get("protected_swing_level") if state else None,
    }


def _parse_timestamp(value: datetime | str | object) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    else:
        raise ValueError("timestamp is required")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


__all__ = ["replay_smc_structure"]
