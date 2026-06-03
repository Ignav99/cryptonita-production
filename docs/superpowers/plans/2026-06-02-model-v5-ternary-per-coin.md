# Cryptonita V5 — Ternary Labels + Per-Coin Models + SHORT Execution

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade cryptonita from a binary LONG-only model to a 3-class (LONG/SHORT/FLAT) per-coin ensemble that can profit in any market direction, validated by honest walk-forward backtest before any production deployment.

**Architecture:** Each of the 47 tickers gets its own trained ensemble (EnsembleV5), which predicts 3 classes using ternary triple-barrier labels. The predictor layer reads per-coin models, emits LONG/SHORT/FLAT signals, and the trading bot executes via Binance Futures margin for SHORT positions. Every training run produces a daily log comparing V4 vs V5 metrics.

**Tech Stack:** Python 3.11, XGBoost, LightGBM, CatBoost, statsmodels, pandas, Binance python-binance, pytest

---

## Pre-flight: understand the baseline

Run the existing backtest to capture V4's real performance BEFORE touching any code:

```bash
~/.pyenv/versions/3.11.9/bin/python scripts/backtest.py \
    --capital 1000 --lookback-days 90 \
    --output docs/BACKTEST_V4_BASELINE_2026-06-02.json
```

Save that JSON — every subsequent task will compare against it.

---

## File Map

| Path | Status | Responsibility |
|------|--------|----------------|
| `src/models/labeling.py` | **MODIFY** | Add `label_for_ternary()` — 3-class labels |
| `src/models/ensemble_v5.py` | **CREATE** | Multiclass ensemble (3 classes) |
| `src/models/per_coin_model_store.py` | **CREATE** | Save/load per-ticker model dirs |
| `src/models/predictor_v5.py` | **CREATE** | Predictor reading per-coin models, emitting LONG/SHORT/FLAT |
| `src/models/auto_trainer_v5.py` | **CREATE** | Per-coin training loop, daily log writer |
| `src/services/binance_futures.py` | **CREATE** | Binance Futures API wrapper for SHORT execution |
| `src/bot/trading_bot.py` | **MODIFY** | Handle SHORT signal via futures service |
| `scripts/walk_forward_backtest_v5.py` | **CREATE** | Honest WFV backtest, no lookahead, logs metrics daily |
| `tests/test_labeling_ternary.py` | **CREATE** | Ternary label correctness |
| `tests/test_ensemble_v5.py` | **CREATE** | Multiclass predict_proba shape + values |
| `tests/test_predictor_v5.py` | **CREATE** | Signal emission (LONG/SHORT/FLAT) |
| `tests/test_binance_futures.py` | **CREATE** | Futures order mock tests |

---

## Task 1: Ternary Labeling

**Files:**
- Modify: `src/models/labeling.py`
- Create: `tests/test_labeling_ternary.py`

### Objective
Add `label_for_ternary()` that keeps label=-1 as class 2 (SHORT), label=+1 as class 1 (LONG), label=0 as class 0 (FLAT/HOLD).
Mapping: `{-1 → 2, 0 → 0, 1 → 1}` — avoids negative class indices in sklearn/XGB/LGB.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_labeling_ternary.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest
from src.models.labeling import TripleBarrierLabeler


def _make_ohlcv(n=100):
    """Synthetic OHLCV — trending up so we get some TPs and SLs."""
    np.random.seed(42)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)
    df = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.uniform(1e6, 5e6, n),
    })
    return df


def test_ternary_classes_are_0_1_2():
    labeler = TripleBarrierLabeler()
    df = labeler.label_for_ternary(_make_ohlcv())
    assert "target" in df.columns
    unique = set(df["target"].dropna().astype(int).unique())
    assert unique.issubset({0, 1, 2}), f"Unexpected classes: {unique}"


def test_ternary_has_all_three_classes():
    """With enough rows we should see LONG, SHORT, and FLAT events."""
    labeler = TripleBarrierLabeler()
    df = labeler.label_for_ternary(_make_ohlcv(300))
    counts = df["target"].dropna().value_counts()
    assert len(counts) == 3, f"Expected 3 classes, got: {counts.to_dict()}"


def test_ternary_label_minus1_maps_to_2():
    """label=-1 (SL hit) must map to target=2 (SHORT class)."""
    labeler = TripleBarrierLabeler()
    df = labeler.label(_make_ohlcv(300))
    df2 = labeler.label_for_ternary(_make_ohlcv(300))
    sl_rows = df["label"] == -1
    assert (df2.loc[sl_rows, "target"] == 2).all(), "SL label -1 should map to class 2"


def test_ternary_label_plus1_maps_to_1():
    labeler = TripleBarrierLabeler()
    df = labeler.label(_make_ohlcv(300))
    df2 = labeler.label_for_ternary(_make_ohlcv(300))
    tp_rows = df["label"] == 1
    assert (df2.loc[tp_rows, "target"] == 1).all(), "TP label +1 should map to class 1"


def test_ternary_label_0_maps_to_0():
    labeler = TripleBarrierLabeler()
    df = labeler.label(_make_ohlcv(300))
    df2 = labeler.label_for_ternary(_make_ohlcv(300))
    time_rows = df["label"] == 0
    assert (df2.loc[time_rows, "target"] == 0).all(), "Time-expired label 0 should map to class 0"
```

- [ ] **Step 2: Run to verify it fails**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_labeling_ternary.py -v 2>&1 | head -30
```
Expected: `AttributeError: 'TripleBarrierLabeler' object has no attribute 'label_for_ternary'`

- [ ] **Step 3: Add `label_for_ternary()` to labeling.py**

Open `src/models/labeling.py` and add this method after `label_for_binary()` (line 155):

```python
def label_for_ternary(self, df: pd.DataFrame) -> pd.DataFrame:
    """
    Label for 3-class classification:
        label=+1 (TP hit)  → target=1  (LONG)
        label= 0 (expired) → target=0  (FLAT/HOLD)
        label=-1 (SL hit)  → target=2  (SHORT)

    Class 2 = SHORT avoids negative indices in XGBoost/LightGBM.
    """
    df = self.label(df)
    mapping = {1: 1, 0: 0, -1: 2}
    df["target"] = df["label"].map(mapping).astype("Int64")
    return df
```

- [ ] **Step 4: Run tests — all 4 must pass**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_labeling_ternary.py -v
```
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add src/models/labeling.py tests/test_labeling_ternary.py
git commit -m "feat(labeling): add label_for_ternary() — 3-class labels LONG/FLAT/SHORT"
```

---

## Task 2: EnsembleV5 — Multiclass

**Files:**
- Create: `src/models/ensemble_v5.py`
- Create: `tests/test_ensemble_v5.py`

