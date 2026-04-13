#!/usr/bin/env python3
"""
LOCAL TRAINING SCRIPT
=====================
Run this on your local machine (not Render) to train the V4 model.
Requires DATABASE_URL env var pointing to production PostgreSQL.

Usage:
    DATABASE_URL="postgresql://..." python scripts/train_local.py [--mode full]
"""

import sys
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from loguru import logger
from src.models.auto_trainer import AutoTrainer


def main():
    parser = argparse.ArgumentParser(description="Train V4 model locally")
    parser.add_argument("--mode", choices=["quick", "full"], default="quick",
                        help="Training mode: quick (defaults) or full (SHAP + hyperopt)")
    args = parser.parse_args()

    logger.remove()
    logger.add(lambda msg: print(msg, end=""),
               format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>",
               level="INFO")

    logger.info(f"Starting local training (mode={args.mode})...")

    trainer = AutoTrainer()

    # Train
    model_dir, metrics = trainer.train_new_model(mode=args.mode)
    logger.info(f"Training complete. Model saved to: {model_dir}")
    logger.info(f"Metrics: {metrics}")

    # Backtest
    logger.info("Running backtest...")
    bt_metrics = trainer.backtest_model(model_dir)
    logger.info(f"Backtest: Sharpe={bt_metrics.get('sharpe', 0):.2f}, "
                f"WR={bt_metrics.get('win_rate', 0)*100:.1f}%, "
                f"DD={bt_metrics.get('max_drawdown', 0)*100:.1f}%")

    # Compare and promote
    current_metrics = trainer.model_store.get_active_metrics() or {}
    should_promote, reason = trainer.compare_and_promote(bt_metrics, current_metrics)

    if should_promote:
        version = trainer.model_store.get_latest_version() + 1
        trainer.model_store.save_ensemble(version, model_dir, metrics)
        trainer.model_store.promote_version(version)
        logger.success(f"Model v{version} promoted to production DB! Bot will hot-reload.")
    else:
        logger.warning(f"Model NOT promoted: {reason}")
        logger.info("To force-promote, use ModelStore manually.")


if __name__ == "__main__":
    main()
