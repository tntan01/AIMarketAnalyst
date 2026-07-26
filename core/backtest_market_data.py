from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from core.market_models import Candle
from core.trading_session_calendar import (
    UNEXPECTED_DATA_GAP,
    TradingSessionCalendar,
    trading_session_calendar,
)


DATA_MANIFEST_VERSION = "backtest-data-manifest-v2-session-aware"
BACKTEST_INTERVAL_CONVENTION = "[start,end)"

TIMEFRAME_DURATIONS: dict[str, timedelta] = {
    "D1": timedelta(days=1),
    "H4": timedelta(hours=4),
    "H1": timedelta(hours=1),
    "M15": timedelta(minutes=15),
}

# The controller deliberately loads a long D1 warm-up for EMA200. Intraday
# frames need materially shorter history for the indicators used by the live
# pipeline. Gaps before this scope remain auditable but do not block a later
# validation window that cannot consume them.
QUALITY_LOOKBACK_DAYS: dict[str, int] = {
    "D1": 365,
    "H4": 90,
    "H1": 30,
    "M15": 7,
}

REQUIRED_BACKTEST_TIMEFRAMES = ("D1", "H4", "H1")


@dataclass(frozen=True, slots=True)
class DataQualityIssue:
    code: str
    severity: str
    message: str
    timeframe: str | None = None


@dataclass(slots=True)
class TimeframeManifest:
    timeframe: str
    duration_seconds: int
    input_count: int
    normalized_count: int
    duplicate_count: int = 0
    conflicting_duplicate_count: int = 0
    naive_timestamp_count: int = 0
    timezone_converted_count: int = 0
    invalid_timestamp_count: int = 0
    invalid_ohlc_count: int = 0
    gap_count: int = 0
    missing_interval_count: int = 0
    gaps: list[dict[str, Any]] = field(default_factory=list)
    audited_gap_count: int = 0
    audited_missing_interval_count: int = 0
    out_of_scope_gap_count: int = 0
    out_of_scope_gaps: list[dict[str, Any]] = field(default_factory=list)
    expected_closure_count: int = 0
    expected_closed_interval_count: int = 0
    expected_closures: list[dict[str, Any]] = field(default_factory=list)
    coverage_start_missing_intervals: int = 0
    coverage_end_missing_intervals: int = 0
    quality_scope_start: str | None = None
    quality_scope_end: str | None = None
    coverage_open_start: str | None = None
    coverage_open_end: str | None = None
    coverage_close_end: str | None = None
    data_hash: str = ""


@dataclass(slots=True)
class DataManifest:
    version: str
    timezone: str
    candle_time_semantics: str
    interval_convention: str
    symbol: str
    session_policy: dict[str, Any]
    requested_start: str | None
    requested_end: str | None
    quality_status: str
    validation_eligible: bool
    dataset_hash: str
    timeframes: dict[str, TimeframeManifest]
    issues: list[DataQualityIssue]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "timezone": self.timezone,
            "candle_time_semantics": self.candle_time_semantics,
            "interval_convention": self.interval_convention,
            "symbol": self.symbol,
            "session_policy": self.session_policy,
            "requested_start": self.requested_start,
            "requested_end": self.requested_end,
            "quality_status": self.quality_status,
            "validation_eligible": self.validation_eligible,
            "dataset_hash": self.dataset_hash,
            "timeframes": {
                key: asdict(value)
                for key, value in sorted(self.timeframes.items())
            },
            "issues": [asdict(issue) for issue in self.issues],
        }


def timeframe_duration(timeframe: str) -> timedelta:
    normalized = str(timeframe or "").upper()
    try:
        return TIMEFRAME_DURATIONS[normalized]
    except KeyError as exc:
        raise ValueError(f"Timeframe không hỗ trợ: {timeframe}") from exc


