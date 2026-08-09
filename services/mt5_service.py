from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_FLOOR, ROUND_HALF_UP
from functools import wraps
from math import isfinite
from pathlib import Path
from threading import RLock
from typing import Any

from core.scanner_performance import safe_performance_call

from config.paths import CONFIG_DIR
from core.market_models import Candle
from core.portfolio_models import (
    PortfolioRiskItem,
    PortfolioSnapshot,
)
from core.scanner_models import ExecutionMarketSnapshot
from services.candle_history_cache import (
    CacheFallbackReason,
    CacheIdentity,
    CandleHistoryCache,
)
from services.data_provider import ConnectionStatus, DataProvider, OrderResult
from services.order_management_models import (
    AccountIdentity,
    AccountTradeMode,
    BrokerPendingOrder,
    BrokerPosition,
    BrokerSymbolMetadata,
    BrokerTick,
    OperationStatus,
    PendingOrderCancelResult,
    PendingOrderModifyResult,
    PendingOrdersSnapshot,
    PositionCloseResult,
    PositionModifyResult,
    PositionsSnapshot,
    SnapshotStatus,
    TickSnapshot,
)


def _serialized_mt5_operation(method):
    """Serialize calls into the MetaTrader5 SDK for one service instance."""

    @wraps(method)
    def wrapped(self, *args, **kwargs):
        with self._operation_lock:
            return method(self, *args, **kwargs)

    return wrapped


@dataclass(frozen=True, slots=True)
class MT5ConnectionStatus:
    initialized: bool
    terminal_connected: bool
    logged_in: bool
    trade_allowed: bool
    terminal_name: str = ""
    terminal_path: str = ""
    broker: str = ""
    server: str = ""
    login: int | None = None
    balance: float | None = None
    currency: str = ""
    error_code: int | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class MT5OrderResult:
    success: bool
    symbol: str
    broker_symbol: str
    side: str
    volume: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    order_id: int | None = None
    retcode: int | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class MT5HistoryCacheIdentity:
    """Broker/account scope used by the in-memory OHLCV cache."""

    server: str
    broker: str
    login: int | str

    def __post_init__(self) -> None:
        server = str(self.server or "").strip()
        broker = str(self.broker or "").strip()
        login = str(self.login if self.login is not None else "").strip()
        if not server or not broker or not login:
            raise ValueError(
                "MT5 history cache identity requires server, broker, and login."
            )
        object.__setattr__(self, "server", server)
        object.__setattr__(self, "broker", broker)
        object.__setattr__(self, "login", login)

    @classmethod
    def from_connection_status(
        cls,
        status: ConnectionStatus,
    ) -> MT5HistoryCacheIdentity | None:
        """Build a complete identity, or disable reuse when metadata is missing."""

        try:
            return cls(
                server=getattr(status, "server", ""),
                broker=getattr(status, "broker", ""),
                login=getattr(status, "login", ""),
            )
        except ValueError:
            return None

    @property
    def account_fingerprint(self) -> str:
        return json.dumps(
            [self.broker, str(self.login)],
            ensure_ascii=True,
            separators=(",", ":"),
        )


_PRIMARY_TIMEFRAME_INTERVALS = {
    "D1": timedelta(days=1),
    "H4": timedelta(hours=4),
    "H1": timedelta(hours=1),
    "M15": timedelta(minutes=15),
}
_MT5_HISTORY_TAIL_BARS = 3


