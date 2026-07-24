from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from pathlib import Path
from threading import RLock
from time import perf_counter
from typing import Any

from PyQt6.QtCore import QThread

from config.paths import app_data_dir
from core.scanner import (
    ScannerRequest,
    blocked_scanner_row,
    build_scanner_output,
    scanner_row_from_analysis,
    sort_scanner_rows,
)
from core.scanner_ai_auditor import (
    build_ai_setup_audit_prompt,
    parse_ai_setup_audit,
)
from core.backtest_config import serialize_backtest_config
from core.execution_revalidation_engine import revalidate_execution
from core.portfolio_risk_engine import evaluate_portfolio_risk
from core.scanner_candidate_engine import build_candidate_order_payload
from core.scanner_ranking_engine import _find_scenario_for_side
from core.scanner_session_review import build_market_brief_prompt
from core.scanner_observability import (
    SCANNER_OBSERVABILITY_VERSION,
    attach_row_observability,
    build_analysis_document,
    create_scan_context,
    input_timestamps_from_candles,
    row_identity,
)
from core.scanner_rollout import (
    ROLLOUT_SHADOW,
    SCANNER_ROLLOUT_VERSION,
    ScannerRolloutPolicy,
    build_rollout_policy,
    build_shadow_report,
)
from core.scanner_safety import (
    AutoTradeSafetyDecision,
    BRANCH_BACKTEST_INVALID,
    evaluate_auto_trade_safety,
)
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput, contract_size_override_for_symbol, position_sizing, recalc_execution_lot, calculate_current_effective_rr
from services.ai_service import AIProviderConfig, AIService
from services.journal_service import JournalService
from services.market_data_service import fetch_macro_correlation_context
from services.mt5_service import MT5Service
from services.news_service import NewsService
from services.observability_service import (
    StructuredObservabilityService,
    structured_observability,
)
from services.scanner_rollout_service import (
    ScannerRolloutMetricsService,
    scanner_rollout_metrics,
)
from services.settings_service import SettingsService
from services.storage_service import JsonStorage
from services.telegram_alert_service import TelegramAlertService
from workers.scanner_worker import ScannerWorker


def _serialized_execution(method):
    """Serialize live order checks so concurrent callers share fresh state."""

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._execution_lock:
            return method(self, *args, **kwargs)

    return wrapper


