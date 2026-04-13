"""
REGIME DETECTOR (HMM)
======================
3-state Gaussian Hidden Markov Model:
- Bull / Sideways / Bear
- Input: BTC daily returns + 14d rolling volatility
- Retrained monthly on 2 years of data
"""

import json
import pickle
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger


class RegimeDetector:
    """
    Market regime detection using Gaussian HMM.
    States: 0=Bull, 1=Sideways, 2=Bear (ordered by mean return after training).
    """

    def __init__(self, n_states: int = 3, vol_window: int = 14, lookback_years: int = 2):
        self.n_states = n_states
        self.vol_window = vol_window
        self.lookback_years = lookback_years
        self.model = None
        self.state_mapping: Dict[int, str] = {}

    def _prepare_features(self, df: pd.DataFrame) -> np.ndarray:
        """Prepare HMM input features from BTC OHLCV data"""
        close = df["close"]
        returns = close.pct_change().fillna(0)
        volatility = returns.rolling(self.vol_window).std().fillna(returns.std())

        features = np.column_stack([returns.values, volatility.values])
        # Remove initial NaN rows
        valid_start = self.vol_window
        return features[valid_start:]

    def train(self, btc_df: pd.DataFrame):
        """
        Train HMM on BTC daily data.

        Args:
            btc_df: BTC OHLCV DataFrame (should be 2+ years)
        """
        try:
            from hmmlearn.hmm import GaussianHMM
        except ImportError:
            raise ImportError("hmmlearn is required: pip install hmmlearn")

        features = self._prepare_features(btc_df)
        if len(features) < 100:
            raise ValueError(f"Not enough data to train HMM: {len(features)} samples")

        logger.info(f"Training HMM on {len(features)} samples...")

        self.model = GaussianHMM(
            n_components=self.n_states,
            covariance_type="full",
            n_iter=200,
            random_state=42,
            tol=1e-4,
        )
        self.model.fit(features)

        # Determine state mapping by mean returns
        states = self.model.predict(features)
        returns = features[:, 0]

        state_returns = {}
        for s in range(self.n_states):
            mask = states == s
            state_returns[s] = returns[mask].mean() if mask.sum() > 0 else 0.0

        # Sort by mean return: highest = Bull, lowest = Bear
        sorted_states = sorted(state_returns.keys(), key=lambda s: state_returns[s], reverse=True)
        names = ["Bull", "Sideways", "Bear"]
        self.state_mapping = {sorted_states[i]: names[i] for i in range(min(len(sorted_states), len(names)))}

        logger.info(f"HMM trained. State mapping: {self.state_mapping}")
        for s in range(self.n_states):
            name = self.state_mapping.get(s, f"State_{s}")
            count = int((states == s).sum())
            mean_ret = state_returns[s] * 100
            logger.info(f"  {name} (state {s}): {count} days, mean return={mean_ret:.3f}%")

    def predict(self, btc_df: pd.DataFrame) -> Dict[str, float]:
        """
        Predict current regime.

        Returns:
            Dict with hmm_state (int), regime_bull_prob, regime_bear_prob, regime_name
        """
        if self.model is None:
            return {
                "hmm_state": np.nan,
                "regime_bull_prob": np.nan,
                "regime_bear_prob": np.nan,
                "regime_name": "unknown",
            }

        features = self._prepare_features(btc_df)
        if len(features) == 0:
            return {
                "hmm_state": np.nan,
                "regime_bull_prob": np.nan,
                "regime_bear_prob": np.nan,
                "regime_name": "unknown",
            }

        # Get state probabilities for the latest observation
        log_probs = self.model.score_samples(features)
        posteriors = log_probs[1]  # State posteriors
        latest_probs = posteriors[-1] if len(posteriors.shape) > 1 else np.zeros(self.n_states)

        # Current state
        current_state = self.model.predict(features[-1:].reshape(1, -1))[0]
        regime_name = self.state_mapping.get(current_state, f"State_{current_state}")

        # Find bull and bear state indices
        bull_state = next((s for s, n in self.state_mapping.items() if n == "Bull"), 0)
        bear_state = next((s for s, n in self.state_mapping.items() if n == "Bear"), 2)

        bull_prob = float(latest_probs[bull_state]) if len(latest_probs) > bull_state else 0.33
        bear_prob = float(latest_probs[bear_state]) if len(latest_probs) > bear_state else 0.33

        return {
            "hmm_state": float(current_state),
            "regime_bull_prob": bull_prob,
            "regime_bear_prob": bear_prob,
            "regime_name": regime_name,
        }

    def fast_regime_check(self, btc_df: pd.DataFrame) -> str:
        """
        Fast regime detection using 7d BTC returns + volatility.
        Supplements the slower HMM for quicker regime change detection.
        """
        if btc_df is None or len(btc_df) < 10:
            return "Sideways"

        close = btc_df["close"].astype(float)
        returns_7d = (close.iloc[-1] / close.iloc[-8] - 1) if len(close) >= 8 else 0
        daily_returns = close.pct_change().dropna().tail(7)
        vol_7d = float(daily_returns.std()) if len(daily_returns) >= 5 else 0.03

        if returns_7d > 0.05 and vol_7d < 0.04:
            return "Bull"
        elif returns_7d < -0.08:
            return "Bear"
        elif vol_7d > 0.06:
            return "Bear"  # High vol = defensive
        else:
            return "Sideways"

    def get_composite_regime(self, btc_df: pd.DataFrame) -> Dict:
        """
        Combine HMM + fast regime. Use HMM when confident, fast otherwise.
        Returns same format as predict().
        """
        hmm_result = self.predict(btc_df)
        fast_regime = self.fast_regime_check(btc_df)

        # If HMM has high confidence in a regime, trust it
        bull_prob = hmm_result.get("regime_bull_prob", 0.33)
        bear_prob = hmm_result.get("regime_bear_prob", 0.33)
        max_prob = max(bull_prob, bear_prob, 1 - bull_prob - bear_prob)

        if max_prob >= 0.7 and hmm_result.get("regime_name") != "unknown":
            hmm_result["detection_method"] = "HMM"
            return hmm_result

        # Otherwise use fast regime
        hmm_result["regime_name"] = fast_regime
        hmm_result["detection_method"] = "fast"
        return hmm_result

    def get_regime_multiplier(self, regime_data: Optional[Dict] = None) -> float:
        """
        Get position size multiplier based on regime.
        Bull → 1.0, Sideways → 0.7, Bear → 0.5
        """
        if regime_data is None:
            return 0.7  # Default: sideways

        name = regime_data.get("regime_name", "Sideways")
        multipliers = {"Bull": 1.0, "Sideways": 0.7, "Bear": 0.5}
        return multipliers.get(name, 0.7)

    def save(self, path: str):
        """Save trained model"""
        save_path = Path(path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "wb") as f:
            pickle.dump({"model": self.model, "state_mapping": self.state_mapping}, f)
        logger.info(f"Regime detector saved to {save_path}")

    def load(self, path: str):
        """Load trained model"""
        with open(path, "rb") as f:
            data = pickle.load(f)
        self.model = data["model"]
        self.state_mapping = data["state_mapping"]
        logger.info(f"Regime detector loaded from {path}")
