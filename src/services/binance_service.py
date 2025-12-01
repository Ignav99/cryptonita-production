"""
BINANCE SERVICE
===============
Handles all Binance API interactions:
- Market data fetching
- Order execution
- Account information
- Supports both testnet and production

Includes:
- Lazy initialization (no API calls on startup)
- Price caching with TTL
- Rate limiting with backoff
- Batched price requests
"""

import pandas as pd
import time
from binance.client import Client
from binance.exceptions import BinanceAPIException
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger
from functools import lru_cache
from threading import Lock

from config import settings


class PriceCache:
    """Simple TTL cache for prices"""

    def __init__(self, ttl_seconds: int = 10):
        self.ttl = ttl_seconds
        self._cache: Dict[str, Tuple[float, float]] = {}  # symbol -> (price, timestamp)
        self._lock = Lock()

    def get(self, symbol: str) -> Optional[float]:
        """Get cached price if not expired"""
        with self._lock:
            if symbol in self._cache:
                price, cached_at = self._cache[symbol]
                if time.time() - cached_at < self.ttl:
                    return price
                del self._cache[symbol]
        return None

    def set(self, symbol: str, price: float):
        """Cache a price"""
        with self._lock:
            self._cache[symbol] = (price, time.time())

    def set_many(self, prices: Dict[str, float]):
        """Cache multiple prices at once"""
        with self._lock:
            now = time.time()
            for symbol, price in prices.items():
                self._cache[symbol] = (price, now)

    def clear(self):
        """Clear all cached prices"""
        with self._lock:
            self._cache.clear()


class RateLimiter:
    """Simple rate limiter with exponential backoff"""

    def __init__(self, max_requests_per_minute: int = 1000):
        self.max_rpm = max_requests_per_minute
        self._requests: List[float] = []
        self._lock = Lock()
        self._backoff_until = 0

    def wait_if_needed(self):
        """Block if we're rate limited or need backoff"""
        # Check backoff first
        now = time.time()
        if now < self._backoff_until:
            wait_time = self._backoff_until - now
            logger.warning(f"⏳ Rate limit backoff: waiting {wait_time:.1f}s")
            time.sleep(wait_time)

        with self._lock:
            now = time.time()
            # Remove requests older than 1 minute
            self._requests = [t for t in self._requests if now - t < 60]

            # If at limit, wait
            if len(self._requests) >= self.max_rpm:
                wait_time = 60 - (now - self._requests[0])
                if wait_time > 0:
                    logger.warning(f"⏳ Rate limit reached: waiting {wait_time:.1f}s")
                    time.sleep(wait_time)

            self._requests.append(time.time())

    def set_backoff(self, seconds: int):
        """Set a backoff period (e.g., after 429 error)"""
        self._backoff_until = time.time() + seconds
        logger.warning(f"⚠️ Rate limiter backoff set for {seconds}s")


