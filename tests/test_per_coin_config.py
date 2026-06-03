"""Tests for per-coin LONG and SHORT threshold configuration."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from src.config.per_coin_config import (
    LONG_DISABLED_COINS,
    LONG_OPTIMIZED_COINS,
    get_long_threshold,
    SHORT_DISABLED_COINS,
    SHORT_OPTIMIZED_COINS,
    get_short_threshold,
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


def test_aaveusdt_disabled_after_pass2():
    # Pass 2 backtest confirmed 30.4% LONG WR — no improvement from lower threshold.
    # Moved from LONG_OPTIMIZED_COINS to LONG_DISABLED_COINS.
    assert "AAVEUSDT" in LONG_DISABLED_COINS
    assert "AAVEUSDT" not in LONG_OPTIMIZED_COINS
    assert get_long_threshold("AAVEUSDT") == pytest.approx(1.0)


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


def test_get_long_threshold_aave_now_disabled():
    # Pass 2: AAVE moved to disabled — threshold must be 1.0
    assert get_long_threshold("AAVEUSDT") == pytest.approx(1.0)


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


# ===========================================================================
# SHORT threshold — per_coin_config constants
# ===========================================================================

def test_short_disabled_coins_use_usdt_suffix():
    for coin in SHORT_DISABLED_COINS:
        assert coin.endswith("USDT"), f"{coin} must end with USDT"


def test_stxusdt_is_short_disabled():
    assert "STXUSDT" in SHORT_DISABLED_COINS


def test_suiusdt_is_short_disabled():
    assert "SUIUSDT" in SHORT_DISABLED_COINS


def test_uniusdt_is_short_disabled():
    assert "UNIUSDT" in SHORT_DISABLED_COINS


def test_filusdt_is_short_disabled():
    assert "FILUSDT" in SHORT_DISABLED_COINS


def test_short_optimized_coins_use_usdt_suffix():
    for coin in SHORT_OPTIMIZED_COINS:
        assert coin.endswith("USDT"), f"{coin} must end with USDT"


def test_atomusdt_is_short_optimized():
    assert "ATOMUSDT" in SHORT_OPTIMIZED_COINS
    assert SHORT_OPTIMIZED_COINS["ATOMUSDT"] == pytest.approx(0.30)


def test_opusdt_is_short_optimized():
    assert "OPUSDT" in SHORT_OPTIMIZED_COINS
    assert SHORT_OPTIMIZED_COINS["OPUSDT"] == pytest.approx(0.30)


def test_short_disabled_and_optimized_are_disjoint():
    overlap = SHORT_DISABLED_COINS & set(SHORT_OPTIMIZED_COINS.keys())
    assert overlap == set(), f"Coins in both sets: {overlap}"


# ===========================================================================
# get_short_threshold
# ===========================================================================

DEFAULT_SHORT = 0.35


def test_get_short_threshold_disabled_returns_one():
    """Disabled SHORT coins → threshold=1.0 (impossible → always HOLD)."""
    assert get_short_threshold("STXUSDT") == pytest.approx(1.0)
    assert get_short_threshold("SUIUSDT") == pytest.approx(1.0)
    assert get_short_threshold("UNIUSDT") == pytest.approx(1.0)
    assert get_short_threshold("FILUSDT") == pytest.approx(1.0)


def test_get_short_threshold_optimized_atom():
    assert get_short_threshold("ATOMUSDT") == pytest.approx(0.30)


def test_get_short_threshold_optimized_op():
    assert get_short_threshold("OPUSDT") == pytest.approx(0.30)


def test_get_short_threshold_default_for_unlisted():
    assert get_short_threshold("SOLUSDT") == pytest.approx(DEFAULT_SHORT)
    assert get_short_threshold("ADAUSDT") == pytest.approx(DEFAULT_SHORT)


def test_get_short_threshold_unknown_coin_gets_default():
    assert get_short_threshold("XYZUSDT") == pytest.approx(DEFAULT_SHORT)


# ===========================================================================
# Integration: predictor applies per-coin SHORT config
# ===========================================================================

from src.models.predictor_v5 import SIGNAL_SHORT


def test_stxusdt_never_emits_short_even_with_high_p_short():
    """STXUSDT has disabled SHORT — p_short=0.95 must produce HOLD."""
    predictor = _make_predictor([0.02, 0.03, 0.95])  # very high p_short
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("STXUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD, (
        f"STXUSDT must never emit SHORT, got {signal_class}"
    )


def test_suiusdt_never_emits_short():
    predictor = _make_predictor([0.02, 0.03, 0.95])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("SUIUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD


def test_atomusdt_emits_short_above_0_30_threshold():
    """ATOMUSDT threshold=0.30 — p_short=0.32 with no uptrend must emit SHORT."""
    predictor = _make_predictor([0.40, 0.28, 0.32])
    # Use a downtrending OHLCV so _passes_trend_filter_short passes
    rng = np.random.RandomState(7)
    close = 100 * np.cumprod(1 + rng.normal(-0.002, 0.01, 250))  # slight downtrend
    ohlcv = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": rng.uniform(1e6, 1e7, 250),
    })

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("ATOMUSDT", ohlcv)

    assert signal_class == SIGNAL_SHORT


def test_solusdt_holds_on_short_below_default():
    """SOLUSDT uses default 0.35 — p_short=0.30 must produce HOLD."""
    predictor = _make_predictor([0.50, 0.20, 0.30])
    ohlcv = _make_ohlcv()

    with patch.object(
        predictor.feature_engineer,
        "calculate_single_prediction_features_v4",
        return_value=np.ones(10),
    ):
        signal_class, _, _ = predictor.predict_single("SOLUSDT", ohlcv)

    assert signal_class == SIGNAL_HOLD
