from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QThread

from config.paths import app_data_dir
from core.system_backtest_engine import BacktestRequest, run_system_backtest
from services.data_provider import DataProvider
from services.mt5_service import MT5Service
from services.settings_service import SettingsService
from services.storage_service import JsonStorage
from workers.backtest_worker import BacktestWorker


class BacktestController:
    def __init__(
        self,
        settings_service: SettingsService | None = None,
        data_provider: DataProvider | None = None,
        # Backward compat
        mt5_service: MT5Service | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.data_provider: DataProvider = data_provider or mt5_service or MT5Service()

    def create_backtest_worker(self, request: BacktestRequest | list[BacktestRequest]) -> tuple[QThread, BacktestWorker]:
        thread = QThread()
        if isinstance(request, list):
            req = request[0] if len(request) == 1 else request
        else:
            req = request
        worker = BacktestWorker(self.run_backtest, {"request": req})
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
    ) -> list[BacktestRequest]:
        symbol = symbols[0] if symbols else "EUR/USD"
        return [
            self.build_request(
                symbol=symbol,
                start=start,
                end=end,
                initial_balance=initial_balance,
                risk_percent=risk_percent,
            )
        ]

    def build_request(
        self,
        *,
        symbol: str,
        start,
        end,
        initial_balance: float,
        risk_percent: float,
    ) -> BacktestRequest:
        settings = self.settings_service.load()
        available = self.data_provider.available_symbols(market_watch_only=True)
        broker_symbol = self.data_provider.resolve_symbol(symbol, available) or symbol.replace("/", "")
        data_quality = self.data_provider.symbol_data_quality(symbol, broker_symbol)
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
            timezone_name=settings.display.timezone or "Asia/Ho_Chi_Minh",
        )

    def run_backtest(
        self,
        *,
        request: BacktestRequest,
        _progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        progress = _progress_callback or (lambda _percent, _message: None)
        progress(8, "Đang kiểm tra kết nối dữ liệu...")
        status = self.data_provider.connection_status()
        if not status.connected or not status.logged_in:
            raise RuntimeError(f"{status.provider_name} chưa kết nối đầy đủ hoặc chưa đăng nhập.")

        progress(15, "Đang tải dữ liệu lịch sử...")
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
        result: dict[str, list] = {}
        for timeframe, (start, end) in ranges.items():
            if timeframe == "M15":
                result[timeframe] = self._load_m15_chunked(
                    request.broker_symbol, start, end,
                )
            else:
                result[timeframe] = self.data_provider.load_ohlcv_range(
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
            candles = self.data_provider.load_ohlcv_range(
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
                chunk = self.data_provider.load_ohlcv_range(
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