class ScannerController:
    def __init__(
        self,
        settings_service: SettingsService | None = None,
        mt5: MT5Service | None = None,
        news_service: NewsService | None = None,
        telegram_service: TelegramAlertService | None = None,
        journal_service: JournalService | None = None,
        orders_screen = None,
        observability_service: StructuredObservabilityService | None = None,
        rollout_metrics_service: ScannerRolloutMetricsService | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.mt5: MT5Service = mt5 or MT5Service()
        self.news_service = news_service or NewsService()
        self.telegram_service = telegram_service or TelegramAlertService()
        self.journal_service = journal_service or JournalService()
        self.orders_screen = orders_screen
        self.observability = observability_service or structured_observability
        self.rollout_metrics = (
            rollout_metrics_service or scanner_rollout_metrics
        )
        self._execution_lock = RLock()
        self._active_rollout_policy: ScannerRolloutPolicy | None = None

    def create_scan_worker(self, request: ScannerRequest) -> tuple[QThread, ScannerWorker]:
        thread = QThread()
        worker = ScannerWorker(self.run_market_scan, {"request": request})
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
    ) -> dict[str, Any]:
        progress = _progress_callback or (lambda _percent, _message: None)
        settings = self.settings_service.load()
        effective_risk_percent = min(
            max(float(request.risk_percent), 0.0),
            max(float(settings.trading.max_risk_percent), 0.0),
        )
        request = replace(request, risk_percent=effective_risk_percent)
        scan_context = create_scan_context(settings, request)
        self._emit_observability(
            "SCAN_STARTED",
            scan_id=scan_context.scan_id,
            payload={
                "request_hash": scan_context.request_hash,
                "settings_hash": scan_context.settings_hash,
                "symbols": list(request.symbols),
                "smc_scoring_mode": scan_context.smc_scoring_mode,
                "smc_scorer_version": scan_context.smc_scorer_version,
                "smc_domain_version": scan_context.smc_domain_version,
            },
        )
        progress(8, "Đang kiểm tra kết nối dữ liệu...")
        status = self.mt5.connection_status()
        if not status.connected or not status.logged_in:
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
            raise RuntimeError(f"{status.provider_name} chưa kết nối đầy đủ hoặc chưa đăng nhập.")
        rollout_settings = getattr(settings, "scanner_rollout", None)
        try:
            pre_scan_readiness = self.rollout_metrics.readiness(
                rollout_settings
            )
            pre_scan_canary_readiness = (
                self.rollout_metrics.canary_readiness(
                    rollout_settings
                )
            )
            release_ready = pre_scan_readiness.get("ready") is True
            canary_ready = (
                pre_scan_canary_readiness.get("ready") is True
            )
        except Exception:
            pre_scan_readiness = {
                "ready": False,
                "block_codes": ["ROLLOUT_METRICS_UNAVAILABLE"],
            }
            pre_scan_canary_readiness = dict(pre_scan_readiness)
            release_ready = False
            canary_ready = False
        rollout_policy = build_rollout_policy(
            rollout_settings,
            server=status.server,
            canary_ready=canary_ready,
            release_ready=release_ready,
        )
        self._active_rollout_policy = rollout_policy
        self._emit_observability(
            "ROLLOUT_POLICY_EVALUATED",
            scan_id=scan_context.scan_id,
            payload=rollout_policy.to_dict(),
        )
        mt5_balance = self.mt5.account_balance()
        if mt5_balance is None:
            self._emit_observability(
                "DATA_FETCH_FAILURE",
                scan_id=scan_context.scan_id,
                severity="ERROR",
                payload={"stage": "account_balance"},
            )
            raise RuntimeError("Không lấy được số dư từ tài khoản.")
        try:
            scan_portfolio = self.mt5.portfolio_snapshot()
            portfolio_state = scan_portfolio.to_dict()
        except Exception as exc:
            portfolio_state = {
                "available": False,
                "reason_codes": ["PORTFOLIO_STATE_UNAVAILABLE"],
                "reason": str(exc),
            }

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
            ))

        with ThreadPoolExecutor(max_workers=2) as _bg:
            _corr_future = _bg.submit(fetch_macro_correlation_context)
            _preload_future = _bg.submit(
                self.news_service.preload_macro_contexts,
                request.symbols,
                progress_callback=lambda p, m: progress(min(14 + p // 10, 18), m),
                ai_service=ai_svc,
            )

            progress(12, "Đang đọc danh sách mã giao dịch...")
            available_symbols = self.mt5.available_symbols(market_watch_only=True)

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

        # ---- Phase 1: fetch MT5 data sequentially (MT5 works best single-threaded) ----
        packets: list[dict[str, Any] | None] = []
        for i, symbol in enumerate(request.symbols):
            progress(19 + int(i / total * 30), f"Đang tải dữ liệu {symbol} ({i + 1}/{total})...")
            try:
                pkt = _fetch_one_symbol_mt5(
                    symbol,
                    mt5=self.mt5,
                    available_symbols=available_symbols,
                    bars_by_timeframe=bars_by_timeframe,
                    news_service=self.news_service,
                    freshness=freshness,
                    ai_service=ai_svc,
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
            packets.append(pkt)

        # ---- Phase 2: analyze all symbols in parallel (CPU-only, no MT5) ----
        progress(49, "Đang phân tích kỹ thuật các cặp tiền...")
        analyze_kwargs = {
            "correlation_context": correlation_context,
            "freshness_multiplier": freshness_multiplier,
            "contract_size_overrides": settings.trading.contract_size_override,
            "analysis_input_kwargs": analysis_input_kwargs,
            "closed_trades": closed_trades,
            "account_guard_settings": account_guard_settings,
            "smc_scoring_mode": request.smc_scoring_mode,
        }

        with ThreadPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
            futures: dict[Any, int] = {}
            for i, pkt in enumerate(packets):
                symbol = request.symbols[i]
                if pkt is None:
                    row = blocked_scanner_row(symbol, "Không tìm thấy mã broker.")
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
                    row = blocked_scanner_row(symbol, f"Lỗi không mong đợi: {exc}")
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
                rows.append(row)

        for row in rows:
            symbol = str(row.get("symbol", ""))
            row["legacy_candidate_status"] = {
                "ready_now": "READY_NOW",
                "waiting_confirmation": "WAITING_CONFIRMATION",
                "watch_zone": "WATCH_ZONE",
                "blocked": "BLOCKED",
            }.get(
                str(row.get("scanner_group", "") or "").lower(),
                "DATA_UNAVAILABLE",
            )
            at_cfg = self._auto_trade_config(request, symbol)
            if at_cfg is not None and "auto_trade_config" not in row:
                row["auto_trade_config"] = dict(at_cfg)
            row["legacy_candidate_input"] = {
                "scanner_action": row.get("scanner_action"),
                "scanner_group": row.get("scanner_group"),
                "trade_permission": row.get("trade_permission"),
                "best_side": row.get("best_side"),
                "best_score": row.get("best_score"),
                "expected_effective_rr": row.get(
                    "expected_effective_rr"
                ),
                "market_regime": row.get("market_regime"),
            }
            row["scan_id"] = scan_context.scan_id
            row["row_id"] = row_identity(scan_context.scan_id, symbol)
            row["settings_hash"] = scan_context.settings_hash
            row["rollout_stage"] = rollout_policy.stage

        progress(74, "Đang áp dụng Strategy Router và execution filters...")
        rows = self._apply_scanner_filters(rows, request)
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
        shadow_report = build_shadow_report(
            rows,
            enabled=rollout_policy.shadow_compare_enabled,
            suppress_v2_orders=rollout_policy.stage == ROLLOUT_SHADOW,
        )
        for comparison in shadow_report.get("comparisons", []):
            self._emit_observability(
                "SHADOW_DECISION_COMPARISON",
                scan_id=scan_context.scan_id,
                symbol=str(comparison.get("symbol", "") or ""),
                severity=(
                    "WARNING"
                    if comparison.get("disagreement")
                    else "INFO"
                ),
                payload=comparison,
            )
        progress(78, "Đã xếp hạng lại candidate sau filters...")

        # AI Market Brief (1 call, after all individual audits)
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
                    AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key)
                ).analyze(brief_prompt, max_tokens=4000)
            except Exception as exc:
                market_brief_error = str(exc)
        elif not active_ai or not active_ai.api_key:
            market_brief_error = "Chưa cấu hình AI Provider hoặc API key trong Settings."

        progress(94, "Đang dựng bảng kết quả quét...")
        output = build_scanner_output(rows, request, 0)  # ai_called=0 since audit is now manual
        output["observability_version"] = SCANNER_OBSERVABILITY_VERSION
        output["scan_id"] = scan_context.scan_id
        output["scan_context"] = scan_context.to_dict()
        output["portfolio_state"] = portfolio_state
        output["rollout_version"] = SCANNER_ROLLOUT_VERSION
        output["rollout_policy"] = rollout_policy.to_dict()
        output["pre_scan_release_readiness"] = pre_scan_readiness
        output["pre_scan_canary_readiness"] = (
            pre_scan_canary_readiness
        )
        output["shadow_report"] = shadow_report
        output["market_brief"] = market_brief
        output["market_brief_error"] = market_brief_error
        auto_trade_results = (
            self._execute_auto_trades(
                rows,
                request,
                rollout_policy=rollout_policy,
            )
            if request.auto_trade_enabled
            else {
                "enabled": False,
                "attempted": 0,
                "opened": 0,
                "skipped": 0,
                "rollout_blocked": 0,
                "errors": [],
                "orders": [],
                "rollout_policy": rollout_policy.to_dict(),
            }
        )
        output["auto_trade_results"] = auto_trade_results
        try:
            output["rollout_metrics"] = self.rollout_metrics.record_scan(
                scan_id=scan_context.scan_id,
                shadow_report=shadow_report,
                auto_trade_results=auto_trade_results,
                rollout_policy=rollout_policy.to_dict(),
                closed_trades=closed_trades,
            )
            output["release_readiness"] = self.rollout_metrics.readiness(
                getattr(settings, "scanner_rollout", None)
            )
            output["canary_readiness"] = (
                self.rollout_metrics.canary_readiness(
                    getattr(settings, "scanner_rollout", None)
                )
            )
        except Exception as exc:
            output["rollout_metrics_error"] = str(exc)
            output["release_readiness"] = {
                "rollout_version": SCANNER_ROLLOUT_VERSION,
                "ready": False,
                "block_codes": ["ROLLOUT_METRICS_UNAVAILABLE"],
            }
            output["canary_readiness"] = dict(
                output["release_readiness"]
            )
            self._emit_observability(
                "ROLLOUT_METRICS_FAILURE",
                scan_id=scan_context.scan_id,
                severity="ERROR",
                payload={"reason": str(exc)},
            )
        output["telegram_alerts"] = self._send_telegram_alerts(rows)
        try:
            output["snapshot_path"] = str(self.save_snapshot(output))
        except Exception as exc:
            output["snapshot_error"] = str(exc)
            self._emit_observability(
                "SNAPSHOT_WRITE_FAILURE",
                scan_id=scan_context.scan_id,
                severity="ERROR",
                payload={"reason": str(exc)},
            )
        self._emit_observability(
            "SCAN_COMPLETED",
            scan_id=scan_context.scan_id,
            payload={
                "symbols_scanned": len(rows),
                "summary": output.get("summary", {}),
                "snapshot_path": output.get("snapshot_path", ""),
            },
        )
        return output

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
        """Annotate auto-trade safety without changing scanner decisions.

        Scanning and execution are deliberately separate in Phase 0.  A WATCH
        row remains visible as WATCH, but can never become an order candidate.
        """
        for row in rows:
            symbol = str(row.get("symbol", ""))
            at_cfg = self._auto_trade_config(request, symbol)
            decision = self._auto_trade_safety_decision(row, at_cfg)
            row["auto_trade_branch"] = decision.branch
            row["strategy_config_status"] = decision.strategy.config_status
            row["backtest_config_status"] = (
                "BACKTEST_CONFIG_INVALID"
                if decision.branch == BRANCH_BACKTEST_INVALID
                else decision.strategy.config_status
            )
            row["candidate_status"] = decision.status
            row["selected_side"] = decision.selected_side
            row["auto_trade_candidate"] = decision.auto_trade_candidate
            row["strategy_eligible"] = decision.strategy_eligible
            row["execution_ready"] = decision.execution_ready
            row["trade_allowed"] = decision.trade_allowed
            row["auto_trade_selected_side"] = decision.selected_side
            row["auto_trade_reason_codes"] = list(decision.reason_codes)
            row["scanner_candidate_decision"] = decision.to_dict()
            candidate_payload = build_candidate_order_payload(
                row,
                decision,
            )
            if isinstance(candidate_payload, dict):
                candidate_payload.pop("analysis_result", None)
            row["candidate_order_payload"] = candidate_payload

        return sort_scanner_rows(rows)

    @_serialized_execution
    def execute_order_candidate(
        self,
        proposal: dict[str, Any],
        *,
        risk_percent: float | None = None,
        comment: str = "AMA",
    ) -> dict[str, Any]:
        """Revalidate and execute one scan proposal through the shared gate."""

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
                "rollout_stage": order.get("rollout_stage"),
                "rollout_version": order.get("rollout_version"),
            },
        )
        settings = self.settings_service.load()
        rollout_policy: ScannerRolloutPolicy | None = None
        rollout_decision = None
        rollout_settings = getattr(settings, "scanner_rollout", None)
        if rollout_settings is not None:
            try:
                rollout_status = self.mt5.connection_status()
                rollout_server = getattr(rollout_status, "server", "")
            except Exception:
                rollout_server = ""
            try:
                execution_canary_ready = (
                    self.rollout_metrics.canary_readiness(
                        rollout_settings
                    ).get("ready") is True
                )
                execution_release_ready = (
                    self.rollout_metrics.readiness(
                        rollout_settings
                    ).get("ready") is True
                )
            except Exception:
                execution_canary_ready = False
                execution_release_ready = False
            rollout_policy = build_rollout_policy(
                rollout_settings,
                server=rollout_server,
                canary_ready=execution_canary_ready,
                release_ready=execution_release_ready,
            )
            rollout_decision = rollout_policy.order_decision(
                symbol,
                requested=True,
            )
            if not rollout_decision.allowed:
                blocked = {
                    "success": False,
                    "symbol": symbol,
                    "broker_symbol": broker_symbol,
                    "side": side,
                    "scan_id": scan_id,
                    "row_id": row_id,
                    "rollout": rollout_decision.to_dict(),
                    "message": (
                        "Rollout guard blocked order: "
                        + ", ".join(rollout_decision.reason_codes)
                    ),
                }
                self._emit_observability(
                    "ROLLOUT_ORDER_BLOCKED",
                    scan_id=scan_id,
                    symbol=symbol,
                    severity="WARNING",
                    payload=blocked,
                )
                self._emit_observability(
                    "ORDER_RESPONSE",
                    scan_id=scan_id,
                    symbol=symbol,
                    severity="WARNING",
                    payload={
                        "row_id": row_id,
                        "success": False,
                        "message": blocked["message"],
                        "rollout": rollout_decision.to_dict(),
                    },
                )
                return blocked
            if rollout_decision.risk_cap_percent is not None:
                requested_risk = (
                    float(risk_percent)
                    if risk_percent is not None
                    else float(settings.trading.default_risk_percent)
                )
                risk_percent = min(
                    requested_risk,
                    rollout_decision.risk_cap_percent,
                )

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
            "rollout": (
                rollout_decision.to_dict()
                if rollout_decision is not None
                else None
            ),
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
        try:
            mt5_result = self.mt5.place_market_order(
                symbol=symbol,
                broker_symbol=broker_symbol,
                side=side,
                volume=float(order["volume"]),
                stop_loss=float(order["stop_loss"]),
                take_profit=float(order["take_profit"]),
                comment=comment,
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
        })
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
        *,
        rollout_policy: ScannerRolloutPolicy,
    ) -> dict[str, Any]:
        """Execute every eligible row through Phase-3 realtime revalidation."""

        results: list[dict[str, Any]] = []
        errors: list[str] = []
        diagnostics: list[dict[str, Any]] = []
        attempted = opened = skipped = rollout_blocked = 0
        for row in rows:
            symbol = str(row.get("symbol") or "--")
            config = self._auto_trade_config(request, symbol)
            decision = self._auto_trade_safety_decision(row, config)
            if not decision.auto_trade_candidate:
                continue

            attempted += 1
            rollout_decision = rollout_policy.order_decision(
                symbol,
                requested=request.auto_trade_enabled,
            )
            if not rollout_decision.allowed:
                rollout_blocked += 1
                skipped += 1
                blocked = {
                    "success": False,
                    "symbol": symbol,
                    "scan_id": row.get("scan_id"),
                    "row_id": row.get("row_id"),
                    "rollout": rollout_decision.to_dict(),
                    "message": (
                        "Rollout guard blocked order: "
                        + ", ".join(rollout_decision.reason_codes)
                    ),
                }
                results.append(blocked)
                errors.append(f"{symbol}: {blocked['message']}")
                self._emit_observability(
                    "ROLLOUT_ORDER_BLOCKED",
                    scan_id=str(row.get("scan_id", "") or ""),
                    symbol=symbol,
                    severity="WARNING",
                    payload=blocked,
                )
                continue
            proposal = build_candidate_order_payload(
                row,
                decision,
                require_price_in_zone=False,
            )
            if proposal is None:
                skipped += 1
                errors.append(f"{symbol}: order proposal không hợp lệ.")
                continue
            proposal.update({
                "execution_origin": "AUTO_TRADE",
                "rollout_version": SCANNER_ROLLOUT_VERSION,
                "rollout_stage": rollout_policy.stage,
            })
            effective_risk = request.risk_percent
            if rollout_decision.risk_cap_percent is not None:
                effective_risk = min(
                    effective_risk,
                    rollout_decision.risk_cap_percent,
                )

            try:
                result = self.execute_order_candidate(
                    proposal,
                    risk_percent=effective_risk,
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
                if self.orders_screen is not None:
                    try:
                        position_id = int(
                            result.get("position_id")
                            or result.get("ticket")
                            or result.get("order_id")
                            or 0
                        )
                        if position_id > 0:
                            validation = result.get("revalidation", {})
                            analysis = row.get("analysis_result", {})
                            technical = (
                                analysis.get("technical", {})
                                if isinstance(analysis, dict)
                                else {}
                            )
                            self.orders_screen.auto_enable_tracking(
                                position_id,
                                symbol,
                                str(result.get("side") or ""),
                                float(
                                    validation.get("execution_price")
                                    if isinstance(validation, dict)
                                    else 0.0
                                ),
                                float(result.get("stop_loss") or 0.0),
                                float(
                                    technical.get("atr_h1", 0.0)
                                    if isinstance(technical, dict)
                                    else 0.0
                                ),
                            )
                    except Exception:
                        pass
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
            "rollout_blocked": rollout_blocked,
            "errors": errors,
            "orders": results,
            "diagnostics": diagnostics,
            "risk_percent": request.risk_percent,
            "effective_risk_cap_percent": (
                rollout_policy.canary_risk_percent
                if rollout_policy.stage == "CANARY"
                else None
            ),
            "rollout_policy": rollout_policy.to_dict(),
        }

    def _is_auto_trade_candidate(self, row: dict[str, Any], at_cfg: dict[str, object] | None) -> bool:
        """Compatibility wrapper around the shared Phase-0 safety contract."""
        return self._auto_trade_safety_decision(row, at_cfg).auto_trade_candidate

    @staticmethod
    def _auto_trade_safety_decision(
        row: dict[str, Any],
        at_cfg: dict[str, object] | None,
    ) -> AutoTradeSafetyDecision:
        return evaluate_auto_trade_safety(row, at_cfg)

    def _get_alert_order_candidates(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return order candidates captured by the canonical scan decision."""
        candidates: list[dict[str, Any]] = []
        for row in rows:
            stored = row.get("candidate_order_payload")
            if not isinstance(stored, dict):
                # Compatibility for old snapshots created before the
                # canonical payload was persisted. This path only prepares an
                # alert/preview payload and never grants execution permission.
                scenario = self._best_scenario(row)
                final_zone = self._final_execution_zone(scenario)
                if not scenario or final_zone is None:
                    continue
                raw_tp = scenario.get("take_profit")
                take_profit = (
                    raw_tp[0]
                    if isinstance(raw_tp, list) and raw_tp
                    else raw_tp
                )
                sizing = scenario.get("position_sizing")
                if not isinstance(sizing, dict):
                    sizing = {}
                stored = {
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
                    "risk_reward_range": scenario.get(
                        "risk_reward_range"
                    ),
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
                    "entry_zone_width": scenario.get(
                        "entry_zone_width"
                    ),
                    "entry_zone_width_atr": scenario.get(
                        "entry_zone_width_atr"
                    ),
                    "price_digits": scenario.get("price_digits"),
                    "invalid_reason": scenario.get("invalid_reason"),
                    "analysis_result": row.get("analysis_result"),
                }
            payload = dict(stored)
            payload.update({
                "rank": row.get("rank"),
                "candidate_status": row.get("candidate_status"),
                "opportunity_rank": row.get("opportunity_rank"),
                "evidence_confidence": row.get("evidence_confidence"),
                "execution_readiness": row.get("execution_readiness"),
                "strategy_branch": row.get("auto_trade_branch"),
                "config_health": row.get("strategy_config_status"),
                "ranking_version": row.get("ranking_version"),
            })
            payload["best_score"] = int(payload.get("best_score") or 0)
            candidates.append(payload)

        return candidates

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

    def _send_telegram_alerts(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        notifications = self.settings_service.load().notifications
        # Filter using the SAME gates as "Hiển thị lệnh" dialog
        candidates = self._get_alert_order_candidates(rows)
        result = self.telegram_service.send_order_alerts(
            candidates,
            bot_token=notifications.telegram_bot_token,
            chat_ids=notifications.telegram_chat_ids,
        )
        summary_sent = self.telegram_service.send_summary_alert(
            rows,
            candidates=candidates,
            bot_token=notifications.telegram_bot_token,
            chat_ids=notifications.telegram_chat_ids,
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        return {"attempted": result.attempted, "sent": result.sent, "errors": result.errors, "summary_sent": summary_sent}

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
        legacy = str(row.get("legacy_candidate_status", "") or "")
        canonical = str(row.get("candidate_status", "") or "")
        if legacy and canonical and legacy != canonical:
            self._emit_observability(
                "DECISION_DISAGREEMENT",
                scan_id=scan_id,
                symbol=symbol,
                severity="WARNING",
                payload={
                    "v1_status": legacy,
                    "v2_status": canonical,
                    "selected_side": row.get("selected_side"),
                    "reason_codes": row.get("auto_trade_reason_codes", []),
                },
            )
        smc_scoring = (
            analysis.get("smc_scoring")
            if isinstance(analysis.get("smc_scoring"), dict)
            else {}
        )
        smc_policy = (
            smc_scoring.get("policy")
            if isinstance(smc_scoring.get("policy"), dict)
            else {}
        )
        if smc_policy.get("shadow_enabled") is True:
            comparison = (
                smc_scoring.get("comparison")
                if isinstance(smc_scoring.get("comparison"), dict)
                else {}
            )
            self._emit_observability(
                "SMC_SHADOW_COMPARISON",
                scan_id=scan_id,
                symbol=symbol,
                severity=(
                    "WARNING"
                    if comparison.get("best_side_changed")
                    else "INFO"
                ),
                payload={
                    "policy": smc_policy,
                    "shadow_status": smc_scoring.get("shadow_status"),
                    "comparison": comparison,
                    "active": smc_scoring.get("active", {}),
                    "shadow": smc_scoring.get("shadow", {}),
                    "consumer_contract": smc_scoring.get(
                        "consumer_contract",
                        {},
                    ),
                },
            )

    def save_snapshot(self, result: dict[str, Any]) -> Path:
        scan_id = str(result.get("scan_id", "") or "").strip()
        if not scan_id:
            scan_id = str(result.get("timestamp", "scanner")).replace(
                ":", ""
            ).replace("+", "_")
        snapshot_dir = app_data_dir() / "scanner_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        analysis_dir = app_data_dir() / "scanner_analysis" / scan_id
        analysis_dir.mkdir(parents=True, exist_ok=True)
        context = (
            result.get("scan_context")
            if isinstance(result.get("scan_context"), dict)
            else {}
        )
        manifest: dict[str, str] = {}
        for row in result.get("rows", []):
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol", "UNKNOWN") or "UNKNOWN")
            safe_symbol = "".join(
                character
                for character in symbol.upper()
                if character.isalnum()
            ) or "UNKNOWN"
            analysis_path = analysis_dir / f"{safe_symbol}.json"
            JsonStorage(analysis_path).save(
                build_analysis_document(row, context)
            )
            manifest[symbol] = str(analysis_path)

        path = snapshot_dir / f"scanner_{scan_id}.json"
        JsonStorage(path).save(self._snapshot_payload(result, manifest))
        return path

    def _write_scanner_ai_audit(self, row: dict[str, Any], active_ai) -> dict[str, Any]:
        prompt = build_ai_setup_audit_prompt(row)
        try:
            raw = AIService(AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key)).analyze(prompt, max_tokens=4000)
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
    ) -> dict[str, Any]:
        payload = dict(result)
        references = manifest or {}
        payload["rows"] = [
            {
                **{
                    key: value
                    for key, value in row.items()
                    if key != "analysis_result"
                },
                "analysis_ref": references.get(str(row.get("symbol", "")), ""),
            }
            for row in result.get("rows", [])
            if isinstance(row, dict)
        ]
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
    smc_scoring_mode: str = "v2",
) -> dict[str, Any]:
    """Process a single symbol — safe for ThreadPoolExecutor (each thread inits its own MT5)."""
    import MetaTrader5 as _mt5

    _mt5_ok = _mt5.initialize()
    try:
        mt5_svc = MT5Service()
        broker_symbol = mt5_svc.resolve_symbol(symbol, available_symbols)
        if not broker_symbol:
            return blocked_scanner_row(symbol, "Không tìm thấy mã broker.")

        all_candles = mt5_svc.load_primary_timeframes(
            broker_symbol,
            {**bars_by_timeframe, "M15": 200},
        )
        candles = {tf: all_candles[tf] for tf in bars_by_timeframe}
        m15_candles = all_candles["M15"]
        data_quality = mt5_svc.symbol_data_quality(symbol, broker_symbol)
        news_flags = news_service.data_quality_flags(symbol)
        macro_context = news_flags.pop("macro_context", {"events": []})
        data_quality.update(news_flags)
        data_quality["macro_freshness"] = freshness

        contract_override = contract_size_override_for_symbol(
            symbol,
            data_quality,
            contract_size_overrides,
        )
        analysis_input = AnalysisInput(
            symbol=symbol,
            broker_symbol=broker_symbol,
            **analysis_input_kwargs,
            contract_size_override=float(contract_override) if contract_override else None,
        )
        macro_alignment = macro_context.get("macro_alignment_scores") if isinstance(macro_context, dict) else None
        macro_confidence = float(macro_context.get("macro_data_quality", 1.0)) if isinstance(macro_context, dict) else 1.0
        macro_confidence = macro_confidence * freshness_multiplier
        quote_currency = symbol.split("/")[-1] if "/" in symbol else symbol[-3:]
        quote_to_usd = mt5_svc.quote_to_usd_rate(quote_currency)

        result = analyze_symbol(
            analysis_input,
            candles,
            data_quality=data_quality,
            macro_alignment=macro_alignment if isinstance(macro_alignment, dict) else None,
            macro_confidence=macro_confidence,
            m15_candles=m15_candles,
            correlation_context=correlation_context,
            quote_to_usd_rate=quote_to_usd,
            closed_trades=closed_trades,
            open_trades=[],
            account_guard_settings=account_guard_settings,
            thresholds=thresholds,
            smc_scoring_mode=smc_scoring_mode,
        )
        result["economic_events"] = macro_context.get("events", [])
        result["macro"]["driver_context"] = macro_context
        if isinstance(macro_context, dict):
            result["macro"]["macro_tier_detail"] = macro_context.get("macro_tier_detail", {})
            result["macro"]["macro_data_quality"] = macro_context.get("macro_data_quality", 1.0)
        row = scanner_row_from_analysis(result, broker_symbol=broker_symbol)
        return row
    except Exception as exc:
        broker_symbol = None
        try:
            temp = MT5Service()
            broker_symbol = temp.resolve_symbol(symbol, available_symbols)
        except Exception:
            pass
        return blocked_scanner_row(symbol, f"Không quét được dữ liệu: {exc}", broker_symbol=broker_symbol)
    finally:
        if _mt5_ok:
            _mt5.shutdown()


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
) -> dict[str, Any] | None:
    """Fetch MT5 data for one symbol on the main thread.  Returns a data packet
    consumed by ``_analyze_one_symbol``, or ``None`` if the symbol can't be resolved."""
    broker_symbol = mt5.resolve_symbol(symbol, available_symbols)
    if not broker_symbol:
        return None

    all_candles = mt5.load_primary_timeframes(
        broker_symbol, {**bars_by_timeframe, "M15": 100},
    )
    data_quality = mt5.symbol_data_quality(symbol, broker_symbol)
    news_flags = news_service.data_quality_flags(symbol, ai_service=ai_service)
    macro_context = news_flags.pop("macro_context", {"events": []})
    data_quality.update(news_flags)
    data_quality["macro_freshness"] = freshness
    quote_currency = symbol.split("/")[-1] if "/" in symbol else symbol[-3:]
    quote_to_usd = mt5.quote_to_usd_rate(quote_currency)

    return {
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "candles": {tf: all_candles[tf] for tf in bars_by_timeframe},
        "m15_candles": all_candles["M15"],
        "data_quality": data_quality,
        "macro_context": macro_context,
        "quote_to_usd": quote_to_usd,
        "input_timestamps": input_timestamps_from_candles(all_candles),
    }


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
    smc_scoring_mode: str = "v2",
) -> dict[str, Any]:
    """Run the analysis pipeline for one symbol (CPU-only, thread-safe)."""
    started_at = perf_counter()
    symbol = pkt["symbol"]
    broker_symbol = pkt["broker_symbol"]
    data_quality = pkt["data_quality"]
    macro_context = pkt["macro_context"]

    contract_override = contract_size_override_for_symbol(
        symbol, data_quality, contract_size_overrides,
    )
    analysis_input = AnalysisInput(
        symbol=symbol,
        broker_symbol=broker_symbol,
        **analysis_input_kwargs,
        contract_size_override=float(contract_override) if contract_override else None,
    )
    macro_alignment = macro_context.get("macro_alignment_scores") if isinstance(macro_context, dict) else None
    macro_confidence = float(macro_context.get("macro_data_quality", 1.0)) if isinstance(macro_context, dict) else 1.0
    macro_confidence = macro_confidence * freshness_multiplier

    try:
        result = analyze_symbol(
            analysis_input,
            pkt["candles"],
            data_quality=data_quality,
            macro_alignment=macro_alignment if isinstance(macro_alignment, dict) else None,
            macro_confidence=macro_confidence,
            m15_candles=pkt["m15_candles"],
            correlation_context=correlation_context,
            quote_to_usd_rate=pkt["quote_to_usd"],
            closed_trades=closed_trades,
            open_trades=[],
            account_guard_settings=account_guard_settings,
            thresholds=thresholds,
            smc_scoring_mode=smc_scoring_mode,
        )
    except Exception as exc:
        blocked = blocked_scanner_row(
            symbol,
            f"Không quét được dữ liệu: {exc}",
            broker_symbol=broker_symbol,
        )
        blocked["_analysis_error"] = str(exc)
        blocked["input_timestamps"] = dict(
            pkt.get("input_timestamps", {})
        )
        blocked["analysis_latency_ms"] = round(
            (perf_counter() - started_at) * 1000,
            3,
        )
        return blocked

    result["economic_events"] = macro_context.get("events", [])
    result["macro"]["driver_context"] = macro_context
    if isinstance(macro_context, dict):
        result["macro"]["macro_tier_detail"] = macro_context.get("macro_tier_detail", {})
        result["macro"]["macro_data_quality"] = macro_context.get("macro_data_quality", 1.0)
    row = scanner_row_from_analysis(result, broker_symbol=broker_symbol)
    row["input_timestamps"] = dict(pkt.get("input_timestamps", {}))
    row["analysis_latency_ms"] = round(
        (perf_counter() - started_at) * 1000,
        3,
    )
    return row

