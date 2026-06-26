from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, replace
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
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
from core.scanner_session_review import build_market_brief_prompt
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput, contract_size_override_for_symbol
from services.ai_service import AIProviderConfig, AIService
from services.data_provider import DataProvider
from services.journal_service import JournalService
from services.market_data_service import fetch_macro_correlation_context
from services.mt5_service import MT5Service
from services.news_service import NewsService
from services.settings_service import SettingsService
from services.storage_service import JsonStorage
from services.telegram_alert_service import TelegramAlertService
from workers.scanner_worker import ScannerWorker


class ScannerController:
    def __init__(
        self,
        settings_service: SettingsService | None = None,
        data_provider: DataProvider | None = None,
        news_service: NewsService | None = None,
        telegram_service: TelegramAlertService | None = None,
        journal_service: JournalService | None = None,
        # Backward compat: accept mt5_service kwarg and use it as data_provider
        mt5_service: MT5Service | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.data_provider: DataProvider = data_provider or mt5_service or MT5Service()
        self.mt5_service = self.data_provider
        self.news_service = news_service or NewsService()
        self.telegram_service = telegram_service or TelegramAlertService()
        self.journal_service = journal_service or JournalService()

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
        progress(8, "Đang kiểm tra kết nối dữ liệu...")
        status = self.data_provider.connection_status()
        if not status.connected or not status.logged_in:
            raise RuntimeError(f"{status.provider_name} chưa kết nối đầy đủ hoặc chưa đăng nhập.")
        mt5_balance = self.data_provider.account_balance()
        if mt5_balance is None:
            raise RuntimeError("Không lấy được số dư từ tài khoản.")

        bars_by_timeframe = {
            "D1": settings.advanced.d1_bars,
            "H4": settings.advanced.h4_bars,
            "H1": settings.advanced.h1_bars,
        }

        # ---- Kick off background I/O immediately (runs while we do MT5 setup) ----
        with ThreadPoolExecutor(max_workers=2) as _bg:
            _corr_future = _bg.submit(fetch_macro_correlation_context)
            _preload_future = _bg.submit(
                self.news_service.preload_macro_contexts,
                request.symbols,
                progress_callback=lambda p, m: progress(min(14 + p // 10, 18), m),
            )

            progress(12, "Đang đọc danh sách mã giao dịch...")
            available_symbols = self.data_provider.available_symbols(market_watch_only=True)

            # Wait for background I/O to complete before proceeding
            progress(14, "Đang tải dữ liệu thị trường Mỹ...")
            correlation_context = _corr_future.result()
            _preload_future.result()

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
                    data_provider=self.data_provider,
                    available_symbols=available_symbols,
                    bars_by_timeframe=bars_by_timeframe,
                    news_service=self.news_service,
                    freshness=freshness,
                )
            except Exception:
                pkt = None
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
        }

        with ThreadPoolExecutor(max_workers=min(6, os.cpu_count() or 4)) as ex:
            futures: dict[Any, int] = {}
            for i, pkt in enumerate(packets):
                symbol = request.symbols[i]
                if pkt is None:
                    rows.append(blocked_scanner_row(symbol, "Không tìm thấy mã broker."))
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
                row = self._apply_symbol_override(row, request.symbol_auto_trade.get(symbol))
                rows.append(row)

        progress(74, "Đang xếp hạng setup theo rule engine...")
        rows = sort_scanner_rows(rows)

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
        output["market_brief"] = market_brief
        output["market_brief_error"] = market_brief_error
        output["auto_trade_results"] = self._execute_auto_trades(rows, request) if request.auto_trade_enabled else {
            "enabled": False,
            "attempted": 0,
            "opened": 0,
            "skipped": 0,
            "errors": [],
            "orders": [],
        }
        output["telegram_alerts"] = self._send_telegram_alerts(rows)
        return output

    @staticmethod
    def _auto_trade_config(request: ScannerRequest, symbol: str) -> dict[str, object] | None:
        """Return per-symbol auto-trade config, or None if not configured."""
        cfg = request.symbol_auto_trade.get(symbol) if request.symbol_auto_trade else None
        if not cfg:
            return None
        regime = str(cfg.get("regime", "")).strip().lower()
        side = str(cfg.get("side", "")).strip().lower()
        min_rr = float(cfg.get("min_rr", 0) or 0)
        # Return config if ANY auto-trade filter is explicitly configured
        if not regime and side not in ("buy", "sell") and not min_rr:
            return None
        return cfg

    def _apply_symbol_override(self, row: dict[str, Any], cfg: dict[str, object] | None) -> dict[str, Any]:
        """Apply per-symbol backtest-driven override from Settings.

        If cfg is provided and the row's current action is ``stand_aside``,
        check whether the setup matches the configured conditions (regime,
        side, min_rr, min_score).  When ALL conditions match, upgrade the
        action from ``stand_aside`` to ``ready``.

        This replaces the old hard-coded ``range + buy + RR>=2.0 + score>=50``
        override with per-symbol configuration sourced from backtest results.
        """
        if cfg is None:
            return row
        if not isinstance(cfg, dict):
            return row

        action = str(row.get("scanner_action") or "")
        if action != "stand_aside":
            return row

        cfg_regime = str(cfg.get("regime", "")).strip().lower()
        cfg_side = str(cfg.get("side", "")).strip().lower()
        cfg_min_rr = float(cfg.get("min_rr", 0) or 0)
        cfg_min_score = int(cfg.get("min_score", 0) or 0)

        # No conditions configured — nothing to override
        if not cfg_regime and cfg_side not in ("buy", "sell") and not cfg_min_rr and not cfg_min_score:
            return row

        # Regime check
        actual_regime = str(row.get("market_regime", "")).strip().lower()
        if cfg_regime and actual_regime != cfg_regime:
            return row

        # Side check
        actual_side = str(row.get("best_side", "")).strip().lower()
        if cfg_side in ("buy", "sell") and actual_side != cfg_side:
            return row

        # Min score check
        if cfg_min_score > 0:
            try:
                score = int(row.get("final_score", row.get("best_score", 0)))
            except (TypeError, ValueError):
                score = 0
            if score < cfg_min_score:
                return row

        # Min RR check
        if cfg_min_rr > 0:
            try:
                rr = float(row.get("expected_effective_rr", 0) or 0)
            except (TypeError, ValueError):
                rr = 0.0
            if rr < cfg_min_rr:
                return row

        # Gate/permission must not be blocked
        if str(row.get("trade_permission", "")).strip().lower() == "blocked":
            return row

        # All conditions matched — upgrade
        row["scanner_action"] = "ready"
        row["scanner_group"] = "ready_now"
        row["display_action"] = "ready"
        row["scanner_decision"] = "READY_TO_TRADE"
        row["short_reason"] = "Nâng cấp bởi cấu hình backtest"
        return row

    def _execute_auto_trades(self, rows: list[dict[str, Any]], request: ScannerRequest) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors: list[str] = []
        attempted = 0
        opened = 0
        skipped = 0

        for row in rows:
            at_cfg = self._auto_trade_config(request, str(row.get("symbol", "")))
            if not self._is_auto_trade_candidate(row, at_cfg):
                continue
            attempted += 1
            symbol = str(row.get("symbol") or "--")
            broker_symbol = str(row.get("broker_symbol") or "").strip()
            trade_side = str(at_cfg.get("side", "")).strip().lower() if at_cfg else ""
            if trade_side not in ("buy", "sell"):
                trade_side = str(row.get("best_side") or "")
            scenario = self._best_scenario(row, force_side=trade_side)
            sizing = scenario.get("position_sizing", {}) if isinstance(scenario.get("position_sizing"), dict) else {}
            take_profit = scenario.get("take_profit")
            first_tp = take_profit[0] if isinstance(take_profit, list) and take_profit else take_profit

            try:
                volume = float(sizing.get("suggested_lot") or 0.0)
                stop_loss = float(scenario.get("stop_loss"))
                tp = float(first_tp)
            except (TypeError, ValueError):
                skipped += 1
                errors.append(f"{symbol}: thiếu lot/SL/TP hợp lệ, bỏ qua auto trade.")
                continue

            if not broker_symbol:
                skipped += 1
                errors.append(f"{symbol}: thiếu broker symbol, bỏ qua auto trade.")
                continue

            try:
                if self.data_provider.has_open_position_or_order(broker_symbol):
                    skipped += 1
                    results.append({
                        "success": False,
                        "symbol": symbol,
                        "broker_symbol": broker_symbol,
                        "side": trade_side,
                        "volume": volume,
                        "message": "Đã có lệnh/position cho mã này, không vào thêm.",
                    })
                    continue
                order = self.data_provider.place_market_order(
                    symbol=symbol,
                    broker_symbol=broker_symbol,
                    side=trade_side,
                    volume=volume,
                    stop_loss=stop_loss,
                    take_profit=tp,
                    comment=f"AMA {symbol}",
                )
                payload = asdict(order) if hasattr(order, "__dataclass_fields__") else dict(order)
                results.append(payload)
                if payload.get("success"):
                    opened += 1
                else:
                    skipped += 1
                    errors.append(f"{symbol}: {payload.get('message') or 'MT5 từ chối lệnh.'}")
            except Exception as exc:
                skipped += 1
                errors.append(f"{symbol}: {exc}")

        return {
            "enabled": True,
            "attempted": attempted,
            "opened": opened,
            "skipped": skipped,
            "errors": errors,
            "orders": results,
            "risk_percent": request.risk_percent,
        }

    def _is_auto_trade_candidate(self, row: dict[str, Any], at_cfg: dict[str, object] | None) -> bool:
        """Check if a scanner row qualifies for auto-trade.

        When *at_cfg* is provided (per-symbol config from Settings), uses
        backtest-proven filters: regime, side, min_rr.  Otherwise requires
        the original strict criteria (scanner_action == "ready").
        """
        if not isinstance(row.get("analysis_result"), dict):
            return False
        # Respect user's Min Score gate and trade permission blocks
        if row.get("scanner_group") == "blocked":
            return False
        if str(row.get("trade_permission", "")).strip().lower() == "blocked":
            return False
        journal_feedback = row.get("journal_feedback") if isinstance(row.get("journal_feedback"), dict) else {}
        if journal_feedback.get("decision_cap") in {"TRADE_BLOCKED", "WATCH_ONLY"}:
            return False

        if at_cfg is None:
            # No per-symbol config — fall back to original strict criteria
            return (
                row.get("scanner_action") == "ready"
                and row.get("trade_permission") == "allowed"
                and bool(self._best_scenario(row))
            )

        # Backtest-proven per-symbol filters
        cfg_regime = str(at_cfg.get("regime", "")).strip().lower()
        cfg_side = str(at_cfg.get("side", "")).strip().lower()
        cfg_min_rr = float(at_cfg.get("min_rr", 0) or 0)

        if cfg_regime and str(row.get("market_regime", "")).strip().lower() != cfg_regime:
            return False
        if cfg_min_rr > 0:
            expected_rr = _safe_float_for_auto(row.get("expected_effective_rr"))
            if expected_rr is None or expected_rr < cfg_min_rr:
                return False
        best_score = int(row.get("best_score", 0) or 0)
        cfg_min_score = int(at_cfg.get("min_score", 0) or 0)
        effective_min_score = cfg_min_score if cfg_min_score > 0 else 65
        if best_score < effective_min_score:
            return False

        # Determine trade side: config override or fall back to best_side
        trade_side = cfg_side if cfg_side in ("buy", "sell") else row.get("best_side")
        return bool(self._best_scenario(row, force_side=trade_side))

    def _best_scenario(self, row: dict[str, Any], *, force_side: str | None = None) -> dict[str, Any]:
        analysis = row.get("analysis_result", {})
        if not isinstance(analysis, dict):
            return {}
        scenarios = analysis.get("scenarios", [])
        if not isinstance(scenarios, list):
            return {}
        side = force_side or row.get("best_side")
        for scenario in scenarios:
            if isinstance(scenario, dict) and scenario.get("type") == side:
                return scenario
        # Fallback: if forced side not found, try best_side
        if force_side:
            fallback_side = row.get("best_side")
            for scenario in scenarios:
                if isinstance(scenario, dict) and scenario.get("type") == fallback_side:
                    return scenario
        return {}

    def _send_telegram_alerts(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        notifications = self.settings_service.load().notifications
        result = self.telegram_service.send_ready_trade_alerts(
            rows,
            bot_token=notifications.telegram_bot_token,
            chat_ids=notifications.telegram_chat_ids,
        )
        # Gui alert tong ket (luon gui, ke ca khi khong co ma ready)
        summary_sent = self.telegram_service.send_summary_alert(
            rows,
            bot_token=notifications.telegram_bot_token,
            chat_ids=notifications.telegram_chat_ids,
            timestamp=datetime.now().astimezone().isoformat(timespec="seconds"),
        )
        return {"attempted": result.attempted, "sent": result.sent, "errors": result.errors, "summary_sent": summary_sent}

    def save_snapshot(self, result: dict[str, Any]) -> Path:
        snapshot_dir = app_data_dir() / "scanner_snapshots"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = str(result.get("timestamp", "scanner")).replace(":", "").replace("+", "_")
        path = snapshot_dir / f"scanner_{timestamp}.json"
        JsonStorage(path).save(self._snapshot_payload(result))
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

    def _snapshot_payload(self, result: dict[str, Any]) -> dict[str, Any]:
        payload = dict(result)
        payload["rows"] = [
            {key: value for key, value in row.items() if key != "analysis_result"}
            for row in result.get("rows", [])
        ]
        return payload


def _safe_float_for_auto(value: object) -> float | None:
    """Safely convert a value to float, returning None on failure."""
    if value is None:
        return None
    try:
        result = float(value)
        if result != result or result == float("inf") or result == float("-inf"):
            return None
        return result
    except (TypeError, ValueError):
        return None


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
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Process a single symbol — safe for ThreadPoolExecutor (each thread inits its own MT5)."""
    import MetaTrader5 as _mt5

    _mt5_ok = _mt5.initialize()
    try:
        data_provider = MT5Service()
        broker_symbol = data_provider.resolve_symbol(symbol, available_symbols)
        if not broker_symbol:
            return blocked_scanner_row(symbol, "Không tìm thấy mã broker.")

        all_candles = data_provider.load_primary_timeframes(
            broker_symbol,
            {**bars_by_timeframe, "M15": 200},
        )
        candles = {tf: all_candles[tf] for tf in bars_by_timeframe}
        m15_candles = all_candles["M15"]
        data_quality = data_provider.symbol_data_quality(symbol, broker_symbol)
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
        quote_to_usd = data_provider.quote_to_usd_rate(quote_currency)

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
    data_provider: Any,
    available_symbols: list[str],
    bars_by_timeframe: dict[str, int],
    news_service: Any,
    freshness: dict[str, Any],
) -> dict[str, Any] | None:
    """Fetch MT5 data for one symbol on the main thread.  Returns a data packet
    consumed by ``_analyze_one_symbol``, or ``None`` if the symbol can't be resolved."""
    broker_symbol = data_provider.resolve_symbol(symbol, available_symbols)
    if not broker_symbol:
        return None

    all_candles = data_provider.load_primary_timeframes(
        broker_symbol, {**bars_by_timeframe, "M15": 100},
    )
    data_quality = data_provider.symbol_data_quality(symbol, broker_symbol)
    news_flags = news_service.data_quality_flags(symbol)
    macro_context = news_flags.pop("macro_context", {"events": []})
    data_quality.update(news_flags)
    data_quality["macro_freshness"] = freshness
    quote_currency = symbol.split("/")[-1] if "/" in symbol else symbol[-3:]
    quote_to_usd = data_provider.quote_to_usd_rate(quote_currency)

    return {
        "symbol": symbol,
        "broker_symbol": broker_symbol,
        "candles": {tf: all_candles[tf] for tf in bars_by_timeframe},
        "m15_candles": all_candles["M15"],
        "data_quality": data_quality,
        "macro_context": macro_context,
        "quote_to_usd": quote_to_usd,
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
    thresholds: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Run the analysis pipeline for one symbol (CPU-only, thread-safe)."""
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
        )
    except Exception as exc:
        return blocked_scanner_row(symbol, f"Không quét được dữ liệu: {exc}", broker_symbol=broker_symbol)

    result["economic_events"] = macro_context.get("events", [])
    result["macro"]["driver_context"] = macro_context
    if isinstance(macro_context, dict):
        result["macro"]["macro_tier_detail"] = macro_context.get("macro_tier_detail", {})
        result["macro"]["macro_data_quality"] = macro_context.get("macro_data_quality", 1.0)
    return scanner_row_from_analysis(result, broker_symbol=broker_symbol)

