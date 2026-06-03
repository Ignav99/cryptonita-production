"""
TRIPLE-BARRIER LABELING
========================
Dynamic ATR-based labels replacing fixed ">20% in 15 days".

- Upper barrier: entry + 2.5 * ATR(14)  → take profit (+1)
- Lower barrier: entry - 1.5 * ATR(14)  → stop loss   (-1)
- Time barrier:  15 days max holding     → expired      (0)
"""

import numpy as np
import pandas as pd
from typing import Dict, List
from loguru import logger


class TripleBarrierLabeler:
    """
    Triple-barrier labeling with ATR-based dynamic thresholds.
    """

    def __init__(
        self,
        tp_atr_mult: float = 2.5,
        sl_atr_mult: float = 1.5,
        max_holding_days: int = 15,
        atr_period: int = 14,
        forward_skip: int = 3,
    ):
        self.tp_atr_mult = tp_atr_mult
        self.sl_atr_mult = sl_atr_mult
        self.max_holding_days = max_holding_days
        self.atr_period = atr_period
        self.forward_skip = forward_skip  # Bars between features and entry to break autocorrelation

    def _compute_atr(self, df: pd.DataFrame) -> pd.Series:
        """Compute ATR(14)"""
        high = df["high"]
        low = df["low"]
        close = df["close"]
        tr = np.maximum(
            high - low,
            np.maximum(abs(high - close.shift(1)), abs(low - close.shift(1)))
        )
        return tr.rolling(self.atr_period).mean()

    def label(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Apply triple-barrier labeling to OHLCV DataFrame.

        Args:
            df: DataFrame with columns [open, high, low, close, volume]
                Must be sorted by date ascending.

        Returns:
            DataFrame with added columns:
                - label: +1 (TP hit first), -1 (SL hit first), 0 (time expired)
                - days_held: number of days position was open
                - barrier_hit: 'tp', 'sl', or 'time'
                - max_favorable: max favorable excursion (%)
                - max_adverse: max adverse excursion (%)
                - tp_price: take-profit price level
                - sl_price: stop-loss price level
        """
        df = df.copy()
        atr = self._compute_atr(df)

        n = len(df)
        labels = np.full(n, np.nan)
        days_held = np.full(n, np.nan)
        barrier_hit = np.full(n, "", dtype=object)
        max_favorable = np.full(n, np.nan)
        max_adverse = np.full(n, np.nan)
        tp_prices = np.full(n, np.nan)
        sl_prices = np.full(n, np.nan)

        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values

        for i in range(n):
            if np.isnan(atr.iloc[i]):
                continue

            # Forward skip: enter at close[i + forward_skip] to break autocorrelation
            entry_idx = i + self.forward_skip
            if entry_idx >= n:
                continue

            entry = closes[entry_idx]
            current_atr = atr.iloc[i]  # ATR from feature bar, not entry bar
            tp = entry + self.tp_atr_mult * current_atr
            sl = entry - self.sl_atr_mult * current_atr
            tp_prices[i] = tp
            sl_prices[i] = sl

            end_idx = min(entry_idx + self.max_holding_days, n)

            best_excursion = 0.0
            worst_excursion = 0.0
            label = 0  # Default: time expired
            hit = "time"
            held = end_idx - entry_idx

            for j in range(entry_idx + 1, end_idx):
                # Track excursions
                high_exc = (highs[j] - entry) / entry
                low_exc = (lows[j] - entry) / entry
                best_excursion = max(best_excursion, high_exc)
                worst_excursion = min(worst_excursion, low_exc)

                # Check barriers
                if highs[j] >= tp:
                    label = 1
                    hit = "tp"
                    held = j - i
                    break
                if lows[j] <= sl:
                    label = -1
                    hit = "sl"
                    held = j - i
                    break

            labels[i] = label
            days_held[i] = held
            barrier_hit[i] = hit
            max_favorable[i] = best_excursion
            max_adverse[i] = worst_excursion

        df["label"] = labels
        df["days_held"] = days_held
        df["barrier_hit"] = barrier_hit
        df["max_favorable"] = max_favorable
        df["max_adverse"] = max_adverse
        df["tp_price"] = tp_prices
        df["sl_price"] = sl_prices

        # Drop rows without valid labels (warm-up + tail)
        valid = df["label"].notna()
        logger.info(
            f"Labeled {valid.sum()}/{n} rows: "
            f"+1={int((labels == 1).sum())}, -1={int((labels == -1).sum())}, "
            f"0={int((labels == 0).sum())}"
        )

        return df

    def label_for_binary(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Label for binary classification: +1 → 1 (BUY), else → 0 (HOLD).
        This matches the V3 model interface.
        """
        df = self.label(df)
        df["target"] = (df["label"] == 1).astype(int)
        return df

    def label_for_ternary(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Label for ternary classification:
          +1 (TP hit)  → target = 1 (LONG)
           0 (time)    → target = 0 (HOLD)
          -1 (SL hit)  → target = 2 (SHORT)

        Class mapping:
          0 = HOLD  (time barrier)
          1 = LONG  (take profit hit first)
          2 = SHORT (stop loss hit first — short this coin)

        Returns DataFrame with added 'target' column (0, 1, or 2).
        """
        df = self.label(df)
        # Map: +1→1 (LONG), 0→0 (HOLD), -1→2 (SHORT)
        label_map = {1: 1, 0: 0, -1: 2}
        df["target"] = df["label"].map(label_map).fillna(0).astype(int)
        logger.info(
            f"Ternary labels: LONG={int((df['target'] == 1).sum())}, "
            f"HOLD={int((df['target'] == 0).sum())}, "
            f"SHORT={int((df['target'] == 2).sum())}"
        )
        return df

    def get_class_weights(self, df: pd.DataFrame) -> dict:
        """
        Compute inverse-frequency class weights for ternary classification.
        Useful for imbalanced datasets where HOLD >> LONG/SHORT.

        Returns:
            dict {0: w_hold, 1: w_long, 2: w_short} for use with
            XGBoost sample_weight, LightGBM class_weight, etc.
        """
        if "target" not in df.columns:
            raise ValueError("DataFrame must have 'target' column. Call label_for_ternary() first.")

        counts = df["target"].value_counts()
        total = len(df)
        n_classes = 3

        weights = {}
        for cls in [0, 1, 2]:
            count = counts.get(cls, 1)
            weights[cls] = total / (n_classes * count)

        logger.info(
            f"Class weights: HOLD(0)={weights[0]:.3f}, "
            f"LONG(1)={weights[1]:.3f}, SHORT(2)={weights[2]:.3f}"
        )
        return weights

    def get_stats(self, df: pd.DataFrame) -> Dict:
        """Get labeling statistics"""
        if "label" not in df.columns:
            return {}
        labels = df["label"].dropna()
        return {
            "total": len(labels),
            "tp_count": int((labels == 1).sum()),
            "sl_count": int((labels == -1).sum()),
            "time_count": int((labels == 0).sum()),
            "tp_rate": float((labels == 1).mean()),
            "avg_days_held": float(df["days_held"].dropna().mean()),
            "avg_max_favorable": float(df["max_favorable"].dropna().mean()),
            "avg_max_adverse": float(df["max_adverse"].dropna().mean()),
        }