class MT5Service(DataProvider):
    def __init__(self, symbol_profile_path: Path | None = None) -> None:
        path = symbol_profile_path or CONFIG_DIR / "symbol_profiles.json"
        self.symbol_profiles = json.loads(path.read_text(encoding="utf-8"))
        self._quote_usd_cache: dict[str, float | None] = {}
        self._lifecycle_lock = RLock()
        self._operation_lock = RLock()
        self._history_cache = CandleHistoryCache()
        self._owns_connection = False

    @staticmethod
    def _has_existing_session(mt5: object) -> bool:
        try:
            if mt5.terminal_info() is not None or mt5.account_info() is not None:
                return True
        except Exception:
            pass
        return False

    # -- DataProvider interface: connection ---------------------------------

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return False

        with self._lifecycle_lock:
            if self._has_existing_session(mt5):
                return True
            initialized = bool(mt5.initialize())
            if initialized:
                self._owns_connection = True
            return initialized

    def disconnect(self) -> None:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return

        with self._lifecycle_lock:
            if not self._owns_connection:
                return
            mt5.shutdown()
            self._owns_connection = False

    def connect_thread(self) -> bool:
        """Compatibility alias for callers using the legacy name."""
        return self.connect()

    def disconnect_thread(self) -> None:
        """Compatibility alias for callers using the legacy name."""
        self.disconnect()

    def ensure_ready(
        self,
        *,
        require_login: bool = True,
        require_trade: bool = False,
    ) -> ConnectionStatus:
        self.connect()
        return super().ensure_ready(
            require_login=require_login,
            require_trade=require_trade,
        )

    @_serialized_mt5_operation
    def connection_status(self) -> ConnectionStatus:
        mt5_status = self.mt5_connection_status()
        return ConnectionStatus(
            initialized=mt5_status.initialized,
            connected=mt5_status.terminal_connected,
            logged_in=mt5_status.logged_in,
            trade_allowed=mt5_status.trade_allowed,
            provider_name="MT5",
            broker=mt5_status.broker,
            server=mt5_status.server,
            login=mt5_status.login,
            balance=mt5_status.balance,
            currency=mt5_status.currency,
            error_code=mt5_status.error_code,
            message=mt5_status.message,
        )

    @_serialized_mt5_operation
    def mt5_connection_status(self) -> MT5ConnectionStatus:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return MT5ConnectionStatus(
                initialized=False,
                terminal_connected=False,
                logged_in=False,
                trade_allowed=False,
                message="Chưa cài package MetaTrader5.",
            )

        error_code, error_message = mt5.last_error()
        terminal = mt5.terminal_info()
        account = mt5.account_info()
        initialized = terminal is not None or account is not None
        if not initialized:
            return MT5ConnectionStatus(
                initialized=False,
                terminal_connected=False,
                logged_in=False,
                trade_allowed=False,
                error_code=error_code,
                message=error_message or "Không khởi tạo được kết nối MT5.",
            )

        terminal_connected = bool(terminal and terminal.connected)
        logged_in = bool(account and account.login)
        trade_allowed = bool(
            account
            and account.trade_allowed
            and (terminal is None or getattr(terminal, "trade_allowed", True))
        )

        return MT5ConnectionStatus(
            initialized=True,
            terminal_connected=terminal_connected,
            logged_in=logged_in,
            trade_allowed=trade_allowed,
            terminal_name=getattr(terminal, "name", "") if terminal else "",
            terminal_path=getattr(terminal, "path", "") if terminal else "",
            broker=getattr(account, "company", "") if account else "",
            server=getattr(account, "server", "") if account else "",
            login=getattr(account, "login", None) if account else None,
            balance=float(getattr(account, "balance", 0.0)) if account and getattr(account, "balance", None) is not None else None,
            currency=getattr(account, "currency", "") if account else "",
            error_code=error_code,
            message="Đã kết nối MT5." if terminal_connected else "MT5 chưa connected trong terminal.",
        )

    @_serialized_mt5_operation
    def execution_snapshot(self, broker_symbol: str) -> ExecutionMarketSnapshot:
        """Capture broker state once for the fail-closed execution gate."""

        captured_at = datetime.now(timezone.utc)
        self.connect()
        status = self.mt5_connection_status()
        reasons: list[str] = []
        values: dict[str, Any] = {
            "broker_symbol": str(broker_symbol or "").strip(),
            "captured_at": captured_at,
            "connected": status.terminal_connected,
            "logged_in": status.logged_in,
            "trade_allowed": status.trade_allowed,
            "symbol_available": False,
            "symbol_trade_mode": None,
            "bid": None,
            "ask": None,
            "point": None,
            "spread_points": None,
            "spread_price": None,
            "tick_time": None,
            "volume_min": None,
            "volume_max": None,
            "volume_step": None,
            "symbol_state_available": False,
            "has_open_position_or_order": None,
            "trade_tick_size": None,
            "trade_tick_value_loss": None,
            "contract_size": None,
        }
        if not broker_symbol:
            return ExecutionMarketSnapshot(
                **values,
                reason_codes=("BROKER_SYMBOL_MISSING",),
            )

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return ExecutionMarketSnapshot(
                **values,
                reason_codes=("MT5_PACKAGE_UNAVAILABLE",),
            )

        if not status.initialized or not status.terminal_connected or not status.logged_in:
            return ExecutionMarketSnapshot(
                **values,
                reason_codes=("MT5_NOT_READY",),
            )

        try:
            selected = bool(mt5.symbol_select(broker_symbol, True))
            info = mt5.symbol_info(broker_symbol) if selected else None
            tick = mt5.symbol_info_tick(broker_symbol) if info is not None else None
            values["symbol_available"] = info is not None
            if info is None:
                reasons.append("SYMBOL_INFO_UNAVAILABLE")
            else:
                values["symbol_trade_mode"] = _optional_int(
                    getattr(info, "trade_mode", None)
                )
                values["point"] = _optional_positive_float(
                    getattr(info, "point", None)
                )
                values["volume_min"] = _optional_positive_float(
                    getattr(info, "volume_min", None)
                )
                values["volume_max"] = _optional_positive_float(
                    getattr(info, "volume_max", None)
                )
                values["volume_step"] = _optional_positive_float(
                    getattr(info, "volume_step", None)
                )
                values["trade_tick_size"] = _optional_positive_float(
                    getattr(info, "trade_tick_size", None)
                ) or values["point"]
                values["trade_tick_value_loss"] = _optional_positive_float(
                    getattr(info, "trade_tick_value_loss", None)
                ) or _optional_positive_float(
                    getattr(info, "trade_tick_value", None)
                )
                values["contract_size"] = _optional_positive_float(
                    getattr(info, "trade_contract_size", None)
                )

            if tick is None:
                reasons.append("TICK_UNAVAILABLE")
            else:
                bid = _optional_positive_float(getattr(tick, "bid", None))
                ask = _optional_positive_float(getattr(tick, "ask", None))
                values["bid"] = bid
                values["ask"] = ask
                tick_timestamp = _tick_timestamp(tick)
                values["tick_time"] = (
                    datetime.fromtimestamp(tick_timestamp, tz=timezone.utc)
                    if tick_timestamp is not None
                    else None
                )
                point = values["point"]
                if (
                    bid is not None
                    and ask is not None
                    and ask >= bid
                    and point is not None
                ):
                    spread_price = ask - bid
                    values["spread_price"] = spread_price
                    values["spread_points"] = spread_price / point
                elif info is not None:
                    spread_points = _optional_nonnegative_float(
                        getattr(info, "spread", None)
                    )
                    values["spread_points"] = spread_points
                    values["spread_price"] = (
                        spread_points * point
                        if spread_points is not None and point is not None
                        else None
                    )

            positions = mt5.positions_get(symbol=broker_symbol)
            orders = mt5.orders_get(symbol=broker_symbol)
            if positions is None or orders is None:
                reasons.append("SYMBOL_POSITION_STATE_UNAVAILABLE")
            else:
                values["symbol_state_available"] = True
                values["has_open_position_or_order"] = bool(positions or orders)
        except Exception:
            reasons.append("EXECUTION_SNAPSHOT_FAILED")

        return ExecutionMarketSnapshot(
            **values,
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    @_serialized_mt5_operation
    def portfolio_snapshot(self) -> PortfolioSnapshot:
        """Capture all live positions and pending orders with broker risk data."""

        captured_at = datetime.now(timezone.utc)
        self.connect()
        status = self.mt5_connection_status()
        if (
            not status.initialized
            or not status.terminal_connected
            or not status.logged_in
        ):
            return PortfolioSnapshot(
                available=False,
                captured_at=captured_at,
                account_balance=status.balance,
                account_currency=status.currency,
                reason_codes=("PORTFOLIO_MT5_NOT_READY",),
            )

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return PortfolioSnapshot(
                available=False,
                captured_at=captured_at,
                account_balance=status.balance,
                account_currency=status.currency,
                reason_codes=("MT5_PACKAGE_UNAVAILABLE",),
            )

        try:
            raw_positions = mt5.positions_get()
            raw_orders = mt5.orders_get()
            if raw_positions is None or raw_orders is None:
                return PortfolioSnapshot(
                    available=False,
                    captured_at=captured_at,
                    account_balance=status.balance,
                    account_currency=status.currency,
                    reason_codes=("PORTFOLIO_STATE_UNAVAILABLE",),
                )
            positions = tuple(
                self._portfolio_risk_item(mt5, item, source="position")
                for item in raw_positions
            )
            pending_orders = tuple(
                self._portfolio_risk_item(mt5, item, source="pending_order")
                for item in raw_orders
            )
            return PortfolioSnapshot(
                available=True,
                captured_at=captured_at,
                account_balance=status.balance,
                account_currency=status.currency,
                positions=positions,
                pending_orders=pending_orders,
            )
        except Exception:
            return PortfolioSnapshot(
                available=False,
                captured_at=captured_at,
                account_balance=status.balance,
                account_currency=status.currency,
                reason_codes=("PORTFOLIO_SNAPSHOT_FAILED",),
            )

    def _portfolio_risk_item(
        self,
        mt5_module: object,
        item: object,
        *,
        source: str,
    ) -> PortfolioRiskItem:
        broker_symbol = str(getattr(item, "symbol", "") or "")
        reasons: list[str] = []
        try:
            mt5_module.symbol_select(broker_symbol, True)
            info = mt5_module.symbol_info(broker_symbol)
        except Exception:
            info = None
        if info is None:
            reasons.append("PORTFOLIO_SYMBOL_INFO_UNAVAILABLE")

        raw_type = _optional_int(getattr(item, "type", None))
        if source == "position":
            side = "buy" if raw_type == 0 else "sell" if raw_type == 1 else ""
            entry_price = _optional_positive_float(
                getattr(item, "price_open", None)
            )
            current_price = _optional_positive_float(
                getattr(item, "price_current", None)
            )
            volume = _optional_positive_float(getattr(item, "volume", None))
            ticket = int(getattr(item, "ticket", 0) or 0)
        else:
            side = (
                "buy"
                if raw_type in {2, 4, 6}
                else "sell" if raw_type in {3, 5, 7} else ""
            )
            entry_price = _optional_positive_float(
                getattr(item, "price_open", None)
            )
            current_price = None
            volume = _optional_positive_float(
                getattr(item, "volume_current", None)
            ) or _optional_positive_float(
                getattr(item, "volume_initial", None)
            )
            ticket = int(getattr(item, "ticket", 0) or 0)
        if not side:
            reasons.append("PORTFOLIO_ITEM_SIDE_INVALID")

        return PortfolioRiskItem(
            source=source,
            ticket=ticket,
            symbol=self.app_symbol_for_broker_symbol(broker_symbol),
            broker_symbol=broker_symbol,
            side=side,
            entry_price=entry_price,
            current_price=current_price,
            stop_loss=_optional_positive_float(getattr(item, "sl", None)),
            volume=volume,
            tick_size=(
                _optional_positive_float(
                    getattr(info, "trade_tick_size", None)
                )
                or _optional_positive_float(getattr(info, "point", None))
                if info is not None
                else None
            ),
            tick_value_loss=(
                _optional_positive_float(
                    getattr(info, "trade_tick_value_loss", None)
                )
                or _optional_positive_float(
                    getattr(info, "trade_tick_value", None)
                )
                if info is not None
                else None
            ),
            contract_size=(
                _optional_positive_float(
                    getattr(info, "trade_contract_size", None)
                )
                if info is not None
                else None
            ),
            reason_codes=tuple(dict.fromkeys(reasons)),
        )

    @_serialized_mt5_operation
    def account_balance(self) -> float | None:
        self.connect()
        status = self.mt5_connection_status()
        if not status.terminal_connected or not status.logged_in:
            return None
        return status.balance

    def aliases_for(self, app_symbol: str) -> list[str]:
        profile = self.symbol_profiles.get(app_symbol)
        if not profile:
            return []
        return list(profile.get("mt5_aliases", []))

    def resolve_symbol(self, app_symbol: str, available_symbols: list[str]) -> str | None:
        available = set(available_symbols)
        for alias in self.aliases_for(app_symbol):
            if alias in available:
                return alias

        available_by_lower = {symbol.lower(): symbol for symbol in available_symbols}
        for alias in self.aliases_for(app_symbol):
            match = available_by_lower.get(alias.lower())
            if match:
                return match

        raw_symbol = app_symbol.replace("/", "").lower()
        candidates = sorted(
            (
                symbol
                for symbol in available_symbols
                if self._normalize_symbol_name(symbol).startswith(raw_symbol)
            ),
            key=len,
        )
        if candidates:
            return candidates[0]
        return None

    def configured_symbols_in_market_watch(self) -> list[tuple[str, str]]:
        available_symbols = self.available_symbols(market_watch_only=True)
        matched: list[tuple[str, str]] = []
        for app_symbol in sorted(self.symbol_profiles):
            broker_symbol = self.resolve_symbol(app_symbol, available_symbols)
            if broker_symbol:
                matched.append((app_symbol, broker_symbol))
        return matched

    @_serialized_mt5_operation
    def available_symbols(self, market_watch_only: bool = True) -> list[str]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []

        if not self.connect():
            return []

        symbols = mt5.symbols_get()
        if not symbols:
            return []
        names = set()
        for symbol in symbols:
            name = getattr(symbol, "name", "")
            if not name:
                continue
            if market_watch_only and not getattr(symbol, "visible", False):
                continue
            names.add(name)
        return sorted(names)

    @_serialized_mt5_operation
    def load_ohlcv(self, broker_symbol: str, timeframe: str, bars: int, skip_select: bool = False) -> list[Candle]:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("Chưa cài package MetaTrader5.") from exc

        # Assume connected

        timeframe_id = self._timeframe_id(mt5, timeframe)
        if timeframe_id is None:
            raise ValueError(f"Timeframe không hỗ trợ: {timeframe}")

        if not skip_select:
            selected = mt5.symbol_select(broker_symbol, True)
            if not selected:
                raise RuntimeError(f"Không chọn được mã {broker_symbol} trong MT5 Market Watch.")

        rates = mt5.copy_rates_from_pos(broker_symbol, timeframe_id, 0, bars)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"Không lấy được OHLCV cho {broker_symbol} {timeframe}.")

        candles: list[Candle] = []
        for item in rates:
            timestamp = int(item["time"] if hasattr(item, "__getitem__") else getattr(item, "time"))
            try:
                volume = float(item["tick_volume"])
            except Exception:
                volume = float(getattr(item, "tick_volume", 0.0))
            candles.append(
                Candle(
                    time=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                    open=float(item["open"] if hasattr(item, "__getitem__") else getattr(item, "open")),
                    high=float(item["high"] if hasattr(item, "__getitem__") else getattr(item, "high")),
                    low=float(item["low"] if hasattr(item, "__getitem__") else getattr(item, "low")),
                    close=float(item["close"] if hasattr(item, "__getitem__") else getattr(item, "close")),
                    volume=volume,
                )
            )
        return candles

    @_serialized_mt5_operation
    def load_ohlcv_range(
        self,
        broker_symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        skip_select: bool = False,
    ) -> list[Candle]:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("Chưa cài package MetaTrader5.") from exc

        if end <= start:
            raise ValueError("Thời điểm kết thúc phải sau thời điểm bắt đầu.")

        # Assume connected

        timeframe_id = self._timeframe_id(mt5, timeframe)
        if timeframe_id is None:
            raise ValueError(f"Timeframe không hỗ trợ: {timeframe}")

        if not skip_select:
            selected = mt5.symbol_select(broker_symbol, True)
            if not selected:
                raise RuntimeError(f"Không chọn được mã {broker_symbol} trong MT5 Market Watch.")

        rates = mt5.copy_rates_range(broker_symbol, timeframe_id, start, end)
        if rates is None or len(rates) == 0:
            raise RuntimeError(f"Không lấy được OHLCV cho {broker_symbol} {timeframe} trong khoảng đã chọn.")

        candles: list[Candle] = []
        for item in rates:
            timestamp = int(item["time"] if hasattr(item, "__getitem__") else getattr(item, "time"))
            try:
                volume = float(item["tick_volume"])
            except Exception:
                volume = float(getattr(item, "tick_volume", 0.0))
            candles.append(
                Candle(
                    time=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                    open=float(item["open"] if hasattr(item, "__getitem__") else getattr(item, "open")),
                    high=float(item["high"] if hasattr(item, "__getitem__") else getattr(item, "high")),
                    low=float(item["low"] if hasattr(item, "__getitem__") else getattr(item, "low")),
                    close=float(item["close"] if hasattr(item, "__getitem__") else getattr(item, "close")),
                    volume=volume,
                )
            )
        return candles

    def load_primary_timeframes(
        self,
        broker_symbol: str,
        bars_by_timeframe: dict[str, int],
        *,
        performance_tracker: object | None = None,
    ) -> dict[str, list[Candle]]:
        import MetaTrader5 as mt5
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with self._operation_lock:
            selected = mt5.symbol_select(broker_symbol, True)
        if not selected:
            raise RuntimeError(f"Không chọn được mã {broker_symbol} trong MT5 Market Watch.")

        def tracked_load(timeframe: str, bars: int) -> list[Candle]:
            safe_performance_call(
                performance_tracker,
                "increment",
                "mt5_copy_rates_calls",
            )
            safe_performance_call(
                performance_tracker,
                "increment",
                "mt5_full_history_calls",
            )
            return self.load_ohlcv(
                broker_symbol,
                timeframe,
                bars,
                True,
            )

        results: dict[str, list[Candle]] = {}
        with ThreadPoolExecutor(max_workers=min(len(bars_by_timeframe), 4)) as ex:
            futures = {
                ex.submit(tracked_load, timeframe, bars): timeframe
                for timeframe, bars in bars_by_timeframe.items()
            }
            for future in as_completed(futures):
                timeframe = futures[future]
                try:
                    results[timeframe] = future.result()
                except Exception as exc:
                    raise RuntimeError(
                        f"Không lấy được OHLCV cho {broker_symbol} {timeframe}: {exc}"
                    ) from exc
        return results

    @_serialized_mt5_operation
    def load_primary_timeframes_cached(
        self,
        broker_symbol: str,
        bars_by_timeframe: dict[str, int],
        cache_identity: MT5HistoryCacheIdentity | None,
        *,
        performance_tracker: object | None = None,
    ) -> dict[str, Any]:
        """Load full history once, then refresh and merge a three-bar tail.

        The entire cache transaction is protected by the existing MT5
        operation lock.  A missing identity fails safe to an uncached full
        load, so histories from different broker accounts can never collide.
        """

        normalized_bars = self._validate_history_request(
            broker_symbol,
            bars_by_timeframe,
        )
        if cache_identity is None:
            candles, metrics = self._load_history_batch(
                broker_symbol,
                normalized_bars,
                fetch_kind="full",
                performance_tracker=performance_tracker,
            )
            return {
                "candles_by_timeframe": {
                    timeframe: list(values)
                    for timeframe, values in candles.items()
                },
                "cache_status": "full_reload_identity_change",
                "fetch_metrics": metrics,
            }

        connection_changed = self._history_cache.activate_connection(
            cache_identity.server,
            cache_identity.account_fingerprint,
        )
        identities = {
            timeframe: CacheIdentity(
                server=cache_identity.server,
                account_fingerprint=cache_identity.account_fingerprint,
                broker_symbol=broker_symbol,
                timeframe=timeframe,
            )
            for timeframe in normalized_bars
        }
        lookups = {
            timeframe: self._history_cache.lookup(
                identities[timeframe],
                expected_interval=_PRIMARY_TIMEFRAME_INTERVALS[timeframe],
                max_count=max_count,
            )
            for timeframe, max_count in normalized_bars.items()
        }

        if not connection_changed and all(
            lookup.usable for lookup in lookups.values()
        ):
            tail_request = {
                timeframe: _MT5_HISTORY_TAIL_BARS
                for timeframe in normalized_bars
            }
            tails, tail_metrics = self._load_history_batch(
                broker_symbol,
                tail_request,
                fetch_kind="tail",
                performance_tracker=performance_tracker,
            )
            staged = self._stage_tail_merge(
                identities,
                normalized_bars,
                lookups,
                tails,
            )
            if all(result.usable for result in staged.values()):
                snapshots = self._commit_history_snapshots(
                    identities,
                    normalized_bars,
                    {
                        timeframe: result.candles
                        for timeframe, result in staged.items()
                    },
                )
                return {
                    "candles_by_timeframe": snapshots,
                    "cache_status": "warm_tail",
                    "fetch_metrics": tail_metrics,
                }
            fallback_status = self._history_fallback_status(
                [result.fallback_reason for result in staged.values()]
            )
            full, full_metrics = self._load_history_batch(
                broker_symbol,
                normalized_bars,
                fetch_kind="full",
                performance_tracker=performance_tracker,
            )
            snapshots = self._commit_history_snapshots(
                identities,
                normalized_bars,
                full,
            )
            return {
                "candles_by_timeframe": snapshots,
                "cache_status": fallback_status,
                "fetch_metrics": self._combine_fetch_metrics(
                    tail_metrics,
                    full_metrics,
                ),
            }

        fallback_reasons = [
            lookup.fallback_reason for lookup in lookups.values()
        ]
        if connection_changed:
            cache_status = "full_reload_identity_change"
        elif fallback_reasons and all(
            reason is CacheFallbackReason.CACHE_MISSING
            for reason in fallback_reasons
        ):
            cache_status = "cold_full"
        else:
            cache_status = self._history_fallback_status(fallback_reasons)

        full, metrics = self._load_history_batch(
            broker_symbol,
            normalized_bars,
            fetch_kind="full",
            performance_tracker=performance_tracker,
        )
        snapshots = self._commit_history_snapshots(
            identities,
            normalized_bars,
            full,
        )
        return {
            "candles_by_timeframe": snapshots,
            "cache_status": cache_status,
            "fetch_metrics": metrics,
        }

    @staticmethod
    def _validate_history_request(
        broker_symbol: str,
        bars_by_timeframe: dict[str, int],
    ) -> dict[str, int]:
        if not str(broker_symbol or "").strip():
            raise ValueError("Broker symbol is required for MT5 history.")
        if not isinstance(bars_by_timeframe, dict) or not bars_by_timeframe:
            raise ValueError("At least one MT5 timeframe is required.")

        normalized: dict[str, int] = {}
        for raw_timeframe, raw_count in bars_by_timeframe.items():
            timeframe = str(raw_timeframe or "").strip().upper()
            if timeframe not in _PRIMARY_TIMEFRAME_INTERVALS:
                raise ValueError(
                    f"Timeframe khong ho tro cache: {raw_timeframe}"
                )
            if (
                isinstance(raw_count, bool)
                or not isinstance(raw_count, int)
                or raw_count <= 0
            ):
                raise ValueError(
                    f"So bar khong hop le cho timeframe {timeframe}."
                )
            normalized[timeframe] = raw_count
        return normalized

    def _load_history_batch(
        self,
        broker_symbol: str,
        bars_by_timeframe: dict[str, int],
        *,
        fetch_kind: str,
        performance_tracker: object | None,
    ) -> tuple[dict[str, list[Candle]], dict[str, int]]:
        """Run one serialized full or tail batch without a thread pool."""

        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("Chua cai package MetaTrader5.") from exc

        if fetch_kind not in {"full", "tail"}:
            raise ValueError(f"Unknown MT5 history fetch kind: {fetch_kind}")
        if not mt5.symbol_select(broker_symbol, True):
            raise RuntimeError(
                f"Khong chon duoc ma {broker_symbol} trong MT5 Market Watch."
            )

        metrics = {
            "copy_rates_calls": 0,
            "full_history_calls": 0,
            "tail_calls": 0,
            "bars_requested": 0,
            "bars_received": 0,
        }
        results: dict[str, list[Candle]] = {}
        counter_name = (
            "mt5_full_history_calls"
            if fetch_kind == "full"
            else "mt5_tail_calls"
        )
        metric_name = (
            "full_history_calls" if fetch_kind == "full" else "tail_calls"
        )
        for timeframe, bars in bars_by_timeframe.items():
            metrics["copy_rates_calls"] += 1
            metrics[metric_name] += 1
            metrics["bars_requested"] += bars
            safe_performance_call(
                performance_tracker,
                "increment",
                "mt5_copy_rates_calls",
            )
            safe_performance_call(
                performance_tracker,
                "increment",
                counter_name,
            )
            try:
                candles = self.load_ohlcv(
                    broker_symbol,
                    timeframe,
                    bars,
                    True,
                )
            except Exception as exc:
                raise RuntimeError(
                    f"Khong lay duoc OHLCV cho {broker_symbol} "
                    f"{timeframe}: {exc}"
                ) from exc
            results[timeframe] = candles
            metrics["bars_received"] += len(candles)
        return results, metrics

    @staticmethod
    def _stage_tail_merge(
        identities: dict[str, CacheIdentity],
        bars_by_timeframe: dict[str, int],
        lookups: dict[str, Any],
        tails: dict[str, list[Candle]],
    ) -> dict[str, Any]:
        """Validate every tail on a staging cache before committing any one."""

        staging = CandleHistoryCache()
        for timeframe, identity in identities.items():
            seeded = staging.store_full(
                identity,
                lookups[timeframe].candles,
                expected_interval=_PRIMARY_TIMEFRAME_INTERVALS[timeframe],
                max_count=bars_by_timeframe[timeframe],
            )
            if seeded.requires_full_reload:
                return {timeframe: seeded}
        return {
            timeframe: staging.merge_tail(
                identity,
                tails[timeframe],
                expected_interval=_PRIMARY_TIMEFRAME_INTERVALS[timeframe],
                max_count=bars_by_timeframe[timeframe],
            )
            for timeframe, identity in identities.items()
        }

    def _commit_history_snapshots(
        self,
        identities: dict[str, CacheIdentity],
        bars_by_timeframe: dict[str, int],
        candles_by_timeframe: dict[str, list[Candle]],
    ) -> dict[str, list[Candle]]:
        """Validate all histories first, then replace the live cache entries."""

        staging = CandleHistoryCache()
        validated: dict[str, list[Candle]] = {}
        for timeframe, identity in identities.items():
            result = staging.store_full(
                identity,
                candles_by_timeframe[timeframe],
                expected_interval=_PRIMARY_TIMEFRAME_INTERVALS[timeframe],
                max_count=bars_by_timeframe[timeframe],
            )
            if result.requires_full_reload:
                raise RuntimeError(
                    f"MT5 returned invalid {timeframe} candle history."
                )
            validated[timeframe] = result.candles

        committed: dict[str, list[Candle]] = {}
        for timeframe, identity in identities.items():
            result = self._history_cache.store_full(
                identity,
                validated[timeframe],
                expected_interval=_PRIMARY_TIMEFRAME_INTERVALS[timeframe],
                max_count=bars_by_timeframe[timeframe],
            )
            if result.requires_full_reload:
                raise RuntimeError(
                    f"Could not commit {timeframe} MT5 history cache."
                )
            committed[timeframe] = result.candles
        return committed

    @staticmethod
    def _history_fallback_status(
        reasons: list[CacheFallbackReason | None],
    ) -> str:
        if CacheFallbackReason.GAP_DETECTED in reasons:
            return "full_reload_gap"
        if CacheFallbackReason.IDENTITY_CHANGED in reasons:
            return "full_reload_identity_change"
        return "full_reload_validation_failure"

    @staticmethod
    def _combine_fetch_metrics(
        first: dict[str, int],
        second: dict[str, int],
    ) -> dict[str, int]:
        return {
            key: int(first.get(key, 0)) + int(second.get(key, 0))
            for key in set(first) | set(second)
        }

    # -- DataProvider interface: trading ------------------------------------

    @_serialized_mt5_operation
    def place_market_order_unified(
        self,
        *,
        symbol: str,
        broker_symbol: str,
        side: str,
        volume: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "AI Market Analyst",
    ) -> OrderResult:
        """DataProvider-compatible wrapper around :meth:`place_market_order`."""
        mt5_result = self.place_market_order(
            symbol=symbol,
            broker_symbol=broker_symbol,
            side=side,
            volume=volume,
            stop_loss=stop_loss,
            take_profit=take_profit,
            comment=comment,
        )
        return OrderResult(
            success=mt5_result.success,
            symbol=mt5_result.symbol,
            broker_symbol=mt5_result.broker_symbol,
            side=mt5_result.side,
            volume=mt5_result.volume,
            price=mt5_result.price,
            stop_loss=mt5_result.stop_loss,
            take_profit=mt5_result.take_profit,
            order_id=mt5_result.order_id,
            retcode=mt5_result.retcode,
            message=mt5_result.message,
        )

    @_serialized_mt5_operation
    def symbol_data_quality(self, display_symbol: str, broker_symbol: str) -> dict[str, Any]:
        self.connect()
        status = self.mt5_connection_status()
        spread_points = None
        spread_price = None
        spread_status = "unknown"
        contract_size = None
        volume_min = None
        volume_max = None
        volume_step = None
        warning = None
        try:
            import MetaTrader5 as mt5

            info = mt5.symbol_info(broker_symbol)
            if info:
                spread_points = getattr(info, "spread", None)
                contract_size = getattr(info, "trade_contract_size", None)
                volume_min = getattr(info, "volume_min", None)
                volume_max = getattr(info, "volume_max", None)
                volume_step = getattr(info, "volume_step", None)
                point_val = getattr(info, "point", None)
                if spread_points is not None and point_val is not None:
                    spread_price = spread_points * point_val
                spread_status = "normal" if spread_points is not None and spread_points <= 50 else "abnormal"
        except Exception as exc:  # pragma: no cover - defensive around MT5 native API.
            warning = str(exc)

        return {
            "price_source": "MT5",
            "terminal_connected": status.terminal_connected,
            "broker_logged_in": status.logged_in,
            "broker": status.broker,
            "display_symbol": display_symbol,
            "broker_symbol": broker_symbol,
            "spread_points": spread_points,
            "spread_price": spread_price,
            "spread_status": spread_status,
            "contract_size": contract_size,
            "volume_min": volume_min,
            "volume_max": volume_max,
            "volume_step": volume_step,
            "warning": warning,
        }

    @_serialized_mt5_operation
    def server_time_utc(self) -> datetime | None:
        """Trả về thời gian UTC từ MT5 server, hoặc None nếu không lấy được."""
        try:
            import MetaTrader5 as mt5
            # Assume connected
            symbols = mt5.symbols_get()
            if symbols:
                tick = mt5.symbol_info_tick(symbols[0].name)
                if tick and tick.time:
                    return datetime.fromtimestamp(tick.time, tz=timezone.utc)
            return datetime.now(timezone.utc)
        except Exception:
            return None

    @_serialized_mt5_operation
    def quote_to_usd_rate(self, quote_currency: str) -> float | None:
        """Trả về tỷ giá quy đổi từ quote_currency sang USD, hoặc None nếu không lấy được.

        Results are cached per currency for the lifetime of this MT5Service instance."""
        if quote_currency == "USD":
            return 1.0
        if quote_currency in self._quote_usd_cache:
            return self._quote_usd_cache[quote_currency]
        try:
            import MetaTrader5 as mt5
            # Assume connected
            for pair_name in (quote_currency + "USD", "USD" + quote_currency):
                tick = mt5.symbol_info_tick(pair_name)
                if tick is None:
                    symbols = mt5.symbols_get()
                    for sym in (symbols or []):
                        name = getattr(sym, "name", "")
                        if name.upper().startswith(pair_name.upper()):
                            mt5.symbol_select(name, True)
                            tick = mt5.symbol_info_tick(name)
                            break
                if tick and tick.bid:
                    rate = float(tick.bid)
                    result = rate if pair_name.startswith(quote_currency) else 1.0 / rate
                    self._quote_usd_cache[quote_currency] = result
                    return result
            self._quote_usd_cache[quote_currency] = None
            return None
        except Exception:
            self._quote_usd_cache[quote_currency] = None
            return None

    @_serialized_mt5_operation
    def has_open_position_or_order(self, broker_symbol: str) -> bool:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return False
        # Assume connected

        positions = mt5.positions_get(symbol=broker_symbol)
        if positions:
            return True
        orders = mt5.orders_get(symbol=broker_symbol)
        return bool(orders)

    @_serialized_mt5_operation
    def get_live_price(self, broker_symbol: str, side: str) -> float | None:
        """Return the current bid/ask tick price for *broker_symbol* and *side*.

        Returns ``tick.ask`` for ``"buy"``, ``tick.bid`` for ``"sell"``,
        or ``None`` if MT5 is unavailable or the tick cannot be fetched.
        """
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return None
        tick = mt5.symbol_info_tick(broker_symbol)
        if not tick:
            return None
        side_lower = str(side).strip().lower()
        if side_lower == "buy":
            return float(tick.ask) if tick.ask else None
        if side_lower == "sell":
            return float(tick.bid) if tick.bid else None
        return None

    @_serialized_mt5_operation
    def place_market_order(
        self,
        *,
        symbol: str,
        broker_symbol: str,
        side: str,
        volume: float,
        stop_loss: float,
        take_profit: float,
        comment: str = "AI Market Analyst",
    ) -> MT5OrderResult:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return MT5OrderResult(False, symbol, broker_symbol, side, volume, message="Chưa cài package MetaTrader5.")

        # Assume connected

        if self.has_open_position_or_order(broker_symbol):
            return MT5OrderResult(False, symbol, broker_symbol, side, volume, message="Đã có lệnh/position cho mã này, không vào thêm.")

        if not mt5.symbol_select(broker_symbol, True):
            return MT5OrderResult(False, symbol, broker_symbol, side, volume, message=f"Không chọn được mã {broker_symbol}.")

        info = mt5.symbol_info(broker_symbol)
        tick = mt5.symbol_info_tick(broker_symbol)
        if not tick:
            return MT5OrderResult(False, symbol, broker_symbol, side, volume, message=f"Không lấy được giá hiện tại cho {broker_symbol}.")

        normalized_side = side.strip().lower()
        if normalized_side == "buy":
            order_type = mt5.ORDER_TYPE_BUY
            price = float(tick.ask)
        elif normalized_side == "sell":
            order_type = mt5.ORDER_TYPE_SELL
            price = float(tick.bid)
        else:
            return MT5OrderResult(False, symbol, broker_symbol, side, volume, message=f"Hướng vào lệnh không hợp lệ: {side}.")

        normalized_volume = self._normalize_volume(volume, info)
        if normalized_volume <= 0:
            return MT5OrderResult(False, symbol, broker_symbol, side, volume, message="Lot không hợp lệ sau khi chuẩn hóa theo broker.")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": broker_symbol,
            "volume": normalized_volume,
            "type": order_type,
            "price": price,
            "sl": float(stop_loss),
            "tp": float(take_profit),
            "deviation": 20,
            "magic": 260609,
            "comment": comment[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": self._order_filling(mt5, info),
        }
        result = mt5.order_send(request)
        retcode = getattr(result, "retcode", None) if result else None
        success_codes = {
            getattr(mt5, "TRADE_RETCODE_DONE", None),
            getattr(mt5, "TRADE_RETCODE_PLACED", None),
            getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", None),
        }
        success = retcode in success_codes
        message = getattr(result, "comment", "") if result else "MT5 không trả kết quả order_send."
        order_id = getattr(result, "order", None) or getattr(result, "deal", None) if result else None
        return MT5OrderResult(
            success=success,
            symbol=symbol,
            broker_symbol=broker_symbol,
            side=normalized_side,
            volume=normalized_volume,
            price=price,
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            order_id=int(order_id) if order_id else None,
            retcode=int(retcode) if retcode is not None else None,
            message=str(message or ("Đã gửi lệnh thành công." if success else "MT5 từ chối lệnh.")),
        )

    def app_symbol_for_broker_symbol(self, broker_symbol: str) -> str:
        normalized = self._normalize_symbol_name(broker_symbol)
        for app_symbol in self.symbol_profiles:
            aliases = self.aliases_for(app_symbol) + [app_symbol.replace("/", "")]
            if any(self._normalize_symbol_name(alias) == normalized for alias in aliases):
                return app_symbol
        return broker_symbol

    @_serialized_mt5_operation
    def closed_trade_history(self, *, start: datetime, end: datetime) -> list[dict[str, object]]:
        """Return closed MT5 positions grouped into journal-ready trades."""
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("Chưa cài package MetaTrader5.") from exc

        # Assume connected

        start_utc = start.astimezone(timezone.utc) if start.tzinfo else start.replace(tzinfo=timezone.utc)
        end_utc = end.astimezone(timezone.utc) if end.tzinfo else end.replace(tzinfo=timezone.utc)
        deals = mt5.history_deals_get(start_utc, end_utc)
        if deals is None:
            error_code, error_message = mt5.last_error()
            raise RuntimeError(error_message or f"Không lấy được lịch sử deal MT5 ({error_code}).")
        return self._closed_trades_from_deals(mt5, list(deals))

    @_serialized_mt5_operation
    def closed_trade_history_recent(self, days: int = 90) -> list[dict[str, object]]:
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, int(days)))
        return self.closed_trade_history(start=start, end=end)

    # ------------------------------------------------------------------
    # Position & order management
    # ------------------------------------------------------------------
    @_serialized_mt5_operation
    def positions_snapshot(self) -> PositionsSnapshot:
        """Return an account-scoped snapshot of open MT5 positions.

        A broker error is represented as ``UNAVAILABLE``, never as a confirmed
        empty collection.  This lets reconciliation code avoid deleting live
        protection state during a transient terminal failure.
        """

        observed_at = datetime.now(timezone.utc)
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return PositionsSnapshot(
                SnapshotStatus.UNAVAILABLE,
                None,
                (),
                observed_at,
                message="MetaTrader5 package is not installed.",
            )

        try:
            account, account_error = self._account_identity(mt5)
            if account is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PositionsSnapshot(
                    SnapshotStatus.UNAVAILABLE,
                    None,
                    (),
                    observed_at,
                    error_code,
                    account_error or error_message or "MT5 account identity is unavailable.",
                )

            raw_positions = mt5.positions_get()
            if raw_positions is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PositionsSnapshot(
                    SnapshotStatus.UNAVAILABLE,
                    account,
                    (),
                    observed_at,
                    error_code,
                    error_message or "MT5 positions query is unavailable.",
                )

            positions: list[BrokerPosition] = []
            metadata_cache: dict[str, BrokerSymbolMetadata] = {}
            for raw_position in raw_positions:
                broker_symbol = str(getattr(raw_position, "symbol", "") or "")
                metadata = metadata_cache.get(broker_symbol)
                if metadata is None:
                    metadata = self._broker_symbol_metadata(mt5, broker_symbol)
                    metadata_cache[broker_symbol] = metadata
                position_id = int(getattr(raw_position, "ticket", 0) or 0)
                positions.append(
                    BrokerPosition(
                        position_id=position_id,
                        broker_symbol=broker_symbol,
                        app_symbol=self.app_symbol_for_broker_symbol(broker_symbol),
                        side="buy" if int(getattr(raw_position, "type", 0) or 0) == 0 else "sell",
                        volume=float(getattr(raw_position, "volume", 0) or 0),
                        open_price=float(getattr(raw_position, "price_open", 0) or 0),
                        current_price=float(getattr(raw_position, "price_current", 0) or 0),
                        sl=float(getattr(raw_position, "sl", 0) or 0),
                        tp=float(getattr(raw_position, "tp", 0) or 0),
                        profit=float(getattr(raw_position, "profit", 0) or 0),
                        swap=float(getattr(raw_position, "swap", 0) or 0),
                        commission=float(getattr(raw_position, "commission", 0) or 0),
                        magic=int(getattr(raw_position, "magic", 0) or 0),
                        comment=str(getattr(raw_position, "comment", "") or ""),
                        open_time=int(getattr(raw_position, "time", 0) or 0),
                        identifier=int(getattr(raw_position, "identifier", 0) or position_id),
                        symbol_metadata=metadata,
                    )
                )

            return PositionsSnapshot(
                SnapshotStatus.AVAILABLE,
                account,
                tuple(positions),
                observed_at,
            )
        except Exception as exc:
            error_code, error_message = self._last_mt5_error(mt5)
            return PositionsSnapshot(
                SnapshotStatus.UNAVAILABLE,
                None,
                (),
                observed_at,
                error_code,
                str(exc) or error_message or "MT5 positions query failed.",
            )

    @_serialized_mt5_operation
    def pending_orders_snapshot(self) -> PendingOrdersSnapshot:
        """Return an account-scoped snapshot of pending MT5 orders."""

        observed_at = datetime.now(timezone.utc)
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return PendingOrdersSnapshot(
                SnapshotStatus.UNAVAILABLE,
                None,
                (),
                observed_at,
                message="MetaTrader5 package is not installed.",
            )

        try:
            account, account_error = self._account_identity(mt5)
            if account is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PendingOrdersSnapshot(
                    SnapshotStatus.UNAVAILABLE,
                    None,
                    (),
                    observed_at,
                    error_code,
                    account_error or error_message or "MT5 account identity is unavailable.",
                )

            raw_orders = mt5.orders_get()
            if raw_orders is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PendingOrdersSnapshot(
                    SnapshotStatus.UNAVAILABLE,
                    account,
                    (),
                    observed_at,
                    error_code,
                    error_message or "MT5 pending-orders query is unavailable.",
                )

            type_map = self._pending_order_type_map(mt5)
            orders: list[BrokerPendingOrder] = []
            metadata_cache: dict[str, BrokerSymbolMetadata] = {}
            for raw_order in raw_orders:
                raw_type = int(getattr(raw_order, "type", 0) or 0)
                broker_symbol = str(getattr(raw_order, "symbol", "") or "")
                metadata = metadata_cache.get(broker_symbol)
                if metadata is None:
                    metadata = self._broker_symbol_metadata(mt5, broker_symbol)
                    metadata_cache[broker_symbol] = metadata
                volume_initial = float(getattr(raw_order, "volume_initial", 0) or 0)
                volume_current = float(getattr(raw_order, "volume_current", 0) or 0)
                orders.append(
                    BrokerPendingOrder(
                        order_id=int(getattr(raw_order, "ticket", 0) or 0),
                        broker_symbol=broker_symbol,
                        app_symbol=self.app_symbol_for_broker_symbol(broker_symbol),
                        order_type=type_map.get(raw_type, f"unknown_{raw_type}"),
                        raw_order_type=raw_type,
                        volume=volume_current or volume_initial,
                        volume_initial=volume_initial,
                        price=float(getattr(raw_order, "price_open", 0) or 0),
                        sl=float(getattr(raw_order, "sl", 0) or 0),
                        tp=float(getattr(raw_order, "tp", 0) or 0),
                        magic=int(getattr(raw_order, "magic", 0) or 0),
                        comment=str(getattr(raw_order, "comment", "") or ""),
                        setup_time=int(getattr(raw_order, "time_setup", 0) or 0),
                        expiration_time=int(getattr(raw_order, "time_expiration", 0) or 0),
                        symbol_metadata=metadata,
                        stoplimit_price=float(
                            getattr(raw_order, "price_stoplimit", 0) or 0
                        ),
                        type_time=int(getattr(raw_order, "type_time", 0) or 0),
                    )
                )

            return PendingOrdersSnapshot(
                SnapshotStatus.AVAILABLE,
                account,
                tuple(orders),
                observed_at,
            )
        except Exception as exc:
            error_code, error_message = self._last_mt5_error(mt5)
            return PendingOrdersSnapshot(
                SnapshotStatus.UNAVAILABLE,
                None,
                (),
                observed_at,
                error_code,
                str(exc) or error_message or "MT5 pending-orders query failed.",
            )

    @_serialized_mt5_operation
    def symbol_tick(self, broker_symbol: str) -> TickSnapshot:
        """Return a serialized, account-scoped bid/ask snapshot."""

        observed_at = datetime.now(timezone.utc)
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return TickSnapshot(
                SnapshotStatus.UNAVAILABLE,
                None,
                None,
                observed_at,
                message="MetaTrader5 package is not installed.",
            )

        try:
            account, account_error = self._account_identity(mt5)
            if account is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return TickSnapshot(
                    SnapshotStatus.UNAVAILABLE,
                    None,
                    None,
                    observed_at,
                    error_code,
                    account_error or error_message or "MT5 account identity is unavailable.",
                )
            raw_tick = mt5.symbol_info_tick(broker_symbol)
            if raw_tick is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return TickSnapshot(
                    SnapshotStatus.UNAVAILABLE,
                    account,
                    None,
                    observed_at,
                    error_code,
                    error_message or f"Current tick for {broker_symbol} is unavailable.",
                )
            return TickSnapshot(
                SnapshotStatus.AVAILABLE,
                account,
                BrokerTick(
                    broker_symbol=str(broker_symbol),
                    bid=float(getattr(raw_tick, "bid", 0) or 0),
                    ask=float(getattr(raw_tick, "ask", 0) or 0),
                    time=int(getattr(raw_tick, "time", 0) or 0),
                    time_msc=int(getattr(raw_tick, "time_msc", 0) or 0),
                ),
                observed_at,
            )
        except Exception as exc:
            error_code, error_message = self._last_mt5_error(mt5)
            return TickSnapshot(
                SnapshotStatus.UNAVAILABLE,
                None,
                None,
                observed_at,
                error_code,
                str(exc) or error_message or "MT5 tick query failed.",
            )

    @_serialized_mt5_operation
    def reconcile_open_position(
        self,
        broker_symbol: str,
        *,
        expected_ticket: int | None = None,
        magic: int | None = 260609,
        comment_prefix: str | None = "AMA",
        expected_side: str | None = None,
        expected_volume: float | None = None,
        opened_after: datetime | int | float | None = None,
    ) -> BrokerPosition | None:
        """Find a broker position without treating an order/deal id as its ticket.

        Candidates are first constrained by broker/app symbol alias, magic,
        comment prefix, optional side/volume, and optional open time.  Only then
        may an exact position ticket win.  This prevents an order/deal id that
        happens to match an unrelated position ticket bypassing correlation.
        The newest correlated position is the fallback. ``None`` also covers an
        unavailable snapshot; callers that need to distinguish that state
        should call :meth:`positions_snapshot` directly.
        """

        snapshot = self.positions_snapshot()
        if not snapshot.available:
            return None
        expected_symbol = str(broker_symbol or "").strip().casefold()
        if not expected_symbol:
            return None
        normalized_symbol = self._normalize_symbol_name(expected_symbol)
        candidates = [
            position
            for position in snapshot.positions
            if (
                position.broker_symbol.casefold() == expected_symbol
                or position.app_symbol.casefold() == expected_symbol
                or self._normalize_symbol_name(position.broker_symbol)
                == normalized_symbol
                or self._normalize_symbol_name(position.app_symbol)
                == normalized_symbol
            )
        ]
        if magic is not None:
            candidates = [position for position in candidates if position.magic == int(magic)]
        if comment_prefix:
            normalized_prefix = " ".join(str(comment_prefix).split()).casefold()

            def comment_correlates(comment: str) -> bool:
                normalized_comment = " ".join(comment.split()).casefold()
                if normalized_comment.startswith(normalized_prefix):
                    return True
                # Some brokers truncate order comments.  Accept a truncated
                # expected correlation only when enough entropy remains; a
                # generic short label such as "AMA" cannot win this branch.
                return (
                    len(normalized_comment) >= 12
                    and normalized_prefix.startswith(normalized_comment)
                )

            candidates = [
                position
                for position in candidates
                if comment_correlates(position.comment)
            ]
        if expected_side is not None:
            normalized_side = str(expected_side).strip().casefold()
            if normalized_side not in {"buy", "sell"}:
                return None
            candidates = [
                position
                for position in candidates
                if position.side.casefold() == normalized_side
            ]
        if expected_volume is not None:
            requested_volume = self._optional_float(expected_volume)
            if requested_volume is None or requested_volume <= 0:
                return None
            candidates = [
                position
                for position in candidates
                if abs(position.volume - requested_volume)
                <= max(
                    float(position.symbol_metadata.volume_step or 0) / 2,
                    1e-9,
                )
            ]
        if opened_after is not None:
            opened_after_timestamp = self._timestamp(opened_after)
            if opened_after_timestamp is None:
                return None
            candidates = [
                position
                for position in candidates
                if position.open_time >= opened_after_timestamp
            ]
        if expected_ticket is not None:
            exact = next(
                (
                    position
                    for position in candidates
                    if position.position_id == int(expected_ticket)
                ),
                None,
            )
            if exact is not None:
                return exact
        return max(candidates, key=lambda position: position.open_time, default=None)

    @_serialized_mt5_operation
    def get_open_positions(self) -> list[dict[str, object]]:
        """Return all currently open positions from MT5."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []
        try:
            raw = mt5.positions_get()
            if raw is None:
                return []
            result: list[dict[str, object]] = []
            for pos in raw:
                symbol = getattr(pos, "symbol", "")
                result.append({
                    "position_id": int(getattr(pos, "ticket", 0)),
                    "symbol": str(symbol),
                    "side": "buy" if getattr(pos, "type", 0) == 0 else "sell",
                    "volume": float(getattr(pos, "volume", 0)),
                    "open_price": float(getattr(pos, "price_open", 0)),
                    "current_price": float(getattr(pos, "price_current", 0)),
                    "sl": float(getattr(pos, "sl", 0) or 0),
                    "tp": float(getattr(pos, "tp", 0) or 0),
                    "profit": float(getattr(pos, "profit", 0)),
                    "swap": float(getattr(pos, "swap", 0)),
                    "commission": float(getattr(pos, "commission", 0)),
                    "comment": str(getattr(pos, "comment", "")),
                    "open_time": int(getattr(pos, "time", 0)),
                })
            return result
        except Exception:
            return []

    @_serialized_mt5_operation
    def get_pending_orders(self) -> list[dict[str, object]]:
        """Return all pending (limit/stop) orders from MT5."""
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []
        try:
            raw = mt5.orders_get()
            if raw is None:
                return []
            result: list[dict[str, object]] = []
            # MT5 order types
            _type_map = {
                2: "buy_limit",
                3: "sell_limit",
                4: "buy_stop",
                5: "sell_stop",
                6: "buy_stop_limit",
                7: "sell_stop_limit",
            }
            for order in raw:
                otype = int(getattr(order, "type", 0))
                result.append({
                    "order_id": int(getattr(order, "ticket", 0)),
                    "symbol": str(getattr(order, "symbol", "")),
                    "type": _type_map.get(otype, f"unknown_{otype}"),
                    "volume": float(getattr(order, "volume_current", 0) or getattr(order, "volume_initial", 0)),
                    "price": float(getattr(order, "price_open", 0)),
                    "sl": float(getattr(order, "sl", 0) or 0),
                    "tp": float(getattr(order, "tp", 0) or 0),
                    "comment": str(getattr(order, "comment", "")),
                    "setup_time": int(getattr(order, "time_setup", 0)),
                })
            return result
        except Exception:
            return []

    @_serialized_mt5_operation
    def close_position(
        self,
        position_id: int,
        *,
        volume: float | None = None,
        comment: str = "",
        expected_account_fingerprint: str | None = None,
        expected_broker_symbol: str | None = None,
    ) -> dict[str, object]:
        """Close a position and verify the resulting broker state.

        The compatibility ``success`` field is true only when the position is
        confirmed fully closed.  A partial execution keeps ``success`` false,
        reports ``status='partial'``, and exposes the remaining volume.
        """

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return PositionCloseResult(
                OperationStatus.UNKNOWN,
                position_id,
                message="MetaTrader5 package is not installed.",
            ).to_dict()

        try:
            initial_query = mt5.positions_get(ticket=position_id)
            if initial_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PositionCloseResult(
                    OperationStatus.UNKNOWN,
                    position_id,
                    error_code=error_code,
                    message=error_message or "MT5 position query is unavailable.",
                ).to_dict()

            position = self._find_position(initial_query, position_id)
            if position is None:
                return PositionCloseResult(
                    OperationStatus.REJECTED,
                    position_id,
                    message=f"Position ticket={position_id} was not found.",
                ).to_dict()

            broker_symbol = str(getattr(position, "symbol", "") or "")
            precondition_error = self._mutation_precondition_error(
                mt5,
                expected_account_fingerprint=expected_account_fingerprint,
                expected_broker_symbol=expected_broker_symbol,
                actual_broker_symbol=broker_symbol,
            )
            if precondition_error:
                return PositionCloseResult(
                    OperationStatus.REJECTED,
                    position_id,
                    broker_symbol=broker_symbol,
                    remaining_volume=float(getattr(position, "volume", 0) or 0),
                    message=precondition_error,
                    precondition_failed=True,
                ).to_dict()
            position_volume = float(getattr(position, "volume", 0) or 0)
            requested_volume = position_volume if volume is None else float(volume)
            if not isfinite(requested_volume) or requested_volume <= 0:
                return PositionCloseResult(
                    OperationStatus.REJECTED,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_volume=requested_volume,
                    remaining_volume=position_volume,
                    message="Close volume must be greater than zero.",
                ).to_dict()

            symbol_info = mt5.symbol_info(broker_symbol)
            close_volume = self._normalize_volume(
                min(requested_volume, position_volume),
                symbol_info,
            )
            if close_volume <= 0:
                return PositionCloseResult(
                    OperationStatus.REJECTED,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_volume=requested_volume,
                    remaining_volume=position_volume,
                    message="Close volume is invalid after broker normalization.",
                ).to_dict()

            tick = mt5.symbol_info_tick(broker_symbol)
            if tick is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PositionCloseResult(
                    OperationStatus.UNKNOWN,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_volume=close_volume,
                    remaining_volume=position_volume,
                    error_code=error_code,
                    message=error_message or f"Current price for {broker_symbol} is unavailable.",
                ).to_dict()

            position_type = int(getattr(position, "type", 0) or 0)
            close_price = float(tick.bid) if position_type == 0 else float(tick.ask)
            close_type = mt5.ORDER_TYPE_SELL if position_type == 0 else mt5.ORDER_TYPE_BUY
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": broker_symbol,
                "volume": close_volume,
                "type": close_type,
                "position": position_id,
                "price": close_price,
                "deviation": 20,
                "magic": 260609,
                "comment": (comment or "AMA Close")[:31],
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": self._order_filling(mt5, symbol_info),
            }
            send_result = mt5.order_send(request)
            retcode = getattr(send_result, "retcode", None) if send_result else None
            accepted_codes = self._retcodes(
                mt5,
                "TRADE_RETCODE_DONE",
                "TRADE_RETCODE_PLACED",
                "TRADE_RETCODE_DONE_PARTIAL",
            )
            broker_message = (
                str(getattr(send_result, "comment", "") or "")
                if send_result
                else ""
            )

            remaining_query = mt5.positions_get(ticket=position_id)
            if remaining_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PositionCloseResult(
                    OperationStatus.UNKNOWN,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_volume=close_volume,
                    price=close_price,
                    retcode=self._optional_int(retcode),
                    order_id=self._result_id(send_result, "order"),
                    deal_id=self._result_id(send_result, "deal"),
                    error_code=error_code,
                    message=error_message or broker_message or "Close request could not be verified.",
                ).to_dict()

            remaining_position = self._find_position(remaining_query, position_id)
            if remaining_position is None:
                status = OperationStatus.CONFIRMED
                remaining_volume = 0.0
                executed_volume = position_volume
                default_message = "Position close was confirmed by MT5."
            else:
                remaining_volume = float(getattr(remaining_position, "volume", 0) or 0)
                executed_volume = max(0.0, position_volume - remaining_volume)
                volume_tolerance = max(
                    float(getattr(symbol_info, "volume_step", 0) or 0) / 2,
                    1e-9,
                )
                if executed_volume > volume_tolerance:
                    status = OperationStatus.PARTIAL
                    default_message = "Position was partially closed; remaining volume is still open."
                elif retcode not in accepted_codes:
                    status = OperationStatus.REJECTED
                    default_message = "MT5 rejected the close request."
                else:
                    status = OperationStatus.UNKNOWN
                    default_message = "MT5 accepted the request but the position state was unchanged."

            return PositionCloseResult(
                status,
                position_id,
                broker_symbol=broker_symbol,
                requested_volume=close_volume,
                executed_volume=executed_volume,
                remaining_volume=remaining_volume,
                price=close_price,
                retcode=self._optional_int(retcode),
                order_id=self._result_id(send_result, "order"),
                deal_id=self._result_id(send_result, "deal"),
                message=broker_message or default_message,
            ).to_dict()
        except Exception as exc:
            error_code, _error_message = self._last_mt5_error(mt5)
            return PositionCloseResult(
                OperationStatus.UNKNOWN,
                position_id,
                error_code=error_code,
                message=str(exc),
            ).to_dict()

    @_serialized_mt5_operation
    def modify_position_sltp(
        self,
        position_id: int,
        *,
        sl: float | None = None,
        tp: float | None = None,
        expected_sl: float | None = None,
        expected_tp: float | None = None,
        enforce_snapshot_precondition: bool = False,
        expected_account_fingerprint: str | None = None,
        expected_broker_symbol: str | None = None,
    ) -> dict[str, object]:
        """Modify SL/TP while preserving omitted fields and verifying the result.

        Automatic management can opt into an optimistic snapshot precondition.
        In that mode a manual/EA edit observed after the engine snapshot aborts
        the request, so a stale trailing target cannot overwrite newer broker
        protection or TP state.
        """

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return PositionModifyResult(
                OperationStatus.UNKNOWN,
                position_id,
                message="MetaTrader5 package is not installed.",
            ).to_dict()

        try:
            initial_query = mt5.positions_get(ticket=position_id)
            if initial_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PositionModifyResult(
                    OperationStatus.UNKNOWN,
                    position_id,
                    error_code=error_code,
                    message=error_message or "MT5 position query is unavailable.",
                ).to_dict()

            position = self._find_position(initial_query, position_id)
            if position is None:
                return PositionModifyResult(
                    OperationStatus.REJECTED,
                    position_id,
                    message=f"Position ticket={position_id} was not found.",
                ).to_dict()

            broker_symbol = str(getattr(position, "symbol", "") or "")
            symbol_info = mt5.symbol_info(broker_symbol)
            current_sl = float(getattr(position, "sl", 0) or 0)
            current_tp = float(getattr(position, "tp", 0) or 0)
            precondition_error = self._mutation_precondition_error(
                mt5,
                expected_account_fingerprint=expected_account_fingerprint,
                expected_broker_symbol=expected_broker_symbol,
                actual_broker_symbol=broker_symbol,
            )
            if precondition_error:
                return PositionModifyResult(
                    OperationStatus.REJECTED,
                    position_id,
                    broker_symbol=broker_symbol,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    message=precondition_error,
                    precondition_failed=True,
                ).to_dict()
            requested_sl = (
                current_sl
                if sl is None
                else self._normalize_price(sl, symbol_info)
            )
            requested_tp = (
                current_tp
                if tp is None
                else self._normalize_price(tp, symbol_info)
            )

            if sl is None and tp is None:
                return PositionModifyResult(
                    OperationStatus.CONFIRMED,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    message="No SL/TP change was requested.",
                ).to_dict()

            if not self._has_price_normalization_metadata(symbol_info):
                return PositionModifyResult(
                    OperationStatus.REJECTED,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    message=(
                        "Symbol tick-size/digits metadata is unavailable; the "
                        "SL/TP request cannot be normalized safely."
                    ),
                ).to_dict()

            if enforce_snapshot_precondition:
                normalized_expected_sl = self._normalize_price(
                    0.0 if expected_sl is None else expected_sl,
                    symbol_info,
                )
                normalized_expected_tp = self._normalize_price(
                    0.0 if expected_tp is None else expected_tp,
                    symbol_info,
                )
                if not self._prices_equal(
                    normalized_expected_sl,
                    current_sl,
                    symbol_info,
                ) or not self._prices_equal(
                    normalized_expected_tp,
                    current_tp,
                    symbol_info,
                ):
                    return PositionModifyResult(
                        OperationStatus.REJECTED,
                        position_id,
                        broker_symbol=broker_symbol,
                        requested_sl=requested_sl,
                        requested_tp=requested_tp,
                        effective_sl=current_sl,
                        effective_tp=current_tp,
                        message=(
                            "Broker SL/TP changed after the management snapshot; "
                            "the stale request was not sent."
                        ),
                        precondition_failed=True,
                    ).to_dict()

            sl_changed = sl is not None and not self._prices_equal(
                requested_sl,
                current_sl,
                symbol_info,
            )
            tp_changed = tp is not None and not self._prices_equal(
                requested_tp,
                current_tp,
                symbol_info,
            )
            if not sl_changed and not tp_changed:
                return PositionModifyResult(
                    OperationStatus.CONFIRMED,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    message="The requested SL/TP values already match MT5.",
                ).to_dict()

            constraint_error = self._validate_position_sltp_constraints(
                mt5,
                position,
                symbol_info,
                requested_sl=requested_sl,
                requested_tp=requested_tp,
                validate_sl=sl_changed,
                validate_tp=tp_changed,
            )
            if constraint_error:
                return PositionModifyResult(
                    OperationStatus.REJECTED,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    message=constraint_error,
                ).to_dict()

            request = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": broker_symbol,
                "position": position_id,
                # TRADE_ACTION_SLTP expects both fields.  Carrying forward the
                # omitted field prevents an SL-only update from clearing TP.
                "sl": requested_sl,
                "tp": requested_tp,
            }
            send_result = mt5.order_send(request)
            retcode = getattr(send_result, "retcode", None) if send_result else None
            accepted_codes = self._retcodes(
                mt5,
                "TRADE_RETCODE_DONE",
                "TRADE_RETCODE_PLACED",
            )
            broker_message = (
                str(getattr(send_result, "comment", "") or "")
                if send_result
                else ""
            )

            confirmed_query = mt5.positions_get(ticket=position_id)
            if confirmed_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PositionModifyResult(
                    OperationStatus.UNKNOWN,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    retcode=self._optional_int(retcode),
                    order_id=self._result_id(send_result, "order"),
                    deal_id=self._result_id(send_result, "deal"),
                    error_code=error_code,
                    message=error_message or broker_message or "SL/TP request could not be verified.",
                ).to_dict()

            confirmed_position = self._find_position(confirmed_query, position_id)
            if confirmed_position is None:
                return PositionModifyResult(
                    OperationStatus.UNKNOWN,
                    position_id,
                    broker_symbol=broker_symbol,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    retcode=self._optional_int(retcode),
                    order_id=self._result_id(send_result, "order"),
                    deal_id=self._result_id(send_result, "deal"),
                    message=broker_message or "Position disappeared before the SL/TP change could be verified.",
                ).to_dict()

            effective_sl = float(getattr(confirmed_position, "sl", 0) or 0)
            effective_tp = float(getattr(confirmed_position, "tp", 0) or 0)
            postcondition_met = self._prices_equal(
                effective_sl,
                requested_sl,
                symbol_info,
            ) and self._prices_equal(
                effective_tp,
                requested_tp,
                symbol_info,
            )
            if postcondition_met:
                status = OperationStatus.CONFIRMED
                default_message = "SL/TP change was confirmed by MT5."
            elif retcode not in accepted_codes:
                status = OperationStatus.REJECTED
                default_message = "MT5 rejected the SL/TP change."
            else:
                status = OperationStatus.UNKNOWN
                default_message = "MT5 accepted the request but the SL/TP postcondition was not confirmed."

            return PositionModifyResult(
                status,
                position_id,
                broker_symbol=broker_symbol,
                requested_sl=requested_sl,
                requested_tp=requested_tp,
                effective_sl=effective_sl,
                effective_tp=effective_tp,
                retcode=self._optional_int(retcode),
                order_id=self._result_id(send_result, "order"),
                deal_id=self._result_id(send_result, "deal"),
                message=broker_message or default_message,
            ).to_dict()
        except Exception as exc:
            error_code, _error_message = self._last_mt5_error(mt5)
            return PositionModifyResult(
                OperationStatus.UNKNOWN,
                position_id,
                error_code=error_code,
                message=str(exc),
            ).to_dict()

    @_serialized_mt5_operation
    def cancel_pending_order(
        self,
        order_id: int,
        *,
        expected_account_fingerprint: str | None = None,
        expected_broker_symbol: str | None = None,
    ) -> dict[str, object]:
        """Cancel a pending order and confirm that it left the active order book."""

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return PendingOrderCancelResult(
                OperationStatus.UNKNOWN,
                order_id,
                message="MetaTrader5 package is not installed.",
            ).to_dict()

        try:
            initial_query = mt5.orders_get(ticket=order_id)
            if initial_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PendingOrderCancelResult(
                    OperationStatus.UNKNOWN,
                    order_id,
                    error_code=error_code,
                    message=error_message or "MT5 pending-order query is unavailable.",
                ).to_dict()

            pending_order = self._find_pending_order(initial_query, order_id)
            if pending_order is None:
                return PendingOrderCancelResult(
                    OperationStatus.REJECTED,
                    order_id,
                    message=f"Pending order ticket={order_id} was not found.",
                ).to_dict()

            broker_symbol = str(getattr(pending_order, "symbol", "") or "")
            precondition_error = self._mutation_precondition_error(
                mt5,
                expected_account_fingerprint=expected_account_fingerprint,
                expected_broker_symbol=expected_broker_symbol,
                actual_broker_symbol=broker_symbol,
            )
            if precondition_error:
                return PendingOrderCancelResult(
                    OperationStatus.REJECTED,
                    order_id,
                    broker_symbol=broker_symbol,
                    message=precondition_error,
                    precondition_failed=True,
                ).to_dict()
            remove_action = self._optional_int(
                getattr(mt5, "TRADE_ACTION_REMOVE", None)
            )
            if remove_action is None:
                return PendingOrderCancelResult(
                    OperationStatus.REJECTED,
                    order_id,
                    broker_symbol=broker_symbol,
                    message="MT5 does not expose TRADE_ACTION_REMOVE.",
                ).to_dict()

            # REMOVE does not use an execution filling policy.  Supplying one can
            # make an otherwise valid cancel request broker-dependent.
            request = {
                "action": remove_action,
                "order": int(order_id),
                "symbol": broker_symbol,
            }
            send_result = mt5.order_send(request)
            retcode = self._optional_int(
                getattr(send_result, "retcode", None) if send_result else None
            )
            broker_message = (
                str(getattr(send_result, "comment", "") or "")
                if send_result
                else ""
            )

            confirmed_query = mt5.orders_get(ticket=order_id)
            if confirmed_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PendingOrderCancelResult(
                    OperationStatus.UNKNOWN,
                    order_id,
                    broker_symbol=broker_symbol,
                    retcode=retcode,
                    response_order_id=self._result_id(send_result, "order"),
                    error_code=error_code,
                    message=(
                        error_message
                        or broker_message
                        or "Pending-order cancellation could not be verified."
                    ),
                ).to_dict()

            remaining_order = self._find_pending_order(confirmed_query, order_id)
            accepted_codes = self._retcodes(
                mt5,
                "TRADE_RETCODE_DONE",
                "TRADE_RETCODE_PLACED",
                "TRADE_RETCODE_ORDER_CHANGED",
            )
            if remaining_order is None and retcode in accepted_codes:
                status = OperationStatus.CONFIRMED
                default_message = "Pending-order cancellation was confirmed by MT5."
            elif remaining_order is None:
                status = OperationStatus.UNKNOWN
                default_message = (
                    "The pending order left the order book, but MT5 did not "
                    "acknowledge this cancellation; it may have filled or expired."
                )
            elif retcode is not None and retcode not in accepted_codes:
                status = OperationStatus.REJECTED
                default_message = "MT5 rejected the pending-order cancellation."
            else:
                status = OperationStatus.UNKNOWN
                default_message = (
                    "MT5 did not confirm that the pending order was cancelled."
                )

            return PendingOrderCancelResult(
                status,
                order_id,
                broker_symbol=broker_symbol,
                retcode=retcode,
                response_order_id=self._result_id(send_result, "order"),
                message=broker_message or default_message,
            ).to_dict()
        except Exception as exc:
            error_code, _error_message = self._last_mt5_error(mt5)
            return PendingOrderCancelResult(
                OperationStatus.UNKNOWN,
                order_id,
                error_code=error_code,
                message=str(exc),
            ).to_dict()

    @_serialized_mt5_operation
    def modify_pending_order(
        self,
        order_id: int,
        *,
        price: float | None = None,
        sl: float | None = None,
        tp: float | None = None,
        expiration: datetime | int | float | None = None,
        expected_account_fingerprint: str | None = None,
        expected_broker_symbol: str | None = None,
    ) -> dict[str, object]:
        """Modify a pending order while preserving omitted broker fields.

        The returned compatibility dictionary reports success only after a
        second ``orders_get`` confirms every effective field.
        """

        try:
            import MetaTrader5 as mt5
        except ImportError:
            return PendingOrderModifyResult(
                OperationStatus.UNKNOWN,
                order_id,
                message="MetaTrader5 package is not installed.",
            ).to_dict()

        try:
            initial_query = mt5.orders_get(ticket=order_id)
            if initial_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PendingOrderModifyResult(
                    OperationStatus.UNKNOWN,
                    order_id,
                    error_code=error_code,
                    message=error_message or "MT5 pending-order query is unavailable.",
                ).to_dict()

            pending_order = self._find_pending_order(initial_query, order_id)
            if pending_order is None:
                return PendingOrderModifyResult(
                    OperationStatus.REJECTED,
                    order_id,
                    message=f"Pending order ticket={order_id} was not found.",
                ).to_dict()

            broker_symbol = str(getattr(pending_order, "symbol", "") or "")
            precondition_error = self._mutation_precondition_error(
                mt5,
                expected_account_fingerprint=expected_account_fingerprint,
                expected_broker_symbol=expected_broker_symbol,
                actual_broker_symbol=broker_symbol,
            )
            if precondition_error:
                return PendingOrderModifyResult(
                    OperationStatus.REJECTED,
                    order_id,
                    broker_symbol=broker_symbol,
                    message=precondition_error,
                    precondition_failed=True,
                ).to_dict()
            raw_order_type = int(getattr(pending_order, "type", -1))
            type_map = self._pending_order_type_map(mt5)
            order_type = type_map.get(raw_order_type, f"unknown_{raw_order_type}")
            if raw_order_type not in type_map:
                return PendingOrderModifyResult(
                    OperationStatus.REJECTED,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    message="Only limit, stop, and stop-limit orders can be modified.",
                ).to_dict()

            symbol_info = mt5.symbol_info(broker_symbol)
            current_price = float(getattr(pending_order, "price_open", 0) or 0)
            current_sl = float(getattr(pending_order, "sl", 0) or 0)
            current_tp = float(getattr(pending_order, "tp", 0) or 0)
            current_stoplimit = float(
                getattr(pending_order, "price_stoplimit", 0) or 0
            )
            current_expiration = int(
                getattr(pending_order, "time_expiration", 0) or 0
            )
            current_type_time = int(getattr(pending_order, "type_time", 0) or 0)

            if all(value is None for value in (price, sl, tp, expiration)):
                return PendingOrderModifyResult(
                    OperationStatus.CONFIRMED,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    requested_price=current_price,
                    requested_sl=current_sl,
                    requested_tp=current_tp,
                    requested_stoplimit=current_stoplimit,
                    requested_expiration=current_expiration,
                    requested_type_time=current_type_time,
                    effective_price=current_price,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    effective_stoplimit=current_stoplimit,
                    effective_expiration=current_expiration,
                    effective_type_time=current_type_time,
                    message="No pending-order change was requested.",
                ).to_dict()

            if not self._has_price_normalization_metadata(symbol_info):
                return PendingOrderModifyResult(
                    OperationStatus.REJECTED,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    effective_price=current_price,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    effective_stoplimit=current_stoplimit,
                    effective_expiration=current_expiration,
                    effective_type_time=current_type_time,
                    message=(
                        "Symbol tick-size/digits metadata is unavailable; the "
                        "pending-order request cannot be normalized safely."
                    ),
                ).to_dict()

            requested_price = (
                current_price
                if price is None
                else self._normalize_price(price, symbol_info)
            )
            requested_sl = (
                current_sl if sl is None else self._normalize_price(sl, symbol_info)
            )
            requested_tp = (
                current_tp if tp is None else self._normalize_price(tp, symbol_info)
            )
            requested_stoplimit = current_stoplimit
            requested_expiration = (
                current_expiration
                if expiration is None
                else self._normalize_expiration(expiration)
            )
            requested_type_time = current_type_time
            if expiration is not None:
                if requested_expiration == 0:
                    requested_type_time = int(getattr(mt5, "ORDER_TIME_GTC", 0))
                else:
                    specified_time = self._optional_int(
                        getattr(mt5, "ORDER_TIME_SPECIFIED", None)
                    )
                    if specified_time is None:
                        return PendingOrderModifyResult(
                            OperationStatus.REJECTED,
                            order_id,
                            broker_symbol=broker_symbol,
                            order_type=order_type,
                            raw_order_type=raw_order_type,
                            requested_expiration=requested_expiration,
                            message=(
                                "MT5 does not expose ORDER_TIME_SPECIFIED, so the "
                                "expiration change cannot be represented safely."
                            ),
                        ).to_dict()
                    requested_type_time = specified_time

            price_changed = not self._prices_equal(
                current_price,
                requested_price,
                symbol_info,
            )
            sl_changed = not self._prices_equal(current_sl, requested_sl, symbol_info)
            tp_changed = not self._prices_equal(current_tp, requested_tp, symbol_info)
            expiration_changed = current_expiration != requested_expiration
            type_time_changed = current_type_time != requested_type_time
            if not any(
                (
                    price_changed,
                    sl_changed,
                    tp_changed,
                    expiration_changed,
                    type_time_changed,
                )
            ):
                return PendingOrderModifyResult(
                    OperationStatus.CONFIRMED,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    requested_price=requested_price,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    requested_stoplimit=requested_stoplimit,
                    requested_expiration=requested_expiration,
                    requested_type_time=requested_type_time,
                    effective_price=current_price,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    effective_stoplimit=current_stoplimit,
                    effective_expiration=current_expiration,
                    effective_type_time=current_type_time,
                    message="The requested pending-order values already match MT5.",
                ).to_dict()

            constraint_error = self._validate_pending_order_constraints(
                mt5,
                raw_order_type=raw_order_type,
                broker_symbol=broker_symbol,
                symbol_info=symbol_info,
                price=requested_price,
                sl=requested_sl,
                tp=requested_tp,
                stoplimit=requested_stoplimit,
            )
            if constraint_error:
                return PendingOrderModifyResult(
                    OperationStatus.REJECTED,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    requested_price=requested_price,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    requested_stoplimit=requested_stoplimit,
                    requested_expiration=requested_expiration,
                    requested_type_time=requested_type_time,
                    effective_price=current_price,
                    effective_sl=current_sl,
                    effective_tp=current_tp,
                    effective_stoplimit=current_stoplimit,
                    effective_expiration=current_expiration,
                    effective_type_time=current_type_time,
                    message=constraint_error,
                ).to_dict()

            modify_action = self._optional_int(
                getattr(mt5, "TRADE_ACTION_MODIFY", None)
            )
            if modify_action is None:
                return PendingOrderModifyResult(
                    OperationStatus.REJECTED,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    message="MT5 does not expose TRADE_ACTION_MODIFY.",
                ).to_dict()

            request: dict[str, object] = {
                "action": modify_action,
                "order": int(order_id),
                "symbol": broker_symbol,
                "type": raw_order_type,
                "price": requested_price,
                "sl": requested_sl,
                "tp": requested_tp,
                "type_time": requested_type_time,
                "expiration": requested_expiration,
            }
            if order_type in {"buy_stop_limit", "sell_stop_limit"}:
                # The stop-limit leg is not editable through this compatibility
                # method, but it must be carried forward or MT5 can clear it.
                request["stoplimit"] = requested_stoplimit

            send_result = mt5.order_send(request)
            retcode = self._optional_int(
                getattr(send_result, "retcode", None) if send_result else None
            )
            broker_message = (
                str(getattr(send_result, "comment", "") or "")
                if send_result
                else ""
            )

            confirmed_query = mt5.orders_get(ticket=order_id)
            if confirmed_query is None:
                error_code, error_message = self._last_mt5_error(mt5)
                return PendingOrderModifyResult(
                    OperationStatus.UNKNOWN,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    requested_price=requested_price,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    requested_stoplimit=requested_stoplimit,
                    requested_expiration=requested_expiration,
                    requested_type_time=requested_type_time,
                    retcode=retcode,
                    response_order_id=self._result_id(send_result, "order"),
                    error_code=error_code,
                    message=(
                        error_message
                        or broker_message
                        or "Pending-order modification could not be verified."
                    ),
                ).to_dict()

            confirmed_order = self._find_pending_order(confirmed_query, order_id)
            if confirmed_order is None:
                return PendingOrderModifyResult(
                    OperationStatus.UNKNOWN,
                    order_id,
                    broker_symbol=broker_symbol,
                    order_type=order_type,
                    raw_order_type=raw_order_type,
                    requested_price=requested_price,
                    requested_sl=requested_sl,
                    requested_tp=requested_tp,
                    requested_stoplimit=requested_stoplimit,
                    requested_expiration=requested_expiration,
                    requested_type_time=requested_type_time,
                    retcode=retcode,
                    response_order_id=self._result_id(send_result, "order"),
                    message=(
                        broker_message
                        or "The pending order left the order book before the change was verified."
                    ),
                ).to_dict()

            effective_price = float(getattr(confirmed_order, "price_open", 0) or 0)
            effective_sl = float(getattr(confirmed_order, "sl", 0) or 0)
            effective_tp = float(getattr(confirmed_order, "tp", 0) or 0)
            effective_stoplimit = float(
                getattr(confirmed_order, "price_stoplimit", 0) or 0
            )
            effective_expiration = int(
                getattr(confirmed_order, "time_expiration", 0) or 0
            )
            effective_type_time = int(
                getattr(confirmed_order, "type_time", 0) or 0
            )
            confirmed_raw_type = int(getattr(confirmed_order, "type", -1))
            confirmed_symbol = str(getattr(confirmed_order, "symbol", "") or "")
            postcondition_met = (
                confirmed_raw_type == raw_order_type
                and confirmed_symbol == broker_symbol
                and self._prices_equal(
                    effective_price,
                    requested_price,
                    symbol_info,
                )
                and self._prices_equal(effective_sl, requested_sl, symbol_info)
                and self._prices_equal(effective_tp, requested_tp, symbol_info)
                and effective_expiration == requested_expiration
                and effective_type_time == requested_type_time
            )
            if order_type in {"buy_stop_limit", "sell_stop_limit"}:
                postcondition_met = postcondition_met and self._prices_equal(
                    effective_stoplimit,
                    requested_stoplimit,
                    symbol_info,
                )

            accepted_codes = self._retcodes(
                mt5,
                "TRADE_RETCODE_DONE",
                "TRADE_RETCODE_PLACED",
                "TRADE_RETCODE_ORDER_CHANGED",
            )
            if postcondition_met:
                status = OperationStatus.CONFIRMED
                default_message = "Pending-order change was confirmed by MT5."
            elif retcode is not None and retcode not in accepted_codes:
                status = OperationStatus.REJECTED
                default_message = "MT5 rejected the pending-order change."
            else:
                status = OperationStatus.UNKNOWN
                default_message = (
                    "MT5 did not confirm the pending-order postcondition."
                )

            return PendingOrderModifyResult(
                status,
                order_id,
                broker_symbol=broker_symbol,
                order_type=order_type,
                raw_order_type=raw_order_type,
                requested_price=requested_price,
                requested_sl=requested_sl,
                requested_tp=requested_tp,
                requested_stoplimit=requested_stoplimit,
                requested_expiration=requested_expiration,
                requested_type_time=requested_type_time,
                effective_price=effective_price,
                effective_sl=effective_sl,
                effective_tp=effective_tp,
                effective_stoplimit=effective_stoplimit,
                effective_expiration=effective_expiration,
                effective_type_time=effective_type_time,
                retcode=retcode,
                response_order_id=self._result_id(send_result, "order"),
                message=broker_message or default_message,
            ).to_dict()
        except (TypeError, ValueError, OverflowError) as exc:
            return PendingOrderModifyResult(
                OperationStatus.REJECTED,
                order_id,
                message=str(exc),
            ).to_dict()
        except Exception as exc:
            error_code, _error_message = self._last_mt5_error(mt5)
            return PendingOrderModifyResult(
                OperationStatus.UNKNOWN,
                order_id,
                error_code=error_code,
                message=str(exc),
            ).to_dict()

    def _account_identity(
        self,
        mt5_module,
    ) -> tuple[AccountIdentity | None, str]:
        try:
            account_info = mt5_module.account_info()
        except Exception as exc:
            return None, str(exc)
        if account_info is None:
            return None, "MT5 account information is unavailable."
        login = self._optional_int(getattr(account_info, "login", None))
        server = str(getattr(account_info, "server", "") or "").strip()
        broker = str(
            getattr(account_info, "company", "")
            or getattr(account_info, "broker", "")
            or ""
        ).strip()
        if login is None or not server or not broker:
            return None, "MT5 account identity is incomplete (broker/server/login required)."
        raw_trade_mode = self._optional_int(getattr(account_info, "trade_mode", None))
        trade_mode_map = {
            self._optional_int(getattr(mt5_module, "ACCOUNT_TRADE_MODE_DEMO", 0)): AccountTradeMode.DEMO,
            self._optional_int(getattr(mt5_module, "ACCOUNT_TRADE_MODE_CONTEST", 1)): AccountTradeMode.CONTEST,
            self._optional_int(getattr(mt5_module, "ACCOUNT_TRADE_MODE_REAL", 2)): AccountTradeMode.REAL,
        }
        trade_mode = trade_mode_map.get(raw_trade_mode, AccountTradeMode.UNKNOWN)
        raw_trade_allowed = getattr(account_info, "trade_allowed", None)
        trade_allowed = (
            bool(raw_trade_allowed) if raw_trade_allowed is not None else None
        )
        try:
            terminal_info = mt5_module.terminal_info()
        except Exception:
            terminal_info = None
        terminal_trade_allowed = (
            getattr(terminal_info, "trade_allowed", None)
            if terminal_info is not None
            else None
        )
        if terminal_trade_allowed is not None:
            trade_allowed = bool(terminal_trade_allowed) and (
                trade_allowed is not False
            )
        return AccountIdentity(
            broker=broker,
            server=server,
            login=login,
            trade_mode=trade_mode,
            currency=str(getattr(account_info, "currency", "") or ""),
            balance=self._optional_float(getattr(account_info, "balance", None)),
            trade_allowed=trade_allowed,
        ), ""

    def _mutation_precondition_error(
        self,
        mt5_module,
        *,
        expected_account_fingerprint: str | None,
        expected_broker_symbol: str | None,
        actual_broker_symbol: str,
    ) -> str:
        """Return a fail-closed reason when a queued mutation changed scope."""

        if expected_account_fingerprint:
            account, account_error = self._account_identity(mt5_module)
            if account is None:
                return (
                    "Current MT5 account identity cannot be verified before "
                    f"mutation: {account_error or 'unknown account error'}"
                )
            if account.fingerprint != str(expected_account_fingerprint):
                return (
                    "MT5 account changed after the broker snapshot; the queued "
                    "mutation was not sent."
                )
        if (
            expected_broker_symbol
            and actual_broker_symbol != str(expected_broker_symbol)
        ):
            return (
                "Broker symbol changed after the broker snapshot; the queued "
                "mutation was not sent."
            )
        return ""

    def _broker_symbol_metadata(
        self,
        mt5_module,
        broker_symbol: str,
    ) -> BrokerSymbolMetadata:
        try:
            info = mt5_module.symbol_info(broker_symbol)
        except Exception:
            info = None
        return BrokerSymbolMetadata(
            digits=self._optional_int(getattr(info, "digits", None)),
            point=self._optional_float(getattr(info, "point", None)),
            trade_tick_size=self._optional_float(getattr(info, "trade_tick_size", None)),
            trade_stops_level=self._optional_int(getattr(info, "trade_stops_level", None)),
            trade_freeze_level=self._optional_int(getattr(info, "trade_freeze_level", None)),
            filling_mode=self._optional_int(getattr(info, "filling_mode", None)),
            volume_min=self._optional_float(getattr(info, "volume_min", None)),
            volume_max=self._optional_float(getattr(info, "volume_max", None)),
            volume_step=self._optional_float(getattr(info, "volume_step", None)),
        )

    @staticmethod
    def _last_mt5_error(mt5_module) -> tuple[int | None, str]:
        try:
            raw_error = mt5_module.last_error()
        except Exception:
            return None, ""
        if not isinstance(raw_error, (tuple, list)) or not raw_error:
            return None, str(raw_error or "")
        try:
            error_code = int(raw_error[0])
        except (TypeError, ValueError):
            error_code = None
        error_message = str(raw_error[1] or "") if len(raw_error) > 1 else ""
        return error_code, error_message

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _optional_float(value: object) -> float | None:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError, OverflowError):
            return None

    @classmethod
    def _timestamp(cls, value: datetime | int | float | object) -> int | None:
        if isinstance(value, datetime):
            normalized = (
                value.astimezone(timezone.utc)
                if value.tzinfo is not None
                else value.replace(tzinfo=timezone.utc)
            )
            try:
                return int(normalized.timestamp())
            except (OSError, OverflowError, ValueError):
                return None
        if isinstance(value, bool):
            return None
        numeric = cls._optional_float(value)
        if numeric is None or not isfinite(numeric):
            return None
        try:
            return int(numeric)
        except (OverflowError, ValueError):
            return None

    @classmethod
    def _normalize_expiration(cls, value: datetime | int | float | object) -> int:
        timestamp = cls._timestamp(value)
        if timestamp is None or timestamp < 0:
            raise ValueError(f"Invalid pending-order expiration: {value!r}")
        return timestamp

    @classmethod
    def _pending_order_type_map(cls, mt5_module) -> dict[int, str]:
        definitions = (
            ("ORDER_TYPE_BUY_LIMIT", 2, "buy_limit"),
            ("ORDER_TYPE_SELL_LIMIT", 3, "sell_limit"),
            ("ORDER_TYPE_BUY_STOP", 4, "buy_stop"),
            ("ORDER_TYPE_SELL_STOP", 5, "sell_stop"),
            ("ORDER_TYPE_BUY_STOP_LIMIT", 6, "buy_stop_limit"),
            ("ORDER_TYPE_SELL_STOP_LIMIT", 7, "sell_stop_limit"),
        )
        result: dict[int, str] = {}
        for name, fallback, label in definitions:
            raw_value = cls._optional_int(getattr(mt5_module, name, fallback))
            if raw_value is not None:
                result[raw_value] = label
        return result

    @staticmethod
    def _find_pending_order(rows: object, order_id: int):
        try:
            items = list(rows)  # type: ignore[arg-type]
        except TypeError:
            return None
        for item in items:
            try:
                if int(getattr(item, "ticket", 0) or 0) == int(order_id):
                    return item
            except (TypeError, ValueError):
                continue
        return None

    @classmethod
    def _has_price_normalization_metadata(cls, symbol_info) -> bool:
        if symbol_info is None:
            return False
        digits = cls._optional_int(getattr(symbol_info, "digits", None))
        tick_size = cls._optional_float(
            getattr(symbol_info, "trade_tick_size", None)
        )
        point = cls._optional_float(getattr(symbol_info, "point", None))
        return (
            digits is not None
            and digits >= 0
            and ((tick_size is not None and tick_size > 0) or (point is not None and point > 0))
        )

    @classmethod
    def _broker_protection_distances(
        cls,
        symbol_info,
    ) -> tuple[float, float, str]:
        stops_level = max(
            0,
            cls._optional_int(
                getattr(symbol_info, "trade_stops_level", 0)
                if symbol_info is not None
                else 0
            )
            or 0,
        )
        freeze_level = max(
            0,
            cls._optional_int(
                getattr(symbol_info, "trade_freeze_level", 0)
                if symbol_info is not None
                else 0
            )
            or 0,
        )
        point = cls._optional_float(
            getattr(symbol_info, "point", None) if symbol_info is not None else None
        )
        if (stops_level or freeze_level) and (point is None or point <= 0):
            return (
                0.0,
                0.0,
                "Broker stop/freeze levels are present but symbol point metadata is unavailable.",
            )
        normalized_point = point or 0.0
        return (
            stops_level * normalized_point,
            freeze_level * normalized_point,
            "",
        )

    @classmethod
    def _validate_position_sltp_constraints(
        cls,
        mt5_module,
        position,
        symbol_info,
        *,
        requested_sl: float,
        requested_tp: float,
        validate_sl: bool,
        validate_tp: bool,
    ) -> str:
        for field_name, field_value, should_validate in (
            ("SL", requested_sl, validate_sl),
            ("TP", requested_tp, validate_tp),
        ):
            if should_validate and (
                not isfinite(float(field_value)) or float(field_value) < 0
            ):
                return f"{field_name} must be a finite non-negative price."

        try:
            tick = mt5_module.symbol_info_tick(
                str(getattr(position, "symbol", "") or "")
            )
        except Exception:
            tick = None
        if tick is None:
            return "Current tick is unavailable; stop/freeze constraints cannot be verified safely."

        position_type = cls._optional_int(getattr(position, "type", None))
        buy_type = cls._optional_int(getattr(mt5_module, "POSITION_TYPE_BUY", 0))
        sell_type = cls._optional_int(getattr(mt5_module, "POSITION_TYPE_SELL", 1))
        if position_type not in {buy_type, sell_type}:
            return "Position side is unknown; SL/TP constraints cannot be verified safely."

        close_price = cls._optional_float(
            getattr(tick, "bid" if position_type == buy_type else "ask", None)
        )
        if close_price is None or not isfinite(close_price) or close_price <= 0:
            return "The close-side market price is invalid; SL/TP modification was blocked."

        stop_distance, freeze_distance, metadata_error = (
            cls._broker_protection_distances(symbol_info)
        )
        if metadata_error:
            return metadata_error
        required_distance = max(stop_distance, freeze_distance)
        epsilon = max(abs(close_price) * 1e-12, 1e-12)

        current_sl = cls._optional_float(getattr(position, "sl", 0)) or 0.0
        current_tp = cls._optional_float(getattr(position, "tp", 0)) or 0.0

        def removal_is_frozen(value: float, *, below_market: bool) -> bool:
            if value == 0 or freeze_distance <= 0:
                return False
            distance = (
                close_price - value if below_market else value - close_price
            )
            return distance <= freeze_distance + epsilon

        if validate_sl and requested_sl == 0:
            sl_below_market = position_type == buy_type
            if removal_is_frozen(current_sl, below_market=sl_below_market):
                return (
                    "Existing SL is inside the broker freeze zone; removing it "
                    "cannot be verified safely."
                )
        if validate_tp and requested_tp == 0:
            tp_below_market = position_type == sell_type
            if removal_is_frozen(current_tp, below_market=tp_below_market):
                return (
                    "Existing TP is inside the broker freeze zone; removing it "
                    "cannot be verified safely."
                )

        def below_market_is_invalid(value: float) -> bool:
            if value == 0:
                return False
            boundary = close_price - required_distance
            return value > boundary + epsilon or (
                required_distance == 0 and value >= close_price - epsilon
            )

        def above_market_is_invalid(value: float) -> bool:
            if value == 0:
                return False
            boundary = close_price + required_distance
            return value < boundary - epsilon or (
                required_distance == 0 and value <= close_price + epsilon
            )

        if position_type == buy_type:
            invalid_sl = validate_sl and below_market_is_invalid(requested_sl)
            invalid_tp = validate_tp and above_market_is_invalid(requested_tp)
        else:
            invalid_sl = validate_sl and above_market_is_invalid(requested_sl)
            invalid_tp = validate_tp and below_market_is_invalid(requested_tp)

        if invalid_sl:
            return (
                "Requested SL violates the broker stop/freeze distance from the "
                "close-side market price."
            )
        if invalid_tp:
            return (
                "Requested TP violates the broker stop/freeze distance from the "
                "close-side market price."
            )
        return ""

    @classmethod
    def _validate_pending_order_constraints(
        cls,
        mt5_module,
        *,
        raw_order_type: int,
        broker_symbol: str,
        symbol_info,
        price: float,
        sl: float,
        tp: float,
        stoplimit: float,
    ) -> str:
        values = {"entry": price, "SL": sl, "TP": tp, "stop-limit": stoplimit}
        for field_name, value in values.items():
            if not isfinite(float(value)) or float(value) < 0:
                return f"Pending-order {field_name} must be a finite non-negative price."
        if price <= 0:
            return "Pending-order entry price must be greater than zero."

        order_type = cls._pending_order_type_map(mt5_module).get(raw_order_type)
        if order_type is None:
            return "Pending order type is unsupported."
        try:
            tick = mt5_module.symbol_info_tick(broker_symbol)
        except Exception:
            tick = None
        if tick is None:
            return "Current tick is unavailable; pending-order constraints cannot be verified safely."

        bid = cls._optional_float(getattr(tick, "bid", None))
        ask = cls._optional_float(getattr(tick, "ask", None))
        if (
            bid is None
            or ask is None
            or not isfinite(bid)
            or not isfinite(ask)
            or bid <= 0
            or ask <= 0
        ):
            return "Current bid/ask is invalid; pending-order modification was blocked."

        stop_distance, freeze_distance, metadata_error = (
            cls._broker_protection_distances(symbol_info)
        )
        if metadata_error:
            return metadata_error
        entry_distance = max(stop_distance, freeze_distance)
        is_buy = order_type.startswith("buy_")
        is_limit = order_type in {"buy_limit", "sell_limit"}
        is_stop = order_type in {
            "buy_stop",
            "sell_stop",
            "buy_stop_limit",
            "sell_stop_limit",
        }
        market_price = ask if is_buy else bid
        epsilon = max(abs(market_price) * 1e-12, 1e-12)

        if is_buy and is_limit:
            invalid_entry = price > market_price - entry_distance + epsilon
        elif not is_buy and is_limit:
            invalid_entry = price < market_price + entry_distance - epsilon
        elif is_buy and is_stop:
            invalid_entry = price < market_price + entry_distance - epsilon
        else:
            invalid_entry = price > market_price - entry_distance + epsilon
        if entry_distance == 0:
            if is_buy and is_limit:
                invalid_entry = price >= market_price - epsilon
            elif not is_buy and is_limit:
                invalid_entry = price <= market_price + epsilon
            elif is_buy and is_stop:
                invalid_entry = price <= market_price + epsilon
            else:
                invalid_entry = price >= market_price - epsilon
        if invalid_entry:
            return (
                f"{order_type} entry violates the broker stop/freeze distance "
                "from the current market."
            )

        fill_price = price
        if order_type in {"buy_stop_limit", "sell_stop_limit"}:
            if stoplimit <= 0:
                return "A stop-limit pending order must preserve a positive stop-limit price."
            fill_price = stoplimit
            if is_buy:
                invalid_stoplimit = stoplimit > price - stop_distance + epsilon
            else:
                invalid_stoplimit = stoplimit < price + stop_distance - epsilon
            if invalid_stoplimit:
                return "Stop-limit price violates the broker distance from its trigger price."

        if is_buy:
            invalid_sl = sl != 0 and sl > fill_price - stop_distance + epsilon
            invalid_tp = tp != 0 and tp < fill_price + stop_distance - epsilon
        else:
            invalid_sl = sl != 0 and sl < fill_price + stop_distance - epsilon
            invalid_tp = tp != 0 and tp > fill_price - stop_distance + epsilon
        if invalid_sl:
            return "Pending-order SL violates the broker stop distance from its entry."
        if invalid_tp:
            return "Pending-order TP violates the broker stop distance from its entry."
        return ""

    @staticmethod
    def _find_position(rows: object, position_id: int):
        try:
            items = list(rows)  # type: ignore[arg-type]
        except TypeError:
            return None
        for item in items:
            try:
                if int(getattr(item, "ticket", 0) or 0) == int(position_id):
                    return item
            except (TypeError, ValueError):
                continue
        return None

    @classmethod
    def _retcodes(cls, mt5_module, *names: str) -> set[int]:
        return {
            value
            for name in names
            if (value := cls._optional_int(getattr(mt5_module, name, None))) is not None
        }

    @classmethod
    def _result_id(cls, result: object, field: str) -> int | None:
        if result is None:
            return None
        value = cls._optional_int(getattr(result, field, None))
        return value if value not in {None, 0} else None

    @staticmethod
    def _normalize_price(value: object, symbol_info) -> float:
        try:
            price = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError(f"Invalid price: {value!r}") from None
        if not price.is_finite():
            raise ValueError(f"Invalid price: {value!r}")

        raw_tick_size = getattr(symbol_info, "trade_tick_size", None) if symbol_info else None
        raw_digits = getattr(symbol_info, "digits", None) if symbol_info else None
        try:
            tick_size = Decimal(str(raw_tick_size)) if raw_tick_size else Decimal("0")
        except InvalidOperation:
            tick_size = Decimal("0")
        try:
            digits = max(0, int(raw_digits)) if raw_digits is not None else None
        except (TypeError, ValueError):
            digits = None

        if tick_size > 0:
            price = (price / tick_size).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * tick_size
        if digits is not None:
            quantum = Decimal("1").scaleb(-digits)
            price = price.quantize(quantum, rounding=ROUND_HALF_UP)
        return float(price)

    @classmethod
    def _prices_equal(cls, left: float, right: float, symbol_info) -> bool:
        raw_tick_size = getattr(symbol_info, "trade_tick_size", None) if symbol_info else None
        raw_digits = getattr(symbol_info, "digits", None) if symbol_info else None
        tick_size = cls._optional_float(raw_tick_size) or 0.0
        try:
            digit_tolerance = 10 ** (-max(0, int(raw_digits))) / 2 if raw_digits is not None else 1e-9
        except (TypeError, ValueError):
            digit_tolerance = 1e-9
        tolerance = max(tick_size / 2, digit_tolerance, 1e-12)
        return abs(float(left) - float(right)) <= tolerance

    def _normalize_volume(self, volume: float, symbol_info) -> float:
        try:
            raw = Decimal(str(volume))
        except (InvalidOperation, TypeError, ValueError):
            return 0.0
        if not raw.is_finite() or raw <= 0:
            return 0.0
        try:
            step = Decimal(str(getattr(symbol_info, "volume_step", 0.01) or 0.01)) if symbol_info else Decimal("0.01")
            minimum = Decimal(str(getattr(symbol_info, "volume_min", 0.0) or 0.0)) if symbol_info else Decimal("0")
            maximum = Decimal(str(getattr(symbol_info, "volume_max", 0.0) or 0.0)) if symbol_info else Decimal("0")
        except InvalidOperation:
            return 0.0
        if step <= 0:
            return 0.0
        normalized = (raw / step).quantize(Decimal("1"), rounding=ROUND_FLOOR) * step
        if maximum > 0:
            normalized = min(normalized, maximum)
        if minimum > 0 and normalized < minimum:
            return 0.0
        return float(normalized)

    def _order_filling(self, mt5_module, symbol_info):
        """Map the symbol's filling-mode bitmask to an order filling enum."""

        filling_flags = self._optional_int(
            getattr(symbol_info, "filling_mode", None) if symbol_info else None
        )
        symbol_ioc = self._optional_int(getattr(mt5_module, "SYMBOL_FILLING_IOC", 2)) or 2
        symbol_fok = self._optional_int(getattr(mt5_module, "SYMBOL_FILLING_FOK", 1)) or 1
        order_ioc = self._optional_int(getattr(mt5_module, "ORDER_FILLING_IOC", None))
        order_fok = self._optional_int(getattr(mt5_module, "ORDER_FILLING_FOK", None))
        order_return = self._optional_int(getattr(mt5_module, "ORDER_FILLING_RETURN", None))

        if filling_flags is not None:
            if order_ioc is not None and filling_flags & symbol_ioc:
                return order_ioc
            if order_fok is not None and filling_flags & symbol_fok:
                return order_fok

        execution_mode = self._optional_int(
            getattr(symbol_info, "trade_exemode", None) if symbol_info else None
        )
        market_execution = self._optional_int(
            getattr(mt5_module, "SYMBOL_TRADE_EXECUTION_MARKET", None)
        )
        if (
            order_return is not None
            and execution_mode is not None
            and market_execution is not None
            and execution_mode != market_execution
        ):
            return order_return
        if order_ioc is not None:
            return order_ioc
        if order_fok is not None:
            return order_fok
        return order_return if order_return is not None else 1

    def _timeframe_id(self, mt5_module, timeframe: str):
        return {
            "D1": getattr(mt5_module, "TIMEFRAME_D1", None),
            "H4": getattr(mt5_module, "TIMEFRAME_H4", None),
            "H1": getattr(mt5_module, "TIMEFRAME_H1", None),
            "M15": getattr(mt5_module, "TIMEFRAME_M15", None),
            "M5": getattr(mt5_module, "TIMEFRAME_M5", None),
        }.get(timeframe)

    def _normalize_symbol_name(self, symbol: str) -> str:
        return "".join(char.lower() for char in symbol if char.isalnum())

    def _symbol_profiles(self) -> dict[str, Any]:
        return self.symbol_profiles

    def _closed_trades_from_deals(self, mt5_module, deals: list[object]) -> list[dict[str, object]]:
        entry_in = getattr(mt5_module, "DEAL_ENTRY_IN", 0)
        entry_out = getattr(mt5_module, "DEAL_ENTRY_OUT", 1)
        entry_inout = getattr(mt5_module, "DEAL_ENTRY_INOUT", 2)
        buy_type = getattr(mt5_module, "DEAL_TYPE_BUY", 0)
        sell_type = getattr(mt5_module, "DEAL_TYPE_SELL", 1)

        groups: dict[int, list[object]] = {}
        for deal in deals:
            symbol = str(getattr(deal, "symbol", "") or "")
            if not symbol:
                continue
            deal_type = getattr(deal, "type", None)
            if deal_type not in {buy_type, sell_type}:
                continue
            position_id = int(getattr(deal, "position_id", 0) or getattr(deal, "order", 0) or getattr(deal, "ticket", 0) or 0)
            if position_id <= 0:
                continue
            groups.setdefault(position_id, []).append(deal)

        trades: list[dict[str, object]] = []
        for position_id, rows in groups.items():
            ordered = sorted(rows, key=lambda item: int(getattr(item, "time", 0) or 0))
            entry_deals = [deal for deal in ordered if getattr(deal, "entry", None) == entry_in]
            exit_deals = [deal for deal in ordered if getattr(deal, "entry", None) in {entry_out, entry_inout}]
            if not exit_deals:
                continue
            entry_deal = entry_deals[0] if entry_deals else ordered[0]
            exit_deal = exit_deals[-1]

            symbol = str(getattr(exit_deal, "symbol", "") or getattr(entry_deal, "symbol", "") or "")
            entry_type = getattr(entry_deal, "type", None)
            side = "buy" if entry_type == buy_type else "sell" if entry_type == sell_type else ""
            open_time = datetime.fromtimestamp(int(getattr(entry_deal, "time", 0) or 0), tz=timezone.utc)
            close_time = datetime.fromtimestamp(int(getattr(exit_deal, "time", 0) or 0), tz=timezone.utc)
            volume = sum(float(getattr(deal, "volume", 0.0) or 0.0) for deal in entry_deals) or float(getattr(exit_deal, "volume", 0.0) or 0.0)
            profit = sum(float(getattr(deal, "profit", 0.0) or 0.0) for deal in exit_deals)
            commission = sum(float(getattr(deal, "commission", 0.0) or 0.0) for deal in ordered)
            swap = sum(float(getattr(deal, "swap", 0.0) or 0.0) for deal in ordered)
            entry_comment = str(getattr(entry_deal, "comment", "") or "")
            correlation_id = (
                entry_comment.split("AMA-FWD:", 1)[1].strip()
                if entry_comment.startswith("AMA-FWD:")
                else ""
            )
            trades.append({
                "candidate_id": correlation_id,
                "symbol": self.app_symbol_for_broker_symbol(symbol),
                "broker_symbol": symbol,
                "side": side,
                "opened_at": open_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "closed_at": close_time.isoformat(timespec="seconds").replace("+00:00", "Z"),
                "actual_entry": float(getattr(entry_deal, "price", 0.0) or 0.0),
                "actual_exit": float(getattr(exit_deal, "price", 0.0) or 0.0),
                "actual_lot": round(volume, 4),
                "result_amount": round(profit + commission + swap, 2),
                "exit_reason": str(getattr(exit_deal, "reason", "") or ""),
                "mt5_deal_id": int(getattr(exit_deal, "ticket", 0) or 0),
                "mt5_order_id": int(getattr(exit_deal, "order", 0) or 0),
                "mt5_position_id": position_id,
                "comment": entry_comment,
            })
        return trades


def _optional_int(value: object) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


def _optional_positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _optional_nonnegative_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number >= 0 else None


def _tick_timestamp(tick: object) -> float | None:
    try:
        milliseconds = float(getattr(tick, "time_msc", 0) or 0)
        if milliseconds > 0:
            return milliseconds / 1000.0
        seconds = float(getattr(tick, "time", 0) or 0)
        return seconds if seconds > 0 else None
    except (TypeError, ValueError, OverflowError):
        return None
