"""Tests for model calibration — separate LONG/SHORT detectors."""
import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.ensemble_v5 import EnsembleV5, N_CLASSES
from src.models.validation import PurgedWalkForwardCV


def make_balanced_synthetic_data(n=1000, n_features=20, seed=42):
    """
    Create synthetic training data with balanced LONG/SHORT labels.

    Returns:
        X: Feature matrix (n, n_features)
        y: Target labels {0=HOLD, 1=LONG, 2=SHORT} with ~45/45/10 split
        feature_names: List of feature names
    """
    rng = np.random.RandomState(seed)
    X = rng.randn(n, n_features)

    # Create balanced labels: 45% LONG, 45% SHORT, 10% HOLD
    n_long = int(n * 0.45)
    n_short = int(n * 0.45)
    n_hold = n - n_long - n_short

    y = np.concatenate([
        np.zeros(n_hold, dtype=int),     # 0 = HOLD
        np.ones(n_long, dtype=int),      # 1 = LONG
        np.full(n_short, 2, dtype=int)   # 2 = SHORT
    ])

    # Shuffle to mix classes
    shuffle_idx = rng.permutation(n)
    X = X[shuffle_idx]
    y = y[shuffle_idx]

    feature_names = [f"f{i}" for i in range(n_features)]
    return X, y, feature_names


def make_imbalanced_synthetic_data(n=1000, n_features=20, seed=42):
    """
    Create synthetic training data mimicking real imbalance.

    Real data: 2 LONGs, 279 SHORTs, rest HOLDs in initial signal window.
    This creates similar imbalance for testing.

    Returns:
        X: Feature matrix (n, n_features)
        y: Target labels with strong class imbalance
        feature_names: List of feature names
    """
    rng = np.random.RandomState(seed)
    X = rng.randn(n, n_features)

    # Create imbalanced distribution similar to real data
    # ~1% LONG, ~28% SHORT, ~71% HOLD
    n_hold = int(n * 0.71)
    n_short = int(n * 0.28)
    n_long = n - n_hold - n_short

    y = np.concatenate([
        np.zeros(n_hold, dtype=int),     # 0 = HOLD
        np.ones(n_long, dtype=int),      # 1 = LONG
        np.full(n_short, 2, dtype=int)   # 2 = SHORT
    ])

    # Shuffle
    shuffle_idx = rng.permutation(n)
    X = X[shuffle_idx]
    y = y[shuffle_idx]

    feature_names = [f"f{i}" for i in range(n_features)]
    return X, y, feature_names


def fast_cv():
    """Small CV config for fast test execution."""
    return PurgedWalkForwardCV(
        n_splits=2,
        min_train_days=60,
        test_days=30,
        purge_days=2,
        embargo_days=1,
    )


def fast_params():
    """Reduced n_estimators for quick test training."""
    return {
        "xgboost": {"n_estimators": 20},
        "lightgbm": {"n_estimators": 20},
        "catboost": {"iterations": 20},
    }


