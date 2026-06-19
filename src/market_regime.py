"""
Market Regime Filter: BTC 4h EMA slope detector.
Prevents counter-trend SHORT trades when market is bullish.
Prevents counter-trend LONG trades when market is bearish.
"""

import pandas as pd
import numpy as np
from typing import Literal


class MarketRegimeDetector:
    """
    Detects market regime based on BTC 4h EMA slope.

    Attributes:
        ema_period (int): Period for EMA calculation (default 20).
        slope_threshold (float): Threshold for slope classification (default 0.002 = ±0.2%).
    """

    def __init__(self, ema_period: int = 20, slope_threshold: float = 0.002):
        """
        Initialize the market regime detector.

        Args:
            ema_period (int): Period for exponential moving average.
            slope_threshold (float): Threshold for regime classification.
                If |slope| < threshold, regime is NEUTRAL.
        """
        self.ema_period = ema_period
        self.slope_threshold = slope_threshold

    def detect(self, klines_df: pd.DataFrame) -> Literal['BULLISH', 'BEARISH', 'NEUTRAL']:
        """
        Detect market regime based on EMA slope.

        Args:
            klines_df (pd.DataFrame): DataFrame with OHLCV data. Must have a 'close' column.

        Returns:
            str: One of 'BULLISH', 'BEARISH', or 'NEUTRAL'.

        Regime logic:
            - BULLISH: EMA slope > +threshold (uptrend)
            - BEARISH: EMA slope < -threshold (downtrend)
            - NEUTRAL: |EMA slope| <= threshold (no clear trend)
        """
        if len(klines_df) < self.ema_period:
            # Not enough data, default to NEUTRAL
            return 'NEUTRAL'

        # Calculate EMA
        ema = klines_df['close'].ewm(span=self.ema_period, adjust=False).mean()

        # Get current and previous EMA
        ema_current = ema.iloc[-1]
        ema_previous = ema.iloc[-2]

        # Calculate slope as percentage change
        if ema_previous == 0:
            slope = 0
        else:
            slope = (ema_current - ema_previous) / ema_previous

        # Classify regime
        if slope > self.slope_threshold:
            return 'BULLISH'
        elif slope < -self.slope_threshold:
            return 'BEARISH'
        else:
            return 'NEUTRAL'

    def allow_short(self, regime: str) -> bool:
        """
        Determine if SHORT trading is allowed in this regime.

        Args:
            regime (str): Market regime ('BULLISH', 'BEARISH', or 'NEUTRAL').

        Returns:
            bool: False if regime is BULLISH (block SHORTs). True otherwise.
        """
        return regime != 'BULLISH'

    def allow_long(self, regime: str) -> bool:
        """
        Determine if LONG trading is allowed in this regime.

        Args:
            regime (str): Market regime ('BULLISH', 'BEARISH', or 'NEUTRAL').

        Returns:
            bool: False if regime is BEARISH (block LONGs). True otherwise.
        """
        return regime != 'BEARISH'
