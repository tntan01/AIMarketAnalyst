"""Broker-facing contracts for reliable order management.

The legacy MT5 APIs in :mod:`services.mt5_service` return lists and dictionaries.
Those shapes cannot distinguish an empty broker snapshot from a failed query.  The
models in this module keep that distinction explicit while still offering
``to_dict`` helpers for existing UI callers.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class SnapshotStatus(str, Enum):
    """Availability of one atomic broker read."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    STALE = "stale"


class OperationStatus(str, Enum):
    """Postcondition-based outcome of a broker mutation."""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


class AccountTradeMode(str, Enum):
    DEMO = "demo"
    CONTEST = "contest"
    REAL = "real"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class AccountIdentity:
    """Fields that scope broker state to one trading account."""

    broker: str
    server: str
    login: int
    trade_mode: AccountTradeMode = AccountTradeMode.UNKNOWN
    currency: str = ""
    balance: float | None = None
    trade_allowed: bool | None = None

    @property
    def fingerprint(self) -> str:
        return f"{self.broker}|{self.server}|{self.login}"

    @property
    def is_demo(self) -> bool:
        return self.trade_mode is AccountTradeMode.DEMO

    @property
    def is_live(self) -> bool:
        return self.trade_mode is AccountTradeMode.REAL

    def to_dict(self) -> dict[str, Any]:
        return {
            "broker": self.broker,
            "server": self.server,
            "login": self.login,
            "trade_mode": self.trade_mode.value,
            "is_demo": self.is_demo,
            "is_live": self.is_live,
            "currency": self.currency,
            "balance": self.balance,
            "trade_allowed": self.trade_allowed,
        }


@dataclass(frozen=True, slots=True)
class BrokerSymbolMetadata:
    """Execution constraints required to normalize broker requests."""

    digits: int | None = None
    point: float | None = None
    trade_tick_size: float | None = None
    trade_stops_level: int | None = None
    trade_freeze_level: int | None = None
    filling_mode: int | None = None
    volume_min: float | None = None
    volume_max: float | None = None
    volume_step: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "digits": self.digits,
            "point": self.point,
            "trade_tick_size": self.trade_tick_size,
            "trade_stops_level": self.trade_stops_level,
            "trade_freeze_level": self.trade_freeze_level,
            "filling_mode": self.filling_mode,
            "volume_min": self.volume_min,
            "volume_max": self.volume_max,
            "volume_step": self.volume_step,
        }


