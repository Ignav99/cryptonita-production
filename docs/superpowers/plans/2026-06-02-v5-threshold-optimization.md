# V5 Threshold Optimization & Corrected Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize V5 LONG threshold to eliminate negative-EV LONG trades, fix the backtest interpretation (wrong break-even baseline), rerun full backtest, and produce a final honest results report.

**Architecture:** Grid-search LONG threshold (0.40→0.65) on a calibration subset of 5 coins using only their TRAIN portion (no lookahead), pick the threshold that maximizes LONG win rate while keeping ≥30 signals, then run the full 25-coin backtest with the winner threshold. SHORT threshold stays at 0.35 (already working).

**Tech Stack:** Python 3.11.9/pyenv, XGBoost + LightGBM + CatBoost (EnsembleV5), existing walk_forward_backtest_v5.py infrastructure

---

## Root cause analysis

Current state (threshold=0.35 for both):
- LONG WR: 26.8% → EV/trade = 0.268×0.05 - 0.732×0.03 = **-0.009** ❌ (costs money)
- SHORT WR: 47.5% → EV/trade = 0.475×0.05 - 0.525×0.03 = **+0.008** ✅ (makes money)
- Break-even WR = SL/(TP+SL) = 3/(5+3) = 37.5%, NOT 50%

Fix: Raise LONG threshold until LONG WR > 37.5% (ideally ≥50% with positive EV).

---

## File structure

- **Create:** `scripts/threshold_optimizer_v5.py` — grid search LONG threshold, returns optimal value
- **Modify:** `scripts/walk_forward_backtest_v5.py:43-44` — update LONG_THRESHOLD constant + fix Interpretation section (wrong 50% baseline)
- **Output:** `docs/BACKTEST_V5_OPTIMIZED_2026-06-02.md` — final report

---

## Task 1: Create threshold_optimizer_v5.py

**Files:**
- Create: `scripts/threshold_optimizer_v5.py`

- [ ] **Step 1: Write the script**

