from __future__ import annotations

import sys

from workers.base_worker import WorkerState
from workers.scanner_worker import ScannerWorker


def test_scanner_worker_runs_task_without_mt5_sdk(monkeypatch):
    monkeypatch.delitem(sys.modules, "MetaTrader5", raising=False)
    events: list[tuple[str, object]] = []

    def task(**kwargs):
        events.append(("task_progress_callback_present", callable(kwargs.get("_progress_callback"))))
        return {"ok": True}

    worker = ScannerWorker(task, {})
    worker.succeeded.connect(lambda result: events.append(("succeeded", result)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert worker.state == WorkerState.FINISHED
    assert ("succeeded", {"ok": True}) in events
    assert not any(name == "failed" for name, _value in events)
    assert events[-1] == ("finished", None)


def test_scanner_worker_reports_task_connection_failure():
    events: list[tuple[str, object]] = []

    def task(**kwargs):
        assert callable(kwargs.get("_progress_callback"))
        raise RuntimeError("MT5 chưa sẵn sàng")

    worker = ScannerWorker(task, {})
    worker.succeeded.connect(lambda result: events.append(("succeeded", result)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert worker.state == WorkerState.FAILED
    assert any(name == "failed" and "MT5" in str(value) for name, value in events)
    assert not any(name == "succeeded" for name, _value in events)
    assert events[-1] == ("finished", None)


def test_scanner_worker_split_emits_core_before_aftercare():
    events: list[tuple[str, object]] = []

    def task(**kwargs):
        assert callable(kwargs.get("_core_ready_callback"))
        assert kwargs.get("_return_aftercare_delta") is True
        # Core result becomes visible before Telegram/persistence finish.
        kwargs["_core_ready_callback"]({"scan_id": "scan-1", "rows": []})
        events.append(("aftercare_ran", None))
        # Split mode returns only the aftercare delta, not the merged output.
        return {"scan_id": "scan-1", "telegram_alerts": {"sent": 1}}

    worker = ScannerWorker(task, {}, split_aftercare=True)
    worker.core_succeeded.connect(lambda r: events.append(("core_succeeded", r)))
    worker.aftercare_succeeded.connect(
        lambda r: events.append(("aftercare_succeeded", r))
    )
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert worker.state == WorkerState.FINISHED
    names = [name for name, _value in events]
    assert ("core_succeeded", {"scan_id": "scan-1", "rows": []}) in events
    assert names.index("core_succeeded") < names.index("aftercare_succeeded")
    assert ("aftercare_succeeded", {"scan_id": "scan-1", "telegram_alerts": {"sent": 1}}) in events
    assert not any(name == "failed" for name, _value in events)
    assert events[-1] == ("finished", None)


def test_scanner_worker_split_receives_aftercare_progress_callback():
    calls: list[tuple[int, str]] = []

    def task(**kwargs):
        apc = kwargs.get("_aftercare_progress_callback")
        assert callable(apc)
        apc(97, "Đang gửi...")
        return {}

    worker = ScannerWorker(task, {}, split_aftercare=True)
    worker.aftercare_progress.connect(lambda p, m: calls.append((p, m)))

    worker.run()

    assert calls == [(97, "Đang gửi...")]


def test_scanner_worker_split_failure_emits_failed_then_finished():
    events: list[tuple[str, object]] = []

    def task(**kwargs):
        raise RuntimeError("aftercare boom")

    worker = ScannerWorker(task, {}, split_aftercare=True)
    worker.core_succeeded.connect(lambda r: events.append(("core", r)))
    worker.aftercare_succeeded.connect(lambda r: events.append(("aftercare", r)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert worker.state == WorkerState.FAILED
    assert ("failed", "aftercare boom") in events
    assert not any(name in {"core", "aftercare"} for name, _value in events)
    assert events[-1] == ("finished", None)


def test_scanner_worker_legacy_mode_does_not_emit_core_signals():
    events: list[tuple[str, object]] = []

    def task(**kwargs):
        return {"ok": True}

    worker = ScannerWorker(task, {}, split_aftercare=False)
    worker.succeeded.connect(lambda r: events.append(("succeeded", r)))
    worker.core_succeeded.connect(lambda r: events.append(("core", r)))
    worker.aftercare_succeeded.connect(lambda r: events.append(("aftercare", r)))

    worker.run()

    assert ("succeeded", {"ok": True}) in events
    assert not any(name in {"core", "aftercare"} for name, _value in events)
