#!/usr/bin/env python3
"""
CRYPTONITA MVP - INITIAL DATA LOAD
===================================
Carga inicial de datos históricos usando las clases existentes:
- BinanceDataService para OHLCV
- db_manager para guardar en crypto_prices

Uso:
    python scripts/initial_data_load.py             # 365 días (default)
    python scripts/initial_data_load.py --days 365  # Especificar días
    python scripts/initial_data_load.py --force     # Limpiar tabla primero
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
import pandas as pd
from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_data_service import BinanceDataService


def run_initial_data_load(days: int = 365, force: bool = False):
    """
    Ejecuta carga inicial de datos OHLCV desde Binance a la BD.

    Args:
        days: Días de historia a cargar
        force: Si True, limpia la tabla antes de cargar
    """
    logger.info("=" * 60)
    logger.info(f"🚀 CARGA INICIAL DE DATOS - {days} días")
    logger.info("=" * 60)

    # Inicializar servicios existentes
    db = DatabaseManager(settings.get_database_url())
    binance = BinanceDataService()

    # Si force, limpiar tabla primero
    if force:
        logger.warning("⚠️ Limpiando tabla crypto_prices...")
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text("TRUNCATE TABLE crypto_prices"))
                conn.commit()
            logger.info("✅ Tabla crypto_prices vaciada")
        except Exception as e:
            logger.warning(f"No se pudo truncar: {e}")

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
        logger.info(f"   Tickers: {row['tickers']}")
        logger.info(f"   Rango: {row['earliest']} a {row['latest']}")

        if row['total'] > 0 and not force:
            logger.warning("⚠️ Ya hay datos en la tabla. Usa --force para recargar.")
            logger.info("   Continuando para añadir datos faltantes...")
    except Exception as e:
        logger.warning(f"No se pudo verificar estado: {e}")

    # Descargar datos para cada ticker
    logger.info(f"\n📥 Descargando {days} días para {len(settings.TICKERS)} tickers...")

    all_data = []
    success_count = 0
    failed_tickers = []

    for i, ticker in enumerate(settings.TICKERS, 1):
        logger.info(f"[{i}/{len(settings.TICKERS)}] {ticker}...")

        try:
            # Usar BinanceDataService existente
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
                logger.success(f"   ✅ {len(df)} velas")
            else:
                logger.warning(f"   ⚠️ Sin datos")
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

    # Eliminar duplicados
    before_dedup = len(combined_df)
    combined_df = combined_df.drop_duplicates(subset=['timestamp', 'ticker'], keep='last')
    if before_dedup != len(combined_df):
        logger.info(f"   Eliminados {before_dedup - len(combined_df)} duplicados")

    # Guardar en la base de datos
    logger.info(f"\n💾 Guardando en crypto_prices...")

    try:
        # Usar save_crypto_prices existente
        db.save_crypto_prices(combined_df)
        logger.success(f"✅ Guardados {len(combined_df):,} registros")
    except Exception as e:
        logger.warning(f"Error al guardar: {e}")
        logger.info("Intentando por lotes...")

        # Insertar en lotes
        batch_size = 500
        saved = 0

        for start in range(0, len(combined_df), batch_size):
            batch = combined_df.iloc[start:start + batch_size]
            try:
                db.save_crypto_prices(batch)
                saved += len(batch)
                if start % 5000 == 0:
                    logger.info(f"   Guardados {saved:,}...")
            except Exception:
                # Ignorar duplicados
                pass

        logger.info(f"   Total guardados: {saved:,}")

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
    logger.info(f"   Tickers: {row['tickers']}")
    logger.info(f"   Rango: {row['earliest']} a {row['latest']}")
    logger.info(f"   Exitosos: {success_count}/{len(settings.TICKERS)}")

    if failed_tickers:
        logger.warning(f"   Fallidos: {', '.join(failed_tickers)}")

    logger.success("\n🎉 CARGA COMPLETADA")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Cargar datos históricos de Binance')
    parser.add_argument('--days', type=int, default=365, help='Días de historia (default: 365)')
    parser.add_argument('--force', action='store_true', help='Limpiar tabla antes de cargar')

    args = parser.parse_args()

    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

    success = run_initial_data_load(days=args.days, force=args.force)
    sys.exit(0 if success else 1)
