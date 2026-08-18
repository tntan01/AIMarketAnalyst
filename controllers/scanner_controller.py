from __future__ import annotations

import os
import hashlib
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from dataclasses import asdict, replace
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from functools import wraps
from math import isfinite
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any

from PyQt6.QtCore import QThread

from config.paths import app_data_dir
from core.scanner import ScannerRequest  # retained request model (legacy row helpers re-platformed; see C2b)
from core.scanner_ai_auditor import (
    build_ai_setup_audit_prompt,
    parse_ai_setup_audit,
)
from core.scanner_composition import AccountState, JournalState, PortfolioState
from core.scanner_live_producers import (
    build_live_market_safety_context,
    compute_live_volatility_ratio,
    derive_live_analysis,
)
from core.scanner_v4_models import (
    READY_NOW,
    WAITING_CONFIRMATION,
    WATCH_ZONE,
    BLOCKED,
    DATA_UNAVAILABLE,
)
from core.scanner_release import run_pair_from_live
from core.scanner_order_policy import (
    DEFAULT_RUNTIME_ORDER_POLICY,
    OrderPolicyLoadError,
    RuntimeOrderPolicy,
    load_runtime_order_policy,
)
from core.scanner_ui_adapter import (
    ANALYSIS_OK,
    AdapterContractError,
    blocked_ui_row,
    build_scanner_output,
    pair_to_ui_row,
    scanner_summary,
)
from core.backtest_config import serialize_backtest_config
from core.chart_payload import build_chart_payload
from core.execution_revalidation_engine import revalidate_execution
from core.portfolio_risk_engine import evaluate_portfolio_risk
from core.scanner_session_review import build_market_brief_prompt
from core.scanner_observability import (
    SCANNER_OBSERVABILITY_VERSION,
    attach_row_observability,
    build_analysis_document,
    create_scan_context,
    input_timestamps_from_candles,
    row_identity,
)
from core.scanner_performance import (
    ScanPerformanceTracker,
    safe_performance_call as _record_performance,
    safe_performance_phase,
)
from core.scan_health import build_scan_health_report
from core.risk_engine import AnalysisInput, contract_size_override_for_symbol, position_sizing, recalc_execution_lot, calculate_current_effective_rr
from services.ai_service import AIProviderConfig, AIService
from services.data_provider import ProviderNotReadyError
from services.journal_converters import _parse_utc
from services.journal_service import JournalService
from services.market_data_service import fetch_macro_correlation_context
from services.mt5_service import MT5HistoryCacheIdentity, MT5Service
from services.news_service import NewsService
from services.observability_service import (
    StructuredObservabilityService,
    structured_observability,
)
from services.scan_health_service import (
    ScanHealthService,
    scan_health_service as default_scan_health_service,
)
from services.runtime_retention_service import RuntimeRetentionService
from services.scanner_job_state import ScannerJobState
from services.scanner_persistence_service import (
    PERSISTENCE_FULL,
    ScannerPersistenceService,
    atomic_json_save,
    persist_performance_summary,
    summary_row,
)
from services.settings_service import SettingsService
from services.telegram_alert_service import TelegramAlertService
from workers.scanner_worker import ScannerWorker

# Guards race-free creation of the per-instance scan lock for test doubles that
# bypass __init__ (object.__new__). Real controllers create the lock in __init__.
_SCAN_LOCK_CREATION_GUARD = RLock()

# Bounded budget the app waits for the aftercare persistence job before it
# marks the job interrupted and exits (mục 19.2).
AFTERCARE_SHUTDOWN_WAIT_SECONDS = 20.0


def _serialized_execution(method):
    """Serialize live order checks so concurrent callers share fresh state."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._execution_lock:
            return method(self, *args, **kwargs)

    return wrapper


def _forward_order_comment(row_id: str, fallback: str) -> str:
    """Return an MT5-safe correlation comment for Scanner forward evidence."""

    normalized = str(row_id or "").strip()
    if not normalized:
        return str(fallback or "AMA")[:31]
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return f"AMA-FWD:{digest}"


def _run_in_performance_phase(
    tracker: object | None,
    phase_name: str,
    callback: Callable[..., Any],
    *args: object,
    **kwargs: object,
) -> Any:
    with safe_performance_phase(tracker, phase_name):
        return callback(*args, **kwargs)


# ---------------------------------------------------------------------------
# C2b — re-platform local helpers (never fabricate; read real Scanner sources)
# ---------------------------------------------------------------------------

# candidate_status -> the legacy scanner_group label run_market_scan maps for
# ``legacy_candidate_status``. Read from the real row candidate_status only.
_SCANNER_GROUP_BY_STATUS: dict[str, str] = {
    READY_NOW: "ready_now",
    WAITING_CONFIRMATION: "waiting_confirmation",
    WATCH_ZONE: "watch_zone",
    BLOCKED: "blocked",
    DATA_UNAVAILABLE: "data_unavailable",
}

# Statuses that make a row an auto-trade candidate (mirrors the adapter's
# AUTO_TRADE_CANDIDATE_STATUSES set copy for local convenience).
_AUTO_TRADE_STATUSES = {READY_NOW, WAITING_CONFIRMATION}


def _v4_candidate_status(row: dict[str, Any]) -> str:
    """Normalize a row's candidate_status to upper-case, failing closed."""
    value = str(row.get("candidate_status") or ("DATA_UNAVAILABLE" if row.get("candidate_status") is None else "")).strip().upper()
    return value if value else DATA_UNAVAILABLE


def _is_structural_reject_row(row: object) -> bool:
    """There is no structural-reject; stable predicate for legacy callers.

    Always False for real Scanner rows (analysis_status is ``ok``), so the rows the
    adapter emits are never mislabelled as fast-path rejects.
    """
    return bool(
        isinstance(row, dict)
        and str(row.get("analysis_status", "") or "").strip().lower()
        == "structural_reject"
    )


def _find_scenario_for_side(
    scenarios: object,
    side: str,
    fallback_to_first: bool = False,
) -> object:
    """Return the scenario whose side matches (scenario dicts carry ``side``)."""
    if not isinstance(scenarios, list):
        return None
    side = str(side or "").strip().lower()
    for scenario in scenarios:
        if isinstance(scenario, dict) and str(
            scenario.get("side") or scenario.get("type") or ""
        ).strip().lower() == side:
            return scenario
    if fallback_to_first and scenarios:
        return scenarios[0]
    return None


