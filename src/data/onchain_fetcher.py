"""
ON-CHAIN DATA FETCHER
======================
CoinMetrics Community API (free, 1000 req/day)
- MVRV ratio
- NVT signal
- Active addresses
- Hash rate
"""

import httpx
from typing import Dict, Optional
from loguru import logger

# CoinMetrics asset mapping
ASSET_MAP = {
    "BTC": "btc",
    "ETH": "eth",
    "BTCUSDT": "btc",
    "ETHUSDT": "eth",
}


class OnChainFetcher:
    """Fetches on-chain metrics from CoinMetrics Community API"""

    BASE_URL = "https://community-api.coinmetrics.io/v4"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def _resolve_asset(self, asset: str) -> str:
        return ASSET_MAP.get(asset.upper(), asset.lower())

    async def _fetch_metric(self, asset: str, metric: str) -> Optional[float]:
        """Fetch a single metric from CoinMetrics"""
        try:
            cm_asset = self._resolve_asset(asset)
            url = f"{self.BASE_URL}/timeseries/asset-metrics"
            params = {
                "assets": cm_asset,
                "metrics": metric,
                "frequency": "1d",
                "page_size": 1,
                "sort": "time",
                "sort_direction": "descending",
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
                rows = data.get("data", [])
                if rows and metric in rows[0]:
                    return float(rows[0][metric])
        except Exception as e:
            logger.warning(f"Failed to fetch {metric} for {asset}: {e}")
        return None

    async def get_mvrv(self, asset: str = "BTC") -> Optional[float]:
        """Market Value to Realized Value ratio"""
        return await self._fetch_metric(asset, "CapMVRVCur")

    async def get_nvt(self, asset: str = "BTC") -> Optional[float]:
        """Network Value to Transactions signal"""
        return await self._fetch_metric(asset, "NVTAdj")

    async def get_active_addresses(self, asset: str = "BTC") -> Optional[float]:
        """Active address count (daily)"""
        return await self._fetch_metric(asset, "AdrActCnt")

    async def get_hash_rate(self, asset: str = "BTC") -> Optional[float]:
        """Hash rate (BTC only)"""
        return await self._fetch_metric(asset, "HashRate")

    async def get_all_onchain_data(self, asset: str = "BTC") -> Dict[str, float]:
        """Get all on-chain metrics"""
        import asyncio

        mvrv, nvt, active_addr, hash_rate = await asyncio.gather(
            self.get_mvrv(asset),
            self.get_nvt(asset),
            self.get_active_addresses(asset),
            self.get_hash_rate(asset),
            return_exceptions=True
        )

        return {
            "mvrv_ratio": mvrv if isinstance(mvrv, (int, float)) else 1.0,
            "nvt_signal": nvt if isinstance(nvt, (int, float)) else 0.0,
            "active_addresses": active_addr if isinstance(active_addr, (int, float)) else 0.0,
            "hash_rate": hash_rate if isinstance(hash_rate, (int, float)) else 0.0,
        }