def normalize_utc(value: datetime) -> tuple[datetime, bool, bool]:
    """Return UTC datetime, whether timezone was assumed, and whether converted."""
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc), True, False
    normalized = value.astimezone(timezone.utc)
    return normalized, False, normalized.utcoffset() != value.utcoffset()


def candle_close_time(candle: Candle, timeframe: str) -> datetime:
    opened_at, _assumed, _converted = normalize_utc(candle.time)
    return opened_at + timeframe_duration(timeframe)


def in_half_open_interval(
    value: datetime,
    start: datetime,
    end: datetime,
) -> bool:
    normalized_value, _assumed_value, _converted_value = normalize_utc(value)
    normalized_start, _assumed_start, _converted_start = normalize_utc(start)
    normalized_end, _assumed_end, _converted_end = normalize_utc(end)
    return normalized_start <= normalized_value < normalized_end


def closed_candle_snapshot(
    candles_by_timeframe: dict[str, list[Candle]],
    decision_time: datetime,
) -> dict[str, list[Candle]]:
    normalized_decision, _assumed, _converted = normalize_utc(decision_time)
    return {
        timeframe: [
            candle
            for candle in candles
            if candle_close_time(candle, timeframe) <= normalized_decision
        ]
        for timeframe, candles in candles_by_timeframe.items()
    }


def execution_candles_in_interval(
    candles: list[Candle],
    timeframe: str,
    *,
    start: datetime,
    end: datetime,
) -> list[Candle]:
    normalized_start, _assumed_start, _converted_start = normalize_utc(start)
    normalized_end, _assumed_end, _converted_end = normalize_utc(end)
    return [
        candle
        for candle in candles
        if normalize_utc(candle.time)[0] >= normalized_start
        and candle_close_time(candle, timeframe) < normalized_end
    ]


def prepare_backtest_data(
    candles_by_timeframe: dict[str, list[Candle]],
    *,
    symbol: str = "",
    requested_start: datetime | None = None,
    requested_end: datetime | None = None,
    session_calendar: TradingSessionCalendar | None = None,
) -> tuple[dict[str, list[Candle]], DataManifest]:
    normalized: dict[str, list[Candle]] = {}
    manifests: dict[str, TimeframeManifest] = {}
    issues: list[DataQualityIssue] = []
    calendar = session_calendar or trading_session_calendar(symbol)
    range_start = (
        normalize_utc(requested_start)[0]
        if isinstance(requested_start, datetime)
        else None
    )
    range_end = (
        normalize_utc(requested_end)[0]
        if isinstance(requested_end, datetime)
        else None
    )

    all_timeframes = sorted(
        set(candles_by_timeframe) | set(REQUIRED_BACKTEST_TIMEFRAMES)
    )
    for timeframe in all_timeframes:
        source = list(candles_by_timeframe.get(timeframe) or [])
        rows, manifest, timeframe_issues = _normalize_timeframe(
            timeframe,
            source,
            session_calendar=calendar,
            requested_start=range_start,
            requested_end=range_end,
        )
        normalized[timeframe] = rows
        manifests[timeframe] = manifest
        issues.extend(timeframe_issues)

    for timeframe in REQUIRED_BACKTEST_TIMEFRAMES:
        if not normalized.get(timeframe):
            issues.append(
                DataQualityIssue(
                    code="REQUIRED_TIMEFRAME_MISSING",
                    severity="ERROR",
                    timeframe=timeframe,
                    message=f"Thiếu dữ liệu bắt buộc {timeframe}.",
                )
            )

    dataset_payload = {
        "timeframes": {
            timeframe: manifest.data_hash
            for timeframe, manifest in sorted(manifests.items())
        },
        "session_policy_fingerprint": calendar.fingerprint,
        "requested_start": range_start.isoformat() if range_start else None,
        "requested_end": range_end.isoformat() if range_end else None,
    }
    dataset_hash = _sha256_json(dataset_payload)
    has_error = any(issue.severity == "ERROR" for issue in issues)
    has_warning = any(issue.severity == "WARNING" for issue in issues)
    quality_status = "INVALID" if has_error else "WARNING" if has_warning else "OK"
    manifest = DataManifest(
        version=DATA_MANIFEST_VERSION,
        timezone="UTC",
        candle_time_semantics="open_time; close_time=open_time+duration",
        interval_convention=BACKTEST_INTERVAL_CONVENTION,
        symbol=calendar.symbol,
        session_policy=calendar.to_dict(),
        requested_start=range_start.isoformat() if range_start else None,
        requested_end=range_end.isoformat() if range_end else None,
        quality_status=quality_status,
        validation_eligible=not has_error and not has_warning,
        dataset_hash=dataset_hash,
        timeframes=manifests,
        issues=issues,
    )
    return normalized, manifest


