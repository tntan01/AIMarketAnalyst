from __future__ import annotations

import sys

from workers.backtest_worker import BacktestWorker
from workers.base_worker import WorkerState


class FakeMT5:
    def __init__(self, *, initialize_result: bool = True) -> None:
        self.initialize_result = initialize_result
        self.initialize_calls = 0
        self.shutdown_calls = 0

    def initialize(self) -> bool:
        self.initialize_calls += 1
        return self.initialize_result

    def shutdown(self) -> None:
        self.shutdown_calls += 1


def test_backtest_worker_shuts_down_mt5_after_success(monkeypatch):
    fake_mt5 = FakeMT5()
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
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
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 1
    assert ("succeeded", {"ok": True}) in events
    assert not any(name == "failed" for name, _value in events)
    assert events[-1] == ("finished", None)


def test_backtest_worker_fails_cleanly_when_mt5_initialize_fails(monkeypatch):
    fake_mt5 = FakeMT5(initialize_result=False)
    monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
    events: list[tuple[str, object]] = []

    def task(**_kwargs):
        raise AssertionError("task should not run when MT5 initialization fails")

    worker = BacktestWorker(task, {})
    worker.succeeded.connect(lambda result: events.append(("succeeded", result)))
    worker.failed.connect(lambda message: events.append(("failed", message)))
    worker.finished.connect(lambda: events.append(("finished", None)))

    worker.run()

    assert worker.state == WorkerState.FAILED
    assert fake_mt5.initialize_calls == 1
    assert fake_mt5.shutdown_calls == 0
    assert any(name == "failed" and "MT5" in str(value) for name, value in events)
    assert not any(name == "succeeded" for name, _value in events)
    assert events[-1] == ("finished", None)
