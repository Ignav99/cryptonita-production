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
    SignalAnalysisSummary, SignalDetail, CoinSummary, CoinTrend, CoinTrendPoint,
    SignalsSummaryStats, ThresholdProximity,
)
import pandas as pd
from loguru import logger
from src.data.storage.db_manager import DatabaseManager

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

# Database instance
db = DatabaseManager(settings.get_database_url())


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
        positions_df = positions_df.where(positions_df.notna(), None)
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
        closed_df = closed_df.where(closed_df.notna(), None)
        closed_positions = closed_df.to_dict('records')
        return closed_positions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/summary", response_model=SignalsSummaryStats)
async def get_signals_summary(current_user: dict = Depends(get_current_user)):
    """Get aggregate signal statistics"""
    try:
        risk_profiles = settings.COIN_RISK_PROFILES
        default_profile = settings.DEFAULT_RISK_PROFILE
        display_names = settings.TICKER_DISPLAY_NAMES

        latest_df = db.get_all_latest_signals()
        logger.info(f"📊 /signals/summary: found {len(latest_df)} latest signals")
        if len(latest_df) == 0:
            return SignalsSummaryStats(
                total_coins_scanned=0, buy_signals_count=0, short_signals_count=0,
                hold_signals_count=0, near_threshold_count=0, avg_probability=0.0,
            )

        # V4: signal_type = BUY/HOLD | V5: signal_type = LONG/SHORT/HOLD (via signal_name)
        signal_name_col = latest_df.get('signal_name', latest_df['signal_type'] if 'signal_type' in latest_df.columns else None)
        effective_type = signal_name_col if signal_name_col is not None else latest_df['signal_type']

        buy_count = int(effective_type.str.upper().isin(['BUY', 'LONG']).sum())
        short_count = int(effective_type.str.upper().isin(['SELL', 'SHORT']).sum())
        hold_count = int(effective_type.str.upper().isin(['HOLD']).sum())

        near_count = 0
        for _, row in latest_df.iterrows():
            profile = risk_profiles.get(row['ticker'], default_profile)
            distance = abs(float(row['probability']) - profile['threshold'])
            if distance <= 0.05:
                near_count += 1

        avg_prob = float(latest_df['probability'].mean())
        top_row = latest_df.loc[latest_df['probability'].idxmax()]
        last_scan = latest_df['timestamp'].max()

        return SignalsSummaryStats(
            total_coins_scanned=len(latest_df),
            buy_signals_count=buy_count,
            short_signals_count=short_count,
            hold_signals_count=hold_count,
            near_threshold_count=near_count,
            avg_probability=round(avg_prob, 4),
            highest_probability_ticker=display_names.get(top_row['ticker'], top_row['ticker']),
            highest_probability_value=round(float(top_row['probability']), 4),
            last_scan_time=last_scan,
        )
    except Exception as e:
        logger.error(f"❌ /signals/summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/coins", response_model=List[CoinSummary])
async def get_coin_summaries(current_user: dict = Depends(get_current_user)):
    """Get per-coin signal summary with trend info"""
    try:
        risk_profiles = settings.COIN_RISK_PROFILES
        default_profile = settings.DEFAULT_RISK_PROFILE
        display_names = settings.TICKER_DISPLAY_NAMES

        latest_df = db.get_all_latest_signals()
        logger.info(f"📊 /signals/coins: found {len(latest_df)} latest signals")
        stats_df = db.get_signals_stats(days=7)
        history_df = db.get_signal_history(days=14)

        stats_map = {}
        if len(stats_df) > 0:
            stats_map = {row['ticker']: row for _, row in stats_df.iterrows()}

        results = []
        for _, row in latest_df.iterrows():
            ticker = row['ticker']
            profile = risk_profiles.get(ticker, default_profile)
            threshold = profile['threshold']
            prob = float(row['probability'])
            distance = round(prob - threshold, 4)

            stats = stats_map.get(ticker, {})
            signal_count = int(stats.get('total_count', 0))
            buy_count = int(stats.get('buy_count', 0))

            # Trend: compare latest prob to avg of last 7 days
            ticker_history = history_df[history_df['ticker'] == ticker] if len(history_df) > 0 else pd.DataFrame()
            prob_change = None
            trend_dir = None
            if len(ticker_history) >= 2:
                prev_avg = float(ticker_history['probability'].iloc[:-1].mean())
                prob_change = round(prob - prev_avg, 4)
                trend_dir = 'up' if prob_change > 0.005 else ('down' if prob_change < -0.005 else 'flat')

            results.append(CoinSummary(
                ticker=ticker,
                display_name=display_names.get(ticker, ticker.replace('USDT', '')),
                latest_signal_type=row['signal_type'],
                latest_signal_name=row.get('signal_name'),
                latest_probability=round(prob, 4),
                threshold=threshold,
                tier=profile['tier'],
                distance_to_threshold=distance,
                probability_change=prob_change,
                trend_direction=trend_dir,
                signal_count_7d=signal_count,
                buy_count_7d=buy_count,
                last_scan=row['timestamp'],
                latest_rejection_reason=row.get('rejection_reason'),
            ))

        results.sort(key=lambda x: x.latest_probability, reverse=True)
        logger.info(f"📊 /signals/coins: returning {len(results)} coin summaries")
        return results
    except Exception as e:
        logger.error(f"❌ /signals/coins error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/trends", response_model=List[CoinTrend])
