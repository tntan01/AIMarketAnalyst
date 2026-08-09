from __future__ import annotations

import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from services.mt5_service import MT5Service
from services.order_management_models import OperationStatus


def _pending_order(
    *,
    ticket: int = 81,
    order_type: int = 2,
    price: float = 1.098,
    sl: float = 1.096,
    tp: float = 1.102,
    stoplimit: float = 0.0,
    expiration: int = 0,
    type_time: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        ticket=ticket,
        symbol="EURUSDm",
        type=order_type,
        volume_current=0.1,
        volume_initial=0.1,
        price_open=price,
        price_stoplimit=stoplimit,
        sl=sl,
        tp=tp,
        magic=260609,
        comment="AMA Pending",
        time_setup=1_700_000_100 + ticket,
        time_expiration=expiration,
        type_time=type_time,
    )


def _position(
    *,
    ticket: int = 41,
    side: int = 0,
    volume: float = 0.2,
    sl: float = 1.096,
    tp: float = 1.104,
    opened_at: int = 1_700_000_000,
    magic: int = 260609,
    comment: str = "AMA Scanner correlation-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        ticket=ticket,
        identifier=ticket + 1_000,
        symbol="EURUSDm",
        type=side,
        volume=volume,
        price_open=1.099,
        price_current=1.1,
        sl=sl,
        tp=tp,
        profit=1.0,
        swap=0.0,
        commission=0.0,
        magic=magic,
        comment=comment,
        time=opened_at,
    )


