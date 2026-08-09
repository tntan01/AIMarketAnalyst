from __future__ import annotations

from dataclasses import replace

import pytest

from core.order_management_state_machine import (
    ActionConfirmation,
    ActionReason,
    BrokerPositionSnapshot,
    ConfirmationStatus,
    ManagementPhase,
    ManagementSettings,
    MarketTick,
    PositionSide,
    SymbolConstraints,
    apply_confirmation,
    evaluate,
    normalize_stop_target,
    pause,
    resume,
    start_management,
)


FX_CONSTRAINTS = SymbolConstraints(
    point=0.00001,
    tick_size=0.00001,
    digits=5,
)


def _settings(**changes: object) -> ManagementSettings:
    values: dict[str, object] = {
        "constraints": FX_CONSTRAINTS,
        "atr": 0.00020,
    }
    values.update(changes)
    return ManagementSettings(**values)  # type: ignore[arg-type]


def _buy_state():
    return start_management(101, PositionSide.BUY, 1.10000, 1.09900)


def _sell_state():
    return start_management(202, PositionSide.SELL, 1.10000, 1.10100)


def _buy_position(**changes: object) -> BrokerPositionSnapshot:
    values: dict[str, object] = {
        "position_id": 101,
        "side": PositionSide.BUY,
        "entry_price": 1.10000,
        "broker_sl": 1.09900,
        "broker_tp": 1.10500,
    }
    values.update(changes)
    return BrokerPositionSnapshot(**values)  # type: ignore[arg-type]


def _sell_position(**changes: object) -> BrokerPositionSnapshot:
    values: dict[str, object] = {
        "position_id": 202,
        "side": PositionSide.SELL,
        "entry_price": 1.10000,
        "broker_sl": 1.10100,
        "broker_tp": 1.09500,
    }
    values.update(changes)
    return BrokerPositionSnapshot(**values)  # type: ignore[arg-type]


def _confirmed(decision, settings: ManagementSettings):
    assert decision.action is not None
    return apply_confirmation(
        decision.state,
        ActionConfirmation(
            status=ConfirmationStatus.CONFIRMED,
            effective_sl=decision.action.target_sl,
            effective_tp=decision.action.preserve_tp,
        ),
        settings,
    )


def test_waiting_be_never_trails_below_trigger() -> None:
    state = replace(_buy_state(), extreme_price=1.20000)

    decision = evaluate(
        state,
        _buy_position(),
        MarketTick(bid=1.10090, ask=1.10120),
        _settings(atr=0.00001),
    )

    assert decision.action is None
    assert decision.state.phase is ManagementPhase.WAITING_BE
    assert decision.reason == "waiting_for_breakeven_trigger"


@pytest.mark.parametrize(
    ("state", "position", "tick"),
    [
        # ASK crossed 1R, but a BUY can close only at Bid and must not trigger.
        (_buy_state(), _buy_position(), MarketTick(bid=1.10099, ask=1.10120)),
        # Bid crossed 1R, but a SELL can close only at Ask and must not trigger.
        (_sell_state(), _sell_position(), MarketTick(bid=1.09880, ask=1.09901)),
    ],
)
def test_be_trigger_uses_executable_close_side(state, position, tick) -> None:
    decision = evaluate(state, position, tick, _settings())

    assert decision.action is None
    assert decision.state.phase is ManagementPhase.WAITING_BE


@pytest.mark.parametrize(
    ("state", "position", "tick", "expected_close"),
    [
        (_buy_state(), _buy_position(), MarketTick(1.10100, 1.10120), 1.10100),
        (_sell_state(), _sell_position(), MarketTick(1.09880, 1.09900), 1.09900),
    ],
)
def test_be_intent_does_not_advance_state_before_confirmation(
    state, position, tick, expected_close
) -> None:
    decision = evaluate(state, position, tick, _settings())

    assert decision.action is not None
    assert decision.action.reason is ActionReason.BREAKEVEN
    assert decision.action.close_price == pytest.approx(expected_close)
    assert decision.action.preserve_tp == position.broker_tp
    assert decision.state.phase is ManagementPhase.WAITING_BE
    assert decision.state.pending_action == decision.action


