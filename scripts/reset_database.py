#!/usr/bin/env python3
"""
Reset Database - Clean all data and start fresh
WARNING: This will delete ALL trades, signals, and positions!
"""

import sys
import argparse
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from config import settings
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_service import BinanceService
from loguru import logger


def reset_database(initial_capital: float = 10000.0):
    """
    Reset database - delete all data and initialize portfolio

    Args:
        initial_capital: Starting capital for the portfolio
    """
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

        logger.success("✅ Database tables cleared")

        # Initialize portfolio with specified capital
        logger.info(f"💰 Initializing portfolio with ${initial_capital:,.2f}...")
        db.initialize_portfolio(initial_capital)

        # Verify portfolio
        portfolio = db.get_portfolio()
        logger.success(f"✅ Portfolio initialized:")
        logger.info(f"  💵 Initial Capital: ${portfolio['initial_capital']:,.2f}")
        logger.info(f"  💵 Available Balance: ${portfolio['available_balance']:,.2f}")
        logger.info(f"  📊 Total Invested: ${portfolio['total_invested']:,.2f}")
        logger.info(f"  📈 Realized P&L: ${portfolio['realized_pnl']:,.2f}")

        # Note: We no longer check Binance balances here because:
        # 1. Binance testnet has many coins with initial balances (not our positions)
        # 2. Our portfolio is now managed internally, not from Binance
        # 3. The bot tracks its own positions in the 'positions' table
        logger.info("\n💡 Note: Portfolio is now managed internally, not from Binance testnet")

        logger.info("=" * 60)
        logger.success("✅ RESET COMPLETE - Ready to start fresh!")
        logger.info(f"💰 Starting capital: ${initial_capital:,.2f}")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"❌ Reset failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reset database and initialize portfolio")
    parser.add_argument("--confirm", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--capital", type=float, default=10000.0,
                        help="Initial capital for portfolio (default: 10000)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("🔄 DATABASE RESET SCRIPT")
    logger.info("=" * 60)

    # Confirmation
    print("\n⚠️  WARNING: This will DELETE ALL data from:")
    print("  - Trades")
    print("  - Positions")
    print("  - Signals")
    print("  - Bot status will be reset to 0")
    print(f"  - Portfolio will be reset to ${args.capital:,.2f}")
    print("\nThis action CANNOT be undone!\n")

    # In production, skip confirmation (assume user knows what they're doing)
    if args.confirm:
        logger.info("🚀 Confirmation flag detected, proceeding with reset...")
        success = reset_database(args.capital)
    else:
        response = input("Type 'RESET' to confirm: ")
        if response == "RESET":
            success = reset_database(args.capital)
        else:
            logger.info("❌ Reset cancelled")
            success = False

    sys.exit(0 if success else 1)