def _sort_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable sort (no legacy deletion import): real candidate_status + score_gap.

    Ranking order mirrors the locked status precedence; ties keep input
    order (stable). All sort keys are REAL current values the adapter emits.
    """
    _priority = {
        READY_NOW: 0,
        WAITING_CONFIRMATION: 1,
        WATCH_ZONE: 2,
        BLOCKED: 3,
        DATA_UNAVAILABLE: 4,
    }

    def _key(row: dict[str, Any]) -> tuple[int, float]:
        status = _v4_candidate_status(row)
        priority = _priority.get(status, 5)
        try:
            gap = float(row.get("score_gap") or 0.0)
        except (TypeError, ValueError):
            gap = 0.0
        return (priority, -gap)

    return sorted(rows, key=_key)


def _order_proposal(row: dict[str, Any]) -> dict[str, Any] | None:
    """Build the executable-order proposal from the row's order payload.

    Uses ONLY real Scanner fields (``candidate_order_payload`` + row identity).  The
    payload tracks entry/SL/TP from the candidate's selected-side plan; volume
    is re-computed at dispatch by ``execute_order_candidate``. Returns None when
    there is no real payload (never fabricates an order intent).
    """
    payload = row.get("candidate_order_payload")
    if not isinstance(payload, dict):
        return None
    symbol = str(row.get("symbol") or "")
    broker_symbol = str(row.get("broker_symbol") or "").strip() or symbol
    side = str(payload.get("side") or "").strip()
    stop_loss = payload.get("stop_loss")
    take_profit = payload.get("take_profit")
    if not symbol or side.lower() not in {"buy", "sell"}:
        return None
    proposal: dict[str, Any] = {
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "side": side,
        "entry_price": payload.get("entry"),
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "volume": payload.get("volume"),
        "scan_id": row.get("scan_id", ""),
        "row_id": row.get("row_id", ""),
        "settings_hash": row.get("settings_hash", ""),
        "setup_score": payload.get("setup_score"),
        "required_min_rr": payload.get("risk_reward_ratio"),
        "scorer_version": payload.get("scoring_version"),
        "ranking_version": payload.get("feature_version"),
    }
    return proposal


def _consecutive_losses(closed_trades: object) -> int | None:
    """Trailing consecutive losing trades from real closed_trades.

    ``closed_trades`` is newest-first; counts contiguous losses via the REAL
    ``result_r`` / ``result_pct`` fields.  Unreadable rows are handled exactly
    like the live account guard (``core/account_guard.py``): a missing or
    non-numeric result counts as breakeven (not a loss, so it BREAKS the
    streak), and non-dict rows are skipped.  The journal contains MT5-history
    rows without an R value; failing closed on them would cap every scan
    forever, which the legacy guard never did.  Returns ``None`` only when the
    list itself is unreadable.
    """
    if not isinstance(closed_trades, list):
        return None
    count = 0
    for trade in closed_trades:
        if not isinstance(trade, dict):
            continue
        result = trade.get("result_r", trade.get("result_pct"))
        try:
            value = float(result or 0.0)
        except (TypeError, ValueError):
            value = 0.0
        if value < 0:
            count += 1
        else:
            break
    return count


# Owner decision (2026-08-15): the journal-gate drawdown window is the most
# recent 90 days.  This constant exists only because the owner explicitly chose
# this window — it is not derived from any other codebase value.
JOURNAL_DRAWDOWN_WINDOW_DAYS = 90


def compute_recent_drawdown_ratio(
    closed_trades: object,
    *,
    now_utc: datetime,
    risk_percent: float,
    window_days: int = JOURNAL_DRAWDOWN_WINDOW_DAYS,
) -> float | None:
    """Equity-curve drawdown over the trailing ``window_days`` (fail-closed).

    The curve follows the codebase's REAL ``result_r`` convention (same field
    ``journal_converters.build_performance_summary`` builds its curve from —
    ``result_pct`` is a PRICE-move percent and must not feed an account curve).
    Like that summary, rows without a readable ``result_r`` (MT5-history rows
    lacking entry/SL) never enter the R curve.  Each in-window closed trade
    compounds, in chronological order,

        ``equity *= 1 + risk_percent/100 * result_r``

    and the returned ratio is ``max((peak - equity) / peak)`` clamped to [0, 1].
    No readable closed trade inside the window -> ``0.0`` (truthful: no
    measurable trading happened, so no measurable drawdown happened).
    Structurally unreadable input (not a list, a non-dict row, an unparseable
    ``closed_at``) -> ``None`` so the gate fails closed instead of guessing.
    """
    if not isinstance(closed_trades, list):
        return None
    cutoff = now_utc - timedelta(days=window_days)
    in_window: list[tuple[datetime, float]] = []
    for trade in closed_trades:
        if not isinstance(trade, dict):
            return None
        closed_at = _parse_utc(trade.get("closed_at"))
        if closed_at is None:
            return None
        if closed_at < cutoff:
            continue
        result = trade.get("result_r")
        try:
            result_value = float(result) if result is not None else None
        except (TypeError, ValueError):
            result_value = None
        if result_value is None or not isfinite(result_value):
            # No readable R -> the row cannot enter the R curve (same
            # convention as build_performance_summary).
            continue
        in_window.append((closed_at, result_value))
    if not in_window:
        return 0.0
    in_window.sort(key=lambda item: item[0])
    equity = 1.0
    peak = 1.0
    drawdown = 0.0
    risk_fraction = float(risk_percent) / 100.0
    for _, result_value in in_window:
        equity *= 1.0 + risk_fraction * result_value
        if equity <= 0:
            # The account cannot lose more than everything: total drawdown.
            return 1.0
        if equity > peak:
            peak = equity
        current = (peak - equity) / peak
        if current > drawdown:
            drawdown = current
    return min(max(drawdown, 0.0), 1.0)


def _exposure_ratio(margin: object, balance: object) -> float | None:
    """Portfolio exposure = used margin ÷ balance (owner-locked semantics).

    Both numbers come from the same MT5 ``account_info()`` snapshot, hence the
    same account currency.  Fail-closed: any missing/non-numeric value or a
    non-positive balance returns ``None`` (never an invented ratio).
    """
    if margin is None or balance is None:
        return None
    try:
        margin_value = float(margin)
        balance_value = float(balance)
    except (TypeError, ValueError):
        return None
    if not isfinite(margin_value) or not isfinite(balance_value):
        return None
    if balance_value <= 0 or margin_value < 0:
        return None
    return margin_value / balance_value


def _open_positions(scan_portfolio: object) -> int | None:
    """Open-position count from the REAL portfolio snapshot (fail-closed).

    Replaces the old probe of ``open_positions_count`` — a method that never
    existed anywhere and therefore always produced ``None``.
    """
    if scan_portfolio is None or not bool(
        getattr(scan_portfolio, "available", False)
    ):
        return None
    positions = getattr(scan_portfolio, "positions", None)
    if positions is None:
        return None
    return len(positions)


class ScannerController:
    def __init__(
        self,
        settings_service: SettingsService | None = None,
        mt5: MT5Service | None = None,
        news_service: NewsService | None = None,
        telegram_service: TelegramAlertService | None = None,
        journal_service: JournalService | None = None,
        orders_screen = None,
        order_management_service = None,
        observability_service: StructuredObservabilityService | None = None,
        scan_health_service: ScanHealthService | None = None,
        retention_service: RuntimeRetentionService | None = None,
        job_state: ScannerJobState | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.mt5: MT5Service = mt5 or MT5Service()
        self.news_service = news_service or NewsService()
        self.telegram_service = telegram_service or TelegramAlertService()
        self.journal_service = journal_service or JournalService()
        self.order_management_service = order_management_service
        # Retained only as a source-compatible attribute for older callers.
        # Production auto-tracking never invokes QWidget methods from workers.
        self.orders_screen = orders_screen
        self.observability = observability_service or structured_observability
        self.scan_health = scan_health_service or default_scan_health_service
        self.retention = retention_service or RuntimeRetentionService()
        self._job_state = job_state or ScannerJobState(
            runtime_root=app_data_dir()
        )
        self._execution_lock = RLock()
        self._active_scan_id: str | None = None
        self._active_scan_lock = RLock()
        self._active_order_policy: RuntimeOrderPolicy = (
            DEFAULT_RUNTIME_ORDER_POLICY
        )

    def _scan_lock(self) -> RLock:
        """Return the one per-instance scan lock (mục 12.3, Phase 5).

        Real controllers create the lock in ``__init__``. Test doubles built via
        ``object.__new__`` get one here under a module guard so two concurrent
        callers can never create two independent locks and both acquire.
        """
        lock = getattr(self, "_active_scan_lock", None)
        if lock is not None:
            return lock
        with _SCAN_LOCK_CREATION_GUARD:
            lock = getattr(self, "_active_scan_lock", None)
            if lock is None:
                lock = RLock()
                self._active_scan_lock = lock
        return lock

    def _try_acquire_scan(self, scan_id: str) -> bool:
        """Non-blocking controller-level guard against overlapping core scans."""
        acquired, _active_owner = self._try_acquire_scan_with_owner(scan_id)
        return acquired

    def _try_acquire_scan_with_owner(
        self, scan_id: str
    ) -> tuple[bool, str | None]:
        """Try to acquire and atomically capture the rejecting owner, if any."""
        with self._scan_lock():
            active_owner = getattr(self, "_active_scan_id", None)
            if active_owner is not None:
                return False, active_owner
            self._active_scan_id = scan_id
            return True, None

    def _release_scan(self, scan_id: str) -> None:
        with self._scan_lock():
            if getattr(self, "_active_scan_id", None) == scan_id:
                self._active_scan_id = None

    def _active_scan(self) -> str | None:
        with self._scan_lock():
            return getattr(self, "_active_scan_id", None)

    def _scanner_job_state(self) -> ScannerJobState:
        state = getattr(self, "_job_state", None)
        if state is not None:
            return state
        state = ScannerJobState(runtime_root=app_data_dir())
        self._job_state = state
        return state

    def create_scan_worker(self, request: ScannerRequest) -> tuple[QThread, ScannerWorker]:
        thread = QThread()
        split_aftercare = bool(
            request.feature_flags.get("scanner_core_result_early", False)
        )
        worker = ScannerWorker(
            self.run_market_scan,
            {"request": request},
            split_aftercare=split_aftercare,
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        return thread, worker

    def run_market_scan(
        self,
        *,
        request: ScannerRequest,
        _progress_callback: Callable[[int, str], None] | None = None,
        _core_ready_callback: Callable[[dict[str, Any]], None] | None = None,
        _aftercare_progress_callback: Callable[[int, str], None] | None = None,
        _return_aftercare_delta: bool = False,
    ) -> dict[str, Any]:
        progress = _progress_callback or (lambda _percent, _message: None)
        try:
            performance: object | None = ScanPerformanceTracker(
                symbol_count=len(request.symbols)
            )
        except Exception:
            performance = None
        _record_performance(performance, "start_phase", "settings")
        aftercare_progress = (
            _aftercare_progress_callback
            or (lambda _percent, _message: None)
        )
        settings = self.settings_service.load()
        effective_risk_percent = min(
            max(float(request.risk_percent), 0.0),
            max(float(settings.trading.max_risk_percent), 0.0),
        )
        request = replace(request, risk_percent=effective_risk_percent)
        scan_context = create_scan_context(settings, request)
        _record_performance(performance, "end_phase", "settings")
        _record_performance(performance, "set_scan_id", scan_context.scan_id)
        acquired, active = self._try_acquire_scan_with_owner(scan_context.scan_id)
        if not acquired:
            raise RuntimeError(
                f"Scanner đang chạy (scan {active}). "
                "Hãy chờ lần quét hiện tại hoàn tất."
            )
        self._active_performance_tracker = performance
        try:
            self._emit_observability(
                "SCAN_STARTED",
                scan_id=scan_context.scan_id,
                payload={
                    "request_hash": scan_context.request_hash,
                    "settings_hash": scan_context.settings_hash,
                    "symbols": list(request.symbols),
                    "smc_scorer_version": scan_context.smc_scorer_version,
                    "smc_domain_version": scan_context.smc_domain_version,
                },
            )
            progress(8, "Đang kiểm tra kết nối dữ liệu...")
            _record_performance(performance, "start_phase", "readiness")
            try:
                status = self.mt5.ensure_ready(require_login=True)
            except ProviderNotReadyError as exc:
                status = exc.status
                self._emit_observability(
                    "DATA_FETCH_FAILURE",
                    scan_id=scan_context.scan_id,
                    severity="ERROR",
                    payload={
                        "stage": "connection",
                        "provider": status.provider_name,
                        "connected": status.connected,
                        "logged_in": status.logged_in,
                    },
                )
                raise
            finally:
                _record_performance(performance, "end_phase", "readiness")
            mt5_history_cache_identity = (
                MT5HistoryCacheIdentity.from_connection_status(status)
            )
            self._active_mt5_history_cache_identity = mt5_history_cache_identity
            # Owner order policy (Bước 13 "bước nối"): fail-closed load. A broken
            # config never crashes the scan — it falls back to the default policy
            # whose order_enabled is False, keeping every order blocked.
            try:
                self._active_order_policy = load_runtime_order_policy()
            except OrderPolicyLoadError as exc:
                self._active_order_policy = DEFAULT_RUNTIME_ORDER_POLICY
                self._emit_observability(
                    "ORDER_POLICY_FAULT",
                    scan_id=scan_context.scan_id,
                    severity="ERROR",
                    payload={
                        "path": exc.path,
                        "detail": exc.detail,
                        "order_enabled": False,
                    },
                )
            _record_performance(performance, "start_phase", "account_portfolio")
            try:
                mt5_balance = self.mt5.account_balance()
                if mt5_balance is None:
                    self._emit_observability(
                        "DATA_FETCH_FAILURE",
                        scan_id=scan_context.scan_id,
                        severity="ERROR",
                        payload={"stage": "account_balance"},
                    )
                    raise RuntimeError("Không lấy được số dư từ tài khoản.")
                scan_portfolio = None
                try:
                    scan_portfolio = self.mt5.portfolio_snapshot()
                    portfolio_state = scan_portfolio.to_dict()
                except Exception as exc:
                    portfolio_state = {
                        "available": False,
                        "reason_codes": ["PORTFOLIO_STATE_UNAVAILABLE"],
                        "reason": str(exc),
                    }
            finally:
                _record_performance(performance, "end_phase", "account_portfolio")

            core_output, ctx = self._run_market_scan_core(
                request,
                progress,
                scan_context=scan_context,
                settings=settings,
                mt5_balance=mt5_balance,
                portfolio_state=portfolio_state,
                scan_portfolio=scan_portfolio,
            )
            split = bool(
                request.feature_flags.get("scanner_core_result_early", False)
            )
            if split and _core_ready_callback is not None:
                _core_ready_callback(core_output)
            if split:
                try:
                    delta = self._run_market_scan_aftercare(
                        core_output,
                        request,
                        aftercare_progress,
                        ctx=ctx,
                        fatal_errors=False,
                    )
                except Exception as exc:
                    # Aftercare must never lose the already-emitted core result.
                    self._emit_observability(
                        "AFTERCARE_FAILURE",
                        scan_id=scan_context.scan_id,
                        severity="ERROR",
                        payload={"reason": str(exc)},
                    )
                    delta = {
                        "scan_id": scan_context.scan_id,
                        "aftercare_error": str(exc),
                    }
                if _return_aftercare_delta:
                    return delta
                return {**core_output, **delta}
            # Legacy flow (scanner_core_result_early=false): no early core
            # signal, aftercare errors fail the scan exactly like the old path.
            delta = self._run_market_scan_aftercare(
                core_output,
                request,
                aftercare_progress,
                ctx=ctx,
                fatal_errors=True,
            )
            return {**core_output, **delta}
        finally:
            self._active_performance_tracker = None
            self._active_mt5_history_cache_identity = None
            self._release_scan(scan_context.scan_id)

    def _run_market_scan_core(
        self,
        request: ScannerRequest,
        progress: Callable[[int, str], None],
        *,
        scan_context,
        settings,
        mt5_balance,
        portfolio_state,
        scan_portfolio=None,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        performance = getattr(self, "_active_performance_tracker", None)
        mt5_history_cache_identity = getattr(
            self, "_active_mt5_history_cache_identity", None
        )
        bars_by_timeframe = {
            "D1": settings.advanced.d1_bars,
            "H4": settings.advanced.h4_bars,
            "H1": settings.advanced.h1_bars,
        }

        # ---- Kick off background I/O immediately (runs while we do MT5 setup) ----
        active_ai = settings.ai.active_provider()
        ai_svc = None
        if active_ai and active_ai.api_key:
            ai_svc = AIService(AIProviderConfig(
                provider=active_ai.provider,
                model=active_ai.model,
                api_key=active_ai.api_key,
                base_url=active_ai.base_url,
            ))

        with ThreadPoolExecutor(max_workers=2) as _bg:
            _corr_future = _bg.submit(
                _run_in_performance_phase,
                performance,
                "correlation",
                fetch_macro_correlation_context,
            )
            _preload_future = _bg.submit(
                self.news_service.preload_macro_contexts,
                request.symbols,
                progress_callback=lambda p, m: progress(min(14 + p // 10, 18), m),
                ai_service=ai_svc,
                performance_tracker=performance,
            )

            progress(12, "Đang đọc danh sách mã giao dịch...")
            _record_performance(performance, "start_phase", "available_symbols")
            available_symbols = self.mt5.available_symbols(market_watch_only=True)
            _record_performance(performance, "end_phase", "available_symbols")

            # Wait for background I/O to complete before proceeding.
            progress(14, "Đang tải dữ liệu thị trường Mỹ...")
            try:
                correlation_context = _corr_future.result()
            except Exception as exc:
                self._emit_observability(
                    "DATA_FETCH_FAILURE",
                    scan_id=scan_context.scan_id,
                    severity="ERROR",
                    payload={
                        "stage": "macro_correlation_context",
                        "reason": str(exc),
                    },
                )
                raise
            try:
                _preload_future.result()
            except Exception as exc:
                self._emit_observability(
                    "DATA_FETCH_FAILURE",
                    scan_id=scan_context.scan_id,
                    severity="ERROR",
                    payload={
                        "stage": "macro_news_preload",
                        "reason": str(exc),
                    },
                )
                raise

        rows: list[dict[str, Any]] = []

        freshness_raw = self.news_service.macro_freshness_status()
        freshness = freshness_raw if isinstance(freshness_raw, dict) else {"confidence_multiplier": 1.0}
        freshness_multiplier = float(freshness.get("confidence_multiplier", 1.0))
        closed_trades = self.journal_service.list_closed_trades_for_account_guard() if self.journal_service else []
        account_guard_settings = {
            "max_daily_loss_pct": float(settings.trading.max_daily_loss_pct),
            "max_weekly_loss_pct": float(settings.trading.max_weekly_loss_pct),
            "max_consecutive_losses": int(settings.trading.max_consecutive_losses),
            "max_open_risk_pct": float(settings.trading.max_open_risk_pct),
            "trader_timezone": settings.display.timezone or "Asia/Ho_Chi_Minh",
        }

        progress(19, "Đang tải dữ liệu giá từ MT5...")
        total = max(1, len(request.symbols))

        analysis_input_kwargs: dict[str, Any] = {
            "account_balance": mt5_balance,
            "risk_percent": request.risk_percent,
            "account_currency": settings.trading.account_currency,
            "lot_step": settings.trading.lot_step,
            "minimum_lot": settings.trading.minimum_lot,
            "timezone_name": request.timezone_name,
        }

        # ---- C2b: build the account/portfolio/journal state ONCE (main thread)
        # and thread it through the fetch packet (never fabricate; fail-closed).
        v4_consecutive_losses = _consecutive_losses(closed_trades)
        # Account numbers straight from MT5 account_info: free margin feeds the
        # account gate; used margin ÷ balance feeds the portfolio exposure gate
        # (owner-locked semantics).  Missing values stay None -> gate UNKNOWN.
        try:
            v4_account_status = self.mt5.mt5_connection_status()
        except Exception:
            v4_account_status = None
        v4_free_margin = getattr(v4_account_status, "free_margin", None)
        v4_exposure_ratio = _exposure_ratio(
            getattr(v4_account_status, "margin", None), mt5_balance
        )
        v4_open_positions = _open_positions(scan_portfolio)
        v4_account = AccountState(free_margin=v4_free_margin, required_margin=None)
        v4_portfolio = PortfolioState(
            open_positions=v4_open_positions, exposure_ratio=v4_exposure_ratio
        )
        v4_journal = JournalState(
            consecutive_losses=v4_consecutive_losses,
            recent_drawdown_ratio=compute_recent_drawdown_ratio(
                closed_trades,
                now_utc=datetime.now(timezone.utc),
                risk_percent=float(request.risk_percent),
            ),
        )

        # ---- Phase 1: fetch MT5 data sequentially (MT5 works best single-threaded) ----
        _record_performance(performance, "start_phase", "mt5_fetch")
        packets: list[dict[str, Any] | None] = []
        for i, symbol in enumerate(request.symbols):
            progress(19 + int(i / total * 30), f"Đang tải dữ liệu {symbol} ({i + 1}/{total})...")
            symbol_fetch_started = perf_counter()
            try:
                pkt = _fetch_one_symbol_mt5(
                    symbol,
                    mt5=self.mt5,
                    available_symbols=available_symbols,
                    bars_by_timeframe=bars_by_timeframe,
                    news_service=self.news_service,
                    freshness=freshness,
                    ai_service=ai_svc,
                    performance_tracker=performance,
                    history_cache_enabled=bool(
                        request.feature_flags.get(
                            "scanner_mt5_history_cache",
                            False,
                        )
                    ),
                    history_cache_identity=mt5_history_cache_identity,
                    v4_account=v4_account,
                    v4_portfolio=v4_portfolio,
                    v4_journal=v4_journal,
                )
            except Exception as exc:
                pkt = None
                self._emit_observability(
                    "DATA_FETCH_FAILURE",
                    scan_id=scan_context.scan_id,
                    symbol=symbol,
                    severity="ERROR",
                    payload={"stage": "market_data", "reason": str(exc)},
                )
            finally:
                symbol_fetch_ms = round(
                    max(0.0, perf_counter() - symbol_fetch_started) * 1_000,
                    3,
                )
                _record_performance(
                    performance,
                    "record_symbol",
                    symbol,
                    fetch_ms=symbol_fetch_ms,
                )
            packets.append(pkt)
        _record_performance(performance, "end_phase", "mt5_fetch")

        # ---- Phase 2: analyze all symbols in parallel (CPU-only, no MT5) ----
        _record_performance(performance, "start_phase", "analysis_wall")
        progress(49, "Đang phân tích kỹ thuật các cặp tiền...")
        analyze_kwargs = {
            "correlation_context": correlation_context,
            "freshness_multiplier": freshness_multiplier,
            "contract_size_overrides": settings.trading.contract_size_override,
            "analysis_input_kwargs": analysis_input_kwargs,
            "closed_trades": closed_trades,
            "account_guard_settings": account_guard_settings,
            "order_policy": getattr(
                self, "_active_order_policy", DEFAULT_RUNTIME_ORDER_POLICY
            ),
            "scanner_fast_tier1": bool(
                request.feature_flags.get("scanner_fast_tier1", False)
            ),
            "ai_service": ai_svc,
        }

        with ThreadPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
            futures: dict[Any, int] = {}
            for i, pkt in enumerate(packets):
                symbol = request.symbols[i]
                if pkt is None:
                    row = blocked_ui_row(symbol, "Không tìm thấy mã broker.")
                    row["input_timestamps"] = {}
                    rows.append(row)
                    self._emit_observability(
                        "DATA_FETCH_FAILURE",
                        scan_id=scan_context.scan_id,
                        symbol=symbol,
                        severity="WARNING",
                        payload={
                            "stage": "symbol_resolution_or_market_data",
                            "reason": row.get("short_reason"),
                        },
                    )
                    continue
                futures[
                    ex.submit(
                        _analyze_one_symbol,
                        pkt,
                        thresholds=request.thresholds.get(symbol),
                        **analyze_kwargs,
                    )
                ] = i

            completed = 0
            for future in as_completed(futures):
                i = futures[future]
                symbol = request.symbols[i]
                completed += 1
                progress(49 + int(completed / total * 25), f"Đã phân tích {symbol} ({completed}/{total})...")
                try:
                    row = future.result()
                except Exception as exc:
                    row = blocked_ui_row(
                        symbol,
                        f"Lỗi không mong đợi: {exc}",
                        broker_symbol="",
                    )
                    row["analysis_error"] = True
                    row["input_timestamps"] = dict(
                        (
                            packets[i].get("input_timestamps", {})
                            if isinstance(packets[i], dict)
                            else {}
                        )
                    )
                    self._emit_observability(
                        "DATA_FETCH_FAILURE",
                        scan_id=scan_context.scan_id,
                        symbol=symbol,
                        severity="ERROR",
                        payload={"stage": "analysis", "reason": str(exc)},
                    )
                analysis_error = str(row.pop("_analysis_error", "") or "")
                if analysis_error:
                    row["analysis_error"] = True
                    self._emit_observability(
                        "DATA_FETCH_FAILURE",
                        scan_id=scan_context.scan_id,
                        symbol=symbol,
                        severity="ERROR",
                        payload={
                            "stage": "analysis_pipeline",
                            "reason": analysis_error,
                        },
                    )
                else:
                    row.setdefault("analysis_error", False)
                # Keep the resolved config for diagnostics.  Canonical branch
                # and safety fields are attached in _apply_scanner_filters.
                at_cfg = self._auto_trade_config(request, symbol)
                if at_cfg is not None:
                    row["auto_trade_config"] = dict(at_cfg)
                row["scan_id"] = scan_context.scan_id
                row["row_id"] = row_identity(
                    scan_context.scan_id,
                    row.get("symbol"),
                )
                row["settings_hash"] = scan_context.settings_hash
                _record_performance(
                    performance,
                    "record_symbol",
                    symbol,
                    analysis_ms=row.get("analysis_latency_ms", 0),
                    pipeline_route=row.get("pipeline_route", ""),
                )
                rows.append(row)

        _record_performance(performance, "end_phase", "analysis_wall")
        for row in rows:
            symbol = str(row.get("symbol", ""))
            row["legacy_candidate_status"] = {
                "ready_now": "READY_NOW",
                "waiting_confirmation": "WAITING_CONFIRMATION",
                "watch_zone": "WATCH_ZONE",
                "out_of_strategy": "OUT_OF_STRATEGY",
                "blocked": "BLOCKED",
            }.get(
                str(row.get("scanner_group", "") or "").lower(),
                (
                    "OUT_OF_STRATEGY"
                    if _is_structural_reject_row(row)
                    else "DATA_UNAVAILABLE"
                ),
            )
            at_cfg = self._auto_trade_config(request, symbol)
            if at_cfg is not None and "auto_trade_config" not in row:
                row["auto_trade_config"] = dict(at_cfg)
            row["scan_id"] = scan_context.scan_id
            row["row_id"] = row_identity(scan_context.scan_id, symbol)
            row["settings_hash"] = scan_context.settings_hash

        progress(74, "Đang áp dụng Strategy Router và execution filters...")
        _record_performance(performance, "start_phase", "candidate_filter")
        rows = self._apply_scanner_filters(rows, request)
        _record_performance(performance, "end_phase", "candidate_filter")
        _record_performance(performance, "start_phase", "observability")
        rows = [
            attach_row_observability(
                row,
                scan_context,
                portfolio_state=portfolio_state,
            )
            for row in rows
        ]
        for row in rows:
            self._emit_candidate_events(row, scan_context.scan_id)
        scan_health = build_scan_health_report(rows)
        _record_performance(performance, "end_phase", "observability")
        progress(78, "Đã xếp hạng lại candidate sau filters...")

        progress(90, "Đang dựng bảng kết quả quét...")
        output = build_scanner_output(rows, request, 0)  # ai_called=0 since audit is now manual
        output["persistence_mode"] = request.persistence_mode
        output["observability_version"] = SCANNER_OBSERVABILITY_VERSION
        output["scan_id"] = scan_context.scan_id
        output["scan_context"] = scan_context.to_dict()
        output["portfolio_state"] = portfolio_state
        output["scan_health"] = scan_health
        _record_performance(performance, "mark_core_ready")
        performance_snapshot = _record_performance(performance, "snapshot")
        if isinstance(performance_snapshot, dict):
            output["performance"] = performance_snapshot
        # Aftercare gets its own deep copy of rows: core_output["rows"] is the
        # immutable snapshot already handed to the UI, and no aftercare step may
        # mutate the object the UI is rendering (mục 11.3 / 19.3).
        ctx: dict[str, Any] = {
            "scan_context": scan_context,
            "settings": settings,
            "correlation_context": correlation_context,
            "freshness": freshness,
            "closed_trades": closed_trades,
            "rows": deepcopy(rows),
            "portfolio_state": portfolio_state,
            "performance": performance,
        }
        return output, ctx

    def _run_market_scan_aftercare(
        self,
        core_output: dict[str, Any],
        request: ScannerRequest,
        progress: Callable[[int, str], None],
        *,
        ctx: dict[str, Any],
        fatal_errors: bool = False,
    ) -> dict[str, Any]:
        scan_context = ctx["scan_context"]
        settings = ctx["settings"]
        rows = ctx["rows"]
        performance = ctx.get("performance")
        delta: dict[str, Any] = {}
        # The aftercare job starts before any slow external I/O, so an app
        # shutdown at ANY aftercare point either waits (bounded) for it or
        # leaves an "interrupted" marker (mục 19.2).  Durable markers are only
        # written when persistence is enabled.
        job_state = self._scanner_job_state()
        job_state.begin_aftercare(
            scan_context.scan_id,
            durable=request.persistence_mode != "none",
        )
        persistence_incomplete = False
        try:
            # Compact summary first: the core result is durable on disk before
            # market brief, Telegram or full persistence run.
            if request.persistence_mode != "none":
                progress(93, "Đang lưu snapshot quét...")
                try:
                    self._write_early_summary(core_output)
                except Exception as exc:
                    delta["snapshot_error"] = str(exc)
                    self._emit_observability(
                        "SNAPSHOT_WRITE_FAILURE",
                        scan_id=scan_context.scan_id,
                        severity="ERROR",
                        payload={"reason": str(exc)},
                    )

            # AI Market Brief (1 call, after all individual audits)
            _record_performance(performance, "start_phase", "market_brief")
            progress(94, "Đang tạo bản tin thị trường...")
            market_brief, market_brief_error = self._generate_market_brief(
                rows,
                correlation_context=ctx["correlation_context"],
                freshness=ctx["freshness"],
                settings=settings,
            )
            delta["market_brief"] = market_brief
            delta["market_brief_error"] = market_brief_error
            _record_performance(performance, "end_phase", "market_brief")

            if request.auto_trade_enabled:
                progress(95, "Đang kiểm tra và đặt lệnh tự động...")
                try:
                    delta["auto_trade_results"] = self._execute_auto_trades(
                        rows,
                        request,
                    )
                except Exception as exc:
                    if fatal_errors:
                        # Legacy flow: an auto-trade failure fails the whole scan.
                        raise
                    delta["auto_trade_error"] = str(exc)
                    delta["auto_trade_results"] = {
                        "enabled": True,
                        "attempted": 0,
                        "opened": 0,
                        "skipped": 0,
                        "errors": [str(exc)],
                        "orders": [],
                    }
                    self._emit_observability(
                        "AUTO_TRADE_FAILURE",
                        scan_id=scan_context.scan_id,
                        severity="ERROR",
                        payload={"reason": str(exc)},
                    )
            else:
                delta["auto_trade_results"] = {
                    "enabled": False,
                    "attempted": 0,
                    "opened": 0,
                    "skipped": 0,
                    "errors": [],
                    "orders": [],
                }

            try:
                delta["scan_health_metrics"] = self.scan_health.record_scan(
                    scan_id=scan_context.scan_id,
                    scan_health=core_output.get("scan_health", {}),
                    auto_trade_results=delta["auto_trade_results"],
                    closed_trades=ctx["closed_trades"],
                )
            except Exception as exc:
                delta["scan_health_error"] = str(exc)
                self._emit_observability(
                    "SCAN_HEALTH_FAILURE",
                    scan_id=scan_context.scan_id,
                    severity="ERROR",
                    payload={"reason": str(exc)},
                )

            progress(97, "Đang gửi cảnh báo Telegram...")
            try:
                delta["telegram_alerts"] = self._send_telegram_alerts(rows)
            except Exception as exc:
                if fatal_errors:
                    # Legacy flow: a Telegram failure fails the whole scan.
                    raise
                delta["telegram_error"] = str(exc)
                delta["telegram_alerts"] = {
                    "attempted": 0,
                    "sent": 0,
                    "errors": [str(exc)],
                    "summary_sent": 0,
                }
                self._emit_observability(
                    "TELEGRAM_ALERT_FAILURE",
                    scan_id=scan_context.scan_id,
                    severity="ERROR",
                    payload={"reason": str(exc)},
                )

            if request.persistence_mode != "none":
                progress(98, "Đang lưu snapshot quét...")
                try:
                    info = self.persist_scan(
                        {**core_output, **delta},
                        manage_job=False,
                    )
                    delta["snapshot_path"] = str(info["snapshot_path"])
                    delta["persistence"] = {
                        "mode": info["snapshot_mode"],
                        "manifest": info["snapshot_manifest"],
                        "write_count": info["snapshot_write_count"],
                        "duration_ms": info["snapshot_duration_ms"],
                        "errors": info["snapshot_errors"],
                        "status": info["snapshot_status"],
                    }
                    if info["snapshot_status"] != "completed":
                        persistence_incomplete = True
                    # The full write supersedes the early compact summary.
                    delta.pop("snapshot_error", None)
                except Exception as exc:
                    persistence_incomplete = True
                    delta["snapshot_error"] = str(exc)
                    self._emit_observability(
                        "SNAPSHOT_WRITE_FAILURE",
                        scan_id=scan_context.scan_id,
                        severity="ERROR",
                        payload={"reason": str(exc)},
                    )

            delta["scan_id"] = scan_context.scan_id
            performance_summary = _record_performance(performance, "finalize")
            if isinstance(performance_summary, dict):
                delta["performance"] = performance_summary
                snapshot_path = str(delta.get("snapshot_path", "") or "")
                if snapshot_path:
                    try:
                        delta["performance_summary_path"] = str(
                            persist_performance_summary(
                                Path(snapshot_path),
                                performance_summary,
                            )
                        )
                    except Exception as exc:
                        self._emit_observability(
                            "PERFORMANCE_SUMMARY_PERSIST_FAILURE",
                            scan_id=scan_context.scan_id,
                            severity="ERROR",
                            payload={"reason": str(exc)},
                        )
            self._emit_observability(
                "SCAN_PERFORMANCE_SUMMARY",
                scan_id=scan_context.scan_id,
                payload=(
                    performance_summary
                    if isinstance(performance_summary, dict)
                    else {}
                ),
            )
            self._emit_observability(
                "SCAN_COMPLETED",
                scan_id=scan_context.scan_id,
                payload={
                    "symbols_scanned": len(rows),
                    "summary": core_output.get("summary", {}),
                    "snapshot_path": delta.get("snapshot_path", ""),
                },
            )
        finally:
            # The job completes only after persistence, retention and the
            # performance summary rewrite finished.  Any failure (recorded
            # persistence error or a propagating exception) leaves an
            # interrupted marker instead.
            if persistence_incomplete or sys.exc_info()[0] is not None:
                job_state.mark_interrupted(
                    scan_context.scan_id,
                    reason=(
                        "persistence_error"
                        if persistence_incomplete
                        else "aftercare_error"
                    ),
                )
            else:
                job_state.complete_aftercare(scan_context.scan_id)
        return delta

    def _generate_market_brief(
        self,
        rows: list[dict[str, Any]],
        *,
        correlation_context: dict[str, Any],
        freshness: dict[str, Any],
        settings,
    ) -> tuple[str, str]:
        market_brief = ""
        market_brief_error = ""
        active_ai = settings.ai.active_provider()
        if active_ai and active_ai.api_key:
            try:
                brief_prompt = build_market_brief_prompt(
                    rows,
                    correlation_context=correlation_context,
                    freshness=freshness,
                )
                market_brief = AIService(
                    AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key, base_url=active_ai.base_url)
                ).analyze(brief_prompt, max_tokens=4000)
            except Exception as exc:
                market_brief_error = str(exc)
        elif not active_ai or not active_ai.api_key:
            market_brief_error = "Chưa cấu hình AI Provider hoặc API key trong Settings."
        return market_brief, market_brief_error

    @staticmethod
    def _auto_trade_config(request: ScannerRequest, symbol: str) -> dict[str, object] | None:
        """Return per-symbol auto-trade config, or None if not configured.

        Only symbols with backtest=true appear in symbol_auto_trade
        (built by scanner_screen).  Every entry is a valid Nhanh-1 config.
        """
        if not request.symbol_auto_trade:
            return None
        # Normalize symbol format: rows use "USDCHF", settings use "USD/CHF"
        cfg = request.symbol_auto_trade.get(symbol)
        if cfg is None and "/" not in symbol and len(symbol) == 6:
            # Try slash format: "USDCHF" -> "USD/CHF"
            slash_key = symbol[:3] + "/" + symbol[3:]
            cfg = request.symbol_auto_trade.get(slash_key)
        if cfg is None:
            return None
        # Preserve configured-branch semantics for malformed payloads so the
        # safety evaluator can fail closed instead of silently using defaults.
        return cfg if isinstance(cfg, dict) else {}

    def _apply_scanner_filters(
        self,
        rows: list[dict[str, Any]],
        request: ScannerRequest,
    ) -> list[dict[str, Any]]:
        """Annotate auto-trade/execution keys WITHOUT changing scanner decisions (C2b).

        Scanning and execution are deliberately separate in Phase 0 (unchanged).  The
        Rows from ``_analyze_one_symbol`` already carry the real candidate fields
        (``candidate_status``, ``selected_side``, ``auto_trade_candidate``,
        ``candidate_order_payload``, ``scanner_candidate_decision``) via
        ``pair_to_ui_row``.  This pass only annotates the legacy compatibility keys,
        reading them from the REAL candidate_status / reason_codes — never from any legacy
        deletion module, and failing closed to None/False where there is no equivalent.
        """
        for row in rows:
            candidate_status = _v4_candidate_status(row)
            is_auto_status = candidate_status in _AUTO_TRADE_STATUSES
            auto_trade_candidate = bool(row.get("auto_trade_candidate"))

            # Status discipline: READY_NOW / WAITING_CONFIRMATION can ONLY be
            # produced by a real routed candidate (pair_to_ui_row sets
            # auto_trade_candidate=True for genuine ready candidates). A row that
            # CLAIMS an auto-trade status but carries no real candidate is stale
            # or fabricated — demote it to DATA_UNAVAILABLE so it can never enter
            # the dispatch loop with an unsupported status (never trusts a stale
            # rank/status; never downgrades a genuine ready row).
            if is_auto_status and not auto_trade_candidate:
                candidate_status = DATA_UNAVAILABLE
                is_auto_status = False
                row["candidate_status"] = DATA_UNAVAILABLE
                row["selected_side"] = None
                row["auto_trade_candidate"] = False
                # Legacy composite rank has no current equivalent — reset to the
                # documented neutral so a stale rank is never preserved.
                row["opportunity_rank"] = None

            # Legacy keys with no current equivalent stay a documented neutral.
            row.setdefault("auto_trade_branch", None)
            row.setdefault("strategy_config_status", None)
            row.setdefault("direction_bias", None)
            # backtest-config status no longer exists.
            row["backtest_config_status"] = None
            # Candidate fields are authoritative already; keep them consistent but
            # never optimistic (a non-auto status can't become an order candidate).
            row["auto_trade_candidate"] = auto_trade_candidate and is_auto_status
            row["strategy_eligible"] = is_auto_status
            row["execution_ready"] = candidate_status == READY_NOW
            row["trade_allowed"] = (
                row["auto_trade_candidate"] and candidate_status == READY_NOW
            )
            row["auto_trade_selected_side"] = row.get("selected_side")
            row["auto_trade_reason_codes"] = list(row.get("reason_codes") or [])
            if not isinstance(row.get("scanner_candidate_decision"), dict):
                row["scanner_candidate_decision"] = {
                    "strategy": {
                        "reason_codes": [],
                        "score_value": None,
                        "setup_score": None,
                        "expected_effective_rr": None,
                    },
                    "reason_codes": list(row.get("reason_codes") or []),
                    "candidate_status": candidate_status,
                    "selected_side": row.get("selected_side"),
                }
            if not isinstance(row.get("candidate_order_payload"), dict):
                row["candidate_order_payload"] = None

        return _sort_rows(rows)

    @_serialized_execution
    def execute_order_candidate(
        self,
        proposal: dict[str, Any],
        *,
        risk_percent: float | None = None,
        comment: str = "AMA",
    ) -> dict[str, Any]:
        """Revalidate and execute one scan proposal through the shared gate.

        No rollout gating remains (removed 2026-08-15, fully live): the guard
        chain is execution snapshot → lot recalc → news blackout →
        portfolio/account guards → ``revalidate_execution`` →
        ``place_market_order``.
        """

        order = dict(proposal) if isinstance(proposal, dict) else {}
        symbol = str(order.get("symbol") or "--")
        broker_symbol = str(order.get("broker_symbol") or "").strip()
        side = str(order.get("side") or "").strip().lower()
        scan_id = str(order.get("scan_id") or "")
        row_id = str(order.get("row_id") or "")
        self._emit_observability(
            "ORDER_REQUEST",
            scan_id=scan_id,
            symbol=symbol,
            payload={
                "row_id": row_id,
                "broker_symbol": broker_symbol,
                "side": side,
                "setup_score": order.get("setup_score"),
                "required_min_rr": order.get("required_min_rr"),
                "backtest_config_id": order.get("backtest_config_id"),
                "scorer_version": order.get("scorer_version"),
                "ranking_version": order.get("ranking_version"),
            },
        )
        settings = self.settings_service.load()

        try:
            snapshot = self.mt5.execution_snapshot(broker_symbol)
        except Exception as exc:
            self._emit_observability(
                "EXECUTION_REVALIDATION_FAILURE",
                scan_id=scan_id,
                symbol=symbol,
                severity="ERROR",
                payload={
                    "row_id": row_id,
                    "stage": "execution_snapshot",
                    "reason": str(exc),
                },
            )
            raise
        try:
            portfolio_snapshot = self.mt5.portfolio_snapshot()
        except Exception:
            portfolio_snapshot = None
        execution_price = (
            snapshot.ask if side == "buy"
            else snapshot.bid if side == "sell"
            else None
        )

        # The lot calculation uses the fresh execution-side bid/ask, never the
        # scanner snapshot or entry-zone midpoint.
        try:
            stop_loss = float(order.get("stop_loss"))
            fallback_lot = float(order.get("volume") or 0.0)
            balance = float(
                portfolio_snapshot.account_balance
                if portfolio_snapshot is not None
                else 0.0
            )
            effective_risk = float(
                risk_percent
                if risk_percent is not None
                else settings.trading.default_risk_percent
            )
            contract_override = settings.trading.contract_size_override
            if isinstance(contract_override, dict):
                contract = float(contract_override.get(symbol, 100000))
            elif isinstance(contract_override, (int, float)) and contract_override > 0:
                contract = float(contract_override)
            else:
                contract = 100000.0
            quote_currency = (
                symbol.split("/")[-1] if "/" in symbol else symbol[-3:]
            )
            quote_to_usd = self.mt5.quote_to_usd_rate(quote_currency)
            order["volume"] = recalc_execution_lot(
                symbol=symbol,
                broker_symbol=broker_symbol or symbol,
                account_balance=balance,
                risk_percent=effective_risk,
                account_currency=settings.trading.account_currency,
                lot_step=float(settings.trading.lot_step or 0.01),
                minimum_lot=float(settings.trading.minimum_lot or 0.01),
                contract_size_override=contract,
                entry_price=float(execution_price or 0.0),
                stop_loss=stop_loss,
                quote_to_usd_rate=quote_to_usd,
                fallback_lot=fallback_lot,
            )
        except Exception:
            # The engine below rejects a missing/invalid volume or live price.
            order["volume"] = None

        news_status: dict[str, object]
        try:
            news_status = self.news_service.execution_news_status(
                symbol,
                before_minutes=int(
                    settings.advanced.high_impact_news_block_before_minutes
                ),
                after_minutes=int(
                    settings.advanced.high_impact_news_block_after_minutes
                ),
            )
        except Exception as exc:
            news_status = {
                "available": False,
                "blackout": None,
                "reason_codes": ["NEWS_STATUS_UNAVAILABLE"],
                "message": str(exc),
            }
        news_blackout = (
            news_status.get("blackout")
            if news_status.get("available") is True
            else None
        )
        if not settings.advanced.block_high_impact_news:
            news_blackout = False

        try:
            portfolio = evaluate_portfolio_risk(
                portfolio_snapshot,
                proposal=order,
                market_snapshot=snapshot,
                closed_trades=(
                    self.journal_service.list_closed_trades_for_account_guard()
                    if self.journal_service
                    else None
                ),
                limits=self._portfolio_limits(settings),
            )
            portfolio_payload = portfolio.to_dict()
            account_guard = portfolio.account_guard
            account_allowed: bool | None = (
                portfolio.account_allowed
                and snapshot.connected
                and snapshot.logged_in
                and snapshot.trade_allowed
            )
            portfolio_allowed: bool | None = portfolio.portfolio_allowed
        except Exception as exc:
            portfolio_payload = {
                "allowed": False,
                "portfolio_allowed": False,
                "account_allowed": False,
                "block_codes": ["PORTFOLIO_GUARD_UNAVAILABLE"],
                "reason": str(exc),
            }
            account_guard = {
                "allowed": None,
                "block_codes": ["ACCOUNT_GUARD_UNAVAILABLE"],
                "reasons": [str(exc)],
            }
            account_allowed = None
            portfolio_allowed = None
        required_min_rr = order.get("required_min_rr", order.get("min_rr"))
        validation = revalidate_execution(
            order,
            snapshot,
            news_blackout=(
                bool(news_blackout) if news_blackout is not None else None
            ),
            account_allowed=account_allowed,
            portfolio_allowed=portfolio_allowed,
            required_min_rr=required_min_rr,
        )
        validation_payload = validation.to_dict()
        common = {
            "symbol": symbol,
            "broker_symbol": broker_symbol,
            "side": side,
            "volume": order.get("volume"),
            "stop_loss": order.get("stop_loss"),
            "take_profit": order.get("take_profit"),
            "revalidation": validation_payload,
            "execution_snapshot": snapshot.to_dict(),
            "news_status": news_status,
            "account_guard": account_guard,
            "portfolio_guard": portfolio_payload,
            "scan_id": scan_id,
            "row_id": row_id,
            "settings_hash": order.get("settings_hash"),
            "backtest_config_id": order.get("backtest_config_id"),
            "scorer_version": order.get("scorer_version"),
            "ranking_version": order.get("ranking_version"),
        }
        if not validation.allowed:
            detailed_blocks = list(validation.block_codes)
            if isinstance(portfolio_payload, dict):
                detailed_blocks.extend(
                    str(code)
                    for code in portfolio_payload.get("block_codes", [])
                )
            detailed_blocks = list(dict.fromkeys(detailed_blocks))
            blocked_result = {
                "success": False,
                **common,
                "message": (
                    "Execution revalidation blocked: "
                    + ", ".join(detailed_blocks)
                ),
            }
            self._emit_observability(
                "EXECUTION_REVALIDATION_FAILURE",
                scan_id=scan_id,
                symbol=symbol,
                severity="WARNING",
                payload={
                    "row_id": row_id,
                    "revalidation": validation_payload,
                    "portfolio_guard": portfolio_payload,
                    "news_status": news_status,
                },
            )
            return blocked_result

        self._emit_observability(
            "ORDER_SEND_REQUEST",
            scan_id=scan_id,
            symbol=symbol,
            payload={
                "row_id": row_id,
                "broker_symbol": broker_symbol,
                "side": side,
                "volume": order.get("volume"),
                "execution_price": validation.execution_price,
                "stop_loss": order.get("stop_loss"),
                "take_profit": order.get("take_profit"),
            },
        )
        order_sent_after = datetime.utcnow()
        try:
            mt5_comment = _forward_order_comment(row_id, comment)
            mt5_result = self.mt5.place_market_order(
                symbol=symbol,
                broker_symbol=broker_symbol,
                side=side,
                volume=float(order["volume"]),
                stop_loss=float(order["stop_loss"]),
                take_profit=float(order["take_profit"]),
                comment=mt5_comment,
            )
        except Exception as exc:
            self._emit_observability(
                "ORDER_RESPONSE",
                scan_id=scan_id,
                symbol=symbol,
                severity="ERROR",
                payload={
                    "row_id": row_id,
                    "success": False,
                    "message": str(exc),
                    "revalidation": validation_payload,
                },
            )
            raise
        payload = (
            asdict(mt5_result)
            if hasattr(mt5_result, "__dataclass_fields__")
            else dict(mt5_result)
        )
        payload.update({
            **common,
            "price": payload.get("price") or validation.execution_price,
            "forward_correlation_id": (
                mt5_comment.removeprefix("AMA-FWD:")
                if mt5_comment.startswith("AMA-FWD:")
                else ""
            ),
        })
        if payload.get("success"):
            # An order/deal id is not a position ticket. Reconcile the actual
            # broker position by broker symbol + AMA correlation before
            # exposing an id to Order Management.
            reconcile = getattr(self.mt5, "reconcile_open_position", None)
            if callable(reconcile):
                try:
                    broker_position = reconcile(
                        broker_symbol,
                        expected_ticket=(
                            int(payload["position_id"])
                            if isinstance(payload.get("position_id"), int)
                            and int(payload["position_id"]) > 0
                            else None
                        ),
                        magic=260609,
                        comment_prefix=mt5_comment,
                        expected_side=side,
                        expected_volume=float(order.get("volume") or 0),
                        opened_after=order_sent_after,
                    )
                except Exception as exc:
                    broker_position = None
                    payload["position_reconciliation"] = {
                        "status": "unavailable",
                        "message": str(exc),
                    }
                if broker_position is not None:
                    raw_position_id = getattr(
                        broker_position, "position_id", None
                    )
                    if isinstance(raw_position_id, int) and raw_position_id > 0:
                        actual_side = str(
                            getattr(broker_position, "side", "") or ""
                        ).lower()
                        actual_volume = float(
                            getattr(broker_position, "volume", 0) or 0
                        )
                        requested_volume = float(order.get("volume") or 0)
                        volume_step = float(
                            getattr(
                                getattr(
                                    broker_position,
                                    "symbol_metadata",
                                    None,
                                ),
                                "volume_step",
                                0,
                            )
                            or 0.01
                        )
                        if (
                            actual_side == side
                            and abs(actual_volume - requested_volume)
                            <= max(volume_step / 2, 1e-9)
                        ):
                            payload["position_id"] = raw_position_id
                            payload["actual_entry_price"] = float(
                                getattr(broker_position, "open_price", 0) or 0
                            )
                            payload["broker_symbol"] = str(
                                getattr(
                                    broker_position,
                                    "broker_symbol",
                                    broker_symbol,
                                )
                                or broker_symbol
                            )
                            payload["position_reconciliation"] = {
                                "status": "verified",
                                "position_id": raw_position_id,
                            }
                        else:
                            payload["position_reconciliation"] = {
                                "status": "identity_mismatch",
                                "expected_side": side,
                                "actual_side": actual_side,
                                "expected_volume": requested_volume,
                                "actual_volume": actual_volume,
                            }
                    else:
                        payload["position_reconciliation"] = {
                            "status": "invalid_position_identity"
                        }
                elif "position_reconciliation" not in payload:
                    payload["position_reconciliation"] = {
                        "status": "not_found"
                    }
        if payload.get("success"):
            try:
                post_snapshot = self.mt5.portfolio_snapshot()
                post_evaluation = evaluate_portfolio_risk(
                    post_snapshot,
                    closed_trades=(
                        self.journal_service.list_closed_trades_for_account_guard()
                        if self.journal_service
                        else None
                    ),
                    limits=self._portfolio_limits(settings),
                )
                payload["post_trade_portfolio"] = post_evaluation.to_dict()
            except Exception as exc:
                payload["post_trade_portfolio"] = {
                    "allowed": False,
                    "block_codes": ["POST_TRADE_PORTFOLIO_UNAVAILABLE"],
                    "reason": str(exc),
                }
        self._emit_observability(
            "ORDER_RESPONSE",
            scan_id=scan_id,
            symbol=symbol,
            severity="INFO" if payload.get("success") else "ERROR",
            payload={
                "row_id": row_id,
                "success": bool(payload.get("success")),
                "ticket": (
                    payload.get("ticket")
                    or payload.get("order_id")
                    or payload.get("position_id")
                ),
                "message": payload.get("message"),
                "revalidation": validation_payload,
            },
        )
        return payload

    @staticmethod
    def _portfolio_limits(settings: object) -> dict[str, object]:
        trading = getattr(settings, "trading", None)
        display = getattr(settings, "display", None)
        return {
            "max_open_risk_pct": float(
                getattr(trading, "max_open_risk_pct", 3.0)
            ),
            "max_symbol_risk_pct": float(
                getattr(trading, "max_symbol_risk_pct", 2.0)
            ),
            "max_currency_exposure_pct": float(
                getattr(trading, "max_currency_exposure_pct", 2.0)
            ),
            "max_correlated_risk_pct": float(
                getattr(trading, "max_correlated_risk_pct", 2.0)
            ),
            "max_concurrent_orders": int(
                getattr(trading, "max_concurrent_orders", 5)
            ),
            "max_daily_loss_pct": float(
                getattr(trading, "max_daily_loss_pct", 2.0)
            ),
            "max_weekly_loss_pct": float(
                getattr(trading, "max_weekly_loss_pct", 5.0)
            ),
            "max_consecutive_losses": int(
                getattr(trading, "max_consecutive_losses", 3)
            ),
            "trader_timezone": str(
                getattr(display, "timezone", "Asia/Ho_Chi_Minh")
            ),
        }

    def _execute_auto_trades(
        self,
        rows: list[dict[str, Any]],
        request: ScannerRequest,
    ) -> dict[str, Any]:
        """Execute every eligible row through Phase-3 realtime revalidation."""

        results: list[dict[str, Any]] = []
        errors: list[str] = []
        diagnostics: list[dict[str, Any]] = []
        attempted = opened = skipped = 0
        for row in rows:
            symbol = str(row.get("symbol") or "--")
            config = self._auto_trade_config(request, symbol)
            # C2b: the auto-trade gate reads the row's REAL flag (set by the
            # adapter/filters); candidate_status must also be an auto-trade status.
            if not (
                bool(row.get("auto_trade_candidate"))
                and _v4_candidate_status(row) in _AUTO_TRADE_STATUSES
            ):
                continue

            attempted += 1
            # C2b: build the executable proposal from the REAL order payload
            # (intent only; execute_order_candidate always revalidates before any
            # real dispatch). Never fabricated — None when no payload exists.
            proposal = _order_proposal(row)
            if proposal is None:
                skipped += 1
                errors.append(f"{symbol}: order proposal không hợp lệ.")
                continue
            proposal.update({
                "execution_origin": "AUTO_TRADE",
            })

            try:
                result = self.execute_order_candidate(
                    proposal,
                    risk_percent=request.risk_percent,
                    comment=f"AMA {symbol}",
                )
            except Exception as exc:
                result = {
                    "success": False,
                    "symbol": symbol,
                    "message": str(exc),
                    "revalidation": {
                        "allowed": False,
                        "block_codes": ["EXECUTION_REVALIDATION_FAILED"],
                    },
                }
            results.append(result)
            if result.get("success"):
                opened += 1
                manager = getattr(self, "order_management_service", None)
                if manager is not None:
                    try:
                        position_id = int(result.get("position_id") or 0)
                        broker_symbol = str(
                            result.get("broker_symbol") or ""
                        ).strip()
                        if position_id <= 0 or not broker_symbol:
                            raise ValueError(
                                "Broker did not return a verified position identity."
                            )
                        validation = result.get("revalidation", {})
                        analysis = row.get("analysis_result", {})
                        technical = (
                            analysis.get("technical", {})
                            if isinstance(analysis, dict)
                            else {}
                        )
                        manager.register_position(
                            verified_ticket=position_id,
                            broker_symbol=broker_symbol,
                            side=str(result.get("side") or ""),
                            actual_entry_price=float(
                                result.get("actual_entry_price")
                                or result.get("price")
                                or (
                                    validation.get("execution_price")
                                    if isinstance(validation, dict)
                                    else 0.0
                                )
                            ),
                            initial_sl=float(result.get("stop_loss") or 0.0),
                            atr=float(
                                technical.get("atr_h1", 0.0)
                                if isinstance(technical, dict)
                                else 0.0
                            ),
                            correlation_id=str(
                                result.get("forward_correlation_id") or ""
                            ),
                        )
                    except Exception as exc:
                        self._emit_observability(
                            "STATE_RECONCILIATION_FAILED",
                            scan_id=str(row.get("scan_id", "") or ""),
                            symbol=symbol,
                            severity="ERROR",
                            payload={
                                "reason": "auto_tracking_registration_failed",
                                "message": str(exc),
                                "broker_symbol": result.get("broker_symbol"),
                                "position_id": result.get("position_id"),
                            },
                        )
            else:
                skipped += 1
                errors.append(
                    f"{symbol}: {result.get('message') or 'order bị chặn.'}"
                )

        return {
            "enabled": True,
            "attempted": attempted,
            "opened": opened,
            "skipped": skipped,
            "errors": errors,
            "orders": results,
            "diagnostics": diagnostics,
            "risk_percent": request.risk_percent,
        }

    def _is_auto_trade_candidate(self, row: dict[str, Any], at_cfg: dict[str, object] | None) -> bool:
        """Compatibility wrapper reading the REAL candidate fields (C2b)."""
        return bool(
            self._auto_trade_safety_decision(row, at_cfg)["auto_trade_candidate"]
        )

    @staticmethod
    def _auto_trade_safety_decision(
        row: dict[str, Any],
        at_cfg: dict[str, object] | None,
    ) -> dict[str, Any]:
        """C2b compat decision: read the adapter's real candidate fields.

        Replaces the legacy ``evaluate_auto_trade_safety`` (deletion) call. Every
        value traces to the row's real ``candidate_status`` / ``reason_codes``
        / ``auto_trade_candidate`` or fails closed. No backtest-config branch /
        strategy-config concept exists, so those stay ``None``.
        """
        candidate_status = _v4_candidate_status(row)
        is_auto_status = candidate_status in _AUTO_TRADE_STATUSES
        auto_candidate = bool(row.get("auto_trade_candidate")) and is_auto_status
        return {
            "auto_trade_candidate": auto_candidate,
            "branch": None,
            "status": candidate_status,
            "selected_side": row.get("selected_side"),
            "strategy": {
                "config_status": None,
                "eligible": is_auto_status,
            },
            "strategy_eligible": is_auto_status,
            "execution_ready": candidate_status == READY_NOW,
            "trade_allowed": auto_candidate and candidate_status == READY_NOW,
            "reason_codes": list(row.get("reason_codes") or []),
            "to_dict": lambda: {
                "auto_trade_candidate": auto_candidate,
                "branch": None,
                "status": candidate_status,
                "selected_side": row.get("selected_side"),
                "strategy": {"config_status": None, "eligible": is_auto_status},
                "strategy_eligible": is_auto_status,
                "execution_ready": candidate_status == READY_NOW,
                "trade_allowed": auto_candidate and candidate_status == READY_NOW,
                "reason_codes": list(row.get("reason_codes") or []),
            },
        }

    def _get_alert_order_candidates(
        self,
        rows: list[dict[str, Any]],
        *,
        performance_tracker: object | None = None,
    ) -> list[dict[str, Any]]:
        """Return order candidates captured by the canonical scan decision."""
        candidates: list[dict[str, Any]] = []
        for row in rows:
            canonical = "candidate_order_payload" in row
            if (
                _is_structural_reject_row(row)
                or self._is_non_candidate_alert_row(
                    row,
                    legacy_compatibility=not canonical,
                )
            ):
                _record_performance(
                    performance_tracker,
                    "increment",
                    "telegram_skipped_non_candidates",
                )
                continue
            if canonical:
                stored = row["candidate_order_payload"]
                if not isinstance(stored, dict):
                    _record_performance(
                        performance_tracker,
                        "increment",
                        "telegram_skipped_non_candidates",
                    )
                    continue
                payload = dict(stored)
                if not self._is_valid_alert_order_payload(
                    payload,
                    require_canonical_contract=True,
                ):
                    _record_performance(
                        performance_tracker,
                        "increment",
                        "telegram_skipped_non_candidates",
                    )
                    continue
                _record_performance(
                    performance_tracker,
                    "increment",
                    "telegram_canonical_candidates",
                )
            else:
                payload = self._build_legacy_alert_order_payload(row)
                if not self._is_valid_alert_order_payload(
                    payload,
                    require_canonical_contract=False,
                ):
                    _record_performance(
                        performance_tracker,
                        "increment",
                        "telegram_skipped_non_candidates",
                    )
                    continue
                _record_performance(
                    performance_tracker,
                    "increment",
                    "telegram_legacy_fallback_candidates",
                )

            ranking_metadata = {
                field: row.get(source)
                for field, source in {
                    "rank": "rank",
                    "opportunity_rank": "opportunity_rank",
                    "evidence_confidence": "evidence_confidence",
                    "execution_readiness": "execution_readiness",
                    "strategy_branch": "auto_trade_branch",
                    "config_health": "strategy_config_status",
                    "ranking_version": "ranking_version",
                }.items()
                if row.get(source) is not None
            }
            if not canonical:
                ranking_metadata["candidate_status"] = row.get(
                    "candidate_status"
                )
            payload.update(ranking_metadata)
            try:
                payload["best_score"] = int(
                    payload.get("best_score") or 0
                )
            except (TypeError, ValueError, OverflowError):
                payload["best_score"] = 0
            candidates.append(payload)

        return candidates

    @staticmethod
    def _is_non_candidate_alert_row(
        row: dict[str, Any],
        *,
        legacy_compatibility: bool,
    ) -> bool:
        """Fail closed for every explicit non-candidate classification."""

        status_fields = (
            ("candidate_status", "legacy_candidate_status")
            if legacy_compatibility
            else ("candidate_status",)
        )
        for field in status_fields:
            status = str(row.get(field, "") or "").strip().upper()
            if status and status != "READY_NOW":
                return True
        if not legacy_compatibility:
            return False
        group = str(row.get("scanner_group", "") or "").strip().lower()
        if group in {
            "blocked",
            "data_unavailable",
            "out_of_strategy",
            "waiting_confirmation",
            "watch_zone",
        }:
            return True
        action = str(
            row.get("scanner_action", "") or ""
        ).strip().lower()
        return action in {
            "stand_aside",
            "skip",
            "wait",
            "wait_for_confirmation",
            "watch",
        }

    def _build_legacy_alert_order_payload(
        self,
        row: dict[str, Any],
    ) -> dict[str, Any]:
        """Build compatibility data only for rows predating the payload key."""

        scenario = self._best_scenario(row)
        final_zone = self._final_execution_zone(scenario)
        if not scenario or final_zone is None:
            return {}
        raw_tp = scenario.get("take_profit")
        take_profit = (
            raw_tp[0]
            if isinstance(raw_tp, (list, tuple)) and raw_tp
            else raw_tp
        )
        sizing = scenario.get("position_sizing")
        if not isinstance(sizing, dict):
            sizing = {}
        return {
            "symbol": str(row.get("symbol") or "--"),
            "broker_symbol": str(
                row.get("broker_symbol") or ""
            ).strip(),
            "side": str(
                scenario.get("type")
                or scenario.get("side")
                or ""
            ).lower(),
            "entry_zone": list(final_zone),
            "entry_price": scenario.get("entry_price"),
            "stop_loss": scenario.get("stop_loss"),
            "take_profit": take_profit,
            "volume": sizing.get("suggested_lot"),
            "risk_reward": scenario.get("risk_reward"),
            "risk_reward_range": scenario.get("risk_reward_range"),
            "expected_effective_rr": scenario.get(
                "expected_effective_rr"
            ),
            "expected_effective_rr_base": scenario.get(
                "expected_effective_rr_base"
            ),
            "source_zone": scenario.get("source_zone"),
            "structural_execution_zone": scenario.get(
                "structural_execution_zone"
            ),
            "rr_trimmed": bool(scenario.get("rr_trimmed")),
            "rr_trim_diagnostics": scenario.get(
                "rr_trim_diagnostics"
            ),
            "entry_zone_width": scenario.get("entry_zone_width"),
            "entry_zone_width_atr": scenario.get(
                "entry_zone_width_atr"
            ),
            "price_digits": scenario.get("price_digits"),
            "invalid_reason": scenario.get("invalid_reason"),
            "analysis_result": row.get("analysis_result"),
        }

    def _is_valid_alert_order_payload(
        self,
        payload: object,
        *,
        require_canonical_contract: bool,
    ) -> bool:
        """Validate order fields and, for new rows, status/provenance."""

        if not isinstance(payload, dict):
            return False
        symbol = str(payload.get("symbol") or "").strip()
        broker_symbol = str(
            payload.get("broker_symbol") or ""
        ).strip()
        side = str(payload.get("side") or "").strip().lower()
        execution_zone = self._final_execution_zone(payload)
        if (
            not symbol
            or symbol == "--"
            or not broker_symbol
            or side not in {"buy", "sell"}
            or execution_zone is None
            or not all(isfinite(value) for value in execution_zone)
            or self._positive_alert_price(payload.get("stop_loss")) is None
        ):
            return False
        take_profit = payload.get("take_profit")
        if isinstance(take_profit, (list, tuple)):
            take_profit = take_profit[0] if take_profit else None
        if self._positive_alert_price(take_profit) is None:
            return False
        if not require_canonical_contract:
            return True
        if (
            str(
                payload.get("candidate_status") or ""
            ).strip().upper()
            != "READY_NOW"
        ):
            return False
        return all(
            str(payload.get(field) or "").strip()
            for field in (
                "scan_id",
                "row_id",
                "settings_hash",
                "scorer_version",
                "ranking_version",
            )
        )

    @staticmethod
    def _positive_alert_price(value: object) -> float | None:
        try:
            price = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return price if isfinite(price) and price > 0 else None

    def _best_scenario(
        self,
        row: dict[str, Any],
        *,
        force_side: str | None = None,
    ) -> dict[str, Any]:
        """Compatibility selector that never borrows the opposite side."""

        analysis = row.get("analysis_result")
        scenarios = (
            analysis.get("scenarios")
            if isinstance(analysis, dict)
            else None
        )
        if not isinstance(scenarios, list):
            return {}
        side = str(
            force_side
            or row.get("selected_side")
            or row.get("best_side")
            or ""
        ).strip().lower()
        scenario = _find_scenario_for_side(
            scenarios,
            side,
            fallback_to_first=side not in {"buy", "sell"},
        )
        return scenario if isinstance(scenario, dict) else {}

    @staticmethod
    def _final_execution_zone(
        scenario: dict[str, Any],
    ) -> tuple[float, float] | None:
        """Return the final entry zone; source bounds are reference-only."""

        zone = (
            scenario.get("entry_zone")
            if isinstance(scenario, dict)
            else None
        )
        if not isinstance(zone, (list, tuple)) or len(zone) != 2:
            return None
        try:
            low, high = sorted((float(zone[0]), float(zone[1])))
        except (TypeError, ValueError):
            return None
        return (low, high) if 0 < low < high else None

    @staticmethod
    def _settings_auto_trade_config(settings: object, symbol: str) -> dict[str, object] | None:
        """Convert persisted per-symbol settings to the canonical live config."""
        if settings is None:
            return None
        trading = getattr(settings, "trading", None)
        symbol_settings = getattr(trading, "symbol_settings", None)
        if not isinstance(symbol_settings, dict):
            return None
        sym_cfg = symbol_settings.get(symbol)
        if sym_cfg is None and "/" not in symbol and len(symbol) == 6:
            sym_cfg = symbol_settings.get(symbol[:3] + "/" + symbol[3:])
        return serialize_backtest_config(sym_cfg, symbol=symbol)

    def _send_telegram_alerts(
        self,
        rows: list[dict[str, Any]],
        *,
        performance_tracker: object | None = None,
    ) -> dict[str, Any]:
        if performance_tracker is None:
            performance_tracker = getattr(
                self, "_active_performance_tracker", None
            )
        _record_performance(performance_tracker, "start_phase", "telegram")
        notifications = self.settings_service.load().notifications
        # Filter using the SAME gates as "Hiển thị lệnh" dialog
        candidates = self._get_alert_order_candidates(
            rows,
            performance_tracker=performance_tracker,
        )
        _record_performance(
            performance_tracker,
            "increment",
            "telegram_candidates",
            len(candidates),
        )
        try:
            result = self.telegram_service.send_order_alerts(
                candidates,
                bot_token=notifications.telegram_bot_token,
                chat_ids=notifications.telegram_chat_ids,
                performance_tracker=performance_tracker,
            )
            summary_sent = self.telegram_service.send_summary_alert(
                rows,
                candidates=candidates,
                bot_token=notifications.telegram_bot_token,
                chat_ids=notifications.telegram_chat_ids,
                timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
                performance_tracker=performance_tracker,
            )
            return {"attempted": result.attempted, "sent": result.sent, "errors": result.errors, "summary_sent": summary_sent}
        finally:
            _record_performance(performance_tracker, "end_phase", "telegram")

    def _emit_observability(
        self,
        event_type: str,
        *,
        scan_id: str = "",
        symbol: str = "",
        severity: str = "INFO",
        payload: dict[str, Any] | None = None,
    ) -> None:
        try:
            self.observability.emit(
                event_type,
                scan_id=scan_id,
                symbol=symbol,
                severity=severity,
                payload=payload,
            )
        except Exception:
            # Observability must never change a trading decision or crash a scan.
            pass

    def _emit_candidate_events(self, row: dict[str, Any], scan_id: str) -> None:
        symbol = str(row.get("symbol", "") or "")
        analysis = (
            row.get("analysis_result")
            if isinstance(row.get("analysis_result"), dict)
            else {}
        )
        decision = (
            row.get("scanner_candidate_decision")
            if isinstance(row.get("scanner_candidate_decision"), dict)
            else {}
        )
        strategy = (
            decision.get("strategy")
            if isinstance(decision.get("strategy"), dict)
            else {}
        )
        execution = (
            decision.get("execution")
            if isinstance(decision.get("execution"), dict)
            else {}
        )
        if strategy.get("eligible") is not True:
            self._emit_observability(
                "STRATEGY_REJECTION",
                scan_id=scan_id,
                symbol=symbol,
                payload={
                    "branch": decision.get("branch"),
                    "status": decision.get("status"),
                    "reason_codes": strategy.get("reason_codes", []),
                },
            )
        if (
            execution.get("entry_ready") is not True
            or execution.get("trade_allowed") is not True
        ):
            self._emit_observability(
                "GATE_REJECTION",
                scan_id=scan_id,
                symbol=symbol,
                payload={
                    "status": decision.get("status"),
                    "reason_codes": execution.get("reason_codes", []),
                    "block_codes": execution.get("block_codes", []),
                },
            )

    def save_snapshot(
        self,
        result: dict[str, Any],
        *,
        runtime_root: Path | None = None,
        performance_tracker: object | None = None,
    ) -> Path:
        """Compatibility wrapper (manual "Lưu snapshot" button): return the path."""
        info = self.persist_scan(
            result,
            runtime_root=runtime_root,
            performance_tracker=performance_tracker,
        )
        return Path(info["snapshot_path"])

    def persist_scan(
        self,
        result: dict[str, Any],
        *,
        runtime_root: Path | None = None,
        performance_tracker: object | None = None,
        manage_job: bool = True,
    ) -> dict[str, Any]:
        """Persist one scan without ever blocking the core result.

        Ordering (Phase 5): the compact summary is written first so a killed
        process always leaves a readable snapshot; the full per-symbol gzip
        evidence follows; the summary is then rewritten with the manifest and
        the actual persistence status. Every write is atomic (temp + replace),
        so a forced exit between writes can leave at most an orphaned ``.tmp``
        sibling, never a truncated target.

        With ``manage_job=True`` (standalone manual save) the aftercare job is
        started and completed around the writes.  The aftercare flow passes
        ``manage_job=False`` because it already owns the job lifecycle across
        the whole aftercare (begin + compact summary before market brief,
        complete only after persistence, retention and performance summary).

        Returns the persistence delta contract: snapshot_path, snapshot_mode,
        snapshot_manifest, snapshot_write_count, snapshot_duration_ms,
        snapshot_errors and snapshot_status.
        """
        started = perf_counter()
        if performance_tracker is None:
            performance_tracker = getattr(
                self, "_active_performance_tracker", None
            )
        _record_performance(performance_tracker, "start_phase", "persistence")
        root = Path(runtime_root) if runtime_root is not None else app_data_dir()
        retention = getattr(self, "retention", None) or RuntimeRetentionService(root)
        retention.ensure_started()
        persistence = ScannerPersistenceService(root)
        mode = persistence.select_mode(result)
        scan_id = self._persistence_scan_id(result)
        snapshot_dir = root / "scanner_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir = root / "scanner_analysis" / scan_id
        context = (
            result.get("scan_context")
            if isinstance(result.get("scan_context"), dict)
            else {}
        )
        manifest: dict[str, str] = {}
        errors: list[str] = []
        snapshot_path = snapshot_dir / f"scanner_{scan_id}.json"
        job_state = self._scanner_job_state()
        if manage_job:
            job_state.begin_aftercare(scan_id, durable=True)
        try:
            # 1) Compact summary first: durable immediately, even if the
            #    process dies during the heavier full-evidence writes below.
            atomic_json_save(
                snapshot_path,
                self._snapshot_payload(
                    result, manifest, mode, status="writing"
                ),
                indent=None,
            )
            # 2) Full analysis documents (aftercare, never on the core path).
            if mode == PERSISTENCE_FULL:
                analysis_dir.mkdir(parents=True, exist_ok=True)
                for row in result.get("rows", []):
                    if not isinstance(row, dict):
                        continue
                    symbol = str(row.get("symbol", "UNKNOWN") or "UNKNOWN")
                    safe_symbol = "".join(
                        character
                        for character in symbol.upper()
                        if character.isalnum()
                    ) or "UNKNOWN"
                    analysis_path = analysis_dir / f"{safe_symbol}.json.gz"
                    try:
                        atomic_json_save(
                            analysis_path,
                            build_analysis_document(row, context),
                            indent=None,
                        )
                    except OSError as exc:
                        errors.append(f"{symbol}: {exc}")
                        continue
                    manifest[symbol] = str(analysis_path)
            # 3) Final summary: manifest + the actual persistence outcome.
            snapshot_status = (
                "completed" if not errors else "completed_with_errors"
            )
            atomic_json_save(
                snapshot_path,
                self._snapshot_payload(
                    result, manifest, mode, status=snapshot_status
                ),
                indent=None,
            )
            if not errors:
                persistence.record(mode)
        except Exception as exc:
            self._emit_observability(
                "RETENTION_PRUNE_SKIPPED",
                scan_id=scan_id,
                severity="WARNING",
                payload={
                    "reason": "persistence_write_failed",
                    "error": str(exc),
                },
            )
            if manage_job:
                job_state.mark_interrupted(scan_id, reason="persistence_error")
            raise
        else:
            if errors:
                self._emit_observability(
                    "RETENTION_PRUNE_SKIPPED",
                    scan_id=scan_id,
                    severity="WARNING",
                    payload={
                        "reason": "persistence_write_incomplete",
                        "error": "; ".join(errors),
                    },
                )
            else:
                _record_performance(
                    performance_tracker, "start_phase", "retention"
                )
                try:
                    retention.prune()
                except OSError:
                    # Retention must never turn a successful scan into a failed scan.
                    pass
                finally:
                    _record_performance(
                        performance_tracker, "end_phase", "retention"
                    )
        finally:
            if manage_job:
                if errors:
                    job_state.mark_interrupted(
                        scan_id, reason="persistence_write_errors"
                    )
                else:
                    job_state.complete_aftercare(scan_id)
            _record_performance(performance_tracker, "end_phase", "persistence")
            _record_performance(
                performance_tracker,
                "increment",
                "analysis_documents_written",
                len(manifest),
            )
        if errors:
            self._emit_observability(
                "SNAPSHOT_WRITE_FAILURE",
                scan_id=scan_id,
                severity="ERROR",
                payload={"reason": "; ".join(errors)},
            )
        return {
            "snapshot_path": snapshot_path,
            "snapshot_mode": mode,
            "snapshot_manifest": manifest,
            "snapshot_write_count": len(manifest),
            "snapshot_duration_ms": round(
                max(0.0, perf_counter() - started) * 1_000,
                3,
            ),
            "snapshot_errors": errors,
            "snapshot_status": snapshot_status,
        }

    @staticmethod
    def _persistence_scan_id(result: dict[str, Any]) -> str:
        scan_id = str(result.get("scan_id", "") or "").strip()
        if not scan_id:
            scan_id = str(result.get("timestamp", "scanner")).replace(
                ":", ""
            ).replace("+", "_")
        return scan_id

    def _write_early_summary(
        self,
        result: dict[str, Any],
        *,
        runtime_root: Path | None = None,
        performance_tracker: object | None = None,
    ) -> dict[str, Any]:
        """Write the compact snapshot before any slow aftercare I/O.

        This makes the core result durable on disk (status ``writing``) before
        market brief, Telegram or persistence run, so an app shutdown at any
        aftercare point leaves at least a readable snapshot plus an
        ``interrupted`` job marker (mục 19.2).
        """
        if performance_tracker is None:
            performance_tracker = getattr(
                self, "_active_performance_tracker", None
            )
        root = Path(runtime_root) if runtime_root is not None else app_data_dir()
        persistence = ScannerPersistenceService(root)
        mode = persistence.select_mode(result)
        scan_id = self._persistence_scan_id(result)
        snapshot_dir = root / "scanner_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        snapshot_path = snapshot_dir / f"scanner_{scan_id}.json"
        atomic_json_save(
            snapshot_path,
            self._snapshot_payload(result, {}, mode, status="writing"),
            indent=None,
        )
        return {"snapshot_path": snapshot_path, "snapshot_mode": mode}

    def wait_for_aftercare_shutdown(
        self,
        *,
        timeout: float = AFTERCARE_SHUTDOWN_WAIT_SECONDS,
    ) -> bool:
        """Bound the app-shutdown wait for in-flight aftercare persistence.

        Returns True when every job finished within the budget.  When the
        budget expires, the still-running jobs are recorded as interrupted so
        the next launch can tell the snapshot was not fully written.
        """
        job_state = self._scanner_job_state()
        return job_state.wait_for_aftercare_shutdown(
            timeout,
            reason="shutdown_timeout",
        )

    def _write_scanner_ai_audit(self, row: dict[str, Any], active_ai) -> dict[str, Any]:
        prompt = build_ai_setup_audit_prompt(row)
        try:
            raw = AIService(AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key, base_url=active_ai.base_url)).analyze(prompt, max_tokens=4000)
            return parse_ai_setup_audit(raw)
        except Exception as exc:
            return {
                "schema_version": 1,
                "agreement": "caution",
                "confidence_score": 0,
                "trade_plan_quality": 0,
                "setup_summary": "",
                "market_context_summary": "",
                "risk_flags": [],
                "missing_confirmations": [],
                "do_not_trade_reason": "",
                "auditor_error": str(exc),
            }

    def audit_single_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Run AI audit on a single row on-demand (called from detail screen)."""
        settings = self.settings_service.load()
        active_ai = settings.ai.active_provider()
        if not active_ai or not active_ai.api_key:
            return {"auditor_error": "Chưa cấu hình AI Provider hoặc API key trong Settings."}
        audit = self._write_scanner_ai_audit(row, active_ai)
        return audit or {"auditor_error": "AI không trả về kết quả."}

    def _snapshot_payload(
        self,
        result: dict[str, Any],
        manifest: dict[str, str] | None = None,
        mode: str = PERSISTENCE_FULL,
        *,
        status: str = "completed",
    ) -> dict[str, Any]:
        payload = {
            key: value
            for key, value in result.items()
            if key not in {"rows", "scan_context", "portfolio_state", "scan_health"}
        }
        references = manifest or {}
        payload["persistence_schema_version"] = 1
        payload["persistence_mode"] = mode
        # Added in Phase 5; absent on legacy snapshots, which readers treat as
        # completed (schema stays backward compatible, mục 20.3).
        payload["persistence_status"] = status
        payload["rows"] = [
            {
                **summary_row(row),
                "analysis_ref": references.get(str(row.get("symbol", "")), ""),
            }
            for row in result.get("rows", [])
            if isinstance(row, dict)
        ]
        if references:
            payload["analysis_manifest"] = dict(references)
        return payload


