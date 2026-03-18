"""
Database repository — CRUD operations for all models.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, List, Optional

from sqlalchemy import select, func, update, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import (
    Trade, MarketData, StrategyResult, PerformanceMetric,
    MLModelRecord, SystemLog, AccountSnapshot,
)


# ── Trades ──────────────────────────────────────────────────────────────────

async def create_trade(session: AsyncSession, **kwargs) -> Trade:
    trade = Trade(**kwargs)
    session.add(trade)
    await session.commit()
    await session.refresh(trade)
    return trade


async def update_trade(session: AsyncSession, trade_id: int, **kwargs) -> Optional[Trade]:
    stmt = update(Trade).where(Trade.id == trade_id).values(**kwargs)
    await session.execute(stmt)
    await session.commit()
    return await session.get(Trade, trade_id)


async def get_open_trades(session: AsyncSession, symbol: str | None = None) -> List[Trade]:
    stmt = select(Trade).where(Trade.status == "OPEN")
    if symbol:
        stmt = stmt.where(Trade.symbol == symbol)
    result = await session.execute(stmt.order_by(desc(Trade.opened_at)))
    return list(result.scalars().all())


async def get_trade_history(session: AsyncSession, limit: int = 100,
                            symbol: str | None = None) -> List[Trade]:
    stmt = select(Trade)
    if symbol:
        stmt = stmt.where(Trade.symbol == symbol)
    result = await session.execute(stmt.order_by(desc(Trade.created_at)).limit(limit))
    return list(result.scalars().all())


async def get_daily_pnl(session: AsyncSession) -> float:
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stmt = select(func.coalesce(func.sum(Trade.pnl), 0.0)).where(
        and_(Trade.closed_at >= today, Trade.status == "CLOSED")
    )
    result = await session.execute(stmt)
    return float(result.scalar())


async def count_open_trades(session: AsyncSession) -> int:
    stmt = select(func.count(Trade.id)).where(Trade.status == "OPEN")
    result = await session.execute(stmt)
    return int(result.scalar())


# ── Market Data ─────────────────────────────────────────────────────────────

async def store_candles(session: AsyncSession, candles: List[dict]) -> int:
    """Bulk upsert candles. Returns number inserted."""
    if not candles:
        return 0

    # Batch lookup: get all existing timestamps for this symbol/timeframe combo
    # Group candles by (symbol, timeframe) to do batch queries
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for c in candles:
        groups[(c["symbol"], c["timeframe"])].append(c)

    count = 0
    for (symbol, timeframe), group in groups.items():
        timestamps = [c["timestamp"] for c in group]
        stmt = select(MarketData.timestamp).where(
            and_(
                MarketData.symbol == symbol,
                MarketData.timeframe == timeframe,
                MarketData.timestamp.in_(timestamps),
            )
        )
        result = await session.execute(stmt)
        existing_ts = {row[0] for row in result.all()}

        for c in group:
            if c["timestamp"] not in existing_ts:
                session.add(MarketData(**c))
                count += 1

    if count > 0:
        await session.commit()
    return count


async def get_candles(session: AsyncSession, symbol: str, timeframe: str,
                      limit: int = 500) -> List[MarketData]:
    stmt = (
        select(MarketData)
        .where(and_(MarketData.symbol == symbol, MarketData.timeframe == timeframe))
        .order_by(desc(MarketData.timestamp))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(reversed(result.scalars().all()))


# ── Strategy Results ────────────────────────────────────────────────────────

async def save_strategy_result(session: AsyncSession, **kwargs) -> StrategyResult:
    result = StrategyResult(**kwargs)
    session.add(result)
    await session.commit()
    return result


# ── Performance ─────────────────────────────────────────────────────────────

async def save_performance_metric(session: AsyncSession, **kwargs) -> PerformanceMetric:
    metric = PerformanceMetric(**kwargs)
    session.add(metric)
    await session.commit()
    return metric


async def get_performance_summary(session: AsyncSession) -> dict:
    """Overall performance summary."""
    closed = select(Trade).where(Trade.status == "CLOSED")
    result = await session.execute(closed)
    trades = list(result.scalars().all())
    if not trades:
        return {"total_trades": 0, "win_rate": 0, "total_pnl": 0,
                "avg_pnl": 0, "max_drawdown": 0}

    wins = [t for t in trades if (t.pnl or 0) > 0]
    pnls = [t.pnl or 0.0 for t in trades]
    cumulative = []
    running = 0
    for p in pnls:
        running += p
        cumulative.append(running)
    peak = cumulative[0]
    max_dd = 0.0
    for val in cumulative:
        if val > peak:
            peak = val
        if peak > 0:
            dd = (peak - val) / peak  # As percentage of peak equity
        else:
            dd = 0.0
        if dd > max_dd:
            max_dd = dd

    return {
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(trades) - len(wins),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "total_pnl": sum(pnls),
        "avg_pnl": sum(pnls) / len(pnls),
        "max_drawdown": max_dd,
    }


# ── ML Models ──────────────────────────────────────────────────────────────

async def save_ml_model_record(session: AsyncSession, **kwargs) -> MLModelRecord:
    record = MLModelRecord(**kwargs)
    session.add(record)
    await session.commit()
    return record


async def get_active_ml_models(session: AsyncSession) -> List[MLModelRecord]:
    stmt = select(MLModelRecord).where(MLModelRecord.is_active == True)
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Logs ────────────────────────────────────────────────────────────────────

async def save_system_log(session: AsyncSession, level: str, module: str,
                          message: str, details: str | None = None) -> SystemLog:
    log = SystemLog(level=level, module=module, message=message, details=details)
    session.add(log)
    await session.commit()
    return log


async def get_recent_logs(session: AsyncSession, limit: int = 200,
                          level: str | None = None) -> List[SystemLog]:
    stmt = select(SystemLog)
    if level:
        stmt = stmt.where(SystemLog.level == level)
    result = await session.execute(stmt.order_by(desc(SystemLog.created_at)).limit(limit))
    return list(result.scalars().all())


# ── Account Snapshots ──────────────────────────────────────────────────────

async def save_account_snapshot(session: AsyncSession, **kwargs) -> AccountSnapshot:
    snap = AccountSnapshot(**kwargs)
    session.add(snap)
    await session.commit()
    return snap


async def get_latest_snapshot(session: AsyncSession) -> Optional[AccountSnapshot]:
    stmt = select(AccountSnapshot).order_by(desc(AccountSnapshot.created_at)).limit(1)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_recent_account_snapshots(
    session: AsyncSession, limit: int = 500
) -> List[AccountSnapshot]:
    stmt = (
        select(AccountSnapshot)
        .order_by(desc(AccountSnapshot.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


# ── Strategy Performance Queries ───────────────────────────────────────────

async def get_strategy_performance(
    session: AsyncSession,
    strategy: str | None = None,
    symbol: str | None = None,
    regime: str | None = None,
    days: int = 30,
) -> dict:
    """Get performance stats for a strategy filtered by symbol/regime/time window."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = select(Trade).where(
        and_(Trade.status == "CLOSED", Trade.closed_at >= cutoff)
    )
    if strategy:
        stmt = stmt.where(Trade.strategy == strategy)
    if symbol:
        stmt = stmt.where(Trade.symbol == symbol)
    if regime:
        stmt = stmt.where(Trade.market_regime == regime)

    result = await session.execute(stmt.order_by(desc(Trade.closed_at)))
    trades = list(result.scalars().all())

    if not trades:
        return {
            "strategy": strategy or "ALL",
            "symbol": symbol or "ALL",
            "regime": regime or "ALL",
            "total_trades": 0,
            "win_rate": 0.0,
            "total_pnl": 0.0,
            "avg_pnl": 0.0,
            "profit_factor": 0.0,
            "avg_confidence": 0.0,
            "sharpe": 0.0,
        }

    pnls = [t.pnl or 0.0 for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins) if wins else 0.0
    gross_loss = abs(sum(losses)) if losses else 0.0
    avg_conf = sum(t.signal_confidence or 0 for t in trades) / len(trades)

    import math
    mean_pnl = sum(pnls) / len(pnls)
    if len(pnls) > 1:
        variance = sum((p - mean_pnl) ** 2 for p in pnls) / (len(pnls) - 1)
        std_pnl = math.sqrt(variance) if variance > 0 else 1e-9
    else:
        std_pnl = 1e-9
    sharpe = mean_pnl / std_pnl if std_pnl > 0 else 0.0

    return {
        "strategy": strategy or "ALL",
        "symbol": symbol or "ALL",
        "regime": regime or "ALL",
        "total_trades": len(trades),
        "win_rate": len(wins) / len(trades),
        "total_pnl": sum(pnls),
        "avg_pnl": mean_pnl,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else 999.0,
        "avg_confidence": avg_conf,
        "sharpe": sharpe,
    }


