#!/usr/bin/env python3
"""
Analyze Model Predictions
=========================
Script to investigate model prediction patterns and identify potential issues.

Usage:
    python scripts/analyze_predictions.py

This script analyzes:
1. Distribution of prediction probabilities
2. High-confidence predictions patterns
3. Time-based analysis
4. Recommendations for threshold adjustments
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from src.data.storage.db_manager import DatabaseManager


def analyze_predictions():
    """Main analysis function"""
    logger.info("=" * 60)
    logger.info("MODEL PREDICTIONS ANALYSIS")
    logger.info("=" * 60)

    # Connect to database
    db = DatabaseManager(settings.get_database_url())

    # 1. Load all signals
    logger.info("\n1. Loading signals from database...")
    signals_query = """
    SELECT id, ticker, signal_type, probability, features, timestamp
    FROM signals
    ORDER BY timestamp DESC
    """
    signals_df = db.execute_query(signals_query)

    if len(signals_df) == 0:
        logger.warning("No signals found in database")
        return

    signals_df['probability'] = pd.to_numeric(signals_df['probability'])
    date_range = signals_df['timestamp'].max() - signals_df['timestamp'].min()
    days = max(date_range.days, 1)

    logger.info(f"Total signals: {len(signals_df)}")
    logger.info(f"Date range: {signals_df['timestamp'].min()} to {signals_df['timestamp'].max()}")
    logger.info(f"Days: {days}")

    # 2. Probability distribution
    logger.info("\n" + "=" * 60)
    logger.info("2. PROBABILITY DISTRIBUTION")
    logger.info("=" * 60)

    logger.info(f"Mean probability: {signals_df['probability'].mean():.4f}")
    logger.info(f"Median probability: {signals_df['probability'].median():.4f}")
    logger.info(f"Std deviation: {signals_df['probability'].std():.4f}")
    logger.info(f"Min probability: {signals_df['probability'].min():.4f}")
    logger.info(f"Max probability: {signals_df['probability'].max():.4f}")

    # Distribution by ranges
    logger.info("\nDistribution by range:")
    ranges = [
        (0.0, 0.5),
        (0.5, 0.7),
        (0.7, 0.8),
        (0.8, 0.9),
        (0.9, 0.95),
        (0.95, 0.97),
        (0.97, 0.99),
        (0.99, 1.01)
    ]

    for low, high in ranges:
        count = len(signals_df[(signals_df['probability'] >= low) & (signals_df['probability'] < high)])
        pct = count / len(signals_df) * 100
        logger.info(f"  [{low:.0%} - {high:.0%}): {count} signals ({pct:.1f}%)")

    # Count exactly 1.0
    count_100 = len(signals_df[signals_df['probability'] >= 0.9999])
    if count_100 > 0:
        logger.warning(f"\n!!! {count_100} predictions at ~100% - This is suspicious !!!")

    # 3. BUY signals analysis
    logger.info("\n" + "=" * 60)
    logger.info("3. BUY SIGNALS ANALYSIS")
    logger.info("=" * 60)

    buy_signals = signals_df[signals_df['signal_type'] == 'BUY']
    logger.info(f"Total BUY signals: {len(buy_signals)}")
    logger.info(f"BUY signals per day: {len(buy_signals) / days:.1f}")

    if len(buy_signals) > 0:
        logger.info(f"\nBUY signal statistics:")
        logger.info(f"  Mean probability: {buy_signals['probability'].mean():.4f}")
        logger.info(f"  Min probability: {buy_signals['probability'].min():.4f}")
        logger.info(f"  Max probability: {buy_signals['probability'].max():.4f}")

        # By ticker
        logger.info("\nBUY signals by ticker:")
        ticker_counts = buy_signals.groupby('ticker').size().sort_values(ascending=False)
        for ticker, count in ticker_counts.head(10).items():
            logger.info(f"  {ticker}: {count}")

    # 4. Threshold analysis
    logger.info("\n" + "=" * 60)
    logger.info("4. THRESHOLD ANALYSIS")
    logger.info("=" * 60)

    logger.info(f"Current threshold: {settings.PREDICTION_THRESHOLD:.0%}")
    logger.info("\nSignals at different thresholds:")

    for threshold in [0.95, 0.96, 0.97, 0.98, 0.99]:
        count = len(signals_df[signals_df['probability'] >= threshold])
        rate = count / days
        marker = " <-- CURRENT" if threshold == settings.PREDICTION_THRESHOLD else ""
        logger.info(f"  {threshold:.0%}: {count} signals ({rate:.1f}/day){marker}")

    # 5. Recommendations
    logger.info("\n" + "=" * 60)
    logger.info("5. RECOMMENDATIONS")
    logger.info("=" * 60)

    signals_per_day = len(buy_signals) / days
    ideal_rate = 1.5  # 1-2 signals per day is ideal

    if signals_per_day > 3:
        logger.warning(f"Too many signals per day: {signals_per_day:.1f}")
        logger.warning("Consider increasing threshold to 0.98 or higher")
    elif signals_per_day > 2:
        logger.info(f"Signal rate is slightly high: {signals_per_day:.1f}/day")
        logger.info("Current threshold of 0.97 should help reduce this")
    else:
        logger.success(f"Signal rate is acceptable: {signals_per_day:.1f}/day")

    if count_100 > 0:
        logger.warning("\nWARNING: Predictions at 100% detected!")
        logger.warning("This indicates potential model issues:")
        logger.warning("  - Feature scaling problems")
        logger.warning("  - Data leakage")
        logger.warning("  - Overfitting")
        logger.warning("Consider investigating the model further")

    logger.info("\n" + "=" * 60)
    logger.info("ANALYSIS COMPLETE")
    logger.info("=" * 60)


if __name__ == "__main__":
    analyze_predictions()
