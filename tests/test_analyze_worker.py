"""
Test AnalyzeWorker — xác minh logic async AI call không block main thread.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication


class TestAnalyzeWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from workers.analyze_worker import AnalyzeWorker
        self.AnalyzeWorker = AnalyzeWorker

    # ── Success path ──────────────────────────────────────────────

    def test_worker_emits_succeeded_with_ai_response(self):
        """AI trả về chuỗi hợp lệ → worker emits succeeded signal."""
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")
        prompt = "Phân tích backtest này"

        worker = self.AnalyzeWorker(config, prompt)

        responses = []

        def on_succeeded(response: str):
            responses.append(response)

        worker.succeeded.connect(on_succeeded)

        with patch("workers.analyze_worker.AIService") as MockAIService:
            mock_ai = MagicMock()
            mock_ai.analyze.return_value = "AI nhận xét: backtest tốt"
            MockAIService.return_value = mock_ai

            worker.run()

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0], "AI nhận xét: backtest tốt")
        self.assertEqual(worker.state, "finished")

    # ── Failure path ──────────────────────────────────────────────

    def test_worker_emits_failed_on_exception(self):
        """AI call throw exception → worker emits failed signal."""
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")
        prompt = "Phân tích backtest này"

        worker = self.AnalyzeWorker(config, prompt)

        errors = []

        def on_failed(message: str):
            errors.append(message)

        worker.failed.connect(on_failed)

        with patch("workers.analyze_worker.AIService") as MockAIService:
            mock_ai = MagicMock()
            mock_ai.analyze.side_effect = RuntimeError("Không kết nối được AI API")
            MockAIService.return_value = mock_ai

            worker.run()

        self.assertEqual(len(errors), 1)
        self.assertIn("Không kết nối được AI API", errors[0])
        self.assertEqual(worker.state, "failed")

    # ── Finished signal always emits ──────────────────────────────

    def test_worker_always_emits_finished(self):
        """Dù success hay fail, finished signal luôn được emit."""
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")

        # Test success path
        worker_ok = self.AnalyzeWorker(config, "prompt")
        finished_ok = []

        worker_ok.finished.connect(lambda: finished_ok.append(True))

        with patch("workers.analyze_worker.AIService") as MockAIService:
            MockAIService.return_value.analyze.return_value = "ok"
            worker_ok.run()

        self.assertTrue(finished_ok, "finished signal should emit on success")

        # Test failure path
        worker_fail = self.AnalyzeWorker(config, "prompt")
        finished_fail = []

        worker_fail.finished.connect(lambda: finished_fail.append(True))

        with patch("workers.analyze_worker.AIService") as MockAIService:
            MockAIService.return_value.analyze.side_effect = RuntimeError("fail")
            worker_fail.run()

        self.assertTrue(finished_fail, "finished signal should emit on failure")

    # ── Edge cases ────────────────────────────────────────────────

    def test_empty_response_still_emits_succeeded(self):
        """AI trả về chuỗi rỗng → vẫn emit succeeded (UI tự xử lý empty)."""
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")
        worker = self.AnalyzeWorker(config, "prompt")

        responses = []

        worker.succeeded.connect(lambda r: responses.append(r))

        with patch("workers.analyze_worker.AIService") as MockAIService:
            MockAIService.return_value.analyze.return_value = ""
            worker.run()

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0], "")

    def test_whitespace_only_response_emits_succeeded(self):
        """AI trả về whitespace → vẫn emit succeeded."""
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")
        worker = self.AnalyzeWorker(config, "prompt")

        responses = []

        worker.succeeded.connect(lambda r: responses.append(r))

        with patch("workers.analyze_worker.AIService") as MockAIService:
            MockAIService.return_value.analyze.return_value = "   \n  "
            worker.run()

        self.assertEqual(len(responses), 1)

    def test_prompt_is_passed_correctly(self):
        """Prompt được truyền nguyên vẹn đến AIService."""
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")
        long_prompt = "Phân tích\n" * 100  # prompt dài

        worker = self.AnalyzeWorker(config, long_prompt)

        with patch("workers.analyze_worker.AIService") as MockAIService:
            mock_ai = MagicMock()
            mock_ai.analyze.return_value = "ok"
            MockAIService.return_value = mock_ai
            worker.run()

        mock_ai.analyze.assert_called_once_with(long_prompt)

    # ── Thread lifecycle (mô phỏng integration) ───────────────────

    def test_thread_lifecycle_pattern(self):
        """Mô phỏng pattern thread → worker → signals như trong backtest_screen."""
        from PyQt6.QtTest import QTest
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")

        thread = QThread()
        worker = self.AnalyzeWorker(config, "phân tích")
        worker.moveToThread(thread)

        results = {}
        finished_flag = []

        def on_succeeded(response: str):
            results["response"] = response

        def on_failed(message: str):
            results["error"] = message

        def on_finished():
            finished_flag.append(True)
            thread.quit()

        worker.succeeded.connect(on_succeeded)
        worker.failed.connect(on_failed)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)

        with patch("workers.analyze_worker.AIService") as MockAIService:
            MockAIService.return_value.analyze.return_value = "phân tích thành công"
            thread.start()

            # Pump event loop so queued signals get delivered
            for _ in range(100):
                QApplication.processEvents()
                if finished_flag:
                    break
                QTest.qWait(10)

            thread.wait(3000)

        self.assertIn("response", results)
        self.assertEqual(results["response"], "phân tích thành công")
        self.assertTrue(finished_flag, "finished signal phải được emit")

    def test_thread_failure_propagates_to_main_thread(self):
        """Exception trong worker thread → failed signal emit đúng trên main thread."""
        from PyQt6.QtTest import QTest
        from services.ai_service import AIProviderConfig

        config = AIProviderConfig(provider="deepseek", model="deepseek-chat", api_key="sk-test")

        thread = QThread()
        worker = self.AnalyzeWorker(config, "phân tích")
        worker.moveToThread(thread)

        results = {}
        finished_flag = []

        def on_failed(message: str):
            results["error"] = message

        def on_finished():
            finished_flag.append(True)
            thread.quit()

        worker.failed.connect(on_failed)
        worker.finished.connect(on_finished)
        thread.started.connect(worker.run)

        with patch("workers.analyze_worker.AIService") as MockAIService:
            MockAIService.return_value.analyze.side_effect = RuntimeError("timeout 120s")
            thread.start()

            for _ in range(100):
                QApplication.processEvents()
                if finished_flag:
                    break
                QTest.qWait(10)

            thread.wait(3000)

        self.assertIn("error", results)
        self.assertIn("timeout 120s", results["error"])
        self.assertTrue(finished_flag)


if __name__ == "__main__":
    unittest.main(verbosity=2)
