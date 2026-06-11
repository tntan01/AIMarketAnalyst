from __future__ import annotations

from dataclasses import asdict, replace
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread

import yfinance as yf

from config.paths import app_data_dir
from core.scanner import (
    ScannerRequest,
    ai_targets,
    blocked_scanner_row,
    build_scanner_output,
    scanner_row_from_analysis,
    sort_scanner_rows,
)
from core.analysis_engine import analyze_symbol
from core.risk_engine import AnalysisInput, contract_size_override_for_symbol
from services.ai_service import AIProviderConfig, AIService
from services.journal_service import JournalService
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
        mt5_service: MT5Service | None = None,
        news_service: NewsService | None = None,
        telegram_service: TelegramAlertService | None = None,
        journal_service: JournalService | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.mt5_service = mt5_service or MT5Service()
        self.news_service = news_service or NewsService()
        self.telegram_service = telegram_service or TelegramAlertService()
        self.journal_service = journal_service

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
        progress(8, "Đang kiểm tra kết nối MetaTrader 5...")
        status = self.mt5_service.connection_status()
        if not status.terminal_connected or not status.logged_in:
            raise RuntimeError("MT5 chưa kết nối đầy đủ hoặc broker chưa đăng nhập.")
        mt5_balance = self.mt5_service.account_balance()
        if mt5_balance is None:
            raise RuntimeError("Không lấy được số dư từ tài khoản MT5.")

        bars_by_timeframe = {
            "D1": settings.advanced.d1_bars,
            "H4": settings.advanced.h4_bars,
            "H1": settings.advanced.h1_bars,
        }
        progress(12, "Đang đọc danh sách mã trong Market Watch...")
        available_symbols = self.mt5_service.available_symbols(market_watch_only=True)
        rows: list[dict[str, Any]] = []

        # Fetch DXY/VIX/US10Y MỘT LẦN cho toàn bộ scanner (song song)
        progress(14, "Đang tải dữ liệu thị trường Mỹ (DXY, VIX, US10Y)...")
        from concurrent.futures import ThreadPoolExecutor, as_completed
        correlation_context: dict = {"dxy_candles": None, "vix_candles": None, "us10y_candles": None}
        with ThreadPoolExecutor(max_workers=3) as ex:
            futures = {
                ex.submit(yf.download, "DX-Y.NYB", period="5d", interval="1d", progress=False): "dxy",
                ex.submit(yf.download, "^VIX", period="5d", interval="1d", progress=False): "vix",
                ex.submit(yf.download, "^TNX", period="5d", interval="1d", progress=False): "us10y",
            }
            for future in as_completed(futures):
                key = futures[future]
                try:
                    data = future.result()
                    correlation_context[f"{key}_candles"] = _parse_yf_candles(data)
                except Exception:
                    pass

        # Pre-fetch toan bo macro context 1 lan (RSS + calendar) de tai su dung trong vong lap
        progress(17, "Đang tải tin tức và phân tích vĩ mô...")
        self.news_service.preload_macro_contexts(request.symbols)
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

        progress(19, "Đang quét các cặp tiền...")
        total = max(1, len(request.symbols))
        for index, symbol in enumerate(request.symbols, start=1):
            progress(12 + int(index / total * 58), f"Đang quét {symbol} ({index}/{total})...")
            broker_symbol = self.mt5_service.resolve_symbol(symbol, available_symbols)
            if not broker_symbol:
                rows.append(blocked_scanner_row(symbol, "Không tìm thấy mã broker trong Market Watch."))
                continue

            try:
                all_candles = self.mt5_service.load_primary_timeframes(
                    broker_symbol,
                    {**bars_by_timeframe, "M15": 200},
                )
                candles = {tf: all_candles[tf] for tf in bars_by_timeframe}
                m15_candles = all_candles["M15"]
                data_quality = self.mt5_service.symbol_data_quality(symbol, broker_symbol)
                news_flags = self.news_service.data_quality_flags(symbol)
                macro_context = news_flags.pop("macro_context", {"events": []})
                data_quality.update(news_flags)
                data_quality["macro_freshness"] = freshness
                contract_override = contract_size_override_for_symbol(
                    symbol,
                    data_quality,
                    settings.trading.contract_size_override,
                )
                analysis_input = AnalysisInput(
                    symbol=symbol,
                    broker_symbol=broker_symbol,
                    account_balance=mt5_balance,
                    risk_percent=request.risk_percent,
                    account_currency=settings.trading.account_currency,
                    lot_step=settings.trading.lot_step,
                    minimum_lot=settings.trading.minimum_lot,
                    contract_size_override=float(contract_override) if contract_override else None,
                    timezone_name=request.timezone_name,
                )
                macro_alignment = macro_context.get("macro_alignment_scores") if isinstance(macro_context, dict) else None
                macro_confidence = float(macro_context.get("macro_data_quality", 1.0)) if isinstance(macro_context, dict) else 1.0
                macro_confidence = macro_confidence * freshness_multiplier
                quote_currency = symbol.split("/")[-1] if "/" in symbol else symbol[-3:]
                quote_to_usd_fn = getattr(self.mt5_service, "quote_to_usd_rate", None)
                quote_to_usd = quote_to_usd_fn(quote_currency) if callable(quote_to_usd_fn) else None
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
                    use_decision_engine_action=True,
                )
                result["economic_events"] = macro_context.get("events", [])
                result["macro"]["driver_context"] = macro_context
                if isinstance(macro_context, dict):
                    result["macro"]["macro_tier_detail"] = macro_context.get("macro_tier_detail", {})
                    result["macro"]["macro_data_quality"] = macro_context.get("macro_data_quality", 1.0)
                row = scanner_row_from_analysis(result, broker_symbol=broker_symbol)
                rows.append(self._apply_min_score_gate(row, request.min_scores.get(symbol, 0)))
            except Exception as exc:
                rows.append(blocked_scanner_row(symbol, f"Không quét được dữ liệu: {exc}", broker_symbol=broker_symbol))

        progress(74, "Đang xếp hạng setup theo rule engine...")
        rows = sort_scanner_rows(rows)

        active_ai = settings.ai.active_provider()
        ai_called = 0
        targets = ai_targets(rows, request.max_ai_details)
        if active_ai and active_ai.api_key and targets:
            for index, row in enumerate(targets, start=1):
                progress(78 + int(index / len(targets) * 12), f"Đang gọi AI cho {row['symbol']} ({index}/{len(targets)})...")
                summary = self._write_scanner_ai_summary(row, active_ai)
                if summary:
                    row["short_reason"] = summary
                    row["ai_summary_available"] = True
                    ai_called += 1

        progress(94, "Đang dựng bảng kết quả quét...")
        output = build_scanner_output(rows, request, ai_called)
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

    def _apply_min_score_gate(self, row: dict[str, Any], min_score: int) -> dict[str, Any]:
        try:
            threshold = int(min_score)
        except (TypeError, ValueError):
            threshold = 0
        threshold = max(0, min(100, threshold))
        row["min_score"] = threshold
        if threshold <= 0:
            return row
        try:
            score = int(row.get("final_score", row.get("best_score", 0)))
        except (TypeError, ValueError):
            score = 0
        if score >= threshold:
            return row
        row["scanner_action"] = "skip"
        row["trade_permission"] = "blocked"
        row["scanner_group"] = "blocked"
        row["scanner_decision"] = "TRADE_BLOCKED"
        reason = f"Final score {score} thấp hơn Min Score {threshold}."
        row["permission_reason"] = reason
        row["short_reason"] = reason
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
                if self.mt5_service.has_open_position_or_order(broker_symbol):
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
                order = self.mt5_service.place_market_order(
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
        effective_min_score = cfg_min_score if cfg_min_score > 0 else 50
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

    def _write_scanner_ai_summary(self, row: dict[str, Any], active_ai) -> str:
        prompt = (
            "Viết nhận định scanner rất ngắn bằng tiếng Việt, tối đa 2 câu. "
            "Chỉ diễn giải dữ liệu đã cung cấp, không tự tạo entry/SL/TP/giá mới.\n"
            f"Mã: {row.get('symbol')}\n"
            f"Regime: {row.get('market_regime')}\n"
            f"Bias: {row.get('direction_bias')}\n"
            f"Permission: {row.get('trade_permission')}\n"
            f"Buy score: {row.get('buy_score')}\n"
            f"Sell score: {row.get('sell_score')}\n"
            f"Best score: {row.get('best_score')}\n"
            f"Action: {row.get('scanner_action')}\n"
            f"R:R: {row.get('risk_reward') or '-'}\n"
            f"Lý do rule engine: {row.get('short_reason')}"
        )
        try:
            return AIService(AIProviderConfig(active_ai.provider, active_ai.model, active_ai.api_key)).analyze(prompt)
        except Exception:
            return ""

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


def _parse_yf_candles(data) -> list | None:
    """Parse yfinance DataFrame thành list Candle objects."""
    from core.market_models import Candle
    if data is None or data.empty:
        return None
    candles = []
    for idx, row in data.iterrows():
        close_val = row["Close"]
        if hasattr(close_val, "iloc"):
            close_val = close_val.iloc[0]
        open_val = row["Open"]
        if hasattr(open_val, "iloc"):
            open_val = open_val.iloc[0]
        high_val = row["High"]
        if hasattr(high_val, "iloc"):
            high_val = high_val.iloc[0]
        low_val = row["Low"]
        if hasattr(low_val, "iloc"):
            low_val = low_val.iloc[0]
        candles.append(Candle(
            time=idx.to_pydatetime(),
            open=float(open_val),
            high=float(high_val),
            low=float(low_val),
            close=float(close_val),
        ))
    return candles
