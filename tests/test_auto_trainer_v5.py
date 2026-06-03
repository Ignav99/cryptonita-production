"""Tests for AutoTrainerV5 — mocked Binance + feature engineering."""
import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.auto_trainer_v5 import AutoTrainerV5
from src.models.per_coin_model_store import PerCoinModelStore


def make_ohlcv(n=300, seed=42):
    rng = np.random.RandomState(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.015, n))
    return pd.DataFrame({
        "timestamp": pd.date_range("2023-01-01", periods=n, freq="1D"),
        "open": close * 0.999, "high": close * 1.015,
        "low": close * 0.985, "close": close,
        "volume": rng.uniform(1e6, 1e7, n),
    })


def make_features_df(n=200, seed=42):
    """Labeled features DataFrame for mocking."""
    rng = np.random.RandomState(seed)
    df = pd.DataFrame({
        f"f{i}": rng.randn(n) for i in range(20)
    })
    # Add ternary target (roughly balanced)
    df["target"] = rng.choice([0, 1, 2], size=n, p=[0.5, 0.3, 0.2])
    df["label"] = df["target"].map({1: 1, 0: 0, 2: -1})
    return df


@pytest.fixture
def store(tmp_path):
    return PerCoinModelStore(base_dir=str(tmp_path / "v5_models"))


@pytest.fixture
def trainer(store):
    return AutoTrainerV5(model_store=store)


def test_trainer_has_store(trainer, store):
    assert trainer.store is store


def test_build_training_data_returns_none_on_small_df(trainer):
    small_df = make_ohlcv(n=50)  # < 200 rows
    result = trainer._build_training_data(
        "BTCUSDT", small_df, make_ohlcv(), make_ohlcv(), {}
    )
    assert result is None


def test_build_training_data_success(trainer):
    """Mock feature_eng and labeler to return controlled data."""
    n = 200
    feature_df = make_features_df(n)
    feature_matrix = pd.DataFrame(
        np.random.randn(n, 10),
        columns=[f"f{i}" for i in range(10)]
    )

    with patch.object(trainer.feature_eng, "calculate_features_v4", return_value=feature_df):
        with patch.object(trainer.feature_eng, "get_feature_vector_v4", return_value=feature_matrix):
            with patch.object(trainer.labeler, "label_for_ternary", return_value=feature_df):
                result = trainer._build_training_data(
                    "BTCUSDT", make_ohlcv(300), make_ohlcv(300), make_ohlcv(300), {}
                )

    assert result is not None
    X, y, feature_names, sample_weight = result
    assert X.shape[0] == len(y)
    assert len(feature_names) == 10
    assert len(sample_weight) == len(y)
    assert (sample_weight > 0).all()


def test_train_coin_saves_to_store(trainer, tmp_path):
    """Mock all heavy dependencies; check that store gets metrics saved."""
    n = 250  # > 200 so features_df size check passes
    feature_df = make_features_df(n)
    feature_matrix = pd.DataFrame(np.random.randn(n, 10), columns=[f"f{i}" for i in range(10)])
    mock_metrics = {
        "oos_accuracy": 0.62, "long_f1": 0.45, "short_f1": 0.38,
        "long_precision": 0.51, "short_precision": 0.44,
        "hold_f1": 0.71, "oos_log_loss": 0.9,
    }

    def fake_save(directory: str):
        """Simulate EnsembleV5.save() creating the metadata sentinel file."""
        import json as _json
        p = Path(directory)
        p.mkdir(parents=True, exist_ok=True)
        with open(p / "v5_ensemble_metadata.json", "w") as fh:
            _json.dump({"version": "v5"}, fh)

    with patch.object(trainer, "_fetch_ohlcv", return_value=make_ohlcv(300)):
        with patch.object(trainer, "_fetch_external_data_sync", return_value={}):
            with patch.object(trainer.feature_eng, "calculate_features_v4", return_value=feature_df):
                with patch.object(trainer.feature_eng, "get_feature_vector_v4", return_value=feature_matrix):
                    with patch.object(trainer.labeler, "label_for_ternary", return_value=feature_df):
                        with patch("src.models.auto_trainer_v5.EnsembleV5") as MockEnsemble:
                            mock_model = MockEnsemble.return_value
                            mock_model.train.return_value = mock_metrics
                            mock_model.save.side_effect = fake_save

                            result = trainer.train_coin("BTCUSDT")

    assert result is not None
    assert result["oos_accuracy"] == pytest.approx(0.62)
    assert trainer.store.has_model("BTCUSDT")
    assert "BTCUSDT" in trainer.store.list_trained_coins()


def test_train_coin_returns_none_on_insufficient_data(trainer):
    with patch.object(trainer, "_fetch_ohlcv", return_value=make_ohlcv(50)):  # Too small
        with patch.object(trainer, "_fetch_external_data_sync", return_value={}):
            result = trainer.train_coin("SMALLCOIN")
    assert result is None


def test_is_training_flag(trainer):
    assert not trainer.is_training


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
