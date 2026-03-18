#!/usr/bin/env python3
"""
Migration script to add missing columns to positions table
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from config import settings
from src.data.storage.db_manager import DatabaseManager
from sqlalchemy import text
from loguru import logger

def migrate_positions_table():
    """Add missing columns to positions table if they don't exist"""

    logger.info("🔧 Starting positions table migration...")

    try:
        db = DatabaseManager(settings.get_database_url())

        with db.engine.connect() as conn:
            # Check if columns exist and add them if missing
            migrations = [
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                 WHERE table_name='positions' AND column_name='total_value') THEN
                        ALTER TABLE positions ADD COLUMN total_value NUMERIC;
                        RAISE NOTICE 'Added total_value column';
                    END IF;
                END $$;
                """,
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                 WHERE table_name='positions' AND column_name='current_price') THEN
                        ALTER TABLE positions ADD COLUMN current_price NUMERIC;
                        RAISE NOTICE 'Added current_price column';
                    END IF;
                END $$;
                """,
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                 WHERE table_name='positions' AND column_name='pnl') THEN
                        ALTER TABLE positions ADD COLUMN pnl NUMERIC;
                        RAISE NOTICE 'Added pnl column';
                    END IF;
                END $$;
                """,
                """
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                 WHERE table_name='positions' AND column_name='pnl_percentage') THEN
                        ALTER TABLE positions ADD COLUMN pnl_percentage NUMERIC;
                        RAISE NOTICE 'Added pnl_percentage column';
                    END IF;
                END $$;
                """
            ]

            for migration_sql in migrations:
                conn.execute(text(migration_sql))
                conn.commit()

            logger.info("✅ Positions table migration completed successfully!")

            # Verify columns exist
            verify_sql = """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_name = 'positions'
            ORDER BY ordinal_position;
            """
            result = conn.execute(text(verify_sql))
            columns = [row[0] for row in result]

            logger.info(f"✅ Positions table columns: {', '.join(columns)}")

    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise

if __name__ == "__main__":
    migrate_positions_table()
