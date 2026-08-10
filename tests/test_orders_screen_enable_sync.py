"""Tests for OrdersScreen enable/resume state sync with OrderManagementService.

Verifies that enabling management for a brand-new position starts at
WAITING_BE, and that re-enabling a paused position resumes the exact phase the
service holds (TRAIL_WIDE / TRAIL_TIGHT / WAITING_BE).  The UI never fabricates
its own runtime state (be_done=False, extreme_price=0.0) when the service
exists — it projects the service read model via ``_sync_managed_views()``.
"""

from __future__ import annotations

import sys
from concurrent.futures import Executor, Future
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt6.QtWidgets import QMessageBox

from config.settings import OrderManagementSettings
from core.order_management_state_machine import ManagementPhase
from services.order_management_models import (
    AccountIdentity,
    AccountTradeMode,
    BrokerPosition,
    BrokerSymbolMetadata,
    BrokerTick,
    OperationStatus,
    PendingOrdersSnapshot,
    PositionsSnapshot,
    SnapshotStatus,
    TickSnapshot,
)
from services.order_management_service import OrderManagementService
from services.order_management_state_store import OrderManagementStateStore


class _ImmediateExecutor(Executor):
    def submit(self, fn, /, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # pragma: no cover - Future contract
            future.set_exception(exc)
        return future


class _ObservabilityStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type, **kwargs):
        event = {"event_type": event_type, **kwargs}
        self.events.append(event)
        return event


def _account(login: int = 1001) -> AccountIdentity:
    return AccountIdentity(
        "Broker",
        "Broker-Demo",
        login,
        AccountTradeMode.DEMO,
        trade_allowed=True,
    )


def _position() -> BrokerPosition:
    return BrokerPosition(
        position_id=41,
        broker_symbol="EURUSDm",
        app_symbol="EUR/USD",
        side="buy",
        volume=0.1,
        open_price=1.1,
        current_price=1.102,
        sl=1.098,
        tp=1.106,
        profit=20.0,
        swap=0.0,
        commission=0.0,
        magic=260609,
        comment="AMA-FWD:abcdef123456",
        open_time=1_700_000_000,
        identifier=41,
        symbol_metadata=BrokerSymbolMetadata(
            digits=5,
            point=0.00001,
            trade_tick_size=0.00001,
            trade_stops_level=10,
            trade_freeze_level=0,
            volume_step=0.01,
        ),
    )


class _FakeMT5:
    positions_status = SnapshotStatus.AVAILABLE

    def __init__(self) -> None:
        self.account = _account()
        self.positions: tuple[BrokerPosition, ...] = (_position(),)
        self.modify_calls: list[dict] = []

    def positions_snapshot(self) -> PositionsSnapshot:
        return PositionsSnapshot(
            self.positions_status,
            self.account,
            self.positions if self.positions_status is SnapshotStatus.AVAILABLE else (),
            datetime.now(timezone.utc),
        )

    def pending_orders_snapshot(self) -> PendingOrdersSnapshot:
        return PendingOrdersSnapshot(
            SnapshotStatus.AVAILABLE,
            self.account,
            (),
            datetime.now(timezone.utc),
        )

    def symbol_tick(self, symbol: str) -> TickSnapshot:
        return TickSnapshot(
            SnapshotStatus.AVAILABLE,
            self.account,
            BrokerTick(symbol, bid=1.1022, ask=1.1024, time=1, time_msc=1000),
            datetime.now(timezone.utc),
        )

    def modify_position_sltp(self, position_id: int, **kwargs):
        self.modify_calls.append({"position_id": position_id, **kwargs})
        return {
            "success": True,
            "status": OperationStatus.CONFIRMED.value,
            "position_id": position_id,
            "effective_sl": kwargs.get("sl"),
            "effective_tp": kwargs.get("tp"),
            "retcode": 10009,
            "message": "ok",
        }


def _make_service(tmp_path) -> OrderManagementService:
    return OrderManagementService(
        _FakeMT5(),
        OrderManagementStateStore(tmp_path / "state.json"),
        feature_enabled=True,
        rollout_settings=OrderManagementSettings(stage="SHADOW"),
        observability_service=_ObservabilityStub(),
        executor=_ImmediateExecutor(),
    )


def _pos_dict(position: BrokerPosition) -> dict:
    md = position.symbol_metadata
    return {
        "position_id": position.position_id,
        "symbol": position.broker_symbol,
        "broker_symbol": position.broker_symbol,
        "side": position.side,
        "open_price": position.open_price,
        "price": position.open_price,
        "sl": position.sl,
        "digits": md.digits,
        "point": md.point,
        "trade_tick_size": md.trade_tick_size,
        "magic": position.magic,
        "comment": position.comment,
    }


