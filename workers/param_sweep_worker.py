"""Cancelable parameter sweep hosted in a separate OS process."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import multiprocessing as mp
from pathlib import Path
import queue
import re
import time
from typing import Any

from PyQt6.QtCore import QThread, pyqtSignal

from config.paths import app_data_dir
from core.param_sensitivity import (
    MarketPeriod,
    ParamSweepConfig,
    SweepResult,
    SweepRunResult,
)


SWEEP_PROCESS_VERSION = "parameter-sweep-process-v2-shared-context"


class ParamSweepThread(QThread):
    """Monitor a spawned process; the UI thread never executes the sweep."""

    progress = pyqtSignal(int, str)
    succeeded = pyqtSignal(list)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal(str)

    def __init__(
        self,
        configs: list[ParamSweepConfig],
        periods: list[MarketPeriod],
        symbols: list[str],
        settings: dict[str, Any] | None = None,
        parent: QThread | None = None,
        *,
        timeout_seconds: int = 7200,
        resume: bool = True,
        request_templates: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(parent)
        self._configs = configs
        self._periods = periods
        self._symbols = symbols
        self._settings = settings or {}
        self._request_templates = request_templates or {}
        self._timeout_seconds = max(30, int(timeout_seconds))
        self._resume = bool(resume)
        self._cancel_requested = False
        self._process: mp.Process | None = None

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        ctx = mp.get_context("spawn")
        messages = ctx.Queue()
        cache_path = _cache_path(
            self._configs,
            self._periods,
            self._symbols,
            self._settings,
            self._request_templates,
        )
        process = ctx.Process(
            target=_sweep_process_main,
            args=(
                self._configs, self._periods, self._symbols, self._settings,
                self._request_templates, str(cache_path), self._resume, messages,
            ),
            daemon=True,
        )
        self._process = process
        process.start()
        started = time.monotonic()
        try:
            while True:
                if self._cancel_requested:
                    _stop_process(process)
                    self.cancelled.emit(
                        "Đã hủy sweep; checkpoint hoàn tất trước đó vẫn dùng để tiếp tục."
                    )
                    return
                if time.monotonic() - started > self._timeout_seconds:
                    _stop_process(process)
                    self.failed.emit(
                        f"Sweep vượt timeout {self._timeout_seconds} giây; có thể chạy tiếp từ checkpoint."
                    )
                    return
                try:
                    kind, payload = messages.get(timeout=0.2)
                except queue.Empty:
                    if not process.is_alive():
                        process.join(timeout=1)
                        if process.exitcode not in (0, None):
                            self.failed.emit(
                                f"Process sweep kết thúc bất thường (exit={process.exitcode})."
                            )
                        return
                    continue
                if kind == "progress":
                    self.progress.emit(int(payload[0]), str(payload[1]))
                elif kind == "success":
                    process.join(timeout=2)
                    self.succeeded.emit([_result_from_dict(row) for row in payload])
                    return
                elif kind == "error":
                    process.join(timeout=2)
                    self.failed.emit(str(payload))
                    return
        finally:
            if process.is_alive() and self._cancel_requested:
                _stop_process(process)
            self._process = None


def _sweep_process_main(
    configs: list[ParamSweepConfig],
    periods: list[MarketPeriod],
    symbols: list[str],
    settings: dict[str, Any],
    request_templates: dict[str, Any],
    cache_path: str,
    resume: bool,
    messages: Any,
) -> None:
    mt5_module = None
    initialized = False
    try:
        import MetaTrader5 as mt5_module
        initialized = bool(mt5_module.initialize())
        if not initialized:
            raise RuntimeError(
                "Không khởi tạo được MT5. Hãy mở terminal và đăng nhập trước khi chạy."
            )
        from core.param_sensitivity import sweep_single_param
        from services.mt5_service import MT5Service

        provider = MT5Service()
        completed = _load_checkpoint(Path(cache_path)) if resume else []
        by_key = {result.json_key: result for result in completed}
        total = max(1, len(configs))
        for index, config in enumerate(configs):
            if config.json_key in by_key:
                messages.put(("progress", (
                    int((index + 1) / total * 100),
                    f"Dùng checkpoint: {config.json_key}",
                )))
                continue
            last_pct = int(index / total * 100)

            def on_progress(message: str) -> None:
                nonlocal last_pct
                match = re.search(r"\[(\d+)/(\d+)\]", message)
                local = int(int(match.group(1)) / max(1, int(match.group(2))) * 100) if match else 0
                last_pct = int((index + local / 100) / total * 100)
                messages.put(("progress", (last_pct, message.strip())))

            result = sweep_single_param(
                config, periods, symbols,
                progress_callback=on_progress,
                data_provider=provider,
                backtest_settings=settings,
                request_templates=request_templates,
            )
            by_key[config.json_key] = result
            ordered = [by_key[item.json_key] for item in configs if item.json_key in by_key]
            _save_checkpoint(Path(cache_path), ordered)
        results = [by_key[item.json_key] for item in configs]
        messages.put(("success", [asdict(result) for result in results]))
    except Exception as exc:
        import traceback
        messages.put(("error", f"{exc}\n\n{traceback.format_exc()}"))
    finally:
        if initialized and mt5_module is not None:
            mt5_module.shutdown()


def _cache_path(
    configs: list[ParamSweepConfig],
    periods: list[MarketPeriod],
    symbols: list[str],
    settings: dict[str, Any],
    request_templates: dict[str, Any] | None = None,
) -> Path:
    payload = {
        "version": SWEEP_PROCESS_VERSION,
        "configs": [asdict(item) for item in configs],
        "periods": [asdict(item) for item in periods],
        "symbols": symbols,
        "settings": settings,
        "request_templates": {
            symbol: asdict(request) if hasattr(request, "__dataclass_fields__") else request
            for symbol, request in sorted((request_templates or {}).items())
        },
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()[:20]
    return app_data_dir() / "backtests" / "sweep_cache" / f"{digest}.json"


def _save_checkpoint(path: Path, results: list[SweepResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps([asdict(result) for result in results], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def _load_checkpoint(path: Path) -> list[SweepResult]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [_result_from_dict(row) for row in payload]
    except (OSError, ValueError, TypeError, KeyError):
        return []


def _result_from_dict(payload: dict[str, Any]) -> SweepResult:
    return SweepResult(
        json_key=str(payload["json_key"]),
        attr_name=str(payload["attr_name"]),
        runs=[SweepRunResult(**row) for row in payload.get("runs", [])],
        stability_score=payload.get("stability_score"),
        verdict=str(payload.get("verdict", "UNKNOWN")),
        recommendation=payload.get("recommendation"),
        version=str(payload.get("version", "parameter-sweep-v1")),
        lifecycle=str(payload.get("lifecycle", "RESEARCH_ONLY")),
        can_apply_config=bool(payload.get("can_apply_config", False)),
        request_context=dict(payload.get("request_context", {})),
    )


def _stop_process(process: mp.Process) -> None:
    if not process.is_alive():
        process.join(timeout=1)
        return
    process.terminate()
    process.join(timeout=3)
    if process.is_alive() and hasattr(process, "kill"):
        process.kill()
        process.join(timeout=2)
