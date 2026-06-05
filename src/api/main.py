"""
CRYPTONITA PRODUCTION - API MAIN
=================================
FastAPI application for trading dashboard and bot control
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pathlib import Path
from loguru import logger

from config import settings
from src.api.routes import auth, dashboard, controls, websocket
from src.bot.bot_manager import BotManager
from src.data.storage.db_manager import DatabaseManager

# Create FastAPI app
app = FastAPI(
    title="Cryptonita Trading Bot API",
    description="API for ML-based cryptocurrency trading bot with real-time dashboard",
    version=settings.APP_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS middleware - Allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(controls.router, prefix="/api")
app.include_router(websocket.router, prefix="/api")

# Serve static files (frontend - after build)
FRONTEND_DIR = Path(__file__).parent.parent.parent / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"

# Only mount static files if frontend is built
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "static").exists():
    try:
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIST / "static")), name="static")
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "static")), name="assets")
        logger.info(f"✅ Frontend assets mounted from {FRONTEND_DIST / 'static'}")
    except Exception as e:
        logger.warning(f"⚠️ Could not mount frontend assets: {e}")


@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Serve frontend dashboard HTML
    """
    # Try to serve built frontend first
    index_file = FRONTEND_DIST / "index.html"

    if index_file.exists():
        return index_file.read_text()
    else:
        # Return simple welcome page if frontend not built yet
        return """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Cryptonita Trading Bot</title>
            <style>
                body {
                    font-family: 'Segoe UI', Arial, sans-serif;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    height: 100vh;
                    margin: 0;
                    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                    color: white;
                }
                .container {
                    text-align: center;
                }
                h1 {
                    font-size: 3em;
                    margin-bottom: 0.2em;
                }
                p {
                    font-size: 1.3em;
                    opacity: 0.9;
                }
                .links {
                    margin-top: 2em;
                }
                a {
                    color: white;
                    text-decoration: none;
                    padding: 10px 20px;
                    border: 2px solid white;
                    border-radius: 5px;
                    margin: 0 10px;
                    display: inline-block;
                    transition: all 0.3s;
                }
                a:hover {
                    background: white;
                    color: #667eea;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <h1>🚀 Cryptonita Trading Bot</h1>
                <p>ML-Powered Cryptocurrency Trading System V5</p>
                <p>Model: Ensemble (XGB+LGBM+CatBoost) | Auto-Training | ~80 Features</p>
                <div class="links">
                    <a href="/api/docs">📚 API Documentation</a>
                    <a href="/api/dashboard/stats">📊 Dashboard API</a>
                </div>
            </div>
        </body>
        </html>
        """


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "trading_mode": settings.TRADING_MODE
    }


