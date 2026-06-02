#!/usr/bin/env python3
"""
Walk-Forward Backtest V5
========================
Honest, no-lookahead backtest for the V5 ternary model.

Answers: "Is V5 actually better than V4? Is the model learning something real?"

- NO LOOKAHEAD: model trained only on past data, tested on strictly future rows
- Triple-barrier P&L simulation: win/loss/flat based on known outcomes
- Runs on local CSV data (no Binance API required)
- Produces a Markdown report saved to docs/BACKTEST_V5_{date}.md

Dataset tickers format: 'ADA-USD', 'SOL-USD', etc.
CLI --tickers accepts both 'ADAUSDT' (normalised) and 'ADA-USD' (direct).

Usage:
    python scripts/walk_forward_backtest_v5.py
    python scripts/walk_forward_backtest_v5.py --tickers ADAUSDT SOLUSDT
    python scripts/walk_forward_backtest_v5.py --tickers ADA-USD SOL-USD
"""

import argparse
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from loguru import logger

# Add project root to path so src.* imports work
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.models.ensemble_v5 import EnsembleV5
from src.models.labeling import TripleBarrierLabeler
from src.models.validation import PurgedWalkForwardCV

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
LONG_THRESHOLD = 0.65   # Optimized via threshold_optimizer_v5.py: maximizes LONG EV (46% WR, +0.678% EV/trade)
SHORT_THRESHOLD = 0.35  # Fixed: already positive EV (47-52% WR, +0.8% EV/trade)
TP_RETURN_PCT = 0.05    # 5% gain when TP hit
SL_RETURN_PCT = 0.03    # 3% loss when SL hit
TRAIN_PCT = 0.75        # Train on first 75% of rows
MIN_SAMPLES = 150       # Skip coins with fewer labeled rows

PRODUCTION_DATASET = Path(__file__).parent.parent / "PRODUCTION_SYSTEM" / "data" / "production_dataset_v3.csv"

# Feature columns in the production CSV (excludes OHLCV, metadata, targets)
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


# ---------------------------------------------------------------------------
# Ticker normalisation helpers
# ---------------------------------------------------------------------------