def _make_screen(service, positions: list[dict]):
    from ui.screens.orders_screen import OrdersScreen

    screen = OrdersScreen.__new__(OrdersScreen)
    screen.order_manager = service
    screen._trailing_configs = {}
    # Mirror runtime behaviour: original SL is remembered from the service read
    # model (a BUY initial SL stays below entry even after BE/trailing moved
    # the broker SL above entry).
    screen._position_original_sl = {
        view.position_id: view.initial_sl for view in service.cached_states()
    }
    screen._positions = positions
    screen._render_table = MagicMock()
    screen._debounce_save = MagicMock()
    screen._dlg_pip_spin = SimpleNamespace(value=lambda: 20)
    screen._dlg_trail_mode = "wide"
    screen._dlg_enable_btn = SimpleNamespace(setText=lambda text: None)
    screen._get_selected_position = lambda: positions[0]
    return screen


def _enable(monkeypatch, screen, pos_id: int) -> str | None:
    """Drive the real OrdersScreen enable handler (managed path).

    Returns the "Đã bật Trailing Stop" detail text so tests can assert the
    popup reports the actual resumed trail mode.
    """
    dlg = SimpleNamespace(accept=lambda: None)
    close_btn = SimpleNamespace()
    captured: dict[str, str] = {}

    def _info(*args, **kwargs):
        captured["detail"] = args[2] if len(args) > 2 else ""

    monkeypatch.setattr(QMessageBox, "information", _info)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    screen._handle_enable_trailing(
        pos_id,
        "EURUSDm",
        "buy",
        dlg,
        lambda *btns: None,
        lambda: None,
        close_btn,
    )
    return captured.get("detail")


def _force_phase(
    service,
    pos_id: int,
    phase: ManagementPhase,
    extreme_price: float,
    broker_sl: float | None = None,
) -> None:
    """Fixture: place the managed state directly into a lifecycle phase.

    When the phase is a trailing phase the broker SL must already be at/above
    BE, otherwise the state machine's broker-authoritative guard re-enters
    WAITING_BE (that guard is real behavior, not the bug under test).
    """
    with service._lock:
        runtime = service._states[pos_id]
        runtime.state = replace(
            runtime.state,
            phase=phase,
            extreme_price=extreme_price,
        )
    if broker_sl is not None:
        position = service.mt5.positions[0]
        service.mt5.positions = (replace(position, sl=broker_sl),)


# ---------------------------------------------------------------------------
# Test 1 — bật position hoàn toàn mới
# ---------------------------------------------------------------------------


def test_enable_new_position_projects_waiting_be(tmp_path, monkeypatch) -> None:
    service = _make_service(tmp_path)
    pos = _pos_dict(service.mt5.positions[0])
    screen = _make_screen(service, [pos])

    _enable(monkeypatch, screen, 41)

    view = service.cached_states()[0]
    assert view.phase == "waiting_be"
    cfg = screen._trailing_configs[41]
    assert cfg["phase"] == "waiting_be"
    assert cfg["be_done"] is False
    assert cfg["enabled"] is True
    assert screen._render_table.called


def test_enable_new_position_honors_dialog_mode_selection(tmp_path, monkeypatch) -> None:
    """Fresh enable keeps the user's dialog mode — the waiting_be projection
    must not override it (the trail-mode override only applies to trailing
    phases the service actually resumed into)."""
    service = _make_service(tmp_path)
    pos = _pos_dict(service.mt5.positions[0])
    screen = _make_screen(service, [pos])
    screen._dlg_trail_mode = "tight"

    detail = _enable(monkeypatch, screen, 41)

    assert service.cached_states()[0].phase == "waiting_be"
    assert "Tight" in (detail or "")


# ---------------------------------------------------------------------------
# Test 2 — resume từ TRAIL_WIDE
# ---------------------------------------------------------------------------


def test_resume_from_trail_wide_keeps_phase_and_extreme_price(tmp_path, monkeypatch) -> None:
    service = _make_service(tmp_path)
    service.register_position(
        verified_ticket=41,
        broker_symbol="EURUSDm",
        side="buy",
        actual_entry_price=1.1,
        initial_sl=1.098,
        atr=0.0008,
    )
    _force_phase(service, 41, ManagementPhase.TRAIL_WIDE, extreme_price=1.1040, broker_sl=1.1005)
    service.pause_position(41)

    with service._lock:
        assert service._states[41].state.phase is ManagementPhase.PAUSED
        assert (
            service._states[41].state.resume_phase is ManagementPhase.TRAIL_WIDE
        )

    screen = _make_screen(service, [_pos_dict(service.mt5.positions[0])])
    detail = _enable(monkeypatch, screen, 41)

    view = service.cached_states()[0]
    assert view.phase == "trail_wide"
    assert view.extreme_price == 1.1040
    cfg = screen._trailing_configs[41]
    assert cfg["phase"] == "trail_wide"
    assert cfg["be_done"] is True
    assert cfg["enabled"] is True
    assert cfg["extreme_price"] == 1.1040
    assert "Wide" in (detail or "")


# ---------------------------------------------------------------------------
# Test 3 — resume từ TRAIL_TIGHT
# ---------------------------------------------------------------------------


