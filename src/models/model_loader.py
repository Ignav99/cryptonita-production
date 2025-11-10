"""
MODEL LOADER
============
Loads and manages the XGBoost model V3
"""

import json
import xgboost as xgb
from pathlib import Path
from typing import Optional
from loguru import logger


class ModelLoader:
    """
    Loads XGBoost models from JSON format
    """

    def __init__(self, model_path: str):
        """
        Initialize model loader

        Args:
            model_path: Path to model JSON file
        """
        self.model_path = Path(model_path)
        self.model: Optional[xgb.Booster] = None
        self.feature_names: Optional[list] = None

    def load_model(self) -> xgb.Booster:
        """
        Load XGBoost model from JSON file

        Returns:
            Loaded XGBoost Booster model
        """
        try:
            if not self.model_path.exists():
                raise FileNotFoundError(f"Model file not found: {self.model_path}")

            logger.info(f"📦 Loading model from {self.model_path}")

            # Load XGBoost model from JSON
            self.model = xgb.Booster()
            self.model.load_model(str(self.model_path))

            # Get feature names from the model
            self.feature_names = self.model.feature_names

            logger.success(f"✅ Model loaded successfully - Features: {len(self.feature_names)}")
            return self.model

        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            raise

    def get_model(self) -> xgb.Booster:
        """
        Get loaded model (loads if not already loaded)

        Returns:
            XGBoost model
        """
        if self.model is None:
            self.load_model()
        return self.model

    def predict(self, features: xgb.DMatrix) -> float:
        """
        Make prediction using the loaded model

        Args:
            features: Feature matrix (DMatrix format)

        Returns:
            Prediction probability (0-1)
        """
        if self.model is None:
            raise ValueError("Model not loaded. Call load_model() first.")

        try:
            predictions = self.model.predict(features)
            # Return probability for positive class
            return float(predictions[0])

        except Exception as e:
            logger.error(f"❌ Prediction failed: {e}")
            raise

    def get_feature_names(self) -> list:
        """Get feature names from model"""
        if self.model is None:
            self.load_model()
        return self.feature_names or []
