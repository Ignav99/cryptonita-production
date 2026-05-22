"""
LLM SENTIMENT ANALYZER
========================
Replaces keyword matching with Claude Haiku structured analysis.

Why LLM over keywords:
  - "SEC APPROVES Bitcoin ETF" → keywords see "SEC" → bearish. LLM: strongly bullish.
  - "Ethereum exploit causes 10% dump" → keywords might miss this. LLM: bearish, hack category.

Cost: ~$0.03-0.05/day at 47 tickers × 5 articles × 4 scans/day.
  Input: $0.25/1M tokens | Output: $1.25/1M tokens (claude-haiku-4-5)

Fallback: if ANTHROPIC_API_KEY is not set or call fails, returns neutral (0.0).
Cache: 15 minutes per (ticker, articles_hash) pair.
"""

import json
import hashlib
import time
from typing import Dict, List, Optional

from loguru import logger

try:
    import anthropic as _anthropic_module
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed — LLM sentiment disabled. Run: pip install anthropic")


_ANALYSIS_PROMPT = """\
Analyze the following {count} news articles about {ticker_name} ({symbol}).

Articles:
{articles_text}

Return ONLY valid JSON — no prose, no markdown, no explanation:
{{
  "sentiment_score": <float, -1.0 (very bearish) to +1.0 (very bullish)>,
  "article_count": <int, number of articles actually relevant to {symbol}>,
  "categories": [<list from: "regulatory", "technical", "adoption", "macro", "hack_exploit", "partnership", "listing", "market_manipulation", "earnings", "other">],
  "confidence": <float 0.0 to 1.0 — how clear is the signal? 0 if irrelevant/ambiguous>,
  "reasoning": "<one sentence max>"
}}

Rules:
- sentiment_score: -1=very bearish, -0.5=bearish, 0=neutral, +0.5=bullish, +1=very bullish
- confidence: high (>0.7) only if signal is clear and unambiguous
- categories: all that apply to the articles
- If articles don't specifically mention {symbol}, set article_count=0, confidence=0, sentiment_score=0
- Consider CONTEXT: "SEC approves" is bullish; "SEC sues" is bearish
- "hack" or "exploit" is always bearish regardless of other wording
"""


class LLMSentimentAnalyzer:
    """
    Uses Claude Haiku to analyze news sentiment per ticker.
    Thread-safe in-memory cache (15 min TTL).
    Falls back to empty neutral result if API unavailable.
    """

    MODEL = "claude-haiku-4-5-20251001"
    MAX_TOKENS = 300

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self._client = None
        self._cache: Dict[str, Dict] = {}
        self._cache_ttl = 900  # 15 min

        if ANTHROPIC_AVAILABLE and api_key:
            self._client = _anthropic_module.Anthropic(api_key=api_key)
            logger.info("LLMSentimentAnalyzer initialized with Claude Haiku")
        elif not api_key:
            logger.info("LLMSentimentAnalyzer: no API key — falling back to neutral scores")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_ticker(
        self,
        ticker: str,
        ticker_name: str,
        articles: List[Dict],
    ) -> Dict[str, float]:
        """
        Analyze sentiment for a specific ticker given its matching articles.

        Args:
            ticker:       Symbol e.g. "ICPUSDT"
            ticker_name:  Display name e.g. "Internet Computer"
            articles:     List of dicts with 'title' and 'summary' keys

        Returns:
            Dict with float features:
              - llm_sentiment_score:      -1.0 to 1.0
              - llm_sentiment_confidence: 0.0 to 1.0
              - llm_news_count:           number of relevant articles
              - llm_regulatory_signal:    1.0 if regulatory category present
              - llm_hack_signal:          1.0 if hack/exploit category present
        """
        if not articles or not self._client:
            return self._empty_result()

        articles_hash = self._hash_articles(articles)
        cache_key = f"{ticker}:{articles_hash}"
        now = time.time()

        if cache_key in self._cache:
            entry = self._cache[cache_key]
            if now - entry["ts"] < self._cache_ttl:
                return entry["result"]

        result = self._call_llm(ticker, ticker_name, articles)

        # Evict old entries if cache grows large
        if len(self._cache) > 200:
            cutoff = now - self._cache_ttl
            self._cache = {k: v for k, v in self._cache.items() if v["ts"] > cutoff}

        self._cache[cache_key] = {"ts": now, "result": result}
        return result

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call_llm(
        self,
        ticker: str,
        ticker_name: str,
        articles: List[Dict],
    ) -> Dict[str, float]:
        symbol = ticker.replace("USDT", "")
        articles_text = "\n\n".join(
            f"[{i+1}] Title: {a.get('title', '').strip()}\n    Summary: {a.get('summary', '')[:250].strip()}"
            for i, a in enumerate(articles[:15])  # max 15 articles
        )

        prompt = _ANALYSIS_PROMPT.format(
            count=min(len(articles), 15),
            ticker_name=ticker_name,
            symbol=symbol,
            articles_text=articles_text,
        )

        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Extract JSON even if model adds surrounding text
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start < 0 or end <= start:
                raise ValueError(f"No JSON found in response: {raw[:100]}")

            data = json.loads(raw[start:end])
            categories = data.get("categories", [])

            result = {
                "llm_sentiment_score":      float(max(-1.0, min(1.0, data.get("sentiment_score", 0.0)))),
                "llm_sentiment_confidence": float(max(0.0, min(1.0, data.get("confidence", 0.0)))),
                "llm_news_count":           float(max(0, data.get("article_count", len(articles)))),
                "llm_regulatory_signal":    1.0 if "regulatory" in categories else 0.0,
                "llm_hack_signal":          1.0 if "hack_exploit" in categories else 0.0,
            }

            logger.debug(
                f"LLM [{ticker}] score={result['llm_sentiment_score']:+.2f} "
                f"conf={result['llm_sentiment_confidence']:.2f} "
                f"cats={categories}"
            )
            return result

        except Exception as exc:
            logger.warning(f"LLM sentiment failed for {ticker}: {exc}")
            return self._empty_result()

    def _hash_articles(self, articles: List[Dict]) -> str:
        content = "|".join(a.get("title", "")[:80] for a in articles[:15])
        return hashlib.md5(content.encode()).hexdigest()[:10]

    def _empty_result(self) -> Dict[str, float]:
        return {
            "llm_sentiment_score":      0.0,
            "llm_sentiment_confidence": 0.0,
            "llm_news_count":           0.0,
            "llm_regulatory_signal":    0.0,
            "llm_hack_signal":          0.0,
        }