@app.on_event("startup")
async def startup_event():
    """Run on application startup"""
    import asyncio
    logger.info("=" * 60)
    logger.info("🚀 CRYPTONITA TRADING BOT API - STARTING")
    logger.info(f"Version: {settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Trading Mode: {settings.TRADING_MODE}")
    logger.info(f"V5 Model dir: {getattr(settings, 'V5_MODEL_DIR', 'not set')}")
    logger.info(f"Auto-Train: {getattr(settings, 'AUTO_TRAIN_ENABLED', False)}")
    logger.info(f"API running on: http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info("=" * 60)

    # Ensure lifecycle schema is up to date
    try:
        db = DatabaseManager(settings.get_database_url())
        db.ensure_lifecycle_schema()

        # Sync portfolio invested amount from real open positions (startup only).
        # We trust the stored realized_pnl and initial_capital — do NOT recalculate
        # PnL from all trades, which would corrupt balances set by soft-reset.
        invested_df = db.execute_query("""
            SELECT COALESCE(SUM(remaining_quantity * avg_buy_price), 0) as real_invested
            FROM positions WHERE remaining_quantity > 0.0001
        """)
        real_invested = float(invested_df.iloc[0]['real_invested'])
        portfolio_df = db.execute_query(
            "SELECT initial_capital, realized_pnl FROM portfolio WHERE id = 1"
        )
        if not portfolio_df.empty:
            initial_capital = float(portfolio_df.iloc[0]['initial_capital'])
            realized_pnl = float(portfolio_df.iloc[0]['realized_pnl'])
        else:
            initial_capital = 10000.0
            realized_pnl = 0.0
        available = initial_capital + realized_pnl - real_invested
        db.execute_command("""
            UPDATE portfolio SET available_balance = :a, total_invested = :i,
                last_update = NOW() WHERE id = 1
        """, {'a': round(available, 2), 'i': round(real_invested, 2)})
        # Clean dust positions
        db.execute_command("DELETE FROM positions WHERE remaining_quantity <= 0.0001 AND remaining_quantity IS NOT NULL")
        logger.info(f"Portfolio synced on startup: available=${available:.2f}, invested=${real_invested:.2f}, pnl=${realized_pnl:.2f}")

        db.close()
        logger.info("Lifecycle schema ensured")
    except Exception as e:
        logger.warning(f"Schema upgrade warning: {e}")

    # Self-ping to keep Render alive (every 10 minutes)
    if settings.ENVIRONMENT == "production":
        asyncio.create_task(_keep_alive_loop())

    # Backfill performance metrics if table is empty (one-time on first deploy)
    asyncio.create_task(_backfill_performance_if_empty())

    # Auto-start bot and launch watchdog
    asyncio.create_task(_auto_start_bot())
    asyncio.create_task(_bot_watchdog_loop())

    # 15-day automated review cycle
    asyncio.create_task(_review_cycle_loop())


async def _keep_alive_loop():
    """Ping ourselves every 10 minutes to prevent Render free tier from sleeping."""
    import asyncio
    import httpx

    await asyncio.sleep(60)  # Wait 1 min after startup
    url = "https://cryptonita-production.onrender.com/health"

    while True:
        try:
            async with httpx.AsyncClient() as client:
                await client.get(url, timeout=10)
        except Exception:
            pass
        await asyncio.sleep(600)  # Every 10 minutes


async def _auto_start_bot():
    """Auto-start the trading bot 10 seconds after API startup."""
    import asyncio
    await asyncio.sleep(10)

    bot_manager = BotManager()
    if bot_manager.is_running():
        logger.info("Bot already running, skipping auto-start")
        return

    logger.info("Auto-starting trading bot...")
    result = bot_manager.start(mode="auto")
    if result["success"]:
        try:
            db = DatabaseManager(settings.get_database_url())
            db.update_bot_status(
                status='running',
                total_signals=0,
                buy_signals=0,
                cycle_number=0,
                last_error=None
            )
            db.close()
        except Exception as e:
            logger.warning(f"Could not update bot status in DB: {e}")
        logger.success(f"Bot auto-started (PID: {result['pid']})")
    else:
        logger.error(f"Bot auto-start failed: {result['message']}")


async def _bot_watchdog_loop():
    """Check bot health every 5 minutes. Restart if dead."""
    import asyncio
    await asyncio.sleep(120)  # Wait 2 min after startup before first check

    bot_manager = BotManager()
    consecutive_dead = 0

    while True:
        try:
            if not bot_manager.is_running():
                consecutive_dead += 1
                logger.warning(f"Watchdog: bot not running (count: {consecutive_dead})")

                if consecutive_dead >= 2:  # Dead for 2 consecutive checks (~10 min)
                    logger.warning("Watchdog: restarting bot...")
                    result = bot_manager.start(mode="auto")
                    if result["success"]:
                        try:
                            db = DatabaseManager(settings.get_database_url())
                            db.update_bot_status(
                                status='running',
                                total_signals=0,
                                buy_signals=0,
                                cycle_number=0,
                                last_error=None
                            )
                            db.close()
                        except Exception:
                            pass
                        logger.success(f"Watchdog: bot restarted (PID: {result['pid']})")
                        consecutive_dead = 0
                    else:
                        logger.error(f"Watchdog: restart failed - {result['message']}")
            else:
                consecutive_dead = 0
        except Exception as e:
            logger.error(f"Watchdog error: {e}")

        await asyncio.sleep(300)  # Check every 5 minutes


async def _backfill_performance_if_empty():
    """Backfill performance_metrics table if empty (runs once on startup)."""
    import asyncio
    await asyncio.sleep(5)  # Wait for DB to be ready
    try:
        db = DatabaseManager(settings.get_database_url())
        existing = db.get_latest_performance()
        if existing is None:
            logger.info("📊 Performance metrics empty — running backfill...")
            count = db.backfill_performance_metrics()
            logger.success(f"📊 Backfilled {count} days of performance metrics")
        else:
            logger.info("📊 Performance metrics already populated, skipping backfill")
        db.close()
    except Exception as e:
        logger.warning(f"⚠️ Performance backfill failed: {e}")


async def _review_cycle_loop():
    """Automated 15-day review cycle — generates performance report and stores in DB."""
    import asyncio
    from datetime import datetime, timedelta

    await asyncio.sleep(300)  # Wait 5 min after startup

    REVIEW_INTERVAL_DAYS = 15
    REVIEW_INTERVAL_SECONDS = REVIEW_INTERVAL_DAYS * 24 * 3600

    while True:
        try:
            db = DatabaseManager(settings.get_database_url())
            report = _generate_review_report(db)
            db.close()

            # Log the full report
            logger.info("=" * 60)
            logger.info("📋 15-DAY AUTOMATED REVIEW REPORT")
            logger.info("=" * 60)
            for key, value in report.items():
                logger.info(f"  {key}: {value}")
            logger.info("=" * 60)

            # Save report to DB
            try:
                db2 = DatabaseManager(settings.get_database_url())
                _save_review_report(db2, report)
                db2.close()
            except Exception as save_err:
                logger.warning(f"⚠️ Could not save review report: {save_err}")

        except Exception as e:
            logger.error(f"❌ Review cycle error: {e}")

        await asyncio.sleep(REVIEW_INTERVAL_SECONDS)


def _generate_review_report(db: DatabaseManager) -> dict:
    """Generate a comprehensive 15-day performance review."""
    from datetime import datetime, timedelta
    import pandas as pd

    now = datetime.utcnow()
    period_start = now - timedelta(days=15)

    # Trades in period
    trades_query = """
    SELECT * FROM trades
    WHERE status = 'executed' AND timestamp >= :start
    ORDER BY timestamp
    """
    trades_df = db.execute_query(trades_query, {'start': period_start})

    total_trades = len(trades_df) if not trades_df.empty else 0
    buys = len(trades_df[trades_df['action'] == 'BUY']) if not trades_df.empty else 0
    sells = len(trades_df[trades_df['action'] == 'SELL']) if not trades_df.empty else 0

    # Volume
    volume = 0.0
    if not trades_df.empty and 'total_value' in trades_df.columns:
        volume = float(trades_df['total_value'].astype(float).abs().sum())

    # Closed P&L in period (FIFO matched)
    pnl_query = """
    WITH numbered_buys AS (
        SELECT ticker, price, quantity,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
        FROM trades WHERE action = 'BUY' AND status = 'executed'
    ),
    numbered_sells AS (
        SELECT ticker, price, quantity, timestamp,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
        FROM trades WHERE action = 'SELL' AND status = 'executed'
    ),
    matched AS (
        SELECT (s.price - b.price) * LEAST(b.quantity, s.quantity) as pnl,
               s.price as sell_price, b.price as buy_price
        FROM numbered_buys b
        INNER JOIN numbered_sells s ON b.ticker = s.ticker AND b.rn = s.rn
        WHERE s.timestamp >= :start
    )
    SELECT COALESCE(SUM(pnl), 0) as pnl,
           COUNT(*) as closed_count,
           COUNT(CASE WHEN pnl > 0 THEN 1 END) as wins
    FROM matched
    """
    pnl_df = db.execute_query(pnl_query, {'start': period_start})

    realized_pnl = float(pnl_df.iloc[0]['pnl']) if not pnl_df.empty else 0.0
    closed_count = int(pnl_df.iloc[0]['closed_count']) if not pnl_df.empty else 0
    wins = int(pnl_df.iloc[0]['wins']) if not pnl_df.empty else 0
    win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0

    # Current positions
    positions_query = "SELECT COUNT(*) as cnt, COALESCE(SUM(total_value), 0) as val, COALESCE(SUM(pnl), 0) as pnl FROM positions WHERE remaining_quantity > 0.0001"
    pos_df = db.execute_query(positions_query)
    open_positions = int(pos_df.iloc[0]['cnt']) if not pos_df.empty else 0
    positions_value = float(pos_df.iloc[0]['val']) if not pos_df.empty else 0.0
    unrealized_pnl = float(pos_df.iloc[0]['pnl']) if not pos_df.empty else 0.0

    # Portfolio value
    portfolio = db.get_portfolio()
    portfolio_value = float(portfolio.get('total_value', 0)) if portfolio else 0.0
    initial_capital = float(portfolio.get('initial_capital', 10000)) if portfolio else 10000.0

    # ROI
    total_pnl = realized_pnl + unrealized_pnl
    roi_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0.0

    # Signals in period
    signals_query = """
    SELECT COUNT(*) as total,
           COUNT(CASE WHEN signal_type IN ('BUY', 'LONG') THEN 1 END) as buy_signals
    FROM signals WHERE timestamp >= :start
    """
    sig_df = db.execute_query(signals_query, {'start': period_start})
    total_signals = int(sig_df.iloc[0]['total']) if not sig_df.empty else 0
    buy_signals = int(sig_df.iloc[0]['buy_signals']) if not sig_df.empty else 0

    # Best and worst trades (FIFO matched)
    best_worst_query = """
    WITH numbered_buys AS (
        SELECT ticker, price, quantity,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
        FROM trades WHERE action = 'BUY' AND status = 'executed'
    ),
    numbered_sells AS (
        SELECT ticker, price, quantity, timestamp,
               ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY timestamp) as rn
        FROM trades WHERE action = 'SELL' AND status = 'executed'
    )
    SELECT b.ticker,
           (s.price - b.price) * LEAST(b.quantity, s.quantity) as pnl,
           ((s.price - b.price) / NULLIF(b.price, 0)) * 100 as pnl_pct
    FROM numbered_buys b
    INNER JOIN numbered_sells s ON b.ticker = s.ticker AND b.rn = s.rn
    WHERE s.timestamp >= :start
    ORDER BY pnl DESC
    """
    bw_df = db.execute_query(best_worst_query, {'start': period_start})

    best_trade = "N/A"
    worst_trade = "N/A"
    if not bw_df.empty:
        best_row = bw_df.iloc[0]
        best_trade = f"{best_row['ticker']} (+${float(best_row['pnl']):.2f}, {float(best_row['pnl_pct']):.1f}%)"
        worst_row = bw_df.iloc[-1]
        worst_trade = f"{worst_row['ticker']} (${float(worst_row['pnl']):.2f}, {float(worst_row['pnl_pct']):.1f}%)"

    return {
        "period": f"{period_start.strftime('%Y-%m-%d')} to {now.strftime('%Y-%m-%d')}",
        "total_trades": total_trades,
        "buys": buys,
        "sells": sells,
        "closed_trades": closed_count,
        "win_rate": f"{win_rate:.1f}%",
        "realized_pnl": f"${realized_pnl:.2f}",
        "unrealized_pnl": f"${unrealized_pnl:.2f}",
        "total_pnl": f"${total_pnl:.2f}",
        "roi": f"{roi_pct:.2f}%",
        "volume": f"${volume:.2f}",
        "open_positions": open_positions,
        "positions_value": f"${positions_value:.2f}",
        "portfolio_value": f"${portfolio_value:.2f}",
        "total_signals": total_signals,
        "buy_signals": buy_signals,
        "best_trade": best_trade,
        "worst_trade": worst_trade,
        "timestamp": now.isoformat(),
    }


def _save_review_report(db: DatabaseManager, report: dict):
    """Save review report to a review_reports table (creates if not exists)."""
    import json
    create_query = """
    CREATE TABLE IF NOT EXISTS review_reports (
        id SERIAL PRIMARY KEY,
        period VARCHAR(100),
        report_data JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """
    db.execute_command(create_query)
    insert_query = """
    INSERT INTO review_reports (period, report_data)
    VALUES (:period, :report_data)
    """
    db.execute_command(insert_query, {
        'period': report['period'],
        'report_data': json.dumps(report),
    })


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown"""
    logger.info("🛑 CRYPTONITA TRADING BOT API - SHUTTING DOWN")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower()
    )