async def get_all_strategy_performances(
    session: AsyncSession, days: int = 30
) -> List[dict]:
    """Get performance for every strategy that has closed trades."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(Trade.strategy)
        .where(and_(Trade.status == "CLOSED", Trade.closed_at >= cutoff))
        .distinct()
    )
    result = await session.execute(stmt)
    strategies = [row[0] for row in result.all()]

    perfs = []
    for strat in strategies:
        perf = await get_strategy_performance(session, strategy=strat, days=days)
        perfs.append(perf)
    return perfs


async def get_strategy_performance_by_regime(
    session: AsyncSession, strategy: str, days: int = 60
) -> List[dict]:
    """Get strategy performance broken down by market regime."""
    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(Trade.market_regime)
        .where(and_(
            Trade.status == "CLOSED",
            Trade.strategy == strategy,
            Trade.closed_at >= cutoff,
        ))
        .distinct()
    )
    result = await session.execute(stmt)
    regimes = [row[0] for row in result.all() if row[0]]

    perfs = []
    for regime in regimes:
        perf = await get_strategy_performance(
            session, strategy=strategy, regime=regime, days=days
        )
        perfs.append(perf)
    return perfs


async def get_regime_history(session: AsyncSession, limit: int = 100) -> List[dict]:
    """Get recent regime detections from strategy results."""
    stmt = (
        select(
            StrategyResult.market_regime,
            StrategyResult.symbol,
            StrategyResult.created_at,
        )
        .where(StrategyResult.market_regime.isnot(None))
        .order_by(desc(StrategyResult.created_at))
        .limit(limit)
    )
    result = await session.execute(stmt)
    return [
        {"regime": r[0], "symbol": r[1], "timestamp": r[2].isoformat()}
        for r in result.all()
    ]
