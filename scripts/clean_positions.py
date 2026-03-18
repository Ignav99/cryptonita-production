#!/usr/bin/env python3
"""
Clean positions table - keep only bot-opened positions
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.data.storage.db_manager import DatabaseManager
from loguru import logger

def clean_positions():
    """Remove positions that weren't opened by the bot"""
    db = DatabaseManager(settings.get_database_url())

    logger.info("🧹 Cleaning positions table...")

    # Get all positions
    positions = db.get_positions()
    logger.info(f"📊 Found {len(positions)} positions in DB")

    # Get all trades (bot-opened positions)
    trades = db.get_recent_trades(limit=1000)
    bot_tickers = set(trades[trades['action'] == 'BUY']['ticker'].unique())
    logger.info(f"🤖 Bot opened {len(bot_tickers)} positions: {bot_tickers}")

    # Delete positions that aren't in trades
    deleted = 0
    for _, pos in positions.iterrows():
        if pos['ticker'] not in bot_tickers:
            db.delete_position(pos['ticker'])
            deleted += 1
            logger.debug(f"  🗑️ Deleted {pos['ticker']}")

    logger.success(f"✅ Cleaned {deleted} positions, kept {len(bot_tickers)}")

if __name__ == "__main__":
    clean_positions()