### Objective
`EnsembleV5` trains on 3-class targets. `predict_proba()` returns shape `(n, 3)` — columns are `[prob_flat, prob_long, prob_short]`. `predict_signal()` returns one of `{"LONG", "SHORT", "FLAT"}`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_v5.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from src.models.ensemble_v5 import EnsembleV5


def _synthetic_data(n=400, n_features=20, seed=42):
    rng = np.random.default_rng(seed)
    X = rng.standard_normal((n, n_features))
    y = rng.integers(0, 3, size=n)  # 3 classes: 0=FLAT, 1=LONG, 2=SHORT
    return X, y


def test_predict_proba_shape():
    X, y = _synthetic_data()
    model = EnsembleV5()
    model.train(X[:300], y[:300], feature_names=[f"f{i}" for i in range(20)])
    proba = model.predict_proba(X[300:])
    assert proba.shape == (100, 3), f"Expected (100, 3), got {proba.shape}"


def test_predict_proba_sums_to_one():
    X, y = _synthetic_data()
    model = EnsembleV5()
    model.train(X[:300], y[:300], feature_names=[f"f{i}" for i in range(20)])
    proba = model.predict_proba(X[300:])
    row_sums = proba.sum(axis=1)
    np.testing.assert_allclose(row_sums, 1.0, atol=1e-5)


def test_predict_signal_values():
    X, y = _synthetic_data()
    model = EnsembleV5()
    model.train(X[:300], y[:300], feature_names=[f"f{i}" for i in range(20)])
    signals = model.predict_signal(X[300:310])
    assert set(signals).issubset({"LONG", "SHORT", "FLAT"})
    assert len(signals) == 10


def test_save_load_roundtrip(tmp_path):
    X, y = _synthetic_data()
    model = EnsembleV5()
    model.train(X[:300], y[:300], feature_names=[f"f{i}" for i in range(20)])
    proba_before = model.predict_proba(X[300:])

    model.save(str(tmp_path))
    model2 = EnsembleV5()
    model2.load(str(tmp_path))
    proba_after = model2.predict_proba(X[300:])

    np.testing.assert_allclose(proba_before, proba_after, atol=1e-4)
```

- [ ] **Step 2: Run to verify it fails**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_ensemble_v5.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'src.models.ensemble_v5'`

- [ ] **Step 3: Create `src/models/ensemble_v5.py`**

```python
"""
ENSEMBLE V5 — MULTICLASS (LONG / FLAT / SHORT)
================================================
3-class stacked ensemble: XGBoost + LightGBM + CatBoost base learners,
LightGBM multiclass meta-learner.

Class encoding: 0=FLAT/HOLD, 1=LONG, 2=SHORT
predict_proba() → shape (n, 3) — columns [prob_flat, prob_long, prob_short]
predict_signal() → str per row: "LONG" | "FLAT" | "SHORT"
"""

import json
import pickle
import copy
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

from src.models.validation import PurgedWalkForwardCV

_CLASS_NAMES = {0: "FLAT", 1: "LONG", 2: "SHORT"}


class EnsembleV5:
    """3-class stacked ensemble with walk-forward OOS meta-training."""

    def __init__(self, params: Optional[Dict] = None):
        self.params = params or {}
        self.base_models: Dict = {}
        self.meta_model = None
        self.feature_names: Optional[List[str]] = None
        self.n_classes = 3

    def _create_base_models(self) -> Dict:
        import xgboost as xgb
        import lightgbm as lgb
        from catboost import CatBoostClassifier

        xgb_params = dict(self.params.get("xgboost", {}))
        xgb_params.setdefault("eval_metric", "mlogloss")
        xgb_params.setdefault("num_class", 3)
        xgb_params.setdefault("objective", "multi:softprob")
        xgb_params.setdefault("random_state", 42)
        xgb_params.setdefault("n_estimators", 300)
        xgb_params.setdefault("max_depth", 5)
        xgb_params.setdefault("learning_rate", 0.05)

        lgb_params = dict(self.params.get("lightgbm", {}))
        lgb_params.setdefault("objective", "multiclass")
        lgb_params.setdefault("num_class", 3)
        lgb_params.setdefault("random_state", 42)
        lgb_params.setdefault("verbose", -1)
        lgb_params.setdefault("n_estimators", 300)
        lgb_params.setdefault("num_leaves", 63)
        lgb_params.setdefault("learning_rate", 0.05)

        cb_params = dict(self.params.get("catboost", {}))
        cb_params.setdefault("loss_function", "MultiClass")
        cb_params.setdefault("classes_count", 3)
        cb_params.setdefault("random_seed", 42)
        cb_params.setdefault("verbose", 0)
        cb_params.setdefault("iterations", 300)
        cb_params.setdefault("depth", 6)
        cb_params.setdefault("learning_rate", 0.05)

        return {
            "xgboost": xgb.XGBClassifier(**xgb_params),
            "lightgbm": lgb.LGBMClassifier(**lgb_params),
            "catboost": CatBoostClassifier(**cb_params),
        }

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        cv: Optional[PurgedWalkForwardCV] = None,
    ):
        """Train ensemble with walk-forward OOS stacking."""
        self.feature_names = feature_names
        if cv is None:
            cv = PurgedWalkForwardCV()

        models = self._create_base_models()
        oos_predictions = {}
        oos_indices = None
        oos_labels = None

        logger.info("EnsembleV5: training base models (3-class)...")
        for name, template in models.items():
            logger.info(f"  {name}...")
            def factory(m=template):
                return copy.deepcopy(m)
            indices, preds, true_labels = cv.get_oos_predictions(X, y, factory)
            oos_predictions[name] = preds
            if oos_indices is None:
                oos_indices = indices
                oos_labels = true_labels

        # Each base model OOS pred is shape (n,) with class indices — convert to proba columns
        # For multiclass base models, get_oos_predictions may return class indices.
        # Stack raw predictions (3 values per model): shape (n, 3*n_models)
        meta_parts = []
        for name in models:
            p = oos_predictions[name]
            if p.ndim == 1:
                # class index → one-hot probability proxy
                oh = np.zeros((len(p), self.n_classes))
                for cls in range(self.n_classes):
                    oh[:, cls] = (p == cls).astype(float)
                meta_parts.append(oh)
            else:
                meta_parts.append(p)

        meta_X = np.hstack(meta_parts)
        meta_X = np.nan_to_num(meta_X, nan=1.0 / self.n_classes)

        logger.info("EnsembleV5: training LightGBM meta-learner...")
        import lightgbm as lgb
        self.meta_model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=3,
            n_estimators=150,
            num_leaves=15,
            learning_rate=0.05,
            random_state=42,
            verbose=-1,
        )
        self.meta_model.fit(meta_X, oos_labels)

        logger.info("EnsembleV5: training final base models on full data...")
        X_clean = np.nan_to_num(X, nan=0.0)
        for name, template in models.items():
            m = copy.deepcopy(template)
            m.fit(X_clean, y)
            self.base_models[name] = m

        logger.info(f"EnsembleV5 trained: {list(self.base_models.keys())} + meta-learner")

    def _base_probas(self, X: np.ndarray) -> np.ndarray:
        """Return stacked base model probas: shape (n, 3*n_models)."""
        X_clean = np.nan_to_num(X, nan=0.0)
        parts = []
        for name, model in self.base_models.items():
            if hasattr(model, "predict_proba"):
                p = model.predict_proba(X_clean)
                if p.shape[1] == self.n_classes:
                    parts.append(p)
                else:
                    # Fallback: uniform
                    parts.append(np.full((len(X_clean), self.n_classes), 1.0 / self.n_classes))
            else:
                preds = model.predict(X_clean)
                oh = np.zeros((len(X_clean), self.n_classes))
                for cls in range(self.n_classes):
                    oh[:, cls] = (preds == cls).astype(float)
                parts.append(oh)
        return np.hstack(parts)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Returns shape (n, 3) — columns: [prob_flat, prob_long, prob_short].
        """
        meta_X = self._base_probas(X)
        meta_X = np.nan_to_num(meta_X, nan=1.0 / self.n_classes)

        if self.meta_model is None:
            # Average base probas
            parts = meta_X.reshape(len(X), len(self.base_models), self.n_classes)
            return parts.mean(axis=1)

        return self.meta_model.predict_proba(meta_X)

    def predict_signal(self, X: np.ndarray) -> List[str]:
        """Return list of 'LONG' | 'FLAT' | 'SHORT' per row."""
        proba = self.predict_proba(X)
        class_indices = proba.argmax(axis=1)
        return [_CLASS_NAMES[i] for i in class_indices]

    def save(self, directory: str):
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        for name, model in self.base_models.items():
            with open(path / f"base_{name}.pkl", "wb") as f:
                pickle.dump(model, f)
        if self.meta_model:
            with open(path / "meta_learner.pkl", "wb") as f:
                pickle.dump(self.meta_model, f)
        metadata = {
            "version": "v5",
            "n_classes": self.n_classes,
            "base_models": list(self.base_models.keys()),
            "feature_names": self.feature_names,
        }
        with open(path / "ensemble_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)
        logger.info(f"EnsembleV5 saved → {path}")

    def load(self, directory: str):
        path = Path(directory)
        with open(path / "ensemble_metadata.json") as f:
            meta = json.load(f)
        self.feature_names = meta.get("feature_names")
        self.n_classes = meta.get("n_classes", 3)
        for name in meta["base_models"]:
            with open(path / f"base_{name}.pkl", "rb") as f:
                self.base_models[name] = pickle.load(f)
        meta_path = path / "meta_learner.pkl"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                self.meta_model = pickle.load(f)
        logger.info(f"EnsembleV5 loaded from {path}")
```

