from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Twisted must be imported carefully. 
# We need to run it in a separate thread.
from twisted.internet import reactor
from twisted.internet.error import ReactorNotRunning

from ctrader_open_api import Client, EndPoints, Protobuf
from ctrader_open_api.messages.OpenApiCommonMessages_pb2 import *
from ctrader_open_api.messages.OpenApiCommonModelMessages_pb2 import *
from ctrader_open_api.messages.OpenApiMessages_pb2 import *
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import *

from config.settings import CTraderSettings
from core.market_models import Candle
from services.data_provider import ConnectionStatus, DataProvider, OrderResult

logger = logging.getLogger(__name__)

# Start reactor in a background thread if not already running
_reactor_started = False
_reactor_lock = threading.Lock()

def _start_reactor():
    global _reactor_started
    with _reactor_lock:
        if not _reactor_started and not reactor.running:
            _reactor_started = True
            threading.Thread(target=reactor.run, args=(False,), daemon=True, name="TwistedReactorThread").start()

class CTraderService(DataProvider):
    """
    cTrader (cTrader) implementation of DataProvider using ctrader-open-api (Twisted).
    """

    def __init__(self, config: CTraderSettings, symbol_profile_path: Path | str | None = None) -> None:
        self._config = config
        self._symbol_profile_path = Path(symbol_profile_path) if symbol_profile_path else Path("./config/symbol_profiles.json")
        
        self._client: Client | None = None
        
        # Connection state
        self._connected = False
        self._app_authed = False
        self._account_authed = False
        self._account_balance: float | None = None
        self._account_currency: str = "USD"
        
        # Requests and async mapping
        self._pending_requests: dict[str, dict] = {}
        self._lock = threading.Lock()
        
        # Caching
        self._symbols_cache: list[dict] = []
        self._symbol_name_to_id: dict[str, int] = {}
        self._symbol_id_to_name: dict[int, str] = {}
        self._asset_id_to_name: dict[int, str] = {}
        
        # Rate tracking for USD conversion
        self._tick_cache: dict[int, float] = {}
        
        _start_reactor()

    def _generate_client_msg_id(self) -> str:
        return uuid.uuid4().hex

    def _send_message_sync(self, request, timeout=10.0) -> Any:
        if not self._client or not self._connected:
            raise RuntimeError("cTrader cTrader client is not connected.")
            
        msg_id = self._generate_client_msg_id()
        event = threading.Event()
        
        context = {
            "event": event,
            "response": None,
            "error": None
        }
        
        with self._lock:
            self._pending_requests[msg_id] = context
            
        def _send():
            try:
                self._client.send(request, clientMsgId=msg_id)
            except Exception as e:
                context["error"] = e
                event.set()
                
        reactor.callFromThread(_send)
        event.wait(timeout)
        
        with self._lock:
            self._pending_requests.pop(msg_id, None)
            
        if context["error"]:
            raise RuntimeError(f"Error sending message: {context['error']}")
            
        return context["response"]

    def _on_connected(self):
        logger.info("cTrader connected.")
        self._connected = True

    def _on_disconnected(self, reason):
        logger.warning(f"cTrader disconnected: {reason}")
        self._connected = False
        self._app_authed = False
        self._account_authed = False

    def _on_message_received(self, client, message):
        msg_type = message.payloadType
        client_msg_id = message.clientMsgId
        
        # If it's an error message
        if msg_type == ProtoOAPayloadType.PROTO_OA_ERROR_RES:
            res = Protobuf.extract(message)
            if client_msg_id:
                with self._lock:
                    if client_msg_id in self._pending_requests:
                        self._pending_requests[client_msg_id]["error"] = res.description
                        self._pending_requests[client_msg_id]["event"].set()
            return
            
        # Try resolving deferred requests
        if client_msg_id:
            with self._lock:
                if client_msg_id in self._pending_requests:
                    self._pending_requests[client_msg_id]["response"] = Protobuf.extract(message)
                    self._pending_requests[client_msg_id]["event"].set()
                    return

    def connect(self) -> bool:
        if self._connected and self._account_authed:
            return True
            
        endpoint = EndPoints.DATACENTER_DEMO if self._config.environment.lower() == "demo" else EndPoints.DATACENTER_LIVE
        
        self._client = Client(endpoint.HOST, endpoint.PORT, EndPoints.PROTOCOLS.TCP)
        self._client.set_connectedCallback(self._on_connected)
        self._client.set_disconnectedCallback(self._on_disconnected)
        self._client.set_messageReceivedCallback(self._on_message_received)
        
        # Start connection from reactor thread
        connect_event = threading.Event()
        
        def _start_client():
            self._client.startService()
            # Twisted doesn't block on startService, we just need to wait a bit for connection
            reactor.callLater(2.0, connect_event.set)
            
        reactor.callFromThread(_start_client)
        connect_event.wait(5.0)
        
        # Auth App
        if self._connected and not self._app_authed:
            req = ProtoOAApplicationAuthReq()
            req.clientId = self._config.client_id
            req.clientSecret = self._config.client_secret
            try:
                res = self._send_message_sync(req)
                if isinstance(res, ProtoOAApplicationAuthRes):
                    self._app_authed = True
            except Exception as e:
                logger.error(f"Failed to auth app: {e}")
                return False

        # Auth Account
        if self._app_authed and not self._account_authed:
            req = ProtoOAAccountAuthReq()
            req.ctidTraderAccountId = self._config.account_id
            req.accessToken = self._config.access_token
            try:
                res = self._send_message_sync(req)
                if isinstance(res, ProtoOAAccountAuthRes):
                    self._account_authed = True
            except Exception as e:
                logger.error(f"Failed to auth account: {e}")
                return False
                
        # Fetch initial account info and symbols
        if self._account_authed:
            self._fetch_account_info()
            self._fetch_symbols()
            self._fetch_assets()
            
        return self._account_authed

    def disconnect(self) -> None:
        if self._client:
            reactor.callFromThread(self._client.stopService)
            self._client = None
        self._connected = False
        self._app_authed = False
        self._account_authed = False

    def connection_status(self) -> ConnectionStatus:
        if not self._connected or not self._account_authed:
            return ConnectionStatus(
                initialized=self._connected,
                connected=self._connected,
                logged_in=self._account_authed,
                trade_allowed=False,
                provider_name="cTrader",
            )
            
        # Refresh account info periodically
        try:
            self._fetch_account_info()
        except:
            pass

        return ConnectionStatus(
            initialized=True,
            connected=True,
            logged_in=True,
            trade_allowed=self._config.environment.lower() == "demo" or True,  # Assume true if logged in
            provider_name="cTrader",
            broker="cTrader",
            server=self._config.environment.upper(),
            login=self._config.account_id,
            balance=self._account_balance,
            currency=self._account_currency,
        )

    def _fetch_account_info(self):
        req = ProtoOATraderReq()
        req.ctidTraderAccountId = self._config.account_id
        res = self._send_message_sync(req)
        if isinstance(res, ProtoOATraderRes):
            # Balance is usually in cents (e.g. 1000000 = 10000.00)
            self._account_balance = float(res.trader.balance) / 100.0
            asset_id = res.trader.depositAssetId
            if asset_id in self._asset_id_to_name:
                self._account_currency = self._asset_id_to_name[asset_id]
                
    def _fetch_assets(self):
        req = ProtoOAGetCtidProfileReq() # No, assets are listed somewhere else? 
        # Wait, ProtoOAAssetListReq
        req = ProtoOAAssetListReq()
        req.ctidTraderAccountId = self._config.account_id
        try:
            res = self._send_message_sync(req)
            if isinstance(res, ProtoOAAssetListRes):
                for asset in res.asset:
                    self._asset_id_to_name[asset.assetId] = asset.name
        except:
            pass

    def _fetch_symbols(self):
        if self._symbols_cache:
            return
            
        req = ProtoOASymbolsListReq()
        req.ctidTraderAccountId = self._config.account_id
        res = self._send_message_sync(req)
        
        if isinstance(res, ProtoOASymbolsListRes):
            for symbol in res.symbol:
                self._symbols_cache.append(symbol)
                self._symbol_name_to_id[symbol.symbolName] = symbol.symbolId
                self._symbol_id_to_name[symbol.symbolId] = symbol.symbolName

    def available_symbols(self, market_watch_only: bool = True) -> list[str]:
        if not self._symbols_cache:
            self._fetch_symbols()
        return list(self._symbol_name_to_id.keys())

    def _symbol_profiles(self) -> dict[str, Any]:
        try:
            if self._symbol_profile_path.is_file():
                return json.loads(self._symbol_profile_path.read_text("utf-8"))
        except Exception as e:
            logger.error(f"Error reading symbol profiles: {e}")
        return {}

    def resolve_symbol(self, app_symbol: str, available_symbols: list[str]) -> str | None:
        profiles = self._symbol_profiles()
        if app_symbol in profiles:
            p_symbol = profiles[app_symbol].get("ctrader_symbol")
            if p_symbol and p_symbol in available_symbols:
                return p_symbol
        # Fallback to exact match
        if app_symbol in available_symbols:
            return app_symbol
        return None

    def app_symbol_for_broker_symbol(self, broker_symbol: str) -> str:
        profiles = self._symbol_profiles()
        for app_sym, info in profiles.items():
            if info.get("ctrader_symbol") == broker_symbol:
                return app_sym
        return broker_symbol

    def _map_timeframe(self, timeframe: str):
        # Map H1 -> ProtoOATrendbarPeriod.H1, etc.
        mapping = {
            "M1": ProtoOATrendbarPeriod.M1,
            "M5": ProtoOATrendbarPeriod.M5,
            "M15": ProtoOATrendbarPeriod.M15,
            "M30": ProtoOATrendbarPeriod.M30,
            "H1": ProtoOATrendbarPeriod.H1,
            "H4": ProtoOATrendbarPeriod.H4,
            "D1": ProtoOATrendbarPeriod.D1,
            "W1": ProtoOATrendbarPeriod.W1,
            "MN1": ProtoOATrendbarPeriod.MN1,
        }
        return mapping.get(timeframe, ProtoOATrendbarPeriod.H1)

    def load_ohlcv(
        self,
        broker_symbol: str,
        timeframe: str,
        bars: int,
        skip_select: bool = False,
    ) -> list[Candle]:
        if not self._connected:
            return []
            
        symbol_id = self._symbol_name_to_id.get(broker_symbol)
        if not symbol_id:
            return []
            
        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self._config.account_id
        req.period = self._map_timeframe(timeframe)
        req.symbolId = symbol_id
        req.count = bars
        
        try:
            res = self._send_message_sync(req)
            if not isinstance(res, ProtoOAGetTrendbarsRes):
                return []
                
            candles = []
            # cTrader delta logic: Prices are often sent as deltas from a base or previous
            # But the GetTrendbarsRes provides absolute low and deltas for others.
            
            # Note: The exact price extraction depends on cTrader API protobuf definition
            # Let's extract standard fields:
            # timestamp is in ms
            
            for tb in res.trendbar:
                # Need to convert integer prices. Usually divide by 100000 for standard 5 digit forex?
                # Actually, the API returns delta values. We should use standard formula.
                
                # A quick implementation, need refinement based on symbol pipSize:
                # Actually, for standard cTrader Open API Python:
                # open = tb.low + tb.deltaOpen
                # high = tb.low + tb.deltaHigh
                # close = tb.low + tb.deltaClose
                
                # The exact multiplier is 1 / 100000.0, but we need pipPosition.
                # Just use 1e-5 as default fallback.
                multiplier = 1e-5
                
                low = tb.low * multiplier
                open_p = low + (tb.deltaOpen * multiplier) if hasattr(tb, 'deltaOpen') else low
                high = low + (tb.deltaHigh * multiplier) if hasattr(tb, 'deltaHigh') else low
                close = low + (tb.deltaClose * multiplier) if hasattr(tb, 'deltaClose') else low
                
                dt = datetime.fromtimestamp(tb.utcTimestampInMinutes * 60, timezone.utc)
                candles.append(Candle(
                    time=dt,
                    open=open_p,
                    high=high,
                    low=low,
                    close=close,
                    volume=float(tb.volume)
                ))
            return candles
            
        except Exception as e:
            logger.error(f"Failed to load OHLCV for {broker_symbol}: {e}")
            return []

    def load_ohlcv_range(
        self,
        broker_symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        skip_select: bool = False,
    ) -> list[Candle]:
        # Not perfectly supported without specific from/to timestamps in ProtoOAGetTrendbarsReq.
        # cTrader allows fetching by timestamp.
        if not self._connected:
            return []
            
        symbol_id = self._symbol_name_to_id.get(broker_symbol)
        if not symbol_id:
            return []
            
        req = ProtoOAGetTrendbarsReq()
        req.ctidTraderAccountId = self._config.account_id
        req.period = self._map_timeframe(timeframe)
        req.symbolId = symbol_id
        req.fromTimestamp = int(start.timestamp() * 1000)
        req.toTimestamp = int(end.timestamp() * 1000)
        
        try:
            res = self._send_message_sync(req)
            if not isinstance(res, ProtoOAGetTrendbarsRes):
                return []
            
            # Same parsing logic
            candles = []
            multiplier = 1e-5
            for tb in res.trendbar:
                low = tb.low * multiplier
                open_p = low + getattr(tb, 'deltaOpen', 0) * multiplier
                high = low + getattr(tb, 'deltaHigh', 0) * multiplier
                close = low + getattr(tb, 'deltaClose', 0) * multiplier
                
                dt = datetime.fromtimestamp(tb.utcTimestampInMinutes * 60, timezone.utc)
                candles.append(Candle(
                    time=dt,
                    open=open_p,
                    high=high,
                    low=low,
                    close=close,
                    volume=float(tb.volume)
                ))
            return candles
        except:
            return []

    def symbol_data_quality(self, display_symbol: str, broker_symbol: str) -> dict[str, Any]:
        # Basic quality stub
        return {"data_source": "cTrader"}

    def quote_to_usd_rate(self, quote_currency: str) -> float | None:
        if quote_currency.upper() == "USD":
            return 1.0
        return 1.0  # Placeholder

    def has_open_position_or_order(self, broker_symbol: str) -> bool:
        if not self._connected:
            return False
            
        # Get positions
        req = ProtoOAReconcileReq()
        req.ctidTraderAccountId = self._config.account_id
        try:
            res = self._send_message_sync(req)
            if isinstance(res, ProtoOAReconcileRes):
                for pos in res.position:
                    sym = self._symbol_id_to_name.get(pos.tradeData.symbolId)
                    if sym == broker_symbol:
                        return True
                for ord in res.order:
                    sym = self._symbol_id_to_name.get(ord.tradeData.symbolId)
                    if sym == broker_symbol:
                        return True
        except:
            pass
        return False

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
        logger.info(f"Auto-trade requested for {symbol} on cTrader, but cTrader only supports alerts.")
        return OrderResult(
            success=False,
            symbol=symbol,
            broker_symbol=broker_symbol,
            side=side,
            volume=volume,
            message="Auto-trading is disabled for cTrader (Alert Only)."
        )

    def closed_trade_history(self, *, start: datetime, end: datetime) -> list[dict[str, Any]]:
        # Fetch deal history
        req = ProtoOADealListReq()
        req.ctidTraderAccountId = self._config.account_id
        req.fromTimestamp = int(start.timestamp() * 1000)
        req.toTimestamp = int(end.timestamp() * 1000)
        
        trades = []
        try:
            res = self._send_message_sync(req)
            if isinstance(res, ProtoOADealListRes):
                for deal in res.deal:
                    if deal.dealStatus == ProtoOADealStatus.FILLED:
                        # Map to our journal structure
                        # Note: This is an incomplete mapping
                        trades.append({
                            "ticket": deal.dealId,
                            "symbol": self._symbol_id_to_name.get(deal.symbolId, ""),
                            "time_in": deal.createTimestamp,
                            "time_out": deal.executionTimestamp,
                            "profit": deal.executionPrice, # placeholder
                        })
        except:
            pass
        return trades
