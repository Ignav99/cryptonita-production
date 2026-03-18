#!/usr/bin/env python3
"""
VERIFY SIGNAL PERFORMANCE
=========================
Verifica si las señales BUY realmente produjeron los pumps esperados.

Para cada señal BUY:
1. Obtiene el precio en la fecha de la señal
2. Obtiene el precio máximo en los siguientes 30 días
3. Calcula el rendimiento real
4. Compara con el target del modelo (+20%)
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from src.data.storage.db_manager import DatabaseManager


def verify_signal_performance():
    """Verifica el rendimiento real de las señales BUY"""

    logger.info("=" * 70)
    logger.info("VERIFICACIÓN DE RENDIMIENTO DE SEÑALES")
    logger.info("=" * 70)

    db = DatabaseManager(settings.get_database_url())

    # 1. Obtener señales BUY de la tabla signals
    signals_df = db.execute_query("""
        SELECT id, ticker, signal_type, probability, timestamp
        FROM signals
        WHERE signal_type = 'BUY'
        ORDER BY timestamp ASC
    """, {})

    if len(signals_df) == 0:
        logger.error("No hay señales BUY en la base de datos")
        return

    logger.info(f"\n📊 Total señales BUY: {len(signals_df)}")

    # 2. Para cada señal, verificar el rendimiento real
    results = []

    for _, signal in signals_df.iterrows():
        ticker = signal['ticker']
        signal_date = pd.to_datetime(signal['timestamp']).tz_localize(None)
        probability = signal['probability']

        # Obtener precio en la fecha de la señal
        price_at_signal = db.execute_query("""
            SELECT close FROM crypto_prices
            WHERE ticker = :ticker
            AND DATE(timestamp) = DATE(:signal_date)
            LIMIT 1
        """, {'ticker': ticker, 'signal_date': signal_date})

        if len(price_at_signal) == 0:
            continue

        entry_price = float(price_at_signal.iloc[0]['close'])

        # Obtener fecha más reciente en la BD para este ticker
        latest_date_df = db.execute_query("""
            SELECT MAX(timestamp) as latest FROM crypto_prices WHERE ticker = :ticker
        """, {'ticker': ticker})
        latest_date = pd.to_datetime(latest_date_df.iloc[0]['latest']).tz_localize(None)

        # Calcular días disponibles desde la señal
        days_available = (latest_date - signal_date).days

        # Obtener precio máximo en los siguientes 30 días (o hasta donde haya datos)
        end_date = min(signal_date + timedelta(days=30), latest_date)

        max_price_df = db.execute_query("""
            SELECT MAX(high) as max_price, MAX(close) as max_close
            FROM crypto_prices
            WHERE ticker = :ticker
            AND timestamp > :signal_date
            AND timestamp <= :end_date
        """, {'ticker': ticker, 'signal_date': signal_date, 'end_date': end_date})

        if len(max_price_df) == 0 or max_price_df.iloc[0]['max_price'] is None:
            continue

        max_price = float(max_price_df.iloc[0]['max_price'])

        # Calcular rendimiento
        max_return = (max_price - entry_price) / entry_price * 100

        # ¿Alcanzó el target de +20%?
        hit_target = max_return >= 20.0

        results.append({
            'ticker': ticker,
            'signal_date': signal_date.date(),
            'probability': probability,
            'entry_price': entry_price,
            'max_price': max_price,
            'max_return_pct': max_return,
            'hit_20pct': hit_target,
            'days_available': days_available
        })

    if not results:
        logger.error("No se pudieron calcular rendimientos (faltan datos de precios)")
        return

    results_df = pd.DataFrame(results)

    # 3. Análisis de resultados
    logger.info("\n" + "=" * 70)
    logger.info("RESULTADOS")
    logger.info("=" * 70)

    total = len(results_df)
    hits = results_df['hit_20pct'].sum()
    hit_rate = hits / total * 100

    logger.info(f"\n📈 Señales analizadas: {total}")
    logger.info(f"✅ Alcanzaron +20%: {hits} ({hit_rate:.1f}%)")
    logger.info(f"❌ No alcanzaron +20%: {total - hits} ({100 - hit_rate:.1f}%)")

    # Estadísticas de rendimiento
    logger.info(f"\n📊 Estadísticas de rendimiento máximo (TODAS):")
    logger.info(f"   Media: {results_df['max_return_pct'].mean():.2f}%")
    logger.info(f"   Mediana: {results_df['max_return_pct'].median():.2f}%")
    logger.info(f"   Min: {results_df['max_return_pct'].min():.2f}%")
    logger.info(f"   Max: {results_df['max_return_pct'].max():.2f}%")

    # ANÁLISIS CRÍTICO: Señales maduras vs recientes
    logger.info("\n" + "=" * 70)
    logger.info("⚠️  ANÁLISIS CRÍTICO: SEÑALES MADURAS vs RECIENTES")
    logger.info("=" * 70)
    logger.info("Las señales recientes NO han tenido tiempo de alcanzar +20%")

    mature_df = results_df[results_df['days_available'] >= 20]
    recent_df = results_df[results_df['days_available'] < 20]

    if len(mature_df) > 0:
        mature_hits = mature_df['hit_20pct'].sum()
        mature_rate = mature_hits / len(mature_df) * 100
        logger.info(f"\n🟢 SEÑALES MADURAS (≥20 días disponibles):")
        logger.info(f"   Total: {len(mature_df)}")
        logger.info(f"   Hit rate (+20%): {mature_rate:.1f}%")
        logger.info(f"   Rendimiento medio: {mature_df['max_return_pct'].mean():.2f}%")
        logger.info(f"   Días disponibles medio: {mature_df['days_available'].mean():.0f}")

    if len(recent_df) > 0:
        recent_hits = recent_df['hit_20pct'].sum()
        recent_rate = recent_hits / len(recent_df) * 100 if len(recent_df) > 0 else 0
        logger.info(f"\n🟡 SEÑALES RECIENTES (<20 días disponibles):")
        logger.info(f"   Total: {len(recent_df)}")
        logger.info(f"   Hit rate (+20%): {recent_rate:.1f}% (NO REPRESENTATIVO)")
        logger.info(f"   Rendimiento medio: {recent_df['max_return_pct'].mean():.2f}%")
        logger.info(f"   Días disponibles medio: {recent_df['days_available'].mean():.0f}")

    # Por rangos de probabilidad
    logger.info("\n" + "-" * 70)
    logger.info("RENDIMIENTO POR RANGO DE PROBABILIDAD")
    logger.info("-" * 70)

    prob_ranges = [
        (0.97, 1.00, "97-100%"),
        (0.95, 0.97, "95-97%"),
        (0.90, 0.95, "90-95%"),
        (0.80, 0.90, "80-90%"),
        (0.70, 0.80, "70-80%"),
    ]

    for low, high, label in prob_ranges:
        subset = results_df[(results_df['probability'] >= low) & (results_df['probability'] < high)]
        if len(subset) > 0:
            sub_hits = subset['hit_20pct'].sum()
            sub_rate = sub_hits / len(subset) * 100
            avg_return = subset['max_return_pct'].mean()
            logger.info(f"   {label}: {len(subset):3d} señales | Hit rate: {sub_rate:5.1f}% | Avg return: {avg_return:+6.2f}%")

    # Señales con prob >= 97% (nuestro threshold)
    high_conf = results_df[results_df['probability'] >= 0.97]
    if len(high_conf) > 0:
        logger.info("\n" + "-" * 70)
        logger.info(f"SEÑALES CON PROBABILIDAD >= 97% (threshold actual)")
        logger.info("-" * 70)
        logger.info(f"   Total: {len(high_conf)}")
        logger.info(f"   Hit rate (+20%): {high_conf['hit_20pct'].sum() / len(high_conf) * 100:.1f}%")
        logger.info(f"   Rendimiento medio: {high_conf['max_return_pct'].mean():.2f}%")

    # Top 10 mejores señales
    logger.info("\n" + "-" * 70)
    logger.info("TOP 10 MEJORES SEÑALES")
    logger.info("-" * 70)

    top10 = results_df.nlargest(10, 'max_return_pct')
    for _, row in top10.iterrows():
        logger.info(f"   {row['signal_date']} | {row['ticker']:12s} | prob: {row['probability']:.2f} | return: {row['max_return_pct']:+.1f}%")

    # Top 10 peores señales
    logger.info("\n" + "-" * 70)
    logger.info("TOP 10 PEORES SEÑALES")
    logger.info("-" * 70)

    bottom10 = results_df.nsmallest(10, 'max_return_pct')
    for _, row in bottom10.iterrows():
        logger.info(f"   {row['signal_date']} | {row['ticker']:12s} | prob: {row['probability']:.2f} | return: {row['max_return_pct']:+.1f}%")

    # Por ticker
    logger.info("\n" + "-" * 70)
    logger.info("RENDIMIENTO POR TICKER")
    logger.info("-" * 70)

    ticker_stats = results_df.groupby('ticker').agg({
        'max_return_pct': ['count', 'mean'],
        'hit_20pct': 'sum'
    }).round(2)
    ticker_stats.columns = ['signals', 'avg_return', 'hits']
    ticker_stats['hit_rate'] = (ticker_stats['hits'] / ticker_stats['signals'] * 100).round(1)
    ticker_stats = ticker_stats.sort_values('avg_return', ascending=False)

    for ticker, row in ticker_stats.head(15).iterrows():
        logger.info(f"   {ticker:12s} | {int(row['signals']):3d} signals | avg: {row['avg_return']:+6.2f}% | hit rate: {row['hit_rate']:5.1f}%")

    # Por fecha
    logger.info("\n" + "-" * 70)
    logger.info("RENDIMIENTO POR FECHA DE SEÑAL")
    logger.info("-" * 70)

    date_stats = results_df.groupby('signal_date').agg({
        'max_return_pct': ['count', 'mean'],
        'hit_20pct': 'sum'
    }).round(2)
    date_stats.columns = ['signals', 'avg_return', 'hits']
    date_stats['hit_rate'] = (date_stats['hits'] / date_stats['signals'] * 100).round(1)

    for date, row in date_stats.iterrows():
        logger.info(f"   {date} | {int(row['signals']):3d} signals | avg: {row['avg_return']:+6.2f}% | hit rate: {row['hit_rate']:5.1f}%")

    # Conclusión - USAR SOLO SEÑALES MADURAS para evaluar
    logger.info("\n" + "=" * 70)
    logger.info("CONCLUSIÓN (basada en señales maduras ≥20 días)")
    logger.info("=" * 70)

    # Usar hit rate de señales maduras, no de todas
    mature_df = results_df[results_df['days_available'] >= 20]
    if len(mature_df) > 0:
        mature_hit_rate = mature_df['hit_20pct'].sum() / len(mature_df) * 100
        mature_avg_return = mature_df['max_return_pct'].mean()
    else:
        mature_hit_rate = hit_rate
        mature_avg_return = results_df['max_return_pct'].mean()

    logger.info(f"\n📊 Señales maduras: {len(mature_df)}")
    logger.info(f"📊 Hit rate (maduras): {mature_hit_rate:.1f}%")
    logger.info(f"📊 Rendimiento medio (maduras): {mature_avg_return:.1f}%")

    if mature_hit_rate >= 60:
        logger.success(f"\n✅ MODELO FUNCIONA BIEN - Hit rate: {mature_hit_rate:.1f}%")
        logger.info("   Las señales maduras están prediciendo pumps reales.")
        logger.info("   El modelo detecta correctamente oportunidades de rebote.")
    elif mature_hit_rate >= 40:
        logger.warning(f"\n⚠️ MODELO FUNCIONA MODERADAMENTE - Hit rate: {mature_hit_rate:.1f}%")
        logger.info("   Algunas señales aciertan, rendimiento positivo pero menor al target.")
    else:
        logger.error(f"\n❌ MODELO NECESITA REVISIÓN - Hit rate: {mature_hit_rate:.1f}%")
        logger.info("   Las señales no están correlacionadas con pumps +20%.")

    # Recomendaciones
    logger.info("\n" + "-" * 70)
    logger.info("RECOMENDACIONES")
    logger.info("-" * 70)
    if mature_avg_return >= 15 and mature_hit_rate < 60:
        logger.info("   - Rendimiento medio bueno pero target muy alto")
        logger.info("   - Considerar reducir target de +20% a +15%")
        logger.info("   - O ajustar take-profit dinámico al rendimiento real")

    return results_df


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

    verify_signal_performance()
