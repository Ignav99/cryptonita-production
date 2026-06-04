"""
COINGECKO SOCIAL/DEV DATA FETCHER
===================================
Fetches community and developer metrics for all 47 tickers via CoinGecko public API.
No API key required (free tier). Rate limit: 30 req/min → 2.5s between calls.

Features per ticker (6):
  cg_market_cap_rank_norm   — normalized market cap rank (1.0 = rank 1, ~0 = rank 1000+)
  cg_sentiment_votes_up     — % positive sentiment votes (0–1 scale)
  cg_twitter_followers_log  — log10(followers+1) / 8, capped at 1.0
  cg_reddit_subscribers_log — log10(subscribers+1) / 7, capped at 1.0
  cg_dev_commits_4w_log     — log10(commit_count_4w+1) / 3, capped at 1.0
  cg_dev_activity_score     — composite dev activity (commits + code changes), 0–1

Cache TTL: 3600s (1h). Cold start: ~3 min (47 sequential calls at 3.5s each, ~17 rpm).
Subsequent calls within 1h: instant (served from cache). Exponential backoff on 429.
"""

import time
import random
import asyncio
import numpy as np
import httpx
from typing import Dict, Optional
from loguru import logger


# ---------------------------------------------------------------------------
# Ticker → CoinGecko coin ID mapping (all 47 configured tickers)
# ---------------------------------------------------------------------------
TICKER_TO_CG_ID: Dict[str, str] = {
    # Layer 1 / Layer 2
    "SOLUSDT":    "solana",
    "AVAXUSDT":   "avalanche-2",
    "NEARUSDT":   "near",
    "APTUSDT":    "aptos",
    "SUIUSDT":    "sui",
    "SEIUSDT":    "sei-network",
    "ARBUSDT":    "arbitrum",
    "OPUSDT":     "optimism",
    "INJUSDT":    "injective-protocol",
    # DeFi
    "UNIUSDT":    "uniswap",
    "AAVEUSDT":   "aave",
    "LDOUSDT":    "lido-dao",
    "RUNEUSDT":   "thorchain",
    "CRVUSDT":    "curve-dao-token",
    "GMXUSDT":    "gmx",
    "DYDXUSDT":   "dydx-chain",
    # Gaming / Metaverse
    "SANDUSDT":   "the-sandbox",
    "MANAUSDT":   "decentraland",
    "AXSUSDT":    "axie-infinity",
    "IMXUSDT":    "immutable-x",
    "GALAUSDT":   "gala",
    # AI / Compute
    "FETUSDT":    "fetch-ai",
    "WLDUSDT":    "worldcoin-wld",
    "RENDERUSDT": "render-token",
    # Memecoins
    "DOGEUSDT":   "dogecoin",
    "SHIBUSDT":   "shiba-inu",
    "PEPEUSDT":   "pepe",
    "FLOKIUSDT":  "floki",
    "BONKUSDT":   "bonk",
    # Solid altcoins
    "DOTUSDT":    "polkadot",
    "ATOMUSDT":   "cosmos",
    "ADAUSDT":    "cardano",
    "POLUSDT":    "matic-network",
    "LINKUSDT":   "chainlink",
    "ICPUSDT":    "internet-computer",
    "FILUSDT":    "filecoin",
    "HBARUSDT":   "hedera-hashgraph",
    "VETUSDT":    "vechain",
    "ALGOUSDT":   "algorand",
    # Phase 5 expansion
    "TAOUSDT":    "bittensor",
    "ARKMUSDT":   "arkham",
    "ONDOUSDT":   "ondo-finance",
    "ARUSDT":     "arweave",
    "IOTAUSDT":   "iota",
    "STXUSDT":    "blockstack",
    "TIAUSDT":    "celestia",
    "MANTAUSDT":  "manta-network",
}

_BASE_URL = "https://api.coingecko.com/api/v3"
_HEADERS = {"Accept": "application/json", "User-Agent": "CryptonitaBot/1.0"}


def _normalize_features(coin_data: Dict) -> Dict[str, float]:
    """Extract and normalize 6 features from a CoinGecko /coins/{id} response."""
    community = coin_data.get("community_data") or {}
    developer = coin_data.get("developer_data") or {}

    # Community
    rank = coin_data.get("market_cap_rank") or 0
    sentiment_up = coin_data.get("sentiment_votes_up_percentage") or 50.0
    twitter = community.get("twitter_followers") or 0
    reddit = community.get("reddit_subscribers") or 0

    # Developer
    commits_4w = developer.get("commit_count_4_weeks") or 0
    code_changes = developer.get("code_additions_deletions_4_weeks") or {}
    additions = abs(code_changes.get("additions") or 0)
    deletions = abs(code_changes.get("deletions") or 0)
    code_activity = additions + deletions

    # --- Normalizations ---
    # rank 1 → 0.999, rank 1000 → 0.0, rank 0 (unknown) → 0.0
    rank_norm = max(0.0, 1.0 - rank / 1000.0) if rank > 0 else 0.0

    # Sentiment: 0–100 → 0–1
    sentiment_norm = float(sentiment_up) / 100.0

    # Log-normalized community (log10 scale, capped at 1.0)
    tw_log = min(1.0, np.log10(twitter + 1) / 8.0)    # log10(100M) ≈ 8
    rd_log = min(1.0, np.log10(reddit + 1) / 7.0)     # log10(10M) ≈ 7

    # Dev: commit count log-normalized
    commits_log = min(1.0, np.log10(commits_4w + 1) / 3.0)  # log10(1000) = 3

    # Dev activity composite: mix of commit count + code churn
    code_log = min(1.0, np.log10(code_activity + 1) / 5.0)  # log10(100K) = 5
    dev_activity = (commits_log + code_log) / 2.0

    return {
        "cg_market_cap_rank_norm":   round(rank_norm, 4),
        "cg_sentiment_votes_up":     round(sentiment_norm, 4),
        "cg_twitter_followers_log":  round(tw_log, 4),
        "cg_reddit_subscribers_log": round(rd_log, 4),
        "cg_dev_commits_4w_log":     round(commits_log, 4),
        "cg_dev_activity_score":     round(dev_activity, 4),
    }


