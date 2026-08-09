"""Pure state machine for break-even and trailing-stop management.

The module deliberately knows nothing about MetaTrader 5, Qt, persistence, or
threads.  It accepts immutable broker observations and returns a decision.  A
caller may execute the returned :class:`DesiredAction`, but the lifecycle state
does not advance until :func:`apply_confirmation` verifies the broker-side
postcondition.

The broker snapshot is authoritative for the current SL and TP.  In
particular, ``ManagedPositionState`` intentionally has no cached ``current_sl``
field; this prevents a restart or an out-of-band MT5 edit from moving a stop in
the less-protective direction.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from enum import Enum
from math import isfinite


class _StringEnum(str, Enum):
    def __str__(self) -> str:
        return self.value


class ManagementPhase(_StringEnum):
    UNMANAGED = "unmanaged"
    WAITING_BE = "waiting_be"
    BE_ACTIVE = "be_active"
    TRAIL_WIDE = "trail_wide"
    TRAIL_TIGHT = "trail_tight"
    PAUSED = "paused"
    STALE = "stale"
    ERROR_RETRYABLE = "error_retryable"
    ERROR_NON_RETRYABLE = "error_non_retryable"
    CLOSED = "closed"


class PositionSide(_StringEnum):
    BUY = "buy"
    SELL = "sell"


class ActionKind(_StringEnum):
    MODIFY_SL = "modify_sl"


class ActionReason(_StringEnum):
    BREAKEVEN = "breakeven"
    TRAIL_WIDE = "trail_wide"
    TRAIL_TIGHT = "trail_tight"


class ConfirmationStatus(_StringEnum):
    CONFIRMED = "confirmed"
    RETRYABLE_ERROR = "retryable_error"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SymbolConstraints:
    """Broker price-grid and stop-distance constraints.

    ``stops_level_points`` and ``freeze_level_points`` use the broker's point
    unit.  The state machine conservatively observes the larger distance when
    proposing a modification.
    """

    point: float
    tick_size: float
    digits: int
    stops_level_points: int = 0
    freeze_level_points: int = 0

    def __post_init__(self) -> None:
        if not _is_positive_number(self.point):
            raise ValueError("point must be a finite positive number")
        if not _is_positive_number(self.tick_size):
            raise ValueError("tick_size must be a finite positive number")
        if self.digits < 0:
            raise ValueError("digits must be non-negative")
        if self.stops_level_points < 0 or self.freeze_level_points < 0:
            raise ValueError("broker distance levels must be non-negative")

    @property
    def minimum_stop_distance(self) -> float:
        points = max(self.stops_level_points, self.freeze_level_points)
        return points * self.point


@dataclass(frozen=True, slots=True)
class ManagementSettings:
    constraints: SymbolConstraints
    atr: float | None
    be_trigger_r: float = 1.0
    be_offset: float = 0.0
    tight_trigger_r: float = 2.0
    wide_atr_multiplier: float = 2.5
    tight_atr_multiplier: float = 1.5
    minimum_update_ticks: int = 1
    max_retries: int = 3
    retry_base_delay_seconds: float = 1.0
    retry_max_delay_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not _is_positive_number(self.be_trigger_r):
            raise ValueError("be_trigger_r must be positive")
        if not _is_non_negative_number(self.be_offset):
            raise ValueError("be_offset must be non-negative")
        if not _is_positive_number(self.tight_trigger_r):
            raise ValueError("tight_trigger_r must be positive")
        if not _is_positive_number(self.wide_atr_multiplier):
            raise ValueError("wide_atr_multiplier must be positive")
        if not _is_positive_number(self.tight_atr_multiplier):
            raise ValueError("tight_atr_multiplier must be positive")
        if self.minimum_update_ticks < 0:
            raise ValueError("minimum_update_ticks must be non-negative")
        if self.max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if not _is_non_negative_number(self.retry_base_delay_seconds):
            raise ValueError("retry_base_delay_seconds must be non-negative")
        if not _is_non_negative_number(self.retry_max_delay_seconds):
            raise ValueError("retry_max_delay_seconds must be non-negative")
        if (
            self.retry_max_delay_seconds > 0
            and self.retry_max_delay_seconds < self.retry_base_delay_seconds
        ):
            raise ValueError("retry_max_delay_seconds cannot be below the base delay")
        if self.atr is not None and not _is_positive_number(self.atr):
            raise ValueError("atr must be None or a finite positive number")


@dataclass(frozen=True, slots=True)
class BrokerPositionSnapshot:
    position_id: int
    side: PositionSide
    entry_price: float
    broker_sl: float | None
    broker_tp: float | None
    fresh: bool = True
    exists: bool = True


@dataclass(frozen=True, slots=True)
class MarketTick:
    bid: float
    ask: float
    observed_at: float = 0.0
    fresh: bool = True

    def closing_price(self, side: PositionSide) -> float:
        """Return the executable close side: BUY->Bid and SELL->Ask."""

        return self.bid if side is PositionSide.BUY else self.ask


@dataclass(frozen=True, slots=True)
class DesiredAction:
    kind: ActionKind
    reason: ActionReason
    position_id: int
    side: PositionSide
    target_sl: float
    preserve_tp: float | None
    expected_broker_sl: float | None
    source_phase: ManagementPhase
    close_price: float
    tick_size: float


@dataclass(frozen=True, slots=True)
class ManagedPositionState:
    position_id: int
    side: PositionSide
    entry_price: float
    initial_sl: float
    phase: ManagementPhase = ManagementPhase.WAITING_BE
    extreme_price: float | None = None
    pending_action: DesiredAction | None = None
    resume_phase: ManagementPhase | None = None
    retry_count: int = 0
    retry_not_before: float = 0.0
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    state: ManagedPositionState
    action: DesiredAction | None = None
    reason: str = ""
    close_price: float | None = None
    profit_r: float | None = None


@dataclass(frozen=True, slots=True)
class ActionConfirmation:
    status: ConfirmationStatus
    effective_sl: float | None = None
    effective_tp: float | None = None
    observed_at: float = 0.0
    error_code: int | None = None
    message: str = ""
    position_exists: bool | None = True


def start_management(
    position_id: int,
    side: PositionSide | str,
    entry_price: float,
    initial_sl: float,
) -> ManagedPositionState:
    """Create a validated state which initially waits for break-even."""

    coerced_side = _coerce_side(side)
    if position_id <= 0:
        raise ValueError("position_id must be positive")
    if not _is_positive_number(entry_price) or not _is_positive_number(initial_sl):
        raise ValueError("entry_price and initial_sl must be finite positive numbers")
    if coerced_side is PositionSide.BUY and initial_sl >= entry_price:
        raise ValueError("a BUY initial SL must be below entry")
    if coerced_side is PositionSide.SELL and initial_sl <= entry_price:
        raise ValueError("a SELL initial SL must be above entry")
    return ManagedPositionState(
        position_id=position_id,
        side=coerced_side,
        entry_price=float(entry_price),
        initial_sl=float(initial_sl),
    )


def pause(state: ManagedPositionState) -> ManagedPositionState:
    """Pause management without losing its resumable lifecycle phase."""

    if state.phase in {ManagementPhase.CLOSED, ManagementPhase.UNMANAGED}:
        return state
    if state.pending_action is not None:
        raise ValueError("cannot pause while a broker action is awaiting confirmation")
    if state.phase is ManagementPhase.PAUSED:
        return state
    return replace(state, phase=ManagementPhase.PAUSED, resume_phase=state.phase)


def resume(state: ManagedPositionState) -> ManagedPositionState:
    """Resume an explicitly paused state."""

    if state.phase is not ManagementPhase.PAUSED:
        return state
    phase = state.resume_phase or ManagementPhase.WAITING_BE
    return replace(state, phase=phase, resume_phase=None, last_error=None)


def evaluate(
    state: ManagedPositionState,
    position: BrokerPositionSnapshot,
    tick: MarketTick,
    settings: ManagementSettings,
) -> Decision:
    """Evaluate one fresh observation and optionally propose one SL action.

    The returned action is an intent only.  ``Decision.state.phase`` never
    advances because that intent merely exists; the caller must execute it and
    pass the post-operation broker observation to :func:`apply_confirmation`.
    """

    if state.phase in {ManagementPhase.UNMANAGED, ManagementPhase.CLOSED}:
        return Decision(state=state, reason="inactive")

    # Availability is checked before any snapshot field is trusted.  A failed
    # query may contain placeholders, and those must never be mistaken for an
    # identity mismatch or a confirmed close.
    if not position.fresh or not tick.fresh:
        stale = _mark_stale(state, "broker_snapshot_unavailable")
        return Decision(state=stale, reason="broker_snapshot_unavailable")

    identity_error = _identity_error(state, position, settings.constraints)
    if identity_error:
        failed = replace(
            state,
            phase=ManagementPhase.ERROR_NON_RETRYABLE,
            pending_action=None,
            last_error=identity_error,
        )
        return Decision(state=failed, reason=identity_error)

    if not position.exists:
        closed = replace(
            state,
            phase=ManagementPhase.CLOSED,
            pending_action=None,
            resume_phase=None,
            last_error=None,
        )
        return Decision(state=closed, reason="position_confirmed_closed")

    if state.phase is ManagementPhase.PAUSED:
        return Decision(state=state, reason="paused")
    if state.phase is ManagementPhase.ERROR_NON_RETRYABLE:
        return Decision(state=state, reason="non_retryable_error")

    close_price = tick.closing_price(state.side)
    if not _is_positive_number(close_price):
        stale = _mark_stale(state, "invalid_market_tick")
        return Decision(state=stale, reason="invalid_market_tick")

    working = state

    # A fresh snapshot resolves STALE without guessing whether an earlier send
    # succeeded.  If the broker already reflects the pending target, reconcile
    # it as a confirmed postcondition; otherwise recompute from broker truth.
    if working.phase is ManagementPhase.STALE:
        if working.pending_action is not None and _action_is_reflected(
            working.pending_action, position, settings.constraints
        ):
            working = _apply_confirmed_action(
                working,
                working.pending_action,
                effective_sl=position.broker_sl,
            )
            return Decision(
                state=working,
                reason="pending_action_reconciled",
                close_price=close_price,
                profit_r=_profit_r(working, close_price),
            )
        resume_phase = (
            working.pending_action.source_phase
            if working.pending_action is not None
            else working.resume_phase
        ) or ManagementPhase.WAITING_BE
        working = replace(
            working,
            phase=resume_phase,
            pending_action=None,
            resume_phase=None,
            last_error=None,
        )

    # STALE may resume into one of these locally inactive phases.
    if working.phase is ManagementPhase.PAUSED:
        return Decision(
            state=working,
            reason="paused",
            close_price=close_price,
            profit_r=_profit_r(working, close_price),
        )
    if working.phase is ManagementPhase.ERROR_NON_RETRYABLE:
        return Decision(
            state=working,
            reason="non_retryable_error",
            close_price=close_price,
            profit_r=_profit_r(working, close_price),
        )

    if working.phase is ManagementPhase.ERROR_RETRYABLE:
        if working.retry_count > settings.max_retries:
            failed = replace(
                working,
                phase=ManagementPhase.ERROR_NON_RETRYABLE,
                last_error=working.last_error or "retry_limit_exhausted",
            )
            return Decision(state=failed, reason="retry_limit_exhausted")
        if tick.observed_at < working.retry_not_before:
            return Decision(
                state=working,
                reason="retry_backoff",
                close_price=close_price,
                profit_r=_profit_r(working, close_price),
            )
        working = replace(
            working,
            phase=working.resume_phase or ManagementPhase.WAITING_BE,
            resume_phase=None,
            last_error=None,
            retry_not_before=0.0,
        )

    if working.pending_action is not None:
        if _action_is_reflected(working.pending_action, position, settings.constraints):
            confirmed = _apply_confirmed_action(
                working,
                working.pending_action,
                effective_sl=position.broker_sl,
            )
            return Decision(
                state=confirmed,
                reason="pending_action_reconciled",
                close_price=close_price,
                profit_r=_profit_r(confirmed, close_price),
            )
        return Decision(
            state=working,
            reason="action_awaiting_confirmation",
            close_price=close_price,
            profit_r=_profit_r(working, close_price),
        )

    profit_r = _profit_r(working, close_price)

    # Broker state remains authoritative after BE was previously confirmed.
    # If an out-of-band edit removes/loosens that protection, re-enter the BE
    # gate and restore it before evaluating any trailing target.
    if working.phase in {
        ManagementPhase.BE_ACTIVE,
        ManagementPhase.TRAIL_WIDE,
        ManagementPhase.TRAIL_TIGHT,
    }:
        raw_be = (
            working.entry_price + settings.be_offset
            if working.side is PositionSide.BUY
            else working.entry_price - settings.be_offset
        )
        if not _is_at_least_as_protective(
            position.broker_sl,
            raw_be,
            working.side,
            _price_tolerance(settings.constraints),
        ):
            working = replace(
                working,
                phase=ManagementPhase.WAITING_BE,
                pending_action=None,
                resume_phase=None,
                last_error="broker_sl_below_breakeven",
            )

    if working.phase is ManagementPhase.WAITING_BE:
        return _evaluate_waiting_be(
            working, position, close_price, profit_r, settings
        )

    if working.phase is ManagementPhase.BE_ACTIVE:
        next_phase = (
            ManagementPhase.TRAIL_TIGHT
            if _r_threshold_reached(
                working, profit_r, settings.tight_trigger_r, settings.constraints
            )
            else ManagementPhase.TRAIL_WIDE
        )
        armed = replace(
            working,
            phase=next_phase,
            extreme_price=_new_extreme(
                working.side, working.extreme_price, close_price
            ),
            retry_count=0,
            retry_not_before=0.0,
            last_error=None,
        )
        return Decision(
            state=armed,
            reason="trailing_armed",
            close_price=close_price,
            profit_r=profit_r,
        )

    if working.phase in {ManagementPhase.TRAIL_WIDE, ManagementPhase.TRAIL_TIGHT}:
        return _evaluate_trailing(
            working, position, close_price, profit_r, settings
        )

    failed = replace(
        working,
        phase=ManagementPhase.ERROR_NON_RETRYABLE,
        last_error=f"unsupported_phase:{working.phase.value}",
    )
    return Decision(state=failed, reason="unsupported_phase")


def apply_confirmation(
    state: ManagedPositionState,
    confirmation: ActionConfirmation,
    settings: ManagementSettings,
) -> ManagedPositionState:
    """Apply an execution result without trusting the send retcode alone.

    ``CONFIRMED`` requires the effective broker SL to meet or exceed the
    requested protection and the effective TP to equal the pre-request TP.
    Retryable failures enter a bounded exponential backoff.  Unknown outcomes
    enter ``STALE`` so the next fresh broker snapshot can reconcile them.
    """

    action = state.pending_action
    if action is None:
        raise ValueError("no pending action to confirm")

    if confirmation.position_exists is False:
        return replace(
            state,
            phase=ManagementPhase.CLOSED,
            pending_action=None,
            resume_phase=None,
            retry_count=0,
            retry_not_before=0.0,
            last_error=None,
        )

    if confirmation.status is ConfirmationStatus.CONFIRMED:
        sl_ok = _is_at_least_as_protective(
            confirmation.effective_sl,
            action.target_sl,
            action.side,
            _price_tolerance(settings.constraints),
        )
        tp_ok = _same_optional_price(
            confirmation.effective_tp,
            action.preserve_tp,
            _price_tolerance(settings.constraints),
        )
        if sl_ok and tp_ok:
            return _apply_confirmed_action(
                state, action, effective_sl=confirmation.effective_sl
            )
        problem = "sl_postcondition_failed" if not sl_ok else "tp_postcondition_failed"
        return replace(
            state,
            phase=ManagementPhase.ERROR_NON_RETRYABLE,
            pending_action=None,
            resume_phase=action.source_phase,
            last_error=problem,
        )

    if confirmation.status is ConfirmationStatus.RETRYABLE_ERROR:
        retry_count = state.retry_count + 1
        message = confirmation.message or "broker_retryable_error"
        if retry_count > settings.max_retries:
            return replace(
                state,
                phase=ManagementPhase.ERROR_NON_RETRYABLE,
                pending_action=None,
                resume_phase=action.source_phase,
                retry_count=retry_count,
                last_error="retry_limit_exhausted:" + message,
            )
        delay = settings.retry_base_delay_seconds * (2 ** (retry_count - 1))
        if settings.retry_max_delay_seconds > 0:
            delay = min(delay, settings.retry_max_delay_seconds)
        return replace(
            state,
            phase=ManagementPhase.ERROR_RETRYABLE,
            pending_action=None,
            resume_phase=action.source_phase,
            retry_count=retry_count,
            retry_not_before=confirmation.observed_at + delay,
            last_error=message,
        )

    if confirmation.status is ConfirmationStatus.UNKNOWN:
        return replace(
            state,
            phase=ManagementPhase.STALE,
            resume_phase=action.source_phase,
            last_error=confirmation.message or "broker_outcome_unknown",
        )

    return replace(
        state,
        phase=ManagementPhase.ERROR_NON_RETRYABLE,
        pending_action=None,
        resume_phase=action.source_phase,
        last_error=confirmation.message or "broker_request_rejected",
    )


def normalize_stop_target(
    raw_target: float,
    side: PositionSide | str,
    close_price: float,
    constraints: SymbolConstraints,
) -> float:
    """Clamp and normalize a stop target conservatively for the broker grid.

    BUY stops are rounded down and SELL stops up.  This directional rounding
    ensures digit/tick normalization cannot accidentally violate the minimum
    stop/freeze distance.
    """

    coerced_side = _coerce_side(side)
    if not _is_positive_number(raw_target) or not _is_positive_number(close_price):
        raise ValueError("raw_target and close_price must be finite positive numbers")

    distance = constraints.minimum_stop_distance
    if coerced_side is PositionSide.BUY:
        clamped = min(raw_target, close_price - distance)
        rounding = ROUND_FLOOR
    else:
        clamped = max(raw_target, close_price + distance)
        rounding = ROUND_CEILING
    if clamped <= 0:
        raise ValueError("broker constraints produce a non-positive stop")

    tick = Decimal(str(constraints.tick_size))
    value = Decimal(str(clamped))
    units = (value / tick).to_integral_value(rounding=rounding)
    normalized = units * tick
    quantum = Decimal(1).scaleb(-constraints.digits)
    normalized = normalized.quantize(quantum, rounding=rounding)
    return float(normalized)


def _evaluate_waiting_be(
    state: ManagedPositionState,
    position: BrokerPositionSnapshot,
    close_price: float,
    profit_r: float,
    settings: ManagementSettings,
) -> Decision:
    tolerance = _price_tolerance(settings.constraints)
    raw_be = (
        state.entry_price + settings.be_offset
        if state.side is PositionSide.BUY
        else state.entry_price - settings.be_offset
    )

    # A fresh broker snapshot is itself valid confirmation.  This covers a
    # successful request whose response was lost and an out-of-band manual SL.
    if _is_at_least_as_protective(
        position.broker_sl, raw_be, state.side, tolerance
    ):
        confirmed = replace(
            state,
            phase=ManagementPhase.BE_ACTIVE,
            extreme_price=_new_extreme(state.side, state.extreme_price, close_price),
            retry_count=0,
            retry_not_before=0.0,
            last_error=None,
        )
        return Decision(
            state=confirmed,
            reason="breakeven_reconciled_from_broker",
            close_price=close_price,
            profit_r=profit_r,
        )

    # WAITING_BE is intentionally a hard gate: no trailing target is evaluated
    # until the broker has confirmed BE protection.
    if not _r_threshold_reached(
        state, profit_r, settings.be_trigger_r, settings.constraints
    ):
        return Decision(
            state=state,
            reason="waiting_for_breakeven_trigger",
            close_price=close_price,
            profit_r=profit_r,
        )

    try:
        target = normalize_stop_target(
            raw_be, state.side, close_price, settings.constraints
        )
    except ValueError:
        return Decision(
            state=state,
            reason="breakeven_blocked_by_constraints",
            close_price=close_price,
            profit_r=profit_r,
        )

    # A constrained target below BUY BE / above SELL BE is not break-even.  Do
    # not send it and, critically, do not advance the lifecycle state.
    if not _is_at_least_as_protective(target, raw_be, state.side, tolerance):
        return Decision(
            state=state,
            reason="breakeven_blocked_by_constraints",
            close_price=close_price,
            profit_r=profit_r,
        )
    if not _is_strictly_more_protective(
        target,
        position.broker_sl,
        state.side,
        settings.minimum_update_ticks * settings.constraints.tick_size,
        tolerance,
    ):
        return Decision(
            state=state,
            reason="broker_stop_already_more_protective",
            close_price=close_price,
            profit_r=profit_r,
        )

    action = DesiredAction(
        kind=ActionKind.MODIFY_SL,
        reason=ActionReason.BREAKEVEN,
        position_id=state.position_id,
        side=state.side,
        target_sl=target,
        preserve_tp=position.broker_tp,
        expected_broker_sl=position.broker_sl,
        source_phase=ManagementPhase.WAITING_BE,
        close_price=close_price,
        tick_size=settings.constraints.tick_size,
    )
    pending = replace(
        state,
        pending_action=action,
        extreme_price=_new_extreme(state.side, state.extreme_price, close_price),
    )
    return Decision(
        state=pending,
        action=action,
        reason="breakeven_action_required",
        close_price=close_price,
        profit_r=profit_r,
    )


def _evaluate_trailing(
    state: ManagedPositionState,
    position: BrokerPositionSnapshot,
    close_price: float,
    profit_r: float,
    settings: ManagementSettings,
) -> Decision:
    phase = state.phase
    if phase is ManagementPhase.TRAIL_WIDE and _r_threshold_reached(
        state, profit_r, settings.tight_trigger_r, settings.constraints
    ):
        phase = ManagementPhase.TRAIL_TIGHT

    extreme = _new_extreme(state.side, state.extreme_price, close_price)
    working = replace(state, phase=phase, extreme_price=extreme)
    if settings.atr is None:
        return Decision(
            state=working,
            reason="atr_unavailable",
            close_price=close_price,
            profit_r=profit_r,
        )

    multiplier = (
        settings.tight_atr_multiplier
        if phase is ManagementPhase.TRAIL_TIGHT
        else settings.wide_atr_multiplier
    )
    distance = settings.atr * multiplier
    raw_target = (
        extreme - distance
        if state.side is PositionSide.BUY
        else extreme + distance
    )
    try:
        target = normalize_stop_target(
            raw_target, state.side, close_price, settings.constraints
        )
    except ValueError:
        return Decision(
            state=working,
            reason="trailing_target_invalid",
            close_price=close_price,
            profit_r=profit_r,
        )

    if not _is_strictly_more_protective(
        target,
        position.broker_sl,
        state.side,
        settings.minimum_update_ticks * settings.constraints.tick_size,
        _price_tolerance(settings.constraints),
    ):
        return Decision(
            state=working,
            reason="no_tighter_stop_available",
            close_price=close_price,
            profit_r=profit_r,
        )

    reason = (
        ActionReason.TRAIL_TIGHT
        if phase is ManagementPhase.TRAIL_TIGHT
        else ActionReason.TRAIL_WIDE
    )
    action = DesiredAction(
        kind=ActionKind.MODIFY_SL,
        reason=reason,
        position_id=state.position_id,
        side=state.side,
        target_sl=target,
        preserve_tp=position.broker_tp,
        expected_broker_sl=position.broker_sl,
        source_phase=phase,
        close_price=close_price,
        tick_size=settings.constraints.tick_size,
    )
    pending = replace(working, pending_action=action)
    return Decision(
        state=pending,
        action=action,
        reason="trailing_action_required",
        close_price=close_price,
        profit_r=profit_r,
    )


def _apply_confirmed_action(
    state: ManagedPositionState,
    action: DesiredAction,
    *,
    effective_sl: float | None,
) -> ManagedPositionState:
    del effective_sl  # Broker SL is consumed for validation, never cached here.
    phase = (
        ManagementPhase.BE_ACTIVE
        if action.reason is ActionReason.BREAKEVEN
        else action.source_phase
    )
    return replace(
        state,
        phase=phase,
        pending_action=None,
        resume_phase=None,
        retry_count=0,
        retry_not_before=0.0,
        last_error=None,
    )


def _action_is_reflected(
    action: DesiredAction,
    position: BrokerPositionSnapshot,
    constraints: SymbolConstraints,
) -> bool:
    tolerance = _price_tolerance(constraints)
    return _is_at_least_as_protective(
        position.broker_sl, action.target_sl, action.side, tolerance
    ) and _same_optional_price(position.broker_tp, action.preserve_tp, tolerance)


def _mark_stale(state: ManagedPositionState, message: str) -> ManagedPositionState:
    if state.phase is ManagementPhase.STALE:
        return replace(state, last_error=message)
    return replace(
        state,
        phase=ManagementPhase.STALE,
        resume_phase=state.phase,
        last_error=message,
    )


def _identity_error(
    state: ManagedPositionState,
    position: BrokerPositionSnapshot,
    constraints: SymbolConstraints,
) -> str | None:
    if position.position_id != state.position_id:
        return "position_id_mismatch"
    try:
        side = _coerce_side(position.side)
    except ValueError:
        return "position_side_invalid"
    if side is not state.side:
        return "position_side_mismatch"
    if position.exists and position.fresh:
        if not _is_positive_number(position.entry_price):
            return "position_entry_invalid"
        if abs(position.entry_price - state.entry_price) > _price_tolerance(constraints):
            return "position_entry_mismatch"
    return None


def _profit_r(state: ManagedPositionState, close_price: float) -> float:
    risk = abs(state.entry_price - state.initial_sl)
    profit = (
        close_price - state.entry_price
        if state.side is PositionSide.BUY
        else state.entry_price - close_price
    )
    return profit / risk


def _r_threshold_reached(
    state: ManagedPositionState,
    profit_r: float,
    threshold_r: float,
    constraints: SymbolConstraints,
) -> bool:
    """Compare R thresholds without losing exact boundaries to float noise."""

    risk = abs(state.entry_price - state.initial_sl)
    tolerance_r = _price_tolerance(constraints) / risk
    return profit_r >= threshold_r - tolerance_r


def _new_extreme(
    side: PositionSide,
    previous: float | None,
    close_price: float,
) -> float:
    if previous is None or not _is_positive_number(previous):
        return close_price
    if side is PositionSide.BUY:
        return max(previous, close_price)
    return min(previous, close_price)


def _is_strictly_more_protective(
    candidate: float,
    broker_sl: float | None,
    side: PositionSide,
    minimum_improvement: float,
    tolerance: float,
) -> bool:
    if not _is_positive_number(broker_sl):
        return True
    current = float(broker_sl)
    required = max(0.0, minimum_improvement)
    if side is PositionSide.BUY:
        return candidate - current >= required - tolerance and candidate > current + tolerance
    return current - candidate >= required - tolerance and candidate < current - tolerance


def _is_at_least_as_protective(
    actual: float | None,
    target: float,
    side: PositionSide,
    tolerance: float,
) -> bool:
    if not _is_positive_number(actual):
        return False
    if side is PositionSide.BUY:
        return float(actual) >= target - tolerance
    return float(actual) <= target + tolerance


def _same_optional_price(
    actual: float | None,
    expected: float | None,
    tolerance: float,
) -> bool:
    actual_missing = not _is_positive_number(actual)
    expected_missing = not _is_positive_number(expected)
    if actual_missing or expected_missing:
        return actual_missing and expected_missing
    return abs(float(actual) - float(expected)) <= tolerance


def _price_tolerance(constraints: SymbolConstraints) -> float:
    digit_quantum = 10.0 ** (-constraints.digits)
    return min(constraints.tick_size, digit_quantum) * 1e-6 + 1e-12


def _coerce_side(side: PositionSide | str) -> PositionSide:
    if isinstance(side, PositionSide):
        return side
    try:
        return PositionSide(str(side).strip().lower())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"unsupported position side: {side!r}") from exc


def _is_positive_number(value: object) -> bool:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return isfinite(number) and number > 0.0


def _is_non_negative_number(value: object) -> bool:
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return False
    return isfinite(number) and number >= 0.0


__all__ = [
    "ActionConfirmation",
    "ActionKind",
    "ActionReason",
    "BrokerPositionSnapshot",
    "ConfirmationStatus",
    "Decision",
    "DesiredAction",
    "ManagedPositionState",
    "ManagementPhase",
    "ManagementSettings",
    "MarketTick",
    "PositionSide",
    "SymbolConstraints",
    "apply_confirmation",
    "evaluate",
    "normalize_stop_target",
    "pause",
    "resume",
    "start_management",
]
