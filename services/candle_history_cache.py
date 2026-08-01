"""Thread-safe, in-memory rolling cache for MT5 candle histories.

This module deliberately has no MetaTrader dependency.  Callers own all SDK
operations and use the fallback reason returned here to decide when a full
history reload is required.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import RLock

from core.market_models import Candle


class CacheFallbackReason(str, Enum):
    """Why a caller must bypass the rolling path and load full history."""

    CACHE_MISSING = "cache_missing"
    IDENTITY_CHANGED = "identity_changed"
    CONFIGURATION_CHANGED = "configuration_changed"
    CACHE_CORRUPT = "cache_corrupt"
    FULL_HISTORY_INVALID = "full_history_invalid"
    TAIL_INVALID = "tail_invalid"
    TIMESTAMP_REGRESSION = "timestamp_regression"
    GAP_DETECTED = "gap_detected"


@dataclass(frozen=True, slots=True)
class CacheIdentity:
    """Complete identity of one broker candle series."""

    server: str
    account_fingerprint: str
    broker_symbol: str
    timeframe: str

    def __post_init__(self) -> None:
        normalized: dict[str, str] = {}
        for field_name in (
            "server",
            "account_fingerprint",
            "broker_symbol",
            "timeframe",
        ):
            value = getattr(self, field_name)
            if value is None or not str(value).strip():
                raise ValueError(f"Cache identity requires {field_name}.")
            normalized[field_name] = str(value).strip()
        normalized["timeframe"] = normalized["timeframe"].upper()
        for field_name, value in normalized.items():
            object.__setattr__(self, field_name, value)

    @property
    def connection_identity(self) -> tuple[str, str]:
        return self.server, self.account_fingerprint


@dataclass(frozen=True, slots=True)
class CandleCacheResult:
    """Result of a cache lookup or mutation.

    ``candles`` is always a new list.  When ``requires_full_reload`` is true,
    the list is only the last-known-good snapshot and must not be reported as a
    freshly updated history.
    """

    candles: list[Candle]
    fallback_reason: CacheFallbackReason | None = None
    replaced_count: int = 0
    appended_count: int = 0
    trimmed_count: int = 0

    @property
    def usable(self) -> bool:
        return self.fallback_reason is None

    @property
    def requires_full_reload(self) -> bool:
        return self.fallback_reason is not None


GapAllowance = Callable[[datetime, datetime, timedelta], bool]


@dataclass(frozen=True, slots=True)
class _CacheEntry:
    identity: CacheIdentity
    expected_interval: timedelta
    max_count: int
    candles: tuple[Candle, ...]


class _InvalidHistory(ValueError):
    pass


class CandleHistoryCache:
    """Pure-memory rolling candle cache with atomic lookup and merge steps."""

    def __init__(self) -> None:
        self._entries: dict[CacheIdentity, _CacheEntry] = {}
        self._active_connection: tuple[str, str] | None = None
        self._lock = RLock()

    def activate_connection(
        self,
        server: str,
        account_fingerprint: str,
    ) -> bool:
        """Activate one MT5 connection identity and clear entries on change.

        Returns ``True`` only when an already-active connection changed.  The
        first activation is not considered an identity change.
        """

        connection_identity = _connection_identity(
            server,
            account_fingerprint,
        )
        with self._lock:
            return self._activate_connection_locked(connection_identity)

    def lookup(
        self,
        identity: CacheIdentity,
        *,
        expected_interval: timedelta,
        max_count: int,
    ) -> CandleCacheResult:
        """Return an isolated snapshot or a reason to perform a full load."""

        _validate_policy(expected_interval, max_count)
        with self._lock:
            return self._lookup_locked(
                identity,
                expected_interval=expected_interval,
                max_count=max_count,
            )

    def store_full(
        self,
        identity: CacheIdentity,
        candles: Sequence[Candle],
        *,
        expected_interval: timedelta,
        max_count: int,
    ) -> CandleCacheResult:
        """Validate and atomically replace one entry with full history."""

        _validate_policy(expected_interval, max_count)
        with self._lock:
            self._activate_connection_locked(identity.connection_identity)
            previous = self._entries.get(identity)
            stale = list(previous.candles) if previous is not None else []
            try:
                normalized = _normalize_history(candles)
            except _InvalidHistory:
                return CandleCacheResult(
                    candles=stale,
                    fallback_reason=CacheFallbackReason.FULL_HISTORY_INVALID,
                )

            trimmed_count = max(0, len(normalized) - max_count)
            snapshot = normalized[-max_count:]
            self._entries[identity] = _CacheEntry(
                identity=identity,
                expected_interval=expected_interval,
                max_count=max_count,
                candles=tuple(snapshot),
            )
            return CandleCacheResult(
                candles=list(snapshot),
                appended_count=len(snapshot),
                trimmed_count=trimmed_count,
            )

    def merge_tail(
        self,
        identity: CacheIdentity,
        tail: Sequence[Candle],
        *,
        expected_interval: timedelta,
        max_count: int,
        gap_allowed: GapAllowance | None = None,
    ) -> CandleCacheResult:
        """Merge a fresh tail by UTC timestamp without mutating on fallback.

        Existing timestamps are replaced (including the forming bar), newer
        timestamps are appended, and an unexpected interval gap requests a
        full reload.  ``gap_allowed`` may exempt known market closures.
        """

        _validate_policy(expected_interval, max_count)
        with self._lock:
            lookup = self._lookup_locked(
                identity,
                expected_interval=expected_interval,
                max_count=max_count,
            )
            if lookup.requires_full_reload:
                return lookup

            cached = lookup.candles
            try:
                normalized_tail = _normalize_history(tail)
            except _InvalidHistory:
                return CandleCacheResult(
                    candles=list(cached),
                    fallback_reason=CacheFallbackReason.TAIL_INVALID,
                )

            cached_by_time = {candle.time: candle for candle in cached}
            cached_last = cached[-1].time
            tail_last = normalized_tail[-1].time
            if tail_last < cached_last or any(
                candle.time < cached_last
                and candle.time not in cached_by_time
                for candle in normalized_tail
            ):
                self._entries.pop(identity, None)
                return CandleCacheResult(
                    candles=list(cached),
                    fallback_reason=CacheFallbackReason.TIMESTAMP_REGRESSION,
                )

            replaced_count = 0
            appended: list[Candle] = []
            merged_by_time = dict(cached_by_time)
            for candle in normalized_tail:
                if candle.time in cached_by_time:
                    replaced_count += 1
                    merged_by_time[candle.time] = candle
                elif candle.time > cached_last:
                    appended.append(candle)
                    merged_by_time[candle.time] = candle
                else:  # Defensive guard for an unknown historical timestamp.
                    self._entries.pop(identity, None)
                    return CandleCacheResult(
                        candles=list(cached),
                        fallback_reason=(
                            CacheFallbackReason.TIMESTAMP_REGRESSION
                        ),
                    )

            previous_time = cached_last
            for candle in appended:
                if _has_unexpected_gap(
                    previous_time,
                    candle.time,
                    expected_interval,
                    gap_allowed,
                ):
                    return CandleCacheResult(
                        candles=list(cached),
                        fallback_reason=CacheFallbackReason.GAP_DETECTED,
                    )
                previous_time = candle.time

            merged = [
                merged_by_time[timestamp]
                for timestamp in sorted(merged_by_time)
            ]
            trimmed_count = max(0, len(merged) - max_count)
            snapshot = merged[-max_count:]
            self._entries[identity] = _CacheEntry(
                identity=identity,
                expected_interval=expected_interval,
                max_count=max_count,
                candles=tuple(snapshot),
            )
            return CandleCacheResult(
                candles=list(snapshot),
                replaced_count=replaced_count,
                appended_count=len(appended),
                trimmed_count=trimmed_count,
            )

    def invalidate(self, identity: CacheIdentity) -> bool:
        """Invalidate exactly one server/account/symbol/timeframe entry."""

        with self._lock:
            return self._entries.pop(identity, None) is not None

    def clear(self) -> int:
        """Clear every cached series and return the removed entry count."""

        with self._lock:
            removed = len(self._entries)
            self._entries.clear()
            self._active_connection = None
            return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    def _lookup_locked(
        self,
        identity: CacheIdentity,
        *,
        expected_interval: timedelta,
        max_count: int,
    ) -> CandleCacheResult:
        identity_changed = self._activate_connection_locked(
            identity.connection_identity
        )
        if identity_changed:
            return CandleCacheResult(
                candles=[],
                fallback_reason=CacheFallbackReason.IDENTITY_CHANGED,
            )

        entry = self._entries.get(identity)
        if entry is None:
            return CandleCacheResult(
                candles=[],
                fallback_reason=CacheFallbackReason.CACHE_MISSING,
            )
        if (
            entry.expected_interval != expected_interval
            or entry.max_count != max_count
        ):
            self._entries.pop(identity, None)
            return CandleCacheResult(
                candles=[],
                fallback_reason=CacheFallbackReason.CONFIGURATION_CHANGED,
            )

        try:
            candles = _validate_cached_entry(entry, identity)
        except _InvalidHistory:
            self._entries.pop(identity, None)
            return CandleCacheResult(
                candles=[],
                fallback_reason=CacheFallbackReason.CACHE_CORRUPT,
            )
        return CandleCacheResult(candles=list(candles))

    def _activate_connection_locked(
        self,
        connection_identity: tuple[str, str],
    ) -> bool:
        if self._active_connection is None:
            self._active_connection = connection_identity
            return False
        if self._active_connection == connection_identity:
            return False
        self._entries.clear()
        self._active_connection = connection_identity
        return True


def _connection_identity(
    server: str,
    account_fingerprint: str,
) -> tuple[str, str]:
    values: list[str] = []
    for name, value in (
        ("server", server),
        ("account_fingerprint", account_fingerprint),
    ):
        if value is None or not str(value).strip():
            raise ValueError(f"Cache identity requires {name}.")
        values.append(str(value).strip())
    return values[0], values[1]


def _validate_policy(
    expected_interval: timedelta,
    max_count: int,
) -> None:
    if not isinstance(expected_interval, timedelta):
        raise TypeError("expected_interval must be a timedelta.")
    if expected_interval <= timedelta(0):
        raise ValueError("expected_interval must be positive.")
    if isinstance(max_count, bool) or not isinstance(max_count, int):
        raise TypeError("max_count must be an integer.")
    if max_count <= 0:
        raise ValueError("max_count must be positive.")


def _normalize_history(candles: Sequence[Candle]) -> list[Candle]:
    if not candles:
        raise _InvalidHistory("Candle history is empty.")

    normalized: list[Candle] = []
    previous: datetime | None = None
    for candle in candles:
        if not isinstance(candle, Candle):
            raise _InvalidHistory("Candle history contains an invalid item.")
        timestamp = candle.time
        if (
            not isinstance(timestamp, datetime)
            or timestamp.tzinfo is None
            or timestamp.utcoffset() is None
        ):
            raise _InvalidHistory("Candle timestamps must be timezone-aware.")
        timestamp = timestamp.astimezone(timezone.utc)
        if previous is not None and timestamp <= previous:
            raise _InvalidHistory(
                "Candle timestamps must be strictly increasing."
            )
        # MT5Service already constructs UTC Candle instances.  Reuse those
        # immutable values on the hot path rather than cloning an entire
        # 500-bar history on every cache read.  Non-UTC aware input is still
        # normalized at the cold/full boundary.
        if candle.time.tzinfo is timezone.utc:
            normalized.append(candle)
        else:
            normalized.append(
                Candle(
                    time=timestamp,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
            )
        previous = timestamp
    return normalized


def _validate_cached_entry(
    entry: _CacheEntry,
    identity: CacheIdentity,
) -> tuple[Candle, ...]:
    if entry.identity != identity or not isinstance(entry.candles, tuple):
        raise _InvalidHistory("Cache entry identity or storage is corrupt.")
    if not entry.candles or len(entry.candles) > entry.max_count:
        raise _InvalidHistory("Cache entry has an invalid candle count.")

    # Entries are immutable tuples of frozen Candle values and are strictly
    # validated before each store.  A constant-time guard catches damaged
    # entries without making every warm scan re-validate and clone 44,800
    # candle objects.  Incoming tails/full reloads remain strictly validated.
    first = entry.candles[0]
    last = entry.candles[-1]
    if not isinstance(first, Candle) or not isinstance(last, Candle):
        raise _InvalidHistory("Cache entry contains an invalid candle.")
    if (
        first.time.tzinfo is not timezone.utc
        or last.time.tzinfo is not timezone.utc
        or first.time >= last.time and len(entry.candles) > 1
    ):
        raise _InvalidHistory("Cached timestamps are not normalized to UTC.")
    return entry.candles


def _has_unexpected_gap(
    previous: datetime,
    current: datetime,
    expected_interval: timedelta,
    gap_allowed: GapAllowance | None,
) -> bool:
    if current - previous <= expected_interval:
        return False
    if gap_allowed is not None and gap_allowed(
        previous,
        current,
        expected_interval,
    ):
        return False
    return True