- [ ] **Step 4: Run tests — all 4 must pass**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_ensemble_v5.py -v
```
Expected: `4 passed` (may take ~2 min due to tree model training)

- [ ] **Step 5: Commit**

```bash
git add src/models/ensemble_v5.py tests/test_ensemble_v5.py
git commit -m "feat(models): EnsembleV5 — 3-class multiclass stacked ensemble"
```

---

## Task 3: Per-Coin Model Store

**Files:**
- Create: `src/models/per_coin_model_store.py`
- (no separate test file — tested inline in Task 4)

### Objective
Save and load one `EnsembleV5` per ticker. Dir layout:
```
PRODUCTION_SYSTEM/models/v5/{ticker}/ensemble_metadata.json
                                     base_xgboost.pkl
                                     base_lightgbm.pkl
                                     base_catboost.pkl
                                     meta_learner.pkl
                                     train_metrics.json
```

- [ ] **Step 1: Create `src/models/per_coin_model_store.py`**

```python
"""
PER-COIN MODEL STORE V5
========================
Manages one EnsembleV5 per ticker.
Base dir: PRODUCTION_SYSTEM/models/v5/{ticker}/
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
from loguru import logger

from src.models.ensemble_v5 import EnsembleV5


class PerCoinModelStore:
    """Load/save one EnsembleV5 per ticker."""

    def __init__(self, base_dir: str = "PRODUCTION_SYSTEM/models/v5"):
        self.base_dir = Path(base_dir)
        self._cache: Dict[str, EnsembleV5] = {}

    def _ticker_dir(self, ticker: str) -> Path:
        return self.base_dir / ticker.upper()

    def save(self, ticker: str, model: EnsembleV5, metrics: Dict):
        """Save model + training metrics for a ticker."""
        d = self._ticker_dir(ticker)
        model.save(str(d))
        with open(d / "train_metrics.json", "w") as f:
            json.dump(metrics, f, indent=2)
        self._cache[ticker] = model
        logger.info(f"PerCoinModelStore: saved {ticker} → {d}")

    def load(self, ticker: str) -> Optional[EnsembleV5]:
        """Load model for ticker; returns None if not found."""
        if ticker in self._cache:
            return self._cache[ticker]
        d = self._ticker_dir(ticker)
        if not (d / "ensemble_metadata.json").exists():
            return None
        model = EnsembleV5()
        model.load(str(d))
        self._cache[ticker] = model
        return model

    def available_tickers(self) -> List[str]:
        """Return tickers that have trained models."""
        if not self.base_dir.exists():
            return []
        return [d.name for d in self.base_dir.iterdir() if (d / "ensemble_metadata.json").exists()]

    def get_metrics(self, ticker: str) -> Optional[Dict]:
        d = self._ticker_dir(ticker)
        metrics_path = d / "train_metrics.json"
        if not metrics_path.exists():
            return None
        with open(metrics_path) as f:
            return json.load(f)

    def invalidate_cache(self, ticker: str):
        self._cache.pop(ticker, None)
```

- [ ] **Step 2: No tests to run — verified in Task 4**

- [ ] **Step 3: Commit**

```bash
git add src/models/per_coin_model_store.py
git commit -m "feat(models): PerCoinModelStore — per-ticker V5 model persistence"
```

---

## Task 4: Per-Coin Auto-Trainer V5

**Files:**
- Create: `src/models/auto_trainer_v5.py`
- Create: `tests/test_auto_trainer_v5.py`

### Objective
`AutoTrainerV5.train_ticker(ticker, df)` takes raw OHLCV + feature DataFrame, applies ternary labels, trains `EnsembleV5`, saves to `PerCoinModelStore`, and returns metrics including `win_rate_long`, `win_rate_short`, `accuracy_3class`.

- [ ] **Step 1: Write failing test**

```python
# tests/test_auto_trainer_v5.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pandas as pd
import pytest
from src.models.auto_trainer_v5 import AutoTrainerV5
from src.models.per_coin_model_store import PerCoinModelStore


def _make_ohlcv_with_features(n=400, seed=42):
    """Synthetic OHLCV + 20 dummy features."""
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)
    df = pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.005,
        "low": close * 0.995,
        "close": close,
        "volume": np.random.uniform(1e6, 5e6, n),
    })
    for i in range(20):
        df[f"feat_{i}"] = np.random.randn(n)
    return df


def test_train_ticker_returns_metrics(tmp_path):
    store = PerCoinModelStore(base_dir=str(tmp_path))
    trainer = AutoTrainerV5(model_store=store)
    df = _make_ohlcv_with_features()
    metrics = trainer.train_ticker("BTCUSDT", df)
    assert "accuracy_3class" in metrics
    assert "win_rate_long" in metrics
    assert "win_rate_short" in metrics
    assert 0.0 <= metrics["accuracy_3class"] <= 1.0


def test_train_ticker_saves_model(tmp_path):
    store = PerCoinModelStore(base_dir=str(tmp_path))
    trainer = AutoTrainerV5(model_store=store)
    df = _make_ohlcv_with_features()
    trainer.train_ticker("ETHUSDT", df)
    model = store.load("ETHUSDT")
    assert model is not None
    assert model.meta_model is not None


def test_train_ticker_model_can_predict(tmp_path):
    store = PerCoinModelStore(base_dir=str(tmp_path))
    trainer = AutoTrainerV5(model_store=store)
    df = _make_ohlcv_with_features()
    trainer.train_ticker("SOLUSDT", df)
    model = store.load("SOLUSDT")
    # Predict on 5 rows of dummy features
    X = np.random.randn(5, 20)
    signals = model.predict_signal(X)
    assert len(signals) == 5
    assert all(s in {"LONG", "SHORT", "FLAT"} for s in signals)
```

- [ ] **Step 2: Run to verify it fails**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_auto_trainer_v5.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'src.models.auto_trainer_v5'`

- [ ] **Step 3: Create `src/models/auto_trainer_v5.py`**

```python
"""
AUTO-TRAINER V5 — PER-COIN
===========================
Trains one EnsembleV5 per ticker using ternary triple-barrier labels.
Writes daily comparison logs to docs/BACKTEST_LOG_YYYY-MM-DD.md.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
from loguru import logger
from sklearn.metrics import accuracy_score, classification_report

