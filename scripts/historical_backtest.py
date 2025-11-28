#!/usr/bin/env python3
"""
Historical Backtest - Generate Signals Day by Day
==================================================
Genera señales históricas día por día, asegurando que el modelo
NUNCA ve datos futuros (no data leakage).

Para cada día D:
- Usa SOLO datos desde D-250 hasta D
- Calcula features con esos datos
- Genera predicciones
- Guarda en la base de datos

Ejecutar en Render shell:
    python scripts/historical_backtest.py --days 30
"""

import sys
import argparse
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import json
import time
import pandas as pd
import numpy as np
import xgboost as xgb
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_data_service import BinanceDataService
from src.data.features import FeatureEngineer
from src.models.model_loader import ModelLoader


class HistoricalBacktester:
    """
    Backtester que genera señales históricas sin data leakage.
    """

    def __init__(self):
        logger.info("Initializing Historical Backtester...")

        self.db = DatabaseManager(settings.get_database_url())
        self.binance_data = BinanceDataService()
        self.feature_engineer = FeatureEngineer()

        # Cargar modelo
        self.model_loader = ModelLoader(settings.MODEL_FILE)
        self.model = self.model_loader.load_model()

        self.threshold = settings.PREDICTION_THRESHOLD

        # Cache para datos históricos (evita descargar múltiples veces)
        self.data_cache = {}

        logger.info(f"Model loaded. Threshold: {self.threshold}")

    def download_all_historical_data(self, days_needed: int = 300):
        """
        Descarga todos los datos históricos necesarios una vez.
        Guarda en cache para usar en el backtest.
        """
        logger.info(f"\n📥 Downloading historical data for all tickers ({days_needed} days)...")

        for ticker in settings.TICKERS:
            try:
                data = self.binance_data.get_historical_klines(
                    symbol=ticker,
                    interval='1d',
                    limit=days_needed
                )

                if data is not None and len(data) > 0:
                    data['timestamp'] = pd.to_datetime(data['timestamp'])
                    data = data.sort_values('timestamp').reset_index(drop=True)
                    self.data_cache[ticker] = data
                    logger.debug(f"  ✓ {ticker}: {len(data)} candles")
                else:
                    logger.warning(f"  ✗ {ticker}: No data")

            except Exception as e:
                logger.warning(f"  ✗ {ticker}: {e}")

        # También BTC para correlaciones
        btc_data = self.binance_data.get_historical_klines(
            symbol='BTCUSDT',
            interval='1d',
            limit=days_needed
        )
        if btc_data is not None:
            btc_data['timestamp'] = pd.to_datetime(btc_data['timestamp'])
            btc_data = btc_data.sort_values('timestamp').reset_index(drop=True)
            self.data_cache['BTCUSDT'] = btc_data

        logger.info(f"✅ Downloaded data for {len(self.data_cache)} tickers")

    def get_data_until_date(self, ticker: str, end_date: datetime, min_candles: int = 200) -> pd.DataFrame:
        """
        Obtiene datos del cache SOLO hasta end_date.
        CRÍTICO: No incluye datos después de end_date (evita data leakage).
        """
        if ticker not in self.data_cache:
            return pd.DataFrame()

        all_data = self.data_cache[ticker]

        # CRÍTICO: Filtrar solo datos hasta end_date (inclusive)
        filtered = all_data[all_data['timestamp'].dt.date <= end_date.date()].copy()

        # Tomar solo los últimos min_candles
        if len(filtered) > min_candles:
            filtered = filtered.tail(min_candles + 50).reset_index(drop=True)

        return filtered

    def simulate_macro_data_for_date(self, target_date: datetime) -> dict:
        """
        Simula/estima macro data para una fecha pasada.
        En un sistema real, tendríamos datos históricos de Fear&Greed, VIX, etc.
        Por ahora usamos valores aproximados o promedio.
        """
        # Valores típicos/promedio (en producción guardaríamos históricos)
        # Fear & Greed típicamente oscila entre 20-80
        # VIX típicamente entre 12-30
        # SPX alrededor de 4500-5000 en 2024

        # Usar un valor base con algo de variación basada en el día
        day_of_year = target_date.timetuple().tm_yday
        np.random.seed(day_of_year)  # Reproducible para cada día

        return {
            'fear_greed': float(np.random.randint(20, 70)),  # Simulado
            'funding_rate': float(np.random.uniform(-0.001, 0.001)),
            'spx': float(np.random.uniform(4800, 5200)),
            'spx_change_7d': float(np.random.uniform(-0.03, 0.03)),
            'vix': float(np.random.uniform(12, 25))
        }

    def generate_signals_for_date(self, target_date: datetime) -> list:
        """
        Genera señales para una fecha específica.
        SOLO usa datos disponibles hasta esa fecha.
        """
        signals = []

        logger.info(f"\n{'='*60}")
        logger.info(f"Processing date: {target_date.date()}")
        logger.info(f"{'='*60}")

        # Obtener BTC data hasta target_date (para features de correlación)
        btc_data = self.get_data_until_date('BTCUSDT', target_date)
        if len(btc_data) < 200:
            logger.warning(f"Insufficient BTC data for {target_date.date()}")
            return signals

        # Macro data para esa fecha
        macro_data = self.simulate_macro_data_for_date(target_date)
        logger.info(f"Macro data: F&G={macro_data['fear_greed']:.0f}, VIX={macro_data['vix']:.1f}")

        # Procesar cada ticker
        buy_count = 0
        for ticker in settings.TICKERS:
            try:
                # Obtener datos hasta target_date SOLAMENTE
                ticker_data = self.get_data_until_date(ticker, target_date)

                if len(ticker_data) < 200:
                    logger.debug(f"  {ticker}: Insufficient data ({len(ticker_data)} candles)")
                    continue

                # Verificar que el último dato es de target_date o antes
                last_date = ticker_data['timestamp'].max()
                if last_date.date() > target_date.date():
                    logger.error(f"  {ticker}: DATA LEAKAGE DETECTED! Last date {last_date} > target {target_date}")
                    continue

                # Calcular features
                features = self.feature_engineer.calculate_single_prediction_features(
                    ticker_data=ticker_data,
                    btc_data=btc_data,
                    macro_data=macro_data
                )

                if features is None:
                    continue

                # Hacer predicción
                dmatrix = xgb.DMatrix(
                    features.reshape(1, -1),
                    feature_names=self.feature_engineer.required_features
                )
                probability = float(self.model.predict(dmatrix)[0])

                # Determinar tipo de señal
                signal_type = 'BUY' if probability >= self.threshold else 'HOLD'

                if signal_type == 'BUY':
                    buy_count += 1
                    logger.info(f"  🟢 {ticker}: {probability:.4f} ({probability*100:.1f}%) - BUY")

                # Crear diccionario de features para guardar
                features_dict = {
                    name: float(val)
                    for name, val in zip(self.feature_engineer.required_features, features)
                }

                signals.append({
                    'ticker': ticker,
                    'signal_type': signal_type,
                    'probability': probability,
                    'features': features_dict,
                    'timestamp': target_date
                })

            except Exception as e:
                logger.debug(f"  {ticker}: Error - {e}")
                continue

        logger.info(f"\nDate {target_date.date()}: {len(signals)} signals, {buy_count} BUY")
        return signals

    def save_signals_to_db(self, signals: list):
        """Guarda las señales en la base de datos"""
        saved_count = 0
        for signal in signals:
            try:
                self.db.save_signal(
                    ticker=signal['ticker'],
                    signal_type=signal['signal_type'],
                    probability=signal['probability'],
                    features=signal['features']
                )
                # Actualizar el timestamp manualmente
                # (save_signal usa NOW(), pero queremos la fecha histórica)
                update_query = """
                UPDATE signals
                SET timestamp = :timestamp
                WHERE id = (SELECT MAX(id) FROM signals WHERE ticker = :ticker)
                """
                self.db.execute_command(update_query, {
                    'timestamp': signal['timestamp'],
                    'ticker': signal['ticker']
                })
                saved_count += 1
            except Exception as e:
                logger.error(f"Failed to save signal: {e}")

        return saved_count

    def run_backtest(self, days_back: int = 30):
        """
        Ejecuta el backtest para los últimos N días.
        """
        logger.info("=" * 70)
        logger.info(f"HISTORICAL BACKTEST - Last {days_back} days")
        logger.info("=" * 70)
        logger.info(f"Threshold: {self.threshold}")
        logger.info(f"Tickers: {len(settings.TICKERS)}")
        logger.info("=" * 70)

        # Calcular fechas
        end_date = datetime.utcnow() - timedelta(days=1)  # Ayer
        start_date = end_date - timedelta(days=days_back)

        logger.info(f"\nBacktest period: {start_date.date()} to {end_date.date()}")

        # Descargar todos los datos históricos primero
        # Necesitamos días_back + 250 (para features) + margen
        days_needed = days_back + 260
        self.download_all_historical_data(days_needed)

        all_signals = []
        current_date = start_date

        while current_date <= end_date:
            signals = self.generate_signals_for_date(current_date)
            all_signals.extend(signals)

            # Guardar en BD
            if signals:
                saved = self.save_signals_to_db(signals)
                logger.info(f"Saved {saved} signals to database")

            # Siguiente día
            current_date += timedelta(days=1)

            # Pequeña pausa para no sobrecargar la API
            time.sleep(0.5)

        # Resumen final
        logger.info("\n" + "=" * 70)
        logger.info("BACKTEST COMPLETE - SUMMARY")
        logger.info("=" * 70)

        signals_df = pd.DataFrame(all_signals)

        if len(signals_df) > 0:
            logger.info(f"\nTotal signals generated: {len(signals_df)}")
            logger.info(f"BUY signals: {len(signals_df[signals_df['signal_type'] == 'BUY'])}")
            logger.info(f"HOLD signals: {len(signals_df[signals_df['signal_type'] == 'HOLD'])}")

            logger.info(f"\nProbability statistics:")
            logger.info(f"  Mean:   {signals_df['probability'].mean():.4f}")
            logger.info(f"  Median: {signals_df['probability'].median():.4f}")
            logger.info(f"  Std:    {signals_df['probability'].std():.4f}")
            logger.info(f"  Min:    {signals_df['probability'].min():.4f}")
            logger.info(f"  Max:    {signals_df['probability'].max():.4f}")

            # Distribución
            logger.info(f"\nProbability distribution:")
            for t in [0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.97, 0.99]:
                count = len(signals_df[signals_df['probability'] >= t])
                pct = count / len(signals_df) * 100
                logger.info(f"  >= {t:.0%}: {count:4d} ({pct:5.1f}%)")

            # Por día
            signals_df['date'] = pd.to_datetime(signals_df['timestamp']).dt.date
            daily_buys = signals_df[signals_df['signal_type'] == 'BUY'].groupby('date').size()

            logger.info(f"\nBUY signals by day:")
            for date, count in daily_buys.items():
                logger.info(f"  {date}: {count} BUY signals")

        return signals_df


def main():
    parser = argparse.ArgumentParser(description="Run historical backtest")
    parser.add_argument('--days', type=int, default=30,
                        help='Number of days to backtest (default: 30)')
    args = parser.parse_args()

    backtester = HistoricalBacktester()
    results = backtester.run_backtest(days_back=args.days)

    logger.info("\n✅ Backtest complete! Run forensic_analysis.py to analyze results.")


if __name__ == "__main__":
    main()
