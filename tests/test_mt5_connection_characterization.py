"""Characterization tests for the current MT5 readiness boundary.

These tests intentionally capture behavior before the connection-lifecycle
refactor.  They protect user-facing guards and Scanner observability while
the implementation is consolidated in later steps.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import controllers.scanner_controller as scanner_module
from controllers.backtest_controller import BacktestController
from controllers.scanner_controller import ScannerController
from core.backtest_contract import BACKTEST_PURPOSE_RESEARCH
from core.backtest_execution_parity import EXECUTION_MODE_PARITY
from core.scanner import ScannerRequest
from core.system_backtest_engine import BacktestRequest
from services.data_provider import ProviderNotReadyError
from services.mt5_service import MT5Service


class _FakeMT5Module:
    def __init__(
        self,
        *,
        terminal_connected: bool,
        login: int | None,
        trade_allowed: bool,
    ) -> None:
        self.initialized = False
        self.initialize_calls = 0
        self.terminal_connected = terminal_connected
        self.login = login
        self.trade_allowed = trade_allowed

    def initialize(self) -> bool:
        self.initialize_calls += 1
        self.initialized = True
        return True

    def last_error(self) -> tuple[int, str]:
        return 0, ""

    def terminal_info(self):
        if not self.initialized:
            return None
        return SimpleNamespace(
            connected=self.terminal_connected,
            trade_allowed=self.trade_allowed,
            name="Terminal",
            path="C:/MT5",
        )

    def account_info(self):
        if not self.initialized:
            return None
        return SimpleNamespace(
            login=self.login,
            trade_allowed=self.trade_allowed,
            company="Fixture Broker",
            server="Fixture-Demo",
            balance=1000.0,
            currency="USD",
        )


@pytest.mark.parametrize(
    ("terminal_connected", "login", "trade_allowed", "expected"),
    [
        (False, 123456, True, (False, True, True)),
        (True, None, True, (True, False, True)),
        (True, 123456, False, (True, True, False)),
    ],
)
def test_mt5_connection_status_reports_readiness_dimensions_after_connect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    terminal_connected: bool,
    login: int | None,
    trade_allowed: bool,
    expected: tuple[bool, bool, bool],
) -> None:
    mt5 = _FakeMT5Module(
        terminal_connected=terminal_connected,
        login=login,
        trade_allowed=trade_allowed,
    )
    monkeypatch.setitem(__import__("sys").modules, "MetaTrader5", mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    service = MT5Service(profile_path)
    assert service.connect() is True
    status = service.connection_status()

    assert mt5.initialize_calls == 1
    assert status.initialized is True
    assert (status.connected, status.logged_in, status.trade_allowed) == expected


def test_ensure_ready_exposes_structured_readiness_reasons(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    mt5 = _FakeMT5Module(
        terminal_connected=False,
        login=None,
        trade_allowed=False,
    )
    monkeypatch.setitem(__import__("sys").modules, "MetaTrader5", mt5)
    profile_path = tmp_path / "symbol_profiles.json"
    profile_path.write_text("{}", encoding="utf-8")

    with pytest.raises(ProviderNotReadyError) as exc_info:
        MT5Service(profile_path).ensure_ready(
            require_login=True,
            require_trade=True,
        )

    assert exc_info.value.reason_codes == (
        "PROVIDER_NOT_CONNECTED",
        "PROVIDER_NOT_LOGGED_IN",
        "TRADING_NOT_ALLOWED",
    )
    assert exc_info.value.status.provider_name == "MT5"


class _StatusProvider:
    def __init__(
        self,
        *,
        connected: bool,
        logged_in: bool,
        trade_allowed: bool = True,
    ) -> None:
        self.calls = 0
        self.status = SimpleNamespace(
            initialized=True,
            connected=connected,
            logged_in=logged_in,
            trade_allowed=trade_allowed,
            provider_name="MT5 fixture",
            server="Fixture-Demo",
        )

    def connection_status(self):
        self.calls += 1
        return self.status

    def ensure_ready(self, *, require_login: bool = True, require_trade: bool = False):
        status = self.connection_status()
        reason_codes: list[str] = []
        if not status.initialized:
            reason_codes.append("PROVIDER_NOT_INITIALIZED")
        if not status.connected:
            reason_codes.append("PROVIDER_NOT_CONNECTED")
        if require_login and not status.logged_in:
            reason_codes.append("PROVIDER_NOT_LOGGED_IN")
        if require_trade and not status.trade_allowed:
            reason_codes.append("TRADING_NOT_ALLOWED")
        if reason_codes:
            raise ProviderNotReadyError(status, tuple(reason_codes))
        return status


def _backtest_request() -> BacktestRequest:
    return BacktestRequest(
        symbol="EUR/USD",
        broker_symbol="EURUSD",
        start=datetime(2025, 1, 1, tzinfo=timezone.utc),
        end=datetime(2025, 2, 1, tzinfo=timezone.utc),
        initial_balance=10_000.0,
        risk_percent=1.0,
        purpose=BACKTEST_PURPOSE_RESEARCH,
        execution_mode=EXECUTION_MODE_PARITY,
    )


@pytest.mark.parametrize("connected, logged_in", [(False, True), (True, False)])
def test_single_backtest_rejects_unready_mt5_before_history_load(
    connected: bool,
    logged_in: bool,
) -> None:
    controller = object.__new__(BacktestController)
    provider = _StatusProvider(connected=connected, logged_in=logged_in)
    controller.mt5 = provider
    controller._history_cache = {}
    controller._load_history = MagicMock()

    with pytest.raises(ProviderNotReadyError, match="MT5 fixture"):
        controller.run_backtest(
            request=_backtest_request(),
            research_validation_enabled=False,
            _progress_callback=lambda _percent, _message: None,
        )

    assert provider.calls == 1
    controller._load_history.assert_not_called()


def test_batch_backtest_rejects_unready_mt5_once_before_history_load() -> None:
    controller = object.__new__(BacktestController)
    provider = _StatusProvider(connected=False, logged_in=False)
    controller.mt5 = provider
    controller._history_cache = {}
    controller._load_history = MagicMock()

    with pytest.raises(ProviderNotReadyError, match="MT5 fixture"):
        controller.run_backtest(
            request=[_backtest_request()],
            research_validation_enabled=False,
            _progress_callback=lambda _percent, _message: None,
        )

    assert provider.calls == 1
    controller._load_history.assert_not_called()


def test_backtest_does_not_require_trade_permission_for_data_readiness() -> None:
    class HistoryReached(RuntimeError):
        pass

    controller = object.__new__(BacktestController)
    provider = _StatusProvider(
        connected=True,
        logged_in=True,
        trade_allowed=False,
    )
    controller.mt5 = provider
    controller._history_cache = {}
    controller._load_history = MagicMock(side_effect=HistoryReached("history reached"))

    with pytest.raises(HistoryReached, match="history reached"):
        controller.run_backtest(
            request=_backtest_request(),
            research_validation_enabled=False,
            _progress_callback=lambda _percent, _message: None,
        )

    assert provider.calls == 1
    controller._load_history.assert_called_once()


@pytest.mark.parametrize("connected, logged_in", [(False, True), (True, False)])
def test_scanner_emits_connection_failure_with_status_fields(
    connected: bool,
    logged_in: bool,
) -> None:
    controller = object.__new__(ScannerController)
    controller.settings_service = SimpleNamespace(
        load=lambda: SimpleNamespace(
            trading=SimpleNamespace(max_risk_percent=2.0),
        )
    )
    controller.mt5 = _StatusProvider(connected=connected, logged_in=logged_in)
    controller.observability = MagicMock()
    request = ScannerRequest(
        symbols=[],
        account_balance=10_000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    context = SimpleNamespace(
        scan_id="scan-characterization",
        request_hash="request-hash",
        settings_hash="settings-hash",
        smc_scoring_mode="v2",
        smc_scorer_version="smc-v2",
        smc_domain_version="smc-domain-v2",
    )

    with patch.object(scanner_module, "create_scan_context", return_value=context):
        with pytest.raises(ProviderNotReadyError, match="MT5 fixture"):
            controller.run_market_scan(request=request)

    failure_calls = [
        call
        for call in controller.observability.emit.call_args_list
        if call.args[0] == "DATA_FETCH_FAILURE"
    ]
    assert len(failure_calls) == 1
    failure = failure_calls[0]
    assert failure.kwargs["scan_id"] == "scan-characterization"
    assert failure.kwargs["severity"] == "ERROR"
    assert failure.kwargs["payload"] == {
        "stage": "connection",
        "provider": "MT5 fixture",
        "connected": connected,
        "logged_in": logged_in,
    }


def test_scanner_ready_mt5_continues_scan_without_rollout_policy() -> None:
    # The Phase-8 rollout stage ladder was removed (2026-08-15, fully live):
    # a ready MT5 connection goes straight from connection readiness to the
    # account/portfolio stage — no rollout policy is built, stored or emitted.
    class ScanContinued(RuntimeError):
        pass

    controller = object.__new__(ScannerController)
    controller.settings_service = SimpleNamespace(
        load=lambda: SimpleNamespace(
            trading=SimpleNamespace(max_risk_percent=2.0),
        )
    )
    provider = _StatusProvider(connected=True, logged_in=True)
    provider.account_balance = MagicMock(
        side_effect=ScanContinued(
            "scan continued after connection readiness"
        )
    )
    controller.mt5 = provider
    controller.observability = MagicMock()
    request = ScannerRequest(
        symbols=[],
        account_balance=10_000.0,
        risk_percent=1.0,
        timezone_name="Asia/Ho_Chi_Minh",
    )
    context = SimpleNamespace(
        scan_id="scan-ready",
        request_hash="request-hash",
        settings_hash="settings-hash",
        smc_scoring_mode="v2",
        smc_scorer_version="smc-v2",
        smc_domain_version="smc-domain-v2",
    )

    with patch.object(scanner_module, "create_scan_context", return_value=context):
        with pytest.raises(ScanContinued, match="scan continued"):
            controller.run_market_scan(request=request)

    assert provider.calls == 1
    assert not hasattr(controller, "_active_rollout_policy")
    provider.account_balance.assert_called_once_with()
    rollout_calls = [
        call
        for call in controller.observability.emit.call_args_list
        if "ROLLOUT" in str(call.args[0])
    ]
    assert rollout_calls == []
