"""
MACRO DATA FETCHER
==================
Obtiene datos macro para features del modelo:
- Fear & Greed Index
- S&P 500 (SPX) via Yahoo Finance
- VIX (Volatility Index) via Yahoo Finance
- Funding Rate
"""

import httpx
from typing import Dict, Optional
from datetime import datetime, timezone
from loguru import logger
import asyncio


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MacroDataFetcher:
    """Fetches macro economic indicators for trading model"""

    def __init__(self):
        self.fear_greed_url = "https://api.alternative.me/fng/"
        self.timeout = 15.0
        logger.info("Macro Data Fetcher initialized")

    async def get_fear_greed_index(self) -> Optional[float]:
        """Get Fear & Greed Index from alternative.me (0-100)"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.fear_greed_url}?limit=1")
                response.raise_for_status()
                data = response.json()

                if 'data' in data and len(data['data']) > 0:
                    value = float(data['data'][0]['value'])
                    logger.debug(f"Fear & Greed Index: {value}")
                    return value

        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed Index: {e}")

        return None

    async def get_funding_rate(self, ticker: str = "BTCUSDT") -> Optional[float]:
        """Get funding rate from Binance"""
        try:
            url = f"https://fapi.binance.com/fapi/v1/fundingRate?symbol={ticker}&limit=1"

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                if len(data) > 0:
                    funding_rate = float(data[0]['fundingRate'])
                    logger.debug(f"Funding Rate ({ticker}): {funding_rate}")
                    return funding_rate

        except Exception as e:
            logger.warning(f"Failed to fetch funding rate: {e}")

        return None

    async def get_spx_data(self) -> Dict[str, Optional[float]]:
        """
        Get S&P 500 data via Yahoo Finance free endpoint.
        Falls back to defaults if unavailable.
        """
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=10d"
            headers = {"User-Agent": "Mozilla/5.0"}

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                chart = data.get('chart', {}).get('result', [{}])[0]
                closes = chart.get('indicators', {}).get('quote', [{}])[0].get('close', [])

                # Filter out None values
                closes = [c for c in closes if c is not None]

                if len(closes) >= 2:
                    spx_current = closes[-1]
                    # Calculate 7d change (or available range)
                    spx_old = closes[0]
                    spx_change_7d = (spx_current - spx_old) / spx_old if spx_old else 0.0
                    logger.debug(f"SPX: {spx_current:.0f}, 7d change: {spx_change_7d:.4f}")
                    return {'spx': spx_current, 'spx_change_7d': spx_change_7d}

        except Exception as e:
            logger.warning(f"Failed to fetch SPX data: {e}")

        return {'spx': None, 'spx_change_7d': None}

    async def get_vix_data(self) -> Optional[float]:
        """Get VIX (Volatility Index) via Yahoo Finance"""
        try:
            url = "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=2d"
            headers = {"User-Agent": "Mozilla/5.0"}

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                chart = data.get('chart', {}).get('result', [{}])[0]
                closes = chart.get('indicators', {}).get('quote', [{}])[0].get('close', [])
                closes = [c for c in closes if c is not None]

                if closes:
                    vix = closes[-1]
                    logger.debug(f"VIX: {vix:.2f}")
                    return vix

        except Exception as e:
            logger.warning(f"Failed to fetch VIX data: {e}")

        return None

    async def get_all_macro_data(self, ticker: str = "BTCUSDT") -> Dict[str, float]:
        """Get all macro indicators concurrently"""
        logger.info("Fetching macro data...")

        # Fetch all data concurrently
        fear_greed, funding_rate, spx_data, vix = await asyncio.gather(
            self.get_fear_greed_index(),
            self.get_funding_rate(ticker),
            self.get_spx_data(),
            self.get_vix_data(),
            return_exceptions=True
        )

        # Handle exceptions from gather
        if isinstance(fear_greed, Exception):
            fear_greed = None
        if isinstance(funding_rate, Exception):
            funding_rate = None
        if isinstance(spx_data, Exception):
            spx_data = {'spx': None, 'spx_change_7d': None}
        if isinstance(vix, Exception):
            vix = None

        # Use explicit None checks (not truthiness) to preserve 0 values
        macro_data = {
            'fear_greed': fear_greed if fear_greed is not None else 50.0,
            'funding_rate': funding_rate if funding_rate is not None else 0.0,
            'spx': spx_data.get('spx') if spx_data.get('spx') is not None else 4500.0,
            'spx_change_7d': spx_data.get('spx_change_7d') if spx_data.get('spx_change_7d') is not None else 0.0,
            'vix': vix if vix is not None else 20.0,
            'timestamp': _utcnow().isoformat()
        }

        logger.success(f"Macro data: Fear&Greed={macro_data['fear_greed']}, "
                       f"SPX={macro_data['spx']:.0f}, VIX={macro_data['vix']:.1f}, "
                       f"Funding={macro_data['funding_rate']:.6f}")
        return macro_data

    def get_all_macro_data_sync(self, ticker: str = "BTCUSDT") -> Dict[str, float]:
        """
        Synchronous wrapper - safe to call from any context.
        Runs the async method in a separate thread if already in an event loop.
        """
        import concurrent.futures

        def _run_in_new_loop():
            new_loop = asyncio.new_event_loop()
            try:
                return new_loop.run_until_complete(self.get_all_macro_data(ticker))
            finally:
                new_loop.close()

        try:
            asyncio.get_running_loop()
            # We're inside a running event loop - run in a thread with its own loop
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run_in_new_loop)
                return future.result(timeout=30)
        except RuntimeError:
            # No event loop running - safe to use asyncio.run()
            return asyncio.run(self.get_all_macro_data(ticker))


# Global instance
macro_fetcher = MacroDataFetcher()
