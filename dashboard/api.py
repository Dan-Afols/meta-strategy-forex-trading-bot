"""
FastAPI Dashboard API — exposes trading system data and controls.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordRequestForm

from config.settings import get_settings
from dashboard.auth import (
    create_access_token, get_current_user, get_password_hash, verify_password,
)
from dashboard.schemas import (
    AccountInfo, BacktestRequest, BacktestResponse, BotControlRequest,
    DashboardAnalyticsResponse,
    LogEntry, LoginRequest, MetaDecisionResponse, PairSelectionRequest,
    NewsConfigResponse, NewsManualToggleRequest,
    PerformanceSummary, RegimeHistoryEntry, SessionInfoResponse,
    SignalResponse, StrategyInfo, StrategyPerformanceResponse,
    SystemStatus, TokenResponse, TradeResponse,
)
from database.session import get_session
from database import repository as repo
from utils.logging_config import get_logger

logger = get_logger("dashboard_api")
router = APIRouter(prefix="/api")

_settings = get_settings()
_start_time = time.time()

# Shared state references (set by main.py)
_bot_state = {
    "running": False,
    "last_scan": None,
    "active_pairs": [],
    "strategies_active": 0,
    "ml_models_loaded": 0,
}


# Bot reference (set by main.py lifespan)
_bot_ref = None


def set_bot_reference(bot) -> None:
    global _bot_ref
    _bot_ref = bot


def set_bot_state(key: str, value) -> None:
    _bot_state[key] = value


def get_bot_state() -> dict:
    return _bot_state.copy()


# ════════════════════════════════════════════════════════════════════════
# Auth
# ════════════════════════════════════════════════════════════════════════

@router.post("/auth/login", response_model=TokenResponse)
async def login(form: OAuth2PasswordRequestForm = Depends()):
    import hmac
    if not hmac.compare_digest(form.username, _settings.dashboard_username):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not hmac.compare_digest(form.password, _settings.dashboard_password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token(data={"sub": form.username})
    return TokenResponse(access_token=token)


# ════════════════════════════════════════════════════════════════════════
# Trades
# ════════════════════════════════════════════════════════════════════════

@router.get("/trades", response_model=List[TradeResponse])
async def list_trades(
    status_filter: Optional[str] = Query(None, alias="status"),
    symbol: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    _user: str = Depends(get_current_user),
):
    session = await get_session()
    try:
        if status_filter == "OPEN":
            trades = await repo.get_open_trades(session, symbol)
        else:
            trades = await repo.get_trade_history(session, limit, symbol)
        return [_trade_to_response(t) for t in trades]
    finally:
        await session.close()


@router.get("/positions", response_model=List[TradeResponse])
async def open_positions(_user: str = Depends(get_current_user)):
    session = await get_session()
    try:
        trades = await repo.get_open_trades(session)
        return [_trade_to_response(t) for t in trades]
    finally:
        await session.close()


# ════════════════════════════════════════════════════════════════════════
# Performance
# ════════════════════════════════════════════════════════════════════════

@router.get("/performance", response_model=PerformanceSummary)
async def performance_summary(_user: str = Depends(get_current_user)):
    session = await get_session()
    try:
        summary = await repo.get_performance_summary(session)
        return PerformanceSummary(**summary)
    finally:
        await session.close()


@router.get("/analytics", response_model=DashboardAnalyticsResponse)
async def dashboard_analytics(
    days: int = Query(30, ge=1, le=365),
    _user: str = Depends(get_current_user),
):
    session = await get_session()
    try:
        summary = await repo.get_performance_summary(session)
        snapshots = await repo.get_recent_account_snapshots(session, limit=500)
        perfs = await repo.get_all_strategy_performances(session, days=days)
        trades = await repo.get_trade_history(session, limit=1000)

        equity_curve = [
            {
                "timestamp": s.created_at.isoformat(),
                "balance": s.balance,
                "equity": s.equity,
            }
            for s in reversed(snapshots)
        ]

        # Trade heatmap by UTC hour
        heatmap = {f"{h:02d}": 0 for h in range(24)}
        for t in trades:
            ts = t.closed_at or t.opened_at
            if ts is None:
                continue
            heatmap[f"{ts.hour:02d}"] += 1

        latency = _bot_state.get("latency", {})
        evolution = _bot_state.get("strategy_evolution", {})

        return DashboardAnalyticsResponse(
            equity_curve=equity_curve,
            win_rate=summary.get("win_rate", 0.0),
            drawdown=summary.get("max_drawdown", 0.0),
            trade_heatmap=heatmap,
            strategy_performance=[StrategyPerformanceResponse(**p) for p in perfs],
            latency=latency,
            strategy_evolution=evolution,
        )
    finally:
        await session.close()


# ════════════════════════════════════════════════════════════════════════
# Account / Balance
# ════════════════════════════════════════════════════════════════════════

@router.get("/balance", response_model=AccountInfo)
async def account_balance(_user: str = Depends(get_current_user)):
    session = await get_session()
    try:
        snapshot = await repo.get_latest_snapshot(session)
        open_count = await repo.count_open_trades(session)
        daily_pnl = await repo.get_daily_pnl(session)
        if snapshot:
            return AccountInfo(
                balance=snapshot.balance,
                equity=snapshot.equity,
                margin=snapshot.margin,
                free_margin=snapshot.free_margin,
                margin_level=snapshot.margin_level,
                open_positions=open_count,
                daily_pnl=daily_pnl,
            )
        return AccountInfo(balance=0, equity=0, open_positions=open_count,
                           daily_pnl=daily_pnl)
    finally:
        await session.close()


@router.get("/account/live")
async def live_account(_user: str = Depends(get_current_user)):
    """Return live MT5 account data from in-memory bot state."""
    account = _bot_state.get("account")
    if not account:
        raise HTTPException(404, "No live account data available yet")
    return account


# ════════════════════════════════════════════════════════════════════════
# Strategies
# ════════════════════════════════════════════════════════════════════════

@router.get("/strategies", response_model=List[StrategyInfo])
async def list_strategies(_user: str = Depends(get_current_user)):
    from config.constants import DEFAULT_STRATEGY_PARAMS
    strategies = []
    for name, params in DEFAULT_STRATEGY_PARAMS.items():
        strategies.append(StrategyInfo(name=name, type=name, parameters=params))
    return strategies


# ════════════════════════════════════════════════════════════════════════
# Logs
# ════════════════════════════════════════════════════════════════════════

@router.get("/logs", response_model=List[LogEntry])
async def system_logs(
    level: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    _user: str = Depends(get_current_user),
):
    session = await get_session()
    try:
        logs = await repo.get_recent_logs(session, limit, level)
        return [LogEntry(
            id=log.id, level=log.level, module=log.module,
            message=log.message, details=log.details, created_at=log.created_at,
        ) for log in logs]
    finally:
        await session.close()


# ════════════════════════════════════════════════════════════════════════
# System Status & Control
# ════════════════════════════════════════════════════════════════════════

@router.get("/status", response_model=SystemStatus)
async def system_status(_user: str = Depends(get_current_user)):
    session = await get_session()
    try:
        open_count = await repo.count_open_trades(session)
        return SystemStatus(
            status="RUNNING" if _bot_state["running"] else "STOPPED",
            uptime_seconds=time.time() - _start_time,
            active_pairs=_bot_state["active_pairs"],
            open_trades=open_count,
            last_scan=_bot_state["last_scan"],
            strategies_active=_bot_state["strategies_active"],
            ml_models_loaded=_bot_state["ml_models_loaded"],
        )
    finally:
        await session.close()


@router.post("/control")
async def bot_control(req: BotControlRequest,
                      _user: str = Depends(get_current_user)):
    if req.action == "start":
        _bot_state["running"] = True
        if _bot_ref:
            _bot_ref._running = True
        return {"message": "Bot started"}
    elif req.action == "stop":
        _bot_state["running"] = False
        if _bot_ref:
            _bot_ref._running = False
        return {"message": "Bot stopped"}
    elif req.action == "pause":
        _bot_state["running"] = False
        if _bot_ref:
            _bot_ref._running = False
        return {"message": "Bot paused"}
    else:
        raise HTTPException(400, "Invalid action. Use: start, stop, pause")


@router.post("/pairs")
async def update_pairs(req: PairSelectionRequest,
                       _user: str = Depends(get_current_user)):
    _bot_state["active_pairs"] = req.pairs
    return {"message": f"Active pairs updated to {req.pairs}"}


@router.get("/news/config", response_model=NewsConfigResponse)
async def news_config(_user: str = Depends(get_current_user)):
    manual_count = 0
    if _bot_ref and getattr(_bot_ref, "news_filter", None):
        manual_count = len(getattr(_bot_ref.news_filter, "_events", []))

    return NewsConfigResponse(
        enable_news_filter=bool(_settings.enable_news_filter),
        enable_news_auto_update=bool(_settings.enable_news_auto_update),
        enable_news_events_utc=bool(_settings.enable_news_events_utc),
        news_auto_refresh_minutes=int(_settings.news_auto_refresh_minutes),
        news_events_url=str(_settings.news_events_url or ""),
        manual_events_count=manual_count,
    )


@router.post("/news/manual-source")
async def set_news_manual_source(
    req: NewsManualToggleRequest,
    _user: str = Depends(get_current_user),
):
    _settings.enable_news_events_utc = bool(req.enabled)

    if _bot_ref and getattr(_bot_ref, "news_filter", None):
        _bot_ref.news_filter.reload_events()
        await _bot_ref.news_filter.refresh_if_needed(force=True)

    logger.info("Dashboard toggled manual NEWS_EVENTS_UTC source",
                enabled=_settings.enable_news_events_utc)
    return {
        "ok": True,
        "enable_news_events_utc": _settings.enable_news_events_utc,
    }


# ════════════════════════════════════════════════════════════════════════
# Helpers
# ════════════════════════════════════════════════════════════════════════

def _trade_to_response(trade) -> TradeResponse:
    return TradeResponse(
        id=trade.id,
        symbol=trade.symbol,
        order_type=trade.order_type,
        strategy=trade.strategy,
        status=trade.status,
        entry_price=trade.entry_price,
        exit_price=trade.exit_price,
        stop_loss=trade.stop_loss,
        take_profit=trade.take_profit,
        lot_size=trade.lot_size,
        risk_percent=trade.risk_percent,
        signal_confidence=trade.signal_confidence,
        pnl=trade.pnl,
        pnl_pips=trade.pnl_pips,
        market_regime=trade.market_regime,
        opened_at=trade.opened_at,
        closed_at=trade.closed_at,
    )


# ════════════════════════════════════════════════════════════════════════
# Meta-Strategy Endpoints
# ════════════════════════════════════════════════════════════════════════

@router.get("/meta/decisions", response_model=List[MetaDecisionResponse])
async def meta_decisions(_user: str = Depends(get_current_user)):
    """Get the latest meta-strategy decisions for all analyzed symbols."""
    decisions = _bot_state.get("meta_decisions", {})
    return [MetaDecisionResponse(**d) for d in decisions.values()]


@router.get("/meta/decisions/{symbol}", response_model=MetaDecisionResponse)
async def meta_decision_for_symbol(symbol: str,
                                   _user: str = Depends(get_current_user)):
    """Get the meta-strategy decision for a specific symbol."""
    decisions = _bot_state.get("meta_decisions", {})
    if symbol not in decisions:
        raise HTTPException(404, f"No meta-strategy decision for {symbol}")
    return MetaDecisionResponse(**decisions[symbol])


@router.get("/meta/rankings", response_model=List[StrategyPerformanceResponse])
async def strategy_rankings(
    days: int = Query(30, ge=1, le=365),
    _user: str = Depends(get_current_user),
):
    """Get strategy performance rankings across all data."""
    session = await get_session()
    try:
        perfs = await repo.get_all_strategy_performances(session, days=days)
        return [StrategyPerformanceResponse(**p) for p in perfs]
    finally:
        await session.close()


@router.get("/meta/performance/{strategy}", response_model=List[StrategyPerformanceResponse])
async def strategy_performance_by_regime(
    strategy: str,
    days: int = Query(60, ge=1, le=365),
    _user: str = Depends(get_current_user),
):
    """Get a strategy's performance broken down by market regime."""
    session = await get_session()
    try:
        perfs = await repo.get_strategy_performance_by_regime(
            session, strategy=strategy, days=days
        )
        return [StrategyPerformanceResponse(**p) for p in perfs]
    finally:
        await session.close()


@router.get("/meta/session", response_model=SessionInfoResponse)
async def current_session(_user: str = Depends(get_current_user)):
    """Get the currently active Forex trading sessions."""
    from data.session_detector import SessionDetector
    detector = SessionDetector()
    info = detector.detect()
    return SessionInfoResponse(**info.to_dict())


@router.get("/meta/regimes", response_model=List[RegimeHistoryEntry])
async def regime_history(
    limit: int = Query(100, ge=1, le=500),
    _user: str = Depends(get_current_user),
):
    """Get recent market regime detections."""
    session = await get_session()
    try:
        history = await repo.get_regime_history(session, limit=limit)
        return [RegimeHistoryEntry(**h) for h in history]
    finally:
        await session.close()