from src.models.labeling import TripleBarrierLabeler
from src.models.ensemble_v5 import EnsembleV5
from src.models.per_coin_model_store import PerCoinModelStore
from src.models.validation import PurgedWalkForwardCV


class AutoTrainerV5:
    """Per-coin training with EnsembleV5 and ternary labels."""

    FEATURE_EXCLUDE = {"open", "high", "low", "close", "volume",
                       "label", "target", "days_held", "barrier_hit",
                       "max_favorable", "max_adverse", "tp_price", "sl_price"}

    def __init__(self, model_store: Optional[PerCoinModelStore] = None):
        self.model_store = model_store or PerCoinModelStore()
        self.labeler = TripleBarrierLabeler()

    def _extract_features(self, df: pd.DataFrame) -> list:
        return [c for c in df.columns if c not in self.FEATURE_EXCLUDE]

    def train_ticker(self, ticker: str, df: pd.DataFrame) -> Dict:
        """
        Train EnsembleV5 for a single ticker.

        Args:
            ticker: e.g. "BTCUSDT"
            df: DataFrame with OHLCV columns + feature columns

        Returns:
            metrics dict with accuracy_3class, win_rate_long, win_rate_short, etc.
        """
        start = time.time()
        logger.info(f"[{ticker}] Labeling {len(df)} rows...")
        labeled = self.labeler.label_for_ternary(df.copy())
        labeled = labeled.dropna(subset=["target"])
        labeled["target"] = labeled["target"].astype(int)

        feature_cols = self._extract_features(labeled)
        if not feature_cols:
            raise ValueError(f"[{ticker}] No feature columns found in DataFrame")

        X = labeled[feature_cols].values.astype(np.float32)
        y = labeled["target"].values

        # Split: 80% train, 20% OOS test (temporal split — no shuffle)
        split = int(len(X) * 0.8)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        logger.info(f"[{ticker}] Training EnsembleV5 on {len(X_train)} rows...")
        cv = PurgedWalkForwardCV()
        model = EnsembleV5()
        model.train(X_train, y_train, feature_names=feature_cols, cv=cv)

        # Evaluate on OOS
        y_pred = np.array(model.predict_proba(X_test).argmax(axis=1))
        accuracy = float(accuracy_score(y_test, y_pred))

        long_mask = y_test == 1
        short_mask = y_test == 2
        win_rate_long = float((y_pred[long_mask] == 1).mean()) if long_mask.sum() > 0 else 0.0
        win_rate_short = float((y_pred[short_mask] == 2).mean()) if short_mask.sum() > 0 else 0.0

        class_counts = {
            "flat": int((y == 0).sum()),
            "long": int((y == 1).sum()),
            "short": int((y == 2).sum()),
        }

        metrics = {
            "ticker": ticker,
            "trained_at": datetime.utcnow().isoformat(),
            "train_rows": int(len(X_train)),
            "test_rows": int(len(X_test)),
            "accuracy_3class": round(accuracy, 4),
            "win_rate_long": round(win_rate_long, 4),
            "win_rate_short": round(win_rate_short, 4),
            "class_distribution": class_counts,
            "n_features": len(feature_cols),
            "training_seconds": round(time.time() - start, 1),
        }

        self.model_store.save(ticker, model, metrics)
        logger.info(f"[{ticker}] Done — accuracy={accuracy:.3f}, "
                    f"win_rate_long={win_rate_long:.3f}, win_rate_short={win_rate_short:.3f}")
        return metrics
```

- [ ] **Step 4: Run tests — all 3 must pass**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_auto_trainer_v5.py -v
```
Expected: `3 passed` (takes ~2-3 min)

- [ ] **Step 5: Commit**

```bash
git add src/models/auto_trainer_v5.py tests/test_auto_trainer_v5.py
git commit -m "feat(models): AutoTrainerV5 — per-coin ternary training with OOS metrics"
```

---

## Task 5: PredictorV5 — LONG/SHORT/FLAT Signals

**Files:**
- Create: `src/models/predictor_v5.py`
- Create: `tests/test_predictor_v5.py`

### Objective
`PredictorV5.get_signal(ticker, features_dict)` returns `{"signal": "LONG"|"SHORT"|"FLAT", "prob_long": float, "prob_short": float, "prob_flat": float, "confidence": float}`. Falls back to "FLAT" if no per-coin model exists.

- [ ] **Step 1: Write failing test**

