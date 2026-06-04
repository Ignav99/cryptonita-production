"""
TRADING PREDICTOR V5
=====================
Ternary trading predictor: LONG / HOLD / SHORT.

Key differences from V4:
- Uses EnsembleV5 (3-class) instead of binary EnsembleModel
- predict_single returns (signal_class, proba_3, features_dict)
  where signal_class ∈ {0=HOLD, 1=LONG, 2=SHORT}
  and proba_3 = [P(HOLD), P(LONG), P(SHORT)]
- predict_multiple includes p_hold, p_long, p_short columns
- should_trade handles LONG and SHORT with separate thresholds
- Per-coin model store integration (loads model for specific ticker)
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
from src.models.ensemble_v5 import EnsembleV5
from src.models.regime_detector import RegimeDetector
from src.models.position_sizer import KellyPositionSizer
from src.config.per_coin_config import get_long_threshold, get_short_threshold

# Signal constants
SIGNAL_HOLD = 0
SIGNAL_LONG = 1
SIGNAL_SHORT = 2
SIGNAL_NAMES = {SIGNAL_HOLD: "HOLD", SIGNAL_LONG: "LONG", SIGNAL_SHORT: "SHORT"}

# Default thresholds
DEFAULT_LONG_THRESHOLD = 0.35   # P(LONG) must exceed this to emit LONG
DEFAULT_SHORT_THRESHOLD = 0.35  # P(SHORT) must exceed this to emit SHORT


class TradingPredictorV5:
    """
    V5 Trading Predictor — ternary signals (LONG / HOLD / SHORT).

    Per-coin models: loads a specific EnsembleV5 per ticker if available.
    Falls back to a global model if per-coin model not found.
    """

    def __init__(self):
        self.model_base_dir = Path(
            getattr(settings, "V5_MODEL_DIR", "PRODUCTION_SYSTEM/models/v5")
        )
        self._lock = threading.Lock()
        self._needs_reload = False

        # Per-coin model cache: {ticker: EnsembleV5}
        self._coin_models: Dict[str, EnsembleV5] = {}
        self._global_model: Optional[EnsembleV5] = None

        # Load global model (fallback)
        self._load_global_model()

        # Feature engineering (reuse V4 feature pipeline)
        self.feature_engineer = FeatureEngineerV4()

        # Data fetchers (same as V4)
        self.macro_fetcher = MacroDataFetcher()
        self.derivatives_fetcher = DerivativesFetcher()
        self.onchain_fetcher = OnChainFetcher()
        self.sentiment_fetcher = SentimentFetcher()
        self.defi_fetcher = DeFiFetcher()
        self.news_fetcher = NewsFetcher()
        self.social_fetcher = SocialFetcher()
        self.whale_fetcher = WhaleFetcher()
        self.coingecko_fetcher = CoinGeckoFetcher()

        # Position sizing
        kelly_fraction = getattr(settings, "KELLY_FRACTION", 0.25)
        self.position_sizer = KellyPositionSizer(kelly_fraction=kelly_fraction)

        # Thresholds (can be overridden per ticker)
        self.long_threshold = getattr(settings, "V5_LONG_THRESHOLD", DEFAULT_LONG_THRESHOLD)
        self.short_threshold = getattr(settings, "V5_SHORT_THRESHOLD", DEFAULT_SHORT_THRESHOLD)

        # Regime cache
        self._cached_regime: Optional[Dict] = None
        self._cached_external: Optional[Dict] = None
        self._cached_coingecko: Optional[Dict] = None

        # Trade result cooldown tracker (same as V4)
        self._trade_results: Dict[str, Dict] = {}

        logger.info(
            f"TradingPredictorV5 initialized — "
            f"LONG threshold={self.long_threshold}, SHORT threshold={self.short_threshold}"
        )

    def _load_global_model(self):
        """Load the global V5 model (used as fallback if no per-coin model)."""
        global_dir = self.model_base_dir / "global"
        metadata_path = global_dir / "v5_ensemble_metadata.json"
        logger.info(f"[V5] Checking global model at: {metadata_path.resolve()} (exists={metadata_path.exists()})")
        if metadata_path.exists():
            try:
                self._global_model = EnsembleV5()
                self._global_model.load(str(global_dir))
                logger.info("[V5] Global model loaded from filesystem")
            except Exception as e:
                logger.warning(f"[V5] Failed to load global model: {e}")
        else:
            logger.warning("[V5] No global model found — predictions will return HOLD until training completes")

    def _get_model(self, ticker: str) -> Optional[EnsembleV5]:
        """
        Get the EnsembleV5 model for a specific ticker.
        Tries per-coin model first, falls back to global.
        Caches loaded models in memory.
        """
        # Check in-memory cache first
        if ticker in self._coin_models:
            return self._coin_models[ticker]

        # Try loading per-coin model from disk
        coin_dir = self.model_base_dir / ticker
        metadata_path = coin_dir / "v5_ensemble_metadata.json"
        if metadata_path.exists():
            try:
                model = EnsembleV5()
                model.load(str(coin_dir))
                self._coin_models[ticker] = model
                logger.info(f"[V5] Per-coin model loaded: {ticker}")
                return model
            except Exception as e:
                logger.warning(f"[V5] Failed to load per-coin model for {ticker}: {e}")

        # Fall back to global model
        if self._global_model is not None:
            return self._global_model

        logger.error(f"[V5] No model available for {ticker}")
        return None

    def load_coin_model(self, ticker: str, model_dir: str):
        """Manually load a per-coin model (used after training)."""
        try:
            model = EnsembleV5()
            model.load(model_dir)
            with self._lock:
                self._coin_models[ticker] = model
            logger.success(f"[V5] Loaded coin model for {ticker} from {model_dir}")
        except Exception as e:
            logger.error(f"[V5] Failed to load coin model for {ticker}: {e}")

    def request_reload(self):
        """Signal that models need hot-reload."""
        self._needs_reload = True
        self._coin_models.clear()  # Clear cache so models reload lazily
        self._load_global_model()

    def register_trade_result(self, ticker: str, won: bool):
        """Register trade result for cooldown tracking."""
        import time as _time
        self._trade_results[ticker] = {"ts": _time.time(), "won": won}
        label = "WIN" if won else "LOSS — 7-day cooldown active"
        logger.info(f"[Cooldown] {ticker}: {label}")

    def _in_cooldown(self, ticker: str) -> bool:
        """True if ticker is in a post-loss cooldown (7 days)."""
        import time as _time
        result = self._trade_results.get(ticker)
        if result is None or result.get("won", True):
            return False
        return (_time.time() - result["ts"]) < 7 * 86400

    def _passes_trend_filter_long(self, ohlcv_data: pd.DataFrame) -> Tuple[bool, str]:
        """Trend filter for LONG: block in confirmed downtrend or over-extended."""
        try:
            if len(ohlcv_data) < 200:
                return True, "insufficient_data"
            close = ohlcv_data["close"]
            ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
            current = float(close.iloc[-1])
            if ema50 < ema200:
                return False, f"downtrend (EMA50={ema50:.4f} < EMA200={ema200:.4f})"
            if current > ema50 * 1.20:
                return False, f"overextended (price={current:.2f} > 1.20×EMA50)"
            return True, "ok"
        except Exception as exc:
            return True, f"error_passthrough: {exc}"

    def _passes_trend_filter_short(self, ohlcv_data: pd.DataFrame) -> Tuple[bool, str]:
        """Trend filter for SHORT: block in confirmed uptrend (don't short bull markets)."""
        try:
            if len(ohlcv_data) < 200:
                return True, "insufficient_data"
            close = ohlcv_data["close"]
            ema50 = float(close.ewm(span=50, adjust=False).mean().iloc[-1])
            ema200 = float(close.ewm(span=200, adjust=False).mean().iloc[-1])
            current = float(close.iloc[-1])
            # Block SHORT if strong uptrend (EMA50 well above EMA200)
            if ema50 > ema200 * 1.05:
                return False, f"strong_uptrend (EMA50={ema50:.4f} > 1.05×EMA200={ema200:.4f})"
            return True, "ok"
        except Exception as exc:
            return True, f"error_passthrough: {exc}"

    async def _fetch_external_data(self) -> Dict:
        """Fetch all external data sources concurrently (same as V4)."""
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

    def _fetch_external_data_sync(self) -> Dict:
        """Sync wrapper for external data."""
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
        """Sync wrapper for CoinGecko data (1h cache in fetcher)."""
        import concurrent.futures
        def _run():
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self.coingecko_fetcher.get_all_coingecko_data())
            finally:
                loop.close()
        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_run).result(timeout=180)
        except RuntimeError:
            return asyncio.run(self.coingecko_fetcher.get_all_coingecko_data())
        except Exception as exc:
            logger.warning(f"CoinGecko fetch failed: {exc}")
            return {}

    def predict_single(
        self,
        ticker: str,
        ohlcv_data: pd.DataFrame,
        btc_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None,
        long_threshold: Optional[float] = None,
        short_threshold: Optional[float] = None,
    ) -> Tuple[int, np.ndarray, Dict]:
        """
        Make V5 ternary prediction for a single ticker.

        Args:
            ticker: Coin symbol (e.g., 'BTCUSDT')
            ohlcv_data: OHLCV DataFrame
            btc_data: BTC OHLCV for regime detection
            macro_data: Optional macro data override
            long_threshold: Override P(LONG) threshold
            short_threshold: Override P(SHORT) threshold

        Returns:
            Tuple of (signal_class, proba_3, features_dict)
              signal_class: 0=HOLD, 1=LONG, 2=SHORT
              proba_3: np.ndarray shape (3,) = [P(HOLD), P(LONG), P(SHORT)]
              features_dict: dict of feature values used
        """
        try:
            # Per-coin LONG threshold: disabled coins get 1.0 (impossible),
            # optimized coins get a lower value, others get 0.65 strict default.
            # Caller override (long_threshold kwarg) takes precedence if provided.
            coin_lt = get_long_threshold(ticker)
            lt = long_threshold if long_threshold is not None else coin_lt
            if coin_lt == 1.0 and long_threshold is None:
                logger.info(f"[V5] {ticker}: LONG disabled by per-coin config")

            # Per-coin SHORT threshold: disabled coins get 1.0 (no SHORT),
            # optimized coins get a lower threshold to capture alpha.
            coin_st = get_short_threshold(ticker)
            st = short_threshold if short_threshold is not None else coin_st
            if coin_st == 1.0 and short_threshold is None:
                logger.info(f"[V5] {ticker}: SHORT disabled by per-coin config")

            # Get or refresh external data
            if self._cached_external is None:
                self._cached_external = self._fetch_external_data_sync()
            ext = self._cached_external
            if macro_data:
                ext["macro"] = macro_data

            # Regime detection
            if btc_data is not None:
                try:
                    regime_det = RegimeDetector()
                    if hasattr(regime_det, 'model') and regime_det.model is not None:
                        self._cached_regime = regime_det.predict(btc_data)
                except Exception:
                    pass

            # Build ticker-specific external features
            ticker_news = self.news_fetcher.get_ticker_features_llm(
                ticker, ext.get("news", {})
            ) if hasattr(self.news_fetcher, 'get_ticker_features_llm') else {}
            ticker_social = self.social_fetcher.get_ticker_features(
                ticker, ext.get("social", {})
            ) if hasattr(self.social_fetcher, 'get_ticker_features') else {}
            ticker_whale = ext.get("whale", {})
            ticker_cg = self.coingecko_fetcher.get_ticker_features(
                ticker, self._cached_coingecko or {}
            )

            # Calculate V4 feature vector (same pipeline, V5 reuses features)
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
                logger.warning(f"[V5] Could not calculate features for {ticker}")
                return SIGNAL_HOLD, np.array([1.0, 0.0, 0.0]), {}

            # Align to model's expected features
            model = self._get_model(ticker)
            if model is None:
                return SIGNAL_HOLD, np.array([1.0, 0.0, 0.0]), {}

            all_names = self.feature_engineer.selected_features or self.feature_engineer.required_features_v4
            model_names = model.feature_names
            if model_names and len(all_names) != len(model_names):
                name_to_val = dict(zip(all_names, feature_vector))
                feature_vector = np.array([name_to_val.get(f, np.nan) for f in model_names])
                log_names = model_names
            else:
                log_names = all_names

            # Get ternary probabilities: shape (1, 3) → (3,)
            X = feature_vector.reshape(1, -1)
            proba_3 = model.predict_proba(X)[0]  # [P(HOLD), P(LONG), P(SHORT)]
            p_hold, p_long, p_short = float(proba_3[0]), float(proba_3[1]), float(proba_3[2])

            # Determine signal with thresholds + tie-breaking
            signal_class = SIGNAL_HOLD
            if p_long >= lt and p_long >= p_short:
                signal_class = SIGNAL_LONG
                # Apply LONG trend filter
                passes, reason = self._passes_trend_filter_long(ohlcv_data)
                if not passes:
                    signal_class = SIGNAL_HOLD
                    logger.info(f"[V5] {ticker}: LONG blocked by trend filter ({reason})")
            elif p_short >= st and p_short > p_long:
                signal_class = SIGNAL_SHORT
                # Apply SHORT trend filter (don't short bull markets)
                passes, reason = self._passes_trend_filter_short(ohlcv_data)
                if not passes:
                    signal_class = SIGNAL_HOLD
                    logger.info(f"[V5] {ticker}: SHORT blocked by trend filter ({reason})")

            # Features dict for logging
            features_dict = {
                name: float(val) if not np.isnan(val) else None
                for name, val in zip(log_names, feature_vector)
            }
            features_dict["_p_hold"] = p_hold
            features_dict["_p_long"] = p_long
            features_dict["_p_short"] = p_short
            features_dict["_signal"] = SIGNAL_NAMES[signal_class]
            features_dict["_in_cooldown"] = self._in_cooldown(ticker)

            regime = self._cached_regime.get("regime_name", "?") if self._cached_regime else "?"
            logger.info(
                f"[V5] {ticker}: {SIGNAL_NAMES[signal_class]} "
                f"(p_long={p_long:.4f}, p_short={p_short:.4f}, p_hold={p_hold:.4f}, "
                f"regime={regime})"
            )

            return signal_class, proba_3, features_dict

        except Exception as e:
            logger.error(f"[V5] prediction failed for {ticker}: {e}")
            return SIGNAL_HOLD, np.array([1.0, 0.0, 0.0]), {}

    def predict_multiple(
        self,
        tickers_data: Dict[str, pd.DataFrame],
        btc_data: Optional[pd.DataFrame] = None,
        macro_data: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """
        Make V5 ternary predictions for multiple tickers.

        Returns:
            DataFrame with columns:
              ticker, signal_class, signal_name, p_hold, p_long, p_short, features
        """
        if self._needs_reload:
            self.request_reload()

        results = []

        # Refresh external data once per batch
        self._cached_external = self._fetch_external_data_sync()
        self._cached_coingecko = self._fetch_coingecko_data_sync()

        logger.info(f"[V5] Predicting {len(tickers_data)} tickers...")

        import gc
        for ticker, ohlcv_data in tickers_data.items():
            signal_class, proba_3, features = self.predict_single(
                ticker=ticker,
                ohlcv_data=ohlcv_data,
                btc_data=btc_data,
                macro_data=macro_data,
            )
            results.append({
                "ticker": ticker,
                "signal_class": signal_class,
                "signal_name": SIGNAL_NAMES[signal_class],
                "p_hold": float(proba_3[0]),
                "p_long": float(proba_3[1]),
                "p_short": float(proba_3[2]),
                "features": features,
            })

        self._cached_external = None
        gc.collect()

        df = pd.DataFrame(results)
        long_signals = (df["signal_class"] == SIGNAL_LONG).sum()
        short_signals = (df["signal_class"] == SIGNAL_SHORT).sum()
        logger.success(
            f"[V5] Results: {long_signals} LONG / {short_signals} SHORT / "
            f"{len(tickers_data) - long_signals - short_signals} HOLD"
        )
        return df

    def should_trade(
        self,
        ticker: str,
        signal_class: int,
        proba_3: np.ndarray,
        current_positions: int,
        daily_loss: float,
    ) -> Tuple[bool, str]:
        """
        Check if we should execute a LONG or SHORT trade.

        Args:
            ticker: Coin symbol
            signal_class: 0=HOLD, 1=LONG, 2=SHORT
            proba_3: [P(HOLD), P(LONG), P(SHORT)]
            current_positions: Number of current open positions
            daily_loss: Current daily loss in USD (positive = loss)

        Returns:
            (should_trade: bool, reason: str)
        """
        if signal_class == SIGNAL_HOLD:
            return False, "Signal is HOLD"

        signal_name = SIGNAL_NAMES[signal_class]
        confidence = float(proba_3[1]) if signal_class == SIGNAL_LONG else float(proba_3[2])

        # Position limit check
        max_pos = getattr(settings, "MAX_POSITIONS", 5)
        if current_positions >= max_pos:
            return False, f"Max positions reached ({max_pos})"

        # Daily loss circuit breaker
        max_daily_loss = getattr(settings, "MAX_DAILY_LOSS_USD", 100.0)
        if daily_loss >= max_daily_loss:
            return False, f"Daily loss limit reached (${daily_loss:.2f})"

        # Manual approval gate
        if getattr(settings, "REQUIRE_MANUAL_APPROVAL", False):
            return False, "Manual approval required"

        # Regime-based gate: in strong bear, only allow LONG if confidence is very high
        if self._cached_regime:
            regime = self._cached_regime.get("regime_name", "Sideways")
            bear_prob = self._cached_regime.get("regime_bear_prob", 0)
            if regime == "Bear" and bear_prob > 0.7:
                if signal_class == SIGNAL_LONG and confidence < 0.55:
                    return False, f"Bear regime — LONG confidence too low ({confidence:.4f})"

        # Cooldown gate (reduces position size, not signal)
        # We allow trades during cooldown but at 50% size (handled by calculate_position_size)

        return True, f"{signal_name} trade approved (confidence={confidence:.4f})"

    def calculate_position_size(
        self,
        current_price: float,
        portfolio_value: float,
        signal_class: int,
        proba_3: np.ndarray,
        ticker: str = "",
    ) -> Dict:
        """
        Calculate position size for a LONG or SHORT trade.

        Args:
            current_price: Current asset price
            portfolio_value: Total portfolio value in USDT
            signal_class: 1=LONG, 2=SHORT
            proba_3: [P(HOLD), P(LONG), P(SHORT)]
            ticker: Coin symbol

        Returns:
            Dict with quantity, usd_value, position_pct, signal_name, cooldown_active
        """
        confidence = float(proba_3[1]) if signal_class == SIGNAL_LONG else float(proba_3[2])
        cooldown_mult = 0.5 if self._in_cooldown(ticker) else 1.0

        # Use Kelly with conservative 0.25 fraction
        kelly_mult = 0.25 * cooldown_mult
        max_position_usd = getattr(settings, "MAX_POSITION_SIZE_USD", 500.0)
        max_position_pct = 0.05 * cooldown_mult  # Max 5% of portfolio per trade

        result = self.position_sizer.calculate_position_size(
            current_price=current_price,
            portfolio_value=portfolio_value,
            probability=confidence,
            regime_data=self._cached_regime,
            max_position_usd=max_position_usd,
            kelly_mult=kelly_mult,
            max_position_pct_override=max_position_pct,
        )

        return {
            "quantity": result["quantity"],
            "usd_value": result["usd_value"],
            "position_pct": result["position_pct"],
            "signal_name": SIGNAL_NAMES.get(signal_class, "HOLD"),
            "cooldown_active": self._in_cooldown(ticker),
        }

    def get_top_signals(
        self,
        predictions_df: pd.DataFrame,
        top_n: int = 5,
        signal_types: Optional[list] = None,
    ) -> pd.DataFrame:
        """
        Get top N signals filtered by type.

        Args:
            predictions_df: Output of predict_multiple()
            top_n: Max signals to return
            signal_types: List of signal_class values to include (default: [1, 2] = LONG + SHORT)
        """
        if signal_types is None:
            signal_types = [SIGNAL_LONG, SIGNAL_SHORT]

        filtered = predictions_df[predictions_df["signal_class"].isin(signal_types)].copy()

        # Sort: LONG by p_long desc, SHORT by p_short desc
        # Combined: sort by max(p_long, p_short)
        filtered["_confidence"] = filtered.apply(
            lambda r: r["p_long"] if r["signal_class"] == SIGNAL_LONG else r["p_short"],
            axis=1,
        )
        return filtered.sort_values("_confidence", ascending=False).head(top_n).drop(columns=["_confidence"])
