from __future__ import annotations

from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from threading import Event, get_ident

from config.settings import OrderManagementSettings
import services.order_management_service as order_management_service_module
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
from services.order_management_state_store import (
    ManagedPositionState as StoredManagedPosition,
    OrderManagementStateStore,
)


class ImmediateExecutor(Executor):
    def submit(self, fn, /, *args, **kwargs):
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as exc:  # pragma: no cover - Future contract
            future.set_exception(exc)
        return future


class ObservabilityStub:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def emit(self, event_type, **kwargs):
        event = {"event_type": event_type, **kwargs}
        self.events.append(event)
        return event


def _account(
    login: int = 1001,
    mode: AccountTradeMode = AccountTradeMode.DEMO,
) -> AccountIdentity:
    return AccountIdentity(
        "Broker",
        "Broker-Demo",
        login,
        mode,
        trade_allowed=True,
    )


def _position(
    *,
    ticket: int = 41,
    symbol: str = "EURUSDm",
    side: str = "buy",
    entry: float = 1.1,
    sl: float = 1.098,
    tp: float = 1.106,
) -> BrokerPosition:
    return BrokerPosition(
        position_id=ticket,
        broker_symbol=symbol,
        app_symbol="EUR/USD",
        side=side,
        volume=0.1,
        open_price=entry,
        current_price=1.102,
        sl=sl,
        tp=tp,
        profit=20.0,
        swap=0.0,
        commission=0.0,
        magic=260609,
        comment="AMA-FWD:abcdef123456",
        open_time=1_700_000_000,
        identifier=ticket,
        symbol_metadata=BrokerSymbolMetadata(
            digits=5,
            point=0.00001,
            trade_tick_size=0.00001,
            trade_stops_level=10,
            trade_freeze_level=0,
            volume_step=0.01,
        ),
    )


class FakeMT5:
    def __init__(self) -> None:
        self.account = _account()
        self.positions_status = SnapshotStatus.AVAILABLE
        self.positions: tuple[BrokerPosition, ...] = (_position(),)
        self.pending_status = SnapshotStatus.AVAILABLE
        self.modify_calls: list[dict] = []
        self.modify_status = OperationStatus.CONFIRMED
        self.modify_retcode = 10009
        self.operation_thread_ids: list[int] = []

    def positions_snapshot(self) -> PositionsSnapshot:
        return PositionsSnapshot(
            self.positions_status,
            self.account if self.positions_status is SnapshotStatus.AVAILABLE else None,
            self.positions if self.positions_status is SnapshotStatus.AVAILABLE else (),
            datetime.now(timezone.utc),
            message=(
                ""
                if self.positions_status is SnapshotStatus.AVAILABLE
                else "terminal disconnected"
            ),
        )

    def pending_orders_snapshot(self) -> PendingOrdersSnapshot:
        return PendingOrdersSnapshot(
            self.pending_status,
            self.account if self.pending_status is SnapshotStatus.AVAILABLE else None,
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
        self.operation_thread_ids.append(get_ident())
        self.modify_calls.append({"position_id": position_id, **kwargs})
        if self.modify_status is OperationStatus.CONFIRMED:
            self.positions = tuple(
                replace(
                    position,
                    sl=float(kwargs.get("sl", position.sl)),
                    tp=float(kwargs.get("tp", position.tp)),
                )
                if position.position_id == position_id
                else position
                for position in self.positions
            )
        return {
            "success": self.modify_status is OperationStatus.CONFIRMED,
            "status": self.modify_status.value,
            "position_id": position_id,
            "effective_sl": kwargs.get("sl"),
            "effective_tp": kwargs.get("tp"),
            "retcode": self.modify_retcode,
            "message": "ok" if self.modify_status is OperationStatus.CONFIRMED else "reject",
        }

    def close_position(self, position_id: int, **kwargs):
        self.operation_thread_ids.append(get_ident())
        return {
            "success": False,
            "status": OperationStatus.PARTIAL.value,
            "position_id": position_id,
            "remaining_volume": 0.05,
            **kwargs,
        }


def _service(tmp_path, fake: FakeMT5, rollout: OrderManagementSettings):
    return OrderManagementService(
        fake,
        OrderManagementStateStore(tmp_path / "state.json"),
        feature_enabled=True,
        rollout_settings=rollout,
        observability_service=ObservabilityStub(),
        executor=ImmediateExecutor(),
    )


def _register(service: OrderManagementService) -> None:
    service.register_position(
        verified_ticket=41,
        broker_symbol="EURUSDm",
        side="buy",
        actual_entry_price=1.1,
        initial_sl=1.098,
        atr=0.0008,
        correlation_id="abcdef123456",
    )


def test_unavailable_snapshot_marks_stale_but_keeps_tracking(tmp_path) -> None:
    fake = FakeMT5()
    fake.positions_status = SnapshotStatus.UNAVAILABLE
    service = _service(tmp_path, fake, OrderManagementSettings(stage="SHADOW"))

    _register(service)

    states = service.cached_states()
    assert len(states) == 1
    assert states[0].phase == "stale"
    assert "disconnected" in (states[0].last_error or "")


def test_confirmed_empty_snapshot_is_the_only_cleanup_path(tmp_path) -> None:
    fake = FakeMT5()
    fake.positions = ()
    service = _service(tmp_path, fake, OrderManagementSettings(stage="SHADOW"))

    _register(service)

    assert service.cached_states() == ()


def test_shadow_mode_computes_intent_without_sending_broker_request(tmp_path) -> None:
    fake = FakeMT5()
    service = _service(tmp_path, fake, OrderManagementSettings(stage="SHADOW"))

    _register(service)

    assert fake.modify_calls == []
    assert service.cached_states()[0].phase == "waiting_be"


def test_demo_mode_confirms_be_and_preserves_tp(tmp_path) -> None:
    fake = FakeMT5()
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))

    _register(service)

    assert len(fake.modify_calls) == 1
    request = fake.modify_calls[0]
    assert request["tp"] == 1.106
    assert request["sl"] >= 1.1
    assert request["expected_sl"] == 1.098
    assert request["expected_tp"] == 1.106
    assert request["enforce_snapshot_precondition"] is True
    assert service.cached_states()[0].phase == "be_active"