def _scan_one_symbol(
    symbol: str,
    *,
    available_symbols: list[str],
    bars_by_timeframe: dict[str, int],
    correlation_context: dict[str, Any],
    news_service: NewsService,
    freshness: dict[str, Any],
    freshness_multiplier: float,
    contract_size_overrides: dict[str, float],
    analysis_input_kwargs: dict[str, Any],
    closed_trades: list[dict[str, Any]],
    account_guard_settings: dict[str, Any],
    thresholds: dict[str, int | float] | None = None,
    ai_service: object | None = None,
) -> dict[str, Any]:
    """C2b stub for the legacy single-symbol scan path.

    ``_scan_one_symbol`` is DEAD — nothing references it (the live two-phase scan
    uses ``_fetch_one_symbol_mt5`` → ``_analyze_one_symbol``).  Its old body
    imported the analysis_engine / scanner / scanner_row_from_analysis deletion
    modules, so it is replaced with a fail-closed blocked row.  Supported
    live analysis is the responsibility of ``_fetch_one_symbol_mt5`` /
    ``_analyze_one_symbol``; this stub never dispatches and never fabricates.
    """
    return blocked_ui_row(symbol, "Legacy sequential scan path retired.")


# ---- Two-phase scan: Phase 1 fetches MT5 data on main thread,
# Phase 2 runs analysis in parallel (no MT5 needed) ----

