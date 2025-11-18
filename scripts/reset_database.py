#!/usr/bin/env python3
"""
Reset Database - Clean all data and start fresh
WARNING: This will delete ALL trades, signals, and positions!
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_service import BinanceService
from loguru import logger


def reset_database():
    """Reset database - delete all data"""
    try:
        db = DatabaseManager(settings.get_database_url())

        logger.warning("⚠️  WARNING: This will delete ALL data from the database!")
        logger.info("🗑️  Starting database reset...")

        # Delete all data from tables
        with db.engine.connect() as conn:
            # Delete in order to avoid foreign key constraints
            logger.info("  - Deleting trades...")
            conn.execute(text("DELETE FROM trades"))

            logger.info("  - Deleting positions...")
            conn.execute(text("DELETE FROM positions"))

            logger.info("  - Deleting signals...")
            conn.execute(text("DELETE FROM signals"))

            logger.info("  - Resetting bot status...")
            conn.execute(text("""
                UPDATE bot_status
                SET cycle_number = 0,
                    total_signals = 0,
                    buy_signals = 0,
                    status = 'stopped',
                    last_error = NULL,
                    last_update = NOW()
            """))

            conn.commit()

        logger.success("✅ Database reset completed")

        # Show remaining balances
        logger.info("💰 Checking Binance Testnet balance...")
        binance = BinanceService()
        usdt_balance = binance.get_usdt_balance()
        logger.info(f"  💵 Available USDT: ${usdt_balance:,.2f}")

        # Get all open positions
        positions = binance.get_all_positions()
        if len(positions) > 0:
            logger.warning(f"  ⚠️  You still have {len(positions)} open positions in Binance")
            logger.warning(f"  ⚠️  Close them manually or they will be re-synced")
            for pos in positions[:5]:  # Show first 5
                logger.info(f"    - {pos['ticker']}: {pos['quantity']} @ ${pos['current_price']}")
        else:
            logger.success("  ✅ No open positions in Binance")

        logger.info("=" * 60)
        logger.success("✅ RESET COMPLETE - Ready to start fresh!")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"❌ Reset failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🔄 DATABASE RESET SCRIPT")
    logger.info("=" * 60)

    # Confirmation
    print("\n⚠️  WARNING: This will DELETE ALL data from:")
    print("  - Trades")
    print("  - Positions")
    print("  - Signals")
    print("  - Bot status will be reset to 0")
    print("\nThis action CANNOT be undone!\n")

    # In production, skip confirmation (assume user knows what they're doing)
    if len(sys.argv) > 1 and sys.argv[1] == "--confirm":
        logger.info("🚀 Confirmation flag detected, proceeding with reset...")
        success = reset_database()
    else:
        response = input("Type 'RESET' to confirm: ")
        if response == "RESET":
            success = reset_database()
        else:
            logger.info("❌ Reset cancelled")
            success = False

    sys.exit(0 if success else 1)
