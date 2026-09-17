from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
from math import isfinite
from typing import Any, Sequence

from core.indicators import atr
from core.market_models import (
    Candle,
    SMC_TIMEFRAME_INTERVALS,
    candle_close_at,
    require_valid_smc_candles,
)
from core.smc_confluence import build_directional_confluence
from core.smc_lifecycle import analyze_zone_lifecycle, update_fvg_fill
from core.smc_history import assess_smc_history, required_history_for_lifetime
from core.smc_models import (
    SMC_DOMAIN_VERSION,
    SmcZone,
    SmcStructureEvent,
    build_swing_id,
    build_setup_id,
    build_zone_id,
)
from core.smc_sweep_linking import (
    SMC_SWEEP_LINK_VERSION,
    associate_sweeps_to_zones,
    build_sweep_id,
    mark_sweeps_consumed,
    empty_sweep_link_payload,
    setup_availability_by_owner,
    setup_owner_key,
)
from core.trading_session_calendar import (
    BROKER_MAINTENANCE,
    EXPECTED_SESSION_CLOSE,
    MARKET_HOLIDAY,
    trading_session_calendar,
)

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------
_SMC_MIN_CANDLES = 11
_SMC_LOOKBACK_EXTERNAL = 5
_SMC_LOOKBACK_FALLBACK = 2
_SMC_LOOKBACK_INTERNAL = 2
_ATR_FILTER_MIN_CANDLES = 15
_ATR_PERIOD = 14
_ATR_DISTANCE_MULT = 0.2
_LOOKBACK_WINDOW = 80
_MAX_FVG = 6
_MAX_ORDER_BLOCKS = 6
_MAX_SD_ZONES = 5
_MAX_LIQUIDITY_LEVELS = 3
_PD_THRESHOLD = 0.05
_LEG_STRONG = 3
_LEG_NORMAL = 2
_CHOCH_CONFIRMED_LEGS = 3
_STRUCTURE_EVENT_LIFETIME_BARS = {
    "D1": 20,
    "H4": 40,
    "H1": 80,
    "M15": 48,
}
# Effective-zone scoring policy (live in execution planning via risk_engine).
# Named constants keep every adjustment auditable.
_EFFECTIVE_ZONE_SCORE_BASE = 50
_EFFECTIVE_ZONE_FRESHNESS_BONUSES = ((3, 10), (8, 6), (16, 3))
_EFFECTIVE_ZONE_STALE_PENALTY = 12
_EFFECTIVE_ZONE_MITIGATED_PENALTY = 6
_EFFECTIVE_ZONE_MAX_RETEST_PENALTY = 20
_EFFECTIVE_ZONE_RETEST_PENALTY_STEP = 4
_EFFECTIVE_ZONE_NARROW_WIDTH_ATR = 0.35
_EFFECTIVE_ZONE_WIDE_WIDTH_ATR = 0.75
_EFFECTIVE_ZONE_NARROW_BONUS = 6
_EFFECTIVE_ZONE_MAX_WIDTH_PENALTY = 20
_EFFECTIVE_ZONE_WIDTH_PENALTY_PER_ATR = 12
_EFFECTIVE_ZONE_MAX_DISPLACEMENT_BONUS = 15
_EFFECTIVE_ZONE_LIQUIDITY_SWEEP_BONUS = 10
_EFFECTIVE_ZONE_LOCATION_CORRECT_BONUS = 12
_EFFECTIVE_ZONE_LOCATION_EQUILIBRIUM_BONUS = 4
_EFFECTIVE_ZONE_LOCATION_WRONG_PENALTY = 8


def _detector_history_start(length: int, timeframe: str, *, minimum: int) -> int:
    """Return a cold-replay window that covers lifecycle history and context."""

    normalized = str(timeframe or "H1").strip().upper()
    try:
        budget = required_history_for_lifetime(normalized)
    except (KeyError, ValueError):
        budget = required_history_for_lifetime("H1")
    return max(minimum, length - budget)


def _finite_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if isfinite(parsed) else None

_DIRECTIONAL_ZONE_TYPES = {
    "buy": frozenset(
        {"demand_zone", "bullish_order_block", "bullish_fvg"}
    ),
    "sell": frozenset(
        {"supply_zone", "bearish_order_block", "bearish_fvg"}
    ),
}


@dataclass(frozen=True, slots=True)
class SmcAtrReference:
    """Formation ATR and its causal prefix provenance."""

    timeframe: str
    period: int
    value: float
    reference_time: str
    event_time: str
    source_event_id: str | None = None

    def __post_init__(self) -> None:
        timeframe = str(self.timeframe or "").strip().upper()
        if timeframe not in SMC_TIMEFRAME_INTERVALS:
            raise ValueError(f"Unsupported SMC timeframe: {self.timeframe}")
        if isinstance(self.period, bool) or self.period <= 0:
            raise ValueError("SMC ATR period must be positive")
        if not isfinite(float(self.value)) or float(self.value) <= 0:
            raise ValueError("SMC ATR reference must be finite and positive")
        reference = _parse_utc_timestamp(self.reference_time, "reference_time")
        event = _parse_utc_timestamp(self.event_time, "event_time")
        if reference > event:
            raise ValueError("SMC ATR reference cannot be after event_time")
        source_event_id = (
            str(self.source_event_id).strip()
            if self.source_event_id is not None
            else None
        )
        object.__setattr__(self, "timeframe", timeframe)
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "reference_time", reference.isoformat())
        object.__setattr__(self, "event_time", event.isoformat())
        object.__setattr__(self, "source_event_id", source_event_id or None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeframe": self.timeframe,
            "period": self.period,
            "value": self.value,
            "reference_time": self.reference_time,
            "event_time": self.event_time,
            "source_event_id": self.source_event_id,
        }


def zone_matches_direction(
    zone: dict[str, Any] | None,
    direction: str,
) -> bool:
    """Return whether an SMC zone family is valid for the trade direction."""
    if not isinstance(zone, dict):
        return False
    normalized_direction = str(direction or "").strip().lower()
    allowed_types = _DIRECTIONAL_ZONE_TYPES.get(normalized_direction)
    if allowed_types is None:
        return False
    zone_type = str(
        zone.get("zone_type") or zone.get("type") or ""
    ).strip().lower()
    return zone_type in allowed_types


def measure_departure(
    candle: Candle,
    *,
    direction: str,
    atr_before_event: float | None,
) -> dict[str, Any]:
    """Measure one closed departure candle without reading future/current ATR.

    ``atr_before_event`` is deliberately an explicit argument.  The helper
    does not calculate or substitute a latest ATR, so callers must provide the
    causal same-timeframe reference produced by ``atr_reference_before_event``.
    ``close_location`` is the raw OHLC location (0 at low, 1 at high), while
    ``directional_close_location`` mirrors SELL into the same BUY-oriented
    scale for symmetric thresholds.
    """

    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"buy", "sell"}:
        raise ValueError(f"Invalid departure direction: {direction}")
    if not isinstance(candle, Candle):
        raise ValueError("departure candle must be a Candle")

    open_price = float(candle.open)
    high = float(candle.high)
    low = float(candle.low)
    close = float(candle.close)
    values = (open_price, high, low, close)
    if not all(isfinite(value) for value in values):
        raise ValueError("departure candle OHLC must be finite")
    price_range = high - low
    body = abs(close - open_price)
    reasons: list[str] = []
    if price_range <= 0:
        return {
            "direction": normalized_direction,
            "body": body,
            "range": price_range,
            "body_atr": None,
            "body_range": None,
            "close_location": None,
            "directional_close_location": None,
            "atr_before_event": None,
            "status": "invalid",
            "reason_codes": ["DEPARTURE_RANGE_ZERO"],
        }

    close_location = (close - low) / price_range
    directional_close_location = (
        close_location
        if normalized_direction == "buy"
        else 1.0 - close_location
    )
    normalized_atr: float | None = None
    body_atr: float | None = None
    if atr_before_event is None:
        reasons.append("DEPARTURE_ATR_UNAVAILABLE")
    else:
        candidate_atr = float(atr_before_event)
        if not isfinite(candidate_atr) or candidate_atr <= 0:
            reasons.append("DEPARTURE_ATR_INVALID")
        else:
            normalized_atr = candidate_atr
            body_atr = body / candidate_atr

    return {
        "direction": normalized_direction,
        "body": body,
        "range": price_range,
        "body_atr": body_atr,
        "body_range": body / price_range,
        "close_location": close_location,
        "directional_close_location": directional_close_location,
        "atr_before_event": normalized_atr,
        "status": "ok" if not reasons else "unavailable",
        "reason_codes": reasons,
    }


def departure_metrics(
    candle: Candle,
    *,
    direction: str,
    atr_before_event: float | None,
) -> dict[str, Any]:
    """Compatibility alias for the shared departure measurement seam."""

    return measure_departure(
        candle,
        direction=direction,
        atr_before_event=atr_before_event,
    )


def measure_fvg_gap(
    first: Candle,
    middle: Candle,
    third: Candle,
    *,
    tick_size: float | None,
    atr_before_event: float | None,
) -> dict[str, Any]:
    """Measure the three-candle FVG geometry and minimum gap only.

    Middle-candle strength and session-gap classification deliberately remain
    outside this helper for the later FVG tasks.  ``atr_before_event`` is an
    explicit causal input; this function never substitutes a latest ATR.
    """

    if not all(isinstance(item, Candle) for item in (first, middle, third)):
        raise ValueError("FVG candles must be Candle objects")
    bullish = first.high < third.low
    bearish = first.low > third.high
    if not bullish and not bearish:
        return {
            "direction": None,
            "gap_low": None,
            "gap_high": None,
            "gap_width": 0.0,
            "minimum_gap": None,
            "accepted": False,
            "reason_codes": ["FVG_NO_GAP"],
        }
    direction = "buy" if bullish else "sell"
    gap_low = first.high if bullish else third.high
    gap_high = third.low if bullish else first.low
    gap_width = gap_high - gap_low
    reasons: list[str] = []
    tick = None
    if tick_size is None or not isfinite(float(tick_size)) or float(tick_size) <= 0:
        reasons.append("SMC_TICK_SIZE_UNAVAILABLE")
    else:
        tick = float(tick_size)
    atr_value = None
    if atr_before_event is None or not isfinite(float(atr_before_event)) or float(atr_before_event) <= 0:
        reasons.append("FVG_ATR_UNAVAILABLE")
    else:
        atr_value = float(atr_before_event)
    if tick is None or atr_value is None:
        return {
            "direction": direction,
            "gap_low": gap_low,
            "gap_high": gap_high,
            "gap_width": gap_width,
            "minimum_gap": None,
            "accepted": False,
            "reason_codes": reasons,
        }
    minimum_gap = max(2.0 * tick, 0.10 * atr_value)
    if gap_width < minimum_gap:
        reasons.append("FVG_GAP_TOO_SMALL")
    return {
        "direction": direction,
        "gap_low": gap_low,
        "gap_high": gap_high,
        "gap_width": gap_width,
        "minimum_gap": minimum_gap,
        "accepted": not reasons,
        "reason_codes": reasons,
    }


