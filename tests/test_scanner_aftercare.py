"""Phase 3 — core result early, aftercare delta, scan lock and stale-ID guard."""

from __future__ import annotations

import statistics
import time
from threading import Barrier, Thread
from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

import pytest

import controllers.scanner_controller as scanner_module
from controllers.scanner_controller import ScannerController
from core.scanner import (
    ScannerRequest,
    blocked_scanner_row,
    build_scanner_output,
)
from core.scanner_observability import create_scan_context
from core.scanner_rollout import build_rollout_policy
from config.settings import ScannerRolloutSettings
from ui.screens.scanner_screen import ScannerScreen


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
    def __init__(self):
        self.calls = 0

    def ensure_ready(self, require_login=True):
        self.calls += 1
        return _Status()

    def account_balance(self):
        self.calls += 1
        return 10000.0

    def portfolio_snapshot(self):
        self.calls += 1
        return SimpleNamespace(to_dict=lambda: {"available": True})

    def available_symbols(self, market_watch_only=True):
        self.calls += 1
        return ["EURUSD"]


class _News:
    def preload_macro_contexts(self, symbols, progress_callback=None, ai_service=None):
        return None

    def macro_freshness_status(self):
        return {"confidence_multiplier": 1.0}


class _Journal:
    def list_closed_trades_for_account_guard(self):
        return []


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
        news_service=_News(),
        journal_service=_Journal(),
        telegram_service=MagicMock(),
        rollout_metrics_service=_RolloutMetrics(),
        retention_service=MagicMock(),
    )
    ctrl.observability = MagicMock()
    return ctrl


