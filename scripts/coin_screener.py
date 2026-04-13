#!/usr/bin/env python3
"""
COIN SCREENER
==============
Automated screening for new trading candidates on Binance.
Filters by volume, spread, listing age, volatility, and BTC correlation.

Usage:
    python scripts/coin_screener.py [--min-volume 10000000] [--top 30]
"""

import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import numpy as np
import pandas as pd
from loguru import logger

from config import settings


def main():
    parser = argparse.ArgumentParser(description="Screen coins for trading candidates")
    parser.add_argument("--min-volume", type=float, default=10_000_000,
                        help="Minimum 24h USDT volume (default: $10M)")
    parser.add_argument("--max-spread", type=float, default=0.001,
                        help="Maximum bid-ask spread ratio (default: 0.1%)")
    parser.add_argument("--min-age-days", type=int, default=180,
                        help="Minimum listing age in days (default: 180)")
    parser.add_argument("--max-btc-corr", type=float, default=0.85,
                        help="Maximum BTC correlation (default: 0.85)")
    parser.add_argument("--min-volatility", type=float, default=0.03,
                        help="Minimum 20d avg daily volatility (default: 3%)")
    parser.add_argument("--top", type=int, default=30,
                        help="Number of top candidates to output (default: 30)")
    args = parser.parse_args()

    logger.remove()
    logger.add(lambda msg: print(msg, end=""),
               format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <level>{message}</level>",
               level="INFO")

    from binance.client import Client

    # Use production data API (read-only, no auth needed for public endpoints)
    client = Client("", "")

    # ---- Stage 1: Get all USDT pairs ----
    logger.info("Stage 1: Fetching exchange info...")
    exchange_info = client.get_exchange_info()
    usdt_pairs = [
        s for s in exchange_info["symbols"]
        if s["quoteAsset"] == "USDT"
        and s["status"] == "TRADING"
        and s["isSpotTradingAllowed"]
    ]
    logger.info(f"Found {len(usdt_pairs)} active USDT spot pairs")

    # ---- Stage 2: Volume filter ----
    logger.info("Stage 2: Fetching 24h tickers for volume filter...")
    tickers_24h = client.get_all_tickers()
    ticker_prices = {t["symbol"]: float(t["price"]) for t in tickers_24h}

    all_24h = client.get_ticker()
    volume_map = {}
    for t in all_24h:
        sym = t["symbol"]
        if sym.endswith("USDT"):
            volume_map[sym] = {
                "volume_usdt": float(t.get("quoteVolume", 0)),
                "price_change_pct": float(t.get("priceChangePercent", 0)),
                "trade_count": int(t.get("count", 0)),
            }

    # Filter by minimum volume
    candidates = []
    existing = set(settings.TICKERS)
    skip_assets = {"BTCUSDT", "ETHUSDT", "BNBUSDT", "USDCUSDT", "TUSDUSDT", "BUSDUSDT", "FDUSDUSDT"}

    for pair_info in usdt_pairs:
        sym = pair_info["symbol"]
        if sym in existing or sym in skip_assets:
            continue
        vol_data = volume_map.get(sym, {})
        vol = vol_data.get("volume_usdt", 0)
        if vol >= args.min_volume:
            candidates.append({
                "symbol": sym,
                "volume_usdt": vol,
                "trade_count": vol_data.get("trade_count", 0),
                "price_change_pct": vol_data.get("price_change_pct", 0),
                "price": ticker_prices.get(sym, 0),
            })

    logger.info(f"Stage 2: {len(candidates)} candidates with volume >= ${args.min_volume/1e6:.0f}M")

    # ---- Stage 3: Spread filter ----
    logger.info("Stage 3: Checking spreads...")
    spread_passed = []
    for c in candidates:
        try:
            book = client.get_order_book(symbol=c["symbol"], limit=5)
            best_bid = float(book["bids"][0][0]) if book["bids"] else 0
            best_ask = float(book["asks"][0][0]) if book["asks"] else 0
            if best_bid > 0 and best_ask > 0:
                mid = (best_bid + best_ask) / 2
                spread = (best_ask - best_bid) / mid
                c["spread"] = spread
                if spread <= args.max_spread:
                    spread_passed.append(c)
            time.sleep(0.05)  # Rate limit
        except Exception as e:
            logger.debug(f"Spread check failed for {c['symbol']}: {e}")

    logger.info(f"Stage 3: {len(spread_passed)} candidates with spread <= {args.max_spread*100:.2f}%")

    # ---- Stage 4: Listing age + data availability ----
    logger.info("Stage 4: Checking listing age and data availability...")
    age_passed = []
    min_date = datetime.now() - timedelta(days=args.min_age_days)

    for c in spread_passed:
        try:
            klines = client.get_historical_klines(
                c["symbol"], "1d",
                start_str=(datetime.now() - timedelta(days=300)).strftime("%Y-%m-%d"),
                limit=300
            )
            c["data_rows"] = len(klines)
            if len(klines) >= 200:
                first_date = datetime.fromtimestamp(klines[0][0] / 1000)
                c["first_date"] = first_date.isoformat()
                if first_date <= min_date:
                    # Calculate volatility
                    closes = np.array([float(k[4]) for k in klines])
                    returns = np.diff(closes) / closes[:-1]
                    c["avg_volatility"] = float(np.std(returns[-20:]) if len(returns) >= 20 else np.std(returns))
                    c["max_drawdown_90d"] = float(
                        np.min(closes[-90:] / np.maximum.accumulate(closes[-90:])) - 1
                    ) if len(closes) >= 90 else -1.0

                    if c["avg_volatility"] >= args.min_volatility:
                        age_passed.append(c)

            time.sleep(0.1)  # Rate limit
        except Exception as e:
            logger.debug(f"Age check failed for {c['symbol']}: {e}")

    logger.info(f"Stage 4: {len(age_passed)} candidates with age >= {args.min_age_days}d and vol >= {args.min_volatility*100:.0f}%")

    # ---- Stage 5: BTC correlation filter ----
    logger.info("Stage 5: Computing BTC correlations...")
    btc_klines = client.get_historical_klines("BTCUSDT", "1d",
                                               start_str=(datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d"))
    btc_closes = np.array([float(k[4]) for k in btc_klines])
    btc_returns = np.diff(btc_closes) / btc_closes[:-1]

    final_candidates = []
    for c in age_passed:
        try:
            klines = client.get_historical_klines(
                c["symbol"], "1d",
                start_str=(datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
            )
            closes = np.array([float(k[4]) for k in klines])
            returns = np.diff(closes) / closes[:-1]

            # Align lengths
            min_len = min(len(returns), len(btc_returns))
            if min_len >= 20:
                corr = float(np.corrcoef(returns[-min_len:], btc_returns[-min_len:])[0, 1])
                c["btc_correlation"] = corr
                if corr <= args.max_btc_corr:
                    final_candidates.append(c)

            time.sleep(0.05)
        except Exception as e:
            logger.debug(f"Correlation check failed for {c['symbol']}: {e}")

    logger.info(f"Stage 5: {len(final_candidates)} candidates with BTC corr <= {args.max_btc_corr}")

    # ---- Scoring and ranking ----
    if not final_candidates:
        logger.warning("No candidates passed all filters")
        return

    # Normalize scores
    max_vol = max(c["volume_usdt"] for c in final_candidates)
    max_volatility = max(c["avg_volatility"] for c in final_candidates)

    for c in final_candidates:
        vol_score = c["volume_usdt"] / max_vol
        volatility_score = c["avg_volatility"] / max_volatility
        corr_score = 1 - c["btc_correlation"]  # Lower correlation = higher score
        spread_score = 1 - c["spread"] / args.max_spread  # Lower spread = higher score

        c["score"] = vol_score * 0.3 + volatility_score * 0.3 + corr_score * 0.2 + spread_score * 0.2

    # Sort by score
    final_candidates.sort(key=lambda x: x["score"], reverse=True)
    top = final_candidates[:args.top]

    # Output
    logger.info(f"\n{'='*80}")
    logger.info(f"TOP {len(top)} CANDIDATES")
    logger.info(f"{'='*80}")
    for i, c in enumerate(top, 1):
        logger.info(
            f"{i:3d}. {c['symbol']:<12s} | "
            f"Vol: ${c['volume_usdt']/1e6:>7.1f}M | "
            f"Spread: {c['spread']*100:.3f}% | "
            f"Volatility: {c['avg_volatility']*100:.1f}% | "
            f"BTC Corr: {c['btc_correlation']:.2f} | "
            f"Score: {c['score']:.3f}"
        )

    # Save to JSON
    output_path = project_root / "data" / "coin_screening_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "timestamp": datetime.utcnow().isoformat(),
        "filters": {
            "min_volume": args.min_volume,
            "max_spread": args.max_spread,
            "min_age_days": args.min_age_days,
            "max_btc_corr": args.max_btc_corr,
            "min_volatility": args.min_volatility,
        },
        "existing_tickers": list(existing),
        "candidates": [{
            k: v for k, v in c.items()
            if k != "first_date" or isinstance(v, (str, int, float))
        } for c in top],
    }

    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    logger.success(f"Results saved to {output_path}")


if __name__ == "__main__":
    main()
