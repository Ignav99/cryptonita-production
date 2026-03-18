"""
FEATURE SELECTION
==================
Two-stage selection:
1. SHAP TreeExplainer → rank features by mean |SHAP|
2. Boruta → statistical test confirming features outperform shadow features
Keep only features passing BOTH filters.
"""

import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import List, Tuple, Optional
from loguru import logger


class FeatureSelector:
    """
    Two-stage feature selection: SHAP + Boruta.
    """

    def __init__(self, min_features: int = 20, max_features: int = 60):
        self.min_features = min_features
        self.max_features = max_features
        self.selected_features: Optional[List[str]] = None
        self.shap_importance: Optional[pd.DataFrame] = None

    def select_features(
        self,
        X: pd.DataFrame,
        y: np.ndarray,
        feature_names: List[str],
        model=None,
    ) -> List[str]:
        """
        Run two-stage feature selection.

        Args:
            X: Feature DataFrame
            y: Target vector
            feature_names: List of feature names
            model: Trained tree model for SHAP (if None, trains XGBoost)

        Returns:
            List of selected feature names
        """
        logger.info(f"Starting feature selection on {len(feature_names)} features...")

        # Stage 1: SHAP importance
        shap_selected = self._shap_selection(X, y, feature_names, model)
        logger.info(f"SHAP selected {len(shap_selected)} features")

        # Stage 2: Boruta
        boruta_selected = self._boruta_selection(X, y, feature_names)
        logger.info(f"Boruta selected {len(boruta_selected)} features")

        # Intersection: features passing BOTH filters
        both = list(set(shap_selected) & set(boruta_selected))

        # Ensure minimum features
        if len(both) < self.min_features:
            logger.warning(f"Only {len(both)} features in intersection, adding top SHAP features")
            # Add top SHAP features until we reach minimum
            for feat in shap_selected:
                if feat not in both:
                    both.append(feat)
                if len(both) >= self.min_features:
                    break

        # Cap at max
        both = both[:self.max_features]

        # Preserve original order
        self.selected_features = [f for f in feature_names if f in both]

        logger.info(f"Final selection: {len(self.selected_features)} features")
        return self.selected_features

    def _shap_selection(
        self,
        X: pd.DataFrame,
        y: np.ndarray,
        feature_names: List[str],
        model=None,
    ) -> List[str]:
        """Select features using SHAP TreeExplainer"""
        try:
            import shap
            import xgboost as xgb

            if model is None:
                model = xgb.XGBClassifier(
                    n_estimators=200, max_depth=5, learning_rate=0.1,
                    use_label_encoder=False, eval_metric="logloss",
                    random_state=42
                )
                # Handle NaN for training
                X_clean = pd.DataFrame(X, columns=feature_names).fillna(0)
                model.fit(X_clean, y)
                explainer = shap.TreeExplainer(model)
                shap_values = explainer.shap_values(X_clean)
            else:
                X_clean = pd.DataFrame(X, columns=feature_names).fillna(0)
                explainer = shap.TreeExplainer(model)
                shap_values = explainer.shap_values(X_clean)

            # Mean absolute SHAP value per feature
            if isinstance(shap_values, list):
                shap_values = shap_values[1]  # For binary classification
            mean_shap = np.abs(shap_values).mean(axis=0)

            importance_df = pd.DataFrame({
                "feature": feature_names,
                "shap_importance": mean_shap,
            }).sort_values("shap_importance", ascending=False)

            self.shap_importance = importance_df

            # Select features with importance > median
            threshold = importance_df["shap_importance"].median()
            selected = importance_df[importance_df["shap_importance"] > threshold]["feature"].tolist()

            return selected[:self.max_features]

        except Exception as e:
            logger.error(f"SHAP selection failed: {e}")
            return feature_names  # Fall back to all features

    def _boruta_selection(
        self,
        X: pd.DataFrame,
        y: np.ndarray,
        feature_names: List[str],
    ) -> List[str]:
        """Select features using Boruta algorithm"""
        try:
            from boruta import BorutaPy
            from sklearn.ensemble import RandomForestClassifier

            X_clean = pd.DataFrame(X, columns=feature_names).fillna(0).values

            rf = RandomForestClassifier(
                n_estimators=100, max_depth=5, n_jobs=-1, random_state=42
            )

            boruta = BorutaPy(
                rf, n_estimators="auto", verbose=0, random_state=42, max_iter=100
            )
            boruta.fit(X_clean, y)

            selected = [
                feature_names[i]
                for i in range(len(feature_names))
                if boruta.support_[i]
            ]

            # Also include tentative features
            tentative = [
                feature_names[i]
                for i in range(len(feature_names))
                if boruta.support_weak_[i] and feature_names[i] not in selected
            ]
            selected.extend(tentative)

            return selected

        except Exception as e:
            logger.error(f"Boruta selection failed: {e}")
            return feature_names

    def save_selection(self, config_path: str):
        """Save selected features to JSON config"""
        if self.selected_features is None:
            logger.warning("No features selected yet")
            return

        path = Path(config_path)
        try:
            with open(path) as f:
                config = json.load(f)
        except FileNotFoundError:
            config = {}

        config["selected_features"] = self.selected_features
        config["selection_method"] = "SHAP + Boruta"
        config["n_selected"] = len(self.selected_features)

        if self.shap_importance is not None:
            config["shap_top_20"] = (
                self.shap_importance.head(20)
                .set_index("feature")["shap_importance"]
                .to_dict()
            )

        with open(path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Saved {len(self.selected_features)} selected features to {path}")