class PendingContractMT5:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_CONTEST = 1
    ACCOUNT_TRADE_MODE_REAL = 2

    TRADE_ACTION_DEAL = 1
    TRADE_ACTION_SLTP = 6
    TRADE_ACTION_MODIFY = 7
    TRADE_ACTION_REMOVE = 8

    POSITION_TYPE_BUY = 0
    POSITION_TYPE_SELL = 1
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    ORDER_TYPE_BUY_STOP = 4
    ORDER_TYPE_SELL_STOP = 5
    ORDER_TYPE_BUY_STOP_LIMIT = 6
    ORDER_TYPE_SELL_STOP_LIMIT = 7

    ORDER_TIME_GTC = 0
    ORDER_TIME_DAY = 1
    ORDER_TIME_SPECIFIED = 2
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
    TRADE_RETCODE_ORDER_CHANGED = 10023

    def __init__(self) -> None:
        self.order_responses: list[object] = [()]
        self.position_responses: list[object] = [()]
        self.sent_requests: list[dict[str, object]] = []
        self.send_result: object | None = SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            comment="done",
            order=81,
            deal=0,
        )
        self.tick: object | None = SimpleNamespace(
            bid=1.1,
            ask=1.1002,
            time=1_700_000_500,
            time_msc=1_700_000_500_000,
        )
        self.error = (0, "")
        self.stops_level = 20
        self.freeze_level = 10
        self.symbol_metadata_available = True

    def account_info(self) -> SimpleNamespace:
        return SimpleNamespace(
            login=123456,
            server="Broker-Demo",
            company="Broker Ltd",
            trade_mode=self.ACCOUNT_TRADE_MODE_DEMO,
            trade_allowed=True,
        )

    def orders_get(self, **_kwargs):
        if len(self.order_responses) > 1:
            return self.order_responses.pop(0)
        return self.order_responses[0]

    def positions_get(self, **_kwargs):
        if len(self.position_responses) > 1:
            return self.position_responses.pop(0)
        return self.position_responses[0]

    def symbol_info(self, _symbol: str) -> SimpleNamespace | None:
        if not self.symbol_metadata_available:
            return None
        return SimpleNamespace(
            digits=5,
            point=0.00001,
            trade_tick_size=0.0001,
            trade_stops_level=self.stops_level,
            trade_freeze_level=self.freeze_level,
            filling_mode=self.SYMBOL_FILLING_FOK | self.SYMBOL_FILLING_IOC,
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
    def build(fake_mt5: PendingContractMT5) -> MT5Service:
        monkeypatch.setitem(sys.modules, "MetaTrader5", fake_mt5)
        profile_path = tmp_path / "symbol_profiles.json"
        profile_path.write_text(
            '{"EUR/USD": {"mt5_aliases": ["EURUSDm"]}}',
            encoding="utf-8",
        )
        return MT5Service(profile_path)

    return build


def test_pending_snapshot_maps_all_supported_types_and_preserves_contract_fields(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [
        tuple(
            _pending_order(
                ticket=80 + raw_type,
                order_type=raw_type,
                stoplimit=1.1015 if raw_type in {6, 7} else 0,
                expiration=1_800_000_000,
                type_time=fake.ORDER_TIME_SPECIFIED,
            )
            for raw_type in range(2, 8)
        )
    ]
    service = service_factory(fake)

    snapshot = service.pending_orders_snapshot()

    assert [order.order_type for order in snapshot.orders] == [
        "buy_limit",
        "sell_limit",
        "buy_stop",
        "sell_stop",
        "buy_stop_limit",
        "sell_stop_limit",
    ]
    assert snapshot.orders[-1].raw_order_type == fake.ORDER_TYPE_SELL_STOP_LIMIT
    assert snapshot.orders[-1].stoplimit_price == 1.1015
    assert snapshot.orders[-1].type_time == fake.ORDER_TIME_SPECIFIED
    legacy = snapshot.orders[-1].to_legacy_dict()
    assert legacy["price_stoplimit"] == 1.1015
    assert legacy["expiration"] == 1_800_000_000


def test_cancel_pending_order_confirms_only_after_order_disappears(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    before = _pending_order()
    fake.order_responses = [(before,), ()]
    service = service_factory(fake)

    result = service.cancel_pending_order(before.ticket)

    assert result["status"] == OperationStatus.CONFIRMED.value
    assert result["success"] is True
    assert result["pending_order_id"] == before.ticket
    assert fake.sent_requests == [
        {
            "action": fake.TRADE_ACTION_REMOVE,
            "order": before.ticket,
            "symbol": before.symbol,
        }
    ]
    assert "type_filling" not in fake.sent_requests[0]


def test_cancel_pending_order_aborts_on_account_precondition_mismatch(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [(_pending_order(),)]
    service = service_factory(fake)

    result = service.cancel_pending_order(
        81,
        expected_account_fingerprint="Broker Ltd|Broker-Demo|999999",
        expected_broker_symbol="EURUSDm",
    )

    assert result["status"] == OperationStatus.REJECTED.value
    assert result["precondition_failed"] is True
    assert fake.sent_requests == []


@pytest.mark.parametrize(
    ("retcode", "expected_status"),
    [
        (PendingContractMT5.TRADE_RETCODE_DONE, OperationStatus.UNKNOWN),
        (PendingContractMT5.TRADE_RETCODE_INVALID_STOPS, OperationStatus.REJECTED),
        (None, OperationStatus.UNKNOWN),
    ],
)
def test_cancel_pending_order_does_not_trust_retcode_when_order_remains(
    service_factory,
    retcode: int | None,
    expected_status: OperationStatus,
) -> None:
    fake = PendingContractMT5()
    before = _pending_order()
    fake.order_responses = [(before,), (before,)]
    fake.send_result = (
        None
        if retcode is None
        else SimpleNamespace(retcode=retcode, comment="broker response", order=81)
    )
    service = service_factory(fake)

    result = service.cancel_pending_order(before.ticket)

    assert result["status"] == expected_status.value
    assert result["success"] is False


def test_cancel_pending_order_postcondition_query_failure_is_unknown(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [(_pending_order(),), None]
    fake.error = (-10004, "connection lost")
    service = service_factory(fake)

    result = service.cancel_pending_order(81)

    assert result["status"] == OperationStatus.UNKNOWN.value
    assert result["error_code"] == -10004


def test_cancel_disappearance_without_broker_ack_is_unknown(service_factory) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [(_pending_order(),), ()]
    fake.send_result = SimpleNamespace(
        retcode=fake.TRADE_RETCODE_INVALID_STOPS,
        comment="rejected",
        order=81,
    )
    service = service_factory(fake)

    result = service.cancel_pending_order(81)

    assert result["status"] == OperationStatus.UNKNOWN.value
    assert result["success"] is False


def test_modify_limit_preserves_omitted_fields_normalizes_and_requeries(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    before = _pending_order(price=1.098, expiration=1_800_000_000, type_time=2)
    after = _pending_order(price=1.0981, expiration=1_800_000_000, type_time=2)
    fake.order_responses = [(before,), (after,)]
    service = service_factory(fake)

    result = service.modify_pending_order(81, price=1.09806)

    request = fake.sent_requests[0]
    assert request == {
        "action": fake.TRADE_ACTION_MODIFY,
        "order": 81,
        "symbol": "EURUSDm",
        "type": fake.ORDER_TYPE_BUY_LIMIT,
        "price": 1.0981,
        "sl": before.sl,
        "tp": before.tp,
        "type_time": before.type_time,
        "expiration": before.time_expiration,
    }
    assert "type_filling" not in request
    assert "stoplimit" not in request
    assert result["status"] == OperationStatus.CONFIRMED.value
    assert result["effective_price"] == 1.0981


def test_modify_stop_limit_preserves_stoplimit_leg_and_confirms_all_fields(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    before = _pending_order(
        order_type=fake.ORDER_TYPE_BUY_STOP_LIMIT,
        price=1.102,
        stoplimit=1.1015,
        sl=1.1,
        tp=1.104,
    )
    after = _pending_order(
        order_type=fake.ORDER_TYPE_BUY_STOP_LIMIT,
        price=1.102,
        stoplimit=1.1015,
        sl=1.1,
        tp=1.1041,
    )
    fake.order_responses = [(before,), (after,)]
    service = service_factory(fake)

    result = service.modify_pending_order(81, tp=1.10406)

    request = fake.sent_requests[0]
    assert request["type"] == fake.ORDER_TYPE_BUY_STOP_LIMIT
    assert request["stoplimit"] == before.price_stoplimit
    assert result["status"] == OperationStatus.CONFIRMED.value
    assert result["effective_stoplimit"] == before.price_stoplimit


def test_modify_expiration_selects_specified_time_and_verifies_it(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    before = _pending_order(expiration=0, type_time=fake.ORDER_TIME_GTC)
    after = _pending_order(
        expiration=1_800_000_000,
        type_time=fake.ORDER_TIME_SPECIFIED,
    )
    fake.order_responses = [(before,), (after,)]
    service = service_factory(fake)

    result = service.modify_pending_order(
        81,
        expiration=datetime.fromtimestamp(1_800_000_000, tz=timezone.utc),
    )

    request = fake.sent_requests[0]
    assert request["expiration"] == 1_800_000_000
    assert request["type_time"] == fake.ORDER_TIME_SPECIFIED
    assert result["status"] == OperationStatus.CONFIRMED.value


@pytest.mark.parametrize(
    ("order_type", "price", "sl", "tp", "stoplimit"),
    [
        (PendingContractMT5.ORDER_TYPE_BUY_LIMIT, 1.098, 1.096, 1.102, 0.0),
        (PendingContractMT5.ORDER_TYPE_SELL_LIMIT, 1.102, 1.104, 1.098, 0.0),
        (PendingContractMT5.ORDER_TYPE_BUY_STOP, 1.102, 1.098, 1.104, 0.0),
        (PendingContractMT5.ORDER_TYPE_SELL_STOP, 1.098, 1.102, 1.096, 0.0),
        (
            PendingContractMT5.ORDER_TYPE_BUY_STOP_LIMIT,
            1.102,
            1.099,
            1.104,
            1.1015,
        ),
        (
            PendingContractMT5.ORDER_TYPE_SELL_STOP_LIMIT,
            1.098,
            1.101,
            1.096,
            1.0985,
        ),
    ],
)
def test_modify_payload_supports_every_pending_order_type(
    service_factory,
    order_type: int,
    price: float,
    sl: float,
    tp: float,
    stoplimit: float,
) -> None:
    fake = PendingContractMT5()
    before = _pending_order(
        order_type=order_type,
        price=price,
        sl=sl,
        tp=tp,
        stoplimit=stoplimit,
    )
    after = _pending_order(
        order_type=order_type,
        price=price,
        sl=sl,
        tp=tp,
        stoplimit=stoplimit,
        expiration=1_800_000_000,
        type_time=fake.ORDER_TIME_SPECIFIED,
    )
    fake.order_responses = [(before,), (after,)]
    service = service_factory(fake)

    result = service.modify_pending_order(81, expiration=1_800_000_000)

    request = fake.sent_requests[0]
    assert request["type"] == order_type
    assert ("stoplimit" in request) is (order_type in {6, 7})
    assert "type_filling" not in request
    assert result["status"] == OperationStatus.CONFIRMED.value


@pytest.mark.parametrize(
    ("retcode", "expected_status"),
    [
        (PendingContractMT5.TRADE_RETCODE_DONE, OperationStatus.UNKNOWN),
        (PendingContractMT5.TRADE_RETCODE_INVALID_STOPS, OperationStatus.REJECTED),
        (None, OperationStatus.UNKNOWN),
    ],
)
def test_modify_pending_order_requires_observed_postcondition(
    service_factory,
    retcode: int | None,
    expected_status: OperationStatus,
) -> None:
    fake = PendingContractMT5()
    before = _pending_order()
    fake.order_responses = [(before,), (before,)]
    fake.send_result = (
        None
        if retcode is None
        else SimpleNamespace(retcode=retcode, comment="broker response", order=81)
    )
    service = service_factory(fake)

    result = service.modify_pending_order(81, price=1.0975)

    assert result["status"] == expected_status.value
    assert result["success"] is False
    assert result["effective_price"] == before.price_open


def test_modify_pending_query_failure_after_send_is_unknown(service_factory) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [(_pending_order(),), None]
    fake.error = (-10004, "connection lost")
    service = service_factory(fake)

    result = service.modify_pending_order(81, price=1.0975)

    assert result["status"] == OperationStatus.UNKNOWN.value
    assert result["success"] is False
    assert result["error_code"] == -10004


def test_pending_stop_freeze_violation_is_rejected_before_send(service_factory) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [(_pending_order(),)]
    service = service_factory(fake)

    # Buy limit must remain at least max(stops, freeze) below Ask (1.1002).
    result = service.modify_pending_order(81, price=1.1001)

    assert result["status"] == OperationStatus.REJECTED.value
    assert "stop/freeze" in str(result["message"])
    assert fake.sent_requests == []


def test_position_stop_freeze_violation_is_rejected_before_send(service_factory) -> None:
    fake = PendingContractMT5()
    fake.position_responses = [(_position(),)]
    service = service_factory(fake)

    # A buy position closes at Bid (1.1000); max distance is 0.0002.
    result = service.modify_position_sltp(41, sl=1.0999)

    assert result["status"] == OperationStatus.REJECTED.value
    assert "stop/freeze" in str(result["message"])
    assert fake.sent_requests == []


def test_position_protection_removal_inside_freeze_zone_fails_closed(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.stops_level = 0
    fake.freeze_level = 20
    fake.position_responses = [(_position(sl=1.0999),)]
    service = service_factory(fake)

    result = service.modify_position_sltp(41, sl=0)

    assert result["status"] == OperationStatus.REJECTED.value
    assert "freeze zone" in str(result["message"])
    assert fake.sent_requests == []


def test_constraint_validation_fails_closed_when_tick_is_unavailable(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [(_pending_order(),)]
    fake.tick = None
    service = service_factory(fake)

    result = service.modify_pending_order(81, price=1.0975)

    assert result["status"] == OperationStatus.REJECTED.value
    assert "cannot be verified safely" in str(result["message"])
    assert fake.sent_requests == []


def test_pending_modify_fails_closed_without_normalization_metadata(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.order_responses = [(_pending_order(),)]
    fake.symbol_metadata_available = False
    service = service_factory(fake)

    result = service.modify_pending_order(81, price=1.0975)

    assert result["status"] == OperationStatus.REJECTED.value
    assert "cannot be normalized safely" in str(result["message"])
    assert fake.sent_requests == []


def test_manual_partial_close_normalizes_requested_volume_and_reports_remaining(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.position_responses = [
        (_position(volume=0.2),),
        (_position(volume=0.1),),
    ]
    fake.send_result = SimpleNamespace(
        retcode=fake.TRADE_RETCODE_DONE,
        comment="done",
        order=501,
        deal=502,
    )
    service = service_factory(fake)

    result = service.close_position(41, volume=0.105)

    assert fake.sent_requests[0]["volume"] == 0.1
    assert result["status"] == OperationStatus.PARTIAL.value
    assert result["requested_volume"] == 0.1
    assert result["executed_volume"] == pytest.approx(0.1)
    assert result["remaining_volume"] == 0.1


def test_reconcile_position_accepts_app_alias_and_all_correlation_fields(
    service_factory,
) -> None:
    fake = PendingContractMT5()
    fake.position_responses = [
        (
            _position(ticket=41, opened_at=1_700_000_010),
            _position(ticket=42, side=1, opened_at=1_700_000_020),
            _position(ticket=43, volume=0.3, opened_at=1_700_000_030),
            _position(ticket=44, opened_at=1_699_999_999),
            _position(ticket=45, opened_at=1_700_000_040),
            _position(
                ticket=46,
                opened_at=1_700_000_050,
                magic=999,
                comment="manual",
            ),
        )
    ]
    service = service_factory(fake)

    reconciled = service.reconcile_open_position(
        "EUR/USD",
        expected_ticket=42,
        expected_side="buy",
        expected_volume=0.2,
        opened_after=datetime.fromtimestamp(1_700_000_000, tz=timezone.utc),
        magic=260609,
        comment_prefix="AMA Scanner correlation-1 suffix-truncated-by-broker",
    )

    # Ticket 42 cannot bypass side correlation; the newest fully correlated
    # broker position is selected instead.
    assert reconciled is not None
    assert reconciled.position_id == 45
    assert reconciled.broker_symbol == "EURUSDm"
    assert reconciled.app_symbol == "EUR/USD"
