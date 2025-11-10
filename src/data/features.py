"""
FEATURE ENGINEERING - MODEL V3
===============================
Calcula las 48 features necesarias para el modelo de predicción V3

Features V3 (48 total):
- 6 OHLCV + EMA (open, high, low, close, volume, ema_200)
- 14 features originales (V1)
- 15 features de tendencia (V2)
- 8 features de momentum avanzado (V3)
- 5 features macro (V2)

IMPORTANT: Model expects features in this exact order!
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
from loguru import logger


class FeatureEngineer:
    """
    Feature engineering para el modelo V3 de trading
    """

    def __init__(self):
        """Initialize feature engineer"""
        self.required_features = self._load_required_features()
        logger.info(f"✅ Feature Engineer initialized - {len(self.required_features)} features")

    def _load_required_features(self) -> List[str]:
        """
        Load required features from V3 config

        IMPORTANT: Model was trained with 48 features in this exact order:
        - First 6: OHLCV + ema_200 (from raw data)
        - Next 42: Calculated features

        DO NOT change the order!
        """
        return [
            # OHLCV + EMA (6 features) - Required by model first
            "open",
            "high",
            "low",
            "close",
            "volume",
            "ema_200",
            # Original V1 (14 features)
            "price_to_ema200",
            "atr_pct",
            "price_change_14d",
            "obv",
            "obv_ratio",
            "hl_ratio",
            "volume_ratio_20",
            "stoch_k",
            "lower_shadow_ratio",
            "upper_shadow_ratio",
            "bullish_candles_3d",
            "body_ratio",
            "close_position",
            "body_trend",
            # Trend V2 (15 features)
            "momentum_3d",
            "momentum_5d",
            "momentum_7d",
            "price_acceleration",
            "volume_trend_ratio",
            "volume_acceleration",
            "atr_compression",
            "hl_compression",
            "green_candles_5d",
            "green_candles_10d",
            "higher_highs_5d",
            "higher_lows_5d",
            "price_position_20d",
            "momentum_strength",
            "body_trend_ratio",
            # Advanced Momentum V3 (8 features)
            "price_jerk_3d",
            "volume_jerk_3d",
            "price_explosion_ratio",
            "volume_explosion_ratio",
            "momentum_vs_btc_3d",
            "beta_acceleration",
            "volatility_spike_ratio",
            "hl_expansion_rate",
            # Macro V2 (5 features) - Added last
            "fear_greed_value",
            "funding_rate",
            "spx",
            "spx_change_7d",
            "vix"
        ]

    def calculate_features(
        self,
        df: pd.DataFrame,
        btc_df: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None
    ) -> pd.DataFrame:
        """
        Calculate all 42 features for model V3

        Args:
            df: OHLCV data for crypto (columns: open, high, low, close, volume)
            btc_df: Optional BTC OHLCV data for correlation features
            macro_data: Optional dict with {fear_greed, funding_rate, spx, vix}

        Returns:
            DataFrame with all calculated features
        """
        if len(df) < 200:
            logger.warning(f"⚠️ Not enough data: {len(df)} rows (need 200+)")
            return pd.DataFrame()

        df = df.copy()

        # Calculate all feature groups
        df = self._calculate_original_features(df)
        df = self._calculate_trend_features(df)
        df = self._calculate_advanced_momentum_features(df)

        # Add macro features if provided
        if macro_data:
            df = self._add_macro_features(df, macro_data)

        # Add BTC correlation features if provided
        if btc_df is not None:
            df = self._calculate_btc_features(df, btc_df)

        # Remove rows with NaN (warm-up period)
        df = df.dropna()

        logger.info(f"✅ Features calculated: {len(df)} rows, {len(self.required_features)} features")
        return df

    # ============================================
    # ORIGINAL V1 FEATURES (14)
    # ============================================

    def _calculate_original_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate original 14 features from V1"""

        # EMAs
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

        # ATR
        df['tr'] = np.maximum(
            df['high'] - df['low'],
            np.maximum(
                abs(df['high'] - df['close'].shift(1)),
                abs(df['low'] - df['close'].shift(1))
            )
        )
        df['atr_14'] = df['tr'].rolling(14).mean()

        # 1. price_to_ema200
        df['price_to_ema200'] = df['close'] / df['ema_200']

        # 2. atr_pct
        df['atr_pct'] = df['atr_14'] / df['close']

        # 3. price_change_14d
        df['price_change_14d'] = (df['close'] - df['close'].shift(14)) / df['close'].shift(14)

        # 4. OBV (On-Balance Volume)
        df['obv'] = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()

        # 5. obv_ratio
        df['obv_ma'] = df['obv'].rolling(20).mean()
        df['obv_ratio'] = df['obv'] / df['obv_ma']

        # 6. hl_ratio
        df['hl_ratio'] = (df['high'] - df['low']) / df['close']

        # 7. volume_ratio_20
        df['volume_ma_20'] = df['volume'].rolling(20).mean()
        df['volume_ratio_20'] = df['volume'] / df['volume_ma_20']

        # 8. stoch_k (Stochastic Oscillator)
        low_14 = df['low'].rolling(14).min()
        high_14 = df['high'].rolling(14).max()
        df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14)

        # 9. lower_shadow_ratio
        df['lower_shadow'] = df[['open', 'close']].min(axis=1) - df['low']
        df['lower_shadow_ratio'] = df['lower_shadow'] / (df['high'] - df['low'])

        # 10. upper_shadow_ratio
        df['upper_shadow'] = df['high'] - df[['open', 'close']].max(axis=1)
        df['upper_shadow_ratio'] = df['upper_shadow'] / (df['high'] - df['low'])

        # 11. bullish_candles_3d
        df['is_bullish'] = (df['close'] > df['open']).astype(int)
        df['bullish_candles_3d'] = df['is_bullish'].rolling(3).sum()

        # 12. body_ratio
        df['body_ratio'] = abs(df['close'] - df['open']) / (df['high'] - df['low'])

        # 13. close_position (where close is in the H-L range)
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'])

        # 14. body_trend (cumulative sum of body direction)
        df['body_direction'] = np.sign(df['close'] - df['open'])
        df['body_trend'] = df['body_direction'].rolling(5).sum()

        return df

    # ============================================
    # TREND V2 FEATURES (15)
    # ============================================

    def _calculate_trend_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate 15 trend features from V2"""

        # 15-17. Momentum (3d, 5d, 7d)
        df['momentum_3d'] = (df['close'] - df['close'].shift(3)) / df['close'].shift(3)
        df['momentum_5d'] = (df['close'] - df['close'].shift(5)) / df['close'].shift(5)
        df['momentum_7d'] = (df['close'] - df['close'].shift(7)) / df['close'].shift(7)

        # 18. price_acceleration (change in momentum)
        df['price_acceleration'] = df['momentum_3d'] - df['momentum_3d'].shift(3)

        # 19. volume_trend_ratio
        df['volume_ma_5'] = df['volume'].rolling(5).mean()
        df['volume_ma_20'] = df['volume'].rolling(20).mean()
        df['volume_trend_ratio'] = df['volume_ma_5'] / df['volume_ma_20']

        # 20. volume_acceleration
        df['volume_change'] = (df['volume'] - df['volume'].shift(3)) / df['volume'].shift(3)
        df['volume_acceleration'] = df['volume_change'] - df['volume_change'].shift(3)

        # 21. atr_compression
        df['atr_20'] = df['tr'].rolling(20).mean()
        df['atr_compression'] = df['atr_14'] / df['atr_20']

        # 22. hl_compression
        df['hl_range_3d'] = (df['high'] - df['low']).rolling(3).mean()
        df['hl_range_20d'] = (df['high'] - df['low']).rolling(20).mean()
        df['hl_compression'] = df['hl_range_3d'] / df['hl_range_20d']

        # 23-24. green_candles (5d, 10d)
        df['green_candles_5d'] = df['is_bullish'].rolling(5).sum()
        df['green_candles_10d'] = df['is_bullish'].rolling(10).sum()

        # 25-26. higher_highs and higher_lows (5d)
        df['higher_highs_5d'] = (df['high'] > df['high'].shift(1)).astype(int).rolling(5).sum()
        df['higher_lows_5d'] = (df['low'] > df['low'].shift(1)).astype(int).rolling(5).sum()

        # 27. price_position_20d (where current price sits in 20d range)
        low_20 = df['low'].rolling(20).min()
        high_20 = df['high'].rolling(20).max()
        df['price_position_20d'] = (df['close'] - low_20) / (high_20 - low_20)

        # 28. momentum_strength (average of momentums)
        df['momentum_strength'] = (df['momentum_3d'] + df['momentum_5d'] + df['momentum_7d']) / 3

        # 29. body_trend_ratio
        df['body_size'] = abs(df['close'] - df['open'])
        df['body_size_ma'] = df['body_size'].rolling(5).mean()
        df['body_trend_ratio'] = df['body_size'] / df['body_size_ma']

        return df

    # ============================================
    # ADVANCED MOMENTUM V3 FEATURES (8)
    # ============================================

    def _calculate_advanced_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate 8 advanced momentum features from V3"""

        # 30. price_jerk_3d (acceleration of acceleration)
        df['price_jerk_3d'] = df['price_acceleration'] - df['price_acceleration'].shift(3)

        # 31. volume_jerk_3d (acceleration of volume acceleration)
        df['volume_jerk_3d'] = df['volume_acceleration'] - df['volume_acceleration'].shift(3)

        # 32. price_explosion_ratio (max_3d / avg_20d)
        df['max_3d'] = df['high'].rolling(3).max()
        df['avg_20d'] = df['close'].rolling(20).mean()
        df['price_explosion_ratio'] = df['max_3d'] / df['avg_20d']

        # 33. volume_explosion_ratio (max_vol_3d / avg_vol_20d)
        df['max_vol_3d'] = df['volume'].rolling(3).max()
        df['avg_vol_20d'] = df['volume'].rolling(20).mean()
        df['volume_explosion_ratio'] = df['max_vol_3d'] / df['avg_vol_20d']

        # 34. momentum_vs_btc_3d (will be calculated in _calculate_btc_features)
        # Placeholder for now
        df['momentum_vs_btc_3d'] = 0.0

        # 35. beta_acceleration (will be calculated in _calculate_btc_features)
        # Placeholder for now
        df['beta_acceleration'] = 0.0

        # 36. volatility_spike_ratio (ATR_3d / ATR_30d)
        df['atr_3'] = df['tr'].rolling(3).mean()
        df['atr_30'] = df['tr'].rolling(30).mean()
        df['volatility_spike_ratio'] = df['atr_3'] / df['atr_30']

        # 37. hl_expansion_rate (rate of change of H-L range)
        df['hl_range'] = df['high'] - df['low']
        df['hl_range_change'] = (df['hl_range'] - df['hl_range'].shift(5)) / df['hl_range'].shift(5)
        df['hl_expansion_rate'] = df['hl_range_change']

        return df

    # ============================================
    # BTC CORRELATION FEATURES
    # ============================================

    def _calculate_btc_features(self, df: pd.DataFrame, btc_df: pd.DataFrame) -> pd.DataFrame:
        """Calculate BTC correlation features"""

        if btc_df is None or len(btc_df) < 30:
            logger.warning("⚠️ No BTC data provided, using defaults for BTC features")
            return df

        # Align BTC data with crypto data by timestamp
        btc_df = btc_df.copy()

        # Calculate BTC momentum
        btc_df['btc_momentum_3d'] = (btc_df['close'] - btc_df['close'].shift(3)) / btc_df['close'].shift(3)

        # Merge on timestamp
        if 'timestamp' in df.columns and 'timestamp' in btc_df.columns:
            df = df.merge(
                btc_df[['timestamp', 'btc_momentum_3d', 'close']].rename(columns={'close': 'btc_close'}),
                on='timestamp',
                how='left'
            )

            # 34. momentum_vs_btc_3d
            df['momentum_vs_btc_3d'] = df['momentum_3d'] - df['btc_momentum_3d'].fillna(0)

            # 35. beta_acceleration (rolling correlation with BTC)
            # Calculate rolling beta (30-day window)
            df['returns'] = df['close'].pct_change()
            df['btc_returns'] = df['btc_close'].pct_change()

            # Rolling correlation as proxy for beta
            df['beta'] = df['returns'].rolling(30).corr(df['btc_returns'])
            df['beta_acceleration'] = df['beta'] - df['beta'].shift(5)

        return df

    # ============================================
    # MACRO FEATURES
    # ============================================

    def _add_macro_features(self, df: pd.DataFrame, macro_data: Dict) -> pd.DataFrame:
        """
        Add macro features (constant for all rows in current batch)

        Args:
            macro_data: Dict with {fear_greed, funding_rate, spx, vix}
        """
        # 38. fear_greed_value
        df['fear_greed_value'] = macro_data.get('fear_greed', 50)  # Default: neutral

        # 39. funding_rate
        df['funding_rate'] = macro_data.get('funding_rate', 0.0)

        # 40. spx (S&P 500 value)
        df['spx'] = macro_data.get('spx', 4500)  # Default value

        # 41. spx_change_7d
        df['spx_change_7d'] = macro_data.get('spx_change_7d', 0.0)

        # 42. vix (Volatility Index)
        df['vix'] = macro_data.get('vix', 20)  # Default value

        return df

    # ============================================
    # FEATURE EXTRACTION
    # ============================================

    def get_feature_vector(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Extract only the required 48 features in correct order

        Args:
            df: DataFrame with all calculated features

        Returns:
            DataFrame with only the 48 required features (OHLCV + ema_200 + 42 calculated)
        """
        # Get the latest row (most recent data)
        if len(df) == 0:
            logger.error("❌ No data to extract features from")
            return pd.DataFrame()

        # Select only required features
        try:
            # Extract ONLY the 48 required features (OHLCV + ema_200 + calculated features)
            # in the exact order the model expects
            feature_df = df[self.required_features].copy()

            # Drop any NaN rows
            feature_df = feature_df.dropna()

            return feature_df
        except KeyError as e:
            logger.error(f"❌ Missing features: {e}")
            # Print which features are available vs required
            available = set(df.columns)
            required = set(self.required_features)
            missing = required - available
            extra = available - required
            if missing:
                logger.error(f"Missing features: {missing}")
            if extra:
                logger.debug(f"Extra columns (will be ignored): {extra}")
            return pd.DataFrame()

    def calculate_single_prediction_features(
        self,
        ticker_data: pd.DataFrame,
        btc_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None
    ) -> Optional[np.ndarray]:
        """
        Calculate features for a single prediction (latest datapoint)

        Args:
            ticker_data: OHLCV data for the ticker
            btc_data: Optional BTC data for correlation
            macro_data: Optional macro indicators

        Returns:
            Feature vector (1D array) ready for prediction, or None if error
        """
        try:
            # Calculate all features
            df_with_features = self.calculate_features(ticker_data, btc_data, macro_data)

            if len(df_with_features) == 0:
                return None

            # Get feature vector (latest row only)
            feature_vector = self.get_feature_vector(df_with_features)

            if len(feature_vector) == 0:
                return None

            # Return as numpy array (last row)
            return feature_vector.iloc[-1].values

        except Exception as e:
            logger.error(f"❌ Failed to calculate features: {e}")
            return None
