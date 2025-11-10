"""
DATABASE MANAGER
================
Handles all database operations for Cryptonita Production
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, date
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
import pandas as pd
from loguru import logger


class DatabaseManager:
    """
    Database manager for PostgreSQL operations
    """

    def __init__(self, database_url: str):
        """
        Initialize database connection

        Args:
            database_url: PostgreSQL connection string
        """
        self.database_url = database_url
        self.engine: Engine = self._create_engine()
        logger.info("✅ Database connection established")

    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine with connection pooling"""
        return create_engine(
            self.database_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using
            echo=False
        )

    # ============================================
    # CONNECTION MANAGEMENT
    # ============================================

    def test_connection(self) -> bool:
        """Test database connection"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.success("✅ Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            return False

    def close(self):
        """Close database connection"""
        self.engine.dispose()
        logger.info("🔌 Database connection closed")

    # ============================================
    # TABLE OPERATIONS
    # ============================================

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists"""
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

    def execute_command(self, query: str, params: Optional[Dict] = None) -> None:
        """
        Execute a SQL command (INSERT, UPDATE, DELETE)

        Args:
            query: SQL query string
            params: Query parameters
        """
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query), params or {})
                conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to execute command: {e}")
            raise

    def execute_query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """
        Execute a SELECT query and return results as DataFrame

        Args:
            query: SQL query string
            params: Query parameters

        Returns:
            DataFrame with results
        """
        try:
            with self.engine.connect() as conn:
                result = pd.read_sql(text(query), conn, params=params or {})
            return result
        except Exception as e:
            logger.error(f"❌ Failed to execute query: {e}")
            raise

    # ============================================
    # CRYPTO PRICES
    # ============================================

    def save_crypto_prices(self, df: pd.DataFrame) -> None:
        """
        Save crypto price data to database

        Args:
            df: DataFrame with columns [timestamp, ticker, open, high, low, close, volume]
        """
        try:
            df.to_sql(
                'crypto_prices',
                self.engine,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            logger.info(f"✅ Saved {len(df)} crypto price records")
        except Exception as e:
            logger.error(f"❌ Failed to save crypto prices: {e}")
            raise

    def get_latest_prices(self, ticker: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
        """
        Get latest crypto prices

        Args:
            ticker: Optional ticker filter
            limit: Number of records to return

        Returns:
            DataFrame with price data
        """
        query = """
        SELECT * FROM crypto_prices
        WHERE 1=1
        """
        params = {}

        if ticker:
            query += " AND ticker = :ticker"
            params['ticker'] = ticker

        query += " ORDER BY timestamp DESC LIMIT :limit"
        params['limit'] = limit

        return self.execute_query(query, params)

    def get_price_history(
        self,
        ticker: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> pd.DataFrame:
        """
        Get price history for a ticker

        Args:
            ticker: Crypto ticker
            start_date: Start date
            end_date: End date

        Returns:
            DataFrame with price history
        """
        query = "SELECT * FROM crypto_prices WHERE ticker = :ticker"
        params = {'ticker': ticker}

        if start_date:
            query += " AND timestamp >= :start_date"
            params['start_date'] = start_date

        if end_date:
            query += " AND timestamp <= :end_date"
            params['end_date'] = end_date

        query += " ORDER BY timestamp ASC"

        return self.execute_query(query, params)

    # ============================================
    # SIGNALS
    # ============================================

    def save_signal(
        self,
        ticker: str,
        signal_type: str,
        probability: float,
        features: Dict[str, Any]
    ) -> int:
        """
        Save a trading signal

        Args:
            ticker: Crypto ticker
            signal_type: BUY, SELL, or HOLD
            probability: Model prediction probability
            features: Feature values as dict

        Returns:
            Signal ID
        """
        query = """
        INSERT INTO signals (ticker, signal_type, probability, features, timestamp)
        VALUES (:ticker, :signal_type, :probability, :features, :timestamp)
        RETURNING id
        """
        params = {
            'ticker': ticker,
            'signal_type': signal_type,
            'probability': probability,
            'features': json.dumps(features),
            'timestamp': datetime.utcnow()
        }

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                signal_id = result.fetchone()[0]
                logger.debug(f"✅ Signal saved: {ticker} - {signal_type} (ID: {signal_id})")
                return signal_id
        except Exception as e:
            logger.error(f"❌ Failed to save signal: {e}")
            raise

    def get_recent_signals(self, limit: int = 50) -> pd.DataFrame:
        """Get recent signals"""
        query = """
        SELECT * FROM signals
        ORDER BY timestamp DESC
        LIMIT :limit
        """
        return self.execute_query(query, {'limit': limit})

    # ============================================
    # TRADES
    # ============================================

    def save_trade(
        self,
        signal_id: int,
        ticker: str,
        action: str,
        quantity: float,
        price: float,
        total_value: float,
        status: str = 'pending'
    ) -> int:
        """
        Save a trade execution

        Args:
            signal_id: Related signal ID
            ticker: Crypto ticker
            action: BUY or SELL
            quantity: Amount to trade
            price: Execution price
            total_value: Total USD value
            status: pending, executed, failed, or cancelled

        Returns:
            Trade ID
        """
        query = """
        INSERT INTO trades (signal_id, ticker, action, quantity, price, total_value, status, timestamp)
        VALUES (:signal_id, :ticker, :action, :quantity, :price, :total_value, :status, :timestamp)
        RETURNING id
        """
        params = {
            'signal_id': signal_id,
            'ticker': ticker,
            'action': action,
            'quantity': quantity,
            'price': price,
            'total_value': total_value,
            'status': status,
            'timestamp': datetime.utcnow()
        }

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                trade_id = result.fetchone()[0]
                logger.info(f"✅ Trade saved: {ticker} {action} (ID: {trade_id})")
                return trade_id
        except Exception as e:
            logger.error(f"❌ Failed to save trade: {e}")
            raise

    def get_recent_trades(self, limit: int = 50) -> pd.DataFrame:
        """Get recent trades"""
        query = """
        SELECT t.*, s.probability
        FROM trades t
        LEFT JOIN signals s ON t.signal_id = s.id
        ORDER BY t.timestamp DESC
        LIMIT :limit
        """
        return self.execute_query(query, {'limit': limit})

    def get_trades_by_status(self, status: str) -> pd.DataFrame:
        """Get trades by status"""
        query = """
        SELECT * FROM trades
        WHERE status = :status
        ORDER BY timestamp DESC
        """
        return self.execute_query(query, {'status': status})

    # ============================================
    # BOT STATUS
    # ============================================

    def update_bot_status(
        self,
        status: str,
        total_signals: int,
        buy_signals: int,
        cycle_number: int,
        last_error: Optional[str] = None
    ) -> None:
        """
        Update bot status

        Args:
            status: running, idle, error, or stopped
            total_signals: Total signals processed
            buy_signals: Number of buy signals
            cycle_number: Current cycle number
            last_error: Last error message if any
        """
        query = """
        UPDATE bot_status
        SET status = :status,
            total_signals = :total_signals,
            buy_signals = :buy_signals,
            cycle_number = :cycle_number,
            last_error = :last_error,
            last_update = :last_update
        WHERE id = 1
        """
        params = {
            'status': status,
            'total_signals': total_signals,
            'buy_signals': buy_signals,
            'cycle_number': cycle_number,
            'last_error': last_error,
            'last_update': datetime.utcnow()
        }
        self.execute_command(query, params)

    def get_bot_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        query = "SELECT * FROM bot_status WHERE id = 1"
        result = self.execute_query(query)
        if len(result) > 0:
            return result.iloc[0].to_dict()
        return {}

    # ============================================
    # POSITIONS
    # ============================================

    def get_positions(self) -> pd.DataFrame:
        """Get all current positions"""
        query = "SELECT * FROM positions ORDER BY total_value DESC"
        return self.execute_query(query)

    def get_position(self, ticker: str) -> Optional[Dict[str, Any]]:
        """Get position for specific ticker"""
        query = "SELECT * FROM positions WHERE ticker = :ticker"
        result = self.execute_query(query, {'ticker': ticker})
        if len(result) > 0:
            return result.iloc[0].to_dict()
        return None

    # ============================================
    # PERFORMANCE METRICS
    # ============================================

    def get_performance_metrics(
        self,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        limit: int = 30
    ) -> pd.DataFrame:
        """
        Get performance metrics

        Args:
            start_date: Start date
            end_date: End date
            limit: Number of records

        Returns:
            DataFrame with performance data
        """
        query = "SELECT * FROM performance_metrics WHERE 1=1"
        params = {'limit': limit}

        if start_date:
            query += " AND date >= :start_date"
            params['start_date'] = start_date

        if end_date:
            query += " AND date <= :end_date"
            params['end_date'] = end_date

        query += " ORDER BY date DESC LIMIT :limit"

        return self.execute_query(query, params)

    def get_latest_performance(self) -> Optional[Dict[str, Any]]:
        """Get latest performance metrics"""
        query = """
        SELECT * FROM performance_metrics
        ORDER BY date DESC
        LIMIT 1
        """
        result = self.execute_query(query)
        if len(result) > 0:
            return result.iloc[0].to_dict()
        return None

    # ============================================
    # STATISTICS
    # ============================================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """
        Get aggregated statistics for dashboard

        Returns:
            Dictionary with dashboard stats
        """
        try:
            # Total trades
            total_trades_query = "SELECT COUNT(*) as count FROM trades"
            total_trades = self.execute_query(total_trades_query).iloc[0]['count']

            # Executed trades
            executed_query = "SELECT COUNT(*) as count FROM trades WHERE status = 'executed'"
            executed_trades = self.execute_query(executed_query).iloc[0]['count']

            # Active positions
            positions_query = "SELECT COUNT(*) as count FROM positions"
            active_positions = self.execute_query(positions_query).iloc[0]['count']

            # Total portfolio value
            portfolio_query = "SELECT COALESCE(SUM(total_value), 0) as total FROM positions"
            portfolio_value = float(self.execute_query(portfolio_query).iloc[0]['total'])

            # Total P&L
            pnl_query = "SELECT COALESCE(SUM(pnl), 0) as total FROM positions"
            total_pnl = float(self.execute_query(pnl_query).iloc[0]['total'])

            # Win rate (from executed trades)
            win_rate_query = """
            SELECT
                COUNT(CASE WHEN pnl > 0 THEN 1 END)::float / NULLIF(COUNT(*), 0) as win_rate
            FROM positions
            """
            win_rate_result = self.execute_query(win_rate_query)
            win_rate = float(win_rate_result.iloc[0]['win_rate']) if len(win_rate_result) > 0 else 0.0

            return {
                'total_trades': int(total_trades),
                'executed_trades': int(executed_trades),
                'active_positions': int(active_positions),
                'portfolio_value': round(portfolio_value, 2),
                'total_pnl': round(total_pnl, 2),
                'win_rate': round(win_rate * 100, 2) if win_rate else 0.0,
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Failed to get dashboard stats: {e}")
            return {
                'total_trades': 0,
                'executed_trades': 0,
                'active_positions': 0,
                'portfolio_value': 0.0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'timestamp': datetime.utcnow().isoformat()
            }