def test_unknown_retryable_retcode_enters_bounded_backoff(tmp_path) -> None:
    fake = FakeMT5()
    fake.modify_status = OperationStatus.UNKNOWN
    fake.modify_retcode = 10004  # requote
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))

    _register(service)

    state = service.cached_states()[0]
    assert state.phase == "error_retryable"
    assert state.retry_count == 1
    assert len(fake.modify_calls) == 1


def test_unavailable_snapshot_cannot_rebind_persistence_account(tmp_path) -> None:
    fake = FakeMT5()
    account_a = fake.account
    account_b = _account(login=2002)
    service = _service(tmp_path, fake, OrderManagementSettings(stage="SHADOW"))
    _register(service)
    assert service.state_store.load(account=account_a).ok is True

    fake.positions_snapshot = lambda: PositionsSnapshot(
        SnapshotStatus.UNAVAILABLE,
        account_b,
        (),
        datetime.now(timezone.utc),
        message="account transition snapshot unavailable",
    )
    service.request_refresh()

    assert service.state_store.load(account=account_a).ok is True
    assert service.state_store.load(account=account_b).ok is False
    assert service.cached_health().execution_allowed is False


def test_cross_account_position_and_pending_snapshots_fail_closed(tmp_path) -> None:
    fake = FakeMT5()
    other_account = _account(login=2002)
    fake.pending_orders_snapshot = lambda: PendingOrdersSnapshot(
        SnapshotStatus.AVAILABLE,
        other_account,
        (),
        datetime.now(timezone.utc),
    )
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))

    _register(service)

    assert service.cached_health().snapshot_status is SnapshotStatus.STALE
    assert service.cached_health().execution_allowed is False
    assert service.cached_positions() == ()
    assert service.cached_pending_orders() == ()
    assert service.cached_states()[0].phase == "stale"
    assert fake.modify_calls == []


def test_tick_from_different_account_cannot_drive_automatic_mutation(tmp_path) -> None:
    fake = FakeMT5()
    other_account = _account(login=2002)
    fake.symbol_tick = lambda symbol: TickSnapshot(
        SnapshotStatus.AVAILABLE,
        other_account,
        BrokerTick(symbol, bid=1.1022, ask=1.1024, time=1, time_msc=1000),
        datetime.now(timezone.utc),
    )
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))

    _register(service)

    assert service.cached_states()[0].phase == "stale"
    assert fake.modify_calls == []