class CoinGeckoFetcher:
    """
    Fetches social + developer metrics for all configured tickers from CoinGecko.

    Uses the public free API (no key required). Fetches one coin at a time with
    a small delay between calls. CoinGecko data is ENRICHMENT only — missing
    features fall back to NaN and the model handles them gracefully.

    Circuit breaker: after 3 consecutive 429s, skips all remaining tickers
    immediately so the main scan cycle is never blocked.

    The 1h TTL cache means a 6h scan cycle only hits the API ~6 times per day.
    """

    RATE_LIMIT_DELAY = 2.0   # seconds between calls
    CACHE_TTL = 3600.0        # 1 hour
    MAX_RETRIES = 1           # try once + one retry max; CG data is optional
    CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive 429s before bailing out
    GLOBAL_TIMEOUT = 60.0     # seconds — hard cap for the full fetch

    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._cache: Optional[Dict[str, Dict]] = None
        self._cache_time: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_one(
        self, coin_id: str, client: httpx.AsyncClient, deadline: float
    ) -> Optional[Dict]:
        """
        Fetch community + dev data for one coin ID.
        Returns None on 429 or error (caller handles circuit breaker).
        Deadline is enforced before any sleep to prevent blocking.
        """
        url = (
            f"{_BASE_URL}/coins/{coin_id}"
            "?localization=false&tickers=false&market_data=false"
            "&community_data=true&developer_data=true&sparkline=false"
        )
        for attempt in range(self.MAX_RETRIES + 1):
            if time.time() >= deadline:
                return None
            try:
                resp = await client.get(url, headers=_HEADERS, timeout=self.timeout)
                if resp.status_code == 429:
                    if attempt < self.MAX_RETRIES:
                        wait = 5.0 + random.uniform(0, 3)
                        # Only sleep if deadline allows it
                        if time.time() + wait < deadline:
                            logger.warning(
                                f"CoinGecko 429 for {coin_id} — backoff {wait:.0f}s"
                            )
                            await asyncio.sleep(wait)
                            continue
                    logger.debug(f"CoinGecko 429 for {coin_id} — skipping")
                    return None
                if resp.status_code != 200:
                    logger.debug(f"CoinGecko {coin_id}: HTTP {resp.status_code}")
                    return None
                return resp.json()
            except Exception as exc:
                logger.debug(f"CoinGecko fetch error ({coin_id}): {exc}")
                return None
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_all_coingecko_data(self) -> Dict[str, Dict]:
        """
        Fetch CoinGecko features for all configured tickers.

        Returns {ticker: {cg_feature: value}} for each ticker with data.
        Missing tickers return an empty dict (features will be NaN in model).
        Never blocks the scan cycle for more than GLOBAL_TIMEOUT seconds.
        """
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        tickers = list(TICKER_TO_CG_ID.items())
        logger.info(f"CoinGecko: fetching {len(tickers)} tickers (budget: {self.GLOBAL_TIMEOUT:.0f}s)")

        result: Dict[str, Dict] = {}
        deadline = time.time() + self.GLOBAL_TIMEOUT
        consecutive_429s = 0

        async with httpx.AsyncClient() as client:
            for i, (ticker, coin_id) in enumerate(tickers):
                if time.time() >= deadline:
                    logger.warning(
                        f"CoinGecko: {self.GLOBAL_TIMEOUT:.0f}s budget exhausted — "
                        f"skipping remaining {len(tickers) - i} tickers"
                    )
                    break

                if consecutive_429s >= self.CIRCUIT_BREAKER_THRESHOLD:
                    logger.warning(
                        f"CoinGecko: circuit breaker triggered ({consecutive_429s} consecutive 429s) — "
                        f"skipping remaining {len(tickers) - i} tickers"
                    )
                    break

                if i > 0:
                    await asyncio.sleep(self.RATE_LIMIT_DELAY)

                data = await self._fetch_one(coin_id, client, deadline)
                if data:
                    result[ticker] = _normalize_features(data)
                    consecutive_429s = 0
                    logger.debug(f"CoinGecko [{ticker}] OK")
                else:
                    result[ticker] = {}
                    consecutive_429s += 1

        self._cache = result
        self._cache_time = time.time()
        fetched = sum(1 for v in result.values() if v)
        logger.info(f"CoinGecko: cached {fetched}/{len(tickers)} tickers successfully")
        return result

    def get_ticker_features(self, ticker: str, cg_data: Dict[str, Dict]) -> Dict[str, float]:
        """
        Extract CoinGecko features for a specific ticker from pre-fetched data.

        Args:
            ticker:  e.g. "SOLUSDT"
            cg_data: result of get_all_coingecko_data()

        Returns:
            Dict with 6 cg_* float features, or empty dict if unavailable.
        """
        return cg_data.get(ticker, {})
