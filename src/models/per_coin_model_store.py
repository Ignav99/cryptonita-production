"""
PER-COIN MODEL STORE (V5)
=========================
Filesystem-based storage for per-ticker EnsembleV5 models.

Structure:
  {base_dir}/{ticker}/v5_ensemble_metadata.json  — model artifacts
  {base_dir}/{ticker}/v5_training_metrics.json   — metrics history
  {base_dir}/_registry.json                      — global coin index

No database required — purely filesystem-based.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger


# Default base directory
DEFAULT_V5_MODEL_DIR = "PRODUCTION_SYSTEM/models/v5"

# Metrics JSON filename (alongside model artifacts)
METRICS_FILENAME = "v5_training_metrics.json"
REGISTRY_FILENAME = "_registry.json"


class PerCoinModelStore:
    """
    Filesystem-based store for per-coin EnsembleV5 models.

    Each coin has its own subdirectory. A registry JSON tracks
    all trained coins and their latest metrics for easy comparison.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir or DEFAULT_V5_MODEL_DIR)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"[PerCoinModelStore] Base dir: {self.base_dir.resolve()}")

    # ============================================================
    # PATHS
    # ============================================================

    def get_coin_dir(self, ticker: str) -> Path:
        """Return the directory for a specific ticker."""
        return self.base_dir / ticker

    def get_global_dir(self) -> Path:
        """Return the global (fallback) model directory."""
        return self.base_dir / "global"

    def get_metrics_path(self, ticker: str) -> Path:
        return self.get_coin_dir(ticker) / METRICS_FILENAME

    def get_registry_path(self) -> Path:
        return self.base_dir / REGISTRY_FILENAME

    # ============================================================
    # COIN MODEL
    # ============================================================

    def has_model(self, ticker: str) -> bool:
        """Check if a trained model exists for this ticker."""
        return (self.get_coin_dir(ticker) / "v5_ensemble_metadata.json").exists()

    def has_global_model(self) -> bool:
        """Check if the global fallback model exists."""
        return (self.get_global_dir() / "v5_ensemble_metadata.json").exists()

    def get_model_path(self, ticker: str) -> str:
        """Return the directory path for a ticker's model (use with EnsembleV5.load())."""
        return str(self.get_coin_dir(ticker))

    def get_global_model_path(self) -> str:
        """Return the global model directory path."""
        return str(self.get_global_dir())

    def save_metrics(self, ticker: str, metrics: Dict) -> None:
        """
        Append a training run's metrics to the coin's metrics history.
        Keeps last 20 runs.

        Args:
            ticker: Coin symbol
            metrics: Dict with keys like oos_accuracy, long_f1, short_f1, etc.
        """
        coin_dir = self.get_coin_dir(ticker)
        coin_dir.mkdir(parents=True, exist_ok=True)
        metrics_path = self.get_metrics_path(ticker)

        # Load existing history
        history = []
        if metrics_path.exists():
            try:
                with open(metrics_path) as f:
                    history = json.load(f)
            except (json.JSONDecodeError, OSError):
                history = []

        # Append new run with timestamp
        run = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ticker": ticker,
            **metrics,
        }
        history.append(run)

        # Keep last 20 runs
        history = history[-20:]

        with open(metrics_path, "w") as f:
            json.dump(history, f, indent=2, default=str)

        logger.info(
            f"[PerCoinModelStore] Saved metrics for {ticker}: "
            f"oos_acc={metrics.get('oos_accuracy', 'N/A'):.4f} "
            f"long_f1={metrics.get('long_f1', 'N/A'):.4f} "
            f"short_f1={metrics.get('short_f1', 'N/A'):.4f}"
        )

    def get_metrics_history(self, ticker: str) -> List[Dict]:
        """Get all training run metrics for a ticker (latest first)."""
        metrics_path = self.get_metrics_path(ticker)
        if not metrics_path.exists():
            return []
        try:
            with open(metrics_path) as f:
                history = json.load(f)
            return list(reversed(history))  # Latest first
        except (json.JSONDecodeError, OSError):
            return []

    def get_latest_metrics(self, ticker: str) -> Optional[Dict]:
        """Get the most recent training metrics for a ticker."""
        history = self.get_metrics_history(ticker)
        return history[0] if history else None

    # ============================================================
    # REGISTRY
    # ============================================================

    def _load_registry(self) -> Dict:
        """Load the registry JSON. Returns empty dict if not found."""
        registry_path = self.get_registry_path()
        if not registry_path.exists():
            return {}
        try:
            with open(registry_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return {}

    def _save_registry(self, registry: Dict) -> None:
        """Save the registry JSON."""
        with open(self.get_registry_path(), "w") as f:
            json.dump(registry, f, indent=2, default=str)

    def register_coin(self, ticker: str, metrics: Dict) -> None:
        """
        Register or update a coin in the global registry.
        Called after successful training.
        """
        registry = self._load_registry()
        registry[ticker] = {
            "last_trained": datetime.now(timezone.utc).isoformat(),
            "oos_accuracy": metrics.get("oos_accuracy"),
            "long_f1": metrics.get("long_f1"),
            "short_f1": metrics.get("short_f1"),
            "long_precision": metrics.get("long_precision"),
            "short_precision": metrics.get("short_precision"),
            "model_dir": str(self.get_coin_dir(ticker)),
        }
        self._save_registry(registry)
        logger.info(f"[PerCoinModelStore] Registered {ticker} in global registry")

    def list_trained_coins(self) -> List[str]:
        """Return list of tickers with trained models, sorted alphabetically."""
        registry = self._load_registry()
        return sorted(registry.keys())

    def get_registry(self) -> Dict[str, Dict]:
        """Return the full registry (all coins + their latest metrics)."""
        return self._load_registry()

    def get_training_summary(self) -> Dict:
        """
        Get a summary of all trained coins with key metrics.

        Returns:
            Dict with:
              n_trained: number of coins with models
              avg_long_f1: average LONG F1 across all coins
              avg_short_f1: average SHORT F1 across all coins
              best_long: ticker with highest LONG F1
              best_short: ticker with highest SHORT F1
              coins: list of {ticker, oos_accuracy, long_f1, short_f1}
        """
        registry = self._load_registry()
        if not registry:
            return {
                "n_trained": 0,
                "avg_long_f1": 0.0,
                "avg_short_f1": 0.0,
                "best_long": None,
                "best_short": None,
                "coins": [],
            }

        coins = []
        long_f1s = []
        short_f1s = []

        for ticker, data in registry.items():
            long_f1 = data.get("long_f1") or 0.0
            short_f1 = data.get("short_f1") or 0.0
            coins.append({
                "ticker": ticker,
                "oos_accuracy": data.get("oos_accuracy"),
                "long_f1": long_f1,
                "short_f1": short_f1,
                "last_trained": data.get("last_trained"),
            })
            long_f1s.append(long_f1)
            short_f1s.append(short_f1)

        coins.sort(key=lambda x: (x["long_f1"] or 0) + (x["short_f1"] or 0), reverse=True)
        best_long = max(registry.items(), key=lambda kv: kv[1].get("long_f1") or 0)[0]
        best_short = max(registry.items(), key=lambda kv: kv[1].get("short_f1") or 0)[0]

        return {
            "n_trained": len(coins),
            "avg_long_f1": float(sum(long_f1s) / len(long_f1s)) if long_f1s else 0.0,
            "avg_short_f1": float(sum(short_f1s) / len(short_f1s)) if short_f1s else 0.0,
            "best_long": best_long,
            "best_short": best_short,
            "coins": coins,
        }

    def compare_runs(self, ticker: str) -> Optional[Dict]:
        """
        Compare the last two training runs for a ticker.

        Returns:
            Dict with delta metrics (positive = improvement), or None if < 2 runs.
        """
        history = self.get_metrics_history(ticker)
        if len(history) < 2:
            return None

        latest = history[0]
        previous = history[1]

        delta = {}
        for key in ["oos_accuracy", "long_f1", "short_f1", "long_precision", "short_precision"]:
            v_latest = latest.get(key)
            v_prev = previous.get(key)
            if v_latest is not None and v_prev is not None:
                delta[f"delta_{key}"] = round(float(v_latest) - float(v_prev), 6)
                delta[f"improved_{key}"] = delta[f"delta_{key}"] > 0

        return {
            "ticker": ticker,
            "latest": {k: v for k, v in latest.items() if k not in ("ticker",)},
            "previous": {k: v for k, v in previous.items() if k not in ("ticker",)},
            "delta": delta,
        }

    def delete_coin_model(self, ticker: str) -> bool:
        """
        Remove a coin's model directory and unregister it.
        Use with caution — irreversible.
        """
        import shutil
        coin_dir = self.get_coin_dir(ticker)
        if not coin_dir.exists():
            logger.warning(f"[PerCoinModelStore] {ticker} not found — nothing to delete")
            return False

        shutil.rmtree(coin_dir)

        # Remove from registry
        registry = self._load_registry()
        if ticker in registry:
            del registry[ticker]
            self._save_registry(registry)

        logger.info(f"[PerCoinModelStore] Deleted model for {ticker}")
        return True
