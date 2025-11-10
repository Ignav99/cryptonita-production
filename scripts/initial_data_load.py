#!/usr/bin/env python3
"""
CRYPTONITA MVP - INITIAL DATA LOAD
===================================
Ejecuta la carga inicial completa de datos.
"""

import sys
from pathlib import Path
from loguru import logger

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from data.ingestion.crypto_data import CryptoDataIngestion
from data.ingestion.macro_data import MacroDataIngestion


def run_initial_data_load():
    """Ejecuta carga inicial completa"""
    logger.info("🚀 INICIANDO CARGA INICIAL DE DATOS")
    
    results = {}

    # Crypto
    logger.info("\n📊 Paso 1/2: Criptomonedas...")
    try:
        crypto = CryptoDataIngestion()
        results['crypto'] = crypto.run_full_ingestion()
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        results['crypto'] = False

    # Macro
    logger.info("\n📊 Paso 2/2: Indicadores macro...")
    try:
        macro = MacroDataIngestion()
        macro_results = macro.run_full_ingestion()
        results['macro'] = all(macro_results.values())
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        results['macro'] = False

    # Resumen
    logger.info("\n" + "="*60)
    logger.info("RESUMEN")
    logger.info("="*60)
    logger.info(f"Crypto: {'✅' if results['crypto'] else '❌'}")
    logger.info(f"Macro: {'✅' if results['macro'] else '❌'}")
    
    if all(results.values()):
        logger.success("🎉 CARGA COMPLETADA")
        return True
    else:
        logger.error("❌ CARGA FALLÓ")
        return False


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    
    success = run_initial_data_load()
    sys.exit(0 if success else 1)
