#!/usr/bin/env python3
"""
ML PIPELINE V4 — TRAINING SCRIPT
===================================
Complete training pipeline for the V4 ensemble model.

Usage:
    python scripts/train_model.py [--mode full|quick] [--output-dir path]

Pipeline steps:
1. Data collection — fetch 2+ years of daily data
2. Feature engineering — FeatureEngineerV4
3. Labeling — Triple-barrier (ATR-based)
4. Feature selection — SHAP + Boruta (full mode only)
5. Hyperparameter optimization — Optuna (full mode only)
6. Model training — XGBoost + LightGBM + CatBoost with walk-forward CV
7. Ensemble — Train meta-learner on OOS predictions
8. Regime model — Train HMM on BTC data
9. Evaluation — Print per-fold + aggregate metrics
10. Save — Model artifacts + feature config + metrics
"""

import sys
import os
import json
import time
import argparse
import asyncio
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

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
from src.models.labeling import TripleBarrierLabeler
from src.models.validation import PurgedWalkForwardCV
from src.models.ensemble import EnsembleModel
from src.models.regime_detector import RegimeDetector


def parse_args():
    parser = argparse.ArgumentParser(description="Train V4 Ensemble Model")
    parser.add_argument(
        "--mode", choices=["full", "quick"], default="quick",
        help="full = feature selection + hyperopt (slow); quick = defaults (fast)"
    )
    parser.add_argument(
        "--output-dir", default=str(PROJECT_ROOT / "PRODUCTION_SYSTEM" / "models" / "v4"),
        help="Directory to save model artifacts"
    )
    parser.add_argument(
        "--lookback-days", type=int, default=730,
        help="Days of historical data (default: 730 = 2 years)"
    )
    parser.add_argument(
        "--max-tickers", type=int, default=0,
        help="Max tickers to process (0 = all)"
    )
    return parser.parse_args()


def fetch_all_data(lookback_days: int, max_tickers: int = 0) -> dict:
    """Fetch all required data"""
    from src.services.binance_data_service import BinanceDataService

    data_service = BinanceDataService()

    tickers = settings.TICKERS
    if max_tickers > 0:
        tickers = tickers[:max_tickers]

    logger.info(f"Fetching data for {len(tickers)} tickers ({lookback_days} days)...")

    # Fetch BTC + ETH reference data
    btc_data = data_service.get_historical_klines("BTCUSDT", "1d", lookback_days)
    eth_data = data_service.get_historical_klines("ETHUSDT", "1d", lookback_days)
    logger.info(f"BTC: {len(btc_data)} rows, ETH: {len(eth_data)} rows")

    # Fetch ticker data
    tickers_data = {}
    for ticker in tickers:
        try:
            df = data_service.get_historical_klines(ticker, "1d", lookback_days)
            if len(df) >= 200:
                tickers_data[ticker] = df
                logger.debug(f"  {ticker}: {len(df)} rows")
            else:
                logger.warning(f"  {ticker}: insufficient data ({len(df)} rows)")
        except Exception as e:
            logger.error(f"  {ticker}: failed — {e}")

    logger.info(f"Fetched {len(tickers_data)} tickers successfully")

    # Fetch external data (async)
    external_data = asyncio.run(_fetch_external_data())

    return {
        "btc_data": btc_data,
        "eth_data": eth_data,
        "tickers_data": tickers_data,
        "external": external_data,
    }


async def _fetch_external_data() -> dict:
    """Fetch all external data sources (including news, social, whale)"""
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


def build_training_dataset(data: dict) -> tuple:
    """Build feature matrix and labels from all tickers"""
    feature_eng = FeatureEngineerV4()
    labeler = TripleBarrierLabeler()

    btc_data = data["btc_data"]
    eth_data = data["eth_data"]
    ext = data["external"]

    all_X = []
    all_y = []
    all_meta = []

    for ticker, df in data["tickers_data"].items():
        logger.info(f"Processing {ticker}...")

        # Calculate features (all 89 including news/social/whale)
        features_df = feature_eng.calculate_features_v4(
            df=df,
            btc_df=btc_data,
            eth_df=eth_data,
            macro_data=ext.get("macro"),
            derivatives_data=ext.get("derivatives"),
            onchain_data=ext.get("onchain"),
            sentiment_data=ext.get("sentiment"),
            defi_data=ext.get("defi"),
            news_data=ext.get("news"),
            social_data=ext.get("social"),
            whale_data=ext.get("whale"),
        )

        if len(features_df) < 200:
            logger.warning(f"  {ticker}: not enough data after features ({len(features_df)})")
            continue

        # Apply labels
        labeled_df = labeler.label_for_binary(features_df)
        labeled_df = labeled_df.dropna(subset=["target"])

        if len(labeled_df) < 100:
            logger.warning(f"  {ticker}: not enough labeled data ({len(labeled_df)})")
            continue

        # Extract feature vector
        feature_vector = feature_eng.get_feature_vector_v4(labeled_df)
        target = labeled_df["target"].values

        all_X.append(feature_vector.values)
        all_y.append(target)
        all_meta.append({"ticker": ticker, "n_samples": len(target)})

        tp_rate = target.mean()
        logger.info(f"  {ticker}: {len(target)} samples, TP rate={tp_rate:.2%}")

    if not all_X:
        raise ValueError("No training data available!")

    X = np.vstack(all_X)
    y = np.concatenate(all_y)
    feature_names = feature_eng.selected_features or feature_eng.required_features_v4

    logger.info(f"Training dataset: {X.shape[0]} samples, {X.shape[1]} features")
    logger.info(f"  Positive rate: {y.mean():.2%}")

    return X, y, feature_names, all_meta


