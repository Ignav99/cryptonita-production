"""
Trading Bot Integration Module
Connects the XGBoost trading bot with the web dashboard backend
"""
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings
from data.storage.db_manager import DatabaseManager


class BotIntegration:
    """
    Integration layer between trading bot and web dashboard
    Call these methods from your trading bot to log all activities
    """

    def __init__(self):
        """Initialize database connection"""
        self.db = DatabaseManager(settings.get_database_url())
        logger.info("✅ Bot integration initialized")

    def log_signal(
        self,
        ticker: str,
        signal_type: str,
        probability: float,
        features: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Log a trading signal from the model

        Args:
            ticker: Crypto ticker (e.g., 'BTC-USD')
            signal_type: 'BUY', 'SELL', or 'HOLD'
            probability: Model prediction probability (0-1)
            features: Feature values used for prediction

        Returns:
            Signal ID

        Example:
            >>> bot = BotIntegration()
            >>> signal_id = bot.log_signal(
            ...     ticker='BTC-USD',
            ...     signal_type='BUY',
            ...     probability=0.85,
            ...     features={'rsi': 45.2, 'macd': 0.003}
            ... )
        """
        try:
            signal_id = self.db.save_signal(
                ticker=ticker,
                signal_type=signal_type,
                probability=probability,
                features=features or {}
            )
            return signal_id
        except Exception as e:
            logger.error(f"❌ Failed to log signal: {e}")
            raise

    def log_trade(
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
        Log a trade execution

        Args:
            signal_id: Related signal ID
            ticker: Crypto ticker
            action: 'BUY' or 'SELL'
            quantity: Amount to trade
            price: Execution price
            total_value: Total USD value
            status: 'pending', 'executed', 'failed', or 'cancelled'

        Returns:
            Trade ID

        Example:
            >>> trade_id = bot.log_trade(
            ...     signal_id=123,
            ...     ticker='BTC-USD',
            ...     action='BUY',
            ...     quantity=0.001,
            ...     price=45000.0,
            ...     total_value=45.0,
            ...     status='executed'
            ... )
        """
        try:
            trade_id = self.db.save_trade(
                signal_id=signal_id,
                ticker=ticker,
                action=action,
                quantity=quantity,
                price=price,
                total_value=total_value,
                status=status
            )
            return trade_id
        except Exception as e:
            logger.error(f"❌ Failed to log trade: {e}")
            raise

    def update_trade_status(
        self,
        trade_id: int,
        status: str,
        error_message: Optional[str] = None
    ) -> None:
        """
        Update trade status after execution attempt

        Args:
            trade_id: Trade ID to update
            status: New status ('executed', 'failed', 'cancelled')
            error_message: Error message if status is 'failed'
        """
        try:
            query = """
            UPDATE trades
            SET status = :status,
                executed_at = :executed_at,
                error_message = :error_message
            WHERE id = :trade_id
            """
            params = {
                "trade_id": trade_id,
                "status": status,
                "executed_at": datetime.utcnow() if status == 'executed' else None,
                "error_message": error_message
            }
            self.db.execute_command(query, params)
            logger.info(f"✅ Trade {trade_id} updated to {status}")
        except Exception as e:
            logger.error(f"❌ Failed to update trade status: {e}")
            raise

    def update_bot_status(
        self,
        status: str,
        total_signals: int,
        buy_signals: int,
        cycle_number: int,
        last_error: Optional[str] = None
    ) -> None:
        """
        Update bot status for dashboard monitoring

        Args:
            status: 'running', 'idle', 'error', or 'stopped'
            total_signals: Total signals processed in this cycle
            buy_signals: Number of buy signals
            cycle_number: Current cycle number
            last_error: Last error message if any

        Example:
            >>> bot.update_bot_status(
            ...     status='running',
            ...     total_signals=43,
            ...     buy_signals=0,
            ...     cycle_number=1
            ... )
        """
        try:
            self.db.update_bot_status(
                status=status,
                total_signals=total_signals,
                buy_signals=buy_signals,
                cycle_number=cycle_number,
                last_error=last_error
            )
        except Exception as e:
            logger.error(f"❌ Failed to update bot status: {e}")
            raise

    def update_position(
        self,
        ticker: str,
        quantity: float,
        avg_buy_price: float,
        current_price: float
    ) -> None:
        """
        Update or create a position in the portfolio

        Args:
            ticker: Crypto ticker
            quantity: Current quantity held
            avg_buy_price: Average buy price
            current_price: Current market price
        """
        try:
            total_value = quantity * current_price
            pnl = (current_price - avg_buy_price) * quantity
            pnl_percentage = (current_price - avg_buy_price) / avg_buy_price

            query = """
            INSERT INTO positions (ticker, quantity, avg_buy_price, current_price, total_value, pnl, pnl_percentage, last_update)
            VALUES (:ticker, :quantity, :avg_buy_price, :current_price, :total_value, :pnl, :pnl_percentage, :last_update)
            ON CONFLICT (ticker) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                avg_buy_price = EXCLUDED.avg_buy_price,
                current_price = EXCLUDED.current_price,
                total_value = EXCLUDED.total_value,
                pnl = EXCLUDED.pnl,
                pnl_percentage = EXCLUDED.pnl_percentage,
                last_update = EXCLUDED.last_update
            """
            params = {
                "ticker": ticker,
                "quantity": quantity,
                "avg_buy_price": avg_buy_price,
                "current_price": current_price,
                "total_value": total_value,
                "pnl": pnl,
                "pnl_percentage": pnl_percentage,
                "last_update": datetime.utcnow()
            }
            self.db.execute_command(query, params)
            logger.info(f"✅ Position updated: {ticker}")
        except Exception as e:
            logger.error(f"❌ Failed to update position: {e}")
            raise

    def remove_position(self, ticker: str) -> None:
        """
        Remove a position from the portfolio (when fully sold)

        Args:
            ticker: Crypto ticker to remove
        """
        try:
            query = "DELETE FROM positions WHERE ticker = :ticker"
            self.db.execute_command(query, {"ticker": ticker})
            logger.info(f"✅ Position removed: {ticker}")
        except Exception as e:
            logger.error(f"❌ Failed to remove position: {e}")
            raise

    def save_daily_performance(
        self,
        date: datetime,
        total_trades: int,
        successful_trades: int,
        failed_trades: int,
        total_volume: float,
        total_pnl: float,
        portfolio_value: float,
        win_rate: float = 0.0,
        sharpe_ratio: Optional[float] = None,
        max_drawdown: Optional[float] = None
    ) -> None:
        """
        Save daily performance snapshot

        Args:
            date: Date for this snapshot
            total_trades: Total trades executed
            successful_trades: Successful trades
            failed_trades: Failed trades
            total_volume: Total trading volume in USD
            total_pnl: Total P&L for the day
            portfolio_value: Total portfolio value
            win_rate: Win rate (0-1)
            sharpe_ratio: Sharpe ratio (optional)
            max_drawdown: Maximum drawdown (optional)
        """
        try:
            query = """
            INSERT INTO performance_metrics (
                date, total_trades, successful_trades, failed_trades,
                total_volume, total_pnl, win_rate, sharpe_ratio,
                max_drawdown, portfolio_value, timestamp
            )
            VALUES (
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
            params = {
                "date": date.date(),
                "total_trades": total_trades,
                "successful_trades": successful_trades,
                "failed_trades": failed_trades,
                "total_volume": total_volume,
                "total_pnl": total_pnl,
                "win_rate": win_rate,
                "sharpe_ratio": sharpe_ratio,
                "max_drawdown": max_drawdown,
                "portfolio_value": portfolio_value,
                "timestamp": datetime.utcnow()
            }
            self.db.execute_command(query, params)
            logger.info(f"✅ Daily performance saved: {date.date()}")
        except Exception as e:
            logger.error(f"❌ Failed to save daily performance: {e}")
            raise

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get all current positions

        Returns:
            List of position dictionaries
        """
        try:
            query = "SELECT * FROM positions ORDER BY total_value DESC"
            result = self.db.execute_query(query)
            return result.to_dict('records')
        except Exception as e:
            logger.error(f"❌ Failed to get positions: {e}")
            return []

    def close(self):
        """Close database connection"""
        self.db.close()
        logger.info("🔌 Bot integration closed")


# Example usage in your trading bot:
"""
from trading.bot_integration import BotIntegration

# Initialize integration
bot_integration = BotIntegration()

# At start of trading cycle
bot_integration.update_bot_status(
    status='running',
    total_signals=43,
    buy_signals=0,
    cycle_number=1
)

# When model generates a signal
for ticker, prediction, probability, features in predictions:
    signal_id = bot_integration.log_signal(
        ticker=ticker,
        signal_type='BUY' if prediction == 1 else 'HOLD',
        probability=probability,
        features=features
    )

    # If signal is BUY and above threshold
    if prediction == 1 and probability > 0.7:
        # Execute trade
        trade_id = bot_integration.log_trade(
            signal_id=signal_id,
            ticker=ticker,
            action='BUY',
            quantity=0.001,
            price=current_price,
            total_value=current_price * 0.001,
            status='pending'
        )

        # Try to execute on exchange
        try:
            # ... execute trade on Binance ...
            bot_integration.update_trade_status(trade_id, 'executed')
            bot_integration.update_position(
                ticker=ticker,
                quantity=0.001,
                avg_buy_price=current_price,
                current_price=current_price
            )
        except Exception as e:
            bot_integration.update_trade_status(trade_id, 'failed', str(e))

# At end of trading cycle
bot_integration.update_bot_status(
    status='idle',
    total_signals=43,
    buy_signals=0,
    cycle_number=1
)

# At end of day
bot_integration.save_daily_performance(
    date=datetime.now(),
    total_trades=10,
    successful_trades=8,
    failed_trades=2,
    total_volume=1000.0,
    total_pnl=50.25,
    portfolio_value=10050.25,
    win_rate=0.8
)
"""