@dataclass(frozen=True, slots=True)
class BrokerPosition:
    position_id: int
    broker_symbol: str
    app_symbol: str
    side: str
    volume: float
    open_price: float
    current_price: float
    sl: float
    tp: float
    profit: float
    swap: float
    commission: float
    magic: int
    comment: str
    open_time: int
    identifier: int
    symbol_metadata: BrokerSymbolMetadata

    @property
    def ticket(self) -> int:
        return self.position_id

    @property
    def symbol(self) -> str:
        return self.broker_symbol

    def to_legacy_dict(self) -> dict[str, object]:
        """Return the pre-V2 dictionary plus additive broker metadata."""

        return {
            "position_id": self.position_id,
            "symbol": self.broker_symbol,
            "broker_symbol": self.broker_symbol,
            "app_symbol": self.app_symbol,
            "side": self.side,
            "volume": self.volume,
            "open_price": self.open_price,
            "current_price": self.current_price,
            "sl": self.sl,
            "tp": self.tp,
            "profit": self.profit,
            "swap": self.swap,
            "commission": self.commission,
            "magic": self.magic,
            "comment": self.comment,
            "open_time": self.open_time,
            "identifier": self.identifier,
            **self.symbol_metadata.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class BrokerPendingOrder:
    order_id: int
    broker_symbol: str
    app_symbol: str
    order_type: str
    raw_order_type: int
    volume: float
    volume_initial: float
    price: float
    sl: float
    tp: float
    magic: int
    comment: str
    setup_time: int
    expiration_time: int
    symbol_metadata: BrokerSymbolMetadata
    stoplimit_price: float = 0.0
    type_time: int = 0

    @property
    def ticket(self) -> int:
        return self.order_id

    @property
    def symbol(self) -> str:
        return self.broker_symbol

    def to_legacy_dict(self) -> dict[str, object]:
        """Return the pre-V2 dictionary plus additive broker metadata."""

        return {
            "order_id": self.order_id,
            "symbol": self.broker_symbol,
            "broker_symbol": self.broker_symbol,
            "app_symbol": self.app_symbol,
            "type": self.order_type,
            "raw_type": self.raw_order_type,
            "volume": self.volume,
            "volume_initial": self.volume_initial,
            "price": self.price,
            "sl": self.sl,
            "tp": self.tp,
            "magic": self.magic,
            "comment": self.comment,
            "setup_time": self.setup_time,
            "expiration_time": self.expiration_time,
            "expiration": self.expiration_time,
            "stoplimit_price": self.stoplimit_price,
            "price_stoplimit": self.stoplimit_price,
            "stoplimit": self.stoplimit_price,
            "type_time": self.type_time,
            **self.symbol_metadata.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class PositionsSnapshot:
    status: SnapshotStatus
    account: AccountIdentity | None
    positions: tuple[BrokerPosition, ...]
    observed_at_utc: datetime
    error_code: int | None = None
    message: str = ""

    @property
    def available(self) -> bool:
        return self.status is SnapshotStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class PendingOrdersSnapshot:
    status: SnapshotStatus
    account: AccountIdentity | None
    orders: tuple[BrokerPendingOrder, ...]
    observed_at_utc: datetime
    error_code: int | None = None
    message: str = ""

    @property
    def available(self) -> bool:
        return self.status is SnapshotStatus.AVAILABLE


@dataclass(frozen=True, slots=True)
class BrokerTick:
    broker_symbol: str
    bid: float
    ask: float
    time: int
    time_msc: int


@dataclass(frozen=True, slots=True)
class TickSnapshot:
    status: SnapshotStatus
    account: AccountIdentity | None
    tick: BrokerTick | None
    observed_at_utc: datetime
    error_code: int | None = None
    message: str = ""

    @property
    def available(self) -> bool:
        return self.status is SnapshotStatus.AVAILABLE and self.tick is not None


@dataclass(frozen=True, slots=True)
class PositionModifyResult:
    status: OperationStatus
    position_id: int
    broker_symbol: str = ""
    requested_sl: float | None = None
    requested_tp: float | None = None
    effective_sl: float | None = None
    effective_tp: float | None = None
    retcode: int | None = None
    order_id: int | None = None
    deal_id: int | None = None
    error_code: int | None = None
    message: str = ""
    precondition_failed: bool = False

    @property
    def success(self) -> bool:
        return self.status is OperationStatus.CONFIRMED

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "status": self.status.value,
            "position_id": self.position_id,
            "symbol": self.broker_symbol,
            "broker_symbol": self.broker_symbol,
            # ``sl`` and ``tp`` are retained for legacy consumers.
            "sl": self.requested_sl,
            "tp": self.requested_tp,
            "requested_sl": self.requested_sl,
            "requested_tp": self.requested_tp,
            "effective_sl": self.effective_sl,
            "effective_tp": self.effective_tp,
            "retcode": self.retcode,
            "order_id": self.order_id,
            "deal_id": self.deal_id,
            "error_code": self.error_code,
            "message": self.message,
            "precondition_failed": self.precondition_failed,
        }


@dataclass(frozen=True, slots=True)
class PositionCloseResult:
    status: OperationStatus
    position_id: int
    broker_symbol: str = ""
    requested_volume: float | None = None
    executed_volume: float | None = None
    remaining_volume: float | None = None
    price: float | None = None
    retcode: int | None = None
    order_id: int | None = None
    deal_id: int | None = None
    error_code: int | None = None
    message: str = ""
    precondition_failed: bool = False

    @property
    def success(self) -> bool:
        # Legacy ``success`` means the position was confirmed fully closed.
        return self.status is OperationStatus.CONFIRMED

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "status": self.status.value,
            "position_id": self.position_id,
            "symbol": self.broker_symbol,
            "broker_symbol": self.broker_symbol,
            # ``volume`` is retained for legacy consumers.
            "volume": self.requested_volume,
            "requested_volume": self.requested_volume,
            "executed_volume": self.executed_volume,
            "remaining_volume": self.remaining_volume,
            "price": self.price,
            "retcode": self.retcode,
            "order_id": self.order_id,
            "deal_id": self.deal_id,
            "error_code": self.error_code,
            "message": self.message,
            "precondition_failed": self.precondition_failed,
        }