def train_pipeline(args):
    """Main training pipeline"""
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    start_time = time.time()

    # Step 1: Data collection
    logger.info("=" * 60)
    logger.info("STEP 1: DATA COLLECTION")
    logger.info("=" * 60)
    data = fetch_all_data(args.lookback_days, args.max_tickers)

    # Step 2-3: Feature engineering + Labeling
    logger.info("=" * 60)
    logger.info("STEP 2-3: FEATURE ENGINEERING + LABELING")
    logger.info("=" * 60)
    X, y, feature_names, meta = build_training_dataset(data)

    # Step 4: Feature selection (full mode only)
    if args.mode == "full":
        logger.info("=" * 60)
        logger.info("STEP 4: FEATURE SELECTION (SHAP + Boruta)")
        logger.info("=" * 60)
        from src.models.feature_selection import FeatureSelector
        selector = FeatureSelector()
        X_df = pd.DataFrame(X, columns=feature_names)
        selected = selector.select_features(X_df, y, feature_names)
        selector.save_selection(str(PROJECT_ROOT / "configs" / "feature_config_v4.json"))

        # Filter X to selected features
        selected_indices = [feature_names.index(f) for f in selected]
        X = X[:, selected_indices]
        feature_names = selected
        logger.info(f"Selected {len(feature_names)} features")

    # Step 5: Hyperparameter optimization (full mode only)
    best_params = {}
    if args.mode == "full":
        logger.info("=" * 60)
        logger.info("STEP 5: HYPERPARAMETER OPTIMIZATION")
        logger.info("=" * 60)
        from src.models.hyperopt import HyperOptimizer
        from sklearn.metrics import roc_auc_score

        cv = PurgedWalkForwardCV(n_splits=5)
        optimizer = HyperOptimizer(n_trials=50, cv_splitter=cv, metric_fn=roc_auc_score)
        best_params = optimizer.optimize_all(X, y)
        optimizer.save_params(str(output_dir / "best_params.json"))

    # Step 6-7: Model training + Ensemble
    logger.info("=" * 60)
    logger.info("STEP 6-7: ENSEMBLE TRAINING")
    logger.info("=" * 60)
    cv = PurgedWalkForwardCV(n_splits=5)
    ensemble = EnsembleModel(params=best_params)
    ensemble.train(X, y, feature_names, cv=cv)

    # Step 8: Regime detection
    logger.info("=" * 60)
    logger.info("STEP 8: REGIME DETECTOR (HMM)")
    logger.info("=" * 60)
    regime_detector = RegimeDetector()
    btc_data = data["btc_data"]
    if len(btc_data) >= 200:
        regime_detector.train(btc_data)
        regime_data = regime_detector.predict(btc_data)
        logger.info(f"Current regime: {regime_data['regime_name']}")
    else:
        logger.warning("Not enough BTC data for regime detection")

    # Step 9: Evaluation
    logger.info("=" * 60)
    logger.info("STEP 9: EVALUATION")
    logger.info("=" * 60)
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
    }

    # Walk-forward CV evaluation
    def auc_metric(y_true, y_pred):
        try:
            return roc_auc_score(y_true, y_pred)
        except ValueError:
            return 0.5

    import xgboost as xgb
    cv_result = cv.cross_validate(
        X, y,
        model_factory=lambda: xgb.XGBClassifier(
            n_estimators=300, max_depth=5, use_label_encoder=False,
            eval_metric="logloss", random_state=42
        ),
        metric_fn=auc_metric,
    )
    metrics["cv_mean_auc"] = cv_result["mean_score"]
    metrics["cv_std_auc"] = cv_result["std_score"]
    metrics["cv_folds"] = cv_result["fold_metrics"]

    logger.info(f"  AUC-ROC: {metrics['auc_roc']:.4f}")
    logger.info(f"  Accuracy: {metrics['accuracy']:.4f}")
    logger.info(f"  Precision: {metrics['precision']:.4f}")
    logger.info(f"  Recall: {metrics['recall']:.4f}")
    logger.info(f"  F1: {metrics['f1']:.4f}")
    logger.info(f"  CV AUC: {metrics['cv_mean_auc']:.4f} +/- {metrics['cv_std_auc']:.4f}")

    # Step 10: Save
    logger.info("=" * 60)
    logger.info("STEP 10: SAVING MODEL ARTIFACTS")
    logger.info("=" * 60)

    ensemble.save(str(output_dir))
    regime_detector.save(str(output_dir / "regime_detector.pkl"))

    # Save metrics
    metrics["training_time_seconds"] = time.time() - start_time
    metrics["training_mode"] = args.mode
    metrics["timestamp"] = datetime.now(timezone.utc).isoformat()
    metrics["tickers_used"] = [m["ticker"] for m in meta]

    with open(output_dir / "training_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2, default=str)

    # Save feature names
    with open(output_dir / "feature_names.json", "w") as f:
        json.dump(feature_names, f, indent=2)

    elapsed = time.time() - start_time
    logger.success(f"Training complete in {elapsed:.0f}s")
    logger.success(f"Artifacts saved to {output_dir}")

    # Print summary
    print("\n" + "=" * 60)
    print("TRAINING SUMMARY")
    print("=" * 60)
    print(f"  Mode:       {args.mode}")
    print(f"  Tickers:    {len(meta)}")
    print(f"  Samples:    {len(y)}")
    print(f"  Features:   {X.shape[1]}")
    print(f"  AUC-ROC:    {metrics['auc_roc']:.4f}")
    print(f"  CV AUC:     {metrics['cv_mean_auc']:.4f} +/- {metrics['cv_std_auc']:.4f}")
    print(f"  Time:       {elapsed:.0f}s")
    print(f"  Output:     {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    # Setup logging
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    args = parse_args()
    train_pipeline(args)
