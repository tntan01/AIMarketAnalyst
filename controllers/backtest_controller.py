from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timedelta
import os
from pathlib import Path
import subprocess
from typing import Any

from PyQt6.QtCore import QThread

from config.paths import app_data_dir
from core.backtest_advanced import (
    advanced_research_manifest,
    run_monte_carlo_if_eligible,
)
from core.backtest_contract import (
    BACKTEST_PURPOSE_RESEARCH,
    BacktestRunPolicy,
    resolve_backtest_run_policy,
)
from core.backtest_execution_parity import EXECUTION_MODE_PARITY
from core.backtest_history import load_backtest_history, load_m15_history
from core.backtest_portfolio_engine import PortfolioReplayLimits, replay_portfolio
from core.system_backtest_engine import BacktestRequest, run_system_backtest
from services.mt5_service import MT5Service
from services.settings_service import SettingsService
from services.storage_service import JsonStorage
from workers.backtest_worker import BacktestWorker


class BacktestController:
    def __init__(
        self,
        settings_service: SettingsService | None = None,
        mt5: MT5Service | None = None,
    ) -> None:
        self.settings_service = settings_service or SettingsService()
        self.mt5: MT5Service = mt5 or MT5Service()
        self._history_cache: dict[
            tuple[str, str, str], dict[str, tuple[Any, ...]]
        ] = {}

    def create_backtest_worker(
        self,
        request: BacktestRequest | list[BacktestRequest],
        research_validation_enabled: bool = False,
        monte_carlo_requested: bool = False,
    ) -> tuple[QThread, BacktestWorker]:
        thread = QThread()
        if isinstance(request, list):
            req = request[0] if len(request) == 1 else request
        else:
            req = request
        worker = BacktestWorker(
            self.run_backtest,
            {
                "request": req,
                "research_validation_enabled": research_validation_enabled,
                "monte_carlo_requested": monte_carlo_requested,
            },
        )
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
        purpose: str = BACKTEST_PURPOSE_RESEARCH,
        execution_mode: str = EXECUTION_MODE_PARITY,
    ) -> list[BacktestRequest]:
        selected = list(dict.fromkeys(symbols or ["EUR/USD"]))
        return [
            self.build_request(
                symbol=symbol,
                start=start,
                end=end,
                initial_balance=initial_balance,
                risk_percent=risk_percent,
                purpose=purpose,
                execution_mode=execution_mode,
            )
            for symbol in selected
        ]

    def build_request(
        self,
        *,
        symbol: str,
        start,
        end,
        initial_balance: float,
        risk_percent: float,
        purpose: str = BACKTEST_PURPOSE_RESEARCH,
        execution_mode: str = EXECUTION_MODE_PARITY,
    ) -> BacktestRequest:
        run_policy = resolve_backtest_run_policy(purpose, execution_mode)
        settings = self.settings_service.load()
        available = self.mt5.available_symbols(market_watch_only=True)
        broker_symbol = self.mt5.resolve_symbol(symbol, available) or symbol.replace("/", "")
        data_quality = self.mt5.symbol_data_quality(symbol, broker_symbol)
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
            lot_step=float(
                data_quality.get("volume_step")
                or settings.trading.lot_step
            ),
            minimum_lot=float(
                data_quality.get("volume_min")
                or settings.trading.minimum_lot
            ),
            maximum_lot=float(
                data_quality.get("volume_max")
                or getattr(settings.trading, "maximum_lot", 100.0)
            ),
            contract_size_override=float(contract_override) if contract_override else None,
            timezone_name=settings.display.timezone or "Asia/Ho_Chi_Minh",
            spread_price=max(
                0.0, float(data_quality.get("spread_price") or 0.0)
            ),
            entry_slippage_price=float(
                getattr(settings.trading, "backtest_slippage_price", 0.0)
            ),
            exit_slippage_price=float(
                getattr(settings.trading, "backtest_slippage_price", 0.0)
            ),
            commission_per_lot_round_turn=(
                getattr(
                    settings.trading,
                    "backtest_commission_per_lot_round_turn",
                    0.0,
                )
            ),
            swap_long_per_lot_day=(
                getattr(
                    settings.trading,
                    "backtest_swap_long_per_lot_day",
                    0.0,
                )
            ),
            swap_short_per_lot_day=(
                getattr(
                    settings.trading,
                    "backtest_swap_short_per_lot_day",
                    0.0,
                )
            ),
            cost_model_configured=(
                data_quality.get("spread_price") is not None
            ),
            account_guard_enabled=True,
            max_daily_loss_pct=settings.trading.max_daily_loss_pct,
            max_weekly_loss_pct=settings.trading.max_weekly_loss_pct,
            max_consecutive_losses=settings.trading.max_consecutive_losses,
            max_open_risk_pct=settings.trading.max_open_risk_pct,
            max_symbol_risk_pct=settings.trading.max_symbol_risk_pct,
            max_currency_exposure_pct=settings.trading.max_currency_exposure_pct,
            max_correlated_risk_pct=settings.trading.max_correlated_risk_pct,
            max_concurrent_positions=settings.trading.max_concurrent_orders,
            purpose=run_policy.purpose,
            execution_mode=run_policy.execution_mode,
            code_revision=_runtime_code_revision(),
        )

    def run_backtest(
        self,
        *,
        request: BacktestRequest | list[BacktestRequest],
        research_validation_enabled: bool = False,
        monte_carlo_requested: bool = False,
        _progress_callback: Callable[[int, str], None] | None = None,
    ) -> dict[str, Any]:
        progress = _progress_callback or (lambda _percent, _message: None)
        if isinstance(request, list):
            return self._run_batch_backtest(
                request,
                research_validation_enabled=research_validation_enabled,
                monte_carlo_requested=monte_carlo_requested,
                progress=progress,
            )
        return self._run_single_backtest(
            request,
            research_validation_enabled=research_validation_enabled,
            monte_carlo_requested=monte_carlo_requested,
            progress=progress,
            save_snapshot=True,
        )

    def _run_single_backtest(
        self,
        request: BacktestRequest,
        *,
        research_validation_enabled: bool,
        monte_carlo_requested: bool = False,
        progress: Callable[[int, str], None],
        save_snapshot: bool,
    ) -> dict[str, Any]:
        run_policy = resolve_backtest_run_policy(
            request.purpose,
            request.execution_mode,
            research_validation_enabled=research_validation_enabled,
        )
        request = replace(
            request,
            purpose=run_policy.purpose,
            execution_mode=run_policy.execution_mode,
        )
        progress(8, "Đang kiểm tra kết nối dữ liệu...")
        status = self.mt5.connection_status()
        if not status.connected or not status.logged_in:
            raise RuntimeError(f"{status.provider_name} chưa kết nối đầy đủ hoặc chưa đăng nhập.")

        progress(15, "Đang tải dữ liệu lịch sử...")
        candles = self._load_history(request)
        request = self._attach_quote_conversion_history(request)
        primary_request = self._primary_replay_request(request, run_policy)
        progress(35, "Đang replay hệ thống phân tích...")
        result = run_system_backtest(
            primary_request,
            candles,
            progress_callback=progress,
        )
        payload = result.to_dict()
        payload["monte_carlo"] = run_monte_carlo_if_eligible(
            result.trades,
            requested=monte_carlo_requested,
        )
        if run_policy.run_validation_replay:
            self._attach_validation_evidence(
                payload,
                request,
                candles,
                progress=progress,
            )
        payload["run_policy"] = run_policy.to_dict()
        contract = payload.get("backtest_contract", {})
        validation = payload.get("validation_replay", {})
        walk_forward = payload.get("walk_forward", {})
        if (
            run_policy.release_candidate
            and isinstance(contract, dict)
            and isinstance(validation, dict)
            and validation.get("status") == "COMPLETE"
            and isinstance(walk_forward, dict)
            and walk_forward.get("status") != "ERROR"
        ):
            payload["lifecycle"] = {
                "status": "DRAFT",
                "reasons": [
                    "VALIDATION_REPLAY_COMPLETE",
                    "CONFIG_NOT_REVIEWED_OR_PUBLISHED",
                ],
            }
        else:
            payload["lifecycle"] = {
                "status": "RESEARCH_ONLY",
                "reasons": [
                    "PURPOSE_OR_EVIDENCE_NOT_RELEASE_ELIGIBLE"
                ],
            }
        payload["timestamp"] = datetime.now().astimezone().isoformat(timespec="seconds")
        if save_snapshot:
            payload["snapshot_path"] = str(self.save_snapshot(payload))
        return payload

    def _run_batch_backtest(
        self,
        requests: list[BacktestRequest],
        *,
        research_validation_enabled: bool,
        monte_carlo_requested: bool = False,
        progress: Callable[[int, str], None],
    ) -> dict[str, Any]:
        if not requests:
            raise ValueError("Batch backtest cần ít nhất một mã.")
        status = self.mt5.connection_status()
        if not status.connected or not status.logged_in:
            raise RuntimeError(
                f"{status.provider_name} chưa kết nối đầy đủ hoặc chưa đăng nhập."
            )
        payloads: list[dict[str, Any]] = []
        engine_results = []
        total = len(requests)
        for index, item in enumerate(requests):
            base = int(index / total * 90)

            def scaled(percent: int, message: str, *, _base: int = base) -> None:
                progress(
                    min(90, _base + int(percent / total)),
                    f"[{index + 1}/{total}] {message}",
                )

            run_policy = resolve_backtest_run_policy(
                item.purpose,
                item.execution_mode,
                research_validation_enabled=research_validation_enabled,
            )
            item = replace(
                item,
                purpose=run_policy.purpose,
                execution_mode=run_policy.execution_mode,
            )
            candles = self._load_history(item)
            attached = self._attach_quote_conversion_history(item)
            primary_request = self._primary_replay_request(
                attached,
                run_policy,
            )
            result = run_system_backtest(
                primary_request,
                candles,
                progress_callback=scaled,
            )
            engine_results.append(result)
            symbol_payload = result.to_dict()
            symbol_payload["monte_carlo"] = run_monte_carlo_if_eligible(
                result.trades,
                requested=monte_carlo_requested,
            )
            if run_policy.run_validation_replay:
                self._attach_validation_evidence(
                    symbol_payload,
                    attached,
                    candles,
                    progress=scaled,
                )
            symbol_payload["run_policy"] = run_policy.to_dict()
            symbol_payload["advanced_research"] = advanced_research_manifest(
                "PORTFOLIO_SYMBOL",
                details={"symbol": item.symbol},
            )
            symbol_payload["lifecycle"] = {
                "status": "RESEARCH_ONLY",
                "reasons": [
                    "PORTFOLIO_CHILD_NOT_PUBLISHABLE_AS_SYMBOL_CONFIG"
                ],
            }
            payloads.append(symbol_payload)

        first_policy = resolve_backtest_run_policy(
            requests[0].purpose,
            requests[0].execution_mode,
            research_validation_enabled=research_validation_enabled,
        )
        first = replace(
            requests[0],
            purpose=first_policy.purpose,
            execution_mode=first_policy.execution_mode,
        )
        portfolio = replay_portfolio(
            engine_results,
            initial_balance=first.initial_balance,
            limits=PortfolioReplayLimits(
                max_open_risk_pct=first.max_open_risk_pct,
                max_symbol_risk_pct=first.max_symbol_risk_pct,
                max_currency_exposure_pct=first.max_currency_exposure_pct,
                max_correlated_risk_pct=first.max_correlated_risk_pct,
                max_concurrent_positions=first.max_concurrent_positions,
            ),
        )
        payload: dict[str, Any] = {
            "mode": "portfolio_backtest",
            "request": {
                "symbols": [item.symbol for item in requests],
                "start": first.start.isoformat(),
                "end": first.end.isoformat(),
                "initial_balance": first.initial_balance,
                "risk_percent": first.risk_percent,
                "purpose": first.purpose,
                "execution_mode": first.execution_mode,
            },
            "summary": portfolio["summary"],
            "trades": portfolio["trades"],
            "equity_curve": portfolio["equity_curve"],
            "portfolio": portfolio,
            "symbols": payloads,
            "lifecycle": {
                "status": "RESEARCH_ONLY",
                "reasons": ["BATCH_PORTFOLIO_NOT_PUBLISHABLE_AS_SYMBOL_CONFIG"],
            },
            "advanced_research": advanced_research_manifest(
                "PORTFOLIO",
                details={
                    "symbols": [item.symbol for item in requests],
                    "monte_carlo_requested": bool(monte_carlo_requested),
                },
            ),
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        progress(95, "Đang lưu snapshot portfolio...")
        payload["snapshot_path"] = str(self.save_snapshot(payload))
        return payload

    @staticmethod
    def _primary_replay_request(
        request: BacktestRequest,
        run_policy: BacktestRunPolicy,
    ) -> BacktestRequest:
        """Build the descriptive replay without pretending it is frozen OOS.

        A user Validation request has no frozen strategy yet. Its first replay
        must therefore remain Research; only the subsequent validation replay
        is allowed to create a true VALIDATION contract.
        """

        if not run_policy.release_candidate:
            return request
        return replace(
            request,
            purpose=BACKTEST_PURPOSE_RESEARCH,
            frozen_strategy_config=None,
        )

    @staticmethod
    def _attach_validation_evidence(
        payload: dict[str, Any],
        request: BacktestRequest,
        candles: dict[str, list],
        *,
        progress: Callable[[int, str], None],
    ) -> None:
        from core.backtest_validation_replay import run_frozen_validation_replay
        from core.walk_forward_engine import run_walk_forward

        try:
            payload["validation_replay"] = run_frozen_validation_replay(
                request,
                candles,
                progress_callback=progress,
            )
        except (RuntimeError, ValueError) as exc:
            payload["validation_replay"] = {
                "status": "ERROR",
                "reason": str(exc),
            }
        try:
            payload["walk_forward"] = run_walk_forward(
                request,
                candles,
                progress_callback=progress,
            )
        except (RuntimeError, ValueError) as exc:
            payload["walk_forward"] = {
                "status": "ERROR",
                "reason": str(exc),
            }

    def _attach_quote_conversion_history(
        self,
        request: BacktestRequest,
    ) -> BacktestRequest:
        """Attach point-in-time quote/account conversion candles."""

        normalized = "".join(
            character for character in request.symbol.upper()
            if character.isalpha()
        )
        if len(normalized) < 6:
            return request
        quote = normalized[-3:]
        account = str(request.account_currency or "USD").upper()
        if quote == account:
            return replace(request, quote_to_account_rate=1.0)

        available = self.mt5.available_symbols(market_watch_only=False)
        display_symbol = f"{quote}/{account}"
        broker_symbol = self.mt5.resolve_symbol(display_symbol, available)
        inverted = False
        if broker_symbol is None:
            display_symbol = f"{account}/{quote}"
            broker_symbol = self.mt5.resolve_symbol(display_symbol, available)
            inverted = broker_symbol is not None
        if broker_symbol is None:
            fallback = (
                self.mt5.quote_to_usd_rate(quote)
                if account == "USD"
                else None
            )
            return replace(request, quote_to_account_rate=fallback)
        try:
            history = self.mt5.load_ohlcv_range(
                broker_symbol,
                "H1",
                request.start - timedelta(days=7),
                request.end,
            )
        except RuntimeError:
            history = []
        return replace(
            request,
            quote_conversion_symbol=display_symbol,
            quote_conversion_inverted=inverted,
            quote_conversion_candles=tuple(history),
        )
    def _load_history(self, request: BacktestRequest) -> dict[str, list]:
        return load_backtest_history(
            self.mt5,
            request,
            cache=self._history_cache,
        )

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
        return load_m15_history(
            self.mt5,
            broker_symbol,
            start,
            end,
            max_chunk_days=max_chunk_days,
        )

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


def _runtime_code_revision() -> str:
    configured = str(os.getenv("AIMARKETANALYST_CODE_REVISION", "") or "")
    if configured:
        return configured.strip().lower()
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
            check=False,
            timeout=2,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip().lower() if completed.returncode == 0 else ""
