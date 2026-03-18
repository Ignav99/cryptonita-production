#!/usr/bin/env python3
"""
CRYPTONITA API - LAUNCHER
==========================
Launch the FastAPI dashboard server
"""

import sys
from pathlib import Path
import uvicorn
from loguru import logger

# Add project root to path
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from config import settings


def main():
    """Launch API server"""
    logger.info("=" * 70)
    logger.info("🚀 CRYPTONITA API SERVER")
    logger.info("=" * 70)
    logger.info(f"Environment: {settings.ENVIRONMENT}")
    logger.info(f"Trading Mode: {settings.TRADING_MODE.upper()}")
    logger.info(f"API URL: http://{settings.API_HOST}:{settings.API_PORT}")
    logger.info(f"Docs: http://{settings.API_HOST}:{settings.API_PORT}/api/docs")
    logger.info("=" * 70)

    # Run uvicorn server
    uvicorn.run(
        "src.api.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        log_level=settings.LOG_LEVEL.lower(),
        access_log=True
    )


if __name__ == "__main__":
    main()
