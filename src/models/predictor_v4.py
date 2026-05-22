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
from src.data.news_fetcher import NewsFetcher
from src.data.social_fetcher import SocialFetcher
from src.data.whale_fetcher import WhaleFetcher
from src.data.coingecko_fetcher import CoinGeckoFetcher
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
        self.news_fetcher = NewsFetcher()
        self.social_fetcher = SocialFetcher()
        self.whale_fetcher = WhaleFetcher()
        self.coingecko_fetcher = CoinGeckoFetcher()

        # Initialize position sizer
        kelly_fraction = getattr(settings, "KELLY_FRACTION", 0.25)
        self.position_sizer = KellyPositionSizer(kelly_fraction=kelly_fraction)

        # Trading parameters
        self.threshold = settings.PREDICTION_THRESHOLD  # Default fallback
        self.risk_profiles = settings.COIN_RISK_PROFILES
        self.default_profile = settings.DEFAULT_RISK_PROFILE

        # Cache for external data (refreshed each scan cycle)
        self._cached_external = None
        self._cached_regime = None
        self._cached_coingecko: Optional[Dict] = None

        # Per-ticker probability history for z-score normalization
        self._prob_history: Dict[str, list] = {}
        self._PROB_HISTORY_SIZE = 50

        # Cooldown tracker: {ticker: {"ts": float, "won": bool}}
        # 7-day cooldown after a loss → 50% position size
        self._trade_results: Dict[str, Dict] = {}

        logger.info(
            f"TradingPredictorV4 initialized — Default threshold: {self.threshold}, "
            f"Dynamic profiles: {len(self.risk_profiles)} tickers"
        )

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

    def _get_ticker_profile(self, ticker: str) -> Dict:
        """Get risk profile for a specific ticker"""
        return self.risk_profiles.get(ticker, self.default_profile)

    def _get_ticker_threshold(self, ticker: str) -> float:
        """Get dynamic threshold for a specific ticker (high confidence level)"""
        return self._get_ticker_profile(ticker)["threshold"]

    def _update_prob_history(self, ticker: str, prob: float):
        """Track per-ticker probability for z-score normalization."""
        if ticker not in self._prob_history:
            self._prob_history[ticker] = []
        self._prob_history[ticker].append(prob)
        if len(self._prob_history[ticker]) > self._PROB_HISTORY_SIZE:
            self._prob_history[ticker].pop(0)

    def _get_prob_zscore(self, ticker: str, prob: float) -> Optional[float]:
        """Get z-score of probability vs this ticker's history. None if not enough data."""
        history = self._prob_history.get(ticker, [])
        if len(history) < 10:
            return None
        mean = np.mean(history)
        std = np.std(history)
        if std < 0.001:
            return None
        return (prob - mean) / std

    def _passes_trend_filter(self, ohlcv_data: pd.DataFrame) -> Tuple[bool, str]:
        """
        Trend quality filter: block entries in confirmed downtrends or over-extended moves.

        Rules:
          - EMA50 < EMA200 (death cross) → block: entering a downtrend is high-risk
          - Price > 1.20 × EMA50 → block: over-extended, late entry with poor R/R

        Returns (passes: bool, reason: str).
        If insufficient data (<200 candles), passes by default (no block).
        """
        try:
            if len(ohlcv_data) < 200:
                return True, "insufficient_data"

            close = ohlcv_data["close"]
            ema50  = float(close.ewm(span=50,  adjust=False).mean().iloc[-1])
            ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
            current = float(close.iloc[-1])

            if ema50 < ema200:
                return False, f"downtrend_guard (EMA50={ema50:.4f} < EMA200={ema200:.4f})"

            if current > ema50 * 1.20:
                return False, f"overextended (price={current:.2f} > 1.20×EMA50={ema50 * 1.20:.2f})"

            return True, "ok"
        except Exception as exc:
            logger.debug(f"Trend filter error: {exc}")
            return True, "error_passthrough"

    def register_trade_result(self, ticker: str, won: bool):
        """
        Register the result of a closed trade.
        Losses trigger a 7-day cooldown with 50% position size reduction.
        Called by the trade executor after a position is closed.
        """
        import time as _time
        self._trade_results[ticker] = {"ts": _time.time(), "won": won}
        label = "WIN" if won else "LOSS — 7-day cooldown active"
        logger.info(f"[Cooldown] {ticker}: registered {label}")

    def _in_cooldown(self, ticker: str) -> bool:
        """True if this ticker is in a 7-day post-loss cooldown period."""
        import time as _time
        result = self._trade_results.get(ticker)
        if result is None or result.get("won", True):
            return False
        elapsed = _time.time() - result["ts"]
        return elapsed < 7 * 86400  # 7 days in seconds

    def _get_cooldown_mult(self, ticker: str) -> float:
        """Position size multiplier: 0.5 during cooldown, 1.0 otherwise."""
        return 0.5 if self._in_cooldown(ticker) else 1.0

    def _classify_confidence(self, probability: float, profile: Dict, ticker: str = "") -> str:
        """
        Band-pass confidence filter with z-score enhancement.
        threshold = CEILING (reject overfit signals above this)
        threshold_medium = FLOOR (minimum to enter)
        Z-score >= 1.5 sigma → "high" confidence (significantly above normal for this coin)

        Returns: "high", "medium", or "none"
        """
        ceiling = profile["threshold"]  # 0.42 — reject above
        floor = profile.get("threshold_medium", profile["threshold"])  # 0.28

        if probability >= ceiling:
            return "none"  # REJECT overfit zone

        if probability >= floor:
            # Check z-score for high confidence upgrade
            if ticker:
                zscore = self._get_prob_zscore(ticker, probability)
                if zscore is not None and zscore >= 1.5:
                    return "high"
            return "medium"

        return "none"

    def get_signal_confidence(self, ticker: str, probability: float) -> str:
        """Public method to get confidence level for a ticker/probability."""
        profile = self._get_ticker_profile(ticker)
        return self._classify_confidence(probability, profile, ticker)

    async def _fetch_external_data(self) -> Dict[str, Dict]:
        """Fetch all external data sources concurrently"""
        macro, derivatives, onchain, sentiment, defi, news, social, whale = await asyncio.gather(
            self.macro_fetcher.get_all_macro_data(),
            self.derivatives_fetcher.get_all_derivatives_data(),
            self.onchain_fetcher.get_all_onchain_data(),
            self.sentiment_fetcher.get_all_sentiment_data(),
            self.defi_fetcher.get_all_defi_data(),
            self.news_fetcher.get_all_news_data(),
            self.social_fetcher.get_all_social_data(),
            self.whale_fetcher.get_all_whale_data(),
            return_exceptions=True,
        )

        return {
            "macro": macro if isinstance(macro, dict) else {},
            "derivatives": derivatives if isinstance(derivatives, dict) else {},
            "onchain": onchain if isinstance(onchain, dict) else {},
            "sentiment": sentiment if isinstance(sentiment, dict) else {},
            "defi": defi if isinstance(defi, dict) else {},
            "news": news if isinstance(news, dict) else {},
            "social": social if isinstance(social, dict) else {},
            "whale": whale if isinstance(whale, dict) else {},
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

    def _fetch_coingecko_data_sync(self) -> Dict:
        """
        Sync wrapper for CoinGecko data fetch.
        The fetcher has its own 1h cache — cold start takes ~2 min,
        subsequent calls within 1h return instantly.
        """
        import concurrent.futures

        def _run():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(
                    self.coingecko_fetcher.get_all_coingecko_data()
                )
            finally:
                loop.close()

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                # 3-min timeout: 47 coins × 2.5s + buffer
                return pool.submit(_run).result(timeout=180)
        except RuntimeError:
            return asyncio.run(self.coingecko_fetcher.get_all_coingecko_data())
        except Exception as exc:
            logger.warning(f"CoinGecko fetch failed: {exc} — using NaN features")
            return {}

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

            # Build ticker-specific news/social/whale/coingecko data
            ticker_news = self.news_fetcher.get_ticker_features_llm(
                ticker, ext.get("news", {})
            ) if hasattr(self, 'news_fetcher') else {}
            ticker_social = self.social_fetcher.get_ticker_features(
                ticker, ext.get("social", {})
            ) if hasattr(self, 'social_fetcher') else {}
            ticker_whale = ext.get("whale", {})
            ticker_cg = self.coingecko_fetcher.get_ticker_features(
                ticker, self._cached_coingecko or {}
            )

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
                news_data=ticker_news,
                social_data=ticker_social,
                whale_data=ticker_whale,
                coingecko_data=ticker_cg,
            )

            if feature_vector is None:
                logger.warning(f"Could not calculate V4 features for {ticker}")
                return 0, 0.0, {}

            # Align feature vector to model's expected features
            all_names = self.feature_engineer.selected_features or self.feature_engineer.required_features_v4
            model_names = self.ensemble.feature_names
            if model_names and len(all_names) != len(model_names):
                name_to_val = dict(zip(all_names, feature_vector))
                feature_vector = np.array([name_to_val.get(f, np.nan) for f in model_names])
                log_names_final = model_names
            else:
                log_names_final = all_names

            # Get ensemble prediction
            X = feature_vector.reshape(1, -1)
            probability = float(self.ensemble.predict_proba(X)[0])

            # Use dynamic threshold per ticker with z-score enhanced confidence
            profile = self._get_ticker_profile(ticker)
            self._update_prob_history(ticker, probability)
            confidence = self._classify_confidence(probability, profile, ticker)
            prediction = 1 if confidence != "none" else 0

            # Features dict for logging
            log_names = log_names_final
            features_dict = {
                name: float(val) if not np.isnan(val) else None
                for name, val in zip(log_names, feature_vector)
            }

            # V4.5: Apply trend filter — block BUY signals in downtrend / over-extended
            if prediction == 1:
                passes, filter_reason = self._passes_trend_filter(ohlcv_data)
                if not passes:
                    prediction = 0
                    logger.info(f"[V4] {ticker}: HOLD — trend filter blocked ({filter_reason})")

            # V4.5: Log cooldown status (affects position sizing, not signal)
            if prediction == 1 and self._in_cooldown(ticker):
                logger.info(f"[V4] {ticker}: BUY — in loss cooldown, position size ×0.5")

            signal_type = "BUY" if prediction == 1 else "HOLD"
            regime = self._cached_regime.get("regime_name", "?") if self._cached_regime else "?"
            logger.info(
                f"[V4] {ticker}: {signal_type} (p={probability:.4f}, "
                f"confidence={confidence}, tier={profile['tier']}, regime={regime})"
            )

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

        # CoinGecko data (1h cache in fetcher — instant if warm, ~2 min if cold)
        self._cached_coingecko = self._fetch_coingecko_data_sync()

        logger.info(f"[V4] Making predictions for {len(tickers_data)} tickers...")

        import gc
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

        # Free external data cache after batch to reduce peak memory
        self._cached_external = None
        gc.collect()

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
        """Get top N signals by probability, filtered by lowest confidence threshold."""
        if min_probability is not None:
            signals = predictions_df[predictions_df["probability"] >= min_probability].copy()
        else:
            # Filter: only signals that reach at least exploratory level for their tier
            mask = predictions_df.apply(
                lambda row: self._classify_confidence(
                    row["probability"],
                    self._get_ticker_profile(row["ticker"]),
                    row["ticker"]
                ) != "none",
                axis=1,
            )
            signals = predictions_df[mask].copy()

        signals = signals.sort_values("probability", ascending=False)
        return signals.head(top_n)

    def should_trade(
        self,
        ticker: str,
        probability: float,
        current_positions: int,
        daily_loss: float,
    ) -> Tuple[bool, str]:
        """
        Check if we should trade, using 3-level confidence system.
        Returns (should_trade, reason).
        """
        profile = self._get_ticker_profile(ticker)
        confidence = self._classify_confidence(probability, profile, ticker)

        if confidence == "none":
            lowest = profile.get("threshold_low", profile["threshold"])
            return False, (
                f"Probability {probability:.4f} below minimum threshold "
                f"{lowest} (tier {profile['tier']})"
            )

        # Check position limits per confidence level
        conf_config = settings.CONFIDENCE_LEVELS.get(confidence, {})
        max_pos = conf_config.get("max_positions", settings.MAX_POSITIONS)
        if current_positions >= max_pos:
            return False, f"Max positions for {confidence} confidence reached ({max_pos})"

        if current_positions >= settings.MAX_POSITIONS:
            return False, f"Max total positions reached ({settings.MAX_POSITIONS})"

        if daily_loss >= settings.MAX_DAILY_LOSS_USD:
            return False, f"Daily loss limit reached (${daily_loss:.2f})"

        if settings.REQUIRE_MANUAL_APPROVAL:
            return False, "Manual approval required"

        # V4: Check regime — block new trades in Bear regime
        # But allow high-confidence signals through even in mild bear
        if self._cached_regime:
            regime = self._cached_regime.get("regime_name", "Sideways")
            bear_prob = self._cached_regime.get("regime_bear_prob", 0)
            if regime == "Bear" and bear_prob > 0.7:
                if confidence != "high":
                    return False, f"Bear regime — only high-confidence trades allowed (prob={bear_prob:.2f})"

        return True, f"All checks passed (confidence={confidence})"

    def calculate_position_size(
        self,
        current_price: float,
        portfolio_value: float,
        probability: float,
        ticker: str = "",
    ) -> Dict[str, float]:
        """
        Calculate position size using Kelly Criterion with tier + confidence adjustments.
        """
        profile = self._get_ticker_profile(ticker)
        confidence = self._classify_confidence(probability, profile, ticker)
        conf_config = settings.CONFIDENCE_LEVELS.get(confidence, settings.CONFIDENCE_LEVELS["exploratory"])
        position_mult = conf_config.get("position_mult", 0.25)

        cooldown_mult = self._get_cooldown_mult(ticker)
        result = self.position_sizer.calculate_position_size(
            current_price=current_price,
            portfolio_value=portfolio_value,
            probability=probability,
            regime_data=self._cached_regime,
            max_position_usd=settings.MAX_POSITION_SIZE_USD,
            kelly_mult=profile["kelly_mult"] * position_mult * cooldown_mult,
            max_position_pct_override=profile["max_position_pct"] * position_mult * cooldown_mult,
        )

        return {
            "quantity": result["quantity"],
            "usd_value": result["usd_value"],
            "position_pct": result["position_pct"],
            "confidence": confidence,
            "cooldown_active": self._in_cooldown(ticker),
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