def _fetch_one_symbol_mt5(
    symbol: str,
    mt5: Any,
    available_symbols: list[str],
    bars_by_timeframe: dict[str, int],
    news_service: Any,
    freshness: dict[str, Any],
    ai_service: object | None = None,
    performance_tracker: object | None = None,
    history_cache_enabled: bool = False,
    history_cache_identity: MT5HistoryCacheIdentity | None = None,
    v4_account: object | None = None,
    v4_portfolio: object | None = None,
    v4_journal: object | None = None,
) -> dict[str, Any] | None:
    """Fetch MT5 data for one symbol on the main thread.  Returns a data packet
    consumed by ``_analyze_one_symbol``, or ``None`` if the symbol can't be resolved.

    C2b: also attaches the ``MarketSafetyContext`` (built from the live MT5
    data-quality state, fail-closed) and the account/portfolio/journal states so
    the CPU-thread ``_analyze_one_symbol`` reads them from the packet.
    """
    mt5_started = perf_counter()
    broker_symbol = mt5.resolve_symbol(symbol, available_symbols)
    if not broker_symbol:
        _record_performance(
            performance_tracker,
            "record_symbol",
            symbol,
            mt5_ms=round(
                max(0.0, perf_counter() - mt5_started) * 1_000,
                3,
            ),
        )
        return None

    requested_bars = {**bars_by_timeframe, "M15": 100}
    history_cache_result: dict[str, Any] | None = None
    if history_cache_enabled:
        history_cache_result = mt5.load_primary_timeframes_cached(
            broker_symbol,
            requested_bars,
            history_cache_identity,
            performance_tracker=performance_tracker,
        )
        all_candles = history_cache_result["candles_by_timeframe"]
    else:
        all_candles = mt5.load_primary_timeframes(
            broker_symbol,
            requested_bars,
            performance_tracker=performance_tracker,
        )
    data_quality = mt5.symbol_data_quality(symbol, broker_symbol)
    mt5_before_macro_ms = (
        max(0.0, perf_counter() - mt5_started) * 1_000
    )
    macro_lookup_started = perf_counter()
    try:
        news_flags = news_service.data_quality_flags(
            symbol,
            ai_service=ai_service,
            performance_tracker=performance_tracker,
        )
    finally:
        _record_performance(
            performance_tracker,
            "record_symbol",
            symbol,
            macro_lookup_ms=round(
                max(0.0, perf_counter() - macro_lookup_started) * 1_000,
                3,
            ),
        )
    macro_context = news_flags.pop("macro_context", {"events": []})
    data_quality.update(news_flags)
    data_quality["macro_freshness"] = freshness
    quote_currency = symbol.split("/")[-1] if "/" in symbol else symbol[-3:]
    mt5_after_macro_started = perf_counter()
    quote_to_usd = mt5.quote_to_usd_rate(quote_currency)
    _record_performance(
        performance_tracker,
        "record_symbol",
        symbol,
        mt5_ms=round(
            mt5_before_macro_ms
            + max(0.0, perf_counter() - mt5_after_macro_started) * 1_000,
            3,
        ),
    )

    # ---- C2b: build the safety context from the live MT5 data-quality state.
    # Every field is sourced from REAL MT5 data; anything unavailable stays None
    # (fail-closed -> MarketSafetyGate reports UNKNOWN/MISSING).
    captured_at = datetime.now(timezone.utc)
    connectivity_checked_at = captured_at
    data_checked_at = captured_at
    spread_checked_at = captured_at
    spread_points = data_quality.get("spread_points") if isinstance(data_quality, dict) else None
    terminal_connected = data_quality.get("terminal_connected") if isinstance(data_quality, dict) else None
    broker_logged_in = data_quality.get("broker_logged_in") if isinstance(data_quality, dict) else None
    # News-source verification: only mark verified when the macro context carries a
    # real fetch scope; otherwise fail closed (None -> NewsSource MISSING).
    news_verified = (
        bool(macro_context)
        and "macro_tier_detail" in (macro_context if isinstance(macro_context, dict) else {})
    )
    v4_safety = build_live_market_safety_context(
        symbol,
        captured_at,
        terminal_connected=terminal_connected,
        broker_logged_in=broker_logged_in,
        connectivity_checked_at=connectivity_checked_at,
        last_candle_time_utc=_newest_last_candle_time_utc(all_candles),
        data_checked_at=data_checked_at,
        last_tick_time_utc=(
            data_quality.get("tick_time") if isinstance(data_quality, dict) else None
        ),
        spread_points=spread_points,
        spread_checked_at=spread_checked_at,
        news_source_verified=bool(news_verified),
        news_checked_at=captured_at,
        volatility_ratio=compute_live_volatility_ratio(
            all_candles.get("D1"), all_candles.get("H4")
        ),
        volatility_checked_at=captured_at,
    )

    # ---- Account gate, per symbol: required margin = what the broker itself
    # computes for the MINIMUM lot of THIS broker symbol (both directions, max
    # kept).  At scan time no entry/SL exists yet, so risk-sizing is impossible;
    # the minimum orderable size is the only honest probe.  Unavailable -> None
    # -> the gate fails closed with GATE_ACCOUNT_DATA_MISSING.
    account_symbol = v4_account
    if v4_account is not None:
        required_margin = None
        try:
            min_lot_margin = getattr(mt5, "min_lot_order_margin", None)
            if callable(min_lot_margin):
                required_margin = min_lot_margin(broker_symbol)
        except Exception:
            required_margin = None
        account_symbol = AccountState(
            free_margin=v4_account.free_margin,
            required_margin=required_margin,
        )

    return {
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "candles": {tf: all_candles[tf] for tf in bars_by_timeframe},
        "m15_candles": all_candles["M15"],
        "data_quality": data_quality,
        "macro_context": macro_context,
        "quote_to_usd": quote_to_usd,
        "input_timestamps": input_timestamps_from_candles(all_candles),
        "mt5_history_cache": history_cache_result,
        "v4_safety": v4_safety,
        "v4_captured_at": captured_at,
        "account": account_symbol,
        "portfolio": v4_portfolio,
        "journal": v4_journal,
    }


