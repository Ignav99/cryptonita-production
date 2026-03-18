"""
DATABASE MANAGER
================
Handles all database operations for Cryptonita Production
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool
import pandas as pd
from loguru import logger


def _utcnow() -> datetime:
    """Return timezone-aware UTC datetime"""
    return datetime.now(timezone.utc)


class DatabaseManager:
    """
    Database manager for PostgreSQL operations.
    Centralizes ALL database CRUD operations.
    """

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine: Engine = self._create_engine()
        logger.info("Database connection established")

    def _create_engine(self) -> Engine:
        """Create SQLAlchemy engine with connection pooling"""
        return create_engine(
            self.database_url,
            poolclass=QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
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
            logger.success("Database connection test successful")
            return True
        except Exception as e:
            logger.error(f"Database connection failed: {e}")
            return False

    def close(self):
        """Close database connection"""
        self.engine.dispose()
        logger.info("Database connection closed")

    # ============================================
    # GENERIC OPERATIONS
    # ============================================

    def table_exists(self, table_name: str) -> bool:
        """Check if a table exists"""
        inspector = inspect(self.engine)
        return table_name in inspector.get_table_names()

    def execute_command(self, query: str, params: Optional[Dict] = None) -> None:
        """Execute a SQL command (INSERT, UPDATE, DELETE)"""
        try:
            with self.engine.connect() as conn:
                conn.execute(text(query), params or {})
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to execute command: {e}")
            raise

    def execute_query(self, query: str, params: Optional[Dict] = None) -> pd.DataFrame:
        """Execute a SELECT query and return results as DataFrame"""
        try:
            with self.engine.connect() as conn:
                result = pd.read_sql(text(query), conn, params=params or {})
            return result
        except Exception as e:
            logger.error(f"Failed to execute query: {e}")
            raise

    # ============================================
    # CRYPTO PRICES
    # ============================================

    def save_crypto_prices(self, df: pd.DataFrame) -> None:
        """Save crypto price data to database"""
        try:
            df.to_sql(
                'crypto_prices',
                self.engine,
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            logger.info(f"Saved {len(df)} crypto price records")
        except Exception as e:
            logger.error(f"Failed to save crypto prices: {e}")
            raise

    def get_latest_prices(self, ticker: Optional[str] = None, limit: int = 100) -> pd.DataFrame:
        """Get latest crypto prices"""
        query = "SELECT * FROM crypto_prices WHERE 1=1"
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
        """Get price history for a ticker"""
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
        """Save a trading signal. Returns Signal ID."""
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
            'timestamp': _utcnow()
        }

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                signal_id = result.fetchone()[0]
                logger.debug(f"Signal saved: {ticker} - {signal_type} (ID: {signal_id})")
                return signal_id
        except Exception as e:
            logger.error(f"Failed to save signal: {e}")
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
        status: str = 'pending',
        pnl: Optional[float] = None
    ) -> int:
        """Save a trade execution. Returns Trade ID."""
        query = """
        INSERT INTO trades (signal_id, ticker, action, quantity, price, total_value, status, pnl, timestamp, executed_at)
        VALUES (:signal_id, :ticker, :action, :quantity, :price, :total_value, :status, :pnl, :timestamp, :executed_at)
        RETURNING id
        """
        now = _utcnow()
        params = {
            'signal_id': signal_id if signal_id else None,
            'ticker': ticker,
            'action': action,
            'quantity': quantity,
            'price': price,
            'total_value': total_value,
            'status': status,
            'pnl': pnl,
            'timestamp': now,
            'executed_at': now if status == 'executed' else None
        }

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                trade_id = result.fetchone()[0]
                logger.info(f"Trade saved: {ticker} {action} (ID: {trade_id})")
                return trade_id
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")
            raise

    def update_trade_status(self, trade_id: int, status: str, pnl: Optional[float] = None, error_message: Optional[str] = None) -> None:
        """Update trade status after execution"""
        query = """
        UPDATE trades
        SET status = :status,
            pnl = COALESCE(:pnl, pnl),
            executed_at = CASE WHEN :status = 'executed' THEN :now ELSE executed_at END,
            error_message = :error_message
        WHERE id = :trade_id
        """
        self.execute_command(query, {
            'trade_id': trade_id,
            'status': status,
            'pnl': pnl,
            'error_message': error_message,
            'now': _utcnow()
        })

    def get_recent_trades(self, limit: int = 50) -> pd.DataFrame:
        """Get recent trades with signal probability"""
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
        """Update bot status (singleton row)"""
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
        self.execute_command(query, {
            'status': status,
            'total_signals': total_signals,
            'buy_signals': buy_signals,
            'cycle_number': cycle_number,
            'last_error': last_error,
            'last_update': _utcnow()
        })

    def get_bot_status(self) -> Dict[str, Any]:
        """Get current bot status"""
        query = "SELECT * FROM bot_status WHERE id = 1"
        result = self.execute_query(query)
        if len(result) > 0:
            return result.iloc[0].to_dict()
        return {}

    # ============================================
    # POSITIONS (full CRUD)
    # ============================================

    def save_position(self, position_data: Dict[str, Any]) -> None:
        """Insert a new position into the database"""
        query = """
        INSERT INTO positions (
            ticker, quantity, remaining_quantity, avg_buy_price,
            current_price, total_value, pnl, pnl_percentage,
            stop_loss, tp1, tp1_hit, tp1_size, tp2, tp2_hit, tp2_size,
            tp3, tp3_hit, tp3_size, atr_pct,
            trailing_stop_enabled, trailing_stop_active,
            oco_order_id, trade_id, entry_time, last_update
        ) VALUES (
            :ticker, :quantity, :remaining_quantity, :avg_buy_price,
            :current_price, :total_value, :pnl, :pnl_percentage,
            :stop_loss, :tp1, :tp1_hit, :tp1_size, :tp2, :tp2_hit, :tp2_size,
            :tp3, :tp3_hit, :tp3_size, :atr_pct,
            :trailing_stop_enabled, :trailing_stop_active,
            :oco_order_id, :trade_id, :entry_time, :last_update
        )
        ON CONFLICT (ticker) DO UPDATE SET
            quantity = EXCLUDED.quantity,
            remaining_quantity = EXCLUDED.remaining_quantity,
            avg_buy_price = EXCLUDED.avg_buy_price,
            current_price = EXCLUDED.current_price,
            total_value = EXCLUDED.total_value,
            pnl = EXCLUDED.pnl,
            pnl_percentage = EXCLUDED.pnl_percentage,
            stop_loss = EXCLUDED.stop_loss,
            tp1 = EXCLUDED.tp1, tp1_hit = EXCLUDED.tp1_hit, tp1_size = EXCLUDED.tp1_size,
            tp2 = EXCLUDED.tp2, tp2_hit = EXCLUDED.tp2_hit, tp2_size = EXCLUDED.tp2_size,
            tp3 = EXCLUDED.tp3, tp3_hit = EXCLUDED.tp3_hit, tp3_size = EXCLUDED.tp3_size,
            atr_pct = EXCLUDED.atr_pct,
            trailing_stop_enabled = EXCLUDED.trailing_stop_enabled,
            trailing_stop_active = EXCLUDED.trailing_stop_active,
            oco_order_id = EXCLUDED.oco_order_id,
            trade_id = EXCLUDED.trade_id,
            last_update = EXCLUDED.last_update
        """
        now = _utcnow()
        params = {
            'ticker': position_data['ticker'],
            'quantity': position_data['quantity'],
            'remaining_quantity': position_data.get('remaining_quantity', position_data['quantity']),
            'avg_buy_price': position_data['avg_buy_price'],
            'current_price': position_data.get('current_price', position_data['avg_buy_price']),
            'total_value': position_data.get('total_value', 0),
            'pnl': position_data.get('pnl', 0),
            'pnl_percentage': position_data.get('pnl_percentage', 0),
            'stop_loss': position_data.get('stop_loss'),
            'tp1': position_data.get('tp1'),
            'tp1_hit': position_data.get('tp1_hit', False),
            'tp1_size': position_data.get('tp1_size'),
            'tp2': position_data.get('tp2'),
            'tp2_hit': position_data.get('tp2_hit', False),
            'tp2_size': position_data.get('tp2_size'),
            'tp3': position_data.get('tp3'),
            'tp3_hit': position_data.get('tp3_hit', False),
            'tp3_size': position_data.get('tp3_size'),
            'atr_pct': position_data.get('atr_pct'),
            'trailing_stop_enabled': position_data.get('trailing_stop_enabled', False),
            'trailing_stop_active': position_data.get('trailing_stop_active', False),
            'oco_order_id': position_data.get('oco_order_id'),
            'trade_id': position_data.get('trade_id'),
            'entry_time': position_data.get('entry_time', now),
            'last_update': now
        }
        self.execute_command(query, params)
        logger.info(f"Position saved: {position_data['ticker']}")

    def update_position(self, ticker: str, updates: Dict[str, Any]) -> None:
        """Update specific fields of an existing position"""
        if not updates:
            return

        set_clauses = []
        params = {'ticker': ticker}

        for key, value in updates.items():
            set_clauses.append(f"{key} = :{key}")
            params[key] = value

        params['last_update'] = _utcnow()
        set_clauses.append("last_update = :last_update")

        query = f"UPDATE positions SET {', '.join(set_clauses)} WHERE ticker = :ticker"
        self.execute_command(query, params)

    def delete_position(self, ticker: str) -> None:
        """Delete a position (when fully closed)"""
        self.execute_command(
            "DELETE FROM positions WHERE ticker = :ticker",
            {'ticker': ticker}
        )
        logger.info(f"Position deleted: {ticker}")

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

    def get_all_positions_as_dict(self) -> Dict[str, Dict[str, Any]]:
        """Load all positions as a dict keyed by ticker (for bot recovery)"""
        df = self.get_positions()
        positions = {}
        for _, row in df.iterrows():
            data = row.to_dict()
            ticker = data['ticker']
            positions[ticker] = {
                'quantity': float(data['quantity']),
                'remaining_quantity': float(data['remaining_quantity']),
                'entry_price': float(data['avg_buy_price']),
                'current_price': float(data['current_price']) if data['current_price'] else float(data['avg_buy_price']),
                'stop_loss': float(data['stop_loss']) if data['stop_loss'] else None,
                'tp1': float(data['tp1']) if data['tp1'] else None,
                'tp1_hit': bool(data['tp1_hit']),
                'tp1_size': float(data['tp1_size']) if data['tp1_size'] else 0.3,
                'tp2': float(data['tp2']) if data['tp2'] else None,
                'tp2_hit': bool(data['tp2_hit']),
                'tp2_size': float(data['tp2_size']) if data['tp2_size'] else 0.4,
                'tp3': float(data['tp3']) if data['tp3'] else None,
                'tp3_hit': bool(data['tp3_hit']),
                'tp3_size': float(data['tp3_size']) if data['tp3_size'] else 0.3,
                'atr_pct': float(data['atr_pct']) if data['atr_pct'] else 0.03,
                'trailing_stop_enabled': bool(data['trailing_stop_enabled']),
                'trailing_stop_active': bool(data['trailing_stop_active']),
                'oco_order_id': data.get('oco_order_id'),
                'trade_id': data.get('trade_id'),
                'entry_time': data['entry_time'],
                'entry_features': {},
            }
        return positions

    # ============================================
    # PERFORMANCE METRICS
    # ============================================

    def save_performance_metrics(self, metrics: Dict[str, Any]) -> None:
        """Save or update daily performance metrics"""
        query = """
        INSERT INTO performance_metrics (
            date, total_trades, successful_trades, failed_trades,
            total_volume, total_pnl, win_rate, sharpe_ratio,
            max_drawdown, portfolio_value, timestamp
        ) VALUES (
            :date, :total_trades, :successful_trades, :failed_trades,
            :total_volume, :total_pnl, :win_rate, :sharpe_ratio,
            :max_drawdown, :portfolio_value, :timestamp
        )
        ON CONFLICT (date) DO UPDATE SET
            total_trades = EXCLUDED.total_trades,
            successful_trades = EXCLUDED.successful_trades,
            failed_trades = EXCLUDED.failed_trades,
            total_volume = EXCLUDED.total_volume,
            total_pnl = EXCLUDED.total_pnl,
            win_rate = EXCLUDED.win_rate,
            sharpe_ratio = EXCLUDED.sharpe_ratio,
            max_drawdown = EXCLUDED.max_drawdown,
            portfolio_value = EXCLUDED.portfolio_value,
            timestamp = EXCLUDED.timestamp
        """
        self.execute_command(query, {
            'date': metrics.get('date', _utcnow().date()),
            'total_trades': metrics.get('total_trades', 0),
            'successful_trades': metrics.get('successful_trades', 0),
            'failed_trades': metrics.get('failed_trades', 0),
            'total_volume': metrics.get('total_volume', 0),
            'total_pnl': metrics.get('total_pnl', 0),
            'win_rate': metrics.get('win_rate', 0),
            'sharpe_ratio': metrics.get('sharpe_ratio'),
            'max_drawdown': metrics.get('max_drawdown'),
            'portfolio_value': metrics.get('portfolio_value', 0),
            'timestamp': _utcnow()
        })

    def get_performance_metrics(
        self,
        start_date=None,
        end_date=None,
        limit: int = 30
    ) -> pd.DataFrame:
        """Get performance metrics"""
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
        query = "SELECT * FROM performance_metrics ORDER BY date DESC LIMIT 1"
        result = self.execute_query(query)
        if len(result) > 0:
            return result.iloc[0].to_dict()
        return None

    # ============================================
    # STATISTICS (optimized)
    # ============================================

    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get aggregated statistics for dashboard (optimized: 2 queries instead of 6)"""
        try:
            # Query 1: Trade stats (including win rate from SELL trades with pnl)
            trade_stats_query = """
            SELECT
                COUNT(*) as total_trades,
                COUNT(*) FILTER (WHERE status = 'executed') as executed_trades,
                COUNT(*) FILTER (WHERE action = 'SELL' AND pnl > 0) as winning_trades,
                COUNT(*) FILTER (WHERE action = 'SELL' AND pnl IS NOT NULL) as closed_trades,
                COALESCE(SUM(pnl) FILTER (WHERE action = 'SELL'), 0) as realized_pnl
            FROM trades
            """
            trade_stats = self.execute_query(trade_stats_query)
            ts = trade_stats.iloc[0]

            # Query 2: Position stats
            position_stats_query = """
            SELECT
                COUNT(*) as active_positions,
                COALESCE(SUM(total_value), 0) as portfolio_value,
                COALESCE(SUM(pnl), 0) as unrealized_pnl
            FROM positions
            """
            pos_stats = self.execute_query(position_stats_query)
            ps = pos_stats.iloc[0]

            closed_trades = int(ts['closed_trades'])
            winning_trades = int(ts['winning_trades'])
            win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0.0

            total_pnl = float(ts['realized_pnl']) + float(ps['unrealized_pnl'])

            return {
                'total_trades': int(ts['total_trades']),
                'executed_trades': int(ts['executed_trades']),
                'active_positions': int(ps['active_positions']),
                'portfolio_value': round(float(ps['portfolio_value']), 2),
                'total_pnl': round(total_pnl, 2),
                'winning_trades': winning_trades,
                'closed_trades': closed_trades,
                'win_rate': round(win_rate, 2),
                'timestamp': _utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"Failed to get dashboard stats: {e}")
            return {
                'total_trades': 0,
                'executed_trades': 0,
                'active_positions': 0,
                'portfolio_value': 0.0,
                'total_pnl': 0.0,
                'winning_trades': 0,
                'closed_trades': 0,
                'win_rate': 0.0,
                'timestamp': _utcnow().isoformat()
            }