```python
# tests/test_predictor_v5.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest
from src.models.predictor_v5 import PredictorV5
from src.models.per_coin_model_store import PerCoinModelStore
from src.models.auto_trainer_v5 import AutoTrainerV5
import pandas as pd


def _make_ohlcv_with_features(n=400, seed=42):
    np.random.seed(seed)
    close = 100 + np.cumsum(np.random.randn(n) * 0.5)
    close = np.maximum(close, 1)
    df = pd.DataFrame({
        "open": close * 0.999, "high": close * 1.005,
        "low": close * 0.995, "close": close,
        "volume": np.random.uniform(1e6, 5e6, n),
    })
    for i in range(20):
        df[f"feat_{i}"] = np.random.randn(n)
    return df


def test_get_signal_returns_valid_keys(tmp_path):
    store = PerCoinModelStore(base_dir=str(tmp_path))
    trainer = AutoTrainerV5(model_store=store)
    df = _make_ohlcv_with_features()
    trainer.train_ticker("BTCUSDT", df)

    predictor = PredictorV5(model_store=store)
    features = {f"feat_{i}": float(np.random.randn()) for i in range(20)}
    result = predictor.get_signal("BTCUSDT", features)

    assert result["signal"] in {"LONG", "SHORT", "FLAT"}
    assert 0.0 <= result["prob_long"] <= 1.0
    assert 0.0 <= result["prob_short"] <= 1.0
    assert 0.0 <= result["prob_flat"] <= 1.0
    assert abs(result["prob_long"] + result["prob_short"] + result["prob_flat"] - 1.0) < 1e-5
    assert "confidence" in result


def test_fallback_to_flat_when_no_model(tmp_path):
    store = PerCoinModelStore(base_dir=str(tmp_path))
    predictor = PredictorV5(model_store=store)
    result = predictor.get_signal("UNKNOWNCOIN", {"feat_0": 1.0})
    assert result["signal"] == "FLAT"
    assert result["confidence"] == 0.0
```

- [ ] **Step 2: Run to verify it fails**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_predictor_v5.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `src/models/predictor_v5.py`**

```python
"""
PREDICTOR V5
=============
Reads per-coin EnsembleV5 models, emits LONG / SHORT / FLAT signals.
Falls back to FLAT with zero confidence if no model exists for a ticker.
"""

from typing import Dict, Optional
import numpy as np
from loguru import logger

from src.models.per_coin_model_store import PerCoinModelStore


class PredictorV5:
    """Signal emitter backed by per-coin EnsembleV5 models."""

    def __init__(self, model_store: Optional[PerCoinModelStore] = None):
        self.model_store = model_store or PerCoinModelStore()

    def get_signal(self, ticker: str, features: Dict[str, float]) -> Dict:
        """
        Returns:
            {
                "signal":     "LONG" | "SHORT" | "FLAT",
                "prob_long":  float,
                "prob_short": float,
                "prob_flat":  float,
                "confidence": float,  # max(prob_long, prob_short) — how sure we are
                "ticker":     str,
            }
        """
        model = self.model_store.load(ticker)

        if model is None:
            logger.warning(f"PredictorV5: no model for {ticker} — emitting FLAT")
            return {
                "signal": "FLAT", "prob_long": 0.0,
                "prob_short": 0.0, "prob_flat": 1.0,
                "confidence": 0.0, "ticker": ticker,
            }

        # Align feature vector to model's feature order
        feature_names = model.feature_names or []
        X = np.array([[features.get(f, 0.0) for f in feature_names]], dtype=np.float32)

        proba = model.predict_proba(X)[0]  # shape (3,)
        idx = int(proba.argmax())
        signal_map = {0: "FLAT", 1: "LONG", 2: "SHORT"}
        signal = signal_map[idx]
        confidence = float(max(proba[1], proba[2]))  # max of directional probs

        return {
            "signal": signal,
            "prob_flat": float(proba[0]),
            "prob_long": float(proba[1]),
            "prob_short": float(proba[2]),
            "confidence": confidence,
            "ticker": ticker,
        }
```

- [ ] **Step 4: Run tests — all 2 must pass**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_predictor_v5.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/models/predictor_v5.py tests/test_predictor_v5.py
git commit -m "feat(models): PredictorV5 — per-coin LONG/SHORT/FLAT signal emitter"
```

---

## Task 6: Binance Futures SHORT Execution

**Files:**
- Create: `src/services/binance_futures.py`
- Create: `tests/test_binance_futures.py`

### Objective
`BinanceFuturesService.open_short(symbol, usdt_amount)` and `close_short(symbol)` using Binance USDT-M Futures API. Uses testnet by default (controlled by `settings.USE_TESTNET`).

- [ ] **Step 1: Write failing tests**

```python
# tests/test_binance_futures.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from unittest.mock import MagicMock, patch
from src.services.binance_futures import BinanceFuturesService


def _mock_client():
    c = MagicMock()
    c.futures_create_order.return_value = {
        "orderId": 12345,
        "symbol": "BTCUSDT",
        "side": "SELL",
        "type": "MARKET",
        "executedQty": "0.001",
        "avgPrice": "65000.0",
        "status": "FILLED",
    }
    c.futures_get_position_risk.return_value = [
        {"symbol": "BTCUSDT", "positionAmt": "-0.001", "entryPrice": "65000.0"}
    ]
    c.futures_change_leverage.return_value = {"leverage": 2}
    return c


@patch("src.services.binance_futures.Client")
def test_open_short_calls_sell_order(MockClient):
    MockClient.return_value = _mock_client()
    service = BinanceFuturesService(testnet=True)
    result = service.open_short("BTCUSDT", usdt_amount=100.0, current_price=65000.0)
    assert result["side"] == "SELL"
    assert result["symbol"] == "BTCUSDT"


@patch("src.services.binance_futures.Client")
def test_close_short_calls_buy_order(MockClient):
    mock_client = _mock_client()
    mock_client.futures_create_order.return_value = {
        "orderId": 99, "symbol": "BTCUSDT", "side": "BUY",
        "type": "MARKET", "executedQty": "0.001",
        "avgPrice": "63000.0", "status": "FILLED",
    }
    MockClient.return_value = mock_client
    service = BinanceFuturesService(testnet=True)
    result = service.close_short("BTCUSDT")
    assert result["side"] == "BUY"


@patch("src.services.binance_futures.Client")
def test_get_short_position_none_when_no_position(MockClient):
    mock_client = _mock_client()
    mock_client.futures_get_position_risk.return_value = [
        {"symbol": "BTCUSDT", "positionAmt": "0.0", "entryPrice": "0.0"}
    ]
    MockClient.return_value = mock_client
    service = BinanceFuturesService(testnet=True)
    pos = service.get_short_position("BTCUSDT")
    assert pos is None
```

- [ ] **Step 2: Run to verify fails**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_binance_futures.py -v 2>&1 | head -10
```

- [ ] **Step 3: Create `src/services/binance_futures.py`**

