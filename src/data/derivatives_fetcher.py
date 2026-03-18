"""
DERIVATIVES DATA FETCHER
=========================
Binance Futures public API (fapi.binance.com) - No auth needed.
- Funding rate
- Open interest + 24h change
- Long/short ratio
- Top trader long/short ratio
"""

import httpx
from typing import Dict, Optional
from loguru import logger


class DerivativesFetcher:
    """Fetches derivatives data from Binance Futures public API"""

    BASE_URL = "https://fapi.binance.com"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def get_funding_rate(self, symbol: str = "BTCUSDT") -> Optional[float]:
        """Get latest funding rate for a symbol"""
        try:
            url = f"{self.BASE_URL}/fapi/v1/fundingRate"
            params = {"symbol": symbol, "limit": 1}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data:
                    return float(data[0]["fundingRate"])
        except Exception as e:
            logger.warning(f"Failed to fetch funding rate for {symbol}: {e}")
        return None

    async def get_open_interest(self, symbol: str = "BTCUSDT") -> Optional[Dict[str, float]]:
        """Get open interest value and 24h change"""
        try:
            url = f"{self.BASE_URL}/fapi/v1/openInterest"
            params = {"symbol": symbol}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                oi = float(data["openInterest"])

            # Get OI history for 24h change
            hist_url = f"{self.BASE_URL}/futures/data/openInterestHist"
            hist_params = {"symbol": symbol, "period": "1h", "limit": 25}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(hist_url, params=hist_params)
                resp.raise_for_status()
                hist_data = resp.json()

            if hist_data and len(hist_data) >= 2:
                oi_24h_ago = float(hist_data[0]["sumOpenInterest"])
                oi_change_24h = (oi - oi_24h_ago) / oi_24h_ago if oi_24h_ago > 0 else 0.0
            else:
                oi_change_24h = 0.0

            return {"open_interest": oi, "oi_change_24h": oi_change_24h}

        except Exception as e:
            logger.warning(f"Failed to fetch open interest for {symbol}: {e}")
        return None

    async def get_long_short_ratio(self, symbol: str = "BTCUSDT") -> Optional[float]:
        """Get global long/short account ratio"""
        try:
            url = f"{self.BASE_URL}/futures/data/globalLongShortAccountRatio"
            params = {"symbol": symbol, "period": "1h", "limit": 1}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data:
                    return float(data[0]["longShortRatio"])
        except Exception as e:
            logger.warning(f"Failed to fetch long/short ratio for {symbol}: {e}")
        return None

    async def get_top_trader_ratio(self, symbol: str = "BTCUSDT") -> Optional[float]:
        """Get top trader long/short ratio (positions)"""
        try:
            url = f"{self.BASE_URL}/futures/data/topLongShortPositionRatio"
            params = {"symbol": symbol, "period": "1h", "limit": 1}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                if data:
                    return float(data[0]["longShortRatio"])
        except Exception as e:
            logger.warning(f"Failed to fetch top trader ratio for {symbol}: {e}")
        return None

    async def get_all_derivatives_data(self, symbol: str = "BTCUSDT") -> Dict[str, float]:
        """Get all derivatives indicators for a symbol"""
        import asyncio

        funding, oi_data, ls_ratio, top_ratio = await asyncio.gather(
            self.get_funding_rate(symbol),
            self.get_open_interest(symbol),
            self.get_long_short_ratio(symbol),
            self.get_top_trader_ratio(symbol),
            return_exceptions=True
        )

        result = {
            "funding_rate": funding if isinstance(funding, float) else 0.0,
            "open_interest": 0.0,
            "oi_change_24h": 0.0,
            "long_short_ratio": ls_ratio if isinstance(ls_ratio, float) else 1.0,
            "top_trader_ratio": top_ratio if isinstance(top_ratio, float) else 1.0,
        }

        if isinstance(oi_data, dict):
            result["open_interest"] = oi_data.get("open_interest", 0.0)
            result["oi_change_24h"] = oi_data.get("oi_change_24h", 0.0)

        return result
