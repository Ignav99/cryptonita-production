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
    Get overall dashboard statistics
    """
    try:
        stats = db.get_dashboard_stats()
        return DashboardStats(**stats)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions", response_model=List[Position])
async def get_positions(current_user: dict = Depends(get_current_user)):
    """
    Get all current positions
    """
    try:
        positions_df = db.get_positions()
        positions = positions_df.to_dict('records')
        return [Position(**pos) for pos in positions]
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
    Get total portfolio value for bot-opened positions

    Returns portfolio breakdown:
    - usdt_balance: Available USDT in Binance account
    - positions_value: Total value of bot-opened positions
    - total_value: USDT + positions value
    - positions_count: Number of bot positions
    """
    try:
        # Get USDT balance from Binance
        usdt_balance = binance.get_usdt_balance()

        # Get bot positions from database
        positions_df = db.get_positions()

        # Calculate total value of bot positions
        positions_value = 0.0
        if len(positions_df) > 0:
            positions_value = positions_df['total_value'].sum()

        total_value = usdt_balance + positions_value

        return {
            'usdt_balance': round(usdt_balance, 2),
            'positions_value': round(positions_value, 2),
            'total_value': round(total_value, 2),
            'positions_count': len(positions_df)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch portfolio value: {str(e)}")
