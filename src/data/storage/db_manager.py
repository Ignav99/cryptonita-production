"""
DATABASE MANAGER
================
Handles all database operations for Cryptonita Production
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime, date, timedelta
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
                result_proxy = conn.execute(text(query), params or {})
                rows = result_proxy.fetchall()
                columns = result_proxy.keys()
                result = pd.DataFrame(rows, columns=columns)
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

    def get_recent_signals(self, limit: int = 50, min_probability: float = 0.60, days: int = 7) -> pd.DataFrame:
        """
        Get recent signals filtered by probability and time

        Args:
            limit: Maximum number of signals to return
            min_probability: Minimum probability threshold (default 60%)
            days: Number of days to look back (default 7)

        Returns:
            DataFrame with filtered signals
        """
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = """
        SELECT * FROM signals
        WHERE probability >= :min_probability
          AND timestamp >= :cutoff
        ORDER BY probability DESC, timestamp DESC
        LIMIT :limit
        """
        return self.execute_query(query, {
            'limit': limit,
            'min_probability': min_probability,
            'cutoff': cutoff
        })

    def get_all_latest_signals(self) -> pd.DataFrame:
        """Get the latest signal per ticker (DISTINCT ON)"""
        query = """
        SELECT DISTINCT ON (ticker) id, ticker, signal_type, probability, timestamp
        FROM signals
        ORDER BY ticker, timestamp DESC
        """
        return self.execute_query(query)

    def get_signal_history(self, days: int = 14) -> pd.DataFrame:
        """Get all signals for the last N days for trend analysis"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = """
        SELECT id, ticker, signal_type, probability, timestamp
        FROM signals
        WHERE timestamp >= :cutoff
        ORDER BY timestamp ASC
        """
        return self.execute_query(query, {'cutoff': cutoff})

    def get_signals_stats(self, days: int = 7) -> pd.DataFrame:
        """Get signal counts per ticker for the last N days"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        query = """
        SELECT
            ticker,
            COUNT(*) as total_count,
            COUNT(*) FILTER (WHERE signal_type = 'BUY') as buy_count,
            COUNT(*) FILTER (WHERE signal_type = 'HOLD') as hold_count
        FROM signals
        WHERE timestamp >= :cutoff
        GROUP BY ticker
        ORDER BY total_count DESC
        """
        return self.execute_query(query, {'cutoff': cutoff})

    # ============================================
    # TRADES
    # ============================================

    def save_trade(
        self,
        signal_id: Optional[int],
        ticker: str,
        action: str,
        quantity: float,
        price: float,
        total_value: float,
        status: str = 'pending',
        probability: Optional[float] = None
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
            probability: Model confidence when trade was executed

        Returns:
            Trade ID
        """
        query = """
        INSERT INTO trades (signal_id, ticker, action, quantity, price, total_value, status, probability, timestamp)
        VALUES (:signal_id, :ticker, :action, :quantity, :price, :total_value, :status, :probability, :timestamp)
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
            'probability': probability,
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
        """Get recent trades with probability"""
        query = """
        SELECT *
        FROM trades
        ORDER BY timestamp DESC
        LIMIT :limit
        """
        return self.execute_query(query, {'limit': limit})

    def get_closed_positions(self, limit: int = 50) -> pd.DataFrame:
        """
        Get closed positions (matched BUY/SELL pairs) with P&L

        Returns DataFrame with:
        - ticker, entry_price, exit_price, quantity
        - entry_time, exit_time
        - pnl, pnl_percentage
        - probability (model confidence at entry)
        """
        query = """
        WITH buy_trades AS (
            SELECT
                id,
                ticker,
                price as entry_price,
                quantity,
                timestamp as entry_time,
                probability
            FROM trades
            WHERE action = 'BUY' AND status = 'executed'
        ),
        sell_trades AS (
            SELECT
                ticker,
                price as exit_price,
                quantity as sell_quantity,
                timestamp as exit_time,
                ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
            FROM trades
            WHERE action = 'SELL' AND status = 'executed'
        ),
        matched_trades AS (
            SELECT
                b.ticker,
                b.entry_price,
                s.exit_price,
                LEAST(b.quantity, s.sell_quantity) as quantity,
                b.entry_time,
                s.exit_time,
                b.probability,
                (s.exit_price - b.entry_price) * LEAST(b.quantity, s.sell_quantity) as pnl,
                ((s.exit_price - b.entry_price) / b.entry_price) * 100 as pnl_percentage
            FROM buy_trades b
            INNER JOIN sell_trades s ON b.ticker = s.ticker
            ORDER BY s.exit_time DESC
            LIMIT :limit
        )
        SELECT * FROM matched_trades
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

    def upsert_position(
        self,
        ticker: str,
        quantity: float,
        avg_buy_price: float,
        current_price: float,
        remaining_quantity: float = None,
        stop_loss: float = None,
        tp1: float = None,
        tp1_hit: bool = False,
        tp1_size: float = None,
        tp2: float = None,
        tp2_hit: bool = False,
        tp2_size: float = None,
        tp3: float = None,
        tp3_hit: bool = False,
        tp3_size: float = None,
        atr_pct: float = None,
        trailing_stop_enabled: bool = False,
        trade_id: int = None,
    ) -> bool:
        """
        Insert or update a position with full state

        Args:
            ticker: Crypto ticker
            quantity: Total position quantity
            avg_buy_price: Average buy price
            current_price: Current market price
            remaining_quantity: Remaining qty after partial exits
            stop_loss: Current stop loss price
            tp1/tp2/tp3: Take profit levels
            tp1_hit/tp2_hit/tp3_hit: Whether TP levels were hit
            tp1_size/tp2_size/tp3_size: Fraction to sell at each TP
            atr_pct: ATR percentage for trailing stop
            trailing_stop_enabled: Whether trailing stop is active
            trade_id: Reference to the entry trade

        Returns:
            True if successful
        """
        try:
            if remaining_quantity is None:
                remaining_quantity = quantity

            total_value = remaining_quantity * current_price
            pnl = (current_price - avg_buy_price) * remaining_quantity
            pnl_percentage = ((current_price - avg_buy_price) / avg_buy_price) * 100 if avg_buy_price > 0 else 0

            # Check if position exists
            existing = self.get_position(ticker)

            if existing:
                # Update existing position
                query = """
                UPDATE positions
                SET quantity = :quantity,
                    remaining_quantity = :remaining_quantity,
                    avg_buy_price = :avg_buy_price,
                    current_price = :current_price,
                    total_value = :total_value,
                    pnl = :pnl,
                    pnl_percentage = :pnl_percentage,
                    stop_loss = :stop_loss,
                    tp1 = :tp1, tp1_hit = :tp1_hit, tp1_size = :tp1_size,
                    tp2 = :tp2, tp2_hit = :tp2_hit, tp2_size = :tp2_size,
                    tp3 = :tp3, tp3_hit = :tp3_hit, tp3_size = :tp3_size,
                    atr_pct = :atr_pct,
                    trailing_stop_enabled = :trailing_stop_enabled,
                    last_update = :last_update
                WHERE ticker = :ticker
                """
            else:
                # Insert new position
                query = """
                INSERT INTO positions (
                    ticker, quantity, remaining_quantity, avg_buy_price,
                    current_price, total_value, pnl, pnl_percentage,
                    stop_loss, tp1, tp1_hit, tp1_size, tp2, tp2_hit, tp2_size,
                    tp3, tp3_hit, tp3_size, atr_pct, trailing_stop_enabled,
                    trade_id, entry_time, last_update
                ) VALUES (
                    :ticker, :quantity, :remaining_quantity, :avg_buy_price,
                    :current_price, :total_value, :pnl, :pnl_percentage,
                    :stop_loss, :tp1, :tp1_hit, :tp1_size, :tp2, :tp2_hit, :tp2_size,
                    :tp3, :tp3_hit, :tp3_size, :atr_pct, :trailing_stop_enabled,
                    :trade_id, :entry_time, :last_update
                )
                """

            params = {
                'ticker': ticker,
                'quantity': quantity,
                'remaining_quantity': remaining_quantity,
                'avg_buy_price': avg_buy_price,
                'current_price': current_price,
                'total_value': total_value,
                'pnl': pnl,
                'pnl_percentage': pnl_percentage,
                'stop_loss': stop_loss,
                'tp1': tp1, 'tp1_hit': tp1_hit, 'tp1_size': tp1_size,
                'tp2': tp2, 'tp2_hit': tp2_hit, 'tp2_size': tp2_size,
                'tp3': tp3, 'tp3_hit': tp3_hit, 'tp3_size': tp3_size,
                'atr_pct': atr_pct,
                'trailing_stop_enabled': trailing_stop_enabled,
                'trade_id': trade_id,
                'entry_time': datetime.utcnow(),
                'last_update': datetime.utcnow()
            }

            with self.engine.connect() as conn:
                conn.execute(text(query), params)
                conn.commit()

            logger.debug(f"✅ Position upserted: {ticker}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to upsert position {ticker}: {e}")
            return False

    def delete_position(self, ticker: str) -> bool:
        """
        Delete a position

        Args:
            ticker: Crypto ticker

        Returns:
            True if successful
        """
        try:
            query = "DELETE FROM positions WHERE ticker = :ticker"
            with self.engine.connect() as conn:
                conn.execute(text(query), {'ticker': ticker})
                conn.commit()

            logger.debug(f"✅ Position deleted: {ticker}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to delete position {ticker}: {e}")
            return False

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

    def get_dashboard_stats(self, usdt_balance: float = 0.0, initial_capital: float = 10000.0) -> Dict[str, Any]:
        """
        Get aggregated statistics for dashboard

        Args:
            usdt_balance: Current available USDT balance from Binance
            initial_capital: Initial capital to calculate total P&L percentage

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

            # Total value of open positions
            positions_value_query = "SELECT COALESCE(SUM(total_value), 0) as total FROM positions"
            positions_result = self.execute_query(positions_value_query).iloc[0]['total']
            positions_value = float(positions_result) if positions_result is not None else 0.0

            # Total portfolio value (USDT balance + positions value)
            portfolio_value = usdt_balance + positions_value

            # Total P&L from open positions
            open_pnl_query = "SELECT COALESCE(SUM(pnl), 0) as total FROM positions"
            open_pnl_result = self.execute_query(open_pnl_query).iloc[0]['total']
            open_pnl = float(open_pnl_result) if open_pnl_result is not None else 0.0

            # Realized P&L from closed positions
            closed_pnl_query = """
            SELECT COALESCE(SUM(
                (s.price - b.price) * LEAST(b.quantity, s.quantity)
            ), 0) as realized_pnl
            FROM trades b
            INNER JOIN trades s ON b.ticker = s.ticker AND s.timestamp > b.timestamp
            WHERE b.action = 'BUY' AND b.status = 'executed'
              AND s.action = 'SELL' AND s.status = 'executed'
            """
            realized_pnl_result = self.execute_query(closed_pnl_query).iloc[0]['realized_pnl']
            realized_pnl = float(realized_pnl_result) if realized_pnl_result is not None else 0.0

            # Total P&L (realized + unrealized)
            total_pnl = realized_pnl + open_pnl

            # Total P&L percentage (based on initial capital)
            total_pnl_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0.0

            # Win rate (ONLY from closed positions)
            win_rate_query = """
            WITH closed_trades AS (
                SELECT
                    b.ticker,
                    (s.price - b.price) * LEAST(b.quantity, s.quantity) as pnl
                FROM trades b
                INNER JOIN trades s ON b.ticker = s.ticker AND s.timestamp > b.timestamp
                WHERE b.action = 'BUY' AND b.status = 'executed'
                  AND s.action = 'SELL' AND s.status = 'executed'
            )
            SELECT
                COUNT(CASE WHEN pnl > 0 THEN 1 END)::float / NULLIF(COUNT(*), 0) as win_rate
            FROM closed_trades
            """
            win_rate_result = self.execute_query(win_rate_query)
            if len(win_rate_result) > 0 and win_rate_result.iloc[0]['win_rate'] is not None:
                win_rate = float(win_rate_result.iloc[0]['win_rate'])
            else:
                win_rate = 0.0

            # Today's stats
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            # Today's P&L (from closed trades today)
            today_pnl_query = """
            SELECT COALESCE(SUM(
                (s.price - b.price) * LEAST(b.quantity, s.quantity)
            ), 0) as today_pnl
            FROM trades b
            INNER JOIN trades s ON b.ticker = s.ticker AND s.timestamp > b.timestamp
            WHERE b.action = 'BUY' AND b.status = 'executed'
              AND s.action = 'SELL' AND s.status = 'executed'
              AND s.timestamp >= :today_start
            """
            today_pnl_result = self.execute_query(today_pnl_query, {'today_start': today_start}).iloc[0]['today_pnl']
            today_pnl = float(today_pnl_result) if today_pnl_result is not None else 0.0

            # Today's P&L percentage
            today_pnl_pct = (today_pnl / portfolio_value * 100) if portfolio_value > 0 else 0.0

            return {
                'total_trades': int(total_trades),
                'executed_trades': int(executed_trades),
                'active_positions': int(active_positions),
                'usdt_balance': round(usdt_balance, 2),
                'positions_value': round(positions_value, 2),
                'portfolio_value': round(portfolio_value, 2),
                'total_pnl': round(total_pnl, 2),
                'total_pnl_pct': round(total_pnl_pct, 2),
                'realized_pnl': round(realized_pnl, 2),
                'unrealized_pnl': round(open_pnl, 2),
                'win_rate': round(win_rate * 100, 2) if win_rate else 0.0,
                'today_pnl': round(today_pnl, 2),
                'today_pnl_pct': round(today_pnl_pct, 2),
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"❌ Failed to get dashboard stats: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'total_trades': 0,
                'executed_trades': 0,
                'active_positions': 0,
                'usdt_balance': round(usdt_balance, 2),
                'positions_value': 0.0,
                'portfolio_value': round(usdt_balance, 2),
                'total_pnl': 0.0,
                'total_pnl_pct': 0.0,
                'realized_pnl': 0.0,
                'unrealized_pnl': 0.0,
                'win_rate': 0.0,
                'today_pnl': 0.0,
                'today_pnl_pct': 0.0,
                'timestamp': datetime.utcnow().isoformat()
            }

    # ============================================
    # PORTFOLIO MANAGEMENT
    # ============================================

    def get_portfolio(self) -> Dict[str, Any]:
        """
        Get current portfolio state

        Returns:
            Dictionary with portfolio data:
            - initial_capital: Starting capital
            - available_balance: Money available to trade
            - total_invested: Money currently in positions
            - realized_pnl: Realized profit/loss from closed trades
            - total_value: available_balance + total_invested
        """
        query = "SELECT * FROM portfolio WHERE id = 1"
        result = self.execute_query(query)

        if len(result) > 0:
            row = result.iloc[0]
            available = float(row['available_balance'])
            invested = float(row['total_invested'])
            return {
                'initial_capital': float(row['initial_capital']),
                'available_balance': available,
                'total_invested': invested,
                'realized_pnl': float(row['realized_pnl']),
                'total_value': available + invested,
                'last_update': row['last_update']
            }

        # Return defaults if no portfolio exists
        return {
            'initial_capital': 10000.0,
            'available_balance': 10000.0,
            'total_invested': 0.0,
            'realized_pnl': 0.0,
            'total_value': 10000.0,
            'last_update': datetime.utcnow()
        }

    def initialize_portfolio(self, initial_capital: float = 10000.0) -> bool:
        """
        Initialize or reset portfolio with given capital

        Args:
            initial_capital: Starting capital amount

        Returns:
            True if successful
        """
        query = """
        INSERT INTO portfolio (id, initial_capital, available_balance, total_invested, realized_pnl, created_at, last_update)
        VALUES (1, :capital, :capital, 0.0, 0.0, NOW(), NOW())
        ON CONFLICT (id) DO UPDATE SET
            initial_capital = :capital,
            available_balance = :capital,
            total_invested = 0.0,
            realized_pnl = 0.0,
            last_update = NOW()
        """
        try:
            self.execute_command(query, {'capital': initial_capital})
            logger.info(f"✅ Portfolio initialized with ${initial_capital:,.2f}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize portfolio: {e}")
            return False

    def deduct_from_balance(self, amount: float, ticker: str = None) -> bool:
        """
        Deduct amount from available balance when buying

        Args:
            amount: USD amount to deduct
            ticker: Optional ticker for logging

        Returns:
            True if successful, False if insufficient balance
        """
        # First check if we have enough balance
        portfolio = self.get_portfolio()
        if portfolio['available_balance'] < amount:
            logger.warning(f"⚠️ Insufficient balance: ${portfolio['available_balance']:.2f} < ${amount:.2f}")
            return False

        query = """
        UPDATE portfolio
        SET available_balance = available_balance - :amount,
            total_invested = total_invested + :amount,
            last_update = NOW()
        WHERE id = 1 AND available_balance >= :amount
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'amount': amount})
                conn.commit()
                if result.rowcount > 0:
                    logger.info(f"💸 Deducted ${amount:.2f} for {ticker or 'trade'}")
                    return True
                return False
        except Exception as e:
            logger.error(f"❌ Failed to deduct from balance: {e}")
            return False

    def add_to_balance(self, amount: float, pnl: float = 0.0, ticker: str = None) -> bool:
        """
        Add amount to available balance when selling

        Args:
            amount: USD amount to add (sale proceeds)
            pnl: Realized P&L from this sale
            ticker: Optional ticker for logging

        Returns:
            True if successful
        """
        # Calculate how much was invested (amount - pnl = original investment)
        invested_amount = amount - pnl

        query = """
        UPDATE portfolio
        SET available_balance = available_balance + :amount,
            total_invested = GREATEST(0, total_invested - :invested),
            realized_pnl = realized_pnl + :pnl,
            last_update = NOW()
        WHERE id = 1
        """
        try:
            self.execute_command(query, {
                'amount': amount,
                'invested': invested_amount,
                'pnl': pnl
            })
            logger.info(f"💰 Added ${amount:.2f} from {ticker or 'sale'} (P&L: ${pnl:+.2f})")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to add to balance: {e}")
            return False

    def sync_portfolio_with_positions(self) -> Dict[str, Any]:
        """
        Sync total_invested with actual positions value

        Returns:
            Updated portfolio state
        """
        # Get sum of positions at entry price (not current price)
        positions_query = """
        SELECT COALESCE(SUM(quantity * avg_buy_price), 0) as total_invested
        FROM positions
        """
        result = self.execute_query(positions_query)
        actual_invested = float(result.iloc[0]['total_invested'])

        # Update portfolio
        query = """
        UPDATE portfolio
        SET total_invested = :invested,
            last_update = NOW()
        WHERE id = 1
        """
        self.execute_command(query, {'invested': actual_invested})

        return self.get_portfolio()

    def can_afford_trade(self, amount: float) -> tuple[bool, str]:
        """
        Check if we can afford a trade

        Args:
            amount: USD amount needed

        Returns:
            Tuple of (can_afford, reason)
        """
        portfolio = self.get_portfolio()
        available = portfolio['available_balance']

        if available < amount:
            return False, f"Insufficient balance: ${available:.2f} < ${amount:.2f} needed"

        return True, f"Balance OK: ${available:.2f} available"
