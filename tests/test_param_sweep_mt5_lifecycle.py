from __future__ import annotations

from queue import SimpleQueue

import services.mt5_service as mt5_service_module
from workers.param_sweep_worker import _sweep_process_main


class _Provider:
    def __init__(self, *, fail_ready: bool = False) -> None:
        self.fail_ready = fail_ready
        self.ensure_calls = 0
        self.disconnect_calls = 0

    def ensure_ready(self, *, require_login: bool = True) -> None:
        self.ensure_calls += 1
        assert require_login is True
        if self.fail_ready:
            raise RuntimeError("MT5 unavailable")

    def disconnect(self) -> None:
        self.disconnect_calls += 1


def test_sweep_process_uses_provider_lifecycle(monkeypatch, tmp_path) -> None:
    provider = _Provider()
    monkeypatch.setattr(mt5_service_module, "MT5Service", lambda: provider)
    messages: SimpleQueue = SimpleQueue()

    _sweep_process_main([], [], [], {}, {}, str(tmp_path / "checkpoint.json"), False, messages)

    assert provider.ensure_calls == 1
    assert provider.disconnect_calls == 1
    assert messages.get_nowait()[0] == "success"


def test_sweep_process_disconnects_after_readiness_failure(monkeypatch, tmp_path) -> None:
    provider = _Provider(fail_ready=True)
    monkeypatch.setattr(mt5_service_module, "MT5Service", lambda: provider)
    messages: SimpleQueue = SimpleQueue()

    _sweep_process_main([], [], [], {}, {}, str(tmp_path / "checkpoint.json"), False, messages)

    assert provider.ensure_calls == 1
    assert provider.disconnect_calls == 1
    assert messages.get_nowait()[0] == "error"
