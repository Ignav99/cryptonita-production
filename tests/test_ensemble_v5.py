"""Tests for EnsembleV5 — ternary classifier."""
import numpy as np
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.ensemble_v5 import EnsembleV5, N_CLASSES
from src.models.validation import PurgedWalkForwardCV


def make_synthetic_data(n=200, n_features=20, seed=42):
    rng = np.random.RandomState(seed)
    X = rng.randn(n, n_features)
    # Create synthetic ternary labels with some signal
    y = rng.choice([0, 1, 2], size=n, p=[0.5, 0.3, 0.2])
    feature_names = [f"f{i}" for i in range(n_features)]
    return X, y, feature_names


def fast_cv():
    """Small CV config so tests run in seconds on synthetic data."""
    return PurgedWalkForwardCV(
        n_splits=2,
        min_train_days=60,
        test_days=30,
        purge_days=2,
        embargo_days=1,
    )


def fast_params():
    """Reduced n_estimators so base models train quickly in tests."""
    return {
        "xgboost": {"n_estimators": 20},
        "lightgbm": {"n_estimators": 20},
        "catboost": {"iterations": 20},
    }


def test_predict_proba_shape():
    X, y, feat = make_synthetic_data()
    model = EnsembleV5(params=fast_params())
    model.train(X, y, feat, cv=fast_cv())
    proba = model.predict_proba(X[:10])
    assert proba.shape == (10, N_CLASSES), f"Expected (10, 3), got {proba.shape}"


def test_predict_proba_sums_to_one():
    X, y, feat = make_synthetic_data()
    model = EnsembleV5(params=fast_params())
    model.train(X, y, feat, cv=fast_cv())
    proba = model.predict_proba(X[:20])
    sums = proba.sum(axis=1)
    np.testing.assert_allclose(sums, 1.0, atol=1e-5)


def test_predict_returns_valid_classes():
    X, y, feat = make_synthetic_data()
    model = EnsembleV5(params=fast_params())
    model.train(X, y, feat, cv=fast_cv())
    preds = model.predict(X[:30])
    assert set(preds).issubset({0, 1, 2}), f"Invalid classes: {set(preds)}"


def test_get_signal_returns_tuple():
    X, y, feat = make_synthetic_data()
    model = EnsembleV5(params=fast_params())
    model.train(X, y, feat, cv=fast_cv())
    proba = model.predict_proba(X[:1])[0]
    cls, name, conf = model.get_signal(proba)
    assert cls in {0, 1, 2}
    assert name in {"HOLD", "LONG", "SHORT"}
    assert 0.0 <= conf <= 1.0


def test_save_load(tmp_path):
    X, y, feat = make_synthetic_data()
    model = EnsembleV5(params=fast_params())
    model.train(X, y, feat, cv=fast_cv())

    model.save(str(tmp_path))

    model2 = EnsembleV5()
    model2.load(str(tmp_path))

    proba1 = model.predict_proba(X[:5])
    proba2 = model2.predict_proba(X[:5])
    np.testing.assert_allclose(proba1, proba2, atol=1e-4)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