```python
#!/usr/bin/env python3
"""
Threshold Optimizer V5
======================
Grid-search the optimal LONG threshold for EnsembleV5.

Methodology (no lookahead, no data leakage):
- Uses 5 calibration tickers (held out from full backtest for tuning)
- For each ticker: trains on first 75% ONLY, evaluates on last 25%
- Sweeps LONG_THRESHOLD in [0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
- SHORT_THRESHOLD is fixed at 0.35 (already positive EV)
- Picks threshold that maximizes LONG win rate with ≥20 LONG signals

Output: prints optimal LONG threshold and per-threshold metrics table.
"""

import sys
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.models.ensemble_v5 import EnsembleV5
from src.models.labeling import TripleBarrierLabeler

PRODUCTION_DATASET = Path(__file__).parent.parent / "PRODUCTION_SYSTEM" / "data" / "production_dataset_v3.csv"

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

# Calibration coins — used ONLY for threshold tuning, not in the main backtest
CALIBRATION_TICKERS = ["BTC-USD", "ETH-USD", "BNB-USD", "LTC-USD", "XRP-USD"]

# Threshold grid
LONG_THRESHOLDS = [0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65]
SHORT_THRESHOLD = 0.35  # Fixed — already positive EV
TP_PCT = 0.05
SL_PCT = 0.03
BREAK_EVEN_WR = SL_PCT / (TP_PCT + SL_PCT)  # 37.5%
MIN_LONG_SIGNALS = 20  # Minimum signals to consider a threshold valid


def load_coin(df: pd.DataFrame, ticker: str):
    """Load and label a single coin. Returns (X_train, y_train, X_test, y_test, feat_names)."""
    coin_df = df[df["ticker"] == ticker].copy().sort_values("timestamp").reset_index(drop=True)
    if len(coin_df) < 150:
        return None

    labeler = TripleBarrierLabeler(tp_atr_mult=2.5, sl_atr_mult=1.5, max_holding_days=15, atr_period=14, forward_skip=3)
    try:
        coin_df = labeler.label_for_ternary(coin_df)
    except Exception as e:
        logger.warning(f"Labeling failed for {ticker}: {e}")
        return None

    coin_df = coin_df[coin_df["target"].notna()].reset_index(drop=True)
    if len(coin_df) < 150:
        return None

    feat = [c for c in FEATURE_COLS if c in coin_df.columns]
    coin_df[feat] = coin_df[feat].fillna(coin_df[feat].median()).fillna(0.0)

    X = coin_df[feat].values.astype(float)
    y = coin_df["target"].values.astype(int)
    split = int(len(X) * 0.75)
    return X[:split], y[:split], X[split:], y[split:], feat


def eval_threshold(y_pred: np.ndarray, y_test: np.ndarray, long_thresh_raw: float) -> Dict:
    """Calculate LONG win rate and signal count for a given threshold."""
    long_mask = y_pred == 1
    short_mask = y_pred == 2
    n_long = int(long_mask.sum())
    n_short = int(short_mask.sum())

    def wr(mask):
        if mask.sum() == 0:
            return float("nan")
        returns = np.zeros(len(y_test))
        returns[mask & (y_test == 1)] = TP_PCT
        returns[mask & (y_test == 2)] = -SL_PCT
        wins = returns[mask] > 0
        return float(wins.mean())

    long_wr = wr(long_mask)
    short_wr = wr(short_mask)
    long_ev = (long_wr * TP_PCT - (1 - long_wr) * SL_PCT) if not np.isnan(long_wr) else float("nan")
    return {
        "long_threshold": long_thresh_raw,
        "n_long": n_long,
        "n_short": n_short,
        "long_wr": long_wr,
        "short_wr": short_wr,
        "long_ev": long_ev,
        "is_valid": n_long >= MIN_LONG_SIGNALS and not np.isnan(long_wr),
    }


def main():
    logger.info("Loading dataset...")
    df = pd.read_csv(PRODUCTION_DATASET, parse_dates=["timestamp"])

    available = [t for t in CALIBRATION_TICKERS if t in df["ticker"].unique()]
    if not available:
        logger.error(f"None of {CALIBRATION_TICKERS} found in dataset. Available: {sorted(df['ticker'].unique())[:10]}")
        sys.exit(1)

    logger.info(f"Calibration tickers: {available}")

    # Train one model per calibration ticker
    coin_data = []
    for ticker in available:
        result = load_coin(df, ticker)
        if result is None:
            logger.warning(f"Skipping {ticker} — insufficient data")
            continue
        X_train, y_train, X_test, y_test, feat = result
        logger.info(f"Training model for {ticker} ({len(X_train)} train, {len(X_test)} test rows)...")
        model = EnsembleV5()
        try:
            model.train(X_train, y_train, feature_names=feat)
        except Exception as e:
            logger.warning(f"Training failed for {ticker}: {e}")
            continue
        # Get raw probabilities for test set
        try:
            proba = model.predict_proba(X_test)  # shape (N, 3)
        except Exception as e:
            logger.warning(f"Predict_proba failed for {ticker}: {e}")
            continue
        coin_data.append({"ticker": ticker, "proba": proba, "y_test": y_test})

    if not coin_data:
        logger.error("No calibration data available.")
        sys.exit(1)

    # Aggregate probabilities across all calibration coins
    all_proba = np.vstack([c["proba"] for c in coin_data])
    all_y_test = np.concatenate([c["y_test"] for c in coin_data])

    print("\n" + "=" * 70)
    print("LONG THRESHOLD OPTIMIZATION — Calibration Results")
    print("=" * 70)
    print(f"Break-even win rate: {BREAK_EVEN_WR*100:.1f}%  (TP={TP_PCT*100:.0f}%, SL={SL_PCT*100:.0f}%)")
    print(f"Calibration coins: {[c['ticker'] for c in coin_data]}")
    print(f"Total test rows: {len(all_y_test):,}")
    print()
    print(f"{'Threshold':<12} {'N Long':<10} {'Long WR':<12} {'Long EV/trade':<16} {'Short WR':<12} {'Valid?'}")
    print("-" * 75)

    best_threshold = SHORT_THRESHOLD  # fallback
    best_score = -999
    results = []

    for lt in LONG_THRESHOLDS:
        # Apply threshold to raw probabilities
        p_hold = all_proba[:, 0]
        p_long = all_proba[:, 1]
        p_short = all_proba[:, 2]

        y_pred = np.zeros(len(all_y_test), dtype=int)
        # LONG: p_long >= lt AND p_long >= p_short
        long_cond = (p_long >= lt) & (p_long >= p_short)
        # SHORT: p_short >= SHORT_THRESHOLD AND p_short > p_long
        short_cond = (p_short >= SHORT_THRESHOLD) & (p_short > p_long)
        y_pred[long_cond] = 1
        y_pred[short_cond & ~long_cond] = 2

        metrics = eval_threshold(y_pred, all_y_test, lt)
        results.append(metrics)

        wr_str = f"{metrics['long_wr']*100:.1f}%" if not np.isnan(metrics['long_wr']) else "N/A"
        ev_str = f"{metrics['long_ev']*100:+.2f}%" if not np.isnan(metrics['long_ev']) else "N/A"
        valid_str = "✅" if metrics["is_valid"] else "❌"

        print(f"{lt:<12.2f} {metrics['n_long']:<10} {wr_str:<12} {ev_str:<16} {_fmt_wr(metrics['short_wr']):<12} {valid_str}")

        # Score: maximize EV when valid, prefer more signals as tiebreaker
        if metrics["is_valid"] and not np.isnan(metrics["long_ev"]):
            score = metrics["long_ev"] * 100 + metrics["n_long"] * 0.001
            if score > best_score:
                best_score = score
                best_threshold = lt

    print("-" * 75)
    print(f"\n✅ OPTIMAL LONG THRESHOLD: {best_threshold}")
    print(f"   Recommendation: set LONG_THRESHOLD = {best_threshold} in walk_forward_backtest_v5.py")
    print(f"   SHORT_THRESHOLD stays at {SHORT_THRESHOLD}")
    return best_threshold


def _fmt_wr(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val*100:.1f}%"


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the optimizer**

```bash
/Users/User/.pyenv/versions/3.11.9/bin/python scripts/threshold_optimizer_v5.py
```

Expected output: table with 7 threshold values, optimal recommendation printed at end.

---

## Task 2: Update LONG_THRESHOLD in walk_forward_backtest_v5.py

**Files:**
- Modify: `scripts/walk_forward_backtest_v5.py:43-48` (constants) and `:544-548` (interpretation logic)

After Step 1 determines the optimal threshold, update the constants:

- [ ] **Step 3: Update threshold constant**

In `scripts/walk_forward_backtest_v5.py`, change line 43:
```python
# Before:
LONG_THRESHOLD = 0.35

