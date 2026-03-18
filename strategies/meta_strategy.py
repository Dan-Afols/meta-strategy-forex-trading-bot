"""
Meta-Strategy Selection Engine — dynamically selects and weights strategies
based on market conditions, session context, and historical performance.

This replaces the static REGIME_STRATEGY_MAP with an intelligent selection
layer that learns which strategies perform best in specific contexts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from config.constants import MarketRegime, StrategyType
from strategies.base import BaseStrategy, Signal
from strategies.performance_tracker import PerformanceTracker, StrategyScore
from strategies.regime_detector import RegimeDetector
from data.session_detector import SessionDetector, SessionInfo
from utils.logging_config import get_logger

logger = get_logger("meta_strategy")

# Baseline regime preferences (used when insufficient historical data)
_REGIME_PRIORS: Dict[MarketRegime, Dict[StrategyType, float]] = {
    MarketRegime.STRONG_BULLISH: {
        StrategyType.TREND_FOLLOWING: 0.9,
        StrategyType.BREAKOUT: 0.7,
        StrategyType.VOLATILITY: 0.4,
        StrategyType.MEAN_REVERSION: 0.1,
    },
    MarketRegime.BULLISH: {
        StrategyType.TREND_FOLLOWING: 0.8,
        StrategyType.BREAKOUT: 0.6,
        StrategyType.VOLATILITY: 0.3,
        StrategyType.MEAN_REVERSION: 0.2,
    },
    MarketRegime.SIDEWAYS: {
        StrategyType.MEAN_REVERSION: 0.9,
        StrategyType.BREAKOUT: 0.3,
        StrategyType.TREND_FOLLOWING: 0.1,
        StrategyType.VOLATILITY: 0.2,
    },
    MarketRegime.BEARISH: {
        StrategyType.TREND_FOLLOWING: 0.8,
        StrategyType.BREAKOUT: 0.6,
        StrategyType.VOLATILITY: 0.3,
        StrategyType.MEAN_REVERSION: 0.2,
    },
    MarketRegime.STRONG_BEARISH: {
        StrategyType.TREND_FOLLOWING: 0.9,
        StrategyType.BREAKOUT: 0.7,
        StrategyType.VOLATILITY: 0.4,
        StrategyType.MEAN_REVERSION: 0.1,
    },
    MarketRegime.HIGH_VOLATILITY: {
        StrategyType.VOLATILITY: 0.9,
        StrategyType.BREAKOUT: 0.6,
        StrategyType.TREND_FOLLOWING: 0.3,
        StrategyType.MEAN_REVERSION: 0.1,
    },
    MarketRegime.LOW_VOLATILITY: {
        StrategyType.MEAN_REVERSION: 0.8,
        StrategyType.TREND_FOLLOWING: 0.3,
        StrategyType.BREAKOUT: 0.2,
        StrategyType.VOLATILITY: 0.1,
    },
}


@dataclass
class MetaDecision:
    """Explains a meta-strategy selection decision."""
    symbol: str
    regime: MarketRegime
    session: SessionInfo
    strategy_weights: Dict[str, float]    # strategy_name → weight 0-1
    selected_strategies: List[str]        # ordered by weight
    excluded_strategies: List[str]
    reasoning: List[str]
    confidence: float  # Overall confidence in the selection

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "regime": self.regime.value,
            "sessions": [s.value for s in self.session.active_sessions],
            "strategy_weights": {k: round(v, 4) for k, v in self.strategy_weights.items()},
            "selected_strategies": self.selected_strategies,
            "excluded_strategies": self.excluded_strategies,
            "reasoning": self.reasoning,
            "confidence": round(self.confidence, 4),
        }


class MetaStrategyEngine:
    """
    Selects strategies dynamically using:
    1. Current market regime (from RegimeDetector)
    2. Active trading session (from SessionDetector)
    3. Historical strategy performance (from PerformanceTracker)
    4. Baseline regime priors (when data is insufficient)

    The output is a weighted set of strategies to run for each symbol,
    with higher weights boosting signal confidence.
    """

    # Below this weight, a strategy is excluded entirely
    MIN_WEIGHT_THRESHOLD = 0.20
    # Blend ratio: how much historical data overrides base priors
    # 0.0 = fully prior-based, 1.0 = fully data-driven
    MAX_DATA_BLEND = 0.70

    def __init__(self, lookback_days: int = 30):
        self.tracker = PerformanceTracker(lookback_days=lookback_days)
        self.regime_detector = RegimeDetector()
        self.session_detector = SessionDetector()
        self._last_decisions: Dict[str, MetaDecision] = {}

    async def select_strategies(
        self,
        df: pd.DataFrame,
        symbol: str,
        strategies: List[BaseStrategy],
    ) -> MetaDecision:
        """
        Determine which strategies to run for a symbol and how to weight them.
        Returns a MetaDecision with ranked strategy weights.
        """
        reasoning: List[str] = []

        # 1. Detect regime
        regime = self.regime_detector.detect(df)
        regime_details = self.regime_detector.get_regime_details(df)
        reasoning.append(f"Regime: {regime.value} (ADX={regime_details['adx']}, "
                         f"vol_ratio={regime_details['volatility_ratio']})")

        # 2. Detect session
        session = self.session_detector.detect()
        if session.is_overlap:
            reasoning.append(f"Session overlap: {', '.join(session.overlap_sessions)} → HIGH volatility expected")
        elif session.active_sessions:
            reasoning.append(f"Active session: {', '.join(s.value for s in session.active_sessions)}")
        else:
            reasoning.append("No major session active → LOW volatility expected")

        # 3. Get baseline regime priors
        priors = _REGIME_PRIORS.get(regime, {})
        strategy_map: Dict[str, BaseStrategy] = {s.name: s for s in strategies}

        weights: Dict[str, float] = {}
        for strat in strategies:
            prior_weight = priors.get(strat.strategy_type, 0.3)
            weights[strat.name] = prior_weight

        reasoning.append(f"Prior weights: {_fmt_weights(weights)}")

        # 4. Overlay historical performance
        rankings = await self.tracker.get_strategy_ranking(symbol, regime.value)
        ranking_map: Dict[str, StrategyScore] = {r.strategy: r for r in rankings}

        if rankings:
            # Determine blend ratio based on data quality
            avg_quality = sum(r.data_quality for r in rankings) / len(rankings)
            blend = min(avg_quality, self.MAX_DATA_BLEND)
            reasoning.append(f"Data blend: {blend:.0%} data-driven, "
                             f"{1-blend:.0%} prior-driven (avg quality={avg_quality:.2f})")

            for strat_name in list(weights.keys()):
                if strat_name in ranking_map:
                    score = ranking_map[strat_name]
                    data_weight = score.composite_score
                    prior_weight = weights[strat_name]
                    weights[strat_name] = (
                        prior_weight * (1 - blend) + data_weight * blend
                    )

            reasoning.append(f"Blended weights: {_fmt_weights(weights)}")
        else:
            reasoning.append("No historical data → using regime priors only")

        # 5. Session adjustments
        if session.volatility_expectation == "LOW":
            # Reduce breakout/volatility weights in quiet sessions
            for strat in strategies:
                if strat.strategy_type in (StrategyType.BREAKOUT, StrategyType.VOLATILITY):
                    weights[strat.name] *= 0.7
            reasoning.append("Low-volatility session: reduced breakout/volatility weights")
        elif session.volatility_expectation == "HIGH":
            # Boost volatility strategy in active overlaps
            for strat in strategies:
                if strat.strategy_type == StrategyType.VOLATILITY:
                    weights[strat.name] *= 1.2
            reasoning.append("High-volatility session: boosted volatility weights")

        # Pair-session affinity: if symbol matches best pairs for session, boost
        if symbol in session.best_pairs:
            for strat_name in weights:
                weights[strat_name] *= 1.1
            reasoning.append(f"{symbol} is a top pair for current session → small boost")

        # 6. Clamp weights to [0, 1]
        for k in weights:
            weights[k] = max(0.0, min(1.0, weights[k]))

        # 7. Partition into selected / excluded
        selected = []
        excluded = []
        for strat_name, w in sorted(weights.items(), key=lambda x: x[1], reverse=True):
            if w >= self.MIN_WEIGHT_THRESHOLD:
                selected.append(strat_name)
            else:
                excluded.append(strat_name)
                reasoning.append(
                    f"Excluded {strat_name}: weight {w:.3f} < threshold {self.MIN_WEIGHT_THRESHOLD}"
                )

        # Overall confidence: average of selected weights
        if selected:
            overall_conf = sum(weights[s] for s in selected) / len(selected)
        else:
            overall_conf = 0.0

        decision = MetaDecision(
            symbol=symbol,
            regime=regime,
            session=session,
            strategy_weights=weights,
            selected_strategies=selected,
            excluded_strategies=excluded,
            reasoning=reasoning,
            confidence=overall_conf,
        )

        self._last_decisions[symbol] = decision
        logger.info("Meta-strategy decision",
                     symbol=symbol,
                     regime=regime.value,
                     selected=selected,
                     weights=_fmt_weights(weights))

        return decision

    def adjust_signal_confidence(self, signal: Signal, decision: MetaDecision) -> Signal:
        """
        Adjust a signal's confidence based on the meta-strategy weight
        for that signal's strategy. Higher-weighted strategies get a boost.
        """
        weight = decision.strategy_weights.get(signal.strategy, 0.5)
        # Scale confidence: weight=1.0 → 1.15x, weight=0.5 → 1.0x, weight=0.2 → 0.85x
        multiplier = 0.7 + 0.45 * weight
        signal.confidence = max(0.0, min(1.0, signal.confidence * multiplier))
        signal.metadata["meta_weight"] = round(weight, 4)
        signal.metadata["meta_regime"] = decision.regime.value
        return signal

    def get_last_decision(self, symbol: str) -> Optional[MetaDecision]:
        return self._last_decisions.get(symbol)

    def get_all_decisions(self) -> Dict[str, dict]:
        return {symbol: d.to_dict() for symbol, d in self._last_decisions.items()}


def _fmt_weights(w: Dict[str, float]) -> str:
    return ", ".join(f"{k}={v:.3f}" for k, v in sorted(w.items(), key=lambda x: -x[1]))