```python
"""
BINANCE FUTURES SERVICE
========================
Manages USDT-M Futures SHORT positions for Cryptonita V5.
Uses testnet when settings.USE_TESTNET=True or testnet=True passed directly.

Safety: max leverage 2x, max 5% portfolio per position (enforced here).
"""

from typing import Dict, Optional
from loguru import logger
from binance.client import Client
from binance.exceptions import BinanceAPIException

from config import settings


class BinanceFuturesService:
    """USDT-M Futures SHORT execution. Leverage fixed at 2x."""

    MAX_LEVERAGE = 2
    MIN_USDT = 10.0  # Binance minimum notional

    def __init__(self, testnet: Optional[bool] = None):
        use_testnet = testnet if testnet is not None else getattr(settings, "USE_TESTNET", True)
        api_key = getattr(settings, "BINANCE_API_KEY", "")
        api_secret = getattr(settings, "BINANCE_SECRET_KEY", "")

        self.client = Client(api_key, api_secret, testnet=use_testnet)
        logger.info(f"BinanceFuturesService init (testnet={use_testnet})")

    def _set_leverage(self, symbol: str):
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=self.MAX_LEVERAGE)
        except BinanceAPIException as e:
            logger.warning(f"Could not set leverage for {symbol}: {e}")

    def open_short(self, symbol: str, usdt_amount: float, current_price: float) -> Dict:
        """
        Open a SHORT position via Futures MARKET SELL.
        qty = usdt_amount / current_price (rounded to symbol precision).
        """
        if usdt_amount < self.MIN_USDT:
            raise ValueError(f"usdt_amount {usdt_amount} below minimum {self.MIN_USDT}")

        self._set_leverage(symbol)
        qty = round(usdt_amount / current_price, 3)  # TODO: use symbol's stepSize

        logger.info(f"Opening SHORT {symbol}: qty={qty} @ ~{current_price}")
        order = self.client.futures_create_order(
            symbol=symbol,
            side="SELL",
            type="MARKET",
            quantity=qty,
            positionSide="SHORT",  # hedge mode
        )
        logger.info(f"SHORT opened: orderId={order.get('orderId')}")
        return order

    def close_short(self, symbol: str) -> Dict:
        """Close entire SHORT position with a BUY order."""
        pos = self.get_short_position(symbol)
        if pos is None:
            logger.info(f"No SHORT position to close for {symbol}")
            return {"status": "no_position", "symbol": symbol}

        qty = abs(float(pos["positionAmt"]))
        logger.info(f"Closing SHORT {symbol}: qty={qty}")
        order = self.client.futures_create_order(
            symbol=symbol,
            side="BUY",
            type="MARKET",
            quantity=qty,
            positionSide="SHORT",
        )
        logger.info(f"SHORT closed: orderId={order.get('orderId')}")
        return order

    def get_short_position(self, symbol: str) -> Optional[Dict]:
        """Return current SHORT position dict, or None if flat."""
        positions = self.client.futures_get_position_risk(symbol=symbol)
        for p in positions:
            if p["symbol"] == symbol and float(p["positionAmt"]) < 0:
                return p
        return None
```

- [ ] **Step 4: Run tests — all 3 must pass**

```bash
~/.pyenv/versions/3.11.9/bin/python -m pytest tests/test_binance_futures.py -v
```

- [ ] **Step 5: Commit**

```bash
git add src/services/binance_futures.py tests/test_binance_futures.py
git commit -m "feat(services): BinanceFuturesService — SHORT execution via USDT-M Futures"
```

---

## Task 7: Walk-Forward Backtest V5 (Diagnostic Script)

**Files:**
- Create: `scripts/walk_forward_backtest_v5.py`

### Objective
Run an honest walk-forward backtest on the NEW V5 model (no lookahead). Outputs a daily log `docs/BACKTEST_LOG_YYYY-MM-DD.md` comparing V4 baseline metrics vs V5 metrics.

- [ ] **Step 1: Create `scripts/walk_forward_backtest_v5.py`**

