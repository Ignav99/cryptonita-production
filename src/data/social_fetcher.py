"""
SOCIAL SENTIMENT FETCHER
==========================
Reddit r/cryptocurrency sentiment analysis via public JSON API (no auth).

Features per ticker:
- reddit_mentions_24h: mention count
- reddit_sentiment: avg upvote_ratio of mentioning posts
- social_buzz_score: mentions x sentiment (normalized)
"""

import time
import httpx
import numpy as np
from typing import Dict, List, Optional
from loguru import logger

from config import settings


class SocialFetcher:
    """Fetches social sentiment from Reddit r/cryptocurrency"""

    REDDIT_URL = "https://www.reddit.com/r/cryptocurrency/hot.json"

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._cache: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 900  # 15 min cache

    async def _fetch_reddit_posts(self) -> List[Dict]:
        """Fetch top posts from r/cryptocurrency"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    self.REDDIT_URL,
                    params={"limit": 100},
                    headers={"User-Agent": "CryptonitaBot/1.0 (trading research)"},
                )
                if resp.status_code != 200:
                    logger.debug(f"Reddit API returned {resp.status_code}")
                    return []

                data = resp.json()
                posts = []
                for child in data.get("data", {}).get("children", []):
                    post = child.get("data", {})
                    posts.append({
                        "title": post.get("title", "").lower(),
                        "upvote_ratio": post.get("upvote_ratio", 0.5),
                        "score": post.get("score", 0),
                        "created_utc": post.get("created_utc", 0),
                    })

                return posts

        except Exception as e:
            logger.debug(f"Reddit fetch failed: {e}")
            return []

    def _match_ticker(self, text: str, ticker: str) -> bool:
        """Check if text mentions a ticker"""
        text_lower = text.lower()

        # Match by display name
        display_name = settings.TICKER_DISPLAY_NAMES.get(ticker, "")
        if display_name and display_name.lower() in text_lower:
            return True

        # Match by symbol
        symbol = ticker.replace("USDT", "").lower()
        if len(symbol) >= 3 and f" {symbol} " in f" {text_lower} ":
            return True

        # Also match $SYMBOL format
        if f"${symbol}" in text_lower:
            return True

        return False

    async def get_all_social_data(self) -> Dict:
        """Fetch Reddit data and return raw posts"""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        posts = await self._fetch_reddit_posts()

        self._cache = {"posts": posts, "count": len(posts)}
        self._cache_time = now
        logger.info(f"Social: fetched {len(posts)} Reddit posts from r/cryptocurrency")
        return self._cache

    def get_ticker_features(self, ticker: str, social_data: Dict) -> Dict[str, float]:
        """Calculate social features for a specific ticker"""
        posts = social_data.get("posts", [])
        if not posts:
            return {
                "reddit_mentions_24h": 0.0,
                "reddit_sentiment": np.nan,
                "social_buzz_score": np.nan,
            }

        matching = [p for p in posts if self._match_ticker(p["title"], ticker)]
        count = len(matching)

        if count == 0:
            return {
                "reddit_mentions_24h": 0.0,
                "reddit_sentiment": 0.5,
                "social_buzz_score": 0.0,
            }

        avg_upvote = sum(p["upvote_ratio"] for p in matching) / count
        # Normalize sentiment: 0.5 = neutral, >0.8 = positive
        sentiment_normalized = (avg_upvote - 0.5) * 2  # -1 to +1

        return {
            "reddit_mentions_24h": float(count),
            "reddit_sentiment": avg_upvote,
            "social_buzz_score": count * sentiment_normalized,
        }