def measure_fvg_middle_candle(
    middle: Candle,
    *,
    direction: str,
) -> dict[str, Any]:
    """Validate the middle candle's body, close location and direction."""

    if not isinstance(middle, Candle):
        raise ValueError("FVG middle candle must be a Candle")
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"buy", "sell"}:
        raise ValueError(f"Invalid FVG direction: {direction}")
    candle_range = float(middle.high) - float(middle.low)
    body = abs(float(middle.close) - float(middle.open))
    if not isfinite(candle_range) or not isfinite(body) or candle_range <= 0:
        return {
            "direction": normalized_direction,
            "middle_direction": None,
            "body": body,
            "range": candle_range,
            "body_range": None,
            "close_location": None,
            "directional_close_location": None,
            "accepted": False,
            "reason_codes": ["FVG_MIDDLE_CANDLE_WEAK"],
        }
    close_location = (float(middle.close) - float(middle.low)) / candle_range
    middle_direction = (
        "buy" if middle.close > middle.open
        else "sell" if middle.close < middle.open
        else "neutral"
    )
    reasons: list[str] = []
    if body / candle_range < 0.50:
        reasons.append("FVG_MIDDLE_CANDLE_WEAK")
    if (
        normalized_direction == "buy" and close_location < 0.70
    ) or (
        normalized_direction == "sell" and close_location > 0.30
    ):
        reasons.append("FVG_MIDDLE_CANDLE_WEAK")
    if middle_direction != normalized_direction:
        reasons.append("FVG_MIDDLE_DIRECTION_MISMATCH")
    return {
        "direction": normalized_direction,
        "middle_direction": middle_direction,
        "body": body,
        "range": candle_range,
        "body_range": body / candle_range,
        "close_location": close_location,
        "directional_close_location": (
            close_location
            if normalized_direction == "buy" else 1.0 - close_location
        ),
        "accepted": not reasons,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def check_fvg_middle_candle(
    middle: Candle,
    *,
    direction: str,
) -> dict[str, Any]:
    """Compatibility alias for the shared middle-candle validation seam."""

    return measure_fvg_middle_candle(middle, direction=direction)


def classify_fvg_session_continuity(
    candles: Sequence[Candle],
    *,
    timeframe: str,
    symbol: str,
) -> dict[str, Any]:
    """Classify whether a three-candle sequence crosses a session closure."""

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported FVG timeframe: {timeframe}")
    if len(candles) != 3 or not all(isinstance(item, Candle) for item in candles):
        raise ValueError("FVG session continuity requires exactly three candles")

    interval = SMC_TIMEFRAME_INTERVALS[normalized_timeframe]
    calendar = trading_session_calendar(symbol) if str(symbol or "").strip() else None
    saw_expected_gap = False
    saw_unknown_gap = False
    saw_session_gap = False
    for previous, current in zip(candles, candles[1:]):
        previous_time = previous.time.astimezone(timezone.utc)
        current_time = current.time.astimezone(timezone.utc)
        expected = previous_time + interval
        if current_time < expected:
            return {
                "status": "invalid",
                "reason_codes": ["FVG_CANDLE_ORDER_INVALID"],
            }
        while expected < current_time:
            if calendar is None:
                saw_unknown_gap = True
            else:
                classification = calendar.classify_missing_slot(
                    expected,
                    interval,
                    timeframe=normalized_timeframe,
                )
                if classification.expected_candle:
                    saw_expected_gap = True
                elif classification.classification in {
                    EXPECTED_SESSION_CLOSE,
                    BROKER_MAINTENANCE,
                    MARKET_HOLIDAY,
                }:
                    saw_session_gap = True
                else:
                    saw_expected_gap = True
            expected += interval
    if saw_expected_gap:
        return {
            "status": "unexpected_gap",
            "reason_codes": ["FVG_CANDLE_GAP_UNEXPECTED"],
        }
    if saw_unknown_gap:
        return {
            "status": "unknown",
            "reason_codes": ["SESSION_GAP_UNKNOWN"],
        }
    if saw_session_gap:
        return {
            "status": "session_gap",
            "reason_codes": ["FVG_SESSION_GAP"],
        }
    return {"status": "continuous", "reason_codes": []}


def fvg_session_continuity(
    candles: Sequence[Candle],
    *,
    timeframe: str,
    symbol: str,
) -> dict[str, Any]:
    """Compatibility alias for FVG session-gap classification."""

    return classify_fvg_session_continuity(
        candles,
        timeframe=timeframe,
        symbol=symbol,
    )


def classify_fvg_session_origin(
    candles: Sequence[Candle],
    *,
    timeframe: str,
    symbol: str,
) -> dict[str, Any]:
    """Classify the OHLC origin of an FVG that crosses a session closure.

    For a known closure, the middle candle's directional segment must cover
    the complete original gap.  This is an OHLC evidence label only: it does
    not replace the independent gap-size or middle-candle quality gates.
    """

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported FVG timeframe: {timeframe}")
    if (
        isinstance(candles, (str, bytes))
        or not isinstance(candles, Sequence)
        or len(candles) != 3
        or not all(isinstance(item, Candle) for item in candles)
    ):
        raise ValueError("FVG session origin requires exactly three candles")
    first, middle, third = require_valid_smc_candles(
        candles,
        normalized_timeframe,
    )
    bullish = first.high < third.low
    bearish = first.low > third.high
    if not bullish and not bearish:
        return {
            "status": "invalid",
            "accepted": False,
            "reason_codes": ["FVG_NO_GAP"],
            "gap_bounds": None,
        }
    if bullish:
        gap_low, gap_high = first.high, third.low
        displacement_low, displacement_high = middle.low, middle.close
    else:
        gap_low, gap_high = third.high, first.low
        displacement_low, displacement_high = middle.close, middle.high
    gap_bounds = {"low": gap_low, "high": gap_high}
    continuity = classify_fvg_session_continuity(
        (first, middle, third),
        timeframe=normalized_timeframe,
        symbol=symbol,
    )
    continuity_status = continuity["status"]
    if continuity_status == "continuous":
        return {
            "status": "continuous",
            "accepted": True,
            "reason_codes": ["FVG_SESSION_CONTINUOUS"],
            "gap_bounds": gap_bounds,
        }
    if continuity_status == "unknown":
        return {
            "status": "unknown",
            "accepted": False,
            "reason_codes": ["SESSION_GAP_UNKNOWN"],
            "gap_bounds": gap_bounds,
        }
    if continuity_status == "unexpected_gap":
        return {
            "status": "invalid",
            "accepted": False,
            "reason_codes": ["FVG_CANDLE_GAP_UNEXPECTED"],
            "gap_bounds": gap_bounds,
        }
    if continuity_status != "session_gap":
        return {
            "status": "invalid",
            "accepted": False,
            "reason_codes": list(continuity.get("reason_codes", [])) or [
                "FVG_CANDLE_ORDER_INVALID"
            ],
            "gap_bounds": gap_bounds,
        }
    if displacement_low <= gap_low and displacement_high >= gap_high:
        return {
            "status": "displacement",
            "accepted": True,
            "reason_codes": ["FVG_SESSION_DISPLACEMENT_CONFIRMED"],
            "gap_bounds": gap_bounds,
        }
    overlap_low = max(displacement_low, gap_low)
    overlap_high = min(displacement_high, gap_high)
    if overlap_high <= overlap_low:
        return {
            "status": "session_only",
            "accepted": False,
            "reason_codes": ["FVG_SESSION_ONLY_GAP"],
            "gap_bounds": gap_bounds,
        }
    return {
        "status": "unknown",
        "accepted": False,
        "reason_codes": ["FVG_SESSION_ORIGIN_AMBIGUOUS"],
        "gap_bounds": gap_bounds,
    }


def detect_fvg_candidates(
    candles: Sequence[Candle],
    *,
    symbol: str = "",
    timeframe: str = "",
    tick_size: float | None,
    atr_before_event: float | dict[int, float] | None = None,
) -> list[dict[str, Any]]:
    """Detect accepted three-candle FVG candidates without promoting them."""

    if len(candles) < 3:
        return []
    candidates: list[dict[str, Any]] = []
    start = _detector_history_start(len(candles), timeframe, minimum=2)
    for third_index in range(start, len(candles)):
        first = candles[third_index - 2]
        middle = candles[third_index - 1]
        third = candles[third_index]
        if isinstance(atr_before_event, dict):
            causal_atr = atr_before_event.get(third_index)
        elif atr_before_event is not None:
            causal_atr = atr_before_event
        elif third_index >= _ATR_FILTER_MIN_CANDLES:
            causal_atr = atr_value_before_event(
                candles,
                timeframe=timeframe or "H1",
                event_index=third_index,
            )
        else:
            causal_atr = None
        measurement = measure_fvg_gap(
            first,
            middle,
            third,
            tick_size=tick_size,
            atr_before_event=causal_atr,
        )
        if not measurement["accepted"]:
            continue
        direction = measurement["direction"]
        middle_measurement = measure_fvg_middle_candle(
            middle,
            direction=direction,
        )
        session_continuity = classify_fvg_session_continuity(
            (first, middle, third),
            timeframe=timeframe or "H1",
            symbol=symbol,
        )
        session_origin = classify_fvg_session_origin(
            (first, middle, third),
            timeframe=timeframe or "H1",
            symbol=symbol,
        )
        session_displacement_eligible = session_origin["accepted"]
        if not session_displacement_eligible:
            continue
        origin_time = first.time.isoformat()
        departure_time = third.time.isoformat()
        # The middle candle is the displacement source; the third candle is
        # only the close boundary that completes the FVG.
        departure_source_time = middle.time.isoformat()
        candidates.append({
            "zone_id": build_zone_id(
                symbol=symbol,
                timeframe=timeframe or "UNKNOWN",
                family="fvg",
                direction=direction,
                origin_time=origin_time,
                low=measurement["gap_low"],
                high=measurement["gap_high"],
            ),
            "setup_id": build_setup_id(
                symbol=symbol,
                timeframe=timeframe or "UNKNOWN",
                direction=direction,
                departure_source=departure_source_time,
            ),
            "type": "bullish_fvg" if direction == "buy" else "bearish_fvg",
            "zone_type": "bullish_fvg" if direction == "buy" else "bearish_fvg",
            "family": "fvg",
            "symbol": symbol,
            "timeframe": timeframe or "UNKNOWN",
            "direction": direction,
            "low": measurement["gap_low"],
            "high": measurement["gap_high"],
            "original_bounds": {
                "low": measurement["gap_low"],
                "high": measurement["gap_high"],
            },
            "origin_index": third_index,
            "origin_time": origin_time,
            "formation_start_index": third_index - 2,
            "formation_end_index": third_index,
            "formation_start": first.time.isoformat(),
            "formation_end": third.time.isoformat(),
            "departure_end_index": third_index,
            "departure_end": departure_time,
            "departure_source_id": departure_source_time,
            "departure_source_time": departure_source_time,
            "available_at": None,
            "confirmed_at": None,
            "confirmation_event_id": None,
            "lifecycle_status": "candidate",
            "candidate": True,
            "entry_eligible": False,
            "gap_measurement": measurement,
            "evidence": {"session_origin": session_origin},
            "session_continuity": session_continuity,
            "session_displacement_eligible": session_displacement_eligible,
            "middle_measurement": middle_measurement,
            "middle_quality_eligible": middle_measurement["accepted"],
            "middle_index": third_index - 1,
            "reason_codes": list(dict.fromkeys(
                ["ZONE_CANDIDATE", *middle_measurement["reason_codes"]]
            )),
        })
    return candidates


def confirm_fvg_candidate(
    candidate: dict[str, Any],
    candles: Sequence[Candle],
    *,
    timeframe: str,
    as_of: datetime | str | None = None,
) -> dict[str, Any]:
    """Confirm an FVG at the close of its third candle.

    FVG confirmation is local to the three-candle formation.  It does not
    wait for BOS or sweep evidence, but it does require every causal gate
    recorded by the candidate detector and never promotes a future candle.
    """

    if not isinstance(candidate, dict):
        raise ValueError("FVG candidate must be a mapping")
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise ValueError("candles must be a sequence")
    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported FVG timeframe: {timeframe}")
    result = dict(candidate)
    raw_reasons = candidate.get("reason_codes", [])
    reasons = [
        str(reason).strip() for reason in raw_reasons if str(reason).strip()
    ] if isinstance(raw_reasons, (list, tuple)) else []
    lifecycle_status = str(candidate.get("lifecycle_status", "candidate") or "candidate").strip().lower()
    if lifecycle_status in {"invalid", "invalidated", "expired", "broken"}:
        result["lifecycle_status"] = lifecycle_status
        result["candidate"] = False
        result["entry_eligible"] = False
        return result
    # These are state/audit markers from an earlier invocation, not current
    # formation blockers.  In particular, a pending result must be promotable
    # when the caller replays it after the third candle closes.
    reasons = [reason for reason in reasons if reason not in {
        "ZONE_CANDIDATE",
        "ZONE_CONFIRMED",
        "FVG_CONFIRMATION_MISSING",
        "FVG_THIRD_CANDLE_NOT_CLOSED",
        "ZONE_NOT_AVAILABLE_YET",
    }]
    evidence = candidate.get("evidence")
    session_origin = evidence.get("session_origin") if isinstance(evidence, dict) else None
    if isinstance(session_origin, dict) and session_origin.get("accepted") is not True:
        reasons.extend(
            str(reason).strip()
            for reason in session_origin.get("reason_codes", [])
            if str(reason).strip()
        )
        result["lifecycle_status"] = "candidate"
        result["candidate"] = True
        result["entry_eligible"] = False
        result["reason_codes"] = list(dict.fromkeys(reasons or ["FVG_SESSION_CONTINUITY_INVALID"]))
        return result
    third_index = candidate.get("formation_end_index", candidate.get("origin_index"))
    try:
        third_index = int(third_index)
    except (TypeError, ValueError):
        third_index = -1
    if third_index < 2 or third_index >= len(candles):
        reasons.append("FVG_FORMATION_DATA_UNAVAILABLE")
    else:
        third_close_at = candle_close_at(
            candles[third_index].time, normalized_timeframe,
        ).astimezone(timezone.utc)
        cutoff = _parse_utc_timestamp(as_of, "as_of") if as_of is not None else None
        if cutoff is not None and third_close_at > cutoff:
            reasons.append("FVG_THIRD_CANDLE_NOT_CLOSED")
        gap = candidate.get("gap_measurement")
        middle = candidate.get("middle_measurement")
        continuity = candidate.get("session_continuity")
        if not isinstance(gap, dict) or gap.get("accepted") is not True:
            reasons.append("FVG_GAP_INVALID")
        if not isinstance(middle, dict) or middle.get("accepted") is not True:
            reasons.append("FVG_MIDDLE_CANDLE_WEAK")
        if candidate.get("middle_quality_eligible") is not True:
            reasons.append("FVG_MIDDLE_CANDLE_WEAK")
        if isinstance(session_origin, dict):
            if session_origin.get("accepted") is not True:
                reasons.extend(session_origin.get("reason_codes", []))
        elif not isinstance(continuity, dict) or (
            continuity.get("status") != "continuous"
            and not (
                continuity.get("status") == "session_gap"
                and candidate.get("session_displacement_eligible") is True
            )
        ):
            reasons.append("FVG_SESSION_CONTINUITY_INVALID")
        if not reasons:
            confirmed_at = third_close_at.isoformat()
            result.update({
                "lifecycle_status": "confirmed",
                "candidate": False,
                "entry_eligible": False,
                "confirmed_at": confirmed_at,
                "available_at": confirmed_at,
                "confirmation_source": "fvg_third_candle_close",
                "reason_codes": ["ZONE_CONFIRMED"],
            })
            return result
    result["lifecycle_status"] = "candidate"
    result["candidate"] = True
    result["entry_eligible"] = False
    result["reason_codes"] = list(dict.fromkeys(reasons or ["FVG_CONFIRMATION_MISSING"]))
    return result


def confirm_fvg_candidates(
    candidates: Sequence[dict[str, Any]],
    candles: Sequence[Candle],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Confirm FVG candidates independently without mutating inputs."""

    return [confirm_fvg_candidate(candidate, candles, **kwargs) for candidate in candidates]
_ZONE_DISPLACEMENT_MULTIPLIER = 5


def build_smc_context(
    d1: list[Candle], h4: list[Candle], h1: list[Candle],
    *, scan_interval_min: int = 15, symbol: str = "",
) -> dict[str, Any]:
    d1_smc = _smc_for_timeframe(
        d1,
        tf_minutes=1440,
        scan_interval_min=scan_interval_min,
        symbol=symbol,
        timeframe="D1",
    )
    h4_smc = _smc_for_timeframe(
        h4,
        tf_minutes=240,
        scan_interval_min=scan_interval_min,
        symbol=symbol,
        timeframe="H4",
    )
    h1_smc = _smc_for_timeframe(
        h1,
        tf_minutes=60,
        scan_interval_min=scan_interval_min,
        symbol=symbol,
        timeframe="H1",
    )
    directional_confluence = build_directional_confluence(
        d1_smc,
        h4_smc,
        h1_smc,
    )
    confluence = directional_confluence.to_dict()
    return {
        "domain_version": SMC_DOMAIN_VERSION,
        "symbol": symbol,
        "D1": d1_smc,
        "H4": h4_smc,
        "H1": h1_smc,
        "confluence": confluence,
    }


def summarize_structure(candles: list[Candle]) -> dict[str, Any]:
    if len(candles) < 3:
        return {"structure": "insufficient_data"}
    swings = swing_points(candles, lookback=_SMC_LOOKBACK_EXTERNAL)
    bos_choch = detect_bos_choch(swings, candles)
    structure = bos_choch.get("structure", "unknown")
    return {
        "structure": structure,
        "bos": bos_choch.get("bos", False),
        "choch": bos_choch.get("choch", False),
        "displacement": bos_choch.get("displacement", "neutral"),
        "swings": swings,
    }


def _smc_for_timeframe(
    candles: list[Candle],
    *,
    tf_minutes: int = 60,
    scan_interval_min: int = 15,
    symbol: str = "",
    timeframe: str = "",
) -> dict[str, Any]:
    if len(candles) < _SMC_MIN_CANDLES:
        return {
            "domain_version": SMC_DOMAIN_VERSION,
            "symbol": symbol,
            "timeframe": timeframe,
            "structure": "insufficient_data",
            "bos": False,
            "choch": False,
            "displacement": "neutral",
            "bos_strength": "weak",
            "choch_confirmed": False,
            "swings": {"highs": [], "lows": []},
            "external_swings": {"highs": [], "lows": []},
            "internal_swings": {"highs": [], "lows": []},
            "leg_count": 0,
            "supply_zones": [],
            "demand_zones": [],
            "order_blocks": [],
            "fvg": [],
            "liquidity_pools": {"equal_highs": [], "equal_lows": [], "swing_highs": [], "swing_lows": []},
            "liquidity_sweeps": {"swept_highs": [], "swept_lows": []},
            "zone_link_sweeps": {"swept_highs": [], "swept_lows": []},
            "premium_discount": "unknown",
            "premium_discount_range": {"status": "unknown"},
        }
    swing_source = "standard"
    swings = swing_points(candles, lookback=_SMC_LOOKBACK_EXTERNAL)
    if len(swings["highs"]) == 0 and len(swings["lows"]) == 0:
        _log.warning("SMC swing_points returned empty with lookback=5, falling back to lookback=2")
        swings = swing_points(candles, lookback=_SMC_LOOKBACK_FALLBACK)
        swing_source = "fallback"
    swings = _filter_swings_by_atr(candles, swings)
    external_swings = swings
    # Keep the public Analyze/Scanner route byte/schema-compatible with the
    # pre-stage-B implementation. The typed detector is owned by the pure
    # replay seam and is not a production rollout at gate 40.
    internal_swings = _legacy_detect_internal_structure(candles, external_swings)
    leg_count = _legacy_count_trend_legs(external_swings)
    bos = detect_bos_choch(swings, candles, leg_count)
    liquidity = detect_liquidity_pools(candles, swings)
    premium_discount = classify_premium_discount(candles[-1].close, swings)
    premium_discount_range = premium_discount_bounds(swings)
    fvg = detect_fvg(candles)
    order_blocks = detect_order_blocks(candles, fvg)
    demand_zones, supply_zones = detect_supply_demand_zones(candles)
    liquidity_sweeps = detect_liquidity_sweeps(
        candles,
        swings,
        symbol=symbol,
        timeframe=timeframe,
        liquidity_pools=liquidity,
        # This public Analyze/Scanner route still runs the legacy unannotated `swing_points`
        # producer, whose pools carry no canonical provenance, so the caller declares the legacy
        # numeric branch explicitly instead of letting an empty `records` container fail closed
        # (Gate40 §R40-03 keeps this route legacy; see fix-plan F07/r1).
        pool_provenance="legacy",
    )
    zone_link_sweeps = detect_liquidity_sweeps(
        candles,
        swings,
        symbol=symbol,
        timeframe=timeframe,
        lookback_bars=_LOOKBACK_WINDOW,
        max_results=None,
        causal_only=True,
        liquidity_pools=liquidity,
        pool_provenance="legacy",
    )
    _attach_zone_sweep_links(
        (
            ("demand", demand_zones),
            ("supply", supply_zones),
            ("order_block", order_blocks),
            ("fvg", fvg),
        ),
        zone_link_sweeps,
        candles=candles,
        symbol=symbol,
        timeframe=timeframe,
        tf_minutes=tf_minutes,
    )
    demand_zones = enrich_zones(
        demand_zones, candles, "demand", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    supply_zones = enrich_zones(
        supply_zones, candles, "supply", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    order_blocks = enrich_zones(
        order_blocks, candles, "order_block", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    fvg = enrich_zones(
        fvg, candles, "fvg", liquidity_sweeps,
        premium_discount_range, tf_minutes=tf_minutes,
        scan_interval_min=scan_interval_min, symbol=symbol,
        timeframe=timeframe,
    )
    return {
        "domain_version": SMC_DOMAIN_VERSION,
        "symbol": symbol,
        "timeframe": timeframe,
        "structure": bos.get("structure", "unknown"),
        "bos": bos.get("bos", False),
        "choch": bos.get("choch", False),
        "displacement": bos.get("displacement", "neutral"),
        "bos_strength": bos.get("bos_strength", "weak"),
        "choch_confirmed": bos.get("choch_confirmed", False),
        "swings": swings,
        "external_swings": external_swings,
        "internal_swings": internal_swings,
        "leg_count": leg_count,
        "supply_zones": supply_zones,
        "demand_zones": demand_zones,
        "order_blocks": order_blocks,
        "fvg": fvg,
        "liquidity_pools": liquidity,
        "liquidity_sweeps": liquidity_sweeps,
        "zone_link_sweeps": zone_link_sweeps,
        "premium_discount": premium_discount,
        "premium_discount_range": premium_discount_range,
        "swing_source": swing_source,
    }


def swing_points(candles: list[Candle], lookback: int = 2) -> dict[str, list[dict[str, Any]]]:
    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []
    for index in range(lookback, len(candles) - lookback):
        window = candles[index - lookback : index + lookback + 1]
        candle = candles[index]
        if candle.high == max(item.high for item in window) and sum(candle.high == item.high for item in window) == 1:
            highs.append({"level": candle.high, "index": index, "time": candle.time.isoformat()})
        if candle.low == min(item.low for item in window) and sum(candle.low == item.low for item in window) == 1:
            lows.append({"level": candle.low, "index": index, "time": candle.time.isoformat()})
    return {"highs": highs, "lows": lows}


def external_swing_points(
    candles: Sequence[Candle],
    *,
    symbol: str = "",
    timeframe: str = "H4",
    lookback: int = _SMC_LOOKBACK_EXTERNAL,
    provisional: bool = False,
    equal_tolerance: float = 0.0,
) -> dict[str, list[dict[str, Any]]]:
    """Detect causal external pivots with an explicit right-side delay.

    A pivot at index ``i`` is emitted only after ``lookback`` candles to its
    right are present.  Its ``pivot_time`` remains candle ``i``'s open time;
    ``confirmed_at`` is the close boundary of candle ``i + lookback``.  The
    fallback width may be marked provisional, but it retains the same causal
    timestamp contract and never changes the pivot identity to a rolling index.
    """

    return _confirmed_swing_points(
        candles,
        symbol=symbol,
        timeframe=timeframe,
        lookback=lookback,
        provisional=provisional,
        scope="external",
        equal_tolerance=equal_tolerance,
    )


def internal_swing_points(
    candles: Sequence[Candle],
    *,
    symbol: str = "",
    timeframe: str = "H4",
    equal_tolerance: float = 0.0,
) -> dict[str, list[dict[str, Any]]]:
    """Detect internal pivots with the fixed, separately-owned width of two."""

    return _confirmed_swing_points(
        candles,
        symbol=symbol,
        timeframe=timeframe,
        lookback=_SMC_LOOKBACK_INTERNAL,
        provisional=False,
        scope="internal",
        equal_tolerance=equal_tolerance,
    )


def _confirmed_swing_points(
    candles: Sequence[Candle],
    *,
    symbol: str,
    timeframe: str,
    lookback: int,
    provisional: bool,
    scope: str,
    equal_tolerance: float,
) -> dict[str, list[dict[str, Any]]]:
    if isinstance(lookback, bool) or not isinstance(lookback, int) or lookback <= 0:
        raise ValueError("pivot lookback must be a positive integer")
    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")
    if not isfinite(float(equal_tolerance)) or float(equal_tolerance) < 0:
        raise ValueError("equal_tolerance must be finite and non-negative")

    highs: list[dict[str, Any]] = []
    lows: list[dict[str, Any]] = []
    for index in range(lookback, len(candles) - lookback):
        window = candles[index - lookback : index + lookback + 1]
        pivot = candles[index]
        confirmation_candle = candles[index + lookback]
        if not isinstance(pivot, Candle) or not isinstance(confirmation_candle, Candle):
            raise ValueError("candles must contain Candle objects")
        if pivot.time.tzinfo is None or pivot.time.utcoffset() is None:
            raise ValueError("pivot candle time must be timezone-aware")
        pivot_time = pivot.time.astimezone(timezone.utc).isoformat()
        confirmed_at = candle_close_at(
            confirmation_candle.time,
            normalized_timeframe,
        ).isoformat()
        common = {
            "index": index,
            "pivot_time": pivot_time,
            "confirmed_at": confirmed_at,
            # A confirmed, non-provisional pivot is usable from the moment it is confirmed:
            # `confirmed_at` is the close of the right-side confirmation candle, so it is the
            # producer's own usability instant — never the pivot's open time.  A provisional
            # (unusable) pivot declares no effective usability instant at all.
            "usable_at": None if provisional else confirmed_at,
            "confirmation_delay": lookback,
            "confirmed": True,
            "usable": not provisional,
            "provisional": provisional,
            "pivot_width": lookback,
            "timeframe": normalized_timeframe,
            "scope": scope,
        }
        window_high = max(item.high for item in window)
        high_candidates = [
            item_index
            for item_index, item in enumerate(window)
            if window_high - item.high <= float(equal_tolerance)
        ]
        pivot_window_index = lookback
        if pivot_window_index == high_candidates[0]:
            high = dict(common)
            high.update(
                {
                    "level": pivot.high,
                    "kind": "high",
                    "equal_level": len(high_candidates) > 1,
                    "plateau_size": len(high_candidates),
                    "swing_id": build_swing_id(
                        symbol=symbol,
                        timeframe=normalized_timeframe,
                        kind="high",
                        pivot_time=pivot_time,
                    ),
                }
            )
            highs.append(high)
        window_low = min(item.low for item in window)
        low_candidates = [
            item_index
            for item_index, item in enumerate(window)
            if item.low - window_low <= float(equal_tolerance)
        ]
        if pivot_window_index == low_candidates[0]:
            low = dict(common)
            low.update(
                {
                    "level": pivot.low,
                    "kind": "low",
                    "equal_level": len(low_candidates) > 1,
                    "plateau_size": len(low_candidates),
                    "swing_id": build_swing_id(
                        symbol=symbol,
                        timeframe=normalized_timeframe,
                        kind="low",
                        pivot_time=pivot_time,
                    ),
                }
            )
            lows.append(low)
    return normalize_swing_sequence({"highs": highs, "lows": lows})


def normalize_swing_sequence(
    swings: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Return high/low lists in deterministic pivot-time order."""

    def key(item: dict[str, Any]) -> tuple[str, str, str, str]:
        return (
            str(item.get("pivot_time", item.get("time", "")) or ""),
            str(item.get("confirmed_at", "") or ""),
            str(item.get("swing_id", "") or ""),
            str(item.get("kind", "") or ""),
        )

    return {
        "highs": sorted(
            (dict(item) for item in swings.get("highs", [])),
            key=key,
        ),
        "lows": sorted(
            (dict(item) for item in swings.get("lows", [])),
            key=key,
        ),
    }


def ordered_swing_sequence(
    swings: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], ...]:
    """Merge high/low streams by timestamp without positional pairing."""

    normalized = normalize_swing_sequence(swings)
    combined = list(normalized["highs"]) + list(normalized["lows"])
    return tuple(
        sorted(
            combined,
            key=lambda item: (
                str(item.get("pivot_time", item.get("time", "")) or ""),
                str(item.get("confirmed_at", "") or ""),
                str(item.get("kind", "") or ""),
                str(item.get("swing_id", "") or ""),
            ),
        )
    )


def initialize_structure_state(
    swings: dict[str, list[dict[str, Any]]],
    *,
    as_of: datetime | str | None = None,
    equal_tolerance: float = 0.0,
) -> dict[str, Any]:
    """Initialize causal structure state from confirmed, usable swings only."""

    if not isfinite(float(equal_tolerance)) or float(equal_tolerance) < 0:
        raise ValueError("equal_tolerance must be finite and non-negative")
    cutoff = _parse_utc_timestamp(as_of, "as_of") if as_of is not None else None
    reasons: list[str] = []

    def collect(kind: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in swings.get(kind, []):
            if not isinstance(item, dict):
                reasons.append("SMC_SWING_REFERENCE_MISSING")
                continue
            if item.get("confirmed") is not True or item.get("usable") is False:
                continue
            swing_id = str(item.get("swing_id", "") or "").strip()
            if not swing_id:
                reasons.append("SMC_SWING_REFERENCE_MISSING")
                continue
            try:
                pivot_time = _parse_utc_timestamp(
                    item.get("pivot_time", item.get("time")),
                    f"{kind}.pivot_time",
                )
                confirmed_at = _parse_utc_timestamp(
                    item.get("confirmed_at"),
                    f"{kind}.confirmed_at",
                )
                level = float(item["level"])
            except (KeyError, TypeError, ValueError, OverflowError):
                reasons.append("SMC_SWING_TIMESTAMP_INVALID")
                continue
            if not isfinite(level) or level <= 0 or confirmed_at < pivot_time:
                reasons.append("SMC_SWING_TIMESTAMP_INVALID")
                continue
            if cutoff is not None and confirmed_at > cutoff:
                continue
            record = dict(item)
            record.update(
                {
                    "swing_id": swing_id,
                    "pivot_time": pivot_time.isoformat(),
                    "confirmed_at": confirmed_at.isoformat(),
                    "level": level,
                }
            )
            records.append(record)
        return sorted(
            records,
            key=lambda item: (
                item["pivot_time"],
                item["confirmed_at"],
                item["swing_id"],
            ),
        )

    highs = collect("highs")
    lows = collect("lows")
    result: dict[str, Any] = {
        "state": "unknown",
        "structure": "unknown",
        "direction": None,
        "confirmed_high_count": len(highs),
        "confirmed_low_count": len(lows),
        "confirmed_high_ids": [item["swing_id"] for item in highs],
        "confirmed_low_ids": [item["swing_id"] for item in lows],
        "tracked_continuation_id": None,
        "tracked_continuation_level": None,
        "protected_swing_id": None,
        "protected_swing_level": None,
        "protected_swing_kind": None,
        "protected_updated_at": None,
        "protected_provenance": None,
        "source_bos_id": None,
        "bootstrap_ready_at": None,
        "source_history_anchor_at": None,
        "anchor_start_at": None,
        "structure_events": [],
        "event_lifecycle": {},
        "expired_event_ids": [],
        "expired_trigger_ids": [],
        "reason_codes": list(dict.fromkeys(reasons)),
    }
    if len(highs) < 2 or len(lows) < 2:
        result["reason_codes"] = list(
            dict.fromkeys(result["reason_codes"] + ["SMC_INSUFFICIENT_CONFIRMED_SWINGS"])
        )
        return result

    latest_high, previous_high = highs[-1], highs[-2]
    latest_low, previous_low = lows[-1], lows[-2]
    high_delta = latest_high["level"] - previous_high["level"]
    low_delta = latest_low["level"] - previous_low["level"]
    tolerance = float(equal_tolerance)
    high_equal = abs(high_delta) <= tolerance
    low_equal = abs(low_delta) <= tolerance
    bullish = high_delta > tolerance and low_delta > tolerance
    bearish = high_delta < -tolerance and low_delta < -tolerance
    if bullish:
        result.update(
            {
                "state": "bullish",
                "structure": "HH/HL",
                "direction": "bullish",
                "tracked_continuation_id": latest_high["swing_id"],
                "tracked_continuation_level": latest_high["level"],
            }
        )
    elif bearish:
        result.update(
            {
                "state": "bearish",
                "structure": "LH/LL",
                "direction": "bearish",
                "tracked_continuation_id": latest_low["swing_id"],
                "tracked_continuation_level": latest_low["level"],
            }
        )
    else:
        if high_equal or low_equal:
            reasons.append("SMC_EQUAL_SWING_LEVEL")
        reasons.append("SMC_STRUCTURE_MIXED")
        result["state"] = "mixed"
        result["structure"] = "mixed"

    latest_pair_confirmed = max(
        _parse_utc_timestamp(latest_high["confirmed_at"], "confirmed_at"),
        _parse_utc_timestamp(latest_low["confirmed_at"], "confirmed_at"),
    )
    history_anchor = min(
        _parse_utc_timestamp(item["pivot_time"], "pivot_time")
        for item in highs + lows
    )
    result["bootstrap_ready_at"] = latest_pair_confirmed.isoformat()
    result["source_history_anchor_at"] = history_anchor.isoformat()
    result["anchor_start_at"] = history_anchor.isoformat()
    result["reason_codes"] = list(dict.fromkeys(reasons))
    return result


def structure_break_buffer(
    *,
    atr_value: float | int | None,
    tick_size: float | int | None,
) -> float | None:
    """Resolve the approved strict structure-break buffer.

    Both inputs are required because the contract is ``max(2*tick,
    0.10*ATR)``.  A missing tick or ATR is not replaced with digits, the
    latest unrelated ATR, or zero.
    """

    try:
        atr_number = float(atr_value)
        tick_number = float(tick_size)
    except (TypeError, ValueError, OverflowError):
        return None
    if (
        not isfinite(atr_number)
        or atr_number <= 0
        or not isfinite(tick_number)
        or tick_number <= 0
    ):
        return None
    return max(2.0 * tick_number, 0.10 * atr_number)


def structure_event_identity(
    *,
    symbol: str,
    timeframe: str,
    direction: str,
    broken_level_id: str,
    occurred_at: datetime | str,
) -> str:
    """Build the stable identity of one causal BOS break."""

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"bullish", "bearish"}:
        raise ValueError(f"Unsupported structure direction: {direction}")
    normalized_level = str(broken_level_id or "").strip()
    if not normalized_level:
        raise ValueError("broken_level_id is required")
    close_text = _parse_utc_timestamp(occurred_at, "occurred_at").isoformat()
    identity_key = "|".join(
        (
            str(symbol or "").strip(),
            normalized_timeframe,
            normalized_direction,
            normalized_level,
            close_text,
        )
    )
    return "smc-bos-" + hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:20]


def structure_candidate_identity(
    *,
    symbol: str,
    timeframe: str,
    direction: str,
    protected_swing_id: str,
    occurred_at: datetime | str,
) -> str:
    """Build the stable identity of one protected-level CHoCH candidate."""

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    normalized_direction = str(direction or "").strip().lower()
    if normalized_direction not in {"bullish", "bearish"}:
        raise ValueError(f"Unsupported structure direction: {direction}")
    normalized_protected = str(protected_swing_id or "").strip()
    if not normalized_protected:
        raise ValueError("protected_swing_id is required")
    close_text = _parse_utc_timestamp(occurred_at, "occurred_at").isoformat()
    identity_key = "|".join(
        (
            str(symbol or "").strip(),
            normalized_timeframe,
            normalized_direction,
            normalized_protected,
            close_text,
        )
    )
    return "smc-choch-candidate-" + hashlib.sha256(identity_key.encode("utf-8")).hexdigest()[:20]


