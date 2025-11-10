"""
MACRO DATA FETCHER
==================
Obtiene datos macro para features del modelo:
- Fear & Greed Index
- S&P 500 (SPX)
- VIX (Volatility Index)
- Funding Rate
"""

import httpx
from typing import Dict, Optional
from datetime import datetime, timedelta
from loguru import logger
import asyncio


class MacroDataFetcher:
    """
    Fetches macro economic indicators for trading model
    """

    def __init__(self):
        """Initialize macro data fetcher"""
        self.fear_greed_url = "https://api.alternative.me/fng/"
        self.timeout = 10.0
        logger.info("✅ Macro Data Fetcher initialized")

    async def get_fear_greed_index(self) -> Optional[float]:
        """
        Get Fear & Greed Index from alternative.me

        Returns:
            Fear & Greed value (0-100), or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.fear_greed_url}?limit=1")
                response.raise_for_status()
                data = response.json()

                if 'data' in data and len(data['data']) > 0:
                    value = float(data['data'][0]['value'])
                    logger.debug(f"📊 Fear & Greed Index: {value}")
                    return value

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch Fear & Greed Index: {e}")

        return None

    async def get_funding_rate(self, ticker: str = "BTCUSDT") -> Optional[float]:
        """
        Get funding rate from Binance

        Args:
            ticker: Trading pair (default: BTCUSDT)

        Returns:
            Funding rate, or None if failed
        """
        try:
            # Binance funding rate endpoint
            url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={ticker}&limit=1"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                if len(data) > 0:
                    funding_rate = float(data[0]['fundingRate'])
                    logger.debug(f"📊 Funding Rate ({ticker}): {funding_rate}")
                    return funding_rate

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch funding rate: {e}")

        return None

    async def get_spx_data(self) -> Dict[str, Optional[float]]:
        """
        Get S&P 500 data

        Note: For production, you would use a paid API like Alpha Vantage or Yahoo Finance
        For now, we'll use placeholder values or free APIs

        Returns:
            Dict with {spx: float, spx_change_7d: float}
        """
        # Placeholder implementation
        # In production, integrate with:
        # - Yahoo Finance API
        # - Alpha Vantage
        # - Finnhub
        # - IEX Cloud

        try:
            # Using a free proxy endpoint (example - may not work in production)
            # Replace with your preferred financial data API

            # For now, return default values
            logger.debug("📊 Using default SPX values (integrate paid API for production)")

            return {
                'spx': 4500.0,  # Placeholder
                'spx_change_7d': 0.0  # Placeholder
            }

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch SPX data: {e}")
            return {'spx': 4500.0, 'spx_change_7d': 0.0}

    async def get_vix_data(self) -> Optional[float]:
        """
        Get VIX (Volatility Index) data

        Note: For production, integrate with financial data API

        Returns:
            VIX value, or None if failed
        """
        # Placeholder implementation
        # In production, integrate with financial data API

        try:
            logger.debug("📊 Using default VIX value (integrate paid API for production)")
            return 20.0  # Placeholder

        except Exception as e:
            logger.warning(f"⚠️ Failed to fetch VIX data: {e}")
            return 20.0

    async def get_all_macro_data(self, ticker: str = "BTCUSDT") -> Dict[str, float]:
        """
        Get all macro indicators at once

        Args:
            ticker: Ticker for funding rate

        Returns:
            Dict with all macro data
        """
        logger.info("📊 Fetching macro data...")

        # Fetch all data concurrently
        fear_greed_task = self.get_fear_greed_index()
        funding_rate_task = self.get_funding_rate(ticker)
        spx_task = self.get_spx_data()
        vix_task = self.get_vix_data()

        # Wait for all tasks
        fear_greed, funding_rate, spx_data, vix = await asyncio.gather(
            fear_greed_task,
            funding_rate_task,
            spx_task,
            vix_task,
            return_exceptions=True
        )

        # Handle exceptions
        if isinstance(fear_greed, Exception):
            fear_greed = 50.0  # Neutral
        if isinstance(funding_rate, Exception):
            funding_rate = 0.0
        if isinstance(spx_data, Exception):
            spx_data = {'spx': 4500.0, 'spx_change_7d': 0.0}
        if isinstance(vix, Exception):
            vix = 20.0

        macro_data = {
            'fear_greed': fear_greed or 50.0,
            'funding_rate': funding_rate or 0.0,
            'spx': spx_data.get('spx', 4500.0),
            'spx_change_7d': spx_data.get('spx_change_7d', 0.0),
            'vix': vix or 20.0,
            'timestamp': datetime.utcnow().isoformat()
        }

        logger.success(f"✅ Macro data fetched: Fear&Greed={macro_data['fear_greed']}, VIX={macro_data['vix']}")
        return macro_data

    def get_all_macro_data_sync(self, ticker: str = "BTCUSDT") -> Dict[str, float]:
        """
        Synchronous version of get_all_macro_data

        Args:
            ticker: Ticker for funding rate

        Returns:
            Dict with all macro data
        """
        return asyncio.run(self.get_all_macro_data(ticker))


# Global instance
macro_fetcher = MacroDataFetcher()
