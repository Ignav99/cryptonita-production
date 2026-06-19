#!/usr/bin/env python3
"""
Retrain ensemble models with Jun 10-19 trade data using separate LONG/SHORT detectors.

This script loads closed trades from the database and retrains the model using
separate binary detectors for LONG and SHORT classes. This fixes the "0 LONGs"
bug that occurs with highly imbalanced training data.

Usage:
    python scripts/retrain_models.py [--days-back 10] [--output-dir path/to/models]
"""

import sys
import argparse
import sqlite3
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.models.ensemble_v5 import EnsembleV5
from src.db_manager import get_db_connection
from loguru import logger

import config


def load_training_data(days_back: int = 10) -> pd.DataFrame:
    """
    Load closed trades from database within last N days.

    Returns:
        DataFrame with columns:
            - trade_id, ticker, side, entry_price, close_price
            - entry_time, close_time, is_win
    """
    logger.info(f"[RETRAIN] Loading trades from last {days_back} days...")

    conn = get_db_connection()
    query = f"""
    SELECT
        trade_id, ticker, side, entry_price, close_price,
        entry_time, close_time,
        CASE WHEN (side='SHORT' AND close_price < entry_price)
             OR (side='LONG' AND close_price > entry_price)
        THEN 1 ELSE 0 END as is_win
    FROM trades
    WHERE status='CLOSED' AND close_time >= datetime('now', '-{days_back} days')
    ORDER BY close_time DESC
    """
    try:
        df = pd.read_sql_query(query, conn)
        logger.info(f"[RETRAIN] Loaded {len(df)} closed trades")
        return df
    finally:
        conn.close()


def create_ternary_labels(trades: pd.DataFrame) -> np.ndarray:
    """
    Create ternary labels from trade outcomes.

    Mapping:
        - Winning LONG  → 1
        - Winning SHORT → 2
        - Losing trades → 0 (HOLD — skip this trade)

    Args:
        trades: DataFrame with columns [side, is_win]

    Returns:
        Array of labels {0, 1, 2}
    """
    labels = []

    for _, row in trades.iterrows():
        is_win = row['is_win']
        side = row['side']

        if is_win:
            if side == 'LONG':
                labels.append(1)
            elif side == 'SHORT':
                labels.append(2)
            else:
                labels.append(0)
        else:
            labels.append(0)

    return np.array(labels)


def load_feature_cache() -> Optional[Tuple[np.ndarray, list]]:
    """
    Load pre-computed features from cache if available.

    Feature cache format: features.npy + features_metadata.json
    This avoids expensive re-computation of OHLCV-based features.

    Returns:
        Tuple of (X, feature_names) or None if cache not found
    """
    cache_dir = project_root / "artifacts" / "feature_cache"
    features_path = cache_dir / "features.npy"
    metadata_path = cache_dir / "features_metadata.json"

    if features_path.exists() and metadata_path.exists():
        logger.info(f"[RETRAIN] Loading features from cache: {features_path}")
        import json
        X = np.load(features_path)
        with open(metadata_path) as f:
            metadata = json.load(f)
        feature_names = metadata.get("feature_names", [])
        logger.info(f"[RETRAIN] Loaded {X.shape} with {len(feature_names)} features")
        return X, feature_names

    logger.warning("[RETRAIN] Feature cache not found. Features required for training.")
    return None


def main():
    parser = argparse.ArgumentParser(
        description="Retrain ensemble with separate LONG/SHORT detectors"
    )
    parser.add_argument(
        "--days-back",
        type=int,
        default=10,
        help="Number of days back to load trades (default: 10)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for trained models (default: artifacts/models/v5_separate_detectors)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Load data and show stats without training",
    )

    args = parser.parse_args()

    # Configure output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = project_root / "artifacts" / "models" / "v5_separate_detectors"

    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"[RETRAIN] Output directory: {output_dir}")

    # Step 1: Load trades
    try:
        trades = load_training_data(days_back=args.days_back)
    except Exception as e:
        logger.error(f"[RETRAIN] Failed to load trades: {e}")
        logger.info("[RETRAIN] Skipping — database may not be available in this environment")
        print("\n[FRAMEWORK READY] Separate LONG/SHORT detector training framework is ready.")
        print("To retrain in production:")
        print("  1. Ensure database connection is configured")
        print("  2. Features are pre-computed in artifacts/feature_cache/")
        print("  3. Run: python scripts/retrain_models.py --days-back 10")
        return

    if len(trades) == 0:
        logger.warning("[RETRAIN] No closed trades found in the specified period")
        return

    # Step 2: Create ternary labels
    y_train = create_ternary_labels(trades)
    label_counts = {0: (y_train == 0).sum(), 1: (y_train == 1).sum(), 2: (y_train == 2).sum()}
    logger.info(f"[RETRAIN] Label distribution: HOLD={label_counts[0]}, LONG={label_counts[1]}, SHORT={label_counts[2]}")

    # Step 3: Load or compute features
    features_result = load_feature_cache()
    if features_result is None:
        logger.error(
            "[RETRAIN] Features not available. "
            "Run feature pipeline first to compute OHLCV-based features."
        )
        print("\n[FRAMEWORK READY] Separate LONG/SHORT detector training framework is ready.")
        print("To train:")
        print("  1. Pre-compute features using feature pipeline")
        print("  2. Cache to: artifacts/feature_cache/features.npy")
        print("  3. Run: python scripts/retrain_models.py --days-back 10")
        return

    X_train, feature_names = features_result

    # Validate shape
    if len(X_train) != len(y_train):
        logger.error(f"[RETRAIN] Feature/label mismatch: {len(X_train)} vs {len(y_train)}")
        return

    if args.dry_run:
        logger.info("[RETRAIN] DRY RUN: Data loaded, no training performed")
        print(f"\nDry-run summary:")
        print(f"  Samples: {len(X_train)}")
        print(f"  Features: {len(feature_names)}")
        print(f"  Labels: LONG={label_counts[1]}, SHORT={label_counts[2]}, HOLD={label_counts[0]}")
        return

    # Step 4: Train separate LONG/SHORT ensemble
    logger.info("[RETRAIN] Initializing separate LONG/SHORT ensemble...")
    model = EnsembleV5()

    logger.info("[RETRAIN] Training separate detectors...")
    metrics = model.train_separate_detectors(
        X=X_train,
        y=y_train,
        feature_names=feature_names,
    )

    # Step 5: Save model
    logger.info(f"[RETRAIN] Saving trained model to {output_dir}...")
    model.save(str(output_dir))

    # Step 6: Log summary
    logger.info(f"[RETRAIN] Training complete!")
    logger.info(f"[RETRAIN] Metrics: {metrics}")
    print(f"\n✓ Model trained and saved to: {output_dir}")
    print(f"  LONG precision:  {metrics.get('long_precision', 0):.3f}")
    print(f"  LONG recall:     {metrics.get('long_recall', 0):.3f}")
    print(f"  SHORT precision: {metrics.get('short_precision', 0):.3f}")
    print(f"  SHORT recall:    {metrics.get('short_recall', 0):.3f}")


if __name__ == "__main__":
    main()
