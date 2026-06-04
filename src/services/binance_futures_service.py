"""
BINANCE FUTURES SERVICE
=======================
Handles Binance USDM Perpetual Futures for SHORT/LONG positions.

Key differences from Spot:
- Different API endpoint (futures endpoint)
- Positions have leverage (default 1x to be conservative)
- Margin: USDT-settled
- Side: BUY to open LONG, SELL to open SHORT
- positionSide: LONG or SHORT (requires hedge mode)
- Use ONE-WAY mode: BUY = open long, SELL = open short

Supported operations:
- open_long(symbol, quantity, leverage)  -> market BUY
- open_short(symbol, quantity, leverage) -> market SELL
- close_long(symbol, quantity)           -> market SELL (close)
- close_short(symbol, quantity)          -> market BUY (close)
- get_position(symbol)                   -> current open position
- get_futures_balance()                  -> available USDT margin
- set_leverage(symbol, leverage)         -> set leverage for symbol
- cancel_all_orders(symbol)              -> cancel open futures orders
"""

import time
from typing import Dict, List, Optional, Tuple
from threading import Lock
from binance.client import Client
from binance.exceptions import BinanceAPIException
from loguru import logger

from config import settings


class BinanceFuturesService:
    """
    Service for Binance USDM Perpetual Futures trading.

    ONE-WAY mode (not hedge mode):
      - BUY  MARKET -> open long / reduce short
      - SELL MARKET -> open short / reduce long

    Always uses market orders to guarantee fills.
    Leverage defaults to 1x (conservative -- can be raised).
    """

    FUTURES_TESTNET_URL = "https://testnet.binancefuture.com/fapi"
    FUTURES_PROD_URL = "https://fapi.binance.com/fapi"

    def __init__(self, lazy_init: bool = True, default_leverage: int = 1):
        self._client: Optional[Client] = None
        self._initialized = False
        self.is_testnet = settings.is_testnet()
        self.default_leverage = default_leverage
        self._lock = Lock()
        self._leverage_cache: Dict[str, int] = {}  # symbol -> leverage set
        self._step_size_cache: Dict[str, float] = {}  # symbol -> stepSize
        self._backoff_until = 0.0

        if not lazy_init:
            self._ensure_client()
        else:
            logger.info("BinanceFuturesService created (lazy init)")

    def _ensure_client(self) -> Client:
        """Lazily initialize the Binance client for Futures."""
        if self._client is None:
            try:
                api_key, api_secret = settings.get_binance_credentials()
                self._client = Client(api_key, api_secret, {"timeout": 30})

                if self.is_testnet:
                    # Futures testnet uses a different base URL
                    self._client.FUTURES_URL = self.FUTURES_TESTNET_URL
                    logger.info("BinanceFuturesService: TESTNET mode")
                else:
                    logger.info("BinanceFuturesService: PRODUCTION mode")

                self._initialized = True

            except Exception as e:
                logger.error(f"Failed to init BinanceFuturesService: {e}")
                raise

        return self._client

    @property
    def client(self) -> Client:
        return self._ensure_client()

    def _wait_backoff(self):
        """Wait if we're in a rate-limit backoff period."""
        now = time.time()
        if now < self._backoff_until:
            wait = self._backoff_until - now
            logger.warning(f"Futures rate-limit backoff: {wait:.1f}s")
            time.sleep(wait)

    def _api_call(self, func, *args, max_retries: int = 3, **kwargs):
        """Execute a Futures API call with retry on rate-limit errors."""
        for attempt in range(max_retries + 1):
            try:
                self._wait_backoff()
                return func(*args, **kwargs)
            except BinanceAPIException as e:
                if e.code in (-1003, -1015):  # Rate limit / too many requests
                    backoff = 2 ** (attempt + 1)
                    self._backoff_until = time.time() + backoff
                    logger.warning(
                        f"Futures rate limit, retry {attempt+1}/{max_retries} in {backoff}s"
                    )
                    time.sleep(backoff)
                    continue
                raise
            except Exception as e:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise

    # ============================================
    # LEVERAGE
    # ============================================

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        """
        Set leverage for a symbol (e.g., 1x, 2x, 3x).
        Cached -- only calls API if leverage hasn't been set yet.
        """
        if self._leverage_cache.get(symbol) == leverage:
            return True
        try:
            self._api_call(
                self.client.futures_change_leverage,
                symbol=symbol,
                leverage=leverage,
            )
            self._leverage_cache[symbol] = leverage
            logger.info(f"Futures leverage set: {symbol} -> {leverage}x")
            return True
        except BinanceAPIException as e:
            logger.error(f"Failed to set leverage for {symbol}: {e}")
            return False

    # ============================================
    # ACCOUNT & POSITIONS
    # ============================================

    def get_futures_balance(self) -> float:
        """
        Get available USDT margin in futures wallet.
        Returns 0.0 on failure.
        """
        try:
            account = self._api_call(self.client.futures_account)
            for asset in account.get("assets", []):
                if asset["asset"] == "USDT":
                    return float(asset["availableBalance"])
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get futures balance: {e}")
            return 0.0

    def get_position(self, symbol: str) -> Optional[Dict]:
        """
        Get current futures position for a symbol.

        Returns:
            Dict with keys: symbol, positionAmt, entryPrice, unRealizedProfit, leverage
            positionAmt > 0 -> LONG, < 0 -> SHORT, == 0 -> no position
            Returns None on failure.
        """
        try:
            positions = self._api_call(
                self.client.futures_position_information,
                symbol=symbol,
            )
            for pos in positions:
                if pos["symbol"] == symbol:
                    return {
                        "symbol": symbol,
                        "positionAmt": float(pos["positionAmt"]),
                        "entryPrice": float(pos["entryPrice"]),
                        "unRealizedProfit": float(pos["unRealizedProfit"]),
                        "leverage": int(pos["leverage"]),
                        "liquidationPrice": float(pos.get("liquidationPrice", 0)),
                        "marginType": pos.get("marginType", "cross"),
                    }
            return None
        except Exception as e:
            logger.error(f"Failed to get position for {symbol}: {e}")
            return None

    def get_all_positions(self) -> List[Dict]:
        """Get all non-zero futures positions."""
        try:
            positions = self._api_call(self.client.futures_position_information)
            active = []
            for pos in positions:
                amt = float(pos.get("positionAmt", 0))
                if abs(amt) > 0:
                    active.append({
                        "symbol": pos["symbol"],
                        "positionAmt": amt,
                        "entryPrice": float(pos["entryPrice"]),
                        "unRealizedProfit": float(pos["unRealizedProfit"]),
                        "leverage": int(pos["leverage"]),
                        "side": "LONG" if amt > 0 else "SHORT",
                    })
            logger.info(f"Open futures positions: {len(active)}")
            return active
        except Exception as e:
            logger.error(f"Failed to get all futures positions: {e}")
            return []

    def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current futures mark price for a symbol."""
        try:
            ticker = self._api_call(
                self.client.futures_mark_price,
                symbol=symbol,
            )
            return float(ticker["markPrice"])
        except Exception as e:
            logger.error(f"Failed to get futures price for {symbol}: {e}")
            return None

    # ============================================
    # ORDER EXECUTION
    # ============================================

    def open_long(
        self, symbol: str, quantity: float, leverage: int = None
    ) -> Optional[Dict]:
        """
        Open a LONG position: market BUY order.
        Sets leverage first if not cached.

        Args:
            symbol: e.g., 'BTCUSDT'
            quantity: Amount in base asset (e.g., 0.001 BTC)
            leverage: Leverage (default: self.default_leverage)

        Returns:
            Order dict or None on failure.
        """
        lev = leverage or self.default_leverage
        self.set_leverage(symbol, lev)
        quantity = self.round_quantity(symbol, quantity)
        try:
            logger.info(f"Opening LONG: {symbol} qty={quantity} leverage={lev}x")
            order = self._api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side="BUY",
                type="MARKET",
                quantity=quantity,
            )
            logger.info(f"LONG opened: {symbol} orderId={order.get('orderId')}")
            return order
        except BinanceAPIException as e:
            logger.error(f"LONG open failed {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"LONG open error {symbol}: {e}")
            return None

    def open_short(
        self, symbol: str, quantity: float, leverage: int = None
    ) -> Optional[Dict]:
        """
        Open a SHORT position: market SELL order.
        Sets leverage first if not cached.

        Args:
            symbol: e.g., 'ETHUSDT'
            quantity: Amount in base asset
            leverage: Leverage (default: self.default_leverage)

        Returns:
            Order dict or None on failure.
        """
        lev = leverage or self.default_leverage
        self.set_leverage(symbol, lev)
        quantity = self.round_quantity(symbol, quantity)
        try:
            logger.info(f"Opening SHORT: {symbol} qty={quantity} leverage={lev}x")
            order = self._api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side="SELL",
                type="MARKET",
                quantity=quantity,
            )
            logger.info(f"SHORT opened: {symbol} orderId={order.get('orderId')}")
            return order
        except BinanceAPIException as e:
            logger.error(f"SHORT open failed {symbol}: {e}")
            return None
        except Exception as e:
            logger.error(f"SHORT open error {symbol}: {e}")
            return None

    def close_long(self, symbol: str, quantity: float) -> Optional[Dict]:
        """
        Close an existing LONG position: market SELL with reduceOnly=True.

        Args:
            symbol: Trading pair
            quantity: Amount to close (use get_position() to find positionAmt)

        Returns:
            Order dict or None on failure.
        """
        try:
            logger.info(f"Closing LONG: {symbol} qty={quantity}")
            order = self._api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side="SELL",
                type="MARKET",
                quantity=quantity,
                reduceOnly=True,
            )
            logger.info(f"LONG closed: {symbol}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Close LONG failed {symbol}: {e}")
            return None

    def close_short(self, symbol: str, quantity: float) -> Optional[Dict]:
        """
        Close an existing SHORT position: market BUY with reduceOnly=True.

        Note: quantity should be positive (absolute value of positionAmt).

        Args:
            symbol: Trading pair
            quantity: Amount to close (positive)

        Returns:
            Order dict or None on failure.
        """
        try:
            quantity = abs(quantity)
            logger.info(f"Closing SHORT: {symbol} qty={quantity}")
            order = self._api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side="BUY",
                type="MARKET",
                quantity=quantity,
                reduceOnly=True,
            )
            logger.info(f"SHORT closed: {symbol}")
            return order
        except BinanceAPIException as e:
            logger.error(f"Close SHORT failed {symbol}: {e}")
            return None

    def cancel_all_orders(self, symbol: str) -> bool:
        """Cancel all open futures orders for a symbol."""
        try:
            self._api_call(
                self.client.futures_cancel_all_open_orders,
                symbol=symbol,
            )
            logger.info(f"All futures orders cancelled: {symbol}")
            return True
        except Exception as e:
            logger.error(f"Cancel futures orders failed {symbol}: {e}")
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """Get all open futures orders."""
        try:
            if symbol:
                orders = self._api_call(
                    self.client.futures_get_open_orders,
                    symbol=symbol,
                )
            else:
                orders = self._api_call(self.client.futures_get_open_orders)
            return orders
        except Exception as e:
            logger.error(f"Failed to get open futures orders: {e}")
            return []

    def set_stop_loss(
        self, symbol: str, stop_price: float, side: str, quantity: float
    ) -> Optional[Dict]:
        """
        Place a STOP_MARKET order as stop-loss for an open position.

        Args:
            symbol: Trading pair
            stop_price: Trigger price
            side: 'SELL' to protect LONG, 'BUY' to protect SHORT
            quantity: Position size to close

        Returns:
            Order dict or None on failure.
        """
        try:
            logger.info(f"Setting SL: {symbol} {side} @ {stop_price}")
            order = self._api_call(
                self.client.futures_create_order,
                symbol=symbol,
                side=side,
                type="STOP_MARKET",
                stopPrice=str(stop_price),
                quantity=quantity,
                reduceOnly=True,
            )
            logger.info(f"SL placed: {symbol} orderId={order.get('orderId')}")
            return order
        except BinanceAPIException as e:
            logger.error(f"SL placement failed {symbol}: {e}")
            return None

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """
        Round quantity to the symbol's LOT_SIZE stepSize from Futures exchange info.
        Prevents -1111 precision errors. Caches stepSize per symbol to avoid
        repeated API calls (which could fail intermittently on testnet).
        """
        if symbol in self._step_size_cache:
            step_size = self._step_size_cache[symbol]
            precision = len(str(step_size).rstrip("0").split(".")[-1])
            return round(quantity - (quantity % step_size), precision)
        try:
            info = self._api_call(self.client.futures_exchange_info)
            for s in info.get("symbols", []):
                if s["symbol"] == symbol:
                    for f in s.get("filters", []):
                        if f["filterType"] == "LOT_SIZE":
                            step_size = float(f["stepSize"])
                            self._step_size_cache[symbol] = step_size
                            precision = len(str(step_size).rstrip("0").split(".")[-1])
                            return round(quantity - (quantity % step_size), precision)
            return quantity
        except Exception as e:
            logger.warning(f"Futures round_quantity failed for {symbol}: {e}")
            return quantity

    def test_connectivity(self) -> bool:
        """Test connectivity to Binance Futures API."""
        try:
            self._api_call(self.client.futures_ping)
            logger.info("Binance Futures API connected")
            return True
        except Exception as e:
            logger.error(f"Futures API connection failed: {e}")
            return False

    def is_connected(self) -> bool:
        return self._initialized
