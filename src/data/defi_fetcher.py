"""
DEFI DATA FETCHER
==================
DeFiLlama public API (api.llama.fi) - Free, no key needed.
- Protocol TVL
- Chain TVL
- TVL changes
"""

import httpx
from typing import Dict, Optional
from loguru import logger


class DeFiFetcher:
    """Fetches DeFi data from DeFiLlama public API"""

    BASE_URL = "https://api.llama.fi"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    async def get_protocol_tvl(self, protocol: str = "aave") -> Optional[float]:
        """Get current TVL for a protocol"""
        try:
            url = f"{self.BASE_URL}/tvl/{protocol}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                return float(resp.text)
        except Exception as e:
            logger.warning(f"Failed to fetch TVL for {protocol}: {e}")
        return None

    async def get_protocol_tvl_history(self, protocol: str = "aave") -> list:
        """Get TVL history for a protocol"""
        try:
            url = f"{self.BASE_URL}/protocol/{protocol}"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                return data.get("tvl", [])
        except Exception as e:
            logger.warning(f"Failed to fetch TVL history for {protocol}: {e}")
        return []

    async def get_chain_tvl(self, chain: str = "Ethereum") -> Optional[float]:
        """Get total TVL for a chain"""
        try:
            url = f"{self.BASE_URL}/v2/chains"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                chains = resp.json()
                for c in chains:
                    if c.get("name", "").lower() == chain.lower():
                        return float(c.get("tvl", 0))
        except Exception as e:
            logger.warning(f"Failed to fetch chain TVL for {chain}: {e}")
        return None

    async def get_tvl_change(self, protocol: str = "aave", days: int = 7) -> Optional[float]:
        """Get TVL % change over N days for a protocol"""
        try:
            history = await self.get_protocol_tvl_history(protocol)
            if len(history) > days:
                current = float(history[-1].get("totalLiquidityUSD", 0))
                past = float(history[-(days + 1)].get("totalLiquidityUSD", 0))
                if past > 0:
                    return (current - past) / past
        except Exception as e:
            logger.warning(f"Failed to calculate TVL change for {protocol}: {e}")
        return None

    async def get_total_tvl(self) -> Optional[float]:
        """Get total DeFi TVL across all chains"""
        try:
            url = f"{self.BASE_URL}/v2/chains"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                chains = resp.json()
                return sum(float(c.get("tvl", 0)) for c in chains)
        except Exception as e:
            logger.warning(f"Failed to fetch total TVL: {e}")
        return None

    async def get_all_defi_data(self) -> Dict[str, float]:
        """Get all DeFi indicators"""
        import asyncio

        eth_tvl, total_tvl, aave_change_7d, aave_change_30d = await asyncio.gather(
            self.get_chain_tvl("Ethereum"),
            self.get_total_tvl(),
            self.get_tvl_change("aave", days=7),
            self.get_tvl_change("aave", days=30),
            return_exceptions=True
        )

        eth_tvl_val = eth_tvl if isinstance(eth_tvl, (int, float)) else 0.0
        total_tvl_val = total_tvl if isinstance(total_tvl, (int, float)) else 1.0

        return {
            "tvl_change_7d": aave_change_7d if isinstance(aave_change_7d, (int, float)) else 0.0,
            "tvl_change_30d": aave_change_30d if isinstance(aave_change_30d, (int, float)) else 0.0,
            "tvl_dominance_change": eth_tvl_val / total_tvl_val if total_tvl_val > 0 else 0.0,
        }
