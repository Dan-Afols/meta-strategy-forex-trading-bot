"""
Breakout Strategy — detects support/resistance breakouts.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config.constants import SignalType, StrategyType, DEFAULT_STRATEGY_PARAMS, PIP_SIZE
from strategies.base import BaseStrategy, Signal
from utils.indicators import atr, support_resistance
from utils.math_helpers import signal_confidence


class BreakoutStrategy(BaseStrategy):
    name = "Breakout"
    strategy_type = StrategyType.BREAKOUT

    def __init__(self, params: dict | None = None):
        defaults = DEFAULT_STRATEGY_PARAMS["BREAKOUT"]
        merged = {**defaults, **(params or {})}
        super().__init__(merged)

    def analyze(self, df: pd.DataFrame, symbol: str, timeframe: str) -> Optional[Signal]:
        if not self.validate_data(df, min_rows=30):
            return None

        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df.get("volume", pd.Series(dtype=float))

        lookback = self.params["lookback_period"]
        atr_val = atr(high, low, close, self.params["atr_period"])
        curr_atr = atr_val.iloc[-1]

        # Support and resistance levels
        sr = support_resistance(high, low, close, lookback)
        recent_high = sr["recent_high"].iloc[-2]  # Previous bar's high
        recent_low = sr["recent_low"].iloc[-2]

        curr_price = close.iloc[-1]
        prev_price = close.iloc[-2]

        # Volume confirmation (if available)
        vol_confirmed = True
        if len(volume.dropna()) > lookback:
            avg_vol = volume.tail(lookback).mean()
            curr_vol = volume.iloc[-1]
            vol_confirmed = curr_vol > avg_vol * self.params["volume_multiplier"]

        # Range for breakout threshold
        price_range = recent_high - recent_low
        threshold = curr_atr * self.params["breakout_threshold"]

        pip = PIP_SIZE.get(symbol, 0.0001)

        # ── Bullish breakout ────────────────────────────────────────
        if (curr_price > recent_high and prev_price <= recent_high and
                curr_price - recent_high > threshold * 0.1):

            strength = min((curr_price - recent_high) / (curr_atr or 1), 1.0)
            indicators = {
                "breakout_strength": strength,
                "volume_confirmation": 1.0 if vol_confirmed else 0.3,
                "range_quality": min(price_range / (curr_atr * 3 or 1), 1.0),
            }
            conf = signal_confidence(indicators)

            sl = recent_low
            tp = curr_price + (curr_price - recent_low)

            return Signal(
                symbol=symbol,
                signal_type=SignalType.BUY,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=curr_price,
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                timeframe=timeframe,
                indicators=indicators,
            )

        # ── Bearish breakout ────────────────────────────────────────
        if (curr_price < recent_low and prev_price >= recent_low and
                recent_low - curr_price > threshold * 0.1):

            strength = min((recent_low - curr_price) / (curr_atr or 1), 1.0)
            indicators = {
                "breakout_strength": strength,
                "volume_confirmation": 1.0 if vol_confirmed else 0.3,
                "range_quality": min(price_range / (curr_atr * 3 or 1), 1.0),
            }
            conf = signal_confidence(indicators)

            sl = recent_high
            tp = curr_price - (recent_high - curr_price)

            return Signal(
                symbol=symbol,
                signal_type=SignalType.SELL,
                strategy=self.name,
                strategy_type=self.strategy_type,
                confidence=conf,
                entry_price=curr_price,
                stop_loss=round(sl, 5),
                take_profit=round(tp, 5),
                timeframe=timeframe,
                indicators=indicators,
            )

        return None
