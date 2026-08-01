"""Phase 0 scanner performance telemetry contracts."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import controllers.scanner_controller as scanner_module
import services.market_data_service as market_data_module
from controllers.scanner_controller import ScannerController
from core.scanner import ScannerRequest, blocked_scanner_row
from core.scanner_observability import create_scan_context
from core.scanner_performance import (
    COUNTER_NAMES,
    PHASE_NAMES,
    SCAN_PERFORMANCE_SCHEMA_VERSION,
    ScanPerformanceTracker,
    safe_performance_call,
    safe_performance_phase,
)
from services.data_provider import ConnectionStatus
from services.mt5_service import MT5Service
from services.news_service import NewsService
from services.market_data_service import fetch_macro_correlation_context
from services.runtime_retention_service import RuntimeRetentionService
from services.storage_service import JsonStorage
from services.telegram_alert_service import (
    TelegramAlertResult,
    TelegramAlertService,
)


def test_tracker_tolerates_duplicate_and_missing_phases() -> None:
    tracker = ScanPerformanceTracker(scan_id="scan-1", symbol_count=2)

    tracker.start_phase("mt5_fetch")
    tracker.start_phase("mt5_fetch")
    tracker.end_phase("missing")
    tracker.end_phase("mt5_fetch")
    tracker.increment("mt5_copy_rates_calls", 4)
    tracker.record_symbol(
        "EUR/USD",
        fetch_ms=12.3,
        macro_lookup_ms=-1,
        mt5_ms=10.2,
        analysis_ms=4.5,
        pipeline_route="full",
    )
    tracker.mark_core_ready()

    first = tracker.finalize()
    second = tracker.finalize()

    assert first == second
    assert first["schema_version"] == SCAN_PERFORMANCE_SCHEMA_VERSION
    assert first["counters"]["mt5_copy_rates_calls"] == 4
    assert first["symbols"]["EUR/USD"]["macro_lookup_ms"] == 0.0
    assert all(value >= 0 for value in first["phases"].values())
    assert set(first["phases"]) == {f"{name}_ms" for name in PHASE_NAMES}
    assert (
        sum(first["exclusive_phases"].values())
        <= first["total_ms"] + 0.01
    )
    assert first["total_ms"] >= 0
    assert first["aftercare_ms"] >= 0


def test_tracker_closes_phase_when_instrumented_code_raises() -> None:
    tracker = ScanPerformanceTracker()

    try:
        with tracker.phase("analysis_wall"):
            raise RuntimeError("analysis failed")
    except RuntimeError:
        pass

    summary = tracker.finalize()

    assert summary["phases"]["analysis_wall_ms"] >= 0
    assert summary["completed_at"]


def test_overlap_preserves_raw_duration_and_separates_exclusive_budget() -> None:
    clock_values = iter((0.0, 0.0, 2.0, 10.0, 10.0, 10.0))
    tracker = ScanPerformanceTracker(clock=lambda: next(clock_values))

    tracker.start_phase("correlation")
    tracker.start_phase("macro_global_fetch")
    tracker.end_phase("macro_global_fetch")
    tracker.end_phase("correlation")
    summary = tracker.finalize()

    assert summary["phases"]["correlation_ms"] == 10_000.0
    assert summary["phases"]["macro_global_fetch_ms"] == 8_000.0
    assert summary["exclusive_phases"]["correlation_ms"] == 6_000.0
    assert summary["exclusive_phases"]["macro_global_fetch_ms"] == 4_000.0
    assert summary["phase_accounting"] == {
        "phases": "raw_elapsed",
        "exclusive_phases": "exclusive_wall_time",
        "exclusive_total_ms": 10_000.0,
    }


def test_snapshot_still_persists_when_performance_instrumentation_fails(
    tmp_path,
    monkeypatch,
) -> None:
    class BrokenTracker:
        def __getattr__(self, _name):
            raise RuntimeError("telemetry unavailable")

    controller = ScannerController.__new__(ScannerController)
    monkeypatch.setattr(
        "controllers.scanner_controller.app_data_dir",
        lambda: tmp_path,
    )

    path = controller.save_snapshot(
        {
            "scan_id": "scan-performance-failure",
            "timestamp": "2026-07-31T00:00:00+00:00",
            "rows": [],
            "summary": {},
        },
        performance_tracker=BrokenTracker(),
    )

    assert path.exists()
    assert path.name == "scanner_scan-performance-failure.json"


class _Observability:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def emit(self, event_type: str, **kwargs):
        event = {"event_type": event_type, **kwargs}
        self.events.append(event)
        return event


class _SpyTracker(ScanPerformanceTracker):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.started_phases: list[str] = []
        self.ended_phases: list[str] = []
        self.incremented_counters: list[str] = []

    def start_phase(self, name: str) -> None:
        self.started_phases.append(name)
        super().start_phase(name)

    def end_phase(self, name: str) -> None:
        self.ended_phases.append(name)
        super().end_phase(name)

    def increment(self, name: str, amount: int = 1) -> None:
        self.incremented_counters.append(name)
        super().increment(name, amount)


class _SettingsService:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            trading=SimpleNamespace(
                max_risk_percent=2.0,
                account_currency="USD",
                lot_step=0.01,
                minimum_lot=0.01,
                max_daily_loss_pct=3.0,
                max_weekly_loss_pct=6.0,
                max_consecutive_losses=3,
                max_open_risk_pct=5.0,
                contract_size_override={},
            ),
            advanced=SimpleNamespace(
                d1_bars=10,
                h4_bars=10,
                h1_bars=10,
            ),
            display=SimpleNamespace(timezone="Asia/Ho_Chi_Minh"),
            ai=SimpleNamespace(active_provider=lambda: None),
            notifications=SimpleNamespace(
                telegram_bot_token="super-secret-token",
                telegram_chat_ids=["secret-chat-id"],
            ),
            scanner_rollout=None,
        )

    def load(self):
        return self.settings


class _MT5:
    def ensure_ready(self, *, require_login: bool):
        assert require_login is True
        return ConnectionStatus(
            initialized=True,
            connected=True,
            logged_in=True,
            trade_allowed=False,
            provider_name="fixture",
            server="Fixture-Demo",
        )

    def account_balance(self):
        return 10_000.0

    def portfolio_snapshot(self):
        return SimpleNamespace(to_dict=lambda: {"available": True})

    def available_symbols(self, *, market_watch_only: bool):
        assert market_watch_only is True
        return ["EURUSD"]


class _News:
    def preload_macro_contexts(
        self,
        symbols,
        progress_callback=None,
        *,
        ai_service=None,
        performance_tracker=None,
    ):
        del symbols, progress_callback, ai_service
        with safe_performance_phase(
            performance_tracker,
            "macro_global_fetch",
        ):
            safe_performance_call(
                performance_tracker,
                "increment",
                "macro_global_fetches",
            )
            safe_performance_call(
                performance_tracker,
                "increment",
                "yfinance_download_calls",
            )
        with safe_performance_phase(
            performance_tracker,
            "macro_pair_build",
        ):
            safe_performance_call(
                performance_tracker,
                "increment",
                "macro_context_cache_misses",
            )

    @staticmethod
    def macro_freshness_status():
        return {"confidence_multiplier": 1.0}


class _Rollout:
    @staticmethod
    def readiness(_settings):
        return {"ready": True}

    @staticmethod
    def canary_readiness(_settings):
        return {"ready": True}

    @staticmethod
    def record_scan(**_kwargs):
        return {"recorded": True}


class _Telegram:
    @staticmethod
    def send_order_alerts(_candidates, **_kwargs):
        return TelegramAlertResult(attempted=0, sent=0, errors=[])

    @staticmethod
    def send_summary_alert(_rows, **_kwargs):
        return False


def _mocked_controller(tmp_path: Path) -> ScannerController:
    controller = ScannerController.__new__(ScannerController)
    controller.settings_service = _SettingsService()
    controller.mt5 = _MT5()
    controller.news_service = _News()
    controller.telegram_service = _Telegram()
    controller.journal_service = SimpleNamespace(
        list_closed_trades_for_account_guard=lambda: []
    )
    controller.orders_screen = None
    controller.observability = _Observability()
    controller.rollout_metrics = _Rollout()
    controller.retention = RuntimeRetentionService(tmp_path)
    controller._active_rollout_policy = None
    controller._apply_scanner_filters = lambda rows, _request: rows
    return controller


def _request() -> ScannerRequest:
    return ScannerRequest(
        symbols=["EUR/USD"],
        account_balance=10_000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
        persistence_mode="full",
    )


def _strip_telemetry(output: dict) -> dict:
    comparable = deepcopy(output)
    for key in (
        "performance",
        "performance_summary_path",
        "snapshot_path",
        "timestamp",
    ):
        comparable.pop(key, None)
    return comparable


def test_mocked_scan_persists_final_summary_and_failure_keeps_core_output(
    tmp_path,
    monkeypatch,
) -> None:
    request = _request()
    settings = _SettingsService().settings
    context = create_scan_context(
        settings,
        request,
        now=datetime(2026, 7, 31, tzinfo=timezone.utc),
    )

    def fake_correlation(**_kwargs):
        return {}

    def fake_fetch(symbol, *, performance_tracker=None, **_kwargs):
        safe_performance_call(
            performance_tracker,
            "increment",
            "mt5_copy_rates_calls",
            4,
        )
        safe_performance_call(
            performance_tracker,
            "increment",
            "mt5_full_history_calls",
            4,
        )
        safe_performance_call(
            performance_tracker,
            "record_symbol",
            symbol,
            mt5_ms=1.0,
            macro_lookup_ms=0.5,
        )
        return {
            "symbol": symbol,
            "broker_symbol": "EURUSD",
            "input_timestamps": {},
        }

    def fake_analyze(packet, **_kwargs):
        row = blocked_scanner_row(packet["symbol"], "fixture")
        row["analysis_latency_ms"] = 1.25
        row["pipeline_route"] = "full"
        return row

    monkeypatch.setattr(scanner_module, "app_data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        scanner_module,
        "create_scan_context",
        lambda _settings, _request: context,
    )
    monkeypatch.setattr(
        scanner_module,
        "fetch_macro_correlation_context",
        fake_correlation,
    )
    monkeypatch.setattr(scanner_module, "_fetch_one_symbol_mt5", fake_fetch)
    monkeypatch.setattr(scanner_module, "_analyze_one_symbol", fake_analyze)
    spy = _SpyTracker(symbol_count=1)
    monkeypatch.setattr(
        scanner_module,
        "ScanPerformanceTracker",
        lambda **_kwargs: spy,
    )

    working = _mocked_controller(tmp_path)
    working_output = working.run_market_scan(request=request)
    performance = working_output["performance"]
    snapshot_path = Path(working_output["performance_summary_path"])
    persisted = JsonStorage(snapshot_path).load()

    assert persisted["performance"] == performance
    assert persisted["performance_summary_path"] == str(snapshot_path)
    assert performance["completed_at"]
    assert performance["phases"]["telegram_ms"] >= 0
    assert performance["phases"]["persistence_ms"] >= 0
    assert performance["phases"]["retention_ms"] >= 0
    assert (
        sum(performance["exclusive_phases"].values())
        <= performance["total_ms"] + 0.01
    )
    assert performance["counters"]["mt5_copy_rates_calls"] == 4
    assert performance["counters"]["mt5_full_history_calls"] == 4
    assert performance["counters"]["macro_context_cache_misses"] == 1
    assert performance["counters"]["macro_global_fetches"] == 1
    assert performance["counters"]["telegram_candidates"] == 0
    assert (
        performance["counters"]["telegram_skipped_non_candidates"]
        == 1
    )
    assert performance["counters"]["analysis_documents_written"] == 1
    assert set(performance["counters"]) == set(COUNTER_NAMES)
    assert set(PHASE_NAMES) <= set(spy.started_phases)
    assert set(PHASE_NAMES) <= set(spy.ended_phases)
    assert "telegram_candidates" in spy.incremented_counters
    assert "analysis_documents_written" in spy.incremented_counters
    encoded = json.dumps(performance, sort_keys=True)
    assert "super-secret-token" not in encoded
    assert "secret-chat-id" not in encoded
    summary_event = next(
        event
        for event in working.observability.events
        if event["event_type"] == "SCAN_PERFORMANCE_SUMMARY"
    )
    assert (
        summary_event["payload"]["counters"]["telegram_requests"]
        == 0
    )
    assert summary_event["payload"]["phases"]["telegram_ms"] >= 0

    class BrokenTracker:
        def __init__(self, **_kwargs):
            raise RuntimeError("telemetry unavailable")

    monkeypatch.setattr(scanner_module, "ScanPerformanceTracker", BrokenTracker)
    broken = _mocked_controller(tmp_path)
    broken_output = broken.run_market_scan(request=request)

    assert _strip_telemetry(broken_output) == _strip_telemetry(working_output)
    assert "performance" not in broken_output


def test_real_counter_call_sites_record_actual_attempts(
    monkeypatch,
) -> None:
    tracker = ScanPerformanceTracker()
    mt5 = MT5Service()
    fake_mt5_module = SimpleNamespace(symbol_select=lambda *_args: True)
    monkeypatch.setitem(__import__("sys").modules, "MetaTrader5", fake_mt5_module)
    monkeypatch.setattr(mt5, "load_ohlcv", lambda *_args, **_kwargs: [])

    mt5.load_primary_timeframes(
        "EURUSD",
        {"D1": 10, "H4": 10, "H1": 10, "M15": 10},
        performance_tracker=tracker,
    )

    summary = tracker.finalize()
    assert summary["counters"]["mt5_copy_rates_calls"] == 4
    assert summary["counters"]["mt5_full_history_calls"] == 4
    assert summary["counters"]["mt5_tail_calls"] == 0


def test_macro_counter_call_sites_record_cache_network_and_ai_attempts(
    monkeypatch,
) -> None:
    tracker = ScanPerformanceTracker()
    downloads: list[str] = []

    def downloader(ticker, **_kwargs):
        downloads.append(ticker)
        return SimpleNamespace(empty=True)

    monkeypatch.setattr(
        market_data_module,
        "_fetch_via_requests",
        lambda *_args, **_kwargs: None,
    )
    fetch_macro_correlation_context(
        downloader=downloader,
        force_refresh=True,
        performance_tracker=tracker,
    )

    news = NewsService()
    cached_context = {"events": []}
    news._tier_scores_cache["EUR/USD_True"] = cached_context
    assert news.latest_macro_context(
        "EUR/USD",
        performance_tracker=tracker,
    ) is cached_context

    news._tier_scores_cache.clear()
    monkeypatch.setattr(
        news._ff_client,
        "calendar_events",
        lambda _currencies: {
            "events": [],
            "source": "fixture",
            "warning": "",
        },
    )
    monkeypatch.setattr(news, "_get_headlines", lambda *_args: [])
    monkeypatch.setattr(news, "_latest_official_statements", lambda: [])
    monkeypatch.setattr(news, "_macro_themes", lambda *_args: [])
    monkeypatch.setattr(news, "_geopolitical_hotspots", lambda *_args: [])
    monkeypatch.setattr(
        news,
        "_compute_macro_tiers",
        lambda *_args, **_kwargs: {
            "alignment": {"buy": 15, "sell": 15},
            "reasons": {"buy": [], "sell": []},
            "tier1": {"detail": {}},
            "tier2": {},
            "tier3": {"detail": {}},
            "raw_total": {"buy": 15, "sell": 15},
            "macro_v2": {},
        },
    )
    monkeypatch.setattr(news, "_macro_data_quality", lambda *_args: 1.0)
    monkeypatch.setattr(
        news,
        "_macro_data_quality_detail",
        lambda **_kwargs: {},
    )
    news.latest_macro_context(
        "EUR/USD",
        performance_tracker=tracker,
    )

    ai = SimpleNamespace(analyze=lambda *_args, **_kwargs: "hawkish")
    assert news._ai_currency_stance(
        "CHF",
        ["SNB signals tighter policy"],
        ai,
        performance_tracker=tracker,
    ) == "hawkish"

    summary = tracker.finalize()
    counters = summary["counters"]
    assert len(downloads) == 4
    assert counters["yfinance_download_calls"] == 4
    assert counters["macro_global_fetches"] == 4
    assert counters["macro_context_cache_hits"] == 1
    assert counters["macro_context_cache_misses"] == 1
    assert counters["ai_stance_calls"] == 1


def test_news_phase_call_sites_close_when_provider_raises(
    monkeypatch,
) -> None:
    pair_tracker = _SpyTracker()
    news = NewsService()
    monkeypatch.setattr(
        news._ff_client,
        "calendar_events",
        lambda _currencies: (_ for _ in ()).throw(
            RuntimeError("calendar unavailable")
        ),
    )

    context = news.latest_macro_context(
        "EUR/USD",
        performance_tracker=pair_tracker,
    )

    assert pair_tracker.started_phases.count("macro_pair_build") == 1
    assert pair_tracker.ended_phases.count("macro_pair_build") == 1
    source_freshness = context["macro_cache"]["source_freshness"]
    assert source_freshness["source_status"]["calendar"]["status"] == (
        "unavailable"
    )

    preload_tracker = _SpyTracker()
    preload_news = NewsService()
    monkeypatch.setattr(
        preload_news,
        "_get_global_macro_snapshot",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("news unavailable")
        ),
    )

    with pytest.raises(RuntimeError, match="news unavailable"):
        preload_news.preload_macro_contexts(
            ["EUR/USD"],
            performance_tracker=preload_tracker,
        )

    assert preload_tracker.started_phases.count("macro_global_fetch") == 1
    assert preload_tracker.ended_phases.count("macro_global_fetch") == 1


def test_telegram_counters_follow_actual_http_attempts(monkeypatch) -> None:
    tracker = ScanPerformanceTracker()
    service = TelegramAlertService()

    def send(_token, chat_id, _message):
        if chat_id == "chat-fail":
            raise RuntimeError("network")

    monkeypatch.setattr(service, "_send_message", send)
    candidates = [{"symbol": "EUR/USD", "candidate_status": "READY_NOW"}]
    recipients = ["chat-ok", "chat-fail"]

    result = service.send_order_alerts(
        candidates,
        bot_token="token",
        chat_ids=recipients,
        performance_tracker=tracker,
    )
    summary_sent = service.send_summary_alert(
        [],
        candidates=candidates,
        bot_token="token",
        chat_ids=recipients,
        timestamp="2026-07-31T00:00:00+00:00",
        performance_tracker=tracker,
    )

    counters = tracker.finalize()["counters"]
    assert result.attempted == 2
    assert len(result.errors) == 1
    assert summary_sent == 1
    assert counters["telegram_requests"] == 4
    assert counters["telegram_errors"] == 2
