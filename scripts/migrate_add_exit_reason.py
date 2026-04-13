#!/usr/bin/env python3
"""
Migration: Add exit_reason column to trades table
Tracks why each SELL trade was executed (TP1_HIT, SL_HIT, ROTATION, TIME_EXIT, etc.)
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from config import settings
from src.data.storage.db_manager import DatabaseManager
from loguru import logger


def migrate():
    """Add exit_reason column to trades table if it doesn't exist"""
    try:
        db = DatabaseManager(settings.get_database_url())

        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('trades')]

        if 'exit_reason' in columns:
            logger.info("✅ Column 'exit_reason' already exists in trades table")
            return True

        logger.info("📊 Adding 'exit_reason' column to trades table...")

        query = """
        ALTER TABLE trades
        ADD COLUMN exit_reason VARCHAR(30) DEFAULT NULL;
        """

        with db.engine.connect() as conn:
            conn.execute(text(query))
            conn.commit()

        logger.success("✅ Successfully added 'exit_reason' column to trades table")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🔄 MIGRATION: Add exit_reason to trades table")
    logger.info("=" * 60)

    success = migrate()

    if success:
        logger.success("✅ Migration completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Migration failed")
        sys.exit(1)