def test_pause_wins_race_against_in_progress_automatic_evaluation(
    tmp_path, monkeypatch
) -> None:
    fake = FakeMT5()
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))
    original_evaluate = order_management_service_module.evaluate

    def evaluate_then_pause(*args, **kwargs):
        decision = original_evaluate(*args, **kwargs)
        service.pause_position(41)
        return decision

    monkeypatch.setattr(
        order_management_service_module,
        "evaluate",
        evaluate_then_pause,
    )

    _register(service)

    assert service.cached_states()[0].phase == "paused"
    assert fake.modify_calls == []


def test_restored_pending_action_is_forced_through_stale_reconciliation() -> None:
    stored = StoredManagedPosition(
        ticket=41,
        symbol="EURUSDm",
        side="buy",
        original_sl=1.098,
        trailing={
            "phase": "waiting_be",
            "entry_price": 1.1,
            "initial_sl": 1.098,
            "pending_action": {
                "kind": "modify_sl",
                "reason": "breakeven",
                "position_id": 41,
                "side": "buy",
                "target_sl": 1.1,
                "preserve_tp": 1.106,
                "expected_broker_sl": 1.098,
                "source_phase": "waiting_be",
                "close_price": 1.1022,
                "tick_size": 0.00001,
            },
        },
    )

    runtime = OrderManagementService._restore_runtime(stored)

    assert runtime is not None
    assert runtime.state.phase.value == "stale"
    assert runtime.state.resume_phase is not None
    assert runtime.state.resume_phase.value == "waiting_be"


def test_missing_atr_is_explicit_and_never_falls_back_to_fixed_pips(tmp_path) -> None:
    fake = FakeMT5()
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))
    service.register_position(
        verified_ticket=41,
        broker_symbol="EURUSDm",
        side="buy",
        actual_entry_price=1.1,
        initial_sl=1.098,
        atr=None,
    )

    service.request_refresh()  # BE_ACTIVE -> TRAIL_WIDE
    service.request_refresh()  # explicit ATR warning, no fallback request

    state = service.cached_states()[0]
    assert state.last_error == "atr_unavailable"
    assert len(fake.modify_calls) == 1  # BE only


def test_demo_stage_fails_closed_on_live_account(tmp_path) -> None:
    fake = FakeMT5()
    fake.account = _account(mode=AccountTradeMode.REAL)
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))

    _register(service)

    assert fake.modify_calls == []
    assert service.cached_health().execution_allowed is False


def test_demo_stage_fails_closed_when_trading_permission_is_unknown(
    tmp_path,
) -> None:
    fake = FakeMT5()
    fake.account = replace(fake.account, trade_allowed=None)
    service = _service(tmp_path, fake, OrderManagementSettings(stage="DEMO"))

    _register(service)

    assert fake.modify_calls == []
    assert service.cached_health().execution_allowed is False


def test_canary_requires_exact_symbol_and_ticket(tmp_path) -> None:
    fake = FakeMT5()
    rollout = OrderManagementSettings(
        stage="CANARY",
        canary_broker_symbol="EURUSDm",
        canary_position_id=999,
    )
    service = _service(tmp_path, fake, rollout)

    _register(service)

    assert fake.modify_calls == []


def test_production_requires_live_account_approval_and_demo_gate_off(tmp_path) -> None:
    fake = FakeMT5()
    fake.account = _account(mode=AccountTradeMode.REAL)
    blocked = _service(
        tmp_path,
        fake,
        OrderManagementSettings(
            stage="PRODUCTION",
            production_approved=True,
            require_demo_account=True,
        ),
    )
    _register(blocked)
    assert fake.modify_calls == []

    allowed_fake = FakeMT5()
    allowed_fake.account = _account(login=1002, mode=AccountTradeMode.REAL)
    allowed = _service(
        tmp_path / "allowed",
        allowed_fake,
        OrderManagementSettings(
            stage="PRODUCTION",
            production_approved=True,
            require_demo_account=False,
        ),
    )
    _register(allowed)
    assert len(allowed_fake.modify_calls) == 1


