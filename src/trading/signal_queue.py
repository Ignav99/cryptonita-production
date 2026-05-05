"""
SIGNAL QUEUE
============
Queue for deferred trading signals when portfolio is full.
Signals expire after a configurable TTL and are prioritized by probability.
"""

from datetime import datetime, timedelta
from typing import Dict, Optional, List
from loguru import logger

from config import settings


class SignalQueue:
    """In-memory queue for deferred buy signals."""

    def __init__(
        self,
        max_age_hours: float = None,
        max_size: int = None,
    ):
        self.max_age_hours = max_age_hours or settings.SIGNAL_QUEUE_MAX_AGE_HOURS
        self.max_size = max_size or settings.SIGNAL_QUEUE_MAX_SIZE
        self._queue: List[Dict] = []

    def enqueue(self, ticker: str, probability: float, features: dict = None) -> bool:
        """
        Add a signal to the queue. Rejects duplicates and respects max size.
        Returns True if successfully queued.
        """
        # Remove expired signals first
        self._purge_expired()

        # Don't queue duplicate tickers
        if any(s['ticker'] == ticker for s in self._queue):
            logger.debug(f"Signal queue: {ticker} already queued, updating probability")
            for s in self._queue:
                if s['ticker'] == ticker:
                    s['probability'] = max(s['probability'], probability)
                    s['queued_at'] = datetime.utcnow()
                    s['features'] = features or s.get('features', {})
            return True

        # If at capacity, only add if better than worst queued signal
        if len(self._queue) >= self.max_size:
            worst = min(self._queue, key=lambda s: s['probability'])
            if probability <= worst['probability']:
                logger.debug(f"Signal queue full, {ticker} (p={probability:.3f}) not better than worst")
                return False
            # Remove worst to make room
            self._queue.remove(worst)
            logger.info(f"Signal queue: evicted {worst['ticker']} (p={worst['probability']:.3f}) for {ticker}")

        signal = {
            'ticker': ticker,
            'probability': probability,
            'features': features or {},
            'queued_at': datetime.utcnow(),
        }
        self._queue.append(signal)
        logger.info(f"Signal queued: {ticker} (p={probability:.3f}), queue size={len(self._queue)}")
        return True

    def dequeue_best(self) -> Optional[Dict]:
        """Remove and return the highest-probability signal, or None if empty."""
        self._purge_expired()

        if not self._queue:
            return None

        # Sort by probability descending
        self._queue.sort(key=lambda s: s['probability'], reverse=True)
        best = self._queue.pop(0)
        logger.info(f"Queued signal executed: {best['ticker']} (p={best['probability']:.3f})")
        return best

    def peek_best(self) -> Optional[Dict]:
        """Return the best signal without removing it."""
        self._purge_expired()
        if not self._queue:
            return None
        return max(self._queue, key=lambda s: s['probability'])

    def has_signals(self) -> bool:
        """Check if there are any valid (non-expired) signals."""
        self._purge_expired()
        return len(self._queue) > 0

    def size(self) -> int:
        """Return current queue size."""
        self._purge_expired()
        return len(self._queue)

    def get_all(self) -> List[Dict]:
        """Return all queued signals (for logging/dashboard)."""
        self._purge_expired()
        return sorted(self._queue, key=lambda s: s['probability'], reverse=True)

    def remove_ticker(self, ticker: str) -> bool:
        """Remove a specific ticker from the queue."""
        before = len(self._queue)
        self._queue = [s for s in self._queue if s['ticker'] != ticker]
        removed = len(self._queue) < before
        if removed:
            logger.debug(f"Signal queue: removed {ticker}")
        return removed

    def _purge_expired(self) -> int:
        """Remove expired signals. Returns count removed."""
        cutoff = datetime.utcnow() - timedelta(hours=self.max_age_hours)
        before = len(self._queue)
        self._queue = [s for s in self._queue if s['queued_at'] > cutoff]
        removed = before - len(self._queue)
        if removed > 0:
            logger.debug(f"Signal queue: purged {removed} expired signals")
        return removed
