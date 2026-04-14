"""
BINANCE DATA SERVICE
====================
Servicio separado para obtener datos históricos de Binance PRODUCTION
(sin autenticación, solo datos públicos)

IMPORTANTE: Este servicio SOLO lee datos, NO ejecuta trades.
Para trading se usa BinanceService con testnet.
"""

import pandas as pd
from binance.client import Client
from binance.exceptions import BinanceAPIException
from typing import Optional
from datetime import datetime, timedelta
from loguru import logger


class BinanceDataService:
    """
    Servicio para obtener datos de mercado de Binance Production (read-only)
    NO requiere API keys, usa endpoints públicos
    """

    def __init__(self):
        """Initialize Binance client for public data only (lazy — no ping)"""
        self._client = None
        logger.info("📊 Binance Data Service initialized (production, read-only)")

    @property
    def client(self):
        """Lazy init: create client on first use, skip ping to avoid IP ban on startup"""
        if self._client is None:
            import requests
            # Create client without the automatic ping()
            c = Client.__new__(Client)
            c.API_KEY = ""
            c.API_SECRET = ""
            c.session = c._init_session()
            c.timestamp_offset = 0
            c.API_URL = "https://api.binance.com/api"
            c.MARGIN_API_URL = "https://api.binance.com/sapi"
            c.WEBSITE_URL = "https://www.binance.com"
            c.FUTURES_URL = "https://fapi.binance.com/fapi"
            c.FUTURES_DATA_URL = "https://fapi.binance.com/futures/data"
            c.FUTURES_COIN_URL = "https://dapi.binance.com/dapi"
            c.FUTURES_COIN_DATA_URL = "https://dapi.binance.com/futures/data"
            c.OPTIONS_URL = "https://vapi.binance.com/vapi"
            c.OPTIONS_TESTNET_URL = "https://testnet.binanceops.com/vapi"
            c.PRIVATE_API_VERSION = "v3"
            c.PUBLIC_API_VERSION = "v3"
            c.MARGIN_API_VERSION = "v1"
            c.FUTURES_API_VERSION = "v1"
            c.FUTURES_API_VERSION2 = "v2"
            c.OPTIONS_API_VERSION = "v1"
            c.response = None
            c.testnet = False
            c.tld = "com"
            self._client = c
        return self._client

    def _init_session(self):
        """Fallback if client needs session init"""
        import requests
        session = requests.Session()
        session.headers.update({"Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        return session

    def get_historical_klines(
        self,
        symbol: str,
        interval: str = '1d',
        lookback_days: int = 250
    ) -> pd.DataFrame:
        """
        Get historical candlestick data from Binance PRODUCTION

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

            logger.debug(f"📊 Fetching {symbol} data (production, {lookback_days} days)")

            # Get klines from Binance PRODUCTION (public endpoint, no auth needed)
            klines = self.client.get_historical_klines(
                symbol=symbol,
                interval=interval,
                start_str=start_str
            )

            if not klines:
                logger.warning(f"⚠️  No data returned for {symbol}")
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

            logger.success(f"✅ Fetched {len(df)} candles for {symbol} (production)")
            return df

        except BinanceAPIException as e:
            logger.error(f"❌ Binance API error for {symbol}: {e}")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"❌ Failed to fetch data for {symbol}: {e}")
            return pd.DataFrame()

    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        Get current price for a symbol from production API

        Args:
            symbol: Trading pair

        Returns:
            Current price or None if failed
        """
        try:
            ticker = self.client.get_symbol_ticker(symbol=symbol)
            price = float(ticker['price'])
            logger.debug(f"💵 {symbol}: ${price:.2f} (production)")
            return price

        except Exception as e:
            logger.error(f"❌ Failed to get price for {symbol}: {e}")
            return None