async def get_signal_trends(
    days: int = 14,
    tickers: str = None,
    current_user: dict = Depends(get_current_user),
):
    """Get probability time series per coin for trend charts"""
    try:
        risk_profiles = settings.COIN_RISK_PROFILES
        default_profile = settings.DEFAULT_RISK_PROFILE
        display_names = settings.TICKER_DISPLAY_NAMES

        history_df = db.get_signal_history(days=days)
        if len(history_df) == 0:
            return []

        if tickers:
            ticker_list = [t.strip() for t in tickers.split(',')]
            history_df = history_df[history_df['ticker'].isin(ticker_list)]

        results = []
        for ticker, group in history_df.groupby('ticker'):
            profile = risk_profiles.get(ticker, default_profile)
            points = [
                CoinTrendPoint(
                    probability=round(float(r['probability']), 4),
                    signal_type=r['signal_type'],
                    timestamp=r['timestamp'],
                )
                for _, r in group.iterrows()
            ]
            results.append(CoinTrend(
                ticker=ticker,
                display_name=display_names.get(ticker, ticker.replace('USDT', '')),
                threshold=profile['threshold'],
                data_points=points,
            ))

        return results
    except Exception as e:
        logger.error(f"❌ /signals/trends error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals/thresholds", response_model=List[ThresholdProximity])
async def get_threshold_proximity(current_user: dict = Depends(get_current_user)):
    """Get all coins ranked by proximity to their threshold"""
    try:
        risk_profiles = settings.COIN_RISK_PROFILES
        default_profile = settings.DEFAULT_RISK_PROFILE
        display_names = settings.TICKER_DISPLAY_NAMES

        latest_df = db.get_all_latest_signals()
        if len(latest_df) == 0:
            return []

        results = []
        for _, row in latest_df.iterrows():
            ticker = row['ticker']
            profile = risk_profiles.get(ticker, default_profile)
            prob = float(row['probability'])
            threshold = profile['threshold']
            distance_pct = round((prob - threshold) * 100, 2)

            results.append(ThresholdProximity(
                ticker=ticker,
                display_name=display_names.get(ticker, ticker.replace('USDT', '')),
                probability=round(prob, 4),
                threshold=threshold,
                distance_pct=distance_pct,
                tier=profile['tier'],
                signal_type=row['signal_type'],
            ))

        results.sort(key=lambda x: abs(x.distance_pct))
        return results
    except Exception as e:
        logger.error(f"❌ /signals/thresholds error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/signals", response_model=List[SignalDetail])