def test_duplicate_evaluation_does_not_emit_pending_action_again() -> None:
    first = evaluate(
        _buy_state(),
        _buy_position(),
        MarketTick(1.10100, 1.10120),
        _settings(),
    )

    second = evaluate(
        first.state,
        _buy_position(),
        MarketTick(1.10300, 1.10320),
        _settings(),
    )

    assert second.action is None
    assert second.reason == "action_awaiting_confirmation"
    assert second.state.phase is ManagementPhase.WAITING_BE


def test_confirmed_be_transitions_only_when_sl_and_tp_postconditions_hold() -> None:
    settings = _settings()
    decision = evaluate(
        _buy_state(),
        _buy_position(),
        MarketTick(1.10100, 1.10120),
        settings,
    )

    confirmed = _confirmed(decision, settings)

    assert confirmed.phase is ManagementPhase.BE_ACTIVE
    assert confirmed.pending_action is None
    assert confirmed.retry_count == 0


def test_tp_change_makes_confirmation_non_retryable_error() -> None:
    settings = _settings()
    decision = evaluate(
        _buy_state(),
        _buy_position(),
        MarketTick(1.10100, 1.10120),
        settings,
    )
    assert decision.action is not None

    failed = apply_confirmation(
        decision.state,
        ActionConfirmation(
            status=ConfirmationStatus.CONFIRMED,
            effective_sl=decision.action.target_sl,
            effective_tp=1.10400,
        ),
        settings,
    )

    assert failed.phase is ManagementPhase.ERROR_NON_RETRYABLE
    assert failed.last_error == "tp_postcondition_failed"


def test_broker_sl_is_authoritative_and_can_reconcile_be() -> None:
    decision = evaluate(
        _buy_state(),
        _buy_position(broker_sl=1.10020),
        MarketTick(1.10040, 1.10060),
        _settings(),
    )

    assert decision.action is None
    assert decision.state.phase is ManagementPhase.BE_ACTIVE
    assert decision.reason == "breakeven_reconciled_from_broker"


@pytest.mark.parametrize(
    ("state", "position", "tick"),
    [
        (
            replace(_buy_state(), phase=ManagementPhase.TRAIL_WIDE),
            _buy_position(broker_sl=1.09950),
            MarketTick(1.10150, 1.10170),
        ),
        (
            replace(_sell_state(), phase=ManagementPhase.TRAIL_TIGHT),
            _sell_position(broker_sl=1.10050),
            MarketTick(1.09830, 1.09850),
        ),
    ],
)
def test_out_of_band_sl_loosen_reenters_be_gate_before_trailing(
    state, position, tick
) -> None:
    decision = evaluate(state, position, tick, _settings())

    assert decision.state.phase is ManagementPhase.WAITING_BE
    assert decision.action is not None
    assert decision.action.reason is ActionReason.BREAKEVEN
    assert decision.state.last_error == "broker_sl_below_breakeven"


def test_be_active_arms_wide_without_modifying_sl_on_same_evaluation() -> None:
    state = replace(_buy_state(), phase=ManagementPhase.BE_ACTIVE)

    decision = evaluate(
        state,
        _buy_position(broker_sl=1.10000),
        MarketTick(1.10150, 1.10170),
        _settings(),
    )

    assert decision.state.phase is ManagementPhase.TRAIL_WIDE
    assert decision.action is None
    assert decision.reason == "trailing_armed"


@pytest.mark.parametrize(
    ("close_price", "expected_phase"),
    [
        (1.10199, ManagementPhase.TRAIL_WIDE),
        (1.10200, ManagementPhase.TRAIL_TIGHT),
    ],
)
def test_wide_switches_to_tight_only_at_two_r(
    close_price: float, expected_phase: ManagementPhase
) -> None:
    state = replace(
        _buy_state(),
        phase=ManagementPhase.TRAIL_WIDE,
        extreme_price=1.10150,
    )

    decision = evaluate(
        state,
        _buy_position(broker_sl=1.10000),
        MarketTick(close_price, close_price + 0.00020),
        _settings(),
    )

    assert decision.state.phase is expected_phase


