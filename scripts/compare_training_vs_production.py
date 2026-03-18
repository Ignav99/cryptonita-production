#!/usr/bin/env python3
"""
Compare Training Data vs Production Data
=========================================
Script para comparar las distribuciones de features entre el entrenamiento
y los datos actuales de producción.

Esto ayudará a identificar si el modelo está recibiendo datos muy diferentes
a los que fue entrenado.

Usage:
    python scripts/compare_training_vs_production.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import pandas as pd
import numpy as np
from loguru import logger
from datetime import datetime

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_data_service import BinanceDataService
from src.data.features import FeatureEngineer
from src.data.macro_data import MacroDataFetcher


def load_signals_features():
    """Load features from recent signals in database"""
    logger.info("Loading features from database signals...")

    db = DatabaseManager(settings.get_database_url())

    query = """
    SELECT id, ticker, probability, features, timestamp
    FROM signals
    WHERE features IS NOT NULL
    ORDER BY timestamp DESC
    LIMIT 500
    """

    df = db.execute_query(query)

    if len(df) == 0:
        logger.warning("No signals found in database")
        return None

    # Parse features
    features_list = []
    for idx, row in df.iterrows():
        try:
            if isinstance(row['features'], str):
                feat_dict = json.loads(row['features'])
            else:
                feat_dict = row['features'] or {}
            feat_dict['probability'] = float(row['probability'])
            feat_dict['ticker'] = row['ticker']
            features_list.append(feat_dict)
        except Exception as e:
            continue

    return pd.DataFrame(features_list)


def calculate_current_features():
    """Calculate features for current market data"""
    logger.info("Calculating features from current market data...")

    binance_data = BinanceDataService()
    feature_engineer = FeatureEngineer()
    macro_fetcher = MacroDataFetcher()

    # Get macro data
    macro_data = macro_fetcher.get_all_macro_data_sync()
    logger.info(f"Macro data: {macro_data}")

    # Get BTC data for correlation
    btc_data = binance_data.get_historical_klines('BTCUSDT', '1d', 250)

    # Calculate features for all tickers
    features_list = []
    for ticker in settings.TICKERS[:20]:  # Test with first 20
        try:
            ticker_data = binance_data.get_historical_klines(ticker, '1d', 250)
            if len(ticker_data) < 200:
                continue

            features = feature_engineer.calculate_single_prediction_features(
                ticker_data=ticker_data,
                btc_data=btc_data,
                macro_data=macro_data
            )

            if features is not None:
                features_dict = {
                    name: float(val)
                    for name, val in zip(feature_engineer.required_features, features)
                }
                features_dict['ticker'] = ticker
                features_list.append(features_dict)

        except Exception as e:
            logger.warning(f"Failed for {ticker}: {e}")

    return pd.DataFrame(features_list)


def analyze_distributions(df, title="Features"):
    """Analyze feature distributions"""
    logger.info(f"\n{'='*60}")
    logger.info(f"ANALYSIS: {title}")
    logger.info(f"{'='*60}")

    numeric_cols = df.select_dtypes(include=[np.number]).columns

    # Key features to analyze
    key_features = [
        'momentum_3d', 'momentum_5d', 'momentum_7d',
        'price_change_14d', 'volume_ratio_20',
        'fear_greed_value', 'atr_pct', 'stoch_k',
        'price_to_ema200', 'body_ratio', 'close_position',
        'price_explosion_ratio', 'volume_explosion_ratio'
    ]

    for feat in key_features:
        if feat in df.columns:
            vals = df[feat].dropna()
            logger.info(f"\n{feat}:")
            logger.info(f"  Mean:   {vals.mean():10.4f}")
            logger.info(f"  Std:    {vals.std():10.4f}")
            logger.info(f"  Min:    {vals.min():10.4f}")
            logger.info(f"  Max:    {vals.max():10.4f}")
            logger.info(f"  Median: {vals.median():10.4f}")


def main():
    logger.info("=" * 60)
    logger.info("TRAINING vs PRODUCTION DATA COMPARISON")
    logger.info("=" * 60)

    # 1. Load signals from database
    signals_df = load_signals_features()
    if signals_df is not None:
        logger.info(f"Loaded {len(signals_df)} signals from database")

        # Check probability distribution
        logger.info("\n" + "=" * 60)
        logger.info("PROBABILITY DISTRIBUTION IN DATABASE")
        logger.info("=" * 60)
        logger.info(f"Mean probability: {signals_df['probability'].mean():.4f}")
        logger.info(f"Std probability: {signals_df['probability'].std():.4f}")
        logger.info(f"Min probability: {signals_df['probability'].min():.4f}")
        logger.info(f"Max probability: {signals_df['probability'].max():.4f}")

        # Count by ranges
        logger.info("\nProbability distribution:")
        for threshold in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99]:
            count = len(signals_df[signals_df['probability'] >= threshold])
            logger.info(f"  >= {threshold:.0%}: {count} signals ({count/len(signals_df)*100:.1f}%)")

        analyze_distributions(signals_df, "Database Signals Features")

    # 2. Calculate current features
    current_df = calculate_current_features()
    if current_df is not None and len(current_df) > 0:
        logger.info(f"\nCalculated features for {len(current_df)} tickers")
        analyze_distributions(current_df, "Current Market Features")

    # 3. Key findings
    logger.info("\n" + "=" * 60)
    logger.info("KEY FINDINGS & RECOMMENDATIONS")
    logger.info("=" * 60)

    if signals_df is not None:
        mean_prob = signals_df['probability'].mean()
        high_prob_count = len(signals_df[signals_df['probability'] >= 0.95])

        if mean_prob > 0.7:
            logger.warning(f"ISSUE: Average probability is very high ({mean_prob:.2%})")
            logger.warning("This suggests the model may be overconfident or data has shifted")

        if high_prob_count / len(signals_df) > 0.3:
            logger.warning(f"ISSUE: {high_prob_count/len(signals_df)*100:.1f}% of signals are >95%")
            logger.warning("Model needs recalibration")

    logger.info("""
NEXT STEPS:
-----------
1. Compare with training data file if available
2. Check if macro data (Fear/Greed, VIX) values are different now
3. Consider recalibrating the model with current data
4. Try using threshold of 0.70 (original training threshold)
""")


if __name__ == "__main__":
    main()
