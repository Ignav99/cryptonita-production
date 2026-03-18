"""
TRADING PREDICTOR V4
=====================
Drop-in replacement for TradingPredictor (V3).
Uses ensemble stacking (XGBoost + LightGBM + CatBoost), regime detection,
and Kelly position sizing.

Same interface: predict_single, predict_multiple, should_trade, calculate_position_size
"""

import asyncio
import threading
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, Optional, Tuple
from loguru import logger

from config import settings
from src.data.features_v4 import FeatureEngineerV4
from src.data.macro_data import MacroDataFetcher
from src.data.derivatives_fetcher import DerivativesFetcher
from src.data.onchain_fetcher import OnChainFetcher
from src.data.sentiment_fetcher import SentimentFetcher
from src.data.defi_fetcher import DeFiFetcher
from src.models.ensemble import EnsembleModel
from src.models.regime_detector import RegimeDetector
from src.models.position_sizer import KellyPositionSizer


class TradingPredictorV4:
    """
    V4 Trading Predictor with ensemble model, regime detection, and Kelly sizing.
    Drop-in replacement for TradingPredictor (V3).
    """

    def __init__(self):
        model_dir = getattr(settings, "V4_MODEL_DIR", "PRODUCTION_SYSTEM/models/v4")
        self.model_dir = Path(model_dir)
        self._lock = threading.Lock()
        self._needs_reload = False
        self._active_version = None

        # Try loading from DB first, fall back to filesystem
        self.ensemble = EnsembleModel()
        self.regime_detector = RegimeDetector()
        self._load_models()

        # Initialize feature engineer
        self.feature_engineer = FeatureEngineerV4()

        # Initialize data fetchers
        self.macro_fetcher = MacroDataFetcher()
        self.derivatives_fetcher = DerivativesFetcher()
        self.onchain_fetcher = OnChainFetcher()
        self.sentiment_fetcher = SentimentFetcher()
        self.defi_fetcher = DeFiFetcher()

        # Initialize position sizer
        kelly_fraction = getattr(settings, "KELLY_FRACTION", 0.25)
        self.position_sizer = KellyPositionSizer(kelly_fraction=kelly_fraction)

        # Trading parameters
        self.threshold = settings.PREDICTION_THRESHOLD

        # Cache for external data (refreshed each scan cycle)
        self._cached_external = None
        self._cached_regime = None

        logger.info(f"TradingPredictorV4 initialized — Threshold: {self.threshold}")

    def _load_models(self):
        """Load models: try DB first, then filesystem."""
        loaded = False

        # Try loading from DB
        try:
            from src.models.model_store import ModelStore
            store = ModelStore()
            if store.has_active_model():
                self.model_dir.mkdir(parents=True, exist_ok=True)
                version = store.load_active_ensemble(str(self.model_dir))
                if version is not None:
                    self.ensemble.load(str(self.model_dir))
                    regime_path = self.model_dir / "regime_detector.pkl"
                    if regime_path.exists():
                        self.regime_detector.load(str(regime_path))
                    self._active_version = version
                    loaded = True
                    logger.info(f"Loaded V4 model v{version} from DB")
        except Exception as e:
            logger.warning(f"Failed to load model from DB: {e}")

        # Fall back to filesystem
        if not loaded:
            try:
                if (self.model_dir / "ensemble_metadata.json").exists():
                    self.ensemble.load(str(self.model_dir))
                    regime_path = self.model_dir / "regime_detector.pkl"
                    if regime_path.exists():
                        self.regime_detector.load(str(regime_path))
                    loaded = True
                    logger.info("Loaded V4 model from filesystem (fallback)")
            except Exception as e:
                logger.error(f"Failed to load V4 model from filesystem: {e}")

        if not loaded:
            logger.error("No V4 model available — predictions will return HOLD")

    def reload_model(self):
        """Reload model from DB after auto-training promotes a new version. Thread-safe."""
        with self._lock:
            try:
                from src.models.model_store import ModelStore
                store = ModelStore()

                new_ensemble = EnsembleModel()
                new_regime = RegimeDetector()

                self.model_dir.mkdir(parents=True, exist_ok=True)
                version = store.load_active_ensemble(str(self.model_dir))
                if version is None:
                    logger.warning("reload_model: no active model in DB")
                    return

                new_ensemble.load(str(self.model_dir))
                regime_path = self.model_dir / "regime_detector.pkl"
                if regime_path.exists():
                    new_regime.load(str(regime_path))

                # Atomic swap
                self.ensemble = new_ensemble
                self.regime_detector = new_regime
                self._active_version = version
                self._needs_reload = False
                logger.success(f"Hot-reloaded V4 model v{version}")

            except Exception as e:
                logger.error(f"Failed to reload model: {e}")

    def request_reload(self):
        """Flag that a reload is needed (called by auto-trainer after promotion)."""
        self._needs_reload = True

    async def _fetch_external_data(self) -> Dict[str, Dict]:
        """Fetch all external data sources concurrently"""
        macro, derivatives, onchain, sentiment, defi = await asyncio.gather(
            self.macro_fetcher.get_all_macro_data(),
            self.derivatives_fetcher.get_all_derivatives_data(),
            self.onchain_fetcher.get_all_onchain_data(),
            self.sentiment_fetcher.get_all_sentiment_data(),
            self.defi_fetcher.get_all_defi_data(),
            return_exceptions=True,
        )

        return {
            "macro": macro if isinstance(macro, dict) else {},
            "derivatives": derivatives if isinstance(derivatives, dict) else {},
            "onchain": onchain if isinstance(onchain, dict) else {},
            "sentiment": sentiment if isinstance(sentiment, dict) else {},
            "defi": defi if isinstance(defi, dict) else {},
        }

    def _fetch_external_data_sync(self) -> Dict[str, Dict]:
        """Sync wrapper for external data fetch"""
        import concurrent.futures

        def _run():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._fetch_external_data())
            finally:
                loop.close()

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_run).result(timeout=60)
        except RuntimeError:
            return asyncio.run(self._fetch_external_data())

    def predict_single(
        self,
        ticker: str,
        ohlcv_data: pd.DataFrame,
        btc_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None,
    ) -> Tuple[int, float, Dict]:
        """
        Make V4 prediction for a single ticker.
        Same interface as TradingPredictor.predict_single.

        Returns:
            Tuple of (prediction, probability, features_dict)
        """
        try:
            # Get or refresh external data
            if self._cached_external is None:
                self._cached_external = self._fetch_external_data_sync()

            ext = self._cached_external

            # Use provided macro_data or cached
            if macro_data:
                ext["macro"] = macro_data

            # Get regime data
            if btc_data is not None and self.regime_detector.model is not None:
                self._cached_regime = self.regime_detector.predict(btc_data)

            # Calculate V4 features
            feature_vector = self.feature_engineer.calculate_single_prediction_features_v4(
                ticker_data=ohlcv_data,
                btc_data=btc_data,
                macro_data=ext.get("macro"),
                derivatives_data=ext.get("derivatives"),
                onchain_data=ext.get("onchain"),
                sentiment_data=ext.get("sentiment"),
                defi_data=ext.get("defi"),
                regime_data=self._cached_regime,
            )

            if feature_vector is None:
                logger.warning(f"Could not calculate V4 features for {ticker}")
                return 0, 0.0, {}

            # Get ensemble prediction
            X = feature_vector.reshape(1, -1)
            probability = float(self.ensemble.predict_proba(X)[0])

            # Make decision
            prediction = 1 if probability >= self.threshold else 0

            # Features dict for logging
            feature_names = self.feature_engineer.selected_features or self.feature_engineer.required_features_v4
            features_dict = {
                name: float(val) if not np.isnan(val) else None
                for name, val in zip(feature_names, feature_vector)
            }

            signal_type = "BUY" if prediction == 1 else "HOLD"
            regime = self._cached_regime.get("regime_name", "?") if self._cached_regime else "?"
            logger.info(f"[V4] {ticker}: {signal_type} (p={probability:.4f}, regime={regime})")

            return prediction, probability, features_dict

        except Exception as e:
            logger.error(f"V4 prediction failed for {ticker}: {e}")
            return 0, 0.0, {}

    def predict_multiple(
        self,
        tickers_data: Dict[str, pd.DataFrame],
        btc_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """
        Make V4 predictions for multiple tickers.
        Same interface as TradingPredictor.predict_multiple.
        """
        # Check if model needs hot-reload
        if self._needs_reload:
            self.reload_model()

        results = []

        # Refresh external data once per batch
        self._cached_external = self._fetch_external_data_sync()

        logger.info(f"[V4] Making predictions for {len(tickers_data)} tickers...")

        for ticker, ohlcv_data in tickers_data.items():
            prediction, probability, features = self.predict_single(
                ticker=ticker,
                ohlcv_data=ohlcv_data,
                btc_data=btc_data,
                macro_data=macro_data,
            )
            results.append({
                "ticker": ticker,
                "prediction": prediction,
                "probability": probability,
                "signal_type": "BUY" if prediction == 1 else "HOLD",
                "features": features,
            })

        df = pd.DataFrame(results)
        buy_signals = (df["prediction"] == 1).sum()
        logger.success(f"[V4] Predictions: {buy_signals} BUY / {len(tickers_data)} total")
        return df

    def get_top_signals(
        self,
        predictions_df: pd.DataFrame,
        top_n: int = 10,
        min_probability: Optional[float] = None,
    ) -> pd.DataFrame:
        """Get top N signals by probability"""
        threshold = min_probability if min_probability is not None else self.threshold
        signals = predictions_df[predictions_df["probability"] >= threshold].copy()
        signals = signals.sort_values("probability", ascending=False)
        return signals.head(top_n)

    def should_trade(
        self,
        ticker: str,
        probability: float,
        current_positions: int,
        daily_loss: float,
    ) -> Tuple[bool, str]:
        """Same interface as TradingPredictor.should_trade"""
        if probability < self.threshold:
            return False, f"Probability {probability:.4f} below threshold {self.threshold}"

        if current_positions >= settings.MAX_POSITIONS:
            return False, f"Max positions reached ({settings.MAX_POSITIONS})"

        if daily_loss >= settings.MAX_DAILY_LOSS_USD:
            return False, f"Daily loss limit reached (${daily_loss:.2f})"

        if settings.REQUIRE_MANUAL_APPROVAL:
            return False, "Manual approval required"

        # V4: Check regime — block new trades in Bear regime
        if self._cached_regime:
            regime = self._cached_regime.get("regime_name", "Sideways")
            bear_prob = self._cached_regime.get("regime_bear_prob", 0)
            if regime == "Bear" and bear_prob > 0.7:
                return False, f"Bear regime detected (prob={bear_prob:.2f})"

        return True, "All checks passed"

    def calculate_position_size(
        self,
        current_price: float,
        portfolio_value: float,
        probability: float,
    ) -> Dict[str, float]:
        """
        Calculate position size using Kelly Criterion.
        Same interface as TradingPredictor.calculate_position_size.
        """
        result = self.position_sizer.calculate_position_size(
            current_price=current_price,
            portfolio_value=portfolio_value,
            probability=probability,
            regime_data=self._cached_regime,
            max_position_usd=settings.MAX_POSITION_SIZE_USD,
        )

        return {
            "quantity": result["quantity"],
            "usd_value": result["usd_value"],
            "position_pct": result["position_pct"],
        }

    async def get_macro_data_async(self) -> Dict:
        """Fetch macro data (compatible with V3 interface)"""
        try:
            return await self.macro_fetcher.get_all_macro_data()
        except Exception as e:
            logger.error(f"Failed to fetch macro data: {e}")
            return {"fear_greed": 50.0, "funding_rate": 0.0, "spx": 4500.0, "spx_change_7d": 0.0, "vix": 20.0}

    def get_macro_data_sync(self) -> Dict:
        """Fetch macro data synchronously (compatible with V3 interface)"""
        try:
            return self.macro_fetcher.get_all_macro_data_sync()
        except Exception as e:
            logger.error(f"Failed to fetch macro data: {e}")
            return {"fear_greed": 50.0, "funding_rate": 0.0, "spx": 4500.0, "spx_change_7d": 0.0, "vix": 20.0}
