"""
Tests for MarketRegimeDetector.
"""

import pytest
import pandas as pd
import numpy as np
from src.market_regime import MarketRegimeDetector


@pytest.fixture
def detector():
    """Create a MarketRegimeDetector instance."""
    return MarketRegimeDetector(ema_period=20, slope_threshold=0.0005)


@pytest.fixture
def bullish_klines():
    """
    Generate synthetic bullish klines (strong uptrend).
    100 candles with significantly increasing close prices.
    """
    np.random.seed(42)
    # Strong linear uptrend: 100 -> 120
    closes = np.linspace(100, 120, 100) + np.random.normal(0, 0.3, 100)
    closes = np.maximum(closes, 1.0)  # Ensure positive prices
    
    data = {
        'open': closes + np.random.uniform(-0.5, 0.5, 100),
        'high': closes + np.random.uniform(0, 1.0, 100),
        'low': closes - np.random.uniform(0, 1.0, 100),
        'close': closes,
        'volume': np.random.randint(1000, 10000, 100),
    }
    return pd.DataFrame(data)


@pytest.fixture
def bearish_klines():
    """
    Generate synthetic bearish klines (strong downtrend).
    100 candles with significantly decreasing close prices.
    """
    np.random.seed(42)
    # Strong linear downtrend: 120 -> 100
    closes = np.linspace(120, 100, 100) + np.random.normal(0, 0.3, 100)
    closes = np.maximum(closes, 1.0)  # Ensure positive prices
    
    data = {
        'open': closes + np.random.uniform(-0.5, 0.5, 100),
        'high': closes + np.random.uniform(0, 1.0, 100),
        'low': closes - np.random.uniform(0, 1.0, 100),
        'close': closes,
        'volume': np.random.randint(1000, 10000, 100),
    }
    return pd.DataFrame(data)


@pytest.fixture
def neutral_klines():
    """
    Generate synthetic neutral klines (sideways).
    100 candles with flat close prices.
    """
    np.random.seed(42)
    closes = np.ones(100) * 110 + np.random.normal(0, 0.2, 100)
    closes = np.maximum(closes, 1.0)  # Ensure positive prices
    
    data = {
        'open': closes + np.random.uniform(-0.5, 0.5, 100),
        'high': closes + np.random.uniform(0, 1.0, 100),
        'low': closes - np.random.uniform(0, 1.0, 100),
        'close': closes,
        'volume': np.random.randint(1000, 10000, 100),
    }
    return pd.DataFrame(data)


def test_bullish_regime_detection(detector, bullish_klines):
    """
    Test that bullish uptrend is correctly detected.
    """
    regime = detector.detect(bullish_klines)
    assert regime == 'BULLISH', f"Expected BULLISH regime for uptrend, got {regime}"


def test_bearish_regime_detection(detector, bearish_klines):
    """
    Test that bearish downtrend is correctly detected.
    """
    regime = detector.detect(bearish_klines)
    assert regime == 'BEARISH', f"Expected BEARISH regime for downtrend, got {regime}"


def test_neutral_regime_detection(detector, neutral_klines):
    """
    Test that neutral sideways market is correctly detected.
    """
    regime = detector.detect(neutral_klines)
    assert regime == 'NEUTRAL', f"Expected NEUTRAL regime for sideways market, got {regime}"


def test_short_block_in_bullish(detector, bullish_klines):
    """
    Test that SHORTs are blocked in bullish regime.
    """
    regime = detector.detect(bullish_klines)
    assert regime == 'BULLISH'
    assert detector.allow_short(regime) is False, "SHORTs should be blocked in BULLISH regime"


def test_short_allowed_in_bearish(detector, bearish_klines):
    """
    Test that SHORTs are allowed in bearish regime.
    """
    regime = detector.detect(bearish_klines)
    assert regime == 'BEARISH'
    assert detector.allow_short(regime) is True, "SHORTs should be allowed in BEARISH regime"


def test_short_allowed_in_neutral(detector, neutral_klines):
    """
    Test that SHORTs are allowed in neutral regime.
    """
    regime = detector.detect(neutral_klines)
    assert regime == 'NEUTRAL'
    assert detector.allow_short(regime) is True, "SHORTs should be allowed in NEUTRAL regime"


def test_long_block_in_bearish(detector, bearish_klines):
    """
    Test that LONGs are blocked in bearish regime.
    """
    regime = detector.detect(bearish_klines)
    assert regime == 'BEARISH'
    assert detector.allow_long(regime) is False, "LONGs should be blocked in BEARISH regime"


def test_long_allowed_in_bullish(detector, bullish_klines):
    """
    Test that LONGs are allowed in bullish regime.
    """
    regime = detector.detect(bullish_klines)
    assert regime == 'BULLISH'
    assert detector.allow_long(regime) is True, "LONGs should be allowed in BULLISH regime"


def test_long_allowed_in_neutral(detector, neutral_klines):
    """
    Test that LONGs are allowed in neutral regime.
    """
    regime = detector.detect(neutral_klines)
    assert regime == 'NEUTRAL'
    assert detector.allow_long(regime) is True, "LONGs should be allowed in NEUTRAL regime"


def test_insufficient_data(detector):
    """
    Test that insufficient data defaults to NEUTRAL.
    """
    minimal_data = pd.DataFrame({
        'close': [100, 101, 102]
    })
    regime = detector.detect(minimal_data)
    assert regime == 'NEUTRAL', "Insufficient data should default to NEUTRAL"


def test_ema_slope_calculation(detector, bullish_klines):
    """
    Test EMA slope calculation logic.
    Bullish klines should have positive slope.
    """
    ema = bullish_klines['close'].ewm(span=detector.ema_period, adjust=False).mean()
    slope = (ema.iloc[-1] - ema.iloc[-2]) / ema.iloc[-2]
    
    # Uptrend should have positive slope > threshold
    assert slope > detector.slope_threshold, f"Bullish uptrend should have slope > {detector.slope_threshold}, got {slope}"


def test_detector_customization():
    """
    Test custom detector parameters.
    """
    custom_detector = MarketRegimeDetector(ema_period=10, slope_threshold=0.001)
    assert custom_detector.ema_period == 10
    assert custom_detector.slope_threshold == 0.001
