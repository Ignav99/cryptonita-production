"""Tests for PerCoinModelStore."""
import json
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.per_coin_model_store import PerCoinModelStore


@pytest.fixture
def store(tmp_path):
    """PerCoinModelStore with a temp directory."""
    return PerCoinModelStore(base_dir=str(tmp_path / "models_v5"))


SAMPLE_METRICS = {
    "oos_accuracy": 0.62,
    "long_f1": 0.45,
    "short_f1": 0.38,
    "long_precision": 0.51,
    "short_precision": 0.44,
    "oos_log_loss": 0.9,
}


def test_has_model_false_when_no_model(store, tmp_path):
    assert not store.has_model("BTCUSDT")


def test_has_global_model_false_initially(store):
    assert not store.has_global_model()


def test_save_metrics_creates_file(store):
    store.save_metrics("BTCUSDT", SAMPLE_METRICS)
    assert store.get_metrics_path("BTCUSDT").exists()


def test_get_metrics_history_returns_entries(store):
    store.save_metrics("ETHUSDT", SAMPLE_METRICS)
    store.save_metrics("ETHUSDT", {**SAMPLE_METRICS, "oos_accuracy": 0.65})
    history = store.get_metrics_history("ETHUSDT")
    assert len(history) == 2
    # Latest first
    assert history[0]["oos_accuracy"] == 0.65


def test_get_latest_metrics(store):
    store.save_metrics("SOLUSDT", SAMPLE_METRICS)
    latest = store.get_latest_metrics("SOLUSDT")
    assert latest is not None
    assert latest["oos_accuracy"] == pytest.approx(0.62)


def test_get_latest_metrics_returns_none_when_no_history(store):
    assert store.get_latest_metrics("XRPUSDT") is None


def test_register_and_list_coins(store):
    store.register_coin("BTCUSDT", SAMPLE_METRICS)
    store.register_coin("ETHUSDT", {**SAMPLE_METRICS, "long_f1": 0.55})
    coins = store.list_trained_coins()
    assert "BTCUSDT" in coins
    assert "ETHUSDT" in coins
    assert coins == sorted(coins)  # Must be sorted


def test_get_training_summary_empty(store):
    summary = store.get_training_summary()
    assert summary["n_trained"] == 0
    assert summary["avg_long_f1"] == 0.0


def test_get_training_summary_with_coins(store):
    store.register_coin("BTCUSDT", SAMPLE_METRICS)
    store.register_coin("ETHUSDT", {**SAMPLE_METRICS, "long_f1": 0.55})
    summary = store.get_training_summary()
    assert summary["n_trained"] == 2
    assert summary["best_long"] == "ETHUSDT"  # 0.55 > 0.45
    assert 0.0 < summary["avg_long_f1"] < 1.0


def test_compare_runs_returns_none_when_single_run(store):
    store.save_metrics("BTCUSDT", SAMPLE_METRICS)
    result = store.compare_runs("BTCUSDT")
    assert result is None


def test_compare_runs_detects_improvement(store):
    store.save_metrics("BTCUSDT", SAMPLE_METRICS)  # Previous
    store.save_metrics("BTCUSDT", {**SAMPLE_METRICS, "long_f1": 0.60})  # Latest (improved)
    result = store.compare_runs("BTCUSDT")
    assert result is not None
    assert result["delta"]["delta_long_f1"] == pytest.approx(0.60 - 0.45, abs=1e-4)
    assert result["delta"]["improved_long_f1"] is True


def test_metrics_history_capped_at_20(store):
    for i in range(25):
        store.save_metrics("ADAUSDT", {**SAMPLE_METRICS, "oos_accuracy": 0.5 + i * 0.01})
    history = store.get_metrics_history("ADAUSDT")
    assert len(history) <= 20


def test_delete_coin_model(store):
    store.register_coin("BTCUSDT", SAMPLE_METRICS)
    store.save_metrics("BTCUSDT", SAMPLE_METRICS)

    result = store.delete_coin_model("BTCUSDT")
    assert result is True
    assert "BTCUSDT" not in store.list_trained_coins()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
