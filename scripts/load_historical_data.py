#!/usr/bin/env python3
"""
LOAD HISTORICAL DATA
====================
Descarga datos históricos de Binance Production y los guarda en crypto_prices.

Uso:
    python scripts/load_historical_data.py --days 365
    python scripts/load_historical_data.py --days 365 --force  # Borra datos existentes primero
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import argparse
import pandas as pd
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_data_service import BinanceDataService


def load_historical_data(days: int = 365, force: bool = False):
    """
    Descarga datos históricos de Binance y los guarda en la BD.

    Args:
        days: Número de días de historia a descargar
        force: Si True, borra datos existentes antes de cargar
    """
    logger.info("=" * 60)
    logger.info(f"📥 CARGA DE DATOS HISTÓRICOS - {days} días")
    logger.info("=" * 60)

    # Inicializar servicios
    db = DatabaseManager(settings.get_database_url())
    binance = BinanceDataService()

    # Si force, limpiar tabla primero
    if force:
        logger.warning("⚠️  Limpiando tabla crypto_prices...")
        try:
            db.execute_query("TRUNCATE TABLE crypto_prices", {})
            logger.info("✅ Tabla crypto_prices vaciada")
        except Exception as e:
            logger.warning(f"No se pudo truncar (probablemente no existe): {e}")

    # Verificar estado actual
    try:
        result = db.execute_query("""
            SELECT COUNT(*) as total,
                   COUNT(DISTINCT ticker) as tickers,
                   MIN(timestamp) as earliest,
                   MAX(timestamp) as latest
            FROM crypto_prices
        """, {})
        row = result.iloc[0]
        logger.info(f"\n📊 Estado actual de crypto_prices:")
        logger.info(f"   Total registros: {row['total']:,}")
        logger.info(f"   Tickers únicos: {row['tickers']}")
        logger.info(f"   Rango: {row['earliest']} a {row['latest']}")
    except Exception as e:
        logger.warning(f"No se pudo verificar estado: {e}")

    # Descargar datos para cada ticker
    logger.info(f"\n📥 Descargando {days} días de datos para {len(settings.TICKERS)} tickers...")

    all_data = []
    success_count = 0
    failed_tickers = []

    for i, ticker in enumerate(settings.TICKERS, 1):
        logger.info(f"\n[{i}/{len(settings.TICKERS)}] {ticker}...")

        try:
            df = binance.get_historical_klines(
                symbol=ticker,
                interval='1d',
                lookback_days=days
            )

            if df is not None and len(df) > 0:
                # Añadir columna ticker
                df['ticker'] = ticker

                # Asegurar columnas correctas
                df = df[['timestamp', 'ticker', 'open', 'high', 'low', 'close', 'volume']]

                all_data.append(df)
                success_count += 1
                logger.success(f"   ✅ {len(df)} velas descargadas")
            else:
                logger.warning(f"   ⚠️  Sin datos")
                failed_tickers.append(ticker)

        except Exception as e:
            logger.error(f"   ❌ Error: {e}")
            failed_tickers.append(ticker)

    if not all_data:
        logger.error("❌ No se descargó ningún dato!")
        return False

    # Combinar todos los datos
    combined_df = pd.concat(all_data, ignore_index=True)
    logger.info(f"\n📊 Total combinado: {len(combined_df):,} registros")

    # Eliminar duplicados por (timestamp, ticker)
    before_dedup = len(combined_df)
    combined_df = combined_df.drop_duplicates(subset=['timestamp', 'ticker'], keep='last')
    after_dedup = len(combined_df)

    if before_dedup != after_dedup:
        logger.info(f"   Eliminados {before_dedup - after_dedup} duplicados")

    # Guardar en la base de datos
    logger.info(f"\n💾 Guardando {len(combined_df):,} registros en crypto_prices...")

    try:
        # Usar upsert para evitar conflictos con datos existentes
        # Primero intentamos insertar directamente
        db.save_crypto_prices(combined_df)
        logger.success(f"✅ Datos guardados exitosamente")
    except Exception as e:
        logger.warning(f"Error al guardar directamente: {e}")
        logger.info("Intentando insertar por lotes con manejo de duplicados...")

        # Insertar en lotes pequeños, ignorando duplicados
        batch_size = 1000
        saved = 0

        for start in range(0, len(combined_df), batch_size):
            batch = combined_df.iloc[start:start + batch_size]
            try:
                db.save_crypto_prices(batch)
                saved += len(batch)
            except Exception as batch_e:
                # Si falla, intentar uno por uno
                for _, row in batch.iterrows():
                    try:
                        single_df = pd.DataFrame([row])
                        db.save_crypto_prices(single_df)
                        saved += 1
                    except:
                        pass  # Ignorar duplicados

        logger.info(f"   Guardados {saved:,} registros")

    # Verificar resultado final
    result = db.execute_query("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT ticker) as tickers,
               MIN(timestamp) as earliest,
               MAX(timestamp) as latest
        FROM crypto_prices
    """, {})
    row = result.iloc[0]

    logger.info("\n" + "=" * 60)
    logger.info("📊 RESULTADO FINAL")
    logger.info("=" * 60)
    logger.info(f"   Total registros: {row['total']:,}")
    logger.info(f"   Tickers únicos: {row['tickers']}")
    logger.info(f"   Rango fechas: {row['earliest']} a {row['latest']}")
    logger.info(f"   Tickers exitosos: {success_count}/{len(settings.TICKERS)}")

    if failed_tickers:
        logger.warning(f"   Tickers fallidos: {', '.join(failed_tickers)}")

    logger.success("\n🎉 CARGA COMPLETADA")
    return True


def main():
    parser = argparse.ArgumentParser(description='Cargar datos históricos de Binance')
    parser.add_argument('--days', type=int, default=365, help='Días de historia a cargar (default: 365)')
    parser.add_argument('--force', action='store_true', help='Limpiar datos existentes antes de cargar')

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

    success = load_historical_data(days=args.days, force=args.force)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
