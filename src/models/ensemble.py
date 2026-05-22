"""
ENSEMBLE STACKING MODEL
=========================
Base learners (Level 0): XGBoost, LightGBM, CatBoost
Meta-learner (Level 1): LogisticRegression on OOS predictions + regime state
"""

import json
import pickle
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger

from src.models.validation import PurgedWalkForwardCV


class EnsembleModel:
    """
    Stacked ensemble: 3 tree-based base learners + logistic regression meta-learner.
    """

    def __init__(self, params: Optional[Dict[str, Dict]] = None):
        """
        Args:
            params: Dict with keys 'xgboost', 'lightgbm', 'catboost' → hyperparams
        """
        self.params = params or {}
        self.base_models = {}
        self.meta_model = None
        self.feature_names: Optional[List[str]] = None

    def _create_base_models(self) -> Dict:
        """Create base model instances with given params"""
        import xgboost as xgb
        import lightgbm as lgb
        from catboost import CatBoostClassifier

        xgb_params = self.params.get("xgboost", {})
        xgb_params.setdefault("use_label_encoder", False)
        xgb_params.setdefault("eval_metric", "logloss")
        xgb_params.setdefault("random_state", 42)
        xgb_params.setdefault("n_estimators", 300)
        xgb_params.setdefault("max_depth", 5)
        xgb_params.setdefault("learning_rate", 0.05)

        lgb_params = self.params.get("lightgbm", {})
        lgb_params.setdefault("random_state", 42)
        lgb_params.setdefault("verbose", -1)
        lgb_params.setdefault("n_estimators", 300)
        lgb_params.setdefault("num_leaves", 63)
        lgb_params.setdefault("learning_rate", 0.05)

        cb_params = self.params.get("catboost", {})
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
        regime_features: Optional[np.ndarray] = None,
    ):
        """
        Train ensemble with walk-forward CV stacking.

        Args:
            X: Feature matrix
            y: Target vector
            feature_names: Feature names
            cv: Walk-forward CV splitter
            regime_features: Optional regime state array for meta-learner input
        """
        self.feature_names = feature_names
        if cv is None:
            cv = PurgedWalkForwardCV()

        logger.info("Training ensemble base models...")

        # Collect OOS predictions for meta-learner
        oos_predictions = {}
        oos_indices = None
        oos_labels = None

        models = self._create_base_models()

        for name, model_template in models.items():
            logger.info(f"  Training {name} with walk-forward CV...")

            def model_factory(m=model_template):
                import copy
                return copy.deepcopy(m)

            indices, preds, true_labels = cv.get_oos_predictions(X, y, model_factory)
            oos_predictions[name] = preds

            if oos_indices is None:
                oos_indices = indices
                oos_labels = true_labels

        # Stack OOS predictions as meta-features
        meta_X = np.column_stack([oos_predictions[name] for name in models.keys()])

        # Add regime features to meta-learner if available
        if regime_features is not None and oos_indices is not None:
            regime_oos = regime_features[oos_indices]
            if regime_oos.ndim == 1:
                regime_oos = regime_oos.reshape(-1, 1)
            meta_X = np.column_stack([meta_X, regime_oos])

        # Handle NaN in meta features
        meta_X = np.nan_to_num(meta_X, nan=0.5)

        # Train meta-learner (LightGBM captures non-linear interactions between base models)
        logger.info("Training meta-learner (LGBMClassifier)...")
        import lightgbm as lgb
        self.meta_model = lgb.LGBMClassifier(
            n_estimators=100,
            num_leaves=15,
            learning_rate=0.05,
            random_state=42,
            verbose=-1,
        )
        self.meta_model.fit(meta_X, oos_labels)

        # Train final base models on ALL data
        logger.info("Training final base models on full dataset...")
        X_clean = np.nan_to_num(X, nan=0.0)
        for name, model_template in models.items():
            import copy
            model = copy.deepcopy(model_template)
            model.fit(X_clean, y)
            self.base_models[name] = model

        logger.info(f"Ensemble trained: {list(self.base_models.keys())} + meta-learner")

    def predict_proba(
        self,
        X: np.ndarray,
        regime_features: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """
        Get ensemble prediction probabilities.

        Args:
            X: Feature matrix
            regime_features: Optional regime state

        Returns:
            Array of probabilities for positive class
        """
        X_clean = np.nan_to_num(X, nan=0.0)

        # Get base model predictions
        base_preds = {}
        for name, model in self.base_models.items():
            if hasattr(model, "predict_proba"):
                base_preds[name] = model.predict_proba(X_clean)[:, 1]
            else:
                base_preds[name] = model.predict(X_clean)

        # If meta-model not available, average base predictions
        if self.meta_model is None:
            preds = np.column_stack(list(base_preds.values()))
            return preds.mean(axis=1)

        # Stack as meta-features
        meta_X = np.column_stack(list(base_preds.values()))

        if regime_features is not None:
            if regime_features.ndim == 1:
                regime_features = regime_features.reshape(-1, 1)
            meta_X = np.column_stack([meta_X, regime_features])

        meta_X = np.nan_to_num(meta_X, nan=0.5)

        return self.meta_model.predict_proba(meta_X)[:, 1]

    def predict(
        self,
        X: np.ndarray,
        threshold: float = 0.5,
        regime_features: Optional[np.ndarray] = None,
    ) -> np.ndarray:
        """Get binary predictions"""
        proba = self.predict_proba(X, regime_features)
        return (proba >= threshold).astype(int)

    def get_base_predictions(self, X: np.ndarray) -> Dict[str, np.ndarray]:
        """Get individual base model predictions (for analysis)"""
        X_clean = np.nan_to_num(X, nan=0.0)
        result = {}
        for name, model in self.base_models.items():
            if hasattr(model, "predict_proba"):
                result[name] = model.predict_proba(X_clean)[:, 1]
            else:
                result[name] = model.predict(X_clean)
        return result

    def save(self, directory: str):
        """Save all models to directory"""
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)

        # Save base models
        for name, model in self.base_models.items():
            model_path = path / f"base_{name}.pkl"
            with open(model_path, "wb") as f:
                pickle.dump(model, f)

        # Save meta-learner
        if self.meta_model:
            with open(path / "meta_learner.pkl", "wb") as f:
                pickle.dump(self.meta_model, f)

        # Save metadata
        metadata = {
            "base_models": list(self.base_models.keys()),
            "feature_names": self.feature_names,
            "params": self.params,
        }
        with open(path / "ensemble_metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"Ensemble saved to {path}")

    def load(self, directory: str):
        """Load all models from directory"""
        path = Path(directory)

        # Load metadata
        with open(path / "ensemble_metadata.json") as f:
            metadata = json.load(f)
        self.feature_names = metadata.get("feature_names")
        self.params = metadata.get("params", {})

        # Load base models
        for name in metadata["base_models"]:
            model_path = path / f"base_{name}.pkl"
            with open(model_path, "rb") as f:
                self.base_models[name] = pickle.load(f)

        # Load meta-learner
        meta_path = path / "meta_learner.pkl"
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                self.meta_model = pickle.load(f)
            # Fix sklearn version compatibility (multi_class removed in 1.6+)
            if hasattr(self.meta_model, '__class__') and not hasattr(self.meta_model, 'multi_class'):
                self.meta_model.multi_class = 'auto'

        logger.info(f"Ensemble loaded: {list(self.base_models.keys())}")
