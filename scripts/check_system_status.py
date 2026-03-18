#!/usr/bin/env python3
"""
SYSTEM STATUS CHECK
===================
Verifica el estado completo del sistema antes de relanzar el bot.
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import asyncio
from datetime import datetime, timedelta
from loguru import logger

from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_service import BinanceService
from src.services.binance_data_service import BinanceDataService


def check_system_status():
    """Verifica el estado completo del sistema"""

    logger.info("=" * 70)
    logger.info("🔍 VERIFICACIÓN COMPLETA DEL SISTEMA")
    logger.info("=" * 70)

    db = DatabaseManager(settings.get_database_url())

    issues = []
    warnings = []

    # 1. DATABASE STATUS
    logger.info("\n" + "=" * 70)
    logger.info("1. DATABASE STATUS")
    logger.info("=" * 70)

    # Check tables
    tables = ['crypto_prices', 'signals', 'trades', 'positions', 'portfolio', 'bot_status']
    for table in tables:
        try:
            count = db.execute_query(f"SELECT COUNT(*) as cnt FROM {table}", {}).iloc[0]['cnt']
            logger.info(f"   ✅ {table}: {count:,} registros")
        except Exception as e:
            logger.error(f"   ❌ {table}: ERROR - {e}")
            issues.append(f"Tabla {table} no accesible")

    # Check crypto_prices date range
    try:
        result = db.execute_query("""
            SELECT MIN(timestamp) as earliest, MAX(timestamp) as latest,
                   COUNT(DISTINCT ticker) as tickers
            FROM crypto_prices
        """, {})
        row = result.iloc[0]
        logger.info(f"\n   📊 crypto_prices:")
        logger.info(f"      Rango: {row['earliest']} a {row['latest']}")
        logger.info(f"      Tickers: {row['tickers']}")

        # Check if BTCUSDT is present
        btc_check = db.execute_query(
            "SELECT COUNT(*) as cnt FROM crypto_prices WHERE ticker = 'BTCUSDT'", {}
        ).iloc[0]['cnt']
        if btc_check > 0:
            logger.info(f"      ✅ BTCUSDT presente: {btc_check} registros")
        else:
            logger.error(f"      ❌ BTCUSDT NO presente - necesario para features")
            issues.append("BTCUSDT no está en crypto_prices")
    except Exception as e:
        logger.error(f"   ❌ Error verificando crypto_prices: {e}")

    # 2. PORTFOLIO STATUS
    logger.info("\n" + "=" * 70)
    logger.info("2. PORTFOLIO STATUS")
    logger.info("=" * 70)

    try:
        portfolio = db.execute_query("SELECT * FROM portfolio WHERE id = 1", {})
        if len(portfolio) > 0:
            p = portfolio.iloc[0]
            logger.info(f"   💰 Capital inicial: ${float(p['initial_capital']):,.2f}")
            logger.info(f"   💵 Balance disponible: ${float(p['available_balance']):,.2f}")
            logger.info(f"   📈 Total invertido: ${float(p['total_invested']):,.2f}")
            logger.info(f"   📊 PnL realizado: ${float(p['realized_pnl']):,.2f}")
            total_value = float(p['available_balance']) + float(p['total_invested'])
            logger.info(f"   🏦 Valor total: ${total_value:,.2f}")
        else:
            logger.warning("   ⚠️ Portfolio no inicializado")
            warnings.append("Portfolio no inicializado")
    except Exception as e:
        logger.error(f"   ❌ Error verificando portfolio: {e}")
        issues.append("Portfolio table error")

    # 3. POSITIONS STATUS
    logger.info("\n" + "=" * 70)
    logger.info("3. POSITIONS STATUS (DB)")
    logger.info("=" * 70)

    try:
        positions = db.execute_query("""
            SELECT ticker, quantity, avg_buy_price, current_price, pnl, pnl_percentage
            FROM positions
            ORDER BY pnl_percentage DESC
        """, {})

        if len(positions) > 0:
            logger.info(f"   📊 Posiciones abiertas: {len(positions)}")
            total_invested = 0
            total_pnl = 0
            for _, pos in positions.iterrows():
                invested = float(pos['quantity']) * float(pos['avg_buy_price'])
                total_invested += invested
                pnl = float(pos['pnl']) if pos['pnl'] else 0
                total_pnl += pnl
                pnl_pct = float(pos['pnl_percentage']) if pos['pnl_percentage'] else 0
                logger.info(f"      {pos['ticker']:12s} | qty: {float(pos['quantity']):.4f} | "
                          f"entry: ${float(pos['avg_buy_price']):.4f} | "
                          f"pnl: {pnl_pct:+.2f}%")
            logger.info(f"\n   💰 Total invertido (DB): ${total_invested:,.2f}")
            logger.info(f"   📈 PnL no realizado: ${total_pnl:,.2f}")
        else:
            logger.info("   📭 No hay posiciones abiertas en DB")
    except Exception as e:
        logger.error(f"   ❌ Error verificando positions: {e}")

    # 4. BINANCE TESTNET STATUS
    logger.info("\n" + "=" * 70)
    logger.info("4. BINANCE TESTNET STATUS")
    logger.info("=" * 70)

    try:
        binance = BinanceService()

        # Test connectivity
        if binance.test_connectivity():
            logger.info("   ✅ Conexión a Binance Testnet: OK")
        else:
            logger.error("   ❌ Conexión a Binance Testnet: FAILED")
            issues.append("No hay conexión a Binance Testnet")

        # Get USDT balance
        usdt_balance = binance.get_usdt_balance()
        logger.info(f"   💵 USDT Balance (Testnet): ${usdt_balance:,.2f}")

        if usdt_balance < 100:
            logger.warning("   ⚠️ Balance bajo - considerar esperar reset mensual del testnet")
            warnings.append(f"Balance testnet bajo: ${usdt_balance:.2f}")

        # Count wallet assets (NOT positions - just informational)
        wallet_assets = binance.get_account_balance()
        non_zero_assets = len([a for a, b in wallet_assets.items() if b['total'] > 0])
        logger.info(f"   📦 Activos en wallet testnet: {non_zero_assets} (monedas de prueba, NO posiciones)")
        logger.info("   ℹ️  Nota: Las posiciones REALES del bot están en la tabla 'positions' de la BD")

    except Exception as e:
        logger.error(f"   ❌ Error conectando a Binance: {e}")
        issues.append(f"Error Binance: {e}")

    # 5. BINANCE PRODUCTION DATA
    logger.info("\n" + "=" * 70)
    logger.info("5. BINANCE PRODUCTION DATA (read-only)")
    logger.info("=" * 70)

    try:
        binance_data = BinanceDataService()

        # Test getting current price
        btc_price = binance_data.get_current_price('BTCUSDT')
        if btc_price:
            logger.info(f"   ✅ BTC Price (Production): ${btc_price:,.2f}")
        else:
            logger.warning("   ⚠️ No se pudo obtener precio de BTC")

        # Test getting historical data
        test_data = binance_data.get_historical_klines('BTCUSDT', '1d', 5)
        if len(test_data) > 0:
            logger.info(f"   ✅ Historical data access: OK ({len(test_data)} candles)")
        else:
            logger.error("   ❌ No se puede acceder a datos históricos")
            issues.append("No hay acceso a datos históricos de Binance")

    except Exception as e:
        logger.error(f"   ❌ Error con Binance Data Service: {e}")

    # 6. BOT STATUS
    logger.info("\n" + "=" * 70)
    logger.info("6. BOT STATUS")
    logger.info("=" * 70)

    try:
        bot_status = db.execute_query("SELECT * FROM bot_status WHERE id = 1", {})
        if len(bot_status) > 0:
            bs = bot_status.iloc[0]
            logger.info(f"   🤖 Status: {bs['status']}")
            logger.info(f"   🔄 Cycle: #{bs['cycle_number']}")
            logger.info(f"   📊 Total signals: {bs['total_signals']}")
            logger.info(f"   🟢 Buy signals: {bs['buy_signals']}")
            logger.info(f"   🕐 Last update: {bs['last_update']}")
            if bs['last_error']:
                logger.warning(f"   ⚠️ Last error: {bs['last_error']}")
        else:
            logger.warning("   ⚠️ Bot status no inicializado")
    except Exception as e:
        logger.error(f"   ❌ Error verificando bot status: {e}")

    # 7. RECENT SIGNALS
    logger.info("\n" + "=" * 70)
    logger.info("7. RECENT SIGNALS (last 24h)")
    logger.info("=" * 70)

    try:
        recent_signals = db.execute_query("""
            SELECT ticker, signal_type, probability, timestamp
            FROM signals
            WHERE timestamp > NOW() - INTERVAL '24 hours'
            ORDER BY timestamp DESC
            LIMIT 20
        """, {})

        if len(recent_signals) > 0:
            buy_signals = recent_signals[recent_signals['signal_type'] == 'BUY']
            logger.info(f"   📊 Signals últimas 24h: {len(recent_signals)}")
            logger.info(f"   🟢 BUY signals: {len(buy_signals)}")

            if len(buy_signals) > 0:
                logger.info("\n   Últimas señales BUY:")
                for _, sig in buy_signals.head(5).iterrows():
                    logger.info(f"      {sig['timestamp']} | {sig['ticker']:12s} | prob: {sig['probability']:.2f}")
        else:
            logger.info("   📭 No hay signals en las últimas 24h")
    except Exception as e:
        logger.error(f"   ❌ Error verificando signals: {e}")

    # 8. RECENT TRADES
    logger.info("\n" + "=" * 70)
    logger.info("8. RECENT TRADES (last 7 days)")
    logger.info("=" * 70)

    try:
        recent_trades = db.execute_query("""
            SELECT ticker, action, quantity, price, total_value, status, timestamp
            FROM trades
            WHERE timestamp > NOW() - INTERVAL '7 days'
            ORDER BY timestamp DESC
            LIMIT 10
        """, {})

        if len(recent_trades) > 0:
            logger.info(f"   📊 Trades últimos 7 días: {len(recent_trades)}")
            for _, trade in recent_trades.iterrows():
                emoji = "🟢" if trade['action'] == 'BUY' else "🔴"
                logger.info(f"      {emoji} {trade['timestamp']} | {trade['ticker']:12s} | "
                          f"{trade['action']} | ${float(trade['total_value']):.2f} | {trade['status']}")
        else:
            logger.info("   📭 No hay trades en los últimos 7 días")
    except Exception as e:
        logger.error(f"   ❌ Error verificando trades: {e}")

    # SUMMARY
    logger.info("\n" + "=" * 70)
    logger.info("📋 RESUMEN")
    logger.info("=" * 70)

    if issues:
        logger.error(f"\n❌ PROBLEMAS CRÍTICOS ({len(issues)}):")
        for issue in issues:
            logger.error(f"   - {issue}")
    else:
        logger.success("\n✅ No hay problemas críticos")

    if warnings:
        logger.warning(f"\n⚠️ ADVERTENCIAS ({len(warnings)}):")
        for warning in warnings:
            logger.warning(f"   - {warning}")

    if not issues:
        logger.success("\n🚀 SISTEMA LISTO PARA OPERAR")
        logger.info("   Puedes relanzar el bot con confianza")
    else:
        logger.error("\n🛑 RESOLVER PROBLEMAS ANTES DE RELANZAR")

    return len(issues) == 0


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO", format="{time:HH:mm:ss} | {level} | {message}")

    check_system_status()
