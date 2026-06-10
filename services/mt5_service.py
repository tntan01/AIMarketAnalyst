from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor
from pathlib import Path

from config.paths import CONFIG_DIR
from core.market_models import Candle


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


class MT5Service:
    def __init__(self, symbol_profile_path: Path | None = None) -> None:
        path = symbol_profile_path or CONFIG_DIR / "symbol_profiles.json"
        self.symbol_profiles = json.loads(path.read_text(encoding="utf-8"))

    def connection_status(self) -> MT5ConnectionStatus:
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

        initialized = mt5.initialize()
        error_code, error_message = mt5.last_error()
        if not initialized:
            return MT5ConnectionStatus(
                initialized=False,
                terminal_connected=False,
                logged_in=False,
                trade_allowed=False,
                error_code=error_code,
                message=error_message or "Không khởi tạo được kết nối MT5.",
            )

        terminal = mt5.terminal_info()
        account = mt5.account_info()
        terminal_connected = bool(terminal and terminal.connected)
        logged_in = bool(account and account.login)
        trade_allowed = bool(account and account.trade_allowed)

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

    def account_balance(self) -> float | None:
        status = self.connection_status()
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

    def available_symbols(self, market_watch_only: bool = True) -> list[str]:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return []

        if not mt5.initialize():
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

    def load_ohlcv(self, broker_symbol: str, timeframe: str, bars: int, skip_select: bool = False) -> list[Candle]:
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise RuntimeError("Chưa cài package MetaTrader5.") from exc

        if not mt5.initialize():
            error_code, error_message = mt5.last_error()
            raise RuntimeError(error_message or f"Không khởi tạo được MT5 ({error_code}).")

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

        if not mt5.initialize():
            error_code, error_message = mt5.last_error()
            raise RuntimeError(error_message or f"Không khởi tạo được MT5 ({error_code}).")

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

    def load_primary_timeframes(self, broker_symbol: str, bars_by_timeframe: dict[str, int]) -> dict[str, list[Candle]]:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            error_code, error_message = mt5.last_error()
            raise RuntimeError(error_message or f"Không khởi tạo được MT5 ({error_code}).")
        selected = mt5.symbol_select(broker_symbol, True)
        if not selected:
            raise RuntimeError(f"Không chọn được mã {broker_symbol} trong MT5 Market Watch.")

        from concurrent.futures import ThreadPoolExecutor, as_completed
        results: dict[str, list[Candle]] = {}
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(self.load_ohlcv, broker_symbol, timeframe, bars, True): timeframe
                for timeframe, bars in bars_by_timeframe.items()
            }
            for future in as_completed(futures):
                tf = futures[future]
                results[tf] = future.result()
        return results

    def symbol_data_quality(self, display_symbol: str, broker_symbol: str) -> dict[str, object]:
        status = self.connection_status()
        spread_points = None
        spread_status = "unknown"
        contract_size = None
        warning = None
        try:
            import MetaTrader5 as mt5

            info = mt5.symbol_info(broker_symbol)
            if info:
                spread_points = getattr(info, "spread", None)
                contract_size = getattr(info, "trade_contract_size", None)
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
            "spread_status": spread_status,
            "contract_size": contract_size,
            "warning": warning,
        }

    def server_time_utc(self) -> datetime | None:
        """Trả về thời gian UTC từ MT5 server, hoặc None nếu không lấy được."""
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return None
            symbols = mt5.symbols_get()
            if symbols:
                tick = mt5.symbol_info_tick(symbols[0].name)
                if tick and tick.time:
                    return datetime.fromtimestamp(tick.time, tz=timezone.utc)
            return datetime.now(timezone.utc)
        except Exception:
            return None

    def quote_to_usd_rate(self, quote_currency: str) -> float | None:
        """Trả về tỷ giá quy đổi từ quote_currency sang USD, hoặc None nếu không lấy được."""
        if quote_currency == "USD":
            return 1.0
        try:
            import MetaTrader5 as mt5
            if not mt5.initialize():
                return None
            # Thử QUOTEUSD (vd: GBP → GBPUSD) hoặc USDQUOTE (vd: JPY → USDJPY)
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
                    return rate if pair_name.startswith(quote_currency) else 1.0 / rate
            return None
        except Exception:
            return None

    def has_open_position_or_order(self, broker_symbol: str) -> bool:
        try:
            import MetaTrader5 as mt5
        except ImportError:
            return False
        if not mt5.initialize():
            return False

        positions = mt5.positions_get(symbol=broker_symbol)
        if positions:
            return True
        orders = mt5.orders_get(symbol=broker_symbol)
        return bool(orders)

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

        if not mt5.initialize():
            error_code, error_message = mt5.last_error()
            return MT5OrderResult(False, symbol, broker_symbol, side, volume, retcode=error_code, message=error_message or "Không khởi tạo được MT5.")

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

    def _normalize_volume(self, volume: float, symbol_info) -> float:
        try:
            raw = float(volume)
        except (TypeError, ValueError):
            return 0.0
        if raw <= 0:
            return 0.0
        step = float(getattr(symbol_info, "volume_step", 0.01) or 0.01) if symbol_info else 0.01
        minimum = float(getattr(symbol_info, "volume_min", 0.0) or 0.0) if symbol_info else 0.0
        maximum = float(getattr(symbol_info, "volume_max", 0.0) or 0.0) if symbol_info else 0.0
        normalized = floor(raw / step) * step
        if maximum > 0:
            normalized = min(normalized, maximum)
        if minimum > 0 and normalized < minimum:
            return 0.0
        return round(normalized, 2)

    def _order_filling(self, mt5_module, symbol_info):
        filling = getattr(symbol_info, "filling_mode", None) if symbol_info else None
        if filling in (
            getattr(mt5_module, "ORDER_FILLING_FOK", None),
            getattr(mt5_module, "ORDER_FILLING_IOC", None),
            getattr(mt5_module, "ORDER_FILLING_RETURN", None),
        ):
            return filling
        return getattr(mt5_module, "ORDER_FILLING_IOC", 1)

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
