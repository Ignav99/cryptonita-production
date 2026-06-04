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
    2.5s delay between calls to stay under the 30 req/min rate limit.

    The 1h TTL cache means a 6h scan cycle only hits the API ~6 times per day.
    Cold start takes ~2 min; all subsequent calls within 1h return instantly.
    """

    RATE_LIMIT_DELAY = 3.5   # seconds between calls — safe for keyless free tier (~17 rpm)
    CACHE_TTL = 3600.0        # 1 hour

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._cache: Optional[Dict[str, Dict]] = None
        self._cache_time: float = 0.0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _fetch_one(self, coin_id: str, client: httpx.AsyncClient) -> Optional[Dict]:
        """Fetch community + dev data for one coin ID with exponential backoff on 429."""
        url = (
            f"{_BASE_URL}/coins/{coin_id}"
            "?localization=false&tickers=false&market_data=false"
            "&community_data=true&developer_data=true&sparkline=false"
        )
        max_retries = 2
        for attempt in range(max_retries):
            try:
                resp = await client.get(url, headers=_HEADERS, timeout=self.timeout)
                if resp.status_code == 429:
                    # Exponential backoff with jitter: 2^attempt * (10 + random 0-5s)
                    wait = (2 ** attempt) * 10 + random.uniform(0, 5)
                    logger.warning(
                        f"CoinGecko 429 for {coin_id} — backoff {wait:.0f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(wait)
                    continue
                if resp.status_code != 200:
                    logger.debug(f"CoinGecko {coin_id}: HTTP {resp.status_code}")
                    return None
                return resp.json()
            except Exception as exc:
                if attempt < max_retries - 1:
                    wait = (2 ** attempt) * 5
                    logger.debug(f"CoinGecko fetch error ({coin_id}), retry in {wait}s: {exc}")
                    await asyncio.sleep(wait)
                else:
                    logger.debug(f"CoinGecko fetch failed ({coin_id}) after {max_retries} attempts: {exc}")
        return None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_all_coingecko_data(self) -> Dict[str, Dict]:
        """
        Fetch CoinGecko features for all configured tickers.

        Returns {ticker: {cg_feature: value}} for each ticker with data.
        Missing tickers return an empty dict (features will be NaN in model).

        Cold start: ~2 min. Subsequent calls within 1h: instant.
        """
        now = time.time()
        if self._cache is not None and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        tickers = list(TICKER_TO_CG_ID.items())
        logger.info(
            f"CoinGecko: fetching {len(tickers)} tickers "
            f"(~{len(tickers) * self.RATE_LIMIT_DELAY:.0f}s at {self.RATE_LIMIT_DELAY}s/call)"
        )

        result: Dict[str, Dict] = {}
        deadline = time.time() + 90  # global 90s cap — never block the scan cycle
        async with httpx.AsyncClient() as client:
            for i, (ticker, coin_id) in enumerate(tickers):
                if time.time() >= deadline:
                    logger.warning(f"CoinGecko: 90s budget exhausted — skipping remaining {len(tickers) - i} tickers")
                    break
                if i > 0:
                    await asyncio.sleep(self.RATE_LIMIT_DELAY)

                data = await self._fetch_one(coin_id, client)
                if data:
                    result[ticker] = _normalize_features(data)
                    logger.debug(f"CoinGecko [{ticker}] ({coin_id}): OK")
                else:
                    result[ticker] = {}

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
