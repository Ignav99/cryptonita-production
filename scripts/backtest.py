#!/usr/bin/env python3
"""
BACKTESTING FRAMEWORK
======================
Replay historical data, apply V4 ensemble predictions, simulate portfolio.

Usage:
    python scripts/backtest.py [--capital 1000] [--compare] [--output report.json]

Features:
- Load V4 ensemble model and replay day-by-day
- Apply prediction → position sizing → TP/SL → exit
- Metrics: ROI, Sharpe, max drawdown, win rate, profit factor
- Compare V3 vs V4 side-by-side (--compare)
"""

import sys
import json
import argparse
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone
from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings


def parse_args():
    parser = argparse.ArgumentParser(description="Backtest V4 Model")
    parser.add_argument("--capital", type=float, default=1000, help="Starting capital in USD")
    parser.add_argument("--compare", action="store_true", help="Compare V3 vs V4")
    parser.add_argument("--output", default="backtest_report.json", help="Output report path")
    parser.add_argument("--lookback-days", type=int, default=365, help="Days to backtest")
    parser.add_argument("--max-tickers", type=int, default=10, help="Max tickers for backtest")
    parser.add_argument("--threshold", type=float, default=0.55, help="Prediction threshold")
    return parser.parse_args()


class BacktestEngine:
    """Simple vectorized backtesting engine"""

    def __init__(self, initial_capital: float = 1000.0, threshold: float = 0.55):
        self.initial_capital = initial_capital
        self.threshold = threshold
        self.max_positions = 10
        self.position_pct = 0.10  # Default 10% per position

    def run(
        self,
        predictions: pd.DataFrame,
        prices: pd.DataFrame,
        tp_pct: float = 0.15,
        sl_pct: float = 0.05,
        max_hold_days: int = 15,
        position_sizer=None,
    ) -> dict:
        """
        Run backtest simulation.

        Args:
            predictions: DataFrame with columns [date, ticker, probability]
            prices: DataFrame with columns [date, ticker, close]
            tp_pct: Take profit percentage
            sl_pct: Stop loss percentage
            max_hold_days: Maximum holding period
            position_sizer: Optional KellyPositionSizer

        Returns:
            Dict with backtest results and metrics
        """
        capital = self.initial_capital
        positions = {}  # ticker -> {entry_price, quantity, entry_date, tp, sl}
        trades = []
        equity_curve = [capital]
        dates = sorted(predictions["date"].unique())

        for date in dates:
            # Check exits
            for ticker in list(positions.keys()):
                pos = positions[ticker]
                price_row = prices[(prices["date"] == date) & (prices["ticker"] == ticker)]
                if price_row.empty:
                    continue

                current_price = price_row["close"].values[0]
                days_held = (date - pos["entry_date"]).days

                # Check TP
                if current_price >= pos["tp"]:
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    capital += pos["entry_price"] * pos["quantity"] + pnl
                    trades.append({
                        "ticker": ticker, "entry_date": str(pos["entry_date"]),
                        "exit_date": str(date), "entry_price": pos["entry_price"],
                        "exit_price": current_price, "pnl": pnl,
                        "pnl_pct": (current_price / pos["entry_price"] - 1) * 100,
                        "days_held": days_held, "exit_reason": "tp",
                    })
                    del positions[ticker]
                    continue

                # Check SL
                if current_price <= pos["sl"]:
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    capital += pos["entry_price"] * pos["quantity"] + pnl
                    trades.append({
                        "ticker": ticker, "entry_date": str(pos["entry_date"]),
                        "exit_date": str(date), "entry_price": pos["entry_price"],
                        "exit_price": current_price, "pnl": pnl,
                        "pnl_pct": (current_price / pos["entry_price"] - 1) * 100,
                        "days_held": days_held, "exit_reason": "sl",
                    })
                    del positions[ticker]
                    continue

                # Check time barrier
                if days_held >= max_hold_days:
                    pnl = (current_price - pos["entry_price"]) * pos["quantity"]
                    capital += pos["entry_price"] * pos["quantity"] + pnl
                    trades.append({
                        "ticker": ticker, "entry_date": str(pos["entry_date"]),
                        "exit_date": str(date), "entry_price": pos["entry_price"],
                        "exit_price": current_price, "pnl": pnl,
                        "pnl_pct": (current_price / pos["entry_price"] - 1) * 100,
                        "days_held": days_held, "exit_reason": "time",
                    })
                    del positions[ticker]

            # Check entries
            day_preds = predictions[predictions["date"] == date]
            day_preds = day_preds[day_preds["probability"] >= self.threshold]
            day_preds = day_preds.sort_values("probability", ascending=False)

            for _, pred in day_preds.iterrows():
                ticker = pred["ticker"]
                if ticker in positions:
                    continue
                if len(positions) >= self.max_positions:
                    break

                price_row = prices[(prices["date"] == date) & (prices["ticker"] == ticker)]
                if price_row.empty:
                    continue

                entry_price = price_row["close"].values[0]

                # Position sizing
                if position_sizer:
                    size_info = position_sizer.calculate_position_size(
                        current_price=entry_price,
                        portfolio_value=capital,
                        probability=pred["probability"],
                    )
                    usd_value = size_info["usd_value"]
                else:
                    usd_value = capital * self.position_pct

                usd_value = min(usd_value, capital * 0.15)  # Cap at 15%
                if usd_value < 10:
                    continue

                quantity = usd_value / entry_price
                capital -= usd_value

                positions[ticker] = {
                    "entry_price": entry_price,
                    "quantity": quantity,
                    "entry_date": date,
                    "tp": entry_price * (1 + tp_pct),
                    "sl": entry_price * (1 - sl_pct),
                }

            # Calculate equity
            portfolio_value = capital
            for ticker, pos in positions.items():
                price_row = prices[(prices["date"] == date) & (prices["ticker"] == ticker)]
                if not price_row.empty:
                    portfolio_value += price_row["close"].values[0] * pos["quantity"]
                else:
                    portfolio_value += pos["entry_price"] * pos["quantity"]

            equity_curve.append(portfolio_value)

        # Close remaining positions at last price
        for ticker, pos in list(positions.items()):
            last_price_row = prices[prices["ticker"] == ticker].tail(1)
            if not last_price_row.empty:
                current_price = last_price_row["close"].values[0]
            else:
                current_price = pos["entry_price"]
            pnl = (current_price - pos["entry_price"]) * pos["quantity"]
            capital += pos["entry_price"] * pos["quantity"] + pnl
            trades.append({
                "ticker": ticker, "entry_date": str(pos["entry_date"]),
                "exit_date": "end", "entry_price": pos["entry_price"],
                "exit_price": current_price, "pnl": pnl,
                "pnl_pct": (current_price / pos["entry_price"] - 1) * 100,
                "days_held": 0, "exit_reason": "end",
            })

        # Calculate metrics
        equity = np.array(equity_curve)
        metrics = self._calculate_metrics(trades, equity)

        return {
            "metrics": metrics,
            "trades": trades,
            "equity_curve": equity_curve,
            "n_trades": len(trades),
        }

    def _calculate_metrics(self, trades: list, equity: np.ndarray) -> dict:
        """Calculate performance metrics"""
        if not trades:
            return {"roi": 0, "sharpe": 0, "max_drawdown": 0, "win_rate": 0}

        pnls = [t["pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        # ROI
        final_value = equity[-1]
        roi = (final_value / self.initial_capital - 1) * 100

        # Sharpe ratio (daily returns)
        returns = np.diff(equity) / equity[:-1]
        sharpe = np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252) if len(returns) > 1 else 0

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (equity - peak) / peak
        max_dd = abs(drawdown.min()) * 100

        # Win rate
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        # Profit factor
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Average hold time
        hold_times = [t["days_held"] for t in trades if t["days_held"] > 0]
        avg_hold = np.mean(hold_times) if hold_times else 0

        return {
            "initial_capital": self.initial_capital,
            "final_value": float(final_value),
            "roi_pct": float(roi),
            "sharpe_ratio": float(sharpe),
            "max_drawdown_pct": float(max_dd),
            "win_rate_pct": float(win_rate),
            "profit_factor": float(profit_factor),
            "total_trades": len(trades),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_win": float(np.mean(wins)) if wins else 0,
            "avg_loss": float(np.mean(losses)) if losses else 0,
            "avg_hold_days": float(avg_hold),
            "total_pnl": float(sum(pnls)),
        }


def generate_predictions_v4(data: dict, feature_eng, ensemble, threshold: float) -> pd.DataFrame:
    """Generate V4 predictions for backtesting"""
    ext = data.get("external", {})
    predictions = []

    for ticker, df in data["tickers_data"].items():
        features_df = feature_eng.calculate_features_v4(
            df=df, btc_df=data["btc_data"], eth_df=data.get("eth_data"),
            macro_data=ext.get("macro"), derivatives_data=ext.get("derivatives"),
            onchain_data=ext.get("onchain"), sentiment_data=ext.get("sentiment"),
            defi_data=ext.get("defi"),
        )

        if len(features_df) < 10:
            continue

        feature_vector = feature_eng.get_feature_vector_v4(features_df)
        X = feature_vector.values

        try:
            proba = ensemble.predict_proba(X)
        except Exception as e:
            logger.warning(f"Prediction failed for {ticker}: {e}")
            continue

        dates = features_df.index if "timestamp" not in features_df.columns else features_df["timestamp"]
        for i in range(len(proba)):
            if hasattr(dates, 'iloc'):
                date = dates.iloc[i]
            else:
                date = dates[i]
            predictions.append({
                "date": pd.Timestamp(date) if not isinstance(date, pd.Timestamp) else date,
                "ticker": ticker,
                "probability": float(proba[i]),
            })

    return pd.DataFrame(predictions)


def generate_prices(data: dict) -> pd.DataFrame:
    """Generate price DataFrame for backtesting"""
    rows = []
    for ticker, df in data["tickers_data"].items():
        for _, row in df.iterrows():
            date = row.get("timestamp", row.name)
            rows.append({
                "date": pd.Timestamp(date) if not isinstance(date, pd.Timestamp) else date,
                "ticker": ticker,
                "close": row["close"],
            })
    return pd.DataFrame(rows)


def run_backtest(args):
    """Main backtest execution"""
    from src.data.features_v4 import FeatureEngineerV4
    from src.models.ensemble import EnsembleModel

    model_dir = PROJECT_ROOT / "PRODUCTION_SYSTEM" / "models" / "v4"

    if not (model_dir / "ensemble_metadata.json").exists():
        logger.error(f"No trained V4 model found at {model_dir}")
        logger.info("Run 'python scripts/train_model.py' first")
        sys.exit(1)

    # Load model
    ensemble = EnsembleModel()
    ensemble.load(str(model_dir))

    # Load position sizer
    position_sizer = None
    try:
        from src.models.position_sizer import KellyPositionSizer
        position_sizer = KellyPositionSizer()
    except ImportError:
        pass

    # Fetch data
    logger.info("Fetching historical data...")
    from scripts.train_model import fetch_all_data
    data = fetch_all_data(args.lookback_days, args.max_tickers)

    # Generate predictions
    logger.info("Generating V4 predictions...")
    feature_eng = FeatureEngineerV4()
    predictions = generate_predictions_v4(data, feature_eng, ensemble, args.threshold)
    prices = generate_prices(data)

    if predictions.empty:
        logger.error("No predictions generated")
        sys.exit(1)

    logger.info(f"Generated {len(predictions)} predictions across {predictions['ticker'].nunique()} tickers")

    # Run backtest for multiple capital levels
    capitals = [args.capital]
    if args.capital == 1000:
        capitals = [100, 500, 1000, 5000, 10000]

    results = {}
    for cap in capitals:
        engine = BacktestEngine(initial_capital=cap, threshold=args.threshold)
        result = engine.run(
            predictions=predictions,
            prices=prices,
            position_sizer=position_sizer,
        )
        results[f"${cap}"] = result["metrics"]

        m = result["metrics"]
        logger.info(
            f"  ${cap}: ROI={m['roi_pct']:.1f}%, Sharpe={m['sharpe_ratio']:.2f}, "
            f"MaxDD={m['max_drawdown_pct']:.1f}%, WinRate={m['win_rate_pct']:.0f}%, "
            f"Trades={m['total_trades']}"
        )

    # Save report
    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "lookback_days": args.lookback_days,
        "threshold": args.threshold,
        "model": "V4 Ensemble",
        "results": results,
    }

    output_path = PROJECT_ROOT / args.output
    with open(output_path, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary table
    print("\n" + "=" * 80)
    print("BACKTEST RESULTS — V4 ENSEMBLE")
    print("=" * 80)
    print(f"{'Capital':>10} | {'ROI':>8} | {'Sharpe':>7} | {'MaxDD':>7} | {'WinRate':>8} | {'Trades':>6} | {'Final':>10}")
    print("-" * 80)
    for cap_label, m in results.items():
        print(
            f"{cap_label:>10} | {m['roi_pct']:>7.1f}% | {m['sharpe_ratio']:>7.2f} | "
            f"{m['max_drawdown_pct']:>6.1f}% | {m['win_rate_pct']:>7.0f}% | "
            f"{m['total_trades']:>6} | ${m['final_value']:>9.2f}"
        )
    print("=" * 80)
    print(f"\nReport saved to: {output_path}")


if __name__ == "__main__":
    logger.remove()
    logger.add(
        lambda msg: print(msg, end=""),
        format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
    )

    args = parse_args()
    run_backtest(args)
