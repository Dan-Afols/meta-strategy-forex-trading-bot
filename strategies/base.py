"""
Base strategy class and signal data structures.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional

import pandas as pd

from config.constants import SignalType, StrategyType


@dataclass
class Signal:
    """Represents a trading signal produced by a strategy."""
    symbol: str
    signal_type: SignalType
    strategy: str
    strategy_type: StrategyType
    confidence: float  # 0 to 1
    entry_price: float
    stop_loss: float
    take_profit: float
    timeframe: str
    market_regime: str = ""
    indicators: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def risk_reward_ratio(self) -> float:
        risk = abs(self.entry_price - self.stop_loss)
        reward = abs(self.take_profit - self.entry_price)
        return reward / risk if risk > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "signal_type": self.signal_type.value,
            "strategy": self.strategy,
            "strategy_type": self.strategy_type.value,
            "confidence": round(self.confidence, 4),
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "timeframe": self.timeframe,
            "market_regime": self.market_regime,
            "indicators": self.indicators,
            "timestamp": self.timestamp.isoformat(),
        }


class BaseStrategy(ABC):
    """Abstract base class for all trading strategies."""

    name: str = "BaseStrategy"
    strategy_type: StrategyType = StrategyType.TREND_FOLLOWING

    def __init__(self, params: dict | None = None):
        self.params = params or {}

    @abstractmethod
    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        """
        Analyze market data and return a Signal or None if no opportunity.
        df must contain columns: timestamp, open, high, low, close, volume.
        """
        ...

    def validate_data(self, df: pd.DataFrame, min_rows: int = 50) -> bool:
        required = {"open", "high", "low", "close"}
        if not required.issubset(df.columns):
            return False
        return len(df) >= min_rows
