#!/usr/bin/env python3
"""
V4 PIPELINE TEST — End-to-End
================================
Tests the complete V4 pipeline WITHOUT needing:
- Database credentials
- Binance API keys
- Any paid services

Uses only FREE public APIs (Binance public klines, alternative.me, etc.)
"""

import sys
import json
import time
import asyncio
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ============================================================
# STEP 0: Fetch historical data from Binance PUBLIC API
# ============================================================

import httpx

async def fetch_klines(symbol: str, interval: str = "1d", limit: int = 500) -> pd.DataFrame:
    """Fetch klines from Binance public API (no auth needed)"""
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()

    df = pd.DataFrame(data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades", "taker_buy_base",
        "taker_buy_quote", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)
    return df[["timestamp", "open", "high", "low", "close", "volume"]]


async def fetch_all_data():
    """Fetch data for BTC + ETH + a few altcoins"""
    tickers = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "AVAXUSDT", "DOGEUSDT", "PEPEUSDT"]

    print("=" * 60)
    print("STEP 0: FETCHING DATA (Binance Public API)")
    print("=" * 60)

    data = {}
    for ticker in tickers:
        try:
            df = await fetch_klines(ticker, "1d", 500)
            data[ticker] = df
            print(f"  {ticker}: {len(df)} days ({df['timestamp'].iloc[0].date()} → {df['timestamp'].iloc[-1].date()})")
        except Exception as e:
            print(f"  {ticker}: FAILED — {e}")

    return data


