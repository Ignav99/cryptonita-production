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
        """Initialize Binance client for public data only"""
        # Cliente sin autenticación (solo datos públicos)
        self.client = Client("", "")  # Empty keys for public endpoints
        logger.info("📊 Binance Data Service initialized (production, read-only)")

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
