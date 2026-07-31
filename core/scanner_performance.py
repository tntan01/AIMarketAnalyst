"""Fail-safe, bounded performance telemetry for scanner runs."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock, get_ident
from time import perf_counter
from typing import Any, Iterator

from core.scanner_observability import redact_sensitive


SCAN_PERFORMANCE_SCHEMA_VERSION = "scanner-performance-v1"

PHASE_NAMES = (
    "settings",
    "readiness",
    "account_portfolio",
    "correlation",
    "macro_global_fetch",
    "macro_pair_build",
    "available_symbols",
    "mt5_fetch",
    "analysis_wall",
    "candidate_filter",
    "observability",
    "market_brief",
    "telegram",
    "persistence",
    "retention",
)

COUNTER_NAMES = (
    "mt5_copy_rates_calls",
    "mt5_full_history_calls",
    "mt5_tail_calls",
    "macro_context_cache_hits",
    "macro_context_cache_misses",
    "macro_global_fetches",
    "yfinance_download_calls",
    "ai_stance_calls",
    "telegram_candidates",
    "telegram_canonical_candidates",
    "telegram_legacy_fallback_candidates",
    "telegram_skipped_non_candidates",
    "telegram_requests",
    "telegram_errors",
    "analysis_documents_written",
)

_SYMBOL_TIMING_FIELDS = ("fetch_ms", "macro_lookup_ms", "mt5_ms", "analysis_ms")


def safe_performance_call(
    tracker: object | None,
    method: str,
    *args: object,
    **kwargs: object,
) -> object | None:
    """Invoke one telemetry method without allowing failures to escape."""

    try:
        callback = getattr(tracker, method, None)
        return callback(*args, **kwargs) if callable(callback) else None
    except Exception:
        return None


@contextmanager
def safe_performance_phase(
    tracker: object | None,
    name: str,
) -> Iterator[None]:
    safe_performance_call(tracker, "start_phase", name)
    try:
        yield
    finally:
        safe_performance_call(tracker, "end_phase", name)


class ScanPerformanceTracker:
    """Thread-safe tracker exposing both raw and critical-path phase timing.

    ``phases`` contains the actual elapsed duration of each phase, even when
    phases overlap. ``exclusive_phases`` attributes each overlapping wall-clock
    slice once, so its sum is bounded by ``total_ms``. Consumers must use raw
    values for service latency and exclusive values for scan-budget accounting.
    """

    def __init__(
        self,
        *,
        scan_id: str = "",
        symbol_count: int = 0,
        clock=perf_counter,
        now=None,
    ) -> None:
        self._clock = clock
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._lock = RLock()
        self._started_clock = self._read_clock()
        self._started_at = self._timestamp()
        self._scan_id = str(scan_id or "")
        self._symbol_count = max(0, int(symbol_count or 0))
        self._phase_started: dict[tuple[int, str], float] = {}
        self._phase_intervals: list[tuple[str, float, float]] = []
        self._counters = {name: 0 for name in COUNTER_NAMES}
        self._symbols: dict[str, dict[str, Any]] = {}
        self._core_ready_clock: float | None = None
        self._core_ready_at = ""
        self._completed_clock: float | None = None
        self._completed_at = ""
        self._finalized: dict[str, Any] | None = None

    def set_scan_id(self, scan_id: object) -> None:
        with self._lock:
            if self._finalized is None:
                self._scan_id = str(scan_id or "")

    def start_phase(self, name: str) -> None:
        normalized = self._phase_name(name)
        key = (get_ident(), normalized)
        with self._lock:
            if self._finalized is None:
                self._phase_started.setdefault(key, self._read_clock())

    def end_phase(self, name: str) -> None:
        normalized = self._phase_name(name)
        key = (get_ident(), normalized)
        with self._lock:
            if self._finalized is not None:
                return
            started = self._phase_started.pop(key, None)
            if started is None:
                return
            ended = max(started, self._read_clock())
            self._phase_intervals.append((normalized, started, ended))

    @contextmanager
    def phase(self, name: str) -> Iterator[None]:
        self.start_phase(name)
        try:
            yield
        finally:
            self.end_phase(name)

    def increment(self, name: str, amount: int = 1) -> None:
        normalized = str(name or "").strip()
        try:
            delta = int(amount)
        except (TypeError, ValueError):
            return
        with self._lock:
            if self._finalized is None:
                self._counters[normalized] = (
                    self._counters.get(normalized, 0) + delta
                )

    def record_symbol(
        self,
        symbol: object,
        *,
        pipeline_route: object | None = None,
        **timings: object,
    ) -> None:
        key = str(symbol or "")[:64]
        if not key:
            return
        with self._lock:
            if self._finalized is not None:
                return
            record = self._symbols.setdefault(
                key, {field: 0.0 for field in _SYMBOL_TIMING_FIELDS}
            )
            for field in _SYMBOL_TIMING_FIELDS:
                if field not in timings:
                    continue
                try:
                    record[field] = round(
                        max(0.0, float(timings[field])),
                        3,
                    )
                except (TypeError, ValueError):
                    continue
            if pipeline_route is not None:
                record["pipeline_route"] = str(pipeline_route)[:96]

    def mark_core_ready(self) -> None:
        with self._lock:
            if self._core_ready_clock is None:
                self._core_ready_clock = self._read_clock()
                self._core_ready_at = self._timestamp()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._build_summary(
                completed_clock=self._read_clock(),
                finalized=False,
            )

    def finalize(self) -> dict[str, Any]:
        with self._lock:
            if self._finalized is not None:
                return dict(self._finalized)
            completed_clock = self._read_clock()
            for (_thread_id, name), started in tuple(
                self._phase_started.items()
            ):
                self._phase_intervals.append(
                    (name, started, max(started, completed_clock))
                )
            self._phase_started.clear()
            self._completed_clock = completed_clock
            self._completed_at = self._timestamp()
            self._finalized = self._build_summary(
                completed_clock=completed_clock,
                finalized=True,
            )
            return dict(self._finalized)

    def _build_summary(
        self,
        *,
        completed_clock: float,
        finalized: bool,
    ) -> dict[str, Any]:
        intervals = list(self._phase_intervals)
        intervals.extend(
            (
                name,
                started,
                max(started, completed_clock),
            )
            for (_thread_id, name), started in self._phase_started.items()
        )
        raw_phases = self._raw_phase_totals(intervals)
        exclusive_phases = self._exclusive_phase_totals(intervals)
        total_ms = round(
            max(0.0, completed_clock - self._started_clock) * 1_000,
            3,
        )
        core_ready_ms = (
            round(
                max(0.0, self._core_ready_clock - self._started_clock)
                * 1_000,
                3,
            )
            if self._core_ready_clock is not None
            else None
        )
        return redact_sensitive(
            {
                "schema_version": SCAN_PERFORMANCE_SCHEMA_VERSION,
                "phase_accounting": {
                    "phases": "raw_elapsed",
                    "exclusive_phases": "exclusive_wall_time",
                    "exclusive_total_ms": round(
                        sum(exclusive_phases.values()),
                        3,
                    ),
                },
                "scan_id": self._scan_id,
                "symbol_count": self._symbol_count,
                "started_at": self._started_at,
                "completed_at": self._completed_at if finalized else "",
                "core_ready_at": self._core_ready_at,
                "total_ms": total_ms,
                "core_ready_ms": core_ready_ms,
                "aftercare_ms": (
                    round(max(0.0, total_ms - core_ready_ms), 3)
                    if core_ready_ms is not None
                    else None
                ),
                "phases": {
                    f"{name}_ms": round(max(0.0, raw_phases[name]), 3)
                    for name in PHASE_NAMES
                },
                "exclusive_phases": {
                    f"{name}_ms": round(
                        max(0.0, exclusive_phases[name]),
                        3,
                    )
                    for name in PHASE_NAMES
                },
                "counters": dict(self._counters),
                "symbols": {
                    symbol: dict(values)
                    for symbol, values in self._symbols.items()
                },
            }
        )

    @staticmethod
    def _raw_phase_totals(
        intervals: list[tuple[str, float, float]],
    ) -> dict[str, float]:
        totals = {name: 0.0 for name in PHASE_NAMES}
        for name, start, end in intervals:
            if name in totals and end >= start:
                totals[name] += (end - start) * 1_000
        return totals

    @staticmethod
    def _exclusive_phase_totals(
        intervals: list[tuple[str, float, float]],
    ) -> dict[str, float]:
        totals = {name: 0.0 for name in PHASE_NAMES}
        valid = [
            (name, start, end)
            for name, start, end in intervals
            if name in totals and end >= start
        ]
        boundaries = sorted(
            {point for _name, start, end in valid for point in (start, end)}
        )
        for left, right in zip(boundaries, boundaries[1:]):
            if right <= left:
                continue
            midpoint = left + (right - left) / 2
            active = {
                name
                for name, start, end in valid
                if start <= midpoint < end
            }
            if not active:
                continue
            share_ms = (right - left) * 1_000 / len(active)
            for name in active:
                totals[name] += share_ms
        return totals

    @staticmethod
    def _phase_name(name: object) -> str:
        return str(name or "").strip().lower() or "unknown"

    def _read_clock(self) -> float:
        try:
            return float(self._clock())
        except Exception:
            return 0.0

    def _timestamp(self) -> str:
        try:
            value = self._now()
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat(
                timespec="milliseconds"
            )
        except Exception:
            return ""
