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
if FRONTEND_DIST.exists() and (FRONTEND_DIST / "assets").exists():
    try:
        app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
        app.mount("/static", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="static")
        logger.info(f"✅ Frontend assets mounted from {FRONTEND_DIST / 'assets'}")
    except Exception as e:
        logger.warning(f"⚠️ Could not mount frontend assets: {e}")


@app.get("/", response_class=HTMLResponse)
async def root():
    """
    Serve frontend dashboard HTML
    """
    # Try to serve built frontend first
    if index_file.exists():
        # Read and serve the HTML, replacing /assets/ with /static/ if needed
        html_content = index_file.read_text()
        return HTMLResponse(content=html_content)

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
                <p>ML-Powered Cryptocurrency Trading System V3</p>
                <p>Model: XGBoost | Features: 42 | Threshold: 0.60</p>
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
    logger.info("=" * 60)
    logger.info("🚀 CRYPTONITA TRADING BOT API - STARTING")
    logger.info(f"Version: {settings.APP_VERSION}")
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Trading Mode: {settings.TRADING_MODE}")
    logger.info(f"API running on: http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info("=" * 60)


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
