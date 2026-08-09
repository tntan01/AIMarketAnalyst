from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from services.mt5_service import MT5Service
from services.order_management_models import OperationStatus, SnapshotStatus


def _position(
    *,
    ticket: int = 41,
    volume: float = 0.2,
    sl: float = 1.095,
    tp: float = 1.10567,
    magic: int = 260609,
    comment: str = "AMA Scanner",
) -> SimpleNamespace:
    return SimpleNamespace(
        ticket=ticket,
        identifier=ticket + 1000,
        symbol="EURUSDm",
        type=0,
        volume=volume,
        price_open=1.1,
        price_current=1.101,
        sl=sl,
        tp=tp,
        profit=12.5,
        swap=-0.2,
        commission=-0.1,
        magic=magic,
        comment=comment,
        time=1_700_000_000 + ticket,
    )


def _pending_order() -> SimpleNamespace:
    return SimpleNamespace(
        ticket=81,
        symbol="EURUSDm",
        type=4,
        volume_current=0.1,
        volume_initial=0.2,
        price_open=1.11,
        sl=1.09,
        tp=1.13,
        magic=260609,
        comment="AMA Pending",
        time_setup=1_700_000_100,
        time_expiration=1_700_086_500,
    )


class ContractMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2
    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TIME_GTC = 0
    ORDER_FILLING_FOK = 0
    ORDER_FILLING_IOC = 1
    ORDER_FILLING_RETURN = 2
    SYMBOL_FILLING_FOK = 1
    SYMBOL_FILLING_IOC = 2
    SYMBOL_TRADE_EXECUTION_MARKET = 2
    TRADE_RETCODE_PLACED = 10008
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_INVALID_STOPS = 10016

    def __init__(self) -> None:
        self.position_responses: list[object] = [()]
        self.order_responses: list[object] = [()]
        self.tick = SimpleNamespace(
            bid=1.101,
            ask=1.1012,
            time=1_700_000_500,
            time_msc=1_700_000_500_123,
        )
        self.send_result: object = SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            comment="done",
            order=501,
            deal=502,
        )
        self.sent_requests: list[dict[str, object]] = []
        self.error = (0, "")
        self.filling_mode = self.SYMBOL_FILLING_FOK | self.SYMBOL_FILLING_IOC
        self.account_login = 123456
        self.account_server = "Broker-Demo"
        self.account_company = "Broker Ltd"

    def account_info(self) -> SimpleNamespace:
        return SimpleNamespace(
            login=self.account_login,
            server=self.account_server,
            company=self.account_company,
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO,
            trade_allowed=True,
        )

    def positions_get(self, **_kwargs):
        if len(self.position_responses) > 1:
            return self.position_responses.pop(0)
        return self.position_responses[0]

    def orders_get(self, **_kwargs):
        if len(self.order_responses) > 1:
            return self.order_responses.pop(0)
        return self.order_responses[0]

    def symbol_info(self, _symbol: str) -> SimpleNamespace:
        return SimpleNamespace(
            digits=5,
            point=0.00001,
            trade_tick_size=0.0001,
            trade_stops_level=20,
            trade_freeze_level=10,
            filling_mode=self.filling_mode,
            trade_exemode=self.SYMBOL_TRADE_EXECUTION_MARKET,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
        )

    def symbol_info_tick(self, _symbol: str):
        return self.tick

    def order_send(self, request: dict[str, object]):
        self.sent_requests.append(dict(request))
        return self.send_result

    def last_error(self) -> tuple[int, str]:
        return self.error


@pytest.fixture
def service_factory(monkeypatch, tmp_path):
    def build(fake_mt5: ContractMT5) -> MT5Service:
        monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
        profile_path = tmp_path / "symbol_profiles.json"
        profile_path.write_text(
            '{"EUR/USD": {"mt5_aliases": ["EURUSDm"]}}',
            encoding="utf-8",
        )
        return MT5Service(profile_path)

    return build


def test_positions_snapshot_distinguishes_confirmed_empty_from_unavailable(
    service_factory,
) -> None:
    fake = ContractMT5()
    service = service_factory(fake)

    empty = service.positions_snapshot()

    assert empty.status is SnapshotStatus.AVAILABLE
    assert empty.available is True
    assert empty.positions == ()
    assert empty.account is not None
    assert empty.account.login == 123456
    assert empty.account.server == "Broker-Demo"
    assert empty.account.is_demo is True
    assert empty.account.is_live is False

    fake.position_responses = [None]
    fake.error = (-10004, "terminal disconnected")
    unavailable = service.positions_snapshot()

    assert unavailable.status is SnapshotStatus.UNAVAILABLE
    assert unavailable.available is False
    assert unavailable.positions == ()
    assert unavailable.account == empty.account
    assert unavailable.error_code == -10004
    assert "disconnected" in unavailable.message


