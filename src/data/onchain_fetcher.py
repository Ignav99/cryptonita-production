"""
ON-CHAIN DATA FETCHER
======================
Replaces broken CoinMetrics API with free alternatives:
- Blockchain.com API (no auth): hash rate, active addresses, tx data
- Mempool.space API (no auth): hash rate alternative
- MVRV/NVT: proxy calculated or NaN (tree models handle it)
"""

import asyncio
import httpx
from typing import Dict, Optional
from loguru import logger


class OnChainFetcher:
    """Fetches on-chain metrics from free public APIs"""

    BLOCKCHAIN_URL = "https://api.blockchain.info"
    MEMPOOL_URL = "https://mempool.space/api/v1"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def get_hash_rate(self, asset: str = "BTC") -> Optional[float]:
        """Hash rate from Blockchain.com (BTC only, TH/s)"""
        if asset.upper() not in ("BTC", "BTCUSDT"):
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.BLOCKCHAIN_URL}/q/hashrate")
                if resp.status_code == 200:
                    # Returns hash rate in GH/s, convert to TH/s
                    val = float(resp.text.strip())
                    return val / 1000.0
        except Exception as e:
            logger.debug(f"Blockchain.com hash rate failed: {e}")

        # Fallback: Mempool.space
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.MEMPOOL_URL}/mining/hashrate/1w")
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("hashrates"):
                        latest = data["hashrates"][-1]
                        return latest.get("avgHashrate", 0) / 1e12  # H/s to TH/s
        except Exception as e:
            logger.debug(f"Mempool.space hash rate failed: {e}")

        return None

    async def get_active_addresses(self, asset: str = "BTC") -> Optional[float]:
        """Active addresses from Blockchain.com (BTC only)"""
        if asset.upper() not in ("BTC", "BTCUSDT"):
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.BLOCKCHAIN_URL}/charts/n-unique-addresses",
                    params={"timespan": "1days", "format": "json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    values = data.get("values", [])
                    if values:
                        return float(values[-1].get("y", 0))
        except Exception as e:
            logger.debug(f"Blockchain.com active addresses failed: {e}")
        return None

    async def get_tx_count(self, asset: str = "BTC") -> Optional[float]:
        """Transaction count from Blockchain.com (BTC only)"""
        if asset.upper() not in ("BTC", "BTCUSDT"):
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.BLOCKCHAIN_URL}/q/24hrtransactioncount")
                if resp.status_code == 200:
                    return float(resp.text.strip())
        except Exception as e:
            logger.debug(f"Blockchain.com tx count failed: {e}")
        return None

    async def get_market_cap(self, asset: str = "BTC") -> Optional[float]:
        """Market cap from Blockchain.com (BTC only)"""
        if asset.upper() not in ("BTC", "BTCUSDT"):
            return None
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.BLOCKCHAIN_URL}/q/marketcap")
                if resp.status_code == 200:
                    return float(resp.text.strip())
        except Exception as e:
            logger.debug(f"Blockchain.com market cap failed: {e}")
        return None

    async def get_mvrv(self, asset: str = "BTC") -> Optional[float]:
        """MVRV proxy — NaN (no free reliable source). Tree models handle NaN."""
        return None

    async def get_nvt(self, asset: str = "BTC") -> Optional[float]:
        """NVT proxy — calculated from market_cap / (tx_count * avg_tx_value)"""
        if asset.upper() not in ("BTC", "BTCUSDT"):
            return None
        try:
            market_cap, tx_count = await asyncio.gather(
                self.get_market_cap(asset),
                self.get_tx_count(asset),
                return_exceptions=True,
            )
            if (
                isinstance(market_cap, (int, float))
                and isinstance(tx_count, (int, float))
                and tx_count > 0
            ):
                # Simplified NVT = market_cap / daily_tx_volume
                # Without exact tx volume, use tx_count as proxy
                return market_cap / (tx_count * 1000)  # rough estimate
        except Exception as e:
            logger.debug(f"NVT calculation failed: {e}")
        return None

    async def get_all_onchain_data(self, asset: str = "BTC") -> Dict[str, float]:
        """Get all on-chain metrics"""
        import numpy as np

        mvrv, nvt, active_addr, hash_rate = await asyncio.gather(
            self.get_mvrv(asset),
            self.get_nvt(asset),
            self.get_active_addresses(asset),
            self.get_hash_rate(asset),
            return_exceptions=True,
        )

        result = {
            "mvrv_ratio": mvrv if isinstance(mvrv, (int, float)) else np.nan,
            "nvt_signal": nvt if isinstance(nvt, (int, float)) else np.nan,
            "active_addresses": active_addr if isinstance(active_addr, (int, float)) else np.nan,
            "hash_rate": hash_rate if isinstance(hash_rate, (int, float)) else np.nan,
        }

        fetched = sum(1 for v in result.values() if not (isinstance(v, float) and v != v))
        logger.info(f"On-chain data: {fetched}/4 metrics fetched (Blockchain.com/Mempool)")
        return result
