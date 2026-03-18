"""
SQLAlchemy models for the trading system.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Integer, Float, String, DateTime, Boolean, Text, Index,
    Enum as SAEnum,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    order_type = Column(String(10), nullable=False)  # BUY / SELL
    strategy = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="OPEN", index=True)

    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    lot_size = Column(Float, nullable=False)

    risk_percent = Column(Float, nullable=False)
    signal_confidence = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    pnl_pips = Column(Float, nullable=True)

    broker_ticket = Column(String(50), nullable=True)
    market_regime = Column(String(30), nullable=True)

    opened_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_trades_symbol_status", "symbol", "status"),
    )


class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)
    timestamp = Column(DateTime, nullable=False, index=True)

    __table_args__ = (
        Index("ix_market_data_sym_tf_ts", "symbol", "timeframe", "timestamp", unique=True),
    )


class StrategyResult(Base):
    __tablename__ = "strategy_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy = Column(String(50), nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    signal = Column(String(10), nullable=False)
    confidence = Column(Float, nullable=False)
    parameters = Column(Text, nullable=True)  # JSON string
    indicators = Column(Text, nullable=True)   # JSON string
    market_regime = Column(String(30), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    metric_type = Column(String(50), nullable=False, index=True)
    strategy = Column(String(50), nullable=True)
    symbol = Column(String(20), nullable=True)
    value = Column(Float, nullable=False)
    details = Column(Text, nullable=True)  # JSON string
    period_start = Column(DateTime, nullable=True)
    period_end = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class MLModelRecord(Base):
    __tablename__ = "ml_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)
    model_type = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=True)
    accuracy = Column(Float, nullable=True)
    precision_score = Column(Float, nullable=True)
    recall_score = Column(Float, nullable=True)
    f1_score = Column(Float, nullable=True)
    parameters = Column(Text, nullable=True)    # JSON string
    file_path = Column(String(255), nullable=True)
    trained_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    is_active = Column(Boolean, default=False)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    level = Column(String(10), nullable=False, index=True)
    module = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class AccountSnapshot(Base):
    __tablename__ = "account_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    balance = Column(Float, nullable=False)
    equity = Column(Float, nullable=False)
    margin = Column(Float, nullable=True)
    free_margin = Column(Float, nullable=True)
    margin_level = Column(Float, nullable=True)
    open_positions = Column(Integer, default=0)
    daily_pnl = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
