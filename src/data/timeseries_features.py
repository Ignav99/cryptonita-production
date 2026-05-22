"""
TIME SERIES FEATURE ENGINEER
==============================
Forward-looking features using ETS (Exponential Smoothing) and linear trend analysis.
Adds a temporal projection dimension to the static table of XGBoost/LightGBM/CatBoost.

Why this matters:
  - Base models see a "photo" of current state. They don't know if price is
    accelerating toward a target or decelerating after a peak.
  - ETS forecasts the expected price trajectory for the next 15 days.
  - Trend slope tells whether the underlying momentum is building or fading.

Features produced (4):
  ets_expected_return_15d  — ETS forecast: expected % return over next 15 days
  ets_uncertainty_15d      — Forecast uncertainty (std of prediction interval), normalized
  trend_slope_14d          — Linear regression slope of close prices over 14d, normalized
  momentum_divergence      — Divergence between short (3d) and medium (14d) momentum

Requirements:
  statsmodels>=0.14.0 (added to requirements.txt)

Fallback:
  Returns NaN for all features if statsmodels is unavailable or data is insufficient.
  Tree models handle NaN natively — no crash, just a NaN feature.
"""

import numpy as np
import pandas as pd
from typing import Dict, Optional
from loguru import logger

try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not installed — ETS features disabled. Run: pip install statsmodels")


# Minimum candles required for a reliable ETS fit
_MIN_ROWS = 60


class TimeSeriesFeatureEngineer:
    """
    Calculates forward-looking time series features for a single ticker.

    Features are scalar values (last-row scalars) that get broadcast across
    the full DataFrame in calculate_ts_features(), so they integrate cleanly
    with the existing FeatureEngineerV4 pattern.
    """

    def calculate_ts_features(
        self,
        df: pd.DataFrame,
        horizon: int = 15,
    ) -> Dict[str, float]:
        """
        Calculate 4 time series features from OHLCV DataFrame.

        Args:
            df:       DataFrame with at least a 'close' column, sorted ascending by time.
            horizon:  Forecast horizon in candles (default: 15 = ~15 days on daily data).

        Returns:
            Dict with 4 float features. NaN if unavailable.
        """
        empty = {
            "ets_expected_return_15d": np.nan,
            "ets_uncertainty_15d":     np.nan,
            "trend_slope_14d":         np.nan,
            "momentum_divergence":     np.nan,
        }

        if not STATSMODELS_AVAILABLE:
            return empty

        if df is None or len(df) < _MIN_ROWS or "close" not in df.columns:
            return empty

        close = df["close"].dropna()
        if len(close) < _MIN_ROWS:
            return empty

        # Use last 120 candles for ETS fit (enough signal, not too slow)
        series = close.tail(120).values.astype(float)
        current_price = float(series[-1])

        if current_price <= 0:
            return empty

        # --- 1 & 2: ETS forecast (expected return + uncertainty) ---
        ets_return, ets_uncertainty = self._ets_forecast(series, horizon)

        # --- 3: Linear trend slope over last 14 candles ---
        trend_slope = self._linear_trend_slope(series, window=14)

        # --- 4: Momentum divergence (short vs medium) ---
        mom_divergence = self._momentum_divergence(series)

        return {
            "ets_expected_return_15d": round(float(ets_return), 6),
            "ets_uncertainty_15d":     round(float(ets_uncertainty), 6),
            "trend_slope_14d":         round(float(trend_slope), 6),
            "momentum_divergence":     round(float(mom_divergence), 6),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ets_forecast(self, series: np.ndarray, horizon: int) -> tuple:
        """
        Fit simple ETS (Holt's linear trend) and forecast `horizon` steps ahead.

        Returns:
            (expected_return, uncertainty)
            expected_return: forecast % return = (forecast_price / current - 1)
            uncertainty:     std of simulated forecast paths, normalized by current price
        """
        try:
            current = float(series[-1])
            # Holt's model (additive trend, no seasonality — weekly crypto has no seasonality)
            model = ExponentialSmoothing(
                series,
                trend="add",
                seasonal=None,
                initialization_method="estimated",
            ).fit(optimized=True, disp=False)

            forecast = model.forecast(horizon)
            forecast_price = float(forecast[-1])

            # Expected return
            expected_return = (forecast_price / current) - 1.0
            # Clip to reasonable range: -50% to +100%
            expected_return = float(np.clip(expected_return, -0.5, 1.0))

            # Uncertainty: use in-sample residuals as proxy for forecast std
            residuals = model.resid
            residual_std = float(np.std(residuals))
            # Scale by sqrt(horizon) for multi-step uncertainty, normalize by price
            uncertainty = (residual_std * np.sqrt(horizon)) / current
            uncertainty = float(np.clip(uncertainty, 0.0, 1.0))

            return expected_return, uncertainty

        except Exception as exc:
            logger.debug(f"ETS forecast failed: {exc}")
            return np.nan, np.nan

    def _linear_trend_slope(self, series: np.ndarray, window: int = 14) -> float:
        """
        OLS slope of close prices over last `window` candles.
        Normalized by current price so it's scale-independent.

        Returns: slope in units of (price_change_per_candle / current_price)
        Range: typically -0.05 to +0.05 for daily data.
        """
        try:
            segment = series[-window:]
            if len(segment) < 3:
                return np.nan
            x = np.arange(len(segment), dtype=float)
            # Numpy polyfit: degree 1
            slope, _ = np.polyfit(x, segment, 1)
            # Normalize: slope as % of current price per candle
            normalized = slope / float(series[-1])
            return float(np.clip(normalized, -0.2, 0.2))
        except Exception:
            return np.nan

    def _momentum_divergence(self, series: np.ndarray) -> float:
        """
        Divergence between short (3-candle) and medium (14-candle) momentum.

        Positive: short-term momentum > medium-term → acceleration (building)
        Negative: short-term < medium-term → deceleration (fading)

        Returns: float in range ~[-1, +1]
        """
        try:
            current = float(series[-1])
            if current <= 0 or len(series) < 15:
                return np.nan

            mom_3d  = (current - float(series[-4]))  / float(series[-4])
            mom_14d = (current - float(series[-15])) / float(series[-15])

            divergence = mom_3d - mom_14d
            return float(np.clip(divergence, -1.0, 1.0))
        except Exception:
            return np.nan

    def add_ts_features_to_df(self, df: pd.DataFrame, horizon: int = 15) -> pd.DataFrame:
        """
        Convenience method: calculate and broadcast TS features as new columns in df.

        Each feature is a scalar (computed from the full history) broadcast to all rows.
        This mirrors the pattern used by other _calculate_*_features() methods.
        """
        features = self.calculate_ts_features(df, horizon=horizon)
        for name, value in features.items():
            df[name] = value
        return df
