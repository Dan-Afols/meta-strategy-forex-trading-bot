"""
Strategy Engine — orchestrates multiple strategies with intelligent
meta-strategy selection based on regime, session, and performance history.

Async architecture:
  - analyze_all_pairs() runs all pairs in PARALLEL via asyncio.gather
  - CPU-bound strategy.analyze() is offloaded to threads via asyncio.to_thread
  - DB writes for strategy results are deferred to background
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from config.constants import MarketRegime, StrategyType
from strategies.base import BaseStrategy, Signal
from strategies.trend_following import TrendFollowingStrategy
from strategies.mean_reversion import MeanReversionStrategy
from strategies.breakout import BreakoutStrategy
from strategies.volatility import VolatilityStrategy
from strategies.session_orb import SessionOpeningRangeBreakoutStrategy
from strategies.liquidity_sweep_reversal import LiquiditySweepReversalStrategy
from strategies.regime_detector import RegimeDetector
from strategies.meta_strategy import MetaStrategyEngine, MetaDecision
from database.session import get_session
from database import repository as repo
from utils.logging_config import get_logger

logger = get_logger("strategy_engine")

# Fallback regime map (only used when meta-strategy is disabled)
REGIME_STRATEGY_MAP: Dict[MarketRegime, List[StrategyType]] = {
    MarketRegime.STRONG_BULLISH: [StrategyType.TREND_FOLLOWING, StrategyType.BREAKOUT],
    MarketRegime.BULLISH: [StrategyType.TREND_FOLLOWING, StrategyType.BREAKOUT],
    MarketRegime.SIDEWAYS: [StrategyType.MEAN_REVERSION],
    MarketRegime.BEARISH: [StrategyType.TREND_FOLLOWING, StrategyType.BREAKOUT],
    MarketRegime.STRONG_BEARISH: [StrategyType.TREND_FOLLOWING, StrategyType.BREAKOUT],
    MarketRegime.HIGH_VOLATILITY: [StrategyType.VOLATILITY, StrategyType.BREAKOUT],
    MarketRegime.LOW_VOLATILITY: [StrategyType.MEAN_REVERSION],
}


class StrategyEngine:
    """
    Manages all strategies with meta-strategy selection.
    When meta-strategy is enabled, strategies are dynamically selected and
    weighted based on regime, session, and historical performance.
    """

    def __init__(self, use_meta_strategy: bool = True, lookback_days: int = 30):
        self.regime_detector = RegimeDetector()
        self.strategies: List[BaseStrategy] = [
            TrendFollowingStrategy(),
            MeanReversionStrategy(),
            BreakoutStrategy(),
            SessionOpeningRangeBreakoutStrategy(),
            LiquiditySweepReversalStrategy(),
            VolatilityStrategy(),
        ]
        self.min_confidence = 0.45
        self.use_meta_strategy = use_meta_strategy
        self.meta_engine = MetaStrategyEngine(lookback_days=lookback_days)
        self.strategy_bias: Dict[str, float] = {s.name: 1.0 for s in self.strategies}
        self._last_evolution: dict = {
            "updated_at": None,
            "min_confidence": self.min_confidence,
            "bias": self.strategy_bias.copy(),
            "changes": [],
        }

    def add_strategy(self, strategy: BaseStrategy) -> None:
        self.strategies.append(strategy)

    def get_strategies_for_regime(self, regime: MarketRegime) -> List[BaseStrategy]:
        """Fallback: return strategies suitable for the detected regime."""
        preferred = REGIME_STRATEGY_MAP.get(regime, [])
        if not preferred:
            return self.strategies
        return [s for s in self.strategies if s.strategy_type in preferred]

    async def analyze_pair(self, df: pd.DataFrame, symbol: str,
                           timeframe: str) -> List[Signal]:
        """
        Analyze a single currency pair.
        CPU-bound strategy.analyze() calls run in threads.
        DB writes for results are deferred to a background task.
        """
        if df.empty or len(df) < 50:
            return []

        decision: Optional[MetaDecision] = None

        if self.use_meta_strategy:
            # Meta-strategy: dynamic selection + weighting
            decision = await self.meta_engine.select_strategies(
                df, symbol, self.strategies
            )
            active_strategies = [
                s for s in self.strategies
                if s.name in decision.selected_strategies
            ]
            regime = decision.regime
            logger.info("Meta-strategy selected",
                        symbol=symbol,
                        regime=regime.value,
                        selected=[s.name for s in active_strategies],
                        reasoning_count=len(decision.reasoning))
        else:
            # Fallback: static regime-based selection
            regime = self.regime_detector.detect(df)
            active_strategies = self.get_strategies_for_regime(regime)

        regime_details = self.regime_detector.get_regime_details(df)
        logger.info("Regime detected", symbol=symbol, regime=regime.value,
                     details=json.dumps(regime_details))

        # Run all active strategies in parallel threads (CPU-bound work)
        async def _run_strategy(strategy: BaseStrategy) -> Optional[Signal]:
            try:
                signal = await asyncio.to_thread(
                    strategy.analyze, df, symbol, timeframe
                )
                if signal and signal.confidence >= self.min_confidence:
                    signal.market_regime = regime.value
                    if decision is not None:
                        signal = self.meta_engine.adjust_signal_confidence(
                            signal, decision
                        )

                    # Apply slow-moving adaptive bias per strategy
                    bias = self.strategy_bias.get(strategy.name, 1.0)
                    signal.confidence = max(0.0, min(1.0, signal.confidence * bias))
                    signal.metadata["evolution_bias"] = round(bias, 4)

                    if signal.confidence >= self.min_confidence:
                        logger.info("Signal generated",
                                    symbol=symbol,
                                    strategy=strategy.name,
                                    type=signal.signal_type.value,
                                    confidence=signal.confidence,
                                    meta_weight=signal.metadata.get("meta_weight"))
                        return signal
            except Exception as e:
                logger.error("Strategy error", strategy=strategy.name,
                             symbol=symbol, error=str(e))
            return None

        results = await asyncio.gather(
            *[_run_strategy(s) for s in active_strategies]
        )
        signals = [s for s in results if s is not None]

        # Rank by confidence
        signals.sort(key=lambda s: s.confidence, reverse=True)

        # Persist signals to DB (deferred — non-blocking)
        if signals:
            asyncio.create_task(self._save_signals_to_db(signals))

        return signals

    async def _save_signals_to_db(self, signals: List[Signal]) -> None:
        """Save strategy signals to database (runs as background task)."""
        try:
            session = await get_session()
            try:
                for sig in signals:
                    await repo.save_strategy_result(
                        session,
                        strategy=sig.strategy,
                        symbol=sig.symbol,
                        timeframe=sig.timeframe,
                        signal=sig.signal_type.value,
                        confidence=sig.confidence,
                        parameters=json.dumps(sig.metadata),
                        indicators=json.dumps(
                            {k: round(v, 4) for k, v in sig.indicators.items()}
                        ),
                        market_regime=sig.market_regime,
                    )
            finally:
                await session.close()
        except Exception as e:
            logger.error("Failed to save strategy results", error=str(e))

    async def analyze_all_pairs(self, data: Dict[str, pd.DataFrame],
                                timeframe: str) -> Dict[str, List[Signal]]:
        """Analyze all pairs in PARALLEL and return signals per pair."""
        async def _analyze_one(symbol: str, df: pd.DataFrame):
            signals = await self.analyze_pair(df, symbol, timeframe)
            return symbol, signals

        results = await asyncio.gather(
            *[_analyze_one(sym, df) for sym, df in data.items()]
        )
        return {sym: sigs for sym, sigs in results if sigs}

    def get_meta_decisions(self) -> Dict[str, dict]:
        """Get the latest meta-strategy decisions for all symbols."""
        return self.meta_engine.get_all_decisions()

    def get_meta_decision(self, symbol: str) -> Optional[dict]:
        """Get the latest meta-strategy decision for a specific symbol."""
        d = self.meta_engine.get_last_decision(symbol)
        return d.to_dict() if d else None

    async def evolve_from_performance(self, min_trades: int = 8) -> dict:
        """Conservative auto-evolution using recent closed-trade performance.

        This does NOT mutate strategy code. It only adjusts:
          - per-strategy confidence bias (0.80 to 1.20)
          - global min_confidence threshold (0.40 to 0.60)
        """
        session = await get_session()
        try:
            perfs = await repo.get_all_strategy_performances(session, days=30)
        finally:
            await session.close()

        if not perfs:
            return {
                "updated_at": None,
                "min_confidence": self.min_confidence,
                "bias": self.strategy_bias.copy(),
                "changes": [],
                "note": "no_closed_trade_data",
            }

        changes = []
        improving = 0
        degrading = 0

        for perf in perfs:
            name = perf.get("strategy")
            total = int(perf.get("total_trades", 0) or 0)
            if not name or total < max(1, min_trades):
                continue

            win_rate = float(perf.get("win_rate", 0.0) or 0.0)
            pf = float(perf.get("profit_factor", 0.0) or 0.0)

            old_bias = float(self.strategy_bias.get(name, 1.0))
            new_bias = old_bias

            if win_rate >= 0.58 and pf >= 1.2:
                new_bias = min(1.20, old_bias + 0.05)
                improving += 1
            elif win_rate <= 0.42 or pf < 0.90:
                new_bias = max(0.80, old_bias - 0.05)
                degrading += 1

            if abs(new_bias - old_bias) > 1e-9:
                self.strategy_bias[name] = new_bias
                changes.append({
                    "strategy": name,
                    "from": round(old_bias, 4),
                    "to": round(new_bias, 4),
                    "win_rate": round(win_rate, 4),
                    "profit_factor": round(pf, 4),
                    "trades": total,
                })

        old_min = self.min_confidence
        if degrading > improving and degrading >= 2:
            self.min_confidence = min(0.60, self.min_confidence + 0.02)
        elif improving > degrading and improving >= 2:
            self.min_confidence = max(0.40, self.min_confidence - 0.01)

        if abs(self.min_confidence - old_min) > 1e-9:
            changes.append({
                "setting": "min_confidence",
                "from": round(old_min, 4),
                "to": round(self.min_confidence, 4),
            })

        self._last_evolution = {
            "updated_at": datetime.utcnow().isoformat(),
            "min_confidence": round(self.min_confidence, 4),
            "bias": {k: round(v, 4) for k, v in self.strategy_bias.items()},
            "changes": changes,
        }

        logger.info("Strategy evolution updated",
                    min_confidence=self.min_confidence,
                    changes=len(changes))
        return self._last_evolution

    def get_evolution_state(self) -> dict:
        return self._last_evolution.copy()
