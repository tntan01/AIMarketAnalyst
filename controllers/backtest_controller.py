from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread

from config.paths import app_data_dir
from core.system_backtest_engine import BacktestRequest, run_system_backtest, summarize_backtest_trades
from services.market_data_service import fetch_macro_correlation_context
from services.mt5_service import MT5Service
from services.settings_service import SettingsService
from services.storage_service import JsonStorage
from workers.backtest_worker import BacktestWorker


class BacktestController:
    def __init__(
        self,
        settings_service: SettingsService | None = None,
        mt5_service: MT5Service | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.mt5_service = mt5_service or MT5Service()

    def create_backtest_worker(self, request: BacktestRequest | list[BacktestRequest]) -> tuple[QThread, BacktestWorker]:
        thread = QThread()
        if isinstance(request, list):
            worker = BacktestWorker(self.run_backtest_batch, {"requests": request})
        else:
            worker = BacktestWorker(self.run_backtest, {"request": request})
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        return thread, worker

    def build_requests(
        self,
        *,
        symbols: list[str],
        start,
        end,
        initial_balance: float,
        risk_percent: float,
        mode: str = "strict",
        spread_price: float = 0.0,
        slippage_price: float = 0.0,
        max_holding_bars: int = 96,
        timezone_name: str | None = None,
        account_guard_enabled: bool = False,
        max_daily_loss_pct: float = 999.0,
        max_weekly_loss_pct: float = 999.0,
        max_consecutive_losses: int = 999,
        max_open_risk_pct: float = 999.0,
        min_final_score: int = 0,
        allow_macro: bool = False,
    ) -> list[BacktestRequest]:
        unique_symbols = list(dict.fromkeys(symbols))
        if not unique_symbols:
            raise ValueError("Cần chọn ít nhất một mã để backtest.")
        return [
            self.build_request(
                symbol=symbol,
                start=start,
                end=end,
                initial_balance=initial_balance,
                risk_percent=risk_percent,
                mode=mode,
                spread_price=spread_price,
                slippage_price=slippage_price,
                max_holding_bars=max_holding_bars,
                timezone_name=timezone_name,
                account_guard_enabled=account_guard_enabled,
                max_daily_loss_pct=max_daily_loss_pct,
                max_weekly_loss_pct=max_weekly_loss_pct,
                max_consecutive_losses=max_consecutive_losses,
                max_open_risk_pct=max_open_risk_pct,
                min_final_score=min_final_score,
                allow_macro=allow_macro,
            )
            for symbol in unique_symbols
        ]

    def build_request(
        self,
        *,
        symbol: str,
        start,
        end,
        initial_balance: float,
        risk_percent: float,
        mode: str = "strict",
        spread_price: float = 0.0,
        slippage_price: float = 0.0,
        max_holding_bars: int = 96,
        timezone_name: str | None = None,
        account_guard_enabled: bool = False,
        max_daily_loss_pct: float = 999.0,
        max_weekly_loss_pct: float = 999.0,
        max_consecutive_losses: int = 999,
        max_open_risk_pct: float = 999.0,
        min_final_score: int = 0,
        allow_macro: bool = False,
    ) -> BacktestRequest:
        settings = self.settings_service.load()
        available = self.mt5_service.available_symbols(market_watch_only=True)
        broker_symbol = self.mt5_service.resolve_symbol(symbol, available) or symbol.replace("/", "")
        data_quality = self.mt5_service.symbol_data_quality(symbol, broker_symbol)
        from core.risk_engine import contract_size_override_for_symbol

        contract_override = contract_size_override_for_symbol(
            symbol,
            data_quality,
            settings.trading.contract_size_override,
        )
        return BacktestRequest(
            symbol=symbol,
            broker_symbol=broker_symbol,
            start=start,
            end=end,
            initial_balance=float(initial_balance),
            risk_percent=float(risk_percent),
            account_currency=settings.trading.account_currency,
            lot_step=settings.trading.lot_step,
            minimum_lot=settings.trading.minimum_lot,
            contract_size_override=float(contract_override) if contract_override else None,
            timezone_name=timezone_name or settings.display.timezone or "Asia/Ho_Chi_Minh",
            spread_price=float(spread_price),
            slippage_price=float(slippage_price),
            max_holding_bars=int(max_holding_bars),
            mode=mode,
            account_guard_enabled=bool(account_guard_enabled),
            max_daily_loss_pct=float(max_daily_loss_pct),
            max_weekly_loss_pct=float(max_weekly_loss_pct),
            max_consecutive_losses=int(max_consecutive_losses),
            max_open_risk_pct=float(max_open_risk_pct),
            min_final_score=int(min_final_score),
            allow_macro=bool(allow_macro),
        )

    def run_backtest(
        self,
        *,
        request: BacktestRequest,
        _progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        progress = _progress_callback or (lambda _percent, _message: None)
        progress(8, "Đang kiểm tra kết nối MT5...")
        status = self.mt5_service.connection_status()
        if not status.terminal_connected or not status.logged_in:
            raise RuntimeError("MT5 chưa kết nối đầy đủ hoặc broker chưa đăng nhập.")

        progress(15, "Đang tải dữ liệu lịch sử từ MT5...")
        candles = self._load_history(request)
        if request.allow_macro:
            progress(25, "Đang tải dữ liệu macro/correlation...")
            self._inject_macro_context(request)
        progress(35, "Đang replay hệ thống phân tích...")
        result = run_system_backtest(request, candles, progress_callback=progress)
        payload = result.to_dict()
        payload["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
        payload["snapshot_path"] = str(self.save_snapshot(payload))
        return payload

    def run_backtest_batch(
        self,
        *,
        requests: list[BacktestRequest],
        _progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        if not requests:
            raise ValueError("Cần chọn ít nhất một mã để backtest.")
        if len(requests) == 1:
            return self.run_backtest(request=requests[0], _progress_callback=_progress_callback)

        progress = _progress_callback or (lambda _percent, _message: None)
        progress(5, "Đang kiểm tra kết nối MT5...")
        status = self.mt5_service.connection_status()
        if not status.terminal_connected or not status.logged_in:
            raise RuntimeError("MT5 chưa kết nối đầy đủ hoặc broker chưa đăng nhập.")

        runs: list[dict[str, Any]] = []
        total = len(requests)

        # Pre-fetch macro context once for all requests
        any_macro = any(r.allow_macro for r in requests)
        if any_macro:
            progress(8, "Đang tải dữ liệu macro/correlation...")
            corr, macro_align = self._fetch_macro_data()
            for r in requests:
                if r.allow_macro:
                    object.__setattr__(r, "correlation_context", corr)
                    object.__setattr__(r, "macro_alignment_override", macro_align)

        for index, request in enumerate(requests, start=1):
            symbol_label = f"{request.symbol} ({index}/{total})"
            base = 8 + int((index - 1) / total * 86)
            span = max(1, int(86 / total))

            def child_progress(percent: int, message: str, *, _base: int = base, _span: int = span) -> None:
                scaled = _base + int(max(0, min(100, percent)) / 100 * _span)
                progress(min(96, scaled), f"{symbol_label}: {message}")

            child_progress(10, "Đang tải dữ liệu lịch sử từ MT5...")
            candles = self._load_history(request)
            child_progress(35, "Đang replay hệ thống phân tích...")
            result = run_system_backtest(request, candles, progress_callback=child_progress)
            payload = result.to_dict()
            payload["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
            runs.append(payload)

        progress(97, "Đang tổng hợp kết quả nhiều mã...")
        batch = self._build_batch_payload(requests, runs)
        batch["snapshot_path"] = str(self.save_snapshot(batch))
        return batch

    def _build_batch_payload(self, requests: list[BacktestRequest], runs: list[dict[str, Any]]) -> dict[str, Any]:
        trades = [
            trade
            for run in runs
            for trade in (run.get("trades", []) if isinstance(run.get("trades"), list) else [])
            if isinstance(trade, dict)
        ]
        trades = sorted(trades, key=lambda item: str(item.get("entry_time") or ""))
        summary = _summarize_trade_dicts(trades)
        by_symbol = {
            str(run.get("request", {}).get("symbol", "unknown")): run.get("summary", {})
            for run in runs
            if isinstance(run.get("request"), dict)
        }
        request0 = requests[0]
        timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        return {
            "mode": "system_backtest_batch",
            "timestamp": timestamp,
            "request": {
                "symbols": [request.symbol for request in requests],
                "start": request0.start.isoformat(),
                "end": request0.end.isoformat(),
                "initial_balance": request0.initial_balance,
                "risk_percent": request0.risk_percent,
                "account_currency": request0.account_currency,
                "timezone_name": request0.timezone_name,
                "spread_price": request0.spread_price,
                "slippage_price": request0.slippage_price,
                "max_holding_bars": request0.max_holding_bars,
                "setup_expiry_bars": request0.setup_expiry_bars,
                "step_timeframe": request0.step_timeframe,
                "mode": request0.mode,
                "min_final_score": request0.min_final_score,
                "allow_macro": request0.allow_macro,
                "account_guard_enabled": request0.account_guard_enabled,
            },
            "summary": summary,
            "trades": trades,
            "equity_curve": [],
            "breakdowns": {"by_symbol": by_symbol},
            "runs": runs,
            "diagnostics": {
                "symbols_tested": len(requests),
                "runs_completed": len(runs),
                "total_snapshots_evaluated": sum(int((run.get("diagnostics", {}) or {}).get("snapshots_evaluated", 0)) for run in runs),
                "total_setups_detected": sum(int((run.get("diagnostics", {}) or {}).get("setups_detected", 0)) for run in runs),
                "total_trades_skipped": sum(int((run.get("diagnostics", {}) or {}).get("trades_skipped", 0)) for run in runs),
            },
        }

    def _fetch_macro_data(self) -> tuple[dict, dict | None]:
        """Fetch current correlation data (DXY/VIX/US10Y) and macro alignment.
        Returns (correlation_context, macro_alignment_override).
        """
        return fetch_macro_correlation_context(), None

    def _inject_macro_context(self, request: BacktestRequest) -> None:
        corr, macro_align = self._fetch_macro_data()
        object.__setattr__(request, "correlation_context", corr)
        object.__setattr__(request, "macro_alignment_override", macro_align)

    def _load_history(self, request: BacktestRequest) -> dict[str, list]:
        warmup_start = request.start - timedelta(days=520)
        ranges = {
            "D1": (warmup_start, request.end),
            "H4": (warmup_start, request.end),
            "H1": (warmup_start, request.end),
            "M15": (request.start - timedelta(days=90), request.end),
        }
        result: dict[str, list] = {}
        for timeframe, (start, end) in ranges.items():
            if timeframe == "M15":
                result[timeframe] = self._load_m15_chunked(
                    request.broker_symbol, start, end,
                )
            else:
                result[timeframe] = self.mt5_service.load_ohlcv_range(
                    request.broker_symbol, timeframe, start, end,
                )
        return result

    def _load_m15_chunked(
        self,
        broker_symbol: str,
        start: datetime,
        end: datetime,
        *,
        max_chunk_days: int = 180,
    ) -> list:
        """Load M15 in 180-day chunks to avoid MT5 per-call bar-count limit.

        A single ``copy_rates_range`` for M15 over 3+ years exceeds MT5's
        internal cap.  Splitting into semi-annual windows works around it.
        Deduplication by bar timestamp handles chunk-boundary overlap.
        """
        from core.market_models import Candle

        # Fast path: try the full range in one call first
        try:
            candles = self.mt5_service.load_ohlcv_range(
                broker_symbol, "M15", start, end,
            )
            if candles:
                return candles
        except RuntimeError:
            pass

        # Build chunk list
        chunk_starts: list[datetime] = []
        cs = start
        while cs < end:
            chunk_starts.append(cs)
            cs += timedelta(days=max_chunk_days)

        if not chunk_starts:
            return []

        seen: set[int] = set()
        all_candles: list[Candle] = []

        for i, cs in enumerate(chunk_starts):
            ce = min(cs + timedelta(days=max_chunk_days), end)
            try:
                chunk = self.mt5_service.load_ohlcv_range(
                    broker_symbol, "M15", cs, ce, skip_select=(i > 0),
                )
            except RuntimeError:
                continue
            for c in chunk:
                key = int(c.time.timestamp())
                if key not in seen:
                    seen.add(key)
                    all_candles.append(c)

        return all_candles

    def save_snapshot(self, payload: dict[str, Any]) -> Path:
        snapshot_dir = app_data_dir() / "backtests"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = str(payload.get("timestamp") or payload.get("request", {}).get("end") or "backtest")
        timestamp = timestamp.replace(":", "").replace("+", "_").replace("-", "")
        request = payload.get("request", {}) if isinstance(payload.get("request"), dict) else {}
        if isinstance(request.get("symbols"), list):
            symbol = "BATCH_" + str(len(request["symbols"])) + "_symbols"
        else:
            symbol = str(request.get("symbol", "symbol")).replace("/", "")
        path = snapshot_dir / f"backtest_{symbol}_{timestamp}.json"
        JsonStorage(path).save(payload)
        return path


def _summarize_trade_dicts(trades: list[dict[str, Any]]) -> dict[str, Any]:
    from core.system_backtest_engine import BacktestTrade

    rows = [
        BacktestTrade(
            symbol=str(item.get("symbol", "")),
            side=str(item.get("side", "")),
            decision=str(item.get("decision", "")),
            entry_time=str(item.get("entry_time", "")),
            exit_time=item.get("exit_time"),
            entry_price=float(item.get("entry_price", 0) or 0),
            stop_loss=float(item.get("stop_loss", 0) or 0),
            take_profit=float(item.get("take_profit", 0) or 0),
            exit_price=float(item["exit_price"]) if item.get("exit_price") is not None else None,
            result=str(item.get("result", "")),
            result_r=float(item.get("result_r", 0) or 0),
            holding_bars=int(item.get("holding_bars", 0) or 0),
            final_score=int(item.get("final_score", 0) or 0),
            signal_score=int(item.get("signal_score", 0) or 0),
            buy_score=int(item.get("buy_score", 0) or 0),
            sell_score=int(item.get("sell_score", 0) or 0),
            score_gap=float(item.get("score_gap", 0) or 0),
            market_regime=str(item.get("market_regime", "")),
            entry_status=str(item.get("entry_status", "")),
            m15_quality=item.get("m15_quality"),
            expected_effective_rr=float(item["expected_effective_rr"]) if item.get("expected_effective_rr") is not None else None,
            selected_zone_score=int(item["selected_zone_score"]) if item.get("selected_zone_score") is not None else None,
            selected_zone_type=item.get("selected_zone_type"),
            entry_zone_score=int(item["entry_zone_score"]) if item.get("entry_zone_score") is not None else None,
            entry_zone_source=item.get("entry_zone_source"),
            liquidity_sweep_aligned=bool(item.get("liquidity_sweep_aligned")),
            displacement_aligned=bool(item.get("displacement_aligned")),
            choch_against_direction=bool(item.get("choch_against_direction")),
        )
        for item in trades
    ]
    return summarize_backtest_trades(rows)