async def get_recent_signals(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """Get recent trading signals enriched with display_name, threshold, tier"""
    try:
        risk_profiles = settings.COIN_RISK_PROFILES
        default_profile = settings.DEFAULT_RISK_PROFILE
        display_names = settings.TICKER_DISPLAY_NAMES

        signals_df = db.get_recent_signals(limit=limit)
        logger.info(f"📊 /signals: found {len(signals_df)} signals (limit={limit})")
        results = []
        for _, row in signals_df.iterrows():
            ticker = row['ticker']
            profile = risk_profiles.get(ticker, default_profile)
            prob = float(row['probability'])
            threshold = profile['threshold']

            results.append(SignalDetail(
                id=int(row['id']),
                ticker=ticker,
                display_name=display_names.get(ticker, ticker.replace('USDT', '')),
                signal_type=row['signal_type'],
                probability=round(prob, 4),
                threshold=threshold,
                distance_to_threshold=round(prob - threshold, 4),
                tier=profile['tier'],
                timestamp=row['timestamp'],
            ))
        return results
    except Exception as e:
        logger.error(f"❌ /signals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def get_recent_trades(
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Get recent trades — returns raw dicts to avoid Decimal/Pydantic issues
    """
    try:
        trades_df = db.get_recent_trades(limit=limit)
        if trades_df.empty:
            return []
        # Convert every value to JSON-safe Python native types
        records = []
        for _, row in trades_df.iterrows():
            record = {}
            for col in trades_df.columns:
                val = row[col]
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    record[col] = None
                elif hasattr(val, 'isoformat'):
                    record[col] = val.isoformat()
                elif isinstance(val, (int, float, str, bool)):
                    record[col] = val
                else:
                    # Decimal, numpy types, etc → float or str
                    try:
                        record[col] = float(val)
                    except (ValueError, TypeError):
                        record[col] = str(val)
            records.append(record)
        return records
    except Exception as e:
        logger.error(f"❌ /trades error: {e}")
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


@router.get("/performance")
async def get_performance_metrics(
    days: int = 30,
    current_user: dict = Depends(get_current_user)
):
    """
    Get performance metrics for last N days — raw dicts to avoid Decimal issues
    """
    try:
        start_date = (datetime.now() - timedelta(days=days)).date()
        metrics_df = db.get_performance_metrics(start_date=start_date, limit=days)
        if metrics_df.empty:
            return []
        records = []
        for _, row in metrics_df.iterrows():
            record = {}
            for col in metrics_df.columns:
                val = row[col]
                if val is None or (isinstance(val, float) and pd.isna(val)):
                    record[col] = None
                elif hasattr(val, 'isoformat'):
                    record[col] = val.isoformat()
                elif isinstance(val, (int, float, str, bool)):
                    record[col] = val
                else:
                    try:
                        record[col] = float(val)
                    except (ValueError, TypeError):
                        record[col] = str(val)
            records.append(record)
        return records
    except Exception as e:
        logger.error(f"❌ /performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backfill-performance")
async def backfill_performance(current_user: dict = Depends(get_current_user)):
    """Backfill performance_metrics from historical trades"""
    try:
        count = db.backfill_performance_metrics()
        return {"status": "ok", "days_backfilled": count}
    except Exception as e:
        logger.error(f"❌ /backfill-performance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/review-reports")
async def get_review_reports(
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """Get 15-day review reports"""
    try:
        # Check if table exists
        check_query = """
        SELECT EXISTS (
            SELECT FROM information_schema.tables
            WHERE table_name = 'review_reports'
        ) as exists
        """
        exists_df = db.execute_query(check_query)
        if not exists_df.iloc[0]['exists']:
            return []

        query = """
        SELECT id, period, report_data, created_at
        FROM review_reports
        ORDER BY created_at DESC
        LIMIT :limit
        """
        df = db.execute_query(query, {'limit': limit})
        if df.empty:
            return []

        records = []
        for _, row in df.iterrows():
            record = {
                'id': int(row['id']),
                'period': str(row['period']),
                'report_data': row['report_data'] if isinstance(row['report_data'], dict) else {},
                'created_at': row['created_at'].isoformat() if hasattr(row['created_at'], 'isoformat') else str(row['created_at']),
            }
            records.append(record)
        return records
    except Exception as e:
        logger.error(f"❌ /review-reports error: {e}")
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


@router.post("/portfolio/recalibrate", response_model=Dict)
async def recalibrate_portfolio(current_user: dict = Depends(get_current_user)):
    """
    Recalibrate portfolio table from actual trades and positions.
    Fixes desynchronized available_balance, total_invested, and realized_pnl.
    """
    try:
        # Read initial_capital from DB — never hardcode, respects soft-reset
        portfolio = db.get_portfolio()
        initial_capital = portfolio['initial_capital']

        # 1. Real invested = sum of (remaining_qty * avg_buy_price) for open positions
        invested_df = db.execute_query("""
            SELECT COALESCE(SUM(remaining_quantity * avg_buy_price), 0) as real_invested
            FROM positions WHERE remaining_quantity > 0.0001
        """)
        real_invested = float(invested_df.iloc[0]['real_invested'])

        # 2. Realized PnL from matched BUY/SELL pairs (FIFO matched)
        pnl_df = db.execute_query("""
            WITH numbered_buys AS (
                SELECT ticker, price, quantity,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
                FROM trades WHERE action = 'BUY' AND status = 'executed'
            ),
            numbered_sells AS (
                SELECT ticker, price, quantity,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
                FROM trades WHERE action = 'SELL' AND status = 'executed'
            )
            SELECT COALESCE(SUM(
                (s.price - b.price) * LEAST(b.quantity, s.quantity)
            ), 0) as realized_pnl
            FROM numbered_buys b
            INNER JOIN numbered_sells s ON b.ticker = s.ticker AND b.rn = s.rn
        """)
        realized_pnl = float(pnl_df.iloc[0]['realized_pnl'])

        # 3. Available balance = initial_capital + realized_pnl - real_invested
        available_balance = initial_capital + realized_pnl - real_invested

        # 4. Update portfolio table
        db.execute_command("""
            UPDATE portfolio SET
                available_balance = :available,
                total_invested = :invested,
                realized_pnl = :pnl,
                last_update = NOW()
            WHERE id = 1
        """, {
            'available': round(available_balance, 2),
            'invested': round(real_invested, 2),
            'pnl': round(realized_pnl, 2),
        })

        # 5. Also clean dust positions
        db.execute_command("""
            DELETE FROM positions WHERE remaining_quantity <= 0.0001 AND remaining_quantity IS NOT NULL
        """)

        total_value = available_balance + real_invested
        return {
            'success': True,
            'available_balance': round(available_balance, 2),
            'total_invested': round(real_invested, 2),
            'realized_pnl': round(realized_pnl, 2),
            'total_value': round(total_value, 2),
            'message': f'Portfolio recalibrated: ${total_value:.2f} total (available=${available_balance:.2f} + invested=${real_invested:.2f}, realized_pnl=${realized_pnl:.2f})'
        }
    except Exception as e:
        logger.error(f"Recalibrate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
