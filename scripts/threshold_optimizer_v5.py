#!/usr/bin/env python3
"""
Threshold Optimizer V5
======================
Grid-search the optimal LONG threshold for EnsembleV5.

Methodology (no lookahead, no data leakage):
- Uses 5 calibration tickers (different from main backtest tickers)
- For each ticker: trains on first 75% ONLY, evaluates on last 25%
- Sweeps LONG_THRESHOLD in [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
- SHORT_THRESHOLD is fixed at 0.35 (already positive EV)
- Picks threshold that maximizes LONG EV with >=20 LONG signals

Output: prints optimal LONG threshold and per-threshold metrics table.
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.models.ensemble_v5 import EnsembleV5
from src.models.labeling import TripleBarrierLabeler

PRODUCTION_DATASET = (
    Path(__file__).parent.parent / "PRODUCTION_SYSTEM" / "data" / "production_dataset_v3.csv"
)

FEATURE_COLS = [
    "price_to_ema200", "atr_pct", "price_change_14d", "obv", "obv_ratio",
    "hl_ratio", "volume_ratio_20", "stoch_k", "lower_shadow_ratio",
    "upper_shadow_ratio", "bullish_candles_3d", "body_ratio", "close_position",
    "body_trend", "fear_greed_value", "funding_rate", "google_trend",
    "fear_greed_change_7d", "funding_rate_change_7d", "google_trend_change_7d",
    "dxy", "dxy_change_7d", "dxy_change_30d",
    "vix", "vix_change_7d", "vix_change_30d",
    "spx", "spx_change_7d", "spx_change_30d",
    "gold", "gold_change_7d", "gold_change_30d",
    "momentum_3d", "momentum_5d", "momentum_7d",
    "price_acceleration", "volume_trend_ratio", "volume_acceleration",
    "atr_compression", "hl_compression",
    "green_candles_5d", "green_candles_10d",
    "higher_highs_5d", "higher_lows_5d", "price_position_20d",
    "momentum_strength", "body_trend_ratio",
    "price_jerk_3d", "volume_jerk_3d", "price_explosion_ratio",
    "volume_explosion_ratio", "momentum_vs_btc_3d",
    "beta_acceleration", "volatility_spike_ratio", "hl_expansion_rate",
]

# Calibration tickers — used ONLY for tuning, separate from main backtest
CALIBRATION_TICKERS = ["BTC-USD", "ETH-USD", "BNB-USD", "LTC-USD", "XRP-USD"]

# Threshold grid
LONG_THRESHOLDS = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
SHORT_THRESHOLD_FIXED = 0.35
TP_PCT = 0.05
SL_PCT = 0.03
BREAK_EVEN_WR = SL_PCT / (TP_PCT + SL_PCT)  # 37.5%
MIN_LONG_SIGNALS = 20


def load_coin(df: pd.DataFrame, ticker: str) -> Optional[Tuple]:
    """Load and label a single coin. Returns (X_train, y_train, X_test, y_test, feat_names) or None."""
    coin_df = df[df["ticker"] == ticker].copy()
    if len(coin_df) < 150:
        logger.warning(f"[{ticker}] insufficient rows: {len(coin_df)}")
        return None

    coin_df = coin_df.sort_values("timestamp").reset_index(drop=True)

    labeler = TripleBarrierLabeler(
        tp_atr_mult=2.5,
        sl_atr_mult=1.5,
        max_holding_days=15,
        atr_period=14,
        forward_skip=3,
    )
    try:
        coin_df = labeler.label_for_ternary(coin_df)
    except Exception as e:
        logger.warning(f"[{ticker}] Labeling failed: {e}")
        return None

    coin_df = coin_df[coin_df["target"].notna()].reset_index(drop=True)
    if len(coin_df) < 150:
        logger.warning(f"[{ticker}] Only {len(coin_df)} labeled rows after filtering")
        return None

    feat = [c for c in FEATURE_COLS if c in coin_df.columns]
    if len(feat) < 10:
        logger.warning(f"[{ticker}] Too few feature columns: {len(feat)}")
        return None

    coin_df[feat] = coin_df[feat].fillna(coin_df[feat].median()).fillna(0.0)
    X = coin_df[feat].values.astype(float)
    y = coin_df["target"].values.astype(int)

    split = int(len(X) * 0.75)
    if split < 60 or (len(X) - split) < 30:
        return None

    return X[:split], y[:split], X[split:], y[split:], feat


def simulate_pnl_for_mask(mask: np.ndarray, y_true: np.ndarray, is_short: bool = False) -> np.ndarray:
    """Simulate trade returns for a boolean signal mask."""
    returns = np.zeros(len(y_true))
    if not is_short:
        # LONG: truth=1 → win, truth=2 → loss, truth=0 → flat
        returns[mask & (y_true == 1)] = TP_PCT
        returns[mask & (y_true == 2)] = -SL_PCT
    else:
        # SHORT: truth=2 → win, truth=1 → loss, truth=0 → flat
        returns[mask & (y_true == 2)] = TP_PCT
        returns[mask & (y_true == 1)] = -SL_PCT
    return returns


def eval_threshold(
    all_proba: np.ndarray,
    all_y_test: np.ndarray,
    long_threshold: float,
) -> Dict:
    """Evaluate a single LONG threshold against aggregated test probabilities."""
    p_long = all_proba[:, 1]
    p_short = all_proba[:, 2]

    long_mask = (p_long >= long_threshold) & (p_long >= p_short)
    short_mask = (p_short >= SHORT_THRESHOLD_FIXED) & (p_short > p_long)

    n_long = int(long_mask.sum())
    n_short = int(short_mask.sum())

    long_returns = simulate_pnl_for_mask(long_mask, all_y_test, is_short=False)
    short_returns = simulate_pnl_for_mask(short_mask, all_y_test, is_short=True)

    def wr(mask):
        if mask.sum() == 0:
            return float("nan")
        wins = (long_returns[mask] > 0) if not mask.any() else None
        # Recalculate which trades won
        relevant_returns = long_returns[mask] if not (mask == short_mask).all() else short_returns[mask]
        # Actually use the signal mask directly
        return float("nan")

    # Simpler: compute win rates directly
    long_wins = int((long_returns[long_mask] > 0).sum()) if n_long > 0 else 0
    short_wins = int((short_returns[short_mask] > 0).sum()) if n_short > 0 else 0

    long_wr = long_wins / n_long if n_long > 0 else float("nan")
    short_wr = short_wins / n_short if n_short > 0 else float("nan")

    long_ev = (long_wr * TP_PCT - (1 - long_wr) * SL_PCT) if not np.isnan(long_wr) else float("nan")
    is_valid = n_long >= MIN_LONG_SIGNALS and not np.isnan(long_wr)

    return {
        "long_threshold": long_threshold,
        "n_long": n_long,
        "n_short": n_short,
        "long_wr": long_wr,
        "short_wr": short_wr,
        "long_ev": long_ev,
        "is_valid": is_valid,
    }


def main() -> float:
    logger.info("Loading production dataset...")
    if not PRODUCTION_DATASET.exists():
        logger.error(f"Dataset not found at {PRODUCTION_DATASET}")
        sys.exit(1)

    df = pd.read_csv(PRODUCTION_DATASET, parse_dates=["timestamp"])
    available_in_csv = set(df["ticker"].unique())
    logger.info(f"Dataset: {len(df):,} rows, {len(available_in_csv)} tickers")

    # Try calibration tickers, fall back to any available tickers
    cal_tickers = [t for t in CALIBRATION_TICKERS if t in available_in_csv]
    if not cal_tickers:
        # Use first 5 available tickers as fallback
        cal_tickers = sorted(available_in_csv)[:5]
        logger.warning(f"Calibration tickers not found — using fallback: {cal_tickers}")
    else:
        logger.info(f"Calibration tickers: {cal_tickers}")

    # Train one EnsembleV5 per calibration coin, collect test probabilities
    all_proba_list = []
    all_y_list = []

    for ticker in cal_tickers:
        logger.info(f"\nProcessing calibration ticker: {ticker}")
        result = load_coin(df, ticker)
        if result is None:
            logger.warning(f"Skipping {ticker}")
            continue

        X_train, y_train, X_test, y_test, feat = result
        logger.info(f"  Train: {len(X_train)} rows | Test: {len(X_test)} rows")
        logger.info(f"  Train label dist: {dict(zip(*np.unique(y_train, return_counts=True)))}")

        model = EnsembleV5()
        try:
            model.train(X_train, y_train, feature_names=feat)
            logger.info(f"  Training OK")
        except Exception as e:
            logger.warning(f"  Training failed: {e}")
            continue

        try:
            proba = model.predict_proba(X_test)  # (N, 3)
            all_proba_list.append(proba)
            all_y_list.append(y_test)
            logger.info(f"  Proba shape: {proba.shape}")
        except Exception as e:
            logger.warning(f"  predict_proba failed: {e}")
            continue

    if not all_proba_list:
        logger.error("No calibration data available. Cannot optimize thresholds.")
        sys.exit(1)

    all_proba = np.vstack(all_proba_list)
    all_y_test = np.concatenate(all_y_list)

    logger.info(f"\nAggregated test set: {len(all_y_test):,} rows")
    logger.info(f"Test label dist: {dict(zip(*np.unique(all_y_test, return_counts=True)))}")

    print("\n" + "=" * 80)
    print("LONG THRESHOLD OPTIMIZATION — Results")
    print("=" * 80)
    print(f"  Asymmetric break-even: {BREAK_EVEN_WR*100:.1f}%  (TP=+{TP_PCT*100:.0f}% / SL=-{SL_PCT*100:.0f}%)")
    print(f"  SHORT threshold: {SHORT_THRESHOLD_FIXED} (fixed, already positive EV)")
    print(f"  Calibration coins: {[a for a in all_proba_list]}")  # indirect
    print()
    print(f"{'Threshold':<12} {'N Long':<10} {'N Short':<10} {'Long WR%':<12} {'Long EV%':<14} {'Short WR%':<12} {'Valid?'}")
    print("-" * 80)

    best_threshold = 0.50  # sensible default
    best_ev = -999.0
    results = []

    for lt in LONG_THRESHOLDS:
        m = eval_threshold(all_proba, all_y_test, lt)
        results.append(m)

        wr_str = f"{m['long_wr']*100:.1f}%" if not np.isnan(m['long_wr']) else "N/A"
        ev_str = f"{m['long_ev']*100:+.3f}%" if not np.isnan(m['long_ev']) else "N/A"
        swr_str = f"{m['short_wr']*100:.1f}%" if not np.isnan(m['short_wr']) else "N/A"
        valid = "✅" if m["is_valid"] else "❌"

        print(f"{lt:<12.2f} {m['n_long']:<10} {m['n_short']:<10} {wr_str:<12} {ev_str:<14} {swr_str:<12} {valid}")

        if m["is_valid"] and not np.isnan(m["long_ev"]) and m["long_ev"] > best_ev:
            best_ev = m["long_ev"]
            best_threshold = lt

    print("-" * 80)
    print(f"\n  OPTIMAL LONG THRESHOLD: {best_threshold}")
    print(f"  Best Long EV: {best_ev*100:+.3f}% per trade")
    print()
    print(f"  → Update LONG_THRESHOLD = {best_threshold} in scripts/walk_forward_backtest_v5.py")
    print(f"  → Keep SHORT_THRESHOLD = {SHORT_THRESHOLD_FIXED}")
    print("=" * 80)

    return best_threshold


if __name__ == "__main__":
    optimal = main()
    print(f"\nFinal answer: LONG_THRESHOLD = {optimal}")
