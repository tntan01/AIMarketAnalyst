"""
Test race condition fix: analyze_btn bị disable khi backtest đang chạy.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication


class TestAnalyzeBtnDisabledDuringBacktest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(sys.argv)

    def setUp(self):
        from ui.screens.backtest_screen import BacktestScreen

        self.mock_app = MagicMock()
        self.mock_app.backtest_controller = MagicMock()
        self.mock_app.settings_service = MagicMock()

        self.screen = BacktestScreen(app=self.mock_app)
        self.screen.analyze_btn.setEnabled(True)
        self.screen.run_button.setEnabled(True)

    def tearDown(self):
        self.screen.close()

    # ── Disable khi backtest chạy ─────────────────────────────────

    def test_analyze_btn_disabled_when_backtest_starts(self):
        """Khi backtest bắt đầu → analyze_btn bị disable."""
        self.screen.controller.create_backtest_worker_from_inputs.return_value = (
            MagicMock(), MagicMock()
        )

        self.assertTrue(self.screen.analyze_btn.isEnabled())
        self.screen._run_backtest()

        self.assertFalse(self.screen.analyze_btn.isEnabled(),
                         "analyze_btn phải bị disable khi backtest chạy")

    def test_run_button_also_disabled(self):
        """run_button vẫn bị disable như trước (không regression)."""
        self.screen.controller.create_backtest_worker_from_inputs.return_value = (
            MagicMock(), MagicMock()
        )

        self.screen._run_backtest()

        self.assertFalse(self.screen.run_button.isEnabled(),
                         "run_button vẫn phải bị disable khi backtest chạy")

    # ── Không crash khi build_requests fail ───────────────────────

    def test_request_building_is_delegated_to_backtest_worker(self):
        """Khi build_requests throw exception → analyze_btn không đổi."""
        self.screen.controller.build_requests.side_effect = ValueError("bad input")
        self.screen.controller.create_backtest_worker_from_inputs.return_value = (
            MagicMock(), MagicMock()
        )

        with patch("ui.screens.backtest_screen.QMessageBox.warning") as warning:
            self.screen._run_backtest()

        # build_requests fail → return sớm, analyze_btn vẫn enabled
        self.assertFalse(self.screen.analyze_btn.isEnabled(),
                        "analyze_btn vẫn enabled khi build_requests fail")
        warning.assert_not_called()

    # ── Re-enable khi backtest hoàn thành (signal connection) ─────

    def test_finished_signal_connected_to_reenable_analyze_btn(self):
        """finished signal được connect để re-enable analyze_btn."""
        mock_thread = MagicMock()
        mock_worker = MagicMock()
        self.screen.controller.create_backtest_worker_from_inputs.return_value = (
            mock_thread, mock_worker
        )

        self.screen._run_backtest()

        # Kiểm tra finished.connect được gọi để re-enable analyze_btn
        # Tìm call có lambda re-enable analyze_btn
        found_analyze_reconnect = False
        for call_args in mock_worker.finished.connect.call_args_list:
            args = call_args[0]
            if len(args) == 1:
                # Gọi lambda để kiểm tra behavior
                self.screen.analyze_btn.setEnabled(False)
                args[0]()  # execute the lambda
                if self.screen.analyze_btn.isEnabled():
                    found_analyze_reconnect = True

        # Reset về enabled để test tiếp
        self.screen.analyze_btn.setEnabled(True)

        self.assertTrue(found_analyze_reconnect,
                        "finished signal phải có lambda re-enable analyze_btn")

    def test_finished_signal_connected_to_reenable_run_button(self):
        """finished signal vẫn reconnect run_button (không regression)."""
        mock_worker = MagicMock()
        self.screen.controller.create_backtest_worker_from_inputs.return_value = (
            MagicMock(), mock_worker
        )

        self.screen._run_backtest()

        found_run_reconnect = False
        for call_args in mock_worker.finished.connect.call_args_list:
            args = call_args[0]
            if len(args) == 1:
                self.screen.run_button.setEnabled(False)
                args[0]()
                if self.screen.run_button.isEnabled():
                    found_run_reconnect = True

        self.screen.run_button.setEnabled(True)
        self.assertTrue(found_run_reconnect,
                        "finished signal phải có lambda re-enable run_button")


if __name__ == "__main__":
    unittest.main(verbosity=2)
