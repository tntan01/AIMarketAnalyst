"""Param Sweep Worker — chạy sensitivity scan trên background thread."""

from __future__ import annotations

import re as _re_mod
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from core.param_sensitivity import ParamSweepConfig, MarketPeriod, sweep_params


class ParamSweepThread(QThread):
    """Thread chạy sweep tham số, không block UI.

    Tín hiệu:
        progress(int, str): phần trăm + mô tả trạng thái
        succeeded(list[SweepResult]): kết quả sweep
        failed(str): thông báo lỗi
    """

    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        configs: list[ParamSweepConfig],
        periods: list[MarketPeriod],
        symbols: list[str],
        settings: dict[str, Any] | None = None,
        parent: QThread | None = None,
    ) -> None:
        super().__init__(parent)
        self._configs = configs
        self._periods = periods
        self._symbols = symbols
        self._settings = settings or {}

    def run(self) -> None:
        mt5 = None
        initialized = False
        try:
            import MetaTrader5 as mt5

            initialized = mt5.initialize()
            if not initialized:
                self.failed.emit(
                    "Không khởi tạo được kết nối MT5. "
                    "Hãy mở MT5 terminal và đăng nhập trước khi chạy."
                )
                return

            from services.mt5_service import MT5Service

            data_provider = MT5Service()

            total_runs = len(self._configs) * len(self._periods) * len(self._symbols) * 5
            self.progress.emit(0, f"Bắt đầu quét ~{total_runs} tổ hợp...")

            last_pct = 0

            def _on_progress(msg: str) -> None:
                nonlocal last_pct
                match = _re_mod.search(r"\[(\d+)/(\d+)\]", msg)
                if match:
                    n, m = int(match.group(1)), int(match.group(2))
                    pct = int(n / m * 100) if m > 0 else last_pct
                    last_pct = pct
                else:
                    pct = last_pct
                self.progress.emit(pct, msg.strip())

            results = sweep_params(
                self._configs,
                self._periods,
                self._symbols,
                progress_callback=_on_progress,
                data_provider=data_provider,
                backtest_settings=self._settings,
            )

            self.progress.emit(100, "Hoàn tất quét tham số.")
            self.succeeded.emit(results)

        except Exception as exc:
            import traceback
            self.failed.emit(f"{exc}\n\n{traceback.format_exc()}")
        finally:
            if initialized and mt5 is not None:
                mt5.shutdown()
