#!/usr/bin/env python3
"""
Forensic Analysis - Understanding Past Predictions
===================================================
Análisis forense para entender qué causó las predicciones altas.

Ejecutar en Render shell:
    python scripts/forensic_analysis.py
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger
from collections import defaultdict

from config import settings
from src.data.storage.db_manager import DatabaseManager


def forensic_analysis():
    """Análisis forense de las predicciones"""

    logger.info("=" * 70)
    logger.info("🔍 FORENSIC ANALYSIS - Understanding Past Predictions")
    logger.info("=" * 70)

    db = DatabaseManager(settings.get_database_url())

    # 1. Cargar TODAS las señales con features
    logger.info("\n" + "=" * 70)
    logger.info("1. LOADING ALL SIGNALS WITH FEATURES")
    logger.info("=" * 70)

    signals_query = """
    SELECT id, ticker, signal_type, probability, features, timestamp
    FROM signals
    ORDER BY timestamp ASC
    """
    signals_df = db.execute_query(signals_query)
    signals_df['probability'] = pd.to_numeric(signals_df['probability'])
    signals_df['timestamp'] = pd.to_datetime(signals_df['timestamp'])

    logger.info(f"Total signals: {len(signals_df)}")
    logger.info(f"Date range: {signals_df['timestamp'].min()} to {signals_df['timestamp'].max()}")

    if len(signals_df) == 0:
        logger.warning("No signals found!")
        return

    # 2. Análisis temporal - ¿Cuándo se generaron las señales altas?
    logger.info("\n" + "=" * 70)
    logger.info("2. TEMPORAL ANALYSIS - When were high signals generated?")
    logger.info("=" * 70)

    # Agrupar por fecha
    signals_df['date'] = signals_df['timestamp'].dt.date
    signals_df['hour'] = signals_df['timestamp'].dt.hour

    # Señales por día
    daily_stats = signals_df.groupby('date').agg({
        'id': 'count',
        'probability': ['mean', 'max', 'min'],
        'signal_type': lambda x: (x == 'BUY').sum()
    }).round(4)
    daily_stats.columns = ['total_signals', 'mean_prob', 'max_prob', 'min_prob', 'buy_signals']

    logger.info("\nDaily signal statistics:")
    logger.info(f"{'Date':<12} | {'Total':>6} | {'Mean':>8} | {'Max':>8} | {'BUY':>5}")
    logger.info("-" * 50)
    for date, row in daily_stats.iterrows():
        logger.info(f"{str(date):<12} | {int(row['total_signals']):>6} | {row['mean_prob']:>8.4f} | {row['max_prob']:>8.4f} | {int(row['buy_signals']):>5}")

    # 3. Análisis de señales BUY (>= threshold)
    logger.info("\n" + "=" * 70)
    logger.info("3. BUY SIGNALS ANALYSIS")
    logger.info("=" * 70)

    buy_signals = signals_df[signals_df['signal_type'] == 'BUY'].copy()
    logger.info(f"\nTotal BUY signals: {len(buy_signals)}")

    if len(buy_signals) > 0:
        # ¿En qué ciclos/fechas se generaron?
        logger.info("\nBUY signals by date and hour:")
        for _, row in buy_signals.iterrows():
            logger.info(f"  {row['timestamp']} | {row['ticker']:<12} | prob: {row['probability']:.4f}")

        # Agrupar por ciclo (asumiendo ciclos de 12 horas)
        buy_signals['cycle'] = buy_signals['timestamp'].dt.floor('12H')
        cycle_counts = buy_signals.groupby('cycle').size()

        logger.info("\nBUY signals per cycle (12h):")
        for cycle, count in cycle_counts.items():
            logger.info(f"  {cycle}: {count} signals")

    # 4. Extraer y analizar features de señales altas
    logger.info("\n" + "=" * 70)
    logger.info("4. FEATURE ANALYSIS OF HIGH PROBABILITY SIGNALS")
    logger.info("=" * 70)

    high_prob_signals = signals_df[signals_df['probability'] >= 0.90].copy()
    low_prob_signals = signals_df[signals_df['probability'] < 0.50].copy()

    logger.info(f"\nHigh probability (>=90%): {len(high_prob_signals)} signals")
    logger.info(f"Low probability (<50%): {len(low_prob_signals)} signals")

    def parse_features(features_str):
        try:
            if isinstance(features_str, str):
                return json.loads(features_str)
            return features_str or {}
        except:
            return {}

    # Parsear features
    high_prob_signals['features_dict'] = high_prob_signals['features'].apply(parse_features)
    low_prob_signals['features_dict'] = low_prob_signals['features'].apply(parse_features)

    # Extraer features clave
    key_features = [
        'momentum_3d', 'momentum_5d', 'momentum_7d',
        'price_change_14d', 'price_to_ema200',
        'volume_ratio_20', 'atr_pct', 'stoch_k',
        'close_position', 'fear_greed_value',
        'price_explosion_ratio', 'volume_explosion_ratio',
        'higher_highs_5d', 'higher_lows_5d', 'green_candles_5d'
    ]

    if len(high_prob_signals) > 0:
        logger.info("\n" + "-" * 70)
        logger.info("Features of HIGH probability signals (>=90%):")
        logger.info("-" * 70)

        for feat in key_features:
            values = [f.get(feat) for f in high_prob_signals['features_dict'] if f.get(feat) is not None]
            if values:
                logger.info(f"\n{feat}:")
                logger.info(f"  Mean:   {np.mean(values):10.4f}")
                logger.info(f"  Std:    {np.std(values):10.4f}")
                logger.info(f"  Min:    {np.min(values):10.4f}")
                logger.info(f"  Max:    {np.max(values):10.4f}")

    # 5. Comparación HIGH vs LOW
    logger.info("\n" + "=" * 70)
    logger.info("5. COMPARISON: HIGH vs LOW PROBABILITY FEATURES")
    logger.info("=" * 70)

    if len(high_prob_signals) > 0 and len(low_prob_signals) > 0:
        logger.info(f"\n{'Feature':<25} | {'High (>=90%)':>12} | {'Low (<50%)':>12} | {'Diff':>12}")
        logger.info("-" * 70)

        for feat in key_features:
            high_vals = [f.get(feat) for f in high_prob_signals['features_dict'] if f.get(feat) is not None]
            low_vals = [f.get(feat) for f in low_prob_signals['features_dict'] if f.get(feat) is not None]

            if high_vals and low_vals:
                high_mean = np.mean(high_vals)
                low_mean = np.mean(low_vals)
                diff = high_mean - low_mean
                logger.info(f"{feat:<25} | {high_mean:>12.4f} | {low_mean:>12.4f} | {diff:>+12.4f}")

    # 6. Análisis de los features más discriminativos
    logger.info("\n" + "=" * 70)
    logger.info("6. MOST DISCRIMINATIVE FEATURES")
    logger.info("=" * 70)

    if len(high_prob_signals) > 0 and len(low_prob_signals) > 0:
        differences = []
        for feat in key_features:
            high_vals = [f.get(feat) for f in high_prob_signals['features_dict'] if f.get(feat) is not None]
            low_vals = [f.get(feat) for f in low_prob_signals['features_dict'] if f.get(feat) is not None]

            if high_vals and low_vals:
                high_mean = np.mean(high_vals)
                low_mean = np.mean(low_vals)
                # Normalizar por la desviación estándar combinada
                combined_std = np.std(high_vals + low_vals)
                if combined_std > 0:
                    normalized_diff = (high_mean - low_mean) / combined_std
                else:
                    normalized_diff = 0
                differences.append({
                    'feature': feat,
                    'high_mean': high_mean,
                    'low_mean': low_mean,
                    'diff': high_mean - low_mean,
                    'normalized_diff': normalized_diff
                })

        diff_df = pd.DataFrame(differences)
        diff_df = diff_df.sort_values('normalized_diff', key=abs, ascending=False)

        logger.info("\nFeatures ranked by discriminative power:")
        logger.info(f"{'Feature':<25} | {'Norm. Diff':>12} | {'Direction':>10}")
        logger.info("-" * 55)
        for _, row in diff_df.iterrows():
            direction = "HIGH ↑" if row['normalized_diff'] > 0 else "LOW ↓"
            logger.info(f"{row['feature']:<25} | {abs(row['normalized_diff']):>12.4f} | {direction:>10}")

    # 7. Hipótesis sobre qué causó las señales altas
    logger.info("\n" + "=" * 70)
    logger.info("7. HYPOTHESIS: What caused the high signals?")
    logger.info("=" * 70)

    if len(high_prob_signals) > 0:
        # Buscar patrones
        first_high = high_prob_signals['timestamp'].min()
        last_high = high_prob_signals['timestamp'].max()

        logger.info(f"\nTemporal pattern:")
        logger.info(f"  First high signal: {first_high}")
        logger.info(f"  Last high signal: {last_high}")
        logger.info(f"  Duration: {last_high - first_high}")

        # ¿Fueron todos en el mismo ciclo?
        unique_cycles = high_prob_signals['timestamp'].dt.floor('12H').nunique()
        logger.info(f"  Unique cycles with high signals: {unique_cycles}")

        # Tickers más frecuentes
        ticker_counts = high_prob_signals['ticker'].value_counts()
        logger.info(f"\nMost frequent tickers in high signals:")
        for ticker, count in ticker_counts.head(10).items():
            pct = count / len(high_prob_signals) * 100
            logger.info(f"  {ticker}: {count} ({pct:.1f}%)")

    # 8. Conclusiones
    logger.info("\n" + "=" * 70)
    logger.info("8. CONCLUSIONS")
    logger.info("=" * 70)

    total_signals = len(signals_df)
    buy_count = len(buy_signals)
    high_count = len(high_prob_signals)

    logger.info(f"""
SUMMARY:
--------
- Total signals analyzed: {total_signals}
- BUY signals (passed threshold): {buy_count}
- High probability (>=90%): {high_count}

KEY QUESTIONS TO ANSWER:
------------------------
1. Were all high signals in the same cycle(s)?
   → If yes: Something specific happened in those scans
   → If spread out: Model consistently sees opportunities

2. Which features are most different between HIGH and LOW?
   → These are the drivers of the predictions

3. Are the feature values realistic?
   → Check if momentum_3d, price_change_14d etc. make sense

NEXT STEPS:
-----------
1. Check if there was a market event during high signal periods
2. Verify feature calculations are correct
3. Consider if the model is overfitting to certain patterns
""")


if __name__ == "__main__":
    forensic_analysis()