def test_tight_mode_never_downgrades_when_profit_retraces() -> None:
    state = replace(
        _buy_state(),
        phase=ManagementPhase.TRAIL_TIGHT,
        extreme_price=1.10300,
    )

    decision = evaluate(
        state,
        _buy_position(broker_sl=1.10250),
        MarketTick(1.10100, 1.10120),
        _settings(),
    )

    assert decision.state.phase is ManagementPhase.TRAIL_TIGHT


@pytest.mark.parametrize(
    ("state", "position", "tick", "expected_reason"),
    [
        (
            replace(
                _buy_state(),
                phase=ManagementPhase.TRAIL_WIDE,
                extreme_price=1.10150,
            ),
            _buy_position(broker_sl=1.10050),
            MarketTick(1.10150, 1.10170),
            ActionReason.TRAIL_WIDE,
        ),
        (
            replace(
                _sell_state(),
                phase=ManagementPhase.TRAIL_WIDE,
                extreme_price=1.09850,
            ),
            _sell_position(broker_sl=1.09950),
            MarketTick(1.09830, 1.09850),
            ActionReason.TRAIL_WIDE,
        ),
    ],
)
def test_trailing_produces_directionally_protective_intent(
    state, position, tick, expected_reason
) -> None:
    decision = evaluate(state, position, tick, _settings())

    assert decision.action is not None
    assert decision.action.reason is expected_reason
    if state.side is PositionSide.BUY:
        assert decision.action.target_sl > position.broker_sl
    else:
        assert decision.action.target_sl < position.broker_sl


@pytest.mark.parametrize(
    ("side", "broker_sl"),
    [(PositionSide.BUY, 1.10120), (PositionSide.SELL, 1.09880)],
)
def test_trailing_never_loosens_authoritative_broker_sl(
    side: PositionSide, broker_sl: float
) -> None:
    if side is PositionSide.BUY:
        state = replace(
            _buy_state(), phase=ManagementPhase.TRAIL_WIDE, extreme_price=1.10150
        )
        position = _buy_position(broker_sl=broker_sl)
        tick = MarketTick(1.10150, 1.10170)
    else:
        state = replace(
            _sell_state(), phase=ManagementPhase.TRAIL_WIDE, extreme_price=1.09850
        )
        position = _sell_position(broker_sl=broker_sl)
        tick = MarketTick(1.09830, 1.09850)

    decision = evaluate(state, position, tick, _settings())

    assert decision.action is None
    assert decision.reason == "no_tighter_stop_available"


def test_target_is_clamped_for_stop_and_freeze_distance_then_rounded_to_tick() -> None:
    constraints = SymbolConstraints(
        point=0.01,
        tick_size=0.05,
        digits=2,
        stops_level_points=7,
        freeze_level_points=9,
    )

    buy_target = normalize_stop_target(100.28, "buy", 100.31, constraints)
    sell_target = normalize_stop_target(100.02, "sell", 99.99, constraints)

    # BUY max is 100.22 -> floor to 100.20; SELL min is 100.08 -> ceil to 100.10.
    assert buy_target == pytest.approx(100.20)
    assert sell_target == pytest.approx(100.10)


def test_be_does_not_advance_when_constraints_cannot_reach_be_target() -> None:
    state = start_management(1, "buy", 100.0, 99.0)
    constraints = SymbolConstraints(
        point=0.01,
        tick_size=0.01,
        digits=2,
        stops_level_points=20,
    )
    settings = ManagementSettings(
        constraints=constraints,
        atr=0.5,
        be_offset=0.9,
    )
    position = BrokerPositionSnapshot(1, PositionSide.BUY, 100.0, 99.0, 110.0)

    decision = evaluate(state, position, MarketTick(101.0, 101.1), settings)

    assert decision.action is None
    assert decision.state.phase is ManagementPhase.WAITING_BE
    assert decision.reason == "breakeven_blocked_by_constraints"


