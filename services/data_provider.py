"""Abstract data-provider interface for market data and trading.

Every concrete provider (MT5, cTrader, …) implements this ABC so that
controllers can work with *any* data source without caring which one
is active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core.market_models import Candle


# ---------------------------------------------------------------------------
# Shared data-classes (provider-agnostic)
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ConnectionStatus:
    """Unified connection/account status returned by every provider."""

    initialized: bool
    connected: bool
    logged_in: bool
    trade_allowed: bool
    provider_name: str = ""       # "MT5" / "cTrader"
    broker: str = ""
    server: str = ""
    login: int | str | None = None
    balance: float | None = None
    currency: str = ""
    error_code: int | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class OrderResult:
    """Unified order result returned by every provider."""

    success: bool
    symbol: str
    broker_symbol: str
    side: str
    volume: float
    price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    order_id: int | str | None = None
    retcode: int | None = None
    message: str = ""


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------

class DataProvider(ABC):
    """Unified interface for market-data retrieval and trade execution.

    Each method mirrors what ``MT5Service`` currently exposes, but is
    provider-agnostic so that ``CTraderService`` (or any future provider)
    can implement the same contract.
    """

    # -- connection --------------------------------------------------------

    @abstractmethod
    def connect(self) -> bool:
        """Attempt to connect / initialise the provider.  Return *True* on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Gracefully shut down the provider connection."""

    @abstractmethod
    def connection_status(self) -> ConnectionStatus:
        """Return the current connection & account status."""

    def account_balance(self) -> float | None:
        """Convenience — extract balance from connection_status()."""
        status = self.connection_status()
        if not status.connected or not status.logged_in:
            return None
        return status.balance

    # -- symbol resolution -------------------------------------------------

    @abstractmethod
    def available_symbols(self, market_watch_only: bool = True) -> list[str]:
        """Return broker-side symbol names available for trading."""

    @abstractmethod
    def resolve_symbol(self, app_symbol: str, available_symbols: list[str]) -> str | None:
        """Map an app symbol (e.g. ``EUR/USD``) to the broker symbol."""

    def configured_symbols_in_market_watch(self) -> list[tuple[str, str]]:
        """Return ``(app_symbol, broker_symbol)`` pairs for all configured symbols."""
        available = self.available_symbols(market_watch_only=True)
        matched: list[tuple[str, str]] = []
        for app_symbol in sorted(self._symbol_profiles()):
            broker = self.resolve_symbol(app_symbol, available)
            if broker:
                matched.append((app_symbol, broker))
        return matched

    # -- market data -------------------------------------------------------

    @abstractmethod
    def load_ohlcv(
        self,
        broker_symbol: str,
        timeframe: str,
        bars: int,
        skip_select: bool = False,
    ) -> list[Candle]:
        """Load the most recent *bars* candles for *broker_symbol*."""

    @abstractmethod
    def load_ohlcv_range(
        self,
        broker_symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        skip_select: bool = False,
    ) -> list[Candle]:
        """Load candles in a specific datetime range."""

    def load_primary_timeframes(
        self,
        broker_symbol: str,
        bars_by_timeframe: dict[str, int],
    ) -> dict[str, list[Candle]]:
        """Load multiple timeframes in one call.

        Default implementation calls ``load_ohlcv`` sequentially; concrete
        providers may optimise with batch requests.
        """
        results: dict[str, list[Candle]] = {}
        for timeframe, bars in bars_by_timeframe.items():
            results[timeframe] = self.load_ohlcv(
                broker_symbol, timeframe, bars, skip_select=True,
            )
        return results

    @abstractmethod
    def symbol_data_quality(
        self, display_symbol: str, broker_symbol: str,
    ) -> dict[str, Any]:
        """Return a quality/metadata dict used by the analysis pipeline."""

    def server_time_utc(self) -> datetime | None:
        """Return server UTC time, or ``None`` if unavailable."""
        return None

    @abstractmethod
    def quote_to_usd_rate(self, quote_currency: str) -> float | None:
        """Return the conversion rate from *quote_currency* to USD."""

    # -- trading -----------------------------------------------------------

    @abstractmethod
    def has_open_position_or_order(self, broker_symbol: str) -> bool:
        """Check if there is already an open position or pending order."""

    @abstractmethod
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
    ) -> OrderResult:
        """Place a market order and return the result."""

    @abstractmethod
    def closed_trade_history(
        self, *, start: datetime, end: datetime,
    ) -> list[dict[str, Any]]:
        """Return closed trades in a journal-ready format."""

    def closed_trade_history_recent(self, days: int = 90) -> list[dict[str, Any]]:
        """Convenience — closed trades for the last *days* days."""
        from datetime import timedelta, timezone

        end = datetime.now(timezone.utc)
        start = end - timedelta(days=max(1, int(days)))
        return self.closed_trade_history(start=start, end=end)

    # -- helpers (override if needed) --------------------------------------

    def app_symbol_for_broker_symbol(self, broker_symbol: str) -> str:
        """Reverse-map a broker symbol back to an app symbol."""
        return broker_symbol

    def _symbol_profiles(self) -> dict[str, Any]:
        """Return the symbol-profiles dict.  Subclasses should override."""
        return {}
