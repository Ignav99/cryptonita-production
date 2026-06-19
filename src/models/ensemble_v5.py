"""
ENSEMBLE V5 — TERNARY STACKING MODEL
======================================
Three-class stacked ensemble for LONG / HOLD / SHORT prediction.

Classes:
  0 = HOLD  (time barrier — no trade)
  1 = LONG  (take profit hit — buy signal)
  2 = SHORT (stop loss hit — short signal)

Base learners (Level 0): XGBoost, LightGBM, CatBoost (all multi-class)
Meta-learner  (Level 1): LightGBM on OOS softmax probabilities (n,3)

NOTE: We call cv.split() directly (not cv.get_oos_predictions()) because
the latter hardcodes [:, 1] for binary models. We need full (n, 3) softmax.
"""

import copy
import json
import pickle
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger

from src.models.validation import PurgedWalkForwardCV


CLASS_NAMES = {0: "HOLD", 1: "LONG", 2: "SHORT"}
N_CLASSES = 3


class EnsembleV5:
    """
    Stacked ensemble for ternary crypto signal prediction.

    predict_proba() → shape (n_samples, 3)
      col 0: P(HOLD), col 1: P(LONG), col 2: P(SHORT)

    predict() → shape (n_samples,)
      Returns class with highest probability above threshold.
      If no class exceeds threshold, returns 0 (HOLD).
    """

    def __init__(self, params: Optional[Dict[str, Dict]] = None):
        self.params = params or {}
        self.base_models: Dict = {}
        self.meta_model = None
        self.feature_names: Optional[List[str]] = None
        self.class_names = CLASS_NAMES
        # Separate LONG/SHORT detector support
        self.long_detector = None
        self.short_detector = None
        self.use_separate_detectors = False

    def _create_base_models(self) -> Dict:
        """Create multi-class base model instances."""
        import xgboost as xgb
        import lightgbm as lgb
        from catboost import CatBoostClassifier

        # XGBoost multi-class
        xgb_params = dict(self.params.get("xgboost", {}))
        xgb_params.setdefault("objective", "multi:softprob")
        xgb_params.setdefault("num_class", N_CLASSES)
        xgb_params.setdefault("eval_metric", "mlogloss")
        xgb_params.setdefault("random_state", 42)
        xgb_params.setdefault("n_estimators", 400)
        xgb_params.setdefault("max_depth", 5)
        xgb_params.setdefault("learning_rate", 0.04)
        xgb_params.setdefault("subsample", 0.8)
        xgb_params.setdefault("colsample_bytree", 0.8)
        xgb_params.setdefault("min_child_weight", 3)
        # use_label_encoder removed — deprecated in XGBoost 2.x and ignored

        # LightGBM multi-class
        lgb_params = dict(self.params.get("lightgbm", {}))
        lgb_params.setdefault("objective", "multiclass")
        lgb_params.setdefault("num_class", N_CLASSES)
        lgb_params.setdefault("metric", "multi_logloss")
        lgb_params.setdefault("random_state", 42)
        lgb_params.setdefault("verbose", -1)
        lgb_params.setdefault("n_estimators", 400)
        lgb_params.setdefault("num_leaves", 63)
        lgb_params.setdefault("learning_rate", 0.04)
        lgb_params.setdefault("subsample", 0.8)
        lgb_params.setdefault("colsample_bytree", 0.8)
        lgb_params.setdefault("min_child_samples", 20)

        # CatBoost multi-class
        cb_params = dict(self.params.get("catboost", {}))
        cb_params.setdefault("loss_function", "MultiClass")
        cb_params.setdefault("classes_count", N_CLASSES)
        cb_params.setdefault("random_seed", 42)
        cb_params.setdefault("verbose", 0)
        cb_params.setdefault("iterations", 400)
        cb_params.setdefault("depth", 6)
        cb_params.setdefault("learning_rate", 0.04)

        return {
            "xgboost": xgb.XGBClassifier(**xgb_params),
            "lightgbm": lgb.LGBMClassifier(**lgb_params),
            "catboost": CatBoostClassifier(**cb_params),
        }

    def _get_oos_proba(
        self,
        X: np.ndarray,
        y: np.ndarray,
        model_template,
        splits: List[Tuple[np.ndarray, np.ndarray]],
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Collect OOS softmax probabilities (n, 3) across walk-forward folds.

        Unlike PurgedWalkForwardCV.get_oos_predictions(), this returns the
        full predict_proba matrix (n, N_CLASSES) — not just the positive-class
        column — which is required for ternary stacking.

        Returns:
            (oos_indices, oos_proba, oos_labels)
            oos_proba shape: (n_oos, N_CLASSES)
        """
        all_indices = []
        all_proba = []
        all_true = []

        for train_idx, test_idx in splits:
            model = copy.deepcopy(model_template)
            model.fit(X[train_idx], y[train_idx])

            proba = model.predict_proba(X[test_idx])  # (n_test, ?)

            # Ensure we have exactly N_CLASSES columns
            if proba.ndim == 1 or proba.shape[1] == 1:
                # Degenerate: force to (n, 3) uniform fallback
                n_test = len(test_idx)
                padded = np.full((n_test, N_CLASSES), 1.0 / N_CLASSES)
                logger.warning(
                    f"[V5] Base model returned 1D or 1-class proba; "
                    f"using uniform fallback for {n_test} samples."
                )
                proba = padded
            elif proba.shape[1] != N_CLASSES:
                # Unexpected class count — pad or trim defensively
                n_test = len(test_idx)
                padded = np.full((n_test, N_CLASSES), 1.0 / N_CLASSES)
                cols = min(proba.shape[1], N_CLASSES)
                padded[:, :cols] = proba[:, :cols]
                logger.warning(
                    f"[V5] Base model returned {proba.shape[1]} classes, "
                    f"expected {N_CLASSES}. Padded."
                )
                proba = padded

            all_indices.extend(test_idx)
            all_proba.append(proba)
            all_true.extend(y[test_idx])

        return (
            np.array(all_indices),
            np.vstack(all_proba),  # (n_oos, N_CLASSES)
            np.array(all_true),
        )

    def train_separate_detectors(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        cv: Optional[PurgedWalkForwardCV] = None,
    ) -> Dict:
        """
        Train separate LONG and SHORT detectors using one-vs-rest stacking.

        This approach decouples the binary detection problems, which helps with
        class imbalance (e.g., 2 LONGs vs 279 SHORTs).

        Architecture:
          - LONG detector: Binary classifier (1 vs. {0, 2}) — detects LONG signals
          - SHORT detector: Binary classifier (2 vs. {0, 1}) — detects SHORT signals
          - Meta-learner: Stacks both detectors to produce final ternary (n, 3)

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target vector with values {0=HOLD, 1=LONG, 2=SHORT}
            feature_names: Feature column names
            cv: Walk-forward CV splitter

        Returns:
            dict with training metrics
        """
        self.feature_names = feature_names
        if cv is None:
            cv = PurgedWalkForwardCV()

        logger.info(f"[V5-SEPARATE] Training separate LONG/SHORT detectors (n={len(y)})")

        X_clean = np.nan_to_num(X, nan=0.0)
        splits = cv.split(len(X_clean))

        # Train LONG detector: 1 vs. (0, 2)
        logger.info("[V5-SEPARATE] Training LONG detector (binary: 1 vs rest)...")
        y_long = (y == 1).astype(int)

        import xgboost as xgb
        import lightgbm as lgb

        long_detector = lgb.LGBMClassifier(
            objective="binary",
            n_estimators=300,
            num_leaves=31,
            learning_rate=0.04,
            random_state=42,
            verbose=-1,
        )

        # Collect OOS predictions for LONG detector
        long_oos_proba = []
        long_oos_indices = None

        for train_idx, test_idx in splits:
            model = copy.deepcopy(long_detector)
            model.fit(X_clean[train_idx], y_long[train_idx])
            proba_1d = model.predict_proba(X_clean[test_idx])[:, 1]
            long_oos_proba.append(proba_1d)
            if long_oos_indices is None:
                long_oos_indices = test_idx

        long_oos_proba = np.concatenate(long_oos_proba)

        # Train SHORT detector: 2 vs. (0, 1)
        logger.info("[V5-SEPARATE] Training SHORT detector (binary: 2 vs rest)...")
        y_short = (y == 2).astype(int)

        short_detector = lgb.LGBMClassifier(
            objective="binary",
            n_estimators=300,
            num_leaves=31,
            learning_rate=0.04,
            random_state=42,
            verbose=-1,
        )

        short_oos_proba = []
        short_oos_indices = None

        for train_idx, test_idx in splits:
            model = copy.deepcopy(short_detector)
            model.fit(X_clean[train_idx], y_short[train_idx])
            proba_1d = model.predict_proba(X_clean[test_idx])[:, 1]
            short_oos_proba.append(proba_1d)
            if short_oos_indices is None:
                short_oos_indices = test_idx

        short_oos_proba = np.concatenate(short_oos_proba)

        # Stack OOS predictions from both detectors + HOLD confidence
        # HOLD confidence = 1 - max(P(LONG), P(SHORT))
        meta_X = np.column_stack([
            1.0 - np.maximum(long_oos_proba, short_oos_proba),  # P(HOLD)
            long_oos_proba,                                       # P(LONG)
            short_oos_proba,                                      # P(SHORT)
        ])
        meta_X = np.nan_to_num(meta_X, nan=1.0 / N_CLASSES)

        # Get corresponding labels
        oos_labels = y[long_oos_indices]

        # Train meta-learner (LightGBM ternary)
        logger.info("[V5-SEPARATE] Training meta-learner on stacked features...")
        self.meta_model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=N_CLASSES,
            n_estimators=150,
            num_leaves=31,
            learning_rate=0.05,
            random_state=42,
            verbose=-1,
        )
        self.meta_model.fit(meta_X, oos_labels)

        # Evaluate on OOS
        from sklearn.metrics import accuracy_score, log_loss, classification_report

        oos_pred_classes = self.meta_model.predict(meta_X)
        acc = accuracy_score(oos_labels, oos_pred_classes)
        try:
            ll = log_loss(
                oos_labels,
                self.meta_model.predict_proba(meta_X),
                labels=[0, 1, 2],
            )
        except Exception:
            ll = float("nan")

        report = classification_report(
            oos_labels,
            oos_pred_classes,
            target_names=["HOLD", "LONG", "SHORT"],
            output_dict=True,
            zero_division=0,
        )

        logger.info(f"[V5-SEPARATE] OOS accuracy: {acc:.4f}, log_loss: {ll:.4f}")
        logger.info(
            f"[V5-SEPARATE] LONG  precision={report.get('LONG',  {}).get('precision', 0):.3f} "
            f"recall={report.get('LONG',  {}).get('recall', 0):.3f} "
            f"f1={report.get('LONG',  {}).get('f1-score', 0):.3f}"
        )
        logger.info(
            f"[V5-SEPARATE] SHORT precision={report.get('SHORT', {}).get('precision', 0):.3f} "
            f"recall={report.get('SHORT', {}).get('recall', 0):.3f} "
            f"f1={report.get('SHORT', {}).get('f1-score', 0):.3f}"
        )

        # Train final detectors on ALL data
        logger.info("[V5-SEPARATE] Training final detectors on full dataset...")
        self.long_detector = copy.deepcopy(long_detector)
        self.long_detector.fit(X_clean, y_long)

        self.short_detector = copy.deepcopy(short_detector)
        self.short_detector.fit(X_clean, y_short)

        # Store that we're using separate detectors
        self.use_separate_detectors = True

        metrics = {
            "oos_accuracy": float(acc),
            "oos_log_loss": float(ll) if not np.isnan(ll) else None,
            "long_precision": float(report.get("LONG", {}).get("precision", 0)),
            "long_recall": float(report.get("LONG", {}).get("recall", 0)),
            "long_f1": float(report.get("LONG", {}).get("f1-score", 0)),
            "short_precision": float(report.get("SHORT", {}).get("precision", 0)),
            "short_recall": float(report.get("SHORT", {}).get("recall", 0)),
            "short_f1": float(report.get("SHORT", {}).get("f1-score", 0)),
            "hold_f1": float(report.get("HOLD", {}).get("f1-score", 0)),
            "training_mode": "separate_detectors",
        }
        logger.info(f"[V5-SEPARATE] Training complete: {metrics}")
        return metrics

    def train(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        cv: Optional[PurgedWalkForwardCV] = None,
        sample_weight: Optional[np.ndarray] = None,
    ) -> Dict:
        """
        Train ternary ensemble with walk-forward CV stacking.

        Args:
            X: Feature matrix (n_samples, n_features)
            y: Target vector with values {0, 1, 2}
            feature_names: Feature column names
            cv: Walk-forward CV splitter
            sample_weight: Optional per-sample weights (from get_class_weights)

        Returns:
            dict with training metrics (accuracy per class, log_loss)
        """
        self.feature_names = feature_names
        if cv is None:
            cv = PurgedWalkForwardCV()

        # Validate classes
        unique_classes = np.unique(y[~np.isnan(y.astype(float))])
        logger.info(f"[V5] Training on classes: {unique_classes}, samples: {len(y)}")

        models = self._create_base_models()
        X_clean = np.nan_to_num(X, nan=0.0)

        # Pre-compute splits once — all base models share the same folds
        splits = cv.split(len(X_clean))

        # Collect OOS predictions (shape: (n_oos, 3) per model)
        oos_preds: Dict[str, np.ndarray] = {}
        oos_indices = None
        oos_labels = None

        for name, model_template in models.items():
            logger.info(f"  [V5] OOS walk-forward for {name}...")
            indices, proba, true_labels = self._get_oos_proba(
                X_clean, y, model_template, splits
            )
            oos_preds[name] = proba  # (n_oos, 3)

            if oos_indices is None:
                oos_indices = indices
                oos_labels = true_labels

        # Stack OOS predictions: (n_oos, 9) — 3 probs × 3 models
        meta_X = np.hstack([oos_preds[name] for name in models.keys()])
        meta_X = np.nan_to_num(meta_X, nan=1.0 / N_CLASSES)

        # Train meta-learner (LightGBM ternary)
        logger.info("[V5] Training meta-learner (LightGBM ternary)...")
        import lightgbm as lgb

        self.meta_model = lgb.LGBMClassifier(
            objective="multiclass",
            num_class=N_CLASSES,
            n_estimators=150,
            num_leaves=31,
            learning_rate=0.05,
            random_state=42,
            verbose=-1,
        )
        self.meta_model.fit(meta_X, oos_labels)

        # Evaluate on OOS
        from sklearn.metrics import accuracy_score, log_loss, classification_report

        oos_pred_classes = self.meta_model.predict(meta_X)
        acc = accuracy_score(oos_labels, oos_pred_classes)
        try:
            ll = log_loss(
                oos_labels,
                self.meta_model.predict_proba(meta_X),
                labels=[0, 1, 2],
            )
        except Exception:
            ll = float("nan")

        report = classification_report(
            oos_labels,
            oos_pred_classes,
            target_names=["HOLD", "LONG", "SHORT"],
            output_dict=True,
            zero_division=0,
        )
        logger.info(f"[V5] OOS accuracy: {acc:.4f}, log_loss: {ll:.4f}")
        logger.info(
            f"[V5] LONG  precision={report.get('LONG',  {}).get('precision', 0):.3f} "
            f"recall={report.get('LONG',  {}).get('recall', 0):.3f} "
            f"f1={report.get('LONG',  {}).get('f1-score', 0):.3f}"
        )
        logger.info(
            f"[V5] SHORT precision={report.get('SHORT', {}).get('precision', 0):.3f} "
            f"recall={report.get('SHORT', {}).get('recall', 0):.3f} "
            f"f1={report.get('SHORT', {}).get('f1-score', 0):.3f}"
        )

        # Train final base models on ALL data
        logger.info("[V5] Training final base models on full dataset...")
        for name, model_template in models.items():
            model = copy.deepcopy(model_template)
            if sample_weight is not None:
                try:
                    model.fit(X_clean, y, sample_weight=sample_weight)
                except TypeError:
                    model.fit(X_clean, y)
            else:
                model.fit(X_clean, y)
            self.base_models[name] = model

        metrics = {
            "oos_accuracy": float(acc),
            "oos_log_loss": float(ll) if not np.isnan(ll) else None,
            "long_precision": float(report.get("LONG", {}).get("precision", 0)),
            "long_recall": float(report.get("LONG", {}).get("recall", 0)),
            "long_f1": float(report.get("LONG", {}).get("f1-score", 0)),
            "short_precision": float(report.get("SHORT", {}).get("precision", 0)),
            "short_recall": float(report.get("SHORT", {}).get("recall", 0)),
            "short_f1": float(report.get("SHORT", {}).get("f1-score", 0)),
            "hold_f1": float(report.get("HOLD", {}).get("f1-score", 0)),
        }
        logger.info(f"[V5] Training complete: {metrics}")
        return metrics

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """
        Get ternary prediction probabilities.

        If trained with separate LONG/SHORT detectors, uses those.
        Otherwise, uses base model ensemble.

        Returns:
            Array of shape (n_samples, 3):
              col 0: P(HOLD), col 1: P(LONG), col 2: P(SHORT)
        """
        X_clean = np.nan_to_num(X, nan=0.0)

        # If using separate detectors, use them
        if self.use_separate_detectors and self.long_detector is not None and self.short_detector is not None:
            p_long = self.long_detector.predict_proba(X_clean)[:, 1]
            p_short = self.short_detector.predict_proba(X_clean)[:, 1]
            p_hold = 1.0 - np.maximum(p_long, p_short)

            # Stack and pass through meta-learner if available
            meta_X = np.column_stack([p_hold, p_long, p_short])
            meta_X = np.nan_to_num(meta_X, nan=1.0 / N_CLASSES)

            if self.meta_model is not None:
                return self.meta_model.predict_proba(meta_X)
            else:
                return meta_X

        # Otherwise use base model ensemble
        if not self.base_models:
            logger.error("[V5] No base models loaded — returning uniform probabilities")
            return np.full((len(X), N_CLASSES), 1.0 / N_CLASSES)

        # Get base model softmax probabilities
        base_preds = {}
        for name, model in self.base_models.items():
            proba = model.predict_proba(X_clean)  # (n, 3)
            if proba.ndim == 1 or proba.shape[1] != N_CLASSES:
                padded = np.full((len(X), N_CLASSES), 1.0 / N_CLASSES)
                if proba.ndim == 2:
                    cols = min(proba.shape[1], N_CLASSES)
                    padded[:, :cols] = proba[:, :cols]
                proba = padded
            base_preds[name] = proba

        # Stack as meta features
        meta_X = np.hstack(list(base_preds.values()))  # (n, 9)
        meta_X = np.nan_to_num(meta_X, nan=1.0 / N_CLASSES)

        if self.meta_model is not None:
            proba_3 = self.meta_model.predict_proba(meta_X)  # (n, 3)
        else:
            # Fallback: average base models
            proba_3 = np.mean(
                np.stack(list(base_preds.values()), axis=0), axis=0
            )

        return proba_3

    def predict(
        self,
        X: np.ndarray,
        long_threshold: float = 0.35,
        short_threshold: float = 0.35,
    ) -> np.ndarray:
        """
        Get class predictions with confidence thresholds.

        Args:
            X: Feature matrix
            long_threshold: Minimum P(LONG) to emit LONG signal
            short_threshold: Minimum P(SHORT) to emit SHORT signal

        Returns:
            Array of {0=HOLD, 1=LONG, 2=SHORT}
        """
        proba = self.predict_proba(X)  # (n, 3)
        p_long = proba[:, 1]
        p_short = proba[:, 2]

        predictions = np.zeros(len(X), dtype=int)

        # LONG: P(LONG) >= threshold AND P(LONG) >= P(SHORT)
        long_mask = (p_long >= long_threshold) & (p_long >= p_short)
        predictions[long_mask] = 1

        # SHORT: P(SHORT) >= threshold AND P(SHORT) > P(LONG) AND not already LONG
        short_mask = (
            (p_short >= short_threshold)
            & (p_short > p_long)
            & (predictions != 1)
        )
        predictions[short_mask] = 2

        return predictions

    def get_signal(
        self,
        proba_row: np.ndarray,
        long_threshold: float = 0.35,
        short_threshold: float = 0.35,
    ) -> Tuple[int, str, float]:
        """
        Get signal for a single prediction row.

        Returns:
            Tuple of (class, signal_name, confidence)
            class: 0=HOLD, 1=LONG, 2=SHORT
            signal_name: 'HOLD', 'LONG', 'SHORT'
            confidence: probability of the predicted class
        """
        p_hold, p_long, p_short = (
            float(proba_row[0]),
            float(proba_row[1]),
            float(proba_row[2]),
        )

        if p_long >= long_threshold and p_long >= p_short:
            return 1, "LONG", p_long
        elif p_short >= short_threshold and p_short > p_long:
            return 2, "SHORT", p_short
        else:
            return 0, "HOLD", p_hold

    def get_base_predictions(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        """Get individual base model softmax probabilities (n, 3) for analysis."""
        X_clean = np.nan_to_num(X, nan=0.0)
        result = {}
        for name, model in self.base_models.items():
            result[name] = model.predict_proba(X_clean)
        return result

    def save(self, directory: str):
        """Save all models to directory."""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)

        # Save base models (multiclass ensemble)
        for name, model in self.base_models.items():
            with open(path / f"v5_base_{name}.pkl", "wb") as f:
                pickle.dump(model, f)

        # Save separate detectors if they exist
        if self.long_detector is not None:
            with open(path / "v5_long_detector.pkl", "wb") as f:
                pickle.dump(self.long_detector, f)

        if self.short_detector is not None:
            with open(path / "v5_short_detector.pkl", "wb") as f:
                pickle.dump(self.short_detector, f)

        # Save meta-learner
        if self.meta_model is not None:
            with open(path / "v5_meta_learner.pkl", "wb") as f:
                pickle.dump(self.meta_model, f)

        metadata = {
            "version": "v5",
            "n_classes": N_CLASSES,
            "class_names": CLASS_NAMES,
            "base_models": list(self.base_models.keys()),
            "feature_names": self.feature_names,
            "params": self.params,
            "use_separate_detectors": self.use_separate_detectors,
        }
        with open(path / "v5_ensemble_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"[V5] Ensemble saved to {path}")

    def load(self, directory: str):
        """Load all models from directory."""
        path = Path(directory)

        with open(path / "v5_ensemble_metadata.json") as f:
            metadata = json.load(f)
        self.feature_names = metadata.get("feature_names")
        self.params = metadata.get("params", {})
        self.use_separate_detectors = metadata.get("use_separate_detectors", False)

        # Load base models (multiclass ensemble)
        for name in metadata.get("base_models", []):
            model_path = path / f"v5_base_{name}.pkl"
            if model_path.exists():
                with open(model_path, "rb") as f:
                    self.base_models[name] = pickle.load(f)

        # Load separate detectors if they exist
        long_path = path / "v5_long_detector.pkl"
        if long_path.exists():
            with open(long_path, "rb") as f:
                self.long_detector = pickle.load(f)

        short_path = path / "v5_short_detector.pkl"
        if short_path.exists():
            with open(short_path, "rb") as f:
                self.short_detector = pickle.load(f)

        # Load meta-learner
        meta_path = path / "v5_meta_learner.pkl"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                self.meta_model = pickle.load(f)

        logger.info(f"[V5] Ensemble loaded: separate_detectors={self.use_separate_detectors}, base_models={list(self.base_models.keys())}")
