#!/usr/bin/env python3
"""
CRYPTONITA MVP - DATABASE SETUP
================================
Crea el esquema de base de datos.
"""

import sys
from pathlib import Path
from loguru import logger
from sqlalchemy import text

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from src.data.storage.db_manager import DatabaseManager

CREATE_TABLES_SQL = """
-- Crypto prices table (existing)
CREATE TABLE IF NOT EXISTS crypto_prices (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    ticker VARCHAR(20) NOT NULL,
    open NUMERIC NOT NULL,
    high NUMERIC NOT NULL,
    low NUMERIC NOT NULL,
    close NUMERIC NOT NULL,
    volume BIGINT NOT NULL,
    UNIQUE(timestamp, ticker)
);

CREATE INDEX IF NOT EXISTS idx_crypto_prices_ticker_timestamp
ON crypto_prices(ticker, timestamp DESC);

-- Trading signals table
CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL,
    signal_type VARCHAR(10) NOT NULL,
    probability NUMERIC NOT NULL,
    features TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT check_signal_type CHECK (signal_type IN ('BUY', 'SELL', 'HOLD'))
);

CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signals_ticker ON signals(ticker);

-- Trades execution table
CREATE TABLE IF NOT EXISTS trades (
    id SERIAL PRIMARY KEY,
    signal_id INTEGER REFERENCES signals(id),
    ticker VARCHAR(20) NOT NULL,
    action VARCHAR(10) NOT NULL,
    quantity NUMERIC NOT NULL,
    price NUMERIC NOT NULL,
    total_value NUMERIC NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    executed_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT check_action CHECK (action IN ('BUY', 'SELL')),
    CONSTRAINT check_status CHECK (status IN ('pending', 'executed', 'failed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trades_ticker ON trades(ticker);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);

-- Bot status table (singleton - only one row)
CREATE TABLE IF NOT EXISTS bot_status (
    id INTEGER PRIMARY KEY DEFAULT 1,
    status VARCHAR(20) NOT NULL DEFAULT 'idle',
    total_signals INTEGER DEFAULT 0,
    buy_signals INTEGER DEFAULT 0,
    cycle_number INTEGER DEFAULT 0,
    last_error TEXT,
    last_update TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT check_singleton CHECK (id = 1),
    CONSTRAINT check_bot_status CHECK (status IN ('running', 'idle', 'error', 'stopped'))
);

-- Insert initial bot status
INSERT INTO bot_status (id, status, total_signals, buy_signals, cycle_number, last_update)
VALUES (1, 'idle', 0, 0, 0, NOW())
ON CONFLICT (id) DO NOTHING;

-- Portfolio positions table
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(20) NOT NULL UNIQUE,
    quantity NUMERIC NOT NULL,
    avg_buy_price NUMERIC NOT NULL,
    current_price NUMERIC,
    total_value NUMERIC,
    pnl NUMERIC,
    pnl_percentage NUMERIC,
    last_update TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_positions_ticker ON positions(ticker);

-- Performance metrics table (daily snapshots)
CREATE TABLE IF NOT EXISTS performance_metrics (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL UNIQUE,
    total_trades INTEGER DEFAULT 0,
    successful_trades INTEGER DEFAULT 0,
    failed_trades INTEGER DEFAULT 0,
    total_volume NUMERIC DEFAULT 0,
    total_pnl NUMERIC DEFAULT 0,
    win_rate NUMERIC DEFAULT 0,
    sharpe_ratio NUMERIC,
    max_drawdown NUMERIC,
    portfolio_value NUMERIC DEFAULT 0,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_performance_date ON performance_metrics(date DESC);
"""


def create_database_schema():
    """Crea el esquema completo"""
    logger.info("🚀 Iniciando setup de base de datos...")

    try:
        # Get database connection string from settings
        db_url = settings.get_database_url()
        db = DatabaseManager(db_url)

        with db.engine.connect() as conn:
            conn.execute(text(CREATE_TABLES_SQL))
            conn.commit()

        logger.success("✅ Tablas creadas exitosamente")

        # Verify all tables
        tables = ['crypto_prices', 'signals', 'trades', 'bot_status', 'positions', 'performance_metrics']
        for table in tables:
            if db.table_exists(table):
                logger.success(f"✅ {table} - OK")
            else:
                logger.warning(f"⚠️ {table} - NOT FOUND")

        return True

    except Exception as e:
        logger.error(f"❌ Error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False


if __name__ == "__main__":
    logger.remove()
    logger.add(sys.stdout, level="INFO")
    
    success = create_database_schema()
    sys.exit(0 if success else 1)