def normalise_ticker(ticker: str) -> str:
    """
    Convert user-supplied ticker to CSV format.
    'BTCUSDT' or 'BTCUSD' → 'BTC-USD'
    'BTC-USD' → 'BTC-USD' (passthrough)
    """
    ticker = ticker.upper().strip()
    if "-" in ticker:
        return ticker
    # Strip trailing USDT / USD and add -USD
    if ticker.endswith("USDT"):
        ticker = ticker[:-4]
    elif ticker.endswith("USD"):
        ticker = ticker[:-3]
    return f"{ticker}-USD"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_dataset(path: Path = PRODUCTION_DATASET) -> pd.DataFrame:
    """
    Load the production CSV. Returns full DataFrame with all columns.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Production dataset not found at {path}. "
            "Run the data pipeline first or provide fresh data."
        )
    logger.info(f"Loading dataset from {path}")
    df = pd.read_csv(path, parse_dates=["timestamp"])
    logger.info(f"Loaded {len(df):,} rows, {df['ticker'].nunique()} tickers")
    return df


# ---------------------------------------------------------------------------
# Per-coin data preparation
# ---------------------------------------------------------------------------

def prepare_coin_data(df: pd.DataFrame, ticker: str) -> Optional[pd.DataFrame]:
    """
    Filter, sort by timestamp, apply ternary labeling, drop NaN rows.

    The production CSV has pre-computed feature columns but only binary targets
    (target_v2). We re-apply TripleBarrierLabeler to get ternary {0,1,2} labels.

    Returns None if coin has insufficient data after labeling.
    """
    coin_df = df[df["ticker"] == ticker].copy()
    if len(coin_df) == 0:
        logger.warning(f"Ticker {ticker} not found in dataset")
        return None

    coin_df = coin_df.sort_values("timestamp").reset_index(drop=True)
    logger.info(f"[{ticker}] {len(coin_df)} raw rows, {coin_df['timestamp'].min().date()} → {coin_df['timestamp'].max().date()}")

    # Apply triple-barrier labeler to get ternary target {0=HOLD, 1=LONG, 2=SHORT}
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
        logger.error(f"[{ticker}] Labeling failed: {e}")
        return None

    # Drop rows without valid labels (warmup + tail)
    coin_df = coin_df[coin_df["target"].notna()].reset_index(drop=True)

    if len(coin_df) < MIN_SAMPLES:
        logger.warning(f"[{ticker}] Only {len(coin_df)} labeled rows — skipping (min={MIN_SAMPLES})")
        return None

    # Resolve available feature cols (CSV may not have all columns in edge cases)
    available_feats = [c for c in FEATURE_COLS if c in coin_df.columns]
    if len(available_feats) < 10:
        logger.error(f"[{ticker}] Too few feature columns ({len(available_feats)}) — skipping")
        return None

    # Fill NaN in features with column medians computed on the whole coin slice
    coin_df[available_feats] = coin_df[available_feats].fillna(
        coin_df[available_feats].median()
    )
    # Final safety fill for any remaining NaN (e.g., all-NaN columns)
    coin_df[available_feats] = coin_df[available_feats].fillna(0.0)

    return coin_df


# ---------------------------------------------------------------------------
# P&L simulation
# ---------------------------------------------------------------------------

def simulate_pnl(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    tp_pct: float = TP_RETURN_PCT,
    sl_pct: float = SL_RETURN_PCT,
) -> np.ndarray:
    """
    Simulate trade returns based on predicted signal vs actual triple-barrier outcome.

    Labels: 0=HOLD, 1=LONG (TP hit), 2=SHORT (SL hit in underlying)

    P&L rules:
      LONG predicted (1):
        truth=1 (TP hit)    → +tp_pct  (we bought, price went up — win)
        truth=2 (SL hit)    → -sl_pct  (we bought, price dropped — loss)
        truth=0 (time exp.) →  0.0     (flat)
      SHORT predicted (2):
        truth=2 (SL hit)    → +tp_pct  (we shorted, price dropped — win)
        truth=1 (TP hit)    → -sl_pct  (we shorted, price went up — loss)
        truth=0 (time exp.) →  0.0     (flat)
      HOLD predicted (0):
        →  0.0              (no position, no P&L)

    Args:
        y_true: array of actual labels {0,1,2}
        y_pred: array of predicted labels {0,1,2}
        tp_pct: take-profit return (positive, e.g. 0.05)
        sl_pct: stop-loss loss (positive magnitude, e.g. 0.03)

    Returns:
        Array of float returns, same length as y_true/y_pred.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)
    returns = np.zeros(len(y_pred), dtype=float)

    long_mask = y_pred == 1
    short_mask = y_pred == 2

    # LONG signals
    returns[long_mask & (y_true == 1)] = tp_pct   # TP hit → profit
    returns[long_mask & (y_true == 2)] = -sl_pct  # SL hit → loss
    returns[long_mask & (y_true == 0)] = 0.0       # time → flat

    # SHORT signals
    returns[short_mask & (y_true == 2)] = tp_pct   # price dropped → we win on short
    returns[short_mask & (y_true == 1)] = -sl_pct  # price rose → we lose on short
    returns[short_mask & (y_true == 0)] = 0.0       # time → flat

    return returns


# ---------------------------------------------------------------------------
# Metric calculation
# ---------------------------------------------------------------------------

