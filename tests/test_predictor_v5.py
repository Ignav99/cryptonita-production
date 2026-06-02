"""Tests for TradingPredictorV5 — mocked dependencies."""
import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.predictor_v5 import (
    TradingPredictorV5,
    SIGNAL_HOLD, SIGNAL_LONG, SIGNAL_SHORT, SIGNAL_NAMES,
)


def make_ohlcv(n=250, seed=42):
    rng = np.random.RandomState(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": rng.uniform(1e6, 1e7, n),
    })


def make_predictor_with_mock_model():
    """Create predictor with a mocked ensemble that returns fixed probas."""
    mock_model = MagicMock()
    mock_model.feature_names = None
    # P(HOLD)=0.2, P(LONG)=0.6, P(SHORT)=0.2 → LONG signal
    mock_model.predict_proba.return_value = np.array([[0.2, 0.6, 0.2]])

    with patch.object(TradingPredictorV5, "_load_global_model"):
        with patch.object(TradingPredictorV5, "_fetch_external_data_sync", return_value={}):
            predictor = TradingPredictorV5()
            predictor._global_model = mock_model
            predictor._cached_external = {}

    return predictor, mock_model


def test_signal_constants():
    assert SIGNAL_HOLD == 0
    assert SIGNAL_LONG == 1
    assert SIGNAL_SHORT == 2
    assert SIGNAL_NAMES[SIGNAL_LONG] == "LONG"
    assert SIGNAL_NAMES[SIGNAL_SHORT] == "SHORT"


def test_predict_single_returns_long_when_p_long_high():
    predictor, mock_model = make_predictor_with_mock_model()
    # p_long=0.70 > DEFAULT_LONG_THRESHOLD_STRICT (0.65) — must emit LONG.
    # BTCUSDT is not in TICKERS so it gets the strict default threshold.
    mock_model.predict_proba.return_value = np.array([[0.10, 0.70, 0.20]])
    ohlcv = make_ohlcv(250)

    with patch.object(predictor.feature_engineer, "calculate_single_prediction_features_v4") as mock_feat:
        mock_feat.return_value = np.ones(10)
        mock_model.feature_names = [f"f{i}" for i in range(10)]

        signal_class, proba_3, features = predictor.predict_single("BTCUSDT", ohlcv)

    assert signal_class == SIGNAL_LONG
    assert proba_3.shape == (3,)
    assert abs(proba_3.sum() - 1.0) < 1e-5


def test_predict_single_returns_short_when_p_short_high():
    predictor, mock_model = make_predictor_with_mock_model()
    # Override to return SHORT proba
    mock_model.predict_proba.return_value = np.array([[0.2, 0.1, 0.7]])
    ohlcv = make_ohlcv(250)

    with patch.object(predictor.feature_engineer, "calculate_single_prediction_features_v4") as mock_feat:
        mock_feat.return_value = np.ones(10)
        mock_model.feature_names = [f"f{i}" for i in range(10)]

        signal_class, proba_3, features = predictor.predict_single("ETHUSDT", ohlcv)

    assert signal_class == SIGNAL_SHORT


def test_predict_single_returns_hold_when_below_threshold():
    predictor, mock_model = make_predictor_with_mock_model()
    mock_model.predict_proba.return_value = np.array([[0.7, 0.15, 0.15]])
    ohlcv = make_ohlcv(250)

    with patch.object(predictor.feature_engineer, "calculate_single_prediction_features_v4") as mock_feat:
        mock_feat.return_value = np.ones(10)
        mock_model.feature_names = [f"f{i}" for i in range(10)]

        signal_class, proba_3, features = predictor.predict_single("XRPUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD


def test_should_trade_rejects_hold():
    predictor, _ = make_predictor_with_mock_model()
    proba = np.array([0.8, 0.1, 0.1])
    ok, reason = predictor.should_trade("BTCUSDT", SIGNAL_HOLD, proba, 0, 0.0)
    assert not ok
    assert "HOLD" in reason


def test_should_trade_approves_long():
    predictor, _ = make_predictor_with_mock_model()
    proba = np.array([0.2, 0.6, 0.2])
    ok, reason = predictor.should_trade("BTCUSDT", SIGNAL_LONG, proba, 0, 0.0)
    assert ok


def test_should_trade_rejects_when_max_positions():
    predictor, _ = make_predictor_with_mock_model()
    proba = np.array([0.2, 0.6, 0.2])
    # Pass 100 current positions — well above any MAX_POSITIONS setting
    ok, reason = predictor.should_trade("BTCUSDT", SIGNAL_LONG, proba, 100, 0.0)
    assert not ok


def test_cooldown_tracking():
    predictor, _ = make_predictor_with_mock_model()
    assert not predictor._in_cooldown("BTCUSDT")
    predictor.register_trade_result("BTCUSDT", won=False)
    assert predictor._in_cooldown("BTCUSDT")
    predictor.register_trade_result("BTCUSDT", won=True)
    assert not predictor._in_cooldown("BTCUSDT")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
