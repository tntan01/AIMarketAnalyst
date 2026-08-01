"""Phase 5 — controller-level scanner scan lock (mục 12.3, mục 22 #9).

The lock is per controller instance: two core scans on the SAME controller
never overlap, while independent controllers are not blocked outside their
scope.  Overlap between separate windows/processes is handled by later
single-instance/OS-mutex work, not by this lock.
"""

from __future__ import annotations

from threading import Barrier, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from controllers.scanner_controller import ScannerController
from core.scanner import ScannerRequest
from config.settings import ScannerRolloutSettings


def _settings():
    return SimpleNamespace(
        trading=SimpleNamespace(
            max_risk_percent=2.0,
            account_currency="USD",
            lot_step=0.01,
            minimum_lot=0.01,
            contract_size_override={},
            default_risk_percent=1.0,
            max_daily_loss_pct=2.0,
            max_weekly_loss_pct=5.0,
            max_consecutive_losses=3,
            max_open_risk_pct=3.0,
        ),
        advanced=SimpleNamespace(
            d1_bars=500,
            h4_bars=500,
            h1_bars=500,
            scanner_ai_detail_limit=3,
            high_impact_news_block_before_minutes=30,
            high_impact_news_block_after_minutes=30,
            block_high_impact_news=True,
        ),
        display=SimpleNamespace(timezone="Asia/Ho_Chi_Minh"),
        ai=SimpleNamespace(active_provider=lambda: None),
        notifications=SimpleNamespace(
            telegram_bot_token="", telegram_chat_ids=[]
        ),
        scanner_rollout=ScannerRolloutSettings(shadow_compare_enabled=False),
    )


class _SettingsService:
    def __init__(self, settings=None):
        self._settings = settings or _settings()

    def load(self):
        return self._settings


class _Status:
    server = "Broker-Demo"
    provider_name = "MT5 fixture"
    connected = True
    logged_in = True


class _MT5:
    def ensure_ready(self, require_login=True):
        return _Status()

    def account_balance(self):
        return 10000.0

    def portfolio_snapshot(self):
        return SimpleNamespace(to_dict=lambda: {"available": True})


class _RolloutMetrics:
    def readiness(self, settings):
        return {"ready": True}

    def canary_readiness(self, settings):
        return {"ready": True}

    def record_scan(self, **kwargs):
        return {"recorded": True}


def _make_controller():
    ctrl = ScannerController(
        settings_service=_SettingsService(),
        mt5=_MT5(),
        news_service=MagicMock(),
        journal_service=MagicMock(),
        telegram_service=MagicMock(),
        rollout_metrics_service=_RolloutMetrics(),
        retention_service=MagicMock(),
    )
    ctrl.observability = MagicMock()
    return ctrl


def _request():
    return ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=False,
        persistence_mode="none",
    )


def test_scan_lock_rejects_overlapping_scan_on_same_controller():
    ctrl = _make_controller()

    assert ctrl._try_acquire_scan("scan-a") is True
    assert ctrl._try_acquire_scan("scan-b") is False
    assert ctrl._active_scan() == "scan-a"
    with pytest.raises(RuntimeError, match="Scanner đang chạy \\(scan scan-a\\)"):
        ctrl.run_market_scan(request=_request())
    ctrl._release_scan("scan-a")
    assert ctrl._active_scan() is None


def test_rejected_scan_reports_owner_captured_before_owner_changes(monkeypatch):
    ctrl = _make_controller()
    assert ctrl._try_acquire_scan("scan-old") is True
    try_acquire_with_owner = ctrl._try_acquire_scan_with_owner

    def reject_then_replace_owner(scan_id):
        acquired, active_owner = try_acquire_with_owner(scan_id)
        assert acquired is False
        assert active_owner == "scan-old"

        ctrl._release_scan("scan-old")
        replacement_acquired, replacement_owner = try_acquire_with_owner("scan-new")
        assert replacement_acquired is True
        assert replacement_owner is None
        return acquired, active_owner

    monkeypatch.setattr(
        ctrl, "_try_acquire_scan_with_owner", reject_then_replace_owner
    )

    try:
        with pytest.raises(RuntimeError) as exc_info:
            ctrl.run_market_scan(request=_request())

        message = str(exc_info.value)
        assert "scan scan-old" in message
        assert "scan None" not in message
        assert "scan scan-new" not in message
        assert ctrl._active_scan() == "scan-new"
    finally:
        ctrl._release_scan("scan-new")


def test_independent_controllers_are_not_blocked():
    first = _make_controller()
    second = _make_controller()

    assert first._try_acquire_scan("scan-a") is True
    assert second._try_acquire_scan("scan-b") is True
    assert first._active_scan() == "scan-a"
    assert second._active_scan() == "scan-b"

    first._release_scan("scan-a")
    second._release_scan("scan-b")
    assert first._active_scan() is None
    assert second._active_scan() is None


def test_lock_released_when_core_scan_raises(monkeypatch):
    ctrl = _make_controller()

    def boom(*args, **kwargs):
        raise RuntimeError("core failure")

    monkeypatch.setattr(ctrl, "_run_market_scan_core", boom)

    with pytest.raises(RuntimeError, match="core failure"):
        ctrl.run_market_scan(request=_request())

    assert ctrl._active_scan() is None
    # The same controller can start a new scan right after the error.
    assert ctrl._try_acquire_scan("scan-after-error") is True
    ctrl._release_scan("scan-after-error")


def test_release_with_unknown_scan_id_is_a_noop():
    ctrl = _make_controller()
    ctrl._try_acquire_scan("scan-a")

    ctrl._release_scan("scan-other")

    assert ctrl._active_scan() == "scan-a"
    ctrl._release_scan("scan-a")
    assert ctrl._active_scan() is None


def test_concurrent_scans_on_same_controller_have_single_winner():
    ctrl = _make_controller()
    results: list[bool] = []
    barrier = Barrier(8)

    def contender() -> None:
        barrier.wait()
        results.append(ctrl._try_acquire_scan("scan-contend"))

    threads = [Thread(target=contender) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results) == 1
    ctrl._release_scan("scan-contend")
    assert ctrl._active_scan() is None


def test_concurrent_independent_controllers_each_allow_one_scan():
    first = _make_controller()
    second = _make_controller()
    results_first: list[bool] = []
    results_second: list[bool] = []
    barrier = Barrier(6)

    def contender(ctrl, results) -> None:
        barrier.wait()
        results.append(ctrl._try_acquire_scan("scan-race"))

    threads = [
        Thread(target=contender, args=(first, results_first)) for _ in range(3)
    ]
    threads += [
        Thread(target=contender, args=(second, results_second)) for _ in range(3)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sum(results_first) == 1
    assert sum(results_second) == 1
    first._release_scan("scan-race")
    second._release_scan("scan-race")