@dataclass(frozen=True, slots=True)
class PendingOrderCancelResult:
    """Compatibility result for a verified pending-order cancellation."""

    status: OperationStatus
    order_id: int
    broker_symbol: str = ""
    retcode: int | None = None
    response_order_id: int | None = None
    error_code: int | None = None
    message: str = ""
    precondition_failed: bool = False

    @property
    def success(self) -> bool:
        return self.status is OperationStatus.CONFIRMED

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "status": self.status.value,
            "order_id": self.order_id,
            "pending_order_id": self.order_id,
            "symbol": self.broker_symbol,
            "broker_symbol": self.broker_symbol,
            "retcode": self.retcode,
            "response_order_id": self.response_order_id,
            "error_code": self.error_code,
            "message": self.message,
            "precondition_failed": self.precondition_failed,
        }


@dataclass(frozen=True, slots=True)
class PendingOrderModifyResult:
    """Compatibility result for a verified pending-order modification."""

    status: OperationStatus
    order_id: int
    broker_symbol: str = ""
    order_type: str = ""
    raw_order_type: int | None = None
    requested_price: float | None = None
    requested_sl: float | None = None
    requested_tp: float | None = None
    requested_stoplimit: float | None = None
    requested_expiration: int | None = None
    requested_type_time: int | None = None
    effective_price: float | None = None
    effective_sl: float | None = None
    effective_tp: float | None = None
    effective_stoplimit: float | None = None
    effective_expiration: int | None = None
    effective_type_time: int | None = None
    retcode: int | None = None
    response_order_id: int | None = None
    error_code: int | None = None
    message: str = ""
    precondition_failed: bool = False

    @property
    def success(self) -> bool:
        return self.status is OperationStatus.CONFIRMED

    def to_dict(self) -> dict[str, object]:
        return {
            "success": self.success,
            "status": self.status.value,
            "order_id": self.order_id,
            "pending_order_id": self.order_id,
            "symbol": self.broker_symbol,
            "broker_symbol": self.broker_symbol,
            "order_type": self.order_type,
            "raw_order_type": self.raw_order_type,
            # Short names are retained for callers of the legacy dictionary API.
            "price": self.requested_price,
            "sl": self.requested_sl,
            "tp": self.requested_tp,
            "stoplimit": self.requested_stoplimit,
            "stoplimit_price": self.requested_stoplimit,
            "price_stoplimit": self.requested_stoplimit,
            "expiration": self.requested_expiration,
            "expiration_time": self.requested_expiration,
            "type_time": self.requested_type_time,
            "requested_price": self.requested_price,
            "requested_sl": self.requested_sl,
            "requested_tp": self.requested_tp,
            "requested_stoplimit": self.requested_stoplimit,
            "requested_expiration": self.requested_expiration,
            "requested_type_time": self.requested_type_time,
            "effective_price": self.effective_price,
            "effective_sl": self.effective_sl,
            "effective_tp": self.effective_tp,
            "effective_stoplimit": self.effective_stoplimit,
            "effective_expiration": self.effective_expiration,
            "effective_type_time": self.effective_type_time,
            "retcode": self.retcode,
            "response_order_id": self.response_order_id,
            "error_code": self.error_code,
            "message": self.message,
            "precondition_failed": self.precondition_failed,
        }