def _request(
    *,
    early: bool = False,
    persistence: str = "none",
    symbols: list[str] | None = None,
):
    return ScannerRequest(
        symbols=symbols or ["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=False,
        persistence_mode=persistence,
        feature_flags={"scanner_core_result_early": early},
    )


# ---------------------------------------------------------------------------
# Controller orchestration: core emitted before aftercare, merged result, lock
# ---------------------------------------------------------------------------


def test_split_core_callback_fires_before_aftercare_and_merged_returned(monkeypatch):
    ctrl = _make_controller()
    request = _request(early=True)
    events: list[str] = []

    def fake_core(
        req,
        progress,
        *,
        scan_context,
        settings,
        rollout_policy,
        pre_scan_readiness,
        pre_scan_canary_readiness,
        mt5_balance,
        portfolio_state,
    ):
        events.append("core")
        return {"scan_id": scan_context.scan_id, "rows": ["row"]}, {"rows": ["row"]}

    def fake_aftercare(core_output, req, progress, *, ctx, fatal_errors=False):
        events.append("aftercare")
        return {
            "scan_id": core_output["scan_id"],
            "telegram_alerts": {"sent": 1},
        }

    monkeypatch.setattr(ctrl, "_run_market_scan_core", fake_core)
    monkeypatch.setattr(ctrl, "_run_market_scan_aftercare", fake_aftercare)
    delivered: list[dict] = []

    result = ctrl.run_market_scan(
        request=request, _core_ready_callback=delivered.append
    )

    assert events == ["core", "aftercare"]
    assert delivered and delivered[0]["rows"] == ["row"]
    assert result["telegram_alerts"] == {"sent": 1}
    assert result["rows"] == ["row"]
    # Lock is released after the scan finishes.
    assert ctrl._active_scan() is None


def test_legacy_mode_returns_merged_result_without_core_callback(monkeypatch):
    ctrl = _make_controller()
    request = _request(early=False)

    def fake_core(req, progress, **kwargs):
        return {"scan_id": kwargs["scan_context"].scan_id, "rows": []}, {}

    def fake_aftercare(core_output, req, progress, *, ctx, fatal_errors):
        return {"scan_id": core_output["scan_id"], "telegram_alerts": {"sent": 0}}

    monkeypatch.setattr(ctrl, "_run_market_scan_core", fake_core)
    monkeypatch.setattr(ctrl, "_run_market_scan_aftercare", fake_aftercare)
    delivered: list[dict] = []

    # Flag OFF: the controller never emits an early core signal even if a
    # callback were supplied — the UI waits for the fully merged result.
    result = ctrl.run_market_scan(
        request=request, _core_ready_callback=delivered.append
    )

    assert delivered == []
    assert result["telegram_alerts"] == {"sent": 0}
    assert result["rows"] == []


def test_scan_lock_primitive_rejects_second_core_scan():
    ctrl = _make_controller()
    assert ctrl._try_acquire_scan("scan-a") is True
    assert ctrl._try_acquire_scan("scan-b") is False
    ctrl._release_scan("scan-b")  # non-owner release is a no-op
    assert ctrl._active_scan() == "scan-a"
    ctrl._release_scan("scan-a")
    assert ctrl._active_scan() is None


def test_scan_lock_rejects_overlapping_scan():
    ctrl = _make_controller()
    request = _request(early=True)
    ctrl._try_acquire_scan("scan-held")
    try:
        with pytest.raises(RuntimeError, match="Scanner đang chạy"):
            ctrl.run_market_scan(request=request)
    finally:
        ctrl._release_scan("scan-held")
    assert ctrl._active_scan() is None


def test_scan_lock_contention_only_one_caller_wins():
    """Eight threads race to acquire the scan lock; exactly one must win."""
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


def test_unexpected_aftercare_crash_still_returns_core(monkeypatch):
    ctrl = _make_controller()
    request = _request(early=True)
    core_output = {"scan_id": "scan-1", "rows": ["row"]}

    def fake_core(req, progress, **kwargs):
        return core_output, {}

    def boom(core, req, progress, *, ctx, fatal_errors=False):
        raise RuntimeError("aftercare bug")

    monkeypatch.setattr(ctrl, "_run_market_scan_core", fake_core)
    monkeypatch.setattr(ctrl, "_run_market_scan_aftercare", boom)
    delivered: list[dict] = []

    result = ctrl.run_market_scan(
        request=request, _core_ready_callback=delivered.append
    )

    assert delivered == [core_output]
    assert result["rows"] == ["row"]
    assert "aftercare_error" in result


# ---------------------------------------------------------------------------
# Full split scan: core signal fires before Telegram and persistence
# ---------------------------------------------------------------------------


def test_full_scan_core_ready_before_telegram_and_persistence(monkeypatch):
    ctrl = _make_controller()
    request = _request(early=True, persistence="full")
    order: list[str] = []

    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )

    def record_core(core_output):
        order.append("core")
        assert "telegram" not in order
        assert "persistence" not in order

    def record_telegram(rows):
        order.append("telegram")
        return {"attempted": 0, "sent": 0, "errors": [], "summary_sent": 0}

    def record_save(result):
        order.append("persistence")
        return Path("/tmp/scan-snapshot.json")

    monkeypatch.setattr(ctrl, "_send_telegram_alerts", record_telegram)
    monkeypatch.setattr(ctrl, "save_snapshot", record_save)

    result = ctrl.run_market_scan(
        request=request, _core_ready_callback=record_core
    )

    assert order == ["core", "telegram", "persistence"]
    assert result["scan_id"]
    assert result["telegram_alerts"]["sent"] == 0
    assert result["snapshot_path"] == str(Path("/tmp/scan-snapshot.json"))
    assert result["market_brief_error"]
    assert ctrl._active_scan() is None


def test_aftercare_step_error_does_not_lose_core_result(monkeypatch):
    ctrl = _make_controller()
    request = _request(early=True)
    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )
    delivered: list[dict] = []

    def boom(rows):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(ctrl, "_send_telegram_alerts", boom)

    result = ctrl.run_market_scan(
        request=request, _core_ready_callback=delivered.append
    )

    assert delivered and delivered[0]["rows"] == result["rows"]
    assert result["telegram_alerts"]["errors"] == ["telegram down"]
    assert result["rows"]  # rows survive the aftercare error
    assert ctrl._active_scan() is None


