"""Thread-safe runtime service for broker-authoritative order management.

The service is the only bridge between the pure state machine and MT5.  Qt
timers merely schedule work; every broker call runs on one serial executor.
Consequently Scanner workers can register a newly opened position without
touching a QWidget, and OrdersScreen can render cached snapshots without doing
blocking broker I/O on the GUI thread.
"""

from __future__ import annotations

from concurrent.futures import Executor, Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from threading import RLock
from time import monotonic
from typing import Any, Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from config.settings import OrderManagementSettings
from core.order_management_state_machine import (
    ActionConfirmation,
    ActionKind,
    ActionReason,
    BrokerPositionSnapshot,
    ConfirmationStatus,
    DesiredAction,
    ManagedPositionState,
    ManagementPhase,
    ManagementSettings,
    MarketTick,
    PositionSide,
    SymbolConstraints,
    apply_confirmation,
    evaluate,
    pause,
    resume,
    start_management,
)
from services.mt5_service import MT5Service
from services.observability_service import (
    StructuredObservabilityService,
    structured_observability,
)
from services.order_management_models import (
    AccountIdentity,
    BrokerPosition,
    OperationStatus,
    PendingOrdersSnapshot,
    PositionsSnapshot,
    SnapshotStatus,
    TickSnapshot,
)
from services.order_management_state_store import (
    ManagedPositionState as StoredManagedPosition,
    OrderManagementStateStatus,
    OrderManagementStateStore,
)


_RETRYABLE_TRADE_RETCODES = {
    10004,  # requote
    10012,  # timeout
    10020,  # price changed
    10021,  # no quotes
    10024,  # too many requests
    10028,  # locked
    10031,  # connection unavailable
}


@dataclass(frozen=True, slots=True)
class OrderManagementHealth:
    snapshot_status: SnapshotStatus
    stage: str
    execution_allowed: bool
    account: AccountIdentity | None
    observed_at_utc: datetime | None
    message: str = ""
    in_flight: bool = False


@dataclass(frozen=True, slots=True)
class ManagedPositionView:
    position_id: int
    broker_symbol: str
    side: str
    phase: str
    entry_price: float
    initial_sl: float
    extreme_price: float | None
    atr: float | None
    pending_action: str | None
    retry_count: int
    last_error: str | None
    last_confirmed_at_utc: datetime | None


@dataclass(slots=True)
class _RuntimePosition:
    state: ManagedPositionState
    broker_symbol: str
    atr: float | None = None
    magic: int | None = 260609
    correlation_id: str = ""
    last_confirmed_at_utc: datetime | None = None


