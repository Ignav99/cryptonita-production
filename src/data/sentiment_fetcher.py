"""
SENTIMENT DATA FETCHER
=======================
Free sentiment sources:
- Fear & Greed Index (alternative.me) — historical + SMA
- CryptoPanic free API — news count + sentiment
"""

import httpx
from typing import Dict, List, Optional
from loguru import logger


class SentimentFetcher:
    """Fetches sentiment data from free public APIs"""

    FEAR_GREED_URL = "https://api.alternative.me/fng/"
    CRYPTOPANIC_URL = "https://cryptopanic.com/api/free/v1/posts/"

    def __init__(self, timeout: float = 15.0, cryptopanic_token: Optional[str] = None):
        self.timeout = timeout
        self.cryptopanic_token = cryptopanic_token

    async def get_fear_greed_history(self, days: int = 30) -> List[Dict]:
        """Get Fear & Greed historical data"""
        try:
            params = {"limit": days, "format": "json"}
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.FEAR_GREED_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                entries = data.get("data", [])
                return [
                    {"value": float(e["value"]), "timestamp": e["timestamp"]}
                    for e in entries
                ]
        except Exception as e:
            logger.warning(f"Failed to fetch Fear & Greed history: {e}")
        return []

    async def get_fear_greed_sma(self, window: int = 7) -> Optional[float]:
        """Get smoothed Fear & Greed Index (SMA)"""
        history = await self.get_fear_greed_history(days=window + 5)
        if len(history) >= window:
            values = [h["value"] for h in history[:window]]
            return sum(values) / len(values)
        return None

    async def get_fear_greed_current(self) -> Optional[float]:
        """Get current Fear & Greed value"""
        history = await self.get_fear_greed_history(days=1)
        if history:
            return history[0]["value"]
        return None

    async def get_crypto_news_sentiment(self, ticker: str = "BTC") -> Dict[str, float]:
        """
        Get news sentiment from CryptoPanic free API.
        Returns news count and basic sentiment score.
        Without auth token, returns limited data (count only).
        """
        result = {"news_count": 0.0, "sentiment_score": 0.0}

        if not self.cryptopanic_token:
            # Without token, we still estimate sentiment from F&G
            fg = await self.get_fear_greed_current()
            if fg is not None:
                # Normalize F&G to [-1, 1] sentiment scale
                result["sentiment_score"] = (fg - 50) / 50
            return result

        try:
            currency = ticker.replace("USDT", "").upper()
            params = {
                "auth_token": self.cryptopanic_token,
                "currencies": currency,
                "kind": "news",
                "filter": "important",
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(self.CRYPTOPANIC_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
                results = data.get("results", [])
                result["news_count"] = float(len(results))

                # Count positive vs negative votes
                positive = sum(1 for r in results if r.get("votes", {}).get("positive", 0) > 0)
                negative = sum(1 for r in results if r.get("votes", {}).get("negative", 0) > 0)
                total = positive + negative
                if total > 0:
                    result["sentiment_score"] = (positive - negative) / total

        except Exception as e:
            logger.warning(f"Failed to fetch CryptoPanic news for {ticker}: {e}")

        return result

    async def get_all_sentiment_data(self, ticker: str = "BTC") -> Dict[str, float]:
        """Get all sentiment indicators"""
        import asyncio

        fg_current, fg_sma_7, fg_sma_14, news = await asyncio.gather(
            self.get_fear_greed_current(),
            self.get_fear_greed_sma(window=7),
            self.get_fear_greed_sma(window=14),
            self.get_crypto_news_sentiment(ticker),
            return_exceptions=True
        )

        fg_val = fg_current if isinstance(fg_current, (int, float)) else 50.0
        sma_7 = fg_sma_7 if isinstance(fg_sma_7, (int, float)) else 50.0
        sma_14 = fg_sma_14 if isinstance(fg_sma_14, (int, float)) else 50.0
        news_data = news if isinstance(news, dict) else {"news_count": 0.0, "sentiment_score": 0.0}

        # Fear & Greed momentum = current - SMA14
        fg_momentum = fg_val - sma_14

        return {
            "fear_greed_value": fg_val,
            "fear_greed_sma_7d": sma_7,
            "fear_greed_momentum": fg_momentum,
            "news_sentiment_score": news_data.get("sentiment_score", 0.0),
            "news_volume_ratio": news_data.get("news_count", 0.0) / 10.0,  # Normalize
        }
