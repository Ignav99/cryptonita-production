"""
BINANCE SERVICE
===============
Handles all Binance API interactions:
- Market data fetching
- Order execution
- Account information
- Supports both testnet and production
"""

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from loguru import logger

from config import settings


class BinanceService:
    """
    Service for interacting with Binance API
    """

    def __init__(self):
        """Initialize Binance client"""

        # Get appropriate credentials based on mode
        api_key, api_secret = settings.get_binance_credentials()

        # Create client
        self.client = Client(api_key, api_secret)

        # Set testnet if needed
        if settings.is_testnet():
            self.client.API_URL = 'https://testnet.binance.vision/api'
            logger.info("🧪 Binance client initialized in TESTNET mode")
        else:
            logger.info("💰 Binance client initialized in PRODUCTION mode")

        self.is_testnet = settings.is_testnet()
        self._symbol_info_cache: Dict[str, Dict] = {}  # Cache to avoid repeated API calls

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

            # Get klines from Binance
            klines = self.client.get_historical_klines(
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

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol

        Args:
            symbol: Trading pair

        Returns:
            Current price or None if failed
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])
            logger.debug(f"💵 {symbol}: ${price:.2f}")
            return price

        except Exception as e:
            logger.error(f"❌ Failed to get price for {symbol}: {e}")
            return None

    def get_multiple_prices(self, symbols: List[str]) -> Dict[str, float]:
        """
        Get current prices for multiple symbols

        Args:
            symbols: List of trading pairs

        Returns:
            Dict mapping symbol -> price
        """
        try:
            tickers = self.client.get_all_tickers()

            # Convert to dict
            prices = {
                ticker['symbol']: float(ticker['price'])
                for ticker in tickers
                if ticker['symbol'] in symbols
            }

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
            ticker = self.client.get_ticker(symbol=symbol)

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
            account = self.client.get_account()

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

            order = self.client.order_market_buy(
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

            order = self.client.order_market_sell(
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

            order = self.client.order_limit_buy(
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

            order = self.client.create_oco_order(
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
            self.client.cancel_order(symbol=symbol, orderId=order_id)
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
                orders = self.client.get_open_orders(symbol=symbol)
            else:
                orders = self.client.get_open_orders()

            logger.info(f"📋 Found {len(orders)} open orders")
            return orders

        except Exception as e:
            logger.error(f"❌ Failed to get open orders: {e}")
            return []

    # ============================================
    # UTILITIES
    # ============================================

    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        """Get trading rules for a symbol (cached)"""
        if symbol in self._symbol_info_cache:
            return self._symbol_info_cache[symbol]
        try:
            info = self.client.get_symbol_info(symbol)
            if info:
                self._symbol_info_cache[symbol] = info
            return info
        except Exception as e:
            logger.error(f"Failed to get symbol info for {symbol}: {e}")
            return None

    def _get_filter(self, symbol: str, filter_type: str) -> Optional[Dict]:
        """Get a specific filter from symbol info"""
        info = self.get_symbol_info(symbol)
        if not info:
            return None
        for f in info['filters']:
            if f['filterType'] == filter_type:
                return f
        return None

    def round_quantity(self, symbol: str, quantity: float) -> float:
        """Round quantity to LOT_SIZE step size"""
        try:
            lot_filter = self._get_filter(symbol, 'LOT_SIZE')
            if not lot_filter:
                return quantity

            step_size = float(lot_filter['stepSize'])
            min_qty = float(lot_filter['minQty'])

            # Round down to step size
            precision = max(0, len(str(step_size).rstrip('0').split('.')[-1]) if '.' in str(step_size) else 0)
            rounded = round(quantity - (quantity % step_size), precision)

            if rounded < min_qty:
                return 0.0

            return rounded

        except Exception as e:
            logger.error(f"Failed to round quantity: {e}")
            return quantity

    def round_price(self, symbol: str, price: float) -> Optional[float]:
        """Round price to PRICE_FILTER tick size"""
        try:
            price_filter = self._get_filter(symbol, 'PRICE_FILTER')
            if not price_filter:
                return price

            tick_size = float(price_filter['tickSize'])
            if tick_size <= 0:
                return price

            precision = max(0, len(str(tick_size).rstrip('0').split('.')[-1]) if '.' in str(tick_size) else 0)
            rounded = round(price - (price % tick_size), precision)

            return rounded

        except Exception as e:
            logger.error(f"Failed to round price: {e}")
            return price

    def check_min_notional(self, symbol: str, quantity: float, price: float) -> bool:
        """Check if order meets MIN_NOTIONAL requirement"""
        try:
            notional_filter = self._get_filter(symbol, 'MIN_NOTIONAL') or self._get_filter(symbol, 'NOTIONAL')
            if not notional_filter:
                return True

            min_notional = float(notional_filter.get('minNotional', 0))
            notional = quantity * price
            return notional >= min_notional

        except Exception:
            return True

    def test_connectivity(self) -> bool:
        """
        Test Binance API connectivity

        Returns:
            True if connected, False otherwise
        """
        try:
            self.client.ping()
            logger.success("✅ Binance API connection successful")
            return True

        except Exception as e:
            logger.error(f"❌ Binance API connection failed: {e}")
            return False
