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
from src.bot.bot_manager import BotManager
from src.services.binance_service import BinanceService

router = APIRouter(prefix="/controls", tags=["Bot Controls"])

# Database instance
db = DatabaseManager(settings.get_database_url())

# Bot process manager
bot_manager = BotManager()


@router.post("/start", response_model=BotControlResponse)
async def start_bot(
    request: StartBotRequest,
    current_user: dict = Depends(get_current_user)
):
    """Start the trading bot"""
    try:
        result = bot_manager.start(mode=request.mode)

        if result["success"]:
            db.update_bot_status(
                status='running',
                total_signals=0,
                buy_signals=0,
                cycle_number=0,
                last_error=None
            )

            logger.info(f"Bot started in {request.mode} mode by {current_user['username']} (PID: {result['pid']})")

            return BotControlResponse(
                success=True,
                message=result["message"],
                status="running"
            )
        else:
            return BotControlResponse(
                success=False,
                message=result["message"],
                status="stopped"
            )

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stop", response_model=BotControlResponse)
async def stop_bot(
    request: StopBotRequest,
    current_user: dict = Depends(get_current_user)
):
    """Stop the trading bot"""
    try:
        result = bot_manager.stop(reason=request.reason or "Manual stop")

        db.update_bot_status(
            status='stopped',
            total_signals=0,
            buy_signals=0,
            cycle_number=0,
            last_error=request.reason if not result["success"] else None
        )

        logger.info(f"Bot stopped by {current_user['username']}: {request.reason}")

        return BotControlResponse(
            success=result["success"],
            message=result["message"],
            status="stopped"
        )
    except Exception as e:
        logger.error(f"Failed to stop bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause", response_model=BotControlResponse)
async def pause_bot(current_user: dict = Depends(get_current_user)):
    """
    Pause the trading bot.
    Sets DB status to 'paused'. The bot checks this status before each scan
    and skips market scanning while paused (but continues monitoring positions).
    """
    try:
        if not bot_manager.is_running():
            return BotControlResponse(
                success=False,
                message="Bot is not running",
                status="stopped"
            )

        db.update_bot_status(
            status='paused',
            total_signals=0,
            buy_signals=0,
            cycle_number=0,
            last_error=None
        )

        logger.info(f"Bot paused by {current_user['username']}")

        return BotControlResponse(
            success=True,
            message="Bot paused - position monitoring continues, new scans suspended",
            status="paused"
        )
    except Exception as e:
        logger.error(f"Failed to pause bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/resume", response_model=BotControlResponse)
async def resume_bot(current_user: dict = Depends(get_current_user)):
    """Resume the bot from paused state"""
    try:
        if not bot_manager.is_running():
            return BotControlResponse(
                success=False,
                message="Bot is not running",
                status="stopped"
            )

        db.update_bot_status(
            status='running',
            total_signals=0,
            buy_signals=0,
            cycle_number=0,
            last_error=None
        )

        logger.info(f"Bot resumed by {current_user['username']}")

        return BotControlResponse(
            success=True,
            message="Bot resumed - market scanning active",
            status="running"
        )
    except Exception as e:
        logger.error(f"Failed to resume bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual-trade", response_model=BotControlResponse)
async def execute_manual_trade(
    request: ManualTradeRequest,
    current_user: dict = Depends(get_current_user)
):
    """Execute a manual trade on Binance"""
    try:
        binance = BinanceService()

        # Validate ticker
        symbol_info = binance.get_symbol_info(request.ticker)
        if not symbol_info:
            return BotControlResponse(
                success=False,
                message=f"Invalid ticker: {request.ticker}"
            )

        # Round quantity
        quantity = binance.round_quantity(request.ticker, request.quantity)
        if quantity <= 0:
            return BotControlResponse(
                success=False,
                message=f"Quantity too small after rounding for {request.ticker}"
            )

        # Execute order
        order = None
        if request.action.upper() == "BUY":
            if request.order_type == "market":
                order = binance.create_market_buy_order(request.ticker, quantity)
            elif request.order_type == "limit" and request.price:
                price = binance.round_price(request.ticker, request.price)
                if price:
                    order = binance.create_limit_buy_order(request.ticker, quantity, price)
        elif request.action.upper() == "SELL":
            if request.order_type == "market":
                order = binance.create_market_sell_order(request.ticker, quantity)

        if order is None:
            return BotControlResponse(
                success=False,
                message=f"Order execution failed for {request.ticker}"
            )

        # Get executed price
        fills = order.get('fills', [])
        if fills:
            total_qty = sum(float(f['qty']) for f in fills)
            total_cost = sum(float(f['price']) * float(f['qty']) for f in fills)
            executed_price = total_cost / total_qty if total_qty > 0 else 0
        else:
            executed_price = float(order.get('price', 0))

        executed_qty = float(order['executedQty'])

        # Log to database
        db.save_trade(
            signal_id=0,
            ticker=request.ticker,
            action=request.action.upper(),
            quantity=executed_qty,
            price=executed_price,
            total_value=executed_price * executed_qty,
            status='executed'
        )

        logger.info(
            f"Manual trade by {current_user['username']}: "
            f"{request.action} {executed_qty} {request.ticker} @ ${executed_price:.2f}"
        )

        return BotControlResponse(
            success=True,
            message=f"Executed: {request.action} {executed_qty} {request.ticker} @ ${executed_price:.2f}"
        )

    except Exception as e:
        logger.error(f"Failed to execute manual trade: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/config")
async def get_bot_config(current_user: dict = Depends(get_current_user)):
    """Get current bot configuration"""
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


@router.get("/process-status")
async def get_process_status(current_user: dict = Depends(get_current_user)):
    """Get bot process status (PID, CPU, Memory, Uptime)"""
    try:
        status = bot_manager.get_status()
        return status
    except Exception as e:
        logger.error(f"Failed to get process status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/restart", response_model=BotControlResponse)
async def restart_bot(
    request: StartBotRequest,
    current_user: dict = Depends(get_current_user)
):
    """Restart the trading bot"""
    try:
        result = await bot_manager.async_restart(mode=request.mode)

        if result["success"]:
            db.update_bot_status(
                status='running',
                total_signals=0,
                buy_signals=0,
                cycle_number=0,
                last_error=None
            )

        logger.info(f"Bot restarted by {current_user['username']}")

        return BotControlResponse(
            success=result["success"],
            message=result["message"],
            status="running" if result["success"] else "stopped"
        )
    except Exception as e:
        logger.error(f"Failed to restart bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))
