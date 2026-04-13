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
                <p>ML-Powered Cryptocurrency Trading System V4</p>
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
    logger.info(f"V4 Model: {getattr(settings, 'USE_V4_MODEL', False)}")
    logger.info(f"Auto-Train: {getattr(settings, 'AUTO_TRAIN_ENABLED', False)}")
    logger.info(f"API running on: http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info("=" * 60)

    # Self-ping to keep Render alive (every 10 minutes)
    if settings.ENVIRONMENT == "production":
        asyncio.create_task(_keep_alive_loop())

    # Auto-start bot and launch watchdog
    asyncio.create_task(_auto_start_bot())
    asyncio.create_task(_bot_watchdog_loop())


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