def test_snapshots_include_account_magic_expiration_and_symbol_constraints(
    service_factory,
) -> None:
    fake = ContractMT5()
    fake.position_responses = [(_position(),)]
    fake.order_responses = [(_pending_order(),)]
    service = service_factory(fake)

    positions = service.positions_snapshot()
    pending = service.pending_orders_snapshot()

    position = positions.positions[0]
    order = pending.orders[0]
    assert position.broker_symbol == "EURUSDm"
    assert position.app_symbol == "EUR/USD"
    assert position.magic == 260609
    assert position.identifier == 1041
    assert position.symbol_metadata.digits == 5
    assert position.symbol_metadata.trade_tick_size == 0.0001
    assert position.symbol_metadata.trade_stops_level == 20
    assert order.order_type == "buy_stop"
    assert order.magic == 260609
    assert order.expiration_time == 1_700_086_500
    assert pending.account == positions.account


def test_pending_snapshot_distinguishes_confirmed_empty_from_unavailable(
    service_factory,
) -> None:
    fake = ContractMT5()
    service = service_factory(fake)

    empty = service.pending_orders_snapshot()
    assert empty.status is SnapshotStatus.AVAILABLE
    assert empty.orders == ()

    fake.order_responses = [None]
    fake.error = (4014, "terminal not ready")
    unavailable = service.pending_orders_snapshot()
    assert unavailable.status is SnapshotStatus.UNAVAILABLE
    assert unavailable.orders == ()
    assert unavailable.error_code == 4014


def test_symbol_tick_has_explicit_availability_and_correct_bid_ask(
    service_factory,
) -> None:
    fake = ContractMT5()
    service = service_factory(fake)

    snapshot = service.symbol_tick("EURUSDm")

    assert snapshot.available is True
    assert snapshot.tick is not None
    assert snapshot.tick.bid == 1.101
    assert snapshot.tick.ask == 1.1012
    assert snapshot.account is not None

    fake.tick = None
    fake.error = (500, "no tick")
    unavailable = service.symbol_tick("EURUSDm")
    assert unavailable.status is SnapshotStatus.UNAVAILABLE
    assert unavailable.tick is None
    assert unavailable.error_code == 500


def test_modify_sltp_preserves_tp_normalizes_sl_and_requires_postcondition(
    service_factory,
) -> None:
    fake = ContractMT5()
    before = _position(sl=1.095, tp=1.10567)
    after = _position(sl=1.1001, tp=1.10567)
    fake.position_responses = [(before,), (after,)]
    service = service_factory(fake)

    result = service.modify_position_sltp(41, sl=1.10006)

    request = fake.sent_requests[0]
    assert request["sl"] == 1.1001
    assert request["tp"] == 1.10567
    assert result["status"] == OperationStatus.CONFIRMED.value
    assert result["success"] is True
    assert result["effective_sl"] == 1.1001
    assert result["effective_tp"] == 1.10567
    assert result["retcode"] == fake.TRADE_RETCODE_DONE


def test_automatic_modify_aborts_when_broker_state_changed_after_snapshot(
    service_factory,
) -> None:
    fake = ContractMT5()
    # The engine saw SL=1.09500, but a user/EA tightened it before execution.
    current = _position(sl=1.1005, tp=1.10567)
    fake.position_responses = [(current,)]
    service = service_factory(fake)

    result = service.modify_position_sltp(
        41,
        sl=1.1001,
        tp=1.10567,
        expected_sl=1.095,
        expected_tp=1.10567,
        enforce_snapshot_precondition=True,
    )

    assert result["status"] == OperationStatus.REJECTED.value
    assert result["precondition_failed"] is True
    assert result["effective_sl"] == 1.1005
    assert fake.sent_requests == []


def test_queued_modify_aborts_after_account_switch(service_factory) -> None:
    fake = ContractMT5()
    current = _position()
    fake.position_responses = [(current,)]
    service = service_factory(fake)

    result = service.modify_position_sltp(
        41,
        sl=1.1001,
        expected_account_fingerprint="Broker Ltd|Broker-Demo|999999",
        expected_broker_symbol="EURUSDm",
    )

    assert result["status"] == OperationStatus.REJECTED.value
    assert result["precondition_failed"] is True
    assert "account changed" in str(result["message"]).lower()
    assert fake.sent_requests == []


def test_queued_close_aborts_after_symbol_scope_changes(service_factory) -> None:
    fake = ContractMT5()
    fake.position_responses = [(_position(),)]
    service = service_factory(fake)

    result = service.close_position(
        41,
        expected_account_fingerprint="Broker Ltd|Broker-Demo|123456",
        expected_broker_symbol="XAUUSDm",
    )

    assert result["status"] == OperationStatus.REJECTED.value
    assert result["precondition_failed"] is True
    assert "symbol changed" in str(result["message"]).lower()
    assert fake.sent_requests == []


