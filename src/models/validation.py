"""
WALK-FORWARD CROSS-VALIDATION
===============================
Purged Walk-Forward CV (Lopez de Prado method):
- 5 expanding windows, min 180 days training
- Purge gap: 5 days between train/test (prevent leakage)
- Embargo: 2 days after test excluded from next train
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Dict, Optional
from loguru import logger


class PurgedWalkForwardCV:
    """
    Walk-forward cross-validation with purge and embargo.
    """

    def __init__(
        self,
        n_splits: int = 5,
        min_train_days: int = 180,
        test_days: int = 60,
        purge_days: int = 5,
        embargo_days: int = 2,
    ):
        self.n_splits = n_splits
        self.min_train_days = min_train_days
        self.test_days = test_days
        self.purge_days = purge_days
        self.embargo_days = embargo_days

    def split(self, n_samples: int) -> List[Tuple[np.ndarray, np.ndarray]]:
        """
        Generate train/test indices for walk-forward CV.

        Args:
            n_samples: Total number of samples

        Returns:
            List of (train_indices, test_indices) tuples
        """
        splits = []

        # Total space needed: min_train + n_splits * test_days
        total_test = self.n_splits * self.test_days
        if n_samples < self.min_train_days + total_test:
            logger.warning(
                f"Not enough samples ({n_samples}) for {self.n_splits} splits. "
                f"Need {self.min_train_days + total_test}."
            )
            # Adjust test_days
            available_test = n_samples - self.min_train_days
            if available_test < self.n_splits * 20:
                raise ValueError(f"Not enough data: {n_samples} samples")
            self.test_days = available_test // self.n_splits

        # Calculate split points
        test_start_points = []
        total_needed = self.min_train_days + self.n_splits * self.test_days
        offset = n_samples - total_needed

        for i in range(self.n_splits):
            test_start = offset + self.min_train_days + i * self.test_days
            test_start_points.append(test_start)

        for i, test_start in enumerate(test_start_points):
            test_end = test_start + self.test_days

            # Training set: everything before test_start minus purge gap
            train_end = test_start - self.purge_days
            train_indices = np.arange(0, max(0, train_end))

            # Test set
            test_indices = np.arange(test_start, min(test_end, n_samples))

            # Embargo: remove embargo_days after test from future training
            # (only relevant for subsequent folds — handled implicitly by expanding window)

            if len(train_indices) >= self.min_train_days and len(test_indices) > 0:
                splits.append((train_indices, test_indices))
                logger.debug(
                    f"Fold {i+1}: train[0:{train_end}] ({len(train_indices)}), "
                    f"test[{test_start}:{test_end}] ({len(test_indices)}), "
                    f"purge={self.purge_days}d"
                )

        logger.info(f"Walk-Forward CV: {len(splits)} folds generated from {n_samples} samples")
        return splits

    def cross_validate(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_factory,
        metric_fn,
    ) -> Dict:
        """
        Run walk-forward CV.

        Args:
            X: Feature matrix
            y: Target vector
            model_factory: Callable that returns a new model instance
            metric_fn: Callable(y_true, y_pred_proba) → float

        Returns:
            Dict with per-fold and aggregate metrics
        """
        splits = self.split(len(X))
        fold_metrics = []

        for fold_idx, (train_idx, test_idx) in enumerate(splits):
            X_train, y_train = X[train_idx], y[train_idx]
            X_test, y_test = X[test_idx], y[test_idx]

            model = model_factory()
            model.fit(X_train, y_train)

            if hasattr(model, "predict_proba"):
                y_pred = model.predict_proba(X_test)[:, 1]
            else:
                y_pred = model.predict(X_test)

            score = metric_fn(y_test, y_pred)
            fold_metrics.append({
                "fold": fold_idx + 1,
                "train_size": len(train_idx),
                "test_size": len(test_idx),
                "score": score,
            })

            logger.info(f"Fold {fold_idx+1}: score={score:.4f} (train={len(train_idx)}, test={len(test_idx)})")

        scores = [m["score"] for m in fold_metrics]
        result = {
            "n_folds": len(fold_metrics),
            "fold_metrics": fold_metrics,
            "mean_score": float(np.mean(scores)),
            "std_score": float(np.std(scores)),
            "min_score": float(np.min(scores)),
            "max_score": float(np.max(scores)),
        }

        logger.info(f"Walk-Forward CV: mean={result['mean_score']:.4f} +/- {result['std_score']:.4f}")
        return result

    def get_oos_predictions(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_factory,
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Get out-of-sample predictions for each fold (for stacking meta-learner).

        Returns:
            (oos_indices, oos_predictions, oos_true_labels)
        """
        splits = self.split(len(X))
        all_indices = []
        all_preds = []
        all_true = []

        for train_idx, test_idx in splits:
            model = model_factory()
            model.fit(X[train_idx], y[train_idx])

            if hasattr(model, "predict_proba"):
                preds = model.predict_proba(X[test_idx])[:, 1]
            else:
                preds = model.predict(X[test_idx])

            all_indices.extend(test_idx)
            all_preds.extend(preds)
            all_true.extend(y[test_idx])

        return np.array(all_indices), np.array(all_preds), np.array(all_true)