def confirmed_choch_identity(
    *,
    candidate_event_id: str,
    reversal_bos_id: str,
) -> str:
    """Build a stable identity for a confirmed candidate transition."""

    candidate_id = str(candidate_event_id or "").strip()
    reversal_id = str(reversal_bos_id or "").strip()
    if not candidate_id or not reversal_id:
        raise ValueError("candidate_event_id and reversal_bos_id are required")
    return "smc-choch-confirmed-" + hashlib.sha256(
        f"{candidate_id}|{reversal_id}".encode("utf-8")
    ).hexdigest()[:20]


def apply_protected_swing_from_bos(
    structure_state: dict[str, Any],
    bos_event: dict[str, Any] | SmcStructureEvent,
    swings: dict[str, list[dict[str, Any]]],
    *,
    as_of: datetime | str | None = None,
) -> dict[str, Any]:
    """Apply a confirmed BOS source to the protected structure cursor.

    The consumer never infers a protected swing from list position or the
    latest pivot.  It resolves the explicit BOS ``source_swing_id`` and
    accepts only a confirmed, usable, non-provisional source of the mirrored
    kind (low for bullish, high for bearish).
    """

    state = dict(structure_state or {})
    reasons = list(state.get("reason_codes", ()))
    try:
        event = (
            bos_event
            if isinstance(bos_event, SmcStructureEvent)
            else SmcStructureEvent.from_dict(bos_event)
        )
    except (TypeError, ValueError, KeyError):
        reasons.append("SMC_PROTECTED_BOS_INVALID")
        state["reason_codes"] = list(dict.fromkeys(reasons))
        return state
    if event.event_type != "BOS" or event.confirmed_at is None:
        reasons.append("SMC_PROTECTED_BOS_REQUIRED")
        state["reason_codes"] = list(dict.fromkeys(reasons))
        return state

    occurred = _parse_utc_timestamp(event.occurred_at, "bos_event.occurred_at")
    if as_of is not None and occurred > _parse_utc_timestamp(as_of, "as_of"):
        reasons.append("SMC_PROTECTED_BOS_AFTER_AS_OF")
        state["reason_codes"] = list(dict.fromkeys(reasons))
        return state

    expected_kind = "low" if event.direction == "bullish" else "high"
    source_id = str(event.source_swing_id or "").strip()
    normalized = normalize_swing_sequence(swings)
    source = next(
        (
            item
            for item in normalized[expected_kind + "s"]
            if str(item.get("swing_id") or "").strip() == source_id
        ),
        None,
    )
    if source is None:
        reasons.append("SMC_PROTECTED_SOURCE_MISSING")
        state["reason_codes"] = list(dict.fromkeys(reasons))
        return state
    try:
        pivot_time = _parse_utc_timestamp(
            source.get("pivot_time", source.get("time")),
            "protected_source.pivot_time",
        )
        confirmed_at = _parse_utc_timestamp(
            source.get("confirmed_at"),
            "protected_source.confirmed_at",
        )
        level = float(source["level"])
    except (KeyError, TypeError, ValueError, OverflowError):
        reasons.append("SMC_PROTECTED_SOURCE_INVALID")
        state["reason_codes"] = list(dict.fromkeys(reasons))
        return state
    if (
        str(source.get("kind") or "").strip().lower() != expected_kind
        or source.get("confirmed") is not True
        or source.get("usable") is False
        or source.get("provisional") is True
        or not isfinite(level)
        or level <= 0
        or pivot_time >= occurred
        or confirmed_at > occurred
    ):
        reasons.append("SMC_PROTECTED_SOURCE_NOT_CAUSAL")
        state["reason_codes"] = list(dict.fromkeys(reasons))
        return state

    current_event_id = str(state.get("source_bos_id") or "").strip()
    if current_event_id == event.event_id:
        reasons.append("SMC_PROTECTED_ALREADY_SYNCED")
        state["reason_codes"] = list(dict.fromkeys(reasons))
        return state
    current_updated = state.get("protected_updated_at")
    if current_updated:
        current_time = _parse_utc_timestamp(
            current_updated,
            "protected_updated_at",
        )
        if occurred < current_time:
            reasons.append("SMC_PROTECTED_BOS_STALE")
            state["reason_codes"] = list(dict.fromkeys(reasons))
            return state

    provenance = {
        "source_bos_id": event.event_id,
        "bos_direction": event.direction,
        "bos_broken_level_id": event.broken_level_id,
        "bos_broken_level": event.source_level,
        "bos_occurred_at": event.occurred_at,
        "bos_confirmed_at": event.confirmed_at,
        "protected_swing_id": source_id,
        "protected_swing_kind": expected_kind,
        "protected_swing_level": level,
        "protected_swing_pivot_time": pivot_time.isoformat(),
        "protected_swing_confirmed_at": confirmed_at.isoformat(),
    }
    state.update(
        {
            "protected_swing_id": source_id,
            "protected_swing_level": level,
            "protected_swing_kind": expected_kind,
            "protected_updated_at": occurred.isoformat(),
            "protected_provenance": provenance,
            "source_bos_id": event.event_id,
        }
    )
    reasons.append("SMC_PROTECTED_UPDATED_FROM_BOS")
    state["reason_codes"] = list(dict.fromkeys(reasons))
    return state