def test_retryable_error_waits_for_exponential_backoff() -> None:
    settings = _settings(retry_base_delay_seconds=2.0, max_retries=2)
    initial = evaluate(
        _buy_state(),
        _buy_position(),
        MarketTick(1.10100, 1.10120, observed_at=10.0),
        settings,
    )

    retrying = apply_confirmation(
        initial.state,
        ActionConfirmation(
            ConfirmationStatus.RETRYABLE_ERROR,
            observed_at=10.0,
            message="broker_busy",
        ),
        settings,
    )
    too_early = evaluate(
        retrying,
        _buy_position(),
        MarketTick(1.10100, 1.10120, observed_at=11.99),
        settings,
    )
    ready = evaluate(
        retrying,
        _buy_position(),
        MarketTick(1.10100, 1.10120, observed_at=12.0),
        settings,
    )

    assert retrying.phase is ManagementPhase.ERROR_RETRYABLE
    assert retrying.retry_not_before == pytest.approx(12.0)
    assert too_early.action is None
    assert too_early.reason == "retry_backoff"
    assert ready.action is not None
    assert ready.state.phase is ManagementPhase.WAITING_BE


def test_retry_limit_becomes_non_retryable() -> None:
    settings = _settings(max_retries=0)
    decision = evaluate(
        _buy_state(),
        _buy_position(),
        MarketTick(1.10100, 1.10120),
        settings,
    )

    failed = apply_confirmation(
        decision.state,
        ActionConfirmation(
            ConfirmationStatus.RETRYABLE_ERROR,
            message="requote",
        ),
        settings,
    )

    assert failed.phase is ManagementPhase.ERROR_NON_RETRYABLE
    assert failed.last_error == "retry_limit_exhausted:requote"


def test_unknown_outcome_reconciles_from_next_fresh_broker_snapshot() -> None:
    settings = _settings()
    decision = evaluate(
        _buy_state(),
        _buy_position(),
        MarketTick(1.10100, 1.10120),
        settings,
    )
    assert decision.action is not None
    unknown = apply_confirmation(
        decision.state,
        ActionConfirmation(ConfirmationStatus.UNKNOWN, message="timeout"),
        settings,
    )

    reconciled = evaluate(
        unknown,
        _buy_position(broker_sl=decision.action.target_sl),
        MarketTick(1.10110, 1.10130),
        settings,
    )

    assert unknown.phase is ManagementPhase.STALE
    assert reconciled.state.phase is ManagementPhase.BE_ACTIVE
    assert reconciled.action is None
    assert reconciled.reason == "pending_action_reconciled"


def test_unavailable_snapshot_never_means_closed() -> None:
    stale = evaluate(
        _buy_state(),
        _buy_position(fresh=False, exists=False),
        MarketTick(0.0, 0.0, fresh=False),
        _settings(),
    )

    assert stale.state.phase is ManagementPhase.STALE

    closed = evaluate(
        stale.state,
        _buy_position(exists=False, fresh=True),
        MarketTick(1.10000, 1.10020),
        _settings(),
    )
    assert closed.state.phase is ManagementPhase.CLOSED


def test_pause_and_resume_preserve_lifecycle_phase() -> None:
    state = replace(_buy_state(), phase=ManagementPhase.TRAIL_TIGHT)

    paused = pause(state)
    decision = evaluate(
        paused,
        _buy_position(),
        MarketTick(1.10300, 1.10320),
        _settings(),
    )
    resumed = resume(paused)

    assert paused.phase is ManagementPhase.PAUSED
    assert decision.action is None
    assert resumed.phase is ManagementPhase.TRAIL_TIGHT


def test_invalid_position_identity_fails_closed_without_action() -> None:
    decision = evaluate(
        _buy_state(),
        _buy_position(position_id=999),
        MarketTick(1.10300, 1.10320),
        _settings(),
    )

    assert decision.action is None
    assert decision.state.phase is ManagementPhase.ERROR_NON_RETRYABLE
    assert decision.state.last_error == "position_id_mismatch"