def run_test():
    start_time = time.time()

    # ============================================================
    # STEP 0: Fetch data
    # ============================================================
    data = asyncio.run(fetch_all_data())

    if len(data) < 3:
        print("ERROR: Could not fetch enough data")
        sys.exit(1)

    btc_data = data["BTCUSDT"]
    eth_data = data.get("ETHUSDT")
    altcoins = {k: v for k, v in data.items() if k not in ("BTCUSDT", "ETHUSDT")}

    # ============================================================
    # STEP 1: Fetch external data
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 1: FETCHING EXTERNAL DATA (Free APIs)")
    print("=" * 60)

    from src.data.derivatives_fetcher import DerivativesFetcher
    from src.data.onchain_fetcher import OnChainFetcher
    from src.data.sentiment_fetcher import SentimentFetcher
    from src.data.defi_fetcher import DeFiFetcher

    async def get_external():
        deriv = DerivativesFetcher()
        onchain = OnChainFetcher()
        sentiment = SentimentFetcher()
        defi = DeFiFetcher()

        d, o, s, f = await asyncio.gather(
            deriv.get_all_derivatives_data(),
            onchain.get_all_onchain_data(),
            sentiment.get_all_sentiment_data(),
            defi.get_all_defi_data(),
            return_exceptions=True,
        )
        return {
            "derivatives": d if isinstance(d, dict) else {},
            "onchain": o if isinstance(o, dict) else {},
            "sentiment": s if isinstance(s, dict) else {},
            "defi": f if isinstance(f, dict) else {},
            "macro": {
                "fear_greed": (s if isinstance(s, dict) else {}).get("fear_greed_value", 50),
                "funding_rate": (d if isinstance(d, dict) else {}).get("funding_rate", 0),
                "spx": 5800, "spx_change_7d": 0.01, "vix": 18,
            }
        }

    ext = asyncio.run(get_external())
    for key, val in ext.items():
        if isinstance(val, dict):
            print(f"  {key}: {len(val)} fields — {list(val.keys())[:4]}...")

    # ============================================================
    # STEP 2: Feature Engineering V4
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 2: FEATURE ENGINEERING V4")
    print("=" * 60)

    from src.data.features_v4 import FeatureEngineerV4

    fe = FeatureEngineerV4()

    for ticker, df in altcoins.items():
        features_df = fe.calculate_features_v4(
            df=df, btc_df=btc_data, eth_df=eth_data,
            macro_data=ext["macro"],
            derivatives_data=ext["derivatives"],
            onchain_data=ext["onchain"],
            sentiment_data=ext["sentiment"],
            defi_data=ext["defi"],
        )

        fv = fe.get_feature_vector_v4(features_df)
        n_nan = fv.iloc[-1].isna().sum()
        n_total = len(fv.columns)
        print(f"  {ticker}: {len(features_df)} rows, {n_total} features, {n_nan} NaN in latest row")

    # ============================================================
    # STEP 3: Triple-Barrier Labeling
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 3: TRIPLE-BARRIER LABELING")
    print("=" * 60)

    from src.models.labeling import TripleBarrierLabeler

    labeler = TripleBarrierLabeler()

    all_X = []
    all_y = []

    for ticker, df in altcoins.items():
        features_df = fe.calculate_features_v4(
            df=df, btc_df=btc_data, eth_df=eth_data,
            macro_data=ext["macro"],
            derivatives_data=ext["derivatives"],
        )

        if len(features_df) < 200:
            continue

        labeled = labeler.label_for_binary(features_df)
        labeled = labeled.dropna(subset=["target"])

        fv = fe.get_feature_vector_v4(labeled)
        valid_mask = fv.index.isin(labeled.index)

        # Align
        common_idx = fv.index.intersection(labeled.index)
        fv_aligned = fv.loc[common_idx]
        target_aligned = labeled.loc[common_idx, "target"]

        # Drop rows where any critical feature is NaN (keep some NaN for tree models)
        keep_mask = fv_aligned.notna().sum(axis=1) > 40  # At least 40 non-NaN features
        fv_clean = fv_aligned[keep_mask]
        target_clean = target_aligned[keep_mask]

        if len(fv_clean) > 50:
            all_X.append(fv_clean.values)
            all_y.append(target_clean.values)
            stats = labeler.get_stats(labeled)
            print(f"  {ticker}: {len(fv_clean)} samples, TP rate={target_clean.mean():.1%}, "
                  f"TP={stats.get('tp_count',0)}, SL={stats.get('sl_count',0)}, Time={stats.get('time_count',0)}")

    if not all_X:
        print("ERROR: No training data available")
        sys.exit(1)

    X = np.vstack(all_X)
    y = np.concatenate(all_y)
    feature_names = list(fe.selected_features or fe.required_features_v4)

    print(f"\n  TOTAL: {X.shape[0]} samples, {X.shape[1]} features, TP rate={y.mean():.1%}")

    # ============================================================
    # STEP 4: Walk-Forward Cross-Validation
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 4: WALK-FORWARD CROSS-VALIDATION")
    print("=" * 60)

    from src.models.validation import PurgedWalkForwardCV
    from sklearn.metrics import roc_auc_score
    import xgboost as xgb

    cv = PurgedWalkForwardCV(n_splits=3, min_train_days=100, test_days=50, purge_days=5)

    # Fill NaN for XGBoost (it handles NaN natively but let's be safe)
    X_clean = np.nan_to_num(X, nan=0.0)

    def auc_fn(y_true, y_pred):
        try:
            return roc_auc_score(y_true, y_pred)
        except:
            return 0.5

    cv_result = cv.cross_validate(
        X_clean, y,
        model_factory=lambda: xgb.XGBClassifier(
            n_estimators=200, max_depth=5, learning_rate=0.05,
            use_label_encoder=False, eval_metric="logloss", random_state=42,
            verbosity=0,
        ),
        metric_fn=auc_fn,
    )

    print(f"\n  CV AUC: {cv_result['mean_score']:.4f} +/- {cv_result['std_score']:.4f}")
    for fold in cv_result["fold_metrics"]:
        print(f"    Fold {fold['fold']}: AUC={fold['score']:.4f} (train={fold['train_size']}, test={fold['test_size']})")

    # ============================================================
    # STEP 5: Regime Detection (HMM)
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 5: REGIME DETECTION (HMM)")
    print("=" * 60)

    from src.models.regime_detector import RegimeDetector

    regime = RegimeDetector()
    regime.train(btc_data)
    regime_data = regime.predict(btc_data)

    print(f"  Current regime: {regime_data['regime_name']}")
    print(f"  Bull prob:  {regime_data['regime_bull_prob']:.3f}")
    print(f"  Bear prob:  {regime_data['regime_bear_prob']:.3f}")

    # ============================================================
    # STEP 6: Ensemble Training
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 6: ENSEMBLE TRAINING (XGBoost + LightGBM + CatBoost)")
    print("=" * 60)

    from src.models.ensemble import EnsembleModel

    ensemble = EnsembleModel()
    ensemble.train(X_clean, y, feature_names, cv=cv)

    # Evaluate ensemble
    proba = ensemble.predict_proba(X_clean)
    ensemble_auc = auc_fn(y, proba)

    from sklearn.metrics import accuracy_score, precision_score, recall_score

    # Find optimal threshold based on precision-recall
    best_f1 = 0
    best_threshold = 0.5
    for t in np.arange(0.05, 0.95, 0.05):
        p = (proba >= t).astype(int)
        prec = precision_score(y, p, zero_division=0)
        rec = recall_score(y, p, zero_division=0)
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = t

    preds = (proba >= best_threshold).astype(int)
    TRADE_THRESHOLD = best_threshold  # Use this for backtest

    print(f"\n  Ensemble Metrics (threshold={best_threshold:.2f}):")
    print(f"    AUC-ROC:   {ensemble_auc:.4f}")
    print(f"    Accuracy:  {accuracy_score(y, preds):.4f}")
    print(f"    Precision: {precision_score(y, preds, zero_division=0):.4f}")
    print(f"    Recall:    {recall_score(y, preds, zero_division=0):.4f}")
    print(f"    F1:        {best_f1:.4f}")
    print(f"    Proba dist: min={proba.min():.4f}, median={np.median(proba):.4f}, max={proba.max():.4f}")
    print(f"    Signals:   {preds.sum()} BUY / {len(preds)} total")

    # Individual model comparison
    base_preds = ensemble.get_base_predictions(X_clean)
    print(f"\n  Individual Model AUCs:")
    for name, bp in base_preds.items():
        print(f"    {name}: AUC={auc_fn(y, bp):.4f}, range=[{bp.min():.3f}, {bp.max():.3f}]")

    # ============================================================
    # STEP 7: Kelly Position Sizing
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 7: KELLY POSITION SIZING")
    print("=" * 60)

    from src.models.position_sizer import KellyPositionSizer

    sizer = KellyPositionSizer()

    test_cases = [
        {"prob": 0.55, "price": 150.0, "portfolio": 1000, "regime": "Sideways"},
        {"prob": 0.70, "price": 150.0, "portfolio": 1000, "regime": "Bull"},
        {"prob": 0.80, "price": 150.0, "portfolio": 1000, "regime": "Bear"},
        {"prob": 0.50, "price": 150.0, "portfolio": 1000, "regime": "Sideways"},
    ]

    for tc in test_cases:
        result = sizer.calculate_position_size(
            current_price=tc["price"],
            portfolio_value=tc["portfolio"],
            probability=tc["prob"],
            regime_data={"regime_name": tc["regime"]},
        )
        print(f"  p={tc['prob']:.0%} regime={tc['regime']:>8s} → "
              f"${result['usd_value']:.2f} ({result['position_pct']:.1f}% of portfolio), "
              f"kelly_raw={result['kelly_raw']:.4f}")

    # ============================================================
    # STEP 8: Simple Backtest Simulation
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 8: BACKTEST SIMULATION")
    print("=" * 60)

    print(f"  Using threshold: {TRADE_THRESHOLD:.2f}")

    # Simulate trading on the last 90 days of data
    initial_capital = 1000
    capital = initial_capital
    wins = 0
    losses = 0
    total_pnl = 0
    trades = []
    open_positions = set()  # Prevent duplicate entries

    for ticker, df in altcoins.items():
        features_df = fe.calculate_features_v4(
            df=df, btc_df=btc_data, eth_df=eth_data,
            macro_data=ext["macro"],
            derivatives_data=ext["derivatives"],
        )

        if len(features_df) < 200:
            continue

        fv = fe.get_feature_vector_v4(features_df)

        # Use last 120 rows for testing (more trades)
        test_start = max(0, len(fv) - 120)

        i = test_start
        while i < len(fv) - 15:  # Need 15 days forward
            row = fv.iloc[i:i+1].values
            row_clean = np.nan_to_num(row, nan=0.0)

            prob = float(ensemble.predict_proba(row_clean)[0])

            if prob >= TRADE_THRESHOLD:
                entry_price = features_df["close"].iloc[i]

                # Use Kelly sizing
                size_info = sizer.calculate_position_size(
                    current_price=entry_price,
                    portfolio_value=capital,
                    probability=prob,
                    regime_data=regime_data,
                )

                usd_invested = min(size_info["usd_value"], capital * 0.15)
                if usd_invested < 5:
                    i += 1
                    continue

                qty = usd_invested / entry_price

                # ATR-based TP/SL
                lookback = features_df["close"].iloc[max(0,i-14):i]
                atr = lookback.diff().abs().mean() if len(lookback) > 1 else entry_price * 0.03
                tp_price = entry_price + 2.5 * atr
                sl_price = entry_price - 1.5 * atr

                exit_price = entry_price
                exit_reason = "time"
                days_held = 15

                for j in range(i+1, min(i+16, len(features_df))):
                    high = features_df["high"].iloc[j]
                    low = features_df["low"].iloc[j]

                    if high >= tp_price:
                        exit_price = tp_price
                        exit_reason = "tp"
                        days_held = j - i
                        break
                    if low <= sl_price:
                        exit_price = sl_price
                        exit_reason = "sl"
                        days_held = j - i
                        break
                    exit_price = features_df["close"].iloc[j]
                    days_held = j - i

                pnl = (exit_price - entry_price) * qty
                total_pnl += pnl
                capital += pnl

                if pnl > 0:
                    wins += 1
                else:
                    losses += 1

                trades.append({
                    "ticker": ticker, "prob": prob, "pnl": pnl,
                    "pnl_pct": (exit_price/entry_price - 1) * 100,
                    "reason": exit_reason, "days": days_held,
                })

                # Skip ahead by days held to avoid overlapping trades
                i += max(days_held, 1)
                continue

            i += 1

    total_trades = wins + losses
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
    roi = (capital / initial_capital - 1) * 100

    print(f"  Starting Capital: ${initial_capital}")
    print(f"  Final Capital:    ${capital:.2f}")
    print(f"  Total PnL:        ${total_pnl:.2f}")
    print(f"  ROI:              {roi:+.2f}%")
    print(f"  Total Trades:     {total_trades}")
    print(f"  Win Rate:         {win_rate:.1f}% ({wins}W / {losses}L)")

    if trades:
        pnls = [t["pnl"] for t in trades]
        win_pnls = [p for p in pnls if p > 0]
        loss_pnls = [p for p in pnls if p < 0]

        print(f"  Avg Win:          ${np.mean(win_pnls):.2f}" if win_pnls else "  Avg Win:          N/A")
        print(f"  Avg Loss:         ${np.mean(loss_pnls):.2f}" if loss_pnls else "  Avg Loss:         N/A")

        profit_factor = sum(win_pnls) / abs(sum(loss_pnls)) if loss_pnls else float("inf")
        print(f"  Profit Factor:    {profit_factor:.2f}")

        # Show by exit reason
        reasons = {}
        for t in trades:
            r = t["reason"]
            reasons[r] = reasons.get(r, 0) + 1
        print(f"  Exit Reasons:     {reasons}")

    # ============================================================
    # STEP 9: Save Model
    # ============================================================
    print("\n" + "=" * 60)
    print("STEP 9: SAVING MODEL ARTIFACTS")
    print("=" * 60)

    output_dir = PROJECT_ROOT / "PRODUCTION_SYSTEM" / "models" / "v4"
    output_dir.mkdir(parents=True, exist_ok=True)

    ensemble.save(str(output_dir))
    regime.save(str(output_dir / "regime_detector.pkl"))

    with open(output_dir / "feature_names.json", "w") as f:
        json.dump(feature_names, f, indent=2)

    metrics = {
        "cv_auc": cv_result["mean_score"],
        "ensemble_auc": ensemble_auc,
        "total_samples": int(len(y)),
        "n_features": int(X.shape[1]),
        "positive_rate": float(y.mean()),
        "backtest_roi": roi,
        "backtest_win_rate": win_rate,
        "backtest_trades": total_trades,
        "regime": regime_data["regime_name"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    with open(output_dir / "training_metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"  Saved to: {output_dir}")
    print(f"  Files: {[f.name for f in output_dir.iterdir()]}")

    # ============================================================
    # FINAL SUMMARY
    # ============================================================
    elapsed = time.time() - start_time

    print("\n" + "=" * 60)
    print("V4 PIPELINE TEST — COMPLETE")
    print("=" * 60)
    print(f"  Time:           {elapsed:.0f}s")
    print(f"  Data:           {len(data)} tickers, ~{len(btc_data)} days each")
    print(f"  Features:       {X.shape[1]} ({X.shape[0]} samples)")
    print(f"  CV AUC:         {cv_result['mean_score']:.4f}")
    print(f"  Ensemble AUC:   {ensemble_auc:.4f}")
    print(f"  Regime:         {regime_data['regime_name']}")
    print(f"  Backtest ROI:   {roi:+.2f}% (${initial_capital} → ${capital:.2f})")
    print(f"  Win Rate:       {win_rate:.1f}%")
    print(f"  Model saved:    {output_dir}")
    print("=" * 60)

    if roi > 0:
        print("\n  RESULT: The V4 model shows POSITIVE returns in backtesting")
    else:
        print("\n  RESULT: The V4 model shows NEGATIVE returns — needs more tuning")

    return metrics


if __name__ == "__main__":
    run_test()
