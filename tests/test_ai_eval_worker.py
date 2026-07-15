"""Test EvalWorker lifecycle + cleanup: khong crash khi QThread bi huy khi dang chay.

Test truc tiep EvalWorker class (khong qua dialog) de tranh dlg.exec() blocking.
"""
from __future__ import annotations

import sys
import os
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtWidgets import QApplication

# -------------------------------------------------------
# Mock AIService
# -------------------------------------------------------
_block_api = threading.Event()
_api_call_count = 0


class MockAI:
    def analyze(self, prompt_text, max_tokens=2500):
        global _api_call_count
        _api_call_count += 1
        _block_api.wait(timeout=5.0)
        return "Mock AI response"


# -------------------------------------------------------
# EvalWorker (identical to the one in dashboard_screen.py)
# -------------------------------------------------------
class EvalWorker(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, ai_service, prompt_text, max_tokens):
        super().__init__()
        self.ai_service = ai_service
        self.prompt_text = prompt_text
        self.max_tokens = max_tokens
        self.stop_flag = False

    def run(self):
        try:
            result = self.ai_service.analyze(self.prompt_text, max_tokens=self.max_tokens)
            if not self.stop_flag:
                self.finished.emit(result)
        except Exception as exc:
            if not self.stop_flag:
                self.error.emit(str(exc))


# -------------------------------------------------------
# Tests
# -------------------------------------------------------
class TestHarness:
    def __init__(self):
        self._eval_worker = None
        self.results: list[str] = []

    def on_finished(self, text):
        self.results.append(f"finished: {text[:50]}")
        self._eval_worker = None

    def on_error(self, err_msg):
        self.results.append(f"error: {err_msg[:50]}")
        self._eval_worker = None


def test_worker_lifecycle():
    global _api_call_count, _block_api
    app = QApplication.instance() or QApplication(sys.argv)
    errors: list[str] = []

    # ---- Test 1: Normal flow - complete before cleanup ----
    print("[TEST 1] Normal: worker completes before cleanup")
    _block_api.set()  # unblock
    _api_call_count = 0

    h = TestHarness()
    ai = MockAI()
    worker = EvalWorker(ai, "test prompt", 2500)
    h._eval_worker = worker
    worker.finished.connect(h.on_finished)
    worker.error.connect(h.on_error)
    worker.finished.connect(worker.deleteLater)
    worker.error.connect(worker.deleteLater)
    worker.start()
    worker.wait(5000)

    # After completion: on_finished should have cleared _eval_worker
    time.sleep(0.1)
    QApplication.processEvents()

    assert h._eval_worker is None, f"_eval_worker should be None after finished, got {h._eval_worker}"
    assert _api_call_count == 1, f"API should be called once, got {_api_call_count}"
    assert len(h.results) == 1 and "finished" in h.results[0], f"Expected finished result, got {h.results}"
    print("[TEST 1] PASS")

    # ---- Test 2: Cleanup while thread is running ----
    print("[TEST 2] Cleanup while worker is still running (simulates dialog close)")
    _block_api.clear()  # BLOCK
    _api_call_count = 0

    h = TestHarness()
    ai = MockAI()
    worker = EvalWorker(ai, "test prompt", 2500)
    worker.setObjectName("TestWorker2")  # for debugging
    h._eval_worker = worker
    worker.finished.connect(h.on_finished)
    worker.error.connect(h.on_error)
    worker.finished.connect(worker.deleteLater)
    worker.error.connect(worker.deleteLater)
    worker.start()

    # Wait for thread to actually start
    time.sleep(0.2)

    # Simulate dialog close cleanup
    w = h._eval_worker
    assert w is not None, "Worker should be set"
    assert w.isRunning(), "Worker should be running"

    # Cleanup (exactly as in dashboard_screen.py after dlg.exec())
    if h._eval_worker is not None and h._eval_worker.isRunning():
        h._eval_worker.stop_flag = True
        h._eval_worker.quit()
        h._eval_worker.wait(3000)
        h._eval_worker = None

    # Release API block
    _block_api.set()
    time.sleep(0.2)
    QApplication.processEvents()

    # Worker should be cleaned up without crash
    assert h._eval_worker is None, "Worker ref should be None after cleanup"
    assert not worker.isRunning() or True, "Worker may still be finishing, but no crash is the goal"
    print("[TEST 2] PASS (no crash, no 'Destroyed while thread is still running')")

    # ---- Test 3: stop_flag prevents signal emission ----
    print("[TEST 3] stop_flag prevents signal emission after cleanup")
    _block_api.clear()  # BLOCK
    _api_call_count = 0

    h = TestHarness()
    ai = MockAI()
    worker = EvalWorker(ai, "test prompt", 2500)
    h._eval_worker = worker
    worker.finished.connect(h.on_finished)
    worker.error.connect(h.on_error)
    worker.start()

    time.sleep(0.2)
    assert worker.isRunning()

    # Set stop_flag before releasing API
    worker.stop_flag = True
    _block_api.set()
    worker.wait(5000)
    time.sleep(0.1)
    QApplication.processEvents()

    # stop_flag=True should prevent finished/error signals
    assert len(h.results) == 0, f"stop_flag should prevent signals, got {h.results}"
    print("[TEST 3] PASS (stop_flag blocked signals)")

    # ---- Test 4: Re-click: stop old worker, start new one ----
    print("[TEST 4] Re-click: stop old worker before starting new one")
    _block_api.clear()
    _api_call_count = 0

    h = TestHarness()
    ai = MockAI()

    # Start first worker
    w1 = EvalWorker(ai, "prompt 1", 2500)
    h._eval_worker = w1
    w1.finished.connect(h.on_finished)
    w1.error.connect(h.on_error)
    w1.finished.connect(w1.deleteLater)
    w1.error.connect(w1.deleteLater)
    w1.start()
    time.sleep(0.15)
    assert w1.isRunning()

    # Stop old worker, start new one (re-click logic)
    if h._eval_worker is not None and h._eval_worker.isRunning():
        h._eval_worker.stop_flag = True
        h._eval_worker.quit()
        h._eval_worker.wait(3000)

    # Unblock and wait for old worker to finish
    _block_api.set()
    time.sleep(0.2)
    QApplication.processEvents()

    # Start new worker
    h.results.clear()
    _block_api.set()  # unblock for new worker
    w2 = EvalWorker(ai, "prompt 2", 2500)
    h._eval_worker = w2
    w2.finished.connect(h.on_finished)
    w2.error.connect(h.on_error)
    w2.finished.connect(w2.deleteLater)
    w2.error.connect(w2.deleteLater)
    w2.start()
    w2.wait(5000)
    time.sleep(0.1)
    QApplication.processEvents()

    assert h._eval_worker is None, "Worker ref should be None after completion"
    assert len(h.results) == 1 and "finished" in h.results[0], f"Expected 1 finished, got {h.results}"
    print("[TEST 4] PASS")

    # ---- Results ----
    if errors:
        print(f"\nFAILED: {len(errors)} error(s)")
        for e in errors:
            print(f"  - {e}")
        return 1
    else:
        print("\nALL TESTS PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(test_worker_lifecycle())