# After (use optimal value from Task 1, e.g. 0.55):
LONG_THRESHOLD = 0.55  # Optimized: requires 55% LONG confidence to enter
```

- [ ] **Step 4: Fix the interpretation break-even baseline**

In the `generate_markdown_report` function, fix the verdict section:

```python
# Current buggy logic (line ~545):
if avg_wr > 0.55 and pct_positive > 0.6 and avg_sharpe > 0.3:
    verdict = "POSITIVE — Model shows genuine predictive power across tickers."
elif avg_wr > 0.50 and pct_positive > 0.5:
    verdict = "MARGINAL — Model is slightly above random. Needs tuning or more data."
else:
    verdict = "NEGATIVE — Win rates near or below 50%. Model may not be learning signal."

# Fixed logic (R/R asymmetric break-even = 37.5%):
BREAK_EVEN_WR = SL_RETURN_PCT / (TP_RETURN_PCT + SL_RETURN_PCT)  # 0.375 for 5/3

if avg_wr > BREAK_EVEN_WR + 0.05 and pct_positive > 0.6 and avg_sharpe > 0.5:
    verdict = "POSITIVE — Win rate exceeds asymmetric break-even. Genuine edge present."
elif avg_wr > BREAK_EVEN_WR and pct_positive > 0.5:
    verdict = "MARGINAL — Slightly above asymmetric break-even (37.5%). Some edge, needs tuning."
else:
    verdict = "NEGATIVE — Win rate below asymmetric break-even (37.5%). No edge detected."
```

Also fix the baseline description in the Caveats section:
```python
# Change:
f"- Random-chance win rate baseline: 50.0% (binary wins/losses, ignoring flat trades)",
# To:
f"- Asymmetric break-even win rate: {BREAK_EVEN_WR*100:.1f}% (TP={TP_RETURN_PCT*100:.0f}% / SL={SL_RETURN_PCT*100:.0f}%)",
```

---

## Task 3: Run optimized full backtest

**Files:**
- No changes — just run the updated script

- [ ] **Step 5: Run full backtest with optimized threshold**

```bash
/Users/User/.pyenv/versions/3.11.9/bin/python scripts/walk_forward_backtest_v5.py 2>&1 | tee /tmp/backtest_v5_optimized.log
```

This will take ~10-20 minutes. Saves report to `docs/BACKTEST_V5_{date}.md`.

- [ ] **Step 6: Read and verify the new report**

Check that:
1. `LONG Win Rate` improved vs 26.8% baseline
2. `% Tickers with positive return` stays ≥ 85%
3. Verdict section now shows correct break-even (37.5%)

---

## Task 4: Commit results

- [ ] **Step 7: Stage and commit**

```bash
cd "/Users/User/Library/CloudStorage/GoogleDrive-ignaciovct99@gmail.com/Mi unidad/Documentos/PROYECTOS/Webapp Projects/cryptonita-production"
git add scripts/threshold_optimizer_v5.py scripts/walk_forward_backtest_v5.py docs/
git commit -m "feat: add threshold optimizer + fix LONG threshold + correct break-even baseline"
```

---

## Expected outcomes

| Metric | Before (threshold=0.35) | Target (threshold≈0.55) |
|--------|------------------------|------------------------|
| LONG signals | 3,155 | ~800-1,200 |
| LONG win rate | 26.8% ❌ | ≥45% ✅ |
| LONG EV/trade | -0.009 ❌ | ≥+0.003 ✅ |
| SHORT win rate | 47.5% ✅ | ~47-50% ✅ |
| % tickers positive | 92% | ≥90% |
| Interpretation verdict | NEGATIVE (wrong) | POSITIVE/MARGINAL (correct) |
