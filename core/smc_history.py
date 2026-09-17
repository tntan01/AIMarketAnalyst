"""Point-in-time history and coverage checks for SMC snapshots.

This module consumes already cutoff-filtered candles.  It never fills a gap,
reorders a record, or turns a zone with an uncovered origin into a fresh zone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence

from core.market_models import (
    Candle,
    SMC_TIMEFRAME_INTERVALS,
    validate_smc_candles,
)
from core.trading_session_calendar import (
    EXPECTED_SESSION_CLOSE,
    MARKET_HOLIDAY,
    BROKER_MAINTENANCE,
    trading_session_calendar,
)


SMC_MINIMUM_HISTORY = {"D1": 60, "H4": 60, "H1": 30, "M15": 15}
SMC_ZONE_LIFETIME_BARS = {"D1": 20, "H4": 30, "H1": 50, "M15": 80}
SMC_ATR_WARMUP_CANDLES = 15  # 14 true ranges plus the first price.
SMC_PIVOT_CONTEXT_BARS = 5
SMC_M15_CONFIRMATION_LAG_BARS = 48

_EXPECTED_CLOSURE_CLASSIFICATIONS = frozenset(
    {EXPECTED_SESSION_CLOSE, MARKET_HOLIDAY, BROKER_MAINTENANCE}
)


@dataclass(frozen=True, slots=True)
class SmcHistoryCoverage:
    """Auditable result of one timeframe's history/coverage assessment."""

    timeframe: str
    symbol: str | None
    status: str
    session_coverage_status: str
    raw_count: int
    minimum_required: int
    lifetime_required: int
    warmup_ready: bool
    origin_covered: bool | None
    freshness_eligible: bool
    first_open_at: str | None
    last_open_at: str | None
    missing_slots: tuple[str, ...]
    closed_session_slots: int
    reason_codes: tuple[str, ...]

    @property
    def coverage_incomplete(self) -> bool:
        return self.status != "complete"

    def to_dict(self) -> dict[str, object]:
        return {
            "timeframe": self.timeframe,
            "symbol": self.symbol,
            "status": self.status,
            "session_coverage_status": self.session_coverage_status,
            "raw_count": self.raw_count,
            "minimum_required": self.minimum_required,
            "lifetime_required": self.lifetime_required,
            "warmup_ready": self.warmup_ready,
            "origin_covered": self.origin_covered,
            "freshness_eligible": self.freshness_eligible,
            "first_open_at": self.first_open_at,
            "last_open_at": self.last_open_at,
            "missing_slots": list(self.missing_slots),
            "closed_session_slots": self.closed_session_slots,
            "reason_codes": list(self.reason_codes),
        }


def required_history_for_lifetime(timeframe: str) -> int:
    """Return the explicit history budget for lifetime replay.

    The budget is the larger of the published technical minimum and the
    lifetime plus ATR warm-up, pivot context, and the M15 confirmation lag.
    The confirmation lag is an M15-only addition; it is not silently converted
    into bars of another timeframe.
    """

    normalized = _normalize_timeframe(timeframe)
    confirmation_lag = (
        SMC_M15_CONFIRMATION_LAG_BARS if normalized == "M15" else 0
    )
    return max(
        SMC_MINIMUM_HISTORY[normalized],
        SMC_ZONE_LIFETIME_BARS[normalized]
        + (SMC_ATR_WARMUP_CANDLES - 1)
        + SMC_PIVOT_CONTEXT_BARS
        + confirmation_lag,
    )