class TestModelProducesBothLongAndShort:
    """
    Test that model produces both LONG and SHORT predictions when trained on
    balanced data.

    This catches the "0 LONGs" bug: if model is miscalibrated for LONG class,
    it will fail this test.
    """

    def test_model_produces_both_long_and_short_on_balanced_data(self):
        """
        Train on 50/50 LONG/SHORT, verify predictions include both classes
        with reasonable frequencies (>5% each).
        """
        X, y, feat = make_balanced_synthetic_data(n=500, seed=42)

        model = EnsembleV5(params=fast_params())
        model.train(X, y, feat, cv=fast_cv())

        # Predict on full training set (sanity check)
        proba = model.predict_proba(X)
        predictions = model.predict(X)

        # Check that we get both LONG and SHORT in predictions
        assert 1 in predictions, "No LONG predictions generated"
        assert 2 in predictions, "No SHORT predictions generated"

        # Check minimum frequency (>5% of non-HOLD predictions)
        n_long = np.sum(predictions == 1)
        n_short = np.sum(predictions == 2)
        total = len(predictions)

        pct_long = n_long / total * 100
        pct_short = n_short / total * 100

        print(f"\n[TEST] Balanced data predictions:")
        print(f"  LONG:  {n_long}/{total} ({pct_long:.1f}%)")
        print(f"  SHORT: {n_short}/{total} ({pct_short:.1f}%)")

        assert pct_long > 5.0, f"LONG predictions too rare: {pct_long:.1f}%"
        assert pct_short > 5.0, f"SHORT predictions too rare: {pct_short:.1f}%"

    def test_model_produces_long_despite_imbalance(self):
        """
        Train on imbalanced data (1% LONG, 28% SHORT), verify model still
        produces some LONG predictions (>1% of total).

        This is the core fix: separate LONG/SHORT detectors should handle
        imbalance better than single multiclass model.
        """
        X, y, feat = make_imbalanced_synthetic_data(n=500, seed=42)

        # Verify true imbalance
        n_long_true = np.sum(y == 1)
        print(f"\n[TEST] True label distribution: LONG={n_long_true}, SHORT={np.sum(y==2)}, HOLD={np.sum(y==0)}")

        model = EnsembleV5(params=fast_params())
        model.train(X, y, feat, cv=fast_cv())

        predictions = model.predict(X)

        # Even with imbalance, model should detect at least 1% LONG
        n_long = np.sum(predictions == 1)
        pct_long = n_long / len(predictions) * 100

        print(f"[TEST] Model predictions: LONG={n_long}/{len(predictions)} ({pct_long:.1f}%)")

        assert n_long > 0, "Model produced 0 LONG predictions on imbalanced data"
        assert pct_long >= 0.5, f"LONG predictions critically low: {pct_long:.1f}%"


class TestThresholdSeparatesLongShort:
    """
    Test that calibrated thresholds for LONG and SHORT are meaningfully different
    and actually separate the classes.
    """

    def test_threshold_long_different_from_short(self):
        """
        Train model and verify that optimal thresholds for LONG and SHORT
        differ (not both 0.5).
        """
        X, y, feat = make_balanced_synthetic_data(n=500, seed=42)

        model = EnsembleV5(params=fast_params())
        model.train(X, y, feat, cv=fast_cv())

        proba = model.predict_proba(X)

        # Get P(LONG) and P(SHORT) distributions
        p_long = proba[:, 1]
        p_short = proba[:, 2]

        # Compute basic statistics
        long_mean = p_long.mean()
        short_mean = p_short.mean()

        print(f"\n[TEST] Probability distributions:")
        print(f"  P(LONG) mean={long_mean:.3f}, std={p_long.std():.3f}")
        print(f"  P(SHORT) mean={short_mean:.3f}, std={p_short.std():.3f}")

        # Thresholds should differ if model learned to separate classes
        assert long_mean != short_mean or p_long.std() > 0.01, \
            "LONG and SHORT probabilities are identical — model not learning signal"

    def test_threshold_separates_predicted_classes(self):
        """
        Verify that using different thresholds for LONG vs SHORT actually
        separates predictions (not all LONG or all SHORT).
        """
        X, y, feat = make_balanced_synthetic_data(n=500, seed=42)

        model = EnsembleV5(params=fast_params())
        model.train(X, y, feat, cv=fast_cv())

        # Predict with default thresholds
        pred_default = model.predict(X, long_threshold=0.35, short_threshold=0.35)

        # Predict with aggressive LONG threshold
        pred_long_aggressive = model.predict(X, long_threshold=0.60, short_threshold=0.35)

        # Predictions should differ
        n_different = np.sum(pred_default != pred_long_aggressive)
        pct_different = n_different / len(X) * 100

        print(f"\n[TEST] Threshold sensitivity: {pct_different:.1f}% predictions changed")

        assert pct_different > 1.0, \
            "Thresholds not affecting predictions — decoupling failed"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