def detect_choch_candidate(
    candles: Sequence[Candle],
    *,
    timeframe: str = "H4",
    symbol: str = "",
    structure_state: dict[str, Any] | None = None,
    as_of: datetime | str | None = None,
    break_buffer: float | int | None = None,
    atr_value: float | int | None = None,
    tick_size: float | int | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Create a causal CHoCH candidate from the protected structure cursor.

    Candidate creation is deliberately separate from candidate reclaim,
    expiry, and follow-through confirmation.  A candidate never changes the
    active trend or protected level.
    """

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")
    state = dict(structure_state or {})
    reasons = list(state.get("reason_codes", ()))

    buffer = None
    if break_buffer is not None:
        try:
            buffer = float(break_buffer)
        except (TypeError, ValueError, OverflowError):
            buffer = None
        if buffer is not None and (not isfinite(buffer) or buffer <= 0):
            buffer = None
    else:
        buffer = structure_break_buffer(atr_value=atr_value, tick_size=tick_size)
    if buffer is None:
        reasons.append("SMC_BREAK_BUFFER_UNAVAILABLE")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    eligible_candles = [candle for candle in candles if isinstance(candle, Candle)]
    cutoff = _parse_utc_timestamp(as_of, "as_of") if as_of is not None else None
    if cutoff is not None:
        eligible_candles = [
            candle
            for candle in eligible_candles
            if _event_close(candle, normalized_timeframe) <= cutoff
        ]
    if not eligible_candles:
        reasons.append("SMC_NO_CLOSED_CANDLE")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    candle = eligible_candles[-1]
    occurred = _event_close(candle, normalized_timeframe)

    direction = str(state.get("direction") or "").strip().lower()
    if direction not in {"bullish", "bearish"}:
        reasons.append("SMC_STRUCTURE_NOT_DIRECTIONAL")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    protected_id = str(state.get("protected_swing_id") or "").strip()
    try:
        protected_level = float(state["protected_swing_level"])
    except (KeyError, TypeError, ValueError, OverflowError):
        protected_level = 0.0
    provenance = state.get("protected_provenance")
    if (
        not protected_id
        or not isfinite(protected_level)
        or protected_level <= 0
        or not isinstance(provenance, dict)
        or str(provenance.get("source_bos_id") or "").strip()
        != str(state.get("source_bos_id") or "").strip()
        or str(provenance.get("protected_swing_id") or "").strip() != protected_id
    ):
        reasons.append("SMC_PROTECTED_SOURCE_UNAVAILABLE")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    protected_updated_at = state.get("protected_updated_at")
    if not protected_updated_at:
        reasons.append("SMC_PROTECTED_TIMESTAMP_UNAVAILABLE")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if occurred <= _parse_utc_timestamp(protected_updated_at, "protected_updated_at"):
        reasons.append("SMC_CHOCH_BEFORE_PROTECTED_UPDATE")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    candidate_direction = "bearish" if direction == "bullish" else "bullish"
    bearish_break = direction == "bullish" and candle.close < protected_level - buffer
    bullish_break = direction == "bearish" and candle.close > protected_level + buffer
    if not bearish_break and not bullish_break:
        wick_only = (
            direction == "bullish"
            and candle.low < protected_level - buffer
            and candle.close >= protected_level - buffer
        ) or (
            direction == "bearish"
            and candle.high > protected_level + buffer
            and candle.close <= protected_level + buffer
        )
        reasons.append(
            "SMC_WICK_ONLY_CHOCH_BREAK"
            if wick_only
            else "SMC_CHOCH_BREAK_NOT_CONFIRMED"
        )
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    if (
        str(state.get("candidate_status") or "").strip().lower() == "candidate"
        and str(state.get("candidate_broken_protected_swing_id") or "").strip()
        == protected_id
        and str(state.get("candidate_direction") or "").strip().lower()
        == candidate_direction
    ):
        reasons.append("SMC_CHOCH_CANDIDATE_ALREADY_ACTIVE")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if (
        str(state.get("candidate_status") or "").strip().lower() == "expired"
        and str(state.get("candidate_broken_protected_swing_id") or "").strip()
        == protected_id
    ):
        reasons.append("SMC_CHOCH_CANDIDATE_EXPIRED")
        return {
            "choch_candidate": False,
            "candidate": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    event_id = structure_candidate_identity(
        symbol=symbol,
        timeframe=normalized_timeframe,
        direction=candidate_direction,
        protected_swing_id=protected_id,
        occurred_at=occurred,
    )
    event_snapshot_id = snapshot_id or (
        "smc-snapshot-"
        + hashlib.sha256(
            "|".join((symbol, normalized_timeframe, occurred.isoformat())).encode("utf-8")
        ).hexdigest()[:20]
    )
    lifetime = _STRUCTURE_EVENT_LIFETIME_BARS[normalized_timeframe]
    expires_at = occurred + SMC_TIMEFRAME_INTERVALS[normalized_timeframe] * lifetime
    event = SmcStructureEvent(
        event_id=event_id,
        event_type="CHOCH_CANDIDATE",
        direction=candidate_direction,
        source_level=protected_level,
        occurred_at=occurred.isoformat(),
        broken_level_id=protected_id,
        protected_swing_id=protected_id,
        expires_at=expires_at.isoformat(),
        snapshot_id=event_snapshot_id,
        reason_codes=("CHOCH_PROTECTED_BREAK", "SMC_STRICT_BREAK_BUFFER"),
    ).to_dict()
    updated_state = dict(state)
    updated_state.update(
        {
            "candidate_id": event_id,
            "candidate_event_id": event_id,
            "candidate_event": event,
            "candidate_status": "candidate",
            "candidate_direction": candidate_direction,
            "candidate_broken_protected_swing_id": protected_id,
            "candidate_break_at": occurred.isoformat(),
            "candidate_expires_at": expires_at.isoformat(),
            "candidate_source_bos_id": state.get("source_bos_id"),
            "candidate_prebreak_tracked_id": state.get("tracked_continuation_id"),
            "candidate_prebreak_tracked_level": state.get("tracked_continuation_level"),
        }
    )
    reasons.append("SMC_CHOCH_CANDIDATE_CREATED")
    return {
        "choch_candidate": True,
        "candidate": event,
        "break_buffer": buffer,
        "structure_state": updated_state,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def invalidate_choch_candidate_on_reclaim(
    candles: Sequence[Candle],
    *,
    timeframe: str = "H4",
    structure_state: dict[str, Any] | None = None,
    candidate_event: dict[str, Any] | SmcStructureEvent | None = None,
    as_of: datetime | str | None = None,
    break_buffer: float | int | None = None,
    atr_value: float | int | None = None,
    tick_size: float | int | None = None,
) -> dict[str, Any]:
    """Invalidate an unconfirmed CHoCH candidate on a causal reclaim.

    Reclaim is inclusive at the protected-level boundary.  The function only
    looks after the candidate break, preserves the active trend/protected
    cursor, and writes the invalidation timestamp onto the original event.
    Confirmation and follow-through are owned by later tasks.
    """

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")
    state = dict(structure_state or {})
    reasons = list(state.get("reason_codes", ()))
    if (
        str(state.get("candidate_status") or "").strip().lower() == "invalidated"
        and state.get("candidate_event")
    ):
        reasons.append("SMC_CHOCH_CANDIDATE_ALREADY_INVALIDATED")
        return {
            "invalidated": False,
            "event": None,
            "invalidated_event_id": state.get("candidate_event_id") or state.get("candidate_id"),
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if str(state.get("candidate_status") or "").strip().lower() == "expired":
        reasons.append("SMC_CHOCH_CANDIDATE_EXPIRED")
        return {
            "invalidated": False,
            "event": None,
            "invalidated_event_id": state.get("candidate_event_id") or state.get("candidate_id"),
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    event_value = candidate_event if candidate_event is not None else state.get("candidate_event")
    try:
        event = (
            event_value
            if isinstance(event_value, SmcStructureEvent)
            else SmcStructureEvent.from_dict(event_value)
        )
    except (TypeError, ValueError, KeyError):
        reasons.append("SMC_CHOCH_CANDIDATE_UNAVAILABLE")
        return {
            "invalidated": False,
            "event": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if event.event_type != "CHOCH_CANDIDATE":
        reasons.append("SMC_CHOCH_CANDIDATE_REQUIRED")
        return {
            "invalidated": False,
            "event": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if event.confirmed_at is not None:
        reasons.append("SMC_CHOCH_CANDIDATE_ALREADY_CONFIRMED")
        return {
            "invalidated": False,
            "event": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if event.invalidated_at is not None:
        reasons.append("SMC_CHOCH_CANDIDATE_ALREADY_INVALIDATED")
        return {
            "invalidated": False,
            "event": None,
            "invalidated_event_id": event.event_id,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    buffer = None
    if break_buffer is not None:
        try:
            buffer = float(break_buffer)
        except (TypeError, ValueError, OverflowError):
            buffer = None
        if buffer is not None and (not isfinite(buffer) or buffer <= 0):
            buffer = None
    else:
        buffer = structure_break_buffer(atr_value=atr_value, tick_size=tick_size)
    if buffer is None:
        reasons.append("SMC_BREAK_BUFFER_UNAVAILABLE")
        return {
            "invalidated": False,
            "event": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    protected_id = str(state.get("protected_swing_id") or "").strip()
    try:
        protected_level = float(state["protected_swing_level"])
    except (KeyError, TypeError, ValueError, OverflowError):
        protected_level = 0.0
    provenance = state.get("protected_provenance")
    if (
        not protected_id
        or event.protected_swing_id != protected_id
        or not isfinite(protected_level)
        or protected_level <= 0
        or not isinstance(provenance, dict)
        or str(provenance.get("protected_swing_id") or "").strip() != protected_id
        or str(provenance.get("source_bos_id") or "").strip()
        != str(state.get("source_bos_id") or "").strip()
    ):
        reasons.append("SMC_PROTECTED_SOURCE_UNAVAILABLE")
        return {
            "invalidated": False,
            "event": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    candidate_break = _parse_utc_timestamp(event.occurred_at, "candidate.occurred_at")
    cutoff = _parse_utc_timestamp(as_of, "as_of") if as_of is not None else None
    eligible_candles = sorted(
        (
            candle
            for candle in candles
            if isinstance(candle, Candle)
            and _event_close(candle, normalized_timeframe) > candidate_break
            and (cutoff is None or _event_close(candle, normalized_timeframe) <= cutoff)
        ),
        key=lambda candle: _event_close(candle, normalized_timeframe),
    )
    if not eligible_candles:
        reasons.append("SMC_NO_CLOSED_CANDLE_AFTER_CANDIDATE")
        return {
            "invalidated": False,
            "event": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    reclaim_candle = None
    if event.direction == "bearish":
        reclaim_candle = next(
            (
                candle
                for candle in eligible_candles
                if candle.close >= protected_level + buffer
            ),
            None,
        )
    elif event.direction == "bullish":
        reclaim_candle = next(
            (
                candle
                for candle in eligible_candles
                if candle.close <= protected_level - buffer
            ),
            None,
        )
    else:
        reasons.append("SMC_CHOCH_DIRECTION_INVALID")
        reclaim_candle = None
    if reclaim_candle is None:
        reasons.append("SMC_CHOCH_RECLAIM_NOT_CONFIRMED")
        return {
            "invalidated": False,
            "event": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    invalidated_at = _event_close(reclaim_candle, normalized_timeframe)
    invalidated_event = SmcStructureEvent(
        event_id=event.event_id,
        event_type=event.event_type,
        direction=event.direction,
        source_level=event.source_level,
        occurred_at=event.occurred_at,
        broken_level_id=event.broken_level_id,
        source_swing_id=event.source_swing_id,
        protected_swing_id=event.protected_swing_id,
        confirmed_at=None,
        expires_at=event.expires_at,
        invalidated_at=invalidated_at.isoformat(),
        snapshot_id=event.snapshot_id,
        reason_codes=tuple(
            dict.fromkeys((*event.reason_codes, "CHOCH_RECLAIM_BEFORE_CONFIRMATION"))
        ),
    ).to_dict()
    updated_state = dict(state)
    updated_state.update(
        {
            "candidate_event": invalidated_event,
            "candidate_status": "invalidated",
            "candidate_invalidated_at": invalidated_at.isoformat(),
            "candidate_invalidation_reason": "reclaim_before_confirmation",
            "candidate_confirmed_at": None,
            "choch_confirmed": False,
        }
    )
    reasons.append("SMC_CHOCH_CANDIDATE_INVALIDATED")
    return {
        "invalidated": True,
        "event": invalidated_event,
        "break_buffer": buffer,
        "structure_state": updated_state,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def confirm_choch_candidate(
    swings: dict[str, list[dict[str, Any]]],
    candles: Sequence[Candle],
    *,
    timeframe: str = "H4",
    symbol: str = "",
    structure_state: dict[str, Any] | None = None,
    candidate_event: dict[str, Any] | SmcStructureEvent | None = None,
    as_of: datetime | str | None = None,
    break_buffer: float | int | None = None,
    atr_value: float | int | None = None,
    tick_size: float | int | None = None,
    equal_tolerance: float = 0.0,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Confirm CHoCH only after candidate-local LH/HL and a new BOS.

    The prior trend's leg count is intentionally not consulted.  Every swing
    and break is bounded by the candidate break, the current candle close,
    confirmation timestamps, and the supplied cutoff.
    """

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    if not isfinite(float(equal_tolerance)) or float(equal_tolerance) < 0:
        raise ValueError("equal_tolerance must be finite and non-negative")
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")
    state = dict(structure_state or {})
    reasons = list(state.get("reason_codes", ()))
    event_value = candidate_event if candidate_event is not None else state.get("candidate_event")
    try:
        event = (
            event_value
            if isinstance(event_value, SmcStructureEvent)
            else SmcStructureEvent.from_dict(event_value)
        )
    except (TypeError, ValueError, KeyError):
        reasons.append("SMC_CHOCH_CANDIDATE_UNAVAILABLE")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if event.event_type == "CHOCH_CONFIRMED" or (
        str(state.get("candidate_status") or "").strip().lower() == "confirmed"
    ):
        reasons.append("SMC_CHOCH_ALREADY_CONFIRMED")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if str(state.get("candidate_status") or "").strip().lower() == "expired":
        reasons.append("SMC_CHOCH_CANDIDATE_EXPIRED")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if event.event_type != "CHOCH_CANDIDATE" or event.confirmed_at is not None:
        reasons.append("SMC_CHOCH_CANDIDATE_REQUIRED")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    if event.invalidated_at is not None or str(state.get("candidate_status") or "").strip().lower() == "invalidated":
        reasons.append("SMC_CHOCH_CANDIDATE_INVALIDATED")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    buffer = None
    if break_buffer is not None:
        try:
            buffer = float(break_buffer)
        except (TypeError, ValueError, OverflowError):
            buffer = None
        if buffer is not None and (not isfinite(buffer) or buffer <= 0):
            buffer = None
    else:
        buffer = structure_break_buffer(atr_value=atr_value, tick_size=tick_size)
    if buffer is None:
        reasons.append("SMC_BREAK_BUFFER_UNAVAILABLE")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    cutoff = _parse_utc_timestamp(as_of, "as_of") if as_of is not None else None
    if cutoff is not None and event.expires_at is not None and cutoff >= _parse_utc_timestamp(
        event.expires_at,
        "candidate.expires_at",
    ):
        updated_state = dict(state)
        updated_state.update(
            {
                "candidate_status": "expired",
                "candidate_expired_at": cutoff.isoformat(),
                "candidate_expiry_reason": "structure_event_lifetime",
                "candidate_confirmed_at": None,
                "choch_confirmed": False,
            }
        )
        reasons.append("SMC_CHOCH_CANDIDATE_EXPIRED")
        return {
            "choch_confirmed": False,
            "candidate": event.to_dict(),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": updated_state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    reclaim_result = invalidate_choch_candidate_on_reclaim(
        candles,
        timeframe=normalized_timeframe,
        structure_state=state,
        candidate_event=event,
        as_of=as_of,
        break_buffer=buffer,
    )
    if reclaim_result.get("invalidated"):
        reasons.extend(reclaim_result.get("reason_codes", ()))
        return {
            "choch_confirmed": False,
            "candidate": reclaim_result.get("event"),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": reclaim_result["structure_state"],
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    prior_direction = str(state.get("direction") or "").strip().lower()
    candidate_direction = event.direction
    if prior_direction not in {"bullish", "bearish"} or candidate_direction != (
        "bearish" if prior_direction == "bullish" else "bullish"
    ):
        reasons.append("SMC_CHOCH_DIRECTION_INVALID")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    protected_id = str(state.get("protected_swing_id") or "").strip()
    if not protected_id or event.protected_swing_id != protected_id:
        reasons.append("SMC_PROTECTED_SOURCE_UNAVAILABLE")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    try:
        prebreak_level = float(state["candidate_prebreak_tracked_level"])
    except (KeyError, TypeError, ValueError, OverflowError):
        prebreak_level = 0.0
    if not isfinite(prebreak_level) or prebreak_level <= 0:
        reasons.append("SMC_PREBREAK_CONTINUATION_UNAVAILABLE")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    candidate_break = _parse_utc_timestamp(event.occurred_at, "candidate.occurred_at")
    closed_at = sorted(
        (
            (_event_close(candle, normalized_timeframe), candle)
            for candle in candles
            if isinstance(candle, Candle)
            and _event_close(candle, normalized_timeframe) > candidate_break
            and (cutoff is None or _event_close(candle, normalized_timeframe) <= cutoff)
        ),
        key=lambda item: item[0],
    )
    if not closed_at:
        reasons.append("SMC_NO_CLOSED_CANDLE_AFTER_CANDIDATE")
        return {
            "choch_confirmed": False,
            "candidate": None,
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    occurred, break_candle = closed_at[-1]
    if cutoff is None and event.expires_at is not None and occurred >= _parse_utc_timestamp(
        event.expires_at,
        "candidate.expires_at",
    ):
        updated_state = dict(state)
        updated_state.update(
            {
                "candidate_status": "expired",
                "candidate_expired_at": occurred.isoformat(),
                "candidate_expiry_reason": "structure_event_lifetime",
                "candidate_confirmed_at": None,
                "choch_confirmed": False,
            }
        )
        reasons.append("SMC_CHOCH_CANDIDATE_EXPIRED")
        return {
            "choch_confirmed": False,
            "candidate": event.to_dict(),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": updated_state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    normalized = normalize_swing_sequence(swings)

    def causal_swings(kind: str) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for item in normalized[kind + "s"]:
            if item.get("confirmed") is not True or item.get("usable") is False or item.get("provisional") is True:
                continue
            try:
                pivot_time = _parse_utc_timestamp(
                    item.get("pivot_time", item.get("time")),
                    "candidate_swing.pivot_time",
                )
                confirmed_at = _parse_utc_timestamp(
                    item.get("confirmed_at"),
                    "candidate_swing.confirmed_at",
                )
                level = float(item["level"])
            except (KeyError, TypeError, ValueError, OverflowError):
                continue
            if pivot_time <= candidate_break or confirmed_at > occurred:
                continue
            if not isfinite(level) or level <= 0:
                continue
            record = dict(item)
            record["_pivot"] = pivot_time
            record["_confirmed"] = confirmed_at
            record["_level"] = level
            records.append(record)
        return records

    if candidate_direction == "bearish":
        lh_candidates = [
            item
            for item in causal_swings("high")
            if item["_level"] <= prebreak_level - float(equal_tolerance)
        ]
        lh_candidates.sort(key=lambda item: (item["_pivot"], item["_confirmed"], item["swing_id"]))
        lh = lh_candidates[0] if lh_candidates else None
        continuation_kind = "low"
    else:
        lh_candidates = [
            item
            for item in causal_swings("low")
            if item["_level"] >= prebreak_level + float(equal_tolerance)
        ]
        lh_candidates.sort(key=lambda item: (item["_pivot"], item["_confirmed"], item["swing_id"]))
        lh = lh_candidates[0] if lh_candidates else None
        continuation_kind = "high"

    updated_state = dict(state)
    if lh is None:
        reasons.append("SMC_CHOCH_WAITING_LH" if candidate_direction == "bearish" else "SMC_CHOCH_WAITING_HL")
        return {
            "choch_confirmed": False,
            "candidate": event.to_dict(),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": updated_state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    updated_state["candidate_lh_id"] = str(lh["swing_id"])
    updated_state["candidate_lh_level"] = lh["_level"]
    updated_state["candidate_lh_pivot_time"] = lh["_pivot"].isoformat()
    updated_state["candidate_lh_confirmed_at"] = lh["_confirmed"].isoformat()

    continuation_candidates = [
        item
        for item in causal_swings(continuation_kind)
        if item["_pivot"] > lh["_pivot"]
    ]
    continuation_candidates.sort(
        key=lambda item: (item["_pivot"], item["_confirmed"], item["swing_id"])
    )
    continuation = continuation_candidates[0] if continuation_candidates else None
    if continuation is None:
        reasons.append("SMC_CHOCH_WAITING_CONTINUATION_SWING")
        return {
            "choch_confirmed": False,
            "candidate": event.to_dict(),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": updated_state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    updated_state["candidate_continuation_low_id" if candidate_direction == "bearish" else "candidate_continuation_high_id"] = str(continuation["swing_id"])
    updated_state["candidate_continuation_level"] = continuation["_level"]
    updated_state["candidate_continuation_pivot_time"] = continuation["_pivot"].isoformat()
    updated_state["candidate_continuation_confirmed_at"] = continuation["_confirmed"].isoformat()

    reversal_break = (
        candidate_direction == "bearish"
        and break_candle.close < continuation["_level"] - buffer
    ) or (
        candidate_direction == "bullish"
        and break_candle.close > continuation["_level"] + buffer
    )
    if not reversal_break:
        reasons.append("SMC_CHOCH_WAITING_REVERSAL_BOS")
        return {
            "choch_confirmed": False,
            "candidate": event.to_dict(),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": updated_state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    source_kind = "high" if candidate_direction == "bearish" else "low"
    anchor_value = state.get("anchor_start_at") or state.get("source_history_anchor_at")
    if not anchor_value:
        reasons.append("SMC_SOURCE_HISTORY_ANCHOR_UNAVAILABLE")
        return {
            "choch_confirmed": False,
            "candidate": event.to_dict(),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": updated_state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    anchor = _parse_utc_timestamp(anchor_value, "anchor_start_at")
    source_candidates = [
        item
        for item in causal_swings(source_kind)
        if item["_pivot"] > anchor and item["_pivot"] < occurred
    ]
    if candidate_direction == "bearish":
        source_candidates.sort(key=lambda item: (item["_pivot"], item["_level"], item["swing_id"]))
    else:
        source_candidates.sort(key=lambda item: (item["_pivot"], -item["_level"], item["swing_id"]))
    source = source_candidates[-1] if source_candidates else None
    if source is None:
        reasons.append("SMC_REVERSAL_BOS_SOURCE_UNAVAILABLE")
        return {
            "choch_confirmed": False,
            "candidate": event.to_dict(),
            "reversal_bos": None,
            "break_buffer": buffer,
            "structure_state": updated_state,
            "reason_codes": list(dict.fromkeys(reasons)),
        }

    continuation_id = str(continuation["swing_id"])
    reversal_event_id = structure_event_identity(
        symbol=symbol,
        timeframe=normalized_timeframe,
        direction=candidate_direction,
        broken_level_id=continuation_id,
        occurred_at=occurred,
    )
    reversal_event = SmcStructureEvent(
        event_id=reversal_event_id,
        event_type="BOS",
        direction=candidate_direction,
        source_level=continuation["_level"],
        occurred_at=occurred.isoformat(),
        broken_level_id=continuation_id,
        source_swing_id=str(source["swing_id"]),
        confirmed_at=occurred.isoformat(),
        expires_at=(
            occurred
            + SMC_TIMEFRAME_INTERVALS[normalized_timeframe]
            * _STRUCTURE_EVENT_LIFETIME_BARS[normalized_timeframe]
        ).isoformat(),
        snapshot_id=snapshot_id or event.snapshot_id,
        reason_codes=("REVERSAL_BOS_CONFIRMED", "SMC_STRICT_BREAK_BUFFER"),
    ).to_dict()
    confirmed_event_id = confirmed_choch_identity(
        candidate_event_id=event.event_id,
        reversal_bos_id=reversal_event_id,
    )
    confirmed_event = SmcStructureEvent(
        event_id=confirmed_event_id,
        event_type="CHOCH_CONFIRMED",
        direction=candidate_direction,
        source_level=continuation["_level"],
        occurred_at=event.occurred_at,
        broken_level_id=continuation_id,
        source_swing_id=str(source["swing_id"]),
        protected_swing_id=protected_id,
        confirmed_at=occurred.isoformat(),
        expires_at=event.expires_at,
        snapshot_id=snapshot_id or event.snapshot_id,
        reason_codes=("CHOCH_CONFIRMED_AFTER_FOLLOW_THROUGH",),
    ).to_dict()
    updated_state = apply_protected_swing_from_bos(updated_state, reversal_event, swings)
    updated_events = list(updated_state.get("structure_events", ()))
    updated_events.extend((reversal_event, confirmed_event))
    updated_state.update(
        {
            "state": "bearish" if candidate_direction == "bearish" else "bullish",
            "structure": "LH/LL" if candidate_direction == "bearish" else "HH/HL",
            "direction": candidate_direction,
            "tracked_continuation_id": continuation_id,
            "tracked_continuation_level": continuation["_level"],
            "candidate_event": confirmed_event,
            "candidate_status": "confirmed",
            "candidate_confirmed_at": occurred.isoformat(),
            "choch_confirmed": True,
            "reversal_bos_id": reversal_event_id,
            "structure_events": updated_events,
            "anchor_start_at": occurred.isoformat(),
            "last_bos_event_id": reversal_event_id,
            "last_broken_level_id": continuation_id,
            "last_bos_direction": candidate_direction,
        }
    )
    reasons.extend(("SMC_REVERSAL_BOS_CONFIRMED", "SMC_CHOCH_CONFIRMED"))
    return {
        "choch_confirmed": True,
        "candidate": confirmed_event,
        "reversal_bos": reversal_event,
        "break_buffer": buffer,
        "structure_state": updated_state,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def expire_structure_events(
    structure_state: dict[str, Any],
    *,
    as_of: datetime | str,
    events: Sequence[dict[str, Any] | SmcStructureEvent] | None = None,
) -> dict[str, Any]:
    """Mark structure events expired without deleting history or protection."""

    cutoff = _parse_utc_timestamp(as_of, "as_of")
    state = dict(structure_state or {})
    reasons = list(state.get("reason_codes", ()))
    history: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    candidates = list(state.get("structure_events", ()))
    candidate_event = state.get("candidate_event")
    if candidate_event is not None:
        candidates.append(candidate_event)
    candidates.extend(events or ())
    lifecycle = dict(state.get("event_lifecycle", {}))
    expired_ids = list(dict.fromkeys(state.get("expired_event_ids", ())))
    newly_expired: list[str] = []

    for raw_event in candidates:
        try:
            event = (
                raw_event
                if isinstance(raw_event, SmcStructureEvent)
                else SmcStructureEvent.from_dict(raw_event)
            )
        except (TypeError, ValueError, KeyError):
            reasons.append("SMC_STRUCTURE_EVENT_INVALID")
            continue
        event_id = event.event_id
        if event_id not in seen_ids:
            history.append(event.to_dict())
            seen_ids.add(event_id)
        if event.invalidated_at is not None:
            lifecycle[event_id] = "invalidated"
            continue
        if lifecycle.get(event_id) in {"invalidated", "confirmed"}:
            continue
        if event.expires_at is not None and cutoff >= _parse_utc_timestamp(
            event.expires_at,
            "event.expires_at",
        ):
            lifecycle[event_id] = "expired"
            if event_id not in expired_ids:
                expired_ids.append(event_id)
                newly_expired.append(event_id)
        else:
            lifecycle.setdefault(event_id, "active")

    candidate_id = str(state.get("candidate_event_id") or state.get("candidate_id") or "").strip()
    candidate_status = str(state.get("candidate_status") or "").strip().lower()
    candidate_event_value = state.get("candidate_event")
    candidate_event_type = ""
    if isinstance(candidate_event_value, dict):
        candidate_event_type = str(
            candidate_event_value.get("event_type") or ""
        ).strip().upper()
    if candidate_id and (candidate_status == "confirmed" or candidate_event_type == "CHOCH_CONFIRMED"):
        # The original candidate trigger may expire after the transition, but
        # the terminal confirmation owns the candidate lifecycle from here.
        lifecycle[candidate_id] = "confirmed"
    if candidate_id and lifecycle.get(candidate_id) == "expired" and candidate_status != "confirmed":
        state.update(
            {
                "candidate_status": "expired",
                "candidate_expired_at": cutoff.isoformat(),
                "candidate_expiry_reason": "structure_event_lifetime",
                "candidate_confirmed_at": None,
                "choch_confirmed": False,
            }
        )
        reasons.append("SMC_CHOCH_CANDIDATE_EXPIRED")
    active_trigger_ids = [
        event_id
        for event_id, status in lifecycle.items()
        if status == "active"
    ]
    state.update(
        {
            "structure_events": history,
            "event_lifecycle": lifecycle,
            "expired_event_ids": expired_ids,
            "expired_trigger_ids": expired_ids,
            "active_trigger_event_ids": active_trigger_ids,
            "last_expiry_as_of": cutoff.isoformat(),
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    )
    return {
        "expired": bool(newly_expired),
        "expired_event_ids": newly_expired,
        "events": history,
        "structure_state": state,
        "reason_codes": list(dict.fromkeys(reasons)),
    }


def detect_structure_bos(
    swings: dict[str, list[dict[str, Any]]],
    candles: Sequence[Candle],
    *,
    timeframe: str = "H4",
    symbol: str = "",
    structure_state: dict[str, Any] | None = None,
    as_of: datetime | str | None = None,
    break_buffer: float | int | None = None,
    atr_value: float | int | None = None,
    tick_size: float | int | None = None,
    snapshot_id: str | None = None,
    existing_events: Sequence[dict[str, Any] | SmcStructureEvent] | None = None,
) -> dict[str, Any]:
    """Evaluate one causal continuation BOS and its protected source swing.

    This is intentionally narrower than the legacy ``detect_bos_choch``
    helper.  It only emits a continuation BOS from the latest closed candle;
    CHoCH/candidate transitions are later tasks.  ``existing_events`` and the
    state history implement the replay-prefix rule: one BOS per broken level
    and direction, while a different broken level remains eligible.
    """

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")

    state = dict(
        structure_state
        if structure_state is not None
        else initialize_structure_state(swings, as_of=as_of)
    )
    state.setdefault("structure_events", [])
    reason_codes = list(state.get("reason_codes", ()))
    buffer = None
    if break_buffer is not None:
        try:
            buffer = float(break_buffer)
        except (TypeError, ValueError, OverflowError):
            buffer = None
        if buffer is not None and (not isfinite(buffer) or buffer <= 0):
            buffer = None
    else:
        buffer = structure_break_buffer(atr_value=atr_value, tick_size=tick_size)
    if buffer is None:
        reason_codes.append("SMC_BREAK_BUFFER_UNAVAILABLE")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": None,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    eligible_candles = [candle for candle in candles if isinstance(candle, Candle)]
    if not eligible_candles:
        reason_codes.append("SMC_NO_CLOSED_CANDLE")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }
    cutoff = _parse_utc_timestamp(as_of, "as_of") if as_of is not None else None
    if cutoff is not None:
        eligible_candles = [
            candle
            for candle in eligible_candles
            if _event_close(candle, normalized_timeframe) <= cutoff
        ]
    if not eligible_candles:
        reason_codes.append("SMC_NO_CLOSED_CANDLE")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }
    candle = eligible_candles[-1]
    occurred = _event_close(candle, normalized_timeframe)
    ready_at = state.get("bootstrap_ready_at")
    if not ready_at or occurred < _parse_utc_timestamp(ready_at, "bootstrap_ready_at"):
        reason_codes.append("SMC_BOS_BEFORE_BOOTSTRAP_READY")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    direction = str(state.get("direction") or "").strip().lower()
    tracked_id = str(state.get("tracked_continuation_id") or "").strip()
    if direction not in {"bullish", "bearish"} or not tracked_id:
        reason_codes.append("SMC_STRUCTURE_NOT_DIRECTIONAL")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    normalized = normalize_swing_sequence(swings)
    all_swings = normalized["highs"] + normalized["lows"]
    tracked = next(
        (item for item in all_swings if str(item.get("swing_id") or "") == tracked_id),
        None,
    )
    if tracked is None or tracked.get("provisional") is True:
        reason_codes.append("SMC_CONTINUATION_REFERENCE_UNAVAILABLE")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    tracked_level = float(tracked["level"])
    bullish_break = direction == "bullish" and candle.close > tracked_level + buffer
    bearish_break = direction == "bearish" and candle.close < tracked_level - buffer
    if not bullish_break and not bearish_break:
        wick_only = (
            direction == "bullish"
            and candle.high > tracked_level + buffer
            and candle.close <= tracked_level + buffer
        ) or (
            direction == "bearish"
            and candle.low < tracked_level - buffer
            and candle.close >= tracked_level - buffer
        )
        if wick_only:
            reason_codes.append("SMC_WICK_ONLY_BREAK")
        else:
            reason_codes.append("SMC_BREAK_NOT_CONFIRMED")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    def as_event_dict(value: dict[str, Any] | SmcStructureEvent) -> dict[str, Any] | None:
        if isinstance(value, SmcStructureEvent):
            return value.to_dict()
        if isinstance(value, dict):
            return value
        return None

    known_events: list[dict[str, Any]] = []
    for value in tuple(state.get("structure_events", ())) + tuple(existing_events or ()):
        event_value = as_event_dict(value)
        if event_value is not None:
            known_events.append(event_value)
    known_bos = [
        item
        for item in known_events
        if str(item.get("event_type") or "").strip().upper() == "BOS"
        and str(item.get("direction") or "").strip().lower() == direction
        and str(item.get("broken_level_id") or "").strip() == tracked_id
    ]
    if known_bos or (
        str(state.get("last_bos_direction") or "").strip().lower() == direction
        and str(state.get("last_broken_level_id") or "").strip() == tracked_id
    ):
        duplicate = known_bos[-1] if known_bos else None
        reason_codes.append("SMC_BOS_ALREADY_EMITTED")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "replayed_event_id": duplicate.get("event_id") if duplicate else state.get("last_bos_event_id"),
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    anchor_start = state.get("anchor_start_at") or state.get("source_history_anchor_at")
    if not anchor_start:
        reason_codes.append("SMC_SOURCE_HISTORY_ANCHOR_UNAVAILABLE")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }
    anchor = _parse_utc_timestamp(anchor_start, "anchor_start_at")
    source_kind = "low" if direction == "bullish" else "high"
    source_candidates: list[dict[str, Any]] = []
    for item in normalized[source_kind + "s"]:
        if item.get("confirmed") is not True or item.get("usable") is False:
            continue
        if item.get("provisional") is True:
            continue
        try:
            pivot_time = _parse_utc_timestamp(
                item.get("pivot_time", item.get("time")),
                "source_swing.pivot_time",
            )
            confirmed_at = _parse_utc_timestamp(
                item.get("confirmed_at"),
                "source_swing.confirmed_at",
            )
            level = float(item["level"])
        except (KeyError, TypeError, ValueError, OverflowError):
            continue
        if pivot_time <= anchor or pivot_time >= occurred or confirmed_at > occurred:
            continue
        if not isfinite(level) or level <= 0:
            continue
        source_candidates.append(item)
    if direction == "bullish":
        source_candidates.sort(
            key=lambda item: (
                item.get("pivot_time", item.get("time", "")),
                -float(item["level"]),
                str(item.get("swing_id") or ""),
            )
        )
    else:
        source_candidates.sort(
            key=lambda item: (
                item.get("pivot_time", item.get("time", "")),
                float(item["level"]),
                str(item.get("swing_id") or ""),
            )
        )
    source = source_candidates[-1] if source_candidates else None
    if source is None:
        reason_codes.append("SMC_BOS_SOURCE_UNAVAILABLE")
        return {
            "bos": False,
            "event": None,
            "events": [],
            "break_buffer": buffer,
            "structure_state": state,
            "reason_codes": list(dict.fromkeys(reason_codes)),
        }

    close_text = occurred.isoformat()
    source_id = str(source["swing_id"])
    event_id = structure_event_identity(
        symbol=symbol,
        timeframe=normalized_timeframe,
        direction=direction,
        broken_level_id=tracked_id,
        occurred_at=occurred,
    )
    event_snapshot_id = snapshot_id or (
        "smc-snapshot-"
        + hashlib.sha256(
            "|".join((symbol, normalized_timeframe, close_text)).encode("utf-8")
        ).hexdigest()[:20]
    )
    lifetime = _STRUCTURE_EVENT_LIFETIME_BARS[normalized_timeframe]
    expires_at = occurred + SMC_TIMEFRAME_INTERVALS[normalized_timeframe] * lifetime
    event = SmcStructureEvent(
        event_id=event_id,
        event_type="BOS",
        direction=direction,
        source_level=tracked_level,
        occurred_at=close_text,
        broken_level_id=tracked_id,
        source_swing_id=source_id,
        confirmed_at=close_text,
        expires_at=expires_at.isoformat(),
        snapshot_id=event_snapshot_id,
        reason_codes=("BOS_CLOSE_CONFIRMED", "SMC_STRICT_BREAK_BUFFER"),
    ).to_dict()
    updated_state = apply_protected_swing_from_bos(state, event, swings)
    updated_events = list(state.get("structure_events", ()))
    updated_events.append(event)
    updated_state.update(
        {
            "anchor_start_at": close_text,
            "last_bos_event_id": event_id,
            "last_broken_level_id": tracked_id,
            "last_bos_direction": direction,
            "structure_events": updated_events,
        }
    )
    return {
        "bos": True,
        "event": event,
        "events": [event],
        "break_buffer": buffer,
        "structure_state": updated_state,
        "reason_codes": list(dict.fromkeys(reason_codes + ["BOS_CONFIRMED"])),
    }


def _filter_swings_by_atr(candles: list[Candle], swings: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    """Filter swing points: keep only those at least 0.2×ATR from previous swing."""
    if len(candles) < _ATR_FILTER_MIN_CANDLES:
        return swings
    closes = [c.close for c in candles]
    highs_atr = [c.high for c in candles]
    lows_atr = [c.low for c in candles]
    atr_values = atr(highs_atr, lows_atr, closes, _ATR_PERIOD)
    atr_now = atr_values[-1] if atr_values and atr_values[-1] is not None else 0.0
    if atr_now <= 0:
        return swings
    min_distance = atr_now * _ATR_DISTANCE_MULT
    highs = swings["highs"]
    lows = swings["lows"]
    filtered_highs: list[dict[str, Any]] = []
    filtered_lows: list[dict[str, Any]] = []
    for h in highs:
        if not filtered_highs or abs(h["level"] - filtered_highs[-1]["level"]) >= min_distance:
            filtered_highs.append(h)
    for lo in lows:
        if not filtered_lows or abs(lo["level"] - filtered_lows[-1]["level"]) >= min_distance:
            filtered_lows.append(lo)
    return {"highs": filtered_highs, "lows": filtered_lows}


def _legacy_count_trend_legs(swings: dict[str, list[dict[str, Any]]]) -> int:
    """Pre-stage-B leg counter retained for the public production route."""

    highs = swings["highs"]
    lows = swings["lows"]
    if len(highs) < 2 or len(lows) < 2:
        return 0
    last_h = highs[-1]["level"]
    prev_h = highs[-2]["level"]
    last_l = lows[-1]["level"]
    prev_l = lows[-2]["level"]
    if last_h > prev_h and last_l > prev_l:
        count = 1
        max_i = min(len(highs), len(lows))
        for i in range(2, max_i):
            if highs[-i]["level"] > highs[-(i + 1)]["level"] and lows[-i]["level"] > lows[-(i + 1)]["level"]:
                count += 1
            else:
                break
        return count
    if last_h < prev_h and last_l < prev_l:
        count = 1
        max_i = min(len(highs), len(lows))
        for i in range(2, max_i):
            if highs[-i]["level"] < highs[-(i + 1)]["level"] and lows[-i]["level"] < lows[-(i + 1)]["level"]:
                count += 1
            else:
                break
        return count
    return 0


def _legacy_detect_internal_structure(
    candles: list[Candle],
    external_swings: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """Pre-stage-B internal payload retained for Analyze/Scanner parity."""

    if not candles:
        return {"highs": [], "lows": []}
    external_highs = external_swings.get("highs", [])
    external_lows = external_swings.get("lows", [])
    all_external = sorted(external_highs + external_lows, key=lambda item: item["index"])
    if len(all_external) < 2:
        return {"highs": [], "lows": []}

    internal_highs: list[dict[str, Any]] = []
    internal_lows: list[dict[str, Any]] = []
    for index in range(len(all_external) - 1):
        start_idx = all_external[index]["index"]
        end_idx = all_external[index + 1]["index"]
        if end_idx - start_idx < 6:
            continue
        segment = candles[start_idx:end_idx + 1]
        segment_swings = swing_points(segment, lookback=_SMC_LOOKBACK_INTERNAL)
        offset = start_idx
        for high in segment_swings["highs"]:
            high_copy = dict(high)
            high_copy["index"] = high["index"] + offset
            high_copy["leg"] = index
            internal_highs.append(high_copy)
        for low in segment_swings["lows"]:
            low_copy = dict(low)
            low_copy["index"] = low["index"] + offset
            low_copy["leg"] = index
            internal_lows.append(low_copy)
    return {"highs": internal_highs, "lows": internal_lows}


def _count_trend_legs(swings: dict[str, list[dict[str, Any]]]) -> int:
    """Count consecutive legs in the current trend direction.

    High and low streams are normalized independently.  Their latest runs are
    combined by length, never by pairing list position ``highs[i]`` with
    ``lows[i]``.
    Returns 0 for mixed/unknown structure.
    """
    normalized = normalize_swing_sequence(swings)
    highs = normalized["highs"]
    lows = normalized["lows"]
    if len(highs) < 2 or len(lows) < 2:
        return 0

    def directional_run(values: list[dict[str, Any]], direction: int) -> int:
        count = 0
        for current, previous in zip(reversed(values), reversed(values[:-1])):
            delta = current["level"] - previous["level"]
            if (direction > 0 and delta > 0) or (direction < 0 and delta < 0):
                count += 1
            else:
                break
        return count

    bullish_pairs = min(directional_run(highs, 1), directional_run(lows, 1))
    bearish_pairs = min(directional_run(highs, -1), directional_run(lows, -1))
    if bullish_pairs:
        return bullish_pairs
    if bearish_pairs:
        return bearish_pairs
    return 0


def _detect_internal_structure(
    candles: list[Candle],
    external_swings: dict[str, list[dict[str, Any]]],
    *,
    symbol: str = "",
    timeframe: str = "H4",
) -> dict[str, list[dict[str, Any]]]:
    """Detect internal (minor) swings within each leg between external swings.

    For each consecutive pair of external swing points, extracts the candle
    segment between them and runs internal_swing_points(width=2) to find minor
    swings used for entry refinement.
    """
    if not candles:
        return {"highs": [], "lows": []}
    external_highs = external_swings.get("highs", [])
    external_lows = external_swings.get("lows", [])
    all_external = ordered_swing_sequence(external_swings)
    if len(all_external) < 2:
        return {"highs": [], "lows": []}

    internal_highs: list[dict[str, Any]] = []
    internal_lows: list[dict[str, Any]] = []
    for i in range(len(all_external) - 1):
        start_idx = all_external[i]["index"]
        end_idx = all_external[i + 1]["index"]
        if end_idx - start_idx < 6:
            continue
        segment = candles[start_idx:end_idx + 1]
        seg_swings = internal_swing_points(
            segment,
            symbol=symbol,
            timeframe=timeframe,
        )
        offset = start_idx
        for h in seg_swings["highs"]:
            h_copy = dict(h)
            h_copy["index"] = h["index"] + offset
            h_copy["leg"] = i
            internal_highs.append(h_copy)
        for lo in seg_swings["lows"]:
            lo_copy = dict(lo)
            lo_copy["index"] = lo["index"] + offset
            lo_copy["leg"] = i
            internal_lows.append(lo_copy)
    return {"highs": internal_highs, "lows": internal_lows}


def detect_bos_choch(swings: dict[str, list[dict[str, Any]]], candles: list[Candle], leg_count: int = 0) -> dict[str, Any]:
    highs = swings["highs"]
    lows = swings["lows"]
    if len(highs) < 2 or len(lows) < 2 or not candles:
        return {"structure": "unknown", "bos": False, "choch": False, "displacement": "neutral",
                "bos_strength": "weak", "choch_confirmed": False}

    last_high = highs[-1]["level"]
    prev_high = highs[-2]["level"]
    last_low = lows[-1]["level"]
    prev_low = lows[-2]["level"]
    last_close = candles[-1].close

    if last_high > prev_high and last_low > prev_low:
        structure = "HH/HL"
        prev_trend = "up"
    elif last_high < prev_high and last_low < prev_low:
        structure = "LH/LL"
        prev_trend = "down"
    else:
        structure = "mixed"
        prev_trend = "mixed"

    bos = False
    choch = False
    displacement = "neutral"

    if prev_trend == "up" and last_close > last_high:
        bos = True
        displacement = "bullish"
    elif prev_trend == "down" and last_close < last_low:
        bos = True
        displacement = "bearish"
    elif prev_trend == "up" and last_close < prev_low:
        choch = True
        displacement = "bearish"
    elif prev_trend == "down" and last_close > prev_high:
        choch = True
        displacement = "bullish"

    if bos:
        bos_strength = "strong" if leg_count >= _LEG_STRONG else "normal" if leg_count >= _LEG_NORMAL else "weak"
    else:
        bos_strength = "weak"
    choch_confirmed = choch and leg_count >= _CHOCH_CONFIRMED_LEGS

    return {"structure": structure, "bos": bos, "choch": choch, "displacement": displacement,
            "bos_strength": bos_strength, "choch_confirmed": choch_confirmed}


def detect_fvg(candles: list[Candle]) -> list[dict[str, Any]]:
    gaps: list[dict[str, Any]] = []
    if len(candles) < 3:
        return gaps
    start = max(0, len(candles) - _LOOKBACK_WINDOW)
    for index in range(start + 2, len(candles)):
        first = candles[index - 2]
        third = candles[index]
        if first.high < third.low:
            gaps.append(
                {
                    "type": "bullish_fvg",
                    "low": first.high,
                    "high": third.low,
                    "index": index,
                    "time": third.time.isoformat(),
                    "origin_index": index,
                    "origin_time": third.time.isoformat(),
                    "formation_start_index": index - 2,
                    "departure_end_index": index,
                    "displacement_multiple": displacement_multiple_at(candles, index),
                }
            )
        elif first.low > third.high:
            gaps.append(
                {
                    "type": "bearish_fvg",
                    "low": third.high,
                    "high": first.low,
                    "index": index,
                    "time": third.time.isoformat(),
                    "origin_index": index,
                    "origin_time": third.time.isoformat(),
                    "formation_start_index": index - 2,
                    "departure_end_index": index,
                    "displacement_multiple": displacement_multiple_at(candles, index),
                }
            )
    return gaps[-_MAX_FVG:]


def detect_order_block_candidates(
    candles: list[Candle],
    *,
    symbol: str = "",
    timeframe: str = "",
) -> list[dict[str, Any]]:
    """Detect opposite-colour base candles as unconfirmed OB candidates.

    This is a pure candidate seam for the staged SMC implementation.  It does
    not promote a zone, attach a structure confirmation, or make the result
    entry-eligible.  A one-candle base is intentional here; broader base
    policies belong to the later confirmation/detector tasks.
    """

    if len(candles) < 2:
        return []
    start = _detector_history_start(len(candles), timeframe, minimum=1)
    candidates: list[dict[str, Any]] = []
    for departure_index in range(start, len(candles)):
        base_index = departure_index - 1
        base = candles[base_index]
        departure = candles[departure_index]
        base_bearish = base.close < base.open
        base_bullish = base.close > base.open
        departure_bullish = (
            departure.close > departure.open
            and departure.close > base.high
        )
        departure_bearish = (
            departure.close < departure.open
            and departure.close < base.low
        )
        if base_bearish and departure_bullish:
            direction = "buy"
            zone_type = "bullish_order_block"
        elif base_bullish and departure_bearish:
            direction = "sell"
            zone_type = "bearish_order_block"
        else:
            continue

        measurement = measure_departure(
            departure,
            direction=direction,
            atr_before_event=atr_value_before_event(
                candles,
                timeframe=timeframe or "H1",
                event_index=departure_index,
            ) if departure_index >= _ATR_FILTER_MIN_CANDLES else None,
        )
        origin_time = base.time.isoformat()
        departure_time = departure.time.isoformat()
        zone_id = build_zone_id(
            symbol=symbol,
            timeframe=timeframe or "UNKNOWN",
            family="ob",
            direction=direction,
            origin_time=origin_time,
            low=base.low,
            high=base.high,
        )
        reason_codes = ["ZONE_CANDIDATE"]
        reason_codes.extend(measurement["reason_codes"])
        candidates.append({
            "zone_id": zone_id,
            "setup_id": build_setup_id(
                symbol=symbol,
                timeframe=timeframe or "UNKNOWN",
                direction=direction,
                departure_source=departure_time,
            ),
            "type": zone_type,
            "zone_type": zone_type,
            "family": "ob",
            "symbol": symbol,
            "timeframe": timeframe or "UNKNOWN",
            "direction": direction,
            "low": base.low,
            "high": base.high,
            "original_bounds": {"low": base.low, "high": base.high},
            "origin_index": base_index,
            "origin_time": origin_time,
            "formation_start_index": base_index,
            "formation_end_index": base_index,
            "formation_start": origin_time,
            "formation_end": origin_time,
            "departure_end_index": departure_index,
            "departure_end": departure_time,
            "departure_source_id": departure_time,
            "departure_source_time": departure_time,
            "available_at": None,
            "confirmed_at": None,
            "confirmation_event_id": None,
            "lifecycle_status": "candidate",
            "candidate": True,
            "entry_eligible": False,
            "departure_measurement": measurement,
            "reason_codes": reason_codes,
        })
    return candidates


def confirm_order_block_candidate(
    candidate: dict[str, Any],
    structure_events: Sequence[dict[str, Any]] | dict[str, Any],
    *,
    candles: Sequence[Candle] | None = None,
    max_bars_after_departure: int = 3,
    as_of: datetime | str | None = None,
) -> dict[str, Any]:
    """Promote one OB candidate only after a related confirmed BOS.

    The structure event is the sole confirmation requirement here.  Sweep and
    FVG evidence remain optional metadata and are intentionally not consulted.
    A candidate that has no causal BOS is returned unchanged except for an
    explicit waiting reason; no entry eligibility is granted.
    """

    if not isinstance(candidate, dict):
        raise ValueError("OB candidate must be a mapping")
    if isinstance(structure_events, dict):
        raw_events = structure_events.get("events", [])
    else:
        raw_events = structure_events
    if not isinstance(raw_events, Sequence) or isinstance(raw_events, (str, bytes)):
        raise ValueError("structure_events must be a sequence or events mapping")
    if isinstance(max_bars_after_departure, bool) or max_bars_after_departure < 1:
        raise ValueError("max_bars_after_departure must be positive")

    result = dict(candidate)
    existing_reasons = [
        str(reason).strip()
        for reason in candidate.get("reason_codes", [])
        if str(reason).strip()
    ] if isinstance(candidate.get("reason_codes", []), (list, tuple)) else []
    direction = str(candidate.get("direction", "") or "").strip().lower()
    expected_event_direction = "bullish" if direction == "buy" else "bearish"
    departure_index = candidate.get(
        "departure_end_index",
        candidate.get("origin_index", -1),
    )
    try:
        departure_index = int(departure_index)
    except (TypeError, ValueError):
        departure_index = -1
    departure_time = candidate.get("departure_end")
    cutoff = (
        _parse_utc_timestamp(as_of, "as_of")
        if as_of is not None else None
    )

    candidate_timeframe = str(candidate.get("timeframe", "") or "").strip().upper()
    normalized_timeframe = candidate_timeframe if candidate_timeframe in SMC_TIMEFRAME_INTERVALS else "H1"
    departure_measurement = candidate.get("departure_measurement")
    if not isinstance(departure_measurement, dict) or departure_measurement.get("status") != "ok":
        result["lifecycle_status"] = "candidate"
        result["entry_eligible"] = False
        result["reason_codes"] = list(dict.fromkeys((
            *existing_reasons, "OB_DEPARTURE_MEASUREMENT_UNAVAILABLE",
            "OB_STRUCTURE_BREAK_MISSING",
        )))
        return result
    quality_reasons: list[str] = []
    body_range = _finite_float(departure_measurement.get("body_range"))
    body_atr = _finite_float(departure_measurement.get("body_atr"))
    directional_close_location = departure_measurement.get("directional_close_location")
    directional_close_location = _finite_float(directional_close_location)
    if body_range is None:
        quality_reasons.append("OB_DEPARTURE_BODY_RANGE_UNAVAILABLE")
    elif body_range < 0.50:
        quality_reasons.append("OB_DEPARTURE_BODY_WEAK")
    if body_atr is None:
        quality_reasons.append("OB_DEPARTURE_ATR_UNAVAILABLE")
    elif body_atr < 0.30:
        quality_reasons.append("OB_DEPARTURE_BODY_ATR_WEAK")
    if directional_close_location is None:
        quality_reasons.append("OB_DEPARTURE_CLOSE_LOCATION_UNAVAILABLE")
    elif directional_close_location < 0.70:
        quality_reasons.append("OB_DEPARTURE_CLOSE_LOCATION_WEAK")
    if quality_reasons:
        result["lifecycle_status"] = "candidate"
        result["entry_eligible"] = False
        result["reason_codes"] = list(dict.fromkeys((
            *existing_reasons, *quality_reasons,
        )))
        return result

    departure_close = None
    if candles is not None:
        if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
            raise ValueError("candles must be a sequence")
        if departure_index < 0 or departure_index >= len(candles):
            result["lifecycle_status"] = "candidate"
            result["entry_eligible"] = False
            result["reason_codes"] = list(dict.fromkeys((
                *existing_reasons, "OB_DEPARTURE_DATA_UNAVAILABLE",
            )))
            return result
        departure_close = candle_close_at(
            candles[departure_index].time, normalized_timeframe,
        ).astimezone(timezone.utc)
    elif departure_time is not None:
        departure_close = candle_close_at(
            _parse_utc_timestamp(departure_time, "departure_end"),
            normalized_timeframe,
        ).astimezone(timezone.utc)

    matching: list[dict[str, Any]] = []
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            continue
        event_type = str(raw_event.get("event_type", raw_event.get("type", "")) or "").strip().upper()
        event_direction = str(raw_event.get("direction", "") or "").strip().lower()
        if event_type != "BOS" or event_direction != expected_event_direction:
            continue
        event_id = str(raw_event.get("event_id", raw_event.get("id", "")) or "").strip()
        broken_level_id = str(raw_event.get("broken_level_id", "") or "").strip()
        if not event_id or not broken_level_id:
            continue
        if raw_event.get("confirmed_at") is None or raw_event.get("occurred_at") is None:
            continue
        event_status = str(raw_event.get("status", "") or "").strip().lower()
        if raw_event.get("confirmed") is not True and event_status != "confirmed":
            continue
        if raw_event.get("wick_only") is True:
            continue
        event_lifecycle = str(
            raw_event.get(
                "lifecycle",
                raw_event.get("event_lifecycle", raw_event.get("status", "")),
            ) or ""
        ).strip().lower()
        if (
            raw_event.get("invalidated") is True
            or raw_event.get("reclaimed") is True
            or raw_event.get("invalidated_at") is not None
            or event_lifecycle in {"invalidated", "reclaimed", "expired"}
        ):
            continue
        event_timeframe = str(raw_event.get("timeframe", "") or "").strip().upper()
        if event_timeframe and event_timeframe != normalized_timeframe:
            continue
        occurred_at = _parse_utc_timestamp(raw_event["occurred_at"], "event.occurred_at")
        confirmed_at = _parse_utc_timestamp(raw_event["confirmed_at"], "event.confirmed_at")
        if confirmed_at < occurred_at:
            continue
        if cutoff is not None:
            if confirmed_at > cutoff:
                continue
        event_index = raw_event.get("occurred_index", raw_event.get("index"))
        if event_index is not None:
            try:
                event_index = int(event_index)
            except (TypeError, ValueError):
                event_index = None
        if event_index is None and candles is not None:
            event_index = next(
                (
                    index for index, candle in enumerate(candles)
                    if candle_close_at(candle.time, normalized_timeframe).astimezone(timezone.utc) == occurred_at
                ),
                None,
            )
            # With a candle snapshot, an event timestamp must resolve to a
            # concrete closed candle.  Never count session downtime as bars.
            if event_index is None:
                continue
        if event_index is not None:
            if departure_index < 0 or not departure_index < event_index <= departure_index + max_bars_after_departure:
                continue
            if candles is not None:
                if event_index < 0 or event_index >= len(candles):
                    continue
                expected_occurred_at = candle_close_at(
                    candles[event_index].time, normalized_timeframe,
                ).astimezone(timezone.utc)
                if occurred_at != expected_occurred_at:
                    continue
            elif departure_close is not None:
                expected_occurred_at = departure_close + (
                    SMC_TIMEFRAME_INTERVALS[normalized_timeframe]
                    * (event_index - departure_index)
                )
                if occurred_at != expected_occurred_at:
                    continue
        elif departure_close is not None:
            if occurred_at <= departure_close:
                continue
            interval_seconds = SMC_TIMEFRAME_INTERVALS[normalized_timeframe].total_seconds()
            elapsed_seconds = (occurred_at - departure_close).total_seconds()
            bars_after = elapsed_seconds / interval_seconds
            if bars_after <= 0 or bars_after > max_bars_after_departure or not bars_after.is_integer():
                    continue
        else:
            continue
        matching.append(raw_event)

    if not matching:
        result["lifecycle_status"] = "candidate"
        result["entry_eligible"] = False
        result["reason_codes"] = list(dict.fromkeys((*existing_reasons, "OB_STRUCTURE_BREAK_MISSING")))
        return result

    event = min(
        matching,
        key=lambda item: (
            0,
            int(item.get("occurred_index", item.get("index", 10**9)))
            if str(item.get("occurred_index", item.get("index", ""))).lstrip("-").isdigit()
            else 10**9,
            str(item.get("occurred_at", "")),
            str(item.get("event_id", "")),
        ),
    )
    confirmed_at = event.get("confirmed_at") or event.get("occurred_at")
    confirmed_timestamp = _parse_utc_timestamp(confirmed_at, "event.confirmed_at")
    result.update({
        "lifecycle_status": "confirmed",
        "candidate": False,
        "entry_eligible": False,
        "confirmation_event_id": str(event.get("event_id", event.get("id", ""))).strip(),
        "confirmed_at": confirmed_timestamp.isoformat(),
        "available_at": confirmed_timestamp.isoformat(),
        "related_structure_event_id": str(event.get("event_id", event.get("id", ""))).strip(),
        "broken_level_id": str(event.get("broken_level_id")).strip(),
        "reason_codes": list(dict.fromkeys((*existing_reasons, "ZONE_CONFIRMED"))),
    })
    return result


def confirm_order_block_candidates(
    candidates: Sequence[dict[str, Any]],
    structure_events: Sequence[dict[str, Any]] | dict[str, Any],
    *,
    candles: Sequence[Candle] | None = None,
    max_bars_after_departure: int = 3,
    as_of: datetime | str | None = None,
) -> list[dict[str, Any]]:
    """Apply :func:`confirm_order_block_candidate` without mutating inputs."""

    return [
        confirm_order_block_candidate(
            candidate,
            structure_events,
            candles=candles,
            max_bars_after_departure=max_bars_after_departure,
            as_of=as_of,
        )
        for candidate in candidates
    ]


def detect_order_blocks(candles: list[Candle], fvg: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    if len(candles) < 4:
        return blocks
    fvg_indices = {item["index"]: item for item in fvg}
    start = max(0, len(candles) - _LOOKBACK_WINDOW)
    for index in range(start + 1, len(candles) - 1):
        candle = candles[index]
        nxt = candles[index + 1]
        is_bearish = candle.close < candle.open
        is_bullish = candle.close > candle.open
        impulse_up = nxt.close > candle.high
        impulse_down = nxt.close < candle.low
        if is_bearish and impulse_up:
            blocks.append(
                {
                    "type": "bullish_order_block",
                    "low": candle.low,
                    "high": candle.high,
                    "index": index,
                    "time": candle.time.isoformat(),
                    "origin_index": index,
                    "origin_time": candle.time.isoformat(),
                    "formation_start_index": index,
                    "departure_end_index": index + 1,
                    "has_fvg_above": (index + 2) in fvg_indices,
                    "displacement_multiple": displacement_multiple_at(candles, index + 1),
                }
            )
        elif is_bullish and impulse_down:
            blocks.append(
                {
                    "type": "bearish_order_block",
                    "low": candle.low,
                    "high": candle.high,
                    "index": index,
                    "time": candle.time.isoformat(),
                    "origin_index": index,
                    "origin_time": candle.time.isoformat(),
                    "formation_start_index": index,
                    "departure_end_index": index + 1,
                    "has_fvg_below": (index + 2) in fvg_indices,
                    "displacement_multiple": displacement_multiple_at(candles, index + 1),
                }
            )
    return blocks[-_MAX_ORDER_BLOCKS:]


def measure_supply_demand_base(
    base: Sequence[Candle],
    *,
    average_range: float | None,
    consolidation_bars: int,
) -> dict[str, Any]:
    """Measure a pre-departure compressed base without confirming departure."""

    if isinstance(consolidation_bars, bool) or consolidation_bars not in {3, 5, 7, 10}:
        raise ValueError("consolidation_bars must be one of 3, 5, 7, or 10")
    if len(base) != consolidation_bars or not all(isinstance(item, Candle) for item in base):
        raise ValueError("S/D base does not contain the requested candle count")
    ranges = [float(item.high) - float(item.low) for item in base]
    if not all(isfinite(value) and value >= 0 for value in ranges):
        return {
            "accepted": False,
            "base_low": None,
            "base_high": None,
            "base_range": None,
            "average_range": None,
            "compression_limit": None,
            "reason_codes": ["SD_AVERAGE_RANGE_UNAVAILABLE"],
        }
    base_low = min(item.low for item in base)
    base_high = max(item.high for item in base)
    base_range = base_high - base_low
    if average_range is None or not isfinite(float(average_range)) or float(average_range) <= 0:
        return {
            "accepted": False,
            "base_low": base_low,
            "base_high": base_high,
            "base_range": base_range,
            "average_range": None,
            "compression_limit": None,
            "reason_codes": ["SD_AVERAGE_RANGE_UNAVAILABLE"],
        }
    reference_range = float(average_range)
    compression_limit = 1.20 + 0.06 * (consolidation_bars - 3)
    reasons = (
        ["SD_COMPRESSION_TOO_WIDE"]
        if base_range > reference_range * compression_limit else []
    )
    return {
        "accepted": not reasons,
        "base_low": base_low,
        "base_high": base_high,
        "base_range": base_range,
        "average_range": reference_range,
        "compression_limit": compression_limit,
        "reason_codes": reasons,
    }


def detect_supply_demand_candidates(
    candles: Sequence[Candle],
    *,
    symbol: str = "",
    timeframe: str = "",
    average_range_before_departure: dict[int, float] | float | None = None,
) -> list[dict[str, Any]]:
    """Find compressed S/D bases before departure; leave confirmation to Task 49."""

    candidates: list[dict[str, Any]] = []
    best_by_impulse: dict[tuple[int, str], dict[str, Any]] = {}
    for departure_index in range(3, len(candles)):
        for consolidation_bars in (3, 5, 7, 10):
            base_start = departure_index - consolidation_bars
            if base_start < 0:
                continue
            base = candles[base_start:departure_index]
            if isinstance(average_range_before_departure, dict):
                reference_range = average_range_before_departure.get(departure_index)
            elif average_range_before_departure is not None:
                reference_range = average_range_before_departure
            else:
                preceding = candles[max(0, base_start - 50):base_start]
                reference_range = (
                    sum(item.high - item.low for item in preceding) / len(preceding)
                    if preceding else None
                )
            measurement = measure_supply_demand_base(
                base,
                average_range=reference_range,
                consolidation_bars=consolidation_bars,
            )
            if not measurement["accepted"]:
                continue
            departure = candles[departure_index]
            if departure.close == departure.open:
                continue
            direction = "buy" if departure.close > departure.open else "sell"
            zone_type = "demand_zone" if direction == "buy" else "supply_zone"
            origin_time = base[-1].time.isoformat()
            departure_time = departure.time.isoformat()
            candidate = {
                "zone_id": build_zone_id(
                    symbol=symbol,
                    timeframe=timeframe or "UNKNOWN",
                    family="supply_demand",
                    direction=direction,
                    origin_time=origin_time,
                    low=measurement["base_low"],
                    high=measurement["base_high"],
                ),
                "setup_id": build_setup_id(
                    symbol=symbol,
                    timeframe=timeframe or "UNKNOWN",
                    direction=direction,
                    departure_source=departure_time,
                ),
                "type": zone_type,
                "zone_type": zone_type,
                "family": "supply_demand",
                "symbol": symbol,
                "timeframe": timeframe or "UNKNOWN",
                "direction": direction,
                "low": measurement["base_low"],
                "high": measurement["base_high"],
                "original_bounds": {
                    "low": measurement["base_low"],
                    "high": measurement["base_high"],
                },
                "origin_index": base_start,
                "origin_time": origin_time,
                "formation_start_index": base_start,
                "formation_end_index": departure_index - 1,
                "formation_start": base[0].time.isoformat(),
                "formation_end": origin_time,
                "departure_end_index": departure_index,
                "departure_end": departure_time,
                "departure_source_id": departure_time,
                "departure_source_time": departure_time,
                "consolidation_bars": consolidation_bars,
                "available_at": None,
                "confirmed_at": None,
                "confirmation_event_id": None,
                "lifecycle_status": "candidate",
                "candidate": True,
                "entry_eligible": False,
                "base_measurement": measurement,
                "departure_close_outside_base": (
                    departure.close > measurement["base_high"]
                    if direction == "buy"
                    else departure.close < measurement["base_low"]
                ),
                "reason_codes": ["ZONE_CANDIDATE"],
            }
            key = (departure_index, direction)
            candidate_key = (
                float(measurement["base_range"]),
                int(consolidation_bars),
                int(base_start),
                str(candidate["zone_id"]),
            )
            prior = best_by_impulse.get(key)
            if prior is None or candidate_key < prior["_canonical_key"]:
                candidate["_canonical_key"] = candidate_key
                best_by_impulse[key] = candidate
    candidates = list(best_by_impulse.values())
    candidates.sort(key=lambda item: (
        int(item.get("departure_end_index", -1)),
        str(item.get("direction", "")),
        str(item.get("zone_id", "")),
    ))
    for candidate in candidates:
        candidate.pop("_canonical_key", None)
    return candidates


def confirm_supply_demand_candidate(
    candidate: dict[str, Any],
    candles: Sequence[Candle],
    *,
    timeframe: str,
    atr_before_event: float | None,
    min_body_atr: float = 0.30,
    min_body_range: float = 0.50,
    min_efficiency: float = 1.50,
    as_of: datetime | str | None = None,
) -> dict[str, Any]:
    """Confirm an S/D candidate from a causal departure candle.

    The candidate's recorded base measurement is reused, so later candles
    cannot change its formation feature.  Confirmation is deliberately kept
    separate from candidate discovery and requires the close to leave the
    original base in the candidate's direction.
    """

    if not isinstance(candidate, dict):
        raise ValueError("S/D candidate must be a mapping")
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise ValueError("candles must be a sequence")
    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported S/D timeframe: {timeframe}")
    departure_index = candidate.get("departure_end_index")
    try:
        departure_index = int(departure_index)
    except (TypeError, ValueError):
        departure_index = -1
    result = dict(candidate)
    raw_reasons = candidate.get("reason_codes", [])
    reasons = [
        str(reason).strip()
        for reason in raw_reasons
        if str(reason).strip()
    ] if isinstance(raw_reasons, (list, tuple)) else []
    reasons = [reason for reason in reasons if reason != "ZONE_CANDIDATE"]
    if departure_index < 0 or departure_index >= len(candles):
        result["lifecycle_status"] = "candidate"
        result["entry_eligible"] = False
        result["reason_codes"] = list(dict.fromkeys((*reasons, "SD_DEPARTURE_DATA_UNAVAILABLE")))
        return result
    departure = candles[departure_index]
    departure_close_at = candle_close_at(
        departure.time,
        normalized_timeframe,
    ).astimezone(timezone.utc)
    if as_of is not None and departure_close_at > _parse_utc_timestamp(as_of, "as_of"):
        result["lifecycle_status"] = "candidate"
        result["entry_eligible"] = False
        result["reason_codes"] = list(dict.fromkeys((*reasons, "SD_DEPARTURE_NOT_CLOSED")))
        return result
    direction = str(candidate.get("direction", "") or "").strip().lower()
    if direction not in {"buy", "sell"}:
        raise ValueError(f"Invalid S/D candidate direction: {direction}")
    base_low = float(candidate.get("low", 0.0))
    base_high = float(candidate.get("high", base_low))
    close_outside = (
        departure.close > base_high
        if direction == "buy"
        else departure.close < base_low
    )
    measurement = measure_departure(
        departure,
        direction=direction,
        atr_before_event=atr_before_event,
    )
    base_measurement = candidate.get("base_measurement", {})
    average_range = (
        base_measurement.get("average_range")
        if isinstance(base_measurement, dict)
        else None
    )
    efficiency = None
    if average_range is not None and float(average_range) > 0:
        efficiency = measurement["range"] / float(average_range)
    if not close_outside:
        reasons.append("SD_CLOSE_NOT_OUTSIDE_BASE")
    if measurement["body_range"] is None or measurement["body_range"] < min_body_range:
        reasons.append("SD_DEPARTURE_WICK_ONLY")
    if measurement["body_atr"] is None:
        reasons.append("SD_DEPARTURE_ATR_UNAVAILABLE")
    elif measurement["body_atr"] < min_body_atr:
        reasons.append("SD_DEPARTURE_BODY_WEAK")
    close_location = measurement.get("directional_close_location")
    if close_location is None:
        reasons.append("SD_DEPARTURE_CLOSE_LOCATION_UNAVAILABLE")
    elif close_location < 0.70:
        reasons.append("SD_DEPARTURE_CLOSE_LOCATION_WEAK")
    if efficiency is None:
        reasons.append("SD_DEPARTURE_EFFICIENCY_UNAVAILABLE")
    elif efficiency < min_efficiency:
        reasons.append("SD_DEPARTURE_EFFICIENCY_WEAK")
    if reasons:
        result["lifecycle_status"] = "candidate"
        result["entry_eligible"] = False
        result["departure_measurement"] = measurement
        result["departure_efficiency"] = efficiency
        result["reason_codes"] = list(dict.fromkeys(reasons))
        return result
    confirmed_at = departure_close_at.isoformat()
    result.update({
        "lifecycle_status": "confirmed",
        "candidate": False,
        "entry_eligible": False,
        "confirmed_at": confirmed_at,
        "available_at": confirmed_at,
        "confirmation_event_id": None,
        "confirmation_source": "departure",
        "departure_measurement": measurement,
        "departure_efficiency": efficiency,
        "reason_codes": list(dict.fromkeys((*reasons, "ZONE_CONFIRMED"))),
    })
    return result


def confirm_supply_demand_candidates(
    candidates: Sequence[dict[str, Any]],
    candles: Sequence[Candle],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Confirm S/D candidates independently without mutating their inputs."""

    return [
        confirm_supply_demand_candidate(candidate, candles, **kwargs)
        for candidate in candidates
    ]


def assign_setup_ids_to_zones(
    zones: Sequence[dict[str, Any]],
    *,
    symbol: str = "",
    timeframe: str = "",
    anchor_timeframe: str | None = None,
) -> list[dict[str, Any]]:
    """Assign one stable setup ID to child zones sharing departure lineage.

    Family and bounds are intentionally excluded from setup identity: one
    departure may create OB, FVG and S/D children.  Direction, snapshot
    lineage and departure source remain part of the identity, so overlap alone
    never groups unrelated zones.
    """

    result: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        item = dict(zone)
        direction = str(item.get("direction", "") or "").strip().lower()
        if direction not in {"buy", "sell"}:
            item["setup_id"] = None
            item["reason_codes"] = list(dict.fromkeys(
                [*(item.get("reason_codes", []) if isinstance(item.get("reason_codes", []), list) else []),
                  "SETUP_DIRECTION_INVALID"]
            ))
            result.append(item)
            continue
        source = str(
            item.get("departure_source_id")
            or item.get("departure_event_id")
            or item.get("departure_end")
            or item.get("departure_end_index", "")
        ).strip()
        if not source:
            item["setup_id"] = None
            item["reason_codes"] = list(dict.fromkeys(
                [*(item.get("reason_codes", []) if isinstance(item.get("reason_codes", []), list) else []),
                  "SETUP_SOURCE_MISSING"]
            ))
            result.append(item)
            continue
        snapshot_lineage = str(
            item.get("snapshot_id")
            or item.get("snapshot_lineage")
            or ""
        ).strip()
        source_identity = f"{snapshot_lineage}|{source}" if snapshot_lineage else source
        item["setup_id"] = build_setup_id(
            symbol=item.get("symbol", symbol),
            timeframe=item.get("timeframe", timeframe),
            direction=direction,
            departure_source=source_identity,
            anchor_timeframe=item.get("anchor_timeframe", anchor_timeframe or timeframe),
        )
        item["setup_source"] = source_identity
        result.append(item)
    return result


def group_smc_zones_into_setups(
    zones: Sequence[dict[str, Any]],
    *,
    symbol: str = "",
    timeframe: str = "",
    anchor_timeframe: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Return assigned child zones grouped by setup without merging bounds."""

    assigned = assign_setup_ids_to_zones(
        zones,
        symbol=symbol,
        timeframe=timeframe,
        anchor_timeframe=anchor_timeframe,
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for zone in assigned:
        setup_id = zone.get("setup_id")
        if not setup_id:
            continue
        grouped.setdefault(str(setup_id), []).append(zone)
    return grouped


def retain_zone_history_candidates(
    zones: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Keep every candidate for lifecycle evaluation without a pre-cut."""

    return [dict(zone) for zone in zones if isinstance(zone, dict)]


def limit_zones_for_output(
    zones: Sequence[dict[str, Any]],
    *,
    family: str,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Apply the bounded display limit only after lifecycle processing.

    Active/confirmed zones rank ahead of invalid or expired zones.  This keeps
    a newly detected invalid zone from displacing an older valid zone in the
    bounded UI payload while preserving all records for history.
    """

    normalized_family = str(family or "").strip().lower()
    if limit is None:
        limit = (
            _MAX_FVG if normalized_family == "fvg"
            else _MAX_ORDER_BLOCKS if normalized_family in {"ob", "order_block"}
            else _MAX_SD_ZONES if normalized_family in {"supply_demand", "demand", "supply"}
            else 0
        )
    if isinstance(limit, bool) or limit < 0:
        raise ValueError("zone output limit must be a non-negative integer")
    history = retain_zone_history_candidates(zones)
    if limit == 0:
        return []
    active_statuses = {"candidate", "confirmed", "usable", "watch"}
    ordered = sorted(
        enumerate(history),
        key=lambda pair: (
            0 if bool(pair[1].get("usable")) or str(pair[1].get("lifecycle_status", "")).lower() in active_statuses else 1,
            -int(pair[1].get("origin_index", pair[1].get("index", -1)) or -1),
            str(pair[1].get("origin_time", pair[1].get("time", "")) or ""),
            str(pair[1].get("zone_id", "") or ""),
            pair[0],
        ),
    )
    return [zone for _, zone in ordered[: int(limit)]]


def apply_zone_availability(
    zones: Sequence[dict[str, Any]],
    candles: Sequence[Candle],
    *,
    timeframe: str,
    symbol: str,
    as_of: datetime | str,
    require_lifetime: bool = True,
    window: Any = None,
) -> list[dict[str, Any]]:
    """Apply availability and causal history gates without inventing data."""

    cutoff = _parse_utc_timestamp(as_of, "as_of")
    normalized_timeframe = str(timeframe or "").strip().upper()
    if not isinstance(candles, Sequence) or isinstance(candles, (str, bytes)):
        raise ValueError("candles must be a sequence")
    closed_history = tuple(
        candle for candle in candles
        if candle_close_at(
            candle.time, normalized_timeframe,
        ).astimezone(timezone.utc) <= cutoff
    )
    result: list[dict[str, Any]] = []
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        item = dict(zone)
        raw_reasons = item.get("reason_codes", [])
        reasons = [
            str(reason).strip()
            for reason in raw_reasons
            if str(reason).strip()
        ] if isinstance(raw_reasons, (list, tuple)) else []
        origin_value = item.get("origin_time") or item.get("time")
        origin_time = None
        if origin_value is not None:
            try:
                origin_time = _parse_utc_timestamp(origin_value, "zone.origin_time")
            except ValueError:
                reasons.append("SMC_TIMESTAMP_INVALID")
        coverage = assess_smc_history(
            closed_history,
            normalized_timeframe,
            symbol=symbol or None,
            origin_time=origin_time,
            require_lifetime=require_lifetime,
            window=window,
        )
        item["history_coverage"] = coverage.to_dict()
        reasons.extend(coverage.reason_codes)
        status = str(item.get("lifecycle_status", "candidate") or "candidate").strip().lower()
        available_value = item.get("available_at")
        available_time = None
        if available_value is not None:
            try:
                available_time = _parse_utc_timestamp(available_value, "zone.available_at")
            except ValueError:
                reasons.append("SMC_TIMESTAMP_INVALID")
        if status not in {"confirmed", "usable"}:
            reasons.append("ZONE_NOT_AVAILABLE_YET")
            item["availability_status"] = "waiting_confirmation"
            item["usable"] = False
        elif available_time is None or available_time > cutoff:
            reasons.append("ZONE_NOT_AVAILABLE_YET")
            item["availability_status"] = "waiting_availability"
            item["usable"] = False
        elif not coverage.freshness_eligible:
            item["availability_status"] = "data_unavailable"
            item["usable"] = False
        elif status == "usable":
            item["availability_status"] = "usable"
            item["usable"] = True
        else:
            item["lifecycle_status"] = "usable"
            item["availability_status"] = "usable"
            item["usable"] = True
        item["reason_codes"] = list(dict.fromkeys(reasons))
        result.append(item)
    return result


def apply_zone_lifetime_and_availability(
    zones: Sequence[dict[str, Any]],
    candles: Sequence[Candle],
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Compatibility alias for the Task 52 availability seam."""

    return apply_zone_availability(zones, candles, **kwargs)


def detect_supply_demand_zones(candles: list[Candle]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if len(candles) < 8:
        return [], []

    avg_range = sum(candle.high - candle.low for candle in candles[-50:]) / max(1, min(50, len(candles)))
    impulse_threshold = avg_range * 1.5 if avg_range > 0 else 0.0

    # Dict keyed by (index, "demand"|"supply") -> best zone for that impulse
    best_by_impulse: dict[tuple[int, str], dict[str, Any]] = {}

    for consolidation_bars in (3, 5, 7, 10):
        if len(candles) < consolidation_bars + 2:
            continue
        max_base_range_mult = 1.2 + 0.06 * (consolidation_bars - 3)

        start = max(consolidation_bars, len(candles) - _LOOKBACK_WINDOW)
        for index in range(start, len(candles) - 1):
            impulse = candles[index]
            impulse_size = impulse.high - impulse.low
            if impulse_size <= impulse_threshold:
                continue
            base = candles[index - consolidation_bars : index]
            if not base:
                continue
            base_high = max(candle.high for candle in base)
            base_low = min(candle.low for candle in base)
            base_range = base_high - base_low
            if avg_range > 0 and base_range > avg_range * max_base_range_mult:
                continue

            is_bullish = impulse.close > impulse.open and impulse.close > base_high
            is_bearish = impulse.close < impulse.open and impulse.close < base_low
            if not (is_bullish or is_bearish):
                continue

            direction = "demand" if is_bullish else "supply"
            key = (index, direction)

            # Keep the zone with tightest base_range per impulse
            if key not in best_by_impulse or base_range < best_by_impulse[key]["_base_range"]:
                best_by_impulse[key] = {
                    "type": "demand_zone" if is_bullish else "supply_zone",
                    "low": base_low,
                    "high": base_high,
                    "index": index - 1,
                    "time": base[-1].time.isoformat(),
                    "origin_index": index - 1,
                    "origin_time": base[-1].time.isoformat(),
                    "formation_start_index": index - consolidation_bars,
                    "departure_end_index": index,
                    "consolidation_bars": consolidation_bars,
                    "displacement_multiple": round(impulse_size / avg_range, 2) if avg_range else 0,
                    "liquidity_sweep": (
                        swept_recent_low(impulse, candles[:index])
                        if is_bullish
                        else swept_recent_high(impulse, candles[:index])
                    ),
                    "_base_range": base_range,
                }

    # Split by type, sort by index descending, keep top _MAX_SD_ZONES
    demand_candidates = sorted(
        [z for z in best_by_impulse.values() if z["type"] == "demand_zone"],
        key=lambda z: z["index"], reverse=True,
    )[: _MAX_SD_ZONES]
    supply_candidates = sorted(
        [z for z in best_by_impulse.values() if z["type"] == "supply_zone"],
        key=lambda z: z["index"], reverse=True,
    )[: _MAX_SD_ZONES]

    # Clean up internal field
    for z in demand_candidates + supply_candidates:
        z.pop("_base_range", None)

    return demand_candidates, supply_candidates


def _usable_time_sort_key(value: str) -> tuple[int, str]:
    """Order ISO-8601 timestamps by instant, keeping unparsable text last."""

    try:
        return (0, datetime.fromisoformat(value).astimezone(timezone.utc).isoformat())
    except (TypeError, ValueError):
        return (1, str(value))


def _parse_usable_instant(value: object) -> datetime | None:
    """Parse a source's declared usable time, or ``None`` when it is not a usable instant.

    A missing, empty, naive or malformed timestamp is not usable provenance: it can never make a
    source (and therefore a pool) eligible for a canonical sweep.
    """

    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def detect_liquidity_pools(
    candles: list[Candle],
    swings: dict[str, list[dict[str, Any]]],
    *,
    tick_size: float | None = None,
    atr_value: float | None = None,
    atr_current: float | None = None,
    equal_tolerance: float | None = None,
) -> dict[str, list[float] | float | str | list[str] | list[dict[str, Any]]]:
    """Build causal liquidity pools from confirmed/equal swing levels.

    Typed swing records are fail-closed unless they are confirmed, usable and
    non-provisional.  The old unannotated swing payload remains supported for
    the pre-stage-B public route, where its historical range tolerance is
    retained for compatibility.

    The four numeric keys stay a legacy projection of pool *levels*.  Canonical
    pool identity, source lineage and per-source times live in ``records``, one
    entry per projected pool (A3-005): a source that does not declare its own
    identity and the moment it became usable gets no canonical entry and is not
    invented from ``confirmed_at``, so such a pool keeps only its projection.
    """

    empty: dict[str, list[float] | float | str | list[str] | list[dict[str, Any]]] = {
        "equal_highs": [],
        "equal_lows": [],
        "swing_highs": [],
        "swing_lows": [],
        "records": [],
    }
    if not candles:
        return empty
    if not isinstance(swings, dict):
        return empty

    raw_highs = swings.get("highs", [])
    raw_lows = swings.get("lows", [])
    if not isinstance(raw_highs, list) or not isinstance(raw_lows, list):
        return empty

    def causal_key(item: dict[str, Any]) -> tuple[int, str, str]:
        raw_index = item.get("index", 0)
        try:
            index = int(raw_index)
        except (TypeError, ValueError, OverflowError):
            index = 0
        return (
            index,
            str(item.get("pivot_time", item.get("time", "")) or ""),
            str(item.get("swing_id", "") or ""),
        )

    def eligible(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        if "confirmed" in item and item.get("confirmed") is not True:
            return False
        if "usable" in item and item.get("usable") is not True:
            return False
        if item.get("provisional") is True:
            return False
        try:
            level = float(item.get("level"))
        except (TypeError, ValueError, OverflowError):
            return False
        return isfinite(level)

    typed_metadata = any(
        isinstance(item, dict)
        and any(key in item for key in ("confirmed", "usable", "provisional"))
        for item in [*raw_highs, *raw_lows]
    )
    high_items = sorted(
        (item for item in raw_highs if eligible(item)),
        key=causal_key,
    )[-8:]
    low_items = sorted(
        (item for item in raw_lows if eligible(item)),
        key=causal_key,
    )[-8:]
    high_levels = [float(item["level"]) for item in high_items]
    low_levels = [float(item["level"]) for item in low_items]

    normalized_atr = atr_value if atr_value is not None else atr_current
    if equal_tolerance is not None:
        tolerance = float(equal_tolerance)
        if not isfinite(tolerance) or tolerance < 0:
            raise ValueError("equal_tolerance must be finite and non-negative")
    elif tick_size is not None and normalized_atr is not None:
        tick = float(tick_size)
        atr = float(normalized_atr)
        if not isfinite(tick) or not isfinite(atr) or tick <= 0 or atr <= 0:
            raise ValueError("tick_size and ATR must be finite and positive")
        tolerance = max(2.0 * tick, 0.10 * atr)
    elif typed_metadata:
        tolerance = None
    else:
        avg_range = sum(
            candle.high - candle.low for candle in candles[-50:]
        ) / max(1, min(50, len(candles)))
        tolerance = max(avg_range * 0.15, 0.0001)

    def equal_pairs(
        items: list[dict[str, Any]],
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        """Equal-level source pairs in the same causal order the projection uses."""

        if tolerance is None:
            return []
        pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
        boundary_epsilon = max(1e-12, abs(tolerance) * 1e-12)
        for index, item in enumerate(items):
            value = float(item["level"])
            for other in items[index + 1 :]:
                if abs(value - float(other["level"])) <= tolerance + boundary_epsilon:
                    pairs.append((item, other))
                    break
        return pairs[-_MAX_LIQUIDITY_LEVELS:]

    def equal_levels(pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> list[float]:
        return [(float(left["level"]) + float(right["level"])) / 2.0 for left, right in pairs]

    equal_low_pairs = equal_pairs(low_items)
    equal_high_pairs = equal_pairs(high_items)

    result: dict[str, list[float] | float | str | list[str] | list[dict[str, Any]]] = {
        "equal_highs": equal_levels(equal_high_pairs),
        "equal_lows": equal_levels(equal_low_pairs),
        "swing_highs": high_levels[-_MAX_LIQUIDITY_LEVELS:],
        "swing_lows": low_levels[-_MAX_LIQUIDITY_LEVELS:],
    }
    if tolerance is not None:
        result["equal_tolerance"] = tolerance
    else:
        result["status"] = "unknown"
        result["reason_codes"] = ["SMC_EQUAL_LEVEL_TOLERANCE_UNAVAILABLE"]

    def canonical_source(item: dict[str, Any]) -> dict[str, Any] | None:
        """Per-source identity and times, or ``None`` when it cannot be canonical.

        The canonical path needs the source's own ID and the moment it became usable.
        Neither is derived here: a source that does not declare ``usable_at`` keeps no
        canonical entry instead of borrowing ``confirmed_at`` (A3-005, A-D06).
        """

        swing_id = str(item.get("swing_id", "") or "").strip()
        usable_at = item.get("usable_at")
        if not swing_id or not isinstance(usable_at, str) or not usable_at.strip():
            return None
        return {
            "swing_id": swing_id,
            "confirmed_at": item.get("confirmed_at"),
            "usable_at": usable_at,
            "provisional": bool(item.get("provisional", False)),
        }

    def canonical_record(
        kind: str,
        level: float,
        items: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        sources = [canonical_source(item) for item in items]
        if any(source is None for source in sources):
            return None
        ordered = sorted(sources, key=lambda source: source["swing_id"])
        # Identity is `kind` + the sorted IDs + each source's own causal record. Level, input
        # order, rolling index and observation time deliberately take no part (A-D06).
        lineage = "|".join(
            f"{source['swing_id']}@{source.get('confirmed_at') or ''}" for source in ordered
        )
        return {
            "pool_id": f"{kind}:{lineage}",
            "kind": kind,
            "level": float(level),
            "source_ids": [source["swing_id"] for source in ordered],
            "sources": ordered,
            "usable_at": max(
                (source["usable_at"] for source in ordered), key=_usable_time_sort_key,
            ),
        }

    canonical: list[tuple[str, float, list[dict[str, Any]]]] = [
        ("swing_low", float(item["level"]), [item])
        for item in low_items[-_MAX_LIQUIDITY_LEVELS:]
    ]
    canonical += [
        ("swing_high", float(item["level"]), [item])
        for item in high_items[-_MAX_LIQUIDITY_LEVELS:]
    ]
    canonical += [
        ("equal_low", (float(left["level"]) + float(right["level"])) / 2.0, [left, right])
        for left, right in equal_low_pairs
    ]
    canonical += [
        ("equal_high", (float(left["level"]) + float(right["level"])) / 2.0, [left, right])
        for left, right in equal_high_pairs
    ]
    result["records"] = [
        record
        for record in (
            canonical_record(kind, level, items) for kind, level, items in canonical
        )
        if record is not None
    ]
    return result


def classify_premium_discount(price: float, swings: dict[str, list[dict[str, Any]]]) -> str:
    highs = [item["level"] for item in swings["highs"][-_MAX_LIQUIDITY_LEVELS:]]
    lows = [item["level"] for item in swings["lows"][-_MAX_LIQUIDITY_LEVELS:]]
    if not highs or not lows:
        return "unknown"
    high = max(highs)
    low = min(lows)
    if high == low:
        return "equilibrium"
    midpoint = (high + low) / 2
    if price >= midpoint + (high - low) * _PD_THRESHOLD:
        return "premium"
    if price <= midpoint - (high - low) * _PD_THRESHOLD:
        return "discount"
    return "equilibrium"


def premium_discount_bounds(swings: dict[str, list[dict[str, Any]]]) -> dict[str, float | str]:
    highs = [item["level"] for item in swings["highs"][-_MAX_LIQUIDITY_LEVELS:]]
    lows = [item["level"] for item in swings["lows"][-_MAX_LIQUIDITY_LEVELS:]]
    if not highs or not lows:
        return {"status": "unknown"}
    high = max(highs)
    low = min(lows)
    return {"status": "ok", "high": high, "low": low, "midpoint": (high + low) / 2}


def detect_liquidity_sweeps(
    candles: list[Candle],
    swings: dict[str, list[dict[str, Any]]],
    *,
    symbol: str = "",
    timeframe: str = "",
    lookback_bars: int = 6,
    max_results: int | None = _MAX_LIQUIDITY_LEVELS,
    causal_only: bool = False,
    tick_size: float | None = None,
    atr_value: float | None = None,
    atr_current: float | None = None,
    excursion_buffer: float | None = None,
    liquidity_pools: dict[str, Any] | None = None,
    pool_provenance: str = "canonical",
) -> dict[str, list[dict[str, Any]]]:
    """Detect sweeps that exceed a pool and reclaim within the sweep candle.

    ``pool_provenance`` selects how a `liquidity_pools` payload is read: ``"canonical"`` (the
    default) trusts only the canonical `records` container, while ``"legacy"`` is an explicit
    caller declaration that the payload's numeric projection is the authority. A caller may only
    choose ``"legacy"`` when it knows its pools were built without canonical provenance; neither
    an empty nor a defective `records` container falls back to the numeric route by itself.
    """

    if pool_provenance not in ("canonical", "legacy"):
        raise ValueError("pool_provenance must be 'canonical' or 'legacy'")
    if len(candles) < 3:
        return {"swept_highs": [], "swept_lows": []}
    safe_lookback = max(1, int(lookback_bars))
    recent_start = max(0, len(candles) - safe_lookback)

    normalized_atr = atr_value if atr_value is not None else atr_current
    if excursion_buffer is not None:
        excursion = float(excursion_buffer)
        if not isfinite(excursion) or excursion < 0:
            raise ValueError("excursion_buffer must be finite and non-negative")
    elif tick_size is not None or normalized_atr is not None:
        if tick_size is None or normalized_atr is None:
            return {"swept_highs": [], "swept_lows": []}
        tick = float(tick_size)
        atr = float(normalized_atr)
        if not isfinite(tick) or not isfinite(atr) or tick <= 0 or atr <= 0:
            raise ValueError("tick_size and ATR must be finite and positive")
        excursion = max(2.0 * tick, 0.10 * atr)
    else:
        excursion = 0.0

    raw_highs = swings.get("highs", []) if isinstance(swings, dict) else []
    raw_lows = swings.get("lows", []) if isinstance(swings, dict) else []

    def eligible_swing(item: object) -> bool:
        if not isinstance(item, dict):
            return False
        if "confirmed" in item and item.get("confirmed") is not True:
            return False
        if "usable" in item and item.get("usable") is not True:
            return False
        if item.get("provisional") is True:
            return False
        try:
            return isfinite(float(item.get("level")))
        except (TypeError, ValueError, OverflowError):
            return False

    typed_metadata = any(
        isinstance(item, dict)
        and any(key in item for key in ("confirmed", "usable", "provisional"))
        for item in [
            *(raw_highs if isinstance(raw_highs, list) else []),
            *(raw_lows if isinstance(raw_lows, list) else []),
        ]
    )
    if typed_metadata and tick_size is None and normalized_atr is None and excursion_buffer is None:
        return {"swept_highs": [], "swept_lows": []}

    def pool_id(kind: str, level: float, source: dict[str, Any] | None) -> str:
        if isinstance(source, dict):
            explicit = str(
                source.get("pool_id", source.get("swing_id", "")) or ""
            ).strip()
            if explicit:
                return explicit
        return f"{kind}:{level:.15g}"

    swing_by_id = {
        str(item.get("swing_id", "") or "").strip(): item
        for item in [
            *(raw_highs if isinstance(raw_highs, list) else []),
            *(raw_lows if isinstance(raw_lows, list) else []),
        ]
        if isinstance(item, dict) and str(item.get("swing_id", "") or "").strip()
    }

    def canonical_candidates(side: str) -> list[dict[str, Any]]:
        """Sweep candidates from the canonical `records` container (A3-005 rule 3, F07).

        A record may grant a sweep only when its own lineage is complete: a kind for this side, a
        finite level, a pool ID, non-empty `source_ids` where every ID has its own `sources` entry,
        and a usable instant on every source. Anything else yields no candidate — the numeric
        level projection and a numeric level match are never allowed to stand in for missing
        lineage, and an unusable or unparsable timestamp never becomes a usable source.
        """

        prefix = "high" if side == "sell" else "low"
        wanted_kinds = (f"equal_{prefix}", f"swing_{prefix}")
        raw = liquidity_pools.get("records")
        if isinstance(raw, dict):
            entries = [
                entry
                for nested in raw.values()
                for entry in (nested if isinstance(nested, list) else [nested])
            ]
        elif isinstance(raw, (list, tuple)):
            entries = list(raw)
        else:
            entries = []

        records: list[dict[str, Any]] = []
        seen_pool_ids: set[str] = set()
        for record in entries:
            if not isinstance(record, dict):
                continue
            kind = str(record.get("kind", "") or "")
            if kind not in wanted_kinds:
                continue
            try:
                level = float(record.get("level"))
            except (TypeError, ValueError, OverflowError):
                continue
            if not isfinite(level):
                continue
            canonical_pool_id = str(record.get("pool_id", "") or "").strip()
            raw_source_ids = record.get("source_ids")
            raw_sources = record.get("sources")
            if not canonical_pool_id or canonical_pool_id in seen_pool_ids:
                continue
            if not isinstance(raw_source_ids, (list, tuple)) or not raw_source_ids:
                continue
            if not isinstance(raw_sources, (list, tuple)) or not raw_sources:
                continue
            source_ids = [str(entry).strip() for entry in raw_source_ids]
            if any(not entry for entry in source_ids):
                continue
            if len(set(source_ids)) != len(source_ids):
                continue
            usable_instants: list[tuple[datetime, str]] = []
            declared_ids: set[str] = set()
            complete = True
            for entry in raw_sources:
                if not isinstance(entry, dict):
                    complete = False
                    break
                swing_id = str(entry.get("swing_id", "") or "").strip()
                usable_at_text = entry.get("usable_at")
                usable_instant = _parse_usable_instant(usable_at_text)
                if not swing_id or usable_instant is None:
                    complete = False
                    break
                declared_ids.add(swing_id)
                usable_instants.append((usable_instant, str(usable_at_text)))
            if not complete or set(source_ids) - declared_ids:
                continue
            seen_pool_ids.add(canonical_pool_id)
            # The pool becomes usable only once every source does (A-D01, max of the sources).
            pool_usable_instant, pool_usable_text = max(
                usable_instants, key=lambda item: item[0],
            )
            single = source_ids[0] if len(source_ids) == 1 else None
            matched = swing_by_id.get(single) if single else None
            records.append({
                "level": level,
                "kind": kind,
                "source": matched,
                "pool_id": canonical_pool_id,
                "source_ids": source_ids,
                "usable_at": pool_usable_instant,
                "usable_at_text": pool_usable_text,
                "canonical": {
                    "source_ids": source_ids,
                    "source_swing_id": single,
                    "source_swing_index": (
                        matched.get("index") if isinstance(matched, dict) else None
                    ),
                    "source_swing_time": (
                        matched.get("pivot_time", matched.get("time"))
                        if isinstance(matched, dict) else None
                    ),
                    "usable_at_text": pool_usable_text,
                },
            })
        # Equal pools keep the projection's precedence over single-source swing pools, so the
        # per-candle first-match behaviour below stays what the pool projection already implied.
        records.sort(key=lambda record: wanted_kinds.index(str(record["kind"])))
        return records

    def candidates(
        side: str,
        source_items: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not isinstance(liquidity_pools, dict):
            return [
                {"level": float(item["level"]), "kind": "swing", "source": item}
                for item in source_items
                if eligible_swing(item)
            ]
        if pool_provenance == "legacy":
            # Explicit caller declaration: this payload's numeric projection is the authority.
            # The pre-canonical rule is restored verbatim — every numeric level of the side is a
            # candidate and its source is the swing at that same level. Only a caller that knows
            # its pools carry no canonical provenance may choose this branch; an empty or
            # defective `records` container never falls back here on its own.
            prefix = "high" if side == "sell" else "low"
            result: list[dict[str, Any]] = []
            seen: set[float] = set()
            for key in (f"equal_{prefix}s", f"swing_{prefix}s"):
                values = liquidity_pools.get(key, [])
                if not isinstance(values, list):
                    continue
                kind = "equal_" + prefix if key.startswith("equal_") else "swing_" + prefix
                for raw_level in values:
                    try:
                        level = float(raw_level)
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if not isfinite(level) or level in seen:
                        continue
                    seen.add(level)
                    source = next(
                        (
                            item for item in source_items
                            if eligible_swing(item) and float(item["level"]) == level
                        ),
                        None,
                    )
                    result.append({
                        "level": level,
                        "kind": kind,
                        "source": source,
                        "pool_id": pool_id(kind, level, source),
                    })
            return result
        if "records" in liquidity_pools:
            # The canonical container is the authority for the whole payload: a level is only
            # usable through its record, so an empty or defective container grants no sweep.
            return canonical_candidates(side)
        # Pool payload without the canonical container: an externally supplied numeric
        # projection, where only the equal level stays a source (task67 contract). A numeric
        # swing level carries no lineage at all — it cannot be matched back to its swing without
        # a level lookup, so it grants nothing (A3-005 rule 3).
        prefix = "high" if side == "sell" else "low"
        kind = f"equal_{prefix}"
        values = liquidity_pools.get(f"equal_{prefix}s", [])
        if not isinstance(values, list):
            return []
        result: list[dict[str, Any]] = []
        seen: set[float] = set()
        for raw_level in values:
            try:
                level = float(raw_level)
            except (TypeError, ValueError, OverflowError):
                continue
            if not isfinite(level) or level in seen:
                continue
            seen.add(level)
            result.append({
                "level": level,
                "kind": kind,
                "source": None,
                "pool_id": pool_id(kind, level, None),
            })
        return result

    swing_highs = candidates(
        "sell", raw_highs[-safe_lookback:] if isinstance(raw_highs, list) else []
    )
    swing_lows = candidates(
        "buy", raw_lows[-safe_lookback:] if isinstance(raw_lows, list) else []
    )
    swept_highs: list[dict[str, Any]] = []
    swept_lows: list[dict[str, Any]] = []

    def close_moment(candle: Candle) -> datetime:
        normalized_timeframe = str(timeframe or "").strip().upper()
        if normalized_timeframe in SMC_TIMEFRAME_INTERVALS:
            return _event_close(candle, normalized_timeframe)
        return candle.time

    def close_timestamp(candle: Candle) -> str:
        return close_moment(candle).isoformat()

    def evidence(
        *,
        candle: Candle,
        candle_index: int,
        level: float,
        side: str,
        kind: str,
        source: dict[str, Any] | None,
        source_pool_id: str,
        depth: float,
        canonical: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        occurred_at = candle.time.isoformat()
        payload: dict[str, Any] = {
            "sweep_id": build_sweep_id(
                symbol=symbol,
                timeframe=timeframe,
                side=side,
                kind=kind,
                level=level,
                occurred_at=occurred_at,
            ),
            "side": side,
            "kind": kind,
            "level": level,
            "index": candle_index,
            "time": occurred_at,
            "occurred_at": occurred_at,
            "reclaimed_at": close_timestamp(candle),
            "reclaim_bars": 1,
            "depth": depth,
            "excursion_buffer": excursion,
            "source_pool_id": source_pool_id,
            "source_pool": source_pool_id,
            "source_pool_kind": kind,
            "source_swing_id": (
                str(source.get("swing_id", "") or "").strip()
                if isinstance(source, dict) else None
            ),
            "source_swing_index": source.get("index") if isinstance(source, dict) else None,
            "source_swing_time": (
                source.get("pivot_time", source.get("time"))
                if isinstance(source, dict) else None
            ),
            "sweep_link_version": SMC_SWEEP_LINK_VERSION,
        }
        if canonical is not None:
            # Canonical pool provenance travels with the sweep: the pool identity comes from the
            # record, and the lineage/time are the record's own (never a numeric level match).
            payload["source_swing_id"] = canonical["source_swing_id"]
            payload["source_swing_index"] = canonical["source_swing_index"]
            payload["source_swing_time"] = canonical["source_swing_time"]
            payload["source_ids"] = list(canonical["source_ids"])
            payload["source_pool_usable_at"] = canonical["usable_at_text"]
        if normalized_atr is not None:
            payload["depth_atr"] = depth / float(normalized_atr)
        return payload

    for candle_index in range(recent_start, len(candles)):
        candle = candles[candle_index]
        candle_close = close_moment(candle)
        for swing in swing_highs:
            source = swing.get("source") if isinstance(swing, dict) else None
            if (
                causal_only
                and isinstance(source, dict)
                and source.get("index") is not None
                and int(source["index"]) >= candle_index
            ):
                continue
            # A-D01: the pool is usable only once every source is, and only from that instant on.
            # Equality is eligible; a source that becomes usable after this candle's close is not.
            if swing.get("usable_at") is not None and swing["usable_at"] > candle_close:
                continue
            level = float(swing["level"])
            if candle.high > level + excursion and candle.close < level:
                swept_highs.append(evidence(
                    candle=candle,
                    candle_index=candle_index,
                    level=level,
                    side="sell",
                    kind="swept_high",
                    source=source if isinstance(source, dict) else None,
                    source_pool_id=pool_id(
                        swing.get("kind", "swing_high") if isinstance(swing, dict) else "swing_high",
                        level,
                        source,
                    ) if not swing.get("pool_id") else str(swing["pool_id"]),
                    depth=candle.high - level,
                    canonical=swing.get("canonical"),
                ))
                break
        for swing in swing_lows:
            source = swing.get("source") if isinstance(swing, dict) else None
            if (
                causal_only
                and isinstance(source, dict)
                and source.get("index") is not None
                and int(source["index"]) >= candle_index
            ):
                continue
            if swing.get("usable_at") is not None and swing["usable_at"] > candle_close:
                continue
            level = float(swing["level"])
            if candle.low < level - excursion and candle.close > level:
                swept_lows.append(evidence(
                    candle=candle,
                    candle_index=candle_index,
                    level=level,
                    side="buy",
                    kind="swept_low",
                    source=source if isinstance(source, dict) else None,
                    source_pool_id=pool_id(
                        swing.get("kind", "swing_low") if isinstance(swing, dict) else "swing_low",
                        level,
                        source,
                    ) if not swing.get("pool_id") else str(swing["pool_id"]),
                    depth=level - candle.low,
                    canonical=swing.get("canonical"),
                ))
                break
    if max_results is None:
        return {"swept_highs": swept_highs, "swept_lows": swept_lows}
    safe_limit = max(0, int(max_results))
    if safe_limit == 0:
        return {"swept_highs": [], "swept_lows": []}
    return {
        "swept_highs": swept_highs[-safe_limit:],
        "swept_lows": swept_lows[-safe_limit:],
    }


def _attach_zone_sweep_links(
    zone_groups: tuple[tuple[str, list[dict[str, Any]]], ...],
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    *,
    candles: list[Candle],
    symbol: str,
    timeframe: str,
    tf_minutes: int,
) -> None:
    """Attach canonical one-to-one sweep links across every zone family."""

    candidates: list[dict[str, Any]] = []
    for family, zones in zone_groups:
        for zone in zones:
            origin_index = int(
                zone.get("origin_index", zone.get("index", -1))
            )
            origin_time = str(
                zone.get("origin_time", zone.get("time", "")) or ""
            )
            direction = zone_side(zone, family)
            zone_id = str(zone.get("zone_id", "") or "").strip() or build_zone_id(
                symbol=symbol,
                timeframe=timeframe or str(tf_minutes),
                family=family,
                direction=direction,
                origin_time=origin_time,
                low=zone.get("low", 0),
                high=zone.get("high", 0),
            )
            zone.update({
                "zone_id": zone_id,
                "family": family,
                "direction": direction,
                "origin_index": origin_index,
                "origin_time": origin_time,
                "formation_start_index": int(
                    zone.get("formation_start_index", origin_index)
                ),
                "departure_end_index": int(
                    zone.get("departure_end_index", origin_index)
                ),
            })
            for key, value in empty_sweep_link_payload().items():
                zone.setdefault(key, value)
            candidates.append(zone)

    links = associate_sweeps_to_zones(
        candidates,
        liquidity_sweeps,
        atr_value=_latest_atr(candles),
    )
    # The claim carries the *setup's* availability, resolved once per owner, so the child whose
    # link happened to be projected cannot redefine when the setup became available (F08).
    setup_availability = setup_availability_by_owner(candidates)
    # The sweep payload keyed by identity, so a claim can carry its sweep's canonical provenance
    # and real reclaim time instead of losing them at this boundary (A3-008 rule 3, C-R1).
    sweeps_by_id: dict[str, dict[str, Any]] = {}
    for sweep_key in ("swept_lows", "swept_highs"):
        sweep_values = liquidity_sweeps.get(sweep_key, [])
        if not isinstance(sweep_values, list):
            continue
        for recorded in sweep_values:
            if not isinstance(recorded, dict):
                continue
            recorded_id = str(recorded.get("sweep_id", "") or "")
            if recorded_id:
                sweeps_by_id.setdefault(recorded_id, recorded)
    sweep_to_zones: dict[str, list[str]] = {}
    ownership_claims: list[dict[str, Any]] = []
    for zone in candidates:
        link = links.get(str(zone.get("zone_id", "")))
        if link is None:
            continue
        zone.update(link.to_zone_payload())
        sweep_to_zones.setdefault(link.sweep_id, []).append(link.zone_id)
        if link.setup_id:
            linked_sweep = sweeps_by_id.get(link.sweep_id)
            claim = {
                **link.to_dict(),
                "zone_id": link.zone_id,
                "side": zone.get("direction"),
                "setup_available_at": setup_availability.get(setup_owner_key(zone)),
                # Canonical provenance travels with the claim: a claim built from a canonical
                # sweep must never be read as a legacy one because this boundary dropped its
                # fields. A sweep without canonical source lineage stays legacy, so the boundary
                # approved in §A3.146 is unchanged (C-R1).
                "pool_id": (
                    linked_sweep.get("source_pool_id")
                    if isinstance(linked_sweep, dict) and linked_sweep.get("source_ids")
                    else None
                ),
                "source_ids": (
                    linked_sweep.get("source_ids")
                    if isinstance(linked_sweep, dict) else None
                ),
            }
            # Only the sweep's own reclaim close travels as the claim time. A missing
            # `reclaimed_at` stays missing — the open time, `sweep_time` or the remaining claim
            # timestamp must never stand in for it, so a canonical claim without it fails closed.
            # Legacy alias resolution belongs to the helper's explicit legacy branch (C-R1 rest).
            if isinstance(linked_sweep, dict) and linked_sweep.get("reclaimed_at"):
                claim["reclaimed_at"] = linked_sweep["reclaimed_at"]
            ownership_claims.append(claim)

    # The sweeps that already carry a recorded consumption are the authority for this pass: an
    # owner and assignment already granted must survive a replay, a restore or a later window
    # (A-D06, F10). The window is the whole sweep payload, so completeness is declared explicitly.
    assignment_history: dict[str, dict[str, Any]] = {}
    for recorded_id, recorded in sweeps_by_id.items():
        if not recorded.get("consumed"):
            continue
        recorded_sources = recorded.get("source_ids")
        assignment_history[recorded_id] = {
            "sweep_id": recorded_id,
            "owner_setup_id": recorded.get("owner_setup_id"),
            "assignment_id": recorded.get("assignment_id"),
            "assigned_at": recorded.get("assigned_at"),
            "claim_eligible_at": recorded.get("claim_eligible_at"),
            "contribution_applied": recorded.get("contribution_applied", True),
            # Only a sweep with canonical pool lineage may be tied back by pool identity;
            # a legacy numeric pool id is not an identity, so it stays sweep-keyed.
            "pool_id": recorded.get("source_pool_id") if recorded_sources else None,
            "source_ids": recorded_sources,
        }

    consumed = mark_sweeps_consumed(
        liquidity_sweeps, ownership_claims,
        assignment_history=assignment_history,
        history_complete=True,
    )
    assignments = consumed.get("assignments", {})
    for zone in candidates:
        sweep_id = str(zone.get("linked_sweep_id", "") or "")
        assignment = assignments.get(sweep_id)
        if not isinstance(assignment, dict):
            continue
        zone.update({
            "sweep_assignment_id": assignment.get("assignment_id"),
            "sweep_owner_setup_id": assignment.get("owner_setup_id"),
            "sweep_assigned_at": assignment.get("assigned_at"),
            "sweep_contribution_applied": any(
                claim.get("zone_id") == zone.get("zone_id")
                and claim.get("contribution_applied") is True
                for claim in consumed.get("claims", [])
            ),
        })
    for key, values in consumed.get("sweeps", {}).items():
        if isinstance(values, list):
            liquidity_sweeps[key] = values

    for key in ("swept_lows", "swept_highs"):
        values = liquidity_sweeps.get(key, [])
        if not isinstance(values, list):
            continue
        for sweep in values:
            if not isinstance(sweep, dict):
                continue
            sweep_id = str(sweep.get("sweep_id", "") or "")
            linked_zone_ids = sorted(set(sweep_to_zones.get(sweep_id, [])))
            recorded_zone_id = str(sweep.get("linked_zone_id", "") or "")
            if linked_zone_ids:
                sweep["linked_zone_id"] = linked_zone_ids[0]
            else:
                # A consumed sweep whose window no longer holds its owner keeps the link it was
                # granted rather than losing it to this snapshot (A3-078, F10).
                sweep["linked_zone_id"] = recorded_zone_id or None
            if len(linked_zone_ids) > 1:
                sweep["linked_zone_ids"] = linked_zone_ids
            sweep["sweep_link_version"] = SMC_SWEEP_LINK_VERSION


def _latest_atr(candles: list[Candle]) -> float | None:
    if not candles:
        return None
    values = atr(
        [candle.high for candle in candles],
        [candle.low for candle in candles],
        [candle.close for candle in candles],
        _ATR_PERIOD,
    )
    value = values[-1] if values else None
    return float(value) if value is not None and value > 0 else None


def atr_reference_before_event(
    candles: Sequence[Candle],
    *,
    timeframe: str,
    event_index: int | None = None,
    event_time: datetime | str | None = None,
    period: int = _ATR_PERIOD,
    source_event_id: str | None = None,
    window: Any = None,
) -> SmcAtrReference | None:
    """Return same-timeframe ATR from candles strictly before an event.

    The event candle is excluded from the ATR prefix.  Candles after the event
    are never read, so appending a later volatile snapshot cannot change this
    formation reference.  ``None`` means the causal prefix has not reached the
    published warm-up boundary or its ATR is not positive/finite.

    ``window`` is an optional :class:`core.smc_structure_window.StructureWindowReuse`
    the caller already validated and already holds an ATR series for (task 137).
    When it owns *candles*, the prefix validation and the prefix ATR scan are read
    from it instead of being redone; every warm-up and positivity check below is
    unchanged, and the value is the same one the prefix computation produced.
    """

    normalized_timeframe = str(timeframe or "").strip().upper()
    if normalized_timeframe not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {timeframe}")
    if isinstance(period, bool) or period <= 0:
        raise ValueError("SMC ATR period must be positive")
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")

    resolved_index = _resolve_event_index(
        candles,
        normalized_timeframe,
        event_index=event_index,
        event_time=event_time,
    )
    prefix = tuple(candles[:resolved_index])
    minimum_prefix = max(_ATR_FILTER_MIN_CANDLES, period + 1)
    if len(prefix) < minimum_prefix:
        return None
    reusable = window is not None and window.owns(candles)
    if reusable:
        # The window owner validated this exact candle sequence and holds its
        # ATR series; validation does not reorder or repair, so the reference
        # candle and the value are the ones the prefix path would produce.
        value = window.atr_before_index(candles, resolved_index, period=period)
        reference_candle = candles[resolved_index - 1]
    else:
        # Validate only the causal prefix.  Future/event records cannot invalidate
        # an already formed reference or influence its result.
        valid_prefix = require_valid_smc_candles(prefix, normalized_timeframe)
        values = atr(
            [candle.high for candle in valid_prefix],
            [candle.low for candle in valid_prefix],
            [candle.close for candle in valid_prefix],
            period,
        )
        value = values[-1] if values else None
        reference_candle = valid_prefix[-1]
    if value is None or not isfinite(float(value)) or float(value) <= 0:
        return None

    reference_time = candle_close_at(
        reference_candle.time,
        normalized_timeframe,
    )
    event_close = candle_close_at(candles[resolved_index].time, normalized_timeframe)
    return SmcAtrReference(
        timeframe=normalized_timeframe,
        period=period,
        value=float(value),
        reference_time=reference_time.isoformat(),
        event_time=(
            _parse_utc_timestamp(event_time, "event_time").isoformat()
            if event_time is not None
            else event_close.isoformat()
        ),
        source_event_id=source_event_id,
    )


def atr_value_before_event(
    candles: Sequence[Candle],
    *,
    timeframe: str,
    event_index: int | None = None,
    event_time: datetime | str | None = None,
    period: int = _ATR_PERIOD,
    window: Any = None,
) -> float | None:
    """Convenience projection of :func:`atr_reference_before_event`."""

    reference = atr_reference_before_event(
        candles,
        timeframe=timeframe,
        event_index=event_index,
        event_time=event_time,
        period=period,
        window=window,
    )
    return reference.value if reference is not None else None


def _resolve_event_index(
    candles: Sequence[Candle],
    timeframe: str,
    *,
    event_index: int | None,
    event_time: datetime | str | None,
) -> int:
    if event_index is None and event_time is None:
        raise ValueError("event_index or event_time is required")
    resolved: int | None = None
    if event_index is not None:
        if isinstance(event_index, bool) or not isinstance(event_index, int):
            raise ValueError("event_index must be an integer")
        if event_index < 0 or event_index >= len(candles):
            raise ValueError("event_index is outside candles")
        resolved = event_index
    if event_time is not None:
        target = _parse_utc_timestamp(event_time, "event_time")
        matches = [
            index
            for index, candle in enumerate(candles)
            if _event_close(candle, timeframe) == target
        ]
        if len(matches) != 1:
            raise ValueError("event_time must match exactly one candle close")
        if resolved is not None and resolved != matches[0]:
            raise ValueError("event_index and event_time identify different candles")
        resolved = matches[0]
    assert resolved is not None
    return resolved


def _event_close(candle: Candle, timeframe: str) -> datetime:
    if not isinstance(candle, Candle):
        raise ValueError("candles must contain Candle objects")
    return candle_close_at(candle.time, timeframe).astimezone(timezone.utc)


def _parse_utc_timestamp(value: datetime | str | None, field_name: str) -> datetime:
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


def enrich_zones(
    zones: list[dict[str, Any]],
    candles: list[Candle],
    family: str,
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
    premium_discount_range: dict[str, float | str],
    *,
    tf_minutes: int = 60,
    scan_interval_min: int = 15,
    symbol: str = "",
    timeframe: str = "",
    tick_size: float | None = None,
) -> list[dict[str, Any]]:
    enriched = []
    stale_threshold = max(1, (scan_interval_min * 2) // tf_minutes)
    for zone in zones:
        item = dict(zone)
        if (
            str(family or "").strip().lower() == "fvg"
            or str(item.get("family", "") or "").strip().lower() == "fvg"
            or "fvg" in str(item.get("type", "") or "").strip().lower()
        ):
            item = update_fvg_fill(
                item,
                candles,
                tick_size=item.get("tick_size", tick_size),
                timeframe=timeframe,
                tf_minutes=tf_minutes,
            )
        for key, value in empty_sweep_link_payload().items():
            item.setdefault(key, value)
        index = int(
            item.get(
                "origin_index",
                item.get("index", len(candles) - 1),
            )
        )
        departure_end_index = int(
            item.get("departure_end_index", index)
        )
        future = candles[index + 1 :] if index + 1 < len(candles) else []
        low = float(item.get("low", 0.0))
        high = float(item.get("high", 0.0))
        side = zone_side(item, family)
        test_count = count_zone_tests(future, low, high)
        zone_broken_flag = zone_broken(future, low, high, side)
        mitigated = test_count > 0
        freshness_bars = max(0, len(candles) - 1 - index)
        stale = freshness_bars > stale_threshold
        zone_location = zone_premium_discount(low, high, premium_discount_range)
        liquidity_sweep = (
            bool(item.get("liquidity_sweep"))
            or _legacy_timeframe_has_sweep(side, liquidity_sweeps)
        )
        origin_time = str(
            item.get("origin_time", item.get("time", "")) or ""
        )
        zone_id = str(item.get("zone_id", "") or "").strip() or build_zone_id(
            symbol=symbol,
            timeframe=timeframe or str(tf_minutes),
            family=family,
            direction=side,
            origin_time=origin_time,
            low=low,
            high=high,
        )
        # A-D07: the item key and the `enrich_zones` argument are the same scope. Equal
        # values are parity, a single declared source is used as-is, and disagreeing
        # same-scope values are a conflict — neither side may win silently.
        item_tick = item.get("tick_size")
        argument_tick = tick_size
        tick_conflict = False
        resolved_tick = item_tick if item_tick is not None else argument_tick
        if item_tick is not None and argument_tick is not None:
            try:
                tick_parity = float(item_tick) == float(argument_tick)
            except (TypeError, ValueError, OverflowError):
                tick_parity = False
            if not tick_parity:
                tick_conflict = True
                resolved_tick = None
        # A payload that already carries terminal evidence keeps it (A3-007 §4): the derivation
        # below may not un-break it, and when the metadata cannot recompute the terminal the
        # declared kind/timestamp are preserved verbatim (B-R2).
        declared_status = str(
            item.get("lifecycle_status", "") or ""
        ).strip().lower()
        if declared_status not in {"invalid", "expired"}:
            declared_status = ""
        declared_terminal_fields = {
            key: item.get(key)
            for key in (
                "invalidated_at",
                "invalidation_index",
                "expired_at",
                "expiry_index",
            )
        }
        # History the payload already carries. When the metadata cannot recompute the
        # derivation these must not be rewritten by the replay (B-R2/history): the caller's
        # own visits, counts and retest anchors are kept verbatim rather than re-derived.
        declared_history = {
            key: item.get(key)
            for key in (
                "visits",
                "independent_retest_count",
                "bars_spent_inside",
                "first_retest_index",
                "first_retest_time",
                "mitigation_ratio",
                "lifecycle_mitigated",
                "departure_end_index",
            )
            if item.get(key) is not None
        }
        lifecycle = analyze_zone_lifecycle(
            candles=candles,
            low=low,
            high=high,
            side=side,
            origin_index=index,
            departure_end_index=departure_end_index,
            zone_id=zone_id,
            timeframe=timeframe,
            tf_minutes=tf_minutes,
            available_at=item.get("available_at"),
            tick_size=resolved_tick,
            atr_current=item.get("atr_current"),
            break_buffer=item.get("break_buffer"),
            tick_conflict=tick_conflict,
            tick_size_source=item.get("tick_size_source"),
            atr_source=item.get("atr_source"),
            declared_terminal_status=declared_status or None,
            declared_invalidated_at=declared_terminal_fields.get("invalidated_at"),
        )
        # Canonical lifecycle invalidation owns the buffered broken state.
        zone_broken_flag = lifecycle.lifecycle_broken
        item.update(
            {
                "zone_id": zone_id,
                "origin_index": index,
                "origin_time": origin_time,
                "freshness_bars": freshness_bars,
                "stale": stale,
                "mitigated": mitigated,
                "broken": zone_broken_flag,
                "test_count": test_count,
                "liquidity_sweep": liquidity_sweep,
                "zone_location": zone_location,
            }
        )
        item.update(lifecycle.to_dict())
        if lifecycle.metadata_state == "unknown":
            # Data-quality gate (A3-007): a rule that depends on unusable metadata makes the
            # zone unusable, but it is not a lifecycle status and must not revive or break a
            # terminal zone. The threshold stays `None` (never a silent zero).
            item["usable"] = False
        if declared_status and lifecycle.metadata_state == "unknown":
            # B-R2 precedence: the payload already declares terminal and the metadata cannot
            # recompute it, so that declaration outranks any expiry/invalidation the derivation
            # managed to produce without a usable threshold. Kind, timestamp, index and reason
            # are kept verbatim — none of them is re-derived, and no zero threshold is used.
            item["lifecycle_status"] = declared_status
            item["usable"] = False
            item["broken"] = declared_status == "invalid"
            item["lifecycle_broken"] = declared_status == "invalid"
            item["lifecycle_expired"] = declared_status == "expired"
            for key, value in declared_terminal_fields.items():
                item[key] = value
            for key, value in declared_history.items():
                item[key] = value
            item["reason_codes"] = list(dict.fromkeys([
                *(
                    item.get("reason_codes", [])
                    if isinstance(item.get("reason_codes"), (list, tuple))
                    else []
                ),
                "ZONE_INVALIDATED" if declared_status == "invalid" else "ZONE_EXPIRED",
            ]))
        elif lifecycle.lifecycle_broken:
            # Canonical terminal is authoritative (A-D04): the invalid state owns the status,
            # usability and the invalidation evidence, and the incoming legacy flags may not
            # overwrite it. Invalidation also outranks expiry on the same derivation.
            item["lifecycle_status"] = "invalid"
            item["usable"] = False
            item["broken"] = True
            item["lifecycle_broken"] = True
            item["invalidated_at"] = lifecycle.invalidated_at
            item["invalidation_index"] = lifecycle.invalidation_index
            item["reason_codes"] = list(dict.fromkeys([
                *(
                    item.get("reason_codes", [])
                    if isinstance(item.get("reason_codes"), (list, tuple))
                    else []
                ),
                "ZONE_INVALIDATED",
            ]))
        elif lifecycle.lifecycle_expired:
            item["lifecycle_status"] = "expired"
            item["expired_at"] = lifecycle.expired_at
            item["usable"] = False
            item["reason_codes"] = list(dict.fromkeys([
                *(
                    item.get("reason_codes", [])
                    if isinstance(item.get("reason_codes"), (list, tuple))
                    else []
                ),
                "ZONE_EXPIRED",
            ]))
        enriched.append(item)
    # Raw candidates carry no scorer score, so order by deterministic raw
    # lifecycle signals: actionable (non-broken, non-stale) and stronger
    # (tested, swept, recent, high displacement) zones first.
    return sorted(
        enriched,
        key=lambda zone: (
            bool(zone.get("broken", False)),
            bool(zone.get("stale", False)),
            -int(zone.get("test_count", 0) or 0),
            -int(bool(zone.get("liquidity_sweep", False))),
            -int(zone.get("origin_index", 0) or 0),
            -float(zone.get("displacement_multiple") or 0.0),
            str(zone.get("zone_id", "") or ""),
        ),
    )


def zone_side(zone: dict[str, Any], family: str) -> str:
    zone_type = str(zone.get("type", ""))
    if "demand" in zone_type or "bullish" in zone_type:
        return "buy"
    if "supply" in zone_type or "bearish" in zone_type:
        return "sell"
    return "buy" if family == "demand" else "sell"


def count_zone_tests(candles: list[Candle], low: float, high: float) -> int:
    return sum(1 for candle in candles if candle.low <= high and candle.high >= low)


def zone_broken(candles: list[Candle], low: float, high: float, side: str) -> bool:
    if side == "buy":
        return any(candle.close < low for candle in candles)
    return any(candle.close > high for candle in candles)


def zone_premium_discount(low: float, high: float, bounds: dict[str, float | str]) -> str:
    if bounds.get("status") != "ok":
        return "unknown"
    midpoint = float(bounds["midpoint"])
    center = (low + high) / 2
    width = max(float(bounds["high"]) - float(bounds["low"]), 1e-9)
    if center <= midpoint - width * _PD_THRESHOLD:
        return "discount"
    if center >= midpoint + width * _PD_THRESHOLD:
        return "premium"
    return "equilibrium"


def _legacy_timeframe_has_sweep(
    side: str,
    liquidity_sweeps: dict[str, list[dict[str, Any]]],
) -> bool:
    """Compatibility-only broadcast for sweep-linking across timeframes."""

    return bool(liquidity_sweeps.get("swept_lows" if side == "buy" else "swept_highs"))


def calculate_effective_zone_score(
    zone: dict[str, Any],
    side: str,
    atr_value: float | int | None,
) -> dict[str, Any]:
    """Return a conservative zone score and its breakdown.

    Unlike ``zone_quality_score``, repeated tests are treated as zone
    consumption, stale/mitigated state is explicit, and excessive source-zone
    width is penalized. Live consumers: execution planning in ``risk_engine``
    (sub-zone selection and stop-loss cap).
    """
    normalized_side = str(side or "").strip().lower()

    test_count_available = zone.get("test_count") is not None
    try:
        test_count = max(0, int(zone.get("test_count", 0) or 0))
    except (TypeError, ValueError):
        test_count = 0
        test_count_available = False
    try:
        freshness_bars = max(0, int(zone.get("freshness_bars", 999) or 999))
    except (TypeError, ValueError):
        freshness_bars = 999
    try:
        displacement = max(0.0, float(zone.get("displacement_multiple", 0) or 0))
    except (TypeError, ValueError):
        displacement = 0.0

    stale = bool(zone.get("stale"))
    mitigated = bool(zone.get("mitigated"))
    broken = bool(zone.get("broken"))

    freshness_bonus = 0
    if not stale:
        for max_bars, bonus in _EFFECTIVE_ZONE_FRESHNESS_BONUSES:
            if freshness_bars <= max_bars:
                freshness_bonus = bonus
                break

    if not test_count_available:
        test_count_adjustment = 0
    elif test_count == 0:
        test_count_adjustment = 4
    elif test_count == 1:
        test_count_adjustment = 2
    elif test_count == 2:
        test_count_adjustment = 0
    else:
        test_count_adjustment = -min(
            _EFFECTIVE_ZONE_MAX_RETEST_PENALTY,
            (test_count - 2) * _EFFECTIVE_ZONE_RETEST_PENALTY_STEP,
        )

    width_atr = None
    try:
        low = float(zone.get("low"))
        high = float(zone.get("high"))
        atr = float(atr_value)
        if high > low and atr > 0:
            width_atr = (high - low) / atr
    except (TypeError, ValueError):
        pass

    width_adjustment = 0
    if width_atr is not None:
        if width_atr <= _EFFECTIVE_ZONE_NARROW_WIDTH_ATR:
            width_adjustment = _EFFECTIVE_ZONE_NARROW_BONUS
        elif width_atr > _EFFECTIVE_ZONE_WIDE_WIDTH_ATR:
            width_adjustment = -min(
                _EFFECTIVE_ZONE_MAX_WIDTH_PENALTY,
                round(
                    (width_atr - _EFFECTIVE_ZONE_WIDE_WIDTH_ATR)
                    * _EFFECTIVE_ZONE_WIDTH_PENALTY_PER_ATR
                ),
            )

    displacement_bonus = min(
        _EFFECTIVE_ZONE_MAX_DISPLACEMENT_BONUS,
        int(displacement * _ZONE_DISPLACEMENT_MULTIPLIER),
    )
    liquidity_sweep_bonus = (
        _EFFECTIVE_ZONE_LIQUIDITY_SWEEP_BONUS
        if zone.get("liquidity_sweep")
        else 0
    )

    location = str(zone.get("zone_location", "") or "").strip().lower()
    if (
        normalized_side == "buy"
        and location == "discount"
        or normalized_side == "sell"
        and location == "premium"
    ):
        premium_discount_adjustment = _EFFECTIVE_ZONE_LOCATION_CORRECT_BONUS
    elif location == "equilibrium":
        premium_discount_adjustment = _EFFECTIVE_ZONE_LOCATION_EQUILIBRIUM_BONUS
    elif (
        normalized_side in {"buy", "sell"}
        and location in {"premium", "discount"}
    ):
        premium_discount_adjustment = -_EFFECTIVE_ZONE_LOCATION_WRONG_PENALTY
    else:
        premium_discount_adjustment = 0

    stale_penalty = -_EFFECTIVE_ZONE_STALE_PENALTY if stale else 0
    mitigation_penalty = -_EFFECTIVE_ZONE_MITIGATED_PENALTY if mitigated else 0
    pre_clamp_total = sum(
        (
            _EFFECTIVE_ZONE_SCORE_BASE,
            freshness_bonus,
            stale_penalty,
            mitigation_penalty,
            test_count_adjustment,
            width_adjustment,
            displacement_bonus,
            liquidity_sweep_bonus,
            premium_discount_adjustment,
        )
    )
    effective_score = 0 if broken else max(0, min(100, int(pre_clamp_total)))

    return {
        "effective_zone_score": effective_score,
        "effective_zone_score_breakdown": {
            "base": _EFFECTIVE_ZONE_SCORE_BASE,
            "freshness_bonus": freshness_bonus,
            "stale_penalty": stale_penalty,
            "mitigation_penalty": mitigation_penalty,
            "test_count_adjustment": test_count_adjustment,
            "width_adjustment": width_adjustment,
            "displacement_bonus": displacement_bonus,
            "liquidity_sweep_bonus": liquidity_sweep_bonus,
            "premium_discount_adjustment": premium_discount_adjustment,
            "source_zone_width_atr": (
                round(width_atr, 4) if width_atr is not None else None
            ),
            "pre_clamp_total": pre_clamp_total,
            "broken_override": broken,
        },
    }


def displacement_multiple_at(candles: list[Candle], index: int) -> float:
    if index < 0 or index >= len(candles):
        return 0.0
    candle = candles[index]
    window = candles[max(0, index - 20) : index]
    avg_range = sum(item.high - item.low for item in window) / len(window) if window else 0.0
    if avg_range <= 0:
        return 0.0
    return round((candle.high - candle.low) / avg_range, 2)


def swept_recent_low(candle: Candle, previous: list[Candle]) -> bool:
    lows = [item.low for item in previous[-8:]]
    return bool(lows and candle.low < min(lows) and candle.close > min(lows))


def swept_recent_high(candle: Candle, previous: list[Candle]) -> bool:
    highs = [item.high for item in previous[-8:]]
    return bool(highs and candle.high > max(highs) and candle.close < max(highs))



# ---------------------------------------------------------------------------
# Phase 5: Safe SMC flag extraction for trade gate decisions
# ---------------------------------------------------------------------------


def extract_smc_trade_flags(smc_context: dict[str, Any] | None, direction: str) -> dict[str, Any]:
    """Trich xuat cac flag SMC an toan cho trade gate.

    Tra ve dict cac flag doc tu SMC context, khong crash neu thieu du lieu.
    Dung H4 lam timeframe chinh cho structural signals, H1 cho liquidity.

    Chi tra ve structural flags (CHOCH, displacement, sweep). Selected zone
    khong duoc chon o day — selected zone luon den tu SMC result/consumer
    canonical.

    Parameters
    ----------
    smc_context : dict | None
        Output cua build_smc_context().
    direction : str
        "buy" hoac "sell".

    Returns
    -------
    dict
        {
            "choch_against_direction": bool,
            "liquidity_sweep_aligned": bool,
            "displacement_aligned": bool,
            "raw": dict,
        }
    """
    result: dict[str, Any] = {
        "choch_against_direction": False,
        "liquidity_sweep_aligned": False,
        "displacement_aligned": False,
        "raw": {},
    }

    if not isinstance(smc_context, dict):
        return result

    if direction not in ("buy", "sell"):
        return result

    h4 = smc_context.get("H4", {}) if isinstance(smc_context.get("H4"), dict) else {}
    h1 = smc_context.get("H1", {}) if isinstance(smc_context.get("H1"), dict) else {}

    # --- CHOCH against direction ---
    if direction == "buy":
        if h4.get("choch") and h4.get("displacement") == "bearish":
            result["choch_against_direction"] = True
        if h1.get("choch") and h1.get("displacement") == "bearish":
            result["choch_against_direction"] = True
    else:  # sell
        if h4.get("choch") and h4.get("displacement") == "bullish":
            result["choch_against_direction"] = True
        if h1.get("choch") and h1.get("displacement") == "bullish":
            result["choch_against_direction"] = True

    # --- Liquidity sweep aligned ---
    liq_sweeps = h1.get("liquidity_sweeps", {}) if isinstance(h1, dict) else {}
    if direction == "buy" and liq_sweeps.get("swept_lows"):
        result["liquidity_sweep_aligned"] = True
    elif direction == "sell" and liq_sweeps.get("swept_highs"):
        result["liquidity_sweep_aligned"] = True

    # --- Displacement aligned ---
    expected_disp = "bullish" if direction == "buy" else "bearish"
    if h4.get("displacement") == expected_disp:
        result["displacement_aligned"] = True

    # --- Raw snapshot ---
    result["raw"] = {
        "h4_structure": h4.get("structure"),
        "h4_bos": h4.get("bos"),
        "h4_choch": h4.get("choch"),
        "h4_displacement": h4.get("displacement"),
        "h1_liquidity_sweeps": bool(
            (isinstance(liq_sweeps, dict) and (liq_sweeps.get("swept_lows") or liq_sweeps.get("swept_highs")))
        ),
    }

    return result
