"""
Bot Control Schemas
"""
from pydantic import BaseModel
from typing import Optional


class StartBotRequest(BaseModel):
    mode: str = "auto"  # auto or manual


class StopBotRequest(BaseModel):
    reason: Optional[str] = None


class ManualTradeRequest(BaseModel):
    ticker: str
    action: str  # BUY or SELL
    quantity: float
    order_type: str = "market"  # market or limit
    price: Optional[float] = None


class BotControlResponse(BaseModel):
    success: bool
    message: str
    status: Optional[str] = None
