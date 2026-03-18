"""
HYPERPARAMETER OPTIMIZATION
=============================
Optuna TPE sampler with walk-forward CV objective.
Optimizes: XGBoost, LightGBM, CatBoost.
Objective: Walk-forward CV average score (not accuracy!).
"""

import json
import numpy as np
from pathlib import Path
from typing import Dict, Callable, Optional
from loguru import logger

try:
    import optuna
    optuna.logging.set_verbosity(optuna.logging.WARNING)
except ImportError:
    optuna = None


class HyperOptimizer:
    """
    Optuna-based hyperparameter optimization for ensemble base learners.
    """

    def __init__(self, n_trials: int = 100, cv_splitter=None, metric_fn=None):
        """
        Args:
            n_trials: Number of Optuna trials per model
            cv_splitter: PurgedWalkForwardCV instance
            metric_fn: Callable(y_true, y_pred_proba) → float (higher is better)
        """
        if optuna is None:
            raise ImportError("optuna is required: pip install optuna")
        self.n_trials = n_trials
        self.cv_splitter = cv_splitter
        self.metric_fn = metric_fn
        self.best_params: Dict[str, Dict] = {}

    def optimize_xgboost(self, X: np.ndarray, y: np.ndarray) -> Dict:
        """Optimize XGBoost hyperparameters"""
        import xgboost as xgb

        def objective(trial):
            params = {
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "subsample": trial.suggest_float("subsample", 0.6, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
                "gamma": trial.suggest_float("gamma", 0, 5),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10, log=True),
                "use_label_encoder": False,
                "eval_metric": "logloss",
                "random_state": 42,
            }

            def model_factory():
                return xgb.XGBClassifier(**params)

            result = self.cv_splitter.cross_validate(X, y, model_factory, self.metric_fn)
            return result["mean_score"]

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=True)

        self.best_params["xgboost"] = study.best_params
        logger.info(f"XGBoost best score: {study.best_value:.4f}")
        return study.best_params

    def optimize_lightgbm(self, X: np.ndarray, y: np.ndarray) -> Dict:
        """Optimize LightGBM hyperparameters"""
        import lightgbm as lgb

        def objective(trial):
            params = {
                "num_leaves": trial.suggest_int("num_leaves", 31, 127),
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "n_estimators": trial.suggest_int("n_estimators", 100, 500),
                "min_child_samples": trial.suggest_int("min_child_samples", 10, 50),
                "feature_fraction": trial.suggest_float("feature_fraction", 0.6, 1.0),
                "bagging_fraction": trial.suggest_float("bagging_fraction", 0.6, 1.0),
                "bagging_freq": trial.suggest_int("bagging_freq", 1, 7),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-8, 10, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-8, 10, log=True),
                "random_state": 42,
                "verbose": -1,
            }

            def model_factory():
                return lgb.LGBMClassifier(**params)

            result = self.cv_splitter.cross_validate(X, y, model_factory, self.metric_fn)
            return result["mean_score"]

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=True)

        self.best_params["lightgbm"] = study.best_params
        logger.info(f"LightGBM best score: {study.best_value:.4f}")
        return study.best_params

    def optimize_catboost(self, X: np.ndarray, y: np.ndarray) -> Dict:
        """Optimize CatBoost hyperparameters"""
        from catboost import CatBoostClassifier

        def objective(trial):
            params = {
                "depth": trial.suggest_int("depth", 4, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "iterations": trial.suggest_int("iterations", 200, 600),
                "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1, 10),
                "bagging_temperature": trial.suggest_float("bagging_temperature", 0, 10),
                "random_strength": trial.suggest_float("random_strength", 0, 10),
                "border_count": trial.suggest_int("border_count", 32, 255),
                "random_seed": 42,
                "verbose": 0,
            }

            def model_factory():
                return CatBoostClassifier(**params)

            result = self.cv_splitter.cross_validate(X, y, model_factory, self.metric_fn)
            return result["mean_score"]

        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=42))
        study.optimize(objective, n_trials=self.n_trials, show_progress_bar=True)

        self.best_params["catboost"] = study.best_params
        logger.info(f"CatBoost best score: {study.best_value:.4f}")
        return study.best_params

    def optimize_all(self, X: np.ndarray, y: np.ndarray) -> Dict[str, Dict]:
        """Optimize all three models"""
        logger.info(f"Starting hyperparameter optimization ({self.n_trials} trials per model)...")
        self.optimize_xgboost(X, y)
        self.optimize_lightgbm(X, y)
        self.optimize_catboost(X, y)
        return self.best_params

    def save_params(self, output_path: str):
        """Save best parameters to JSON"""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.best_params, f, indent=2)
        logger.info(f"Saved best params to {path}")

    def load_params(self, input_path: str) -> Dict[str, Dict]:
        """Load best parameters from JSON"""
        with open(input_path) as f:
            self.best_params = json.load(f)
        logger.info(f"Loaded params for {list(self.best_params.keys())}")
        return self.best_params
