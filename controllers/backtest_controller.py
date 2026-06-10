from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread

from config.paths import app_data_dir
from core.system_backtest_engine import BacktestRequest, run_system_backtest
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

    def create_backtest_worker(self, request: BacktestRequest) -> tuple[QThread, BacktestWorker]:
        thread = QThread()
        worker = BacktestWorker(self.run_backtest, {"request": request})
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        return thread, worker

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
        progress(35, "Đang replay hệ thống phân tích...")
        result = run_system_backtest(request, candles, progress_callback=progress)
        payload = result.to_dict()
        payload["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
        payload["snapshot_path"] = str(self.save_snapshot(payload))
        return payload

    def _load_history(self, request: BacktestRequest) -> dict[str, list]:
        warmup_start = request.start - timedelta(days=520)
        ranges = {
            "D1": (warmup_start, request.end),
            "H4": (warmup_start, request.end),
            "H1": (warmup_start, request.end),
            "M15": (request.start - timedelta(days=90), request.end),
        }
        return {
            timeframe: self.mt5_service.load_ohlcv_range(
                request.broker_symbol,
                timeframe,
                start,
                end,
            )
            for timeframe, (start, end) in ranges.items()
        }

    def save_snapshot(self, payload: dict[str, Any]) -> Path:
        snapshot_dir = app_data_dir() / "backtests"
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        timestamp = str(payload.get("timestamp") or payload.get("request", {}).get("end") or "backtest")
        timestamp = timestamp.replace(":", "").replace("+", "_").replace("-", "")
        symbol = str(payload.get("request", {}).get("symbol", "symbol")).replace("/", "")
        path = snapshot_dir / f"backtest_{symbol}_{timestamp}.json"
        JsonStorage(path).save(payload)
        return path