def test_aftercare_mutating_rows_cannot_corrupt_core_output(monkeypatch):
    """mục 19.3: aftercare works on its own snapshot, never the UI's rows."""
    ctrl = _make_controller()
    request = _request(early=True)
    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )
    delivered: list[dict] = []

    def destructive_telegram(rows):
        rows.clear()
        raise RuntimeError("telegram down")

    monkeypatch.setattr(ctrl, "_send_telegram_alerts", destructive_telegram)

    result = ctrl.run_market_scan(
        request=request, _core_ready_callback=delivered.append
    )

    # The core output handed to the UI is untouched even though the aftercare
    # dependency cleared its own row snapshot.
    assert len(delivered[0]["rows"]) == 1
    assert delivered[0]["rows"][0]["symbol"] == "EUR/USD"
    assert len(result["rows"]) == 1
    assert result["telegram_alerts"]["errors"] == ["telegram down"]


def test_flag_off_telegram_error_fails_scan(monkeypatch):
    """Rollback (mục 20.3): flag OFF keeps the old fatal Telegram semantics."""
    ctrl = _make_controller()
    request = _request(early=False)
    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )

    def boom(rows):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(ctrl, "_send_telegram_alerts", boom)

    with pytest.raises(RuntimeError, match="telegram down"):
        ctrl.run_market_scan(request=request)


def test_flag_off_auto_trade_error_fails_scan(monkeypatch):
    """Rollback: flag OFF keeps the old fatal auto-trade semantics."""
    ctrl = _make_controller()
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=True,
        persistence_mode="none",
        feature_flags={"scanner_core_result_early": False},
    )
    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )

    def boom(rows, request, rollout_policy):
        raise RuntimeError("auto trade down")

    monkeypatch.setattr(ctrl, "_execute_auto_trades", boom)

    with pytest.raises(RuntimeError, match="auto trade down"):
        ctrl.run_market_scan(request=request)


def test_flag_on_auto_trade_error_is_recorded(monkeypatch):
    """Split: an auto-trade error is recorded and does not lose the core result."""
    ctrl = _make_controller()
    request = ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        auto_trade_enabled=True,
        persistence_mode="none",
        feature_flags={"scanner_core_result_early": True},
    )
    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )
    delivered: list[dict] = []

    def boom(rows, request, rollout_policy):
        raise RuntimeError("auto trade down")

    monkeypatch.setattr(ctrl, "_execute_auto_trades", boom)

    result = ctrl.run_market_scan(
        request=request, _core_ready_callback=delivered.append
    )

    assert delivered and delivered[0]["rows"]
    assert result["auto_trade_error"] == "auto trade down"
    assert result["rows"]


def test_flag_off_and_on_share_output_parity(monkeypatch):
    """ON and OFF modes produce the same final merged output on success."""
    ctrl = _make_controller()
    symbols = ["EUR/USD", "GBP/USD"]
    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )
    monkeypatch.setattr(
        ctrl,
        "_send_telegram_alerts",
        lambda rows: {"attempted": 0, "sent": 0, "errors": [], "summary_sent": 0},
    )

    legacy = ctrl.run_market_scan(request=_request(early=False, symbols=symbols))
    split = ctrl.run_market_scan(
        request=_request(early=True, symbols=symbols),
        _core_ready_callback=lambda out: None,
    )

    # Same top-level keys and same stable fields. Volatile fields (scan_id,
    # timestamp, scan_context, request-hash feature_flags) differ by design.
    assert set(legacy.keys()) == set(split.keys())
    assert legacy["summary"] == split["summary"]
    assert legacy["telegram_alerts"] == split["telegram_alerts"]
    assert legacy["market_brief_error"] == split["market_brief_error"]
    assert legacy["auto_trade_results"] == split["auto_trade_results"]
    assert [row["symbol"] for row in legacy["rows"]] == [
        row["symbol"] for row in split["rows"]
    ]


