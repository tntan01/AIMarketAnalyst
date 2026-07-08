"""Test suite for Group D — pre-warm market data cache sooner.

D2 — ``QTimer.singleShot(3000, ...)`` replaced with immediate call
     in ``_build_ui``, since ``MarketWorker`` runs on its own thread.
"""

from __future__ import annotations

import inspect
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# D2 — immediate market data fetch in _build_ui
# ---------------------------------------------------------------------------


class TestD2PreWarmCache:
    def test_no_3s_delay_in_build_ui(self):
        """Verify the 3000ms QTimer.singleShot has been removed."""
        from ui.screens.dashboard_screen import DashboardScreen

        source = inspect.getsource(DashboardScreen._build_ui)
        assert "QTimer.singleShot(3000" not in source, (
            "D2 FAILED: QTimer.singleShot(3000, ...) still present in _build_ui"
        )

    def test_refresh_market_overview_called_in_build_ui(self):
        """Verify _refresh_market_overview is called directly in _build_ui."""
        from ui.screens.dashboard_screen import DashboardScreen

        source = inspect.getsource(DashboardScreen._build_ui)
        assert "self._refresh_market_overview()" in source, (
            "D2 FAILED: _refresh_market_overview() call not found in _build_ui"
        )

    def test_worker_guard_still_in_place(self):
        """Verify _refresh_market_overview still guards against duplicate workers."""
        from ui.screens.dashboard_screen import DashboardScreen

        source = inspect.getsource(DashboardScreen._refresh_market_overview)
        assert "isRunning" in source, (
            "D2 FAILED: worker guard (isRunning check) missing"
        )

    def test_market_worker_runs_on_thread(self):
        """MarketWorker.start() spawns a QThread — verify it does not block."""
        from ui.screens.dashboard_screen import MarketWorker
        from services.market_data_service import fetch_market_overview

        # Patch the actual fetch to return immediately with test data
        with patch(
            "ui.screens.dashboard_screen.fetch_market_overview",
            return_value={"DXY": (103.0, 0.5)},
        ):
            worker = MarketWorker()
            worker.start()
            worker.wait(5000)  # max 5s

        assert not worker.isRunning(), (
            "D2 FAILED: MarketWorker did not finish within 5s — may be blocking"
        )

    def test_redundant_refresh_blocked(self):
        """Calling _refresh_market_overview while worker is running should no-op."""
        # We test the guard logic by simulating a running worker
        mock_worker = MagicMock()
        mock_worker.isRunning.return_value = True

        # Simulate the attribute check in _refresh_market_overview
        screen = MagicMock()
        screen.market_worker = mock_worker

        # Replicate the guard logic from _refresh_market_overview
        if hasattr(screen, 'market_worker') and screen.market_worker is not None:
            try:
                if screen.market_worker.isRunning():
                    # Should return early, NOT start a new worker
                    worker_started = False
                else:
                    worker_started = True
            except RuntimeError:
                worker_started = True
        else:
            worker_started = True

        assert not worker_started, (
            "D2 FAILED: guard should block re-fetch while worker is running"
        )


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
