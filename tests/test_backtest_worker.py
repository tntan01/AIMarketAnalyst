from __future__ import annotations

import sys

from workers.backtest_worker import BacktestWorker
from workers.base_worker import WorkerState


def test_backtest_worker_runs_task_without_mt5_sdk(monkeypatch):
    monkeypatch.delitem(sys.modules, "MetaTrader5", raising=False)
    events: list[tuple[str, object]] = []

    def task(**kwargs):
        events.append(("task_progress_callback_present", callable(kwargs.get("_progress_callback"))))
        return {"ok": True}

    worker = BacktestWorker(task, {})
    worker.succeeded.connect(lambda result: events.append(("succeeded", result)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert worker.state == WorkerState.FINISHED
    assert ("succeeded", {"ok": True}) in events
    assert not any(name == "failed" for name, _value in events)
    assert events[-1] == ("finished", None)


def test_backtest_worker_reports_task_connection_failure():
    events: list[tuple[str, object]] = []

    def task(**kwargs):
        assert callable(kwargs.get("_progress_callback"))
        raise RuntimeError("MT5 chưa sẵn sàng")

    worker = BacktestWorker(task, {})
    worker.succeeded.connect(lambda result: events.append(("succeeded", result)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert worker.state == WorkerState.FAILED
    assert any(name == "failed" and "MT5" in str(value) for name, value in events)
    assert not any(name == "succeeded" for name, _value in events)
    assert events[-1] == ("finished", None)
