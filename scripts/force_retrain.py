"""
FORCE RETRAIN — Bypass Sharpe promotion threshold
==================================================
Triggers a full model retrain and optionally promotes the result regardless of
the Sharpe threshold guard (which was blocking auto-promotion at 0.49 < 0.5).

The auto-trainer trains weekly but won't promote if backtest Sharpe < 0.5.
Use this script after adding new features to force a baseline refresh.

Usage:
    cd cryptonita-production
    python scripts/force_retrain.py              # Train + show metrics only
    python scripts/force_retrain.py --promote    # Train + force promote to production

Options:
    --promote     Promote to production regardless of Sharpe threshold
    --mode full   Full training with hyperopt (slower, better). Default: full
    --mode quick  Quick training with defaults (faster)
"""

import sys
import asyncio
import argparse
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from config import settings
from src.models.auto_trainer import AutoTrainer
from src.models.model_store import ModelStore


def main(force_promote: bool = False, mode: str = "full"):
    logger.info("=" * 60)
    logger.info(f"FORCE RETRAIN — mode={mode}, force_promote={force_promote}")
    logger.info("=" * 60)

    trainer = AutoTrainer()
    model_store = trainer.model_store

    version = model_store.get_latest_version() + 1
    logger.info(f"Training version: v{version}")

    # Step 1: Train
    start = time.time()
    logger.info(f"Step 1/3 — Training model (mode={mode})...")
    try:
        model_dir, train_metrics = trainer.train_new_model(mode=mode)
    except Exception as e:
        logger.error(f"Training failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)

    elapsed_train = time.time() - start
    logger.info(f"Training done in {elapsed_train/60:.1f} min")

    # Step 2: Backtest
    logger.info("Step 2/3 — Backtesting new model...")
    try:
        backtest_metrics = trainer.backtest_model(model_dir)
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        backtest_metrics = {"sharpe": 0.0, "roi": 0.0, "win_rate": 0.0, "max_drawdown": 0.0}

    # Step 3: Compare
    current_metrics = model_store.get_active_metrics()
    should_promote, comparison = trainer.compare_and_promote(backtest_metrics, current_metrics)

    combined_metrics = {**train_metrics, **backtest_metrics}

    # Print results
    logger.info("")
    logger.info("=" * 60)
    logger.info("TRAINING RESULTS")
    logger.info("=" * 60)
    logger.info(f"CV AUC-ROC:       {combined_metrics.get('cv_auc_mean', 0):.4f} ± {combined_metrics.get('cv_auc_std', 0):.4f}")
    logger.info(f"Backtest Sharpe:  {backtest_metrics.get('sharpe', 0):.4f}")
    logger.info(f"Backtest ROI:     {backtest_metrics.get('roi', 0):.2%}")
    logger.info(f"Win Rate:         {backtest_metrics.get('win_rate', 0):.2%}")
    logger.info(f"Max Drawdown:     {backtest_metrics.get('max_drawdown', 0):.2%}")
    logger.info("")
    logger.info(f"Auto-promotion decision: {'PROMOTE' if should_promote else 'NO PROMOTE'}")
    logger.info(f"Reason: {comparison.get('promotion_reason') or comparison.get('rejection_reason', 'N/A')}")
    logger.info("")

    # Promote?
    if force_promote:
        logger.info(f"Force promoting v{version} to production (--promote flag)...")
        try:
            model_store.save_ensemble(version, model_dir, combined_metrics)
            model_store.promote_version(version)
            logger.success(f"Model v{version} PROMOTED to production.")
        except Exception as e:
            logger.error(f"Promotion failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
            sys.exit(1)
    elif should_promote:
        logger.info(f"Auto-promoting v{version} (Sharpe criteria met)...")
        model_store.save_ensemble(version, model_dir, combined_metrics)
        model_store.promote_version(version)
        logger.success(f"Model v{version} promoted.")
    else:
        logger.info(f"Model v{version} NOT promoted (use --promote to force).")
        logger.info(f"Model artifacts saved at: {model_dir}")

    logger.info("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Force model retrain bypassing Sharpe threshold")
    parser.add_argument("--promote", action="store_true", help="Force promote to production regardless of Sharpe")
    parser.add_argument("--mode", choices=["quick", "full"], default="full", help="Training mode")
    args = parser.parse_args()
    main(force_promote=args.promote, mode=args.mode)