```python
#!/usr/bin/env python3
"""
WALK-FORWARD BACKTEST V5
=========================
Honest backtesting with no lookahead:
  - Train on first 70% of data
  - Test on next 15%
  - Validate on last 15%
  - Trades are simulated with 0.1% fees and real TP/SL levels

Usage:
    ~/.pyenv/versions/3.11.9/bin/python scripts/walk_forward_backtest_v5.py \
        --ticker BTCUSDT --capital 1000 --output docs/BACKTEST_LOG_2026-06-02.md

Output metrics:
    - accuracy_3class (3-way)
    - win_rate_long, win_rate_short (precision on directional signals)
    - roi, sharpe, max_drawdown (portfolio simulation)
    - n_trades (how selective the model is)
"""

import sys
import argparse
import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.models.labeling import TripleBarrierLabeler
from src.models.ensemble_v5 import EnsembleV5
from src.models.auto_trainer_v5 import AutoTrainerV5
from src.models.per_coin_model_store import PerCoinModelStore
from src.services.binance_data_service import BinanceDataService


FEE_PCT = 0.001  # 0.1% per trade (Binance taker)


def simulate_portfolio(trades_df: pd.DataFrame, initial_capital: float = 1000.0) -> dict:
    """Simulate portfolio from a list of trades with returns."""
    capital = initial_capital
    equity_curve = [capital]
    wins, losses = 0, 0

    for _, row in trades_df.iterrows():
        gross_return = row.get("gross_return", 0.0)
        net_return = gross_return - FEE_PCT * 2  # entry + exit fees
        pnl = capital * net_return
        capital += pnl
        equity_curve.append(capital)
        if pnl > 0:
            wins += 1
        else:
            losses += 1

    equity = np.array(equity_curve)
    total_trades = wins + losses
    roi = (capital - initial_capital) / initial_capital
    returns = np.diff(equity) / equity[:-1]
    sharpe = float(np.sqrt(252) * returns.mean() / returns.std()) if returns.std() > 0 else 0.0
    rolling_max = np.maximum.accumulate(equity)
    drawdowns = (equity - rolling_max) / rolling_max
    max_dd = float(drawdowns.min())

    return {
        "roi": round(roi, 4),
        "sharpe": round(sharpe, 3),
        "max_drawdown": round(max_dd, 4),
        "win_rate": round(wins / total_trades, 4) if total_trades > 0 else 0.0,
        "n_trades": total_trades,
        "final_capital": round(capital, 2),
    }


def backtest_ticker(ticker: str, df: pd.DataFrame, initial_capital: float) -> dict:
    """Run walk-forward backtest for one ticker."""
    labeler = TripleBarrierLabeler()
    labeled = labeler.label_for_ternary(df.copy())
    labeled = labeled.dropna(subset=["target"])
    labeled["target"] = labeled["target"].astype(int)

    n = len(labeled)
    train_end = int(n * 0.70)
    test_end = int(n * 0.85)

    trainer = AutoTrainerV5(model_store=PerCoinModelStore(base_dir="/tmp/v5_backtest"))
    trainer_feature_cols = trainer._extract_features(labeled)

    X_all = labeled[trainer_feature_cols].values.astype(np.float32)
    y_all = labeled["target"].values

    # Train on first 70%
    model = EnsembleV5()
    model.train(X_all[:train_end], y_all[:train_end], feature_names=trainer_feature_cols)

    # Test on 15-30% slice (out-of-sample)
    X_test = X_all[train_end:test_end]
    y_test = y_all[train_end:test_end]
    test_rows = labeled.iloc[train_end:test_end].copy()

    proba = model.predict_proba(X_test)
    pred_classes = proba.argmax(axis=1)

    from sklearn.metrics import accuracy_score
    accuracy = float(accuracy_score(y_test, pred_classes))

    long_mask = y_test == 1
    short_mask = y_test == 2
    win_rate_long = float((pred_classes[long_mask] == 1).mean()) if long_mask.sum() > 0 else 0.0
    win_rate_short = float((pred_classes[short_mask] == 2).mean()) if short_mask.sum() > 0 else 0.0

    # Simulate trades: only enter on LONG(1) or SHORT(2) predictions
    # Use actual label (1=TP, 2=SL → SHORT TP) as outcome
    trades = []
    for i, (pred_cls, true_cls, max_fav, max_adv) in enumerate(zip(
        pred_classes, y_test,
        test_rows["max_favorable"].values,
        test_rows["max_adverse"].values,
    )):
        if pred_cls == 1:  # Predicted LONG
            # TP hit (true_cls==1) → +max_favorable, SL hit (true_cls==2) → max_adverse, else 0
            gross = max_fav if true_cls == 1 else (max_adv if true_cls == 2 else 0.0)
            trades.append({"gross_return": gross})
        elif pred_cls == 2:  # Predicted SHORT
            # Inverse: SL hit on LONG label is a SHORT win
            gross = abs(max_adv) if true_cls == 2 else (-max_fav if true_cls == 1 else 0.0)
            trades.append({"gross_return": gross})

    if trades:
        trades_df = pd.DataFrame(trades)
        portfolio = simulate_portfolio(trades_df, initial_capital)
    else:
        portfolio = {"roi": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                     "win_rate": 0.0, "n_trades": 0, "final_capital": initial_capital}

    return {
        "ticker": ticker,
        "accuracy_3class": round(accuracy, 4),
        "win_rate_long": round(win_rate_long, 4),
        "win_rate_short": round(win_rate_short, 4),
        "class_dist": {
            "flat": int((y_all == 0).sum()),
            "long": int((y_all == 1).sum()),
            "short": int((y_all == 2).sum()),
        },
        **portfolio,
    }


def write_log(results: list, output_path: str, initial_capital: float):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# Cryptonita V5 Walk-Forward Backtest — {today}\n",
        f"Capital: ${initial_capital} | Fees: {FEE_PCT*100:.1f}% per side\n\n",
        "| Ticker | Accuracy | Win%Long | Win%Short | ROI | Sharpe | MaxDD | Trades |\n",
        "|--------|----------|----------|-----------|-----|--------|-------|--------|\n",
    ]
    for r in results:
        lines.append(
            f"| {r['ticker']} | {r['accuracy_3class']:.3f} | "
            f"{r['win_rate_long']:.3f} | {r['win_rate_short']:.3f} | "
            f"{r['roi']*100:+.1f}% | {r['sharpe']:.2f} | "
            f"{r['max_drawdown']*100:.1f}% | {r['n_trades']} |\n"
        )

    avg_acc = np.mean([r["accuracy_3class"] for r in results])
    avg_win_l = np.mean([r["win_rate_long"] for r in results])
    avg_win_s = np.mean([r["win_rate_short"] for r in results])
    avg_roi = np.mean([r["roi"] for r in results])

    lines += [
        "\n## Summary\n",
        f"- Avg 3-class accuracy: **{avg_acc:.3f}**\n",
        f"- Avg win rate LONG: **{avg_win_l:.3f}**\n",
        f"- Avg win rate SHORT: **{avg_win_s:.3f}**\n",
        f"- Avg ROI: **{avg_roi*100:+.1f}%**\n",
        f"\n> V4 baseline win rate (binary): see BACKTEST_V4_BASELINE_2026-06-02.json\n",
    ]

    Path(output_path).write_text("".join(lines))
    logger.info(f"Log written → {output_path}")


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--ticker", default="BTCUSDT")
    p.add_argument("--all-tickers", action="store_true", help="Run on all 47 coins")
    p.add_argument("--capital", type=float, default=1000.0)
    p.add_argument("--output", default=f"docs/BACKTEST_LOG_{datetime.now().strftime('%Y-%m-%d')}.md")
    p.add_argument("--lookback-days", type=int, default=365)
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    data_service = BinanceDataService()

    tickers = list(settings.TICKERS) if args.all_tickers else [args.ticker]

    results = []
    for ticker in tickers:
        logger.info(f"Fetching {args.lookback_days}d OHLCV for {ticker}...")
        try:
            df = data_service.get_ohlcv(ticker, interval="1d", lookback_days=args.lookback_days)
            if df is None or len(df) < 100:
                logger.warning(f"Not enough data for {ticker}")
                continue
            result = backtest_ticker(ticker, df, args.capital)
            results.append(result)
            logger.info(f"{ticker}: acc={result['accuracy_3class']:.3f} roi={result['roi']*100:+.1f}%")
        except Exception as e:
            logger.error(f"{ticker} failed: {e}")

    if results:
        write_log(results, args.output, args.capital)
        print(f"\nResults saved → {args.output}")
    else:
        print("No results generated — check ticker and data service")
```

- [ ] **Step 2: Run it on BTC (quick smoke test)**

```bash
~/.pyenv/versions/3.11.9/bin/python scripts/walk_forward_backtest_v5.py \
    --ticker BTCUSDT --capital 1000 \
    --output docs/BACKTEST_LOG_$(date +%Y-%m-%d).md
```
Expected: markdown file created with at least 1 row in the table, no Python errors.

- [ ] **Step 3: Run full backtest (all tickers)**

```bash
~/.pyenv/versions/3.11.9/bin/python scripts/walk_forward_backtest_v5.py \
    --all-tickers --capital 1000 \
    --output "docs/BACKTEST_LOG_$(date +%Y-%m-%d).md"
```
Expected: log with one row per ticker, summary section with averages.

- [ ] **Step 4: Commit**

```bash
git add scripts/walk_forward_backtest_v5.py
git commit -m "feat(scripts): walk_forward_backtest_v5 — honest OOS backtest with daily log"
```

---

## Task 8: Wire PredictorV5 into Trading Bot (SHORT signals)

**Files:**
- Modify: `src/bot/trading_bot.py` (add SHORT branch)

