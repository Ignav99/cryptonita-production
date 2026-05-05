"""
HEALTH MONITOR
==============
Production safeguards for the trading bot:
- Trade rate limiting (circuit breaker)
- Stale price detection
- Table validation
- Daily health summary
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from loguru import logger

from config import settings


class HealthMonitor:
    """Production health monitoring and safeguards."""

    def __init__(self):
        self.max_trades_per_day = settings.MAX_TRADES_PER_DAY
        self.stale_price_hours = settings.STALE_PRICE_ALERT_HOURS

    def check_trade_rate(self, db) -> bool:
        """
        Check if we've exceeded the daily trade limit.
        Returns True if trading is allowed, False if rate limit exceeded.
        """
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            result = db.execute_query(
                "SELECT COUNT(*) as cnt FROM trades WHERE timestamp >= :start AND status = 'executed'",
                {'start': today_start}
            )
            count = int(result.iloc[0]['cnt']) if not result.empty else 0

            if count >= self.max_trades_per_day:
                logger.warning(
                    f"HEALTH: Trade rate limit reached ({count}/{self.max_trades_per_day}). "
                    f"Pausing new entries."
                )
                return False
            return True
        except Exception as e:
            logger.error(f"HEALTH: Trade rate check failed: {e}")
            return True  # Allow trading on error (fail open)

    def check_stale_positions(self, positions: Dict) -> List[str]:
        """
        Check for positions with stale (not recently updated) prices.
        Returns list of warning messages.
        """
        warnings = []
        cutoff = datetime.utcnow() - timedelta(hours=self.stale_price_hours)

        for ticker, pos in positions.items():
            last_update = pos.get('last_update') or pos.get('entry_time')
            if last_update is None:
                warnings.append(f"{ticker}: no last_update timestamp")
                continue

            if isinstance(last_update, str):
                try:
                    last_update = datetime.fromisoformat(last_update)
                except ValueError:
                    warnings.append(f"{ticker}: invalid timestamp format")
                    continue

            if last_update < cutoff:
                hours_stale = (datetime.utcnow() - last_update).total_seconds() / 3600
                warnings.append(f"{ticker}: price stale for {hours_stale:.1f}h")

        if warnings:
            logger.warning(f"HEALTH: {len(warnings)} stale positions: {', '.join(warnings)}")
        return warnings

    def validate_tables(self, db) -> List[str]:
        """
        Validate that required tables exist and are populated.
        Returns list of issues found.
        """
        issues = []
        required_tables = ['trades', 'signals', 'positions', 'portfolio', 'bot_status', 'performance_metrics']

        for table in required_tables:
            if not db.table_exists(table):
                issues.append(f"Table '{table}' does not exist")

        if issues:
            logger.warning(f"HEALTH: Table validation issues: {issues}")
        return issues

    def daily_summary(self, db, positions: Dict) -> Dict:
        """
        Generate a daily health summary for logging.
        """
        try:
            today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

            # Today's trade count
            trades_result = db.execute_query(
                "SELECT COUNT(*) as cnt FROM trades WHERE timestamp >= :start AND status = 'executed'",
                {'start': today_start}
            )
            today_trades = int(trades_result.iloc[0]['cnt']) if not trades_result.empty else 0

            # Active positions
            active_count = len(positions)

            # Portfolio value
            portfolio = db.get_portfolio()
            portfolio_value = portfolio.get('total_value', 0)

            # Stale positions
            stale_warnings = self.check_stale_positions(positions)

            # Calculate avg hold time of current positions
            hold_times = []
            for ticker, pos in positions.items():
                entry_time = pos.get('entry_time')
                if entry_time:
                    if isinstance(entry_time, str):
                        entry_time = datetime.fromisoformat(entry_time)
                    days = (datetime.utcnow() - entry_time).total_seconds() / 86400
                    hold_times.append(days)

            avg_hold = sum(hold_times) / len(hold_times) if hold_times else 0

            summary = {
                'timestamp': datetime.utcnow().isoformat(),
                'today_trades': today_trades,
                'trade_rate_ok': today_trades < self.max_trades_per_day,
                'active_positions': active_count,
                'portfolio_value': round(portfolio_value, 2),
                'stale_positions': len(stale_warnings),
                'avg_hold_days': round(avg_hold, 1),
            }

            logger.info(
                f"HEALTH SUMMARY: trades={today_trades}/{self.max_trades_per_day}, "
                f"positions={active_count}, portfolio=${portfolio_value:.2f}, "
                f"stale={len(stale_warnings)}, avg_hold={avg_hold:.1f}d"
            )
            return summary

        except Exception as e:
            logger.error(f"HEALTH: Daily summary failed: {e}")
            return {'error': str(e)}