def _measure_ui_visible_times(ctrl, symbols, runs=10, warmup=2, aftercare_delay=0.2):
    """Measure UI-visible time for legacy vs split across `runs` iterations.

    Returns (legacy_ms, split_ms) sorted lists. The aftercare dependency is a
    controllable deterministic delay so the structural difference (UI shows at
    core_ready vs after everything) is measurable without real I/O.
    """

    def slow_telegram(rows):
        time.sleep(aftercare_delay)
        return {"attempted": 0, "sent": 0, "errors": [], "summary_sent": 0}

    ctrl._send_telegram_alerts = slow_telegram

    # Warm-up (>=2 runs) so thread pools and caches are steady.
    for _ in range(warmup):
        ctrl.run_market_scan(request=_request(early=True, symbols=symbols))
        ctrl.run_market_scan(request=_request(early=False, symbols=symbols))

    legacy_ms: list[float] = []
    split_ms: list[float] = []
    for _ in range(runs):
        # Legacy: the UI table appears only when run_market_scan returns.
        start = time.perf_counter()
        ctrl.run_market_scan(request=_request(early=False, symbols=symbols))
        legacy_ms.append((time.perf_counter() - start) * 1000)

        # Split: the UI table appears at the core_ready callback.
        core_ready_at: list[float] = []
        start = time.perf_counter()
        ctrl.run_market_scan(
            request=_request(early=True, symbols=symbols),
            _core_ready_callback=lambda out: core_ready_at.append(
                time.perf_counter()
            ),
        )
        split_ms.append((core_ready_at[0] - start) * 1000)

    return legacy_ms, split_ms


def _p50(values):
    return statistics.median(values)


def _p95(values):
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1)))))
    return ordered[index]


def test_ui_visible_time_28_symbols_p50_p95(monkeypatch):
    """Characterization (mục 17.3): 28 symbols, warm-up, >=10 runs, P50/P95."""
    ctrl = _make_controller()
    symbols = [f"SYM{i:02d}" for i in range(28)]
    monkeypatch.setattr(
        scanner_module, "fetch_macro_correlation_context", lambda: {"available": False}
    )
    monkeypatch.setattr(
        scanner_module, "_fetch_one_symbol_mt5", lambda *a, **k: None
    )

    legacy_ms, split_ms = _measure_ui_visible_times(
        ctrl, symbols, runs=10, warmup=2, aftercare_delay=0.2
    )

    legacy_p50 = _p50(legacy_ms)
    split_p50 = _p50(split_ms)
    print(
        f"\n[benchmark 28-symbol] legacy P50={legacy_p50:.1f}ms "
        f"P95={_p95(legacy_ms):.1f}ms | split P50={split_p50:.1f}ms "
        f"P95={_p95(split_ms):.1f}ms"
    )
    # The split shows the table at core_ready, i.e. before the injected
    # aftercare delay; legacy must wait for the whole aftercare.
    assert split_p50 < legacy_p50 / 3
    assert len(legacy_ms) == 10
    assert len(split_ms) == 10


# ---------------------------------------------------------------------------
# Aftercare delta contract (isolation)
# ---------------------------------------------------------------------------


def test_aftercare_returns_delta_without_mutating_core(monkeypatch):
    ctrl = _make_controller()
    request = _request(early=True)
    settings = _settings()
    scan_context = create_scan_context(settings, request)
    rows = [blocked_scanner_row("EUR/USD", "test")]
    core_output = build_scanner_output(rows, request, 0)
    core_output["scan_id"] = scan_context.scan_id
    core_output["scan_context"] = scan_context.to_dict()
    policy = build_rollout_policy(settings.scanner_rollout, server="Broker-Demo")
    ctx = {
        "scan_context": scan_context,
        "settings": settings,
        "rollout_policy": policy,
        "pre_scan_readiness": {"ready": True},
        "pre_scan_canary_readiness": {"ready": True},
        "correlation_context": {},
        "freshness": {},
        "closed_trades": [],
        "rows": rows,
        "portfolio_state": {},
    }

    def boom(rows):
        raise RuntimeError("telegram down")

    monkeypatch.setattr(ctrl, "_send_telegram_alerts", boom)

    delta = ctrl._run_market_scan_aftercare(
        core_output, request, lambda p, m: None, ctx=ctx
    )

    assert delta["scan_id"] == scan_context.scan_id
    assert delta["telegram_alerts"]["errors"] == ["telegram down"]
    assert "telegram_error" in delta
    assert delta["auto_trade_results"]["enabled"] is False
    assert delta["market_brief_error"]
    # Core output is immutable: aftercare must not mutate it.
    assert core_output["rows"] == rows
    assert "telegram_alerts" not in core_output
    merged = {**core_output, **delta}
    assert merged["rows"] == rows


