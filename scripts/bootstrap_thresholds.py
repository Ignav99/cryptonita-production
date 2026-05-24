#!/usr/bin/env python3
"""
BOOTSTRAP THRESHOLD CALIBRATION
=================================
Run this ONCE after the first deploy to populate coin_thresholds
using the existing signal/trade history in the DB.

Usage:
    python scripts/bootstrap_thresholds.py

This is idempotent — safe to re-run.  Subsequent calibrations happen
automatically after every model promotion via AutoTrainer.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from loguru import logger
from src.models.threshold_calibrator import ThresholdCalibrator


def main():
    logger.info("=" * 60)
    logger.info("BOOTSTRAP: Threshold calibration from historical data")
    logger.info("=" * 60)

    calibrator = ThresholdCalibrator()
    results = calibrator.calibrate_all(model_version=0)

    logger.info("\n--- Results ---")
    for ticker, r in sorted(results.items()):
        logger.info(
            f"  {ticker:<14}  floor={r['floor']:.2f}  ceiling={r['ceiling']:.2f}  "
            f"method={r['calibration_method']:<12}  "
            f"signals={r['n_signals']}  trades={r['n_trades']}"
        )

    logger.success(f"\nDone. {len(results)} tickers calibrated and saved to DB.")
    logger.info(
        "Redeploy or restart the bot process so TradingPredictorV4 "
        "picks up the new thresholds on init."
    )


if __name__ == "__main__":
    main()