def test_modify_sltp_rejection_does_not_report_success(service_factory) -> None:
    fake = ContractMT5()
    before = _position()
    fake.position_responses = [(before,), (before,)]
    fake.send_result = SimpleNamespace(
        retcode=fake.TRADE_RETCODE_INVALID_STOPS,
        comment="invalid stops",
        order=0,
        deal=0,
    )
    service = service_factory(fake)

    result = service.modify_position_sltp(41, sl=1.1001)

    assert result["status"] == OperationStatus.REJECTED.value
    assert result["success"] is False
    assert result["effective_sl"] == before.sl
    assert result["effective_tp"] == before.tp


def test_modify_sltp_accepted_without_observed_change_is_unknown(
    service_factory,
) -> None:
    fake = ContractMT5()
    before = _position()
    fake.position_responses = [(before,), (before,)]
    fake.send_result = SimpleNamespace(
        retcode=fake.TRADE_RETCODE_PLACED,
        comment="placed",
        order=501,
        deal=0,
    )
    service = service_factory(fake)

    result = service.modify_position_sltp(41, sl=1.1001)

    assert result["status"] == OperationStatus.UNKNOWN.value
    assert result["success"] is False


def test_close_uses_symbol_filling_bitmask_and_only_confirms_after_requery(
    service_factory,
) -> None:
    fake = ContractMT5()
    fake.position_responses = [(_position(),), ()]
    service = service_factory(fake)

    result = service.close_position(41)

    request = fake.sent_requests[0]
    assert request["type_filling"] == fake.ORDER_FILLING_IOC
    assert request["price"] == fake.tick.bid
    assert result["status"] == OperationStatus.CONFIRMED.value
    assert result["success"] is True
    assert result["remaining_volume"] == 0.0
    assert result["executed_volume"] == 0.2


def test_close_maps_fok_symbol_flag_to_fok_order_enum(service_factory) -> None:
    fake = ContractMT5()
    fake.filling_mode = fake.SYMBOL_FILLING_FOK
    fake.position_responses = [(_position(),), ()]
    service = service_factory(fake)

    result = service.close_position(41)

    assert result["status"] == OperationStatus.CONFIRMED.value
    assert fake.sent_requests[0]["type_filling"] == fake.ORDER_FILLING_FOK


def test_close_placed_but_still_open_is_unknown(service_factory) -> None:
    fake = ContractMT5()
    before = _position()
    fake.position_responses = [(before,), (before,)]
    fake.send_result = SimpleNamespace(
        retcode=fake.TRADE_RETCODE_PLACED,
        comment="placed",
        order=501,
        deal=0,
    )
    service = service_factory(fake)

    result = service.close_position(41)

    assert result["status"] == OperationStatus.UNKNOWN.value
    assert result["success"] is False
    assert result["remaining_volume"] == 0.2
    assert result["executed_volume"] == 0.0


def test_close_partial_reports_remaining_volume_and_keeps_success_false(
    service_factory,
) -> None:
    fake = ContractMT5()
    fake.position_responses = [
        (_position(volume=0.2),),
        (_position(volume=0.1),),
    ]
    fake.send_result = SimpleNamespace(
        retcode=fake.TRADE_RETCODE_DONE_PARTIAL,
        comment="partial",
        order=501,
        deal=502,
    )
    service = service_factory(fake)

    result = service.close_position(41)

    assert result["status"] == OperationStatus.PARTIAL.value
    assert result["success"] is False
    assert result["executed_volume"] == pytest.approx(0.1)
    assert result["remaining_volume"] == 0.1


def test_close_postcondition_query_failure_is_unknown(service_factory) -> None:
    fake = ContractMT5()
    fake.position_responses = [(_position(),), None]
    fake.error = (-10004, "connection lost")
    service = service_factory(fake)

    result = service.close_position(41)

    assert result["status"] == OperationStatus.UNKNOWN.value
    assert result["success"] is False
    assert result["remaining_volume"] is None
    assert result["error_code"] == -10004


def test_reconcile_position_prefers_position_ticket_then_correlation_fields(
    service_factory,
) -> None:
    fake = ContractMT5()
    older = _position(ticket=41, magic=260609, comment="AMA Scanner")
    exact = _position(ticket=42, magic=999, comment="manual")
    newer = _position(ticket=43, magic=260609, comment="AMA Scanner")
    fake.position_responses = [(older, exact, newer)]
    service = service_factory(fake)

    unrelated_ticket = service.reconcile_open_position(
        "EURUSDm",
        expected_ticket=42,
    )
    by_ticket = service.reconcile_open_position(
        "EURUSDm",
        expected_ticket=41,
    )
    correlated = service.reconcile_open_position("EURUSDm")

    assert unrelated_ticket is not None and unrelated_ticket.position_id == 43
    assert by_ticket is not None and by_ticket.position_id == 41
    assert correlated is not None and correlated.position_id == 43