def assess_smc_history(
    candles: Sequence[Candle],
    timeframe: str,
    *,
    symbol: str | None = None,
    origin_time: datetime | None = None,
    require_lifetime: bool = False,
    minimum_candles: int | None = None,
    window: object | None = None,
) -> SmcHistoryCoverage:
    """Assess history without synthesizing candles or freshness evidence.

    ``candles`` must already be filtered by ``closed_candles_at_cutoff``.  A
    valid weekend/holiday/maintenance break is evidence of a known closure and
    is not a coverage gap.  A gap inside an expected session is reported as
    ``SMC_COVERAGE_GAP``.  ``origin_time`` is optional for generic history
    checks; when it is absent, ``freshness_eligible`` is always false.

    ``window`` is an optional ``core.smc_structure_window.StructureWindowReuse``
    the caller already owns (task 137).  When it holds this exact candle window,
    the parts that depend only on the window — the candle validation, the open
    times and the coverage scan — are read from it instead of being recomputed
    per caller.  Everything that depends on ``origin_time``, on the lifetime
    requirement and on the assembly below is unchanged.
    """

    normalized = _normalize_timeframe(timeframe)
    if isinstance(candles, (str, bytes)) or not isinstance(candles, Sequence):
        raise ValueError("candles must be a sequence")
    if minimum_candles is not None:
        if isinstance(minimum_candles, bool) or minimum_candles < 0:
            raise ValueError("minimum_candles must be a non-negative integer")
        minimum = int(minimum_candles)
    elif require_lifetime:
        minimum = required_history_for_lifetime(normalized)
    else:
        minimum = SMC_MINIMUM_HISTORY[normalized]

    reusable = window is not None and window.is_window(candles)
    if reusable:
        assessed = window.history_window(normalized, symbol)
        issues = assessed.issues
        first_open = assessed.first_open
        last_open = assessed.last_open
        missing_slots: list[str] = []
        closed_session_slots = 0
        session_status = "known"
        # The coverage scan describes the complete window; the original only
        # reports it for a window the caller actually passed whole.
        if len(candles) > 1:
            missing_slots = list(assessed.missing_slots)
            closed_session_slots = assessed.closed_session_slots
            session_status = assessed.session_status
        reason_codes = list(dict.fromkeys(issue.code for issue in issues))
    else:
        issues = validate_smc_candles(candles, normalized)
        reason_codes = list(dict.fromkeys(issue.code for issue in issues))
        valid_timestamps = [_utc(candle.time) for candle in candles if _is_utc_aware(candle.time)]
        first_open = valid_timestamps[0] if valid_timestamps else None
        last_open = valid_timestamps[-1] if valid_timestamps else None
        missing_slots: list[str] = []
        closed_session_slots = 0
        session_status = "known"

    if not candles:
        reason_codes.extend(("SMC_TIMEFRAME_MISSING", f"SMC_{normalized}_MISSING"))
    elif not issues and len(candles) > 1:
        if not reusable:
            missing_slots, closed_session_slots, session_status = _find_coverage_gaps(
                candles,
                normalized,
                symbol,
            )
        if missing_slots:
            reason_codes.append("SMC_COVERAGE_GAP")
        if session_status == "unknown":
            reason_codes.append("SMC_SESSION_COVERAGE_UNKNOWN")

    if len(candles) < minimum:
        reason_codes.extend(
            ("SMC_INSUFFICIENT_HISTORY", f"SMC_{normalized}_INSUFFICIENT_HISTORY")
        )

    warmup_ready = len(candles) >= SMC_ATR_WARMUP_CANDLES and not issues
    if not warmup_ready:
        reason_codes.append("SMC_ATR_REFERENCE_UNAVAILABLE")

    origin_covered: bool | None = None
    if origin_time is not None:
        origin_utc = _utc(origin_time)
        origin_covered = origin_utc is not None and (
            first_open is not None
            and last_open is not None
            and first_open <= origin_utc <= last_open
        )
        if origin_utc is None:
            reason_codes.append("SMC_TIMESTAMP_INVALID")
        elif not origin_covered:
            reason_codes.append("SMC_COVERAGE_GAP")

    reason_codes = list(dict.fromkeys(reason_codes))
    insufficient = (
        not candles
        or len(candles) < minimum
        or bool(issues)
        or not warmup_ready
    )
    incomplete = bool(missing_slots) or session_status == "unknown" or origin_covered is False
    status = "insufficient" if insufficient else ("partial" if incomplete else "complete")
    freshness_eligible = (
        status == "complete"
        and origin_covered is True
        and warmup_ready
    )
    return SmcHistoryCoverage(
        timeframe=normalized,
        symbol=symbol,
        status=status,
        session_coverage_status=session_status,
        raw_count=len(candles),
        minimum_required=minimum,
        lifetime_required=required_history_for_lifetime(normalized),
        warmup_ready=warmup_ready,
        origin_covered=origin_covered,
        freshness_eligible=freshness_eligible,
        first_open_at=_format(first_open),
        last_open_at=_format(last_open),
        missing_slots=tuple(missing_slots),
        closed_session_slots=closed_session_slots,
        reason_codes=tuple(reason_codes),
    )


def _find_coverage_gaps(
    candles: Sequence[Candle],
    timeframe: str,
    symbol: str | None,
) -> tuple[list[str], int, str]:
    interval = SMC_TIMEFRAME_INTERVALS[timeframe]
    missing: list[str] = []
    closed_slots = 0
    session_status = "known"
    calendar = trading_session_calendar(symbol) if str(symbol or "").strip() else None
    for previous, current in zip(candles, candles[1:]):
        expected = _utc(previous.time) + interval
        current_open = _utc(current.time)
        while expected < current_open:
            if calendar is None:
                session_status = "unknown"
                missing.append(_format(expected) or "")
            else:
                classification = calendar.classify_missing_slot(
                    expected,
                    interval,
                    timeframe=timeframe,
                )
                if classification.expected_candle:
                    missing.append(_format(expected) or "")
                elif classification.classification in _EXPECTED_CLOSURE_CLASSIFICATIONS:
                    closed_slots += 1
            expected += interval
    return missing, closed_slots, session_status


def _normalize_timeframe(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in SMC_TIMEFRAME_INTERVALS:
        raise ValueError(f"Unsupported SMC timeframe: {value}")
    return normalized


def _is_utc_aware(value: object) -> bool:
    return isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None


def _utc(value: datetime) -> datetime | None:
    if not _is_utc_aware(value):
        return None
    return value.astimezone(timezone.utc)


def _format(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None
