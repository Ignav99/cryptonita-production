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
            # All columns that might be missing from the positions table
            columns_to_add = [
                ("total_value", "NUMERIC"),
                ("current_price", "NUMERIC"),
                ("pnl", "NUMERIC"),
                ("pnl_percentage", "NUMERIC"),
                ("remaining_quantity", "NUMERIC"),
                ("stop_loss", "NUMERIC"),
                ("tp1", "NUMERIC"),
                ("tp1_hit", "BOOLEAN DEFAULT FALSE"),
                ("tp1_size", "NUMERIC"),
                ("tp2", "NUMERIC"),
                ("tp2_hit", "BOOLEAN DEFAULT FALSE"),
                ("tp2_size", "NUMERIC"),
                ("tp3", "NUMERIC"),
                ("tp3_hit", "BOOLEAN DEFAULT FALSE"),
                ("tp3_size", "NUMERIC"),
                ("atr_pct", "NUMERIC"),
                ("trailing_stop_enabled", "BOOLEAN DEFAULT FALSE"),
                ("trailing_stop_active", "BOOLEAN DEFAULT FALSE"),
                ("oco_order_id", "VARCHAR(50)"),
                ("trade_id", "INTEGER"),
                ("entry_time", "TIMESTAMPTZ DEFAULT NOW()"),
                ("last_update", "TIMESTAMPTZ DEFAULT NOW()"),
            ]

            migrations = []
            for col_name, col_type in columns_to_add:
                migrations.append(f"""
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                                 WHERE table_name='positions' AND column_name='{col_name}') THEN
                        ALTER TABLE positions ADD COLUMN {col_name} {col_type};
                        RAISE NOTICE 'Added {col_name} column';
                    END IF;
                END $$;
                """)

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
