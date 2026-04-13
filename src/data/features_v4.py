"""
FEATURE ENGINEERING V4
=======================
Extends V3 FeatureEngineer (48 features) with ~41 new features for a total of ~89.

New feature groups:
- Derivatives (6): funding_rate_zscore, oi_change_24h, long_short_ratio, etc.
- On-Chain (5): mvrv_ratio, nvt_signal, active_addr_change_7d, etc.
- Sentiment (4): fear_greed_sma_7d, fear_greed_momentum, etc.
- DeFi (3): tvl_change_7d, tvl_change_30d, tvl_dominance_change
- Cross-Asset (4): btc_dominance_change, eth_btc_momentum, etc.
- Advanced TA (6): rsi_14, macd_signal, bb_width, bb_position, adx_14, mfi_14
- Regime (4): hmm_state, regime_bull_prob, regime_bear_prob, volatility_regime
- News (3): news_sentiment_24h, news_count_24h, news_impact_score
- Social (3): reddit_mentions_24h, reddit_sentiment, social_buzz_score
- Whale (3): whale_tx_count_24h, whale_net_flow, whale_activity_score
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

from src.data.features import FeatureEngineer

CONFIG_PATH = Path(__file__).parent.parent.parent / "configs" / "feature_config_v4.json"


class FeatureEngineerV4(FeatureEngineer):
    """
    V4 Feature Engineer — inherits V3 and adds new feature groups.
    Missing external data → NaN (handled natively by XGBoost/LightGBM/CatBoost).
    """

    def __init__(self):
        super().__init__()
        self._load_v4_config()
        logger.info(f"FeatureEngineerV4 initialized — {len(self.required_features_v4)} features")

    def _load_v4_config(self):
        """Load V4 feature list from JSON config"""
        try:
            with open(CONFIG_PATH) as f:
                config = json.load(f)
            self.required_features_v4 = config["all_features"]
            self.selected_features = config.get("selected_features")
        except FileNotFoundError:
            logger.warning("V4 feature config not found, using hardcoded list")
            self.required_features_v4 = self.required_features + self._get_new_feature_names()
            self.selected_features = None

    def _get_new_feature_names(self) -> List[str]:
        return [
            # Derivatives
            "funding_rate_zscore", "oi_change_24h", "long_short_ratio",
            "top_trader_ratio", "oi_price_divergence", "funding_oi_signal",
            # On-Chain
            "mvrv_ratio", "nvt_signal", "active_addr_change_7d",
            "hash_rate_change_30d", "mvrv_zscore",
            # Sentiment
            "fear_greed_sma_7d", "fear_greed_momentum",
            "news_sentiment_score", "news_volume_ratio",
            # DeFi
            "tvl_change_7d", "tvl_change_30d", "tvl_dominance_change",
            # Cross-Asset
            "btc_dominance_change", "eth_btc_momentum",
            "alt_season_index", "btc_correlation_30d",
            # Advanced TA
            "rsi_14", "macd_signal", "bb_width", "bb_position", "adx_14", "mfi_14",
            # Regime
            "hmm_state", "regime_bull_prob", "regime_bear_prob", "volatility_regime",
            # News (RSS)
            "news_sentiment_24h", "news_count_24h", "news_impact_score",
            # Social (Reddit)
            "reddit_mentions_24h", "reddit_sentiment", "social_buzz_score",
            # Whale
            "whale_tx_count_24h", "whale_net_flow", "whale_activity_score",
            # Mean-Reversion
            "price_zscore_20", "price_zscore_50", "return_5d_pct",
            "return_10d_pct", "overextension_score",
        ]

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def calculate_features_v4(
        self,
        df: pd.DataFrame,
        btc_df: Optional[pd.DataFrame] = None,
        eth_df: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None,
        derivatives_data: Optional[Dict] = None,
        onchain_data: Optional[Dict] = None,
        sentiment_data: Optional[Dict] = None,
        defi_data: Optional[Dict] = None,
        regime_data: Optional[Dict] = None,
        news_data: Optional[Dict] = None,
        social_data: Optional[Dict] = None,
        whale_data: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """
        Calculate all ~89 features (V3 base + V4 extensions + news/social/whale).

        Returns DataFrame with NaN for unavailable features (tree models handle this).
        """
        if len(df) < 200:
            logger.warning(f"Not enough data: {len(df)} rows (need 200+)")
            return pd.DataFrame()

        required_cols = {"open", "high", "low", "close", "volume"}
        if required_cols - set(df.columns):
            logger.error(f"Missing columns: {required_cols - set(df.columns)}")
            return pd.DataFrame()

        df = df.copy()

        # --- V3 base features (48) ---
        df = self._calculate_original_features(df)
        df = self._calculate_trend_features(df)
        df = self._calculate_advanced_momentum_features(df)
        if macro_data:
            df = self._add_macro_features(df, macro_data)
        if btc_df is not None:
            df = self._calculate_btc_features(df, btc_df)

        # --- V4 new features ---
        df = self._calculate_derivatives_features(df, derivatives_data)
        df = self._calculate_onchain_features(df, onchain_data)
        df = self._calculate_sentiment_features(df, sentiment_data)
        df = self._calculate_defi_features(df, defi_data)
        df = self._calculate_cross_asset_features(df, btc_df, eth_df)
        df = self._calculate_advanced_ta_features(df)
        df = self._calculate_regime_features(df, regime_data)

        # --- V4.2 mean-reversion features ---
        df = self._calculate_mean_reversion_features(df)

        # --- V4.1 new features (news, social, whale) ---
        df = self._calculate_news_features(df, news_data)
        df = self._calculate_social_features(df, social_data)
        df = self._calculate_whale_features(df, whale_data)

        # Replace inf with NaN (tree models handle NaN natively)
        df = df.replace([np.inf, -np.inf], np.nan)

        logger.info(f"V4 features calculated: {len(df)} rows")
        return df

    # ------------------------------------------------------------------
    # V4 Feature Groups
    # ------------------------------------------------------------------

    def _calculate_derivatives_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """Derivatives features (6)"""
        if data is None:
            data = {}

        funding = data.get("funding_rate", 0.0)
        # Z-score of funding rate (assume mean=0.0001, std=0.0005 for crypto)
        df["funding_rate_zscore"] = (funding - 0.0001) / 0.0005 if funding != 0.0 else 0.0

        df["oi_change_24h"] = data.get("oi_change_24h", np.nan)
        df["long_short_ratio"] = data.get("long_short_ratio", np.nan)
        df["top_trader_ratio"] = data.get("top_trader_ratio", np.nan)

        # OI-price divergence: OI up but price down (or vice versa) = divergence signal
        oi_chg = data.get("oi_change_24h", 0.0)
        price_chg = df["close"].pct_change().iloc[-1] if len(df) > 1 else 0.0
        df["oi_price_divergence"] = oi_chg - price_chg

        # Combined funding + OI signal
        df["funding_oi_signal"] = funding * 10000 + oi_chg  # Scale funding to comparable magnitude

        return df

    def _calculate_onchain_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """On-chain features (5)"""
        if data is None:
            data = {}

        df["mvrv_ratio"] = data.get("mvrv_ratio", np.nan)
        df["nvt_signal"] = data.get("nvt_signal", np.nan)
        df["active_addr_change_7d"] = data.get("active_addr_change_7d", np.nan)
        df["hash_rate_change_30d"] = data.get("hash_rate_change_30d", np.nan)

        # MVRV z-score (historical mean ~1.5, std ~1.0)
        mvrv = data.get("mvrv_ratio", np.nan)
        df["mvrv_zscore"] = (mvrv - 1.5) / 1.0 if not np.isnan(mvrv) else np.nan

        return df

    def _calculate_sentiment_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """Sentiment features (4)"""
        if data is None:
            data = {}

        df["fear_greed_sma_7d"] = data.get("fear_greed_sma_7d", np.nan)
        df["fear_greed_momentum"] = data.get("fear_greed_momentum", np.nan)
        df["news_sentiment_score"] = data.get("news_sentiment_score", np.nan)
        df["news_volume_ratio"] = data.get("news_volume_ratio", np.nan)

        return df

    def _calculate_defi_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """DeFi features (3)"""
        if data is None:
            data = {}

        df["tvl_change_7d"] = data.get("tvl_change_7d", np.nan)
        df["tvl_change_30d"] = data.get("tvl_change_30d", np.nan)
        df["tvl_dominance_change"] = data.get("tvl_dominance_change", np.nan)

        return df

    def _calculate_cross_asset_features(
        self,
        df: pd.DataFrame,
        btc_df: Optional[pd.DataFrame],
        eth_df: Optional[pd.DataFrame],
    ) -> pd.DataFrame:
        """Cross-asset features (4)"""

        # BTC dominance change (approximation from price momentum)
        if btc_df is not None and len(btc_df) >= 30:
            btc_close = btc_df["close"].values
            btc_mom_7d = (btc_close[-1] - btc_close[-7]) / btc_close[-7] if len(btc_close) >= 7 else 0.0
            coin_mom_7d = (df["close"].iloc[-1] - df["close"].iloc[-7]) / df["close"].iloc[-7] if len(df) >= 7 else 0.0

            df["btc_dominance_change"] = btc_mom_7d - coin_mom_7d  # BTC outperformance

            # BTC correlation (30d rolling)
            if len(df) >= 30 and len(btc_df) >= 30:
                returns = df["close"].pct_change().tail(30)
                btc_returns = btc_df["close"].pct_change().tail(30)
                if len(returns) == len(btc_returns):
                    df["btc_correlation_30d"] = returns.corr(btc_returns)
                else:
                    df["btc_correlation_30d"] = np.nan
            else:
                df["btc_correlation_30d"] = np.nan
        else:
            df["btc_dominance_change"] = np.nan
            df["btc_correlation_30d"] = np.nan

        # ETH/BTC momentum
        if eth_df is not None and btc_df is not None and len(eth_df) >= 7 and len(btc_df) >= 7:
            eth_close = eth_df["close"].values
            btc_close = btc_df["close"].values
            eth_btc_ratio_now = eth_close[-1] / btc_close[-1]
            eth_btc_ratio_7d = eth_close[-7] / btc_close[-7]
            df["eth_btc_momentum"] = (eth_btc_ratio_now - eth_btc_ratio_7d) / eth_btc_ratio_7d
        else:
            df["eth_btc_momentum"] = np.nan

        # Alt season index (simple: coin momentum vs BTC momentum)
        if btc_df is not None and len(btc_df) >= 14 and len(df) >= 14:
            btc_close = btc_df["close"].values
            btc_mom_14 = (btc_close[-1] - btc_close[-14]) / btc_close[-14]
            coin_mom_14 = (df["close"].iloc[-1] - df["close"].iloc[-14]) / df["close"].iloc[-14]
            df["alt_season_index"] = coin_mom_14 - btc_mom_14
        else:
            df["alt_season_index"] = np.nan

        return df

    def _calculate_advanced_ta_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Advanced technical analysis features (6)"""
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # RSI 14
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df["rsi_14"] = 100 - (100 / (1 + rs))

        # MACD signal
        ema_12 = close.ewm(span=12, adjust=False).mean()
        ema_26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema_12 - ema_26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        df["macd_signal"] = macd_line - signal_line  # Histogram

        # Bollinger Bands width and position
        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        bb_upper = sma_20 + 2 * std_20
        bb_lower = sma_20 - 2 * std_20
        bb_range = bb_upper - bb_lower
        df["bb_width"] = bb_range / sma_20  # Normalized width
        df["bb_position"] = np.where(bb_range > 0, (close - bb_lower) / bb_range, 0.5)

        # ADX 14
        plus_dm = high.diff()
        minus_dm = -low.diff()
        plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
        minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)

        tr = np.maximum(
            high - low,
            np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1)))
        )
        atr_14 = pd.Series(tr, index=df.index).rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr_14.replace(0, np.nan))
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr_14.replace(0, np.nan))
        di_sum = plus_di + minus_di
        dx = 100 * abs(plus_di - minus_di) / di_sum.replace(0, np.nan)
        df["adx_14"] = dx.rolling(14).mean()

        # MFI 14 (Money Flow Index)
        typical_price = (high + low + close) / 3
        money_flow = typical_price * volume
        tp_diff = typical_price.diff()
        positive_flow = money_flow.where(tp_diff > 0, 0.0).rolling(14).sum()
        negative_flow = money_flow.where(tp_diff <= 0, 0.0).rolling(14).sum()
        mfi_ratio = positive_flow / negative_flow.replace(0, np.nan)
        df["mfi_14"] = 100 - (100 / (1 + mfi_ratio))

        return df

    def _calculate_regime_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """Regime features (4) — from pre-computed HMM or defaults"""
        if data is None:
            data = {}

        df["hmm_state"] = data.get("hmm_state", np.nan)
        df["regime_bull_prob"] = data.get("regime_bull_prob", np.nan)
        df["regime_bear_prob"] = data.get("regime_bear_prob", np.nan)

        # Volatility regime from rolling std
        returns = df["close"].pct_change()
        vol_20 = returns.rolling(20).std()
        vol_60 = returns.rolling(60).std()
        # >1 = expanding vol, <1 = contracting vol
        df["volatility_regime"] = np.where(vol_60 > 0, vol_20 / vol_60, 1.0)

        return df

    def _calculate_mean_reversion_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Mean-reversion features (5) — penalize overextended prices, detect reversion setups."""
        close = df["close"]

        # 1. Price z-score vs 20-day mean (how many std devs from short-term average)
        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std()
        df["price_zscore_20"] = (close - sma_20) / std_20.replace(0, np.nan)

        # 2. Price z-score vs 50-day mean (medium-term overextension)
        sma_50 = close.rolling(50).mean()
        std_50 = close.rolling(50).std()
        df["price_zscore_50"] = (close - sma_50) / std_50.replace(0, np.nan)

        # 3. Recent 5-day return (captures recent pump/dump)
        df["return_5d_pct"] = close.pct_change(5)

        # 4. Recent 10-day return
        df["return_10d_pct"] = close.pct_change(10)

        # 5. Overextension composite (0-1 scale, high = price overextended upward)
        # Normalize RSI to 0-1, BB position already 0-1, momentum_7d normalized
        rsi_norm = df["rsi_14"] / 100 if "rsi_14" in df.columns else 0.5
        bb_pos = df["bb_position"] if "bb_position" in df.columns else 0.5
        mom_7d = df["momentum_7d"] if "momentum_7d" in df.columns else 0.0
        # Clip momentum to reasonable range and normalize
        mom_norm = (mom_7d.clip(-0.2, 0.2) + 0.2) / 0.4  # Maps [-0.2, 0.2] -> [0, 1]
        df["overextension_score"] = (rsi_norm + bb_pos + mom_norm) / 3

        return df

    def _calculate_news_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """News features (3) — from NewsFetcher per-ticker data"""
        if data is None:
            data = {}
        df["news_sentiment_24h"] = data.get("news_sentiment_24h", np.nan)
        df["news_count_24h"] = data.get("news_count_24h", np.nan)
        df["news_impact_score"] = data.get("news_impact_score", np.nan)
        return df

    def _calculate_social_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """Social features (3) — from SocialFetcher per-ticker data"""
        if data is None:
            data = {}
        df["reddit_mentions_24h"] = data.get("reddit_mentions_24h", np.nan)
        df["reddit_sentiment"] = data.get("reddit_sentiment", np.nan)
        df["social_buzz_score"] = data.get("social_buzz_score", np.nan)
        return df

    def _calculate_whale_features(self, df: pd.DataFrame, data: Optional[Dict]) -> pd.DataFrame:
        """Whale features (3) — from WhaleFetcher"""
        if data is None:
            data = {}
        df["whale_tx_count_24h"] = data.get("whale_tx_count_24h", np.nan)
        df["whale_net_flow"] = data.get("whale_net_flow", np.nan)
        df["whale_activity_score"] = data.get("whale_activity_score", np.nan)
        return df

    # ------------------------------------------------------------------
    # Feature extraction
    # ------------------------------------------------------------------

    def get_feature_vector_v4(self, df: pd.DataFrame) -> pd.DataFrame:
        """Extract V4 feature vector in correct order"""
        if len(df) == 0:
            return pd.DataFrame()

        features = self.selected_features or self.required_features_v4
        available = [f for f in features if f in df.columns]
        missing = [f for f in features if f not in df.columns]

        if missing:
            logger.debug(f"Missing V4 features (will be NaN): {missing}")
            for feat in missing:
                df[feat] = np.nan

        return df[features].copy()

    def calculate_single_prediction_features_v4(
        self,
        ticker_data: pd.DataFrame,
        btc_data: Optional[pd.DataFrame] = None,
        eth_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None,
        derivatives_data: Optional[Dict] = None,
        onchain_data: Optional[Dict] = None,
        sentiment_data: Optional[Dict] = None,
        defi_data: Optional[Dict] = None,
        regime_data: Optional[Dict] = None,
        news_data: Optional[Dict] = None,
        social_data: Optional[Dict] = None,
        whale_data: Optional[Dict] = None,
    ) -> Optional[np.ndarray]:
        """Calculate V4 features for a single prediction (latest datapoint)"""
        try:
            df = self.calculate_features_v4(
                df=ticker_data,
                btc_df=btc_data,
                eth_df=eth_data,
                macro_data=macro_data,
                derivatives_data=derivatives_data,
                onchain_data=onchain_data,
                sentiment_data=sentiment_data,
                defi_data=defi_data,
                regime_data=regime_data,
                news_data=news_data,
                social_data=social_data,
                whale_data=whale_data,
            )
            if len(df) == 0:
                return None

            feature_df = self.get_feature_vector_v4(df)
            if len(feature_df) == 0:
                return None

            return feature_df.iloc[-1].values

        except Exception as e:
            logger.error(f"Failed to calculate V4 features: {e}")
            return None
