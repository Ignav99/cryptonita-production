#!/usr/bin/env python3
"""
Migration: Create model_artifacts and training_runs tables
for storing ML models in PostgreSQL (survives Render restarts).
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.data.storage.db_manager import DatabaseManager
from loguru import logger


def run_migration():
    db = DatabaseManager(settings.get_database_url())

    # Table 1: model_artifacts — stores serialized model blobs
    db.execute_command("""
        CREATE TABLE IF NOT EXISTS model_artifacts (
            id SERIAL PRIMARY KEY,
            version INTEGER NOT NULL,
            model_type VARCHAR(50) NOT NULL,
            artifact_data BYTEA,
            metadata JSONB DEFAULT '{}',
            training_metrics JSONB DEFAULT '{}',
            is_active BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Partial index: fast lookup for active model
    db.execute_command("""
        CREATE INDEX IF NOT EXISTS idx_model_artifacts_active
        ON model_artifacts(is_active) WHERE is_active = TRUE
    """)

    # Index for version ordering
    db.execute_command("""
        CREATE INDEX IF NOT EXISTS idx_model_artifacts_version
        ON model_artifacts(version DESC)
    """)

    logger.info("Created model_artifacts table")

    # Table 2: training_runs — history of training attempts
    db.execute_command("""
        CREATE TABLE IF NOT EXISTS training_runs (
            id SERIAL PRIMARY KEY,
            version INTEGER NOT NULL,
            status VARCHAR(20) DEFAULT 'running',
            mode VARCHAR(10) DEFAULT 'quick',
            started_at TIMESTAMPTZ DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            metrics JSONB DEFAULT '{}',
            comparison JSONB DEFAULT '{}',
            error_message TEXT,
            promoted BOOLEAN DEFAULT FALSE
        )
    """)

    logger.info("Created training_runs table")
    logger.success("Migration complete: model_artifacts + training_runs")

    db.close()


if __name__ == "__main__":
    run_migration()