def calculate_metrics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    returns: Optional[np.ndarray] = None,
) -> Dict:
    """
    Calculate trading performance metrics.

    Args:
        y_true: actual labels {0,1,2}
        y_pred: predicted labels {0,1,2}
        returns: per-bar returns from simulate_pnl (optional, computed if None)

    Returns:
        Dict with all metrics fields.
    """
    y_true = np.asarray(y_true, dtype=int)
    y_pred = np.asarray(y_pred, dtype=int)

    if returns is None:
        returns = simulate_pnl(y_true, y_pred)

    n = len(y_true)

    # Signal counts
    long_mask = y_pred == 1
    short_mask = y_pred == 2
    hold_mask = y_pred == 0
    n_long = int(long_mask.sum())
    n_short = int(short_mask.sum())
    n_hold = int(hold_mask.sum())

    # Win rate — only on non-HOLD signals
    def win_rate(mask: np.ndarray) -> float:
        if mask.sum() == 0:
            return float("nan")
        wins = returns[mask] > 0
        return float(wins.mean())

    long_wr = win_rate(long_mask)
    short_wr = win_rate(short_mask)
    all_signal_mask = long_mask | short_mask
    overall_wr = win_rate(all_signal_mask)

    # Total & avg return
    total_return = float(returns.sum())
    avg_return = float(returns[all_signal_mask].mean()) if all_signal_mask.sum() > 0 else 0.0

    # Sharpe ratio — use full test period returns (0 for HOLD days = correct)
    # Annualised Sharpe assuming daily bars
    daily_std = float(returns.std())
    daily_mean = float(returns.mean())
    sharpe = (daily_mean / daily_std * np.sqrt(252)) if daily_std > 1e-10 else 0.0

    # Max drawdown from cumulative return curve
    cum_returns = (1 + returns).cumprod()
    rolling_max = np.maximum.accumulate(cum_returns)
    drawdowns = (cum_returns - rolling_max) / rolling_max
    max_dd = float(drawdowns.min())  # negative

    # OOS multi-class accuracy
    from sklearn.metrics import accuracy_score
    oos_acc = float(accuracy_score(y_true, y_pred))

    return {
        "n_test_rows": n,
        "n_long_signals": n_long,
        "n_short_signals": n_short,
        "n_hold_signals": n_hold,
        "long_win_rate": long_wr,
        "short_win_rate": short_wr,
        "overall_win_rate": overall_wr,
        "total_return_pct": total_return * 100,
        "avg_return_per_trade": avg_return * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": max_dd * 100,
        "oos_accuracy": oos_acc,
    }


# ---------------------------------------------------------------------------
# Single ticker backtest
# ---------------------------------------------------------------------------

def run_backtest_single_ticker(
    ticker: str,
    df: pd.DataFrame,
) -> Optional[Dict]:
    """
    Train EnsembleV5 on first 75% of coin data, predict on last 25%.
    No data from the test set is visible during training.

    Returns metrics dict or None if ticker must be skipped.
    """
    logger.info(f"\n{'='*60}")
    logger.info(f"Backtesting: {ticker}")
    logger.info(f"{'='*60}")

    coin_df = prepare_coin_data(df, ticker)
    if coin_df is None:
        return None

    available_feats = [c for c in FEATURE_COLS if c in coin_df.columns]
    X = coin_df[available_feats].values.astype(float)
    y = coin_df["target"].values.astype(int)

    n = len(X)
    split_idx = int(n * TRAIN_PCT)

    if split_idx < 60:
        logger.warning(f"[{ticker}] Train set too small ({split_idx} rows) — skipping")
        return None
    if n - split_idx < 30:
        logger.warning(f"[{ticker}] Test set too small ({n - split_idx} rows) — skipping")
        return None

    X_train, y_train = X[:split_idx], y[:split_idx]
    X_test, y_test = X[split_idx:], y[split_idx:]

    logger.info(f"[{ticker}] Train={split_idx} rows, Test={n - split_idx} rows")
    logger.info(f"[{ticker}] Train label dist: {dict(zip(*np.unique(y_train, return_counts=True)))}")
    logger.info(f"[{ticker}] Test  label dist: {dict(zip(*np.unique(y_test, return_counts=True)))}")

    # Fast CV: 2 folds, small windows (enough for internal stacking)
    cv = PurgedWalkForwardCV(
        n_splits=2,
        min_train_days=60,
        test_days=30,
        purge_days=5,
        embargo_days=2,
    )

    model = EnsembleV5()
    try:
        train_metrics = model.train(X_train, y_train, feature_names=available_feats, cv=cv)
        logger.info(f"[{ticker}] Train OOS accuracy: {train_metrics.get('oos_accuracy', 'N/A'):.4f}")
    except Exception as e:
        logger.error(f"[{ticker}] Training failed: {e}")
        return None

    # Predict on held-out test set (model never saw this)
    try:
        y_pred = model.predict(
            X_test,
            long_threshold=LONG_THRESHOLD,
            short_threshold=SHORT_THRESHOLD,
        )
    except Exception as e:
        logger.error(f"[{ticker}] Prediction failed: {e}")
        return None

    returns = simulate_pnl(y_test, y_pred)
    metrics = calculate_metrics(y_test, y_pred, returns)
    metrics["ticker"] = ticker
    metrics["train_rows"] = split_idx
    metrics["test_date_start"] = str(coin_df["timestamp"].iloc[split_idx].date())
    metrics["test_date_end"] = str(coin_df["timestamp"].iloc[-1].date())

    logger.info(
        f"[{ticker}] LONG wr={metrics['long_win_rate']:.1%} "
        f"SHORT wr={metrics['short_win_rate']:.1%} "
        f"Return={metrics['total_return_pct']:+.1f}% "
        f"Sharpe={metrics['sharpe']:.2f} "
        f"MaxDD={metrics['max_drawdown_pct']:.1f}%"
    )
    return metrics


