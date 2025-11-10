"""
Bot Control Routes
"""
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger

from config import settings
from src.api.auth import get_current_user
from src.api.schemas.controls import (
    StartBotRequest, StopBotRequest, ManualTradeRequest, BotControlResponse
)
from src.data.storage.db_manager import DatabaseManager

router = APIRouter(prefix="/controls", tags=["Bot Controls"])

# Database instance
db = DatabaseManager(settings.get_database_url())


@router.post("/start", response_model=BotControlResponse)
async def start_bot(
    request: StartBotRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Start the trading bot
    """
    try:
        # Update bot status to 'running'
        db.update_bot_status(
            status='running',
            total_signals=0,
            buy_signals=0,
            cycle_number=1,
            last_error=None
        )

        logger.info(f"🚀 Bot started in {request.mode} mode by {current_user['username']}")

        return BotControlResponse(
            success=True,
            message=f"Bot started in {request.mode} mode",
            status="running"
        )
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop", response_model=BotControlResponse)
async def stop_bot(
    request: StopBotRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Stop the trading bot
    """
    try:
        # Update bot status to 'stopped'
        db.update_bot_status(
            status='stopped',
            total_signals=0,
            buy_signals=0,
            cycle_number=0,
            last_error=request.reason
        )

        logger.info(f"🛑 Bot stopped by {current_user['username']}: {request.reason}")

        return BotControlResponse(
            success=True,
            message="Bot stopped successfully",
            status="stopped"
        )
    except Exception as e:
        logger.error(f"❌ Failed to stop bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause", response_model=BotControlResponse)
async def pause_bot(current_user: dict = Depends(get_current_user)):
    """
    Pause the trading bot
    """
    try:
        # Update bot status to 'idle'
        db.update_bot_status(
            status='idle',
            total_signals=0,
            buy_signals=0,
            cycle_number=0,
            last_error=None
        )

        logger.info(f"⏸️ Bot paused by {current_user['username']}")

        return BotControlResponse(
            success=True,
            message="Bot paused",
            status="idle"
        )
    except Exception as e:
        logger.error(f"❌ Failed to pause bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual-trade", response_model=BotControlResponse)
async def execute_manual_trade(
    request: ManualTradeRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Execute a manual trade (requires manual approval to be enabled)
    """
    try:
        # This would integrate with the actual trading bot
        # For now, just log the request

        logger.info(
            f"📝 Manual trade request by {current_user['username']}: "
            f"{request.action} {request.quantity} {request.ticker} @ {request.order_type}"
        )

        # In production, this would:
        # 1. Validate the trade
        # 2. Execute on Binance
        # 3. Log to database
        # 4. Update positions

        return BotControlResponse(
            success=True,
            message=f"Manual trade queued: {request.action} {request.quantity} {request.ticker}"
        )

    except Exception as e:
        logger.error(f"❌ Failed to execute manual trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_bot_config(current_user: dict = Depends(get_current_user)):
    """
    Get current bot configuration
    """
    return {
        "trading_mode": settings.TRADING_MODE,
        "max_positions": settings.MAX_POSITIONS,
        "prediction_threshold": settings.PREDICTION_THRESHOLD,
        "position_size_pct": settings.POSITION_SIZE_PCT,
        "take_profit_pct": settings.TAKE_PROFIT_PCT,
        "stop_loss_pct": settings.STOP_LOSS_PCT,
        "max_daily_loss_usd": settings.MAX_DAILY_LOSS_USD,
        "require_manual_approval": settings.REQUIRE_MANUAL_APPROVAL,
        "tickers_count": len(settings.TICKERS)
    }
