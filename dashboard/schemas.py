"""
Pydantic schemas for API request/response models.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


# ── Auth ────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# ── Trades ──────────────────────────────────────────────────────────────

class TradeResponse(BaseModel):
    id: int
    symbol: str
    order_type: str
    strategy: str
    status: str
    entry_price: float
    exit_price: Optional[float] = None
    stop_loss: float
    take_profit: float
    lot_size: float
    risk_percent: float
    signal_confidence: Optional[float] = None
    pnl: Optional[float] = None
    pnl_pips: Optional[float] = None
    market_regime: Optional[str] = None
    opened_at: datetime
    closed_at: Optional[datetime] = None


# ── Performance ─────────────────────────────────────────────────────────

class PerformanceSummary(BaseModel):
    total_trades: int
    wins: int = 0
    losses: int = 0
    win_rate: float
    total_pnl: float
    avg_pnl: float
    max_drawdown: float


# ── Account ─────────────────────────────────────────────────────────────

class AccountInfo(BaseModel):
    balance: float
    equity: float
    margin: Optional[float] = None
    free_margin: Optional[float] = None
    margin_level: Optional[float] = None
    open_positions: int = 0
    daily_pnl: Optional[float] = None


# ── Strategies ──────────────────────────────────────────────────────────

class StrategyInfo(BaseModel):
    name: str
    type: str
    is_active: bool = True
    parameters: Dict[str, Any] = {}


class SignalResponse(BaseModel):
    symbol: str
    signal_type: str
    strategy: str
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    risk_reward_ratio: float
    timeframe: str
    market_regime: str
    timestamp: datetime


# ── System ──────────────────────────────────────────────────────────────

class SystemStatus(BaseModel):
    status: str
    uptime_seconds: float
    active_pairs: List[str]
    open_trades: int
    last_scan: Optional[datetime] = None
    strategies_active: int = 0
    ml_models_loaded: int = 0


class LogEntry(BaseModel):
    id: int
    level: str
    module: str
    message: str
    details: Optional[str] = None
    created_at: datetime


# ── Bot Control ─────────────────────────────────────────────────────────

class BotControlRequest(BaseModel):
    action: str  # "start", "stop", "pause"


class PairSelectionRequest(BaseModel):
    pairs: List[str]


class NewsManualToggleRequest(BaseModel):
    enabled: bool


class NewsConfigResponse(BaseModel):
    enable_news_filter: bool
    enable_news_auto_update: bool
    enable_news_events_utc: bool
    news_auto_refresh_minutes: int
    news_events_url: str
    manual_events_count: int = 0


# ── Backtest ────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    strategy: str
    symbol: str
    timeframe: str = "H1"
    start_date: Optional[str] = None
    end_date: Optional[str] = None


class BacktestResponse(BaseModel):
    strategy: str
    symbol: str
    timeframe: str
    total_trades: int
    win_rate: float
    total_pnl: float
    sharpe_ratio: float
    max_drawdown: float
    profit_factor: float


# ── Meta-Strategy ───────────────────────────────────────────────────────

class StrategyScoreResponse(BaseModel):
    strategy: str
    symbol: str = "ALL"
    regime: str = "ALL"
    total_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    sharpe: float = 0.0
    avg_pnl: float = 0.0
    total_pnl: float = 0.0
    avg_confidence: float = 0.0
    composite_score: float = 0.0
    data_quality: float = 0.0


class MetaDecisionResponse(BaseModel):
    symbol: str
    regime: str
    sessions: List[str] = []
    strategy_weights: Dict[str, float] = {}
    selected_strategies: List[str] = []
    excluded_strategies: List[str] = []
    reasoning: List[str] = []
    confidence: float = 0.0


class SessionInfoResponse(BaseModel):
    active_sessions: List[str] = []
    is_overlap: bool = False
    overlap_sessions: List[str] = []
    volatility_expectation: str = "LOW"
    best_pairs: List[str] = []


class RegimeHistoryEntry(BaseModel):
    regime: str
    symbol: str
    timestamp: str


class StrategyPerformanceResponse(BaseModel):
    strategy: str
    symbol: str = "ALL"
    regime: str = "ALL"
    total_trades: int = 0
    win_rate: float = 0.0
    total_pnl: float = 0.0
    avg_pnl: float = 0.0
    profit_factor: float = 0.0
    avg_confidence: float = 0.0
    sharpe: float = 0.0


class DashboardAnalyticsResponse(BaseModel):
    equity_curve: List[Dict[str, Any]] = []
    win_rate: float = 0.0
    drawdown: float = 0.0
    trade_heatmap: Dict[str, int] = {}
    strategy_performance: List[StrategyPerformanceResponse] = []
    latency: Dict[str, float] = {}
    strategy_evolution: Dict[str, Any] = {}