# ---------------------------------------------------------------------------
# ScannerScreen stale-scan-ID guard (merge on GUI thread only)
# ---------------------------------------------------------------------------


class _ProgressBar:
    def __init__(self):
        self.value = None
        self.visible = True

    def setValue(self, value):
        self.value = value

    def setVisible(self, visible):
        self.visible = visible


def _screen_owner(active_scan_id: str, scan_result: dict):
    return type(
        "Owner",
        (),
        {
            "_active_scan_id": active_scan_id,
            "scan_result": scan_result,
            "progress_bar": _ProgressBar(),
            "progress_container": _ProgressBar(),
            "_apply_scan_status": lambda self, result: _screen_owner._calls.append(
                ("status", result)
            ),
            "_apply_market_brief": lambda self, result: _screen_owner._calls.append(
                ("brief", result)
            ),
            "_configure_table_columns": lambda self: _screen_owner._calls.append(
                "configure"
            ),
        },
    )()


def test_stale_aftercare_delta_does_not_overwrite_new_scan():
    _screen_owner._calls = []
    owner = _screen_owner(
        "scan-new", {"scan_id": "scan-new", "rows": ["row"]}
    )
    stale = {"scan_id": "scan-old", "telegram_alerts": {"sent": 9}}

    ScannerScreen._scan_aftercare_finished(owner, stale)

    assert owner.scan_result == {"scan_id": "scan-new", "rows": ["row"]}
    assert _screen_owner._calls == []


def test_matching_aftercare_delta_merges_on_gui_thread():
    _screen_owner._calls = []
    core = {
        "scan_id": "scan-1",
        "rows": ["row"],
        "timestamp": "2026-01-01T00:00:00+07:00",
        "rollout_policy": {"stage": "SHADOW"},
        "ai_called": 0,
    }
    owner = _screen_owner("scan-1", core)
    delta = {
        "scan_id": "scan-1",
        "market_brief": "brief",
        "telegram_alerts": {"sent": 1},
    }
    # Aftercare returns only the delta; the screen merges it into the core
    # result it already holds on the GUI thread (mục 19.3 / 11.3).
    ScannerScreen._scan_aftercare_finished(owner, delta)

    expected = {**core, **delta}
    assert owner.scan_result["market_brief"] == "brief"
    assert owner.scan_result["telegram_alerts"] == {"sent": 1}
    assert owner.scan_result["rows"] == ["row"]  # core rows preserved
    assert owner.scan_result["rollout_policy"] == {"stage": "SHADOW"}
    assert ("status", expected) in _screen_owner._calls
    assert ("brief", expected) in _screen_owner._calls
    assert owner.progress_bar.value == 100
    assert owner.progress_container.visible is False


def test_core_ready_shows_pending_aftercare_status():
    status_labels = {
        "AI đã gọi": MagicMock(),
        "Telegram": MagicMock(),
        "Rollout": MagicMock(),
        "Lần quét gần nhất": MagicMock(),
    }
    owner = type(
        "Owner",
        (),
        {
            "_active_scan_id": "",
            "scan_result": None,
            "status_labels": status_labels,
            "progress_bar": _ProgressBar(),
            "scan_button": MagicMock(),
            "_render_scan_table": lambda self, result: None,
            "_update_status_summary": lambda self: None,
        },
    )()
    ScannerScreen._scan_core_finished(
        owner,
        {"scan_id": "scan-1", "rows": ["row"], "timestamp": "2026-01-01T00:00:00+07:00"},
    )

    assert owner._active_scan_id == "scan-1"
    status_labels["AI đã gọi"].setText.assert_called_once_with("Đang tạo bản tin...")
    status_labels["Telegram"].setText.assert_called_once_with("Đang gửi...")
    status_labels["Rollout"].setText.assert_called_once_with("Đang ghi nhận...")
    assert owner.progress_bar.value == 96
    owner.scan_button.setText.assert_called_once_with("Đang gửi/lưu kết quả...")
