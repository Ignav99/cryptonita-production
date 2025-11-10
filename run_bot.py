#!/usr/bin/env python3
"""
CRYPTONITA TRADING BOT - LAUNCHER
==================================
Launch the trading bot with proper logging and error handling
"""

import sys
import asyncio
from pathlib import Path
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.bot.trading_bot import TradingBot


def setup_logging():
    """Configure logging"""
    logger.remove()

    # Console logging
    logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO",
        colorize=True
    )

    # File logging
    log_file = Path(settings.LOG_FILE)
    log_file.parent.mkdir(exist_ok=True)

    logger.add(
        settings.LOG_FILE,
        rotation="1 day",
        retention="30 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
    )

    logger.info("📝 Logging configured")


async def main():
    """Main entry point"""
    # Setup logging
    setup_logging()

    logger.info("=" * 70)
    logger.info("🤖 CRYPTONITA TRADING BOT V3")
    logger.info("=" * 70)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Trading Mode: {settings.TRADING_MODE.upper()}")
    logger.info(f"Model Version: {settings.MODEL_VERSION}")
    logger.info("=" * 70)

    try:
        # Create bot instance
        bot = TradingBot(config_path="bot_config.json")

        # Start bot
        await bot.start()

    except KeyboardInterrupt:
        logger.info("\n⏸️ Bot stopped by user (Ctrl+C)")
    except Exception as e:
        logger.error(f"❌ Fatal error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