def test_resume_from_trail_tight_keeps_phase_and_extreme_price(tmp_path, monkeypatch) -> None:
    service = _make_service(tmp_path)
    service.register_position(
        verified_ticket=41,
        broker_symbol="EURUSDm",
        side="buy",
        actual_entry_price=1.1,
        initial_sl=1.098,
        atr=0.0008,
    )
    _force_phase(service, 41, ManagementPhase.TRAIL_TIGHT, extreme_price=1.1050, broker_sl=1.1005)
    service.pause_position(41)

    screen = _make_screen(service, [_pos_dict(service.mt5.positions[0])])
    detail = _enable(monkeypatch, screen, 41)

    view = service.cached_states()[0]
    assert view.phase == "trail_tight"
    assert view.extreme_price == 1.1050
    cfg = screen._trailing_configs[41]
    assert cfg["phase"] == "trail_tight"
    assert cfg["be_done"] is True
    assert cfg["enabled"] is True
    assert cfg["extreme_price"] == 1.1050
    assert "Tight" in (detail or "")


# ---------------------------------------------------------------------------
# Test 4 — không tạo state UI giả: projection khớp read model service
# ---------------------------------------------------------------------------


def test_ui_config_matches_service_read_model_after_resume(tmp_path, monkeypatch) -> None:
    service = _make_service(tmp_path)
    service.register_position(
        verified_ticket=41,
        broker_symbol="EURUSDm",
        side="buy",
        actual_entry_price=1.1,
        initial_sl=1.098,
        atr=0.0008,
    )
    _force_phase(service, 41, ManagementPhase.TRAIL_WIDE, extreme_price=1.1040, broker_sl=1.1005)
    service.pause_position(41)

    screen = _make_screen(service, [_pos_dict(service.mt5.positions[0])])
    _enable(monkeypatch, screen, 41)

    cfg = screen._trailing_configs[41]
    # Re-project the authoritative service state and compare field-for-field.
    projected: dict[int, dict] = {}
    screen._trailing_configs = {}
    screen._sync_managed_views()
    authoritative = screen._trailing_configs[41]
    for field in ("phase", "be_done", "extreme_price", "enabled"):
        assert cfg[field] == authoritative[field], field
    assert cfg["phase"] == "trail_wide"
    assert cfg["be_done"] is True
    assert cfg["extreme_price"] == 1.1040
    assert cfg["enabled"] is True


# ---------------------------------------------------------------------------
# Test 5 — luồng trực tiếp không bị gãy
# ---------------------------------------------------------------------------


def test_pause_resume_flow_and_new_registration_unbroken(tmp_path, monkeypatch) -> None:
    service = _make_service(tmp_path)

    # Pause vẫn lưu resume_phase.
    service.register_position(
        verified_ticket=41,
        broker_symbol="EURUSDm",
        side="buy",
        actual_entry_price=1.1,
        initial_sl=1.098,
        atr=0.0008,
    )
    _force_phase(service, 41, ManagementPhase.TRAIL_TIGHT, extreme_price=1.1050, broker_sl=1.1005)
    service.pause_position(41)
    with service._lock:
        assert service._states[41].state.resume_phase is ManagementPhase.TRAIL_TIGHT

    # Resume qua handler OrdersScreen phục hồi đúng phase.
    screen = _make_screen(service, [_pos_dict(service.mt5.positions[0])])
    _enable(monkeypatch, screen, 41)
    assert service.cached_states()[0].phase == "trail_tight"
    assert screen._trailing_configs[41]["phase"] == "trail_tight"
    assert screen._render_table.called

    # Bật position mới vẫn đăng ký thành công.
    pos42 = replace(service.mt5.positions[0], position_id=42, sl=1.098)
    service.mt5.positions = service.mt5.positions + (pos42,)
    pos_new = _pos_dict(pos42)
    screen2 = _make_screen(service, [pos_new])
    _enable(monkeypatch, screen2, 42)
    assert service.cached_states()[0].position_id == 41
    assert service.cached_states()[1].position_id == 42
    assert service.cached_states()[1].phase == "waiting_be"
    assert screen2._trailing_configs[42]["phase"] == "waiting_be"

    # No broker action was requested (SHADOW) — BE/trailing formula untouched.
    assert service.mt5.modify_calls == []


def test_legacy_enable_without_manager_still_builds_local_config(tmp_path, monkeypatch) -> None:
    """order_manager is None → compatibility path keeps the legacy local dict."""
    from ui.screens.orders_screen import OrdersScreen

    pos = _pos_dict(_position())
    screen = OrdersScreen.__new__(OrdersScreen)
    screen.order_manager = None
    screen._trailing_configs = {}
    screen._position_original_sl = {}
    screen._positions = [pos]
    screen._render_table = MagicMock()
    screen._debounce_save = MagicMock()
    screen._dlg_pip_spin = SimpleNamespace(value=lambda: 20)
    screen._dlg_trail_mode = "wide"
    screen._dlg_enable_btn = SimpleNamespace(setText=lambda text: None)
    screen._get_selected_position = lambda: pos

    _enable(monkeypatch, screen, 41)

    cfg = screen._trailing_configs[41]
    assert cfg["enabled"] is True
    assert cfg["be_done"] is False
    assert cfg["extreme_price"] == 0.0
    assert screen._debounce_save.called
    assert screen._render_table.called