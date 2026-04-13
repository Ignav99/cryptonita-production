"""
CORRELATION ENGINE
===================
Computes rolling correlations between candidate trades and held positions.
Returns a penalty multiplier [0.5, 1.0] to reduce position size for
highly correlated additions.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from loguru import logger


class CorrelationEngine:
    """
    Rolling correlation analysis for portfolio diversification.
    """

    def __init__(self, window: int = 30, penalty_floor: float = 0.50):
        self.window = window
        self.penalty_floor = penalty_floor
        self._returns_cache: Optional[pd.DataFrame] = None

    def update_returns(self, tickers_data: Dict[str, pd.DataFrame]):
        """
        Cache daily returns for all tickers from OHLCV data.
        Call once per scan cycle.
        """
        returns_dict = {}
        for ticker, df in tickers_data.items():
            if df is not None and len(df) >= self.window + 1:
                close = df["close"].astype(float)
                ret = close.pct_change().tail(self.window)
                returns_dict[ticker] = ret.values

        if returns_dict:
            # Align lengths
            min_len = min(len(v) for v in returns_dict.values())
            aligned = {k: v[-min_len:] for k, v in returns_dict.items()}
            self._returns_cache = pd.DataFrame(aligned)
            logger.debug(f"Correlation engine: cached returns for {len(returns_dict)} tickers")

    def get_correlation_penalty(
        self,
        candidate_ticker: str,
        held_tickers: List[str],
    ) -> float:
        """
        Calculate position size penalty based on correlation with held positions.

        Returns:
            Multiplier in [penalty_floor, 1.0]. Lower = more correlated = smaller position.
        """
        if not held_tickers or self._returns_cache is None:
            return 1.0

        if candidate_ticker not in self._returns_cache.columns:
            return 1.0

        candidate_returns = self._returns_cache[candidate_ticker]
        correlations = []

        for held in held_tickers:
            if held in self._returns_cache.columns:
                corr = candidate_returns.corr(self._returns_cache[held])
                if not np.isnan(corr):
                    correlations.append(corr)

        if not correlations:
            return 1.0

        avg_corr = np.mean(correlations)

        # Penalty: linear reduction as average correlation increases
        # avg_corr <= 0.3  -> 1.0 (no penalty)
        # avg_corr = 0.6   -> 0.85
        # avg_corr = 0.8   -> 0.65
        # avg_corr >= 0.95 -> penalty_floor (0.50)
        if avg_corr <= 0.3:
            penalty = 1.0
        else:
            penalty = max(self.penalty_floor, 1.0 - (avg_corr - 0.3) * (1.0 - self.penalty_floor) / 0.65)

        logger.debug(
            f"Correlation {candidate_ticker} vs {held_tickers}: "
            f"avg={avg_corr:.3f}, penalty={penalty:.2f}"
        )
        return penalty

    def get_portfolio_correlation_matrix(self, tickers: List[str]) -> Optional[pd.DataFrame]:
        """Get correlation matrix for a set of tickers."""
        if self._returns_cache is None:
            return None
        available = [t for t in tickers if t in self._returns_cache.columns]
        if len(available) < 2:
            return None
        return self._returns_cache[available].corr()
