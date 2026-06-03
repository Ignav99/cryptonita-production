"""Tests for TripleBarrierLabeler.label_for_ternary()"""
import numpy as np
import pandas as pd
import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.labeling import TripleBarrierLabeler


def make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Create synthetic OHLCV data."""
    rng = np.random.RandomState(seed)
    close = 100 * np.cumprod(1 + rng.normal(0, 0.02, n))
    high = close * (1 + abs(rng.normal(0, 0.01, n)))
    low = close * (1 - abs(rng.normal(0, 0.01, n)))
    open_ = close * (1 + rng.normal(0, 0.005, n))
    volume = rng.uniform(1e6, 1e7, n)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low,
        "close": close, "volume": volume
    })


def test_label_for_ternary_has_target_column():
    labeler = TripleBarrierLabeler()
    df = make_ohlcv(200)
    result = labeler.label_for_ternary(df)
    assert "target" in result.columns


def test_label_for_ternary_only_valid_classes():
    labeler = TripleBarrierLabeler()
    df = make_ohlcv(200)
    result = labeler.label_for_ternary(df)
    valid_targets = result["target"].dropna()
    assert set(valid_targets.unique()).issubset({0, 1, 2}), (
        f"Unexpected classes: {valid_targets.unique()}"
    )


def test_label_for_ternary_sl_maps_to_2():
    """When SL hits (label=-1), target must be 2 (SHORT), not 0."""
    labeler = TripleBarrierLabeler()
    df = make_ohlcv(300)
    result = labeler.label_for_ternary(df)
    sl_rows = result[result["label"] == -1]
    if len(sl_rows) > 0:
        assert (sl_rows["target"] == 2).all(), (
            "SL rows (label=-1) must have target=2 (SHORT)"
        )


def test_label_for_ternary_tp_maps_to_1():
    """When TP hits (label=+1), target must be 1 (LONG)."""
    labeler = TripleBarrierLabeler()
    df = make_ohlcv(300)
    result = labeler.label_for_ternary(df)
    tp_rows = result[result["label"] == 1]
    if len(tp_rows) > 0:
        assert (tp_rows["target"] == 1).all(), (
            "TP rows (label=+1) must have target=1 (LONG)"
        )


def test_label_for_ternary_time_maps_to_0():
    """When time barrier (label=0), target must be 0 (HOLD)."""
    labeler = TripleBarrierLabeler()
    df = make_ohlcv(300)
    result = labeler.label_for_ternary(df)
    time_rows = result[result["label"] == 0]
    if len(time_rows) > 0:
        assert (time_rows["target"] == 0).all(), (
            "Time rows (label=0) must have target=0 (HOLD)"
        )


def test_get_class_weights_returns_dict():
    labeler = TripleBarrierLabeler()
    df = make_ohlcv(300)
    df = labeler.label_for_ternary(df)
    weights = labeler.get_class_weights(df)
    assert isinstance(weights, dict)
    assert set(weights.keys()) == {0, 1, 2}
    assert all(w > 0 for w in weights.values())


def test_get_class_weights_rare_classes_get_higher_weight():
    """Rarer classes should get higher weight (inverse frequency)."""
    labeler = TripleBarrierLabeler()
    df = make_ohlcv(500)
    df = labeler.label_for_ternary(df)
    weights = labeler.get_class_weights(df)
    counts = df["target"].value_counts()
    # The class with fewer samples should have higher weight
    if counts.get(1, 0) < counts.get(0, 0):
        assert weights[1] > weights[0], "LONG (fewer samples) should have higher weight than HOLD"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
