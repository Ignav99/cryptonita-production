"""
Dashboard Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from datetime import datetime, timedelta

from config import settings
from src.api.auth import get_current_user
from src.api.schemas.dashboard import (
    DashboardStats, Position, Signal, Trade, BotStatus, PerformanceMetric,
    SignalAnalysisSummary
)
import pandas as pd
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


@router.get("/signal-analysis", response_model=SignalAnalysisSummary)
async def get_signal_analysis(current_user: dict = Depends(get_current_user)):
    """
    Get signal performance analysis - how well are BUY signals predicting pumps?

    Analyzes:
    - Hit rate: % of signals that reached +20% target
    - Average return: mean max return achieved
    - Breakdown by probability range
    - Best/worst performing signals
    """
    try:
        # Get all BUY signals
        signals_df = db.execute_query("""
            SELECT id, ticker, signal_type, probability, timestamp
            FROM signals
            WHERE signal_type = 'BUY'
            ORDER BY timestamp ASC
        """, {})

        if len(signals_df) == 0:
            return SignalAnalysisSummary(
                total_signals=0,
                hit_rate=0.0,
                avg_return=0.0,
                mature_signals=0,
                mature_hit_rate=0.0,
                mature_avg_return=0.0,
                by_probability=[],
                recent_signals=[],
                best_signals=[],
                worst_signals=[]
            )

        results = []

        for _, signal in signals_df.iterrows():
            ticker = signal['ticker']
            signal_date = pd.to_datetime(signal['timestamp']).tz_localize(None)
            probability = signal['probability']

            # Get price at signal date
            price_at_signal = db.execute_query("""
                SELECT close FROM crypto_prices
                WHERE ticker = :ticker
                AND DATE(timestamp) = DATE(:signal_date)
                LIMIT 1
            """, {'ticker': ticker, 'signal_date': signal_date})

            if len(price_at_signal) == 0:
                continue

            entry_price = float(price_at_signal.iloc[0]['close'])

            # Get latest date available for this ticker
            latest_date_df = db.execute_query("""
                SELECT MAX(timestamp) as latest FROM crypto_prices WHERE ticker = :ticker
            """, {'ticker': ticker})
            latest_date = pd.to_datetime(latest_date_df.iloc[0]['latest']).tz_localize(None)

            days_available = (latest_date - signal_date).days

            # Get max price in next 30 days
            end_date = min(signal_date + timedelta(days=30), latest_date)

            max_price_df = db.execute_query("""
                SELECT MAX(high) as max_price
                FROM crypto_prices
                WHERE ticker = :ticker
                AND timestamp > :signal_date
                AND timestamp <= :end_date
            """, {'ticker': ticker, 'signal_date': signal_date, 'end_date': end_date})

            if len(max_price_df) == 0 or max_price_df.iloc[0]['max_price'] is None:
                continue

            max_price = float(max_price_df.iloc[0]['max_price'])
            max_return = (max_price - entry_price) / entry_price * 100
            hit_target = max_return >= 20.0

            results.append({
                'ticker': ticker,
                'signal_date': signal_date.date().isoformat(),
                'probability': round(probability, 4),
                'entry_price': round(entry_price, 4),
                'max_price': round(max_price, 4),
                'max_return_pct': round(max_return, 2),
                'hit_20pct': hit_target,
                'days_available': days_available
            })

        if not results:
            return SignalAnalysisSummary(
                total_signals=len(signals_df),
                hit_rate=0.0,
                avg_return=0.0,
                mature_signals=0,
                mature_hit_rate=0.0,
                mature_avg_return=0.0,
                by_probability=[],
                recent_signals=[],
                best_signals=[],
                worst_signals=[]
            )

        results_df = pd.DataFrame(results)

        # Overall stats
        total = len(results_df)
        hits = results_df['hit_20pct'].sum()
        hit_rate = round(hits / total * 100, 1)
        avg_return = round(results_df['max_return_pct'].mean(), 2)

        # Mature signals (>= 20 days)
        mature_df = results_df[results_df['days_available'] >= 20]
        mature_signals = len(mature_df)
        mature_hit_rate = round(mature_df['hit_20pct'].sum() / len(mature_df) * 100, 1) if len(mature_df) > 0 else 0.0
        mature_avg_return = round(mature_df['max_return_pct'].mean(), 2) if len(mature_df) > 0 else 0.0

        # By probability range
        by_probability = []
        prob_ranges = [
            (0.97, 1.00, "97-100%"),
            (0.95, 0.97, "95-97%"),
            (0.90, 0.95, "90-95%"),
            (0.80, 0.90, "80-90%"),
            (0.70, 0.80, "70-80%"),
        ]

        for low, high, label in prob_ranges:
            subset = results_df[(results_df['probability'] >= low) & (results_df['probability'] < high)]
            if len(subset) > 0:
                sub_hits = subset['hit_20pct'].sum()
                sub_rate = round(sub_hits / len(subset) * 100, 1)
                sub_avg = round(subset['max_return_pct'].mean(), 2)
                by_probability.append({
                    'range': label,
                    'count': len(subset),
                    'hit_rate': sub_rate,
                    'avg_return': sub_avg
                })

        # Recent signals (last 10)
        recent_signals = results_df.nlargest(10, 'signal_date').to_dict('records')

        # Best and worst signals
        best_signals = results_df.nlargest(5, 'max_return_pct').to_dict('records')
        worst_signals = results_df.nsmallest(5, 'max_return_pct').to_dict('records')

        return SignalAnalysisSummary(
            total_signals=total,
            hit_rate=hit_rate,
            avg_return=avg_return,
            mature_signals=mature_signals,
            mature_hit_rate=mature_hit_rate,
            mature_avg_return=mature_avg_return,
            by_probability=by_probability,
            recent_signals=recent_signals,
            best_signals=best_signals,
            worst_signals=worst_signals
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze signals: {str(e)}")
