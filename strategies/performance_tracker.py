"""
Strategy Performance Tracker — monitors real-time performance metrics
per strategy/symbol/regime combination for meta-strategy selection.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from database.session import get_session
from database import repository as repo
from utils.logging_config import get_logger

logger = get_logger("performance_tracker")


@dataclass
class StrategyScore:
    """Composite score for a strategy in a given context."""
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
    data_quality: float = 0.0  # 0-1, how much data we have to trust score

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy,
            "symbol": self.symbol,
            "regime": self.regime,
            "total_trades": self.total_trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 3),
            "sharpe": round(self.sharpe, 3),
            "avg_pnl": round(self.avg_pnl, 4),
            "total_pnl": round(self.total_pnl, 2),
            "avg_confidence": round(self.avg_confidence, 4),
            "composite_score": round(self.composite_score, 4),
            "data_quality": round(self.data_quality, 4),
        }


class PerformanceTracker:
    """
    Tracks and scores strategy performance for meta-strategy selection.

    Scoring considers:
    - Win rate (weight: 0.25)
    - Profit factor (weight: 0.25)
    - Risk-adjusted returns / Sharpe (weight: 0.30)
    - Average confidence of signals (weight: 0.10)
    - Data quality / sample size (weight: 0.10)
    """

    # Scoring weights
    W_WIN_RATE = 0.25
    W_PROFIT_FACTOR = 0.25
    W_SHARPE = 0.30
    W_CONFIDENCE = 0.10
    W_DATA_QUALITY = 0.10

    # Minimum trades to trust a score
    MIN_TRADES_FULL_TRUST = 20
    MIN_TRADES_PARTIAL = 5

    def __init__(self, lookback_days: int = 30):
        self.lookback_days = lookback_days
        self._cache: Dict[str, StrategyScore] = {}
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=10)

    def _cache_key(self, strategy: str, symbol: str, regime: str) -> str:
        return f"{strategy}|{symbol}|{regime}"

    def _is_cache_valid(self) -> bool:
        if self._cache_time is None:
            return False
        return datetime.utcnow() - self._cache_time < self._cache_ttl

    def _compute_composite_score(self, perf: dict) -> StrategyScore:
        """Convert raw performance dict into a normalized composite score."""
        total = perf.get("total_trades", 0)

        # Data quality: sigmoid on trade count
        if total >= self.MIN_TRADES_FULL_TRUST:
            data_quality = 1.0
        elif total >= self.MIN_TRADES_PARTIAL:
            data_quality = total / self.MIN_TRADES_FULL_TRUST
        elif total > 0:
            data_quality = 0.2
        else:
            data_quality = 0.0

        # Normalize metrics to 0-1 range
        win_rate = perf.get("win_rate", 0.0)  # Already 0-1
        pf = perf.get("profit_factor", 0.0)
        pf_norm = min(pf / 3.0, 1.0)  # Cap at PF=3

        sharpe = perf.get("sharpe", 0.0)
        sharpe_norm = max(min((sharpe + 1.0) / 3.0, 1.0), 0.0)  # Map [-1,2] → [0,1]

        confidence = perf.get("avg_confidence", 0.0)  # Already ~0-1

        # Weighted composite
        composite = (
            self.W_WIN_RATE * win_rate
            + self.W_PROFIT_FACTOR * pf_norm
            + self.W_SHARPE * sharpe_norm
            + self.W_CONFIDENCE * confidence
            + self.W_DATA_QUALITY * data_quality
        )

        return StrategyScore(
            strategy=perf.get("strategy", "UNKNOWN"),
            symbol=perf.get("symbol", "ALL"),
            regime=perf.get("regime", "ALL"),
            total_trades=total,
            win_rate=win_rate,
            profit_factor=pf,
            sharpe=sharpe,
            avg_pnl=perf.get("avg_pnl", 0.0),
            total_pnl=perf.get("total_pnl", 0.0),
            avg_confidence=confidence,
            composite_score=composite,
            data_quality=data_quality,
        )

    async def get_strategy_scores(
        self,
        symbol: str | None = None,
        regime: str | None = None,
    ) -> List[StrategyScore]:
        """Get scored performances for all strategies, optionally filtered."""
        session = await get_session()
        try:
            perfs = await repo.get_all_strategy_performances(
                session, days=self.lookback_days
            )

            scores = []
            for perf in perfs:
                score = self._compute_composite_score(perf)
                scores.append(score)
                self._cache[self._cache_key(score.strategy, "ALL", "ALL")] = score

            # If regime-specific scores requested, fetch those too
            if regime:
                for perf in perfs:
                    strat = perf["strategy"]
                    regime_perf = await repo.get_strategy_performance(
                        session, strategy=strat, regime=regime,
                        days=self.lookback_days,
                    )
                    regime_score = self._compute_composite_score(regime_perf)
                    key = self._cache_key(strat, "ALL", regime)
                    self._cache[key] = regime_score

            # If symbol-specific scores requested
            if symbol:
                for perf in perfs:
                    strat = perf["strategy"]
                    sym_perf = await repo.get_strategy_performance(
                        session, strategy=strat, symbol=symbol,
                        days=self.lookback_days,
                    )
                    sym_score = self._compute_composite_score(sym_perf)
                    key = self._cache_key(strat, symbol, "ALL")
                    self._cache[key] = sym_score

            self._cache_time = datetime.utcnow()

            # Sort by composite score descending
            scores.sort(key=lambda s: s.composite_score, reverse=True)
            return scores

        finally:
            await session.close()

    async def get_strategy_ranking(
        self,
        symbol: str,
        regime: str,
    ) -> List[StrategyScore]:
        """
        Get a ranked list of strategies for a specific symbol + regime context.
        Blends overall performance with regime-specific and symbol-specific data.
        """
        session = await get_session()
        try:
            # Get distinct strategies
            perfs = await repo.get_all_strategy_performances(
                session, days=self.lookback_days
            )
            strategy_names = list({p["strategy"] for p in perfs})

            if not strategy_names:
                return []

            rankings: List[StrategyScore] = []
            for strat in strategy_names:
                # 3 performance slices: overall, by-regime, by-symbol
                overall = await repo.get_strategy_performance(
                    session, strategy=strat, days=self.lookback_days
                )
                by_regime = await repo.get_strategy_performance(
                    session, strategy=strat, regime=regime, days=self.lookback_days
                )
                by_symbol = await repo.get_strategy_performance(
                    session, strategy=strat, symbol=symbol, days=self.lookback_days
                )

                s_overall = self._compute_composite_score(overall)
                s_regime = self._compute_composite_score(by_regime)
                s_symbol = self._compute_composite_score(by_symbol)

                # Blend: regime-specific > symbol-specific > overall
                # Weight by data quality
                total_weight = 0.0
                blended_score = 0.0

                w_overall = 0.3 * max(s_overall.data_quality, 0.1)
                w_regime = 0.4 * max(s_regime.data_quality, 0.01)
                w_symbol = 0.3 * max(s_symbol.data_quality, 0.01)

                blended_score = (
                    w_overall * s_overall.composite_score
                    + w_regime * s_regime.composite_score
                    + w_symbol * s_symbol.composite_score
                )
                total_weight = w_overall + w_regime + w_symbol

                if total_weight > 0:
                    blended_score /= total_weight

                # Use overall stats as base, override score
                final = StrategyScore(
                    strategy=strat,
                    symbol=symbol,
                    regime=regime,
                    total_trades=s_overall.total_trades,
                    win_rate=s_overall.win_rate,
                    profit_factor=s_overall.profit_factor,
                    sharpe=s_overall.sharpe,
                    avg_pnl=s_overall.avg_pnl,
                    total_pnl=s_overall.total_pnl,
                    avg_confidence=s_overall.avg_confidence,
                    composite_score=blended_score,
                    data_quality=max(
                        s_overall.data_quality,
                        s_regime.data_quality,
                        s_symbol.data_quality,
                    ),
                )
                rankings.append(final)

            rankings.sort(key=lambda s: s.composite_score, reverse=True)
            return rankings

        finally:
            await session.close()

    async def record_trade_outcome(
        self, strategy: str, symbol: str, regime: str, pnl: float
    ) -> None:
        """Invalidate cache when a new trade outcome arrives."""
        self._cache_time = None  # Force cache refresh
        logger.info("Trade outcome recorded, cache invalidated",
                     strategy=strategy, symbol=symbol, regime=regime,
                     pnl=round(pnl, 2))
