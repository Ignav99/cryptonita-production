#!/usr/bin/env python3
"""
Migration: Add probability column to trades table
This stores the model confidence when the trade was executed
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text, inspect
from config import settings
from src.data.storage.db_manager import DatabaseManager
from loguru import logger


def migrate():
    """Add probability column to trades table if it doesn't exist"""
    try:
        db = DatabaseManager(settings.get_database_url())

        # Check if column already exists
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('trades')]

        if 'probability' in columns:
            logger.info("✅ Column 'probability' already exists in trades table")
            return True

        logger.info("📊 Adding 'probability' column to trades table...")

        # Add the column
        query = """
        ALTER TABLE trades
        ADD COLUMN probability FLOAT DEFAULT NULL;
        """

        with db.engine.connect() as conn:
            conn.execute(text(query))
            conn.commit()

        logger.success("✅ Successfully added 'probability' column to trades table")
        return True

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    logger.info("=" * 60)
    logger.info("🔄 MIGRATION: Add probability to trades table")
    logger.info("=" * 60)

    success = migrate()

    if success:
        logger.success("✅ Migration completed successfully")
        sys.exit(0)
    else:
        logger.error("❌ Migration failed")
        sys.exit(1)
