"""
Dashboard Schemas
"""
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class DashboardStats(BaseModel):
    total_trades: int
    executed_trades: int
    active_positions: int
    portfolio_value: float
    total_pnl: float
    win_rate: float
    timestamp: str


class Position(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
    current_price: Optional[float]
    total_value: Optional[float]
    pnl: Optional[float]
    pnl_percentage: Optional[float]
    last_update: datetime


class Signal(BaseModel):
    id: int
    ticker: str
    signal_type: str
    probability: float
    timestamp: datetime


class Trade(BaseModel):
    id: int
    signal_id: Optional[int]
    ticker: str
    action: str
    quantity: float
    price: float
    total_value: float
    status: str
    timestamp: datetime
    executed_at: Optional[datetime]
    error_message: Optional[str]


class BotStatus(BaseModel):
    status: str
    total_signals: int
    buy_signals: int
    cycle_number: int
    last_error: Optional[str]
    last_update: datetime


class PerformanceMetric(BaseModel):
    date: str
    total_trades: int
    successful_trades: int
    failed_trades: int
    total_volume: float
    total_pnl: float
    win_rate: float
    sharpe_ratio: Optional[float]
    max_drawdown: Optional[float]
    portfolio_value: float