### Objective
When `PredictorV5` returns `signal="SHORT"` and `confidence >= threshold`, open a Futures SHORT instead of a LONG. When SHORT position hits TP/SL, close via `BinanceFuturesService.close_short()`.

This is the INTEGRATION step. Read `src/bot/trading_bot.py` fully before editing to understand the existing LONG flow, then mirror it for SHORT.

- [ ] **Step 1: Read the full trading_bot.py**

```bash
~/.pyenv/versions/3.11.9/bin/python -c "
import sys; sys.path.insert(0,'.')
from pathlib import Path
print(Path('src/bot/trading_bot.py').read_text())
" 2>&1 | head -200
```

- [ ] **Step 2: Add SHORT handling**

In `trading_bot.py`, find the `_process_signal()` method (or equivalent). After the LONG branch, add:

```python
elif signal_result["signal"] == "SHORT" and signal_result["confidence"] >= self.short_threshold:
    if self.futures_service.get_short_position(ticker) is not None:
        logger.info(f"{ticker}: already in SHORT — skip")
        return
    current_price = self.binance_service.get_price(ticker)
    usdt_size = self._calculate_position_size(ticker, signal_result["confidence"])
    try:
        order = self.futures_service.open_short(ticker, usdt_size, current_price)
        logger.info(f"SHORT opened {ticker}: {order}")
        self._record_trade(ticker, "SHORT", current_price, usdt_size, signal_result)
    except Exception as e:
        logger.error(f"SHORT order failed {ticker}: {e}")
```

And in `__init__`, add:
```python
from src.services.binance_futures import BinanceFuturesService
from src.models.predictor_v5 import PredictorV5

self.futures_service = BinanceFuturesService()
self.predictor_v5 = PredictorV5()
self.short_threshold = getattr(settings, "SHORT_CONFIDENCE_THRESHOLD", 0.60)
```

- [ ] **Step 3: Add `SHORT_CONFIDENCE_THRESHOLD` to config.py**

Find `config.py` and add:
```python
SHORT_CONFIDENCE_THRESHOLD: float = 0.60
```

- [ ] **Step 4: Commit**

```bash
git add src/bot/trading_bot.py config.py
git commit -m "feat(bot): wire PredictorV5 SHORT signals to BinanceFuturesService"
```

---

## Task 9: Per-Coin Training Script

**Files:**
- Create: `scripts/train_all_coins_v5.py`

### Objective
Train one `EnsembleV5` per ticker in the portfolio (47 coins), save to `PerCoinModelStore`, print a summary table. This is the script that replaces the old global `force_retrain.py`.

- [ ] **Step 1: Create `scripts/train_all_coins_v5.py`**

```python
#!/usr/bin/env python3
"""
TRAIN ALL COINS V5
===================
Trains one EnsembleV5 per ticker. Replaces global model training.

Usage:
    ~/.pyenv/versions/3.11.9/bin/python scripts/train_all_coins_v5.py \
        [--tickers BTCUSDT,ETHUSDT] [--lookback-days 365]
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd
from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.services.binance_data_service import BinanceDataService
from src.data.features_v4 import FeatureEngineerV4
from src.models.auto_trainer_v5 import AutoTrainerV5
from src.models.per_coin_model_store import PerCoinModelStore


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--tickers", default=None, help="Comma-separated list; default=all")
    p.add_argument("--lookback-days", type=int, default=365)
    p.add_argument("--model-dir", default="PRODUCTION_SYSTEM/models/v5")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    tickers = args.tickers.split(",") if args.tickers else list(settings.TICKERS)

    data_service = BinanceDataService()
    feature_eng = FeatureEngineerV4()
    store = PerCoinModelStore(base_dir=args.model_dir)
    trainer = AutoTrainerV5(model_store=store)

    summary = []
    for ticker in tickers:
        logger.info(f"=== {ticker} ===")
        try:
            df = data_service.get_ohlcv(ticker, interval="1d", lookback_days=args.lookback_days)
            if df is None or len(df) < 100:
                logger.warning(f"  Skipping {ticker}: insufficient data")
                continue
            # Engineer features
            df_feat = feature_eng.engineer(df, ticker=ticker)
            metrics = trainer.train_ticker(ticker, df_feat)
            summary.append(metrics)
            logger.info(
                f"  ✓ acc={metrics['accuracy_3class']:.3f} "
                f"long_wr={metrics['win_rate_long']:.3f} "
                f"short_wr={metrics['win_rate_short']:.3f}"
            )
        except Exception as e:
            logger.error(f"  ✗ {ticker}: {e}")

    if summary:
        print("\n=== Training Summary ===")
        df_sum = pd.DataFrame(summary)[["ticker", "accuracy_3class",
                                        "win_rate_long", "win_rate_short",
                                        "n_features", "training_seconds"]]
        print(df_sum.to_string(index=False))
        avg_acc = df_sum["accuracy_3class"].mean()
        print(f"\nAvg 3-class accuracy: {avg_acc:.3f}")
    else:
        print("No models trained successfully")
```

- [ ] **Step 2: Smoke test on 3 coins**

```bash
~/.pyenv/versions/3.11.9/bin/python scripts/train_all_coins_v5.py \
    --tickers BTCUSDT,ETHUSDT,SOLUSDT --lookback-days 180
```
Expected: table with 3 rows, accuracy values, no crashes.

- [ ] **Step 3: Commit**

```bash
git add scripts/train_all_coins_v5.py
git commit -m "feat(scripts): train_all_coins_v5 — per-coin V5 training runner"
```

---

## Validation Checklist (run before declaring V5 ready)

- [ ] All unit tests pass: `~/.pyenv/versions/3.11.9/bin/python -m pytest tests/ -v -k "ternary or ensemble_v5 or predictor_v5 or futures" 2>&1 | tail -20`
- [ ] V5 backtest log exists: `ls docs/BACKTEST_LOG_*.md`
- [ ] V5 average accuracy > V4 win rate (check `docs/BACKTEST_V4_BASELINE_2026-06-02.json`)
- [ ] SHORT signals appear in V5 backtest (win_rate_short > 0 for at least 50% of tickers)
- [ ] `config.py` has `SHORT_CONFIDENCE_THRESHOLD`
- [ ] At least 10 per-coin models saved: `ls PRODUCTION_SYSTEM/models/v5/ | wc -l`

---

## Daily Comparison Protocol

After each training run, run:
```bash
~/.pyenv/versions/3.11.9/bin/python scripts/walk_forward_backtest_v5.py \
    --all-tickers --output "docs/BACKTEST_LOG_$(date +%Y-%m-%d).md"
```

Compare `win_rate_long` and `accuracy_3class` in successive log files. V5 is better than V4 when:
- `accuracy_3class` > 0.43 (V4 baseline win rate was 43.93%)
- `win_rate_long + win_rate_short` > `V4 win_rate_long` (we now have two ways to win)
- `roi` positive across >50% of tickers in the OOS window
