#!/usr/bin/env python3
"""
Deep Model Investigation
========================
Análisis profundo del modelo para entender por qué genera tantas señales.

Ejecutar en Render shell:
    python scripts/deep_model_investigation.py
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
import xgboost as xgb

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_data_service import BinanceDataService
from src.data.features import FeatureEngineer
from src.data.macro_data import MacroDataFetcher
from src.models.model_loader import ModelLoader


def investigate_model():
    """Investigación profunda del modelo"""

    logger.info("=" * 70)
    logger.info("DEEP MODEL INVESTIGATION")
    logger.info("=" * 70)

    # 1. Cargar el modelo y ver su configuración
    logger.info("\n" + "=" * 70)
    logger.info("1. MODEL CONFIGURATION")
    logger.info("=" * 70)

    model_loader = ModelLoader(settings.MODEL_FILE)
    model = model_loader.load_model()

    # Obtener config del modelo
    config_str = model.save_config()
    config = json.loads(config_str)

    learner_params = config.get('learner', {}).get('learner_model_param', {})
    logger.info(f"Model parameters:")
    for key, value in learner_params.items():
        logger.info(f"  {key}: {value}")

    # Feature names del modelo
    feature_names = model.feature_names
    logger.info(f"\nModel expects {len(feature_names)} features:")
    for i, name in enumerate(feature_names):
        logger.info(f"  {i+1:2d}. {name}")

    # 2. Cargar señales de la base de datos
    logger.info("\n" + "=" * 70)
    logger.info("2. DATABASE SIGNALS ANALYSIS")
    logger.info("=" * 70)

    db = DatabaseManager(settings.get_database_url())

    signals_query = """
    SELECT id, ticker, signal_type, probability, features, timestamp
    FROM signals
    ORDER BY timestamp DESC
    LIMIT 1000
    """
    signals_df = db.execute_query(signals_query)
    signals_df['probability'] = pd.to_numeric(signals_df['probability'])

    logger.info(f"Total signals in DB: {len(signals_df)}")

    if len(signals_df) > 0:
        # Estadísticas de probabilidad
        logger.info(f"\nProbability statistics:")
        logger.info(f"  Mean:   {signals_df['probability'].mean():.4f}")
        logger.info(f"  Median: {signals_df['probability'].median():.4f}")
        logger.info(f"  Std:    {signals_df['probability'].std():.4f}")
        logger.info(f"  Min:    {signals_df['probability'].min():.4f}")
        logger.info(f"  Max:    {signals_df['probability'].max():.4f}")

        # Distribución
        logger.info(f"\nProbability distribution:")
        thresholds = [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99]
        for t in thresholds:
            count = len(signals_df[signals_df['probability'] >= t])
            pct = count / len(signals_df) * 100
            logger.info(f"  >= {t:.0%}: {count:4d} ({pct:5.1f}%)")

        # BUY signals
        buy_signals = signals_df[signals_df['signal_type'] == 'BUY']
        logger.info(f"\nBUY signals: {len(buy_signals)}")

        if len(buy_signals) > 0:
            # Tiempo entre señales
            buy_signals = buy_signals.sort_values('timestamp')
            time_range = buy_signals['timestamp'].max() - buy_signals['timestamp'].min()
            days = time_range.days if hasattr(time_range, 'days') else 1
            signals_per_day = len(buy_signals) / max(days, 1)
            logger.info(f"  Days covered: {days}")
            logger.info(f"  Signals per day: {signals_per_day:.2f}")

            # Por ticker
            logger.info(f"\n  BUY signals by ticker:")
            ticker_counts = buy_signals['ticker'].value_counts()
            for ticker, count in ticker_counts.head(15).items():
                logger.info(f"    {ticker}: {count}")

    # 3. Hacer predicciones frescas y analizar
    logger.info("\n" + "=" * 70)
    logger.info("3. FRESH PREDICTIONS ANALYSIS")
    logger.info("=" * 70)

    binance_data = BinanceDataService()
    feature_engineer = FeatureEngineer()
    macro_fetcher = MacroDataFetcher()

    # Obtener macro data
    macro_data = macro_fetcher.get_all_macro_data_sync()
    logger.info(f"\nCurrent macro data:")
    for key, value in macro_data.items():
        logger.info(f"  {key}: {value}")

    # Obtener BTC data
    btc_data = binance_data.get_historical_klines('BTCUSDT', '1d', 250)

    # Hacer predicciones para todos los tickers
    logger.info(f"\nMaking predictions for {len(settings.TICKERS)} tickers...")

    predictions = []
    feature_data = []

    for ticker in settings.TICKERS:
        try:
            ticker_data = binance_data.get_historical_klines(ticker, '1d', 250)
            if len(ticker_data) < 200:
                continue

            # Calcular features
            features = feature_engineer.calculate_single_prediction_features(
                ticker_data=ticker_data,
                btc_data=btc_data,
                macro_data=macro_data
            )

            if features is None:
                continue

            # Hacer predicción
            dmatrix = xgb.DMatrix(
                features.reshape(1, -1),
                feature_names=feature_engineer.required_features
            )
            probability = float(model.predict(dmatrix)[0])

            predictions.append({
                'ticker': ticker,
                'probability': probability
            })

            # Guardar features para análisis
            feat_dict = {name: float(val) for name, val in zip(feature_engineer.required_features, features)}
            feat_dict['ticker'] = ticker
            feat_dict['probability'] = probability
            feature_data.append(feat_dict)

        except Exception as e:
            logger.debug(f"Failed for {ticker}: {e}")
            continue

    pred_df = pd.DataFrame(predictions)
    feat_df = pd.DataFrame(feature_data)

    logger.info(f"\nPredictions made for {len(pred_df)} tickers")
    logger.info(f"\nFresh prediction statistics:")
    logger.info(f"  Mean probability:   {pred_df['probability'].mean():.4f}")
    logger.info(f"  Median probability: {pred_df['probability'].median():.4f}")
    logger.info(f"  Std probability:    {pred_df['probability'].std():.4f}")
    logger.info(f"  Min probability:    {pred_df['probability'].min():.4f}")
    logger.info(f"  Max probability:    {pred_df['probability'].max():.4f}")

    # Distribución de predicciones frescas
    logger.info(f"\nFresh predictions distribution:")
    for t in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99]:
        count = len(pred_df[pred_df['probability'] >= t])
        pct = count / len(pred_df) * 100
        logger.info(f"  >= {t:.0%}: {count:4d} ({pct:5.1f}%)")

    # Top predictions
    logger.info(f"\nTop 10 predictions:")
    top_pred = pred_df.nlargest(10, 'probability')
    for _, row in top_pred.iterrows():
        logger.info(f"  {row['ticker']}: {row['probability']:.4f} ({row['probability']*100:.1f}%)")

    # 4. Analizar qué features están correlacionadas con alta probabilidad
    logger.info("\n" + "=" * 70)
    logger.info("4. FEATURE CORRELATION WITH PROBABILITY")
    logger.info("=" * 70)

    if len(feat_df) > 5:
        # Calcular correlación de cada feature con la probabilidad
        correlations = []
        numeric_cols = feat_df.select_dtypes(include=[np.number]).columns

        for col in numeric_cols:
            if col not in ['probability', 'ticker']:
                corr = feat_df[col].corr(feat_df['probability'])
                if not np.isnan(corr):
                    correlations.append({'feature': col, 'correlation': corr})

        corr_df = pd.DataFrame(correlations)
        corr_df = corr_df.sort_values('correlation', key=abs, ascending=False)

        logger.info("\nFeatures most correlated with high probability:")
        for _, row in corr_df.head(15).iterrows():
            direction = "↑" if row['correlation'] > 0 else "↓"
            logger.info(f"  {row['feature']:30s}: {row['correlation']:+.4f} {direction}")

        # 5. Comparar features de alta vs baja probabilidad
        logger.info("\n" + "=" * 70)
        logger.info("5. HIGH vs LOW PROBABILITY FEATURE COMPARISON")
        logger.info("=" * 70)

        high_prob = feat_df[feat_df['probability'] >= 0.90]
        low_prob = feat_df[feat_df['probability'] < 0.50]

        logger.info(f"\nHigh probability (>=90%): {len(high_prob)} tickers")
        logger.info(f"Low probability (<50%): {len(low_prob)} tickers")

        if len(high_prob) > 0 and len(low_prob) > 0:
            # Comparar features clave
            key_features = [
                'momentum_3d', 'momentum_5d', 'momentum_7d',
                'price_change_14d', 'price_to_ema200',
                'volume_ratio_20', 'atr_pct', 'stoch_k',
                'close_position', 'fear_greed_value'
            ]

            logger.info(f"\nFeature comparison:")
            logger.info(f"{'Feature':<25s} | {'High Prob':>12s} | {'Low Prob':>12s} | {'Diff':>12s}")
            logger.info("-" * 70)

            for feat in key_features:
                if feat in feat_df.columns:
                    high_mean = high_prob[feat].mean()
                    low_mean = low_prob[feat].mean()
                    diff = high_mean - low_mean
                    logger.info(f"{feat:<25s} | {high_mean:>12.4f} | {low_mean:>12.4f} | {diff:>+12.4f}")

    # 6. Verificar el threshold del config vs modelo
    logger.info("\n" + "=" * 70)
    logger.info("6. THRESHOLD ANALYSIS")
    logger.info("=" * 70)

    # Leer PRODUCTION_MASTER_CONFIG
    master_config_path = settings.MASTER_CONFIG_FILE
    try:
        with open(master_config_path, 'r') as f:
            master_config = json.load(f)

        logger.info(f"\nFrom PRODUCTION_MASTER_CONFIG:")
        logger.info(f"  Model threshold (training): {master_config['model'].get('threshold', 'N/A')}")
        logger.info(f"  Trading rules threshold:    {master_config['trading_rules'].get('threshold', 'N/A')}")
        logger.info(f"  Test period trades:         {master_config['performance'].get('total_trades', 'N/A')}")
        logger.info(f"  Test period:                {master_config['performance'].get('test_period', 'N/A')}")

        logger.info(f"\nCurrent config.py threshold: {settings.PREDICTION_THRESHOLD}")

    except Exception as e:
        logger.warning(f"Could not read master config: {e}")

    # 7. Conclusiones
    logger.info("\n" + "=" * 70)
    logger.info("7. CONCLUSIONS & RECOMMENDATIONS")
    logger.info("=" * 70)

    avg_prob = pred_df['probability'].mean()
    high_prob_count = len(pred_df[pred_df['probability'] >= 0.95])

    logger.info(f"""
FINDINGS:
---------
1. Average probability of fresh predictions: {avg_prob:.2%}
2. Predictions >= 95%: {high_prob_count}/{len(pred_df)} ({high_prob_count/len(pred_df)*100:.1f}%)
3. Fear & Greed Index: {macro_data.get('fear_greed', 'N/A')} (Extreme Fear = 0-25)

LIKELY CAUSE:
-------------
The model was trained on historical data where Extreme Fear + low prices
relative to EMA200 often preceded pumps. Current market conditions match
these patterns, causing high confidence predictions.

RECOMMENDATIONS:
----------------
1. OPTION A - Increase threshold to 0.98 or 0.99
   - Quick fix but may miss real opportunities

2. OPTION B - Recalibrate the model (Platt scaling)
   - More robust solution
   - Requires validation data

3. OPTION C - Retrain with more recent data
   - Best long-term solution
   - Include current market conditions

4. OPTION D - Add market regime filter
   - Don't trade when Fear & Greed < 25 (Extreme Fear)
   - Or reduce position sizes in extreme conditions
""")


if __name__ == "__main__":
    investigate_model()