class OrderManagementService(QObject):
    """Own managed-position state and serialize all MT5 access off the UI thread."""

    snapshot_updated = pyqtSignal(object)
    state_changed = pyqtSignal(object)
    operation_failed = pyqtSignal(object)
    operation_completed = pyqtSignal(object)
    health_changed = pyqtSignal(object)
    event_emitted = pyqtSignal(object)

    def __init__(
        self,
        mt5_service: MT5Service,
        state_store: OrderManagementStateStore | None = None,
        *,
        feature_enabled: bool = False,
        rollout_settings: OrderManagementSettings | None = None,
        observability_service: StructuredObservabilityService | None = None,
        clock: Callable[[], float] | None = None,
        executor: Executor | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.mt5 = mt5_service
        self.state_store = state_store or OrderManagementStateStore()
        self.observability = observability_service or structured_observability
        self._feature_enabled = bool(feature_enabled)
        self._rollout = rollout_settings or OrderManagementSettings()
        self._clock = clock or monotonic
        self._executor = executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="ama-order-management",
        )
        self._owns_executor = executor is None
        self._lock = RLock()
        self._states: dict[int, _RuntimePosition] = {}
        self._ticks: dict[str, TickSnapshot] = {}
        self._positions_snapshot: PositionsSnapshot | None = None
        self._pending_snapshot: PendingOrdersSnapshot | None = None
        self._active_account: AccountIdentity | None = None
        self._loaded_account_fingerprint: str | None = None
        self._refresh_future: Future[Any] | None = None
        self._shutdown = False
        self._health = OrderManagementHealth(
            snapshot_status=SnapshotStatus.UNAVAILABLE,
            stage=self._rollout.stage,
            execution_allowed=False,
            account=None,
            observed_at_utc=None,
            message="Broker snapshot has not been loaded.",
        )

        self._timer = QTimer(self)
        self._timer.setInterval(self._poll_interval_ms())
        self._timer.timeout.connect(self.request_refresh)

    # -- lifecycle -----------------------------------------------------

    def start(self) -> None:
        """Start scheduling background refreshes from the object's Qt thread."""

        with self._lock:
            if self._shutdown:
                return
        self._timer.setInterval(self._poll_interval_ms())
        if not self._timer.isActive():
            self._timer.start()
        self.request_refresh()

    def shutdown(self) -> None:
        """Stop scheduling, finish queued broker work, and flush durable state."""

        self._timer.stop()
        with self._lock:
            if self._shutdown:
                return
            self._shutdown = True
        if self._owns_executor:
            self._executor.shutdown(wait=True, cancel_futures=False)  # type: ignore[attr-defined]
        self._persist_state()
        self.state_store.flush()

    def update_policy(
        self,
        *,
        feature_enabled: bool,
        rollout_settings: OrderManagementSettings,
    ) -> None:
        """Apply saved rollout settings without requiring an app restart."""

        with self._lock:
            self._feature_enabled = bool(feature_enabled)
            self._rollout = rollout_settings
        self._timer.setInterval(self._poll_interval_ms())
        self._publish_health()

    # -- cached read model ---------------------------------------------

    def cached_positions(self) -> tuple[BrokerPosition, ...]:
        with self._lock:
            snapshot = self._positions_snapshot
            return snapshot.positions if snapshot and snapshot.available else ()

    def cached_pending_orders(self) -> tuple[object, ...]:
        with self._lock:
            snapshot = self._pending_snapshot
            return snapshot.orders if snapshot and snapshot.available else ()

    def cached_health(self) -> OrderManagementHealth:
        with self._lock:
            return self._health

    def cached_states(self) -> tuple[ManagedPositionView, ...]:
        with self._lock:
            return tuple(
                self._view(runtime)
                for _ticket, runtime in sorted(self._states.items())
            )

    def latest_tick(self, broker_symbol: str) -> TickSnapshot | None:
        with self._lock:
            return self._ticks.get(str(broker_symbol or ""))

    def _position_mutation_context(
        self,
        position_id: int,
    ) -> tuple[str, str] | None:
        with self._lock:
            snapshot = self._positions_snapshot
            if snapshot is None or not snapshot.available or snapshot.account is None:
                return None
            for position in snapshot.positions:
                if position.position_id == int(position_id):
                    return snapshot.account.fingerprint, position.broker_symbol
        return None

    def _pending_mutation_context(
        self,
        order_id: int,
    ) -> tuple[str, str] | None:
        with self._lock:
            snapshot = self._pending_snapshot
            if snapshot is None or not snapshot.available or snapshot.account is None:
                return None
            for order in snapshot.orders:
                if order.order_id == int(order_id):
                    return snapshot.account.fingerprint, order.broker_symbol
        return None

    def _report_missing_mutation_context(self, operation: str, ticket: int) -> None:
        payload = {
            "operation": operation,
            "success": False,
            "position_id": int(ticket),
            "message": (
                "A fresh account-scoped broker snapshot is required before "
                "submitting this mutation."
            ),
        }
        self.operation_failed.emit(payload)
        self._emit_event(
            "STATE_RECONCILIATION_FAILED",
            severity="ERROR",
            payload=payload,
        )

    # -- managed-position commands ------------------------------------

    def register_position(
        self,
        *,
        verified_ticket: int | None = None,
        position_id: int | None = None,
        broker_symbol: str,
        side: str,
        actual_entry_price: float | None = None,
        entry_price: float | None = None,
        initial_sl: float,
        atr: float | None = None,
        atr_h1: float | None = None,
        magic: int | None = 260609,
        correlation_id: str = "",
    ) -> ManagedPositionView:
        """Register only a verified broker position; safe from any caller thread."""

        ticket = int(verified_ticket or position_id or 0)
        actual_entry = float(actual_entry_price or entry_price or 0)
        symbol = str(broker_symbol or "").strip()
        if not symbol:
            raise ValueError("broker_symbol is required")
        core_state = start_management(ticket, side, actual_entry, float(initial_sl))
        resolved_atr = atr if atr is not None else atr_h1
        normalized_atr = (
            float(resolved_atr)
            if resolved_atr is not None and float(resolved_atr) > 0
            else None
        )
        with self._lock:
            current = self._states.get(ticket)
            if current is None:
                runtime = _RuntimePosition(
                    state=core_state,
                    broker_symbol=symbol,
                    atr=normalized_atr,
                    magic=magic,
                    correlation_id=str(correlation_id or ""),
                )
                self._states[ticket] = runtime
            else:
                if (
                    current.broker_symbol != symbol
                    or current.state.side.value != str(side).lower()
                    or not _prices_close(current.state.entry_price, actual_entry)
                ):
                    raise ValueError(
                        "registered position identity conflicts with existing state"
                    )
                current.atr = normalized_atr or current.atr
                current.magic = magic
                current.correlation_id = str(correlation_id or current.correlation_id)
                runtime = current
            view = self._view(runtime)
        self._emit_event("ORDER_MANAGEMENT_ENABLED", runtime)
        self.state_changed.emit(view)
        self._persist_state()
        self.request_refresh()
        return view

    def pause_position(self, position_id: int) -> ManagedPositionView | None:
        return self._transform_state(position_id, pause)

    def resume_position(self, position_id: int) -> ManagedPositionView | None:
        result = self._transform_state(position_id, resume)
        if result is not None:
            self.request_refresh()
        return result

    def unregister_position(self, position_id: int) -> bool:
        """Explicitly stop automation; never called by unavailable cleanup."""

        with self._lock:
            removed = self._states.pop(int(position_id), None)
        if removed is None:
            return False
        self._persist_state()
        self.state_changed.emit(self._view(replace_runtime_phase(removed, ManagementPhase.UNMANAGED)))
        return True

    # -- asynchronous manual operations --------------------------------

    def modify_position(
        self,
        position_id: int,
        *,
        sl: float | None = None,
        tp: float | None = None,
    ) -> Future[Any] | None:
        context = self._position_mutation_context(position_id)
        if context is None:
            self._report_missing_mutation_context("modify_position", position_id)
            return None
        account_fingerprint, broker_symbol = context
        return self.submit_broker_operation(
            "modify_position",
            self.mt5.modify_position_sltp,
            int(position_id),
            sl=sl,
            tp=tp,
            expected_account_fingerprint=account_fingerprint,
            expected_broker_symbol=broker_symbol,
        )

    def close_position(
        self,
        position_id: int,
        *,
        volume: float | None = None,
    ) -> Future[Any] | None:
        context = self._position_mutation_context(position_id)
        if context is None:
            self._report_missing_mutation_context("close_position", position_id)
            return None
        account_fingerprint, broker_symbol = context
        kwargs: dict[str, object] = {
            "expected_account_fingerprint": account_fingerprint,
            "expected_broker_symbol": broker_symbol,
        }
        if volume is not None:
            kwargs["volume"] = volume
        return self.submit_broker_operation(
            "close_position",
            self.mt5.close_position,
            int(position_id),
            **kwargs,
        )

    def cancel_pending_order(self, order_id: int) -> Future[Any] | None:
        method = getattr(self.mt5, "cancel_pending_order", None)
        if not callable(method):
            return None
        context = self._pending_mutation_context(order_id)
        if context is None:
            self._report_missing_mutation_context("cancel_pending_order", order_id)
            return None
        account_fingerprint, broker_symbol = context
        return self.submit_broker_operation(
            "cancel_pending_order",
            method,
            int(order_id),
            expected_account_fingerprint=account_fingerprint,
            expected_broker_symbol=broker_symbol,
        )

    def modify_pending_order(
        self,
        order_id: int,
        **changes: object,
    ) -> Future[Any] | None:
        method = getattr(self.mt5, "modify_pending_order", None)
        if not callable(method):
            return None
        context = self._pending_mutation_context(order_id)
        if context is None:
            self._report_missing_mutation_context("modify_pending_order", order_id)
            return None
        account_fingerprint, broker_symbol = context
        return self.submit_broker_operation(
            "modify_pending_order",
            method,
            int(order_id),
            expected_account_fingerprint=account_fingerprint,
            expected_broker_symbol=broker_symbol,
            **changes,
        )

    def submit_broker_operation(
        self,
        name: str,
        callback: Callable[..., Any],
        *args: object,
        **kwargs: object,
    ) -> Future[Any] | None:
        with self._lock:
            if self._shutdown or self._rollout.kill_switch:
                return None
            runtime = (
                self._states.get(int(args[0]))
                if args and isinstance(args[0], int)
                else None
            )
        requested_event = {
            "close_position": "POSITION_CLOSE_REQUESTED",
            "modify_position": "SL_MODIFY_REQUESTED",
            "cancel_pending_order": "PENDING_ORDER_CANCEL_REQUESTED",
            "modify_pending_order": "PENDING_ORDER_MODIFY_REQUESTED",
        }.get(name)
        if requested_event:
            self._emit_event(
                requested_event,
                runtime,
                payload={
                    "operation": name,
                    "arguments": list(args),
                    "changes": dict(kwargs),
                },
            )
        def execute_if_still_allowed() -> Any:
            with self._lock:
                blocked = self._shutdown or self._rollout.kill_switch
            if blocked:
                return {
                    "success": False,
                    "status": OperationStatus.REJECTED.value,
                    "message": (
                        "The broker mutation was cancelled before execution "
                        "because the order-management kill switch is active."
                    ),
                    "precondition_failed": True,
                }
            return callback(*args, **kwargs)

        future = self._executor.submit(execute_if_still_allowed)

        def completed(done: Future[Any]) -> None:
            try:
                result = done.result()
            except Exception as exc:  # pragma: no cover - defensive boundary
                payload = {"operation": name, "success": False, "message": str(exc)}
                self.operation_failed.emit(payload)
            else:
                payload = {"operation": name, "result": result}
                if isinstance(result, dict) and not result.get("success"):
                    self.operation_failed.emit(payload)
                if isinstance(result, dict):
                    status = str(result.get("status") or "unknown")
                    if name == "close_position":
                        completed_event = (
                            "POSITION_CLOSE_CONFIRMED"
                            if status == OperationStatus.CONFIRMED.value
                            else "POSITION_CLOSE_PARTIAL"
                            if status == OperationStatus.PARTIAL.value
                            else "POSITION_CLOSE_REJECTED"
                        )
                    elif name == "modify_position":
                        completed_event = (
                            "SL_MODIFY_CONFIRMED"
                            if status == OperationStatus.CONFIRMED.value
                            else "SL_MODIFY_REJECTED"
                        )
                    else:
                        completed_event = (
                            name.upper() + "_CONFIRMED"
                            if status == OperationStatus.CONFIRMED.value
                            else name.upper() + "_REJECTED"
                        )
                    self._emit_event(
                        completed_event,
                        runtime,
                        severity=(
                            "INFO"
                            if status
                            in {
                                OperationStatus.CONFIRMED.value,
                                OperationStatus.PARTIAL.value,
                            }
                            else "ERROR"
                        ),
                        payload={
                            "operation": name,
                            "status": status,
                            "retcode": result.get("retcode"),
                            "remaining_volume": result.get("remaining_volume"),
                            "message": result.get("message"),
                        },
                    )
                self.operation_completed.emit(payload)
            self.request_refresh()

        future.add_done_callback(completed)
        return future

    # -- background polling --------------------------------------------

    def request_refresh(self) -> bool:
        """Queue one refresh unless another refresh is already running."""

        with self._lock:
            if self._shutdown:
                return False
            if self._refresh_future is not None and not self._refresh_future.done():
                return False
            future = self._executor.submit(self._poll_cycle)
            self._refresh_future = future
            self._health = replace(self._health, in_flight=True)
        self.health_changed.emit(self.cached_health())
        future.add_done_callback(self._refresh_completed)
        return True

    def _refresh_completed(self, future: Future[Any]) -> None:
        try:
            future.result()
        except Exception as exc:  # pragma: no cover - final containment boundary
            payload = {
                "operation": "refresh",
                "success": False,
                "message": str(exc),
            }
            self.operation_failed.emit(payload)
            with self._lock:
                self._health = replace(
                    self._health,
                    snapshot_status=SnapshotStatus.UNAVAILABLE,
                    execution_allowed=False,
                    message=str(exc),
                )
        finally:
            with self._lock:
                self._refresh_future = None
                self._health = replace(self._health, in_flight=False)
            self.health_changed.emit(self.cached_health())

    def _poll_cycle(self) -> None:
        positions = self.mt5.positions_snapshot()
        pending = self.mt5.pending_orders_snapshot()
        if (
            positions.available
            and positions.account is not None
            and pending.available
            and (
                pending.account is None
                or pending.account.fingerprint != positions.account.fingerprint
            )
        ):
            mismatch_message = (
                "Position and pending-order snapshots belong to different "
                "MT5 accounts; the poll was rejected."
            )
            positions = replace(
                positions,
                status=SnapshotStatus.STALE,
                positions=(),
                message=mismatch_message,
            )
            pending = replace(
                pending,
                status=SnapshotStatus.STALE,
                orders=(),
                message=mismatch_message,
            )
        with self._lock:
            self._positions_snapshot = positions
            self._pending_snapshot = pending
        self.snapshot_updated.emit({"positions": positions, "pending": pending})

        if not positions.available or positions.account is None:
            self._mark_all_stale(positions.message or "Broker snapshot unavailable.")
            self._set_health(
                positions.status,
                positions.account,
                positions.observed_at_utc,
                positions.message or "Broker snapshot unavailable.",
            )
            self._emit_event(
                "BROKER_SNAPSHOT_UNAVAILABLE",
                payload={
                    "error_code": positions.error_code,
                    "message": positions.message,
                },
                severity="ERROR",
            )
            self._persist_state()
            return

        self._activate_account(positions.account, positions.positions)
        self._set_health(
            SnapshotStatus.AVAILABLE,
            positions.account,
            positions.observed_at_utc,
            "Broker snapshot is healthy.",
        )

        broker_positions = {
            position.position_id: position for position in positions.positions
        }
        with self._lock:
            managed_ids = tuple(self._states)

        for position_id in managed_ids:
            with self._lock:
                runtime = self._states.get(position_id)
            if runtime is None:
                continue
            broker_position = broker_positions.get(position_id)
            if broker_position is None:
                self._confirm_closed(runtime)
                continue
            self._evaluate_position(runtime, broker_position, positions.account)

        self._persist_state()

    def _evaluate_position(
        self,
        runtime: _RuntimePosition,
        position: BrokerPosition,
        account: AccountIdentity,
    ) -> None:
        if position.broker_symbol != runtime.broker_symbol:
            failed = replace(
                runtime.state,
                phase=ManagementPhase.ERROR_NON_RETRYABLE,
                pending_action=None,
                last_error="broker_symbol_identity_mismatch",
            )
            self._update_runtime_state(runtime, failed)
            self._emit_event(
                "STATE_RECONCILIATION_FAILED",
                runtime,
                severity="ERROR",
                payload={"reason": "broker_symbol_identity_mismatch"},
            )
            return

        tick_snapshot = self.mt5.symbol_tick(runtime.broker_symbol)
        with self._lock:
            self._ticks[runtime.broker_symbol] = tick_snapshot
        core_position = BrokerPositionSnapshot(
            position_id=position.position_id,
            side=PositionSide(position.side),
            entry_price=position.open_price,
            broker_sl=position.sl,
            broker_tp=position.tp,
            fresh=True,
            exists=True,
        )
        tick_account_matches = (
            tick_snapshot.account is not None
            and tick_snapshot.account.fingerprint == account.fingerprint
        )
        if (
            not tick_snapshot.available
            or tick_snapshot.tick is None
            or not tick_account_matches
        ):
            core_tick = MarketTick(0.0, 0.0, self._clock(), fresh=False)
        else:
            core_tick = MarketTick(
                bid=tick_snapshot.tick.bid,
                ask=tick_snapshot.tick.ask,
                observed_at=self._clock(),
                fresh=True,
            )
        settings = self._management_settings(position, runtime)
        with self._lock:
            if self._states.get(position.position_id) is not runtime:
                return
            observed_state = runtime.state
        input_state = observed_state
        if runtime.atr is not None and input_state.last_error == "atr_unavailable":
            input_state = replace(input_state, last_error=None)
        decision = evaluate(input_state, core_position, core_tick, settings)
        if decision.reason == "atr_unavailable":
            first_warning = decision.state.last_error != "atr_unavailable"
            decision = replace(
                decision,
                state=replace(decision.state, last_error="atr_unavailable"),
            )
            if first_warning:
                self._emit_event(
                    "STATE_RECONCILIATION_FAILED",
                    runtime,
                    severity="WARNING",
                    payload={"reason": "atr_unavailable"},
                )
        if not self._update_runtime_state(
            runtime,
            decision.state,
            expected_state=observed_state,
        ):
            # A UI command (pause/unregister) won the race while the pure
            # decision was being computed.  Never overwrite it or send the
            # now-stale broker intent.
            return
        if decision.action is None:
            return

        allowed, gate_reason = self._execution_gate(account, runtime)
        if not allowed:
            # SHADOW/disabled decisions are intents, not sent requests. Clear
            # pending so the next fresh tick recomputes from broker truth.
            shadow_state = replace(decision.state, pending_action=None)
            if not self._update_runtime_state(
                runtime,
                shadow_state,
                expected_state=decision.state,
            ):
                return
            if self._feature_enabled and self._rollout.stage.upper() == "SHADOW":
                self._emit_event(
                    "SL_MODIFY_SHADOW",
                    runtime,
                    payload={
                        "reason": decision.action.reason.value,
                        "target_sl": decision.action.target_sl,
                        "tp": decision.action.preserve_tp,
                        "gate": gate_reason,
                    },
                )
            return

        if decision.action.reason is ActionReason.BREAKEVEN:
            self._emit_event(
                "BE_TRIGGERED",
                runtime,
                payload={
                    "close_price": decision.action.close_price,
                    "target_sl": decision.action.target_sl,
                },
            )
        self._emit_event(
            "SL_MODIFY_REQUESTED",
            runtime,
            payload={
                "reason": decision.action.reason.value,
                "old_sl": decision.action.expected_broker_sl,
                "new_sl": decision.action.target_sl,
                "tp": decision.action.preserve_tp,
            },
        )
        with self._lock:
            state_is_current = not (
                self._states.get(position.position_id) is not runtime
                or runtime.state != decision.state
            )
            still_allowed = self._execution_gate(account, runtime)[0]
        if not state_is_current or not still_allowed:
            self._update_runtime_state(
                runtime,
                replace(decision.state, pending_action=None),
                expected_state=decision.state,
            )
            return
        result = self.mt5.modify_position_sltp(
            position.position_id,
            sl=decision.action.target_sl,
            tp=decision.action.preserve_tp,
            expected_sl=decision.action.expected_broker_sl,
            expected_tp=decision.action.preserve_tp,
            enforce_snapshot_precondition=True,
            expected_account_fingerprint=account.fingerprint,
            expected_broker_symbol=runtime.broker_symbol,
        )
        confirmation = self._confirmation_from_result(result)
        confirmed_state = apply_confirmation(decision.state, confirmation, settings)
        if confirmation.status is ConfirmationStatus.CONFIRMED:
            runtime.last_confirmed_at_utc = datetime.now(timezone.utc)
            event_type = "SL_MODIFY_CONFIRMED"
            severity = "INFO"
        else:
            event_type = "SL_MODIFY_REJECTED"
            severity = "ERROR"
        self._update_runtime_state(runtime, confirmed_state)
        self._emit_event(
            event_type,
            runtime,
            severity=severity,
            payload={
                "retcode": result.get("retcode"),
                "status": result.get("status"),
                "effective_sl": result.get("effective_sl"),
                "effective_tp": result.get("effective_tp"),
                "message": result.get("message"),
            },
        )
        if confirmation.status is not ConfirmationStatus.CONFIRMED:
            self.operation_failed.emit(
                {
                    "operation": "automatic_sl_modify",
                    "position_id": position.position_id,
                    "result": result,
                }
            )

    # -- account/persistence -------------------------------------------

    def _activate_account(
        self,
        account: AccountIdentity,
        broker_positions: tuple[BrokerPosition, ...],
    ) -> None:
        fingerprint = account.fingerprint
        with self._lock:
            if self._loaded_account_fingerprint == fingerprint:
                return
            first_account = self._loaded_account_fingerprint is None
            pending_registrations = dict(self._states) if first_account else {}
            self._states.clear()
            self._loaded_account_fingerprint = fingerprint
            self._active_account = account

        broker_by_id = {position.position_id: position for position in broker_positions}
        loaded = self.state_store.load(account=account)
        restored: dict[int, _RuntimePosition] = {}
        if loaded.ok and loaded.snapshot is not None:
            for stored in loaded.snapshot.positions:
                broker = broker_by_id.get(stored.ticket)
                if broker is None:
                    continue
                runtime = self._restore_runtime(stored)
                if (
                    runtime is None
                    or runtime.broker_symbol != broker.broker_symbol
                    or runtime.state.side.value != broker.side
                    or not _prices_close(runtime.state.entry_price, broker.open_price)
                ):
                    self._emit_event(
                        "STATE_RECONCILIATION_FAILED",
                        payload={
                            "position_id": stored.ticket,
                            "reason": "persisted_position_identity_mismatch",
                        },
                        severity="ERROR",
                    )
                    continue
                restored[stored.ticket] = runtime
        elif loaded.status not in {
            OrderManagementStateStatus.NOT_FOUND,
            OrderManagementStateStatus.ACCOUNT_MISMATCH,
        }:
            self._emit_event(
                "STATE_RECONCILIATION_FAILED",
                payload={"reason": loaded.status.value, "message": loaded.error},
                severity="ERROR",
            )

        # Registrations created by the just-completed Scanner execution win
        # over an older persisted copy on the first observed account only.
        restored.update(pending_registrations)
        with self._lock:
            self._states.update(restored)

    def _persist_state(self) -> None:
        with self._lock:
            account = self._active_account
            positions = tuple(
                self._stored_position(runtime)
                for runtime in self._states.values()
                if runtime.state.phase
                not in {ManagementPhase.CLOSED, ManagementPhase.UNMANAGED}
            )
        if account is None:
            return
        result = self.state_store.save(account=account, positions=positions)
        if not result.ok:
            self._emit_event(
                "STATE_RECONCILIATION_FAILED",
                payload={"reason": result.status.value, "message": result.error},
                severity="ERROR",
            )

    @staticmethod
    def _stored_position(runtime: _RuntimePosition) -> StoredManagedPosition:
        state = runtime.state
        trailing: dict[str, Any] = {
            "phase": state.phase.value,
            "entry_price": state.entry_price,
            "initial_sl": state.initial_sl,
            "extreme_price": state.extreme_price,
            "resume_phase": state.resume_phase.value if state.resume_phase else None,
            "retry_count": state.retry_count,
            # Monotonic timestamps are process-local; retry safely restarts at
            # zero after a crash/restart rather than persisting an invalid epoch.
            "retry_not_before": 0.0,
            "last_error": state.last_error,
            "pending_action": _serialize_action(state.pending_action),
            "atr": runtime.atr,
            "magic": runtime.magic,
            "correlation_id": runtime.correlation_id,
            "last_confirmed_at_utc": (
                runtime.last_confirmed_at_utc.isoformat()
                if runtime.last_confirmed_at_utc
                else None
            ),
        }
        return StoredManagedPosition(
            ticket=state.position_id,
            symbol=runtime.broker_symbol,
            side=state.side.value,
            original_sl=state.initial_sl,
            trailing=trailing,
        )

    @staticmethod
    def _restore_runtime(stored: StoredManagedPosition) -> _RuntimePosition | None:
        data = stored.trailing
        try:
            side = PositionSide(stored.side)
            phase = ManagementPhase(str(data.get("phase", "waiting_be")))
            resume_value = data.get("resume_phase")
            resume_phase = ManagementPhase(str(resume_value)) if resume_value else None
            action = _restore_action(data.get("pending_action"))
            if action is not None:
                # A process restart cannot know whether an in-flight request
                # reached MT5.  Force broker reconciliation on the first fresh
                # snapshot instead of waiting forever on an orphaned intent.
                phase = ManagementPhase.STALE
                resume_phase = action.source_phase
            state = ManagedPositionState(
                position_id=stored.ticket,
                side=side,
                entry_price=float(data["entry_price"]),
                initial_sl=float(data.get("initial_sl") or stored.original_sl),
                phase=phase,
                extreme_price=_optional_float(data.get("extreme_price")),
                pending_action=action,
                resume_phase=resume_phase,
                retry_count=max(int(data.get("retry_count", 0) or 0), 0),
                retry_not_before=0.0,
                last_error=(str(data["last_error"]) if data.get("last_error") else None),
            )
            confirmed_text = data.get("last_confirmed_at_utc")
            confirmed_at = (
                datetime.fromisoformat(str(confirmed_text))
                if confirmed_text
                else None
            )
            return _RuntimePosition(
                state=state,
                broker_symbol=stored.symbol,
                atr=_optional_float(data.get("atr")),
                magic=(int(data["magic"]) if data.get("magic") is not None else None),
                correlation_id=str(data.get("correlation_id") or ""),
                last_confirmed_at_utc=confirmed_at,
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return None

    # -- helpers -------------------------------------------------------

    def _management_settings(
        self,
        position: BrokerPosition,
        runtime: _RuntimePosition,
    ) -> ManagementSettings:
        metadata = position.symbol_metadata
        digits = metadata.digits if metadata.digits is not None else 5
        point = metadata.point or 10 ** (-digits)
        tick_size = metadata.trade_tick_size or point
        pip_size = max(tick_size, point * (10 if digits in {3, 5} else 1))
        return ManagementSettings(
            constraints=SymbolConstraints(
                point=point,
                tick_size=tick_size,
                digits=digits,
                stops_level_points=max(metadata.trade_stops_level or 0, 0),
                freeze_level_points=max(metadata.trade_freeze_level or 0, 0),
            ),
            atr=runtime.atr,
            be_trigger_r=self._rollout.be_trigger_r,
            be_offset=self._rollout.be_plus_pips * pip_size,
            tight_trigger_r=self._rollout.trail_tight_trigger_r,
            wide_atr_multiplier=self._rollout.trail_wide_atr_multiplier,
            tight_atr_multiplier=self._rollout.trail_tight_atr_multiplier,
            max_retries=self._rollout.max_retry_attempts,
            retry_base_delay_seconds=self._rollout.retry_initial_seconds,
            retry_max_delay_seconds=self._rollout.retry_max_seconds,
        )

    def _execution_gate(
        self,
        account: AccountIdentity,
        runtime: _RuntimePosition | None = None,
    ) -> tuple[bool, str]:
        rollout = self._rollout
        stage = str(rollout.stage or "SHADOW").upper()
        if not self._feature_enabled:
            return False, "feature_disabled"
        if rollout.kill_switch:
            return False, "kill_switch"
        if stage in {"DISABLED", "SHADOW"}:
            return False, stage.lower()
        if account.trade_allowed is not True:
            return False, "trading_not_allowed"
        if stage == "DEMO":
            return (account.is_demo, "demo_account" if account.is_demo else "not_demo")
        if stage == "CANARY":
            if rollout.require_demo_account and not account.is_demo:
                return False, "canary_requires_demo"
            if account.is_live and (
                not rollout.production_approved or rollout.require_demo_account
            ):
                return False, "live_canary_not_approved"
            if runtime is None:
                return False, "canary_target_required"
            symbol_ok = bool(rollout.canary_broker_symbol) and (
                runtime.broker_symbol == rollout.canary_broker_symbol
            )
            ticket_ok = rollout.canary_position_id > 0 and (
                runtime.state.position_id == rollout.canary_position_id
            )
            return (
                symbol_ok and ticket_ok,
                "canary_target" if symbol_ok and ticket_ok else "canary_target_mismatch",
            )
        if stage == "PRODUCTION":
            allowed = (
                rollout.production_approved
                and not rollout.require_demo_account
                and account.is_live
            )
            return allowed, "production_approved" if allowed else "production_blocked"
        return False, "unknown_stage"

    def _set_health(
        self,
        status: SnapshotStatus,
        account: AccountIdentity | None,
        observed_at: datetime | None,
        message: str,
    ) -> None:
        allowed = (
            status is SnapshotStatus.AVAILABLE
            and account is not None
            and self._execution_gate(account)[0]
        )
        with self._lock:
            self._health = OrderManagementHealth(
                snapshot_status=status,
                stage=self._rollout.stage,
                execution_allowed=allowed,
                account=account,
                observed_at_utc=observed_at,
                message=message,
                in_flight=self._health.in_flight,
            )
        self.health_changed.emit(self.cached_health())

    def _publish_health(self) -> None:
        with self._lock:
            current = self._health
        self._set_health(
            current.snapshot_status,
            current.account,
            current.observed_at_utc,
            current.message,
        )

    def _mark_all_stale(self, message: str) -> None:
        with self._lock:
            runtimes = tuple(self._states.values())
        for runtime in runtimes:
            state = runtime.state
            if state.phase in {
                ManagementPhase.CLOSED,
                ManagementPhase.UNMANAGED,
                ManagementPhase.PAUSED,
            }:
                continue
            resume_phase = (
                state.resume_phase
                if state.phase is ManagementPhase.STALE
                else state.phase
            )
            stale = replace(
                state,
                phase=ManagementPhase.STALE,
                resume_phase=resume_phase,
                last_error=message,
            )
            self._update_runtime_state(runtime, stale)

    def _confirm_closed(self, runtime: _RuntimePosition) -> None:
        closed = replace(
            runtime.state,
            phase=ManagementPhase.CLOSED,
            pending_action=None,
            resume_phase=None,
            last_error=None,
        )
        self._update_runtime_state(runtime, closed)
        with self._lock:
            self._states.pop(closed.position_id, None)

    def _transform_state(
        self,
        position_id: int,
        transform: Callable[[ManagedPositionState], ManagedPositionState],
    ) -> ManagedPositionView | None:
        with self._lock:
            runtime = self._states.get(int(position_id))
            if runtime is None:
                return None
            runtime.state = transform(runtime.state)
            view = self._view(runtime)
        self.state_changed.emit(view)
        self._persist_state()
        return view

    def _update_runtime_state(
        self,
        runtime: _RuntimePosition,
        state: ManagedPositionState,
        *,
        expected_state: ManagedPositionState | None = None,
    ) -> bool:
        with self._lock:
            current = self._states.get(state.position_id)
            if current is not runtime:
                return False
            if expected_state is not None and runtime.state != expected_state:
                return False
            previous_phase = runtime.state.phase
            changed = runtime.state != state
            runtime.state = state
            view = self._view(runtime)
        if changed:
            self.state_changed.emit(view)
        if (
            previous_phase != state.phase
            and state.phase
            in {ManagementPhase.TRAIL_WIDE, ManagementPhase.TRAIL_TIGHT}
        ):
            self._emit_event(
                "TRAIL_MODE_CHANGED",
                runtime,
                payload={
                    "old_phase": previous_phase.value,
                    "new_phase": state.phase.value,
                },
            )
        return True

    def _confirmation_from_result(self, result: dict[str, object]) -> ActionConfirmation:
        raw_status = str(result.get("status") or "unknown")
        retcode = _optional_int(result.get("retcode"))
        if raw_status == OperationStatus.CONFIRMED.value:
            status = ConfirmationStatus.CONFIRMED
        elif (
            result.get("precondition_failed") is True
            or retcode in _RETRYABLE_TRADE_RETCODES
        ):
            status = ConfirmationStatus.RETRYABLE_ERROR
        elif raw_status == OperationStatus.UNKNOWN.value:
            status = ConfirmationStatus.UNKNOWN
        else:
            status = ConfirmationStatus.REJECTED
        return ActionConfirmation(
            status=status,
            effective_sl=_optional_float(result.get("effective_sl")),
            effective_tp=_optional_float(result.get("effective_tp")),
            observed_at=self._clock(),
            error_code=_optional_int(result.get("error_code")),
            message=str(result.get("message") or ""),
            position_exists=True,
        )

    def _emit_event(
        self,
        event_type: str,
        runtime: _RuntimePosition | None = None,
        *,
        payload: dict[str, Any] | None = None,
        severity: str = "INFO",
    ) -> None:
        details = dict(payload or {})
        with self._lock:
            account = self._active_account
        if account is not None:
            details.setdefault("account_fingerprint", account.fingerprint)
        if runtime is not None:
            details.setdefault("position_id", runtime.state.position_id)
            details.setdefault("broker_symbol", runtime.broker_symbol)
            details.setdefault("correlation_id", runtime.correlation_id)
        symbol = runtime.broker_symbol if runtime is not None else ""
        try:
            event = self.observability.emit(
                event_type,
                symbol=symbol,
                severity=severity,
                payload=details,
            )
        except Exception as exc:  # observability cannot break protection
            event = {
                "event_type": event_type,
                "severity": severity,
                "symbol": symbol,
                "payload": details,
                "logging_error": str(exc),
            }
        self.event_emitted.emit(event)

    def _poll_interval_ms(self) -> int:
        return max(500, int(float(self._rollout.poll_interval_seconds) * 1000))

    @staticmethod
    def _view(runtime: _RuntimePosition) -> ManagedPositionView:
        state = runtime.state
        return ManagedPositionView(
            position_id=state.position_id,
            broker_symbol=runtime.broker_symbol,
            side=state.side.value,
            phase=state.phase.value,
            entry_price=state.entry_price,
            initial_sl=state.initial_sl,
            extreme_price=state.extreme_price,
            atr=runtime.atr,
            pending_action=(
                state.pending_action.reason.value if state.pending_action else None
            ),
            retry_count=state.retry_count,
            last_error=state.last_error,
            last_confirmed_at_utc=runtime.last_confirmed_at_utc,
        )


def _serialize_action(action: DesiredAction | None) -> dict[str, Any] | None:
    if action is None:
        return None
    return {
        "kind": action.kind.value,
        "reason": action.reason.value,
        "position_id": action.position_id,
        "side": action.side.value,
        "target_sl": action.target_sl,
        "preserve_tp": action.preserve_tp,
        "expected_broker_sl": action.expected_broker_sl,
        "source_phase": action.source_phase.value,
        "close_price": action.close_price,
        "tick_size": action.tick_size,
    }


def _restore_action(value: object) -> DesiredAction | None:
    if not isinstance(value, dict):
        return None
    return DesiredAction(
        kind=ActionKind(str(value["kind"])),
        reason=ActionReason(str(value["reason"])),
        position_id=int(value["position_id"]),
        side=PositionSide(str(value["side"])),
        target_sl=float(value["target_sl"]),
        preserve_tp=_optional_float(value.get("preserve_tp")),
        expected_broker_sl=_optional_float(value.get("expected_broker_sl")),
        source_phase=ManagementPhase(str(value["source_phase"])),
        close_price=float(value["close_price"]),
        tick_size=float(value["tick_size"]),
    )


def _optional_float(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _prices_close(left: float, right: float) -> bool:
    tolerance = max(abs(left), abs(right), 1.0) * 1e-7
    return abs(left - right) <= tolerance


def replace_runtime_phase(
    runtime: _RuntimePosition,
    phase: ManagementPhase,
) -> _RuntimePosition:
    """Create an event-only copy without mutating the removed runtime."""

    return _RuntimePosition(
        state=replace(runtime.state, phase=phase, pending_action=None),
        broker_symbol=runtime.broker_symbol,
        atr=runtime.atr,
        magic=runtime.magic,
        correlation_id=runtime.correlation_id,
        last_confirmed_at_utc=runtime.last_confirmed_at_utc,
    )
