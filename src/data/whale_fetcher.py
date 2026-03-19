"""
WHALE TRACKING FETCHER
========================
Tracks large BTC transactions using free APIs.

Sources:
- Blockchain.com: recent BTC blocks + large transactions
- Blockchair API (no auth): BTC stats

Features:
- whale_tx_count_24h: large transactions (>100 BTC)
- whale_net_flow: accumulation vs distribution (-1 to +1)
- whale_activity_score: combined metric
"""

import time
import httpx
import numpy as np
from typing import Dict, Optional
from loguru import logger


class WhaleFetcher:
    """Tracks whale activity via free blockchain APIs"""

    BLOCKCHAIN_URL = "https://api.blockchain.info"
    BLOCKCHAIR_URL = "https://api.blockchair.com/bitcoin/stats"

    def __init__(self, timeout: float = 20.0):
        self.timeout = timeout
        self._cache: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 1800  # 30 min cache

    async def _fetch_blockchain_stats(self) -> Dict:
        """Fetch BTC blockchain stats from Blockchain.com"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.BLOCKCHAIN_URL}/stats")
                if resp.status_code == 200:
                    data = resp.json()
                    return {
                        "n_tx_24h": data.get("n_tx", 0),
                        "total_btc_sent_24h": data.get("total_btc_sent", 0) / 1e8,  # satoshi to BTC
                        "market_price_usd": data.get("market_price_usd", 0),
                        "hash_rate": data.get("hash_rate", 0),
                        "estimated_btc_sent_24h": data.get("estimated_btc_sent", 0) / 1e8,
                    }
        except Exception as e:
            logger.debug(f"Blockchain.com stats failed: {e}")
        return {}

    async def _fetch_blockchair_stats(self) -> Dict:
        """Fetch BTC stats from Blockchair (no auth)"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    self.BLOCKCHAIR_URL,
                    headers={"User-Agent": "CryptonitaBot/1.0"},
                )
                if resp.status_code == 200:
                    data = resp.json().get("data", {})
                    return {
                        "avg_transaction_fee_usd": data.get("average_transaction_fee_usd_24h", 0),
                        "median_transaction_value_usd": data.get("median_transaction_fee_usd_24h", 0),
                        "largest_tx_value_usd": data.get("largest_transaction_24h", {}).get("output_total_usd", 0),
                        "mempool_size": data.get("mempool_transactions", 0),
                    }
        except Exception as e:
            logger.debug(f"Blockchair stats failed: {e}")
        return {}

    async def _fetch_recent_blocks(self) -> Dict:
        """Fetch recent blocks and estimate whale transactions"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Get latest block hash
                resp = await client.get(f"{self.BLOCKCHAIN_URL}/latestblock")
                if resp.status_code != 200:
                    return {}

                latest = resp.json()
                block_hash = latest.get("hash", "")
                if not block_hash:
                    return {}

                # Get block details (single block to keep it fast)
                resp = await client.get(
                    f"{self.BLOCKCHAIN_URL}/rawblock/{block_hash}",
                    params={"cors": "true"},
                )
                if resp.status_code != 200:
                    return {}

                block = resp.json()
                txs = block.get("tx", [])

                # Count whale txs (>100 BTC output)
                whale_count = 0
                total_whale_value = 0.0
                for tx in txs:
                    total_output = sum(
                        out.get("value", 0) for out in tx.get("out", [])
                    ) / 1e8  # satoshi to BTC
                    if total_output > 100:
                        whale_count += 1
                        total_whale_value += total_output

                return {
                    "whale_tx_in_block": whale_count,
                    "whale_btc_in_block": total_whale_value,
                    "block_tx_count": len(txs),
                }

        except Exception as e:
            logger.debug(f"Block analysis failed: {e}")
        return {}

    async def get_all_whale_data(self) -> Dict[str, float]:
        """Get all whale metrics"""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        import asyncio
        blockchain_stats, blockchair_stats, block_data = await asyncio.gather(
            self._fetch_blockchain_stats(),
            self._fetch_blockchair_stats(),
            self._fetch_recent_blocks(),
            return_exceptions=True,
        )

        if not isinstance(blockchain_stats, dict):
            blockchain_stats = {}
        if not isinstance(blockchair_stats, dict):
            blockchair_stats = {}
        if not isinstance(block_data, dict):
            block_data = {}

        # Estimate whale tx count from block sample (extrapolate to 24h)
        # ~144 blocks per day, we sampled 1
        whale_per_block = block_data.get("whale_tx_in_block", 0)
        estimated_whale_24h = whale_per_block * 144

        # Total BTC sent — large volume = whale activity
        total_sent = blockchain_stats.get("total_btc_sent_24h", 0)
        estimated_sent = blockchain_stats.get("estimated_btc_sent_24h", 0)

        # Net flow: if estimated < total, more is being accumulated (positive)
        if total_sent > 0 and estimated_sent > 0:
            net_flow = (total_sent - estimated_sent) / total_sent
            net_flow = max(-1.0, min(1.0, net_flow))
        else:
            net_flow = 0.0

        # Activity score: normalized combo
        activity = 0.0
        if estimated_whale_24h > 0:
            # Normalize: 50 whale txs/day = 0.5 score, 100+ = 1.0
            activity = min(1.0, estimated_whale_24h / 100.0)

        result = {
            "whale_tx_count_24h": float(estimated_whale_24h),
            "whale_net_flow": net_flow,
            "whale_activity_score": activity,
        }

        self._cache = result
        self._cache_time = now

        fetched = sum(1 for v in result.values() if v != 0.0)
        logger.info(f"Whale: {fetched}/3 metrics active (est. {estimated_whale_24h} whale txs/24h)")
        return result
