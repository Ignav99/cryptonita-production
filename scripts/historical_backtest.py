#!/usr/bin/env python3
"""
Historical Backtest - Generate Signals Day by Day
==================================================
Genera señales históricas día por día usando datos de la BD,
asegurando que el modelo NUNCA ve datos futuros (no data leakage).

Para cada día D:
- Usa SOLO datos desde la BD hasta el día D
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
import pandas as pd
import numpy as np
import xgboost as xgb
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.data.features import FeatureEngineer
from src.models.model_loader import ModelLoader


class HistoricalBacktester:
    """
    Backtester que genera señales históricas sin data leakage.
    Usa datos de la base de datos (crypto_prices).
    """

    def __init__(self):
        logger.info("Initializing Historical Backtester...")

        self.db = DatabaseManager(settings.get_database_url())
        self.feature_engineer = FeatureEngineer()

        # Cargar modelo
        self.model_loader = ModelLoader(settings.MODEL_FILE)
        self.model = self.model_loader.load_model()

        self.threshold = settings.PREDICTION_THRESHOLD

        logger.info(f"Model loaded. Threshold: {self.threshold}")

    def check_database_data(self):
        """Verifica qué datos hay en la BD"""
        query = """
        SELECT
            COUNT(*) as total_records,
            COUNT(DISTINCT ticker) as unique_tickers,
            MIN(timestamp) as earliest_date,
            MAX(timestamp) as latest_date
        FROM crypto_prices
        """
        result = self.db.execute_query(query)
        row = result.iloc[0]

        logger.info(f"\n📊 Database crypto_prices info:")
        logger.info(f"  Total records: {row['total_records']:,}")
        logger.info(f"  Unique tickers: {row['unique_tickers']}")
        logger.info(f"  Date range: {row['earliest_date']} to {row['latest_date']}")

        # Listar tickers disponibles
        ticker_query = "SELECT DISTINCT ticker FROM crypto_prices ORDER BY ticker"
        tickers = self.db.execute_query(ticker_query)['ticker'].tolist()
        logger.info(f"  Tickers: {', '.join(tickers[:10])}{'...' if len(tickers) > 10 else ''}")

        return {
            'total': row['total_records'],
            'tickers': row['unique_tickers'],
            'earliest': row['earliest_date'],
            'latest': row['latest_date']
        }

    def get_data_until_date(self, ticker: str, end_date: datetime, min_candles: int = 250) -> pd.DataFrame:
        """
        Obtiene datos de la BD SOLO hasta end_date.
        CRÍTICO: No incluye datos después de end_date (evita data leakage).
        """
        # Calcular fecha de inicio (necesitamos min_candles días antes)
        start_date = end_date - timedelta(days=min_candles + 50)

        data = self.db.get_price_history(
            ticker=ticker,
            start_date=start_date,
            end_date=end_date
        )

        if len(data) == 0:
            return pd.DataFrame()

        # Asegurar que timestamp es datetime
        data['timestamp'] = pd.to_datetime(data['timestamp'])

        # Verificar que no hay datos del futuro
        max_date = data['timestamp'].max()
        if max_date.date() > end_date.date():
            logger.error(f"DATA LEAKAGE: {ticker} has data from {max_date} > {end_date}")
            data = data[data['timestamp'].dt.date <= end_date.date()]

        return data.sort_values('timestamp').reset_index(drop=True)

    def simulate_macro_data_for_date(self, target_date: datetime) -> dict:
        """
        Simula/estima macro data para una fecha pasada.
        En un sistema real, tendríamos datos históricos.
        Usamos valores que varían de forma reproducible por fecha.
        """
        # Seed basado en la fecha para reproducibilidad
        day_seed = int(target_date.strftime('%Y%m%d'))
        np.random.seed(day_seed)

        return {
            'fear_greed': float(np.random.randint(20, 70)),
            'funding_rate': float(np.random.uniform(-0.001, 0.001)),
            'spx': float(np.random.uniform(4800, 5200)),
            'spx_change_7d': float(np.random.uniform(-0.03, 0.03)),
            'vix': float(np.random.uniform(12, 25))
        }

    def generate_signals_for_date(self, target_date: datetime, available_tickers: list) -> list:
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
            logger.warning(f"Insufficient BTC data for {target_date.date()} ({len(btc_data)} candles)")
            return signals

        # Macro data para esa fecha
        macro_data = self.simulate_macro_data_for_date(target_date)

        # Procesar cada ticker
        buy_count = 0
        processed = 0

        for ticker in available_tickers:
            if ticker == 'BTCUSDT':  # Skip BTC (ya lo tenemos para correlación)
                continue

            try:
                # Obtener datos hasta target_date SOLAMENTE
                ticker_data = self.get_data_until_date(ticker, target_date)

                if len(ticker_data) < 200:
                    continue

                processed += 1

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

        logger.info(f"Date {target_date.date()}: processed {processed} tickers, {buy_count} BUY signals")
        return signals

    def save_signals_to_db(self, signals: list):
        """Guarda las señales en la base de datos con timestamp correcto"""
        saved_count = 0
        for signal in signals:
            try:
                # Guardar señal
                signal_id = self.db.save_signal(
                    ticker=signal['ticker'],
                    signal_type=signal['signal_type'],
                    probability=signal['probability'],
                    features=signal['features']
                )

                # Actualizar el timestamp al histórico (save_signal usa NOW())
                update_query = """
                UPDATE signals
                SET timestamp = :timestamp
                WHERE id = :signal_id
                """
                self.db.execute_command(update_query, {
                    'timestamp': signal['timestamp'],
                    'signal_id': signal_id
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
        logger.info("=" * 70)

        # Verificar datos en BD
        db_info = self.check_database_data()

        if db_info['total'] == 0:
            logger.error("No data in crypto_prices table!")
            return None

        # Obtener tickers disponibles en la BD
        ticker_query = "SELECT DISTINCT ticker FROM crypto_prices"
        available_tickers = self.db.execute_query(ticker_query)['ticker'].tolist()
        logger.info(f"\nAvailable tickers in DB: {len(available_tickers)}")

        # Calcular fechas del backtest
        end_date = datetime.utcnow() - timedelta(days=1)  # Ayer
        start_date = end_date - timedelta(days=days_back)

        # Verificar que tenemos datos suficientes
        if db_info['earliest'] and pd.to_datetime(db_info['earliest']).date() > start_date.date():
            logger.warning(f"DB data starts at {db_info['earliest']}, adjusting start date")
            start_date = pd.to_datetime(db_info['earliest']) + timedelta(days=250)

        logger.info(f"\nBacktest period: {start_date.date()} to {end_date.date()}")

        all_signals = []
        current_date = start_date

        while current_date <= end_date:
            signals = self.generate_signals_for_date(current_date, available_tickers)
            all_signals.extend(signals)

            # Guardar en BD
            if signals:
                saved = self.save_signals_to_db(signals)
                logger.info(f"Saved {saved} signals to database")

            # Siguiente día
            current_date += timedelta(days=1)

        # Resumen final
        self.print_summary(all_signals)

        return pd.DataFrame(all_signals)

    def print_summary(self, all_signals: list):
        """Imprime resumen del backtest"""
        logger.info("\n" + "=" * 70)
        logger.info("BACKTEST COMPLETE - SUMMARY")
        logger.info("=" * 70)

        if not all_signals:
            logger.warning("No signals generated!")
            return

        signals_df = pd.DataFrame(all_signals)

        logger.info(f"\nTotal signals generated: {len(signals_df)}")
        buy_signals = signals_df[signals_df['signal_type'] == 'BUY']
        logger.info(f"BUY signals: {len(buy_signals)}")
        logger.info(f"HOLD signals: {len(signals_df) - len(buy_signals)}")

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

        # BUY signals por día
        if len(buy_signals) > 0:
            signals_df['date'] = pd.to_datetime(signals_df['timestamp']).dt.date
            daily_buys = buy_signals.groupby(pd.to_datetime(buy_signals['timestamp']).dt.date).size()

            logger.info(f"\nBUY signals by day:")
            for date, count in daily_buys.items():
                logger.info(f"  {date}: {count} BUY signals")

        logger.info("\n✅ Now run: python scripts/forensic_analysis.py")


def main():
    parser = argparse.ArgumentParser(description="Run historical backtest using DB data")
    parser.add_argument('--days', type=int, default=30,
                        help='Number of days to backtest (default: 30)')
    args = parser.parse_args()

    backtester = HistoricalBacktester()
    results = backtester.run_backtest(days_back=args.days)


if __name__ == "__main__":
    main()