def test_policy_update_applies_without_restart(tmp_path) -> None:
    fake = FakeMT5()
    service = _service(tmp_path, fake, OrderManagementSettings(stage="SHADOW"))
    _register(service)
    assert fake.modify_calls == []

    service.update_policy(
        feature_enabled=True,
        rollout_settings=OrderManagementSettings(stage="DEMO"),
    )
    service.request_refresh()

    assert len(fake.modify_calls) == 1


def test_partial_close_does_not_unregister_managed_position(tmp_path) -> None:
    fake = FakeMT5()
    service = _service(tmp_path, fake, OrderManagementSettings(stage="SHADOW"))
    _register(service)

    future = service.close_position(41, volume=0.05)

    assert future is not None
    assert future.result()["status"] == "partial"
    assert service.cached_states()[0].position_id == 41


def test_kill_switch_blocks_manual_broker_mutations(tmp_path) -> None:
    fake = FakeMT5()
    service = _service(
        tmp_path,
        fake,
        OrderManagementSettings(stage="DEMO", kill_switch=True),
    )

    assert service.modify_position(41, sl=1.1, tp=1.106) is None
    assert service.close_position(41) is None
    assert fake.modify_calls == []


def test_kill_switch_recheck_cancels_manual_mutation_waiting_in_queue(
    tmp_path,
) -> None:
    fake = FakeMT5()
    executor = ThreadPoolExecutor(max_workers=1)
    blocker_started = Event()
    release_blocker = Event()

    def blocker() -> None:
        blocker_started.set()
        release_blocker.wait(timeout=2)

    executor.submit(blocker)
    assert blocker_started.wait(timeout=1)
    service = OrderManagementService(
        fake,
        OrderManagementStateStore(tmp_path / "state.json"),
        feature_enabled=False,
        rollout_settings=OrderManagementSettings(stage="SHADOW"),
        observability_service=ObservabilityStub(),
        executor=executor,
    )
    service._poll_cycle()
    future = service.modify_position(41, sl=1.1, tp=1.106)
    assert future is not None

    service.update_policy(
        feature_enabled=False,
        rollout_settings=OrderManagementSettings(
            stage="SHADOW",
            kill_switch=True,
        ),
    )
    release_blocker.set()
    result = future.result(timeout=2)

    assert result["status"] == OperationStatus.REJECTED.value
    assert result["precondition_failed"] is True
    assert fake.modify_calls == []
    executor.shutdown(wait=True)


def test_kill_switch_recheck_cancels_automatic_intent_before_send(
    tmp_path,
) -> None:
    fake = FakeMT5()
    rollout = OrderManagementSettings(stage="DEMO")
    service = _service(tmp_path, fake, rollout)
    original_emit = service._emit_event

    def enable_kill_switch_on_request(event_type, *args, **kwargs):
        if event_type == "SL_MODIFY_REQUESTED":
            service.update_policy(
                feature_enabled=True,
                rollout_settings=replace(rollout, kill_switch=True),
            )
        return original_emit(event_type, *args, **kwargs)

    service._emit_event = enable_kill_switch_on_request

    _register(service)

    assert fake.modify_calls == []
    assert service.cached_states()[0].pending_action is None


def test_real_executor_runs_broker_operation_off_calling_thread(tmp_path) -> None:
    fake = FakeMT5()
    executor = ThreadPoolExecutor(max_workers=1)
    service = OrderManagementService(
        fake,
        OrderManagementStateStore(tmp_path / "state.json"),
        feature_enabled=False,
        rollout_settings=OrderManagementSettings(),
        observability_service=ObservabilityStub(),
        executor=executor,
    )
    service._poll_cycle()
    caller_thread = get_ident()

    future = service.modify_position(41, sl=1.1, tp=1.106)
    assert future is not None
    future.result(timeout=2)

    assert fake.operation_thread_ids[-1] != caller_thread
    assert fake.modify_calls[-1]["expected_account_fingerprint"] == fake.account.fingerprint
    assert fake.modify_calls[-1]["expected_broker_symbol"] == "EURUSDm"
    executor.shutdown(wait=True)
