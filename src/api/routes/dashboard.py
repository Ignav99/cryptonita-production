"""
Dashboard Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from datetime import datetime, timedelta

from config import settings
from src.api.auth import get_current_user
from src.api.schemas.dashboard import (
    DashboardStats, Position, Signal, Trade, BotStatus, PerformanceMetric
)
from src.data.storage.db_manager import DatabaseManager
from src.services.binance_service import BinanceService

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Database instance
db = DatabaseManager(settings.get_database_url())

# Binance service instance
binance = BinanceService()


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(current_user: dict = Depends(get_current_user)):
    """
    Get overall dashboard statistics with portfolio balance
    """
    try:
        # Get portfolio balance from our managed portfolio (NOT Binance)
        portfolio = db.get_portfolio()
        usdt_balance = portfolio['available_balance']

        # Get stats with portfolio balance
        stats = db.get_dashboard_stats(
            usdt_balance=usdt_balance,
            initial_capital=portfolio['initial_capital']
        )

        # Override with accurate portfolio values
        stats['usdt_balance'] = portfolio['available_balance']
        stats['positions_value'] = portfolio['total_invested']
        stats['portfolio_value'] = portfolio['total_value']

        return DashboardStats(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions", response_model=List[Position])
async def get_positions(current_user: dict = Depends(get_current_user)):
    """
    Get all current open positions
    """
    try:
        positions_df = db.get_positions()
        positions = positions_df.to_dict('records')
        return [Position(**pos) for pos in positions]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/closed-positions", response_model=List[Dict])
async def get_closed_positions(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Get closed positions (matched BUY/SELL pairs) with P&L info
    """
    try:
        closed_df = db.get_closed_positions(limit=limit)
        if len(closed_df) == 0:
            return []
        closed_positions = closed_df.to_dict('records')
        return closed_positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals", response_model=List[Signal])
async def get_recent_signals(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent trading signals
    """
    try:
        signals_df = db.get_recent_signals(limit=limit)
        signals = signals_df.to_dict('records')
        return [Signal(**signal) for signal in signals]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades", response_model=List[Trade])
async def get_recent_trades(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent trades
    """
    try:
        trades_df = db.get_recent_trades(limit=limit)
        trades = trades_df.to_dict('records')
        return [Trade(**trade) for trade in trades]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bot-status", response_model=BotStatus)
async def get_bot_status(current_user: dict = Depends(get_current_user)):
    """
    Get current bot status
    """
    try:
        status = db.get_bot_status()
        if not status:
            raise HTTPException(status_code=404, detail="Bot status not found")
        return BotStatus(**status)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance", response_model=List[PerformanceMetric])
async def get_performance_metrics(
    days: int = 30,
    current_user: dict = Depends(get_current_user)
):
    """
    Get performance metrics for last N days
    """
    try:
        start_date = (datetime.now() - timedelta(days=days)).date()
        metrics_df = db.get_performance_metrics(start_date=start_date, limit=days)
        metrics = metrics_df.to_dict('records')

        # Convert date to string
        for metric in metrics:
            if 'date' in metric and hasattr(metric['date'], 'isoformat'):
                metric['date'] = metric['date'].isoformat()

        return [PerformanceMetric(**metric) for metric in metrics]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/portfolio-value", response_model=Dict)
async def get_portfolio_value(current_user: dict = Depends(get_current_user)):
    """
    Get total portfolio value from managed portfolio

    Returns portfolio breakdown:
    - usdt_balance: Available USDT to trade
    - positions_value: Total value invested in positions
    - total_value: USDT + positions value
    - positions_count: Number of open positions
    - initial_capital: Starting capital
    - realized_pnl: Realized P&L from closed trades
    """
    try:
        # Get portfolio from our managed system (NOT Binance)
        portfolio = db.get_portfolio()

        # Get positions count from database
        positions_df = db.get_positions()

        return {
            'usdt_balance': round(portfolio['available_balance'], 2),
            'positions_value': round(portfolio['total_invested'], 2),
            'total_value': round(portfolio['total_value'], 2),
            'positions_count': len(positions_df),
            'initial_capital': round(portfolio['initial_capital'], 2),
            'realized_pnl': round(portfolio['realized_pnl'], 2)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch portfolio value: {str(e)}")


@router.post("/portfolio/initialize", response_model=Dict)
async def initialize_portfolio(
    initial_capital: float = 10000.0,
    current_user: dict = Depends(get_current_user)
):
    """
    Initialize or reset portfolio with given capital.
    WARNING: This will reset all balance tracking!

    Args:
        initial_capital: Starting capital amount (default: $10,000)

    Returns:
        New portfolio state
    """
    try:
        if initial_capital <= 0:
            raise HTTPException(status_code=400, detail="Initial capital must be positive")

        if initial_capital > 1000000:
            raise HTTPException(status_code=400, detail="Initial capital cannot exceed $1,000,000")

        success = db.initialize_portfolio(initial_capital)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to initialize portfolio")

        portfolio = db.get_portfolio()
        return {
            'success': True,
            'message': f'Portfolio initialized with ${initial_capital:,.2f}',
            'portfolio': portfolio
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize portfolio: {str(e)}")
