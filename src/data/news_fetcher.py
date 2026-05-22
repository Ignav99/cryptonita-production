"""
NEWS RSS FETCHER
=================
Scrapes crypto news from free RSS feeds and calculates sentiment per ticker.

Sources:
- CoinDesk RSS
- CoinTelegraph RSS
- The Block RSS

Sentiment: keyword-based scoring from article titles.
"""

import time
import httpx
import feedparser
import numpy as np
from typing import Dict, List, Optional
from loguru import logger

from config import settings
from src.data.llm_sentiment import LLMSentimentAnalyzer

# Sentiment keywords
POSITIVE_KEYWORDS = {
    "bullish", "surge", "rally", "partnership", "launch", "upgrade",
    "adoption", "breakout", "soars", "gains", "all-time high", "ath",
    "milestone", "growth", "approval", "integration", "listing",
}
NEGATIVE_KEYWORDS = {
    "hack", "crash", "bearish", "exploit", "lawsuit", "ban", "dump",
    "sec", "fraud", "vulnerability", "rug", "scam", "bankrupt",
    "liquidation", "delisting", "investigation", "decline",
}

RSS_FEEDS = [
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
    "https://www.theblock.co/rss.xml",
]


class NewsFetcher:
    """Fetches crypto news from RSS feeds and calculates sentiment"""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout
        self._cache: Optional[Dict] = None
        self._cache_time: float = 0
        self._cache_ttl: float = 900  # 15 min cache

        # LLM sentiment analyzer (Claude Haiku) — uses ANTHROPIC_API_KEY from settings
        _api_key = getattr(settings, "ANTHROPIC_API_KEY", None) or None
        self._llm = LLMSentimentAnalyzer(api_key=_api_key)

    async def _fetch_feed(self, url: str) -> List[Dict]:
        """Fetch and parse a single RSS feed"""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, headers={"User-Agent": "CryptonitaBot/1.0"})
                if resp.status_code != 200:
                    logger.debug(f"RSS feed {url} returned {resp.status_code}")
                    return []

                feed = feedparser.parse(resp.text)
                articles = []
                now = time.time()
                for entry in feed.entries[:50]:  # Last 50 entries
                    # Check if within 24h
                    published = entry.get("published_parsed") or entry.get("updated_parsed")
                    if published:
                        entry_time = time.mktime(published)
                        if now - entry_time > 86400:  # >24h old
                            continue

                    articles.append({
                        "title": entry.get("title", "").lower(),
                        "summary": entry.get("summary", "").lower()[:200],
                    })

                return articles
        except Exception as e:
            logger.debug(f"RSS fetch failed ({url}): {e}")
            return []

    def _score_text(self, text: str) -> float:
        """Score text sentiment: -1 (bearish) to +1 (bullish)"""
        text_lower = text.lower()
        pos = sum(1 for kw in POSITIVE_KEYWORDS if kw in text_lower)
        neg = sum(1 for kw in NEGATIVE_KEYWORDS if kw in text_lower)
        total = pos + neg
        if total == 0:
            return 0.0
        return (pos - neg) / total

    def _match_ticker(self, text: str, ticker: str) -> bool:
        """Check if text mentions a ticker"""
        text_lower = text.lower()

        # Match by display name
        display_name = settings.TICKER_DISPLAY_NAMES.get(ticker, "")
        if display_name and display_name.lower() in text_lower:
            return True

        # Match by symbol (e.g., "SOL", "AVAX")
        symbol = ticker.replace("USDT", "").lower()
        if len(symbol) >= 3 and f" {symbol} " in f" {text_lower} ":
            return True

        return False

    async def get_all_news_data(self) -> Dict:
        """Fetch all RSS feeds and return raw articles"""
        now = time.time()
        if self._cache and (now - self._cache_time) < self._cache_ttl:
            return self._cache

        import asyncio
        feeds = await asyncio.gather(
            *[self._fetch_feed(url) for url in RSS_FEEDS],
            return_exceptions=True,
        )

        all_articles = []
        for feed_result in feeds:
            if isinstance(feed_result, list):
                all_articles.extend(feed_result)

        self._cache = {"articles": all_articles, "count": len(all_articles)}
        self._cache_time = now
        logger.info(f"News: fetched {len(all_articles)} articles from {len(RSS_FEEDS)} RSS feeds")
        return self._cache

    def get_ticker_features(self, ticker: str, news_data: Dict) -> Dict[str, float]:
        """Calculate news features for a specific ticker"""
        articles = news_data.get("articles", [])
        if not articles:
            return {
                "news_sentiment_24h": np.nan,
                "news_count_24h": 0.0,
                "news_impact_score": np.nan,
            }

        matching = []
        for article in articles:
            text = article.get("title", "") + " " + article.get("summary", "")
            if self._match_ticker(text, ticker):
                matching.append(article)

        count = len(matching)
        if count == 0:
            return {
                "news_sentiment_24h": 0.0,
                "news_count_24h": 0.0,
                "news_impact_score": 0.0,
            }

        sentiments = [self._score_text(a["title"]) for a in matching]
        avg_sentiment = sum(sentiments) / len(sentiments) if sentiments else 0.0

        return {
            "news_sentiment_24h": avg_sentiment,
            "news_count_24h": float(count),
            "news_impact_score": avg_sentiment * count,
        }

    def get_ticker_features_llm(self, ticker: str, news_data: Dict) -> Dict[str, float]:
        """
        Calculate news features using Claude Haiku LLM analysis.
        Includes legacy keyword features (always computed) plus LLM features.
        Falls back gracefully if ANTHROPIC_API_KEY is not configured.

        Returns merged dict with:
          Legacy: news_sentiment_24h, news_count_24h, news_impact_score
          LLM:    llm_sentiment_score, llm_sentiment_confidence,
                  llm_news_count, llm_regulatory_signal, llm_hack_signal
        """
        # Get legacy keyword features (always computed, fast)
        legacy = self.get_ticker_features(ticker, news_data)

        # Filter matching articles for LLM analysis
        articles = news_data.get("articles", [])
        matching = [
            a for a in articles
            if self._match_ticker(a.get("title", "") + " " + a.get("summary", ""), ticker)
        ]

        if not matching:
            llm_features = self._llm._empty_result()
        else:
            ticker_name = settings.TICKER_DISPLAY_NAMES.get(ticker, ticker.replace("USDT", ""))
            llm_features = self._llm.analyze_ticker(ticker, ticker_name, matching)

        return {**legacy, **llm_features}