class BinanceService:
    """
    Service for interacting with Binance API

    Features:
    - Lazy initialization (client created on first use)
    - Price caching (10s TTL by default)
    - Rate limiting (1000 requests/minute)
    - Automatic retry with backoff on rate limit errors
    """

    def __init__(self, lazy_init: bool = True):
        """
        Initialize Binance service

        Args:
            lazy_init: If True, don't connect to Binance until first API call
        """
        self._client: Optional[Client] = None
        self._initialized = False
        self.is_testnet = settings.is_testnet()

        # Caching and rate limiting
        self._price_cache = PriceCache(ttl_seconds=10)
        self._rate_limiter = RateLimiter(max_requests_per_minute=1000)
        self._symbol_info_cache: Dict[str, Dict] = {}  # Permanent cache for symbol info

        if not lazy_init:
            self._ensure_client()
        else:
            logger.info("🔄 BinanceService created (lazy init - no connection yet)")

    def _ensure_client(self) -> Client:
        """Lazily initialize the Binance client"""
        if self._client is None:
            try:
                api_key, api_secret = settings.get_binance_credentials()

                # Create client without auto-ping
                self._client = Client(api_key, api_secret, {"timeout": 30})

                # Set testnet if needed
                if self.is_testnet:
                    self._client.API_URL = 'https://testnet.binance.vision/api'
                    logger.info("🧪 Binance client initialized in TESTNET mode")
                else:
                    logger.info("💰 Binance client initialized in PRODUCTION mode")

                self._initialized = True

            except BinanceAPIException as e:
                if e.code == -1003:  # IP banned
                    logger.error(f"❌ IP banned by Binance: {e.message}")
                    logger.error("⚠️ The bot will continue with limited functionality (no Binance API)")
                    raise
                raise
            except Exception as e:
                logger.error(f"❌ Failed to initialize Binance client: {e}")
                raise

        return self._client

    @property
    def client(self) -> Client:
        """Get the Binance client (lazy initialization)"""
        return self._ensure_client()

    def _api_call_with_retry(self, func, *args, max_retries: int = 3, **kwargs):
        """
        Execute an API call with rate limiting and retry logic

        Args:
            func: The API function to call
            max_retries: Maximum number of retries on rate limit errors
        """
        for attempt in range(max_retries + 1):
            try:
                self._rate_limiter.wait_if_needed()
                return func(*args, **kwargs)

            except BinanceAPIException as e:
                if e.code == -1003:  # Rate limited / IP banned
                    if attempt < max_retries:
                        backoff = 2 ** (attempt + 1)  # 2, 4, 8 seconds
                        logger.warning(f"⚠️ Rate limited, retry {attempt + 1}/{max_retries} in {backoff}s")
                        self._rate_limiter.set_backoff(backoff)
                        time.sleep(backoff)
                        continue
                    else:
                        logger.error(f"❌ Rate limit exceeded after {max_retries} retries")
                raise
            except Exception as e:
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    logger.warning(f"⚠️ API error, retry {attempt + 1}/{max_retries} in {backoff}s: {e}")
                    time.sleep(backoff)
                    continue
                raise

    # ============================================
    # MARKET DATA
    # ============================================

    def get_historical_klines(
        self,
        symbol: str,
        interval: str = '1d',
        lookback_days: int = 250
    ) -> pd.DataFrame:
        """
        Get historical candlestick data

        Args:
            symbol: Trading pair (e.g., 'BTCUSDT')
            interval: Candlestick interval (1m, 5m, 1h, 1d, etc.)
            lookback_days: Number of days to look back

        Returns:
            DataFrame with OHLCV data
        """
        try:
            # Calculate start time
            start_time = datetime.now() - timedelta(days=lookback_days)
            start_str = start_time.strftime('%Y-%m-%d')

            logger.debug(f"📊 Fetching {symbol} data ({interval}, {lookback_days} days)")

            # Get klines from Binance with retry
            klines = self._api_call_with_retry(
                self.client.get_historical_klines,
                symbol=symbol,
                interval=interval,
                start_str=start_str
            )

            if not klines:
                logger.warning(f"⚠️ No data returned for {symbol}")
                return pd.DataFrame()

            # Convert to DataFrame
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_base',
                'taker_buy_quote', 'ignore'
            ])

            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            # Convert price columns to float
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)

            # Keep only necessary columns
            df = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

            logger.success(f"✅ Fetched {len(df)} candles for {symbol}")
            return df

        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error for {symbol}: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ Failed to fetch data for {symbol}: {e}")
            return pd.DataFrame()

    def get_current_price(self, symbol: str, use_cache: bool = True) -> Optional[float]:
        """
        Get current price for a symbol

        Args:
            symbol: Trading pair
            use_cache: Whether to use cached price if available

        Returns:
            Current price or None if failed
        """
        try:
            # Check cache first
            if use_cache:
                cached = self._price_cache.get(symbol)
                if cached is not None:
                    logger.debug(f"💵 {symbol}: ${cached:.2f} (cached)")
                    return cached

            ticker = self._api_call_with_retry(
                self.client.get_symbol_ticker,
                symbol=symbol
            )
            price = float(ticker['price'])

            # Cache the price
            self._price_cache.set(symbol, price)

            logger.debug(f"💵 {symbol}: ${price:.2f}")
            return price

        except Exception as e:
            logger.error(f"❌ Failed to get price for {symbol}: {e}")
            return None

    def get_multiple_prices(self, symbols: List[str] = None) -> Dict[str, float]:
        """
        Get current prices for multiple symbols efficiently (single API call)

        Args:
            symbols: List of trading pairs (if None, gets all)

        Returns:
            Dict mapping symbol -> price
        """
        try:
            tickers = self._api_call_with_retry(self.client.get_all_tickers)

            # Convert to dict
            if symbols:
                prices = {
                    ticker['symbol']: float(ticker['price'])
                    for ticker in tickers
                    if ticker['symbol'] in symbols
                }
            else:
                prices = {
                    ticker['symbol']: float(ticker['price'])
                    for ticker in tickers
                }

            # Cache all prices
            self._price_cache.set_many(prices)

            logger.success(f"✅ Fetched prices for {len(prices)} symbols")
            return prices

        except Exception as e:
            logger.error(f"❌ Failed to fetch multiple prices: {e}")
            return {}

    def get_24h_ticker(self, symbol: str) -> Dict:
        """
        Get 24h ticker statistics

        Args:
            symbol: Trading pair

        Returns:
            Dict with 24h stats
        """
        try:
            ticker = self._api_call_with_retry(
                self.client.get_ticker,
                symbol=symbol
            )

            return {
                'symbol': ticker['symbol'],
                'price_change': float(ticker['priceChange']),
                'price_change_pct': float(ticker['priceChangePercent']),
                'volume': float(ticker['volume']),
                'high': float(ticker['highPrice']),
                'low': float(ticker['lowPrice']),
            }

        except Exception as e:
            logger.error(f"❌ Failed to get 24h ticker for {symbol}: {e}")
            return {}

    # ============================================
    # ACCOUNT INFO
    # ============================================

    def get_account_balance(self) -> Dict[str, float]:
        """
        Get account balances

        Returns:
            Dict mapping asset -> balance
        """
        try:
            account = self._api_call_with_retry(self.client.get_account)

            balances = {
                balance['asset']: {
                    'free': float(balance['free']),
                    'locked': float(balance['locked']),
                    'total': float(balance['free']) + float(balance['locked'])
                }
                for balance in account['balances']
                if float(balance['free']) > 0 or float(balance['locked']) > 0
            }

            logger.success(f"✅ Account has {len(balances)} assets")
            return balances

        except Exception as e:
            logger.error(f"❌ Failed to get account balance: {e}")
            return {}

    def get_usdt_balance(self) -> float:
        """
        Get USDT balance

        Returns:
            Available USDT balance
        """
        try:
            balances = self.get_account_balance()
            if 'USDT' in balances:
                return balances['USDT']['free']
            return 0.0

        except Exception as e:
            logger.error(f"❌ Failed to get USDT balance: {e}")
            return 0.0

    # ============================================
    # TRADING - ORDER EXECUTION
    # ============================================

    def create_market_buy_order(
        self,
        symbol: str,
        quantity: float
    ) -> Optional[Dict]:
        """
        Create a market buy order

        Args:
            symbol: Trading pair
            quantity: Amount to buy (in base asset)

        Returns:
            Order info dict or None if failed
        """
        try:
            logger.info(f"🛒 Creating MARKET BUY order: {symbol} x {quantity}")

            order = self._api_call_with_retry(
                self.client.order_market_buy,
                symbol=symbol,
                quantity=quantity
            )

            logger.success(f"✅ Order executed: {order['orderId']}")
            return order

        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error on buy: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to create buy order: {e}")
            return None

    def create_market_sell_order(
        self,
        symbol: str,
        quantity: float
    ) -> Optional[Dict]:
        """
        Create a market sell order

        Args:
            symbol: Trading pair
            quantity: Amount to sell (in base asset)

        Returns:
            Order info dict or None if failed
        """
        try:
            logger.info(f"💸 Creating MARKET SELL order: {symbol} x {quantity}")

            order = self._api_call_with_retry(
                self.client.order_market_sell,
                symbol=symbol,
                quantity=quantity
            )

            logger.success(f"✅ Order executed: {order['orderId']}")
            return order

        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error on sell: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to create sell order: {e}")
            return None

    def create_limit_buy_order(
        self,
        symbol: str,
        quantity: float,
        price: float
    ) -> Optional[Dict]:
        """
        Create a limit buy order

        Args:
            symbol: Trading pair
            quantity: Amount to buy
            price: Limit price

        Returns:
            Order info dict or None if failed
        """
        try:
            logger.info(f"🛒 Creating LIMIT BUY order: {symbol} x {quantity} @ ${price}")

            order = self._api_call_with_retry(
                self.client.order_limit_buy,
                symbol=symbol,
                quantity=quantity,
                price=str(price)
            )

            logger.success(f"✅ Limit order placed: {order['orderId']}")
            return order

        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error on limit buy: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to create limit buy order: {e}")
            return None

    def create_oco_order(
        self,
        symbol: str,
        quantity: float,
        price: float,
        stop_price: float,
        stop_limit_price: float
    ) -> Optional[Dict]:
        """
        Create OCO (One-Cancels-Other) order for take profit + stop loss

        Args:
            symbol: Trading pair
            quantity: Amount to sell
            price: Take profit price
            stop_price: Stop loss trigger price
            stop_limit_price: Stop loss limit price

        Returns:
            Order info dict or None if failed
        """
        try:
            logger.info(f"🎯 Creating OCO order: {symbol} TP=${price} SL=${stop_price}")

            order = self._api_call_with_retry(
                self.client.create_oco_order,
                symbol=symbol,
                side='SELL',
                quantity=quantity,
                price=str(price),
                stopPrice=str(stop_price),
                stopLimitPrice=str(stop_limit_price),
                stopLimitTimeInForce='GTC'
            )

            logger.success(f"✅ OCO order placed: {order['orderListId']}")
            return order

        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error on OCO: {e}")
            return None
        except Exception as e:
            logger.error(f"❌ Failed to create OCO order: {e}")
            return None

    def cancel_order(self, symbol: str, order_id: int) -> bool:
        """
        Cancel an open order

        Args:
            symbol: Trading pair
            order_id: Order ID to cancel

        Returns:
            True if successful, False otherwise
        """
        try:
            self._api_call_with_retry(
                self.client.cancel_order,
                symbol=symbol,
                orderId=order_id
            )
            logger.success(f"✅ Order {order_id} cancelled")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to cancel order {order_id}: {e}")
            return False

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """
        Get open orders

        Args:
            symbol: Optional symbol filter

        Returns:
            List of open orders
        """
        try:
            if symbol:
                orders = self._api_call_with_retry(
                    self.client.get_open_orders,
                    symbol=symbol
                )
            else:
                orders = self._api_call_with_retry(self.client.get_open_orders)

            logger.info(f"📋 Found {len(orders)} open orders")
            return orders

        except Exception as e:
            logger.error(f"❌ Failed to get open orders: {e}")
            return []

    # ============================================
    # UTILITIES
    # ============================================

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """
        Get trading rules and info for a symbol (cached permanently)

        Args:
            symbol: Trading pair

        Returns:
            Symbol info dict
        """
        try:
            # Check permanent cache first
            if symbol in self._symbol_info_cache:
                return self._symbol_info_cache[symbol]

            info = self._api_call_with_retry(
                self.client.get_symbol_info,
                symbol
            )

            # Cache permanently (symbol info rarely changes)
            if info:
                self._symbol_info_cache[symbol] = info

            return info

        except Exception as e:
            logger.error(f"❌ Failed to get symbol info for {symbol}: {e}")
            return None

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """
        Round quantity according to symbol's step size

        Args:
            symbol: Trading pair
            quantity: Raw quantity

        Returns:
            Rounded quantity
        """
        try:
            info = self.get_symbol_info(symbol)
            if not info:
                return quantity

            # Get LOT_SIZE filter
            for filter in info['filters']:
                if filter['filterType'] == 'LOT_SIZE':
                    step_size = float(filter['stepSize'])

                    # Round to step size
                    precision = len(str(step_size).rstrip('0').split('.')[-1])
                    rounded = round(quantity - (quantity % step_size), precision)

                    return rounded

            return quantity

        except Exception as e:
            logger.error(f"❌ Failed to round quantity: {e}")
            return quantity

    def round_price(self, symbol: str, price: float) -> float:
        """
        Round price according to symbol's tick size

        Args:
            symbol: Trading pair
            price: Raw price

        Returns:
            Rounded price
        """
        try:
            info = self.get_symbol_info(symbol)
            if not info:
                return round(price, 2)  # Default to 2 decimals

            # Get PRICE_FILTER
            for filter in info['filters']:
                if filter['filterType'] == 'PRICE_FILTER':
                    tick_size = float(filter['tickSize'])

                    # Round to tick size
                    precision = len(str(tick_size).rstrip('0').split('.')[-1])
                    rounded = round(price - (price % tick_size), precision)

                    return rounded

            return round(price, 2)  # Default fallback

        except Exception as e:
            logger.error(f"❌ Failed to round price: {e}")
            return round(price, 2)

    def get_all_positions(self) -> List[Dict]:
        """
        Get all current positions (non-zero balances) with current prices

        OPTIMIZED: Uses batched price fetch instead of per-asset API calls

        Returns:
            List of position dicts with balance and value info
        """
        try:
            # Get all balances (single API call)
            balances = self.get_account_balance()

            # Valid crypto assets (exclude fiat and stablecoins that don't have USDT pairs)
            SKIP_ASSETS = {'USDT', 'TRY', 'ZAR', 'UAH', 'BRL', 'DAI', 'EUR', 'GBP', 'AUD', 'NGN', 'RUB', 'PLN', 'ARS', 'BIDR', 'TUSD', 'USDC', 'BUSD', 'UST'}

            # Filter valid assets
            valid_assets = {
                asset: balance for asset, balance in balances.items()
                if asset not in SKIP_ASSETS and balance['total'] >= 0.0001
            }

            if not valid_assets:
                return []

            # Build list of symbols to fetch
            symbols = [f"{asset}USDT" for asset in valid_assets.keys()]

            # Get all prices in ONE API call
            all_prices = self.get_multiple_prices(symbols)

            positions = []
            for asset, balance_info in valid_assets.items():
                symbol = f"{asset}USDT"

                if symbol not in all_prices:
                    continue

                current_price = all_prices[symbol]
                total_value = balance_info['total'] * current_price

                positions.append({
                    'asset': asset,
                    'symbol': symbol,
                    'quantity': balance_info['total'],
                    'free': balance_info['free'],
                    'locked': balance_info['locked'],
                    'current_price': current_price,
                    'total_value_usdt': total_value
                })

            logger.info(f"📊 Found {len(positions)} open positions")
            return positions

        except Exception as e:
            logger.error(f"❌ Failed to get positions: {e}")
            return []

    def get_total_portfolio_value(self) -> Dict[str, float]:
        """
        Get total portfolio value in USDT

        Returns:
            Dict with usdt_balance, positions_value, total_value
        """
        try:
            # Get USDT balance
            usdt_balance = self.get_usdt_balance()

            # Get all positions value (uses batched price fetch)
            positions = self.get_all_positions()
            positions_value = sum(pos['total_value_usdt'] for pos in positions)

            total_value = usdt_balance + positions_value

            return {
                'usdt_balance': usdt_balance,
                'positions_value': positions_value,
                'total_value': total_value,
                'positions_count': len(positions)
            }

        except Exception as e:
            logger.error(f"❌ Failed to get portfolio value: {e}")
            return {
                'usdt_balance': 0.0,
                'positions_value': 0.0,
                'total_value': 0.0,
                'positions_count': 0
            }

    def test_connectivity(self) -> bool:
        """
        Test Binance API connectivity

        Returns:
            True if connected, False otherwise
        """
        try:
            self._api_call_with_retry(self.client.ping)
            logger.success("✅ Binance API connection successful")
            return True

        except Exception as e:
            logger.error(f"❌ Binance API connection failed: {e}")
            return False

    def is_connected(self) -> bool:
        """Check if the service has been initialized"""
        return self._initialized
