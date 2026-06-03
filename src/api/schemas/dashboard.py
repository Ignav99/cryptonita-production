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
    usdt_balance: float
    positions_value: float
    total_pnl: float
    total_pnl_pct: float
    win_rate: float
    realized_pnl: Optional[float] = 0.0
    unrealized_pnl: Optional[float] = 0.0
    today_pnl: Optional[float] = 0.0
    today_pnl_pct: Optional[float] = 0.0
    timestamp: str


class Position(BaseModel):
    ticker: str
    quantity: float
    avg_buy_price: float
    current_price: Optional[float]
    total_value: Optional[float]
    pnl: Optional[float]
    pnl_percentage: Optional[float]
    remaining_quantity: Optional[float]
    stop_loss: Optional[float]
    tp1: Optional[float]
    tp1_hit: Optional[bool]
    tp2: Optional[float]
    tp2_hit: Optional[bool]
    tp3: Optional[float]
    tp3_hit: Optional[bool]
    entry_time: Optional[datetime]
    last_update: datetime


class Signal(BaseModel):
    id: int
    ticker: str
    signal_type: str
    probability: float
    timestamp: datetime


class Trade(BaseModel):
    id: int
    signal_id: Optional[int] = None
    ticker: str
    action: str
    quantity: float
    price: float
    total_value: float
    status: str
    timestamp: datetime
    probability: Optional[float] = None
    exit_reason: Optional[str] = None
    executed_at: Optional[datetime] = None
    error_message: Optional[str] = None


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


class SignalPerformance(BaseModel):
    ticker: str
    signal_date: str
    probability: float
    entry_price: float
    max_price: float
    max_return_pct: float
    hit_20pct: bool
    days_available: int


class SignalDetail(BaseModel):
    id: int
    ticker: str
    display_name: str
    signal_type: str
    probability: float
    threshold: float
    distance_to_threshold: float
    tier: int
    timestamp: datetime


class CoinTrendPoint(BaseModel):
    probability: float
    signal_type: str
    timestamp: datetime


class CoinSummary(BaseModel):
    ticker: str
    display_name: str
    latest_signal_type: str
    latest_probability: float
    threshold: float
    tier: int
    distance_to_threshold: float
    probability_change: Optional[float] = None
    trend_direction: Optional[str] = None
    signal_count_7d: int = 0
    buy_count_7d: int = 0
    last_scan: Optional[datetime] = None
    latest_rejection_reason: Optional[str] = None


class CoinTrend(BaseModel):
    ticker: str
    display_name: str
    threshold: float
    data_points: List[CoinTrendPoint]


class SignalsSummaryStats(BaseModel):
    total_coins_scanned: int
    buy_signals_count: int      # LONG signals (V5) or BUY (V4)
    short_signals_count: int = 0  # SHORT signals — V5 only
    hold_signals_count: int
    near_threshold_count: int
    avg_probability: float
    highest_probability_ticker: Optional[str] = None
    highest_probability_value: Optional[float] = None
    last_scan_time: Optional[datetime] = None


class ThresholdProximity(BaseModel):
    ticker: str
    display_name: str
    probability: float
    threshold: float
    distance_pct: float
    tier: int
    signal_type: str


class SignalAnalysisSummary(BaseModel):
    total_signals: int
    hit_rate: float
    avg_return: float
    mature_signals: int
    mature_hit_rate: float
    mature_avg_return: float
    by_probability: list
    recent_signals: list
    best_signals: list
    worst_signals: list
