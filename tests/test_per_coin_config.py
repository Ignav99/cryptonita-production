"""Tests for per-coin LONG threshold configuration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.config.per_coin_config import (
    LONG_DISABLED_COINS,
    LONG_OPTIMIZED_COINS,
    get_long_threshold,
)


# ---------------------------------------------------------------------------
# LONG_DISABLED_COINS
# ---------------------------------------------------------------------------

def test_stxusdt_is_disabled():
    assert "STXUSDT" in LONG_DISABLED_COINS


def test_filusdt_is_disabled():
    assert "FILUSDT" in LONG_DISABLED_COINS


def test_adausdt_is_disabled():
    assert "ADAUSDT" in LONG_DISABLED_COINS


def test_runeusdt_is_disabled():
    assert "RUNEUSDT" in LONG_DISABLED_COINS


def test_disabled_coins_use_usdt_suffix():
    for coin in LONG_DISABLED_COINS:
        assert coin.endswith("USDT"), f"{coin} must end with USDT"


# ---------------------------------------------------------------------------
# LONG_OPTIMIZED_COINS
# ---------------------------------------------------------------------------

def test_arbusdt_optimized_threshold():
    assert "ARBUSDT" in LONG_OPTIMIZED_COINS
    assert LONG_OPTIMIZED_COINS["ARBUSDT"] == pytest.approx(0.40)


def test_aaveusdt_optimized_threshold():
    assert "AAVEUSDT" in LONG_OPTIMIZED_COINS
    assert LONG_OPTIMIZED_COINS["AAVEUSDT"] == pytest.approx(0.45)


def test_optimized_coins_use_usdt_suffix():
    for coin in LONG_OPTIMIZED_COINS:
        assert coin.endswith("USDT"), f"{coin} must end with USDT"


def test_disabled_and_optimized_are_disjoint():
    overlap = LONG_DISABLED_COINS & set(LONG_OPTIMIZED_COINS.keys())
    assert overlap == set(), f"Coins in both sets: {overlap}"


# ---------------------------------------------------------------------------
# get_long_threshold
# ---------------------------------------------------------------------------

DEFAULT_STRICT = 0.65  # the stricter default for unlisted coins


def test_get_long_threshold_disabled_returns_one():
    """Disabled coin → threshold=1.0 (impossible to meet → always HOLD)."""
    assert get_long_threshold("STXUSDT") == pytest.approx(1.0)
    assert get_long_threshold("FILUSDT") == pytest.approx(1.0)
    assert get_long_threshold("ADAUSDT") == pytest.approx(1.0)


def test_get_long_threshold_optimized_arb():
    assert get_long_threshold("ARBUSDT") == pytest.approx(0.40)


def test_get_long_threshold_optimized_aave():
    assert get_long_threshold("AAVEUSDT") == pytest.approx(0.45)


def test_get_long_threshold_default_for_unlisted():
    """Coins not in either set get the strict default."""
    assert get_long_threshold("SOLUSDT") == pytest.approx(DEFAULT_STRICT)
    assert get_long_threshold("DOTUSDT") == pytest.approx(DEFAULT_STRICT)


def test_get_long_threshold_unknown_coin_gets_default():
    assert get_long_threshold("XYZUSDT") == pytest.approx(DEFAULT_STRICT)


# ---------------------------------------------------------------------------
# Integration: TradingPredictorV5 applies per-coin config
# ---------------------------------------------------------------------------

import numpy as np
import pandas as pd
from unittest.mock import MagicMock, patch
from src.models.predictor_v5 import TradingPredictorV5, SIGNAL_HOLD, SIGNAL_LONG


def _make_ohlcv(n=250, seed=42):
    rng = np.random.RandomState(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.01, n))
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.01,
        "low":  close * 0.99,
        "close": close,
        "volume": rng.uniform(1e6, 1e7, n),
    })


def _make_predictor(proba):
    """Return a predictor whose mock model always emits `proba`."""
    mock_model = MagicMock()
    mock_model.feature_names = [f"f{i}" for i in range(10)]
    mock_model.predict_proba.return_value = np.array([proba])

    with patch.object(TradingPredictorV5, "_load_global_model"):
        with patch.object(TradingPredictorV5, "_fetch_external_data_sync", return_value={}):
            predictor = TradingPredictorV5()
            predictor._global_model = mock_model
            predictor._cached_external = {}
    return predictor


def test_stxusdt_never_emits_long_even_with_high_p_long():
    """STXUSDT is disabled — even p_long=0.95 must produce HOLD."""
    predictor = _make_predictor([0.02, 0.95, 0.03])  # very high p_long
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, proba_3, _ = predictor.predict_single("STXUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD, (
        f"STXUSDT must never emit LONG, got {signal_class}"
    )


def test_filusdt_never_emits_long():
    predictor = _make_predictor([0.02, 0.95, 0.03])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("FILUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD


def test_arbusdt_emits_long_above_0_40_threshold():
    """ARBUSDT threshold=0.40 — p_long=0.42 must emit LONG (above 0.40)."""
    predictor = _make_predictor([0.30, 0.42, 0.28])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("ARBUSDT", ohlcv)

    assert signal_class == SIGNAL_LONG


def test_solusdt_holds_below_strict_default():
    """SOLUSDT uses default 0.65 — p_long=0.50 must produce HOLD."""
    predictor = _make_predictor([0.20, 0.50, 0.30])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("SOLUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD


def test_solusdt_emits_long_above_strict_default():
    """SOLUSDT uses default 0.65 — p_long=0.70 must produce LONG."""
    predictor = _make_predictor([0.10, 0.70, 0.20])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("SOLUSDT", ohlcv)

    assert signal_class == SIGNAL_LONG
