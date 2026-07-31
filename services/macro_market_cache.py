"""Shared single-flight cache for Yahoo Finance macro market data downloads.

Used by both fetch_macro_correlation_context() (market_data_service) and
NewsService._download_macro_source() (news_service) to avoid duplicate
yfinance downloads when these two tasks run concurrently in a scanner flow.

Single-flight guarantees (per canonical key = ticker/period/interval):

- Concurrent refreshes for the same key perform exactly ONE downloader
  attempt. Every waiter that races with that flight — including one that
  starts after the owner recorded the outcome but before the owner released
  the per-key lock — shares the same stale/unavailable/fresh outcome.
- Empty/invalid frames are treated as failed attempts: they flow through
  stale-if-error exactly like downloader exceptions and are never cached
  as fresh data.
- After a failed/empty refresh, a retry gate (``next_retry_at``) makes every
  consumer reuse the stale/unavailable outcome WITHOUT invoking the downloader
  until the gate reopens. Retry metadata is stored separately from the cached
  data entry, so a failed attempt never extends or refreshes the data's expiry.
- ``force_refresh`` bypasses TTL and the retry gate, so a SEQUENTIAL force
  refresh always performs a new download — even with the same ``checked_at``.
  Only force refreshes that are genuinely concurrent share a flight.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import Event, RLock
from typing import Any, Callable

import yfinance as yf

UTC = timezone.utc
_DEFAULT_TTL = timedelta(minutes=5)
_DEFAULT_STALE_IF_ERROR = timedelta(minutes=30)
_DEFAULT_RETRY_TTL = timedelta(minutes=5)


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class _FrameEntry:
    data: Any  # raw yf DataFrame
    fetched_at: datetime
    expires_at: datetime
    refresh_error_type: str = ""


@dataclass(frozen=True)
class _FetchOutcome:
    """Immutable result/provenance for one caller-visible cache generation."""

    data: Any
    is_fresh: bool
    error_type: str
    exception: Exception | None
    checked_at: datetime
    data_fetched_at: datetime | None
    origin_expires_at: datetime | None
    next_retry_at: datetime | None


@dataclass
class _Flight:
    """One active single-flight generation shared by owner and waiters."""

    generation: int
    done: Event = field(default_factory=Event)
    outcome: _FetchOutcome | None = None
    waiters: int = 0


@dataclass
class _AttemptState:
    """Retry/attempt bookkeeping for one canonical key.

    Deliberately separate from ``_FrameEntry``: recording a failed attempt,
    the retry gate, or in-flight state must never move the cached data's
    expiry or pretend old data is fresh.
    """

    generation: int = 0  # advances once per flight START (acts as a flight token)
    attempts: int = 0  # every downloader call, including failed/empty
    successes: int = 0  # downloads that produced a usable frame
    last_attempt_at: datetime | None = None
    last_error_type: str = ""
    last_exception: Exception | None = None
    next_retry_at: datetime | None = None  # retry gate for failed/empty refreshes
    in_flight: bool = False
    active_flight: _Flight | None = None


def _default_download(ticker: str, *, period: str = "5d", interval: str = "1d") -> Any:
    return yf.download(ticker, period=period, interval=interval, progress=False)


def _make_cache_key(ticker: str, period: str, interval: str) -> tuple[str, str, str]:
    return (ticker, period, interval)


def _extract_frame_scalars(frame: Any) -> tuple[float, float | None]:
    """Extract the ``(value, previous)`` scalars any cached DataFrame must yield.

    Shared by BOTH publish-time validation (``_fetch``) and scalar conversion
    (``_frame_to_scalar``) so a published frame can always be converted
    downstream. Supports the two column layouts ``_frame_to_scalar`` accepted:
    regular columns via ``frame["Close"]`` and a MultiIndex via ``iloc``.

    Raises ``ValueError`` for empty/absent frames and for non-empty frames that
    cannot produce the scalars — missing ``Close`` column, non-numeric cells,
    malformed MultiIndex, etc. — so a malformed response routes through the
    exact same failure path as a downloader exception and never poisons the
    cache as a fresh success.
    """
    if frame is None or getattr(frame, "empty", True):
        raise ValueError("Empty or invalid DataFrame returned")
    import pandas as pd

    try:
        if isinstance(frame.columns, pd.MultiIndex):
            value = float(frame.iloc[-1, 0])
            previous = float(frame.iloc[-2, 0]) if len(frame) >= 2 else None
        else:
            value = float(frame["Close"].iloc[-1])
            previous = float(frame["Close"].iloc[-2]) if len(frame) >= 2 else None
        return value, previous
    except Exception as exc:
        raise ValueError(
            f"DataFrame is not scalarizable: {type(exc).__name__}: {exc}"
        ) from exc


class MacroMarketCache:
    """Thread-safe single-flight cache for yfinance macro downloads.

    Each cache key has its own lock so different tickers/periods download in
    parallel, but concurrent requests for the same key serialize (single-flight).
    """

    def __init__(
        self,
        *,
        ttl: timedelta | None = None,
        stale_if_error: timedelta | None = None,
        retry_ttl: timedelta | None = None,
        downloader: Callable[..., Any] | None = None,
    ) -> None:
        self._ttl = ttl or _DEFAULT_TTL
        self._stale_if_error = stale_if_error or _DEFAULT_STALE_IF_ERROR
        self._retry_ttl = retry_ttl or _DEFAULT_RETRY_TTL
        self._downloader = downloader or _default_download
        self._cache: dict[tuple[str, str, str], _FrameEntry] = {}
        self._cache_lock = RLock()
        self._key_locks: dict[tuple[str, str, str], RLock] = {}
        self._locks_lock = RLock()
        self._attempts: dict[tuple[str, str, str], _AttemptState] = {}
        self._attempts_lock = RLock()
        # Test hook: called by the flight owner AFTER recording the outcome but
        # BEFORE releasing the per-key lock, so tests can pin the late-waiter
        # interleaving. Never set in production.
        self._after_flight_hook: Callable[[], None] | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_frame(
        self,
        ticker: str,
        *,
        now: datetime | None = None,
        period: str = "5d",
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> Any:
        """Return cached/fresh/stale DataFrame. Uses stale-if-error internally.

        Returns a **copy** so consumer mutations cannot corrupt the cache.

        Only raises when no fresh data is available AND no stale data exists
        within the ``stale_if_error`` window.
        """
        outcome = self._fetch(
            ticker, period, interval,
            now=_ensure_utc(now),
            force_refresh=force_refresh,
        )
        if outcome.exception is not None:
            raise outcome.exception
        data = outcome.data
        # Defensive copy — the caller must not be able to mutate the cache.
        try:
            return data.copy()
        except AttributeError:
            return data

    def get_scalar(
        self,
        ticker: str,
        *,
        now: datetime | None = None,
        period: str = "5d",
        interval: str = "1d",
        force_refresh: bool = False,
    ) -> dict[str, object]:
        """Return {status, value, previous, ...} dict with full provenance.

        Status values:
        - ``"fresh"`` — TTL-valid download
        - ``"stale"`` — served from stale-if-error after download failure
        - ``"unavailable"`` — no data at all (empty frame or total failure)

        Provenance keys included in every result:
        - ``cache_key``, ``checked_at_utc``, ``data_fetched_at_utc``
        - ``origin_expires_at_utc``, ``next_retry_at_utc``
        - ``refresh_error_type`` (empty on a healthy result)
        - legacy aliases ``fetched_at_utc`` and ``expires_at_utc``
        """
        requested_at = _ensure_utc(now)
        cache_key = _make_cache_key(ticker, period, interval)
        outcome = self._fetch(
            ticker, period, interval,
            now=requested_at,
            force_refresh=force_refresh,
        )
        if outcome.exception is not None:
            result = {
                "status": "unavailable",
                "value": None,
                "previous": None,
                "error_type": outcome.error_type or type(outcome.exception).__name__,
            }
        else:
            result = self._frame_to_scalar(
                outcome.data,
                "fresh" if outcome.is_fresh else "stale",
            )

        # Use the immutable per-flight outcome. Rereading mutable cache state
        # here could mix this value/status with a later force generation.
        data_fetched = (
            outcome.data_fetched_at.isoformat() if outcome.data_fetched_at else ""
        )
        origin_expires = (
            outcome.origin_expires_at.isoformat() if outcome.origin_expires_at else ""
        )
        next_retry = outcome.next_retry_at.isoformat() if outcome.next_retry_at else ""
        result["cache_key"] = list(cache_key)
        result["checked_at_utc"] = outcome.checked_at.isoformat()
        result["data_fetched_at_utc"] = data_fetched
        result["origin_expires_at_utc"] = origin_expires
        result["next_retry_at_utc"] = next_retry
        result["refresh_error_type"] = str(
            outcome.error_type or result.get("error_type", "") or ""
        )
        # Backward-compatible aliases used by older Phase 2 consumers/tests.
        result["fetched_at_utc"] = data_fetched
        result["expires_at_utc"] = origin_expires
        return result

    def attempt_counts(self) -> dict[str, int]:
        """Downloader attempts per canonical key, INCLUDING failed/empty calls."""
        with self._attempts_lock:
            return {"/".join(k): s.attempts for k, s in self._attempts.items()}

    def success_counts(self) -> dict[str, int]:
        """Successful downloads (usable frame cached) per canonical key."""
        with self._attempts_lock:
            return {"/".join(k): s.successes for k, s in self._attempts.items()}

    def call_counts(self) -> dict[str, int]:
        """Backward-compatible alias for :meth:`success_counts`."""
        return self.success_counts()

    def raw_call_counts(self) -> dict[tuple[str, str, str], int]:
        """Return successful download counts per raw cache key."""
        with self._attempts_lock:
            return {k: s.successes for k, s in self._attempts.items()}

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------
    def _fetch(
        self,
        ticker: str,
        period: str,
        interval: str,
        now: datetime,
        force_refresh: bool = False,
    ) -> _FetchOutcome:
        """Return one immutable single-flight outcome for a canonical key.

        Ownership is claimed atomically before the owner waits for the per-key
        lock. Callers that encounter an active flight wait without holding any
        cache/state/key lock and reuse that flight's exact outcome.
        """
        cache_key = _make_cache_key(ticker, period, interval)
        checked_at = _ensure_utc(now)

        if not force_refresh:
            with self._cache_lock:
                entry = self._cache.get(cache_key)
            cached_outcome = self._cached_entry_outcome(
                cache_key,
                entry,
                checked_at,
            )
            if cached_outcome is not None:
                return cached_outcome

        # Claim/join is atomic and happens before the key lock. This closes the
        # force-refresh race where two callers were already queued behind it.
        with self._attempts_lock:
            state = self._attempts.setdefault(cache_key, _AttemptState())
            flight = state.active_flight
            if flight is None:
                state.generation += 1
                flight = _Flight(generation=state.generation)
                state.active_flight = flight
                state.in_flight = True
                is_owner = True
            else:
                flight.waiters += 1
                is_owner = False

        if not is_owner:
            flight.done.wait()
            if flight.outcome is None:  # pragma: no cover - invariant guard
                raise RuntimeError(f"Macro cache flight ended without outcome: {cache_key!r}")
            return flight.outcome

        key_lock = self._get_key_lock(cache_key)
        outcome: _FetchOutcome | None = None
        try:
            key_lock.acquire()
            try:
                if not force_refresh:
                    with self._cache_lock:
                        entry = self._cache.get(cache_key)
                    outcome = self._cached_entry_outcome(
                        cache_key,
                        entry,
                        checked_at,
                    )

                if outcome is None and not force_refresh:
                    # The retry gate delays attempts only. It never changes the
                    # origin timestamps or extends the hard stale deadline.
                    with self._attempts_lock:
                        next_retry_at = state.next_retry_at
                        pending_error = state.last_exception
                        pending_error_type = state.last_error_type
                    if (
                        pending_error is not None
                        and next_retry_at is not None
                        and checked_at < next_retry_at
                    ):
                        with self._cache_lock:
                            entry = self._cache.get(cache_key)
                        if self._can_serve_stale(entry, checked_at):
                            outcome = self._outcome_from_entry(
                                cache_key,
                                entry,
                                checked_at=checked_at,
                                is_fresh=False,
                                error_type=pending_error_type,
                                next_retry_at=next_retry_at,
                            )
                        else:
                            outcome = self._outcome_from_entry(
                                cache_key,
                                entry,
                                checked_at=checked_at,
                                is_fresh=False,
                                error_type=pending_error_type,
                                exception=pending_error,
                                next_retry_at=next_retry_at,
                                include_data=False,
                            )

                if outcome is None:
                    with self._attempts_lock:
                        state.attempts += 1

                    failure: Exception | None = None
                    data: Any = None
                    try:
                        data = self._downloader(
                            ticker,
                            period=period,
                            interval=interval,
                        )
                    except Exception as exc:
                        failure = exc
                    if failure is None:
                        # Publish only frames the downstream scalar extraction
                        # can use safely (regular Close columns OR MultiIndex).
                        # Empty/None and non-scalarizable frames share the exact
                        # failure path as downloader exceptions below.
                        try:
                            _extract_frame_scalars(data)
                        except Exception as exc:
                            failure = exc

                    if failure is not None:
                        error_type = type(failure).__name__
                        next_retry_at = checked_at + self._retry_ttl
                        with self._attempts_lock:
                            state.last_attempt_at = checked_at
                            state.last_error_type = error_type
                            state.last_exception = failure
                            state.next_retry_at = next_retry_at
                        with self._cache_lock:
                            entry = self._cache.get(cache_key)
                            can_serve_stale = self._can_serve_stale(entry, checked_at)
                            if can_serve_stale:
                                # Error metadata changes; origin data expiry does not.
                                entry.refresh_error_type = error_type
                        if can_serve_stale:
                            outcome = self._outcome_from_entry(
                                cache_key,
                                entry,
                                checked_at=checked_at,
                                is_fresh=False,
                                error_type=error_type,
                                next_retry_at=next_retry_at,
                            )
                        else:
                            outcome = self._outcome_from_entry(
                                cache_key,
                                entry,
                                checked_at=checked_at,
                                is_fresh=False,
                                error_type=error_type,
                                exception=failure,
                                next_retry_at=next_retry_at,
                                include_data=False,
                            )
                    else:
                        entry = _FrameEntry(
                            data=data,
                            fetched_at=checked_at,
                            expires_at=checked_at + self._ttl,
                        )
                        with self._cache_lock:
                            self._cache[cache_key] = entry
                        with self._attempts_lock:
                            state.last_attempt_at = checked_at
                            state.last_error_type = ""
                            state.last_exception = None
                            state.next_retry_at = None
                            state.successes += 1
                        outcome = self._outcome_from_entry(
                            cache_key,
                            entry,
                            checked_at=checked_at,
                            is_fresh=True,
                            next_retry_at=None,
                        )

                if self._after_flight_hook is not None:
                    self._after_flight_hook()
            finally:
                key_lock.release()
        except Exception as exc:
            # A hook/internal failure must not strand any flight waiter.
            with self._cache_lock:
                entry = self._cache.get(cache_key)
            outcome = self._outcome_from_entry(
                cache_key,
                entry,
                checked_at=checked_at,
                is_fresh=False,
                error_type=type(exc).__name__,
                exception=exc,
                include_data=False,
            )
        finally:
            with self._attempts_lock:
                flight.outcome = outcome
                # Publish after key-lock release, then atomically retire flight.
                flight.done.set()
                if state.active_flight is flight:
                    state.active_flight = None
                    state.in_flight = False

        if outcome is None:  # pragma: no cover - defensive invariant
            raise RuntimeError(f"Macro cache owner produced no outcome: {cache_key!r}")
        return outcome

    def _cached_entry_outcome(
        self,
        cache_key: tuple[str, str, str],
        entry: _FrameEntry | None,
        checked_at: datetime,
    ) -> _FetchOutcome | None:
        """Resolve a non-force cache read without reviving a failed refresh.

        A force failure can happen while the origin TTL is still valid. Once
        that flight reports stale, normal readers must keep the same stale (or
        unavailable after its hard deadline) state until a successful retry;
        the old origin TTL cannot silently turn that outcome fresh again.
        """
        with self._attempts_lock:
            state = self._attempts.get(cache_key)
            pending_error = state.last_exception if state else None
            pending_error_type = state.last_error_type if state else ""
            next_retry_at = state.next_retry_at if state else None

        if pending_error is not None:
            if next_retry_at is None or checked_at >= next_retry_at:
                return None
            if self._can_serve_stale(entry, checked_at):
                return self._outcome_from_entry(
                    cache_key,
                    entry,
                    checked_at=checked_at,
                    is_fresh=False,
                    error_type=pending_error_type,
                    next_retry_at=next_retry_at,
                )
            return self._outcome_from_entry(
                cache_key,
                entry,
                checked_at=checked_at,
                is_fresh=False,
                error_type=pending_error_type,
                exception=pending_error,
                next_retry_at=next_retry_at,
                include_data=False,
            )

        if entry is not None and checked_at < entry.expires_at:
            return self._outcome_from_entry(
                cache_key,
                entry,
                checked_at=checked_at,
                is_fresh=True,
            )
        return None

    def _outcome_from_entry(
        self,
        _cache_key: tuple[str, str, str],
        entry: _FrameEntry | None,
        *,
        checked_at: datetime,
        is_fresh: bool,
        error_type: str = "",
        exception: Exception | None = None,
        next_retry_at: datetime | None = None,
        include_data: bool = True,
    ) -> _FetchOutcome:
        """Capture one result without later mutable cache/attempt rereads."""
        return _FetchOutcome(
            data=entry.data if entry is not None and include_data else None,
            is_fresh=is_fresh,
            error_type=error_type,
            exception=exception,
            checked_at=checked_at,
            data_fetched_at=entry.fetched_at if entry is not None else None,
            origin_expires_at=entry.expires_at if entry is not None else None,
            next_retry_at=next_retry_at,
        )

    def _can_serve_stale(
        self,
        entry: _FrameEntry | None,
        checked_at: datetime,
    ) -> bool:
        """Hard stale deadline is origin fetched_at + stale_if_error."""
        return bool(
            entry is not None
            and checked_at < entry.fetched_at + self._stale_if_error
        )

    @staticmethod
    def _frame_to_scalar(frame: Any, status: str) -> dict[str, object]:
        try:
            value, previous = _extract_frame_scalars(frame)
            return {"status": status, "value": value, "previous": previous}
        except Exception as exc:
            return {
                "status": "unavailable",
                "value": None,
                "previous": None,
                "error_type": type(exc).__name__,
            }

    def _get_key_lock(self, cache_key: tuple[str, str, str]) -> RLock:
        with self._locks_lock:
            lock = self._key_locks.get(cache_key)
            if lock is None:
                lock = RLock()
                self._key_locks[cache_key] = lock
            return lock


def _ensure_utc(dt: datetime | None) -> datetime:
    """Normalize a datetime to UTC-aware. Raises on naive input."""
    if dt is None:
        return _utcnow()
    if dt.tzinfo is None:
        raise TypeError(
            f"MacroMarketCache requires UTC-aware datetime, got naive: {dt!r}"
        )
    return dt


# ------------------------------------------------------------------
# Module-level singleton
# ------------------------------------------------------------------
_shared_cache: MacroMarketCache | None = None
_shared_cache_lock = RLock()


def get_shared_cache() -> MacroMarketCache:
    """Return the module-level singleton, creating it on first call."""
    global _shared_cache
    with _shared_cache_lock:
        if _shared_cache is None:
            _shared_cache = MacroMarketCache()
        return _shared_cache


def set_shared_cache(cache: MacroMarketCache) -> None:
    """Replace the singleton (for test injection)."""
    global _shared_cache
    with _shared_cache_lock:
        _shared_cache = cache


def reset_shared_cache() -> None:
    """Reset the singleton to None so next get_shared_cache() creates a fresh one."""
    global _shared_cache
    with _shared_cache_lock:
        _shared_cache = None