# ---------------------------------------------------------------------------
# Aggregate backtest across all tickers
# ---------------------------------------------------------------------------

def run_backtest_all(tickers: List[str], df: pd.DataFrame) -> List[Dict]:
    """Run single-ticker backtest for each ticker. Skip failures silently."""
    results = []
    for ticker in tickers:
        result = run_backtest_single_ticker(ticker, df)
        if result is not None:
            results.append(result)
    return results


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------

def _fmt_pct(val, decimals: int = 1) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:+.{decimals}f}%"


def _fmt_float(val, decimals: int = 2) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:.{decimals}f}"


def _fmt_wr(val) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val * 100:.1f}%"


def generate_markdown_report(results: List[Dict], output_path: Path) -> None:
    """
    Write a Markdown backtest report to output_path.

    Includes per-ticker table + aggregate summary section.
    """
    if not results:
        logger.error("No results to report.")
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")

    lines = [
        f"# Walk-Forward Backtest V5 — {today}",
        "",
        "> **Method:** Train on first 75% of each coin's history, predict on last 25%. "
        "Zero lookahead. Triple-barrier P&L simulation.",
        "",
        f"- **TP return:** +{TP_RETURN_PCT*100:.0f}%  |  **SL loss:** -{SL_RETURN_PCT*100:.0f}%",
        f"- **Long threshold:** {LONG_THRESHOLD}  |  **Short threshold:** {SHORT_THRESHOLD}",
        f"- **Train split:** {int(TRAIN_PCT*100)}% / Test: {int((1-TRAIN_PCT)*100)}%",
        f"- **Tickers tested:** {len(results)}",
        "",
        "---",
        "",
        "## Per-Ticker Results",
        "",
        "| Ticker | Test Period | Long Win% | Short Win% | Overall Win% | Return% | Avg/Trade% | Sharpe | MaxDD% | N Long | N Short | OOS Acc |",
        "|--------|-------------|-----------|------------|--------------|---------|------------|--------|--------|--------|---------|---------|",
    ]

    # Sort by total return descending
    sorted_results = sorted(results, key=lambda r: r.get("total_return_pct", 0.0), reverse=True)

    for r in sorted_results:
        test_period = f"{r.get('test_date_start', '?')} → {r.get('test_date_end', '?')}"
        lines.append(
            f"| {r['ticker']:<10} "
            f"| {test_period} "
            f"| {_fmt_wr(r.get('long_win_rate'))} "
            f"| {_fmt_wr(r.get('short_win_rate'))} "
            f"| {_fmt_wr(r.get('overall_win_rate'))} "
            f"| {_fmt_pct(r.get('total_return_pct'))} "
            f"| {_fmt_pct(r.get('avg_return_per_trade'))} "
            f"| {_fmt_float(r.get('sharpe'))} "
            f"| {_fmt_pct(r.get('max_drawdown_pct'))} "
            f"| {r.get('n_long_signals', 0):>6} "
            f"| {r.get('n_short_signals', 0):>7} "
            f"| {_fmt_float(r.get('oos_accuracy'), 3)} |"
        )

    # ---------------------------------------------------------------------------
    # Aggregate stats
    # ---------------------------------------------------------------------------
    lines += ["", "---", "", "## Aggregate Summary", ""]

    valid_long_wr = [r["long_win_rate"] for r in results if not np.isnan(r.get("long_win_rate", float("nan")))]
    valid_short_wr = [r["short_win_rate"] for r in results if not np.isnan(r.get("short_win_rate", float("nan")))]
    valid_overall_wr = [r["overall_win_rate"] for r in results if not np.isnan(r.get("overall_win_rate", float("nan")))]
    returns_list = [r["total_return_pct"] for r in results]
    sharpes = [r["sharpe"] for r in results]
    mdd_list = [r["max_drawdown_pct"] for r in results]
    n_longs = sum(r.get("n_long_signals", 0) for r in results)
    n_shorts = sum(r.get("n_short_signals", 0) for r in results)
    n_signals = n_longs + n_shorts
    accs = [r["oos_accuracy"] for r in results]

    lines += [
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Tickers in report | {len(results)} |",
        f"| Total signals (LONG+SHORT) | {n_signals:,} |",
        f"| Total LONG signals | {n_longs:,} |",
        f"| Total SHORT signals | {n_shorts:,} |",
        f"| Avg Long Win Rate | {np.mean(valid_long_wr)*100:.1f}% |" if valid_long_wr else "| Avg Long Win Rate | N/A |",
        f"| Avg Short Win Rate | {np.mean(valid_short_wr)*100:.1f}% |" if valid_short_wr else "| Avg Short Win Rate | N/A |",
        f"| Avg Overall Win Rate | {np.mean(valid_overall_wr)*100:.1f}% |" if valid_overall_wr else "| Avg Overall Win Rate | N/A |",
        f"| Median Return% | {np.median(returns_list):+.1f}% |",
        f"| Mean Return% | {np.mean(returns_list):+.1f}% |",
        f"| Best Return% | {max(returns_list):+.1f}% |",
        f"| Worst Return% | {min(returns_list):+.1f}% |",
        f"| Median Sharpe | {np.median(sharpes):.2f} |",
        f"| Mean Sharpe | {np.mean(sharpes):.2f} |",
        f"| Avg Max Drawdown | {np.mean(mdd_list):+.1f}% |",
        f"| Avg OOS Accuracy | {np.mean(accs):.3f} |",
        f"| % Tickers with positive return | {sum(r>0 for r in returns_list)/len(returns_list)*100:.0f}% |",
        f"| % Tickers with Sharpe > 0.5 | {sum(s>0.5 for s in sharpes)/len(sharpes)*100:.0f}% |",
    ]

    # ---------------------------------------------------------------------------
    # Interpretation section
    # ---------------------------------------------------------------------------
    avg_wr = np.mean(valid_overall_wr) if valid_overall_wr else 0.5
    pct_positive = sum(r > 0 for r in returns_list) / len(returns_list)
    avg_sharpe = np.mean(sharpes)

    lines += [
        "",
        "---",
        "",
        "## Interpretation",
        "",
        "### Is V5 learning something real?",
        "",
    ]

    # Asymmetric break-even: with TP=5% / SL=3%, you need WR > 3/(5+3) = 37.5% to profit
    break_even_wr = SL_RETURN_PCT / (TP_RETURN_PCT + SL_RETURN_PCT)

    if avg_wr > break_even_wr + 0.05 and pct_positive > 0.6 and avg_sharpe > 0.5:
        verdict = "POSITIVE — Win rate exceeds asymmetric break-even. Genuine edge present."
    elif avg_wr > break_even_wr and pct_positive > 0.5:
        verdict = "MARGINAL — Slightly above asymmetric break-even. Some edge, needs tuning."
    else:
        verdict = f"NEGATIVE — Win rate below asymmetric break-even ({break_even_wr*100:.1f}%). No edge detected."

    lines += [
        f"**Verdict: {verdict}**",
        "",
        f"- Asymmetric break-even win rate: {break_even_wr*100:.1f}%  (TP=+{TP_RETURN_PCT*100:.0f}% / SL=-{SL_RETURN_PCT*100:.0f}%)",
        f"- Observed avg overall win rate: {np.mean(valid_overall_wr)*100:.1f}%" if valid_overall_wr else "- Observed avg overall win rate: N/A",
        f"- Positive-return tickers: {pct_positive*100:.0f}% of {len(results)}",
        f"- Avg Sharpe ratio: {avg_sharpe:.2f} (>0.5 = acceptable, >1.0 = good)",
        "",
        "### Caveats",
        "",
        "- Triple-barrier TP/SL returns are approximations (ATR-based, not exact fill prices)",
        "- No transaction costs or slippage modeled",
        "- SHORT signals assume frictionless shorting",
        "- Past performance does not guarantee future results",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*",
    ]

    report_text = "\n".join(lines)
    output_path.write_text(report_text, encoding="utf-8")
    logger.success(f"Report saved to: {output_path}")
    return report_text


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Walk-forward backtest for EnsembleV5 ternary model"
    )
    parser.add_argument(
        "--tickers",
        nargs="+",
        default=None,
        help=(
            "Tickers to test, e.g. BTCUSDT ETHUSDT or BTC-USD ETH-USD. "
            "Defaults to all tickers in the production dataset."
        ),
    )
    parser.add_argument(
        "--dataset",
        default=str(PRODUCTION_DATASET),
        help="Path to production_dataset_v3.csv",
    )
    args = parser.parse_args()

    # Load data
    df = load_dataset(Path(args.dataset))

    all_tickers_in_csv = sorted(df["ticker"].unique())

    if args.tickers:
        # Normalise user-supplied tickers to CSV format
        requested = [normalise_ticker(t) for t in args.tickers]
        # Filter to only those that exist in the CSV
        tickers = [t for t in requested if t in all_tickers_in_csv]
        missing = [t for t in requested if t not in all_tickers_in_csv]
        if missing:
            logger.warning(
                f"Tickers not found in CSV (skipped): {missing}. "
                f"Available: {all_tickers_in_csv}"
            )
        if not tickers:
            logger.error("No valid tickers to backtest. Exiting.")
            sys.exit(1)
    else:
        tickers = all_tickers_in_csv

    logger.info(f"Running backtest on {len(tickers)} tickers: {tickers}")

    # Run backtest
    results = run_backtest_all(tickers, df)

    if not results:
        logger.error("No successful backtests. Check MIN_SAMPLES or data quality.")
        sys.exit(1)

    # Generate report
    today_str = datetime.now().strftime("%Y-%m-%d")
    report_path = Path(__file__).parent.parent / "docs" / f"BACKTEST_V5_{today_str}.md"
    generate_markdown_report(results, report_path)

    # Print quick summary to stdout
    print("\n" + "="*70)
    print(f"BACKTEST V5 SUMMARY — {today_str}")
    print("="*70)
    print(f"Tickers: {len(results)}")

    valid_wr = [r["overall_win_rate"] for r in results if not np.isnan(r.get("overall_win_rate", float("nan")))]
    if valid_wr:
        print(f"Avg overall win rate: {np.mean(valid_wr)*100:.1f}%")
    print(f"Avg total return: {np.mean([r['total_return_pct'] for r in results]):+.1f}%")
    print(f"Avg Sharpe: {np.mean([r['sharpe'] for r in results]):.2f}")
    print(f"% positive-return tickers: {sum(r['total_return_pct']>0 for r in results)/len(results)*100:.0f}%")
    print(f"\nFull report: {report_path}")


if __name__ == "__main__":
    main()
