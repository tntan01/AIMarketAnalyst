"""In-memory aftercare job registry with durable status markers.

The registry lets the application bound the shutdown wait: aftercare jobs
signal completion on a condition variable, and ``wait_for_aftercare`` returns
as soon as no job is in flight or the budget expires.  Durable jobs (those
with persistence enabled) also record every transition as an atomic marker
under ``<runtime_root>/scanner_jobs`` so an interrupted aftercare leaves an
explicit ``interrupted`` record instead of silently vanishing (mục 19.2 /
Phase 5).  Non-durable jobs are tracked in memory only.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from config.paths import app_data_dir
from services.scanner_persistence_service import atomic_json_save

JOB_SCHEMA_VERSION = 1
JOB_DIR_NAME = "scanner_jobs"

STATE_RUNNING = "running"
STATE_COMPLETED = "completed"
STATE_INTERRUPTED = "interrupted"

# A normal local marker write completes inside this grace period, preserving
# the useful synchronous fast path for callers that inspect the marker right
# after shutdown.  A stalled filesystem must not extend the bounded shutdown
# by the duration of the stall; the daemon writer may finish later instead.
_INTERRUPTED_MARKER_GRACE_SECONDS = 0.01


class ScannerJobState:
    def __init__(self, *, runtime_root: Path | None = None) -> None:
        self._runtime_root = runtime_root
        self._condition = threading.Condition(threading.RLock())
        self._jobs: dict[str, str] = {}
        self._started_at: dict[str, str] = {}
        self._durable_jobs: set[str] = set()
        self._marker_locks: dict[str, threading.Lock] = {}

    def runtime_root(self) -> Path:
        return (self._runtime_root or app_data_dir()).resolve()

    def marker_path(self, scan_id: str) -> Path:
        return self.runtime_root() / JOB_DIR_NAME / f"{scan_id}.json"

    def load_marker(self, scan_id: str) -> dict[str, object] | None:
        path = self.marker_path(scan_id)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def begin_aftercare(self, scan_id: str, *, durable: bool = True) -> None:
        marker_lock: threading.Lock | None = None
        with self._condition:
            started_at = _utc_now_iso()
            self._jobs[scan_id] = STATE_RUNNING
            self._started_at[scan_id] = started_at
            if durable:
                self._durable_jobs.add(scan_id)
                # Claim the per-job marker lock before publishing the state to
                # another thread.  A concurrent interruption will therefore
                # be serialized after this initial ``running`` write without
                # keeping the condition held during filesystem I/O.
                marker_lock = threading.Lock()
                marker_lock.acquire()
                self._marker_locks[scan_id] = marker_lock
            self._condition.notify_all()

        if marker_lock is not None:
            try:
                self._write_marker_safe(
                    scan_id, STATE_RUNNING, started_at=started_at
                )
            finally:
                marker_lock.release()

    def complete_aftercare(self, scan_id: str) -> None:
        with self._condition:
            state = self._jobs.get(scan_id)
            if state is None:
                # Already interrupted: the disk marker must keep "interrupted"
                # even when the worker finishes late.
                return
            if state == STATE_INTERRUPTED:
                return
            durable = scan_id in self._durable_jobs
            started_at = self._started_at.get(scan_id)
            marker_lock = self._marker_locks.get(scan_id)
            self._discard_active_job(scan_id)
            self._condition.notify_all()

        # Marker persistence is best-effort and independent from the in-memory
        # liveness registry.  In particular, no filesystem I/O may happen while
        # the condition is held: a blocked disk must not stop shutdown from
        # observing that the worker has completed.
        if durable:
            try:
                self._write_marker_serialized(
                    marker_lock,
                    scan_id,
                    STATE_COMPLETED,
                    started_at=started_at,
                )
            finally:
                self._forget_marker_lock(scan_id, marker_lock)
        else:
            self._forget_marker_lock(scan_id, marker_lock)

    def mark_interrupted(
        self,
        scan_id: str,
        *,
        reason: str = "shutdown_timeout",
        defer_marker: bool = False,
    ) -> None:
        with self._condition:
            state = self._jobs.get(scan_id)
            if state is None or state != STATE_RUNNING:
                return
            durable = scan_id in self._durable_jobs
            started_at = self._started_at.get(scan_id)
            marker_lock = self._marker_locks.get(scan_id)
            self._discard_active_job(scan_id)
            self._condition.notify_all()

        finished = self._persist_interrupted_marker(
            scan_id,
            durable=durable,
            started_at=started_at,
            marker_lock=marker_lock,
            reason=reason,
            defer_marker=defer_marker,
        )
        if finished is not None:
            finished.wait(_INTERRUPTED_MARKER_GRACE_SECONDS)

    def wait_for_aftercare_shutdown(
        self,
        timeout: float,
        *,
        reason: str = "shutdown_timeout",
    ) -> bool:
        """Wait for workers, atomically claiming any jobs left at timeout.

        The timeout decision and interrupted transition share one condition
        critical section.  A worker completing immediately after the deadline
        therefore cannot win a second lock acquisition and replace the chosen
        interrupted terminal state with ``completed``.  Marker I/O remains
        outside the condition and is best-effort.
        """
        deadline = time.monotonic() + max(0.0, float(timeout))
        interrupted: list[
            tuple[str, bool, str | None, threading.Lock | None]
        ] = []
        with self._condition:
            while self._jobs and time.monotonic() < deadline:
                self._condition.wait(max(0.0, deadline - time.monotonic()))
            if not self._jobs:
                return True

            for scan_id in tuple(self._jobs):
                if self._jobs.get(scan_id) != STATE_RUNNING:
                    continue
                interrupted.append(
                    (
                        scan_id,
                        scan_id in self._durable_jobs,
                        self._started_at.get(scan_id),
                        self._marker_locks.get(scan_id),
                    )
                )
                self._discard_active_job(scan_id)
            self._condition.notify_all()

        # Start every best-effort marker writer before spending a single,
        # shared grace window.  Filesystem latency must not scale the bounded
        # shutdown path with the number of jobs that were claimed.
        finished_events: list[threading.Event] = []
        for scan_id, durable, started_at, marker_lock in interrupted:
            finished = self._persist_interrupted_marker(
                scan_id,
                durable=durable,
                started_at=started_at,
                marker_lock=marker_lock,
                reason=reason,
                defer_marker=True,
            )
            if finished is not None:
                finished_events.append(finished)

        grace_deadline = time.monotonic() + _INTERRUPTED_MARKER_GRACE_SECONDS
        for finished in finished_events:
            finished.wait(max(0.0, grace_deadline - time.monotonic()))
        return False

    def _persist_interrupted_marker(
        self,
        scan_id: str,
        *,
        durable: bool,
        started_at: str | None,
        marker_lock: threading.Lock | None,
        reason: str,
        defer_marker: bool,
    ) -> threading.Event | None:
        if not durable:
            self._forget_marker_lock(scan_id, marker_lock)
            return None

        if not defer_marker:
            try:
                self._write_marker_serialized(
                    marker_lock,
                    scan_id,
                    STATE_INTERRUPTED,
                    started_at=started_at,
                    reason=reason,
                )
            finally:
                self._forget_marker_lock(scan_id, marker_lock)
            return None

        # The wait budget has already expired when this is called from app
        # shutdown. Persist the interruption outside both the condition and
        # the caller's critical path. A failed or stalled write deliberately
        # leaves the prior ``running`` marker as the durable incomplete signal.
        finished = threading.Event()

        def persist_interrupted_marker() -> None:
            try:
                self._write_marker_serialized(
                    marker_lock,
                    scan_id,
                    STATE_INTERRUPTED,
                    started_at=started_at,
                    reason=reason,
                )
            finally:
                self._forget_marker_lock(scan_id, marker_lock)
                finished.set()

        writer = threading.Thread(
            target=persist_interrupted_marker,
            name=f"scanner-marker-{scan_id}",
            daemon=True,
        )
        writer.start()
        return finished

    def _discard_active_job(self, scan_id: str) -> None:
        self._jobs.pop(scan_id, None)
        self._started_at.pop(scan_id, None)
        self._durable_jobs.discard(scan_id)

    def _forget_marker_lock(
        self,
        scan_id: str,
        marker_lock: threading.Lock | None,
    ) -> None:
        if marker_lock is None:
            return
        with self._condition:
            if (
                scan_id not in self._jobs
                and self._marker_locks.get(scan_id) is marker_lock
            ):
                self._marker_locks.pop(scan_id, None)

    def active_jobs(self) -> tuple[str, ...]:
        with self._condition:
            return tuple(
                scan_id
                for scan_id, state in self._jobs.items()
                if state == STATE_RUNNING
            )

    def wait_for_aftercare(self, timeout: float) -> bool:
        """Block at most ``timeout`` seconds for every in-flight job.

        Returns True when no job is still running; False when the budget
        expired.  Interrupted jobs have already left the waiting set, so a
        later call returns True immediately.
        """
        deadline = time.monotonic() + max(0.0, float(timeout))
        with self._condition:
            while self._jobs and time.monotonic() < deadline:
                self._condition.wait(max(0.0, deadline - time.monotonic()))
            return not self._jobs

    def _write_marker_safe(
        self,
        scan_id: str,
        state: str,
        *,
        started_at: str | None = None,
        reason: str | None = None,
    ) -> bool:
        """Persist a marker without leaking write failures.

        The marker is best-effort: an OSError (disk full/permission) must never
        escape the job-state layer and break an app shutdown.  Returns False
        when the marker could not be written; callers still update in-memory
        liveness while the previous durable marker remains the incomplete-job
        signal.
        """
        try:
            self._write_marker(
                scan_id, state, started_at=started_at, reason=reason
            )
        except OSError:
            return False
        return True

    def _write_marker_serialized(
        self,
        marker_lock: threading.Lock | None,
        scan_id: str,
        state: str,
        *,
        started_at: str | None = None,
        reason: str | None = None,
    ) -> bool:
        if marker_lock is None:
            return self._write_marker_safe(
                scan_id,
                state,
                started_at=started_at,
                reason=reason,
            )
        with marker_lock:
            return self._write_marker_safe(
                scan_id,
                state,
                started_at=started_at,
                reason=reason,
            )

    def _write_marker(
        self,
        scan_id: str,
        state: str,
        *,
        started_at: str | None = None,
        reason: str | None = None,
    ) -> None:
        marker = {
            "schema_version": JOB_SCHEMA_VERSION,
            "scan_id": scan_id,
            "state": state,
            "started_at": started_at or self._started_at.get(scan_id) or _utc_now_iso(),
            "completed_at": _utc_now_iso() if state == STATE_COMPLETED else None,
            "reason": reason,
        }
        atomic_json_save(self.marker_path(scan_id), marker)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
