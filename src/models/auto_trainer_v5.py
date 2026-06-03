"""
AUTO-TRAINER V5
================
Per-coin ternary model training engine.

Trains one EnsembleV5 per ticker using LONG/SHORT/HOLD labels.
Stores results in PerCoinModelStore (filesystem-based).

Usage:
    trainer = AutoTrainerV5()
    metrics = trainer.train_coin("BTCUSDT")        # Single coin
    results = trainer.train_all_coins(tickers)      # All coins
    trainer.train_global_model(tickers)             # Train global fallback
"""

import asyncio
import time
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from loguru import logger

from config import settings
from src.models.ensemble_v5 import EnsembleV5
from src.models.labeling import TripleBarrierLabeler
from src.models.per_coin_model_store import PerCoinModelStore
from src.models.validation import PurgedWalkForwardCV
from src.data.features_v4 import FeatureEngineerV4


class AutoTrainerV5:
    """
    Per-coin ternary training engine.

    Trains one EnsembleV5 model per ticker.
    Falls back gracefully if a coin has insufficient data.
    """

    MIN_SAMPLES = 100          # Minimum labeled rows to train a coin
    LOOKBACK_DAYS = 730        # 2 years of daily OHLCV
    RATE_LIMIT_PAUSE = 10      # Seconds to pause every 5 tickers (Binance rate limit)

    def __init__(self, model_store: Optional[PerCoinModelStore] = None):
        self.store = model_store or PerCoinModelStore()
        self.labeler = TripleBarrierLabeler()
        self.feature_eng = FeatureEngineerV4()
        self._is_training = False

    @property
    def is_training(self) -> bool:
        return self._is_training

    # ============================================================
    # DATA FETCHING
    # ============================================================

    def _fetch_external_data_sync(self) -> Dict:
        """Fetch macro/derivatives/onchain/etc. data synchronously."""
        try:
            from src.data.macro_data import MacroDataFetcher
            from src.data.derivatives_fetcher import DerivativesFetcher
            from src.data.onchain_fetcher import OnChainFetcher
            from src.data.sentiment_fetcher import SentimentFetcher
            from src.data.defi_fetcher import DeFiFetcher

            async def _gather():
                macro_f = MacroDataFetcher()
                deriv_f = DerivativesFetcher()
                onchain_f = OnChainFetcher()
                sentiment_f = SentimentFetcher()
                defi_f = DeFiFetcher()
                results = await asyncio.gather(
                    macro_f.get_all_macro_data(),
                    deriv_f.get_all_derivatives_data(),
                    onchain_f.get_all_onchain_data(),
                    sentiment_f.get_all_sentiment_data(),
                    defi_f.get_all_defi_data(),
                    return_exceptions=True,
                )
                return {
                    "macro": results[0] if isinstance(results[0], dict) else {},
                    "derivatives": results[1] if isinstance(results[1], dict) else {},
                    "onchain": results[2] if isinstance(results[2], dict) else {},
                    "sentiment": results[3] if isinstance(results[3], dict) else {},
                    "defi": results[4] if isinstance(results[4], dict) else {},
                    "news": {},
                    "social": {},
                    "whale": {},
                }

            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    return pool.submit(lambda: asyncio.run(_gather())).result(timeout=120)
            except RuntimeError:
                return asyncio.run(_gather())
        except Exception as exc:
            logger.warning(f"External data fetch failed: {exc} — using empty dict")
            return {k: {} for k in ["macro", "derivatives", "onchain", "sentiment", "defi", "news", "social", "whale"]}

    def _fetch_ohlcv(self, ticker: str) -> pd.DataFrame:
        """Fetch OHLCV data for a single ticker."""
        from src.services.binance_data_service import BinanceDataService
        data_service = BinanceDataService()
        return data_service.get_historical_klines(ticker, "1d", self.LOOKBACK_DAYS)

    def _build_training_data(
        self,
        ticker: str,
        df: pd.DataFrame,
        btc_df: pd.DataFrame,
        eth_df: pd.DataFrame,
        external_data: Dict,
    ) -> Optional[Tuple[np.ndarray, np.ndarray, List[str], np.ndarray]]:
        """
        Build (X, y, feature_names, sample_weight) for a single ticker.

        Returns None if insufficient data.
        """
        try:
            if len(df) < 200:
                logger.warning(f"[V5] {ticker}: only {len(df)} OHLCV rows — skipping")
                return None

            # Calculate V4 features
            features_df = self.feature_eng.calculate_features_v4(
                df=df,
                btc_df=btc_df,
                eth_df=eth_df,
                macro_data=external_data.get("macro"),
                derivatives_data=external_data.get("derivatives"),
                onchain_data=external_data.get("onchain"),
                sentiment_data=external_data.get("sentiment"),
                defi_data=external_data.get("defi"),
                news_data=external_data.get("news"),
                social_data=external_data.get("social"),
                whale_data=external_data.get("whale"),
            )

            if features_df is None or len(features_df) < 200:
                logger.warning(f"[V5] {ticker}: features_df too small — skipping")
                return None

            # Apply ternary labels
            labeled_df = self.labeler.label_for_ternary(features_df)
            labeled_df = labeled_df.dropna(subset=["target"])

            if len(labeled_df) < self.MIN_SAMPLES:
                logger.warning(
                    f"[V5] {ticker}: only {len(labeled_df)} labeled rows "
                    f"(min={self.MIN_SAMPLES}) — skipping"
                )
                return None

            # Get feature matrix
            feature_vector_df = self.feature_eng.get_feature_vector_v4(labeled_df)
            X = feature_vector_df.values
            y = labeled_df["target"].values
            feature_names = list(feature_vector_df.columns)

            # Compute class weights for imbalanced labels
            class_weights = self.labeler.get_class_weights(labeled_df)
            sample_weight = np.array([class_weights[int(cls)] for cls in y])

            logger.info(
                f"[V5] {ticker}: {len(y)} samples, "
                f"LONG={int((y==1).sum())}, SHORT={int((y==2).sum())}, HOLD={int((y==0).sum())}"
            )

            return X, y, feature_names, sample_weight

        except Exception as e:
            logger.error(f"[V5] Failed to build training data for {ticker}: {e}")
            return None

    # ============================================================
    # SINGLE COIN TRAINING
    # ============================================================

    def train_coin(
        self,
        ticker: str,
        btc_df: Optional[pd.DataFrame] = None,
        eth_df: Optional[pd.DataFrame] = None,
        external_data: Optional[Dict] = None,
        cv: Optional[PurgedWalkForwardCV] = None,
    ) -> Optional[Dict]:
        """
        Train one EnsembleV5 for a single ticker.

        Args:
            ticker: Coin symbol (e.g., 'BTCUSDT')
            btc_df: BTC OHLCV (fetched if None)
            eth_df: ETH OHLCV (fetched if None)
            external_data: Macro/derivatives/etc. (fetched if None)
            cv: Walk-forward CV splitter (uses default if None)

        Returns:
            Training metrics dict, or None if training failed/skipped.
        """
        logger.info(f"[V5] Training coin: {ticker}")
        start = time.time()

        try:
            # Fetch OHLCV data
            coin_df = self._fetch_ohlcv(ticker)
            if btc_df is None:
                btc_df = self._fetch_ohlcv("BTCUSDT")
            if eth_df is None:
                eth_df = self._fetch_ohlcv("ETHUSDT")
            if external_data is None:
                external_data = self._fetch_external_data_sync()

            # Build training data
            result = self._build_training_data(ticker, coin_df, btc_df, eth_df, external_data)
            if result is None:
                return None

            X, y, feature_names, sample_weight = result

            # Train EnsembleV5
            if cv is None:
                cv = PurgedWalkForwardCV(n_splits=3, min_train_days=180, test_days=60)

            model = EnsembleV5()
            metrics = model.train(X, y, feature_names, cv=cv, sample_weight=sample_weight)

            # Save model to disk
            coin_dir = self.store.get_coin_dir(ticker)
            coin_dir.mkdir(parents=True, exist_ok=True)
            model.save(str(coin_dir))

            # Add extra metrics
            metrics["ticker"] = ticker
            metrics["n_samples"] = len(y)
            metrics["training_seconds"] = round(time.time() - start, 1)

            # Persist metrics + register in store
            self.store.save_metrics(ticker, metrics)
            self.store.register_coin(ticker, metrics)

            # Log delta vs previous run
            comparison = self.store.compare_runs(ticker)
            if comparison:
                delta = comparison.get("delta", {})
                logger.info(
                    f"[V5] {ticker} delta: "
                    f"long_f1={delta.get('delta_long_f1', 0):+.4f}, "
                    f"short_f1={delta.get('delta_short_f1', 0):+.4f}"
                )

            elapsed = time.time() - start
            logger.success(
                f"[V5] {ticker} trained in {elapsed:.1f}s — "
                f"acc={metrics['oos_accuracy']:.4f} "
                f"long_f1={metrics['long_f1']:.4f} short_f1={metrics['short_f1']:.4f}"
            )

            return metrics

        except Exception as e:
            logger.error(f"[V5] Training failed for {ticker}: {e}")
            return None

    # ============================================================
    # BULK TRAINING
    # ============================================================

    def train_all_coins(
        self,
        tickers: Optional[List[str]] = None,
        resume: bool = True,
    ) -> Dict[str, Optional[Dict]]:
        """
        Train EnsembleV5 for all tickers.

        Args:
            tickers: List of coin symbols. Defaults to settings.TICKERS.
            resume: If True, skip coins that already have a model trained today.

        Returns:
            Dict mapping ticker -> metrics dict (or None if skipped/failed).
        """
        tickers = tickers or list(settings.TICKERS)
        self._is_training = True
        results = {}

        logger.info(f"[V5] Training {len(tickers)} coins (resume={resume})...")
        start_all = time.time()

        # Fetch shared data ONCE for all coins (saves many API calls)
        logger.info("[V5] Fetching shared data (BTC, ETH, external)...")
        btc_df = self._fetch_ohlcv("BTCUSDT")
        eth_df = self._fetch_ohlcv("ETHUSDT")
        external_data = self._fetch_external_data_sync()

        # Shared walk-forward CV (more splits = better OOS estimate but slower)
        cv = PurgedWalkForwardCV(n_splits=3, min_train_days=180, test_days=60)

        for i, ticker in enumerate(tickers):
            # Optional: skip coins already trained recently
            if resume and self.store.has_model(ticker):
                latest = self.store.get_latest_metrics(ticker)
                if latest:
                    trained_at = latest.get("timestamp", "")
                    today = time.strftime("%Y-%m-%d")
                    if trained_at.startswith(today):
                        logger.info(f"[V5] {ticker}: already trained today — skipping")
                        results[ticker] = latest
                        continue

            # Train this coin
            metrics = self.train_coin(
                ticker=ticker,
                btc_df=btc_df,
                eth_df=eth_df,
                external_data=external_data,
                cv=cv,
            )
            results[ticker] = metrics

            # Rate limit: pause every 5 tickers
            if (i + 1) % 5 == 0:
                logger.info(f"[V5] Trained {i+1}/{len(tickers)} — pausing {self.RATE_LIMIT_PAUSE}s")
                time.sleep(self.RATE_LIMIT_PAUSE)

        self._is_training = False
        elapsed = time.time() - start_all

        trained_count = sum(1 for v in results.values() if v is not None)
        failed_count = len(tickers) - trained_count

        logger.success(
            f"[V5] Bulk training complete: {trained_count} trained, {failed_count} failed/skipped "
            f"in {elapsed:.1f}s"
        )

        return results

    def train_global_model(
        self,
        tickers: Optional[List[str]] = None,
        cv: Optional[PurgedWalkForwardCV] = None,
    ) -> Optional[Dict]:
        """
        Train a global EnsembleV5 on ALL coins combined (fallback model).

        This is the model that gets used for coins without a per-coin model.
        Saved to {base_dir}/global/.
        """
        tickers = tickers or list(settings.TICKERS)
        logger.info(f"[V5] Training global model on {len(tickers)} coins...")
        start = time.time()

        # Fetch shared data
        btc_df = self._fetch_ohlcv("BTCUSDT")
        eth_df = self._fetch_ohlcv("ETHUSDT")
        external_data = self._fetch_external_data_sync()

        all_X, all_y, all_weights = [], [], []
        feature_names = None

        for ticker in tickers:
            try:
                coin_df = self._fetch_ohlcv(ticker)
                result = self._build_training_data(ticker, coin_df, btc_df, eth_df, external_data)
                if result is None:
                    continue
                X, y, fnames, weights = result
                all_X.append(X)
                all_y.append(y)
                all_weights.append(weights)
                if feature_names is None:
                    feature_names = fnames
            except Exception as e:
                logger.warning(f"[V5] Global model: failed to process {ticker}: {e}")

        if not all_X:
            logger.error("[V5] Global model: no training data — aborting")
            return None

        X_all = np.vstack(all_X)
        y_all = np.concatenate(all_y)
        w_all = np.concatenate(all_weights)

        if cv is None:
            cv = PurgedWalkForwardCV(n_splits=3, min_train_days=180, test_days=60)

        model = EnsembleV5()
        metrics = model.train(X_all, y_all, feature_names, cv=cv, sample_weight=w_all)

        # Save to global/ subdirectory
        global_dir = self.store.get_global_dir()
        global_dir.mkdir(parents=True, exist_ok=True)
        model.save(str(global_dir))

        metrics["n_samples"] = len(y_all)
        metrics["n_tickers"] = len(all_X)
        metrics["training_seconds"] = round(time.time() - start, 1)

        logger.success(
            f"[V5] Global model trained on {len(all_X)} coins ({len(y_all)} samples) "
            f"in {metrics['training_seconds']}s — acc={metrics['oos_accuracy']:.4f}"
        )
        return metrics