def _newest_last_candle_time_utc(all_candles: object) -> object:
    """Newest last-candle time across every timeframe (real, or None).

    Candle ``time`` values come tz-aware UTC from MT5Service; a naive value is
    NOT coerced (no fabricated timezone) and stays out of the freshness source.
    """
    if not isinstance(all_candles, dict):
        return None
    newest = None
    for timeframes in all_candles.values():
        if not isinstance(timeframes, list) or not timeframes:
            continue
        last = timeframes[-1]
        value = None
        if hasattr(last, "time"):
            value = last.time
        elif isinstance(last, dict):
            value = last.get("time")
        if value is None:
            continue
        if getattr(value, "tzinfo", None) is None:
            continue  # fail-closed: never assume a timezone
        if newest is None or value > newest:
            newest = value
    return newest


def _analyze_one_symbol(
    pkt: dict[str, Any],
    *,
    correlation_context: dict[str, Any],
    freshness_multiplier: float,
    contract_size_overrides: dict[str, float],
    analysis_input_kwargs: dict[str, Any],
    closed_trades: list[dict[str, Any]],
    account_guard_settings: dict[str, Any],
    thresholds: dict[str, int | float] | None = None,
    scanner_fast_tier1: bool = False,
    ai_service: object | None = None,
    order_policy: RuntimeOrderPolicy | None = None,
) -> dict[str, Any]:
    """Run the single-symbol analysis path (CPU-only, thread-safe, C2b).

    Re-platformed from the legacy ``analyze_symbol``+``scanner_row_from_analysis``
    (deletion) path: composes the live snapshot and maps the release pair via
    ``pair_to_ui_row``. Every emitted value comes from the real Scanner sources (or
    fails closed to a ``blocked_ui_row``). Legacy-only kwargs are kept for signature
    compatibility with ``_run_market_scan_core``'s submit and are not used here.
    """
    started_at = perf_counter()
    symbol = pkt["symbol"]
    broker_symbol = pkt["broker_symbol"]
    macro_context = (
        pkt["macro_context"]
        if isinstance(pkt.get("macro_context"), dict)
        else {}
    )
    now = datetime.now(timezone.utc)
    try:
        candles = pkt["candles"] if isinstance(pkt.get("candles"), dict) else {}
        d1 = candles.get("D1") or []
        h4 = candles.get("H4") or []
        h1 = candles.get("H1") or []
        safety = pkt.get("v4_safety")
        if safety is None:
            # No live safety context -> fail closed (all sources MISSING).
            # Volatility is still derivable from the prefetched candles alone
            # (no MT5 needed); everything else stays MISSING/UNKNOWN.
            safety = build_live_market_safety_context(
                symbol,
                now,
                terminal_connected=None,
                broker_logged_in=None,
                connectivity_checked_at=None,
                last_candle_time_utc=None,
                data_checked_at=None,
                spread_points=None,
                spread_checked_at=None,
                news_source_verified=False,
                news_checked_at=None,
                volatility_ratio=compute_live_volatility_ratio(d1, h4),
                volatility_checked_at=None,
            )
        # Real macro derivation (mirrors the legacy analysis_engine consumption).
        macro_alignment = (
            macro_context.get("macro_alignment_scores")
            if isinstance(macro_context.get("macro_alignment_scores"), dict)
            else {}
        )
        macro_buy = macro_alignment.get("buy")
        macro_sell = macro_alignment.get("sell")
        macro_raw_buy = int(macro_buy) if isinstance(macro_buy, (int, float)) else None
        macro_raw_sell = int(macro_sell) if isinstance(macro_sell, (int, float)) else None
        macro_confidence = float(
            macro_context.get("macro_data_quality", 1.0)
        ) * freshness_multiplier

        # Failure-safe derivation + the one-symbol release pair.
        analysis = derive_live_analysis(
            d1,
            h4,
            h1,
            symbol=symbol,
            captured_at=now,
            news_in_3h=False,
        )
        pair = run_pair_from_live(
            d1,
            h4,
            h1,
            symbol,
            safety,
            now=now,
            captured_at=now,
            news_in_3h=False,
            macro_raw_buy=macro_raw_buy,
            macro_raw_sell=macro_raw_sell,
            macro_confidence=macro_confidence,
            account=pkt.get("account"),
            portfolio=pkt.get("portfolio"),
            journal=pkt.get("journal"),
            order_policy=order_policy,
        )
        # The thresholds the candidate was routed with come from the SAME
        # ``order_policy`` this function received (module-level, no ``self``);
        # fall back to the shared locked default when none is supplied.
        _threshold = (
            order_policy.threshold
            if order_policy is not None
            else DEFAULT_RUNTIME_ORDER_POLICY.threshold
        )
        row = pair_to_ui_row(
            pair,
            broker_symbol=broker_symbol,
            technical=analysis.get("technical"),
            min_score=(
                float(_threshold.setup_floor)
                if _threshold.setup_floor is not None
                else None
            ),
            min_rr=(
                float(_threshold.min_risk_reward)
                if _threshold.min_risk_reward is not None
                else None
            ),
        )
        # The detail chart must render for EVERY candidate (blocked included).
        # ``pair_to_ui_row``'s ``analysis_result`` carries no candles, so inject
        # the REAL prefetched candles here — otherwise the chart is empty and
        # the background candle-refresh aborts regardless of candidate_status.
        # The blocked/ready annotation lives in the hero + score panels.
        _analysis_ui = row.get("analysis_result")
        if isinstance(_analysis_ui, dict):
            chart_candles = {
                tf: series
                for tf, series in (pkt.get("candles") or {}).items()
                if isinstance(series, list) and series
            }
            if chart_candles:
                _analysis_ui["chart_payload"] = build_chart_payload(chart_candles)
    except AdapterContractError:
        raise
    except Exception as exc:
        blocked = blocked_ui_row(
            symbol,
            f"Không quét được dữ liệu: {exc}",
            broker_symbol=broker_symbol,
            analysis_latency_ms=round(
                max(0.0, perf_counter() - started_at) * 1000, 3
            ),
            input_timestamps=dict(pkt.get("input_timestamps", {})),
            analysis_error=str(exc),
        )
        blocked["_analysis_error"] = str(exc)
        return blocked

    # Controller bookkeeping ``_run_market_scan_core`` expects.
    row["scanner_group"] = (
        _SCANNER_GROUP_BY_STATUS.get(_v4_candidate_status(row))
        or "data_unavailable"
    )
    row["input_timestamps"] = dict(pkt.get("input_timestamps", {}))
    row["analysis_latency_ms"] = round(
        max(0.0, perf_counter() - started_at) * 1000, 3
    )
    row["economic_events"] = macro_context.get("events", [])
    macro_bucket = row.get("macro")
    if not isinstance(macro_bucket, dict):
        macro_bucket = {}
    macro_bucket["driver_context"] = macro_context
    macro_bucket["macro_confidence"] = macro_confidence
    macro_bucket["macro_data_quality"] = macro_context.get(
        "macro_data_quality", 1.0
    )
    row["macro"] = macro_bucket
    return row