def normalize_candle_series(
    candles: list[Candle],
    timeframe: str,
) -> list[Candle]:
    rows, _manifest, _issues = _normalize_timeframe(
        timeframe,
        candles,
        session_calendar=trading_session_calendar(""),
    )
    return rows


def validation_quality_errors(manifest: DataManifest) -> list[str]:
    return [
        f"{issue.code}"
        + (f"[{issue.timeframe}]" if issue.timeframe else "")
        + f": {issue.message}"
        for issue in manifest.issues
        if issue.severity in {"ERROR", "WARNING"}
    ]


def _normalize_timeframe(
    timeframe: str,
    source: list[Candle],
    *,
    session_calendar: TradingSessionCalendar,
    requested_start: datetime | None = None,
    requested_end: datetime | None = None,
) -> tuple[list[Candle], TimeframeManifest, list[DataQualityIssue]]:
    duration = timeframe_duration(timeframe)
    issues: list[DataQualityIssue] = []
    normalized_rows: list[tuple[Candle, bool, bool, bool]] = []
    invalid_timestamp_count = 0

    for candle in source:
        if not isinstance(candle.time, datetime):
            invalid_timestamp_count += 1
            continue
        try:
            opened_at, assumed_utc, converted = normalize_utc(candle.time)
        except (OverflowError, TypeError, ValueError):
            invalid_timestamp_count += 1
            continue
        try:
            open_price = float(candle.open)
            high_price = float(candle.high)
            low_price = float(candle.low)
            close_price = float(candle.close)
            volume = float(candle.volume)
        except (TypeError, ValueError):
            open_price = high_price = low_price = close_price = volume = float("nan")
        normalized_candle = Candle(
            time=opened_at,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            volume=volume,
        )
        valid_ohlc = _valid_ohlc(normalized_candle)
        normalized_rows.append(
            (normalized_candle, assumed_utc, converted, valid_ohlc)
        )

    # The complete value tuple makes duplicate resolution deterministic even
    # when the provider returns the same timestamps in a different order.
    normalized_rows.sort(key=lambda row: row[0].time)

    deduplicated: list[Candle] = []
    by_timestamp: dict[datetime, list[tuple[Candle, bool, bool, bool]]] = {}
    for row in normalized_rows:
        by_timestamp.setdefault(row[0].time, []).append(row)

    duplicate_count = 0
    conflicting_duplicate_count = 0
    naive_count = sum(1 for _candle, assumed, _converted, _valid in normalized_rows if assumed)
    converted_count = sum(1 for _candle, _assumed, converted, _valid in normalized_rows if converted)
    invalid_ohlc_count = sum(1 for _candle, _assumed, _converted, valid in normalized_rows if not valid)

    for opened_at in sorted(by_timestamp):
        candidates = by_timestamp[opened_at]
        if len(candidates) > 1:
            duplicate_count += len(candidates) - 1
            distinct_values = {
                _candle_value_key(candidate[0])
                for candidate in candidates
            }
            if len(distinct_values) > 1:
                conflicting_duplicate_count += len(candidates) - 1
        # Choose the lexicographically greatest complete value. This is
        # deterministic and therefore independent from provider input order.
        valid_candidates = [
            candidate for candidate in candidates if candidate[3]
        ]
        if valid_candidates:
            selected = max(
                valid_candidates,
                key=lambda row: _candle_value_key(row[0]),
            )
            deduplicated.append(selected[0])

    audited_gaps, expected_closures = _classify_gaps(
        deduplicated,
        duration,
        timeframe=timeframe,
        session_calendar=session_calendar,
    )
    quality_scope_start = _quality_scope_start(timeframe, requested_start)
    quality_scope_end = requested_end
    gaps = [
        gap for gap in audited_gaps
        if _gap_overlaps_scope(
            gap,
            duration,
            quality_scope_start,
            quality_scope_end,
        )
    ]
    out_of_scope_gaps = [gap for gap in audited_gaps if gap not in gaps]
    (
        coverage_start_missing,
        coverage_end_missing,
        coverage_issues,
    ) = _coverage_quality(
        deduplicated,
        duration,
        timeframe=timeframe,
        session_calendar=session_calendar,
        requested_start=requested_start,
        requested_end=requested_end,
    )
    issues.extend(coverage_issues)
    data_hash = _sha256_json(
        [_serialized_candle(candle) for candle in deduplicated]
    )
    manifest = TimeframeManifest(
        timeframe=timeframe,
        duration_seconds=int(duration.total_seconds()),
        input_count=len(source),
        normalized_count=len(deduplicated),
        duplicate_count=duplicate_count,
        conflicting_duplicate_count=conflicting_duplicate_count,
        naive_timestamp_count=naive_count,
        timezone_converted_count=converted_count,
        invalid_timestamp_count=invalid_timestamp_count,
        invalid_ohlc_count=invalid_ohlc_count,
        gap_count=len(gaps),
        missing_interval_count=sum(
            int(gap.get("missing_intervals", 0) or 0)
            for gap in gaps
        ),
        gaps=gaps[:20],
        audited_gap_count=len(audited_gaps),
        audited_missing_interval_count=sum(
            int(gap.get("missing_intervals", 0) or 0)
            for gap in audited_gaps
        ),
        out_of_scope_gap_count=len(out_of_scope_gaps),
        out_of_scope_gaps=out_of_scope_gaps[:20],
        expected_closure_count=len(expected_closures),
        expected_closed_interval_count=sum(
            int(gap.get("closed_intervals", 0) or 0)
            for gap in expected_closures
        ),
        expected_closures=expected_closures[:20],
        coverage_start_missing_intervals=coverage_start_missing,
        coverage_end_missing_intervals=coverage_end_missing,
        quality_scope_start=(
            quality_scope_start.isoformat() if quality_scope_start else None
        ),
        quality_scope_end=(
            quality_scope_end.isoformat() if quality_scope_end else None
        ),
        coverage_open_start=(
            deduplicated[0].time.isoformat() if deduplicated else None
        ),
        coverage_open_end=(
            deduplicated[-1].time.isoformat() if deduplicated else None
        ),
        coverage_close_end=(
            (deduplicated[-1].time + duration).isoformat()
            if deduplicated
            else None
        ),
        data_hash=data_hash,
    )

    if naive_count:
        issues.append(
            DataQualityIssue(
                code="TIMEZONE_ASSUMED_UTC",
                severity="WARNING",
                timeframe=timeframe,
                message=(
                    f"{naive_count} nến không có timezone; hệ thống tạm coi là UTC."
                ),
            )
        )
    if invalid_timestamp_count:
        issues.append(
            DataQualityIssue(
                code="INVALID_CANDLE_TIMESTAMP",
                severity="ERROR",
                timeframe=timeframe,
                message=(
                    f"Có {invalid_timestamp_count} nến có timestamp không hợp lệ."
                ),
            )
        )
    if duplicate_count:
        issues.append(
            DataQualityIssue(
                code="DUPLICATE_CANDLES_NORMALIZED",
                severity="WARNING",
                timeframe=timeframe,
                message=(
                    f"Đã loại {duplicate_count} nến trùng timestamp"
                    + (
                        f", gồm {conflicting_duplicate_count} bản ghi xung đột."
                        if conflicting_duplicate_count
                        else "."
                    )
                ),
            )
        )
    if invalid_ohlc_count:
        issues.append(
            DataQualityIssue(
                code="INVALID_OHLC",
                severity="ERROR",
                timeframe=timeframe,
                message=f"Có {invalid_ohlc_count} nến OHLC không hợp lệ.",
            )
        )
    if gaps:
        missing_count = sum(
            int(gap.get("missing_intervals", 0) or 0)
            for gap in gaps
        )
        first_missing = str(gaps[0].get("first_missing") or gaps[0].get("after") or "?")
        issues.append(
            DataQualityIssue(
                code=UNEXPECTED_DATA_GAP,
                severity="WARNING",
                timeframe=timeframe,
                message=(
                    f"Có {len(gaps)} khoảng trống trong phiên, tổng cộng "
                    f"{missing_count} nến thiếu. Thời điểm thiếu đầu tiên: "
                    f"{first_missing}."
                ),
            )
        )
    return deduplicated, manifest, issues


