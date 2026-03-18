"""
Bot Control Schemas
"""
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime


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


class TrainingRunResponse(BaseModel):
    id: int
    version: int
    status: str
    mode: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metrics: Dict[str, Any] = {}
    comparison: Dict[str, Any] = {}
    error_message: Optional[str] = None
    promoted: bool = False


class TrainingStatusResponse(BaseModel):
    active_model_version: Optional[int] = None
    has_active_model: bool = False
    is_training: bool = False
    auto_train_enabled: bool = False
    auto_train_interval_days: int = 7
    training_history: List[TrainingRunResponse] = []
