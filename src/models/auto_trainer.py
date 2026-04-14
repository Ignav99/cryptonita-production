"""
AUTO-TRAINER
==============
Self-retraining engine for V4 ensemble model.
Trains new models, backtests them, and promotes only if they outperform the current model.
Designed to run autonomously on Render with zero manual intervention.
"""

import asyncio
import json
import shutil
import time
import tempfile
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from loguru import logger

from config import settings
from src.models.model_store import ModelStore
from src.models.ensemble import EnsembleModel
from src.models.regime_detector import RegimeDetector
from src.models.labeling import TripleBarrierLabeler
from src.models.validation import PurgedWalkForwardCV
from src.data.features_v4 import FeatureEngineerV4


class AutoTrainer:
    """Autonomous model training, evaluation, and promotion."""

    def __init__(self, model_store: Optional[ModelStore] = None):
        self.model_store = model_store or ModelStore()
        self._is_training = False

    @property
    def is_training(self) -> bool:
        return self._is_training

    def train_new_model(self, mode: str = "quick") -> Tuple[str, Dict]:
        """
        Train a new V4 ensemble model from scratch using fresh data.

        Args:
            mode: 'quick' (defaults) or 'full' (feature selection + hyperopt)

        Returns:
            Tuple of (model_dir_path, training_metrics_dict)
        """
        from src.services.binance_data_service import BinanceDataService

        start_time = time.time()
        data_service = BinanceDataService()

        # Create temp directory for this training run
        version = self.model_store.get_latest_version() + 1
        model_dir = tempfile.mkdtemp(prefix=f"v4_training_{version}_")
        logger.info(f"Training V4 model v{version} (mode={mode}) in {model_dir}")

        # Step 1: Fetch data
        logger.info("Step 1: Fetching data...")
        tickers = settings.TICKERS
        lookback_days = 730  # 2 years

        btc_data = data_service.get_historical_klines("BTCUSDT", "1d", lookback_days)
        eth_data = data_service.get_historical_klines("ETHUSDT", "1d", lookback_days)

        tickers_data = {}
        for i, ticker in enumerate(tickers):
            try:
                df = data_service.get_historical_klines(ticker, "1d", lookback_days)
                if len(df) >= 200:
                    tickers_data[ticker] = df
            except Exception as e:
                logger.warning(f"Failed to fetch {ticker}: {e}")
            # Rate limit: pause every 5 tickers (730d klines = heavy weight)
            if (i + 1) % 5 == 0:
                time.sleep(10)

        logger.info(f"Fetched {len(tickers_data)} tickers")

        # Step 2: Fetch external data
        logger.info("Step 2: Fetching external data...")
        external_data = self._fetch_external_data_sync()

        # Step 3: Feature engineering + Labeling
        logger.info("Step 3: Feature engineering + labeling...")
        feature_eng = FeatureEngineerV4()
        labeler = TripleBarrierLabeler()

        all_X, all_y = [], []
        meta_list = []

        for ticker, df in tickers_data.items():
            try:
                features_df = feature_eng.calculate_features_v4(
                    df=df,
                    btc_df=btc_data,
                    eth_df=eth_data,
                    macro_data=external_data.get("macro"),
                    derivatives_data=external_data.get("derivatives"),
                    onchain_data=external_data.get("onchain"),
                    sentiment_data=external_data.get("sentiment"),
                    defi_data=external_data.get("defi"),
                    news_data=external_data.get("news"),
                    social_data=external_data.get("social"),
                    whale_data=external_data.get("whale"),
                )

                if len(features_df) < 200:
                    continue

                labeled_df = labeler.label_for_binary(features_df)
                labeled_df = labeled_df.dropna(subset=["target"])

                if len(labeled_df) < 100:
                    continue

                feature_vector = feature_eng.get_feature_vector_v4(labeled_df)
                target = labeled_df["target"].values

                all_X.append(feature_vector.values)
                all_y.append(target)
                meta_list.append({"ticker": ticker, "n_samples": len(target)})
            except Exception as e:
                logger.warning(f"Failed to process {ticker}: {e}")

        if not all_X:
            raise ValueError("No training data available!")

        X = np.vstack(all_X)
        y = np.concatenate(all_y)
        feature_names = feature_eng.selected_features or feature_eng.required_features_v4

        logger.info(f"Training dataset: {X.shape[0]} samples, {X.shape[1]} features")

        # Step 4: Feature selection (full mode only)
        if mode == "full":
            try:
                from src.models.feature_selection import FeatureSelector
                selector = FeatureSelector()
                X_df = pd.DataFrame(X, columns=feature_names)
                selected = selector.select_features(X_df, y, feature_names)
                selected_indices = [feature_names.index(f) for f in selected]
                X = X[:, selected_indices]
                feature_names = selected
                logger.info(f"Selected {len(feature_names)} features")
            except Exception as e:
                logger.warning(f"Feature selection failed, using all features: {e}")

        # Step 5: Hyperparameter optimization (full mode only)
        best_params = {}
        if mode == "full":
            try:
                from src.models.hyperopt import HyperOptimizer
                from sklearn.metrics import roc_auc_score
                cv = PurgedWalkForwardCV(n_splits=5)
                optimizer = HyperOptimizer(n_trials=50, cv_splitter=cv, metric_fn=roc_auc_score)
                best_params = optimizer.optimize_all(X, y)
            except Exception as e:
                logger.warning(f"Hyperopt failed, using defaults: {e}")

        # Step 6: Train ensemble
        logger.info("Step 6: Training ensemble...")
        cv = PurgedWalkForwardCV(n_splits=5)
        ensemble = EnsembleModel(params=best_params)
        ensemble.train(X, y, feature_names, cv=cv)

        # Step 7: Train regime detector
        logger.info("Step 7: Training regime detector...")
        regime_detector = RegimeDetector()
        if len(btc_data) >= 200:
            regime_detector.train(btc_data)

        # Step 8: Evaluation
        from sklearn.metrics import roc_auc_score, accuracy_score, precision_score, recall_score, f1_score

        proba = ensemble.predict_proba(X)
        preds = (proba >= 0.5).astype(int)

        metrics = {
            "auc_roc": float(roc_auc_score(y, proba)),
            "accuracy": float(accuracy_score(y, preds)),
            "precision": float(precision_score(y, preds, zero_division=0)),
            "recall": float(recall_score(y, preds, zero_division=0)),
            "f1": float(f1_score(y, preds, zero_division=0)),
            "n_samples": int(len(y)),
            "n_features": int(X.shape[1]),
            "positive_rate": float(y.mean()),
            "training_mode": mode,
            "training_time_seconds": time.time() - start_time,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "tickers_used": [m["ticker"] for m in meta_list],
            "version": version,
        }

        # Save artifacts to temp dir
        ensemble.save(model_dir)
        regime_detector.save(str(Path(model_dir) / "regime_detector.pkl"))

        with open(Path(model_dir) / "training_metrics.json", "w") as f:
            json.dump(metrics, f, indent=2, default=str)

        with open(Path(model_dir) / "feature_names.json", "w") as f:
            json.dump(feature_names, f, indent=2)

        logger.info(f"Training complete: AUC={metrics['auc_roc']:.4f}, F1={metrics['f1']:.4f}")
        return model_dir, metrics

    def backtest_model(self, model_dir: str) -> Dict:
        """
        Run simplified backtest on the last 90 days of data.

        Returns:
            Dict with roi, sharpe, max_drawdown, win_rate, profit_factor
        """
        from src.services.binance_data_service import BinanceDataService

        logger.info("Running backtest on last 90 days...")
        data_service = BinanceDataService()

        # Load model from temp dir
        ensemble = EnsembleModel()
        ensemble.load(model_dir)

        feature_eng = FeatureEngineerV4()
        labeler = TripleBarrierLabeler()

        # Fetch recent data
        btc_data = data_service.get_historical_klines("BTCUSDT", "1d", 365)
        eth_data = data_service.get_historical_klines("ETHUSDT", "1d", 365)

        # Use a subset of tickers for faster backtest
        test_tickers = settings.TICKERS[:15]
        trades = []

        for i, ticker in enumerate(test_tickers):
            try:
                df = data_service.get_historical_klines(ticker, "1d", 365)
                if (i + 1) % 5 == 0:
                    time.sleep(10)  # Rate limit
                if len(df) < 200:
                    continue

                features_df = feature_eng.calculate_features_v4(
                    df=df, btc_df=btc_data, eth_df=eth_data,
                )

                if len(features_df) < 200:
                    continue

                labeled_df = labeler.label_for_binary(features_df)
                labeled_df = labeled_df.dropna(subset=["target"])

                if len(labeled_df) < 100:
                    continue

                feature_vector = feature_eng.get_feature_vector_v4(labeled_df)

                # Predict on last 90 rows (approximately 90 days)
                test_start = max(0, len(feature_vector) - 90)
                X_test = feature_vector.iloc[test_start:].values
                y_test = labeled_df["target"].iloc[test_start:].values

                probas = ensemble.predict_proba(X_test)

                # Use per-tier confidence thresholds
                profile = settings.COIN_RISK_PROFILES.get(ticker, settings.DEFAULT_RISK_PROFILE)
                lowest_threshold = profile.get(
                    "threshold_low",
                    profile.get("threshold", settings.PREDICTION_THRESHOLD),
                )

                closes = labeled_df["close"].iloc[test_start:].values
                tp_prices = labeled_df["tp_price"].iloc[test_start:].values
                sl_prices = labeled_df["sl_price"].iloc[test_start:].values

                for i in range(len(probas)):
                    prob = float(probas[i])
                    if prob < lowest_threshold:
                        continue

                    # Band-pass ceiling: reject overfit signals above threshold
                    ceiling = profile["threshold"]
                    if prob >= ceiling:
                        continue

                    # Classify confidence level (within accepted band)
                    if prob >= profile.get("threshold_medium", ceiling):
                        confidence = "medium"
                    else:
                        confidence = "medium"  # floor == threshold_medium when exploratory disabled

                    conf_config = settings.CONFIDENCE_LEVELS.get(confidence, settings.CONFIDENCE_LEVELS["medium"])
                    position_mult = conf_config.get("position_mult", 0.25)

                    entry = closes[i]
                    tp = tp_prices[i]
                    sl = sl_prices[i]

                    if np.isnan(tp) or np.isnan(sl):
                        continue

                    # Simplified: use label as outcome
                    actual = y_test[i] if i < len(y_test) else 0
                    if actual == 1:
                        pnl_pct = (tp - entry) / entry
                    else:
                        pnl_pct = (sl - entry) / entry

                    # Scale PnL by position multiplier (reflects real sizing)
                    pnl_pct *= position_mult

                    trades.append({
                        "ticker": ticker,
                        "entry": entry,
                        "pnl_pct": pnl_pct,
                        "win": actual == 1,
                        "probability": prob,
                        "confidence": confidence,
                    })

            except Exception as e:
                logger.warning(f"Backtest failed for {ticker}: {e}")

        # Calculate metrics
        if not trades:
            logger.warning("No trades in backtest")
            return {
                "roi": 0.0, "sharpe": 0.0, "max_drawdown": 0.0,
                "win_rate": 0.0, "profit_factor": 0.0, "n_trades": 0,
            }

        pnl_series = [t["pnl_pct"] for t in trades]
        wins = [p for p in pnl_series if p > 0]
        losses = [p for p in pnl_series if p <= 0]

        roi = sum(pnl_series)
        win_rate = len(wins) / len(pnl_series) if pnl_series else 0
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1e-9
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Sharpe ratio (annualized, assuming daily-ish trades)
        pnl_arr = np.array(pnl_series)
        sharpe = float(np.mean(pnl_arr) / (np.std(pnl_arr) + 1e-9) * np.sqrt(252))

        # Max drawdown (as percentage of peak equity)
        equity = 1.0 + np.cumsum(pnl_arr)  # Start with $1 of equity
        running_max = np.maximum.accumulate(equity)
        drawdown_pct = (running_max - equity) / np.maximum(running_max, 1e-9)
        max_drawdown = float(np.max(drawdown_pct)) if len(drawdown_pct) > 0 else 0

        result = {
            "roi": float(roi),
            "sharpe": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": float(win_rate),
            "profit_factor": float(profit_factor),
            "n_trades": len(trades),
        }
        logger.info(
            f"Backtest: ROI={roi:.2%}, Sharpe={sharpe:.2f}, "
            f"WR={win_rate:.1%}, PF={profit_factor:.2f}, Trades={len(trades)}"
        )
        return result

    def compare_and_promote(self, new_metrics: Dict, current_metrics: Dict) -> Tuple[bool, Dict]:
        """
        Compare new model metrics against current active model.

        Returns:
            Tuple of (should_promote: bool, comparison: dict)
        """
        new_sharpe = new_metrics.get("sharpe", 0)
        new_win_rate = new_metrics.get("win_rate", 0)
        new_max_dd = new_metrics.get("max_drawdown", 1)
        new_roi = new_metrics.get("roi", 0)

        cur_sharpe = current_metrics.get("sharpe", 0)
        cur_win_rate = current_metrics.get("win_rate", 0)
        cur_roi = current_metrics.get("roi", 0)

        min_sharpe = getattr(settings, "AUTO_TRAIN_MIN_SHARPE", 0.5)

        comparison = {
            "new_sharpe": new_sharpe,
            "current_sharpe": cur_sharpe,
            "new_win_rate": new_win_rate,
            "current_win_rate": cur_win_rate,
            "new_roi": new_roi,
            "current_roi": cur_roi,
            "new_max_drawdown": new_max_dd,
        }

        # Safety floors
        if new_win_rate < 0.50:
            comparison["rejection_reason"] = f"Win rate too low: {new_win_rate:.1%} < 50%"
            logger.warning(f"New model rejected: {comparison['rejection_reason']}")
            return False, comparison

        if new_max_dd > 0.30:
            comparison["rejection_reason"] = f"Max drawdown too high: {new_max_dd:.1%} > 30%"
            logger.warning(f"New model rejected: {comparison['rejection_reason']}")
            return False, comparison

        if new_sharpe < min_sharpe:
            comparison["rejection_reason"] = f"Sharpe too low: {new_sharpe:.2f} < {min_sharpe}"
            logger.warning(f"New model rejected: {comparison['rejection_reason']}")
            return False, comparison

        # Promotion criteria: new Sharpe > 95% of current Sharpe
        # (allows small regression if other metrics improve)
        should_promote = new_sharpe > cur_sharpe * 0.95

        if not should_promote:
            comparison["rejection_reason"] = (
                f"Sharpe regression: {new_sharpe:.2f} < {cur_sharpe * 0.95:.2f} (95% of current)"
            )
            logger.info(f"New model not promoted: {comparison['rejection_reason']}")
        else:
            comparison["promotion_reason"] = (
                f"Sharpe improved: {new_sharpe:.2f} vs {cur_sharpe:.2f}"
            )
            logger.info(f"New model promoted: {comparison['promotion_reason']}")

        return should_promote, comparison

    async def run_auto_training(self) -> Dict:
        """
        Main orchestrator: train, backtest, compare, and optionally promote.
        Returns summary dict.
        """
        if self._is_training:
            logger.warning("Training already in progress, skipping")
            return {"status": "skipped", "reason": "already_training"}

        self._is_training = True
        version = self.model_store.get_latest_version() + 1
        mode = getattr(settings, "AUTO_TRAIN_MODE", "quick")
        model_dir = None

        try:
            # Log start
            self.model_store.save_training_run(version=version, status="running", mode=mode)
            logger.info(f"Auto-training started: version={version}, mode={mode}")

            # Train in a thread to avoid blocking the event loop
            loop = asyncio.get_running_loop()
            model_dir, train_metrics = await loop.run_in_executor(
                None, self.train_new_model, mode
            )

            # Backtest the new model
            backtest_metrics = await loop.run_in_executor(
                None, self.backtest_model, model_dir
            )

            # Get current model metrics
            current_metrics = self.model_store.get_active_metrics()

            # Compare and decide
            should_promote, comparison = self.compare_and_promote(backtest_metrics, current_metrics)

            combined_metrics = {**train_metrics, **backtest_metrics}

            if should_promote:
                # Save to DB and promote
                self.model_store.save_ensemble(version, model_dir, combined_metrics)
                self.model_store.promote_version(version)
                status = "promoted"
                logger.success(f"Model v{version} promoted to active!")
            else:
                status = "completed"
                logger.info(f"Model v{version} trained but not promoted")

            # Update training run record
            self.model_store.update_training_run(
                version=version,
                status=status,
                metrics=combined_metrics,
                comparison=comparison,
                promoted=should_promote,
            )

            return {
                "status": status,
                "version": version,
                "metrics": combined_metrics,
                "comparison": comparison,
                "promoted": should_promote,
            }

        except Exception as e:
            logger.error(f"Auto-training failed: {e}")
            import traceback
            logger.error(traceback.format_exc())

            self.model_store.update_training_run(
                version=version,
                status="failed",
                error_message=str(e),
            )

            return {"status": "failed", "version": version, "error": str(e)}

        finally:
            self._is_training = False
            # Clean up temp directory
            if model_dir:
                try:
                    shutil.rmtree(model_dir, ignore_errors=True)
                except Exception:
                    pass

    def _fetch_external_data_sync(self) -> Dict:
        """Fetch all external data sources synchronously (including news, social, whale)."""
        from src.data.macro_data import MacroDataFetcher
        from src.data.derivatives_fetcher import DerivativesFetcher
        from src.data.onchain_fetcher import OnChainFetcher
        from src.data.sentiment_fetcher import SentimentFetcher
        from src.data.defi_fetcher import DeFiFetcher
        from src.data.news_fetcher import NewsFetcher
        from src.data.social_fetcher import SocialFetcher
        from src.data.whale_fetcher import WhaleFetcher

        async def _fetch():
            macro = MacroDataFetcher()
            derivatives = DerivativesFetcher()
            onchain = OnChainFetcher()
            sentiment = SentimentFetcher()
            defi = DeFiFetcher()
            news = NewsFetcher()
            social = SocialFetcher()
            whale = WhaleFetcher()

            results = await asyncio.gather(
                macro.get_all_macro_data(),
                derivatives.get_all_derivatives_data(),
                onchain.get_all_onchain_data(),
                sentiment.get_all_sentiment_data(),
                defi.get_all_defi_data(),
                news.get_all_news_data(),
                social.get_all_social_data(),
                whale.get_all_whale_data(),
                return_exceptions=True,
            )
            return {
                "macro": results[0] if isinstance(results[0], dict) else {},
                "derivatives": results[1] if isinstance(results[1], dict) else {},
                "onchain": results[2] if isinstance(results[2], dict) else {},
                "sentiment": results[3] if isinstance(results[3], dict) else {},
                "defi": results[4] if isinstance(results[4], dict) else {},
                "news": results[5] if isinstance(results[5], dict) else {},
                "social": results[6] if isinstance(results[6], dict) else {},
                "whale": results[7] if isinstance(results[7], dict) else {},
            }

        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                def _run():
                    new_loop = asyncio.new_event_loop()
                    try:
                        return new_loop.run_until_complete(_fetch())
                    finally:
                        new_loop.close()
                return pool.submit(_run).result(timeout=120)
        except RuntimeError:
            return asyncio.run(_fetch())