def _unexpected_gaps(
    candles: list[Candle],
    duration: timedelta,
    *,
    symbol: str = "",
    timeframe: str = "H1",
) -> list[dict[str, Any]]:
    gaps, _expected = _classify_gaps(
        candles,
        duration,
        timeframe=timeframe,
        session_calendar=trading_session_calendar(symbol),
    )
    return gaps


def _classify_gaps(
    candles: list[Candle],
    duration: timedelta,
    *,
    timeframe: str,
    session_calendar: TradingSessionCalendar,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    gaps: list[dict[str, Any]] = []
    expected_closures: list[dict[str, Any]] = []
    for previous, current in zip(candles, candles[1:]):
        expected = previous.time + duration
        if current.time <= expected:
            continue
        missing_cursor = expected
        unexpected_slots: list[str] = []
        expected_slots: list[str] = []
        classifications: dict[str, int] = {}
        while missing_cursor < current.time:
            classified = session_calendar.classify_missing_slot(
                missing_cursor,
                duration,
                timeframe=timeframe,
            )
            classifications[classified.classification] = (
                classifications.get(classified.classification, 0) + 1
            )
            target = unexpected_slots if classified.expected_candle else expected_slots
            target.append(missing_cursor.isoformat())
            missing_cursor += duration
        if unexpected_slots:
            gaps.append(
                {
                    "after": previous.time.isoformat(),
                    "before": current.time.isoformat(),
                    "missing_intervals": len(unexpected_slots),
                    "total_missing_intervals": len(unexpected_slots) + len(expected_slots),
                    "first_missing": unexpected_slots[0],
                    "last_missing": unexpected_slots[-1],
                    "missing_slots": unexpected_slots[:20],
                    "classifications": classifications,
                }
            )
        if expected_slots:
            expected_closures.append(
                {
                    "after": previous.time.isoformat(),
                    "before": current.time.isoformat(),
                    "closed_intervals": len(expected_slots),
                    "first_closed": expected_slots[0],
                    "last_closed": expected_slots[-1],
                    "closed_slots": expected_slots[:20],
                    "classifications": {
                        key: value
                        for key, value in classifications.items()
                        if key != UNEXPECTED_DATA_GAP
                    },
                }
            )
    return gaps, expected_closures


def _coverage_quality(
    candles: list[Candle],
    duration: timedelta,
    *,
    timeframe: str,
    session_calendar: TradingSessionCalendar,
    requested_start: datetime | None,
    requested_end: datetime | None,
) -> tuple[int, int, list[DataQualityIssue]]:
    if (
        not candles
        or requested_start is None
        or requested_end is None
        or requested_end <= requested_start
    ):
        return 0, 0, []

    first_open = candles[0].time
    last_close = candles[-1].time + duration
    start_slots = _expected_slots_between(
        requested_start,
        min(first_open, requested_end),
        duration,
        timeframe=timeframe,
        session_calendar=session_calendar,
    ) if first_open > requested_start else []
    end_slots = _expected_slots_between(
        max(last_close, requested_start),
        requested_end,
        duration,
        timeframe=timeframe,
        session_calendar=session_calendar,
    ) if last_close < requested_end else []

    issues: list[DataQualityIssue] = []
    if start_slots:
        issues.append(
            DataQualityIssue(
                code="DATA_COVERAGE_START_MISSING",
                severity="WARNING",
                timeframe=timeframe,
                message=(
                    f"Thiếu {len(start_slots)} nến ở đầu khoảng yêu cầu; "
                    f"bắt đầu từ {start_slots[0]}."
                ),
            )
        )
    if end_slots:
        issues.append(
            DataQualityIssue(
                code="DATA_COVERAGE_END_MISSING",
                severity="WARNING",
                timeframe=timeframe,
                message=(
                    f"Thiếu {len(end_slots)} nến ở cuối khoảng yêu cầu; "
                    f"bắt đầu từ {end_slots[0]}."
                ),
            )
        )
    return len(start_slots), len(end_slots), issues


def _expected_slots_between(
    start: datetime,
    end: datetime,
    duration: timedelta,
    *,
    timeframe: str,
    session_calendar: TradingSessionCalendar,
) -> list[str]:
    slots: list[str] = []
    cursor = start
    while cursor < end:
        classified = session_calendar.classify_missing_slot(
            cursor,
            duration,
            timeframe=timeframe,
        )
        if classified.expected_candle:
            slots.append(cursor.isoformat())
        cursor += duration
    return slots


def _quality_scope_start(
    timeframe: str,
    requested_start: datetime | None,
) -> datetime | None:
    if requested_start is None:
        return None
    days = QUALITY_LOOKBACK_DAYS.get(str(timeframe or "").upper(), 30)
    return requested_start - timedelta(days=days)


def _gap_overlaps_scope(
    gap: dict[str, Any],
    duration: timedelta,
    scope_start: datetime | None,
    scope_end: datetime | None,
) -> bool:
    if scope_start is None and scope_end is None:
        return True
    try:
        gap_start = normalize_utc(
            datetime.fromisoformat(str(gap["first_missing"]))
        )[0]
        gap_end = normalize_utc(
            datetime.fromisoformat(str(gap["last_missing"]))
        )[0] + duration
    except (KeyError, TypeError, ValueError):
        return True
    if scope_start is not None and gap_end <= scope_start:
        return False
    if scope_end is not None and gap_start >= scope_end:
        return False
    return True


def _valid_ohlc(candle: Candle) -> bool:
    values = (
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
    )
    if not all(_is_finite_number(value) for value in values):
        return False
    if candle.high < candle.low:
        return False
    if candle.high < max(candle.open, candle.close):
        return False
    if candle.low > min(candle.open, candle.close):
        return False
    return candle.volume >= 0


def _is_finite_number(value: float) -> bool:
    return value == value and value not in {float("inf"), float("-inf")}


def _candle_value_key(candle: Candle) -> tuple[float, ...]:
    return (
        candle.open,
        candle.high,
        candle.low,
        candle.close,
        candle.volume,
    )


def _serialized_candle(candle: Candle) -> dict[str, Any]:
    return {
        "time": candle.time.isoformat(),
        "open": format(candle.open, ".17g"),
        "high": format(candle.high, ".17g"),
        "low": format(candle.low, ".17g"),
        "close": format(candle.close, ".17g"),
        "volume": format(candle.volume, ".17g"),
    }


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
