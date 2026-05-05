"""
HOLD TIME ESTIMATOR
===================
Predicts optimal holding time for positions based on historical data.
Uses a lookup table bucketed by tier x probability range.
"""

import json
import os
from typing import Dict, Optional
from loguru import logger


# Default hold time estimates (days) until bootstrap runs
DEFAULT_LOOKUP = {
    "1": {
        "0.25-0.30": {"median_days": 5, "p75_days": 8, "avg_max_gain": 0.12, "samples": 0},
        "0.30-0.35": {"median_days": 7, "p75_days": 11, "avg_max_gain": 0.18, "samples": 0},
        "0.35-0.42": {"median_days": 9, "p75_days": 14, "avg_max_gain": 0.25, "samples": 0},
    },
    "2": {
        "0.25-0.30": {"median_days": 4, "p75_days": 7, "avg_max_gain": 0.10, "samples": 0},
        "0.30-0.35": {"median_days": 6, "p75_days": 9, "avg_max_gain": 0.15, "samples": 0},
        "0.35-0.42": {"median_days": 8, "p75_days": 12, "avg_max_gain": 0.22, "samples": 0},
    },
    "3": {
        "0.25-0.30": {"median_days": 3, "p75_days": 5, "avg_max_gain": 0.08, "samples": 0},
        "0.30-0.35": {"median_days": 5, "p75_days": 8, "avg_max_gain": 0.12, "samples": 0},
        "0.35-0.42": {"median_days": 7, "p75_days": 10, "avg_max_gain": 0.18, "samples": 0},
    },
    "4": {
        "0.25-0.30": {"median_days": 2, "p75_days": 4, "avg_max_gain": 0.06, "samples": 0},
        "0.30-0.35": {"median_days": 3, "p75_days": 5, "avg_max_gain": 0.10, "samples": 0},
        "0.35-0.42": {"median_days": 5, "p75_days": 8, "avg_max_gain": 0.15, "samples": 0},
    },
}

PROB_BUCKETS = [(0.25, 0.30), (0.30, 0.35), (0.35, 0.42)]


class HoldTimeEstimator:
    """Estimates optimal hold time for positions using tier x probability lookup."""

    def __init__(self, lookup_path: str = "models/hold_time_lookup.json"):
        self.lookup_path = lookup_path
        self._lookup = self._load_or_bootstrap(lookup_path)
        logger.info(f"HoldTimeEstimator initialized (path={lookup_path})")

    def _load_or_bootstrap(self, path: str) -> Dict:
        """Load lookup table from disk, or use defaults."""
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                logger.info(f"Loaded hold time lookup from {path}")
                return data
            except Exception as e:
                logger.warning(f"Could not load lookup from {path}: {e}")
        return DEFAULT_LOOKUP.copy()

    def _save(self) -> None:
        """Persist lookup table to disk."""
        try:
            os.makedirs(os.path.dirname(self.lookup_path) or '.', exist_ok=True)
            with open(self.lookup_path, 'w') as f:
                json.dump(self._lookup, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save lookup: {e}")

    def _get_prob_bucket(self, probability: float) -> str:
        """Map a probability to its bucket key."""
        for low, high in PROB_BUCKETS:
            if low <= probability < high:
                return f"{low:.2f}-{high:.2f}"
        # Clamp to nearest bucket
        if probability < PROB_BUCKETS[0][0]:
            return f"{PROB_BUCKETS[0][0]:.2f}-{PROB_BUCKETS[0][1]:.2f}"
        return f"{PROB_BUCKETS[-1][0]:.2f}-{PROB_BUCKETS[-1][1]:.2f}"

    def estimate(self, ticker: str, probability: float, tier: int) -> Dict:
        """
        Estimate hold time for a position.

        Returns:
            Dict with predicted_hold_days, max_hold_days, expected_max_gain_pct, confidence
        """
        tier_key = str(min(max(tier, 1), 4))
        bucket_key = self._get_prob_bucket(probability)

        tier_data = self._lookup.get(tier_key, DEFAULT_LOOKUP["3"])
        bucket_data = tier_data.get(bucket_key)

        if bucket_data is None:
            # Fallback to middle bucket
            bucket_data = tier_data.get("0.30-0.35", {"median_days": 5, "p75_days": 8, "avg_max_gain": 0.12, "samples": 0})

        samples = bucket_data.get("samples", 0)
        confidence = "bootstrap" if samples < 10 else ("low" if samples < 30 else "medium" if samples < 100 else "high")

        return {
            "predicted_hold_days": bucket_data["median_days"],
            "max_hold_days": bucket_data["p75_days"],
            "expected_max_gain_pct": bucket_data["avg_max_gain"],
            "confidence": confidence,
            "samples": samples,
        }

    def bootstrap_from_labels(self, labeled_df) -> Dict:
        """
        Build lookup table from Triple Barrier Labeler output.

        Expected columns: ticker, tier, probability, days_held, max_favorable_excursion
        """
        import numpy as np

        new_lookup = {}
        for tier in range(1, 5):
            tier_key = str(tier)
            new_lookup[tier_key] = {}
            tier_df = labeled_df[labeled_df['tier'] == tier]

            for low, high in PROB_BUCKETS:
                bucket_key = f"{low:.2f}-{high:.2f}"
                mask = (tier_df['probability'] >= low) & (tier_df['probability'] < high)
                bucket_df = tier_df[mask]

                if len(bucket_df) >= 3:
                    new_lookup[tier_key][bucket_key] = {
                        "median_days": float(np.median(bucket_df['days_held'])),
                        "p75_days": float(np.percentile(bucket_df['days_held'], 75)),
                        "avg_max_gain": float(bucket_df['max_favorable_excursion'].mean()),
                        "samples": len(bucket_df),
                    }
                else:
                    # Keep defaults for sparse buckets
                    new_lookup[tier_key][bucket_key] = DEFAULT_LOOKUP[tier_key][bucket_key]

        self._lookup = new_lookup
        self._save()
        logger.info("Hold time lookup bootstrapped from labeled data")
        return new_lookup

    def update_from_closed_trade(self, trade: Dict) -> None:
        """
        Incrementally update statistics with a real closed trade.

        Expected keys: tier, probability, days_held, max_gain_pct
        """
        tier_key = str(min(max(trade.get('tier', 3), 1), 4))
        bucket_key = self._get_prob_bucket(trade.get('probability', 0.30))

        if tier_key not in self._lookup:
            self._lookup[tier_key] = {}
        if bucket_key not in self._lookup[tier_key]:
            self._lookup[tier_key][bucket_key] = DEFAULT_LOOKUP.get(tier_key, DEFAULT_LOOKUP["3"]).get(bucket_key, {
                "median_days": 5, "p75_days": 8, "avg_max_gain": 0.12, "samples": 0
            })

        cell = self._lookup[tier_key][bucket_key]
        n = cell.get("samples", 0)
        days = trade.get('days_held', 5)
        gain = trade.get('max_gain_pct', 0.0)

        # Exponential moving average update
        alpha = min(0.1, 1.0 / (n + 1))
        cell["median_days"] = cell["median_days"] * (1 - alpha) + days * alpha
        cell["p75_days"] = max(cell["p75_days"], cell["median_days"] * 1.4)
        cell["avg_max_gain"] = cell["avg_max_gain"] * (1 - alpha) + gain * alpha
        cell["samples"] = n + 1

        self._save()
